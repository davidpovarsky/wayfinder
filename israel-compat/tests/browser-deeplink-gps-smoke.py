"""Wayfinder Israel: read-only mobile deep-link and GPS-marker smoke test."""
import sys, time, re
sys.stdout.reconfigure(encoding="utf-8",errors="replace")
from playwright.sync_api import sync_playwright

BASE="https://wayfinder-130-110-238-163.nip.io"
CHROME=r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CASES=[
 ("route",BASE+"/?route=mot%3Aroute%3A33285"),
 ("stop",BASE+"/map/stops/mot%3Astop%3A5997"),
 ("plan",BASE+"/?plan=1"),
 ("trip",BASE+"/?from=31.81634%2C35.20318&to=31.78948%2C35.22441&fromName=Lipsky&toName=Beit+Yisrael")
]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path=CHROME,args=["--no-sandbox","--disable-gpu","--disable-dev-shm-usage"])
 context=browser.new_context(viewport={"width":430,"height":932},device_scale_factor=1,is_mobile=True,has_touch=True,locale="he-IL",timezone_id="Asia/Jerusalem")
 for name,url in CASES:
  page=context.new_page()
  errors=[]
  page.on("pageerror",lambda e:errors.append(str(e)[:130]))
  requests=[]
  page.on("response",lambda r:requests.append((r.status,r.url.split("?")[0])) if "trips-for-route" in r.url or "/api/otp/plan" in r.url else None)
  try:
   r=page.goto(url,wait_until="domcontentloaded",timeout=33000)
   page.wait_for_timeout(8000 if name=="route" else 5200)
   body=page.locator("body").inner_text()
   bus_count=page.locator('.leaflet-marker-icon img[src^="data:image/svg+xml"]').count()
   print(name.upper(),"HTTP",r.status if r else None,"RTL",page.locator("html").get_attribute("dir"),
         "MARKERS",bus_count,"GPS_API_CALLS",requests[:6],"JS_ERRORS",errors[:3],flush=True)
   print(name.upper()+"_VIEW",re.sub(r"\s+"," ",body[-370:]),flush=True)
  except Exception as e:print("EXCEPTION",name,type(e).__name__,str(e)[:300],flush=True)
  finally:page.close()
 browser.close()
