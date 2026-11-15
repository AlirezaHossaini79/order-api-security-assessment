import argparse,json,urllib.request,urllib.error,os
p=argparse.ArgumentParser()
p.add_argument('--url',default='http://127.0.0.1:18080')
p.add_argument('--delay-ms',type=int,default=0)
p.add_argument('--business-fail',action='store_true')
p.add_argument('--release',default='v1')
p.add_argument('--token',default=os.environ.get('LAB_OPS_TOKEN','lab-ops'))
a=p.parse_args()
req=urllib.request.Request(a.url+'/lab/control',data=json.dumps({'delay_ms':a.delay_ms,'business_fail':a.business_fail,'release':a.release}).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+a.token})
try:
    print(urllib.request.urlopen(req,timeout=10).read().decode())
except urllib.error.HTTPError as error:
    raise SystemExit(str(error.code)+': '+error.read().decode())
