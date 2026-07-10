"""Tests the live-odds confirmation window logic in isolation —
no Matchbook API calls, no bot, no real bets. Just proves the timer
and reset behavior work the way you expect.

Run:
    python3 test_live_confirm.py
"""

import sys
from datetime import datetime, timedelta

sys.path.insert(0, "src")


class FakeRunner:
    """Minimal stand-in for StrategyRunner, just the confirm logic."""

    def __init__(self, live_confirm_seconds):
        self.live_confirm_seconds = live_confirm_seconds
        self._live_candidates = {}
        self.name = "TEST"

    def log(self, msg):
        print(f"    {msg}")

    # Copied 1:1 from strategy_runner.py so this tests the real logic
    def _confirm_live_candidate(self, event_id, runner_id, event_name, runner_name, odds, now):
        cand = self._live_candidates.get(event_id)

        if cand and cand["runner_id"] == runner_id:
            elapsed = (now - cand["first_seen"]).total_seconds()
            if elapsed < self.live_confirm_seconds:
                self.log(f"still confirming ({elapsed:.0f}s/{self.live_confirm_seconds}s)")
                return False
            del self._live_candidates[event_id]
            return True

        self._live_candidates[event_id] = {"runner_id": runner_id, "first_seen": now}
        self.log("new candidate, timer started")
        return False


def run_case(title, live_confirm_seconds, polls):
    """polls = list of (seconds_since_start, event_id, runner_id, odds or None)
    odds=None means 'no longer matching' at that poll.
    """
    print(f"\n=== {title} (confirm window: {live_confirm_seconds}s) ===")
    runner = FakeRunner(live_confirm_seconds)
    t0 = datetime.utcnow()
    bet_placed_at = None

    for offset, event_id, runner_id, odds in polls:
        now = t0 + timedelta(seconds=offset)
        print(f"[t+{offset:>3}s] poll -> runner={runner_id} odds={odds}")

        if odds is None:
            # Simulates odds moving out of range this poll — real code
            # would just not find a match and prune the candidate.
            runner._live_candidates.pop(event_id, None)
            continue

        # Matches strategy_runner.py: confirm step is skipped entirely
        # when live_confirm_seconds is 0 (old, instant-bet behavior).
        if runner.live_confirm_seconds <= 0:
            confirmed = True
        else:
            confirmed = runner._confirm_live_candidate(event_id, runner_id, "Test Match", "Home", odds, now)
        if confirmed:
            bet_placed_at = offset
            print(f"    ✅ BET PLACED at t+{offset}s")

    print(f"Result: {'bet placed at t+' + str(bet_placed_at) + 's' if bet_placed_at is not None else 'no bet placed'}")
    return bet_placed_at


if __name__ == "__main__":
    # Case 1: flash spike that reverses before confirm window elapses -> should NOT bet
    run_case(
        "Flash spike, reverses fast",
        live_confirm_seconds=20,
        polls=[
            (0, "evt1", "runnerA", 1.50),
            (10, "evt1", "runnerA", 1.51),   # still in range, 10s in
            (15, "evt1", None, None),        # odds moved out of range -> reset
            (35, "evt1", "runnerA", 1.52),   # new candidate, timer restarts
        ],
    )

    # Case 2: genuine sustained move -> SHOULD bet once 20s elapse
    run_case(
        "Real move, stays in range",
        live_confirm_seconds=20,
        polls=[
            (0, "evt2", "runnerB", 1.48),
            (10, "evt2", "runnerB", 1.49),
            (20, "evt2", "runnerB", 1.50),   # 20s elapsed -> should confirm here
        ],
    )

    # Case 3: confirm window disabled (0) -> bets instantly like before
    run_case(
        "Confirm window off (0s)",
        live_confirm_seconds=0,
        polls=[
            (0, "evt3", "runnerC", 1.50),
        ],
    )
