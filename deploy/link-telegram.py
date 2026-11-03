#!/usr/bin/env python3
"""Connect only the owner's Telegram menu to verified Wayfinder staging.

Does not read Telegram updates or change the OpenClaw bot's gateway/channel.
Telegram bot token is read locally and never displayed or committed.
"""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

TOKEN_FILE = Path(os.getenv("NEVO_TELEGRAM_TOKEN_FILE",
    "/var/lib/openclaw/.openclaw/credentials/nevo-telegram.token"))
CHAT_ID = int(os.getenv("NEVO_TRANSIT_OWNER_ID", "8005665701"))
URL = os.getenv("WAYFINDER_URL", "https://wayfinder-130-110-238-163.nip.io/")

if not URL.startswith("https://wayfinder-130-110-238-163.nip.io/"):
    raise SystemExit("Unexpected Wayfinder URL: aborting without changing Telegram")


def api(method, payload):
    token = TOKEN_FILE.read_text().strip()
    request = Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=18) as response:
        result = json.load(response)
    if result.get("ok") is not True:
        raise RuntimeError(f"Telegram rejected {method}")
    return result["result"]


def main():
    # Require a healthy page before altering the user's existing bot menu.
    with urlopen(URL, timeout=15) as response:
        if response.status != 200:
            raise RuntimeError("Public HTTPS Wayfinder is unhealthy")
    label = "🚌 תחבורה ומפות"
    menu = {"type": "web_app", "text": label, "web_app": {"url": URL}}
    api("setChatMenuButton", {"chat_id": CHAT_ID, "menu_button": menu})
    actual = api("getChatMenuButton", {"chat_id": CHAT_ID})
    if actual.get("type") != "web_app" or actual.get("web_app", {}).get("url") != URL:
        raise RuntimeError("Telegram did not confirm the new private-chat menu")
    print("Owner's private chat menu now opens:", URL)
    result = api("sendMessage", {
        "chat_id": CHAT_ID,
        "parse_mode": "HTML",
        "text": "🚌 <b>Wayfinder Israel החדש מוכן לבדיקה</b>\n\n"
                "מפת Mapbox, תחנות וקווים בישראל, זמני הגעה וחיפוש בעברית. "
                "הממשק הישן נשאר זמין כגיבוי. "
                "תכנון נסיעות עשוי להיות לא זמין כשהספק מחזיר שגיאה.",
        "reply_markup": {"inline_keyboard": [[{
            "text": "🗺 פתח את Wayfinder Israel",
            "web_app": {"url": URL},
        }]]},
    })
    print("Telegram launch message sent:", bool(result.get("message_id")))


if __name__ == "__main__":
    main()
