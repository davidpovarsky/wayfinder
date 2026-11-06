import sys
from urllib.parse import parse_qs,urlsplit
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8",errors="replace")
base="https://wayfinder-130-110-238-163.nip.io/?from=31.816586%2C35.202785&to=31.788564%2C35.224251"
cases=[
 ("depart-date",base+"&date=2026-11-08&time=09%3A30"),
 ("arrive-shortcut",base+"&departAt=2026-11-08T17%3A15&arriveBy=true"),
 ("legacy-now",base),
]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",args=["--no-sandbox","--disable-gpu"])
 c=b.new_context(viewport={"width":430,"height":932},device_scale_factor=1,is_mobile=True,has_touch=True,locale="he-IL",timezone_id="Asia/Jerusalem")
 for name,url in cases:
  page=c.new_page()
  errors=[]
  requests=[]
  page.on("pageerror",lambda e:errors.append(str(e)[:170]))
  page.on("request",lambda r:requests.append(r.url) if "/api/otp/plan?" in r.url else None)
  try:
   res=page.goto(url,wait_until="domcontentloaded",timeout=34000)
   page.wait_for_timeout(8500)
   if not requests: page.wait_for_timeout(6500)
   params=parse_qs(urlsplit(requests[0]).query) if requests else {}
   print("CASE",name,"HTTP",res.status if res else None,"OTP_CALLS",len(requests),
     "DATE",params.get("date"),"TIME",params.get("time"),
     "ARRIVE_BY",params.get("arriveBy"),
     "ITINERARIES",page.locator(".itinerary-tab").count(),
     "JS_ERRORS",errors[:3],flush=True)
   if name=="depart-date":
    assert params.get("date")==["11-08-2026"],params
    assert params.get("arriveBy")==["false"],params
    assert params.get("time")==["9:30 AM"],params
   if name=="arrive-shortcut":
    assert params.get("date")==["11-08-2026"],params
    assert params.get("arriveBy")==["true"],params
    assert params.get("time")==["5:15 PM"],params
   if name=="legacy-now":
    assert "time" not in params and "date" not in params,params
   assert not errors,errors
  except Exception as e: print("FAIL",name,type(e).__name__,str(e)[:550],flush=True)
  finally: page.close()
 b.close()
