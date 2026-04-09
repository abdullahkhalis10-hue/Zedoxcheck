import telebot
from telebot.types import *
from pymongo import MongoClient
import os, time, random, string, threading

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = str(os.getenv("ADMIN_ID"))

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# =========================
# 🌐 DATABASE
# =========================
client = MongoClient(os.getenv("MONGO_URI"))
db = client["zedox"]

users_col = db["users"]
folders_col = db["folders"]
codes_col = db["codes"]
config_col = db["config"]

# =========================
# ⚙️ CONFIG SYSTEM (FIXED)
# =========================
def get_config():
    cfg = config_col.find_one({"_id": "config"})
    if not cfg:
        cfg = {
            "_id": "config",
            "vip_price": 100,
            "vip_msg": "💎 Buy VIP to unlock everything!",
            "welcome": "🔥 Welcome to ZEDOX BOT",
            "ref_reward": 5,
            "notify": True,
            "force_channels": [],
            "points_price": 10,  # NEW (points purchase)
            "purchase_msg": "Contact admin to buy points"
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
                "ref": None,
                "refs": 0,
                "purchased": [],
                "used_codes": []
            }
            users_col.insert_one(data)

        self.data = data

    def save(self):
        users_col.update_one({"_id": self.uid}, {"$set": self.data})

    def points(self): return self.data.get("points", 0)
    def is_vip(self): return self.data.get("vip", False)

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

    def add_ref(self):
        self.data["refs"] += 1
        self.save()

    def add_purchase(self, name):
        if name not in self.data["purchased"]:
            self.data["purchased"].append(name)
            self.save()

# =========================
# 📦 FILE SYSTEM (FIXED)
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

fs = FS()

# =========================
# 👑 ADMIN CHECK
# =========================
def is_admin(uid):
    return str(uid) == ADMIN_ID

# =========================
# 🚫 FORCE JOIN
# =========================
def force_block(uid):
    cfg = get_config()

    for ch in cfg["force_channels"]:
        try:
            member = bot.get_chat_member(ch, uid)
            if member.status in ["left", "kicked"]:
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton("Join", url=f"https://t.me/{ch.replace('@','')}"))
                kb.add(InlineKeyboardButton("🔄 I Joined", callback_data="recheck"))

                bot.send_message(uid, "🚫 Join all channels first!", reply_markup=kb)
                return True
        except:
            return True
    return False
    # =========================
# 📱 MAIN MENU (FIXED + COMPLETE)
# =========================
def main_menu(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)

    kb.row("📂 FREE METHODS", "💎 VIP METHODS")
    kb.row("📦 PREMIUM APPS", "⚡ SERVICES")
    kb.row("💰 POINTS", "💳 BUY POINTS")

    kb.row("⭐ BUY VIP", "🎁 REFERRAL")
    kb.row("👤 ACCOUNT", "🆔 CHAT ID", "🏆 COUPON REDEEM")

    kb.row("📚 MY METHODS")

    if is_admin(uid):
        kb.row("⚙️ ADMIN PANEL")

    return kb


# =========================
# 🚀 START + REFERRAL (FIXED)
# =========================
@bot.message_handler(commands=["start"])
def start_cmd(m):
    uid = m.from_user.id
    args = m.text.split()

    user = User(uid)

    # referral FIXED
    if len(args) > 1:
        ref_id = args[1]

        if ref_id != str(uid) and not user.data.get("ref"):
            ref_user = users_col.find_one({"_id": ref_id})

            if ref_user:
                User(ref_id).add_points(get_config()["ref_reward"])
                User(ref_id).add_ref()

                user.data["ref"] = ref_id
                user.save()

    if force_block(uid):
        return

    bot.send_message(uid, get_config()["welcome"], reply_markup=main_menu(uid))


# =========================
# 💳 BUY POINTS (FIXED)
# =========================
@bot.message_handler(func=lambda m: m.text == "💳 BUY POINTS")
def buy_points(m):
    cfg = get_config()

    bot.send_message(m.from_user.id,
        f"💳 **BUY POINTS**\n\n"
        f"Price per unit: **{cfg['points_price']} PKR / point**\n\n"
        f"{cfg['purchase_msg']}",
        parse_mode="Markdown"
    )


# =========================
# 💰 POINTS
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 POINTS")
def points(m):
    user = User(m.from_user.id)
    bot.send_message(m.from_user.id, f"💰 Points: **{user.points()}**", parse_mode="Markdown")


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
# 🎁 REFERRAL
# =========================
@bot.message_handler(func=lambda m: m.text == "🎁 REFERRAL")
def referral(m):
    uid = m.from_user.id
    user = User(uid)

    link = f"https://t.me/{bot.get_me().username}?start={uid}"

    bot.send_message(uid,
        f"🎁 **Referral System**\n\n"
        f"🔗 Link:\n{link}\n\n"
        f"👥 Referrals: **{user.data.get('refs',0)}**\n"
        f"💰 Reward: **{get_config()['ref_reward']} pts**",
        parse_mode="Markdown"
    )


# =========================
# 👤 ACCOUNT
# =========================
@bot.message_handler(func=lambda m: m.text == "👤 ACCOUNT")
def account(m):
    user = User(m.from_user.id)

    bot.send_message(m.from_user.id,
        f"👤 **ACCOUNT**\n\n"
        f"Status: {'💎 VIP' if user.is_vip() else '🆓 FREE'}\n"
        f"Points: **{user.points()}**\n"
        f"Referrals: **{user.data.get('refs',0)}**\n"
        f"Purchased: **{len(user.data.get('purchased',[]))}**",
        parse_mode="Markdown"
    )


# =========================
# 🆔 CHAT ID
# =========================
@bot.message_handler(func=lambda m: m.text == "🆔 CHAT ID")
def chatid(m):
    bot.send_message(m.from_user.id, f"`{m.from_user.id}`", parse_mode="Markdown")


# =========================
# ⚙️ ADMIN PANEL (FULL)
# =========================
def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)

    kb.row("📦 Upload FREE", "💎 Upload VIP")
    kb.row("📱 Upload APPS", "⚡ Upload SERVICES")

    kb.row("🗑 Delete Folder", "✏️ Edit Price")

    kb.row("👑 Add VIP", "👑 Remove VIP")

    kb.row("💰 Give Points", "🔄 Set Points")

    kb.row("🏆 Generate Codes", "📊 Stats")

    kb.row("📢 Broadcast ALL", "📢 VIP", "📢 FREE")

    kb.row("⭐ Set VIP Message", "🏠 Set Welcome Message")
    kb.row("💳 Set Points Price", "💎 Set VIP Price")

    kb.row("➕ Add Force Join", "➖ Remove Force Join")

    kb.row("🔔 Toggle Notify")

    kb.row("❌ Exit Admin")

    return kb


@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def admin_panel(m):
    bot.send_message(m.from_user.id, "⚙️ Admin Panel", reply_markup=admin_menu())


@bot.message_handler(func=lambda m: m.text == "❌ Exit Admin" and is_admin(m.from_user.id))
def exit_admin(m):
    bot.send_message(m.from_user.id, "Exited", reply_markup=main_menu(m.from_user.id))


# =========================
# ⭐ SET VIP MESSAGE (FIXED)
# =========================
@bot.message_handler(func=lambda m: m.text == "⭐ Set VIP Message" and is_admin(m.from_user.id))
def set_vip_msg(m):
    msg = bot.send_message(m.from_user.id, "Send new VIP message:")
    bot.register_next_step_handler(msg, save_vip_msg)

def save_vip_msg(m):
    set_config("vip_msg", m.text)
    bot.send_message(m.from_user.id, "✅ VIP message updated")


# =========================
# 🏠 SET WELCOME MESSAGE (FIXED)
# =========================
@bot.message_handler(func=lambda m: m.text == "🏠 Set Welcome Message" and is_admin(m.from_user.id))
def set_welcome(m):
    msg = bot.send_message(m.from_user.id, "Send new welcome message:")
    bot.register_next_step_handler(msg, save_welcome)

def save_welcome(m):
    set_config("welcome", m.text)
    bot.send_message(m.from_user.id, "✅ Welcome updated")


# =========================
# 💳 SET POINT PRICE (NEW)
# =========================
@bot.message_handler(func=lambda m: m.text == "💳 Set Points Price" and is_admin(m.from_user.id))
def set_points_price(m):
    msg = bot.send_message(m.from_user.id, "Send price per point:")
    bot.register_next_step_handler(msg, save_points_price)

def save_points_price(m):
    set_config("points_price", int(m.text))
    bot.send_message(m.from_user.id, "✅ Points price updated")


# =========================
# 💎 SET VIP PRICE (NEW)
# =========================
@bot.message_handler(func=lambda m: m.text == "💎 Set VIP Price" and is_admin(m.from_user.id))
def set_vip_price(m):
    msg = bot.send_message(m.from_user.id, "Send VIP price:")
    bot.register_next_step_handler(msg, save_vip_price)

def save_vip_price(m):
    set_config("vip_price", int(m.text))
    bot.send_message(m.from_user.id, "✅ VIP price updated")
    # =========================
# 📂 SHOW CATEGORIES
# =========================
@bot.message_handler(func=lambda m: m.text in [
    "📂 FREE METHODS",
    "💎 VIP METHODS",
    "📦 PREMIUM APPS",
    "⚡ SERVICES"
])
def show_categories(m):
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
    data = db_col.find_one({"_id": "data"})[cat]

    if not data:
        bot.send_message(uid, "❌ No content available")
        return

    kb = InlineKeyboardMarkup()

    for name, d in data.items():
        price = d.get("price", 0)
        stock = d.get("stock", True)

        if cat == "services":
            status = "✅" if stock else "❌"
            txt = f"{status} {name} [{price} pts]"
        else:
            txt = f"{name} [{price} pts]" if price > 0 else name

        kb.add(InlineKeyboardButton(txt, callback_data=f"open|{cat}|{name}"))

    bot.send_message(uid, f"📂 {m.text}", reply_markup=kb)


# =========================
# 📂 OPEN FOLDER / SERVICE
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("open|"))
def open_folder(c):
    uid = c.from_user.id
    user = User(uid)

    _, cat, name = c.data.split("|")

    db = db_col.find_one({"_id": "data"})
    folder = db[cat].get(name)

    if not folder:
        bot.answer_callback_query(c.id, "❌ Not found")
        return

    price = folder.get("price", 0)

    # =========================
    # ⚡ SERVICES SYSTEM (FIXED)
    # =========================
    if cat == "services":
        if not folder.get("stock", True):
            bot.answer_callback_query(c.id, "❌ Out of stock", show_alert=True)
            return

        if user.points() < price:
            bot.answer_callback_query(c.id, "❌ Not enough points", show_alert=True)
            return

        user.add_points(-price)

        bot.send_message(uid,
            f"✅ **Service Purchased: {name}**\n\n"
            f"{folder.get('msg','Service will be delivered soon.')}",
            parse_mode="Markdown"
        )
        return

    # =========================
    # 💎 VIP CHECK
    # =========================
    if cat == "vip" and not user.is_vip():
        bot.send_message(uid,
            f"🔒 {get_config()['vip_msg']}",
            parse_mode="Markdown"
        )
        return

    # =========================
    # 💰 PRICE CHECK
    # =========================
    if price > 0 and not user.is_vip():
        if user.points() < price:
            bot.answer_callback_query(c.id, "❌ Not enough points", show_alert=True)
            return

        user.add_points(-price)

    # =========================
    # 📤 SEND FILES (FIXED)
    # =========================
    sent = 0

    for f in folder.get("files", []):
        try:
            bot.copy_message(uid, f["chat"], f["msg"])
            sent += 1
        except:
            continue

    # =========================
    # 💾 SAVE TO MY METHODS (FIXED)
    # =========================
    if cat == "vip" and not user.is_vip():
        user.add_purchase(name)

    # =========================
    # 🔔 NOTIFY
    # =========================
    if get_config()["notify"]:
        bot.send_message(uid, f"✅ Sent {sent} files")


# =========================
# 📚 MY METHODS (BUTTON VIEW)
# =========================
@bot.message_handler(func=lambda m: m.text == "📚 MY METHODS")
def my_methods(m):
    user = User(m.from_user.id)

    if user.is_vip():
        bot.send_message(m.from_user.id, "💎 You have ALL VIP access")
        return

    purchased = user.data.get("purchased", [])

    if not purchased:
        bot.send_message(m.from_user.id, "❌ No purchased methods")
        return

    kb = InlineKeyboardMarkup()

    for name in purchased:
        kb.add(InlineKeyboardButton(name, callback_data=f"open|vip|{name}"))

    bot.send_message(m.from_user.id, "📚 Your Methods:", reply_markup=kb)


# =========================
# 📤 UPLOAD SYSTEM (FIXED FULL)
# =========================
upload_sessions = {}

def start_upload(uid, cat):
    upload_sessions[uid] = {"files": [], "cat": cat}

    bot.send_message(uid,
        f"📤 Send files for {cat}\n\n"
        f"/done = finish\n"
        f"/cancel = cancel"
    )


@bot.message_handler(func=lambda m: m.text == "📦 Upload FREE" and is_admin(m.from_user.id))
def up_free(m): start_upload(m.from_user.id, "free")

@bot.message_handler(func=lambda m: m.text == "💎 Upload VIP" and is_admin(m.from_user.id))
def up_vip(m): start_upload(m.from_user.id, "vip")

@bot.message_handler(func=lambda m: m.text == "📱 Upload APPS" and is_admin(m.from_user.id))
def up_apps(m): start_upload(m.from_user.id, "apps")

@bot.message_handler(func=lambda m: m.text == "⚡ Upload SERVICES" and is_admin(m.from_user.id))
def up_services(m):
    msg = bot.send_message(m.from_user.id, "Service Name:")
    bot.register_next_step_handler(msg, service_name)


def service_name(m):
    name = m.text
    msg = bot.send_message(m.from_user.id, "Price:")
    bot.register_next_step_handler(msg, lambda x: service_price(x, name))


def service_price(m, name):
    price = int(m.text)
    msg = bot.send_message(m.from_user.id, "Message to send to user:")
    bot.register_next_step_handler(msg, lambda x: save_service(x, name, price))


def save_service(m, name, price):
    db = db_col.find_one({"_id": "data"})
    db["services"][name] = {
        "price": price,
        "msg": m.text,
        "stock": True
    }
    db_col.update_one({"_id": "data"}, {"$set": db})

    bot.send_message(m.from_user.id, "✅ Service added")


# =========================
# 📤 HANDLE FILES
# =========================
@bot.message_handler(content_types=['document','photo','video'])
def handle_upload(m):
    uid = m.from_user.id

    if uid not in upload_sessions:
        return

    upload_sessions[uid]["files"].append({
        "chat": m.chat.id,
        "msg": m.message_id
    })

    bot.send_message(uid, f"Saved {len(upload_sessions[uid]['files'])}")


# =========================
# ✅ DONE UPLOAD
# =========================
@bot.message_handler(func=lambda m: m.text == "/done")
def done_upload(m):
    uid = m.from_user.id

    if uid not in upload_sessions:
        return

    data = upload_sessions[uid]

    msg = bot.send_message(uid, "Folder Name:")
    bot.register_next_step_handler(msg, lambda x: save_folder(x, data))


def save_folder(m, data):
    name = m.text

    msg = bot.send_message(m.from_user.id, "Price:")
    bot.register_next_step_handler(msg, lambda x: final_save(x, name, data))


def final_save(m, name, data):
    price = int(m.text)

    db = db_col.find_one({"_id": "data"})
    db[data["cat"]][name] = {
        "files": data["files"],
        "price": price
    }

    db_col.update_one({"_id": "data"}, {"$set": db})

    del upload_sessions[m.from_user.id]

    bot.send_message(m.from_user.id, "✅ Uploaded successfully")
    # =========================
# 🏆 REDEEM SYSTEM (FIXED + MULTI USE)
# =========================
@bot.message_handler(func=lambda m: m.text == "🏆 COUPON REDEEM")
def redeem_start(m):
    msg = bot.send_message(m.from_user.id, "Enter code:")
    bot.register_next_step_handler(msg, redeem_process)


def redeem_process(m):
    code = m.text.strip().upper()
    user = User(m.from_user.id)

    data = codes_col.find_one({"_id": code})

    if not data:
        bot.send_message(m.from_user.id, "❌ Invalid code")
        return

    # one-time or multi-use
    if not data.get("multi", False):
        if data.get("used", False):
            bot.send_message(m.from_user.id, "❌ Already used")
            return

    if str(user.uid) in data.get("users", []):
        bot.send_message(m.from_user.id, "❌ You already used this code")
        return

    pts = data["points"]
    user.add_points(pts)

    codes_col.update_one({"_id": code}, {
        "$set": {"used": True},
        "$addToSet": {"users": str(user.uid)}
    })

    bot.send_message(m.from_user.id, f"✅ +{pts} points added")


# =========================
# 🏆 GENERATE CODES (ADMIN)
# =========================
@bot.message_handler(func=lambda m: m.text == "🏆 Generate Codes" and is_admin(m.from_user.id))
def gen_codes(m):
    msg = bot.send_message(m.from_user.id, "Points per code:")
    bot.register_next_step_handler(msg, gen_count)


def gen_count(m):
    pts = int(m.text)
    msg = bot.send_message(m.from_user.id, "How many codes?")
    bot.register_next_step_handler(msg, lambda x: gen_multi(x, pts))


def gen_multi(m, pts):
    count = int(m.text)
    msg = bot.send_message(m.from_user.id, "Multi-use? (yes/no)")
    bot.register_next_step_handler(msg, lambda x: create_codes(x, pts, count))


def create_codes(m, pts, count):
    multi = m.text.lower() == "yes"

    res = []

    for _ in range(count):
        code = "ZEDOX" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

        codes_col.insert_one({
            "_id": code,
            "points": pts,
            "used": False,
            "multi": multi,
            "users": []
        })

        res.append(code)

    bot.send_message(m.from_user.id, "✅ Codes:\n\n" + "\n".join(res))


# =========================
# 📊 ADVANCED STATS (FULL)
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 Stats" and is_admin(m.from_user.id))
def stats(m):
    users = list(users_col.find({}))

    total = len(users)
    vip = len([u for u in users if u.get("vip")])
    free = total - vip

    total_points = sum(u.get("points", 0) for u in users)
    total_refs = sum(u.get("refs", 0) for u in users)
    total_purchases = sum(len(u.get("purchased", [])) for u in users)

    bot.send_message(m.from_user.id,
        f"📊 **BOT STATS**\n\n"
        f"👥 Total Users: {total}\n"
        f"💎 VIP Users: {vip}\n"
        f"🆓 Free Users: {free}\n\n"
        f"💰 Total Points: {total_points}\n"
        f"🎁 Total Referrals: {total_refs}\n"
        f"📚 Total Purchases: {total_purchases}",
        parse_mode="Markdown"
    )


# =========================
# 📢 BROADCAST SYSTEM
# =========================
@bot.message_handler(func=lambda m: m.text in ["📢 Broadcast ALL","📢 VIP","📢 FREE"] and is_admin(m.from_user.id))
def bc_start(m):
    target = m.text

    msg = bot.send_message(m.from_user.id, "Send message/photo/video:")
    bot.register_next_step_handler(msg, lambda x: bc_send(x, target))


def bc_send(m, target):
    users = list(users_col.find({}))

    sent = 0

    for u in users:
        if target == "📢 VIP" and not u.get("vip"):
            continue
        if target == "📢 FREE" and u.get("vip"):
            continue

        try:
            if m.content_type == "text":
                bot.send_message(u["_id"], m.text)
            elif m.content_type == "photo":
                bot.send_photo(u["_id"], m.photo[-1].file_id, caption=m.caption)
            elif m.content_type == "video":
                bot.send_video(u["_id"], m.video.file_id, caption=m.caption)

            sent += 1
        except:
            continue

    bot.send_message(ADMIN_ID, f"✅ Sent to {sent}")


# =========================
# ➕ FORCE JOIN ADD
# =========================
@bot.message_handler(func=lambda m: m.text == "➕ Add Force Join" and is_admin(m.from_user.id))
def add_force(m):
    msg = bot.send_message(m.from_user.id, "Send channel @username:")
    bot.register_next_step_handler(msg, save_force)


def save_force(m):
    cfg = get_config()
    cfg["force_channels"].append(m.text)
    config_col.update_one({"_id": "config"}, {"$set": cfg})

    bot.send_message(m.from_user.id, "✅ Added")


# =========================
# ➖ REMOVE FORCE JOIN
# =========================
@bot.message_handler(func=lambda m: m.text == "➖ Remove Force Join" and is_admin(m.from_user.id))
def rem_force(m):
    msg = bot.send_message(m.from_user.id, "Send channel:")
    bot.register_next_step_handler(msg, delete_force)


def delete_force(m):
    cfg = get_config()
    cfg["force_channels"].remove(m.text)
    config_col.update_one({"_id": "config"}, {"$set": cfg})

    bot.send_message(m.from_user.id, "Removed")


# =========================
# 🔔 TOGGLE NOTIFICATIONS
# =========================
@bot.message_handler(func=lambda m: m.text == "🔔 Toggle Notify" and is_admin(m.from_user.id))
def toggle_notify(m):
    cfg = get_config()

    cfg["notify"] = not cfg["notify"]

    config_col.update_one({"_id": "config"}, {"$set": cfg})

    bot.send_message(m.from_user.id, f"Notify: {cfg['notify']}")


# =========================
# 🗑 DELETE FOLDER
# =========================
@bot.message_handler(func=lambda m: m.text == "🗑 Delete Folder" and is_admin(m.from_user.id))
def delete_folder(m):
    msg = bot.send_message(m.from_user.id, "Category (free/vip/apps):")
    bot.register_next_step_handler(msg, delete_name)


def delete_name(m):
    cat = m.text
    msg = bot.send_message(m.from_user.id, "Folder name:")
    bot.register_next_step_handler(msg, lambda x: delete_final(x, cat))


def delete_final(m, cat):
    db = db_col.find_one({"_id": "data"})
    del db[cat][m.text]

    db_col.update_one({"_id": "data"}, {"$set": db})

    bot.send_message(m.from_user.id, "Deleted")


# =========================
# ✏️ EDIT PRICE
# =========================
@bot.message_handler(func=lambda m: m.text == "✏️ Edit Price" and is_admin(m.from_user.id))
def edit_price(m):
    msg = bot.send_message(m.from_user.id, "Category:")
    bot.register_next_step_handler(msg, edit_name)


def edit_name(m):
    cat = m.text
    msg = bot.send_message(m.from_user.id, "Folder:")
    bot.register_next_step_handler(msg, lambda x: edit_value(x, cat))


def edit_value(m, cat):
    name = m.text
    msg = bot.send_message(m.from_user.id, "New price:")
    bot.register_next_step_handler(msg, lambda x: edit_save(x, cat, name))


def edit_save(m, cat, name):
    db = db_col.find_one({"_id": "data"})
    db[cat][name]["price"] = int(m.text)

    db_col.update_one({"_id": "data"}, {"$set": db})

    bot.send_message(m.from_user.id, "Updated")


# =========================
# 🚀 RUN BOT (SAFE LOOP)
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
    run()
