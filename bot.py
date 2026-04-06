import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pymongo import MongoClient
import logging
from datetime import datetime
import re
import random
import string

# ========== CONFIGURATION ==========
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
MONGO_URI = os.getenv('MONGO_URI')

if not BOT_TOKEN or not ADMIN_ID or not MONGO_URI:
    raise ValueError("Missing required environment variables!")

# ========== SETUP ==========
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='Markdown')
logging.basicConfig(level=logging.INFO)

# MongoDB Connection
client = MongoClient(MONGO_URI)
db = client.zedox_bot
users_col = db.users
content_col = db.content
config_col = db.config
force_join_col = db.force_join
codes_col = db.codes
upload_sessions = {}  # Store upload sessions

# ========== INITIALIZE DEFAULTS ==========
def init_db():
    if not config_col.find_one({"_id": "config"}):
        config_col.insert_one({
            "_id": "config",
            "welcome_message": "✨ *Welcome to ZEDOX BOT!* ✨\n\nUse /menu to explore features.\n\n📌 *Commands:*\n/menu - Main Menu\n/profile - Your Profile\n/redeem - Redeem Code\n/points - Check Points",
            "vip_message": "🎉 *VIP Access Granted!* 🎉\n\nYou now have exclusive access to VIP content!",
            "referral_reward": 100,
            "notifications": True
        })
    
    if not force_join_col.find_one({"_id": "channels"}):
        force_join_col.insert_one({"_id": "channels", "channels": []})

init_db()

# ========== HELPER FUNCTIONS ==========
def get_user(user_id):
    user = users_col.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id,
            "points": 0,
            "vip": False,
            "referrals": 0,
            "referred_by": None,
            "join_date": datetime.now()
        }
        users_col.insert_one(user)
    return user

def update_user(user_id, update_data):
    users_col.update_one({"user_id": user_id}, {"$set": update_data})

def add_points(user_id, points):
    user = get_user(user_id)
    new_points = user['points'] + points
    update_user(user_id, {"points": new_points})
    return new_points

def is_admin(user_id):
    return user_id == ADMIN_ID

def check_force_join(user_id):
    channels = force_join_col.find_one({"_id": "channels"}).get("channels", [])
    not_joined = []
    
    for channel in channels:
        try:
            status = bot.get_chat_member(channel, user_id).status
            if status in ['left', 'kicked']:
                not_joined.append(channel)
        except:
            not_joined.append(channel)
    
    return not_joined

def generate_referral_link(user_id):
    return f"https://t.me/{bot.get_me().username}?start=ref_{user_id}"

# ========== USER KEYBOARDS ==========
def get_main_menu(user_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    user = get_user(user_id)
    
    buttons = [
        [InlineKeyboardButton("📚 FREE CONTENT", callback_data="category_free")],
        [InlineKeyboardButton("👑 VIP CONTENT", callback_data="category_vip")],
        [InlineKeyboardButton("📱 PREMIUM APPS", callback_data="category_apps")],
        [InlineKeyboardButton(f"⭐ {user['points']} POINTS", callback_data="points_info"),
         InlineKeyboardButton("🎁 REFERRAL", callback_data="referral_info")],
        [InlineKeyboardButton("🎫 REDEEM CODE", callback_data="redeem_menu")],
        [InlineKeyboardButton("👤 MY PROFILE", callback_data="my_profile")]
    ]
    
    if user['vip']:
        buttons.insert(3, [InlineKeyboardButton("💎 VIP ACTIVE", callback_data="vip_info")])
    
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton("⚙️ ADMIN PANEL", callback_data="admin_panel")])
    
    for row in buttons:
        keyboard.add(*row)
    
    return keyboard

def get_content_keyboard(category, page=0):
    keyboard = InlineKeyboardMarkup(row_width=1)
    folders = list(content_col.find({"category": category}))
    items_per_page = 5
    start = page * items_per_page
    end = start + items_per_page
    
    for folder in folders[start:end]:
        price_text = f" [{folder.get('price', 0)} pts]" if folder.get('price', 0) > 0 else " [FREE]"
        keyboard.add(InlineKeyboardButton(
            f"📁 {folder['folder_name']}{price_text}",
            callback_data=f"open_folder_{category}|{folder['folder_name']}"
        ))
    
    # Pagination buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ PREV", callback_data=f"page_{category}_{page-1}"))
    if end < len(folders):
        nav_buttons.append(InlineKeyboardButton("NEXT ▶️", callback_data=f"page_{category}_{page+1}"))
    
    if nav_buttons:
        keyboard.add(*nav_buttons)
    
    keyboard.add(InlineKeyboardButton("🔙 MAIN MENU", callback_data="main_menu"))
    return keyboard

# ========== ADMIN PANEL KEYBOARDS ==========
def get_admin_panel():
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        ["👑 VIP MANAGEMENT", "⭐ POINTS MANAGEMENT"],
        ["📤 UPLOAD CONTENT", "📁 MANAGE CONTENT"],
        ["🔗 FORCE JOIN", "📢 BROADCAST"],
        ["🎟️ GENERATE CODES", "📊 STATISTICS"],
        ["⚙️ SETTINGS", "📨 NOTIFICATIONS"]
    ]
    
    for row in buttons:
        keyboard.add(
            InlineKeyboardButton(row[0], callback_data=f"admin_{row[0].split()[0].lower()}"),
            InlineKeyboardButton(row[1], callback_data=f"admin_{row[1].split()[0].lower()}")
        )
    
    return keyboard

def get_upload_type_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("📝 TEXT", "text"),
        ("🖼️ PHOTO", "photo"),
        ("🎥 VIDEO", "video"),
        ("🎵 AUDIO", "audio"),
        ("📄 DOCUMENT", "document"),
        ("🎬 ANIMATION", "animation"),
        ("📍 LOCATION", "location"),
        ("🎴 STICKER", "sticker")
    ]
    
    for btn_text, btn_type in buttons:
        keyboard.add(InlineKeyboardButton(btn_text, callback_data=f"upload_type_{btn_type}"))
    
    keyboard.add(InlineKeyboardButton("❌ CANCEL", callback_data="cancel_upload"))
    return keyboard

# ========== USER COMMANDS ==========
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    args = message.text.split()
    
    # Handle referral
    if len(args) > 1 and args[1].startswith('ref_'):
        referrer_id = int(args[1].replace('ref_', ''))
        if referrer_id != user_id:
            user = get_user(user_id)
            if not user.get('referred_by'):
                update_user(user_id, {"referred_by": referrer_id})
                config = config_col.find_one({"_id": "config"})
                reward = config.get('referral_reward', 100)
                add_points(referrer_id, reward)
                users_col.update_one({"user_id": referrer_id}, {"$inc": {"referrals": 1}})
                bot.send_message(referrer_id, f"🎉 *NEW REFERRAL!*\n\nYou earned {reward} points!")
    
    # Check force join
    not_joined = check_force_join(user_id)
    if not_joined:
        keyboard = InlineKeyboardMarkup()
        for ch in not_joined:
            keyboard.add(InlineKeyboardButton(f"📢 JOIN {ch}", url=f"https://t.me/{ch[1:]}"))
        keyboard.add(InlineKeyboardButton("✅ CHECK AGAIN", callback_data="check_join"))
        bot.send_message(user_id, "⚠️ *PLEASE JOIN THESE CHANNELS FIRST:*", reply_markup=keyboard)
        return
    
    # Register user
    get_user(user_id)
    config = config_col.find_one({"_id": "config"})
    welcome_msg = config.get('welcome_message')
    
    bot.send_message(user_id, welcome_msg, reply_markup=get_main_menu(user_id))

@bot.message_handler(commands=['menu'])
def menu_command(message):
    user_id = message.from_user.id
    not_joined = check_force_join(user_id)
    if not_joined:
        start_command(message)
        return
    bot.send_message(user_id, "🔰 *MAIN MENU*", reply_markup=get_main_menu(user_id))

@bot.message_handler(commands=['profile'])
def profile_command(message):
    user = get_user(message.from_user.id)
    text = f"""👤 *USER PROFILE*

🆔 ID: `{user['user_id']}`
⭐ POINTS: {user['points']}
💎 VIP: {'✅ ACTIVE' if user['vip'] else '❌ INACTIVE'}
👥 REFERRALS: {user['referrals']}
📅 JOINED: {user['join_date'].strftime('%Y-%m-%d')}

🎁 *Referral Link:* {generate_referral_link(user['user_id'])}"""
    
    bot.send_message(message.chat.id, text, reply_markup=get_main_menu(message.from_user.id))

@bot.message_handler(commands=['points'])
def points_command(message):
    user = get_user(message.from_user.id)
    bot.send_message(message.chat.id, f"⭐ *YOUR POINTS:* {user['points']}\n\nUse /redeem to redeem codes!", 
                    reply_markup=get_main_menu(message.from_user.id))

@bot.message_handler(commands=['redeem'])
def redeem_command(message):
    msg = bot.send_message(message.chat.id, "🎫 *ENTER REDEEM CODE:*\n\nSend the code you received:")
    bot.register_next_step_handler(msg, process_redeem)

def process_redeem(message):
    code = message.text.strip().upper()
    user_id = message.from_user.id
    
    code_data = codes_col.find_one({"code": code})
    if not code_data:
        bot.send_message(user_id, "❌ *INVALID CODE!*\n\nPlease check and try again.")
        return
    
    if code_data['uses'] >= code_data['max_uses']:
        bot.send_message(user_id, "❌ *CODE EXPIRED!*\n\nThis code has reached maximum uses.")
        return
    
    points = code_data['points']
    add_points(user_id, points)
    codes_col.update_one({"code": code}, {"$inc": {"uses": 1}})
    
    bot.send_message(user_id, f"✅ *CODE REDEEMED!*\n\n🎉 You received {points} points!\n⭐ Total Points: {get_user(user_id)['points']}",
                    reply_markup=get_main_menu(user_id))

# ========== CALLBACK HANDLERS ==========
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call: CallbackQuery):
    user_id = call.from_user.id
    data = call.data
    
    # Check force join for all actions
    if data not in ["check_join", "admin_login"]:
        not_joined = check_force_join(user_id)
        if not_joined and not is_admin(user_id):
            bot.answer_callback_query(call.id, "⚠️ Please join required channels first!", show_alert=True)
            return
    
    # ========== FORCE JOIN ==========
    if data == "check_join":
        not_joined = check_force_join(user_id)
        if not_joined:
            keyboard = InlineKeyboardMarkup()
            for ch in not_joined:
                keyboard.add(InlineKeyboardButton(f"📢 JOIN {ch}", url=f"https://t.me/{ch[1:]}"))
            keyboard.add(InlineKeyboardButton("✅ CHECK AGAIN", callback_data="check_join"))
            bot.edit_message_text("⚠️ *PLEASE JOIN THESE CHANNELS:*", call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        else:
            bot.edit_message_text("✅ *ACCESS GRANTED!*", call.message.chat.id, call.message.message_id)
            bot.send_message(user_id, "🔰 *MAIN MENU*", reply_markup=get_main_menu(user_id))
        return
    
    # ========== MAIN MENU ==========
    if data == "main_menu":
        bot.edit_message_text("🔰 *MAIN MENU*", call.message.chat.id, call.message.message_id, 
                            reply_markup=get_main_menu(user_id))
        return
    
    if data == "my_profile":
        user = get_user(user_id)
        text = f"""👤 *USER PROFILE*

🆔 ID: `{user['user_id']}`
⭐ POINTS: {user['points']}
💎 VIP: {'✅ ACTIVE' if user['vip'] else '❌ INACTIVE'}
👥 REFERRALS: {user['referrals']}

🎁 *Referral Program*
Share your link and earn {config_col.find_one({'_id': 'config'})['referral_reward']} points per referral!

🔗 {generate_referral_link(user_id)}"""
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 BACK", callback_data="main_menu")))
        return
    
    if data == "points_info":
        user = get_user(user_id)
        bot.answer_callback_query(call.id, f"You have {user['points']} points! Use /redeem for codes.", show_alert=True)
        return
    
    if data == "referral_info":
        user = get_user(user_id)
        text = f"""🎁 *REFERRAL SYSTEM*

Your Referrals: {user['referrals']}
Reward per referral: {config_col.find_one({'_id': 'config'})['referral_reward']} points

🔗 *Your Link:*
{generate_referral_link(user_id)}

Share this link with friends! When they join, you both earn points!"""
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 BACK", callback_data="main_menu")))
        return
    
    if data == "redeem_menu":
        bot.edit_message_text("🎫 *REDEEM CODE*\n\nClick below to enter your code:", 
                            call.message.chat.id, call.message.message_id,
                            reply_markup=InlineKeyboardMarkup().add(
                                InlineKeyboardButton("✅ REDEEM CODE", callback_data="redeem_now"),
                                InlineKeyboardButton("🔙 BACK", callback_data="main_menu")
                            ))
        return
    
    if data == "redeem_now":
        bot.edit_message_text("🎫 *SEND YOUR REDEEM CODE:*", call.message.chat.id, call.message.message_id)
        msg = bot.send_message(user_id, "Type or paste your code here:")
        bot.register_next_step_handler(msg, process_redeem)
        return
    
    # ========== CONTENT CATEGORIES ==========
    if data.startswith("category_"):
        category = data.split("_")[1]
        keyboard = get_content_keyboard(category)
        category_names = {"free": "📚 FREE CONTENT", "vip": "👑 VIP CONTENT", "apps": "📱 PREMIUM APPS"}
        bot.edit_message_text(f"*{category_names.get(category, category.upper())}*", 
                            call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        return
    
    if data.startswith("page_"):
        _, category, page = data.split("_")
        page = int(page)
        keyboard = get_content_keyboard(category, page)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        return
    
    if data.startswith("open_folder_"):
        _, folder_data = data.split("|", 1)
        category, folder_name = folder_data.split("|", 1)
        
        folder = content_col.find_one({"category": category, "folder_name": folder_name})
        if not folder:
            bot.answer_callback_query(call.id, "❌ Folder not found!")
            return
        
        price = folder.get('price', 0)
        user = get_user(user_id)
        
        # Check access
        if category == "vip" and not user['vip']:
            bot.answer_callback_query(call.id, "👑 VIP only content! Get VIP from admin.", show_alert=True)
            return
        
        if price > 0 and not user['vip']:
            if user['points'] < price:
                bot.answer_callback_query(call.id, f"❌ Need {price} points! You have {user['points']}", show_alert=True)
                return
            add_points(user_id, -price)
            bot.answer_callback_query(call.id, f"✅ Paid {price} points!")
        
        # Send all files in folder
        for file in folder['files']:
            try:
                if file['type'] == 'text':
                    bot.send_message(call.message.chat.id, file['content'])
                elif file['type'] == 'photo':
                    bot.send_photo(call.message.chat.id, file['file_id'], caption=file.get('caption', ''))
                elif file['type'] == 'video':
                    bot.send_video(call.message.chat.id, file['file_id'], caption=file.get('caption', ''))
                elif file['type'] == 'audio':
                    bot.send_audio(call.message.chat.id, file['file_id'], caption=file.get('caption', ''))
                elif file['type'] == 'document':
                    bot.send_document(call.message.chat.id, file['file_id'], caption=file.get('caption', ''))
                elif file['type'] == 'animation':
                    bot.send_animation(call.message.chat.id, file['file_id'], caption=file.get('caption', ''))
                elif file['type'] == 'sticker':
                    bot.send_sticker(call.message.chat.id, file['file_id'])
                elif file['type'] == 'location':
                    bot.send_location(call.message.chat.id, file['latitude'], file['longitude'])
            except Exception as e:
                logging.error(f"Error sending file: {e}")
        
        bot.send_message(call.message.chat.id, f"✅ *{folder_name}* delivered successfully!")
        return
    
    # ========== ADMIN PANEL ==========
    if data == "admin_panel":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Admin access only!")
            return
        bot.edit_message_text("⚙️ *ADMIN CONTROL PANEL*\n\nSelect an option:", 
                            call.message.chat.id, call.message.message_id, reply_markup=get_admin_panel())
        return
    
    # Admin VIP Management
    if data == "admin_vip":
        if not is_admin(user_id):
            return
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("➕ ADD VIP USER", callback_data="vip_add"),
            InlineKeyboardButton("❌ REMOVE VIP", callback_data="vip_remove"),
            InlineKeyboardButton("📋 LIST VIP USERS", callback_data="vip_list"),
            InlineKeyboardButton("🔙 BACK", callback_data="admin_panel")
        )
        bot.edit_message_text("👑 *VIP MANAGEMENT*\n\nSelect action:", 
                            call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        return
    
    if data == "vip_add":
        msg = bot.send_message(user_id, "👑 *ADD VIP USER*\n\nSend the user ID to add as VIP:")
        bot.register_next_step_handler(msg, process_vip_add)
        return
    
    if data == "vip_remove":
        msg = bot.send_message(user_id, "❌ *REMOVE VIP*\n\nSend the user ID to remove VIP status:")
        bot.register_next_step_handler(msg, process_vip_remove)
        return
    
    if data == "vip_list":
        vip_users = list(users_col.find({"vip": True}).limit(20))
        if not vip_users:
            text = "📋 *VIP USERS*\n\nNo VIP users found."
        else:
            text = "📋 *VIP USERS*\n\n"
            for u in vip_users[:20]:
                text += f"🆔 `{u['user_id']}`\n"
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 BACK", callback_data="admin_vip")))
        return
    
    # Admin Points Management
    if data == "admin_points":
        if not is_admin(user_id):
            return
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("➕ ADD POINTS", callback_data="points_add"),
            InlineKeyboardButton("➖ REMOVE POINTS", callback_data="points_remove"),
            InlineKeyboardButton("🔍 CHECK POINTS", callback_data="points_check"),
            InlineKeyboardButton("🔙 BACK", callback_data="admin_panel")
        )
        bot.edit_message_text("⭐ *POINTS MANAGEMENT*\n\nSelect action:", 
                            call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        return
    
    if data == "points_add":
        msg = bot.send_message(user_id, "⭐ *ADD POINTS*\n\nSend: `user_id points`\nExample: `123456 500`")
        bot.register_next_step_handler(msg, process_points_add)
        return
    
    if data == "points_remove":
        msg = bot.send_message(user_id, "➖ *REMOVE POINTS*\n\nSend: `user_id points`\nExample: `123456 100`")
        bot.register_next_step_handler(msg, process_points_remove)
        return
    
    if data == "points_check":
        msg = bot.send_message(user_id, "🔍 *CHECK POINTS*\n\nSend user ID:")
        bot.register_next_step_handler(msg, process_points_check)
        return
    
    # Admin Upload Content
    if data == "admin_upload":
        if not is_admin(user_id):
            return
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("📚 FREE CONTENT", callback_data="upload_free"),
            InlineKeyboardButton("👑 VIP CONTENT", callback_data="upload_vip"),
            InlineKeyboardButton("📱 PREMIUM APPS", callback_data="upload_apps"),
            InlineKeyboardButton("🔙 BACK", callback_data="admin_panel")
        )
        bot.edit_message_text("📤 *UPLOAD CONTENT*\n\nSelect category:", 
                            call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        return
    
    if data in ["upload_free", "upload_vip", "upload_apps"]:
        category = data.split("_")[1]
        upload_sessions[user_id] = {"category": category, "step": "folder_name", "files": []}
        msg = bot.send_message(user_id, f"📁 *CREATE FOLDER*\n\nSend folder name for {category.upper()} content:\n\n(Type /cancel to cancel)")
        bot.register_next_step_handler(msg, process_folder_name)
        return
    
    # Admin Manage Content
    if data == "admin_manage":
        if not is_admin(user_id):
            return
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("📝 EDIT FOLDER", callback_data="manage_edit"),
            InlineKeyboardButton("🗑️ DELETE FOLDER", callback_data="manage_delete"),
            InlineKeyboardButton("💰 SET PRICE", callback_data="manage_price"),
            InlineKeyboardButton("🔙 BACK", callback_data="admin_panel")
        )
        bot.edit_message_text("📁 *MANAGE CONTENT*\n\nSelect action:", 
                            call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        return
    
    if data == "manage_delete":
        keyboard = InlineKeyboardMarkup(row_width=1)
        categories = ["free", "vip", "apps"]
        for cat in categories:
            folders = list(content_col.find({"category": cat}))
            for folder in folders:
                keyboard.add(InlineKeyboardButton(f"🗑️ [{cat.upper()}] {folder['folder_name']}", 
                                                callback_data=f"del_folder_{cat}|{folder['folder_name']}"))
        keyboard.add(InlineKeyboardButton("🔙 BACK", callback_data="admin_manage"))
        bot.edit_message_text("🗑️ *DELETE FOLDER*\n\nSelect folder to delete:", 
                            call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        return
    
    if data.startswith("del_folder_"):
        _, folder_data = data.split("_", 2)
        cat, folder_name = folder_data.split("|", 1)
        content_col.delete_one({"category": cat, "folder_name": folder_name})
        bot.answer_callback_query(call.id, "✅ Folder deleted!")
        bot.edit_message_text("✅ *FOLDER DELETED*", call.message.chat.id, call.message.message_id,
                            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 BACK", callback_data="admin_manage")))
        return
    
    # Admin Force Join
    if data == "admin_forcejoin":
        if not is_admin(user_id):
            return
        channels = force_join_col.find_one({"_id": "channels"}).get("channels", [])
        text = "🔗 *FORCE JOIN CHANNELS*\n\n"
        if channels:
            text += "\n".join([f"• {ch}" for ch in channels])
        else:
            text += "No channels set."
        
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("➕ ADD CHANNEL", callback_data="fj_add"),
            InlineKeyboardButton("❌ REMOVE CHANNEL", callback_data="fj_remove"),
            InlineKeyboardButton("🔙 BACK", callback_data="admin_panel")
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        return
    
    if data == "fj_add":
        msg = bot.send_message(user_id, "➕ *ADD CHANNEL*\n\nSend channel username (with @):\nExample: @channelname")
        bot.register_next_step_handler(msg, process_add_channel)
        return
    
    if data == "fj_remove":
        channels = force_join_col.find_one({"_id": "channels"}).get("channels", [])
        if not channels:
            bot.answer_callback_query(call.id, "No channels to remove!")
            return
        
        keyboard = InlineKeyboardMarkup(row_width=1)
        for ch in channels:
            keyboard.add(InlineKeyboardButton(f"❌ {ch}", callback_data=f"rm_channel_{ch}"))
        keyboard.add(InlineKeyboardButton("🔙 BACK", callback_data="admin_forcejoin"))
        bot.edit_message_text("❌ *REMOVE CHANNEL*\n\nSelect channel to remove:", 
                            call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        return
    
    if data.startswith("rm_channel_"):
        channel = data.replace("rm_channel_", "")
        force_join_col.update_one({"_id": "channels"}, {"$pull": {"channels": channel}})
        bot.answer_callback_query(call.id, "✅ Channel removed!")
        callback_handler(CallbackQuery(id=call.id, from_user=call.from_user, message=call.message, 
                                       chat_instance=call.chat_instance, data="admin_forcejoin"))
        return
    
    # Admin Broadcast
    if data == "admin_broadcast":
        if not is_admin(user_id):
            return
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("📢 TO ALL USERS", callback_data="broadcast_all"),
            InlineKeyboardButton("👑 TO VIP ONLY", callback_data="broadcast_vip"),
            InlineKeyboardButton("🆓 TO FREE ONLY", callback_data="broadcast_free"),
            InlineKeyboardButton("🔙 BACK", callback_data="admin_panel")
        )
        bot.edit_message_text("📢 *BROADCAST MESSAGE*\n\nSelect audience:", 
                            call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        return
    
    if data in ["broadcast_all", "broadcast_vip", "broadcast_free"]:
        broadcast_type = data.split("_")[1]
        upload_sessions[user_id] = {"broadcast_type": broadcast_type, "step": "broadcast_content"}
        msg = bot.send_message(user_id, "📢 *SEND BROADCAST CONTENT*\n\nSend the message or media to broadcast:\n\n(Type /cancel to cancel)")
        bot.register_next_step_handler(msg, process_broadcast_content)
        return
    
    # Admin Generate Codes
    if data == "admin_codes":
        if not is_admin(user_id):
            return
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("🎟️ GENERATE CODE", callback_data="gen_code"),
            InlineKeyboardButton("📋 LIST CODES", callback_data="list_codes"),
            InlineKeyboardButton("🔙 BACK", callback_data="admin_panel")
        )
        bot.edit_message_text("🎟️ *REDEEM CODE GENERATOR*\n\nSelect action:", 
                            call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        return
    
    if data == "gen_code":
        msg = bot.send_message(user_id, "🎟️ *GENERATE CODE*\n\nSend: `points max_uses`\nExample: `100 50`\n\n(100 points, can be used 50 times)")
        bot.register_next_step_handler(msg, process_generate_code)
        return
    
    if data == "list_codes":
        codes = list(codes_col.find().sort("_id", -1).limit(20))
        if not codes:
            text = "📋 *REDEEM CODES*\n\nNo codes generated yet."
        else:
            text = "📋 *RECENT CODES*\n\n"
            for code in codes[:20]:
                text += f"🎫 `{code['code']}` - {code['points']} pts - {code['uses']}/{code['max_uses']} uses\n"
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 BACK", callback_data="admin_codes")))
        return
    
    # Admin Statistics
    if data == "admin_stats":
        if not is_admin(user_id):
            return
        total_users = users_col.count_documents({})
        vip_users = users_col.count_documents({"vip": True})
        total_points = sum([u.get('points', 0) for u in users_col.find({}, {"points": 1})])
        total_referrals = sum([u.get('referrals', 0) for u in users_col.find({}, {"referrals": 1})])
        
        stats = f"""📊 *BOT STATISTICS*

👥 TOTAL USERS: {total_users}
💎 VIP USERS: {vip_users}
🆓 FREE USERS: {total_users - vip_users}
⭐ TOTAL POINTS: {total_points}
🎁 TOTAL REFERRALS: {total_referrals}

📁 *CONTENT*
📚 FREE FOLDERS: {content_col.count_documents({'category': 'free'})}
👑 VIP FOLDERS: {content_col.count_documents({'category': 'vip'})}
📱 APPS: {content_col.count_documents({'category': 'apps'})}

🎟️ ACTIVE CODES: {codes_col.count_documents({})}"""
        
        bot.edit_message_text(stats, call.message.chat.id, call.message.message_id,
                            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 BACK", callback_data="admin_panel")))
        return
    
    # Admin Settings
    if data == "admin_settings":
        if not is_admin(user_id):
            return
        config = config_col.find_one({"_id": "config"})
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("✏️ WELCOME MESSAGE", callback_data="set_welcome"),
            InlineKeyboardButton("✏️ VIP MESSAGE", callback_data="set_vipmsg"),
            InlineKeyboardButton(f"💰 REFERRAL REWARD: {config['referral_reward']}", callback_data="set_reward"),
            InlineKeyboardButton("🔙 BACK", callback_data="admin_panel")
        )
        bot.edit_message_text("⚙️ *SETTINGS*\n\nConfigure bot settings:", 
                            call.message.chat.id, call.message.message_id, reply_markup=keyboard)
        return
    
    if data == "set_welcome":
        msg = bot.send_message(user_id, "✏️ *SET WELCOME MESSAGE*\n\nSend new welcome message (supports Markdown):\n\n(Type /cancel to cancel)")
        bot.register_next_step_handler(msg, process_set_welcome)
        return
    
    if data == "set_vipmsg":
        msg = bot.send_message(user_id, "✏️ *SET VIP MESSAGE*\n\nSend new VIP welcome message (supports Markdown):")
        bot.register_next_step_handler(msg, process_set_vipmsg)
        return
    
    if data == "set_reward":
        msg = bot.send_message(user_id, "💰 *SET REFERRAL REWARD*\n\nSend new points amount per referral:\nExample: `150`")
        bot.register_next_step_handler(msg, process_set_reward)
        return
    
    if data == "admin_notifications":
        if not is_admin(user_id):
            return
        config = config_col.find_one({"_id": "config"})
        current = config.get('notifications', True)
        new_status = not current
        config_col.update_one({"_id": "config"}, {"$set": {"notifications": new_status}})
        bot.answer_callback_query(call.id, f"✅ Notifications {'ON' if new_status else 'OFF'}")
        callback_handler(CallbackQuery(id=call.id, from_user=call.from_user, message=call.message,
                                       chat_instance=call.chat_instance, data="admin_settings"))
        return

# ========== ADMIN PROCESSING FUNCTIONS ==========
def process_vip_add(message):
    try:
        user_id = int(message.text.strip())
        user = get_user(user_id)
        if user['vip']:
            bot.send_message(message.chat.id, "⚠️ User is already VIP!")
        else:
            update_user(user_id, {"vip": True})
            config = config_col.find_one({"_id": "config"})
            bot.send_message(user_id, config.get('vip_message'))
            bot.send_message(message.chat.id, f"✅ VIP granted to `{user_id}`!")
    except:
        bot.send_message(message.chat.id, "❌ Invalid user ID!")
    
    show_admin_panel(message.chat.id)

def process_vip_remove(message):
    try:
        user_id = int(message.text.strip())
        user = get_user(user_id)
        if not user['vip']:
            bot.send_message(message.chat.id, "⚠️ User is not VIP!")
        else:
            update_user(user_id, {"vip": False})
            bot.send_message(message.chat.id, f"❌ VIP removed from `{user_id}`!")
    except:
        bot.send_message(message.chat.id, "❌ Invalid user ID!")
    
    show_admin_panel(message.chat.id)

def process_points_add(message):
    try:
        parts = message.text.split()
        user_id = int(parts[0])
        points = int(parts[1])
        new_points = add_points(user_id, points)
        bot.send_message(message.chat.id, f"✅ Added {points} points to `{user_id}`\n⭐ New total: {new_points}")
        
        user = get_user(user_id)
        if user.get('notify_points', True):
            bot.send_message(user_id, f"🎉 You received {points} points!\n⭐ Total: {new_points}")
    except:
        bot.send_message(message.chat.id, "❌ Invalid format! Use: `user_id points`")
    
    show_admin_panel(message.chat.id)

def process_points_remove(message):
    try:
        parts = message.text.split()
        user_id = int(parts[0])
        points = int(parts[1])
        user = get_user(user_id)
        new_points = max(0, user['points'] - points)
        update_user(user_id, {"points": new_points})
        bot.send_message(message.chat.id, f"➖ Removed {points} points from `{user_id}`\n⭐ New total: {new_points}")
    except:
        bot.send_message(message.chat.id, "❌ Invalid format! Use: `user_id points`")
    
    show_admin_panel(message.chat.id)

def process_points_check(message):
    try:
        user_id = int(message.text.strip())
        user = get_user(user_id)
        bot.send_message(message.chat.id, f"👤 User `{user_id}`\n⭐ Points: {user['points']}\n💎 VIP: {'Yes' if user['vip'] else 'No'}")
    except:
        bot.send_message(message.chat.id, "❌ Invalid user ID!")
    
    show_admin_panel(message.chat.id)

def process_add_channel(message):
    channel = message.text.strip()
    if not channel.startswith('@'):
        channel = '@' + channel
    
    force_join_col.update_one({"_id": "channels"}, {"$addToSet": {"channels": channel}})
    bot.send_message(message.chat.id, f"✅ Channel {channel} added to force join!")
    show_admin_panel(message.chat.id)

def process_generate_code(message):
    try:
        points, max_uses = map(int, message.text.split())
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
        codes_col.insert_one({
            "code": code,
            "points": points,
            "uses": 0,
            "max_uses": max_uses,
            "created_by": message.from_user.id,
            "created_at": datetime.now()
        })
        bot.send_message(message.chat.id, f"✅ *CODE GENERATED!*\n\n🎫 `{code}`\n⭐ {points} points\n🎟️ {max_uses} uses max")
    except:
        bot.send_message(message.chat.id, "❌ Invalid format! Use: `points max_uses`\nExample: `100 50`")
    
    show_admin_panel(message.chat.id)

def process_set_welcome(message):
    if message.text == "/cancel":
        bot.send_message(message.chat.id, "❌ Cancelled!")
        show_admin_panel(message.chat.id)
        return
    
    config_col.update_one({"_id": "config"}, {"$set": {"welcome_message": message.text}})
    bot.send_message(message.chat.id, "✅ Welcome message updated!")
    show_admin_panel(message.chat.id)

def process_set_vipmsg(message):
    config_col.update_one({"_id": "config"}, {"$set": {"vip_message": message.text}})
    bot.send_message(message.chat.id, "✅ VIP message updated!")
    show_admin_panel(message.chat.id)

def process_set_reward(message):
    try:
        reward = int(message.text.strip())
        config_col.update_one({"_id": "config"}, {"$set": {"referral_reward": reward}})
        bot.send_message(message.chat.id, f"✅ Referral reward set to {reward} points!")
    except:
        bot.send_message(message.chat.id, "❌ Invalid number!")
    
    show_admin_panel(message.chat.id)

def process_broadcast_content(message):
    user_id = message.from_user.id
    session = upload_sessions.get(user_id, {})
    broadcast_type = session.get('broadcast_type')
    
    # Get target users
    if broadcast_type == 'all':
        users = list(users_col.find({}))
    elif broadcast_type == 'vip':
        users = list(users_col.find({"vip": True}))
    else:
        users = list(users_col.find({"vip": False}))
    
    success = 0
    failed = 0
    
    for user in users:
        try:
            if message.text:
                bot.send_message(user['user_id'], f"📢 *BROADCAST*\n\n{message.text}")
            elif message.photo:
                bot.send_photo(user['user_id'], message.photo[-1].file_id, caption=message.caption)
            elif message.video:
                bot.send_video(user['user_id'], message.video.file_id, caption=message.caption)
            elif message.document:
                bot.send_document(user['user_id'], message.document.file_id, caption=message.caption)
            elif message.audio:
                bot.send_audio(user['user_id'], message.audio.file_id, caption=message.caption)
            success += 1
        except:
            failed += 1
    
    bot.send_message(user_id, f"✅ *BROADCAST COMPLETE*\n\n📨 Sent: {success}\n❌ Failed: {failed}")
    show_admin_panel(user_id)
    del upload_sessions[user_id]

# ========== UPLOAD SYSTEM ==========
def process_folder_name(message):
    user_id = message.from_user.id
    if message.text == "/cancel":
        del upload_sessions[user_id]
        bot.send_message(user_id, "❌ Upload cancelled!")
        show_admin_panel(user_id)
        return
    
    upload_sessions[user_id]['folder_name'] = message.text
    upload_sessions[user_id]['step'] = 'price'
    msg = bot.send_message(user_id, f"💰 *SET PRICE*\n\nFolder: {message.text}\n\nSend price in points (0 for free):")
    bot.register_next_step_handler(msg, process_folder_price)

def process_folder_price(message):
    user_id = message.from_user.id
    if message.text == "/cancel":
        del upload_sessions[user_id]
        bot.send_message(user_id, "❌ Upload cancelled!")
        show_admin_panel(user_id)
        return
    
    try:
        price = int(message.text.strip())
        upload_sessions[user_id]['price'] = price
        upload_sessions[user_id]['step'] = 'upload'
        
        bot.send_message(user_id, f"📤 *UPLOAD FILES*\n\nFolder: {upload_sessions[user_id]['folder_name']}\nPrice: {price} points\n\nSelect content type to upload:",
                        reply_markup=get_upload_type_keyboard())
    except:
        bot.send_message(user_id, "❌ Invalid price! Send a number:")
        bot.register_next_step_handler(message, process_folder_price)

@bot.callback_query_handler(func=lambda call: call.data.startswith("upload_type_"))
def process_upload_type(call):
    user_id = call.from_user.id
    media_type = call.data.replace("upload_type_", "")
    
    if user_id not in upload_sessions:
        bot.answer_callback_query(call.id, "Session expired! Start over.")
        return
    
    upload_sessions[user_id]['current_type'] = media_type
    
    messages = {
        'text': "✏️ Send the text message:",
        'photo': "🖼️ Send the photo (with optional caption):",
        'video': "🎥 Send the video (with optional caption):",
        'audio': "🎵 Send the audio (with optional caption):",
        'document': "📄 Send the document (with optional caption):",
        'animation': "🎬 Send the GIF/animation:",
        'location': "📍 Send a location:",
        'sticker': "🎴 Send a sticker:"
    }
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("✅ DONE", callback_data="upload_done"),
                InlineKeyboardButton("❌ CANCEL", callback_data="cancel_upload"))
    
    bot.edit_message_text(f"📤 *UPLOADING {media_type.upper()}*\n\n{messages.get(media_type, 'Send the file:')}\n\nClick DONE when finished adding files.",
                         call.message.chat.id, call.message.message_id, reply_markup=keyboard)
    
    # Register next step based on type
    if media_type == 'text':
        msg = bot.send_message(user_id, "Send text content:")
        bot.register_next_step_handler(msg, save_text_content)
    elif media_type == 'location':
        msg = bot.send_message(user_id, "Send a location:")
        bot.register_next_step_handler(msg, save_location_content)
    else:
        # For media files, the next step is handled by message handlers
        pass

def save_text_content(message):
    if message.text == "/cancel":
        cancel_upload(message.from_user.id, message.chat.id)
        return
    
    user_id = message.from_user.id
    if user_id in upload_sessions:
        upload_sessions[user_id]['files'].append({
            'type': 'text',
            'content': message.text
        })
        bot.send_message(message.chat.id, f"✅ Text saved! ({len(upload_sessions[user_id]['files'])} files total)\n\nContinue uploading or click DONE.",
                        reply_markup=InlineKeyboardMarkup().add(
                            InlineKeyboardButton("✅ DONE", callback_data="upload_done"),
                            InlineKeyboardButton("➕ ADD MORE", callback_data=f"upload_type_text")
                        ))

def save_location_content(message):
    if message.location:
        user_id = message.from_user.id
        upload_sessions[user_id]['files'].append({
            'type': 'location',
            'latitude': message.location.latitude,
            'longitude': message.location.longitude
        })
        bot.send_message(message.chat.id, f"✅ Location saved! ({len(upload_sessions[user_id]['files'])} files total)\n\nContinue uploading or click DONE.",
                        reply_markup=InlineKeyboardMarkup().add(
                            InlineKeyboardButton("✅ DONE", callback_data="upload_done"),
                            InlineKeyboardButton("➕ ADD MORE", callback_data=f"upload_type_location")
                        ))
    else:
        bot.send_message(message.chat.id, "❌ Please send a valid location!")

@bot.message_handler(content_types=['photo', 'video', 'audio', 'document', 'animation', 'sticker'])
def handle_media_upload(message):
    user_id = message.from_user.id
    if user_id not in upload_sessions or upload_sessions[user_id].get('step') != 'upload':
        return
    
    media_type = upload_sessions[user_id].get('current_type')
    file_data = {'type': media_type}
    
    if message.photo:
        file_data['file_id'] = message.photo[-1].file_id
        file_data['caption'] = message.caption or ''
    elif message.video:
        file_data['file_id'] = message.video.file_id
        file_data['caption'] = message.caption or ''
    elif message.audio:
        file_data['file_id'] = message.audio.file_id
        file_data['caption'] = message.caption or ''
        file_data['title'] = message.audio.title
        file_data['performer'] = message.audio.performer
    elif message.document:
        file_data['file_id'] = message.document.file_id
        file_data['caption'] = message.caption or ''
        file_data['file_name'] = message.document.file_name
    elif message.animation:
        file_data['file_id'] = message.animation.file_id
        file_data['caption'] = message.caption or ''
    elif message.sticker:
        file_data['file_id'] = message.sticker.file_id
    
    upload_sessions[user_id]['files'].append(file_data)
    
    bot.send_message(user_id, f"✅ {media_type.upper()} saved! ({len(upload_sessions[user_id]['files'])} files total)\n\nContinue uploading or click DONE.",
                    reply_markup=InlineKeyboardMarkup().add(
                        InlineKeyboardButton("✅ DONE", callback_data="upload_done"),
                        InlineKeyboardButton("➕ ADD MORE", callback_data=f"upload_type_{media_type}")
                    ))

@bot.callback_query_handler(func=lambda call: call.data == "upload_done")
def finish_upload(call):
    user_id = call.from_user.id
    if user_id not in upload_sessions:
        bot.answer_callback_query(call.id, "No active upload session!")
        return
    
    session = upload_sessions[user_id]
    if not session['files']:
        bot.answer_callback_query(call.id, "No files uploaded! Add at least one file.")
        return
    
    # Save to database
    content_col.insert_one({
        "category": session['category'],
        "folder_name": session['folder_name'],
        "price": session['price'],
        "files": session['files'],
        "created_by": user_id,
        "created_at": datetime.now()
    })
    
    bot.edit_message_text(f"✅ *UPLOAD COMPLETE!*\n\n📁 {session['folder_name']}\n📂 Category: {session['category']}\n💰 Price: {session['price']} points\n📎 Files: {len(session['files'])}",
                         call.message.chat.id, call.message.message_id,
                         reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 ADMIN PANEL", callback_data="admin_panel")))
    
    del upload_sessions[user_id]

@bot.callback_query_handler(func=lambda call: call.data == "cancel_upload")
def cancel_upload_callback(call):
    cancel_upload(call.from_user.id, call.message.chat.id)

def cancel_upload(user_id, chat_id):
    if user_id in upload_sessions:
        del upload_sessions[user_id]
    bot.send_message(chat_id, "❌ Upload cancelled!")
    show_admin_panel(chat_id)

def show_admin_panel(chat_id):
    bot.send_message(chat_id, "⚙️ *ADMIN CONTROL PANEL*", reply_markup=get_admin_panel())

# ========== ERROR HANDLING ==========
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Unknown command. Use /menu")
    else:
        # For admin, just ignore unknown messages
        pass

# ========== MAIN ==========
if __name__ == "__main__":
    print("🤖 ZEDOX BOT STARTED...")
    print(f"✅ Bot: @{bot.get_me().username}")
    print(f"✅ Admin ID: {ADMIN_ID}")
    print(f"✅ MongoDB: Connected")
    print("✅ Ready for deployment on Railway!")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            logging.error(f"Error: {e}")
            time.sleep(5)
