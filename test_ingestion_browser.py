"""Browser UI checks using isolated mocked events; never modifies dataset records."""
import os
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('VIEWER_URL', 'http://10.1.1.49:8769')
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox'])
    page=browser.new_page()
    state={'calls':0,'fail':False}
    def route(request):
        state['calls']+=1
        if state['fail']:
            request.fulfill(status=503,body='test outage');return
        older='before=' in request.request.url
        name='older.jpg' if older else 'new.jpg' if state['calls']>1 else 'first.jpg'
        event=dict(id=1,status='ingested',detected_at=datetime.now(timezone.utc).isoformat(),filename=name,batch='fixture_batch',lighting='dark',subject='fixture',sdk='web',device='iphone-13',test_plan='fixture_plan',creation_time='capture time')
        request.fulfill(json=dict(last_scan=event['detected_at'],errors=[],pending_images=0,total=1,existing=0,ingested=1,events=[event],next_before=None if older else 1))
    page.route('**/api/ingestion?*',route)
    page.goto(BASE+'/ingestion.html')
    expect(page.locator('#logs')).to_contain_text('first.jpg')
    expect(page.locator('#logs')).to_contain_text('new.jpg',timeout=8000)
    headers=page.locator('th').all_text_contents()
    assert 'Status' not in headers and 'Detected at' not in headers
    assert page.locator('#logs td').count()==8
    assert page.evaluate('getComputedStyle(document.body).backgroundColor')=='rgb(8, 10, 12)'
    page.locator('#older').click();expect(page.locator('#logs')).to_contain_text('older.jpg')
    page.locator('#latest').click();expect(page.locator('#logs')).to_contain_text('new.jpg')
    state['fail']=True;page.locator('#refresh').click();expect(page.locator('#error')).to_contain_text('503')
    state['fail']=False;page.locator('#refresh').click();expect(page.locator('#error')).to_be_empty()
    assert page.locator('.app-sidebar a[aria-current]').inner_text()=='Ingestion logs'
    for path in ['/', '/coverage.html']:
        page.goto(BASE+path)
        expect(page.locator('.app-sidebar').get_by_role('link',name='Ingestion logs')).to_have_attribute('href','/ingestion.html')
    browser.close()
print('PASS: 5-second refresh, compact dark style, hidden event status/time, pagination, outage recovery, sidebar links.')
