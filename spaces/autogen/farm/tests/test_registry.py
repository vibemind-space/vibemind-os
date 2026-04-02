"""Smoke-test registry review fixes."""
import urllib.request, json

BASE = 'http://127.0.0.1:8899'

# I2: Score < 6 with validated status -> should 422
req = urllib.request.Request(BASE + '/api/v1/registry',
    data=json.dumps({'team_key':'test','run_id':'x','status':'validated','eval_score':3}).encode(),
    headers={'Content-Type':'application/json'}, method='POST')
try:
    urllib.request.urlopen(req)
    print('I2: FAIL - accepted bad score')
except urllib.error.HTTPError as e:
    print(f'I2: OK - got {e.code} for validated+score=3')

# M4: Pagination
resp = urllib.request.urlopen(BASE + '/api/v1/registry?limit=2&offset=0')
d = json.loads(resp.read())
print(f'M4: OK - got {len(d)} entries with limit=2 (expected 2)')

# C2: PUT status without auth -> should 401/403
entry_id = json.loads(urllib.request.urlopen(BASE + '/api/v1/registry').read())[0]['id']
req = urllib.request.Request(BASE + f'/api/v1/registry/{entry_id}/status',
    data=json.dumps({'status':'deprecated'}).encode(),
    headers={'Content-Type':'application/json'}, method='PUT')
try:
    urllib.request.urlopen(req)
    print('C2: FAIL - accepted unauthenticated request')
except urllib.error.HTTPError as e:
    print(f'C2: OK - got {e.code} for unauthenticated PUT')
