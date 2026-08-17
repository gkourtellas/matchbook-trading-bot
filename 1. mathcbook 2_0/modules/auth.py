import requests
import json
import os

class MatchbookAuth:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.session = requests.Session()
        self.token = None
        self.credentials = self._load_config()

    def _load_config(self):
        with open(self.config_path, "r") as f:
            return json.load(f)

    def login(self):
        url = "https://api.matchbook.com/bpapi/rest/security/session"
        payload = {
            "username": self.credentials.get("MATCHBOOK_USER"),
            "password": self.credentials.get("MATCHBOOK_PASS")
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        response = self.session.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            self.token = response.json().get("session-token")
            self.session.headers.update({"session-token": self.token})
            return True
        return False