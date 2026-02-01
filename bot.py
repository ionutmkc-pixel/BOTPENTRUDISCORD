import os
import re
import time
import requests
import xml.etree.ElementTree as ET
from io import BytesIO

import discord
from discord.ext import tasks

# ====== CONFIG ======
TOKEN = os.environ.get("DISCORD_TOKEN")

# Channel IDs (VOICE)
MAP_CHANNEL_ID = 1466767151267446953
UPTIME_CHANNEL_ID = 1467532233601585448
ECONOMY_CHANNEL_ID = 1467532195143880775

CODE = "0c77cbd246bbdae1ad09d6ef78780e78"
BASE = "http://85.190.163.102:10710/feed"

STATS_URL = f"{BASE}/dedicated-server-stats.xml?code={CODE}"
CAREER_URL = f"{BASE}/dedicated-server-savegame.html?code={CODE}&file=careerSavegame"
ECONOMY_URL = f"{BASE}/dedicated-server-savegame.html?code={CODE}&file=economy"

UPDATE_INTERVAL = 600  # 10 minute (safe pt rate-limit)

# ====== DISCORD CLIENT ======
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ====== HELPERS ======
def download_bytes(url: str) -> BytesIO:
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    return BytesIO(r.content)

def clean_voice_name(name: str, max_len: int = 95) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > max_len:
        name = name[: max_len - 1].rstrip() + "…"
    return name

def parse_xml(xml_file: BytesIO) -> ET.Element:
    tree = ET.parse(xml_file)
    return tree.getroot()

def find_first_text(root: ET.Element, paths: list[str]) -> str | None:
    for p in paths:
        el = root.find(p)
        if el is not None and (el.text or "").strip():
            return el.text.strip()
    return None

def find_first_number_by_tag_contains(root: ET.Element, needle: str) -> float | None:
    needle = needle.lower()
    for el in root.iter():
        tag = (el.tag or "").lower()
        if needle in tag:
            txt = (el.text or "").strip()
            if not txt:
                continue
            try:
                return float(txt)
            except:
                continue
    return None

def format_duration(seconds: int) -> str:
    if seconds < 0:
        seconds = 0
    days = seconds // 86400
    seconds %= 86400
    hours = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60

    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

def format_money(value: float) -> str:
    # FS values sunt de obicei în €
    abs_v = abs(value)
    if abs_v >= 1_000_000_000:
        return f"{value/1_000_000_000:.2f}B €"
    if abs_v >= 1_000_000:
        return f"{value/1_000_000:.2f}M €"
    if abs_v >= 1_000:
        return f"{value/1_000:.1f}K €"
    return f"{value:.0f} €"

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

# ====== EXTRACTORS ======
def get_map_title() -> str | None:
    root = parse_xml(download_bytes(CAREER_URL))
    # în fișierul tău apare <mapTitle>...</mapTitle>
    title = find_first_text(root, [".//mapTitle"])
    if title:
        return title
    # fallback
    mid = find_first_text(root, [".//mapId"])
    return mid

def get_uptime_seconds() -> int | None:
    root = parse_xml(download_bytes(STATS_URL))

    # încercări “standard”
    for path in [".//uptime", ".//serverUptime", ".//server_uptime", ".//upTime", ".//up_time"]:
        txt = find_first_text(root, [path])
        if txt:
            try:
                return int(float(txt))
            except:
                pass

    # fallback: caută orice tag care conține "uptime" și are număr
    n = find_first_number_by_tag_contains(root, "uptime")
    if n is not None:
        return int(n)

    # alt fallback: uneori există "runningTime" etc.
    n2 = find_first_number_by_tag_contains(root, "running")
    if n2 is not None:
        return int(n2)

    return None

def get_economy_money() -> float | None:
    root = parse_xml(download_bytes(ECONOMY_URL))

    # Uneori banii sunt la .//statistics/money sau direct .//money
    txt = find_first_text(root, [".//statistics/money", ".//money"])
    if txt:
        try:
            return float(txt)
        except:
            pass

    # fallback: primul <money> numeric pe oriunde
    for el in root.iter():
        if (el.tag or "").lower() == "money":
            t = (el.text or "").strip()
            if not t:
                continue
            try:
                return float(t)
            except:
                continue

    return None

# ====== UPDATE LOOP ======
async def do_update():
    # Map
    try:
        m = get_map_title()
        await safe_rename(MAP_CHANNEL_ID, f"🌾 {m}" if m else "🌾 map-unknown")
    except Exception as e:
        print("Map update error:", e)

    # Uptime
    try:
        up = get_uptime_seconds()
        if up is None:
            await safe_rename(UPTIME_CHANNEL_ID, "⏱️ Uptime: unknown")
        else:
            await safe_rename(UPTIME_CHANNEL_ID, f"⏱️ Uptime: {format_duration(up)}")
    except Exception as e:
        print("Uptime update error:", e)

    # Economy
    try:
        money = get_economy_money()
        if money is None:
            await safe_rename(ECONOMY_CHANNEL_ID, "💰 Economy: unknown")
        else:
            await safe_rename(ECONOMY_CHANNEL_ID, f"💰 Economy: {format_money(money)}")
    except Exception as e:
        print("Economy update error:", e)

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