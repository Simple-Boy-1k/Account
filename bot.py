import os
import asyncio
import logging
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from google import genai
from google.genai import types

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

running_userbots = {}
user_data = {}
recent_logs = []

def add_log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    recent_logs.append(log_entry)
    if len(recent_logs) > 20:
        recent_logs.pop(0)
    print(log_entry)

FORCE_CHANNEL = os.getenv("FORCE_CHANNEL", "@YourChannelName")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# Fallback / Random Replies agar Gemini API limit cross ho jaye ya error aaye
FALLBACK_REPLIES = [
    "Arey bhai bilkul! Sahi keh rahe ho aap! 😉🔥",
    "Haha true yaar! Ekdum mast baat boli aapne! 🥂",
    "Sahi hai boss! Main samajh raha hu aapki baat ko. 😎✌️",
    "Acha ji? Phir batao aage kya plan hai phir? 🤔",
    "Kasam se, yeh wali baat ekdam dil pe lag gayi! ❤️✨",
    "Arre wah! Kya baat hai bhai, maza aa gaya sunkar! 🚀",
    "Sahi ja rahe ho dost! Aise hi lage raho! 💯",
    "Hmm, yeh toh socha hi nahi tha maine! Sahi hai waise. 🧐",
    "Arey chhodho in baaton ko, kuch naya sunao! 🍻",
    "Ekdum sahi time par yaad dilaya aapne yeh toh! 🎯",
    "Bhai thoda busy hu yaar, baad me baat karte hain! 🏃‍♂️💨",
    "Acha ji, aisi baat hai kya? Phir toh party banti hai! 🎉",
    "Sahi hai yaar, tumhara koi jawab nahi! 🔥",
    "Bilkul bhai, agree karta hu aapki is baat se! 👍",
    "Arre mere sher! Ekdum faadu jawab diya aapne! 🦁✨"
]

async def check_subscription(bot, user_id):
    if not FORCE_CHANNEL or FORCE_CHANNEL == "@YourChannelName":
        return True
    try:
        member = await bot.get_chat_member(chat_id=FORCE_CHANNEL, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception as e:
        add_log(f"Force Sub Error: {e}")
    return False

# Background Userbot runner with Fallback mechanism
async def run_userbot(user_id, api_id, api_hash, session_string, gemini_key):
    try:
        if user_id in running_userbots:
            await running_userbots[user_id].disconnect()

        client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
        ai_client = genai.Client(api_key=gemini_key)
        
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]["ai_enabled"] = True
        add_log(f"Userbot successfully connected for user ID: {user_id}")

        @client.on(events.NewMessage(pattern=r'\.aion', outgoing=True))
        async def turn_on(event):
            user_data[user_id]["ai_enabled"] = True
            add_log(f"AI Activated (.aion) by user {user_id}")
            try:
                await event.edit("✅ **Gemini AI & Fallback Auto-Reply Activated!**")
            except:
                pass

        @client.on(events.NewMessage(pattern=r'\.aioff', outgoing=True))
        async def turn_off(event):
            user_data[user_id]["ai_enabled"] = False
            add_log(f"AI Deactivated (.aioff) by user {user_id}")
            try:
                await event.edit("❌ **Gemini AI Auto-Reply Deactivated!**")
            except:
                pass

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

            reply_text = None
            try:
                sender = await event.get_sender()
                user_name = sender.first_name if sender and sender.first_name else "Dost"
                
                sys_prompt = (
                    f"Aap abhi '{user_name}' naam ke person se baat kar rahe ho. "
                    f"Aapko unka naam '{user_name}' lekar poori izzat, respect aur friendly tone me baat karni hai. "
                    f"Ache ache aur natural emojis ka use karo aur Hinglish me short, energetic reply do."
                )

                await asyncio.sleep(1)
                # Gemini API call try karenge
                response = ai_client.models.generate_content(
                    model="gemini-1.5-flash",
                    contents=event.raw_text,
                    config=types.GenerateContentConfig(system_instruction=sys_prompt)
                )
                if response and response.text:
                    reply_text = response.text
            except Exception as api_err:
                add_log(f"Gemini Limit/Error (Using Fallback): {api_err}")
                # Agar Gemini fail ho ya limit lage, toh random fallback message utha lo
                reply_text = random.choice(FALLBACK_REPLIES)

            if reply_text:
                try:
                    await event.reply(reply_text)
                    add_log(f"Auto-Reply sent in chat {event.chat_id}")
                except Exception as send_err:
                    add_log(f"Send Error: {send_err}")

        await client.start()
        running_userbots[user_id] = client
        await client.run_until_disconnected()
        
    except Exception as e:
        add_log(f"Failed userbot for {user_id}: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    is_subbed = await check_subscription(context.bot, user_id)
    if not is_subbed:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_CHANNEL.replace('@', '')}")],
            [InlineKeyboardButton("🔄 Joined / Check Again", callback_data="check_sub")]
        ]
        await update.message.reply_text(
            "⚠️ **Access Denied!**\n\nPehle channel join karo phir check karo!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if OWNER_ID and user_id == OWNER_ID:
        keyboard = [
            [InlineKeyboardButton("🚀 Host / Setup Account", callback_data="start_setup")],
            [InlineKeyboardButton("👑 Owner Control & Logs", callback_data="owner_panel")],
            [InlineKeyboardButton("🔵 Bot Status: ONLINE 🟢", callback_data="status")]
        ]
        text = "👑 **Welcome Boss!** Owner Panel ready hai:"
    else:
        keyboard = [
            [InlineKeyboardButton("🚀 Host / Setup Account", callback_data="start_setup")],
            [InlineKeyboardButton("🔵 Bot Status: ONLINE 🟢", callback_data="status")]
        ]
        text = "👋 **Welcome to AI Userbot Host Bot!**\n\nNeeche click karke setup shuru karo:"

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "check_sub":
        if await check_subscription(context.bot, user_id):
            keyboard = [[InlineKeyboardButton("🚀 Host / Setup Account", callback_data="start_setup")]]
            if OWNER_ID and user_id == OWNER_ID:
                keyboard.append([InlineKeyboardButton("👑 Owner Control & Logs", callback_data="owner_panel")])
            await query.edit_message_text("✅ Verified! Ab setup par click karo:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.answer("❌ Pehle channel join karo!", show_alert=True)

    elif query.data == "owner_panel":
        if user_id != OWNER_ID:
            await query.answer("⚠️ Yeh sirf Owner ke liye hai!", show_alert=True)
            return
        
        active_count = len(running_userbots)
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Panel", callback_data="owner_panel"), InlineKeyboardButton("📋 View Live Logs", callback_data="view_logs")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"👑 **Owner Control Panel & Logs**\n\n"
            f"• Active Hosted Userbots: `{active_count}`\n"
            f"• System Status: `Running with Fallback Protection 🚀`",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "view_logs":
        if user_id != OWNER_ID:
            return
        logs_text = "\n".join(recent_logs[-12:]) if recent_logs else "Koi logs abhi available nahi hain."
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Logs", callback_data="view_logs")],
            [InlineKeyboardButton("🔙 Back to Owner Panel", callback_data="owner_panel")]
        ]
        await query.edit_message_text(
            f"📋 **Live System Logs:**\n\n```text\n{logs_text}\n```",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "main_menu":
        keyboard = [[InlineKeyboardButton("🚀 Host / Setup Account", callback_data="start_setup")]]
        if OWNER_ID and user_id == OWNER_ID:
            keyboard.append([InlineKeyboardButton("👑 Owner Control & Logs", callback_data="owner_panel")])
        await query.edit_message_text("👋 **Main Menu:**", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "start_setup":
        user_data[user_id] = {"step": "API_ID"}
        await query.edit_message_text("📝 **Step 1/4: API ID**\n\nApni Telegram API ID bhejo:")

    elif query.data == "ai_on":
        if user_id in user_data:
            user_data[user_id]["ai_enabled"] = True
            await query.edit_message_text("🟢 **AI Status: ACTIVE**", reply_markup=get_control_panel(True))

    elif query.data == "ai_off":
        if user_id in user_data:
            user_data[user_id]["ai_enabled"] = False
            await query.edit_message_text("🔴 **AI Status: INACTIVE**", reply_markup=get_control_panel(False))

def get_control_panel(is_enabled):
    if is_enabled:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔴 Turn OFF AI", callback_data="ai_off")]])
    else:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🟢 Turn ON AI", callback_data="ai_on")]])

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data or "step" not in user_data[user_id]:
        return

    step = user_data[user_id].get("step")
    text = update.message.text.strip()

    if step == "API_ID":
        user_data[user_id]["api_id"] = text
        user_data[user_id]["step"] = "API_HASH"
        await update.message.reply_text("✅ API ID saved!\n\nAb apni **API HASH** bhejo:")

    elif step == "API_HASH":
        user_data[user_id]["api_hash"] = text
        user_data[user_id]["step"] = "SESSION"
        await update.message.reply_text("✅ API Hash saved!\n\nAb apna **SESSION STRING** bhejo:")

    elif step == "SESSION":
        user_data[user_id]["session"] = text
        user_data[user_id]["step"] = "GEMINI_KEY"
        await update.message.reply_text("✅ Session saved!\n\nAkhir mein apni **GEMINI API KEY** bhejo:")

    elif step == "GEMINI_KEY":
        api_id = user_data[user_id]["api_id"]
        api_hash = user_data[user_id]["api_hash"]
        session = user_data[user_id]["session"]
        gemini_key = text

        user_data[user_id].pop("step")
        user_data[user_id]["ai_enabled"] = True
        add_log(f"New user {user_id} completed setup successfully.")

        await update.message.reply_text(
            "🎉 **Setup Complete & Host Started!**\n\nAb group mein `.aion` bhejo aur maza lo!",
            reply_markup=get_control_panel(True)
        )
        asyncio.create_task(run_userbot(user_id, api_id, api_hash, session, gemini_key))

if __name__ == "__main__":
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN missing!")
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))
    
    print("Manager Bot with Fallback & Live Logs is running...")
    app.run_polling()
