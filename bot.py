import discord
from discord.ext import tasks, commands
import asyncio
import os
from datetime import datetime, timedelta

# --- CONFIGURAȚIE ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")  # pune tokenul în Environment Variables
VOICE_CHANNEL_ID = 1466767151267446953          # ID canal voice
TIME_MULTIPLIER = 3                               # afișare ×3 în nume
DAYS_PER_MONTH = 5                                # o lună FS25 = 5 zile
START_YEAR = 2026                                 # anul FS25
START_MONTH = 6                                   # luna FS25 (IUN)
START_DAY = 5                                     # ziua FS25
START_HOUR = 16                                   # ora FS25
START_MINUTE = 11                                 # minutul FS25

# Lunile în română
LUNI = {
    1: "IAN", 2: "FEB", 3: "MAR", 4: "APR",
    5: "MAI", 6: "IUN", 7: "IUL", 8: "AUG",
    9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"
}

# --- BOT ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Variabilă globală pentru timpul FS25
fs25_time = datetime(START_YEAR, START_MONTH, START_DAY, START_HOUR, START_MINUTE)

# --- FUNCȚII ---
def format_fs25_time():
    """Returnează timpul FS25 formatat pentru numele canalului"""
    global fs25_time
    an = fs25_time.year
    luna = LUNI[fs25_time.month]
    zi = fs25_time.day
    ora = fs25_time.hour
    minut = fs25_time.minute
    return f"{an} | {luna} {zi} | {ora:02d}:{minut:02d} | x{TIME_MULTIPLIER}"

def increment_fs25_time(minutes=1):
    """Crește timpul FS25 cu minutes * TIME_MULTIPLIER"""
    global fs25_time
    delta = timedelta(minutes=minutes)
    fs25_time += delta * TIME_MULTIPLIER

    # Ajustăm ziua și luna FS25 (o lună = 5 zile)
    while fs25_time.day > DAYS_PER_MONTH:
        fs25_time = fs25_time.replace(day=fs25_time.day - DAYS_PER_MONTH)
        fs25_time = fs25_time.replace(month=(fs25_time.month % 12) + 1)
        if fs25_time.month == 1:
            fs25_time = fs25_time.replace(year=fs25_time.year + 1)

async def safe_edit_channel(channel):
    """Editează numele canalului, evitând rate-limit"""
    nume_nou = format_fs25_time()
    if channel.name == nume_nou:
        return  # deja corect

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
@tasks.loop(minutes=2)  # actualizare la fiecare 2 minute pentru a evita rate-limit
async def update_voice_name():
    increment_fs25_time()  # crește timpul FS25
    canal = bot.get_channel(VOICE_CHANNEL_ID)
    if canal and isinstance(canal, discord.VoiceChannel):
        print(f"[DEBUG] Numele calculat FS25: {format_fs25_time()}")
        await safe_edit_channel(canal)

# --- EVENIMENTE ---
@bot.event
async def on_ready():
    print(f"Botul este online ca {bot.user}")
    await asyncio.sleep(5)
    update_voice_name.start()

# --- START BOT ---
bot.run(DISCORD_TOKEN)