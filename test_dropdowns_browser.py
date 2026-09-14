import json,urllib.request
from playwright.sync_api import sync_playwright,expect
BASE='http://10.1.1.49:8769'
def get(path):
 with urllib.request.urlopen(BASE+path) as r:return json.load(r)
rows=get('/api/captures');batches=get('/api/batches')
row=next(r for r in rows if any(b['batch_name']==r['folder'] and b['test_plan_name']==r['metadata']['test_plan_name'] for b in batches))
batch=next(b for b in batches if b['batch_name']==row['folder'] and b['test_plan_name']==row['metadata']['test_plan_name'])
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox']);page=browser.new_page()
 page.goto(BASE+'/search.html');page.evaluate('(key)=>openCapture(key)',row['key']);page.locator('#edit-subject').wait_for()
 for field in ['subject','lighting','capture_device']:assert page.locator('#edit-'+field).evaluate('(e)=>e.tagName')=='SELECT'
 def values(field):return page.locator('#edit-'+field+' option').evaluate_all('(options)=>options.map(o=>o.value)')
 assert set(batch['expected_lighting'].split(';'))<=set(values('lighting'))
 assert set(batch['expected_web_devices'].split(';'))<=set(values('capture_device'))
 assert '' in values('capture_device')
 assert row['metadata']['subject'] in values('subject')
 page.locator('#review-close').click()
 custom=[dict(b,expected_lighting='office-white',expected_web_devices='fixture-web-device',expected_identities='fixture-identity') if b is batch else b for b in batches]
 page.route('**/api/batches',lambda route:route.fulfill(json=custom))
 page.evaluate('(key)=>openCapture(key)',row['key']);page.locator('#edit-subject').wait_for()
 assert 'fixture-identity' in values('subject') and 'fixture-web-device' in values('capture_device')
 assert set(values('lighting'))=={'office-white',row['metadata'].get('lighting','')}
 assert page.locator('#edit-subject').input_value()==row['metadata']['subject']
 browser.close()
print('PASS dropdown types, batch choices, App blank device, configured identities, changed CSV options, preserved current metadata. No writes.')
