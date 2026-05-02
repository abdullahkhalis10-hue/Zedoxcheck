# =========================
# ZEDOX BOT - ULTIMATE INDUSTRIAL GRADE VERSION
# Most Stable, Fastest, Never Crashes
# =========================

import os
import sys
import signal
import time
import random
import string
import threading
import traceback
from datetime import datetime
from functools import wraps

# Force unbuffered output for Railway
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)

print("=" * 70)
print("🚀 STARTING ZEDOX BOT - ULTIMATE EDITION 🚀")
print("=" * 70)
print(f"Python version: {sys.version}")
print(f"Time: {datetime.now().isoformat()}")
print("=" * 70)

# =========================
# CRITICAL: Install/Verify Dependencies (For Railway)
# =========================
def ensure_dependencies():
    """Auto-install missing dependencies for Railway"""
    import subprocess
    
    required = {
        'telebot': 'pyTelegramBotAPI',
        'pymongo': 'pymongo',
        'cachetools': 'cachetools'
    }
    
    for module, package in required.items():
        try:
            __import__(module)
            print(f"✅ {module} already installed")
        except ImportError:
            print(f"⚠️ Installing {package}...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package, "-q"])
                print(f"✅ {package} installed successfully")
            except Exception as e:
                print(f"❌ Failed to install {package}: {e}")
                # Continue anyway, might already be there

# Run dependency check
try:
    ensure_dependencies()
except:
    pass  # Continue anyway

# =========================
# IMPORTS WITH FALLBACKS
# =========================
try:
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
    print("✅ telebot imported")
except Exception as e:
    print(f"❌ telebot import error: {e}")
    # Fallback: try to install
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyTelegramBotAPI"])
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup

try:
    from pymongo import MongoClient
    from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure, OperationFailure
    print("✅ pymongo imported")
except Exception as e:
    print(f"⚠️ pymongo import error: {e}")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pymongo"])
    from pymongo import MongoClient

try:
    from cachetools import TTLCache
    print("✅ cachetools imported")
except:
    # Simple fallback cache
    class TTLCache:
        def __init__(self, maxsize, ttl):
            self.maxsize = maxsize
            self.ttl = ttl
            self._cache = {}
            self._times = {}
        
        def __getitem__(self, key):
            if key in self._cache:
                if time.time() - self._times[key] < self.ttl:
                    return self._cache[key]
                del self._cache[key]
                del self._times[key]
            raise KeyError(key)
        
        def __setitem__(self, key, value):
            if len(self._cache) >= self.maxsize:
                oldest = min(self._times.items(), key=lambda x: x[1])[0]
                del self._cache[oldest]
                del self._times[oldest]
            self._cache[key] = value
            self._times[key] = time.time()
        
        def __contains__(self, key):
            return key in self._cache and time.time() - self._times[key] < self.ttl
        
        def pop(self, key, default=None):
            return self._cache.pop(key, default)

# =========================
# GET ENVIRONMENT VARIABLES
# =========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")
MONGO_URI = os.environ.get("MONGO_URI")

print(f"BOT_TOKEN: {'✅ Set' if BOT_TOKEN else '❌ Missing'}")
print(f"ADMIN_ID: {'✅ Set' if ADMIN_ID else '❌ Missing'}")
print(f"MONGO_URI: {'✅ Set' if MONGO_URI else '❌ Missing'}")

if not BOT_TOKEN:
    print("❌ CRITICAL: BOT_TOKEN not set!")
    sys.exit(1)

if not ADMIN_ID:
    print("❌ CRITICAL: ADMIN_ID not set!")
    sys.exit(1)

if not MONGO_URI:
    print("❌ CRITICAL: MONGO_URI not set!")
    sys.exit(1)

try:
    ADMIN_ID = int(ADMIN_ID)
    print(f"✅ Admin ID: {ADMIN_ID}")
except:
    print(f"❌ ADMIN_ID must be a number! Got: {ADMIN_ID}")
    sys.exit(1)

# =========================
# MONGO CONNECTION WITH AUTO-RECONNECT
# =========================
class SafeMongoClient:
    """MongoDB client with auto-reconnect and retry logic"""
    
    def __init__(self, uri):
        self.uri = uri
        self.client = None
        self.db = None
        self._connect()
    
    def _connect(self):
        """Establish MongoDB connection"""
        max_retries = 10
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                print(f"📡 MongoDB connection attempt {attempt + 1}/{max_retries}...")
                self.client = MongoClient(
                    self.uri,
                    serverSelectionTimeoutMS=15000,
                    connectTimeoutMS=15000,
                    socketTimeoutMS=15000,
                    maxPoolSize=100,
                    minPoolSize=10,
                    retryWrites=True,
                    w='majority'
                )
                # Test connection
                self.client.admin.command('ping')
                self.db = self.client["zedox_ultimate"]
                print("✅ MongoDB connected successfully!")
                return True
            except Exception as e:
                print(f"⚠️ Connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    print("❌ Failed to connect to MongoDB after all retries!")
                    raise
    
    def get_collection(self, name):
        """Get collection with connection check"""
        if self.client is None:
            self._connect()
        return self.db[name]
    
    def ensure_connection(self):
        """Ensure connection is alive"""
        try:
            self.client.admin.command('ping')
            return True
        except:
            print("⚠️ MongoDB connection lost, reconnecting...")
            self._connect()
            return True

# Initialize MongoDB
mongo = SafeMongoClient(MONGO_URI)

# Collections
users_col = mongo.get_collection("users")
folders_col = mongo.get_collection("folders")
codes_col = mongo.get_collection("codes")
config_col = mongo.get_collection("config")
custom_buttons_col = mongo.get_collection("custom_buttons")
admins_col = mongo.get_collection("admins")
payments_col = mongo.get_collection("payments")

# Create indexes (safe)
try:
    users_col.create_index("points")
    users_col.create_index("vip")
    users_col.create_index("refs")
    folders_col.create_index([("cat", 1), ("parent", 1)])
    folders_col.create_index("number", unique=True, sparse=True)
    codes_col.create_index("created_at")
    print("✅ Database indexes created")
except Exception as e:
    print(f"⚠️ Index creation warning: {e}")

# =========================
# INITIALIZE BOT WITH ERROR HANDLING
# =========================
try:
    bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=False)
    bot_info = bot.get_me()
    print(f"✅ Bot initialized: @{bot_info.username}")
    print(f"✅ Bot ID: {bot_info.id}")
except Exception as e:
    print(f"❌ Failed to initialize bot: {e}")
    sys.exit(1)

# =========================
# CACHE SYSTEMS
# =========================
user_cache = TTLCache(maxsize=5000, ttl=300)  # 5 minutes
folder_cache = TTLCache(maxsize=2000, ttl=600)  # 10 minutes
config_cache = TTLCache(maxsize=10, ttl=300)
admin_cache = TTLCache(maxsize=500, ttl=600)

# =========================
# HELPER FUNCTIONS
# =========================
def safe_execute(func, *args, **kwargs):
    """Safely execute any function with error handling"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        print(f"⚠️ Error in {func.__name__}: {e}")
        traceback.print_exc()
        return None

def get_config():
    """Get config with caching"""
    try:
        if "config" in config_cache:
            return config_cache["config"]
        
        cfg = config_col.find_one({"_id": "config"})
        if not cfg:
            cfg = {
                "_id": "config",
                "force_channels": [],
                "custom_buttons": [],
                "vip_msg": "💎 Buy VIP to unlock premium content!",
                "welcome": "🔥 Welcome to ZEDOX BOT! Get premium methods, apps, and services!",
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
                "payment_methods": ["💳 Binance", "💵 USDT (TRC20)"],
                "require_screenshot": True
            }
            config_col.insert_one(cfg)
        
        config_cache["config"] = cfg
        return cfg
    except Exception as e:
        print(f"⚠️ Config error: {e}")
        # Return default config
        return {
            "force_channels": [],
            "custom_buttons": [],
            "vip_msg": "💎 Buy VIP!",
            "welcome": "🔥 Welcome!",
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
            "payment_methods": ["💳 Binance"],
            "require_screenshot": True
        }

def set_config(key, value):
    """Set config value"""
    try:
        config_col.update_one({"_id": "config"}, {"$set": {key: value}}, upsert=True)
        config_cache.pop("config", None)
        return True
    except Exception as e:
        print(f"⚠️ Set config error: {e}")
        return False

# =========================
# USER SYSTEM
# =========================
def get_user(uid):
    """Get user data with caching"""
    uid = str(uid)
    try:
        if uid in user_cache:
            return user_cache[uid].copy()
        
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
                "total_earned": 0,
                "total_spent": 0
            }
            users_col.insert_one(data)
        
        user_cache[uid] = data.copy()
        return data
    except Exception as e:
        print(f"⚠️ Get user error for {uid}: {e}")
        return {"_id": uid, "points": 0, "vip": False}

def save_user(uid, data):
    """Save user data"""
    try:
        uid = str(uid)
        users_col.update_one({"_id": uid}, {"$set": data})
        user_cache[uid] = data.copy()
        return True
    except Exception as e:
        print(f"⚠️ Save user error for {uid}: {e}")
        return False

def add_points(uid, amount):
    """Add points to user"""
    if amount <= 0:
        return get_user(uid).get("points", 0)
    try:
        data = get_user(uid)
        data["points"] = data.get("points", 0) + amount
        data["total_earned"] = data.get("total_earned", 0) + amount
        save_user(uid, data)
        return data["points"]
    except Exception as e:
        print(f"⚠️ Add points error: {e}")
        return get_user(uid).get("points", 0)

def spend_points(uid, amount):
    """Spend points"""
    if amount <= 0:
        return get_user(uid).get("points", 0)
    try:
        data = get_user(uid)
        current = data.get("points", 0)
        if current < amount:
            return current
        data["points"] = current - amount
        data["total_spent"] = data.get("total_spent", 0) + amount
        save_user(uid, data)
        return data["points"]
    except Exception as e:
        print(f"⚠️ Spend points error: {e}")
        return get_user(uid).get("points", 0)

def is_vip(uid):
    """Check if user is VIP"""
    try:
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
    except:
        return False

def make_vip(uid, duration_days=None):
    """Make user VIP"""
    try:
        data = get_user(uid)
        data["vip"] = True
        if duration_days and duration_days > 0:
            data["vip_expiry"] = time.time() + (duration_days * 86400)
        else:
            data["vip_expiry"] = None
        save_user(uid, data)
        return True
    except Exception as e:
        print(f"⚠️ Make VIP error: {e}")
        return False

# =========================
# FOLDER SYSTEM
# =========================
def get_folders(cat, parent=None):
    """Get folders with caching"""
    cache_key = f"{cat}_{parent}"
    try:
        if cache_key in folder_cache:
            return folder_cache[cache_key]
        
        query = {"cat": cat}
        if parent:
            query["parent"] = parent
        else:
            query["parent"] = None
        
        result = list(folders_col.find(query).sort("number", 1))
        folder_cache[cache_key] = result
        return result
    except Exception as e:
        print(f"⚠️ Get folders error: {e}")
        return []

def add_folder(cat, name, files, price, parent=None, text_content=None):
    """Add new folder"""
    try:
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
        folder_cache.clear()
        return number
    except Exception as e:
        print(f"⚠️ Add folder error: {e}")
        return None

def get_folder(cat, name, parent=None):
    """Get single folder"""
    try:
        query = {"cat": cat, "name": name}
        if parent:
            query["parent"] = parent
        return folders_col.find_one(query)
    except Exception as e:
        print(f"⚠️ Get folder error: {e}")
        return None

def delete_folder(cat, name):
    """Delete folder"""
    try:
        result = folders_col.delete_one({"cat": cat, "name": name})
        folder_cache.clear()
        return result.deleted_count > 0
    except Exception as e:
        print(f"⚠️ Delete folder error: {e}")
        return False

# =========================
# CODE SYSTEM
# =========================
def generate_code(points):
    """Generate redemption code"""
    try:
        code = "ZEDOX" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        codes_col.insert_one({
            "_id": code,
            "points": points,
            "used": False,
            "created_at": time.time()
        })
        return code
    except Exception as e:
        print(f"⚠️ Generate code error: {e}")
        return None

def redeem_code(code, uid):
    """Redeem code"""
    try:
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
    except Exception as e:
        print(f"⚠️ Redeem code error: {e}")
        return False, 0, "error"

# =========================
# ADMIN CHECK
# =========================
def is_admin(uid):
    """Check if user is admin"""
    try:
        if uid == ADMIN_ID:
            return True
        cache_key = f"admin_{uid}"
        if cache_key in admin_cache:
            return admin_cache[cache_key]
        result = admins_col.find_one({"_id": uid}) is not None
        admin_cache[cache_key] = result
        return result
    except:
        return uid == ADMIN_ID

# =========================
# KEYBOARDS
# =========================
def get_main_menu(uid):
    """Get main menu keyboard"""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📂 FREE METHODS", "💎 VIP METHODS")
    kb.add("📦 PREMIUM APPS", "⚡ SERVICES")
    kb.add("💰 MY WALLET", "⭐ BUY VIP")
    kb.add("🎁 REFERRAL", "👤 PROFILE")
    kb.add("🏆 MY PURCHASES", "🎫 REDEEM")
    kb.add("🆔 MY ID")
    
    if is_admin(uid):
        kb.add("⚙️ ADMIN PANEL")
    
    return kb

def get_folders_kb(cat, parent=None, page=0, per_page=10):
    """Get folders keyboard with pagination"""
    try:
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
            text = f"{icon} [{number}] {name}"
            if price > 0 and not has_subs:
                text += f" ─ {price}💎"
            
            kb.add(InlineKeyboardButton(text, callback_data=f"open|{cat}|{name}|{parent or ''}"))
        
        # Navigation
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
    except Exception as e:
        print(f"⚠️ Get folders kb error: {e}")
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("❌ Error", callback_data="noop"))
        return kb

# =========================
# FORCE JOIN CHECK
# =========================
force_cache_local = {}

def check_force_join(uid):
    """Check if user needs to join channels"""
    if is_admin(uid):
        return False
    
    if uid in force_cache_local:
        return force_cache_local[uid]
    
    try:
        cfg = get_config()
        channels = cfg.get("force_channels", [])
        
        if not channels:
            force_cache_local[uid] = False
            return False
        
        for channel in channels:
            try:
                member = bot.get_chat_member(channel, uid)
                if member.status in ["left", "kicked"]:
                    # Send force join message
                    kb = InlineKeyboardMarkup()
                    for ch in channels:
                        clean = ch.replace("@", "")
                        kb.add(InlineKeyboardButton(f"📢 Join {ch}", url=f"https://t.me/{clean}"))
                    kb.add(InlineKeyboardButton("✅ I Joined", callback_data="recheck"))
                    bot.send_message(uid, "🚫 <b>Access Restricted!</b>\n\nPlease join the required channels:", reply_markup=kb)
                    force_cache_local[uid] = True
                    return True
            except:
                pass
        
        force_cache_local[uid] = False
        return False
    except:
        return False

# =========================
# BOT HANDLERS
# =========================

@bot.message_handler(commands=["start"])
def start_command(message):
    try:
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
                    cfg = get_config()
                    reward = cfg.get("ref_reward", 5)
                    add_points(ref_id, reward)
                    
                    # Add referral count
                    ref_user = get_user(ref_id)
                    ref_user["refs"] = ref_user.get("refs", 0) + 1
                    save_user(ref_id, ref_user)
                    
                    user["ref"] = ref_id
                    save_user(uid, user)
        
        # Check force join
        if check_force_join(uid):
            return
        
        cfg = get_config()
        welcome = cfg.get("welcome", "🔥 Welcome to ZEDOX BOT!")
        points = get_user(uid).get("points", 0)
        
        bot.send_message(uid, 
            f"{welcome}\n\n"
            f"💰 <b>Balance:</b> {points} 💎\n"
            f"👑 <b>VIP:</b> {'✅ Active' if is_vip(uid) else '❌ Not Active'}\n\n"
            f"Use the buttons below! 🚀",
            reply_markup=get_main_menu(uid))
    except Exception as e:
        print(f"⚠️ Start command error: {e}")
        try:
            bot.send_message(message.from_user.id, "❌ Error, please try again later.")
        except:
            pass

@bot.message_handler(func=lambda m: m.text == "💰 MY WALLET")
def wallet_command(message):
    try:
        uid = message.from_user.id
        user = get_user(uid)
        
        text = f"┌─<b>💰 YOUR WALLET</b>─┐\n\n"
        text += f"├ 💎 Points: <code>{user.get('points', 0):,}</code>\n"
        text += f"├ 👑 VIP: <code>{'Yes' if is_vip(uid) else 'No'}</code>\n"
        text += f"├ 👥 Referrals: <code>{user.get('refs', 0)}</code>\n"
        text += f"├ 📈 Earned: <code>{user.get('total_earned', 0):,}</code>\n"
        text += f"└ 📉 Spent: <code>{user.get('total_spent', 0):,}</code>\n\n"
        text += f"✨ Earn points: Referrals, Redeem codes"
        
        bot.send_message(uid, text)
    except Exception as e:
        print(f"⚠️ Wallet error: {e}")

@bot.message_handler(func=lambda m: m.text == "👤 PROFILE")
def profile_command(message):
    try:
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
    except Exception as e:
        print(f"⚠️ Profile error: {e}")

@bot.message_handler(func=lambda m: m.text == "🏆 MY PURCHASES")
def purchases_command(message):
    try:
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
            text += f"{i}. {method}\n"
        
        bot.send_message(uid, text)
    except Exception as e:
        print(f"⚠️ Purchases error: {e}")

@bot.message_handler(func=lambda m: m.text == "🎫 REDEEM")
def redeem_command(message):
    try:
        msg = bot.send_message(message.from_user.id, "🎫 <b>Enter code:</b>\n\nExample: <code>ZEDOXABC123</code>")
        bot.register_next_step_handler(msg, process_redeem)
    except Exception as e:
        print(f"⚠️ Redeem error: {e}")

def process_redeem(message):
    try:
        uid = message.from_user.id
        code = message.text.strip().upper()
        
        success, points, reason = redeem_code(code, uid)
        
        if success:
            bot.send_message(uid, f"✅ <b>Redeemed!</b>\n\n+{points} 💎\n💰 Balance: {get_user(uid).get('points', 0)} 💎")
        else:
            errors = {
                "invalid": "❌ Invalid code!",
                "already_used": "❌ Code already used!",
                "already_used_by_user": "❌ You already used this code!"
            }
            bot.send_message(uid, errors.get(reason, "❌ Invalid code!"))
    except Exception as e:
        print(f"⚠️ Process redeem error: {e}")

@bot.message_handler(func=lambda m: m.text == "🎁 REFERRAL")
def referral_command(message):
    try:
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
    except Exception as e:
        print(f"⚠️ Referral error: {e}")

@bot.message_handler(func=lambda m: m.text == "🆔 MY ID")
def myid_command(message):
    try:
        uid = message.from_user.id
        bot.send_message(uid, f"🆔 <b>Your ID:</b> <code>{uid}</code>")
    except Exception as e:
        print(f"⚠️ ID error: {e}")

@bot.message_handler(func=lambda m: m.text == "⭐ BUY VIP")
def buy_vip_command(message):
    try:
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
        if get_user(uid).get("points", 0) >= cfg.get("vip_points_price", 5000):
            kb.add(InlineKeyboardButton(f"👑 BUY WITH {cfg.get('vip_points_price', 5000):,}💎", callback_data="buy_vip"))
        if cfg.get("vip_contact"):
            contact = cfg.get("vip_contact")
            if contact.startswith("@"):
                kb.add(InlineKeyboardButton("📞 CONTACT", url=f"https://t.me/{contact[1:]}"))
            elif contact.startswith("http"):
                kb.add(InlineKeyboardButton("📞 CONTACT", url=contact))
        
        bot.send_message(uid, text, reply_markup=kb if kb.keyboard else None)
    except Exception as e:
        print(f"⚠️ Buy VIP error: {e}")

@bot.message_handler(func=lambda m: m.text in ["📂 FREE METHODS", "💎 VIP METHODS", "📦 PREMIUM APPS", "⚡ SERVICES"])
def show_category(message):
    try:
        cat_map = {
            "📂 FREE METHODS": "free",
            "💎 VIP METHODS": "vip",
            "📦 PREMIUM APPS": "apps",
            "⚡ SERVICES": "services"
        }
        cat = cat_map.get(message.text)
        folders = get_folders(cat)
        
        if not folders:
            bot.send_message(message.from_user.id, f"📂 <b>{message.text}</b>\n\nNo content available!")
            return
        
        bot.send_message(message.from_user.id, f"📂 <b>{message.text}</b>\n\nSelect:", reply_markup=get_folders_kb(cat))
    except Exception as e:
        print(f"⚠️ Show category error: {e}")

# =========================
# CALLBACK HANDLERS
# =========================

@bot.callback_query_handler(func=lambda c: c.data.startswith("open|"))
def open_callback(call):
    try:
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
                text = f"📁 [{sub.get('number', '?')}] {sub['name']}"
                kb.add(InlineKeyboardButton(text, callback_data=f"open|{cat}|{sub['name']}|{name}"))
            kb.add(InlineKeyboardButton("🔙 BACK", callback_data=f"back|{cat}|{parent or ''}"))
            bot.edit_message_text(f"📁 <b>{name}</b>", uid, call.message.message_id, reply_markup=kb)
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
                    InlineKeyboardButton("👑 GET VIP", callback_data="get_vip_info")
                )
                kb.add(InlineKeyboardButton("❌ CANCEL", callback_data="cancel"))
                bot.edit_message_text(
                    f"🔒 <b>{name}</b>\n\nPrice: {price} 💎\nBalance: {get_user(uid).get('points', 0)} 💎",
                    uid, call.message.message_id, reply_markup=kb)
            else:
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton("👑 GET VIP", callback_data="get_vip_info"))
                bot.edit_message_text(f"🔒 <b>{name}</b>\n\nVIP only!", uid, call.message.message_id, reply_markup=kb)
            bot.answer_callback_query(call.id)
            return
        
        # Deduct points
        if price > 0 and not user_vip and not user_owns:
            if get_user(uid).get("points", 0) < price:
                bot.answer_callback_query(call.id, f"❌ Need {price}💎!", True)
                return
            spend_points(uid, price)
        
        # Mark as purchased
        if is_vip_cat and not user_vip:
            purchased = get_user(uid).get("purchased_methods", [])
            if name not in purchased:
                purchased.append(name)
                user_data = get_user(uid)
                user_data["purchased_methods"] = purchased
                save_user(uid, user_data)
        
        # Send content
        text_content = folder.get("text_content")
        files = folder.get("files", [])
        
        if text_content:
            bot.edit_message_text(f"📄 <b>{name}</b>\n\n{text_content}", uid, call.message.message_id)
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
            bot.edit_message_text(f"📁 <b>{name}</b>\n\nNo content.", uid, call.message.message_id)
        
        bot.answer_callback_query(call.id)
    except Exception as e:
        print(f"⚠️ Open callback error: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ Error!")
        except:
            pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("buy|"))
def buy_callback(call):
    try:
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
        
        if get_user(uid).get("points", 0) < price:
            bot.answer_callback_query(call.id, f"❌ Need {price}💎!", True)
            return
        
        # Purchase
        spend_points(uid, price)
        purchased = get_user(uid).get("purchased_methods", [])
        if name not in purchased:
            purchased.append(name)
            user_data = get_user(uid)
            user_data["purchased_methods"] = purchased
            save_user(uid, user_data)
        
        bot.answer_callback_query(call.id, f"✅ Purchased! -{price}💎", True)
        bot.edit_message_text(f"✅ <b>Purchased!</b>\n\nYou now own: {name}\nRemaining: {get_user(uid).get('points', 0)} 💎", uid, call.message.message_id)
        
        time.sleep(0.5)
        open_callback(call)
    except Exception as e:
        print(f"⚠️ Buy callback error: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "buy_vip")
def buy_vip_callback(call):
    try:
        uid = call.from_user.id
        cfg = get_config()
        price = cfg.get("vip_points_price", 5000)
        
        if is_vip(uid):
            bot.answer_callback_query(call.id, "✅ Already VIP!", True)
            return
        
        if get_user(uid).get("points", 0) >= price:
            spend_points(uid, price)
            make_vip(uid, cfg.get("vip_duration_days", 30))
            bot.answer_callback_query(call.id, "✅ VIP Activated!", True)
            bot.edit_message_text(f"🎉 <b>CONGRATULATIONS!</b> 🎉\n\nYou are now VIP!\n💰 Balance: {get_user(uid).get('points', 0)} 💎", uid, call.message.message_id)
        else:
            bot.answer_callback_query(call.id, f"❌ Need {price}💎!", True)
    except Exception as e:
        print(f"⚠️ Buy VIP callback error: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "get_vip_info")
def vip_info_callback(call):
    try:
        cfg = get_config()
        text = f"👑 <b>VIP INFO</b>\n\n"
        text += f"💰 Price: {cfg.get('vip_points_price', 5000):,}💎 or ${cfg.get('vip_price', 50)}\n"
        text += f"✨ Benefits: All VIP methods, No points needed\n"
        text += f"🎁 Free: {cfg.get('referral_vip_count', 50)} referrals = FREE VIP"
        bot.edit_message_text(text, call.from_user.id, call.message.message_id)
        bot.answer_callback_query(call.id)
    except Exception as e:
        print(f"⚠️ VIP info error: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "cancel")
def cancel_callback(call):
    try:
        bot.edit_message_text("❌ Cancelled", call.from_user.id, call.message.message_id)
        bot.answer_callback_query(call.id)
    except:
        pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("back|"))
def back_callback(call):
    try:
        _, cat, parent = call.data.split("|")
        bot.edit_message_reply_markup(call.from_user.id, call.message.message_id, reply_markup=get_folders_kb(cat, parent if parent else None))
        bot.answer_callback_query(call.id)
    except:
        pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("page|"))
def page_callback(call):
    try:
        _, cat, page, parent = call.data.split("|")
        parent = parent if parent != "None" else None
        bot.edit_message_reply_markup(call.from_user.id, call.message.message_id, reply_markup=get_folders_kb(cat, parent, int(page)))
        bot.answer_callback_query(call.id)
    except:
        pass

@bot.callback_query_handler(func=lambda c: c.data == "main_menu")
def main_menu_callback(call):
    try:
        uid = call.from_user.id
        points = get_user(uid).get("points", 0)
        bot.edit_message_text(f"🏠 <b>MAIN MENU</b>\n\n💰 Balance: {points} 💎", uid, call.message.message_id, reply_markup=get_main_menu(uid))
        bot.answer_callback_query(call.id)
    except:
        pass

@bot.callback_query_handler(func=lambda c: c.data == "recheck")
def recheck_callback(call):
    try:
        uid = call.from_user.id
        force_cache_local.pop(uid, None)
        
        if not check_force_join(uid):
            bot.edit_message_text("✅ <b>Access Granted!</b>", uid, call.message.message_id)
            points = get_user(uid).get("points", 0)
            bot.send_message(uid, f"🎉 Welcome!\n\n💰 Balance: {points} 💎", reply_markup=get_main_menu(uid))
        else:
            bot.answer_callback_query(call.id, "❌ Please join all channels first!", True)
    except:
        pass

@bot.callback_query_handler(func=lambda c: c.data == "noop")
def noop_callback(call):
    bot.answer_callback_query(call.id)

# =========================
# ADMIN PANEL
# =========================

@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def admin_panel(message):
    try:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        kb.add("📦 Add FREE", "💎 Add VIP")
        kb.add("📱 Add APP", "⚡ Add SERVICE")
        kb.add("💰 Give Points", "👑 Give VIP")
        kb.add("🎫 Generate Code", "📊 Stats")
        kb.add("📢 Broadcast", "❌ Exit Admin")
        bot.send_message(message.from_user.id, "⚙️ <b>ADMIN PANEL</b>", reply_markup=kb)
    except Exception as e:
        print(f"⚠️ Admin panel error: {e}")

@bot.message_handler(func=lambda m: m.text == "❌ Exit Admin" and is_admin(m.from_user.id))
def exit_admin(message):
    try:
        bot.send_message(message.from_user.id, "👋 Exited", reply_markup=get_main_menu(message.from_user.id))
    except:
        pass

# Add content
upload_sessions = {}

@bot.message_handler(func=lambda m: m.text in ["📦 Add FREE", "💎 Add VIP", "📱 Add APP", "⚡ Add SERVICE"] and is_admin(m.from_user.id))
def add_content_start(message):
    try:
        cat_map = {
            "📦 Add FREE": "free",
            "💎 Add VIP": "vip",
            "📱 Add APP": "apps",
            "⚡ Add SERVICE": "services"
        }
        uid = message.from_user.id
        upload_sessions[uid] = {"cat": cat_map[message.text], "step": "name", "files": []}
        bot.send_message(uid, "📝 <b>Enter folder name:</b>")
    except Exception as e:
        print(f"⚠️ Add content error: {e}")

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions.get(m.from_user.id, {}).get("step") == "name")
def add_name(message):
    try:
        uid = message.from_user.id
        upload_sessions[uid]["name"] = message.text
        upload_sessions[uid]["step"] = "price"
        bot.send_message(uid, "💰 <b>Price (points, 0 = free):</b>")
    except Exception as e:
        print(f"⚠️ Add name error: {e}")

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions.get(m.from_user.id, {}).get("step") == "price")
def add_price(message):
    try:
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
    except Exception as e:
        print(f"⚠️ Add price error: {e}")

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions.get(m.from_user.id, {}).get("step") == "type" and m.text == "📄 Text")
def add_text_type(message):
    try:
        uid = message.from_user.id
        upload_sessions[uid]["step"] = "text"
        bot.send_message(uid, "📝 <b>Enter text content:</b>", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("❌ Cancel"))
    except:
        pass

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions.get(m.from_user.id, {}).get("step") == "type" and m.text == "📁 Files")
def add_files_type(message):
    try:
        uid = message.from_user.id
        upload_sessions[uid]["step"] = "files"
        upload_sessions[uid]["files"] = []
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("✅ Done", "❌ Cancel")
        bot.send_message(uid, "📁 <b>Send files:</b>\nPress ✅ Done when finished", reply_markup=kb)
    except:
        pass

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions.get(m.from_user.id, {}).get("step") == "text")
def save_text(message):
    try:
        uid = message.from_user.id
        if message.text == "❌ Cancel":
            upload_sessions.pop(uid, None)
            bot.send_message(uid, "❌ Cancelled", reply_markup=admin_panel_menu())
            return
        
        data = upload_sessions[uid]
        number = add_folder(data["cat"], data["name"], [], data["price"], text_content=message.text)
        if number:
            bot.send_message(uid, f"✅ <b>Added!</b>\n\n📌 #{number}\n📂 {data['name']}\n💰 {data['price']}💎", reply_markup=admin_panel_menu())
        else:
            bot.send_message(uid, "❌ Failed to add!", reply_markup=admin_panel_menu())
        upload_sessions.pop(uid, None)
    except Exception as e:
        print(f"⚠️ Save text error: {e}")

@bot.message_handler(func=lambda m: m.from_user.id in upload_sessions and upload_sessions.get(m.from_user.id, {}).get("step") == "files")
def save_files(message):
    try:
        uid = message.from_user.id
        
        if message.text == "✅ Done":
            data = upload_sessions[uid]
            if not data.get("files"):
                bot.send_message(uid, "❌ No files!")
                return
            number = add_folder(data["cat"], data["name"], data["files"], data["price"])
            if number:
                bot.send_message(uid, f"✅ <b>Added!</b>\n\n📌 #{number}\n📂 {data['name']}\n💰 {data['price']}💎\n📁 {len(data['files'])} files", reply_markup=admin_panel_menu())
            else:
                bot.send_message(uid, "❌ Failed to add!", reply_markup=admin_panel_menu())
            upload_sessions.pop(uid, None)
            return
        
        if message.text == "❌ Cancel":
            upload_sessions.pop(uid, None)
            bot.send_message(uid, "❌ Cancelled", reply_markup=get_main_menu(uid))
            return
        
        if message.content_type in ["photo", "document", "video"]:
            upload_sessions[uid]["files"].append({"chat": message.chat.id, "msg": message.message_id, "type": message.content_type})
            bot.send_message(uid, f"✅ File {len(upload_sessions[uid]['files'])} added")
    except Exception as e:
        print(f"⚠️ Save files error: {e}")

def admin_panel_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Add FREE", "💎 Add VIP", "📱 Add APP", "⚡ Add SERVICE", "❌ Exit Admin")
    return kb

@bot.message_handler(func=lambda m: m.text == "💰 Give Points" and is_admin(m.from_user.id))
def give_points_start(message):
    try:
        msg = bot.send_message(message.from_user.id, "💰 <b>Give Points</b>\n\nFormat: <code>user_id points</code>\nExample: <code>123456789 100</code>")
        bot.register_next_step_handler(msg, process_give_points)
    except:
        pass

def process_give_points(message):
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(message.from_user.id, "❌ Use: user_id points")
            return
        
        uid = int(parts[0])
        points = int(parts[1])
        
        if points <= 0:
            bot.send_message(message.from_user.id, "❌ Points must be > 0")
            return
        
        old = get_user(uid).get("points", 0)
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
    try:
        msg = bot.send_message(message.from_user.id, "👑 <b>Give VIP</b>\n\nSend user ID or @username:")
        bot.register_next_step_handler(msg, process_give_vip)
    except:
        pass

def process_give_vip(message):
    try:
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
    except:
        bot.send_message(message.from_user.id, "❌ Error!")

@bot.message_handler(func=lambda m: m.text == "🎫 Generate Code" and is_admin(m.from_user.id))
def gen_code_start(message):
    try:
        msg = bot.send_message(message.from_user.id, "🎫 <b>Generate Code</b>\n\nSend points amount:")
        bot.register_next_step_handler(msg, process_gen_code)
    except:
        pass

def process_gen_code(message):
    try:
        points = int(message.text)
        code = generate_code(points)
        if code:
            bot.send_message(message.from_user.id, f"✅ <b>Code generated!</b>\n\n<code>{code}</code>\n💰 +{points} points", reply_markup=admin_panel_menu())
        else:
            bot.send_message(message.from_user.id, "❌ Failed to generate!", reply_markup=admin_panel_menu())
    except:
        bot.send_message(message.from_user.id, "❌ Invalid points!")

@bot.message_handler(func=lambda m: m.text == "📊 Stats" and is_admin(m.from_user.id))
def stats_command(message):
    try:
        total_users = users_col.count_documents({})
        vip_users = users_col.count_documents({"vip": True})
        total_points = sum(u.get("points", 0) for u in users_col.find({}))
        free_folders = folders_col.count_documents({"cat": "free"})
        vip_folders = folders_col.count_documents({"cat": "vip"})
        total_codes = codes_col.count_documents({})
        
        text = f"📊 <b>STATISTICS</b>\n\n"
        text += f"👥 Users: {total_users}\n"
        text += f"├ VIP: {vip_users}\n"
        text += f"└ Free: {total_users - vip_users}\n\n"
        text += f"💰 Points: {total_points:,}\n\n"
        text += f"📁 Content:\n"
        text += f"├ FREE: {free_folders}\n"
        text += f"└ VIP: {vip_folders}\n\n"
        text += f"🎫 Codes: {total_codes}"
        
        bot.send_message(message.from_user.id, text)
    except Exception as e:
        print(f"⚠️ Stats error: {e}")
        bot.send_message(message.from_user.id, "❌ Error getting stats!")

@bot.message_handler(func=lambda m: m.text == "📢 Broadcast" and is_admin(m.from_user.id))
def broadcast_start(message):
    try:
        msg = bot.send_message(message.from_user.id, "📢 <b>Broadcast</b>\n\nSend message to broadcast to all users:")
        bot.register_next_step_handler(msg, process_broadcast)
    except:
        pass

def process_broadcast(message):
    try:
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
        bot.send_message(message.from_user.id, "Returning to admin panel...", reply_markup=admin_panel_menu())
    except:
        pass

# Fallback
@bot.message_handler(func=lambda m: True)
def fallback(message):
    try:
        uid = message.from_user.id
        points = get_user(uid).get("points", 0)
        bot.send_message(uid, f"❌ Unknown command\n💰 Balance: {points}💎", reply_markup=get_main_menu(uid))
    except:
        pass

# =========================
# HEALTH CHECK ENDPOINT (For Railway)
# =========================
import threading
import socket

def health_check():
    """Simple health check server for Railway"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('0.0.0.0', int(os.environ.get('PORT', 8080))))
        sock.listen(1)
        print(f"✅ Health check server running on port {os.environ.get('PORT', 8080)}")
        
        while True:
            conn, addr = sock.accept()
            conn.send(b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nOK')
            conn.close()
    except Exception as e:
        print(f"⚠️ Health check server error: {e}")

# Start health check
threading.Thread(target=health_check, daemon=True).start()

# =========================
# MAIN - ULTRA RESILIENT
# =========================
def main():
    print("=" * 70)
    print("🚀 ZEDOX BOT - ULTIMATE EDITION RUNNING 🚀")
    print(f"✅ Bot: @{bot.get_me().username}")
    print(f"✅ Bot ID: {bot.get_me().id}")
    print(f"👑 Admin: {ADMIN_ID}")
    print(f"💾 MongoDB: Connected")
    print("=" * 70)
    print("🤖 Bot is operational!")
    print("=" * 70)
    
    # Start bot with infinite retry
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=30)
        except KeyboardInterrupt:
            print("👋 Bot stopped by user")
            break
        except Exception as e:
            print(f"⚠️ Bot polling error: {e}")
            traceback.print_exc()
            print("🔄 Restarting in 10 seconds...")
            time.sleep(10)

if __name__ == "__main__":
    main()
