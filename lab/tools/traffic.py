import argparse, concurrent.futures, json, time, urllib.request, urllib.error, uuid
p=argparse.ArgumentParser()
p.add_argument('--url',default='http://127.0.0.1:18080')
p.add_argument('--requests',type=int,default=100)
p.add_argument('--workers',type=int,default=5)
p.add_argument('--timeout',type=float,default=2)
p.add_argument('--key',default='')
a=p.parse_args()
def one(i):
    started=time.monotonic()
    req=urllib.request.Request(a.url+'/orders',data=b'{"item":"test"}',headers={
        'Content-Type':'application/json','Authorization':'Bearer lab-alice',
        'Idempotency-Key':a.key or str(uuid.uuid4())})
    try:
        with urllib.request.urlopen(req,timeout=a.timeout) as r:
            code=r.status;body=json.load(r); ok=code in (200,201) and body.get('ok') is True
    except urllib.error.HTTPError as e: code=e.code;ok=False
    except Exception: code=0;ok=False
    return {'index':i,'status':code,'business_ok':ok,'seconds':round(time.monotonic()-started,4)}
with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
    rows=list(pool.map(one,range(a.requests)))
lat=sorted(r['seconds'] for r in rows)
print(json.dumps({'requests':len(rows),'success':sum(r['business_ok'] for r in rows),
    'p95_seconds':lat[max(0,int(len(lat)*.95)-1)],'results':rows},indent=2))
