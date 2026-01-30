import discord
from discord.ext import tasks, commands
import requests
import xml.etree.ElementTree as ET
import os

# INTENTS
intents = discord.Intents.default()
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

def timp_fs25():
    r = requests.get(XML_URL, timeout=5)
    root = ET.fromstring(r.content)

    data = root.find(".//gameDate").text
    timp = root.find(".//gameTime").text

    an, luna, _ = map(int, data.split("-"))
    ora, minut, _ = map(int, timp.split(":"))

    total_min = (ora * 60 + minut) * 3
    total_min %= 1440

    ora_joc = total_min // 60
    min_joc = total_min % 60

    return f"🕒 FS25 | {an} | {LUNI[luna]} | {ora_joc:02d}:{min_joc:02d} x3"

@bot.event
async def on_ready():
    print("BOT PORNIT")
    update_voice_name.start()

@tasks.loop(minutes=5)
async def update_voice_name():
    canal = bot.get_channel(VOICE_CHANNEL_ID)
    if canal:
        await canal.edit(name=timp_fs25())

bot.run(os.environ["DISCORD_TOKEN"])