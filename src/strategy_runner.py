"""Runs one strategy's scan -> bet -> wait -> settle -> repeat loop.

Each strategy gets one of these, running on its own, side by side with
every other strategy. They don't affect each other.
"""

import asyncio
from datetime import datetime, timedelta

import market_match_odds
import market_total
from state_store import load_state, save_state
from bet_records import record_bet_placed, record_bet_settled

MATCHERS = {
    "Match Odds": market_match_odds,
    "Moneyline": market_match_odds,
    "Total": market_total,
}


class StrategyRunner:
    def __init__(self, strategy, client):
        self.cfg = strategy
        self.name = strategy["name"]
        self.client = client

        self.staking_plan = strategy["staking_plan"]
        self.max_steps = len(self.staking_plan)

        market_key = strategy.get("market_name") or (strategy.get("market_names") or [None])[0]
        self.market_name = market_key
        self.matcher = MATCHERS.get(market_key)
        if self.matcher is None:
            raise ValueError(f"[{self.name}] Don't know how to handle market '{market_key}'.")

        self.current_step, self.active_bets = load_state(self.name)
        self.max_open_bets = strategy.get("max_open_bets", 1)
        self.poll_interval = strategy.get("poll_interval_seconds", 600)
        self.cooldown_after_bet = strategy.get("open_positions_cooldown_seconds", 600)
        self.pause_while_open = strategy.get("pause_scanning_with_open_positions", True)
        self.lookahead_minutes = strategy.get("event_lookahead_minutes", 180)
        self.min_seconds_to_start = strategy.get("min_seconds_to_start", 300)

    def log(self, msg):
        print(f"[{self.name}] {msg}")

    def stake_for_step(self):
        idx = max(0, min(self.current_step - 1, len(self.staking_plan) - 1))
        return float(self.staking_plan[idx])

    async def run(self):
        self.log(f"Starting. Market: {self.market_name}, odds {self.cfg['min_back_odds']}-{self.cfg['max_back_odds']}")
        while True:
            try:
                if len(self.active_bets) < self.max_open_bets:
                    await self.scan_and_bet()

                await self.check_settlements()

            except Exception as e:
                self.log(f"⚠️ Error in loop: {e}")

            await asyncio.sleep(self.poll_interval if not self.active_bets else 30)

    async def scan_and_bet(self):
        data = await asyncio.to_thread(self.client.get_live_events, sport_ids=self.cfg["_sport_id"], per_page=30)
        if not data or "events" not in data:
            self.log("Scanned: no data back from site.")
            return

        now = datetime.utcnow()
        horizon = now + timedelta(minutes=self.lookahead_minutes)
        self.log(f"Scanning {len(data['events'])} upcoming match(es)...")

        for event in data["events"]:
            if event.get("in-play") or event.get("live-execution"):
                if not self.cfg.get("keep_in_play", False):
                    continue

            start_str = event.get("start")
            if not start_str:
                continue
            try:
                start_time = datetime.strptime(start_str.replace("Z", ""), "%Y-%m-%dT%H:%M:%S.%f")
            except Exception:
                continue

            if start_time <= now or start_time > horizon:
                continue
            if (start_time - now).total_seconds() < self.min_seconds_to_start:
                continue

            event_name = event.get("name", "Unknown Match")
            event_id = event.get("id")

            already_bet = any(b.get("event_id") == event_id for b in self.active_bets)
            if already_bet:
                continue

            for market in event.get("markets", []):
                if market.get("name") != self.market_name:
                    continue

                found = self.matcher.find_opportunity(market, self.cfg)
                if not found:
                    continue

                runner_id, runner_name, odds = found
                stake = self.stake_for_step()

                self.log(f"🎯 Match found: {event_name} -> {runner_name} @ {odds}")

                order_status = await asyncio.to_thread(
                    self.client.submit_order,
                    runner_id=runner_id, side="back", odds=odds, stake=stake
                )

                if not order_status:
                    self.log("⚠️ Bet was rejected.")
                    continue

                offers = order_status.get("offers", [])
                placed_offer = offers[0] if offers else {}

                bet = {
                    "offer_id": placed_offer.get("id"),
                    "event_id": placed_offer.get("event-id"),
                    "start_time": start_time,
                    "placed_at": datetime.utcnow(),
                    "selection_name": runner_name,
                    "event_name": event_name,
                    "stake": stake,
                    "odds": odds,
                    "step": self.current_step,
                }
                bet["record_id"] = record_bet_placed(
                    self.name, event_name, runner_name, odds, stake,
                    self.current_step, bet["placed_at"]
                )
                self.active_bets.append(bet)
                save_state(self.name, self.current_step, self.active_bets)

                msg = (
                    f"🚀 Bet Placed [{self.name}]\n"
                    f"Step: {self.current_step}/{self.max_steps}\n"
                    f"Match: {event_name}\n"
                    f"Selection: {runner_name}\n"
                    f"Odds: {odds}\n"
                    f"Stake: {stake}"
                )
                self.log(msg)
                self.client.send_telegram(msg)
                return  # one new bet per scan pass

        self.log("Scan done: nothing matched the strategy right now.")

    async def check_settlements(self):
        if not self.active_bets:
            return

        still_open = []
        for bet in self.active_bets:
            resume_time = bet["start_time"] + timedelta(seconds=self.cooldown_after_bet)
            now = datetime.utcnow()

            if now < resume_time:
                wait_left = int((resume_time - now).total_seconds())
                last_print = bet.get("_last_wait_print", 0)
                if wait_left % 60 == 0 or last_print == 0:
                    self.log(f"'{bet['event_name']}': match hasn't started/settled yet, next check in {wait_left}s.")
                bet["_last_wait_print"] = wait_left
                still_open.append(bet)
                continue

            after_dt = bet.get("placed_at") or bet.get("start_time")
            outcome, source = await asyncio.to_thread(
                self.client.resolve_offer_outcome,
                bet["offer_id"], after_dt=after_dt, event_id=bet.get("event_id"),
                sport_id=self.cfg["_sport_id"]
            )

            if outcome not in ("won", "lost"):
                self.log(f"Waiting on result for '{bet['event_name']}' — not settled yet.")
                still_open.append(bet)
                continue

            result_label = "Won" if outcome == "won" else "Lost"
            if bet.get("record_id"):
                record_bet_settled(bet["record_id"], outcome, bet["odds"], bet["stake"])

            self.current_step = 1 if outcome == "won" else (
                self.current_step + 1 if self.current_step < self.max_steps else 1
            )

            settle_msg = (
                f"Settled [{self.name}]\n"
                f"Match: {bet['event_name']}\n"
                f"Result: {result_label}\n"
                f"Next step: {self.current_step}/{self.max_steps}"
            )
            self.log(settle_msg)
            self.client.send_telegram(settle_msg)

        self.active_bets = still_open
        save_state(self.name, self.current_step, self.active_bets)
