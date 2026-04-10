# =========================
# ZEDOX BOT - WITH MONGODB
# Core Setup + MongoDB + User + Codes + Force Join
# =========================

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
import json, os, time, random, string, threading
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))

# MongoDB Connection
MONGODB_URI = os.environ.get("MONGODB_URI")  # Get from environment
if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable not set!")

# Connect to MongoDB
client = MongoClient(MONGODB_URI)
db = client["zedox_bot"]  # Database name

# Collections
users_collection = db["users"]
config_collection = db["config"]
content_collection = db["content"]
codes_collection = db["codes"]

# Create indexes for better performance
users_collection.create_index("uid", unique=True)
users_collection.create_index("ref")
users_collection.create_index("vip")
codes_collection.create_index("code", unique=True)
codes_collection.create_index("used")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# =========================
# INIT MONGODB DATA
# =========================
def init_mongodb():
    # Initialize config if not exists
    if config_collection.count_documents({}) == 0:
        default_config = {
            "force_channels": [],
            "vip_msg": "💎 Buy VIP to unlock this!",
            "welcome": "🔥 Welcome to ZEDOX BOT",
            "ref_reward": 5,
            "notify": True,
            "purchase_msg": "💰 Purchase VIP to access premium features!"
        }
        config_collection.insert_one(default_config)
    
    # Initialize content if not exists
    if content_collection.count_documents({}) == 0:
        default_content = {
            "free": {},
            "vip": {},
            "apps": {}
        }
        content_collection.insert_one(default_content)

init_mongodb()

def load_config():
    return config_collection.find_one({})

def save_config(config):
    config_collection.update_one({}, {"$set": config})

def load_content():
    doc = content_collection.find_one({})
    if doc:
        return doc
    return {"free": {}, "vip": {}, "apps": {}}

def save_content(content):
    content_collection.update_one({}, {"$set": content}, upsert=True)

# =========================
# USER CLASS (MONGODB VERSION)
# =========================
class User:
    def __init__(self, uid):
        self.uid = str(uid)
        
        # Try to find user
        user = users_collection.find_one({"uid": self.uid})
        
        if not user:
            # Create new user
            user_data = {
                "uid": self.uid,
                "points": 0,
                "vip": False,
                "ref": None,
                "purchased_methods": [],
                "used_codes": [],
                "username": None,
                "created_at": datetime.now(),
                "last_active": datetime.now()
            }
            users_collection.insert_one(user_data)
            self.data = user_data
        else:
            self.data = user
            # Update last active
            users_collection.update_one(
                {"uid": self.uid},
                {"$set": {"last_active": datetime.now()}}
            )

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

    def update_username(self, username):
        if username != self.data.get("username"):
            users_collection.update_one(
                {"uid": self.uid},
                {"$set": {"username": username}}
            )
            self.data["username"] = username

    def add_points(self, p):
        new_points = self.points() + p
        users_collection.update_one(
            {"uid": self.uid},
            {"$set": {"points": new_points}}
        )
        self.data["points"] = new_points

    def make_vip(self):
        users_collection.update_one(
            {"uid": self.uid},
            {"$set": {"vip": True}}
        )
        self.data["vip"] = True
    
    def remove_vip(self):
        users_collection.update_one(
            {"uid": self.uid},
            {"$set": {"vip": False}}
        )
        self.data["vip"] = False
    
    def purchase_method(self, method_name, price):
        if self.points() >= price:
            self.add_points(-price)
            purchased = self.purchased_methods()
            if method_name not in purchased:
                purchased.append(method_name)
                users_collection.update_one(
                    {"uid": self.uid},
                    {"$set": {"purchased_methods": purchased}}
                )
                self.data["purchased_methods"] = purchased
            return True
        return False
    
    def can_access_method(self, method_name):
        return self.is_vip() or method_name in self.purchased_methods()
    
    def add_used_code(self, code):
        used = self.used_codes()
        if code not in used:
            used.append(code)
            users_collection.update_one(
                {"uid": self.uid},
                {"$set": {"used_codes": used}}
            )
            self.data["used_codes"] = used
            return True
        return False
    
    def has_used_code(self, code):
        return code in self.used_codes()

# =========================
# CODES SYSTEM (MONGODB VERSION)
# =========================
class Codes:
    def __init__(self):
        pass

    def generate(self, pts, count):
        res = []
        for _ in range(count):
            code = "ZEDOX" + ''.join(random.choices(string.ascii_uppercase+string.digits, k=6))
            # Store code with points and mark as unused
            code_data = {
                "code": code,
                "points": pts,
                "used": False,
                "used_by": None,
                "used_at": None,
                "created_at": datetime.now()
            }
            try:
                codes_collection.insert_one(code_data)
                res.append(code)
            except DuplicateKeyError:
                # If duplicate, try again with new code
                continue
        return res

    def redeem(self, code, user):
        # Find the code
        code_data = codes_collection.find_one({"code": code})
        
        if not code_data:
            return False, 0, "invalid"
        
        # Check if code has already been used
        if code_data.get("used", False):
            return False, 0, "already_used"
        
        # Check if this user has already used this specific code
        if user.has_used_code(code):
            return False, 0, "already_used_by_user"
        
        # Redeem the code
        pts = code_data["points"]
        user.add_points(pts)
        
        # Mark code as used
        codes_collection.update_one(
            {"code": code},
            {
                "$set": {
                    "used": True,
                    "used_by": user.uid,
                    "used_at": datetime.now()
                }
            }
        )
        
        # Add code to user's used codes list
        user.add_used_code(code)
        
        return True, pts, "success"

    def get_code_info(self, code):
        return codes_collection.find_one({"code": code})

    def get_all_codes(self):
        return list(codes_collection.find({}))

    def delete_code(self, code):
        result = codes_collection.delete_one({"code": code})
        return result.deleted_count > 0

    def get_stats(self):
        total = codes_collection.count_documents({})
        used = codes_collection.count_documents({"used": True})
        unused = total - used
        return total, used, unused

codesys = Codes()

# =========================
# FORCE JOIN (STRICT)
# =========================
def force_block(uid):
    cfg = load_config()

    for ch in cfg["force_channels"]:
        try:
            m = bot.get_chat_member(ch, uid)
            if m.status in ["left","kicked"]:
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(f"Join {ch}", url=f"https://t.me/{ch.replace('@','')}"))
                kb.add(InlineKeyboardButton("🔄 I Joined", callback_data="recheck"))
                bot.send_message(uid, "🚫 Join all channels first!", reply_markup=kb)
                return True
        except:
            return True
    return False

# =========================
# FILE SYSTEM (MONGODB VERSION)
# =========================
class FS:
    def add(self, cat, name, files, price):
        content = load_content()
        content[cat][name] = {"files": files, "price": price}
        save_content(content)

    def get(self, cat):
        content = load_content()
        return content.get(cat, {})

    def delete(self, cat, name):
        content = load_content()
        if name in content[cat]:
            del content[cat][name]
            save_content(content)
            return True
        return False

    def edit(self, cat, name, price):
        content = load_content()
        if name in content[cat]:
            content[cat][name]["price"] = price
            save_content(content)
            return True
        return False

fs = FS()

def get_kb(cat, page=0):
    data = list(fs.get(cat).items())
    per = 10
    start = page*per
    items = data[start:start+per]

    kb = InlineKeyboardMarkup()
    for name, d in items:
        price = d["price"]
        txt = f"{name} [{price} pts]" if price>0 else name
        kb.add(InlineKeyboardButton(txt, callback_data=f"open|{cat}|{name}"))

    nav=[]
    if page>0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"page|{cat}|{page-1}"))
    if start+per < len(data):
        nav.append(InlineKeyboardButton("➡️", callback_data=f"page|{cat}|{page+1}"))
    if nav: kb.row(*nav)

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

    kb.row("✏️ Edit Folder Price", "🗑 Delete Folder")

    kb.row("👑 Add VIP User", "👑 Remove VIP User")
    kb.row("🏆 Generate Codes", "📊 View Codes")
    kb.row("📊 User Statistics", "📤 Broadcast")

    kb.row("⭐ Set VIP Message", "💰 Set Purchase Message")
    kb.row("🏠 Set Welcome")

    kb.row("➕ Add Force Join", "➖ Remove Force Join")

    kb.row("❌ Exit Admin")
    return kb

# =========================
# USER STATISTICS (MONGODB VERSION)
# =========================
def get_user_statistics():
    total_users = users_collection.count_documents({})
    vip_users = users_collection.count_documents({"vip": True})
    free_users = total_users - vip_users
    
    # Aggregation pipeline for points
    points_pipeline = [
        {"$group": {"_id": None, "total": {"$sum": "$points"}, "avg": {"$avg": "$points"}}}
    ]
    points_stats = list(users_collection.aggregate(points_pipeline))
    total_points = points_stats[0]["total"] if points_stats else 0
    avg_points = int(points_stats[0]["avg"]) if points_stats else 0
    
    # Total purchased methods
    purchased_pipeline = [
        {"$unwind": "$purchased_methods"},
        {"$group": {"_id": None, "count": {"$sum": 1}}}
    ]
    purchased_stats = list(users_collection.aggregate(purchased_pipeline))
    total_purchased = purchased_stats[0]["count"] if purchased_stats else 0
    
    # Total codes redeemed
    codes_pipeline = [
        {"$unwind": "$used_codes"},
        {"$group": {"_id": None, "count": {"$sum": 1}}}
    ]
    codes_stats = list(users_collection.aggregate(codes_pipeline))
    total_codes_redeemed = codes_stats[0]["count"] if codes_stats else 0
    
    # Top users by points
    top_users = list(users_collection.find({}, {"uid": 1, "username": 1, "points": 1})
                     .sort("points", -1).limit(5))
    
    return {
        "total_users": total_users,
        "vip_users": vip_users,
        "free_users": free_users,
        "total_points": total_points,
        "avg_points": avg_points,
        "total_purchased": total_purchased,
        "total_codes_redeemed": total_codes_redeemed,
        "top_users": top_users
    }

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
    
    # Update username
    if m.from_user.username:
        user.update_username(m.from_user.username)

    if len(args) > 1:
        ref = args[1]
        # Check if ref is valid and user hasn't been referred
        if ref != str(uid):
            referrer = users_collection.find_one({"uid": ref})
            if referrer and not user.data.get("ref"):
                # Add points to referrer
                ref_reward = load_config().get("ref_reward", 5)
                User(ref).add_points(ref_reward)
                # Set referrer for new user
                users_collection.update_one(
                    {"uid": user.uid},
                    {"$set": {"ref": ref}}
                )
                user.data["ref"] = ref

    if force_block(uid):
        return

    cfg = load_config()
    bot.send_message(uid, cfg.get("welcome", "Welcome!"), reply_markup=main_menu(uid))

# =========================
# USER COMMANDS
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 POINTS")
def points_cmd(m):
    uid = m.from_user.id
    user = User(uid)
    
    if force_block(uid):
        return
    
    bot.send_message(uid, f"💰 Your Points: **{user.points()}**\n\n🎁 Earn more points by:\n• Using referral link\n• Redeeming codes\n• Completing tasks", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎁 REFERRAL")
def referral_cmd(m):
    uid = m.from_user.id
    user = User(uid)
    
    if force_block(uid):
        return
    
    link = f"https://t.me/{bot.get_me().username}?start={uid}"
    ref_count = users_collection.count_documents({"ref": str(uid)})
    bot.send_message(uid, f"🎁 **Your Referral Link**\n\n{link}\n\n✨ For each friend who joins, you get **{load_config().get('ref_reward', 5)} points**!\n\n📊 Total referrals: **{ref_count}**", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "👤 ACCOUNT")
def account_cmd(m):
    uid = m.from_user.id
    user = User(uid)
    
    if force_block(uid):
        return
    
    status = "💎 VIP Member" if user.is_vip() else "🆓 Free User"
    purchased_count = len(user.purchased_methods())
    used_codes_count = len(user.used_codes())
    
    account_text = f"**👤 Account Info**\n\n"
    account_text += f"Status: {status}\n"
    account_text += f"Points: **{user.points()}**\n"
    account_text += f"Purchased Methods: **{purchased_count}**\n"
    account_text += f"Redeemed Codes: **{used_codes_count}**\n"
    
    if not user.is_vip():
        account_text += f"\n💡 Use points to buy VIP methods individually!"
    
    bot.send_message(uid, account_text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🆔 CHAT ID")
def chatid_cmd(m):
    uid = m.from_user.id
    
    if force_block(uid):
        return
    
    bot.send_message(uid, f"🆔 Your Chat ID: `{uid}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🏆 REDEEM")
def redeem_cmd(m):
    uid = m.from_user.id
    
    if force_block(uid):
        return
    
    msg = bot.send_message(uid, "🎫 Enter your redeem code:\n\n*Each code can only be used once!*", parse_mode="Markdown")
    bot.register_next_step_handler(msg, redeem_code)

def redeem_code(m):
    uid = m.from_user.id
    user = User(uid)
    code = m.text.strip().upper()

    success, pts, reason = codesys.redeem(code, user)

    if success:
        bot.send_message(uid, f"✅ **Success!**\n\n➕ +{pts} points\n💰 Total Points: **{user.points()}**\n\n✨ Code redeemed successfully!", parse_mode="Markdown")
    else:
        if reason == "invalid":
            bot.send_message(uid, "❌ **Invalid Code**\n\nPlease check your code and try again.\n\n*Each code can only be used once!*", parse_mode="Markdown")
        elif reason == "already_used":
            bot.send_message(uid, "❌ **Code Already Used**\n\nThis code has already been redeemed by another user.\n\n*Each code can only be used once!*", parse_mode="Markdown")
        elif reason == "already_used_by_user":
            bot.send_message(uid, "❌ **Code Already Used**\n\nYou have already redeemed this code.\n\n*Each code can only be used once!*", parse_mode="Markdown")

# =========================
# SHOW FOLDERS
# =========================
@bot.message_handler(func=lambda m: m.text in [
    "📂 FREE METHODS",
    "💎 VIP METHODS",
    "📦 PREMIUM APPS"
])
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
    
    if cat is None:
        bot.send_message(uid, "❌ Invalid category")
        return

    folders = fs.get(cat)
    
    if not folders:
        bot.send_message(uid, f"📂 {m.text}\n\nNo folders available in this category yet!")
        return

    bot.send_message(uid, f"📂 {m.text}\n\nSelect a folder to view content:", reply_markup=get_kb(cat, 0))

# =========================
# OPEN FOLDER
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("open|"))
def open_folder(c):
    uid = c.from_user.id
    user = User(uid)

    try:
        _, cat, name = c.data.split("|")
    except:
        bot.answer_callback_query(c.id, "Invalid folder data")
        return
        
    folder = fs.get(cat).get(name)

    if not folder:
        bot.answer_callback_query(c.id, "❌ Folder not found")
        return

    # Check access for VIP category
    if cat == "vip":
        if user.is_vip():
            # VIP user gets free access
            pass
        elif user.can_access_method(name):
            # User already purchased this method
            pass
        else:
            # Show options to get VIP or get points
            price = folder.get("price", 0)
            if price > 0:
                kb = InlineKeyboardMarkup(row_width=2)
                kb.add(
                    InlineKeyboardButton(f"💰 Buy for {price} pts", callback_data=f"buy|{cat}|{name}|{price}"),
                    InlineKeyboardButton("⭐ GET VIP", callback_data="get_vip"),
                    InlineKeyboardButton("💎 GET POINTS", callback_data="get_points")
                )
                kb.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_buy"))
                bot.answer_callback_query(c.id, "🔒 This is a VIP method")
                bot.send_message(uid, f"🔒 **VIP Method: {name}**\n\nPrice: **{price} points**\nYour points: **{user.points()}**\n\nChoose an option:", reply_markup=kb, parse_mode="Markdown")
            else:
                # Show options without price
                kb = InlineKeyboardMarkup(row_width=2)
                kb.add(
                    InlineKeyboardButton("⭐ GET VIP", callback_data="get_vip"),
                    InlineKeyboardButton("💎 GET POINTS", callback_data="get_points")
                )
                kb.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_buy"))
                bot.answer_callback_query(c.id, "🔒 This is a VIP method")
                bot.send_message(uid, f"🔒 **VIP Method: {name}**\n\nThis is a VIP method.\n\nChoose an option to access it:", reply_markup=kb, parse_mode="Markdown")
            return

    # Handle points for non-VIP free content
    price = folder.get("price", 0)
    if cat != "vip" and price > 0 and not user.is_vip():
        if user.points() < price:
            bot.answer_callback_query(c.id, f"❌ Need {price} points! You have {user.points()}", show_alert=True)
            return
        user.add_points(-price)
        bot.answer_callback_query(c.id, f"✅ {price} points deducted!")

    # Send files
    bot.answer_callback_query(c.id, "📤 Sending files...")
    count = 0
    for f in folder["files"]:
        try:
            bot.copy_message(uid, f["chat"], f["msg"])
            count += 1
            time.sleep(0.3)
        except Exception as e:
            print(f"Error sending file: {e}")
            continue

    if load_config().get("notify", True):
        if count > 0:
            bot.send_message(uid, f"✅ Sent {count} file(s) successfully!")
        else:
            bot.send_message(uid, "❌ Failed to send files. Please try again later.")

# =========================
# BUY METHOD HANDLER
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
        bot.answer_callback_query(c.id, "✅ You are VIP! You have free access to all methods!", show_alert=True)
        open_folder(c)
        return
    
    if user.can_access_method(method_name):
        bot.answer_callback_query(c.id, "✅ You already own this method!", show_alert=True)
        open_folder(c)
        return
    
    if user.points() < price:
        bot.answer_callback_query(c.id, f"❌ You need {price} points! You have {user.points()}", show_alert=True)
        return
    
    # Purchase the method
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

@bot.callback_query_handler(func=lambda c: c.data == "get_vip")
def get_vip_callback(c):
    uid = c.from_user.id
    user = User(uid)
    
    if force_block(uid):
        return
    
    if user.is_vip():
        bot.answer_callback_query(c.id, "✅ You are already a VIP member!", show_alert=True)
        return
    
    cfg = load_config()
    vip_msg = cfg.get("vip_msg", "💎 Buy VIP to unlock this!")
    
    bot.edit_message_text(
        f"💎 **VIP Membership**\n\n{vip_msg}\n\nContact admin to get VIP access.",
        uid,
        c.message.message_id,
        parse_mode="Markdown"
    )
    bot.answer_callback_query(c.id, "🔒 VIP Access Required")

@bot.callback_query_handler(func=lambda c: c.data == "get_points")
def get_points_callback(c):
    uid = c.from_user.id
    
    if force_block(uid):
        return
    
    cfg = load_config()
    purchase_msg = cfg.get("purchase_msg", "💰 Purchase VIP to access premium features!")
    
    bot.edit_message_text(
        f"💰 **Get Points**\n\n{purchase_msg}\n\n✨ You can earn points by:\n• Using referral link\n• Redeeming codes\n• Completing tasks\n\nContact admin to purchase points directly.",
        uid,
        c.message.message_id,
        parse_mode="Markdown"
    )
    bot.answer_callback_query(c.id, "💰 Points Info")

@bot.callback_query_handler(func=lambda c: c.data == "cancel_buy")
def cancel_buy(c):
    bot.edit_message_text("❌ Cancelled", c.from_user.id, c.message.message_id)
    bot.answer_callback_query(c.id)

# =========================
# MY METHODS
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
        bot.send_message(uid, "📚 **Your Purchased Methods**\n\nYou haven't purchased any VIP methods yet.\n\nUse points to buy VIP methods from the 💎 VIP METHODS section!", parse_mode="Markdown")
        return
    
    vip_methods = fs.get("vip")
    purchased_list = []
    for method in purchased:
        if method in vip_methods:
            purchased_list.append(f"✅ {method}")
    
    if purchased_list:
        methods_text = "📚 **Your Purchased Methods**\n\n" + "\n".join(purchased_list)
        methods_text += "\n\n💡 Tip: These methods are permanently unlocked for you!"
        bot.send_message(uid, methods_text, parse_mode="Markdown")
    else:
        bot.send_message(uid, "📚 **Your Purchased Methods**\n\nNo purchased methods found.", parse_mode="Markdown")

# =========================
# GET VIP/POINTS BUTTONS
# =========================
@bot.message_handler(func=lambda m: m.text == "⭐ GET VIP")
def get_vip_button(m):
    uid = m.from_user.id
    user = User(uid)
    
    if force_block(uid):
        return
    
    if user.is_vip():
        bot.send_message(uid, "✅ **You are already a VIP member!**\n\n✨ Enjoy exclusive VIP content and benefits!", parse_mode="Markdown")
        return
    
    cfg = load_config()
    vip_msg = cfg.get("vip_msg", "💎 Buy VIP to unlock this!")
    
    message = f"💎 **VIP Membership**\n\n{vip_msg}\n\nContact admin to get VIP access."
    bot.send_message(uid, message, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "💎 GET POINTS")
def get_points_button(m):
    uid = m.from_user.id
    
    if force_block(uid):
        return
    
    cfg = load_config()
    purchase_msg = cfg.get("purchase_msg", "💰 Purchase VIP to access premium features!")
    
    message = f"💰 **Get Points**\n\n{purchase_msg}\n\n✨ You can earn points by:\n• Using referral link\n• Redeeming codes\n• Completing tasks\n\nContact admin to purchase points directly."
    bot.send_message(uid, message, parse_mode="Markdown")

# =========================
# FORCE JOIN RECHECK
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "recheck")
def recheck(c):
    uid = c.from_user.id

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

        bot.send_message(uid, "🎉 Welcome! Use the menu below to get started.", reply_markup=main_menu(uid))
    else:
        bot.answer_callback_query(c.id, "❌ Please join all required channels first", show_alert=True)

# =========================
# PAGINATION HANDLER
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("page|"))
def page_handler(c):
    _, cat, page = c.data.split("|")
    
    try:
        bot.edit_message_reply_markup(
            c.from_user.id,
            c.message.message_id,
            reply_markup=get_kb(cat, int(page))
        )
    except Exception as e:
        bot.answer_callback_query(c.id, "Error updating page")

# =========================
# FALLBACK HANDLER
# =========================
@bot.message_handler(func=lambda m: True)
def fallback(m):
    uid = m.from_user.id

    if force_block(uid):
        return

    known = [
        "📂 FREE METHODS","💎 VIP METHODS",
        "📦 PREMIUM APPS", "📚 MY METHODS",
        "💰 POINTS","⭐ GET VIP","💎 GET POINTS",
        "🎁 REFERRAL","👤 ACCOUNT",
        "🆔 CHAT ID","🏆 REDEEM",
        "⚙️ ADMIN PANEL"
    ]

    if m.text and m.text not in known:
        bot.send_message(uid, "❌ Please use the menu buttons only", reply_markup=main_menu(uid))

# =========================
# RUN BOT
# =========================
if __name__ == "__main__":
    print("🚀 ZEDOX BOT RUNNING WITH MONGODB...")
    print(f"✅ Bot Username: @{bot.get_me().username}")
    print(f"✅ Admin ID: {ADMIN_ID}")
    print(f"✅ MongoDB Connected: {MONGODB_URI.split('@')[-1] if '@' in MONGODB_URI else 'Connected'}")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(5)
