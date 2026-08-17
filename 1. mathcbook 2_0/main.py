import time
import json
from datetime import datetime
from modules.auth import MatchbookAuth
from modules.strategy import StrategyEngine
from modules.execution import ExecutionManager
from modules.state_manager import StateManager
from modules.notifier import Notifier
from modules.api_service import MatchbookAPI

def run():
    with open("config.json", "r") as f:
        cfg = json.load(f)

    auth = MatchbookAuth("config.json")
    if not auth.login():
        print("Login failed.")
        return
    
    strat_engine = StrategyEngine("strategy_config.json")
    exec_manager = ExecutionManager(auth.session)
    state_mgr = StateManager("state.json")
    notifier = Notifier(cfg["TELEGRAM_BOT_TOKEN"], cfg["TELEGRAM_CHAT_ID"])
    api = MatchbookAPI(auth.session)
    
    print("Engine started.")

    while True:
        try:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting scan cycle...")
            strategies = strat_engine.load_strategies()
            current_states = state_mgr.load()

            for strategy in strategies:
                s_name = strategy["name"]
                print(f"Scanning: {s_name}")
                
                if s_name not in current_states:
                    current_states[s_name] = {"step": 1, "active_bet": None}

                state = current_states[s_name]

                # 1. Handle Active Bet Settlement
                if state.get("active_bet"):
                    print(f"Active bet found for {s_name}. Skipping scan.")
                    continue 

                # 2. Scan and Execute
                events_data = api.get_live_events(strategy.get("sport_id", "15"))
                matches = strat_engine.scan_market(events_data, strategy)
                
                for match in matches:
                    print(f"Trigger met: {match['event']['name']} -> {match['odds']}")
                    order = exec_manager.place_bet(
                        match["runner"]["id"], "back", match["odds"], 0.10
                    )
                    
                    if order:
                        state["active_bet"] = {"order_id": order.get("id")}
                        state_mgr.save(current_states)
                        notifier.send(f"Bet placed on {match['event']['name']}")
                        print(f"Bet placed for {s_name}")
                        break
            
            print("Cycle complete. Sleeping for 60s.")
            time.sleep(60)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run()