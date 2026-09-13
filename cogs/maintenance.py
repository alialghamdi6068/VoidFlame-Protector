from discord.ext import commands

OWNER_ID = 1293157778030071920
maintenance_mode = False


def is_maintenance() -> bool:
    return maintenance_mode


class Maintenance(commands.Cog):
    """Global maintenance switch. Only the bot owner can control it."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="maintenance")
    async def maintenance(self, ctx):
        global maintenance_mode

        if ctx.author.id != OWNER_ID:
            await ctx.reply(
                "❌ لا يستطيع استخدام هذا الأمر إلا <@1293157778030071920>.",
                mention_author=False,
            )
            return

        maintenance_mode = not maintenance_mode

        if maintenance_mode:
            await ctx.reply(
                "🔧 تم تفعيل وضع الصيانة. جميع أعمال وأنظمة البوت متوقفة مؤقتًا.",
                mention_author=False,
            )
        else:
            await ctx.reply(
                "✅ تم إنهاء وضع الصيانة. جميع أعمال وأنظمة البوت تعمل الآن.",
                mention_author=False,
            )


async def setup(bot):
    await bot.add_cog(Maintenance(bot))
