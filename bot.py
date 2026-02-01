import os
import re
import requests
import xml.etree.ElementTree as ET

import discord
from discord.ext import tasks

# ================= CONFIG =================
TOKEN = os.environ.get("DISCORD_TOKEN")

MAP_CHANNEL_ID = 1466767151267446953
ECONOMY_CHANNEL_ID = 1467532195143880775
TIME_CHANNEL_ID = 1467532233601585448
PLAYERS_CHANNEL_ID = 1466873332036272352

MAX_SLOTS_FALLBACK = 6  # folosit doar dacă XML nu are lista de sloturi <player>

CODE = "0c77cbd246bbdae1ad09d6ef78780e78"
BASE_URL = "http://85.190.163.102:10710/feed"

STATS_URL = f"{BASE_URL}/dedicated-server-stats.xml?code={CODE}"
CAREER_URL = f"{BASE_URL}/dedicated-server-savegame.html?code={CODE}&file=careerSavegame"

UPDATE_INTERVAL = 300  # 5 minute (pentru toate canalele)

# ================= DISCORD =================
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ================= HELPERS =================
def fetch_xml(url: str) -> ET.Element:
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return ET.fromstring(r.content)

def clean_name(name: str, max_len: int = 95) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > max_len:
        name = name[:max_len - 1] + "…"
    return name

async def rename_channel(channel_id: int, new_name: str) -> None:
    ch = client.get_channel(channel_id)
    if ch is None:
        print("Nu găsesc canalul:", channel_id)
        return
    new_name = clean_name(new_name)
    if ch.name != new_name:
        await ch.edit(name=new_name)
        print(f"Renamed {channel_id} -> {new_name}")

def to_small_caps(text: str) -> str:
    mapping = {
        "a":"ᴀ","b":"ʙ","c":"ᴄ","d":"ᴅ","e":"ᴇ","f":"ꜰ","g":"ɢ","h":"ʜ",
        "i":"ɪ","j":"ᴊ","k":"ᴋ","l":"ʟ","m":"ᴍ","n":"ɴ","o":"ᴏ","p":"ᴘ",
        "q":"ǫ","r":"ʀ","s":"ꜱ","t":"ᴛ","u":"ᴜ","v":"ᴠ","w":"ᴡ","x":"x",
        "y":"ʏ","z":"ᴢ"
    }
    return "".join(mapping.get(c, c) for c in text.lower())

def format_money(value: float) -> str:
    v = int(round(value))
    return f"{v:,}".replace(",", ".") + " €"

# ================= DATA =================
def get_map_title() -> str:
    root = fetch_xml(CAREER_URL)
    el = root.find(".//mapTitle")
    if el is not None and (el.text or "").strip():
        return el.text.strip()
    el2 = root.find(".//mapId")
    if el2 is not None and (el2.text or "").strip():
        return el2.text.strip()
    return "unknown"

def get_money() -> float | None:
    root = fetch_xml(CAREER_URL)
    el = root.find(".//statistics/money")
    if el is None or not (el.text or "").strip():
        return None
    try:
        return float(el.text.strip())
    except:
        return None

def get_game_time() -> str:
    root = fetch_xml(STATS_URL)
    for el in root.iter():
        if (el.tag or "").lower() == "server":
            try:
                ms = int(float(el.attrib.get("dayTime", "0")))
            except:
                return "--:--"
            total_minutes = (ms // 1000) // 60
            hh = (total_minutes // 60) % 24
            mm = total_minutes % 60
            return f"{hh:02d}:{mm:02d}"
    return "--:--"

def get_players_online_and_slots() -> tuple[int, int]:
    """
    Corect pentru Nitrado FS25:
    - de obicei există <player> slots
    - fiecare slot are isUsed="true/false"
    """
    root = fetch_xml(STATS_URL)

    players = []
    for el in root.iter():
        if (el.tag or "").lower() == "player":
            players.append(el)

    if not players:
        # nu există slot list -> nu putem citi exact online
        return 0, MAX_SLOTS_FALLBACK

    slots = len(players)
    online = 0
    for p in players:
        if (p.attrib.get("isUsed", "")).lower() == "true":
            online += 1

    if online < 0:
        online = 0
    if online > slots:
        online = slots

    return online, slots

# ================= UPDATE =================
async def update_all():
    # MAP
    await rename_channel(
        MAP_CHANNEL_ID,
        f"🌾 {to_small_caps(get_map_title())}"
    )

    # ECONOMY
    money = get_money()
    if money is None:
        await rename_channel(ECONOMY_CHANNEL_ID, "💰 ᴇᴄᴏɴᴏᴍʏ -- €")
    else:
        await rename_channel(ECONOMY_CHANNEL_ID, f"💰 ᴇᴄᴏɴᴏᴍʏ {format_money(money)}")

    # TIME
    await rename_channel(
        TIME_CHANNEL_ID,
        f"⏰ ᴛɪᴍᴇ {get_game_time()}"
    )

    # PLAYERS ONLINE (emoji schimbat la 🚜 cum ai cerut)
    online, slots = get_players_online_and_slots()
    await rename_channel(
        PLAYERS_CHANNEL_ID,
        f"🚜 ᴘʟᴀʏᴇʀꜱ ᴏɴʟɪɴᴇ {online}/{slots}"
    )

@tasks.loop(seconds=UPDATE_INTERVAL)
async def updater():
    await update_all()

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    await update_all()  # update instant
    if not updater.is_running():
        updater.start()

client.run(TOKEN)