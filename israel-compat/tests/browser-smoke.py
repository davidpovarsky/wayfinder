"""Read-only Wayfinder Israel UI check in a mobile Chromium viewport."""
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

URL = "https://wayfinder-130-110-238-163.nip.io/"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SHOT = Path(r"C:\Users\DAVID\Code\wayfinder\israel-compat\tests\wayfinder-mobile-check.png")
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=CHROME,
        headless=True,
        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
    )
    ctx = browser.new_context(
        viewport={"width": 430, "height": 932},
        device_scale_factor=1,
        is_mobile=True,
        has_touch=True,
        locale="he-IL",
        timezone_id="Asia/Jerusalem",
    )
    page = ctx.new_page()
    errors = []
    failed = []
    page.on("pageerror", lambda e: errors.append(str(e)[:200]))
    page.on("requestfailed", lambda r: failed.append((r.url[:125], r.failure)))
    try:
        response = page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(7500)
        print("HOME_HTTP", response.status if response else "none")
        print("TITLE", page.title())
        print("LANG", page.locator("html").get_attribute("lang"))
        print("DIR", page.locator("html").get_attribute("dir"))
        print("LEAFLET_MAP_COUNT", page.locator(".leaflet-container").count())
        print("LOADED_MAP_TILES", page.locator(".leaflet-tile-loaded").count())
        print("VISIBLE_STOP_MARKERS", page.locator(".leaflet-marker-icon").count())
        print("BODY_TEXT", page.locator("body").inner_text()[:500].replace("\n", " / "))
        print("PAGE_ERRORS", errors[:8])
        print("REQUEST_FAILURES", failed[:8])
        page.screenshot(path=str(SHOT), full_page=True)
        print("SCREENSHOT_PATH", str(SHOT))
    finally:
        browser.close()
