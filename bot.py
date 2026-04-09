import telebot
from telebot.types import *
from pymongo import MongoClient
import os, time, random, string, threading

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = str(os.getenv("ADMIN_ID"))

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# =========================
# 🌐 MONGODB SETUP
# =========================
client = MongoClient(os.getenv("MONGO_URI"))
db = client["zedox"]

users_col = db["users"]
db_col = db["folders"]
codes_col = db["codes"]
config_col = db["config"]

# =========================
# ⚙️ CONFIG SYSTEM
# =========================
def get_config():
    cfg = config_col.find_one({"_id": "config"})
    if not cfg:
        cfg = {
            "_id": "config",
            "vip_price": 100,
            "vip_msg": "💎 Buy VIP to unlock all features!",
            "welcome": "🔥 Welcome to Zedox Bot",
            "ref_reward": 5,
            "notify": True,
            "force_channels": [],
            "purchase_msg": "💰 Contact admin to buy points!"
        }
        config_col.insert_one(cfg)
    return cfg

def set_config(key, value):
    config_col.update_one({"_id": "config"}, {"$set": {key: value}}, upsert=True)


# =========================
# 👤 USER SYSTEM
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
                "vip_expiry": None,
                "ref": None,
                "refs": 0,
                "purchased": [],
                "used_codes": [],
                "username": None
            }
            users_col.insert_one(data)

        self.data = data

    def save(self):
        users_col.update_one({"_id": self.uid}, {"$set": self.data})

    def points(self): return self.data.get("points", 0)

    def is_vip(self):
        expiry = self.data.get("vip_expiry")
        if expiry and time.time() > expiry:
            self.data["vip"] = False
            self.data["vip_expiry"] = None
            self.save()
        return self.data.get("vip", False)

    def add_points(self, p):
        self.data["points"] += p
        self.save()

    def set_points(self, p):
        self.data["points"] = p
        self.save()

    def make_vip(self, days=None):
        self.data["vip"] = True
        if days:
            self.data["vip_expiry"] = time.time() + (days * 86400)
        self.save()

    def remove_vip(self):
        self.data["vip"] = False
        self.data["vip_expiry"] = None
        self.save()

    def update_username(self, u):
        self.data["username"] = u
        self.save()

    def add_ref(self):
        self.data["refs"] += 1
        self.save()

    def add_purchase(self, name):
        if name not in self.data["purchased"]:
            self.data["purchased"].append(name)
            self.save()

    def used_code(self, code):
        return code in self.data.get("used_codes", [])

    def add_code(self, code):
        self.data.setdefault("used_codes", []).append(code)
        self.save()


# =========================
# 📦 CONTENT SYSTEM (WITH SUBFOLDERS SUPPORT)
# =========================
class FS:
    def add(self, cat, name, files, price, parent=None):
        db_col.insert_one({
            "cat": cat,
            "name": name,
            "files": files,
            "price": price,
            "parent": parent  # for subfolders
        })

    def get(self, cat, parent=None):
        return list(db_col.find({"cat": cat, "parent": parent}))

    def get_one(self, cat, name):
        return db_col.find_one({"cat": cat, "name": name})

    def delete(self, cat, name):
        db_col.delete_one({"cat": cat, "name": name})

    def edit_price(self, cat, name, price):
        db_col.update_one({"cat": cat, "name": name}, {"$set": {"price": price}})

    def edit_name(self, cat, old, new):
        db_col.update_one({"cat": cat, "name": old}, {"$set": {"name": new}})

fs = FS()


# =========================
# 👑 ADMIN CHECK
# =========================
def is_admin(uid):
    return str(uid) == ADMIN_ID


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

                bot.send_message(uid, "🚫 ACCESS DENIED! Join all channels", reply_markup=kb)
                return True
        except:
            return True
    return False
    # =========================
# 📱 MAIN MENU (EXACT UI)
# =========================
def main_menu(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)

    kb.row("📂 FREE METHODS", "💎 VIP METHODS")
    kb.row("📦 PREMIUM APPS", "⚡ SERVICES")
    kb.row("💰 POINTS")

    kb.row("⭐ BUY VIP", "🎁 REFERRAL")
    kb.row("👤 ACCOUNT", "🆔 CHAT ID", "🏆 COUPON REDEEM")

    if is_admin(uid):
        kb.row("⚙️ ADMIN PANEL")

    return kb


# =========================
# 🚀 START + REFERRAL FIXED
# =========================
@bot.message_handler(commands=["start"])
def start_cmd(m):
    uid = m.from_user.id
    args = m.text.split()

    user = User(uid)

    # update username
    if m.from_user.username:
        user.update_username(m.from_user.username)

    # referral system (FIXED)
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

    bot.send_message(uid, get_config()["welcome"], reply_markup=main_menu(uid))


# =========================
# 🎁 REFERRAL COMMAND
# =========================
@bot.message_handler(func=lambda m: m.text == "🎁 REFERRAL")
def referral(m):
    uid = m.from_user.id
    user = User(uid)

    link = f"https://t.me/{bot.get_me().username}?start={uid}"

    bot.send_message(uid,
        f"🎁 **Referral System**\n\n"
        f"🔗 Link:\n{link}\n\n"
        f"👥 Total Referrals: **{user.data.get('refs',0)}**\n"
        f"💰 Reward per referral: **{get_config()['ref_reward']} pts**",
        parse_mode="Markdown"
    )


# =========================
# 💰 POINTS
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 POINTS")
def points(m):
    user = User(m.from_user.id)
    bot.send_message(m.from_user.id,
        f"💰 Your Points: **{user.points()}**",
        parse_mode="Markdown"
    )


# =========================
# 👤 ACCOUNT
# =========================
@bot.message_handler(func=lambda m: m.text == "👤 ACCOUNT")
def account(m):
    user = User(m.from_user.id)

    status = "💎 VIP" if user.is_vip() else "🆓 FREE"

    bot.send_message(m.from_user.id,
        f"👤 **ACCOUNT INFO**\n\n"
        f"Status: {status}\n"
        f"Points: **{user.points()}**\n"
        f"Referrals: **{user.data.get('refs',0)}**\n"
        f"Purchased: **{len(user.data.get('purchased',[]))}**",
        parse_mode="Markdown"
    )


# =========================
# 🆔 CHAT ID
# =========================
@bot.message_handler(func=lambda m: m.text == "🆔 CHAT ID")
def chat_id(m):
    bot.send_message(m.from_user.id, f"`{m.from_user.id}`", parse_mode="Markdown")


# =========================
# ⭐ BUY VIP (FIXED MESSAGE)
# =========================
@bot.message_handler(func=lambda m: m.text == "⭐ BUY VIP")
def buy_vip(m):
    cfg = get_config()

    bot.send_message(m.from_user.id,
        f"💎 **VIP MEMBERSHIP**\n\n"
        f"{cfg['vip_msg']}\n\n"
        f"💰 Price: **{cfg['vip_price']} points**",
        parse_mode="Markdown"
    )


# =========================
# ⚙️ ADMIN PANEL (FULL BUTTONS)
# =========================
def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)

    kb.row("📦 Upload FREE", "💎 Upload VIP")
    kb.row("📱 Upload APPS", "⚡ Upload SERVICES")

    kb.row("🗑 Delete Folder", "✏️ Edit Price")
    kb.row("✏️ Edit Name")

    kb.row("👑 Add VIP", "👑 Remove VIP")

    kb.row("💰 Give Points", "🔄 Set Points")

    kb.row("🏆 Generate Codes", "📊 Stats")

    kb.row("📢 Broadcast ALL", "📢 VIP", "📢 FREE")

    kb.row("⭐ Set VIP Msg", "🏠 Set Welcome")

    kb.row("➕ Add Force Join", "➖ Remove Force Join")

    kb.row("🔔 Toggle Notify")

    kb.row("❌ Exit Admin")

    return kb


@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def open_admin(m):
    bot.send_message(m.from_user.id, "⚙️ ADMIN PANEL", reply_markup=admin_menu())


@bot.message_handler(func=lambda m: m.text == "❌ Exit Admin" and is_admin(m.from_user.id))
def exit_admin(m):
    bot.send_message(m.from_user.id, "Exited", reply_markup=main_menu(m.from_user.id))


# =========================
# 👑 VIP CONTROL
# =========================
@bot.message_handler(func=lambda m: m.text == "👑 Add VIP" and is_admin(m.from_user.id))
def add_vip(m):
    msg = bot.send_message(m.from_user.id, "Send user ID:")
    bot.register_next_step_handler(msg, add_vip2)

def add_vip2(m):
    user = User(m.text)
    user.make_vip()
    bot.send_message(m.from_user.id, "✅ VIP added")


@bot.message_handler(func=lambda m: m.text == "👑 Remove VIP" and is_admin(m.from_user.id))
def rem_vip(m):
    msg = bot.send_message(m.from_user.id, "Send user ID:")
    bot.register_next_step_handler(msg, rem_vip2)

def rem_vip2(m):
    user = User(m.text)
    user.remove_vip()
    bot.send_message(m.from_user.id, "❌ VIP removed")


# =========================
# 💰 POINT ADMIN
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 Give Points" and is_admin(m.from_user.id))
def give_points(m):
    msg = bot.send_message(m.from_user.id, "Send: user_id points")
    bot.register_next_step_handler(msg, give_points2)

def give_points2(m):
    uid, pts = m.text.split()
    User(uid).add_points(int(pts))
    bot.send_message(m.from_user.id, "✅ Points added")


@bot.message_handler(func=lambda m: m.text == "🔄 Set Points" and is_admin(m.from_user.id))
def set_points(m):
    msg = bot.send_message(m.from_user.id, "Send: user_id points")
    bot.register_next_step_handler(msg, set_points2)

def set_points2(m):
    uid, pts = m.text.split()
    User(uid).set_points(int(pts))
    bot.send_message(m.from_user.id, "✅ Points set")


# =========================
# 📢 BROADCAST SYSTEM
# =========================
def broadcast(target, msg):
    users = list(users_col.find())
    sent = 0

    for u in users:
        uid = int(u["_id"])

        if target == "vip" and not u.get("vip"): continue
        if target == "free" and u.get("vip"): continue

        try:
            bot.copy_message(uid, msg.chat.id, msg.message_id)
            sent += 1
        except:
            continue

    bot.send_message(ADMIN_ID, f"✅ Sent to {sent} users")


@bot.message_handler(func=lambda m: m.text == "📢 Broadcast ALL" and is_admin(m.from_user.id))
def bc_all(m):
    msg = bot.send_message(m.from_user.id, "Send message")
    bot.register_next_step_handler(msg, lambda x: broadcast("all", x))


@bot.message_handler(func=lambda m: m.text == "📢 VIP" and is_admin(m.from_user.id))
def bc_vip(m):
    msg = bot.send_message(m.from_user.id, "Send message")
    bot.register_next_step_handler(msg, lambda x: broadcast("vip", x))


@bot.message_handler(func=lambda m: m.text == "📢 FREE" and is_admin(m.from_user.id))
def bc_free(m):
    msg = bot.send_message(m.from_user.id, "Send message")
    bot.register_next_step_handler(msg, lambda x: broadcast("free", x))
    # =========================
# 📂 SHOW FOLDERS (ALL TYPES)
# =========================
def get_folders_kb(cat, parent=None):
    data = fs.get(cat, parent)

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

    cat = mapping[m.text]

    data = fs.get(cat)

    if not data:
        bot.send_message(uid, "❌ No content yet")
        return

    bot.send_message(uid, "📂 Select:", reply_markup=get_folders_kb(cat))


# =========================
# 📂 OPEN FOLDER / SERVICE
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("open|"))
def open_folder(c):
    uid = c.from_user.id
    user = User(uid)

    _, cat, name = c.data.split("|")

    folder = fs.get_one(cat, name)

    if not folder:
        bot.answer_callback_query(c.id, "❌ Not found")
        return

    price = folder.get("price", 0)

    # ================= VIP LOGIC =================
    if cat == "vip" and not user.is_vip():
        bot.send_message(uid,
            f"🔒 VIP ONLY\n\n{get_config()['vip_msg']}",
            parse_mode="Markdown"
        )
        return

    # ================= PAYMENT LOGIC =================
    if not user.is_vip() and price > 0:
        if user.points() < price:
            bot.answer_callback_query(c.id, "❌ Not enough points", show_alert=True)
            return

        user.set_points(user.points() - price)

    # ================= SERVICES SYSTEM =================
    if cat == "services":
        # services don't send files, send custom message
        service_msg = folder.get("service_msg", "✅ Service activated!")

        bot.send_message(uid, service_msg, parse_mode="Markdown")
        return

    # ================= SEND FILES =================
    count = 0

    for f in folder["files"]:
        try:
            bot.copy_message(uid, f["chat"], f["msg"])
            count += 1
            time.sleep(0.3)
        except:
            continue

    # save purchased
    user.add_purchase(name)

    # notification
    if get_config().get("notify", True):
        bot.send_message(uid, f"✅ Sent {count} files")


# =========================
# 📤 UPLOAD SYSTEM (ALL TYPES)
# =========================
def start_upload(uid, cat):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("/done", "/cancel")

    msg = bot.send_message(uid, f"Send files for {cat}", reply_markup=kb)
    bot.register_next_step_handler(msg, lambda m: upload_step(m, cat, []))


def upload_step(m, cat, files):
    uid = m.from_user.id

    if m.text == "/cancel":
        bot.send_message(uid, "❌ Cancelled", reply_markup=admin_menu())
        return

    if m.text == "/done":
        if not files:
            bot.send_message(uid, "No files")
            return

        msg = bot.send_message(uid, "Folder name:")
        bot.register_next_step_handler(msg, lambda x: upload_name(x, cat, files))
        return

    if m.content_type in ["document", "photo", "video"]:
        files.append({
            "chat": m.chat.id,
            "msg": m.message_id
        })
        bot.send_message(uid, f"Saved {len(files)}")

    bot.register_next_step_handler(m, lambda x: upload_step(x, cat, files))


def upload_name(m, cat, files):
    name = m.text

    msg = bot.send_message(m.from_user.id, "Price:")
    bot.register_next_step_handler(msg, lambda x: upload_save(x, cat, name, files))


def upload_save(m, cat, name, files):
    try:
        price = int(m.text)

        fs.add(cat, name, files, price)

        bot.send_message(m.from_user.id, "✅ Uploaded", reply_markup=admin_menu())
    except:
        bot.send_message(m.from_user.id, "❌ Error")


# =========================
# ⚡ SERVICES UPLOAD (SPECIAL)
# =========================
@bot.message_handler(func=lambda m: m.text == "⚡ Upload SERVICES" and is_admin(m.from_user.id))
def upload_service(m):
    msg = bot.send_message(m.from_user.id, "Service name:")
    bot.register_next_step_handler(msg, service_name)


def service_name(m):
    name = m.text

    msg = bot.send_message(m.from_user.id, "Price:")
    bot.register_next_step_handler(msg, lambda x: service_price(x, name))


def service_price(m, name):
    price = int(m.text)

    msg = bot.send_message(m.from_user.id, "Service message:")
    bot.register_next_step_handler(msg, lambda x: service_save(x, name, price))


def service_save(m, name, price):
    db_col.insert_one({
        "cat": "services",
        "name": name,
        "files": [],
        "price": price,
        "service_msg": m.text
    })

    bot.send_message(m.from_user.id, "✅ Service added")


# =========================
# 🗑 DELETE
# =========================
@bot.message_handler(func=lambda m: m.text == "🗑 Delete Folder" and is_admin(m.from_user.id))
def del_folder(m):
    msg = bot.send_message(m.from_user.id, "Send: category name")
    bot.register_next_step_handler(msg, del2)

def del2(m):
    cat, name = m.text.split(maxsplit=1)
    fs.delete(cat, name)
    bot.send_message(m.from_user.id, "Deleted")


# =========================
# ✏️ EDIT PRICE
# =========================
@bot.message_handler(func=lambda m: m.text == "✏️ Edit Price" and is_admin(m.from_user.id))
def edit_price(m):
    msg = bot.send_message(m.from_user.id, "Send: cat name price")
    bot.register_next_step_handler(msg, edit_price2)

def edit_price2(m):
    cat, name, price = m.text.split(maxsplit=2)
    fs.edit_price(cat, name, int(price))
    bot.send_message(m.from_user.id, "Updated")


# =========================
# ✏️ EDIT NAME
# =========================
@bot.message_handler(func=lambda m: m.text == "✏️ Edit Name" and is_admin(m.from_user.id))
def edit_name(m):
    msg = bot.send_message(m.from_user.id, "Send: cat old new")
    bot.register_next_step_handler(msg, edit_name2)

def edit_name2(m):
    cat, old, new = m.text.split(maxsplit=2)
    fs.edit_name(cat, old, new)
    bot.send_message(m.from_user.id, "Renamed")
    # =========================
# 🏆 REDEEM CODES SYSTEM
# =========================
class Codes:
    def generate(self, pts, count, multi_use=False):
        res = []
        for _ in range(count):
            code = "ZEDOX" + ''.join(random.choices(string.ascii_uppercase+string.digits, k=6))

            codes_col.insert_one({
                "_id": code,
                "points": pts,
                "multi": multi_use,
                "used_by": []
            })
            res.append(code)
        return res

    def redeem(self, code, user):
        data = codes_col.find_one({"_id": code})

        if not data:
            return False, "invalid"

        if not data["multi"] and data["used_by"]:
            return False, "used"

        if user.uid in data["used_by"]:
            return False, "already"

        user.add_points(data["points"])

        codes_col.update_one(
            {"_id": code},
            {"$push": {"used_by": user.uid}}
        )

        user.add_code(code)

        return True, data["points"]


codesys = Codes()


# =========================
# 🏆 ADMIN GENERATE CODES
# =========================
@bot.message_handler(func=lambda m: m.text == "🏆 Generate Codes" and is_admin(m.from_user.id))
def gen_codes(m):
    msg = bot.send_message(m.from_user.id, "Send: points count multi(yes/no)")
    bot.register_next_step_handler(msg, gen_codes2)

def gen_codes2(m):
    pts, count, multi = m.text.split()
    multi = True if multi.lower() == "yes" else False

    codes = codesys.generate(int(pts), int(count), multi)

    bot.send_message(m.from_user.id,
        "```\n" + "\n".join(codes) + "\n```",
        parse_mode="Markdown"
    )


# =========================
# 🏆 USER REDEEM
# =========================
@bot.message_handler(func=lambda m: m.text == "🏆 COUPON REDEEM")
def redeem_start(m):
    msg = bot.send_message(m.from_user.id, "Enter code:")
    bot.register_next_step_handler(msg, redeem2)

def redeem2(m):
    user = User(m.from_user.id)
    ok, res = codesys.redeem(m.text.upper(), user)

    if ok:
        bot.send_message(m.from_user.id, f"✅ +{res} points")
    else:
        bot.send_message(m.from_user.id, f"❌ {res}")


# =========================
# 📊 FULL STATISTICS (ADVANCED)
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 Stats" and is_admin(m.from_user.id))
def stats(m):
    users = list(users_col.find())

    total = len(users)
    vip = sum(1 for u in users if u.get("vip"))
    free = total - vip

    total_points = sum(u.get("points", 0) for u in users)
    total_refs = sum(u.get("refs", 0) for u in users)
    total_purchases = sum(len(u.get("purchased", [])) for u in users)

    bot.send_message(m.from_user.id,
        f"📊 **FULL STATS**\n\n"
        f"👥 Users: {total}\n"
        f"💎 VIP: {vip}\n"
        f"🆓 Free: {free}\n\n"
        f"💰 Total Points: {total_points}\n"
        f"🎁 Total Referrals: {total_refs}\n"
        f"📦 Purchases: {total_purchases}",
        parse_mode="Markdown"
    )


# =========================
# ➕ FORCE JOIN ADD
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ Add Force Join" and is_admin(m.from_user.id))
def add_force(m):
    msg = bot.send_message(m.from_user.id, "Send @channel")
    bot.register_next_step_handler(msg, add_force2)

def add_force2(m):
    cfg = get_config()
    chs = cfg.get("force_channels", [])

    if m.text not in chs:
        chs.append(m.text)
        set_config("force_channels", chs)

    bot.send_message(m.from_user.id, "Added")


# =========================
# ➖ FORCE JOIN REMOVE
# =========================
@bot.message_handler(func=lambda m: m.text == "➖ Remove Force Join" and is_admin(m.from_user.id))
def rem_force(m):
    msg = bot.send_message(m.from_user.id, "Send @channel")
    bot.register_next_step_handler(msg, rem_force2)

def rem_force2(m):
    cfg = get_config()
    chs = cfg.get("force_channels", [])

    if m.text in chs:
        chs.remove(m.text)
        set_config("force_channels", chs)

    bot.send_message(m.from_user.id, "Removed")


# =========================
# 🔄 RECHECK JOIN
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "recheck")
def recheck(c):
    if not force_block(c.from_user.id):
        bot.send_message(c.from_user.id, "✅ Access granted", reply_markup=main_menu(c.from_user.id))
    else:
        bot.answer_callback_query(c.id, "Still not joined", show_alert=True)


# =========================
# 🔔 TOGGLE NOTIFICATION
# =========================
@bot.message_handler(func=lambda m: m.text == "🔔 Toggle Notify" and is_admin(m.from_user.id))
def toggle_notify(m):
    cfg = get_config()
    state = not cfg.get("notify", True)
    set_config("notify", state)

    bot.send_message(m.from_user.id, f"Notify: {state}")


# =========================
# 📚 MY METHODS (BUTTONS)
# =========================
@bot.message_handler(func=lambda m: m.text == "📚 MY METHODS")
def my_methods(m):
    user = User(m.from_user.id)

    if not user.data.get("purchased"):
        bot.send_message(m.from_user.id, "No purchases")
        return

    kb = InlineKeyboardMarkup()

    for name in user.data["purchased"]:
        kb.add(InlineKeyboardButton(name, callback_data=f"open|vip|{name}"))

    bot.send_message(m.from_user.id, "📚 Your Methods:", reply_markup=kb)


# =========================
# 🧠 SAFE FALLBACK
# =========================
@bot.message_handler(func=lambda m: True)
def fallback(m):
    if force_block(m.from_user.id):
        return

    bot.send_message(m.from_user.id, "❌ Use menu buttons", reply_markup=main_menu(m.from_user.id))


# =========================
# 🚀 RUN BOT
# =========================
def run():
    while True:
        try:
            print("🚀 ZEDOX RUNNING...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print("Error:", e)
            time.sleep(5)


if __name__ == "__main__":
    threading.Thread(target=run).start()

    while True:
        time.sleep(1)
