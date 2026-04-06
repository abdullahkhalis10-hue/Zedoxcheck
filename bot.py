# =========================
# ZEDOX BOT - MONGODB VERSION
# Advanced Features: Multi-Admin, Hierarchical Folders, Custom Buttons
# =========================

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import os, time, random, string, threading
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import hashlib

# =========================
# CONFIGURATION
# =========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.environ.get("ADMIN_IDS", "").split(','))) if os.environ.get("ADMIN_IDS") else []

# MongoDB Connection
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGODB_URI)
db = client['zedox_bot']

# Collections
users_col = db['users']
folders_col = db['folders']
codes_col = db['codes']
settings_col = db['settings']
main_buttons_col = db['main_buttons']
user_sessions_col = db['user_sessions']

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# =========================
# INITIALIZE SETTINGS
# =========================
def init_settings():
    if not settings_col.find_one({"_id": "config"}):
        settings_col.insert_one({
            "_id": "config",
            "force_channels": [],
            "custom_buttons": [],  # Buttons that don't force join
            "main_page_buttons": [],  # Buttons on main menu
            "vip_msg": "💎 Buy VIP to unlock premium features!",
            "welcome": "🔥 Welcome to ZEDOX BOT\n\nExplore our premium content!",
            "ref_reward": 10,
            "ref_levels": {1: 10, 5: 50, 10: 100},  # Referral milestones
            "notify": True,
            "purchase_msg": "💰 Get points by:\n• Referrals\n• Redeeming codes\n• Contacting admin",
            "admin_ids": ADMIN_IDS,
            "privacy_mode": True,  # No data sharing
            "folder_structure": {}  # Hierarchical folder structure
        })
    
    # Initialize main menu buttons if empty
    if settings_col.find_one({"_id": "main_buttons"}) is None:
        default_buttons = [
            {"text": "📂 FREE METHODS", "type": "folder", "data": "free"},
            {"text": "💎 VIP METHODS", "type": "folder", "data": "vip"},
            {"text": "📦 PREMIUM APPS", "type": "folder", "data": "apps"},
            {"text": "💰 POINTS", "type": "command", "data": "points"},
            {"text": "⭐ GET VIP", "type": "command", "data": "get_vip"},
            {"text": "🎁 REFERRAL", "type": "command", "data": "referral"},
            {"text": "👤 ACCOUNT", "type": "command", "data": "account"},
            {"text": "📚 MY METHODS", "type": "command", "data": "my_methods"},
            {"text": "💎 GET POINTS", "type": "command", "data": "get_points"},
            {"text": "🏆 REDEEM", "type": "command", "data": "redeem"}
        ]
        settings_col.insert_one({"_id": "main_buttons", "buttons": default_buttons})

init_settings()

# =========================
# HELPER FUNCTIONS
# =========================
def is_admin(user_id):
    config = settings_col.find_one({"_id": "config"})
    return user_id in config.get("admin_ids", [])

def get_settings():
    return settings_col.find_one({"_id": "config"})

def update_settings(update_data):
    settings_col.update_one({"_id": "config"}, {"$set": update_data})

# =========================
# USER CLASS
# =========================
class User:
    def __init__(self, uid):
        self.uid = str(uid)
        user = users_col.find_one({"_id": self.uid})
        
        if not user:
            user = {
                "_id": self.uid,
                "points": 0,
                "vip": False,
                "vip_expiry": None,
                "ref": None,
                "ref_count": 0,
                "ref_earnings": 0,
                "purchased_methods": [],
                "used_codes": [],
                "username": None,
                "first_name": None,
                "last_seen": datetime.now(),
                "created_at": datetime.now(),
                "total_spent": 0
            }
            users_col.insert_one(user)
        
        self.data = user
    
    def save(self):
        users_col.update_one({"_id": self.uid}, {"$set": self.data})
    
    def is_vip(self):
        if self.data.get("vip") and self.data.get("vip_expiry"):
            if datetime.now() > self.data["vip_expiry"]:
                self.data["vip"] = False
                self.save()
                return False
        return self.data.get("vip", False)
    
    def points(self):
        return self.data.get("points", 0)
    
    def purchased_methods(self):
        return self.data.get("purchased_methods", [])
    
    def used_codes(self):
        return self.data.get("used_codes", [])
    
    def update_username(self, username, first_name):
        if username != self.data.get("username"):
            self.data["username"] = username
        if first_name != self.data.get("first_name"):
            self.data["first_name"] = first_name
        self.data["last_seen"] = datetime.now()
        self.save()
    
    def add_points(self, points, source="unknown"):
        self.data["points"] += points
        if source == "referral":
            self.data["ref_earnings"] = self.data.get("ref_earnings", 0) + points
        self.save()
    
    def make_vip(self, days=30):
        self.data["vip"] = True
        expiry = datetime.now() + timedelta(days=days)
        self.data["vip_expiry"] = expiry
        self.save()
    
    def remove_vip(self):
        self.data["vip"] = False
        self.data["vip_expiry"] = None
        self.save()
    
    def purchase_method(self, method_id, price):
        if self.points() >= price:
            self.add_points(-price, "purchase")
            if method_id not in self.data.get("purchased_methods", []):
                self.data.setdefault("purchased_methods", []).append(method_id)
                self.data["total_spent"] = self.data.get("total_spent", 0) + price
                self.save()
            return True
        return False
    
    def can_access_method(self, method_id):
        if self.is_vip():
            return True
        return method_id in self.data.get("purchased_methods", [])
    
    def add_used_code(self, code):
        if code not in self.data.get("used_codes", []):
            self.data.setdefault("used_codes", []).append(code)
            self.save()
            return True
        return False
    
    def add_referral(self, referrer_id):
        if not self.data.get("ref"):
            self.data["ref"] = str(referrer_id)
            self.save()
            
            # Give points to referrer
            referrer = User(referrer_id)
            config = get_settings()
            reward = config.get("ref_reward", 10)
            referrer.add_points(reward, "referral")
            referrer.data["ref_count"] = referrer.data.get("ref_count", 0) + 1
            
            # Check milestone rewards
            ref_count = referrer.data["ref_count"]
            milestone_rewards = config.get("ref_levels", {})
            if str(ref_count) in milestone_rewards:
                milestone_reward = milestone_rewards[str(ref_count)]
                referrer.add_points(milestone_reward, "milestone")
                try:
                    bot.send_message(referrer_id, f"🎉 **Milestone Reached!**\n\nYou've referred {ref_count} users!\n➕ +{milestone_reward} bonus points!")
                except:
                    pass
            
            referrer.save()
            return True
        return False

# =========================
# HIERARCHICAL FOLDER SYSTEM
# =========================
class FolderManager:
    @staticmethod
    def create_folder(name, category, parent_id=None, price=0, is_free=False):
        folder = {
            "name": name,
            "category": category,  # free, vip, apps
            "parent_id": parent_id,
            "price": price,
            "is_free": is_free,
            "files": [],
            "subfolders": [],
            "created_at": datetime.now(),
            "order": FolderManager.get_next_order(category, parent_id)
        }
        result = folders_col.insert_one(folder)
        return result.inserted_id
    
    @staticmethod
    def get_next_order(category, parent_id=None):
        query = {"category": category}
        if parent_id:
            query["parent_id"] = parent_id
        else:
            query["parent_id"] = None
        
        count = folders_col.count_documents(query)
        return count
    
    @staticmethod
    def get_folder(folder_id):
        return folders_col.find_one({"_id": ObjectId(folder_id)})
    
    @staticmethod
    def get_folders(category, parent_id=None):
        query = {"category": category}
        if parent_id:
            query["parent_id"] = parent_id
        else:
            query["parent_id"] = None
        return list(folders_col.find(query).sort("order", 1))
    
    @staticmethod
    def update_folder_order(category, folder_orders):
        """Update order of folders - shifts all affected folders"""
        for folder_id, new_order in folder_orders.items():
            folders_col.update_one(
                {"_id": ObjectId(folder_id)},
                {"$set": {"order": new_order}}
            )
    
    @staticmethod
    def add_file(folder_id, file_data):
        folders_col.update_one(
            {"_id": ObjectId(folder_id)},
            {"$push": {"files": file_data}}
        )
    
    @staticmethod
    def delete_folder(folder_id):
        # Delete all subfolders recursively
        subfolders = folders_col.find({"parent_id": folder_id})
        for sub in subfolders:
            FolderManager.delete_folder(sub["_id"])
        
        # Delete the folder
        folders_col.delete_one({"_id": ObjectId(folder_id)})
    
    @staticmethod
    def update_folder_price(folder_id, price):
        folders_col.update_one(
            {"_id": ObjectId(folder_id)},
            {"$set": {"price": price}}
        )
    
    @staticmethod
    def move_folder(folder_id, new_parent_id, new_order=None):
        """Move folder to different parent with automatic reordering"""
        folder = FolderManager.get_folder(folder_id)
        old_parent = folder.get("parent_id")
        
        # Remove from old parent's subfolders list if exists
        if old_parent:
            folders_col.update_one(
                {"_id": ObjectId(old_parent)},
                {"$pull": {"subfolders": folder_id}}
            )
        
        # Add to new parent
        if new_parent_id:
            folders_col.update_one(
                {"_id": ObjectId(new_parent_id)},
                {"$push": {"subfolders": folder_id}}
            )
        
        # Update folder
        update_data = {"parent_id": new_parent_id}
        if new_order is not None:
            update_data["order"] = new_order
        
        folders_col.update_one(
            {"_id": ObjectId(folder_id)},
            {"$set": update_data}
        )
        
        # Reorder affected folders
        FolderManager.reorder_folders(folder["category"], new_parent_id)
    
    @staticmethod
    def reorder_folders(category, parent_id=None):
        """Renumber all folders sequentially starting from 0"""
        folders = FolderManager.get_folders(category, parent_id)
        for index, folder in enumerate(folders):
            folders_col.update_one(
                {"_id": folder["_id"]},
                {"$set": {"order": index}}
            )

# =========================
# CODES SYSTEM
# =========================
class CodesManager:
    @staticmethod
    def generate(pts, count, uses_per_code=1):
        codes = []
        for _ in range(count):
            code = "ZEDOX" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            code_data = {
                "code": code,
                "points": pts,
                "uses_left": uses_per_code,
                "total_uses": uses_per_code,
                "used_by": [],
                "created_at": datetime.now(),
                "expires_at": None
            }
            codes_col.insert_one(code_data)
            codes.append(code)
        return codes
    
    @staticmethod
    def redeem(code, user):
        code_data = codes_col.find_one({"code": code})
        
        if not code_data:
            return False, 0, "invalid"
        
        if code_data["uses_left"] <= 0:
            return False, 0, "already_used"
        
        if user.uid in code_data["used_by"]:
            return False, 0, "already_used_by_user"
        
        # Check expiry
        if code_data.get("expires_at") and datetime.now() > code_data["expires_at"]:
            return False, 0, "expired"
        
        # Redeem
        pts = code_data["points"]
        user.add_points(pts, "code_redeem")
        
        # Update code
        codes_col.update_one(
            {"_id": code_data["_id"]},
            {
                "$inc": {"uses_left": -1},
                "$push": {"used_by": user.uid}
            }
        )
        
        user.add_used_code(code)
        return True, pts, "success"
    
    @staticmethod
    def get_stats():
        total = codes_col.count_documents({})
        used = codes_col.count_documents({"uses_left": 0})
        unused = total - used
        return {"total": total, "used": used, "unused": unused}
    
    @staticmethod
    def delete_code(code):
        result = codes_col.delete_one({"code": code})
        return result.deleted_count > 0

# =========================
# FORCE JOIN & CUSTOM BUTTONS
# =========================
def check_force_join(uid):
    """Check if user has joined required channels"""
    config = get_settings()
    
    for ch in config.get("force_channels", []):
        try:
            m = bot.get_chat_member(ch, uid)
            if m.status in ["left", "kicked", "restricted"]:
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(f"📢 Join Channel", url=f"https://t.me/{ch.replace('@','')}"))
                kb.add(InlineKeyboardButton("🔄 I Joined", callback_data="recheck_force"))
                bot.send_message(uid, "🚫 **Access Restricted**\n\nPlease join our channel to continue:", reply_markup=kb)
                return True
        except:
            return True
    return False

def get_custom_buttons_kb():
    """Get custom buttons that don't force join"""
    config = get_settings()
    buttons = config.get("custom_buttons", [])
    
    if not buttons:
        return None
    
    kb = InlineKeyboardMarkup(row_width=2)
    for btn in buttons:
        kb.add(InlineKeyboardButton(btn["text"], url=btn["url"]))
    
    return kb

# =========================
# MAIN MENU WITH CUSTOM BUTTONS
# =========================
def main_menu(uid):
    """Generate main menu with admin-configurable buttons"""
    main_buttons_data = settings_col.find_one({"_id": "main_buttons"})
    buttons = main_buttons_data.get("buttons", [])
    
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Add buttons in rows
    row = []
    for btn in buttons:
        row.append(KeyboardButton(btn["text"]))
        if len(row) == 2:
            kb.row(*row)
            row = []
    
    if row:
        kb.row(*row)
    
    # Add admin panel button if admin
    if is_admin(uid):
        kb.row(KeyboardButton("⚙️ ADMIN PANEL"))
    
    return kb

# =========================
# FOLDER NAVIGATION
# =========================
def get_folder_kb(category, folder_id=None, page=0):
    """Get keyboard for folder navigation with pagination"""
    folders = FolderManager.get_folders(category, folder_id)
    per_page = 10
    start = page * per_page
    items = folders[start:start + per_page]
    
    kb = InlineKeyboardMarkup(row_width=1)
    
    for folder in items:
        price_text = f" [{folder['price']} pts]" if folder['price'] > 0 else " [FREE]" if folder['is_free'] else ""
        kb.add(InlineKeyboardButton(
            f"📁 {folder['name']}{price_text}",
            callback_data=f"open_folder|{str(folder['_id'])}"
        ))
    
    # Navigation buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Back", callback_data=f"folder_page|{category}|{folder_id if folder_id else 'root'}|{page - 1}"))
    if start + per_page < len(folders):
        nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"folder_page|{category}|{folder_id if folder_id else 'root'}|{page + 1}"))
    
    if folder_id:
        nav_buttons.append(InlineKeyboardButton("🔙 Parent Folder", callback_data=f"parent_folder|{category}|{folder_id}"))
    
    if nav_buttons:
        kb.row(*nav_buttons)
    
    # Add custom buttons (WhatsApp, etc.)
    custom_kb = get_custom_buttons_kb()
    if custom_kb:
        for row in custom_kb.keyboard:
            kb.row(*row)
    
    return kb

# =========================
# ADMIN PANEL - ENHANCED
# =========================
def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    buttons = [
        "📁 Manage Folders", "📤 Upload Content",
        "🔢 Reorder Folders", "🔄 Move Folder",
        "👑 Manage VIP", "🏆 Generate Codes",
        "📊 Statistics", "📤 Broadcast",
        "🔗 Force Join", "➕ Custom Buttons",
        "🎨 Main Menu Buttons", "⚙️ Settings",
        "📋 View Codes", "❌ Exit Admin"
    ]
    
    row = []
    for btn in buttons:
        row.append(btn)
        if len(row) == 2:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    
    return kb

# =========================
# FOLDER MANAGEMENT ADMIN
# =========================
@bot.message_handler(func=lambda m: m.text == "📁 Manage Folders" and is_admin(m.from_user.id))
def manage_folders(m):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ Create Folder", callback_data="admin_create_folder"),
        InlineKeyboardButton("🗑 Delete Folder", callback_data="admin_delete_folder"),
        InlineKeyboardButton("💰 Set Price", callback_data="admin_set_price"),
        InlineKeyboardButton("🔄 Move Folder", callback_data="admin_move_folder")
    )
    bot.send_message(m.from_user.id, "📁 **Folder Management**", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "admin_create_folder")
def create_folder_start(c):
    msg = bot.send_message(c.from_user.id, "📝 Send folder name:")
    bot.register_next_step_handler(msg, create_folder_category)

def create_folder_category(m):
    folder_name = m.text
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📂 FREE", callback_data=f"create_cat|free|{folder_name}"),
        InlineKeyboardButton("💎 VIP", callback_data=f"create_cat|vip|{folder_name}"),
        InlineKeyboardButton("📦 APPS", callback_data=f"create_cat|apps|{folder_name}")
    )
    bot.send_message(m.from_user.id, "Select category:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("create_cat|"))
def create_folder_parent(c):
    _, cat, folder_name = c.data.split("|")
    
    # Get existing folders for parent selection
    folders = FolderManager.get_folders(cat)
    
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📁 Root (No Parent)", callback_data=f"create_parent|{cat}|{folder_name}|none"))
    
    for folder in folders:
        kb.add(InlineKeyboardButton(f"📁 {folder['name']}", callback_data=f"create_parent|{cat}|{folder_name}|{folder['_id']}"))
    
    bot.edit_message_text("Select parent folder (or root):", c.from_user.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("create_parent|"))
def create_folder_price(c):
    _, cat, folder_name, parent_id = c.data.split("|")
    
    # Store in session
    user_sessions_col.update_one(
        {"user_id": c.from_user.id},
        {"$set": {
            "temp_folder": {
                "name": folder_name,
                "category": cat,
                "parent_id": None if parent_id == "none" else parent_id
            }
        }},
        upsert=True
    )
    
    msg = bot.send_message(c.from_user.id, "💰 Enter price (0 for free):")
    bot.register_next_step_handler(msg, create_folder_final)

def create_folder_final(m):
    try:
        price = int(m.text)
        session = user_sessions_col.find_one({"user_id": m.from_user.id})
        folder_data = session.get("temp_folder", {})
        
        folder_id = FolderManager.create_folder(
            name=folder_data["name"],
            category=folder_data["category"],
            parent_id=folder_data["parent_id"],
            price=price,
            is_free=(price == 0)
        )
        
        bot.send_message(m.from_user.id, f"✅ Folder created successfully!\nID: `{folder_id}`", parse_mode="Markdown")
        user_sessions_col.delete_one({"user_id": m.from_user.id})
    except:
        bot.send_message(m.from_user.id, "❌ Invalid price!")

# =========================
# REORDER FOLDERS
# =========================
@bot.message_handler(func=lambda m: m.text == "🔢 Reorder Folders" and is_admin(m.from_user.id))
def reorder_folders_start(m):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📂 FREE", callback_data="reorder|free"),
        InlineKeyboardButton("💎 VIP", callback_data="reorder|vip"),
        InlineKeyboardButton("📦 APPS", callback_data="reorder|apps")
    )
    bot.send_message(m.from_user.id, "Select category to reorder:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("reorder|"))
def reorder_show_folders(c):
    cat = c.data.split("|")[1]
    folders = FolderManager.get_folders(cat)
    
    if not folders:
        bot.answer_callback_query(c.id, "No folders found!")
        return
    
    kb = InlineKeyboardMarkup(row_width=1)
    for folder in folders:
        kb.add(InlineKeyboardButton(
            f"{folder['order']}. {folder['name']}",
            callback_data=f"reorder_select|{folder['_id']}"
        ))
    
    kb.add(InlineKeyboardButton("✅ Done Reordering", callback_data="reorder_done"))
    
    bot.edit_message_text(
        "📋 **Current Folder Order**\n\nClick a folder to change its position:",
        c.from_user.id,
        c.message.message_id,
        reply_markup=kb
    )

# =========================
# CUSTOM BUTTONS MANAGEMENT
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ Custom Buttons" and is_admin(m.from_user.id))
def manage_custom_buttons(m):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ Add Button", callback_data="add_custom_btn"),
        InlineKeyboardButton("🗑 Remove Button", callback_data="remove_custom_btn"),
        InlineKeyboardButton("📋 List Buttons", callback_data="list_custom_btns")
    )
    bot.send_message(m.from_user.id, "🔘 **Custom Buttons Manager**\n(Buttons that appear below folders - WhatsApp, Social, etc.)", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "add_custom_btn")
def add_custom_btn_start(c):
    msg = bot.send_message(c.from_user.id, "📝 Send button text:")
    bot.register_next_step_handler(msg, add_custom_btn_url)

def add_custom_btn_url(m):
    btn_text = m.text
    msg = bot.send_message(m.from_user.id, "🔗 Send button URL (Telegram link, WhatsApp, etc.):")
    bot.register_next_step_handler(msg, lambda m2: save_custom_btn(m2, btn_text))

def save_custom_btn(m, btn_text):
    url = m.text
    config = get_settings()
    buttons = config.get("custom_buttons", [])
    buttons.append({"text": btn_text, "url": url})
    update_settings({"custom_buttons": buttons})
    bot.send_message(m.from_user.id, f"✅ Button added: {btn_text}")

# =========================
# MAIN MENU BUTTONS MANAGEMENT
# =========================
@bot.message_handler(func=lambda m: m.text == "🎨 Main Menu Buttons" and is_admin(m.from_user.id))
def manage_main_buttons(m):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ Add Button", callback_data="add_main_btn"),
        InlineKeyboardButton("🗑 Remove Button", callback_data="remove_main_btn"),
        InlineKeyboardButton("📋 List Buttons", callback_data="list_main_btns"),
        InlineKeyboardButton("⬆️ Move Up", callback_data="move_main_up"),
        InlineKeyboardButton("⬇️ Move Down", callback_data="move_main_down")
    )
    bot.send_message(m.from_user.id, "🎨 **Main Menu Buttons Manager**", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "add_main_btn")
def add_main_btn_start(c):
    msg = bot.send_message(c.from_user.id, "📝 Send button text:")
    bot.register_next_step_handler(msg, add_main_btn_type)

def add_main_btn_type(m):
    btn_text = m.text
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📁 Folder", callback_data=f"main_btn_type|folder|{btn_text}"),
        InlineKeyboardButton("⚡ Command", callback_data=f"main_btn_type|command|{btn_text}")
    )
    bot.send_message(m.from_user.id, "Select button type:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("main_btn_type|"))
def add_main_btn_data(c):
    _, btn_type, btn_text = c.data.split("|")
    
    if btn_type == "folder":
        msg = bot.send_message(c.from_user.id, "📁 Enter folder category (free/vip/apps):")
        bot.register_next_step_handler(msg, lambda m: save_main_btn(m, btn_text, btn_type, m.text))
    else:
        msg = bot.send_message(c.from_user.id, "⚡ Enter command data (points/get_vip/referral/etc.):")
        bot.register_next_step_handler(msg, lambda m: save_main_btn(m, btn_text, btn_type, m.text))

def save_main_btn(m, btn_text, btn_type, btn_data):
    main_buttons_data = settings_col.find_one({"_id": "main_buttons"})
    buttons = main_buttons_data.get("buttons", [])
    buttons.append({"text": btn_text, "type": btn_type, "data": btn_data})
    settings_col.update_one({"_id": "main_buttons"}, {"$set": {"buttons": buttons}})
    bot.send_message(m.from_user.id, f"✅ Button added: {btn_text}")

# =========================
# STATISTICS WITH PRIVACY
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 Statistics" and is_admin(m.from_user.id))
def show_statistics(m):
    config = get_settings()
    privacy_mode = config.get("privacy_mode", True)
    
    total_users = users_col.count_documents({})
    vip_users = users_col.count_documents({"vip": True})
    free_users = total_users - vip_users
    
    total_points = sum(user.get("points", 0) for user in users_col.find())
    total_refs = sum(user.get("ref_count", 0) for user in users_col.find())
    
    total_folders = folders_col.count_documents({})
    total_files = sum(len(folder.get("files", [])) for folder in folders_col.find())
    
    codes_stats = CodesManager.get_stats()
    
    stats_msg = f"📊 **ZEDOX BOT STATISTICS**\n\n"
    stats_msg += f"👥 **Users:**\n"
    stats_msg += f"• Total: {total_users}\n"
    stats_msg += f"• VIP: {vip_users}\n"
    stats_msg += f"• Free: {free_users}\n\n"
    
    stats_msg += f"💰 **Economy:**\n"
    stats_msg += f"• Total Points: {total_points:,}\n"
    stats_msg += f"• Total Referrals: {total_refs}\n\n"
    
    stats_msg += f"📚 **Content:**\n"
    stats_msg += f"• Folders: {total_folders}\n"
    stats_msg += f"• Files: {total_files}\n\n"
    
    stats_msg += f"🎫 **Codes:**\n"
    stats_msg += f"• Total: {codes_stats['total']}\n"
    stats_msg += f"• Used: {codes_stats['used']}\n"
    stats_msg += f"• Unused: {codes_stats['unused']}\n"
    
    if privacy_mode:
        stats_msg += f"\n🔒 **Privacy Mode: ENABLED**\nNo user data is shared with third parties."
    
    bot.send_message(m.from_user.id, stats_msg, parse_mode="Markdown")

# =========================
# BROADCAST WITH TARGETING
# =========================
@bot.message_handler(func=lambda m: m.text == "📤 Broadcast" and is_admin(m.from_user.id))
def broadcast_menu(m):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📢 All Users", callback_data="broadcast|all"),
        InlineKeyboardButton("💎 VIP Users", callback_data="broadcast|vip"),
        InlineKeyboardButton("🆓 Free Users", callback_data="broadcast|free"),
        InlineKeyboardButton("👥 Active (7d)", callback_data="broadcast|active")
    )
    bot.send_message(m.from_user.id, "📡 Select target audience:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("broadcast|"))
def broadcast_target(c):
    target = c.data.split("|")[1]
    msg = bot.send_message(c.from_user.id, "📝 Send your broadcast message (text, photo, video, or document):")
    bot.register_next_step_handler(msg, lambda m: send_broadcast(m, target))

def send_broadcast(m, target):
    query = {}
    if target == "vip":
        query["vip"] = True
    elif target == "free":
        query["vip"] = False
    elif target == "active":
        week_ago = datetime.now() - timedelta(days=7)
        query["last_seen"] = {"$gte": week_ago}
    
    users = users_col.find(query)
    sent = 0
    failed = 0
    
    status_msg = bot.send_message(m.from_user.id, "📤 Broadcasting in progress...")
    
    for user in users:
        try:
            uid = int(user["_id"])
            if m.content_type == "text":
                bot.send_message(uid, m.text, parse_mode="HTML")
            elif m.content_type == "photo":
                bot.send_photo(uid, m.photo[-1].file_id, caption=m.caption, parse_mode="HTML")
            elif m.content_type == "video":
                bot.send_video(uid, m.video.file_id, caption=m.caption, parse_mode="HTML")
            elif m.content_type == "document":
                bot.send_document(uid, m.document.file_id, caption=m.caption, parse_mode="HTML")
            sent += 1
        except:
            failed += 1
        
        # Rate limiting
        time.sleep(0.05)
    
    bot.edit_message_text(
        f"✅ **Broadcast Complete**\n\n📤 Sent: {sent}\n❌ Failed: {failed}\n🎯 Target: {target.upper()}",
        m.from_user.id,
        status_msg.message_id
    )

# =========================
# USER COMMANDS
# =========================
@bot.message_handler(commands=["start"])
def start_cmd(m):
    uid = m.from_user.id
    args = m.text.split()
    
    user = User(uid)
    user.update_username(m.from_user.username, m.from_user.first_name)
    
    # Handle referral
    if len(args) > 1:
        ref_code = args[1]
        if ref_code != str(uid):
            user.add_referral(ref_code)
    
    if check_force_join(uid):
        return
    
    config = get_settings()
    
    # Send welcome with custom buttons
    welcome_text = config.get("welcome", "🔥 Welcome to ZEDOX BOT!")
    
    # Add custom inline buttons if any
    custom_kb = get_custom_buttons_kb()
    if custom_kb:
        bot.send_message(uid, welcome_text, reply_markup=main_menu(uid))
        bot.send_message(uid, "🔗 **Quick Links:**", reply_markup=custom_kb)
    else:
        bot.send_message(uid, welcome_text, reply_markup=main_menu(uid))

@bot.message_handler(func=lambda m: m.text in ["📂 FREE METHODS", "💎 VIP METHODS", "📦 PREMIUM APPS"])
def show_category(m):
    uid = m.from_user.id
    
    if check_force_join(uid):
        return
    
    mapping = {
        "📂 FREE METHODS": "free",
        "💎 VIP METHODS": "vip",
        "📦 PREMIUM APPS": "apps"
    }
    
    category = mapping.get(m.text)
    folders = FolderManager.get_folders(category)
    
    if not folders:
        bot.send_message(uid, f"📂 {m.text}\n\nNo content available yet!")
        return
    
    bot.send_message(uid, f"📂 {m.text}\n\nSelect a folder:", reply_markup=get_folder_kb(category))

@bot.callback_query_handler(func=lambda c: c.data.startswith("open_folder|"))
def open_folder_callback(c):
    uid = c.from_user.id
    user = User(uid)
    folder_id = c.data.split("|")[1]
    
    folder = FolderManager.get_folder(folder_id)
    if not folder:
        bot.answer_callback_query(c.id, "Folder not found!")
        return
    
    # Check access for VIP folders
    if folder["category"] == "vip" and not user.is_vip() and not user.can_access_method(folder_id):
        price = folder.get("price", 0)
        if price > 0:
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton(f"💰 Buy for {price} pts", callback_data=f"buy_folder|{folder_id}|{price}"),
                InlineKeyboardButton("⭐ GET VIP", callback_data="get_vip"),
                InlineKeyboardButton("💎 GET POINTS", callback_data="get_points")
            )
            bot.send_message(uid, f"🔒 **VIP Content: {folder['name']}**\n\nPrice: {price} points\nYour points: {user.points()}", reply_markup=kb)
        else:
            bot.send_message(uid, "🔒 **VIP Content**\n\nGet VIP membership to access this content!")
        bot.answer_callback_query(c.id)
        return
    
    # Check if folder has subfolders
    subfolders = FolderManager.get_folders(folder["category"], folder_id)
    if subfolders:
        bot.edit_message_text(
            f"📁 **{folder['name']}**\n\nSelect subfolder:",
            uid,
            c.message.message_id,
            reply_markup=get_folder_kb(folder["category"], folder_id)
        )
        return
    
    # Send files if no subfolders
    files = folder.get("files", [])
    if not files:
        bot.answer_callback_query(c.id, "No files in this folder!")
        return
    
    # Deduct points if needed
    if folder["price"] > 0 and folder["category"] != "vip":
        if user.points() < folder["price"]:
            bot.answer_callback_query(c.id, f"❌ Need {folder['price']} points!", show_alert=True)
            return
        user.add_points(-folder["price"], "purchase")
        bot.answer_callback_query(c.id, f"✅ {folder['price']} points deducted!")
    
    # Send files
    bot.answer_callback_query(c.id, "📤 Sending files...")
    for file_data in files:
        try:
            if file_data["type"] == "document":
                bot.send_document(uid, file_data["file_id"], caption=file_data.get("caption", ""))
            elif file_data["type"] == "photo":
                bot.send_photo(uid, file_data["file_id"], caption=file_data.get("caption", ""))
            elif file_data["type"] == "video":
                bot.send_video(uid, file_data["file_id"], caption=file_data.get("caption", ""))
            time.sleep(0.3)
        except Exception as e:
            print(f"Error sending file: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_folder|"))
def buy_folder_callback(c):
    uid = c.from_user.id
    user = User(uid)
    _, folder_id, price = c.data.split("|")
    price = int(price)
    
    if user.points() < price:
        bot.answer_callback_query(c.id, f"❌ Need {price} points!", show_alert=True)
        return
    
    if user.purchase_method(folder_id, price):
        bot.answer_callback_query(c.id, f"✅ Purchased! {price} points deducted!", show_alert=True)
        # Re-open folder
        open_folder_callback(c)
    else:
        bot.answer_callback_query(c.id, "❌ Purchase failed!", show_alert=True)

# =========================
# OTHER USER COMMANDS
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 POINTS")
def show_points(m):
    uid = m.from_user.id
    user = User(uid)
    bot.send_message(uid, f"💰 **Your Balance**\n\nPoints: **{user.points()}**\n\n✨ Ways to earn:\n• Referral program\n• Redeem codes\n• Complete tasks", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎁 REFERRAL")
def show_referral(m):
    uid = m.from_user.id
    user = User(uid)
    bot_username = bot.get_me().username
    link = f"https://t.me/{bot_username}?start={uid}"
    
    config = get_settings()
    ref_reward = config.get("ref_reward", 10)
    milestones = config.get("ref_levels", {})
    
    msg = f"🎁 **Referral Program**\n\n"
    msg += f"Your link: `{link}`\n\n"
    msg += f"✨ For each friend who joins: **+{ref_reward} points**\n"
    msg += f"📊 Total referrals: **{user.data.get('ref_count', 0)}**\n"
    msg += f"💰 Total earned: **{user.data.get('ref_earnings', 0)}** points\n\n"
    
    if milestones:
        msg += f"🏆 **Milestone Rewards:**\n"
        for refs, reward in milestones.items():
            msg += f"• {refs} referrals → +{reward} points\n"
    
    bot.send_message(uid, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "👤 ACCOUNT")
def show_account(m):
    uid = m.from_user.id
    user = User(uid)
    
    status = "💎 VIP" if user.is_vip() else "🆓 Free"
    if user.is_vip() and user.data.get("vip_expiry"):
        days_left = (user.data["vip_expiry"] - datetime.now()).days
        status += f" (expires in {days_left} days)"
    
    msg = f"👤 **Account Info**\n\n"
    msg += f"ID: `{uid}`\n"
    msg += f"Name: {user.data.get('first_name', 'Unknown')}\n"
    msg += f"Username: @{user.data.get('username', 'None')}\n"
    msg += f"Status: {status}\n"
    msg += f"Points: **{user.points()}**\n"
    msg += f"Purchased: **{len(user.purchased_methods())}** items\n"
    msg += f"Redeemed Codes: **{len(user.used_codes())}**\n"
    msg += f"Referrals: **{user.data.get('ref_count', 0)}**\n"
    msg += f"Total Spent: **{user.data.get('total_spent', 0)}** points\n"
    
    bot.send_message(uid, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📚 MY METHODS")
def show_my_methods(m):
    uid = m.from_user.id
    user = User(uid)
    
    if user.is_vip():
        bot.send_message(uid, "💎 **VIP Member**\n\nYou have access to ALL VIP content!\n\nUse the VIP METHODS section to browse.", parse_mode="Markdown")
        return
    
    purchased = user.purchased_methods()
    if not purchased:
        bot.send_message(uid, "📚 **Your Purchased Items**\n\nYou haven't purchased any VIP items yet.\n\nUse points to buy VIP content!", parse_mode="Markdown")
        return
    
    msg = "📚 **Your Purchased Items**\n\n"
    for method_id in purchased:
        folder = folders_col.find_one({"_id": ObjectId(method_id)})
        if folder:
            msg += f"✅ {folder['name']}\n"
    
    bot.send_message(uid, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "💎 GET POINTS")
def get_points_info(m):
    uid = m.from_user.id
    config = get_settings()
    msg = config.get("purchase_msg", "💰 Get points through referrals and codes!")
    bot.send_message(uid, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "⭐ GET VIP")
def get_vip_info(m):
    uid = m.from_user.id
    user = User(uid)
    
    if user.is_vip():
        bot.send_message(uid, "✅ **You are already a VIP member!**\n\nEnjoy exclusive content!", parse_mode="Markdown")
        return
    
    config = get_settings()
    msg = config.get("vip_msg", "💎 Contact admin to get VIP access!")
    bot.send_message(uid, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🏆 REDEEM")
def redeem_start(m):
    msg = bot.send_message(m.from_user.id, "🎫 Enter your redeem code:")
    bot.register_next_step_handler(msg, process_redeem)

def process_redeem(m):
    uid = m.from_user.id
    user = User(uid)
    code = m.text.strip().upper()
    
    success, pts, reason = CodesManager.redeem(code, user)
    
    if success:
        bot.send_message(uid, f"✅ **Code Redeemed!**\n\n➕ +{pts} points\n💰 Total: **{user.points()}** points", parse_mode="Markdown")
    else:
        messages = {
            "invalid": "❌ Invalid code!",
            "already_used": "❌ Code already used!",
            "already_used_by_user": "❌ You've already used this code!",
            "expired": "❌ Code has expired!"
        }
        bot.send_message(uid, messages.get(reason, "❌ Invalid code!"))

@bot.message_handler(func=lambda m: m.text == "🆔 CHAT ID")
def send_chat_id(m):
    bot.send_message(m.from_user.id, f"🆔 Your ID: `{m.from_user.id}`", parse_mode="Markdown")

# =========================
# FORCE JOIN RECHECK
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "recheck_force")
def recheck_force(c):
    uid = c.from_user.id
    if not check_force_join(uid):
        bot.edit_message_text("✅ Access granted!", uid, c.message.message_id)
        bot.send_message(uid, "Welcome! Use the menu below.", reply_markup=main_menu(uid))
    else:
        bot.answer_callback_query(c.id, "Please join all channels first!", show_alert=True)

# =========================
# ADMIN PANEL ACCESS
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def admin_panel(m):
    bot.send_message(m.from_user.id, "⚙️ **Admin Control Panel**", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "❌ Exit Admin" and is_admin(m.from_user.id))
def exit_admin(m):
    bot.send_message(m.from_user.id, "Exited admin panel", reply_markup=main_menu(m.from_user.id))

# =========================
# UPLOAD CONTENT
# =========================
@bot.message_handler(func=lambda m: m.text == "📤 Upload Content" and is_admin(m.from_user.id))
def upload_content_start(m):
    # Show folder selection for upload
    categories = ["free", "vip", "apps"]
    kb = InlineKeyboardMarkup(row_width=2)
    for cat in categories:
        kb.add(InlineKeyboardButton(f"📂 {cat.upper()}", callback_data=f"upload_select_cat|{cat}"))
    bot.send_message(m.from_user.id, "Select category to upload to:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("upload_select_cat|"))
def upload_select_folder(c):
    cat = c.data.split("|")[1]
    folders = FolderManager.get_folders(cat)
    
    if not folders:
        bot.answer_callback_query(c.id, "No folders! Create one first.")
        return
    
    kb = InlineKeyboardMarkup(row_width=1)
    for folder in folders:
        kb.add(InlineKeyboardButton(f"📁 {folder['name']}", callback_data=f"upload_to|{folder['_id']}"))
    
    bot.edit_message_text("Select folder to upload to:", c.from_user.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("upload_to|"))
def upload_to_folder(c):
    folder_id = c.data.split("|")[1]
    
    # Store in session
    user_sessions_col.update_one(
        {"user_id": c.from_user.id},
        {"$set": {"upload_folder_id": folder_id, "upload_files": []}},
        upsert=True
    )
    
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("/done", "/cancel")
    
    bot.send_message(c.from_user.id, "📤 Send files (documents, photos, videos)\nClick /done when finished\nClick /cancel to cancel", reply_markup=kb)
    bot.register_next_step_handler_by_chat_id(c.from_user.id, collect_upload_files)

def collect_upload_files(m):
    if m.text == "/cancel":
        user_sessions_col.delete_one({"user_id": m.from_user.id})
        bot.send_message(m.from_user.id, "❌ Upload cancelled", reply_markup=admin_menu())
        return
    
    if m.text == "/done":
        session = user_sessions_col.find_one({"user_id": m.from_user.id})
        files = session.get("upload_files", [])
        folder_id = session.get("upload_folder_id")
        
        if files:
            for file_data in files:
                FolderManager.add_file(folder_id, file_data)
            bot.send_message(m.from_user.id, f"✅ Uploaded {len(files)} file(s)!", reply_markup=admin_menu())
        else:
            bot.send_message(m.from_user.id, "No files to upload!", reply_markup=admin_menu())
        
        user_sessions_col.delete_one({"user_id": m.from_user.id})
        return
    
    # Collect file
    if m.content_type in ["document", "photo", "video"]:
        file_id = m.document.file_id if m.content_type == "document" else m.photo[-1].file_id if m.content_type == "photo" else m.video.file_id
        file_data = {
            "type": m.content_type,
            "file_id": file_id,
            "caption": m.caption,
            "uploaded_at": datetime.now()
        }
        
        user_sessions_col.update_one(
            {"user_id": m.from_user.id},
            {"$push": {"upload_files": file_data}}
        )
        bot.send_message(m.from_user.id, f"✅ File saved! ({m.content_type})")
    
    bot.register_next_step_handler(m, collect_upload_files)

# =========================
# FALLBACK HANDLER
# =========================
@bot.message_handler(func=lambda m: True)
def fallback_handler(m):
    uid = m.from_user.id
    if not check_force_join(uid):
        bot.send_message(uid, "❌ Please use the menu buttons", reply_markup=main_menu(uid))

# =========================
# ERROR HANDLER
# =========================
@bot.callback_query_handler(func=lambda c: True)
def callback_fallback(c):
    bot.answer_callback_query(c.id, "Processing...")

# =========================
# START BOT
# =========================
def run_bot():
    while True:
        try:
            print("🚀 ZEDOX BOT RUNNING (MongoDB Version)")
            print(f"✅ Bot: @{bot.get_me().username}")
            print(f"✅ Admins: {ADMIN_IDS}")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"ERROR: {e}")
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    while True:
        time.sleep(1)
