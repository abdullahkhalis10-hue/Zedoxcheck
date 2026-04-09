import telebot
from telebot.types import *
from pymongo import MongoClient
import os, time, random, string, threading

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# =========================
# 🌐 MONGODB SETUP
# =========================
client = MongoClient(os.getenv("MONGO_URI"))
db = client["zedox_bot"]

users_col = db["users"]
files_col = db["files"]
codes_col = db["codes"]
config_col = db["config"]

# =========================
# ⚙️ CONFIG
# =========================
def get_config():
    cfg = config_col.find_one({"_id": "config"})
    if not cfg:
        cfg = {
            "_id": "config",
            "vip_price": 100,
            "vip_msg": "💎 Buy VIP",
            "purchase_msg": "💰 Buy points",
            "ref_reward": 5
        }
        config_col.insert_one(cfg)
    return cfg


# =========================
# 👤 USER CLASS
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
                "username": None
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

    def make_vip(self):
        self.data["vip"] = True
        self.save()

    def update_username(self, u):
        self.data["username"] = u
        self.save()

    def add_ref(self):
        self.data["refs"] += 1
        self.save()


# =========================
# 📦 FILE SYSTEM (ALL CATEGORIES)
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
# 👑 ADMIN CHECK (FIXED)
# =========================
def is_admin(uid):
    return str(uid) == str(ADMIN_ID)
    # =========================
# 📋 MAIN MENU (ADMIN FIXED)
# =========================
def main_menu(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)

    kb.row("📂 FREE METHODS", "💎 VIP METHODS")
    kb.row("📦 PREMIUM APPS", "🛠 SERVICES")

    kb.row("💰 POINTS", "⭐ GET VIP")
    kb.row("🎁 REFERRAL", "👤 ACCOUNT")

    if str(uid) == str(ADMIN_ID):  # ✅ FIXED
        kb.row("⚙️ ADMIN PANEL")

    return kb


# =========================
# ⚙️ ADMIN MENU (BUTTON BASED)
# =========================
def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)

    kb.row("📦 Upload FREE", "💎 Upload VIP")
    kb.row("📱 Upload APPS", "🛠 Upload SERVICE")

    kb.row("💰 Set VIP Price", "💎 Set Points Price")
    kb.row("⭐ Set VIP Message", "💬 Set Purchase Msg")

    kb.row("📊 Statistics", "🏆 Generate Codes")

    kb.row("❌ Exit Admin")
    return kb


# =========================
# ⚙️ OPEN ADMIN PANEL
# =========================
@bot.message_handler(func=lambda m: m.text == "⚙️ ADMIN PANEL" and is_admin(m.from_user.id))
def open_admin(m):
    bot.send_message(m.from_user.id, "⚙️ Admin Panel", reply_markup=admin_menu())


@bot.message_handler(func=lambda m: m.text == "❌ Exit Admin")
def exit_admin(m):
    bot.send_message(m.from_user.id, "Exited", reply_markup=main_menu(m.from_user.id))


# =========================
# 📤 UPLOAD SYSTEM (USED FOR ALL)
# =========================
def start_upload(uid, cat):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("/done", "/cancel")

    msg = bot.send_message(uid, f"Upload files for {cat}", reply_markup=kb)
    bot.register_next_step_handler(msg, lambda m: collect_files(m, cat, []))


def collect_files(m, cat, files):
    uid = m.from_user.id

    if m.text == "/cancel":
        bot.send_message(uid, "Cancelled", reply_markup=admin_menu())
        return

    if m.text == "/done":
        msg = bot.send_message(uid, "Folder / Service Name:")
        bot.register_next_step_handler(msg, lambda m2: ask_price(m2, cat, files))
        return

    if m.content_type in ["document", "photo", "video"]:
        files.append({
            "chat": m.chat.id,
            "msg": m.message_id
        })
        bot.send_message(uid, f"Saved {len(files)} file(s)")

    bot.register_next_step_handler(m, lambda m2: collect_files(m2, cat, files))


def ask_price(m, cat, files):
    name = m.text
    msg = bot.send_message(m.from_user.id, "Price (points):")
    bot.register_next_step_handler(msg, lambda m2: save_upload(m2, cat, name, files))


def save_upload(m, cat, name, files):
    price = int(m.text)
    fs.add(cat, name, files, price)
    bot.send_message(m.from_user.id, "✅ Uploaded!", reply_markup=admin_menu())


# =========================
# 📤 ADMIN UPLOAD HANDLERS
# =========================
@bot.message_handler(func=lambda m: m.text == "📦 Upload FREE")
def up_free(m):
    if is_admin(m.from_user.id):
        start_upload(m.from_user.id, "free")


@bot.message_handler(func=lambda m: m.text == "💎 Upload VIP")
def up_vip(m):
    if is_admin(m.from_user.id):
        start_upload(m.from_user.id, "vip")


@bot.message_handler(func=lambda m: m.text == "📱 Upload APPS")
def up_apps(m):
    if is_admin(m.from_user.id):
        start_upload(m.from_user.id, "apps")


@bot.message_handler(func=lambda m: m.text == "🛠 Upload SERVICE")
def up_services(m):
    if is_admin(m.from_user.id):
        start_upload(m.from_user.id, "services")  # ✅ SAME SYSTEM


# =========================
# 💰 SETTINGS SYSTEM (FIXED)
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 Set VIP Price")
def set_vip_price(m):
    if not is_admin(m.from_user.id): return
    msg = bot.send_message(m.from_user.id, "Enter VIP price:")
    bot.register_next_step_handler(msg, save_vip_price)


def save_vip_price(m):
    config_col.update_one({"_id": "config"}, {"$set": {"vip_price": int(m.text)}})
    bot.send_message(m.from_user.id, "✅ VIP price updated")


@bot.message_handler(func=lambda m: m.text == "💎 Set Points Price")
def set_points_price(m):
    if not is_admin(m.from_user.id): return
    msg = bot.send_message(m.from_user.id, "Enter points purchase message:")
    bot.register_next_step_handler(msg, save_points_msg)


def save_points_msg(m):
    config_col.update_one({"_id": "config"}, {"$set": {"purchase_msg": m.text}})
    bot.send_message(m.from_user.id, "✅ Updated")


@bot.message_handler(func=lambda m: m.text == "⭐ Set VIP Message")
def set_vip_msg(m):
    if not is_admin(m.from_user.id): return
    msg = bot.send_message(m.from_user.id, "Send VIP message:")
    bot.register_next_step_handler(msg, save_vip_msg)


def save_vip_msg(m):
    config_col.update_one({"_id": "config"}, {"$set": {"vip_msg": m.text}})
    bot.send_message(m.from_user.id, "✅ VIP message updated")


@bot.message_handler(func=lambda m: m.text == "💬 Set Purchase Msg")
def set_purchase_msg(m):
    if not is_admin(m.from_user.id): return
    msg = bot.send_message(m.from_user.id, "Send purchase message:")
    bot.register_next_step_handler(msg, save_purchase_msg)


def save_purchase_msg(m):
    config_col.update_one({"_id": "config"}, {"$set": {"purchase_msg": m.text}})
    bot.send_message(m.from_user.id, "✅ Purchase message updated")
    # =========================
# 🚀 START (REFERRAL FIXED)
# =========================
@bot.message_handler(commands=["start"])
def start_cmd(m):
    uid = m.from_user.id
    user = User(uid)

    # Save username
    if m.from_user.username:
        user.update_username(m.from_user.username)

    args = m.text.split()

    # ✅ FIXED REFERRAL SYSTEM
    if len(args) > 1:
        ref_id = args[1]

        if ref_id != str(uid):
            ref_user = users_col.find_one({"_id": ref_id})

            if ref_user and not user.data.get("ref"):
                # give reward
                User(ref_id).add_points(get_config()["ref_reward"])
                User(ref_id).add_ref()

                user.data["ref"] = ref_id
                user.save()

    bot.send_message(uid, "🔥 Welcome to ZEDOX BOT", reply_markup=main_menu(uid))


# =========================
# 📂 SHOW FILES (ALL TYPES)
# =========================
def show_category(uid, cat, title):
    kb = InlineKeyboardMarkup()

    items = fs.get(cat)

    if not items:
        bot.send_message(uid, f"{title}\n\nNo items available.")
        return

    for i in items:
        kb.add(InlineKeyboardButton(
            f"{i['name']} ({i['price']} pts)",
            callback_data=f"open|{cat}|{i['name']}"
        ))

    bot.send_message(uid, title, reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "📂 FREE METHODS")
def free(m):
    show_category(m.from_user.id, "free", "📂 FREE METHODS")


@bot.message_handler(func=lambda m: m.text == "💎 VIP METHODS")
def vip(m):
    show_category(m.from_user.id, "vip", "💎 VIP METHODS")


@bot.message_handler(func=lambda m: m.text == "📦 PREMIUM APPS")
def apps(m):
    show_category(m.from_user.id, "apps", "📦 PREMIUM APPS")


@bot.message_handler(func=lambda m: m.text == "🛠 SERVICES")
def services_ui(m):
    show_category(m.from_user.id, "services", "🛠 SERVICES")


# =========================
# 📂 OPEN ITEM (BUY + SEND)
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("open|"))
def open_item(c):
    uid = c.from_user.id
    user = User(uid)

    _, cat, name = c.data.split("|")
    item = fs.get_one(cat, name)

    if not item:
        bot.answer_callback_query(c.id, "Not found")
        return

    price = item["price"]

    # 💎 VIP LOGIC
    if cat == "vip" and not user.is_vip():
        cfg = get_config()

        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("⭐ GET VIP", callback_data="getvip"))

        bot.send_message(uid, f"🔒 VIP ONLY\n\n{cfg['vip_msg']}", reply_markup=kb)
        return

    # 💰 POINTS CHECK
    if price > 0:
        if user.points() < price:
            bot.answer_callback_query(c.id, "Not enough points", True)
            return

        user.add_points(-price)

    # 📥 SEND FILES
    for f in item["files"]:
        bot.copy_message(uid, f["chat"], f["msg"])

    # 📚 SAVE PURCHASE
    if name not in user.data["purchased"]:
        user.data["purchased"].append(name)
        user.save()

    bot.answer_callback_query(c.id, "✅ Delivered!")


# =========================
# ⭐ GET VIP (FIXED MESSAGE)
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "getvip")
def getvip(c):
    cfg = get_config()
    bot.send_message(
        c.from_user.id,
        f"💎 VIP PRICE: {cfg['vip_price']} pts\n\n{cfg['vip_msg']}"
    )


# =========================
# 💰 POINTS
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 POINTS")
def points(m):
    user = User(m.from_user.id)
    bot.send_message(m.from_user.id, f"💰 Points: {user.points()}")


# =========================
# 🎁 REFERRAL (FIXED COUNT)
# =========================
@bot.message_handler(func=lambda m: m.text == "🎁 REFERRAL")
def referral(m):
    uid = m.from_user.id
    user = User(uid)

    link = f"https://t.me/{bot.get_me().username}?start={uid}"

    bot.send_message(
        uid,
        f"🔗 Link:\n{link}\n\n👥 Referrals: {user.data.get('refs',0)}"
    )


# =========================
# 👤 ACCOUNT
# =========================
@bot.message_handler(func=lambda m: m.text == "👤 ACCOUNT")
def account(m):
    user = User(m.from_user.id)

    bot.send_message(
        m.from_user.id,
        f"👤 ACCOUNT\n\n"
        f"💰 Points: {user.points()}\n"
        f"💎 VIP: {user.is_vip()}\n"
        f"📚 Purchased: {len(user.data.get('purchased',[]))}\n"
        f"👥 Referrals: {user.data.get('refs',0)}"
    )


# =========================
# 📚 MY METHODS (BUTTONS)
# =========================
@bot.message_handler(func=lambda m: m.text == "📚 MY METHODS")
def my_methods(m):
    user = User(m.from_user.id)

    kb = InlineKeyboardMarkup()

    for name in user.data.get("purchased", []):
        kb.add(InlineKeyboardButton(name, callback_data=f"my|{name}"))

    if not user.data.get("purchased"):
        bot.send_message(m.from_user.id, "No methods purchased")
        return

    bot.send_message(m.from_user.id, "📚 Your Methods:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("my|"))
def open_my(c):
    uid = c.from_user.id
    name = c.data.split("|")[1]

    item = files_col.find_one({"name": name})

    if not item:
        return

    for f in item["files"]:
        bot.copy_message(uid, f["chat"], f["msg"])
        # =========================
# 🎫 CODES SYSTEM (SECURE)
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

        # mark used
        codes_col.update_one(
            {"_id": code},
            {"$set": {
                "used": True,
                "used_by": user.uid,
                "used_at": time.time()
            }}
        )

        user.add_points(data["points"])
        return True, data["points"]


codesys = Codes()


# =========================
# 🏆 ADMIN GENERATE CODES
# =========================
@bot.message_handler(func=lambda m: m.text == "🏆 Generate Codes" and is_admin(m.from_user.id))
def gen_codes(m):
    msg = bot.send_message(m.from_user.id, "Points per code:")
    bot.register_next_step_handler(msg, gen_count)


def gen_count(m):
    pts = int(m.text)
    msg = bot.send_message(m.from_user.id, "How many codes?")
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
    msg = bot.send_message(m.from_user.id, "Enter your code:")
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
            bot.send_message(m.from_user.id, "❌ Code already used")


# =========================
# 📊 ADVANCED STATISTICS (FULL)
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 Statistics" and is_admin(m.from_user.id))
def stats(m):
    total_users = users_col.count_documents({})
    vip_users = users_col.count_documents({"vip": True})
    free_users = total_users - vip_users

    total_points = sum(u.get("points", 0) for u in users_col.find())
    total_refs = sum(u.get("refs", 0) for u in users_col.find())
    total_purchased = sum(len(u.get("purchased", [])) for u in users_col.find())

    text = (
        f"📊 BOT STATISTICS\n\n"
        f"👥 Total Users: {total_users}\n"
        f"💎 VIP Users: {vip_users}\n"
        f"🆓 Free Users: {free_users}\n\n"
        f"💰 Total Points: {total_points}\n"
        f"👥 Total Referrals: {total_refs}\n"
        f"📚 Methods Purchased: {total_purchased}\n"
    )

    bot.send_message(m.from_user.id, text)


# =========================
# 🔄 SAFE SEND
# =========================
def safe_send(uid, text):
    try:
        bot.send_message(uid, text)
    except Exception as e:
        print("SEND ERROR:", e)


# =========================
# ⚠️ FALLBACK
# =========================
@bot.message_handler(content_types=['text'])
def fallback(m):
    known = [
        "📂 FREE METHODS", "💎 VIP METHODS",
        "📦 PREMIUM APPS", "🛠 SERVICES",
        "💰 POINTS", "⭐ GET VIP",
        "🎁 REFERRAL", "👤 ACCOUNT",
        "📚 MY METHODS", "🏆 REDEEM",
        "⚙️ ADMIN PANEL"
    ]

    if m.text not in known:
        safe_send(m.from_user.id, "❌ Use menu buttons only")


# =========================
# 🔁 AUTO RESTART
# =========================
def run_bot():
    while True:
        try:
            print("🚀 BOT RUNNING...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)

        except Exception as e:
            print("ERROR:", e)
            time.sleep(5)


# =========================
# 🚀 START BOT
# =========================
if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()

    while True:
        time.sleep(1)
