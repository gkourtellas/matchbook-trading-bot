import time
import requests
from datetime import datetime, timedelta
from api_client import MatchbookClient

def main():
    print("Starting automated execution strategy loop...")
    client = MatchbookClient()
    
    if not client.login():
        print("Initial authentication failed.")
        return

    target_sport_id = "15"
    loop_interval = 15
    
    current_step = 1
    max_steps = 6

    try:
        while True:
            print(f"\n--- Scanning markets at {time.strftime('%Y-%m-%d %H:%M:%S')} (Step {current_step}/{max_steps}) ---")
            
            url = f"{client.base_url}/events"
            params = {
                "sport-ids": target_sport_id,
                "states": "open",
                "include-prices": "true",
                "price-depth": 1,
                "price-mode": "expanded",
                "odds-type": "DECIMAL",
                "exchange-type": "back-lay",
                "per-page": 30
            }
            
            try:
                response = requests.get(url, params=params, headers=client.headers)
                data = response.json() if response.status_code == 200 else None
            except Exception as e:
                print(f"Error scanning markets: {str(e)}")
                data = None

            active_bet_info = None

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
                                    
                                    if 1.45 <= best_back <= 1.60:
                                        print(f"🎯 Trigger conditions met for: {event_name} -> {runner_name}")
                                        
                                        target_side = "back"
                                        target_odds = best_back
                                        target_stake = 0.10
                                        
                                        order_status = client.submit_order(
                                            runner_id=runner_id,
                                            side=target_side,
                                            odds=target_odds,
                                            stake=target_stake
                                        )
                                        
                                        if order_status:
                                            offers = order_status.get("offers", [])
                                            offer_id = offers[0].get("id") if offers else None
                                            
                                            # Convert UTC start time to Athens time (+3 hours offset)
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
                                                "start_time": start_time,
                                                "selection_name": runner_name
                                            }
                                            break
                                        else:
                                            print(f"⚠️ Execution routing declined by backend exchange rules.")
                    if active_bet_info:
                        break

            if active_bet_info:
                resume_time = active_bet_info["start_time"] + timedelta(minutes=110)
                print(f"⏳ Bet placed. Holding all market checks until 110 minutes after kickoff ({resume_time.strftime('%Y-%m-%d %H:%M:%S')} UTC)...")
                
                while datetime.utcnow() < resume_time:
                    time.sleep(30)
                
                print("⏰ 110 minutes elapsed since kickoff. Transitioning to minute-by-minute status tracking...")
                
                while True:
                    time.sleep(60)
                    print(f"Checking settlement status for offer {active_bet_info['offer_id']}...")
                    
                    status_data = None
                    if active_bet_info["offer_id"]:
                        status_data = client.get_order_status(active_bet_info["offer_id"])
                    
                    settled = False
                    outcome = "Unknown"
                    
                    if status_data:
                        status_str = status_data.get("status", "").upper()
                        if status_str in ["SETTLED", "FLUSHED"]:
                            settled = True
                            settled_items = status_data.get("settled-items", [])
                            if settled_items:
                                profit = settled_items[0].get("profit-loss", 0)
                                outcome = "won" if profit > 0 else "Lost"
                    else:
                        check_url = f"{client.base_url}/events"
                        check_params = {"sport-ids": target_sport_id, "states": "open"}
                        try:
                            chk_resp = requests.get(check_url, params=check_params, headers=client.headers)
                            if chk_resp.status_code == 200:
                                current_events = chk_resp.json().get("events", [])
                                event_still_active = any(e.get("name") in event_name for e in current_events)
                                if not event_still_active:
                                    settled = True
                                    outcome = "Settled"
                        except Exception:
                            pass
                    
                    if settled:
                        settle_msg = f"🔔 Bet {active_bet_info['offer_id'] or 'ID'}, Step {current_step}/{max_steps} {outcome}. Start scanning for next bet."
                        print(settle_msg)
                        client.send_telegram(settle_msg)
                        
                        current_step = current_step + 1 if current_step < max_steps else 1
                        break
            
            time.sleep(loop_interval)
            
    except KeyboardInterrupt:
        print("\nStrategy engine loop safely terminated.")

if __name__ == "__main__":
    main()
