import json
import requests
import datetime
import os

# CONFIGURATION
API_KEY = "905bafedfcfddfd43ff28649c78c30e8"
BASE_URL = "https://v3.football.api-sports.io"
TELEGRAM_TOKEN = "8696236951:AAFZRIXoZs_BdulN9qtH5-DRTGI5mNDeLis"
TELEGRAM_CHAT_ID = "521374790"
STATE_FILE = "/home/gk/matchbook-trading-bot/config/state.json"
CACHE_FILE = "/home/gk/matchbook-trading-bot/config/cache.json"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, data=payload)

def check_api():
    try:
        with open(STATE_FILE, "r") as f:
            state_data = json.load(f)
        
        step = state_data.get("current_step", "N/A")
        active_bet = state_data.get("active_bet_info", {})
        event_name = active_bet.get("event_name", "")
        target_home = event_name.split(" vs ")[0].split()[0].lower()
        target_away = event_name.split(" vs ")[1].split()[0].lower()
        
        headers = {"x-apisports-key": API_KEY}
        params = {"date": datetime.datetime.now().strftime("%Y-%m-%d")}
        response = requests.get(f"{BASE_URL}/fixtures", headers=headers, params=params).json()
        
        # Load cache
        cache = {}
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r") as f:
                cache = json.load(f)

        for fixture in response.get("response", []):
            home = fixture["teams"]["home"]["name"].lower()
            away = fixture["teams"]["away"]["name"].lower()
            
            if (target_home in home or target_home in away) and (target_away in home or target_away in away):
                status = fixture['fixture']['status']['short']
                minute = fixture['fixture']['status'].get('elapsed')
                h_goals = fixture['goals'].get('home', 0)
                a_goals = fixture['goals'].get('away', 0)
                
                # Check for changes
                cache_key = f"{fixture['fixture']['id']}"
                last = cache.get(cache_key, {})
                
                if (status != last.get('status') or h_goals != last.get('h_goals') or a_goals != last.get('a_goals')):
                    msg = (f"Step: {step}\nMatch: {fixture['teams']['home']['name']} vs {fixture['teams']['away']['name']}\n"
                           f"Status: {status} ({minute}')\nScore: {h_goals} - {a_goals}")
                    send_telegram(msg)
                    
                    # Update cache
                    cache[cache_key] = {'status': status, 'h_goals': h_goals, 'a_goals': a_goals}
                    with open(CACHE_FILE, "w") as f:
                        json.dump(cache, f)
                return
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_api()
