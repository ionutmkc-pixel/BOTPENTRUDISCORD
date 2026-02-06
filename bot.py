import oss
import re
import time
import json
import asyncio
import requests
import xml.etree.ElementTree as ET
from ftplib import FTP

import discord
from discord.ext import tasks

# ==========================
# ENV
# ==========================
TOKEN = os.environ.get("DISCORD_TOKEN", "")

NITRADO_CODE = os.environ.get("NITRADO_CODE", "")
NITRADO_BASE = os.environ.get("NITRADO_BASE", "http://85.190.163.102:10710/feed").rstrip("/")

STATS_URL = f"{NITRADO_BASE}/dedicated-server-stats.xml?code={NITRADO_CODE}"
CAREER_URL = f"{NITRADO_BASE}/dedicated-server-savegame.html?code={NITRADO_CODE}&file=careerSavegame"

MAX_SLOTS = int(os.environ.get("MAX_SLOTS", "6"))

# Voice channels
MAP_CHANNEL_ID = int(os.environ.get("MAP_CHANNEL_ID", "0"))
ECONOMY_CHANNEL_ID = int(os.environ.get("ECONOMY_CHANNEL_ID", "0"))
TIME_CHANNEL_ID = int(os.environ.get("TIME_CHANNEL_ID", "0"))
PLAYERS_CHANNEL_ID = int(os.environ.get("PLAYERS_CHANNEL_ID", "0"))

# Text channels
STATUS_TEXT_CHANNEL_ID = int(os.environ.get("STATUS_TEXT_CHANNEL_ID", "0"))
JOINLEAVE_TEXT_CHANNEL_ID = int(os.environ.get("JOINLEAVE_TEXT_CHANNEL_ID", "0"))

# Manual command channels
FIELDS_COMMAND_CHANNEL_ID = int(os.environ.get("FIELDS_COMMAND_CHANNEL_ID", "0"))
FIELDS_ANNOUNCE_CHANNEL_ID = int(os.environ.get("FIELDS_ANNOUNCE_CHANNEL_ID", "0"))

# Mods announce
FTP_HOST = os.environ.get("FTP_HOST", "")
FTP_PORT = int(os.environ.get("FTP_PORT", "21"))
FTP_USER = os.environ.get("FTP_USER", "")
FTP_PASS = os.environ.get("FTP_PASS", "")
FTP_MODS_DIR = os.environ.get("FTP_MODS_DIR", "/")  # your case: "/"
MODS_ANNOUNCE_CHANNEL_ID = int(os.environ.get("MODS_ANNOUNCE_CHANNEL_ID", "0"))
MODS_STATE_FILE = "mods_state.json"

# intervals
VOICE_UPDATE_INTERVAL = int(os.environ.get("VOICE_UPDATE_INTERVAL", "300"))
EVENT_POLL_INTERVAL = int(os.environ.get("EVENT_POLL_INTERVAL", "30"))
MODS_POLL_INTERVAL = int(os.environ.get("MODS_POLL_INTERVAL", "600"))

# messages
STATUS_ON_MESSAGE = "🌾 Server ONLINE — porțile fermei sunt deschise. Spor la treabă!"
STATUS_OFF_MESSAGE = "🛠️ Server OFFLINE — pauză tehnică / restart. Revenim imediat."

JOIN_MESSAGE = "🌱 **{X}** A intrat pe server, Și a început treaba — spor la semănat și recoltat! 🚜"
LEAVE_MESSAGE = "🚜 **{X}** a băgat utilajele la garaj, Și a părăsit serverul. Durata sesiunii: **{DURATA}** 🌾"

FIELD_READY_TEMPLATE = (
    "⛰️ Terenul **{TEREN}** Cultivat cu {CULTURA} este gata de recoltat!\n"
    "Pregătiți combinele 🚜"
)

MOD_ADDED_TEMPLATE = (
    "🧩 **Tocmai s-a adăugat un nou MOD pe server pentru a ne îmbunătăți munca!**\n"
    "Este vorba despre **{MOD}** 🚜🌾"
)

# ==========================
# DISCORD
# ==========================
intents = discord.Intents.default()
intents.message_content = True  # IMPORTANT for !gata
intents.messages = True
client = discord.Client(intents=intents)

# ==========================
# STATE
# ==========================
_last_edit = {}
last_server_online = None
last_online_names = set()
session_start = {}

_last_hb_value = None
_last_hb_change_at = None

# single requests session
HTTP = requests.Session()

# ==========================
# HELPERS
# ==========================
def clean_name(name: str, max_len: int = 95) -> str:
    name = re.sub(r"\s+", " ", (name or "")).strip()
    return name[:max_len] if len(name) <= max_len else name[:max_len - 1] + "…"

def fetch_xml(url: str, timeout: int = 15) -> ET.Element:
    r = HTTP.get(url, timeout=timeout)
    r.raise_for_status()
    return ET.fromstring(r.content)

async def get_channel_safe(channel_id: int):
    ch = client.get_channel(channel_id)
    if ch is None:
        ch = await client.fetch_channel(channel_id)
    return ch

async def send_text(channel_id: int, message: str) -> None:
    if channel_id <= 0:
        return
    try:
        ch = await get_channel_safe(channel_id)
        await ch.send(message)
        print(f"[TEXT] -> {channel_id}")
    except Exception as e:
        print("[TEXT] error:", channel_id, e)

async def rename_channel(channel_id: int, new_name: str, cooldown_sec: int = 360) -> None:
    if channel_id <= 0:
        return
    now = time.monotonic()
    last = _last_edit.get(channel_id, 0.0)
    if now - last < cooldown_sec:
        return

    try:
        ch = await get_channel_safe(channel_id)
        new_name = clean_name(new_name)
        if ch.name == new_name:
            return
        await ch.edit(name=new_name)
        _last_edit[channel_id] = now
        print(f"[VOICE] {channel_id} -> {new_name}")
        await asyncio.sleep(2)
    except Exception as e:
        print("[VOICE] rename error:", channel_id, e)

def to_small_caps(text: str) -> str:
    mapping = {
        "a":"ᴀ","b":"ʙ","c":"ᴄ","d":"ᴅ","e":"ᴇ","f":"ꜰ","g":"ɢ","h":"ʜ",
        "i":"ɪ","j":"ᴊ","k":"ᴋ","l":"ʟ","m":"ᴍ","n":"ɴ","o":"ᴏ","p":"ᴘ",
        "q":"ǫ","r":"ʀ","s":"ꜱ","t":"ᴛ","u":"ᴜ","v":"ᴠ","w":"ᴡ","x":"x",
        "y":"ʏ","z":"ᴢ"
    }
    return "".join(mapping.get(c, c) for c in (text or "").lower())

def format_money(v: float) -> str:
    v = int(round(v))
    return f"{v:,}".replace(",", ".") + " €"

def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h} ore si {m} minute" if h else f"{m} minute"

# ==========================
# ONLINE/OFFLINE heartbeat
# ==========================
def _read_server_heartbeat() -> int | None:
    try:
        root = fetch_xml(STATS_URL, timeout=10)
        for el in root.iter():
            if (el.tag or "").lower() == "server":
                up = el.attrib.get("uptime") or el.attrib.get("upTime") or el.attrib.get("up_time")
                if up is not None:
                    return int(float(up))
                dt = el.attrib.get("dayTime") or el.attrib.get("daytime")
                if dt is not None:
                    return int(float(dt))
        return None
    except Exception as e:
        print("[HB] error:", e)
        return None

def is_server_online(stale_seconds: int = 90) -> bool:
    global _last_hb_value, _last_hb_change_at
    hb = _read_server_heartbeat()
    now = time.monotonic()
    if hb is None:
        return False

    if _last_hb_value is None:
        _last_hb_value = hb
        _last_hb_change_at = now
        return True

    if hb != _last_hb_value:
        _last_hb_value = hb
        _last_hb_change_at = now
        return True

    if _last_hb_change_at is None:
        _last_hb_change_at = now
        return True

    return (now - _last_hb_change_at) <= stale_seconds

# ==========================
# DATA
# ==========================
def get_map_title() -> str:
    root = fetch_xml(CAREER_URL)
    el = root.find(".//mapTitle")
    if el is not None and (el.text or "").strip():
        return el.text.strip()
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
            ms = int(float(el.attrib.get("dayTime", "0")))
            mins = (ms // 1000) // 60
            hh = (mins // 60) % 24
            mm = mins % 60
            return f"{hh:02d}:{mm:02d}"
    return "--:--"

def get_players_online_and_slots() -> tuple[int, int]:
    root = fetch_xml(STATS_URL)
    players = [el for el in root.iter() if (el.tag or "").lower() == "player"]
    if not players:
        return 0, MAX_SLOTS
    slots = len(players)
    online = sum(1 for p in players if (p.attrib.get("isUsed", "")).lower() == "true")
    return min(online, slots), slots

def extract_online_names_from_stats() -> set[str]:
    root = fetch_xml(STATS_URL)
    names = set()
    for p in root.iter():
        if (p.tag or "").lower() != "player":
            continue
        if (p.attrib.get("isUsed", "")).lower() != "true":
            continue
        name = p.attrib.get("name") or p.attrib.get("username") or p.attrib.get("playerName")
        if not name:
            name = (p.text or "").strip() or "Player"
        names.add(name)
    return names

# ==========================
# TASKS
# ==========================
@tasks.loop(seconds=VOICE_UPDATE_INTERVAL)
async def voice_updater():
    print("[TICK] voice_updater")
    try:
        if not is_server_online():
            print("[VOICE] server offline -> skip")
            return

        if MAP_CHANNEL_ID:
            await rename_channel(MAP_CHANNEL_ID, f"🌾 {to_small_caps(get_map_title())}")
        if ECONOMY_CHANNEL_ID:
            m = get_money()
            await rename_channel(ECONOMY_CHANNEL_ID, f"💰 ᴇᴄᴏɴᴏᴍʏ {format_money(m)}" if m is not None else "💰 ᴇᴄᴏɴᴏᴍʏ -- €")
        if TIME_CHANNEL_ID:
            await rename_channel(TIME_CHANNEL_ID, f"⏰ ᴛɪᴍᴇ {get_game_time()}")
        if PLAYERS_CHANNEL_ID:
            on, sl = get_players_online_and_slots()
            await rename_channel(PLAYERS_CHANNEL_ID, f"🚜 ᴘʟᴀʏᴇʀꜱ ᴏɴʟɪɴᴇ {on}/{sl}")
    except Exception as e:
        print("[VOICE] task error:", e)

@tasks.loop(seconds=EVENT_POLL_INTERVAL)
async def event_poller():
    global last_server_online, last_online_names
    print("[TICK] event_poller")

    try:
        online_now = is_server_online()

        if last_server_online is None:
            last_server_online = online_now
        elif online_now != last_server_online:
            last_server_online = online_now
            await send_text(STATUS_TEXT_CHANNEL_ID, STATUS_ON_MESSAGE if online_now else STATUS_OFF_MESSAGE)

            if not online_now:
                now = time.monotonic()
                for name in sorted(last_online_names):
                    start = session_start.pop(name, None)
                    durata = "necunoscut" if start is None else format_duration(now - start)
                    await send_text(JOINLEAVE_TEXT_CHANNEL_ID, LEAVE_MESSAGE.replace("{X}", name).replace("{DURATA}", durata))
                last_online_names = set()
                return

        if not online_now:
            return

        current = extract_online_names_from_stats()
        joined = current - last_online_names
        left = last_online_names - current
        now = time.monotonic()

        for name in sorted(joined):
            session_start[name] = now
            await send_text(JOINLEAVE_TEXT_CHANNEL_ID, JOIN_MESSAGE.replace("{X}", name))

        for name in sorted(left):
            start = session_start.pop(name, None)
            durata = "necunoscut" if start is None else format_duration(now - start)
            await send_text(JOINLEAVE_TEXT_CHANNEL_ID, LEAVE_MESSAGE.replace("{X}", name).replace("{DURATA}", durata))

        last_online_names = current
    except Exception as e:
        print("[EVENT] task error:", e)

def ftp_list_mods() -> dict:
    mods = {}
    with FTP() as ftp:
        ftp.connect(FTP_HOST, FTP_PORT, timeout=20)
        ftp.login(FTP_USER, FTP_PASS)

        # root support
        if FTP_MODS_DIR and FTP_MODS_DIR not in ["/", ".", "./"]:
            ftp.cwd(FTP_MODS_DIR)

        for name in ftp.nlst():
            if name.lower().endswith(".zip"):
                try:
                    size = ftp.size(name) or 0
                except:
                    size = 0
                mods[name] = int(size)
    return mods

def load_mods_state() -> dict:
    try:
        with open(MODS_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_mods_state(state: dict) -> None:
    with open(MODS_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)

@tasks.loop(seconds=MODS_POLL_INTERVAL)
async def mods_watcher():
    print("[TICK] mods_watcher")
    if not (FTP_HOST and FTP_USER and FTP_PASS and MODS_ANNOUNCE_CHANNEL_ID):
        print("[MODS] missing env -> skip")
        return

    try:
        old = load_mods_state()
        current = ftp_list_mods()

        if not old:
            save_mods_state(current)
            print("[MODS] baseline saved (no announcements)")
            return

        added = sorted(set(current.keys()) - set(old.keys()))
        for name in added:
            await send_text(MODS_ANNOUNCE_CHANNEL_ID, MOD_ADDED_TEMPLATE.replace("{MOD}", name))

        if added:
            save_mods_state(current)
            print("[MODS] added:", added)
    except Exception as e:
        print("[MODS] task error:", e)

# ==========================
# COMMAND (!gata)
# ==========================
@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # DEBUG: show we receive messages
    print("[MSG]", "channel=", message.channel.id, "content=", repr(message.content))

    # only from command channel
    if FIELDS_COMMAND_CHANNEL_ID and message.channel.id != FIELDS_COMMAND_CHANNEL_ID:
        return

    content = (message.content or "").strip()
    if not content.lower().startswith("!gata"):
        return

    # permission
    if not message.author.guild_permissions.manage_guild:
        await message.reply("❌ Nu ai permisiune pentru comanda asta.")
        return

    parts = content.split()
    if len(parts) < 2:
        await message.reply("❗ Folosește: `!gata <teren> <ce vrei tu...>`")
        return

    teren = parts[1]
    cultura_raw = " ".join(parts[2:]).strip() or "CULTURĂ"
    cultura = cultura_raw.upper()

    if not FIELDS_ANNOUNCE_CHANNEL_ID:
        await message.reply("❌ FIELDS_ANNOUNCE_CHANNEL_ID nu e setat.")
        return

    announce = message.guild.get_channel(FIELDS_ANNOUNCE_CHANNEL_ID)
    if announce is None:
        announce = await client.fetch_channel(FIELDS_ANNOUNCE_CHANNEL_ID)

    await announce.send(FIELD_READY_TEMPLATE.replace("{TEREN}", teren).replace("{CULTURA}", cultura))

    try:
        await message.add_reaction("✅")
    except:
        pass

    # optional delete
    try:
        await message.delete()
    except:
        pass

# ==========================
# READY
# ==========================
@client.event
async def on_ready():
    print(f"[READY] Logged in as {client.user}")
    print("[READY] URLs:", STATS_URL, CAREER_URL)

    # Start tasks safely
    if not voice_updater.is_running():
        voice_updater.start()
    if not event_poller.is_running():
        event_poller.start()
    if not mods_watcher.is_running():
        mods_watcher.start()

    print("[READY] tasks started")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN missing in Railway Variables.")
if not NITRADO_CODE:
    print("[WARN] NITRADO_CODE is empty -> stats/career will fail.")

client.run(TOKEN)