from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from datetime import timedelta, datetime
import logging
import asyncio

from config.settings import CONFIG
from services.logging_service import setup_logging
from models.user_profile import EventBot
from handlers.commands import start, set_address, set_interests, set_email, example_event
from handlers.messages import handle_message
from handlers.callbacks import handle_feedback
from services.event_service import search_events

# Global state
event_bot = EventBot(CONFIG)
pending_event_details = {}

async def log_wake_up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        user_id = update.effective_user.id
        logging.info(f"Bot woken up by user {user_id} at {datetime.now()}")
    return True

def main():
    setup_logging()
    token = CONFIG["telegram_token"]
    logging.info(f"Initializing bot with token: {token[:8]}...{token[-4:]}")
    
    try:
        application = Application.builder().token(token).build()
        
        # Add handlers
        application.add_handler(MessageHandler(filters.ALL, log_wake_up), group=-1)
        application.add_handler(CommandHandler("start", lambda update, context: start(update, context, event_bot)))
        application.add_handler(CommandHandler("setaddress", set_address))
        application.add_handler(CommandHandler("setinterests", lambda update, context: set_interests(update, context, event_bot)))
        application.add_handler(CommandHandler("setemail", set_email))
        application.add_handler(CommandHandler("example", example_event))
        application.add_handler(CallbackQueryHandler(
            lambda update, context: handle_feedback(update, context, event_bot, CONFIG, pending_event_details)
        ))
        application.add_handler(MessageHandler(
            filters.TEXT & (~filters.COMMAND),
            lambda update, context: handle_message(update, context, event_bot)
        ))

        # Schedule notifications
        if application.job_queue:
            logging.info("Setting up job queue for periodic notifications...")
            application.job_queue.run_repeating(
                lambda context: search_events(context, event_bot, CONFIG, pending_event_details),
                interval=timedelta(hours=CONFIG["search_interval_hours"]),
                first=10,
            )
        else:
            logging.warning("Job queue is not available. Periodic notifications will not be scheduled.")

        logging.info("Bot started and ready to handle messages")
        
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    except Exception as e:
        logging.error(f"Failed to initialize bot: {str(e)}")
        raise

if __name__ == "__main__":
    main() 