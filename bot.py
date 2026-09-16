import asyncio
import time
import logging
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.constants import ChatMemberStatus
from telegram.ext import (Application, CommandHandler, MessageHandler,
                          CallbackQueryHandler, ContextTypes, filters)

import config
import database as db
from api import send_likes

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

# ================= ضد اسپم =================
# هر کاربر: لیست timestamp پیام‌های اخیر | کاربران سنگین: uid -> تا کِی ساکت باشه
_msg_log = defaultdict(list)
_muted = defaultdict(float)   # در گروه: chat_id -> user_id

def check_spam(update: Update) -> bool:
    """True = مجاز، False = اسپمر (پیام نباید پردازش بشه)"""
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    key = (chat_id, uid)
    now = time.time()
    if now < _muted.get(key, 0):
        return False
    _msg_log[key] = [t for t in _msg_log[key] if now - t < config.SPAM_WINDOW]
    _msg_log[key].append(now)
    if len(_msg_log[key]) > config.SPAM_MAX_MSGS:
        _muted[key] = now + config.SPAM_PENALTY
        _msg_log[key].clear()
        return False
    return True

# ================= کمکی‌ها =================

def is_admin(uid):
    return uid == config.OWNER_ID or (db.get_user(uid) or {}).get("is_admin", 0)

def fmt_time(seconds):
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)} ساعت و {int(m)} دقیقه و {int(s)} ثانیه"

def main_menu(admin=False):
    kb = [
        [InlineKeyboardButton("🔥 ارسال لایک فری فایر", callback_data="send_like"),
         InlineKeyboardButton("📊 وضعیت من", callback_data="status")],
        [InlineKeyboardButton("👥 دعوت دوستان 🎁", callback_data="referral"),
         InlineKeyboardButton("ℹ️ راهنما", callback_data="help")],
    ]
    if admin:
        kb.append([InlineKeyboardButton("🛠 پنل مدیریت", callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)

async def check_joined(bot, uid) -> list:
    """لیست کانال‌هایی که کاربر جویین نشده"""
    not_joined = []
    for ch in db.get_channels():
        try:
            m = await bot.get_chat_member(ch, uid)
            if m.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
                not_joined.append(ch)
        except Exception:
            not_joined.append(ch)   # اگر ربات تو کانال ادمین نباشه، محتاط باش
    return not_joined

def join_keyboard(channels):
    rows = [[InlineKeyboardButton(f"📢 عضویت در {ch}", url=f"https://t.me/{ch.lstrip('@')}")] for ch in channels]
    rows.append([InlineKeyboardButton("✅ تایید عضویت", callback_data="check_join")])
    return InlineKeyboardMarkup(rows)

# ================= دستورات =================

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_spam(update):
        return
    u = update.effective_user
    ref_by = 0
    if ctx.args and ctx.args[0].lstrip("-").isdigit() and int(ctx.args[0]) != u.id:
        ref_by = int(ctx.args[0])
    db.add_user(u.id, u.username or u.first_name, ref_by)
    await update.message.reply_text(
        f"سلام {u.first_name} عزیز 👋\n\n"
        "🔥 به ربات لایک فری فایر خوش اومدی!\n\n"
        f"✅ هر ۲۴ ساعت یک‌بار {config.LIKES_PER_REQUEST} لایک رایگان\n"
        "👥 با دعوت دوستان لایک اضافه بدون کول‌داون بگیر!\n\n"
        "👇 از دکمه‌ها استفاده کن:",
        reply_markup=main_menu(is_admin(u.id)))

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_spam(update):
        return
    await update.message.reply_text(
        "📖 راهنما:\n\n"
        "🔥 /start - شروع و منوی اصلی\n"
        "❌ /cancel - لغو عملیات\n\n"
        "1️⃣ روی «ارسال لایک» بزن\n"
        "2️⃣ UID اکانتت رو بفرست\n"
        f"3️⃣ {config.LIKES_PER_REQUEST} لایک برات ارسال می‌شه!\n\n"
        "⏰ محدودیت: هر ۲۴ ساعت یک‌بار\n"
        "👥 هر دعوت موفق = ۱ لایک اضافه بدون کول‌داون")

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("✅ لغو شد.",
        reply_markup=main_menu(is_admin(update.effective_user.id)))

# ================= پیام همگانی (با دکمه) =================

async def broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    if not ctx.args:
        await update.message.reply_text("❌ استفاده: /send متن پیام")
        return
    text = " ".join(ctx.args)
    uids = db.all_uids()
    ok = fail = 0
    msg = await update.message.reply_text(f"📡 در حال ارسال به {len(uids)} کاربر... (0%)")
    for i, target in enumerate(uids, 1):
        try:
            await ctx.bot.send_message(target, text)
            ok += 1
        except Exception:
            fail += 1
        if i % 50 == 0:
            try: await msg.edit_text(f"📡 در حال ارسال... ({i}/{len(uids)})")
            except Exception: pass
        await asyncio.sleep(0.05)
    await msg.edit_text(f"✅ پیام همگانی تمام شد!\n✔️ موفق: {ok}\n❌ ناموفق: {fail}")

# ================= دکمه‌ها =================

async def button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    user = db.get_user(uid) or {}
    await q.answer()

    # --- تایید عضویت ---
    if q.data == "check_join":
        not_joined = await check_joined(ctx.bot, uid)
        if not_joined:
            await q.edit_message_text("⛔️ هنوز عضو همه کانال‌ها نشدی!\nاول عضو شو، بعد «تایید عضویت» رو بزن:",
                                      reply_markup=join_keyboard(not_joined))
        else:
            await q.edit_message_text("✅ ممنون که عضو شدی! حالا می‌تونی از ربات استفاده کنی 👇",
                                      reply_markup=main_menu(is_admin(uid)))
        return

    # --- پنل مدیریت اصلی ---
    if q.data == "admin_panel":
        if not is_admin(uid):
            await q.answer("⛔️ دسترسی نداری!", show_alert=True)
            return
        total, today, banned = db.stats()
        channels = db.get_channels()
        kb = [
            [InlineKeyboardButton("👤 مدیریت کاربر", callback_data="a_users"),
             InlineKeyboardButton("📊 آمار ربات", callback_data="a_stats")],
            [InlineKeyboardButton("📢 مدیریت کانال‌های جوین اجباری", callback_data="a_channels")],
            [InlineKeyboardButton("📣 پیام همگانی", callback_data="a_broadcast"),
             InlineKeyboardButton("ℹ️ اطلاعات ربات", callback_data="a_info")],
            [InlineKeyboardButton("🔙 برگشت", callback_data="back_main")],
        ]
        await q.edit_message_text(
            f"🛠 *پنل مدیریت*\n\n👥 کل کاربران: {total}\n🔥 فعال ۲۴ ساعت: {today}\n🚫 بن‌شده: {banned}\n"
            f"📢 کانال‌ها: {len(channels)}",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return

    # --- مدیریت کاربر ---
    if q.data == "a_users":
        if not is_admin(uid): return
        kb = [
            [InlineKeyboardButton("👑 تعیین ادمین", callback_data="a_addadmin"),
             InlineKeyboardButton("🚫 بن کاربر", callback_data="a_ban")],
            [InlineKeyboardButton("♻️ ریست کول‌داون", callback_data="a_reset"),
             InlineKeyboardButton("➕ لایک اضافی بده", callback_data="a_bonus")],
            [InlineKeyboardButton("🔍 اطلاعات کاربر", callback_data="a_userinfo"),
             InlineKeyboardButton("🔓 رفع بن", callback_data="a_unban")],
            [InlineKeyboardButton("🔙 برگشت", callback_data="admin_panel")],
        ]
        await q.edit_message_text("👤 مدیریت کاربر - یکی رو انتخاب کن:",
                                  reply_markup=InlineKeyboardMarkup(kb))
        return

    if q.data == "a_stats":
        if not is_admin(uid): return
        total, today, banned = db.stats()
        await q.answer(f"👥 کل: {total} | 🔥 امروز: {today} | 🚫 بن: {banned}", show_alert=True)
        return

    if q.data == "a_info":
        if not is_admin(uid): return
        me = await ctx.bot.get_me()
        await q.answer(f"🤖 @{me.username} | ID: {me.id}", show_alert=True)
        return

    if q.data == "a_broadcast":
        if not is_admin(uid): return
        ctx.user_data["admin_action"] = "a_broadcast"
        await q.edit_message_text("📣 متن پیام همگانی رو بفرست (برای همه کاربران ارسال می‌شه):")
        return

    # --- مدیریت کانال‌های جوین اجباری ---
    if q.data == "a_channels":
        if not is_admin(uid): return
        channels = db.get_channels()
        kb = [[InlineKeyboardButton(f"❌ حذف {ch}", callback_data=f"delch:{ch}")] for ch in channels]
        kb += [[InlineKeyboardButton("➕ اضافه کردن کانال", callback_data="a_addch")],
               [InlineKeyboardButton("🔙 برگشت", callback_data="admin_panel")]]
        txt = "📢 *کانال‌های جوین اجباری:*\n" + ("\n".join(f"• {ch}" for ch in channels) if channels else "هیچ کانالی ثبت نشده!")
        await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return

    if q.data == "a_addch":
        if not is_admin(uid): return
        ctx.user_data["admin_action"] = "a_addch"
        await q.edit_message_text("➕ یوزرنیم کانال رو بفرست (مثال: @MyChannel):")
        return

    if q.data.startswith("delch:"):
        if not is_admin(uid): return
        ch = q.data.split(":", 1)[1]
        ok = db.del_channel(ch)
        channels = db.get_channels()
        kb = [[InlineKeyboardButton(f"❌ حذف {c}", callback_data=f"delch:{c}")] for c in channels]
        kb += [[InlineKeyboardButton("➕ اضافه کردن کانال", callback_data="a_addch")],
               [InlineKeyboardButton("🔙 برگشت", callback_data="admin_panel")]]
        await q.edit_message_text(f"{'✅ حذف شد!' if ok else '❌ پیدا نشد!'}",
                                  reply_markup=InlineKeyboardMarkup(kb))
        return

    if q.data == "back_main":
        await q.edit_message_text("منوی اصلی 👇", reply_markup=main_menu(is_admin(uid)))
        return

    # --- وضعیت من ---
    if q.data == "status":
        if user.get("banned"):
            await q.answer("⛔️ شما بن هستید!", show_alert=True)
            return
        can, remain = db.can_like(user)
        me = await ctx.bot.get_me()
        ref_link = f"https://t.me/{me.username}?start={uid}"
        txt = (f"📊 وضعیت شما:\n\n👥 دعوت‌های موفق: {user.get('referrals',0)}\n"
               f"🎁 لایک اضافی باقی‌مانده: {user.get('bonus',0)}\n"
               f"🔗 لینک دعوت:\n`{ref_link}`\n\n")
        txt += "✅ الان می‌تونی لایک بزنی!" if can else f"⏳ زمان باقی‌مانده تا لایک بعدی: {fmt_time(remain)}"
        await q.edit_message_text(txt, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 برگشت", callback_data="back_main")]]))
        return

    # --- رفرال ---
    if q.data == "referral":
        me = await ctx.bot.get_me()
        ref_link = f"https://t.me/{me.username}?start={uid}"
        await q.edit_message_text(
            f"👥 با دعوت دوستانت پاداش بگیر!\n\n"
            f"🎁 هر دعوت موفق = {config.REFERRAL_REWARD_LIKES} لایک اضافه (بدون کول‌داون ۲۴ ساعته)\n\n"
            f"🔗 لینک دعوتت:\n`{ref_link}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 برگشت", callback_data="back_main")]]))
        return

    # --- راهنما ---
    if q.data == "help":
        await q.edit_message_text(
            "📖 راهنما:\n\n🔥 «ارسال لایک» رو بزن و UID بفرست\n"
            f"⏰ هر ۲۴ ساعت یک‌بار {config.LIKES_PER_REQUEST} لایک\n"
            "👥 دعوت دوستان = لایک اضافه",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 برگشت", callback_data="back_main")]]))
        return

    # --- شروع ارسال لایک (چک جوین اجباری) ---
    if q.data == "send_like":
        if user.get("banned"):
            await q.answer("⛔️ شما بن هستید!", show_alert=True)
            return
        not_joined = await check_joined(ctx.bot, uid)
        if not_joined:
            await q.edit_message_text("⛔️ برای استفاده از ربات، اول عضو این کانال‌ها شو:",
                                      reply_markup=join_keyboard(not_joined))
            return
        can, remain = db.can_like(user)
        if not can:
            await q.answer(f"⏳ فقط هر ۲۴ ساعت یک‌بار!\nزمان باقی‌مانده: {fmt_time(remain)}", show_alert=True)
            return
        await q.edit_message_text("🆔 لطفاً UID اکانت فری فایر خودت رو بفرست:")
        ctx.user_data["awaiting_uid"] = True
        return

    # --- اکشن‌های ادمین (گرفتن ورودی) ---
    actions = {"a_addadmin": "👑 آیدی عددی ادمین جدید رو بفرست:",
               "a_ban": "🚫 آیدی عددی کاربر برای بن رو بفرست:",
               "a_unban": "🔓 آیدی عددی کاربر برای رفع بن رو بفرست:",
               "a_reset": "♻️ آیدی کاربر برای ریست کول‌داون رو بفرست:",
               "a_bonus": "➕ آیدی کاربر برای لایک اضافی رو بفرست:",
               "a_userinfo": "🔍 آیدی عددی کاربر رو بفرست:"}
    if q.data in actions:
        if not is_admin(uid): return
        ctx.user_data["admin_action"] = q.data
        await q.edit_message_text(actions[q.data])
        return

# ================= تایید ارسال لایک =================

async def confirm_like(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    user = db.get_user(uid)
    await q.answer()
    if not ctx.user_data.get("pending_uid"):
        await q.edit_message_text("❌ خطا! از منو دوباره شروع کن.")
        return
    can, remain = db.can_like(user)
    if not can:
        await q.edit_message_text(f"⏳ محدودیت ۲۴ ساعته!\nزمان باقی‌مانده: {fmt_time(remain)}")
        return
    game_uid = ctx.user_data.pop("pending_uid")
    await q.edit_message_text("⏳ در حال ارسال لایک... لطفاً صبر کن!")
    result = await asyncio.to_thread(send_likes, game_uid)
    if result["ok"]:
        db.consume_like(user)
        await ctx.bot.send_message(uid,
            f"✅ لایک با موفقیت ارسال شد!\n\n🔥 {config.LIKES_PER_REQUEST} لایک به UID `{game_uid}` ارسال شد!\n"
            f"⏳ لایک بعدی: ۲۴ ساعت دیگه\n👥 دوستانت رو دعوت کن تا لایک اضافه بگیری!",
            parse_mode="Markdown", reply_markup=main_menu(is_admin(uid)))
    else:
        await ctx.bot.send_message(uid,
            f"❌ Request rejected\n\nدرخواست لایک برای UID `{game_uid}` رد شد!\n"
            "دوباره تلاش کن یا با پشتیبانی در تماس باش.",
            parse_mode="Markdown", reply_markup=main_menu(is_admin(uid)))

# ================= پیام‌ها =================

async def message_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not check_spam(update):
        return
    uid = update.effective_user.id
    text = update.message.text.strip()
    data = ctx.user_data

    # پنل ادمین
    if data.get("admin_action"):
        if not is_admin(uid): return
        action = data.pop("admin_action")

        if action == "a_broadcast":
            uids = db.all_uids()
            ok = fail = 0
            msg = await update.message.reply_text(f"📡 در حال ارسال به {len(uids)} کاربر...")
            for i, t in enumerate(uids, 1):
                try:
                    await ctx.bot.send_message(t, text); ok += 1
                except Exception: fail += 1
                if i % 50 == 0:
                    try: await msg.edit_text(f"📡 ارسال... ({i}/{len(uids)})")
                    except Exception: pass
                await asyncio.sleep(0.05)
            await msg.edit_text(f"✅ تمام شد!\n✔️ موفق: {ok}\n❌ ناموفق: {fail}")
            return

        if action == "a_addch":
            ch = text.strip()
            if not ch.startswith("@"):
                await update.message.reply_text("❌ فرمت باید با @ شروع بشه! دوباره بفرست.")
                return
            db.add_channel(ch)
            await update.message.reply_text(f"✅ کانال {ch} به جوین اجباری اضافه شد!")
            return

        if action == "a_userinfo":
            if not text.lstrip("-").isdigit():
                await update.message.reply_text("❌ آیدی باید عدد باشه!")
                return
            u = db.get_user(int(text))
            if u:
                await update.message.reply_text(
                    f"🔍 اطلاعات کاربر {text}:\n\n"
                    f"👤 یوزرنیم: @{u['username']}\n"
                    f"👥 دعوت‌ها: {u['referrals']}\n🎁 لایک اضافی: {u['bonus']}\n"
                    f"🚫 بن: {'بله' if u['banned'] else 'خیر'}\n"
                    f"👑 ادمین: {'بله' if u['is_admin'] else 'خیر'}\n"
                    f"⏰ آخرین لایک: {time.strftime('%Y-%m-%d %H:%M', time.localtime(u['last_like'])) if u['last_like'] else 'هرگز'}")
            else:
                await update.message.reply_text("❌ کاربر پیدا نشد!")
            return

        if not text.lstrip("-").isdigit():
            await update.message.reply_text("❌ آیدی باید عدد باشه!")
            return
        target = int(text)
        if action == "a_addadmin":
            db.add_user(target, "-"); db.set_admin(target, 1)
            await update.message.reply_text(f"✅ {target} ادمین شد!")
        elif action == "a_ban":
            db.ban(target, 1); await update.message.reply_text(f"🚫 {target} بن شد!")
        elif action == "a_unban":
            db.ban(target, 0); await update.message.reply_text(f"🔓 بن {target} برداشته شد!")
        elif action == "a_reset":
            db.reset_cooldown(target); await update.message.reply_text(f"♻️ کول‌داون {target} ریست شد!")
        elif action == "a_bonus":
            db.add_bonus(target, 1); await update.message.reply_text(f"➕ ۱ لایک اضافی به {target} داده شد!")
        return

    # دریافت UID فری فایر
    if data.get("awaiting_uid"):
        if not text.isdigit() or len(text) < 6:
            await update.message.reply_text("❌ UID نامعتبره! UID فقط عدده. دوباره بفرست یا /cancel")
            return
        data["awaiting_uid"] = False
        data["pending_uid"] = text
        kb = [[InlineKeyboardButton("✅ تایید و ارسال لایک", callback_data="confirm_like"),
               InlineKeyboardButton("❌ لغو", callback_data="back_main")]]
        await update.message.reply_text(
            f"🆔 UID: `{text}`\n🔥 تعداد لایک: {config.LIKES_PER_REQUEST}\n\nتایید می‌کنی؟",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return

    await update.message.reply_text("از منوی پایین استفاده کن 👇",
                                    reply_markup=main_menu(is_admin(uid)))

# ================= اجرا =================

def main():
    db.init()
    app = Application.builder().token(config.BOT_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("send", broadcast))
    app.add_handler(CallbackQueryHandler(confirm_like, pattern="^confirm_like$"))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("🤖 Bot is running... (Ctrl+C برای خاموش کردن)")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()