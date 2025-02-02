import json
import sqlite3
from typing import Dict, List
import logging

class UserProfile:
    def __init__(self):
        self.address = ""
        self.interests: Dict[str, str] = {}
        self.liked_keywords: List[str] = []
        self.disliked_keywords: List[str] = []
        self.email = ""
        self.current_category = None

class EventBot:
    def __init__(self, config):
        self.config = config
        self.db_conn = sqlite3.connect(config["database_file"], check_same_thread=False)
        self._init_db()
        self.user_profiles: Dict[int, UserProfile] = {}
        self.load_profiles()

    def _init_db(self):
        cursor = self.db_conn.cursor()
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                profile TEXT,
                sent_events TEXT
            )"""
        )
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS events_feedback (
                user_id INTEGER,
                event_hash TEXT,
                feedback INTEGER,
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
                if isinstance(sent, list):
                    return {ev: 0 for ev in sent}
                return sent
            except Exception as e:
                logging.error(f"Error parsing sent_events for user {user_id}: {e}")
                return {}
        return {}

    def add_sent_event(self, user_id: int, event_hash: str):
        sent_events = self.get_sent_events(user_id)
        sent_events[event_hash] = time.time()
        cursor = self.db_conn.cursor()
        cursor.execute(
            "UPDATE users SET sent_events = ? WHERE user_id = ?",
            (json.dumps(sent_events), user_id),
        )
        self.db_conn.commit() 