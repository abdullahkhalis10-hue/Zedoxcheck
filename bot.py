# =========================
# ZEDOX BOT - ULTIMATE WORKING VERSION
# With Fixed Code Generation & Edit Folder Material
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
from pymongo import MongoClient
from datetime import datetime, timedelta
from functools import wraps

# =========================
# 📋 LOGGING SETUP
# =========================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
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
# 🌐 MONGODB SETUP
# =========================
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable not set!")

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client["zedox_bot"]
    logger.info("✅ MongoDB connected successfully!")
except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")
    raise

# Collections
users_col = db["users"]
folders_col = db["folders"]
codes_col = db["codes"]
config_col = db["config"]
admins_col = db["admins"]

# Create indexes for better performance
try:
    users_col.create_index("points")
    users_col.create_index("vip")
    folders_col.create_index([("cat", 1), ("parent", 1)])
    folders_col.create_index("number", unique=True, sparse=True)
    codes_col.create_index("code")
    logger.info("✅ Database indexes created!")
except Exception as e:
    logger.warning(f"Index creation warning: {e}")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# =========================
# 🔐 HELPER FUNCTIONS
# =========================
def is_admin(user_id):
    """Check if user is admin"""
    if user_id == ADMIN_ID:
        return True
    return admins_col.find_one({"_id": user_id}) is not None

def get_config():
    """Get bot configuration"""
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
    return config

def update_config(key, value):
    """Update bot configuration"""
    config_col.update_one({"_id": "main_config"}, {"$set": {key: value}}, upsert=True)

def get_next_folder_number():
    """Get next available folder number"""
    config = get_config()
    number = config.get("next_folder_number", 1)
    update_config("next_folder_number", number + 1)
    return number

# =========================
# 👤 USER CLASS
# =========================
class User:
    def __init__(self, user_id):
        self.user_id = str(user_id)
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
    
    def save(self):
        """Save user data"""
        users_col.update_one({"_id": self.user_id}, {"$set": self.data})
    
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
        """Get user points"""
        return self.data["points"]
    
    def is_vip(self):
        """Check if user is VIP"""
        return self.data.get("is_vip", False)
    
    def make_vip(self):
        """Make user VIP"""
        self.data["is_vip"] = True
        self.save()
    
    def remove_vip(self):
        """Remove VIP status"""
        self.data["is_vip"] = False
        self.save()
    
    def add_referral(self, referrer_id):
        """Add referral"""
        if not self.data.get("referred_by"):
            self.data["referred_by"] = str(referrer_id)
            self.save()
            
            # Give points to referrer
            reward = get_config().get("referral_reward", 5)
            referrer = User(referrer_id)
            referrer.add_points(reward)
            referrer.data["referrals_count"] += 1
            referrer.save()
            return True
        return False
    
    def purchase_item(self, item_name, price):
        """Purchase an item"""
        if self.remove_points(price):
            if item_name not in self.data["purchased_items"]:
                self.data["purchased_items"].append(item_name)
                self.save()
            return True
        return False
    
    def has_purchased(self, item_name):
        """Check if user purchased an item"""
        return item_name in self.data.get("purchased_items", [])
    
    def add_used_code(self, code):
        """Add used code to user"""
        if code not in self.data["used_codes"]:
            self.data["used_codes"].append(code)
            self.save()
            return True
        return False
    
    def has_used_code(self, code):
        """Check if user used a code"""
        return code in self.data.get("used_codes", [])
    
    def update_username(self, username, first_name):
        """Update user info"""
        self.data["username"] = username
        self.data["first_name"] = first_name
        self.save()

# =========================
# 📁 FOLDER SYSTEM
# =========================
class FolderSystem:
    def __init__(self):
        pass
    
    def add_folder(self, category, name, files, price, parent=None, text_content=None):
        """Add a new folder"""
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
        return number
    
    def get_folders(self, category, parent=None):
        """Get folders by category and parent"""
        query = {"category": category}
        if parent:
            query["parent"] = parent
        else:
            query["parent"] = None
        
        return list(folders_col.find(query).sort("number", 1))
    
    def get_folder(self, category, name, parent=None):
        """Get a specific folder"""
        query = {"category": category, "name": name}
        if parent:
            query["parent"] = parent
        
        return folders_col.find_one(query)
    
    def get_folder_by_number(self, number):
        """Get folder by number"""
        return folders_col.find_one({"number": number})
    
    def delete_folder(self, category, name, parent=None):
        """Delete a folder and its subfolders"""
        query = {"category": category, "name": name}
        if parent:
            query["parent"] = parent
        else:
            query["parent"] = None
        
        # Get folder to delete
        folder = folders_col.find_one(query)
        if not folder:
            return False
        
        # Delete all subfolders recursively
        folders_col.delete_many({"category": category, "parent": name})
        
        # Delete the folder itself
        folders_col.delete_one(query)
        
        # Reorganize numbers
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
        
        return True
    
    def update_price(self, category, name, price, parent=None):
        """Update folder price"""
        query = {"category": category, "name": name}
        if parent:
            query["parent"] = parent
        
        folders_col.update_one(query, {"$set": {"price": price}})
    
    def update_name(self, category, old_name, new_name, parent=None):
        """Update folder name"""
        query = {"category": category, "name": old_name}
        if parent:
            query["parent"] = parent
        
        folders_col.update_one(query, {"$set": {"name": new_name}})
        
        # Update parent references in subfolders
        folders_col.update_many(
            {"category": category, "parent": old_name},
            {"$set": {"parent": new_name}}
        )
    
    def move_folder(self, number, new_parent):
        """Move folder to new parent"""
        folders_col.update_one({"number": number}, {"$set": {"parent": new_parent}})
    
    def update_content(self, category, name, content_type, content, parent=None):
        """Update folder content (text or files)"""
        query = {"category": category, "name": name}
        if parent:
            query["parent"] = parent
        
        if content_type == "text":
            folders_col.update_one(query, {"$set": {"text_content": content}})
        elif content_type == "files":
            folders_col.update_one(query, {"$set": {"files": content}})
        
        return True
    
    def get_folder_content(self, category, name, parent=None):
        """Get folder content"""
        query = {"category": category, "name": name}
        if parent:
            query["parent"] = parent
        
        folder = folders_col.find_one(query)
        if folder:
            if folder.get("text_content"):
                return "text", folder["text_content"]
            elif folder.get("files"):
                return "files", folder["files"]
        return None, None

fs = FolderSystem()

# =========================
# 🎫 CODES SYSTEM
# =========================
class CodeSystem:
    def generate_codes(self, points, count, multi_use=False, expiry_days=None):
        """Generate redeem codes"""
        codes = []
        expiry_time = time.time() + (expiry_days * 86400) if expiry_days else None
        
        for _ in range(count):
            code = "ZEDOX" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            
            code_data = {
                "_id": code,
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
        return list(codes_col.find({}).sort("created_at", -1))

code_system = CodeSystem()

# =========================
# 📊 POINTS PACKAGES
# =========================
def get_points_packages():
    """Get points packages"""
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
    """Save points packages"""
    config_col.update_one(
        {"_id": "points_packages"},
        {"$set": {"packages": packages}},
        upsert=True
    )

# =========================
# 🚫 FORCE JOIN CHECK
# =========================
def check_force_join(user_id):
    """Check if user joined required channels"""
    config = get_config()
    force_channels = config.get("force_channels", [])
    
    if not force_channels:
        return True
    
    for channel in force_channels:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    
    return True

def force_join_handler(func):
    """Decorator for force join check"""
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
                "🚫 <b>Access Restricted!</b>\n\nPlease join the following channels to use this bot:",
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
    """Get main menu keyboard"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    keyboard.add("📂 FREE METHODS", "💎 VIP METHODS")
    keyboard.add("📱 PREMIUM APPS", "⚡ SERVICES")
    keyboard.add("💰 BALANCE", "⭐ VIP ACCESS")
    keyboard.add("🎁 REFERRAL", "👤 PROFILE")
    keyboard.add("🎫 REDEEM", "💎 BUY POINTS")
    
    if is_admin(user_id):
        keyboard.add("⚙️ ADMIN")
    
    # Add custom buttons
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
    """Get admin panel keyboard"""
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
    """Handle /start command"""
    user_id = message.from_user.id
    user = User(user_id)
    
    # Update user info
    user.update_username(
        message.from_user.username,
        message.from_user.first_name
    )
    
    # Check for referral
    args = message.text.split()
    if len(args) > 1:
        referrer_id = args[1]
        if referrer_id.isdigit() and int(referrer_id) != user_id:
            user.add_referral(referrer_id)
            
            # Notify referrer
            try:
                bot.send_message(
                    int(referrer_id),
                    f"🎉 <b>New Referral!</b>\n\n"
                    f"@{message.from_user.username or user_id} joined using your link!\n"
                    f"You earned +{get_config().get('referral_reward', 5)} points!",
                    parse_mode="HTML"
                )
            except:
                pass
    
    # Welcome message
    config = get_config()
    welcome_msg = config.get("welcome_message", "Welcome to ZEDOX BOT!")
    
    bot.send_message(
        user_id,
        f"{welcome_msg}\n\n"
        f"💰 <b>Your Points:</b> {user.get_points()}\n"
        f"👑 <b>VIP Status:</b> {'✅ Active' if user.is_vip() else '❌ Not Active'}",
        reply_markup=get_main_keyboard(user_id),
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def check_join_callback(call):
    """Handle force join check"""
    user_id = call.from_user.id
    
    if check_force_join(user_id):
        bot.edit_message_text(
            "✅ <b>Access Granted!</b>\n\nWelcome to ZEDOX BOT!",
            user_id,
            call.message.message_id,
            parse_mode="HTML"
        )
        
        user = User(user_id)
        bot.send_message(
            user_id,
            f"🎉 Welcome! Use the menu below.\n\n💰 Points: {user.get_points()}",
            reply_markup=get_main_keyboard(user_id)
        )
    else:
        bot.answer_callback_query(call.id, "❌ Please join all channels first!", show_alert=True)

# =========================
# 📂 CATEGORY HANDLERS
# =========================
def show_category_folders(user_id, category, title):
    """Show folders in a category"""
    folders = fs.get_folders(category)
    
    if not folders:
        bot.send_message(user_id, f"📁 <b>{title}</b>\n\nNo content available yet!", parse_mode="HTML")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    for folder in folders:
        name = folder["name"]
        number = folder.get("number", "?")
        price = folder.get("price", 0)
        
        has_subfolders = len(fs.get_folders(category, name)) > 0
        icon = "📁" if has_subfolders else "📄"
        
        text = f"{icon} [{number}] {name}"
        if price > 0:
            text += f" - {price} pts"
        
        keyboard.add(InlineKeyboardButton(
            text,
            callback_data=f"open_{category}_{name}"
        ))
    
    bot.send_message(
        user_id,
        f"📁 <b>{title}</b>\n\nSelect an option:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: m.text == "📂 FREE METHODS")
@force_join_handler
def free_methods(message):
    """Show free methods"""
    show_category_folders(message.from_user.id, "free", "FREE METHODS")

@bot.message_handler(func=lambda m: m.text == "💎 VIP METHODS")
@force_join_handler
def vip_methods(message):
    """Show VIP methods"""
    show_category_folders(message.from_user.id, "vip", "VIP METHODS")

@bot.message_handler(func=lambda m: m.text == "📱 PREMIUM APPS")
@force_join_handler
def apps_methods(message):
    """Show premium apps"""
    show_category_folders(message.from_user.id, "apps", "PREMIUM APPS")

@bot.message_handler(func=lambda m: m.text == "⚡ SERVICES")
@force_join_handler
def services_methods(message):
    """Show services"""
    show_category_folders(message.from_user.id, "services", "SERVICES")

# =========================
# 📂 FOLDER NAVIGATION
# =========================
@bot.callback_query_handler(func=lambda call: call.data.startswith("open_"))
def open_folder_callback(call):
    """Handle folder opening"""
    user_id = call.from_user.id
    user = User(user_id)
    
    parts = call.data.split("_")
    category = parts[1]
    name = parts[2]
    
    folder = fs.get_folder(category, name)
    if not folder:
        bot.answer_callback_query(call.id, "❌ Folder not found!")
        return
    
    # Check for subfolders
    subfolders = fs.get_folders(category, name)
    if subfolders:
        keyboard = InlineKeyboardMarkup(row_width=1)
        
        for sub in subfolders:
            sub_name = sub["name"]
            sub_number = sub.get("number", "?")
            sub_price = sub.get("price", 0)
            
            text = f"📁 [{sub_number}] {sub_name}"
            if sub_price > 0:
                text += f" - {sub_price} pts"
            
            keyboard.add(InlineKeyboardButton(
                text,
                callback_data=f"open_{category}_{sub_name}"
            ))
        
        keyboard.add(InlineKeyboardButton("🔙 BACK", callback_data=f"back_{category}"))
        
        bot.edit_message_text(
            f"📁 <b>{name}</b>\n\nSelect an option:",
            user_id,
            call.message.message_id,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        bot.answer_callback_query(call.id)
        return
    
    # Handle text content
    text_content = folder.get("text_content")
    if text_content:
        price = folder.get("price", 0)
        
        # Check access
        can_access = user.is_vip() or user.has_purchased(name)
        
        if not can_access and price > 0:
            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                InlineKeyboardButton(f"💰 Buy for {price} pts", callback_data=f"buy_{category}_{name}_{price}"),
                InlineKeyboardButton("⭐ Get VIP", callback_data="get_vip")
            )
            keyboard.add(InlineKeyboardButton("💎 Buy Points", callback_data="buy_points"))
            
            bot.edit_message_text(
                f"🔒 <b>VIP Content: {name}</b>\n\n"
                f"💰 Price: {price} points\n"
                f"💎 Your points: {user.get_points()}\n\n"
                f"Choose an option to access:",
                user_id,
                call.message.message_id,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            bot.answer_callback_query(call.id, "🔒 This is premium content!")
            return
        
        if not can_access and price == 0:
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("⭐ Get VIP", callback_data="get_vip"))
            
            bot.edit_message_text(
                f"🔒 <b>VIP Content: {name}</b>\n\n"
                f"This content is only available for VIP members!\n\n"
                f"Get VIP to unlock all content!",
                user_id,
                call.message.message_id,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            bot.answer_callback_query(call.id, "🔒 VIP only content!")
            return
        
        # Deduct points if not VIP
        if not user.is_vip() and price > 0:
            if user.get_points() >= price:
                user.remove_points(price)
                user.purchase_item(name, price)
                bot.answer_callback_query(call.id, f"✅ {price} points deducted!")
            else:
                bot.answer_callback_query(call.id, f"❌ Need {price} points! You have {user.get_points()}", show_alert=True)
                return
        
        # Send content
        bot.edit_message_text(
            f"📄 <b>{name}</b>\n\n{text_content}",
            user_id,
            call.message.message_id,
            parse_mode="HTML"
        )
        bot.answer_callback_query(call.id)
        return
    
    # Handle files
    files = folder.get("files", [])
    price = folder.get("price", 0)
    
    # Check access
    can_access = user.is_vip() or user.has_purchased(name)
    
    if not can_access and price > 0:
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton(f"💰 Buy for {price} pts", callback_data=f"buy_{category}_{name}_{price}"),
            InlineKeyboardButton("⭐ Get VIP", callback_data="get_vip")
        )
        keyboard.add(InlineKeyboardButton("💎 Buy Points", callback_data="buy_points"))
        
        bot.edit_message_text(
            f"🔒 <b>VIP Content: {name}</b>\n\n"
            f"💰 Price: {price} points\n"
            f"💎 Your points: {user.get_points()}\n\n"
            f"Choose an option to access:",
            user_id,
            call.message.message_id,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        bot.answer_callback_query(call.id, "🔒 This is premium content!")
        return
    
    if not can_access and price == 0:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("⭐ Get VIP", callback_data="get_vip"))
        
        bot.edit_message_text(
            f"🔒 <b>VIP Content: {name}</b>\n\n"
            f"This content is only available for VIP members!\n\n"
            f"Get VIP to unlock all content!",
            user_id,
            call.message.message_id,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        bot.answer_callback_query(call.id, "🔒 VIP only content!")
        return
    
    # Deduct points if not VIP
    if not user.is_vip() and price > 0:
        if user.get_points() >= price:
            user.remove_points(price)
            user.purchase_item(name, price)
            bot.answer_callback_query(call.id, f"✅ {price} points deducted!")
        else:
            bot.answer_callback_query(call.id, f"❌ Need {price} points! You have {user.get_points()}", show_alert=True)
            return
    
    # Send files
    bot.answer_callback_query(call.id, "📤 Sending files...")
    
    for file in files:
        try:
            if file.get("type") == "document":
                bot.copy_message(user_id, file["chat"], file["msg"])
            elif file.get("type") == "photo":
                bot.copy_message(user_id, file["chat"], file["msg"])
            elif file.get("type") == "video":
                bot.copy_message(user_id, file["chat"], file["msg"])
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"Failed to send file: {e}")
    
    config = get_config()
    if config.get("send_notifications", True):
        bot.send_message(user_id, f"✅ Files sent successfully!", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("back_"))
def back_callback(call):
    """Handle back button"""
    category = call.data.split("_")[1]
    
    title_map = {
        "free": "FREE METHODS",
        "vip": "VIP METHODS",
        "apps": "PREMIUM APPS",
        "services": "SERVICES"
    }
    
    show_category_folders(call.from_user.id, category, title_map.get(category, category.upper()))
    bot.answer_callback_query(call.id)

# =========================
# 💰 PURCHASE HANDLERS
# =========================
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def buy_item_callback(call):
    """Handle item purchase"""
    user_id = call.from_user.id
    user = User(user_id)
    
    parts = call.data.split("_")
    category = parts[1]
    name = parts[2]
    price = int(parts[3])
    
    if user.is_vip():
        bot.answer_callback_query(call.id, "✅ You're VIP! You have free access!", show_alert=True)
        return
    
    if user.has_purchased(name):
        bot.answer_callback_query(call.id, "✅ You already own this item!", show_alert=True)
        return
    
    if user.get_points() >= price:
        user.remove_points(price)
        user.purchase_item(name, price)
        
        bot.answer_callback_query(call.id, f"✅ Purchased! {price} points deducted!", show_alert=True)
        
        # Open the folder after purchase
        folder = fs.get_folder(category, name)
        if folder:
            text_content = folder.get("text_content")
            if text_content:
                bot.edit_message_text(
                    f"📄 <b>{name}</b>\n\n{text_content}",
                    user_id,
                    call.message.message_id,
                    parse_mode="HTML"
                )
            else:
                bot.edit_message_text(
                    f"✅ <b>Purchase Successful!</b>\n\n"
                    f"You now own: {name}\n"
                    f"Remaining points: {user.get_points()}\n\n"
                    f"Click the folder again to access it!",
                    user_id,
                    call.message.message_id,
                    parse_mode="HTML"
                )
    else:
        bot.answer_callback_query(
            call.id,
            f"❌ Need {price} points! You have {user.get_points()}",
            show_alert=True
        )

# =========================
# 💎 POINTS & VIP HANDLERS
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 BALANCE")
@force_join_handler
def balance_command(message):
    """Show user balance"""
    user_id = message.from_user.id
    user = User(user_id)
    
    purchased_count = len(user.data.get("purchased_items", []))
    
    text = (
        f"💰 <b>YOUR BALANCE</b> 💰\n\n"
        f"┌ <b>Points:</b> {user.get_points()}\n"
        f"├ <b>VIP Status:</b> {'✅ Active' if user.is_vip() else '❌ Not Active'}\n"
        f"├ <b>Purchased Items:</b> {purchased_count}\n"
        f"├ <b>Referrals:</b> {user.data.get('referrals_count', 0)}\n"
        f"├ <b>Total Earned:</b> {user.data.get('total_points_earned', 0)}\n"
        f"└ <b>Total Spent:</b> {user.data.get('total_points_spent', 0)}\n\n"
        f"💡 <b>Earn More Points:</b>\n"
        f"• Invite friends using referral link\n"
        f"• Redeem codes from admin\n"
        f"• Purchase points packages"
    )
    
    bot.send_message(user_id, text, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "⭐ VIP ACCESS")
@force_join_handler
def vip_command(message):
    """Show VIP information"""
    user_id = message.from_user.id
    user = User(user_id)
    
    if user.is_vip():
        bot.send_message(
            user_id,
            "✅ <b>You are a VIP Member!</b>\n\n"
            "✨ <b>VIP Benefits:</b>\n"
            "• Access to all VIP METHODS\n"
            "• No points needed for VIP items\n"
            "• Priority support\n"
            "• Exclusive offers\n\n"
            f"💰 Points: {user.get_points()}",
            parse_mode="HTML"
        )
        return
    
    config = get_config()
    vip_contact = config.get("vip_contact", "Contact admin")
    
    text = (
        f"⭐ <b>VIP ACCESS</b> ⭐\n\n"
        f"✨ <b>Benefits:</b>\n"
        f"• Access to ALL VIP METHODS\n"
        f"• No points needed for VIP items\n"
        f"• Priority customer support\n"
        f"• Exclusive VIP-only content\n"
        f"• Special offers and bonuses\n\n"
        f"💰 <b>Current Points:</b> {user.get_points()}\n\n"
        f"📞 <b>Contact to become VIP:</b>\n{vip_contact}\n\n"
        f"🆔 Your ID: <code>{user_id}</code>"
    )
    
    keyboard = InlineKeyboardMarkup()
    if config.get("vip_contact") and config.get("vip_contact").startswith("http"):
        keyboard.add(InlineKeyboardButton("📞 Contact Admin", url=config.get("vip_contact")))
    
    bot.send_message(user_id, text, reply_markup=keyboard if keyboard.keyboard else None, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "💎 BUY POINTS")
@force_join_handler
def buy_points_command(message):
    """Show points packages"""
    user_id = message.from_user.id
    user = User(user_id)
    
    packages = get_points_packages()
    active_packages = [p for p in packages if p.get("active", True)]
    
    config = get_config()
    contact = config.get("contact_username") or config.get("contact_link") or "Contact admin"
    
    text = f"💎 <b>BUY POINTS</b> 💎\n\n"
    text += f"💰 <b>Your Balance:</b> {user.get_points()} points\n\n"
    
    if active_packages:
        text += f"📦 <b>Available Packages:</b>\n\n"
        for i, pkg in enumerate(active_packages, 1):
            total = pkg["points"] + pkg.get("bonus", 0)
            text += f"<b>{i}.</b> {pkg['points']} points"
            if pkg.get("bonus", 0) > 0:
                text += f" + {pkg['bonus']} BONUS"
            text += f"\n   💰 Price: ${pkg['price_usd']}\n"
            text += f"   📦 Total: {total} points\n\n"
    
    text += f"📞 <b>How to Purchase:</b>\n"
    text += f"1. Contact: {contact}\n"
    text += f"2. Send your User ID: <code>{user_id}</code>\n"
    text += f"3. Choose a package\n"
    text += f"4. Complete payment\n"
    text += f"5. Get points added instantly!\n\n"
    text += f"💳 <b>Payment Methods:</b>\n"
    text += f"• Cryptocurrency (USDT, BTC)\n"
    text += f"• Bank Transfer\n"
    text += f"• E-wallets\n\n"
    text += f"⚡ Fast delivery within minutes!"
    
    keyboard = InlineKeyboardMarkup()
    if config.get("contact_link"):
        keyboard.add(InlineKeyboardButton("📞 Contact Admin", url=config.get("contact_link")))
    elif config.get("contact_username"):
        keyboard.add(InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{config.get('contact_username').replace('@', '')}"))
    
    bot.send_message(user_id, text, reply_markup=keyboard if keyboard.keyboard else None, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "buy_points")
def buy_points_callback(call):
    """Handle buy points from callback"""
    buy_points_command(call.message)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "get_vip")
def get_vip_callback(call):
    """Handle get VIP from callback"""
    vip_command(call.message)
    bot.answer_callback_query(call.id)

# =========================
# 🎁 REFERRAL HANDLER
# =========================
@bot.message_handler(func=lambda m: m.text == "🎁 REFERRAL")
@force_join_handler
def referral_command(message):
    """Show referral information"""
    user_id = message.from_user.id
    user = User(user_id)
    
    bot_username = bot.get_me().username
    referral_link = f"https://t.me/{bot_username}?start={user_id}"
    
    reward = get_config().get("referral_reward", 5)
    
    text = (
        f"🎁 <b>REFERRAL SYSTEM</b> 🎁\n\n"
        f"🔗 <b>Your Referral Link:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"👥 <b>Your Referrals:</b> {user.data.get('referrals_count', 0)}\n"
        f"💰 <b>Reward per Referral:</b> +{reward} points\n"
        f"💎 <b>Total Earned:</b> {user.data.get('referrals_count', 0) * reward} points\n\n"
        f"✨ <b>How it works:</b>\n"
        f"• Share your link with friends\n"
        f"• When they join, you get +{reward} points\n"
        f"• More referrals = more points!\n\n"
        f"💡 <b>Pro tip:</b> Share in groups for maximum referrals!"
    )
    
    bot.send_message(user_id, text, parse_mode="HTML")

# =========================
# 👤 PROFILE HANDLER
# =========================
@bot.message_handler(func=lambda m: m.text == "👤 PROFILE")
@force_join_handler
def profile_command(message):
    """Show user profile"""
    user_id = message.from_user.id
    user = User(user_id)
    
    purchased_items = user.data.get("purchased_items", [])
    purchased_text = "\n".join([f"• {item}" for item in purchased_items[:10]])
    if len(purchased_items) > 10:
        purchased_text += f"\n• ... and {len(purchased_items) - 10} more"
    
    text = (
        f"👤 <b>USER PROFILE</b>\n\n"
        f"┌ <b>User ID:</b> <code>{user_id}</code>\n"
        f"├ <b>Name:</b> {message.from_user.first_name}\n"
        f"├ <b>Username:</b> @{message.from_user.username or 'None'}\n"
        f"├ <b>VIP Status:</b> {'✅ Active' if user.is_vip() else '❌ Not Active'}\n"
        f"├ <b>Points:</b> {user.get_points()}\n"
        f"├ <b>Referrals:</b> {user.data.get('referrals_count', 0)}\n"
        f"├ <b>Purchased Items:</b> {len(purchased_items)}\n"
        f"├ <b>Total Earned:</b> {user.data.get('total_points_earned', 0)}\n"
        f"└ <b>Total Spent:</b> {user.data.get('total_points_spent', 0)}\n"
    )
    
    if purchased_items:
        text += f"\n📚 <b>Your Items:</b>\n{purchased_text}"
    
    bot.send_message(user_id, text, parse_mode="HTML")

# =========================
# 🎫 REDEEM HANDLER
# =========================
@bot.message_handler(func=lambda m: m.text == "🎫 REDEEM")
@force_join_handler
def redeem_command(message):
    """Handle redeem code"""
    msg = bot.send_message(
        message.from_user.id,
        "🎫 <b>REDEEM CODE</b>\n\nPlease enter your code:",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_redeem)

def process_redeem(message):
    """Process redeem code"""
    user_id = message.from_user.id
    user = User(user_id)
    code = message.text.strip().upper()
    
    success, result = code_system.redeem_code(code, user)
    
    if success:
        bot.send_message(
            user_id,
            f"✅ <b>Code Redeemed!</b>\n\n{result}\n"
            f"💰 <b>New Balance:</b> {user.get_points()} points",
            parse_mode="HTML"
        )
    else:
        bot.send_message(user_id, result, parse_mode="HTML")

# =========================
# ⚙️ ADMIN PANEL
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN" and is_admin(m.from_user.id))
def admin_panel(message):
    """Show admin panel"""
    bot.send_message(
        message.from_user.id,
        "⚙️ <b>ADMIN CONTROL PANEL</b>\n\nSelect an option:",
        reply_markup=get_admin_keyboard(),
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: m.text == "◀️ BACK TO MENU" and is_admin(m.from_user.id))
def back_to_menu(message):
    """Back to main menu"""
    bot.send_message(
        message.from_user.id,
        "Returning to main menu...",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

# =========================
# 📤 UPLOAD HANDLERS
# =========================
upload_sessions = {}

def start_upload_process(user_id, category, is_service=False):
    """Start upload process"""
    upload_sessions[user_id] = {
        "category": category,
        "is_service": is_service,
        "files": [],
        "step": "name"
    }
    
    msg = bot.send_message(
        user_id,
        "📤 <b>UPLOAD CONTENT</b>\n\n"
        "Send the <b>folder name</b>:\n\n"
        "Type /cancel to cancel",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_upload_name)

def process_upload_name(message):
    """Process upload folder name"""
    user_id = message.from_user.id
    
    if message.text == "/cancel":
        if user_id in upload_sessions:
            del upload_sessions[user_id]
        bot.send_message(user_id, "❌ Upload cancelled!", reply_markup=get_admin_keyboard())
        return
    
    if user_id not in upload_sessions:
        start_upload_process(user_id, upload_sessions.get(user_id, {}).get("category", "free"))
        return
    
    upload_sessions[user_id]["name"] = message.text
    upload_sessions[user_id]["step"] = "price"
    
    msg = bot.send_message(
        user_id,
        f"💰 <b>Set Price</b>\n\n"
        f"Enter price in points (0 for free):",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_upload_price)

def process_upload_price(message):
    """Process upload price"""
    user_id = message.from_user.id
    
    if message.text == "/cancel":
        if user_id in upload_sessions:
            del upload_sessions[user_id]
        bot.send_message(user_id, "❌ Upload cancelled!", reply_markup=get_admin_keyboard())
        return
    
    try:
        price = int(message.text)
        upload_sessions[user_id]["price"] = price
        upload_sessions[user_id]["step"] = "content_type"
        
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        keyboard.add("📝 Text Content", "📁 File Upload")
        keyboard.add("/cancel")
        
        msg = bot.send_message(
            user_id,
            f"📤 <b>Choose Content Type</b>\n\n"
            f"Select how you want to add content:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_upload_type)
    except:
        bot.send_message(user_id, "❌ Invalid price! Please enter a number.")
        msg = bot.send_message(user_id, "💰 Enter price in points (0 for free):")
        bot.register_next_step_handler(msg, process_upload_price)

def process_upload_type(message):
    """Process upload content type"""
    user_id = message.from_user.id
    
    if message.text == "/cancel":
        if user_id in upload_sessions:
            del upload_sessions[user_id]
        bot.send_message(user_id, "❌ Upload cancelled!", reply_markup=get_admin_keyboard())
        return
    
    if message.text == "📝 Text Content":
        upload_sessions[user_id]["type"] = "text"
        upload_sessions[user_id]["step"] = "content"
        
        msg = bot.send_message(
            user_id,
            "📝 <b>Enter Text Content</b>\n\n"
            "Send the text/content for this folder:",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_upload_text)
    
    elif message.text == "📁 File Upload":
        upload_sessions[user_id]["type"] = "files"
        upload_sessions[user_id]["step"] = "files"
        
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add("/done", "/cancel")
        
        msg = bot.send_message(
            user_id,
            "📁 <b>Upload Files</b>\n\n"
            "Send files (documents, photos, videos)\n"
            "Press /done when finished:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_upload_files)
    else:
        bot.send_message(user_id, "❌ Invalid choice!")
        process_upload_price(message)

def process_upload_text(message):
    """Process upload text content"""
    user_id = message.from_user.id
    
    if message.text == "/cancel":
        if user_id in upload_sessions:
            del upload_sessions[user_id]
        bot.send_message(user_id, "❌ Upload cancelled!", reply_markup=get_admin_keyboard())
        return
    
    session = upload_sessions[user_id]
    text_content = message.text
    
    # Save to database
    number = fs.add_folder(
        session["category"],
        session["name"],
        [],
        session["price"],
        text_content=text_content
    )
    
    if session.get("is_service"):
        # For services, also save service message
        folder = fs.get_folder(session["category"], session["name"])
        if folder:
            folders_col.update_one(
                {"_id": folder["_id"]},
                {"$set": {"service_msg": text_content}}
            )
    
    bot.send_message(
        user_id,
        f"✅ <b>Upload Successful!</b>\n\n"
        f"📌 Number: {number}\n"
        f"📂 Name: {session['name']}\n"
        f"💰 Price: {session['price']} points\n"
        f"📝 Type: Text Content",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard()
    )
    
    del upload_sessions[user_id]

def process_upload_files(message):
    """Process upload files"""
    user_id = message.from_user.id
    
    if message.text == "/cancel":
        if user_id in upload_sessions:
            del upload_sessions[user_id]
        bot.send_message(user_id, "❌ Upload cancelled!", reply_markup=get_admin_keyboard())
        return
    
    if message.text == "/done":
        session = upload_sessions[user_id]
        
        if not session["files"]:
            bot.send_message(user_id, "❌ No files uploaded!")
            return
        
        # Save to database
        number = fs.add_folder(
            session["category"],
            session["name"],
            session["files"],
            session["price"]
        )
        
        bot.send_message(
            user_id,
            f"✅ <b>Upload Successful!</b>\n\n"
            f"📌 Number: {number}\n"
            f"📂 Name: {session['name']}\n"
            f"💰 Price: {session['price']} points\n"
            f"📁 Files: {len(session['files'])}",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard()
        )
        
        del upload_sessions[user_id]
        return
    
    # Save file
    if message.content_type in ["document", "photo", "video"]:
        upload_sessions[user_id]["files"].append({
            "chat": message.chat.id,
            "msg": message.message_id,
            "type": message.content_type
        })
        bot.send_message(user_id, f"✅ File saved! ({len(upload_sessions[user_id]['files'])} files)")
    else:
        bot.send_message(user_id, "❌ Please send documents, photos, or videos only!")
    
    # Continue listening
    bot.register_next_step_handler(message, process_upload_files)

@bot.message_handler(func=lambda m: m.text == "📤 UPLOAD FREE" and is_admin(m.from_user.id))
def upload_free(message):
    start_upload_process(message.from_user.id, "free")

@bot.message_handler(func=lambda m: m.text == "📤 UPLOAD VIP" and is_admin(m.from_user.id))
def upload_vip(message):
    start_upload_process(message.from_user.id, "vip")

@bot.message_handler(func=lambda m: m.text == "📤 UPLOAD APPS" and is_admin(m.from_user.id))
def upload_apps(message):
    start_upload_process(message.from_user.id, "apps")

@bot.message_handler(func=lambda m: m.text == "📤 UPLOAD SERVICE" and is_admin(m.from_user.id))
def upload_service(message):
    start_upload_process(message.from_user.id, "services", is_service=True)

# =========================
# 🗑 DELETE FOLDER - IMPROVED
# =========================
@bot.message_handler(func=lambda m: m.text == "🗑 DELETE FOLDER" and is_admin(m.from_user.id))
def delete_folder_command(message):
    """Delete folder"""
    msg = bot.send_message(
        message.from_user.id,
        "🗑 <b>DELETE FOLDER</b>\n\n"
        "Send: <code>category folder_name</code>\n\n"
        "Categories: free, vip, apps, services\n\n"
        "Examples:\n"
        "<code>services Amazon Prime 6 Months</code>\n"
        "<code>vip My VIP Method</code>\n\n"
        "⚠️ This will delete the folder AND all its subfolders!",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_delete_folder)

def process_delete_folder(message):
    """Process folder deletion"""
    user_id = message.from_user.id
    
    try:
        # Split by first space only (category) and the rest is folder name
        first_space = message.text.find(' ')
        if first_space == -1:
            bot.send_message(user_id, "❌ Invalid format! Use: category folder_name")
            return
        
        category = message.text[:first_space].lower().strip()
        name = message.text[first_space+1:].strip()
        
        # Remove quotes if present
        if name.startswith('"') and name.endswith('"'):
            name = name[1:-1]
        if name.startswith("'") and name.endswith("'"):
            name = name[1:-1]
        
        if category not in ["free", "vip", "apps", "services"]:
            bot.send_message(user_id, "❌ Invalid category! Use: free, vip, apps, or services")
            return
        
        # First, try to find the folder exactly as typed
        folder = fs.get_folder(category, name)
        
        # If not found, try case-insensitive search
        if not folder:
            all_folders = fs.get_folders(category)
            for f in all_folders:
                if f["name"].lower() == name.lower():
                    folder = f
                    name = f["name"]  # Use the correct case
                    break
        
        if not folder:
            # Show available folders
            available = fs.get_folders(category)
            if available:
                available_names = "\n".join([f"• {f['name']}" for f in available[:10]])
                bot.send_message(
                    user_id,
                    f"❌ <b>Folder Not Found!</b>\n\n"
                    f"Could not find '{name}' in {category.upper()}\n\n"
                    f"<b>Available folders in {category.upper()}:</b>\n{available_names}",
                    parse_mode="HTML"
                )
            else:
                bot.send_message(user_id, f"❌ No folders found in {category.upper()}!")
            return
        
        # Confirm deletion
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("✅ Yes, Delete", callback_data=f"confirm_del_{category}_{name}"),
            InlineKeyboardButton("❌ No, Cancel", callback_data="cancel_del")
        )
        
        bot.send_message(
            user_id,
            f"⚠️ <b>Confirm Deletion</b>\n\n"
            f"Delete '<b>{name}</b>' from {category.upper()}?\n\n"
            f"This will also delete all subfolders inside it!",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        bot.send_message(user_id, f"❌ Error: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_del_"))
def confirm_delete_callback(call):
    """Confirm folder deletion"""
    user_id = call.from_user.id
    parts = call.data.replace("confirm_del_", "").split("_", 1)
    category = parts[0]
    name = parts[1]
    
    if fs.delete_folder(category, name):
        bot.edit_message_text(
            f"✅ <b>Deleted Successfully!</b>\n\n"
            f"Removed: {category.upper()} → {name}",
            user_id,
            call.message.message_id,
            parse_mode="HTML"
        )
        bot.send_message(user_id, "✅ Folder deleted!", reply_markup=get_admin_keyboard())
    else:
        bot.edit_message_text(
            f"❌ <b>Folder Not Found!</b>\n\n"
            f"Could not find: {category.upper()} → {name}",
            user_id,
            call.message.message_id,
            parse_mode="HTML"
        )
    
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_del")
def cancel_delete_callback(call):
    """Cancel folder deletion"""
    bot.edit_message_text(
        "❌ Deletion cancelled",
        call.from_user.id,
        call.message.message_id
    )
    bot.send_message(call.from_user.id, "Returning to admin panel...", reply_markup=get_admin_keyboard())
    bot.answer_callback_query(call.id)

# =========================
# ✏️ EDIT PRICE
# =========================
@bot.message_handler(func=lambda m: m.text == "✏️ EDIT PRICE" and is_admin(m.from_user.id))
def edit_price_command(message):
    """Edit folder price"""
    msg = bot.send_message(
        message.from_user.id,
        "✏️ <b>EDIT PRICE</b>\n\n"
        "Send: <code>category folder_name new_price</code>\n\n"
        "Example: <code>vip My Method 50</code>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_edit_price)

def process_edit_price(message):
    """Process price edit"""
    user_id = message.from_user.id
    
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.send_message(user_id, "❌ Invalid format! Use: category folder_name price")
            return
        
        category = parts[0].lower()
        price = int(parts[-1])
        name = " ".join(parts[1:-1])
        
        if category not in ["free", "vip", "apps", "services"]:
            bot.send_message(user_id, "❌ Invalid category!")
            return
        
        fs.update_price(category, name, price)
        bot.send_message(
            user_id,
            f"✅ Price updated!\n\n"
            f"📂 {category.upper()} → {name}\n"
            f"💰 New price: {price} points",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard()
        )
    except:
        bot.send_message(user_id, "❌ Invalid format or price!")

# =========================
# ✏️ EDIT NAME
# =========================
@bot.message_handler(func=lambda m: m.text == "✏️ EDIT NAME" and is_admin(m.from_user.id))
def edit_name_command(message):
    """Edit folder name"""
    msg = bot.send_message(
        message.from_user.id,
        "✏️ <b>EDIT NAME</b>\n\n"
        "Send: <code>category old_name new_name</code>\n\n"
        "Example: <code>free OldName NewName</code>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_edit_name)

def process_edit_name(message):
    """Process name edit"""
    user_id = message.from_user.id
    
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) != 3:
            bot.send_message(user_id, "❌ Invalid format! Use: category old_name new_name")
            return
        
        category = parts[0].lower()
        old_name = parts[1]
        new_name = parts[2]
        
        if category not in ["free", "vip", "apps", "services"]:
            bot.send_message(user_id, "❌ Invalid category!")
            return
        
        fs.update_name(category, old_name, new_name)
        bot.send_message(
            user_id,
            f"✅ Name updated!\n\n"
            f"📂 {category.upper()}\n"
            f"🔄 {old_name} → {new_name}",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard()
        )
    except:
        bot.send_message(user_id, "❌ Invalid format!")

# =========================
# 📝 EDIT CONTENT (NEW FEATURE)
# =========================
@bot.message_handler(func=lambda m: m.text == "📝 EDIT CONTENT" and is_admin(m.from_user.id))
def edit_content_command(message):
    """Edit folder content"""
    msg = bot.send_message(
        message.from_user.id,
        "📝 <b>EDIT CONTENT</b>\n\n"
        "First, send the folder details:\n\n"
        "Send: <code>category folder_name</code>\n\n"
        "Example: <code>vip My Method</code>\n\n"
        "This will let you edit the content (text or files).",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_edit_content_select)

def process_edit_content_select(message):
    """Process folder selection for content edit"""
    user_id = message.from_user.id
    
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) != 2:
            bot.send_message(user_id, "❌ Invalid format! Use: category folder_name")
            return
        
        category = parts[0].lower()
        name = parts[1].strip()
        
        if category not in ["free", "vip", "apps", "services"]:
            bot.send_message(user_id, "❌ Invalid category! Use: free, vip, apps, or services")
            return
        
        folder = fs.get_folder(category, name)
        if not folder:
            bot.send_message(user_id, f"❌ Folder '{name}' not found in {category.upper()}!")
            return
        
        # Store selection in session
        if not hasattr(bot, 'edit_session'):
            bot.edit_session = {}
        
        bot.edit_session[user_id] = {
            "category": category,
            "name": name,
            "step": "select_type"
        }
        
        # Ask what to edit
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("📝 Edit Text Content", callback_data="edit_text"),
            InlineKeyboardButton("📁 Edit Files", callback_data="edit_files"),
            InlineKeyboardButton("❌ Cancel", callback_data="edit_cancel")
        )
        
        bot.send_message(
            user_id,
            f"📝 <b>Edit Content: {name}</b>\n\n"
            f"📂 Category: {category.upper()}\n\n"
            f"What would you like to edit?",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        bot.send_message(user_id, f"❌ Error: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "edit_text")
def edit_text_content_callback(call):
    """Handle text content edit"""
    user_id = call.from_user.id
    
    if not hasattr(bot, 'edit_session') or user_id not in bot.edit_session:
        bot.answer_callback_query(call.id, "❌ Session expired! Please start over.")
        return
    
    session = bot.edit_session[user_id]
    session["step"] = "edit_text"
    
    # Get current content
    content_type, content = fs.get_folder_content(session["category"], session["name"])
    
    current_text = "No current text content"
    if content_type == "text":
        current_text = content[:500] + "..." if len(content) > 500 else content
    
    msg = bot.send_message(
        user_id,
        f"📝 <b>Edit Text Content</b>\n\n"
        f"📂 {session['category'].upper()} → {session['name']}\n\n"
        f"<b>Current Content:</b>\n{current_text}\n\n"
        f"Send the <b>NEW text content</b> for this folder:\n\n"
        f"Type /cancel to cancel",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_edit_text_save)
    bot.answer_callback_query(call.id)

def process_edit_text_save(message):
    """Save edited text content"""
    user_id = message.from_user.id
    
    if message.text == "/cancel":
        if hasattr(bot, 'edit_session') and user_id in bot.edit_session:
            del bot.edit_session[user_id]
        bot.send_message(user_id, "❌ Edit cancelled!", reply_markup=get_admin_keyboard())
        return
    
    if not hasattr(bot, 'edit_session') or user_id not in bot.edit_session:
        bot.send_message(user_id, "❌ Session expired! Please start over.", reply_markup=get_admin_keyboard())
        return
    
    session = bot.edit_session[user_id]
    new_content = message.text
    
    # Update the content
    fs.update_content(session["category"], session["name"], "text", new_content)
    
    bot.send_message(
        user_id,
        f"✅ <b>Content Updated!</b>\n\n"
        f"📂 {session['category'].upper()} → {session['name']}\n"
        f"📝 Text content has been updated successfully!",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard()
    )
    
    del bot.edit_session[user_id]

@bot.callback_query_handler(func=lambda call: call.data == "edit_files")
def edit_files_content_callback(call):
    """Handle files content edit"""
    user_id = call.from_user.id
    
    if not hasattr(bot, 'edit_session') or user_id not in bot.edit_session:
        bot.answer_callback_query(call.id, "❌ Session expired! Please start over.")
        return
    
    session = bot.edit_session[user_id]
    session["step"] = "edit_files"
    session["new_files"] = []
    
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("/done", "/cancel")
    
    msg = bot.send_message(
        user_id,
        f"📁 <b>Edit Files</b>\n\n"
        f"📂 {session['category'].upper()} → {session['name']}\n\n"
        f"Send the NEW files (documents, photos, videos)\n"
        f"Press /done when finished:\n\n"
        f"⚠️ This will REPLACE all existing files!",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_edit_files_save)
    bot.answer_callback_query(call.id)

def process_edit_files_save(message):
    """Process new files for edit"""
    user_id = message.from_user.id
    
    if message.text == "/cancel":
        if hasattr(bot, 'edit_session') and user_id in bot.edit_session:
            del bot.edit_session[user_id]
        bot.send_message(user_id, "❌ Edit cancelled!", reply_markup=get_admin_keyboard())
        return
    
    if not hasattr(bot, 'edit_session') or user_id not in bot.edit_session:
        bot.send_message(user_id, "❌ Session expired! Please start over.", reply_markup=get_admin_keyboard())
        return
    
    if message.text == "/done":
        session = bot.edit_session[user_id]
        
        if not session["new_files"]:
            bot.send_message(user_id, "❌ No files uploaded! Send files or /cancel")
            return
        
        # Update the files
        fs.update_content(session["category"], session["name"], "files", session["new_files"])
        
        bot.send_message(
            user_id,
            f"✅ <b>Files Updated!</b>\n\n"
            f"📂 {session['category'].upper()} → {session['name']}\n"
            f"📁 {len(session['new_files'])} file(s) have been updated successfully!",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard()
        )
        
        del bot.edit_session[user_id]
        return
    
    # Save file
    if message.content_type in ["document", "photo", "video"]:
        bot.edit_session[user_id]["new_files"].append({
            "chat": message.chat.id,
            "msg": message.message_id,
            "type": message.content_type
        })
        bot.send_message(user_id, f"✅ File saved! ({len(bot.edit_session[user_id]['new_files'])} files)")
    else:
        bot.send_message(user_id, "❌ Please send documents, photos, or videos only!")
    
    # Continue listening
    bot.register_next_step_handler(message, process_edit_files_save)

@bot.callback_query_handler(func=lambda call: call.data == "edit_cancel")
def edit_cancel_callback(call):
    """Cancel edit session"""
    user_id = call.from_user.id
    
    if hasattr(bot, 'edit_session') and user_id in bot.edit_session:
        del bot.edit_session[user_id]
    
    bot.edit_message_text(
        "❌ Edit cancelled",
        user_id,
        call.message.message_id
    )
    bot.send_message(user_id, "Returning to admin panel...", reply_markup=get_admin_keyboard())
    bot.answer_callback_query(call.id)

# =========================
# 🔀 MOVE FOLDER
# =========================
@bot.message_handler(func=lambda m: m.text == "🔀 MOVE FOLDER" and is_admin(m.from_user.id))
def move_folder_command(message):
    """Move folder"""
    msg = bot.send_message(
        message.from_user.id,
        "🔀 <b>MOVE FOLDER</b>\n\n"
        "Send: <code>folder_number new_parent</code>\n\n"
        "Examples:\n"
        "<code>5 root</code> (move to main level)\n"
        "<code>5 MainFolder</code> (move inside another folder)\n\n"
        "Use 'root' for main level",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_move_folder)

def process_move_folder(message):
    """Process folder move"""
    user_id = message.from_user.id
    
    try:
        parts = message.text.split()
        number = int(parts[0])
        new_parent = parts[1] if parts[1] != "root" else None
        
        folder = fs.get_folder_by_number(number)
        if not folder:
            bot.send_message(user_id, "❌ Folder not found!")
            return
        
        fs.move_folder(number, new_parent)
        bot.send_message(
            user_id,
            f"✅ Folder #{number} moved successfully!",
            reply_markup=get_admin_keyboard()
        )
    except:
        bot.send_message(user_id, "❌ Invalid format! Use: number new_parent")

# =========================
# 📁 CREATE SUBFOLDER
# =========================
@bot.message_handler(func=lambda m: m.text == "📁 CREATE SUBFOLDER" and is_admin(m.from_user.id))
def create_subfolder_command(message):
    """Create subfolder"""
    msg = bot.send_message(
        message.from_user.id,
        "📁 <b>CREATE SUBFOLDER</b>\n\n"
        "Send: <code>category parent_name subfolder_name price</code>\n\n"
        "Example: <code>free MainFolder SubFolder 10</code>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_create_subfolder)

def process_create_subfolder(message):
    """Process subfolder creation"""
    user_id = message.from_user.id
    
    try:
        parts = message.text.split(maxsplit=3)
        if len(parts) < 4:
            bot.send_message(user_id, "❌ Invalid format! Use: category parent name price")
            return
        
        category = parts[0].lower()
        parent = parts[1]
        name = parts[2]
        price = int(parts[3])
        
        if category not in ["free", "vip", "apps", "services"]:
            bot.send_message(user_id, "❌ Invalid category!")
            return
        
        parent_folder = fs.get_folder(category, parent)
        if not parent_folder:
            bot.send_message(user_id, f"❌ Parent folder '{parent}' not found!")
            return
        
        number = fs.add_folder(category, name, [], price, parent)
        bot.send_message(
            user_id,
            f"✅ <b>Subfolder Created!</b>\n\n"
            f"📌 Number: {number}\n"
            f"📂 {parent} → {name}\n"
            f"💰 Price: {price} points",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard()
        )
    except:
        bot.send_message(user_id, "❌ Invalid format!")

# =========================
# 👑 VIP MANAGEMENT
# =========================
@bot.message_handler(func=lambda m: m.text == "👑 ADD VIP" and is_admin(m.from_user.id))
def add_vip_command(message):
    """Add VIP user"""
    msg = bot.send_message(
        message.from_user.id,
        "👑 <b>ADD VIP USER</b>\n\n"
        "Send user ID or @username:",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_add_vip)

def process_add_vip(message):
    """Process add VIP"""
    user_id = message.from_user.id
    input_text = message.text.strip()
    
    target_id = None
    if input_text.startswith("@"):
        username = input_text[1:]
        try:
            chat = bot.get_chat(f"@{username}")
            target_id = chat.id
        except:
            bot.send_message(user_id, "❌ User not found!")
            return
    else:
        try:
            target_id = int(input_text)
        except:
            bot.send_message(user_id, "❌ Invalid user ID!")
            return
    
    user = User(target_id)
    
    if user.is_vip():
        bot.send_message(user_id, "⚠️ User is already VIP!")
        return
    
    user.make_vip()
    bot.send_message(user_id, f"✅ User {target_id} is now VIP!")
    
    try:
        bot.send_message(
            target_id,
            "🎉 <b>CONGRATULATIONS!</b> 🎉\n\n"
            "You are now a <b>VIP Member</b>!\n\n"
            "✨ <b>Benefits:</b>\n"
            "• Access to all VIP METHODS\n"
            "• No points needed for VIP items\n"
            "• Priority support\n\n"
            f"💰 Your points: {user.get_points()}",
            parse_mode="HTML"
        )
    except:
        pass

@bot.message_handler(func=lambda m: m.text == "👑 REMOVE VIP" and is_admin(m.from_user.id))
def remove_vip_command(message):
    """Remove VIP user"""
    msg = bot.send_message(
        message.from_user.id,
        "👑 <b>REMOVE VIP</b>\n\n"
        "Send user ID or @username:",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_remove_vip)

def process_remove_vip(message):
    """Process remove VIP"""
    user_id = message.from_user.id
    input_text = message.text.strip()
    
    target_id = None
    if input_text.startswith("@"):
        username = input_text[1:]
        try:
            chat = bot.get_chat(f"@{username}")
            target_id = chat.id
        except:
            bot.send_message(user_id, "❌ User not found!")
            return
    else:
        try:
            target_id = int(input_text)
        except:
            bot.send_message(user_id, "❌ Invalid user ID!")
            return
    
    user = User(target_id)
    
    if not user.is_vip():
        bot.send_message(user_id, "⚠️ User is not VIP!")
        return
    
    user.remove_vip()
    bot.send_message(user_id, f"✅ VIP removed from user {target_id}!")
    
    try:
        bot.send_message(
            target_id,
            "⚠️ <b>VIP Status Removed</b>\n\n"
            "Your VIP membership has been removed.\n\n"
            f"💰 Your points: {user.get_points()}",
            parse_mode="HTML"
        )
    except:
        pass

# =========================
# 💰 GIVE POINTS
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 GIVE POINTS" and is_admin(m.from_user.id))
def give_points_command(message):
    """Give points to user"""
    msg = bot.send_message(
        message.from_user.id,
        "💰 <b>GIVE POINTS</b>\n\n"
        "Send: <code>user_id points</code>\n\n"
        "Example: <code>123456789 100</code>\n\n"
        "User must have started the bot before!",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_give_points)

def process_give_points(message):
    """Process give points"""
    admin_id = message.from_user.id
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(admin_id, "❌ Invalid format! Use: user_id points")
            return
        
        target_id = int(parts[0])
        points = int(parts[1])
        
        if points <= 0:
            bot.send_message(admin_id, "❌ Points must be greater than 0!")
            return
        
        if points > 1000000:
            bot.send_message(admin_id, "⚠️ Maximum 1,000,000 points per transaction!")
            return
        
        # Check if user exists
        user_data = users_col.find_one({"_id": str(target_id)})
        if not user_data:
            bot.send_message(
                admin_id,
                f"❌ User {target_id} not found!\n\n"
                f"User must send /start to the bot first.",
                parse_mode="HTML"
            )
            return
        
        user = User(target_id)
        old_points = user.get_points()
        user.add_points(points)
        
        bot.send_message(
            admin_id,
            f"✅ <b>Points Added!</b>\n\n"
            f"👤 User: {target_id}\n"
            f"💰 Old: {old_points}\n"
            f"➕ Added: +{points}\n"
            f"💰 New: {user.get_points()}",
            parse_mode="HTML"
        )
        
        try:
            bot.send_message(
                target_id,
                f"🎉 <b>Points Received!</b> 🎉\n\n"
                f"✨ You received <b>+{points} points</b>!\n\n"
                f"💰 <b>New Balance:</b> {user.get_points()} points",
                parse_mode="HTML"
            )
        except:
            pass
            
    except ValueError:
        bot.send_message(admin_id, "❌ Invalid user ID or points!")
    except Exception as e:
        bot.send_message(admin_id, f"❌ Error: {str(e)}")

# =========================
# 🎫 GENERATE CODES - FIXED
# =========================
@bot.message_handler(func=lambda m: m.text == "🎫 GENERATE CODES" and is_admin(m.from_user.id))
def generate_codes_command(message):
    """Generate codes"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("Single Use", callback_data="gen_single"),
        InlineKeyboardButton("Multi Use", callback_data="gen_multi")
    )
    
    bot.send_message(
        message.from_user.id,
        "🎫 <b>GENERATE CODES</b>\n\nSelect code type:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("gen_"))
def generate_codes_type(call):
    """Generate codes by type"""
    code_type = call.data.split("_")[1]
    multi_use = (code_type == "multi")
    
    # Store in session
    if not hasattr(bot, 'code_gen_session'):
        bot.code_gen_session = {}
    
    bot.code_gen_session[call.from_user.id] = {"multi_use": multi_use, "step": "points"}
    
    msg = bot.send_message(
        call.from_user.id,
        "💰 Enter points per code:",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_code_points)
    bot.answer_callback_query(call.id)

def process_code_points(message):
    """Process code points"""
    user_id = message.from_user.id
    
    try:
        # Clean the input
        points_text = message.text.strip()
        
        if not points_text:
            bot.send_message(user_id, "❌ Please enter a number!")
            msg = bot.send_message(user_id, "💰 Enter points per code:", parse_mode="HTML")
            bot.register_next_step_handler(msg, process_code_points)
            return
        
        points = int(points_text)
        
        if points <= 0:
            bot.send_message(user_id, "❌ Points must be greater than 0!")
            msg = bot.send_message(user_id, "💰 Enter points per code:", parse_mode="HTML")
            bot.register_next_step_handler(msg, process_code_points)
            return
        
        if points > 100000:
            bot.send_message(user_id, "⚠️ Maximum 100,000 points per code! Please enter a lower amount.")
            msg = bot.send_message(user_id, "💰 Enter points per code:", parse_mode="HTML")
            bot.register_next_step_handler(msg, process_code_points)
            return
        
        if not hasattr(bot, 'code_gen_session'):
            bot.code_gen_session = {}
        
        bot.code_gen_session[user_id]["points"] = points
        bot.code_gen_session[user_id]["step"] = "count"
        
        msg = bot.send_message(
            user_id,
            "🔢 How many codes to generate? (Max 100):",
            parse_mode="HTML"
        )
        bot.register_next_step_handler(msg, process_code_count)
    except ValueError:
        bot.send_message(user_id, "❌ Invalid number! Please enter a valid number (e.g., 50)")
        msg = bot.send_message(user_id, "💰 Enter points per code:", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_code_points)
    except Exception as e:
        bot.send_message(user_id, f"❌ Error: {str(e)}")

def process_code_count(message):
    """Process code count"""
    user_id = message.from_user.id
    
    try:
        # Clean the input - remove any non-numeric characters
        count_text = message.text.strip()
        
        # Handle potential issues with the input
        if not count_text:
            bot.send_message(user_id, "❌ Please enter a number!")
            msg = bot.send_message(user_id, "🔢 How many codes to generate?", parse_mode="HTML")
            bot.register_next_step_handler(msg, process_code_count)
            return
        
        # Convert to integer
        count = int(count_text)
        
        if count <= 0:
            bot.send_message(user_id, "❌ Count must be greater than 0!")
            msg = bot.send_message(user_id, "🔢 How many codes to generate?", parse_mode="HTML")
            bot.register_next_step_handler(msg, process_code_count)
            return
        
        if count > 100:
            bot.send_message(user_id, "⚠️ Maximum 100 codes at once! Please enter a lower number.")
            msg = bot.send_message(user_id, "🔢 How many codes to generate? (1-100):", parse_mode="HTML")
            bot.register_next_step_handler(msg, process_code_count)
            return
        
        if user_id not in bot.code_gen_session:
            bot.send_message(user_id, "❌ Session expired! Please start over.")
            return
        
        session = bot.code_gen_session[user_id]
        
        if session["multi_use"]:
            msg = bot.send_message(
                user_id,
                "📅 Expiry days? (0 for no expiry):",
                parse_mode="HTML"
            )
            bot.register_next_step_handler(msg, lambda x: process_code_expiry(x, session["points"], count, session["multi_use"]))
        else:
            codes = code_system.generate_codes(session["points"], count, session["multi_use"])
            codes_text = "\n".join(codes)
            
            bot.send_message(
                user_id,
                f"✅ <b>Generated {count} Codes!</b>\n\n"
                f"📊 Points each: {session['points']}\n"
                f"🔑 Type: {'Multi-use' if session['multi_use'] else 'Single-use'}\n\n"
                f"<code>{codes_text}</code>",
                parse_mode="HTML",
                reply_markup=get_admin_keyboard()
            )
            
            del bot.code_gen_session[user_id]
    except ValueError:
        bot.send_message(user_id, "❌ Invalid number! Please enter a valid number (e.g., 10)")
        msg = bot.send_message(user_id, "🔢 How many codes to generate?", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_code_count)
    except Exception as e:
        bot.send_message(user_id, f"❌ Error: {str(e)}")
        if user_id in bot.code_gen_session:
            del bot.code_gen_session[user_id]

def process_code_expiry(message, points, count, multi_use):
    """Process code expiry"""
    user_id = message.from_user.id
    
    try:
        expiry_days = int(message.text) if message.text != "0" else None
        codes = code_system.generate_codes(points, count, multi_use, expiry_days)
        codes_text = "\n".join(codes)
        
        expiry_msg = f"Expiry: {expiry_days} days" if expiry_days else "No expiry"
        
        bot.send_message(
            user_id,
            f"✅ <b>Generated {count} Codes!</b>\n\n"
            f"📊 Points each: {points}\n"
            f"🔑 Type: {'Multi-use' if multi_use else 'Single-use'}\n"
            f"⏰ {expiry_msg}\n\n"
            f"<code>{codes_text}</code>",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard()
        )
        
        if hasattr(bot, 'code_gen_session') and user_id in bot.code_gen_session:
            del bot.code_gen_session[user_id]
    except:
        bot.send_message(user_id, "❌ Invalid expiry days!")

# =========================
# 📊 VIEW CODES
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 VIEW CODES" and is_admin(m.from_user.id))
def view_codes_command(message):
    """View all codes"""
    codes = code_system.get_all_codes()
    
    if not codes:
        bot.send_message(message.from_user.id, "📊 No codes generated yet!")
        return
    
    total, used, unused, multi = code_system.get_stats()
    
    text = f"📊 <b>CODE STATISTICS</b>\n\n"
    text += f"┌ Total: {total}\n"
    text += f"├ Used: {used}\n"
    text += f"├ Unused: {unused}\n"
    text += f"└ Multi-Use: {multi}\n\n"
    
    # Show recent unused codes
    unused_codes = [c for c in codes if not c.get("used", False)][:10]
    if unused_codes:
        text += "<b>Recent Unused Codes:</b>\n"
        for code in unused_codes[:5]:
            text += f"• <code>{code['_id']}</code> - {code['points']} pts\n"
    
    bot.send_message(message.from_user.id, text, parse_mode="HTML")

# =========================
# 📦 POINTS PACKAGES
# =========================
@bot.message_handler(func=lambda m: m.text == "📦 POINTS PACKAGES" and is_admin(m.from_user.id))
def manage_packages_command(message):
    """Manage points packages"""
    packages = get_points_packages()
    
    text = f"📦 <b>POINTS PACKAGES</b>\n\n"
    
    for i, pkg in enumerate(packages, 1):
        status = "✅ Active" if pkg.get("active", True) else "❌ Inactive"
        text += f"{i}. <b>{pkg['points']} pts</b> - ${pkg['price_usd']}\n"
        if pkg.get("bonus", 0) > 0:
            text += f"   Bonus: +{pkg['bonus']} pts\n"
        text += f"   Status: {status}\n\n"
    
    text += f"<b>Commands:</b>\n"
    text += f"/addpackage points price_usd bonus\n"
    text += f"/editpackage number points price_usd bonus\n"
    text += f"/togglepackage number\n"
    text += f"/delpackage number"
    
    bot.send_message(message.from_user.id, text, parse_mode="HTML")

@bot.message_handler(commands=['addpackage'])
def add_package_command(message):
    """Add points package"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        _, points, price, bonus = message.text.split()
        points = int(points)
        price = int(price)
        bonus = int(bonus)
        
        packages = get_points_packages()
        packages.append({
            "points": points,
            "price_usd": price,
            "bonus": bonus,
            "active": True
        })
        save_points_packages(packages)
        
        bot.send_message(
            message.from_user.id,
            f"✅ Package added: {points} pts for ${price} (+{bonus} bonus)"
        )
    except:
        bot.send_message(message.from_user.id, "❌ Use: /addpackage points price_usd bonus")

@bot.message_handler(commands=['editpackage'])
def edit_package_command(message):
    """Edit points package"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        _, num, points, price, bonus = message.text.split()
        num = int(num) - 1
        points = int(points)
        price = int(price)
        bonus = int(bonus)
        
        packages = get_points_packages()
        if 0 <= num < len(packages):
            packages[num]["points"] = points
            packages[num]["price_usd"] = price
            packages[num]["bonus"] = bonus
            save_points_packages(packages)
            bot.send_message(message.from_user.id, f"✅ Package {num+1} updated!")
        else:
            bot.send_message(message.from_user.id, "❌ Invalid package number!")
    except:
        bot.send_message(message.from_user.id, "❌ Use: /editpackage number points price_usd bonus")

@bot.message_handler(commands=['togglepackage'])
def toggle_package_command(message):
    """Toggle package active status"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        _, num = message.text.split()
        num = int(num) - 1
        
        packages = get_points_packages()
        if 0 <= num < len(packages):
            packages[num]["active"] = not packages[num].get("active", True)
            save_points_packages(packages)
            status = "activated" if packages[num]["active"] else "deactivated"
            bot.send_message(message.from_user.id, f"✅ Package {num+1} {status}!")
        else:
            bot.send_message(message.from_user.id, "❌ Invalid package number!")
    except:
        bot.send_message(message.from_user.id, "❌ Use: /togglepackage number")

@bot.message_handler(commands=['delpackage'])
def del_package_command(message):
    """Delete points package"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        _, num = message.text.split()
        num = int(num) - 1
        
        packages = get_points_packages()
        if 0 <= num < len(packages):
            removed = packages.pop(num)
            save_points_packages(packages)
            bot.send_message(message.from_user.id, f"✅ Package removed: {removed['points']} pts")
        else:
            bot.send_message(message.from_user.id, "❌ Invalid package number!")
    except:
        bot.send_message(message.from_user.id, "❌ Use: /delpackage number")

# =========================
# 👥 MANAGE ADMINS
# =========================
@bot.message_handler(func=lambda m: m.text == "👥 MANAGE ADMINS" and is_admin(m.from_user.id))
def manage_admins_command(message):
    """Manage admins"""
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.from_user.id, "❌ Only bot owner can manage admins!")
        return
    
    admins = list(admins_col.find({}))
    
    text = f"👥 <b>ADMIN MANAGEMENT</b>\n\n"
    text += f"<b>Current Admins:</b>\n"
    
    for admin in admins:
        owner_tag = " 👑 OWNER" if admin.get("_id") == ADMIN_ID else ""
        username = admin.get("username") or f"ID: {admin['_id']}"
        text += f"• <code>{admin['_id']}</code> - {username}{owner_tag}\n"
    
    text += f"\n<b>Commands:</b>\n"
    text += f"/addadmin user_id - Add admin\n"
    text += f"/removeadmin user_id - Remove admin\n"
    text += f"/listadmins - List all admins"
    
    bot.send_message(message.from_user.id, text, parse_mode="HTML")

@bot.message_handler(commands=['addadmin'])
def add_admin_command(message):
    """Add admin"""
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        _, user_id = message.text.split()
        user_id = int(user_id)
        
        if admins_col.find_one({"_id": user_id}):
            bot.send_message(message.from_user.id, f"❌ User {user_id} is already an admin!")
            return
        
        admins_col.insert_one({
            "_id": user_id,
            "username": None,
            "added_by": message.from_user.id,
            "added_at": time.time()
        })
        
        bot.send_message(message.from_user.id, f"✅ Admin {user_id} added!")
        
        try:
            bot.send_message(
                user_id,
                "🎉 You are now an admin of ZEDOX BOT!\n\nUse ⚙️ ADMIN panel to manage the bot."
            )
        except:
            pass
    except:
        bot.send_message(message.from_user.id, "❌ Use: /addadmin user_id")

@bot.message_handler(commands=['removeadmin'])
def remove_admin_command(message):
    """Remove admin"""
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        _, user_id = message.text.split()
        user_id = int(user_id)
        
        if user_id == ADMIN_ID:
            bot.send_message(message.from_user.id, "❌ Cannot remove bot owner!")
            return
        
        result = admins_col.delete_one({"_id": user_id})
        
        if result.deleted_count > 0:
            bot.send_message(message.from_user.id, f"✅ Admin {user_id} removed!")
            
            try:
                bot.send_message(user_id, "⚠️ You are no longer an admin of ZEDOX BOT.")
            except:
                pass
        else:
            bot.send_message(message.from_user.id, f"❌ User {user_id} is not an admin!")
    except:
        bot.send_message(message.from_user.id, "❌ Use: /removeadmin user_id")

@bot.message_handler(commands=['listadmins'])
def list_admins_command(message):
    """List all admins"""
    if not is_admin(message.from_user.id):
        return
    
    admins = list(admins_col.find({}))
    
    text = f"👥 <b>ADMIN LIST</b>\n\n"
    for admin in admins:
        owner_tag = " 👑 OWNER" if admin.get("_id") == ADMIN_ID else ""
        username = admin.get("username") or f"ID: {admin['_id']}"
        text += f"• <code>{admin['_id']}</code> - {username}{owner_tag}\n"
    
    bot.send_message(message.from_user.id, text, parse_mode="HTML")

# =========================
# 📞 SET CONTACTS
# =========================
@bot.message_handler(func=lambda m: m.text == "📞 SET CONTACTS" and is_admin(m.from_user.id))
def set_contacts_command(message):
    """Set contact information"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("💰 Points Contact", callback_data="set_points_contact"),
        InlineKeyboardButton("⭐ VIP Contact", callback_data="set_vip_contact"),
        InlineKeyboardButton("📋 View Contacts", callback_data="view_contacts")
    )
    
    bot.send_message(
        message.from_user.id,
        "📞 <b>CONTACT SETTINGS</b>\n\nSelect an option:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data == "set_points_contact")
def set_points_contact_callback(call):
    """Set points purchase contact"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Admin only!")
        return
    
    msg = bot.send_message(
        call.from_user.id,
        "📞 <b>Set Points Purchase Contact</b>\n\n"
        "Send username (with @) or link:\n"
        "Example: <code>@username</code> or <code>https://t.me/username</code>\n\n"
        "Send <code>none</code> to remove",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, save_points_contact)
    bot.answer_callback_query(call.id)

def save_points_contact(message):
    """Save points contact"""
    if message.text.lower() == "none":
        update_config("contact_username", None)
        update_config("contact_link", None)
        bot.send_message(message.from_user.id, "✅ Points contact removed!", reply_markup=get_admin_keyboard())
    elif message.text.startswith("http"):
        update_config("contact_link", message.text)
        update_config("contact_username", None)
        bot.send_message(message.from_user.id, f"✅ Points contact link set!", reply_markup=get_admin_keyboard())
    elif message.text.startswith("@"):
        update_config("contact_username", message.text)
        update_config("contact_link", None)
        bot.send_message(message.from_user.id, f"✅ Points contact username set!", reply_markup=get_admin_keyboard())
    else:
        bot.send_message(message.from_user.id, "❌ Invalid format! Use @username or https://t.me/username")

@bot.callback_query_handler(func=lambda call: call.data == "set_vip_contact")
def set_vip_contact_callback(call):
    """Set VIP contact"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Admin only!")
        return
    
    msg = bot.send_message(
        call.from_user.id,
        "⭐ <b>Set VIP Contact</b>\n\n"
        "Send username (with @) or link:\n"
        "Example: <code>@username</code> or <code>https://t.me/username</code>\n\n"
        "Send <code>none</code> to remove",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, save_vip_contact)
    bot.answer_callback_query(call.id)

def save_vip_contact(message):
    """Save VIP contact"""
    if message.text.lower() == "none":
        update_config("vip_contact", None)
        bot.send_message(message.from_user.id, "✅ VIP contact removed!", reply_markup=get_admin_keyboard())
    elif message.text.startswith("http"):
        update_config("vip_contact", message.text)
        bot.send_message(message.from_user.id, f"✅ VIP contact link set!", reply_markup=get_admin_keyboard())
    elif message.text.startswith("@"):
        update_config("vip_contact", message.text)
        bot.send_message(message.from_user.id, f"✅ VIP contact username set!", reply_markup=get_admin_keyboard())
    else:
        bot.send_message(message.from_user.id, "❌ Invalid format! Use @username or https://t.me/username")

@bot.callback_query_handler(func=lambda call: call.data == "view_contacts")
def view_contacts_callback(call):
    """View current contacts"""
    config = get_config()
    points = config.get("contact_username") or config.get("contact_link") or "Not set"
    vip = config.get("vip_contact") or "Not set"
    
    text = f"📞 <b>CURRENT CONTACTS</b>\n\n"
    text += f"💰 <b>Points Purchase:</b> {points}\n"
    text += f"⭐ <b>VIP Purchase:</b> {vip}"
    
    bot.edit_message_text(
        text,
        call.from_user.id,
        call.message.message_id,
        parse_mode="HTML"
    )
    bot.answer_callback_query(call.id)

# =========================
# 🔘 CUSTOM BUTTONS
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ ADD BUTTON" and is_admin(m.from_user.id))
def add_button_command(message):
    """Add custom button"""
    msg = bot.send_message(
        message.from_user.id,
        "🔘 <b>ADD CUSTOM BUTTON</b>\n\n"
        "Send: <code>type|text|data</code>\n\n"
        "<b>Types:</b>\n"
        "• <code>link</code> - Opens URL\n"
        "• <code>folder</code> - Opens folder (use folder number as data)\n\n"
        "<b>Examples:</b>\n"
        "<code>link|Website|https://example.com</code>\n"
        "<code>folder|My Folder|5</code>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_add_button)

def process_add_button(message):
    """Process add button"""
    user_id = message.from_user.id
    
    try:
        parts = message.text.split("|")
        if len(parts) != 3:
            bot.send_message(user_id, "❌ Invalid format! Use: type|text|data")
            return
        
        btn_type = parts[0].lower()
        btn_text = parts[1]
        btn_data = parts[2]
        
        if btn_type not in ["link", "folder"]:
            bot.send_message(user_id, "❌ Invalid type! Use: link or folder")
            return
        
        if btn_type == "folder":
            folder = fs.get_folder_by_number(int(btn_data))
            if not folder:
                bot.send_message(user_id, f"❌ Folder #{btn_data} not found!")
                return
        
        config = get_config()
        buttons = config.get("custom_buttons", [])
        buttons.append({
            "text": btn_text,
            "type": btn_type,
            "data": btn_data
        })
        update_config("custom_buttons", buttons)
        
        bot.send_message(user_id, f"✅ Button added: {btn_text}", reply_markup=get_admin_keyboard())
    except:
        bot.send_message(user_id, "❌ Invalid format!")

@bot.message_handler(func=lambda m: m.text == "➖ REMOVE BUTTON" and is_admin(m.from_user.id))
def remove_button_command(message):
    """Remove custom button"""
    config = get_config()
    buttons = config.get("custom_buttons", [])
    
    if not buttons:
        bot.send_message(message.from_user.id, "❌ No custom buttons to remove!")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for btn in buttons:
        keyboard.add(InlineKeyboardButton(f"❌ {btn['text']}", callback_data=f"rmbtn_{btn['text']}"))
    
    bot.send_message(
        message.from_user.id,
        "🔘 <b>REMOVE BUTTON</b>\n\nSelect button to remove:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("rmbtn_"))
def remove_button_callback(call):
    """Remove button callback"""
    button_text = call.data.replace("rmbtn_", "")
    
    config = get_config()
    buttons = config.get("custom_buttons", [])
    buttons = [b for b in buttons if b["text"] != button_text]
    update_config("custom_buttons", buttons)
    
    bot.edit_message_text(
        f"✅ Removed: {button_text}",
        call.from_user.id,
        call.message.message_id
    )
    bot.answer_callback_query(call.id)

# =========================
# 📢 FORCE JOIN CHANNELS
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ ADD CHANNEL" and is_admin(m.from_user.id))
def add_channel_command(message):
    """Add force join channel"""
    msg = bot.send_message(
        message.from_user.id,
        "➕ <b>ADD FORCE JOIN CHANNEL</b>\n\n"
        "Send channel username (with @):\n"
        "Example: <code>@channelusername</code>",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, process_add_channel)

def process_add_channel(message):
    """Process add channel"""
    user_id = message.from_user.id
    channel = message.text.strip()
    
    if not channel.startswith("@"):
        bot.send_message(user_id, "❌ Channel username must start with @")
        return
    
    config = get_config()
    channels = config.get("force_channels", [])
    
    if channel in channels:
        bot.send_message(user_id, "❌ Channel already in list!")
        return
    
    channels.append(channel)
    update_config("force_channels", channels)
    bot.send_message(user_id, f"✅ Force join channel added: {channel}", reply_markup=get_admin_keyboard())

@bot.message_handler(func=lambda m: m.text == "➖ REMOVE CHANNEL" and is_admin(m.from_user.id))
def remove_channel_command(message):
    """Remove force join channel"""
    config = get_config()
    channels = config.get("force_channels", [])
    
    if not channels:
        bot.send_message(message.from_user.id, "❌ No channels to remove!")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for channel in channels:
        keyboard.add(InlineKeyboardButton(f"❌ {channel}", callback_data=f"rmch_{channel}"))
    
    bot.send_message(
        message.from_user.id,
        "➖ <b>REMOVE FORCE JOIN CHANNEL</b>\n\nSelect channel to remove:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("rmch_"))
def remove_channel_callback(call):
    """Remove channel callback"""
    channel = call.data.replace("rmch_", "")
    
    config = get_config()
    channels = config.get("force_channels", [])
    channels = [c for c in channels if c != channel]
    update_config("force_channels", channels)
    
    bot.edit_message_text(
        f"✅ Removed: {channel}",
        call.from_user.id,
        call.message.message_id
    )
    bot.answer_callback_query(call.id)

# =========================
# ⚙️ SETTINGS
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ SETTINGS" and is_admin(m.from_user.id))
def settings_command(message):
    """Show settings menu"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⭐ VIP Message", callback_data="set_vip_msg"),
        InlineKeyboardButton("🏠 Welcome Message", callback_data="set_welcome"),
        InlineKeyboardButton("💰 Referral Reward", callback_data="set_reward"),
        InlineKeyboardButton("💵 Points per $", callback_data="set_ppd")
    )
    
    bot.send_message(
        message.from_user.id,
        "⚙️ <b>SETTINGS</b>\n\nSelect an option:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data == "set_vip_msg")
def set_vip_msg_callback(call):
    """Set VIP message"""
    msg = bot.send_message(
        call.from_user.id,
        "⭐ <b>Set VIP Message</b>\n\nSend the new VIP message:",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, save_vip_msg)
    bot.answer_callback_query(call.id)

def save_vip_msg(message):
    """Save VIP message"""
    update_config("vip_message", message.text)
    bot.send_message(message.from_user.id, "✅ VIP message updated!", reply_markup=get_admin_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "set_welcome")
def set_welcome_callback(call):
    """Set welcome message"""
    msg = bot.send_message(
        call.from_user.id,
        "🏠 <b>Set Welcome Message</b>\n\nSend the new welcome message:",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, save_welcome)
    bot.answer_callback_query(call.id)

def save_welcome(message):
    """Save welcome message"""
    update_config("welcome_message", message.text)
    bot.send_message(message.from_user.id, "✅ Welcome message updated!", reply_markup=get_admin_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "set_reward")
def set_reward_callback(call):
    """Set referral reward"""
    config = get_config()
    current = config.get("referral_reward", 5)
    
    msg = bot.send_message(
        call.from_user.id,
        f"💰 <b>Set Referral Reward</b>\n\nCurrent reward: {current} points\n\nSend new amount:",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, save_reward)
    bot.answer_callback_query(call.id)

def save_reward(message):
    """Save referral reward"""
    try:
        reward = int(message.text)
        update_config("referral_reward", reward)
        bot.send_message(message.from_user.id, f"✅ Referral reward set to {reward} points!", reply_markup=get_admin_keyboard())
    except:
        bot.send_message(message.from_user.id, "❌ Invalid number!")

@bot.callback_query_handler(func=lambda call: call.data == "set_ppd")
def set_ppd_callback(call):
    """Set points per dollar"""
    config = get_config()
    current = config.get("points_per_dollar", 100)
    
    msg = bot.send_message(
        call.from_user.id,
        f"💰 <b>Set Points per Dollar</b>\n\nCurrent: {current} points = $1\n\nSend new value:",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, save_ppd)
    bot.answer_callback_query(call.id)

def save_ppd(message):
    """Save points per dollar"""
    try:
        ppd = int(message.text)
        update_config("points_per_dollar", ppd)
        bot.send_message(message.from_user.id, f"✅ Set: {ppd} points = $1", reply_markup=get_admin_keyboard())
    except:
        bot.send_message(message.from_user.id, "❌ Invalid number!")

# =========================
# 📊 STATISTICS
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 STATISTICS" and is_admin(m.from_user.id))
def statistics_command(message):
    """Show bot statistics"""
    total_users = users_col.count_documents({})
    vip_users = users_col.count_documents({"is_vip": True})
    free_users = total_users - vip_users
    
    all_users = list(users_col.find({}))
    total_points = sum(u.get("points", 0) for u in all_users)
    total_earned = sum(u.get("total_points_earned", 0) for u in all_users)
    total_spent = sum(u.get("total_points_spent", 0) for u in all_users)
    total_refs = sum(u.get("referrals_count", 0) for u in all_users)
    total_purchases = sum(len(u.get("purchased_items", [])) for u in all_users)
    
    free_folders = folders_col.count_documents({"category": "free"})
    vip_folders = folders_col.count_documents({"category": "vip"})
    apps_folders = folders_col.count_documents({"category": "apps"})
    services_folders = folders_col.count_documents({"category": "services"})
    
    total_codes, used_codes, unused_codes, multi_codes = code_system.get_stats()
    
    text = f"📊 <b>BOT STATISTICS</b>\n\n"
    text += f"👥 <b>USERS:</b>\n"
    text += f"┌ Total: {total_users}\n"
    text += f"├ VIP: {vip_users}\n"
    text += f"└ Free: {free_users}\n\n"
    
    text += f"💰 <b>POINTS:</b>\n"
    text += f"┌ Current Total: {total_points:,}\n"
    text += f"├ Total Earned: {total_earned:,}\n"
    text += f"├ Total Spent: {total_spent:,}\n"
    text += f"└ Avg per User: {total_points//total_users if total_users > 0 else 0}\n\n"
    
    text += f"📚 <b>CONTENT:</b>\n"
    text += f"┌ FREE METHODS: {free_folders}\n"
    text += f"├ VIP METHODS: {vip_folders}\n"
    text += f"├ PREMIUM APPS: {apps_folders}\n"
    text += f"└ SERVICES: {services_folders}\n\n"
    
    text += f"📈 <b>ACTIVITY:</b>\n"
    text += f"┌ Referrals: {total_refs}\n"
    text += f"├ Purchases: {total_purchases}\n"
    text += f"├ Codes Total: {total_codes}\n"
    text += f"├ Codes Used: {used_codes}\n"
    text += f"└ Codes Unused: {unused_codes}"
    
    bot.send_message(message.from_user.id, text, parse_mode="HTML")

# =========================
# 📢 BROADCAST
# =========================
@bot.message_handler(func=lambda m: m.text == "📢 BROADCAST" and is_admin(m.from_user.id))
def broadcast_command(message):
    """Send broadcast"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📢 All Users", callback_data="broadcast_all"),
        InlineKeyboardButton("💎 VIP Users", callback_data="broadcast_vip"),
        InlineKeyboardButton("🆓 Free Users", callback_data="broadcast_free")
    )
    
    bot.send_message(
        message.from_user.id,
        "📢 <b>BROADCAST MESSAGE</b>\n\nSelect target audience:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("broadcast_"))
def broadcast_target_callback(call):
    """Handle broadcast target selection"""
    target = call.data.replace("broadcast_", "")
    
    msg = bot.send_message(
        call.from_user.id,
        f"📢 <b>Broadcast to {target.upper()} Users</b>\n\n"
        f"Send your broadcast message (text, photo, video, or document):",
        parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, lambda x: process_broadcast(x, target))
    bot.answer_callback_query(call.id)

def process_broadcast(message, target):
    """Process and send broadcast"""
    admin_id = message.from_user.id
    
    # Get users based on target
    query = {}
    if target == "vip":
        query = {"is_vip": True}
    elif target == "free":
        query = {"is_vip": False}
    
    users = list(users_col.find(query))
    
    if not users:
        bot.send_message(admin_id, "❌ No users found for this target!")
        return
    
    status_msg = bot.send_message(admin_id, "📤 Broadcasting... Please wait.")
    
    sent = 0
    failed = 0
    
    for user_data in users:
        try:
            user_id = int(user_data["_id"])
            
            if message.content_type == "text":
                bot.send_message(user_id, message.text, parse_mode="HTML")
            elif message.content_type == "photo":
                caption = message.caption if message.caption else None
                bot.send_photo(user_id, message.photo[-1].file_id, caption=caption, parse_mode="HTML")
            elif message.content_type == "video":
                caption = message.caption if message.caption else None
                bot.send_video(user_id, message.video.file_id, caption=caption, parse_mode="HTML")
            elif message.content_type == "document":
                caption = message.caption if message.caption else None
                bot.send_document(user_id, message.document.file_id, caption=caption, parse_mode="HTML")
            
            sent += 1
            
            if sent % 20 == 0:
                time.sleep(1)
                
        except Exception as e:
            failed += 1
            logger.error(f"Broadcast failed to {user_data['_id']}: {e}")
    
    bot.edit_message_text(
        f"✅ <b>Broadcast Complete!</b>\n\n"
        f"📤 Sent: {sent}\n"
        f"❌ Failed: {failed}\n"
        f"🎯 Target: {target.upper()}\n"
        f"👥 Total: {len(users)}",
        admin_id,
        status_msg.message_id,
        parse_mode="HTML"
    )

# =========================
# 🔔 TOGGLE NOTIFY
# =========================
@bot.message_handler(func=lambda m: m.text == "🔔 TOGGLE NOTIFY" and is_admin(m.from_user.id))
def toggle_notify_command(message):
    """Toggle notifications"""
    config = get_config()
    current = config.get("send_notifications", True)
    update_config("send_notifications", not current)
    
    state = "ON" if not current else "OFF"
    bot.send_message(
        message.from_user.id,
        f"🔔 Notifications turned {state}",
        reply_markup=get_admin_keyboard()
    )

# =========================
# 🏃‍♂️ RUN BOT
# =========================
def run_bot():
    """Run the bot"""
    while True:
        try:
            logger.info("=" * 50)
            logger.info("🚀 ZEDOX BOT STARTING...")
            logger.info(f"✅ Bot: @{bot.get_me().username}")
            logger.info(f"👑 Owner ID: {ADMIN_ID}")
            logger.info(f"💾 Database: MongoDB Connected")
            logger.info("📝 New Features: Edit Content, Fixed Code Gen")
            logger.info("=" * 50)
            
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logger.error(f"Bot error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_bot()
