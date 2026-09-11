import asyncio
import json
import logging
from datetime import timedelta

import aiohttp
import discord
from discord.ext import commands

from config import AI_API_KEY, GEMINI_MODEL, AI_TIMEOUT, AI_HIGH_CONFIDENCE, AI_LOW_CONFIDENCE
from database import get_settings, is_trusted


class AIModeration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        if self.session and not self.session.closed:
            asyncio.create_task(self.session.close())

    @staticmethod
    def timeout_minutes(confidence: float) -> int:
        """Convert AI confidence/severity into a bounded moderation duration."""
        if confidence >= 0.99:
            return 30
        if confidence >= 0.97:
            return 20
        if confidence >= 0.95:
            return 15
        return 5

    async def analyze(self, text: str) -> dict | None:
        if not AI_API_KEY or not self.session:
            return None
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={AI_API_KEY}"
        prompt = (
            "You are a Discord safety classifier. Analyze the user's message only. "
            "Return JSON only with keys: harmful (boolean), confidence (number 0 to 1), "
            "category (short string), reason (short string). "
            "Harmful means serious harassment, threats, targeted abuse, scams, malicious spam, "
            "or other clearly unsafe/toxic content that should be moderated. "
            "Do not treat ordinary disagreement, profanity without a target, jokes, or benign content as harmful. "
            "Never provide extra text outside JSON.\nMESSAGE:\n" + text[:3500]
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
        try:
            timeout = aiohttp.ClientTimeout(total=AI_TIMEOUT)
            async with self.session.post(url, json=payload, timeout=timeout) as response:
                if response.status != 200:
                    logging.warning("Gemini returned HTTP %s", response.status)
                    return None
                data = await response.json()
                raw = data["candidates"][0]["content"]["parts"][0]["text"]
                result = json.loads(raw)
                confidence = max(0.0, min(float(result.get("confidence", 0)), 1.0))
                return {
                    "harmful": bool(result.get("harmful", False)),
                    "confidence": confidence,
                    "category": str(result.get("category", "unknown"))[:100],
                    "reason": str(result.get("reason", ""))[:500],
                }
        except (asyncio.TimeoutError, aiohttp.ClientError, KeyError, ValueError, json.JSONDecodeError) as exc:
            logging.warning("AI analysis failed: %s", exc)
            return None

    async def staff_alert(self, message, result):
        settings = get_settings(message.guild.id)
        channel_id = settings.get("staff_channel_id")
        if not channel_id:
            return
        channel = message.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        embed = discord.Embed(
            title="AI review required",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Member", value=f"{message.author.mention} (`{message.author.id}`)", inline=False)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(name="Confidence", value=f"{result['confidence'] * 100:.1f}%", inline=True)
        embed.add_field(name="Category", value=result["category"], inline=True)
        embed.add_field(name="Message", value=message.content[:1000] or "[empty]", inline=False)
        embed.add_field(name="Reason", value=result["reason"] or "No reason", inline=False)
        embed.set_footer(text="VoidFlame Protector • AI")
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot or not message.content.strip():
            return
        settings = get_settings(message.guild.id)
        if not settings.get("protection_enabled") or not settings.get("ai_enabled"):
            return
        if is_trusted(message.guild.id, message.author.id):
            return

        result = await self.analyze(message.content)
        if not result or not result["harmful"]:
            return

        confidence = result["confidence"]
        logger = self.bot.get_cog("LoggingSystem")

        if confidence >= AI_HIGH_CONFIDENCE:
            minutes = self.timeout_minutes(confidence)
            timeout_applied = False
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            try:
                await message.author.timeout(
                    timedelta(minutes=minutes),
                    reason=f"VoidFlame AI: harmful message ({confidence:.2f})",
                )
                timeout_applied = True
            except (discord.Forbidden, discord.HTTPException):
                pass

            if logger:
                await logger.send_log(
                    message.guild,
                    "AI action: timeout",
                    f"Member: {message.author.mention}\n"
                    f"Channel: {message.channel.mention}\n"
                    f"Confidence: **{confidence * 100:.1f}%**\n"
                    f"Timeout: **{minutes} minutes**\n"
                    f"Applied: **{'yes' if timeout_applied else 'no'}**\n"
                    f"Category: `{result['category']}`\n"
                    f"Reason: {result['reason']}",
                    color=discord.Color.red(),
                    actor=message.author,
                )
        elif confidence < AI_LOW_CONFIDENCE:
            await self.staff_alert(message, result)
            if logger:
                await logger.send_log(
                    message.guild,
                    "AI review requested",
                    f"Member: {message.author.mention}\n"
                    f"Channel: {message.channel.mention}\n"
                    f"Confidence: **{confidence * 100:.1f}%**\n"
                    f"Category: `{result['category']}`",
                    color=discord.Color.orange(),
                    actor=message.author,
                )


async def setup(bot):
    await bot.add_cog(AIModeration(bot))
