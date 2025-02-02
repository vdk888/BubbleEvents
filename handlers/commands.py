from telegram import Update
from telegram.ext import ContextTypes
from config.categories import CATEGORY_DESCRIPTIONS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, event_bot):
    user_id = update.effective_user.id
    if user_id not in event_bot.user_profiles:
        event_bot.user_profiles[user_id] = UserProfile()
        event_bot.save_profile(user_id)
    welcome_message = (
        "🌟 Welcome to EventFinder Bot! 🌟\n\n"
        "Configure your settings:\n"
        "/setaddress - Set your location\n"
        "/setinterests - Set your interests\n"
        "/setemail - Set your email address (for event details)\n"
        "/example - Show example event"
    )
    await update.message.reply_text(welcome_message)

async def set_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please enter your address (e.g., '123 Main St, City'):")
    context.user_data["awaiting_address"] = True

async def set_interests(update: Update, context: ContextTypes.DEFAULT_TYPE, event_bot):
    user_id = update.effective_user.id
    if user_id not in event_bot.user_profiles:
        event_bot.user_profiles[user_id] = UserProfile()
    
    profile = event_bot.user_profiles[user_id]
    profile.interests = {}
    profile.current_category = list(CATEGORY_DESCRIPTIONS.keys())[0]
    
    await ask_category_interest(update, context, profile.current_category)

async def set_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please enter your email address:")
    context.user_data["awaiting_email"] = True

async def example_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sample_event = {
        "title": "Virtual Reality Night @ TechHub",
        "description": "Experience the latest in VR technology. Friday 8PM at TechHub.",
        "date": "Not specified",
        "location": "TechHub",
    }
    message = await format_event_message(sample_event)
    keyboard = [
        [
            InlineKeyboardButton("👍", callback_data="like_123"),
            InlineKeyboardButton("👎", callback_data="dislike_123"),
        ]
    ]
    await update.message.reply_text(
        text=f"Example Event:\n\n{message}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    ) 