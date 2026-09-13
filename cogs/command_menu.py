import discord
from discord.ext import commands
from database import get_settings, set_channel, set_toggle, add_trusted, remove_trusted


class ProtectionCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="حماية", invoke_without_command=True)
    @commands.has_guild_permissions(administrator=True)
    async def protection(self, ctx):
        s = get_settings(ctx.guild.id)
        labels = {
            "protection_enabled": "الحماية",
            "ai_enabled": "الذكاء الاصطناعي",
            "raid_enabled": "مكافحة الغارات",
            "spam_enabled": "مكافحة السبام",
            "link_enabled": "مكافحة الروابط",
            "mention_enabled": "مكافحة المنشن",
            "webhook_enabled": "مكافحة الويب هوك",
            "nuke_enabled": "مكافحة التخريب",
            "lockdown_enabled": "القفل الطارئ",
        }
        text = "\n".join(f"{label}: {'ON' if s.get(key) else 'OFF'}" for key, label in labels.items())
        await ctx.reply(f"🛡️ **VoidFlame Protector**\n{text}\n\nاستخدم `!حماية` مع أحد الخيارات لإدارة الحماية.")

    @protection.command(name="لوق")
    async def logs(self, ctx, channel: discord.TextChannel):
        set_channel(ctx.guild.id, "log_channel_id", channel.id)
        await ctx.reply(f"تم تعيين روم اللوق إلى {channel.mention}.")

    @protection.command(name="انذارات")
    async def warnings(self, ctx, channel: discord.TextChannel):
        set_channel(ctx.guild.id, "warning_channel_id", channel.id)
        await ctx.reply(f"تم تعيين روم الانذارات إلى {channel.mention}.")

    @protection.command(name="ادارة")
    async def staff(self, ctx, channel: discord.TextChannel):
        set_channel(ctx.guild.id, "staff_channel_id", channel.id)
        await ctx.reply(f"تم تعيين روم الإدارة إلى {channel.mention}.")

    @protection.command(name="وثوق")
    async def trust(self, ctx, member: discord.Member):
        add_trusted(ctx.guild.id, member.id)
        await ctx.reply(f"تمت إضافة {member.mention} إلى قائمة الموثوقين.")

    @protection.command(name="ازالةوثوق")
    async def untrust(self, ctx, member: discord.Member):
        remove_trusted(ctx.guild.id, member.id)
        await ctx.reply(f"تمت إزالة {member.mention} من قائمة الموثوقين.")

    @protection.command(name="حالة")
    async def status(self, ctx):
        await self.protection(ctx)

    @protection.command(name="تشغيل")
    async def enable(self, ctx):
        set_toggle(ctx.guild.id, "protection_enabled", True)
        await ctx.reply("🛡️ تم تشغيل الحماية العامة.")

    @protection.command(name="ايقاف")
    async def disable(self, ctx):
        set_toggle(ctx.guild.id, "protection_enabled", False)
        await ctx.reply("🛡️ تم إيقاف الحماية العامة.")

    @protection.command(name="ذكاء")
    async def ai(self, ctx):
        s = get_settings(ctx.guild.id)
        value = not bool(s.get("ai_enabled"))
        set_toggle(ctx.guild.id, "ai_enabled", value)
        await ctx.reply(f"الذكاء الاصطناعي: **{'ON' if value else 'OFF'}**")

    @protection.command(name="قفل")
    async def lockdown(self, ctx):
        s = get_settings(ctx.guild.id)
        if not s.get("lockdown_enabled"):
            await ctx.reply("❌ نظام القفل الطارئ معطل.")
            return
        changed = 0
        for channel in ctx.guild.text_channels:
            if channel.permissions_for(ctx.guild.default_role).send_messages is False:
                continue
            try:
                await channel.set_permissions(ctx.guild.default_role, send_messages=False, reason="VoidFlame emergency lockdown")
                changed += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await ctx.reply(f"🚨 تم تفعيل القفل الطارئ على **{changed}** روم.")

    @protection.command(name="فتح")
    async def unlock(self, ctx):
        changed = 0
        for channel in ctx.guild.text_channels:
            overwrite = channel.overwrites_for(ctx.guild.default_role)
            if overwrite.send_messages is False:
                try:
                    await channel.set_permissions(ctx.guild.default_role, send_messages=None, reason="VoidFlame lockdown released")
                    changed += 1
                except (discord.Forbidden, discord.HTTPException):
                    pass
        await ctx.reply(f"تم فتح **{changed}** روم.")


async def setup(bot):
    for name in ("لوق", "انذارات", "ادارة", "وثوق", "ازالةوثوق", "حالةالحماية", "حالة", "حماية", "حمايةai", "قفل", "فتح"):
        bot.remove_command(name)
    await bot.add_cog(ProtectionCommands(bot))
