import discord
from discord.ext import tasks, commands
from datetime import datetime, timedelta
import os

# --- CONFIGURAȚIE ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")  # pune tokenul în Environment Variables
VOICE_CHANNEL_ID = 1466767151267446953          # ID-ul canalului tău de voice
TIME_MULTIPLIER = 3                              # x3
# Data inițială a serverului: 5 Iunie 2026, ora 08:10
SERVER_START = datetime(2026, 6, 5, 8, 10)

LUNI = {
    1: "IAN", 2: "FEB", 3: "MAR", 4: "APR",
    5: "MAI", 6: "IUN", 7: "IUL", 8: "AUG",
    9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"
}

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- FUNCȚII ---
def timp_fs25():
    # Calculăm timpul în joc: x3 față de timpul real
    now = datetime.utcnow()
    delta = now - SERVER_START  # diferența față de startul serverului
    total_minutes = (delta.total_seconds() / 60) * TIME_MULTIPLIER
    total_minutes %= 1440  # rămâne în intervalul unei zile

    ora_joc = int(total_minutes // 60)
    minut_joc = int(total_minutes % 60)

    return f" {SERVER_START.year} | {LUNI[SERVER_START.month]} | {ora_joc:02d}:{minut_joc:02d} x{TIME_MULTIPLIER}"

# --- TASKS ---
@tasks.loop(seconds=60)
async def update_voice_name():
    canal = bot.get_channel(VOICE_CHANNEL_ID)
    if canal and isinstance(canal, discord.VoiceChannel):
        try:
            await canal.edit(name=timp_fs25())
            print(f"✅ Canal actualizat: {timp_fs25()}")
        except discord.HTTPException as e:
            print(f"❌ Eroare la editarea canalului: {e}")

# --- EVENIMENTE ---
@bot.event
async def on_ready():
    print(f"Botul este online ca {bot.user}")
    update_voice_name.start()

# --- START BOT ---
bot.run(DISCORD_TOKEN)