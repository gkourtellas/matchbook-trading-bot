import json

class StrategyEngine:
    def __init__(self, config_path="strategy_config.json"):
        self.config_path = config_path

    def load_strategies(self):
        with open(self.config_path, "r") as f:
            data = json.load(f)
            return [s for s in data.get("strategies", []) if s.get("enabled", True)]

    def scan_market(self, events_data, strategy):
        matches = []
        for event in events_data.get("events", []):
            # Debug: Log the status to identify why it's not filtering correctly
            print(f"Debug: Checking {event.get('name')} | In-Running: {event.get('in-running')} | Status: {event.get('status')}")
            
            if event.get("in-running") is True:
                continue
                
            for market in event.get("markets", []):
                if market.get("name") == strategy.get("market_name"):
                    for runner in market.get("runners", []):
                        prices = runner.get("prices", [])
                        backs = [p for p in prices if p.get("side") == "back"]
                        if backs:
                            odds = backs[0].get("odds")
                            if strategy["min_back_odds"] <= odds <= strategy["max_back_odds"]:
                                matches.append({"event": event, "runner": runner, "odds": odds})
        return matches