import os
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import google.generativeai as genai

from config import Config

# Gemini API Configure karna
genai.configure(api_key=Config.GEMINI_API_KEY)

# Automatic Model Finder (Jo bhi model available hoga, bot khud utha lega)
selected_model = "gemini-1.5-flash"
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            selected_model = m.name
            break
except Exception as e:
    print(f"Model select karte waqt error: {e}")

print(f"==> Using Gemini Model: {selected_model}")

model = genai.GenerativeModel(
    model_name=selected_model,
    system_instruction=Config.SYSTEM_PROMPT
)

# Telethon Client Setup
client = TelegramClient(
    StringSession(Config.SESSION_STRING),
    Config.API_ID,
    Config.API_HASH
)

AI_ENABLED = False

@client.on(events.NewMessage(pattern=r'\.aion', outgoing=True))
async def turn_on_ai(event):
    global AI_ENABLED
    AI_ENABLED = True
    await event.edit("✅ **Gemini AI Auto-Reply Activated!**")

@client.on(events.NewMessage(pattern=r'\.aioff', outgoing=True))
async def turn_off_ai(event):
    global AI_ENABLED
    AI_ENABLED = False
    await event.edit("❌ **Gemini AI Auto-Reply Deactivated!**")

@client.on(events.NewMessage(incoming=True))
async def auto_reply(event):
    global AI_ENABLED
    if not AI_ENABLED or not event.raw_text:
        return

    if event.is_channel:
        chat = await event.get_chat()
        if not getattr(chat, 'megagroup', False) and not getattr(chat, 'gigagroup', False):
            return

    try:
        async with event.client.action(event.chat_id, 'typing'):
            response = model.generate_content(event.raw_text)
            if response and response.text:
                await event.reply(response.text)
    except Exception as e:
        print(f"AI Error: {e}")

if __name__ == "__main__":
    print("Telethon AI Userbot is starting...")
    client.start()
    client.run_until_disconnected()
