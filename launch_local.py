"""Run the dashboard in this launcher process; keep the window open."""
import json
import threading
import webbrowser
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parent
URL='http://127.0.0.1:8765'

def ready():
    try:
        # Local traffic must not be sent to a configured Internet proxy.
        with build_opener(ProxyHandler({})).open(URL+'/api/search',timeout=1) as response:
            return 'browser' in json.load(response)
    except Exception:
        return False

def launch():
    if ready():
        print('Dashboard is already running. Opening it.')
        webbrowser.open(URL)
        return
    from dashboard_server import Handler
    try:
        server=ThreadingHTTPServer(('127.0.0.1',8765),Handler)
    except OSError as exc:
        raise RuntimeError('Cannot start dashboard on port 8765: '+str(exc)) from exc
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    if not ready():
        server.shutdown()
        raise RuntimeError('Server started but its local connection check failed.')
    print('Dashboard is running at '+URL,flush=True)
    print('Keep this window open while using the dashboard. Close it to stop.',flush=True)
    webbrowser.open(URL)
    try:
        thread.join()
    except KeyboardInterrupt:
        server.shutdown()
    finally:
        server.server_close()

if __name__=='__main__':
    launch()
