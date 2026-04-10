# =========================
# ZEDOX BOT - MONGODB OPTIMIZED VERSION
# Optimized for 512MB Free Tier - Minimal Storage Usage
# =========================

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
import os, time, random, string, threading, hashlib, hmac, json
from pymongo import MongoClient
from datetime import datetime, timedelta

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))

# =========================
# 🌐 MONGODB SETUP - OPTIMIZED
# =========================
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable not set!")

client = MongoClient(MONGO_URI)
db = client["zedox"]

# Optimized Collections - Using only what's necessary
users_col = db["users"]           # Store only user data
folders_col = db["folders"]       # Store folder structure
codes_col = db["codes"]           # Store redeem codes
config_col = db["config"]         # Store bot configuration

# Create indexes for better performance (minimal)
users_col.create_index("_id")     # Already indexed by default
users_col.create_index("vip")
users_col.create_index("points")
folders_col.create_index("cat")
codes_col.create_index("_id")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# =========================
# ⚙️ CONFIG SYSTEM - MINIMAL
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
            "purchase_msg": "💰 Contact admin to buy points!",
            "next_folder_number": 1,
            "points_packages": [
                {"points": 100, "price": 5, "bonus": 0},
                {"points": 250, "price": 10, "bonus": 25},
                {"points": 550, "price": 20, "bonus": 100},
                {"points": 1500, "price": 50, "bonus": 500},
                {"points": 3500, "price": 100, "bonus": 1500},
                {"points": 10000, "price": 250, "bonus": 5000}
            ],
            "contact_username": None,
            "contact_link": None,
            "vip_contact": None
        }
        config_col.insert_one(cfg)
    return cfg

def set_config(key, value):
    config_col.update_one({"_id": "config"}, {"$set": {key: value}}, upsert=True)

# =========================
# 👤 USER SYSTEM - MINIMAL DATA
# =========================
class User:
    def __init__(self, uid):
        self.uid = str(uid)
        data = users_col.find_one({"_id": self.uid})
        
        if not data:
            # Minimal user data structure
            data = {
                "_id": self.uid,
                "p": 0,           # points
                "v": False,       # vip
                "r": None,        # referred by
                "rc": 0,          # referral count
                "pm": [],         # purchased methods
                "uc": [],         # used codes
                "u": None,        # username
                "t": time.time()  # created timestamp
            }
            users_col.insert_one(data)
        
        self.data = data
    
    def save(self):
        users_col.update_one({"_id": self.uid}, {"$set": self.data})
    
    def is_vip(self): 
        return self.data.get("v", False)
    
    def points(self): 
        return self.data.get("p", 0)
    
    def purchased_methods(self): 
        return self.data.get("pm", [])
    
    def used_codes(self): 
        return self.data.get("uc", [])
    
    def username(self): 
        return self.data.get("u", None)
    
    def update_username(self, username):
        if username != self.data.get("u"):
            self.data["u"] = username
            self.save()
    
    def add_points(self, p):
        self.data["p"] = self.data.get("p", 0) + p
        self.save()
    
    def spend_points(self, p):
        self.data["p"] = self.data.get("p", 0) - p
        self.save()
    
    def make_vip(self):
        self.data["v"] = True
        self.save()
    
    def remove_vip(self):
        self.data["v"] = False
        self.save()
    
    def purchase_method(self, method_name, price):
        if self.points() >= price:
            self.spend_points(price)
            if method_name not in self.purchased_methods():
                pm = self.data.get("pm", [])
                pm.append(method_name)
                self.data["pm"] = pm
                self.save()
            return True
        return False
    
    def can_access_method(self, method_name):
        return self.is_vip() or method_name in self.purchased_methods()
    
    def add_used_code(self, code):
        if code not in self.used_codes():
            uc = self.data.get("uc", [])
            uc.append(code)
            self.data["uc"] = uc
            self.save()
            return True
        return False
    
    def has_used_code(self, code):
        return code in self.used_codes()
    
    def add_ref(self):
        self.data["rc"] = self.data.get("rc", 0) + 1
        self.save()

# =========================
# 📦 CONTENT SYSTEM - OPTIMIZED
# =========================
class FS:
    def add(self, cat, name, files, price, parent=None, text_content=None):
        config = get_config()
        number = config.get("next_folder_number", 1)
        set_config("next_folder_number", number + 1)
        
        folder_data = {
            "c": cat,               # category
            "n": name,              # name
            "f": files,             # files
            "pr": price,            # price
            "pa": parent,           # parent
            "nm": number,           # number
            "t": time.time()        # timestamp
        }
        
        if text_content:
            folder_data["tc"] = text_content
        
        folders_col.insert_one(folder_data)
        return number
    
    def get(self, cat, parent=None):
        query = {"c": cat}
        if parent:
            query["pa"] = parent
        else:
            query["pa"] = None
        return list(folders_col.find(query).sort("nm", 1))
    
    def get_one(self, cat, name, parent=None):
        query = {"c": cat, "n": name}
        if parent:
            query["pa"] = parent
        return folders_col.find_one(query)
    
    def get_by_number(self, number):
        return folders_col.find_one({"nm": number})
    
    def delete(self, cat, name, parent=None):
        query = {"c": cat, "n": name}
        if parent:
            query["pa"] = parent
        result = folders_col.delete_one(query)
        return result.deleted_count > 0
    
    def edit_price(self, cat, name, price, parent=None):
        query = {"c": cat, "n": name}
        if parent:
            query["pa"] = parent
        folders_col.update_one(query, {"$set": {"pr": price}})
    
    def edit_name(self, cat, old, new, parent=None):
        query = {"c": cat, "n": old}
        if parent:
            query["pa"] = parent
        folders_col.update_one(query, {"$set": {"n": new}})

fs = FS()

# =========================
# 🏆 CODES SYSTEM - OPTIMIZED
# =========================
class Codes:
    def generate(self, pts, count, multi_use=False, expiry_days=None):
        res = []
        expiry = time.time() + (expiry_days * 86400) if expiry_days else None
        
        for _ in range(count):
            code = "ZDX" + ''.join(random.choices(string.ascii_uppercase+string.digits, k=6))
            code_data = {
                "_id": code,
                "p": pts,           # points
                "u": False,         # used
                "m": multi_use,     # multi_use
                "uc": 0,            # used_count
                "ex": expiry        # expiry
            }
            if multi_use:
                code_data["ub"] = []  # used_by
            codes_col.insert_one(code_data)
            res.append(code)
        return res
    
    def redeem(self, code, user):
        code_data = codes_col.find_one({"_id": code})
        
        if not code_data:
            return False, 0, "invalid"
        
        if code_data.get("ex") and time.time() > code_data["ex"]:
            return False, 0, "expired"
        
        if not code_data.get("m", False) and code_data.get("u", False):
            return False, 0, "already_used"
        
        if code_data.get("m", False):
            used_by = code_data.get("ub", [])
            if user.uid in used_by:
                return False, 0, "already_used_by_user"
            used_by.append(user.uid)
            codes_col.update_one({"_id": code}, {"$set": {"ub": used_by}, "$inc": {"uc": 1}})
        else:
            codes_col.update_one({"_id": code}, {"$set": {"u": True}})
        
        pts = code_data["p"]
        user.add_points(pts)
        user.add_used_code(code)
        
        return True, pts, "success"
    
    def get_all_codes(self):
        return list(codes_col.find({}).limit(100))

codesys = Codes()

# =========================
# 🚫 FORCE JOIN
# =========================
def force_block(uid):
    cfg = get_config()
    
    for ch in cfg.get("force_channels", []):
        try:
            member = bot.get_chat_member(ch, uid)
            if member.status in ["left", "kicked"]:
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(f"Join {ch}", url=f"https://t.me/{ch.replace('@','')}"))
                kb.add(InlineKeyboardButton("🔄 I Joined", callback_data="recheck"))
                bot.send_message(uid, "🚫 Join all channels first!", reply_markup=kb)
                return True
        except:
            return True
    return False

def get_custom_buttons():
    cfg = get_config()
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
# 📱 MAIN MENU
# =========================
def main_menu(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    
    kb.row("📂 FREE", "💎 VIP")
    kb.row("📦 APPS", "⚡ SERVICES")
    kb.row("💰 POINTS", "⭐ VIP")
    
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
    
    kb.row("🎁 REFER", "👤 ME")
    kb.row("📚 MY", "💎 BUY")
    kb.row("🆔 ID", "🏆 CODE")
    
    if is_admin(uid):
        kb.row("⚙️ ADMIN")
    
    return kb

# =========================
# ADMIN CHECK
# =========================
def is_admin(uid):
    return uid == ADMIN_ID

# =========================
# 🚀 START
# =========================
@bot.message_handler(commands=["start"])
def start_cmd(m):
    uid = m.from_user.id
    args = m.text.split()
    
    user = User(uid)
    
    if m.from_user.username:
        user.update_username(m.from_user.username)
    
    if len(args) > 1:
        ref_id = args[1]
        if ref_id != str(uid) and ref_id.isdigit():
            ref_user = users_col.find_one({"_id": ref_id})
            if ref_user and not user.data.get("r"):
                reward = get_config().get("ref_reward", 5)
                User(ref_id).add_points(reward)
                user.data["r"] = ref_id
                user.add_ref()
                user.save()
                try:
                    bot.send_message(int(ref_id), f"🎉 New referral! +{reward} points!")
                except:
                    pass
    
    if force_block(uid):
        return
    
    cfg = get_config()
    bot.send_message(uid, f"{cfg.get('welcome', 'Welcome!')}\n💰 Points: {user.points()}", reply_markup=main_menu(uid))

# =========================
# 💰 POINTS
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 POINTS")
def points_cmd(m):
    user = User(m.from_user.id)
    bot.send_message(m.from_user.id, f"💰 **Points:** {user.points()}\n🎁 VIP: {'Yes' if user.is_vip() else 'No'}\n📚 Methods: {len(user.purchased_methods())}", parse_mode="Markdown")

# =========================
# 💎 BUY POINTS
# =========================
@bot.message_handler(func=lambda m: m.text == "💎 BUY")
def buy_points(m):
    uid = m.from_user.id
    user = User(uid)
    cfg = get_config()
    packages = cfg.get("points_packages", [])
    
    msg = f"💰 **BUY POINTS**\n\nYour balance: {user.points()}\n\n"
    for i, pkg in enumerate(packages, 1):
        total = pkg["points"] + pkg.get("bonus", 0)
        msg += f"{i}. {pkg['points']} pts = ${pkg['price']}"
        if pkg.get("bonus", 0) > 0:
            msg += f" (+{pkg['bonus']} bonus = {total} pts)"
        msg += "\n"
    
    msg += "\n📞 Contact admin to buy!"
    
    contact = cfg.get("contact_link") or cfg.get("contact_username")
    kb = InlineKeyboardMarkup()
    if contact:
        if contact.startswith("http"):
            kb.add(InlineKeyboardButton("📞 Contact Admin", url=contact))
        else:
            kb.add(InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{contact.replace('@','')}"))
    
    bot.send_message(uid, msg, reply_markup=kb, parse_mode="Markdown")

# =========================
# 📂 SHOW FOLDERS
# =========================
def get_folders_kb(cat, parent=None):
    data = fs.get(cat, parent)
    kb = InlineKeyboardMarkup(row_width=2)
    
    for item in data:
        name = item["n"]
        price = item.get("pr", 0)
        num = item.get("nm", "?")
        has_sub = len(fs.get(cat, name)) > 0
        icon = "📁" if has_sub else "📄"
        text = f"{icon}[{num}] {name}"
        if price > 0:
            text += f" [{price}]"
        kb.add(InlineKeyboardButton(text, callback_data=f"op|{cat}|{name}|{parent or ''}"))
    
    if parent:
        kb.add(InlineKeyboardButton("🔙 Back", callback_data=f"bk|{cat}|{parent}"))
    
    return kb

@bot.message_handler(func=lambda m: m.text in ["📂 FREE", "💎 VIP", "📦 APPS", "⚡ SERVICES"])
def show_category(m):
    uid = m.from_user.id
    if force_block(uid):
        return
    
    mapping = {"📂 FREE": "free", "💎 VIP": "vip", "📦 APPS": "apps", "⚡ SERVICES": "services"}
    cat = mapping.get(m.text)
    
    if not fs.get(cat):
        bot.send_message(uid, "❌ No content yet!")
        return
    
    bot.send_message(uid, f"📂 {m.text}:", reply_markup=get_folders_kb(cat))

# =========================
# 📂 OPEN FOLDER
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("op|"))
def open_folder(c):
    uid = c.from_user.id
    user = User(uid)
    _, cat, name, parent = c.data.split("|")
    parent = parent if parent else None
    
    folder = fs.get_one(cat, name, parent)
    if not folder:
        bot.answer_callback_query(c.id, "Not found")
        return
    
    # Check subfolders
    if fs.get(cat, name):
        bot.edit_message_reply_markup(uid, c.message.message_id, reply_markup=get_folders_kb(cat, name))
        bot.answer_callback_query(c.id)
        return
    
    # Handle services
    if cat == "services":
        price = folder.get("pr", 0)
        if price > 0 and not user.is_vip():
            if user.points() < price:
                bot.answer_callback_query(c.id, f"Need {price} points!", True)
                return
            user.spend_points(price)
        msg = folder.get("tc", "✅ Service activated!")
        bot.send_message(uid, msg)
        bot.answer_callback_query(c.id)
        return
    
    # Handle text content
    text_content = folder.get("tc")
    if text_content:
        price = folder.get("pr", 0)
        
        if cat == "vip" and not user.is_vip() and not user.can_access_method(name):
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("💰 Buy", callback_data=f"buy|{cat}|{name}|{price}"))
            kb.add(InlineKeyboardButton("⭐ VIP", callback_data="get_vip"))
            bot.send_message(uid, f"🔒 VIP: {name}\nPrice: {price}\nYour points: {user.points()}", reply_markup=kb)
            bot.answer_callback_query(c.id)
            return
        
        if price > 0 and not user.is_vip():
            if user.points() < price:
                bot.answer_callback_query(c.id, f"Need {price} points!", True)
                return
            user.spend_points(price)
        
        bot.send_message(uid, text_content)
        bot.answer_callback_query(c.id)
        return
    
    # Handle files
    price = folder.get("pr", 0)
    if cat == "vip" and not user.is_vip() and not user.can_access_method(name):
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("💰 Buy", callback_data=f"buy|{cat}|{name}|{price}"))
        kb.add(InlineKeyboardButton("⭐ VIP", callback_data="get_vip"))
        bot.send_message(uid, f"🔒 VIP: {name}\nPrice: {price}\nYour points: {user.points()}", reply_markup=kb)
        bot.answer_callback_query(c.id)
        return
    
    if price > 0 and not user.is_vip():
        if user.points() < price:
            bot.answer_callback_query(c.id, f"Need {price} points!", True)
            return
        user.spend_points(price)
    
    count = 0
    for f in folder.get("f", []):
        try:
            bot.copy_message(uid, f["chat"], f["msg"])
            count += 1
            time.sleep(0.3)
        except:
            continue
    
    bot.send_message(uid, f"✅ Sent {count} files!")
    bot.answer_callback_query(c.id)

# =========================
# BUY METHOD
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy|"))
def buy_method(c):
    uid = c.from_user.id
    user = User(uid)
    _, cat, name, price = c.data.split("|")
    price = int(price)
    
    if user.points() < price:
        bot.answer_callback_query(c.id, f"Need {price} points!", True)
        return
    
    if user.purchase_method(name, price):
        bot.answer_callback_query(c.id, f"✅ Purchased! -{price} points", True)
        bot.send_message(uid, f"✅ You now own: {name}\nPoints left: {user.points()}")
    else:
        bot.answer_callback_query(c.id, "Purchase failed!", True)

# =========================
# BACK BUTTON
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("bk|"))
def back_handler(c):
    _, cat, parent = c.data.split("|")
    parent_folder = fs.get_one(cat, parent)
    grand_parent = parent_folder.get("pa") if parent_folder else None
    bot.edit_message_reply_markup(c.from_user.id, c.message.message_id, reply_markup=get_folders_kb(cat, grand_parent))
    bot.answer_callback_query(c.id)

# =========================
# OTHER USER COMMANDS
# =========================
@bot.message_handler(func=lambda m: m.text == "🎁 REFER")
def referral_cmd(m):
    uid = m.from_user.id
    user = User(uid)
    link = f"https://t.me/{bot.get_me().username}?start={uid}"
    bot.send_message(uid, f"🎁 **Your Link:**\n{link}\n\nReferrals: {user.data.get('rc', 0)}\nReward: +{get_config().get('ref_reward', 5)} points each", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "👤 ME")
def account_cmd(m):
    user = User(m.from_user.id)
    methods = len(user.purchased_methods())
    bot.send_message(m.from_user.id, f"👤 **Account**\nPoints: {user.points()}\nVIP: {'Yes' if user.is_vip() else 'No'}\nMethods: {methods}\nReferrals: {user.data.get('rc', 0)}", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📚 MY")
def my_methods(m):
    user = User(m.from_user.id)
    purchased = user.purchased_methods()
    if not purchased:
        bot.send_message(m.from_user.id, "No purchased methods yet!")
        return
    
    kb = InlineKeyboardMarkup()
    for method in purchased:
        kb.add(InlineKeyboardButton(method, callback_data=f"op|vip|{method}|"))
    bot.send_message(m.from_user.id, "📚 Your methods:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "🆔 ID")
def chatid_cmd(m):
    bot.send_message(m.from_user.id, f"🆔 Your ID: `{m.from_user.id}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🏆 CODE")
def redeem_cmd(m):
    msg = bot.send_message(m.from_user.id, "🎫 Enter code:")
    bot.register_next_step_handler(msg, redeem_code)

def redeem_code(m):
    user = User(m.from_user.id)
    success, pts, reason = codesys.redeem(m.text.strip().upper(), user)
    if success:
        bot.send_message(m.from_user.id, f"✅ +{pts} points! Total: {user.points()}")
    else:
        bot.send_message(m.from_user.id, f"❌ {reason}")

@bot.message_handler(func=lambda m: m.text == "⭐ VIP")
def vip_info(m):
    cfg = get_config()
    contact = cfg.get("vip_contact")
    msg = f"💎 **VIP Membership**\n\n{cfg.get('vip_msg')}\n\nContact admin to buy VIP!"
    kb = InlineKeyboardMarkup()
    if contact:
        if contact.startswith("http"):
            kb.add(InlineKeyboardButton("📞 Contact", url=contact))
        else:
            kb.add(InlineKeyboardButton("📞 Contact", url=f"https://t.me/{contact.replace('@','')}"))
    bot.send_message(m.from_user.id, msg, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "get_vip")
def get_vip_callback(c):
    vip_info(c)

# =========================
# ⚙️ ADMIN PANEL - SIMPLIFIED
# =========================
def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📤 UP FREE", "📤 UP VIP")
    kb.row("📤 UP APP", "📤 UP SVC")
    kb.row("📁 SUB", "🗑 DEL")
    kb.row("✏️ PRICE", "✏️ NAME")
    kb.row("👑 +VIP", "👑 -VIP")
    kb.row("💰 GIVE", "🎫 CODE")
    kb.row("📦 PKG", "📞 CONTACT")
    kb.row("🔘 +BTN", "🔘 -BTN")
    kb.row("➕ +FC", "➖ -FC")
    kb.row("📊 STATS", "📢 BC")
    kb.row("⚙️ SET", "❌ EXIT")
    return kb

@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN" and is_admin(m.from_user.id))
def open_admin(m):
    bot.send_message(m.from_user.id, "⚙️ Admin Panel", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "❌ EXIT" and is_admin(m.from_user.id))
def exit_admin(m):
    bot.send_message(m.from_user.id, "Exited", reply_markup=main_menu(m.from_user.id))

# =========================
# UPLOAD SYSTEM
# =========================
def start_upload(uid, cat, is_service=False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📄 TEXT", "📁 FILE")
    kb.row("/cancel")
    msg = bot.send_message(uid, f"Upload to {cat}:", reply_markup=kb)
    bot.register_next_step_handler(msg, lambda m: upload_type(m, cat, is_service))

def upload_type(m, cat, is_service):
    if m.text == "/cancel":
        bot.send_message(m.from_user.id, "Cancelled", reply_markup=admin_menu())
        return
    if m.text == "📄 TEXT":
        msg = bot.send_message(m.from_user.id, "Name:")
        bot.register_next_step_handler(msg, lambda x: upload_text_name(x, cat, is_service))
    elif m.text == "📁 FILE":
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row("/done", "/cancel")
        msg = bot.send_message(m.from_user.id, "Send files:", reply_markup=kb)
        bot.register_next_step_handler(msg, lambda x: upload_file_step(x, cat, m.from_user.id, [], is_service))

def upload_text_name(m, cat, is_service):
    name = m.text
    msg = bot.send_message(m.from_user.id, "Price (0 for free):")
    bot.register_next_step_handler(msg, lambda x: upload_text_price(x, cat, name, is_service))

def upload_text_price(m, cat, name, is_service):
    try:
        price = int(m.text)
        msg = bot.send_message(m.from_user.id, "Content:")
        bot.register_next_step_handler(msg, lambda x: upload_text_save(x, cat, name, price, is_service))
    except:
        bot.send_message(m.from_user.id, "Invalid price!")

def upload_text_save(m, cat, name, price, is_service):
    text = m.text
    num = fs.add(cat, name, [], price, text_content=text)
    if is_service:
        folders_col.update_one({"c": cat, "n": name}, {"$set": {"tc": text}})
    bot.send_message(m.from_user.id, f"✅ Added! #{num}", reply_markup=admin_menu())

def upload_file_step(m, cat, uid, files, is_service):
    if m.text == "/cancel":
        bot.send_message(uid, "Cancelled", reply_markup=admin_menu())
        return
    if m.text == "/done":
        if not files:
            bot.send_message(uid, "No files!")
            return
        msg = bot.send_message(uid, "Name:")
        bot.register_next_step_handler(msg, lambda x: upload_file_name(x, cat, files, is_service))
        return
    if m.content_type in ["document", "photo", "video"]:
        files.append({"chat": m.chat.id, "msg": m.message_id})
        bot.send_message(uid, f"Saved ({len(files)})")
    bot.register_next_step_handler(m, lambda x: upload_file_step(x, cat, uid, files, is_service))

def upload_file_name(m, cat, files, is_service):
    name = m.text
    msg = bot.send_message(m.from_user.id, "Price:")
    bot.register_next_step_handler(msg, lambda x: upload_file_save(x, cat, name, files, is_service))

def upload_file_save(m, cat, name, files, is_service):
    try:
        price = int(m.text)
        num = fs.add(cat, name, files, price)
        if is_service:
            msg = bot.send_message(m.from_user.id, "Service message:")
            bot.register_next_step_handler(msg, lambda x: service_msg_save(x, cat, name, num, price, files))
        else:
            bot.send_message(m.from_user.id, f"✅ Uploaded! #{num}", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "Invalid price!")

def service_msg_save(m, cat, name, num, price, files):
    folders_col.update_one({"c": cat, "n": name}, {"$set": {"tc": m.text}})
    bot.send_message(m.from_user.id, f"✅ Service added! #{num}", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📤 UP FREE" and is_admin(m.from_user.id))
def up_free(m): start_upload(m.from_user.id, "free")
@bot.message_handler(func=lambda m: m.text == "📤 UP VIP" and is_admin(m.from_user.id))
def up_vip(m): start_upload(m.from_user.id, "vip")
@bot.message_handler(func=lambda m: m.text == "📤 UP APP" and is_admin(m.from_user.id))
def up_apps(m): start_upload(m.from_user.id, "apps")
@bot.message_handler(func=lambda m: m.text == "📤 UP SVC" and is_admin(m.from_user.id))
def up_service(m): start_upload(m.from_user.id, "services", True)

# =========================
# SUBFOLDER
# =========================
@bot.message_handler(func=lambda m: m.text == "📁 SUB" and is_admin(m.from_user.id))
def create_sub(m):
    msg = bot.send_message(m.from_user.id, "Send: cat parent name price\nExample: free Main Sub 10")
    bot.register_next_step_handler(msg, create_sub_process)

def create_sub_process(m):
    try:
        cat, parent, name, price = m.text.split()
        price = int(price)
        if fs.get_one(cat, parent):
            num = fs.add(cat, name, [], price, parent)
            bot.send_message(m.from_user.id, f"✅ Subfolder #{num} created!")
        else:
            bot.send_message(m.from_user.id, "Parent not found!")
    except:
        bot.send_message(m.from_user.id, "Invalid! Use: cat parent name price")

# =========================
# DELETE
# =========================
@bot.message_handler(func=lambda m: m.text == "🗑 DEL" and is_admin(m.from_user.id))
def del_start(m):
    msg = bot.send_message(m.from_user.id, "Send: cat name\nExample: free MyFolder")
    bot.register_next_step_handler(msg, del_process)

def del_process(m):
    try:
        cat, name = m.text.split(maxsplit=1)
        if fs.delete(cat, name):
            bot.send_message(m.from_user.id, "✅ Deleted!")
        else:
            bot.send_message(m.from_user.id, "Not found!")
    except:
        bot.send_message(m.from_user.id, "Invalid! Use: cat name")

# =========================
# EDIT PRICE
# =========================
@bot.message_handler(func=lambda m: m.text == "✏️ PRICE" and is_admin(m.from_user.id))
def edit_price_start(m):
    msg = bot.send_message(m.from_user.id, "Send: cat name price\nExample: vip Method 50")
    bot.register_next_step_handler(msg, edit_price_process)

def edit_price_process(m):
    try:
        cat, name, price = m.text.split()
        price = int(price)
        fs.edit_price(cat, name, price)
        bot.send_message(m.from_user.id, "✅ Price updated!")
    except:
        bot.send_message(m.from_user.id, "Invalid!")

# =========================
# EDIT NAME
# =========================
@bot.message_handler(func=lambda m: m.text == "✏️ NAME" and is_admin(m.from_user.id))
def edit_name_start(m):
    msg = bot.send_message(m.from_user.id, "Send: cat old new\nExample: free Old New")
    bot.register_next_step_handler(msg, edit_name_process)

def edit_name_process(m):
    try:
        cat, old, new = m.text.split()
        fs.edit_name(cat, old, new)
        bot.send_message(m.from_user.id, "✅ Renamed!")
    except:
        bot.send_message(m.from_user.id, "Invalid!")

# =========================
# VIP MANAGEMENT
# =========================
@bot.message_handler(func=lambda m: m.text == "👑 +VIP" and is_admin(m.from_user.id))
def add_vip(m):
    msg = bot.send_message(m.from_user.id, "Send user ID:")
    bot.register_next_step_handler(msg, add_vip_process)

def add_vip_process(m):
    try:
        uid = int(m.text)
        user = User(uid)
        user.make_vip()
        bot.send_message(m.from_user.id, f"✅ VIP added!")
        try:
            bot.send_message(uid, "🎉 You are now VIP!")
        except:
            pass
    except:
        bot.send_message(m.from_user.id, "Invalid ID!")

@bot.message_handler(func=lambda m: m.text == "👑 -VIP" and is_admin(m.from_user.id))
def remove_vip(m):
    msg = bot.send_message(m.from_user.id, "Send user ID:")
    bot.register_next_step_handler(msg, remove_vip_process)

def remove_vip_process(m):
    try:
        uid = int(m.text)
        user = User(uid)
        user.remove_vip()
        bot.send_message(m.from_user.id, f"✅ VIP removed!")
    except:
        bot.send_message(m.from_user.id, "Invalid ID!")

# =========================
# GIVE POINTS
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 GIVE" and is_admin(m.from_user.id))
def give_points(m):
    msg = bot.send_message(m.from_user.id, "Send: user_id points\nExample: 123456789 100")
    bot.register_next_step_handler(msg, give_points_process)

def give_points_process(m):
    try:
        uid, pts = m.text.split()
        pts = int(pts)
        user = User(uid)
        old = user.points()
        user.add_points(pts)
        bot.send_message(m.from_user.id, f"✅ Added {pts} points!\nOld: {old}\nNew: {user.points()}")
        try:
            bot.send_message(int(uid), f"🎉 +{pts} points! New balance: {user.points()}")
        except:
            pass
    except:
        bot.send_message(m.from_user.id, "Invalid! Use: user_id points")

# =========================
# GENERATE CODES
# =========================
@bot.message_handler(func=lambda m: m.text == "🎫 CODE" and is_admin(m.from_user.id))
def gen_code(m):
    msg = bot.send_message(m.from_user.id, "Send: points count\nExample: 100 5")
    bot.register_next_step_handler(msg, gen_code_process)

def gen_code_process(m):
    try:
        pts, count = m.text.split()
        pts = int(pts)
        count = int(count)
        codes = codesys.generate(pts, count)
        bot.send_message(m.from_user.id, f"✅ Generated {count} codes:\n" + "\n".join(codes))
    except:
        bot.send_message(m.from_user.id, "Invalid! Use: points count")

# =========================
# POINTS PACKAGES
# =========================
@bot.message_handler(func=lambda m: m.text == "📦 PKG" and is_admin(m.from_user.id))
def manage_packages(m):
    cfg = get_config()
    packages = cfg.get("points_packages", [])
    msg = "📦 Packages:\n"
    for i, pkg in enumerate(packages, 1):
        msg += f"{i}. {pkg['points']} pts = ${pkg['price']}"
        if pkg.get('bonus', 0) > 0:
            msg += f" (+{pkg['bonus']})"
        msg += "\n"
    msg += "\nCommands:\n/addpkg points price bonus\n/editpkg num points price bonus\n/delpkg num"
    bot.send_message(m.from_user.id, msg)

@bot.message_handler(commands=["addpkg"])
def add_pkg(m):
    if not is_admin(m.from_user.id):
        return
    try:
        _, points, price, bonus = m.text.split()
        cfg = get_config()
        pkgs = cfg.get("points_packages", [])
        pkgs.append({"points": int(points), "price": int(price), "bonus": int(bonus)})
        set_config("points_packages", pkgs)
        bot.send_message(m.from_user.id, "✅ Package added!")
    except:
        bot.send_message(m.from_user.id, "Use: /addpkg points price bonus")

@bot.message_handler(commands=["editpkg"])
def edit_pkg(m):
    if not is_admin(m.from_user.id):
        return
    try:
        _, num, points, price, bonus = m.text.split()
        num = int(num) - 1
        cfg = get_config()
        pkgs = cfg.get("points_packages", [])
        if 0 <= num < len(pkgs):
            pkgs[num] = {"points": int(points), "price": int(price), "bonus": int(bonus)}
            set_config("points_packages", pkgs)
            bot.send_message(m.from_user.id, "✅ Package edited!")
        else:
            bot.send_message(m.from_user.id, "Invalid number!")
    except:
        bot.send_message(m.from_user.id, "Use: /editpkg num points price bonus")

@bot.message_handler(commands=["delpkg"])
def del_pkg(m):
    if not is_admin(m.from_user.id):
        return
    try:
        _, num = m.text.split()
        num = int(num) - 1
        cfg = get_config()
        pkgs = cfg.get("points_packages", [])
        if 0 <= num < len(pkgs):
            pkgs.pop(num)
            set_config("points_packages", pkgs)
            bot.send_message(m.from_user.id, "✅ Package deleted!")
        else:
            bot.send_message(m.from_user.id, "Invalid number!")
    except:
        bot.send_message(m.from_user.id, "Use: /delpkg num")

# =========================
# CONTACT SETTINGS
# =========================
@bot.message_handler(func=lambda m: m.text == "📞 CONTACT" and is_admin(m.from_user.id))
def set_contact(m):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💰 Points Contact", callback_data="set_points"))
    kb.add(InlineKeyboardButton("⭐ VIP Contact", callback_data="set_vip"))
    bot.send_message(m.from_user.id, "Select contact type:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["set_points", "set_vip"])
def set_contact_type(c):
    key = "contact_link" if c.data == "set_points" else "vip_contact"
    msg = bot.send_message(c.from_user.id, "Send @username or link (or 'none' to remove):")
    bot.register_next_step_handler(msg, lambda x: save_contact(x, key))

def save_contact(m, key):
    if m.text.lower() == "none":
        set_config(key, None)
        bot.send_message(m.from_user.id, "✅ Removed!")
    elif m.text.startswith("http") or m.text.startswith("@"):
        set_config(key, m.text)
        bot.send_message(m.from_user.id, f"✅ Set: {m.text}")
    else:
        bot.send_message(m.from_user.id, "Invalid! Use @username or https://t.me/username")

# =========================
# CUSTOM BUTTONS
# =========================
@bot.message_handler(func=lambda m: m.text == "🔘 +BTN" and is_admin(m.from_user.id))
def add_btn(m):
    msg = bot.send_message(m.from_user.id, "Send: type|text|data\nTypes: link, folder\nExample: link|Website|https://example.com")
    bot.register_next_step_handler(msg, add_btn_process)

def add_btn_process(m):
    try:
        btype, text, data = m.text.split("|")
        if btype == "folder":
            if not fs.get_by_number(int(data)):
                bot.send_message(m.from_user.id, "Folder not found!")
                return
        add_custom_button(text, btype, data)
        bot.send_message(m.from_user.id, "✅ Button added!")
    except:
        bot.send_message(m.from_user.id, "Invalid! Use: type|text|data")

@bot.message_handler(func=lambda m: m.text == "🔘 -BTN" and is_admin(m.from_user.id))
def remove_btn(m):
    btns = get_custom_buttons()
    if not btns:
        bot.send_message(m.from_user.id, "No buttons!")
        return
    kb = InlineKeyboardMarkup()
    for btn in btns:
        kb.add(InlineKeyboardButton(f"❌ {btn['text']}", callback_data=f"rmbtn|{btn['text']}"))
    bot.send_message(m.from_user.id, "Select to remove:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rmbtn|"))
def remove_btn_process(c):
    text = c.data.split("|")[1]
    remove_custom_button(text)
    bot.edit_message_text(f"✅ Removed: {text}", c.from_user.id, c.message.message_id)

# =========================
# FORCE JOIN
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ +FC" and is_admin(m.from_user.id))
def add_fc(m):
    msg = bot.send_message(m.from_user.id, "Send @channel:")
    bot.register_next_step_handler(msg, add_fc_process)

def add_fc_process(m):
    cfg = get_config()
    chs = cfg.get("force_channels", [])
    if m.text not in chs:
        chs.append(m.text)
        set_config("force_channels", chs)
        bot.send_message(m.from_user.id, "✅ Added!")
    else:
        bot.send_message(m.from_user.id, "Already exists!")

@bot.message_handler(func=lambda m: m.text == "➖ -FC" and is_admin(m.from_user.id))
def remove_fc(m):
    cfg = get_config()
    chs = cfg.get("force_channels", [])
    if not chs:
        bot.send_message(m.from_user.id, "No channels!")
        return
    kb = InlineKeyboardMarkup()
    for ch in chs:
        kb.add(InlineKeyboardButton(f"❌ {ch}", callback_data=f"rmfc|{ch}"))
    bot.send_message(m.from_user.id, "Select to remove:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rmfc|"))
def remove_fc_process(c):
    ch = c.data.split("|")[1]
    cfg = get_config()
    chs = cfg.get("force_channels", [])
    if ch in chs:
        chs.remove(ch)
        set_config("force_channels", chs)
        bot.edit_message_text(f"✅ Removed: {ch}", c.from_user.id, c.message.message_id)

# =========================
# STATISTICS
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 STATS" and is_admin(m.from_user.id))
def show_stats(m):
    total = users_col.count_documents({})
    vip = users_col.count_documents({"v": True})
    total_points = sum(u.get("p", 0) for u in users_col.find({}, {"p": 1}))
    
    msg = f"📊 **Stats**\n"
    msg += f"Users: {total}\n"
    msg += f"VIP: {vip}\n"
    msg += f"Free: {total - vip}\n"
    msg += f"Points: {total_points}\n"
    msg += f"Folders: {folders_col.count_documents({})}\n"
    msg += f"Codes: {codes_col.count_documents({})}"
    
    bot.send_message(m.from_user.id, msg, parse_mode="Markdown")

# =========================
# BROADCAST
# =========================
@bot.message_handler(func=lambda m: m.text == "📢 BC" and is_admin(m.from_user.id))
def broadcast_start(m):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("All", callback_data="bc|all"))
    kb.add(InlineKeyboardButton("VIP", callback_data="bc|vip"))
    kb.add(InlineKeyboardButton("Free", callback_data="bc|free"))
    bot.send_message(m.from_user.id, "Target:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("bc|"))
def broadcast_target(c):
    target = c.data.split("|")[1]
    msg = bot.send_message(c.from_user.id, "Send message:")
    bot.register_next_step_handler(msg, lambda x: broadcast_send(x, target))

def broadcast_send(m, target):
    query = {}
    if target == "vip":
        query = {"v": True}
    elif target == "free":
        query = {"v": False}
    
    users = list(users_col.find(query, {"_id": 1}))
    sent = 0
    
    for user in users:
        try:
            if m.content_type == "text":
                bot.send_message(int(user["_id"]), m.text)
            elif m.content_type == "photo":
                bot.send_photo(int(user["_id"]), m.photo[-1].file_id, caption=m.caption)
            elif m.content_type == "video":
                bot.send_video(int(user["_id"]), m.video.file_id, caption=m.caption)
            sent += 1
        except:
            pass
        if sent % 20 == 0:
            time.sleep(1)
    
    bot.send_message(m.from_user.id, f"✅ Sent to {sent} users!")

# =========================
# SETTINGS
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ SET" and is_admin(m.from_user.id))
def settings_menu(m):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("VIP Msg", callback_data="set_vip_msg"),
        InlineKeyboardButton("Welcome", callback_data="set_welcome"),
        InlineKeyboardButton("Ref Reward", callback_data="set_ref"),
        InlineKeyboardButton("Notify", callback_data="toggle_notify")
    )
    bot.send_message(m.from_user.id, "Settings:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "set_vip_msg")
def set_vip_msg_cb(c):
    msg = bot.send_message(c.from_user.id, "Send VIP message:")
    bot.register_next_step_handler(msg, lambda x: set_config("vip_msg", x.text))

@bot.callback_query_handler(func=lambda c: c.data == "set_welcome")
def set_welcome_cb(c):
    msg = bot.send_message(c.from_user.id, "Send welcome message:")
    bot.register_next_step_handler(msg, lambda x: set_config("welcome", x.text))

@bot.callback_query_handler(func=lambda c: c.data == "set_ref")
def set_ref_cb(c):
    msg = bot.send_message(c.from_user.id, "Send referral reward (points):")
    bot.register_next_step_handler(msg, lambda x: set_config("ref_reward", int(x.text)))

@bot.callback_query_handler(func=lambda c: c.data == "toggle_notify")
def toggle_notify_cb(c):
    cfg = get_config()
    set_config("notify", not cfg.get("notify", True))
    bot.answer_callback_query(c.id, f"Notify: {not cfg.get('notify', True)}")

# =========================
# RECHECK FORCE JOIN
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "recheck")
def recheck(c):
    if not force_block(c.from_user.id):
        bot.send_message(c.from_user.id, "✅ Access granted!", reply_markup=main_menu(c.from_user.id))
    else:
        bot.answer_callback_query(c.id, "Still not joined!", True)

# =========================
# FALLBACK
# =========================
@bot.message_handler(func=lambda m: True)
def fallback(m):
    if force_block(m.from_user.id):
        return
    
    custom_btns = get_custom_buttons()
    for btn in custom_btns:
        if m.text == btn["text"]:
            if btn["type"] == "link":
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton("🔗 Open", url=btn["data"]))
                bot.send_message(m.from_user.id, f"🔗 {btn['text']}", reply_markup=kb)
            return
    
    known = ["📂 FREE", "💎 VIP", "📦 APPS", "⚡ SERVICES", "💰 POINTS", "⭐ VIP", "🎁 REFER", "👤 ME", "📚 MY", "🆔 ID", "🏆 CODE", "💎 BUY", "⚙️ ADMIN"]
    if m.text and m.text not in known:
        bot.send_message(m.from_user.id, "❌ Use menu buttons", reply_markup=main_menu(m.from_user.id))

# =========================
# RUN BOT
# =========================
def run_bot():
    while True:
        try:
            print("=" * 40)
            print("🚀 ZEDOX BOT - OPTIMIZED")
            print(f"✅ Bot: @{bot.get_me().username}")
            print(f"💾 MongoDB: Optimized for 512MB")
            print(f"📊 Storage: ~100 bytes per user")
            print("=" * 40)
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    while True:
        time.sleep(1)
