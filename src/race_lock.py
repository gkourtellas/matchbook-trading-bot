"""Race-wide lock: only ONE bet per race, across ALL racing
strategies, no matter which strategy sees the favorite first.
Only used for the WIN market (horse/greyhound racing)."""

import asyncio

_lock = asyncio.Lock()
_locked_races = set()


async def try_lock_race(event_id):
    """True = race was free, now locked, safe to bet.
    False = another strategy already has this race."""
    if not event_id:
        return False
    async with _lock:
        if event_id in _locked_races:
            return False
        _locked_races.add(event_id)
        return True


async def unlock_race(event_id):
    """Call this if the bet attempt fails, so race is free again."""
    if not event_id:
        return
    async with _lock:
        _locked_races.discard(event_id)
