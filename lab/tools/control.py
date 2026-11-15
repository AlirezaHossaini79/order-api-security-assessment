import argparse,json,urllib.request
p=argparse.ArgumentParser()
p.add_argument('--url',default='http://127.0.0.1:18080')
p.add_argument('--delay-ms',type=int,default=0)
p.add_argument('--business-fail',action='store_true')
p.add_argument('--release',default='v1')
a=p.parse_args()
req=urllib.request.Request(a.url+'/lab/control',data=json.dumps({'delay_ms':a.delay_ms,'business_fail':a.business_fail,'release':a.release}).encode(),headers={'Content-Type':'application/json'})
print(urllib.request.urlopen(req).read().decode())
