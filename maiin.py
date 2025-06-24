
import yt_dlp
import os
import sys
import json
import time
import threading
import requests
from datetime import datetime, timedelta
from telebot import TeleBot, types

# --- Config ---
BOT_TOKEN = "7530147130:AAHbD4yZHf4U4lBiX2xFLjtHPABK1ze_jPI"
ADMIN_ID = 7348631392
JOIN_CHANNEL = "@ElabCode"
FORWARD_CHANNEL = "@ElabMediass"
DB_FILE = "db.json"

bot = TeleBot(BOT_TOKEN, parse_mode="HTML")

# --- Initialize DB if not exists ---
if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w") as f:
        json.dump({
            "users": {},
            "downloads": [],
            "ratings": [],
            "favorites": {},
            "history": {},
            "announcements": []
        }, f)

# --- DB Utilities ---
def load_db():
    with open(DB_FILE) as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- Check if user joined the required channel ---
def is_joined(uid):
    try:
        member = bot.get_chat_member(JOIN_CHANNEL, uid)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

# --- Get user premium level, handle expiry ---
def get_user_level(uid):
    db = load_db()
    user = db["users"].get(str(uid), {})
    premium_info = user.get("premium_info", {})

    premium_until = premium_info.get("premium_until")
    if premium_until:
        try:
            exp_date = datetime.fromisoformat(premium_until)
            if datetime.now() > exp_date:
                # Premium expired - downgrade user to free
                user["premium_info"] = {"level": 0}
                db["users"][str(uid)] = user
                save_db(db)
                return 0
            else:
                return premium_info.get("level", 0)
        except Exception:
            return 0
    return premium_info.get("level", 0)

# --- Calculate remaining premium days ---
def get_premium_days_left(uid):
    db = load_db()
    user = db["users"].get(str(uid), {})
    premium_info = user.get("premium_info", {})
    premium_until = premium_info.get("premium_until")
    if premium_until:
        try:
            exp_date = datetime.fromisoformat(premium_until)
            delta = exp_date - datetime.now()
            return max(delta.days, 0)
        except:
            return 0
    return 0

# --- Log downloads ---
def log_download(uid):
    db = load_db()
    db["downloads"].append({"uid": uid, "time": datetime.now().isoformat()})
    save_db(db)

# --- Download limits check ---
def can_download(uid):
    db = load_db()
    level = get_user_level(uid)
    now = datetime.now()
    downloads = [d for d in db["downloads"] if d["uid"] == uid]
    downloads_today = [d for d in downloads if datetime.fromisoformat(d["time"]).date() == now.date()]
    downloads_last_hour = [d for d in downloads_today if (now - datetime.fromisoformat(d["time"])).total_seconds() < 3600]

    if level == 2:
        return True  # Unlimited
    elif level == 1:
        return len(downloads_last_hour) < 3 and len(downloads_today) < 15
    else:
        return len(downloads_last_hour) < 1 and len(downloads_today) < 3

def can_download_custom(uid, hourly_limit, daily_limit):
    db = load_db()
    now = datetime.now()
    user_downloads = [d for d in db["downloads"] if d["uid"] == uid]
    today_downloads = [d for d in user_downloads if datetime.fromisoformat(d["time"]).date() == now.date()]
    last_hour_downloads = [d for d in today_downloads if (now - datetime.fromisoformat(d["time"])).total_seconds() < 3600]
    return len(today_downloads) < daily_limit and len(last_hour_downloads) < hourly_limit

# --- Favorites and History Management ---
def get_favorites(uid):
    db = load_db()
    return db.get("favorites", {}).get(str(uid), [])

def add_favorite(uid, video_url):
    db = load_db()
    favs = db.get("favorites", {}).get(str(uid), [])
    if video_url not in favs:
        favs.append(video_url)
    level = get_user_level(uid)
    max_favs = 0
    if level == 1:
        max_favs = 10
    elif level == 2:
        max_favs = 20
    if max_favs > 0 and len(favs) > max_favs:
        favs = favs[-max_favs:]
    db.setdefault("favorites", {})[str(uid)] = favs
    save_db(db)

def get_history(uid):
    db = load_db()
    return db.get("history", {}).get(str(uid), [])

def add_history(uid, video_url):
    db = load_db()
    hist = db.get("history", {}).get(str(uid), [])
    hist.append({"url": video_url, "time": datetime.now().isoformat()})
    level = get_user_level(uid)
    max_hist = 0
    if level == 1:
        max_hist = 5
    elif level == 2:
        max_hist = 10
    else:
        max_hist = 0
    if len(hist) > max_hist:
        hist = hist[-max_hist:]
    db.setdefault("history", {})[str(uid)] = hist
    save_db(db)

# --- Premium Expiry Notification ---
def check_expiring_premium():
    db = load_db()
    now = datetime.now()
    for uid, info in db["users"].items():
        premium_info = info.get("premium_info", {})
        exp = premium_info.get("premium_until")
        if not exp:
            continue
        try:
            exp_date = datetime.fromisoformat(exp)
            days_left = (exp_date - now).days
            if 0 < days_left <= 3 and not premium_info.get("warned", False):
                try:
                    bot.send_message(int(uid), f"⚠️ Your premium will expire in {days_left} day(s).\nPlease contact @Agegnewu0102 to renew.")
                except Exception:
                    pass
                premium_info["warned"] = True
                save_db(db)
            elif days_left <= 0 and premium_info.get("level", 0) > 0:
                try:
                    bot.send_message(int(uid), "⚠️ Your premium has expired.\nPlease contact @Agegnewu0102 to renew.")
                except Exception:
                    pass
                # Downgrade premium after expiry notification
                info["premium_info"] = {"level": 0}
                save_db(db)
        except Exception:
            continue

def schedule_premium_check():
    check_expiring_premium()
    threading.Timer(21600, schedule_premium_check).start()

schedule_premium_check()

# --- /start Command ---
@bot.message_handler(commands=["start"])
def start_command(message):
    uid = str(message.from_user.id)
    db = load_db()

    if uid not in db["users"]:
        db["users"][uid] = {
            "joined": datetime.now().isoformat(),
            "username": message.from_user.username or "",
            "premium_info": {"level": 0},
            "warned": False
        }
        save_db(db)

    if not is_joined(message.from_user.id):
        btn = types.InlineKeyboardMarkup()
        btn.add(
            types.InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{JOIN_CHANNEL[1:]}"),
            types.InlineKeyboardButton("✅ I Joined", callback_data="joined")
        )
        return bot.send_message(message.chat.id,
                                "🔐 Please join our channel to use this bot.",
                                reply_markup=btn)

    level = get_user_level(message.from_user.id)
    fav_count = len(get_favorites(message.from_user.id))
    hist_count = len(get_history(message.from_user.id))
    days_left = get_premium_days_left(message.from_user.id)

    premium_status_text = f"⭐ Your Level: {level} | Favorites: {fav_count} | History: {hist_count}"
    if level > 0:
        premium_status_text += f" | Premium expires in: {days_left} day(s)"

    welcome_text = (
        f"👋 Hello <b>{message.from_user.first_name}</b>!\n\n"
        "📥 Send any video link to download from:\n"
        "- TikTok (No Watermark)\n"
        "- YouTube Videos / Shorts\n"
        "- Instagram Reels / Videos / Images\n\n"
        "🔥 Free users: 1 video/hour & 3 videos/day (No Favorites or History)\n"
        "💎 Level 1 Premium: 3 videos/hour & 15/day, 10 Favorites, 5 History\n"
        "💎 Level 2 Premium: Unlimited, 20 Favorites, 10 History\n\n"
        f"{premium_status_text}\n\n"
        "💡 What would you like to do?"
    )

    buttons = types.InlineKeyboardMarkup(row_width=3)
    buttons.add(
        types.InlineKeyboardButton("🧑‍💻 My Profile", callback_data="profile"),
        types.InlineKeyboardButton("💎 Premium Plans", callback_data="premium"),
        types.InlineKeyboardButton("💖 Donate", callback_data="donate"),
        types.InlineKeyboardButton("🗂 Favorites", callback_data="favorites"),
        types.InlineKeyboardButton("📜 History", callback_data="history"),
        types.InlineKeyboardButton("ℹ️ Help", callback_data="help"),
        types.InlineKeyboardButton("⭐ Rate Bot", callback_data="rate"),
        types.InlineKeyboardButton("📢 Channel", url=f"https://t.me/{JOIN_CHANNEL[1:]}"),
        types.InlineKeyboardButton("📩 Contact Admin", url="https://t.me/Agegnewu0102"),
        types.InlineKeyboardButton("📣 Announcements", callback_data="announcements")
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=buttons, parse_mode="HTML")

# --- Join button callback ---
@bot.callback_query_handler(func=lambda c: c.data == "joined")
def joined_callback(c):
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

# --- Main buttons callback ---
@bot.callback_query_handler(func=lambda c: c.data in [
    "profile", "premium", "donate", "help", "rate", "favorites", "history", "announcements"
])
def main_buttons_callback(c):
    db = load_db()
    uid = str(c.from_user.id)
    user = db["users"].get(uid, {})
    level = get_user_level(c.from_user.id)

    if c.data == "profile":
        joined_date = user.get("joined", "N/A").split("T")[0]
        downloads = len([d for d in db["downloads"] if d["uid"] == c.from_user.id])
        premium_status = "Free User"
        if level == 1:
            premium_status = "💎 Level 1 Premium"
        elif level == 2:
            premium_status = "💎 Level 2 Premium"

        days_left = get_premium_days_left(c.from_user.id)
        days_text = f"\n⏳ Premium expires in: {days_left} day(s)" if days_left > 0 else ""

        fav_count = len(get_favorites(c.from_user.id))
        hist_count = len(get_history(c.from_user.id))

        msg = (
            f"👤 <b>Your Profile</b>\n\n"
            f"🆔 ID: <code>{uid}</code>\n"
            f"📆 Joined: {joined_date}\n"
            f"📦 Downloads: {downloads}\n"
            f"💎 Status: {premium_status}{days_text}\n"
            f"⭐ Favorites: {fav_count}\n"
            f"📜 History: {hist_count}"
        )
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, msg, parse_mode="HTML")

    elif c.data == "premium":
        msg = (
            "💎 <b>Premium Plans</b>\n\n"
            "Level 1: 3/hour, 15/day, 10 Favorites, 5 History\n"
            "Price: 30 Birr / 25 ⭐ / 0.25$ per month\n\n"
            "Level 2: Unlimited, 20 Favorites, 10 History\n"
            "Price: 60 Birr / 50 ⭐ / 0.7$ per month\n\n"
            "🔔 Includes reminder notifications and auto expiry.\n"
            "📩 Contact @Agegnewu0102 to upgrade or renew."
        )
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, msg, parse_mode="HTML")

    elif c.data == "donate":
        msg = (
            "🙏 <b>Donate & Support</b>\n\n"
            "BINANCE UID, BITGET UID, TON Wallet & Telegram ⭐️:\n"
            "Send your support to @Agegnewu0102\n\n"
            "For help, contact: @ElabSupport"
        )
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, msg, parse_mode="HTML")

    elif c.data == "help":
        msg = (
            "ℹ️ <b>How To Use</b>\n\n"
            "1️⃣ Send any supported video link (TikTok, YouTube, Instagram) to download.\n"
            "2️⃣ Use the buttons to view your profile, favorites, or history.\n"
            "3️⃣ Upgrade to premium for higher limits and extra features.\n"
            "4️⃣ Use /start anytime to see main menu.\n\n"
            "⚠️ Make sure you have joined our channel to use the bot.\n"
            "💬 For questions or support, contact @Agegnewu0102."
        )
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, msg, parse_mode="HTML")

    elif c.data == "rate":
        buttons = types.InlineKeyboardMarkup(row_width=1)
        buttons.add(
            types.InlineKeyboardButton("⭐️ 1", callback_data="rate_1"),
            types.InlineKeyboardButton("⭐️⭐️ 2", callback_data="rate_2"),
            types.InlineKeyboardButton("⭐️⭐️⭐️ 3", callback_data="rate_3"),
            types.InlineKeyboardButton("⭐️⭐️⭐️⭐️ 4", callback_data="rate_4"),
            types.InlineKeyboardButton("⭐️⭐️⭐️⭐️⭐️ 5", callback_data="rate_5"),
 )
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, "⭐️ Please select your rating:", reply_markup=buttons)

    elif c.data == "favorites":
        favs = get_favorites(c.from_user.id)
        if not favs:
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "⭐️ You have no favorites yet.")
            return
        text = "⭐️ <b>Your Favorites:</b>\n\n"
        for i, url in enumerate(favs, 1):
            text += f"{i}. {url}\n"
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, text, parse_mode="HTML")

    elif c.data == "history":
        hist = get_history(c.from_user.id)
        if not hist:
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "📜 You have no history yet.")
            return
        text = "📜 <b>Your History:</b>\n\n"
        for i, entry in enumerate(hist, 1):
            t = entry.get("time", "")[:10]
            url = entry.get("url", "")
            text += f"{i}. {url} ({t})\n"
        bot.answer_callback_query(c.id)
        bot.send_message(c.message.chat.id, text, parse_mode="HTML")

    elif c.data == "announcements":
        ann = get_latest_announcement()
        if ann:
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, f"📢 <b>Latest Announcement:</b>\n\n{ann}", parse_mode="HTML")
        else:
            bot.answer_callback_query(c.id)
            bot.send_message(c.message.chat.id, "📢 No announcements yet.", parse_mode="HTML")
            
# --- ADMIN CALLBACKS EXTENDED CONTINUED ---

@bot.callback_query_handler(func=lambda c: c.data.startswith("a_"))
def admin_callbacks(c):
    if c.from_user.id != ADMIN_ID:
        return bot.answer_callback_query(c.id, "❌ Not authorized.")

    db = load_db()
    data = c.data

    if data == "a_total_users":
        text = "👥 <b>Total Users:</b>\n"
        for uid, info in db["users"].items():
            uname = info.get("username") or "NAN"
            joined = info.get("joined", "N/A").split("T")[0]
            text += f"🆔 <code>{uid}</code> - @{uname}\n📅 Joined: {joined}\n\n"
        bot.send_message(c.message.chat.id, text, parse_mode="HTML")

    elif data == "a_today":
        today = datetime.now().date()
        new_users = [u for u in db["users"].values() if datetime.fromisoformat(u["joined"]).date() == today]
        bot.send_message(c.message.chat.id, f"📅 New Users Today: {len(new_users)}")

    elif data == "a_premium_users":
        text = "<b>💎 Premium Users:</b>\n"
        count = 0
        for uid, info in db["users"].items():
            prem = info.get("premium_info", {})
            level = prem.get("level", 0)
            if level > 0:
                name = info.get("username") or "NAN"
                until = prem.get("premium_until", "N/A")
                text += f"🆔 <code>{uid}</code> - @{name} | Level: {level} | Until: {until}\n"
                count += 1
        bot.send_message(c.message.chat.id, text if count > 0 else "❌ No premium users.", parse_mode="HTML")

    elif data == "a_restart":
        bot.answer_callback_query(c.id, "🔄 Restarting bot...")
        os.execv(sys.executable, ['python'] + sys.argv)

    elif data == "a_grant":
        msg = bot.send_message(c.message.chat.id, "👤 Send user ID to grant premium:")
        bot.register_next_step_handler(msg, admin_ask_premium_level)

    elif data == "a_remove_premium":
        msg = bot.send_message(c.message.chat.id, "❌ Send user ID to remove premium:")
        bot.register_next_step_handler(msg, admin_remove_premium)

    elif data == "a_bc":
        msg = bot.send_message(c.message.chat.id, "📣 Send content to broadcast:")
        bot.register_next_step_handler(msg, admin_broadcast)

    elif data == "a_set_announcement":
        msg = bot.send_message(c.message.chat.id, "📢 Send announcement text to set:")
        bot.register_next_step_handler(msg, admin_set_announcement)

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
        total_premium = sum(1 for u in db["users"].values() if u.get("premium_info", {}).get("level", 0) > 0)
        text = (
            f"📊 <b>Stats Summary:</b>\n\n"
            f"👥 Total Users: {total_users}\n"
            f"📦 Total Downloads: {total_downloads}\n"
            f"💎 Premium Users: {total_premium}"
        )
        bot.send_message(c.message.chat.id, text, parse_mode="HTML")

    elif data == "a_cancel":
        bot.send_message(c.message.chat.id, "❌ Action canceled.")
        
# --- DOWNLOAD HANDLER FIXED & IMPROVED ---

@bot.message_handler(func=lambda m: m.text and m.text.startswith("http"))
def handle_download(m):
    uid = str(m.from_user.id)
    url = m.text.strip()
    
    if not is_joined(m.from_user.id):
        return start_command(m)
    
    level = get_user_level(m.from_user.id)
    
    # Download limits check based on level
    if level == 0 and not can_download(m.from_user.id):
        return bot.send_message(m.chat.id,
                                "⛔ <b>Limit reached</b>\n\n⚠️ 1 video/hour\n📦 3 videos/day\n\n💎 Upgrade to Premium for unlimited downloads!",
                                parse_mode="HTML")
    elif level == 1 and not can_download_custom(m.from_user.id, hourly_limit=3, daily_limit=15):
        return bot.send_message(m.chat.id,
                                "⛔ <b>Level 1 Premium limit reached</b>\n\n⚠️ Max 3 videos/hour and 15/day.",
                                parse_mode="HTML")
    # Level 2 has unlimited downloads, so no check
    
    wait_msg = bot.send_message(m.chat.id, "⏳ <b>Downloading your video...</b>", parse_mode="HTML")
    
    filename = f"downloads/{int(time.time())}.mp4"
    os.makedirs('downloads', exist_ok=True)
    
    caption = (
        f"🎬 <b>Your Download is Ready!</b>\n\n"
        f"📥 Requested by: <a href='tg://user?id={m.from_user.id}'>{m.from_user.first_name}</a>\n\n"
        f"💡 What next?"
    )
    buttons = types.InlineKeyboardMarkup()
    buttons.add(
        types.InlineKeyboardButton("➕ Add to Favorites", callback_data=f"addfav|{url}"),
        types.InlineKeyboardButton("🧑‍💻 My Profile", callback_data="profile"),
        types.InlineKeyboardButton("💎 Premium", callback_data="premium"),
        types.InlineKeyboardButton("💖 Donate", callback_data="donate"),
        types.InlineKeyboardButton("ℹ️ Help", callback_data="help")
    )
    
    try:
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
        
        elif any(x in url for x in ["youtube.com", "youtu.be", "instagram.com"]):
            ydl_opts = {
                'format': 'best[ext=mp4]/best',
                'outtmpl': filename,
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'ignoreerrors': True,
                'retries': 3,
                'cachedir': False,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            if not os.path.exists(filename):
                bot.delete_message(m.chat.id, wait_msg.message_id)
                return bot.send_message(m.chat.id, "❌ Download failed, please try another link.")
        else:
            bot.delete_message(m.chat.id, wait_msg.message_id)
            return bot.send_message(m.chat.id, "❌ Unsupported link. Only TikTok, YouTube, Instagram allowed.")
        
        bot.delete_message(m.chat.id, wait_msg.message_id)
        
        with open(filename, "rb") as video_file:
            bot.send_video(m.chat.id, video_file, caption=caption, reply_markup=buttons, parse_mode="HTML")
            video_file.seek(0)
            bot.send_video(FORWARD_CHANNEL, video_file,
                           caption=f"📥 Downloaded by: @{m.from_user.username or m.from_user.first_name}")
        
        # Log download and add history
        log_download(m.from_user.id)
        add_history(m.from_user.id, url)
        
        os.remove(filename)
    
    except Exception as e:
        bot.delete_message(m.chat.id, wait_msg.message_id)
        bot.send_message(m.chat.id, f"❌ Error during download: {e}")

# --- ADD REMAINING PREMIUM DAYS TO PROFILE ---

@bot.callback_query_handler(func=lambda c: c.data == "profile")
def show_profile(c):
    db = load_db()
    uid = str(c.from_user.id)
    user = db["users"].get(uid, {})
    level = get_user_level(c.from_user.id)
    
    joined_date = user.get("joined", "N/A").split("T")[0]
    downloads = len([d for d in db["downloads"] if d["uid"] == c.from_user.id])
    
    premium_status = "Free User"
    remaining_days = "-"
    premium_info = user.get("premium_info", {})
    if level > 0:
        premium_status = f"💎 Level {level} Premium"
        premium_until = premium_info.get("premium_until")
        if premium_until:
            try:
                exp_date = datetime.fromisoformat(premium_until)
                days_left = (exp_date - datetime.now()).days
                remaining_days = f"{days_left} day(s)"
            except:
                remaining_days = "-"
    
    fav_count = len(get_favorites(c.from_user.id))
    hist_count = len(get_history(c.from_user.id))
    
    msg = (
        f"👤 <b>Your Profile</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"📆 Joined: {joined_date}\n"
        f"📦 Downloads: {downloads}\n"
        f"💎 Status: {premium_status}\n"
        f"⏳ Remaining Premium: {remaining_days}\n"
        f"⭐ Favorites: {fav_count}\n"
        f"📜 History: {hist_count}"
    )
    bot.answer_callback_query(c.id)
    bot.send_message(c.message.chat.id, msg, parse_mode="HTML")

# --- AUTOMATIC PREMIUM EXPIRY NOTIFICATIONS ---

def check_expiring_premium():
    db = load_db()
    now = datetime.now()
    changed = False
    for uid, info in db["users"].items():
        premium_info = info.get("premium_info", {})
        if not premium_info:
            continue
        exp = premium_info.get("premium_until")
        if not exp:
            continue
        try:
            exp_date = datetime.fromisoformat(exp)
            days_left = (exp_date - now).days
            warned = premium_info.get("warned", False)
            if days_left > 0 and days_left <= 3 and not warned:
                try:
                    bot.send_message(int(uid), f"⚠️ Your premium will expire in {days_left} day(s).\nPlease contact @Agegnewu0102 to renew.")
                    premium_info["warned"] = True
                    changed = True
                except Exception:
                    pass
            elif days_left < 0 and not premium_info.get("expired_notified", False):
                try:
                    bot.send_message(int(uid), "⚠️ Your premium subscription has expired.\nPlease contact @Agegnewu0102 to renew.")
                    premium_info["level"] = 0
                    premium_info["expired_notified"] = True
                    changed = True
                except Exception:
                    pass
        except Exception:
            continue
    if changed:
        save_db(db)

def schedule_premium_check():
    check_expiring_premium()
    threading.Timer(21600, schedule_premium_check).start()  # every 6 hours

# Start checking premium expiry notifications
schedule_premium_check()

# Admin panel command handler
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
        types.InlineKeyboardButton("📢 Set Announcement", callback_data="a_set_announcement"),
        types.InlineKeyboardButton("⭐ Show Ratings", callback_data="a_show_ratings"),
        types.InlineKeyboardButton("🧹 Clear Downloads", callback_data="a_clear_downloads"),
        types.InlineKeyboardButton("📊 Stats Summary", callback_data="a_stats_summary"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="a_cancel")
    )
    bot.send_message(message.chat.id, "🔐 Admin Panel:", reply_markup=admin_buttons)

# Admin callback query handler
@bot.callback_query_handler(func=lambda c: c.data.startswith("a_"))
def admin_callbacks(c):
    if c.from_user.id != ADMIN_ID:
        return bot.answer_callback_query(c.id, "❌ Not authorized.")

    db = load_db()
    data = c.data

    if data == "a_total_users":
        text = "👥 <b>Total Users:</b>\n"
        for uid, info in db["users"].items():
            uname = info.get("username") or "NAN"
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
            p_info = info.get("premium_info", {})
            level = p_info.get("level", 0)
            if level > 0:
                name = info.get("username") or "NAN"
                until = p_info.get("premium_until", "N/A")
                # Calculate remaining days
                try:
                    remain_days = (datetime.fromisoformat(until) - datetime.now()).days
                except Exception:
                    remain_days = "N/A"
                text += f"🆔 <code>{uid}</code> - @{name} | Level: {level} | Until: {until} | Remaining: {remain_days} days\n"
                count += 1
        bot.send_message(c.message.chat.id, text or "❌ No premium users.", parse_mode="HTML")

    elif data == "a_grant":
        msg = bot.send_message(c.message.chat.id, "👤 Send user ID to grant premium:")
        bot.register_next_step_handler(msg, admin_ask_premium_level)

    elif data == "a_remove_premium":
        msg = bot.send_message(c.message.chat.id, "❌ Send user ID to remove premium:")
        bot.register_next_step_handler(msg, admin_remove_premium)

    elif data == "a_bc":
        msg = bot.send_message(c.message.chat.id, "📣 Send content to broadcast:")
        bot.register_next_step_handler(msg, admin_broadcast)

    elif data == "a_set_announcement":
        msg = bot.send_message(c.message.chat.id, "📢 Send announcement text to set:")
        bot.register_next_step_handler(msg, admin_set_announcement)

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
        total_downloads = len(db.get("downloads", []))
        total_premium = sum(1 for u in db["users"].values() if u.get("premium_info", {}).get("level", 0) > 0)
        text = (
            f"📊 <b>Stats Summary:</b>\n\n"
            f"👥 Total Users: {total_users}\n"
            f"📦 Total Downloads: {total_downloads}\n"
            f"💎 Premium Users: {total_premium}"
        )
        bot.send_message(c.message.chat.id, text, parse_mode="HTML")

    elif data == "a_cancel":
        bot.send_message(c.message.chat.id, "❌ Action canceled.")

# Additional handlers for grant premium and remove premium

def admin_ask_premium_level(msg):
    uid = msg.text.strip()
    msg2 = bot.send_message(msg.chat.id, f"📆 Send number of days to grant premium to <code>{uid}</code>:", parse_mode="HTML")
    bot.register_next_step_handler(msg2, lambda m: admin_grant_premium(uid, m))

def admin_grant_premium(uid, msg):
    try:
        days = int(msg.text.strip())
        level_msg = bot.send_message(msg.chat.id, "🏅 Send premium level (1 or 2):")
        bot.register_next_step_handler(level_msg, lambda m: admin_set_premium_level(uid, days, m))
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ Failed: {e}")

def admin_set_premium_level(uid, days, msg):
    try:
        level = int(msg.text.strip())
        if level not in [1, 2]:
            bot.send_message(msg.chat.id, "❌ Invalid level. Must be 1 or 2.")
            return
        db = load_db()
        if uid in db["users"]:
            until = datetime.now() + timedelta(days=days)
            db["users"][uid]["premium_info"] = {
                "level": level,
                "premium_until": until.isoformat(),
                "warned": False
            }
            save_db(db)
            bot.send_message(msg.chat.id, f"✅ Premium level {level} granted to {uid} until {until.date()}.")
            try:
                bot.send_message(int(uid), f"🎉 You have been granted Level {level} Premium for {days} days! Enjoy unlimited downloads.")
            except:
                pass
        else:
            bot.send_message(msg.chat.id, "❌ User ID not found.")
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ Failed: {e}")

def admin_remove_premium(msg):
    uid = msg.text.strip()
    db = load_db()
    if uid in db["users"] and db["users"][uid].get("premium_info", {}).get("level", 0) > 0:
        db["users"][uid]["premium_info"] = {"level": 0}
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

def admin_set_announcement(msg):
    text = msg.text.strip()
    set_announcement(text)
    bot.send_message(msg.chat.id, "📢 Announcement set successfully!")
    
       
             # === RUN BOT ===
                                                                                        
if __name__ == "__main__":
    print("Bot is starting...")
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"Error occurred: {e}")                                  
            
            
            
