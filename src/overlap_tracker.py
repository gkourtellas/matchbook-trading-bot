"""Tracks which event IDs currently have an active bet, and which
overlap group placed it.

Used so strategies tagged with the same overlap_group can freely bet
the same match at the same time, while a strategy from a DIFFERENT
group is blocked from also betting that match while it's still open.

Strategies with no overlap_group set never touch this tracker — they
don't block anyone, and nobody blocks them. This keeps every existing
strategy working exactly as before; the group check only applies to
strategies that opt in by setting overlap_group.
"""

import asyncio

_lock = asyncio.Lock()
_active = {}  # event_id -> set of group names currently holding a bet on it


async def register(event_id, group):
    """Call right after a bet is placed."""
    if not group or not event_id:
        return
    async with _lock:
        _active.setdefault(event_id, set()).add(group)


async def unregister(event_id, group):
    """Call once a bet on this event is no longer active (settled or cashed out)."""
    if not group or not event_id:
        return
    async with _lock:
        groups = _active.get(event_id)
        if not groups:
            return
        groups.discard(group)
        if not groups:
            del _active[event_id]


async def blocked_by_other_group(event_id, group):
    """True if this event already has an active bet from a group other
    than the one asking. Same group, or no group set, is never blocked.
    """
    if not group or not event_id:
        return False
    async with _lock:
        groups = _active.get(event_id, set())
        return any(g != group for g in groups)
