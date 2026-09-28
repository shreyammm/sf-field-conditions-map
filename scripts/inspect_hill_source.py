#!/usr/bin/env python3
import collections, json, urllib.request
URL='https://data.sf.gov/api/v3/views/rnbg-2qxw/query.geojson?accessType=DOWNLOAD'
req=urllib.request.Request(URL,headers={'User-Agent':'sf-field-conditions-map/1.0','Accept':'application/json, application/geo+json'})
with urllib.request.urlopen(req,timeout=180) as r:
    data=json.load(r)
features=data.get('features',[])
print('feature_count',len(features))
print('geometry_types',collections.Counter((f.get('geometry') or {}).get('type') for f in features))
for i,f in enumerate(features[:5]):
    print('feature',i,'properties',json.dumps(f.get('properties') or {},sort_keys=True))
keys=collections.Counter()
for f in features[:1000]:
    keys.update((f.get('properties') or {}).keys())
print('keys',keys)
for key in sorted(keys):
    vals=[]
    for f in features[:5000]:
        v=(f.get('properties') or {}).get(key)
        if v not in (None,''):
            vals.append(v)
        if len(vals)>=20: break
    print('sample',key,vals[:20])
