import sys,re,time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
url='https://wayfinder-130-110-238-163.nip.io/'
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True,args=['--no-sandbox','--disable-gpu'])
 ctx=b.new_context(viewport={"width":430,"height":932},is_mobile=True,has_touch=True,locale='he-IL',timezone_id='Asia/Jerusalem',permissions=['geolocation'],geolocation={"latitude":31.815188,"longitude":35.203022})
 pg=ctx.new_page()
 errors=[]
 pg.on('pageerror',lambda e:errors.append(str(e)[:120]))
 def tiles():
  vals=[]
  for a in pg.locator('img.leaflet-tile').all():
   src=a.get_attribute('src') or ''
   m=re.search(r'/tiles/512/(\d+)/',src)
   if m: vals.append(int(m.group(1)))
  return sorted(set(vals))
 try:
  pg.goto(url,wait_until='domcontentloaded',timeout=30000)
  pg.wait_for_timeout(3600)
  before=tiles()
  button=pg.get_by_role('button',name='מצא את המיקום שלי')
  print('BUTTON_COUNT',button.count(),'INITIAL_TILES_ZOOM',before)
  if button.count():
   button.click(timeout=7000)
   pg.wait_for_timeout(4500)
   print('POST_LOCATION_TILES_ZOOM',tiles())
   print('CENTER_BLUE_MARKERS',pg.locator('.leaflet-interactive').count())
  print('JS_ERRORS',errors[:5])
 except Exception as e:print('TEST_ERROR',type(e).__name__,str(e)[:180])
 finally:b.close()
