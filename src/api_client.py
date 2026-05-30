import os
import requests
import json

class MatchbookClient:
    def __init__(self):
        self.username = os.getenv("MATCHBOOK_USERNAME")
        self.password = os.getenv("MATCHBOOK_PASSWORD")
        self.tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.tg_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        self.auth_url = "https://api.matchbook.com/bpapi/rest/security/session"
        self.base_url = "https://api.matchbook.com/edge/rest"
        self.session_token = None
        self.headers = {
            "content-type": "application/json;charset=UTF-8",
            "accept": "application/json"
        }

    def login(self):
        """Authenticates with Matchbook and stores the session token."""
        payload = {
            "username": self.username,
            "password": self.password
        }
        try:
            response = requests.post(self.auth_url, data=json.dumps(payload), headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                self.session_token = data.get("session-token")
                self.headers["session-token"] = self.session_token
                self.send_telegram("✅ Matchbook login successful. Session token acquired.")
                return True
            else:
                self.send_telegram(f"❌ Login failed. Status: {response.status_code}")
                return False
        except Exception as e:
            self.send_telegram(f"❌ Login exception encountered: {str(e)}")
            return False

    def get_navigation(self):
        """Retrieves the navigation hierarchy to locate sports and markets."""
        url = f"{self.base_url}/navigation"
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                if self.login():
                    return self.get_navigation()
            return None
        except Exception as e:
            print(f"Error fetching navigation: {str(e)}")
            return None

    def get_live_events(self, sport_ids, per_page=20):
        """Fetches active events, runners, and exchange market odds for specified sport IDs."""
        url = f"{self.base_url}/events"
        params = {
            "sport-ids": sport_ids,
            "states": "open",
            "include-prices": "true",
            "price-depth": 3,
            "price-mode": "expanded",
            "odds-type": "DECIMAL",
            "exchange-type": "back-lay",
            "per-page": per_page
        }
        try:
            response = requests.get(url, params=params, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                if self.login():
                    return self.get_live_events(sport_ids, per_page)
            return None
        except Exception as e:
            print(f"Error fetching live events: {str(e)}")
            return None

    def submit_order(self, runner_id, side, odds, stake):
        """Submits an exchange order for a specific selection runner ID."""
        url = f"{self.base_url}/v2/offers"
        payload = {
            "odds-type": "DECIMAL",
            "exchange-type": "back-lay",
            "offers": [
                {
                    "runner-id": runner_id,
                    "side": side,
                    "odds": odds,
                    "stake": stake
                }
            ]
        }
        try:
            response = requests.post(url, data=json.dumps(payload), headers=self.headers)
            if response.status_code in [200, 201]:
                return response.json()
            elif response.status_code == 401:
                if self.login():
                    return self.submit_order(runner_id, side, odds, stake)
            print(f"Order submission rejected. Status: {response.status_code}, Response: {response.text}")
            return None
        except Exception as e:
            print(f"Exception during order submission: {str(e)}")
            return None

    def get_order_status(self, offer_id):
        """Queries the status of a specific submitted offer ID to find its settlement state."""
        url = f"{self.base_url}/v2/offers/{offer_id}"
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                if self.login():
                    return self.get_order_status(offer_id)
            return None
        except Exception as e:
            print(f"Error checking offer status: {str(e)}")
            return None

    def send_telegram(self, message):
        """Helper service to push instant alerts to your Telegram chat."""
        if not self.tg_token or not self.tg_chat_id:
            return
        url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
        payload = {
            "chat_id": self.tg_chat_id,
            "text": message
        }
        try:
            requests.post(url, json=payload)
        except Exception:
            pass
