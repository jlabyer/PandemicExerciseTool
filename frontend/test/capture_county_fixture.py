# LEGACY custom-expansion capture helper; preserved for rollback.
# """Capture the running frontend for browser-free expansion integration tests.
# 
# From frontend, with the app running on port 8051:
#     python test/capture_county_fixture.py > /tmp/county-fixture.json
#     PET_COUNTY_FIXTURE=/tmp/county-fixture.json node --test test/test_county_expansion_integration.cjs
# 
# Only synthetic county data is submitted; no simulation is started.
# """
# import contextlib
# import json
# import os
# import sys
# from pathlib import Path
# sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# with contextlib.redirect_stdout(sys.stderr):
#     from county_data import county_metrics
#     from test.test_county_age_breakdown import output_county
# import requests
# base=os.environ.get('PET_FRONTEND_URL', 'http://localhost:8051')
# deps=requests.get(base+'/_dash-dependencies', timeout=10)
# deps.raise_for_status()
# deps=deps.json()
# expansion=next(item for item in deps if (item.get('clientside_function') or {}).get('function_name')=='updateRow')
# table_callback=next(item for item in deps if 'spread-table.children' in item['output'])
# counties=[]
# mapping={}
# ages={}
# for i in range(254):
#     county=county_metrics(output_county())
#     county['fips']=str(48001+2*i)
#     ages[county['fips']]=county.pop('ageGroups')
#     counties.append(county)
#     mapping[f'County {i:03}']=county['fips']
# values={
#     'county-table-day':{'day':0,'counties':counties,'mapping':mapping},
#     'view-toggle':'count','county-search':'','county-table-sort':{'col':'name','dir':'asc'},
#     'selected-county-store':None,'selected-model-store':'seihrd-stochastic','expanded-counties':[],
# }
# response=requests.post(base+'/_dash-update-component',json={
#     'output':table_callback['output'],
#     'outputs':[{'id':'spread-table','property':'children'},{'id':'county-controls','property':'style'}],
#     'inputs':[{**item,'value':values[item['id']]} for item in table_callback['inputs']],
#     'state':[{**item,'value':values[item['id']]} for item in table_callback['state']],
#     'changedPropIds':['county-table-day.data'],
# }, timeout=20)
# response.raise_for_status()
# asset=requests.get(base+'/assets/county_data.js',timeout=10)
# asset.raise_for_status()
# print(json.dumps({'dependency':expansion,'table':response.json()['response']['spread-table']['children'],
#     'javascript':asset.text,'ages':ages,'labels':['0-4 years','5-17 years','18-49 years','50-64 years','65+ years']}))
