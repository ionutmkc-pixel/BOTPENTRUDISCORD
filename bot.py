import discord
from discord.ext import tasks, commands
from datetime import datetime, timedelta, timezone
import asyncio
import os

# --- CONFIGURAȚIE ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
VOICE_CHANNEL_ID = 1466767151267446953
TIME_MULTIPLIER = 3
SERVER_START = datetime(2026, 6, 5, 8, 10, tzinfo=timezone.utc)  # Start server (UTC)
DAYS_PER_MONTH = 5  # o lună FS25 = 5 zile

LUNI = {
    1: "IAN", 2: "FEB", 3: "MAR", 4: "APR",
    5: "MAI", 6: "IUN", 7: "IUL", 8: "AUG",
    9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"
}

# --- BOT ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- FUNCȚII ---
def timp_fs25():
    now = datetime.now(timezone.utc)
    delta = now - SERVER_START
    total_minutes = (delta.total_seconds() / 60) * TIME_MULTIPLIER

    # Total zile FS25
    total_days = int(total_minutes // (24*60))

    # Ziua din lună FS25 (1..5)
    zi_luna = (total_days % DAYS_PER_MONTH) + 1

    # Luna FS25 (1..12)
    luna_index = ((total_days // DAYS_PER_MONTH) % 12) + 1

    # Ora și minutul în joc
    minutes_in_day = total_minutes % (24*60)
    ora_joc = int(minutes_in_day // 60)
    minut_joc = int(minutes_in_day % 60)

    return f"{SERVER_START.year} | {LUNI[luna_index]} {zi_luna} | {ora_joc:02d}:{minut_joc:02d} | x{TIME_MULTIPLIER}"

async def safe_edit_channel(channel):
    """Editează canalul cu retry la 429."""
    retry = 0
    while retry < 5:
        try:
            await channel.edit(name=timp_fs25())
            print(f"✅ Canal actualizat: {timp_fs25()}")
            return
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limit
                retry_after = getattr(e, 'retry_after', 60)
                print(f"⚠️ Rate-limit, reîncerc după {retry_after} secunde")
                await asyncio.sleep(retry_after + 1)
                retry += 1
            else:
                print(f"❌ Eroare la editarea canalului: {e}")
                return

# --- TASKS ---
@tasks.loop(minutes=5)
async def update_voice_name():
    canal = bot.get_channel(VOICE_CHANNEL_ID)
    if canal and isinstance(canal, discord.VoiceChannel):
        await safe_edit_channel(canal)

# --- EVENIMENTE ---
@bot.event
async def on_ready():
    print(f"Botul este online ca {bot.user}")
    # Delay la start ca să evităm primul PATCH imediat
    await asyncio.sleep(10)
    update_voice_name.start()

# --- START BOT ---
bot.run(DISCORD_TOKEN)