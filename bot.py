import os
import re
import requests
import xml.etree.ElementTree as ET
from io import BytesIO

import discord
from discord.ext import tasks

# ====== CONFIG ======
TOKEN = os.environ.get("DISCORD_TOKEN")

CHANNEL_ID = 1466767151267446953

SAVEGAME_URL = (
    "http://85.190.163.102:10710/feed/dedicated-server-savegame.html"
    "?code=0c77cbd246bbdae1ad09d6ef78780e78&file=careerSavegame"
)

UPDATE_INTERVAL = 600  # 10 minute (safe pt rate-limit)

# ====== DISCORD CLIENT ======
intents = discord.Intents.default()
client = discord.Client(intents=intents)

def download_xml(url: str) -> BytesIO:
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return BytesIO(r.content)

def get_map_title(xml_file: BytesIO) -> str | None:
    tree = ET.parse(xml_file)
    root = tree.getroot()

    mt = root.find(".//mapTitle")
    if mt is not None and (mt.text or "").strip():
        return mt.text.strip()

    mid = root.find(".//mapId")
    if mid is not None and (mid.text or "").strip():
        return mid.text.strip()

    return None

def clean_channel_name(name: str, max_len: int = 95) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > max_len:
        name = name[: max_len - 1].rstrip() + "…"
    return name

async def update_channel_map_name():
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("Nu găsesc canalul (CHANNEL_ID).")
        return

    try:
        xml_file = download_xml(SAVEGAME_URL)
        map_title = get_map_title(xml_file)

        if not map_title:
            new_name = "🌾 harta-unknown"
        else:
            new_name = f"🌾 {map_title}"

        new_name = clean_channel_name(new_name)

        if getattr(channel, "name", None) == new_name:
            return

        await channel.edit(name=new_name)
        print("Canal actualizat:", new_name)

    except discord.HTTPException as e:
        print("Discord HTTPException:", e)
    except Exception as e:
        print("Eroare update:", e)

@tasks.loop(seconds=UPDATE_INTERVAL)
async def loop_update():
    await update_channel_map_name()

@client.event
async def on_ready():
    print(f"Logged in ca {client.user}")
    await update_channel_map_name()  # update instant
    if not loop_update.is_running():
        loop_update.start()

client.run(TOKEN)