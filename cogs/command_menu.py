import discord
from discord.ext import commands

from database import (
    add_trusted,
    get_settings,
    remove_trusted,
    set_channel,
    set_toggle,
)


class ProtectionCommands(commands.Cog):
    """Clean administrator command interface for VoidFlame Protector."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def status_text(settings: dict) -> str:
        labels = (
            ("protection_enabled", "الحماية العامة"),
            ("ai_enabled", "الذكاء الاصطناعي"),
            ("raid_enabled", "مكافحة الغارات"),
            ("spam_enabled", "مكافحة السبام"),
            ("link_enabled", "مكافحة الروابط"),
            ("mention_enabled", "مكافحة المنشن الجماعي"),
            ("webhook_enabled", "مكافحة الويب هوك"),
            ("nuke_enabled", "مكافحة التخريب"),
            ("lockdown_enabled", "القفل الطارئ"),
        )
        return "\n".join(
            f"{'🟢' if settings.get(key) else '🔴'} {label}"
            for key, label in labels
        )

    @commands.group(name="حماية", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def protection(self, ctx: commands.Context):
        settings = get_settings(ctx.guild.id)
        embed = discord.Embed(
            title="🛡️ VoidFlame Protector",
            description=(
                f"{self.status_text(settings)}\n\n"
                "استخدم `!حماية حالة` لعرض الحالة، أو اختر أحد أوامر الإدارة."
            ),
            color=discord.Color.blurple(),
        )
        await ctx.reply(embed=embed, mention_author=False)

    @protection.command(name="حالة")
    async def status(self, ctx: commands.Context):
        await self.protection(ctx)

    @protection.command(name="تشغيل")
    async def enable(self, ctx: commands.Context):
        set_toggle(ctx.guild.id, "protection_enabled", True)
        await ctx.reply("🟢 تم تشغيل الحماية العامة.", mention_author=False)

    @protection.command(name="ايقاف")
    async def disable(self, ctx: commands.Context):
        set_toggle(ctx.guild.id, "protection_enabled", False)
        await ctx.reply("🔴 تم إيقاف الحماية العامة.", mention_author=False)

    @protection.command(name="ذكاء")
    async def ai(self, ctx: commands.Context):
        settings = get_settings(ctx.guild.id)
        value = not bool(settings.get("ai_enabled"))
        set_toggle(ctx.guild.id, "ai_enabled", value)
        await ctx.reply(
            f"{'🟢' if value else '🔴'} الذكاء الاصطناعي: **{'ON' if value else 'OFF'}**",
            mention_author=False,
        )

    @protection.command(name="لوق")
    async def logs(self, ctx: commands.Context, channel: discord.TextChannel):
        set_channel(ctx.guild.id, "log_channel_id", channel.id)
        await ctx.reply(f"📝 تم تعيين روم اللوق إلى {channel.mention}.", mention_author=False)

    @protection.command(name="انذارات")
    async def warnings(self, ctx: commands.Context, channel: discord.TextChannel):
        set_channel(ctx.guild.id, "warning_channel_id", channel.id)
        await ctx.reply(f"⚠️ تم تعيين روم الانذارات إلى {channel.mention}.", mention_author=False)

    @protection.command(name="ادارة")
    async def staff(self, ctx: commands.Context, channel: discord.TextChannel):
        set_channel(ctx.guild.id, "staff_channel_id", channel.id)
        await ctx.reply(f"👮 تم تعيين روم الإدارة إلى {channel.mention}.", mention_author=False)

    @protection.command(name="وثوق")
    async def trust(self, ctx: commands.Context, member: discord.Member):
        add_trusted(ctx.guild.id, member.id)
        await ctx.reply(f"🟢 تمت إضافة {member.mention} إلى قائمة الموثوقين.", mention_author=False)

    @protection.command(name="ازالة وثوق")
    async def untrust(self, ctx: commands.Context, member: discord.Member):
        remove_trusted(ctx.guild.id, member.id)
        await ctx.reply(f"🔴 تمت إزالة {member.mention} من قائمة الموثوقين.", mention_author=False)

    @protection.command(name="قفل")
    async def lockdown(self, ctx: commands.Context):
        settings = get_settings(ctx.guild.id)
        if not settings.get("lockdown_enabled"):
            await ctx.reply("❌ نظام القفل الطارئ معطل.", mention_author=False)
            return

        changed = 0
        for channel in ctx.guild.text_channels:
            if channel.permissions_for(ctx.guild.default_role).send_messages is False:
                continue
            try:
                await channel.set_permissions(
                    ctx.guild.default_role,
                    send_messages=False,
                    reason="VoidFlame emergency lockdown",
                )
                changed += 1
            except (discord.Forbidden, discord.HTTPException):
                continue

        await ctx.reply(f"🚨 تم تفعيل القفل الطارئ على **{changed}** روم.", mention_author=False)

    @protection.command(name="فتح")
    async def unlock(self, ctx: commands.Context):
        changed = 0
        for channel in ctx.guild.text_channels:
            overwrite = channel.overwrites_for(ctx.guild.default_role)
            if overwrite.send_messages is not False:
                continue
            try:
                await channel.set_permissions(
                    ctx.guild.default_role,
                    send_messages=None,
                    reason="VoidFlame lockdown released",
                )
                changed += 1
            except (discord.Forbidden, discord.HTTPException):
                continue

        await ctx.reply(f"🟢 تم فتح **{changed}** روم.", mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(ProtectionCommands(bot))
