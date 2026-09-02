"""Main entry point. Starts every enabled strategy from strategies.json,
all running at the same time, independently.

To add, remove, or change a strategy: edit config/strategies.json only.
No code changes needed.

Strategies with cash_out_at_percent set also get a second task
(cash_out_loop) running alongside their main loop, so cash-out checks
happen on their own fast timer instead of waiting behind the normal
scan/settle loop.
"""

import asyncio

from api_client import MatchbookClient
from log_util import install_print_logger, setup_logging
from strategy_loader import load_strategies
from strategy_runner import StrategyRunner
import overlap_tracker

# Bump this string every time main.py or strategy_runner.py changes.
# Printed to logs and sent to Telegram on startup, so you can confirm
# what's actually running without checking github or SSHing in.
BOT_VERSION = "v4"


async def main():
    log_path = setup_logging()
    install_print_logger()
    print(f"Log file: {log_path}")
    print(f"Bot version: {BOT_VERSION}")

    client = MatchbookClient()
    if not client.login():
        print("Initial login failed. Stopping.")
        return

    client.send_telegram(f"🤖 Bot starting — version {BOT_VERSION}", login=True)

    strategies = load_strategies(client)
    if not strategies:
        print("No enabled strategies found in strategies.json. Nothing to do.")
        return

    print(f"Loaded {len(strategies)} strategy(ies): {', '.join(s['name'] for s in strategies)}")

    runners = [StrategyRunner(s, client) for s in strategies]

    # Bets that were already open before this restart need to be back in
    # the overlap tracker too, or a different-group strategy could bet
    # the same match right after startup, before either bet settles.
    for r in runners:
        for bet in r.active_bets:
            market_type = bet.get("market_type") or r.market_name
            await overlap_tracker.register(bet.get("event_id"), r.overlap_group, market_type)

    tasks = []
    for r in runners:
        tasks.append(r.run())
        if r.cash_out_at_percent:
            tasks.append(r.cash_out_loop())

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
