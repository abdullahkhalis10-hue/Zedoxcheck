# =========================
# ZEDOX BOT - COMPLETE ULTRA FAST VERSION
# With All Features, Subfolders, Notifications, Caching, Page Numbers
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

client = MongoClient(MONGO_URI, maxPoolSize=100, minPoolSize=20, connectTimeoutMS=5000, socketTimeoutMS=5000)
db = client["zedox_complete_fast"]

# Collections
users_col = db["users"]
folders_col = db["folders"]
codes_col = db["codes"]
config_col = db["config"]
custom_buttons_col = db["custom_buttons"]
admins_col = db["admins"]
payments_col = db["payments"]
pending_payments_col = db["pending_payments"]

# Create indexes for speed
users_col.create_index("points")
users_col.create_index("vip")
users_col.create_index("referrals_count")
folders_col.create_index([("cat", 1), ("parent", 1)])
folders_col.create_index("number", unique=True, sparse=True)
codes_col.create_index("created_at")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# =========================
# 🚀 FAST CACHE SYSTEM
# =========================
user_cache = TTLCache(maxsize=2000, ttl=60)
folder_cache = TTLCache(maxsize=1000, ttl=120)
config_cache = TTLCache(maxsize=10, ttl=60)
admin_cache = TTLCache(maxsize=100, ttl=300)

# =========================
# 🔐 SECURITY
# =========================
def validate_request(message):
    if not message or not message.from_user:
        return False
    if len(message.text or "") > 4096:
        return False
    return True

def hash_user_data(uid):
    secret = os.environ.get("BOT_TOKEN", "secret_key")
    return hmac.new(secret.encode(), str(uid).encode(), hashlib.sha256).hexdigest()[:16]

# =========================
# ⚙️ CONFIG SYSTEM (CACHED)
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
            "vip_msg": "💎 Buy VIP to unlock premium content! 🚀",
            "welcome": "🔥 Welcome to ZEDOX BOT! Get premium methods, apps, and services! 🎉",
            "ref_reward": 5,
            "notify_new_methods": True,
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
            "require_screenshot": True,
            "admin_logs": True,
            "auto_delete_after": 0
        }
        config_col.insert_one(cfg)
    
    config_cache[key] = cfg
    return cfg

def set_config(key, value):
    config_col.update_one({"_id": "config"}, {"$set": {key: value}}, upsert=True)
    config_cache.pop("config", None)

# =========================
# 👑 MULTIPLE ADMINS SYSTEM
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
    
    cache_key = f"admin_{uid}"
    if cache_key in admin_cache:
        return admin_cache[cache_key]
    
    result = admins_col.find_one({"_id": uid}) is not None
    admin_cache[cache_key] = result
    return result

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
    admin_cache.pop(f"admin_{uid}", None)
    return True

def remove_admin(uid):
    uid = int(uid) if isinstance(uid, str) else uid
    if uid == ADMIN_ID:
        return False
    result = admins_col.delete_one({"_id": uid})
    admin_cache.pop(f"admin_{uid}", None)
    return result.deleted_count > 0

def get_all_admins():
    return list(admins_col.find({}))

# =========================
# 👤 USER SYSTEM (CACHED)
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
                "refs_who_bought_vip": 0,
                "purchased_methods": [],
                "used_codes": [],
                "username": None,
                "created_at": time.time(),
                "last_active": time.time(),
                "hash_id": hash_user_data(uid),
                "total_points_earned": 0,
                "total_points_spent": 0,
                "vip_start_date": None
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
    def purchased_methods(uid):
        return User.get(uid).get("purchased_methods", [])
    
    @staticmethod
    def used_codes(uid):
        return User.get(uid).get("used_codes", [])
    
    @staticmethod
    def add_points(uid, amount):
        if amount <= 0:
            return User.points(uid)
        data = User.get(uid)
        data["points"] = data.get("points", 0) + amount
        data["total_points_earned"] = data.get("total_points_earned", 0) + amount
        User.save(uid, data)
        return data["points"]
    
    @staticmethod
    def spend_points(uid, amount):
        if amount <= 0:
            return User.points(uid)
        data = User.get(uid)
        current = data.get("points", 0)
        if current < amount:
            return current
        data["points"] = current - amount
        data["total_points_spent"] = data.get("total_points_spent", 0) + amount
        User.save(uid, data)
        return data["points"]
    
    @staticmethod
    def make_vip(uid, duration_days=None):
        data = User.get(uid)
        data["vip"] = True
        if duration_days and duration_days > 0:
            data["vip_expiry"] = time.time() + (duration_days * 86400)
            data["vip_start_date"] = time.time()
        else:
            data["vip_expiry"] = None
        User.save(uid, data)
    
    @staticmethod
    def remove_vip(uid):
        data = User.get(uid)
        data["vip"] = False
        data["vip_expiry"] = None
        data["vip_start_date"] = None
        User.save(uid, data)
    
    @staticmethod
    def purchase_method(uid, method_name, price):
        if User.points(uid) >= price:
            User.spend_points(uid, price)
            data = User.get(uid)
            purchased = data.get("purchased_methods", [])
            if method_name not in purchased:
                purchased.append(method_name)
                data["purchased_methods"] = purchased
                User.save(uid, data)
            return True
        return False
    
    @staticmethod
    def can_access_method(uid, method_name):
        return User.is_vip(uid) or method_name in User.purchased_methods(uid)
    
    @staticmethod
    def add_used_code(uid, code):
        data = User.get(uid)
        used = data.get("used_codes", [])
        if code not in used:
            used.append(code)
            data["used_codes"] = used
            User.save(uid, data)
            return True
        return False
    
    @staticmethod
    def add_referral(uid):
        data = User.get(uid)
        data["refs"] = data.get("refs", 0) + 1
        User.save(uid, data)
        
        cfg = get_cached_config()
        required_refs = cfg.get("referral_vip_count", 50)
        
        if data["refs"] >= required_refs and not User.is_vip(uid):
            User.make_vip(uid, cfg.get("vip_duration_days", 30))
            return True
        return False
    
    @staticmethod
    def add_referral_purchase(uid):
        data = User.get(uid)
        data["refs_who_bought_vip"] = data.get("refs_who_bought_vip", 0) + 1
        User.save(uid, data)
        
        cfg = get_cached_config()
        required = cfg.get("referral_purchase_count", 10)
        
        if data["refs_who_bought_vip"] >= required and not User.is_vip(uid):
            User.make_vip(uid, cfg.get("vip_duration_days", 30))
            return True
        return False

# =========================
# 📁 FOLDER SYSTEM (FULLY WORKING SUBFOLDERS)
# =========================
class FolderSystem:
    @staticmethod
    def add(cat, name, files, price, parent=None, number=None, text_content=None):
        if number is None:
            cfg = get_cached_config()
            number = cfg.get("next_folder_number", 1)
            set_config("next_folder_number", number + 1)
        
        folder_data = {
            "cat": cat,
            "name": name,
            "files": files,
            "price": price,
            "parent": parent,
            "number": number,
            "created_at": time.time()
        }
        
        if text_content:
            folder_data["text_content"] = text_content
        
        folders_col.insert_one(folder_data)
        
        # Send notification
        cfg = get_cached_config()
        if cfg.get("notify_new_methods", True):
            threading.Thread(target=FolderSystem._notify_users, args=(cat, name, number)).start()
        
        # Clear cache
        FolderSystem.clear_cache()
        return number
    
    @staticmethod
    def _notify_users(cat, name, number):
        cfg = get_cached_config()
        if not cfg.get("notify_new_methods", True):
            return
        
        cat_emoji = {"free": "📂", "vip": "💎", "apps": "📱", "services": "⚡"}
        message = f"🎉 <b>NEW METHOD ADDED!</b> 🎉\n\n"
        message += f"{cat_emoji.get(cat, '📌')} <b>Category:</b> {cat.upper()}\n"
        message += f"📌 <b>#{number}</b> {name}\n\n"
        message += f"✨ Check it out in the menu!"
        
        for user in users_col.find({}, {"_id": 1}):
            try:
                bot.send_message(int(user["_id"]), message)
                time.sleep(0.05)
            except:
                pass
    
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
        else:
            query["parent"] = {"$in": [None, ""]}
        return folders_col.find_one(query)
    
    @staticmethod
    def get_by_number(number):
        return folders_col.find_one({"number": number})
    
    @staticmethod
    def delete_all_subfolders(cat, parent_name):
        subfolders = list(folders_col.find({"cat": cat, "parent": parent_name}))
        for sub in subfolders:
            FolderSystem.delete_all_subfolders(cat, sub["name"])
            folders_col.delete_one({"_id": sub["_id"]})
    
    @staticmethod
    def delete(cat, name, parent=None):
        query = {"cat": cat, "name": name}
        if parent:
            query["parent"] = parent
        else:
            query["parent"] = {"$in": [None, ""]}
        
        folder = folders_col.find_one(query)
        if not folder:
            return False
        
        number = folder.get("number")
        FolderSystem.delete_all_subfolders(cat, name)
        folders_col.delete_one(query)
        
        if number:
            folders_col.update_many(
                {"number": {"$gt": number}},
                {"$inc": {"number": -1}}
            )
        
        FolderSystem.clear_cache()
        return True
    
    @staticmethod
    def edit_price(cat, name, price, parent=None):
        query = {"cat": cat, "name": name}
        if parent:
            query["parent"] = parent
        folders_col.update_one(query, {"$set": {"price": price}})
        FolderSystem.clear_cache()
    
    @staticmethod
    def edit_name(cat, old_name, new_name, parent=None):
        query = {"cat": cat, "name": old_name}
        if parent:
            query["parent"] = parent
        folders_col.update_one(query, {"$set": {"name": new_name}})
        folders_col.update_many({"cat": cat, "parent": old_name}, {"$set": {"parent": new_name}})
        FolderSystem.clear_cache()
    
    @staticmethod
    def move_folder(number, new_parent):
        folders_col.update_one({"number": number}, {"$set": {"parent": new_parent}})
        FolderSystem.clear_cache()
    
    @staticmethod
    def edit_content(cat, name, content_type, content, parent=None):
        query = {"cat": cat, "name": name}
        if parent:
            query["parent"] = parent
        
        if content_type == "text":
            folders_col.update_one(query, {"$set": {"text_content": content}})
        elif content_type == "files":
            folders_col.update_one(query, {"$set": {"files": content}})
        
        FolderSystem.clear_cache()
        return True
    
    @staticmethod
    def clear_cache():
        folder_cache.clear()

fs = FolderSystem()

# =========================
# 🏆 CODES SYSTEM
# =========================
class CodeSystem:
    @staticmethod
    def generate(points, count, multi_use=False, expiry_days=None):
        codes = []
        expiry = time.time() + (expiry_days * 86400) if expiry_days else None
        
        for _ in range(count):
            code = "ZEDOX" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            while codes_col.find_one({"_id": code}):
                code = "ZEDOX" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            
            codes_col.insert_one({
                "_id": code,
                "points": points,
                "used": False,
                "multi_use": multi_use,
                "used_count": 0,
                "max_uses": 100 if multi_use else 1,
                "expiry": expiry,
                "created_at": time.time(),
                "used_by_users": []
            })
            codes.append(code)
        return codes
    
    @staticmethod
    def redeem(code, uid):
        code_data = codes_col.find_one({"_id": code})
        
        if not code_data:
            return False, 0, "invalid"
        
        if code_data.get("expiry") and time.time() > code_data["expiry"]:
            return False, 0, "expired"
        
        user_data = User.get(uid)
        
        if code in user_data.get("used_codes", []):
            return False, 0, "already_used_by_user"
        
        if not code_data.get("multi_use", False) and code_data.get("used", False):
            return False, 0, "already_used"
        
        if code_data.get("multi_use", False):
            used_count = code_data.get("used_count", 0)
            max_uses = code_data.get("max_uses", 100)
            if used_count >= max_uses:
                return False, 0, "max_uses_reached"
        
        points = code_data["points"]
        User.add_points(uid, points)
        
        update_data = {
            "$push": {"used_by_users": uid},
            "$inc": {"used_count": 1}
        }
        
        if not code_data.get("multi_use", False):
            update_data["$set"] = {"used": True}
        
        codes_col.update_one({"_id": code}, update_data)
        User.add_used_code(uid, code)
        
        return True, points, "success"
    
    @staticmethod
    def get_all():
        return list(codes_col.find({}).sort("created_at", -1))
    
    @staticmethod
    def get_stats():
        total = codes_col.count_documents({})
        used = codes_col.count_documents({"used": True})
        multi = codes_col.count_documents({"multi_use": True})
        return total, used, total - used, multi

codes = CodeSystem()

# =========================
# 🏷️ AUTO EMOJI SYSTEM
# =========================
def add_auto_emoji(name, cat=None):
    """Auto-add emojis based on name keywords"""
    emoji_map = {
        "premium": "💎", "vip": "👑", "pro": "⭐", "advanced": "🚀",
        "free": "🆓", "basic": "📌", "starter": "🌱",
        "app": "📱", "apps": "📱", "android": "🤖", "ios": "🍎", "mobile": "📲",
        "service": "⚡", "services": "⚡", "api": "🔌", "tool": "🛠️",
        "method": "🔧", "tutorial": "📚", "guide": "📖", "course": "🎓",
        "hack": "🎮", "cheat": "🎯", "mod": "🔧", "crack": "🔓",
        "key": "🔑", "license": "📜", "code": "💻",
        "account": "👤", "profile": "👥",
        "card": "💳", "bank": "🏦", "crypto": "🪙", "bitcoin": "₿", "usdt": "💵",
        "social": "📱", "instagram": "📸", "facebook": "📘", "twitter": "🐦", "tiktok": "🎵",
        "video": "🎥", "movie": "🍿", "series": "📺", "music": "🎵",
        "game": "🎮", "gaming": "🕹️", "pc": "💻", "console": "🎮"
    }
    
    name_lower = name.lower()
    for keyword, emoji in emoji_map.items():
        if keyword in name_lower:
            return f"{emoji} {name}"
    
    # Category fallback
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
# 📄 FORMATTING HELPERS
# =========================
def format_folder_button(folder, cat):
    """Format folder button with number, emoji, and price"""
    name = folder["name"]
    price = folder.get("price", 0)
    number = folder.get("number", "?")
    
    # Check for subfolders
    subfolders = fs.get(cat, name)
    icon = "📁" if subfolders else "📄"
    
    display_name = add_auto_emoji(name, cat)
    
    text = f"{icon} [{number}] {display_name}"
    if price > 0 and not subfolders:
        text += f" ─ {price}💎"
    
    return text

def get_folders_keyboard(cat, parent=None, page=0, items_per_page=10):
    """Get keyboard with page numbers"""
    data = fs.get(cat, parent)
    total_items = len(data)
    
    if total_items == 0:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("📂 Empty", callback_data="noop"))
        return kb
    
    total_pages = (total_items + items_per_page - 1) // items_per_page
    page = max(0, min(page, total_pages - 1))
    
    start = page * items_per_page
    end = min(start + items_per_page, total_items)
    page_items = data[start:end]
    
    kb = InlineKeyboardMarkup(row_width=2)
    
    for item in page_items:
        text = format_folder_button(item, cat)
        callback = f"open|{cat}|{item['name']}|{parent or ''}"
        kb.add(InlineKeyboardButton(text, callback_data=callback))
    
    # Navigation row
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"page|{cat}|{page-1}|{parent or ''}"))
    
    nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="noop"))
    
    if end < total_items:
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"page|{cat}|{page+1}|{parent or ''}"))
    
    if nav_buttons:
        kb.row(*nav_buttons)
    
    # Back button
    if parent:
        kb.add(InlineKeyboardButton("🔙 BACK", callback_data=f"back|{cat}|{parent}"))
    else:
        kb.add(InlineKeyboardButton("🏠 MAIN MENU", callback_data="main_menu"))
    
    return kb

# =========================
# 🚫 FORCE JOIN (CACHED)
# =========================
force_cache = TTLCache(maxsize=500, ttl=30)

def check_force_join(uid):
    """Check if user needs to join channels"""
    if is_admin(uid):
        return False
    
    cache_key = f"force_{uid}"
    if cache_key in force_cache:
        return force_cache[cache_key]
    
    cfg = get_cached_config()
    channels = cfg.get("force_channels", [])
    
    if not channels:
        force_cache[cache_key] = False
        return False
    
    for channel in channels:
        try:
            member = bot.get_chat_member(channel, uid)
            if member.status in ["left", "kicked"]:
                force_cache[cache_key] = True
                return True
        except:
            force_cache[cache_key] = True
            return True
    
    force_cache[cache_key] = False
    return False

def send_force_join_message(uid):
    """Send force join message"""
    cfg = get_cached_config()
    channels = cfg.get("force_channels", [])
    
    kb = InlineKeyboardMarkup(row_width=1)
    for channel in channels:
        clean = channel.replace("@", "")
        kb.add(InlineKeyboardButton(f"📢 Join {channel}", url=f"https://t.me/{clean}"))
    kb.add(InlineKeyboardButton("✅ I Joined", callback_data="check_force"))
    
    bot.send_message(uid, "🚫 <b>ACCESS RESTRICTED</b> 🚫\n\nPlease join the required channels to use this bot:", reply_markup=kb)

def force_join_decorator(func):
    @wraps(func)
    def wrapper(message):
        uid = message.from_user.id
        if check_force_join(uid):
            send_force_join_message(uid)
            return
        return func(message)
    return wrapper

# =========================
# 🏠 MAIN MENU
# =========================
def get_custom_buttons():
    cfg = get_cached_config()
    return cfg.get("custom_buttons", [])

def get_main_menu(uid):
    """Get main menu keyboard"""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Main categories
    kb.add("📂 FREE METHODS", "💎 VIP METHODS")
    kb.add("📱 PREMIUM APPS", "⚡ SERVICES")
    
    # Points and VIP
    kb.add("💰 MY WALLET", "⭐ BUY VIP")
    
    # User features
    kb.add("🎁 REFERRAL", "👤 PROFILE")
    kb.add("🏆 MY PURCHASES", "🎫 REDEEM CODE")
    kb.add("🆔 MY ID", "📊 LEADERBOARD")
    
    # Custom buttons
    custom_btns = get_custom_buttons()
    if custom_btns:
        row = []
        for btn in custom_btns:
            row.append(btn["text"])
            if len(row) == 2:
                kb.add(*row)
                row = []
        if row:
            kb.add(*row)
    
    # Admin panel
    if is_admin(uid):
        kb.add("⚙️ ADMIN PANEL")
    
    return kb

# =========================
# 🚀 START COMMAND
# =========================
@bot.message_handler(commands=["start"])
def start_command(message):
    if not validate_request(message):
        return
    
    uid = message.from_user.id
    chat_id = message.chat.id
    args = message.text.split()
    
    # Update username
    if message.from_user.username:
        user_data = User.get(uid)
        if user_data.get("username") != message.from_user.username:
            user_data["username"] = message.from_user.username
            User.save(uid, user_data)
    
    # Handle referral
    if len(args) > 1:
        ref_id = args[1]
        if ref_id != str(uid) and ref_id.isdigit():
            user_data = User.get(uid)
            if not user_data.get("ref"):
                ref_user = User.get(ref_id)
                if ref_user:
                    cfg = get_cached_config()
                    reward = cfg.get("ref_reward", 5)
                    
                    User.add_points(ref_id, reward)
                    got_vip = User.add_referral(ref_id)
                    
                    user_data["ref"] = ref_id
                    User.save(uid, user_data)
                    
                    # Notify referrer
                    try:
                        vip_msg = "\n\n🎉 <b>YOU GOT FREE VIP!</b> 🎉" if got_vip else ""
                        bot.send_message(int(ref_id), 
                            f"👤 <b>New Referral!</b>\n\n"
                            f"✨ @{message.from_user.username or uid} joined!\n"
                            f"💰 You earned +{reward} points!\n"
                            f"📊 Total referrals: {ref_user.get('refs', 0)}{vip_msg}")
                    except:
                        pass
    
    # Check force join
    if check_force_join(uid):
        send_force_join_message(uid)
        return
    
    # Send welcome
    cfg = get_cached_config()
    welcome = cfg.get("welcome", "🔥 Welcome to ZEDOX BOT!")
    points = User.points(uid)
    
    bot.send_message(chat_id, 
        f"{welcome}\n\n"
        f"💰 <b>Your Balance:</b> {points} 💎\n"
        f"👑 <b>VIP Status:</b> {'✅ Active' if User.is_vip(uid) else '❌ Not Active'}\n\n"
        f"Use the buttons below to get started! 🚀",
        reply_markup=get_main_menu(uid))

# =========================
# 💰 MY WALLET
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 MY WALLET")
@force_join_decorator
def my_wallet(message):
    uid = message.from_user.id
    user = User.get(uid)
    
    wallet_text = f"┌─<b>💰 YOUR WALLET</b>─┐\n\n"
    wallet_text += f"├ 💎 <b>Points:</b> <code>{user.get('points', 0):,}</code>\n"
    wallet_text += f"├ 👑 <b>VIP:</b> <code>{'Active' if User.is_vip(uid) else 'Not Active'}</code>\n"
    wallet_text += f"├ 📊 <b>Referrals:</b> <code>{user.get('refs', 0)}</code>\n"
    wallet_text += f"├ 🎯 <b>Referral Purchases:</b> <code>{user.get('refs_who_bought_vip', 0)}</code>\n"
    wallet_text += f"├ 📈 <b>Total Earned:</b> <code>{user.get('total_points_earned', 0):,}</code>\n"
    wallet_text += f"└ 📉 <b>Total Spent:</b> <code>{user.get('total_points_spent', 0):,}</code>\n\n"
    
    wallet_text += f"✨ <b>WAYS TO EARN:</b>\n"
    wallet_text += f"• 🎁 Referral program\n"
    wallet_text += f"• 🎫 Redeem codes\n"
    wallet_text += f"• 💎 Purchase points"
    
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("💎 GET POINTS", callback_data="get_points"),
        InlineKeyboardButton("🎁 REFERRAL LINK", callback_data="get_referral")
    )
    
    bot.send_message(uid, wallet_text, reply_markup=kb)

# =========================
# 👤 PROFILE
# =========================
@bot.message_handler(func=lambda m: m.text == "👤 PROFILE")
@force_join_decorator
def profile_command(message):
    uid = message.from_user.id
    user = User.get(uid)
    
    status = "💎 VIP" if User.is_vip(uid) else "🆓 FREE"
    purchased = len(user.get("purchased_methods", []))
    created = datetime.fromtimestamp(user.get("created_at", time.time())).strftime("%Y-%m-%d")
    
    profile_text = f"┌─<b>👤 USER PROFILE</b>─┐\n\n"
    profile_text += f"├ 🆔 <b>ID:</b> <code>{uid}</code>\n"
    profile_text += f"├ 📛 <b>Name:</b> {message.from_user.first_name}\n"
    profile_text += f"├ 🎭 <b>Status:</b> {status}\n"
    profile_text += f"├ 💎 <b>Points:</b> <code>{user.get('points', 0):,}</code>\n"
    profile_text += f"├ 📚 <b>Purchased:</b> <code>{purchased}</code> methods\n"
    profile_text += f"├ 👥 <b>Referrals:</b> <code>{user.get('refs', 0)}</code>\n"
    profile_text += f"├ 🎯 <b>VIP Referrals:</b> <code>{user.get('refs_who_bought_vip', 0)}</code>\n"
    profile_text += f"└ 📅 <b>Joined:</b> {created}"
    
    bot.send_message(uid, profile_text)

# =========================
# 🏆 MY PURCHASES
# =========================
@bot.message_handler(func=lambda m: m.text == "🏆 MY PURCHASES")
@force_join_decorator
def my_purchases(message):
    uid = message.from_user.id
    
    if User.is_vip(uid):
        bot.send_message(uid, "👑 <b>VIP MEMBER</b> 👑\n\nYou have access to <b>ALL</b> VIP methods!")
        return
    
    purchased = User.purchased_methods(uid)
    if not purchased:
        bot.send_message(uid, "📚 <b>No Purchased Methods</b>\n\nUse your points to buy methods from 💎 VIP METHODS!")
        return
    
    text = f"📚 <b>YOUR PURCHASES</b> ({len(purchased)})\n\n"
    for i, method in enumerate(purchased, 1):
        text += f"{i}. {add_auto_emoji(method, 'vip')}\n"
    
    bot.send_message(uid, text)

# =========================
# 🎫 REDEEM CODE
# =========================
@bot.message_handler(func=lambda m: m.text == "🎫 REDEEM CODE")
@force_join_decorator
def redeem_command(message):
    msg = bot.send_message(message.from_user.id, "🎫 <b>Enter your redemption code:</b>\n\nExample: <code>ZEDOXABC123</code>")
    bot.register_next_step_handler(msg, process_redeem)

def process_redeem(message):
    uid = message.from_user.id
    code = message.text.strip().upper()
    
    success, points, reason = codes.redeem(code, uid)
    
    if success:
        new_balance = User.points(uid)
        bot.send_message(uid, 
            f"✅ <b>CODE REDEEMED SUCCESSFULLY!</b> ✅\n\n"
            f"➕ +{points} 💎\n"
            f"💰 New Balance: <code>{new_balance:,}</code> 💎")
    else:
        error_messages = {
            "invalid": "❌ <b>Invalid code!</b>\n\nPlease check and try again.",
            "expired": "⏰ <b>Code expired!</b>\n\nThis code is no longer valid.",
            "already_used": "❌ <b>Code already used!</b>\n\nThis code has been redeemed already.",
            "already_used_by_user": "❌ <b>You already used this code!</b>\n\nEach code can only be used once per user.",
            "max_uses_reached": "❌ <b>Max uses reached!</b>\n\nThis code has been used too many times."
        }
        bot.send_message(uid, error_messages.get(reason, "❌ Invalid code!"))

# =========================
# 🎁 REFERRAL
# =========================
@bot.message_handler(func=lambda m: m.text == "🎁 REFERRAL")
@force_join_decorator
def referral_command(message):
    uid = message.from_user.id
    user = User.get(uid)
    cfg = get_cached_config()
    
    link = f"https://t.me/{bot.get_me().username}?start={uid}"
    refs = user.get("refs", 0)
    reward = cfg.get("ref_reward", 5)
    
    text = f"┌─<b>🎁 REFERRAL PROGRAM</b>─┐\n\n"
    text += f"├ 🔗 <b>Your Link:</b>\n├ <code>{link}</code>\n\n"
    text += f"├ 📊 <b>Your Stats:</b>\n"
    text += f"├ 👥 Referrals: <code>{refs}</code>\n"
    text += f"├ 💰 Points Earned: <code>{refs * reward:,}</code>\n"
    text += f"└ 🎯 Progress: <code>{refs}/{cfg.get('referral_vip_count', 50)}</code>\n\n"
    text += f"✨ <b>REWARDS:</b>\n"
    text += f"• +{reward}💎 per referral\n"
    text += f"• {cfg.get('referral_vip_count', 50)} referrals → <b>FREE VIP</b> 👑\n"
    text += f"• {cfg.get('referral_purchase_count', 10)} referral purchases → <b>FREE VIP</b> 👑"
    
    bot.send_message(uid, text)

# =========================
# 🆔 MY ID
# =========================
@bot.message_handler(func=lambda m: m.text == "🆔 MY ID")
@force_join_decorator
def my_id_command(message):
    uid = message.from_user.id
    user = User.get(uid)
    
    text = f"🆔 <b>YOUR INFORMATION</b> 🆔\n\n"
    text += f"┌ <b>User ID:</b> <code>{uid}</code>\n"
    text += f"├ <b>Points:</b> <code>{user.get('points', 0):,}</code> 💎\n"
    text += f"├ <b>VIP:</b> <code>{'Yes' if User.is_vip(uid) else 'No'}</code>\n"
    text += f"├ <b>Referrals:</b> <code>{user.get('refs', 0)}</code>\n"
    text += f"└ <b>Hash ID:</b> <code>{user.get('hash_id', 'N/A')}</code>"
    
    bot.send_message(uid, text)

# =========================
# 📊 LEADERBOARD
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 LEADERBOARD")
@force_join_decorator
def leaderboard_command(message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🏆 TOP POINTS", callback_data="top_points"),
        InlineKeyboardButton("👥 TOP REFERRALS", callback_data="top_refs"),
        InlineKeyboardButton("⭐ TOP EARNERS", callback_data="top_earners")
    )
    bot.send_message(message.from_user.id, "📊 <b>LEADERBOARD</b>\n\nSelect category:", reply_markup=kb)

# =========================
# ⭐ BUY VIP
# =========================
@bot.message_handler(func=lambda m: m.text == "⭐ BUY VIP")
@force_join_decorator
def buy_vip_command(message):
    uid = message.from_user.id
    cfg = get_cached_config()
    
    if User.is_vip(uid):
        bot.send_message(uid, "👑 <b>You are already a VIP member!</b> 👑")
        return
    
    vip_price_usd = cfg.get("vip_price", 50)
    vip_price_points = cfg.get("vip_points_price", 5000)
    vip_contact = cfg.get("vip_contact")
    binance_address = cfg.get("binance_address", "")
    binance_coin = cfg.get("binance_coin", "USDT")
    binance_network = cfg.get("binance_network", "TRC20")
    
    text = f"┌─<b>👑 VIP MEMBERSHIP</b>─┐\n\n"
    text += f"├ {cfg.get('vip_msg', '💎 Buy VIP for premium access!')}\n\n"
    text += f"├ 💰 <b>PRICES:</b>\n"
    text += f"├   • ${vip_price_usd} USD\n"
    text += f"└   • {vip_price_points:,} 💎 points\n\n"
    text += f"✨ <b>BENEFITS:</b>\n"
    text += f"• Access to ALL VIP methods\n"
    text += f"• Priority support\n"
    text += f"• No points needed\n"
    text += f"• Exclusive content\n\n"
    
    if binance_address:
        text += f"💳 <b>Binance Payment:</b>\n"
        text += f"├ Coin: {binance_coin}\n"
        text += f"├ Network: {binance_network}\n"
        text += f"├ Address: <code>{binance_address}</code>\n"
        text += f"└ Amount: ${vip_price_usd}\n\n"
    
    text += f"💡 <b>Free VIP:</b>\n"
    text += f"• Invite {cfg.get('referral_vip_count', 50)} users\n"
    text += f"• Get {cfg.get('referral_purchase_count', 10)} referrals to buy VIP"
    
    kb = InlineKeyboardMarkup(row_width=2)
    if User.points(uid) >= vip_price_points:
        kb.add(InlineKeyboardButton(f"👑 BUY WITH {vip_price_points:,}💎", callback_data="buy_vip_points"))
    if vip_contact:
        if vip_contact.startswith("http"):
            kb.add(InlineKeyboardButton("📞 CONTACT", url=vip_contact))
        elif vip_contact.startswith("@"):
            kb.add(InlineKeyboardButton("📞 CONTACT", url=f"https://t.me/{vip_contact.replace('@', '')}"))
    
    bot.send_message(uid, text, reply_markup=kb if kb.keyboard else None)

# =========================
# 📂 CATEGORY HANDLERS
# =========================
@bot.message_handler(func=lambda m: m.text in ["📂 FREE METHODS", "💎 VIP METHODS", "📱 PREMIUM APPS", "⚡ SERVICES"])
@force_join_decorator
def show_category(message):
    cat_map = {
        "📂 FREE METHODS": "free",
        "💎 VIP METHODS": "vip",
        "📱 PREMIUM APPS": "apps",
        "⚡ SERVICES": "services"
    }
    
    cat = cat_map.get(message.text)
    items = fs.get(cat)
    
    if not items:
        bot.send_message(message.from_user.id, f"📂 {message.text}\n\nNo content available yet!")
        return
    
    kb = get_folders_keyboard(cat)
    bot.send_message(message.from_user.id, f"📂 <b>{message.text}</b>\n\nSelect an option:", reply_markup=kb)

# =========================
# 📂 OPEN FOLDER (WITH SUBFOLDERS)
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("open|"))
def open_folder_callback(call):
    uid = call.from_user.id
    
    if check_force_join(uid):
        send_force_join_message(uid)
        bot.answer_callback_query(call.id)
        return
    
    parts = call.data.split("|")
    cat = parts[1]
    name = parts[2]
    parent = parts[3] if len(parts) > 3 and parts[3] else None
    
    folder = fs.get_one(cat, name, parent if parent else None)
    if not folder:
        bot.answer_callback_query(call.id, "❌ Folder not found!")
        return
    
    # Check for subfolders
    subfolders = fs.get(cat, name)
    if subfolders:
        kb = InlineKeyboardMarkup(row_width=1)
        for sub in subfolders:
            text = format_folder_button(sub, cat)
            kb.add(InlineKeyboardButton(text, callback_data=f"open|{cat}|{sub['name']}|{name}"))
        kb.add(InlineKeyboardButton("🔙 BACK", callback_data=f"back|{cat}|{parent or ''}"))
        
        bot.edit_message_text(f"📁 <b>{add_auto_emoji(name, cat)}</b>", uid, call.message.message_id, reply_markup=kb)
        bot.answer_callback_query(call.id)
        return
    
    # Check access
    price = folder.get("price", 0)
    is_vip_cat = cat == "vip"
    user_is_vip = User.is_vip(uid)
    user_owns = name in User.purchased_methods(uid)
    
    if is_vip_cat and not user_is_vip and not user_owns:
        if price > 0:
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton(f"💰 BUY ({price}💎)", callback_data=f"buy|{cat}|{name}|{price}"),
                InlineKeyboardButton("👑 GET VIP", callback_data="get_vip_info")
            )
            kb.add(InlineKeyboardButton("❌ CANCEL", callback_data="cancel_buy"))
            bot.edit_message_text(
                f"🔒 <b>{add_auto_emoji(name, cat)}</b>\n\n"
                f"Price: {price} 💎\n"
                f"Your balance: {User.points(uid)} 💎",
                uid, call.message.message_id, reply_markup=kb)
        else:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("👑 GET VIP", callback_data="get_vip_info"))
            bot.edit_message_text(f"🔒 <b>{add_auto_emoji(name, cat)}</b>\n\nVIP only!", uid, call.message.message_id, reply_markup=kb)
        
        bot.answer_callback_query(call.id)
        return
    
    # Deduct points if needed
    if price > 0 and not user_is_vip and not user_owns:
        if User.points(uid) < price:
            bot.answer_callback_query(call.id, f"❌ Need {price}💎! You have {User.points(uid)}", True)
            return
        User.spend_points(uid, price)
    
    # Mark as purchased if VIP method
    if is_vip_cat and not user_is_vip:
        User.purchase_method(uid, name, 0)
    
    # Send content
    text_content = folder.get("text_content")
    files = folder.get("files", [])
    
    if text_content:
        bot.edit_message_text(f"📄 <b>{add_auto_emoji(name, cat)}</b>\n\n{text_content}", uid, call.message.message_id)
    elif files:
        bot.answer_callback_query(call.id, "📤 Sending files...")
        for f in files[:10]:
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
        bot.send_message(uid, f"✅ <b>{name}</b> sent!")
    else:
        bot.edit_message_text(f"📁 <b>{add_auto_emoji(name, cat)}</b>\n\nNo content available.", uid, call.message.message_id)
    
    bot.answer_callback_query(call.id)

# =========================
# 💰 BUY METHOD
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy|"))
def buy_method_callback(call):
    uid = call.from_user.id
    _, cat, name, price = call.data.split("|")
    price = int(price)
    
    if User.is_vip(uid):
        bot.answer_callback_query(call.id, "✅ You're VIP! Access free!", True)
        open_folder_callback(call)
        return
    
    if name in User.purchased_methods(uid):
        bot.answer_callback_query(call.id, "✅ You already own this!", True)
        open_folder_callback(call)
        return
    
    if User.points(uid) < price:
        bot.answer_callback_query(call.id, f"❌ Need {price}💎! Balance: {User.points(uid)}", True)
        return
    
    if User.purchase_method(uid, name, price):
        bot.answer_callback_query(call.id, f"✅ Purchased! -{price}💎", True)
        bot.edit_message_text(
            f"✅ <b>PURCHASED!</b> ✅\n\n"
            f"You now own: {add_auto_emoji(name, cat)}\n"
            f"Remaining: {User.points(uid)} 💎",
            uid, call.message.message_id)
        
        # Auto-open the method
        time.sleep(0.5)
        open_folder_callback(call)
    else:
        bot.answer_callback_query(call.id, "❌ Failed!", True)

# =========================
# 🎁 REFERRAL LINK
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "get_referral")
def get_referral_callback(call):
    uid = call.from_user.id
    link = f"https://t.me/{bot.get_me().username}?start={uid}"
    cfg = get_cached_config()
    
    text = f"🎁 <b>YOUR REFERRAL LINK</b> 🎁\n\n"
    text += f"<code>{link}</code>\n\n"
    text += f"✨ <b>Rewards:</b>\n"
    text += f"• +{cfg.get('ref_reward', 5)}💎 per referral\n"
    text += f"• {cfg.get('referral_vip_count', 50)} referrals → FREE VIP\n"
    text += f"• {cfg.get('referral_purchase_count', 10)} referral purchases → FREE VIP"
    
    bot.edit_message_text(text, uid, call.message.message_id)
    bot.answer_callback_query(call.id)

# =========================
# 💎 GET POINTS
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "get_points")
def get_points_callback(call):
    uid = call.from_user.id
    cfg = get_cached_config()
    
    text = f"💎 <b>GET POINTS</b> 💎\n\n"
    text += f"💰 Your balance: <code>{User.points(uid):,}</code> 💎\n\n"
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
    if cfg.get("vip_contact"):
        contact = cfg.get("vip_contact")
        if contact.startswith("http"):
            kb.add(InlineKeyboardButton("📞 CONTACT ADMIN", url=contact))
        elif contact.startswith("@"):
            kb.add(InlineKeyboardButton("📞 CONTACT ADMIN", url=f"https://t.me/{contact.replace('@', '')}"))
    
    bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb if kb.keyboard else None)
    bot.answer_callback_query(call.id)

# =========================
# 👑 GET VIP INFO
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "get_vip_info")
def get_vip_info_callback(call):
    uid = call.from_user.id
    cfg = get_cached_config()
    
    text = f"👑 <b>VIP INFORMATION</b> 👑\n\n"
    text += f"✨ <b>Benefits:</b>\n"
    text += f"• All VIP methods unlocked\n"
    text += f"• No points needed\n"
    text += f"• Priority support\n"
    text += f"• Exclusive content\n\n"
    text += f"💰 <b>Price:</b> ${cfg.get('vip_price', 50)} or {cfg.get('vip_points_price', 5000):,}💎\n\n"
    text += f"🎁 <b>Free VIP:</b>\n"
    text += f"• Invite {cfg.get('referral_vip_count', 50)} users\n"
    text += f"• Get {cfg.get('referral_purchase_count', 10)} referrals to buy VIP"
    
    bot.edit_message_text(text, uid, call.message.message_id)
    bot.answer_callback_query(call.id)

# =========================
# 👑 BUY VIP WITH POINTS
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "buy_vip_points")
def buy_vip_points_callback(call):
    uid = call.from_user.id
    cfg = get_cached_config()
    price = cfg.get("vip_points_price", 5000)
    
    if User.is_vip(uid):
        bot.answer_callback_query(call.id, "✅ Already VIP!", True)
        return
    
    if User.points(uid) >= price:
        User.spend_points(uid, price)
        User.make_vip(uid, cfg.get("vip_duration_days", 30))
        
        bot.answer_callback_query(call.id, "✅ VIP Activated!", True)
        bot.edit_message_text(
            f"🎉 <b>CONGRATULATIONS!</b> 🎉\n\n"
            f"You are now <b>VIP</b>!\n"
            f"💰 Remaining balance: {User.points(uid)} 💎",
            uid, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, f"❌ Need {price}💎! Balance: {User.points(uid)}", True)

# =========================
# 📊 LEADERBOARD CALLBACKS
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "top_points")
def top_points_callback(call):
    users = list(users_col.find({}).sort("points", -1).limit(20))
    text = "🏆 <b>TOP 20 USERS BY POINTS</b> 🏆\n\n"
    
    for i, user in enumerate(users, 1):
        name = user.get("username") or f"User_{user['_id'][:6]}"
        points = user.get("points", 0)
        vip = "👑" if user.get("vip", False) else "📌"
        text += f"{i}. {vip} <code>{name}</code> → {points:,} 💎\n"
    
    if not users:
        text += "No users found!"
    
    bot.edit_message_text(text, call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "top_refs")
def top_refs_callback(call):
    users = list(users_col.find({}).sort("refs", -1).limit(20))
    text = "👥 <b>TOP 20 USERS BY REFERRALS</b> 👥\n\n"
    
    for i, user in enumerate(users, 1):
        name = user.get("username") or f"User_{user['_id'][:6]}"
        refs = user.get("refs", 0)
        vip = "👑" if user.get("vip", False) else "📌"
        text += f"{i}. {vip} <code>{name}</code> → {refs} referrals\n"
    
    if not users:
        text += "No users found!"
    
    bot.edit_message_text(text, call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "top_earners")
def top_earners_callback(call):
    users = list(users_col.find({}).sort("total_points_earned", -1).limit(20))
    text = "⭐ <b>TOP 20 USERS BY POINTS EARNED</b> ⭐\n\n"
    
    for i, user in enumerate(users, 1):
        name = user.get("username") or f"User_{user['_id'][:6]}"
        earned = user.get("total_points_earned", 0)
        vip = "👑" if user.get("vip", False) else "📌"
        text += f"{i}. {vip} <code>{name}</code> → {earned:,} 💎\n"
    
    if not users:
        text += "No users found!"
    
    bot.edit_message_text(text, call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

# =========================
# 🔙 NAVIGATION CALLBACKS
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("back|"))
def back_callback(call):
    _, cat, parent = call.data.split("|")
    kb = get_folders_keyboard(cat, parent if parent else None)
    bot.edit_message_reply_markup(call.from_user.id, call.message.message_id, reply_markup=kb)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("page|"))
def page_callback(call):
    _, cat, page, parent = call.data.split("|")
    parent = parent if parent != "None" else None
    kb = get_folders_keyboard(cat, parent, int(page))
    bot.edit_message_reply_markup(call.from_user.id, call.message.message_id, reply_markup=kb)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "main_menu")
def main_menu_callback(call):
    uid = call.from_user.id
    points = User.points(uid)
    bot.edit_message_text(
        f"🏠 <b>MAIN MENU</b> 🏠\n\n💰 Balance: {points} 💎",
        uid, call.message.message_id,
        reply_markup=get_main_menu(uid))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "cancel_buy")
def cancel_buy_callback(call):
    bot.edit_message_text("❌ Cancelled", call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "check_force")
def check_force_callback(call):
    uid = call.from_user.id
    if not check_force_join(uid):
        bot.edit_message_text("✅ <b>Access Granted!</b>", uid, call.message.message_id)
        points = User.points(uid)
        bot.send_message(uid, f"🎉 Welcome!\n\n💰 Balance: {points} 💎", reply_markup=get_main_menu(uid))
    else:
        bot.answer_callback_query(call.id, "❌ Please join all channels first!", True)

@bot.callback_query_handler(func=lambda c: c.data == "noop")
def noop_callback(call):
    bot.answer_callback_query(call.id)

# =========================
# ⚙️ ADMIN PANEL - COMPLETE
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def admin_panel(message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Row 1 - Upload
    kb.add("📦 Upload FREE", "💎 Upload VIP")
    kb.add("📱 Upload APPS", "⚡ Upload SERVICE")
    
    # Row 2 - Management
    kb.add("📁 Create Subfolder", "🗑 Delete Folder")
    kb.add("✏️ Edit Price", "✏️ Edit Name")
    kb.add("📝 Edit Content", "🔀 Move Folder")
    
    # Row 3 - User Management
    kb.add("👑 Add VIP", "👑 Remove VIP")
    kb.add("💰 Give Points", "🎫 Generate Codes")
    
    # Row 4 - Tools
    kb.add("📊 View Codes", "📦 Points Packages")
    kb.add("👥 Admin Management", "📞 Set Contacts")
    
    # Row 5 - Settings
    kb.add("⚙️ VIP Settings", "💳 Payment Methods")
    kb.add("🏦 Binance Settings", "📸 Screenshot")
    kb.add("➕ Add Button", "➖ Remove Button")
    kb.add("➕ Add Channel", "➖ Remove Channel")
    
    # Row 6 - Actions
    kb.add("⚙️ Settings", "📊 Statistics")
    kb.add("📢 Broadcast", "🔔 Toggle Notify")
    kb.add("📊 Leaderboard", "❌ Exit Admin")
    
    bot.send_message(message.from_user.id, "⚙️ <b>ADMIN CONTROL PANEL</b> ⚙️\n\nSelect an option:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "❌ Exit Admin" and is_admin(m.from_user.id))
def exit_admin(message):
    bot.send_message(message.from_user.id, "👋 Exited admin mode", reply_markup=get_main_menu(message.from_user.id))

# =========================
# 📤 UPLOAD SYSTEM
# =========================
upload_sessions = {}

@bot.message_handler(func=lambda m: m.text in ["📦 Upload FREE", "💎 Upload VIP", "📱 Upload APPS", "⚡ Upload SERVICE"] and is_admin(m.from_user.id))
def start_upload(message):
    cat_map = {
        "📦 Upload FREE": "free",
        "💎 Upload VIP": "vip",
        "📱 Upload APPS": "apps",
        "⚡ Upload SERVICE": "services"
    }
    
    uid = message.from_user.id
    upload_sessions[uid] = {
        "cat": cat_map[message.text],
        "files": [],
        "step": "name"
    }
    
    bot.send_message(uid, "📝 <b>Enter folder name:</b>\n\nUse letters, numbers, and spaces.")

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions[m.from_user.id].get("step") == "name")
def upload_get_name(message):
    uid = message.from_user.id
    upload_sessions[uid]["name"] = message.text
    upload_sessions[uid]["step"] = "price"
    bot.send_message(uid, "💰 <b>Enter price (points):</b>\n\n0 = free\nExample: <code>100</code>")

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions[m.from_user.id].get("step") == "price")
def upload_get_price(message):
    uid = message.from_user.id
    try:
        price = int(message.text)
        if price < 0:
            raise ValueError
        upload_sessions[uid]["price"] = price
        upload_sessions[uid]["step"] = "type"
        
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("📄 Text Content", "📁 File Upload")
        kb.add("❌ Cancel")
        bot.send_message(uid, "📝 <b>Choose content type:</b>", reply_markup=kb)
    except:
        bot.send_message(uid, "❌ Invalid price! Enter a number:")

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions[m.from_user.id].get("step") == "type" and m.text == "📄 Text Content")
def upload_text_type(message):
    uid = message.from_user.id
    upload_sessions[uid]["type"] = "text"
    upload_sessions[uid]["step"] = "text"
    bot.send_message(uid, "📝 <b>Enter text content:</b>\n\nYou can use HTML formatting.", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("❌ Cancel"))

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions[m.from_user.id].get("step") == "type" and m.text == "📁 File Upload")
def upload_files_type(message):
    uid = message.from_user.id
    upload_sessions[uid]["type"] = "files"
    upload_sessions[uid]["step"] = "files"
    upload_sessions[uid]["files"] = []
    
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✅ Done", "❌ Cancel")
    bot.send_message(uid, "📁 <b>Send files:</b>\n\nSend photos, documents, or videos.\nPress <b>✅ Done</b> when finished.", reply_markup=kb)

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions[m.from_user.id].get("step") == "text")
def upload_save_text(message):
    uid = message.from_user.id
    data = upload_sessions[uid]
    
    if message.text == "❌ Cancel":
        upload_sessions.pop(uid, None)
        bot.send_message(uid, "❌ Cancelled", reply_markup=get_main_menu(uid))
        return
    
    number = fs.add(
        cat=data["cat"],
        name=data["name"],
        files=[],
        price=data["price"],
        text_content=message.text
    )
    
    bot.send_message(uid, 
        f"✅ <b>UPLOADED SUCCESSFULLY!</b> ✅\n\n"
        f"📌 <b>#{number}</b>\n"
        f"📂 {add_auto_emoji(data['name'], data['cat'])}\n"
        f"💰 {data['price']} 💎\n"
        f"📄 Text content",
        reply_markup=admin_panel_menu())
    
    upload_sessions.pop(uid, None)

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions[m.from_user.id].get("step") == "files")
def upload_files_process(message):
    uid = message.from_user.id
    
    if message.text == "✅ Done":
        data = upload_sessions[uid]
        if not data.get("files"):
            bot.send_message(uid, "❌ No files uploaded! Send at least one file.")
            return
        
        number = fs.add(
            cat=data["cat"],
            name=data["name"],
            files=data["files"],
            price=data["price"]
        )
        
        bot.send_message(uid, 
            f"✅ <b>UPLOADED SUCCESSFULLY!</b> ✅\n\n"
            f"📌 <b>#{number}</b>\n"
            f"📂 {add_auto_emoji(data['name'], data['cat'])}\n"
            f"💰 {data['price']} 💎\n"
            f"📁 {len(data['files'])} files",
            reply_markup=admin_panel_menu())
        
        upload_sessions.pop(uid, None)
        return
    
    if message.text == "❌ Cancel":
        upload_sessions.pop(uid, None)
        bot.send_message(uid, "❌ Cancelled", reply_markup=get_main_menu(uid))
        return
    
    if message.content_type in ["photo", "document", "video"]:
        data = upload_sessions[uid]
        data["files"].append({
            "chat": message.chat.id,
            "msg": message.message_id,
            "type": message.content_type
        })
        bot.send_message(uid, f"✅ File {len(data['files'])} added! Send more or press ✅ Done")

def admin_panel_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Upload FREE", "💎 Upload VIP", "📱 Upload APPS", "⚡ Upload SERVICE", "❌ Exit Admin")
    return kb

# =========================
# 📁 CREATE SUBFOLDER
# =========================
@bot.message_handler(func=lambda m: m.text == "📁 Create Subfolder" and is_admin(m.from_user.id))
def create_subfolder(message):
    msg = bot.send_message(message.from_user.id, 
        "📁 <b>Create Subfolder</b>\n\n"
        "Send in format:\n"
        "<code>category parent_name sub_name price</code>\n\n"
        "Example: <code>free Tutorials Advanced 10</code>\n\n"
        "Categories: free, vip, apps, services")

def process_subfolder(message):
    try:
        parts = message.text.split(maxsplit=3)
        if len(parts) < 4:
            bot.send_message(message.from_user.id, "❌ Invalid format! Use: category parent name price")
            return
        
        cat = parts[0].lower()
        parent = parts[1]
        name = parts[2]
        price = int(parts[3])
        
        if cat not in ["free", "vip", "apps", "services"]:
            bot.send_message(message.from_user.id, "❌ Invalid category! Use: free, vip, apps, services")
            return
        
        parent_folder = fs.get_one(cat, parent)
        if not parent_folder:
            bot.send_message(message.from_user.id, f"❌ Parent folder '{parent}' not found in {cat}!")
            return
        
        number = fs.add(cat, name, [], price, parent)
        
        bot.send_message(message.from_user.id, 
            f"✅ <b>SUBFOLDER CREATED!</b> ✅\n\n"
            f"📌 <b>#{number}</b>\n"
            f"📂 {parent} → {name}\n"
            f"💰 {price} 💎",
            reply_markup=admin_panel_menu())
    except Exception as e:
        bot.send_message(message.from_user.id, f"❌ Error: {str(e)}")

# =========================
# 🗑 DELETE FOLDER
# =========================
@bot.message_handler(func=lambda m: m.text == "🗑 Delete Folder" and is_admin(m.from_user.id))
def delete_folder_start(message):
    msg = bot.send_message(message.from_user.id, 
        "🗑 <b>Delete Folder</b>\n\n"
        "Send in format:\n"
        "<code>category folder_name</code>\n\n"
        "Example: <code>free Test</code>")

def process_delete(message):
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) != 2:
            bot.send_message(message.from_user.id, "❌ Use: category folder_name")
            return
        
        cat = parts[0].lower()
        name = parts[1].strip()
        
        if cat not in ["free", "vip", "apps", "services"]:
            bot.send_message(message.from_user.id, "❌ Invalid category!")
            return
        
        folder = fs.get_one(cat, name)
        if not folder:
            bot.send_message(message.from_user.id, f"❌ '{name}' not found in {cat}!")
            return
        
        # Confirm deletion
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("✅ YES, DELETE", callback_data=f"confirm_del|{cat}|{name}"),
            InlineKeyboardButton("❌ NO, CANCEL", callback_data="cancel_del")
        )
        
        bot.send_message(message.from_user.id, 
            f"⚠️ <b>CONFIRM DELETION</b> ⚠️\n\n"
            f"Category: {cat}\n"
            f"Folder: {name}\n\n"
            f"This action cannot be undone!",
            reply_markup=kb)
    except:
        bot.send_message(message.from_user.id, "❌ Use: category folder_name")

@bot.callback_query_handler(func=lambda c: c.data.startswith("confirm_del|"))
def confirm_delete_callback(call):
    _, cat, name = call.data.split("|")
    if fs.delete(cat, name):
        bot.edit_message_text(f"✅ Deleted: {cat} → {name}", call.from_user.id, call.message.message_id)
        bot.send_message(call.from_user.id, "✅ Folder deleted!", reply_markup=admin_panel_menu())
    else:
        bot.edit_message_text("❌ Failed to delete!", call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "cancel_del")
def cancel_delete_callback(call):
    bot.edit_message_text("❌ Deletion cancelled", call.from_user.id, call.message.message_id)
    bot.send_message(call.from_user.id, "Returning to admin panel...", reply_markup=admin_panel_menu())
    bot.answer_callback_query(call.id)

# =========================
# ✏️ EDIT PRICE
# =========================
@bot.message_handler(func=lambda m: m.text == "✏️ Edit Price" and is_admin(m.from_user.id))
def edit_price_start(message):
    msg = bot.send_message(message.from_user.id, 
        "✏️ <b>Edit Price</b>\n\n"
        "Send in format:\n"
        "<code>category folder_name new_price</code>\n\n"
        "Example: <code>vip Method 50</code>")

def process_edit_price(message):
    try:
        parts = message.text.rsplit(maxsplit=2)
        if len(parts) < 3:
            bot.send_message(message.from_user.id, "❌ Use: category folder_name new_price")
            return
        
        cat = parts[0].lower()
        price = int(parts[-1])
        name = " ".join(parts[1:-1]) if len(parts) > 2 else parts[1]
        
        fs.edit_price(cat, name, price)
        bot.send_message(message.from_user.id, f"✅ Price updated to {price} 💎!", reply_markup=admin_panel_menu())
    except:
        bot.send_message(message.from_user.id, "❌ Invalid format!")

# =========================
# ✏️ EDIT NAME
# =========================
@bot.message_handler(func=lambda m: m.text == "✏️ Edit Name" and is_admin(m.from_user.id))
def edit_name_start(message):
    msg = bot.send_message(message.from_user.id, 
        "✏️ <b>Edit Name</b>\n\n"
        "Send in format:\n"
        "<code>category old_name new_name</code>\n\n"
        "Example: <code>free OldMethod NewMethod</code>")

def process_edit_name(message):
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            bot.send_message(message.from_user.id, "❌ Use: category old_name new_name")
            return
        
        cat = parts[0].lower()
        old = parts[1]
        new = parts[2]
        
        fs.edit_name(cat, old, new)
        bot.send_message(message.from_user.id, f"✅ Renamed: {old} → {new}", reply_markup=admin_panel_menu())
    except:
        bot.send_message(message.from_user.id, "❌ Invalid format!")

# =========================
# 📝 EDIT CONTENT
# =========================
edit_sessions = {}

@bot.message_handler(func=lambda m: m.text == "📝 Edit Content" and is_admin(m.from_user.id))
def edit_content_start(message):
    msg = bot.send_message(message.from_user.id, 
        "📝 <b>Edit Content</b>\n\n"
        "Send in format:\n"
        "<code>category folder_name</code>\n\n"
        "Example: <code>vip My Method</code>")

def process_edit_content_select(message):
    uid = message.from_user.id
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) != 2:
            bot.send_message(uid, "❌ Use: category folder_name")
            return
        
        cat = parts[0].lower()
        name = parts[1].strip()
        
        folder = fs.get_one(cat, name)
        if not folder:
            bot.send_message(uid, f"❌ '{name}' not found!")
            return
        
        edit_sessions[uid] = {"cat": cat, "name": name}
        
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("📝 Edit Text", callback_data="edit_text"),
            InlineKeyboardButton("📁 Edit Files", callback_data="edit_files"),
            InlineKeyboardButton("❌ Cancel", callback_data="edit_cancel")
        )
        
        bot.send_message(uid, f"📝 <b>Editing: {add_auto_emoji(name, cat)}</b>\n\nWhat would you like to edit?", reply_markup=kb)
    except:
        bot.send_message(uid, "❌ Invalid format!")

@bot.callback_query_handler(func=lambda c: c.data == "edit_text")
def edit_text_callback(call):
    uid = call.from_user.id
    if uid not in edit_sessions:
        bot.answer_callback_query(call.id, "Session expired!")
        return
    
    s = edit_sessions[uid]
    folder = fs.get_one(s["cat"], s["name"])
    current = folder.get("text_content", "No content")[:300]
    
    msg = bot.send_message(uid, 
        f"📝 <b>Current Text Content:</b>\n\n{current}\n\n"
        f"Send <b>NEW text content</b> (HTML allowed):\n"
        f"Send <code>/skip</code> to keep current")
    bot.register_next_step_handler(msg, save_edit_text)
    bot.answer_callback_query(call.id)

def save_edit_text(message):
    uid = message.from_user.id
    if uid not in edit_sessions:
        bot.send_message(uid, "Session expired!", reply_markup=admin_panel_menu())
        return
    
    if message.text == "/skip":
        edit_sessions.pop(uid, None)
        bot.send_message(uid, "❌ Cancelled", reply_markup=admin_panel_menu())
        return
    
    s = edit_sessions[uid]
    fs.edit_content(s["cat"], s["name"], "text", message.text)
    bot.send_message(uid, f"✅ Text content updated for <b>{s['name']}</b>!", reply_markup=admin_panel_menu())
    edit_sessions.pop(uid, None)

@bot.callback_query_handler(func=lambda c: c.data == "edit_files")
def edit_files_callback(call):
    uid = call.from_user.id
    if uid not in edit_sessions:
        bot.answer_callback_query(call.id, "Session expired!")
        return
    
    edit_sessions[uid]["new_files"] = []
    edit_sessions[uid]["step"] = "files"
    
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✅ Done", "❌ Cancel")
    bot.send_message(uid, "📁 <b>Send NEW files</b>\n\nSend photos, documents, or videos.\nPress <b>✅ Done</b> when finished.", reply_markup=kb)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "edit_cancel")
def edit_cancel_callback(call):
    edit_sessions.pop(call.from_user.id, None)
    bot.edit_message_text("❌ Cancelled", call.from_user.id, call.message.message_id)
    bot.send_message(call.from_user.id, "Returning to admin panel...", reply_markup=admin_panel_menu())
    bot.answer_callback_query(call.id)

# =========================
# 🔀 MOVE FOLDER
# =========================
@bot.message_handler(func=lambda m: m.text == "🔀 Move Folder" and is_admin(m.from_user.id))
def move_folder_start(message):
    msg = bot.send_message(message.from_user.id, 
        "🔀 <b>Move Folder</b>\n\n"
        "Send in format:\n"
        "<code>folder_number new_parent</code>\n\n"
        "Use 'root' for main level\n"
        "Example: <code>15 Tutorials</code>")

def process_move_folder(message):
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) != 2:
            bot.send_message(message.from_user.id, "❌ Use: folder_number new_parent")
            return
        
        number = int(parts[0])
        new_parent = parts[1] if parts[1] != "root" else None
        
        folder = fs.get_by_number(number)
        if not folder:
            bot.send_message(message.from_user.id, f"❌ Folder #{number} not found!")
            return
        
        fs.move_folder(number, new_parent)
        bot.send_message(message.from_user.id, f"✅ Folder #{number} moved to '{new_parent or 'root'}'!", reply_markup=admin_panel_menu())
    except:
        bot.send_message(message.from_user.id, "❌ Use: number parent")

# =========================
# 👑 ADD VIP
# =========================
@bot.message_handler(func=lambda m: m.text == "👑 Add VIP" and is_admin(m.from_user.id))
def add_vip_start(message):
    msg = bot.send_message(message.from_user.id, 
        "👑 <b>Add VIP</b>\n\n"
        "Send user ID or @username:\n"
        "Example: <code>123456789</code> or <code>@username</code>")

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
    
    if User.is_vip(uid):
        bot.send_message(message.from_user.id, "⚠️ User is already VIP!")
        return
    
    cfg = get_cached_config()
    User.make_vip(uid, cfg.get("vip_duration_days", 30))
    
    bot.send_message(message.from_user.id, f"✅ User <code>{uid}</code> is now VIP!", reply_markup=admin_panel_menu())
    
    try:
        bot.send_message(uid, "🎉 <b>CONGRATULATIONS!</b> 🎉\n\nYou have been granted <b>VIP</b> status by an admin!")
    except:
        pass

# =========================
# 👑 REMOVE VIP
# =========================
@bot.message_handler(func=lambda m: m.text == "👑 Remove VIP" and is_admin(m.from_user.id))
def remove_vip_start(message):
    msg = bot.send_message(message.from_user.id, 
        "🗑 <b>Remove VIP</b>\n\n"
        "Send user ID or @username:\n"
        "Example: <code>123456789</code> or <code>@username</code>")

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
    
    if not User.is_vip(uid):
        bot.send_message(message.from_user.id, "⚠️ User is not VIP!")
        return
    
    User.remove_vip(uid)
    
    bot.send_message(message.from_user.id, f"✅ VIP removed from <code>{uid}</code>!", reply_markup=admin_panel_menu())
    
    try:
        bot.send_message(uid, "⚠️ Your VIP status has been removed by an admin.")
    except:
        pass

# =========================
# 💰 GIVE POINTS
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 Give Points" and is_admin(m.from_user.id))
def give_points_start(message):
    msg = bot.send_message(message.from_user.id, 
        "💰 <b>Give Points</b>\n\n"
        "Send in format:\n"
        "<code>user_id points</code>\n\n"
        "Example: <code>123456789 100</code>")

def process_give_points(message):
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(message.from_user.id, "❌ Use: user_id points")
            return
        
        uid = int(parts[0])
        points = int(parts[1])
        
        if points <= 0 or points > 100000:
            bot.send_message(message.from_user.id, "❌ Points must be between 1 and 100,000")
            return
        
        old_points = User.points(uid)
        new_points = User.add_points(uid, points)
        
        bot.send_message(message.from_user.id, 
            f"✅ <b>POINTS ADDED!</b> ✅\n\n"
            f"👤 User: <code>{uid}</code>\n"
            f"💰 Old balance: {old_points:,} 💎\n"
            f"➕ Added: +{points:,} 💎\n"
            f"💰 New balance: {new_points:,} 💎",
            reply_markup=admin_panel_menu())
        
        try:
            bot.send_message(uid, 
                f"🎉 <b>POINTS RECEIVED!</b> 🎉\n\n"
                f"You received <b>+{points:,} points</b>!\n"
                f"💰 New balance: {new_points:,} 💎")
        except:
            pass
    except:
        bot.send_message(message.from_user.id, "❌ Use: user_id points")

# =========================
# 🎫 GENERATE CODES
# =========================
@bot.message_handler(func=lambda m: m.text == "🎫 Generate Codes" and is_admin(m.from_user.id))
def generate_codes_start(message):
    msg = bot.send_message(message.from_user.id, 
        "🎫 <b>Generate Codes</b>\n\n"
        "Send in format:\n"
        "<code>points count multi_use expiry_days</code>\n\n"
        "Example: <code>100 5 false 30</code>\n"
        "Example: <code>500 1 false 0</code> (no expiry)\n"
        "Example: <code>50 10 true 7</code> (multi-use)")

def process_generate_codes(message):
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.send_message(message.from_user.id, "❌ Use: points count multi_use expiry_days")
            return
        
        points = int(parts[0])
        count = int(parts[1])
        multi_use = parts[2].lower() in ["true", "yes", "1"]
        expiry_days = int(parts[3]) if len(parts) > 3 and int(parts[3]) > 0 else None
        
        if count > 50:
            bot.send_message(message.from_user.id, "❌ Maximum 50 codes at once!")
            return
        
        new_codes = codes.generate(points, count, multi_use, expiry_days)
        
        expiry_text = f"{expiry_days} days" if expiry_days else "No expiry"
        code_text = "\n".join(new_codes)
        
        bot.send_message(message.from_user.id, 
            f"✅ <b>CODES GENERATED!</b> ✅\n\n"
            f"💰 Points: {points} 💎\n"
            f"🔢 Count: {count}\n"
            f"🔄 Multi-use: {'Yes' if multi_use else 'No'}\n"
            f"⏰ Expiry: {expiry_text}\n\n"
            f"<code>{code_text}</code>",
            reply_markup=admin_panel_menu())
    except:
        bot.send_message(message.from_user.id, "❌ Use: points count multi_use expiry_days")

# =========================
# 📊 VIEW CODES
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 View Codes" and is_admin(m.from_user.id))
def view_codes_admin(message):
    all_codes = codes.get_all()[:30]
    if not all_codes:
        bot.send_message(message.from_user.id, "📊 No codes found!")
        return
    
    total, used, unused, multi = codes.get_stats()
    
    text = f"📊 <b>CODE STATISTICS</b> 📊\n\n"
    text += f"📊 Total: {total}\n"
    text += f"✅ Used: {used}\n"
    text += f"⏳ Unused: {unused}\n"
    text += f"🔄 Multi-use: {multi}\n\n"
    text += f"📋 <b>RECENT CODES:</b>\n"
    
    for c in all_codes[:10]:
        used_status = "❌" if c.get("used", False) else "✅"
        multi_status = "🔄" if c.get("multi_use", False) else "📄"
        uses = c.get("used_count", 0)
        text += f"{used_status} {multi_status} <code>{c['_id']}</code> - {c['points']}💎 (used: {uses})\n"
    
    bot.send_message(message.from_user.id, text)

# =========================
# 📦 POINTS PACKAGES
# =========================
def get_points_packages():
    packages = config_col.find_one({"_id": "points_packages"})
    if not packages:
        default = {
            "_id": "points_packages",
            "packages": [
                {"points": 100, "price": 5, "bonus": 0, "active": True},
                {"points": 250, "price": 10, "bonus": 25, "active": True},
                {"points": 550, "price": 20, "bonus": 100, "active": True},
                {"points": 1500, "price": 50, "bonus": 500, "active": True},
                {"points": 3500, "price": 100, "bonus": 1500, "active": True},
                {"points": 10000, "price": 250, "bonus": 5000, "active": True}
            ]
        }
        config_col.insert_one(default)
        return default["packages"]
    return packages["packages"]

def save_points_packages(packages):
    config_col.update_one({"_id": "points_packages"}, {"$set": {"packages": packages}}, upsert=True)

@bot.message_handler(func=lambda m: m.text == "📦 Points Packages" and is_admin(m.from_user.id))
def points_packages_menu(message):
    packages = get_points_packages()
    text = "📦 <b>POINTS PACKAGES</b>\n\n"
    for i, p in enumerate(packages, 1):
        status = "✅" if p.get("active", True) else "❌"
        text += f"{i}. {status} {p['points']}💎 - ${p['price']}"
        if p.get("bonus", 0) > 0:
            text += f" (+{p['bonus']})"
        text += "\n"
    text += "\nCommands:\n/addpackage pts price bonus\n/editpackage num pts price bonus\n/togglepackage num\n/delpackage num"
    bot.send_message(message.from_user.id, text)

@bot.message_handler(commands=["addpackage", "editpackage", "togglepackage", "delpackage"])
def package_commands(message):
    if not is_admin(message.from_user.id):
        return
    
    cmd = message.text.split()[0][1:]
    packages = get_points_packages()
    
    try:
        if cmd == "addpackage":
            _, pts, price, bonus = message.text.split()
            packages.append({
                "points": int(pts),
                "price": int(price),
                "bonus": int(bonus),
                "active": True
            })
            save_points_packages(packages)
            bot.send_message(message.from_user.id, f"✅ Added {pts}💎 package for ${price}")
        elif cmd == "editpackage":
            _, num, pts, price, bonus = message.text.split()
            num = int(num) - 1
            if 0 <= num < len(packages):
                packages[num].update({
                    "points": int(pts),
                    "price": int(price),
                    "bonus": int(bonus)
                })
                save_points_packages(packages)
                bot.send_message(message.from_user.id, f"✅ Package {num+1} updated!")
            else:
                bot.send_message(message.from_user.id, "❌ Invalid package number!")
        elif cmd == "togglepackage":
            _, num = message.text.split()
            num = int(num) - 1
            if 0 <= num < len(packages):
                packages[num]["active"] = not packages[num].get("active", True)
                save_points_packages(packages)
                status = "activated" if packages[num]["active"] else "deactivated"
                bot.send_message(message.from_user.id, f"✅ Package {num+1} {status}!")
            else:
                bot.send_message(message.from_user.id, "❌ Invalid package number!")
        elif cmd == "delpackage":
            _, num = message.text.split()
            num = int(num) - 1
            if 0 <= num < len(packages):
                removed = packages.pop(num)
                save_points_packages(packages)
                bot.send_message(message.from_user.id, f"✅ Removed {removed['points']}💎 package!")
            else:
                bot.send_message(message.from_user.id, "❌ Invalid package number!")
    except Exception as e:
        bot.send_message(message.from_user.id, f"❌ Error: {str(e)}\nUse: /{cmd} ...")

# =========================
# 👥 ADMIN MANAGEMENT
# =========================
@bot.message_handler(func=lambda m: m.text == "👥 Admin Management" and is_admin(m.from_user.id))
def admin_management(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.from_user.id, "❌ Owner only!")
        return
    
    admins = get_all_admins()
    text = "👥 <b>ADMIN LIST</b>\n\n"
    for a in admins:
        owner = " 👑 OWNER" if a["_id"] == ADMIN_ID else ""
        text += f"• <code>{a['_id']}</code>{owner}\n"
    text += "\nCommands:\n/addadmin id\n/removeadmin id"
    bot.send_message(message.from_user.id, text)

@bot.message_handler(commands=["addadmin", "removeadmin"])
def admin_commands(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    cmd = message.text.split()[0][1:]
    try:
        _, uid = message.text.split()
        uid = int(uid)
        
        if cmd == "addadmin":
            if add_admin(uid, message.from_user.username, message.from_user.id):
                bot.send_message(message.from_user.id, f"✅ Admin {uid} added!")
                try:
                    bot.send_message(uid, "🎉 You have been made an admin!")
                except:
                    pass
            else:
                bot.send_message(message.from_user.id, "❌ Already an admin!")
        else:
            if remove_admin(uid):
                bot.send_message(message.from_user.id, f"✅ Admin {uid} removed!")
                try:
                    bot.send_message(uid, "⚠️ Your admin rights have been removed.")
                except:
                    pass
            else:
                bot.send_message(message.from_user.id, "❌ Not an admin or cannot remove owner!")
    except:
        bot.send_message(message.from_user.id, f"❌ Use: /{cmd} user_id")

# =========================
# 📞 SET CONTACTS
# =========================
@bot.message_handler(func=lambda m: m.text == "📞 Set Contacts" and is_admin(m.from_user.id))
def set_contacts_menu(message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("💰 Points Contact", callback_data="set_points_contact"),
        InlineKeyboardButton("👑 VIP Contact", callback_data="set_vip_contact"),
        InlineKeyboardButton("📋 View Contacts", callback_data="view_contacts")
    )
    bot.send_message(message.from_user.id, "📞 <b>Contact Settings</b>", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "set_points_contact")
def set_points_contact_callback(call):
    msg = bot.send_message(call.from_user.id, "💰 <b>Set Points Contact</b>\n\nSend @username or link:\nSend 'none' to remove")
    bot.register_next_step_handler(msg, save_points_contact)
    bot.answer_callback_query(call.id)

def save_points_contact(message):
    if message.text.lower() == "none":
        set_config("contact_username", None)
        set_config("contact_link", None)
    elif message.text.startswith("http"):
        set_config("contact_link", message.text)
        set_config("contact_username", None)
    elif message.text.startswith("@"):
        set_config("contact_username", message.text)
        set_config("contact_link", None)
    else:
        bot.send_message(message.from_user.id, "❌ Invalid! Use @username or https:// link")
        return
    bot.send_message(message.from_user.id, "✅ Contact updated!", reply_markup=admin_panel_menu())

@bot.callback_query_handler(func=lambda c: c.data == "set_vip_contact")
def set_vip_contact_callback(call):
    msg = bot.send_message(call.from_user.id, "👑 <b>Set VIP Contact</b>\n\nSend @username or link:\nSend 'none' to remove")
    bot.register_next_step_handler(msg, save_vip_contact)
    bot.answer_callback_query(call.id)

def save_vip_contact(message):
    if message.text.lower() == "none":
        set_config("vip_contact", None)
    elif message.text.startswith("http") or message.text.startswith("@"):
        set_config("vip_contact", message.text)
    else:
        bot.send_message(message.from_user.id, "❌ Invalid! Use @username or https:// link")
        return
    bot.send_message(message.from_user.id, "✅ VIP contact updated!", reply_markup=admin_panel_menu())

@bot.callback_query_handler(func=lambda c: c.data == "view_contacts")
def view_contacts_callback(call):
    cfg = get_cached_config()
    points = cfg.get("contact_username") or cfg.get("contact_link") or "Not set"
    vip = cfg.get("vip_contact") or "Not set"
    bot.edit_message_text(
        f"📞 <b>CONTACTS</b>\n\n"
        f"💰 Points: {points}\n"
        f"👑 VIP: {vip}",
        call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

# =========================
# ⚙️ VIP SETTINGS
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ VIP Settings" and is_admin(m.from_user.id))
def vip_settings_menu(message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("💰 USD Price", callback_data="set_vip_usd"),
        InlineKeyboardButton("💎 Points Price", callback_data="set_vip_points"),
        InlineKeyboardButton("👥 Ref VIP Count", callback_data="set_ref_vip"),
        InlineKeyboardButton("🛒 Ref Purchase", callback_data="set_ref_purchase"),
        InlineKeyboardButton("📅 Duration", callback_data="set_vip_duration"),
        InlineKeyboardButton("📋 View", callback_data="view_vip_settings")
    )
    bot.send_message(message.from_user.id, "⚙️ <b>VIP Settings</b>", reply_markup=kb)

# VIP Settings Callbacks (simplified)
@bot.callback_query_handler(func=lambda c: c.data == "set_vip_usd")
def set_vip_usd_callback(call):
    msg = bot.send_message(call.from_user.id, f"💰 Current VIP USD price: ${get_cached_config().get('vip_price', 50)}\n\nSend new price:")
    bot.register_next_step_handler(msg, lambda x: set_config("vip_price", int(x.text)) if x.text.isdigit() else bot.send_message(x.from_user.id, "❌ Invalid!"))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "set_vip_points")
def set_vip_points_callback(call):
    msg = bot.send_message(call.from_user.id, f"💎 Current VIP points price: {get_cached_config().get('vip_points_price', 5000)}\n\nSend new price:")
    bot.register_next_step_handler(msg, lambda x: set_config("vip_points_price", int(x.text)) if x.text.isdigit() else bot.send_message(x.from_user.id, "❌ Invalid!"))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "set_ref_vip")
def set_ref_vip_callback(call):
    msg = bot.send_message(call.from_user.id, f"👥 Current referrals needed for VIP: {get_cached_config().get('referral_vip_count', 50)}\n\nSend new number:")
    bot.register_next_step_handler(msg, lambda x: set_config("referral_vip_count", int(x.text)) if x.text.isdigit() else bot.send_message(x.from_user.id, "❌ Invalid!"))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "set_ref_purchase")
def set_ref_purchase_callback(call):
    msg = bot.send_message(call.from_user.id, f"🛒 Current referral purchases needed for VIP: {get_cached_config().get('referral_purchase_count', 10)}\n\nSend new number:")
    bot.register_next_step_handler(msg, lambda x: set_config("referral_purchase_count", int(x.text)) if x.text.isdigit() else bot.send_message(x.from_user.id, "❌ Invalid!"))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "set_vip_duration")
def set_vip_duration_callback(call):
    msg = bot.send_message(call.from_user.id, f"📅 Current VIP duration (days): {get_cached_config().get('vip_duration_days', 30)} (0 = permanent)\n\nSend new duration:")
    bot.register_next_step_handler(msg, lambda x: set_config("vip_duration_days", int(x.text)) if x.text.isdigit() else bot.send_message(x.from_user.id, "❌ Invalid!"))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "view_vip_settings")
def view_vip_settings_callback(call):
    cfg = get_cached_config()
    text = f"📋 <b>VIP SETTINGS</b>\n\n"
    text += f"💰 USD Price: ${cfg.get('vip_price', 50)}\n"
    text += f"💎 Points Price: {cfg.get('vip_points_price', 5000):,}💎\n"
    text += f"👥 Referrals for VIP: {cfg.get('referral_vip_count', 50)}\n"
    text += f"🛒 Purchases for VIP: {cfg.get('referral_purchase_count', 10)}\n"
    text += f"📅 Duration: {cfg.get('vip_duration_days', 30)} days"
    if cfg.get('vip_duration_days', 30) == 0:
        text += " (permanent)"
    bot.edit_message_text(text, call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

# =========================
# 💳 PAYMENT METHODS
# =========================
@bot.message_handler(func=lambda m: m.text == "💳 Payment Methods" and is_admin(m.from_user.id))
def payment_methods_menu(message):
    methods = get_cached_config().get("payment_methods", ["💳 Binance", "💵 USDT"])
    text = "💳 <b>PAYMENT METHODS</b>\n\n"
    for i, mtd in enumerate(methods, 1):
        text += f"{i}. {mtd}\n"
    text += "\nCommands:\n/addmethod name\n/removemethod number\n/listmethods"
    bot.send_message(message.from_user.id, text)

@bot.message_handler(commands=["addmethod", "removemethod", "listmethods"])
def payment_method_commands(message):
    if not is_admin(message.from_user.id):
        return
    
    cmd = message.text.split()[0][1:]
    methods = get_cached_config().get("payment_methods", [])
    
    if cmd == "listmethods":
        text = "💳 <b>Methods</b>\n\n"
        for i, m in enumerate(methods, 1):
            text += f"{i}. {m}\n"
        bot.send_message(message.from_user.id, text)
        return
    
    try:
        if cmd == "addmethod":
            method = message.text.replace("/addmethod", "").strip()
            if not method:
                bot.send_message(message.from_user.id, "❌ Usage: /addmethod Method Name")
                return
            methods.append(method)
            set_config("payment_methods", methods)
            bot.send_message(message.from_user.id, f"✅ Added: {method}")
        elif cmd == "removemethod":
            _, num = message.text.split()
            num = int(num) - 1
            if 0 <= num < len(methods):
                removed = methods.pop(num)
                set_config("payment_methods", methods)
                bot.send_message(message.from_user.id, f"✅ Removed: {removed}")
            else:
                bot.send_message(message.from_user.id, "❌ Invalid number!")
    except:
        bot.send_message(message.from_user.id, f"❌ Use: /{cmd} ...")

# =========================
# 🏦 BINANCE SETTINGS
# =========================
@bot.message_handler(func=lambda m: m.text == "🏦 Binance Settings" and is_admin(m.from_user.id))
def binance_settings_menu(message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("💰 Coin", callback_data="set_binance_coin"),
        InlineKeyboardButton("🌐 Network", callback_data="set_binance_network"),
        InlineKeyboardButton("📍 Address", callback_data="set_binance_address"),
        InlineKeyboardButton("📝 Memo", callback_data="set_binance_memo"),
        InlineKeyboardButton("📋 View", callback_data="view_binance")
    )
    bot.send_message(message.from_user.id, "🏦 <b>Binance Settings</b>", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "set_binance_coin")
def set_binance_coin_callback(call):
    msg = bot.send_message(call.from_user.id, f"💰 Current coin: {get_cached_config().get('binance_coin', 'USDT')}\n\nSend new coin (USDT, BUSD, BTC):")
    bot.register_next_step_handler(msg, lambda x: set_config("binance_coin", x.text.upper()))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "set_binance_network")
def set_binance_network_callback(call):
    msg = bot.send_message(call.from_user.id, f"🌐 Current network: {get_cached_config().get('binance_network', 'TRC20')}\n\nSend new network (TRC20, BEP20, ERC20):")
    bot.register_next_step_handler(msg, lambda x: set_config("binance_network", x.text.upper()))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "set_binance_address")
def set_binance_address_callback(call):
    msg = bot.send_message(call.from_user.id, f"📍 Current address: {get_cached_config().get('binance_address', 'Not set')}\n\nSend new wallet address:")
    bot.register_next_step_handler(msg, lambda x: set_config("binance_address", x.text))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "set_binance_memo")
def set_binance_memo_callback(call):
    msg = bot.send_message(call.from_user.id, f"📝 Current memo: {get_cached_config().get('binance_memo', 'None')}\n\nSend new memo (or 'none' to clear):")
    bot.register_next_step_handler(msg, lambda x: set_config("binance_memo", "" if x.text.lower() == "none" else x.text))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "view_binance")
def view_binance_callback(call):
    cfg = get_cached_config()
    text = f"🏦 <b>BINANCE SETTINGS</b>\n\n"
    text += f"💰 Coin: {cfg.get('binance_coin', 'USDT')}\n"
    text += f"🌐 Network: {cfg.get('binance_network', 'TRC20')}\n"
    text += f"📍 Address: <code>{cfg.get('binance_address', 'Not set')}</code>\n"
    text += f"📝 Memo: <code>{cfg.get('binance_memo', 'None') or 'None'}</code>"
    bot.edit_message_text(text, call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

# =========================
# 📸 SCREENSHOT TOGGLE
# =========================
@bot.message_handler(func=lambda m: m.text == "📸 Screenshot" and is_admin(m.from_user.id))
def screenshot_toggle_menu(message):
    cfg = get_cached_config()
    current = cfg.get("require_screenshot", True)
    status = "✅ ENABLED" if current else "❌ DISABLED"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔘 TOGGLE", callback_data="toggle_screenshot"))
    bot.send_message(message.from_user.id, f"📸 <b>Screenshot Requirement</b>\n\n{status}\n\nRequire screenshot for payments?", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "toggle_screenshot")
def toggle_screenshot_callback(call):
    current = get_cached_config().get("require_screenshot", True)
    set_config("require_screenshot", not current)
    new_status = "ENABLED" if not current else "DISABLED"
    bot.answer_callback_query(call.id, f"Screenshot {new_status}!")
    bot.edit_message_text(f"✅ Screenshot requirement {new_status}!", call.from_user.id, call.message.message_id)
    bot.send_message(call.from_user.id, "Returning to admin panel...", reply_markup=admin_panel_menu())

# =========================
# ➕ ADD CUSTOM BUTTON
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ Add Button" and is_admin(m.from_user.id))
def add_custom_button_start(message):
    msg = bot.send_message(message.from_user.id, 
        "➕ <b>Add Custom Button</b>\n\n"
        "Send in format:\n"
        "<code>type|text|data</code>\n\n"
        "Types:\n"
        "• <code>link</code> - Opens URL\n"
        "• <code>folder</code> - Opens folder by number\n\n"
        "Examples:\n"
        "<code>link|Website|https://example.com</code>\n"
        "<code>folder|VIP Methods|5</code>")

def process_add_button(message):
    try:
        parts = message.text.split("|")
        if len(parts) != 3:
            bot.send_message(message.from_user.id, "❌ Use: type|text|data")
            return
        
        typ, text, data = parts[0].lower(), parts[1], parts[2]
        
        if typ not in ["link", "folder"]:
            bot.send_message(message.from_user.id, "❌ Type must be 'link' or 'folder'")
            return
        
        if typ == "folder" and not fs.get_by_number(int(data)):
            bot.send_message(message.from_user.id, f"❌ Folder #{data} not found!")
            return
        
        cfg = get_cached_config()
        buttons = cfg.get("custom_buttons", [])
        buttons.append({"text": text, "type": typ, "data": data})
        set_config("custom_buttons", buttons)
        
        bot.send_message(message.from_user.id, f"✅ Button added: {text}", reply_markup=admin_panel_menu())
    except:
        bot.send_message(message.from_user.id, "❌ Invalid format!")

# =========================
# ➖ REMOVE CUSTOM BUTTON
# =========================
@bot.message_handler(func=lambda m: m.text == "➖ Remove Button" and is_admin(m.from_user.id))
def remove_custom_button_start(message):
    cfg = get_cached_config()
    buttons = cfg.get("custom_buttons", [])
    
    if not buttons:
        bot.send_message(message.from_user.id, "❌ No custom buttons to remove!")
        return
    
    kb = InlineKeyboardMarkup(row_width=1)
    for btn in buttons:
        kb.add(InlineKeyboardButton(f"❌ {btn['text']}", callback_data=f"remove_btn_{btn['text']}"))
    
    bot.send_message(message.from_user.id, "Select button to remove:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("remove_btn_"))
def remove_button_callback(call):
    text = call.data[11:]
    cfg = get_cached_config()
    buttons = [b for b in cfg.get("custom_buttons", []) if b["text"] != text]
    set_config("custom_buttons", buttons)
    bot.edit_message_text(f"✅ Removed: {text}", call.from_user.id, call.message.message_id)
    bot.send_message(call.from_user.id, "Button removed!", reply_markup=admin_panel_menu())
    bot.answer_callback_query(call.id)

# =========================
# ➕ ADD FORCE CHANNEL
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ Add Channel" and is_admin(m.from_user.id))
def add_force_channel(message):
    msg = bot.send_message(message.from_user.id, 
        "➕ <b>Add Force Join Channel</b>\n\n"
        "Send channel @username:\n"
        "Example: <code>@mychannel</code>")

def process_add_channel(message):
    channel = message.text.strip()
    if not channel.startswith("@"):
        bot.send_message(message.from_user.id, "❌ Must start with @")
        return
    
    cfg = get_cached_config()
    channels = cfg.get("force_channels", [])
    
    if channel in channels:
        bot.send_message(message.from_user.id, "❌ Channel already added!")
        return
    
    channels.append(channel)
    set_config("force_channels", channels)
    bot.send_message(message.from_user.id, f"✅ Added: {channel}", reply_markup=admin_panel_menu())

# =========================
# ➖ REMOVE FORCE CHANNEL
# =========================
@bot.message_handler(func=lambda m: m.text == "➖ Remove Channel" and is_admin(m.from_user.id))
def remove_force_channel(message):
    cfg = get_cached_config()
    channels = cfg.get("force_channels", [])
    
    if not channels:
        bot.send_message(message.from_user.id, "❌ No channels to remove!")
        return
    
    kb = InlineKeyboardMarkup(row_width=1)
    for ch in channels:
        kb.add(InlineKeyboardButton(f"❌ {ch}", callback_data=f"remove_ch_{ch}"))
    
    bot.send_message(message.from_user.id, "Select channel to remove:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("remove_ch_"))
def remove_channel_callback(call):
    channel = call.data[10:]
    cfg = get_cached_config()
    channels = [ch for ch in cfg.get("force_channels", []) if ch != channel]
    set_config("force_channels", channels)
    bot.edit_message_text(f"✅ Removed: {channel}", call.from_user.id, call.message.message_id)
    bot.send_message(call.from_user.id, "Channel removed!", reply_markup=admin_panel_menu())
    bot.answer_callback_query(call.id)

# =========================
# ⚙️ GENERAL SETTINGS
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ Settings" and is_admin(m.from_user.id))
def general_settings_menu(message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📝 Welcome Message", callback_data="set_welcome"),
        InlineKeyboardButton("💎 VIP Message", callback_data="set_vip_msg"),
        InlineKeyboardButton("💰 Ref Reward", callback_data="set_ref_reward"),
        InlineKeyboardButton("💵 Points/$", callback_data="set_points_per_dollar")
    )
    bot.send_message(message.from_user.id, "⚙️ <b>General Settings</b>", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "set_welcome")
def set_welcome_callback(call):
    msg = bot.send_message(call.from_user.id, f"📝 Current welcome message:\n{get_cached_config().get('welcome', 'Welcome')}\n\nSend new welcome message:")
    bot.register_next_step_handler(msg, lambda x: set_config("welcome", x.text) or bot.send_message(x.from_user.id, "✅ Welcome message updated!"))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "set_vip_msg")
def set_vip_msg_callback(call):
    msg = bot.send_message(call.from_user.id, f"💎 Current VIP message:\n{get_cached_config().get('vip_msg', 'Buy VIP!')}\n\nSend new VIP message:")
    bot.register_next_step_handler(msg, lambda x: set_config("vip_msg", x.text) or bot.send_message(x.from_user.id, "✅ VIP message updated!"))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "set_ref_reward")
def set_ref_reward_callback(call):
    msg = bot.send_message(call.from_user.id, f"💰 Current referral reward: {get_cached_config().get('ref_reward', 5)} points\n\nSend new amount:")
    bot.register_next_step_handler(msg, lambda x: set_config("ref_reward", int(x.text)) if x.text.isdigit() else bot.send_message(x.from_user.id, "❌ Invalid number!"))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "set_points_per_dollar")
def set_points_per_dollar_callback(call):
    msg = bot.send_message(call.from_user.id, f"💵 Current points per dollar: {get_cached_config().get('points_per_dollar', 100)}\n\nSend new value (points per $1):")
    bot.register_next_step_handler(msg, lambda x: set_config("points_per_dollar", int(x.text)) if x.text.isdigit() else bot.send_message(x.from_user.id, "❌ Invalid number!"))
    bot.answer_callback_query(call.id)

# =========================
# 📊 STATISTICS
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 Statistics" and is_admin(m.from_user.id))
def statistics_command(message):
    total_users = users_col.count_documents({})
    vip_users = users_col.count_documents({"vip": True})
    free_users = total_users - vip_users
    
    all_users = list(users_col.find({}))
    total_points = sum(u.get("points", 0) for u in all_users)
    total_earned = sum(u.get("total_points_earned", 0) for u in all_users)
    total_spent = sum(u.get("total_points_spent", 0) for u in all_users)
    total_refs = sum(u.get("refs", 0) for u in all_users)
    total_purchases = sum(len(u.get("purchased_methods", [])) for u in all_users)
    
    free_methods = folders_col.count_documents({"cat": "free"})
    vip_methods = folders_col.count_documents({"cat": "vip"})
    apps = folders_col.count_documents({"cat": "apps"})
    services = folders_col.count_documents({"cat": "services"})
    
    total_codes, used_codes, unused_codes, multi_codes = codes.get_stats()
    
    text = f"📊 <b>BOT STATISTICS</b> 📊\n\n"
    text += f"👥 <b>USERS</b>\n"
    text += f"├ Total: {total_users}\n"
    text += f"├ VIP: {vip_users}\n"
    text += f"└ Free: {free_users}\n\n"
    text += f"💰 <b>POINTS</b>\n"
    text += f"├ Current: {total_points:,}\n"
    text += f"├ Earned: {total_earned:,}\n"
    text += f"├ Spent: {total_spent:,}\n"
    text += f"└ Avg: {total_points // total_users if total_users > 0 else 0:,}\n\n"
    text += f"📁 <b>CONTENT</b>\n"
    text += f"├ FREE: {free_methods}\n"
    text += f"├ VIP: {vip_methods}\n"
    text += f"├ APPS: {apps}\n"
    text += f"└ SERVICES: {services}\n\n"
    text += f"📈 <b>ACTIVITY</b>\n"
    text += f"├ Referrals: {total_refs}\n"
    text += f"├ Purchases: {total_purchases}\n"
    text += f"├ Codes Total: {total_codes}\n"
    text += f"├ Codes Used: {used_codes}\n"
    text += f"└ Codes Unused: {unused_codes}\n\n"
    text += f"⚙️ <b>SETTINGS</b>\n"
    text += f"└ Notifications: {'ON' if get_cached_config().get('notify_new_methods', True) else 'OFF'}"
    
    bot.send_message(message.from_user.id, text)

# =========================
# 📢 BROADCAST
# =========================
@bot.message_handler(func=lambda m: m.text == "📢 Broadcast" and is_admin(m.from_user.id))
def broadcast_start(message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📢 ALL USERS", callback_data="broadcast_all"),
        InlineKeyboardButton("👑 VIP ONLY", callback_data="broadcast_vip"),
        InlineKeyboardButton("🆓 FREE ONLY", callback_data="broadcast_free")
    )
    bot.send_message(message.from_user.id, "📢 <b>Broadcast Message</b>\n\nSelect target audience:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("broadcast_"))
def broadcast_target_callback(call):
    target = call.data.split("_")[1]
    msg = bot.send_message(call.from_user.id, f"📢 Send message to broadcast to {target.upper()} users:\n\n(HTML formatting supported)")
    bot.register_next_step_handler(msg, lambda x: process_broadcast(x, target))
    bot.answer_callback_query(call.id)

def process_broadcast(message, target):
    query = {}
    if target == "vip":
        query = {"vip": True}
    elif target == "free":
        query = {"vip": False}
    
    users = list(users_col.find(query))
    if not users:
        bot.send_message(message.from_user.id, "❌ No users found!")
        return
    
    status_msg = bot.send_message(message.from_user.id, f"📤 Broadcasting to {len(users)} users...")
    sent = 0
    failed = 0
    
    for user in users:
        try:
            uid = int(user["_id"])
            if message.content_type == "text":
                bot.send_message(uid, message.text, parse_mode="HTML")
            elif message.content_type == "photo":
                bot.send_photo(uid, message.photo[-1].file_id, caption=message.caption, parse_mode="HTML")
            elif message.content_type == "video":
                bot.send_video(uid, message.video.file_id, caption=message.caption, parse_mode="HTML")
            elif message.content_type == "document":
                bot.send_document(uid, message.document.file_id, caption=message.caption, parse_mode="HTML")
            sent += 1
            if sent % 20 == 0:
                time.sleep(0.2)
        except:
            failed += 1
    
    bot.edit_message_text(
        f"✅ <b>BROADCAST COMPLETE</b> ✅\n\n"
        f"📤 Sent: {sent}\n"
        f"❌ Failed: {failed}",
        message.from_user.id, status_msg.message_id)

# =========================
# 🔔 TOGGLE NOTIFY
# =========================
@bot.message_handler(func=lambda m: m.text == "🔔 Toggle Notify" and is_admin(m.from_user.id))
def toggle_notify_admin(message):
    current = get_cached_config().get("notify_new_methods", True)
    set_config("notify_new_methods", not current)
    status = "ON" if not current else "OFF"
    bot.send_message(message.from_user.id, f"🔔 New method notifications: <b>{status}</b>\n\nUsers will {'now' if not current else 'no longer'} receive notifications when new methods are added.", reply_markup=admin_panel_menu())

# =========================
# 📊 LEADERBOARD (ADMIN)
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 Leaderboard" and is_admin(m.from_user.id))
def admin_leaderboard(message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🏆 TOP POINTS", callback_data="admin_top_points"),
        InlineKeyboardButton("👥 TOP REFERRALS", callback_data="admin_top_refs"),
        InlineKeyboardButton("⭐ TOP EARNERS", callback_data="admin_top_earners")
    )
    bot.send_message(message.from_user.id, "📊 <b>ADMIN LEADERBOARD</b>\n\nSelect category:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "admin_top_points")
def admin_top_points_callback(call):
    users = list(users_col.find({}).sort("points", -1).limit(50))
    text = "🏆 <b>TOP 50 USERS BY POINTS</b> 🏆\n\n"
    for i, user in enumerate(users, 1):
        name = user.get("username") or f"User_{user['_id'][:6]}"
        points = user.get("points", 0)
        vip = "👑" if user.get("vip", False) else ""
        text += f"{i}. {vip} <code>{name}</code> → {points:,} 💎\n"
    bot.edit_message_text(text, call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "admin_top_refs")
def admin_top_refs_callback(call):
    users = list(users_col.find({}).sort("refs", -1).limit(50))
    text = "👥 <b>TOP 50 USERS BY REFERRALS</b> 👥\n\n"
    for i, user in enumerate(users, 1):
        name = user.get("username") or f"User_{user['_id'][:6]}"
        refs = user.get("refs", 0)
        vip = "👑" if user.get("vip", False) else ""
        text += f"{i}. {vip} <code>{name}</code> → {refs} referrals\n"
    bot.edit_message_text(text, call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "admin_top_earners")
def admin_top_earners_callback(call):
    users = list(users_col.find({}).sort("total_points_earned", -1).limit(50))
    text = "⭐ <b>TOP 50 USERS BY POINTS EARNED</b> ⭐\n\n"
    for i, user in enumerate(users, 1):
        name = user.get("username") or f"User_{user['_id'][:6]}"
        earned = user.get("total_points_earned", 0)
        vip = "👑" if user.get("vip", False) else ""
        text += f"{i}. {vip} <code>{name}</code> → {earned:,} 💎\n"
    bot.edit_message_text(text, call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

# =========================
# 🏃 FALLBACK HANDLER
# =========================
@bot.message_handler(func=lambda m: True)
def fallback_handler(message):
    if not validate_request(message):
        return
    
    uid = message.from_user.id
    
    if check_force_join(uid):
        send_force_join_message(uid)
        return
    
    # Check custom buttons
    cfg = get_cached_config()
    for btn in cfg.get("custom_buttons", []):
        if message.text == btn["text"]:
            if btn["type"] == "link":
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton("🔗 OPEN", url=btn["data"]))
                bot.send_message(uid, f"🔗 {btn['text']}", reply_markup=kb)
            elif btn["type"] == "folder":
                folder = fs.get_by_number(int(btn["data"]))
                if folder:
                    # Simulate opening folder
                    fake_call = type('obj', (object,), {
                        'from_user': message.from_user,
                        'message': message,
                        'data': f"open|{folder['cat']}|{folder['name']}|",
                        'id': message.message_id
                    })
                    open_folder_callback(fake_call)
            return
    
    points = User.points(uid)
    bot.send_message(uid, f"❌ Unknown command\n\n💰 Balance: {points} 💎", reply_markup=get_main_menu(uid))

# =========================
# 🚀 RUN BOT
# =========================
def run_bot():
    while True:
        try:
            print("=" * 60)
            print("🚀 ZEDOX BOT - COMPLETE ULTRA FAST VERSION 🚀")
            print("=" * 60)
            print(f"✅ Bot: @{bot.get_me().username}")
            print(f"👑 Owner: {ADMIN_ID}")
            print(f"💾 MongoDB: Connected")
            print(f"⚡ Cache: ENABLED (TTL: 60-120s)")
            print(f"📁 Subfolders: WORKING")
            print(f"🏷️ Auto Emojis: ENABLED")
            print(f"📄 Page Numbers: ENABLED (10 items/page)")
            print(f"🔔 New Method Notifications: {'ON' if get_cached_config().get('notify_new_methods', True) else 'OFF'}")
            print(f"💰 Points System: WORKING")
            print(f"👑 VIP System: WORKING")
            print(f"🎫 Code System: WORKING")
            print(f"📢 Broadcast: WORKING")
            print(f"👥 Multi-Admin: WORKING")
            print("=" * 60)
            print("🤖 BOT IS RUNNING...")
            print("=" * 60)
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    # Register all message handlers properly
    bot.register_message_handler(start_command, commands=["start"])
    bot.register_message_handler(my_wallet, func=lambda m: m.text == "💰 MY WALLET")
    bot.register_message_handler(profile_command, func=lambda m: m.text == "👤 PROFILE")
    bot.register_message_handler(my_purchases, func=lambda m: m.text == "🏆 MY PURCHASES")
    bot.register_message_handler(redeem_command, func=lambda m: m.text == "🎫 REDEEM CODE")
    bot.register_message_handler(referral_command, func=lambda m: m.text == "🎁 REFERRAL")
    bot.register_message_handler(my_id_command, func=lambda m: m.text == "🆔 MY ID")
    bot.register_message_handler(leaderboard_command, func=lambda m: m.text == "📊 LEADERBOARD")
    bot.register_message_handler(buy_vip_command, func=lambda m: m.text == "⭐ BUY VIP")
    bot.register_message_handler(show_category, func=lambda m: m.text in ["📂 FREE METHODS", "💎 VIP METHODS", "📱 PREMIUM APPS", "⚡ SERVICES"])
    
    # Admin handlers
    bot.register_message_handler(admin_panel, func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
    bot.register_message_handler(exit_admin, func=lambda m: m.text == "❌ Exit Admin" and is_admin(m.from_user.id))
    bot.register_message_handler(start_upload, func=lambda m: m.text in ["📦 Upload FREE", "💎 Upload VIP", "📱 Upload APPS", "⚡ Upload SERVICE"] and is_admin(m.from_user.id))
    bot.register_message_handler(create_subfolder, func=lambda m: m.text == "📁 Create Subfolder" and is_admin(m.from_user.id))
    bot.register_message_handler(delete_folder_start, func=lambda m: m.text == "🗑 Delete Folder" and is_admin(m.from_user.id))
    bot.register_message_handler(edit_price_start, func=lambda m: m.text == "✏️ Edit Price" and is_admin(m.from_user.id))
    bot.register_message_handler(edit_name_start, func=lambda m: m.text == "✏️ Edit Name" and is_admin(m.from_user.id))
    bot.register_message_handler(edit_content_start, func=lambda m: m.text == "📝 Edit Content" and is_admin(m.from_user.id))
    bot.register_message_handler(move_folder_start, func=lambda m: m.text == "🔀 Move Folder" and is_admin(m.from_user.id))
    bot.register_message_handler(add_vip_start, func=lambda m: m.text == "👑 Add VIP" and is_admin(m.from_user.id))
    bot.register_message_handler(remove_vip_start, func=lambda m: m.text == "👑 Remove VIP" and is_admin(m.from_user.id))
    bot.register_message_handler(give_points_start, func=lambda m: m.text == "💰 Give Points" and is_admin(m.from_user.id))
    bot.register_message_handler(generate_codes_start, func=lambda m: m.text == "🎫 Generate Codes" and is_admin(m.from_user.id))
    bot.register_message_handler(view_codes_admin, func=lambda m: m.text == "📊 View Codes" and is_admin(m.from_user.id))
    bot.register_message_handler(points_packages_menu, func=lambda m: m.text == "📦 Points Packages" and is_admin(m.from_user.id))
    bot.register_message_handler(admin_management, func=lambda m: m.text == "👥 Admin Management" and is_admin(m.from_user.id))
    bot.register_message_handler(set_contacts_menu, func=lambda m: m.text == "📞 Set Contacts" and is_admin(m.from_user.id))
    bot.register_message_handler(vip_settings_menu, func=lambda m: m.text == "⚙️ VIP Settings" and is_admin(m.from_user.id))
    bot.register_message_handler(payment_methods_menu, func=lambda m: m.text == "💳 Payment Methods" and is_admin(m.from_user.id))
    bot.register_message_handler(binance_settings_menu, func=lambda m: m.text == "🏦 Binance Settings" and is_admin(m.from_user.id))
    bot.register_message_handler(screenshot_toggle_menu, func=lambda m: m.text == "📸 Screenshot" and is_admin(m.from_user.id))
    bot.register_message_handler(add_custom_button_start, func=lambda m: m.text == "➕ Add Button" and is_admin(m.from_user.id))
    bot.register_message_handler(remove_custom_button_start, func=lambda m: m.text == "➖ Remove Button" and is_admin(m.from_user.id))
    bot.register_message_handler(add_force_channel, func=lambda m: m.text == "➕ Add Channel" and is_admin(m.from_user.id))
    bot.register_message_handler(remove_force_channel, func=lambda m: m.text == "➖ Remove Channel" and is_admin(m.from_user.id))
    bot.register_message_handler(general_settings_menu, func=lambda m: m.text == "⚙️ Settings" and is_admin(m.from_user.id))
    bot.register_message_handler(statistics_command, func=lambda m: m.text == "📊 Statistics" and is_admin(m.from_user.id))
    bot.register_message_handler(broadcast_start, func=lambda m: m.text == "📢 Broadcast" and is_admin(m.from_user.id))
    bot.register_message_handler(toggle_notify_admin, func=lambda m: m.text == "🔔 Toggle Notify" and is_admin(m.from_user.id))
    bot.register_message_handler(admin_leaderboard, func=lambda m: m.text == "📊 Leaderboard" and is_admin(m.from_user.id))
    
    run_bot()
