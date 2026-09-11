import asyncio
import json
import logging
import re
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
        if confidence >= 0.99:
            return 30
        if confidence >= 0.97:
            return 20
        if confidence >= 0.95:
            return 15
        return 5

    @staticmethod
    def parse_json(text: str) -> dict | None:
        text = (text or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text).strip()
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.S)
            if not match:
                return None
            try:
                value = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return value if isinstance(value, dict) else None

    async def analyze(self, text: str) -> dict | None:
        if not AI_API_KEY or not self.session:
            logging.warning("AI moderation disabled: GEMINI_API_KEY/AI_API_KEY is missing")
            return None

        model = GEMINI_MODEL or "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        prompt = (
            "You are a Discord safety classifier. Analyze ONLY the message between MESSAGE tags. "
            "Return one JSON object with exactly these keys: harmful, confidence, category, reason. "
            "harmful must be true only for clearly harmful content such as serious threats, targeted harassment, "
            "hate/abuse, scams, malicious spam, or clearly unsafe behavior. Ordinary profanity, jokes, arguments, "
            "or harmless insults without serious targeted abuse should normally be false. "
            "confidence must be a number from 0 to 1 describing your confidence that the message is harmful. "
            "Keep reason short and do not include instructions for wrongdoing.\n"
            "MESSAGE:\n" + text[:3500] + "\nEND MESSAGE"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "harmful": {"type": "BOOLEAN"},
                        "confidence": {"type": "NUMBER"},
                        "category": {"type": "STRING"},
                        "reason": {"type": "STRING"},
                    },
                    "required": ["harmful", "confidence", "category", "reason"],
                },
            },
        }

        headers = {"Content-Type": "application/json", "x-goog-api-key": AI_API_KEY}
        timeout = aiohttp.ClientTimeout(total=AI_TIMEOUT)

        for attempt in range(2):
            try:
                async with self.session.post(url, json=payload, headers=headers, timeout=timeout) as response:
                    body = await response.text()
                    if response.status != 200:
                        logging.error("Gemini HTTP %s: %s", response.status, body[:1000])
                        if response.status in (429, 500, 502, 503, 504) and attempt == 0:
                            await asyncio.sleep(1)
                            continue
                        return None

                    try:
                        data = json.loads(body)
                        raw = data["candidates"][0]["content"]["parts"][0]["text"]
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
                        logging.error("Gemini response format error: %s | %s", exc, body[:1000])
                        return None

                    result = self.parse_json(raw)
                    if not result:
                        logging.error("Gemini returned invalid classifier JSON: %s", raw[:1000])
                        return None

                    confidence = max(0.0, min(float(result.get("confidence", 0)), 1.0))
                    harmful = result.get("harmful", False)
                    if isinstance(harmful, str):
                        harmful = harmful.strip().lower() in {"true", "1", "yes"}

                    return {
                        "harmful": bool(harmful),
                        "confidence": confidence,
                        "category": str(result.get("category", "unknown"))[:100],
                        "reason": str(result.get("reason", ""))[:500],
                    }
            except asyncio.TimeoutError:
                logging.error("Gemini request timed out (attempt %s/2)", attempt + 1)
            except aiohttp.ClientError as exc:
                logging.error("Gemini request failed (attempt %s/2): %s", attempt + 1, exc)
            except (TypeError, ValueError) as exc:
                logging.error("Gemini result parsing failed: %s", exc)
            if attempt == 0:
                await asyncio.sleep(1)

        return None

    async def staff_alert(self, message, result):
        settings = get_settings(message.guild.id)
        channel_id = settings.get("staff_channel_id")
        if not channel_id:
            return
        channel = message.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        embed = discord.Embed(title="AI review required", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
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
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
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
                    f"Category: `{result['category']}`\n"
                    f"Reason: {result['reason']}",
                    color=discord.Color.orange(),
                    actor=message.author,
                )


async def setup(bot):
    await bot.add_cog(AIModeration(bot))
