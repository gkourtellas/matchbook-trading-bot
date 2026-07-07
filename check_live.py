import sys, json
sys.path.insert(0, "src")
from dotenv import load_dotenv
load_dotenv()
from api_client import MatchbookClient

client = MatchbookClient()
if not client.login():
    print("Login failed.")
    sys.exit(1)

data = client.get_live_events(sport_ids="15", per_page=30)
events = data.get("events", []) if data else []
print(f"Total events: {len(events)}\n")

for e in events:
    print(f"name={e.get('name')} in-play={e.get('in-play')} live-execution={e.get('live-execution')} start={e.get('start')}")
