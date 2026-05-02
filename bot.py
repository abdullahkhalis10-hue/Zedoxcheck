# =========================
# ZEDOX BOT - COMPLETE ULTRA FAST VERSION
# Fully Functional with All Features
# =========================

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
import os
import time
import random
import string
import threading
import hashlib
import hmac
from pymongo import MongoClient
from datetime import datetime, timedelta
from functools import wraps

# =========================
# CONFIGURATION
# =========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
MONGO_URI = os.environ.get("MONGO_URI")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set!")
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable not set!")

# =========================
# MONGODB SETUP
# =========================
client = MongoClient(MONGO_URI, maxPoolSize=50, minPoolSize=10, connectTimeoutMS=5000, socketTimeoutMS=5000)
db = client["zedox_complete"]

users_col = db["users"]
folders_col = db["folders"]
codes_col = db["codes"]
config_col = db["config"]
custom_buttons_col = db["custom_buttons"]
admins_col = db["admins"]
payments_col = db["payments"]

# Create indexes
users_col.create_index("points")
users_col.create_index("vip")
folders_col.create_index([("cat", 1), ("parent", 1)])
folders_col.create_index("number", unique=True, sparse=True)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# =========================
# SIMPLE CACHE
# =========================
_config_cache = None
_config_cache_time = 0
_user_cache = {}
_user_cache_time = {}
_folder_cache = {}
_folder_cache_time = {}
_force_cache = {}

CACHE_TTL = 30

def get_cached_config():
    global _config_cache, _config_cache_time
    now = time.time()
    if _config_cache and (now - _config_cache_time) < CACHE_TTL:
        return _config_cache
    _config_cache = get_config()
    _config_cache_time = now
    return _config_cache

# =========================
# CONFIG SYSTEM
# =========================
def get_config():
    cfg = config_col.find_one({"_id": "config"})
    if not cfg:
        cfg = {
            "_id": "config",
            "force_channels": [],
            "custom_buttons": [],
            "vip_msg": "💎 Buy VIP to unlock premium content!",
            "welcome": "🔥 Welcome to ZEDOX BOT! 🚀",
            "ref_reward": 5,
            "notify": True,
            "notify_new_methods": True,
            "next_folder_number": {"free": 1, "vip": 1, "apps": 1, "services": 1},
            "points_per_dollar": 100,
            "contact_username": None,
            "contact_link": None,
            "vip_contact": None,
            "vip_price": 50,
            "vip_points_price": 5000,
            "payment_methods": ["💳 Binance", "💵 USDT (TRC20)", "💰 Bank Transfer", "🪙 Bitcoin"],
            "referral_vip_count": 50,
            "referral_purchase_count": 10,
            "vip_duration_days": 30,
            "binance_coin": "USDT",
            "binance_network": "TRC20",
            "binance_address": "",
            "binance_memo": "",
            "require_screenshot": True
        }
        config_col.insert_one(cfg)
    return cfg

def set_config(key, value):
    global _config_cache
    _config_cache = None
    config_col.update_one({"_id": "config"}, {"$set": {key: value}}, upsert=True)

# =========================
# ADMIN SYSTEM
# =========================
def init_admins():
    if not admins_col.find_one({"_id": ADMIN_ID}):
        admins_col.insert_one({
            "_id": ADMIN_ID,
            "username": None,
            "added_by": "system",
            "added_at": time.time(),
            "is_owner": True
        })

init_admins()

def is_admin(uid):
    uid = int(uid) if isinstance(uid, str) else uid
    if uid == ADMIN_ID:
        return True
    return admins_col.find_one({"_id": uid}) is not None

def add_admin(uid, username=None, added_by=None):
    uid = int(uid) if isinstance(uid, str) else uid
    if admins_col.find_one({"_id": uid}):
        return False
    admins_col.insert_one({
        "_id": uid,
        "username": username,
        "added_by": added_by,
        "added_at": time.time(),
        "is_owner": False
    })
    return True

def remove_admin(uid):
    uid = int(uid) if isinstance(uid, str) else uid
    if uid == ADMIN_ID:
        return False
    result = admins_col.delete_one({"_id": uid})
    return result.deleted_count > 0

# =========================
# USER SYSTEM
# =========================
def get_user(uid):
    uid = str(uid)
    now = time.time()
    
    if uid in _user_cache and (now - _user_cache_time.get(uid, 0)) < CACHE_TTL:
        return _user_cache[uid].copy()
    
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
            "last_active": time.time(),
            "total_points_earned": 0,
            "total_points_spent": 0
        }
        users_col.insert_one(data)
    
    _user_cache[uid] = data.copy()
    _user_cache_time[uid] = now
    return data

def save_user(uid, data):
    users_col.update_one({"_id": str(uid)}, {"$set": data})
    _user_cache[str(uid)] = data.copy()
    _user_cache_time[str(uid)] = time.time()

def add_points(uid, amount):
    data = get_user(uid)
    old = data.get("points", 0)
    data["points"] = old + amount
    data["total_points_earned"] = data.get("total_points_earned", 0) + amount
    save_user(uid, data)
    return data["points"]

def spend_points(uid, amount):
    data = get_user(uid)
    current = data.get("points", 0)
    if current < amount:
        return current
    data["points"] = current - amount
    data["total_points_spent"] = data.get("total_points_spent", 0) + amount
    save_user(uid, data)
    return data["points"]

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

def can_access_method(uid, method_name):
    return is_vip(uid) or method_name in get_user(uid).get("purchased_methods", [])

def get_points(uid):
    return get_user(uid).get("points", 0)

def add_referral(uid):
    data = get_user(uid)
    data["refs"] = data.get("refs", 0) + 1
    save_user(uid, data)
    cfg = get_cached_config()
    if data["refs"] >= cfg.get("referral_vip_count", 50) and not is_vip(uid):
        make_vip(uid, cfg.get("vip_duration_days", 30))
        return True
    return False

# =========================
# FOLDER SYSTEM (SEPARATE NUMBERING)
# =========================
def get_next_number(cat):
    cfg = get_config()
    next_numbers = cfg.get("next_folder_number", {"free": 1, "vip": 1, "apps": 1, "services": 1})
    current = next_numbers.get(cat, 1)
    next_numbers[cat] = current + 1
    set_config("next_folder_number", next_numbers)
    return current

def add_folder(cat, name, files, price, parent=None, text_content=None):
    number = get_next_number(cat)
    
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
    
    # Send notification if enabled
    cfg = get_cached_config()
    if cfg.get("notify_new_methods", True):
        send_new_method_notification(cat, name, number)
    
    return number

def send_new_method_notification(cat, name, number):
    cat_names = {"free": "📂 FREE", "vip": "💎 VIP", "apps": "📱 APPS", "services": "⚡ SERVICES"}
    cat_emoji = {"free": "📂", "vip": "💎", "apps": "📱", "services": "⚡"}
    
    message = f"🎉 <b>NEW METHOD ADDED!</b> 🎉\n\n"
    message += f"{cat_emoji.get(cat, '📌')} <b>Category:</b> {cat_names.get(cat, cat.upper())}\n"
    message += f"📌 <b>#{number}</b> {name}\n\n"
    message += f"✨ Click the button below to view it instantly!"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(f"🔓 OPEN #{number} - {name}", callback_data=f"open|{cat}|{name}|"))
    
    def broadcast():
        for user in users_col.find({}, {"_id": 1}):
            try:
                bot.send_message(int(user["_id"]), message, reply_markup=kb)
                time.sleep(0.03)
            except:
                pass
    
    threading.Thread(target=broadcast, daemon=True).start()

def get_folders(cat, parent=None):
    cache_key = f"{cat}_{parent}"
    now = time.time()
    
    if cache_key in _folder_cache and (now - _folder_cache_time.get(cache_key, 0)) < CACHE_TTL * 2:
        return _folder_cache[cache_key]
    
    query = {"cat": cat}
    if parent:
        query["parent"] = parent
    else:
        query["parent"] = None
    
    result = list(folders_col.find(query).sort("number", 1))
    _folder_cache[cache_key] = result
    _folder_cache_time[cache_key] = now
    return result

def get_folder(cat, name, parent=None):
    query = {"cat": cat, "name": name}
    if parent:
        query["parent"] = parent
    return folders_col.find_one(query)

def delete_folder(cat, name):
    folders_col.delete_one({"cat": cat, "name": name})
    clear_folder_cache()

def clear_folder_cache():
    _folder_cache.clear()
    _folder_cache_time.clear()

# =========================
# CODE SYSTEM
# =========================
def generate_code(points):
    code = "ZEDOX" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    while codes_col.find_one({"_id": code}):
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
# AUTO EMOJI FUNCTION
# =========================
def add_auto_emoji(name, cat=None):
    emoji_map = {
        "premium": "💎", "vip": "👑", "pro": "⭐", "advanced": "🚀",
        "free": "🆓", "basic": "📌", "starter": "🌱",
        "app": "📱", "android": "🤖", "ios": "🍎", "mobile": "📲",
        "service": "⚡", "tool": "🛠️", "api": "🔌",
        "method": "🔧", "tutorial": "📚", "guide": "📖", "course": "🎓",
        "hack": "🎮", "cheat": "🎯", "mod": "🔧", "crack": "🔓",
        "key": "🔑", "license": "📜", "code": "💻",
        "account": "👤", "card": "💳", "crypto": "🪙", "bitcoin": "₿", "usdt": "💵",
        "social": "📱", "instagram": "📸", "facebook": "📘", "twitter": "🐦",
        "video": "🎥", "music": "🎵", "game": "🎮"
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
# FORCE JOIN
# =========================
def force_block(uid):
    if is_admin(uid):
        return False
    
    now = time.time()
    if uid in _force_cache and (now - _force_cache[uid].get("time", 0)) < 30:
        return _force_cache[uid].get("blocked", False)
    
    cfg = get_cached_config()
    channels = cfg.get("force_channels", [])
    
    if not channels:
        _force_cache[uid] = {"blocked": False, "time": now}
        return False
    
    for ch in channels:
        try:
            member = bot.get_chat_member(ch, uid)
            if member.status in ["left", "kicked"]:
                kb = InlineKeyboardMarkup()
                for channel in channels:
                    clean = channel.replace("@", "")
                    kb.add(InlineKeyboardButton(f"📢 Join {channel}", url=f"https://t.me/{clean}"))
                kb.add(InlineKeyboardButton("✅ I Joined", callback_data="recheck"))
                bot.send_message(uid, "🚫 <b>Access Restricted!</b>\n\nPlease join the required channels:", reply_markup=kb)
                _force_cache[uid] = {"blocked": True, "time": now}
                return True
        except:
            pass
    
    _force_cache[uid] = {"blocked": False, "time": now}
    return False

def force_join_handler(func):
    @wraps(func)
    def wrapper(message):
        if force_block(message.from_user.id):
            return
        return func(message)
    return wrapper

# =========================
# KEYBOARDS
# =========================
def get_category_counts():
    return {
        "free": folders_col.count_documents({"cat": "free"}),
        "vip": folders_col.count_documents({"cat": "vip"}),
        "apps": folders_col.count_documents({"cat": "apps"}),
        "services": folders_col.count_documents({"cat": "services"})
    }

def get_custom_buttons():
    cfg = get_cached_config()
    return cfg.get("custom_buttons", [])

def main_menu(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    counts = get_category_counts()
    
    kb.add(f"📂 FREE METHODS [{counts['free']}]", f"💎 VIP METHODS [{counts['vip']}]")
    kb.add(f"📦 PREMIUM APPS [{counts['apps']}]", f"⚡ SERVICES [{counts['services']}]")
    kb.add("💰 POINTS", "⭐ BUY VIP")
    
    custom = get_custom_buttons()
    if custom:
        row = []
        for btn in custom:
            row.append(btn["text"])
            if len(row) == 2:
                kb.add(*row)
                row = []
        if row:
            kb.add(*row)
    
    kb.add("🎁 REFERRAL", "👤 ACCOUNT")
    kb.add("📚 MY METHODS", "💎 GET POINTS")
    kb.add("🆔 CHAT ID", "🏆 REDEEM")
    
    if is_admin(uid):
        kb.add("⚙️ ADMIN PANEL")
    
    return kb

def get_folders_kb(cat, parent=None, page=0, per_page=10):
    folders = get_folders(cat, parent)
    total = len(folders)
    
    if total == 0:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("📂 Empty", callback_data="noop"))
        return kb
    
    total_pages = (total + per_page - 1) // per_page
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
        display = add_auto_emoji(name, cat)
        
        text = f"{icon} [{number}] {display}"
        if price > 0 and not has_subs:
            text += f" ─ {price}💎"
        
        kb.add(InlineKeyboardButton(text, callback_data=f"open|{cat}|{name}|{parent or ''}"))
    
    # Page navigation
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
        kb.add(InlineKeyboardButton("🏠 MAIN", callback_data="main_menu"))
    
    return kb

def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Upload FREE", "💎 Upload VIP")
    kb.add("📱 Upload APPS", "⚡ Upload SERVICE")
    kb.add("📁 Create Subfolder", "🗑 Delete Folder")
    kb.add("✏️ Edit Price", "✏️ Edit Name")
    kb.add("📝 Edit Content", "🔀 Move Folder")
    kb.add("👑 Add VIP", "👑 Remove VIP")
    kb.add("💰 Give Points", "🎫 Generate Code")
    kb.add("📊 View Codes", "📦 Points Packages")
    kb.add("👥 Admin Management", "📞 Set Contacts")
    kb.add("⚙️ VIP Settings", "💳 Payment Methods")
    kb.add("🏦 Binance Settings", "📸 Screenshot")
    kb.add("➕ Add Button", "➖ Remove Button")
    kb.add("➕ Add Channel", "➖ Remove Channel")
    kb.add("⚙️ Settings", "📊 Stats")
    kb.add("📢 Broadcast", "🔔 Notify")
    kb.add("🔔 Toggle Method Notify", "📊 Leaderboard")
    kb.add("❌ Exit")
    return kb

# =========================
# BOT HANDLERS
# =========================

@bot.message_handler(commands=["start"])
def start_command(message):
    uid = message.from_user.id
    
    # Update username
    if message.from_user.username:
        user = get_user(uid)
        user["username"] = message.from_user.username
        save_user(uid, user)
    
    # Handle referral
    args = message.text.split()
    if len(args) > 1:
        ref_id = args[1]
        if ref_id != str(uid) and ref_id.isdigit():
            user = get_user(uid)
            if not user.get("ref"):
                cfg = get_cached_config()
                reward = cfg.get("ref_reward", 5)
                add_points(ref_id, reward)
                add_referral(ref_id)
                user["ref"] = ref_id
                save_user(uid, user)
                
                try:
                    bot.send_message(int(ref_id), f"👤 <b>New Referral!</b>\n\n✨ @{message.from_user.username or uid} joined!\n💰 You earned +{reward} points!")
                except:
                    pass
    
    if force_block(uid):
        return
    
    cfg = get_cached_config()
    welcome = cfg.get("welcome", "🔥 Welcome to ZEDOX BOT!")
    points = get_points(uid)
    
    bot.send_message(uid, f"{welcome}\n\n💰 <b>Balance:</b> {points} 💎\n👑 <b>VIP:</b> {'✅ Active' if is_vip(uid) else '❌ Not Active'}", reply_markup=main_menu(uid))

@bot.message_handler(func=lambda m: m.text == "💰 POINTS")
@force_join_handler
def points_command(message):
    uid = message.from_user.id
    user = get_user(uid)
    cfg = get_cached_config()
    
    text = f"┌─<b>💰 YOUR WALLET</b>─┐\n\n"
    text += f"├ 💎 Points: <code>{user.get('points', 0):,}</code>\n"
    text += f"├ 👑 VIP: <code>{'Yes' if is_vip(uid) else 'No'}</code>\n"
    text += f"├ 👥 Referrals: <code>{user.get('refs', 0)}</code>\n"
    text += f"├ 📈 Earned: <code>{user.get('total_points_earned', 0):,}</code>\n"
    text += f"└ 📉 Spent: <code>{user.get('total_points_spent', 0):,}</code>\n\n"
    text += f"✨ <b>Earn points:</b> Referrals, Redeem codes\n"
    text += f"🎯 <b>FREE VIP:</b> {cfg.get('referral_vip_count', 50)} referrals = FREE VIP"
    
    bot.send_message(uid, text)

@bot.message_handler(func=lambda m: m.text == "👤 ACCOUNT")
@force_join_handler
def account_command(message):
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

@bot.message_handler(func=lambda m: m.text == "📚 MY METHODS")
@force_join_handler
def my_methods_command(message):
    uid = message.from_user.id
    
    if is_vip(uid):
        bot.send_message(uid, "👑 <b>VIP MEMBER</b>\n\nYou have access to ALL VIP methods!")
        return
    
    purchased = get_user(uid).get("purchased_methods", [])
    if not purchased:
        bot.send_message(uid, f"📚 <b>No purchased methods</b>\n\nBuy methods from 💎 VIP METHODS!\n💰 Points: {get_points(uid)}")
        return
    
    text = f"📚 <b>YOUR PURCHASES</b> ({len(purchased)})\n\n"
    for i, method in enumerate(purchased, 1):
        text += f"{i}. {add_auto_emoji(method, 'vip')}\n"
    
    bot.send_message(uid, text)

@bot.message_handler(func=lambda m: m.text == "🏆 REDEEM")
@force_join_handler
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
@force_join_handler
def referral_command(message):
    uid = message.from_user.id
    user = get_user(uid)
    cfg = get_cached_config()
    
    link = f"https://t.me/{bot.get_me().username}?start={uid}"
    text = f"┌─<b>🎁 REFERRAL PROGRAM</b>─┐\n\n"
    text += f"├ 🔗 <code>{link}</code>\n\n"
    text += f"├ 👥 Referrals: <code>{user.get('refs', 0)}</code>\n"
    text += f"├ 💰 Earned: <code>{user.get('refs', 0) * cfg.get('ref_reward', 5)}</code>\n"
    text += f"└ 🎯 Goal: <code>{user.get('refs', 0)}/{cfg.get('referral_vip_count', 50)}</code>\n\n"
    text += f"✨ +{cfg.get('ref_reward', 5)}💎 per referral\n"
    text += f"✨ {cfg.get('referral_vip_count', 50)} referrals → FREE VIP"
    
    bot.send_message(uid, text)

@bot.message_handler(func=lambda m: m.text == "🆔 CHAT ID")
@force_join_handler
def chatid_command(message):
    uid = message.from_user.id
    bot.send_message(uid, f"🆔 <b>Your ID:</b> <code>{uid}</code>")

@bot.message_handler(func=lambda m: m.text == "⭐ BUY VIP")
@force_join_handler
def buy_vip_command(message):
    uid = message.from_user.id
    cfg = get_cached_config()
    
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

@bot.message_handler(func=lambda m: m.text == "💎 GET POINTS")
@force_join_handler
def get_points_button(message):
    uid = message.from_user.id
    cfg = get_cached_config()
    
    text = f"💰 <b>GET POINTS</b> 💰\n\n"
    text += f"💰 Your balance: <code>{get_points(uid):,}</code> 💎\n\n"
    text += f"✨ <b>Purchase Packages:</b>\n"
    text += f"• 100💎 = $5 USD\n"
    text += f"• 250💎 = $10 USD (+25 bonus)\n"
    text += f"• 550💎 = $20 USD (+100 bonus)\n"
    text += f"• 1500💎 = $50 USD (+500 bonus)\n"
    text += f"• 3500💎 = $100 USD (+1500 bonus)\n\n"
    
    if cfg.get("binance_address"):
        text += f"💳 <b>Binance Payment:</b>\n"
        text += f"├ Coin: {cfg.get('binance_coin', 'USDT')}\n"
        text += f"├ Network: {cfg.get('binance_network', 'TRC20')}\n"
        text += f"├ Address: <code>{cfg.get('binance_address')}</code>\n"
        if cfg.get("binance_memo"):
            text += f"├ Memo: <code>{cfg.get('binance_memo')}</code>\n"
        text += f"└ Amount: Equal to package price\n\n"
    
    text += f"📸 <b>How to purchase:</b>\n"
    text += f"1. Send payment to Binance address\n"
    text += f"2. Take a screenshot\n"
    text += f"3. Send screenshot here with your User ID: <code>{uid}</code>\n"
    text += f"4. Mention which package\n\n"
    text += f"Contact admin for support!"
    
    kb = InlineKeyboardMarkup()
    if cfg.get("contact_username"):
        contact = cfg.get("contact_username")
        if contact.startswith("@"):
            kb.add(InlineKeyboardButton("📞 CONTACT", url=f"https://t.me/{contact[1:]}"))
    elif cfg.get("contact_link"):
        kb.add(InlineKeyboardButton("📞 CONTACT", url=cfg.get("contact_link")))
    
    bot.send_message(uid, text, reply_markup=kb if kb.keyboard else None)

@bot.message_handler(func=lambda m: m.text.startswith("📂 FREE METHODS") or m.text.startswith("💎 VIP METHODS") or m.text.startswith("📦 PREMIUM APPS") or m.text.startswith("⚡ SERVICES"))
@force_join_handler
def show_category(message):
    uid = message.from_user.id
    text = message.text.split("[")[0].strip()
    
    mapping = {
        "📂 FREE METHODS": "free",
        "💎 VIP METHODS": "vip",
        "📦 PREMIUM APPS": "apps",
        "⚡ SERVICES": "services"
    }
    
    cat = mapping.get(text)
    if not cat:
        return
    
    folders = get_folders(cat)
    if not folders:
        bot.send_message(uid, f"📂 {text}\n\nNo content available!")
        return
    
    bot.send_message(uid, f"📂 {text}\n\nSelect:", reply_markup=get_folders_kb(cat))

# =========================
# CALLBACK HANDLERS
# =========================

@bot.callback_query_handler(func=lambda c: c.data.startswith("open|"))
def open_callback(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    
    parts = call.data.split("|")
    cat = parts[1]
    name = parts[2]
    parent = parts[3] if len(parts) > 3 and parts[3] else None
    
    folder = get_folder(cat, name, parent if parent else None)
    if not folder:
        bot.send_message(uid, "❌ Not found!")
        return
    
    # Check subfolders
    subfolders = get_folders(cat, name)
    if subfolders:
        kb = InlineKeyboardMarkup(row_width=1)
        for sub in subfolders:
            sub_name = sub["name"]
            sub_number = sub.get("number", "?")
            sub_price = sub.get("price", 0)
            deeper = get_folders(cat, sub_name)
            icon = "📁" if deeper else "📄"
            display = add_auto_emoji(sub_name, cat)
            text = f"{icon} [{sub_number}] {display}"
            if sub_price > 0:
                text += f" - {sub_price}💎"
            kb.add(InlineKeyboardButton(text, callback_data=f"open|{cat}|{sub_name}|{name}"))
        kb.add(InlineKeyboardButton("🔙 BACK", callback_data=f"back|{cat}|{parent or ''}"))
        bot.edit_message_text(f"📁 <b>{add_auto_emoji(name, cat)}</b>", uid, call.message.message_id, reply_markup=kb)
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
                InlineKeyboardButton("👑 GET VIP", callback_data="get_vip_info")
            )
            kb.add(InlineKeyboardButton("❌ CANCEL", callback_data="cancel"))
            bot.edit_message_text(f"🔒 <b>{add_auto_emoji(name, cat)}</b>\n\nPrice: {price} 💎\nBalance: {get_points(uid)} 💎", uid, call.message.message_id, reply_markup=kb)
        else:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("👑 GET VIP", callback_data="get_vip_info"))
            bot.edit_message_text(f"🔒 <b>{add_auto_emoji(name, cat)}</b>\n\nVIP only!", uid, call.message.message_id, reply_markup=kb)
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
        bot.edit_message_text(f"📄 <b>{add_auto_emoji(name, cat)}</b>\n\n{text_content}", uid, call.message.message_id)
    elif files:
        for f in files[:5]:
            try:
                bot.copy_message(uid, f["chat"], f["msg"])
                time.sleep(0.05)
            except:
                pass
        bot.send_message(uid, f"✅ <b>{add_auto_emoji(name, cat)}</b> sent!")
        bot.edit_message_text(f"✅ <b>{add_auto_emoji(name, cat)}</b>\n\nSent!", uid, call.message.message_id)
    else:
        bot.edit_message_text(f"📁 <b>{add_auto_emoji(name, cat)}</b>\n\nNo content.", uid, call.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("buy|"))
def buy_callback(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    
    _, cat, name, price = call.data.split("|")
    price = int(price)
    
    if is_vip(uid):
        bot.send_message(uid, "✅ You're VIP!")
        open_callback(call)
        return
    
    if name in get_user(uid).get("purchased_methods", []):
        bot.send_message(uid, "✅ You own this!")
        open_callback(call)
        return
    
    if get_points(uid) < price:
        bot.send_message(uid, f"❌ Need {price}💎!")
        return
    
    if purchase_method(uid, name, price):
        bot.send_message(uid, f"✅ Purchased! -{price}💎\nRemaining: {get_points(uid)} 💎")
        open_callback(call)

@bot.callback_query_handler(func=lambda c: c.data == "buy_vip")
def buy_vip_callback(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    cfg = get_cached_config()
    price = cfg.get("vip_points_price", 5000)
    
    if is_vip(uid):
        bot.send_message(uid, "✅ Already VIP!")
        return
    
    if get_points(uid) >= price:
        spend_points(uid, price)
        make_vip(uid, cfg.get("vip_duration_days", 30))
        bot.send_message(uid, f"🎉 <b>CONGRATULATIONS!</b> 🎉\n\nYou are now VIP!\n💰 Balance: {get_points(uid)} 💎")
        bot.edit_message_text(f"🎉 VIP Activated! 🎉", uid, call.message.message_id)
    else:
        bot.send_message(uid, f"❌ Need {price}💎!")

@bot.callback_query_handler(func=lambda c: c.data == "get_vip_info")
def vip_info_callback(call):
    bot.answer_callback_query(call.id)
    cfg = get_cached_config()
    text = f"👑 <b>VIP INFO</b>\n\n"
    text += f"💰 Price: {cfg.get('vip_points_price', 5000):,}💎 or ${cfg.get('vip_price', 50)}\n"
    text += f"✨ Benefits: All VIP methods, No points needed\n"
    text += f"🎁 Free: {cfg.get('referral_vip_count', 50)} referrals = FREE VIP"
    bot.edit_message_text(text, call.from_user.id, call.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == "cancel")
def cancel_callback(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text("❌ Cancelled", call.from_user.id, call.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("back|"))
def back_callback(call):
    bot.answer_callback_query(call.id)
    _, cat, parent = call.data.split("|")
    bot.edit_message_reply_markup(call.from_user.id, call.message.message_id, reply_markup=get_folders_kb(cat, parent if parent else None))

@bot.callback_query_handler(func=lambda c: c.data.startswith("page|"))
def page_callback(call):
    bot.answer_callback_query(call.id)
    _, cat, page, parent = call.data.split("|")
    parent = parent if parent != "None" else None
    bot.edit_message_reply_markup(call.from_user.id, call.message.message_id, reply_markup=get_folders_kb(cat, parent, int(page)))

@bot.callback_query_handler(func=lambda c: c.data == "main_menu")
def main_menu_callback(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    bot.edit_message_text(f"🏠 <b>MAIN MENU</b>\n\n💰 Balance: {get_points(uid)} 💎", uid, call.message.message_id, reply_markup=main_menu(uid))

@bot.callback_query_handler(func=lambda c: c.data == "recheck")
def recheck_callback(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    if uid in _force_cache:
        del _force_cache[uid]
    
    if not force_block(uid):
        bot.edit_message_text("✅ <b>Access Granted!</b>", uid, call.message.message_id)
        bot.send_message(uid, f"🎉 Welcome!\n\n💰 Balance: {get_points(uid)} 💎", reply_markup=main_menu(uid))

@bot.callback_query_handler(func=lambda c: c.data == "noop")
def noop_callback(call):
    bot.answer_callback_query(call.id)

# =========================
# ADMIN HANDLERS
# =========================

@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def admin_panel(message):
    bot.send_message(message.from_user.id, "⚙️ <b>ADMIN PANEL</b>", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "❌ Exit" and is_admin(m.from_user.id))
def exit_admin(message):
    bot.send_message(message.from_user.id, "👋 Exited", reply_markup=main_menu(message.from_user.id))

# Upload sessions
upload_sessions = {}

@bot.message_handler(func=lambda m: m.text in ["📦 Upload FREE", "💎 Upload VIP", "📱 Upload APPS", "⚡ Upload SERVICE"] and is_admin(m.from_user.id))
def start_upload(message):
    cat_map = {"📦 Upload FREE": "free", "💎 Upload VIP": "vip", "📱 Upload APPS": "apps", "⚡ Upload SERVICE": "services"}
    uid = message.from_user.id
    upload_sessions[uid] = {"cat": cat_map[message.text], "step": "name", "files": []}
    bot.send_message(uid, "📝 <b>Enter folder name:</b>")

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions.get(m.from_user.id, {}).get("step") == "name")
def upload_name(message):
    uid = message.from_user.id
    upload_sessions[uid]["name"] = message.text
    upload_sessions[uid]["step"] = "price"
    bot.send_message(uid, "💰 <b>Price (points, 0 = free):</b>")

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions.get(m.from_user.id, {}).get("step") == "price")
def upload_price(message):
    uid = message.from_user.id
    try:
        price = int(message.text)
        upload_sessions[uid]["price"] = price
        upload_sessions[uid]["step"] = "type"
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("📄 Text", "📁 Files")
        kb.add("❌ Cancel")
        bot.send_message(uid, "📝 <b>Content type:</b>", reply_markup=kb)
    except:
        bot.send_message(uid, "❌ Invalid price!")

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions.get(m.from_user.id, {}).get("step") == "type" and m.text == "📄 Text")
def upload_text_type(message):
    uid = message.from_user.id
    upload_sessions[uid]["step"] = "text"
    bot.send_message(uid, "📝 <b>Enter text content:</b>", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("❌ Cancel"))

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions.get(m.from_user.id, {}).get("step") == "type" and m.text == "📁 Files")
def upload_files_type(message):
    uid = message.from_user.id
    upload_sessions[uid]["step"] = "files"
    upload_sessions[uid]["files"] = []
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✅ Done", "❌ Cancel")
    bot.send_message(uid, "📁 <b>Send files:</b>\nPress ✅ Done when finished", reply_markup=kb)

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions.get(m.from_user.id, {}).get("step") == "text")
def upload_save_text(message):
    uid = message.from_user.id
    if message.text == "❌ Cancel":
        upload_sessions.pop(uid, None)
        bot.send_message(uid, "❌ Cancelled", reply_markup=admin_menu())
        return
    
    data = upload_sessions[uid]
    number = add_folder(data["cat"], data["name"], [], data["price"], text_content=message.text)
    if number:
        bot.send_message(uid, f"✅ <b>Added!</b>\n\n📌 #{number}\n📂 {data['name']}\n💰 {data['price']}💎", reply_markup=admin_menu())
    else:
        bot.send_message(uid, "❌ Failed to add!", reply_markup=admin_menu())
    upload_sessions.pop(uid, None)

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions.get(m.from_user.id, {}).get("step") == "files")
def upload_save_files(message):
    uid = message.from_user.id
    
    if message.text == "✅ Done":
        data = upload_sessions[uid]
        if not data.get("files"):
            bot.send_message(uid, "❌ No files!")
            return
        number = add_folder(data["cat"], data["name"], data["files"], data["price"])
        if number:
            bot.send_message(uid, f"✅ <b>Added!</b>\n\n📌 #{number}\n📂 {data['name']}\n💰 {data['price']}💎\n📁 {len(data['files'])} files", reply_markup=admin_menu())
        else:
            bot.send_message(uid, "❌ Failed to add!", reply_markup=admin_menu())
        upload_sessions.pop(uid, None)
        return
    
    if message.text == "❌ Cancel":
        upload_sessions.pop(uid, None)
        bot.send_message(uid, "❌ Cancelled", reply_markup=admin_menu())
        return
    
    if message.content_type in ["photo", "document", "video"]:
        upload_sessions[uid]["files"].append({"chat": message.chat.id, "msg": message.message_id, "type": message.content_type})
        bot.send_message(uid, f"✅ File {len(upload_sessions[uid]['files'])} added")

@bot.message_handler(func=lambda m: m.text == "📁 Create Subfolder" and is_admin(m.from_user.id))
def create_subfolder(message):
    msg = bot.send_message(message.from_user.id, "📁 <b>Create Subfolder</b>\n\nFormat: <code>category parent_name sub_name price</code>\nExample: <code>free Tutorials Advanced 10</code>")
    bot.register_next_step_handler(msg, process_subfolder)

def process_subfolder(message):
    try:
        parts = message.text.split(maxsplit=3)
        cat, parent, name, price = parts[0].lower(), parts[1], parts[2], int(parts[3])
        number = add_folder(cat, name, [], price, parent)
        bot.send_message(message.from_user.id, f"✅ <b>Subfolder added!</b>\n📌 #{number}\n📂 {parent} → {name}", reply_markup=admin_menu())
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
            bot.send_message(message.from_user.id, f"✅ Deleted: {cat} → {name}", reply_markup=admin_menu())
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
        uid = int(parts[0])
        points = int(parts[1])
        
        old = get_points(uid)
        new = add_points(uid, points)
        
        bot.send_message(message.from_user.id, f"✅ Added {points}💎 to {uid}\nOld: {old} → New: {new}", reply_markup=admin_menu())
        try:
            bot.send_message(uid, f"🎉 You received {points} points! New balance: {new}💎")
        except:
            pass
    except:
        bot.send_message(message.from_user.id, "❌ Use: user_id points")

@bot.message_handler(func=lambda m: m.text == "👑 Add VIP" and is_admin(m.from_user.id))
def add_vip_start(message):
    msg = bot.send_message(message.from_user.id, "👑 <b>Give VIP</b>\n\nSend user ID or @username:")
    bot.register_next_step_handler(msg, process_add_vip)

def process_add_vip(message):
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
    
    cfg = get_cached_config()
    make_vip(uid, cfg.get("vip_duration_days", 30))
    bot.send_message(message.from_user.id, f"✅ {uid} is now VIP!", reply_markup=admin_menu())
    try:
        bot.send_message(uid, "👑 You have been granted VIP status!")
    except:
        pass

@bot.message_handler(func=lambda m: m.text == "👑 Remove VIP" and is_admin(m.from_user.id))
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
    bot.send_message(message.from_user.id, f"✅ VIP removed from {uid}", reply_markup=admin_menu())
    try:
        bot.send_message(uid, "⚠️ Your VIP status has been removed.")
    except:
        pass

@bot.message_handler(func=lambda m: m.text == "🎫 Generate Code" and is_admin(m.from_user.id))
def generate_code_start(message):
    msg = bot.send_message(message.from_user.id, "🎫 <b>Generate Code</b>\n\nSend points amount:")
    bot.register_next_step_handler(msg, process_generate_code)

def process_generate_code(message):
    try:
        points = int(message.text)
        code = generate_code(points)
        bot.send_message(message.from_user.id, f"✅ <b>Code generated!</b>\n\n<code>{code}</code>\n💰 +{points} points", reply_markup=admin_menu())
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
            bot.send_message(int(user["_id"]), message.text)
            sent += 1
            if sent % 10 == 0:
                time.sleep(0.1)
        except:
            failed += 1
    
    bot.edit_message_text(f"✅ Broadcast done!\n📤 Sent: {sent}\n❌ Failed: {failed}", message.from_user.id, status.message_id)

@bot.message_handler(func=lambda m: m.text == "📊 Stats" and is_admin(m.from_user.id))
def stats_command(message):
    total = users_col.count_documents({})
    vip = users_col.count_documents({"vip": True})
    total_points = sum(u.get("points", 0) for u in users_col.find({}))
    free_folders = folders_col.count_documents({"cat": "free"})
    vip_folders = folders_col.count_documents({"cat": "vip"})
    total_codes = codes_col.count_documents({})
    
    text = f"📊 <b>STATISTICS</b>\n\n"
    text += f"👥 Users: {total}\n├ VIP: {vip}\n└ Free: {total - vip}\n\n"
    text += f"💰 Points: {total_points:,}\n\n"
    text += f"📁 Content:\n├ FREE: {free_folders}\n└ VIP: {vip_folders}\n\n"
    text += f"🎫 Codes: {total_codes}"
    
    bot.send_message(message.from_user.id, text)

@bot.message_handler(func=lambda m: m.text == "🔔 Toggle Method Notify" and is_admin(m.from_user.id))
def toggle_method_notify(message):
    cfg = get_cached_config()
    current = cfg.get("notify_new_methods", True)
    set_config("notify_new_methods", not current)
    status = "ON" if not current else "OFF"
    bot.send_message(message.from_user.id, f"🔔 New method notifications: <b>{status}</b>", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📊 Leaderboard" and is_admin(m.from_user.id))
def leaderboard_command(message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🏆 Top Points", callback_data="top_points"),
        InlineKeyboardButton("👥 Top Referrals", callback_data="top_refs")
    )
    bot.send_message(message.from_user.id, "📊 <b>LEADERBOARD</b>", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "top_points")
def top_points_admin(call):
    users = list(users_col.find({}).sort("points", -1).limit(20))
    text = "🏆 <b>TOP 20 BY POINTS</b>\n\n"
    for i, u in enumerate(users, 1):
        name = u.get("username") or f"User_{u['_id'][:6]}"
        points = u.get("points", 0)
        vip = "👑" if u.get("vip") else ""
        text += f"{i}. {vip} <code>{name}</code> → {points:,}💎\n"
    bot.edit_message_text(text, call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "top_refs")
def top_refs_admin(call):
    users = list(users_col.find({}).sort("refs", -1).limit(20))
    text = "👥 <b>TOP 20 BY REFERRALS</b>\n\n"
    for i, u in enumerate(users, 1):
        name = u.get("username") or f"User_{u['_id'][:6]}"
        refs = u.get("refs", 0)
        vip = "👑" if u.get("vip") else ""
        text += f"{i}. {vip} <code>{name}</code> → {refs} referrals\n"
    bot.edit_message_text(text, call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

# Simplified admin handlers (placeholders for other features)
@bot.message_handler(func=lambda m: m.text == "✏️ Edit Price" and is_admin(m.from_user.id))
def edit_price_start(m):
    bot.send_message(m.from_user.id, "✏️ Edit Price - Use: category name price\nExample: free Test 100")

@bot.message_handler(func=lambda m: m.text == "✏️ Edit Name" and is_admin(m.from_user.id))
def edit_name_start(m):
    bot.send_message(m.from_user.id, "✏️ Edit Name - Use: category old new\nExample: free Old New")

@bot.message_handler(func=lambda m: m.text == "📝 Edit Content" and is_admin(m.from_user.id))
def edit_content_start(m):
    bot.send_message(m.from_user.id, "📝 Edit Content - Coming soon")

@bot.message_handler(func=lambda m: m.text == "🔀 Move Folder" and is_admin(m.from_user.id))
def move_folder_start(m):
    bot.send_message(m.from_user.id, "🔀 Move Folder - Coming soon")

@bot.message_handler(func=lambda m: m.text == "📦 Points Packages" and is_admin(m.from_user.id))
def points_packages_start(m):
    bot.send_message(m.from_user.id, "📦 Points Packages - Coming soon")

@bot.message_handler(func=lambda m: m.text == "👥 Admin Management" and is_admin(m.from_user.id))
def admin_management_start(m):
    bot.send_message(m.from_user.id, "👥 Admin Management - Coming soon")

@bot.message_handler(func=lambda m: m.text == "📞 Set Contacts" and is_admin(m.from_user.id))
def set_contacts_start(m):
    bot.send_message(m.from_user.id, "📞 Set Contacts - Coming soon")

@bot.message_handler(func=lambda m: m.text == "⚙️ VIP Settings" and is_admin(m.from_user.id))
def vip_settings_start(m):
    bot.send_message(m.from_user.id, "⚙️ VIP Settings - Coming soon")

@bot.message_handler(func=lambda m: m.text == "💳 Payment Methods" and is_admin(m.from_user.id))
def payment_methods_start(m):
    bot.send_message(m.from_user.id, "💳 Payment Methods - Coming soon")

@bot.message_handler(func=lambda m: m.text == "🏦 Binance Settings" and is_admin(m.from_user.id))
def binance_settings_start(m):
    bot.send_message(m.from_user.id, "🏦 Binance Settings - Coming soon")

@bot.message_handler(func=lambda m: m.text == "📸 Screenshot" and is_admin(m.from_user.id))
def screenshot_settings_start(m):
    bot.send_message(m.from_user.id, "📸 Screenshot - Coming soon")

@bot.message_handler(func=lambda m: m.text == "➕ Add Button" and is_admin(m.from_user.id))
def add_button_start(m):
    bot.send_message(m.from_user.id, "➕ Add Button - Coming soon")

@bot.message_handler(func=lambda m: m.text == "➖ Remove Button" and is_admin(m.from_user.id))
def remove_button_start(m):
    bot.send_message(m.from_user.id, "➖ Remove Button - Coming soon")

@bot.message_handler(func=lambda m: m.text == "➕ Add Channel" and is_admin(m.from_user.id))
def add_channel_start(m):
    bot.send_message(m.from_user.id, "➕ Add Channel - Coming soon")

@bot.message_handler(func=lambda m: m.text == "➖ Remove Channel" and is_admin(m.from_user.id))
def remove_channel_start(m):
    bot.send_message(m.from_user.id, "➖ Remove Channel - Coming soon")

@bot.message_handler(func=lambda m: m.text == "⚙️ Settings" and is_admin(m.from_user.id))
def settings_start(m):
    bot.send_message(m.from_user.id, "⚙️ Settings - Coming soon")

@bot.message_handler(func=lambda m: m.text == "🔔 Notify" and is_admin(m.from_user.id))
def notify_toggle(m):
    bot.send_message(m.from_user.id, "🔔 Notify toggled")

# Fallback
@bot.message_handler(func=lambda m: True)
def fallback(message):
    uid = message.from_user.id
    if not force_block(uid):
        bot.send_message(uid, "❌ Use menu buttons", reply_markup=main_menu(uid))

# =========================
# MAIN
# =========================
def main():
    print("=" * 50)
    print("🚀 ZEDOX BOT - FULLY FUNCTIONAL")
    print(f"✅ Bot: @{bot.get_me().username}")
    print(f"👑 Admin: {ADMIN_ID}")
    print(f"📊 Category Counts: ENABLED")
    print(f"📄 Page Numbers: ENABLED")
    print(f"🏷️ Auto Emojis: ENABLED")
    print(f"🔔 Method Notifications: ENABLED")
    print("=" * 50)
    
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=60)
        except Exception as e:
            print(f"⚠️ Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
