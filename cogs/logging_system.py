import discord
from discord.ext import commands
from database import get_settings, set_channel, ensure_guild


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
        embed.set_footer(text="VoidFlame Protector")
        if actor:
            embed.set_author(name=str(actor), icon_url=actor.display_avatar.url)
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.command(name="لوق")
    @commands.has_guild_permissions(administrator=True)
    async def set_log(self, ctx, channel: discord.TextChannel):
        set_channel(ctx.guild.id, "log_channel_id", channel.id)
        await ctx.reply(f"تم تعيين روم اللوق إلى {channel.mention}.")
        await self.send_log(ctx.guild, "Log system configured", f"Log channel: {channel.mention}", actor=ctx.author)

    @discord.app_commands.command(name="logs", description="Set the comprehensive security log channel")
    @discord.app_commands.default_permissions(administrator=True)
    async def set_log_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        set_channel(interaction.guild.id, "log_channel_id", channel.id)
        await interaction.response.send_message(f"تم تعيين روم اللوق إلى {channel.mention}.")

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        ensure_guild(guild.id)
        await self.send_log(guild, "Bot joined server", f"Guild: **{guild.name}**\nID: `{guild.id}`", color=discord.Color.green())

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self.send_log(member.guild, "Member joined", f"Member: {member.mention}\nID: `{member.id}`\nAccount: <t:{int(member.created_at.timestamp())}:R>", color=discord.Color.green())

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await self.send_log(member.guild, "Member left", f"Member: **{member}**\nID: `{member.id}`", color=discord.Color.orange())

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        changes = []
        if before.display_name != after.display_name:
            changes.append(f"Name: `{before.display_name}` → `{after.display_name}`")
        if before.avatar != after.avatar:
            changes.append("Avatar changed")
        if changes:
            await self.send_log(after.guild, "Member updated", f"Member: {after.mention}\n" + "\n".join(changes), actor=after)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.guild and not message.author.bot:
            content = message.content or "[no text]"
            await self.send_log(message.guild, "Message deleted", f"Author: {message.author.mention}\nChannel: {message.channel.mention}\nContent: `{content[:1800]}`", color=discord.Color.red())

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.guild and before.content != after.content and not before.author.bot:
            await self.send_log(before.guild, "Message edited", f"Author: {before.author.mention}\nChannel: {before.channel.mention}\nBefore: `{before.content[:800]}`\nAfter: `{after.content[:800]}`", color=discord.Color.orange())

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        await self.send_log(channel.guild, "Channel created", f"Channel: {channel.mention}\nType: `{channel.type}`", color=discord.Color.green())

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        await self.send_log(channel.guild, "Channel deleted", f"Channel: **{channel.name}**\nID: `{channel.id}`", color=discord.Color.red())

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if before.name != after.name:
            await self.send_log(after.guild, "Channel renamed", f"Before: `{before.name}`\nAfter: `{after.name}`", color=discord.Color.orange())

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        await self.send_log(role.guild, "Role created", f"Role: {role.mention}\nID: `{role.id}`", color=discord.Color.green())

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        await self.send_log(role.guild, "Role deleted", f"Role: **{role.name}**\nID: `{role.id}`", color=discord.Color.red())

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        changes = []
        if before.name != after.name:
            changes.append(f"Name: `{before.name}` → `{after.name}`")
        if before.permissions != after.permissions:
            changes.append("Permissions changed")
        if changes:
            await self.send_log(after.guild, "Role updated", f"Role: {after.mention}\n" + "\n".join(changes), color=discord.Color.orange())


async def setup(bot):
    await bot.add_cog(LoggingSystem(bot))
