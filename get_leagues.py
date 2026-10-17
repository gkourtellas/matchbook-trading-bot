import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
USERNAME = os.environ["MATCHBOOK_USERNAME"]
PASSWORD = os.environ["MATCHBOOK_PASSWORD"]

# Add more sports here as needed — id: name (name is used for the output filename).
# Horse/Greyhound Racing added 2026-09-29: they don't have a COMPETITION
# tag like other sports, so _extract_name below falls back to COUNTRY for
# them (this is what gives you Australia/UK/USA/etc as the "league").
TARGET_SPORTS = {
    15: "Soccer",
    4: "Basketball",
    9: "Tennis",
    24735152712200: "Horse Racing",
    241798357140019: "Greyhound Racing",
}

LEAGUES_DIR = "config/leagues"
os.makedirs(LEAGUES_DIR, exist_ok=True)

# --- API Endpoints ---
LOGIN_URL = "https://api.matchbook.com/bpapi/rest/security/session"
EVENTS_URL = "https://api.matchbook.com/edge/rest/events"


def output_path(sport_name):
    safe = "".join(c if c.isalnum() else "_" for c in sport_name.strip())
    return os.path.join(LEAGUES_DIR, f"{safe}.json")


def _extract_name(event):
    """Returns the COMPETITION name if the event has one (soccer,
    basketball, etc). Racing events don't have COMPETITION — for those,
    falls back to COUNTRY (e.g. 'Australia', 'UK', 'South Africa').
    """
    country = None
    for tag in event.get("meta-tags", []):
        if tag.get("type") == "COMPETITION":
            return tag.get("name")
        if tag.get("type") == "COUNTRY":
            country = tag.get("name")
    return country


# 1. Authenticate and get Session Token
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

authenticated_headers = {
    "session-token": session_token,
    "accept": "application/json",
}

# 2. Pull leagues for each sport separately — one output file per sport,
#    so football and basketball (and anything else added later) never mix.
for sport_id, sport_name in TARGET_SPORTS.items():
    path = output_path(sport_name)

    existing_leagues = set()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    existing_leagues = set(data)
        except (json.JSONDecodeError, IOError):
            pass

    new_leagues_found = 0
    offset = 0
    per_page = 100
    while True:
        query_params = {"sport-ids": sport_id, "per-page": per_page, "offset": offset, "states": "open"}
        events_response = requests.get(
            EVENTS_URL, headers=authenticated_headers, params=query_params
        )
        events_response.raise_for_status()
        events_data = events_response.json()

        events = events_data.get("events", [])
        for event in events:
            league_name = _extract_name(event)
            if league_name and league_name not in existing_leagues:
                existing_leagues.add(league_name)
                new_leagues_found += 1

        total = events_data.get("total", 0)
        offset += per_page
        if offset >= total or not events:
            break

    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(existing_leagues), f, indent=4, ensure_ascii=False)

    print(f"[{sport_name}] Added {new_leagues_found} new leagues. Total stored: {len(existing_leagues)}")
