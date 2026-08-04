import sys, os
sys.path.insert(0, "src")
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime
from api_client import MatchbookClient

client = MatchbookClient()
client.login()

offer_id = 33980210404300060
event_id = 33970776095400023
after_dt = datetime.fromisoformat("2026-08-03T12:09:38.770720")

outcome = client.get_settled_outcome_for_offer(offer_id, after_dt=after_dt, event_id=event_id, sport_id=9)
print("Result with sport_id=9:", outcome)

outcome2 = client.get_settled_outcome_for_offer(offer_id, after_dt=after_dt, event_id=event_id, sport_id=None)
print("Result with sport_id=None (defaults to soccer):", outcome2)
