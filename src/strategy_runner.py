"""Runs one strategy's scan -> bet -> wait -> settle -> repeat loop.

Each strategy gets one of these, running on its own, side by side with
every other strategy. They don't affect each other.
"""

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import market_match_odds
import market_total
import market_lay_opponent
import market_double_chance
import flashscore_client
from state_store import load_state, save_state
from bet_records import record_bet_placed, record_bet_settled, record_bet_cashed_out
from league_tracker import record_league
from strategy_loader import disable_strategy

MATCHERS = {
    "Match Odds": market_match_odds,
    "Moneyline": market_match_odds,
    "Total": market_total,
    "Double Chance": market_match_odds,
}


class StrategyRunner:
    def __init__(self, strategy, client):
        self.cfg = strategy
        self.name = strategy["name"]
        self.client = client

        self.strategy_type = strategy.get("strategy_type", "normal")

        if self.strategy_type == "compound":
            self.compound_start = float(strategy["compound_start"])
            self.compound_target = float(strategy["compound_target"])
            self.staking_plan = None
            self.max_steps = 1
        else:
            self.staking_plan = strategy["staking_plan"]
            self.max_steps = len(self.staking_plan)

        market_key = strategy.get("market_name") or (strategy.get("market_names") or [None])[0]
        self.market_name = market_key

        # bet_mode "double_chance": check Match Odds for the trigger, but
        # place the actual bet on the Double Chance market of the same
        # event. Different from the normal single-market matchers below.
        self.bet_mode = strategy.get("bet_mode", "normal")

        self.bet_side = strategy.get("bet_side", "back")
        if self.bet_mode == "double_chance":
            if market_key != "Match Odds":
                raise ValueError(f"[{self.name}] bet_mode 'double_chance' requires "
                                  f"market_name 'Match Odds' (used as the trigger).")
            if self.bet_side == "lay":
                raise ValueError(f"[{self.name}] bet_mode 'double_chance' only supports "
                                  f"backing the Double Chance selection, not laying.")
            self.matcher = market_double_chance
        elif self.bet_side == "lay":
            if market_key not in ("Match Odds", "Moneyline"):
                raise ValueError(f"[{self.name}] bet_side 'lay' is only supported for "
                                  f"'Match Odds'/'Moneyline' markets right now.")
            self.matcher = market_lay_opponent
        else:
            self.matcher = MATCHERS.get(market_key)
            if self.matcher is None:
                raise ValueError(f"[{self.name}] Don't know how to handle market '{market_key}'.")

        self.current_step, self.active_bets, saved_balance = load_state(self.name)
        if self.strategy_type == "compound":
            self.balance = saved_balance if saved_balance is not None else self.compound_start
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
        elif requested_cash_out and self.bet_side == "lay":
            print(f"[{self.name}] ⚠️ cash_out_at_percent is set but this strategy lays "
                  f"its bets. Cash-out math currently only supports back bets — ignoring it.")
            self.cash_out_at_percent = None
        else:
            self.cash_out_at_percent = requested_cash_out

        self.excluded_leagues = set(strategy.get("excluded_leagues", []))
        self.live_mode = strategy.get("live_mode", "pre")  # pre / live / both
        self.sport_configs = strategy.get("sport_configs")  # None for single-sport

        # NEW: live-odds confirmation window. A live market can show a
        # flash price (e.g. 1.02) for a few seconds that isn't a real
        # reflection of the game — a clearance off the line, a fast
        # break that gets stopped, etc. If set, a live opportunity has
        # to keep matching on the SAME runner for this many seconds
        # before we actually bet on it, instead of betting the instant
        # it's first seen. Ignored for pre-match bets (odds don't flash
        # like that pre-match, no need to slow those down).
        self.live_confirm_seconds = strategy.get("live_confirm_seconds", 0)
        # event_id -> {"runner_id": ..., "first_seen": datetime}
        self._live_candidates = {}

    def log(self, msg):
        ts = datetime.now(ZoneInfo("Europe/Athens")).strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] [{self.name}] {msg}")

    def _save(self):
        balance = self.balance if self.strategy_type == "compound" else None
        save_state(self.name, self.current_step, self.active_bets, balance)

    def stake_for_step(self):
        if self.strategy_type == "compound":
            return round(self.balance, 2)
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

    def _event_passes_live_filter(self, event):
        """Return True if event matches the strategy's live_mode setting."""
        is_live = bool(event.get("in-play") or event.get("live-execution"))
        if self.live_mode == "pre":
            return not is_live
        if self.live_mode == "live":
            return is_live
        return True  # both

    def _get_matcher_for_config(self, cfg):
        """Return the right matcher module for a sport config dict."""
        bet_mode = cfg.get("bet_mode", "normal")
        bet_side = cfg.get("bet_side", "back")
        market = cfg.get("market_name", "")
        if bet_mode == "double_chance":
            return market_double_chance
        if bet_side == "lay":
            return market_lay_opponent
        return MATCHERS.get(market)

    def _confirm_live_candidate(self, event_id, runner_id, event_name, runner_name, odds):
        """Returns True if this live opportunity has been seen on the
        SAME runner for at least live_confirm_seconds and can be bet
        on now. Returns False (and starts/keeps a timer) otherwise.

        If a different runner triggers for the same event, or this is
        the first time we've seen it, the timer (re)starts and we wait.
        """
        now = datetime.utcnow()
        cand = self._live_candidates.get(event_id)

        if cand and cand["runner_id"] == runner_id:
            elapsed = (now - cand["first_seen"]).total_seconds()
            if elapsed < self.live_confirm_seconds:
                self.log(f"👀 '{event_name}' -> {runner_name} @ {odds} still confirming "
                         f"({elapsed:.0f}s/{self.live_confirm_seconds}s)")
                return False
            # Confirmed for long enough — clear it and allow the bet.
            del self._live_candidates[event_id]
            return True

        # First sighting, or the odds moved to a different runner — restart the clock.
        self._live_candidates[event_id] = {"runner_id": runner_id, "first_seen": now}
        self.log(f"👀 New live candidate: '{event_name}' -> {runner_name} @ {odds}. Confirming...")
        return False

    def _prune_live_candidates(self, seen_event_ids, still_matching_event_ids):
        """Drop any tracked candidate whose event disappeared from this
        scan, or whose odds no longer match the strategy (the flash
        move reversed) — so a reversal resets the clock instead of
        leaving a stale timer running.
        """
        for event_id in list(self._live_candidates.keys()):
            if event_id not in seen_event_ids or event_id not in still_matching_event_ids:
                self._live_candidates.pop(event_id, None)

    async def scan_and_bet(self):
        data = await asyncio.to_thread(self.client.get_live_events, sport_ids=self.cfg["_sport_id"], per_page=30)
        if not data or "events" not in data:
            self.log("Scanned: no data back from site.")
            return

        now = datetime.utcnow()
        horizon = now + timedelta(minutes=self.lookahead_minutes)
        self.log(f"Scanning {len(data['events'])} upcoming match(es)...")

        # Build list of sport configs to scan — multi-sport or single
        configs = self.sport_configs if self.sport_configs else [self.cfg]

        seen_event_ids = set()
        still_matching_event_ids = set()

        for event in data["events"]:
            event_id_for_tracking = event.get("id")
            if event_id_for_tracking is not None:
                seen_event_ids.add(event_id_for_tracking)

            if not self._event_passes_live_filter(event):
                continue

            if self.cash_out_at_percent and not event.get("allow-live-betting", False):
                continue

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

            is_live = bool(event.get("in-play") or event.get("live-execution"))
            if not is_live:
                if start_time <= now or start_time > horizon:
                    continue
                if (start_time - now).total_seconds() < self.min_seconds_to_start:
                    continue

            event_name = event.get("name", "Unknown Match")
            event_id = event.get("id")

            already_bet = any(b.get("event_id") == event_id for b in self.active_bets)
            if already_bet:
                continue

            # Try each sport config until one matches
            runner_id = runner_name = odds = market_id = None
            matched_cfg = None

            for scfg in configs:
                bet_mode = scfg.get("bet_mode", "normal")
                matcher = self._get_matcher_for_config(scfg)
                if matcher is None:
                    continue

                if bet_mode == "double_chance":
                    found = matcher.find_opportunity_in_event(event, scfg)
                    if not found:
                        continue
                    runner_id, runner_name, odds, market_id = found
                    matched_cfg = scfg
                    break
                else:
                    for market in event.get("markets", []):
                        if market.get("name") != scfg.get("market_name"):
                            continue
                        found = matcher.find_opportunity(market, scfg)
                        if not found:
                            continue
                        runner_id, runner_name, odds = found
                        market_id = market.get("id")
                        matched_cfg = scfg
                        break
                if matched_cfg:
                    break

            if runner_id is None:
                continue

            # This event currently has a matching opportunity — keep it
            # marked so the candidate isn't pruned as "no longer matching".
            if event_id is not None:
                still_matching_event_ids.add(event_id)

            # Live confirmation window: don't bet on a live opportunity
            # the instant it's seen — require it to hold for a bit first.
            if is_live and self.live_confirm_seconds > 0:
                confirmed = self._confirm_live_candidate(event_id, runner_id, event_name, runner_name, odds)
                if not confirmed:
                    continue

            bet_side = matched_cfg.get("bet_side", self.bet_side)
            stake = self.stake_for_step()

            action_word = "Lay" if bet_side == "lay" else "Back"
            self.log(f"🎯 Match found: {event_name} -> {action_word} {runner_name} @ {odds}")

            order_status = await asyncio.to_thread(
                self.client.submit_order,
                runner_id=runner_id, side=bet_side, odds=odds, stake=stake
            )

            if not order_status:
                self.log("⚠️ Bet was rejected.")
                continue

            sport = self.cfg.get("sport_name") or (self.cfg.get("sport_names") or ["?"])[0]
            record_league(sport, event)

            # Best-effort: add the match to FlashScore favorites so score
            # push notifications reach your phone. Never blocks or breaks
            # bet placement if this fails.
            await asyncio.to_thread(flashscore_client.favorite_event, event_name)

            offers = order_status.get("offers", [])
            placed_offer = offers[0] if offers else {}

            bet = {
                "offer_id": placed_offer.get("id"),
                "event_id": placed_offer.get("event-id"),
                "market_id": market_id,
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
                self.current_step, bet["placed_at"], league=self._extract_league(event)
            )
            self.active_bets.append(bet)
            self._save()

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
            self._prune_live_candidates(seen_event_ids, still_matching_event_ids)
            return  # one new bet per scan pass

        self._prune_live_candidates(seen_event_ids, still_matching_event_ids)
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
        self._save()

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
                record_bet_settled(bet["record_id"], outcome, bet["odds"], bet["stake"], bet_side=self.bet_side)

            if self.strategy_type == "compound":
                if outcome == "won":
                    self.balance = round(self.balance * bet["odds"], 2)
                else:
                    self.balance = 0.0

                settle_msg = (
                    f"Settled [{self.name}]\n"
                    f"Match: {bet['event_name']}\n"
                    f"Result: {result_label}\n"
                    f"Balance: {self.balance} (target {self.compound_target})"
                )
                self.log(settle_msg)
                self.client.send_telegram(settle_msg)

                if self.balance <= 0:
                    self.log("💥 Balance hit 0. Disabling.")
                    await disable_strategy(self.name, "balance hit 0")
                elif self.balance >= self.compound_target:
                    self.log(f"🏁 Target {self.compound_target} reached. Disabling.")
                    await disable_strategy(self.name, "target reached")
            else:
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
        self._save()
