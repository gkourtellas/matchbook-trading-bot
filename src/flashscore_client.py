"""Logs into FlashScore and favorites a match by team names.

Used automatically by strategy_runner.py right after a bet is placed.
If anything here fails, it just logs a warning — it never stops or
breaks bet placement.
"""

import os
import re
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


def _search_entity(name):
    """Searches FlashScore for a team OR player, any sport. Picks the
    best word-overlap match among candidates (not just the first hit).
    Returns (entity_id, country_id, sport_id) or (None, None, None).
    """
    resp = requests.get(
        "https://s.livesport.services/api/v2/search/",
        params={"q": name, "lang-id": 1, "type-ids": "1,2,3,4", "project-id": 2, "project-type-id": 1},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json()

    candidates = [r for r in results if r.get("type", {}).get("id") in (2, 3)]  # Team or Player
    if not candidates:
        return None, None, None

    query_words = _tokenize(name)
    best = None
    best_score = -1
    for r in candidates:
        score = len(query_words & _tokenize(r.get("name", "")))
        if score > best_score:
            best_score = score
            best = r

    return best["id"], best["defaultCountry"]["id"], best["sport"]["id"]


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


_STOPWORDS = {
    "fc", "cf", "cd", "sc", "ac", "de", "del", "la", "el", "los", "las",
    "united", "city", "club", "real", "atletico", "athletic", "sporting",
}


def _tokenize(name):
    """Turns a team name into a set of significant words, so 'Dep.
    Santo Domingo' and 'Deportivo Santo Domingo' still share 'santo'
    and 'domingo' even though FlashScore abbreviates names.
    """
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    return {w for w in name.split() if len(w) >= 3 and w not in _STOPWORDS}


def _find_upcoming_match(sport_id, entity_id, country_id, opponent_name):
    url = f"https://2.flashscore.ninja/2/x/feed/p_{sport_id}_{country_id}_{entity_id}_3_en_1"
    resp = requests.get(url, headers=FEED_HEADERS, timeout=15)
    resp.raise_for_status()
    matches = _parse_feed(resp.text)

    opponent_words = _tokenize(opponent_name)
    if not opponent_words:
        return None, None

    best_match = None
    best_score = 0
    for m in matches:
        home_words = _tokenize(m.get("CX", ""))
        away_words = _tokenize(m.get("AF", ""))
        score = max(len(opponent_words & home_words), len(opponent_words & away_words))
        if score > best_score:
            best_score = score
            best_match = m

    if best_match and best_score >= 1:
        return best_match.get("AA"), best_match.get("AD")
    return None, None


def _add_favorite(sport_id, match_id, timestamp):
    resp = requests.post(
        "https://lsid.eu/v3/storemergeddata",
        json={
            "loggedIn": {"id": _session_id, "hash": _session_hash},
            "key": f"mygames.data.g_{sport_id}_{match_id}",
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
    FlashScore by team/player names and add it to favorites. Never
    raises — logs a warning and returns False on any failure.
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

        entity_id, country_id, sport_id = _search_entity(home)
        if not entity_id:
            print(f"⚠️ FlashScore: '{home}' not found — skipping favorite.")
            return False

        match_id, timestamp = _find_upcoming_match(sport_id, entity_id, country_id, away)
        if not match_id:
            print(f"⚠️ FlashScore: match '{event_name}' not found in fixtures — skipping favorite.")
            return False

        _add_favorite(sport_id, match_id, timestamp)
        print(f"⭐ FlashScore: favorited '{event_name}'.")
        return True

    except Exception as e:
        # Session may have expired — force a fresh login next time.
        _session_id = None
        _session_hash = None
        print(f"⚠️ FlashScore favorite failed for '{event_name}': {e}")
        return False
