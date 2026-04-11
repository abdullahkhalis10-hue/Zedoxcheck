# =========================
# ZEDOX BOT - OPTIMIZED & FIXED
# Fast Performance + Fixed Code Generation
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
import logging
from pymongo import MongoClient, ASCENDING
from datetime import datetime, timedelta
from functools import wraps
from bson import ObjectId

# =========================
# 📋 LOGGING SETUP
# =========================
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =========================
# 🔧 CONFIGURATION
# =========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set!")

# =========================
# 🌐 MONGODB SETUP - OPTIMIZED
# =========================
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable not set!")

# Connection pool optimization
client = MongoClient(
    MONGO_URI, 
    maxPoolSize=50,
    minPoolSize=10,
    maxIdleTimeMS=30000,
    connectTimeoutMS=5000,
    socketTimeoutMS=5000,
    serverSelectionTimeoutMS=5000
)
db = client["zedox_bot"]

# Collections
users_col = db["users"]
folders_col = db["folders"]
codes_col = db["codes"]
config_col = db["config"]
admins_col = db["admins"]

# Drop problematic indexes and recreate properly
try:
    # Drop the problematic index if exists
    codes_col.drop_index("code_1")
except:
    pass

# Create proper indexes for performance
users_col.create_index([("points", ASCENDING)])
users_col.create_index([("is_vip", ASCENDING)])
users_col.create_index([("user_id", ASCENDING)])

folders_col.create_index([("category", ASCENDING), ("parent", ASCENDING)])
folders_col.create_index([("number", ASCENDING)], unique=True, sparse=True)

codes_col.create_index([("created_at", ASCENDING)])
codes_col.create_index([("expiry", ASCENDING)])

logger.info("✅ Database optimized with proper indexes!")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Cache for frequently accessed data
_config_cache = None
_config_cache_time = 0
CACHE_TTL = 60  # Cache for 60 seconds

# =========================
# 🔐 HELPER FUNCTIONS - OPTIMIZED
# =========================
def is_admin(user_id):
    """Check if user is admin (cached)"""
    if user_id == ADMIN_ID:
        return True
    return admins_col.find_one({"_id": user_id}) is not None

def get_config():
    """Get bot configuration with caching"""
    global _config_cache, _config_cache_time
    
    current_time = time.time()
    if _config_cache and (current_time - _config_cache_time) < CACHE_TTL:
        return _config_cache
    
    config = config_col.find_one({"_id": "main_config"})
    if not config:
        config = {
            "_id": "main_config",
            "force_channels": [],
            "custom_buttons": [],
            "vip_message": "💎 <b>VIP METHODS</b> 💎\n\nContact admin to get VIP access!",
            "welcome_message": "🔥 <b>Welcome to ZEDOX BOT!</b> 🔥\n\nUse the buttons below to explore!",
            "referral_reward": 5,
            "send_notifications": True,
            "next_folder_number": 1,
            "points_per_dollar": 100,
            "contact_username": None,
            "contact_link": None,
            "vip_contact": None
        }
        config_col.insert_one(config)
    
    _config_cache = config
    _config_cache_time = current_time
    return config

def update_config(key, value):
    """Update bot configuration and clear cache"""
    global _config_cache
    config_col.update_one({"_id": "main_config"}, {"$set": {key: value}}, upsert=True)
    _config_cache = None  # Clear cache

def get_next_folder_number():
    """Get next available folder number (atomic)"""
    config = get_config()
    number = config.get("next_folder_number", 1)
    update_config("next_folder_number", number + 1)
    return number

# =========================
# 👤 USER CLASS - OPTIMIZED
# =========================
class User:
    _cache = {}
    _cache_time = {}
    USER_CACHE_TTL = 30
    
    def __init__(self, user_id):
        self.user_id = str(user_id)
        
        # Check cache first
        if user_id in User._cache and (time.time() - User._cache_time.get(user_id, 0)) < User.USER_CACHE_TTL:
            self.data = User._cache[user_id]
        else:
            self.data = users_col.find_one({"_id": self.user_id})
            
            if not self.data:
                self.data = {
                    "_id": self.user_id,
                    "points": 0,
                    "is_vip": False,
                    "referred_by": None,
                    "referrals_count": 0,
                    "purchased_items": [],
                    "used_codes": [],
                    "username": None,
                    "first_name": None,
                    "joined_date": time.time(),
                    "last_active": time.time(),
                    "total_points_earned": 0,
                    "total_points_spent": 0
                }
                users_col.insert_one(self.data)
            
            # Update cache
            User._cache[user_id] = self.data
            User._cache_time[user_id] = time.time()
    
    def save(self):
        """Save user data and update cache"""
        users_col.update_one({"_id": self.user_id}, {"$set": self.data})
        User._cache[self.user_id] = self.data
        User._cache_time[self.user_id] = time.time()
    
    def add_points(self, amount):
        """Add points to user"""
        self.data["points"] += amount
        self.data["total_points_earned"] += amount
        self.save()
        return True
    
    def remove_points(self, amount):
        """Remove points from user"""
        if self.data["points"] >= amount:
            self.data["points"] -= amount
            self.data["total_points_spent"] += amount
            self.save()
            return True
        return False
    
    def get_points(self):
        return self.data["points"]
    
    def is_vip(self):
        return self.data.get("is_vip", False)
    
    def make_vip(self):
        self.data["is_vip"] = True
        self.save()
    
    def remove_vip(self):
        self.data["is_vip"] = False
        self.save()
    
    def add_referral(self, referrer_id):
        if not self.data.get("referred_by"):
            self.data["referred_by"] = str(referrer_id)
            self.save()
            reward = get_config().get("referral_reward", 5)
            referrer = User(referrer_id)
            referrer.add_points(reward)
            referrer.data["referrals_count"] += 1
            referrer.save()
            return True
        return False
    
    def purchase_item(self, item_name, price):
        if self.remove_points(price):
            if item_name not in self.data["purchased_items"]:
                self.data["purchased_items"].append(item_name)
                self.save()
            return True
        return False
    
    def has_purchased(self, item_name):
        return item_name in self.data.get("purchased_items", [])
    
    def add_used_code(self, code):
        if code not in self.data["used_codes"]:
            self.data["used_codes"].append(code)
            self.save()
            return True
        return False
    
    def update_username(self, username, first_name):
        self.data["username"] = username
        self.data["first_name"] = first_name
        self.save()

# =========================
# 📁 FOLDER SYSTEM - OPTIMIZED
# =========================
class FolderSystem:
    _folders_cache = {}
    _cache_time = {}
    FOLDER_CACHE_TTL = 30
    
    def get_folders(self, category, parent=None):
        """Get folders with caching"""
        cache_key = f"{category}_{parent}"
        
        if cache_key in self._folders_cache and (time.time() - self._cache_time.get(cache_key, 0)) < self.FOLDER_CACHE_TTL:
            return self._folders_cache[cache_key]
        
        query = {"category": category}
        if parent:
            query["parent"] = parent
        else:
            query["parent"] = None
        
        result = list(folders_col.find(query).sort("number", 1))
        self._folders_cache[cache_key] = result
        self._cache_time[cache_key] = time.time()
        return result
    
    def get_folder(self, category, name, parent=None):
        query = {"category": category, "name": name}
        if parent:
            query["parent"] = parent
        return folders_col.find_one(query)
    
    def get_folder_by_number(self, number):
        return folders_col.find_one({"number": number})
    
    def add_folder(self, category, name, files, price, parent=None, text_content=None):
        number = get_next_folder_number()
        
        folder_data = {
            "category": category,
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
        
        # Clear cache for this category
        self._folders_cache.pop(f"{category}_None", None)
        if parent:
            self._folders_cache.pop(f"{category}_{parent}", None)
        
        return number
    
    def delete_folder(self, category, name, parent=None):
        query = {"category": category, "name": name}
        if parent:
            query["parent"] = parent
        else:
            query["parent"] = None
        
        folder = folders_col.find_one(query)
        if not folder:
            return False
        
        folders_col.delete_many({"category": category, "parent": name})
        folders_col.delete_one(query)
        
        number = folder.get("number")
        if number:
            folders_col.update_many(
                {"number": {"$gt": number}},
                {"$inc": {"number": -1}}
            )
            config = get_config()
            current_next = config.get("next_folder_number", 1)
            if current_next > number:
                update_config("next_folder_number", current_next - 1)
        
        # Clear cache
        self._folders_cache.pop(f"{category}_None", None)
        if parent:
            self._folders_cache.pop(f"{category}_{parent}", None)
        
        return True
    
    def update_price(self, category, name, price, parent=None):
        query = {"category": category, "name": name}
        if parent:
            query["parent"] = parent
        folders_col.update_one(query, {"$set": {"price": price}})
        # Clear cache
        self._folders_cache.pop(f"{category}_None", None)
    
    def update_name(self, category, old_name, new_name, parent=None):
        query = {"category": category, "name": old_name}
        if parent:
            query["parent"] = parent
        folders_col.update_one(query, {"$set": {"name": new_name}})
        folders_col.update_many(
            {"category": category, "parent": old_name},
            {"$set": {"parent": new_name}}
        )
        # Clear cache
        self._folders_cache.pop(f"{category}_None", None)
    
    def move_folder(self, number, new_parent):
        folders_col.update_one({"number": number}, {"$set": {"parent": new_parent}})
        # Clear cache for all categories
        self._folders_cache.clear()
    
    def update_content(self, category, name, content_type, content, parent=None):
        query = {"category": category, "name": name}
        if parent:
            query["parent"] = parent
        
        if content_type == "text":
            folders_col.update_one(query, {"$set": {"text_content": content}})
        elif content_type == "files":
            folders_col.update_one(query, {"$set": {"files": content}})
        
        # Clear cache
        self._folders_cache.pop(f"{category}_None", None)
        return True

fs = FolderSystem()

# =========================
# 🎫 CODES SYSTEM - FIXED
# =========================
class CodeSystem:
    def generate_codes(self, points, count, multi_use=False, expiry_days=None):
        """Generate redeem codes - FIXED"""
        codes = []
        expiry_time = time.time() + (expiry_days * 86400) if expiry_days else None
        
        for _ in range(count):
            # Generate unique code
            code = "ZED" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            
            # Ensure code is unique
            while codes_col.find_one({"_id": code}):
                code = "ZED" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            
            code_data = {
                "_id": code,  # Using code as _id
                "points": points,
                "used": False,
                "multi_use": multi_use,
                "used_count": 0,
                "max_uses": 10 if multi_use else 1,
                "expiry": expiry_time,
                "created_at": time.time(),
                "used_by": []
            }
            
            codes_col.insert_one(code_data)
            codes.append(code)
        
        return codes
    
    def redeem_code(self, code, user):
        """Redeem a code"""
        code_data = codes_col.find_one({"_id": code})
        
        if not code_data:
            return False, "❌ Invalid code!"
        
        # Check expiry
        if code_data.get("expiry") and time.time() > code_data["expiry"]:
            return False, "❌ Code has expired!"
        
        # Check usage
        if not code_data.get("multi_use", False) and code_data.get("used", False):
            return False, "❌ Code already used!"
        
        # Check if user already used
        if user.user_id in code_data.get("used_by", []):
            return False, "❌ You have already used this code!"
        
        # Check max uses
        if code_data.get("multi_use", False):
            if code_data.get("used_count", 0) >= code_data.get("max_uses", 10):
                return False, "❌ Code has reached maximum uses!"
        
        # Add points
        points = code_data["points"]
        user.add_points(points)
        
        # Update code
        update_data = {
            "$push": {"used_by": user.user_id},
            "$inc": {"used_count": 1}
        }
        
        if not code_data.get("multi_use", False):
            update_data["$set"] = {"used": True}
        
        codes_col.update_one({"_id": code}, update_data)
        user.add_used_code(code)
        
        return True, f"✅ +{points} points added!"
    
    def get_stats(self):
        """Get code statistics"""
        total = codes_col.count_documents({})
        used = codes_col.count_documents({"used": True})
        unused = total - used
        multi_use = codes_col.count_documents({"multi_use": True})
        return total, used, unused, multi_use
    
    def get_all_codes(self):
        """Get all codes"""
        return list(codes_col.find({}).sort("created_at", -1).limit(100))

code_system = CodeSystem()

# =========================
# 📊 POINTS PACKAGES
# =========================
def get_points_packages():
    packages = config_col.find_one({"_id": "points_packages"})
    if not packages:
        default_packages = {
            "_id": "points_packages",
            "packages": [
                {"points": 100, "price_usd": 5, "bonus": 0, "active": True},
                {"points": 250, "price_usd": 10, "bonus": 25, "active": True},
                {"points": 550, "price_usd": 20, "bonus": 100, "active": True},
                {"points": 1500, "price_usd": 50, "bonus": 500, "active": True},
                {"points": 3500, "price_usd": 100, "bonus": 1500, "active": True},
                {"points": 10000, "price_usd": 250, "bonus": 5000, "active": True}
            ]
        }
        config_col.insert_one(default_packages)
        return default_packages["packages"]
    return packages["packages"]

def save_points_packages(packages):
    config_col.update_one({"_id": "points_packages"}, {"$set": {"packages": packages}}, upsert=True)

# =========================
# 🚫 FORCE JOIN CHECK - OPTIMIZED
# =========================
_force_join_cache = {}
FORCE_JOIN_CACHE_TTL = 60

def check_force_join(user_id):
    """Check if user joined required channels with caching"""
    global _force_join_cache
    
    current_time = time.time()
    if user_id in _force_join_cache and (current_time - _force_join_cache[user_id][1]) < FORCE_JOIN_CACHE_TTL:
        return _force_join_cache[user_id][0]
    
    config = get_config()
    force_channels = config.get("force_channels", [])
    
    if not force_channels:
        _force_join_cache[user_id] = (True, current_time)
        return True
    
    for channel in force_channels:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                _force_join_cache[user_id] = (False, current_time)
                return False
        except:
            _force_join_cache[user_id] = (False, current_time)
            return False
    
    _force_join_cache[user_id] = (True, current_time)
    return True

def force_join_handler(func):
    @wraps(func)
    def wrapper(message):
        user_id = message.from_user.id
        
        if not check_force_join(user_id):
            config = get_config()
            channels = config.get("force_channels", [])
            
            keyboard = InlineKeyboardMarkup()
            for channel in channels:
                keyboard.add(InlineKeyboardButton(
                    f"📢 Join {channel}",
                    url=f"https://t.me/{channel.replace('@', '')}"
                ))
            keyboard.add(InlineKeyboardButton("✅ I've Joined", callback_data="check_join"))
            
            bot.send_message(
                user_id,
                "🚫 <b>Access Restricted!</b>\n\nPlease join the following channels:",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return
        
        return func(message)
    return wrapper

# =========================
# 🎨 KEYBOARDS
# =========================
def get_main_keyboard(user_id):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    keyboard.add("📂 FREE METHODS", "💎 VIP METHODS")
    keyboard.add("📱 PREMIUM APPS", "⚡ SERVICES")
    keyboard.add("💰 BALANCE", "⭐ VIP ACCESS")
    keyboard.add("🎁 REFERRAL", "👤 PROFILE")
    keyboard.add("🎫 REDEEM", "💎 BUY POINTS")
    
    if is_admin(user_id):
        keyboard.add("⚙️ ADMIN")
    
    config = get_config()
    custom_buttons = config.get("custom_buttons", [])
    
    if custom_buttons:
        row = []
        for btn in custom_buttons:
            row.append(btn["text"])
            if len(row) == 2:
                keyboard.add(*row)
                row = []
        if row:
            keyboard.add(*row)
    
    return keyboard

def get_admin_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    keyboard.add("📤 UPLOAD FREE", "📤 UPLOAD VIP")
    keyboard.add("📤 UPLOAD APPS", "📤 UPLOAD SERVICE")
    keyboard.add("📁 CREATE SUBFOLDER", "🗑 DELETE FOLDER")
    keyboard.add("✏️ EDIT PRICE", "✏️ EDIT NAME")
    keyboard.add("📝 EDIT CONTENT", "🔀 MOVE FOLDER")
    keyboard.add("👑 ADD VIP", "👑 REMOVE VIP")
    keyboard.add("💰 GIVE POINTS", "🎫 GENERATE CODES")
    keyboard.add("📊 VIEW CODES", "📦 POINTS PACKAGES")
    keyboard.add("👥 MANAGE ADMINS", "📞 SET CONTACTS")
    keyboard.add("➕ ADD BUTTON", "➖ REMOVE BUTTON")
    keyboard.add("➕ ADD CHANNEL", "➖ REMOVE CHANNEL")
    keyboard.add("⚙️ SETTINGS", "📊 STATISTICS")
    keyboard.add("📢 BROADCAST", "🔔 TOGGLE NOTIFY")
    keyboard.add("◀️ BACK TO MENU")
    
    return keyboard

# =========================
# 🤖 BOT COMMANDS
# =========================
@bot.message_handler(commands=['start'])
@force_join_handler
def start_command(message):
    user_id = message.from_user.id
    user = User(user_id)
    
    user.update_username(message.from_user.username, message.from_user.first_name)
    
    args = message.text.split()
    if len(args) > 1:
        referrer_id = args[1]
        if referrer_id.isdigit() and int(referrer_id) != user_id:
            user.add_referral(referrer_id)
            try:
                bot.send_message(
                    int(referrer_id),
                    f"🎉 <b>New Referral!</b>\n\n@{message.from_user.username or user_id} joined!\nYou earned +{get_config().get('referral_reward', 5)} points!",
                    parse_mode="HTML"
                )
            except:
                pass
    
    config = get_config()
    welcome_msg = config.get("welcome_message", "Welcome to ZEDOX BOT!")
    
    bot.send_message(
        user_id,
        f"{welcome_msg}\n\n💰 <b>Points:</b> {user.get_points()}\n👑 <b>VIP:</b> {'✅' if user.is_vip() else '❌'}",
        reply_markup=get_main_keyboard(user_id),
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def check_join_callback(call):
    user_id = call.from_user.id
    
    if check_force_join(user_id):
        bot.edit_message_text("✅ <b>Access Granted!</b>", user_id, call.message.message_id, parse_mode="HTML")
        user = User(user_id)
        bot.send_message(user_id, f"Welcome! Points: {user.get_points()}", reply_markup=get_main_keyboard(user_id))
    else:
        bot.answer_callback_query(call.id, "❌ Join all channels first!", show_alert=True)

# =========================
# 📂 CATEGORY HANDLERS
# =========================
def show_category_folders(user_id, category, title):
    folders = fs.get_folders(category)
    
    if not folders:
        bot.send_message(user_id, f"📁 <b>{title}</b>\n\nNo content available!", parse_mode="HTML")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    for folder in folders:
        name = folder["name"]
        number = folder.get("number", "?")
        price = folder.get("price", 0)
        has_subfolders = len(fs.get_folders(category, name)) > 0
        icon = "📁" if has_subfolders else "📄"
        text = f"{icon} [{number}] {name}" + (f" - {price} pts" if price > 0 else "")
        keyboard.add(InlineKeyboardButton(text, callback_data=f"open_{category}_{name}"))
    
    bot.send_message(user_id, f"📁 <b>{title}</b>\n\nSelect:", reply_markup=keyboard, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "📂 FREE METHODS")
@force_join_handler
def free_methods(m): show_category_folders(m.from_user.id, "free", "FREE METHODS")

@bot.message_handler(func=lambda m: m.text == "💎 VIP METHODS")
@force_join_handler
def vip_methods(m): show_category_folders(m.from_user.id, "vip", "VIP METHODS")

@bot.message_handler(func=lambda m: m.text == "📱 PREMIUM APPS")
@force_join_handler
def apps_methods(m): show_category_folders(m.from_user.id, "apps", "PREMIUM APPS")

@bot.message_handler(func=lambda m: m.text == "⚡ SERVICES")
@force_join_handler
def services_methods(m): show_category_folders(m.from_user.id, "services", "SERVICES")

# =========================
# 📂 FOLDER NAVIGATION
# =========================
@bot.callback_query_handler(func=lambda call: call.data.startswith("open_"))
def open_folder_callback(call):
    user_id = call.from_user.id
    user = User(user_id)
    
    parts = call.data.split("_")
    category = parts[1]
    name = parts[2]
    
    folder = fs.get_folder(category, name)
    if not folder:
        bot.answer_callback_query(call.id, "❌ Not found!")
        return
    
    subfolders = fs.get_folders(category, name)
    if subfolders:
        keyboard = InlineKeyboardMarkup(row_width=1)
        for sub in subfolders:
            sub_name = sub["name"]
            sub_number = sub.get("number", "?")
            sub_price = sub.get("price", 0)
            text = f"📁 [{sub_number}] {sub_name}" + (f" - {sub_price} pts" if sub_price > 0 else "")
            keyboard.add(InlineKeyboardButton(text, callback_data=f"open_{category}_{sub_name}"))
        keyboard.add(InlineKeyboardButton("🔙 BACK", callback_data=f"back_{category}"))
        bot.edit_message_text(f"📁 <b>{name}</b>", user_id, call.message.message_id, reply_markup=keyboard, parse_mode="HTML")
        bot.answer_callback_query(call.id)
        return
    
    text_content = folder.get("text_content")
    price = folder.get("price", 0)
    can_access = user.is_vip() or user.has_purchased(name)
    
    if not can_access:
        if price > 0:
            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                InlineKeyboardButton(f"💰 Buy {price} pts", callback_data=f"buy_{category}_{name}_{price}"),
                InlineKeyboardButton("⭐ VIP", callback_data="get_vip"),
                InlineKeyboardButton("💎 Buy Points", callback_data="buy_points")
            )
            bot.edit_message_text(
                f"🔒 <b>{name}</b>\n\nPrice: {price} pts\nYour points: {user.get_points()}",
                user_id, call.message.message_id, reply_markup=keyboard, parse_mode="HTML"
            )
        else:
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("⭐ Get VIP", callback_data="get_vip"))
            bot.edit_message_text(f"🔒 <b>{name}</b>\n\nVIP only!", user_id, call.message.message_id, reply_markup=keyboard, parse_mode="HTML")
        bot.answer_callback_query(call.id, "🔒 Premium content!")
        return
    
    if not user.is_vip() and price > 0:
        if user.get_points() >= price:
            user.remove_points(price)
            user.purchase_item(name, price)
            bot.answer_callback_query(call.id, f"✅ -{price} pts")
        else:
            bot.answer_callback_query(call.id, f"❌ Need {price} pts! You have {user.get_points()}", show_alert=True)
            return
    
    if text_content:
        bot.edit_message_text(f"📄 <b>{name}</b>\n\n{text_content}", user_id, call.message.message_id, parse_mode="HTML")
    else:
        files = folder.get("files", [])
        bot.answer_callback_query(call.id, "📤 Sending...")
        for f in files:
            try:
                bot.copy_message(user_id, f["chat"], f["msg"])
                time.sleep(0.2)
            except:
                continue
        if get_config().get("send_notifications", True):
            bot.send_message(user_id, f"✅ {len(files)} file(s) sent!")

@bot.callback_query_handler(func=lambda call: call.data.startswith("back_"))
def back_callback(call):
    category = call.data.split("_")[1]
    titles = {"free": "FREE METHODS", "vip": "VIP METHODS", "apps": "PREMIUM APPS", "services": "SERVICES"}
    show_category_folders(call.from_user.id, category, titles.get(category, category.upper()))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def buy_item_callback(call):
    user_id = call.from_user.id
    user = User(user_id)
    _, category, name, price = call.data.split("_")
    price = int(price)
    
    if user.is_vip() or user.has_purchased(name):
        bot.answer_callback_query(call.id, "✅ Already have access!")
        return
    
    if user.get_points() >= price:
        user.remove_points(price)
        user.purchase_item(name, price)
        bot.answer_callback_query(call.id, f"✅ Purchased! -{price} pts", show_alert=True)
        bot.edit_message_text(f"✅ <b>Purchased!</b>\n\nYou now own: {name}\nRemaining: {user.get_points()} pts", user_id, call.message.message_id, parse_mode="HTML")
    else:
        bot.answer_callback_query(call.id, f"❌ Need {price} pts! You have {user.get_points()}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "buy_points")
def buy_points_callback(call):
    buy_points_command(call.message)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "get_vip")
def get_vip_callback(call):
    vip_command(call.message)
    bot.answer_callback_query(call.id)

# =========================
# 💎 POINTS & VIP HANDLERS
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 BALANCE")
@force_join_handler
def balance_command(m):
    user = User(m.from_user.id)
    bot.send_message(
        m.from_user.id,
        f"💰 <b>BALANCE</b>\n\n┌ Points: {user.get_points()}\n├ VIP: {'✅' if user.is_vip() else '❌'}\n├ Purchased: {len(user.data.get('purchased_items', []))}\n├ Referrals: {user.data.get('referrals_count', 0)}\n├ Earned: {user.data.get('total_points_earned', 0)}\n└ Spent: {user.data.get('total_points_spent', 0)}",
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: m.text == "⭐ VIP ACCESS")
@force_join_handler
def vip_command(m):
    user = User(m.from_user.id)
    if user.is_vip():
        bot.send_message(m.from_user.id, "✅ <b>You are VIP!</b>\n\nAccess all VIP METHODS!", parse_mode="HTML")
        return
    
    config = get_config()
    vip_contact = config.get("vip_contact", "Contact admin")
    text = f"⭐ <b>VIP ACCESS</b>\n\n✨ Benefits:\n• All VIP METHODS\n• No points needed\n• Priority support\n\n💰 Points: {user.get_points()}\n\n📞 Contact: {vip_contact}\n🆔 ID: <code>{m.from_user.id}</code>"
    
    keyboard = InlineKeyboardMarkup()
    if config.get("vip_contact") and config.get("vip_contact").startswith("http"):
        keyboard.add(InlineKeyboardButton("📞 Contact", url=config.get("vip_contact")))
    
    bot.send_message(m.from_user.id, text, reply_markup=keyboard if keyboard.keyboard else None, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "💎 BUY POINTS")
@force_join_handler
def buy_points_command(m):
    user = User(m.from_user.id)
    packages = [p for p in get_points_packages() if p.get("active", True)]
    config = get_config()
    contact = config.get("contact_username") or config.get("contact_link") or "Contact admin"
    
    text = f"💎 <b>BUY POINTS</b>\n\n💰 Balance: {user.get_points()} pts\n\n"
    for i, pkg in enumerate(packages, 1):
        total = pkg["points"] + pkg.get("bonus", 0)
        text += f"{i}. {pkg['points']} pts"
        if pkg.get("bonus", 0) > 0:
            text += f" +{pkg['bonus']} BONUS"
        text += f"\n   💰 ${pkg['price_usd']} → {total} pts\n\n"
    
    text += f"📞 Contact: {contact}\n🆔 ID: <code>{m.from_user.id}</code>"
    
    keyboard = InlineKeyboardMarkup()
    if config.get("contact_link"):
        keyboard.add(InlineKeyboardButton("📞 Contact", url=config.get("contact_link")))
    elif config.get("contact_username"):
        keyboard.add(InlineKeyboardButton("📞 Contact", url=f"https://t.me/{config.get('contact_username').replace('@', '')}"))
    
    bot.send_message(m.from_user.id, text, reply_markup=keyboard if keyboard.keyboard else None, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🎁 REFERRAL")
@force_join_handler
def referral_command(m):
    user = User(m.from_user.id)
    link = f"https://t.me/{bot.get_me().username}?start={m.from_user.id}"
    reward = get_config().get("referral_reward", 5)
    
    bot.send_message(
        m.from_user.id,
        f"🎁 <b>REFERRAL</b>\n\n🔗 <code>{link}</code>\n\n👥 Referrals: {user.data.get('referrals_count', 0)}\n💰 Per referral: +{reward} pts\n💎 Total earned: {user.data.get('referrals_count', 0) * reward} pts",
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: m.text == "👤 PROFILE")
@force_join_handler
def profile_command(m):
    user = User(m.from_user.id)
    items = user.data.get("purchased_items", [])
    items_text = "\n".join([f"• {item}" for item in items[:10]])
    if len(items) > 10:
        items_text += f"\n• ... {len(items)-10} more"
    
    bot.send_message(
        m.from_user.id,
        f"👤 <b>PROFILE</b>\n\n┌ ID: <code>{m.from_user.id}</code>\n├ Name: {m.from_user.first_name}\n├ VIP: {'✅' if user.is_vip() else '❌'}\n├ Points: {user.get_points()}\n├ Referrals: {user.data.get('referrals_count', 0)}\n└ Items: {len(items)}\n\n📚 <b>Your Items:</b>\n{items_text if items else 'None'}",
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: m.text == "🎫 REDEEM")
@force_join_handler
def redeem_command(m):
    msg = bot.send_message(m.from_user.id, "🎫 <b>REDEEM CODE</b>\n\nEnter code:", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_redeem)

def process_redeem(m):
    user = User(m.from_user.id)
    success, result = code_system.redeem_code(m.text.strip().upper(), user)
    bot.send_message(m.from_user.id, result + (f"\n💰 Balance: {user.get_points()}" if success else ""), parse_mode="HTML")

# =========================
# ⚙️ ADMIN PANEL
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN" and is_admin(m.from_user.id))
def admin_panel(m):
    bot.send_message(m.from_user.id, "⚙️ <b>ADMIN PANEL</b>", reply_markup=get_admin_keyboard(), parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "◀️ BACK TO MENU" and is_admin(m.from_user.id))
def back_to_menu(m):
    bot.send_message(m.from_user.id, "Main menu:", reply_markup=get_main_keyboard(m.from_user.id))

# =========================
# 🎫 GENERATE CODES - FIXED & FAST
# =========================
@bot.message_handler(func=lambda m: m.text == "🎫 GENERATE CODES" and is_admin(m.from_user.id))
def generate_codes_command(m):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(InlineKeyboardButton("Single Use", callback_data="gen_single"), InlineKeyboardButton("Multi Use", callback_data="gen_multi"))
    bot.send_message(m.from_user.id, "🎫 <b>GENERATE CODES</b>\n\nSelect type:", reply_markup=keyboard, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("gen_"))
def generate_codes_type(call):
    code_type = call.data.split("_")[1]
    multi_use = (code_type == "multi")
    
    if not hasattr(bot, 'code_gen_session'):
        bot.code_gen_session = {}
    
    bot.code_gen_session[call.from_user.id] = {"multi_use": multi_use, "step": "points"}
    msg = bot.send_message(call.from_user.id, "💰 Enter points per code:", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_code_points)
    bot.answer_callback_query(call.id)

def process_code_points(message):
    user_id = message.from_user.id
    
    try:
        points = int(message.text.strip())
        if points <= 0:
            bot.send_message(user_id, "❌ Points must be > 0!")
            return
        if points > 100000:
            bot.send_message(user_id, "⚠️ Max 100,000 points!")
            return
        
        bot.code_gen_session[user_id]["points"] = points
        msg = bot.send_message(user_id, "🔢 How many codes? (1-100):", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_code_count)
    except ValueError:
        bot.send_message(user_id, "❌ Enter a valid number!")
        msg = bot.send_message(user_id, "💰 Enter points per code:", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_code_points)

def process_code_count(message):
    user_id = message.from_user.id
    
    try:
        count = int(message.text.strip())
        if count <= 0:
            bot.send_message(user_id, "❌ Count must be > 0!")
            return
        if count > 100:
            bot.send_message(user_id, "⚠️ Max 100 codes!")
            return
        
        session = bot.code_gen_session.get(user_id)
        if not session:
            bot.send_message(user_id, "❌ Session expired!")
            return
        
        if session["multi_use"]:
            msg = bot.send_message(user_id, "📅 Expiry days? (0 = no expiry):", parse_mode="HTML")
            bot.register_next_step_handler(msg, lambda x: process_code_expiry(x, session["points"], count))
        else:
            codes = code_system.generate_codes(session["points"], count, False)
            codes_text = "\n".join(codes)
            bot.send_message(
                user_id,
                f"✅ <b>{count} Codes Generated!</b>\n\n📊 {session['points']} pts each\n🔑 Single-use\n\n<code>{codes_text}</code>",
                parse_mode="HTML",
                reply_markup=get_admin_keyboard()
            )
            del bot.code_gen_session[user_id]
    except ValueError:
        bot.send_message(user_id, "❌ Enter a valid number!")
        msg = bot.send_message(user_id, "🔢 How many codes? (1-100):", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_code_count)

def process_code_expiry(message, points, count):
    user_id = message.from_user.id
    
    try:
        expiry_days = int(message.text.strip()) if message.text.strip() != "0" else None
        codes = code_system.generate_codes(points, count, True, expiry_days)
        codes_text = "\n".join(codes)
        expiry_msg = f"Expiry: {expiry_days} days" if expiry_days else "No expiry"
        
        bot.send_message(
            user_id,
            f"✅ <b>{count} Codes Generated!</b>\n\n📊 {points} pts each\n🔑 Multi-use\n⏰ {expiry_msg}\n\n<code>{codes_text}</code>",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard()
        )
        
        if hasattr(bot, 'code_gen_session') and user_id in bot.code_gen_session:
            del bot.code_gen_session[user_id]
    except ValueError:
        bot.send_message(user_id, "❌ Enter a valid number!")

# =========================
# 📊 VIEW CODES
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 VIEW CODES" and is_admin(m.from_user.id))
def view_codes_command(m):
    codes = code_system.get_all_codes()
    if not codes:
        bot.send_message(m.from_user.id, "📊 No codes yet!")
        return
    
    total, used, unused, multi = code_system.get_stats()
    text = f"📊 <b>CODE STATS</b>\n\n┌ Total: {total}\n├ Used: {used}\n├ Unused: {unused}\n└ Multi: {multi}\n\n"
    
    unused_codes = [c for c in codes if not c.get("used", False)][:5]
    if unused_codes:
        text += "<b>Recent Unused:</b>\n"
        for c in unused_codes:
            text += f"• <code>{c['_id']}</code> - {c['points']} pts\n"
    
    bot.send_message(m.from_user.id, text, parse_mode="HTML")

# =========================
# 📤 UPLOAD HANDLERS (SIMPLIFIED)
# =========================
upload_sessions = {}

@bot.message_handler(func=lambda m: m.text in ["📤 UPLOAD FREE", "📤 UPLOAD VIP", "📤 UPLOAD APPS", "📤 UPLOAD SERVICE"] and is_admin(m.from_user.id))
def start_upload(m):
    category_map = {"📤 UPLOAD FREE": "free", "📤 UPLOAD VIP": "vip", "📤 UPLOAD APPS": "apps", "📤 UPLOAD SERVICE": "services"}
    is_service = (m.text == "📤 UPLOAD SERVICE")
    
    upload_sessions[m.from_user.id] = {"category": category_map[m.text], "is_service": is_service, "files": [], "step": "name"}
    msg = bot.send_message(m.from_user.id, "📤 Send folder name:\n/cancel to cancel", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_upload_name)

def process_upload_name(m):
    user_id = m.from_user.id
    if m.text == "/cancel":
        upload_sessions.pop(user_id, None)
        bot.send_message(user_id, "❌ Cancelled!", reply_markup=get_admin_keyboard())
        return
    
    if user_id not in upload_sessions:
        return
    
    upload_sessions[user_id]["name"] = m.text
    msg = bot.send_message(user_id, "💰 Price (points, 0 = free):", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_upload_price)

def process_upload_price(m):
    user_id = m.from_user.id
    if m.text == "/cancel":
        upload_sessions.pop(user_id, None)
        bot.send_message(user_id, "❌ Cancelled!", reply_markup=get_admin_keyboard())
        return
    
    try:
        upload_sessions[user_id]["price"] = int(m.text)
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        keyboard.add("📝 Text", "📁 Files")
        keyboard.add("/cancel")
        msg = bot.send_message(user_id, "Choose content type:", reply_markup=keyboard, parse_mode="HTML")
        bot.register_next_step_handler(msg, process_upload_type)
    except:
        bot.send_message(user_id, "❌ Invalid price!")
        msg = bot.send_message(user_id, "💰 Price (points):", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_upload_price)

def process_upload_type(m):
    user_id = m.from_user.id
    if m.text == "/cancel":
        upload_sessions.pop(user_id, None)
        bot.send_message(user_id, "❌ Cancelled!", reply_markup=get_admin_keyboard())
        return
    
    if m.text == "📝 Text":
        msg = bot.send_message(user_id, "📝 Send text content:", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_text_content)
    elif m.text == "📁 Files":
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add("/done", "/cancel")
        msg = bot.send_message(user_id, "📁 Send files, press /done when finished:", reply_markup=keyboard, parse_mode="HTML")
        bot.register_next_step_handler(msg, process_upload_files)
    else:
        process_upload_price(m)

def save_text_content(m):
    user_id = m.from_user.id
    if m.text == "/cancel":
        upload_sessions.pop(user_id, None)
        bot.send_message(user_id, "❌ Cancelled!", reply_markup=get_admin_keyboard())
        return
    
    session = upload_sessions[user_id]
    number = fs.add_folder(session["category"], session["name"], [], session["price"], text_content=m.text)
    
    if session.get("is_service"):
        folder = fs.get_folder(session["category"], session["name"])
        if folder:
            folders_col.update_one({"_id": folder["_id"]}, {"$set": {"service_msg": m.text}})
    
    bot.send_message(user_id, f"✅ Uploaded!\n📌 #{number}\n📂 {session['name']}\n💰 {session['price']} pts", reply_markup=get_admin_keyboard(), parse_mode="HTML")
    upload_sessions.pop(user_id, None)

def process_upload_files(m):
    user_id = m.from_user.id
    if m.text == "/cancel":
        upload_sessions.pop(user_id, None)
        bot.send_message(user_id, "❌ Cancelled!", reply_markup=get_admin_keyboard())
        return
    
    if m.text == "/done":
        session = upload_sessions[user_id]
        if not session["files"]:
            bot.send_message(user_id, "❌ No files!")
            return
        
        number = fs.add_folder(session["category"], session["name"], session["files"], session["price"])
        bot.send_message(user_id, f"✅ Uploaded!\n📌 #{number}\n📂 {session['name']}\n💰 {session['price']} pts\n📁 {len(session['files'])} files", reply_markup=get_admin_keyboard(), parse_mode="HTML")
        upload_sessions.pop(user_id, None)
        return
    
    if m.content_type in ["document", "photo", "video"]:
        upload_sessions[user_id]["files"].append({"chat": m.chat.id, "msg": m.message_id, "type": m.content_type})
        bot.send_message(user_id, f"✅ Saved ({len(upload_sessions[user_id]['files'])} files)")
    else:
        bot.send_message(user_id, "❌ Send documents, photos, or videos only!")
    
    bot.register_next_step_handler(m, process_upload_files)

# =========================
# 🗑 DELETE FOLDER
# =========================
@bot.message_handler(func=lambda m: m.text == "🗑 DELETE FOLDER" and is_admin(m.from_user.id))
def delete_folder_cmd(m):
    msg = bot.send_message(m.from_user.id, "🗑 Send: <code>category folder_name</code>\nExample: <code>services Amazon Prime</code>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_delete)

def process_delete(m):
    user_id = m.from_user.id
    parts = m.text.split(maxsplit=1)
    if len(parts) != 2:
        bot.send_message(user_id, "❌ Use: category folder_name")
        return
    
    category, name = parts[0].lower(), parts[1].strip()
    if category not in ["free", "vip", "apps", "services"]:
        bot.send_message(user_id, "❌ Category: free, vip, apps, services")
        return
    
    folder = fs.get_folder(category, name)
    if not folder:
        bot.send_message(user_id, f"❌ '{name}' not found in {category}!")
        return
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("✅ Delete", callback_data=f"del_{category}_{name}"), InlineKeyboardButton("❌ Cancel", callback_data="cancel_del"))
    bot.send_message(user_id, f"⚠️ Delete '{name}' from {category.upper()}?\nAll subfolders will be deleted!", reply_markup=keyboard, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("del_"))
def confirm_delete(call):
    _, category, name = call.data.split("_", 2)
    if fs.delete_folder(category, name):
        bot.edit_message_text(f"✅ Deleted: {category} → {name}", call.from_user.id, call.message.message_id)
    else:
        bot.edit_message_text(f"❌ Not found!", call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_del")
def cancel_delete(call):
    bot.edit_message_text("❌ Cancelled", call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

# =========================
# 📝 EDIT CONTENT
# =========================
@bot.message_handler(func=lambda m: m.text == "📝 EDIT CONTENT" and is_admin(m.from_user.id))
def edit_content_cmd(m):
    msg = bot.send_message(m.from_user.id, "📝 Send: <code>category folder_name</code>\nExample: <code>services Amazon Prime</code>", parse_mode="HTML")
    bot.register_next_step_handler(msg, select_folder_for_edit)

def select_folder_for_edit(m):
    user_id = m.from_user.id
    parts = m.text.split(maxsplit=1)
    if len(parts) != 2:
        bot.send_message(user_id, "❌ Use: category folder_name")
        return
    
    category, name = parts[0].lower(), parts[1].strip()
    if category not in ["free", "vip", "apps", "services"]:
        bot.send_message(user_id, "❌ Invalid category!")
        return
    
    folder = fs.get_folder(category, name)
    if not folder:
        bot.send_message(user_id, f"❌ '{name}' not found!")
        return
    
    if not hasattr(bot, 'edit_session'):
        bot.edit_session = {}
    
    bot.edit_session[user_id] = {"category": category, "name": name}
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(InlineKeyboardButton("📝 Edit Text", callback_data="edit_text"), InlineKeyboardButton("📁 Edit Files", callback_data="edit_files"), InlineKeyboardButton("❌ Cancel", callback_data="edit_cancel"))
    bot.send_message(user_id, f"📝 <b>Edit: {name}</b>\n\nWhat to edit?", reply_markup=keyboard, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "edit_text")
def edit_text_callback(call):
    user_id = call.from_user.id
    if not hasattr(bot, 'edit_session') or user_id not in bot.edit_session:
        bot.answer_callback_query(call.id, "Session expired!")
        return
    
    session = bot.edit_session[user_id]
    folder = fs.get_folder(session["category"], session["name"])
    current = folder.get("text_content", "No current content")[:200]
    
    msg = bot.send_message(user_id, f"📝 Current:\n{current}\n\nSend NEW text content:", parse_mode="HTML")
    bot.register_next_step_handler(msg, save_edited_text)
    bot.answer_callback_query(call.id)

def save_edited_text(m):
    user_id = m.from_user.id
    if not hasattr(bot, 'edit_session') or user_id not in bot.edit_session:
        bot.send_message(user_id, "Session expired!", reply_markup=get_admin_keyboard())
        return
    
    session = bot.edit_session[user_id]
    fs.update_content(session["category"], session["name"], "text", m.text)
    bot.send_message(user_id, f"✅ Text updated for {session['name']}!", reply_markup=get_admin_keyboard())
    del bot.edit_session[user_id]

@bot.callback_query_handler(func=lambda call: call.data == "edit_files")
def edit_files_callback(call):
    user_id = call.from_user.id
    if not hasattr(bot, 'edit_session') or user_id not in bot.edit_session:
        bot.answer_callback_query(call.id, "Session expired!")
        return
    
    session = bot.edit_session[user_id]
    session["new_files"] = []
    
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("/done", "/cancel")
    msg = bot.send_message(user_id, "📁 Send NEW files (will replace all)\nPress /done when finished:", reply_markup=keyboard, parse_mode="HTML")
    bot.register_next_step_handler(msg, process_edit_files)
    bot.answer_callback_query(call.id)

def process_edit_files(m):
    user_id = m.from_user.id
    if m.text == "/cancel":
        bot.edit_session.pop(user_id, None)
        bot.send_message(user_id, "❌ Cancelled!", reply_markup=get_admin_keyboard())
        return
    
    if m.text == "/done":
        session = bot.edit_session.get(user_id)
        if not session or not session.get("new_files"):
            bot.send_message(user_id, "❌ No files uploaded!")
            return
        
        fs.update_content(session["category"], session["name"], "files", session["new_files"])
        bot.send_message(user_id, f"✅ Files updated! {len(session['new_files'])} file(s)", reply_markup=get_admin_keyboard())
        del bot.edit_session[user_id]
        return
    
    if m.content_type in ["document", "photo", "video"]:
        bot.edit_session[user_id]["new_files"].append({"chat": m.chat.id, "msg": m.message_id, "type": m.content_type})
        bot.send_message(user_id, f"✅ Saved ({len(bot.edit_session[user_id]['new_files'])} files)")
    else:
        bot.send_message(user_id, "❌ Send documents, photos, or videos!")
    
    bot.register_next_step_handler(m, process_edit_files)

@bot.callback_query_handler(func=lambda call: call.data == "edit_cancel")
def edit_cancel_callback(call):
    if hasattr(bot, 'edit_session') and call.from_user.id in bot.edit_session:
        del bot.edit_session[call.from_user.id]
    bot.edit_message_text("❌ Cancelled", call.from_user.id, call.message.message_id)
    bot.send_message(call.from_user.id, "Returning...", reply_markup=get_admin_keyboard())
    bot.answer_callback_query(call.id)

# =========================
# ✏️ EDIT PRICE & NAME (SIMPLIFIED)
# =========================
@bot.message_handler(func=lambda m: m.text == "✏️ EDIT PRICE" and is_admin(m.from_user.id))
def edit_price_cmd(m):
    msg = bot.send_message(m.from_user.id, "✏️ Send: <code>category folder_name new_price</code>\nExample: <code>vip Method 50</code>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: process_edit_price(x))

def process_edit_price(m):
    parts = m.text.split()
    if len(parts) < 3:
        bot.send_message(m.from_user.id, "❌ Use: category folder_name price")
        return
    category, price = parts[0].lower(), int(parts[-1])
    name = " ".join(parts[1:-1])
    fs.update_price(category, name, price)
    bot.send_message(m.from_user.id, f"✅ Price updated: {name} → {price} pts", reply_markup=get_admin_keyboard())

@bot.message_handler(func=lambda m: m.text == "✏️ EDIT NAME" and is_admin(m.from_user.id))
def edit_name_cmd(m):
    msg = bot.send_message(m.from_user.id, "✏️ Send: <code>category old_name new_name</code>\nExample: <code>free Old New</code>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: process_edit_name(x))

def process_edit_name(m):
    parts = m.text.split(maxsplit=2)
    if len(parts) != 3:
        bot.send_message(m.from_user.id, "❌ Use: category old_name new_name")
        return
    category, old, new = parts[0].lower(), parts[1], parts[2]
    fs.update_name(category, old, new)
    bot.send_message(m.from_user.id, f"✅ Renamed: {old} → {new}", reply_markup=get_admin_keyboard())

# =========================
# 🔀 MOVE FOLDER
# =========================
@bot.message_handler(func=lambda m: m.text == "🔀 MOVE FOLDER" and is_admin(m.from_user.id))
def move_folder_cmd(m):
    msg = bot.send_message(m.from_user.id, "🔀 Send: <code>folder_number new_parent</code>\nUse 'root' for main level", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: process_move(x))

def process_move(m):
    parts = m.text.split()
    if len(parts) != 2:
        bot.send_message(m.from_user.id, "❌ Use: number parent")
        return
    number, new_parent = int(parts[0]), parts[1] if parts[1] != "root" else None
    fs.move_folder(number, new_parent)
    bot.send_message(m.from_user.id, f"✅ Folder #{number} moved!", reply_markup=get_admin_keyboard())

# =========================
# 📁 CREATE SUBFOLDER
# =========================
@bot.message_handler(func=lambda m: m.text == "📁 CREATE SUBFOLDER" and is_admin(m.from_user.id))
def create_sub_cmd(m):
    msg = bot.send_message(m.from_user.id, "📁 Send: <code>category parent_name sub_name price</code>\nExample: <code>free Main Sub 10</code>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: process_sub(x))

def process_sub(m):
    parts = m.text.split(maxsplit=3)
    if len(parts) != 4:
        bot.send_message(m.from_user.id, "❌ Use: category parent name price")
        return
    category, parent, name, price = parts[0].lower(), parts[1], parts[2], int(parts[3])
    if not fs.get_folder(category, parent):
        bot.send_message(m.from_user.id, f"❌ Parent '{parent}' not found!")
        return
    number = fs.add_folder(category, name, [], price, parent)
    bot.send_message(m.from_user.id, f"✅ Subfolder #{number}: {parent} → {name}\n💰 {price} pts", reply_markup=get_admin_keyboard())

# =========================
# 👑 VIP MANAGEMENT (SIMPLIFIED)
# =========================
@bot.message_handler(func=lambda m: m.text == "👑 ADD VIP" and is_admin(m.from_user.id))
def add_vip_cmd(m):
    msg = bot.send_message(m.from_user.id, "👑 Send user ID or @username:", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: process_vip(x, True))

@bot.message_handler(func=lambda m: m.text == "👑 REMOVE VIP" and is_admin(m.from_user.id))
def remove_vip_cmd(m):
    msg = bot.send_message(m.from_user.id, "👑 Send user ID or @username:", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: process_vip(x, False))

def process_vip(m, add):
    user_id = m.from_user.id
    input_text = m.text.strip()
    
    if input_text.startswith("@"):
        try:
            target_id = bot.get_chat(input_text).id
        except:
            bot.send_message(user_id, "❌ User not found!")
            return
    else:
        try:
            target_id = int(input_text)
        except:
            bot.send_message(user_id, "❌ Invalid ID!")
            return
    
    user = User(target_id)
    if add:
        if user.is_vip():
            bot.send_message(user_id, "⚠️ Already VIP!")
            return
        user.make_vip()
        bot.send_message(user_id, f"✅ User {target_id} is now VIP!")
        try:
            bot.send_message(target_id, "🎉 <b>You are now VIP!</b>\n\nAccess all VIP METHODS!", parse_mode="HTML")
        except:
            pass
    else:
        if not user.is_vip():
            bot.send_message(user_id, "⚠️ Not VIP!")
            return
        user.remove_vip()
        bot.send_message(user_id, f"✅ VIP removed from {target_id}!")
        try:
            bot.send_message(target_id, "⚠️ <b>VIP status removed</b>", parse_mode="HTML")
        except:
            pass

# =========================
# 💰 GIVE POINTS
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 GIVE POINTS" and is_admin(m.from_user.id))
def give_points_cmd(m):
    msg = bot.send_message(m.from_user.id, "💰 Send: <code>user_id points</code>\nExample: <code>123456789 100</code>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: process_give(x))

def process_give(m):
    parts = m.text.split()
    if len(parts) != 2:
        bot.send_message(m.from_user.id, "❌ Use: user_id points")
        return
    
    try:
        target_id, points = int(parts[0]), int(parts[1])
        if points <= 0 or points > 1000000:
            bot.send_message(m.from_user.id, "❌ Points: 1-1,000,000")
            return
        
        user_data = users_col.find_one({"_id": str(target_id)})
        if not user_data:
            bot.send_message(m.from_user.id, f"❌ User {target_id} not found! Send /start first.")
            return
        
        user = User(target_id)
        old = user.get_points()
        user.add_points(points)
        
        bot.send_message(m.from_user.id, f"✅ Added +{points} pts to {target_id}\nOld: {old} → New: {user.get_points()}")
        try:
            bot.send_message(target_id, f"🎉 +{points} points received!\n💰 New balance: {user.get_points()} pts", parse_mode="HTML")
        except:
            pass
    except:
        bot.send_message(m.from_user.id, "❌ Invalid input!")

# =========================
# 📦 POINTS PACKAGES (SIMPLIFIED)
# =========================
@bot.message_handler(func=lambda m: m.text == "📦 POINTS PACKAGES" and is_admin(m.from_user.id))
def packages_cmd(m):
    packages = get_points_packages()
    text = "📦 <b>POINTS PACKAGES</b>\n\n"
    for i, pkg in enumerate(packages, 1):
        status = "✅" if pkg.get("active", True) else "❌"
        text += f"{i}. {status} {pkg['points']} pts - ${pkg['price_usd']}"
        if pkg.get("bonus", 0) > 0:
            text += f" (+{pkg['bonus']} bonus)"
        text += "\n"
    
    text += "\n<b>Commands:</b>\n/addpackage pts price_usd bonus\n/editpackage num pts price_usd bonus\n/togglepackage num\n/delpackage num"
    bot.send_message(m.from_user.id, text, parse_mode="HTML")

@bot.message_handler(commands=['addpackage', 'editpackage', 'togglepackage', 'delpackage'])
def package_commands(m):
    if not is_admin(m.from_user.id):
        return
    
    cmd = m.text.split()[0][1:]
    packages = get_points_packages()
    
    try:
        if cmd == 'addpackage':
            _, pts, price, bonus = m.text.split()
            packages.append({"points": int(pts), "price_usd": int(price), "bonus": int(bonus), "active": True})
            save_points_packages(packages)
            bot.send_message(m.from_user.id, f"✅ Added: {pts} pts for ${price}")
        
        elif cmd == 'editpackage':
            _, num, pts, price, bonus = m.text.split()
            num = int(num) - 1
            if 0 <= num < len(packages):
                packages[num].update({"points": int(pts), "price_usd": int(price), "bonus": int(bonus)})
                save_points_packages(packages)
                bot.send_message(m.from_user.id, f"✅ Package {num+1} updated!")
            else:
                bot.send_message(m.from_user.id, "❌ Invalid number!")
        
        elif cmd == 'togglepackage':
            _, num = m.text.split()
            num = int(num) - 1
            if 0 <= num < len(packages):
                packages[num]["active"] = not packages[num].get("active", True)
                save_points_packages(packages)
                status = "activated" if packages[num]["active"] else "deactivated"
                bot.send_message(m.from_user.id, f"✅ Package {num+1} {status}!")
            else:
                bot.send_message(m.from_user.id, "❌ Invalid number!")
        
        elif cmd == 'delpackage':
            _, num = m.text.split()
            num = int(num) - 1
            if 0 <= num < len(packages):
                removed = packages.pop(num)
                save_points_packages(packages)
                bot.send_message(m.from_user.id, f"✅ Removed: {removed['points']} pts")
            else:
                bot.send_message(m.from_user.id, "❌ Invalid number!")
    except:
        bot.send_message(m.from_user.id, f"❌ Use: /{cmd} ...")

# =========================
# 📊 STATISTICS
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 STATISTICS" and is_admin(m.from_user.id))
def stats_cmd(m):
    total_users = users_col.count_documents({})
    vip_users = users_col.count_documents({"is_vip": True})
    
    all_users = list(users_col.find({}))
    total_points = sum(u.get("points", 0) for u in all_users)
    total_earned = sum(u.get("total_points_earned", 0) for u in all_users)
    total_spent = sum(u.get("total_points_spent", 0) for u in all_users)
    total_refs = sum(u.get("referrals_count", 0) for u in all_users)
    
    free_folders = folders_col.count_documents({"category": "free"})
    vip_folders = folders_col.count_documents({"category": "vip"})
    apps_folders = folders_col.count_documents({"category": "apps"})
    services_folders = folders_col.count_documents({"category": "services"})
    
    total_codes, used_codes, unused_codes, _ = code_system.get_stats()
    
    text = f"📊 <b>STATISTICS</b>\n\n"
    text += f"👥 USERS: {total_users} (VIP: {vip_users})\n"
    text += f"💰 POINTS: {total_points:,} (Earned: {total_earned:,})\n"
    text += f"📚 CONTENT: FREE:{free_folders} VIP:{vip_folders} APPS:{apps_folders} SVC:{services_folders}\n"
    text += f"🎫 CODES: {total_codes} (Used: {used_codes})\n"
    text += f"👥 REFERRALS: {total_refs}\n"
    text += f"💎 SPENT: {total_spent:,}"
    
    bot.send_message(m.from_user.id, text, parse_mode="HTML")

# =========================
# 📢 BROADCAST (SIMPLIFIED)
# =========================
@bot.message_handler(func=lambda m: m.text == "📢 BROADCAST" and is_admin(m.from_user.id))
def broadcast_cmd(m):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(InlineKeyboardButton("All", callback_data="bc_all"), InlineKeyboardButton("VIP", callback_data="bc_vip"), InlineKeyboardButton("Free", callback_data="bc_free"))
    bot.send_message(m.from_user.id, "📢 Broadcast to:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith("bc_"))
def broadcast_target(call):
    target = call.data.split("_")[1]
    msg = bot.send_message(call.from_user.id, f"Send message to {target.upper()} users:", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: send_broadcast(x, target))
    bot.answer_callback_query(call.id)

def send_broadcast(m, target):
    query = {}
    if target == "vip":
        query = {"is_vip": True}
    elif target == "free":
        query = {"is_vip": False}
    
    users = list(users_col.find(query))
    if not users:
        bot.send_message(m.from_user.id, "❌ No users found!")
        return
    
    status = bot.send_message(m.from_user.id, f"📤 Broadcasting to {len(users)} users...")
    sent, failed = 0, 0
    
    for user in users:
        try:
            user_id = int(user["_id"])
            if m.content_type == "text":
                bot.send_message(user_id, m.text, parse_mode="HTML")
            elif m.content_type == "photo":
                bot.send_photo(user_id, m.photo[-1].file_id, caption=m.caption, parse_mode="HTML")
            elif m.content_type == "video":
                bot.send_video(user_id, m.video.file_id, caption=m.caption, parse_mode="HTML")
            elif m.content_type == "document":
                bot.send_document(user_id, m.document.file_id, caption=m.caption, parse_mode="HTML")
            sent += 1
            if sent % 20 == 0:
                time.sleep(0.5)
        except:
            failed += 1
    
    bot.edit_message_text(f"✅ Broadcast done!\n📤 Sent: {sent}\n❌ Failed: {failed}", m.from_user.id, status.message_id)

# =========================
# 🔘 CUSTOM BUTTONS (SIMPLIFIED)
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ ADD BUTTON" and is_admin(m.from_user.id))
def add_btn_cmd(m):
    msg = bot.send_message(m.from_user.id, "🔘 Send: <code>type|text|data</code>\nTypes: link|folder\nExample: <code>link|Website|https://example.com</code>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: process_add_btn(x))

def process_add_btn(m):
    parts = m.text.split("|")
    if len(parts) != 3:
        bot.send_message(m.from_user.id, "❌ Use: type|text|data")
        return
    btn_type, btn_text, btn_data = parts[0].lower(), parts[1], parts[2]
    if btn_type not in ["link", "folder"]:
        bot.send_message(m.from_user.id, "❌ Type: link or folder")
        return
    if btn_type == "folder" and not fs.get_folder_by_number(int(btn_data)):
        bot.send_message(m.from_user.id, f"❌ Folder #{btn_data} not found!")
        return
    
    config = get_config()
    buttons = config.get("custom_buttons", [])
    buttons.append({"text": btn_text, "type": btn_type, "data": btn_data})
    update_config("custom_buttons", buttons)
    bot.send_message(m.from_user.id, f"✅ Button added: {btn_text}", reply_markup=get_admin_keyboard())

@bot.message_handler(func=lambda m: m.text == "➖ REMOVE BUTTON" and is_admin(m.from_user.id))
def remove_btn_cmd(m):
    config = get_config()
    buttons = config.get("custom_buttons", [])
    if not buttons:
        bot.send_message(m.from_user.id, "❌ No buttons!")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for btn in buttons:
        keyboard.add(InlineKeyboardButton(f"❌ {btn['text']}", callback_data=f"rm_{btn['text']}"))
    bot.send_message(m.from_user.id, "Select button to remove:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith("rm_"))
def remove_btn_callback(call):
    btn_text = call.data[3:]
    config = get_config()
    buttons = [b for b in config.get("custom_buttons", []) if b["text"] != btn_text]
    update_config("custom_buttons", buttons)
    bot.edit_message_text(f"✅ Removed: {btn_text}", call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

# =========================
# 📢 FORCE JOIN CHANNELS (SIMPLIFIED)
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ ADD CHANNEL" and is_admin(m.from_user.id))
def add_channel_cmd(m):
    msg = bot.send_message(m.from_user.id, "➕ Send channel @username:", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: process_add_channel(x))

def process_add_channel(m):
    channel = m.text.strip()
    if not channel.startswith("@"):
        bot.send_message(m.from_user.id, "❌ Must start with @")
        return
    config = get_config()
    channels = config.get("force_channels", [])
    if channel in channels:
        bot.send_message(m.from_user.id, "❌ Already added!")
        return
    channels.append(channel)
    update_config("force_channels", channels)
    bot.send_message(m.from_user.id, f"✅ Added: {channel}", reply_markup=get_admin_keyboard())

@bot.message_handler(func=lambda m: m.text == "➖ REMOVE CHANNEL" and is_admin(m.from_user.id))
def remove_channel_cmd(m):
    config = get_config()
    channels = config.get("force_channels", [])
    if not channels:
        bot.send_message(m.from_user.id, "❌ No channels!")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for ch in channels:
        keyboard.add(InlineKeyboardButton(f"❌ {ch}", callback_data=f"rmch_{ch}"))
    bot.send_message(m.from_user.id, "Select channel to remove:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith("rmch_"))
def remove_channel_callback(call):
    channel = call.data[5:]
    config = get_config()
    channels = [c for c in config.get("force_channels", []) if c != channel]
    update_config("force_channels", channels)
    bot.edit_message_text(f"✅ Removed: {channel}", call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

# =========================
# 📞 SET CONTACTS
# =========================
@bot.message_handler(func=lambda m: m.text == "📞 SET CONTACTS" and is_admin(m.from_user.id))
def set_contacts_cmd(m):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("💰 Points Contact", callback_data="set_points"), InlineKeyboardButton("⭐ VIP Contact", callback_data="set_vip"), InlineKeyboardButton("📋 View", callback_data="view_contacts"))
    bot.send_message(m.from_user.id, "📞 Contact Settings:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data == "set_points")
def set_points_contact(call):
    msg = bot.send_message(call.from_user.id, "💰 Send @username or link:\nSend 'none' to remove", parse_mode="HTML")
    bot.register_next_step_handler(msg, save_points_contact)
    bot.answer_callback_query(call.id)

def save_points_contact(m):
    if m.text.lower() == "none":
        update_config("contact_username", None)
        update_config("contact_link", None)
    elif m.text.startswith("http"):
        update_config("contact_link", m.text)
        update_config("contact_username", None)
    elif m.text.startswith("@"):
        update_config("contact_username", m.text)
        update_config("contact_link", None)
    else:
        bot.send_message(m.from_user.id, "❌ Invalid!")
        return
    bot.send_message(m.from_user.id, "✅ Updated!", reply_markup=get_admin_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "set_vip")
def set_vip_contact(call):
    msg = bot.send_message(call.from_user.id, "⭐ Send @username or link:\nSend 'none' to remove", parse_mode="HTML")
    bot.register_next_step_handler(msg, save_vip_contact)
    bot.answer_callback_query(call.id)

def save_vip_contact(m):
    if m.text.lower() == "none":
        update_config("vip_contact", None)
    elif m.text.startswith("http") or m.text.startswith("@"):
        update_config("vip_contact", m.text)
    else:
        bot.send_message(m.from_user.id, "❌ Invalid!")
        return
    bot.send_message(m.from_user.id, "✅ Updated!", reply_markup=get_admin_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "view_contacts")
def view_contacts_cb(call):
    config = get_config()
    points = config.get("contact_username") or config.get("contact_link") or "Not set"
    vip = config.get("vip_contact") or "Not set"
    bot.edit_message_text(f"📞 Points: {points}\n⭐ VIP: {vip}", call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

# =========================
# ⚙️ SETTINGS
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ SETTINGS" and is_admin(m.from_user.id))
def settings_cmd(m):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(InlineKeyboardButton("⭐ VIP Msg", callback_data="set_vip_msg"), InlineKeyboardButton("🏠 Welcome", callback_data="set_welcome"), InlineKeyboardButton("💰 Referral Reward", callback_data="set_reward"), InlineKeyboardButton("💵 Points/$", callback_data="set_ppd"))
    bot.send_message(m.from_user.id, "⚙️ Settings:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data == "set_vip_msg")
def set_vip_msg_cb(call):
    msg = bot.send_message(call.from_user.id, "Send new VIP message:", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: update_config("vip_message", x.text) or bot.send_message(x.from_user.id, "✅ Updated!", reply_markup=get_admin_keyboard()))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "set_welcome")
def set_welcome_cb(call):
    msg = bot.send_message(call.from_user.id, "Send new welcome message:", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: update_config("welcome_message", x.text) or bot.send_message(x.from_user.id, "✅ Updated!", reply_markup=get_admin_keyboard()))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "set_reward")
def set_reward_cb(call):
    msg = bot.send_message(call.from_user.id, f"Current: {get_config().get('referral_reward', 5)}\nSend new amount:", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: update_config("referral_reward", int(x.text)) or bot.send_message(x.from_user.id, f"✅ Set to {x.text} points!", reply_markup=get_admin_keyboard()) if x.text.isdigit() else bot.send_message(x.from_user.id, "❌ Invalid!"))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "set_ppd")
def set_ppd_cb(call):
    msg = bot.send_message(call.from_user.id, f"Current: {get_config().get('points_per_dollar', 100)} pts = $1\nSend new value:", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: update_config("points_per_dollar", int(x.text)) or bot.send_message(x.from_user.id, f"✅ Set to {x.text} pts = $1!", reply_markup=get_admin_keyboard()) if x.text.isdigit() else bot.send_message(x.from_user.id, "❌ Invalid!"))
    bot.answer_callback_query(call.id)

# =========================
# 🔔 TOGGLE NOTIFY
# =========================
@bot.message_handler(func=lambda m: m.text == "🔔 TOGGLE NOTIFY" and is_admin(m.from_user.id))
def toggle_notify_cmd(m):
    config = get_config()
    current = config.get("send_notifications", True)
    update_config("send_notifications", not current)
    bot.send_message(m.from_user.id, f"🔔 Notifications: {'ON' if not current else 'OFF'}", reply_markup=get_admin_keyboard())

# =========================
# 👥 MANAGE ADMINS (SIMPLIFIED)
# =========================
@bot.message_handler(func=lambda m: m.text == "👥 MANAGE ADMINS" and is_admin(m.from_user.id))
def manage_admins_cmd(m):
    if m.from_user.id != ADMIN_ID:
        bot.send_message(m.from_user.id, "❌ Owner only!")
        return
    
    admins = list(admins_col.find({}))
    text = "👥 <b>ADMINS</b>\n\n"
    for admin in admins:
        owner = " 👑" if admin["_id"] == ADMIN_ID else ""
        text += f"• <code>{admin['_id']}</code>{owner}\n"
    text += "\n/addadmin id\n/removeadmin id\n/listadmins"
    bot.send_message(m.from_user.id, text, parse_mode="HTML")

@bot.message_handler(commands=['addadmin', 'removeadmin', 'listadmins'])
def admin_commands(m):
    if m.from_user.id != ADMIN_ID:
        return
    
    cmd = m.text.split()[0][1:]
    
    if cmd == 'listadmins':
        admins = list(admins_col.find({}))
        text = "👥 Admins:\n"
        for a in admins:
            text += f"• <code>{a['_id']}</code>\n"
        bot.send_message(m.from_user.id, text, parse_mode="HTML")
        return
    
    try:
        _, user_id = m.text.split()
        user_id = int(user_id)
        
        if cmd == 'addadmin':
            if admins_col.find_one({"_id": user_id}):
                bot.send_message(m.from_user.id, "❌ Already admin!")
                return
            admins_col.insert_one({"_id": user_id, "added_at": time.time()})
            bot.send_message(m.from_user.id, f"✅ Admin {user_id} added!")
            try:
                bot.send_message(user_id, "🎉 You are now an admin!")
            except:
                pass
        else:  # removeadmin
            if user_id == ADMIN_ID:
                bot.send_message(m.from_user.id, "❌ Cannot remove owner!")
                return
            result = admins_col.delete_one({"_id": user_id})
            if result.deleted_count > 0:
                bot.send_message(m.from_user.id, f"✅ Admin {user_id} removed!")
            else:
                bot.send_message(m.from_user.id, "❌ Not an admin!")
    except:
        bot.send_message(m.from_user.id, f"❌ Use: /{cmd} user_id")

# =========================
# 🧠 FALLBACK
# =========================
@bot.message_handler(func=lambda m: True)
def fallback(m):
    if m.text and m.text not in ["📂 FREE METHODS", "💎 VIP METHODS", "📱 PREMIUM APPS", "⚡ SERVICES", "💰 BALANCE", "⭐ VIP ACCESS", "🎁 REFERRAL", "👤 PROFILE", "🎫 REDEEM", "💎 BUY POINTS", "⚙️ ADMIN"]:
        config = get_config()
        for btn in config.get("custom_buttons", []):
            if m.text == btn["text"]:
                if btn["type"] == "link":
                    keyboard = InlineKeyboardMarkup()
                    keyboard.add(InlineKeyboardButton("🔗 Open", url=btn["data"]))
                    bot.send_message(m.from_user.id, f"🔗 {btn['text']}", reply_markup=keyboard)
                elif btn["type"] == "folder":
                    folder = fs.get_folder_by_number(int(btn["data"]))
                    if folder:
                        fake_callback = type('obj', (object,), {'from_user': m.from_user, 'id': m.message_id, 'data': f"open_{folder['category']}_{folder['name']}"})
                        open_folder_callback(fake_callback)
                return
        bot.send_message(m.from_user.id, "❌ Use menu buttons", reply_markup=get_main_keyboard(m.from_user.id))

# =========================
# 🏃‍♂️ RUN BOT
# =========================
def run_bot():
    while True:
        try:
            logger.info("=" * 50)
            logger.info("🚀 ZEDOX BOT - OPTIMIZED VERSION")
            logger.info(f"✅ Bot: @{bot.get_me().username}")
            logger.info(f"👑 Owner: {ADMIN_ID}")
            logger.info(f"💾 MongoDB: Connected & Optimized")
            logger.info(f"⚡ Caching: Enabled")
            logger.info("=" * 50)
            
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logger.error(f"Bot error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_bot()
