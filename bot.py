# =========================
# ZEDOX BOT - WITH MONGODB (UPDATED)
# Core Setup + MongoDB + User + Codes + Force Join
# =========================

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
import os, time, random, string, threading
from pymongo import MongoClient

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))

# =========================
# 🌐 MONGODB SETUP
# =========================
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable not set!")

client = MongoClient(MONGO_URI)
db = client["zedox"]  # Database name

# Collections
users_col = db["users"]
folders_col = db["folders"]
codes_col = db["codes"]
config_col = db["config"]

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# =========================
# ⚙️ CONFIG SYSTEM
# =========================
def get_config():
    cfg = config_col.find_one({"_id": "config"})
    if not cfg:
        cfg = {
            "_id": "config",
            "force_channels": [],
            "vip_msg": "💎 Buy VIP to unlock this!",
            "welcome": "🔥 Welcome to ZEDOX BOT",
            "ref_reward": 5,
            "notify": True,
            "purchase_msg": "💰 Purchase VIP to access premium features!"
        }
        config_col.insert_one(cfg)
    return cfg

def set_config(key, value):
    config_col.update_one({"_id": "config"}, {"$set": {key: value}}, upsert=True)

# =========================
# 👤 USER SYSTEM (MONGODB VERSION)
# =========================
class User:
    def __init__(self, uid):
        self.uid = str(uid)
        data = users_col.find_one({"_id": self.uid})

        if not data:
            data = {
                "_id": self.uid,
                "points": 0,
                "vip": False,
                "ref": None,
                "refs": 0,
                "purchased_methods": [],
                "used_codes": [],
                "username": None,
                "created_at": time.time()
            }
            users_col.insert_one(data)

        self.data = data

    def save(self):
        users_col.update_one({"_id": self.uid}, {"$set": self.data})

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
            self.data["username"] = username
            self.save()

    def add_points(self, p):
        self.data["points"] += p
        self.save()

    def set_points(self, p):
        self.data["points"] = p
        self.save()

    def make_vip(self):
        self.data["vip"] = True
        self.save()
    
    def remove_vip(self):
        self.data["vip"] = False
        self.save()
    
    def purchase_method(self, method_name, price):
        if self.points() >= price:
            self.add_points(-price)
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

# =========================
# 📦 CONTENT SYSTEM (MONGODB VERSION)
# =========================
class FS:
    def add(self, cat, name, files, price):
        folders_col.insert_one({
            "cat": cat,
            "name": name,
            "files": files,
            "price": price
        })

    def get(self, cat):
        return list(folders_col.find({"cat": cat}))

    def get_one(self, cat, name):
        return folders_col.find_one({"cat": cat, "name": name})

    def delete(self, cat, name):
        folders_col.delete_one({"cat": cat, "name": name})

    def edit_price(self, cat, name, price):
        folders_col.update_one({"cat": cat, "name": name}, {"$set": {"price": price}})

    def edit_name(self, cat, old, new):
        folders_col.update_one({"cat": cat, "name": old}, {"$set": {"name": new}})

fs = FS()

# =========================
# 🏆 CODES SYSTEM (MONGODB VERSION)
# =========================
class Codes:
    def generate(self, pts, count):
        res = []
        for _ in range(count):
            code = "ZEDOX" + ''.join(random.choices(string.ascii_uppercase+string.digits, k=6))
            codes_col.insert_one({
                "_id": code,
                "points": pts,
                "used": False,
                "used_by": None,
                "used_at": None
            })
            res.append(code)
        return res

    def redeem(self, code, user):
        code_data = codes_col.find_one({"_id": code})
        
        if not code_data:
            return False, 0, "invalid"
        
        if code_data.get("used", False):
            return False, 0, "already_used"
        
        if user.has_used_code(code):
            return False, 0, "already_used_by_user"
        
        pts = code_data["points"]
        user.add_points(pts)
        
        codes_col.update_one(
            {"_id": code},
            {
                "$set": {
                    "used": True,
                    "used_by": user.uid,
                    "used_at": time.time()
                }
            }
        )
        
        user.add_used_code(code)
        return True, pts, "success"

    def get_all_codes(self):
        return list(codes_col.find({}))

    def delete_code(self, code):
        result = codes_col.delete_one({"_id": code})
        return result.deleted_count > 0

codesys = Codes()

# =========================
# 🚫 FORCE JOIN SYSTEM
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

# =========================
# 📱 MAIN MENU
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
# 🚀 START + REFERRAL SYSTEM
# =========================
@bot.message_handler(commands=["start"])
def start_cmd(m):
    uid = m.from_user.id
    args = m.text.split()

    user = User(uid)
    
    # Update username
    if m.from_user.username:
        user.update_username(m.from_user.username)

    # Referral system
    if len(args) > 1:
        ref_id = args[1]
        
        if ref_id != str(uid):
            ref_user_data = users_col.find_one({"_id": ref_id})
            
            if ref_user_data and not user.data.get("ref"):
                ref_user = User(ref_id)
                reward = get_config().get("ref_reward", 5)
                ref_user.add_points(reward)
                ref_user.add_ref()
                
                user.data["ref"] = ref_id
                user.save()

    if force_block(uid):
        return

    cfg = get_config()
    bot.send_message(uid, cfg.get("welcome", "Welcome!"), reply_markup=main_menu(uid))

# =========================
# 📂 SHOW FOLDERS
# =========================
def get_folders_kb(cat):
    data = fs.get(cat)
    
    kb = InlineKeyboardMarkup()
    for item in data:
        name = item["name"]
        price = item.get("price", 0)
        text = f"{name} [{price} pts]" if price > 0 else name
        kb.add(InlineKeyboardButton(text, callback_data=f"open|{cat}|{name}"))
    
    return kb

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

    data = fs.get(cat)
    
    if not data:
        bot.send_message(uid, f"📂 {m.text}\n\nNo folders available in this category yet!")
        return

    bot.send_message(uid, f"📂 {m.text}\n\nSelect a folder to view content:", reply_markup=get_folders_kb(cat))

# =========================
# 📂 OPEN FOLDER
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
        
    folder = fs.get_one(cat, name)

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

    if get_config().get("notify", True):
        if count > 0:
            bot.send_message(uid, f"✅ Sent {count} file(s) successfully!")
        else:
            bot.send_message(uid, "❌ Failed to send files. Please try again later.")
    
    # Save purchased method
    if cat == "vip" and not user.is_vip():
        user.add_purchase(name)

# =========================
# 💰 BUY METHOD HANDLER
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

# =========================
# ⭐ GET VIP/POINTS CALLBACKS
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "get_vip")
def get_vip_callback(c):
    uid = c.from_user.id
    user = User(uid)
    
    if force_block(uid):
        return
    
    if user.is_vip():
        bot.answer_callback_query(c.id, "✅ You are already a VIP member!", show_alert=True)
        return
    
    cfg = get_config()
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
    
    cfg = get_config()
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
        bot.send_message(uid, "📚 **Your Purchased Methods**\n\nYou haven't purchased any VIP methods yet.\n\nUse points to buy VIP methods from the 💎 VIP METHODS section!", parse_mode="Markdown")
        return
    
    # Create inline keyboard for purchased methods
    kb = InlineKeyboardMarkup()
    vip_methods = {item["name"]: item for item in fs.get("vip")}
    
    for method in purchased:
        if method in vip_methods:
            kb.add(InlineKeyboardButton(method, callback_data=f"open|vip|{method}"))
    
    if kb.keyboard:
        bot.send_message(uid, "📚 **Your Purchased Methods**\n\nClick any method to open it:", reply_markup=kb, parse_mode="Markdown")
    else:
        bot.send_message(uid, "📚 **Your Purchased Methods**\n\nNo purchased methods found.", parse_mode="Markdown")

# =========================
# 💰 USER COMMANDS
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
    ref_count = user.data.get("refs", 0)
    bot.send_message(uid, f"🎁 **Your Referral Link**\n\n{link}\n\n✨ For each friend who joins, you get **{get_config().get('ref_reward', 5)} points**!\n\n📊 Total referrals: **{ref_count}**", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "👤 ACCOUNT")
def account_cmd(m):
    uid = m.from_user.id
    user = User(uid)
    
    if force_block(uid):
        return
    
    status = "💎 VIP Member" if user.is_vip() else "🆓 Free User"
    purchased_count = len(user.purchased_methods())
    used_codes_count = len(user.used_codes())
    ref_count = user.data.get("refs", 0)
    
    account_text = f"**👤 Account Info**\n\n"
    account_text += f"Status: {status}\n"
    account_text += f"Points: **{user.points()}**\n"
    account_text += f"Referrals: **{ref_count}**\n"
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

@bot.message_handler(func=lambda m: m.text == "⭐ GET VIP")
def get_vip_button(m):
    uid = m.from_user.id
    user = User(uid)
    
    if force_block(uid):
        return
    
    if user.is_vip():
        bot.send_message(uid, "✅ **You are already a VIP member!**\n\n✨ Enjoy exclusive VIP content and benefits!", parse_mode="Markdown")
        return
    
    cfg = get_config()
    vip_msg = cfg.get("vip_msg", "💎 Buy VIP to unlock this!")
    
    message = f"💎 **VIP Membership**\n\n{vip_msg}\n\nContact admin to get VIP access."
    bot.send_message(uid, message, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "💎 GET POINTS")
def get_points_button(m):
    uid = m.from_user.id
    
    if force_block(uid):
        return
    
    cfg = get_config()
    purchase_msg = cfg.get("purchase_msg", "💰 Purchase VIP to access premium features!")
    
    message = f"💰 **Get Points**\n\n{purchase_msg}\n\n✨ You can earn points by:\n• Using referral link\n• Redeeming codes\n• Completing tasks\n\nContact admin to purchase points directly."
    bot.send_message(uid, message, parse_mode="Markdown")

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
# 🔄 FORCE JOIN RECHECK
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
# ⚙️ ADMIN PANEL - UPLOAD SYSTEM
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

@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def admin_panel(m):
    bot.send_message(m.from_user.id, "⚙️ Admin Panel", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "❌ Exit Admin" and is_admin(m.from_user.id))
def exit_admin(m):
    bot.send_message(m.from_user.id, "Exited Admin", reply_markup=main_menu(m.from_user.id))

# =========================
# 📤 UPLOAD SYSTEM
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

    if m.content_type in ["document","photo","video"]:
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
# 🗑 DELETE SYSTEM
# =========================
@bot.message_handler(func=lambda m: m.text == "🗑 Delete Folder" and is_admin(m.from_user.id))
def del_start(m):
    kb = InlineKeyboardMarkup()
    for c in ["free","vip","apps"]:
        kb.add(InlineKeyboardButton(c, callback_data=f"del|{c}"))
    bot.send_message(m.from_user.id, "Select category", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("del|"))
def del_list(c):
    cat = c.data.split("|")[1]
    data = fs.get(cat)

    kb = InlineKeyboardMarkup()
    for item in data:
        name = item["name"]
        kb.add(InlineKeyboardButton(name, callback_data=f"delf|{cat}|{name}"))

    bot.edit_message_text("Select folder", c.from_user.id, c.message.id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("delf|"))
def del_final(c):
    _, cat, name = c.data.split("|")
    fs.delete(cat, name)
    bot.answer_callback_query(c.id, "Deleted")
    bot.edit_message_text("Done", c.from_user.id, c.message.id)

# =========================
# ✏️ EDIT PRICE
# =========================
@bot.message_handler(func=lambda m: m.text == "✏️ Edit Folder Price" and is_admin(m.from_user.id))
def edit_start(m):
    msg = bot.send_message(m.from_user.id, "Category (free/vip/apps):")
    bot.register_next_step_handler(msg, edit2)

def edit2(m):
    cat = m.text.strip().lower()
    if cat not in ["free", "vip", "apps"]:
        bot.send_message(m.from_user.id, "Invalid category! Use: free, vip, apps")
        return
    msg = bot.send_message(m.from_user.id, "Folder name:")
    bot.register_next_step_handler(msg, lambda m2: edit3(m2, cat))

def edit3(m, cat):
    name = m.text
    msg = bot.send_message(m.from_user.id, "New price:")
    bot.register_next_step_handler(msg, lambda m2: edit4(m2, cat, name))

def edit4(m, cat, name):
    try:
        fs.edit_price(cat, name, int(m.text))
        bot.send_message(m.from_user.id, "✅ Price updated")
    except:
        bot.send_message(m.from_user.id, "❌ Error updating price")

# =========================
# 👑 VIP USER MANAGEMENT
# =========================
@bot.message_handler(func=lambda m: m.text == "👑 Add VIP User" and is_admin(m.from_user.id))
def add_vip_start(m):
    msg = bot.send_message(m.from_user.id, "📝 Send user ID or @username to add VIP:")
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
            bot.send_message(m.from_user.id, f"❌ Could not find user with username {user_input}")
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
            bot.send_message(m.from_user.id, f"⚠️ User `{user_id}` is already VIP!")
            return
        
        user.make_vip()
        bot.send_message(m.from_user.id, f"✅ User `{user_id}` has been upgraded to VIP!")
        
        try:
            bot.send_message(user_id, "🎉 **Congratulations!**\n\nYou have been upgraded to **VIP** by the admin!\n\n✨ Enjoy exclusive VIP content and benefits!", parse_mode="Markdown")
        except:
            bot.send_message(m.from_user.id, f"⚠️ Could not notify user `{user_id}`.")
    
    except Exception as e:
        bot.send_message(m.from_user.id, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda m: m.text == "👑 Remove VIP User" and is_admin(m.from_user.id))
def remove_vip_start(m):
    msg = bot.send_message(m.from_user.id, "📝 Send user ID or @username to remove VIP:")
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
            bot.send_message(m.from_user.id, f"❌ Could not find user with username {user_input}")
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
            bot.send_message(m.from_user.id, f"⚠️ User `{user_id}` is not a VIP member!")
            return
        
        user.remove_vip()
        bot.send_message(m.from_user.id, f"✅ VIP status removed from user `{user_id}`!")
        
        try:
            bot.send_message(user_id, "⚠️ **VIP Status Removed**\n\nYour VIP membership has been removed by the admin.", parse_mode="Markdown")
        except:
            bot.send_message(m.from_user.id, f"⚠️ Could not notify user `{user_id}`.")
    
    except Exception as e:
        bot.send_message(m.from_user.id, f"❌ Error: {str(e)}")

# =========================
# 🏆 GENERATE CODES
# =========================
@bot.message_handler(func=lambda m: m.text == "🏆 Generate Codes" and is_admin(m.from_user.id))
def code1(m):
    msg = bot.send_message(m.from_user.id, "Points per code:")
    bot.register_next_step_handler(msg, code2)

def code2(m):
    pts = int(m.text)
    msg = bot.send_message(m.from_user.id, "How many codes?")
    bot.register_next_step_handler(msg, lambda m2: code3(m2, pts))

def code3(m, pts):
    count = int(m.text)
    res = codesys.generate(pts, count)
    codes_list = "\n".join(res)
    bot.send_message(m.from_user.id, f"✅ **Generated {count} codes!**\n\nEach code can be used **ONCE** by any user.\n\n```\n{codes_list}\n```", parse_mode="Markdown")

# =========================
# 📊 VIEW CODES
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
        code = code_data["_id"]
        if code_data.get("used", False):
            used_by = code_data.get("used_by", "Unknown")
            used_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(code_data.get("used_at", 0)))
            used_codes.append(f"❌ {code} - {code_data['points']} pts - Used by: {used_by} at {used_at}")
        else:
            unused_codes.append(f"✅ {code} - {code_data['points']} pts")
    
    message = "📊 **Code Statistics**\n\n"
    message += f"**Total Codes:** {len(codes)}\n"
    message += f"**Used:** {len(used_codes)}\n"
    message += f"**Unused:** {len(unused_codes)}\n\n"
    
    if unused_codes:
        message += "**Unused Codes:**\n" + "\n".join(unused_codes[:20])
        if len(unused_codes) > 20:
            message += f"\n... and {len(unused_codes) - 20} more"
    
    if used_codes:
        message += "\n\n**Recently Used Codes:**\n" + "\n".join(used_codes[:10])
        if len(used_codes) > 10:
            message += f"\n... and {len(used_codes) - 10} more"
    
    if len(message) > 4096:
        bot.send_message(m.from_user.id, "📊 Code Statistics")
        bot.send_message(m.from_user.id, f"Total: {len(codes)} | Used: {len(used_codes)} | Unused: {len(unused_codes)}")
        
        if unused_codes:
            batch = []
            for code in unused_codes:
                batch.append(code)
                if len("\n".join(batch)) > 3500:
                    bot.send_message(m.from_user.id, "✅ **Unused Codes:**\n" + "\n".join(batch))
                    batch = []
            if batch:
                bot.send_message(m.from_user.id, "✅ **Unused Codes:**\n" + "\n".join(batch))
    else:
        bot.send_message(m.from_user.id, message, parse_mode="Markdown")

# =========================
# 📊 USER STATISTICS
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 User Statistics" and is_admin(m.from_user.id))
def user_statistics(m):
    users = list(users_col.find({}))
    
    if not users:
        bot.send_message(m.from_user.id, "📊 No users found!")
        return
    
    total_users = len(users)
    vip_users = sum(1 for u in users if u.get("vip", False))
    free_users = total_users - vip_users
    
    total_points = sum(u.get("points", 0) for u in users)
    avg_points = total_points // total_users if total_users > 0 else 0
    
    total_purchased = sum(len(u.get("purchased_methods", [])) for u in users)
    total_codes_redeemed = sum(len(u.get("used_codes", [])) for u in users)
    total_refs = sum(u.get("refs", 0) for u in users)
    
    top_users = sorted(users, key=lambda x: x.get("points", 0), reverse=True)[:5]
    
    stats_msg = f"📊 **USER STATISTICS**\n\n"
    stats_msg += f"👥 **Total Users:** {total_users}\n"
    stats_msg += f"💎 **VIP Users:** {vip_users}\n"
    stats_msg += f"🆓 **Free Users:** {free_users}\n\n"
    
    stats_msg += f"💰 **Points Statistics:**\n"
    stats_msg += f"• Total Points: {total_points:,}\n"
    stats_msg += f"• Average Points: {avg_points:,}\n\n"
    
    stats_msg += f"📚 **Content Statistics:**\n"
    stats_msg += f"• Total Methods Purchased: {total_purchased}\n"
    stats_msg += f"• Total Codes Redeemed: {total_codes_redeemed}\n"
    stats_msg += f"• Total Referrals: {total_refs}\n\n"
    
    stats_msg += f"🏆 **Top 5 Users by Points:**\n"
    for i, u in enumerate(top_users, 1):
        username = u.get("username", "Unknown")
        points = u.get("points", 0)
        stats_msg += f"{i}. {username} (ID: {u['_id']}) - {points} pts\n"
    
    bot.send_message(m.from_user.id, stats_msg, parse_mode="Markdown")

# =========================
# 📤 BROADCAST
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
    msg = bot.send_message(c.from_user.id, "📝 Send your broadcast message (text, photo, video, or document):")
    bot.register_next_step_handler(msg, lambda m: bc_send(m, t))

def bc_send(m, target):
    users = list(users_col.find({}))
    sent = 0
    failed = 0

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
        except Exception as e:
            failed += 1

    result_msg = f"✅ Broadcast completed!\n\n📤 Sent: {sent}\n❌ Failed: {failed}\n🎯 Target: {target.upper()}"
    bot.send_message(ADMIN_ID, result_msg)

# =========================
# ⭐ SET VIP MESSAGE
# =========================
@bot.message_handler(func=lambda m: m.text == "⭐ Set VIP Message" and is_admin(m.from_user.id))
def set_vip(m):
    msg = bot.send_message(m.from_user.id, "Send VIP message:")
    bot.register_next_step_handler(msg, save_vip)

def save_vip(m):
    set_config("vip_msg", m.text)
    bot.send_message(m.from_user.id, "✅ VIP message updated!")

# =========================
# 💰 SET PURCHASE MESSAGE
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 Set Purchase Message" and is_admin(m.from_user.id))
def set_purchase_msg(m):
    msg = bot.send_message(m.from_user.id, "Send purchase message (shown when users click GET POINTS or GET VIP):")
    bot.register_next_step_handler(msg, save_purchase_msg)

def save_purchase_msg(m):
    set_config("purchase_msg", m.text)
    bot.send_message(m.from_user.id, "✅ Purchase message updated!")

# =========================
# 🏠 SET WELCOME
# =========================
@bot.message_handler(func=lambda m: m.text == "🏠 Set Welcome" and is_admin(m.from_user.id))
def set_wel(m):
    msg = bot.send_message(m.from_user.id, "Send welcome message:")
    bot.register_next_step_handler(msg, save_wel)

def save_wel(m):
    set_config("welcome", m.text)
    bot.send_message(m.from_user.id, "✅ Welcome message updated!")

# =========================
# ➕ FORCE JOIN MANAGEMENT
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ Add Force Join" and is_admin(m.from_user.id))
def add_force(m):
    msg = bot.send_message(m.from_user.id, "Send @channel:")
    bot.register_next_step_handler(msg, save_force)

def save_force(m):
    cfg = get_config()
    chs = cfg.get("force_channels", [])
    if m.text not in chs:
        chs.append(m.text)
        set_config("force_channels", chs)
        bot.send_message(m.from_user.id, "✅ Added")
    else:
        bot.send_message(m.from_user.id, "Already exists")

@bot.message_handler(func=lambda m: m.text == "➖ Remove Force Join" and is_admin(m.from_user.id))
def remove_force(m):
    msg = bot.send_message(m.from_user.id, "Send channel:")
    bot.register_next_step_handler(msg, rem_force)

def rem_force(m):
    cfg = get_config()
    chs = cfg.get("force_channels", [])
    if m.text in chs:
        chs.remove(m.text)
        set_config("force_channels", chs)
        bot.send_message(m.from_user.id, "Removed")
    else:
        bot.send_message(m.from_user.id, "Not found")

# =========================
# 🧠 FALLBACK HANDLER
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
# 🚀 RUN BOT
# =========================
def run_bot():
    while True:
        try:
            print("🚀 ZEDOX BOT RUNNING WITH MONGODB...")
            print(f"✅ Bot Username: @{bot.get_me().username}")
            print(f"✅ Admin ID: {ADMIN_ID}")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    
    while True:
        time.sleep(1)
