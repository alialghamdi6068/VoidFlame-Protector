import os
import logging
import asyncio

import discord
from discord.ext import commands
from dotenv import load_dotenv

from database import init_db, ensure_guild
from cogs.maintenance import is_maintenance

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing")

logging.basicConfig(level=logging.INFO, format="[VoidFlame] %(levelname)s: %(message)s")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

EXTENSIONS = (
    "cogs.logging_system",
    "cogs.protection",
    "cogs.ai_moderation",
    "cogs.command_menu",
    "cogs.maintenance",
)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # During maintenance only the owner can use !maintenance to restore commands.
    if is_maintenance() and message.content.strip().lower() != "!maintenance":
        return

    await bot.process_commands(message)


@bot.event
async def setup_hook():
    init_db()
    for guild in bot.guilds:
        ensure_guild(guild.id)

    for extension in EXTENSIONS:
        try:
            await bot.load_extension(extension)
            logging.info("Loaded %s", extension)
        except Exception:
            logging.exception("Failed to load %s", extension)

    try:
        synced = await bot.tree.sync()
        logging.info("Synced %d slash command(s)", len(synced))
    except Exception:
        logging.exception("Slash command sync failed")


@bot.event
async def on_ready():
    logging.info("Logged in as %s (%s)", bot.user, bot.user.id)
    logging.info("Connected to %d guild(s)", len(bot.guilds))


@bot.tree.interaction_check
async def maintenance_check(interaction: discord.Interaction):
    if is_maintenance():
        try:
            owner = await bot.is_owner(interaction.user)
        except discord.HTTPException:
            owner = False
        if not owner:
            await interaction.response.send_message(
                "🔧 البوت حاليًا في وضع الصيانة. الأوامر متوقفة مؤقتًا.",
                ephemeral=True,
            )
            return False
    return True


@bot.tree.command(name="protection", description="Show VoidFlame Protector status")
@discord.app_commands.default_permissions(administrator=True)
async def protection_slash(interaction: discord.Interaction):
    cog = bot.get_cog("Protection")
    if cog:
        settings = __import__("database").get_settings(interaction.guild.id)
        enabled = "ON" if settings.get("protection_enabled") else "OFF"
        await interaction.response.send_message(f"🛡️ **VoidFlame Protector**\nالحماية العامة: **{enabled}**\nاستخدم `/status` أو `!حماية حالة` للتفاصيل.")
    else:
        await interaction.response.send_message("❌ نظام الحماية لم يتم تحميله.", ephemeral=True)


@bot.tree.command(name="status", description="Show all VoidFlame protection systems")
@discord.app_commands.default_permissions(administrator=True)
async def status_slash(interaction: discord.Interaction):
    from database import get_settings
    s = get_settings(interaction.guild.id)
    labels = {
        "protection_enabled": "Protection", "ai_enabled": "AI", "raid_enabled": "Anti-Raid",
        "spam_enabled": "Anti-Spam", "link_enabled": "Anti-Link", "mention_enabled": "Anti-Mention",
        "webhook_enabled": "Anti-Webhook", "nuke_enabled": "Anti-Nuke", "lockdown_enabled": "Lockdown",
    }
    text = "\n".join(f"{label}: {'ON' if s.get(key) else 'OFF'}" for key, label in labels.items())
    await interaction.response.send_message(f"🛡️ **VoidFlame Protector**\n{text}")


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.NotOwner):
        await ctx.reply("❌ هذا الأمر مخصص لصاحب البوت فقط.", mention_author=False)
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply("❌ هذا الأمر يحتاج صلاحية Administrator.", mention_author=False)
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply("❌ ناقصك تحديد المطلوب للأمر. مثال: `!حماية لوق #logs`", mention_author=False)
        return
    if isinstance(error, commands.BadArgument):
        await ctx.reply("❌ تأكد من المنشن أو الروم المستخدم في الأمر.", mention_author=False)
        return
    if isinstance(error, (commands.CommandNotFound, commands.CheckFailure)):
        return
    logging.exception("Command error", exc_info=error)


async def main():
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
