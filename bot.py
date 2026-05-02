# =========================
# ZEDOX BOT - FULLY WORKING RAILWAY DEPLOYMENT
# =========================

import os
import sys
import time
import random
import string
import threading
from datetime import datetime
from functools import wraps

# Force stdout/stderr to be unbuffered for Railway logs
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)

print("=" * 60)
print("🚀 STARTING ZEDOX BOT...")
print("=" * 60)

# Import required modules with error handling
try:
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
    print("✅ Telebot imported")
except Exception as e:
    print(f"❌ Failed to import telebot: {e}")
    sys.exit(1)

try:
    from pymongo import MongoClient
    from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
    print("✅ PyMongo imported")
except Exception as e:
    print(f"❌ Failed to import pymongo: {e}")
    sys.exit(1)

# Get environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")
MONGO_URI = os.environ.get("MONGO_URI")

# Validate required environment variables
if not BOT_TOKEN:
    print("❌ BOT_TOKEN environment variable not set!")
    sys.exit(1)

if not ADMIN_ID:
    print("❌ ADMIN_ID environment variable not set!")
    sys.exit(1)

if not MONGO_URI:
    print("❌ MONGO_URI environment variable not set!")
    sys.exit(1)

try:
    ADMIN_ID = int(ADMIN_ID)
    print(f"✅ Admin ID: {ADMIN_ID}")
except:
    print(f"❌ ADMIN_ID must be a number! Got: {ADMIN_ID}")
    sys.exit(1)

print(f"✅ Bot Token: {BOT_TOKEN[:10]}...")

# Connect to MongoDB with retry logic
print("📡 Connecting to MongoDB...")
max_retries = 5
retry_delay = 3

for attempt in range(max_retries):
    try:
        client = MongoClient(
            MONGO_URI, 
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            socketTimeoutMS=10000,
            retryWrites=True,
            w='majority'
        )
        client.admin.command('ping')
        print("✅ MongoDB connected successfully!")
        break
    except Exception as e:
        print(f"⚠️ MongoDB connection attempt {attempt + 1}/{max_retries} failed: {e}")
        if attempt < max_retries - 1:
            time.sleep(retry_delay)
        else:
            print("❌ Failed to connect to MongoDB after multiple attempts!")
            sys.exit(1)

db = client["zedox_bot"]

# Collections
users_col = db["users"]
folders_col = db["folders"]
codes_col = db["codes"]
config_col = db["config"]
custom_buttons_col = db["custom_buttons"]
admins_col = db["admins"]

print("✅ Database collections initialized")

# Initialize bot
try:
    bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=False)
    bot_info = bot.get_me()
    print(f"✅ Bot initialized: @{bot_info.username}")
except Exception as e:
    print(f"❌ Failed to initialize bot: {e}")
    sys.exit(1)

# =========================
# INITIALIZE ADMINS
# =========================
def init_admins():
    try:
        if not admins_col.find_one({"_id": ADMIN_ID}):
            admins_col.insert_one({
                "_id": ADMIN_ID,
                "username": None,
                "added_by": "system",
                "added_at": time.time(),
                "is_owner": True
            })
            print(f"✅ Admin {ADMIN_ID} initialized")
    except Exception as e:
        print(f"⚠️ Admin init warning: {e}")

init_admins()

# =========================
# CONFIG SYSTEM
# =========================
def get_config():
    try:
        cfg = config_col.find_one({"_id": "config"})
        if not cfg:
            cfg = {
                "_id": "config",
                "force_channels": [],
                "custom_buttons": [],
                "vip_msg": "💎 Buy VIP to unlock premium content! 🚀",
                "welcome": "🔥 Welcome to ZEDOX BOT! Get premium methods, apps, and services! 🎉",
                "ref_reward": 5,
                "notify_new_methods": True,
                "next_folder_number": 1,
                "vip_price": 50,
                "vip_points_price": 5000,
                "referral_vip_count": 50,
                "referral_purchase_count": 10,
                "vip_duration_days": 30,
                "contact_username": None,
                "contact_link": None,
                "vip_contact": None,
                "binance_address": "",
                "binance_coin": "USDT",
                "binance_network": "TRC20",
                "binance_memo": "",
                "payment_methods": ["💳 Binance", "💵 USDT (TRC20)"]
            }
            config_col.insert_one(cfg)
            print("✅ Default config created")
        return cfg
    except Exception as e:
        print(f"⚠️ Config error: {e}")
        return {
            "_id": "config",
            "force_channels": [],
            "custom_buttons": [],
            "vip_msg": "💎 Buy VIP!",
            "welcome": "🔥 Welcome to ZEDOX BOT!",
            "ref_reward": 5,
            "notify_new_methods": True,
            "next_folder_number": 1,
            "vip_price": 50,
            "vip_points_price": 5000,
            "referral_vip_count": 50,
            "referral_purchase_count": 10,
            "vip_duration_days": 30,
            "contact_username": None,
            "contact_link": None,
            "vip_contact": None,
            "binance_address": "",
            "binance_coin": "USDT",
            "binance_network": "TRC20",
            "binance_memo": "",
            "payment_methods": ["💳 Binance", "💵 USDT (TRC20)"]
        }

def set_config(key, value):
    try:
        config_col.update_one({"_id": "config"}, {"$set": {key: value}}, upsert=True)
        return True
    except Exception as e:
        print(f"⚠️ Set config error: {e}")
        return False

# =========================
# USER SYSTEM
# =========================
def get_user(uid):
    uid = str(uid)
    try:
        data = users_col.find_one({"_id": uid})
        if not data:
            data = {
                "_id": uid,
                "points": 0,
                "vip": False,
                "vip_expiry": None,
                "ref": None,
                "refs": 0,
                "refs_who_bought_vip": 0,
                "purchased_methods": [],
                "used_codes": [],
                "username": None,
                "created_at": time.time(),
                "total_earned": 0,
                "total_spent": 0
            }
            users_col.insert_one(data)
        return data
    except Exception as e:
        print(f"⚠️ Get user error: {e}")
        return {"_id": uid, "points": 0, "vip": False}

def save_user(uid, data):
    try:
        users_col.update_one({"_id": str(uid)}, {"$set": data})
        return True
    except Exception as e:
        print(f"⚠️ Save user error: {e}")
        return False

def is_vip(uid):
    data = get_user(uid)
    if data.get("vip", False):
        expiry = data.get("vip_expiry")
        if expiry and expiry < time.time():
            data["vip"] = False
            data["vip_expiry"] = None
            save_user(uid, data)
            return False
        return True
    return False

def get_points(uid):
    return get_user(uid).get("points", 0)

def add_points(uid, amount):
    if amount <= 0:
        return get_points(uid)
    data = get_user(uid)
    data["points"] = data.get("points", 0) + amount
    data["total_earned"] = data.get("total_earned", 0) + amount
    save_user(uid, data)
    return data["points"]

def spend_points(uid, amount):
    if amount <= 0:
        return get_points(uid)
    data = get_user(uid)
    current = data.get("points", 0)
    if current < amount:
        return current
    data["points"] = current - amount
    data["total_spent"] = data.get("total_spent", 0) + amount
    save_user(uid, data)
    return data["points"]

def make_vip(uid, duration_days=None):
    data = get_user(uid)
    data["vip"] = True
    if duration_days and duration_days > 0:
        data["vip_expiry"] = time.time() + (duration_days * 86400)
    else:
        data["vip_expiry"] = None
    save_user(uid, data)

def remove_vip(uid):
    data = get_user(uid)
    data["vip"] = False
    data["vip_expiry"] = None
    save_user(uid, data)

def purchase_method(uid, method_name, price):
    if get_points(uid) >= price:
        spend_points(uid, price)
        data = get_user(uid)
        purchased = data.get("purchased_methods", [])
        if method_name not in purchased:
            purchased.append(method_name)
            data["purchased_methods"] = purchased
            save_user(uid, data)
        return True
    return False

def add_referral(uid):
    data = get_user(uid)
    data["refs"] = data.get("refs", 0) + 1
    save_user(uid, data)
    cfg = get_config()
    if data["refs"] >= cfg.get("referral_vip_count", 50) and not is_vip(uid):
        make_vip(uid, cfg.get("vip_duration_days", 30))
        return True
    return False

# =========================
# FOLDER SYSTEM
# =========================
def add_folder(cat, name, files, price, parent=None, text_content=None):
    cfg = get_config()
    number = cfg.get("next_folder_number", 1)
    set_config("next_folder_number", number + 1)
    
    folder = {
        "cat": cat,
        "name": name,
        "files": files,
        "price": price,
        "parent": parent,
        "number": number,
        "created_at": time.time()
    }
    if text_content:
        folder["text_content"] = text_content
    
    folders_col.insert_one(folder)
    return number

def get_folders(cat, parent=None):
    query = {"cat": cat}
    if parent:
        query["parent"] = parent
    else:
        query["parent"] = {"$in": [None, "", "root"]}
    return list(folders_col.find(query).sort("number", 1))

def get_folder(cat, name, parent=None):
    query = {"cat": cat, "name": name}
    if parent:
        query["parent"] = parent
    return folders_col.find_one(query)

def get_folder_by_number(number):
    return folders_col.find_one({"number": number})

def delete_folder(cat, name, parent=None):
    query = {"cat": cat, "name": name}
    if parent:
        query["parent"] = parent
    result = folders_col.delete_one(query)
    return result.deleted_count > 0

# =========================
# CODE SYSTEM
# =========================
def generate_code(points):
    code = "ZEDOX" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    codes_col.insert_one({
        "_id": code,
        "points": points,
        "used": False,
        "created_at": time.time()
    })
    return code

def redeem_code(code, uid):
    code_data = codes_col.find_one({"_id": code})
    if not code_data:
        return False, 0, "invalid"
    
    if code_data.get("used", False):
        return False, 0, "already_used"
    
    user_data = get_user(uid)
    if code in user_data.get("used_codes", []):
        return False, 0, "already_used_by_user"
    
    points = code_data["points"]
    add_points(uid, points)
    
    codes_col.update_one({"_id": code}, {"$set": {"used": True}})
    
    used_codes = user_data.get("used_codes", [])
    used_codes.append(code)
    user_data["used_codes"] = used_codes
    save_user(uid, user_data)
    
    return True, points, "success"

# =========================
# AUTO EMOJI
# =========================
def add_emoji(name, cat=None):
    emoji_map = {
        "premium": "💎", "vip": "👑", "pro": "⭐",
        "free": "🆓", "basic": "📌",
        "app": "📱", "android": "🤖", "ios": "🍎",
        "service": "⚡", "tool": "🛠️",
        "method": "🔧", "tutorial": "📚",
        "hack": "🎮", "cheat": "🎯",
        "account": "👤", "card": "💳", "crypto": "🪙"
    }
    
    name_lower = name.lower()
    for keyword, emoji in emoji_map.items():
        if keyword in name_lower:
            return f"{emoji} {name}"
    
    if cat == "vip":
        return f"💎 {name}"
    elif cat == "free":
        return f"🆓 {name}"
    elif cat == "apps":
        return f"📱 {name}"
    elif cat == "services":
        return f"⚡ {name}"
    
    return f"📌 {name}"

# =========================
# KEYBOARDS
# =========================
def is_admin(uid):
    if uid == ADMIN_ID:
        return True
    return admins_col.find_one({"_id": uid}) is not None

def get_main_menu(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📂 FREE METHODS", "💎 VIP METHODS")
    kb.add("📱 PREMIUM APPS", "⚡ SERVICES")
    kb.add("💰 MY WALLET", "⭐ BUY VIP")
    kb.add("🎁 REFERRAL", "👤 PROFILE")
    kb.add("🏆 MY PURCHASES", "🎫 REDEEM CODE")
    kb.add("🆔 MY ID")
    
    if is_admin(uid):
        kb.add("⚙️ ADMIN PANEL")
    
    return kb

def get_folders_kb(cat, parent=None, page=0, per_page=10):
    folders = get_folders(cat, parent)
    total = len(folders)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    page = max(0, min(page, total_pages - 1))
    
    start = page * per_page
    end = min(start + per_page, total)
    page_folders = folders[start:end]
    
    kb = InlineKeyboardMarkup(row_width=2)
    
    for folder in page_folders:
        name = folder["name"]
        price = folder.get("price", 0)
        number = folder.get("number", "?")
        has_subs = len(get_folders(cat, name)) > 0
        
        icon = "📁" if has_subs else "📄"
        display = add_emoji(name, cat)
        text = f"{icon} [{number}] {display}"
        if price > 0 and not has_subs:
            text += f" ─ {price}💎"
        
        kb.add(InlineKeyboardButton(text, callback_data=f"open|{cat}|{name}|{parent or ''}"))
    
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"page|{cat}|{page-1}|{parent or ''}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="noop"))
    if end < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"page|{cat}|{page+1}|{parent or ''}"))
    
    if nav:
        kb.row(*nav)
    
    if parent:
        kb.add(InlineKeyboardButton("🔙 BACK", callback_data=f"back|{cat}|{parent}"))
    else:
        kb.add(InlineKeyboardButton("🏠 MAIN MENU", callback_data="main_menu"))
    
    return kb

# =========================
# BOT HANDLERS
# =========================

@bot.message_handler(commands=["start"])
def start_command(message):
    uid = message.from_user.id
    
    # Handle referral
    args = message.text.split()
    if len(args) > 1:
        ref_id = args[1]
        if ref_id != str(uid) and ref_id.isdigit():
            user_data = get_user(uid)
            if not user_data.get("ref"):
                cfg = get_config()
                reward = cfg.get("ref_reward", 5)
                add_points(ref_id, reward)
                add_referral(ref_id)
                user_data["ref"] = ref_id
                save_user(uid, user_data)
    
    # Update username
    if message.from_user.username:
        user_data = get_user(uid)
        user_data["username"] = message.from_user.username
        save_user(uid, user_data)
    
    cfg = get_config()
    welcome = cfg.get("welcome", "🔥 Welcome to ZEDOX BOT!")
    points = get_points(uid)
    
    bot.send_message(uid, 
        f"{welcome}\n\n"
        f"💰 <b>Balance:</b> {points} 💎\n"
        f"👑 <b>VIP:</b> {'✅ Active' if is_vip(uid) else '❌ Not Active'}\n\n"
        f"Use the buttons below! 🚀",
        reply_markup=get_main_menu(uid))

@bot.message_handler(func=lambda m: m.text == "💰 MY WALLET")
def wallet_command(message):
    uid = message.from_user.id
    user = get_user(uid)
    
    text = f"┌─<b>💰 YOUR WALLET</b>─┐\n\n"
    text += f"├ 💎 Points: <code>{user.get('points', 0):,}</code>\n"
    text += f"├ 👑 VIP: <code>{'Yes' if is_vip(uid) else 'No'}</code>\n"
    text += f"├ 👥 Referrals: <code>{user.get('refs', 0)}</code>\n"
    text += f"├ 📈 Total Earned: <code>{user.get('total_earned', 0):,}</code>\n"
    text += f"└ 📉 Total Spent: <code>{user.get('total_spent', 0):,}</code>\n\n"
    text += f"✨ <b>Earn points:</b> Referrals, Redeem codes"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎁 REFERRAL LINK", callback_data="get_referral"))
    bot.send_message(uid, text, reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "👤 PROFILE")
def profile_command(message):
    uid = message.from_user.id
    user = get_user(uid)
    
    text = f"┌─<b>👤 USER PROFILE</b>─┐\n\n"
    text += f"├ 🆔 ID: <code>{uid}</code>\n"
    text += f"├ 📛 Name: {message.from_user.first_name}\n"
    text += f"├ 👑 VIP: <code>{'Yes' if is_vip(uid) else 'No'}</code>\n"
    text += f"├ 💎 Points: <code>{user.get('points', 0):,}</code>\n"
    text += f"├ 📚 Purchased: <code>{len(user.get('purchased_methods', []))}</code>\n"
    text += f"├ 👥 Referrals: <code>{user.get('refs', 0)}</code>\n"
    text += f"└ 📅 Joined: {datetime.fromtimestamp(user.get('created_at', time.time())).strftime('%Y-%m-%d')}"
    
    bot.send_message(uid, text)

@bot.message_handler(func=lambda m: m.text == "🏆 MY PURCHASES")
def purchases_command(message):
    uid = message.from_user.id
    
    if is_vip(uid):
        bot.send_message(uid, "👑 <b>VIP MEMBER</b>\n\nYou have access to ALL VIP methods!")
        return
    
    purchased = get_user(uid).get("purchased_methods", [])
    if not purchased:
        bot.send_message(uid, "📚 <b>No purchased methods</b>\n\nBuy methods from 💎 VIP METHODS!")
        return
    
    text = f"📚 <b>YOUR PURCHASES</b> ({len(purchased)})\n\n"
    for i, method in enumerate(purchased, 1):
        text += f"{i}. {add_emoji(method, 'vip')}\n"
    
    bot.send_message(uid, text)

@bot.message_handler(func=lambda m: m.text == "🎫 REDEEM CODE")
def redeem_command(message):
    msg = bot.send_message(message.from_user.id, "🎫 <b>Enter code:</b>\n\nExample: <code>ZEDOXABC123</code>")
    bot.register_next_step_handler(msg, process_redeem)

def process_redeem(message):
    uid = message.from_user.id
    code = message.text.strip().upper()
    
    success, points, reason = redeem_code(code, uid)
    
    if success:
        bot.send_message(uid, f"✅ <b>Redeemed!</b>\n\n+{points} 💎\n💰 Balance: {get_points(uid)} 💎")
    else:
        errors = {"invalid": "❌ Invalid code!", "already_used": "❌ Code already used!", "already_used_by_user": "❌ You already used this code!"}
        bot.send_message(uid, errors.get(reason, "❌ Invalid code!"))

@bot.message_handler(func=lambda m: m.text == "🎁 REFERRAL")
def referral_command(message):
    uid = message.from_user.id
    user = get_user(uid)
    cfg = get_config()
    
    link = f"https://t.me/{bot.get_me().username}?start={uid}"
    text = f"┌─<b>🎁 REFERRAL PROGRAM</b>─┐\n\n"
    text += f"├ 🔗 <code>{link}</code>\n\n"
    text += f"├ 👥 Referrals: <code>{user.get('refs', 0)}</code>\n"
    text += f"├ 💰 Earned: <code>{user.get('refs', 0) * cfg.get('ref_reward', 5)}</code>\n"
    text += f"└ 🎯 Goal: <code>{user.get('refs', 0)}/{cfg.get('referral_vip_count', 50)}</code>\n\n"
    text += f"✨ +{cfg.get('ref_reward', 5)}💎 per referral\n"
    text += f"✨ {cfg.get('referral_vip_count', 50)} referrals → FREE VIP"
    
    bot.send_message(uid, text)

@bot.message_handler(func=lambda m: m.text == "🆔 MY ID")
def myid_command(message):
    uid = message.from_user.id
    bot.send_message(uid, f"🆔 <b>Your ID:</b> <code>{uid}</code>")

@bot.message_handler(func=lambda m: m.text == "⭐ BUY VIP")
def buy_vip_command(message):
    uid = message.from_user.id
    cfg = get_config()
    
    if is_vip(uid):
        bot.send_message(uid, "👑 <b>You are already VIP!</b>")
        return
    
    text = f"┌─<b>👑 VIP MEMBERSHIP</b>─┐\n\n"
    text += f"├ 💎 Price: {cfg.get('vip_points_price', 5000):,} points\n"
    text += f"├ 💵 USD: ${cfg.get('vip_price', 50)}\n\n"
    text += f"✨ <b>Benefits:</b>\n"
    text += f"• ALL VIP methods\n"
    text += f"• No points needed\n"
    text += f"• Priority support\n\n"
    text += f"💳 Contact admin to purchase with USD"
    
    kb = InlineKeyboardMarkup()
    if get_points(uid) >= cfg.get("vip_points_price", 5000):
        kb.add(InlineKeyboardButton(f"👑 BUY WITH {cfg.get('vip_points_price', 5000):,}💎", callback_data="buy_vip"))
    if cfg.get("vip_contact"):
        contact = cfg.get("vip_contact")
        if contact.startswith("@"):
            kb.add(InlineKeyboardButton("📞 CONTACT", url=f"https://t.me/{contact[1:]}"))
        elif contact.startswith("http"):
            kb.add(InlineKeyboardButton("📞 CONTACT", url=contact))
    
    bot.send_message(uid, text, reply_markup=kb if kb.keyboard else None)

@bot.message_handler(func=lambda m: m.text in ["📂 FREE METHODS", "💎 VIP METHODS", "📱 PREMIUM APPS", "⚡ SERVICES"])
def show_category(message):
    cat_map = {
        "📂 FREE METHODS": "free",
        "💎 VIP METHODS": "vip",
        "📱 PREMIUM APPS": "apps",
        "⚡ SERVICES": "services"
    }
    cat = cat_map.get(message.text)
    folders = get_folders(cat)
    
    if not folders:
        bot.send_message(message.from_user.id, f"📂 <b>{message.text}</b>\n\nNo content available!")
        return
    
    bot.send_message(message.from_user.id, f"📂 <b>{message.text}</b>\n\nSelect:", reply_markup=get_folders_kb(cat))

# =========================
# CALLBACK HANDLERS
# =========================

@bot.callback_query_handler(func=lambda c: c.data.startswith("open|"))
def open_callback(call):
    uid = call.from_user.id
    parts = call.data.split("|")
    cat = parts[1]
    name = parts[2]
    parent = parts[3] if len(parts) > 3 and parts[3] else None
    
    folder = get_folder(cat, name, parent if parent else None)
    if not folder:
        bot.answer_callback_query(call.id, "❌ Not found!")
        return
    
    # Check subfolders
    subfolders = get_folders(cat, name)
    if subfolders:
        kb = InlineKeyboardMarkup(row_width=1)
        for sub in subfolders:
            text = f"📁 [{sub.get('number', '?')}] {add_emoji(sub['name'], cat)}"
            kb.add(InlineKeyboardButton(text, callback_data=f"open|{cat}|{sub['name']}|{name}"))
        kb.add(InlineKeyboardButton("🔙 BACK", callback_data=f"back|{cat}|{parent or ''}"))
        bot.edit_message_text(f"📁 <b>{add_emoji(name, cat)}</b>", uid, call.message.message_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return
    
    # Check access
    price = folder.get("price", 0)
    is_vip_cat = cat == "vip"
    user_vip = is_vip(uid)
    user_owns = name in get_user(uid).get("purchased_methods", [])
    
    if is_vip_cat and not user_vip and not user_owns:
        if price > 0:
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton(f"💰 BUY ({price}💎)", callback_data=f"buy|{cat}|{name}|{price}"),
                InlineKeyboardButton("👑 GET VIP", callback_data="get_vip")
            )
            kb.add(InlineKeyboardButton("❌ CANCEL", callback_data="cancel"))
            bot.edit_message_text(
                f"🔒 <b>{add_emoji(name, cat)}</b>\n\n"
                f"Price: {price} 💎\n"
                f"Balance: {get_points(uid)} 💎",
                uid, call.message.message_id, reply_markup=kb)
        else:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("👑 GET VIP", callback_data="get_vip"))
            bot.edit_message_text(f"🔒 <b>{add_emoji(name, cat)}</b>\n\nVIP only!", uid, call.message.message_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return
    
    # Deduct points
    if price > 0 and not user_vip and not user_owns:
        if get_points(uid) < price:
            bot.answer_callback_query(call.id, f"❌ Need {price}💎!", True)
            return
        spend_points(uid, price)
    
    # Mark as purchased
    if is_vip_cat and not user_vip:
        purchase_method(uid, name, 0)
    
    # Send content
    text_content = folder.get("text_content")
    files = folder.get("files", [])
    
    if text_content:
        bot.edit_message_text(f"📄 <b>{add_emoji(name, cat)}</b>\n\n{text_content}", uid, call.message.message_id)
    elif files:
        bot.answer_callback_query(call.id, "📤 Sending...")
        for f in files[:5]:
            try:
                bot.copy_message(uid, f["chat"], f["msg"])
                time.sleep(0.1)
            except:
                pass
        bot.send_message(uid, f"✅ <b>{name}</b> sent!")
    else:
        bot.edit_message_text(f"📁 <b>{add_emoji(name, cat)}</b>\n\nNo content.", uid, call.message.message_id)
    
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("buy|"))
def buy_callback(call):
    uid = call.from_user.id
    _, cat, name, price = call.data.split("|")
    price = int(price)
    
    if is_vip(uid):
        bot.answer_callback_query(call.id, "✅ You're VIP!", True)
        open_callback(call)
        return
    
    if name in get_user(uid).get("purchased_methods", []):
        bot.answer_callback_query(call.id, "✅ You own this!", True)
        open_callback(call)
        return
    
    if get_points(uid) < price:
        bot.answer_callback_query(call.id, f"❌ Need {price}💎!", True)
        return
    
    if purchase_method(uid, name, price):
        bot.answer_callback_query(call.id, f"✅ Purchased! -{price}💎", True)
        bot.edit_message_text(f"✅ <b>Purchased!</b>\n\nYou now own: {add_emoji(name, cat)}\nRemaining: {get_points(uid)} 💎", uid, call.message.message_id)
        time.sleep(0.5)
        open_callback(call)

@bot.callback_query_handler(func=lambda c: c.data == "buy_vip")
def buy_vip_callback(call):
    uid = call.from_user.id
    cfg = get_config()
    price = cfg.get("vip_points_price", 5000)
    
    if is_vip(uid):
        bot.answer_callback_query(call.id, "✅ Already VIP!", True)
        return
    
    if get_points(uid) >= price:
        spend_points(uid, price)
        make_vip(uid, cfg.get("vip_duration_days", 30))
        bot.answer_callback_query(call.id, "✅ VIP Activated!", True)
        bot.edit_message_text(f"🎉 <b>CONGRATULATIONS!</b> 🎉\n\nYou are now VIP!\n💰 Balance: {get_points(uid)} 💎", uid, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, f"❌ Need {price}💎!", True)

@bot.callback_query_handler(func=lambda c: c.data == "get_referral")
def referral_callback(call):
    uid = call.from_user.id
    link = f"https://t.me/{bot.get_me().username}?start={uid}"
    bot.edit_message_text(f"🎁 <b>Your Referral Link</b>\n\n<code>{link}</code>\n\nShare to earn points!", uid, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "get_vip")
def vip_info_callback(call):
    cfg = get_config()
    text = f"👑 <b>VIP INFO</b>\n\n"
    text += f"💰 Price: {cfg.get('vip_points_price', 5000):,}💎 or ${cfg.get('vip_price', 50)}\n"
    text += f"✨ Benefits: All VIP methods, No points needed\n"
    text += f"🎁 Free: {cfg.get('referral_vip_count', 50)} referrals = FREE VIP"
    bot.edit_message_text(text, call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "cancel")
def cancel_callback(call):
    bot.edit_message_text("❌ Cancelled", call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("back|"))
def back_callback(call):
    _, cat, parent = call.data.split("|")
    bot.edit_message_reply_markup(call.from_user.id, call.message.message_id, reply_markup=get_folders_kb(cat, parent if parent else None))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("page|"))
def page_callback(call):
    _, cat, page, parent = call.data.split("|")
    parent = parent if parent != "None" else None
    bot.edit_message_reply_markup(call.from_user.id, call.message.message_id, reply_markup=get_folders_kb(cat, parent, int(page)))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "main_menu")
def main_menu_callback(call):
    uid = call.from_user.id
    points = get_points(uid)
    bot.edit_message_text(f"🏠 <b>MAIN MENU</b>\n\n💰 Balance: {points} 💎", uid, call.message.message_id, reply_markup=get_main_menu(uid))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "noop")
def noop_callback(call):
    bot.answer_callback_query(call.id)

# =========================
# ADMIN PANEL
# =========================

@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def admin_panel(message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Add FREE", "💎 Add VIP")
    kb.add("📱 Add APP", "⚡ Add SERVICE")
    kb.add("📁 Add Subfolder", "🗑 Delete Folder")
    kb.add("💰 Give Points", "👑 Give VIP")
    kb.add("🗑 Remove VIP", "🎫 Generate Code")
    kb.add("📊 View Codes", "📢 Broadcast")
    kb.add("⚙️ Settings", "📊 Stats")
    kb.add("❌ Exit Admin")
    bot.send_message(message.from_user.id, "⚙️ <b>ADMIN PANEL</b>", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "❌ Exit Admin" and is_admin(m.from_user.id))
def exit_admin(message):
    bot.send_message(message.from_user.id, "👋 Exited", reply_markup=get_main_menu(message.from_user.id))

# Add content
upload_session = {}

@bot.message_handler(func=lambda m: m.text in ["📦 Add FREE", "💎 Add VIP", "📱 Add APP", "⚡ Add SERVICE"] and is_admin(m.from_user.id))
def add_content_start(message):
    cat_map = {"📦 Add FREE": "free", "💎 Add VIP": "vip", "📱 Add APP": "apps", "⚡ Add SERVICE": "services"}
    uid = message.from_user.id
    upload_session[uid] = {"cat": cat_map[message.text], "files": [], "step": "name"}
    bot.send_message(uid, "📝 <b>Enter folder name:</b>")

@bot.message_handler(func=lambda m: m.from_user.id in upload_session and upload_session[m.from_user.id].get("step") == "name")
def add_name(message):
    uid = message.from_user.id
    upload_session[uid]["name"] = message.text
    upload_session[uid]["step"] = "price"
    bot.send_message(uid, "💰 <b>Price (points, 0 = free):</b>")

@bot.message_handler(func=lambda m: m.from_user.id in upload_session and upload_session[m.from_user.id].get("step") == "price")
def add_price(message):
    uid = message.from_user.id
    try:
        price = int(message.text)
        upload_session[uid]["price"] = price
        upload_session[uid]["step"] = "type"
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("📄 Text", "📁 Files")
        kb.add("❌ Cancel")
        bot.send_message(uid, "📝 <b>Content type:</b>", reply_markup=kb)
    except:
        bot.send_message(uid, "❌ Invalid price!")

@bot.message_handler(func=lambda m: m.from_user.id in upload_session and upload_session[m.from_user.id].get("step") == "type" and m.text == "📄 Text")
def add_text(message):
    uid = message.from_user.id
    upload_session[uid]["step"] = "text"
    bot.send_message(uid, "📝 <b>Enter text content:</b>", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("❌ Cancel"))

@bot.message_handler(func=lambda m: m.from_user.id in upload_session and upload_session[m.from_user.id].get("step") == "type" and m.text == "📁 Files")
def add_files_start(message):
    uid = message.from_user.id
    upload_session[uid]["step"] = "files"
    upload_session[uid]["files"] = []
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✅ Done", "❌ Cancel")
    bot.send_message(uid, "📁 <b>Send files:</b>\nPress ✅ Done when finished", reply_markup=kb)

@bot.message_handler(func=lambda m: m.from_user.id in upload_session and upload_session[m.from_user.id].get("step") == "text")
def save_text(message):
    uid = message.from_user.id
    if message.text == "❌ Cancel":
        upload_session.pop(uid, None)
        bot.send_message(uid, "❌ Cancelled", reply_markup=get_main_menu(uid))
        return
    
    data = upload_session[uid]
    number = add_folder(data["cat"], data["name"], [], data["price"], text_content=message.text)
    bot.send_message(uid, f"✅ <b>Added!</b>\n\n📌 #{number}\n📂 {data['name']}\n💰 {data['price']}💎", reply_markup=admin_panel_menu())
    upload_session.pop(uid, None)

@bot.message_handler(func=lambda m: m.from_user.id in upload_session and upload_session[m.from_user.id].get("step") == "files")
def save_files(message):
    uid = message.from_user.id
    
    if message.text == "✅ Done":
        data = upload_session[uid]
        if not data.get("files"):
            bot.send_message(uid, "❌ No files!")
            return
        number = add_folder(data["cat"], data["name"], data["files"], data["price"])
        bot.send_message(uid, f"✅ <b>Added!</b>\n\n📌 #{number}\n📂 {data['name']}\n💰 {data['price']}💎\n📁 {len(data['files'])} files", reply_markup=admin_panel_menu())
        upload_session.pop(uid, None)
        return
    
    if message.text == "❌ Cancel":
        upload_session.pop(uid, None)
        bot.send_message(uid, "❌ Cancelled", reply_markup=get_main_menu(uid))
        return
    
    if message.content_type in ["photo", "document", "video"]:
        upload_session[uid]["files"].append({"chat": message.chat.id, "msg": message.message_id, "type": message.content_type})
        bot.send_message(uid, f"✅ File {len(upload_session[uid]['files'])} added")

def admin_panel_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Add FREE", "💎 Add VIP", "📱 Add APP", "⚡ Add SERVICE", "❌ Exit Admin")
    return kb

@bot.message_handler(func=lambda m: m.text == "📁 Add Subfolder" and is_admin(m.from_user.id))
def add_subfolder(message):
    msg = bot.send_message(message.from_user.id, "📁 <b>Add Subfolder</b>\n\nFormat: <code>category parent name price</code>\nExample: <code>free Tutorials Advanced 10</code>")
    bot.register_next_step_handler(msg, process_subfolder)

def process_subfolder(message):
    try:
        parts = message.text.split(maxsplit=3)
        cat, parent, name, price = parts[0].lower(), parts[1], parts[2], int(parts[3])
        number = add_folder(cat, name, [], price, parent)
        bot.send_message(message.from_user.id, f"✅ <b>Subfolder added!</b>\n📌 #{number}\n📂 {parent} → {name}", reply_markup=admin_panel_menu())
    except:
        bot.send_message(message.from_user.id, "❌ Use: category parent name price")

@bot.message_handler(func=lambda m: m.text == "🗑 Delete Folder" and is_admin(m.from_user.id))
def delete_start(message):
    msg = bot.send_message(message.from_user.id, "🗑 <b>Delete Folder</b>\n\nFormat: <code>category name</code>\nExample: <code>free Test</code>")
    bot.register_next_step_handler(msg, process_delete)

def process_delete(message):
    try:
        parts = message.text.split(maxsplit=1)
        cat, name = parts[0].lower(), parts[1]
        if delete_folder(cat, name):
            bot.send_message(message.from_user.id, f"✅ Deleted: {cat} → {name}", reply_markup=admin_panel_menu())
        else:
            bot.send_message(message.from_user.id, "❌ Not found!")
    except:
        bot.send_message(message.from_user.id, "❌ Use: category name")

@bot.message_handler(func=lambda m: m.text == "💰 Give Points" and is_admin(m.from_user.id))
def give_points_start(message):
    msg = bot.send_message(message.from_user.id, "💰 <b>Give Points</b>\n\nFormat: <code>user_id points</code>\nExample: <code>123456789 100</code>")
    bot.register_next_step_handler(msg, process_give_points)

def process_give_points(message):
    try:
        parts = message.text.split()
        uid, points = int(parts[0]), int(parts[1])
        old = get_points(uid)
        new = add_points(uid, points)
        bot.send_message(message.from_user.id, f"✅ Added {points}💎 to {uid}\nOld: {old} → New: {new}", reply_markup=admin_panel_menu())
        try:
            bot.send_message(uid, f"🎉 You received {points} points! New balance: {new}💎")
        except:
            pass
    except:
        bot.send_message(message.from_user.id, "❌ Use: user_id points")

@bot.message_handler(func=lambda m: m.text == "👑 Give VIP" and is_admin(m.from_user.id))
def give_vip_start(message):
    msg = bot.send_message(message.from_user.id, "👑 <b>Give VIP</b>\n\nSend user ID or @username:")
    bot.register_next_step_handler(msg, process_give_vip)

def process_give_vip(message):
    inp = message.text.strip()
    if inp.startswith("@"):
        try:
            uid = bot.get_chat(inp).id
        except:
            bot.send_message(message.from_user.id, "❌ User not found!")
            return
    else:
        try:
            uid = int(inp)
        except:
            bot.send_message(message.from_user.id, "❌ Invalid ID!")
            return
    
    cfg = get_config()
    make_vip(uid, cfg.get("vip_duration_days", 30))
    bot.send_message(message.from_user.id, f"✅ {uid} is now VIP!", reply_markup=admin_panel_menu())
    try:
        bot.send_message(uid, "👑 You have been granted VIP status!")
    except:
        pass

@bot.message_handler(func=lambda m: m.text == "🗑 Remove VIP" and is_admin(m.from_user.id))
def remove_vip_start(message):
    msg = bot.send_message(message.from_user.id, "🗑 <b>Remove VIP</b>\n\nSend user ID or @username:")
    bot.register_next_step_handler(msg, process_remove_vip)

def process_remove_vip(message):
    inp = message.text.strip()
    if inp.startswith("@"):
        try:
            uid = bot.get_chat(inp).id
        except:
            bot.send_message(message.from_user.id, "❌ User not found!")
            return
    else:
        try:
            uid = int(inp)
        except:
            bot.send_message(message.from_user.id, "❌ Invalid ID!")
            return
    
    remove_vip(uid)
    bot.send_message(message.from_user.id, f"✅ VIP removed from {uid}", reply_markup=admin_panel_menu())
    try:
        bot.send_message(uid, "⚠️ Your VIP status has been removed.")
    except:
        pass

@bot.message_handler(func=lambda m: m.text == "🎫 Generate Code" and is_admin(m.from_user.id))
def gen_code_start(message):
    msg = bot.send_message(message.from_user.id, "🎫 <b>Generate Code</b>\n\nSend points amount:")
    bot.register_next_step_handler(msg, process_gen_code)

def process_gen_code(message):
    try:
        points = int(message.text)
        code = generate_code(points)
        bot.send_message(message.from_user.id, f"✅ <b>Code generated!</b>\n\n<code>{code}</code>\n💰 +{points} points", reply_markup=admin_panel_menu())
    except:
        bot.send_message(message.from_user.id, "❌ Invalid points!")

@bot.message_handler(func=lambda m: m.text == "📊 View Codes" and is_admin(m.from_user.id))
def view_codes_admin(message):
    codes = list(codes_col.find({}).sort("created_at", -1).limit(20))
    if not codes:
        bot.send_message(message.from_user.id, "📊 No codes!")
        return
    
    text = "📊 <b>Recent Codes</b>\n\n"
    for c in codes:
        used = "✅" if c.get("used", False) else "⏳"
        text += f"{used} <code>{c['_id']}</code> → {c['points']}💎\n"
    bot.send_message(message.from_user.id, text)

@bot.message_handler(func=lambda m: m.text == "📢 Broadcast" and is_admin(m.from_user.id))
def broadcast_start(message):
    msg = bot.send_message(message.from_user.id, "📢 <b>Broadcast</b>\n\nSend message to broadcast to all users:")
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    total = users_col.count_documents({})
    status = bot.send_message(message.from_user.id, f"📤 Broadcasting to {total} users...")
    sent = 0
    failed = 0
    
    for user in users_col.find({}, {"_id": 1}):
        try:
            bot.send_message(int(user["_id"]), message.text, parse_mode="HTML")
            sent += 1
            if sent % 10 == 0:
                time.sleep(0.1)
        except:
            failed += 1
    
    bot.edit_message_text(f"✅ Broadcast done!\n📤 Sent: {sent}\n❌ Failed: {failed}", message.from_user.id, status.message_id)

@bot.message_handler(func=lambda m: m.text == "⚙️ Settings" and is_admin(m.from_user.id))
def settings_menu(message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📝 Welcome", callback_data="set_welcome"),
        InlineKeyboardButton("💎 VIP Msg", callback_data="set_vip_msg"),
        InlineKeyboardButton("💰 Ref Reward", callback_data="set_ref_reward"),
        InlineKeyboardButton("👑 VIP Price", callback_data="set_vip_price"),
        InlineKeyboardButton("📞 Contact", callback_data="set_contact")
    )
    bot.send_message(message.from_user.id, "⚙️ <b>Settings</b>", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "set_welcome")
def set_welcome_cb(call):
    msg = bot.send_message(call.from_user.id, "📝 Send new welcome message:")
    bot.register_next_step_handler(msg, lambda x: set_config("welcome", x.text) or bot.send_message(x.from_user.id, "✅ Updated!", reply_markup=admin_panel_menu()))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "set_vip_msg")
def set_vip_msg_cb(call):
    msg = bot.send_message(call.from_user.id, "💎 Send new VIP message:")
    bot.register_next_step_handler(msg, lambda x: set_config("vip_msg", x.text) or bot.send_message(x.from_user.id, "✅ Updated!", reply_markup=admin_panel_menu()))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "set_ref_reward")
def set_ref_reward_cb(call):
    msg = bot.send_message(call.from_user.id, f"💰 Current: {get_config().get('ref_reward', 5)}\nSend new amount:")
    bot.register_next_step_handler(msg, lambda x: set_config("ref_reward", int(x.text)) if x.text.isdigit() else bot.send_message(x.from_user.id, "❌ Invalid!"))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "set_vip_price")
def set_vip_price_cb(call):
    msg = bot.send_message(call.from_user.id, f"👑 Current VIP points price: {get_config().get('vip_points_price', 5000)}\nSend new amount:")
    bot.register_next_step_handler(msg, lambda x: set_config("vip_points_price", int(x.text)) if x.text.isdigit() else bot.send_message(x.from_user.id, "❌ Invalid!"))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "set_contact")
def set_contact_cb(call):
    msg = bot.send_message(call.from_user.id, "📞 Send @username or link:\nSend 'none' to clear")
    bot.register_next_step_handler(msg, lambda x: set_config("vip_contact", None if x.text.lower() == "none" else x.text) or bot.send_message(x.from_user.id, "✅ Updated!", reply_markup=admin_panel_menu()))
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.text == "📊 Stats" and is_admin(m.from_user.id))
def stats_command(message):
    total_users = users_col.count_documents({})
    vip_users = users_col.count_documents({"vip": True})
    total_points = sum(u.get("points", 0) for u in users_col.find({}))
    free_folders = folders_col.count_documents({"cat": "free"})
    vip_folders = folders_col.count_documents({"cat": "vip"})
    apps_folders = folders_col.count_documents({"cat": "apps"})
    services_folders = folders_col.count_documents({"cat": "services"})
    total_codes = codes_col.count_documents({})
    used_codes = codes_col.count_documents({"used": True})
    
    text = f"📊 <b>STATISTICS</b>\n\n"
    text += f"👥 <b>Users:</b> {total_users}\n"
    text += f"├ VIP: {vip_users}\n"
    text += f"└ Free: {total_users - vip_users}\n\n"
    text += f"💰 <b>Points:</b> {total_points:,}\n\n"
    text += f"📁 <b>Content:</b>\n"
    text += f"├ FREE: {free_folders}\n"
    text += f"├ VIP: {vip_folders}\n"
    text += f"├ APPS: {apps_folders}\n"
    text += f"└ SERVICES: {services_folders}\n\n"
    text += f"🎫 <b>Codes:</b>\n"
    text += f"├ Total: {total_codes}\n"
    text += f"└ Used: {used_codes}"
    
    bot.send_message(message.from_user.id, text)

# Fallback
@bot.message_handler(func=lambda m: True)
def fallback(message):
    uid = message.from_user.id
    points = get_points(uid)
    bot.send_message(uid, f"❌ Unknown\n💰 Balance: {points}💎", reply_markup=get_main_menu(uid))

# =========================
# MAIN
# =========================
def main():
    print("=" * 60)
    print("🚀 ZEDOX BOT IS RUNNING!")
    print(f"✅ Bot: @{bot.get_me().username}")
    print(f"👑 Admin: {ADMIN_ID}")
    print("=" * 60)
    
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=60)
        except Exception as e:
            print(f"⚠️ Polling error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
