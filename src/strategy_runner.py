"""Runs one strategy's scan -> bet -> wait -> settle -> repeat loop.

Each strategy gets one of these, running on its own, side by side with
every other strategy. They don't affect each other.

League filter: strategies now pick which leagues to bet using
categories (config/league_categories.json), resolved to a flat allow-list
in strategy_loader.py as strategy["_allowed_leagues"]. If that's None,
the strategy bets any league (no filter, old behavior). If it's a set,
only events in one of those leagues are considered.

Odds stability check (2026-07-26): before placing ANY bet, we re-check
the same runner's price 2 more times, 5 seconds apart (3 checks total).
If the odds move more than 5% across those checks, we skip the bet and
log why. This catches bad/stale/thin prices (e.g. a runner briefly
showing 1.01 with no real reason) instead of betting on them blind.

Cash-out timing fix (2026-08-16): cash-out used to be checked inside
the main scan/settle loop, which sleeps up to 30s between passes and
can also get held up by a slow scan_and_bet() call (odds-confirm
sleeps, network calls). That made cash-out react late. Cash-out now
runs in its own loop (cash_out_loop), on its own fast timer, fully
independent of the main loop. A shared lock (_bets_lock) keeps it from
stepping on check_settlements() at the same moment, since both read
and write active_bets plus the same state file.

FlashScore favorite fix (2026-08-24): favorite_on_flashscore and
favorite_min_step were saved in strategies.json but never actually
read anywhere — every bet got favorited regardless. Now respects both:
toggle off = never favorite; toggle on = favorite once current_step is
at or above favorite_min_step (compound strategies always favorite
when the toggle is on, since they don't have "steps").
"""

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import market_match_odds
import market_total
import market_lay_opponent
import market_double_chance
import market_racing_favorite
import overlap_tracker
import flashscore_client
from state_store import load_state, save_state
from log_util import setup_skip_logging

_skip_logger = setup_skip_logging()
from bet_records import record_bet_placed, record_bet_settled, record_bet_cashed_out
from league_tracker import record_league
from strategy_loader import disable_strategy

MATCHERS = {
    "Match Odds": market_match_odds,
    "Moneyline": market_match_odds,
    "Winner": market_match_odds,
    "Both Teams To Score": market_match_odds,
    "Total": market_total,
    "Double Chance": market_match_odds,
    "WIN": market_racing_favorite,
}

ODDS_CHECK_COUNT = 3
ODDS_CHECK_GAP_SECONDS = 5
ODDS_CHECK_MAX_SPREAD_PERCENT = 5
CASH_OUT_POLL_SECONDS = 5


class StrategyRunner:
    def __init__(self, strategy, client):
        self.cfg = strategy
        self.name = strategy["name"]
        self.client = client

        self.strategy_type = strategy.get("strategy_type", "normal")
        self.auto_restart = bool(strategy.get("autoRestart", False))

        if self.strategy_type == "compound":
            self.compound_start = float(strategy["compound_start"])
            self.compound_target = float(strategy["compound_target"])
            self.staking_plan = None
            self.max_steps = 1
        else:
            self.staking_plan = strategy["staking_plan"]
            self.max_steps = len(self.staking_plan)

        is_multi_sport = bool(strategy.get("sport_configs"))

        if is_multi_sport:
            self.market_name = "multi"
            self.bet_mode = strategy.get("bet_mode", "normal")
            self.bet_side = strategy.get("bet_side", "back")
            self.matcher = None  # per-row matcher picked in scan_and_bet via _get_matcher_for_config
        else:
            market_key = strategy.get("market_name") or (strategy.get("market_names") or [None])[0]
            self.market_name = market_key

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

        self.bankroll_stop_loss_percent = strategy.get("bankroll_stop_loss_percent")
        if self.strategy_type == "compound":
            self.balance = saved_balance if saved_balance is not None else self.compound_start
        elif self.bankroll_stop_loss_percent:
            self.starting_bankroll = float(strategy.get("bankroll", 0))
            self.balance = saved_balance if saved_balance is not None else self.starting_bankroll

        self.max_open_bets = strategy.get("max_open_bets", 1)
        self.poll_interval = strategy.get("poll_interval_seconds", 600)
        self.cooldown_after_bet = strategy.get("open_positions_cooldown_seconds", 600)
        self.pause_while_open = strategy.get("pause_scanning_with_open_positions", True)
        self.lookahead_minutes = strategy.get("event_lookahead_minutes", 180)
        self.min_seconds_to_start = strategy.get("min_seconds_to_start", 300)

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

        self.allowed_leagues = strategy.get("_allowed_leagues")
        self.live_mode = strategy.get("live_mode", "pre")
        self.sport_configs = strategy.get("sport_configs")
        self.overlap_group = strategy.get("overlap_group") or None

        # Guards active_bets + the state file from being read/written by
        # check_settlements() and check_cash_out() at the same moment,
        # now that cash-out runs in its own loop alongside the main one.
        self._bets_lock = asyncio.Lock()

    def log(self, msg):
        ts = datetime.now(ZoneInfo("Europe/Athens")).strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] [{self.name}] {msg}"
        if msg.startswith("Skipped"):
            _skip_logger.info(line)  # goes to logs/skipped.log only
        else:
            print(line)  # goes to logs/bot.log (console + main log)

    def _tracks_balance(self):
        return self.strategy_type == "compound" or bool(self.bankroll_stop_loss_percent)

    def _save(self):
        balance = self.balance if self._tracks_balance() else None
        save_state(self.name, self.current_step, self.active_bets, balance)

    def stake_for_step(self):
        if self.strategy_type == "compound":
            return round(self.balance, 2)
        idx = max(0, min(self.current_step - 1, len(self.staking_plan) - 1))
        return float(self.staking_plan[idx])

    def _should_favorite_on_flashscore(self):
        """True only if this strategy's toggle is on AND (for normal
        staking strategies) the current step has reached favorite_min_step.
        Compound strategies have no step ladder, so the toggle alone decides.
        """
        if not self.cfg.get("favorite_on_flashscore", False):
            return False
        if self.strategy_type == "compound":
            return True
        min_step = self.cfg.get("favorite_min_step", 1)
        return self.current_step >= min_step

    def _bet_profit(self, bet, outcome):
        if outcome == "push":
            return 0.0
        stake, odds = bet["stake"], bet["odds"]
        if self.bet_side == "lay":
            return round(stake, 4) if outcome == "won" else -round(stake * (odds - 1), 4)
        return round(stake * (odds - 1), 4) if outcome == "won" else -stake

    @staticmethod
    def _extract_league(event):
        for tag in event.get("meta-tags", []):
            if tag.get("type") == "COMPETITION":
                return tag.get("name")
        return None

    async def _confirm_odds_stable(self, event_id, market_id, runner_id, first_odds, bet_side, event_name, stake,
                                    min_odds=None, max_odds=None):
        """Re-checks the same runner's price ODDS_CHECK_COUNT times total
        (first_odds counts as check #1), ODDS_CHECK_GAP_SECONDS apart.
        Returns (True, final_odds) only if every check stayed within
        ODDS_CHECK_MAX_SPREAD_PERCENT of each other, the top-of-book
        available size can cover the stake, AND the final live price is
        still inside the strategy's min/max odds range (price can drift
        stably but still walk outside the allowed range).
        final_odds is the LAST live price checked — this is what actually
        gets bet, not the first (possibly stale) price we scanned with.
        Returns (False, None) on any failure.
        """
        if not event_id or not market_id or not runner_id:
            self.log(f"Skipped {event_name} — missing event/market/runner id, can't confirm odds")
            return False, None

        checks = [first_odds]
        side = "lay" if bet_side == "lay" else "back"
        last_available = None

        for i in range(ODDS_CHECK_COUNT - 1):
            await asyncio.sleep(ODDS_CHECK_GAP_SECONDS)

            response = await asyncio.to_thread(
                self.client.get_runner_prices, event_id, market_id, runner_id
            )
            if not response:
                self.log(f"Skipped {event_name} — odds re-check {i + 2}/{ODDS_CHECK_COUNT} "
                          f"got no response from Matchbook")
                return False, None

            prices = response.get("prices", []) if isinstance(response, dict) else response
            matching = [p for p in prices if p.get("side") == side]
            if not matching:
                self.log(f"Skipped {event_name} — odds re-check {i + 2}/{ODDS_CHECK_COUNT} "
                          f"found no {side} price for this runner")
                return False, None

            best = min(matching, key=lambda p: p.get("odds", float("inf")))
            odds_now = best.get("odds")
            if odds_now is None:
                self.log(f"Skipped {event_name} — odds re-check {i + 2}/{ODDS_CHECK_COUNT} "
                          f"returned no odds value")
                return False, None

            checks.append(odds_now)
            last_available = best.get("available-amount", best.get("available_amount"))

        lowest, highest = min(checks), max(checks)
        if lowest <= 0:
            self.log(f"Skipped {event_name} — bad odds value in re-check: {checks}")
            return False, None

        spread_percent = (highest - lowest) / lowest * 100
        if spread_percent > ODDS_CHECK_MAX_SPREAD_PERCENT:
            self.log(f"Skipped {event_name} — odds not stable across {ODDS_CHECK_COUNT} checks "
                      f"({ODDS_CHECK_GAP_SECONDS}s apart): {checks} "
                      f"({spread_percent:.1f}% spread, max {ODDS_CHECK_MAX_SPREAD_PERCENT}%)")
            return False, None

        if last_available is not None and last_available < stake:
            self.log(f"Skipped {event_name} — only {last_available} available at the best price, "
                      f"need {stake} for this bet. Market's too thin, would slide to a much worse "
                      f"price to fill.")
            return False, None

        final_odds = checks[-1]
        if min_odds is not None and max_odds is not None and not (min_odds <= final_odds <= max_odds):
            self.log(f"Skipped {event_name} — final price {final_odds} drifted outside "
                      f"allowed range {min_odds}-{max_odds}")
            return False, None

        self.log(f"Odds confirmed stable across {ODDS_CHECK_COUNT} checks "
                  f"({ODDS_CHECK_GAP_SECONDS}s apart): {checks}")
        return True, final_odds

    async def run(self):
        if self.sport_configs:
            self.log(f"Starting. Multi-sport ({len(self.sport_configs)} sport rows).")
        else:
            self.log(f"Starting. Market: {self.market_name}, odds {self.cfg['min_back_odds']}-{self.cfg['max_back_odds']}")
        while True:
            try:
                if len(self.active_bets) < self.max_open_bets:
                    await self.scan_and_bet()

                async with self._bets_lock:
                    await self.check_settlements()

            except Exception as e:
                self.log(f"⚠️ Error in loop: {e}")

            await asyncio.sleep(self.poll_interval if not self.active_bets else 30)

    async def cash_out_loop(self):
        """Own fast timer for cash-out checks, running the whole time
        this strategy is active. Independent of run() above — never
        waits behind a scan or the 30s gate. main.py only starts this
        task for strategies that actually have cash_out_at_percent set.
        """
        while True:
            await asyncio.sleep(CASH_OUT_POLL_SECONDS)

            if not self.active_bets:
                continue

            try:
                async with self._bets_lock:
                    await self.check_cash_out()
            except Exception as e:
                self.log(f"⚠️ Error in cash-out loop: {e}")

    def _event_passes_live_filter(self, event):
        is_live = bool(event.get("in-play") or event.get("live-execution"))
        if self.live_mode == "pre":
            return not is_live
        if self.live_mode == "live":
            return is_live
        return True

    def _get_matcher_for_config(self, cfg):
        bet_mode = cfg.get("bet_mode", "normal")
        bet_side = cfg.get("bet_side", "back")
        market = cfg.get("market_name", "")
        if bet_mode == "double_chance":
            return market_double_chance
        if bet_side == "lay":
            return market_lay_opponent
        return MATCHERS.get(market)

    async def scan_and_bet(self):
        if self.sport_configs:
            # One query per sport row — first sport with a matching, in-range
            # event wins (rows are checked in the order they were added).
            for row_cfg in self.sport_configs:
                if not row_cfg.get("_sport_id"):
                    continue  # sport not offered right now, skip this row
                data = await asyncio.to_thread(
                    self.client.get_live_events, sport_ids=row_cfg["_sport_id"], per_page=30
                )
                if not data or "events" not in data:
                    continue
                placed = await self._scan_events(data["events"], [row_cfg])
                if placed:
                    return  # one bet at a time — stop checking further sports
            return

        data = await asyncio.to_thread(self.client.get_live_events, sport_ids=self.cfg["_sport_id"], per_page=30)
        if not data or "events" not in data:
            self.log("Scanned: no data back from site.")
            return
        await self._scan_events(data["events"], [self.cfg])

    async def _scan_events(self, events, configs):
        now = datetime.utcnow()
        horizon = now + timedelta(minutes=self.lookahead_minutes)
        self.log(f"Scanning {len(events)} upcoming event(s)...")

        for event in events:
            event_name_early = event.get("name", "Unknown Event")

            if not self._event_passes_live_filter(event):
                is_live_flag = bool(event.get("in-play") or event.get("live-execution"))
                self.log(f"Skipped {event_name_early} — live_mode='{self.live_mode}' but event in-play={is_live_flag}")
                continue

            if self.cash_out_at_percent and not event.get("allow-live-betting", False):
                self.log(f"Skipped {event_name_early} — live betting not allowed on this event (needed for cash-out)")
                continue

            if self.allowed_leagues is not None:
                league = self._extract_league(event)
                if not league or league not in self.allowed_leagues:
                    self.log(f"Skipped {event_name_early} — league '{league}' is not in this strategy's allowed leagues")
                    continue

            start_str = event.get("start")
            if not start_str:
                self.log(f"Skipped {event_name_early} — no start time on event")
                continue
            try:
                start_time = datetime.strptime(start_str.replace("Z", ""), "%Y-%m-%dT%H:%M:%S.%f")
            except Exception:
                self.log(f"Skipped {event_name_early} — could not parse start time '{start_str}'")
                continue

            is_live = bool(event.get("in-play") or event.get("live-execution"))
            if not is_live:
                if start_time <= now:
                    self.log(f"Skipped {event_name_early} — already started ({start_time})")
                    continue
                if start_time > horizon:
                    continue
                if (start_time - now).total_seconds() < self.min_seconds_to_start:
                    secs_left = int((start_time - now).total_seconds())
                    self.log(f"Skipped {event_name_early} — starts in {secs_left}s, under min_seconds_to_start ({self.min_seconds_to_start}s)")
                    continue

            event_name = event.get("name", "Unknown Event")
            event_id = event.get("id")

            already_bet = any(b.get("event_id") == event_id for b in self.active_bets)
            if already_bet:
                self.log(f"Skipped {event_name} — already have an active bet on this event")
                continue

            if self.overlap_group and await overlap_tracker.blocked_by_other_group(event_id, self.overlap_group):
                self.log(f"Skipped {event_name} — already has an active bet from a different overlap group")
                continue

            runner_id = runner_name = odds = market_id = None
            matched_cfg = None
            tried_markets = []

            for scfg in configs:
                bet_mode = scfg.get("bet_mode", "normal")
                matcher = self._get_matcher_for_config(scfg)
                if matcher is None:
                    continue

                if bet_mode == "double_chance":
                    tried_markets.append("Match Odds (double_chance trigger)")
                    found = matcher.find_opportunity_in_event(event, scfg)
                    if not found:
                        continue
                    runner_id, runner_name, odds, market_id = found
                    matched_cfg = scfg
                    break
                else:
                    market_found_on_event = False
                    for market in event.get("markets", []):
                        if market.get("name") != scfg.get("market_name"):
                            continue
                        market_found_on_event = True
                        found = matcher.find_opportunity(market, scfg)
                        if not found:
                            continue
                        runner_id, runner_name, odds = found
                        market_id = market.get("id")
                        matched_cfg = scfg
                        break
                    if not market_found_on_event:
                        tried_markets.append(f"{scfg.get('market_name')} (not offered on this event)")
                    else:
                        tried_markets.append(f"{scfg.get('market_name')} (odds/liquidity/field-size didn't match)")
                if matched_cfg:
                    break

            if runner_id is None:
                reason = "; ".join(tried_markets) if tried_markets else "no matcher configured"
                self.log(f"Skipped {event_name} — no bet matched ({reason})")
                continue

            bet_side = matched_cfg.get("bet_side", self.bet_side)
            stake = self.stake_for_step()

            # Claim this event NOW, before the ~10s odds recheck, not after
            # the bet lands. Two different-group strategies could otherwise
            # both pass the block-check, both spend 10s confirming odds, and
            # both place the bet before either one had actually claimed it.
            if self.overlap_group:
                await overlap_tracker.register(event_id, self.overlap_group)

            odds_ok, confirmed_odds = await self._confirm_odds_stable(
                event_id, market_id, runner_id, odds, bet_side, event_name, stake,
                min_odds=matched_cfg.get("min_back_odds"), max_odds=matched_cfg.get("max_back_odds")
            )
            if not odds_ok:
                if self.overlap_group:
                    await overlap_tracker.unregister(event_id, self.overlap_group)
                continue
            odds = confirmed_odds

            action_word = "Lay" if bet_side == "lay" else "Back"
            self.log(f"🎯 Match found: {event_name} -> {action_word} {runner_name} @ {odds}")

            order_status = await asyncio.to_thread(
                self.client.submit_order,
                runner_id=runner_id, side=bet_side, odds=odds, stake=stake
            )

            if not order_status:
                self.log("⚠️ Bet was rejected.")
                if self.overlap_group:
                    await overlap_tracker.unregister(event_id, self.overlap_group)
                continue

            sport = matched_cfg.get("sport_name") or self.cfg.get("sport_name") or (self.cfg.get("sport_names") or ["?"])[0]
            record_league(sport, event)

            if self._should_favorite_on_flashscore() and sport not in ("Horse Racing", "Greyhound Racing", "Horse Racing (Ante Post)"):
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
                "sport_id": matched_cfg.get("_sport_id") or self.cfg.get("_sport_id"),
            }
            league = self._extract_league(event)
            bet["record_id"] = record_bet_placed(
                self.name, event_name, runner_name, odds, stake,
                self.current_step, bet["placed_at"], league=league, offer_id=bet["offer_id"]
            )
            self.active_bets.append(bet)
            self._save()

            start_time_str = (
                start_time.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Europe/Athens")).strftime("%Y-%m-%d %H:%M")
                if start_time else "?"
            )
            msg = (
                f"🚀 Bet Placed [{self.name}]\n"
                f"Step: {self.current_step}/{self.max_steps}\n"
                f"Event: {event_name}\n"
                f"Sport: {sport}\n"
                f"League: {league or '—'}\n"
                f"Start: {start_time_str}\n"
                f"Selection: {runner_name}\n"
                f"Odds: {odds}\n"
                f"Stake: {stake}"
            )
            self.log(msg)
            self.client.send_telegram(msg)
            return True

        self.log("Scan done: nothing matched the strategy right now.")
        return False

    async def check_cash_out(self):
        for bet in self.active_bets:
            if bet.get("cashed_out") or bet.get("settled_via_cashout"):
                continue
            if not all(bet.get(k) for k in ("event_id", "market_id", "runner_id")):
                continue

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
            if lay_odds is None or lay_odds <= 0:
                continue

            stake = bet["stake"]
            back_odds = bet["odds"]

            lay_stake = round((stake * back_odds) / lay_odds, 2)
            equal_profit = round(stake * (back_odds - lay_odds) / lay_odds, 4)

            target_profit = round(stake * (self.cash_out_at_percent / 100), 4)

            if available is not None and available < lay_stake:
                continue

            if equal_profit >= target_profit * 0.95:
                self.log(f"💰 Cashing out '{bet['event_name']}' — locking in ~{equal_profit} "
                         f"equally on both outcomes via lay @ {lay_odds}, lay stake {lay_stake}")

                order_status = await asyncio.to_thread(
                    self.client.submit_order,
                    runner_id=bet["runner_id"], side="lay", odds=lay_odds, stake=lay_stake
                )

                if not order_status:
                    self.log(f"⚠️ Cash-out lay bet was rejected for '{bet['event_name']}'.")
                    continue

                bet["cashed_out"] = True
                bet["cash_out_profit"] = equal_profit
                if bet.get("record_id"):
                    record_bet_cashed_out(bet["record_id"], equal_profit)
                await overlap_tracker.unregister(bet.get("event_id"), self.overlap_group)

                msg = (f"💰 Cashed Out [{self.name}]\nEvent: {bet['event_name']}\n"
                       f"Locked in profit (equal both ways): {equal_profit}")
                self.client.send_telegram(msg)

        self.active_bets = [b for b in self.active_bets if not b.get("cashed_out")]
        self._save()

    @staticmethod
    def _weighted_matched_odds(order_status):
        if not order_status:
            return None
        offers = order_status.get("offers") or []
        if not offers:
            return None
        matched = offers[0].get("matched-bets") or []
        if not matched:
            return None

        total_stake = sum(mb.get("stake", 0) for mb in matched)
        if not total_stake:
            return None

        weighted = sum(mb.get("stake", 0) * mb.get("odds", 0) for mb in matched)
        return round(weighted / total_stake, 4)

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
                    self.log(f"'{bet['event_name']}': not settled yet, next check in {wait_left}s.")
                bet["_last_wait_print"] = wait_left
                still_open.append(bet)
                continue

            after_dt = bet.get("placed_at") or bet.get("start_time")
            outcome, source, real_odds = await asyncio.to_thread(
                self.client.resolve_offer_outcome,
                bet["offer_id"], after_dt=after_dt, event_id=bet.get("event_id"),
                sport_id=bet.get("sport_id") or self.cfg.get("_sport_id")
            )

            if outcome not in ("won", "lost", "push"):
                self.log(f"Waiting on result for '{bet['event_name']}' — not settled yet.")
                still_open.append(bet)
                continue

            await overlap_tracker.unregister(bet.get("event_id"), self.overlap_group)

            result_label = {"won": "Won", "lost": "Lost", "push": "Push (void)"}[outcome]
            result_icon = {"won": "✅", "lost": "❌", "push": "➖"}[outcome]

            if real_odds is not None and real_odds != bet["odds"]:
                self.log(f"'{bet['event_name']}': requested odds {bet['odds']}, "
                         f"actually matched at {real_odds} — using the real price.")
                bet["odds"] = real_odds

            if bet.get("record_id"):
                record_bet_settled(bet["record_id"], outcome, bet["odds"], bet["stake"], bet_side=self.bet_side)

            if self.strategy_type == "compound":
                if outcome == "won":
                    self.balance = round(self.balance * bet["odds"], 2)
                elif outcome == "lost":
                    self.balance = 0.0
                # push: balance unchanged, stake was returned

                settle_msg = (
                    f"{result_icon} Settled [{self.name}]\n"
                    f"Event: {bet['event_name']}\n"
                    f"Result: {result_label}\n"
                    f"Balance: {self.balance} (target {self.compound_target})"
                )
                self.log(settle_msg)
                self.client.send_telegram(settle_msg)

                if self.balance <= 0:
                    if self.auto_restart:
                        self.log(f"💥 Balance hit 0. Auto-restart is on — resetting to {self.compound_start} and continuing.")
                        self.balance = self.compound_start
                    else:
                        self.log("💥 Balance hit 0. Disabling.")
                        await disable_strategy(self.name, "balance hit 0")
                elif self.balance >= self.compound_target:
                    if self.auto_restart:
                        self.log(f"🏁 Target {self.compound_target} reached. Auto-restart is on — "
                                 f"resetting to {self.compound_start} and continuing.")
                        self.balance = self.compound_start
                    else:
                        self.log(f"🏁 Target {self.compound_target} reached. Disabling.")
                        await disable_strategy(self.name, "target reached")

            else:
                if outcome == "won":
                    self.current_step = 1
                elif outcome == "lost":
                    self.current_step = self.current_step + 1 if self.current_step < self.max_steps else 1
                # push: step stays the same, retry this step next time

                settle_msg = (
                    f"{result_icon} Settled [{self.name}]\n"
                    f"Event: {bet['event_name']}\n"
                    f"Result: {result_label}\n"
                    f"Next step: {self.current_step}/{self.max_steps}"
                )

                if self.bankroll_stop_loss_percent:
                    profit = self._bet_profit(bet, outcome)
                    self.balance = round(self.balance + profit, 2)
                    stop_at = round(self.starting_bankroll * (self.bankroll_stop_loss_percent / 100), 2)
                    settle_msg += f"\nBankroll: {self.balance} (stop-loss at {stop_at})"

                    if self.balance <= stop_at:
                        if self.auto_restart:
                            self.log(f"🛑 Bankroll hit {self.balance}, at/below stop-loss ({stop_at}). "
                                     f"Auto-restart is on — resetting to {self.starting_bankroll} and continuing.")
                            self.balance = self.starting_bankroll
                            settle_msg += f"\nAuto-restart: reset to {self.starting_bankroll}"
                            self.log(settle_msg)
                            self.client.send_telegram(settle_msg)
                            continue
                        else:
                            self.log(settle_msg)
                            self.client.send_telegram(settle_msg)
                            self.log(f"🛑 Bankroll hit {self.balance}, at/below stop-loss ({stop_at}). Disabling.")
                            await disable_strategy(self.name, "bankroll stop-loss hit")
                            continue

                self.log(settle_msg)
                self.client.send_telegram(settle_msg)

        self.active_bets = still_open
        self._save()
