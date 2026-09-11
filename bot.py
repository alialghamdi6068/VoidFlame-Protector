import os
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing")

logging.basicConfig(level=logging.INFO, format="[VoidFlame] %(levelname)s: %(message)s")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.event
async def on_ready():
    logging.info("Logged in as %s (%s)", bot.user, bot.user.id)
    logging.info("Connected to %d guild(s)", len(bot.guilds))
    try:
        synced = await bot.tree.sync()
        logging.info("Synced %d slash command(s)", len(synced))
    except Exception:
        logging.exception("Slash command sync failed")

@bot.command(name="حماية")
@commands.has_guild_permissions(administrator=True)
async def protection(ctx: commands.Context):
    await ctx.send("🛡️ **VoidFlame Protector**\nنظام الحماية الأساسي يعمل. سيتم إضافة أنظمة Anti-Raid و Anti-Nuke و AI والحماية المتقدمة في الخطوة التالية.")

@bot.tree.command(name="protection", description="Show VoidFlame Protector status")
@discord.app_commands.default_permissions(administrator=True)
async def protection_slash(interaction: discord.Interaction):
    await interaction.response.send_message("🛡️ **VoidFlame Protector**\nنظام الحماية الأساسي يعمل.")

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ هذا الأمر يحتاج صلاحية Administrator.")
        return
    if isinstance(error, commands.CommandNotFound):
        return
    logging.exception("Command error", exc_info=error)

bot.run(TOKEN)
