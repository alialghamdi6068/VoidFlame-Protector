import re
import time
from datetime import timedelta
from collections import defaultdict, deque

import discord
from discord.ext import commands

from database import get_settings, is_trusted
from config import (
    SPAM_MAX_MESSAGES, SPAM_WINDOW_SECONDS, RAID_JOIN_LIMIT, RAID_WINDOW_SECONDS,
    MASS_MENTION_LIMIT,
)

INVITE_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:discord\.gg|discord\.com/invite)/[A-Za-z0-9-]+", re.I)


class Protection(commands.Cog):
    """Automatic protection systems. Command UI is handled by command_menu."""

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

    def is_protected_actor(self, guild, member_id):
        return is_trusted(guild.id, member_id) or member_id == guild.owner_id

    async def security_action(self, guild, member, reason, *, ban=False):
        target = guild.get_member(getattr(member, "id", 0))
        if target is None:
            return False
        if target.bot or self.is_protected_actor(guild, target.id):
            return False
        me = guild.me
        if not me:
            return False
        try:
            if ban and me.guild_permissions.ban_members:
                await guild.ban(target, reason=reason, delete_message_seconds=0)
            elif not ban and me.guild_permissions.moderate_members:
                await target.timeout(timedelta(minutes=10), reason=reason)
            else:
                return False
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    async def _recent_audit_actor(self, guild, action, target_id, max_age=20):
        try:
            async for entry in guild.audit_logs(limit=10, action=action):
                if target_id is not None and getattr(entry.target, "id", None) != target_id:
                    continue
                if abs(time.time() - entry.created_at.timestamp()) <= max_age:
                    return entry.user
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    async def _anti_nuke(self, guild, action, target, label):
        settings = get_settings(guild.id)
        if not settings.get("protection_enabled") or not settings.get("nuke_enabled"):
            return

        actor = await self._recent_audit_actor(guild, action, getattr(target, "id", None))
        if not actor or actor.bot or self.is_protected_actor(guild, actor.id):
            return

        key = (guild.id, actor.id)
        now = time.monotonic()
        bucket = self.action_buckets[key]
        bucket.append(now)
        while bucket and now - bucket[0] > 15:
            bucket.popleft()

        if len(bucket) >= 3:
            acted = await self.security_action(guild, actor, f"VoidFlame Anti-Nuke: repeated {label}")
            await self.warn_room(guild, f"🚨 Anti-Nuke: تم رصد تغييرات متكررة بواسطة {actor.mention} ({label}).")
            await self.log(
                guild,
                "Anti-Nuke triggered",
                f"Actor: {actor.mention}\nAction: `{label}`\nCount: **{len(bucket)}** in **15s**\nResponse: **{'timeout' if acted else 'failed'}**",
                discord.Color.dark_red(),
                actor,
            )
            bucket.clear()

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        settings = get_settings(guild.id)
        if not settings.get("protection_enabled") or not settings.get("raid_enabled") or member.bot:
            return

        now = time.monotonic()
        bucket = self.join_buckets[guild.id]
        bucket.append(now)
        while bucket and now - bucket[0] > RAID_WINDOW_SECONDS:
            bucket.popleft()

        if len(bucket) >= RAID_JOIN_LIMIT:
            self.raid_until[guild.id] = now + 60
            await self.log(
                guild,
                "Anti-Raid triggered",
                f"Detected **{len(bucket)}** joins within **{RAID_WINDOW_SECONDS}s**. New members will be temporarily restricted.",
                discord.Color.dark_red(),
            )
            await self.warn_room(guild, f"🚨 **Anti-Raid** موجة دخول: {len(bucket)} أعضاء خلال {RAID_WINDOW_SECONDS} ثوانٍ.")

        if guild.id in self.raid_until and now < self.raid_until[guild.id] and not self.is_protected_actor(guild, member.id):
            try:
                if guild.me and guild.me.guild_permissions.moderate_members:
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
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass
            await self.warn_room(message.guild, f"⚠️ تم حذف دعوة Discord من {message.author.mention} في {message.channel.mention}.")
            await self.log(message.guild, "Invite link blocked", f"Member: {message.author.mention}\nChannel: {message.channel.mention}", discord.Color.orange(), message.author)
            return

        if settings.get("mention_enabled") and len(message.mentions) >= MASS_MENTION_LIMIT:
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
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
            acted = False
            try:
                if message.guild.me and message.guild.me.guild_permissions.moderate_members:
                    await message.author.timeout(timedelta(seconds=60), reason="VoidFlame Anti-Spam")
                    acted = True
            except (discord.Forbidden, discord.HTTPException):
                pass
            await self.log(message.guild, "Anti-Spam action", f"Member: {message.author.mention}\nMessages: **{len(bucket)}** in **{SPAM_WINDOW_SECONDS}s**\nResponse: **{'timeout' if acted else 'failed'}**", discord.Color.red(), message.author)
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
    async def on_guild_channel_update(self, before, after):
        if before.overwrites != after.overwrites:
            await self._anti_nuke(after.guild, discord.AuditLogAction.channel_update, after, "channel permission update")

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        if before.permissions != after.permissions:
            await self._anti_nuke(after.guild, discord.AuditLogAction.role_update, after, "role permission update")

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel):
        settings = get_settings(channel.guild.id)
        if not settings.get("protection_enabled") or not settings.get("webhook_enabled"):
            return
        try:
            webhooks = await channel.webhooks()
        except (discord.Forbidden, discord.HTTPException):
            return
        if len(webhooks) <= 3:
            return

        actor = None
        try:
            async for entry in channel.guild.audit_logs(limit=10, action=discord.AuditLogAction.webhook_create):
                target = entry.target
                target_channel_id = getattr(target, "channel_id", None)
                if target_channel_id not in (None, channel.id):
                    continue
                if abs(time.time() - entry.created_at.timestamp()) <= 20:
                    actor = entry.user
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass

        if actor and not actor.bot and not self.is_protected_actor(channel.guild, actor.id):
            acted = await self.security_action(channel.guild, actor, "VoidFlame Anti-Webhook")
            await self.log(
                channel.guild,
                "Anti-Webhook",
                f"Actor: {actor.mention}\nChannel: {channel.mention}\nWebhooks: **{len(webhooks)}**\nResponse: **{'timeout' if acted else 'log only'}**",
                discord.Color.red(),
                actor,
            )

    @discord.app_commands.command(name="logs", description="Set the comprehensive security log channel")
    @discord.app_commands.default_permissions(administrator=True)
    async def logs_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        from database import set_channel
        set_channel(interaction.guild.id, "log_channel_id", channel.id)
        await interaction.response.send_message(f"تم تعيين روم اللوق إلى {channel.mention}.")

    @discord.app_commands.command(name="warnings", description="Set the warning channel")
    @discord.app_commands.default_permissions(administrator=True)
    async def warnings_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        from database import set_channel
        set_channel(interaction.guild.id, "warning_channel_id", channel.id)
        await interaction.response.send_message(f"تم تعيين روم الانذارات إلى {channel.mention}.")

    @discord.app_commands.command(name="staff", description="Set the staff review channel")
    @discord.app_commands.default_permissions(administrator=True)
    async def staff_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        from database import set_channel
        set_channel(interaction.guild.id, "staff_channel_id", channel.id)
        await interaction.response.send_message(f"تم تعيين روم الإدارة إلى {channel.mention}.")


async def setup(bot):
    await bot.add_cog(Protection(bot))
