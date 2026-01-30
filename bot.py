import discord
from discord.ext import tasks, commands
from datetime import datetime, timedelta, timezone
import asyncio
import os

# --- CONFIGURAȚIE ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")  # Token pus în Environment Variables
VOICE_CHANNEL_ID = 1466767151267446953           # ID canal voice
TIME_MULTIPLIER = 3                              # x3
SERVER_START = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)  # Start FS25 la ora 12:00
DAYS_PER_MONTH = 5                                # O lună FS25 = 5 zile

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

    # Dacă suntem înainte de startul FS25 → rămâne ora de start
    if now < SERVER_START:
        return f"2026 | IUN 5 | 12:00 | x{TIME_MULTIPLIER}"

    # Diferența de timp în minute × TIME_MULTIPLIER
    delta = now - SERVER_START
    total_minutes = delta.total_seconds() / 60 * TIME_MULTIPLIER

    # Total zile FS25 de la start
    total_days = int(total_minutes // (24*60))

    # Ziua din lună FS25 (1..5)
    zi_luna = (5 + total_days - 1) % DAYS_PER_MONTH + 1

    # Luna FS25 (începând de la IUN = 6)
    luna_index = ((6 - 1 + (total_days // DAYS_PER_MONTH)) % 12) + 1

    # Anul FS25 (incrementat dacă trecem peste DEC)
    an_fs25 = 2026 + ((6 - 1 + (total_days // DAYS_PER_MONTH)) // 12)

    # Ora și minutul în joc
    minutes_in_day = total_minutes % (24*60)
    ora_joc = int(minutes_in_day // 60)
    minut_joc = int(minutes_in_day % 60)

    return f"{an_fs25} | {LUNI[luna_index]} {zi_luna} | {ora_joc:02d}:{minut_joc:02d} | x{TIME_MULTIPLIER}"

async def safe_edit_channel(channel):
    """Editează canalul doar dacă s-a schimbat și retry la 429."""
    nume_nou = timp_fs25()
    if channel.name == nume_nou:
        return  # nu schimbăm dacă e deja corect

    retry = 0
    while retry < 5:
        try:
            await channel.edit(name=nume_nou)
            print(f"✅ Canal actualizat: {nume_nou}")
            return
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limit
                retry_after = getattr(e, 'retry_after', 60)
                print(f"⚠️ Rate-limit, reîncerc după {retry_after:.2f} secunde")
                await asyncio.sleep(retry_after + 1)
                retry += 1
            else:
                print(f"❌ Eroare la editarea canalului: {e}")
                return

# --- TASKS ---
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
    await asyncio.sleep(20)  # Delay mai sigur la start
    update_voice_name.start()

# --- START BOT ---
bot.run(DISCORD_TOKEN)