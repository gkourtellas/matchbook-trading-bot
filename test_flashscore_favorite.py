#!/usr/bin/env python3
"""Test the full FlashScore favorite flow: login -> find match -> favorite it.

Run:
    python3 test_flashscore_favorite.py "Flora" "Iberia 1999"

First argument = home team name (as it appears on FlashScore), second = away team.
Reads FLASHSCORE_EMAIL / FLASHSCORE_PASSWORD from .env in current folder.

This only touches FlashScore, not Matchbook or the bot's database.
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

EMAIL = os.getenv("FLASHSCORE_EMAIL")
PASSWORD = os.getenv("FLASHSCORE_PASSWORD")

HEADERS = {
    "accept": "*/*",
    "origin": "https://www.flashscore.com",
    "referer": "https://www.flashscore.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# FlashScore's feed API (2.flashscore.ninja) requires this header or it
# returns 401. Value seen constant across requests in captured traffic —
# if it starts failing again, it may need to be re-captured from a fresh HAR.
FEED_HEADERS = {**HEADERS, "x-fsign": "SW9D1eZo"}


def login():
    resp = requests.post(
        "https://lsid.eu/v3/login",
        json={"email": EMAIL, "password": PASSWORD, "project": 2},
        headers={**HEADERS, "content-type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["id"], data["hash"]


def search_team(name):
    resp = requests.get(
        "https://s.livesport.services/api/v2/search/",
        params={"q": name, "lang-id": 1, "type-ids": "1,2,3,4", "project-id": 2, "project-type-id": 1},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json()
    for r in results:
        if r.get("sport", {}).get("id") == 1 and r.get("type", {}).get("id") == 2:
            return r["id"], r["defaultCountry"]["id"], r["name"]
    return None, None, None


def parse_feed(text):
    """Splits FlashScore's pipe-delimited feed into a list of match dicts."""
    matches = []
    current = {}
    for block in text.split("~"):
        block = block.strip("¬")
        if not block:
            continue
        fields = block.split("¬")
        for field in fields:
            if "÷" not in field:
                continue
            key, _, value = field.partition("÷")
            if key == "AA":
                if current.get("AA"):
                    matches.append(current)
                current = {}
            current[key] = value
    if current.get("AA"):
        matches.append(current)
    return matches


def find_upcoming_match(team_id, country_id, opponent_name):
    url = f"https://2.flashscore.ninja/2/x/feed/p_1_{country_id}_{team_id}_3_en_1"
    resp = requests.get(url, headers=FEED_HEADERS, timeout=15)
    resp.raise_for_status()
    matches = parse_feed(resp.text)

    opponent_lower = opponent_name.lower()
    for m in matches:
        home = m.get("CX", "")
        away = m.get("AF", "")
        if opponent_lower in home.lower() or opponent_lower in away.lower():
            return m.get("AA"), m.get("AD")
    return None, None


def add_favorite(user_id, user_hash, match_id, timestamp):
    resp = requests.post(
        "https://lsid.eu/v3/storemergeddata",
        json={
            "loggedIn": {"id": user_id, "hash": user_hash},
            "key": f"mygames.data.g_1_{match_id}",
            "dataDiff": {"merge": {"AD": int(timestamp), "MG": "0", "is_duel": 1}, "unmerge": []},
            "project": 2,
        },
        headers={**HEADERS, "content-type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Usage: python3 test_flashscore_favorite.py "Home Team" "Away Team"')
        sys.exit(1)

    if not EMAIL or not PASSWORD:
        print("Missing FLASHSCORE_EMAIL / FLASHSCORE_PASSWORD in .env")
        sys.exit(1)

    home_team = sys.argv[1]
    away_team = sys.argv[2]

    print("Logging in to FlashScore...")
    user_id, user_hash = login()
    print(f"  OK — id={user_id}")

    print(f"Searching for team: {home_team}...")
    team_id, country_id, matched_name = search_team(home_team)
    if not team_id:
        print("  Team not found.")
        sys.exit(1)
    print(f"  Found: {matched_name} (team_id={team_id}, country_id={country_id})")

    print(f"Looking for upcoming match vs {away_team}...")
    match_id, timestamp = find_upcoming_match(team_id, country_id, away_team)
    if not match_id:
        print("  Match not found in this team's fixture list.")
        sys.exit(1)
    print(f"  Found match_id={match_id}, kickoff timestamp={timestamp}")

    print("Adding to favorites...")
    result = add_favorite(user_id, user_hash, match_id, timestamp)
    print("  Result:", result)
    print("\nDone. Check your FlashScore favorites / phone app now.")
