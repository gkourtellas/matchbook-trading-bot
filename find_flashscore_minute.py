"""
Tries FlashScore's per-match "detail" feed (not the team fixture list),
which usually carries the live minute. Run during a live match:

    python3 find_flashscore_minute.py "Celtic" "Dundee"
"""

import sys
sys.path.insert(0, "src")

from dotenv import load_dotenv
load_dotenv()

import requests
import flashscore_client as fc

if len(sys.argv) != 3:
    print('Usage: python3 find_flashscore_minute.py "Home Team" "Away Team"')
    sys.exit(1)

home, away = sys.argv[1], sys.argv[2]

if not fc._login():
    print("Login failed.")
    sys.exit(1)

entity_id, country_id, sport_id = fc._search_entity(home)
if not entity_id:
    print(f"'{home}' not found.")
    sys.exit(1)

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
    print("Match not found.")
    sys.exit(0)

match_id = best.get("AA")
print(f"Match id: {match_id}\n")

# Try a few known FlashScore detail feed URL patterns.
candidate_urls = [
    f"https://2.flashscore.ninja/2/x/feed/df_sb_1_{match_id}",
    f"https://2.flashscore.ninja/2/x/feed/dc_1_{match_id}",
    f"https://2.flashscore.ninja/2/x/feed/detail_1_{match_id}",
]

for u in candidate_urls:
    print(f"Trying: {u}")
    try:
        r = requests.get(u, headers=fc.FEED_HEADERS, timeout=15)
        print(f"  status: {r.status_code}")
        if r.status_code == 200 and r.text.strip():
            print(f"  raw text (first 500 chars): {r.text[:500]}")
        print()
    except Exception as e:
        print(f"  error: {e}\n")
