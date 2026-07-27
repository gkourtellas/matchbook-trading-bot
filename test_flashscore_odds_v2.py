"""Dumps the FULL flashscore feed for one match, so we can find odds
numbers if they exist anywhere in it.

Run:
    python3 test_flashscore_odds_v2.py "McDonald M."
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

if len(sys.argv) < 2:
    print('Usage: python3 test_flashscore_odds_v2.py "player or team name"')
    sys.exit(1)

query = sys.argv[1]

resp = requests.get(
    "https://s.livesport.services/api/v2/search/",
    params={"q": query, "lang-id": 1, "type-ids": "1,2,3,4", "project-id": 2, "project-type-id": 1},
    headers=HEADERS,
    timeout=15,
)
results = resp.json()
candidates = [r for r in results if r.get("type", {}).get("id") in (2, 3)]
if not candidates:
    print("No team/player found.")
    sys.exit(0)

picked = candidates[0]
sport_id = picked["sport"]["id"]
country_id = picked["defaultCountry"]["id"]
entity_id = picked["id"]

url = f"https://2.flashscore.ninja/2/x/feed/p_{sport_id}_{country_id}_{entity_id}_3_en_1"
resp = requests.get(url, headers=FEED_HEADERS, timeout=15)
text = resp.text

print("FULL FEED:\n")
print(text)

print("\n\n--- Searching for decimal-odds-looking numbers (e.g. 1.85, 2.10) ---")
import re
odds_pattern = re.findall(r'[÷"](\d\.\d{2})[¬"]', text)
print(f"Found {len(odds_pattern)} decimal-odds-shaped values:")
print(odds_pattern[:30])
