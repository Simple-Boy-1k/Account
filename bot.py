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

# ANSI Color Codes for Terminal Logs
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"

def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"{RED}Error loading DB: {e}{RESET}")
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
                "reply_mode": uinfo.get("reply_mode", "TAG_ONLY"),
                "ai_type": uinfo.get("ai_type", "GEMINI_AI"),
                "active_chats": list(uinfo.get("active_chats", set()))
            }
        with open(DATA_FILE, "w") as f:
            json.dump(serializable_data, f)
    except Exception as e:
        print(f"{RED}Error saving DB: {e}{RESET}")

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

def add_user_log(user_id, message, log_type="info"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    if log_type == "error":
        emoji_icon = "🔴"
        term_color = RED
    elif log_type == "success":
        emoji_icon = "🟢"
        term_color = GREEN
    elif log_type == "warn":
        emoji_icon = "🟡"
        term_color = YELLOW
    else:
        emoji_icon = "🔵"
        term_color = CYAN

    log_entry = f"[{timestamp}] {emoji_icon} {message}"
    if user_id not in user_logs:
        user_logs[user_id] = []
    user_logs[user_id].append(log_entry)
    if len(user_logs[user_id]) > 25:
        user_logs[user_id].pop(0)
    
    print(f"{term_color}User {user_id} -> {log_entry}{RESET}")

FORCE_CHANNEL = os.getenv("FORCE_CHANNEL", "@YourChannelName")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

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
        print(f"{RED}Force Sub Check Error: {e}{RESET}")
    return False

def generate_ai_response_safely(ai_client, text, sys_prompt, user_id=None):
    # Using generalized stable identifiers for Google GenAI SDK
    models_to_try = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-flash"]
    for model_name in models_to_try:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=text,
                config=types.GenerateContentConfig(system_instruction=sys_prompt)
            )
            if response and response.text:
                if user_id:
                    add_user_log(user_id, f"Gemini AI Success [{model_name}]", "success")
                return response.text
        except Exception as err:
            err_msg = str(err)
            if user_id:
                add_user_log(user_id, f"Model {model_name} Error: {err_msg}", "error")
            print(f"{YELLOW}Model {model_name} failed: {err_msg}{RESET}")
            continue
    return None

async def run_userbot(user_id, api_id, api_hash, session_string, gemini_key):
    while user_data.get(user_id, {}).get("is_active", False):
        client = None
        try:
            if user_id in running_userbots:
                try:
                    await running_userbots[user_id].disconnect()
                except:
                    pass

            client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
            ai_client = genai.Client(api_key=gemini_key) if gemini_key else None
            
            if user_id not in user_data:
                user_data[user_id] = {}
            if "active_chats" not in user_data[user_id]:
                user_data[user_id]["active_chats"] = set()

            await client.connect()
            if not await client.is_user_authorized():
                add_user_log(user_id, "Session String Expired/Invalid! Re-enter setup.", "error")
                user_data[user_id]["is_active"] = False
                save_db()
                break

            user_data[user_id]["is_active"] = True
            save_db()
            add_user_log(user_id, "Account Online & Connected to Telegram!", "success")

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
                add_user_log(user_id, f"Activated in Chat {chat_id} (Filter: {mode}, Engine: {ai_type})", "success")
                try:
                    await event.edit(f"🟩 **[ACTIVATED] Filter: {mode} | Engine: {ai_type}**")
                except:
                    pass

            @client.on(events.NewMessage(pattern=r'\.aioff', outgoing=True))
            async def turn_off(event):
                chat_id = event.chat_id
                if chat_id in user_data[user_id]["active_chats"]:
                    user_data[user_id]["active_chats"].remove(chat_id)
                    save_db()
                add_user_log(user_id, f"Deactivated in Chat: {chat_id}", "warn")
                try:
                    await event.edit("🟥 **[STOPPED] Auto-Reply Turned OFF for THIS Group!**")
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
                add_user_log(user_id, f"Incoming Msg in Chat {chat_id}: '{event.raw_text}'", "info")

                try:
                    if ai_type == "GEMINI_AI" and ai_client:
                        sender = await event.get_sender()
                        user_name = sender.first_name if sender and sender.first_name else "Dost"
                        
                        sys_prompt = (
                            f"Aap real person '{my_firstname}' ho. Telegram chat me '{user_name}' se baat kar rahe ho. "
                            f"Ekdum natural, human jaisa, cool, smart aur friendly Hinglish me jawab do. "
                            f"Short aur engaging reply do with emojis like a real online friend."
                        )

                        await asyncio.sleep(0.5)
                        reply_text = generate_ai_response_safely(ai_client, event.raw_text, sys_prompt, user_id)
                        if not reply_text:
                            add_user_log(user_id, "Gemini API failed -> Using Fallback Msg", "warn")
                            reply_text = random.choice(SMART_FALLBACKS)
                    else:
                        if ai_type == "GEMINI_AI" and not ai_client:
                            add_user_log(user_id, "Gemini Key missing! Switched to Normal Message.", "error")
                        await asyncio.sleep(0.5)
                        reply_text = random.choice(SMART_FALLBACKS)

                except Exception as api_err:
                    add_user_log(user_id, f"Exception Error -> {api_err}", "error")
                    reply_text = random.choice(SMART_FALLBACKS)

                if reply_text:
                    try:
                        await event.reply(reply_text)
                        add_user_log(user_id, "Reply Sent Successfully!", "success")
                    except Exception as send_err:
                        add_user_log(user_id, f"Send Error: {send_err}", "error")
                        await asyncio.sleep(2)

            running_userbots[user_id] = client
            await client.run_until_disconnected()
            
        except Exception as e:
            add_user_log(user_id, f"Connection Glitch: {e}. Reconnecting in 5s...", "error")
            if client:
                try:
                    await client.disconnect()
                except:
                    pass
            await asyncio.sleep(5)
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
    add_user_log(user_id, "Hosting Deactivated by User.", "warn")

def get_user_panel_markup(user_id):
    is_active = user_data.get(user_id, {}).get("is_active", False)
    has_session = bool(user_data.get(user_id, {}).get("session"))
    reply_mode = user_data.get(user_id, {}).get("reply_mode", "TAG_ONLY")
    ai_type = user_data.get(user_id, {}).get("ai_type", "GEMINI_AI")
    
    keyboard = []
    
    if is_active and has_session:
        keyboard.append([InlineKeyboardButton("🔴 Stop Hosting Bot", callback_data="deactivate_host")])
        keyboard.append([InlineKeyboardButton("🟢 Status: Hosting Active", callback_data="status_info")])
    else:
        keyboard.append([InlineKeyboardButton("🟢 Start Hosting Bot", callback_data="activate_host")])
        keyboard.append([InlineKeyboardButton("🔴 Status: Deactivated", callback_data="status_info")])
    
    mode_btn_text = "🏷️ Filter: Tag Only (Mention)" if reply_mode == "TAG_ONLY" else "💬 Filter: All Messages"
    ai_btn_text = "🤖 Engine: Gemini AI Smart" if ai_type == "GEMINI_AI" else "💬 Engine: Normal Messages"
    
    keyboard.append([
        InlineKeyboardButton(mode_btn_text, callback_data="toggle_reply_mode"),
        InlineKeyboardButton(ai_btn_text, callback_data="toggle_ai_type")
    ])
    
    keyboard.append([
        InlineKeyboardButton("📋 View Real-Time Logs", callback_data="view_my_logs"),
        InlineKeyboardButton("⚡ Test Gemini API Key", callback_data="test_ai")
    ])

    keyboard.append([InlineKeyboardButton("⚙️ Re-Enter API & Session Setup", callback_data="start_setup")])

    if OWNER_ID and user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("👑 Owner Admin Panel", callback_data="owner_panel")])
        
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    is_subbed = await check_subscription(context.bot, user_id)
    if not is_subbed:
        keyboard = [
            [InlineKeyboardButton("🟦 Join Official Channel", url=f"https://t.me/{FORCE_CHANNEL.replace('@', '')}")],
            [InlineKeyboardButton("🟩 Verify Subscription", callback_data="check_sub")]
        ]
        await update.message.reply_text(
            "🟥 **ACCESS DENIED!**\n\nPehle official channel join karein!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    text = (
        "👋 **Welcome to VIP AI Userbot Control Panel!**\n\n"
        "Control Panel se manage karein:"
    )
    await update.message.reply_text(text, reply_markup=get_user_panel_markup(user_id))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if query.data == "check_sub":
        await query.answer()
        if await check_subscription(context.bot, user_id):
            await query.edit_message_text(
                "🟩 **VERIFIED SUCCESSFULLY!**\n\nWelcome! Apne control panel se manage karein:",
                reply_markup=get_user_panel_markup(user_id)
            )
        else:
            await query.answer("Pehle channel join karein!", show_alert=True)

    elif query.data == "deactivate_host":
        await query.answer("Stopping Hosting...")
        await stop_userbot(user_id)
        try:
            await query.edit_message_text(
                "🔴 **HOSTING DEACTIVATED!**\n\nUserbot ab off hai.",
                reply_markup=get_user_panel_markup(user_id)
            )
        except Exception as e:
            print(f"{RED}Edit error: {e}{RESET}")

    elif query.data == "activate_host":
        uinfo = user_data.get(user_id, {})
        session = uinfo.get("session")
        api_id = uinfo.get("api_id")
        api_hash = uinfo.get("api_hash")
        gemini_key = uinfo.get("gemini_key")

        if session and api_id and api_hash:
            await query.answer("Starting Hosting...")
            user_data[user_id]["is_active"] = True
            save_db()
            
            asyncio.create_task(run_userbot(user_id, api_id, api_hash, session, gemini_key))
            
            try:
                await query.edit_message_text(
                    "🟢 **HOSTING ACTIVATED SUCCESSFULLY!**",
                    reply_markup=get_user_panel_markup(user_id)
                )
            except Exception as e:
                print(f"{RED}Edit error: {e}{RESET}")
        else:
            await query.answer("❌ Pehle 'Re-Enter API & Session Setup' par click karke details submit karein!", show_alert=True)

    elif query.data == "toggle_reply_mode":
        current_mode = user_data.get(user_id, {}).get("reply_mode", "TAG_ONLY")
        new_mode = "ALL_MESSAGES" if current_mode == "TAG_ONLY" else "TAG_ONLY"
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]["reply_mode"] = new_mode
        save_db()
        await query.answer(f"Filter Switched to: {new_mode}", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=get_user_panel_markup(user_id))
        except:
            pass

    elif query.data == "toggle_ai_type":
        current_type = user_data.get(user_id, {}).get("ai_type", "GEMINI_AI")
        new_type = "NORMAL_MSG" if current_type == "GEMINI_AI" else "GEMINI_AI"
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]["ai_type"] = new_type
        save_db()
        await query.answer(f"Engine Switched to: {new_type}", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=get_user_panel_markup(user_id))
        except:
            pass

    elif query.data == "test_ai":
        uinfo = user_data.get(user_id, {})
        key = uinfo.get("gemini_key")
        if not key:
            await query.answer("❌ Pehle setup complete karein! Gemini API Key nahi mili.", show_alert=True)
            return
        await query.answer("Testing Gemini AI Key...", show_alert=False)
        try:
            ai_client = genai.Client(api_key=key)
            res = generate_ai_response_safely(ai_client, "Hello, say Working!", "Be brief.", user_id)
            if res:
                await query.answer("Gemini Key Working Perfectly! 🟢", show_alert=True)
            else:
                await query.answer("❌ API Key test failed! Check logs.", show_alert=True)
        except Exception as e:
            await query.answer(f"Test Failed: {e}", show_alert=True)

    elif query.data == "view_my_logs":
        await query.answer()
        logs = user_logs.get(user_id, [])
        logs_text = "\n".join(logs[-15:]) if logs else "🔴 Koi logs abhi tak record nahi hue hain."
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Live Logs", callback_data="view_my_logs")],
            [InlineKeyboardButton("🔙 Back to Main Panel", callback_data="main_menu")]
        ]
        try:
            await query.edit_message_text(
                f"📋 **YOUR REAL-TIME USERBOT LOGS:**\n\n```text\n{logs_text}\n```",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            pass

    elif query.data == "owner_panel":
        await query.answer()
        if user_id != OWNER_ID:
            await query.answer("Sirf Owner ke liye hai!", show_alert=True)
            return
        active_count = len(running_userbots)
        total_users = len(user_data)
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Panel", callback_data="owner_panel")],
            [InlineKeyboardButton("🔙 Back to Panel", callback_data="main_menu")]
        ]
        try:
            await query.edit_message_text(
                f"👑 **OWNER ADMIN PANEL** 👑\n\n• Active Bots: `{active_count}`\n• Total Accounts: `{total_users}`",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            pass

    elif query.data == "main_menu":
        await query.answer()
        try:
            await query.edit_message_text("👋 **VIP Hosting Dashboard:**", reply_markup=get_user_panel_markup(user_id))
        except:
            pass

    elif query.data == "start_setup":
        await query.answer()
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]["step"] = "API_ID"
        try:
            await query.edit_message_text("📝 **Step 1/4: API ID**\n\nApni Telegram **API ID** bhejo:")
        except:
            pass

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

        user_data[user_id]["gemini_key"] = gemini_key
        user_data[user_id].pop("step", None)
        user_data[user_id]["is_active"] = True
        save_db()
        add_user_log(user_id, "Setup Completed & API Key Saved Successfully!", "success")

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
            print(f"{GREEN}Auto-relaunching session for User: {uid}{RESET}")
            asyncio.create_task(run_userbot(
                uid, uinfo["api_id"], uinfo["api_hash"], uinfo["session"], uinfo.get("gemini_key")
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
    
    print(f"{GREEN}Dual Engine AI Assistant Bot Started Successfully!{RESET}")
    app.run_polling()
