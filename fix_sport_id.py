import json

p = "config/state/Multi_All_In.json"

with open(p) as f:
    d = json.load(f)

print("BEFORE:", d["active_bets"][0].get("sport_id"))

d["active_bets"][0]["sport_id"] = 9

with open(p, "w") as f:
    json.dump(d, f, indent=2)

with open(p) as f:
    check = json.load(f)

print("AFTER (re-read from disk):", check["active_bets"][0].get("sport_id"))
