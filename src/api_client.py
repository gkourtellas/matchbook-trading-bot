"""Matchbook REST API client and optional Telegram alerts.

See README.md and docs/API.md for usage and endpoints.
"""

import os
import requests
import json
import time
from datetime import datetime, timedelta

class MatchbookClient:
    def __init__(self):
        self.username = os.getenv("MATCHBOOK_USERNAME")
        self.password = os.getenv("MATCHBOOK_PASSWORD")
        self.tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.tg_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.tg_chat_id_login = os.getenv("TELEGRAM_CHAT_ID_LOGIN", self.tg_chat_id)

        self.auth_url = "https://api.matchbook.com/bpapi/rest/security/session"
        self.base_url = "https://api.matchbook.com/edge/rest"
        self.session_token = None
        self.last_login_time = None
        self.headers = {
            "content-type": "application/json;charset=UTF-8",
            "accept": "application/json"
        }

    def login(self):
        """Authenticates with Matchbook and stores the session token with rate-limit recovery."""
        payload = {
            "username": self.username,
            "password": self.password
        }
        
        attempt = 1
        wait_time = 10  # Start with a 10 second wait on 429 errors

        while True:
            try:
                response = requests.post(self.auth_url, data=json.dumps(payload), headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    self.session_token = data.get("session-token")
                    self.headers["session-token"] = self.session_token
                    self.last_login_time = datetime.utcnow()
                    self.send_telegram("✅ Matchbook login successful. Session token acquired.", login=True)
                    return True
                
                elif response.status_code == 429:
                    print(f"⚠️ Matchbook API login returned 429 (Rate Limited). Attempt {attempt}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    attempt += 1
                    wait_time = min(wait_time * 2, 300)  # Double the wait time, capping at 5 minutes
                    continue
                    
                else:
                    self.send_telegram(f"❌ Login failed. Status: {response.status_code}", login=True)
                    return False
                    
            except Exception as e:
                self.send_telegram(f"❌ Login exception encountered: {str(e)}", login=True)
                return False

    def ensure_valid_session(self):
        """Proactively checks if the current token is older than 4 hours and refreshes if needed."""
        if not self.last_login_time or not self.session_token:
            print("No active session token found. Initializing login...")
            return self.login()
        
        # If token is older than 4 hours, force a proactive background refresh
        if datetime.utcnow() - self.last_login_time > timedelta(hours=4):
            print("🔄 Session token is older than 4 hours. Executing proactive background refresh...")
            return self.login()
        return True

    def get_navigation(self):
        """Retrieves the navigation hierarchy to locate sports and markets."""
        self.ensure_valid_session()
        url = f"{self.base_url}/navigation"
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 401:
                print("⚠️ Received 401 Unauthorized on get_navigation. Attempting reactive session refresh...")
                if self.login():
                    response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error fetching navigation: {str(e)}")
            return None

    def get_runner_prices(self, event_id, market_id, runner_id):
        """Fetches current back/lay prices for one specific runner.
        Used to check if a position can be cashed out at a good price,
        without re-scanning the whole event list.
        """
        self.ensure_valid_session()
        url = f"{self.base_url}/events/{event_id}/markets/{market_id}/runners/{runner_id}/prices"
        params = {"odds-type": "DECIMAL", "exchange-type": "back-lay"}
        try:
            response = requests.get(url, params=params, headers=self.headers)
            if response.status_code == 401:
                if self.login():
                    response = requests.get(url, params=params, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error fetching runner prices: {str(e)}")
            return None

    def get_live_events(self, sport_ids, per_page=20):
        """Fetches active events, runners, and exchange market odds for specified sport IDs."""
        self.ensure_valid_session()
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
            if response.status_code == 401:
                print("⚠️ Received 401 Unauthorized on get_live_events. Attempting reactive session refresh...")
                if self.login():
                    response = requests.get(url, params=params, headers=self.headers)
                    
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error fetching live events: {str(e)}")
            return None

    def submit_order(self, runner_id, side, odds, stake):
        """Submits an exchange order for a specific selection runner ID."""
        self.ensure_valid_session()
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
            if response.status_code == 401:
                print("⚠️ Received 401 Unauthorized on submit_order. Attempting reactive session refresh...")
                if self.login():
                    response = requests.post(url, data=json.dumps(payload), headers=self.headers)

            if response.status_code in [200, 201]:
                return response.json()
            print(f"Order submission rejected. Status: {response.status_code}, Response: {response.text}")
            return None
        except Exception as e:
            print(f"Exception during order submission: {str(e)}")
            return None

    def get_order_status(self, offer_id):
        """Fetch one offer by ID (Matchbook: GET /v2/offers?offer-ids=...)."""
        self.ensure_valid_session()
        url = f"{self.base_url}/v2/offers"
        params = {"offer-ids": str(offer_id), "per-page": 1}
        try:
            response = requests.get(url, params=params, headers=self.headers)
            if response.status_code == 401:
                print("⚠️ Received 401 Unauthorized on get_order_status. Attempting reactive session refresh...")
                if self.login():
                    response = requests.get(url, params=params, headers=self.headers)

            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error checking offer status: {str(e)}")
            return None

    @staticmethod
    def unwrap_offer(data):
        """Normalize GET offer response (single object or offers list)."""
        if not data:
            return None
        offers = data.get("offers")
        if offers:
            return offers[0]
        if data.get("id") is not None:
            return data
        return None

    def outcome_from_offer(self, offer):
        """Return 'won' or 'lost' from one offer object, or None if not settled."""
        if not offer:
            return None

        result = (offer.get("result") or "").upper()
        if result == "WIN":
            return "won"
        if result in ("LOSE", "LOST"):
            return "lost"

        status = (offer.get("status") or "").upper()

        for key in ("settled-items", "settled_items"):
            items = offer.get(key) or []
            if items:
                pl = items[0].get("profit-loss", items[0].get("profit_and_loss", 0))
                return "won" if pl > 0 else "lost"

        if status in ("SETTLED", "FLUSHED"):
            pl = offer.get("profit-loss", offer.get("profit_and_loss"))
            if pl is not None:
                return "won" if pl > 0 else "lost"

        for key in ("matched-bets", "matched_bets"):
            for bet in offer.get(key) or []:
                bet_result = (bet.get("result") or "").upper()
                if bet_result == "WIN":
                    return "won"
                if bet_result in ("LOSE", "LOST"):
                    return "lost"
                if status in ("SETTLED", "FLUSHED"):
                    pl = bet.get("profit-loss", bet.get("profit_and_loss"))
                    if pl is not None:
                        return "won" if pl > 0 else "lost"

        return None

    @staticmethod
    def _outcome_from_settled_bet(bet):
        bet_result = (bet.get("result") or "").upper()
        if bet_result == "WIN":
            return "won"
        if bet_result in ("LOSE", "LOST"):
            return "lost"
        if bet_result in ("PUSH_WIN",):
            return "won"
        if bet_result in ("PUSH", "PUSH_LOSE"):
            return "lost"
        pl = bet.get("profit-loss", bet.get("profit_and_loss"))
        if pl is not None:
            return "won" if pl > 0 else "lost"
        return None

    def get_settled_outcome_for_offer(self, offer_id, after_dt=None, event_id=None, sport_id=None):
        """Look up offer in Matchbook settled-bets report (WIN / LOSE / profit-loss)."""
        self.ensure_valid_session()
        url = f"{self.base_url}/reports/v2/bets/settled"
        target = str(offer_id)
        offset = 0
        per_page = 500

        while True:
            params = {"per-page": per_page, "offset": offset, "sport-ids": sport_id or "15"}
            if after_dt:
                params["after"] = after_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            if event_id:
                params["event-ids"] = str(event_id)

            try:
                response = requests.get(url, params=params, headers=self.headers)
                if response.status_code == 401:
                    print("⚠️ Received 401 Unauthorized on get_settled_outcome_for_offer. Attempting reactive session refresh...")
                    if self.login():
                        response = requests.get(url, params=params, headers=self.headers)

                if response.status_code != 200:
                    return None

                data = response.json()
                for market in data.get("markets", []):
                    for selection in market.get("selections", []):
                        for bet in selection.get("bets", []):
                            if str(bet.get("offer-id", bet.get("offer_id"))) != target:
                                continue
                            return self._outcome_from_settled_bet(bet)

                total = data.get("total", 0)
                offset += per_page
                if offset >= total:
                    return None
            except Exception as e:
                print(f"Error fetching settled bets: {str(e)}")
                return None

    def resolve_offer_outcome(self, offer_id, after_dt=None, event_id=None, sport_id=None):
        """Resolve won/lost from Matchbook only (offers API + settled-bets report)."""
        outcome = self.get_settled_outcome_for_offer(offer_id, after_dt, event_id, sport_id)
        if outcome:
            return outcome, "settled-report"

        raw = self.get_order_status(offer_id)
        offer = self.unwrap_offer(raw)
        outcome = self.outcome_from_offer(offer)
        status_label = (offer.get("status") if offer else None) or (
            "not_found" if raw is None else "unknown"
        )
        if outcome:
            return outcome, status_label

        return None, status_label

    def send_telegram(self, message, login=False):
        """Helper service to push instant alerts to your Telegram chat.

        login=True routes to TELEGRAM_CHAT_ID_LOGIN (falls back to
        TELEGRAM_CHAT_ID if that's not set). Bet notifications keep
        using login=False (default), unchanged.
        """
        if not self.tg_token:
            return
        chat_id = self.tg_chat_id_login if login else self.tg_chat_id
        if not chat_id:
            return
        url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message
        }
        try:
            requests.post(url, json=payload)
        except Exception:
            pass
