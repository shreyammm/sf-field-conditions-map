#!/usr/bin/env python3
import json, urllib.request, datetime as dt
URL='https://data.sfgov.org/api/v3/views/wg3w-h783/query.json'
H={'User-Agent':'sf-field-conditions-map-debug/1.0','Accept':'application/json','Content-Type':'application/json'}

def q(query,page_size=20):
    body=json.dumps({'query':query,'page':{'pageNumber':1,'pageSize':page_size},'includeSynthetic':False}).encode()
    req=urllib.request.Request(URL,data=body,headers=H,method='POST')
    with urllib.request.urlopen(req,timeout=120) as r: obj=json.load(r)
    if isinstance(obj,list): return obj
    for k in ('data','results','rows'):
        if isinstance(obj,dict) and isinstance(obj.get(k),list): return obj[k]
    print('RAW',type(obj),obj if isinstance(obj,dict) else str(obj)[:1000]); return []

end=dt.date(2026,9,28)
for days in (1,7,30):
    start=end-dt.timedelta(days=days-1)
    a=start.isoformat()+'T00:00:00.000'; b=(end+dt.timedelta(days=1)).isoformat()+'T00:00:00.000'
    where=f"`incident_datetime` >= '{a}' AND `incident_datetime` < '{b}' AND `latitude` IS NOT NULL AND `longitude` IS NOT NULL"
    queries={
      'raw':f"SELECT `incident_id`,`incident_datetime`,`latitude`,`longitude` WHERE {where} ORDER BY `incident_datetime` ASC LIMIT 20",
      'all_group':f"SELECT `intersection`,`police_district`,`analysis_neighborhood`,`latitude`,`longitude`,count(distinct `incident_id`) AS report_count WHERE {where} GROUP BY `intersection`,`police_district`,`analysis_neighborhood`,`latitude`,`longitude` ORDER BY `latitude` ASC,`longitude` ASC LIMIT 20",
      'city_count':f"SELECT count(distinct `incident_id`) AS report_count WHERE {where} LIMIT 1",
      'group_count':f"SELECT count(*) AS n FROM (SELECT `intersection`,`police_district`,`analysis_neighborhood`,`latitude`,`longitude` WHERE {where} GROUP BY `intersection`,`police_district`,`analysis_neighborhood`,`latitude`,`longitude`) LIMIT 1",
    }
    print('\nDAYS',days,a,b)
    for name,query in queries.items():
        try:
            rows=q(query,20)
            print(name,'LEN',len(rows),'FIRST',rows[:2])
        except Exception as e:
            print(name,'ERR',repr(e))
