# =========================
# ZEDOX BOT - RAILWAY DEPLOYMENT VERSION
# MongoDB + Private Channel Support + Railway Optimized
# =========================

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
import os, time, random, string, threading, logging
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import certifi
from flask import Flask, request

# =========================
# LOGGING SETUP (RAILWAY COMPATIBLE)
# =========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =========================
# ENVIRONMENT VARIABLES
# =========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
MONGO_URI = os.environ.get("MONGO_URI")
PRIVATE_CHANNEL_ID = os.environ.get("PRIVATE_CHANNEL_ID")  # e.g., "-1001234567890"
PORT = int(os.environ.get("PORT", 5000))

if not all([BOT_TOKEN, ADMIN_ID, MONGO_URI]):
    logger.error("Missing required environment variables!")
    exit(1)

# =========================
# FLASK APP FOR HEALTH CHECKS (RAILWAY REQUIREMENT)
# =========================
app = Flask(__name__)

@app.route('/')
def home():
    return "ZEDOX Bot is running!"

@app.route('/health')
def health():
    return {"status": "healthy"}, 200

# =========================
# MONGODB CONNECTION WITH RAILWAY OPTIMIZATIONS
# =========================
def connect_to_mongo():
    """Connect to MongoDB with Railway optimizations"""
    max_retries = 5
    retry_delay = 3
    
    for attempt in range(max_retries):
        try:
            client = MongoClient(
                MONGO_URI,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=30000,
                maxPoolSize=5,  # Railway free tier optimized
                minPoolSize=1,
                maxIdleTimeMS=60000,
                retryWrites=True,
                retryReads=True,
                w='majority'  # Write concern for Atlas
            )
            
            # Test connection
            client.admin.command('ping')
            logger.info("✅ Connected to MongoDB Atlas!")
            return client
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.warning(f"MongoDB connection attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                logger.error("Failed to connect to MongoDB")
                raise e

# Initialize MongoDB
try:
    client = connect_to_mongo()
    db = client.zedox_bot
    
    # Collections
    users_col = db.users
    config_col = db.config
    codes_col = db.codes
    files_col = db.files
    
except Exception as e:
    logger.error(f"FATAL: MongoDB connection error: {e}")
    exit(1)

# =========================
# TELEGRAM BOT SETUP
# =========================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# Store private channel ID
PRIVATE_CHANNEL = PRIVATE_CHANNEL_ID

# =========================
# DATABASE INITIALIZATION
# =========================
def init_db():
    """Initialize database with indexes"""
    try:
        if config_col.count_documents({}) == 0:
            default_config = {
                "force_channels": [],
                "vip_msg": "💎 Contact @admin to buy VIP access!",
                "welcome": "🔥 Welcome to ZEDOX BOT!\n\nUse buttons below to access content.",
                "ref_reward": 5,
                "notify": True,
                "purchase_msg": "💰 Contact @admin to purchase points or VIP!",
                "bot_username": None,
                "private_channel": PRIVATE_CHANNEL
            }
            config_col.insert_one(default_config)
            logger.info("✅ Default config created")
        
        # Create indexes
        users_col.create_index("uid", unique=True)
        users_col.create_index("vip")
        codes_col.create_index("code", unique=True)
        files_col.create_index([("category", 1), ("name", 1)])
        
        logger.info("✅ Database indexes created")
        
    except Exception as e:
        logger.error(f"Database initialization error: {e}")

init_db()

# =========================
# HELPER FUNCTIONS
# =========================
def get_config():
    try:
        return config_col.find_one({}) or {}
    except:
        return {}

def update_config(key, value):
    try:
        config_col.update_one({}, {"$set": {key: value}}, upsert=True)
        return True
    except:
        return False

# =========================
# USER CLASS (RAILWAY OPTIMIZED)
# =========================
class User:
    def __init__(self, uid):
        self.uid = str(uid)
        self.data = self._load_user()
        
    def _load_user(self):
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
            logger.error(f"Error loading user {self.uid}: {e}")
            return {"uid": self.uid, "points": 0, "vip": False}

    def _update_field(self, operation):
        try:
            users_col.update_one({"uid": self.uid}, operation)
            return True
        except:
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
                users_col.update_one(
                    {"uid": ref_uid},
                    {"$inc": {"ref_count": 1}, "$set": {"last_active": time.time()}}
                )
                return True
        return False
    
    def get_ref(self):
        return self.data.get("ref")

# =========================
# CODES SYSTEM
# =========================
class Codes:
    def generate(self, pts, count):
        res = []
        for _ in range(min(count, 50)):  # Limit for free tier
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
            except:
                pass
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
        except:
            return False, 0, "error"

    def get_all_codes(self):
        try:
            return list(codes_col.find().sort("created_at", -1).limit(100))
        except:
            return []

codesys = Codes()

# =========================
# FORCE JOIN
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
            except:
                continue
    except:
        pass
    
    return False

# =========================
# FILE SYSTEM WITH PRIVATE CHANNEL SUPPORT
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
        except:
            return False

    def get(self, cat):
        try:
            files = list(files_col.find({"category": cat}))
            result = {}
            for f in files:
                result[f["name"]] = {"files": f["files"], "price": f["price"]}
            return result
        except:
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
# ADMIN CHECK
# =========================
def is_admin(uid):
    return uid == ADMIN_ID

# =========================
# ADMIN MENU
# =========================
def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📦 Upload FREE", "💎 Upload VIP")
    kb.row("📱 Upload APPS")
    kb.row("✏️ Edit Price", "🗑 Delete")
    kb.row("👑 Add VIP", "👑 Remove VIP")
    kb.row("🏆 Gen Codes", "📊 Codes")
    kb.row("📊 Stats", "📤 Broadcast")
    kb.row("⭐ VIP Msg", "💰 Purchase Msg")
    kb.row("🏠 Welcome", "🎁 Ref Reward")
    kb.row("➕ Force Join", "➖ Remove Force")
    kb.row("📎 Set Channel", "📋 View Files")
    kb.row("❌ Exit Admin")
    return kb

@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def admin_panel(m):
    bot.send_message(m.from_user.id, "⚙️ Admin Panel", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "❌ Exit Admin" and is_admin(m.from_user.id))
def exit_admin(m):
    bot.send_message(m.from_user.id, "Exited Admin", reply_markup=main_menu(m.from_user.id))

# =========================
# SET PRIVATE CHANNEL
# =========================
@bot.message_handler(func=lambda m: m.text == "📎 Set Channel" and is_admin(m.from_user.id))
def set_channel_start(m):
    msg = bot.send_message(
        m.from_user.id,
        "📎 **Set Private Channel**\n\n"
        "Send the channel ID or @username where files are stored.\n\n"
        "Example:\n"
        "• `-1001234567890`\n"
        "• `@mychannel`\n\n"
        "Make sure bot is admin in that channel!",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, save_channel)

def save_channel(m):
    channel_id = m.text.strip()
    
    # Test if bot can access the channel
    try:
        test_msg = bot.send_message(channel_id, "✅ Bot connected to this channel!")
        bot.delete_message(channel_id, test_msg.message_id)
        
        update_config("private_channel", channel_id)
        global PRIVATE_CHANNEL
        PRIVATE_CHANNEL = channel_id
        
        bot.send_message(m.from_user.id, f"✅ Private channel set to: {channel_id}")
    except Exception as e:
        bot.send_message(m.from_user.id, f"❌ Cannot access channel: {str(e)[:100]}")

# =========================
# VIEW STORED FILES
# =========================
@bot.message_handler(func=lambda m: m.text == "📋 View Files" and is_admin(m.from_user.id))
def view_files(m):
    try:
        files = list(files_col.find().limit(50))
        if not files:
            bot.send_message(m.from_user.id, "📋 No files stored!")
            return
        
        msg = "📋 **Stored Files:**\n\n"
        for f in files[:20]:
            msg += f"📁 {f['category']}/{f['name']} - {len(f['files'])} files\n"
        
        bot.send_message(m.from_user.id, msg, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(m.from_user.id, f"❌ Error: {str(e)[:100]}")

# =========================
# REFERRAL REWARD SETTING
# =========================
@bot.message_handler(func=lambda m: m.text == "🎁 Ref Reward" and is_admin(m.from_user.id))
def set_ref_reward_start(m):
    cfg = get_config()
    current = cfg.get("ref_reward", 5)
    msg = bot.send_message(m.from_user.id, f"Current reward: **{current} pts**\n\nSend new value:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_ref_reward)

def save_ref_reward(m):
    try:
        points = int(m.text)
        if points < 0:
            bot.send_message(m.from_user.id, "❌ Points cannot be negative!")
            return
        update_config("ref_reward", points)
        bot.send_message(m.from_user.id, f"✅ Referral reward set to **{points} pts**!", parse_mode="Markdown")
    except:
        bot.send_message(m.from_user.id, "❌ Invalid number!")

# =========================
# STATISTICS
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 Stats" and is_admin(m.from_user.id))
def user_statistics(m):
    try:
        total_users = users_col.count_documents({})
        
        if total_users == 0:
            bot.send_message(m.from_user.id, "📊 No users found!")
            return
        
        vip_users = users_col.count_documents({"vip": True})
        free_users = total_users - vip_users
        
        top_users = list(users_col.find().sort("points", -1).limit(5))
        
        pipeline = [
            {"$group": {
                "_id": None,
                "total_points": {"$sum": "$points"},
                "total_refs": {"$sum": "$ref_count"}
            }}
        ]
        stats = list(users_col.aggregate(pipeline))
        stats = stats[0] if stats else {"total_points": 0, "total_refs": 0}
        
        stats_msg = f"📊 **STATISTICS**\n\n"
        stats_msg += f"👥 Users: **{total_users}**\n"
        stats_msg += f"💎 VIP: **{vip_users}**\n"
        stats_msg += f"🆓 Free: **{free_users}**\n\n"
        stats_msg += f"💰 Total Points: **{stats['total_points']:,}**\n"
        stats_msg += f"🎁 Total Refs: **{stats['total_refs']:,}**\n"
        stats_msg += f"💵 Ref Reward: **{get_config().get('ref_reward', 5)}** pts\n\n"
        
        stats_msg += f"🏆 **Top Users:**\n"
        for i, data in enumerate(top_users, 1):
            username = data.get("username", "Unknown")[:15]
            points = data.get("points", 0)
            stats_msg += f"{i}. {username}: {points} pts\n"
        
        bot.send_message(m.from_user.id, stats_msg, parse_mode="Markdown")
        
    except Exception as e:
        bot.send_message(m.from_user.id, f"❌ Error: {str(e)[:100]}")

# =========================
# MESSAGE SETTINGS
# =========================
@bot.message_handler(func=lambda m: m.text == "⭐ VIP Msg" and is_admin(m.from_user.id))
def set_vip(m):
    msg = bot.send_message(m.from_user.id, "Send VIP message:")
    bot.register_next_step_handler(msg, lambda x: [update_config("vip_msg", x.text), bot.send_message(m.from_user.id, "✅ Updated!")])

@bot.message_handler(func=lambda m: m.text == "🏠 Welcome" and is_admin(m.from_user.id))
def set_wel(m):
    msg = bot.send_message(m.from_user.id, "Send welcome message:")
    bot.register_next_step_handler(msg, lambda x: [update_config("welcome", x.text), bot.send_message(m.from_user.id, "✅ Updated!")])

@bot.message_handler(func=lambda m: m.text == "💰 Purchase Msg" and is_admin(m.from_user.id))
def set_purchase_msg(m):
    msg = bot.send_message(m.from_user.id, "Send purchase message:")
    bot.register_next_step_handler(msg, lambda x: [update_config("purchase_msg", x.text), bot.send_message(m.from_user.id, "✅ Updated!")])

# =========================
# VIP MANAGEMENT
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
# FORCE JOIN
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ Force Join" and is_admin(m.from_user.id))
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

@bot.message_handler(func=lambda m: m.text == "➖ Remove Force" and is_admin(m.from_user.id))
def remove_force(m):
    msg = bot.send_message(m.from_user.id, "Send channel:")
    bot.register_next_step_handler(msg, rem_force)

def rem_force(m):
    cfg = get_config()
    channels = cfg.get("force_channels", [])
    if m.text in channels:
        channels.remove(m.text)
        update_config("force_channels", channels)
        bot.send_message(m.from_user.id, "✅ Removed")

# =========================
# UPLOAD SYSTEM (SUPPORTS ALL FILE TYPES)
# =========================
def start_upload(uid, cat):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("/done", "/cancel")
    
    # Get private channel
    channel = PRIVATE_CHANNEL or get_config().get("private_channel")
    
    if not channel:
        bot.send_message(uid, "❌ No private channel set! Use 📎 Set Channel first.")
        return
    
    msg = bot.send_message(
        uid, 
        f"📤 **Upload to {cat}**\n\n"
        f"Send files (photos, videos, documents, text)\n"
        f"Files will be stored in: {channel}\n\n"
        f"Send /done when finished",
        parse_mode="Markdown",
        reply_markup=kb
    )
    bot.register_next_step_handler(msg, lambda m: upload_step(m, cat, uid, [], channel))

def upload_step(m, cat, uid, files, channel):
    if m.text == "/cancel":
        bot.send_message(uid, "❌ Cancelled", reply_markup=admin_menu())
        return
    
    if m.text == "/done":
        if not files:
            bot.send_message(uid, "❌ No files uploaded!")
            return
        msg = bot.send_message(uid, "📝 Folder name:")
        bot.register_next_step_handler(msg, lambda m2: upload_name(m2, cat, files, channel))
        return
    
    # Forward all types of content to private channel
    try:
        forwarded = None
        if m.content_type == "text":
            forwarded = bot.send_message(channel, m.text)
        elif m.content_type == "photo":
            forwarded = bot.send_photo(channel, m.photo[-1].file_id, caption=m.caption)
        elif m.content_type == "video":
            forwarded = bot.send_video(channel, m.video.file_id, caption=m.caption)
        elif m.content_type == "document":
            forwarded = bot.send_document(channel, m.document.file_id, caption=m.caption)
        elif m.content_type == "audio":
            forwarded = bot.send_audio(channel, m.audio.file_id, caption=m.caption)
        elif m.content_type == "voice":
            forwarded = bot.send_voice(channel, m.voice.file_id)
        elif m.content_type == "animation":
            forwarded = bot.send_animation(channel, m.animation.file_id, caption=m.caption)
        else:
            bot.send_message(uid, f"⚠️ Unsupported type: {m.content_type}")
            bot.register_next_step_handler(m, lambda m2: upload_step(m2, cat, uid, files, channel))
            return
        
        if forwarded:
            files.append({
                "chat": channel,
                "msg": forwarded.message_id,
                "type": m.content_type
            })
            bot.send_message(uid, f"✅ Saved! ({len(files)} files)")
        
    except Exception as e:
        bot.send_message(uid, f"❌ Error: {str(e)[:100]}")
    
    bot.register_next_step_handler(m, lambda m2: upload_step(m2, cat, uid, files, channel))

def upload_name(m, cat, files, channel):
    name = m.text
    msg = bot.send_message(m.from_user.id, "💰 Price (0 for free):")
    bot.register_next_step_handler(msg, lambda m2: upload_save(m2, cat, name, files))

def upload_save(m, cat, name, files):
    try:
        price = int(m.text)
        fs.add(cat, name, files, price)
        bot.send_message(
            m.from_user.id, 
            f"✅ **Uploaded!**\n\n📁 {name}\n📂 {cat}\n📎 {len(files)} files\n💰 {price} points",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
    except:
        bot.send_message(m.from_user.id, "❌ Invalid price!")

@bot.message_handler(func=lambda m: m.text == "📦 Upload FREE" and is_admin(m.from_user.id))
def up1(m): start_upload(m.from_user.id, "free")

@bot.message_handler(func=lambda m: m.text == "💎 Upload VIP" and is_admin(m.from_user.id))
def up2(m): start_upload(m.from_user.id, "vip")

@bot.message_handler(func=lambda m: m.text == "📱 Upload APPS" and is_admin(m.from_user.id))
def up3(m): start_upload(m.from_user.id, "apps")

# =========================
# DELETE & EDIT
# =========================
@bot.message_handler(func=lambda m: m.text == "🗑 Delete" and is_admin(m.from_user.id))
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
        count = min(int(m.text), 50)
        res = codesys.generate(pts, count)
        codes_list = "\n".join(res)
        bot.send_message(m.from_user.id, f"✅ **{count} codes:**\n```\n{codes_list}\n```", parse_mode="Markdown")
    except:
        bot.send_message(m.from_user.id, "❌ Invalid")

@bot.message_handler(func=lambda m: m.text == "📊 Codes" and is_admin(m.from_user.id))
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
    
    users = list(users_col.find(filter_dict).limit(200))
    sent = 0
    
    for user in users:
        try:
            uid = int(user["uid"])
            if m.content_type == "text":
                bot.send_message(uid, m.text)
            elif m.content_type == "photo":
                bot.send_photo(uid, m.photo[-1].file_id, caption=m.caption)
            elif m.content_type == "video":
                bot.send_video(uid, m.video.file_id, caption=m.caption)
            elif m.content_type == "document":
                bot.send_document(uid, m.document.file_id, caption=m.caption)
            sent += 1
            time.sleep(0.05)
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
    welcome_msg = cfg.get("welcome", "Welcome to ZEDOX BOT!")
    
    # Add private channel info for admin
    if uid == ADMIN_ID:
        channel = PRIVATE_CHANNEL or cfg.get("private_channel")
        if not channel:
            welcome_msg += "\n\n⚠️ **Admin:** Please set private channel using 📎 Set Channel"
    
    bot.send_message(uid, welcome_msg, reply_markup=main_menu(uid), parse_mode="Markdown")

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
    
    # Send files from private channel
    bot.answer_callback_query(c.id, "📤 Sending files...")
    
    channel = PRIVATE_CHANNEL or get_config().get("private_channel")
    
    for f in folder["files"]:
        try:
            # Copy from private channel to user
            bot.copy_message(uid, f["chat"], f["msg"])
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"Error sending file: {e}")
            continue
    
    bot.send_message(uid, "✅ All files sent!")

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
# RUN BOT WITH RAILWAY SUPPORT
# =========================
def run_flask():
    """Run Flask app for health checks"""
    app.run(host='0.0.0.0', port=PORT)

def run_bot():
    """Run bot with auto-restart"""
    while True:
        try:
            logger.info("🚀 ZEDOX BOT starting...")
            logger.info(f"✅ Bot: @{bot.get_me().username}")
            logger.info(f"✅ Admin: {ADMIN_ID}")
            
            update_config("bot_username", bot.get_me().username)
            
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logger.error(f"Bot error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    # Start Flask in separate thread for Railway health checks
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Start bot
    run_bot()
