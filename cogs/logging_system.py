import discord
from discord.ext import commands
from database import get_settings, ensure_guild


class LoggingSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def send_log(self, guild: discord.Guild, title: str, description: str, *, color=discord.Color.blurple(), actor=None):
        settings = get_settings(guild.id)
        channel_id = settings.get("log_channel_id")
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        embed = discord.Embed(title=title, description=description[:4000], color=color, timestamp=discord.utils.utcnow())
        embed.set_footer(text="VoidFlame Protector • Security Log")
        if actor:
            try:
                embed.set_author(name=str(actor), icon_url=actor.display_avatar.url)
            except Exception:
                embed.set_author(name=str(actor))
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def audit_actor(self, guild, action, target_id=None, max_age=20):
        try:
            async for entry in guild.audit_logs(limit=10, action=action):
                if target_id is not None and entry.target and getattr(entry.target, "id", None) != target_id:
                    continue
                if abs((discord.utils.utcnow() - entry.created_at).total_seconds()) <= max_age:
                    return entry.user, entry.reason
        except (discord.Forbidden, discord.HTTPException):
            pass
        return None, None

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        ensure_guild(guild.id)
        await self.send_log(guild, "Bot joined server", f"Guild: **{guild.name}**\nID: `{guild.id}`", color=discord.Color.green())

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        await self.send_log(guild, "Bot left server", f"Guild: **{guild.name}**\nID: `{guild.id}`", color=discord.Color.red())

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        changes = []
        if before.name != after.name:
            changes.append(f"Name: `{before.name}` → `{after.name}`")
        if before.icon != after.icon:
            changes.append("Server icon changed")
        if before.owner_id != after.owner_id:
            changes.append(f"Owner ID: `{before.owner_id}` → `{after.owner_id}`")
        if before.verification_level != after.verification_level:
            changes.append(f"Verification: `{before.verification_level}` → `{after.verification_level}`")
        if before.default_notifications != after.default_notifications:
            changes.append("Default notifications changed")
        if changes:
            actor, reason = await self.audit_actor(after, discord.AuditLogAction.guild_update)
            if reason:
                changes.append(f"Reason: `{reason}`")
            await self.send_log(after, "Server updated", "\n".join(changes), color=discord.Color.orange(), actor=actor)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self.send_log(member.guild, "Member joined", f"Member: {member.mention}\nID: `{member.id}`\nAccount: <t:{int(member.created_at.timestamp())}:R>", color=discord.Color.green(), actor=member)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        actor, reason = await self.audit_actor(member.guild, discord.AuditLogAction.kick, member.id)
        if actor:
            await self.send_log(member.guild, "Member kicked", f"Member: {member.mention}\nID: `{member.id}`\nActor: {actor.mention}\nReason: `{reason or 'No reason provided'}`", color=discord.Color.red(), actor=actor)
        else:
            await self.send_log(member.guild, "Member left", f"Member: **{member}**\nID: `{member.id}`", color=discord.Color.orange(), actor=member)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        changes = []
        if before.display_name != after.display_name:
            changes.append(f"Name: `{before.display_name}` → `{after.display_name}`")
        if before.avatar != after.avatar:
            changes.append("Avatar changed")
        before_roles = {r.id for r in before.roles}
        after_roles = {r.id for r in after.roles}
        added = after_roles - before_roles
        removed = before_roles - after_roles
        if added:
            changes.append("Roles added: " + ", ".join(f"`{after.guild.get_role(r).name}`" for r in added if after.guild.get_role(r)))
        if removed:
            changes.append("Roles removed: " + ", ".join(f"`{before.guild.get_role(r).name}`" for r in removed if before.guild.get_role(r)))
        if before.communication_disabled_until != after.communication_disabled_until:
            if after.communication_disabled_until:
                changes.append(f"Timeout until: <t:{int(after.communication_disabled_until.timestamp())}:F>")
            else:
                changes.append("Timeout removed")
        if changes:
            actor, reason = await self.audit_actor(after.guild, discord.AuditLogAction.member_update, after.id)
            await self.send_log(after.guild, "Member updated", f"Member: {after.mention}\n" + "\n".join(changes) + (f"\nActor: {actor.mention}\nReason: `{reason or 'No reason provided'}`" if actor else ""), color=discord.Color.orange(), actor=actor or after)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        actor, reason = await self.audit_actor(guild, discord.AuditLogAction.ban, user.id)
        await self.send_log(guild, "Member banned", f"Member: **{user}**\nID: `{user.id}`\nActor: {actor.mention if actor else 'Unknown'}\nReason: `{reason or 'No reason provided'}`", color=discord.Color.red(), actor=actor or user)

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        actor, reason = await self.audit_actor(guild, discord.AuditLogAction.unban, user.id)
        await self.send_log(guild, "Member unbanned", f"Member: **{user}**\nID: `{user.id}`\nActor: {actor.mention if actor else 'Unknown'}\nReason: `{reason or 'No reason provided'}`", color=discord.Color.green(), actor=actor or user)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.guild and not message.author.bot:
            content = message.content or "[no text]"
            await self.send_log(message.guild, "Message deleted", f"Author: {message.author.mention}\nChannel: {message.channel.mention}\nContent: `{content[:1800]}`", color=discord.Color.red(), actor=message.author)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        if messages:
            await self.send_log(messages[0].guild, "Messages bulk deleted", f"Channel: {messages[0].channel.mention}\nCount: **{len(messages)}**", color=discord.Color.red())

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.guild and before.content != after.content and not before.author.bot:
            await self.send_log(before.guild, "Message edited", f"Author: {before.author.mention}\nChannel: {before.channel.mention}\nBefore: `{before.content[:800]}`\nAfter: `{after.content[:800]}`", color=discord.Color.orange(), actor=before.author)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        actor, reason = await self.audit_actor(channel.guild, discord.AuditLogAction.channel_create, channel.id)
        await self.send_log(channel.guild, "Channel created", f"Channel: {channel.mention}\nType: `{channel.type}`\nReason: `{reason or 'No reason provided'}`", color=discord.Color.green(), actor=actor)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        actor, reason = await self.audit_actor(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
        await self.send_log(channel.guild, "Channel deleted", f"Channel: **{channel.name}`\nID: `{channel.id}`\nActor: {actor.mention if actor else 'Unknown'}\nReason: `{reason or 'No reason provided'}`", color=discord.Color.red(), actor=actor)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        changes = []
        if before.name != after.name:
            changes.append(f"Name: `{before.name}` → `{after.name}`")
        if before.position != after.position:
            changes.append("Position changed")
        if before.category_id != after.category_id:
            changes.append("Category changed")
        if before.overwrites != after.overwrites:
            changes.append("Permissions/overwrites changed")
        if changes:
            actor, reason = await self.audit_actor(after.guild, discord.AuditLogAction.channel_update, after.id)
            await self.send_log(after.guild, "Channel updated", f"Channel: {after.mention}\n" + "\n".join(changes) + (f"\nActor: {actor.mention}\nReason: `{reason or 'No reason provided'}`" if actor else ""), color=discord.Color.orange(), actor=actor)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        actor, reason = await self.audit_actor(role.guild, discord.AuditLogAction.role_create, role.id)
        await self.send_log(role.guild, "Role created", f"Role: {role.mention}\nID: `{role.id}`\nReason: `{reason or 'No reason provided'}`", color=discord.Color.green(), actor=actor)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        actor, reason = await self.audit_actor(role.guild, discord.AuditLogAction.role_delete, role.id)
        await self.send_log(role.guild, "Role deleted", f"Role: **{role.name}**\nID: `{role.id}`\nActor: {actor.mention if actor else 'Unknown'}\nReason: `{reason or 'No reason provided'}`", color=discord.Color.red(), actor=actor)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        changes = []
        if before.name != after.name:
            changes.append(f"Name: `{before.name}` → `{after.name}`")
        if before.permissions != after.permissions:
            changes.append("Permissions changed")
        if before.position != after.position:
            changes.append("Position changed")
        if changes:
            actor, reason = await self.audit_actor(after.guild, discord.AuditLogAction.role_update, after.id)
            await self.send_log(after.guild, "Role updated", f"Role: {after.mention}\n" + "\n".join(changes) + (f"\nActor: {actor.mention}\nReason: `{reason or 'No reason provided'}`" if actor else ""), color=discord.Color.orange(), actor=actor)

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        before_ids = {e.id for e in before}
        after_ids = {e.id for e in after}
        added = after_ids - before_ids
        removed = before_ids - after_ids
        if added or removed:
            await self.send_log(guild, "Emojis updated", f"Added: **{len(added)}**\nRemoved: **{len(removed)}**", color=discord.Color.orange())

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild, before, after):
        before_ids = {s.id for s in before}
        after_ids = {s.id for s in after}
        added = after_ids - before_ids
        removed = before_ids - after_ids
        if added or removed:
            await self.send_log(guild, "Stickers updated", f"Added: **{len(added)}**\nRemoved: **{len(removed)}**", color=discord.Color.orange())

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        changes = []
        if before.channel != after.channel:
            if before.channel is None and after.channel:
                changes.append(f"Joined: {after.channel.mention}")
            elif before.channel and after.channel is None:
                changes.append(f"Left: {before.channel.mention}")
            elif before.channel and after.channel:
                changes.append(f"Moved: {before.channel.mention} → {after.channel.mention}")
        if before.self_mute != after.self_mute:
            changes.append(f"Self mute: **{'ON' if after.self_mute else 'OFF'}**")
        if before.self_deaf != after.self_deaf:
            changes.append(f"Self deaf: **{'ON' if after.self_deaf else 'OFF'}**")
        if before.mute != after.mute:
            changes.append(f"Server mute: **{'ON' if after.mute else 'OFF'}**")
        if before.deaf != after.deaf:
            changes.append(f"Server deaf: **{'ON' if after.deaf else 'OFF'}**")
        if before.suppress != after.suppress:
            changes.append(f"Suppressed: **{'ON' if after.suppress else 'OFF'}**")
        if changes:
            await self.send_log(member.guild, "Voice state updated", f"Member: {member.mention}\n" + "\n".join(changes), color=discord.Color.blurple(), actor=member)

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel):
        await self.send_log(channel.guild, "Webhooks updated", f"Channel: {channel.mention}", color=discord.Color.orange())


async def setup(bot):
    await bot.add_cog(LoggingSystem(bot))
