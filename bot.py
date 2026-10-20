import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
import google.generativeai as genai

from config import Config

# Gemini API Configure karna
genai.configure(api_key=Config.GEMINI_API_KEY)

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=Config.SYSTEM_PROMPT
)

app = Client(
    name="ai_userbot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    session_string=Config.SESSION_STRING
)

AI_ENABLED = False

@app.on_message(filters.me & filters.command("aion", prefixes="."))
async def turn_on_ai(client: Client, message: Message):
    global AI_ENABLED
    AI_ENABLED = True
    await message.edit_text("✅ **Gemini AI Auto-Reply Activated!**")

@app.on_message(filters.me & filters.command("aioff", prefixes="."))
async def turn_off_ai(client: Client, message: Message):
    global AI_ENABLED
    AI_ENABLED = False
    await message.edit_text("❌ **Gemini AI Auto-Reply Deactivated!**")

# Strict filter: Sirf Private chats, non-bot, non-channel, non-group messages par chalega
@app.on_message(filters.private & ~filters.me & ~filters.bot & ~filters.channel & ~filters.group)
async def auto_reply(client: Client, message: Message):
    global AI_ENABLED
    if not AI_ENABLED or not message.text:
        return

    try:
        await client.send_chat_action(message.chat.id, "typing")
        response = model.generate_content(message.text)
        await message.reply_text(response.text)
    except Exception as e:
        print(f"Gemini API / Peer Error: {e}")

if __name__ == "__main__":
    print("Gemini AI Userbot is starting...")
    app.run()
