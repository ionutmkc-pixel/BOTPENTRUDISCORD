# bot.py — FS25 Nitrado (PS5-friendly) Discord bot
# FEATURES:
# ✅ Voice channels rename: Map / Economy / Time / Players  (every 300s)
# ✅ Text: Server ONLINE/OFFLINE (Farm Sim Bot heartbeat style)
# ✅ Text: Join/Leave + session duration
# ✅ FTP: Announce NEW mod .zip added (mods in FTP root supported)
# ✅ Manual: !gata in one channel -> bot posts in another channel (free text after field number)

import os
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
# ENV / CONFIG
# ==========================
TOKEN = os.environ.get("DISCORD_TOKEN")

# ---- NITRADO FEED ----
CODE = os.environ.get("NITRADO_CODE", "")
BASE_URL = os.environ.get("NITRADO_BASE", "http://85.190.163.102:10710/feed").rstrip("/")

if CODE:
    STATS_URL = f"{BASE_URL}/dedicated-server-stats.xml?code={CODE}"
    CAREER_URL = f"{BASE_URL}/dedicated-server-savegame.html?code={CODE}&file=careerSavegame"
else:
    # fallback (won't work without CODE)
    STATS_URL = f"{BASE_URL}/dedicated-server-stats.xml"
    CAREER_URL = f"{BASE_URL}/dedicated-server-savegame.html?file=careerSavegame"

MAX_SLOTS_FALLBACK = int(os.environ.get("MAX_SLOTS", "6"))

# ---- CHANNEL IDS (VOICE) ----
MAP_CHANNEL_ID = int(os.environ.get("MAP_CHANNEL_ID", "0"))
ECONOMY_CHANNEL_ID = int(os.environ.get("ECONOMY_CHANNEL_ID", "0"))
TIME_CHANNEL_ID = int(os.environ.get("TIME_CHANNEL_ID", "0"))
PLAYERS_CHANNEL_ID = int(os.environ.get("PLAYERS_CHANNEL_ID", "0"))

# ---- CHANNEL IDS (TEXT) ----
STATUS_TEXT_CHANNEL_ID = int(os.environ.get("STATUS_TEXT_CHANNEL_ID", "0"))
JOINLEAVE_TEXT_CHANNEL_ID = int(os.environ.get("JOINLEAVE_TEXT_CHANNEL_ID", "0"))

# ---- MANUAL FIELD ANNOUNCE ----
FIELDS_COMMAND_CHANNEL_ID = int(os.environ.get("FIELDS_COMMAND_CHANNEL_ID", "0"))
FIELDS_ANNOUNCE_CHANNEL_ID = int(os.environ.get("FIELDS_ANNOUNCE_CHANNEL_ID", "0"))

# ---- INTERVALS ----
VOICE_UPDATE_INTERVAL = int(os.environ.get("VOICE_UPDATE_INTERVAL", "300"))  # 300 = 5 min
EVENT_POLL_INTERVAL = int(os.environ.get("EVENT_POLL_INTERVAL", "30"))       # join/leave + online/offline check
MODS_POLL_INTERVAL = int(os.environ.get("MODS_POLL_INTERVAL", "600"))        # mods watcher (10 min default)

# ---- MESSAGES ----
STATUS_ON_MESSAGE = "🌾 Server ONLINE — porțile fermei sunt deschise. Spor la treabă!"
STATUS_OFF_MESSAGE = "🛠️ Server OFFLINE — pauză tehnică / restart. Revenim imediat."

JOIN_MESSAGE = "🌱 **{X}** A intrat pe server, Și ajuns la fermă — spor la semănat și recoltat! 🚜"
LEAVE_MESSAGE = "🚜 **{X}** a băgat utilajele la garaj, Și a părăsit serverul. Durata sesiunii: **{DURATA}** 🌾"

# Manual command output (your exact style)
FIELD_READY_TEMPLATE = (
    "⛰️ Terenul **{TEREN}** Cultivat cu {CULTURA} este gata de recoltat!\n"
    "Pregătiți combinele 🚜"
)

# ---- FTP MODS WATCHER ----
FTP_HOST = os.environ.get("FTP_HOST", "")
FTP_PORT = int(os.environ.get("FTP_PORT", "21"))
FTP_USER = os.environ.get("FTP_USER", "")
FTP_PASS = os.environ.get("FTP_PASS", "")
# IMPORTANT: for your case, set FTP_MODS_DIR="/" in Railway
FTP_MODS_DIR = os.environ.get("FTP_MODS_DIR", "/")

MODS_ANNOUNCE_CHANNEL_ID = int(os.environ.get("MODS_ANNOUNCE_CHANNEL_ID", "0"))
MODS_STATE_FILE = "mods_state.json"

MOD_ADDED_TEMPLATE = (
    "🧩 **Tocmai s-a adăugat un nou MOD pe server pentru a ne îmbunătăți munca!**\n"
    "Este vorba despre **{MOD}** 🚜🌾"
)

# ==========================
# DISCORD CLIENT
# ==========================
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ==========================
# STATE
# ==========================
last_server_online: bool | None = None
last_online_names: set[str] = set()
session_start: dict[str, float] = {}  # name -> time.monotonic()

# anti rate-limit rename
_last_edit: dict[int, float] = {}  # channel_id -> monotonic time

# heartbeat (Farm Sim Bot style)
_last_hb_value: int | None = None
_last_hb_change_at: float | None = None

# ==========================
# HELPERS
# ==========================
def clean_name(name: str, max_len: int = 95) -> str:
    name = re.sub(r"\s+", " ", (name or "")).strip()
    if len(name) > max_len:
        name = name[:max_len - 1] + "…"
    return name

def fetch_xml(url: str, timeout: int = 20) -> ET.Element:
    r = requests.get(url, timeout=timeout)
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
        print(f"[TEXT] Sent -> {channel_id}")
    except Exception as e:
        print("send_text error:", channel_id, e)

async def rename_channel(channel_id: int, new_name: str, cooldown_sec: int = 360) -> None:
    """
    Stable rename (reduce 429):
    - cooldown per channel (default 360s)
    """
    if channel_id <= 0:
        return
    try:
        ch = await get_channel_safe(channel_id)
    except Exception as e:
        print("rename fetch error:", channel_id, e)
        return

    new_name = clean_name(new_name)
    now = time.monotonic()
    last = _last_edit.get(channel_id, 0.0)
    if now - last < cooldown_sec:
        return

    if getattr(ch, "name", None) == new_name:
        return

    try:
        await ch.edit(name=new_name)
        _last_edit[channel_id] = now
        print(f"[VOICE] Renamed {channel_id} -> {new_name}")
        await asyncio.sleep(2)
    except Exception as e:
        print("rename error:", channel_id, e)

def to_small_caps(text: str) -> str:
    mapping = {
        "a":"ᴀ","b":"ʙ","c":"ᴄ","d":"ᴅ","e":"ᴇ","f":"ꜰ","g":"ɢ","h":"ʜ",
        "i":"ɪ","j":"ᴊ","k":"ᴋ","l":"ʟ","m":"ᴍ","n":"ɴ","o":"ᴏ","p":"ᴘ",
        "q":"ǫ","r":"ʀ","s":"ꜱ","t":"ᴛ","u":"ᴜ","v":"ᴠ","w":"ᴡ","x":"x",
        "y":"ʏ","z":"ᴢ"
    }
    return "".join(mapping.get(c, c) for c in (text or "").lower())

def format_money(value: float) -> str:
    v = int(round(value))
    return f"{v:,}".replace(",", ".") + " €"

def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h} ore si {m} minute"
    return f"{m} minute"

# ==========================
# ONLINE/OFFLINE (Farm Sim Bot style)
# ==========================
def _read_server_heartbeat() -> int | None:
    """
    Heartbeat changes while server is truly running.
    Priority:
      1) uptime (if present in <server ...>)
      2) dayTime (ms)
    """
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
    except:
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
# DATA (voice)
# ==========================
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
    root = fetch_xml(STATS_URL)
    players = [el for el in root.iter() if (el.tag or "").lower() == "player"]
    if not players:
        return 0, MAX_SLOTS_FALLBACK
    slots = len(players)
    online = sum(1 for p in players if (p.attrib.get("isUsed", "")).lower() == "true")
    online = min(online, slots)
    return online, slots

# ==========================
# PLAYER NAMES (events) - best effort
# ==========================
def extract_online_names_from_stats() -> set[str]:
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

# ==========================
# VOICE UPDATER
# ==========================
async def update_voice_channels():
    if not is_server_online():
        return

    if MAP_CHANNEL_ID:
        await rename_channel(MAP_CHANNEL_ID, f"🌾 {to_small_caps(get_map_title())}")

    if ECONOMY_CHANNEL_ID:
        money = get_money()
        if money is None:
            await rename_channel(ECONOMY_CHANNEL_ID, "💰 ᴇᴄᴏɴᴏᴍʏ -- €")
        else:
            await rename_channel(ECONOMY_CHANNEL_ID, f"💰 ᴇᴄᴏɴᴏᴍʏ {format_money(money)}")

    if TIME_CHANNEL_ID:
        await rename_channel(TIME_CHANNEL_ID, f"⏰ ᴛɪᴍᴇ {get_game_time()}")

    if PLAYERS_CHANNEL_ID:
        online, slots = get_players_online_and_slots()
        await rename_channel(PLAYERS_CHANNEL_ID, f"🚜 ᴘʟᴀʏᴇʀꜱ ᴏɴʟɪɴᴇ {online}/{slots}")

@tasks.loop(seconds=VOICE_UPDATE_INTERVAL)
async def voice_updater():
    await update_voice_channels()

# ==========================
# EVENT POLLER (online/offline + join/leave duration)
# ==========================
@tasks.loop(seconds=EVENT_POLL_INTERVAL)
async def event_poller():
    global last_server_online, last_online_names

    online_now = is_server_online()

    # server status change
    if last_server_online is None:
        last_server_online = online_now
    elif online_now != last_server_online:
        last_server_online = online_now

        if online_now:
            await send_text(STATUS_TEXT_CHANNEL_ID, STATUS_ON_MESSAGE)
        else:
            await send_text(STATUS_TEXT_CHANNEL_ID, STATUS_OFF_MESSAGE)

            # close sessions if server went offline
            now = time.monotonic()
            for name in sorted(last_online_names):
                start = session_start.pop(name, None)
                durata = "necunoscut" if start is None else format_duration(now - start)
                msg = LEAVE_MESSAGE.replace("{X}", name).replace("{DURATA}", durata)
                await send_text(JOINLEAVE_TEXT_CHANNEL_ID, msg)

            last_online_names = set()
            return

    if not online_now:
        return

    # join/leave
    try:
        current = extract_online_names_from_stats()
    except Exception as e:
        print("extract_online_names error:", e)
        return

    joined = current - last_online_names
    left = last_online_names - current
    now = time.monotonic()

    for name in sorted(joined):
        session_start[name] = now
        await send_text(JOINLEAVE_TEXT_CHANNEL_ID, JOIN_MESSAGE.replace("{X}", name))

    for name in sorted(left):
        start = session_start.pop(name, None)
        durata = "necunoscut" if start is None else format_duration(now - start)
        msg = LEAVE_MESSAGE.replace("{X}", name).replace("{DURATA}", durata)
        await send_text(JOINLEAVE_TEXT_CHANNEL_ID, msg)

    last_online_names = current

# ==========================
# MODS WATCHER (FTP) — supports ROOT dir
# ==========================
def ftp_list_mods() -> dict:
    """
    Return {filename: size} for all .zip files.
    Works even if your FTP has NO folders (mods in root).
    """
    mods = {}
    with FTP() as ftp:
        ftp.connect(FTP_HOST, FTP_PORT, timeout=20)
        ftp.login(FTP_USER, FTP_PASS)

        # ✅ IMPORTANT FIX:
        # If FTP_MODS_DIR is "/" or empty or ".", we stay in root.
        # If it's a real folder, we cd into it.
        if FTP_MODS_DIR and FTP_MODS_DIR not in ["/", ".", "./"]:
            ftp.cwd(FTP_MODS_DIR)

        for name in ftp.nlst():
            if not name.lower().endswith(".zip"):
                continue
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
    if not (FTP_HOST and FTP_USER and FTP_PASS and MODS_ANNOUNCE_CHANNEL_ID):
        return

    try:
        old = load_mods_state()
        current = ftp_list_mods()

        # first run baseline (no announcements)
        if not old:
            save_mods_state(current)
            print("[MODS] baseline saved (no announcements)")
            return

        old_keys = set(old.keys())
        cur_keys = set(current.keys())
        added = sorted(cur_keys - old_keys)

        for name in added:
            msg = MOD_ADDED_TEMPLATE.replace("{MOD}", name)
            await send_text(MODS_ANNOUNCE_CHANNEL_ID, msg)

        if added:
            save_mods_state(current)
            print(f"[MODS] added: {added}")

    except Exception as e:
        print("[MODS] watcher error:", e)

# ==========================
# MANUAL FIELD COMMAND (!gata)
# ==========================
@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # only accept commands from the command channel (if set)
    if FIELDS_COMMAND_CHANNEL_ID and message.channel.id != FIELDS_COMMAND_CHANNEL_ID:
        return

    content = (message.content or "").strip()
    if not content.lower().startswith("!gata"):
        return

    # permission: Manage Guild (admin/mod)
    if not message.author.guild_permissions.manage_guild:
        try:
            await message.reply("❌ Nu ai permisiune pentru comanda asta.")
        except:
            pass
        return

    parts = content.split()
    if len(parts) < 2:
        try:
            await message.reply("❗ Folosește: `!gata <teren> <ce vrei tu...>` (ex: `!gata 12 porumb`) ")
        except:
            pass
        return

    teren = parts[1]
    cultura_raw = " ".join(parts[2:]).strip()
    if not cultura_raw:
        cultura_raw = "CULTURĂ"

    # free text allowed; we uppercase it like your example
    cultura = cultura_raw.upper()

    if not FIELDS_ANNOUNCE_CHANNEL_ID:
        try:
            await message.reply("❌ Canalul de anunț nu e setat (FIELDS_ANNOUNCE_CHANNEL_ID).")
        except:
            pass
        return

    try:
        announce_ch = message.guild.get_channel(FIELDS_ANNOUNCE_CHANNEL_ID)
        if announce_ch is None:
            announce_ch = await client.fetch_channel(FIELDS_ANNOUNCE_CHANNEL_ID)
    except Exception as e:
        print("announce channel error:", e)
        return

    text = FIELD_READY_TEMPLATE.replace("{TEREN}", teren).replace("{CULTURA}", cultura)
    await announce_ch.send(text)

    # confirm + keep command channel clean
    try:
        await message.add_reaction("✅")
    except:
        pass

    # optional: delete command message (needs Manage Messages perm for bot)
    try:
        await message.delete()
    except:
        pass

# ==========================
# READY
# ==========================
@client.event
async def on_ready():
    global last_server_online, last_online_names
    print(f"Logged in as {client.user}")

    # init state (no spam)
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

    if not voice_updater.is_running():
        voice_updater.start()
    if not event_poller.is_running():
        event_poller.start()
    if not mods_watcher.is_running():
        mods_watcher.start()

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN lipsește din Railway Variables.")

client.run(TOKEN)