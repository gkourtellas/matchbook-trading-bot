"""Logs into FlashScore and favorites a match by team names.

Used automatically by strategy_runner.py right after a bet is placed.
If anything here fails, it just logs a warning — it never stops or
breaks bet placement.
"""

import os
import requests

EMAIL = os.getenv("FLASHSCORE_EMAIL")
PASSWORD = os.getenv("FLASHSCORE_PASSWORD")

HEADERS = {
    "accept": "*/*",
    "origin": "https://www.flashscore.com",
    "referer": "https://www.flashscore.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# FlashScore's feed API (2.flashscore.ninja) requires this header or it
# returns 401. Seen constant across captured traffic — if favoriting
# starts failing with 401 again, this may need to be re-captured.
FEED_HEADERS = {**HEADERS, "x-fsign": "SW9D1eZo"}

_session_id = None
_session_hash = None


def _login():
    global _session_id, _session_hash
    if not EMAIL or not PASSWORD:
        print("⚠️ FlashScore: FLASHSCORE_EMAIL/PASSWORD not set in .env — skipping favorite.")
        return False
    try:
        resp = requests.post(
            "https://lsid.eu/v3/login",
            json={"email": EMAIL, "password": PASSWORD, "project": 2},
            headers={**HEADERS, "content-type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        _session_id = data["id"]
        _session_hash = data["hash"]
        return True
    except Exception as e:
        print(f"⚠️ FlashScore login failed: {e}")
        return False


def _search_team(name):
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
            return r["id"], r["defaultCountry"]["id"]
    return None, None


def _parse_feed(text):
    matches = []
    current = {}
    for block in text.split("~"):
        block = block.strip("¬")
        if not block:
            continue
        for field in block.split("¬"):
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


def _find_upcoming_match(team_id, country_id, opponent_name):
    url = f"https://2.flashscore.ninja/2/x/feed/p_1_{country_id}_{team_id}_3_en_1"
    resp = requests.get(url, headers=FEED_HEADERS, timeout=15)
    resp.raise_for_status()
    matches = _parse_feed(resp.text)

    opponent_lower = opponent_name.lower()
    for m in matches:
        home = m.get("CX", "")
        away = m.get("AF", "")
        if opponent_lower in home.lower() or opponent_lower in away.lower():
            return m.get("AA"), m.get("AD")
    return None, None


def _add_favorite(match_id, timestamp):
    resp = requests.post(
        "https://lsid.eu/v3/storemergeddata",
        json={
            "loggedIn": {"id": _session_id, "hash": _session_hash},
            "key": f"mygames.data.g_1_{match_id}",
            "dataDiff": {"merge": {"AD": int(timestamp), "MG": "0", "is_duel": 1}, "unmerge": []},
            "project": 2,
        },
        headers={**HEADERS, "content-type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _split_event_name(event_name):
    """Splits a Matchbook event name like 'Flora - Iberia 1999' or
    'Flora v Iberia 1999' into (home, away). Returns (None, None) if
    it can't figure out the split.
    """
    for sep in (" - ", " v ", " vs "):
        if sep in event_name:
            parts = event_name.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    return None, None


def favorite_event(event_name):
    """Call this right after placing a bet. Tries to find the match on
    FlashScore by team names and add it to favorites. Never raises —
    logs a warning and returns False on any failure.
    """
    global _session_id, _session_hash
    try:
        home, away = _split_event_name(event_name)
        if not home or not away:
            print(f"⚠️ FlashScore: could not split event name '{event_name}' into two teams — skipping.")
            return False

        if _session_id is None:
            if not _login():
                return False

        team_id, country_id = _search_team(home)
        if not team_id:
            print(f"⚠️ FlashScore: team '{home}' not found — skipping favorite.")
            return False

        match_id, timestamp = _find_upcoming_match(team_id, country_id, away)
        if not match_id:
            print(f"⚠️ FlashScore: match '{event_name}' not found in fixtures — skipping favorite.")
            return False

        _add_favorite(match_id, timestamp)
        print(f"⭐ FlashScore: favorited '{event_name}'.")
        return True

    except Exception as e:
        # Session may have expired — force a fresh login next time.
        _session_id = None
        _session_hash = None
        print(f"⚠️ FlashScore favorite failed for '{event_name}': {e}")
        return False
