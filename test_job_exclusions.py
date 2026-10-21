import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from job_exclusions import is_removed, removed_jobs
from browser_import import import_page

class RemovalTests(unittest.TestCase):
    def test_same_job_on_other_website_and_url_variants(self):
        old={'id':'old','company':'Example A/S','role':'Student - Software Testing','url':'https://www.linkedin.com/jobs/view/123/?tracking=x','status':'removed'}
        self.assertTrue(is_removed({'url':'https://linkedin.com/jobs/view/student-software-testing-123'},[old]))
        self.assertTrue(is_removed({'company':'EXAMPLE A/S','role':'Student Software Testing','url':'https://dtu.jobteaser.com/en/job-offers/other'},[old]))
        self.assertFalse(is_removed({'company':'Example A/S','role':'Student Hardware Design','url':'https://linkedin.com/jobs/view/456'},[old]))
        self.assertFalse(is_removed({'company':'','role':''},[old]))

    def test_persistent_removal_blocks_browser_import_after_overlay_changes(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            root=Path(tmp);state=root/'job_scraper';state.mkdir()
            job={'id':'removed-1','company':'Example','role':'Student Software Testing','url':'https://linkedin.com/jobs/view/123','status':'removed'}
            (state/'removed_jobs.json').write_text(json.dumps({'removed-1':job}),encoding='utf-8')
            (state/'dashboard_records.json').write_text('{}',encoding='utf-8')
            self.assertTrue(is_removed(job,removed_jobs(root)))
            result=import_page(root,{'page_url':'https://linkedin.com/jobs/search/','jobs':[dict(job,url='https://www.linkedin.com/jobs/view/999')]})
            self.assertEqual(result['added'],0)
            self.assertEqual(json.loads((state/'candidate_inbox.json').read_text()),{})

if __name__=='__main__':unittest.main()
