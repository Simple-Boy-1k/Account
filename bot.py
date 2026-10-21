import os
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from google import genai
from google.genai import types

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Global storage
running_userbots = {}
user_data = {}  # {user_id: {"api_id": ..., "api_hash": ..., "session": ..., "gemini_key": ..., "step": ..., "ai_enabled": False}}

# Force Subscribe Channel Username
FORCE_CHANNEL = os.getenv("FORCE_CHANNEL", "@YourChannelName")

async def check_subscription(bot, user_id):
    if not FORCE_CHANNEL or FORCE_CHANNEL == "@YourChannelName":
        return True
    try:
        member = await bot.get_chat_member(chat_id=FORCE_CHANNEL, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception as e:
        print(f"Force Sub Check Error: {e}")
    return False

# Background Userbot runner with AI logic
async def run_userbot(user_id, api_id, api_hash, session_string, gemini_key):
    try:
        if user_id in running_userbots:
            await running_userbots[user_id].disconnect()

        client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
        ai_client = genai.Client(api_key=gemini_key)
        
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]["ai_enabled"] = False

        @client.on(events.NewMessage(pattern=r'\.aion', outgoing=True))
        async def turn_on(event):
            user_data[user_id]["ai_enabled"] = True
            await event.edit("✅ **Gemini AI Auto-Reply Activated via Bot!**")

        @client.on(events.NewMessage(pattern=r'\.aioff', outgoing=True))
        async def turn_off(event):
            user_data[user_id]["ai_enabled"] = False
            await event.edit("❌ **Gemini AI Auto-Reply Deactivated!**")

        @client.on(events.NewMessage())
        async def handle_incoming(event):
            if not user_data[user_id].get("ai_enabled", False) or not event.raw_text:
                return
            if event.raw_text.startswith(".aion") or event.raw_text.startswith(".aioff"):
                return
            if event.is_channel:
                chat = await event.get_chat()
                if not getattr(chat, 'megagroup', False) and not getattr(chat, 'gigagroup', False):
                    return
            try:
                sender = await event.get_sender()
                user_name = sender.first_name if sender and sender.first_name else "Dost"
                
                sys_prompt = (
                    f"Aap abhi '{user_name}' naam ke person se baat kar rahe ho. "
                    f"Aapko unka naam '{user_name}' lekar poori izzat, respect aur friendly tone me baat karni hai. "
                    f"Ache ache aur natural emojis ka use karo aur Hinglish me short, energetic reply do."
                )

                await asyncio.sleep(1)
                response = ai_client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=event.raw_text,
                    config=types.GenerateContentConfig(system_instruction=sys_prompt)
                )
                if response and response.text:
                    await event.reply(response.text)
            except Exception as e:
                print(f"Userbot Error for user {user_id}: {e}")

        await client.start()
        running_userbots[user_id] = client
        print(f"Successfully hosted userbot for user: {user_id}")
        await client.run_until_disconnected()
        
    except Exception as e:
        print(f"Failed to start userbot for {user_id}: {e}")

# /start command with Force Subscribe
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    is_subbed = await check_subscription(context.bot, user_id)
    if not is_subbed:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_CHANNEL.replace('@', '')}")],
            [InlineKeyboardButton("🔄 Joined / Check Again", callback_data="check_sub")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⚠️ **Access Denied!**\n\n"
            f"Phle hamare channel {FORCE_CHANNEL} ko join karo, phir 'Joined / Check Again' par click karo!",
            reply_markup=reply_markup
        )
        return

    user_data[user_id] = {"step": "API_ID"}
    await update.message.reply_text(
        "👋 **Welcome to AI Userbot Host Bot!**\n\n"
        "Channel join karne ke liye shukriya ❤️\n"
        "Apne Telegram account ko host karne ke liye sabse pehle apni **API ID** bhejo:"
    )

# Callback query for Force Sub check and Control Panel buttons
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "check_sub":
        is_subbed = await check_subscription(context.bot, user_id)
        if is_subbed:
            user_data[user_id] = {"step": "API_ID"}
            await query.edit_message_text(
                "✅ **Channel Verified Successfully!**\n\n"
                "Ab apne Telegram account ko host karne ke liye apni **API ID** bhejo:"
            )
        else:
            await query.answer("❌ Tumne abhi tak channel join nahi kiya hai!", show_alert=True)

    elif query.data == "ai_on":
        if user_id in user_data:
            user_data[user_id]["ai_enabled"] = True
            await query.edit_message_text(
                "🟢 **Gemini AI Auto-Reply Status: ACTIVE**\n\nTumhara AI auto-reply successfully chalu ho gaya hai! ✨",
                reply_markup=get_control_panel_markup(True)
            )

    elif query.data == "ai_off":
        if user_id in user_data:
            user_data[user_id]["ai_enabled"] = False
            await query.edit_message_text(
                "🔴 **Gemini AI Auto-Reply Status: INACTIVE (Stopped)**\n\nTumhara AI auto-reply rok diya gaya hai! 🛑",
                reply_markup=get_control_panel_markup(False)
            )

def get_control_panel_markup(is_enabled):
    # Telegram inline buttons me colors emojis aur clear action ke sath manage hote hain:
    # 🟢 Green vibe (Turn On) | 🔴 Red danger vibe (Turn Off) | 🔵 Blue vibe (Status/Control)
    if is_enabled:
        keyboard = [
            [InlineKeyboardButton("🔴 Turn OFF AI (Stop)", callback_data="ai_off")],
            [InlineKeyboardButton("🔵 Control Panel: ACTIVE 🟢", callback_data="status")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("🟢 Turn ON AI (Start)", callback_data="ai_on")],
            [InlineKeyboardButton("🔵 Control Panel: INACTIVE 🔴", callback_data="status")]
        ]
    return InlineKeyboardMarkup(keyboard)

# Message handler for step-by-step setup
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data or "step" not in user_data[user_id]:
        await update.message.reply_text("Pehle /start command bhejo bhai!")
        return

    step = user_data[user_id].get("step")
    text = update.message.text.strip()

    if step == "API_ID":
        user_data[user_id]["api_id"] = text
        user_data[user_id]["step"] = "API_HASH"
        await update.message.reply_text("✅ API ID save ho gayi!\n\nAb apni Telegram **API HASH** bhejo:")

    elif step == "API_HASH":
        user_data[user_id]["api_hash"] = text
        user_data[user_id]["step"] = "SESSION"
        await update.message.reply_text("✅ API Hash save ho gayi!\n\nAb apna Telethon **SESSION STRING** bhejo:")

    elif step == "SESSION":
        user_data[user_id]["session"] = text
        user_data[user_id]["step"] = "GEMINI_KEY"
        await update.message.reply_text("✅ Session String save ho gayi!\n\nAb apni **GEMINI API KEY** bhejo:")

    elif step == "GEMINI_KEY":
        api_id = user_data[user_id]["api_id"]
        api_hash = user_data[user_id]["api_hash"]
        session = user_data[user_id]["session"]
        gemini_key = text

        user_data[user_id].pop("step")
        user_data[user_id]["ai_enabled"] = True

        await update.message.reply_text(
            "🎉 **Setup Complete & Host Started!**\n\n"
            "Tumhari saari details mil gayi hain aur userbot background mein live ho gaya hai!\n"
            "Neeche diye gaye colorful control panel se tum kabhi bhi AI ko control kar sakte ho:",
            reply_markup=get_control_panel_markup(True)
        )

        asyncio.create_task(run_userbot(user_id, api_id, api_hash, session, gemini_key))

if __name__ == "__main__":
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is missing!")
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))
    
    print("Manager Bot with Colorful Control Panel is running...")
    app.run_polling()
