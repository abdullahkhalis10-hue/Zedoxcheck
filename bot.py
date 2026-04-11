# =========================
# ZEDOX BOT - COMPLETE FIXED VERSION
# All Features Working: Delete Folder, Give Points, Generate Codes
# =========================

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
import os
import time
import random
import string
import logging
from pymongo import MongoClient
from functools import wraps
from datetime import datetime

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
# 🌐 MONGODB SETUP
# =========================
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable not set!")

client = MongoClient(MONGO_URI, maxPoolSize=50, serverSelectionTimeoutMS=5000)
db = client["zedox_bot"]

# Collections
users_col = db["users"]
folders_col = db["folders"]
codes_col = db["codes"]
config_col = db["config"]
admins_col = db["admins"]

# Create indexes
users_col.create_index("user_id")
users_col.create_index("is_vip")
folders_col.create_index([("category", 1), ("parent", 1)])
folders_col.create_index("number", unique=True, sparse=True)

logger.info("✅ Database connected!")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# =========================
# 🔐 HELPER FUNCTIONS
# =========================
def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True
    return admins_col.find_one({"_id": user_id}) is not None

def get_config():
    config = config_col.find_one({"_id": "main_config"})
    if not config:
        config = {
            "_id": "main_config",
            "force_channels": [],
            "custom_buttons": [],
            "vip_message": "💎 <b>VIP METHODS</b> 💎\n\nContact admin to get VIP access!",
            "welcome_message": "🔥 <b>Welcome to ZEDOX BOT!</b> 🔥\n\nUse the buttons below!",
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
    config_col.update_one({"_id": "main_config"}, {"$set": {key: value}}, upsert=True)

def get_next_number():
    config = get_config()
    num = config.get("next_folder_number", 1)
    update_config("next_folder_number", num + 1)
    return num

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
                "referrals": 0,
                "purchased": [],
                "used_codes": [],
                "username": None,
                "joined": time.time(),
                "total_earned": 0,
                "total_spent": 0
            }
            users_col.insert_one(self.data)
    
    def save(self):
        users_col.update_one({"_id": self.user_id}, {"$set": self.data})
    
    def add_points(self, amount):
        self.data["points"] += amount
        self.data["total_earned"] += amount
        self.save()
        return True
    
    def remove_points(self, amount):
        if self.data["points"] >= amount:
            self.data["points"] -= amount
            self.data["total_spent"] += amount
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
            referrer.data["referrals"] += 1
            referrer.save()
            return True
        return False
    
    def purchase(self, item, price):
        if self.remove_points(price):
            if item not in self.data["purchased"]:
                self.data["purchased"].append(item)
                self.save()
            return True
        return False
    
    def has_purchased(self, item):
        return item in self.data.get("purchased", [])
    
    def add_code(self, code):
        if code not in self.data["used_codes"]:
            self.data["used_codes"].append(code)
            self.save()
            return True
        return False
    
    def update_username(self, username, first_name):
        self.data["username"] = username
        self.save()

# =========================
# 📁 FOLDER SYSTEM
# =========================
class FolderSystem:
    def add(self, cat, name, files, price, parent=None, text=None):
        num = get_next_number()
        data = {
            "category": cat, "name": name, "files": files, "price": price,
            "parent": parent, "number": num, "created": time.time()
        }
        if text:
            data["text_content"] = text
        folders_col.insert_one(data)
        return num
    
    def get(self, cat, parent=None):
        query = {"category": cat}
        query["parent"] = parent if parent else None
        return list(folders_col.find(query).sort("number", 1))
    
    def get_one(self, cat, name, parent=None):
        query = {"category": cat, "name": name}
        if parent:
            query["parent"] = parent
        return folders_col.find_one(query)
    
    def get_by_num(self, num):
        return folders_col.find_one({"number": num})
    
    def delete_recursive(self, cat, parent_name):
        """Delete all subfolders recursively"""
        subfolders = folders_col.find({"category": cat, "parent": parent_name})
        for sub in subfolders:
            self.delete_recursive(cat, sub["name"])
            folders_col.delete_one({"_id": sub["_id"]})
    
    def delete(self, cat, name, parent=None):
        query = {"category": cat, "name": name}
        if parent:
            query["parent"] = parent
        else:
            query["parent"] = None
        
        folder = folders_col.find_one(query)
        if not folder:
            return False
        
        # Delete all subfolders recursively
        self.delete_recursive(cat, name)
        
        # Delete the folder
        folders_col.delete_one(query)
        
        # Update numbers
        num = folder.get("number")
        if num:
            folders_col.update_many({"number": {"$gt": num}}, {"$inc": {"number": -1}})
            config = get_config()
            if config.get("next_folder_number", 1) > num:
                update_config("next_folder_number", config.get("next_folder_number", 1) - 1)
        return True
    
    def update_price(self, cat, name, price, parent=None):
        query = {"category": cat, "name": name}
        if parent:
            query["parent"] = parent
        folders_col.update_one(query, {"$set": {"price": price}})
    
    def update_name(self, cat, old, new, parent=None):
        query = {"category": cat, "name": old}
        if parent:
            query["parent"] = parent
        folders_col.update_one(query, {"$set": {"name": new}})
        folders_col.update_many({"category": cat, "parent": old}, {"$set": {"parent": new}})
    
    def move(self, num, new_parent):
        folders_col.update_one({"number": num}, {"$set": {"parent": new_parent}})
    
    def update_content(self, cat, name, content_type, content, parent=None):
        query = {"category": cat, "name": name}
        if parent:
            query["parent"] = parent
        
        if content_type == "text":
            folders_col.update_one(query, {"$set": {"text_content": content}})
        elif content_type == "files":
            folders_col.update_one(query, {"$set": {"files": content}})
        return True

fs = FolderSystem()

# =========================
# 🎫 CODES SYSTEM (FIXED)
# =========================
class CodeSystem:
    def generate(self, points, count, multi=False, days=None):
        codes = []
        expiry = time.time() + (days * 86400) if days else None
        
        for _ in range(count):
            code = "ZED" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=9))
            while codes_col.find_one({"_id": code}):
                code = "ZED" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=9))
            
            codes_col.insert_one({
                "_id": code,
                "points": points,
                "used": False,
                "multi": multi,
                "used_count": 0,
                "max_uses": 10 if multi else 1,
                "expiry": expiry,
                "created": time.time(),
                "used_by": []
            })
            codes.append(code)
        return codes
    
    def redeem(self, code, user):
        data = codes_col.find_one({"_id": code})
        if not data:
            return False, "❌ Invalid code!"
        
        if data.get("expiry") and time.time() > data["expiry"]:
            return False, "❌ Code expired!"
        
        if not data.get("multi", False) and data.get("used", False):
            return False, "❌ Code already used!"
        
        if user.user_id in data.get("used_by", []):
            return False, "❌ You already used this code!"
        
        if data.get("multi", False):
            if data.get("used_count", 0) >= data.get("max_uses", 10):
                return False, "❌ Code max uses reached!"
        
        points = data["points"]
        user.add_points(points)
        
        update = {"$push": {"used_by": user.user_id}, "$inc": {"used_count": 1}}
        if not data.get("multi", False):
            update["$set"] = {"used": True}
        
        codes_col.update_one({"_id": code}, update)
        user.add_code(code)
        return True, f"✅ +{points} points!"
    
    def stats(self):
        total = codes_col.count_documents({})
        used = codes_col.count_documents({"used": True})
        return total, used, total - used, codes_col.count_documents({"multi": True})
    
    def get_all(self):
        return list(codes_col.find({}).sort("created", -1).limit(50))

code_sys = CodeSystem()

# =========================
# 📊 POINTS PACKAGES
# =========================
def get_packages():
    pkg = config_col.find_one({"_id": "points_packages"})
    if not pkg:
        default = {
            "_id": "points_packages",
            "packages": [
                {"points": 100, "price": 5, "bonus": 0, "active": True},
                {"points": 250, "price": 10, "bonus": 25, "active": True},
                {"points": 550, "price": 20, "bonus": 100, "active": True},
                {"points": 1500, "price": 50, "bonus": 500, "active": True},
                {"points": 3500, "price": 100, "bonus": 1500, "active": True},
                {"points": 10000, "price": 250, "bonus": 5000, "active": True}
            ]
        }
        config_col.insert_one(default)
        return default["packages"]
    return pkg["packages"]

def save_packages(packages):
    config_col.update_one({"_id": "points_packages"}, {"$set": {"packages": packages}}, upsert=True)

# =========================
# 🚫 FORCE JOIN
# =========================
def check_force(user_id):
    channels = get_config().get("force_channels", [])
    if not channels:
        return True
    for ch in channels:
        try:
            member = bot.get_chat_member(ch, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

def force_join(func):
    @wraps(func)
    def wrapper(m):
        if not check_force(m.from_user.id):
            kb = InlineKeyboardMarkup()
            for ch in get_config().get("force_channels", []):
                kb.add(InlineKeyboardButton(f"📢 Join {ch}", url=f"https://t.me/{ch.replace('@', '')}"))
            kb.add(InlineKeyboardButton("✅ I Joined", callback_data="check_join"))
            bot.send_message(m.from_user.id, "🚫 <b>Join channels first!</b>", reply_markup=kb, parse_mode="HTML")
            return
        return func(m)
    return wrapper

# =========================
# 🎨 KEYBOARDS
# =========================
def main_kb(user_id):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📂 FREE METHODS", "💎 VIP METHODS")
    kb.add("📱 PREMIUM APPS", "⚡ SERVICES")
    kb.add("💰 MY BALANCE", "⭐ VIP ACCESS")
    kb.add("🎁 REFERRAL", "👤 MY PROFILE")
    kb.add("🎫 REDEEM CODE", "💎 BUY POINTS")
    if is_admin(user_id):
        kb.add("⚙️ ADMIN PANEL")
    for btn in get_config().get("custom_buttons", []):
        kb.add(btn["text"])
    return kb

def admin_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row("📤 UPLOAD FREE", "📤 UPLOAD VIP")
    kb.row("📤 UPLOAD APPS", "📤 UPLOAD SERVICE")
    kb.row("📁 CREATE SUBFOLDER", "🗑️ DELETE FOLDER")
    kb.row("✏️ EDIT PRICE", "✏️ EDIT NAME")
    kb.row("🔀 MOVE FOLDER", "📝 EDIT CONTENT")
    kb.row("👑 ADD VIP", "👑 REMOVE VIP")
    kb.row("💰 GIVE POINTS", "🎫 GENERATE CODES")
    kb.row("📊 VIEW CODES", "📦 POINTS PKGS")
    kb.row("👥 MANAGE ADMINS", "📞 SET CONTACTS")
    kb.row("➕ ADD BUTTON", "➖ REMOVE BUTTON")
    kb.row("➕ ADD CHANNEL", "➖ REMOVE CHANNEL")
    kb.row("⚙️ SETTINGS", "📊 STATS")
    kb.row("📢 BROADCAST", "🔔 TOGGLE NOTIFY")
    kb.row("◀️ EXIT ADMIN")
    return kb

# =========================
# 🤖 BOT COMMANDS
# =========================
@bot.message_handler(commands=['start'])
@force_join
def start_cmd(m):
    user = User(m.from_user.id)
    user.update_username(m.from_user.username, m.from_user.first_name)
    
    # Referral
    args = m.text.split()
    if len(args) > 1 and args[1].isdigit() and int(args[1]) != m.from_user.id:
        user.add_referral(int(args[1]))
        try:
            bot.send_message(int(args[1]), f"🎉 New referral! +{get_config().get('referral_reward', 5)} points!")
        except:
            pass
    
    bot.send_message(m.from_user.id, 
        f"{get_config().get('welcome_message')}\n\n"
        f"💰 Points: {user.get_points()}\n"
        f"⭐ VIP: {'✅' if user.is_vip() else '❌'}",
        reply_markup=main_kb(m.from_user.id))

@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def check_join_cb(c):
    if check_force(c.from_user.id):
        bot.edit_message_text("✅ Access granted!", c.from_user.id, c.message.message_id)
        user = User(c.from_user.id)
        bot.send_message(c.from_user.id, f"Welcome! Points: {user.get_points()}", reply_markup=main_kb(c.from_user.id))
    else:
        bot.answer_callback_query(c.id, "❌ Join all channels first!", True)

# =========================
# 📂 CATEGORY HANDLERS
# =========================
def show_folders(uid, cat, title):
    folders = fs.get(cat)
    if not folders:
        bot.send_message(uid, f"📁 {title}\n\nNo content yet!")
        return
    
    kb = InlineKeyboardMarkup(row_width=1)
    for f in folders:
        has_sub = len(fs.get(cat, f["name"])) > 0
        icon = "📁" if has_sub else "📄"
        text = f"{icon} [{f.get('number', '?')}] {f['name']}"
        if f.get("price", 0) > 0:
            text += f" - {f['price']} pts"
        kb.add(InlineKeyboardButton(text, callback_data=f"open_{cat}_{f['name']}"))
    bot.send_message(uid, f"📁 {title}", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["📂 FREE METHODS", "💎 VIP METHODS", "📱 PREMIUM APPS", "⚡ SERVICES"])
@force_join
def cat_handler(m):
    titles = {"📂 FREE METHODS": "FREE METHODS", "💎 VIP METHODS": "VIP METHODS", "📱 PREMIUM APPS": "PREMIUM APPS", "⚡ SERVICES": "SERVICES"}
    cats = {"📂 FREE METHODS": "free", "💎 VIP METHODS": "vip", "📱 PREMIUM APPS": "apps", "⚡ SERVICES": "services"}
    show_folders(m.from_user.id, cats[m.text], titles[m.text])

# =========================
# 📂 OPEN FOLDER
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("open_"))
def open_cb(c):
    uid = c.from_user.id
    user = User(uid)
    _, cat, name = c.data.split("_", 2)
    
    folder = fs.get_one(cat, name)
    if not folder:
        bot.answer_callback_query(c.id, "❌ Not found!")
        return
    
    # Check subfolders
    subs = fs.get(cat, name)
    if subs:
        kb = InlineKeyboardMarkup(row_width=1)
        for s in subs:
            has_sub = len(fs.get(cat, s["name"])) > 0
            icon = "📁" if has_sub else "📄"
            text = f"{icon} [{s.get('number', '?')}] {s['name']}"
            if s.get("price", 0) > 0:
                text += f" - {s['price']} pts"
            kb.add(InlineKeyboardButton(text, callback_data=f"open_{cat}_{s['name']}"))
        kb.add(InlineKeyboardButton("🔙 BACK", callback_data=f"back_{cat}"))
        bot.edit_message_text(f"📁 {name}", uid, c.message.message_id, reply_markup=kb)
        bot.answer_callback_query(c.id)
        return
    
    price = folder.get("price", 0)
    can = user.is_vip() or user.has_purchased(name)
    
    # Check access
    if not can and price > 0:
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(InlineKeyboardButton(f"💰 Buy {price} pts", callback_data=f"buy_{cat}_{name}_{price}"))
        kb.add(InlineKeyboardButton("⭐ Get VIP", callback_data="vip_info"))
        kb.add(InlineKeyboardButton("💎 Buy Points", callback_data="buy_points"))
        bot.edit_message_text(f"🔒 {name}\nPrice: {price} pts\nYour points: {user.get_points()}", uid, c.message.message_id, reply_markup=kb)
        bot.answer_callback_query(c.id, "🔒 Premium content!")
        return
    
    if not can and price == 0:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("⭐ Get VIP", callback_data="vip_info"))
        bot.edit_message_text(f"🔒 {name}\nVIP only!", uid, c.message.message_id, reply_markup=kb)
        bot.answer_callback_query(c.id, "🔒 VIP only!")
        return
    
    # Deduct points if needed
    if not user.is_vip() and price > 0:
        if user.get_points() >= price:
            user.remove_points(price)
            user.purchase(name, price)
            bot.answer_callback_query(c.id, f"✅ -{price} pts")
        else:
            bot.answer_callback_query(c.id, f"❌ Need {price} pts! You have {user.get_points()}", True)
            return
    
    # Send content
    text = folder.get("text_content")
    if text:
        bot.edit_message_text(f"📄 {name}\n\n{text}", uid, c.message.message_id)
    else:
        files = folder.get("files", [])
        bot.answer_callback_query(c.id, "📤 Sending...")
        for f in files:
            try:
                bot.copy_message(uid, f["chat"], f["msg"])
                time.sleep(0.2)
            except:
                continue
        if get_config().get("send_notifications", True):
            bot.send_message(uid, f"✅ {len(files)} files sent!")

@bot.callback_query_handler(func=lambda c: c.data.startswith("back_"))
def back_cb(c):
    cat = c.data.split("_")[1]
    titles = {"free": "FREE METHODS", "vip": "VIP METHODS", "apps": "PREMIUM APPS", "services": "SERVICES"}
    show_folders(c.from_user.id, cat, titles.get(cat, cat.upper()))
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def buy_cb(c):
    uid = c.from_user.id
    user = User(uid)
    _, cat, name, price = c.data.split("_")
    price = int(price)
    
    if user.is_vip() or user.has_purchased(name):
        bot.answer_callback_query(c.id, "✅ Already have access!")
        return
    
    if user.get_points() >= price:
        user.remove_points(price)
        user.purchase(name, price)
        bot.answer_callback_query(c.id, f"✅ Purchased! -{price} pts", True)
        bot.edit_message_text(f"✅ Purchased {name}!\nRemaining: {user.get_points()} pts", uid, c.message.message_id)
    else:
        bot.answer_callback_query(c.id, f"❌ Need {price} pts! You have {user.get_points()}", True)

@bot.callback_query_handler(func=lambda c: c.data == "vip_info")
def vip_info_cb(c):
    vip_cmd(c.message)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "buy_points")
def buy_points_cb(c):
    buy_points_cmd(c.message)
    bot.answer_callback_query(c.id)

# =========================
# 💎 USER FEATURES
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 MY BALANCE")
@force_join
def balance_cmd(m):
    u = User(m.from_user.id)
    bot.send_message(m.from_user.id,
        f"💰 <b>MY BALANCE</b>\n\n"
        f"┌ Points: {u.get_points()}\n"
        f"├ VIP: {'✅' if u.is_vip() else '❌'}\n"
        f"├ Purchased: {len(u.data.get('purchased', []))}\n"
        f"├ Referrals: {u.data.get('referrals', 0)}\n"
        f"├ Earned: {u.data.get('total_earned', 0)}\n"
        f"└ Spent: {u.data.get('total_spent', 0)}",
        parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "⭐ VIP ACCESS")
@force_join
def vip_cmd(m):
    u = User(m.from_user.id)
    if u.is_vip():
        bot.send_message(m.from_user.id, "✅ <b>You are VIP!</b>\n\nAccess all VIP METHODS!", parse_mode="HTML")
        return
    
    cfg = get_config()
    contact = cfg.get("vip_contact", "Contact admin")
    text = f"⭐ <b>VIP ACCESS</b>\n\n✨ Benefits:\n• All VIP METHODS\n• No points needed\n• Priority support\n\n💰 Points: {u.get_points()}\n\n📞 Contact: {contact}\n🆔 ID: <code>{m.from_user.id}</code>"
    kb = InlineKeyboardMarkup()
    if cfg.get("vip_contact") and cfg.get("vip_contact").startswith("http"):
        kb.add(InlineKeyboardButton("📞 Contact", url=cfg.get("vip_contact")))
    bot.send_message(m.from_user.id, text, reply_markup=kb if kb.keyboard else None, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "💎 BUY POINTS")
@force_join
def buy_points_cmd(m):
    u = User(m.from_user.id)
    pkgs = [p for p in get_packages() if p.get("active", True)]
    cfg = get_config()
    contact = cfg.get("contact_username") or cfg.get("contact_link") or "Contact admin"
    
    text = f"💎 <b>BUY POINTS</b>\n\n💰 Balance: {u.get_points()} pts\n\n"
    for i, p in enumerate(pkgs, 1):
        total = p["points"] + p.get("bonus", 0)
        text += f"{i}. {p['points']} pts"
        if p.get("bonus", 0) > 0:
            text += f" +{p['bonus']} BONUS"
        text += f"\n   💰 ${p['price']} → {total} pts\n\n"
    
    text += f"📞 Contact: {contact}\n🆔 ID: <code>{m.from_user.id}</code>"
    
    kb = InlineKeyboardMarkup()
    if cfg.get("contact_link"):
        kb.add(InlineKeyboardButton("📞 Contact", url=cfg.get("contact_link")))
    elif cfg.get("contact_username"):
        kb.add(InlineKeyboardButton("📞 Contact", url=f"https://t.me/{cfg.get('contact_username').replace('@', '')}"))
    
    bot.send_message(m.from_user.id, text, reply_markup=kb if kb.keyboard else None, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🎁 REFERRAL")
@force_join
def referral_cmd(m):
    u = User(m.from_user.id)
    link = f"https://t.me/{bot.get_me().username}?start={m.from_user.id}"
    reward = get_config().get("referral_reward", 5)
    bot.send_message(m.from_user.id,
        f"🎁 <b>REFERRAL</b>\n\n🔗 <code>{link}</code>\n\n"
        f"👥 Referrals: {u.data.get('referrals', 0)}\n"
        f"💰 Per referral: +{reward} pts\n"
        f"💎 Total earned: {u.data.get('referrals', 0) * reward}",
        parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "👤 MY PROFILE")
@force_join
def profile_cmd(m):
    u = User(m.from_user.id)
    items = u.data.get("purchased", [])
    items_text = "\n".join([f"• {i}" for i in items[:10]])
    if len(items) > 10:
        items_text += f"\n• ... {len(items)-10} more"
    
    bot.send_message(m.from_user.id,
        f"👤 <b>MY PROFILE</b>\n\n"
        f"┌ ID: <code>{m.from_user.id}</code>\n"
        f"├ Name: {m.from_user.first_name}\n"
        f"├ VIP: {'✅' if u.is_vip() else '❌'}\n"
        f"├ Points: {u.get_points()}\n"
        f"├ Referrals: {u.data.get('referrals', 0)}\n"
        f"└ Items: {len(items)}\n\n"
        f"📚 <b>My Items:</b>\n{items_text if items else 'None'}",
        parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🎫 REDEEM CODE")
@force_join
def redeem_cmd(m):
    msg = bot.send_message(m.from_user.id, "🎫 Enter your code:", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_redeem)

def process_redeem(m):
    u = User(m.from_user.id)
    success, result = code_sys.redeem(m.text.strip().upper(), u)
    bot.send_message(m.from_user.id, result + (f"\n💰 Balance: {u.get_points()}" if success else ""), parse_mode="HTML")

# =========================
# ⚙️ ADMIN PANEL
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def admin_cmd(m):
    bot.send_message(m.from_user.id, "⚙️ <b>ADMIN PANEL</b>", reply_markup=admin_kb(), parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "◀️ EXIT ADMIN" and is_admin(m.from_user.id))
def exit_admin_cmd(m):
    bot.send_message(m.from_user.id, "Exited admin panel", reply_markup=main_kb(m.from_user.id))

# =========================
# 📤 UPLOAD SYSTEM
# =========================
upload_sessions = {}

def start_upload(uid, cat, is_service=False):
    upload_sessions[uid] = {"cat": cat, "service": is_service, "files": [], "step": "name"}
    msg = bot.send_message(uid, "📤 Send folder name:\n/cancel to cancel", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_upload_name)

def process_upload_name(m):
    uid = m.from_user.id
    if m.text == "/cancel":
        upload_sessions.pop(uid, None)
        bot.send_message(uid, "❌ Cancelled!", reply_markup=admin_kb())
        return
    
    if uid not in upload_sessions:
        return
    
    upload_sessions[uid]["name"] = m.text
    msg = bot.send_message(uid, "💰 Price (points, 0 = free):", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_upload_price)

def process_upload_price(m):
    uid = m.from_user.id
    if m.text == "/cancel":
        upload_sessions.pop(uid, None)
        bot.send_message(uid, "❌ Cancelled!", reply_markup=admin_kb())
        return
    
    try:
        upload_sessions[uid]["price"] = int(m.text)
        kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        kb.add("📝 Text", "📁 Files")
        kb.add("/cancel")
        msg = bot.send_message(uid, "Choose content type:", reply_markup=kb, parse_mode="HTML")
        bot.register_next_step_handler(msg, process_upload_type)
    except:
        bot.send_message(uid, "❌ Invalid price!")
        msg = bot.send_message(uid, "💰 Price:", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_upload_price)

def process_upload_type(m):
    uid = m.from_user.id
    if m.text == "/cancel":
        upload_sessions.pop(uid, None)
        bot.send_message(uid, "❌ Cancelled!", reply_markup=admin_kb())
        return
    
    if m.text == "📝 Text":
        msg = bot.send_message(uid, "📝 Send text content:", parse_mode="HTML")
        bot.register_next_step_handler(msg, save_text)
    elif m.text == "📁 Files":
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("/done", "/cancel")
        msg = bot.send_message(uid, "📁 Send files, /done when finished:", reply_markup=kb, parse_mode="HTML")
        bot.register_next_step_handler(msg, process_files)
    else:
        process_upload_price(m)

def save_text(m):
    uid = m.from_user.id
    if m.text == "/cancel":
        upload_sessions.pop(uid, None)
        bot.send_message(uid, "❌ Cancelled!", reply_markup=admin_kb())
        return
    
    s = upload_sessions[uid]
    num = fs.add(s["cat"], s["name"], [], s["price"], text=m.text)
    
    if s.get("service"):
        f = fs.get_one(s["cat"], s["name"])
        if f:
            folders_col.update_one({"_id": f["_id"]}, {"$set": {"service_msg": m.text}})
    
    bot.send_message(uid, f"✅ Uploaded!\n📌 #{num}\n📂 {s['name']}\n💰 {s['price']} pts", reply_markup=admin_kb(), parse_mode="HTML")
    upload_sessions.pop(uid, None)

def process_files(m):
    uid = m.from_user.id
    if m.text == "/cancel":
        upload_sessions.pop(uid, None)
        bot.send_message(uid, "❌ Cancelled!", reply_markup=admin_kb())
        return
    
    if m.text == "/done":
        s = upload_sessions[uid]
        if not s["files"]:
            bot.send_message(uid, "❌ No files!")
            return
        
        num = fs.add(s["cat"], s["name"], s["files"], s["price"])
        bot.send_message(uid, f"✅ Uploaded!\n📌 #{num}\n📂 {s['name']}\n💰 {s['price']} pts\n📁 {len(s['files'])} files", reply_markup=admin_kb(), parse_mode="HTML")
        upload_sessions.pop(uid, None)
        return
    
    if m.content_type in ["document", "photo", "video"]:
        upload_sessions[uid]["files"].append({"chat": m.chat.id, "msg": m.message_id, "type": m.content_type})
        bot.send_message(uid, f"✅ Saved ({len(upload_sessions[uid]['files'])} files)")
    else:
        bot.send_message(uid, "❌ Send documents, photos, or videos!")
    
    bot.register_next_step_handler(m, process_files)

@bot.message_handler(func=lambda m: m.text in ["📤 UPLOAD FREE", "📤 UPLOAD VIP", "📤 UPLOAD APPS", "📤 UPLOAD SERVICE"] and is_admin(m.from_user.id))
def upload_handler(m):
    cats = {"📤 UPLOAD FREE": "free", "📤 UPLOAD VIP": "vip", "📤 UPLOAD APPS": "apps", "📤 UPLOAD SERVICE": "services"}
    start_upload(m.from_user.id, cats[m.text], m.text == "📤 UPLOAD SERVICE")

# =========================
# 🗑️ DELETE FOLDER (FIXED - WORKING)
# =========================
@bot.message_handler(func=lambda m: m.text == "🗑️ DELETE FOLDER" and is_admin(m.from_user.id))
def delete_cmd(m):
    msg = bot.send_message(m.from_user.id, "🗑️ <b>DELETE FOLDER</b>\n\nSend: <code>category folder_name</code>\n\nCategories: free, vip, apps, services\nExample: <code>services Amazon Prime</code>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_delete)

def process_delete(m):
    uid = m.from_user.id
    parts = m.text.split(maxsplit=1)
    if len(parts) != 2:
        bot.send_message(uid, "❌ Use: category folder_name")
        return
    
    cat, name = parts[0].lower(), parts[1].strip()
    if cat not in ["free", "vip", "apps", "services"]:
        bot.send_message(uid, "❌ Category: free, vip, apps, services")
        return
    
    # Try to find folder (case-insensitive)
    folder = fs.get_one(cat, name)
    if not folder:
        folders = fs.get(cat)
        for f in folders:
            if f["name"].lower() == name.lower():
                folder = f
                name = f["name"]
                break
    
    if not folder:
        bot.send_message(uid, f"❌ '{name}' not found in {cat}!")
        return
    
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ YES, DELETE", callback_data=f"del_{cat}_{name}"))
    kb.add(InlineKeyboardButton("❌ NO, CANCEL", callback_data="cancel_del"))
    bot.send_message(uid, f"⚠️ <b>Confirm Deletion</b>\n\nDelete '{name}' from {cat.upper()}?\n\nThis will delete ALL subfolders inside it!", reply_markup=kb, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data.startswith("del_"))
def confirm_del(c):
    _, cat, name = c.data.split("_", 2)
    if fs.delete(cat, name):
        bot.edit_message_text(f"✅ Deleted: {cat} → {name}", c.from_user.id, c.message.message_id)
        bot.send_message(c.from_user.id, "✅ Folder deleted!", reply_markup=admin_kb())
    else:
        bot.edit_message_text(f"❌ Not found!", c.from_user.id, c.message.message_id)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "cancel_del")
def cancel_del(c):
    bot.edit_message_text("❌ Cancelled", c.from_user.id, c.message.message_id)
    bot.send_message(c.from_user.id, "Returning...", reply_markup=admin_kb())
    bot.answer_callback_query(c.id)

# =========================
# ✏️ EDIT PRICE & NAME
# =========================
@bot.message_handler(func=lambda m: m.text == "✏️ EDIT PRICE" and is_admin(m.from_user.id))
def edit_price_cmd(m):
    msg = bot.send_message(m.from_user.id, "✏️ <b>EDIT PRICE</b>\n\nSend: <code>category folder_name new_price</code>\nExample: <code>vip Method 50</code>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_edit_price)

def process_edit_price(m):
    parts = m.text.split()
    if len(parts) < 3:
        bot.send_message(m.from_user.id, "❌ Use: category folder_name price")
        return
    cat, price = parts[0].lower(), int(parts[-1])
    name = " ".join(parts[1:-1])
    fs.update_price(cat, name, price)
    bot.send_message(m.from_user.id, f"✅ Price updated: {name} → {price} pts", reply_markup=admin_kb())

@bot.message_handler(func=lambda m: m.text == "✏️ EDIT NAME" and is_admin(m.from_user.id))
def edit_name_cmd(m):
    msg = bot.send_message(m.from_user.id, "✏️ <b>EDIT NAME</b>\n\nSend: <code>category old_name new_name</code>\nExample: <code>free Old New</code>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_edit_name)

def process_edit_name(m):
    parts = m.text.split(maxsplit=2)
    if len(parts) != 3:
        bot.send_message(m.from_user.id, "❌ Use: category old_name new_name")
        return
    cat, old, new = parts[0].lower(), parts[1], parts[2]
    fs.update_name(cat, old, new)
    bot.send_message(m.from_user.id, f"✅ Renamed: {old} → {new}", reply_markup=admin_kb())

# =========================
# 📝 EDIT CONTENT
# =========================
edit_sessions = {}

@bot.message_handler(func=lambda m: m.text == "📝 EDIT CONTENT" and is_admin(m.from_user.id))
def edit_content_cmd(m):
    msg = bot.send_message(m.from_user.id, "📝 <b>EDIT CONTENT</b>\n\nSend: <code>category folder_name</code>\nExample: <code>vip My Method</code>", parse_mode="HTML")
    bot.register_next_step_handler(msg, select_for_edit)

def select_for_edit(m):
    uid = m.from_user.id
    parts = m.text.split(maxsplit=1)
    if len(parts) != 2:
        bot.send_message(uid, "❌ Use: category folder_name")
        return
    
    cat, name = parts[0].lower(), parts[1].strip()
    if cat not in ["free", "vip", "apps", "services"]:
        bot.send_message(uid, "❌ Invalid category!")
        return
    
    folder = fs.get_one(cat, name)
    if not folder:
        bot.send_message(uid, f"❌ '{name}' not found!")
        return
    
    edit_sessions[uid] = {"cat": cat, "name": name}
    
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("📝 Edit Text", callback_data="edit_text"))
    kb.add(InlineKeyboardButton("📁 Edit Files", callback_data="edit_files"))
    kb.add(InlineKeyboardButton("❌ Cancel", callback_data="edit_cancel"))
    bot.send_message(uid, f"📝 <b>Edit: {name}</b>\n\nWhat would you like to edit?", reply_markup=kb, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "edit_text")
def edit_text_cb(c):
    uid = c.from_user.id
    if uid not in edit_sessions:
        bot.answer_callback_query(c.id, "Session expired!")
        return
    
    s = edit_sessions[uid]
    folder = fs.get_one(s["cat"], s["name"])
    current = folder.get("text_content", "No current content")
    current_preview = current[:300] + "..." if len(current) > 300 else current
    
    msg = bot.send_message(uid, f"📝 <b>Current Content:</b>\n{current_preview}\n\nSend <b>NEW text content</b>:", parse_mode="HTML")
    bot.register_next_step_handler(msg, save_edit_text)
    bot.answer_callback_query(c.id)

def save_edit_text(m):
    uid = m.from_user.id
    if uid not in edit_sessions:
        bot.send_message(uid, "Session expired!", reply_markup=admin_kb())
        return
    
    s = edit_sessions[uid]
    fs.update_content(s["cat"], s["name"], "text", m.text)
    bot.send_message(uid, f"✅ Text updated for {s['name']}!", reply_markup=admin_kb())
    edit_sessions.pop(uid, None)

@bot.callback_query_handler(func=lambda c: c.data == "edit_files")
def edit_files_cb(c):
    uid = c.from_user.id
    if uid not in edit_sessions:
        bot.answer_callback_query(c.id, "Session expired!")
        return
    
    edit_sessions[uid]["new_files"] = []
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("/done", "/cancel")
    msg = bot.send_message(uid, "📁 Send <b>NEW files</b> (will replace all)\nPress /done when finished:", reply_markup=kb, parse_mode="HTML")
    bot.register_next_step_handler(msg, process_edit_files)
    bot.answer_callback_query(c.id)

def process_edit_files(m):
    uid = m.from_user.id
    if m.text == "/cancel":
        edit_sessions.pop(uid, None)
        bot.send_message(uid, "❌ Cancelled!", reply_markup=admin_kb())
        return
    
    if m.text == "/done":
        if uid not in edit_sessions:
            bot.send_message(uid, "Session expired!")
            return
        
        s = edit_sessions[uid]
        if not s.get("new_files"):
            bot.send_message(uid, "❌ No files uploaded!")
            return
        
        fs.update_content(s["cat"], s["name"], "files", s["new_files"])
        bot.send_message(uid, f"✅ Files updated! {len(s['new_files'])} file(s)", reply_markup=admin_kb())
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
    bot.send_message(c.from_user.id, "Returning...", reply_markup=admin_kb())
    bot.answer_callback_query(c.id)

# =========================
# 🔀 MOVE FOLDER
# =========================
@bot.message_handler(func=lambda m: m.text == "🔀 MOVE FOLDER" and is_admin(m.from_user.id))
def move_cmd(m):
    msg = bot.send_message(m.from_user.id, "🔀 <b>MOVE FOLDER</b>\n\nSend: <code>folder_number new_parent</code>\nUse 'root' for main level\n\nExample: <code>5 root</code> or <code>5 MainFolder</code>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_move)

def process_move(m):
    parts = m.text.split()
    if len(parts) != 2:
        bot.send_message(m.from_user.id, "❌ Use: number parent")
        return
    try:
        num = int(parts[0])
        parent = parts[1] if parts[1] != "root" else None
        fs.move(num, parent)
        bot.send_message(m.from_user.id, f"✅ Folder #{num} moved successfully!", reply_markup=admin_kb())
    except:
        bot.send_message(m.from_user.id, "❌ Invalid format!")

# =========================
# 📁 CREATE SUBFOLDER
# =========================
@bot.message_handler(func=lambda m: m.text == "📁 CREATE SUBFOLDER" and is_admin(m.from_user.id))
def create_sub_cmd(m):
    msg = bot.send_message(m.from_user.id, "📁 <b>CREATE SUBFOLDER</b>\n\nSend: <code>category parent_name sub_name price</code>\nExample: <code>free Main Sub 10</code>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_sub)

def process_sub(m):
    parts = m.text.split(maxsplit=3)
    if len(parts) != 4:
        bot.send_message(m.from_user.id, "❌ Use: category parent name price")
        return
    cat, parent, name, price = parts[0].lower(), parts[1], parts[2], int(parts[3])
    
    if cat not in ["free", "vip", "apps", "services"]:
        bot.send_message(m.from_user.id, "❌ Invalid category!")
        return
    
    if not fs.get_one(cat, parent):
        bot.send_message(m.from_user.id, f"❌ Parent folder '{parent}' not found!")
        return
    
    num = fs.add(cat, name, [], price, parent)
    bot.send_message(m.from_user.id, f"✅ Subfolder #{num}: {parent} → {name}\n💰 Price: {price} pts", reply_markup=admin_kb())

# =========================
# 👑 VIP MANAGEMENT
# =========================
@bot.message_handler(func=lambda m: m.text == "👑 ADD VIP" and is_admin(m.from_user.id))
def add_vip_cmd(m):
    msg = bot.send_message(m.from_user.id, "👑 <b>ADD VIP</b>\n\nSend user ID or @username:", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: process_vip(x, True))

@bot.message_handler(func=lambda m: m.text == "👑 REMOVE VIP" and is_admin(m.from_user.id))
def remove_vip_cmd(m):
    msg = bot.send_message(m.from_user.id, "👑 <b>REMOVE VIP</b>\n\nSend user ID or @username:", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: process_vip(x, False))

def process_vip(m, add):
    uid = m.from_user.id
    inp = m.text.strip()
    
    if inp.startswith("@"):
        try:
            target = bot.get_chat(inp).id
        except:
            bot.send_message(uid, "❌ User not found!")
            return
    else:
        try:
            target = int(inp)
        except:
            bot.send_message(uid, "❌ Invalid ID!")
            return
    
    u = User(target)
    if add:
        if u.is_vip():
            bot.send_message(uid, "⚠️ User is already VIP!")
            return
        u.make_vip()
        bot.send_message(uid, f"✅ User {target} is now VIP!")
        try:
            bot.send_message(target, "🎉 <b>CONGRATULATIONS!</b> 🎉\n\nYou are now a <b>VIP Member</b>!\n\n✨ Access all VIP METHODS!", parse_mode="HTML")
        except:
            pass
    else:
        if not u.is_vip():
            bot.send_message(uid, "⚠️ User is not VIP!")
            return
        u.remove_vip()
        bot.send_message(uid, f"✅ VIP removed from {target}!")
        try:
            bot.send_message(target, "⚠️ <b>VIP Status Removed</b>", parse_mode="HTML")
        except:
            pass

# =========================
# 💰 GIVE POINTS (FULLY WORKING)
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 GIVE POINTS" and is_admin(m.from_user.id))
def give_cmd(m):
    msg = bot.send_message(m.from_user.id, "💰 <b>GIVE POINTS</b>\n\nSend: <code>user_id points</code>\n\nExample: <code>123456789 100</code>\n\nUser must have started the bot first!", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_give)

def process_give(m):
    parts = m.text.split()
    if len(parts) != 2:
        bot.send_message(m.from_user.id, "❌ Use: user_id points")
        return
    
    try:
        target = int(parts[0])
        points = int(parts[1])
        
        if points <= 0:
            bot.send_message(m.from_user.id, "❌ Points must be greater than 0!")
            return
        
        if points > 1000000:
            bot.send_message(m.from_user.id, "⚠️ Maximum 1,000,000 points per transaction!")
            return
        
        # Check if user exists
        user_data = users_col.find_one({"_id": str(target)})
        if not user_data:
            bot.send_message(m.from_user.id, f"❌ User {target} not found!\n\nUser must send /start to the bot first.")
            return
        
        u = User(target)
        old = u.get_points()
        u.add_points(points)
        
        bot.send_message(m.from_user.id, f"✅ <b>Points Added!</b>\n\n👤 User: {target}\n💰 Old: {old}\n➕ Added: +{points}\n💰 New: {u.get_points()}", parse_mode="HTML")
        
        try:
            bot.send_message(target, f"🎉 <b>Points Received!</b> 🎉\n\n✨ You received <b>+{points} points</b>!\n\n💰 New Balance: {u.get_points()} pts", parse_mode="HTML")
        except:
            bot.send_message(m.from_user.id, "⚠️ Could not notify user (they may have blocked the bot)")
            
    except ValueError:
        bot.send_message(m.from_user.id, "❌ Invalid user ID or points!")
    except Exception as e:
        bot.send_message(m.from_user.id, f"❌ Error: {str(e)}")

# =========================
# 🎫 GENERATE CODES (FIXED)
# =========================
code_gen_session = {}

@bot.message_handler(func=lambda m: m.text == "🎫 GENERATE CODES" and is_admin(m.from_user.id))
def gen_codes_cmd(m):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("Single Use", callback_data="gen_single"))
    kb.add(InlineKeyboardButton("Multi Use", callback_data="gen_multi"))
    bot.send_message(m.from_user.id, "🎫 <b>GENERATE CODES</b>\n\nSelect code type:", reply_markup=kb, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data.startswith("gen_"))
def gen_type_cb(c):
    multi = (c.data == "gen_multi")
    code_gen_session[c.from_user.id] = {"multi": multi, "step": "points"}
    msg = bot.send_message(c.from_user.id, "💰 Enter points per code:", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_gen_points)
    bot.answer_callback_query(c.id)

def process_gen_points(m):
    uid = m.from_user.id
    try:
        points = int(m.text.strip())
        if points <= 0:
            bot.send_message(uid, "❌ Points must be greater than 0!")
            return
        if points > 100000:
            bot.send_message(uid, "⚠️ Maximum 100,000 points per code!")
            return
        
        if uid not in code_gen_session:
            bot.send_message(uid, "❌ Session expired! Start over.")
            return
        
        code_gen_session[uid]["points"] = points
        msg = bot.send_message(uid, "🔢 How many codes? (1-100):", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_gen_count)
    except ValueError:
        bot.send_message(uid, "❌ Enter a valid number!")
        msg = bot.send_message(uid, "💰 Enter points per code:", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_gen_points)

def process_gen_count(m):
    uid = m.from_user.id
    try:
        count = int(m.text.strip())
        if count <= 0:
            bot.send_message(uid, "❌ Count must be greater than 0!")
            return
        if count > 100:
            bot.send_message(uid, "⚠️ Maximum 100 codes at once!")
            return
        
        if uid not in code_gen_session:
            bot.send_message(uid, "❌ Session expired! Start over.")
            return
        
        session = code_gen_session[uid]
        
        if session["multi"]:
            msg = bot.send_message(uid, "📅 Expiry days? (0 = no expiry):", parse_mode="HTML")
            bot.register_next_step_handler(msg, lambda x: process_gen_expiry(x, session["points"], count))
        else:
            codes = code_sys.generate(session["points"], count, False)
            codes_text = "\n".join(codes)
            bot.send_message(uid, f"✅ <b>{count} Codes Generated!</b>\n\n📊 {session['points']} pts each\n🔑 Single-use\n\n<code>{codes_text}</code>", parse_mode="HTML", reply_markup=admin_kb())
            code_gen_session.pop(uid, None)
    except ValueError:
        bot.send_message(uid, "❌ Enter a valid number!")
        msg = bot.send_message(uid, "🔢 How many codes? (1-100):", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_gen_count)

def process_gen_expiry(m, points, count):
    uid = m.from_user.id
    try:
        days = int(m.text.strip()) if m.text.strip() != "0" else None
        codes = code_sys.generate(points, count, True, days)
        codes_text = "\n".join(codes)
        expiry_msg = f"Expiry: {days} days" if days else "No expiry"
        bot.send_message(uid, f"✅ <b>{count} Codes Generated!</b>\n\n📊 {points} pts each\n🔑 Multi-use\n⏰ {expiry_msg}\n\n<code>{codes_text}</code>", parse_mode="HTML", reply_markup=admin_kb())
        code_gen_session.pop(uid, None)
    except ValueError:
        bot.send_message(uid, "❌ Invalid expiry days!")

# =========================
# 📊 VIEW CODES
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 VIEW CODES" and is_admin(m.from_user.id))
def view_codes_cmd(m):
    codes = code_sys.get_all()
    if not codes:
        bot.send_message(m.from_user.id, "📊 No codes generated yet!")
        return
    
    total, used, unused, multi = code_sys.stats()
    text = f"📊 <b>CODE STATISTICS</b>\n\n"
    text += f"┌ Total: {total}\n"
    text += f"├ Used: {used}\n"
    text += f"├ Unused: {unused}\n"
    text += f"└ Multi-Use: {multi}\n\n"
    
    unused_codes = [c for c in codes if not c.get("used", False)][:5]
    if unused_codes:
        text += "<b>Recent Unused Codes:</b>\n"
        for c in unused_codes:
            text += f"• <code>{c['_id']}</code> - {c['points']} pts\n"
    
    bot.send_message(m.from_user.id, text, parse_mode="HTML")

# =========================
# 📦 POINTS PACKAGES
# =========================
@bot.message_handler(func=lambda m: m.text == "📦 POINTS PKGS" and is_admin(m.from_user.id))
def pkgs_cmd(m):
    pkgs = get_packages()
    text = "📦 <b>POINTS PACKAGES</b>\n\n"
    for i, p in enumerate(pkgs, 1):
        status = "✅" if p.get("active", True) else "❌"
        text += f"{i}. {status} {p['points']} pts - ${p['price']}"
        if p.get("bonus", 0) > 0:
            text += f" (+{p['bonus']} bonus)"
        text += "\n"
    
    text += "\n<b>Commands:</b>\n/addpackage points price bonus\n/editpackage num points price bonus\n/togglepackage num\n/delpackage num"
    bot.send_message(m.from_user.id, text, parse_mode="HTML")

@bot.message_handler(commands=['addpackage', 'editpackage', 'togglepackage', 'delpackage'])
def pkg_commands(m):
    if not is_admin(m.from_user.id):
        return
    
    cmd = m.text.split()[0][1:]
    pkgs = get_packages()
    
    try:
        if cmd == 'addpackage':
            _, pts, price, bonus = m.text.split()
            pkgs.append({"points": int(pts), "price": int(price), "bonus": int(bonus), "active": True})
            save_packages(pkgs)
            bot.send_message(m.from_user.id, f"✅ Added: {pts} pts for ${price}")
        
        elif cmd == 'editpackage':
            _, num, pts, price, bonus = m.text.split()
            num = int(num) - 1
            if 0 <= num < len(pkgs):
                pkgs[num].update({"points": int(pts), "price": int(price), "bonus": int(bonus)})
                save_packages(pkgs)
                bot.send_message(m.from_user.id, f"✅ Package {num+1} updated!")
            else:
                bot.send_message(m.from_user.id, "❌ Invalid package number!")
        
        elif cmd == 'togglepackage':
            _, num = m.text.split()
            num = int(num) - 1
            if 0 <= num < len(pkgs):
                pkgs[num]["active"] = not pkgs[num].get("active", True)
                save_packages(pkgs)
                status = "activated" if pkgs[num]["active"] else "deactivated"
                bot.send_message(m.from_user.id, f"✅ Package {num+1} {status}!")
            else:
                bot.send_message(m.from_user.id, "❌ Invalid package number!")
        
        elif cmd == 'delpackage':
            _, num = m.text.split()
            num = int(num) - 1
            if 0 <= num < len(pkgs):
                removed = pkgs.pop(num)
                save_packages(pkgs)
                bot.send_message(m.from_user.id, f"✅ Removed: {removed['points']} pts")
            else:
                bot.send_message(m.from_user.id, "❌ Invalid package number!")
    except:
        bot.send_message(m.from_user.id, f"❌ Use: /{cmd} ...")

# =========================
# 👥 MANAGE ADMINS
# =========================
@bot.message_handler(func=lambda m: m.text == "👥 MANAGE ADMINS" and is_admin(m.from_user.id))
def manage_admins_cmd(m):
    if m.from_user.id != ADMIN_ID:
        bot.send_message(m.from_user.id, "❌ Only bot owner can manage admins!")
        return
    
    admins = list(admins_col.find({}))
    text = "👥 <b>ADMIN MANAGEMENT</b>\n\n"
    for a in admins:
        owner = " 👑 OWNER" if a["_id"] == ADMIN_ID else ""
        text += f"• <code>{a['_id']}</code>{owner}\n"
    text += "\n<b>Commands:</b>\n/addadmin user_id\n/removeadmin user_id\n/listadmins"
    bot.send_message(m.from_user.id, text, parse_mode="HTML")

@bot.message_handler(commands=['addadmin', 'removeadmin', 'listadmins'])
def admin_commands(m):
    if m.from_user.id != ADMIN_ID:
        return
    
    cmd = m.text.split()[0][1:]
    
    if cmd == 'listadmins':
        admins = list(admins_col.find({}))
        text = "👥 <b>ADMIN LIST</b>\n\n"
        for a in admins:
            text += f"• <code>{a['_id']}</code>\n"
        bot.send_message(m.from_user.id, text, parse_mode="HTML")
        return
    
    try:
        _, uid = m.text.split()
        uid = int(uid)
        
        if cmd == 'addadmin':
            if admins_col.find_one({"_id": uid}):
                bot.send_message(m.from_user.id, f"❌ User {uid} is already an admin!")
                return
            admins_col.insert_one({"_id": uid, "added_at": time.time()})
            bot.send_message(m.from_user.id, f"✅ Admin {uid} added!")
            try:
                bot.send_message(uid, "🎉 You are now an admin of ZEDOX BOT!", parse_mode="HTML")
            except:
                pass
        else:
            if uid == ADMIN_ID:
                bot.send_message(m.from_user.id, "❌ Cannot remove bot owner!")
                return
            result = admins_col.delete_one({"_id": uid})
            if result.deleted_count > 0:
                bot.send_message(m.from_user.id, f"✅ Admin {uid} removed!")
                try:
                    bot.send_message(uid, "⚠️ You are no longer an admin.", parse_mode="HTML")
                except:
                    pass
            else:
                bot.send_message(m.from_user.id, f"❌ User {uid} is not an admin!")
    except:
        bot.send_message(m.from_user.id, f"❌ Use: /{cmd} user_id")

# =========================
# 📞 SET CONTACTS
# =========================
@bot.message_handler(func=lambda m: m.text == "📞 SET CONTACTS" and is_admin(m.from_user.id))
def set_contacts_cmd(m):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("💰 Points Contact", callback_data="set_points"))
    kb.add(InlineKeyboardButton("⭐ VIP Contact", callback_data="set_vip"))
    kb.add(InlineKeyboardButton("📋 View Contacts", callback_data="view_contacts"))
    bot.send_message(m.from_user.id, "📞 <b>CONTACT SETTINGS</b>", reply_markup=kb, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "set_points")
def set_points_cb(c):
    msg = bot.send_message(c.from_user.id, "💰 Send @username or link:\nSend 'none' to remove", parse_mode="HTML")
    bot.register_next_step_handler(msg, save_points_contact)
    bot.answer_callback_query(c.id)

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
        bot.send_message(m.from_user.id, "❌ Invalid format! Use @username or https://t.me/username")
        return
    bot.send_message(m.from_user.id, "✅ Updated!", reply_markup=admin_kb())

@bot.callback_query_handler(func=lambda c: c.data == "set_vip")
def set_vip_cb(c):
    msg = bot.send_message(c.from_user.id, "⭐ Send @username or link:\nSend 'none' to remove", parse_mode="HTML")
    bot.register_next_step_handler(msg, save_vip_contact)
    bot.answer_callback_query(c.id)

def save_vip_contact(m):
    if m.text.lower() == "none":
        update_config("vip_contact", None)
    elif m.text.startswith("http") or m.text.startswith("@"):
        update_config("vip_contact", m.text)
    else:
        bot.send_message(m.from_user.id, "❌ Invalid format! Use @username or https://t.me/username")
        return
    bot.send_message(m.from_user.id, "✅ Updated!", reply_markup=admin_kb())

@bot.callback_query_handler(func=lambda c: c.data == "view_contacts")
def view_contacts_cb(c):
    cfg = get_config()
    points = cfg.get("contact_username") or cfg.get("contact_link") or "Not set"
    vip = cfg.get("vip_contact") or "Not set"
    bot.edit_message_text(f"📞 <b>CURRENT CONTACTS</b>\n\n💰 Points: {points}\n⭐ VIP: {vip}", c.from_user.id, c.message.message_id, parse_mode="HTML")
    bot.answer_callback_query(c.id)

# =========================
# 🔘 CUSTOM BUTTONS
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ ADD BUTTON" and is_admin(m.from_user.id))
def add_btn_cmd(m):
    msg = bot.send_message(m.from_user.id, "🔘 <b>ADD CUSTOM BUTTON</b>\n\nSend: <code>type|text|data</code>\n\nTypes: link|folder\n\nExamples:\n<code>link|Website|https://example.com</code>\n<code>folder|My Folder|5</code>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_add_btn)

def process_add_btn(m):
    parts = m.text.split("|")
    if len(parts) != 3:
        bot.send_message(m.from_user.id, "❌ Invalid format! Use: type|text|data")
        return
    typ, text, data = parts[0].lower(), parts[1], parts[2]
    
    if typ not in ["link", "folder"]:
        bot.send_message(m.from_user.id, "❌ Type must be 'link' or 'folder'")
        return
    
    if typ == "folder":
        if not fs.get_by_num(int(data)):
            bot.send_message(m.from_user.id, f"❌ Folder #{data} not found!")
            return
    
    cfg = get_config()
    btns = cfg.get("custom_buttons", [])
    btns.append({"text": text, "type": typ, "data": data})
    update_config("custom_buttons", btns)
    bot.send_message(m.from_user.id, f"✅ Button added: {text}", reply_markup=admin_kb())

@bot.message_handler(func=lambda m: m.text == "➖ REMOVE BUTTON" and is_admin(m.from_user.id))
def remove_btn_cmd(m):
    cfg = get_config()
    btns = cfg.get("custom_buttons", [])
    if not btns:
        bot.send_message(m.from_user.id, "❌ No custom buttons to remove!")
        return
    
    kb = InlineKeyboardMarkup(row_width=1)
    for b in btns:
        kb.add(InlineKeyboardButton(f"❌ {b['text']}", callback_data=f"rmbtn_{b['text']}"))
    bot.send_message(m.from_user.id, "🔘 Select button to remove:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rmbtn_"))
def rm_btn_cb(c):
    text = c.data[6:]
    cfg = get_config()
    btns = [b for b in cfg.get("custom_buttons", []) if b["text"] != text]
    update_config("custom_buttons", btns)
    bot.edit_message_text(f"✅ Removed: {text}", c.from_user.id, c.message.message_id)
    bot.answer_callback_query(c.id)

# =========================
# 📢 FORCE JOIN CHANNELS
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ ADD CHANNEL" and is_admin(m.from_user.id))
def add_ch_cmd(m):
    msg = bot.send_message(m.from_user.id, "➕ <b>ADD FORCE JOIN CHANNEL</b>\n\nSend channel username (with @):\nExample: <code>@channelusername</code>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_add_ch)

def process_add_ch(m):
    ch = m.text.strip()
    if not ch.startswith("@"):
        bot.send_message(m.from_user.id, "❌ Channel username must start with @")
        return
    
    cfg = get_config()
    chs = cfg.get("force_channels", [])
    if ch in chs:
        bot.send_message(m.from_user.id, "❌ Channel already in list!")
        return
    
    chs.append(ch)
    update_config("force_channels", chs)
    bot.send_message(m.from_user.id, f"✅ Force join channel added: {ch}", reply_markup=admin_kb())

@bot.message_handler(func=lambda m: m.text == "➖ REMOVE CHANNEL" and is_admin(m.from_user.id))
def remove_ch_cmd(m):
    cfg = get_config()
    chs = cfg.get("force_channels", [])
    if not chs:
        bot.send_message(m.from_user.id, "❌ No channels to remove!")
        return
    
    kb = InlineKeyboardMarkup(row_width=1)
    for ch in chs:
        kb.add(InlineKeyboardButton(f"❌ {ch}", callback_data=f"rmch_{ch}"))
    bot.send_message(m.from_user.id, "➖ Select channel to remove:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rmch_"))
def rm_ch_cb(c):
    ch = c.data[5:]
    cfg = get_config()
    chs = [c for c in cfg.get("force_channels", []) if c != ch]
    update_config("force_channels", chs)
    bot.edit_message_text(f"✅ Removed: {ch}", c.from_user.id, c.message.message_id)
    bot.answer_callback_query(c.id)

# =========================
# ⚙️ SETTINGS
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ SETTINGS" and is_admin(m.from_user.id))
def settings_cmd(m):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("⭐ VIP Message", callback_data="set_vip_msg"))
    kb.add(InlineKeyboardButton("🏠 Welcome Message", callback_data="set_welcome"))
    kb.add(InlineKeyboardButton("💰 Referral Reward", callback_data="set_reward"))
    kb.add(InlineKeyboardButton("💵 Points per $", callback_data="set_ppd"))
    bot.send_message(m.from_user.id, "⚙️ <b>SETTINGS</b>", reply_markup=kb, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "set_vip_msg")
def set_vip_msg_cb(c):
    msg = bot.send_message(c.from_user.id, "⭐ Send new VIP message:", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: update_config("vip_message", x.text) or bot.send_message(x.from_user.id, "✅ VIP message updated!", reply_markup=admin_kb()))
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "set_welcome")
def set_welcome_cb(c):
    msg = bot.send_message(c.from_user.id, "🏠 Send new welcome message:", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: update_config("welcome_message", x.text) or bot.send_message(x.from_user.id, "✅ Welcome message updated!", reply_markup=admin_kb()))
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "set_reward")
def set_reward_cb(c):
    current = get_config().get("referral_reward", 5)
    msg = bot.send_message(c.from_user.id, f"💰 Current reward: {current} points\n\nSend new amount:", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: update_config("referral_reward", int(x.text)) or bot.send_message(x.from_user.id, f"✅ Referral reward set to {x.text} points!", reply_markup=admin_kb()) if x.text.isdigit() else bot.send_message(x.from_user.id, "❌ Invalid number!"))
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "set_ppd")
def set_ppd_cb(c):
    current = get_config().get("points_per_dollar", 100)
    msg = bot.send_message(c.from_user.id, f"💵 Current: {current} points = $1\n\nSend new value:", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: update_config("points_per_dollar", int(x.text)) or bot.send_message(x.from_user.id, f"✅ Set to {x.text} points = $1!", reply_markup=admin_kb()) if x.text.isdigit() else bot.send_message(x.from_user.id, "❌ Invalid number!"))
    bot.answer_callback_query(c.id)

# =========================
# 📊 STATISTICS
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 STATS" and is_admin(m.from_user.id))
def stats_cmd(m):
    total = users_col.count_documents({})
    vip = users_col.count_documents({"is_vip": True})
    free = total - vip
    
    all_u = list(users_col.find({}))
    points = sum(u.get("points", 0) for u in all_u)
    earned = sum(u.get("total_earned", 0) for u in all_u)
    spent = sum(u.get("total_spent", 0) for u in all_u)
    refs = sum(u.get("referrals", 0) for u in all_u)
    purchases = sum(len(u.get("purchased", [])) for u in all_u)
    
    free_f = folders_col.count_documents({"category": "free"})
    vip_f = folders_col.count_documents({"category": "vip"})
    apps_f = folders_col.count_documents({"category": "apps"})
    svc_f = folders_col.count_documents({"category": "services"})
    
    total_c, used_c, _, _ = code_sys.stats()
    
    text = f"📊 <b>BOT STATISTICS</b>\n\n"
    text += f"👥 <b>USERS:</b>\n"
    text += f"┌ Total: {total}\n"
    text += f"├ VIP: {vip}\n"
    text += f"└ Free: {free}\n\n"
    
    text += f"💰 <b>POINTS:</b>\n"
    text += f"┌ Current: {points:,}\n"
    text += f"├ Earned: {earned:,}\n"
    text += f"├ Spent: {spent:,}\n"
    text += f"└ Avg: {points//total if total > 0 else 0}\n\n"
    
    text += f"📚 <b>CONTENT:</b>\n"
    text += f"┌ FREE METHODS: {free_f}\n"
    text += f"├ VIP METHODS: {vip_f}\n"
    text += f"├ PREMIUM APPS: {apps_f}\n"
    text += f"└ SERVICES: {svc_f}\n\n"
    
    text += f"📈 <b>ACTIVITY:</b>\n"
    text += f"┌ Referrals: {refs}\n"
    text += f"├ Purchases: {purchases}\n"
    text += f"└ Codes: {total_c} (Used: {used_c})"
    
    bot.send_message(m.from_user.id, text, parse_mode="HTML")

# =========================
# 📢 BROADCAST
# =========================
@bot.message_handler(func=lambda m: m.text == "📢 BROADCAST" and is_admin(m.from_user.id))
def broadcast_cmd(m):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("📢 All Users", callback_data="bc_all"))
    kb.add(InlineKeyboardButton("💎 VIP Users", callback_data="bc_vip"))
    kb.add(InlineKeyboardButton("🆓 Free Users", callback_data="bc_free"))
    bot.send_message(m.from_user.id, "📢 <b>BROADCAST</b>\n\nSelect target:", reply_markup=kb, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data.startswith("bc_"))
def broadcast_target_cb(c):
    target = c.data[3:]
    msg = bot.send_message(c.from_user.id, f"📢 Send message to {target.upper()} users:\n\n(Text, photo, video, or document)", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda x: send_broadcast(x, target))
    bot.answer_callback_query(c.id)

def send_broadcast(m, target):
    query = {}
    if target == "vip":
        query = {"is_vip": True}
    elif target == "free":
        query = {"is_vip": False}
    
    users = list(users_col.find(query))
    if not users:
        bot.send_message(m.from_user.id, "❌ No users found for this target!")
        return
    
    status = bot.send_message(m.from_user.id, f"📤 Broadcasting to {len(users)} users...")
    sent, failed = 0, 0
    
    for u in users:
        try:
            uid = int(u["_id"])
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
            if sent % 20 == 0:
                time.sleep(0.5)
        except:
            failed += 1
    
    bot.edit_message_text(f"✅ <b>Broadcast Complete!</b>\n\n📤 Sent: {sent}\n❌ Failed: {failed}\n🎯 Target: {target.upper()}\n👥 Total: {len(users)}", m.from_user.id, status.message_id, parse_mode="HTML")

# =========================
# 🔔 TOGGLE NOTIFY
# =========================
@bot.message_handler(func=lambda m: m.text == "🔔 TOGGLE NOTIFY" and is_admin(m.from_user.id))
def toggle_notify_cmd(m):
    cfg = get_config()
    current = cfg.get("send_notifications", True)
    update_config("send_notifications", not current)
    state = "ON" if not current else "OFF"
    bot.send_message(m.from_user.id, f"🔔 Notifications turned {state}", reply_markup=admin_kb())

# =========================
# 🧠 FALLBACK
# =========================
@bot.message_handler(func=lambda m: True)
def fallback(m):
    if not check_force(m.from_user.id):
        return
    
    # Check custom buttons
    for btn in get_config().get("custom_buttons", []):
        if m.text == btn["text"]:
            if btn["type"] == "link":
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton("🔗 Open Link", url=btn["data"]))
                bot.send_message(m.from_user.id, f"🔗 {btn['text']}", reply_markup=kb)
            elif btn["type"] == "folder":
                f = fs.get_by_num(int(btn["data"]))
                if f:
                    fake = type('obj', (object,), {'from_user': m.from_user, 'id': m.message_id, 'data': f"open_{f['category']}_{f['name']}"})
                    open_cb(fake)
            return
    
    # Ignore known buttons
    known = ["📂 FREE METHODS", "💎 VIP METHODS", "📱 PREMIUM APPS", "⚡ SERVICES", "💰 MY BALANCE", "⭐ VIP ACCESS", "🎁 REFERRAL", "👤 MY PROFILE", "🎫 REDEEM CODE", "💎 BUY POINTS", "⚙️ ADMIN PANEL", "◀️ EXIT ADMIN"]
    if m.text not in known:
        bot.send_message(m.from_user.id, "❌ Please use the menu buttons!", reply_markup=main_kb(m.from_user.id))

# =========================
# 🏃‍♂️ RUN BOT
# =========================
def run():
    while True:
        try:
            print("=" * 50)
            print("🚀 ZEDOX BOT - COMPLETE FIXED VERSION")
            print(f"✅ Bot: @{bot.get_me().username}")
            print(f"👑 Owner ID: {ADMIN_ID}")
            print(f"💾 Database: MongoDB Connected")
            print(f"⚡ Features:")
            print(f"   • DELETE FOLDER ✓ (recursive)")
            print(f"   • GIVE POINTS ✓ (with notification)")
            print(f"   • GENERATE CODES ✓ (no errors)")
            print(f"   • EDIT CONTENT ✓ (text & files)")
            print("=" * 50)
            bot.infinity_polling(timeout=60)
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run()
