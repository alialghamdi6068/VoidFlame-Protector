import re
import time
from datetime import timedelta
from collections import defaultdict, deque

import discord
from discord.ext import commands

from database import get_settings, set_channel, set_toggle, add_trusted, remove_trusted, is_trusted
from config import (
    SPAM_MAX_MESSAGES, SPAM_WINDOW_SECONDS, RAID_JOIN_LIMIT, RAID_WINDOW_SECONDS,
    MASS_MENTION_LIMIT, WEBHOOK_LIMIT, LOCKDOWN_SECONDS,
)

INVITE_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:discord\.gg|discord\.com/invite)/[A-Za-z0-9-]+", re.I)


class Protection(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_buckets = defaultdict(deque)
        self.join_buckets = defaultdict(deque)
        self.action_buckets = defaultdict(deque)
        self.raid_until = {}

    async def log(self, guild, title, description, color=discord.Color.red(), actor=None):
        cog = self.bot.get_cog("LoggingSystem")
        if cog:
            await cog.send_log(guild, title, description, color=color, actor=actor)

    async def warn_room(self, guild, text):
        channel_id = get_settings(guild.id).get("warning_channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(text)
            except discord.HTTPException:
                pass

    async def security_action(self, guild, member, reason, *, ban=False):
        if member.bot or is_trusted(guild.id, member.id) or member.id == guild.owner_id:
            return False
        try:
            if ban:
                await guild.ban(member, reason=reason, delete_message_seconds=0)
            else:
                await member.timeout(timedelta(minutes=10), reason=reason)
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    @commands.command(name="لوق")
    @commands.has_guild_permissions(administrator=True)
    async def logs(self, ctx, channel: discord.TextChannel):
        set_channel(ctx.guild.id, "log_channel_id", channel.id)
        await ctx.reply(f"تم تعيين روم اللوق إلى {channel.mention}.")

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

    @commands.command(name="ازالةوثوق")
    @commands.has_guild_permissions(administrator=True)
    async def untrust(self, ctx, member: discord.Member):
        remove_trusted(ctx.guild.id, member.id)
        await ctx.reply(f"تمت إزالة {member.mention} من قائمة الموثوقين.")

    @commands.command(name="حالةالحماية", aliases=["حالة"])
    @commands.has_guild_permissions(administrator=True)
    async def status(self, ctx):
        s = get_settings(ctx.guild.id)
        labels = {
            "protection_enabled": "الحماية", "ai_enabled": "AI", "raid_enabled": "Anti-Raid",
            "spam_enabled": "Anti-Spam", "link_enabled": "Anti-Link", "mention_enabled": "Anti-Mention",
            "webhook_enabled": "Anti-Webhook", "nuke_enabled": "Anti-Nuke", "lockdown_enabled": "Lockdown",
        }
        text = "\n".join(f"{label}: {'ON' if s.get(key) else 'OFF'}" for key, label in labels.items())
        await ctx.reply(f"🛡️ **VoidFlame Protector**\n{text}")

    @commands.command(name="حماية")
    @commands.has_guild_permissions(administrator=True)
    async def enable(self, ctx, mode: str = "on"):
        value = mode.lower() in {"on", "تشغيل", "1", "true"}
        set_toggle(ctx.guild.id, "protection_enabled", value)
        await ctx.reply(f"🛡️ الحماية العامة: **{'ON' if value else 'OFF'}**")

    @commands.command(name="حمايةai")
    @commands.has_guild_permissions(administrator=True)
    async def ai_toggle(self, ctx, mode: str = "on"):
        value = mode.lower() in {"on", "تشغيل", "1", "true"}
        set_toggle(ctx.guild.id, "ai_enabled", value)
        await ctx.reply(f"AI: **{'ON' if value else 'OFF'}")

    @commands.command(name="قفل")
    @commands.has_guild_permissions(administrator=True)
    async def lockdown(self, ctx):
        s = get_settings(ctx.guild.id)
        if not s.get("lockdown_enabled"):
            await ctx.reply("❌ نظام القفل الطارئ معطل.")
            return
        changed = 0
        for channel in ctx.guild.text_channels:
            if not channel.permissions_for(ctx.guild.default_role).send_messages:
                continue
            try:
                await channel.set_permissions(ctx.guild.default_role, send_messages=False, reason="VoidFlame emergency lockdown")
                changed += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await self.log(ctx.guild, "Emergency lockdown", f"Locked **{changed}** text channels for new messages.", discord.Color.dark_red(), ctx.author)
        await ctx.reply(f"🚨 تم تفعيل القفل الطارئ على **{changed}** روم.")

    @commands.command(name="فتح")
    @commands.has_guild_permissions(administrator=True)
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
        await self.log(ctx.guild, "Emergency lockdown released", f"Restored **{changed}** text channels.", discord.Color.green(), ctx.author)
        await ctx.reply(f"تم فتح **{changed}** روم.")

    async def _recent_audit_actor(self, guild, action, target_id, max_age=20):
        try:
            async for entry in guild.audit_logs(limit=8, action=action):
                if entry.target and getattr(entry.target, "id", None) == target_id:
                    created = entry.created_at.timestamp()
                    if abs(time.time() - created) <= max_age:
                        return entry.user
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    async def _anti_nuke(self, guild, action, target, label):
        settings = get_settings(guild.id)
        if not settings.get("protection_enabled") or not settings.get("nuke_enabled"):
            return
        actor = await self._recent_audit_actor(guild, action, target.id)
        if not actor or actor.bot or is_trusted(guild.id, actor.id) or actor.id == guild.owner_id:
            return
        key = (guild.id, actor.id, label)
        now = time.monotonic()
        bucket = self.action_buckets[key]
        bucket.append(now)
        while bucket and now - bucket[0] > 15:
            bucket.popleft()
        if len(bucket) >= 3:
            acted = await self.security_action(guild, actor, f"VoidFlame Anti-Nuke: repeated {label}", ban=False)
            await self.warn_room(guild, f"🚨 Anti-Nuke: تم رصد تغييرات متكررة بواسطة {actor.mention} ({label}).")
            await self.log(guild, "Anti-Nuke triggered", f"Actor: {actor.mention}\nAction: `{label}`\nCount: **{len(bucket)}**\nResponse: **{'timeout' if acted else 'failed'}**", discord.Color.dark_red(), actor)
            bucket.clear()

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
            await self.log(guild, "Anti-Raid triggered", f"Detected **{len(bucket)}** joins within **{RAID_WINDOW_SECONDS}s**. New members will be temporarily restricted.", discord.Color.dark_red())
            await self.warn_room(guild, f"🚨 **Anti-Raid** موجة دخول: {len(bucket)} أعضاء خلال {RAID_WINDOW_SECONDS} ثوانٍ.")
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
            await self.log(message.guild, "Invite link blocked", f"Member: {message.author.mention}\nChannel: {message.channel.mention}", discord.Color.orange(), message.author)
            return

        if settings.get("mention_enabled") and len(message.mentions) >= MASS_MENTION_LIMIT:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            acted = await self.security_action(message.guild, message.author, "VoidFlame Anti-Mass-Mention")
            await self.warn_room(message.guild, f"⚠️ تم إيقاف منشن جماعي من {message.author.mention}.")
            await self.log(message.guild, "Anti-Mass-Mention", f"Member: {message.author.mention}\nMentions: **{len(message.mentions)}**\nResponse: **{'timeout' if acted else 'delete only'}**", discord.Color.red(), message.author)
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
            await self.log(message.guild, "Anti-Spam action", f"Member: {message.author.mention}\nMessages: **{len(bucket)}** in **{SPAM_WINDOW_SECONDS}s**", discord.Color.red(), message.author)
            bucket.clear()

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        await self._anti_nuke(channel.guild, discord.AuditLogAction.channel_delete, channel, "channel delete")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        await self._anti_nuke(channel.guild, discord.AuditLogAction.channel_create, channel, "channel create")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        await self._anti_nuke(role.guild, discord.AuditLogAction.role_delete, role, "role delete")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        await self._anti_nuke(role.guild, discord.AuditLogAction.role_create, role, "role create")

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel):
        settings = get_settings(channel.guild.id)
        if not settings.get("protection_enabled") or not settings.get("webhook_enabled"):
            return
        try:
            webhooks = await channel.webhooks()
        except (discord.Forbidden, discord.HTTPException):
            return
        if len(webhooks) <= WEBHOOK_LIMIT:
            return
        actor = None
        try:
            async for entry in channel.guild.audit_logs(limit=5, action=discord.AuditLogAction.webhook_create):
                if entry.target and getattr(entry.target, "channel_id", channel.id) == channel.id:
                    actor = entry.user
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass
        if actor and not actor.bot and not is_trusted(channel.guild.id, actor.id) and actor.id != channel.guild.owner_id:
            acted = await self.security_action(channel.guild, actor, "VoidFlame Anti-Webhook")
            await self.log(channel.guild, "Anti-Webhook", f"Actor: {actor.mention}\nChannel: {channel.mention}\nWebhooks: **{len(webhooks)}**\nResponse: **{'timeout' if acted else 'log only'}**", discord.Color.red(), actor)

    @discord.app_commands.command(name="logs", description="Set the comprehensive security log channel")
    @discord.app_commands.default_permissions(administrator=True)
    async def logs_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        set_channel(interaction.guild.id, "log_channel_id", channel.id)
        await interaction.response.send_message(f"تم تعيين روم اللوق إلى {channel.mention}.")

    @discord.app_commands.command(name="warnings", description="Set the warning channel")
    @discord.app_commands.default_permissions(administrator=True)
    async def warnings_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        set_channel(interaction.guild.id, "warning_channel_id", channel.id)
        await interaction.response.send_message(f"تم تعيين روم الانذارات إلى {channel.mention}.")

    @discord.app_commands.command(name="staff", description="Set the staff review channel")
    @discord.app_commands.default_permissions(administrator=True)
    async def staff_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        set_channel(interaction.guild.id, "staff_channel_id", channel.id)
        await interaction.response.send_message(f"تم تعيين روم الإدارة إلى {channel.mention}.")


async def setup(bot):
    await bot.add_cog(Protection(bot))
