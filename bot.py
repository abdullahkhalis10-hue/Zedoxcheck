import telebot
from telebot.types import *
from pymongo import MongoClient
import os, time, random, string, threading

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
MONGO_URI = os.getenv("MONGO_URI")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# =========================
# DATABASE
# =========================
client = MongoClient(MONGO_URI)
db = client["zedox_final"]

users_col = db["users"]
codes_col = db["codes"]
files_col = db["files"]
config_col = db["config"]
services_col = db["services"]

# =========================
# CONFIG INIT
# =========================
def init_config():
    if not config_col.find_one({"_id": "main"}):
        config_col.insert_one({
            "_id": "main",
            "force_channels": [],
            "vip_price": 100,
            "points_price": 1,
            "vip_msg": "💎 Buy VIP to unlock all features!",
            "purchase_msg": "💰 Buy points from admin!",
            "welcome": "🔥 Welcome to ZEDOX BOT",
            "ref_reward": 5
        })

init_config()

def cfg():
    return config_col.find_one({"_id": "main"})

def set_cfg(key, value):
    config_col.update_one({"_id": "main"}, {"$set": {key: value}})

# =========================
# USER SYSTEM (FINAL)
# =========================
class User:
    def __init__(self, uid):
        self.uid = str(uid)
        self.data = users_col.find_one({"_id": self.uid})

        if not self.data:
            self.data = {
                "_id": self.uid,
                "points": 0,
                "vip": False,
                "ref": None,
                "ref_count": 0,
                "purchased": [],
                "used_codes": [],
                "username": None
            }
            users_col.insert_one(self.data)

    def save(self):
        users_col.update_one({"_id": self.uid}, {"$set": self.data})

    def refresh(self):
        self.data = users_col.find_one({"_id": self.uid})

    # ----------------
    # BASIC
    # ----------------
    def points(self): return self.data["points"]
    def is_vip(self): return self.data["vip"]

    def add_points(self, p):
        self.data["points"] += p
        self.save()

    # ----------------
    # VIP
    # ----------------
    def make_vip(self):
        self.data["vip"] = True
        self.save()

    def remove_vip(self):
        self.data["vip"] = False
        self.save()

    # ----------------
    # PURCHASE
    # ----------------
    def purchase(self, name):
        if name not in self.data["purchased"]:
            self.data["purchased"].append(name)
            self.save()

    def has(self, name):
        return self.is_vip() or name in self.data["purchased"]

    # ----------------
    # REFERRAL (FIXED)
    # ----------------
    def add_ref(self, ref_id):
        if self.data["ref"] or ref_id == self.uid:
            return

        ref_user = User(ref_id)
        ref_user.data["ref_count"] += 1
        ref_user.add_points(cfg()["ref_reward"])
        ref_user.save()

        self.data["ref"] = ref_id
        self.save()

    def ref_count(self):
        return self.data.get("ref_count", 0)

    # ----------------
    # USERNAME
    # ----------------
    def update_username(self, username):
        if username and username != self.data.get("username"):
            self.data["username"] = username
            self.save()

# =========================
# FILE SYSTEM
# =========================
class FS:
    def add(self, cat, name, files, price):
        files_col.insert_one({
            "cat": cat,
            "name": name,
            "files": files,
            "price": price
        })

    def get(self, cat):
        return list(files_col.find({"cat": cat}))

    def get_one(self, cat, name):
        return files_col.find_one({"cat": cat, "name": name})

fs = FS()

# =========================
# SERVICES SYSTEM (FIXED)
# =========================
class Services:
    def add(self, name, price, message):
        services_col.insert_one({
            "_id": ''.join(random.choices(string.ascii_letters, k=6)),
            "name": name,
            "price": price,
            "message": message,
            "available": True
        })

    def all(self):
        return list(services_col.find())

    def get(self, sid):
        return services_col.find_one({"_id": sid})

    def toggle(self, sid):
        s = self.get(sid)
        services_col.update_one(
            {"_id": sid},
            {"$set": {"available": not s["available"]}}
        )

services = Services()

# =========================
# FORCE JOIN
# =========================
def force_block(uid):
    for ch in cfg()["force_channels"]:
        try:
            m = bot.get_chat_member(ch, uid)
            if m.status in ["left", "kicked"]:
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton("Join", url=f"https://t.me/{ch.replace('@','')}"))
                kb.add(InlineKeyboardButton("🔄 Recheck", callback_data="recheck"))
                bot.send_message(uid, "Join channels first!", reply_markup=kb)
                return True
        except:
            return True
    return False
    # =========================
# ADMIN CHECK
# =========================
def is_admin(uid):
    return uid == ADMIN_ID


# =========================
# ADMIN MENU (UPDATED)
# =========================
def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)

    kb.row("📦 Upload FREE", "💎 Upload VIP")
    kb.row("📱 Upload APPS", "🛠 Manage Services")

    kb.row("💎 Set VIP Price", "💰 Set Points Price")
    kb.row("⭐ Set VIP Message", "💰 Set Purchase Msg")

    kb.row("👑 Add VIP", "❌ Remove VIP")
    kb.row("📊 Statistics", "📢 Broadcast")

    kb.row("🏠 Set Welcome", "➕ Force Join")
    kb.row("➖ Remove Join")

    kb.row("❌ Exit Admin")
    return kb


# =========================
# OPEN ADMIN PANEL
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def open_admin(m):
    bot.send_message(m.from_user.id, "⚙️ Admin Panel", reply_markup=admin_menu())


@bot.message_handler(func=lambda m: m.text == "❌ Exit Admin" and is_admin(m.from_user.id))
def exit_admin(m):
    bot.send_message(m.from_user.id, "Exited Admin", reply_markup=main_menu(m.from_user.id))


# =========================
# 💎 SET VIP PRICE
# =========================
@bot.message_handler(func=lambda m: m.text == "💎 Set VIP Price" and is_admin(m.from_user.id))
def set_vip_price(m):
    msg = bot.send_message(m.from_user.id, "Enter VIP price (points):")
    bot.register_next_step_handler(msg, save_vip_price)

def save_vip_price(m):
    try:
        price = int(m.text)
        set_cfg("vip_price", price)
        bot.send_message(m.from_user.id, f"✅ VIP price set to {price}")
    except:
        bot.send_message(m.from_user.id, "❌ Invalid number")


# =========================
# 💰 SET POINT PRICE
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 Set Points Price" and is_admin(m.from_user.id))
def set_points_price(m):
    msg = bot.send_message(m.from_user.id, "Enter price per point:")
    bot.register_next_step_handler(msg, save_points_price)

def save_points_price(m):
    try:
        price = int(m.text)
        set_cfg("points_price", price)
        bot.send_message(m.from_user.id, f"✅ Points price updated")
    except:
        bot.send_message(m.from_user.id, "❌ Invalid")


# =========================
# ⭐ SET VIP MESSAGE (FIXED)
# =========================
@bot.message_handler(func=lambda m: m.text == "⭐ Set VIP Message" and is_admin(m.from_user.id))
def set_vip_msg(m):
    msg = bot.send_message(m.from_user.id, "Send VIP message:")
    bot.register_next_step_handler(msg, save_vip_msg)

def save_vip_msg(m):
    set_cfg("vip_msg", m.text)
    bot.send_message(m.from_user.id, "✅ VIP message updated!")


# =========================
# 💰 SET PURCHASE MESSAGE
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 Set Purchase Msg" and is_admin(m.from_user.id))
def set_purchase(m):
    msg = bot.send_message(m.from_user.id, "Send purchase message:")
    bot.register_next_step_handler(msg, save_purchase)

def save_purchase(m):
    set_cfg("purchase_msg", m.text)
    bot.send_message(m.from_user.id, "✅ Updated!")


# =========================
# 🛠 SERVICES MANAGEMENT (FIXED)
# =========================
@bot.message_handler(func=lambda m: m.text == "🛠 Manage Services" and is_admin(m.from_user.id))
def services_menu(m):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ Add Service", callback_data="srv_add"))
    kb.add(InlineKeyboardButton("📋 View Services", callback_data="srv_list"))
    bot.send_message(m.from_user.id, "🛠 Services Panel:", reply_markup=kb)


# ADD SERVICE
@bot.callback_query_handler(func=lambda c: c.data == "srv_add")
def srv_add(c):
    msg = bot.send_message(c.from_user.id, "Service name:")
    bot.register_next_step_handler(msg, srv_price)

def srv_price(m):
    name = m.text
    msg = bot.send_message(m.from_user.id, "Price (points):")
    bot.register_next_step_handler(msg, lambda m2: srv_msg(m2, name))

def srv_msg(m, name):
    price = int(m.text)
    msg = bot.send_message(m.from_user.id, "Delivery message:")
    bot.register_next_step_handler(msg, lambda m2: srv_save(m2, name, price))

def srv_save(m, name, price):
    services.add(name, price, m.text)
    bot.send_message(m.from_user.id, "✅ Service added!")


# VIEW SERVICES
@bot.callback_query_handler(func=lambda c: c.data == "srv_list")
def srv_list(c):
    kb = InlineKeyboardMarkup()
    for s in services.all():
        status = "🟢" if s["available"] else "🔴"
        kb.add(InlineKeyboardButton(
            f"{status} {s['name']} ({s['price']} pts)",
            callback_data=f"srv_toggle|{s['_id']}"
        ))
    bot.edit_message_text("Click to toggle:", c.from_user.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("srv_toggle"))
def srv_toggle(c):
    sid = c.data.split("|")[1]
    services.toggle(sid)
    bot.answer_callback_query(c.id, "Updated!")
    srv_list(c)


# =========================
# 👑 VIP MANAGEMENT
# =========================
@bot.message_handler(func=lambda m: m.text == "👑 Add VIP" and is_admin(m.from_user.id))
def add_vip(m):
    msg = bot.send_message(m.from_user.id, "Send user ID:")
    bot.register_next_step_handler(msg, do_add_vip)

def do_add_vip(m):
    user = User(m.text)
    user.make_vip()
    bot.send_message(m.from_user.id, "✅ VIP Added")


@bot.message_handler(func=lambda m: m.text == "❌ Remove VIP" and is_admin(m.from_user.id))
def rem_vip(m):
    msg = bot.send_message(m.from_user.id, "Send user ID:")
    bot.register_next_step_handler(msg, do_rem_vip)

def do_rem_vip(m):
    user = User(m.text)
    user.remove_vip()
    bot.send_message(m.from_user.id, "❌ VIP Removed")


# =========================
# 📊 ADVANCED STATISTICS (FULL)
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 Statistics" and is_admin(m.from_user.id))
def stats(m):
    users = list(users_col.find())

    total = len(users)
    vip = len([u for u in users if u["vip"]])
    free = total - vip

    total_points = sum(u["points"] for u in users)
    total_refs = sum(u.get("ref_count", 0) for u in users)
    total_methods = sum(len(u.get("purchased", [])) for u in users)

    top = sorted(users, key=lambda x: x["points"], reverse=True)[:5]

    msg = f"""
📊 *STATISTICS*

👥 Total Users: {total}
💎 VIP Users: {vip}
🆓 Free Users: {free}

💰 Total Points: {total_points}
🎁 Total Referrals: {total_refs}
📚 Methods Purchased: {total_methods}

🏆 Top Users:
"""

    for i, u in enumerate(top, 1):
        msg += f"\n{i}. {u.get('username','NoUser')} - {u['points']} pts"

    bot.send_message(m.from_user.id, msg, parse_mode="Markdown")


# =========================
# 📢 BROADCAST
# =========================
@bot.message_handler(func=lambda m: m.text == "📢 Broadcast" and is_admin(m.from_user.id))
def broadcast(m):
    msg = bot.send_message(m.from_user.id, "Send message:")
    bot.register_next_step_handler(msg, send_bc)

def send_bc(m):
    users = users_col.find()
    sent = 0

    for u in users:
        try:
            bot.send_message(int(u["_id"]), m.text)
            sent += 1
        except:
            pass

    bot.send_message(ADMIN_ID, f"✅ Sent to {sent} users")


# =========================
# FORCE JOIN SETTINGS
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ Force Join" and is_admin(m.from_user.id))
def add_join(m):
    msg = bot.send_message(m.from_user.id, "Send @channel:")
    bot.register_next_step_handler(msg, save_join)

def save_join(m):
    data = cfg()
    data["force_channels"].append(m.text)
    set_cfg("force_channels", data["force_channels"])
    bot.send_message(m.from_user.id, "✅ Added")


@bot.message_handler(func=lambda m: m.text == "➖ Remove Join" and is_admin(m.from_user.id))
def rem_join(m):
    msg = bot.send_message(m.from_user.id, "Send @channel:")
    bot.register_next_step_handler(msg, do_rem_join)

def do_rem_join(m):
    data = cfg()
    if m.text in data["force_channels"]:
        data["force_channels"].remove(m.text)
        set_cfg("force_channels", data["force_channels"])
    bot.send_message(m.from_user.id, "Removed")
    # =========================
# MAIN MENU (UPDATED)
# =========================
def main_menu(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)

    kb.row("📂 FREE METHODS", "💎 VIP METHODS")
    kb.row("📦 PREMIUM APPS", "🛠 SERVICES")

    kb.row("💰 POINTS", "⭐ GET VIP")
    kb.row("🎁 REFERRAL", "👤 ACCOUNT")

    kb.row("📚 MY METHODS", "💎 GET POINTS")
    kb.row("🆔 CHAT ID")

    if uid == ADMIN_ID:
        kb.row("⚙️ ADMIN PANEL")

    return kb


# =========================
# START (FIXED REFERRAL)
# =========================
@bot.message_handler(commands=["start"])
def start(m):
    uid = str(m.from_user.id)
    user = User(uid)

    if m.from_user.username:
        user.update_username(m.from_user.username)

    args = m.text.split()

    if len(args) > 1:
        ref = args[1]
        if ref != uid:
            user.add_ref(ref)

    if force_block(uid):
        return

    bot.send_message(uid, cfg()["welcome"], reply_markup=main_menu(uid))


# =========================
# 📂 SHOW METHODS
# =========================
@bot.message_handler(func=lambda m: m.text in [
    "📂 FREE METHODS", "💎 VIP METHODS", "📦 PREMIUM APPS"
])
def show_methods(m):
    uid = m.from_user.id
    user = User(uid)

    if force_block(uid):
        return

    mapping = {
        "📂 FREE METHODS": "free",
        "💎 VIP METHODS": "vip",
        "📦 PREMIUM APPS": "apps"
    }

    cat = mapping[m.text]
    data = fs.get(cat)

    if not data:
        bot.send_message(uid, "No data available")
        return

    kb = InlineKeyboardMarkup()

    for f in data:
        name = f["name"]
        price = f["price"]
        kb.add(InlineKeyboardButton(
            f"{name} ({price} pts)",
            callback_data=f"open|{cat}|{name}"
        ))

    bot.send_message(uid, "Select:", reply_markup=kb)


# =========================
# OPEN METHOD
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("open|"))
def open_method(c):
    uid = c.from_user.id
    user = User(uid)

    _, cat, name = c.data.split("|")
    data = fs.get_one(cat, name)

    if not data:
        bot.answer_callback_query(c.id, "Not found")
        return

    price = data["price"]

    # VIP LOCK
    if cat == "vip" and not user.has(name):
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("💰 Buy", callback_data=f"buy|{name}|{price}"))
        kb.add(InlineKeyboardButton("⭐ Get VIP", callback_data="getvip"))
        bot.send_message(uid, f"🔒 {name}\nPrice: {price}", reply_markup=kb)
        return

    # NORMAL BUY
    if price > 0 and not user.has(name):
        if user.points() < price:
            bot.answer_callback_query(c.id, "Not enough points", show_alert=True)
            return

        user.add_points(-price)
        user.purchase(name)

    # SEND FILES
    for f in data["files"]:
        bot.copy_message(uid, f["chat"], f["msg"])

    bot.answer_callback_query(c.id, "✅ Sent!")


# =========================
# 💰 BUY BUTTON
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy|"))
def buy_method(c):
    uid = c.from_user.id
    user = User(uid)

    _, name, price = c.data.split("|")
    price = int(price)

    if user.points() < price:
        bot.answer_callback_query(c.id, "Not enough points", True)
        return

    data = fs.get_one("vip", name)

    user.add_points(-price)
    user.purchase(name)

    # SEND FILES INSTANTLY
    for f in data["files"]:
        bot.copy_message(uid, f["chat"], f["msg"])

    bot.edit_message_text("✅ Purchased & Sent!", uid, c.message.message_id)


# =========================
# 🛠 SERVICES (WORKING)
# =========================
@bot.message_handler(func=lambda m: m.text == "🛠 SERVICES")
def services_ui(m):
    uid = m.from_user.id
    user = User(uid)

    if force_block(uid):
        return

    kb = InlineKeyboardMarkup()

    for s in services.all():
        if not s["available"]:
            continue

        kb.add(InlineKeyboardButton(
            f"{s['name']} ({s['price']} pts)",
            callback_data=f"service|{s['_id']}"
        ))

    bot.send_message(uid, "🛠 Services:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("service|"))
def service_buy(c):
    uid = c.from_user.id
    user = User(uid)

    sid = c.data.split("|")[1]
    s = services.get(sid)

    if not s or not s["available"]:
        bot.answer_callback_query(c.id, "Unavailable")
        return

    if user.points() < s["price"]:
        bot.answer_callback_query(c.id, "Not enough points", True)
        return

    user.add_points(-s["price"])

    # SEND ADMIN SET MESSAGE
    bot.send_message(uid, s["message"])

    bot.answer_callback_query(c.id, "✅ Delivered")


# =========================
# 📚 MY METHODS (BUTTON UI)
# =========================
@bot.message_handler(func=lambda m: m.text == "📚 MY METHODS")
def my_methods(m):
    uid = m.from_user.id
    user = User(uid)

    if force_block(uid):
        return

    if user.is_vip():
        bot.send_message(uid, "💎 You have ALL VIP access!")
        return

    kb = InlineKeyboardMarkup()

    for name in user.data["purchased"]:
        kb.add(InlineKeyboardButton(
            name,
            callback_data=f"open|vip|{name}"
        ))

    bot.send_message(uid, "📚 Your Methods:", reply_markup=kb)


# =========================
# 🎁 REFERRAL (FIXED UI)
# =========================
@bot.message_handler(func=lambda m: m.text == "🎁 REFERRAL")
def referral(m):
    uid = m.from_user.id
    user = User(uid)

    link = f"https://t.me/{bot.get_me().username}?start={uid}"

    bot.send_message(uid,
        f"🎁 Referral Link:\n{link}\n\n"
        f"👥 Referrals: {user.ref_count()}\n"
        f"🎁 Reward: {cfg()['ref_reward']} pts"
    )


# =========================
# 💰 POINTS
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 POINTS")
def points(m):
    user = User(m.from_user.id)
    bot.send_message(m.from_user.id, f"💰 Points: {user.points()}")


# =========================
# 💎 GET VIP (FIXED)
# =========================
@bot.message_handler(func=lambda m: m.text == "⭐ GET VIP")
def get_vip(m):
    bot.send_message(
        m.from_user.id,
        f"💎 VIP Price: {cfg()['vip_price']} pts\n\n{cfg()['vip_msg']}"
    )


# =========================
# 💎 GET POINTS (FIXED)
# =========================
@bot.message_handler(func=lambda m: m.text == "💎 GET POINTS")
def get_points(m):
    bot.send_message(
        m.from_user.id,
        f"💰 1 Point = {cfg()['points_price']}\n\n{cfg()['purchase_msg']}"
    )


# =========================
# 👤 ACCOUNT
# =========================
@bot.message_handler(func=lambda m: m.text == "👤 ACCOUNT")
def account(m):
    user = User(m.from_user.id)

    bot.send_message(m.from_user.id,
        f"👤 Account\n\n"
        f"Points: {user.points()}\n"
        f"VIP: {user.is_vip()}\n"
        f"Referrals: {user.ref_count()}\n"
        f"Methods: {len(user.data['purchased'])}"
    )


# =========================
# 🆔 CHAT ID
# =========================
@bot.message_handler(func=lambda m: m.text == "🆔 CHAT ID")
def chatid(m):
    bot.send_message(m.from_user.id, f"🆔 {m.from_user.id}")
    # =========================
# 🎫 CODES SYSTEM (MONGODB)
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
                "used_by": None
            })
            res.append(code)
        return res

    def redeem(self, code, user: User):
        data = codes_col.find_one({"_id": code})

        if not data:
            return False, "invalid"

        if data["used"]:
            return False, "used"

        # mark used
        codes_col.update_one(
            {"_id": code},
            {"$set": {"used": True, "used_by": user.uid}}
        )

        user.add_points(data["points"])
        return True, data["points"]

codesys = Codes()


# =========================
# 🎫 ADMIN GENERATE CODES
# =========================
@bot.message_handler(func=lambda m: m.text == "🏆 Generate Codes" and is_admin(m.from_user.id))
def gen_codes(m):
    msg = bot.send_message(m.from_user.id, "Points per code:")
    bot.register_next_step_handler(msg, gen_count)

def gen_count(m):
    pts = int(m.text)
    msg = bot.send_message(m.from_user.id, "How many?")
    bot.register_next_step_handler(msg, lambda m2: gen_done(m2, pts))

def gen_done(m, pts):
    count = int(m.text)
    res = codesys.generate(pts, count)

    bot.send_message(
        m.from_user.id,
        "✅ Codes Generated:\n\n" + "\n".join(res)
    )


# =========================
# 🎫 USER REDEEM
# =========================
@bot.message_handler(func=lambda m: m.text == "🏆 REDEEM")
def redeem_start(m):
    msg = bot.send_message(m.from_user.id, "Enter code:")
    bot.register_next_step_handler(msg, redeem_code)

def redeem_code(m):
    user = User(m.from_user.id)
    code = m.text.strip().upper()

    ok, res = codesys.redeem(code, user)

    if ok:
        bot.send_message(m.from_user.id, f"✅ +{res} points added!")
    else:
        if res == "invalid":
            bot.send_message(m.from_user.id, "❌ Invalid code")
        elif res == "used":
            bot.send_message(m.from_user.id, "❌ Already used")


# =========================
# 🔄 FORCE JOIN RECHECK
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "recheck")
def recheck(c):
    uid = c.from_user.id

    if not force_block(uid):
        try:
            bot.edit_message_text(
                "✅ Access Granted!",
                uid,
                c.message.message_id
            )
        except:
            pass

        bot.send_message(uid, "🎉 Welcome!", reply_markup=main_menu(uid))
    else:
        bot.answer_callback_query(c.id, "Join all channels first", True)


# =========================
# 🛡 SAFE FUNCTIONS
# =========================
def safe_send(uid, text):
    try:
        bot.send_message(uid, text)
    except Exception as e:
        print("SEND ERROR:", e)

def safe_copy(uid, chat, msg):
    try:
        bot.copy_message(uid, chat, msg)
    except Exception as e:
        print("COPY ERROR:", e)


# =========================
# ⚠️ FALLBACK (ANTI-SPAM)
# =========================
@bot.message_handler(content_types=['text'])
def fallback(m):
    uid = m.from_user.id

    if force_block(uid):
        return

    known = [
        "📂 FREE METHODS", "💎 VIP METHODS",
        "📦 PREMIUM APPS", "🛠 SERVICES",
        "💰 POINTS", "⭐ GET VIP",
        "💎 GET POINTS", "🎁 REFERRAL",
        "👤 ACCOUNT", "📚 MY METHODS",
        "🆔 CHAT ID", "🏆 REDEEM",
        "⚙️ ADMIN PANEL"
    ]

    if m.text not in known:
        safe_send(uid, "❌ Use buttons only")


# =========================
# 🔁 AUTO RESTART SYSTEM
# =========================
def run_bot():
    while True:
        try:
            print("🚀 BOT RUNNING...")
            print(f"🤖 @{bot.get_me().username}")

            bot.infinity_polling(timeout=60, long_polling_timeout=60)

        except Exception as e:
            print("CRASH:", e)
            time.sleep(5)


# =========================
# 🚀 START BOT
# =========================
if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()

    while True:
        time.sleep(1)
