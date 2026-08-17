"""Automated Matchbook strategy loop (scan, bet, settle, step ladder).

See README.md and docs/STRATEGY.md for behavior and configuration.
"""

import json
import os
import time
from datetime import datetime, timedelta
from api_client import MatchbookClient
from log_util import install_print_logger, setup_logging

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "state.json")


def load_settings():
    path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Missing config: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def stake_for_step(settings, step):
    mode = settings.get("mode", "testing")
    ladder = settings.get("stakes", {}).get(mode)
    if not ladder:
        ladder = settings.get("stakes", {}).get("testing", [0.10])
    idx = max(0, min(step - 1, len(ladder) - 1))
    return float(ladder[idx])


def load_state():
    """Loads active bet information and step tracking from disk if present."""
    if not os.path.isfile(STATE_FILE):
        return 1, None
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
            current_step = state.get("current_step", 1)
            active_bet_info = state.get("active_bet_info")
            
            if active_bet_info:
                # Restore datetime instances from stored string formats
                active_bet_info["start_time"] = datetime.fromisoformat(active_bet_info["start_time"])
                active_bet_info["placed_at"] = datetime.fromisoformat(active_bet_info["placed_at"])
                
            return current_step, active_bet_info
    except Exception as e:
        print(f"⚠️ Error loading state file: {str(e)}. Falling back to clean slate.")
        return 1, None


def save_state(current_step, active_bet_info):
    """Saves active bet information and step tracking securely to disk."""
    try:
        state_to_save = {
            "current_step": current_step,
            "active_bet_info": None
        }
        if active_bet_info:
            # Serialize datetime fields into ISO format strings for JSON compatibility
            state_to_save["active_bet_info"] = {
                **active_bet_info,
                "start_time": active_bet_info["start_time"].isoformat(),
                "placed_at": active_bet_info["placed_at"].isoformat()
            }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state_to_save, f, indent=2)
    except Exception as e:
        print(f"⚠️ Error updating state file: {str(e)}")


def main():
    log_path = setup_logging()
    install_print_logger()
    print(f"Log file: {log_path}")
    print("Starting automated execution strategy loop...")
    client = MatchbookClient()

    if not client.login():
        print("Initial authentication failed.")
        return

    settings = load_settings()
    max_steps = int(settings.get("max_steps", 6))
    odds_min = float(settings.get("odds_min", 1.45))
    odds_max = float(settings.get("odds_max", 1.60))
    mode = settings.get("mode", "testing")
    print(
        f"Config loaded: mode={mode}, max_steps={max_steps}, "
        f"odds {odds_min}-{odds_max}, stake step 1={stake_for_step(settings, 1)}"
    )

    target_sport_id = "15"
    loop_interval = 15

    # Recover state on startup sequence
    current_step, active_bet_info = load_state()
    if active_bet_info:
        print(f"🔄 Recovered existing active bet profile for: {active_bet_info['event_name']}")

    try:
        while True:
            # Skip scanning if we recovered an ongoing trackable bet profile
            if not active_bet_info:
                print(f"\n--- Scanning markets at {time.strftime('%Y-%m-%d %H:%M:%S')} (Step {current_step}/{max_steps}) ---")

                data = client.get_live_events(sport_ids=target_sport_id, per_page=30)

                if data and "events" in data:
                    current_utc = datetime.utcnow()

                    for event in data["events"]:
                        if event.get("in-play") is True or event.get("live-execution") is True:
                            continue

                        start_str = event.get("start")
                        if start_str:
                            try:
                                start_time = datetime.strptime(start_str.replace("Z", ""), "%Y-%m-%dT%H:%M:%S.%f")
                                if current_utc >= start_time:
                                    continue
                            except Exception:
                                continue
                        else:
                            continue

                        event_name = event.get("name", "Unknown Match")

                        meta_tags = event.get("meta-tags", [])
                        league_name = "Unknown League"
                        for tag in meta_tags:
                            if tag.get("type") == "COMPETITION":
                                league_name = tag.get("name")
                                break

                        for market in event.get("markets", []):
                            if market.get("name") == "Match Odds":
                                for runner in market.get("runners", []):
                                    runner_id = runner.get("id")
                                    runner_name = runner.get("name")
                                    prices = runner.get("prices", [])

                                    backs = [p for p in prices if p.get("side") == "back"]
                                    if backs:
                                        best_back = backs[0].get("odds")

                                        if odds_min <= best_back <= odds_max:
                                            print(f"🎯 Trigger conditions met for: {event_name} -> {runner_name}")

                                            target_side = "back"
                                            target_odds = best_back
                                            target_stake = stake_for_step(settings, current_step)

                                            order_status = client.submit_order(
                                                runner_id=runner_id,
                                                side=target_side,
                                                odds=target_odds,
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
                                                    f"Step: {current_step}/{max_steps}\n"
                                                    f"League: {league_name}\n"
                                                    f"Match: {event_name}\n"
                                                    f"Selection: {runner_name}\n"
                                                    f"Action: {target_side}\n"
                                                    f"Odds: {target_odds}\n"
                                                    f"Stake: {target_stake}\n"
                                                    f"Start Time: {athens_time_str}"
                                                )
                                                print(msg)
                                                client.send_telegram(msg)

                                                active_bet_info = {
                                                    "offer_id": offer_id,
                                                    "event_id": event_id,
                                                    "start_time": start_time,
                                                    "placed_at": datetime.utcnow(),
                                                    "selection_name": runner_name,
                                                    "event_name": event_name,
                                                }
                                                # Persistent save after placing a new bet
                                                save_state(current_step, active_bet_info)
                                                break
                                            else:
                                                print(f"⚠️ Execution routing declined by backend exchange rules.")
                        if active_bet_info:
                            break

            if active_bet_info:
                resume_time = active_bet_info["start_time"] + timedelta(minutes=110)
                resume_athens = resume_time + timedelta(hours=3)
                
                if datetime.utcnow() < resume_time:
                    print(f"⏳ Active bet track verified. Holding market checks until 110 minutes after kickoff ({resume_athens.strftime('%H:%M')} Athens time)...")

                while datetime.utcnow() < resume_time:
                    time.sleep(30)

                print("⏰ 110 minutes elapsed since kickoff. Transitioning to minute-by-minute status tracking...")

                consecutive_failures = 0

                while True:
                    time.sleep(60)
                    offer_id = active_bet_info.get("offer_id")
                    if not offer_id:
                        print("No offer_id — waiting for Matchbook...")
                        continue

                    after_dt = active_bet_info.get("placed_at") or active_bet_info.get("start_time")
                    outcome, source = client.resolve_offer_outcome(
                        offer_id,
                        after_dt=after_dt,
                        event_id=active_bet_info.get("event_id"),
                    )
                    print(
                        f"Checking settlement for offer {offer_id} "
                        f"({source or 'pending'})..."
                    )

                    if outcome not in ("won", "lost"):
                        if source in ("not_found", "unknown"):
                            consecutive_failures += 1
                            if consecutive_failures >= 5:
                                alert_msg = (
                                    f"🚨 Settlement Loop Error\n"
                                    f"Offer {offer_id} returned status: {source} 5 times consecutively.\n"
                                    f"Breaking loop to prevent lockup. Retaining current step: {current_step}."
                                )
                                print(alert_msg)
                                client.send_telegram(alert_msg)
                                active_bet_info = None
                                save_state(current_step, active_bet_info)
                                break
                        else:
                            consecutive_failures = 0
                        continue

                    result_label = "Won" if outcome == "won" else "Lost"
                    next_step = 1 if outcome == "won" else (
                        current_step + 1 if current_step < max_steps else 1
                    )

                    settle_msg = (
                        f"Settled\n"
                        f"Match: {active_bet_info['event_name']}\n"
                        f"Result: {result_label}\n"
                        f"Next step: {next_step}/{max_steps}"
                    )
                    print(settle_msg)
                    client.send_telegram(settle_msg)

                    current_step = next_step
                    active_bet_info = None
                    # Clear active bet profile and persist updated ladder step level
                    save_state(current_step, active_bet_info)
                    break

            time.sleep(loop_interval)

    except KeyboardInterrupt:
        print("\nStrategy engine loop safely terminated.")

if __name__ == "__main__":
    main()