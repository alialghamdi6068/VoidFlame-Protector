# VoidFlame Protector

Discord server protection bot with persistent settings, comprehensive logs, Anti-Raid, Anti-Spam, invite protection, trusted members, and Gemini AI moderation.

## Environment

Set these environment variables on the host:

```env
DISCORD_TOKEN=your_discord_bot_token
GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_MODEL=gemini-2.5-flash
AI_ENABLED=true
AI_TIMEOUT_MINUTES=10
```

Never commit real tokens or API keys to GitHub.

## Discord permissions/intents

Enable **Server Members Intent** and **Message Content Intent** in the Discord Developer Portal. The bot needs permissions appropriate to the configured protection actions, especially **Manage Messages**, **Moderate Members**, **View Audit Log**, and access to the configured log/staff/warning channels.

## Initial setup

1. Invite the bot with the required permissions.
2. Start the bot.
3. Use `!لوق #channel` for the comprehensive log room.
4. Use `!انذارات #channel` for warning events.
5. Use `!ادارة #channel` for AI/manual review alerts.
6. Use `!وثوق @member` for trusted members.
7. Use `!حالة الحماية` to verify the configuration.

## AI policy

- **90% or higher harmful confidence:** delete the message and apply a temporary timeout.
- **Below 50% harmful confidence:** send the message to the configured staff room for review.
- AI cannot ban or kick members.
- If Gemini is unavailable, the AI module fails closed and the non-AI protection systems continue running.
