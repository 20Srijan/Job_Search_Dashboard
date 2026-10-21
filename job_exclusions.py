"""Persistent user removals shared by dashboard and discovery readers."""
import json
import re
from urllib.parse import urlsplit


def identity(job):
    return tuple(re.sub(r'\W+', '', str(job.get(k, '')).casefold())
                 for k in ('company', 'role'))


def links(job):
    values = [job.get('url', ''), *job.get('source_urls', [])]
    result = set()
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        p = urlsplit(value)
        host = (p.hostname or '').lower().removeprefix('www.')
        path = p.path.rstrip('/')
        if host == 'linkedin.com':
            match = re.search(r'/jobs/view/(?:.*-)?(\d+)$', path)
            if match:
                path = '/jobs/view/' + match[1]
        result.add(host + path)
    return result


def removed_jobs(root):
    records = []
    for name in ('dashboard_records.json', 'removed_jobs.json'):
        path = root / 'job_scraper' / name
        if path.exists():
            records.extend(json.loads(path.read_text(encoding='utf-8')).values())
    return [j for j in records if j.get('status') == 'removed']


def is_removed(job, removed):
    key = identity(job)
    urls = links(job)
    return any((job.get('id') and job.get('id') == old.get('id'))
               or bool(urls & links(old))
               or (all(key) and key == identity(old)) for old in removed)
