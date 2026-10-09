"""Create empty local records; never overwrite existing user data."""
from pathlib import Path
import json
def initialize(root):
    root=Path(root)
    for folder in ('job_scraper','documents','cv','cover_letters','outbox'):
        (root/folder).mkdir(parents=True,exist_ok=True)
    for name,value in {'seen_jobs.json':{'seen':{}},'dashboard_records.json':{},'candidate_inbox.json':{},'search_health.json':[]}.items():
        p=root/'job_scraper'/name
        if not p.exists():p.write_text(json.dumps(value),encoding='utf-8')
    profile=root/'PROFILE-AND-TIMELINE.md'
    if not profile.exists():profile.write_text('# Local search preferences\n\nEdit locally. Verify eligibility, workplace, commute, language and monthly hours before applying. No personal profile is distributed.\n',encoding='utf-8')
if __name__=='__main__':initialize(Path(__file__).resolve().parent)
