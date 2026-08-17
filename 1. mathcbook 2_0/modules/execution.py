class ExecutionManager:
    def __init__(self, auth_session):
        self.session = auth_session

    def place_bet(self, runner_id, side, odds, stake):
        url = "https://api.matchbook.com/edge/rest/v2/offers"
        payload = {
            "odds-type": "decimal",
            "exchange-type": "back-lay",
            "offers": [{
                "runner-id": int(runner_id),
                "side": side,
                "odds": float(odds),
                "stake": float(stake)
            }]
        }
        response = self.session.post(url, json=payload)
        return response.json() if response.status_code in [200, 201] else None