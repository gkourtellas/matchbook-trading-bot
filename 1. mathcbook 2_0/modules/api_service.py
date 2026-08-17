import requests

class MatchbookAPI:
    def __init__(self, session):
        self.session = session
        self.base_url = "https://api.matchbook.com"

    def get_live_events(self, sport_ids):
        url = f"{self.base_url}/edge/rest/events"
        params = {
            "sport-ids": sport_ids,
            "states": "open",
            "exchange-type": "back-lay",
            "odds-type": "DECIMAL",
            "include-prices": "true",
            "price-depth": "1",
            "price-mode": "expanded",
            "per-page": "40"
        }
        response = self.session.get(url, params=params)
        return response.json() if response.status_code == 200 else {}