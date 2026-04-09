# =========================
# ZEDOX BOT - MONGODB VERSION
# Core Setup + MongoDB + User + Codes + Force Join
# =========================

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
import os, time, random, string, threading
from pymongo import MongoClient
from bson import ObjectId
import json

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# =========================
# MONGODB SETUP
# =========================
client = MongoClient(MONGO_URI)
db = client.zedox_bot

# Collections
users_col = db.users
config_col = db.config
codes_col = db.codes
files_col = db.files

# =========================
# INIT DATABASE
# =========================
def init_db():
    # Initialize config if not exists
    if config_col.count_documents({}) == 0:
        default_config = {
            "force_channels": [],
            "vip_msg": "💎 Buy VIP to unlock this!",
            "welcome": "🔥 Welcome to ZEDOX BOT",
            "ref_reward": 5,
            "notify": True,
            "purchase_msg": "💰 Purchase VIP to access premium features!"
        }
        config_col.insert_one(default_config)
    
    # Create indexes for better performance
    users_col.create_index("uid", unique=True)
    codes_col.create_index("code", unique=True)
    files_col.create_index([("category", 1), ("name", 1)])

init_db()

def get_config():
    return config_col.find_one({}) or {}

def update_config(key, value):
    config_col.update_one({}, {"$set": {key: value}}, upsert=True)

# =========================
# USER CLASS (MONGODB)
# =========================
class User:
    def __init__(self, uid):
        self.uid = str(uid)
        user_data = users_col.find_one({"uid": self.uid})
        
        if not user_data:
            user_data = {
                "uid": self.uid,
                "points": 0,
                "vip": False,
                "ref": None,
                "purchased_methods": [],
                "used_codes": [],
                "username": None,
                "ref_count": 0,
                "joined_at": time.time()
            }
            users_col.insert_one(user_data)
        
        self.data = user_data

    def is_vip(self): 
        return self.data.get("vip", False)
    
    def points(self): 
        return self.data.get("points", 0)
    
    def purchased_methods(self): 
        return self.data.get("purchased_methods", [])
    
    def used_codes(self): 
        return self.data.get("used_codes", [])
    
    def username(self): 
        return self.data.get("username", None)
    
    def ref_count(self):
        return self.data.get("ref_count", 0)

    def update_username(self, username):
        if username != self.data.get("username"):
            users_col.update_one(
                {"uid": self.uid},
                {"$set": {"username": username}}
            )
            self.data["username"] = username

    def add_points(self, p):
        users_col.update_one(
            {"uid": self.uid},
            {"$inc": {"points": p}}
        )
        self.data["points"] = self.data.get("points", 0) + p

    def make_vip(self):
        users_col.update_one(
            {"uid": self.uid},
            {"$set": {"vip": True}}
        )
        self.data["vip"] = True
    
    def remove_vip(self):
        users_col.update_one(
            {"uid": self.uid},
            {"$set": {"vip": False}}
        )
        self.data["vip"] = False
    
    def purchase_method(self, method_name, price):
        if self.points() >= price:
            self.add_points(-price)
            users_col.update_one(
                {"uid": self.uid},
                {"$addToSet": {"purchased_methods": method_name}}
            )
            if "purchased_methods" not in self.data:
                self.data["purchased_methods"] = []
            self.data["purchased_methods"].append(method_name)
            return True
        return False
    
    def can_access_method(self, method_name):
        return self.is_vip() or method_name in self.data.get("purchased_methods", [])
    
    def add_used_code(self, code):
        if code not in self.data.get("used_codes", []):
            users_col.update_one(
                {"uid": self.uid},
                {"$addToSet": {"used_codes": code}}
            )
            if "used_codes" not in self.data:
                self.data["used_codes"] = []
            self.data["used_codes"].append(code)
            return True
        return False
    
    def has_used_code(self, code):
        return code in self.data.get("used_codes", [])
    
    def set_ref(self, ref_uid):
        if not self.data.get("ref") and ref_uid != self.uid:
            users_col.update_one(
                {"uid": self.uid},
                {"$set": {"ref": ref_uid}}
            )
            self.data["ref"] = ref_uid
            
            # Increment referral count for referrer
            users_col.update_one(
                {"uid": ref_uid},
                {"$inc": {"ref_count": 1}}
            )
            return True
        return False
    
    def get_ref(self):
        return self.data.get("ref")

# =========================
# CODES SYSTEM (MONGODB)
# =========================
class Codes:
    def __init__(self):
        pass

    def generate(self, pts, count):
        res = []
        for _ in range(count):
            code = "ZEDOX" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            code_data = {
                "code": code,
                "points": pts,
                "used": False,
                "used_by": None,
                "used_at": None,
                "created_at": time.time()
            }
            codes_col.insert_one(code_data)
            res.append(code)
        return res

    def redeem(self, code, user):
        code_data = codes_col.find_one({"code": code})
        
        if not code_data:
            return False, 0, "invalid"
        
        if code_data.get("used", False):
            return False, 0, "already_used"
        
        if user.has_used_code(code):
            return False, 0, "already_used_by_user"
        
        pts = code_data["points"]
        user.add_points(pts)
        
        # Mark code as used
        codes_col.update_one(
            {"code": code},
            {"$set": {
                "used": True,
                "used_by": user.uid,
                "used_at": time.time()
            }}
        )
        
        user.add_used_code(code)
        return True, pts, "success"

    def get_code_info(self, code):
        return codes_col.find_one({"code": code})

    def get_all_codes(self):
        return list(codes_col.find().sort("created_at", -1))

    def delete_code(self, code):
        result = codes_col.delete_one({"code": code})
        return result.deleted_count > 0

codesys = Codes()

# =========================
# FORCE JOIN (STRICT)
# =========================
def force_block(uid):
    cfg = get_config()
    
    for ch in cfg.get("force_channels", []):
        try:
            m = bot.get_chat_member(ch, uid)
            if m.status in ["left", "kicked"]:
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(f"Join {ch}", url=f"https://t.me/{ch.replace('@', '')}"))
                kb.add(InlineKeyboardButton("🔄 I Joined", callback_data="recheck"))
                bot.send_message(uid, "🚫 Join all channels first!", reply_markup=kb)
                return True
        except Exception as e:
            print(f"Force join error: {e}")
            return True
    return False

# =========================
# FILE SYSTEM (MONGODB)
# =========================
class FS:
    def add(self, cat, name, files, price):
        file_data = {
            "category": cat,
            "name": name,
            "files": files,
            "price": price,
            "created_at": time.time()
        }
        files_col.insert_one(file_data)

    def get(self, cat):
        files = list(files_col.find({"category": cat}))
        result = {}
        for f in files:
            result[f["name"]] = {"files": f["files"], "price": f["price"]}
        return result

    def delete(self, cat, name):
        result = files_col.delete_one({"category": cat, "name": name})
        return result.deleted_count > 0

    def edit(self, cat, name, price):
        result = files_col.update_one(
            {"category": cat, "name": name},
            {"$set": {"price": price}}
        )
        return result.modified_count > 0

fs = FS()

def get_kb(cat, page=0):
    data = list(fs.get(cat).items())
    per = 10
    start = page * per
    items = data[start:start + per]

    kb = InlineKeyboardMarkup()
    for name, d in items:
        price = d["price"]
        txt = f"{name} [{price} pts]" if price > 0 else name
        kb.add(InlineKeyboardButton(txt, callback_data=f"open|{cat}|{name}"))

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"page|{cat}|{page - 1}"))
    if start + per < len(data):
        nav.append(InlineKeyboardButton("➡️", callback_data=f"page|{cat}|{page + 1}"))
    if nav:
        kb.row(*nav)

    return kb

# =========================
# ZEDOX BOT - PART 2
# Admin Panel + Upload + Delete + Edit + Broadcast + Codes + VIP Management
# =========================

def is_admin(uid):
    return uid == ADMIN_ID

def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    
    kb.row("📦 Upload FREE", "💎 Upload VIP")
    kb.row("📱 Upload APPS")
    
    kb.row("✏️ Edit Folder Price", "🗑 Delete Folder")
    
    kb.row("👑 Add VIP User", "👑 Remove VIP User")
    kb.row("🏆 Generate Codes", "📊 View Codes")
    kb.row("📊 User Statistics", "📤 Broadcast")
    
    kb.row("⭐ Set VIP Message", "💰 Set Purchase Message")
    kb.row("🏠 Set Welcome", "🎁 Set Ref Reward")
    
    kb.row("➕ Add Force Join", "➖ Remove Force Join")
    
    kb.row("❌ Exit Admin")
    return kb

@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def admin_panel(m):
    bot.send_message(m.from_user.id, "⚙️ Admin Panel", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "❌ Exit Admin" and is_admin(m.from_user.id))
def exit_admin(m):
    bot.send_message(m.from_user.id, "Exited Admin", reply_markup=main_menu(m.from_user.id))

# =========================
# SET REFERRAL REWARD (NEW)
# =========================
@bot.message_handler(func=lambda m: m.text == "🎁 Set Ref Reward" and is_admin(m.from_user.id))
def set_ref_reward_start(m):
    cfg = get_config()
    current = cfg.get("ref_reward", 5)
    msg = bot.send_message(
        m.from_user.id, 
        f"🎁 **Set Referral Reward**\n\nCurrent reward: **{current} points** per referral\n\nSend new point value:",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, save_ref_reward)

def save_ref_reward(m):
    try:
        points = int(m.text)
        if points < 0:
            bot.send_message(m.from_user.id, "❌ Points cannot be negative!")
            return
        
        update_config("ref_reward", points)
        bot.send_message(m.from_user.id, f"✅ Referral reward set to **{points} points**!", parse_mode="Markdown")
    except:
        bot.send_message(m.from_user.id, "❌ Invalid number format!")

# =========================
# USER STATISTICS
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 User Statistics" and is_admin(m.from_user.id))
def user_statistics(m):
    total_users = users_col.count_documents({})
    
    if total_users == 0:
        bot.send_message(m.from_user.id, "📊 No users found!")
        return
    
    vip_users = users_col.count_documents({"vip": True})
    free_users = total_users - vip_users
    
    # Aggregate statistics
    pipeline = [
        {"$group": {
            "_id": None,
            "total_points": {"$sum": "$points"},
            "total_refs": {"$sum": "$ref_count"}
        }}
    ]
    stats = list(users_col.aggregate(pipeline))
    stats = stats[0] if stats else {"total_points": 0, "total_refs": 0}
    
    avg_points = stats["total_points"] // total_users if total_users > 0 else 0
    
    # Get all VIP methods
    vip_methods = fs.get("vip")
    total_vip_methods = len(vip_methods)
    
    # Users with most points
    top_users = list(users_col.find().sort("points", -1).limit(5))
    
    stats_msg = f"📊 **USER STATISTICS**\n\n"
    stats_msg += f"👥 **Total Users:** {total_users}\n"
    stats_msg += f"💎 **VIP Users:** {vip_users}\n"
    stats_msg += f"🆓 **Free Users:** {free_users}\n\n"
    
    stats_msg += f"💰 **Points Statistics:**\n"
    stats_msg += f"• Total Points: {stats['total_points']:,}\n"
    stats_msg += f"• Average Points: {avg_points:,}\n\n"
    
    stats_msg += f"🎁 **Referral Statistics:**\n"
    stats_msg += f"• Total Referrals: {stats['total_refs']:,}\n"
    stats_msg += f"• Ref Reward: {get_config().get('ref_reward', 5)} pts\n\n"
    
    stats_msg += f"📚 **Content Statistics:**\n"
    stats_msg += f"• Available VIP Methods: {total_vip_methods}\n\n"
    
    stats_msg += f"🏆 **Top 5 Users by Points:**\n"
    for i, data in enumerate(top_users, 1):
        username = data.get("username", "Unknown")
        points = data.get("points", 0)
        stats_msg += f"{i}. {username} (ID: `{data['uid']}`) - {points} pts\n"
    
    bot.send_message(m.from_user.id, stats_msg, parse_mode="Markdown")
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📋 View All Users", callback_data="view_all_users"))
    kb.add(InlineKeyboardButton("💎 View VIP Users", callback_data="view_vip_users"))
    kb.add(InlineKeyboardButton("🆓 View Free Users", callback_data="view_free_users"))
    bot.send_message(m.from_user.id, "Select user list to view:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["view_all_users", "view_vip_users", "view_free_users"])
def view_users_list(c):
    user_type = c.data.replace("view_", "").replace("_users", "")
    
    filter_dict = {}
    if user_type == "vip":
        filter_dict = {"vip": True}
        title = "VIP USERS"
    elif user_type == "free":
        filter_dict = {"vip": False}
        title = "FREE USERS"
    else:
        title = "ALL USERS"
    
    filtered_users = list(users_col.find(filter_dict).limit(50))
    
    if not filtered_users:
        bot.edit_message_text(f"📋 No {title.lower()} found!", c.from_user.id, c.message.message_id)
        return
    
    user_list = f"📋 **{title}**\n\nTotal: {users_col.count_documents(filter_dict)}\n\n"
    
    for data in filtered_users:
        username = data.get("username", "No username")
        points = data.get("points", 0)
        vip = "💎" if data.get("vip", False) else "🆓"
        purchased = len(data.get("purchased_methods", []))
        refs = data.get("ref_count", 0)
        
        user_list += f"{vip} **{username}**\n"
        user_list += f"   ID: `{data['uid']}`\n"
        user_list += f"   Points: {points} | Methods: {purchased} | Refs: {refs}\n\n"
    
    bot.edit_message_text(user_list, c.from_user.id, c.message.message_id, parse_mode="Markdown")
    bot.answer_callback_query(c.id)

# =========================
# SET PURCHASE MESSAGE
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 Set Purchase Message" and is_admin(m.from_user.id))
def set_purchase_msg(m):
    msg = bot.send_message(m.from_user.id, "Send purchase message:")
    bot.register_next_step_handler(msg, save_purchase_msg)

def save_purchase_msg(m):
    update_config("purchase_msg", m.text)
    bot.send_message(m.from_user.id, "✅ Purchase message updated!")

# =========================
# ADD VIP USER
# =========================
@bot.message_handler(func=lambda m: m.text == "👑 Add VIP User" and is_admin(m.from_user.id))
def add_vip_start(m):
    msg = bot.send_message(m.from_user.id, "📝 Send user ID or @username to add VIP:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, add_vip_process)

def add_vip_process(m):
    user_input = m.text.strip()
    user_id = None
    
    if user_input.startswith('@'):
        username = user_input.replace('@', '')
        try:
            chat = bot.get_chat(f"@{username}")
            user_id = chat.id
        except:
            bot.send_message(m.from_user.id, f"❌ Could not find user {user_input}")
            return
    else:
        try:
            user_id = int(user_input)
        except:
            bot.send_message(m.from_user.id, "❌ Invalid user ID format")
            return
    
    try:
        user = User(user_id)
        if user.is_vip():
            bot.send_message(m.from_user.id, f"⚠️ User `{user_id}` is already VIP!", parse_mode="Markdown")
            return
        
        user.make_vip()
        bot.send_message(m.from_user.id, f"✅ User `{user_id}` upgraded to VIP!", parse_mode="Markdown")
        
        try:
            bot.send_message(user_id, "🎉 **Congratulations!**\n\nYou have been upgraded to **VIP**!", parse_mode="Markdown")
        except:
            pass
    
    except Exception as e:
        bot.send_message(m.from_user.id, f"❌ Error: {str(e)}")

# =========================
# REMOVE VIP USER
# =========================
@bot.message_handler(func=lambda m: m.text == "👑 Remove VIP User" and is_admin(m.from_user.id))
def remove_vip_start(m):
    msg = bot.send_message(m.from_user.id, "📝 Send user ID or @username to remove VIP:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, remove_vip_process)

def remove_vip_process(m):
    user_input = m.text.strip()
    user_id = None
    
    if user_input.startswith('@'):
        username = user_input.replace('@', '')
        try:
            chat = bot.get_chat(f"@{username}")
            user_id = chat.id
        except:
            bot.send_message(m.from_user.id, f"❌ Could not find user {user_input}")
            return
    else:
        try:
            user_id = int(user_input)
        except:
            bot.send_message(m.from_user.id, "❌ Invalid user ID format")
            return
    
    try:
        user = User(user_id)
        if not user.is_vip():
            bot.send_message(m.from_user.id, f"⚠️ User `{user_id}` is not VIP!", parse_mode="Markdown")
            return
        
        user.remove_vip()
        bot.send_message(m.from_user.id, f"✅ VIP removed from user `{user_id}`!", parse_mode="Markdown")
        
        try:
            bot.send_message(user_id, "⚠️ **VIP Status Removed**\n\nYour VIP membership has been removed.", parse_mode="Markdown")
        except:
            pass
    
    except Exception as e:
        bot.send_message(m.from_user.id, f"❌ Error: {str(e)}")

# =========================
# VIP / WELCOME SETTINGS
# =========================
@bot.message_handler(func=lambda m: m.text == "⭐ Set VIP Message" and is_admin(m.from_user.id))
def set_vip(m):
    msg = bot.send_message(m.from_user.id, "Send VIP message:")
    bot.register_next_step_handler(msg, save_vip)

def save_vip(m):
    update_config("vip_msg", m.text)
    bot.send_message(m.from_user.id, "✅ VIP message updated!")

@bot.message_handler(func=lambda m: m.text == "🏠 Set Welcome" and is_admin(m.from_user.id))
def set_wel(m):
    msg = bot.send_message(m.from_user.id, "Send welcome message:")
    bot.register_next_step_handler(msg, save_wel)

def save_wel(m):
    update_config("welcome", m.text)
    bot.send_message(m.from_user.id, "✅ Welcome message updated!")

# =========================
# FORCE JOIN MANAGEMENT
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ Add Force Join" and is_admin(m.from_user.id))
def add_force(m):
    msg = bot.send_message(m.from_user.id, "Send @channel:")
    bot.register_next_step_handler(msg, save_force)

def save_force(m):
    cfg = get_config()
    channels = cfg.get("force_channels", [])
    if m.text not in channels:
        channels.append(m.text)
        update_config("force_channels", channels)
        bot.send_message(m.from_user.id, "✅ Added")
    else:
        bot.send_message(m.from_user.id, "Already exists")

@bot.message_handler(func=lambda m: m.text == "➖ Remove Force Join" and is_admin(m.from_user.id))
def remove_force(m):
    msg = bot.send_message(m.from_user.id, "Send channel:")
    bot.register_next_step_handler(msg, rem_force)

def rem_force(m):
    cfg = get_config()
    channels = cfg.get("force_channels", [])
    if m.text in channels:
        channels.remove(m.text)
        update_config("force_channels", channels)
        bot.send_message(m.from_user.id, "Removed")
    else:
        bot.send_message(m.from_user.id, "Not found")

# =========================
# UPLOAD SYSTEM
# =========================
def start_upload(uid, cat):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("/done", "/cancel")
    
    msg = bot.send_message(uid, f"Upload files to {cat}", reply_markup=kb)
    bot.register_next_step_handler(msg, lambda m: upload_step(m, cat, uid, []))

def upload_step(m, cat, uid, files):
    if m.text == "/cancel":
        bot.send_message(uid, "❌ Cancelled", reply_markup=admin_menu())
        return
    
    if m.text == "/done":
        if not files:
            bot.send_message(uid, "No files")
            return
        
        msg = bot.send_message(uid, "Folder name:")
        bot.register_next_step_handler(msg, lambda m2: upload_name(m2, cat, files))
        return
    
    if m.content_type in ["document", "photo", "video"]:
        files.append({"chat": m.chat.id, "msg": m.message_id, "type": m.content_type})
        bot.send_message(uid, f"Saved {len(files)}")
    
    bot.register_next_step_handler(m, lambda m2: upload_step(m2, cat, uid, files))

def upload_name(m, cat, files):
    name = m.text
    msg = bot.send_message(m.from_user.id, "Price:")
    bot.register_next_step_handler(msg, lambda m2: upload_save(m2, cat, name, files))

def upload_save(m, cat, name, files):
    try:
        price = int(m.text)
        fs.add(cat, name, files, price)
        bot.send_message(m.from_user.id, "✅ Uploaded", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "Invalid price")

@bot.message_handler(func=lambda m: m.text == "📦 Upload FREE" and is_admin(m.from_user.id))
def up1(m): start_upload(m.from_user.id, "free")

@bot.message_handler(func=lambda m: m.text == "💎 Upload VIP" and is_admin(m.from_user.id))
def up2(m): start_upload(m.from_user.id, "vip")

@bot.message_handler(func=lambda m: m.text == "📱 Upload APPS" and is_admin(m.from_user.id))
def up3(m): start_upload(m.from_user.id, "apps")

# =========================
# DELETE SYSTEM
# =========================
@bot.message_handler(func=lambda m: m.text == "🗑 Delete Folder" and is_admin(m.from_user.id))
def del_start(m):
    kb = InlineKeyboardMarkup()
    for c in ["free", "vip", "apps"]:
        kb.add(InlineKeyboardButton(c, callback_data=f"del|{c}"))
    bot.send_message(m.from_user.id, "Select category", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("del|"))
def del_list(c):
    cat = c.data.split("|")[1]
    data = fs.get(cat)
    
    kb = InlineKeyboardMarkup()
    for name in data:
        kb.add(InlineKeyboardButton(name, callback_data=f"delf|{cat}|{name}"))
    
    bot.edit_message_text("Select folder", c.from_user.id, c.message.id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("delf|"))
def del_final(c):
    _, cat, name = c.data.split("|")
    fs.delete(cat, name)
    bot.answer_callback_query(c.id, "Deleted")
    bot.edit_message_text("Done", c.from_user.id, c.message.id)

# =========================
# EDIT PRICE
# =========================
@bot.message_handler(func=lambda m: m.text == "✏️ Edit Folder Price" and is_admin(m.from_user.id))
def edit_start(m):
    msg = bot.send_message(m.from_user.id, "Category (free/vip/apps):")
    bot.register_next_step_handler(msg, edit2)

def edit2(m):
    cat = m.text.strip().lower()
    if cat not in ["free", "vip", "apps"]:
        bot.send_message(m.from_user.id, "Invalid category!")
        return
    msg = bot.send_message(m.from_user.id, "Folder name:")
    bot.register_next_step_handler(msg, lambda m2: edit3(m2, cat))

def edit3(m, cat):
    name = m.text
    msg = bot.send_message(m.from_user.id, "New price:")
    bot.register_next_step_handler(msg, lambda m2: edit4(m2, cat, name))

def edit4(m, cat, name):
    try:
        fs.edit(cat, name, int(m.text))
        bot.send_message(m.from_user.id, "✅ Price updated")
    except:
        bot.send_message(m.from_user.id, "❌ Error")

# =========================
# GENERATE CODES
# =========================
@bot.message_handler(func=lambda m: m.text == "🏆 Generate Codes" and is_admin(m.from_user.id))
def code1(m):
    msg = bot.send_message(m.from_user.id, "Points per code:")
    bot.register_next_step_handler(msg, code2)

def code2(m):
    try:
        pts = int(m.text)
        msg = bot.send_message(m.from_user.id, "How many codes?")
        bot.register_next_step_handler(msg, lambda m2: code3(m2, pts))
    except:
        bot.send_message(m.from_user.id, "Invalid points")

def code3(m, pts):
    try:
        count = int(m.text)
        res = codesys.generate(pts, count)
        codes_list = "\n".join(res)
        bot.send_message(m.from_user.id, f"✅ **Generated {count} codes!**\n\n```\n{codes_list}\n```", parse_mode="Markdown")
    except:
        bot.send_message(m.from_user.id, "Invalid count")

# =========================
# VIEW CODES
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 View Codes" and is_admin(m.from_user.id))
def view_codes(m):
    codes = codesys.get_all_codes()
    
    if not codes:
        bot.send_message(m.from_user.id, "📊 No codes generated yet!")
        return
    
    used_codes = []
    unused_codes = []
    
    for code_data in codes:
        code = code_data["code"]
        if code_data.get("used", False):
            used_by = code_data.get("used_by", "Unknown")
            used_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(code_data.get("used_at", 0)))
            used_codes.append(f"❌ {code} - {code_data['points']} pts - Used by: {used_by}")
        else:
            unused_codes.append(f"✅ {code} - {code_data['points']} pts")
    
    message = "📊 **Code Statistics**\n\n"
    message += f"**Total Codes:** {len(codes)}\n"
    message += f"**Used:** {len(used_codes)}\n"
    message += f"**Unused:** {len(unused_codes)}\n\n"
    
    if unused_codes:
        message += "**Unused Codes:**\n" + "\n".join(unused_codes[:20])
    
    if len(message) > 4000:
        bot.send_message(m.from_user.id, "📊 Code Statistics")
        if unused_codes:
            bot.send_message(m.from_user.id, "✅ **Unused Codes:**\n" + "\n".join(unused_codes[:50]))
    else:
        bot.send_message(m.from_user.id, message, parse_mode="Markdown")

# =========================
# BROADCAST
# =========================
@bot.message_handler(func=lambda m: m.text == "📤 Broadcast" and is_admin(m.from_user.id))
def bc_start(m):
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("📢 All Users", callback_data="bc|all"),
        InlineKeyboardButton("💎 VIP Users", callback_data="bc|vip"),
        InlineKeyboardButton("🆓 Free Users", callback_data="bc|free")
    )
    bot.send_message(m.from_user.id, "📡 Select target users:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("bc|"))
def bc_pick(c):
    t = c.data.split("|")[1]
    msg = bot.send_message(c.from_user.id, "📝 Send your broadcast message:")
    bot.register_next_step_handler(msg, lambda m: bc_send(m, t))

def bc_send(m, target):
    filter_dict = {}
    if target == "vip":
        filter_dict = {"vip": True}
    elif target == "free":
        filter_dict = {"vip": False}
    
    users = list(users_col.find(filter_dict))
    sent = 0
    failed = 0
    
    for user_data in users:
        uid = int(user_data["uid"])
        try:
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
        time.sleep(0.1)
    
    bot.send_message(ADMIN_ID, f"✅ Broadcast completed!\n\n📤 Sent: {sent}\n❌ Failed: {failed}\n🎯 Target: {target.upper()}")

# =========================
# ZEDOX BOT - PART 3
# User Panel + Start + Folders + Redeem + Referral + Buy Methods
# =========================

def main_menu(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    
    kb.row("📂 FREE METHODS", "💎 VIP METHODS")
    kb.row("📦 PREMIUM APPS")
    
    kb.row("💰 POINTS", "⭐ GET VIP")
    kb.row("🎁 REFERRAL", "👤 ACCOUNT")
    kb.row("📚 MY METHODS", "💎 GET POINTS")
    
    kb.row("🆔 CHAT ID", "🏆 REDEEM")
    
    if uid == ADMIN_ID:
        kb.row("⚙️ ADMIN PANEL")
    
    return kb

@bot.message_handler(commands=["start"])
def start_cmd(m):
    uid = m.from_user.id
    args = m.text.split()
    
    user = User(uid)
    
    if m.from_user.username:
        user.update_username(m.from_user.username)
    
    # Handle referral
    if len(args) > 1:
        ref_uid = args[1]
        if ref_uid != str(uid):
            # Check if referrer exists
            ref_user = users_col.find_one({"uid": ref_uid})
            if ref_user and not user.get_ref():
                if user.set_ref(ref_uid):
                    ref_reward = get_config().get("ref_reward", 5)
                    User(ref_uid).add_points(ref_reward)
                    
                    # Notify referrer
                    try:
                        bot.send_message(
                            int(ref_uid),
                            f"🎉 **New Referral!**\n\nSomeone joined using your link!\n➕ +{ref_reward} points added to your balance!",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
    
    if force_block(uid):
        return
    
    cfg = get_config()
    bot.send_message(uid, cfg.get("welcome", "Welcome!"), reply_markup=main_menu(uid))

@bot.message_handler(func=lambda m: m.text in ["📂 FREE METHODS", "💎 VIP METHODS", "📦 PREMIUM APPS"])
def show_folders(m):
    uid = m.from_user.id
    
    if force_block(uid):
        return
    
    mapping = {
        "📂 FREE METHODS": "free",
        "💎 VIP METHODS": "vip",
        "📦 PREMIUM APPS": "apps"
    }
    
    cat = mapping.get(m.text)
    folders = fs.get(cat)
    
    if not folders:
        bot.send_message(uid, f"📂 {m.text}\n\nNo folders available!")
        return
    
    bot.send_message(uid, f"📂 {m.text}\n\nSelect a folder:", reply_markup=get_kb(cat, 0))

@bot.callback_query_handler(func=lambda c: c.data.startswith("page|"))
def page_handler(c):
    _, cat, page = c.data.split("|")
    try:
        bot.edit_message_reply_markup(c.from_user.id, c.message.message_id, reply_markup=get_kb(cat, int(page)))
    except:
        bot.answer_callback_query(c.id, "Error updating page")

@bot.callback_query_handler(func=lambda c: c.data.startswith("open|"))
def open_folder(c):
    uid = c.from_user.id
    user = User(uid)
    
    try:
        _, cat, name = c.data.split("|")
    except:
        bot.answer_callback_query(c.id, "Invalid folder")
        return
    
    folder = fs.get(cat).get(name)
    
    if not folder:
        bot.answer_callback_query(c.id, "❌ Folder not found")
        return
    
    # Check access
    if cat == "vip":
        if user.is_vip() or user.can_access_method(name):
            pass
        else:
            price = folder.get("price", 0)
            kb = InlineKeyboardMarkup(row_width=2)
            if price > 0:
                kb.add(
                    InlineKeyboardButton(f"💰 Buy for {price} pts", callback_data=f"buy|{cat}|{name}|{price}"),
                    InlineKeyboardButton("⭐ GET VIP", callback_data="get_vip")
                )
            else:
                kb.add(InlineKeyboardButton("⭐ GET VIP", callback_data="get_vip"))
            kb.add(InlineKeyboardButton("💎 GET POINTS", callback_data="get_points"))
            kb.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_buy"))
            
            bot.answer_callback_query(c.id, "🔒 VIP method")
            bot.send_message(uid, f"🔒 **VIP Method: {name}**\n\nPrice: **{price} points**\nYour points: **{user.points()}**", 
                           reply_markup=kb, parse_mode="Markdown")
            return
    
    # Send files
    bot.answer_callback_query(c.id, "📤 Sending files...")
    count = 0
    for f in folder["files"]:
        try:
            bot.copy_message(uid, f["chat"], f["msg"])
            count += 1
            time.sleep(0.3)
        except:
            continue
    
    if count > 0:
        bot.send_message(uid, f"✅ Sent {count} file(s)!")

@bot.callback_query_handler(func=lambda c: c.data.startswith("buy|"))
def buy_method(c):
    uid = c.from_user.id
    user = User(uid)
    
    try:
        _, cat, method_name, price = c.data.split("|")
        price = int(price)
    except:
        bot.answer_callback_query(c.id, "Invalid purchase")
        return
    
    if user.is_vip():
        bot.answer_callback_query(c.id, "✅ You are VIP!", show_alert=True)
        open_folder(c)
        return
    
    if user.can_access_method(method_name):
        bot.answer_callback_query(c.id, "✅ You already own this!", show_alert=True)
        open_folder(c)
        return
    
    if user.points() < price:
        bot.answer_callback_query(c.id, f"❌ Need {price} points!", show_alert=True)
        return
    
    if user.purchase_method(method_name, price):
        bot.answer_callback_query(c.id, f"✅ Purchased! {price} pts deducted!", show_alert=True)
        bot.edit_message_text(
            f"✅ **Purchase Successful!**\n\nMethod: **{method_name}**\nPoints: **{user.points()}**",
            uid, c.message.message_id, parse_mode="Markdown"
        )

@bot.callback_query_handler(func=lambda c: c.data == "get_vip")
def get_vip_callback(c):
    uid = c.from_user.id
    user = User(uid)
    
    if user.is_vip():
        bot.answer_callback_query(c.id, "✅ Already VIP!", show_alert=True)
        return
    
    cfg = get_config()
    bot.edit_message_text(f"💎 **VIP Membership**\n\n{cfg.get('vip_msg')}", uid, c.message.message_id, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "get_points")
def get_points_callback(c):
    cfg = get_config()
    bot.edit_message_text(f"💰 **Get Points**\n\n{cfg.get('purchase_msg')}", c.from_user.id, c.message.message_id, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "cancel_buy")
def cancel_buy(c):
    bot.edit_message_text("❌ Cancelled", c.from_user.id, c.message.message_id)

@bot.message_handler(func=lambda m: m.text == "📚 MY METHODS")
def show_purchased_methods(m):
    uid = m.from_user.id
    user = User(uid)
    
    if force_block(uid):
        return
    
    if user.is_vip():
        bot.send_message(uid, "💎 **VIP Member**\n\nYou have access to ALL VIP methods!", parse_mode="Markdown")
        return
    
    purchased = user.purchased_methods()
    
    if not purchased:
        bot.send_message(uid, "📚 **Your Purchased Methods**\n\nNo methods purchased yet.", parse_mode="Markdown")
        return
    
    purchased_list = "\n".join([f"✅ {m}" for m in purchased])
    bot.send_message(uid, f"📚 **Your Purchased Methods**\n\n{purchased_list}", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def user_commands(m):
    uid = m.from_user.id
    user = User(uid)
    
    if m.from_user.username:
        user.update_username(m.from_user.username)
    
    if force_block(uid):
        return
    
    t = m.text
    
    if t == "💰 POINTS":
        bot.send_message(uid, f"💰 Your Points: **{user.points()}**", parse_mode="Markdown")
    
    elif t == "🎁 REFERRAL":
        link = f"https://t.me/{bot.get_me().username}?start={uid}"
        ref_reward = get_config().get("ref_reward", 5)
        bot.send_message(
            uid, 
            f"🎁 **Your Referral Link**\n\n{link}\n\n✨ Each friend gives **{ref_reward} points**!\n📊 Total referrals: **{user.ref_count()}**",
            parse_mode="Markdown"
        )
    
    elif t == "👤 ACCOUNT":
        status = "💎 VIP" if user.is_vip() else "🆓 Free"
        bot.send_message(
            uid,
            f"**👤 Account Info**\n\nStatus: {status}\nPoints: **{user.points()}**\nPurchased: **{len(user.purchased_methods())}**\nReferrals: **{user.ref_count()}**",
            parse_mode="Markdown"
        )
    
    elif t == "🆔 CHAT ID":
        bot.send_message(uid, f"🆔 Your Chat ID: `{uid}`", parse_mode="Markdown")
    
    elif t == "🏆 REDEEM":
        msg = bot.send_message(uid, "🎫 Enter redeem code:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, redeem_code)
    
    elif t == "⭐ GET VIP":
        cfg = get_config()
        bot.send_message(uid, f"💎 **VIP Membership**\n\n{cfg.get('vip_msg')}", parse_mode="Markdown")
    
    elif t == "💎 GET POINTS":
        cfg = get_config()
        bot.send_message(uid, f"💰 **Get Points**\n\n{cfg.get('purchase_msg')}", parse_mode="Markdown")

def redeem_code(m):
    uid = m.from_user.id
    user = User(uid)
    code = m.text.strip().upper()
    
    success, pts, reason = codesys.redeem(code, user)
    
    if success:
        bot.send_message(uid, f"✅ **Success!**\n\n➕ +{pts} points\n💰 Total: **{user.points()}**", parse_mode="Markdown")
    elif reason == "invalid":
        bot.send_message(uid, "❌ **Invalid Code**", parse_mode="Markdown")
    else:
        bot.send_message(uid, "❌ **Code Already Used**", parse_mode="Markdown")

# =========================
# FORCE JOIN RECHECK
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "recheck")
def recheck(c):
    uid = c.from_user.id
    
    if not force_block(uid):
        try:
            bot.edit_message_text("✅ **Access Granted!**", uid, c.message.message_id, parse_mode="Markdown")
        except:
            pass
        bot.send_message(uid, "🎉 Welcome!", reply_markup=main_menu(uid))
    else:
        bot.answer_callback_query(c.id, "❌ Join all channels first", show_alert=True)

# =========================
# RUN BOT
# =========================
def run_bot():
    while True:
        try:
            print("🚀 ZEDOX BOT (MongoDB) RUNNING...")
            print(f"✅ Bot: @{bot.get_me().username}")
            print(f"✅ Admin: {ADMIN_ID}")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_bot()
