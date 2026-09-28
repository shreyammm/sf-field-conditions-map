#!/usr/bin/env python3
import json, pathlib, urllib.request
URL='https://data.sf.gov/api/v3/views/rnbg-2qxw/query.geojson?accessType=DOWNLOAD'
out=pathlib.Path('contours.geojson')
req=urllib.request.Request(URL,headers={'User-Agent':'sf-field-conditions-map/1.0','Accept':'application/json, application/geo+json'})
with urllib.request.urlopen(req,timeout=180) as r:
    raw=r.read()
out.write_bytes(raw)
data=json.loads(raw)
features=data.get('features',[])
print('feature_count',len(features))
print('bytes',len(raw))
for i,f in enumerate(features[:5]):
    print('feature',i,'properties',json.dumps(f.get('properties') or {},sort_keys=True))
