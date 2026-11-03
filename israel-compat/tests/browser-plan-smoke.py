import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
url='https://wayfinder-130-110-238-163.nip.io/'
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True,args=['--no-sandbox','--disable-gpu'])
 page=b.new_page(viewport={"width":430,"height":932},is_mobile=True,has_touch=True,locale='he-IL',timezone_id='Asia/Jerusalem')
 errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)[:180]))
 page.on('response',lambda r:print('GEO_RESPONSE',r.status,r.url.split('?')[0]) if '/api/oba/geocode-location' in r.url else None)
 try:
  r=page.goto(url,wait_until='domcontentloaded',timeout=30000)
  page.wait_for_timeout(4900)
  print('HOME_HTTP',r.status,'LANG',page.locator('html').get_attribute('lang'),'RTL',page.locator('html').get_attribute('dir'))
  print('MAP_MARKERS',page.locator('.leaflet-marker-icon').count())
  plan=page.get_by_text('תכנון נסיעה',exact=True)
  print('PLAN_TABS',plan.count())
  if plan.count():
   plan.first.click(timeout=8000)
   page.wait_for_timeout(800)
   fields=page.locator('input[role="combobox"]')
   print('COMBOBOXES',fields.count())
   print('BODY',page.locator('body').inner_text()[:400].replace('\n','|'))
   if fields.count():
    fields.first.fill('ליפסקי 39')
    page.wait_for_timeout(2450)
    print('SUGGESTIONS',page.locator('[role="option"]').count())
    if page.locator('[role="option"]').count():
     page.locator('[role="option"]').first.click(timeout=7000)
     print('FIRST_SELECTED')
    fields=page.locator('input[role="combobox"]')
    if fields.count()>1:
     fields.nth(1).fill('בית ישראל')
     page.wait_for_timeout(2400)
     print('SECOND_SUGGESTIONS',page.locator('[role="option"]').count())
     if page.locator('[role="option"]').count():
      page.locator('[role="option"]').first.click(timeout=7000)
      print('SECOND_SELECTED')
    print('AFTER_SELECTION',page.locator('body').inner_text()[-650:].replace('\n','|'))
    page.wait_for_timeout(1800)
    print('INPUT_VALUES',[el.input_value() for el in page.locator('input[role="combobox"]').all()])
    buttons=page.get_by_role('button',name='תכנון נסיעה',exact=True)
    print('PLAN_BUTTONS',buttons.count())
    if buttons.count():
     button=buttons.last
     print('PLAN_BUTTON_ENABLED',button.is_enabled())
     if button.is_enabled():
      button.click(timeout=7000)
      page.wait_for_timeout(8500)
      print('RESULT_SCREEN',page.locator('body').inner_text()[-1400:].replace('\\n','|'))
      print('RESULT_PAGE_ERRORS',errors[:8])
  print('PAGE_ERRORS',errors[:8])
 except Exception as e: print('BROWSER_ERROR',type(e).__name__,str(e)[:330]); print('PAGE_ERRORS',errors[:8])
 finally:b.close()
