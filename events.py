"""
EventFinder Bot
Author: Joris Dupraz <jorisdupraz@gmail.com>

This Telegram bot allows users to find events near their location based on their interests.
Features:
- Users can set their address, interests, and email.
- The bot queries an external Perplexity API to retrieve events.
- The API response is parsed into a list of events (with title, date, location, description, and URL).
- Each event is given a unique hash to prevent duplicate notifications.
- Sent events are stored with a timestamp so that after a configurable expiration period they can be re-notified.
- Notifications include inline buttons for feedback (like/dislike) and, if available, a "More Info" URL.
- When a user expresses interest (clicks the like button), an email is sent with full event details and reservation info.
- Feedback is stored in the SQLite database, and event notification sending is rate limited.
"""

import os
import json
import sqlite3
import logging
import hashlib
import asyncio
import time
import smtplib
from email.mime.text import MIMEText
from datetime import timedelta, datetime
from typing import Dict, List
import requests
import logging.handlers

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Configuration using environment variables
telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
if not telegram_token:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set!")

CONFIG = {
    "telegram_token": telegram_token.strip(),  # Remove any whitespace
    "perplexity_api_key": os.getenv("PERPLEXITY_API_KEY"),
    "search_base_url": "https://api.perplexity.ai/chat/completions",  # Adjusted URL for clarity
    "database_file": "events_bot.db",
    "max_results": 5,
    "search_interval_hours": 6,
    "result_fields": ["title", "date", "location", "description", "url"],
    "max_description_length": 300,
    # Expiration period (in days) for sent event notifications
    "notification_expire_days": 7,
    # SMTP configuration for sending emails
    "smtp_server": "smtp.gmail.com",  # Hardcoded for Gmail
    "smtp_port": 465,  # Gmail's SSL port
    "smtp_username": os.getenv("EMAIL_ADDRESS"),  # Match your exemple.py naming
    "smtp_password": os.getenv("BUBBLE_INVEST_EMAIL_PASSWORD"),  # Match your exemple.py naming
    "from_email": os.getenv("EMAIL_ADDRESS"),  # Use the same email address
    # New: list of categories for event search
    "search_categories": ["music", "food", "sports", "arts", "technology",'conference','miscellaneous'],
}

# Add these constants near the top of the file with other configurations
CATEGORY_DESCRIPTIONS = {
    "music": {
        "question": "What kind of music do you enjoy? Tell me about your favorite genres, artists, or the type of concerts you like to attend.",
        "example": "For example: 'I love indie rock and electronic music, especially live performances. I enjoy intimate venue concerts and outdoor festivals. Artists like Arctic Monkeys and Bonobo are my style.'"
    },
    "food": {
        "question": "What are your food preferences and what kind of culinary events interest you?",
        "example": "For example: 'I'm interested in Asian cuisine, particularly Japanese and Thai. I enjoy wine tastings, cooking workshops, and food festivals. I'm also curious about molecular gastronomy.'"
    },
    "sports": {
        "question": "What sports or physical activities interest you? Include both watching and participating.",
        "example": "For example: 'I'm into basketball and yoga. I enjoy watching tennis matches live and would love to join running events or martial arts workshops.'"
    },
    "arts": {
        "question": "What types of arts and cultural events appeal to you?",
        "example": "For example: 'I love contemporary art exhibitions, photography galleries, and interactive installations. I'm also interested in theater performances and dance shows.'"
    },
    "technology": {
        "question": "What aspects of technology interest you most?",
        "example": "For example: 'I'm fascinated by AI and VR demos. I enjoy tech meetups, coding workshops, and startup presentations. I'm particularly interested in sustainable tech.'"
    },
    "conference": {
        "question": "What kinds of conferences or professional events interest you?",
        "example": "For example: 'I'm interested in business innovation, entrepreneurship talks, and industry networking events. I particularly enjoy panels about future trends.'"
    },
    "miscellaneous": {
        "question": "Are there any other types of events that interest you that weren't covered by the previous categories?",
        "example": "For example: 'I enjoy trivia nights, board game meetups, photography walks, or wellness workshops.'"
    }
}

# Modify the logging configuration to include timestamps and maintain logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            "bot.log",
            maxBytes=1024 * 1024,  # 1MB
            backupCount=1
        )
    ]
)


class UserProfile:
    def __init__(self):
        self.address = ""
        self.interests: Dict[str, str] = {}  # Changed to store detailed interests per category
        self.liked_keywords: List[str] = []
        self.disliked_keywords: List[str] = []
        self.email = ""
        self.current_category = None  # Track which category we're currently asking about


class EventBot:
    def __init__(self):
        # Connect to database and initialize tables
        self.db_conn = sqlite3.connect(CONFIG["database_file"], check_same_thread=False)
        self._init_db()
        self.user_profiles: Dict[int, UserProfile] = {}
        self.load_profiles()

    def _init_db(self):
        cursor = self.db_conn.cursor()
        # Table for user profiles and the list of sent events (as JSON dictionary)
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                profile TEXT,
                sent_events TEXT
            )"""
        )
        # Table for feedback (like/dislike) on events
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS events_feedback (
                user_id INTEGER,
                event_hash TEXT,
                feedback INTEGER,  -- 1=like, -1=dislike
                PRIMARY KEY(user_id, event_hash)
            )"""
        )
        self.db_conn.commit()

    def load_profiles(self):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT user_id, profile, sent_events FROM users")
        for user_id, profile_json, sent_events_json in cursor.fetchall():
            profile_data = json.loads(profile_json)
            profile = UserProfile()
            profile.address = profile_data.get("address", "")
            profile.interests = profile_data.get("interests", {})
            profile.liked_keywords = profile_data.get("liked_keywords", [])
            profile.disliked_keywords = profile_data.get("disliked_keywords", [])
            profile.email = profile_data.get("email", "")
            profile.current_category = profile_data.get("current_category")
            self.user_profiles[user_id] = profile

    def save_profile(self, user_id: int):
        profile = self.user_profiles.get(user_id)
        if not profile:
            return
        profile_data = {
            "address": profile.address,
            "interests": profile.interests,
            "liked_keywords": profile.liked_keywords,
            "disliked_keywords": profile.disliked_keywords,
            "email": profile.email,
            "current_category": profile.current_category,
        }
        # Preserve sent_events if available, or initialize as an empty dictionary
        sent_events = self.get_sent_events(user_id) or {}
        cursor = self.db_conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO users (user_id, profile, sent_events) VALUES (?, ?, ?)",
            (user_id, json.dumps(profile_data), json.dumps(sent_events)),
        )
        self.db_conn.commit()

    def get_sent_events(self, user_id: int) -> Dict[str, float]:
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT sent_events FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if result and result[0]:
            try:
                sent = json.loads(result[0])
                # If stored in old format (list), convert to dict with zero timestamps.
                if isinstance(sent, list):
                    return {ev: 0 for ev in sent}
                return sent
            except Exception as e:
                logging.error(f"Error parsing sent_events for user {user_id}: {e}")
                return {}
        return {}

    def add_sent_event(self, user_id: int, event_hash: str):
        sent_events = self.get_sent_events(user_id)
        # Record the current timestamp
        sent_events[event_hash] = time.time()
        cursor = self.db_conn.cursor()
        cursor.execute(
            "UPDATE users SET sent_events = ? WHERE user_id = ?",
            (json.dumps(sent_events), user_id),
        )
        self.db_conn.commit()


# Create a global instance of EventBot
event_bot = EventBot()

# Global dictionary to hold event details for pending email notifications.
pending_event_details: Dict[str, Dict] = {}


def parse_events(raw_data: str) -> List[Dict]:
    """
    Parse the API response into structured events.
    Expected format example:
      ### Events in [Location]
      1. **Event Title**
         - Date: March 25, 2024
         - Location: Venue Name
         - Description: Event details truncated...
         - URL: https://example.com/event
    """
    events = []
    current_event = {}
    for line in raw_data.split("\n"):
        line = line.strip()
        if not line or line.startswith("### Events in"):
            continue
        if line and line[0].isdigit() and ". **" in line:
            if current_event:
                events.append(current_event)
                current_event = {}
            # Extract title between ** markers
            title_start = line.find("**") + 2
            title_end = line.rfind("**")
            current_event["title"] = line[title_start:title_end].strip()
        elif line.startswith("- Date:"):
            current_event["date"] = line.split(":", 1)[1].strip()
        elif line.startswith("- Location:"):
            current_event["location"] = line.split(":", 1)[1].strip()
        elif line.startswith("- Description:"):
            description = line.split(":", 1)[1].strip()
            current_event["description"] = description[: CONFIG["max_description_length"]]
        elif line.startswith("- URL:"):
            current_event["url"] = line.split(":", 1)[1].strip()
    if current_event:
        events.append(current_event)
    return events[: CONFIG["max_results"]]


def generate_event_hash(event: Dict) -> str:
    """Generate a unique MD5 hash for an event based on title, date, and location."""
    hash_string = f"{event.get('title','')}{event.get('date','')}{event.get('location','')}"
    return hashlib.md5(hash_string.encode()).hexdigest()


async def format_event_message(event: Dict) -> str:
    """Format the event message using Markdown."""
    lines = [
        f"🎉 *{event.get('title', 'No Title')}*",
        f"🗓️ {event.get('date', 'Date not specified')}",
        f"📍 {event.get('location', 'Location not specified')}",
    ]
    if event.get("description"):
        lines.append(f"\n{event['description']}")
    return "\n".join(lines)


def search_events_for_category(profile: UserProfile, category: str) -> List[Dict]:
    """Builds a query for a specific category and returns parsed events from the Perplexity API."""
    # Only search if user has interests in this category
    if category not in profile.interests:
        return []
    
    query = (
        f"Events near {profile.address} matching this interest description: "
        f"'{profile.interests[category]}'. Category: {category}. "
    )
    if profile.liked_keywords:
        query += f"Preferred: {', '.join(profile.liked_keywords)}. "
    if profile.disliked_keywords:
        query += f"Avoid: {', '.join(profile.disliked_keywords)}. "
    
    headers = {
        "Authorization": f"Bearer {CONFIG['perplexity_api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "sonar-reasoning",
        "messages": [{"role": "user", "content": query}],
    }
    try:
        response = requests.post(CONFIG["search_base_url"], json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        raw_content = data["choices"][0]["message"]["content"]
        return parse_events(raw_content)
    except Exception as e:
        logging.error(f"Search error for category '{category}': {e}")
        return []


async def search_events(user_id: int) -> List[Dict]:
    """
    Run a separate Perplexity API query for each category defined in CONFIG["search_categories"],
    aggregate and deduplicate the events, then return all events.
    """
    profile = event_bot.user_profiles.get(user_id)
    if not profile or not profile.address or not profile.interests:
        return []
    categories = CONFIG.get("search_categories", [])
    tasks = [asyncio.to_thread(search_events_for_category, profile, cat) for cat in categories]
    results = await asyncio.gather(*tasks)
    aggregated_events = {}
    for events in results:
        for event in events:
            event_hash = generate_event_hash(event)
            aggregated_events[event_hash] = event
    return list(aggregated_events.values())


def send_email(recipient_email: str, subject: str, body: str):
    """Send an email using Gmail's SMTP SSL."""
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = CONFIG["from_email"]
    msg["To"] = recipient_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(CONFIG["smtp_username"], CONFIG["smtp_password"])
            server.send_message(msg)
        logging.info(f"Email sent to {recipient_email} with subject: {subject}")
    except Exception as e:
        logging.error(f"Email sending failed to {recipient_email}: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


async def set_interests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the interests setting conversation."""
    user_id = update.effective_user.id
    if user_id not in event_bot.user_profiles:
        event_bot.user_profiles[user_id] = UserProfile()
    
    profile = event_bot.user_profiles[user_id]
    profile.interests = {}  # Reset interests
    profile.current_category = list(CATEGORY_DESCRIPTIONS.keys())[0]  # Start with first category
    
    await ask_category_interest(update, context, profile.current_category)

async def ask_category_interest(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str):
    """Ask user about their interests for a specific category."""
    category_info = CATEGORY_DESCRIPTIONS[category]
    message = (
        f"📋 *{category.title()} Interests*\n\n"
        f"{category_info['question']}\n\n"
        f"💡 {category_info['example']}\n\n"
        "Please describe your interests in natural language, or type 'skip' if you're not interested in this category."
    )
    await update.message.reply_text(message, parse_mode="Markdown")
    context.user_data["awaiting_category_response"] = True

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user messages including category interest responses."""
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
        
        # Move to next category or finish
        categories = list(CATEGORY_DESCRIPTIONS.keys())
        current_index = categories.index(profile.current_category)
        
        if current_index + 1 < len(categories):
            # Move to next category
            profile.current_category = categories[current_index + 1]
            await ask_category_interest(update, context, profile.current_category)
        else:
            # Finished all categories
            context.user_data.pop("awaiting_category_response", None)
            profile.current_category = None
            event_bot.save_profile(user_id)
            
            # Show summary of interests
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


async def send_event_notifications(context: ContextTypes.DEFAULT_TYPE):
    expire_seconds = CONFIG["notification_expire_days"] * 86400
    current_time = time.time()
    for user_id, _ in event_bot.user_profiles.items():
        try:
            events = await search_events(user_id)
            sent_events = event_bot.get_sent_events(user_id)  # dict: event_hash -> timestamp
            for event in events:
                event_hash = generate_event_hash(event)
                # Check if event was already sent and if it hasn't expired yet.
                if event_hash in sent_events and (current_time - sent_events[event_hash] < expire_seconds):
                    continue
                # Save the event details for potential email sending when liked.
                pending_event_details[event_hash] = event

                message = await format_event_message(event)
                feedback_buttons = [
                    InlineKeyboardButton("👍", callback_data=f"like_{event_hash}"),
                    InlineKeyboardButton("👎", callback_data=f"dislike_{event_hash}"),
                ]
                keyboard = [feedback_buttons]
                if event.get("url"):
                    keyboard.append([InlineKeyboardButton("🌐 More Info", url=event["url"])])
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown",
                )
                event_bot.add_sent_event(user_id, event_hash)
                await asyncio.sleep(1)  # Rate limiting between notifications
        except Exception as e:
            logging.error(f"Error processing events for user {user_id}: {e}")


async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data.split("_")
    if len(data) != 2:
        await query.answer("Invalid feedback data.")
        return
    action, event_hash = data
    try:
        # Store feedback in the database
        cursor = event_bot.db_conn.cursor()
        cursor.execute(
            """
            INSERT INTO events_feedback (user_id, event_hash, feedback)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, event_hash) DO UPDATE SET feedback=excluded.feedback
            """,
            (user_id, event_hash, 1 if action == "like" else -1),
        )
        event_bot.db_conn.commit()

        if action == "like":
            await query.answer("Added to your preferences 👍")
            # If the user expressed interest, send event details via email if they provided an email.
            profile = event_bot.user_profiles.get(user_id)
            if profile and profile.email:
                # Look up event details from the pending_event_details global
                event = pending_event_details.get(event_hash)
                if event:
                    subject = f"Event Details: {event.get('title', 'No Title')}"
                    body_lines = [
                        f"Title: {event.get('title', 'No Title')}",
                        f"Date: {event.get('date', 'Not specified')}",
                        f"Location: {event.get('location', 'Not specified')}",
                    ]
                    if event.get("description"):
                        body_lines.append(f"Description: {event['description']}")
                    if event.get("url"):
                        body_lines.append(f"More Info / Reservation: {event['url']}")
                    body = "\n".join(body_lines)
                    # Send the email in a background thread to prevent blocking.
                    asyncio.create_task(asyncio.to_thread(send_email, profile.email, subject, body))
                    await query.answer("Email sent with event details!")
                else:
                    await query.answer("Event details not found for email sending.")
            else:
                await query.answer("Set your email using /setemail to receive event details via email.")
        else:
            await query.answer("We'll avoid similar events 👎")
    except Exception as e:
        logging.error(f"Feedback error for user {user_id}: {e}")
        await query.answer("Error processing feedback 😞")


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


# Add this function to log bot wake-ups
async def log_wake_up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log when the bot wakes up from sleep."""
    if update.message:
        user_id = update.effective_user.id
        logging.info(f"Bot woken up by user {user_id} at {datetime.now()}")
    return True


def main():
    token = CONFIG["telegram_token"]
    logging.info(f"Initializing bot with token: {token[:8]}...{token[-4:]}")  # Log partial token for verification
    
    try:
        application = Application.builder().token(token).build()
        
        # Add this line to handle wake-ups
        application.add_handler(MessageHandler(filters.ALL, log_wake_up), group=-1)
        
        # Keep your existing handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("setaddress", set_address))
        application.add_handler(CommandHandler("setinterests", set_interests))
        application.add_handler(CommandHandler("setemail", set_email))
        application.add_handler(CommandHandler("example", example_event))
        application.add_handler(CallbackQueryHandler(handle_feedback))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

        # Schedule periodic sending of event notifications
        job_queue = application.job_queue
        job_queue.run_repeating(
            send_event_notifications,
            interval=timedelta(hours=CONFIG["search_interval_hours"]),
            first=10,
        )

        # Add some startup logging
        logging.info("Bot started and ready to handle messages")
        
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True  # Ignore updates received while bot was sleeping
        )
    except Exception as e:
        logging.error(f"Failed to initialize bot: {str(e)}")
        raise


if __name__ == "__main__":
    main()