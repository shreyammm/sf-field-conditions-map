#!/usr/bin/env python3
import collections, json, urllib.parse, urllib.request
BASE='https://data.sf.gov/resource/rnbg-2qxw.geojson'
url=BASE+'?'+urllib.parse.urlencode({'$limit':5})
req=urllib.request.Request(url,headers={'User-Agent':'sf-field-conditions-map/1.0','Accept':'application/json, application/geo+json'})
with urllib.request.urlopen(req,timeout=60) as r:
    data=json.load(r)
features=data.get('features',[])
print('sample_url',url)
print('sample_feature_count',len(features))
print('geometry_types',collections.Counter((f.get('geometry') or {}).get('type') for f in features))
for i,f in enumerate(features):
    print('feature',i,'properties',json.dumps(f.get('properties') or {},sort_keys=True))
    print('geometry_head',json.dumps(f.get('geometry'))[:240])
