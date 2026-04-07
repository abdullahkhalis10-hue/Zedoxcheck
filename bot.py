# =========================
# ZEDOX BOT - PART 1 (MONGODB VERSION)
# Core Setup + MongoDB + User System
# =========================

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
import os, time, random, string, threading
from pymongo import MongoClient

# =========================
# CONFIG
# =========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
MONGO_URI = os.environ.get("MONGO_URI")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# =========================
# MONGODB CONNECTION
# =========================
client = MongoClient(MONGO_URI)
db = client["zedox_bot"]

users_col = db["users"]
methods_col = db["methods"]
config_col = db["config"]
codes_col = db["codes"]

# =========================
# INIT DEFAULT CONFIG
# =========================
def init_config():
    if config_col.count_documents({}) == 0:
        config_col.insert_one({
            "force_channels": [],
            "vip_msg": "💎 Buy VIP to unlock this!",
            "welcome": "🔥 Welcome to ZEDOX BOT",
            "ref_reward": 5,
            "notify": True,
            "purchase_msg": "💰 Purchase VIP to access premium features!",
            "buttons": [],  # extra buttons on main page
            "optional_links": []  # non-force join buttons
        })

init_config()

def get_config():
    return config_col.find_one()

def update_config(data):
    config_col.update_one({}, {"$set": data})

# =========================
# USER CLASS (MONGODB)
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
                "username": None,
                "purchased": [],
                "used_codes": [],
                "ref_count": 0
            }
            users_col.insert_one(self.data)

    def refresh(self):
        self.data = users_col.find_one({"_id": self.uid})

    def save(self):
        users_col.update_one({"_id": self.uid}, {"$set": self.data})

    def update_username(self, username):
        if username and username != self.data.get("username"):
            self.data["username"] = username
            self.save()

    def is_vip(self):
        return self.data.get("vip", False)

    def points(self):
        return self.data.get("points", 0)

    def add_points(self, pts):
        self.data["points"] += pts
        self.save()

    def deduct_points(self, pts):
        self.data["points"] -= pts
        self.save()

    def make_vip(self):
        self.data["vip"] = True
        self.save()

    def remove_vip(self):
        self.data["vip"] = False
        self.save()

    def purchase(self, method):
        if method not in self.data["purchased"]:
            self.data["purchased"].append(method)
            self.save()

    def has_method(self, method):
        return method in self.data.get("purchased", [])

    def add_used_code(self, code):
        if code not in self.data["used_codes"]:
            self.data["used_codes"].append(code)
            self.save()

    def has_used_code(self, code):
        return code in self.data.get("used_codes", [])

# =========================
# STRONG REFERRAL SYSTEM
# =========================
def handle_referral(user, ref_id):
    if user.data["ref"]:
        return

    if ref_id == user.uid:
        return

    ref_user = users_col.find_one({"_id": ref_id})
    if not ref_user:
        return

    reward = get_config().get("ref_reward", 5)

    users_col.update_one({"_id": ref_id}, {
        "$inc": {
            "points": reward,
            "ref_count": 1
        }
    })

    user.data["ref"] = ref_id
    user.save()

# =========================
# CODES SYSTEM (MONGODB)
# =========================
class Codes:
    def generate(self, pts, count):
        res = []
        for _ in range(count):
            code = "ZEDOX" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            codes_col.insert_one({
                "_id": code,
                "points": pts,
                "used": False,
                "used_by": None
            })
            res.append(code)
        return res

    def redeem(self, code, user):
        data = codes_col.find_one({"_id": code})

        if not data:
            return False, "invalid"

        if data["used"]:
            return False, "used"

        if user.has_used_code(code):
            return False, "already"

        pts = data["points"]
        user.add_points(pts)

        codes_col.update_one({"_id": code}, {
            "$set": {
                "used": True,
                "used_by": user.uid,
                "used_at": time.time()
            }
        })

        user.add_used_code(code)

        return True, pts

codesys = Codes()

# =========================
# FORCE JOIN
# =========================
def force_block(uid):
    cfg = get_config()

    for ch in cfg.get("force_channels", []):
        try:
            m = bot.get_chat_member(ch, uid)
            if m.status in ["left", "kicked"]:
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton("Join Channel", url=f"https://t.me/{ch.replace('@','')}"))
                kb.add(InlineKeyboardButton("🔄 I Joined", callback_data="recheck"))

                bot.send_message(uid, "🚫 Join all channels first!", reply_markup=kb)
                return True
        except:
            return True
    return False

# =========================
# OPTIONAL BUTTONS (NOT FORCE JOIN)
# =========================
def optional_buttons():
    cfg = get_config()
    kb = InlineKeyboardMarkup()

    for btn in cfg.get("optional_links", []):
        kb.add(InlineKeyboardButton(btn["name"], url=btn["url"]))

    return kb if cfg.get("optional_links") else None

# =========================
# SAFE RUN
# =========================
def run_bot():
    while True:
        try:
            print("🚀 BOT RUNNING (MongoDB)")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print("ERROR:", e)
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
# =========================
# METHODS SYSTEM (MONGODB)
# =========================

class Methods:
    def add(self, category, name, files, price=0, parent=None):
        count = methods_col.count_documents({"category": category, "parent": parent})
        number = count + 1

        methods_col.insert_one({
            "name": name,
            "number": number,
            "category": category,
            "parent": parent,  # for folders inside folders
            "files": files,
            "price": price,
            "expired": False,
            "created_at": time.time()
        })

    def get(self, category, parent=None):
        return list(methods_col.find({
            "category": category,
            "parent": parent
        }).sort("number", 1))

    def get_one(self, category, name):
        return methods_col.find_one({
            "category": category,
            "name": name
        })

    def delete(self, category, name):
        methods_col.delete_one({
            "category": category,
            "name": name
        })
        self.reorder(category)

    def reorder(self, category, parent=None):
        data = list(methods_col.find({
            "category": category,
            "parent": parent
        }).sort("number", 1))

        for i, item in enumerate(data, start=1):
            methods_col.update_one(
                {"_id": item["_id"]},
                {"$set": {"number": i}}
            )

    def set_price(self, category, name, price):
        methods_col.update_one({
            "category": category,
            "name": name
        }, {"$set": {"price": price}})

    def expire(self, category, name):
        methods_col.update_one({
            "category": category,
            "name": name
        }, {"$set": {"expired": True}})

    def unexpire(self, category, name):
        methods_col.update_one({
            "category": category,
            "name": name
        }, {"$set": {"expired": False}})

methods = Methods()

# =========================
# KEYBOARD (WITH NUMBERING)
# =========================
def get_methods_kb(category, parent=None):
    data = methods.get(category, parent)
    kb = InlineKeyboardMarkup()

    for item in data:
        price = item["price"]
        number = item["number"]

        name = f"{number}. {item['name']}"
        if price > 0:
            name += f" [{price} pts]"

        if item.get("expired"):
            name += " ❌"

        kb.add(InlineKeyboardButton(
            name,
            callback_data=f"open|{category}|{item['name']}"
        ))

    return kb

# =========================
# OPEN METHOD / FOLDER
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("open|"))
def open_method(c):
    uid = c.from_user.id
    user = User(uid)

    if force_block(uid):
        return

    _, category, name = c.data.split("|")

    data = methods.get_one(category, name)

    if not data:
        bot.answer_callback_query(c.id, "Not found")
        return

    # =========================
    # HANDLE EXPIRY (REFUND SYSTEM)
    # =========================
    if data.get("expired"):
        price = data.get("price", 0)

        if price > 0 and user.has_method(name):
            user.add_points(price)
            bot.send_message(uid, f"♻️ Method expired!\n\n💰 {price} points refunded to your account.")
        
        bot.answer_callback_query(c.id, "❌ Method expired")
        return

    # =========================
    # ACCESS CHECK
    # =========================
    price = data.get("price", 0)

    if category == "vip":
        if not user.is_vip() and not user.has_method(name):
            kb = InlineKeyboardMarkup()
            kb.add(
                InlineKeyboardButton(f"💰 Buy {price} pts", callback_data=f"buy|{category}|{name}|{price}"),
                InlineKeyboardButton("⭐ VIP", callback_data="get_vip")
            )
            bot.send_message(uid, f"🔒 VIP Method\n\n{name}", reply_markup=kb)
            return

    if price > 0 and not user.is_vip() and not user.has_method(name):
        if user.points() < price:
            bot.answer_callback_query(c.id, "Not enough points", show_alert=True)
            return

        user.deduct_points(price)
        user.purchase(name)

    # =========================
    # SEND FILES
    # =========================
    if data.get("files"):
        for f in data["files"]:
            try:
                bot.copy_message(uid, f["chat"], f["msg"])
                time.sleep(0.3)
            except:
                continue

    bot.answer_callback_query(c.id, "✅ Sent")

# =========================
# UPLOAD SYSTEM (WITH FOLDER SUPPORT)
# =========================
upload_sessions = {}

def start_upload(uid, category):
    upload_sessions[uid] = {
        "category": category,
        "files": [],
        "parent": None
    }

    bot.send_message(uid, "📤 Send files\n\n/done when finished\n/cancel to stop")

@bot.message_handler(commands=["done"])
def done_upload(m):
    uid = m.from_user.id
    session = upload_sessions.get(uid)

    if not session:
        return

    msg = bot.send_message(uid, "Folder name:")
    bot.register_next_step_handler(msg, save_upload)

def save_upload(m):
    uid = m.from_user.id
    session = upload_sessions.get(uid)

    if not session:
        return

    name = m.text

    msg = bot.send_message(uid, "Price (0 for free):")
    bot.register_next_step_handler(msg, lambda x: final_upload(x, name))

def final_upload(m, name):
    uid = m.from_user.id
    session = upload_sessions.get(uid)

    try:
        price = int(m.text)
    except:
        bot.send_message(uid, "Invalid price")
        return

    methods.add(
        session["category"],
        name,
        session["files"],
        price,
        session["parent"]
    )

    del upload_sessions[uid]

    bot.send_message(uid, "✅ Uploaded successfully!")

@bot.message_handler(content_types=["document","photo","video"])
def collect_files(m):
    uid = m.from_user.id

    if uid in upload_sessions:
        upload_sessions[uid]["files"].append({
            "chat": m.chat.id,
            "msg": m.message_id
        })
        bot.send_message(uid, "Saved file")

# =========================
# EXPIRE METHOD (ADMIN FEATURE 🔥)
# =========================
@bot.message_handler(commands=["expire"])
def expire_method_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return

    msg = bot.send_message(m.from_user.id, "Send: category | name")
    bot.register_next_step_handler(msg, expire_process)

def expire_process(m):
    try:
        cat, name = m.text.split("|")
        methods.expire(cat.strip(), name.strip())
        bot.send_message(m.from_user.id, "✅ Method expired")
    except:
        bot.send_message(m.from_user.id, "❌ Format error")

# =========================
# UNEXPIRE METHOD
# =========================
@bot.message_handler(commands=["unexpire"])
def unexpire_method_cmd(m):
    if m.from_user.id != ADMIN_ID:
        return

    msg = bot.send_message(m.from_user.id, "Send: category | name")
    bot.register_next_step_handler(msg, unexpire_process)

def unexpire_process(m):
    try:
        cat, name = m.text.split("|")
        methods.unexpire(cat.strip(), name.strip())
        bot.send_message(m.from_user.id, "✅ Method restored")
    except:
        bot.send_message(m.from_user.id, "❌ Format error")
# =========================
# ADMIN PANEL (MONGODB)
# =========================

buttons_col = db["buttons"]
force_col = db["force"]

class Buttons:
    def add(self, name, action, value):
        buttons_col.insert_one({
            "name": name,
            "action": action,  # category / link
            "value": value
        })

    def get_all(self):
        return list(buttons_col.find())

    def delete(self, name):
        buttons_col.delete_one({"name": name})

buttons = Buttons()

# =========================
# MAIN MENU (DYNAMIC BUTTONS)
# =========================
def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)

    for btn in buttons.get_all():
        kb.add(btn["name"])

    kb.add("👤 Profile")
    return kb

@bot.message_handler(commands=["start"])
def start(m):
    uid = m.from_user.id
    User(uid)

    if force_block(uid):
        return

    bot.send_message(uid, "🔥 Welcome to ZEDOX BOT", reply_markup=main_menu())

# =========================
# BUTTON HANDLER
# =========================
@bot.message_handler(func=lambda m: True)
def handle_buttons(m):
    uid = m.from_user.id

    if force_block(uid):
        return

    text = m.text

    if text == "👤 Profile":
        user = User(uid)
        bot.send_message(uid,
            f"👤 ID: {uid}\n⭐ VIP: {user.is_vip()}\n💰 Points: {user.points()}"
        )
        return

    btn = buttons_col.find_one({"name": text})

    if not btn:
        return

    if btn["action"] == "link":
        bot.send_message(uid, f"🔗 {btn['value']}")
    
    elif btn["action"] == "category":
        kb = get_methods_kb(btn["value"])
        bot.send_message(uid, f"📂 {btn['name']}", reply_markup=kb)

# =========================
# BACK BUTTON (NAVIGATION)
# =========================
def back_button(category):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Back", callback_data=f"back|{category}"))
    return kb

@bot.callback_query_handler(func=lambda c: c.data.startswith("back|"))
def back_handler(c):
    _, category = c.data.split("|")

    kb = get_methods_kb(category)
    bot.edit_message_text(
        f"📂 {category}",
        c.message.chat.id,
        c.message.message_id,
        reply_markup=kb
    )

# =========================
# FORCE JOIN SYSTEM (ADVANCED)
# =========================
class ForceJoin:
    def add(self, name, link):
        force_col.insert_one({"name": name, "link": link})

    def get(self):
        return list(force_col.find())

force = ForceJoin()

def force_block(uid):
    data = force.get()
    if not data:
        return False

    not_joined = []

    for ch in data:
        try:
            member = bot.get_chat_member(ch["link"], uid)
            if member.status in ["left", "kicked"]:
                not_joined.append(ch)
        except:
            continue

    if not_joined:
        kb = InlineKeyboardMarkup()

        for ch in not_joined:
            kb.add(InlineKeyboardButton(ch["name"], url=ch["link"]))

        bot.send_message(uid, "🚫 Join required channels", reply_markup=kb)
        return True

    return False

# =========================
# ADMIN COMMANDS
# =========================

# ADD BUTTON
@bot.message_handler(commands=["addbtn"])
def add_btn(m):
    if m.from_user.id != ADMIN_ID:
        return

    msg = bot.send_message(m.chat.id, "Send: name | action(link/category) | value")
    bot.register_next_step_handler(msg, save_btn)

def save_btn(m):
    try:
        name, action, value = m.text.split("|")
        buttons.add(name.strip(), action.strip(), value.strip())
        bot.send_message(m.chat.id, "✅ Button added")
    except:
        bot.send_message(m.chat.id, "❌ Format error")

# DELETE BUTTON
@bot.message_handler(commands=["delbtn"])
def del_btn(m):
    if m.from_user.id != ADMIN_ID:
        return

    msg = bot.send_message(m.chat.id, "Send button name")
    bot.register_next_step_handler(msg, lambda x: remove_btn(x))

def remove_btn(m):
    buttons.delete(m.text.strip())
    bot.send_message(m.chat.id, "🗑 Removed")

# ADD FORCE CHANNEL
@bot.message_handler(commands=["addforce"])
def add_force(m):
    if m.from_user.id != ADMIN_ID:
        return

    msg = bot.send_message(m.chat.id, "Send: name | link")
    bot.register_next_step_handler(msg, save_force)

def save_force(m):
    try:
        name, link = m.text.split("|")
        force.add(name.strip(), link.strip())
        bot.send_message(m.chat.id, "✅ Added")
    except:
        bot.send_message(m.chat.id, "❌ Error")

# =========================
# BROADCAST SYSTEM 🔥
# =========================
@bot.message_handler(commands=["broadcast"])
def broadcast(m):
    if m.from_user.id != ADMIN_ID:
        return

    msg = bot.send_message(m.chat.id, "Send message to broadcast:")
    bot.register_next_step_handler(msg, send_broadcast)

def send_broadcast(m):
    users = users_col.find()
    sent = 0

    for u in users:
        try:
            bot.send_message(u["_id"], m.text)
            sent += 1
            time.sleep(0.05)
        except:
            continue

    bot.send_message(m.chat.id, f"✅ Sent to {sent} users")
# =========================
# VIP + POINTS SYSTEM
# =========================

class User:
    def __init__(self, uid):
        self.uid = uid
        if not users_col.find_one({"_id": uid}):
            users_col.insert_one({
                "_id": uid,
                "points": 0,
                "vip": False,
                "methods": [],
                "created": time.time()
            })

    def data(self):
        return users_col.find_one({"_id": self.uid})

    def points(self):
        return self.data().get("points", 0)

    def add_points(self, amt):
        users_col.update_one({"_id": self.uid}, {"$inc": {"points": amt}})

    def deduct_points(self, amt):
        users_col.update_one({"_id": self.uid}, {"$inc": {"points": -amt}})

    def is_vip(self):
        return self.data().get("vip", False)

    def set_vip(self, status=True):
        users_col.update_one({"_id": self.uid}, {"$set": {"vip": status}})

    def purchase(self, name):
        users_col.update_one({"_id": self.uid}, {"$addToSet": {"methods": name}})

    def has_method(self, name):
        return name in self.data().get("methods", [])

# =========================
# BUY POINTS SYSTEM
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "buy_points")
def buy_points(c):
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("💰 200 Points = $1", callback_data="req|200|1"),
        InlineKeyboardButton("💰 1000 Points = $5", callback_data="req|1000|5")
    )
    bot.send_message(c.from_user.id, "💳 Choose package", reply_markup=kb)

# =========================
# PAYMENT REQUEST
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("req|"))
def req_payment(c):
    uid = c.from_user.id
    pts, usd = c.data.split("|")[1:]

    msg = bot.send_message(uid, f"""
💳 Payment Details

Amount: ${usd}
Points: {pts}

Send payment screenshot
""")

    bot.register_next_step_handler(msg, lambda m: save_payment(m, pts))

payments = {}

def save_payment(m, pts):
    uid = m.from_user.id

    if not m.photo:
        bot.send_message(uid, "❌ Send screenshot")
        return

    payments[uid] = pts

    bot.send_photo(
        ADMIN_ID,
        m.photo[-1].file_id,
        caption=f"💰 Payment Request\n\nUser: {uid}\nPoints: {pts}",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("✅ Approve", callback_data=f"approve|{uid}")
        )
    )

    bot.send_message(uid, "⏳ Waiting for approval")

# =========================
# APPROVE PAYMENT
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("approve|"))
def approve_payment(c):
    if c.from_user.id != ADMIN_ID:
        return

    uid = int(c.data.split("|")[1])
    pts = int(payments.get(uid, 0))

    user = User(uid)
    user.add_points(pts)

    bot.send_message(uid, f"✅ Payment approved\n💰 {pts} points added")

    bot.answer_callback_query(c.id, "Approved")

# =========================
# VIP PURCHASE BUTTON
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "get_vip")
def get_vip(c):
    bot.send_message(c.from_user.id,
        "⭐ VIP Price: $10\n\nContact admin to activate\n@zedox5"
    )

# =========================
# ADMIN GIVE VIP
# =========================
@bot.message_handler(commands=["givevip"])
def give_vip(m):
    if m.from_user.id != ADMIN_ID:
        return

    msg = bot.send_message(m.chat.id, "Send user ID")
    bot.register_next_step_handler(msg, set_vip_user)

def set_vip_user(m):
    try:
        uid = int(m.text)
        user = User(uid)
        user.set_vip(True)
        bot.send_message(m.chat.id, "✅ VIP activated")
    except:
        bot.send_message(m.chat.id, "❌ Error")

# =========================
# LOG SYSTEM
# =========================
def log(text):
    try:
        bot.send_message(ADMIN_ID, f"📊 LOG:\n{text}")
    except:
        pass
