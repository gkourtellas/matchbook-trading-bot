"""Tracks which event IDs currently have an active bet, and which
overlap group + market type placed it.

Rule: a strategy is blocked from betting an event only if a DIFFERENT
overlap_group already has an active bet of the SAME market type
(e.g. Match Odds vs Match Odds) on that event. Same group never
blocks (they're meant to co-bet). Different market types never block
each other either, even across different groups — a "Win" (Match
Odds) strategy and a "GG" (Both Teams To Score) strategy betting the
same match are not considered overlapping.

Strategies with no overlap_group set never touch this tracker — they
don't block anyone, and nobody blocks them.
"""

import asyncio

_lock = asyncio.Lock()
_active = {}  # event_id -> set of (group, market_type) tuples currently holding a bet on it


async def register(event_id, group, market_type):
    """Call right after a bet is placed."""
    if not group or not event_id:
        return
    async with _lock:
        _active.setdefault(event_id, set()).add((group, market_type))


async def unregister(event_id, group, market_type):
    """Call once a bet on this event is no longer active (settled or cashed out)."""
    if not group or not event_id:
        return
    async with _lock:
        entries = _active.get(event_id)
        if not entries:
            return
        entries.discard((group, market_type))
        if not entries:
            del _active[event_id]


async def blocked_by_other_group(event_id, group, market_type):
    """True if this event already has an active bet from a DIFFERENT
    group of the SAME market type. Same group never blocks. Different
    market type never blocks, even from a different group.
    """
    if not group or not event_id:
        return False
    async with _lock:
        entries = _active.get(event_id, set())
        return any(g != group and mtype == market_type for g, mtype in entries)
