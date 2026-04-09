import telebot
from telebot.types import *
from pymongo import MongoClient
import os, time, random, string

# =========================
# ENV VARIABLES
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
MONGO_URI = os.getenv("MONGO_URI")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# =========================
# MONGODB CONNECTION
# =========================
client = MongoClient(MONGO_URI)
db = client["zedox_bot"]

users_col = db["users"]
codes_col = db["codes"]
config_col = db["config"]
files_col = db["files"]
services_col = db["services"]

# =========================
# INIT CONFIG
# =========================
def init_config():
    if not config_col.find_one({"_id": "main"}):
        config_col.insert_one({
            "_id": "main",
            "force_channels": [],
            "vip_msg": "💎 Buy VIP to unlock this!",
            "welcome": "🔥 Welcome to ZEDOX BOT",
            "ref_reward": 5,
            "purchase_msg": "💰 Purchase VIP to access premium features!",
            "notify": True
        })

init_config()

def get_config():
    return config_col.find_one({"_id": "main"})

def update_config(key, value):
    config_col.update_one({"_id": "main"}, {"$set": {key: value}})

# =========================
# USER SYSTEM (FULL + FIXED REFERRAL)
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
                "purchased_methods": [],
                "used_codes": [],
                "username": None
            }
            users_col.insert_one(self.data)

    def refresh(self):
        self.data = users_col.find_one({"_id": self.uid})

    def save(self):
        users_col.update_one({"_id": self.uid}, {"$set": self.data})

    # BASIC
    def points(self): return self.data.get("points", 0)
    def is_vip(self): return self.data.get("vip", False)
    def username(self): return self.data.get("username")

    def update_username(self, username):
        if username and username != self.data.get("username"):
            self.data["username"] = username
            self.save()

    # POINTS
    def add_points(self, p):
        self.data["points"] += p
        self.save()

    # VIP
    def make_vip(self):
        self.data["vip"] = True
        self.save()

    def remove_vip(self):
        self.data["vip"] = False
        self.save()

    # METHODS
    def purchase_method(self, name, price):
        if self.points() >= price:
            self.add_points(-price)
            if name not in self.data["purchased_methods"]:
                self.data["purchased_methods"].append(name)
                self.save()
            return True
        return False

    def can_access(self, name):
        return self.is_vip() or name in self.data["purchased_methods"]

    # CODES
    def add_used_code(self, code):
        if code not in self.data["used_codes"]:
            self.data["used_codes"].append(code)
            self.save()

    def has_used(self, code):
        return code in self.data["used_codes"]

    # ✅ FIXED REFERRAL SYSTEM
    def add_referral(self, ref_id):
        if self.data["ref"] or ref_id == self.uid:
            return

        ref_user = User(ref_id)

        ref_user.data["ref_count"] += 1
        ref_user.add_points(get_config()["ref_reward"])
        ref_user.save()

        self.data["ref"] = ref_id
        self.save()

    def ref_count(self):
        return self.data.get("ref_count", 0)

# =========================
# CODES SYSTEM (SECURE)
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

    def redeem(self, code, user: User):
        data = codes_col.find_one({"_id": code})

        if not data:
            return False, "invalid"

        if data["used"]:
            return False, "used"

        if user.has_used(code):
            return False, "user_used"

        user.add_points(data["points"])
        user.add_used_code(code)

        codes_col.update_one({"_id": code}, {
            "$set": {
                "used": True,
                "used_by": user.uid,
                "used_at": time.time()
            }
        })

        return True, data["points"]

codesys = Codes()

# =========================
# FILE SYSTEM (MongoDB)
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

    def delete(self, cat, name):
        files_col.delete_one({"cat": cat, "name": name})

    def edit(self, cat, name, price):
        files_col.update_one(
            {"cat": cat, "name": name},
            {"$set": {"price": price}}
        )

fs = FS()

# =========================
# SERVICES SYSTEM (DB BASE)
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
# FORCE JOIN (Mongo)
# =========================
def force_block(uid):
    channels = get_config().get("force_channels", [])

    for ch in channels:
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
# HELPERS
# =========================
def is_admin(uid):
    return uid == ADMIN_ID

def gen_code():
    return ''.join(random.choices(string.ascii_uppercase+string.digits, k=6))
# =========================
# ADMIN MENU (BUTTON UI)
# =========================
def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)

    kb.row("📦 Upload FREE", "💎 Upload VIP")
    kb.row("📱 Upload APPS", "🛠 Manage Services")

    kb.row("✏️ Edit Price", "🗑 Delete Folder")

    kb.row("👑 Add VIP", "👑 Remove VIP")
    kb.row("🏆 Generate Codes", "📊 View Codes")

    kb.row("📤 Broadcast")

    kb.row("⭐ Set VIP Msg", "💰 Set Purchase Msg")
    kb.row("🏠 Set Welcome")

    kb.row("➕ Add Force Join", "➖ Remove Force Join")

    kb.row("❌ Exit Admin")
    return kb


# =========================
# OPEN ADMIN PANEL
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def open_admin(m):
    bot.send_message(m.chat.id, "⚙️ Admin Panel", reply_markup=admin_menu())


@bot.message_handler(func=lambda m: m.text == "❌ Exit Admin" and is_admin(m.from_user.id))
def exit_admin(m):
    bot.send_message(m.chat.id, "Exited Admin", reply_markup=main_menu(m.from_user.id))


# =========================
# UPLOAD SYSTEM
# =========================
def start_upload(uid, cat):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("/done", "/cancel")

    msg = bot.send_message(uid, f"📤 Send files for {cat}\n\nUse /done when finished", reply_markup=kb)
    bot.register_next_step_handler(msg, lambda m: upload_step(m, cat, [], uid))


def upload_step(m, cat, files, uid):
    if m.text == "/cancel":
        return bot.send_message(uid, "❌ Cancelled", reply_markup=admin_menu())

    if m.text == "/done":
        if not files:
            return bot.send_message(uid, "No files uploaded")

        msg = bot.send_message(uid, "Folder name:")
        return bot.register_next_step_handler(msg, lambda x: upload_name(x, cat, files))

    if m.content_type in ["document", "photo", "video"]:
        files.append({"chat": m.chat.id, "msg": m.message_id})
        bot.send_message(uid, f"Saved {len(files)} file(s)")

    bot.register_next_step_handler(m, lambda x: upload_step(x, cat, files, uid))


def upload_name(m, cat, files):
    name = m.text
    msg = bot.send_message(m.chat.id, "Price (0 for free):")
    bot.register_next_step_handler(msg, lambda x: upload_save(x, cat, name, files))


def upload_save(m, cat, name, files):
    try:
        price = int(m.text)
        fs.add(cat, name, files, price)
        bot.send_message(m.chat.id, "✅ Uploaded!", reply_markup=admin_menu())
    except:
        bot.send_message(m.chat.id, "Invalid price")


@bot.message_handler(func=lambda m: m.text == "📦 Upload FREE" and is_admin(m.from_user.id))
def up_free(m): start_upload(m.chat.id, "free")

@bot.message_handler(func=lambda m: m.text == "💎 Upload VIP" and is_admin(m.from_user.id))
def up_vip(m): start_upload(m.chat.id, "vip")

@bot.message_handler(func=lambda m: m.text == "📱 Upload APPS" and is_admin(m.from_user.id))
def up_apps(m): start_upload(m.chat.id, "apps")


# =========================
# DELETE FOLDER
# =========================
@bot.message_handler(func=lambda m: m.text == "🗑 Delete Folder" and is_admin(m.from_user.id))
def delete_start(m):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("FREE", callback_data="del|free"))
    kb.add(InlineKeyboardButton("VIP", callback_data="del|vip"))
    kb.add(InlineKeyboardButton("APPS", callback_data="del|apps"))
    bot.send_message(m.chat.id, "Select category:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("del|"))
def delete_list(c):
    cat = c.data.split("|")[1]
    data = fs.get(cat)

    kb = InlineKeyboardMarkup()
    for f in data:
        kb.add(InlineKeyboardButton(f["name"], callback_data=f"delf|{cat}|{f['name']}"))

    bot.edit_message_text("Select folder:", c.from_user.id, c.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("delf|"))
def delete_final(c):
    _, cat, name = c.data.split("|")
    fs.delete(cat, name)
    bot.answer_callback_query(c.id, "Deleted")
    bot.edit_message_text("✅ Deleted", c.from_user.id, c.message.message_id)


# =========================
# EDIT PRICE
# =========================
@bot.message_handler(func=lambda m: m.text == "✏️ Edit Price" and is_admin(m.from_user.id))
def edit_start(m):
    msg = bot.send_message(m.chat.id, "Category (free/vip/apps):")
    bot.register_next_step_handler(msg, edit_name)


def edit_name(m):
    cat = m.text.lower()
    msg = bot.send_message(m.chat.id, "Folder name:")
    bot.register_next_step_handler(msg, lambda x: edit_price(x, cat))


def edit_price(m, cat):
    name = m.text
    msg = bot.send_message(m.chat.id, "New price:")
    bot.register_next_step_handler(msg, lambda x: save_price(x, cat, name))


def save_price(m, cat, name):
    try:
        fs.edit(cat, name, int(m.text))
        bot.send_message(m.chat.id, "✅ Updated")
    except:
        bot.send_message(m.chat.id, "Error")


# =========================
# VIP MANAGEMENT
# =========================
@bot.message_handler(func=lambda m: m.text == "👑 Add VIP" and is_admin(m.from_user.id))
def add_vip(m):
    msg = bot.send_message(m.chat.id, "Send user ID:")
    bot.register_next_step_handler(msg, process_add_vip)


def process_add_vip(m):
    user = User(m.text)
    user.make_vip()
    bot.send_message(m.chat.id, "✅ VIP added")


@bot.message_handler(func=lambda m: m.text == "👑 Remove VIP" and is_admin(m.from_user.id))
def rem_vip(m):
    msg = bot.send_message(m.chat.id, "Send user ID:")
    bot.register_next_step_handler(msg, process_rem_vip)


def process_rem_vip(m):
    user = User(m.text)
    user.remove_vip()
    bot.send_message(m.chat.id, "❌ VIP removed")


# =========================
# CODES SYSTEM (ADMIN)
# =========================
@bot.message_handler(func=lambda m: m.text == "🏆 Generate Codes" and is_admin(m.from_user.id))
def gen_codes(m):
    msg = bot.send_message(m.chat.id, "Points per code:")
    bot.register_next_step_handler(msg, code_count)


def code_count(m):
    pts = int(m.text)
    msg = bot.send_message(m.chat.id, "How many?")
    bot.register_next_step_handler(msg, lambda x: save_codes(x, pts))


def save_codes(m, pts):
    codes = codesys.generate(pts, int(m.text))
    bot.send_message(m.chat.id, "\n".join(codes))


@bot.message_handler(func=lambda m: m.text == "📊 View Codes" and is_admin(m.from_user.id))
def view_codes(m):
    all_codes = list(codes_col.find())
    msg = f"Total: {len(all_codes)}\n\n"
    for c in all_codes[:20]:
        status = "❌ Used" if c["used"] else "✅ Free"
        msg += f"{c['_id']} - {status}\n"
    bot.send_message(m.chat.id, msg)


# =========================
# BROADCAST
# =========================
@bot.message_handler(func=lambda m: m.text == "📤 Broadcast" and is_admin(m.from_user.id))
def bc(m):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("All", callback_data="bc|all"))
    kb.add(InlineKeyboardButton("VIP", callback_data="bc|vip"))
    kb.add(InlineKeyboardButton("Free", callback_data="bc|free"))
    bot.send_message(m.chat.id, "Select:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("bc|"))
def bc_select(c):
    target = c.data.split("|")[1]
    msg = bot.send_message(c.from_user.id, "Send message:")
    bot.register_next_step_handler(msg, lambda x: bc_send(x, target))


def bc_send(m, target):
    users = list(users_col.find())

    for u in users:
        if target == "vip" and not u.get("vip"):
            continue
        if target == "free" and u.get("vip"):
            continue

        try:
            bot.send_message(int(u["_id"]), m.text)
        except:
            pass

    bot.send_message(ADMIN_ID, "✅ Broadcast done")


# =========================
# FORCE JOIN
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ Add Force Join" and is_admin(m.from_user.id))
def add_force(m):
    msg = bot.send_message(m.chat.id, "Channel @username:")
    bot.register_next_step_handler(msg, save_force)


def save_force(m):
    cfg = get_config()
    chs = cfg["force_channels"]
    if m.text not in chs:
        chs.append(m.text)
        update_config("force_channels", chs)
    bot.send_message(m.chat.id, "Added")


@bot.message_handler(func=lambda m: m.text == "➖ Remove Force Join" and is_admin(m.from_user.id))
def rem_force(m):
    msg = bot.send_message(m.chat.id, "Channel:")
    bot.register_next_step_handler(msg, del_force)


def del_force(m):
    cfg = get_config()
    chs = cfg["force_channels"]
    if m.text in chs:
        chs.remove(m.text)
        update_config("force_channels", chs)
    bot.send_message(m.chat.id, "Removed")


# =========================
# SETTINGS
# =========================
@bot.message_handler(func=lambda m: m.text == "⭐ Set VIP Msg" and is_admin(m.from_user.id))
def set_vip(m):
    msg = bot.send_message(m.chat.id, "Send VIP message:")
    bot.register_next_step_handler(msg, lambda x: update_config("vip_msg", x.text))


@bot.message_handler(func=lambda m: m.text == "💰 Set Purchase Msg" and is_admin(m.from_user.id))
def set_purchase(m):
    msg = bot.send_message(m.chat.id, "Send purchase msg:")
    bot.register_next_step_handler(msg, lambda x: update_config("purchase_msg", x.text))


@bot.message_handler(func=lambda m: m.text == "🏠 Set Welcome" and is_admin(m.from_user.id))
def set_welcome(m):
    msg = bot.send_message(m.chat.id, "Send welcome:")
    bot.register_next_step_handler(msg, lambda x: update_config("welcome", x.text))
# =========================
# MAIN MENU (USER)
# =========================
def main_menu(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)

    kb.row("📂 FREE METHODS", "💎 VIP METHODS")
    kb.row("📦 PREMIUM APPS", "🛠 SERVICES")

    kb.row("💰 POINTS", "⭐ GET VIP")
    kb.row("🎁 REFERRAL", "👤 ACCOUNT")

    kb.row("📚 MY METHODS", "💎 GET POINTS")
    kb.row("🆔 CHAT ID", "🏆 REDEEM")

    if uid == ADMIN_ID:
        kb.row("⚙️ ADMIN PANEL")

    return kb


# =========================
# START COMMAND (FIXED REFERRAL)
# =========================
@bot.message_handler(commands=["start"])
def start_cmd(m):
    uid = m.from_user.id
    user = User(uid)

    # update username
    if m.from_user.username:
        user.update_username(m.from_user.username)

    # referral fix
    args = m.text.split()
    if len(args) > 1:
        ref = args[1]
        user.add_referral(ref)

    if force_block(uid):
        return

    bot.send_message(uid, get_config()["welcome"], reply_markup=main_menu(uid))


# =========================
# SHOW FOLDERS
# =========================
def get_kb(cat, page=0):
    data = fs.get(cat)
    per = 10
    start = page * per
    items = data[start:start+per]

    kb = InlineKeyboardMarkup()

    for f in items:
        name = f["name"]
        price = f["price"]
        txt = f"{name} [{price} pts]" if price > 0 else name
        kb.add(InlineKeyboardButton(txt, callback_data=f"open|{cat}|{name}"))

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"page|{cat}|{page-1}"))
    if start + per < len(data):
        nav.append(InlineKeyboardButton("➡️", callback_data=f"page|{cat}|{page+1}"))

    if nav:
        kb.row(*nav)

    return kb


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

    cat = mapping[m.text]

    if not fs.get(cat):
        return bot.send_message(uid, "No folders available")

    bot.send_message(uid, "Select folder:", reply_markup=get_kb(cat, 0))


# =========================
# PAGINATION
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("page|"))
def page_handler(c):
    _, cat, page = c.data.split("|")

    bot.edit_message_reply_markup(
        c.from_user.id,
        c.message.message_id,
        reply_markup=get_kb(cat, int(page))
    )


# =========================
# OPEN FOLDER
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("open|"))
def open_folder(c):
    uid = c.from_user.id
    user = User(uid)

    _, cat, name = c.data.split("|")

    folder = fs.get_one(cat, name)
    if not folder:
        return bot.answer_callback_query(c.id, "Not found")

    price = folder["price"]

    # VIP CHECK
    if cat == "vip":
        if not user.can_access(name):
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("⭐ GET VIP", callback_data="get_vip"))
            kb.add(InlineKeyboardButton("💎 GET POINTS", callback_data="get_points"))

            if price > 0:
                kb.add(InlineKeyboardButton(f"💰 Buy ({price})", callback_data=f"buy|{name}|{price}"))

            bot.send_message(uid, "🔒 VIP METHOD", reply_markup=kb)
            return

    # PRICE CHECK (FREE/APPS)
    if cat != "vip" and price > 0:
        if user.points() < price:
            return bot.answer_callback_query(c.id, "Not enough points", True)

        user.add_points(-price)

    # SEND FILES
    for f in folder["files"]:
        try:
            bot.copy_message(uid, f["chat"], f["msg"])
            time.sleep(0.3)
        except:
            continue

    bot.answer_callback_query(c.id, "Sent")


# =========================
# BUY METHOD
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy|"))
def buy_method(c):
    uid = c.from_user.id
    user = User(uid)

    _, name, price = c.data.split("|")
    price = int(price)

    if user.purchase_method(name, price):
        bot.answer_callback_query(c.id, "Purchased")
    else:
        bot.answer_callback_query(c.id, "Not enough points")


# =========================
# SERVICES (USER)
# =========================
@bot.message_handler(func=lambda m: m.text == "🛠 SERVICES")
def services_user(m):
    kb = InlineKeyboardMarkup()

    for s in services.all():
        status = "🟢" if s["available"] else "🔴"
        kb.add(InlineKeyboardButton(
            f"{status} {s['name']} ({s['price']} pts)",
            callback_data=f"service|{s['_id']}"
        ))

    bot.send_message(m.chat.id, "Services:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("service|"))
def service_buy(c):
    user = User(c.from_user.id)
    sid = c.data.split("|")[1]
    s = services.get(sid)

    if not s["available"]:
        return bot.answer_callback_query(c.id, "Out of stock")

    if user.points() < s["price"]:
        return bot.answer_callback_query(c.id, "Not enough points")

    user.add_points(-s["price"])
    bot.send_message(c.from_user.id, s["message"])
    bot.answer_callback_query(c.id, "Done")


# =========================
# POINTS
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 POINTS")
def points(m):
    user = User(m.from_user.id)
    bot.send_message(m.chat.id, f"💰 Points: {user.points()}")


# =========================
# REFERRAL
# =========================
@bot.message_handler(func=lambda m: m.text == "🎁 REFERRAL")
def referral(m):
    uid = m.from_user.id
    user = User(uid)

    link = f"https://t.me/{bot.get_me().username}?start={uid}"

    bot.send_message(
        uid,
        f"🎁 Your Link:\n{link}\n\n👥 Referrals: {user.ref_count()}"
    )


# =========================
# ACCOUNT
# =========================
@bot.message_handler(func=lambda m: m.text == "👤 ACCOUNT")
def account(m):
    user = User(m.from_user.id)

    bot.send_message(
        m.chat.id,
        f"Status: {'VIP' if user.is_vip() else 'Free'}\n"
        f"Points: {user.points()}\n"
        f"Referrals: {user.ref_count()}"
    )


# =========================
# MY METHODS
# =========================
@bot.message_handler(func=lambda m: m.text == "📚 MY METHODS")
def my_methods(m):
    user = User(m.from_user.id)

    if user.is_vip():
        return bot.send_message(m.chat.id, "You have all VIP access")

    if not user.data["purchased_methods"]:
        return bot.send_message(m.chat.id, "No methods")

    bot.send_message(
        m.chat.id,
        "\n".join(user.data["purchased_methods"])
    )


# =========================
# CHAT ID
# =========================
@bot.message_handler(func=lambda m: m.text == "🆔 CHAT ID")
def chat_id(m):
    bot.send_message(m.chat.id, f"ID: `{m.from_user.id}`")


# =========================
# REDEEM
# =========================
@bot.message_handler(func=lambda m: m.text == "🏆 REDEEM")
def redeem_start(m):
    msg = bot.send_message(m.chat.id, "Send code:")
    bot.register_next_step_handler(msg, redeem_process)


def redeem_process(m):
    user = User(m.from_user.id)

    ok, res = codesys.redeem(m.text.upper(), user)

    if ok:
        bot.send_message(m.chat.id, f"+{res} points added")
    else:
        bot.send_message(m.chat.id, "Invalid or used code")


# =========================
# GET VIP / GET POINTS
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "get_vip")
def get_vip(c):
    bot.send_message(c.from_user.id, get_config()["vip_msg"])

@bot.callback_query_handler(func=lambda c: c.data == "get_points")
def get_points(c):
    bot.send_message(c.from_user.id, get_config()["purchase_msg"])
    # =========================
# FORCE JOIN RECHECK BUTTON
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "recheck")
def recheck(c):
    uid = c.from_user.id

    if not force_block(uid):
        try:
            bot.edit_message_text(
                "✅ Access Granted!\n\nWelcome to ZEDOX BOT",
                uid,
                c.message.message_id
            )
        except:
            pass

        bot.send_message(uid, "🎉 Welcome!", reply_markup=main_menu(uid))
    else:
        bot.answer_callback_query(c.id, "❌ Join all channels first", show_alert=True)


# =========================
# SAFE FUNCTIONS (ANTI CRASH)
# =========================
def safe_send(uid, text=None, kb=None):
    try:
        bot.send_message(uid, text, reply_markup=kb)
    except Exception as e:
        print(f"[SEND ERROR] {uid}: {e}")


def safe_copy(uid, chat, msg):
    try:
        bot.copy_message(uid, chat, msg)
    except Exception as e:
        print(f"[COPY ERROR] {uid}: {e}")


# =========================
# FALLBACK HANDLER
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
        safe_send(uid, "❌ Please use buttons only", main_menu(uid))


# =========================
# GLOBAL ERROR SAFETY WRAPPER
# =========================
def run_bot():
    while True:
        try:
            print("🚀 ZEDOX BOT RUNNING...")
            print(f"🤖 Bot: @{bot.get_me().username}")
            print(f"👑 Admin: {ADMIN_ID}")

            bot.infinity_polling(timeout=60, long_polling_timeout=60)

        except Exception as e:
            print(f"[CRASH] {e}")
            print("🔄 Restarting in 5 seconds...")
            time.sleep(5)


# =========================
# START BOT (FINAL)
# =========================
if __name__ == "__main__":
    import threading

    threading.Thread(target=run_bot, daemon=True).start()

    # Keep main thread alive
    while True:
        time.sleep(1)
