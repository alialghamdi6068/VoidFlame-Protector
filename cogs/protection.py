import re
import time
from datetime import timedelta
from collections import defaultdict, deque
import discord
from discord.ext import commands
from database import get_settings, set_channel, add_trusted, remove_trusted, is_trusted
from config import SPAM_MAX_MESSAGES, SPAM_WINDOW_SECONDS, RAID_JOIN_LIMIT, RAID_WINDOW_SECONDS

INVITE_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:discord\.gg|discord\.com/invite)/[A-Za-z0-9-]+", re.I)


class Protection(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_buckets = defaultdict(deque)
        self.join_buckets = defaultdict(deque)
        self.raid_until = {}

    async def log(self, guild, title, description, color=discord.Color.red()):
        cog = self.bot.get_cog("LoggingSystem")
        if cog:
            await cog.send_log(guild, title, description, color=color)

    async def warn_room(self, guild, text):
        channel_id = get_settings(guild.id).get("warning_channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(text)
            except discord.HTTPException:
                pass

    @commands.command(name="انذارات")
    @commands.has_guild_permissions(administrator=True)
    async def warnings(self, ctx, channel: discord.TextChannel):
        set_channel(ctx.guild.id, "warning_channel_id", channel.id)
        await ctx.reply(f"تم تعيين روم الانذارات إلى {channel.mention}.")

    @commands.command(name="ادارة")
    @commands.has_guild_permissions(administrator=True)
    async def staff(self, ctx, channel: discord.TextChannel):
        set_channel(ctx.guild.id, "staff_channel_id", channel.id)
        await ctx.reply(f"تم تعيين روم الإدارة إلى {channel.mention}.")

    @commands.command(name="وثوق")
    @commands.has_guild_permissions(administrator=True)
    async def trust(self, ctx, member: discord.Member):
        add_trusted(ctx.guild.id, member.id)
        await ctx.reply(f"تمت إضافة {member.mention} إلى قائمة الموثوقين.")

    @commands.command(name="ازالة وثوق")
    @commands.has_guild_permissions(administrator=True)
    async def untrust(self, ctx, member: discord.Member):
        remove_trusted(ctx.guild.id, member.id)
        await ctx.reply(f"تمت إزالة {member.mention} من قائمة الموثوقين.")

    @commands.command(name="حالة الحماية")
    @commands.has_guild_permissions(administrator=True)
    async def status(self, ctx):
        s = get_settings(ctx.guild.id)
        await ctx.reply(
            "🛡️ **VoidFlame Protector**\n"
            f"الحماية: {'ON' if s['protection_enabled'] else 'OFF'}\n"
            f"AI: {'ON' if s['ai_enabled'] else 'OFF'}\n"
            f"Anti-Raid: {'ON' if s['raid_enabled'] else 'OFF'}\n"
            f"Anti-Spam: {'ON' if s['spam_enabled'] else 'OFF'}\n"
            f"Anti-Link: {'ON' if s['link_enabled'] else 'OFF'}"
        )

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        settings = get_settings(guild.id)
        if not settings.get("protection_enabled") or not settings.get("raid_enabled"):
            return
        now = time.monotonic()
        bucket = self.join_buckets[guild.id]
        bucket.append(now)
        while bucket and now - bucket[0] > RAID_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= RAID_JOIN_LIMIT:
            self.raid_until[guild.id] = now + 60
            await self.log(guild, "Anti-Raid triggered", f"Detected {len(bucket)} joins within {RAID_WINDOW_SECONDS} seconds. Emergency protection window enabled.")
            await self.warn_room(guild, f"🚨 **Anti-Raid** تم رصد موجة دخول ({len(bucket)} أعضاء خلال {RAID_WINDOW_SECONDS} ثوانٍ).")

        if guild.id in self.raid_until and now < self.raid_until[guild.id]:
            try:
                await member.timeout(timedelta(seconds=30), reason="VoidFlame Anti-Raid")
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot or is_trusted(message.guild.id, message.author.id):
            return
        settings = get_settings(message.guild.id)
        if not settings.get("protection_enabled"):
            return
        if settings.get("link_enabled") and INVITE_RE.search(message.content):
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            await self.warn_room(message.guild, f"⚠️ تم حذف دعوة Discord من {message.author.mention} في {message.channel.mention}.")
            await self.log(message.guild, "Invite link blocked", f"Member: {message.author.mention}\nChannel: {message.channel.mention}", discord.Color.orange())
            return

        if not settings.get("spam_enabled"):
            return
        now = time.monotonic()
        bucket = self.message_buckets[(message.guild.id, message.author.id)]
        bucket.append(now)
        while bucket and now - bucket[0] > SPAM_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= SPAM_MAX_MESSAGES:
            try:
                await message.author.timeout(timedelta(seconds=60), reason="VoidFlame Anti-Spam")
            except (discord.Forbidden, discord.HTTPException):
                pass
            await self.log(message.guild, "Anti-Spam action", f"Member: {message.author.mention}\nMessages: {len(bucket)} in {SPAM_WINDOW_SECONDS}s", discord.Color.red())
            bucket.clear()


async def setup(bot):
    await bot.add_cog(Protection(bot))
