import json,urllib.request
from playwright.sync_api import sync_playwright,expect
BASE='http://10.1.1.49:8769'
def get(path):
 with urllib.request.urlopen(BASE+path) as r:return json.load(r)
rows=get('/api/captures');state=get('/api/ingestion');current={r['key']:r for r in rows}
for event in state['events']:
 if event['available']:
  row=current[event['key']]
  assert event['lighting']==row['metadata'].get('lighting','')
  assert event['subject']==row['metadata'].get('subject','')
print('PASS live ingestion API matches current CSV metadata')
event=next(e for e in state['events'] if e['available']);row=current[event['key']];state['events']=[event]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox']);page=browser.new_page()
 page.route('**/api/ingestion?*',lambda route:route.fulfill(json=state))
 page.route('**/api/capture?*',lambda route:route.fulfill(json=row))
 def save(route):
  changes=route.request.post_data_json['changes'];row['metadata'].update(changes);event.update(changes);route.fulfill(json={'updated':True})
 page.route('**/api/edit-capture',save)
 page.goto(BASE+'/ingestion.html');page.locator('#logs button').click();page.locator('#edit-lighting').wait_for()
 lighting='office-white' if row['metadata'].get('lighting')!='office-white' else 'dark'
 page.locator('#edit-lighting').select_option(lighting)
 page.on('dialog',lambda d:d.accept('test-pin') if d.type=='prompt' else d.accept())
 page.locator('#save-metadata').click()
 expect(page.locator('#logs tr').first.locator('td').nth(2)).to_have_text(lighting)
 page.wait_for_function('!editing');expect(page.locator('#edit-lighting')).to_have_value(lighting)
 browser.close()
print('PASS saving metadata refreshes visible ingestion row (mocked edit, no real changes)')
