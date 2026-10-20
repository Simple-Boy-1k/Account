import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
import openai

# Config file import kar rahe hain
from config import Config

# OpenAI Key Setup
openai.api_key = Config.OPENAI_API_KEY

# Pyrogram Client Setup
app = Client(
    name="ai_userbot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    session_string=Config.SESSION_STRING
)

# AI Auto-Reply Switch (Default: OFF)
AI_ENABLED = False

@app.on_message(filters.me & filters.command("aion", prefixes="."))
async def turn_on_ai(client: Client, message: Message):
    global AI_ENABLED
    AI_ENABLED = True
    await message.edit_text("✅ **AI Auto-Reply System Activated!**")

@app.on_message(filters.me & filters.command("aioff", prefixes="."))
async def turn_off_ai(client: Client, message: Message):
    global AI_ENABLED
    AI_ENABLED = False
    await message.edit_text("❌ **AI Auto-Reply System Deactivated!**")

@app.on_message(filters.private & ~filters.me & ~filters.bot)
async def auto_reply(client: Client, message: Message):
    global AI_ENABLED
    if not AI_ENABLED:
        return

    await client.send_chat_action(message.chat.id, "typing")

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": Config.SYSTEM_PROMPT},
                {"role": "user", "content": message.text}
            ]
        )
        reply_text = response.choices[0].message.content
        await message.reply_text(reply_text)
    except Exception as e:
        print(f"Error generating AI reply: {e}")

if __name__ == "__main__":
    print("Userbot is starting on Heroku using config...")
    app.run()
