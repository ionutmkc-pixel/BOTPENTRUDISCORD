import discord
from discord.ext import tasks
import requests
import xml.etree.ElementTree as ET
from io import BytesIO
import os

# ---------------- CONFIG ----------------
TOKEN = os.environ.get("DISCORD_TOKEN")  # token Railway ENV
CHANNEL_ID = 1466767151267446953  # canalul tau
NITRADO_URL = "http://85.190.163.102:10710/feed/dedicated-server-savegame.html?code=0c77cbd246bbdae1ad09d6ef78780e78&file=careerSavegame"

UPDATE_INTERVAL = 300  # 5 minute
HOURS_PER_DAY = 24
DAYS_PER_SEASON = 5  # serverul tau are 5 zile pe lună
SEASONS = ["Primăvară", "Vară", "Toamnă", "Iarnă"]
SEASON_EMOJI = ["🌱", "☀️", "🍂", "❄️"]

# Lunile pe server pentru afișare
MONTHS = ["Sep", "Oct", "Nov", "Dec"]

# ---------------- CLIENT DISCORD ----------------
intents = discord.Intents.default()
client = discord.Client(intents=intents)

# ---------------- FUNCȚII ----------------
def download_savegame():
    try:
        response = requests.get(NITRADO_URL)
        response.raise_for_status()
        return BytesIO(response.content)
    except Exception as e:
        print("Eroare la descărcare savegame:", e)
        return None

def parse_time(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()
    
    playTime_elem = root.find(".//statistics/playTime")
    timeScale_elem = root.find(".//settings/timeScale")
    
    if playTime_elem is None or timeScale_elem is None:
        return None
    
    playTime = float(playTime_elem.text)
    timeScale = float(timeScale_elem.text)
    
    # calculăm orele totale din joc
    game_hours_total = playTime * timeScale
    
    hour = int(game_hours_total % HOURS_PER_DAY)
    minute = int((game_hours_total % 1) * 60)
    
    total_days = int(game_hours_total // HOURS_PER_DAY)
    day = (total_days % DAYS_PER_SEASON) + 1
    
    # calculăm sezon și emoji
    season_index = (total_days // DAYS_PER_SEASON) % len(SEASONS)
    season = SEASONS[season_index]
    season_emoji = SEASON_EMOJI[season_index]
    
    # calculăm luna
    month_index = (total_days // DAYS_PER_SEASON) % len(MONTHS)
    month = MONTHS[month_index]
    
    return hour, minute, day, month, season, season_emoji

async def update_fs25_channel():
    channel = client.get_channel(CHANNEL_ID)
    xml_file = download_savegame()
    if xml_file:
        result = parse_time(xml_file)
        if result:
            hour, minute, day, month, season, season_emoji = result
            new_name = f"⏰ {hour:02d}:{minute:02d} | Zi {day} | {month} | {season_emoji} {season}"
            try:
                await channel.edit(name=new_name)
                print(f"Canal actualizat: {new_name}")
            except discord.errors.HTTPException as e:
                print("Eroare la edit canal (posibil rate limit):", e)
    else:
        print("Nu am putut descărca savegame-ul.")

# ---------------- TASK PERIODIC ----------------
@tasks.loop(seconds=UPDATE_INTERVAL)
async def fs25_loop():
    await update_fs25_channel()

@client.event
async def on_ready():
    print(f'Logged in ca {client.user}')
    # update instant la pornire
    await update_fs25_channel()
    # apoi periodic
    fs25_loop.start()

client.run(TOKEN)