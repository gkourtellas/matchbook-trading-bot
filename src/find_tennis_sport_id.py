#!/usr/bin/env python3
"""Finds FlashScore's internal sport ID for tennis.

Run:
    python3 find_tennis_sport_id.py
"""

import requests

HEADERS = {
    "accept": "*/*",
    "origin": "https://www.flashscore.com",
    "referer": "https://www.flashscore.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

resp = requests.get(
    "https://s.livesport.services/api/v2/search/",
    params={"q": "Djokovic", "lang-id": 1, "type-ids": "1,2,3,4", "project-id": 2, "project-type-id": 1},
    headers=HEADERS,
    timeout=15,
)
resp.raise_for_status()
results = resp.json()

for r in results:
    print(r.get("name"), "-> sport:", r.get("sport"))
