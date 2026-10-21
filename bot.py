import os
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from google import genai
from google.genai import types

from config import Config

# Google GenAI SDK Client Setup
ai_client = genai.Client(api_key=Config.GEMINI_API_KEY)

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
    await event.edit("✅ **Gemini AI Auto-Reply Activated (Name + Emojis)!**")

@client.on(events.NewMessage(pattern=r'\.aioff', outgoing=True))
async def turn_off_ai(event):
    global AI_ENABLED
    AI_ENABLED = False
    await event.edit("❌ **Gemini AI Auto-Reply Deactivated!**")

@client.on(events.NewMessage())
async def auto_reply(event):
    global AI_ENABLED
    if not AI_ENABLED or not event.raw_text:
        return

    # Commands ko ignore karna
    if event.raw_text.startswith(".aion") or event.raw_text.startswith(".aioff"):
        return

    # Channels ko ignore karke Groups aur PM me chalna
    if event.is_channel:
        chat = await event.get_chat()
        if not getattr(chat, 'megagroup', False) and not getattr(chat, 'gigagroup', False):
            return

    try:
        # Sender Name extraction
        sender = await event.get_sender()
        user_name = sender.first_name if sender and sender.first_name else "Dost"

        sys_instruction = (
            f"{Config.SYSTEM_PROMPT}\n"
            f"Aap abhi '{user_name}' naam ke person se baat kar rahe ho. "
            f"Aapko unka naam '{user_name}' lekar poori izzat, respect aur friendly tone me baat karni hai. "
            f"Ache ache aur natural emojis ka use karo aur Hinglish me short, energetic reply do."
        )

        async with event.client.action(event.chat_id, 'typing'):
            # Google exact model name fix: gemini-3.8-flash
            response = ai_client.models.generate_content(
                model="gemini-3.8-flash",
                contents=event.raw_text,
                config=types.GenerateContentConfig(
                    system_instruction=sys_instruction
                )
            )
            
            if response and response.text:
                await event.reply(response.text)

    except Exception as e:
        print(f"AI Error: {e}")

if __name__ == "__main__":
    print("Telethon AI Userbot is starting...")
    client.start()
    client.run_until_disconnected()
