"""Local dashboard. Reads the agent's records; edits are stored as dashboard overlays."""
import csv
import hashlib
import json
import mimetypes
import os
import secrets
import threading
from datetime import datetime
from independent_search import Runner, read as local_read, write as atomic_write, GUARD, canonical, sources
from browser_import import import_page
from browser_search import BrowserService, SITES as BROWSER_SITES
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
from initialize_data import initialize
initialize(ROOT)
STATE = ROOT / 'job_scraper' / 'dashboard_records.json'
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.Lock()
SEARCH = Runner()
BROWSER = BrowserService()
OPERATION_LOCK = threading.Lock()
ALL_STATE = {'running': False, 'message': 'Ready'}

def search_all():
    """One manual command: public readers, then dedicated browser readers."""
    try:
        ALL_STATE.update(message='Searching public websites…')
        SEARCH.start('all', 7)
        import time
        while SEARCH.state.get('running'): time.sleep(.25)
        ALL_STATE.update(message='Searching browser websites. Sign in directly if a site asks.')
        if ALL_STATE.get('stop_requested'):
            ALL_STATE.update(message='Search stopped by you.')
            return
        BROWSER.submit('all')
        while BROWSER.snapshot().get('running'): time.sleep(.25)
        ALL_STATE.update(message='All search attempts finished. Check website coverage and new candidates.')
    except Exception as exc:
        ALL_STATE.update(message='Search stopped: ' + str(exc))
    finally:
        ALL_STATE['running'] = False
ALLOWED = ('documents', 'cv', 'cover_letters', 'outbox')

def read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def rows():
    result = {}
    seen = read_json(ROOT / 'job_scraper/seen_jobs.json', {'seen': {}}).get('seen', {})
    for key, value in seen.items():
        if not isinstance(value, dict):
            continue
        uid = 'seen-' + hashlib.sha256(key.encode()).hexdigest()[:16]
        result[uid] = dict(value, id=uid, role=value.get('role') or value.get('title', ''), status='saved', url=value.get('url', ''), origin='Agent search')
    tracker = ROOT / 'job_search_tracker.csv'
    if tracker.exists():
        with tracker.open(encoding='utf-8-sig', newline='') as stream:
            for i, value in enumerate(csv.DictReader(stream)):
                source = value.get('source', '')
                existing = next((k for k, v in result.items() if source and v.get('url') == source), None)
                uid = existing or 'tracker-' + hashlib.sha256((str(i)+value.get('company','')+value.get('role','')).encode()).hexdigest()[:16]
                result[uid] = dict(result.get(uid, {}), **value, id=uid, url=source, origin='Application tracker')
    for uid, value in read_json(STATE, {}).items():
        result[uid] = dict(result.get(uid, {}), **value, id=uid)
    return list(result.values())

def documents():
    out = []
    for folder in ALLOWED:
        for path in (ROOT / folder).rglob('*'):
            if path.is_file() and path.suffix.lower() in ('.pdf', '.tex', '.docx', '.md'):
                out.append({'name': path.name, 'path': path.relative_to(ROOT).as_posix(), 'group': folder})
    return out

class Handler(BaseHTTPRequestHandler):
    def reply(self, data, code=200, mime='application/json'):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.headers.get('Host') not in ('127.0.0.1:8765', 'localhost:8765'):
            return self.reply({'error': 'Invalid host'}, 403)
        path = unquote(urlparse(self.path).path)
        try:
            if path == '/api/data':
                return self.reply({'jobs': rows(), 'documents': documents(), 'profile': (ROOT / 'PROFILE-AND-TIMELINE.md').read_text(encoding='utf-8'), 'search_health': read_json(ROOT / 'job_scraper/search_health.json', []), 'token': TOKEN})
            if path == '/api/search':
                return self.reply({'all': dict(ALL_STATE), 'run': SEARCH.state, 'browser': BROWSER.snapshot(), 'candidates': list(read_json(ROOT / 'job_scraper/candidate_inbox.json', {}).values()),'sources':[{'name':name,'url':url,'browser_required':name in BROWSER_SITES,'login_required':name in ('DTU JobTeaser','LinkedIn Jobs')} for name,url,_ in sources('all')]})
            if path == '/':
                return self.reply((ROOT / 'index.html').read_bytes(), mime='text/html; charset=utf-8')
            if path.startswith('/files/'):
                relative = Path(path[7:])
                target = (ROOT / relative).resolve()
                if target.is_relative_to(ROOT) and relative.parts and relative.parts[0] in ALLOWED and target.is_file() and target.suffix.lower() in ('.pdf','.tex','.docx','.md'):
                    return self.reply(target.read_bytes(), mime=mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
            return self.reply({'error': 'Not found'}, 404)
        except (ValueError, OSError) as exc:
            return self.reply({'error': str(exc)}, 500)

    def do_POST(self):
        if self.headers.get('Host') not in ('127.0.0.1:8765', 'localhost:8765') or self.headers.get('X-Dashboard-Token') != TOKEN:
            return self.reply({'error': 'Unauthorized'}, 403)
        if self.path not in ('/api/jobs','/api/search','/api/inbox','/api/browser-import','/api/browser'):
            return self.reply({'error': 'Not found'}, 404)
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 100000:
                return self.reply({'error': 'Invalid request size'}, 400)
            item = json.loads(self.rfile.read(length))
            if not isinstance(item,dict):raise ValueError('JSON object required')
            if self.path == '/api/browser-import':
                with GUARD:return self.reply(import_page(ROOT,item))
            if self.path == '/api/browser':
                with OPERATION_LOCK:
                    if (SEARCH.state.get('running') or ALL_STATE['running']) and item.get('action') != 'stop':
                        raise ValueError('Wait for the public search to finish')
                    if item.get('action') == 'stop':
                        ALL_STATE['stop_requested'] = True
                        SEARCH.stop_requested = True
                    BROWSER.submit(item.get('action'),item.get('site'))
                return self.reply({'started':True})
            if self.path == '/api/search':
                group=item.get('group','all')
                if group not in ('all','weekday','twice') and group not in {name for name,_,_ in sources('all')}:raise ValueError('Invalid search source')
                with OPERATION_LOCK:
                    if ALL_STATE['running']:raise ValueError('Wait for Search all to finish')
                    if BROWSER.snapshot().get('running'):raise ValueError('Wait for the browser search to finish')
                    if group == 'all':
                        ALL_STATE.update(running=True,stop_requested=False,message='Starting all website searches')
                        threading.Thread(target=search_all,daemon=True).start()
                    elif group in BROWSER_SITES:BROWSER.submit('search',group)
                    else:SEARCH.start(group,7)
                return self.reply({'started':True})
            if self.path == '/api/inbox':
                if item.get('state') not in ('dismissed','pending'):raise ValueError('Invalid inbox action')
                with GUARD:
                    inbox=read_json(ROOT/'job_scraper/candidate_inbox.json',{})
                    if item.get('id') not in inbox:raise ValueError('Candidate not found')
                    inbox[item['id']]['state']=item['state']
                    atomic_write(ROOT/'job_scraper/candidate_inbox.json',inbox)
                return self.reply({'saved':True})
            if not isinstance(item, dict) or not isinstance(item.get('company'), str) or not item['company'].strip() or not isinstance(item.get('role'), str) or not item['role'].strip():
                return self.reply({'error': 'Company and role are required'}, 400)
            statuses = ('saved','drafting','applied','interview','offer','rejected','withdrawn','expired','removed')
            if item.get('status') not in statuses:
                return self.reply({'error': 'Invalid status'}, 400)
            for field in ('commute','monthly_hours','fit'):
                if item.get(field, '') != '':
                    number = float(item[field])
                    if not 0 <= number <= (100 if field == 'fit' else 10000):
                        raise ValueError('Invalid ' + field)
            if item.get('url') and urlparse(item['url']).scheme not in ('https','http'):
                raise ValueError('Job link must begin with https:// or http://')
            uid = item.get('id') or 'manual-' + secrets.token_hex(8)
            with LOCK, GUARD:
                saved = read_json(STATE, {})
                previous=next((j for j in rows() if j['id']==uid),{})
                fields=('company','role','status','url','deadline','posted_date','older_fit_exception','category','location','fit','fit_level','commute','monthly_hours','danish','notes','cv_file','cover_letter_file','why_fit','missing','commute_mode','commute_rule_status','cycling_options','cycle_distance_km','cycle_minutes','transit_minutes','cycling_source','commute_assessment','commute_source','hours_assessment','verification_date','status_date','applied_date','interview_date')
                saved[uid]=dict(previous,**saved.get(uid,{}),**{k:item[k] for k in fields if k in item})
                backups=ROOT/'backups';backups.mkdir(exist_ok=True)
                if STATE.exists():
                    (backups/('dashboard_records-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json')).write_bytes(STATE.read_bytes())
                temp = STATE.with_suffix('.tmp')
                temp.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding='utf-8')
                os.replace(temp, STATE)
                inbox=read_json(ROOT/'job_scraper/candidate_inbox.json',{})
                for candidate in inbox.values():
                    if item.get('url') and canonical(candidate['url'])==canonical(item['url']):candidate['state']='saved'
                atomic_write(ROOT/'job_scraper/candidate_inbox.json',inbox)
            self.reply({'id': uid})
        except (ValueError, TypeError, OSError) as exc:
            self.reply({'error': str(exc)}, 400)

if __name__ == '__main__':
    print('Open http://127.0.0.1:8765 in your browser. Keep this window open.')
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()

