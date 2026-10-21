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
user_data = {}
recent_logs = []

# Persistent Data Management (Save & Load)
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
        # Convert sets to lists for JSON serialization
        serializable_data = {}
        for uid, uinfo in user_data.items():
            serializable_data[str(uid)] = {
                "api_id": uinfo.get("api_id"),
                "api_hash": uinfo.get("api_hash"),
                "session": uinfo.get("session"),
                "gemini_key": uinfo.get("gemini_key"),
                "is_active": uinfo.get("is_active", True),
                "active_chats": list(uinfo.get("active_chats", set()))
            }
        with open(DATA_FILE, "w") as f:
            json.dump(serializable_data, f)
    except Exception as e:
        print(f"Error saving DB: {e}")

def add_log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    recent_logs.append(log_entry)
    if len(recent_logs) > 25:
        recent_logs.pop(0)
    print(log_entry)

FORCE_CHANNEL = os.getenv("FORCE_CHANNEL", "@YourChannelName")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

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
        add_log(f"⚠️ Force Sub Error: {e}")
    return False

# Background Userbot runner
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
        add_log(f"🟢 Userbot Session Online for User: {user_id}")

        @client.on(events.NewMessage(pattern=r'\.aion', outgoing=True))
        async def turn_on(event):
            if not user_data.get(user_id, {}).get("is_active", True):
                return
            chat_id = event.chat_id
            user_data[user_id]["active_chats"].add(chat_id)
            save_db()
            add_log(f"⚡ [COMMAND] AI Turned ON in Chat: {chat_id}")
            try:
                await event.edit("🔴 **[DANGER MODE ON] Gemini AI Active for THIS Group!** 🔥")
            except:
                pass

        @client.on(events.NewMessage(pattern=r'\.aioff', outgoing=True))
        async def turn_off(event):
            chat_id = event.chat_id
            if chat_id in user_data[user_id].get("active_chats", set()):
                user_data[user_id]["active_chats"].remove(chat_id)
                save_db()
            add_log(f"🛑 [COMMAND] AI Turned OFF in Chat: {chat_id}")
            try:
                await event.edit("⛔ **[STOPPED] AI Auto-Reply Deactivated for THIS Group!** 🛑")
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
            sender_id = event.sender_id
            add_log(f"📩 Incoming Msg in Chat {chat_id} from User {sender_id}")

            try:
                sender = await event.get_sender()
                user_name = sender.first_name if sender and sender.first_name else "Dost"
                
                sys_prompt = (
                    f"Aap abhi '{user_name}' naam ke person se baat kar rahe ho. "
                    f"Aapko unka naam '{user_name}' lekar poori izzat, respect aur friendly tone me baat karni hai. "
                    f"Ache ache aur natural emojis ka use karo aur Hinglish me short, energetic reply do."
                )

                await asyncio.sleep(2)  # Rate limit protection delay

                response = ai_client.models.generate_content(
                    model="gemini-1.5-flash",
                    contents=event.raw_text,
                    config=types.GenerateContentConfig(system_instruction=sys_prompt)
                )
                if response and response.text:
                    reply_text = response.text
                    add_log(f"✨ Gemini AI Generated Reply for Chat: {chat_id}")
            except Exception as api_err:
                add_log(f"⚠️ Gemini API Limit (Fallback Used): {api_err}")
                reply_text = random.choice(FALLBACK_REPLIES)

            if reply_text:
                try:
                    await event.reply(reply_text)
                    add_log(f"🚀 Auto-Reply Sent Successfully in Chat: {chat_id}")
                except Exception as send_err:
                    add_log(f"🛑 Rate-Limit Send Error: {send_err}")
                    await asyncio.sleep(4)

        await client.start()
        running_userbots[user_id] = client
        await client.run_until_disconnected()
        
    except Exception as e:
        add_log(f"❌ Userbot Disconnected/Error for {user_id}: {e}")

async def stop_userbot(user_id):
    if user_id in running_userbots:
        try:
            await running_userbots[user_id].disconnect()
        except Exception as e:
            add_log(f"Error stopping bot for {user_id}: {e}")
        running_userbots.pop(user_id, None)
    if user_id in user_data:
        user_data[user_id]["is_active"] = False
        save_db()
    add_log(f"🛑 Userbot Deactivated for User: {user_id}")

def get_user_panel_markup(user_id):
    is_active = user_data.get(user_id, {}).get("is_active", False)
    has_session = "session" in user_data.get(user_id, {})
    
    keyboard = []
    if not has_session:
        keyboard.append([InlineKeyboardButton("🚀 HOST / SETUP ACCOUNT ⚡", callback_data="start_setup")])
    else:
        if is_active:
            keyboard.append([InlineKeyboardButton("🔴 DEACTIVATE HOSTING (STOP)", callback_data="deactivate_host")])
            status_btn = "🟢 HOSTING STATUS: ACTIVE ⚡"
        else:
            keyboard.append([InlineKeyboardButton("🟢 ACTIVATE HOSTING (START)", callback_data="activate_host")])
            status_btn = "🔴 HOSTING STATUS: DEACTIVATED 🛑"
        
        keyboard.append([InlineKeyboardButton(status_btn, callback_data="status_info")])
        keyboard.append([InlineKeyboardButton("🔄 RE-ENTER ALL DETAILS 📝", callback_data="start_setup")])

    if OWNER_ID and user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("👑 OWNER DANGER PANEL & LOGS 🔴", callback_data="owner_panel")])
        
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    is_subbed = await check_subscription(context.bot, user_id)
    if not is_subbed:
        keyboard = [
            [InlineKeyboardButton("📢 JOIN DANGER CHANNEL 🚨", url=f"https://t.me/{FORCE_CHANNEL.replace('@', '')}")],
            [InlineKeyboardButton("🔄 VERIFY / CHECK AGAIN 🔴", callback_data="check_sub")]
        ]
        await update.message.reply_text(
            "🛑 **ACCESS DENIED!** 🛑\n\nPehle hamare official channel ko join karo!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    text = "👋 **Welcome to AI Userbot Host System!**\n\nNiche Control Panel se apne account hosting ko Manage / Active / Deactive karo 🔥"
    await update.message.reply_text(text, reply_markup=get_user_panel_markup(user_id))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "check_sub":
        if await check_subscription(context.bot, user_id):
            await query.edit_message_text(
                "✅ **VERIFIED SUCCESSFULLY!**\n\nApne Panel se account manage karo:",
                reply_markup=get_user_panel_markup(user_id)
            )
        else:
            await query.answer("❌ Pehle channel join karo boss!", show_alert=True)

    elif query.data == "deactivate_host":
        await stop_userbot(user_id)
        await query.edit_message_text(
            "🔴 **HOSTING DEACTIVATED!**\n\nTumhara userbot ab stop ho chuka hai aur kisi group me auto-reply nahi karega.",
            reply_markup=get_user_panel_markup(user_id)
        )

    elif query.data == "activate_host":
        uinfo = user_data.get(user_id, {})
        if "session" in uinfo:
            await query.edit_message_text("⚡ **ACTIVATING HOSTING...** Please wait...")
            asyncio.create_task(run_userbot(
                user_id,
                uinfo["api_id"],
                uinfo["api_hash"],
                uinfo["session"],
                uinfo["gemini_key"]
            ))
            await asyncio.sleep(2)
            await query.edit_message_text(
                "🟢 **HOSTING ACTIVATED SUCCESSFULLY!**\n\nTumhara Userbot live ho gaya hai! Group me `.aion` bhej kar chalu karo 🔥",
                reply_markup=get_user_panel_markup(user_id)
            )
        else:
            await query.answer("❌ Pehle details setup karo!", show_alert=True)

    elif query.data == "owner_panel":
        if user_id != OWNER_ID:
            await query.answer("⚠️ Access Denied! Sirf Owner ke liye hai!", show_alert=True)
            return
        
        active_count = len(running_userbots)
        total_saved = len(user_data)
        keyboard = [
            [InlineKeyboardButton("🔄 REFRESH PANEL 🔴", callback_data="owner_panel"), InlineKeyboardButton("📋 VIEW LIVE LOGS ⚡", callback_data="view_logs")],
            [InlineKeyboardButton("🔙 BACK TO MAIN MENU 🔵", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"🔴 **DANGER ADMIN CONTROL PANEL** 🔴\n\n"
            f"• Active Running Bots: `{active_count}`\n"
            f"• Total Saved Accounts: `{total_saved}`\n"
            f"• Persistent Storage: `ACTIVE (JSON) 📁`\n"
            f"• System Vibe: `KHATARNAK 🔥`",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "view_logs":
        if user_id != OWNER_ID:
            return
        logs_text = "\n".join(recent_logs[-15:]) if recent_logs else "Koi logs abhi available nahi hain."
        keyboard = [
            [InlineKeyboardButton("🔄 REFRESH LIVE LOGS 🔴", callback_data="view_logs")],
            [InlineKeyboardButton("🔙 BACK TO OWNER PANEL 🔵", callback_data="owner_panel")]
        ]
        await query.edit_message_text(
            f"📋 **REAL-TIME LIVE SYSTEM LOGS:**\n\n```text\n{logs_text}\n```",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "main_menu":
        await query.edit_message_text("👋 **Main Menu:**", reply_markup=get_user_panel_markup(user_id))

    elif query.data == "start_setup":
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]["step"] = "API_ID"
        await query.edit_message_text("📝 **Step 1/4: API ID**\n\nApni Telegram API ID bhejo:")

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
        await update.message.reply_text("✅ **API Hash Saved!**\n\n📝 **Step 3/4: SESSION STRING**\n\nAb apna Telethon **SESSION STRING** bhejo:")

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
        add_log(f"🔥 New Setup Completed & Saved for User: {user_id}")

        await update.message.reply_text(
            "🎉 **Setup Complete & Host Started!** 🔥\n\n"
            "Ab tumhari details save ho chuki hain! Repeat redeploy ke baad bhi ye automatic restart ho jayega.\n"
            "Jis group me AI chalana ho, wahan **`.aion`** bhej kar start karo!",
            reply_markup=get_user_panel_markup(user_id)
        )
        asyncio.create_task(run_userbot(user_id, api_id, api_hash, session, gemini_key))

# Auto Auto-restart saved userbots on system launch
async def startup_reconnect():
    await asyncio.sleep(3)
    saved_db = load_db()
    for uid_str, uinfo in saved_db.items():
        uid = int(uid_str)
        user_data[uid] = {
            "api_id": uinfo.get("api_id"),
            "api_hash": uinfo.get("api_hash"),
            "session": uinfo.get("session"),
            "gemini_key": uinfo.get("gemini_key"),
            "is_active": uinfo.get("is_active", True),
            "active_chats": set(uinfo.get("active_chats", []))
        }
        if uinfo.get("is_active", True) and uinfo.get("session"):
            add_log(f"🔄 Auto-relaunching saved session for User: {uid}")
            asyncio.create_task(run_userbot(
                uid,
                uinfo["api_id"],
                uinfo["api_hash"],
                uinfo["session"],
                uinfo["gemini_key"]
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
    
    print("Manager Bot with Persistent Data & Active/Deactive Control is running...")
    app.run_polling()
