"""Runs one strategy's scan -> bet -> wait -> settle -> repeat loop.

Each strategy gets one of these, running on its own, side by side with
every other strategy. They don't affect each other.
"""

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import market_match_odds
import market_total
from state_store import load_state, save_state
from bet_records import record_bet_placed, record_bet_settled, record_bet_cashed_out
from league_tracker import record_league

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

        # If set, automatically locks in this % of the stake as guaranteed
        # profit (win or lose) as soon as live odds make it possible.
        # e.g. cash_out_at_percent: 5 on a 10 EUR stake locks in 0.50 EUR.
        # Only applies to single-step strategies — multi-step (martingale
        # ladder) strategies don't support cash-out yet.
        requested_cash_out = strategy.get("cash_out_at_percent")
        if requested_cash_out and self.max_steps > 1:
            print(f"[{self.name}] ⚠️ cash_out_at_percent is set but this strategy has "
                  f"{self.max_steps} steps. Cash-out is only supported for single-step "
                  f"strategies right now — ignoring it.")
            self.cash_out_at_percent = None
        else:
            self.cash_out_at_percent = requested_cash_out

        self.excluded_leagues = set(strategy.get("excluded_leagues", []))

    def log(self, msg):
        ts = datetime.now(ZoneInfo("Europe/Athens")).strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] [{self.name}] {msg}")

    def stake_for_step(self):
        idx = max(0, min(self.current_step - 1, len(self.staking_plan) - 1))
        return float(self.staking_plan[idx])

    @staticmethod
    def _extract_league(event):
        """Same logic as get_leagues.py — pulls the COMPETITION name
        from the event's meta-tags, if present."""
        for tag in event.get("meta-tags", []):
            if tag.get("type") == "COMPETITION":
                return tag.get("name")
        return None

    async def run(self):
        self.log(f"Starting. Market: {self.market_name}, odds {self.cfg['min_back_odds']}-{self.cfg['max_back_odds']}")
        while True:
            try:
                if len(self.active_bets) < self.max_open_bets:
                    await self.scan_and_bet()

                if self.cash_out_at_percent:
                    await self.check_cash_out()

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

            if self.cash_out_at_percent and not event.get("allow-live-betting", False):
                continue  # can't cash out later if live betting isn't offered on this event

            if self.excluded_leagues:
                league = self._extract_league(event)
                if league and league in self.excluded_leagues:
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

                sport = self.cfg.get("sport_name") or (self.cfg.get("sport_names") or ["?"])[0]
                record_league(sport, event)

                offers = order_status.get("offers", [])
                placed_offer = offers[0] if offers else {}

                bet = {
                    "offer_id": placed_offer.get("id"),
                    "event_id": placed_offer.get("event-id"),
                    "market_id": market.get("id"),
                    "runner_id": runner_id,
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

    async def check_cash_out(self):
        """For each open bet, checks if current lay odds let us lock in
        the target % of stake as guaranteed profit. If so, places the
        lay bet and marks this bet as closed (cashed out).
        """
        for bet in self.active_bets:
            if bet.get("cashed_out") or bet.get("settled_via_cashout"):
                continue
            if not all(bet.get(k) for k in ("event_id", "market_id", "runner_id")):
                continue  # older bet placed before these fields existed

            response = await asyncio.to_thread(
                self.client.get_runner_prices, bet["event_id"], bet["market_id"], bet["runner_id"]
            )
            if not response:
                continue
            prices = response.get("prices", []) if isinstance(response, dict) else response
            if not prices:
                continue

            lays = [p for p in prices if p.get("side") == "lay"]
            if not lays:
                continue

            best_lay = min(lays, key=lambda p: p.get("odds", float("inf")))
            lay_odds = best_lay.get("odds")
            available = best_lay.get("available-amount", best_lay.get("available_amount"))
            if lay_odds is None:
                continue

            stake = bet["stake"]
            target_profit = round(stake * (self.cash_out_at_percent / 100), 4)
            lay_stake = round(target_profit + stake, 2)

            if available is not None and available < lay_stake:
                continue  # not enough liquidity to fully hedge yet

            win_case_profit = round(stake * (bet["odds"] - 1) - lay_stake * (lay_odds - 1), 4)
            lose_case_profit = round(lay_stake - stake, 4)

            if win_case_profit >= target_profit - 0.01 and lose_case_profit >= target_profit - 0.01:
                self.log(f"💰 Cashing out '{bet['event_name']}' — locking in ~{lose_case_profit} "
                         f"({self.cash_out_at_percent}% of stake) via lay @ {lay_odds}")

                order_status = await asyncio.to_thread(
                    self.client.submit_order,
                    runner_id=bet["runner_id"], side="lay", odds=lay_odds, stake=lay_stake
                )

                if not order_status:
                    self.log(f"⚠️ Cash-out lay bet was rejected for '{bet['event_name']}'.")
                    continue

                bet["cashed_out"] = True
                bet["cash_out_profit"] = lose_case_profit
                if bet.get("record_id"):
                    record_bet_cashed_out(bet["record_id"], lose_case_profit)

                msg = (f"💰 Cashed Out [{self.name}]\nMatch: {bet['event_name']}\n"
                       f"Locked in profit: {lose_case_profit}")
                self.client.send_telegram(msg)

        self.active_bets = [b for b in self.active_bets if not b.get("cashed_out")]
        save_state(self.name, self.current_step, self.active_bets)

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
