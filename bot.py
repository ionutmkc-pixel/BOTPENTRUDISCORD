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
PLAYERS_CHANNEL_ID = 1466873332036272352  # canalul nou

MAX_SLOTS = 6

CODE = "0c77cbd246bbdae1ad09d6ef78780e78"
BASE_URL = "http://85.190.163.102:10710/feed"

STATS_URL = f"{BASE_URL}/dedicated-server-stats.xml?code={CODE}"
CAREER_URL = f"{BASE_URL}/dedicated-server-savegame.html?code={CODE}&file=careerSavegame"

UPDATE_INTERVAL = 300  # 5 minute (safe)

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
        name = name[:max_len - 1].rstrip() + "…"
    return name

async def rename_channel(channel_id: int, new_name: str) -> None:
    ch = client.get_channel(channel_id)
    if ch is None:
        print("Nu găsesc canalul:", channel_id)
        return
    new_name = clean_name(new_name)
    if getattr(ch, "name", None) != new_name:
        await ch.edit(name=new_name)
        print(f"Renamed {channel_id} -> {new_name}")

def to_small_caps(text: str) -> str:
    mapping = {
        "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ",
        "f": "ꜰ", "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ",
        "k": "ᴋ", "l": "ʟ", "m": "ᴍ", "n": "ɴ", "o": "ᴏ",
        "p": "ᴘ", "q": "ǫ", "r": "ʀ", "s": "ꜱ", "t": "ᴛ",
        "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x", "y": "ʏ", "z": "ᴢ"
    }
    out = []
    for ch in text.lower():
        out.append(mapping.get(ch, ch))
    return "".join(out)

def format_money_exact(value: float) -> str:
    v = int(round(value))
    return f"{v:,}".replace(",", ".") + " €"

# ================= DATA READERS =================
def get_map_title() -> str:
    root = fetch_xml(CAREER_URL)
    el = root.find(".//mapTitle")
    if el is not None and (el.text or "").strip():
        return el.text.strip()
    el2 = root.find(".//mapId")
    return el2.text.strip() if el2 is not None and (el2.text or "").strip() else "unknown"

def get_economy_money() -> float | None:
    root = fetch_xml(CAREER_URL)
    el = root.find(".//statistics/money")
    if el is None or not (el.text or "").strip():
        return None
    try:
        return float(el.text.strip())
    except:
        return None

def _get_server_el(stats_root: ET.Element) -> ET.Element | None:
    for el in stats_root.iter():
        if (el.tag or "").lower() == "server":
            return el
    return None

def get_game_time_hhmm() -> str:
    """
    FS25 time from stats.xml:
    <Server ... dayTime="50725127" />
    dayTime is milliseconds -> HH:MM
    """
    root = fetch_xml(STATS_URL)
    server_el = _get_server_el(root)
    if server_el is None:
        return "--:--"

    day_time = server_el.attrib.get("dayTime") or server_el.attrib.get("daytime")
    if not day_time:
        return "--:--"

    try:
        ms = int(float(day_time))
    except:
        return "--:--"

    total_minutes = (ms // 1000) // 60
    hh = (total_minutes // 60) % 24
    mm = total_minutes % 60
    return f"{hh:02d}:{mm:02d}"

def get_players_online() -> int:
    """
    Tragem numărul de jucători online din stats.xml.
    Încercăm întâi atribute pe <Server>, apoi fallback (numărăm <Player>).
    """
    root = fetch_xml(STATS_URL)
    server_el = _get_server_el(root)

    if server_el is not None:
        for key in ["players", "playerCount", "currentPlayers", "numPlayers", "connectedPlayers", "onlinePlayers"]:
            v = server_el.attrib.get(key)
            if v is not None:
                try:
                    n = int(float(v))
                    return max(0, n)
                except:
                    pass

    # fallback: numără elemente Player (dacă există)
    count = 0
    for el in root.iter():
        tag = (el.tag or "").lower()
        if tag == "player":
            count += 1

    if count > 100:
        return 0
    return count

# ================= MAIN UPDATE =================
async def update_all_channels():
    # MAP
    map_title = get_map_title()
    await rename_channel(MAP_CHANNEL_ID, f"🌾 {to_small_caps(map_title)}")

    # TIME
    await rename_channel(TIME_CHANNEL_ID, f"⏰ ᴛɪᴍᴇ {get_game_time_hhmm()}")

    # ECONOMY
    money = get_economy_money()
    if money is None:
        await rename_channel(ECONOMY_CHANNEL_ID, "💰 ᴇᴄᴏɴᴏᴍʏ -- €")
    else:
        await rename_channel(ECONOMY_CHANNEL_ID, f"💰 ᴇᴄᴏɴᴏᴍʏ {format_money_exact(money)}")

    # PLAYERS ONLINE
    online = get_players_online()
    await rename_channel(PLAYERS_CHANNEL_ID, f"🌴 ᴘʟᴀʏᴇʀꜱ ᴏɴʟɪɴᴇ {online}/{MAX_SLOTS}")

@tasks.loop(seconds=UPDATE_INTERVAL)
async def updater():
    await update_all_channels()

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    await update_all_channels()  # instant
    if not updater.is_running():
        updater.start()

client.run(TOKEN)