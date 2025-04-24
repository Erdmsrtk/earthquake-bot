#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Bot
import asyncio

# ——— LOGGING —————————————————————————————————————————————————————————————
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ——— ENVIRONMENT ————————————————————————————————————————————————————————————
TOKEN       = os.getenv("TELEGRAM_TOKEN")
CHAT_ID_STR = os.getenv("CHAT_ID")

if not TOKEN or not CHAT_ID_STR:
    logging.error("Missing TELEGRAM_TOKEN or CHAT_ID environment variables!")
    exit(1)

try:
    CHAT_ID = int(CHAT_ID_STR)
except ValueError:
    logging.error("CHAT_ID must be an integer!")
    exit(1)

bot = Bot(token=TOKEN)

# ——— CONSTANTS —————————————————————————————————————————————————————————————
CITIES       = ["ISTANBUL", "IZMIR", "MANISA"]
MAX_MESSAGES = 5
STATE_FILE   = "last_id.txt"
SOURCE_URL   = "http://www.koeri.boun.edu.tr/scripts/lst9.asp"

# ——— HELPERS ——————————————————————————————————————————————————————————————

def normalize(text: str) -> str:
    return (text.upper()
            .replace("İ", "I").replace("ı", "I")
            .replace("Ş", "S").replace("Ğ", "G")
            .replace("Ü", "U").replace("Ö", "O")
            .replace("Ç", "C"))

def fetch_data() -> list[str]:
    try:
        r = requests.get(SOURCE_URL, timeout=10)
        r.raise_for_status()
        r.encoding = "iso-8859-9"
    except requests.RequestException as e:
        logging.error(f"Failed to fetch data: {e}")
        return []
    pre = BeautifulSoup(r.text, "html.parser").find("pre")
    return pre.text.strip().split("\n")[6:] if pre else []

def parse_line(line: str) -> dict | None:
    parts = line.split()
    if len(parts) < 10:
        return None
    return {
        "date":  parts[0],
        "time":  parts[1],
        "lat":   parts[2],
        "lon":   parts[3],
        "depth": parts[4],
        "mag":   parts[6],
        "place": " ".join(parts[9:])
    }

def load_last_id() -> str:
    if os.path.exists(STATE_FILE):
        try:
            return open(STATE_FILE, "r").read().strip()
        except IOError as e:
            logging.warning(f"Could not read state file: {e}")
    return ""

def save_last_id(eid: str) -> None:
    try:
        with open(STATE_FILE, "w") as f:
            f.write(eid)
    except IOError as e:
        logging.error(f"Could not write state file: {e}")

def filter_new(lines: list[str], last_id: str) -> list[tuple[str, dict]]:
    found = []
    for line in lines:
        data = parse_line(line)
        if not data:
            continue
        norm_place = normalize(data["place"])
        if not any(city in norm_place for city in CITIES):
            continue
        eid = f"{data['date']}_{data['time']}"
        if eid == last_id:
            break
        found.append((eid, data))
        if len(found) >= MAX_MESSAGES:
            break
    return list(reversed(found))

def send_message(data: dict, eid: str) -> None:
    """Asenkron send_message coroutine'unu çalıştırır."""
    text = (
        f"<b>Deprem Bilgisi</b>\n"
        f"Yer: {data['place']}\n"
        f"Tarih: {data['date']} {data['time']} (TSİ)\n"
        f"Büyüklük: {data['mag']} ML\n"
        f"Derinlik: {data['depth']} km\n"
        f"Koordinatlar: {data['lat']}, {data['lon']}\n"
        f"<code>#ID: {eid}</code>"
    )

    async def _send():
        await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML")

    try:
        asyncio.run(_send())
        logging.info(f"Sent: {eid}")
    except Exception as e:
        logging.error(f"Failed to send {eid}: {e}")

# ——— MAIN ——————————————————————————————————————————————————————————————————

def main() -> None:
    lines   = fetch_data()
    if not lines:
        logging.info("No data fetched, exiting.")
        return

    last_id = load_last_id()
    new_qs  = filter_new(lines, last_id)
    if not new_qs:
        logging.info("No new quakes in target cities.")
        return

    for i, (eid, data) in enumerate(new_qs):
        send_message(data, eid)
        if i == len(new_qs) - 1:
            save_last_id(eid)

if __name__ == "__main__":
    main()