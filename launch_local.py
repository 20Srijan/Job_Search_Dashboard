"""Start the local dashboard and ask its worker to open dedicated Chromium."""
import os,subprocess,sys,time,json
from pathlib import Path
from urllib.request import urlopen,Request
ROOT=Path(__file__).resolve().parent
URL='http://127.0.0.1:8765'
def ready():
 try:
  with urlopen(URL+'/api/search',timeout=2) as r:return 'browser' in json.load(r)
 except Exception:return False
def launch():
 from initialize_data import initialize
 initialize(ROOT)
 if not ready():
  log=(ROOT/'job_scraper/local_server.log').open('a',encoding='utf-8')
  subprocess.Popen([sys.executable,str(ROOT/'dashboard_server.py')],cwd=ROOT,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
  for _ in range(40):
   if ready():break
   time.sleep(.25)
  else:raise RuntimeError('Dashboard failed to start. See job_scraper/local_server.log.')
 with urlopen(URL+'/api/data',timeout=3) as response:token=json.load(response)['token']
 request=Request(URL+'/api/browser',data=json.dumps({'action':'open'}).encode(),headers={'Content-Type':'application/json','X-Dashboard-Token':token})
 with urlopen(request,timeout=5) as response:json.load(response)
 for _ in range(120):
  with urlopen(URL+'/api/search',timeout=3) as response:state=json.load(response)['browser']
  if not state.get('running'):
   if state.get('status')=='failed':raise RuntimeError(state['message'])
   return
  time.sleep(.25)
 raise RuntimeError('Browser is taking longer to open. Check http://127.0.0.1:8765.')
if __name__=='__main__':launch()
