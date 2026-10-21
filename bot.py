import os
import json
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

DATA_FILE = "user_sessions.json"
running_userbots = {}
user_logs = {}

# Load DB instantly at startup so session is never lost
def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading DB: {e}")
    return {}

def save_db():
    try:
        serializable_data = {}
        for uid, uinfo in user_data.items():
            serializable_data[str(uid)] = {
                "api_id": uinfo.get("api_id"),
                "api_hash": uinfo.get("api_hash"),
                "session": uinfo.get("session"),
                "gemini_key": uinfo.get("gemini_key"),
                "is_active": uinfo.get("is_active", True),
                "ai_mode": uinfo.get("ai_mode", "HYBRID"),
                "active_chats": list(uinfo.get("active_chats", set()))
            }
        with open(DATA_FILE, "w") as f:
            json.dump(serializable_data, f)
    except Exception as e:
        print(f"Error saving DB: {e}")

# Initialize user_data immediately from saved DB
user_data = {}
saved_db = load_db()
for uid_str, uinfo in saved_db.items():
    uid = int(uid_str)
    user_data[uid] = {
        "api_id": uinfo.get("api_id"),
        "api_hash": uinfo.get("api_hash"),
        "session": uinfo.get("session"),
        "gemini_key": uinfo.get("gemini_key"),
        "is_active": uinfo.get("is_active", True),
        "ai_mode": uinfo.get("ai_mode", "HYBRID"),
        "active_chats": set(uinfo.get("active_chats", []))
    }

def add_user_log(user_id, message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    if user_id not in user_logs:
        user_logs[user_id] = []
    user_logs[user_id].append(log_entry)
    if len(user_logs[user_id]) > 25:
        user_logs[user_id].pop(0)
    print(f"User {user_id} -> {log_entry}")

FORCE_CHANNEL = os.getenv("FORCE_CHANNEL", "@YourChannelName")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

SMART_FALLBACKS = [
    "Arey bilkul sahi baat kahi aapne! 🔥",
    "Haha true dost, main bhi wahi soch raha tha! 😎✨",
    "Sahi hai boss! Aage ka kya scene hai phir? 🥂",
    "Arre wah, ye toh zabardast point hai! 🎯",
    "Acha ji? Samjha samjha, bilkul sahi! 👍",
    "Sahi ja rahe ho yaar, maza aa gaya sunke! 🚀"
]

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

# Advanced Background Userbot Runner
async def run_userbot(user_id, api_id, api_hash, session_string, gemini_key):
    try:
        if user_id in running_userbots:
            try:
                await running_userbots[user_id].disconnect()
            except:
                pass

        client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
        ai_client = genai.Client(api_key=gemini_key)
        
        if user_id not in user_data:
            user_data[user_id] = {}
        if "active_chats" not in user_data[user_id]:
            user_data[user_id]["active_chats"] = set()

        user_data[user_id]["is_active"] = True
        save_db()
        add_user_log(user_id, "🚀 Account Online & Connected to Telegram!")

        @client.on(events.NewMessage(pattern=r'\.aion', outgoing=True))
        async def turn_on(event):
            if not user_data.get(user_id, {}).get("is_active", True):
                return
            chat_id = event.chat_id
            user_data[user_id]["active_chats"].add(chat_id)
            save_db()
            add_user_log(user_id, f"🟢 AI Activated in Group: {chat_id}")
            try:
                await event.edit("🔥 **[AI ACTIVATED] Gemini Smart Auto-Reply is Live in THIS Group!** ⚡")
            except:
                pass

        @client.on(events.NewMessage(pattern=r'\.aioff', outgoing=True))
        async def turn_off(event):
            chat_id = event.chat_id
            if chat_id in user_data[user_id]["active_chats"]:
                user_data[user_id]["active_chats"].remove(chat_id)
                save_db()
            add_user_log(user_id, f"🔴 AI Deactivated in Group: {chat_id}")
            try:
                await event.edit("🛑 **[AI STOPPED] Auto-Reply Turned OFF for THIS Group!** ⛔")
            except:
                pass

        @client.on(events.NewMessage())
        async def handle_incoming(event):
            if not user_data.get(user_id, {}).get("is_active", True):
                return
            chat_id = event.chat_id
            if chat_id not in user_data[user_id].get("active_chats", set()):
                return
            if not event.raw_text or event.raw_text.startswith(".aion") or event.raw_text.startswith(".aioff"):
                return
            if event.is_channel and not getattr(event.chat, 'megagroup', False) and not getattr(event.chat, 'gigagroup', False):
                return

            reply_text = None
            add_user_log(user_id, f"📩 New Message in Chat {chat_id}")

            try:
                sender = await event.get_sender()
                user_name = sender.first_name if sender and sender.first_name else "Dost"
                
                sys_prompt = (
                    f"Aap ek real person ho jo Telegram account se chat kar rahe ho. "
                    f"Aapko samne wale user '{user_name}' ki baat ka exact, context-based aur bilkul accurate reply dena hai. "
                    f"Agar woh pooche ki 'kaise ho', 'kya kar rahe ho', 'account active hai kya', toh naturally Hinglish me jawab do. "
                    f"Reply hamesha short, smart, cool aur friendly rakho. Emojis ka ache se use karo."
                )

                await asyncio.sleep(1.2)

                response = ai_client.models.generate_content(
                    model="gemini-1.5-flash",
                    contents=event.raw_text,
                    config=types.GenerateContentConfig(system_instruction=sys_prompt)
                )
                if response and response.text:
                    reply_text = response.text
                    add_user_log(user_id, f"✨ Gemini AI Generated Exact Context Reply")
            except Exception as api_err:
                add_user_log(user_id, f"⚠️ Gemini Limit/Error: {api_err}")
                mode = user_data.get(user_id, {}).get("ai_mode", "HYBRID")
                if mode == "HYBRID":
                    reply_text = random.choice(SMART_FALLBACKS)

            if reply_text:
                try:
                    await event.reply(reply_text)
                    add_user_log(user_id, f"✅ Auto-Reply Sent Successfully!")
                except Exception as send_err:
                    add_user_log(user_id, f"❌ Send Rate Limit Error: {send_err}")
                    await asyncio.sleep(3)

        await client.start()
        running_userbots[user_id] = client
        await client.run_until_disconnected()
        
    except Exception as e:
        add_user_log(user_id, f"❌ Userbot Stopped/Error: {e}")

async def stop_userbot(user_id):
    if user_id in running_userbots:
        try:
            await running_userbots[user_id].disconnect()
        except:
            pass
        running_userbots.pop(user_id, None)
    if user_id in user_data:
        user_data[user_id]["is_active"] = False
        save_db()
    add_user_log(user_id, "🔴 Hosting Deactivated by User.")

def get_user_panel_markup(user_id):
    is_active = user_data.get(user_id, {}).get("is_active", False)
    has_session = "session" in user_data.get(user_id, {})
    ai_mode = user_data.get(user_id, {}).get("ai_mode", "HYBRID")
    
    keyboard = []
    if not has_session:
        keyboard.append([InlineKeyboardButton("🚀 HOST / SETUP ACCOUNT NOW ⚡", callback_data="start_setup")])
    else:
        if is_active:
            keyboard.append([InlineKeyboardButton("🔴 DEACTIVATE HOSTING 🛑", callback_data="deactivate_host")])
            status_text = "🟢 STATUS: HOSTING ACTIVE ⚡"
        else:
            keyboard.append([InlineKeyboardButton("🟢 ACTIVATE HOSTING 🚀", callback_data="activate_host")])
            status_text = "🔴 STATUS: DEACTIVATED ⛔"
        
        keyboard.append([InlineKeyboardButton(status_text, callback_data="status_info")])
        keyboard.append([
            InlineKeyboardButton("📊 LIVE LOGS", callback_data="view_my_logs"),
            InlineKeyboardButton(f"⚙️ MODE: {ai_mode}", callback_data="toggle_mode")
        ])
        keyboard.append([
            InlineKeyboardButton("💬 TEST AI KEY", callback_data="test_ai"),
            InlineKeyboardButton("🔄 RE-ENTER DATA 📝", callback_data="start_setup")
        ])

    if OWNER_ID and user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("👑 OWNER DANGER CONTROL PANEL 🚨", callback_data="owner_panel")])
        
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    is_subbed = await check_subscription(context.bot, user_id)
    if not is_subbed:
        keyboard = [
            [InlineKeyboardButton("📢 JOIN OFFICIAL CHANNEL 🚨", url=f"https://t.me/{FORCE_CHANNEL.replace('@', '')}")],
            [InlineKeyboardButton("🔄 VERIFY SUBSCRIPTION 🔴", callback_data="check_sub")]
        ]
        await update.message.reply_text(
            "🛑 **ACCESS DENIED!** 🛑\n\nPehle official channel join karein!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    text = (
        "👋 **Welcome to VIP AI Userbot Hosting Panel!**\n\n"
        "Apka account already saved hai. Niche panel se status check karein! 🔥"
    )
    await update.message.reply_text(text, reply_markup=get_user_panel_markup(user_id))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "check_sub":
        if await check_subscription(context.bot, user_id):
            await query.edit_message_text(
                "✅ **VERIFIED SUCCESSFULLY!**\n\nWelcome! Apne control panel se manage karein:",
                reply_markup=get_user_panel_markup(user_id)
            )
        else:
            await query.answer("❌ Pehle channel join karein boss!", show_alert=True)

    elif query.data == "deactivate_host":
        await stop_userbot(user_id)
        await query.edit_message_text(
            "🔴 **HOSTING DEACTIVATED!**\n\nUserbot ab off hai.",
            reply_markup=get_user_panel_markup(user_id)
        )

    elif query.data == "activate_host":
        uinfo = user_data.get(user_id, {})
        if "session" in uinfo:
            user_data[user_id]["is_active"] = True
            save_db()
            await query.edit_message_text("⚡ **ACTIVATING HOSTING...**")
            asyncio.create_task(run_userbot(
                user_id, uinfo["api_id"], uinfo["api_hash"], uinfo["session"], uinfo["gemini_key"]
            ))
            await asyncio.sleep(1)
            await query.edit_message_text(
                "🟢 **HOSTING ACTIVATED SUCCESSFULLY!** 🔥",
                reply_markup=get_user_panel_markup(user_id)
            )
        else:
            await query.answer("❌ Pehle account setup karein!", show_alert=True)

    elif query.data == "toggle_mode":
        current_mode = user_data.get(user_id, {}).get("ai_mode", "HYBRID")
        new_mode = "AI_ONLY" if current_mode == "HYBRID" else "HYBRID"
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]["ai_mode"] = new_mode
        save_db()
        await query.answer(f"✅ Mode Changed to: {new_mode}", show_alert=True)
        await query.edit_message_reply_markup(reply_markup=get_user_panel_markup(user_id))

    elif query.data == "test_ai":
        uinfo = user_data.get(user_id, {})
        key = uinfo.get("gemini_key")
        if not key:
            await query.answer("❌ Gemini Key Nahi Mili!", show_alert=True)
            return
        await query.answer("🧪 Testing Gemini AI Key...", show_alert=False)
        try:
            ai_client = genai.Client(api_key=key)
            res = ai_client.models.generate_content(model="gemini-1.5-flash", contents="Hello, say Working!")
            if res and res.text:
                await query.answer(f"✅ Key Working Perfectly!", show_alert=True)
        except Exception as e:
            await query.answer(f"❌ Test Failed: {e}", show_alert=True)

    elif query.data == "view_my_logs":
        logs = user_logs.get(user_id, [])
        logs_text = "\n".join(logs[-12:]) if logs else "Koi logs abhi tak record nahi hue hain."
        keyboard = [
            [InlineKeyboardButton("🔄 REFRESH LOGS 🔴", callback_data="view_my_logs")],
            [InlineKeyboardButton("🔙 BACK TO PANEL 🔵", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"📋 **YOUR REAL-TIME USERBOT LOGS:**\n\n```text\n{logs_text}\n```",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "owner_panel":
        if user_id != OWNER_ID:
            await query.answer("⚠️ Sirf Owner ke liye hai!", show_alert=True)
            return
        active_count = len(running_userbots)
        total_users = len(user_data)
        keyboard = [
            [InlineKeyboardButton("🔄 REFRESH PANEL 🔴", callback_data="owner_panel")],
            [InlineKeyboardButton("🔙 BACK TO MAIN MENU 🔵", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"👑 **OWNER ADMIN PANEL** 👑\n\n• Active Bots: `{active_count}`\n• Total Accounts: `{total_users}`",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "main_menu":
        await query.edit_message_text("👋 **VIP Hosting Dashboard:**", reply_markup=get_user_panel_markup(user_id))

    elif query.data == "start_setup":
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]["step"] = "API_ID"
        await query.edit_message_text("📝 **Step 1/4: API ID**\n\nApni Telegram **API ID** bhejo:")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data or "step" not in user_data[user_id]:
        return

    step = user_data[user_id].get("step")
    text = update.message.text.strip()

    if step == "API_ID":
        user_data[user_id]["api_id"] = text
        user_data[user_id]["step"] = "API_HASH"
        await update.message.reply_text("✅ **API ID Saved!**\n\n📝 **Step 2/4: API HASH**\n\nAb apni **API HASH** bhejo:")

    elif step == "API_HASH":
        user_data[user_id]["api_hash"] = text
        user_data[user_id]["step"] = "SESSION"
        await update.message.reply_text("✅ **API Hash Saved!**\n\n📝 **Step 3/4: SESSION STRING**\n\nAb apna **SESSION STRING** bhejo:")

    elif step == "SESSION":
        user_data[user_id]["session"] = text
        user_data[user_id]["step"] = "GEMINI_KEY"
        await update.message.reply_text("✅ **Session String Saved!**\n\n📝 **Step 4/4: GEMINI API KEY**\n\nAkhir mein apni **GEMINI API KEY** bhejo:")

    elif step == "GEMINI_KEY":
        api_id = user_data[user_id]["api_id"]
        api_hash = user_data[user_id]["api_hash"]
        session = user_data[user_id]["session"]
        gemini_key = text

        user_data[user_id].pop("step", None)
        user_data[user_id]["is_active"] = True
        save_db()
        add_user_log(user_id, "🔥 Setup Completed Successfully!")

        await update.message.reply_text(
            "🎉 **Setup Complete & Hosting Started!** 🔥\n\n"
            "Account live ho chuka hai! Group me **`.aion`** bhej kar AI active karein.",
            reply_markup=get_user_panel_markup(user_id)
        )
        asyncio.create_task(run_userbot(user_id, api_id, api_hash, session, gemini_key))

# Auto-reconnect saved userbots instantly at startup
async def startup_reconnect():
    await asyncio.sleep(1)
    for uid, uinfo in user_data.items():
        if uinfo.get("is_active", True) and uinfo.get("session"):
            add_log_msg = f"🔄 Auto-relaunching session for User: {uid}"
            print(add_log_msg)
            asyncio.create_task(run_userbot(
                uid, uinfo["api_id"], uinfo["api_hash"], uinfo["session"], uinfo["gemini_key"]
            ))

if __name__ == "__main__":
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN missing!")
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))
    
    loop = asyncio.get_event_loop()
    loop.create_task(startup_reconnect())
    
    print("Manager Bot is running with instant persistent session load...")
    app.run_polling()
