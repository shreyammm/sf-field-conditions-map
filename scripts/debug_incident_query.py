#!/usr/bin/env python3
import json, urllib.request
URL='https://data.sfgov.org/api/v3/views/wg3w-h783/query.json'
H={'User-Agent':'sf-field-conditions-map-debug/1.0','Accept':'application/json','Content-Type':'application/json'}

def q(query,page_size=5):
    body=json.dumps({'query':query,'page':{'pageNumber':1,'pageSize':page_size},'includeSynthetic':False}).encode()
    req=urllib.request.Request(URL,data=body,headers=H,method='POST')
    with urllib.request.urlopen(req,timeout=180) as r: obj=json.load(r)
    if isinstance(obj,list): return obj
    for k in ('data','results','rows'):
        if isinstance(obj,dict) and isinstance(obj.get(k),list): return obj[k]
    print('RAW',type(obj),obj if isinstance(obj,dict) else str(obj)[:1000]); return []

a='2026-09-28T00:00:00.000'; b='2026-09-29T00:00:00.000'
where=f"`incident_datetime` >= '{a}' AND `incident_datetime` < '{b}' AND `latitude` IS NOT NULL AND `longitude` IS NOT NULL"
queries=[
 ('all_group',f"SELECT `intersection`,`police_district`,`analysis_neighborhood`,`latitude`,`longitude`,count(distinct `incident_id`) AS report_count WHERE {where} GROUP BY `intersection`,`police_district`,`analysis_neighborhood`,`latitude`,`longitude` ORDER BY `latitude` ASC,`longitude` ASC LIMIT 5"),
 ('city_count',f"SELECT count(distinct `incident_id`) AS report_count WHERE {where} LIMIT 1"),
]
for name,query in queries:
    try:
        rows=q(query,5)
        print(name,'LEN',len(rows),'ROWS',rows)
    except Exception as e:
        print(name,'ERR',repr(e))
