import discord
from discord.ext import tasks, commands
from datetime import datetime, timedelta, timezone
import os

# --- CONFIGURAȚIE ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")  # Token pus în Environment Variables
VOICE_CHANNEL_ID = 1466767151267446953          # ID-ul canalului de voice
TIME_MULTIPLIER = 3                              # x3
SERVER_START = datetime(2026, 6, 5, 8, 10, tzinfo=timezone.utc)  # Start server (UTC)

LUNI = {
    1: "IAN", 2: "FEB", 3: "MAR", 4: "APR",
    5: "MAI", 6: "IUN", 7: "IUL", 8: "AUG",
    9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"
}

DAYS_PER_MONTH = 5  # o lună pe server = 5 zile

# --- BOT ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- FUNCȚII ---
def timp_fs25():
    now = datetime.now(timezone.utc)
    delta = now - SERVER_START
    total_minutes = (delta.total_seconds() / 60) * TIME_MULTIPLIER

    total_days = total_minutes // (24 * 60)
    minutes_in_day = total_minutes % (24 * 60)
    ora_joc = int(minutes_in_day // 60)
    minut_joc = int(minutes_in_day % 60)

    # Calcul luna FS25 (1 lună = 5 zile)
    luna_index = (total_days // DAYS_PER_MONTH) % 12 + 1  # 1..12
    return f"{SERVER_START.year} | {LUNI[luna_index]} | {ora_joc:02d}:{minut_joc:02d} | x{TIME_MULTIPLIER}"

# --- TASKS ---
@tasks.loop(minutes=5)
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
    await discord.utils.sleep_until(datetime.now() + timedelta(seconds=10))  # delay 10 sec
    update_voice_name.start()

# --- START BOT ---
bot.run(DISCORD_TOKEN)