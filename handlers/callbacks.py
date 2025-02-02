from telegram import Update
from telegram.ext import ContextTypes
import logging
import asyncio
from services.email_service import send_email

async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE, event_bot, config, pending_event_details):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data.split("_")
    if len(data) != 2:
        await query.answer("Invalid feedback data.")
        return
    action, event_hash = data
    try:
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
            profile = event_bot.user_profiles.get(user_id)
            if profile and profile.email:
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
                    asyncio.create_task(asyncio.to_thread(send_email, config, profile.email, subject, body))
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