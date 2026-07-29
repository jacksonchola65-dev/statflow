import json
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar

BASE = 'http://127.0.0.1:8000/api/v1'
jar = CookieJar()
opener = build_opener(HTTPCookieProcessor(jar))

# login
req = Request(
    BASE + '/auth/login',
    data=json.dumps({'email': 'admin@example.com', 'password': 'ChangeMe123!'}).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
)
resp = opener.open(req, timeout=20)
print('login', resp.status)
body = json.loads(resp.read().decode())
print('user', body['user']['email'], 'role', body['user']['role'])

# dataset list
req = Request(BASE + '/analytics/datasets', headers={'Cookie': '; '.join(f'{c.name}={c.value}' for c in jar)})
resp = opener.open(req, timeout=20)
data = json.loads(resp.read().decode())
print('datasets count', data.get('total'), 'items', len(data.get('items', [])))
for item in data.get('items', [])[:3]:
    print('-', item['dataset_name'], item['ingestion_job_id'], 'ready', item['analytics_ready'])

if data.get('items'):
    ds_id = data['items'][0]['ingestion_job_id']
    print('inspect', ds_id)
    for path in [
        '/analytics/datasets/' + ds_id,
        '/analytics/datasets/' + ds_id + '/dimensions',
        '/analytics/datasets/' + ds_id + '/measures',
    ]:
        req = Request(BASE + path, headers={'Cookie': '; '.join(f'{c.name}={c.value}' for c in jar)})
        resp = opener.open(req, timeout=20)
        body = json.loads(resp.read().decode())
        print(path, 'len', len(body) if isinstance(body, list) else 'obj')
        if path.endswith('/dimensions'):
            for d in body[:3]:
                print(' dim', d)
        if path.endswith('/measures'):
            for m in body[:3]:
                print(' meas', m)
    dims = []
    measures = []
    dims_data = json.loads(opener.open(Request(BASE + '/analytics/datasets/' + ds_id + '/dimensions', headers={'Cookie': '; '.join(f'{c.name}={c.value}' for c in jar)})).read().decode())
    if dims_data:
        dims = [{'column_name': dims_data[0]['identifier']}]
    meas_data = json.loads(opener.open(Request(BASE + '/analytics/datasets/' + ds_id + '/measures', headers={'Cookie': '; '.join(f'{c.name}={c.value}' for c in jar)})).read().decode())
    if meas_data:
        meas = meas_data[0]
        measures = [{'column_name': meas['identifier'], 'aggregation': meas['supported_aggregations'][0]}]
    if dims and measures:
        q = {
            'dataset_reference': {'ingestion_job_id': ds_id},
            'dimensions': dims,
            'measures': measures,
            'limit': 10,
        }
        req = Request(
            BASE + '/analytics/query',
            data=json.dumps(q).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Cookie': '; '.join(f'{c.name}={c.value}' for c in jar),
                'x-csrf-token': body['csrf_token'] if 'csrf_token' in body else ''
            },
        )
        resp = opener.open(req, timeout=20)
        qres = json.loads(resp.read().decode())
        print('query rows', len(qres.get('rows', [])), 'columns', [c['identifier'] for c in qres['columns']])
else:
    print('no dataset')
