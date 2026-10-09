"""Dedicated local browser service. All Playwright objects stay on one worker thread.

No browser extension, shared daily profile, credential export or remote debug port.
Searches are bounded, user-triggered, read-only and always report coverage limits.
"""
import hashlib
import os
import queue
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from independent_search import GUARD, TZ, canonical, jobs_from_ld, plain, read, relevant, stamp, write
from browser_import import import_page

ROOT = Path(__file__).resolve().parent
SITES = {
    'DTU JobTeaser': 'https://dtu.jobteaser.com/en/job-offers?contract=part_time&localized_location=Denmark&location=Denmark&sort=recency',
    'LinkedIn Jobs': 'https://www.linkedin.com/jobs/search/?keywords=student&location=Copenhagen%2C%20Denmark&f_TPR=r604800&sortBy=DD',
}
MAX_PAGES = 10
MAX_DETAILS = 40

# Read public job elements only. Never read form values, cookies or browser storage.
EXTRACT = r'''() => ({url:location.href, title:document.title,
 headings:[...document.querySelectorAll('h1')].map(e=>e.innerText),
 links:[...document.querySelectorAll('a[href]')].map(e=>({url:e.href,text:e.innerText.trim(),
 card:(e.closest('li,article,[data-job-id]')?.innerText||'').slice(0,1800)})),
 dates:[...document.querySelectorAll('time[datetime]')].map(e=>({value:e.dateTime,text:e.innerText})),
 scripts:[...document.querySelectorAll('script[type="application/ld+json"]')].map(e=>e.textContent),
 text:(document.querySelector('main')||document.body).innerText.slice(0,80000)})'''

def job_link(site, url):
    p = urlparse(url)
    if p.scheme != 'https':
        return False
    if site == 'DTU JobTeaser':
        return p.hostname == 'dtu.jobteaser.com' and bool(re.fullmatch(r'/(en|da)/job-offers/[^/]+/?', p.path))
    return p.hostname in ('linkedin.com', 'www.linkedin.com') and bool(re.match(r'^/jobs/view/\d+/?$', p.path))

def blocked_reason(site, snapshot):
    url = snapshot['url'].lower()
    text = (snapshot.get('title', '') + ' ' + snapshot.get('text', '')[:8000]).lower()
    if any(word in url for word in ('/checkpoint', '/challenge', '/captcha')) or any(word in text for word in ('verify you are human', 'unusual activity', 'security verification', 'access denied')):
        return 'Website verification or access restriction needs your attention. Nothing was bypassed.'
    if any(word in url for word in ('/login', '/signin', '/sign_in', '/auth', 'login.microsoftonline.com', '/uas/')):
        return 'Sign in directly in the dedicated browser, then click Search again.'
    if urlparse(url).hostname not in ('dtu.jobteaser.com', 'linkedin.com', 'www.linkedin.com'):
        return 'Sign in directly in the dedicated browser, then click Search again.'
    if not any(job_link(site, link['url']) for link in snapshot.get('links', [])) and ('sign in to view' in text or 'log in to view' in text):
        return 'Sign in directly in the dedicated browser, then click Search again.'
    return ''

def parse_posting(site, url, snapshot, today=None):
    """Only original structured publication dates establish freshness; no updated dates."""
    today = today or datetime.now(TZ).date()
    structured = []
    for text in snapshot.get('scripts', []):
        try:
            import json
            structured.extend(jobs_from_ld(json.loads(text)))
        except (ValueError, TypeError):
            continue
    posting = next((j for j in structured if not j.get('url') or canonical(j['url']) == canonical(url)), {})
    title = plain(posting.get('title') or next(iter(snapshot.get('headings', [])), ''))
    description = plain(posting.get('description') or snapshot.get('text', ''))
    if not relevant(title + ' ' + description):
        return None, 'Not a relevant student role'
    if re.search(r'\b(internship|praktik|ph\.?d|postdoc|thesis)\b', title, re.I):
        return None, 'Internship/thesis or non-student employment'
    if re.search(r'danish\s+(?:is\s+)?(?:required|mandatory|essential)|(?:must|required to)\s+(?:speak|know|be fluent in)\s+danish|(?:fluent|proficient)\s+(?:in\s+)?danish\s+(?:is\s+)?(?:required|mandatory|essential)', description, re.I):
        return None, 'Explicit mandatory Danish requirement'
    employment = posting.get('employmentType', [])
    if isinstance(employment, str):employment = [employment]
    if 'FULL_TIME' in employment and 'PART_TIME' not in employment:
        return None, 'Structured posting specifies full-time employment'
    raw_date = str(posting.get('datePosted', ''))[:10]
    try:
        published = datetime.strptime(raw_date, '%Y-%m-%d').date()
    except ValueError:
        return None, 'Original publication date unverified'
    if not today - timedelta(days=7) <= published <= today:
        return None, 'Outside last-seven-days publication window'
    deadline = str(posting.get('validThrough', ''))[:10]
    if deadline:
        try:
            if datetime.strptime(deadline, '%Y-%m-%d').date() < today:
                return None, 'Deadline already passed'
        except ValueError:
            deadline = ''
    organization = posting.get('hiringOrganization') or {}
    company = organization.get('name', '') if isinstance(organization, dict) else ''
    location = posting.get('jobLocation') or {}
    if isinstance(location, list):
        location = location[0] if location else {}
    address = location.get('address', {}) if isinstance(location, dict) else {}
    city = plain(address.get('addressLocality', '')) if isinstance(address, dict) else ''
    country = address.get('addressCountry', '') if isinstance(address, dict) else ''
    if isinstance(country, dict):country = country.get('name', '')
    if country and str(country).lower() not in ('dk', 'dnk', 'denmark', 'danmark'):
        return None, 'Workplace outside Denmark'
    if re.search(r'aalborg|aarhus|odense|esbjerg|sønderborg|herning|kolding|vejle', city, re.I):
        return None, 'Outside candidate commuting region'
    return dict(url=canonical(url), role=title, company=plain(company), description=description[:15000],
                posted_date=raw_date, deadline=deadline, location=city), ''

class BrowserService:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.commands = queue.Queue()
        self.lock = threading.Lock()
        self.state = {'running': False, 'status': 'idle', 'message': 'Dedicated browser ready to open.'}
        self.thread = None
        self.context = None
        self.playwright = None
        self.stop_requested = threading.Event()

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def update(self, **fields):
        with self.lock:
            self.state.update(fields)

    def submit(self, action, site=None):
        if action not in ('open', 'search', 'stop') or site and site not in SITES:
            raise ValueError('Unknown browser action or site')
        if action == 'search' and not site:
            raise ValueError('Choose a website')
        if action == 'stop':
            self.stop_requested.set()
            return
        with self.lock:
            if self.state['running']:
                raise ValueError('A browser operation is already running')
            self.state.update(running=True, status='starting', message='Opening dedicated Chromium...', site=site)
        self.stop_requested.clear()
        self.commands.put((action, site))
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self.worker, daemon=True)
            self.thread.start()

    def ensure_browser(self):
        if self.context is not None:
            try:
                self.context.new_page().close()
                return
            except Exception:
                self.context = None
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(self.root / '.runtime/browsers')
        from playwright.sync_api import sync_playwright
        if self.playwright is None:
            self.playwright = sync_playwright().start()
        self.context = self.playwright.chromium.launch_persistent_context(
            str(self.root / '.local-browser/profile'), headless=False,
            accept_downloads=False, chromium_sandbox=True, viewport=None,
            ignore_default_args=['--password-store=basic', '--use-mock-keychain', '--unsafely-disable-devtools-self-xss-warnings', '--enable-unsafe-swiftshader'],
        )
        self.context.set_default_timeout(8000)
        page = self.context.pages[0] if self.context.pages else self.context.new_page()
        page.goto('http://127.0.0.1:8765', wait_until='domcontentloaded')

    def site_page(self, site):
        host = urlparse(SITES[site]).hostname
        return next((p for p in self.context.pages if urlparse(p.url).hostname == host), None) or self.context.new_page()

    def worker(self):
        while True:
            try:
                action, site = self.commands.get(timeout=.2)
            except queue.Empty:
                # Pump Playwright events without scheduling or starting any searches.
                if self.context:
                    try:
                        pages = self.context.pages
                        if pages:
                            pages[0].wait_for_timeout(100)
                    except Exception:
                        self.context = None
                continue
            try:
                self.ensure_browser()
                if action == 'open':
                    if site:
                        page = self.site_page(site)
                        page.goto(SITES[site], wait_until='domcontentloaded', timeout=30000)
                        page.bring_to_front()
                    self.update(status='ready', message='Browser opened. Sign in directly, then click the website Search button.')
                else:
                    self.search(site)
            except Exception as exc:
                self.update(status='failed', message='Browser operation failed: ' + str(exc)[:600])
                if site:
                    self.health(site, 'Blocked / failed', self.snapshot()['message'])
            finally:
                self.update(running=False, finished_at=stamp())

    def health(self, site, status, detail):
        with GUARD:
            path = self.root / 'job_scraper/search_health.json'
            rows = read(path, [])
            row = next((r for r in rows if r['site'] == site), None)
            if row is None:
                row = {'site': site}
                rows.append(row)
            row.update(last_checked=stamp(), status=status, detail=detail)
            write(path, rows)

    def search(self, site):
        import json
        started = stamp()
        page = self.site_page(site)
        page.goto(SITES[site], wait_until='domcontentloaded', timeout=30000)
        page.bring_to_front()
        try:
            page.locator('a[href*="/job-offers/"],a[href*="/jobs/view/"]').first.wait_for(timeout=12000)
        except Exception:
            pass
        jobs, visited, exclusions = {}, set(), {}
        pages_read = 0
        reason = ''
        for number in range(MAX_PAGES):
            if self.stop_requested.is_set():
                reason = 'Stopped by user'; break
            snapshot = page.evaluate(EXTRACT)
            reason = blocked_reason(site, snapshot)
            if reason:
                break
            links = {}
            for link in snapshot['links']:
                if job_link(site, link['url']):
                    key = canonical(link['url'])
                    if key not in links or len(link['text']) > len(links[key]['text']):links[key] = link
            fingerprint = tuple(sorted(links))
            if not links or fingerprint in visited:
                reason = 'No readable results or repeated page; inventory unverified'; break
            visited.add(fingerprint)
            pages_read += 1
            for url, card in links.items():
                if url not in jobs and (relevant(card['text'] + ' ' + card['card']) or re.search(r'student|studentermedhj|studiejob', card['text'] + ' ' + card['card'], re.I)):
                    jobs[url] = card
            self.update(status='searching', message=f'{site}: read {pages_read} result pages; {len(jobs)} relevant links found.')
            # Accessible next-page controls only; never guess URL pagination parameters.
            next_button = page.get_by_role('button', name=re.compile(r'^(?:go to )?(next(?: page)?|suivant|næste(?: side)?)$', re.I))
            next_link = page.locator('a[rel="next"]')
            target = next_button if next_button.count() else next_link
            if not target.count() or not target.first.is_visible() or not target.first.is_enabled():
                reason = 'No supported next-page control; further results unverified'; break
            if number == MAX_PAGES - 1:
                reason = 'Result-page safety limit reached'; break
            target.first.click()
            page.wait_for_timeout(1500)
        found, details = [], 0
        detail_page = self.context.new_page()
        try:
            for url in list(jobs)[:MAX_DETAILS]:
                if self.stop_requested.is_set():
                    reason = 'Stopped by user'; break
                self.update(message=f'{site}: checking posting {details + 1} of {min(len(jobs), MAX_DETAILS)}.')
                try:
                    detail_page.goto(url, wait_until='domcontentloaded', timeout=25000)
                    detail_page.wait_for_timeout(1000)
                    snapshot = detail_page.evaluate(EXTRACT)
                    blocked = blocked_reason(site, snapshot)
                    if blocked:
                        reason = blocked; break
                    if not job_link(site, snapshot['url']):
                        exclusion = 'Posting redirected outside supported job page'
                        item = None
                    else:
                        item, exclusion = parse_posting(site, url, snapshot)
                    details += 1
                    if item:
                        found.append(item)
                    else:
                        exclusions[exclusion] = exclusions.get(exclusion, 0) + 1
                except Exception:
                    exclusions['Posting could not be read'] = exclusions.get('Posting could not be read', 0) + 1
        finally:
            detail_page.close()
        if len(jobs) > MAX_DETAILS:
            reason += '; posting limit reached'
        with GUARD:
            result = import_page(self.root, {'page_url': SITES[site], 'jobs': found})
            path = self.root / 'job_scraper/candidate_inbox.json'
            inbox = read(path, {})
            for item in found:
                key = hashlib.sha256(canonical(item['url']).encode()).hexdigest()[:20]
                # Preserve earlier candidates and all reviewed/user records.
                if key in inbox and inbox[key].get('discovered_at', '') >= started:
                    inbox[key].update(location=item['location'], deadline=item['deadline'], description=item['description'],
                        why_fit='Student technical/design keyword match from original posting; fit still requires review.',
                        missing='Verify mandatory skills, English eligibility, exact workplace, cycling route ≤25 km, commute ≤90 minutes and actual calendar-month roster ≤90 hours.')
            write(path, inbox)
        status = 'needs_attention' if ('Sign in' in reason or 'verification' in reason) else 'stopped' if self.stop_requested.is_set() else 'partial'
        message = f'{site}: {pages_read} result pages, {details} postings checked, {result["added"]} new candidates. {reason}. Publication filter: seven days.'
        self.health(site, 'Browser search · ' + status, message + ' Exclusions: ' + json.dumps(exclusions))
        self.update(status=status, message=message, pages_read=pages_read, details_checked=details, added=result['added'])
        entry = dict(site=site, started_at=started, finished_at=stamp(), status=status, publication_filter_days=7,
                     pages_read=pages_read, details_checked=details, added=result['added'], exclusions=exclusions, limitation=reason)
        with (self.root / 'job_scraper/browser_search_runs.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + '\n')

