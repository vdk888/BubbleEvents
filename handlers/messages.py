from telegram import Update
from telegram.ext import ContextTypes
from config.categories import CATEGORY_DESCRIPTIONS

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, event_bot):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    profile = event_bot.user_profiles.get(user_id)

    if context.user_data.get("awaiting_address"):
        profile.address = text
        event_bot.save_profile(user_id)
        context.user_data.pop("awaiting_address", None)
        await update.message.reply_text(f"📍 Address set to: {text}")
    
    elif context.user_data.get("awaiting_category_response"):
        if not text.lower() == 'skip':
            profile.interests[profile.current_category] = text
        
        categories = list(CATEGORY_DESCRIPTIONS.keys())
        current_index = categories.index(profile.current_category)
        
        if current_index + 1 < len(categories):
            profile.current_category = categories[current_index + 1]
            await ask_category_interest(update, context, profile.current_category)
        else:
            context.user_data.pop("awaiting_category_response", None)
            profile.current_category = None
            event_bot.save_profile(user_id)
            
            summary = "✨ Here's a summary of your interests:\n\n"
            for cat, interests in profile.interests.items():
                summary += f"*{cat.title()}*:\n{interests}\n\n"
            summary += "You can update your interests anytime using /setinterests"
            
            await update.message.reply_text(summary, parse_mode="Markdown")
    
    elif context.user_data.get("awaiting_email"):
        profile.email = text
        event_bot.save_profile(user_id)
        context.user_data.pop("awaiting_email", None)
        await update.message.reply_text(f"📧 Email set to: {text}")

async def ask_category_interest(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str):
    category_info = CATEGORY_DESCRIPTIONS[category]
    message = (
        f"📋 *{category.title()} Interests*\n\n"
        f"{category_info['question']}\n\n"
        f"💡 {category_info['example']}\n\n"
        "Please describe your interests in natural language, or type 'skip' if you're not interested in this category."
    )
    await update.message.reply_text(message, parse_mode="Markdown")
    context.user_data["awaiting_category_response"] = True 