#!/usr/bin/env python3
"""Debug tool: shows everything FlashScore returns for a team search,
and every match in that team's fixture feed — so we can see exactly
why a match wasn't found (wrong team picked, name mismatch, etc).

Run:
    python3 debug_flashscore_match.py "Deportivo Santo Domingo"
"""

import sys
import requests

HEADERS = {
    "accept": "*/*",
    "origin": "https://www.flashscore.com",
    "referer": "https://www.flashscore.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
FEED_HEADERS = {**HEADERS, "x-fsign": "SW9D1eZo"}


def search_team_all(name):
    resp = requests.get(
        "https://s.livesport.services/api/v2/search/",
        params={"q": name, "lang-id": 1, "type-ids": "1,2,3,4", "project-id": 2, "project-type-id": 1},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def parse_feed(text):
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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python3 debug_flashscore_match.py "team or player name"')
        sys.exit(1)

    query = sys.argv[1]
    print(f"Searching for: {query}\n")
    results = search_team_all(query)

    candidates = [r for r in results if r.get("type", {}).get("id") in (2, 3)]  # Team or Player

    if not candidates:
        print("No team/player found at all in search results.")
        sys.exit(0)

    print(f"Found {len(candidates)} candidate(s):\n")
    for t in candidates:
        print(f"  - {t['name']}  (id={t['id']}, type={t['type']['name']}, "
              f"sport={t['sport']['name']}(id={t['sport']['id']}), country={t['defaultCountry']['name']}(id={t['defaultCountry']['id']}))")

    import re as _re
    stop = {"fc", "cf", "cd", "sc", "ac", "de", "del", "la", "el", "los", "las",
            "united", "city", "club", "real", "atletico", "athletic", "sporting"}

    def tokenize(n):
        n = n.lower()
        n = _re.sub(r"[^a-z0-9\s]", " ", n)
        return {w for w in n.split() if len(w) >= 3 and w not in stop}

    query_words = tokenize(query)
    picked = max(candidates, key=lambda r: len(query_words & tokenize(r["name"])))
    print(f"\nBest word-overlap match: {picked['name']} (id={picked['id']}, sport_id={picked['sport']['id']})")
    print(f"Fetching fixture feed for this entity...\n")

    sport_id = picked["sport"]["id"]
    country_id = picked["defaultCountry"]["id"]
    entity_id = picked["id"]
    url = f"https://2.flashscore.ninja/2/x/feed/p_{sport_id}_{country_id}_{entity_id}_3_en_1"
    print("URL:", url)
    resp = requests.get(url, headers=FEED_HEADERS, timeout=15)
    print("Feed status:", resp.status_code)

    if resp.status_code != 200:
        print("Feed body:", resp.text[:500])
        sys.exit(0)

    matches = parse_feed(resp.text)
    print(f"Feed has {len(matches)} match(es) listed:\n")
    for m in matches:
        home = m.get("CX", "?")
        away = m.get("AF", "?")
        print(f"  - {home}  vs  {away}   (match_id={m.get('AA')}, timestamp={m.get('AD')})")
