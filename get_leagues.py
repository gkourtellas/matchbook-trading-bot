import json
import os
import requests

# --- Configuration ---
USERNAME = "nintza13"
PASSWORD = "!IB0d0@QEjMEOp!!"
TARGET_SPORT_IDS = [15]  # Configured for Soccer
OUTPUT_FILE = "leagues.json"

# --- API Endpoints ---
LOGIN_URL = "https://api.matchbook.com/bpapi/rest/security/session"
EVENTS_URL = "https://api.matchbook.com/edge/rest/events"

# 1. Load existing leagues to prevent duplicates
existing_leagues = set()
if os.path.exists(OUTPUT_FILE):
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                existing_leagues = set(data)
    except (json.JSONDecodeError, IOError):
        pass

# 2. Authenticate and get Session Token
login_payload = {"username": USERNAME, "password": PASSWORD}
login_headers = {
    "content-type": "application/json;charset=UTF-8",
    "accept": "application/json",
}

response = requests.post(
    LOGIN_URL, data=json.dumps(login_payload), headers=login_headers
)
response.raise_for_status()
session_token = response.json().get("session-token")

# 3. Setup Authenticated Headers
authenticated_headers = {
    "session-token": session_token,
    "accept": "application/json",
}

# 4. Pull Events for the chosen Sports
sport_ids_str = ",".join(map(str, TARGET_SPORT_IDS))
query_params = {"sport-ids": sport_ids_str, "per-page": "100", "states": "open"}

events_response = requests.get(
    EVENTS_URL, headers=authenticated_headers, params=query_params
)
events_response.raise_for_status()
events_data = events_response.json()

# 5. Extract Unique League Names
new_leagues_found = 0
for event in events_data.get("events", []):
    meta_tags = event.get("meta-tags", [])
    for tag in meta_tags:
        if tag.get("type") == "COMPETITION":
            league_name = tag.get("name")
            if league_name and league_name not in existing_leagues:
                existing_leagues.add(league_name)
                new_leagues_found += 1

# 6. Save the updated list back to the file
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(sorted(list(existing_leagues)), f, indent=4, ensure_ascii=False)

print(f"Added {new_leagues_found} new leagues. Total stored: {len(existing_leagues)}")