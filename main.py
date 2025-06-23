# === IMPORTS & INIT ===
import os, sys, json, time, threading, requests
from datetime import datetime, timedelta
from telebot import TeleBot, types
from subprocess import run

# === CONFIG ===
BOT_TOKEN = "7530147130:AAHbD4yZHf4U4lBiX2xFLjtHPABK1ze_jPI"
ADMIN_ID = 7348631392
JOIN_CHANNEL = "@ElabCode"
FORWARD_CHANNEL = "@ElabMediass"
DB_FILE = "db.json"

bot = TeleBot(BOT_TOKEN, parse_mode="HTML")

# === INIT DB ===
if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w") as f:
        json.dump({"users": {}, "downloads": [], "ratings": []}, f)

def load_db():
    with open(DB_FILE) as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

# === JOIN CHECK ===
def is_joined(uid):
    try:
        member = bot.get_chat_member(JOIN_CHANNEL, uid)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# === PREMIUM CHECK ===
def is_premium(uid):
    db = load_db()
    user = db["users"].get(str(uid), {})
    if user.get("premium") == True:
        return True
    try:
        joined = datetime.fromisoformat(user.get("joined", ""))
        return (datetime.now() - joined).days < 3
    except:
        return False

# === DOWNLOAD LIMIT CHECK ===
def can_download(uid):
    db = load_db()
    now = datetime.now()
    dls = [d for d in db["downloads"] if d["uid"] == uid]
    today = [d for d in dls if datetime.fromisoformat(d["time"]).date() == now.date()]
    last_hour = [d for d in today if (now - datetime.fromisoformat(d["time"])).seconds < 3600]
    return is_premium(uid) or (len(today) < 3 and len(last_hour) < 1)

# === LOG DOWNLOAD ===
def log_download(uid):
    db = load_db()
    db["downloads"].append({"uid": uid, "time": str(datetime.now())})
    save_db(db)

# === PREMIUM EXPIRY CHECK ===
def check_expiring_premium():
    db = load_db()
    now = datetime.now()
    for uid, info in db["users"].items():
        exp = info.get("premium_until")
        if not exp:
            continue
        try:
            exp_date = datetime.fromisoformat(exp)
            days_left = (exp_date - now).days
            if 0 < days_left <= 3 and not info.get("warned"):
                bot.send_message(int(uid), f"⚠️ Your premium will expire in {days_left} day(s).\nPlease contact @Agegnewu0102 to renew.")
                info["warned"] = True
        except:
            pass
    save_db(db)

def schedule_premium_check():
    check_expiring_premium()
    threading.Timer(21600, schedule_premium_check).start()

# === START PREMIUM CHECK THREAD ===
schedule_premium_check()
# === START COMMAND & MAIN BUTTONS ===
@bot.message_handler(commands=["start"])
def start_command(message):
    uid = str(message.from_user.id)
    db = load_db()
    if uid not in db["users"]:
        db["users"][uid] = {
            "joined": str(datetime.now()),
            "username": message.from_user.username or "",
            "premium": False,
            "warned": False
        }
        save_db(db)

    if not is_joined(message.from_user.id):
        btn = types.InlineKeyboardMarkup()
        btn.add(
            types.InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{JOIN_CHANNEL[1:]}"),
            types.InlineKeyboardButton("✅ I Joined", callback_data="joined")
        )
        return bot.send_message(message.chat.id, "🔐 Please join our channel to use this bot.", reply_markup=btn)

    text = (
        f"👋 Hello <b>{message.from_user.first_name}</b>!\n\n"
        "📥 Send any video link to download from:\n"
        "- TikTok (No Watermark)\n"
        "- YouTube Videos / Shorts\n"
        "- Instagram Reels / Videos / Images\n\n"
        "🔥 First 3 Days = Unlimited Access\n"
        "⚠️ After that: 1 video/hour & 3 videos/day limit or 💎 Upgrade Premium\n\n"
        "💡 Want Me to:"
    )

    buttons = types.InlineKeyboardMarkup(row_width=3)
    buttons.add(
        types.InlineKeyboardButton("🧑‍💻 My Profile", callback_data="profile"),
        types.InlineKeyboardButton("💎 Premium", callback_data="premium"),
        types.InlineKeyboardButton("💖 Donate", callback_data="donate"),
        types.InlineKeyboardButton("ℹ️ Help", callback_data="help"),
        types.InlineKeyboardButton("⭐ Rate Bot", callback_data="rate"),
        types.InlineKeyboardButton("📢 Channel", url=f"https://t.me/{JOIN_CHANNEL[1:]}"),
        types.InlineKeyboardButton("📩 Contact Admin", url="https://t.me/Agegnewu0102")
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=buttons)

# === CALLBACK: JOIN CHECK BUTTON ===
@bot.callback_query_handler(func=lambda c: c.data == "joined")
def recheck_join_callback(c):
    bot.answer_callback_query(c.id)
    if is_joined(c.from_user.id):
        bot.edit_message_text(
            "✅ You have joined the channel! You can now use the bot.",
            chat_id=c.message.chat.id,
            message_id=c.message.message_id
        )
        start_command(c.message)
    else:
        bot.answer_callback_query(c.id, "⚠️ You have NOT joined yet. Please join to continue.", show_alert=True)

# === CALLBACKS FOR MAIN BUTTONS ===
@bot.callback_query_handler(func=lambda c: c.data in ["profile", "premium", "donate", "help", "rate"])
def main_buttons_callback(c):
    db = load_db()
    uid = str(c.from_user.id)
    user = db["users"].get(uid, {})

    if c.data == "profile":
        joined_date = user.get("joined", "N/A").split("T")[0]
        downloads = len([d for d in db["downloads"] if d["uid"] == c.from_user.id])
        premium_status = "✅ Premium" if user.get("premium") else \
            ("✅ Until 3 Days" if is_premium(uid) else "❌ Not Premium")
        msg = (
            f"👤 <b>Your Profile</b>\n\n"
            f"🆔 ID: <code>{uid}</code>\n"
            f"📆 Joined: {joined_date}\n"
            f"📦 Downloads: {downloads}\n"
            f"💎 Status: {premium_status}"
        )
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, msg, parse_mode="HTML")

    elif c.data == "premium":
        msg = (
            "💎 <b>Premium Plans</b>\n\n"
            "🔥 Lifetime Access: 50 Birr / 0.5$\n"
            "⭐ Or 50 Star support to @Agegnewu0102\n\n"
            "📩 Contact Admin to Upgrade."
        )
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, msg, parse_mode="HTML")

    elif c.data == "donate":
        msg = (
            "🙏 <b>Donate & Support</b>\n\n"
            "💎 TON Wallet:\n<code>UQC3iPLHG6BkQg5Cxi9psMjkv8uK_2dDtiE9qDJyPUpnDO8N</code>\n\n"
            "⭐ Send Stars Gift to Owner: @Agegnewu0102"
        )
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, msg, parse_mode="HTML")

    elif c.data == "help":
        msg = (
            "ℹ️ <b>How To Use</b>\n\n"
            "📌 Send any video link from:\n"
            "- TikTok\n- YouTube\n- Instagram\n\n"
            "⏳ Wait... the bot will download and send the video.\n\n"
            "⚠️ Free users: 1 video/hour & 3 videos/day limit\n"
            "💎 Premium users: Unlimited downloads"
        )
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, msg, parse_mode="HTML")

    elif c.data == "rate":
        buttons = types.InlineKeyboardMarkup(row_width=5)
        buttons.add(
            types.InlineKeyboardButton("⭐️ 1", callback_data="rate_1"),
            types.InlineKeyboardButton("⭐️ 2", callback_data="rate_2"),
            types.InlineKeyboardButton("⭐️ 3", callback_data="rate_3"),
            types.InlineKeyboardButton("⭐️ 4", callback_data="rate_4"),
            types.InlineKeyboardButton("⭐️ 5", callback_data="rate_5"),
        )
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, "Please rate the bot:", reply_markup=buttons)

# === HANDLE RATINGS ===
@bot.callback_query_handler(func=lambda c: c.data.startswith("rate_"))
def handle_rating(c):
    rating = int(c.data.split("_")[1])
    db = load_db()
    uid = str(c.from_user.id)

    # Save or update user's rating
    ratings = db.get("ratings", [])
    existing = next((r for r in ratings if r["uid"] == uid), None)
    if existing:
        existing["rating"] = rating
        existing["time"] = str(datetime.now())
    else:
        ratings.append({"uid": uid, "rating": rating, "time": str(datetime.now())})
    db["ratings"] = ratings
    save_db(db)

    bot.answer_callback_query(c.id, f"Thank you for rating {rating}⭐️!")

# === Utility to get average rating ===
def get_average_rating():
    db = load_db()
    ratings = db.get("ratings", [])
    if not ratings:
        return 0
    return round(sum(r["rating"] for r in ratings) / len(ratings), 2)
    # === DOWNLOAD LINK HANDLER ===
@bot.message_handler(func=lambda m: m.text and m.text.startswith("http"))
def handle_download(m):
    uid = str(m.from_user.id)
    url = m.text.strip()
    db = load_db()

    if not is_joined(m.from_user.id):
        return start_command(m)

    if not can_download(m.from_user.id):
        return bot.send_message(m.chat.id,
            "⛔ <b>Limit reached</b>\n\n⚠️ 1 video per hour\n📦 3 videos per day\n\n💎 Upgrade to Premium for unlimited downloads!",
            parse_mode="HTML")

    wait_msg = bot.send_message(m.chat.id, "⏳ <b>Downloading your video...</b>", parse_mode="HTML")

    filename = f"{int(time.time())}.mp4"
    caption = (
        f"🎬 <b>Your Download is Ready!</b>\n\n"
        f"📥 Requested by: <a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a>\n"
        f"💡 Want Me to: <i>Download More Videos!</i>\n\n"
        f"🚀 Powered by @ElabCode"
    )
    buttons = types.InlineKeyboardMarkup()
    buttons.add(
        types.InlineKeyboardButton("🧑‍💻 My Profile", callback_data="profile"),
        types.InlineKeyboardButton("💎 Premium", callback_data="premium"),
        types.InlineKeyboardButton("💖 Donate", callback_data="donate"),
        types.InlineKeyboardButton("ℹ️ Help", callback_data="help")
    )

    try:
        # TikTok downloader (no watermark) using Lovetik API
        if "tiktok.com" in url:
            headers = {
                'origin': 'https://lovetik.com',
                'referer': 'https://lovetik.com/',
                'user-agent': 'Mozilla/5.0'
            }
            r = requests.post("https://lovetik.com/api/ajax/search", data={'query': url}, headers=headers)
            j = r.json()
            if 'links' not in j or not j["links"]:
                bot.delete_message(m.chat.id, wait_msg.message_id)
                return bot.send_message(m.chat.id, "❌ Couldn't fetch the TikTok video.")
            video_url = j["links"][0]["a"]
            video_data = requests.get(video_url)
            with open(filename, "wb") as f:
                f.write(video_data.content)

        # YouTube & Instagram downloader via yt-dlp command line
        elif any(x in url for x in ["youtube.com", "youtu.be", "instagram.com"]):
            cmd = f'yt-dlp -f mp4 -o "{filename}" "{url}"'
            os.system(cmd)

        else:
            bot.delete_message(m.chat.id, wait_msg.message_id)
            return bot.send_message(m.chat.id, "❌ Unsupported link. Only TikTok, YouTube, Instagram allowed.")

        if not os.path.exists(filename):
            bot.delete_message(m.chat.id, wait_msg.message_id)
            return bot.send_message(m.chat.id, "❌ Download failed, please try another link.")

        bot.delete_message(m.chat.id, wait_msg.message_id)

        with open(filename, "rb") as video_file:
            bot.send_video(m.chat.id, video_file, caption=caption, reply_markup=buttons, parse_mode="HTML")
            video_file.seek(0)
            bot.send_video(FORWARD_CHANNEL, video_file,
                caption=f"📥 Downloaded by: @{m.from_user.username or m.from_user.first_name}")

        log_download(m.from_user.id)
        os.remove(filename)

    except Exception as e:
        bot.delete_message(m.chat.id, wait_msg.message_id)
        bot.send_message(m.chat.id, f"❌ Error during download: {e}")

# === ADMIN PANEL ===
@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return

    admin_buttons = types.InlineKeyboardMarkup(row_width=3)
    admin_buttons.add(
        types.InlineKeyboardButton("👥 Total Users", callback_data="a_total_users"),
        types.InlineKeyboardButton("📅 New Users Today", callback_data="a_today"),
        types.InlineKeyboardButton("💎 Premium Users", callback_data="a_premium_users"),
        types.InlineKeyboardButton("🔄 Restart Bot", callback_data="a_restart"),
        types.InlineKeyboardButton("➕ Grant Premium", callback_data="a_grant"),
        types.InlineKeyboardButton("➖ Remove Premium", callback_data="a_remove_premium"),
        types.InlineKeyboardButton("📣 Broadcast Message", callback_data="a_bc"),
        types.InlineKeyboardButton("⭐ Show Ratings", callback_data="a_show_ratings"),
        types.InlineKeyboardButton("🧹 Clear Downloads", callback_data="a_clear_downloads"),
        types.InlineKeyboardButton("📊 Stats Summary", callback_data="a_stats_summary"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="a_cancel")
    )
    bot.send_message(message.chat.id, "🔐 Admin Panel:", reply_markup=admin_buttons)

# === ADMIN CALLBACKS ===
@bot.callback_query_handler(func=lambda c: c.data.startswith("a_"))
def admin_callbacks(c):
    if c.from_user.id != ADMIN_ID:
        return bot.answer_callback_query(c.id, "❌ Not authorized.")

    db = load_db()
    data = c.data

    if data == "a_total_users":
        text = "👥 <b>Total Users:</b>\n"
        for uid, info in db["users"].items():
            uname = info.get("username") or "NoUsername"
            joined = info.get("joined", "N/A").split("T")[0]
            text += f"🆔 <code>{uid}</code> - @{uname}\n📅 Joined: {joined}\n\n"
        bot.send_message(c.message.chat.id, text, parse_mode="HTML")

    elif data == "a_today":
        today = datetime.now().date()
        new_users = [u for u in db["users"].values() if datetime.fromisoformat(u["joined"]).date() == today]
        bot.send_message(c.message.chat.id, f"📅 New Users Today: {len(new_users)}")

    elif data == "a_restart":
        bot.answer_callback_query(c.id, "🔄 Restarting bot...")
        os.execv(sys.executable, ['python'] + sys.argv)

    elif data == "a_premium_users":
        text = "<b>💎 Premium Users:</b>\n"
        count = 0
        for uid, info in db["users"].items():
            if info.get("premium"):
                name = info.get("username") or "NoUsername"
                text += f"🆔 <code>{uid}</code> - @{name}\n"
                count += 1
        bot.send_message(c.message.chat.id, text or "❌ No premium users.", parse_mode="HTML")

    elif data == "a_grant":
        msg = bot.send_message(c.message.chat.id, "👤 Send user ID to grant premium:")
        bot.register_next_step_handler(msg, admin_ask_premium_days)

    elif data == "a_remove_premium":
        msg = bot.send_message(c.message.chat.id, "❌ Send user ID to remove premium:")
        bot.register_next_step_handler(msg, admin_remove_premium)

    elif data == "a_bc":
        msg = bot.send_message(c.message.chat.id, "📣 Send content to broadcast:")
        bot.register_next_step_handler(msg, admin_broadcast)

    elif data == "a_show_ratings":
        ratings = db.get("ratings", [])
        if not ratings:
            bot.send_message(c.message.chat.id, "⭐ No ratings yet.")
            return
        total = len(ratings)
        avg = round(sum(r["rating"] for r in ratings) / total, 2)
        text = f"⭐ Ratings Summary:\n\nTotal Ratings: {total}\nAverage Rating: {avg}⭐"
        bot.send_message(c.message.chat.id, text)

    elif data == "a_clear_downloads":
        db["downloads"] = []
        save_db(db)
        bot.send_message(c.message.chat.id, "🧹 Download logs cleared.")

    elif data == "a_stats_summary":
        total_users = len(db["users"])
        total_downloads = len(db["downloads"])
        total_premium = sum(1 for u in db["users"].values() if u.get("premium"))
        text = (
            f"📊 <b>Stats Summary:</b>\n\n"
            f"👥 Total Users: {total_users}\n"
            f"📦 Total Downloads: {total_downloads}\n"
            f"💎 Premium Users: {total_premium}"
        )
        bot.send_message(c.message.chat.id, text, parse_mode="HTML")

    elif data == "a_cancel":
        bot.send_message(c.message.chat.id, "❌ Action canceled.")

# === ADMIN HANDLERS ===
def admin_ask_premium_days(msg):
    uid = msg.text.strip()
    msg2 = bot.send_message(msg.chat.id, f"📆 How many days to grant premium to <code>{uid}</code>?", parse_mode="HTML")
    bot.register_next_step_handler(msg2, lambda m: admin_grant_premium(uid, m))

def admin_grant_premium(uid, msg):
    try:
        days = int(msg.text.strip())
        db = load_db()
        if uid in db["users"]:
            until = datetime.now() + timedelta(days=days)
            db["users"][uid]["premium"] = True
            db["users"][uid]["premium_until"] = str(until)
            db["users"][uid]["warned"] = False
            save_db(db)
            bot.send_message(msg.chat.id, f"✅ Premium granted to {uid} until {until.date()}.")
            try:
                bot.send_message(int(uid), f"🎉 You have been granted Premium access for {days} days! Enjoy unlimited downloads.")
            except:
                pass
        else:
            bot.send_message(msg.chat.id, "❌ User ID not found.")
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ Failed to grant premium: {e}")

def admin_remove_premium(msg):
    uid = msg.text.strip()
    db = load_db()
    if uid in db["users"] and db["users"][uid].get("premium"):
        db["users"][uid]["premium"] = False
        db["users"][uid].pop("premium_until", None)
        save_db(db)
        bot.send_message(msg.chat.id, f"❌ Premium removed from {uid}.")
        try:
            bot.send_message(int(uid), "⚠️ Your Premium access has been revoked.")
        except:
            pass
    else:
        bot.send_message(msg.chat.id, "❌ User ID not found or not a premium user.")
        
def admin_broadcast(msg):
    db = load_db()
    success = 0
    total = 0
    for uid in db["users"]:
        total += 1
        try:
            if msg.content_type == "text":
                bot.send_message(uid, msg.text)
            elif msg.content_type == "photo":
                bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.caption or "")
            elif msg.content_type == "video":
                bot.send_video(uid, msg.video.file_id, caption=msg.caption or "")
            elif msg.content_type == "document":
                bot.send_document(uid, msg.document.file_id, caption=msg.caption or "")
            success += 1
        except Exception:
            continue
    bot.send_message(msg.chat.id, f"✅ Broadcast sent to {success}/{total} users.")
    
    # === RUN BOT ===
if __name__ == "__main__":
    print("Bot is starting...")
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"Error occurred: {e}")        print(f"Error occurred: {e}")main.py
