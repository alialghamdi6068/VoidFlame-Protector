from discord.ext import commands


maintenance_mode = False


def is_maintenance() -> bool:
    return maintenance_mode


class Maintenance(commands.Cog):
    """Global maintenance switch for the bot's command system."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="صيانة")
    @commands.is_owner()
    async def maintenance(self, ctx):
        global maintenance_mode
        maintenance_mode = not maintenance_mode

        if maintenance_mode:
            await ctx.reply("🔧 تم تفعيل وضع الصيانة. جميع أوامر البوت متوقفة مؤقتًا.")
        else:
            await ctx.reply("✅ تم إنهاء الصيانة. جميع أوامر البوت تعمل الآن.")


async def setup(bot):
    await bot.add_cog(Maintenance(bot))
