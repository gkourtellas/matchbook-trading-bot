import json  
import os  
import requests  
  
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "config.json")  
  
class MatchbookClient:  
    def __init__(self):  
        self.session = requests.Session()  
        self.username = None  
        self.password = None  
        self.token = None  
        self.bot_token = None  
        self.chat_id = None  
        self._load_config()  
  
    def _load_config(self):  
        if os.path.isfile(CONFIG_FILE):  
            try:  
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:  
                    config = json.load(f)  
                    self.username = config.get("MATCHBOOK_USER")  
                    self.password = config.get("MATCHBOOK_PASS")  
                    self.bot_token = config.get("TELEGRAM_BOT_TOKEN")  
                    self.chat_id = config.get("TELEGRAM_CHAT_ID")  
            except Exception as e:  
                print(f"⚠️ Error loading config inside api_client: {e}")  
  
    def login(self):  
        payload = {"username": self.username, "password": self.password}  
        url = "https://api.matchbook.com/bpapi/rest/security/session"  
        headers = {"Content-Type": "application/json", "Accept": "application/json"}  
        try:  
            response = self.session.post(url, json=payload, headers=headers, timeout=15)  
            if response.status_code == 200:  
                data = response.json()  
                self.token = data.get("session-token")  
                self.session.headers.update({"session-token": self.token})  
                return True  
            print(f"⚠️ Login HTTP failure: {response.status_code}")  
            return False  
        except Exception as e:  
            print(f"⚠️ Login connection error: {e}")  
            return False  
  
    def get_live_events(self, sport_ids="15", per_page=30):  
        url = "https://api.matchbook.com/edge/rest/events"  
        params = {  
            "sport-ids": sport_ids,  
            "states": "open",  
            "exchange-type": "back-lay",  
            "per-page": per_page,  
            "include-prices": "true",  
            "price-depth": 1  
        }  
        try:  
            response = self.session.get(url, params=params, timeout=15)  
            if response.status_code == 200:  
                return response.json()  
            return None  
        except Exception:  
            return None  
  
    def submit_order(self, runner_id, side, odds, stake):  
        url = f"https://api.matchbook.com/edge/rest/v2/offers"  
        payload = {  
            "odds-type": "decimal",  
            "exchange-type": "back-lay",  
            "offers": [  
                {  
                    "runner-id": int(runner_id),  
                    "side": side,  
                    "odds": float(odds),  
                    "stake": float(stake)  
                }  
            ]  
        }  
        try:  
            response = self.session.post(url, json=payload, timeout=15)  
            if response.status_code in (200, 201):  
                return response.json()  
            print(f"⚠️ Order placement rejected by API: {response.text}")  
            return None  
        except Exception as e:  
            print(f"⚠️ Order execution network exception: {e}")  
            return None  
  
    def resolve_offer_outcome(self, offer_id, after_dt=None, event_id=None):  
        url = f"https://api.matchbook.com/edge/rest/v2/offers/{offer_id}"  
        try:  
            response = self.session.get(url, timeout=15)  
            if response.status_code == 200:  
                data = response.json()  
                status = data.get("status")  
                if status == "flushed":  
                    return "lost", "api_status"  
                elif status == "settled":  
                    profit_loss = data.get("profit-loss", 0)  
                    if profit_loss > 0:  
                        return "won", "api_settled"  
                    return "lost", "api_settled"  
            return "pending", "api_check"  
        except Exception:  
            return "pending", "network_error"  
  
    def send_telegram(self, message):  
        if not self.bot_token or not self.chat_id:  
            return  
        url = f"https://api.telegram.com/bot{self.bot_token}/sendMessage"  
        payload = {"chat_id": self.chat_id, "text": message}  
        try:  
            requests.post(url, json=payload, timeout=10)  
        except Exception as e:  
            print(f"⚠️ Telegram sending failure: {e}")