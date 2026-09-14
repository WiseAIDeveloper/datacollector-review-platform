from pathlib import Path
import json,urllib.request
from playwright.sync_api import sync_playwright,expect
src=Path(__file__).parent
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox']);page=b.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 for api in ['captures','matrix','batches','quality']:
  data=json.load(urllib.request.urlopen('http://10.1.1.49:8769/api/'+api));page.route('**/api/'+api,lambda r,request,data=data:r.fulfill(json=data))
 page.route('**/image_zoom.js',lambda r:r.fulfill(body=(src/'image_zoom.js').read_text(),content_type='text/javascript'))
 page.route('**/coverage.html',lambda r:r.fulfill(body=(src/'coverage.html').read_text(),content_type='text/html'))
 page.route('**/terminal.css',lambda r:r.fulfill(body=(src/'terminal.css').read_text(),content_type='text/css'))
 for width in [1440,390]:
  page.set_viewport_size({'width':width,'height':1000});page.goto('http://10.1.1.49:8769/coverage.html');page.locator('.batch').first.wait_for();expect(page.locator('#execute')).to_have_count(1)
  button=page.locator('#execute').bounding_box();header=page.locator('.dashboard-header').bounding_box();assert header['x']+header['width']-(button['x']+button['width'])<25
  page.evaluate('window.scrollTo(0,800)');page.wait_for_timeout(150);assert abs(page.locator('.dashboard-header').bounding_box()['y'])<1
  expect(page.locator('#execute')).to_be_in_viewport();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  page.screenshot(path='/tmp/dashboard-header-'+str(width)+'.png')
 assert not errors,errors;b.close()
print('PASS sticky top pane, top-right Execute, desktop/mobile widths, and no horizontal overflow.')
