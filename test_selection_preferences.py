import tempfile
import unittest
from pathlib import Path
from selection_preferences import refresh
from job_exclusions import removed_jobs


class SelectionTests(unittest.TestCase):
    def test_rejection_keeps_interest_and_removal_survives_later_overlay(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            root = Path(tmp)
            jobs = [
                {'id':'a','company':'Example','role':'Student Testing','status':'rejected'},
                {'id':'b','company':'Example','role':'Student Strategy','status':'removed'},
                {'id':'c','company':'Example','role':'Student Research','status':'drafting'},
            ]
            evidence = refresh(root, jobs)
            self.assertEqual([j['id'] for j in evidence['applied_interest']], ['a'])
            self.assertEqual([j['id'] for j in evidence['preparing_interest']], ['c'])
            self.assertEqual(evidence['removed_listings'][0]['id'], 'b')
            refresh(root, [])
            self.assertEqual([j['id'] for j in removed_jobs(root)], ['b'])


if __name__ == '__main__':
    unittest.main()
