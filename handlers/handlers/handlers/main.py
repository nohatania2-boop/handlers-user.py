import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters,
)

from config import BOT_TOKEN
from database import init_db
from handlers import user, admin

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

    def log_message(self, format, *args):
        pass


def start_health_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    server.serve_forever()


def main():
    init_db()

    threading.Thread(target=start_health_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", user.start))
    app.add_handler(CommandHandler("cancel", user.cancel))
    app.add_handler(CallbackQueryHandler(
        user.menu_callback,
        pattern=r"^(menu_|task_|submit_)",
    ))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user.receive_proof), group=1)

    addtask_conv = ConversationHandler(
        entry_points=[CommandHandler("addtask", admin.addtask_start)],
        states={
            admin.TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.addtask_title)],
            admin.DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.addtask_description)],
            admin.CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.addtask_category)],
            admin.REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.addtask_reward)],
        },
        fallbacks=[CommandHandler("cancel", admin.addtask_cancel)],
    )
    app.add_handler(addtask_conv)

    app.add_handler(CommandHandler("tasks", admin.list_tasks))
    app.add_handler(CommandHandler("stats", admin.stats))

    app.add_handler(CallbackQueryHandler(admin.admin_task_callback, pattern=r"^(toggletask_|deltask_)"))
    app.add_handler(CallbackQueryHandler(admin.review_callback, pattern=r"^(approve_|reject_)"))

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
