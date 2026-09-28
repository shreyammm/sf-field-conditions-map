#!/usr/bin/env python3
import collections, json, urllib.request

URL='https://data.sf.gov/api/v3/views/bpc9-7sus/query.geojson?accessType=DOWNLOAD'
req=urllib.request.Request(URL,headers={'User-Agent':'sf-field-conditions-map/1.0','Accept':'application/geo+json,application/json'})
with urllib.request.urlopen(req,timeout=180) as r:
    fc=json.load(r)
fs=fc.get('features',[])
print('SURFACE_AUDIT feature_count',len(fs))
print('SURFACE_AUDIT geometry_types',dict(collections.Counter((f.get('geometry') or {}).get('type') or '(none)' for f in fs)))
keys=collections.Counter()
for f in fs:
    keys.update((f.get('properties') or {}).keys())
print('SURFACE_AUDIT property_keys',sorted(keys))
for field in ['status','permit_type','source','permit_source','data_source','permit_status']:
    c=collections.Counter(str((f.get('properties') or {}).get(field) or '(blank)').strip() for f in fs)
    if len(c)>1 or '(blank)' not in c:
        print('SURFACE_AUDIT',field,c.most_common(40))
for fld in ['permit_start_date','permit_end_date','start_date','end_date','approved_date','data_as_of']:
    vals=sorted(str((f.get('properties') or {}).get(fld)) for f in fs if (f.get('properties') or {}).get(fld) not in (None,''))
    if vals: print('SURFACE_AUDIT range',fld,vals[0],vals[-1],len(vals))
for i,f in enumerate(fs[:12]):
    p=f.get('properties') or {}
    sample={k:p.get(k) for k in ['permit_number','unique_identifier','cnn','streetname','cross_street_1','cross_street_2','permit_type','permit_purpose','status','approved_date','permit_start_date','permit_end_date','analysis_neighborhood','data_as_of'] if k in p}
    print('SURFACE_AUDIT sample',i,sample)
