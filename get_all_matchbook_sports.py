#!/usr/bin/env python3
"""
Fetch all sports from Matchbook lookups endpoint.
"""

import requests
import json

url = "https://api.matchbook.com/edge/rest/lookups/sports"
params = {
    "offset": 0,
    "per-page": 100,
    "order": "name asc",
    "status": "active"
}

headers = {
    "User-Agent": "api-doc-test-client",
    "accept": "application/json"
}

print("Fetching all sports from Matchbook...\n")

resp = requests.get(url, params=params, headers=headers, timeout=15)
resp.raise_for_status()

data = resp.json()
sports = data.get("sports", [])
total = data.get("total", 0)

print(f"Found {len(sports)} sports (total available: {total}):\n")
print("=" * 80)

for sport in sports:
    print(f"Name: {sport.get('name'):<30} ID: {sport.get('id')}")

print("=" * 80)

# Save to file
with open("matchbook_sports.json", "w") as f:
    json.dump(sports, f, indent=2)

print(f"\nSaved to matchbook_sports.json")
