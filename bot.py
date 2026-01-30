import discord
from discord.ext import tasks, commands
import requests
import xml.etree.ElementTree as ET
import os
from datetime import datetime, timedelta

# INTENTS
intents = discord.Intents.default()
intents.guilds = True  # necesar pentru get_channel
bot = commands.Bot(command_prefix="!", intents=intents)

# ID CANAL VOICE (al tău)
VOICE_CHANNEL_ID = 1466767151267446953

# Link XML FS25
XML_URL = "http://85.190.163.102:10710/feed/dedicated-server-stats.xml?code=0c77cbd246bbdae1ad09d6ef78780e78"

LUNI = {
    1: "IAN", 2: "FEB", 3: "MAR", 4: "APR",
    5: "MAI", 6: "IUN", 7: "IUL", 8: "AUG",
    9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"
}

TIME_MULTIPLIER = 3  # x3

def timp_fs25():
    try:
        r = requests.get(XML_URL, timeout=5)
        root = ET.fromstring(r.content)

        game_date_elem = root.find(".//gameDate")
        game_time_elem = root.find(".//gameTime")

        if game_date_elem is None or game_time_elem is None:
            raise ValueError("Tag gameDate sau gameTime nu există în XML")

        data = game_date_elem.text
        timp = game_time_elem.text

        an, luna, _ = map(int, data.split("-"))
        ora, minut, _ = map(int, timp.split(":"))

        total_min = (ora * 60 + minut) * TIME_MULTIPLIER
        total_min %= 1440  # 24h în minute

        ora_joc = total_min // 60
        min_joc = total_min % 60

        return f"🕒 FS25 | {an} | {LUNI[luna]} | {ora_joc:02d}:{min_joc:02d} x{TIME_MULTIPLIER}"

    except Exception as e:
        print(f"❌ Eroare la citirea XML sau calcul: {e}")
        # fallback: timpul local
        now = datetime.utcnow() + timedelta(hours=(TIME_MULTIPLIER-1))
        return f"🕒 FS25 | {now.year} | {LUNI[now.month]} | {now.hour:02d}:{now.minute:02d} x{TIME_MULTIPLIER}"

@bot.event
async def on_ready():
    print(f"BOT PORNIT ca {bot.user}")
    update_voice_name.start()

@tasks.loop(minutes=1)
async def update_voice_name():
    canal = bot.get_channel(VOICE_CHANNEL_ID)
    if canal and isinstance(canal, discord.VoiceChannel):
        try:
            new_name = timp_fs25()
            await canal.edit(name=new_name)
            print(f"✅ Canal actualizat: {new_name}")
        except discord.HTTPException as e:
            print(f"❌ Eroare la editarea canalului: {e}")

# Rulează botul
bot.run(os.environ["DISCORD_TOKEN"])