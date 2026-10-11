"""Import a user-invoked capture from the narrow-permission Chrome extension."""
import hashlib,json,re
from datetime import datetime,timedelta
from urllib.parse import urlparse
from independent_search import read,write,canonical,stamp,TZ,relevant

def site_for(url):
 parsed=urlparse(url)
 if parsed.scheme!='https':raise ValueError('HTTPS job page required')
 host=parsed.hostname or ''
 if host=='jobdanmark.dk':return 'Jobdanmark'
 if host=='thehub.io':return 'The Hub'
 if host=='dtu.jobteaser.com':return 'DTU JobTeaser'
 if host in ('www.linkedin.com','linkedin.com'):return 'LinkedIn Jobs'
 raise ValueError('Only DTU JobTeaser and LinkedIn Jobs captures are supported')

def import_page(root,payload):
 site=site_for(payload.get('page_url',''))
 incoming=payload.get('jobs')
 if not isinstance(incoming,list) or len(incoming)>100:raise ValueError('Up to 100 jobs per captured page')
 inboxpath=root/'job_scraper/candidate_inbox.json';inbox=read(inboxpath,{})
 records=list(read(root/'job_scraper/seen_jobs.json',{'seen':{}})['seen'].values())+list(read(root/'job_scraper/dashboard_records.json',{}).values())
 known={canonical(j.get('url','')) for j in records}
 for j in records:known.update(canonical(u) for u in j.get('source_urls',[]) if isinstance(u,str))
 identity=lambda j:re.sub(r'\W+','',j.get('company','').lower())+'|'+re.sub(r'\W+','',j.get('role','').lower())
 identities={identity(j) for j in records+list(inbox.values()) if j.get('company') and j.get('role')}
 added=0;unknown=0;ignored=0
 for raw in incoming:
  if not isinstance(raw,dict):raise ValueError('Invalid job record')
  url=raw.get('url','');title=raw.get('role','')
  if not isinstance(url,str) or not isinstance(title,str):raise ValueError('Invalid job link/title')
  if site_for(url)!=site:raise ValueError('Captured job belongs to another site')
  path=urlparse(url).path
  if site=='DTU JobTeaser' and not re.match(r'^/(en|da)/job-offers/[^/]+',path):ignored+=1;continue
  if site=='LinkedIn Jobs' and not re.match(r'^/jobs/view/\d+',path):ignored+=1;continue
  url=canonical(url);key=hashlib.sha256(url.encode()).hexdigest()[:20]
  if not relevant(title+' '+str(raw.get('description',''))) or url in known or key in inbox or raw.get('company') and identity(raw) in identities:ignored+=1;continue
  posted=raw.get('posted_date','')
  if not isinstance(posted,str):posted=''
  try:
   date=datetime.strptime(posted,'%Y-%m-%d').date();today=datetime.now(TZ).date()
   if date<today-timedelta(days=7) or date>today:ignored+=1;continue
  except ValueError:posted='';unknown+=1
  company=raw.get('company','');description=raw.get('description','')
  if not isinstance(company,str) or not isinstance(description,str):raise ValueError('Invalid job text')
  inbox[key]={'id':key,'url':url,'role':title[:300],'company':company[:300],'source':site,'location':'','posted_date':posted,'deadline':'','description':description[:2500],'state':'pending','discovered_at':stamp(),'why_fit':'Student AI/software/electronics keyword match from a page you opened in Chrome; fit not yet verified.','missing':('Publication date unverified; confirm freshness before saving. ' if not posted else '')+'Verify original posting, English eligibility, skills, workplace, commute and actual monthly roster. Current page only; other pages were not searched.'}
  added+=1
  if company:identities.add(identity(raw))
 write(inboxpath,inbox)
 healthpath=root/'job_scraper/search_health.json';health=read(healthpath,[]);item=next((x for x in health if x['site']==site),None)
 if item is None:item={'site':site};health.append(item)
 item.update(last_checked=stamp(),status='Chrome page captured · limited coverage',detail=f"User-invoked current page only: {len(incoming)} extracted cards, {added} new inbox candidates, {unknown} with unverified publication dates. No automatic pagination or full-site claim.")
 write(healthpath,health)
 with (root/'job_scraper/browser_capture_runs.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'at':stamp(),'site':site,'page_url':payload['page_url'],'extracted':len(incoming),'added':added,'unknown_publication':unknown,'ignored':ignored})+'\n')
 return {'added':added,'unknown_publication':unknown,'ignored':ignored}
