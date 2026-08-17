import requests

class Notifier:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, message):
        url = f"https://api.telegram.com/bot{self.bot_token}/sendMessage"
        requests.post(url, json={"chat_id": self.chat_id, "text": message})