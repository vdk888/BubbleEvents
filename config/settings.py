import os

# Configuration using environment variables
telegram_token = os.getenv("TELEGRAM_BOT_TOKEN_EVENTS")
if not telegram_token:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set!")

CONFIG = {
    "telegram_token": telegram_token.strip(),
    "perplexity_api_key": os.getenv("PERPLEXITY_API_KEY"),
    "search_base_url": "https://api.perplexity.ai/chat/completions",
    "database_file": "events_bot.db",
    "max_results": 5,
    "search_interval_hours": 6,
    "result_fields": ["title", "date", "location", "description", "url"],
    "max_description_length": 300,
    "notification_expire_days": 7,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 465,
    "smtp_username": os.getenv("EMAIL_ADDRESS"),
    "smtp_password": os.getenv("BUBBLE_INVEST_EMAIL_PASSWORD"),
    "from_email": os.getenv("EMAIL_ADDRESS"),
    "search_categories": ["music", "food", "sports", "arts", "technology", 'conference', 'miscellaneous'],
} 