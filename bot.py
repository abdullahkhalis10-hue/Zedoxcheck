# =========================
# ZEDOX BOT - TRULY OPTIMIZED FOR 512MB
# Focus on what actually matters
# =========================

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
import os, time, random, string, threading
from pymongo import MongoClient

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))

MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["zedox"]

# Normal readable field names - the savings aren't worth the confusion
users_col = db["users"]
folders_col = db["folders"]
codes_col = db["codes"]
config_col = db["config"]

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# =========================
# CONFIG - Minimal queries (THIS SAVES MORE)
# =========================
_config_cache = None
_config_cache_time = 0

def get_config():
    global _config_cache, _config_cache_time
    # Cache config for 60 seconds to reduce database reads
    if _config_cache and time.time() - _config_cache_time < 60:
        return _config_cache
    
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
    
    _config_cache = cfg
    _config_cache_time = time.time()
    return cfg

def set_config(key, value):
    global _config_cache
    config_col.update_one({"_id": "config"}, {"$set": {key: value}}, upsert=True)
    _config_cache = None  # Invalidate cache

# =========================
# USER SYSTEM - With caching (THIS SAVES MORE)
# =========================
_user_cache = {}
_user_cache_time = {}

def get_user(uid):
    """Get user with 30-second cache to reduce DB reads"""
    uid = str(uid)
    
    # Check cache
    if uid in _user_cache and time.time() - _user_cache_time.get(uid, 0) < 30:
        return _user_cache[uid]
    
    data = users_col.find_one({"_id": uid})
    if not data:
        data = {
            "_id": uid,
            "points": 0,
            "vip": False,
            "referred_by": None,
            "referrals": 0,
            "purchased_methods": [],
            "used_codes": [],
            "username": None,
            "created_at": time.time()
        }
        users_col.insert_one(data)
    
    _user_cache[uid] = data
    _user_cache_time[uid] = time.time()
    return data

def save_user(uid, data):
    """Save user and update cache"""
    uid = str(uid)
    users_col.update_one({"_id": uid}, {"$set": data}, upsert=True)
    _user_cache[uid] = data
    _user_cache_time[uid] = time.time()

# =========================
# SIMPLE USER CLASS
# =========================
class User:
    def __init__(self, uid):
        self.uid = str(uid)
        self.data = get_user(uid)
    
    def save(self):
        save_user(self.uid, self.data)
    
    def points(self): 
        return self.data.get("points", 0)
    
    def is_vip(self): 
        return self.data.get("vip", False)
    
    def add_points(self, p):
        self.data["points"] = self.data.get("points", 0) + p
        self.save()
    
    def spend_points(self, p):
        self.data["points"] = self.data.get("points", 0) - p
        self.save()
    
    def make_vip(self):
        self.data["vip"] = True
        self.save()
    
    def remove_vip(self):
        self.data["vip"] = False
        self.save()
    
    def purchase_method(self, method_name, price):
        if self.points() >= price:
            self.spend_points(price)
            purchased = self.data.get("purchased_methods", [])
            if method_name not in purchased:
                purchased.append(method_name)
                self.data["purchased_methods"] = purchased
                self.save()
            return True
        return False
    
    def can_access_method(self, method_name):
        return self.is_vip() or method_name in self.data.get("purchased_methods", [])
    
    def add_used_code(self, code):
        used = self.data.get("used_codes", [])
        if code not in used:
            used.append(code)
            self.data["used_codes"] = used
            self.save()
            return True
        return False
    
    def add_referral(self):
        self.data["referrals"] = self.data.get("referrals", 0) + 1
        self.save()

# =========================
# CONTENT SYSTEM - With pagination (REDUCES DATA TRANSFER)
# =========================
class FS:
    def add(self, category, name, files, price, parent=None, text_content=None):
        config = get_config()
        number = config.get("next_folder_number", 1)
        set_config("next_folder_number", number + 1)
        
        folders_col.insert_one({
            "category": category,
            "name": name,
            "files": files,
            "price": price,
            "parent": parent,
            "number": number,
            "text_content": text_content,
            "created_at": time.time()
        })
        return number
    
    def get(self, category, parent=None, limit=20, skip=0):
        """Get folders with pagination - reduces data transfer"""
        query = {"category": category}
        if parent:
            query["parent"] = parent
        else:
            query["parent"] = None
        
        total = folders_col.count_documents(query)
        items = list(folders_col.find(query).sort("number", 1).skip(skip).limit(limit))
        
        return {
            "items": items,
            "total": total,
            "has_more": skip + limit < total
        }
    
    def get_one(self, category, name, parent=None):
        query = {"category": category, "name": name}
        if parent:
            query["parent"] = parent
        return folders_col.find_one(query)
    
    def get_by_number(self, number):
        return folders_col.find_one({"number": number})
    
    def delete(self, category, name, parent=None):
        query = {"category": category, "name": name}
        if parent:
            query["parent"] = parent
        result = folders_col.delete_one(query)
        return result.deleted_count > 0
    
    def edit_price(self, category, name, price, parent=None):
        query = {"category": category, "name": name}
        if parent:
            query["parent"] = parent
        folders_col.update_one(query, {"$set": {"price": price}})

fs = FS()

# =========================
# CODES SYSTEM - With auto-cleanup (PREVENTS BLOAT)
# =========================
class Codes:
    def generate(self, points, count, multi_use=False, expiry_days=7):
        """Generate codes with expiry (auto-cleanup saves space)"""
        res = []
        expiry = time.time() + (expiry_days * 86400) if expiry_days else time.time() + 86400  # Default 1 day
        
        for _ in range(count):
            code = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
            codes_col.insert_one({
                "_id": code,
                "points": points,
                "used": False,
                "multi_use": multi_use,
                "used_by": [],
                "used_count": 0,
                "expiry": expiry,
                "created_at": time.time()
            })
            res.append(code)
        return res
    
    def redeem(self, code, user):
        code_data = codes_col.find_one({"_id": code})
        
        if not code_data:
            return False, 0, "invalid"
        
        if code_data.get("expiry") and time.time() > code_data["expiry"]:
            codes_col.delete_one({"_id": code})  # Auto-delete expired codes
            return False, 0, "expired"
        
        if not code_data.get("multi_use", False) and code_data.get("used", False):
            return False, 0, "already_used"
        
        if user.uid in code_data.get("used_by", []):
            return False, 0, "already_used"
        
        points = code_data["points"]
        user.add_points(points)
        
        if code_data.get("multi_use", False):
            codes_col.update_one(
                {"_id": code},
                {"$push": {"used_by": user.uid}, "$inc": {"used_count": 1}}
            )
        else:
            codes_col.update_one({"_id": code}, {"$set": {"used": True}})
        
        user.add_used_code(code)
        return True, points, "success"

codesys = Codes()

# =========================
# CLEANUP OLD CODES (RUN EVERY DAY)
# =========================
def cleanup_old_codes():
    """Delete expired codes automatically - THIS SAVES SPACE"""
    while True:
        try:
            # Delete expired codes older than 7 days
            expiry_time = time.time() - (7 * 86400)
            result = codes_col.delete_many({
                "expiry": {"$lt": time.time()},
                "used": True
            })
            if result.deleted_count > 0:
                print(f"Cleaned up {result.deleted_count} old codes")
        except:
            pass
        time.sleep(86400)  # Run once per day

# Start cleanup thread
threading.Thread(target=cleanup_old_codes, daemon=True).start()

# =========================
# FORCE JOIN
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
    return get_config().get("custom_buttons", [])

def add_custom_button(button_text, button_type, button_data):
    cfg = get_config()
    buttons = cfg.get("custom_buttons", [])
    buttons.append({"text": button_text, "type": button_type, "data": button_data})
    set_config("custom_buttons", buttons)

def remove_custom_button(button_text):
    cfg = get_config()
    buttons = cfg.get("custom_buttons", [])
    buttons = [b for b in buttons if b["text"] != button_text]
    set_config("custom_buttons", buttons)

def is_admin(uid):
    return uid == ADMIN_ID

# =========================
# MAIN MENU
# =========================
def main_menu(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📂 FREE METHODS", "💎 VIP METHODS")
    kb.row("📦 PREMIUM APPS", "⚡ SERVICES")
    kb.row("💰 POINTS", "⭐ BUY VIP")
    
    for btn in get_custom_buttons():
        kb.row(btn["text"])
    
    kb.row("🎁 REFERRAL", "👤 ACCOUNT")
    kb.row("📚 MY METHODS", "💎 GET POINTS")
    kb.row("🆔 CHAT ID", "🏆 REDEEM")
    
    if is_admin(uid):
        kb.row("⚙️ ADMIN PANEL")
    return kb

# =========================
# START
# =========================
@bot.message_handler(commands=["start"])
def start_cmd(m):
    uid = m.from_user.id
    args = m.text.split()
    
    user = User(uid)
    
    if m.from_user.username:
        user.data["username"] = m.from_user.username
        user.save()
    
    if len(args) > 1:
        ref_id = args[1]
        if ref_id != str(uid) and ref_id.isdigit():
            ref_user = users_col.find_one({"_id": ref_id})
            if ref_user and not user.data.get("referred_by"):
                reward = get_config().get("ref_reward", 5)
                User(ref_id).add_points(reward)
                user.data["referred_by"] = ref_id
                user.add_referral()
                user.save()
                try:
                    bot.send_message(int(ref_id), f"🎉 New referral! +{reward} points!")
                except:
                    pass
    
    if force_block(uid):
        return
    
    cfg = get_config()
    bot.send_message(uid, f"{cfg.get('welcome')}\n💰 Points: {user.points()}", reply_markup=main_menu(uid))

# =========================
# POINTS
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 POINTS")
def points_cmd(m):
    user = User(m.from_user.id)
    bot.send_message(m.from_user.id, f"💰 **Points:** {user.points()}\n⭐ **VIP:** {'Yes' if user.is_vip() else 'No'}\n📚 **Methods:** {len(user.data.get('purchased_methods', []))}", parse_mode="Markdown")

# =========================
# GET POINTS
# =========================
@bot.message_handler(func=lambda m: m.text == "💎 GET POINTS")
def get_points(m):
    uid = m.from_user.id
    user = User(uid)
    cfg = get_config()
    packages = cfg.get("points_packages", [])
    
    msg = f"💰 **BUY POINTS**\n\nYour balance: {user.points()}\n\n"
    for i, pkg in enumerate(packages, 1):
        total = pkg["points"] + pkg.get("bonus", 0)
        msg += f"{i}. {pkg['points']} points = ${pkg['price']}"
        if pkg.get("bonus", 0) > 0:
            msg += f" (+{pkg['bonus']} bonus = {total} points)"
        msg += "\n"
    
    msg += "\n📞 Contact admin to buy points!"
    
    contact = cfg.get("contact_link") or cfg.get("contact_username")
    kb = InlineKeyboardMarkup()
    if contact:
        if contact.startswith("http"):
            kb.add(InlineKeyboardButton("📞 Contact Admin", url=contact))
        else:
            kb.add(InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{contact.replace('@','')}"))
    
    bot.send_message(uid, msg, reply_markup=kb, parse_mode="Markdown")

# =========================
# SHOW FOLDERS WITH PAGINATION
# =========================
def get_folders_kb(category, parent=None, page=0, items_per_page=10):
    result = fs.get(category, parent, limit=items_per_page, skip=page * items_per_page)
    items = result["items"]
    
    kb = InlineKeyboardMarkup(row_width=2)
    
    for item in items:
        name = item["name"]
        price = item.get("price", 0)
        number = item.get("number", "?")
        has_sub = len(fs.get(category, name)["items"]) > 0
        icon = "📁" if has_sub else "📄"
        text = f"{icon}[{number}] {name}"
        if price > 0:
            text += f" [{price}]"
        kb.add(InlineKeyboardButton(text, callback_data=f"open|{category}|{name}|{parent or ''}"))
    
    # Pagination buttons
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"page|{category}|{page-1}|{parent or ''}"))
    if result["has_more"]:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"page|{category}|{page+1}|{parent or ''}"))
    if nav:
        kb.row(*nav)
    
    if parent:
        kb.add(InlineKeyboardButton("🔙 Back", callback_data=f"back|{category}|{parent}"))
    
    return kb

@bot.message_handler(func=lambda m: m.text in ["📂 FREE METHODS", "💎 VIP METHODS", "📦 PREMIUM APPS", "⚡ SERVICES"])
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
    category = mapping.get(m.text)
    
    result = fs.get(category)
    if not result["items"]:
        bot.send_message(uid, "❌ No content yet!")
        return
    
    bot.send_message(uid, f"📂 {m.text}:", reply_markup=get_folders_kb(category))

# =========================
# PAGINATION HANDLER
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("page|"))
def page_handler(c):
    _, category, page, parent = c.data.split("|")
    parent = parent if parent != "None" else None
    page = int(page)
    
    try:
        bot.edit_message_reply_markup(
            c.from_user.id,
            c.message.message_id,
            reply_markup=get_folders_kb(category, parent, page)
        )
    except:
        pass
    bot.answer_callback_query(c.id)

# =========================
# OPEN FOLDER
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("open|"))
def open_folder(c):
    uid = c.from_user.id
    user = User(uid)
    _, category, name, parent = c.data.split("|")
    parent = parent if parent else None
    
    folder = fs.get_one(category, name, parent)
    if not folder:
        bot.answer_callback_query(c.id, "Not found")
        return
    
    # Check for subfolders
    subfolders = fs.get(category, name)
    if subfolders["items"]:
        bot.edit_message_reply_markup(uid, c.message.message_id, reply_markup=get_folders_kb(category, name))
        bot.answer_callback_query(c.id)
        return
    
    # Handle services
    if category == "services":
        price = folder.get("price", 0)
        if price > 0 and not user.is_vip():
            if user.points() < price:
                bot.answer_callback_query(c.id, f"Need {price} points!", True)
                return
            user.spend_points(price)
        msg = folder.get("text_content", "✅ Service activated!")
        bot.send_message(uid, msg)
        bot.answer_callback_query(c.id)
        return
    
    # Handle text content
    text_content = folder.get("text_content")
    if text_content:
        price = folder.get("price", 0)
        
        if category == "vip" and not user.is_vip() and not user.can_access_method(name):
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton(f"💰 Buy ({price} pts)", callback_data=f"buy|{category}|{name}|{price}"))
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
    price = folder.get("price", 0)
    if category == "vip" and not user.is_vip() and not user.can_access_method(name):
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(f"💰 Buy ({price} pts)", callback_data=f"buy|{category}|{name}|{price}"))
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
    for f in folder.get("files", []):
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
    _, category, name, price = c.data.split("|")
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
@bot.callback_query_handler(func=lambda c: c.data.startswith("back|"))
def back_handler(c):
    _, category, parent = c.data.split("|")
    parent_folder = fs.get_one(category, parent)
    grand_parent = parent_folder.get("parent") if parent_folder else None
    bot.edit_message_reply_markup(
        c.from_user.id,
        c.message.message_id,
        reply_markup=get_folders_kb(category, grand_parent)
    )
    bot.answer_callback_query(c.id)

# =========================
# GET VIP
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "get_vip")
def get_vip_callback(c):
    vip_info(c)

@bot.message_handler(func=lambda m: m.text == "⭐ BUY VIP")
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
    bot.send_message(m.from_user.id if hasattr(m, 'from_user') else m, msg, reply_markup=kb, parse_mode="Markdown")

# =========================
# USER COMMANDS
# =========================
@bot.message_handler(func=lambda m: m.text == "🎁 REFERRAL")
def referral_cmd(m):
    user = User(m.from_user.id)
    link = f"https://t.me/{bot.get_me().username}?start={m.from_user.id}"
    bot.send_message(m.from_user.id, f"🎁 **Your Link:**\n{link}\n\nReferrals: {user.data.get('referrals', 0)}\nReward: +{get_config().get('ref_reward', 5)} points each", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "👤 ACCOUNT")
def account_cmd(m):
    user = User(m.from_user.id)
    bot.send_message(m.from_user.id, f"👤 **Account**\nPoints: {user.points()}\nVIP: {'Yes' if user.is_vip() else 'No'}\nMethods: {len(user.data.get('purchased_methods', []))}\nReferrals: {user.data.get('referrals', 0)}", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📚 MY METHODS")
def my_methods(m):
    user = User(m.from_user.id)
    purchased = user.data.get("purchased_methods", [])
    if not purchased:
        bot.send_message(m.from_user.id, "No purchased methods yet!")
        return
    
    kb = InlineKeyboardMarkup(row_width=2)
    for method in purchased:
        kb.add(InlineKeyboardButton(method, callback_data=f"open|vip|{method}|"))
    bot.send_message(m.from_user.id, "📚 Your methods:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "🆔 CHAT ID")
def chatid_cmd(m):
    bot.send_message(m.from_user.id, f"🆔 Your ID: `{m.from_user.id}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🏆 REDEEM")
def redeem_cmd(m):
    msg = bot.send_message(m.from_user.id, "🎫 Enter code:")
    bot.register_next_step_handler(msg, redeem_code)

def redeem_code(m):
    user = User(m.from_user.id)
    success, points, reason = codesys.redeem(m.text.strip().upper(), user)
    if success:
        bot.send_message(m.from_user.id, f"✅ +{points} points! Total: {user.points()}")
    else:
        bot.send_message(m.from_user.id, f"❌ {reason}")

# =========================
# RECHECK
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "recheck")
def recheck(c):
    if not force_block(c.from_user.id):
        bot.send_message(c.from_user.id, "✅ Access granted!", reply_markup=main_menu(c.from_user.id))
    else:
        bot.answer_callback_query(c.id, "Still not joined!", True)

# =========================
# ADMIN PANEL - SIMPLIFIED
# =========================
def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📤 Upload", "🗑 Delete", "✏️ Edit")
    kb.row("👑 VIP", "💰 Give Points")
    kb.row("🎫 Generate", "📊 Stats", "📢 Broadcast")
    kb.row("🔘 Buttons", "📞 Contact", "➕ Force")
    kb.row("⚙️ Settings", "❌ Exit")
    return kb

@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def open_admin(m):
    bot.send_message(m.from_user.id, "⚙️ Admin Panel", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "❌ Exit" and is_admin(m.from_user.id))
def exit_admin(m):
    bot.send_message(m.from_user.id, "Exited", reply_markup=main_menu(m.from_user.id))

# =========================
# UPLOAD (Simplified)
# =========================
@bot.message_handler(func=lambda m: m.text == "📤 Upload" and is_admin(m.from_user.id))
def upload_menu(m):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("FREE", "VIP", "APPS", "SERVICES")
    kb.row("/cancel")
    msg = bot.send_message(m.from_user.id, "Select category:", reply_markup=kb)
    bot.register_next_step_handler(msg, upload_category)

def upload_category(m):
    if m.text == "/cancel":
        bot.send_message(m.from_user.id, "Cancelled", reply_markup=admin_menu())
        return
    
    cat = m.text.lower()
    if cat not in ["free", "vip", "apps", "services"]:
        bot.send_message(m.from_user.id, "Invalid!")
        return
    
    msg = bot.send_message(m.from_user.id, "Send files or text (press /done when done):", 
                          reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).row("/done", "/cancel"))
    bot.register_next_step_handler(msg, lambda x: upload_files(x, cat, []))

def upload_files(m, cat, files):
    if m.text == "/cancel":
        bot.send_message(m.from_user.id, "Cancelled", reply_markup=admin_menu())
        return
    if m.text == "/done":
        if not files:
            bot.send_message(m.from_user.id, "No files!")
            return
        msg = bot.send_message(m.from_user.id, "Folder name:")
        bot.register_next_step_handler(msg, lambda x: upload_name(x, cat, files))
        return
    if m.content_type in ["document", "photo", "video"]:
        files.append({"chat": m.chat.id, "msg": m.message_id})
        bot.send_message(m.from_user.id, f"Saved ({len(files)})")
    bot.register_next_step_handler(m, lambda x: upload_files(x, cat, files))

def upload_name(m, cat, files):
    name = m.text
    msg = bot.send_message(m.from_user.id, "Price (0 for free):")
    bot.register_next_step_handler(msg, lambda x: upload_price(x, cat, name, files))

def upload_price(m, cat, name, files):
    try:
        price = int(m.text)
        number = fs.add(cat, name, files, price)
        bot.send_message(m.from_user.id, f"✅ Uploaded! #{number}", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "Invalid price!")

# =========================
# DELETE
# =========================
@bot.message_handler(func=lambda m: m.text == "🗑 Delete" and is_admin(m.from_user.id))
def delete_folder(m):
    msg = bot.send_message(m.from_user.id, "Send: category name\nExample: free MyFolder")
    bot.register_next_step_handler(msg, delete_process)

def delete_process(m):
    try:
        cat, name = m.text.split(maxsplit=1)
        if fs.delete(cat, name):
            bot.send_message(m.from_user.id, "✅ Deleted!")
        else:
            bot.send_message(m.from_user.id, "Not found!")
    except:
        bot.send_message(m.from_user.id, "Invalid! Use: category name")

# =========================
# EDIT
# =========================
@bot.message_handler(func=lambda m: m.text == "✏️ Edit" and is_admin(m.from_user.id))
def edit_menu(m):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Price", callback_data="edit_price"))
    kb.add(InlineKeyboardButton("Name", callback_data="edit_name"))
    bot.send_message(m.from_user.id, "Edit what?", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["edit_price", "edit_name"])
def edit_type(c):
    if c.data == "edit_price":
        msg = bot.send_message(c.from_user.id, "Send: category name price\nExample: vip Method 50")
        bot.register_next_step_handler(msg, edit_price_process)
    else:
        msg = bot.send_message(c.from_user.id, "Send: category old new\nExample: free Old New")
        bot.register_next_step_handler(msg, edit_name_process)

def edit_price_process(m):
    try:
        cat, name, price = m.text.split()
        price = int(price)
        fs.edit_price(cat, name, price)
        bot.send_message(m.from_user.id, "✅ Price updated!")
    except:
        bot.send_message(m.from_user.id, "Invalid!")

def edit_name_process(m):
    try:
        cat, old, new = m.text.split()
        folder = fs.get_one(cat, old)
        if folder:
            folders_col.update_one({"_id": folder["_id"]}, {"$set": {"name": new}})
            bot.send_message(m.from_user.id, "✅ Renamed!")
        else:
            bot.send_message(m.from_user.id, "Not found!")
    except:
        bot.send_message(m.from_user.id, "Invalid!")

# =========================
# VIP MANAGEMENT
# =========================
@bot.message_handler(func=lambda m: m.text == "👑 VIP" and is_admin(m.from_user.id))
def vip_manage(m):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Add VIP", callback_data="add_vip"))
    kb.add(InlineKeyboardButton("Remove VIP", callback_data="remove_vip"))
    bot.send_message(m.from_user.id, "Manage VIP:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["add_vip", "remove_vip"])
def vip_action(c):
    action = "add" if c.data == "add_vip" else "remove"
    msg = bot.send_message(c.from_user.id, f"Send user ID to {action} VIP:")
    bot.register_next_step_handler(msg, lambda x: vip_process(x, action))

def vip_process(m, action):
    try:
        uid = int(m.text)
        user = User(uid)
        if action == "add":
            user.make_vip()
            bot.send_message(m.from_user.id, f"✅ VIP added!")
            try:
                bot.send_message(uid, "🎉 You are now VIP!")
            except:
                pass
        else:
            user.remove_vip()
            bot.send_message(m.from_user.id, f"✅ VIP removed!")
    except:
        bot.send_message(m.from_user.id, "Invalid ID!")

# =========================
# GIVE POINTS
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 Give Points" and is_admin(m.from_user.id))
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
@bot.message_handler(func=lambda m: m.text == "🎫 Generate" and is_admin(m.from_user.id))
def gen_codes(m):
    msg = bot.send_message(m.from_user.id, "Send: points count\nExample: 100 5")
    bot.register_next_step_handler(msg, gen_process)

def gen_process(m):
    try:
        pts, count = m.text.split()
        pts = int(pts)
        count = int(count)
        codes = codesys.generate(pts, count)
        bot.send_message(m.from_user.id, f"✅ Generated {count} codes:\n" + "\n".join(codes))
    except:
        bot.send_message(m.from_user.id, "Invalid! Use: points count")

# =========================
# STATS
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 Stats" and is_admin(m.from_user.id))
def stats(m):
    total = users_col.count_documents({})
    vip = users_col.count_documents({"vip": True})
    total_points = sum(u.get("points", 0) for u in users_col.find({}, {"points": 1}))
    
    msg = f"📊 **Stats**\n"
    msg += f"👥 Users: {total}\n"
    msg += f"💎 VIP: {vip}\n"
    msg += f"🆓 Free: {total - vip}\n"
    msg += f"💰 Points: {total_points}\n"
    msg += f"📁 Folders: {folders_col.count_documents({})}\n"
    msg += f"🎫 Codes: {codes_col.count_documents({})}"
    
    bot.send_message(m.from_user.id, msg, parse_mode="Markdown")

# =========================
# BROADCAST
# =========================
@bot.message_handler(func=lambda m: m.text == "📢 Broadcast" and is_admin(m.from_user.id))
def broadcast_start(m):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("All", callback_data="bc_all"))
    kb.add(InlineKeyboardButton("VIP", callback_data="bc_vip"))
    kb.add(InlineKeyboardButton("Free", callback_data="bc_free"))
    bot.send_message(m.from_user.id, "Target:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("bc_"))
def broadcast_target(c):
    target = c.data.split("_")[1]
    msg = bot.send_message(c.from_user.id, "Send message:")
    bot.register_next_step_handler(msg, lambda x: broadcast_send(x, target))

def broadcast_send(m, target):
    query = {}
    if target == "vip":
        query = {"vip": True}
    elif target == "free":
        query = {"vip": False}
    
    users = list(users_col.find(query, {"_id": 1}))
    sent = 0
    
    for user in users:
        try:
            if m.content_type == "text":
                bot.send_message(int(user["_id"]), m.text)
            elif m.content_type == "photo":
                bot.send_photo(int(user["_id"]), m.photo[-1].file_id, caption=m.caption)
            sent += 1
        except:
            pass
        if sent % 20 == 0:
            time.sleep(1)
    
    bot.send_message(m.from_user.id, f"✅ Sent to {sent} users!")

# =========================
# BUTTONS MANAGEMENT
# =========================
@bot.message_handler(func=lambda m: m.text == "🔘 Buttons" and is_admin(m.from_user.id))
def buttons_menu(m):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Add Button", callback_data="add_btn"))
    kb.add(InlineKeyboardButton("Remove Button", callback_data="remove_btn"))
    bot.send_message(m.from_user.id, "Manage buttons:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "add_btn")
def add_btn(c):
    msg = bot.send_message(c.from_user.id, "Send: type|text|data\nTypes: link, folder\nExample: link|Website|https://example.com")
    bot.register_next_step_handler(msg, add_btn_process)

def add_btn_process(m):
    try:
        btype, text, data = m.text.split("|")
        add_custom_button(text, btype, data)
        bot.send_message(m.from_user.id, "✅ Button added!")
    except:
        bot.send_message(m.from_user.id, "Invalid! Use: type|text|data")

@bot.callback_query_handler(func=lambda c: c.data == "remove_btn")
def remove_btn(c):
    btns = get_custom_buttons()
    if not btns:
        bot.send_message(c.from_user.id, "No buttons!")
        return
    kb = InlineKeyboardMarkup()
    for btn in btns:
        kb.add(InlineKeyboardButton(f"❌ {btn['text']}", callback_data=f"rmbtn|{btn['text']}"))
    bot.send_message(c.from_user.id, "Select to remove:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rmbtn|"))
def remove_btn_process(c):
    text = c.data.split("|")[1]
    remove_custom_button(text)
    bot.edit_message_text(f"✅ Removed: {text}", c.from_user.id, c.message.message_id)

# =========================
# CONTACT SETTINGS
# =========================
@bot.message_handler(func=lambda m: m.text == "📞 Contact" and is_admin(m.from_user.id))
def contact_settings(m):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Points Contact", callback_data="set_points"))
    kb.add(InlineKeyboardButton("VIP Contact", callback_data="set_vip"))
    bot.send_message(m.from_user.id, "Select:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["set_points", "set_vip"])
def set_contact_type(c):
    key = "contact_link" if c.data == "set_points" else "vip_contact"
    msg = bot.send_message(c.from_user.id, "Send @username or link (or 'none'):")
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
# FORCE JOIN MANAGEMENT
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ Force" and is_admin(m.from_user.id))
def force_menu(m):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Add Channel", callback_data="add_fc"))
    kb.add(InlineKeyboardButton("Remove Channel", callback_data="remove_fc"))
    bot.send_message(m.from_user.id, "Force Join:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "add_fc")
def add_fc(c):
    msg = bot.send_message(c.from_user.id, "Send @channel:")
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

@bot.callback_query_handler(func=lambda c: c.data == "remove_fc")
def remove_fc(c):
    cfg = get_config()
    chs = cfg.get("force_channels", [])
    if not chs:
        bot.send_message(c.from_user.id, "No channels!")
        return
    kb = InlineKeyboardMarkup()
    for ch in chs:
        kb.add(InlineKeyboardButton(f"❌ {ch}", callback_data=f"rmfc|{ch}"))
    bot.send_message(c.from_user.id, "Select:", reply_markup=kb)

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
# SETTINGS
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ Settings" and is_admin(m.from_user.id))
def settings_menu(m):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("VIP Message", callback_data="set_vip_msg"),
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
# FALLBACK
# =========================
@bot.message_handler(func=lambda m: True)
def fallback(m):
    if force_block(m.from_user.id):
        return
    
    known = ["📂 FREE METHODS", "💎 VIP METHODS", "📦 PREMIUM APPS", "⚡ SERVICES", 
             "💰 POINTS", "⭐ BUY VIP", "🎁 REFERRAL", "👤 ACCOUNT", "📚 MY METHODS", 
             "💎 GET POINTS", "🆔 CHAT ID", "🏆 REDEEM", "⚙️ ADMIN PANEL"]
    
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
            print(f"💾 MongoDB: Optimized with caching")
            print(f"📊 Cache: Users cached for 30 seconds")
            print(f"🧹 Auto-cleanup: Expired codes removed daily")
            print("=" * 40)
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    while True:
        time.sleep(1)
