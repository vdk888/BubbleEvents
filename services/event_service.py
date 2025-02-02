import hashlib
import requests
import logging
import asyncio
from typing import Dict, List

def generate_event_hash(event: Dict) -> str:
    hash_string = f"{event.get('title','')}{event.get('date','')}{event.get('location','')}"
    return hashlib.md5(hash_string.encode()).hexdigest()

async def format_event_message(event: Dict) -> str:
    lines = [
        f"🎉 *{event.get('title', 'No Title')}*",
        f"🗓️ {event.get('date', 'Date not specified')}",
        f"📍 {event.get('location', 'Location not specified')}",
    ]
    if event.get("description"):
        lines.append(f"\n{event['description']}")
    return "\n".join(lines)

def search_events_for_category(config, profile, category: str) -> List[Dict]:
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
        "Authorization": f"Bearer {config['perplexity_api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "sonar-reasoning",
        "messages": [{"role": "user", "content": query}],
    }
    try:
        response = requests.post(config["search_base_url"], json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        raw_content = data["choices"][0]["message"]["content"]
        return parse_events(raw_content)
    except Exception as e:
        logging.error(f"Search error for category '{category}': {e}")
        return []

def parse_events(raw_data: str) -> List[Dict]:
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
            title_start = line.find("**") + 2
            title_end = line.rfind("**")
            current_event["title"] = line[title_start:title_end].strip()
        elif line.startswith("- Date:"):
            current_event["date"] = line.split(":", 1)[1].strip()
        elif line.startswith("- Location:"):
            current_event["location"] = line.split(":", 1)[1].strip()
        elif line.startswith("- Description:"):
            description = line.split(":", 1)[1].strip()
            current_event["description"] = description[:300]
        elif line.startswith("- URL:"):
            current_event["url"] = line.split(":", 1)[1].strip()
    if current_event:
        events.append(current_event)
    return events[:5] 