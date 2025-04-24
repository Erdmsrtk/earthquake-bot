#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, logging, requests, asyncio
from bs4 import BeautifulSoup
from telegram import Bot

# ——— LOGGING —————————————————————————————————————————————————————————————
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ——— ENVIRONMENT ————————————————————————————————————————————————————————————
TOKEN       = os.getenv("TELEGRAM_TOKEN")
CHAT_ID_STR = os.getenv("CHAT_ID")
if not TOKEN or not CHAT_ID_STR:
    logging.error("Missing TELEGRAM_TOKEN or CHAT_ID")
    exit(1)
try:
    CHAT_ID = int(CHAT_ID_STR)
except ValueError:
    logging.error("CHAT_ID must be integer")
    exit(1)

bot = Bot(token=TOKEN)

# ——— CONSTANTS —————————————————————————————————————————————————————————————
CITIES       = ["ISTANBUL", "IZMIR", "MANISA"]
MAX_MESSAGES = 20
STATE_FILE   = "last_id.txt"
SOURCE_URL   = "http://www.koeri.boun.edu.tr/scripts/lst9.asp"

# ——— HELPERS ——————————————————————————————————————————————————————————————

def normalize(text: str) -> str:
    return (text.upper()
            .replace("İ","I").replace("ı","I")
            .replace("Ş","S").replace("Ğ","G")
            .replace("Ü","U").replace("Ö","O")
            .replace("Ç","C"))

def fetch_data() -> list[str]:
    try:
        r = requests.get(SOURCE_URL, timeout=10); r.raise_for_status()
        r.encoding = "iso-8859-9"
    except Exception as e:
        logging.error(f"Fetch failed: {e}")
        return []
    pre = BeautifulSoup(r.text, "html.parser").find("pre")
    return pre.text.splitlines()[6:] if pre else []

def parse_line(line: str) -> dict|None:
    p = line.split()
    if len(p)<10: return None
    return {
      "date":  p[0], "time": p[1],
      "lat":   p[2], "lon":   p[3],
      "depth": p[4], "mag":   p[6],
      "place": " ".join(p[9:])
    }

def load_last_id() -> str:
    return open(STATE_FILE).read().strip() if os.path.exists(STATE_FILE) else ""

def save_last_id(eid: str):
    with open(STATE_FILE,"w") as f: f.write(eid)

def filter_new(lines, last_id):
    found = []
    for line in lines:
        data = parse_line(line)
        if not data: continue
        if not any(c in normalize(data["place"]) for c in CITIES):
            continue
        eid = f"{data['date']}_{data['time']}"
        if eid == last_id: break
        found.append((eid,data))
        if len(found)>=MAX_MESSAGES: break
    return list(reversed(found))

def group_by_city(events):
    groups = {city: [] for city in CITIES}
    for eid, d in events:
        norm = normalize(d["place"])
        for city in CITIES:
            if city in norm:
                groups[city].append((eid,d))
                break
    return groups

def build_grouped_message(groups: dict[str, list[tuple[str,dict]]]) -> str:
    header = "🛰️ <b>Yeni Deprem Bildirimleri</b> 🛰️\n\n"
    body_parts = []
    emojis = {"ISTANBUL":"🌆", "IZMIR":"🏖️", "MANISA":"🌄"}
    for city in CITIES:
        evs = groups.get(city, [])
        if not evs:
            continue
        body_parts.append(f"{emojis.get(city,'📍')} <b>{city.title()}</b> <em>({len(evs)})</em>")
        for eid, d in evs:
            body_parts.append(
                f"📌 {d['place']}\n"
                f"   🗓 {d['date']} {d['time']} (TSİ)\n"
                f"   🌋 {d['mag']} ML — 📏 {d['depth']} km\n"
                f"   📍 {d['lat']}, {d['lon']}\n"
                f"<code>#ID: {eid}</code>"
            )
        body_parts.append("")  # şehirler arası boşluk
    return header + "\n".join(body_parts).strip()

def send_text(text):
    async def _send(): 
        await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML")
    try:
        asyncio.run(_send())
        logging.info("Aggregated message sent.")
    except Exception as e:
        logging.error(f"Send failed: {e}")

def main():
    lines   = fetch_data()
    if not lines:
        logging.info("No data.")
        return

    last_id = load_last_id()
    new_qs  = filter_new(lines, last_id)
    if not new_qs:
        logging.info("No new quakes.")
        return

    groups = group_by_city(new_qs)
    msg    = build_grouped_message(groups)
    print(msg)       # konsolda kontrol için
    send_text(msg)   # Telegram’a gönder
    # en son ID
    save_last_id(new_qs[-1][0])

if __name__=="__main__":
    main()