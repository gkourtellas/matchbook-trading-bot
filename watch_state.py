import json
import time

p = "config/state/Multi_All_In.json"

d = json.load(open(p))
d["active_bets"][0]["sport_id"] = 9
json.dump(d, open(p, "w"), indent=2)
print("sport_id set to 9. Watching for 90 seconds...")

for i in range(18):
    time.sleep(5)
    check = json.load(open(p))
    sid = check["active_bets"][0].get("sport_id")
    print(f"[{i*5}s] sport_id = {sid}")
    if sid is None:
        print("!!! IT GOT WIPED HERE !!!")
        break
