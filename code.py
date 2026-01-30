import discord
from discord.ext import tasks, commands
import requests
import xml.etree.ElementTree as ET
import os

# Intents necesare pentru Discord.py v2
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Canal Discord
CANAL_ID = 1466767151267446953

# Lunile prescurtate
luni_prescurtate = {
    1: "IAN", 2: "FEB", 3: "MAR", 4: "APR",
    5: "MAI", 6: "IUN", 7: "IUL", 8: "AUG",
    9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"
}

# Link XML server FS25
XML_URL = "http://85.190.163.102:10710/feed/dedicated-server-stats.xml?code=0c77cbd246bbdae1ad09d6ef78780e78"

@bot.event
async def on_ready():
    print(f"Bot conectat ca {bot.user}")
    post_timp_fs25.start()

def get_server_time():
    try:
        # Cerere HTTP
        r = requests.get(XML_URL, timeout=5)
        r.raise_for_status()
        root = ET.fromstring(r.content)

        # Ajustează aici în funcție de XML-ul tău real
        # Exemple comune FS25:
        # <gameDate>2026-01-30</gameDate>
        # <gameTime>12:34:56</gameTime>
        game_time = root.find(".//gameTime").text  # HH:MM:SS
        game_date = root.find(".//gameDate").text  # YYYY-MM-DD

        an, luna_num, zi = map(int, game_date.split("-"))
        ora, minut, sec = map(int, game_time.split(":"))

        # Lună prescurtată
        luna_text = luni_prescurtate[luna_num]

        # Calculează timpul x3 (ore și minute)
        timp_total_minute = ora*60 + minut
        timp_joc_total_minute = timp_total_minute * 3
        timp_joc_total_minute %= 24*60  # normalizare 24h

        ora_joc = int(timp_joc_total_minute // 60)
        minut_joc = int(timp_joc_total_minute % 60)

        return f"{an} | {luna_text} | {ora_joc:02d}:{minut_joc:02d} | x3"

    except Exception as e:
        print("Eroare la citirea XML:", e)
        return "Nu s-a putut citi timpul serverului."

# Loop automat la fiecare 5 minute
@tasks.loop(minutes=5)
async def post_timp_fs25():
    canal = bot.get_channel(CANAL_ID)
    if canal:
        mesaj = get_server_time()
        await canal.send(mesaj)

# Comandă manuală
@bot.command()
async def timp(ctx):
    await ctx.send(get_server_time())

# Token din variabilă de mediu (ENV)
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    print("ERROR: Nu ai setat variabila DISCORD_TOKEN!")
else:
    bot.run(TOKEN)