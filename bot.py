# =========================
# ZEDOX BOT - COMPLETE VERSION
# With Fixed Start, Binance Payment, Screenshot Requirement, Optimized Speed
# =========================

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
import os, time, random, string, threading, hashlib, hmac
from pymongo import MongoClient
from datetime import datetime, timedelta
from functools import wraps

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set!")

# =========================
# 🌐 MONGODB SETUP (OPTIMIZED)
# =========================
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable not set!")

client = MongoClient(MONGO_URI, maxPoolSize=50, minPoolSize=10, connectTimeoutMS=5000, socketTimeoutMS=5000)
db = client["zedox_complete"]

# Collections
users_col = db["users"]
folders_col = db["folders"]
codes_col = db["codes"]
config_col = db["config"]
custom_buttons_col = db["custom_buttons"]
admins_col = db["admins"]
payments_col = db["payments"]  # New collection for payment tracking

# Create indexes for speed
users_col.create_index("points")
users_col.create_index("vip")
users_col.create_index("referrals_count")
folders_col.create_index([("cat", 1), ("parent", 1)])
folders_col.create_index("number", unique=True, sparse=True)
payments_col.create_index("user_id")
payments_col.create_index("status")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# Cache for frequently accessed data
_config_cache = None
_config_cache_time = 0
CACHE_TTL = 30

def get_cached_config():
    global _config_cache, _config_cache_time
    now = time.time()
    if _config_cache and (now - _config_cache_time) < CACHE_TTL:
        return _config_cache
    _config_cache = get_config()
    _config_cache_time = now
    return _config_cache

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
# ⚙️ CONFIG SYSTEM (UPDATED WITH BINANCE DETAILS)
# =========================
def get_config():
    cfg = config_col.find_one({"_id": "config"})
    if not cfg:
        cfg = {
            "_id": "config",
            "force_channels": [],
            "custom_buttons": [],
            "vip_msg": "💎 Buy VIP to unlock this!",
            "welcome": "🔥 Welcome to ZEDOX BOT",
            "ref_reward": 5,
            "notify": True,
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
            # NEW: Binance Payment Details
            "binance_coin": "USDT",
            "binance_network": "TRC20",
            "binance_address": "",
            "binance_memo": "",
            "require_screenshot": True,
            "payment_instructions": "📌 **Payment Instructions:**\n\n1️⃣ Send the exact amount to the Binance address below\n2️⃣ Take a screenshot of the payment confirmation\n3️⃣ Send the screenshot here\n4️⃣ Wait for admin confirmation"
        }
        config_col.insert_one(cfg)
    return cfg

def set_config(key, value):
    global _config_cache
    _config_cache = None
    config_col.update_one({"_id": "config"}, {"$set": {key: value}}, upsert=True)

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
    return admins_col.find_one({"_id": uid}) is not None

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
    return True

def remove_admin(uid):
    uid = int(uid) if isinstance(uid, str) else uid
    if uid == ADMIN_ID:
        return False
    result = admins_col.delete_one({"_id": uid})
    return result.deleted_count > 0

def get_all_admins():
    return list(admins_col.find({}))

# =========================
# 👤 USER SYSTEM
# =========================
class User:
    _cache = {}
    _cache_time = {}
    
    def __init__(self, uid):
        self.uid = str(uid)
        
        if uid in self._cache and (time.time() - self._cache_time.get(uid, 0)) < 30:
            self.data = self._cache[uid]
            return
        
        data = users_col.find_one({"_id": self.uid})
        
        if not data:
            data = {
                "_id": self.uid,
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
                "total_points_spent": 0
            }
            users_col.insert_one(data)
        
        self.data = data
        self._cache[uid] = data
        self._cache_time[uid] = time.time()
    
    def save(self):
        users_col.update_one({"_id": self.uid}, {"$set": self.data})
        self._cache[self.uid] = self.data
        self._cache_time[self.uid] = time.time()
    
    def is_vip(self):
        if self.data.get("vip", False):
            expiry = self.data.get("vip_expiry")
            if expiry and expiry < time.time():
                self.data["vip"] = False
                self.data["vip_expiry"] = None
                self.save()
                return False
            return True
        return False
    
    def points(self): 
        return self.data.get("points", 0)
    
    def purchased_methods(self): 
        return self.data.get("purchased_methods", [])
    
    def used_codes(self): 
        return self.data.get("used_codes", [])
    
    def username(self): 
        return self.data.get("username", None)
    
    def update_username(self, username):
        if username != self.data.get("username"):
            self.data["username"] = username
            self.save()
    
    def add_points(self, p):
        self.data["points"] += p
        self.data["total_points_earned"] = self.data.get("total_points_earned", 0) + p
        self.save()
    
    def spend_points(self, p):
        self.data["points"] -= p
        self.data["total_points_spent"] = self.data.get("total_points_spent", 0) + p
        self.save()
    
    def make_vip(self, duration_days=None):
        self.data["vip"] = True
        if duration_days and duration_days > 0:
            self.data["vip_expiry"] = time.time() + (duration_days * 86400)
        else:
            self.data["vip_expiry"] = None
        self.save()
    
    def remove_vip(self):
        self.data["vip"] = False
        self.data["vip_expiry"] = None
        self.save()
    
    def purchase_method(self, method_name, price):
        if self.points() >= price:
            self.spend_points(price)
            if method_name not in self.purchased_methods():
                self.data["purchased_methods"].append(method_name)
                self.save()
            return True
        return False
    
    def can_access_method(self, method_name):
        return self.is_vip() or method_name in self.purchased_methods()
    
    def add_used_code(self, code):
        if code not in self.used_codes():
            self.data["used_codes"].append(code)
            self.save()
            return True
        return False
    
    def has_used_code(self, code):
        return code in self.used_codes()
    
    def add_ref(self):
        self.data["refs"] = self.data.get("refs", 0) + 1
        self.save()
        
        config = get_cached_config()
        required_refs = config.get("referral_vip_count", 50)
        
        if self.data["refs"] >= required_refs and not self.is_vip():
            self.make_vip(config.get("vip_duration_days", 30))
            return True
        return False
    
    def add_ref_bought_vip(self):
        self.data["refs_who_bought_vip"] = self.data.get("refs_who_bought_vip", 0) + 1
        self.save()
        
        config = get_cached_config()
        required_purchases = config.get("referral_purchase_count", 10)
        
        if self.data["refs_who_bought_vip"] >= required_purchases and not self.is_vip():
            self.make_vip(config.get("vip_duration_days", 30))
            return True
        return False
    
    def get_refs_count(self):
        return self.data.get("refs", 0)
    
    def get_refs_bought_vip_count(self):
        return self.data.get("refs_who_bought_vip", 0)

# =========================
# 📦 CONTENT SYSTEM
# =========================
class FS:
    def add(self, cat, name, files, price, parent=None, number=None, text_content=None):
        if number is None:
            config = get_config()
            number = config.get("next_folder_number", 1)
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
        return number
    
    def get(self, cat, parent=None):
        query = {"cat": cat}
        if parent:
            query["parent"] = parent
        else:
            query["parent"] = None
        return list(folders_col.find(query).sort("number", 1))
    
    def get_one(self, cat, name, parent=None):
        query = {"cat": cat, "name": name}
        if parent:
            query["parent"] = parent
        return folders_col.find_one(query)
    
    def get_by_number(self, number):
        return folders_col.find_one({"number": number})
    
    def update_numbers_after_delete(self, deleted_number):
        folders_col.update_many(
            {"number": {"$gt": deleted_number}},
            {"$inc": {"number": -1}}
        )
        config = get_config()
        current_next = config.get("next_folder_number", 1)
        if current_next > deleted_number:
            set_config("next_folder_number", current_next - 1)
    
    def delete_all_subfolders(self, cat, parent_name):
        subfolders = list(folders_col.find({"cat": cat, "parent": parent_name}))
        for sub in subfolders:
            self.delete_all_subfolders(cat, sub["name"])
            folders_col.delete_one({"_id": sub["_id"]})
    
    def delete(self, cat, name, parent=None):
        query = {"cat": cat, "name": name}
        if parent:
            query["parent"] = parent
        else:
            query["parent"] = None
        
        folder = folders_col.find_one(query)
        if not folder:
            return False
        
        number = folder.get("number")
        self.delete_all_subfolders(cat, name)
        folders_col.delete_one(query)
        
        if number:
            self.update_numbers_after_delete(number)
        
        return True
    
    def edit_price(self, cat, name, price, parent=None):
        query = {"cat": cat, "name": name}
        if parent:
            query["parent"] = parent
        folders_col.update_one(query, {"$set": {"price": price}})
    
    def edit_name(self, cat, old, new, parent=None):
        query = {"cat": cat, "name": old}
        if parent:
            query["parent"] = parent
        folders_col.update_one(query, {"$set": {"name": new}})
        folders_col.update_many({"cat": cat, "parent": old}, {"$set": {"parent": new}})
    
    def move_folder(self, number, new_parent):
        folders_col.update_one({"number": number}, {"$set": {"parent": new_parent}})
    
    def edit_content(self, cat, name, content_type, content, parent=None):
        query = {"cat": cat, "name": name}
        if parent:
            query["parent"] = parent
        
        if content_type == "text":
            folders_col.update_one(query, {"$set": {"text_content": content}})
        elif content_type == "files":
            folders_col.update_one(query, {"$set": {"files": content}})
        return True

fs = FS()

# =========================
# 🏆 CODES SYSTEM
# =========================
class Codes:
    def generate(self, pts, count, multi_use=False, expiry_days=None):
        res = []
        expiry = time.time() + (expiry_days * 86400) if expiry_days else None
        
        for _ in range(count):
            code = "ZEDOX" + ''.join(random.choices(string.ascii_uppercase+string.digits, k=8))
            while codes_col.find_one({"_id": code}):
                code = "ZEDOX" + ''.join(random.choices(string.ascii_uppercase+string.digits, k=8))
            
            codes_col.insert_one({
                "_id": code,
                "points": pts,
                "used": False,
                "multi_use": multi_use,
                "used_count": 0,
                "max_uses": 0 if not multi_use else 10,
                "expiry": expiry,
                "created_at": time.time(),
                "used_by_users": []
            })
            res.append(code)
        return res
    
    def redeem(self, code, user):
        code_data = codes_col.find_one({"_id": code})
        
        if not code_data:
            return False, 0, "invalid"
        
        if code_data.get("expiry") and time.time() > code_data["expiry"]:
            return False, 0, "expired"
        
        if not code_data.get("multi_use", False) and code_data.get("used", False):
            return False, 0, "already_used"
        
        if user.uid in code_data.get("used_by_users", []):
            return False, 0, "already_used_by_user"
        
        if code_data.get("multi_use", False):
            used_count = code_data.get("used_count", 0)
            max_uses = code_data.get("max_uses", 10)
            if used_count >= max_uses:
                return False, 0, "max_uses_reached"
        
        pts = code_data["points"]
        user.add_points(pts)
        
        update_data = {
            "$push": {"used_by_users": user.uid},
            "$inc": {"used_count": 1}
        }
        
        if not code_data.get("multi_use", False):
            update_data["$set"] = {"used": True}
        
        codes_col.update_one({"_id": code}, update_data)
        user.add_used_code(code)
        
        return True, pts, "success"
    
    def get_all_codes(self):
        return list(codes_col.find({}).sort("created_at", -1))
    
    def get_stats(self):
        total = codes_col.count_documents({})
        used = codes_col.count_documents({"used": True})
        unused = total - used
        multi_use = codes_col.count_documents({"multi_use": True})
        return total, used, unused, multi_use

codesys = Codes()

# =========================
# 📦 POINTS PACKAGES SYSTEM
# =========================
def get_points_packages():
    packages = config_col.find_one({"_id": "points_packages"})
    if not packages:
        default_packages = {
            "_id": "points_packages",
            "packages": [
                {"points": 100, "price": 5, "currency": "USD", "bonus": 0, "active": True},
                {"points": 250, "price": 10, "currency": "USD", "bonus": 25, "active": True},
                {"points": 550, "price": 20, "currency": "USD", "bonus": 100, "active": True},
                {"points": 1500, "price": 50, "currency": "USD", "bonus": 500, "active": True},
                {"points": 3500, "price": 100, "currency": "USD", "bonus": 1500, "active": True},
                {"points": 10000, "price": 250, "currency": "USD", "bonus": 5000, "active": True}
            ]
        }
        config_col.insert_one(default_packages)
        return default_packages["packages"]
    return packages["packages"]

def save_points_packages(packages):
    config_col.update_one(
        {"_id": "points_packages"},
        {"$set": {"packages": packages}},
        upsert=True
    )

# =========================
# 🚫 FORCE JOIN (ADMIN BYPASS)
# =========================
_force_cache = {}
FORCE_CACHE_TTL = 60

def force_block(uid):
    global _force_cache
    now = time.time()
    
    if uid in _force_cache and (now - _force_cache[uid][1]) < FORCE_CACHE_TTL:
        return _force_cache[uid][0]
    
    # ADMINS BYPASS FORCE JOIN
    if is_admin(uid):
        _force_cache[uid] = (False, now)
        return False
    
    cfg = get_cached_config()
    force_channels = cfg.get("force_channels", [])
    
    if not force_channels:
        _force_cache[uid] = (False, now)
        return False
    
    for ch in force_channels:
        try:
            member = bot.get_chat_member(ch, uid)
            if member.status in ["left", "kicked"]:
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(f"Join {ch}", url=f"https://t.me/{ch.replace('@','')}"))
                kb.add(InlineKeyboardButton("✅ I Joined", callback_data="recheck"))
                bot.send_message(uid, "🚫 **Join all channels first!**", reply_markup=kb, parse_mode="Markdown")
                _force_cache[uid] = (True, now)
                return True
        except Exception as e:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton(f"Join {ch}", url=f"https://t.me/{ch.replace('@','')}"))
            kb.add(InlineKeyboardButton("✅ I Joined", callback_data="recheck"))
            bot.send_message(uid, f"🚫 **Please join {ch} first!**", reply_markup=kb, parse_mode="Markdown")
            _force_cache[uid] = (True, now)
            return True
    
    _force_cache[uid] = (False, now)
    return False

def force_join_handler(func):
    @wraps(func)
    def wrapper(message):
        if force_block(message.from_user.id):
            return
        return func(message)
    return wrapper

# =========================
# 📱 MAIN MENU
# =========================
def main_menu(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    
    kb.row("📂 FREE METHODS", "💎 VIP METHODS")
    kb.row("📦 PREMIUM APPS", "⚡ SERVICES")
    kb.row("💰 POINTS", "⭐ BUY VIP")
    
    custom_btns = get_custom_buttons()
    if custom_btns:
        row = []
        for btn in custom_btns:
            row.append(btn["text"])
            if len(row) == 2:
                kb.row(*row)
                row = []
        if row:
            kb.row(*row)
    
    kb.row("🎁 REFERRAL", "👤 ACCOUNT")
    kb.row("📚 MY METHODS", "💎 GET POINTS")
    kb.row("🆔 CHAT ID", "🏆 REDEEM")
    
    if is_admin(uid):
        kb.row("⚙️ ADMIN PANEL")
    
    return kb

def get_custom_buttons():
    cfg = get_cached_config()
    return cfg.get("custom_buttons", [])

def add_custom_button(button_text, button_type, button_data):
    cfg = get_config()
    buttons = cfg.get("custom_buttons", [])
    buttons.append({
        "text": button_text,
        "type": button_type,
        "data": button_data
    })
    set_config("custom_buttons", buttons)

def remove_custom_button(button_text):
    cfg = get_config()
    buttons = cfg.get("custom_buttons", [])
    buttons = [b for b in buttons if b["text"] != button_text]
    set_config("custom_buttons", buttons)

# =========================
# 🚀 START (FIXED)
# =========================
@bot.message_handler(commands=["start"])
def start_cmd(m):
    if not validate_request(m):
        return
    
    uid = m.from_user.id
    args = m.text.split()
    
    user = User(uid)
    
    if m.from_user.username:
        user.update_username(m.from_user.username)
    
    if len(args) > 1:
        ref_id = args[1]
        
        if ref_id != str(uid) and ref_id.isdigit():
            ref_user_data = users_col.find_one({"_id": ref_id})
            
            if ref_user_data and not user.data.get("ref"):
                try:
                    ref_user = User(ref_id)
                    reward = get_cached_config().get("ref_reward", 5)
                    
                    ref_user.add_points(reward)
                    got_vip = ref_user.add_ref()
                    
                    user.data["ref"] = ref_id
                    user.save()
                    
                    try:
                        vip_msg = ""
                        if got_vip:
                            vip_msg = f"\n\n🎉 **CONGRATULATIONS!** 🎉\nYou've reached {ref_user.get_refs_count()} referrals and got **FREE VIP ACCESS**!"
                        
                        bot.send_message(int(ref_id), 
                            f"👤 **New Referral Alert!**\n\n"
                            f"✨ **@{user.username or user.uid}** just joined using your referral link!\n\n"
                            f"💰 You earned **+{reward} points**!\n"
                            f"📊 Total Referrals: **{ref_user.get_refs_count()}**\n"
                            f"💎 Total Points: **{ref_user.points()}**{vip_msg}",
                            parse_mode="Markdown")
                    except:
                        pass
                except:
                    pass
    
    if force_block(uid):
        return
    
    cfg = get_cached_config()
    welcome_msg = cfg.get("welcome", "Welcome to ZEDOX BOT!")
    
    bot.send_message(uid, f"{welcome_msg}\n\n💰 Your points: **{user.points()}**", reply_markup=main_menu(uid))

# =========================
# 💰 POINTS COMMAND
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 POINTS")
def points_cmd(m):
    uid = m.from_user.id
    user = User(uid)
    
    if force_block(uid):
        return
    
    purchased_count = len(user.purchased_methods())
    ref_count = user.get_refs_count()
    ref_bought_count = user.get_refs_bought_vip_count()
    
    points_msg = f"💰 **YOUR POINTS BALANCE** 💰\n\n"
    points_msg += f"┌ **Points:** `{user.points()}`\n"
    points_msg += f"├ **VIP Status:** {'✅ Active' if user.is_vip() else '❌ Not Active'}\n"
    points_msg += f"├ **Purchased Methods:** `{purchased_count}`\n"
    points_msg += f"├ **Total Referrals:** `{ref_count}`\n"
    points_msg += f"├ **Referrals who bought VIP:** `{ref_bought_count}`\n"
    points_msg += f"├ **Total Earned:** `{user.data.get('total_points_earned', 0)}`\n"
    points_msg += f"└ **Total Spent:** `{user.data.get('total_points_spent', 0)}`\n\n"
    
    points_msg += f"✨ **Ways to Earn Points:**\n"
    points_msg += f"• 🎁 **Referral System:** Share your link\n"
    points_msg += f"• 🏆 **Redeem Codes:** Use coupon codes\n"
    points_msg += f"• 💎 **Purchase:** Click 💎 GET POINTS button\n\n"
    
    points_msg += f"🎯 **Referral Rewards:**\n"
    cfg = get_cached_config()
    points_msg += f"• Invite {cfg.get('referral_vip_count', 50)} users → **FREE VIP**\n"
    points_msg += f"• {cfg.get('referral_purchase_count', 10)} referrals buy VIP → **FREE VIP**\n\n"
    
    points_msg += f"💡 **Use points to:**\n"
    points_msg += f"• Buy individual VIP methods\n"
    points_msg += f"• Access premium content\n"
    points_msg += f"• Redeem special offers"
    
    bot.send_message(uid, points_msg, parse_mode="Markdown")

# =========================
# 💎 GET POINTS (WITH BINANCE PAYMENT)
# =========================
@bot.message_handler(func=lambda m: m.text == "💎 GET POINTS")
def get_points_button(m):
    uid = m.from_user.id
    user = User(uid)
    
    if force_block(uid):
        return
    
    packages = get_points_packages()
    active_packages = [p for p in packages if p.get("active", True)]
    cfg = get_cached_config()
    
    contact_username = cfg.get("contact_username")
    contact_link = cfg.get("contact_link")
    vip_contact = cfg.get("vip_contact")
    
    # Get Binance payment details
    binance_coin = cfg.get("binance_coin", "USDT")
    binance_network = cfg.get("binance_network", "TRC20")
    binance_address = cfg.get("binance_address", "")
    binance_memo = cfg.get("binance_memo", "")
    
    message = f"💰 **GET POINTS** 💰\n\n"
    message += f"✨ **Your Current Balance:** `{user.points()}` points\n\n"
    
    if active_packages:
        message += f"📦 **BUY POINTS PACKAGES:**\n\n"
        for i, pkg in enumerate(active_packages, 1):
            total_points = pkg["points"] + pkg.get("bonus", 0)
            price_display = f"${pkg['price']}"
            
            message += f"💎 **Package {i}:**\n"
            message += f"   • {pkg['points']} points for `{price_display}`\n"
            if pkg.get("bonus", 0) > 0:
                message += f"   • **BONUS:** +{pkg['bonus']} points FREE!\n"
                message += f"   • **Total:** `{total_points}` points\n"
            message += f"   • 💰 **Value:** {price_display}\n\n"
        
        message += f"✨ **How to Purchase Points:**\n"
        message += f"1️⃣ Click the button below to contact admin\n"
        message += f"2️⃣ Send your **User ID**: `{uid}`\n"
        message += f"3️⃣ Mention which package you want\n"
        message += f"4️⃣ Complete payment\n"
        message += f"5️⃣ Get points added instantly!\n\n"
        
        # Binance Payment Details
        if binance_address:
            message += f"💳 **Binance Payment Details:**\n"
            message += f"┌ **Coin:** {binance_coin}\n"
            message += f"├ **Network:** {binance_network}\n"
            message += f"├ **Address:** `{binance_address}`\n"
            if binance_memo:
                message += f"├ **Memo/Tag:** `{binance_memo}`\n"
            message += f"└ **Amount:** Equal to package price\n\n"
            
            if cfg.get("require_screenshot", True):
                message += f"📸 **IMPORTANT:** Send payment screenshot after payment!\n\n"
        
        message += f"💳 **Other Payment Methods:**\n"
        for method in cfg.get("payment_methods", ["💳 Binance", "💵 USDT"]):
            if "Binance" not in method:
                message += f"• {method}\n"
        message += f"\n"
        
        message += f"🎁 **Special Offers:**\n"
        message += f"• First purchase: **10% BONUS**\n"
        message += f"• Referral: Earn points when friends buy\n"
        message += f"• Bulk orders: Contact for custom pricing\n\n"
        
        message += f"⚡ **Fast delivery within 5-10 minutes after payment confirmation!**\n\n"
    else:
        message += f"❌ No points packages available right now.\n\n"
    
    message += f"🎁 **FREE WAYS TO EARN POINTS:**\n"
    message += f"• **Referral System:** Share your referral link\n"
    message += f"• **Redeem Codes:** Use coupon codes from admin\n"
    message += f"• **Complete Tasks:** Check announcements\n\n"
    
    message += f"💡 **Tip:** More points = More VIP methods!"
    
    kb = InlineKeyboardMarkup(row_width=2)
    
    if contact_link:
        kb.add(InlineKeyboardButton("📞 Contact Admin", url=contact_link))
    elif contact_username:
        kb.add(InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{contact_username.replace('@', '')}"))
    else:
        try:
            admin_chat = bot.get_chat(ADMIN_ID)
            if admin_chat.username:
                kb.add(InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{admin_chat.username}"))
        except:
            pass
    
    if active_packages:
        kb.add(InlineKeyboardButton("💰 Check Balance", callback_data="check_balance"))
    kb.add(InlineKeyboardButton("🎁 Referral Link", callback_data="get_referral"))
    kb.add(InlineKeyboardButton("⭐ VIP Info", callback_data="get_vip_info"))
    
    bot.send_message(uid, message, reply_markup=kb, parse_mode="Markdown")

# =========================
# 📂 SHOW FOLDERS
# =========================
def get_folders_kb(cat, parent=None, page=0, items_per_page=10):
    data = fs.get(cat, parent)
    
    start = page * items_per_page
    end = start + items_per_page
    page_items = data[start:end]
    
    kb = InlineKeyboardMarkup(row_width=2)
    
    for item in page_items:
        name = item["name"]
        price = item.get("price", 0)
        number = item.get("number", "?")
        
        has_subfolders = len(fs.get(cat, name)) > 0
        icon = "📁" if has_subfolders else "📄"
        
        text = f"{icon} [{number}] {name}"
        if price > 0:
            text += f" [{price} pts]"
        
        kb.add(InlineKeyboardButton(text, callback_data=f"open|{cat}|{name}|{parent or ''}"))
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"page|{cat}|{page-1}|{parent or ''}"))
    if end < len(data):
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"page|{cat}|{page+1}|{parent or ''}"))
    
    if nav_buttons:
        kb.row(*nav_buttons)
    
    if parent:
        kb.add(InlineKeyboardButton("🔙 Back", callback_data=f"back|{cat}|{parent}"))
    
    return kb

@bot.message_handler(func=lambda m: m.text in [
    "📂 FREE METHODS",
    "💎 VIP METHODS",
    "📦 PREMIUM APPS",
    "⚡ SERVICES"
])
def show_category(m):
    uid = m.from_user.id
    
    if force_block(uid):
        return
    
    mapping = {
        "📂 FREE METHODS": "free",
        "💎 VIP METHODS": "vip",
        "📦 PREMIUM APPS": "apps",
        "⚡ SERVICES": "services"
    }
    
    cat = mapping.get(m.text)
    
    if cat is None:
        bot.send_message(uid, "❌ Invalid category")
        return
    
    data = fs.get(cat)
    
    if not data:
        bot.send_message(uid, f"📂 {m.text}\n\nNo folders available in this category yet!")
        return
    
    bot.send_message(uid, f"📂 {m.text}\n\nSelect a folder:", reply_markup=get_folders_kb(cat))

# =========================
# 📂 OPEN FOLDER
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("open|"))
def open_folder(c):
    uid = c.from_user.id
    user = User(uid)
    
    parts = c.data.split("|")
    cat = parts[1]
    name = parts[2]
    parent = parts[3] if len(parts) > 3 and parts[3] else None
    
    folder = fs.get_one(cat, name, parent if parent else None)
    
    if not folder:
        bot.answer_callback_query(c.id, "❌ Folder not found")
        return
    
    subfolders = fs.get(cat, name)
    if subfolders:
        bot.edit_message_reply_markup(
            uid,
            c.message.message_id,
            reply_markup=get_folders_kb(cat, name)
        )
        bot.answer_callback_query(c.id)
        return
    
    if cat == "services":
        price = folder.get("price", 0)
        
        if price > 0 and not user.is_vip():
            if user.points() < price:
                bot.answer_callback_query(c.id, f"❌ Need {price} points! You have {user.points()}", show_alert=True)
                return
            user.spend_points(price)
            bot.answer_callback_query(c.id, f"✅ {price} points deducted!")
        
        service_msg = folder.get("service_msg", "✅ Service activated!")
        bot.send_message(uid, service_msg, parse_mode="Markdown")
        return
    
    text_content = folder.get("text_content")
    if text_content and not folder.get("files"):
        price = folder.get("price", 0)
        
        if cat == "vip":
            if user.is_vip():
                pass
            elif user.can_access_method(name):
                pass
            else:
                if price > 0:
                    kb = InlineKeyboardMarkup(row_width=2)
                    kb.add(
                        InlineKeyboardButton(f"💰 Buy for {price} pts", callback_data=f"buy|{cat}|{name}|{price}"),
                        InlineKeyboardButton("⭐ BUY VIP", callback_data="get_vip"),
                        InlineKeyboardButton("💎 GET POINTS", callback_data="get_points")
                    )
                    kb.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_buy"))
                    bot.answer_callback_query(c.id, "🔒 This is a VIP method")
                    bot.send_message(uid, f"🔒 **VIP Method: {name}**\n\nPrice: **{price} points**\nYour points: **{user.points()}**\n\nChoose an option:", reply_markup=kb, parse_mode="Markdown")
                else:
                    kb = InlineKeyboardMarkup(row_width=2)
                    kb.add(
                        InlineKeyboardButton("⭐ BUY VIP", callback_data="get_vip"),
                        InlineKeyboardButton("💎 GET POINTS", callback_data="get_points")
                    )
                    bot.answer_callback_query(c.id, "🔒 This is a VIP method")
                    bot.send_message(uid, f"🔒 **VIP Method: {name}**\n\nThis is a VIP method.\n\nChoose an option to access it:", reply_markup=kb, parse_mode="Markdown")
                return
        
        if cat != "vip" and price > 0 and not user.is_vip():
            if user.points() < price:
                bot.answer_callback_query(c.id, f"❌ Need {price} points! You have {user.points()}", show_alert=True)
                return
            user.spend_points(price)
            bot.answer_callback_query(c.id, f"✅ {price} points deducted!")
        
        bot.send_message(uid, text_content, parse_mode="Markdown")
        
        if cat == "vip" and not user.is_vip():
            user.purchase_method(name, 0)
        
        return
    
    if cat == "vip":
        if user.is_vip():
            pass
        elif user.can_access_method(name):
            pass
        else:
            price = folder.get("price", 0)
            if price > 0:
                kb = InlineKeyboardMarkup(row_width=2)
                kb.add(
                    InlineKeyboardButton(f"💰 Buy for {price} pts", callback_data=f"buy|{cat}|{name}|{price}"),
                    InlineKeyboardButton("⭐ BUY VIP", callback_data="get_vip"),
                    InlineKeyboardButton("💎 GET POINTS", callback_data="get_points")
                )
                kb.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_buy"))
                bot.answer_callback_query(c.id, "🔒 This is a VIP method")
                bot.send_message(uid, f"🔒 **VIP Method: {name}**\n\nPrice: **{price} points**\nYour points: **{user.points()}**\n\nChoose an option:", reply_markup=kb, parse_mode="Markdown")
            else:
                kb = InlineKeyboardMarkup(row_width=2)
                kb.add(
                    InlineKeyboardButton("⭐ BUY VIP", callback_data="get_vip"),
                    InlineKeyboardButton("💎 GET POINTS", callback_data="get_points")
                )
                bot.answer_callback_query(c.id, "🔒 This is a VIP method")
                bot.send_message(uid, f"🔒 **VIP Method: {name}**\n\nThis is a VIP method.\n\nChoose an option to access it:", reply_markup=kb, parse_mode="Markdown")
            return
    
    price = folder.get("price", 0)
    if cat != "vip" and price > 0 and not user.is_vip():
        if user.points() < price:
            bot.answer_callback_query(c.id, f"❌ Need {price} points! You have {user.points()}", show_alert=True)
            return
        user.spend_points(price)
        bot.answer_callback_query(c.id, f"✅ {price} points deducted!")
    
    bot.answer_callback_query(c.id, "📤 Sending files...")
    count = 0
    
    for f in folder.get("files", []):
        try:
            bot.copy_message(uid, f["chat"], f["msg"])
            count += 1
            time.sleep(0.15)  # Reduced for speed
        except:
            continue
    
    if get_cached_config().get("notify", True):
        if count > 0:
            bot.send_message(uid, f"✅ Sent {count} file(s) successfully!")
        else:
            bot.send_message(uid, "❌ Failed to send files. Please try again later.")
    
    if cat == "vip" and not user.is_vip():
        user.purchase_method(name, 0)

# =========================
# 🔙 BACK BUTTON
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("back|"))
def back_handler(c):
    _, cat, current_parent = c.data.split("|")
    
    parent_folder = fs.get_one(cat, current_parent)
    if parent_folder:
        grand_parent = parent_folder.get("parent")
        bot.edit_message_reply_markup(
            c.from_user.id,
            c.message.message_id,
            reply_markup=get_folders_kb(cat, grand_parent)
        )
    else:
        bot.edit_message_reply_markup(
            c.from_user.id,
            c.message.message_id,
            reply_markup=get_folders_kb(cat)
        )
    bot.answer_callback_query(c.id)

# =========================
# 📄 PAGINATION
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("page|"))
def page_handler(c):
    _, cat, page, parent = c.data.split("|")
    parent = parent if parent != "None" else None
    
    try:
        bot.edit_message_reply_markup(
            c.from_user.id,
            c.message.message_id,
            reply_markup=get_folders_kb(cat, parent, int(page))
        )
    except:
        pass
    bot.answer_callback_query(c.id)

# =========================
# 💰 BUY METHOD
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy|"))
def buy_method(c):
    uid = c.from_user.id
    user = User(uid)
    
    try:
        _, cat, method_name, price = c.data.split("|")
        price = int(price)
    except:
        bot.answer_callback_query(c.id, "Invalid purchase data")
        return
    
    if user.is_vip():
        bot.answer_callback_query(c.id, "✅ You are VIP! You have free access!", show_alert=True)
        open_folder(c)
        return
    
    if user.can_access_method(method_name):
        bot.answer_callback_query(c.id, "✅ You already own this method!", show_alert=True)
        open_folder(c)
        return
    
    if user.points() < price:
        bot.answer_callback_query(c.id, f"❌ You need {price} points! You have {user.points()}", show_alert=True)
        return
    
    if user.purchase_method(method_name, price):
        bot.answer_callback_query(c.id, f"✅ Method purchased! {price} points deducted!", show_alert=True)
        bot.edit_message_text(
            f"✅ **Purchase Successful!**\n\nYou now own: **{method_name}**\nPoints remaining: **{user.points()}**\n\nClick the folder again to access it!",
            uid,
            c.message.message_id,
            parse_mode="Markdown"
        )
    else:
        bot.answer_callback_query(c.id, "❌ Purchase failed!", show_alert=True)

# =========================
# CALLBACK HANDLERS
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "get_vip")
def get_vip_callback(c):
    uid = c.from_user.id
    user = User(uid)
    cfg = get_cached_config()
    
    if force_block(uid):
        return
    
    if user.is_vip():
        bot.answer_callback_query(c.id, "✅ You are already a VIP member!", show_alert=True)
        return
    
    vip_msg = cfg.get("vip_msg", "💎 Buy VIP to unlock this!")
    vip_price_usd = cfg.get("vip_price", 50)
    vip_price_points = cfg.get("vip_points_price", 5000)
    payment_methods = cfg.get("payment_methods", ["💳 Binance", "💵 USDT (TRC20)", "💰 Bank Transfer", "🪙 Bitcoin"])
    vip_contact = cfg.get("vip_contact")
    
    # Binance details
    binance_address = cfg.get("binance_address", "")
    binance_coin = cfg.get("binance_coin", "USDT")
    binance_network = cfg.get("binance_network", "TRC20")
    binance_memo = cfg.get("binance_memo", "")
    
    message = f"💎 **VIP Membership** 💎\n\n"
    message += f"{vip_msg}\n\n"
    message += f"💰 **VIP Price:**\n"
    message += f"• **${vip_price_usd} USD**\n"
    message += f"• **{vip_price_points} points**\n\n"
    
    if binance_address:
        message += f"💳 **Binance Payment Details:**\n"
        message += f"┌ **Coin:** {binance_coin}\n"
        message += f"├ **Network:** {binance_network}\n"
        message += f"├ **Address:** `{binance_address}`\n"
        if binance_memo:
            message += f"├ **Memo/Tag:** `{binance_memo}`\n"
        message += f"└ **Amount:** ${vip_price_usd} USD\n\n"
        
        if cfg.get("require_screenshot", True):
            message += f"📸 **IMPORTANT:** Send payment screenshot after payment!\n\n"
    
    message += f"✨ **VIP Benefits:**\n"
    message += f"• Access to all VIP methods\n"
    message += f"• Priority support\n"
    message += f"• Exclusive content\n"
    message += f"• No points needed for VIP content\n\n"
    
    message += f"💳 **Other Payment Methods:**\n"
    for method in payment_methods:
        if "Binance" not in method:
            message += f"• {method}\n"
    message += f"\n"
    
    message += f"🎁 **Referral Rewards:**\n"
    message += f"• Invite {cfg.get('referral_vip_count', 50)} users → **FREE VIP**\n"
    message += f"• {cfg.get('referral_purchase_count', 10)} referrals buy VIP → **FREE VIP**\n\n"
    
    if vip_contact:
        message += f"📞 **Contact to become VIP:** {vip_contact}\n\n"
    else:
        message += f"📞 **Contact admin to get VIP access!**\n\n"
    
    message += f"🆔 Your ID: `{uid}`"
    message += f"\n💰 Your points: `{user.points()}`"
    
    kb = InlineKeyboardMarkup()
    
    if user.points() >= vip_price_points:
        kb.add(InlineKeyboardButton(f"⭐ Buy VIP with {vip_price_points} points", callback_data="buy_vip_points"))
    
    if vip_contact:
        if vip_contact.startswith("http"):
            kb.add(InlineKeyboardButton("📞 Contact for VIP", url=vip_contact))
        elif vip_contact.startswith("@"):
            kb.add(InlineKeyboardButton("📞 Contact for VIP", url=f"https://t.me/{vip_contact.replace('@', '')}"))
    
    bot.edit_message_text(message, uid, c.message.message_id, reply_markup=kb if kb.keyboard else None, parse_mode="Markdown")
    bot.answer_callback_query(c.id, "🔒 VIP Access Required")

@bot.callback_query_handler(func=lambda c: c.data == "buy_vip_points")
def buy_vip_points_callback(c):
    uid = c.from_user.id
    user = User(uid)
    cfg = get_cached_config()
    vip_price_points = cfg.get("vip_points_price", 5000)
    
    if user.is_vip():
        bot.answer_callback_query(c.id, "✅ You are already VIP!", show_alert=True)
        return
    
    if user.points() >= vip_price_points:
        user.spend_points(vip_price_points)
        user.make_vip(cfg.get("vip_duration_days", 30))
        
        bot.answer_callback_query(c.id, f"✅ VIP Purchased! {vip_price_points} points deducted!", show_alert=True)
        bot.edit_message_text(
            f"🎉 **CONGRATULATIONS!** 🎉\n\n"
            f"You are now a **VIP Member**!\n\n"
            f"✨ **VIP Benefits:**\n"
            f"• Access to all VIP methods\n"
            f"• Priority support\n"
            f"• Exclusive content\n\n"
            f"💰 Points remaining: `{user.points()}`",
            uid,
            c.message.message_id,
            parse_mode="Markdown"
        )
    else:
        bot.answer_callback_query(c.id, f"❌ You need {vip_price_points} points! You have {user.points()}", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data == "get_points")
def get_points_callback(c):
    uid = c.from_user.id
    user = User(uid)
    cfg = get_cached_config()
    
    if force_block(uid):
        return
    
    packages = get_points_packages()
    active_packages = [p for p in packages if p.get("active", True)]
    
    contact_username = cfg.get("contact_username")
    contact_link = cfg.get("contact_link")
    
    binance_address = cfg.get("binance_address", "")
    binance_coin = cfg.get("binance_coin", "USDT")
    binance_network = cfg.get("binance_network", "TRC20")
    binance_memo = cfg.get("binance_memo", "")
    
    message = f"💰 **GET POINTS** 💰\n\n"
    message += f"✨ **Your Current Balance:** `{user.points()}` points\n\n"
    
    if active_packages:
        message += f"📦 **BUY POINTS PACKAGES:**\n\n"
        for i, pkg in enumerate(active_packages, 1):
            total_points = pkg["points"] + pkg.get("bonus", 0)
            price_display = f"${pkg['price']}"
            
            message += f"💎 **Package {i}:**\n"
            message += f"   • {pkg['points']} points for `{price_display}`\n"
            if pkg.get("bonus", 0) > 0:
                message += f"   • **BONUS:** +{pkg['bonus']} points FREE!\n"
                message += f"   • **Total:** `{total_points}` points\n"
            message += f"   • 💰 **Value:** {price_display}\n\n"
        
        if binance_address:
            message += f"💳 **Binance Payment Details:**\n"
            message += f"┌ **Coin:** {binance_coin}\n"
            message += f"├ **Network:** {binance_network}\n"
            message += f"├ **Address:** `{binance_address}`\n"
            if binance_memo:
                message += f"├ **Memo/Tag:** `{binance_memo}`\n"
            message += f"└ **Amount:** Equal to package price\n\n"
            
            if cfg.get("require_screenshot", True):
                message += f"📸 **IMPORTANT:** Send payment screenshot after payment!\n\n"
        
        message += f"✨ **How to Purchase Points:**\n"
        message += f"1️⃣ Send payment to the Binance address above\n"
        message += f"2️⃣ Take a screenshot of payment confirmation\n"
        message += f"3️⃣ Send the screenshot here\n"
        message += f"4️⃣ Send your **User ID**: `{uid}`\n"
        message += f"5️⃣ Mention which package you want\n"
        message += f"6️⃣ Wait for admin confirmation\n\n"
        
        message += f"💳 **Other Payment Methods:**\n"
        for method in cfg.get("payment_methods", ["💳 Binance", "💵 USDT"]):
            if "Binance" not in method:
                message += f"• {method}\n"
        message += f"\n"
        
        message += f"🎁 **Special Offers:**\n"
        message += f"• First purchase: **10% BONUS**\n"
        message += f"• Referral: Earn points when friends buy\n"
        message += f"• Bulk orders: Contact for custom pricing\n\n"
        
        message += f"⚡ **Fast delivery within 5-10 minutes after payment confirmation!**\n\n"
    else:
        message += f"❌ No points packages available right now.\n\n"
    
    message += f"🎁 **FREE WAYS TO EARN POINTS:**\n"
    message += f"• **Referral System:** Share your referral link\n"
    message += f"• **Redeem Codes:** Use coupon codes from admin\n"
    message += f"• **Complete Tasks:** Check announcements\n\n"
    
    message += f"💡 **Tip:** More points = More VIP methods!"
    
    kb = InlineKeyboardMarkup(row_width=2)
    
    if contact_link:
        kb.add(InlineKeyboardButton("📞 Contact Admin", url=contact_link))
    elif contact_username:
        kb.add(InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{contact_username.replace('@', '')}"))
    else:
        try:
            admin_chat = bot.get_chat(ADMIN_ID)
            if admin_chat.username:
                kb.add(InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{admin_chat.username}"))
        except:
            pass
    
    if active_packages:
        kb.add(InlineKeyboardButton("💰 Check Balance", callback_data="check_balance"))
    kb.add(InlineKeyboardButton("🎁 Referral Link", callback_data="get_referral"))
    kb.add(InlineKeyboardButton("⭐ VIP Info", callback_data="get_vip_info"))
    
    bot.edit_message_text(message, uid, c.message.message_id, reply_markup=kb, parse_mode="Markdown")
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "cancel_buy")
def cancel_buy(c):
    bot.edit_message_text("❌ Cancelled", c.from_user.id, c.message.message_id)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "check_balance")
def check_balance_callback(c):
    uid = c.from_user.id
    user = User(uid)
    
    bot.answer_callback_query(c.id, f"💰 Your balance: {user.points()} points", show_alert=True)
    
    bot.edit_message_text(
        f"💰 **Your Points Balance**\n\n"
        f"┌ Points: `{user.points()}`\n"
        f"├ VIP: {'✅ Active' if user.is_vip() else '❌ Not Active'}\n"
        f"├ Referrals: `{user.get_refs_count()}`\n"
        f"├ Referrals who bought VIP: `{user.get_refs_bought_vip_count()}`\n"
        f"├ Total Earned: `{user.data.get('total_points_earned', 0)}`\n"
        f"└ Total Spent: `{user.data.get('total_points_spent', 0)}`\n\n"
        f"Need more points? Click 💎 GET POINTS button!",
        uid,
        c.message.message_id,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda c: c.data == "get_referral")
def get_referral_callback(c):
    uid = c.from_user.id
    cfg = get_cached_config()
    link = f"https://t.me/{bot.get_me().username}?start={uid}"
    
    bot.edit_message_text(
        f"🎁 **Your Referral Link**\n\n"
        f"`{link}`\n\n"
        f"✨ **Referral Rewards:**\n"
        f"• For each friend who joins: `+{cfg.get('ref_reward', 5)}` points\n"
        f"• Invite {cfg.get('referral_vip_count', 50)} users → **FREE VIP**\n"
        f"• {cfg.get('referral_purchase_count', 10)} referrals buy VIP → **FREE VIP**\n\n"
        f"📊 **Your Stats:**\n"
        f"• Total Referrals: {User(uid).get_refs_count()}\n"
        f"• Referrals who bought VIP: {User(uid).get_refs_bought_vip_count()}\n\n"
        f"💡 Share this link in groups, channels, and with friends!",
        uid,
        c.message.message_id,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda c: c.data == "get_vip_info")
def get_vip_info_callback(c):
    uid = c.from_user.id
    cfg = get_cached_config()
    vip_contact = cfg.get("vip_contact")
    vip_price_usd = cfg.get("vip_price", 50)
    vip_price_points = cfg.get("vip_points_price", 5000)
    
    message = f"⭐ **VIP Membership Benefits** ⭐\n\n"
    message += f"✨ **Why become VIP?**\n"
    message += f"• Access to **ALL VIP methods**\n"
    message += f"• No points needed for VIP content\n"
    message += f"• Priority support\n"
    message += f"• Exclusive content and updates\n"
    message += f"• Special VIP-only offers\n\n"
    
    message += f"💰 **VIP Price:**\n"
    message += f"• **${vip_price_usd} USD**\n"
    message += f"• **{vip_price_points} points**\n\n"
    
    message += f"💳 **Payment Methods:**\n"
    for method in cfg.get("payment_methods", ["💳 Binance", "💵 USDT"]):
        message += f"• {method}\n"
    message += f"\n"
    
    message += f"🎁 **FREE VIP via Referrals:**\n"
    message += f"• Invite {cfg.get('referral_vip_count', 50)} users\n"
    message += f"• Get {cfg.get('referral_purchase_count', 10)} referrals to buy VIP\n\n"
    
    if vip_contact:
        message += f"📞 **Contact for VIP:** {vip_contact}\n\n"
    else:
        message += f"📞 **Contact admin to become VIP today!** 🚀"
    
    kb = InlineKeyboardMarkup()
    if vip_contact:
        if vip_contact.startswith("http"):
            kb.add(InlineKeyboardButton("📞 Contact for VIP", url=vip_contact))
        elif vip_contact.startswith("@"):
            kb.add(InlineKeyboardButton("📞 Contact for VIP", url=f"https://t.me/{vip_contact.replace('@', '')}"))
    
    bot.edit_message_text(message, uid, c.message.message_id, reply_markup=kb if kb.keyboard else None, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "recheck")
def recheck(c):
    uid = c.from_user.id
    user = User(uid)
    
    if not force_block(uid):
        try:
            bot.edit_message_text(
                "✅ **Access Granted!**\n\nWelcome to ZEDOX BOT!",
                uid,
                c.message.message_id,
                parse_mode="Markdown"
            )
        except:
            pass
        
        bot.send_message(uid, f"🎉 Welcome! Use the menu below to get started.\n\n💰 Your points: **{user.points()}**", reply_markup=main_menu(uid))
    else:
        bot.answer_callback_query(c.id, "❌ Please join all required channels first", show_alert=True)

# =========================
# 📚 MY METHODS
# =========================
@bot.message_handler(func=lambda m: m.text == "📚 MY METHODS")
def show_purchased_methods(m):
    uid = m.from_user.id
    user = User(uid)
    
    if force_block(uid):
        return
    
    purchased = user.purchased_methods()
    
    if user.is_vip():
        bot.send_message(uid, "💎 **VIP Member**\n\nYou have access to ALL VIP methods!\n\nNo need to purchase individual methods.", parse_mode="Markdown")
        return
    
    if not purchased:
        bot.send_message(uid, f"📚 **Your Purchased Methods**\n\nYou haven't purchased any VIP methods yet.\n\n💰 Use your **{user.points()} points** to buy VIP methods from the 💎 VIP METHODS section!", parse_mode="Markdown")
        return
    
    all_vip_methods = {item["name"]: item.get("number", "?") for item in fs.get("vip")}
    
    kb = InlineKeyboardMarkup(row_width=2)
    for method in purchased:
        number = all_vip_methods.get(method, "?")
        kb.add(InlineKeyboardButton(f"[{number}] {method}", callback_data=f"open|vip|{method}|"))
    
    bot.send_message(uid, f"📚 **Your Purchased Methods** (Total: {len(purchased)})\n\n💰 Points remaining: `{user.points()}`\n\nClick any method to open it:", reply_markup=kb, parse_mode="Markdown")

# =========================
# 👤 ACCOUNT
# =========================
@bot.message_handler(func=lambda m: m.text == "👤 ACCOUNT")
def account_cmd(m):
    uid = m.from_user.id
    user = User(uid)
    
    if force_block(uid):
        return
    
    status = "💎 VIP Member" if user.is_vip() else "🆓 Free User"
    purchased_count = len(user.purchased_methods())
    used_codes_count = len(user.used_codes())
    ref_count = user.get_refs_count()
    ref_bought_count = user.get_refs_bought_vip_count()
    
    all_vip_methods = {item["name"]: item.get("number", "?") for item in fs.get("vip")}
    purchased_with_numbers = [f"[{all_vip_methods.get(m, '?')}] {m}" for m in user.purchased_methods()]
    
    account_text = f"**👤 Account Information**\n\n"
    account_text += f"┌ **Status:** {status}\n"
    account_text += f"├ **Points:** `{user.points()}`\n"
    account_text += f"├ **Total Referrals:** `{ref_count}`\n"
    account_text += f"├ **Referrals who bought VIP:** `{ref_bought_count}`\n"
    account_text += f"├ **Purchased:** `{purchased_count}` methods\n"
    account_text += f"├ **Redeemed Codes:** `{used_codes_count}`\n"
    account_text += f"├ **Total Points Earned:** `{user.data.get('total_points_earned', 0)}`\n"
    account_text += f"└ **Total Points Spent:** `{user.data.get('total_points_spent', 0)}`\n"
    
    if purchased_with_numbers:
        account_text += f"\n📚 **Your Methods:**\n"
        for method in purchased_with_numbers[:10]:
            account_text += f"• {method}\n"
        if len(purchased_with_numbers) > 10:
            account_text += f"• ... and {len(purchased_with_numbers) - 10} more\n"
    
    if not user.is_vip():
        cfg = get_cached_config()
        account_text += f"\n💡 **Get FREE VIP:**\n"
        account_text += f"• Invite {cfg.get('referral_vip_count', 50)} users\n"
        account_text += f"• Get {cfg.get('referral_purchase_count', 10)} referrals to buy VIP\n"
    
    account_text += f"\n\n🆔 **User ID:** `{uid}`"
    
    bot.send_message(uid, account_text, parse_mode="Markdown")

# =========================
# 🎁 REFERRAL
# =========================
@bot.message_handler(func=lambda m: m.text == "🎁 REFERRAL")
def referral_cmd(m):
    uid = m.from_user.id
    user = User(uid)
    
    if force_block(uid):
        return
    
    link = f"https://t.me/{bot.get_me().username}?start={uid}"
    ref_count = user.get_refs_count()
    ref_bought_count = user.get_refs_bought_vip_count()
    ref_reward = get_cached_config().get("ref_reward", 5)
    cfg = get_cached_config()
    
    bot.send_message(uid, 
        f"🎁 **REFERRAL SYSTEM** 🎁\n\n"
        f"🔗 **Your Referral Link:**\n`{link}`\n\n"
        f"📊 **Your Stats:**\n"
        f"┌ Total Referrals: `{ref_count}`\n"
        f"├ Referrals who bought VIP: `{ref_bought_count}`\n"
        f"├ Points earned: `{ref_count * ref_reward}`\n"
        f"└ Progress to VIP: `{ref_count}/{cfg.get('referral_vip_count', 50)}`\n\n"
        
        f"✨ **Rewards:**\n"
        f"• Per referral: **+{ref_reward} points**\n"
        f"• Reach {cfg.get('referral_vip_count', 50)} referrals → **FREE VIP**\n"
        f"• Get {cfg.get('referral_purchase_count', 10)} referrals to buy VIP → **FREE VIP**\n\n"
        
        f"💡 **How it works:**\n"
        f"1. Share your link with friends\n"
        f"2. When they join, you get points\n"
        f"3. When they buy VIP, you get progress\n"
        f"4. Reach milestones → FREE VIP!\n\n"
        
        f"🚀 **Pro tip:** Share in groups and channels for more referrals!\n\n"
        f"💰 **Current Points:** `{user.points()}`",
        parse_mode="Markdown")

# =========================
# 🏆 REDEEM CODE
# =========================
@bot.message_handler(func=lambda m: m.text == "🏆 REDEEM")
def redeem_cmd(m):
    uid = m.from_user.id
    
    if force_block(uid):
        return
    
    msg = bot.send_message(uid, "🎫 **Enter your redeem code:**\n\n*Each code can only be used once!*\n\nFormat: `ZEDOX12345678`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, redeem_code)

def redeem_code(m):
    uid = m.from_user.id
    user = User(uid)
    code = m.text.strip().upper()
    
    success, pts, reason = codesys.redeem(code, user)
    
    if success:
        bot.send_message(uid, 
            f"✅ **Code Redeemed Successfully!** 🎉\n\n"
            f"➕ **+{pts} points added**\n"
            f"💰 **Total Points:** `{user.points()}`\n\n"
            f"✨ Use your points to buy VIP methods!\n"
            f"📚 Check '📚 MY METHODS' to see your purchases.",
            parse_mode="Markdown")
    else:
        messages = {
            "invalid": "❌ **Invalid Code**\n\nPlease check your code and try again.",
            "already_used": "❌ **Code Already Used**\n\nThis code has already been redeemed.",
            "already_used_by_user": "❌ **Code Already Used**\n\nYou have already redeemed this code.",
            "expired": "❌ **Code Expired**\n\nThis code has expired and is no longer valid.",
            "max_uses_reached": "❌ **Max Uses Reached**\n\nThis code has reached its maximum usage limit."
        }
        bot.send_message(uid, messages.get(reason, "❌ Invalid code!"), parse_mode="Markdown")

# =========================
# 🆔 CHAT ID
# =========================
@bot.message_handler(func=lambda m: m.text == "🆔 CHAT ID")
def chatid_cmd(m):
    uid = m.from_user.id
    user = User(uid)
    
    if force_block(uid):
        return
    
    bot.send_message(uid, f"🆔 **Your Information**\n\n"
                          f"┌ **Chat ID:** `{uid}`\n"
                          f"├ **Points:** `{user.points()}`\n"
                          f"├ **VIP:** {'✅' if user.is_vip() else '❌'}\n"
                          f"├ **Referrals:** `{user.get_refs_count()}`\n"
                          f"└ **Referrals who bought VIP:** `{user.get_refs_bought_vip_count()}`\n\n"
                          f"Share this ID with admin if needed.", 
                    parse_mode="Markdown")

# =========================
# ⭐ BUY VIP (UPDATED WITH BINANCE)
# =========================
@bot.message_handler(func=lambda m: m.text == "⭐ BUY VIP")
def buy_vip_button(m):
    uid = m.from_user.id
    user = User(uid)
    cfg = get_cached_config()
    
    if force_block(uid):
        return
    
    if user.is_vip():
        bot.send_message(uid, "✅ **You are already a VIP member!**\n\n✨ Enjoy exclusive VIP content and benefits!\n\n💰 Your points: `{}`".format(user.points()), parse_mode="Markdown")
        return
    
    vip_msg = cfg.get("vip_msg", "💎 Buy VIP to unlock this!")
    vip_price_usd = cfg.get("vip_price", 50)
    vip_price_points = cfg.get("vip_points_price", 5000)
    vip_contact = cfg.get("vip_contact")
    payment_methods = cfg.get("payment_methods", ["💳 Binance", "💵 USDT (TRC20)", "💰 Bank Transfer", "🪙 Bitcoin"])
    
    binance_address = cfg.get("binance_address", "")
    binance_coin = cfg.get("binance_coin", "USDT")
    binance_network = cfg.get("binance_network", "TRC20")
    binance_memo = cfg.get("binance_memo", "")
    
    message = f"💎 **VIP Membership** 💎\n\n"
    message += f"{vip_msg}\n\n"
    message += f"💰 **VIP Price:**\n"
    message += f"• **${vip_price_usd} USD**\n"
    message += f"• **{vip_price_points} points**\n\n"
    
    if binance_address:
        message += f"💳 **Binance Payment Details:**\n"
        message += f"┌ **Coin:** {binance_coin}\n"
        message += f"├ **Network:** {binance_network}\n"
        message += f"├ **Address:** `{binance_address}`\n"
        if binance_memo:
            message += f"├ **Memo/Tag:** `{binance_memo}`\n"
        message += f"└ **Amount:** ${vip_price_usd} USD\n\n"
        
        if cfg.get("require_screenshot", True):
            message += f"📸 **IMPORTANT:** Send payment screenshot after payment!\n\n"
    
    message += f"💳 **Other Payment Methods:**\n"
    for method in payment_methods:
        if "Binance" not in method:
            message += f"• {method}\n"
    message += f"\n"
    
    message += f"✨ **VIP Benefits:**\n"
    message += f"• Access to all VIP methods\n"
    message += f"• Priority support\n"
    message += f"• Exclusive content\n"
    message += f"• No points needed for VIP content\n\n"
    
    message += f"🎁 **FREE VIP via Referrals:**\n"
    message += f"• Invite {cfg.get('referral_vip_count', 50)} users\n"
    message += f"• Get {cfg.get('referral_purchase_count', 10)} referrals to buy VIP\n\n"
    
    if vip_contact:
        message += f"📞 **Contact to become VIP:** {vip_contact}\n\n"
    else:
        message += f"📞 **Contact admin to get VIP access!**\n\n"
    
    message += f"🆔 Your ID: `{uid}`"
    message += f"\n💰 Your points: `{user.points()}`"
    
    kb = InlineKeyboardMarkup()
    
    if user.points() >= vip_price_points:
        kb.add(InlineKeyboardButton(f"⭐ Buy VIP with {vip_price_points} points", callback_data="buy_vip_points"))
    
    if vip_contact:
        if vip_contact.startswith("http"):
            kb.add(InlineKeyboardButton("📞 Contact for VIP", url=vip_contact))
        elif vip_contact.startswith("@"):
            kb.add(InlineKeyboardButton("📞 Contact for VIP", url=f"https://t.me/{vip_contact.replace('@', '')}"))
    
    bot.send_message(uid, message, reply_markup=kb if kb.keyboard else None, parse_mode="Markdown")

# =========================
# ⚙️ ADMIN PANEL (UPDATED WITH BINANCE SETTINGS)
# =========================
def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    
    kb.row("📦 Upload FREE", "💎 Upload VIP")
    kb.row("📱 Upload APPS", "⚡ Upload SERVICE")
    
    kb.row("📁 Create Subfolder", "🗑 Delete Folder")
    kb.row("✏️ Edit Price", "✏️ Edit Name")
    kb.row("📝 Edit Content", "🔀 Move Folder")
    
    kb.row("👑 Add VIP", "👑 Remove VIP")
    kb.row("💰 Give Points")
    
    kb.row("🏆 Generate Codes", "📊 View Codes")
    kb.row("📦 Points Packages", "💰 Set Point Price")
    
    kb.row("👥 Admin Management", "📞 Set Contacts")
    kb.row("⚙️ VIP Settings", "💳 Payment Methods")
    kb.row("🏦 Binance Settings", "📸 Screenshot Setting")  # NEW
    
    kb.row("➕ Add Main Button", "➖ Remove Main Button")
    
    kb.row("➕ Add Force Join", "➖ Remove Force Join")
    kb.row("🔗 Add Custom Link", "📋 View Links")
    
    kb.row("⭐ Set VIP Msg", "💰 Set Purchase Msg")
    kb.row("🏠 Set Welcome", "⚙️ Set Ref Reward")
    kb.row("📊 Stats", "📢 Broadcast")
    
    kb.row("🔔 Toggle Notify")
    kb.row("❌ Exit Admin")
    
    return kb

@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def open_admin(m):
    bot.send_message(m.from_user.id, "⚙️ **Admin Control Panel**\n\nSelect an option:", reply_markup=admin_menu(), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "❌ Exit Admin" and is_admin(m.from_user.id))
def exit_admin(m):
    bot.send_message(m.from_user.id, "Exited Admin Panel", reply_markup=main_menu(m.from_user.id))

# =========================
# 🏦 BINANCE SETTINGS (NEW)
# =========================
@bot.message_handler(func=lambda m: m.text == "🏦 Binance Settings" and is_admin(m.from_user.id))
def binance_settings_menu(m):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("💰 Set Binance Coin", callback_data="set_binance_coin"),
        InlineKeyboardButton("🌐 Set Network", callback_data="set_binance_network"),
        InlineKeyboardButton("📍 Set Wallet Address", callback_data="set_binance_address"),
        InlineKeyboardButton("📝 Set Memo/Tag", callback_data="set_binance_memo"),
        InlineKeyboardButton("📋 View Binance Settings", callback_data="view_binance_settings")
    )
    
    bot.send_message(m.from_user.id, "🏦 **Binance Payment Settings**\n\nSelect an option:", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "set_binance_coin")
def set_binance_coin_cb(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Admin only!")
        return
    
    msg = bot.send_message(c.from_user.id, "💰 Enter Binance coin (e.g., USDT, BUSD, BTC):\n\nCurrent: {}".format(get_config().get("binance_coin", "USDT")), parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_binance_coin)
    bot.answer_callback_query(c.id)

def save_binance_coin(m):
    set_config("binance_coin", m.text.strip().upper())
    bot.send_message(m.from_user.id, f"✅ Binance coin set to: {m.text.upper()}", reply_markup=admin_menu())

@bot.callback_query_handler(func=lambda c: c.data == "set_binance_network")
def set_binance_network_cb(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Admin only!")
        return
    
    msg = bot.send_message(c.from_user.id, "🌐 Enter network (e.g., TRC20, BEP20, ERC20):\n\nCurrent: {}".format(get_config().get("binance_network", "TRC20")), parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_binance_network)
    bot.answer_callback_query(c.id)

def save_binance_network(m):
    set_config("binance_network", m.text.strip().upper())
    bot.send_message(m.from_user.id, f"✅ Network set to: {m.text.upper()}", reply_markup=admin_menu())

@bot.callback_query_handler(func=lambda c: c.data == "set_binance_address")
def set_binance_address_cb(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Admin only!")
        return
    
    msg = bot.send_message(c.from_user.id, "📍 Enter Binance wallet address:\n\nCurrent: {}".format(get_config().get("binance_address", "Not set")), parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_binance_address)
    bot.answer_callback_query(c.id)

def save_binance_address(m):
    set_config("binance_address", m.text.strip())
    bot.send_message(m.from_user.id, f"✅ Binance address saved!", reply_markup=admin_menu())

@bot.callback_query_handler(func=lambda c: c.data == "set_binance_memo")
def set_binance_memo_cb(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Admin only!")
        return
    
    msg = bot.send_message(c.from_user.id, "📝 Enter Memo/Tag (if required, otherwise send 'none'):\n\nCurrent: {}".format(get_config().get("binance_memo", "None")), parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_binance_memo)
    bot.answer_callback_query(c.id)

def save_binance_memo(m):
    if m.text.lower() == "none":
        set_config("binance_memo", "")
    else:
        set_config("binance_memo", m.text.strip())
    bot.send_message(m.from_user.id, f"✅ Memo/Tag saved!", reply_markup=admin_menu())

@bot.callback_query_handler(func=lambda c: c.data == "view_binance_settings")
def view_binance_settings_cb(c):
    cfg = get_config()
    text = f"🏦 **Binance Payment Settings**\n\n"
    text += f"💰 Coin: **{cfg.get('binance_coin', 'USDT')}**\n"
    text += f"🌐 Network: **{cfg.get('binance_network', 'TRC20')}**\n"
    text += f"📍 Address: `{cfg.get('binance_address', 'Not set')}`\n"
    text += f"📝 Memo/Tag: `{cfg.get('binance_memo', 'None') or 'None'}`\n"
    text += f"📸 Screenshot Required: **{'Yes' if cfg.get('require_screenshot', True) else 'No'}**"
    
    bot.edit_message_text(text, c.from_user.id, c.message.message_id, parse_mode="Markdown")
    bot.answer_callback_query(c.id)

# =========================
# 📸 SCREENSHOT SETTING
# =========================
@bot.message_handler(func=lambda m: m.text == "📸 Screenshot Setting" and is_admin(m.from_user.id))
def screenshot_setting_menu(m):
    cfg = get_config()
    current = cfg.get("require_screenshot", True)
    status = "✅ ENABLED" if current else "❌ DISABLED"
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔘 Toggle Screenshot Requirement", callback_data="toggle_screenshot"))
    
    bot.send_message(m.from_user.id, f"📸 **Screenshot Requirement**\n\nCurrent: {status}\n\nWhen enabled, users must send payment screenshot before getting points.", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "toggle_screenshot")
def toggle_screenshot_cb(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Admin only!")
        return
    
    cfg = get_config()
    current = cfg.get("require_screenshot", True)
    set_config("require_screenshot", not current)
    new_status = "ENABLED" if not current else "DISABLED"
    
    bot.answer_callback_query(c.id, f"Screenshot requirement {new_status}!")
    bot.edit_message_text(f"✅ Screenshot requirement {new_status}!", c.from_user.id, c.message.message_id)
    bot.send_message(c.from_user.id, "Returning to admin panel...", reply_markup=admin_menu())

# =========================
# ⚙️ VIP SETTINGS
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ VIP Settings" and is_admin(m.from_user.id))
def vip_settings_menu(m):
    cfg = get_config()
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("💰 Set VIP Price (USD)", callback_data="set_vip_price_usd"),
        InlineKeyboardButton("💎 Set VIP Price (Points)", callback_data="set_vip_price_points"),
        InlineKeyboardButton("👥 Set Referral VIP Count", callback_data="set_ref_vip_count"),
        InlineKeyboardButton("🛒 Set Referral Purchase Count", callback_data="set_ref_purchase_count"),
        InlineKeyboardButton("📅 Set VIP Duration (Days)", callback_data="set_vip_duration"),
        InlineKeyboardButton("📋 View VIP Settings", callback_data="view_vip_settings")
    )
    
    bot.send_message(m.from_user.id, "⚙️ **VIP & Referral Settings**\n\nSelect an option:", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "set_vip_price_usd")
def set_vip_price_usd_cb(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Admin only!")
        return
    
    msg = bot.send_message(c.from_user.id, "💰 Enter VIP price in USD:\n\nCurrent: ${} USD".format(get_config().get("vip_price", 50)), parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_vip_price_usd)
    bot.answer_callback_query(c.id)

def save_vip_price_usd(m):
    try:
        price = int(m.text)
        if price <= 0:
            bot.send_message(m.from_user.id, "❌ Price must be greater than 0!")
            return
        set_config("vip_price", price)
        bot.send_message(m.from_user.id, f"✅ VIP price set to ${price} USD!", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid number!")

@bot.callback_query_handler(func=lambda c: c.data == "set_vip_price_points")
def set_vip_price_points_cb(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Admin only!")
        return
    
    msg = bot.send_message(c.from_user.id, "💎 Enter VIP price in points:\n\nCurrent: {} points".format(get_config().get("vip_points_price", 5000)), parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_vip_price_points)
    bot.answer_callback_query(c.id)

def save_vip_price_points(m):
    try:
        price = int(m.text)
        if price <= 0:
            bot.send_message(m.from_user.id, "❌ Price must be greater than 0!")
            return
        set_config("vip_points_price", price)
        bot.send_message(m.from_user.id, f"✅ VIP price set to {price} points!", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid number!")

@bot.callback_query_handler(func=lambda c: c.data == "set_ref_vip_count")
def set_ref_vip_count_cb(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Admin only!")
        return
    
    msg = bot.send_message(c.from_user.id, "👥 Enter number of referrals needed for FREE VIP:\n\nCurrent: {}".format(get_config().get("referral_vip_count", 50)), parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_ref_vip_count)
    bot.answer_callback_query(c.id)

def save_ref_vip_count(m):
    try:
        count = int(m.text)
        if count <= 0:
            bot.send_message(m.from_user.id, "❌ Count must be greater than 0!")
            return
        set_config("referral_vip_count", count)
        bot.send_message(m.from_user.id, f"✅ Users need {count} referrals to get FREE VIP!", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid number!")

@bot.callback_query_handler(func=lambda c: c.data == "set_ref_purchase_count")
def set_ref_purchase_count_cb(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Admin only!")
        return
    
    msg = bot.send_message(c.from_user.id, "🛒 Enter number of referrals who bought VIP needed for FREE VIP:\n\nCurrent: {}".format(get_config().get("referral_purchase_count", 10)), parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_ref_purchase_count)
    bot.answer_callback_query(c.id)

def save_ref_purchase_count(m):
    try:
        count = int(m.text)
        if count <= 0:
            bot.send_message(m.from_user.id, "❌ Count must be greater than 0!")
            return
        set_config("referral_purchase_count", count)
        bot.send_message(m.from_user.id, f"✅ Users need {count} referrals who bought VIP to get FREE VIP!", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid number!")

@bot.callback_query_handler(func=lambda c: c.data == "set_vip_duration")
def set_vip_duration_cb(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Admin only!")
        return
    
    msg = bot.send_message(c.from_user.id, "📅 Enter VIP duration in days (0 = permanent):\n\nCurrent: {} days".format(get_config().get("vip_duration_days", 30)), parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_vip_duration)
    bot.answer_callback_query(c.id)

def save_vip_duration(m):
    try:
        days = int(m.text)
        if days < 0:
            bot.send_message(m.from_user.id, "❌ Days cannot be negative!")
            return
        set_config("vip_duration_days", days)
        if days == 0:
            bot.send_message(m.from_user.id, f"✅ VIP set to PERMANENT (never expires)!", reply_markup=admin_menu())
        else:
            bot.send_message(m.from_user.id, f"✅ VIP duration set to {days} days!", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid number!")

@bot.callback_query_handler(func=lambda c: c.data == "view_vip_settings")
def view_vip_settings_cb(c):
    cfg = get_config()
    text = f"📋 **VIP & Referral Settings**\n\n"
    text += f"💰 VIP Price (USD): **${cfg.get('vip_price', 50)}**\n"
    text += f"💎 VIP Price (Points): **{cfg.get('vip_points_price', 5000)}** points\n"
    text += f"👥 Referrals for FREE VIP: **{cfg.get('referral_vip_count', 50)}**\n"
    text += f"🛒 Referral purchases for FREE VIP: **{cfg.get('referral_purchase_count', 10)}**\n"
    text += f"📅 VIP Duration: **{cfg.get('vip_duration_days', 30)} days** (0 = permanent)\n"
    text += f"💳 Payment Methods: {', '.join(cfg.get('payment_methods', ['💳 Binance', '💵 USDT']))}"
    
    bot.edit_message_text(text, c.from_user.id, c.message.message_id, parse_mode="Markdown")
    bot.answer_callback_query(c.id)

# =========================
# 💳 PAYMENT METHODS
# =========================
@bot.message_handler(func=lambda m: m.text == "💳 Payment Methods" and is_admin(m.from_user.id))
def payment_methods_menu(m):
    cfg = get_config()
    methods = cfg.get("payment_methods", ["💳 Binance", "💵 USDT (TRC20)", "💰 Bank Transfer", "🪙 Bitcoin"])
    
    text = f"💳 **Payment Methods**\n\n"
    text += f"**Current Methods:**\n"
    for i, method in enumerate(methods, 1):
        text += f"{i}. {method}\n"
    
    text += f"\n**Commands:**\n"
    text += f"/addmethod [method name] - Add payment method\n"
    text += f"/removemethod [number] - Remove payment method\n"
    text += f"/listmethods - List all methods"
    
    bot.send_message(m.from_user.id, text, parse_mode="Markdown")

@bot.message_handler(commands=["addmethod"])
def add_payment_method(m):
    if not is_admin(m.from_user.id):
        return
    
    try:
        method = m.text.replace("/addmethod", "").strip()
        if not method:
            bot.send_message(m.from_user.id, "❌ Usage: /addmethod [method name]")
            return
        
        cfg = get_config()
        methods = cfg.get("payment_methods", [])
        methods.append(method)
        set_config("payment_methods", methods)
        bot.send_message(m.from_user.id, f"✅ Added payment method: {method}", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Error adding method!")

@bot.message_handler(commands=["removemethod"])
def remove_payment_method(m):
    if not is_admin(m.from_user.id):
        return
    
    try:
        parts = m.text.split()
        if len(parts) != 2:
            bot.send_message(m.from_user.id, "❌ Usage: /removemethod [number]")
            return
        
        num = int(parts[1]) - 1
        cfg = get_config()
        methods = cfg.get("payment_methods", [])
        
        if 0 <= num < len(methods):
            removed = methods.pop(num)
            set_config("payment_methods", methods)
            bot.send_message(m.from_user.id, f"✅ Removed payment method: {removed}", reply_markup=admin_menu())
        else:
            bot.send_message(m.from_user.id, "❌ Invalid method number!")
    except:
        bot.send_message(m.from_user.id, "❌ Error removing method!")

@bot.message_handler(commands=["listmethods"])
def list_payment_methods(m):
    if not is_admin(m.from_user.id):
        return
    
    cfg = get_config()
    methods = cfg.get("payment_methods", ["💳 Binance", "💵 USDT (TRC20)", "💰 Bank Transfer", "🪙 Bitcoin"])
    
    text = f"💳 **Payment Methods**\n\n"
    for i, method in enumerate(methods, 1):
        text += f"{i}. {method}\n"
    
    bot.send_message(m.from_user.id, text, parse_mode="Markdown")

# =========================
# 👥 ADMIN MANAGEMENT
# =========================
@bot.message_handler(func=lambda m: m.text == "👥 Admin Management" and is_admin(m.from_user.id))
def admin_management(m):
    if m.from_user.id != ADMIN_ID:
        bot.send_message(m.from_user.id, "❌ Only the bot owner can manage admins!")
        return
    
    admins = get_all_admins()
    msg = "👥 **Admin Management**\n\n"
    msg += "**Current Admins:**\n"
    for admin in admins:
        owner_tag = " 👑 OWNER" if admin.get("is_owner") else ""
        username = admin.get("username") or f"ID: {admin['_id']}"
        msg += f"• `{admin['_id']}` - {username}{owner_tag}\n"
    
    msg += "\n**Commands:**\n"
    msg += "/addadmin user_id - Add new admin\n"
    msg += "/removeadmin user_id - Remove admin\n"
    msg += "/listadmins - List all admins"
    
    bot.send_message(m.from_user.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=["addadmin"])
def add_admin_cmd(m):
    if m.from_user.id != ADMIN_ID:
        bot.send_message(m.from_user.id, "❌ Only the bot owner can add admins!")
        return
    
    try:
        _, user_id = m.text.split()
        user_id = int(user_id)
        
        try:
            chat = bot.get_chat(user_id)
            username = chat.username
        except:
            username = None
        
        if add_admin(user_id, username, m.from_user.id):
            bot.send_message(m.from_user.id, f"✅ Admin `{user_id}` added successfully!", parse_mode="Markdown")
            try:
                bot.send_message(user_id, "🎉 **You are now an admin of ZEDOX BOT!**\n\nUse ⚙️ ADMIN PANEL to manage the bot.", parse_mode="Markdown")
            except:
                pass
        else:
            bot.send_message(m.from_user.id, f"❌ User `{user_id}` is already an admin!", parse_mode="Markdown")
    except:
        bot.send_message(m.from_user.id, "❌ Use: /addadmin user_id")

@bot.message_handler(commands=["removeadmin"])
def remove_admin_cmd(m):
    if m.from_user.id != ADMIN_ID:
        bot.send_message(m.from_user.id, "❌ Only the bot owner can remove admins!")
        return
    
    try:
        _, user_id = m.text.split()
        user_id = int(user_id)
        
        if remove_admin(user_id):
            bot.send_message(m.from_user.id, f"✅ Admin `{user_id}` removed!", parse_mode="Markdown")
            try:
                bot.send_message(user_id, "⚠️ You are no longer an admin of ZEDOX BOT.", parse_mode="Markdown")
            except:
                pass
        else:
            bot.send_message(m.from_user.id, f"❌ Cannot remove main owner or user is not admin!", parse_mode="Markdown")
    except:
        bot.send_message(m.from_user.id, "❌ Use: /removeadmin user_id")

@bot.message_handler(commands=["listadmins"])
def list_admins_cmd(m):
    if not is_admin(m.from_user.id):
        return
    
    admins = get_all_admins()
    msg = "👥 **Admin List**\n\n"
    for admin in admins:
        owner_tag = " 👑 OWNER" if admin.get("is_owner") else ""
        username = admin.get("username") or f"ID: {admin['_id']}"
        msg += f"• `{admin['_id']}` - {username}{owner_tag}\n"
    
    bot.send_message(m.from_user.id, msg, parse_mode="Markdown")

# =========================
# 📞 SET CONTACTS
# =========================
@bot.message_handler(func=lambda m: m.text == "📞 Set Contacts" and is_admin(m.from_user.id))
def set_contacts_menu(m):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📞 Set Points Contact", callback_data="set_points_contact"),
        InlineKeyboardButton("⭐ Set VIP Contact", callback_data="set_vip_contact"),
        InlineKeyboardButton("📋 View Contacts", callback_data="view_contacts")
    )
    bot.send_message(m.from_user.id, "📞 **Contact Settings**\n\nSelect an option:", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "set_points_contact")
def set_points_contact(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Admin only!")
        return
    
    msg = bot.send_message(c.from_user.id, 
        "📞 **Set Points Purchase Contact**\n\n"
        "Send username (with @) or link:\n"
        "Example: `@username` or `https://t.me/username`\n\n"
        "Send `none` to remove",
        parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_points_contact)

def save_points_contact(m):
    if m.text.lower() == "none":
        set_config("contact_username", None)
        set_config("contact_link", None)
        bot.send_message(m.from_user.id, "✅ Points contact removed!", reply_markup=admin_menu())
    elif m.text.startswith("http"):
        set_config("contact_link", m.text)
        set_config("contact_username", None)
        bot.send_message(m.from_user.id, f"✅ Points contact link set: {m.text}", reply_markup=admin_menu())
    elif m.text.startswith("@"):
        set_config("contact_username", m.text)
        set_config("contact_link", None)
        bot.send_message(m.from_user.id, f"✅ Points contact username set: {m.text}", reply_markup=admin_menu())
    else:
        bot.send_message(m.from_user.id, "❌ Invalid format! Use @username or https://t.me/username")

@bot.callback_query_handler(func=lambda c: c.data == "set_vip_contact")
def set_vip_contact(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Admin only!")
        return
    
    msg = bot.send_message(c.from_user.id, 
        "⭐ **Set VIP Purchase Contact**\n\n"
        "Send username (with @) or link:\n"
        "Example: `@username` or `https://t.me/username`\n\n"
        "Send `none` to remove",
        parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_vip_contact)

def save_vip_contact(m):
    if m.text.lower() == "none":
        set_config("vip_contact", None)
        bot.send_message(m.from_user.id, "✅ VIP contact removed!", reply_markup=admin_menu())
    elif m.text.startswith("http"):
        set_config("vip_contact", m.text)
        bot.send_message(m.from_user.id, f"✅ VIP contact link set: {m.text}", reply_markup=admin_menu())
    elif m.text.startswith("@"):
        set_config("vip_contact", m.text)
        bot.send_message(m.from_user.id, f"✅ VIP contact username set: {m.text}", reply_markup=admin_menu())
    else:
        bot.send_message(m.from_user.id, "❌ Invalid format! Use @username or https://t.me/username")

@bot.callback_query_handler(func=lambda c: c.data == "view_contacts")
def view_contacts(c):
    cfg = get_cached_config()
    points_contact = cfg.get("contact_username") or cfg.get("contact_link") or "Not set"
    vip_contact = cfg.get("vip_contact") or "Not set"
    
    msg = "📞 **Current Contacts**\n\n"
    msg += f"💰 **Points Purchase:** {points_contact}\n"
    msg += f"⭐ **VIP Purchase:** {vip_contact}\n"
    
    bot.edit_message_text(msg, c.from_user.id, c.message.message_id, parse_mode="Markdown")
    bot.answer_callback_query(c.id)

# =========================
# 🔗 ADD CUSTOM LINK (FIXED)
# =========================
@bot.message_handler(func=lambda m: m.text == "🔗 Add Custom Link" and is_admin(m.from_user.id))
def add_custom_link_start(m):
    msg = bot.send_message(m.from_user.id, 
        "🔗 **Add Custom Link Button**\n\n"
        "Send: `button_text|url`\n\n"
        "Example: `WhatsApp Channel|https://whatsapp.com/channel/...`\n\n"
        "The button will appear in the main menu!",
        parse_mode="Markdown")
    bot.register_next_step_handler(msg, add_custom_link_process)

def add_custom_link_process(m):
    try:
        parts = m.text.split("|")
        if len(parts) != 2:
            bot.send_message(m.from_user.id, "❌ Invalid format! Use: text|url")
            return
        
        text = parts[0].strip()
        url = parts[1].strip()
        
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        
        add_custom_button(text, "link", url)
        bot.send_message(m.from_user.id, f"✅ Custom link added!\n\n📌 **{text}**\n🔗 {url}\n\nThe button will appear in the main menu.", parse_mode="Markdown", reply_markup=admin_menu())
    except Exception as e:
        bot.send_message(m.from_user.id, f"❌ Error: {str(e)}\n\nUse format: `text|url`", parse_mode="Markdown")

# =========================
# 📋 VIEW LINKS
# =========================
@bot.message_handler(func=lambda m: m.text == "📋 View Links" and is_admin(m.from_user.id))
def view_links(m):
    buttons = get_custom_buttons()
    if not buttons:
        bot.send_message(m.from_user.id, "📋 No custom buttons added yet!\n\nUse 🔗 Add Custom Link to add buttons.", parse_mode="Markdown")
        return
    
    msg = "📋 **Your Custom Buttons**\n\n"
    for i, btn in enumerate(buttons, 1):
        msg += f"{i}. **{btn['text']}**\n"
        msg += f"   Type: `{btn['type']}`\n"
        if btn['type'] == 'link':
            msg += f"   URL: {btn['data']}\n"
        elif btn['type'] == 'folder':
            msg += f"   Folder: #{btn['data']}\n"
        msg += "\n"
    
    msg += f"Total: {len(buttons)} button(s)"
    
    bot.send_message(m.from_user.id, msg, parse_mode="Markdown")

# =========================
# ➕ ADD MAIN BUTTON
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ Add Main Button" and is_admin(m.from_user.id))
def add_button_start(m):
    msg = bot.send_message(m.from_user.id, 
        "🔘 **Add Main Menu Button**\n\n"
        "Send: button_type|button_text|button_data\n\n"
        "Types:\n"
        "• `link` - Opens URL\n"
        "• `folder` - Opens folder (use folder number as data)\n\n"
        "Examples:\n"
        "`link|Website|https://example.com`\n"
        "`folder|My Folder|5`",
        parse_mode="Markdown")
    bot.register_next_step_handler(msg, add_button_process)

def add_button_process(m):
    try:
        parts = m.text.split("|")
        if len(parts) != 3:
            bot.send_message(m.from_user.id, "❌ Invalid format! Use: type|text|data")
            return
        
        btn_type = parts[0].lower()
        btn_text = parts[1]
        btn_data = parts[2]
        
        if btn_type not in ["link", "folder"]:
            bot.send_message(m.from_user.id, "❌ Invalid type! Use: link or folder")
            return
        
        if btn_type == "folder":
            folder = fs.get_by_number(int(btn_data))
            if not folder:
                bot.send_message(m.from_user.id, f"❌ Folder #{btn_data} not found!")
                return
        
        add_custom_button(btn_text, btn_type, btn_data)
        bot.send_message(m.from_user.id, f"✅ Button added: {btn_text}", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid format! Use: type|text|data")

@bot.message_handler(func=lambda m: m.text == "➖ Remove Main Button" and is_admin(m.from_user.id))
def remove_button_start(m):
    buttons = get_custom_buttons()
    if not buttons:
        bot.send_message(m.from_user.id, "❌ No buttons to remove!")
        return
    
    kb = InlineKeyboardMarkup(row_width=1)
    for btn in buttons:
        kb.add(InlineKeyboardButton(f"❌ {btn['text']}", callback_data=f"rmbtn|{btn['text']}"))
    
    bot.send_message(m.from_user.id, "🔘 **Remove Button**\n\nSelect button:", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("rmbtn|"))
def remove_button_process(c):
    button_text = c.data.split("|")[1]
    remove_custom_button(button_text)
    bot.edit_message_text(f"✅ Removed: {button_text}", c.from_user.id, c.message.message_id)
    bot.answer_callback_query(c.id)

# =========================
# ➕ ADD FORCE JOIN
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ Add Force Join" and is_admin(m.from_user.id))
def add_force_join(m):
    msg = bot.send_message(m.from_user.id, "➕ **Add Force Join**\n\nSend channel username (with @):", parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_force_join)

def save_force_join(m):
    cfg = get_config()
    chs = cfg.get("force_channels", [])
    channel = m.text.strip()
    
    if channel not in chs:
        chs.append(channel)
        set_config("force_channels", chs)
        bot.send_message(m.from_user.id, f"✅ Force join added: {channel}", reply_markup=admin_menu())
    else:
        bot.send_message(m.from_user.id, "❌ Already exists!")

@bot.message_handler(func=lambda m: m.text == "➖ Remove Force Join" and is_admin(m.from_user.id))
def remove_force_join(m):
    cfg = get_config()
    chs = cfg.get("force_channels", [])
    
    if not chs:
        bot.send_message(m.from_user.id, "❌ No channels!")
        return
    
    kb = InlineKeyboardMarkup(row_width=1)
    for ch in chs:
        kb.add(InlineKeyboardButton(f"❌ {ch}", callback_data=f"rmfj|{ch}"))
    
    bot.send_message(m.from_user.id, "🔘 **Remove Force Join**\n\nSelect channel:", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("rmfj|"))
def remove_force_join_process(c):
    channel = c.data.split("|")[1]
    cfg = get_config()
    chs = cfg.get("force_channels", [])
    
    if channel in chs:
        chs.remove(channel)
        set_config("force_channels", chs)
        bot.edit_message_text(f"✅ Removed: {channel}", c.from_user.id, c.message.message_id)
    else:
        bot.edit_message_text(f"❌ Not found!", c.from_user.id, c.message.message_id)
    
    bot.answer_callback_query(c.id)

# =========================
# 📤 UPLOAD SYSTEM (KEPT SAME)
# =========================
def start_upload(uid, cat, is_service=False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📄 Text Method", "📁 File Method")
    kb.row("/cancel")
    
    msg = bot.send_message(uid, f"📤 **Upload to {cat.upper()}**\n\nChoose method type:", reply_markup=kb, parse_mode="Markdown")
    bot.register_next_step_handler(msg, lambda m: upload_type_choice(m, cat, is_service))

def upload_type_choice(m, cat, is_service):
    if m.text == "/cancel":
        bot.send_message(m.from_user.id, "❌ Upload cancelled", reply_markup=admin_menu())
        return
    
    if m.text == "📄 Text Method":
        msg = bot.send_message(m.from_user.id, "📝 **Folder name:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda x: upload_text_name(x, cat, is_service))
    elif m.text == "📁 File Method":
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row("/done", "/cancel")
        msg = bot.send_message(m.from_user.id, f"📤 **Upload files for {cat.upper()}**\n\nSend files:\nPress /done when finished", reply_markup=kb, parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda x: upload_file_step(x, cat, m.from_user.id, [], is_service))
    else:
        bot.send_message(m.from_user.id, "❌ Invalid choice!", reply_markup=admin_menu())

def upload_text_name(m, cat, is_service):
    name = m.text
    msg = bot.send_message(m.from_user.id, "💰 **Price (points):**\n\nEnter 0 for free:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, lambda x: upload_text_price(x, cat, name, is_service))

def upload_text_price(m, cat, name, is_service):
    try:
        price = int(m.text)
        msg = bot.send_message(m.from_user.id, "📝 **Enter the text/content:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda x: upload_text_save(x, cat, name, price, is_service))
    except:
        bot.send_message(m.from_user.id, "❌ Invalid price!")

def upload_text_save(m, cat, name, price, is_service):
    text_content = m.text
    number = fs.add(cat, name, [], price, text_content=text_content)
    
    if is_service:
        folders_col.update_one(
            {"cat": cat, "name": name},
            {"$set": {"service_msg": text_content}}
        )
    
    bot.send_message(m.from_user.id, 
        f"✅ **{'Service' if is_service else 'Method'} added!**\n\n"
        f"📌 Number: `{number}`\n"
        f"📂 Name: {name}\n"
        f"💰 Price: {price} points\n"
        f"📝 Type: Text Method",
        parse_mode="Markdown", reply_markup=admin_menu())

def upload_file_step(m, cat, uid, files, is_service):
    if m.text == "/cancel":
        bot.send_message(uid, "❌ Upload cancelled", reply_markup=admin_menu())
        return
    
    if m.text == "/done":
        if not files:
            bot.send_message(uid, "❌ No files uploaded!")
            return
        
        msg = bot.send_message(uid, "📝 **Folder name:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda x: upload_file_name(x, cat, files, is_service))
        return
    
    if m.content_type in ["document", "photo", "video"]:
        files.append({
            "chat": m.chat.id,
            "msg": m.message_id,
            "type": m.content_type
        })
        bot.send_message(uid, f"✅ Saved ({len(files)} files)")
    
    bot.register_next_step_handler(m, lambda x: upload_file_step(x, cat, uid, files, is_service))

def upload_file_name(m, cat, files, is_service):
    name = m.text
    msg = bot.send_message(m.from_user.id, "💰 **Price (points):**\n\nEnter 0 for free:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, lambda x: upload_file_save(x, cat, name, files, is_service))

def upload_file_save(m, cat, name, files, is_service):
    try:
        price = int(m.text)
        number = fs.add(cat, name, files, price)
        
        if is_service:
            msg = bot.send_message(m.from_user.id, "📝 **Service message:**", parse_mode="Markdown")
            bot.register_next_step_handler(msg, lambda x: service_msg_save(x, cat, name, number, price, files))
        else:
            bot.send_message(m.from_user.id, 
                f"✅ **Upload successful!**\n\n"
                f"📌 Number: `{number}`\n"
                f"📂 Name: {name}\n"
                f"💰 Price: {price} points\n"
                f"📁 Files: {len(files)}",
                parse_mode="Markdown", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid price!")

def service_msg_save(m, cat, name, number, price, files):
    service_msg = m.text
    folders_col.update_one(
        {"cat": cat, "name": name},
        {"$set": {"service_msg": service_msg}}
    )
    bot.send_message(m.from_user.id, 
        f"✅ **Service added!**\n\n"
        f"📌 Number: `{number}`\n"
        f"📂 Name: {name}\n"
        f"💰 Price: {price} points\n"
        f"📁 Files: {len(files)}",
        parse_mode="Markdown", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📦 Upload FREE" and is_admin(m.from_user.id))
def up_free(m): start_upload(m.from_user.id, "free")

@bot.message_handler(func=lambda m: m.text == "💎 Upload VIP" and is_admin(m.from_user.id))
def up_vip(m): start_upload(m.from_user.id, "vip")

@bot.message_handler(func=lambda m: m.text == "📱 Upload APPS" and is_admin(m.from_user.id))
def up_apps(m): start_upload(m.from_user.id, "apps")

@bot.message_handler(func=lambda m: m.text == "⚡ Upload SERVICE" and is_admin(m.from_user.id))
def up_service(m): start_upload(m.from_user.id, "services", is_service=True)

# =========================
# 📁 CREATE SUBFOLDER
# =========================
@bot.message_handler(func=lambda m: m.text == "📁 Create Subfolder" and is_admin(m.from_user.id))
def create_subfolder(m):
    msg = bot.send_message(m.from_user.id, "📝 **Create Subfolder**\n\nSend: category parent_folder_name subfolder_name price\n\nExample: `free MainFolder SubFolder 10`\n\nUse 0 for free", parse_mode="Markdown")
    bot.register_next_step_handler(msg, create_subfolder_process)

def create_subfolder_process(m):
    try:
        parts = m.text.split(maxsplit=3)
        if len(parts) < 4:
            bot.send_message(m.from_user.id, "❌ Invalid format! Use: category parent name price")
            return
        
        cat = parts[0].lower()
        parent = parts[1]
        name = parts[2]
        price = int(parts[3])
        
        if cat not in ["free", "vip", "apps", "services"]:
            bot.send_message(m.from_user.id, "❌ Invalid category!")
            return
        
        parent_folder = fs.get_one(cat, parent)
        if not parent_folder:
            bot.send_message(m.from_user.id, f"❌ Parent folder '{parent}' not found!")
            return
        
        number = fs.add(cat, name, [], price, parent)
        bot.send_message(m.from_user.id, f"✅ Subfolder created!\n\n📌 Number: `{number}`\n📂 {parent} → {name}\n💰 Price: {price} points", parse_mode="Markdown", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid format! Use: category parent name price")

# =========================
# 🔀 MOVE FOLDER
# =========================
@bot.message_handler(func=lambda m: m.text == "🔀 Move Folder" and is_admin(m.from_user.id))
def move_folder_start(m):
    msg = bot.send_message(m.from_user.id, "🔀 **Move Folder**\n\nSend: folder_number new_parent\n\nExample: `5 root` or `5 MainFolder`\n\nUse 'root' for main level", parse_mode="Markdown")
    bot.register_next_step_handler(msg, move_folder_process)

def move_folder_process(m):
    try:
        parts = m.text.split()
        number = int(parts[0])
        new_parent = parts[1] if parts[1] != "root" else None
        
        folder = fs.get_by_number(number)
        if not folder:
            bot.send_message(m.from_user.id, "❌ Folder not found!")
            return
        
        fs.move_folder(number, new_parent)
        bot.send_message(m.from_user.id, f"✅ Folder #{number} moved successfully!", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid format! Use: number new_parent")

# =========================
# 🗑 DELETE FOLDER
# =========================
@bot.message_handler(func=lambda m: m.text == "🗑 Delete Folder" and is_admin(m.from_user.id))
def del_start(m):
    msg = bot.send_message(m.from_user.id, "🗑 **DELETE FOLDER**\n\nSend: `category folder_name`\n\nCategories: `free`, `vip`, `apps`, `services`\n\nExample: `services Amazon Prime`\n\n⚠️ This will delete the folder AND all its subfolders!", parse_mode="Markdown")
    bot.register_next_step_handler(msg, del_folder)

def del_folder(m):
    try:
        parts = m.text.split(maxsplit=1)
        if len(parts) != 2:
            bot.send_message(m.from_user.id, "❌ Invalid format! Use: category folder_name")
            return
        
        cat = parts[0].lower()
        name = parts[1].strip()
        
        if cat not in ["free", "vip", "apps", "services"]:
            bot.send_message(m.from_user.id, "❌ Invalid category! Use: free, vip, apps, services")
            return
        
        folder = fs.get_one(cat, name)
        if not folder:
            all_folders = fs.get(cat)
            for f in all_folders:
                if f["name"].lower() == name.lower():
                    folder = f
                    name = f["name"]
                    break
        
        if not folder:
            bot.send_message(m.from_user.id, f"❌ Folder '{name}' not found in {cat.upper()}!")
            return
        
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("✅ YES, DELETE", callback_data=f"confirm_del|{cat}|{name}"),
            InlineKeyboardButton("❌ NO, CANCEL", callback_data="cancel_del")
        )
        
        subfolders = fs.get(cat, name)
        sub_count = len(subfolders)
        
        confirm_msg = f"⚠️ **CONFIRM DELETION** ⚠️\n\n"
        confirm_msg += f"📂 **Category:** {cat.upper()}\n"
        confirm_msg += f"📛 **Folder:** {name}\n"
        confirm_msg += f"📁 **Subfolders:** {sub_count}\n\n"
        confirm_msg += f"🗑️ This will delete the folder AND all its subfolders!\n\n"
        confirm_msg += f"**This action cannot be undone!**"
        
        bot.send_message(m.from_user.id, confirm_msg, reply_markup=kb, parse_mode="Markdown")
        
    except Exception as e:
        bot.send_message(m.from_user.id, f"❌ Error: {str(e)}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("confirm_del|"))
def confirm_delete(c):
    _, cat, name = c.data.split("|")
    
    if fs.delete(cat, name):
        bot.edit_message_text(
            f"✅ **DELETED SUCCESSFULLY!**\n\n"
            f"Removed: {cat.upper()} → {name}\n"
            f"All subfolders were also deleted.",
            c.from_user.id,
            c.message.message_id,
            parse_mode="Markdown"
        )
        bot.send_message(c.from_user.id, "✅ Folder deleted!", reply_markup=admin_menu())
    else:
        bot.edit_message_text(
            f"❌ **FOLDER NOT FOUND!**\n\n"
            f"Could not find: {cat.upper()} → {name}",
            c.from_user.id,
            c.message.message_id,
            parse_mode="Markdown"
        )
    
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "cancel_del")
def cancel_delete(c):
    bot.edit_message_text("❌ Deletion cancelled", c.from_user.id, c.message.message_id)
    bot.send_message(c.from_user.id, "Returning to admin panel...", reply_markup=admin_menu())
    bot.answer_callback_query(c.id)

# =========================
# ✏️ EDIT PRICE
# =========================
@bot.message_handler(func=lambda m: m.text == "✏️ Edit Price" and is_admin(m.from_user.id))
def edit_price_start(m):
    msg = bot.send_message(m.from_user.id, "✏️ **Edit Price**\n\nSend: category folder_name new_price\n\nExample: `vip My Method 50`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, edit_price_process)

def edit_price_process(m):
    try:
        parts = m.text.split()
        cat = parts[0].lower()
        name = " ".join(parts[1:-1])
        price = int(parts[-1])
        
        if cat not in ["free", "vip", "apps", "services"]:
            bot.send_message(m.from_user.id, "❌ Invalid category!")
            return
        
        fs.edit_price(cat, name, price)
        bot.send_message(m.from_user.id, f"✅ Price updated: {price} points", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid format! Use: category folder_name price")

# =========================
# ✏️ EDIT NAME
# =========================
@bot.message_handler(func=lambda m: m.text == "✏️ Edit Name" and is_admin(m.from_user.id))
def edit_name_start(m):
    msg = bot.send_message(m.from_user.id, "✏️ **Edit Name**\n\nSend: category old_name new_name\n\nExample: `free OldName NewName`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, edit_name_process)

def edit_name_process(m):
    try:
        parts = m.text.split(maxsplit=2)
        cat = parts[0].lower()
        old_name = parts[1]
        new_name = parts[2]
        
        if cat not in ["free", "vip", "apps", "services"]:
            bot.send_message(m.from_user.id, "❌ Invalid category!")
            return
        
        fs.edit_name(cat, old_name, new_name)
        bot.send_message(m.from_user.id, f"✅ Renamed: {old_name} → {new_name}", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid format! Use: category old_name new_name")

# =========================
# 📝 EDIT CONTENT
# =========================
edit_sessions = {}

@bot.message_handler(func=lambda m: m.text == "📝 Edit Content" and is_admin(m.from_user.id))
def edit_content_start(m):
    msg = bot.send_message(m.from_user.id, "📝 **Edit Folder Content**\n\nFirst, send the folder details:\n\nSend: `category folder_name`\n\nExample: `vip My Method`\n\nThis will let you edit the content (text or files).", parse_mode="Markdown")
    bot.register_next_step_handler(msg, edit_content_select)

def edit_content_select(m):
    uid = m.from_user.id
    
    try:
        parts = m.text.split(maxsplit=1)
        if len(parts) != 2:
            bot.send_message(uid, "❌ Invalid format! Use: category folder_name")
            return
        
        cat = parts[0].lower()
        name = parts[1].strip()
        
        if cat not in ["free", "vip", "apps", "services"]:
            bot.send_message(uid, "❌ Invalid category! Use: free, vip, apps, or services")
            return
        
        folder = fs.get_one(cat, name)
        if not folder:
            bot.send_message(uid, f"❌ Folder '{name}' not found in {cat.upper()}!")
            return
        
        edit_sessions[uid] = {"cat": cat, "name": name}
        
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("📝 Edit Text", callback_data="edit_text_content"),
            InlineKeyboardButton("📁 Edit Files", callback_data="edit_files_content"),
            InlineKeyboardButton("❌ Cancel", callback_data="edit_cancel")
        )
        
        bot.send_message(uid, f"📝 **Edit: {name}**\n\nWhat would you like to edit?", reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(uid, f"❌ Error: {str(e)}")

@bot.callback_query_handler(func=lambda c: c.data == "edit_text_content")
def edit_text_cb(c):
    uid = c.from_user.id
    if uid not in edit_sessions:
        bot.answer_callback_query(c.id, "Session expired!")
        return
    
    s = edit_sessions[uid]
    folder = fs.get_one(s["cat"], s["name"])
    current = folder.get("text_content", "No content")
    preview = current[:300] + "..." if len(current) > 300 else current
    
    msg = bot.send_message(uid, f"📝 **Current Content:**\n{preview}\n\nSend NEW text:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_edit_text)
    bot.answer_callback_query(c.id)

def save_edit_text(m):
    uid = m.from_user.id
    if uid not in edit_sessions:
        bot.send_message(uid, "Session expired!", reply_markup=admin_menu())
        return
    
    s = edit_sessions[uid]
    fs.edit_content(s["cat"], s["name"], "text", m.text)
    bot.send_message(uid, f"✅ Text updated for {s['name']}!", reply_markup=admin_menu())
    edit_sessions.pop(uid, None)

@bot.callback_query_handler(func=lambda c: c.data == "edit_files_content")
def edit_files_cb(c):
    uid = c.from_user.id
    if uid not in edit_sessions:
        bot.answer_callback_query(c.id, "Session expired!")
        return
    
    edit_sessions[uid]["new_files"] = []
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("/done", "/cancel")
    msg = bot.send_message(uid, "📁 Send NEW files (will replace all)\n/done when finished:", reply_markup=kb, parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_edit_files)
    bot.answer_callback_query(c.id)

def process_edit_files(m):
    uid = m.from_user.id
    if m.text == "/cancel":
        edit_sessions.pop(uid, None)
        bot.send_message(uid, "❌ Cancelled!", reply_markup=admin_menu())
        return
    
    if m.text == "/done":
        if uid not in edit_sessions:
            bot.send_message(uid, "Session expired!")
            return
        
        s = edit_sessions[uid]
        if not s.get("new_files"):
            bot.send_message(uid, "❌ No files!")
            return
        
        fs.edit_content(s["cat"], s["name"], "files", s["new_files"])
        bot.send_message(uid, f"✅ Files updated! {len(s['new_files'])} file(s)", reply_markup=admin_menu())
        edit_sessions.pop(uid, None)
        return
    
    if m.content_type in ["document", "photo", "video"]:
        edit_sessions[uid]["new_files"].append({"chat": m.chat.id, "msg": m.message_id, "type": m.content_type})
        bot.send_message(uid, f"✅ Saved ({len(edit_sessions[uid]['new_files'])} files)")
    else:
        bot.send_message(uid, "❌ Send documents, photos, or videos!")
    
    bot.register_next_step_handler(m, process_edit_files)

@bot.callback_query_handler(func=lambda c: c.data == "edit_cancel")
def edit_cancel_cb(c):
    edit_sessions.pop(c.from_user.id, None)
    bot.edit_message_text("❌ Cancelled", c.from_user.id, c.message.message_id)
    bot.send_message(c.from_user.id, "Returning...", reply_markup=admin_menu())
    bot.answer_callback_query(c.id)

# =========================
# 👑 ADD VIP
# =========================
@bot.message_handler(func=lambda m: m.text == "👑 Add VIP" and is_admin(m.from_user.id))
def add_vip_start(m):
    msg = bot.send_message(m.from_user.id, "👑 **Add VIP User**\n\nSend user ID or @username:", parse_mode="Markdown")
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
            bot.send_message(m.from_user.id, f"❌ User not found!")
            return
    else:
        try:
            user_id = int(user_input)
        except:
            bot.send_message(m.from_user.id, "❌ Invalid ID!")
            return
    
    try:
        user = User(user_id)
        if user.is_vip():
            bot.send_message(m.from_user.id, f"⚠️ User already VIP!")
            return
        
        cfg = get_config()
        user.make_vip(cfg.get("vip_duration_days", 30))
        bot.send_message(m.from_user.id, f"✅ User is now VIP!")
        
        try:
            duration_msg = ""
            if cfg.get("vip_duration_days", 30) > 0:
                duration_msg = f"\n\n⏰ VIP Duration: {cfg.get('vip_duration_days', 30)} days"
            
            bot.send_message(user_id, 
                "🎉 **CONGRATULATIONS!** 🎉\n\n"
                "You are now **VIP**!\n\n"
                "✨ **VIP Benefits:**\n"
                "• Access to all VIP methods\n"
                "• Priority support\n"
                "• Exclusive content\n"
                f"{duration_msg}\n\n"
                f"💰 Your points: `{user.points()}`",
                parse_mode="Markdown")
        except:
            pass
    except Exception as e:
        bot.send_message(m.from_user.id, f"❌ Error: {str(e)}")

# =========================
# 👑 REMOVE VIP
# =========================
@bot.message_handler(func=lambda m: m.text == "👑 Remove VIP" and is_admin(m.from_user.id))
def remove_vip_start(m):
    msg = bot.send_message(m.from_user.id, "👑 **Remove VIP**\n\nSend user ID or @username:", parse_mode="Markdown")
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
            bot.send_message(m.from_user.id, f"❌ User not found!")
            return
    else:
        try:
            user_id = int(user_input)
        except:
            bot.send_message(m.from_user.id, "❌ Invalid ID!")
            return
    
    try:
        user = User(user_id)
        if not user.is_vip():
            bot.send_message(m.from_user.id, f"⚠️ User is not VIP!")
            return
        
        user.remove_vip()
        bot.send_message(m.from_user.id, f"✅ VIP removed!")
        
        try:
            bot.send_message(user_id, 
                "⚠️ **VIP Status Removed**\n\n"
                "Your VIP membership has been removed.\n\n"
                f"💰 Your points: `{user.points()}`",
                parse_mode="Markdown")
        except:
            pass
    except Exception as e:
        bot.send_message(m.from_user.id, f"❌ Error: {str(e)}")

# =========================
# 💰 GIVE POINTS
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 Give Points" and is_admin(m.from_user.id))
def give_points_start(m):
    msg = bot.send_message(m.from_user.id, 
        "💰 **Give Points**\n\n"
        "Send: `user_id points`\n\n"
        "Example: `123456789 100`\n\n"
        "*User must have started the bot first*",
        parse_mode="Markdown")
    bot.register_next_step_handler(msg, give_points_process)

def give_points_process(m):
    try:
        parts = m.text.split()
        if len(parts) != 2:
            bot.send_message(m.from_user.id, "❌ Use: user_id points")
            return
        
        uid = parts[0]
        pts = int(parts[1])
        
        if pts <= 0:
            bot.send_message(m.from_user.id, "❌ Points must be > 0!")
            return
        if pts > 1000000:
            bot.send_message(m.from_user.id, "⚠️ Max 1,000,000 points!")
            return
        
        user_data = users_col.find_one({"_id": uid})
        if not user_data:
            bot.send_message(m.from_user.id, f"❌ User {uid} not found! Send /start first.")
            return
        
        user = User(uid)
        old = user.points()
        user.add_points(pts)
        
        username = user.username()
        display = f"@{username}" if username else f"ID: {uid}"
        
        bot.send_message(m.from_user.id, 
            f"✅ **Added +{pts} points to {display}**\nOld: {old} → New: {user.points()}")
        
        try:
            bot.send_message(int(uid), f"🎉 **+{pts} points received!**\n💰 New balance: {user.points()} pts")
        except:
            pass
    except:
        bot.send_message(m.from_user.id, "❌ Invalid format!")

# =========================
# 🏆 GENERATE CODES
# =========================
@bot.message_handler(func=lambda m: m.text == "🏆 Generate Codes" and is_admin(m.from_user.id))
def gen_codes_start(m):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Single Use", callback_data="gen|single"))
    kb.add(InlineKeyboardButton("Multi Use", callback_data="gen|multi"))
    bot.send_message(m.from_user.id, "🎫 **Generate Codes**\n\nChoose type:", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("gen|"))
def gen_codes_type(c):
    code_type = c.data.split("|")[1]
    multi_use = (code_type == "multi")
    
    msg = bot.send_message(c.from_user.id, "💰 **Points per code:**", parse_mode="Markdown")
    bot.register_next_step_handler(msg, lambda x: gen_codes_points(x, multi_use))

def gen_codes_points(m, multi_use):
    try:
        pts = int(m.text)
        if pts <= 0:
            bot.send_message(m.from_user.id, "❌ Points must be > 0!")
            return
        msg = bot.send_message(m.from_user.id, "🔢 **How many codes? (1-100)**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda x: gen_codes_count(x, pts, multi_use))
    except:
        bot.send_message(m.from_user.id, "❌ Invalid number!")

def gen_codes_count(m, pts, multi_use):
    try:
        count = int(m.text)
        if count <= 0 or count > 100:
            bot.send_message(m.from_user.id, "❌ Count: 1-100")
            return
        
        if multi_use:
            msg = bot.send_message(m.from_user.id, "📅 **Expiry days?** (0 = no expiry):", parse_mode="Markdown")
            bot.register_next_step_handler(msg, lambda x: gen_codes_expiry(x, pts, count, multi_use))
        else:
            codes = codesys.generate(pts, count, multi_use)
            codes_list = "\n".join(codes)
            bot.send_message(m.from_user.id, 
                f"✅ **Generated {count} codes!**\n\n"
                f"📊 Points each: `{pts}`\n"
                f"🔑 Type: {'Multi-use' if multi_use else 'Single-use'}\n\n"
                f"```\n{codes_list}\n```",
                parse_mode="Markdown", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid number!")

def gen_codes_expiry(m, pts, count, multi_use):
    try:
        expiry_days = int(m.text) if m.text != "0" else None
        codes = codesys.generate(pts, count, multi_use, expiry_days)
        codes_list = "\n".join(codes)
        
        expiry_msg = f"Expiry: {expiry_days} days" if expiry_days else "No expiry"
        
        bot.send_message(m.from_user.id, 
            f"✅ **Generated {count} codes!**\n\n"
            f"📊 Points each: `{pts}`\n"
            f"🔑 Type: {'Multi-use' if multi_use else 'Single-use'}\n"
            f"⏰ {expiry_msg}\n\n"
            f"```\n{codes_list}\n```",
            parse_mode="Markdown", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid number!")

# =========================
# 📊 VIEW CODES
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 View Codes" and is_admin(m.from_user.id))
def view_codes(m):
    codes = codesys.get_all_codes()
    
    if not codes:
        bot.send_message(m.from_user.id, "📊 No codes generated!")
        return
    
    total, used, unused, multi = codesys.get_stats()
    
    stats_msg = f"📊 **Code Statistics**\n\n"
    stats_msg += f"┌ Total: `{total}`\n"
    stats_msg += f"├ Used: `{used}`\n"
    stats_msg += f"├ Unused: `{unused}`\n"
    stats_msg += f"└ Multi-Use: `{multi}`\n\n"
    
    unused_codes = [c for c in codes if not c.get("used", False)][:10]
    if unused_codes:
        stats_msg += "**Recent Unused Codes:**\n"
        for code_data in unused_codes[:5]:
            stats_msg += f"• `{code_data['_id']}` - {code_data['points']} pts\n"
    
    bot.send_message(m.from_user.id, stats_msg, parse_mode="Markdown")

# =========================
# 📊 STATISTICS
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 Stats" and is_admin(m.from_user.id))
def show_stats(m):
    users = list(users_col.find({}))
    
    total = len(users)
    vip = sum(1 for u in users if u.get("vip", False))
    free = total - vip
    
    total_points = sum(u.get("points", 0) for u in users)
    total_earned = sum(u.get("total_points_earned", 0) for u in users)
    total_spent = sum(u.get("total_points_spent", 0) for u in users)
    total_refs = sum(u.get("refs", 0) for u in users)
    total_purchases = sum(len(u.get("purchased_methods", [])) for u in users)
    
    free_folders = folders_col.count_documents({"cat": "free"})
    vip_folders = folders_col.count_documents({"cat": "vip"})
    apps_folders = folders_col.count_documents({"cat": "apps"})
    services_folders = folders_col.count_documents({"cat": "services"})
    
    stats_msg = f"📊 **ZEDOX STATISTICS**\n\n"
    stats_msg += f"👥 **Users:**\n"
    stats_msg += f"┌ Total: `{total}`\n"
    stats_msg += f"├ VIP: `{vip}`\n"
    stats_msg += f"└ Free: `{free}`\n\n"
    
    stats_msg += f"💰 **Points:**\n"
    stats_msg += f"┌ Current Total: `{total_points:,}`\n"
    stats_msg += f"├ Total Earned: `{total_earned:,}`\n"
    stats_msg += f"├ Total Spent: `{total_spent:,}`\n"
    stats_msg += f"└ Avg per User: `{total_points//total if total > 0 else 0}`\n\n"
    
    stats_msg += f"📚 **Content:**\n"
    stats_msg += f"┌ FREE: `{free_folders}`\n"
    stats_msg += f"├ VIP: `{vip_folders}`\n"
    stats_msg += f"├ APPS: `{apps_folders}`\n"
    stats_msg += f"└ SERVICES: `{services_folders}`\n\n"
    
    stats_msg += f"📈 **Activity:**\n"
    stats_msg += f"┌ Referrals: `{total_refs}`\n"
    stats_msg += f"├ Purchases: `{total_purchases}`\n"
    stats_msg += f"└ Codes: `{codes_col.count_documents({})}`"
    
    bot.send_message(m.from_user.id, stats_msg, parse_mode="Markdown")

# =========================
# 📦 POINTS PACKAGES MANAGEMENT
# =========================
@bot.message_handler(func=lambda m: m.text == "📦 Points Packages" and is_admin(m.from_user.id))
def manage_packages(m):
    packages = get_points_packages()
    
    message = f"📦 **Points Packages**\n\n"
    message += f"Current packages:\n\n"
    
    for i, pkg in enumerate(packages, 1):
        status = "✅ Active" if pkg.get("active", True) else "❌ Inactive"
        message += f"{i}. **{pkg['points']} pts** - ${pkg['price']}\n"
        if pkg.get("bonus", 0) > 0:
            message += f"   Bonus: +{pkg['bonus']} pts\n"
        message += f"   Status: {status}\n\n"
    
    message += f"Commands:\n"
    message += f"/addpackage points price bonus\n"
    message += f"/editpackage number points price bonus\n"
    message += f"/togglepackage number\n"
    message += f"/delpackage number"
    
    bot.send_message(m.from_user.id, message, parse_mode="Markdown")

@bot.message_handler(commands=["addpackage"])
def add_package(m):
    if not is_admin(m.from_user.id):
        return
    
    try:
        _, points, price, bonus = m.text.split()
        points = int(points)
        price = int(price)
        bonus = int(bonus)
        
        packages = get_points_packages()
        packages.append({
            "points": points,
            "price": price,
            "currency": "USD",
            "bonus": bonus,
            "active": True
        })
        save_points_packages(packages)
        
        bot.send_message(m.from_user.id, f"✅ Package added: {points} pts for ${price} (+{bonus} bonus)")
    except:
        bot.send_message(m.from_user.id, "❌ Use: /addpackage points price bonus")

@bot.message_handler(commands=["editpackage"])
def edit_package(m):
    if not is_admin(m.from_user.id):
        return
    
    try:
        _, num, points, price, bonus = m.text.split()
        num = int(num) - 1
        points = int(points)
        price = int(price)
        bonus = int(bonus)
        
        packages = get_points_packages()
        if 0 <= num < len(packages):
            packages[num]["points"] = points
            packages[num]["price"] = price
            packages[num]["bonus"] = bonus
            save_points_packages(packages)
            bot.send_message(m.from_user.id, f"✅ Package {num+1} updated!")
        else:
            bot.send_message(m.from_user.id, "❌ Invalid package number!")
    except:
        bot.send_message(m.from_user.id, "❌ Use: /editpackage number points price bonus")

@bot.message_handler(commands=["togglepackage"])
def toggle_package(m):
    if not is_admin(m.from_user.id):
        return
    
    try:
        _, num = m.text.split()
        num = int(num) - 1
        
        packages = get_points_packages()
        if 0 <= num < len(packages):
            packages[num]["active"] = not packages[num].get("active", True)
            save_points_packages(packages)
            status = "activated" if packages[num]["active"] else "deactivated"
            bot.send_message(m.from_user.id, f"✅ Package {num+1} {status}!")
        else:
            bot.send_message(m.from_user.id, "❌ Invalid package number!")
    except:
        bot.send_message(m.from_user.id, "❌ Use: /togglepackage number")

@bot.message_handler(commands=["delpackage"])
def del_package(m):
    if not is_admin(m.from_user.id):
        return
    
    try:
        _, num = m.text.split()
        num = int(num) - 1
        
        packages = get_points_packages()
        if 0 <= num < len(packages):
            removed = packages.pop(num)
            save_points_packages(packages)
            bot.send_message(m.from_user.id, f"✅ Package removed: {removed['points']} pts")
        else:
            bot.send_message(m.from_user.id, "❌ Invalid package number!")
    except:
        bot.send_message(m.from_user.id, "❌ Use: /delpackage number")

# =========================
# 💰 SET POINT PRICE
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 Set Point Price" and is_admin(m.from_user.id))
def set_point_price(m):
    msg = bot.send_message(m.from_user.id, 
        "💰 **Set Point Price**\n\n"
        "Send: points_per_dollar\n\n"
        f"Current: {get_cached_config().get('points_per_dollar', 100)} points = $1",
        parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_point_price)

def save_point_price(m):
    try:
        ppd = int(m.text)
        set_config("points_per_dollar", ppd)
        bot.send_message(m.from_user.id, f"✅ Set: {ppd} points = $1", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid number!")

# =========================
# 📢 BROADCAST
# =========================
@bot.message_handler(func=lambda m: m.text == "📢 Broadcast" and is_admin(m.from_user.id))
def broadcast_start(m):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📢 All Users", callback_data="bc|all"),
        InlineKeyboardButton("💎 VIP Users", callback_data="bc|vip"),
        InlineKeyboardButton("🆓 Free Users", callback_data="bc|free")
    )
    bot.send_message(m.from_user.id, "📡 **Broadcast**\n\nSelect target:", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("bc|"))
def broadcast_target(c):
    target = c.data.split("|")[1]
    msg = bot.send_message(c.from_user.id, "📝 **Send your broadcast message**\n\n(Text, photo, video, or document)", parse_mode="Markdown")
    bot.register_next_step_handler(msg, lambda x: broadcast_send(x, target))

def broadcast_send(m, target):
    users = list(users_col.find({}))
    sent = 0
    failed = 0
    
    status_msg = bot.send_message(m.from_user.id, "📤 Broadcasting...")
    
    for user_data in users:
        uid = int(user_data["_id"])
        
        if target == "vip" and not user_data.get("vip", False):
            continue
        if target == "free" and user_data.get("vip", False):
            continue
        
        try:
            if m.content_type == "text":
                bot.send_message(uid, m.text, parse_mode="HTML")
            elif m.content_type == "photo":
                caption = m.caption if m.caption else None
                bot.send_photo(uid, m.photo[-1].file_id, caption=caption, parse_mode="HTML")
            elif m.content_type == "video":
                caption = m.caption if m.caption else None
                bot.send_video(uid, m.video.file_id, caption=caption, parse_mode="HTML")
            elif m.content_type == "document":
                caption = m.caption if m.caption else None
                bot.send_document(uid, m.document.file_id, caption=caption, parse_mode="HTML")
            sent += 1
        except:
            failed += 1
        
        if sent % 20 == 0:
            time.sleep(0.5)  # Reduced for speed
    
    bot.edit_message_text(
        f"✅ **Broadcast Complete!**\n\n"
        f"📤 Sent: `{sent}`\n"
        f"❌ Failed: `{failed}`\n"
        f"🎯 Target: `{target.upper()}`",
        m.from_user.id,
        status_msg.message_id,
        parse_mode="Markdown"
    )

# =========================
# ⭐ SET VIP MSG
# =========================
@bot.message_handler(func=lambda m: m.text == "⭐ Set VIP Msg" and is_admin(m.from_user.id))
def set_vip_msg(m):
    msg = bot.send_message(m.from_user.id, "⭐ **VIP Message**\n\nSend new message:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_vip_msg)

def save_vip_msg(m):
    set_config("vip_msg", m.text)
    bot.send_message(m.from_user.id, "✅ VIP message updated!", reply_markup=admin_menu())

# =========================
# 💰 Set Purchase Msg
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 Set Purchase Msg" and is_admin(m.from_user.id))
def set_purchase_msg(m):
    msg = bot.send_message(m.from_user.id, "💰 **Purchase Message**\n\nSend new message:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_purchase_msg)

def save_purchase_msg(m):
    set_config("purchase_msg", m.text)
    bot.send_message(m.from_user.id, "✅ Purchase message updated!", reply_markup=admin_menu())

# =========================
# 🏠 Set Welcome
# =========================
@bot.message_handler(func=lambda m: m.text == "🏠 Set Welcome" and is_admin(m.from_user.id))
def set_welcome(m):
    msg = bot.send_message(m.from_user.id, "🏠 **Welcome Message**\n\nSend new message:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_welcome)

def save_welcome(m):
    set_config("welcome", m.text)
    bot.send_message(m.from_user.id, "✅ Welcome message updated!", reply_markup=admin_menu())

# =========================
# ⚙️ Set Ref Reward
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ Set Ref Reward" and is_admin(m.from_user.id))
def set_ref_reward(m):
    msg = bot.send_message(m.from_user.id, f"⚙️ **Referral Reward**\n\nCurrent: {get_cached_config().get('ref_reward', 5)} points\n\nSend new amount:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_ref_reward)

def save_ref_reward(m):
    try:
        reward = int(m.text)
        set_config("ref_reward", reward)
        bot.send_message(m.from_user.id, f"✅ Referral reward set to {reward} points!", parse_mode="Markdown", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid number!")

# =========================
# 🔔 Toggle Notify
# =========================
@bot.message_handler(func=lambda m: m.text == "🔔 Toggle Notify" and is_admin(m.from_user.id))
def toggle_notify(m):
    cfg = get_config()
    current = cfg.get("notify", True)
    set_config("notify", not current)
    state = "ON" if not current else "OFF"
    bot.send_message(m.from_user.id, f"🔔 Notifications {state}", reply_markup=admin_menu())

# =========================
# 🧠 FALLBACK
# =========================
@bot.message_handler(func=lambda m: True)
def fallback(m):
    if not validate_request(m):
        return
    
    uid = m.from_user.id
    
    if force_block(uid):
        return
    
    custom_btns = get_custom_buttons()
    for btn in custom_btns:
        if m.text == btn["text"]:
            if btn["type"] == "link":
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton("🔗 Open Link", url=btn["data"]))
                bot.send_message(uid, f"🔗 **{btn['text']}**", reply_markup=kb, parse_mode="Markdown")
            elif btn["type"] == "folder":
                folder = fs.get_by_number(int(btn["data"]))
                if folder:
                    cat = folder["cat"]
                    name = folder["name"]
                    fake_callback = type('obj', (object,), {
                        'from_user': m.from_user,
                        'id': m.message_id,
                        'data': f"open|{cat}|{name}|"
                    })
                    open_folder(fake_callback)
            return
    
    known = [
        "📂 FREE METHODS", "💎 VIP METHODS",
        "📦 PREMIUM APPS", "⚡ SERVICES",
        "💰 POINTS", "⭐ BUY VIP", "🎁 REFERRAL",
        "👤 ACCOUNT", "🆔 CHAT ID", "🏆 REDEEM",
        "📚 MY METHODS", "💎 GET POINTS",
        "⚙️ ADMIN PANEL"
    ]
    
    if m.text and m.text not in known:
        bot.send_message(uid, "❌ Please use menu buttons", reply_markup=main_menu(uid))

# =========================
# 🚀 RUN BOT
# =========================
def run_bot():
    while True:
        try:
            print("=" * 50)
            print("🚀 ZEDOX BOT - COMPLETE VERSION")
            print(f"✅ Bot: @{bot.get_me().username}")
            print(f"👑 Owner ID: {ADMIN_ID}")
            print(f"👥 Multiple Admins: ENABLED")
            print(f"💾 Database: MongoDB (Optimized)")
            print(f"💰 Points System: ACTIVE")
            print(f"🗑 Delete Folder: FIXED & WORKING")
            print(f"📝 Edit Content: ADDED")
            print(f"⭐ VIP Settings: PRICE & REFERRAL REWARDS")
            print(f"💳 Payment Methods: CONFIGURABLE")
            print(f"🏦 Binance Payment: CONFIGURABLE")
            print(f"📸 Screenshot Required: ENABLED")
            print(f"🔗 Custom Links: FIXED")
            print(f"🚫 Force Join: ADMIN BYPASS")
            print("=" * 50)
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    
    while True:
        time.sleep(1)
