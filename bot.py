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

def iter_candidates(root: ET.Element, needles: list[str]):
    needles = [n.lower() for n in needles]
    out = []
    for el in root.iter():
        tag = (el.tag or "").lower()
        txt = (el.text or "").strip()
        # tag matches
        if any(n in tag for n in needles):
            out.append((el.tag, txt, dict(el.attrib)))
            continue
        # attribute key matches
        for k, v in el.attrib.items():
            if any(n in k.lower() for n in needles):
                out.append((el.tag, txt, dict(el.attrib)))
                break
    return out

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
    abs_v = abs(value)
    if abs_v >= 1_000_000_000:
        return f"{value/1_000_000_000:.2f}B €"
    if abs_v >= 1_000_000:
        return f"{value/1_000_000:.2f}M €"
    if abs_v >= 1_000:
        return f"{value/1_000:.1f}K €"
    return f"{value:.0f} €"

# ====== EXTRACTORS ======
def get_map_title() -> str | None:
    root = parse_xml(download_bytes(CAREER_URL))
    title = find_text(root, ".//mapTitle")
    if title:
        return title
    mid = find_text(root, ".//mapId")
    return mid

def get_economy_money() -> float | None:
    # 1) cel mai sigur: careerSavegame -> statistics/money
    try:
        root = parse_xml(download_bytes(CAREER_URL))
        txt = find_text(root, ".//statistics/money") or find_text(root, ".//money")
        if txt:
            return float(txt)
    except Exception as e:
        print("Economy read from careerSavegame failed:", e)

    # 2) fallback: economy file (dacă are alt format)
    try:
        root2 = parse_xml(download_bytes(ECONOMY_URL))
        # încearcă orice tag numit money
        for el in root2.iter():
            if (el.tag or "").lower() == "money":
                t = (el.text or "").strip()
                if t:
                    return float(t)
        # sau orice tag care conține "money"
        cands = iter_candidates(root2, ["money", "cash", "balance"])
        for tag, txt, attrib in cands:
            if txt:
                try:
                    return float(txt)
                except:
                    pass
    except Exception as e:
        print("Economy read from economy file failed:", e)

    return None

def get_uptime_seconds() -> int | None:
    root = parse_xml(download_bytes(STATS_URL))

    # căutăm în tag-uri/atribute care pot conține uptime
    cands = iter_candidates(root, ["uptime", "running", "online", "started", "starttime", "runtime"])
    # DEBUG: afișăm în logs primele candidate
    if cands:
        print("Uptime candidates (first 10):")
        for i, (tag, txt, attrib) in enumerate(cands[:10], start=1):
            print(i, tag, "text=", txt[:50], "attrib=", attrib)

    # 1) dacă găsim un NUMĂR direct (secunde/minute)
    for tag, txt, attrib in cands:
        # text numeric?
        if txt:
            try:
                val = float(txt)
                # heuristics: dacă e mare, probabil secunde; dacă e mic, poate minute
                if val > 10_000:  # ex secunde
                    return int(val)
                if 0 <= val <= 10_000:
                    # presupunem secunde și aici (mai sigur decât minute)
                    return int(val)
            except:
                pass
        # attribute numeric?
        for k, v in attrib.items():
            if "uptime" in k.lower() or "running" in k.lower() or "runtime" in k.lower():
                try:
                    return int(float(v))
                except:
                    pass

    return None

# ====== UPDATE LOOP ======
async def do_update():
    # MAP
    try:
        m = get_map_title()
        await safe_rename(MAP_CHANNEL_ID, f"🌾 {m}" if m else "🌾 map-unknown")
    except Exception as e:
        print("Map update error:", e)

    # UPTIME
    try:
        up = get_uptime_seconds()
        if up is None:
            # nu mai punem unknown “urât”, punem online + te uiți în logs la candidates
            await safe_rename(UPTIME_CHANNEL_ID, "⏱️ Uptime: ONLINE")
        else:
            await safe_rename(UPTIME_CHANNEL_ID, f"⏱️ Uptime: {format_duration(up)}")
    except Exception as e:
        print("Uptime update error:", e)
        await safe_rename(UPTIME_CHANNEL_ID, "⏱️ Uptime: ONLINE")

    # ECONOMY
    try:
        money = get_economy_money()
        if money is None:
            await safe_rename(ECONOMY_CHANNEL_ID, "💰 Economy: unavailable")
        else:
            await safe_rename(ECONOMY_CHANNEL_ID, f"💰 Economy: {format_money(money)}")
    except Exception as e:
        print("Economy update error:", e)
        await safe_rename(ECONOMY_CHANNEL_ID, "💰 Economy: unavailable")

@tasks.loop(seconds=UPDATE_INTERVAL)
async def loop_update():
    await do_update()

@client.event
async def on_ready():
    print(f"Logged in ca {client.user}")
    await do_update()
    if not loop_update.is_running():
        loop_update.start()

client.run(TOKEN)