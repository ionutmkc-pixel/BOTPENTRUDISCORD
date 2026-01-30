import discord
from discord.ext import tasks, commands
import requests
import xml.etree.ElementTree as ET
import asyncio
import os

# --- CONFIGURAȚIE ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")  # pune tokenul în Environment Variables
VOICE_CHANNEL_ID = 1466767151267446953          # ID canal voice
TIME_MULTIPLIER = 3                               # afișare ×3 în nume
DAYS_PER_MONTH = 5                                # o lună FS25 = 5 zile
START_MONTH = 6                                   # IUN
START_YEAR = 2026

LUNI = {
    1: "IAN", 2: "FEB", 3: "MAR", 4: "APR",
    5: "MAI", 6: "IUN", 7: "IUL", 8: "AUG",
    9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"
}

# Link XML FS25
XML_URL = "http://85.190.163.102:10710/feed/dedicated-server-stats.xml?code=0c77cbd246bbdae1ad09d6ef78780e78"

# --- BOT ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- FUNCȚII ---
def timp_fs25():
    try:
        r = requests.get(XML_URL, timeout=5)
        root = ET.fromstring(r.content)

        # preluăm dayTime în milisecunde și convertim în secunde
        dayTime_attr = root.attrib.get("dayTime")
        if not dayTime_attr:
            print("❌ dayTime nu există în XML")
            return "FS25 | ???"

        day_seconds = int(dayTime_attr) // 1000  # corectăm milisecunde → secunde

        # total zile FS25
        total_days = day_seconds // 86400

        # Ziua din lună (1..5)
        zi_luna = (total_days % DAYS_PER_MONTH) + 1

        # Luna FS25
        luna_index = ((START_MONTH - 1 + (total_days // DAYS_PER_MONTH)) % 12) + 1

        # An FS25
        an_fs25 = START_YEAR + ((START_MONTH - 1 + (total_days // DAYS_PER_MONTH)) // 12)

        # Ora și minutul
        seconds_in_day = day_seconds % 86400
        ora_joc = int(seconds_in_day // 3600)
        minut_joc = int((seconds_in_day % 3600) // 60)

        # Returnăm timpul FS25 exact + ×3 doar pentru afișare
        return f"{an_fs25} | {LUNI[luna_index]} {zi_luna} | {ora_joc:02d}:{minut_joc:02d} | x{TIME_MULTIPLIER}"

    except Exception as e:
        print(f"❌ Eroare la citirea XML sau calcul: {e}")
        return "FS25 | ???"

async def safe_edit_channel(channel):
    nume_nou = timp_fs25()
    if channel.name == nume_nou:
        return

    retry = 0
    while retry < 5:
        try:
            await channel.edit(name=nume_nou)
            print(f"✅ Canal actualizat: {nume_nou}")
            return
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', 60)
                print(f"⚠️ Rate-limit, reîncerc după {retry_after:.2f} secunde")
                await asyncio.sleep(retry_after + 1)
                retry += 1
            else:
                print(f"❌ Eroare la editarea canalului: {e}")
                return

# --- TASK ---
@tasks.loop(minutes=1)
async def update_voice_name():
    canal = bot.get_channel(VOICE_CHANNEL_ID)
    if canal and isinstance(canal, discord.VoiceChannel):
        nou_nume = timp_fs25()
        print(f"[DEBUG] Numele calculat FS25: {nou_nume}")
        await safe_edit_channel(canal)

# --- EVENIMENTE ---
@bot.event
async def on_ready():
    print(f"Botul este online ca {bot.user}")
    await asyncio.sleep(5)
    update_voice_name.start()

# --- START BOT ---
bot.run(DISCORD_TOKEN)