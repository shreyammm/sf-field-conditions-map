#!/usr/bin/env python3
import json, urllib.parse, urllib.request, time
H={'User-Agent':'sf-field-conditions-map-debug/1.0','Accept':'application/json'}
params={'$select':'incident_id,incident_datetime,latitude,longitude','$where':"incident_datetime >= '2026-09-28T00:00:00.000' AND incident_datetime < '2026-09-29T00:00:00.000'",'$limit':'5','$order':'incident_datetime ASC'}
for host in ('https://data.sf.gov','https://data.sfgov.org'):
    url=host+'/resource/wg3w-h783.json?'+urllib.parse.urlencode(params)
    t=time.time()
    try:
        req=urllib.request.Request(url,headers=H)
        with urllib.request.urlopen(req,timeout=30) as r:
            rows=json.load(r)
        print(host,'OK',round(time.time()-t,2),'rows',len(rows),'first',rows[:2])
    except Exception as e:
        print(host,'ERR',round(time.time()-t,2),repr(e))
