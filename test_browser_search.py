"""Fixture-only browser/search tests. Never visits a live job website."""
import json
import os
from pathlib import Path
import tempfile
import unittest
import sys
from datetime import datetime, timedelta
from unittest.mock import patch
from browser_search import BrowserService, EXTRACT, blocked_reason, job_link, parse_posting
from independent_search import ROOT, TZ, read, write
from browser_import import import_page

class BrowserTests(unittest.TestCase):
    def posting(self, **changes):
        value={'@type':'JobPosting','title':'Student FPGA Engineer','description':'Student hardware testing role',
               'datePosted':datetime.now(TZ).date().isoformat(),'hiringOrganization':{'name':'Fixture'},
               'url':'https://dtu.jobteaser.com/en/job-offers/fixture'}
        value.update(changes)
        return {'url':value['url'],'scripts':[json.dumps(value)],'headings':[value['title']],'text':value['description']}

    def test_original_dates_and_eligibility(self):
        good=self.posting();record,reason=parse_posting('DTU JobTeaser',good['url'],good)
        self.assertEqual(record['company'],'Fixture');self.assertEqual(reason,'')
        for changes,expected in [({'datePosted':'','dateModified':datetime.now(TZ).date().isoformat()},'unverified'),
                ({'datePosted':(datetime.now(TZ).date()-timedelta(days=8)).isoformat()},'window'),
                ({'description':'Student hardware testing. Fluent in Danish required.'},'Danish'),
                ({'title':'FPGA Student Internship'},'Internship')]:
            snapshot=self.posting(**changes);record,reason=parse_posting('DTU JobTeaser',snapshot['url'],snapshot)
            self.assertIsNone(record);self.assertIn(expected,reason)

    def test_login_and_strict_job_urls(self):
        self.assertIn('Sign in',blocked_reason('DTU JobTeaser',{'url':'https://dtu.jobteaser.com/en/login','title':'Login','text':'','links':[]}))
        self.assertFalse(job_link('DTU JobTeaser','https://dtu.jobteaser.com.evil.example/en/job-offers/id'))
        self.assertFalse(job_link('LinkedIn Jobs','https://www.linkedin.com/jobs/search/'))

    def test_removed_identity_is_not_resurrected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root=Path(folder);write(root/'job_scraper/dashboard_records.json',{'removed':{'company':'Fixture','role':'Student FPGA Engineer','status':'removed','url':'https://www.linkedin.com/jobs/view/123','notes':'Keep me'}})
            payload={'page_url':'https://dtu.jobteaser.com/en/job-offers','jobs':[{'url':'https://dtu.jobteaser.com/en/job-offers/fixture','company':'Fixture','role':'Student FPGA Engineer','posted_date':datetime.now(TZ).date().isoformat()}]}
            self.assertEqual(import_page(root,payload)['added'],0)
            self.assertEqual(read(root/'job_scraper/dashboard_records.json',{})['removed']['notes'],'Keep me')

    def test_browser_requires_manual_command(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            service=BrowserService(folder)
            self.assertIsNone(service.thread);self.assertFalse(service.snapshot()['running'])
            with self.assertRaises(ValueError):service.submit('search','Unknown')
            service.submit('stop');self.assertTrue(service.stop_requested.is_set())

    def test_search_paginates_and_keeps_candidates_unreviewed(self):
        # Controlled page objects exercise the actual search loop without external requests.
        today=datetime.now(TZ).date().isoformat()
        class Control:
            def __init__(self,page,exists=True):self.page=page;self.exists=exists
            @property
            def first(self):return self
            def count(self):return int(self.exists)
            def is_visible(self):return self.exists
            def is_enabled(self):return self.exists
            def click(self):self.page.number+=1
            def wait_for(self,**kwargs):pass
        class FixturePage:
            def __init__(self,detail=False):self.number=1;self.detail=detail;self.url=''
            def goto(self,url,**kwargs):self.url=url
            def bring_to_front(self):pass
            def wait_for_timeout(self,ms):pass
            def close(self):pass
            def locator(self,selector):return Control(self,selector!='a[rel="next"]')
            def get_by_role(self,*args,**kwargs):return Control(self,self.number==1)
            def evaluate(self,script):
                if self.detail:
                    j={'@type':'JobPosting','title':'Student FPGA Engineer '+self.url[-1],'description':'Hardware testing student role','datePosted':today,'hiringOrganization':{'name':'Fixture'},'url':self.url}
                    return {'url':self.url,'title':j['title'],'headings':[j['title']],'text':j['description'],'scripts':[json.dumps(j)],'links':[]}
                return {'url':'https://dtu.jobteaser.com/en/job-offers','title':'Jobs','text':'Jobs','scripts':[], 'links':[{'url':'https://dtu.jobteaser.com/en/job-offers/job'+str(self.number),'text':'Student FPGA Engineer','card':'Student hardware'}]}
        class FixtureContext:
            def new_page(self):return FixturePage(True)
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root=Path(folder);service=BrowserService(root);service.context=FixtureContext();page=FixturePage()
            with patch.object(service,'site_page',return_value=page):service.search('DTU JobTeaser')
            state=service.snapshot();self.assertEqual(state['pages_read'],2);self.assertEqual(state['details_checked'],2)
            self.assertEqual(state['added'],2);self.assertEqual(state['status'],'partial')
            inbox=read(root/'job_scraper/candidate_inbox.json',{})
            self.assertTrue(all(j['state']=='pending' for j in inbox.values()))
            self.assertFalse((root/'job_scraper/dashboard_records.json').exists())

    @unittest.skipUnless('--browser' in sys.argv, 'Live Chromium check is opt-in; run with --browser outside the restricted agent shell')
    def test_chromium_dom_and_profile_survive_restart(self):
        # Local fixture only; exercises real Chromium and actual persisted browser storage.
        from playwright.sync_api import sync_playwright
        os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'.runtime/browsers')
        with tempfile.TemporaryDirectory(dir=ROOT) as folder, sync_playwright() as pw:
            profile=Path(folder)/'profile'
            for iteration in range(2):
                context=pw.chromium.launch_persistent_context(str(profile),headless=True,channel='chromium',chromium_sandbox=True)
                page=context.new_page()
                context.route('https://fixture.test/**',lambda route:route.fulfill(content_type='text/html',body='<main><h1>Student FPGA Engineer</h1><a href="https://dtu.jobteaser.com/en/job-offers/fixture">Student FPGA Engineer</a></main>'))
                page.goto('https://fixture.test/')
                if iteration==0:page.evaluate("localStorage.setItem('fixture-session','retained')")
                else:self.assertEqual(page.evaluate("localStorage.getItem('fixture-session')"),'retained')
                snapshot=page.evaluate(EXTRACT)
                self.assertEqual(snapshot['headings'],['Student FPGA Engineer'])
                self.assertTrue(job_link('DTU JobTeaser',snapshot['links'][0]['url']))
                context.close()

if __name__=='__main__':
    if '--browser' in sys.argv:sys.argv.remove('--browser')
    unittest.main()
