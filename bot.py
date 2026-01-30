import discord
from discord.ext import tasks, commands
from datetime import datetime, timedelta, timezone
import asyncio
import os

# --- CONFIGURAȚIE ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
VOICE_CHANNEL_ID = 1466767151267446953
TIME_MULTIPLIER = 3
SERVER_START = datetime(2026, 6, 5, 1, 30, tzinfo=timezone.utc)
DAYS_PER_MONTH = 5

LUNI = {
    1: "IAN", 2: "FEB", 3: "MAR", 4: "APR",
    5: "MAI", 6: "IUN", 7: "IUL", 8: "AUG",
    9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"
}

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

def timp_fs25():
    now = datetime.now(timezone.utc)
    delta = now - SERVER_START

    # dacă suntem înainte de start, delta = 0
    delta_minutes = max(delta.total_seconds() / 60, 0) * TIME_MULTIPLIER

    # Total zile FS25
    total_days = int(delta_minutes // (24*60))

    zi_luna = (1 + total_days - 1) % DAYS_PER_MONTH + 1
    luna_index = ((6 - 1 + (total_days // DAYS_PER_MONTH)) % 12) + 1
    an_fs25 = 2026 + ((6 - 1 + (total_days // DAYS_PER_MONTH)) // 12)

    minutes_in_day = delta_minutes % (24*60)
    ora_joc = int(minutes_in_day // 60)
    minut_joc = int(minutes_in_day % 60)

    return f"{an_fs25} | {LUNI[luna_index]} {zi_luna} | {ora_joc:02d}:{minut_joc:02d} | x{TIME_MULTIPLIER}"

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

@tasks.loop(minutes=1)
async def update_voice_name():
    canal = bot.get_channel(VOICE_CHANNEL_ID)
    if canal and isinstance(canal, discord.VoiceChannel):
        nou_nume = timp_fs25()
        print(f"[DEBUG] Numele calculat FS25: {nou_nume}")
        await safe_edit_channel(canal)

@bot.event
async def on_ready():
    print(f"Botul este online ca {bot.user}")
    await asyncio.sleep(5)
    update_voice_name.start()

bot.run(DISCORD_TOKEN)