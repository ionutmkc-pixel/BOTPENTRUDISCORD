import os
import re
import time
import requests
import xml.etree.ElementTree as ET

import discord
from discord.ext import tasks

# ================= CONFIG =================
TOKEN = os.environ.get("DISCORD_TOKEN")  # pune tokenul în Railway env

# Voice channels (rename)
MAP_CHANNEL_ID = 1466767151267446953
ECONOMY_CHANNEL_ID = 1467532195143880775
TIME_CHANNEL_ID = 1467532233601585448
PLAYERS_CHANNEL_ID = 1466873332036272352

# Text channels (messages)
STATUS_TEXT_CHANNEL_ID = 1463573433240784948
JOINLEAVE_TEXT_CHANNEL_ID = 1463864786088624219

MAX_SLOTS_FALLBACK = 6

CODE = "0c77cbd246bbdae1ad09d6ef78780e78"
BASE_URL = "http://85.190.163.102:10710/feed"
STATS_URL = f"{BASE_URL}/dedicated-server-stats.xml?code={CODE}"
CAREER_URL = f"{BASE_URL}/dedicated-server-savegame.html?code={CODE}&file=careerSavegame"

VOICE_UPDATE_INTERVAL = 300  # 5 minute (NU schimbăm)
EVENT_POLL_INTERVAL = 30     # 30 sec (doar detect + post text)

# ===== MESAJELE TALE (FIX) =====
STATUS_ON_MESSAGE = "🟢🌾 Server ONLINE — porțile fermei sunt deschise. Spor la treabă!"
STATUS_OFF_MESSAGE = "🔴🛠️ Server OFFLINE — pauză tehnică / restart. Revenim imediat."

JOIN_MESSAGE = "🌱 **{X}** A intrat pe server, Și ajuns la fermă — spor la semănat și recoltat! 🚜"
LEAVE_MESSAGE = "🚜 **{X}** a băgat utilajele la garaj, Și a părăsit serverul. Durata sesiunii: **{DURATA}** 🌾"

# ================= DISCORD =================
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ================= STATE =================
last_server_online: bool | None = None
last_online_names: set[str] = set()
session_start: dict[str, float] = {}  # name -> time.monotonic()

# ================= HELPERS =================
def fetch_xml(url: str, timeout: int = 20) -> ET.Element:
    r = requests.get(url, timeout=timeout)
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
        return
    new_name = clean_name(new_name)
    if ch.name != new_name:
        await ch.edit(name=new_name)

async def send_text(channel_id: int, message: str) -> None:
    ch = client.get_channel(channel_id)
    if ch is None:
        return
    await ch.send(message)

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

def format_duration(seconds: int) -> str:
    if seconds < 0:
        seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h} ore si {m} minute"
    return f"{m} minute"

# ================= SERVER ONLINE/OFFLINE =================
def is_server_online() -> bool:
    try:
        r = requests.get(STATS_URL, timeout=10)
        return r.status_code == 200 and len(r.content) > 20
    except:
        return False

# ================= DATA (VOICE) =================
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
    Nitrado FS25: <player isUsed="true/false" ...> = slot
    online = count isUsed="true"
    slots = count <player>
    """
    root = fetch_xml(STATS_URL)
    players = [el for el in root.iter() if (el.tag or "").lower() == "player"]
    if not players:
        return 0, MAX_SLOTS_FALLBACK
    slots = len(players)
    online = sum(1 for p in players if (p.attrib.get("isUsed", "")).lower() == "true")
    if online > slots:
        online = slots
    return online, slots

# ================= EVENT DATA (NAMES) =================
def extract_online_names_from_stats() -> set[str]:
    """
    Extrage numele jucătorilor online din <player ... isUsed="true" ...>
    Best-effort:
      - atribute: name/userName/username/playerName/nickname
      - altfel text interior
    Dacă XML-ul tău nu conține nume, o să iasă "Player".
    """
    root = fetch_xml(STATS_URL)
    names = set()

    for p in root.iter():
        if (p.tag or "").lower() != "player":
            continue
        if (p.attrib.get("isUsed", "")).lower() != "true":
            continue

        name = None
        for key in ["name", "nickname", "userName", "username", "playerName", "playername"]:
            v = p.attrib.get(key)
            if v and v.strip():
                name = v.strip()
                break

        if not name:
            t = (p.text or "").strip()
            if t:
                name = t

        if not name:
            name = "Player"

        names.add(name)

    return names

# ================= VOICE UPDATER (NU schimbăm 300s) =================
async def update_voice_channels():
    if not is_server_online():
        return

    await rename_channel(MAP_CHANNEL_ID, f"🌾 {to_small_caps(get_map_title())}")

    money = get_money()
    if money is None:
        await rename_channel(ECONOMY_CHANNEL_ID, "💰 ᴇᴄᴏɴᴏᴍʏ -- €")
    else:
        await rename_channel(ECONOMY_CHANNEL_ID, f"💰 ᴇᴄᴏɴᴏᴍʏ {format_money(money)}")

    await rename_channel(TIME_CHANNEL_ID, f"⏰ ᴛɪᴍᴇ {get_game_time()}")

    online, slots = get_players_online_and_slots()
    await rename_channel(PLAYERS_CHANNEL_ID, f"🚜 ᴘʟᴀʏᴇʀꜱ ᴏɴʟɪɴᴇ {online}/{slots}")

@tasks.loop(seconds=VOICE_UPDATE_INTERVAL)
async def voice_updater():
    await update_voice_channels()

# ================= EVENT POLLER (30s, nu afectează voice) =================
@tasks.loop(seconds=EVENT_POLL_INTERVAL)
async def event_poller():
    global last_server_online, last_online_names

    online_now = is_server_online()

    # ONLINE/OFFLINE: trimitem doar când se schimbă
    if last_server_online is None:
        last_server_online = online_now
    elif online_now != last_server_online:
        last_server_online = online_now
        if online_now:
            await send_text(STATUS_TEXT_CHANNEL_ID, STATUS_ON_MESSAGE)
        else:
            await send_text(STATUS_TEXT_CHANNEL_ID, STATUS_OFF_MESSAGE)

            # Dacă serverul a picat, considerăm că toți au ieșit
            now = time.monotonic()
            for name in sorted(last_online_names):
                start = session_start.pop(name, None)
                durata = "necunoscut" if start is None else format_duration(int(now - start))
                msg = LEAVE_MESSAGE.replace("{X}", name).replace("{DURATA}", durata)
                await send_text(JOINLEAVE_TEXT_CHANNEL_ID, msg)

            last_online_names = set()
            return

    # dacă serverul e offline, nu verificăm jucători
    if not online_now:
        return

    # JOIN/LEAVE
    current = extract_online_names_from_stats()
    joined = current - last_online_names
    left = last_online_names - current
    now = time.monotonic()

    for name in sorted(joined):
        session_start[name] = now
        await send_text(JOINLEAVE_TEXT_CHANNEL_ID, JOIN_MESSAGE.replace("{X}", name))

    for name in sorted(left):
        start = session_start.pop(name, None)
        durata = "necunoscut" if start is None else format_duration(int(now - start))
        msg = LEAVE_MESSAGE.replace("{X}", name).replace("{DURATA}", durata)
        await send_text(JOINLEAVE_TEXT_CHANNEL_ID, msg)

    last_online_names = current

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    # init: setăm statusul inițial și jucătorii curenți fără spam
    global last_server_online, last_online_names
    last_server_online = is_server_online()

    if last_server_online:
        try:
            current = extract_online_names_from_stats()
            last_online_names = set(current)
            now = time.monotonic()
            for n in last_online_names:
                session_start[n] = now
        except:
            pass

    # rulează imediat update-ul voice o dată
    await update_voice_channels()

    if not voice_updater.is_running():
        voice_updater.start()

    if not event_poller.is_running():
        event_poller.start()

client.run(TOKEN)