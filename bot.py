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
                "reply_mode": uinfo.get("reply_mode", "TAG_ONLY"), # TAG_ONLY ya ALL_MESSAGES
                "ai_type": uinfo.get("ai_type", "GEMINI_AI"),     # GEMINI_AI ya NORMAL_MSG
                "active_chats": list(uinfo.get("active_chats", set()))
            }
        with open(DATA_FILE, "w") as f:
            json.dump(serializable_data, f)
    except Exception as e:
        print(f"Error saving DB: {e}")

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
        "reply_mode": uinfo.get("reply_mode", "TAG_ONLY"),
        "ai_type": uinfo.get("ai_type", "GEMINI_AI"),
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

# EXTENSIVE NATURAL HINGLISH SMART NORMAL MESSAGES
SMART_FALLBACKS = [
    "Arey bilkul sahi baat kahi aapne! 🔥",
    "Haha true dost, main bhi wahi soch raha tha! 😎✨",
    "Sahi hai boss! Aage ka kya scene hai phir? 🥂",
    "Arre wah, ye toh zabardast point hai! 🎯",
    "Acha ji? Samjha samjha, bilkul sahi! 👍",
    "Sahi ja rahe ho yaar, maza aa gaya sunke! 🚀",
    "Bhai thoda busy hu yaar, 2 min me ache se baat karte hain! 🏃‍♂️",
    "Ekdum mast life chal rahi hai bhai, tum batao apna! 😎✨",
    "Haan batao bhai, main sun raha hu! 🎧",
    "Sahi hai yaar, aur batao kya chal raha hai aajkal? 🍻",
    "Haha lol, ye sahi tha vaise! 😂",
    "Sahi me yaar, ab kya hi bolu ispe! 🙌",
    "Arey waah, sahi khel gaye guru! 😉",
    "Aur sab badhiya? Baki ghar me sab kaise hain? 🏡",
    "Arre bilkul bhai, tension mat lo sab sahi hoga! 👍✨",
    "Haha mast joke tha ye waise! 🤣",
    "Bhai baaki sab toh theek hai, tum batao kya plan hai? 🤔",
    "Sahi hai yaar, enjoy karo mast! 🎉",
    "Arey waah, kya baat hai! 🔥👌",
    "Haan haan bilkul, sahi keh rahe ho! 💯",
    "Bhai 1 minute ruko, thoda sa kaam nipta ke aata hu! ⏳",
    "Oho, ye baat hai kya! Phir toh sahi hai 👍",
    "Sahi baat hai boss, point toh hai tumhari baat me! 💯",
    "Arey wah! Ye kab hua? 😮",
    "Chalo achhi baat hai, sab badiya hi hona chahiye! 😊",
    "Haha ekdum sahi pakde hain! 😁",
    "Waah bhai waah, maza aa gaya! 👏",
    "Bhai tu toh ekdum heavy driver nikla! 😎🏎️",
    "Sahi scene hai yaar, chalte raho aise hi! 🚀",
    "Bilkul bhai, hamesha ready hain hum toh! 🤜🤛",
    "Acha aisi baat hai kya? Mujhe toh pata hi nahi tha! 😄",
    "Maza aa gaya bhai baat karke, aur batao! 🥂"
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

# Multi-Model Smart AI Generator
def generate_ai_response_safely(ai_client, text, sys_prompt):
    models_to_try = ["gemini-3.8-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    for model_name in models_to_try:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=text,
                config=types.GenerateContentConfig(system_instruction=sys_prompt)
            )
            if response and response.text:
                return response.text
        except Exception as err:
            print(f"Model {model_name} failed/busy: {err}")
            continue
    return None

async def run_userbot(user_id, api_id, api_hash, session_string, gemini_key):
    while user_data.get(user_id, {}).get("is_active", False):
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
            add_user_log(user_id, "Account Online & Connected to Telegram!")

            me = await client.get_me()
            my_id = me.id
            my_username = f"@{me.username}" if me.username else ""
            my_firstname = me.first_name if me.first_name else ""

            @client.on(events.NewMessage(pattern=r'\.aion', outgoing=True))
            async def turn_on(event):
                if not user_data.get(user_id, {}).get("is_active", True):
                    return
                chat_id = event.chat_id
                user_data[user_id]["active_chats"].add(chat_id)
                save_db()
                mode = user_data.get(user_id, {}).get("reply_mode", "TAG_ONLY")
                ai_type = user_data.get(user_id, {}).get("ai_type", "GEMINI_AI")
                add_user_log(user_id, f"Activated in Chat {chat_id} (Mode: {mode}, Type: {ai_type})")
                try:
                    await event.edit(f"🟩 **[ACTIVATED] Mode: {mode} | Reply Engine: {ai_type}**")
                except:
                    pass

            @client.on(events.NewMessage(pattern=r'\.aioff', outgoing=True))
            async def turn_off(event):
                chat_id = event.chat_id
                if chat_id in user_data[user_id]["active_chats"]:
                    user_data[user_id]["active_chats"].remove(chat_id)
                    save_db()
                add_user_log(user_id, f"Deactivated in Chat: {chat_id}")
                try:
                    await event.edit("ff **[STOPPED] Auto-Reply Turned OFF for THIS Group!**")
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
                
                if event.out:
                    return

                if event.is_channel and not getattr(event.chat, 'megagroup', False) and not getattr(event.chat, 'gigagroup', False):
                    return

                reply_mode = user_data.get(user_id, {}).get("reply_mode", "TAG_ONLY")
                ai_type = user_data.get(user_id, {}).get("ai_type", "GEMINI_AI")

                # IF MODE IS 'TAG_ONLY', CHECK FOR TAG / REPLY
                if reply_mode == "TAG_ONLY":
                    is_mentioned = False
                    if event.is_reply:
                        reply_msg = await event.get_reply_message()
                        if reply_msg and reply_msg.sender_id == my_id:
                            is_mentioned = True

                    if not is_mentioned:
                        msg_text = event.raw_text.lower()
                        if my_username and my_username.lower() in msg_text:
                            is_mentioned = True
                        elif my_firstname and my_firstname.lower() in msg_text:
                            is_mentioned = True
                        elif event.mentioned:
                            is_mentioned = True

                    if not is_mentioned:
                        return

                reply_text = None
                add_user_log(user_id, f"Processing Msg in Chat {chat_id}: '{event.raw_text}'")

                try:
                    if ai_type == "GEMINI_AI":
                        sender = await event.get_sender()
                        user_name = sender.first_name if sender and sender.first_name else "Dost"
                        
                        sys_prompt = (
                            f"Aap '{my_firstname}' ke AI Assistant ho. "
                            f"Samne wala user '{user_name}' jo message bhej raha hai, "
                            f"uska ekdum natural, cool, friendly Hinglish me assistant jaisa reply do. "
                            f"Short aur smart reply do with emojis."
                        )

                        await asyncio.sleep(0.5)

                        # Gemini AI Attempt
                        reply_text = generate_ai_response_safely(ai_client, event.raw_text, sys_prompt)
                        if not reply_text:
                            reply_text = random.choice(SMART_FALLBACKS)
                    else:
                        # Normal Mode -> Pure Pre-saved Random Response
                        await asyncio.sleep(0.5)
                        reply_text = random.choice(SMART_FALLBACKS)

                except Exception as api_err:
                    add_user_log(user_id, f"Exception Handled -> Using Normal Msg: {api_err}")
                    reply_text = random.choice(SMART_FALLBACKS)

                if reply_text:
                    try:
                        await event.reply(reply_text)
                        add_user_log(user_id, f"Reply Sent Successfully!")
                    except Exception as send_err:
                        add_user_log(user_id, f"Send Error: {send_err}")
                        await asyncio.sleep(2)

            await client.start()
            running_userbots[user_id] = client
            await client.run_until_disconnected()
            
        except Exception as e:
            add_user_log(user_id, f"Connection Glitch: {e}. Auto-reconnecting in 3 seconds...")
            await asyncio.sleep(3)
            if not user_data.get(user_id, {}).get("is_active", False):
                break

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
    add_user_log(user_id, "Hosting Deactivated by User.")

def get_user_panel_markup(user_id):
    is_active = user_data.get(user_id, {}).get("is_active", False)
    has_session = "session" in user_data.get(user_id, {})
    reply_mode = user_data.get(user_id, {}).get("reply_mode", "TAG_ONLY")
    ai_type = user_data.get(user_id, {}).get("ai_type", "GEMINI_AI")
    
    keyboard = []
    
    if is_active and has_session:
        keyboard.append([InlineKeyboardButton("Stop Hosting 🟥", callback_data="deactivate_host")])
        keyboard.append([InlineKeyboardButton("🟩 STATUS: HOSTING ACTIVE 🟩", callback_data="status_info")])
    else:
        keyboard.append([InlineKeyboardButton("Start Hosting 🟩", callback_data="activate_host")])
        keyboard.append([InlineKeyboardButton("🟥 STATUS: DEACTIVATED 🟥", callback_data="status_info")])
    
    # Buttons for Toggle Modes
    mode_btn_text = "🏷️ FILTER: TAG ONLY" if reply_mode == "TAG_ONLY" else "💬 FILTER: ALL MESSAGES"
    ai_btn_text = "🤖 ENGINE: GEMINI AI" if ai_type == "GEMINI_AI" else "💬 ENGINE: NORMAL MSG"
    
    keyboard.append([
        InlineKeyboardButton(mode_btn_text, callback_data="toggle_reply_mode"),
        InlineKeyboardButton(ai_btn_text, callback_data="toggle_ai_type")
    ])
    
    keyboard.append([
        InlineKeyboardButton("🟦 LIVE LOGS 🟦", callback_data="view_my_logs"),
        InlineKeyboardButton("🟩 TEST AI KEY 🟩", callback_data="test_ai")
    ])

    keyboard.append([InlineKeyboardButton("🟧 RE-ENTER SETUP DATA 🟧", callback_data="start_setup")])

    if OWNER_ID and user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("👑 OWNER CONTROL PANEL 👑", callback_data="owner_panel")])
        
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    is_subbed = await check_subscription(context.bot, user_id)
    if not is_subbed:
        keyboard = [
            [InlineKeyboardButton("🟦 JOIN OFFICIAL CHANNEL 🟦", url=f"https://t.me/{FORCE_CHANNEL.replace('@', '')}")],
            [InlineKeyboardButton("🟩 VERIFY SUBSCRIPTION 🟩", callback_data="check_sub")]
        ]
        await update.message.reply_text(
            "🟥 **ACCESS DENIED!**\n\nPehle official channel join karein!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    text = (
        "👋 **Welcome to VIP AI & Normal Userbot Control Panel!**\n\n"
        "Control Panel me buttons dabakar choose karein:\n"
        "• **FILTER**: Tag Only ya All Messages\n"
        "• **ENGINE**: Gemini AI ya Normal Messages"
    )
    await update.message.reply_text(text, reply_markup=get_user_panel_markup(user_id))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "check_sub":
        if await check_subscription(context.bot, user_id):
            await query.edit_message_text(
                "🟩 **VERIFIED SUCCESSFULLY!**\n\nWelcome! Apne control panel se manage karein:",
                reply_markup=get_user_panel_markup(user_id)
            )
        else:
            await query.answer("Pehle channel join karein!", show_alert=True)

    elif query.data == "deactivate_host":
        await stop_userbot(user_id)
        await query.edit_message_text(
            "libre **HOSTING DEACTIVATED!**\n\nUserbot ab off hai.",
            reply_markup=get_user_panel_markup(user_id)
        )

    elif query.data == "activate_host":
        uinfo = user_data.get(user_id, {})
        if "session" in uinfo and uinfo["session"]:
            user_data[user_id]["is_active"] = True
            save_db()
            await query.edit_message_text("🟦 **ACTIVATING HOSTING...** Please wait...")
            asyncio.create_task(run_userbot(
                user_id, uinfo["api_id"], uinfo["api_hash"], uinfo["session"], uinfo["gemini_key"]
            ))
            await asyncio.sleep(1)
            await query.edit_message_text(
                "🟩 **HOSTING ACTIVATED SUCCESSFULLY!**",
                reply_markup=get_user_panel_markup(user_id)
            )
        else:
            await query.answer("❌ Pehle 'RE-ENTER SETUP DATA' par click karke details submit karein!", show_alert=True)

    elif query.data == "toggle_reply_mode":
        current_mode = user_data.get(user_id, {}).get("reply_mode", "TAG_ONLY")
        new_mode = "ALL_MESSAGES" if current_mode == "TAG_ONLY" else "TAG_ONLY"
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]["reply_mode"] = new_mode
        save_db()
        await query.answer(f"Filter Switched to: {new_mode}", show_alert=True)
        await query.edit_message_reply_markup(reply_markup=get_user_panel_markup(user_id))

    elif query.data == "toggle_ai_type":
        current_type = user_data.get(user_id, {}).get("ai_type", "GEMINI_AI")
        new_type = "NORMAL_MSG" if current_type == "GEMINI_AI" else "GEMINI_AI"
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]["ai_type"] = new_type
        save_db()
        await query.answer(f"Engine Switched to: {new_type}", show_alert=True)
        await query.edit_message_reply_markup(reply_markup=get_user_panel_markup(user_id))

    elif query.data == "test_ai":
        uinfo = user_data.get(user_id, {})
        key = uinfo.get("gemini_key")
        if not key:
            await query.answer("❌ Pehle setup complete karein! Key nahi mili.", show_alert=True)
            return
        await query.answer("Testing AI Key...", show_alert=False)
        try:
            ai_client = genai.Client(api_key=key)
            res = generate_ai_response_safely(ai_client, "Hello, say Working!", "Be brief.")
            if res:
                await query.answer("Key Working Perfectly!", show_alert=True)
            else:
                await query.answer("AI busy, but fallback system active hai!", show_alert=True)
        except Exception as e:
            await query.answer(f"Test Failed: {e}", show_alert=True)

    elif query.data == "view_my_logs":
        logs = user_logs.get(user_id, [])
        logs_text = "\n".join(logs[-12:]) if logs else "Koi logs abhi tak record nahi hue hain."
        keyboard = [
            [InlineKeyboardButton("Refresh Live Logs 🟥", callback_data="view_my_logs")],
            [InlineKeyboardButton("Back to Panel 🟦", callback_data="main_menu")]
        ]
        await query.edit_message_text(
            f"📋 **YOUR REAL-TIME USERBOT LOGS:**\n\n```text\n{logs_text}\n```",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "owner_panel":
        if user_id != OWNER_ID:
            await query.answer("Sirf Owner ke liye hai!", show_alert=True)
            return
        active_count = len(running_userbots)
        total_users = len(user_data)
        keyboard = [
            [InlineKeyboardButton("Refresh Panel 🔴", callback_data="owner_panel")],
            [InlineKeyboardButton("Back to Panel 🟦", callback_data="main_menu")]
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
        await update.message.reply_text("🟩 **API ID Saved!**\n\n📝 **Step 2/4: API HASH**\n\nAb apni **API HASH** bhejo:")

    elif step == "API_HASH":
        user_data[user_id]["api_hash"] = text
        user_data[user_id]["step"] = "SESSION"
        await update.message.reply_text("🟩 **API Hash Saved!**\n\n📝 **Step 3/4: SESSION STRING**\n\nAb apna **SESSION STRING** bhejo:")

    elif step == "SESSION":
        user_data[user_id]["session"] = text
        user_data[user_id]["step"] = "GEMINI_KEY"
        await update.message.reply_text("🟩 **Session String Saved!**\n\n📝 **Step 4/4: GEMINI API KEY**\n\nAkhir mein apni **GEMINI API KEY** bhejo:")

    elif step == "GEMINI_KEY":
        api_id = user_data[user_id]["api_id"]
        api_hash = user_data[user_id]["api_hash"]
        session = user_data[user_id]["session"]
        gemini_key = text

        user_data[user_id].pop("step", None)
        user_data[user_id]["is_active"] = True
        save_db()
        add_user_log(user_id, "Setup Completed Successfully!")

        await update.message.reply_text(
            "🟩 **Setup Complete & Hosting Started!**\n\n"
            "Account live ho chuka hai! Group me **`.aion`** bhej kar active karein, aur **`.aioff`** se band karein.",
            reply_markup=get_user_panel_markup(user_id)
        )
        asyncio.create_task(run_userbot(user_id, api_id, api_hash, session, gemini_key))

async def startup_reconnect():
    await asyncio.sleep(1)
    for uid, uinfo in user_data.items():
        if uinfo.get("is_active", True) and uinfo.get("session"):
            print(f"Auto-relaunching session for User: {uid}")
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
    
    print("Dual Engine AI Assistant Bot Started Successfully!")
    app.run_polling()
