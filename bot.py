import os
import re
import requests
import xml.etree.ElementTree as ET
from io import BytesIO

import discord
from discord.ext import tasks

# ====== CONFIG ======
TOKEN = os.environ.get("DISCORD_TOKEN")

# Channel IDs (VOICE)
MAP_CHANNEL_ID = 1466767151267446953
TIME_CHANNEL_ID = 1467532233601585448      # canalul “uptime” -> devine ora serverului
ECONOMY_CHANNEL_ID = 1467532195143880775

CODE = "0c77cbd246bbdae1ad09d6ef78780e78"
BASE = "http://85.190.163.102:10710/feed"

STATS_URL = f"{BASE}/dedicated-server-stats.xml?code={CODE}"
CAREER_URL = f"{BASE}/dedicated-server-savegame.html?code={CODE}&file=careerSavegame"

UPDATE_INTERVAL = 600  # 10 minute (safe pt rate-limit)

# ====== DISCORD CLIENT ======
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ====== HELPERS ======
def download_bytes(url: str) -> BytesIO:
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    return BytesIO(r.content)

def parse_xml(xml_file: BytesIO) -> ET.Element:
    return ET.parse(xml_file).getroot()

def clean_voice_name(name: str, max_len: int = 95) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > max_len:
        name = name[: max_len - 1].rstrip() + "…"
    return name

async def safe_rename(channel_id: int, new_name: str):
    ch = client.get_channel(channel_id)
    if ch is None:
        print("Nu găsesc canalul:", channel_id)
        return
    new_name = clean_voice_name(new_name)
    if getattr(ch, "name", None) == new_name:
        return
    await ch.edit(name=new_name)
    print("Renamed:", channel_id, "->", new_name)

def find_text(root: ET.Element, xpath: str) -> str | None:
    el = root.find(xpath)
    if el is not None and (el.text or "").strip():
        return el.text.strip()
    return None

def format_money_exact(value: float) -> str:
    v = int(round(value))
    s = f"{v:,}".replace(",", ".")  # 52619 -> 52.619
    return f"{s} €"

# ====== EXTRACTORS ======
def get_map_title() -> str | None:
    root = parse_xml(download_bytes(CAREER_URL))
    title = find_text(root, ".//mapTitle")
    if title:
        return title
    mid = find_text(root, ".//mapId")
    return mid

def get_economy_money() -> float | None:
    root = parse_xml(download_bytes(CAREER_URL))
    txt = find_text(root, ".//statistics/money")
    if not txt:
        return None
    try:
        return float(txt)
    except:
        return None

def get_server_time_hhmm() -> tuple[int, int] | None:
    """
    Ia ora din dedicated-server-stats.xml:
    <Server ... dayTime="50725127" />
    dayTime e în milisecunde. Convertim în HH:MM (mod 24h).
    """
    root = parse_xml(download_bytes(STATS_URL))

    # caută elementul Server (poate fi <Server> sau alt caz)
    server_el = None
    for el in root.iter():
        if (el.tag or "").lower() == "server":
            server_el = el
            break

    if server_el is None:
        return None

    day_time = server_el.attrib.get("dayTime") or server_el.attrib.get("daytime")
    if not day_time:
        return None

    try:
        ms = int(float(day_time))
    except:
        return None

    total_minutes = (ms // 1000) // 60
    hh = (total_minutes // 60) % 24
    mm = total_minutes % 60
    return int(hh), int(mm)

# ====== UPDATE LOOP ======
async def do_update():
    # MAP
    try:
        m = get_map_title()
        await safe_rename(MAP_CHANNEL_ID, f"🌾 {m}" if m else "🌾 map-unknown")
    except Exception as e:
        print("Map update error:", e)

    # SERVER TIME (din dayTime)
    try:
        t = get_server_time_hhmm()
        if t is None:
            await safe_rename(TIME_CHANNEL_ID, "⏰ --:--")
        else:
            hh, mm = t
            await safe_rename(TIME_CHANNEL_ID, f"⏰ {hh:02d}:{mm:02d}")
    except Exception as e:
        print("Time update error:", e)
        await safe_rename(TIME_CHANNEL_ID, "⏰ --:--")

    # ECONOMY (exact)
    try:
        money = get_economy_money()
        if money is None:
            await safe_rename(ECONOMY_CHANNEL_ID, "💰 -- €")
        else:
            await safe_rename(ECONOMY_CHANNEL_ID, f"💰 {format_money_exact(money)}")
    except Exception as e:
        print("Economy update error:", e)
        await safe_rename(ECONOMY_CHANNEL_ID, "💰 -- €")

@tasks.loop(seconds=UPDATE_INTERVAL)
async def loop_update():
    await do_update()

@client.event
async def on_ready():
    print(f"Logged in ca {client.user}")
    await do_update()  # update instant
    if not loop_update.is_running():
        loop_update.start()

client.run(TOKEN)