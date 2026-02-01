import os
import json
import math
import requests
import xml.etree.ElementTree as ET
from io import BytesIO

import discord
from discord.ext import commands, tasks

# ====== CONFIG ======
TOKEN = os.environ.get("DISCORD_TOKEN")

CHANNEL_ID = 1466767151267446953
NITRADO_URL = "http://85.190.163.102:10710/feed/dedicated-server-savegame.html?code=0c77cbd246bbdae1ad09d6ef78780e78&file=careerSavegame"

UPDATE_INTERVAL = 300  # 5 minute
DAYS_PER_MONTH = 5     # la tine: 5 zile / lună

STATE_FILE = "fs_time_state.json"  # pe Railway poate dispărea la redeploy -> dai !sync iar

MINUTES_PER_DAY = 24 * 60

# ====== DISCORD BOT ======
intents = discord.Intents.default()
intents.message_content = True  # necesar pentru comenzi !sync
bot = commands.Bot(command_prefix="!", intents=intents)

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass

state = load_state()
offset_minutes_signed = state.get("offset_minutes_signed")  # None până dai !sync

def download_savegame():
    r = requests.get(NITRADO_URL, timeout=20)
    r.raise_for_status()
    return BytesIO(r.content)

def parse_playtime_timescale(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()

    playTime_elem = root.find(".//statistics/playTime")
    timeScale_elem = root.find(".//settings/timeScale")

    if playTime_elem is None or timeScale_elem is None:
        return None

    playTime_hours = float(playTime_elem.text)
    timeScale = float(timeScale_elem.text)
    return playTime_hours, timeScale

def compute_raw_total_minutes(playTime_hours: float, timeScale: float) -> int:
    return int(math.floor(playTime_hours * timeScale * 60.0))

def minutes_to_hhmm(total_minutes: int):
    m = total_minutes % MINUTES_PER_DAY
    hh = m // 60
    mm = m % 60
    return int(hh), int(mm)

def compute_day_in_month(total_minutes: int) -> int:
    total_days = total_minutes // MINUTES_PER_DAY
    return int((total_days % DAYS_PER_MONTH) + 1)

def parse_hhmm(s: str):
    s = s.strip()
    if ":" not in s:
        raise ValueError("Format invalid. Folosește HH:MM (ex: 00:06)")
    hh_str, mm_str = s.split(":", 1)
    hh = int(hh_str)
    mm = int(mm_str)
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError("Ora trebuie între 00:00 și 23:59")
    return hh, mm

def pick_signed_offset(raw_clock_minutes: int, target_clock_minutes: int) -> int:
    # (raw + offset) % 1440 = target
    diff = (target_clock_minutes - raw_clock_minutes) % MINUTES_PER_DAY
    if diff > MINUTES_PER_DAY // 2:
        diff -= MINUTES_PER_DAY
    return int(diff)

async def update_channel_name():
    global offset_minutes_signed

    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        return

    try:
        xml_file = download_savegame()
        parsed = parse_playtime_timescale(xml_file)
        if not parsed:
            await channel.edit(name="⏰ FS: no-data")
            return

        playTime_hours, timeScale = parsed
        raw_total_minutes = compute_raw_total_minutes(playTime_hours, timeScale)

        # dacă nu e sincronizat încă, afișăm ceva util
        if offset_minutes_signed is None:
            hh, mm = minutes_to_hhmm(raw_total_minutes)
            day = compute_day_in_month(raw_total_minutes)
            await channel.edit(name=f"⏰ {hh:02d}:{mm:02d} | Zi {day} | !sync")
            return

        synced_total_minutes = raw_total_minutes + int(offset_minutes_signed)
        hh, mm = minutes_to_hhmm(synced_total_minutes)
        day = compute_day_in_month(synced_total_minutes)

        await channel.edit(name=f"⏰ {hh:02d}:{mm:02d} | Zi {day}")

    except discord.HTTPException as e:
        print("Discord HTTPException:", e)
    except Exception as e:
        print("Update error:", e)

@tasks.loop(seconds=UPDATE_INTERVAL)
async def loop_update():
    await update_channel_name()

@bot.event
async def on_ready():
    print(f"Logged in ca {bot.user}")
    await update_channel_name()  # update instant
    if not loop_update.is_running():
        loop_update.start()

@bot.command(name="sync")
async def sync(ctx, hhmm: str):
    """
    Folosești: !sync 00:06  (ora exactă pe care o vezi ACUM în joc)
    """
    global offset_minutes_signed

    try:
        xml_file = download_savegame()
        parsed = parse_playtime_timescale(xml_file)
        if not parsed:
            await ctx.reply("Nu pot citi XML-ul (playTime/timeScale lipsă).")
            return

        playTime_hours, timeScale = parsed
        raw_total_minutes = compute_raw_total_minutes(playTime_hours, timeScale)

        raw_clock = raw_total_minutes % MINUTES_PER_DAY

        hh, mm = parse_hhmm(hhmm)
        target_clock = hh * 60 + mm

        offset_minutes_signed = pick_signed_offset(raw_clock, target_clock)

        state["offset_minutes_signed"] = offset_minutes_signed
        save_state(state)

        await update_channel_name()
        await ctx.reply(f"✅ Sincronizat! (Offset {offset_minutes_signed} min)")

    except Exception as e:
        await ctx.reply(f"❌ Eroare la sync: {e}")

bot.run(TOKEN)