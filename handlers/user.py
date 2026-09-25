from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import get_session, get_or_create_user, Task, Submission, User
from config import ADMIN_IDS, is_admin

MAIN_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("📋 Tasks", callback_data="menu_tasks")],
    [InlineKeyboardButton("💰 Balance", callback_data="menu_balance"),
     InlineKeyboardButton("👥 Referral", callback_data="menu_referral")],
    [InlineKeyboardButton("❓ Help", callback_data="menu_help")],
])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    args = context.args

    referred_by = None
    if args and args[0].startswith("ref_"):
        try:
            ref_id = int(args[0].replace("ref_", ""))
            if ref_id != tg_user.id:
                referred_by = ref_id
        except ValueError:
            pass

    session = get_session()
    try:
        user, created = get_or_create_user(
            session,
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            referred_by=referred_by,
        )
        if created and referred_by:
            referrer = session.query(User).filter_by(telegram_id=referred_by).first()
            if referrer:
                from config import REFERRAL_BONUS
                referrer.balance += REFERRAL_BONUS
                session.commit()
                try:
                    await context.bot.send_message(
                        referrer.telegram_id,
                        f"🎉 আপনার রেফারেলে নতুন ইউজার জয়েন করেছে! +{REFERRAL_BONUS} যোগ হয়েছে।"
                    )
                except Exception:
                    pass
    finally:
        session.close()

    await update.message.reply_text(
        f"স্বাগতম, {tg_user.first_name}! 👋\n\n"
        "নিচের মেনু থেকে টাস্ক দেখুন, সম্পন্ন করুন এবং রিওয়ার্ড পান।",
        reply_markup=MAIN_MENU,
    )


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_main":
        await query.edit_message_text("মেনু থেকে বেছে নিন:", reply_markup=MAIN_MENU)
        return

    if data == "menu_tasks":
        await show_task_list(query, context)
        return

    if data == "menu_balance":
        await show_balance(query, context)
        return

    if data == "menu_referral":
        await show_referral(query, context)
        return

    if data == "menu_help":
        await query.edit_message_text(
            "ℹ️ কীভাবে কাজ করে:\n"
            "1️⃣ Tasks থেকে একটা টাস্ক বেছে নিন\n"
            "2️⃣ ইন্সট্রাকশন অনুযায়ী কাজ শেষ করুন\n"
            "3️⃣ প্রুফ (লিংক/ইউজারনেম/স্ক্রিনশট লিংক) সাবমিট করুন\n"
            "4️⃣ অ্যাডমিন রিভিউ করে অ্যাপ্রুভ করলে ব্যালেন্স যোগ হবে\n\n"
            "⬅️ মেনুতে ফিরতে নিচে চাপুন",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back", callback_data="menu_main")]]
            ),
        )
        return

    if data.startswith("task_"):
        task_id = int(data.split("_", 1)[1])
        await show_task_detail(query, context, task_id)
        return

    if data.startswith("submit_"):
        task_id = int(data.split("_", 1)[1])
        context.user_data["awaiting_proof_task_id"] = task_id
        await query.edit_message_text(
            "📝 এই টাস্কের প্রুফ (লিংক / ইউজারনেম / বিস্তারিত) মেসেজ করে পাঠান।\n\n"
            "বাতিল করতে /cancel পাঠান।"
        )
        return


async def show_task_list(query, context):
    session = get_session()
    try:
        tasks = session.query(Task).filter_by(is_active=True).all()
        if not tasks:
            await query.edit_message_text(
                "এই মুহূর্তে কোনো একটিভ টাস্ক নেই। পরে আবার চেক করুন।",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Back", callback_data="menu_main")]]
                ),
            )
            return

        buttons = []
        for t in tasks:
            label = f"{t.title} — {t.reward}$ [{t.category}]"
            buttons.append([InlineKeyboardButton(label, callback_data=f"task_{t.id}")])
        buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="menu_main")])

        await query.edit_message_text(
            "📋 এভেইলেবল টাস্ক লিস্ট:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    finally:
        session.close()


async def show_task_detail(query, context, task_id):
    session = get_session()
    try:
        task = session.query(Task).filter_by(id=task_id, is_active=True).first()
        if not task:
            await query.edit_message_text("এই টাস্কটি আর এভেইলেবল নেই।")
            return

        text = (
            f"📌 {task.title}\n"
            f"💵 রিওয়ার্ড: {task.reward}$\n"
            f"🏷️ ক্যাটাগরি: {task.category}\n\n"
            f"{task.description}"
        )
        buttons = [
            [InlineKeyboardButton("✅ কাজ শেষ, প্রুফ সাবমিট করব", callback_data=f"submit_{task.id}")],
            [InlineKeyboardButton("⬅️ Back", callback_data="menu_tasks")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    finally:
        session.close()


async def show_balance(query, context):
    session = get_session()
    try:
        user = session.query(User).filter_by(telegram_id=query.from_user.id).first()
        balance = user.balance if user else 0.0
        pending = 0
        if user:
            pending = session.query(Submission).filter_by(user_id=user.id, status="pending").count()

        await query.edit_message_text(
            f"💰 আপনার ব্যালেন্স: {balance:.2f}$\n"
            f"⏳ পেন্ডিং সাবমিশন: {pending} টি",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back", callback_data="menu_main")]]
            ),
        )
    finally:
        session.close()


async def show_referral(query, context):
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{query.from_user.id}"

    session = get_session()
    try:
        count = session.query(User).filter_by(referred_by=query.from_user.id).count()
    finally:
        session.close()

    await query.edit_message_text(
        f"👥 আপনার রেফারেল লিংক:\n{link}\n\n"
        f"✅ এখন পর্যন্ত রেফার করেছেন: {count} জন",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Back", callback_data="menu_main")]]
        ),
    )


async def receive_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_id = context.user_data.get("awaiting_proof_task_id")
    if not task_id:
        return

    proof_text = update.message.text
    tg_user = update.effective_user

    session = get_session()
    try:
        user, _ = get_or_create_user(
            session, telegram_id=tg_user.id,
            username=tg_user.username, first_name=tg_user.first_name,
        )
        task = session.query(Task).filter_by(id=task_id).first()
        if not task:
            await update.message.reply_text("টাস্কটি খুঁজে পাওয়া যায়নি।")
            context.user_data.pop("awaiting_proof_task_id", None)
            return

        submission = Submission(user_id=user.id, task_id=task.id, proof=proof_text, status="pending")
        session.add(submission)
        session.commit()

        context.user_data.pop("awaiting_proof_task_id", None)
        await update.message.reply_text(
            "✅ আপনার প্রুফ সাবমিট হয়েছে। অ্যাডমিন রিভিউ করার পর ব্যালেন্স যোগ হবে।",
            reply_markup=MAIN_MENU,
        )

        for admin_id in ADMIN_IDS:
            try:
                from telegram import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Mk
                kb = Mk([[
                    Btn("✅ Approve", callback_data=f"approve_{submission.id}"),
                    Btn("❌ Reject", callback_data=f"reject_{submission.id}"),
                ]])
                await context.bot.send_message(
                    admin_id,
                    f"🆕 নতুন সাবমিশন #{submission.id}\n"
                    f"টাস্ক: {task.title} ({task.reward}$)\n"
                    f"ইউজার: {tg_user.first_name} (@{tg_user.username or '-'}, id: {tg_user.id})\n"
                    f"প্রুফ: {proof_text}",
                    reply_markup=kb,
                )
            except Exception:
                pass
    finally:
        session.close()


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("awaiting_proof_task_id", None)
    await update.message.reply_text("বাতিল করা হয়েছে।", reply_markup=MAIN_MENU)
