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
START_MONTH = 6                                   # IUN
START_YEAR = 2026
START_DAY = 5                                     # ziua inițială
START_HOUR = 10                                   # ora inițială
START_MINUTE = 0                                  # minut inițial

LUNI = {
    1: "IAN", 2: "FEB", 3: "MAR", 4: "APR",
    5: "MAI", 6: "IUN", 7: "IUL", 8: "AUG",
    9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"
}

# --- BOT ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Timp FS25 intern ---
current_fs25 = datetime(START_YEAR, START_MONTH, START_DAY, START_HOUR, START_MINUTE)

def timp_fs25():
    global current_fs25
    # Calculăm ora ×3 doar pentru afișare
    ora = current_fs25.hour
    minut = current_fs25.minute
    zi = current_fs25.day
    luna = current_fs25.month
    an = current_fs25.year

    return f"{an} | {LUNI[luna]} {zi} | {ora:02d}:{minut:02d} | x{TIME_MULTIPLIER}"

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

# --- TASK: update la fiecare minut ---
@tasks.loop(minutes=1)
async def update_voice_name():
    global current_fs25
    canal = bot.get_channel(VOICE_CHANNEL_ID)
    if canal and isinstance(canal, discord.VoiceChannel):
        # incrementăm timpul cu 1 minut real
        current_fs25 += timedelta(minutes=1)
        # verificăm overflow pentru luna FS25 (5 zile)
        zi = current_fs25.day
        if zi > DAYS_PER_MONTH:
            current_fs25 = current_fs25.replace(day=1)
            # incrementăm luna
            luna = current_fs25.month + 1
            an = current_fs25.year
            if luna > 12:
                luna = 1
                an += 1
            current_fs25 = current_fs25.replace(month=luna, year=an)
        # edităm canalul
        await safe_edit_channel(canal)
        print(f"[DEBUG] Numele calculat FS25: {timp_fs25()}")

# --- EVENIMENTE ---
@bot.event
async def on_ready():
    print(f"Botul este online ca {bot.user}")
    await asyncio.sleep(5)
    update_voice_name.start()

# --- START BOT ---
bot.run(DISCORD_TOKEN)