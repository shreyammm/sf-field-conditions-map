#!/usr/bin/env python3
import json, urllib.parse, urllib.request, time
BASE='https://data.sf.gov/resource/wg3w-h783.json'
H={'User-Agent':'sf-field-conditions-map-debug/1.0','Accept':'application/json'}

def run(name, params):
    url=BASE+'?'+urllib.parse.urlencode(params)
    t=time.time()
    try:
        req=urllib.request.Request(url,headers=H)
        with urllib.request.urlopen(req,timeout=60) as r:
            rows=json.load(r)
        print(name,'OK',round(time.time()-t,2),'rows',len(rows),'first',rows[:3])
    except Exception as e:
        print(name,'ERR',round(time.time()-t,2),repr(e))

where="incident_datetime >= '2026-09-01T00:00:00.000' AND incident_datetime < '2026-09-28T00:00:00.000' AND latitude IS NOT NULL AND longitude IS NOT NULL"
run('raw',{'$select':'incident_id,incident_datetime,latitude,longitude','$where':where,'$limit':'5','$order':'incident_datetime ASC'})
run('count',{'$select':'count(distinct incident_id) as report_count','$where':where,'$limit':'1'})
run('all_group',{'$select':'intersection,police_district,analysis_neighborhood,latitude,longitude,count(distinct incident_id) as report_count','$where':where,'$group':'intersection,police_district,analysis_neighborhood,latitude,longitude','$order':'latitude ASC,longitude ASC,intersection ASC','$limit':'5'})
run('cat_group',{'$select':'incident_category,intersection,police_district,analysis_neighborhood,latitude,longitude,count(distinct incident_id) as report_count','$where':where,'$group':'incident_category,intersection,police_district,analysis_neighborhood,latitude,longitude','$order':'incident_category ASC,latitude ASC,longitude ASC,intersection ASC','$limit':'5'})
