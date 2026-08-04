"""
Finds the FlashScore live score + minute for one match, using the
same login/search already used for favoriting.

Run while a match is actually live:
    python3 find_flashscore_score.py "Celtic" "Dundee"

(pass home team, away team as arguments — use the same names Matchbook
shows for that match)
"""

import sys
sys.path.insert(0, "src")

from dotenv import load_dotenv
load_dotenv()

import flashscore_client as fc

if len(sys.argv) != 3:
    print('Usage: python3 find_flashscore_score.py "Home Team" "Away Team"')
    sys.exit(1)

home, away = sys.argv[1], sys.argv[2]

if not fc._login():
    print("FlashScore login failed — check FLASHSCORE_EMAIL/PASSWORD in .env")
    sys.exit(1)

entity_id, country_id, sport_id = fc._search_entity(home)
if not entity_id:
    print(f"Could not find '{home}' on FlashScore.")
    sys.exit(1)

# Feed type "1" = live/current matches for this team (type "3" = fixtures,
# already used by favorite_event). Trying "1" here to get live score data.
import requests
url = f"https://2.flashscore.ninja/2/x/feed/p_{sport_id}_{country_id}_{entity_id}_1_en_1"
resp = requests.get(url, headers=fc.FEED_HEADERS, timeout=15)
resp.raise_for_status()

matches = fc._parse_feed(resp.text)
away_words = fc._tokenize(away)

best = None
best_score = 0
for m in matches:
    home_words = fc._tokenize(m.get("CX", ""))
    away_words_m = fc._tokenize(m.get("AF", ""))
    score = max(len(away_words & home_words), len(away_words & away_words_m))
    if score > best_score:
        best_score = score
        best = m

if not best:
    print("Match not found in live feed. Raw matches returned:")
    for m in matches[:5]:
        print(" ", m.get("CX"), "vs", m.get("AF"))
    sys.exit(0)

print("Match found. Showing ONLY fields that look like a score or minute")
print("(short plain numbers, 0-99) — should be just a handful of lines:\n")

for k, v in best.items():
    if isinstance(v, str) and v.isdigit() and len(v) <= 2:
        print(f"  {k} = {v}")

print("\nStatus/text fields (may say 'live', 'finished', half-time etc):")
for k, v in best.items():
    if isinstance(v, str) and any(c.isalpha() for c in v) and len(v) <= 20:
        print(f"  {k} = {v}")
