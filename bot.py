import os
import re
import requests
import xml.etree.ElementTree as ET
from io import BytesIO

import discord
from discord.ext import tasks

# ====== CONFIG ======
TOKEN = os.environ.get("DISCORD_TOKEN")

MAP_CHANNEL_ID = 1466767151267446953
TIME_CHANNEL_ID = 1467532233601585448
ECONOMY_CHANNEL_ID = 1467532195143880775

CODE = "0c77cbd246bbdae1ad09d6ef78780e78"
BASE = "http://85.190.163.102:10710/feed"

STATS_URL = f"{BASE}/dedicated-server-stats.xml?code={CODE}"
CAREER_URL = f"{BASE}/dedicated-server-savegame.html?code={CODE}&file=careerSavegame"

UPDATE_INTERVAL = 600  # 10 minute (safe)

# ====== DISCORD CLIENT ======
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ====== HELPERS ======
def download_bytes(url):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return BytesIO(r.content)

def parse_xml(xml_file):
    return ET.parse(xml_file).getroot()

def clean_name(name, max_len=95):
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > max_len:
        name = name[: max_len - 1].rstrip() + "…"
    return name

async def safe_rename(channel_id, new_name):
    ch = client.get_channel(channel_id)
    if not ch:
        return
    new_name = clean_name(new_name)
    if ch.name != new_name:
        await ch.edit(name=new_name)

# ====== DATA ======
def get_map_title():
    root = parse_xml(download_bytes(CAREER_URL))
    el = root.find(".//mapTitle")
    return el.text.strip() if el is not None else "Unknown Map"

def get_money():
    root = parse_xml(download_bytes(CAREER_URL))
    el = root.find(".//statistics/money")
    if el is None:
        return None
    return int(float(el.text))

def get_server_time():
    root = parse_xml(download_bytes(STATS_URL))
    for el in root.iter():
        if el.tag.lower() == "server":
            ms = int(el.attrib.get("dayTime", 0))
            minutes = (ms // 1000) // 60
            h = (minutes // 60) % 24
            m = minutes % 60
            return f"{h:02d}:{m:02d}"
    return "--:--"

def format_money(value):
    return f"{value:,}".replace(",", ".") + " €"

# ====== UPDATE ======
async def update_all():
    # MAP
    await safe_rename(MAP_CHANNEL_ID, f"🌾 {get_map_title()}")

    # TIME
    await safe_rename(TIME_CHANNEL_ID, f"⏰ Ora {get_server_time()}")

    # ECONOMY
    money = get_money()
    if money is not None:
        await safe_rename(ECONOMY_CHANNEL_ID, f"💰 Economy {format_money(money)}")
    else:
        await safe_rename(ECONOMY_CHANNEL_ID, "💰 Economy -- €")

@tasks.loop(seconds=UPDATE_INTERVAL)
async def loop_update():
    await update_all()

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    await update_all()
    if not loop_update.is_running():
        loop_update.start()

client.run(TOKEN)