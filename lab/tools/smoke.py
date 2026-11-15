import argparse, json, time, urllib.request
parser=argparse.ArgumentParser()
parser.add_argument('--url',default='http://127.0.0.1:18080')
base=parser.parse_args().url.rstrip('/')
for attempt in range(60):
    try:
        with urllib.request.urlopen(base+'/ready',timeout=2) as r:
            if r.status==200:break
    except Exception:time.sleep(1)
else:raise SystemExit('FAIL: API not ready within startup window')
for path in ['/live','/ready']:
    with urllib.request.urlopen(base+path,timeout=5) as r: assert r.status==200
req=urllib.request.Request(base+'/orders',data=b'{"item":"smoke"}',headers={'Authorization':'Bearer lab-alice','Content-Type':'application/json','Idempotency-Key':'smoke'})
with urllib.request.urlopen(req,timeout=5) as r:
    body=json.load(r);assert body['ok'];oid=body['id']
with urllib.request.urlopen(urllib.request.Request(base+'/orders/'+str(oid),headers={'Authorization':'Bearer lab-alice'}),timeout=5) as r:
    assert json.load(r)['item']=='smoke'
print('PASS: live, ready, create, read')
