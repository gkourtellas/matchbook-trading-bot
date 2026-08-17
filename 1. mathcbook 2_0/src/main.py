import json  
import os  
import time  
from datetime import datetime, timedelta  
from api_client import MatchbookClient  
from log_util import install_print_logger, setup_logging  
  
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "strategy_config.json")  
STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "state.json")  
  
# Mapping common sport names to Matchbook Sport IDs  
SPORT_ID_MAP = {  
    "football": "15",  
    "soccer": "15",  
    "ice hockey": "4",  
    "baseball": "1"  
}  
  
def stake_for_step(settings, step):  
    ladder = settings.get("staking_plan", [0.10])  
    idx = max(0, min(step - 1, len(ladder) - 1))  
    return float(ladder[idx])  
  
def load_all_states():  
    if not os.path.isfile(STATE_FILE):  
        return {}  
    try:  
        with open(STATE_FILE, "r", encoding="utf-8") as f:  
            states = json.load(f)  
        for s_name, s_data in states.items():  
            active_bet = s_data.get("active_bet_info")  
            if active_bet:  
                active_bet["start_time"] = datetime.fromisoformat(active_bet["start_time"])  
                active_bet["placed_at"] = datetime.fromisoformat(active_bet["placed_at"])  
        return states  
    except Exception as e:  
        print(f"⚠️ Error loading state file: {str(e)}. Starting fresh.")  
        return {}  
  
def save_all_states(states):  
    try:  
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)  
        serialized = {}  
        for s_name, s_data in states.items():  
            serialized[s_name] = {  
                "current_step": s_data.get("current_step", 1),  
                "active_bet_info": None  
            }  
            active_bet = s_data.get("active_bet_info")  
            if active_bet:  
                serialized[s_name]["active_bet_info"] = {  
                    **active_bet,  
                    "start_time": active_bet["start_time"].isoformat(),  
                    "placed_at": active_bet["placed_at"].isoformat()  
                }  
        with open(STATE_FILE, "w", encoding="utf-8") as f:  
            json.dump(serialized, f, indent=2)  
    except Exception as e:  
        print(f"⚠️ Error updating state file: {str(e)}")  
  
def load_strategies():  
    if not os.path.isfile(CONFIG_FILE):  
        print(f"⚠️ Configuration file not found at {CONFIG_FILE}")  
        return []  
    try:  
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:  
            data = json.load(f)  
            return [s for s in data.get("strategies", []) if s.get("enabled", True)]  
    except Exception as e:  
        print(f"⚠️ Error loading configuration file: {str(e)}")  
        return []  
  
def run_engine():  
    log_path = setup_logging()  
    install_print_logger()  
    print(f"Log file: {log_path}")  
    print("Starting scalable multi-strategy v2.0 engine...")  
      
    client = MatchbookClient()  
    if not client.login():  
        print("Initial authentication failed.")  
        return  
  
    strategy_states = load_all_states()  
  
    try:  
        while True:  
            strategies = load_strategies()  
            if not strategies:  
                print("No active strategies found. Retrying in 15 seconds...")  
                time.sleep(15)  
                continue  
  
            for settings in strategies:  
                s_name = settings.get("name")  
                  
                # Initialize state tracking if missing for this specific strategy  
                if s_name not in strategy_states:  
                    strategy_states[s_name] = {"current_step": 1, "active_bet_info": None}  
  
                current_step = strategy_states[s_name]["current_step"]  
                active_bet_info = strategy_states[s_name]["active_bet_info"]  
  
                # Handle settlement tracking loop if an active position exists  
                if active_bet_info:  
                    resume_time = active_bet_info["start_time"] + timedelta(minutes=110)  
                    if datetime.utcnow() < resume_time:  
                        continue  # Keep skipping market checks until event concludes  
  
                    offer_id = active_bet_info.get("offer_id")  
                    after_dt = active_bet_info.get("placed_at") or active_bet_info.get("start_time")  
                    outcome, source = client.resolve_offer_outcome(  
                        offer_id,  
                        after_dt=after_dt,  
                        event_id=active_bet_info.get("event_id"),  
                    )  
                    print(f"[{s_name}] Checking settlement for offer {offer_id} ({source or 'pending'})...")  
  
                    if outcome == "won":  
                        msg = f"✅ Strategy: {s_name}\nBet Won! Resetting to Step 1."  
                        print(msg)  
                        client.send_telegram(msg)  
                        strategy_states[s_name]["current_step"] = 1  
                        strategy_states[s_name]["active_bet_info"] = None  
                        save_all_states(strategy_states)  
                    elif outcome == "lost":  
                        max_steps = settings.get("staking_steps", 6)  
                        next_step = current_step + 1  
                        if next_step > max_steps:  
                            msg = f"🚨 CIRCUIT BREAKER TRIPPED\nStrategy: {s_name} exceeded max steps ({max_steps}). Halting execution."  
                            print(msg)  
                            client.send_telegram(msg)  
                            settings["enabled"] = False  # Deactivate strategy flag  
                        else:  
                            msg = f"❌ Strategy: {s_name}\nBet Lost. Advancing to Step {next_step}."  
                            print(msg)  
                            client.send_telegram(msg)  
                            strategy_states[s_name]["current_step"] = next_step  
                        strategy_states[s_name]["active_bet_info"] = None  
                        save_all_states(strategy_states)  
                    continue  
  
                # Scan Markets if no active positions are locked  
                sport_name = settings.get("sport_name", "Football").lower()  
                target_sport_id = SPORT_ID_MAP.get(sport_name, "15")  
                market_name_filter = settings.get("market_name", "Match Odds")  
  
                print(f"\n--- Scanning [{s_name}] at {time.strftime('%Y-%m-%d %H:%M:%S')} (Step {current_step}) ---")  
                data = client.get_live_events(sport_ids=target_sport_id, per_page=40)  
  
                if data and "events" in data:  
                    current_utc = datetime.utcnow()  
  
                    for event in data["events"]:  
                        if event.get("in-play") is True or event.get("live-execution") is True:  
                            continue  
  
                        start_str = event.get("start")  
                        if not start_str:  
                            continue  
                        try:  
                            start_time = datetime.strptime(start_str.replace("Z", ""), "%Y-%m-%dT%H:%M:%S.%f")  
                            if current_utc >= start_time:  
                                continue  
                        except Exception:  
                            continue  
  
                        event_name = event.get("name", "Unknown Match")  
                        meta_tags = event.get("meta-tags", [])  
                        league_name = "Unknown League"  
                        for tag in meta_tags:  
                            if tag.get("type") == "COMPETITION":  
                                league_name = tag.get("name")  
                                break  
  
                        for market in event.get("markets", []):  
                            if market.get("name") == market_name_filter:  
                                # Optional validation for Over/Under total ranges  
                                if settings.get("total_range"):  
                                    if str(settings.get("total_range")) not in market.get("name", ""):  
                                        continue  
  
                                for runner in market.get("runners", []):  
                                    runner_id = runner.get("id")  
                                    runner_name = runner.get("name")  
                                      
                                    if settings.get("total_direction"):  
                                        if settings.get("total_direction").lower() != runner_name.lower():  
                                            continue  
  
                                    prices = runner.get("prices", [])  
                                    backs = [p for p in prices if p.get("side") == "back"]  
                                    if backs:  
                                        best_back = backs[0].get("odds")  
  
                                        if float(settings.get("min_back_odds", 1.45)) <= best_back <= float(settings.get("max_back_odds", 1.60)):  
                                            print(f"🎯 Trigger met: {event_name} -> {runner_name} at {best_back}")  
  
                                            target_stake = stake_for_step(settings, current_step)  
                                            order_status = client.submit_order(  
                                                runner_id=runner_id,  
                                                side="back",  
                                                odds=best_back,  
                                                stake=target_stake  
                                            )  
  
                                            if order_status:  
                                                offers = order_status.get("offers", [])  
                                                placed_offer = offers[0] if offers else {}  
                                                offer_id = placed_offer.get("id")  
                                                event_id = placed_offer.get("event-id")  
  
                                                athens_time = start_time + timedelta(hours=3)  
                                                athens_time_str = athens_time.strftime("%H:%M")  
  
                                                msg = (  
                                                    f"🚀 Bet Placed!\n"  
                                                    f"Strategy: {s_name}\n"  
                                                    f"Step: {current_step}\n"  
                                                    f"League: {league_name}\n"  
                                                    f"Match: {event_name}\n"  
                                                    f"Selection: {runner_name}\n"  
                                                    f"Odds: {best_back}\n"  
                                                    f"Stake: {target_stake}\n"  
                                                    f"Start Time: {athens_time_str} Athens"  
                                                )  
                                                print(msg)  
                                                client.send_telegram(msg)  
  
                                                strategy_states[s_name]["active_bet_info"] = {  
                                                    "offer_id": offer_id,  
                                                    "event_id": event_id,  
                                                    "start_time": start_time,  
                                                    "placed_at": datetime.utcnow(),  
                                                    "selection_name": runner_name,  
                                                    "event_name": event_name,  
                                                }  
                                                save_all_states(strategy_states)  
                                                break  
                        if strategy_states[s_name]["active_bet_info"]:  
                            break  
  
            time.sleep(15)  
  
    except KeyboardInterrupt:  
        print("\nStopping engine execution loop clean.")  
  
if __name__ == "__main__":  
    run_engine()