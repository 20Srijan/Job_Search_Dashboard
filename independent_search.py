"""Subscription-free public-site discovery. Findings require human verification."""
import argparse,html,json,os,re,threading,time,hashlib,ipaddress,socket
from datetime import datetime,timedelta
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse,urljoin,urlencode
from urllib.request import Request,urlopen,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.robotparser import RobotFileParser
import math
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parent
TZ=ZoneInfo('Europe/Paris')
UA='SrijanJobDashboard/1.0'
GUARD=threading.Lock()

def read(path,default):
 return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def write(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(tmp,path)

def stamp():return datetime.now(TZ).isoformat()
def canonical(url):
 p=urlparse(url);return p._replace(query='',fragment='').geturl().rstrip('/')

class Page(HTMLParser):
 def __init__(self,text):
  super().__init__();self.links=[];self.scripts=[];self.href=None;self.label=[];self.ld=False;self.buf=[];self.feed(text)
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='a':self.href=a.get('href');self.label=[]
  if tag=='script':self.ld=a.get('type','').lower()=='application/ld+json';self.buf=[]
 def handle_data(self,data):
  if self.href is not None:self.label.append(data)
  if self.ld:self.buf.append(data)
 def handle_endtag(self,tag):
  if tag=='a' and self.href is not None:self.links.append((self.href,' '.join(self.label).strip()));self.href=None
  if tag=='script' and self.ld:
   try:self.scripts.append(json.loads(''.join(self.buf)))
   except ValueError:pass
   self.ld=False

def jobs_from_ld(value):
 if isinstance(value,list):
  for x in value:yield from jobs_from_ld(x)
 elif isinstance(value,dict):
  t=value.get('@type',[])
  if t=='JobPosting' or isinstance(t,list) and 'JobPosting' in t:yield value
  for k in ('@graph','itemListElement','item'):
   if k in value:yield from jobs_from_ld(value[k])

def plain(text):return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]+>',' ',str(text)))).strip()
def relevant(text):
 if re.search(r"\bui[ /-]*ux\b|\b(?:ui|ux)\s+(?:developer|designer|design)|user.experience.design|user.interface.design",text,re.I):return False
 if re.search(r'\bph\.?d\b|postdoc|professor|thesis|speciale',text,re.I):return False
 return bool(re.search(r'student|studentermedhj|studiejob|working.student',text,re.I)) and bool(re.search(r'fpga|asic|\brtl\b|electronic|elektronik|embedded|hardware|test|\bqa\b|software|python|iot|automation|compliance|laborator|validation|machine.learning|data.anal|artificial.intelligence|\bai\b|sensor|it.support',text,re.I))

def search_response(text):
 marker='var Stash = '
 if marker not in text:raise RuntimeError('Jobindex result format changed; manual review needed')
 value=json.JSONDecoder().raw_decode(text.split(marker,1)[1])[0]
 def find(node):
  if isinstance(node,dict):
   if isinstance(node.get('searchResponse'),dict) and isinstance(node['searchResponse'].get('results'),list):return node['searchResponse']
   for v in node.values():
    found=find(v)
    if found is not None:return found
  if isinstance(node,list):
   for v in node:
    found=find(v)
    if found is not None:return found
  return None
 result=find(value)
 if result is None:raise RuntimeError('Jobindex result payload missing')
 return result

class PublicClient:
 def __init__(self):self.robots={};self.last={}
 def raw(self,url):
  def validate(target):
   parsed=urlparse(target)
   if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise RuntimeError('Only public HTTPS destinations allowed')
   for entry in socket.getaddrinfo(parsed.hostname,parsed.port or 443,type=socket.SOCK_STREAM):
    if not ipaddress.ip_address(entry[4][0]).is_global:raise RuntimeError('Private/local network destinations are not job sources')
  class Redirect(HTTPRedirectHandler):
   def redirect_request(self,req,fp,code,msg,headers,newurl):
    validate(newurl);return super().redirect_request(req,fp,code,msg,headers,newurl)
  validate(url)
  with build_opener(Redirect()).open(Request(url,headers={'User-Agent':UA}),timeout=15) as r:
   if urlparse(r.url).scheme!='https':raise RuntimeError('Unexpected non-HTTPS redirect')
   body=r.read(4_000_001)
   if len(body)>4_000_000:raise RuntimeError('Page exceeds size limit')
   return body.decode(r.headers.get_content_charset() or 'utf-8',errors='replace')
 def get(self,url):
  p=urlparse(url)
  if p.scheme!='https' or not p.hostname:raise RuntimeError('Only HTTPS public sources supported')
  base='https://'+p.netloc
  if base not in self.robots:
   robot=RobotFileParser()
   try:robot.parse(self.raw(base+'/robots.txt').splitlines())
   except HTTPError as e:
    if e.code==404:robot.parse([])
    else:raise RuntimeError('Cannot verify site access rules: HTTP '+str(e.code))
   self.robots[base]=robot
  robot=self.robots[base]
  if not robot.can_fetch(UA,url):raise RuntimeError('Site access rules disallow automated fetching; open manually')
  pause=max(1,robot.crawl_delay(UA) or 0)
  time.sleep(max(0,pause-(time.monotonic()-self.last.get(base,0))))
  self.last[base]=time.monotonic();return self.raw(url)

def sources(group):
 weekday=[('DTU JobTeaser','https://dtu.jobteaser.com/en/job-offers',r'/job-offers/.+'),('LinkedIn Jobs','https://www.linkedin.com/jobs/search/?'+urlencode({'keywords':'student AI Python software electronics testing','location':'Copenhagen, Denmark','f_TPR':'r604800','sortBy':'DD'}),r'/jobs/view/'),('Jobindex','https://www.jobindex.dk/jobsoegning?q=student&jobage=7&sort=date',r'/jobannonce/'),('StuderendeOnline','https://studerendeonline.dk/job/?cvtype=4&amt=2&amt=3&oprettet='+datetime.now(TZ).strftime('%d.%m.%Y'),r'/job/\d+/')]
 twice=[('Jobdanmark','https://jobdanmark.dk/jobsoeger/find-job',r'/job/'),('Jobbank','https://jobbank.dk/job/?cvtype=4&amt=2&amt=3',r'/job/\d+/'),('Workindenmark','https://workindenmark.jobnet.dk/find-job',r'/job'),('The Hub','https://thehub.io/jobs?countryCode=DK&search=student',r'/jobs/[a-f0-9]{24}'),('Demant/Oticon','https://careers.demant.com/',r'/job/'),('GN','https://www.gn.com/Working-with-us',r'/job'),('Presto Engineering','https://www.presto-eng.com/career-page',r'/job|career'),('Napatech','https://www.napatech.com/careers/open-positions/',r'/job|position'),('Trackman','https://careers.trackman.com/',r'/o/'),('WSA/Widex','https://careersemea.wsa.com/jobs',r'/jobs/'),('Ramboll','https://www.ramboll.com/careers/open-jobs',r'/career|/job|/careers/')]
 return weekday if group=='weekday' else twice if group=='twice' else weekday+twice

def discover(client,site,url,pattern,days):
 if site=='DTU JobTeaser':return [],{'status':'Sign-in adapter needed','detail':'Open DTU Career Hub in Chrome. The public runner does not reuse browser cookies or claim signed-in coverage.'}
 raw=client.get(url);page=Page(raw);found=[];links=[];indexed=[];pages=1
 if site in ('Jobbank','StuderendeOnline'):
  feedurl='https://'+urlparse(url).hostname+'/job/rss?cvtype=4&amt=2&amt=3'
  feed=ET.fromstring(client.get(feedurl))
  for item in feed.findall('.//item'):
   label=item.findtext('title','')+' '+plain(item.findtext('description',''))
   target=item.findtext('link','')
   if relevant(label) and urlparse(target).scheme=='https':links.append(target)
 if site=='Jobindex':
  response=search_response(raw);items=list(response['results']);total=int(response.get('hitcount',len(items)))
  for n in range(2,min(20,math.ceil(total/20))+1):
   more=search_response(client.get(url+'&page='+str(n)));items.extend(more['results']);pages=n
  for card in items:
   if card.get('tid'):
    indexed.append({'@type':'JobPosting','title':card.get('headline',''),'description':card.get('abstract',''),'datePosted':card.get('firstdate',''),'validThrough':'' if card.get('apply_deadline_asap') else card.get('apply_deadline') or '','url':'https://www.jobindex.dk/jobannonce/'+card['tid'],'hiringOrganization':{'name':(card.get('company') or {}).get('name') or card.get('companytext','')},'jobLocation':{'address':{'addressLocality':card.get('area','')}}})
 for href,label in page.links:
  target=urljoin(url,href)
  if re.search(pattern,target) and relevant(label) and canonical(target) not in [canonical(x) for x in links]:links.append(target)
 structured=list(jobs_from_ld(page.scripts))+indexed
 errors=[]
 for target in links[:15]:
  try:
   detail=Page(client.get(target));structured.extend(dict(j, url=j.get('url') or target) for j in jobs_from_ld(detail.scripts))
  except Exception as e:errors.append(str(e))
 cutoff=(datetime.now(TZ)-timedelta(days=days)).date()
 for j in structured:
  title=plain(j.get('title',''));desc=plain(j.get('description',''))
  if not relevant(title+' '+desc):continue
  if re.search(r'\bph\.?d\b|postdoc|professor|thesis|speciale|internship|praktik',title,re.I):continue
  loc=j.get('jobLocation') or {}
  if isinstance(loc,list):loc=loc[0] if loc else {}
  address=loc.get('address') or {} if isinstance(loc,dict) else {}
  city=plain(address.get('addressLocality','')) if isinstance(address,dict) else ''
  if re.search(r'aalborg|aarhus|odense|esbjerg|sønderborg|sonderborg|herning|kolding|vejle',city,re.I):continue
  date=str(j.get('datePosted',''))[:10]
  try:published=datetime.strptime(date,'%Y-%m-%d').date()
  except ValueError:continue
  if published<cutoff or published>datetime.now(TZ).date():continue
  target=j.get('url')
  if not isinstance(target,str) or urlparse(target).scheme!='https':continue
  employer=j.get('hiringOrganization') or {};loc=j.get('jobLocation') or {}
  if isinstance(loc,list):loc=loc[0] if loc else {}
  found.append({'id':hashlib.sha256(canonical(target).encode()).hexdigest()[:20],'url':target,'role':title,'company':employer.get('name','') if isinstance(employer,dict) else str(employer),'location':plain((loc.get('address') or {}).get('addressLocality','')) if isinstance(loc,dict) and isinstance(loc.get('address'),dict) else '', 'posted_date':date,'deadline':str(j.get('validThrough',''))[:10],'description':desc[:15000],'source':site,'discovered_at':stamp(),'state':'pending','why_fit':'Keyword match to student AI/Python, software, automation/testing and electronics priorities. This is a rule-based suggestion, not a confirmed assessment.','missing':'Verify language, exact workplace, cycling distance/time, public transport, student eligibility, mandatory skills and actual monthly roster before saving.'})
 status='Checked · limited public coverage' if structured else 'Browser/manual review needed'
 return found,{'status':status,'detail':f'{pages} public index pages scanned; {len(indexed)} result cards parsed; {len(links[:15])} relevant detail links attempted; {len(found)} fresh candidates. Portal-card candidates require original-posting verification. No complete inventory claimed. '+('; '.join(errors[:2]) if errors else '')}

class Runner:
 def __init__(self):
  self.state=read(ROOT/'job_scraper/local_search_state.json',{'running':False,'message':'Ready'})
  if self.state.get('running'):self.state['message']='Previous search was interrupted. You can run it again.'
  self.state['running']=False
 def start(self,group='all',days=7):
  self.stop_requested=False
  available={site for site,_,_ in sources('all')}
  if group not in ('all','weekday','twice') and group not in available:raise ValueError('Unknown website')
  with GUARD:
   if self.state.get('running'):raise ValueError('A search is already running')
   self.state={'running':True,'started_at':stamp(),'message':'Starting public-site search','group':group,'days':days,'added':0,'sites':[]}
   write(ROOT/'job_scraper/local_search_state.json',self.state)
  threading.Thread(target=self.run,args=(group,days),daemon=True).start()
 def run(self,group,days):
  client=PublicClient()
  try:
   selected=sources(group) if group in ('all','weekday','twice') else [s for s in sources('all') if s[0]==group]
   if group=='all':selected=[s for s in selected if s[0] not in ('DTU JobTeaser','LinkedIn Jobs','Jobdanmark','The Hub')]
   for site,url,pattern in selected:
    if self.stop_requested:break
    self.state['message']='Checking '+site;write(ROOT/'job_scraper/local_search_state.json',self.state)
    try:found,result=discover(client,site,url,pattern,days)
    except Exception as e:found=[];result={'status':'Blocked / failed','detail':str(e)}
    with GUARD:
     inbox=read(ROOT/'job_scraper/candidate_inbox.json',{})
     seen=read(ROOT/'job_scraper/seen_jobs.json',{'seen':{}})['seen']
     overlays=read(ROOT/'job_scraper/dashboard_records.json',{})
     known={canonical(v.get('url',k)) for k,v in seen.items()}|{canonical(v.get('url','')) for v in overlays.values()}
     for value in seen.values():known.update(canonical(u) for u in value.get('source_urls',[]) if isinstance(u,str))
     identity=lambda j:re.sub(r'\W+','',j.get('company','').lower())+'|'+re.sub(r'\W+','',j.get('role','').lower())
     identities={identity(j) for j in list(seen.values())+list(overlays.values())+list(inbox.values()) if j.get('company') and j.get('role')}
     for j in found:
      if canonical(j['url']) not in known and j['id'] not in inbox and identity(j) not in identities:
       inbox[j['id']]=j;self.state['added']+=1;identities.add(identity(j))
     write(ROOT/'job_scraper/candidate_inbox.json',inbox)
     health=read(ROOT/'job_scraper/search_health.json',[]);item=next((x for x in health if x['site']==site),None)
     if item is None:item={'site':site};health.append(item)
     item.update(last_checked=stamp(),**result);write(ROOT/'job_scraper/search_health.json',health)
    self.state['sites'].append(dict(site=site,**result));write(ROOT/'job_scraper/local_search_state.json',self.state)
   self.state.update(running=False,finished_at=stamp(),message=f"Search finished: {self.state['added']} new candidates. Review site limitations below.")
  except Exception as e:self.state.update(running=False,finished_at=stamp(),message='Search stopped: '+str(e))
  write(ROOT/'job_scraper/local_search_state.json',self.state)
  with (ROOT/'job_scraper/local_search_runs.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(self.state,ensure_ascii=False)+'\n')

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--group',choices=['all','weekday','twice'],default='all');args=ap.parse_args()
 runner=Runner();runner.start(args.group)
 while runner.state['running']:time.sleep(.5)
 print(json.dumps(runner.state,ensure_ascii=False,indent=2))
