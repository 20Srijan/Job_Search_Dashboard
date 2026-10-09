"""One-time project-local installation; never alters the global browser."""
import os
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parent
runtime=root/'.runtime';runtime.mkdir(exist_ok=True)
temporary=runtime/'tmp';temporary.mkdir(exist_ok=True)
env=dict(os.environ,TEMP=str(temporary),TMP=str(temporary),PLAYWRIGHT_BROWSERS_PATH=str(runtime/'browsers'))
python=root/'.venv/Scripts/python.exe' if os.name=='nt' else root/'.venv/bin/python'
if not python.exists():
    subprocess.run([sys.executable,'-m','venv','--without-pip',str(root/'.venv')],check=True,env=env)
subprocess.run([sys.executable,'-m','pip','--python',str(python),'install','--no-cache-dir','-r',str(root/'requirements-independent.txt')],check=True,env=env)
subprocess.run([str(python),'-m','playwright','install','chromium'],check=True,env=env)
print('Setup complete. Open OPEN-INDEPENDENT-DASHBOARD.cmd.')
