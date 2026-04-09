# =========================
# ZEDOX BOT - MONGODB ATLAS FREE TIER VERSION
# Core Setup + MongoDB + User + Codes + Force Join
# =========================

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
import os, time, random, string, threading
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import certifi

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")

# =========================
# MONGODB CONNECTION WITH RETRY (FREE TIER OPTIMIZED)
# =========================
def connect_to_mongo():
    """Connect to MongoDB with retry logic for free tier"""
    max_retries = 5
    retry_delay = 3
    
    for attempt in range(max_retries):
        try:
            # Use certifi for SSL certificate verification (required for Atlas)
            client = MongoClient(
                MONGO_URI,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=5000,  # 5 second timeout
                connectTimeoutMS=10000,
                socketTimeoutMS=30000,
                maxPoolSize=10,  # Free tier limit
                minPoolSize=1,
                maxIdleTimeMS=60000,
                retryWrites=True,
                retryReads=True
            )
            
            # Test connection
            client.admin.command('ping')
            print("✅ Connected to MongoDB Atlas successfully!")
            return client
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            print(f"⚠️ MongoDB connection attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print("❌ Failed to connect to MongoDB after multiple attempts")
                raise e

# Initialize MongoDB connection
try:
    client = connect_to_mongo()
    db = client.zedox_bot
    
    # Collections
    users_col = db.users
    config_col = db.config
    codes_col = db.codes
    files_col = db.files
    
except Exception as e:
    print(f"❌ FATAL: Could not connect to MongoDB: {e}")
    print("Please check your MONGO_URI and network connection")
    exit(1)

# =========================
# INIT DATABASE WITH FREE TIER OPTIMIZATIONS
# =========================
def init_db():
    """Initialize database with free tier optimizations"""
    try:
        # Initialize config if not exists
        if config_col.count_documents({}) == 0:
            default_config = {
                "force_channels": [],
                "vip_msg": "💎 Buy VIP to unlock this! Contact @admin",
                "welcome": "🔥 Welcome to ZEDOX BOT\n\nUse buttons below to navigate!",
                "ref_reward": 5,
                "notify": True,
                "purchase_msg": "💰 Contact @admin to purchase points or VIP!",
                "bot_username": None
            }
            config_col.insert_one(default_config)
            print("✅ Default config created")
        
        # Create indexes for better performance (free tier supports indexes)
        try:
            users_col.create_index("uid", unique=True)
            users_col.create_index("vip")
            users_col.create_index("points")
            print("✅ Users indexes created")
        except Exception as e:
            print(f"⚠️ Users index creation: {e}")
        
        try:
            codes_col.create_index("code", unique=True)
            codes_col.create_index("used")
            print("✅ Codes indexes created")
        except Exception as e:
            print(f"⚠️ Codes index creation: {e}")
        
        try:
            files_col.create_index([("category", 1), ("name", 1)])
            print("✅ Files indexes created")
        except Exception as e:
            print(f"⚠️ Files index creation: {e}")
        
        print("✅ Database initialization complete")
        
    except Exception as e:
        print(f"❌ Database initialization error: {e}")

init_db()

# =========================
# HELPER FUNCTIONS WITH ERROR HANDLING
# =========================
def safe_db_operation(operation, default_return=None, max_retries=3):
    """Wrapper for safe database operations with retry"""
    for attempt in range(max_retries):
        try:
            return operation()
        except Exception as e:
            print(f"DB operation failed (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                return default_return

def get_config():
    """Get config with error handling"""
    try:
        return config_col.find_one({}) or {}
    except Exception as e:
        print(f"Error getting config: {e}")
        return {}

def update_config(key, value):
    """Update config with error handling"""
    try:
        config_col.update_one({}, {"$set": {key: value}}, upsert=True)
        return True
    except Exception as e:
        print(f"Error updating config: {e}")
        return False

# =========================
# USER CLASS (MONGODB WITH FREE TIER OPTIMIZATIONS)
# =========================
class User:
    def __init__(self, uid):
        self.uid = str(uid)
        self.data = self._load_user()
        
    def _load_user(self):
        """Load user with retry logic"""
        try:
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
                    "joined_at": time.time(),
                    "last_active": time.time()
                }
                users_col.insert_one(user_data)
            
            return user_data
        except Exception as e:
            print(f"Error loading user {self.uid}: {e}")
            # Return minimal data structure to prevent crashes
            return {
                "uid": self.uid,
                "points": 0,
                "vip": False,
                "ref": None,
                "purchased_methods": [],
                "used_codes": [],
                "username": None,
                "ref_count": 0
            }

    def _update_field(self, operation):
        """Generic field update with error handling"""
        try:
            users_col.update_one({"uid": self.uid}, operation)
            return True
        except Exception as e:
            print(f"Error updating user {self.uid}: {e}")
            return False

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
            if self._update_field({"$set": {"username": username, "last_active": time.time()}}):
                self.data["username"] = username

    def add_points(self, p):
        if self._update_field({"$inc": {"points": p}, "$set": {"last_active": time.time()}}):
            self.data["points"] = self.data.get("points", 0) + p

    def make_vip(self):
        if self._update_field({"$set": {"vip": True, "last_active": time.time()}}):
            self.data["vip"] = True
    
    def remove_vip(self):
        if self._update_field({"$set": {"vip": False, "last_active": time.time()}}):
            self.data["vip"] = False
    
    def purchase_method(self, method_name, price):
        if self.points() >= price:
            self.add_points(-price)
            if self._update_field({"$addToSet": {"purchased_methods": method_name}}):
                if "purchased_methods" not in self.data:
                    self.data["purchased_methods"] = []
                self.data["purchased_methods"].append(method_name)
                return True
        return False
    
    def can_access_method(self, method_name):
        return self.is_vip() or method_name in self.data.get("purchased_methods", [])
    
    def add_used_code(self, code):
        if code not in self.data.get("used_codes", []):
            if self._update_field({"$addToSet": {"used_codes": code}}):
                if "used_codes" not in self.data:
                    self.data["used_codes"] = []
                self.data["used_codes"].append(code)
                return True
        return False
    
    def has_used_code(self, code):
        return code in self.data.get("used_codes", [])
    
    def set_ref(self, ref_uid):
        if not self.data.get("ref") and ref_uid != self.uid:
            if self._update_field({"$set": {"ref": ref_uid, "last_active": time.time()}}):
                self.data["ref"] = ref_uid
                
                # Increment referral count for referrer
                users_col.update_one(
                    {"uid": ref_uid},
                    {"$inc": {"ref_count": 1}, "$set": {"last_active": time.time()}}
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
            try:
                codes_col.insert_one(code_data)
                res.append(code)
            except Exception as e:
                print(f"Error generating code: {e}")
        return res

    def redeem(self, code, user):
        try:
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
        except Exception as e:
            print(f"Error redeeming code: {e}")
            return False, 0, "error"

    def get_code_info(self, code):
        try:
            return codes_col.find_one({"code": code})
        except:
            return None

    def get_all_codes(self):
        try:
            return list(codes_col.find().sort("created_at", -1).limit(100))  # Limit for free tier
        except:
            return []

    def delete_code(self, code):
        try:
            result = codes_col.delete_one({"code": code})
            return result.deleted_count > 0
        except:
            return False

codesys = Codes()

# =========================
# FORCE JOIN (STRICT)
# =========================
def force_block(uid):
    try:
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
                print(f"Force join check error for {ch}: {e}")
                # Don't block if channel check fails
                continue
    except Exception as e:
        print(f"Force block error: {e}")
    
    return False

# =========================
# FILE SYSTEM (MONGODB)
# =========================
class FS:
    def add(self, cat, name, files, price):
        try:
            file_data = {
                "category": cat,
                "name": name,
                "files": files,
                "price": price,
                "created_at": time.time()
            }
            files_col.insert_one(file_data)
            return True
        except Exception as e:
            print(f"Error adding file: {e}")
            return False

    def get(self, cat):
        try:
            files = list(files_col.find({"category": cat}).limit(50))  # Limit for free tier
            result = {}
            for f in files:
                result[f["name"]] = {"files": f["files"], "price": f["price"]}
            return result
        except Exception as e:
            print(f"Error getting files: {e}")
            return {}

    def delete(self, cat, name):
        try:
            result = files_col.delete_one({"category": cat, "name": name})
            return result.deleted_count > 0
        except:
            return False

    def edit(self, cat, name, price):
        try:
            result = files_col.update_one(
                {"category": cat, "name": name},
                {"$set": {"price": price}}
            )
            return result.modified_count > 0
        except:
            return False

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
# ADMIN PANEL FUNCTIONS
# =========================
def is_admin(uid):
    return uid == ADMIN_ID

def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    
    kb.row("📦 Upload FREE", "💎 Upload VIP")
    kb.row("📱 Upload APPS")
    
    kb.row("✏️ Edit Price", "🗑 Delete Folder")
    
    kb.row("👑 Add VIP", "👑 Remove VIP")
    kb.row("🏆 Gen Codes", "📊 View Codes")
    kb.row("📊 Statistics", "📤 Broadcast")
    
    kb.row("⭐ VIP Message", "💰 Purchase Msg")
    kb.row("🏠 Welcome Msg", "🎁 Ref Reward")
    
    kb.row("➕ Force Join", "➖ Remove Force")
    
    kb.row("❌ Exit Admin")
    return kb

@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def admin_panel(m):
    bot.send_message(m.from_user.id, "⚙️ Admin Panel", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "❌ Exit Admin" and is_admin(m.from_user.id))
def exit_admin(m):
    bot.send_message(m.from_user.id, "Exited Admin", reply_markup=main_menu(m.from_user.id))

# =========================
# SET REFERRAL REWARD
# =========================
@bot.message_handler(func=lambda m: m.text == "🎁 Ref Reward" and is_admin(m.from_user.id))
def set_ref_reward_start(m):
    cfg = get_config()
    current = cfg.get("ref_reward", 5)
    msg = bot.send_message(
        m.from_user.id, 
        f"🎁 **Set Referral Reward**\n\nCurrent: **{current} points**\n\nSend new value:",
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
        bot.send_message(m.from_user.id, "❌ Invalid number!")

# =========================
# USER STATISTICS (FREE TIER OPTIMIZED)
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 Statistics" and is_admin(m.from_user.id))
def user_statistics(m):
    try:
        total_users = users_col.count_documents({})
        
        if total_users == 0:
            bot.send_message(m.from_user.id, "📊 No users found!")
            return
        
        vip_users = users_col.count_documents({"vip": True})
        free_users = total_users - vip_users
        
        # Get top users (limited for free tier)
        top_users = list(users_col.find().sort("points", -1).limit(5))
        
        # Get total points (using aggregation with limit for free tier)
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
        
        stats_msg = f"📊 **STATISTICS**\n\n"
        stats_msg += f"👥 Users: **{total_users}**\n"
        stats_msg += f"💎 VIP: **{vip_users}**\n"
        stats_msg += f"🆓 Free: **{free_users}**\n\n"
        stats_msg += f"💰 Total Points: **{stats['total_points']:,}**\n"
        stats_msg += f"📊 Avg Points: **{avg_points:,}**\n"
        stats_msg += f"🎁 Total Refs: **{stats['total_refs']:,}**\n"
        stats_msg += f"💵 Ref Reward: **{get_config().get('ref_reward', 5)}** pts\n\n"
        
        stats_msg += f"🏆 **Top Users:**\n"
        for i, data in enumerate(top_users, 1):
            username = data.get("username", "Unknown")[:15]  # Limit length
            points = data.get("points", 0)
            stats_msg += f"{i}. {username}: {points} pts\n"
        
        bot.send_message(m.from_user.id, stats_msg, parse_mode="Markdown")
        
    except Exception as e:
        bot.send_message(m.from_user.id, f"❌ Error: {str(e)[:100]}")

# =========================
# MESSAGE SETTINGS (SHORTENED NAMES)
# =========================
@bot.message_handler(func=lambda m: m.text == "⭐ VIP Message" and is_admin(m.from_user.id))
def set_vip(m):
    msg = bot.send_message(m.from_user.id, "Send VIP message:")
    bot.register_next_step_handler(msg, lambda x: [update_config("vip_msg", x.text), bot.send_message(m.from_user.id, "✅ Updated!")])

@bot.message_handler(func=lambda m: m.text == "🏠 Welcome Msg" and is_admin(m.from_user.id))
def set_wel(m):
    msg = bot.send_message(m.from_user.id, "Send welcome message:")
    bot.register_next_step_handler(msg, lambda x: [update_config("welcome", x.text), bot.send_message(m.from_user.id, "✅ Updated!")])

@bot.message_handler(func=lambda m: m.text == "💰 Purchase Msg" and is_admin(m.from_user.id))
def set_purchase_msg(m):
    msg = bot.send_message(m.from_user.id, "Send purchase message:")
    bot.register_next_step_handler(msg, lambda x: [update_config("purchase_msg", x.text), bot.send_message(m.from_user.id, "✅ Updated!")])

# =========================
# VIP MANAGEMENT (SHORTENED)
# =========================
@bot.message_handler(func=lambda m: m.text == "👑 Add VIP" and is_admin(m.from_user.id))
def add_vip_start(m):
    msg = bot.send_message(m.from_user.id, "Send user ID or @username:")
    bot.register_next_step_handler(msg, add_vip_process)

def add_vip_process(m):
    user_input = m.text.strip()
    user_id = None
    
    if user_input.startswith('@'):
        try:
            chat = bot.get_chat(user_input)
            user_id = chat.id
        except:
            bot.send_message(m.from_user.id, "❌ User not found")
            return
    else:
        try:
            user_id = int(user_input)
        except:
            bot.send_message(m.from_user.id, "❌ Invalid ID")
            return
    
    user = User(user_id)
    if user.is_vip():
        bot.send_message(m.from_user.id, "⚠️ Already VIP!")
        return
    
    user.make_vip()
    bot.send_message(m.from_user.id, f"✅ User `{user_id}` is now VIP!", parse_mode="Markdown")
    
    try:
        bot.send_message(user_id, "🎉 You are now VIP!")
    except:
        pass

@bot.message_handler(func=lambda m: m.text == "👑 Remove VIP" and is_admin(m.from_user.id))
def remove_vip_start(m):
    msg = bot.send_message(m.from_user.id, "Send user ID or @username:")
    bot.register_next_step_handler(msg, remove_vip_process)

def remove_vip_process(m):
    user_input = m.text.strip()
    user_id = None
    
    if user_input.startswith('@'):
        try:
            chat = bot.get_chat(user_input)
            user_id = chat.id
        except:
            bot.send_message(m.from_user.id, "❌ User not found")
            return
    else:
        try:
            user_id = int(user_input)
        except:
            bot.send_message(m.from_user.id, "❌ Invalid ID")
            return
    
    user = User(user_id)
    if not user.is_vip():
        bot.send_message(m.from_user.id, "⚠️ Not VIP!")
        return
    
    user.remove_vip()
    bot.send_message(m.from_user.id, f"✅ VIP removed from `{user_id}`", parse_mode="Markdown")

# =========================
# FORCE JOIN (SHORTENED)
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ Force Join" and is_admin(m.from_user.id))
def add_force(m):
    msg = bot.send_message(m.from_user.id, "Send @channel:")
    bot.register_next_step_handler(msg, lambda x: save_force(x))

def save_force(m):
    cfg = get_config()
    channels = cfg.get("force_channels", [])
    if m.text not in channels:
        channels.append(m.text)
        update_config("force_channels", channels)
        bot.send_message(m.from_user.id, "✅ Added")

@bot.message_handler(func=lambda m: m.text == "➖ Remove Force" and is_admin(m.from_user.id))
def remove_force(m):
    msg = bot.send_message(m.from_user.id, "Send channel:")
    bot.register_next_step_handler(msg, lambda x: rem_force(x))

def rem_force(m):
    cfg = get_config()
    channels = cfg.get("force_channels", [])
    if m.text in channels:
        channels.remove(m.text)
        update_config("force_channels", channels)
        bot.send_message(m.from_user.id, "✅ Removed")

# =========================
# UPLOAD SYSTEM
# =========================
def start_upload(uid, cat):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("/done", "/cancel")
    msg = bot.send_message(uid, f"Upload files to {cat}\nSend /done when finished", reply_markup=kb)
    bot.register_next_step_handler(msg, lambda m: upload_step(m, cat, uid, []))

def upload_step(m, cat, uid, files):
    if m.text == "/cancel":
        bot.send_message(uid, "❌ Cancelled", reply_markup=admin_menu())
        return
    
    if m.text == "/done":
        if not files:
            bot.send_message(uid, "❌ No files")
            return
        msg = bot.send_message(uid, "Folder name:")
        bot.register_next_step_handler(msg, lambda m2: upload_name(m2, cat, files))
        return
    
    if m.content_type in ["document", "photo", "video"]:
        files.append({"chat": m.chat.id, "msg": m.message_id, "type": m.content_type})
        bot.send_message(uid, f"✅ Saved ({len(files)})")
    
    bot.register_next_step_handler(m, lambda m2: upload_step(m2, cat, uid, files))

def upload_name(m, cat, files):
    name = m.text
    msg = bot.send_message(m.from_user.id, "Price (0 for free):")
    bot.register_next_step_handler(msg, lambda m2: upload_save(m2, cat, name, files))

def upload_save(m, cat, name, files):
    try:
        price = int(m.text)
        fs.add(cat, name, files, price)
        bot.send_message(m.from_user.id, "✅ Uploaded!", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid price")

@bot.message_handler(func=lambda m: m.text == "📦 Upload FREE" and is_admin(m.from_user.id))
def up1(m): start_upload(m.from_user.id, "free")

@bot.message_handler(func=lambda m: m.text == "💎 Upload VIP" and is_admin(m.from_user.id))
def up2(m): start_upload(m.from_user.id, "vip")

@bot.message_handler(func=lambda m: m.text == "📱 Upload APPS" and is_admin(m.from_user.id))
def up3(m): start_upload(m.from_user.id, "apps")

# =========================
# DELETE & EDIT
# =========================
@bot.message_handler(func=lambda m: m.text == "🗑 Delete Folder" and is_admin(m.from_user.id))
def del_start(m):
    kb = InlineKeyboardMarkup()
    for c in ["free", "vip", "apps"]:
        kb.add(InlineKeyboardButton(c, callback_data=f"del|{c}"))
    bot.send_message(m.from_user.id, "Select category:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("del|"))
def del_list(c):
    cat = c.data.split("|")[1]
    data = fs.get(cat)
    kb = InlineKeyboardMarkup()
    for name in data:
        kb.add(InlineKeyboardButton(name, callback_data=f"delf|{cat}|{name}"))
    bot.edit_message_text("Select folder:", c.from_user.id, c.message.id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("delf|"))
def del_final(c):
    _, cat, name = c.data.split("|")
    fs.delete(cat, name)
    bot.answer_callback_query(c.id, "✅ Deleted")
    bot.edit_message_text("✅ Done", c.from_user.id, c.message.id)

@bot.message_handler(func=lambda m: m.text == "✏️ Edit Price" and is_admin(m.from_user.id))
def edit_start(m):
    msg = bot.send_message(m.from_user.id, "Category (free/vip/apps):")
    bot.register_next_step_handler(msg, edit2)

def edit2(m):
    cat = m.text.strip().lower()
    if cat not in ["free", "vip", "apps"]:
        bot.send_message(m.from_user.id, "❌ Invalid!")
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
        bot.send_message(m.from_user.id, "✅ Updated")
    except:
        bot.send_message(m.from_user.id, "❌ Error")

# =========================
# CODES
# =========================
@bot.message_handler(func=lambda m: m.text == "🏆 Gen Codes" and is_admin(m.from_user.id))
def code1(m):
    msg = bot.send_message(m.from_user.id, "Points per code:")
    bot.register_next_step_handler(msg, code2)

def code2(m):
    try:
        pts = int(m.text)
        msg = bot.send_message(m.from_user.id, "How many codes? (max 50)")
        bot.register_next_step_handler(msg, lambda m2: code3(m2, pts))
    except:
        bot.send_message(m.from_user.id, "❌ Invalid")

def code3(m, pts):
    try:
        count = min(int(m.text), 50)  # Limit for free tier
        res = codesys.generate(pts, count)
        codes_list = "\n".join(res)
        bot.send_message(m.from_user.id, f"✅ **{count} codes:**\n```\n{codes_list}\n```", parse_mode="Markdown")
    except:
        bot.send_message(m.from_user.id, "❌ Invalid")

@bot.message_handler(func=lambda m: m.text == "📊 View Codes" and is_admin(m.from_user.id))
def view_codes(m):
    codes = codesys.get_all_codes()
    if not codes:
        bot.send_message(m.from_user.id, "📊 No codes!")
        return
    
    unused = [c for c in codes if not c.get("used")]
    used = [c for c in codes if c.get("used")]
    
    msg = f"📊 **Codes:**\n\nTotal: {len(codes)}\nUnused: {len(unused)}\nUsed: {len(used)}\n\n"
    if unused[:10]:
        msg += "**Recent unused:**\n" + "\n".join([f"✅ {c['code']} ({c['points']} pts)" for c in unused[:10]])
    
    bot.send_message(m.from_user.id, msg, parse_mode="Markdown")

# =========================
# BROADCAST
# =========================
@bot.message_handler(func=lambda m: m.text == "📤 Broadcast" and is_admin(m.from_user.id))
def bc_start(m):
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("All", callback_data="bc|all"),
        InlineKeyboardButton("VIP", callback_data="bc|vip"),
        InlineKeyboardButton("Free", callback_data="bc|free")
    )
    bot.send_message(m.from_user.id, "Select target:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("bc|"))
def bc_pick(c):
    t = c.data.split("|")[1]
    msg = bot.send_message(c.from_user.id, "Send message to broadcast:")
    bot.register_next_step_handler(msg, lambda m: bc_send(m, t))

def bc_send(m, target):
    filter_dict = {"vip": True} if target == "vip" else ({"vip": False} if target == "free" else {})
    
    users = list(users_col.find(filter_dict).limit(200))  # Limit for free tier
    sent = 0
    
    for user in users:
        try:
            uid = int(user["uid"])
            if m.content_type == "text":
                bot.send_message(uid, m.text)
            elif m.content_type == "photo":
                bot.send_photo(uid, m.photo[-1].file_id, caption=m.caption)
            sent += 1
            time.sleep(0.05)  # Rate limit
        except:
            pass
    
    bot.send_message(ADMIN_ID, f"✅ Sent to {sent} users")

# =========================
# MAIN MENU
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

# =========================
# START COMMAND
# =========================
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
            ref_user = users_col.find_one({"uid": ref_uid})
            if ref_user and not user.get_ref():
                if user.set_ref(ref_uid):
                    ref_reward = get_config().get("ref_reward", 5)
                    User(ref_uid).add_points(ref_reward)
                    try:
                        bot.send_message(int(ref_uid), f"🎉 +{ref_reward} points! New referral!")
                    except:
                        pass
    
    if force_block(uid):
        return
    
    cfg = get_config()
    bot.send_message(uid, cfg.get("welcome", "Welcome!"), reply_markup=main_menu(uid))

# =========================
# FOLDER NAVIGATION
# =========================
@bot.message_handler(func=lambda m: m.text in ["📂 FREE METHODS", "💎 VIP METHODS", "📦 PREMIUM APPS"])
def show_folders(m):
    uid = m.from_user.id
    if force_block(uid): return
    
    mapping = {"📂 FREE METHODS": "free", "💎 VIP METHODS": "vip", "📦 PREMIUM APPS": "apps"}
    cat = mapping.get(m.text)
    folders = fs.get(cat)
    
    if not folders:
        bot.send_message(uid, "📂 No folders available!")
        return
    
    bot.send_message(uid, f"📂 {m.text}", reply_markup=get_kb(cat, 0))

@bot.callback_query_handler(func=lambda c: c.data.startswith("page|"))
def page_handler(c):
    _, cat, page = c.data.split("|")
    try:
        bot.edit_message_reply_markup(c.from_user.id, c.message.message_id, reply_markup=get_kb(cat, int(page)))
    except:
        bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("open|"))
def open_folder(c):
    uid = c.from_user.id
    user = User(uid)
    
    try:
        _, cat, name = c.data.split("|")
    except:
        return
    
    folder = fs.get(cat).get(name)
    if not folder:
        bot.answer_callback_query(c.id, "❌ Not found")
        return
    
    # VIP check
    if cat == "vip" and not user.is_vip() and not user.can_access_method(name):
        price = folder.get("price", 0)
        kb = InlineKeyboardMarkup(row_width=2)
        if price > 0:
            kb.add(InlineKeyboardButton(f"💰 Buy ({price} pts)", callback_data=f"buy|{cat}|{name}|{price}"))
        kb.add(InlineKeyboardButton("⭐ Get VIP", callback_data="get_vip"))
        kb.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_buy"))
        
        bot.answer_callback_query(c.id, "🔒 VIP only")
        bot.send_message(uid, f"🔒 **{name}**\nPrice: {price} pts\nYour points: {user.points()}", 
                        reply_markup=kb, parse_mode="Markdown")
        return
    
    # Send files
    bot.answer_callback_query(c.id, "📤 Sending...")
    for f in folder["files"]:
        try:
            bot.copy_message(uid, f["chat"], f["msg"])
            time.sleep(0.3)
        except:
            pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("buy|"))
def buy_method(c):
    uid = c.from_user.id
    user = User(uid)
    
    try:
        _, cat, method_name, price = c.data.split("|")
        price = int(price)
    except:
        return
    
    if user.is_vip() or user.can_access_method(method_name):
        bot.answer_callback_query(c.id, "✅ Already owned!", show_alert=True)
        return
    
    if user.points() < price:
        bot.answer_callback_query(c.id, f"❌ Need {price} points!", show_alert=True)
        return
    
    if user.purchase_method(method_name, price):
        bot.answer_callback_query(c.id, f"✅ Purchased!", show_alert=True)
        bot.edit_message_text(f"✅ **Purchased!**\nMethod: {method_name}\nPoints: {user.points()}", 
                            uid, c.message.message_id, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data in ["get_vip", "get_points", "cancel_buy"])
def misc_callbacks(c):
    if c.data == "cancel_buy":
        bot.edit_message_text("❌ Cancelled", c.from_user.id, c.message.message_id)
    elif c.data == "get_vip":
        cfg = get_config()
        bot.edit_message_text(f"💎 **VIP**\n\n{cfg.get('vip_msg')}", c.from_user.id, c.message.message_id, parse_mode="Markdown")
    elif c.data == "get_points":
        cfg = get_config()
        bot.edit_message_text(f"💰 **Points**\n\n{cfg.get('purchase_msg')}", c.from_user.id, c.message.message_id, parse_mode="Markdown")
    bot.answer_callback_query(c.id)

# =========================
# USER COMMANDS
# =========================
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
        bot.send_message(uid, f"🎁 **Referral**\n\n{link}\n\n+{ref_reward} pts per referral!\nTotal refs: {user.ref_count()}", 
                        parse_mode="Markdown", disable_web_page_preview=True)
    
    elif t == "👤 ACCOUNT":
        status = "💎 VIP" if user.is_vip() else "🆓 Free"
        bot.send_message(uid, f"👤 **Account**\n\nStatus: {status}\nPoints: {user.points()}\nMethods: {len(user.purchased_methods())}\nRefs: {user.ref_count()}", 
                        parse_mode="Markdown")
    
    elif t == "🆔 CHAT ID":
        bot.send_message(uid, f"🆔 `{uid}`", parse_mode="Markdown")
    
    elif t == "📚 MY METHODS":
        if user.is_vip():
            bot.send_message(uid, "💎 **VIP** - All methods unlocked!", parse_mode="Markdown")
        else:
            methods = user.purchased_methods()
            if methods:
                bot.send_message(uid, "📚 **Your Methods:**\n" + "\n".join([f"✅ {m}" for m in methods]), parse_mode="Markdown")
            else:
                bot.send_message(uid, "📚 No methods purchased yet!")
    
    elif t == "⭐ GET VIP":
        cfg = get_config()
        bot.send_message(uid, f"💎 **VIP**\n\n{cfg.get('vip_msg')}", parse_mode="Markdown")
    
    elif t == "💎 GET POINTS":
        cfg = get_config()
        bot.send_message(uid, f"💰 **Get Points**\n\n{cfg.get('purchase_msg')}", parse_mode="Markdown")
    
    elif t == "🏆 REDEEM":
        msg = bot.send_message(uid, "🎫 Enter code:")
        bot.register_next_step_handler(msg, redeem_code)

def redeem_code(m):
    uid = m.from_user.id
    user = User(uid)
    code = m.text.strip().upper()
    
    success, pts, reason = codesys.redeem(code, user)
    
    if success:
        bot.send_message(uid, f"✅ +{pts} points!\nTotal: {user.points()}", parse_mode="Markdown")
    else:
        bot.send_message(uid, "❌ Invalid or used code!")

# =========================
# FORCE JOIN RECHECK
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "recheck")
def recheck(c):
    uid = c.from_user.id
    if not force_block(uid):
        try:
            bot.edit_message_text("✅ Access Granted!", uid, c.message.message_id)
        except:
            pass
        bot.send_message(uid, "🎉 Welcome!", reply_markup=main_menu(uid))
    else:
        bot.answer_callback_query(c.id, "❌ Join all channels!", show_alert=True)

# =========================
# RUN BOT WITH CONNECTION MONITORING
# =========================
def monitor_connection():
    """Monitor MongoDB connection and reconnect if needed"""
    global client, db, users_col, config_col, codes_col, files_col
    
    while True:
        try:
            # Ping MongoDB every 5 minutes
            time.sleep(300)
            client.admin.command('ping')
        except Exception as e:
            print(f"⚠️ MongoDB connection lost: {e}")
            try:
                client = connect_to_mongo()
                db = client.zedox_bot
                users_col = db.users
                config_col = db.config
                codes_col = db.codes
                files_col = db.files
                print("✅ MongoDB reconnected!")
            except Exception as reconnect_error:
                print(f"❌ Reconnection failed: {reconnect_error}")

def run_bot():
    """Run bot with auto-restart"""
    while True:
        try:
            print("🚀 ZEDOX BOT (MongoDB Atlas Free Tier) RUNNING...")
            print(f"✅ Bot: @{bot.get_me().username}")
            print(f"✅ Admin: {ADMIN_ID}")
            
            # Update bot username in config
            update_config("bot_username", bot.get_me().username)
            
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"[BOT ERROR] {e}")
            time.sleep(5)

if __name__ == "__main__":
    # Start connection monitor thread
    threading.Thread(target=monitor_connection, daemon=True).start()
    
    # Start bot
    run_bot()
