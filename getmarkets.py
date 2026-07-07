import os
import requests
from dotenv import load_dotenv

load_dotenv()

def get_soccer_markets():
    username = os.environ.get("MATCHBOOK_USERNAME")
    password = os.environ.get("MATCHBOOK_PASSWORD")
    
    auth_url = "https://api.matchbook.com/bpapi/rest/security/session"
    payload = {
        "username": username,
        "password": password
    }
    
    events_url = "https://api.matchbook.com/edge/rest/events"
    params = {
        "sport-ids": "15",
        "per-page": "50"
    }
    
    auth_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        session_response = requests.post(auth_url, json=payload, headers=auth_headers)
        session_response.raise_for_status()
        session_token = session_response.json().get("session-token")
        
        headers = {
            "session-token": session_token,
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(events_url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # Track unique market names across all games globally
        global_seen_markets = set()
        
        for event in data.get("events", []):
            for market in event.get("markets", []):
                global_seen_markets.add(market.get("name"))
        
        print("Unique Soccer Market Types:")
        for market_name in sorted(global_seen_markets):
            print(f"  - {market_name}")
                
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_soccer_markets()