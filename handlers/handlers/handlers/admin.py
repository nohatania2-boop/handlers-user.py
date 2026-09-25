from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import get_session, Task, Submission, User
from config import is_admin

TITLE, DESCRIPTION, CATEGORY, REWARD = range(4)


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not is_admin(user_id):
            if update.message:
                await update.message.reply_text("⛔ এই কমান্ড শুধু অ্যাডমিনের জন্য।")
            return ConversationHandler.END
        return await func(update, context)
    return wrapper


@admin_only
async def addtask_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📌 টাস্কের টাইটেল দিন (বা /cancel):")
    return TITLE


async def addtask_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_task_title"] = update.message.text
    await update.message.reply_text("📝 টাস্কের বিস্তারিত/ইন্সট্রাকশন দিন:")
    return DESCRIPTION


async def addtask_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_task_description"] = update.message.text
    await update.message.reply_text("🏷️ ক্যাটাগরি দিন (যেমন: gmail / telegram / other):")
    return CATEGORY


async def addtask_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_task_category"] = update.message.text.strip().lower()
    await update.message.reply_text("💵 রিওয়ার্ড এমাউন্ট দিন (শুধু সংখ্যা, যেমন 0.20):")
    return REWARD


async def addtask_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        reward = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("সঠিক সংখ্যা দিন, যেমন 0.20:")
        return REWARD

    session = get_session()
    try:
        task = Task(
            title=context.user_data.pop("new_task_title"),
            description=context.user_data.pop("new_task_description"),
            category=context.user_data.pop("new_task_category"),
            reward=reward,
            is_active=True,
        )
        session.add(task)
        session.commit()
        await update.message.reply_text(f"✅ টাস্ক '{task.title}' যোগ হয়েছে (id: {task.id})।")
    finally:
        session.close()

    return ConversationHandler.END


async def addtask_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for k in ["new_task_title", "new_task_description", "new_task_category"]:
        context.user_data.pop(k, None)
    await update.message.reply_text("টাস্ক অ্যাড বাতিল করা হয়েছে।")
    return ConversationHandler.END


@admin_only
async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_session()
    try:
        tasks = session.query(Task).all()
        if not tasks:
            await update.message.reply_text("কোনো টাস্ক নেই।")
            return
        for t in tasks:
            status = "🟢 Active" if t.is_active else "🔴 Inactive"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🔴 Deactivate" if t.is_active else "🟢 Activate",
                    callback_data=f"toggletask_{t.id}",
                ),
                InlineKeyboardButton("🗑 Delete", callback_data=f"deltask_{t.id}"),
            ]])
            await update.message.reply_text(
                f"#{t.id} {t.title} — {t.reward}$ [{t.category}] {status}\n{t.description}",
                reply_markup=kb,
            )
    finally:
        session.close()


async def admin_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ অনুমতি নেই।", show_alert=True)
        return
    await query.answer()

    data = query.data
    session = get_session()
    try:
        if data.startswith("toggletask_"):
            task_id = int(data.split("_", 1)[1])
            task = session.query(Task).filter_by(id=task_id).first()
            if task:
                task.is_active = not task.is_active
                session.commit()
                await query.edit_message_text(
                    f"#{task.id} {task.title} — এখন {'🟢 Active' if task.is_active else '🔴 Inactive'}"
                )
        elif data.startswith("deltask_"):
            task_id = int(data.split("_", 1)[1])
            task = session.query(Task).filter_by(id=task_id).first()
            if task:
                session.delete(task)
                session.commit()
                await query.edit_message_text(f"🗑 টাস্ক #{task_id} ডিলিট করা হয়েছে।")
    finally:
        session.close()


async def review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ অনুমতি নেই।", show_alert=True)
        return
    await query.answer()

    action, sub_id = query.data.split("_", 1)
    sub_id = int(sub_id)

    session = get_session()
    try:
        submission = session.query(Submission).filter_by(id=sub_id).first()
        if not submission or submission.status != "pending":
            await query.edit_message_text("এই সাবমিশন আগেই প্রসেস হয়ে গেছে।")
            return

        user = session.query(User).filter_by(id=submission.user_id).first()
        task = session.query(Task).filter_by(id=submission.task_id).first()

        if action == "approve":
            submission.status = "approved"
            user.balance += task.reward
            session.commit()
            await query.edit_message_text(f"✅ সাবমিশন #{sub_id} অ্যাপ্রুভ করা হয়েছে। {user.first_name} কে {task.reward}$ যোগ হয়েছে।")
            try:
                await context.bot.send_message(
                    user.telegram_id,
                    f"🎉 আপনার '{task.title}' টাস্কের সাবমিশন অ্যাপ্রুভ হয়েছে! +{task.reward}$ যোগ হয়েছে।"
                )
            except Exception:
                pass
        else:
            submission.status = "rejected"
            session.commit()
            await query.edit_message_text(f"❌ সাবমিশন #{sub_id} রিজেক্ট করা হয়েছে।")
            try:
                await context.bot.send_message(
                    user.telegram_id,
                    f"⚠️ দুঃখিত, আপনার '{task.title}' টাস্কের সাবমিশন রিজেক্ট হয়েছে। সঠিক প্রুফসহ আবার চেষ্টা করুন।"
                )
            except Exception:
                pass
    finally:
        session.close()


@admin_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_session()
    try:
        total_users = session.query(User).count()
        total_tasks = session.query(Task).filter_by(is_active=True).count()
        pending = session.query(Submission).filter_by(status="pending").count()
        approved = session.query(Submission).filter_by(status="approved").count()
        await update.message.reply_text(
            f"📊 পরিসংখ্যান\n"
            f"👥 মোট ইউজার: {total_users}\n"
            f"📋 একটিভ টাস্ক: {total_tasks}\n"
            f"⏳ পেন্ডিং সাবমিশন: {pending}\n"
            f"✅ অ্যাপ্রুভড সাবমিশন: {approved}"
        )
    finally:
        session.close()
