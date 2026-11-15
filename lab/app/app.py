import os, json, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections import defaultdict
import psycopg

DSN=os.environ['DATABASE_URL']
state={'delay_ms':0, 'business_fail':False, 'release':'v1'}
counts=defaultdict(int)
durations=[]
lock=threading.Lock()
def db(): return psycopg.connect(DSN, connect_timeout=3)
def init():
    for _ in range(40):
        try:
            with db() as c:
                c.execute('CREATE TABLE IF NOT EXISTS orders(id BIGSERIAL PRIMARY KEY, owner TEXT NOT NULL, item TEXT NOT NULL, request_key TEXT NOT NULL)')
                if c.execute('SELECT count(*) FROM orders').fetchone()[0]==0:
                    c.execute("INSERT INTO orders(owner,item,request_key) VALUES ('alice','seed-a','seed-a'),('bob','seed-b','seed-b')")
            return
        except psycopg.Error: time.sleep(1)
    raise RuntimeError('database unavailable at startup')

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(json.dumps({'event':'http','path':self.path,'detail':fmt%args}),flush=True)
    def send(self, status, value, typ='application/json'):
        data=(json.dumps(value) if typ=='application/json' else value).encode()
        self.send_response(status);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def body(self): return json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}')
    def do_GET(self): self.run_request()
    def do_POST(self): self.run_request()
    def run_request(self):
        start=time.monotonic(); status=500
        try: status=self.route()
        except (psycopg.Error, OSError) as e:
            self.send(503,{'error':'dependency unavailable'});status=503
        except Exception as e:
            self.send(400,{'error':type(e).__name__});status=400
        finally:
            with lock:
                # Raw paths are intentionally retained in this starter implementation.
                counts[(self.path,str(status))]+=1
                durations.append(time.monotonic()-start)
    def route(self):
        path=self.path.split('?')[0]
        if path=='/live': self.send(200,{'alive':True,'release':state['release']});return 200
        if path=='/ready':
            with db() as c: c.execute('SELECT 1')
            self.send(200,{'ready':True});return 200
        if path=='/lab/control' and self.command=='POST':
            body=self.body()
            with lock:
                for k in state:
                    if k in body: state[k]=body[k]
            self.send(200,state);return 200
        if path=='/debug/config':
            self.send(200,{'database_url':DSN,'mode':'synthetic-lab'});return 200
        if path=='/metrics':
            with lock:
                lines=['# TYPE lab_http_requests_total counter']
                for (p,s),n in counts.items():
                    lines.append('lab_http_requests_total{path='+json.dumps(p)+',status="'+s+'"} '+str(n))
                lines+=['# TYPE lab_http_request_duration_seconds summary',
                    'lab_http_request_duration_seconds_sum '+str(sum(durations)),
                    'lab_http_request_duration_seconds_count '+str(len(durations))]
            self.send(200,'\n'.join(lines)+'\n','text/plain');return 200
        actor={'lab-alice':'alice','lab-bob':'bob','lab-ops':'ops'}.get(self.headers.get('Authorization','').removeprefix('Bearer '))
        if not actor: self.send(401,{'error':'authentication required'});return 401
        if path=='/orders' and self.command=='POST':
            body=self.body()
            time.sleep(max(0,min(int(state['delay_ms']),10000))/1000)
            if state['business_fail']:
                self.send(200,{'ok':False,'error':'order rejected'});return 200
            with db() as c:
                row=c.execute('INSERT INTO orders(owner,item,request_key) VALUES (%s,%s,%s) RETURNING id',
                    (actor,body.get('item','demo'),self.headers.get('Idempotency-Key',''))).fetchone()
            self.send(201,{'ok':True,'id':row[0]});return 201
        if path.startswith('/orders/'):
            oid=int(path.rsplit('/',1)[1])
            with db() as c: row=c.execute('SELECT id,owner,item,request_key FROM orders WHERE id=%s',(oid,)).fetchone()
            if not row: self.send(404,{'error':'missing'});return 404
            self.send(200,dict(zip(['id','owner','item','request_key'],row)));return 200
        self.send(404,{'error':'missing'});return 404

if __name__=='__main__':
    init()
    ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
