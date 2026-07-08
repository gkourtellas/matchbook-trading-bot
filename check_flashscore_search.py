#!/usr/bin/env python3
"""One-off check: search FlashScore for a team name and print raw result.

Run:
    python3 check_flashscore_search.py "Real Madrid"

This does NOT place bets or touch Matchbook. It just prints what
FlashScore's search API returns, so we can see the match ID field
needed for the favorite call.
"""

import sys
import json
import requests

if len(sys.argv) < 2:
    print('Usage: python3 check_flashscore_search.py "team name"')
    sys.exit(1)

query = sys.argv[1]

url = "https://s.livesport.services/api/v2/search/"
params = {
    "q": query,
    "lang-id": 1,
    "type-ids": "1,2,3,4",
    "project-id": 2,
    "project-type-id": 1,
}
headers = {
    "accept": "*/*",
    "origin": "https://www.flashscore.com",
    "referer": "https://www.flashscore.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

print(f"Searching FlashScore for: {query}\n")
resp = requests.get(url, params=params, headers=headers, timeout=15)
print("Status:", resp.status_code)
print()

try:
    data = resp.json()
    print(json.dumps(data, indent=2)[:5000])
except Exception as e:
    print("Could not parse JSON:", e)
    print("Raw response:", resp.text[:2000])
