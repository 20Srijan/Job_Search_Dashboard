"""Keep an auditable preference history from current user application choices.

Statuses are interest signals, never proof of eligibility or removal reasons.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from independent_search import read, write


def refresh(root, jobs):
    positive = ('applied', 'interview', 'offer', 'rejected')
    fields = ('id', 'company', 'role', 'category', 'status', 'status_date', 'url')
    project = lambda j: {k: j.get(k, '') for k in fields}
    result = {
        'updated_at': datetime.now(ZoneInfo('Europe/Paris')).isoformat(),
        'purpose': 'Evidence for future search and sorting; not candidate qualifications.',
        'rules': [
            'Use actual duties and verified skills, not employer name, category labels or AI in the title alone.',
            'Prioritise software testing/verification, engineering/electronics and hands-on AI/Python/data automation.',
            'Retain technical research, laboratory and teaching opportunities; applied IT/support roles show secondary interest.',
            'Rank generic business strategy, administration-heavy process support, content/design and warehouse duties lower; recent removals support caution, not a permanent domain ban.',
            'An application is a positive interest signal, not evidence that language, commute, hours or eligibility gaps are resolved.',
            'Rejected applications remain positive interest evidence; an employer rejection is not a user dislike.',
            'Preparing and saved jobs are weaker interest signals than an actual application.',
            'Block the exact removed listing and matching cross-posts. Do not infer a company-wide or profession-wide exclusion without an explicit reason.',
            'A removed testing/embedded role does not exclude all testing/embedded roles; removal reason may be unknown or a closed listing.',
            'Keep explicit constraints: student work, no required Danish, agreed actual calendar-month roster at most 90 hours, commute at most 90 minutes with a checked cycling route at most 25 km.',
            'Keep saved ordering by verified fit then upcoming deadline. Use learned preferences to assess relevance; never inflate qualifications or override constraints.'
        ],
        'applied_interest': [project(j) for j in jobs if j.get('status') in positive],
        'preparing_interest': [project(j) for j in jobs if j.get('status') == 'drafting'],
        'removed_listings': [dict(project(j), reason='Not inferred; consult explicit user instruction or record notes if established.') for j in jobs if j.get('status') == 'removed'],
    }
    write(root/'job_scraper/selection_preferences.json', result)
    # Keep removal memory after overlays or discovery records change.
    path = root/'job_scraper/removed_jobs.json'
    removed = read(path, {})
    removed.update({j['id']: j for j in jobs if j.get('status') == 'removed'})
    write(path, removed)
    return result
