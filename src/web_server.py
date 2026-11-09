from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import json, sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from simulator import MARSOranSimulator, POLICIES, deep_update

ROOT=Path(__file__).resolve().parents[1]; WEB=ROOT/'web'
SESSIONS={}

DEFAULT={"policy":"MARS","seed":17,"severity":0.2,"total_prbs":100,"risk_aversion":0.55,"aoi_limit":4.0}

def make_sim(params):
    overrides={"incident":{"initial_severity":float(params.get("severity",0.2))},"radio":{"total_prbs":int(params.get('total_prbs',100))},"controller":{"risk_aversion":float(params.get('risk_aversion',0.55))},"aoi":{"max_safety_aoi_s":float(params.get('aoi_limit',4.0))}}
    return MARSOranSimulator(policy=params.get("policy","MARS"),seed=int(params.get('seed',17)),duration=300,overrides=overrides)

def payload(sim):
    r=sim.result(); last=sim.state.trace[-1] if sim.state.trace else {}
    return {"result":r,"last":last,"t":sim.state.t,"events":sim.state.events[-10:],"tasks":sim.state.task_rows}

class H(BaseHTTPRequestHandler):
    def _send(self,obj,code=200,ctype='application/json'):
        b=obj if isinstance(obj,bytes) else (json.dumps(obj).encode('utf-8') if not isinstance(obj,str) else obj.encode())
        self.send_response(code); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        p=urlparse(self.path)
        if p.path=='/': return self._send((WEB/'index.html').read_bytes(),200,'text/html; charset=utf-8')
        if p.path=='/app.js': return self._send((WEB/'app.js').read_bytes(),200,'application/javascript')
        if p.path=='/style.css': return self._send((WEB/'style.css').read_bytes(),200,'text/css')
        if p.path=='/api/health': return self._send({'status':'ok','policies':POLICIES})
        return self._send({'error':'not found'},404)
    def do_POST(self):
        n=int(self.headers.get('Content-Length','0')); data=json.loads(self.rfile.read(n) or b'{}'); p=urlparse(self.path)
        sid=data.get('session','default')
        if p.path=='/api/reset':
            params={**DEFAULT,**data}; sim=make_sim(params); SESSIONS[sid]=sim; return self._send(payload(sim))
        if sid not in SESSIONS: SESSIONS[sid]=make_sim(DEFAULT)
        sim=SESSIONS[sid]
        if p.path=='/api/step':
            count=int(data.get('steps',1)); count=max(1,min(count,10));
            for _ in range(count):
                if sim.state.t<sim.duration: sim.step()
            return self._send(payload(sim))
        if p.path=='/api/run':
            while sim.state.t<sim.duration: sim.step()
            return self._send(payload(sim))
        return self._send({'error':'not found'},404)

if __name__=='__main__':
    print('MARS-O-RAN live dashboard: http://127.0.0.1:8765')
    ThreadingHTTPServer(('127.0.0.1',8765),H).serve_forever()
