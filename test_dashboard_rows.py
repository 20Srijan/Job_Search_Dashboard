"""Check record merging without starting browser/search services."""
import ast
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from job_exclusions import removed_jobs, is_removed


class DashboardRowsTests(unittest.TestCase):
    def test_tracker_matches_manual_record_without_duplicate_or_status_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'job_scraper').mkdir()
            state = root / 'job_scraper/dashboard_records.json'
            url = 'https://example.org/jobs/testing'
            state.write_text(json.dumps({'manual-job': {
                'company': 'Example', 'role': 'Student Tester', 'url': url,
                'status': 'applied', 'applied_date': '2026-11-01',
            }}), encoding='utf-8')
            with (root / 'job_search_tracker.csv').open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['company', 'role', 'source', 'status', 'cv_file'])
                writer.writeheader()
                writer.writerow(dict(company='Example', role='Student Tester', source=url,
                                     status='drafted', cv_file='cv/example.pdf'))
                # Same title/company with a different URL must remain a distinct record.
                writer.writerow(dict(company='Example', role='Student Tester',
                                     source='https://example.org/jobs/other', status='drafted'))
            tree = ast.parse(Path(__file__).with_name('dashboard_server.py').read_text(encoding='utf-8'))
            function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'rows')
            namespace = dict(ROOT=root, STATE=state, csv=csv, hashlib=hashlib,
                             removed_jobs=removed_jobs, is_removed=is_removed,
                             read_json=lambda p, default: json.loads(p.read_text(encoding='utf-8')) if p.exists() else default)
            exec(compile(ast.Module(body=[function], type_ignores=[]), 'dashboard_server.py', 'exec'), namespace)
            jobs = namespace['rows']()
            self.assertEqual(len(jobs), 2)
            merged = next(j for j in jobs if j['url'] == url)
            self.assertEqual(merged['id'], 'manual-job')
            self.assertEqual(merged['status'], 'applied')
            self.assertEqual(merged['applied_date'], '2026-11-01')
            self.assertEqual(merged['cv_file'], 'cv/example.pdf')


if __name__ == '__main__':
    unittest.main()
