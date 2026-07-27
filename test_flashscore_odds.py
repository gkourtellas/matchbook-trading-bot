"""One-off check: does FlashScore's feed (the one we already use for
favoriting) also carry odds data?

Run:
    python3 test_flashscore_odds.py "Djokovic"

Uses the same search + feed endpoints as flashscore_client.py.
Does NOT touch the bot or place bets.
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
    print('Usage: python3 test_flashscore_odds.py "player or team name"')
    sys.exit(1)

query = sys.argv[1]

print(f"Searching FlashScore for: {query}\n")
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
print(f"Using: {picked['name']} (id={picked['id']}, sport={picked['sport']['name']})\n")

sport_id = picked["sport"]["id"]
country_id = picked["defaultCountry"]["id"]
entity_id = picked["id"]

url = f"https://2.flashscore.ninja/2/x/feed/p_{sport_id}_{country_id}_{entity_id}_3_en_1"
print("Feed URL:", url)
resp = requests.get(url, headers=FEED_HEADERS, timeout=15)
print("Feed status:", resp.status_code)

text = resp.text
print("\nFeed length:", len(text))
print("\nFirst 1500 chars of raw feed:")
print(text[:1500])

# Look for any field codes that commonly mean odds on flashscore feeds
# (these are guesses based on common flashscore field letter codes)
for code in ["OD", "OA", "OB", "OC", "OW"]:
    hits = text.count(code + "\u00f7")
    print(f"Field code '{code}' appears {hits} time(s) in feed")
