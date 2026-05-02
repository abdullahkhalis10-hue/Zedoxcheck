# =========================
# ZEDOX BOT - ULTRA FAST VERSION
# With Subfolders, Caching, Notifications, & Page Numbers
# =========================

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
import os, time, random, string, threading, hashlib, hmac
from pymongo import MongoClient
from datetime import datetime, timedelta
from functools import wraps
from cachetools import TTLCache

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set!")

# MongoDB Setup
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable not set!")

client = MongoClient(MONGO_URI, maxPoolSize=50, minPoolSize=10, connectTimeoutMS=5000)
db = client["zedox_fast"]

# Collections
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

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# =========================
# 🚀 FAST CACHE SYSTEM
# =========================
user_cache = TTLCache(maxsize=1000, ttl=60)
folder_cache = TTLCache(maxsize=500, ttl=120)
config_cache = TTLCache(maxsize=10, ttl=60)

# =========================
# 🔐 SECURITY & HELPERS
# =========================
def get_cached_config():
    key = "config"
    if key in config_cache:
        return config_cache[key]
    cfg = config_col.find_one({"_id": "config"})
    if not cfg:
        cfg = {
            "_id": "config",
            "force_channels": [],
            "custom_buttons": [],
            "vip_msg": "💎 Buy VIP to unlock premium content!",
            "welcome": "🔥 Welcome to ZEDOX BOT! 🚀",
            "ref_reward": 5,
            "notify_new_methods": True,  # New: Notification toggle
            "purchase_msg": "💰 Purchase VIP to access premium features!",
            "next_folder_number": 1,
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
    config_cache[key] = cfg
    return cfg

def set_config(key, value):
    config_col.update_one({"_id": "config"}, {"$set": {key: value}}, upsert=True)
    config_cache.pop("config", None)

def is_admin(uid):
    uid = int(uid) if isinstance(uid, str) else uid
    if uid == ADMIN_ID:
        return True
    return admins_col.find_one({"_id": uid}) is not None

def init_admins():
    if not admins_col.find_one({"_id": ADMIN_ID}):
        admins_col.insert_one({"_id": ADMIN_ID, "is_owner": True, "added_at": time.time()})

init_admins()

# =========================
# 👤 USER CLASS (FAST)
# =========================
class User:
    @staticmethod
    def get(uid):
        uid = str(uid)
        if uid in user_cache:
            return user_cache[uid]
        
        data = users_col.find_one({"_id": uid})
        if not data:
            data = {
                "_id": uid,
                "points": 0,
                "vip": False,
                "vip_expiry": None,
                "ref": None,
                "refs": 0,
                "refs_bought_vip": 0,
                "purchased_methods": [],
                "used_codes": [],
                "username": None,
                "created_at": time.time(),
                "last_active": time.time(),
                "total_earned": 0,
                "total_spent": 0
            }
            users_col.insert_one(data)
        
        user_cache[uid] = data
        return data
    
    @staticmethod
    def save(uid, data):
        users_col.update_one({"_id": str(uid)}, {"$set": data})
        user_cache[str(uid)] = data
    
    @staticmethod
    def is_vip(uid):
        data = User.get(uid)
        if data.get("vip", False):
            expiry = data.get("vip_expiry")
            if expiry and expiry < time.time():
                data["vip"] = False
                data["vip_expiry"] = None
                User.save(uid, data)
                return False
            return True
        return False
    
    @staticmethod
    def points(uid):
        return User.get(uid).get("points", 0)
    
    @staticmethod
    def add_points(uid, amount):
        data = User.get(uid)
        data["points"] = data.get("points", 0) + amount
        data["total_earned"] = data.get("total_earned", 0) + amount
        User.save(uid, data)
        return data["points"]
    
    @staticmethod
    def spend_points(uid, amount):
        data = User.get(uid)
        data["points"] = data.get("points", 0) - amount
        data["total_spent"] = data.get("total_spent", 0) + amount
        User.save(uid, data)
        return data["points"]

# =========================
# 📁 FOLDER SYSTEM (FAST)
# =========================
class FolderSystem:
    @staticmethod
    def add(cat, name, files, price, parent=None, text_content=None):
        config = get_cached_config()
        number = config.get("next_folder_number", 1)
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
        
        # Send notification to all users if enabled
        if config.get("notify_new_methods", True):
            threading.Thread(target=notify_new_method, args=(cat, name, number)).start()
        
        return number
    
    @staticmethod
    def get(cat, parent=None):
        cache_key = f"{cat}_{parent}"
        if cache_key in folder_cache:
            return folder_cache[cache_key]
        
        query = {"cat": cat}
        if parent:
            query["parent"] = parent
        else:
            query["parent"] = {"$in": [None, "", "root"]}
        
        result = list(folders_col.find(query).sort("number", 1))
        folder_cache[cache_key] = result
        return result
    
    @staticmethod
    def get_one(cat, name, parent=None):
        query = {"cat": cat, "name": name}
        if parent:
            query["parent"] = parent
        return folders_col.find_one(query)
    
    @staticmethod
    def get_by_number(number):
        return folders_col.find_one({"number": number})
    
    @staticmethod
    def delete(cat, name, parent=None):
        query = {"cat": cat, "name": name}
        if parent:
            query["parent"] = parent
        result = folders_col.delete_one(query)
        FolderSystem.clear_cache()
        return result.deleted_count > 0
    
    @staticmethod
    def clear_cache():
        folder_cache.clear()

fs = FolderSystem()

# =========================
# 🔔 NOTIFICATION SYSTEM (NEW)
# =========================
def notify_new_method(cat, name, number):
    """Send notification to all users about new method"""
    cfg = get_cached_config()
    if not cfg.get("notify_new_methods", True):
        return
    
    cat_emoji = {
        "free": "📂",
        "vip": "💎",
        "apps": "📱",
        "services": "⚡"
    }
    
    message = f"🎉 **NEW METHOD ADDED!** 🎉\n\n"
    message += f"{cat_emoji.get(cat, '📌')} **Category:** {cat.upper()}\n"
    message += f"📌 **#{number}** {name}\n\n"
    message += f"✨ Check it out in the menu!"
    
    # Send to all users (async)
    def broadcast():
        for user in users_col.find({}, {"_id": 1}):
            try:
                bot.send_message(int(user["_id"]), message, parse_mode="HTML")
                time.sleep(0.05)  # Fast, but not too fast
            except:
                pass
    
    threading.Thread(target=broadcast).start()

# =========================
# 🏷️ EMOJI AUTO-ADD (NEW FEATURE)
# =========================
def add_emoji(name, cat=None):
    """Auto-add emojis based on name/category"""
    emoji_map = {
        "premium": "💎",
        "free": "🆓",
        "vip": "👑",
        "app": "📱",
        "apps": "📱",
        "service": "⚡",
        "services": "⚡",
        "method": "🔧",
        "tutorial": "📚",
        "guide": "📖",
        "tool": "🛠️",
        "hack": "🎮",
        "cheat": "🎯",
        "crack": "🔓",
        "key": "🔑",
        "license": "📜",
        "account": "👤",
        "card": "💳",
        "paypal": "💰",
        "bank": "🏦",
        "crypto": "🪙",
        "bitcoin": "₿",
        "usdt": "💵"
    }
    
    name_lower = name.lower()
    for keyword, emoji in emoji_map.items():
        if keyword in name_lower:
            return f"{emoji} {name}"
    
    # Category-based emojis
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
# 📄 CATEGORY MENU WITH PAGE NUMBERS
# =========================
def format_folder_button(folder, cat):
    """Format folder button with proper emoji and price"""
    name = folder["name"]
    price = folder.get("price", 0)
    number = folder.get("number", "?")
    has_subs = len(fs.get(cat, name)) > 0
    
    icon = "📁" if has_subs else "📄"
    display_name = add_emoji(name, cat)
    
    text = f"{icon} [{number}] {display_name}"
    if price > 0 and not has_subs:
        text += f" ─ {price}💎"
    
    return text

def get_folders_kb(cat, parent=None, page=0, items_per_page=10):
    """Get keyboard with page number display"""
    data = fs.get(cat, parent)
    total_items = len(data)
    total_pages = (total_items + items_per_page - 1) // items_per_page
    page = max(0, min(page, total_pages - 1))
    
    start = page * items_per_page
    end = start + items_per_page
    page_items = data[start:end]
    
    kb = InlineKeyboardMarkup(row_width=2)
    
    for item in page_items:
        text = format_folder_button(item, cat)
        callback = f"open|{cat}|{item['name']}|{parent or ''}"
        kb.add(InlineKeyboardButton(text, callback_data=callback))
    
    # Navigation row with page indicator
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"page|{cat}|{page-1}|{parent or ''}"))
    
    nav_row.append(InlineKeyboardButton(f"📄 PAGE {page+1}/{total_pages}", callback_data="noop"))
    
    if end < total_items:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"page|{cat}|{page+1}|{parent or ''}"))
    
    if nav_row:
        kb.row(*nav_row)
    
    # Back button
    if parent:
        kb.add(InlineKeyboardButton("🔙 BACK", callback_data=f"back|{cat}|{parent}"))
    else:
        kb.add(InlineKeyboardButton("🏠 MAIN MENU", callback_data="main_menu"))
    
    return kb

# =========================
# 🚀 MAIN MENU (SEPARATE CATEGORIES)
# =========================
def main_menu(uid):
    """Main menu with separate categories"""
    user = User.get(uid)
    points = user.get("points", 0)
    
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Main categories with emojis
    kb.add("📂 FREE METHODS", "💎 VIP METHODS")
    kb.add("📱 PREMIUM APPS", "⚡ SERVICES")
    
    # Points & VIP row
    kb.add("💰 MY WALLET", "⭐ BUY VIP")
    kb.add("🎁 REFERRAL", "👤 PROFILE")
    kb.add("🏆 MY PURCHASES", "🎫 REDEEM CODE")
    
    # Admin button
    if is_admin(uid):
        kb.add("⚙️ ADMIN PANEL")
    
    return kb, points

# =========================
# 🚀 FAST START
# =========================
@bot.message_handler(commands=["start"])
def start_cmd(m):
    uid = m.from_user.id
    chat_id = m.chat.id
    
    # Handle referral
    args = m.text.split()
    if len(args) > 1:
        ref_id = args[1]
        if ref_id != str(uid) and ref_id.isdigit():
            ref_data = users_col.find_one({"_id": ref_id})
            if ref_data and not User.get(uid).get("ref"):
                cfg = get_cached_config()
                reward = cfg.get("ref_reward", 5)
                
                User.add_points(ref_id, reward)
                ref_data = User.get(ref_id)
                ref_data["refs"] = ref_data.get("refs", 0) + 1
                User.save(ref_id, ref_data)
                
                user_data = User.get(uid)
                user_data["ref"] = ref_id
                User.save(uid, user_data)
                
                # Check for VIP via referrals
                if ref_data.get("refs", 0) >= cfg.get("referral_vip_count", 50):
                    if not User.is_vip(ref_id):
                        ref_data["vip"] = True
                        ref_data["vip_expiry"] = time.time() + (cfg.get("vip_duration_days", 30) * 86400)
                        User.save(ref_id, ref_data)
                        try:
                            bot.send_message(int(ref_id), "🎉 **CONGRATULATIONS!** 🎉\n\nYou've reached the referral goal and got **FREE VIP**!")
                        except:
                            pass
    
    cfg = get_cached_config()
    welcome = cfg.get("welcome", "🔥 Welcome to ZEDOX BOT! 🚀")
    user_data = User.get(uid)
    
    if m.from_user.username:
        user_data["username"] = m.from_user.username
        User.save(uid, user_data)
    
    menu, points = main_menu(uid)
    bot.send_message(chat_id, f"{welcome}\n\n💰 **Balance:** {points} 💎", reply_markup=menu)

# =========================
# 💰 MY WALLET (FAST RESPONSE)
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 MY WALLET")
def wallet_cmd(m):
    uid = m.from_user.id
    user = User.get(uid)
    
    message = f"┌─💰 **YOUR WALLET** ─┐\n\n"
    message += f"├ 💎 Points: `{user.get('points', 0)}`\n"
    message += f"├ 👑 VIP: `{'✅ Active' if User.is_vip(uid) else '❌ Not Active'}`\n"
    message += f"├ 📊 Referrals: `{user.get('refs', 0)}`\n"
    message += f"├ 🎯 Referral Purchases: `{user.get('refs_bought_vip', 0)}`\n"
    message += f"├ 📈 Total Earned: `{user.get('total_earned', 0)}`\n"
    message += f"└ 📉 Total Spent: `{user.get('total_spent', 0)}`\n\n"
    
    message += f"✨ **WAYS TO EARN:**\n"
    message += f"• 🎁 Referral program\n"
    message += f"• 🎫 Redeem codes\n"
    message += f"• 💎 Purchase points"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💎 GET POINTS", callback_data="get_points"))
    kb.add(InlineKeyboardButton("🎁 REFERRAL LINK", callback_data="get_referral"))
    
    bot.send_message(uid, message, reply_markup=kb)

# =========================
# 👤 PROFILE
# =========================
@bot.message_handler(func=lambda m: m.text == "👤 PROFILE")
def profile_cmd(m):
    uid = m.from_user.id
    user = User.get(uid)
    
    status = "💎 VIP" if User.is_vip(uid) else "🆓 FREE"
    purchased = len(user.get("purchased_methods", []))
    
    message = f"┌─👤 **USER PROFILE** ─┐\n\n"
    message += f"├ 🆔 ID: `{uid}`\n"
    message += f"├ 📛 Name: {m.from_user.first_name}\n"
    message += f"├ 🎭 Status: {status}\n"
    message += f"├ 💎 Points: `{user.get('points', 0)}`\n"
    message += f"├ 📚 Purchased: `{purchased}` methods\n"
    message += f"├ 👥 Referrals: `{user.get('refs', 0)}`\n"
    message += f"├ 🎯 Referral VIP: `{user.get('refs_bought_vip', 0)}`\n"
    message += f"└ 📅 Joined: {datetime.fromtimestamp(user.get('created_at', time.time())).strftime('%Y-%m-%d')}"
    
    bot.send_message(uid, message)

# =========================
# 🏆 MY PURCHASES
# =========================
@bot.message_handler(func=lambda m: m.text == "🏆 MY PURCHASES")
def my_purchases_cmd(m):
    uid = m.from_user.id
    user = User.get(uid)
    
    if User.is_vip(uid):
        bot.send_message(uid, "👑 **VIP MEMBER**\n\nYou have access to ALL VIP methods!")
        return
    
    purchased = user.get("purchased_methods", [])
    if not purchased:
        bot.send_message(uid, "📚 **No purchased methods yet**\n\nUse your points to buy methods from 💎 VIP METHODS!")
        return
    
    message = f"📚 **YOUR PURCHASES** ({len(purchased)})\n\n"
    for i, method in enumerate(purchased, 1):
        message += f"{i}. {method}\n"
    
    bot.send_message(uid, message)

# =========================
# 🎫 REDEEM CODE
# =========================
@bot.message_handler(func=lambda m: m.text == "🎫 REDEEM CODE")
def redeem_code_cmd(m):
    msg = bot.send_message(m.from_user.id, "🎫 **Enter your code:**\n\nExample: `ZEDOXABC123`")
    bot.register_next_step_handler(msg, process_redeem)

def process_redeem(m):
    uid = m.from_user.id
    code = m.text.strip().upper()
    
    code_data = codes_col.find_one({"_id": code})
    
    if not code_data:
        bot.send_message(uid, "❌ **Invalid code!**\n\nPlease check and try again.")
        return
    
    if code_data.get("expiry") and time.time() > code_data["expiry"]:
        bot.send_message(uid, "⏰ **Code expired!**")
        return
    
    user_data = User.get(uid)
    used_codes = user_data.get("used_codes", [])
    
    if code in used_codes:
        bot.send_message(uid, "❌ **You already used this code!**")
        return
    
    # Redeem
    points = code_data.get("points", 0)
    User.add_points(uid, points)
    
    used_codes.append(code)
    user_data["used_codes"] = used_codes
    User.save(uid, user_data)
    
    # Update code usage
    codes_col.update_one({"_id": code}, {"$inc": {"used_count": 1}, "$push": {"used_by": uid}})
    
    new_balance = User.points(uid)
    bot.send_message(uid, f"✅ **CODE REDEEMED!** ✅\n\n➕ +{points} 💎\n💰 New Balance: {new_balance} 💎")

# =========================
# 📂 CATEGORY HANDLERS
# =========================
@bot.message_handler(func=lambda m: m.text in ["📂 FREE METHODS", "💎 VIP METHODS", "📱 PREMIUM APPS", "⚡ SERVICES"])
def show_category(m):
    uid = m.from_user.id
    cat_map = {
        "📂 FREE METHODS": "free",
        "💎 VIP METHODS": "vip",
        "📱 PREMIUM APPS": "apps",
        "⚡ SERVICES": "services"
    }
    cat = cat_map.get(m.text)
    
    items = fs.get(cat)
    if not items:
        bot.send_message(uid, f"📂 **{m.text}**\n\nNo content available yet.")
        return
    
    bot.send_message(uid, f"📂 **{m.text}**\n\nSelect an option:", reply_markup=get_folders_kb(cat))

# =========================
# 📂 OPEN FOLDER (FAST)
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("open|"))
def open_folder_callback(c):
    uid = c.from_user.id
    parts = c.data.split("|")
    cat = parts[1]
    name = parts[2]
    parent = parts[3] if len(parts) > 3 and parts[3] else None
    
    folder = fs.get_one(cat, name, parent if parent else None)
    if not folder:
        bot.answer_callback_query(c.id, "❌ Not found!")
        return
    
    # Check for subfolders
    subfolders = fs.get(cat, name)
    if subfolders:
        kb = InlineKeyboardMarkup(row_width=1)
        for sub in subfolders:
            text = format_folder_button(sub, cat)
            kb.add(InlineKeyboardButton(text, callback_data=f"open|{cat}|{sub['name']}|{name}"))
        kb.add(InlineKeyboardButton("🔙 BACK", callback_data=f"back|{cat}|{parent or ''}"))
        
        bot.edit_message_text(f"📁 **{add_emoji(name, cat)}**", uid, c.message.message_id, reply_markup=kb)
        bot.answer_callback_query(c.id)
        return
    
    # Check access
    price = folder.get("price", 0)
    is_premium = cat == "vip"
    user_is_vip = User.is_vip(uid)
    user_purchased = name in User.get(uid).get("purchased_methods", [])
    
    if is_premium and not user_is_vip and not user_purchased:
        if price > 0:
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton(f"💰 BUY ({price}💎)", callback_data=f"buy|{cat}|{name}|{price}"),
                InlineKeyboardButton("👑 GET VIP", callback_data="get_vip_info")
            )
            kb.add(InlineKeyboardButton("❌ CANCEL", callback_data="cancel_buy"))
            bot.edit_message_text(f"🔒 **{add_emoji(name, cat)}**\n\nPrice: {price} 💎\nYour balance: {User.points(uid)} 💎", uid, c.message.message_id, reply_markup=kb)
        else:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("👑 GET VIP", callback_data="get_vip_info"))
            bot.edit_message_text(f"🔒 **{add_emoji(name, cat)}**\n\nVIP only!", uid, c.message.message_id, reply_markup=kb)
        bot.answer_callback_query(c.id)
        return
    
    # Deduct points if needed
    if price > 0 and not user_is_vip and not user_purchased:
        if User.points(uid) < price:
            bot.answer_callback_query(c.id, f"❌ Need {price}💎! You have {User.points(uid)}", True)
            return
        User.spend_points(uid, price)
    
    # Mark as purchased if VIP method
    if is_premium and not user_is_vip:
        user_data = User.get(uid)
        purchased = user_data.get("purchased_methods", [])
        if name not in purchased:
            purchased.append(name)
            user_data["purchased_methods"] = purchased
            User.save(uid, user_data)
    
    # Send content
    text_content = folder.get("text_content")
    files = folder.get("files", [])
    
    if text_content:
        bot.edit_message_text(f"📄 **{add_emoji(name, cat)}**\n\n{text_content}", uid, c.message.message_id)
    elif files:
        bot.answer_callback_query(c.id, "📤 Sending...")
        for f in files[:5]:  # Max 5 files per folder
            try:
                if f.get("type") == "photo":
                    bot.copy_message(uid, f["chat"], f["msg"])
                elif f.get("type") == "document":
                    bot.copy_message(uid, f["chat"], f["msg"])
                elif f.get("type") == "video":
                    bot.copy_message(uid, f["chat"], f["msg"])
                time.sleep(0.1)
            except:
                pass
        bot.send_message(uid, f"✅ **{name}** sent!")
    else:
        bot.edit_message_text(f"📁 **{add_emoji(name, cat)}**\n\nNo content.", uid, c.message.message_id)
    
    bot.answer_callback_query(c.id)

# =========================
# 💰 BUY METHOD
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy|"))
def buy_method_callback(c):
    uid = c.from_user.id
    _, cat, name, price = c.data.split("|")
    price = int(price)
    
    if User.is_vip(uid):
        bot.answer_callback_query(c.id, "✅ You're VIP! Access free!", True)
        open_folder_callback(c)
        return
    
    user_data = User.get(uid)
    if name in user_data.get("purchased_methods", []):
        bot.answer_callback_query(c.id, "✅ You already own this!", True)
        open_folder_callback(c)
        return
    
    if User.points(uid) < price:
        bot.answer_callback_query(c.id, f"❌ Need {price}💎! Balance: {User.points(uid)}", True)
        return
    
    User.spend_points(uid, price)
    purchased = user_data.get("purchased_methods", [])
    purchased.append(name)
    user_data["purchased_methods"] = purchased
    User.save(uid, user_data)
    
    bot.answer_callback_query(c.id, f"✅ Purchased! -{price}💎", True)
    bot.edit_message_text(f"✅ **PURCHASED!**\n\nYou now own: {name}\nRemaining: {User.points(uid)}💎", uid, c.message.message_id)
    
    # Auto-open the method
    time.sleep(0.5)
    open_folder_callback(c)

# =========================
# 🎁 REFERRAL
# =========================
@bot.message_handler(func=lambda m: m.text == "🎁 REFERRAL")
def referral_cmd(m):
    uid = m.from_user.id
    user = User.get(uid)
    cfg = get_cached_config()
    
    link = f"https://t.me/{bot.get_me().username}?start={uid}"
    refs = user.get("refs", 0)
    reward = cfg.get("ref_reward", 5)
    
    message = f"┌─🎁 **REFERRAL PROGRAM** ─┐\n\n"
    message += f"├ 🔗 **Your Link:**\n├ `{link}`\n\n"
    message += f"├ 📊 **Your Stats:**\n"
    message += f"├ 👥 Referrals: `{refs}`\n"
    message += f"├ 💰 Points Earned: `{refs * reward}`\n"
    message += f"└ 🎯 Progress: `{refs}/{cfg.get('referral_vip_count', 50)}`\n\n"
    message += f"✨ **REWARDS:**\n"
    message += f"• +{reward}💎 per referral\n"
    message += f"• {cfg.get('referral_vip_count', 50)} referrals → FREE VIP 👑\n"
    message += f"• {cfg.get('referral_purchase_count', 10)} referral purchases → FREE VIP 👑"
    
    bot.send_message(uid, message)

# =========================
# ⭐ BUY VIP
# =========================
@bot.message_handler(func=lambda m: m.text == "⭐ BUY VIP")
def buy_vip_cmd(m):
    uid = m.from_user.id
    cfg = get_cached_config()
    
    if User.is_vip(uid):
        bot.send_message(uid, "👑 **You are already VIP!**")
        return
    
    vip_price_usd = cfg.get("vip_price", 50)
    vip_price_points = cfg.get("vip_points_price", 5000)
    
    message = f"┌─👑 **VIP MEMBERSHIP** ─┐\n\n"
    message += f"├ {cfg.get('vip_msg', '💎 Buy VIP for premium access!')}\n\n"
    message += f"├ 💰 **PRICES:**\n"
    message += f"├   • ${vip_price_usd} USD\n"
    message += f"└   • {vip_price_points} 💎 points\n\n"
    message += f"✨ **BENEFITS:**\n"
    message += f"• Access to ALL VIP methods\n"
    message += f"• Priority support\n"
    message += f"• No points needed\n"
    message += f"• Exclusive content\n\n"
    message += f"💳 **Payment:** Binance USDT (TRC20)\n"
    message += f"Contact admin for payment details."
    
    kb = InlineKeyboardMarkup(row_width=2)
    if User.points(uid) >= vip_price_points:
        kb.add(InlineKeyboardButton(f"👑 BUY WITH {vip_price_points}💎", callback_data="buy_vip_points"))
    if cfg.get("vip_contact"):
        contact = cfg.get("vip_contact")
        if contact.startswith("@"):
            kb.add(InlineKeyboardButton("📞 CONTACT ADMIN", url=f"https://t.me/{contact[1:]}"))
        else:
            kb.add(InlineKeyboardButton("📞 CONTACT ADMIN", url=contact))
    
    bot.send_message(uid, message, reply_markup=kb if kb.keyboard else None)

@bot.callback_query_handler(func=lambda c: c.data == "buy_vip_points")
def buy_vip_points_callback(c):
    uid = c.from_user.id
    cfg = get_cached_config()
    price = cfg.get("vip_points_price", 5000)
    
    if User.is_vip(uid):
        bot.answer_callback_query(c.id, "✅ Already VIP!", True)
        return
    
    if User.points(uid) >= price:
        User.spend_points(uid, price)
        user_data = User.get(uid)
        user_data["vip"] = True
        user_data["vip_expiry"] = time.time() + (cfg.get("vip_duration_days", 30) * 86400)
        User.save(uid, user_data)
        
        bot.answer_callback_query(c.id, "✅ VIP Activated!", True)
        bot.edit_message_text(f"🎉 **CONGRATULATIONS!** 🎉\n\nYou are now VIP!\n💰 Balance: {User.points(uid)}💎", uid, c.message.message_id)
    else:
        bot.answer_callback_query(c.id, f"❌ Need {price}💎! Balance: {User.points(uid)}", True)

# =========================
# 🔙 BACK & PAGE HANDLERS
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("back|"))
def back_callback(c):
    _, cat, parent = c.data.split("|")
    bot.edit_message_reply_markup(c.from_user.id, c.message.message_id, reply_markup=get_folders_kb(cat, parent if parent else None))

@bot.callback_query_handler(func=lambda c: c.data.startswith("page|"))
def page_callback(c):
    _, cat, page, parent = c.data.split("|")
    parent = parent if parent != "None" else None
    bot.edit_message_reply_markup(c.from_user.id, c.message.message_id, reply_markup=get_folders_kb(cat, parent, int(page)))

@bot.callback_query_handler(func=lambda c: c.data == "main_menu")
def main_menu_callback(c):
    menu, points = main_menu(c.from_user.id)
    bot.edit_message_text(f"🏠 **MAIN MENU**\n\n💰 Balance: {points}💎", c.from_user.id, c.message.message_id, reply_markup=menu)

@bot.callback_query_handler(func=lambda c: c.data == "cancel_buy")
def cancel_buy_callback(c):
    bot.edit_message_text("❌ Cancelled", c.from_user.id, c.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == "get_points")
def get_points_callback(c):
    uid = c.from_user.id
    cfg = get_cached_config()
    
    message = f"💎 **GET POINTS** 💎\n\n"
    message += f"💰 Balance: {User.points(uid)}💎\n\n"
    message += f"✨ **Purchase Points:**\n"
    message += f"• 100💎 = $5 USD\n"
    message += f"• 250💎 = $10 USD (+25 bonus)\n"
    message += f"• 550💎 = $20 USD (+100 bonus)\n"
    message += f"• 1500💎 = $50 USD (+500 bonus)\n\n"
    message += f"💳 **Payment:** Binance USDT (TRC20)\n"
    message += f"Contact admin to purchase."
    
    kb = InlineKeyboardMarkup()
    if cfg.get("contact_username"):
        contact = cfg.get("contact_username")
        if contact.startswith("@"):
            kb.add(InlineKeyboardButton("📞 CONTACT", url=f"https://t.me/{contact[1:]}"))
    elif cfg.get("contact_link"):
        kb.add(InlineKeyboardButton("📞 CONTACT", url=cfg.get("contact_link")))
    
    bot.edit_message_text(message, uid, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "get_referral")
def get_referral_callback(c):
    uid = c.from_user.id
    link = f"https://t.me/{bot.get_me().username}?start={uid}"
    bot.edit_message_text(f"🎁 **YOUR REFERRAL LINK**\n\n`{link}`\n\nShare this link to earn points!", uid, c.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == "get_vip_info")
def vip_info_callback(c):
    uid = c.from_user.id
    cfg = get_cached_config()
    
    message = f"👑 **VIP INFORMATION** 👑\n\n"
    message += f"✨ **Benefits:**\n"
    message += f"• All VIP methods unlocked\n"
    message += f"• No points needed\n"
    message += f"• Priority support\n"
    message += f"• Exclusive content\n\n"
    message += f"💰 **Price:** ${cfg.get('vip_price', 50)} or {cfg.get('vip_points_price', 5000)}💎\n\n"
    message += f"🎁 **Free VIP:**\n"
    message += f"• Invite {cfg.get('referral_vip_count', 50)} users\n"
    message += f"• Get {cfg.get('referral_purchase_count', 10)} referrals to buy VIP"
    
    bot.edit_message_text(message, uid, c.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == "noop")
def noop_callback(c):
    bot.answer_callback_query(c.id)

# =========================
# ⚙️ ADMIN PANEL
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def admin_panel(m):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Add FREE", "💎 Add VIP")
    kb.add("📱 Add APP", "⚡ Add SERVICE")
    kb.add("📁 Add Subfolder", "🗑 Delete Folder")
    kb.add("💰 Give Points", "👑 Give VIP")
    kb.add("🗑 Remove VIP", "🎫 Generate Code")
    kb.add("📊 View Codes", "📢 Broadcast")
    kb.add("🔔 Toggle Notify", "📊 Stats")
    kb.add("⚙️ Settings", "❌ Exit")
    bot.send_message(m.from_user.id, "⚙️ **ADMIN PANEL**", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "❌ Exit" and is_admin(m.from_user.id))
def exit_admin(m):
    menu, _ = main_menu(m.from_user.id)
    bot.send_message(m.from_user.id, "👋 Exited admin mode", reply_markup=menu)

# 📦 Add Content
uploading = {}

@bot.message_handler(func=lambda m: m.text in ["📦 Add FREE", "💎 Add VIP", "📱 Add APP", "⚡ Add SERVICE"] and is_admin(m.from_user.id))
def start_upload(m):
    cat_map = {
        "📦 Add FREE": "free",
        "💎 Add VIP": "vip",
        "📱 Add APP": "apps",
        "⚡ Add SERVICE": "services"
    }
    uid = m.from_user.id
    uploading[uid] = {"cat": cat_map[m.text], "files": [], "step": "name"}
    bot.send_message(uid, "📝 **Enter folder name:**")

@bot.message_handler(func=lambda m: m.from_user.id in uploading and uploading[m.from_user.id].get("step") == "name")
def upload_name(m):
    uid = m.from_user.id
    uploading[uid]["name"] = m.text
    uploading[uid]["step"] = "price"
    bot.send_message(uid, "💰 **Price (points, 0 = free):**")

@bot.message_handler(func=lambda m: m.from_user.id in uploading and uploading[m.from_user.id].get("step") == "price")
def upload_price(m):
    uid = m.from_user.id
    try:
        price = int(m.text)
        if price < 0:
            raise ValueError
        uploading[uid]["price"] = price
        uploading[uid]["step"] = "content"
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("📄 Text", "📁 Files")
        kb.add("/skip", "/cancel")
        bot.send_message(uid, "📝 **Content type:**\nChoose 'Text' for message or 'Files' for media", reply_markup=kb)
    except:
        bot.send_message(uid, "❌ Invalid price! Enter a number:")

@bot.message_handler(func=lambda m: m.from_user.id in uploading and uploading[m.from_user.id].get("step") == "content" and m.text == "📄 Text")
def upload_text_type(m):
    uid = m.from_user.id
    uploading[uid]["type"] = "text"
    uploading[uid]["step"] = "text_content"
    bot.send_message(uid, "📝 **Enter text content:**", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("/cancel"))

@bot.message_handler(func=lambda m: m.from_user.id in uploading and uploading[m.from_user.id].get("step") == "content" and m.text == "📁 Files")
def upload_files_type(m):
    uid = m.from_user.id
    uploading[uid]["type"] = "files"
    uploading[uid]["step"] = "files"
    uploading[uid]["files"] = []
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("/done", "/cancel")
    bot.send_message(uid, "📁 **Send files:**\nPress /done when finished", reply_markup=kb)

@bot.message_handler(func=lambda m: m.from_user.id in uploading and uploading[m.from_user.id].get("step") == "text_content")
def upload_text_save(m):
    uid = m.from_user.id
    data = uploading[uid]
    
    number = fs.add(
        cat=data["cat"],
        name=data["name"],
        files=[],
        price=data["price"],
        text_content=m.text
    )
    
    bot.send_message(uid, f"✅ **ADDED!**\n\n📌 #{number}\n📂 {add_emoji(data['name'], data['cat'])}\n💰 {data['price']}💎", reply_markup=admin_panel_markup())
    uploading.pop(uid, None)

@bot.message_handler(func=lambda m: m.from_user.id in uploading and uploading[m.from_user.id].get("step") == "files")
def upload_files_process(m):
    uid = m.from_user.id
    
    if m.text == "/done":
        data = uploading[uid]
        if not data.get("files"):
            bot.send_message(uid, "❌ No files! Send at least one file.")
            return
        
        number = fs.add(
            cat=data["cat"],
            name=data["name"],
            files=data["files"],
            price=data["price"]
        )
        
        bot.send_message(uid, f"✅ **ADDED!**\n\n📌 #{number}\n📂 {add_emoji(data['name'], data['cat'])}\n💰 {data['price']}💎\n📁 {len(data['files'])} files", reply_markup=admin_panel_markup())
        uploading.pop(uid, None)
        return
    
    if m.text == "/cancel":
        uploading.pop(uid, None)
        bot.send_message(uid, "❌ Cancelled", reply_markup=admin_panel_markup())
        return
    
    if m.content_type in ["photo", "document", "video"]:
        data = uploading[uid]
        data["files"].append({
            "chat": m.chat.id,
            "msg": m.message_id,
            "type": m.content_type
        })
        bot.send_message(uid, f"✅ File {len(data['files'])} added")

def admin_panel_markup():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Add FREE", "💎 Add VIP", "📱 Add APP", "⚡ Add SERVICE", "❌ Exit")
    return kb

@bot.message_handler(func=lambda m: m.text == "/skip" or m.text == "/cancel")
def cancel_upload(m):
    if m.from_user.id in uploading:
        uploading.pop(m.from_user.id)
    bot.send_message(m.from_user.id, "Cancelled", reply_markup=admin_panel_markup())

# 📁 Add Subfolder
@bot.message_handler(func=lambda m: m.text == "📁 Add Subfolder" and is_admin(m.from_user.id))
def add_subfolder(m):
    msg = bot.send_message(m.from_user.id, "📁 **Add Subfolder**\n\nSend: `category parent_name sub_name price`\nExample: `free Tutorials Advanced 10`")
    bot.register_next_step_handler(msg, process_subfolder)

def process_subfolder(m):
    try:
        parts = m.text.split(maxsplit=3)
        cat, parent, name, price = parts[0].lower(), parts[1], parts[2], int(parts[3])
        
        if cat not in ["free", "vip", "apps", "services"]:
            bot.send_message(m.from_user.id, "❌ Invalid category!")
            return
        
        parent_folder = fs.get_one(cat, parent)
        if not parent_folder:
            bot.send_message(m.from_user.id, f"❌ Parent '{parent}' not found!")
            return
        
        number = fs.add(cat, name, [], price, parent)
        bot.send_message(m.from_user.id, f"✅ **SUBFOLDER ADDED!**\n\n📌 #{number}\n📂 {parent} → {name}\n💰 {price}💎", reply_markup=admin_panel_markup())
    except Exception as e:
        bot.send_message(m.from_user.id, f"❌ Error! Use: `category parent name price`")

# 🗑 Delete Folder
@bot.message_handler(func=lambda m: m.text == "🗑 Delete Folder" and is_admin(m.from_user.id))
def delete_folder(m):
    msg = bot.send_message(m.from_user.id, "🗑 **Delete Folder**\n\nSend: `category folder_name`\nExample: `free Test`")
    bot.register_next_step_handler(msg, process_delete)

def process_delete(m):
    try:
        parts = m.text.split(maxsplit=1)
        cat = parts[0].lower()
        name = parts[1].strip()
        
        if fs.delete(cat, name):
            bot.send_message(m.from_user.id, f"✅ Deleted: {cat} → {name}", reply_markup=admin_panel_markup())
        else:
            bot.send_message(m.from_user.id, f"❌ '{name}' not found!")
    except:
        bot.send_message(m.from_user.id, "❌ Use: `category name`")

# 💰 Give Points
@bot.message_handler(func=lambda m: m.text == "💰 Give Points" and is_admin(m.from_user.id))
def give_points_start(m):
    msg = bot.send_message(m.from_user.id, "💰 **Give Points**\n\nSend: `user_id points`\nExample: `123456789 100`")
    bot.register_next_step_handler(msg, process_give_points)

def process_give_points(m):
    try:
        uid, points = m.text.split()
        uid = int(uid)
        points = int(points)
        
        if points <= 0 or points > 100000:
            bot.send_message(m.from_user.id, "❌ Points must be between 1 and 100,000")
            return
        
        old_points = User.points(uid)
        new_points = User.add_points(uid, points)
        
        bot.send_message(m.from_user.id, f"✅ **GAVE {points}💎**\n\n👤 User: `{uid}`\n💰 Old: {old_points}💎\n💰 New: {new_points}💎")
        
        try:
            bot.send_message(uid, f"🎉 **You received {points} points!** 🎉\n\n💰 New balance: {new_points}💎")
        except:
            pass
    except:
        bot.send_message(m.from_user.id, "❌ Use: `user_id points`")

# 👑 Give VIP
@bot.message_handler(func=lambda m: m.text == "👑 Give VIP" and is_admin(m.from_user.id))
def give_vip_start(m):
    msg = bot.send_message(m.from_user.id, "👑 **Give VIP**\n\nSend user ID or @username:\nExample: `123456789` or `@username`")
    bot.register_next_step_handler(msg, process_give_vip)

def process_give_vip(m):
    inp = m.text.strip()
    if inp.startswith("@"):
        try:
            uid = bot.get_chat(inp).id
        except:
            bot.send_message(m.from_user.id, "❌ User not found!")
            return
    else:
        try:
            uid = int(inp)
        except:
            bot.send_message(m.from_user.id, "❌ Invalid ID!")
            return
    
    cfg = get_cached_config()
    user_data = User.get(uid)
    user_data["vip"] = True
    user_data["vip_expiry"] = time.time() + (cfg.get("vip_duration_days", 30) * 86400)
    User.save(uid, user_data)
    
    bot.send_message(m.from_user.id, f"✅ **VIP GIVEN**\n\n👤 User: `{uid}`")
    try:
        bot.send_message(uid, "👑 **You are now VIP!** 🎉")
    except:
        pass

# 🗑 Remove VIP
@bot.message_handler(func=lambda m: m.text == "🗑 Remove VIP" and is_admin(m.from_user.id))
def remove_vip_start(m):
    msg = bot.send_message(m.from_user.id, "🗑 **Remove VIP**\n\nSend user ID or @username:")
    bot.register_next_step_handler(msg, process_remove_vip)

def process_remove_vip(m):
    inp = m.text.strip()
    if inp.startswith("@"):
        try:
            uid = bot.get_chat(inp).id
        except:
            bot.send_message(m.from_user.id, "❌ User not found!")
            return
    else:
        try:
            uid = int(inp)
        except:
            bot.send_message(m.from_user.id, "❌ Invalid ID!")
            return
    
    user_data = User.get(uid)
    user_data["vip"] = False
    user_data["vip_expiry"] = None
    User.save(uid, user_data)
    
    bot.send_message(m.from_user.id, f"✅ **VIP REMOVED**\n\n👤 User: `{uid}`")
    try:
        bot.send_message(uid, "⚠️ Your VIP status has been removed.")
    except:
        pass

# 🎫 Generate Code
@bot.message_handler(func=lambda m: m.text == "🎫 Generate Code" and is_admin(m.from_user.id))
def gen_code_start(m):
    msg = bot.send_message(m.from_user.id, "🎫 **Generate Code**\n\nPoints amount:")
    bot.register_next_step_handler(msg, gen_code_points)

def gen_code_points(m):
    try:
        points = int(m.text)
        if points <= 0 or points > 100000:
            bot.send_message(m.from_user.id, "❌ Points: 1-100,000")
            return
        
        code = "ZEDOX" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        codes_col.insert_one({
            "_id": code,
            "points": points,
            "used_count": 0,
            "created_at": time.time()
        })
        
        bot.send_message(m.from_user.id, f"✅ **CODE GENERATED**\n\n`{code}`\n💰 {points} points", reply_markup=admin_panel_markup())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid number!")

# 📊 View Codes
@bot.message_handler(func=lambda m: m.text == "📊 View Codes" and is_admin(m.from_user.id))
def view_codes(m):
    codes = list(codes_col.find({}).sort("created_at", -1).limit(20))
    if not codes:
        bot.send_message(m.from_user.id, "📊 No codes!")
        return
    
    text = "📊 **RECENT CODES**\n\n"
    for c in codes:
        used = c.get("used_count", 0)
        text += f"• `{c['_id']}` - {c['points']}💎 (used: {used})\n"
    
    bot.send_message(m.from_user.id, text)

# 📢 Broadcast
@bot.message_handler(func=lambda m: m.text == "📢 Broadcast" and is_admin(m.from_user.id))
def broadcast_start(m):
    msg = bot.send_message(m.from_user.id, "📢 **Broadcast Message**\n\nSend the message to broadcast to all users:\n(HTML formatting supported)")
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(m):
    total = users_col.count_documents({})
    status_msg = bot.send_message(m.from_user.id, f"📤 Broadcasting to {total} users...")
    
    sent = 0
    failed = 0
    
    for user in users_col.find({}, {"_id": 1}):
        try:
            bot.send_message(int(user["_id"]), m.text, parse_mode="HTML")
            sent += 1
            if sent % 10 == 0:
                time.sleep(0.1)
        except:
            failed += 1
    
    bot.edit_message_text(f"✅ **BROADCAST COMPLETE**\n\n📤 Sent: {sent}\n❌ Failed: {failed}", m.from_user.id, status_msg.message_id)

# 🔔 Toggle Notify
@bot.message_handler(func=lambda m: m.text == "🔔 Toggle Notify" and is_admin(m.from_user.id))
def toggle_notify(m):
    cfg = get_cached_config()
    current = cfg.get("notify_new_methods", True)
    set_config("notify_new_methods", not current)
    
    status = "ON" if not current else "OFF"
    bot.send_message(m.from_user.id, f"🔔 New method notifications: **{status}**", reply_markup=admin_panel_markup())

# 📊 Stats
@bot.message_handler(func=lambda m: m.text == "📊 Stats" and is_admin(m.from_user.id))
def stats_cmd(m):
    total_users = users_col.count_documents({})
    vip_users = users_col.count_documents({"vip": True})
    total_points = sum(u.get("points", 0) for u in users_col.find({}))
    free_methods = folders_col.count_documents({"cat": "free"})
    vip_methods = folders_col.count_documents({"cat": "vip"})
    apps = folders_col.count_documents({"cat": "apps"})
    services = folders_col.count_documents({"cat": "services"})
    
    text = f"📊 **BOT STATISTICS**\n\n"
    text += f"👥 **USERS**\n"
    text += f"├ Total: {total_users}\n"
    text += f"├ VIP: {vip_users}\n"
    text += f"└ Free: {total_users - vip_users}\n\n"
    text += f"💰 **POINTS**\n"
    text += f"└ Total in circulation: {total_points:,}\n\n"
    text += f"📁 **CONTENT**\n"
    text += f"├ FREE: {free_methods}\n"
    text += f"├ VIP: {vip_methods}\n"
    text += f"├ APPS: {apps}\n"
    text += f"└ SERVICES: {services}\n\n"
    text += f"⚙️ **SETTINGS**\n"
    text += f"└ Notifications: {'ON' if get_cached_config().get('notify_new_methods', True) else 'OFF'}"
    
    bot.send_message(m.from_user.id, text, reply_markup=admin_panel_markup())

# ⚙️ Settings
@bot.message_handler(func=lambda m: m.text == "⚙️ Settings" and is_admin(m.from_user.id))
def settings_menu(m):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📝 Set Welcome", "💰 Set Ref Reward")
    kb.add("👑 Set VIP Price", "💎 Set VIP Points")
    kb.add("📞 Set Contact", "🔔 Notify Toggle")
    kb.add("❌ Back")
    bot.send_message(m.from_user.id, "⚙️ **SETTINGS**", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "📝 Set Welcome" and is_admin(m.from_user.id))
def set_welcome(m):
    msg = bot.send_message(m.from_user.id, "📝 **Set Welcome Message**\n\nSend new welcome message:")
    bot.register_next_step_handler(msg, lambda x: set_config("welcome", x.text) or bot.send_message(x.from_user.id, "✅ Welcome message updated!", reply_markup=admin_panel_markup()))

@bot.message_handler(func=lambda m: m.text == "💰 Set Ref Reward" and is_admin(m.from_user.id))
def set_ref_reward(m):
    msg = bot.send_message(m.from_user.id, "💰 **Set Referral Reward**\n\nCurrent: " + str(get_cached_config().get("ref_reward", 5)) + "\n\nSend new amount:")
    bot.register_next_step_handler(msg, lambda x: set_config("ref_reward", int(x.text)) if x.text.isdigit() else bot.send_message(x.from_user.id, "❌ Invalid!") or bot.send_message(m.from_user.id, f"✅ Set to {x.text} points!", reply_markup=admin_panel_markup()))

@bot.message_handler(func=lambda m: m.text == "👑 Set VIP Price" and is_admin(m.from_user.id))
def set_vip_price(m):
    msg = bot.send_message(m.from_user.id, "👑 **Set VIP USD Price**\n\nCurrent: $" + str(get_cached_config().get("vip_price", 50)) + "\n\nSend new price:")
    bot.register_next_step_handler(msg, lambda x: set_config("vip_price", int(x.text)) if x.text.isdigit() else bot.send_message(x.from_user.id, "❌ Invalid!") or bot.send_message(m.from_user.id, f"✅ Set to ${x.text}", reply_markup=admin_panel_markup()))

@bot.message_handler(func=lambda m: m.text == "💎 Set VIP Points" and is_admin(m.from_user.id))
def set_vip_points(m):
    msg = bot.send_message(m.from_user.id, "💎 **Set VIP Points Price**\n\nCurrent: " + str(get_cached_config().get("vip_points_price", 5000)) + " points\n\nSend new price:")
    bot.register_next_step_handler(msg, lambda x: set_config("vip_points_price", int(x.text)) if x.text.isdigit() else bot.send_message(x.from_user.id, "❌ Invalid!") or bot.send_message(m.from_user.id, f"✅ Set to {x.text} points", reply_markup=admin_panel_markup()))

@bot.message_handler(func=lambda m: m.text == "📞 Set Contact" and is_admin(m.from_user.id))
def set_contact(m):
    msg = bot.send_message(m.from_user.id, "📞 **Set Contact**\n\nSend @username or link:\nExample: `@admin` or `https://t.me/admin`\n\nSend 'none' to clear")
    bot.register_next_step_handler(msg, process_set_contact)

def process_set_contact(m):
    if m.text.lower() == "none":
        set_config("vip_contact", None)
        set_config("contact_username", None)
        set_config("contact_link", None)
        bot.send_message(m.from_user.id, "✅ Contact cleared!", reply_markup=admin_panel_markup())
    elif m.text.startswith("@"):
        set_config("vip_contact", m.text)
        bot.send_message(m.from_user.id, f"✅ Contact set to {m.text}", reply_markup=admin_panel_markup())
    elif m.text.startswith("http"):
        set_config("vip_contact", m.text)
        bot.send_message(m.from_user.id, f"✅ Contact set", reply_markup=admin_panel_markup())
    else:
        bot.send_message(m.from_user.id, "❌ Invalid format! Use @username or link")

# =========================
# 🏃 FALLBACK HANDLER
# =========================
@bot.message_handler(func=lambda m: True)
def fallback_handler(m):
    uid = m.from_user.id
    menu, points = main_menu(uid)
    bot.send_message(uid, f"❌ Unknown command\n\n💰 Balance: {points}💎", reply_markup=menu)

# =========================
# 🚀 RUN BOT
# =========================
def run_bot():
    while True:
        try:
            print("=" * 50)
            print("🚀 ZEDOX BOT - ULTRA FAST VERSION")
            print(f"✅ Bot: @{bot.get_me().username}")
            print(f"👑 Admin: {ADMIN_ID}")
            print(f"💾 MongoDB: Connected")
            print(f"⚡ Cache: ENABLED (TTL: 60s)")
            print(f"🔔 Notifications: {'ON' if get_cached_config().get('notify_new_methods', True) else 'OFF'}")
            print(f"📄 Page Numbers: ENABLED")
            print(f"🏷️ Auto-Emojis: ENABLED")
            print("=" * 50)
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_bot()
