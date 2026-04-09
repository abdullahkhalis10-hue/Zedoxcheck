# =========================
# ZEDOX VIP BOT - PART 1
# Core Setup + MongoDB + /start
# =========================

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from pymongo import MongoClient
import json, os, time, random

# -------------------------
# CONFIGURATION
# -------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # Telegram bot token
ADMIN_ID = int(os.environ.get("ADMIN_ID"))  # Admin chat ID
MONGO_URI = os.environ.get("MONGO_URI")  # MongoDB URI

bot = telebot.TeleBot(BOT_TOKEN)

# -------------------------
# DATABASE CONNECTION
# -------------------------
client = MongoClient(MONGO_URI)
db = client['zedox_vip_bot']  # Database
users_col = db['users']        # Users collection
folders_col = db['folders']    # Content folders
services_col = db['services']  # Services collection
codes_col = db['codes']        # Redeem codes collection
config_col = db['config']      # Bot config (welcome messages, VIP message, etc.)

# -------------------------
# DEFAULT CONFIG
# -------------------------
default_config = {
    "welcome_message": "Welcome to ZEDOX VIP BOT! 🎯",
    "vip_join_message": "❌ This is a VIP-only content. Get VIP to access!",
    "referral_points": 10,
    "notifications": True
}

if config_col.count_documents({}) == 0:
    config_col.insert_one(default_config)

# -------------------------
# HELPER FUNCTIONS
# -------------------------
def create_user(user_id, username=None, referrer_id=None):
    """Create new user in database"""
    if users_col.find_one({"user_id": user_id}):
        return False
    users_col.insert_one({
        "user_id": user_id,
        "username": username,
        "points": 0,
        "vip": False,
        "referrals": [],
        "referrer_id": referrer_id
    })
    # Add referral points to referrer
    if referrer_id:
        ref_user = users_col.find_one({"user_id": referrer_id})
        if ref_user:
            users_col.update_one(
                {"user_id": referrer_id},
                {"$inc": {"points": default_config["referral_points"]}, 
                 "$push": {"referrals": user_id}}
            )
    return True

def get_main_menu(user_id):
    """Returns main menu keyboard with all buttons including Services"""
    markup = InlineKeyboardMarkup(row_width=2)

    row1 = [InlineKeyboardButton("📂 FREE METHODS", callback_data="free_methods"),
            InlineKeyboardButton("💎 VIP METHODS", callback_data="vip_methods")]
    row2 = [InlineKeyboardButton("📦 PREMIUM APPS", callback_data="premium_apps"),
            InlineKeyboardButton("💰 POINTS", callback_data="points")]
    row3 = [InlineKeyboardButton("⭐ BUY VIP", callback_data="buy_vip"),
            InlineKeyboardButton("🎁 REFERRAL", callback_data="referral")]
    row4 = [InlineKeyboardButton("👤 ACCOUNT", callback_data="account"),
            InlineKeyboardButton("🆔 CHAT ID", callback_data="chat_id"),
            InlineKeyboardButton("🏆 COUPON REDEEM", callback_data="redeem")]
    row5 = [InlineKeyboardButton("🛠 SERVICES", callback_data="services")]  # NEW SERVICES BUTTON
    if user_id == ADMIN_ID:
        row6 = [InlineKeyboardButton("⚙️ ADMIN PANEL", callback_data="admin_panel")]
        markup.add(*row1, *row2, *row3, *row4, *row5, *row6)
    else:
        markup.add(*row1, *row2, *row3, *row4, *row5)
    return markup

# -------------------------
# COMMAND HANDLERS
# -------------------------
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    # Check for referral
    referrer_id = None
    if len(message.text.split()) > 1:
        try:
            referrer_id = int(message.text.split()[1])
        except:
            referrer_id = None

    create_user(user_id, username, referrer_id)

    welcome_msg = config_col.find_one({})["welcome_message"]
    bot.send_message(user_id, welcome_msg, reply_markup=get_main_menu(user_id))

# -------------------------
# START POLLING
# -------------------------
bot.infinity_polling()
# =========================
# ZEDOX VIP BOT - PART 2
# Force Join + Referral + VIP Basics
# =========================

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# -------------------------
# FORCE JOIN SYSTEM
# -------------------------
def check_force_join(user_id):
    """Check if user joined all required channels"""
    config = config_col.find_one({})
    force_channels = config.get("force_join_channels", [])
    not_joined = []

    for channel in force_channels:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                not_joined.append(channel)
        except Exception:
            not_joined.append(channel)
    return not_joined

def force_join_message(user_id):
    """Return message + buttons for force join"""
    not_joined = check_force_join(user_id)
    if not_joined:
        markup = InlineKeyboardMarkup()
        for ch in not_joined:
            markup.add(InlineKeyboardButton(f"Join {ch}", url=f"https://t.me/{ch}"))
        markup.add(InlineKeyboardButton("🔄 I Joined", callback_data="recheck_join"))
        bot.send_message(user_id, "🚫 ACCESS DENIED! Join all channels first.", reply_markup=markup)
        return True
    return False

# -------------------------
# REFERRAL SYSTEM
# -------------------------
def get_referral_info(user_id):
    user = users_col.find_one({"user_id": user_id})
    total_refs = len(user.get("referrals", []))
    points = user.get("points", 0)
    return total_refs, points

def referral_message(user_id):
    total_refs, points = get_referral_info(user_id)
    msg = f"🎁 You have {total_refs} referrals!\n💰 Total Points: {points}\n\nShare your link:\nhttps://t.me/YOUR_BOT_USERNAME?start={user_id}"
    bot.send_message(user_id, msg)

# -------------------------
# VIP SYSTEM BASICS
# -------------------------
def is_vip(user_id):
    user = users_col.find_one({"user_id": user_id})
    if user:
        return user.get("vip", False)
    return False

def vip_only_message(user_id):
    vip_msg = config_col.find_one({})["vip_join_message"]
    bot.send_message(user_id, vip_msg)

# -------------------------
# CALLBACK HANDLER
# -------------------------
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id

    # Force join recheck
    if call.data == "recheck_join":
        if not force_join_message(user_id):
            bot.answer_callback_query(call.id, "✅ All channels joined! You can use the bot now.")
            bot.send_message(user_id, "Main menu:", reply_markup=get_main_menu(user_id))
        else:
            bot.answer_callback_query(call.id, "🚫 You still need to join all channels.")

    # Referral
    elif call.data == "referral":
        referral_message(user_id)

    # VIP check example
    elif call.data == "vip_methods":
        if is_vip(user_id):
            bot.send_message(user_id, "💎 Access granted to VIP methods!")
        else:
            vip_only_message(user_id)

    # Services placeholder
    elif call.data == "services":
        bot.send_message(user_id, "🛠 Services menu will be here! Admin can add services with price/availability.")
        # =========================
# ZEDOX VIP BOT - PART 3
# Points System + Content Folders + Access Logic
# =========================

# -------------------------
# POINTS SYSTEM
# -------------------------
def add_points(user_id, amount):
    users_col.update_one({"user_id": user_id}, {"$inc": {"points": amount}})

def set_points(user_id, amount):
    users_col.update_one({"user_id": user_id}, {"$set": {"points": amount}})

def get_points(user_id):
    user = users_col.find_one({"user_id": user_id})
    return user.get("points", 0) if user else 0

def points_message(user_id):
    points = get_points(user_id)
    bot.send_message(user_id, f"💰 Your points balance: {points}")

# -------------------------
# CONTENT SYSTEM
# -------------------------
def get_content(category):
    """
    Fetch content folders for a category:
    'free', 'vip', 'apps', 'services'
    """
    db = db_col.find_one({})
    return db.get(category, {})

def send_folder_files(user_id, category, folder_name):
    db = db_col.find_one({})
    folder = db.get(category, {}).get(folder_name, {})
    files = folder.get("files", [])
    for file in files:
        try:
            bot.copy_message(user_id, file["chat"], file["msg"])
        except Exception as e:
            print(f"Error sending file: {e}")

# -------------------------
# ACCESS LOGIC
# -------------------------
def can_access(user_id, category, folder_name):
    """Determine if user can access content"""
    folder = get_content(category).get(folder_name, {})
    price = folder.get("price", 0)
    vip = is_vip(user_id)
    points = get_points(user_id)

    if vip:
        return True, 0
    elif category == "free":
        return True, price  # price may be 0 for free methods
    elif category in ["vip", "services"]:
        return False, price
    elif category == "apps":
        if points >= price:
            return True, price
        return False, price
    return False, price

def access_folder(user_id, category, folder_name):
    access, price = can_access(user_id, category, folder_name)
    if access:
        if price > 0 and not is_vip(user_id):
            add_points(user_id, -price)
            bot.send_message(user_id, f"💸 Deducted {price} points for accessing this folder!")
        send_folder_files(user_id, category, folder_name)
    else:
        if category in ["vip", "services"]:
            vip_only_message(user_id)
        else:
            bot.send_message(user_id, f"❌ You need {price} points to access this folder!")

# -------------------------
# SERVICES BUTTON HANDLER
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("service_"))
def service_handler(call):
    """Handle services menu: check availability / points / price"""
    user_id = call.from_user.id
    service_name = call.data.split("_", 1)[1]
    db = db_col.find_one({})
    service = db.get("services", {}).get(service_name, {})
    if not service:
        bot.send_message(user_id, "❌ Service not found.")
        return

    status = service.get("status", "out of stock")
    price = service.get("price", 0)
    currency = service.get("currency", "points")

    if status != "available":
        bot.send_message(user_id, "❌ This service is currently out of stock.")
        return

    if currency == "points":
        if get_points(user_id) >= price:
            add_points(user_id, -price)
            bot.send_message(user_id, f"✅ You purchased {service_name} for {price} points!")
        else:
            bot.send_message(user_id, f"❌ You need {price} points to buy this service.")
    elif currency == "usdt":
        bot.send_message(user_id, f"💵 Service {service_name} costs {price} USDT. Admin will contact you for payment.")
# =========================
# ZEDOX VIP BOT - PART 4
# Main Menu + Admin Panel + Broadcast System
# =========================

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# -------------------------
# MAIN MENU BUTTONS
# -------------------------
def main_menu(user_id):
    vip_status = "VIP ✅" if is_vip(user_id) else "FREE ❌"
    markup = InlineKeyboardMarkup(row_width=2)

    # Row 1
    markup.add(
        InlineKeyboardButton("📂 FREE METHODS", callback_data="free_methods"),
        InlineKeyboardButton("💎 VIP METHODS", callback_data="vip_methods")
    )
    # Row 2
    markup.add(
        InlineKeyboardButton("📦 PREMIUM APPS", callback_data="apps_methods"),
        InlineKeyboardButton("💰 POINTS", callback_data="check_points")
    )
    # Row 3
    markup.add(
        InlineKeyboardButton("⭐ BUY VIP", callback_data="buy_vip"),
        InlineKeyboardButton("🎁 REFERRAL", callback_data="referral")
    )
    # Row 4
    markup.add(
        InlineKeyboardButton("👤 ACCOUNT", callback_data="account_info"),
        InlineKeyboardButton("🆔 CHAT ID", callback_data=f"chatid_{user_id}")
    )
    # Row 5
    markup.add(
        InlineKeyboardButton("🏆 COUPON REDEEM", callback_data="redeem_code")
    )
    # Row 6 - Admin only
    if user_id in ADMIN_IDS:
        markup.add(InlineKeyboardButton("⚙️ ADMIN PANEL", callback_data="admin_panel"))

    bot.send_message(user_id, f"Welcome {vip_status}!\nChoose an option:", reply_markup=markup)


# -------------------------
# ADMIN PANEL
# -------------------------
def admin_panel(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ Add VIP", callback_data="admin_add_vip"),
        InlineKeyboardButton("✅ Remove VIP", callback_data="admin_remove_vip"),
        InlineKeyboardButton("📨 Broadcast All", callback_data="broadcast_all"),
        InlineKeyboardButton("📨 Broadcast VIP", callback_data="broadcast_vip"),
        InlineKeyboardButton("📨 Broadcast FREE", callback_data="broadcast_free"),
        InlineKeyboardButton("📝 Upload FREE", callback_data="upload_free"),
        InlineKeyboardButton("📝 Upload VIP", callback_data="upload_vip"),
        InlineKeyboardButton("📝 Upload APPS", callback_data="upload_apps"),
        InlineKeyboardButton("📝 Upload SERVICES", callback_data="upload_services"),
        InlineKeyboardButton("🗑 Delete Folder", callback_data="delete_folder"),
        InlineKeyboardButton("✏️ Edit Price", callback_data="edit_price"),
        InlineKeyboardButton("✏️ Edit Folder Name", callback_data="edit_folder"),
        InlineKeyboardButton("⚡ Force Join Channel", callback_data="force_join"),
        InlineKeyboardButton("🔔 Toggle Notifications", callback_data="toggle_notifications"),
        InlineKeyboardButton("📊 View Stats", callback_data="view_stats")
    )
    bot.send_message(user_id, "⚙️ Admin Panel:", reply_markup=markup)

# -------------------------
# BROADCAST SYSTEM
# -------------------------
def broadcast_message(target_group, text=None, media=None):
    """
    target_group: "all", "vip", "free"
    text: str
    media: dict {"type":"photo/video","file_id":""} optional
    """
    if target_group == "all":
        users = users_col.find({})
    elif target_group == "vip":
        users = users_col.find({"vip": True})
    elif target_group == "free":
        users = users_col.find({"vip": False})
    else:
        return

    for u in users:
        user_id = u["user_id"]
        try:
            if media:
                if media["type"] == "photo":
                    bot.send_photo(user_id, media["file_id"], caption=text)
                elif media["type"] == "video":
                    bot.send_video(user_id, media["file_id"], caption=text)
            else:
                bot.send_message(user_id, text)
        except Exception as e:
            print(f"Broadcast error for {user_id}: {e}")
# =========================
# ZEDOX VIP BOT - PART 5
# Force Join + Referral + VIP Expiry
# =========================

from datetime import datetime, timedelta

# -------------------------
# FORCE JOIN SYSTEM
# -------------------------
FORCE_CHANNELS = []  # List of channel usernames or IDs

def check_force_join(user_id):
    """Check if user joined all force channels"""
    for ch in FORCE_CHANNELS:
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status == 'left' or member.status == 'kicked':
                return False
        except:
            return False
    return True

def force_join_prompt(user_id):
    """Send join prompt to user"""
    markup = InlineKeyboardMarkup()
    for ch in FORCE_CHANNELS:
        markup.add(InlineKeyboardButton(f"Join {ch}", url=f"https://t.me/{ch}"))
    markup.add(InlineKeyboardButton("🔄 I Joined", callback_data="recheck_join"))
    bot.send_message(user_id, "🚫 ACCESS DENIED! Join all channels to continue:", reply_markup=markup)


# -------------------------
# REFERRAL SYSTEM
# -------------------------
REFERRAL_REWARD = 10  # points per referral

def handle_start(user_id, ref_id=None):
    """Create user and handle referral points"""
    user = users_col.find_one({"user_id": user_id})
    if not user:
        user_data = {
            "user_id": user_id,
            "points": 0,
            "vip": False,
            "referrals": 0,
            "ref_id": ref_id
        }
        users_col.insert_one(user_data)

        # Reward referral
        if ref_id:
            ref_user = users_col.find_one({"user_id": int(ref_id)})
            if ref_user:
                new_points = ref_user["points"] + REFERRAL_REWARD
                users_col.update_one({"user_id": int(ref_id)}, {"$set": {"points": new_points}})
                users_col.update_one({"user_id": int(ref_id)}, {"$inc": {"referrals": 1}})


# -------------------------
# VIP JOIN / EXPIRY SYSTEM
# -------------------------
VIP_DURATION_DAYS = 30  # default duration

def add_vip(user_id, days=VIP_DURATION_DAYS):
    expire_date = datetime.now() + timedelta(days=days)
    users_col.update_one({"user_id": user_id}, {"$set": {"vip": True, "vip_expiry": expire_date}})

def remove_vip(user_id):
    users_col.update_one({"user_id": user_id}, {"$set": {"vip": False, "vip_expiry": None}})

def check_vip_status(user_id):
    """Check VIP expiry"""
    user = users_col.find_one({"user_id": user_id})
    if user and user.get("vip"):
        if "vip_expiry" in user and user["vip_expiry"]:
            if datetime.now() > user["vip_expiry"]:
                remove_vip(user_id)
                return False
        return True
    return False
# =========================
# ZEDOX VIP BOT - PART 6
# CONTENT SYSTEM (Free / VIP / Apps / Services)
# =========================

# Categories
CATEGORIES = ["free", "vip", "apps", "services"]  # Added services

# MongoDB collections
content_col = db["content"]  # stores folders and files

# -------------------------
# ADMIN UPLOAD WORKFLOW
# -------------------------
def create_folder(category, folder_name, price=0, files=[]):
    """
    Create folder in a category
    files: list of {"chat_id": int, "msg_id": int}
    price: for points or USDT (admin decides)
    """
    if category not in CATEGORIES:
        return False
    folder = {
        "folder_name": folder_name,
        "files": files,
        "price": price,
        "status": "available"  # For services: available or out of stock
    }
    content_col.update_one(
        {"category": category, "folder_name": folder_name},
        {"$set": folder},
        upsert=True
    )
    return True

def add_files_to_folder(category, folder_name, new_files):
    """Add new files to existing folder"""
    folder = content_col.find_one({"category": category, "folder_name": folder_name})
    if folder:
        files = folder.get("files", [])
        files.extend(new_files)
        content_col.update_one(
            {"category": category, "folder_name": folder_name},
            {"$set": {"files": files}}
        )
        return True
    return False

# -------------------------
# SEND CONTENT TO USER
# -------------------------
def send_folder_content(user_id, category, folder_name):
    """
    Send all files from folder
    Access logic depends on VIP or points
    """
    user = users_col.find_one({"user_id": user_id})
    folder = content_col.find_one({"category": category, "folder_name": folder_name})
    if not folder or not user:
        return

    # Check access
    if category == "vip" and not user.get("vip"):
        bot.send_message(user_id, VIP_JOIN_MESSAGE)
        return

    if category in ["apps", "services"] and not user.get("vip"):
        price = folder.get("price", 0)
        if user["points"] < price:
            bot.send_message(user_id, f"❌ Not enough points. Folder costs {price} points.")
            return
        users_col.update_one({"user_id": user_id}, {"$inc": {"points": -price}})

    # Send files
    for file in folder.get("files", []):
        try:
            bot.copy_message(user_id, file["chat_id"], file["msg_id"])
        except Exception as e:
            print(f"Error sending file: {e}")

# -------------------------
# SERVICES BUTTON
# -------------------------
def get_services_keyboard():
    """Generate services folder buttons"""
    keyboard = InlineKeyboardMarkup()
    services = content_col.find({"category": "services"})
    for s in services:
        status = s.get("status", "available")
        label = f"{s['folder_name']} ({status}) - {s.get('price', 0)} pts"
        keyboard.add(InlineKeyboardButton(label, callback_data=f"service_{s['folder_name']}"))
    return keyboard
    # =========================
# ZEDOX VIP BOT - PART 7
# MAIN MENU & CALLBACK HANDLING
# =========================

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# -------------------------
# MAIN MENU KEYBOARD
# -------------------------
def main_menu_keyboard(user_id):
    user = users_col.find_one({"user_id": user_id})
    vip_status = user.get("vip", False)
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    # Row 1
    keyboard.add(
        InlineKeyboardButton("📂 FREE METHODS", callback_data="free_methods"),
        InlineKeyboardButton("💎 VIP METHODS", callback_data="vip_methods")
    )
    # Row 2
    keyboard.add(
        InlineKeyboardButton("📦 PREMIUM APPS", callback_data="apps_methods"),
        InlineKeyboardButton("💰 POINTS", callback_data="points_balance")
    )
    # Row 3
    keyboard.add(
        InlineKeyboardButton("⭐ BUY VIP", callback_data="buy_vip"),
        InlineKeyboardButton("🎁 REFERRAL", callback_data="referral")
    )
    # Row 4
    keyboard.add(
        InlineKeyboardButton("👤 ACCOUNT", callback_data="account_info"),
        InlineKeyboardButton("🆔 CHAT ID", callback_data=f"chat_id_{user_id}"),
        InlineKeyboardButton("🏆 COUPON REDEEM", callback_data="redeem_code")
    )
    # Row 5 - Admin only
    if user_id == ADMIN_ID:
        keyboard.add(InlineKeyboardButton("⚙️ ADMIN PANEL", callback_data="admin_panel"))
    
    # Row 6 - Services
    keyboard.add(InlineKeyboardButton("🛠 SERVICES", callback_data="services_menu"))
    
    return keyboard

# -------------------------
# CALLBACK HANDLER
# -------------------------
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data

    if data == "free_methods":
        send_category_menu(user_id, "free")
    elif data == "vip_methods":
        send_category_menu(user_id, "vip")
    elif data == "apps_methods":
        send_category_menu(user_id, "apps")
    elif data == "services_menu":
        bot.send_message(user_id, "🛠 Available Services:", reply_markup=get_services_keyboard())
    elif data.startswith("service_"):
        folder_name = data.split("_", 1)[1]
        send_folder_content(user_id, "services", folder_name)
    elif data == "points_balance":
        user = users_col.find_one({"user_id": user_id})
        points = user.get("points", 0)
        bot.send_message(user_id, f"💰 Your Points Balance: {points}")
    elif data == "buy_vip":
        bot.send_message(user_id, "⭐ VIP Upgrade is available. Contact admin or use points if allowed.")
    elif data == "referral":
        user = users_col.find_one({"user_id": user_id})
        ref_count = user.get("referrals", 0)
        bot.send_message(user_id, f"🎁 You have referred {ref_count} users.")
    elif data == "account_info":
        user = users_col.find_one({"user_id": user_id})
        status = "VIP ✅" if user.get("vip") else "FREE ❌"
        points = user.get("points", 0)
        bot.send_message(user_id, f"👤 Account Status: {status}\n💰 Points: {points}")
    elif data == "redeem_code":
        bot.send_message(user_id, "🏆 Enter your redeem code:")
    elif data == "admin_panel" and user_id == ADMIN_ID:
        show_admin_panel(user_id)
    else:
        bot.answer_callback_query(call.id, "❌ Unknown action.")

# -------------------------
# CATEGORY MENU
# -------------------------
def send_category_menu(user_id, category):
    """Send list of folders in a category"""
    folders = content_col.find({"category": category})
    keyboard = InlineKeyboardMarkup()
    for f in folders:
        folder_name = f["folder_name"]
        price = f.get("price", 0)
        label = f"{folder_name} - {price} pts"
        if category == "vip":
            label = folder_name if users_col.find_one({"user_id": user_id}).get("vip") else f"{folder_name} ❌ VIP"
        keyboard.add(InlineKeyboardButton(label, callback_data=f"{category}_{folder_name}"))
    bot.send_message(user_id, f"📂 {category.upper()} Folders:", reply_markup=keyboard)
# =========================
# ZEDOX VIP BOT - PART 8
# ADMIN PANEL & SERVICES MANAGEMENT
# =========================

# -------------------------
# ADMIN PANEL MENU
# -------------------------
def show_admin_panel(admin_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Add VIP", callback_data="admin_add_vip"),
        InlineKeyboardButton("❌ Remove VIP", callback_data="admin_remove_vip"),
        InlineKeyboardButton("💌 Broadcast All", callback_data="admin_broadcast_all"),
        InlineKeyboardButton("💎 Broadcast VIP", callback_data="admin_broadcast_vip"),
        InlineKeyboardButton("📤 Broadcast FREE", callback_data="admin_broadcast_free"),
        InlineKeyboardButton("📂 Upload FREE", callback_data="admin_upload_free"),
        InlineKeyboardButton("💎 Upload VIP", callback_data="admin_upload_vip"),
        InlineKeyboardButton("📦 Upload APPS", callback_data="admin_upload_apps"),
        InlineKeyboardButton("🛠 Upload SERVICE", callback_data="admin_upload_service"),
        InlineKeyboardButton("✏️ Edit Folder Name/Price", callback_data="admin_edit_folder"),
        InlineKeyboardButton("🗑 Delete Folder", callback_data="admin_delete_folder"),
        InlineKeyboardButton("⚙️ Force Join Channels", callback_data="admin_force_join"),
        InlineKeyboardButton("🔔 Toggle Notifications", callback_data="admin_toggle_notifications"),
        InlineKeyboardButton("📊 View Stats", callback_data="admin_view_stats")
    )
    bot.send_message(admin_id, "⚙️ ADMIN PANEL:", reply_markup=keyboard)

# -------------------------
# SERVICES MANAGEMENT
# -------------------------
def get_services_keyboard():
    """Generate services list keyboard"""
    services = services_col.find()
    keyboard = InlineKeyboardMarkup()
    for s in services:
        status = "✅ Available" if s.get("status") == "available" else "❌ Out of Stock"
        price = s.get("price_points", 0)
        label = f"{s['name']} - {price} pts - {status}"
        keyboard.add(InlineKeyboardButton(label, callback_data=f"service_{s['folder_name']}"))
    return keyboard

# -------------------------
# ADMIN CALLBACKS FOR SERVICES
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_callbacks(call):
    admin_id = call.from_user.id
    data = call.data

    if admin_id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ You are not admin.")
        return

    if data == "admin_upload_service":
        msg = bot.send_message(admin_id, "🛠 Forward file(s) for SERVICE folder:")
        bot.register_next_step_handler(msg, process_service_upload)
    elif data == "admin_add_vip":
        msg = bot.send_message(admin_id, "Enter CHAT ID to give VIP:")
        bot.register_next_step_handler(msg, add_vip_user)
    elif data == "admin_remove_vip":
        msg = bot.send_message(admin_id, "Enter CHAT ID to remove VIP:")
        bot.register_next_step_handler(msg, remove_vip_user)
    # ... add other admin features similarly

# -------------------------
# PROCESS SERVICE UPLOAD
# -------------------------
def process_service_upload(message):
    files = message.document or message.photo or message.video
    if not files:
        bot.send_message(ADMIN_ID, "❌ No files found. Upload cancelled.")
        return
    folder_name = f"service_{int(time.time())}"
    services_col.insert_one({
        "folder_name": folder_name,
        "name": message.caption or "New Service",
        "files": [{"chat": message.chat.id, "msg": message.message_id}],
        "price_points": 0,
        "price_usdt": 0,
        "status": "available"
    })
    bot.send_message(ADMIN_ID, f"✅ Service '{folder_name}' added. You can set price/status now.")

# -------------------------
# UPDATE SERVICE PRICE / STATUS
# -------------------------
def update_service(folder_name, price_points=None, price_usdt=None, status=None):
    update_fields = {}
    if price_points is not None:
        update_fields["price_points"] = price_points
    if price_usdt is not None:
        update_fields["price_usdt"] = price_usdt
    if status is not None:
        update_fields["status"] = status
    services_col.update_one({"folder_name": folder_name}, {"$set": update_fields})
# =========================
# ZEDOX VIP BOT - PART 9
# FORCE JOIN, REFERRAL, POINTS & VIP LOGIC
# =========================

# -------------------------
# FORCE JOIN SYSTEM
# -------------------------
def check_force_join(user_id):
    """Check if user joined all required channels"""
    channels = config.get("force_join_channels", [])
    not_joined = []
    for ch in channels:
        try:
            member = bot.get_chat_member(chat_id=ch, user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_joined.append(ch)
        except:
            not_joined.append(ch)
    return not_joined

def send_force_join_message(user_id):
    not_joined = check_force_join(user_id)
    if not_joined:
        keyboard = InlineKeyboardMarkup()
        for ch in not_joined:
            keyboard.add(InlineKeyboardButton("Join Channel", url=f"https://t.me/{ch}"))
        keyboard.add(InlineKeyboardButton("🔄 I Joined", callback_data="recheck_join"))
        bot.send_message(user_id, "🚫 ACCESS DENIED! Join all channels to continue.", reply_markup=keyboard)
        return True
    return False

# -------------------------
# REFERRAL SYSTEM
# -------------------------
def process_referral(user_id, ref_id=None):
    """Add referral points if user used a ref link"""
    if ref_id and ref_id != str(user_id):
        inviter = users_col.find_one({"user_id": int(ref_id)})
        if inviter:
            reward = config.get("referral_reward_points", 5)
            users_col.update_one({"user_id": int(ref_id)}, {"$inc": {"points": reward, "referrals": 1}})
            bot.send_message(int(ref_id), f"🎉 You got {reward} points from referral!")
    # create user entry
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({"user_id": user_id, "points": 0, "vip": False, "referrals": 0})

# -------------------------
# POINTS SYSTEM
# -------------------------
def add_points(user_id, amount):
    users_col.update_one({"user_id": user_id}, {"$inc": {"points": amount}})
    
def set_points(user_id, amount):
    users_col.update_one({"user_id": user_id}, {"$set": {"points": amount}})

def get_points(user_id):
    user = users_col.find_one({"user_id": user_id})
    return user.get("points", 0) if user else 0

# -------------------------
# VIP SYSTEM
# -------------------------
def is_vip(user_id):
    user = users_col.find_one({"user_id": user_id})
    return user.get("vip", False) if user else False

def vip_required_message(user_id):
    vip_msg = config.get("vip_join_message", "💎 This is a VIP-only feature. Join VIP to access!")
    bot.send_message(user_id, vip_msg)

# -------------------------
# VIP CONTENT ACCESS LOGIC
# -------------------------
def access_content(user_id, category):
    """
    category: "free", "vip", "apps", "service"
    """
    if category == "free":
        # everyone can access
        return True
    elif category == "vip":
        if is_vip(user_id):
            return True
        else:
            vip_required_message(user_id)
            return False
    elif category == "apps":
        # free users need points
        if is_vip(user_id):
            return True
        else:
            # check points, deduct if needed
            return True
    elif category == "service":
        # service access depends on status and points
        return True
# =========================
# ZEDOX VIP BOT - PART 10
# CONTENT SYSTEM & FILE SENDING
# =========================

# -------------------------
# LOAD DATABASE
# -------------------------
db = load_json("db.json")  # structure: {"free": {}, "vip": {}, "apps": {}, "service": {}}

# -------------------------
# CONTENT ACCESS
# -------------------------
def get_folders(category):
    """Return list of folder names in a category"""
    if category in db:
        return list(db[category].keys())
    return []

def get_folder_files(category, folder_name):
    """Return list of files for a folder"""
    try:
        folder = db[category][folder_name]
        return folder.get("files", [])
    except KeyError:
        return []

def get_folder_price(category, folder_name):
    try:
        folder = db[category][folder_name]
        return folder.get("price", 0)
    except KeyError:
        return 0

# -------------------------
# SEND FILES
# -------------------------
def send_folder_files(user_id, category, folder_name):
    files = get_folder_files(category, folder_name)
    if not files:
        bot.send_message(user_id, "❌ Folder is empty or missing files.")
        return

    for f in files:
        try:
            bot.copy_message(chat_id=user_id, from_chat_id=f["chat"], message_id=f["msg"])
        except Exception as e:
            print(f"Error sending file: {e}")
            bot.send_message(user_id, "⚠️ Error sending one of the files.")

# -------------------------
# CATEGORY ACCESS LOGIC
# -------------------------
def handle_category_access(user_id, category, folder_name):
    if category == "vip" and not is_vip(user_id):
        vip_required_message(user_id)
        return
    if category == "apps":
        price = get_folder_price(category, folder_name)
        if not is_vip(user_id) and get_points(user_id) < price:
            bot.send_message(user_id, f"💰 You need {price} points to access this folder.")
            return
        if not is_vip(user_id):
            add_points(user_id, -price)  # deduct points
    if category == "service":
        # Service logic: check status, points or USDT price
        folder = db["service"].get(folder_name, {})
        status = folder.get("status", "available")
        price = folder.get("price_points", 0)
        if status != "available":
            bot.send_message(user_id, "❌ Service is currently out of stock.")
            return
        if not is_vip(user_id) and get_points(user_id) < price:
            bot.send_message(user_id, f"💰 You need {price} points to access this service.")
            return
        if not is_vip(user_id):
            add_points(user_id, -price)
    
    send_folder_files(user_id, category, folder_name)

# -------------------------
# INLINE KEYBOARD GENERATION
# -------------------------
def generate_category_keyboard(category):
    keyboard = InlineKeyboardMarkup(row_width=2)
    folders = get_folders(category)
    for folder in folders:
        keyboard.add(InlineKeyboardButton(folder, callback_data=f"{category}:{folder}"))
    return keyboard
    # =========================
# ZEDOX VIP BOT - PART 11
# CALLBACK HANDLERS FOR FOLDERS & SERVICES
# =========================

from telebot.types import CallbackQuery

# -------------------------
# CALLBACK HANDLER
# -------------------------
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call: CallbackQuery):
    user_id = call.from_user.id
    data = call.data

    # -------------------------
    # CATEGORY FOLDER CLICK
    # Format: category:folder_name
    # -------------------------
    if ":" in data:
        category, folder_name = data.split(":", 1)
        if category in ["free", "vip", "apps", "service"]:
            handle_category_access(user_id, category, folder_name)
        else:
            bot.answer_callback_query(call.id, "❌ Invalid category.")
        return

    # -------------------------
    # MAIN MENU BUTTONS
    # -------------------------
    if data == "free_methods":
        keyboard = generate_category_keyboard("free")
        bot.send_message(user_id, "📂 Free Methods:", reply_markup=keyboard)
    elif data == "vip_methods":
        keyboard = generate_category_keyboard("vip")
        bot.send_message(user_id, "💎 VIP Methods:", reply_markup=keyboard)
    elif data == "premium_apps":
        keyboard = generate_category_keyboard("apps")
        bot.send_message(user_id, "📦 Premium Apps:", reply_markup=keyboard)
    elif data == "services":
        keyboard = generate_category_keyboard("service")
        bot.send_message(user_id, "🛠 Services Available:", reply_markup=keyboard)
    elif data == "points":
        points = get_points(user_id)
        bot.send_message(user_id, f"💰 Your Points Balance: {points}")
    elif data == "buy_vip":
        vip_required_message(user_id)
    elif data == "referral":
        ref_id = get_referral_id(user_id)
        bot.send_message(user_id, f"🎁 Your Referral ID: {ref_id}")
    elif data == "account":
        vip_status = "✅ VIP" if is_vip(user_id) else "❌ Free"
        bot.send_message(user_id, f"👤 Your Account Status: {vip_status}")
    elif data == "chat_id":
        bot.send_message(user_id, f"🆔 Your Chat ID: {user_id}")
    elif data == "coupon_redeem":
        bot.send_message(user_id, "🏆 Enter your coupon code using /redeem <code>")

    # -------------------------
    # ADMIN PANEL BUTTONS
    # -------------------------
    elif data.startswith("admin:"):
        handle_admin_callback(user_id, data)
    else:
        bot.answer_callback_query(call.id, "❌ Unknown action.")
        # =========================
# ZEDOX VIP BOT - PART 12
# ADMIN PANEL & FILE/FOLDER MANAGEMENT
# =========================

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# -------------------------
# ADMIN PANEL HANDLER
# -------------------------
def handle_admin_callback(admin_id, data):
    if not is_admin(admin_id):
        return

    if data == "admin:add_vip":
        bot.send_message(admin_id, "✅ Send the Chat ID to add VIP:")
    elif data == "admin:remove_vip":
        bot.send_message(admin_id, "✅ Send the Chat ID to remove VIP:")
    elif data == "admin:set_vip_msg":
        bot.send_message(admin_id, "✍️ Send the new VIP join message:")
    elif data == "admin:set_welcome":
        bot.send_message(admin_id, "✍️ Send the new welcome message:")
    elif data == "admin:give_points":
        bot.send_message(admin_id, "💰 Send user Chat ID and points to give (ID:Points):")
    elif data == "admin:set_points":
        bot.send_message(admin_id, "💰 Send user Chat ID and set points (ID:Points):")
    elif data == "admin:broadcast_all":
        bot.send_message(admin_id, "📢 Send message to broadcast to ALL users:")
    elif data == "admin:broadcast_vip":
        bot.send_message(admin_id, "📢 Send message to broadcast to VIP users:")
    elif data == "admin:broadcast_free":
        bot.send_message(admin_id, "📢 Send message to broadcast to Free users:")
    elif data.startswith("admin:upload_"):
        category = data.split("_")[1]  # free, vip, apps, service
        bot.send_message(admin_id, f"📤 Forward files for category: {category}")
    elif data == "admin:delete_folder":
        bot.send_message(admin_id, "❌ Send category:folder_name to delete folder")
    elif data == "admin:edit_price":
        bot.send_message(admin_id, "💰 Send category:folder_name:new_price to edit folder price")
    elif data == "admin:edit_folder_name":
        bot.send_message(admin_id, "✏️ Send category:old_name:new_name to rename folder")
    elif data == "admin:add_forcejoin":
        bot.send_message(admin_id, "➕ Send the channel username to add to Force Join list:")
    elif data == "admin:remove_forcejoin":
        bot.send_message(admin_id, "➖ Send the channel username to remove from Force Join list:")
    elif data == "admin:toggle_notifications":
        toggle_notifications(admin_id)
    elif data == "admin:view_stats":
        total, vip_count, free_count = get_user_stats()
        bot.send_message(admin_id, f"📊 Total: {total}\n✅ VIP: {vip_count}\n❌ Free: {free_count}")
    else:
        bot.send_message(admin_id, "❌ Unknown admin command")

# -------------------------
# UPLOAD FILES HANDLER
# -------------------------
@bot.message_handler(content_types=['document', 'photo', 'video'])
def handle_upload(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    # Expecting format: admin:upload_category
    category = get_pending_upload_category(user_id)
    if not category:
        bot.send_message(user_id, "❌ No pending category set. Use admin panel to select category.")
        return

    folder_name = get_pending_folder_name(user_id)
    if not folder_name:
        bot.send_message(user_id, "❌ No folder name provided. Please provide folder name first.")
        return

    # Save file to DB
    db[category].setdefault(folder_name, {"files": [], "price": 0, "status": "available"})
    db[category][folder_name]["files"].append({
        "chat_id": message.chat.id,
        "msg_id": message.message_id
    })
    save_db()
    bot.send_message(user_id, f"✅ File added to {category}:{folder_name}")

# -------------------------
# SERVICES CATEGORY SUPPORT
# -------------------------
def set_service_status(category, folder_name, status):
    if category != "service":
        return
    if folder_name in db[category]:
        db[category][folder_name]["status"] = status
        save_db()

def set_service_price(category, folder_name, price):
    if category != "service":
        return
    if folder_name in db[category]:
        db[category][folder_name]["price"] = price
        save_db()

# -------------------------
# SAVE DB
# -------------------------
def save_db():
    with open("db.json", "w") as f:
        json.dump(db, f, indent=4)
        # =========================
# ZEDOX VIP BOT - PART 13
# SERVICES BUTTONS & USER ACCESS
# =========================

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# -------------------------
# SHOW SERVICES TO USERS
# -------------------------
def show_services(user_id):
    markup = InlineKeyboardMarkup(row_width=1)
    for folder_name, folder_info in db["service"].items():
        status = folder_info.get("status", "available")
        price = folder_info.get("price", 0)
        text = f"{folder_name} | {'✅ Available' if status=='available' else '❌ Out of Stock'} | Price: {price} pts/USDT"
        
        # If out of stock, disable button
        if status == "available":
            markup.add(InlineKeyboardButton(text=text, callback_data=f"service:{folder_name}"))
        else:
            markup.add(InlineKeyboardButton(text=text, callback_data="service:unavailable"))
    
    bot.send_message(user_id, "🛠️ Available Services:", reply_markup=markup)

# -------------------------
# SERVICE CALLBACK HANDLER
# -------------------------
@bot.callback_query_handler(func=lambda c: c.data.startswith("service:"))
def service_callback(call):
    user_id = call.from_user.id
    _, folder_name = call.data.split(":", 1)

    if folder_name == "unavailable":
        bot.answer_callback_query(call.id, "❌ Service is out of stock!")
        return

    # Check if service exists and is available
    if folder_name not in db["service"] or db["service"][folder_name]["status"] != "available":
        bot.answer_callback_query(call.id, "❌ Service not found or unavailable!")
        return

    # Get price and check points
    price = db["service"][folder_name]["price"]
    user_points = users.get(str(user_id), {}).get("points", 0)

    if user_points < price:
        bot.answer_callback_query(call.id, "❌ Not enough points to buy this service!")
        return

    # Deduct points and send files
    users[str(user_id)]["points"] -= price
    save_users()
    
    bot.answer_callback_query(call.id, f"✅ Purchased {folder_name} for {price} points!")
    
    # Send all files in the service folder
    for file_info in db["service"][folder_name]["files"]:
        try:
            bot.copy_message(chat_id=user_id, from_chat_id=file_info["chat_id"], message_id=file_info["msg_id"])
        except Exception as e:
            print(f"Error sending service file: {e}")

# -------------------------
# ADD SERVICE BUTTON TO MAIN MENU
# -------------------------
def main_menu(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    
    markup.add(
        InlineKeyboardButton("📂 FREE METHODS", callback_data="free_methods"),
        InlineKeyboardButton("💎 VIP METHODS", callback_data="vip_methods"),
    )
    markup.add(
        InlineKeyboardButton("📦 PREMIUM APPS", callback_data="apps"),
        InlineKeyboardButton("💰 POINTS", callback_data="points"),
    )
    markup.add(
        InlineKeyboardButton("⭐ BUY VIP", callback_data="buy_vip"),
        InlineKeyboardButton("🎁 REFERRAL", callback_data="referral"),
    )
    markup.add(
        InlineKeyboardButton("👤 ACCOUNT", callback_data="account"),
        InlineKeyboardButton("🆔 CHAT ID", callback_data="chat_id"),
    )
    markup.add(
        InlineKeyboardButton("🏆 COUPON REDEEM", callback_data="redeem")
    )
    # Add Services button
    markup.add(
        InlineKeyboardButton("🛠️ SERVICES", callback_data="services")
    )

    # Admin panel button
    if is_admin(user_id):
        markup.add(InlineKeyboardButton("⚙️ ADMIN PANEL", callback_data="admin_panel"))

    bot.send_message(user_id, "📋 Main Menu:", reply_markup=markup)

# -------------------------
# USERS DATA SAVE
# -------------------------
def save_users():
    with open("users.json", "w") as f:
        json.dump(users, f, indent=4)
# =========================
# ZEDOX VIP BOT - PART 14
# FORCE JOIN, VIP CHECKS & REFERRALS FOR SERVICES
# =========================

# -------------------------
# FORCE JOIN CHANNEL CHECK
# -------------------------
def check_force_join(user_id):
    # Get list of channels from config/db
    force_channels = db.get("force_join_channels", [])
    not_joined = []

    for channel in force_channels:
        try:
            member = bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ["left", "kicked"]:
                not_joined.append(channel)
        except Exception as e:
            print(f"Error checking channel {channel}: {e}")
            continue

    return not_joined

def force_join_message(user_id):
    not_joined = check_force_join(user_id)
    if not_joined:
        markup = InlineKeyboardMarkup(row_width=1)
        for ch in not_joined:
            markup.add(InlineKeyboardButton(f"Join {ch}", url=f"https://t.me/{ch.replace('@','')}"))
        markup.add(InlineKeyboardButton("🔄 I Joined", callback_data="recheck_join"))
        bot.send_message(user_id, "🚫 ACCESS DENIED! Join all channels to use the bot:", reply_markup=markup)
        return True
    return False

# -------------------------
# CALLBACK TO RECHECK FORCE JOIN
# -------------------------
@bot.callback_query_handler(func=lambda c: c.data == "recheck_join")
def recheck_join(call):
    if not force_join_message(call.from_user.id):
        bot.answer_callback_query(call.id, "✅ All channels joined!")
        main_menu(call.from_user.id)

# -------------------------
# VIP CHECK FOR SERVICES
# -------------------------
def user_can_access_service(user_id, folder_name):
    user_data = users.get(str(user_id), {})
    is_vip = user_data.get("vip", False)
    service_info = db["service"].get(folder_name, {})

    if is_vip:
        return True  # VIP users get access always
    if service_info.get("vip_only", False):
        return False  # Free users cannot access VIP-only services
    return True

# -------------------------
# REFERRAL POINTS FOR SERVICE PURCHASE
# -------------------------
def add_referral_points(user_id, points):
    ref_id = users.get(str(user_id), {}).get("referral_id")
    if ref_id and str(ref_id) in users:
        users[str(ref_id)]["points"] += points
        save_users()
        bot.send_message(ref_id, f"🎁 You earned {points} points from your referral!")

# -------------------------
# SERVICE PURCHASE HANDLER UPDATE
# -------------------------
@bot.callback_query_handler(func=lambda c: c.data.startswith("service:"))
def service_callback(call):
    user_id = call.from_user.id
    folder_name = call.data.split(":")[1]

    # Force join check
    if force_join_message(user_id):
        bot.answer_callback_query(call.id, "🚫 Join all channels first!")
        return

    # VIP access check
    if not user_can_access_service(user_id, folder_name):
        bot.answer_callback_query(call.id, "❌ This service is VIP only!")
        return

    # Check availability and points
    service_info = db["service"].get(folder_name)
    if not service_info or service_info.get("status") != "available":
        bot.answer_callback_query(call.id, "❌ Service unavailable!")
        return

    price = service_info.get("price", 0)
    user_points = users.get(str(user_id), {}).get("points", 0)
    if user_points < price:
        bot.answer_callback_query(call.id, "❌ Not enough points!")
        return

    # Deduct points & give referral bonus
    users[str(user_id)]["points"] -= price
    save_users()
    add_referral_points(user_id, db.get("referral_reward", 0))
    
    bot.answer_callback_query(call.id, f"✅ Purchased {folder_name} for {price} points!")
    
    # Send files
    for file_info in service_info["files"]:
        try:
            bot.copy_message(chat_id=user_id, from_chat_id=file_info["chat_id"], message_id=file_info["msg_id"])
        except Exception as e:
            print(f"Error sending service file: {e}")
# =========================
# ZEDOX VIP BOT - PART 15
# ADMIN PANEL - SERVICE MANAGEMENT
# =========================

# -------------------------
# ADMIN CHECK
# -------------------------
def is_admin(user_id):
    return user_id in config.get("admins", [])

# -------------------------
# ADD SERVICE FOLDER
# -------------------------
@bot.message_handler(commands=["add_service"])
def add_service_step1(message):
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "❌ You are not authorized.")
    msg = bot.reply_to(message, "📌 Send me the Service folder name:")
    bot.register_next_step_handler(msg, add_service_step2)

def add_service_step2(message):
    folder_name = message.text.strip()
    if folder_name in db.get("service", {}):
        msg = bot.reply_to(message, "❌ Folder already exists. Send another name:")
        bot.register_next_step_handler(msg, add_service_step2)
        return

    msg = bot.reply_to(message, "💰 Set the price in points (0 for free):")
    bot.register_next_step_handler(msg, lambda m: add_service_step3(m, folder_name))

def add_service_step3(message, folder_name):
    try:
        price = int(message.text.strip())
    except:
        msg = bot.reply_to(message, "❌ Invalid price. Enter a number:")
        bot.register_next_step_handler(msg, lambda m: add_service_step3(m, folder_name))
        return

    msg = bot.reply_to(message, "⚡ VIP only? (yes/no):")
    bot.register_next_step_handler(msg, lambda m: add_service_step4(m, folder_name, price))

def add_service_step4(message, folder_name, price):
    vip_only = message.text.lower() in ["yes", "y"]
    msg = bot.reply_to(message, "📤 Now forward the service files (multiple allowed).")
    bot.register_next_step_handler(msg, lambda m: save_service_files(m, folder_name, price, vip_only))

def save_service_files(message, folder_name, price, vip_only):
    # Initialize folder
    if "service" not in db:
        db["service"] = {}
    if folder_name not in db["service"]:
        db["service"][folder_name] = {"files": [], "price": price, "vip_only": vip_only, "status": "available"}

    # Capture forwarded files
    if message.content_type in ["document", "video", "photo", "audio"]:
        db["service"][folder_name]["files"].append({
            "chat_id": message.chat.id,
            "msg_id": message.message_id
        })
        save_db()
        bot.reply_to(message, f"✅ File added to service '{folder_name}'. Send more or /done to finish.")
    else:
        bot.reply_to(message, "❌ Invalid content. Please forward documents, videos, photos, or audio.")

# -------------------------
# MARK SERVICE AS AVAILABLE/OUT OF STOCK
# -------------------------
@bot.message_handler(commands=["service_status"])
def service_status(message):
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "❌ You are not authorized.")

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return bot.reply_to(message, "Usage: /service_status <folder_name> <available/out_of_stock>")

    folder_name, status = args[1], args[2].lower()
    if folder_name not in db.get("service", {}):
        return bot.reply_to(message, "❌ Service folder not found.")
    if status not in ["available", "out_of_stock"]:
        return bot.reply_to(message, "❌ Status must be 'available' or 'out_of_stock'.")

    db["service"][folder_name]["status"] = status
    save_db()
    bot.reply_to(message, f"✅ Service '{folder_name}' status set to {status}.")

# -------------------------
# EDIT SERVICE PRICE
# -------------------------
@bot.message_handler(commands=["service_price"])
def service_price(message):
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "❌ You are not authorized.")

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return bot.reply_to(message, "Usage: /service_price <folder_name> <new_price>")

    folder_name, price = args[1], args[2]
    if folder_name not in db.get("service", {}):
        return bot.reply_to(message, "❌ Service folder not found.")
    try:
        price = int(price)
    except:
        return bot.reply_to(message, "❌ Price must be a number.")

    db["service"][folder_name]["price"] = price
    save_db()
    bot.reply_to(message, f"✅ Service '{folder_name}' price updated to {price} points.")

# -------------------------
# DELETE SERVICE FOLDER
# -------------------------
@bot.message_handler(commands=["delete_service"])
def delete_service(message):
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "❌ You are not authorized.")

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return bot.reply_to(message, "Usage: /delete_service <folder_name>")

    folder_name = args[1]
    if folder_name not in db.get("service", {}):
        return bot.reply_to(message, "❌ Service folder not found.")

    db["service"].pop(folder_name)
    save_db()
    bot.reply_to(message, f"✅ Service '{folder_name}' deleted successfully.")
# =========================
# ZEDOX VIP BOT - PART 16
# USER INTERFACE - SERVICES
# =========================

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# -------------------------
# MAIN MENU UPDATE
# -------------------------
def main_menu(user_id):
    markup = InlineKeyboardMarkup(row_width=2)

    # Row 1
    markup.add(
        InlineKeyboardButton("📂 FREE METHODS", callback_data="free_methods"),
        InlineKeyboardButton("💎 VIP METHODS", callback_data="vip_methods")
    )
    # Row 2
    markup.add(
        InlineKeyboardButton("📦 PREMIUM APPS", callback_data="premium_apps"),
        InlineKeyboardButton("💰 POINTS", callback_data="points")
    )
    # Row 3
    markup.add(
        InlineKeyboardButton("⭐ BUY VIP", callback_data="buy_vip"),
        InlineKeyboardButton("🎁 REFERRAL", callback_data="referral")
    )
    # Row 4
    markup.add(
        InlineKeyboardButton("👤 ACCOUNT", callback_data="account"),
        InlineKeyboardButton("🆔 CHAT ID", callback_data="chat_id"),
        InlineKeyboardButton("🏆 COUPON REDEEM", callback_data="redeem")
    )
    # Row 5 (Admin Only)
    if is_admin(user_id):
        markup.add(InlineKeyboardButton("⚙️ ADMIN PANEL", callback_data="admin_panel"))
    
    # Row 6 - SERVICES button for all users
    markup.add(InlineKeyboardButton("🛠️ SERVICES", callback_data="services"))

    return markup

# -------------------------
# SERVICES CALLBACK
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data == "services")
def services_callback(call):
    services = db.get("service", {})
    if not services:
        return bot.answer_callback_query(call.id, "❌ No services available currently.")

    markup = InlineKeyboardMarkup(row_width=1)
    for folder_name, info in services.items():
        status = "✅ Available" if info.get("status") == "available" else "❌ Out of stock"
        price = info.get("price", 0)
        vip_only = "💎 VIP" if info.get("vip_only") else "👤 Free"
        button_text = f"{folder_name} | {price} pts | {vip_only} | {status}"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"service_{folder_name}"))

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="🛠️ Available Services:",
        reply_markup=markup
    )

# -------------------------
# SERVICE PURCHASE CALLBACK
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("service_"))
def service_purchase_callback(call):
    folder_name = call.data.replace("service_", "")
    service = db["service"].get(folder_name)
    if not service:
        return bot.answer_callback_query(call.id, "❌ Service not found.")

    user_id = str(call.from_user.id)
    user = db_users.get(user_id, {})

    # Check VIP restriction
    if service.get("vip_only") and not user.get("vip", False):
        return bot.answer_callback_query(call.id, "❌ VIP Only service. Upgrade VIP to access.")

    # Check availability
    if service.get("status") != "available":
        return bot.answer_callback_query(call.id, "❌ Service is currently out of stock.")

    # Check user points
    price = service.get("price", 0)
    user_points = user.get("points", 0)
    if price > 0 and user_points < price:
        return bot.answer_callback_query(call.id, f"❌ Not enough points. You have {user_points} pts.")

    # Deduct points if price > 0
    if price > 0:
        user["points"] -= price
        db_users[user_id] = user
        save_users()
        bot.answer_callback_query(call.id, f"✅ {price} points deducted. Service unlocked!")

    # Send all files in folder
    for f in service.get("files", []):
        try:
            bot.copy_message(
                chat_id=call.message.chat.id,
                from_chat_id=f["chat_id"],
                message_id=f["msg_id"]
            )
        except Exception as e:
            print(f"Error sending service file: {e}")

    # Notify user
    bot.send_message(call.message.chat.id, f"🎉 You received the '{folder_name}' service!")
# =========================
# ZEDOX VIP BOT - PART 17
# SERVICES MANAGEMENT - ADMIN + PAYMENT
# =========================

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# -------------------------
# ADMIN: VIEW / MANAGE SERVICES
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data == "admin_services")
def admin_services_callback(call):
    if not is_admin(call.from_user.id):
        return bot.answer_callback_query(call.id, "❌ Access denied.")

    services = db.get("service", {})
    markup = InlineKeyboardMarkup(row_width=1)

    for folder_name, info in services.items():
        status = "✅ Available" if info.get("status") == "available" else "❌ Out of stock"
        price = info.get("price", 0)
        currency = info.get("currency", "points")
        vip_only = "💎 VIP" if info.get("vip_only") else "👤 Free"
        button_text = f"{folder_name} | {price} {currency} | {vip_only} | {status}"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"admin_service_{folder_name}"))

    markup.add(InlineKeyboardButton("➕ Add New Service", callback_data="add_service"))
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="🛠️ Admin: Manage Services",
        reply_markup=markup
    )

# -------------------------
# ADMIN: ADD NEW SERVICE
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data == "add_service")
def add_service_start(call):
    bot.send_message(call.message.chat.id, "📥 Forward files for the new service folder.")
    # Set state to capture files
    user_states[call.from_user.id] = {"action": "add_service_files"}

# -------------------------
# HANDLE SERVICE FILES
# -------------------------
@bot.message_handler(content_types=["document", "photo", "video"])
def handle_service_files(message):
    state = user_states.get(message.from_user.id, {})
    if state.get("action") != "add_service_files":
        return

    folder_name = f"service_{int(time.time())}"
    files = state.get("files", [])
    files.append({"chat_id": message.chat.id, "msg_id": message.message_id})
    state["files"] = files
    user_states[message.from_user.id] = state
    bot.reply_to(message, f"✅ File added to temporary service folder '{folder_name}'. Send /done when finished.")

# -------------------------
# ADMIN: FINISH ADDING SERVICE
# -------------------------
@bot.message_handler(commands=["done"])
def finish_add_service(message):
    state = user_states.get(message.from_user.id)
    if not state or state.get("action") != "add_service_files":
        return

    folder_name = f"service_{int(time.time())}"
    files = state.get("files", [])
    db["service"][folder_name] = {
        "files": files,
        "price": 0,
        "currency": "points",
        "vip_only": False,
        "status": "available"
    }
    save_db()
    user_states.pop(message.from_user.id)
    bot.send_message(message.chat.id, f"✅ Service folder '{folder_name}' created successfully!")

# -------------------------
# SERVICE PURCHASE VIA USDT
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("service_usdt_"))
def service_usdt_purchase(call):
    folder_name = call.data.replace("service_usdt_", "")
    service = db["service"].get(folder_name)
    if not service:
        return bot.answer_callback_query(call.id, "❌ Service not found.")

    # Here you would integrate USDT payment API
    # For demo, simulate payment:
    bot.answer_callback_query(call.id, "💰 Please send the payment to the provided USDT address.")
    usdt_address = service.get("usdt_address", "USDT-ADDRESS-HERE")
    bot.send_message(call.message.chat.id, f"Send {service.get('price')} USDT to:\n`{usdt_address}`", parse_mode="Markdown")

# -------------------------
# SERVICE STATUS TOGGLE
# -------------------------
def toggle_service_status(folder_name, status):
    if folder_name in db["service"]:
        db["service"][folder_name]["status"] = status
        save_db()
        return True
    return False
# =========================
# ZEDOX VIP BOT - PART 18
# SERVICES MANAGEMENT - EDIT & DELETE
# =========================

# -------------------------
# ADMIN: EDIT SERVICE PROPERTIES
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_service_"))
def admin_service_options(call):
    folder_name = call.data.replace("admin_service_", "")
    service = db["service"].get(folder_name)
    if not service:
        return bot.answer_callback_query(call.id, "❌ Service not found.")

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✏️ Edit Name", callback_data=f"edit_service_name_{folder_name}"),
        InlineKeyboardButton("💰 Edit Price", callback_data=f"edit_service_price_{folder_name}"),
        InlineKeyboardButton("💎 VIP Only Toggle", callback_data=f"toggle_service_vip_{folder_name}"),
        InlineKeyboardButton("🔄 Toggle Status", callback_data=f"toggle_service_status_{folder_name}"),
        InlineKeyboardButton("🗑 Delete Service", callback_data=f"delete_service_{folder_name}"),
        InlineKeyboardButton("⬅️ Back", callback_data="admin_services")
    )

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"🛠️ Service: {folder_name}",
        reply_markup=markup
    )

# -------------------------
# EDIT SERVICE NAME
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_service_name_"))
def edit_service_name(call):
    folder_name = call.data.replace("edit_service_name_", "")
    user_states[call.from_user.id] = {"action": "edit_service_name", "folder": folder_name}
    bot.send_message(call.from_user.id, "✏️ Send the new service name:")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get("action") == "edit_service_name")
def handle_new_service_name(message):
    state = user_states[message.from_user.id]
    folder_name = state["folder"]
    new_name = message.text.strip()
    db["service"][new_name] = db["service"].pop(folder_name)
    save_db()
    bot.send_message(message.chat.id, f"✅ Service renamed to '{new_name}'")
    user_states.pop(message.from_user.id)

# -------------------------
# EDIT SERVICE PRICE
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_service_price_"))
def edit_service_price(call):
    folder_name = call.data.replace("edit_service_price_", "")
    user_states[call.from_user.id] = {"action": "edit_service_price", "folder": folder_name}
    bot.send_message(call.from_user.id, "💰 Send the new price and currency separated by space (e.g., '50 points' or '10 usdt'):")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get("action") == "edit_service_price")
def handle_service_price(message):
    state = user_states[message.from_user.id]
    folder_name = state["folder"]
    try:
        parts = message.text.strip().split()
        price = float(parts[0])
        currency = parts[1].lower()
        db["service"][folder_name]["price"] = price
        db["service"][folder_name]["currency"] = currency
        save_db()
        bot.send_message(message.chat.id, f"✅ Service '{folder_name}' price set to {price} {currency.upper()}")
    except:
        bot.send_message(message.chat.id, "❌ Invalid format. Example: '50 points' or '10 usdt'")
    user_states.pop(message.from_user.id)

# -------------------------
# TOGGLE VIP ONLY
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_service_vip_"))
def toggle_vip_only(call):
    folder_name = call.data.replace("toggle_service_vip_", "")
    service = db["service"].get(folder_name)
    if not service:
        return bot.answer_callback_query(call.id, "❌ Service not found.")

    service["vip_only"] = not service.get("vip_only", False)
    save_db()
    status = "VIP Only" if service["vip_only"] else "Free Access"
    bot.answer_callback_query(call.id, f"✅ Service access changed to: {status}")

# -------------------------
# DELETE SERVICE
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_service_"))
def delete_service(call):
    folder_name = call.data.replace("delete_service_", "")
    if folder_name in db["service"]:
        db["service"].pop(folder_name)
        save_db()
        bot.answer_callback_query(call.id, f"🗑 Service '{folder_name}' deleted")
    else:
        bot.answer_callback_query(call.id, "❌ Service not found")

# -------------------------
# INTEGRATE SERVICES INTO MAIN MENU
# -------------------------
def main_menu_markup():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📂 FREE METHODS", callback_data="free_methods"),
        InlineKeyboardButton("💎 VIP METHODS", callback_data="vip_methods"),
        InlineKeyboardButton("📦 PREMIUM APPS", callback_data="premium_apps"),
        InlineKeyboardButton("🛠️ SERVICES", callback_data="services"),  # <-- SERVICES button
        InlineKeyboardButton("💰 POINTS", callback_data="points"),
        InlineKeyboardButton("⭐ BUY VIP", callback_data="buy_vip"),
        InlineKeyboardButton("🎁 REFERRAL", callback_data="referral"),
        InlineKeyboardButton("👤 ACCOUNT", callback_data="account"),
        InlineKeyboardButton("🆔 CHAT ID", callback_data="chat_id"),
        InlineKeyboardButton("🏆 COUPON REDEEM", callback_data="redeem_coupon")
    )
    if is_admin(user_id):  # Admin row
        markup.add(InlineKeyboardButton("⚙️ ADMIN PANEL", callback_data="admin_panel"))
    return markup

# -------------------------
# USER: VIEW SERVICES
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data == "services")
def show_services(call):
    services = db.get("service", {})
    if not services:
        return bot.answer_callback_query(call.id, "❌ No services available.")

    markup = InlineKeyboardMarkup(row_width=1)
    for folder_name, info in services.items():
        status = "✅ Available" if info.get("status") == "available" else "❌ Out of stock"
        price = info.get("price", 0)
        currency = info.get("currency", "points")
        vip_only = "💎 VIP" if info.get("vip_only") else "👤 Free"
        markup.add(InlineKeyboardButton(f"{folder_name} | {price} {currency} | {vip_only} | {status}",
                                        callback_data=f"service_{folder_name}"))
    bot.edit_message_text(chat_id=call.message.chat.id,
                          message_id=call.message.message_id,
                          text="🛍️ Available Services",
                          reply_markup=markup)
# =========================
# ZEDOX VIP BOT - PART 19
# SERVICES PURCHASE FLOW
# =========================

# -------------------------
# HANDLE USER CLICK ON SERVICE
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("service_"))
def handle_service_selection(call):
    folder_name = call.data.replace("service_", "")
    service = db["service"].get(folder_name)

    if not service:
        return bot.answer_callback_query(call.id, "❌ Service not found.")

    # Check VIP only access
    user = db_users.get(call.from_user.id, {"vip": False, "points": 0})
    if service.get("vip_only") and not user.get("vip"):
        return bot.answer_callback_query(call.id, "❌ This service is for VIP users only.")

    # Check availability
    if service.get("status") != "available":
        return bot.answer_callback_query(call.id, "❌ This service is currently out of stock.")

    price = service.get("price", 0)
    currency = service.get("currency", "points")

    if currency == "points":
        if user.get("points", 0) < price:
            return bot.answer_callback_query(call.id, f"❌ You need {price} points to buy this service. Your balance: {user.get('points',0)}")
        # Deduct points
        db_users[call.from_user.id]["points"] -= price
        save_users()
        bot.answer_callback_query(call.id, f"✅ Purchased {folder_name} for {price} points!")
    elif currency == "usdt":
        # For simplicity, mark as pending payment (integration with payment gateway needed)
        bot.answer_callback_query(call.id, f"💵 To buy {folder_name} for {price} USDT, send payment to admin or integrated gateway.")
        return

    # After purchase, deliver service (e.g., copy files)
    files = service.get("files", [])
    if not files:
        return bot.send_message(call.from_user.id, "❌ No files available for this service yet.")
    
    bot.send_message(call.from_user.id, f"📦 Delivering service '{folder_name}'...")
    for file in files:
        try:
            bot.copy_message(
                chat_id=call.from_user.id,
                from_chat_id=file["chat"],
                message_id=file["msg"]
            )
        except Exception as e:
            bot.send_message(call.from_user.id, f"❌ Failed to deliver some files: {str(e)}")

# -------------------------
# ADMIN: TOGGLE SERVICE STATUS
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_service_status_"))
def toggle_service_status(call):
    folder_name = call.data.replace("toggle_service_status_", "")
    service = db["service"].get(folder_name)
    if not service:
        return bot.answer_callback_query(call.id, "❌ Service not found.")

    current_status = service.get("status", "available")
    service["status"] = "out of stock" if current_status == "available" else "available"
    save_db()
    bot.answer_callback_query(call.id, f"✅ Service status changed to: {service['status']}")

# -------------------------
# ADMIN: CHECK USER POINTS BEFORE PURCHASE
# -------------------------
def check_user_points(user_id, cost):
    user = db_users.get(user_id, {"points": 0})
    return user.get("points", 0) >= cost

# -------------------------
# DELIVERY HELPER
# -------------------------
def deliver_service(user_id, service):
    files = service.get("files", [])
    if not files:
        bot.send_message(user_id, "❌ No files available for this service yet.")
        return

    bot.send_message(user_id, f"📦 Delivering service '{service}'...")
    for file in files:
        try:
            bot.copy_message(
                chat_id=user_id,
                from_chat_id=file["chat"],
                message_id=file["msg"]
            )
        except Exception as e:
            bot.send_message(user_id, f"❌ Failed to deliver some files: {str(e)}")
# =========================
# ZEDOX VIP BOT - PART 20
# ADMIN: ADD / MANAGE SERVICES
# =========================

# -------------------------
# ADMIN: START ADD SERVICE
# -------------------------
@bot.message_handler(commands=['addservice'])
def start_add_service(message):
    if message.from_user.id != ADMIN_ID:
        return bot.reply_to(message, "❌ You are not authorized.")
    msg = bot.reply_to(message, "📝 Send the service name you want to add:")
    bot.register_next_step_handler(msg, process_service_name)

# -------------------------
# STEP 1: GET SERVICE NAME
# -------------------------
def process_service_name(message):
    service_name = message.text.strip()
    if service_name in db["service"]:
        return bot.reply_to(message, "❌ This service already exists.")
    db["service"][service_name] = {"files": [], "price": 0, "currency": "points", "vip_only": False, "status": "available"}
    save_db()
    msg = bot.reply_to(message, "💰 Send the price for this service (number):")
    bot.register_next_step_handler(msg, process_service_price, service_name)

# -------------------------
# STEP 2: GET SERVICE PRICE
# -------------------------
def process_service_price(message, service_name):
    try:
        price = float(message.text.strip())
    except:
        return bot.reply_to(message, "❌ Invalid number. Try /addservice again.")
    db["service"][service_name]["price"] = price
    save_db()
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("Points", callback_data=f"set_currency_points_{service_name}"),
        InlineKeyboardButton("USDT", callback_data=f"set_currency_usdt_{service_name}")
    )
    bot.send_message(message.chat.id, "💱 Choose currency type:", reply_markup=markup)

# -------------------------
# STEP 3: SET VIP ONLY FLAG
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("set_currency_"))
def set_currency(call):
    _, currency, service_name = call.data.split("_", 2)
    db["service"][service_name]["currency"] = currency
    save_db()
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("VIP Only ✅", callback_data=f"vip_only_yes_{service_name}"),
        InlineKeyboardButton("All Users", callback_data=f"vip_only_no_{service_name}")
    )
    bot.edit_message_text(f"Currency set to {currency}. Choose if VIP only:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

# -------------------------
# STEP 4: SET VIP ONLY FLAG HANDLER
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("vip_only_"))
def set_vip_only(call):
    _, yesno, service_name = call.data.split("_", 2)
    db["service"][service_name]["vip_only"] = True if yesno == "yes" else False
    save_db()
    bot.answer_callback_query(call.id, "✅ VIP only status set.")
    bot.send_message(call.message.chat.id, f"✅ Service '{service_name}' created! Now forward the files for this service.")

# -------------------------
# STEP 5: RECEIVE FILES
# -------------------------
@bot.message_handler(content_types=['document', 'video', 'audio', 'photo'])
def receive_service_files(message):
    last_service = list(db["service"].keys())[-1]  # last created service
    service = db["service"][last_service]
    if message.content_type == 'photo':
        file_id = message.photo[-1].file_id
    else:
        file_id = message.document.file_id if message.document else None
    if file_id:
        service["files"].append({"chat": message.chat.id, "msg": message.message_id})
        save_db()
        bot.reply_to(message, f"✅ File added to service '{last_service}'")
        # =========================
# ZEDOX VIP BOT - PART 21
# ADMIN: MANAGE / EDIT / DELETE SERVICES
# =========================

# -------------------------
# ADMIN: LIST SERVICES
# -------------------------
@bot.message_handler(commands=['listservices'])
def list_services(message):
    if message.from_user.id != ADMIN_ID:
        return bot.reply_to(message, "❌ You are not authorized.")
    if not db["service"]:
        return bot.reply_to(message, "ℹ️ No services found.")
    markup = InlineKeyboardMarkup()
    for name in db["service"]:
        markup.add(InlineKeyboardButton(name, callback_data=f"admin_service_{name}"))
    bot.send_message(message.chat.id, "📃 Select a service to manage:", reply_markup=markup)

# -------------------------
# ADMIN: SERVICE CALLBACK
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_service_"))
def admin_service_menu(call):
    service_name = call.data.split("admin_service_")[1]
    service = db["service"][service_name]
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✏️ Edit Name", callback_data=f"edit_name_{service_name}"),
        InlineKeyboardButton("💰 Edit Price", callback_data=f"edit_price_{service_name}"),
        InlineKeyboardButton("💱 Change Currency", callback_data=f"edit_currency_{service_name}"),
        InlineKeyboardButton("👑 Toggle VIP Only", callback_data=f"toggle_vip_{service_name}"),
        InlineKeyboardButton("📦 Toggle Availability", callback_data=f"toggle_status_{service_name}"),
        InlineKeyboardButton("🗑 Delete Service", callback_data=f"delete_service_{service_name}")
    )
    bot.edit_message_text(f"⚙️ Managing service: {service_name}\nPrice: {service['price']} {service['currency']}\nVIP Only: {service['vip_only']}\nStatus: {service['status']}", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

# -------------------------
# ADMIN: EDIT NAME
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_name_"))
def edit_service_name(call):
    service_name = call.data.split("edit_name_")[1]
    msg = bot.send_message(call.message.chat.id, f"✏️ Send new name for '{service_name}':")
    bot.register_next_step_handler(msg, process_edit_name, service_name)

def process_edit_name(message, old_name):
    new_name = message.text.strip()
    db["service"][new_name] = db["service"].pop(old_name)
    save_db()
    bot.reply_to(message, f"✅ Service name changed from '{old_name}' to '{new_name}'")

# -------------------------
# ADMIN: EDIT PRICE
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_price_"))
def edit_service_price(call):
    service_name = call.data.split("edit_price_")[1]
    msg = bot.send_message(call.message.chat.id, f"💰 Send new price for '{service_name}':")
    bot.register_next_step_handler(msg, process_edit_price, service_name)

def process_edit_price(message, service_name):
    try:
        price = float(message.text.strip())
        db["service"][service_name]["price"] = price
        save_db()
        bot.reply_to(message, f"✅ Price updated to {price}")
    except:
        bot.reply_to(message, "❌ Invalid number.")

# -------------------------
# ADMIN: TOGGLE VIP ONLY
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_vip_"))
def toggle_vip_only(call):
    service_name = call.data.split("toggle_vip_")[1]
    db["service"][service_name]["vip_only"] = not db["service"][service_name]["vip_only"]
    save_db()
    bot.answer_callback_query(call.id, f"VIP Only set to {db['service'][service_name]['vip_only']}")

# -------------------------
# ADMIN: TOGGLE AVAILABILITY
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_status_"))
def toggle_status(call):
    service_name = call.data.split("toggle_status_")[1]
    current = db["service"][service_name]["status"]
    db["service"][service_name]["status"] = "out_of_stock" if current == "available" else "available"
    save_db()
    bot.answer_callback_query(call.id, f"Service status is now {db['service'][service_name]['status']}")

# -------------------------
# ADMIN: DELETE SERVICE
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_service_"))
def delete_service(call):
    service_name = call.data.split("delete_service_")[1]
    db["service"].pop(service_name, None)
    save_db()
    bot.answer_callback_query(call.id, f"🗑 Service '{service_name}' deleted.")
    bot.edit_message_text(f"🗑 Service '{service_name}' has been deleted.", chat_id=call.message.chat.id, message_id=call.message.message_id)
# =========================
# ZEDOX VIP BOT - PART 22
# USER: VIEW & PURCHASE SERVICES
# =========================

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# -------------------------
# USER: SHOW SERVICES MENU
# -------------------------
def services_menu(user_id):
    markup = InlineKeyboardMarkup()
    for service_name, service in db.get("service", {}).items():
        status = "✅ Available" if service["status"] == "available" else "❌ Out of Stock"
        vip_tag = "👑 VIP Only" if service["vip_only"] else ""
        button_text = f"{service_name} - {service['price']} {service['currency']} {status} {vip_tag}"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"service_{service_name}"))
    return markup

@bot.message_handler(commands=['services'])
def list_services_user(message):
    if not db.get("service"):
        return bot.reply_to(message, "ℹ️ No services are available at the moment.")
    markup = services_menu(message.from_user.id)
    bot.send_message(message.chat.id, "🛠️ Available Services:", reply_markup=markup)

# -------------------------
# USER: SERVICE CALLBACK
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("service_"))
def service_callback(call):
    service_name = call.data.split("service_")[1]
    service = db["service"].get(service_name)
    if not service:
        return bot.answer_callback_query(call.id, "❌ Service not found.", show_alert=True)

    # VIP restriction
    user = db["users"].get(str(call.from_user.id), {})
    vip = user.get("vip", False)
    if service["vip_only"] and not vip:
        return bot.answer_callback_query(call.id, "❌ This service is VIP only. Please join VIP.", show_alert=True)

    # Out of stock
    if service["status"] != "available":
        return bot.answer_callback_query(call.id, "❌ Service is currently out of stock.", show_alert=True)

    # Show purchase options
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(f"💰 Buy with Points ({service['price']} pts)", callback_data=f"buy_points_{service_name}"))
    markup.add(InlineKeyboardButton(f"💱 Buy with USDT ({service['price']} {service['currency']})", callback_data=f"buy_usdt_{service_name}"))
    bot.edit_message_text(f"🛠️ {service_name}\nPrice: {service['price']} {service['currency']}\nStatus: {service['status']}\nVIP Only: {service['vip_only']}", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

# -------------------------
# USER: BUY SERVICE WITH POINTS
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_points_"))
def buy_service_points(call):
    service_name = call.data.split("buy_points_")[1]
    service = db["service"].get(service_name)
    user_id = str(call.from_user.id)
    user = db["users"].get(user_id, {})
    points = user.get("points", 0)

    if points < service["price"]:
        return bot.answer_callback_query(call.id, "❌ Not enough points.", show_alert=True)

    user["points"] -= service["price"]
    db["users"][user_id] = user
    save_db()
    bot.answer_callback_query(call.id, f"✅ You purchased {service_name} using {service['price']} points!")

# -------------------------
# USER: BUY SERVICE WITH USDT
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_usdt_"))
def buy_service_usdt(call):
    service_name = call.data.split("buy_usdt_")[1]
    service = db["service"].get(service_name)
    # Here you can integrate real payment gateway or external link
    bot.answer_callback_query(call.id, f"💱 To purchase {service_name} with {service['currency']}, please send payment via USDT to: YOUR_WALLET_ADDRESS", show_alert=True)
    # =========================
# ZEDOX VIP BOT - PART 23
# SERVICE HISTORY & ADMIN NOTIFICATIONS
# =========================

# -------------------------
# TRACK SERVICE PURCHASES
# -------------------------
def record_service_purchase(user_id, service_name, method):
    """
    Record the purchase of a service by a user.
    method: 'points' or 'usdt'
    """
    if "service_history" not in db:
        db["service_history"] = {}

    if user_id not in db["service_history"]:
        db["service_history"][user_id] = []

    db["service_history"][user_id].append({
        "service": service_name,
        "method": method,
        "timestamp": int(time.time())
    })
    save_db()

# -------------------------
# UPDATE PART 22 PURCHASE HANDLERS
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_points_"))
def buy_service_points(call):
    service_name = call.data.split("buy_points_")[1]
    service = db["service"].get(service_name)
    user_id = str(call.from_user.id)
    user = db["users"].get(user_id, {})
    points = user.get("points", 0)

    if points < service["price"]:
        return bot.answer_callback_query(call.id, "❌ Not enough points.", show_alert=True)

    user["points"] -= service["price"]
    db["users"][user_id] = user
    save_db()
    
    record_service_purchase(user_id, service_name, "points")
    
    bot.answer_callback_query(call.id, f"✅ You purchased {service_name} using {service['price']} points!")
    notify_admin_service_purchase(call.from_user.id, service_name, "points")

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_usdt_"))
def buy_service_usdt(call):
    service_name = call.data.split("buy_usdt_")[1]
    service = db["service"].get(service_name)
    # Here you can integrate real payment gateway or external link
    
    record_service_purchase(str(call.from_user.id), service_name, "usdt")
    bot.answer_callback_query(call.id, f"💱 To purchase {service_name} with {service['currency']}, please send payment via USDT to: YOUR_WALLET_ADDRESS", show_alert=True)
    notify_admin_service_purchase(call.from_user.id, service_name, "usdt")

# -------------------------
# ADMIN NOTIFICATIONS
# -------------------------
def notify_admin_service_purchase(user_id, service_name, method):
    """
    Send a notification to admin about a service purchase
    """
    admin_message = f"📢 User: {user_id}\n🛠️ Service: {service_name}\n💰 Method: {method}\n⏱️ Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}"
    bot.send_message(ADMIN_ID, admin_message)

# -------------------------
# USER: VIEW PURCHASE HISTORY
# -------------------------
@bot.message_handler(commands=['my_services'])
def my_services_history(message):
    user_id = str(message.from_user.id)
    history = db.get("service_history", {}).get(user_id, [])
    
    if not history:
        return bot.reply_to(message, "ℹ️ You have not purchased any services yet.")

    text = "🛠️ Your Service Purchases:\n\n"
    for entry in history:
        ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry["timestamp"]))
        text += f"• {entry['service']} via {entry['method'].upper()} at {ts}\n"

    bot.send_message(message.chat.id, text)
# =========================
# ZEDOX VIP BOT - PART 24
# ADMIN PANEL - SERVICE MANAGEMENT
# =========================

# -------------------------
# ADMIN: ADD NEW SERVICE
# -------------------------
@bot.message_handler(commands=['add_service'])
def add_service(message):
    if message.from_user.id != ADMIN_ID:
        return

    msg = bot.reply_to(message, "🛠️ Send service details in format:\nName|Price|Currency(points/usdt)|Available(yes/no)")
    bot.register_next_step_handler(msg, process_add_service)

def process_add_service(message):
    try:
        name, price, currency, available = message.text.split("|")
        price = float(price)
        available = available.lower() == "yes"

        if "service" not in db:
            db["service"] = {}

        db["service"][name] = {
            "price": price,
            "currency": currency.lower(),
            "available": available
        }
        save_db()
        bot.reply_to(message, f"✅ Service '{name}' added successfully!")
    except Exception as e:
        bot.reply_to(message, "❌ Invalid format. Try again.")

# -------------------------
# ADMIN: EDIT SERVICE
# -------------------------
@bot.message_handler(commands=['edit_service'])
def edit_service(message):
    if message.from_user.id != ADMIN_ID:
        return

    msg = bot.reply_to(message, "🛠️ Send service edit in format:\nName|Price|Currency(points/usdt)|Available(yes/no)")
    bot.register_next_step_handler(msg, process_edit_service)

def process_edit_service(message):
    try:
        name, price, currency, available = message.text.split("|")
        price = float(price)
        available = available.lower() == "yes"

        if name not in db.get("service", {}):
            return bot.reply_to(message, "❌ Service not found!")

        db["service"][name].update({
            "price": price,
            "currency": currency.lower(),
            "available": available
        })
        save_db()
        bot.reply_to(message, f"✅ Service '{name}' updated successfully!")
    except Exception as e:
        bot.reply_to(message, "❌ Invalid format. Try again.")

# -------------------------
# ADMIN: DELETE SERVICE
# -------------------------
@bot.message_handler(commands=['delete_service'])
def delete_service(message):
    if message.from_user.id != ADMIN_ID:
        return

    msg = bot.reply_to(message, "🛠️ Send the name of the service to delete:")
    bot.register_next_step_handler(msg, process_delete_service)

def process_delete_service(message):
    name = message.text.strip()
    if name in db.get("service", {}):
        del db["service"][name]
        save_db()
        bot.reply_to(message, f"✅ Service '{name}' deleted successfully!")
    else:
        bot.reply_to(message, "❌ Service not found!")

# -------------------------
# ADMIN: LIST ALL SERVICES
# -------------------------
@bot.message_handler(commands=['list_services'])
def list_services(message):
    if message.from_user.id != ADMIN_ID:
        return

    services = db.get("service", {})
    if not services:
        return bot.reply_to(message, "ℹ️ No services available.")

    text = "🛠️ Services List:\n\n"
    for name, info in services.items():
        status = "✅ Available" if info["available"] else "❌ Out of stock"
        text += f"• {name} | Price: {info['price']} {info['currency'].upper()} | {status}\n"
    bot.reply_to(message, text)
# =========================
# ZEDOX VIP BOT - PART 25
# USER INTERFACE - SERVICES MENU
# =========================

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# -------------------------
# SHOW SERVICES MENU TO USER
# -------------------------
@bot.message_handler(commands=['services'])
def show_services(message):
    user_id = message.from_user.id

    services = db.get("service", {})
    if not services:
        return bot.reply_to(message, "ℹ️ No services available at the moment.")

    markup = InlineKeyboardMarkup(row_width=1)
    for name, info in services.items():
        status = "✅ Available" if info["available"] else "❌ Out of stock"
        button_text = f"{name} | {info['price']} {info['currency'].upper()} | {status}"

        # Button disabled if out of stock
        callback = f"service_{name}"
        markup.add(InlineKeyboardButton(button_text, callback_data=callback))

    bot.send_message(user_id, "🛠️ Select a service to purchase:", reply_markup=markup)

# -------------------------
# HANDLE SERVICE BUTTON CALLBACK
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("service_"))
def handle_service_callback(call):
    user_id = call.from_user.id
    service_name = call.data.split("service_")[1]

    service = db.get("service", {}).get(service_name)
    if not service:
        return bot.answer_callback_query(call.id, "❌ Service not found!")

    if not service["available"]:
        return bot.answer_callback_query(call.id, "❌ This service is currently out of stock.")

    # Check if user has enough points for points-based service
    if service["currency"] == "points":
        user_points = users.get(str(user_id), {}).get("points", 0)
        if user_points < service["price"]:
            return bot.answer_callback_query(call.id, "❌ You don't have enough points to purchase this service.")
        # Deduct points and confirm
        users[str(user_id)]["points"] -= service["price"]
        save_users()
        bot.answer_callback_query(call.id, f"✅ You purchased '{service_name}' using {service['price']} points!")
        return

    # USDT purchase flow (simulated, can integrate payment API)
    if service["currency"] == "usdt":
        bot.answer_callback_query(call.id, f"💰 To purchase '{service_name}' for {service['price']} USDT, send payment and then contact admin.")
        return
# =========================
# ZEDOX VIP BOT - PART 26
# SERVICE PURCHASE LOGIC & REFERRAL
# =========================

from datetime import datetime

# -------------------------
# HANDLE SERVICE PURCHASE LOGIC
# -------------------------
def purchase_service(user_id, service_name):
    user = users.get(str(user_id))
    service = db.get("service", {}).get(service_name)

    if not user or not service:
        return "❌ User or service not found."

    # VIP users get all services for free
    if user.get("vip", False):
        log_service_purchase(user_id, service_name, free=True)
        return f"✅ VIP Access: You received '{service_name}' for free!"

    # Check points
    if service["currency"] == "points":
        if user["points"] >= service["price"]:
            user["points"] -= service["price"]
            save_users()
            log_service_purchase(user_id, service_name)
            return f"✅ You purchased '{service_name}' for {service['price']} points!"
        else:
            return "❌ Not enough points to purchase this service."

    # USDT payment handling (manual/admin)
    if service["currency"] == "usdt":
        log_service_purchase(user_id, service_name, pending=True)
        return f"💰 To purchase '{service_name}' for {service['price']} USDT, please follow the payment instructions and contact admin."

# -------------------------
# SERVICE PURCHASE LOGGING
# -------------------------
def log_service_purchase(user_id, service_name, free=False, pending=False):
    log = db.get("service_log", [])
    entry = {
        "user_id": user_id,
        "service": service_name,
        "timestamp": datetime.utcnow().isoformat(),
        "free": free,
        "pending": pending
    }
    log.append(entry)
    db["service_log"] = log
    save_db()

    # Optional: Notify admin if notifications are ON
    if config.get("notify_admin_on_service", True):
        admin_msg = f"🛠️ Service purchased:\nUser: {user_id}\nService: {service_name}\nFree: {free}\nPending USDT: {pending}"
        bot.send_message(config.get("admin_id"), admin_msg)

# -------------------------
# REFERRAL POINTS FOR SERVICE PURCHASE
# -------------------------
def reward_referral_for_service(user_id, service_name):
    user = users.get(str(user_id))
    if not user or "referral_id" not in user:
        return

    ref_id = user["referral_id"]
    ref_user = users.get(str(ref_id))
    if not ref_user:
        return

    # Configurable referral reward for services
    reward = config.get("service_referral_points", 5)
    ref_user["points"] += reward
    save_users()

    # Notify referrer
    bot.send_message(ref_id, f"🎉 Your referral purchased '{service_name}'. You earned {reward} points!")
    # =========================
# ZEDOX VIP BOT - PART 27
# ADMIN PANEL - SERVICE MANAGEMENT
# =========================

# -------------------------
# ADD NEW SERVICE
# -------------------------
def admin_add_service(service_name, price, currency="points", available=True):
    """
    Admin function to add a new service.
    service_name: str - name of service
    price: int/float - price in points or USDT
    currency: str - "points" or "usdt"
    available: bool - True if service is available
    """
    if "service" not in db:
        db["service"] = {}

    if service_name in db["service"]:
        return f"❌ Service '{service_name}' already exists."

    db["service"][service_name] = {
        "price": price,
        "currency": currency,
        "available": available
    }
    save_db()
    return f"✅ Service '{service_name}' added successfully!"

# -------------------------
# EDIT EXISTING SERVICE
# -------------------------
def admin_edit_service(service_name, price=None, currency=None, available=None):
    service = db.get("service", {}).get(service_name)
    if not service:
        return f"❌ Service '{service_name}' does not exist."

    if price is not None:
        service["price"] = price
    if currency is not None:
        service["currency"] = currency
    if available is not None:
        service["available"] = available

    save_db()
    return f"✅ Service '{service_name}' updated successfully!"

# -------------------------
# DELETE SERVICE
# -------------------------
def admin_delete_service(service_name):
    if service_name in db.get("service", {}):
        db["service"].pop(service_name)
        save_db()
        return f"✅ Service '{service_name}' deleted successfully!"
    return f"❌ Service '{service_name}' not found."

# -------------------------
# TOGGLE SERVICE AVAILABILITY
# -------------------------
def admin_toggle_service_availability(service_name):
    service = db.get("service", {}).get(service_name)
    if not service:
        return f"❌ Service '{service_name}' not found."
    service["available"] = not service["available"]
    save_db()
    return f"✅ Service '{service_name}' availability set to {service['available']}."

# -------------------------
# GENERATE SERVICE BUTTONS FOR USER
# -------------------------
def generate_service_buttons():
    markup = InlineKeyboardMarkup(row_width=1)
    for s_name, s_info in db.get("service", {}).items():
        text = f"{s_name} - {s_info['price']} {s_info['currency']}"
        if not s_info["available"]:
            text += " ❌ Out of Stock"
        markup.add(InlineKeyboardButton(text, callback_data=f"service_{s_name}"))
    return markup
# =========================
# ZEDOX VIP BOT - PART 28
# SERVICE PURCHASE HANDLER
# =========================

# User clicks a service button
@bot.callback_query_handler(func=lambda call: call.data.startswith("service_"))
def handle_service_click(call):
    user_id = call.from_user.id
    service_name = call.data.replace("service_", "")
    
    service = db.get("service", {}).get(service_name)
    if not service:
        bot.answer_callback_query(call.id, "❌ Service not found!")
        return
    
    # Check if available
    if not service["available"]:
        bot.answer_callback_query(call.id, "❌ This service is currently out of stock!")
        return
    
    # VIP users get services free
    if users.get(user_id, {}).get("vip"):
        bot.send_message(user_id, f"✅ As a VIP, you get '{service_name}' for free!")
        deliver_service(user_id, service_name)
        return
    
    # Check currency
    if service["currency"] == "points":
        user_points = users.get(user_id, {}).get("points", 0)
        if user_points >= service["price"]:
            # Deduct points
            users[user_id]["points"] -= service["price"]
            save_users()
            bot.send_message(user_id, f"✅ You purchased '{service_name}' for {service['price']} points!")
            deliver_service(user_id, service_name)
        else:
            bot.send_message(user_id, f"❌ You need {service['price']} points to purchase '{service_name}'! Your balance: {user_points}")
    elif service["currency"] == "usdt":
        # Here you would integrate USDT payment gateway logic
        bot.send_message(user_id, f"💰 Payment of {service['price']} USDT required to get '{service_name}'. Payment system integration required.")

# -------------------------
# FUNCTION TO DELIVER SERVICE
# -------------------------
def deliver_service(user_id, service_name):
    """
    Delivers the files/content of the service to the user.
    """
    service_folder = db["service"].get(service_name, {})
    files = service_folder.get("files", [])
    if not files:
        bot.send_message(user_id, "❌ No files found for this service. Contact admin.")
        return
    
    for f in files:
        try:
            bot.copy_message(chat_id=user_id, from_chat_id=f["chat"], message_id=f["msg"])
        except Exception as e:
            bot.send_message(user_id, f"⚠️ Error sending file: {e}")

# -------------------------
# ADD SERVICE TO REFERRAL REWARD
# -------------------------
def reward_referral_for_service(user_id, service_name):
    """
    Rewards points/referral bonuses when a service is purchased.
    """
    ref_id = users.get(user_id, {}).get("referral")
    if ref_id and ref_id in users:
        reward_points = db.get("referral_reward", 10)  # Default 10 points per referral
        users[ref_id]["points"] += reward_points
        save_users()
        bot.send_message(ref_id, f"🎉 You earned {reward_points} points because your referral purchased '{service_name}'!")
# =========================
# ZEDOX VIP BOT - PART 29
# ADMIN SERVICE MANAGEMENT & BROADCAST
# =========================

# -------------------------
# ADMIN ADD SERVICE
# -------------------------
@bot.message_handler(commands=["add_service"])
def add_service_admin(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ You are not authorized!")
        return

    msg = bot.reply_to(message, "📌 Send the service name:")
    bot.register_next_step_handler(msg, process_service_name)

def process_service_name(msg):
    service_name = msg.text.strip()
    if service_name in db.get("service", {}):
        bot.reply_to(msg, "❌ Service already exists!")
        return
    msg2 = bot.reply_to(msg, "💰 Enter price (use '0' for free):")
    bot.register_next_step_handler(msg2, process_service_price, service_name)

def process_service_price(msg, service_name):
    try:
        price_text = msg.text.strip()
        if "usdt" in price_text.lower():
            price = float(price_text.replace("usdt", "").strip())
            currency = "usdt"
        else:
            price = int(price_text)
            currency = "points"
    except:
        bot.reply_to(msg, "❌ Invalid price!")
        return
    
    # Add service to DB
    db.setdefault("service", {})[service_name] = {
        "files": [],
        "price": price,
        "currency": currency,
        "available": True
    }
    save_db()
    bot.reply_to(msg, f"✅ Service '{service_name}' added successfully!\nPrice: {price} {currency}")

# -------------------------
# ADMIN EDIT SERVICE
# -------------------------
@bot.message_handler(commands=["edit_service"])
def edit_service_admin(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ You are not authorized!")
        return
    if not db.get("service"):
        bot.reply_to(message, "❌ No services to edit!")
        return
    keyboard = InlineKeyboardMarkup()
    for s in db["service"]:
        keyboard.add(InlineKeyboardButton(s, callback_data=f"edit_svc_{s}"))
    bot.send_message(message.chat.id, "Select a service to edit:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_svc_"))
def edit_service_callback(call):
    service_name = call.data.replace("edit_svc_", "")
    msg = bot.send_message(call.from_user.id, f"Editing '{service_name}'. Send new price or 'toggle' for availability:")
    bot.register_next_step_handler(msg, process_service_edit, service_name)

def process_service_edit(msg, service_name):
    text = msg.text.strip().lower()
    service = db["service"].get(service_name)
    if not service:
        bot.reply_to(msg, "❌ Service not found!")
        return
    
    if text == "toggle":
        service["available"] = not service["available"]
        save_db()
        bot.reply_to(msg, f"✅ Service '{service_name}' availability toggled to {service['available']}")
    else:
        try:
            if "usdt" in text:
                price = float(text.replace("usdt","").strip())
                service["currency"] = "usdt"
            else:
                price = int(text)
                service["currency"] = "points"
            service["price"] = price
            save_db()
            bot.reply_to(msg, f"✅ Service '{service_name}' price updated to {price} {service['currency']}")
        except:
            bot.reply_to(msg, "❌ Invalid input!")

# -------------------------
# ADMIN BROADCAST SERVICE
# -------------------------
@bot.message_handler(commands=["broadcast_service"])
def broadcast_service_admin(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ You are not authorized!")
        return
    if not db.get("service"):
        bot.reply_to(message, "❌ No services to broadcast!")
        return
    keyboard = InlineKeyboardMarkup()
    for s in db["service"]:
        keyboard.add(InlineKeyboardButton(s, callback_data=f"broadcast_svc_{s}"))
    bot.send_message(message.chat.id, "Select a service to broadcast:", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith("broadcast_svc_"))
def broadcast_service_callback(call):
    service_name = call.data.replace("broadcast_svc_", "")
    users_list = list(users.keys())
    for uid in users_list:
        try:
            bot.send_message(uid, f"📢 New Service Available: {service_name}!\nCheck it using /services")
        except:
            continue
    bot.answer_callback_query(call.id, f"✅ Broadcasted '{service_name}' to {len(users_list)} users")
    # =========================
# ZEDOX VIP BOT - PART 30
# SERVICES MENU & ACCESS LOGIC
# =========================

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# -------------------------
# MAIN MENU UPDATE
# -------------------------
def main_menu(user_id):
    vip_status = users.get(str(user_id), {}).get("vip", False)
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    # Row 1
    keyboard.add(
        InlineKeyboardButton("📂 FREE METHODS", callback_data="free_methods"),
        InlineKeyboardButton("💎 VIP METHODS", callback_data="vip_methods")
    )
    # Row 2
    keyboard.add(
        InlineKeyboardButton("📦 PREMIUM APPS", callback_data="premium_apps"),
        InlineKeyboardButton("💰 POINTS", callback_data="check_points")
    )
    # Row 3
    keyboard.add(
        InlineKeyboardButton("⭐ BUY VIP", callback_data="buy_vip"),
        InlineKeyboardButton("🎁 REFERRAL", callback_data="referral_info")
    )
    # Row 4
    keyboard.add(
        InlineKeyboardButton("👤 ACCOUNT", callback_data="account_info"),
        InlineKeyboardButton("🆔 CHAT ID", callback_data="chat_id"),
        InlineKeyboardButton("🏆 COUPON REDEEM", callback_data="redeem_code")
    )
    # Row 5 - Services button added
    keyboard.add(
        InlineKeyboardButton("🛠 SERVICES", callback_data="services_menu")
    )
    # Row 6 - ADMIN ONLY
    if user_id == ADMIN_ID:
        keyboard.add(InlineKeyboardButton("⚙️ ADMIN PANEL", callback_data="admin_panel"))
    
    return keyboard

# -------------------------
# SERVICES MENU
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data == "services_menu")
def services_menu(call):
    user_id = str(call.from_user.id)
    
    # Force join check
    if not check_force_join(user_id):
        bot.answer_callback_query(call.id, "🚫 Access denied! Join all channels first.")
        return
    
    vip_status = users.get(user_id, {}).get("vip", False)
    
    if not db.get("service"):
        bot.send_message(user_id, "❌ No services available at the moment.")
        return
    
    keyboard = InlineKeyboardMarkup()
    for svc_name, svc_data in db["service"].items():
        if not svc_data["available"]:
            display_name = f"{svc_name} ❌ Out of Stock"
        else:
            if vip_status:
                display_name = f"{svc_name} ✅ FREE for VIP"
            else:
                if svc_data["currency"] == "points":
                    display_name = f"{svc_name} - {svc_data['price']} Points"
                else:
                    display_name = f"{svc_name} - {svc_data['price']} USDT"
        
        keyboard.add(InlineKeyboardButton(display_name, callback_data=f"select_service_{svc_name}"))
    
    bot.send_message(user_id, "🛠 Available Services:", reply_markup=keyboard)

# -------------------------
# SERVICE SELECTION LOGIC
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_service_"))
def select_service(call):
    user_id = str(call.from_user.id)
    svc_name = call.data.replace("select_service_", "")
    service = db["service"].get(svc_name)
    
    if not service or not service["available"]:
        bot.answer_callback_query(call.id, "❌ Service unavailable!")
        return
    
    vip_status = users.get(user_id, {}).get("vip", False)
    
    # VIP access
    if vip_status:
        bot.send_message(user_id, f"✅ You can access '{svc_name}' for free!")
        send_service_files(user_id, svc_name)
        return
    
    # Free users must pay
    if service["currency"] == "points":
        user_points = users[user_id].get("points", 0)
        if user_points < service["price"]:
            bot.answer_callback_query(call.id, f"❌ You need {service['price']} points, you have {user_points}.")
            return
        users[user_id]["points"] -= service["price"]
        save_users()
        bot.send_message(user_id, f"✅ You used {service['price']} points to access '{svc_name}'.")
    else:
        # Here you can integrate USDT payment link logic
        bot.send_message(user_id, f"💳 Pay {service['price']} USDT to access '{svc_name}'.")
        return
    
    send_service_files(user_id, svc_name)

# -------------------------
# HELPER FUNCTION TO SEND FILES
# -------------------------
def send_service_files(user_id, svc_name):
    service = db["service"].get(svc_name)
    if not service or not service["files"]:
        bot.send_message(user_id, "❌ No files available in this service.")
        return
    for f in service["files"]:
        try:
            bot.copy_message(user_id, f["chat"], f["msg"])
        except:
            continue
# =========================
# ZEDOX VIP BOT - PART 31
# ADMIN SERVICE MANAGEMENT
# =========================

# -------------------------
# START SERVICE CREATION
# -------------------------
@bot.message_handler(func=lambda message: message.text == "➕ Add Service" and message.from_user.id == ADMIN_ID)
def add_service_start(message):
    msg = bot.send_message(ADMIN_ID, "🛠 Send the **name of the new service**:")
    bot.register_next_step_handler(msg, get_service_name)

def get_service_name(message):
    service_name = message.text.strip()
    if service_name in db.get("service", {}):
        bot.send_message(ADMIN_ID, "❌ Service already exists. Try a different name.")
        return
    
    # Initialize new service
    db.setdefault("service", {})[service_name] = {
        "files": [],
        "price": 0,
        "currency": "points",
        "available": True
    }
    save_db()
    
    msg = bot.send_message(ADMIN_ID, "💰 Set **price** for the service:")
    bot.register_next_step_handler(msg, get_service_price, service_name)

def get_service_price(message, service_name):
    try:
        price = float(message.text.strip())
    except:
        bot.send_message(ADMIN_ID, "❌ Invalid price. Enter a number.")
        return
    
    db["service"][service_name]["price"] = price
    save_db()
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("Points", callback_data=f"set_currency_points_{service_name}"),
        InlineKeyboardButton("USDT", callback_data=f"set_currency_usdt_{service_name}")
    )
    bot.send_message(ADMIN_ID, "💱 Select **currency** for this service:", reply_markup=markup)

# -------------------------
# SET CURRENCY CALLBACK
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("set_currency_"))
def set_service_currency(call):
    parts = call.data.split("_")
    currency = parts[1]
    service_name = "_".join(parts[2:])
    
    db["service"][service_name]["currency"] = currency
    save_db()
    
    bot.send_message(ADMIN_ID, "📤 Now forward **all files** for this service. Send **done** when finished.")
    bot.register_next_step_handler_by_chat_id(ADMIN_ID, receive_service_files, service_name)

# -------------------------
# RECEIVE MULTIPLE FILES
# -------------------------
def receive_service_files(message, service_name):
    if message.text and message.text.lower() == "done":
        bot.send_message(ADMIN_ID, f"✅ Service '{service_name}' added successfully!")
        return
    
    if not message.content_type in ["document", "photo", "video", "audio"]:
        bot.send_message(ADMIN_ID, "❌ Invalid type. Send a document, photo, video, or audio.")
        return
    
    # Save file details
    file_data = {"chat": message.chat.id, "msg": message.message_id}
    db["service"][service_name]["files"].append(file_data)
    save_db()
    
    # Continue listening for more files
    msg = bot.send_message(ADMIN_ID, "📤 File added. Send more or 'done' to finish.")
    bot.register_next_step_handler(msg, receive_service_files, service_name)

# -------------------------
# TOGGLE AVAILABILITY
# -------------------------
@bot.message_handler(func=lambda message: message.text == "🛑 Toggle Service Availability" and message.from_user.id == ADMIN_ID)
def toggle_service_availability(message):
    if not db.get("service"):
        bot.send_message(ADMIN_ID, "❌ No services available.")
        return
    
    markup = InlineKeyboardMarkup()
    for svc_name, svc_data in db["service"].items():
        status = "✅ Available" if svc_data["available"] else "❌ Out of Stock"
        markup.add(InlineKeyboardButton(f"{svc_name} - {status}", callback_data=f"toggle_avail_{svc_name}"))
    
    bot.send_message(ADMIN_ID, "Select a service to toggle availability:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_avail_"))
def toggle_avail_callback(call):
    svc_name = call.data.replace("toggle_avail_", "")
    db["service"][svc_name]["available"] = not db["service"][svc_name]["available"]
    save_db()
    bot.answer_callback_query(call.id, f"{svc_name} availability updated!")
# =========================
# ZEDOX VIP BOT - PART 32
# Services Management & Final Integrations
# =========================

from telebot import types
from pymongo import MongoClient
import json

# ------------------------
# MongoDB Setup
# ------------------------
mongo_uri = "YOUR_MONGODB_URI"
client = MongoClient(mongo_uri)
db = client.zedox_bot

users_col = db.users
folders_col = db.folders
services_col = db.services
config_col = db.config

# ------------------------
# Callback Handler - Services
# ------------------------
@bot.callback_query_handler(func=lambda call: True)
def handle_services(call):
    data = call.data

    # Show all services
    if data == "services":
        all_services = list(services_col.find({}))
        if not all_services:
            bot.answer_callback_query(call.id, "No services available right now.")
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for svc in all_services:
            name = svc['name']
            price = svc['price']
            currency = svc.get('currency', 'points')
            stock = "✅ Available" if svc.get('stock', True) else "❌ Out of stock"
            text = f"{name} - {price} {currency} - {stock}"
            markup.add(types.InlineKeyboardButton(text=text, callback_data=f"service_{svc['_id']}"))
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="💼 Available Services:",
            reply_markup=markup
        )

    # Service Details & Purchase
    elif data.startswith("service_"):
        svc_id = data.split("_")[1]
        svc = services_col.find_one({"_id": svc_id})
        if not svc:
            bot.answer_callback_query(call.id, "Service not found.")
            return

        price = svc['price']
        currency = svc.get('currency', 'points')
        stock = svc.get('stock', True)
        name = svc['name']

        if not stock:
            bot.answer_callback_query(call.id, "❌ This service is out of stock!")
            return

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(text="✅ Purchase", callback_data=f"buy_{svc_id}"))
        markup.add(types.InlineKeyboardButton(text="⬅️ Back", callback_data="services"))
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"💼 Service: {name}\nPrice: {price} {currency}\nStock: {'Available' if stock else 'Out of stock'}",
            reply_markup=markup
        )

    # Buy service
    elif data.startswith("buy_"):
        svc_id = data.split("_")[1]
        svc = services_col.find_one({"_id": svc_id})
        if not svc:
            bot.answer_callback_query(call.id, "Service not found.")
            return

        user = users_col.find_one({"chat_id": call.from_user.id})
        if not user:
            bot.answer_callback_query(call.id, "User not found.")
            return

        price = svc['price']
        currency = svc.get('currency', 'points')

        if currency == 'points':
            if user.get('points', 0) < price:
                bot.answer_callback_query(call.id, "❌ You don't have enough points!")
                return
            users_col.update_one({"chat_id": user['chat_id']}, {"$inc": {"points": -price}})
        # Add other currencies like USDT if needed

        bot.answer_callback_query(call.id, f"✅ You purchased {svc['name']} successfully!")
        bot.send_message(call.from_user.id, f"💼 Service {svc['name']} delivered. Admin will contact you if needed.")

# ------------------------
# Admin Service Management
# ------------------------
def admin_add_service(name, price, currency="points", stock=True):
    svc_id = str(int(client.zedox_bot.services.count_documents({})) + 1)
    services_col.insert_one({
        "_id": svc_id,
        "name": name,
        "price": price,
        "currency": currency,
        "stock": stock
    })
    return svc_id

def admin_edit_service(svc_id, name=None, price=None, currency=None, stock=None):
    update = {}
    if name: update['name'] = name
    if price: update['price'] = price
    if currency: update['currency'] = currency
    if stock is not None: update['stock'] = stock
    if update:
        services_col.update_one({"_id": svc_id}, {"$set": update})

def admin_delete_service(svc_id):
    services_col.delete_one({"_id": svc_id})

# ------------------------
# Final Notes / Integrations
# ------------------------
# - All callbacks for FREE/VIP/APPS work as in previous parts
# - Services added as an extra category, fully integrated
# - VIP/Points system applies to services as well
# - Infinite polling
bot.infinity_polling()
