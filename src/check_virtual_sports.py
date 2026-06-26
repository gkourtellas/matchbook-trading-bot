"""One-off check: does Matchbook list Virtual Sports for your account?

Run this once:
    python check_virtual_sports.py

It logs in, asks Matchbook for the full sports list, and prints anything
with "virtual" in the name. Doesn't place any bets.
"""

import sys
sys.path.insert(0, "src")

from api_client import MatchbookClient

client = MatchbookClient()
if not client.login():
    print("Login failed. Check your .env file.")
    sys.exit(1)

data = client.get_navigation()
if not data:
    print("Could not get sports list from Matchbook.")
    sys.exit(1)

sports = data if isinstance(data, list) else data.get("sports", [])
print(f"Total sports found: {len(sports)}\n")

if sports:
    print("Example item (raw):", sports[0], "\n")

print("All sports:")
for s in sports:
    print(f"  - {s.get('name')} (id: {s.get('id')})")

print("\nVirtual-looking matches:")
found = False
for s in sports:
    name = (s.get("name") or "").lower()
    if "virtual" in name:
        print(f"  - {s.get('name')} (id: {s.get('id')})")
        found = True

if not found:
    print("  None found.")
