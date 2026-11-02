"""D7B read-only HTTP verification; secrets exist only in memory."""
import os, sys, json, urllib.request, urllib.error
sys.path.insert(0, os.path.abspath('backend'))
os.environ['DJANGO_SETTINGS_MODULE']='config.settings.demo_view'
import django
django.setup()
from apps.organizations.demo.demo_view import verified_locations
from apps.organizations.demo.rehearsal_command import _Authority, _read_bundle
plan=verified_locations()
bundle,status=_read_bundle(plan,_Authority(plan),plan.deliveries[0])
assert status=='complete'
base='http://127.0.0.1:5174/api'
def request(path, token=None, data=None):
    headers={'Content-Type':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    req=urllib.request.Request(base+path,headers=headers,data=json.dumps(data).encode() if data else None)
    try:
        with urllib.request.urlopen(req,timeout=15) as response: return response.status,json.load(response)
    except urllib.error.HTTPError as e: return e.code,None
seen={}; counts={}; failures=[]; animal_ids=[]
for entry in bundle['credentials']:
    status,login=request('/auth/login',data={'email':entry['email'],'password':entry['password']})
    if status!=200: failures.append('login:'+str(status)); continue
    token=login['access']; status,context=request('/common/context',token)
    assert status==200 and context['role']==entry['role'] and context['organization']['id']==entry['organization_uuid']
    status,animals=request('/animals/',token); assert status==200
    org=entry['organization_uuid']; ids={a['id'] for a in animals}
    if org in seen: assert ids==seen[org]
    else: seen[org]=ids
    counts[entry['role']]=counts.get(entry['role'],0)+1
    for path in ['/organizations/','/dashboard/summary','/dashboard/upcoming-births','/farms/','/lots/']:
        code,_=request(path,token)
        if code!=200: failures.append(path+':'+str(code))
    if animals:
        aid=animals[0]['id']
        for path in [f'/breeding/animal/{aid}/history',f'/pregnancies/animal/{aid}/history',f'/births/animal/{aid}/history',f'/production/history/{aid}',f'/timeline/animal/{aid}']:
            code,_=request(path,token)
            if code!=200: failures.append(path.split('/')[1]+':'+str(code))
    animal_ids.append((org,token,next(iter(ids),None)))
assert len(seen)==5 and not any(a & b for i,a in enumerate(seen.values()) for b in list(seen.values())[i+1:])
checks=0
for org,token,aid in animal_ids:
    other=next((item[2] for item in animal_ids if item[0]!=org and item[2]),None)
    if other:
        code,_=request('/animals/'+other,token); assert code in (403,404); checks+=1
print(json.dumps({'logins':len(animal_ids),'roles':counts,'organizations':len(seen),'animals_per_org':sorted(map(len,seen.values())),'cross_org_denials':checks,'endpoint_failures':sorted(set(failures))}))
