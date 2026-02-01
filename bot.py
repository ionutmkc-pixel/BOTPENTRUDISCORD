import os
import re
import requests
import xml.etree.ElementTree as ET

import discord
from discord.ext import tasks

# ================= CONFIG =================
TOKEN = os.environ.get("DISCORD_TOKEN")

MAP_CHANNEL_ID = 1466767151267446953
TIME_CHANNEL_ID = 1467532233601585448
ECONOMY_CHANNEL_ID = 1467532195143880775

CODE = "0c77cbd246bbdae1ad09d6ef78780e78"
BASE_URL = "http://85.190.163.102:10710/feed"

STATS_URL = f"{BASE_URL}/dedicated-server-stats.xml?code={CODE}"
CAREER_URL = f"{BASE_URL}/dedicated-server-savegame.html?code={CODE}&file=careerSavegame"

UPDATE_INTERVAL = 300  # 5 minute

# ================= DISCORD =================
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ================= HELPERS =================
def fetch_xml(url):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return ET.fromstring(r.content)

def clean_name(name, max_len=95):
    name = re.sub(r"\s+", " ", name).strip()
    return name if len(name) <= max_len else name[:max_len - 1] + "…"

async def rename(channel_id, name):
    ch = client.get_channel(channel_id)
    if not ch:
        return
    name = clean_name(name)
    if ch.name != name:
        await ch.edit(name=name)

# ================= DATA =================
def get_map_name():
    root = fetch_xml(CAREER_URL)
    el = root.find(".//mapTitle")
    return el.text.strip() if el is not None else "Unknown Map"

def get_money():
    root = fetch_xml(CAREER_URL)
    el = root.find(".//statistics/money")
    if el is None:
        return None
    return int(float(el.text))

def format_money(value):
    return f"{value:,}".replace(",", ".") + " €"

def get_game_time():
    root = fetch_xml(STATS_URL)
    for el in root.iter():
        if el.tag.lower() == "server":
            ms = int(el.attrib.get("dayTime", 0))
            minutes = (ms // 1000) // 60
            h = (minutes // 60) % 24
            m = minutes % 60
            return f"{h:02d}:{m:02d}"
    return "--:--"

# ================= UPDATE =================
async def update_channels():
    # MAP
    await rename(MAP_CHANNEL_ID, f"🌾 {get_map_name()}")

    # TIME (etichetă schimbată)
    await rename(TIME_CHANNEL_ID, f"⏰ Time {get_game_time()}")

    # ECONOMY
    money = get_money()
    if money is not None:
        await rename(ECONOMY_CHANNEL_ID, f"💰 Economy {format_money(money)}")
    else:
        await rename(ECONOMY_CHANNEL_ID, "💰 Economy -- €")

@tasks.loop(seconds=UPDATE_INTERVAL)
async def updater():
    await update_channels()

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    await update_channels()
    if not updater.is_running():
        updater.start()

client.run(TOKEN)