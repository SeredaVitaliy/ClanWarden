"""Which notifications are due.

This is a pure function: in — a war, the current time, chat settings and what
has already been sent; out — a list of events. No API or Telegram calls, so
every edge case is covered by plain unit tests.

Why not a "fire in 3 hours" timer: the bot may restart, the server may have
been down, the war may have started before the bot joined the group. The
"look at the current state on every poll and check the journal" approach
survives all of that: each event is sent exactly once, as soon as its window opens.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from clanwarden.coc.models import War, WarState
from clanwarden.db import ChatSettings


class Event(StrEnum):
    PREPARATION = "prep"  # opponent found, preparation day
    BATTLE_START = "start"  # battle day started
    REMINDER = "remind"  # N hours left and some attacks are unused
    WAR_END = "end"  # war results


# How "stale" an event may be and still be worth sending. If the bot joins a
# group 10 hours into a war, "the war has started" is no longer useful; one
# hour in, it still is.
BATTLE_START_GRACE = timedelta(hours=2)
WAR_END_GRACE = timedelta(hours=6)


def plan_events(
    war: War,
    now: datetime,
    *,
    remind_hours: int,
    enabled: set[Event],
    already_sent: set[str],
) -> list[Event]:
    events: list[Event] = []

    def want(event: Event, condition: bool) -> None:
        if condition and event in enabled and event.value not in already_sent:
            events.append(event)

    if war.state is WarState.PREPARATION:
        want(Event.PREPARATION, war.start is None or now < war.start)

    elif war.state is WarState.IN_WAR:
        recent_start = war.start is not None and now - war.start <= BATTLE_START_GRACE
        want(Event.BATTLE_START, recent_start)

        if war.end is not None:
            left = war.end - now
            in_window = timedelta(0) < left <= timedelta(hours=remind_hours)
            want(Event.REMINDER, in_window and bool(war.members_with_attacks_left()))

    elif war.state is WarState.ENDED:
        want(Event.WAR_END, war.end is None or now - war.end <= WAR_END_GRACE)

    return events


def enabled_events(chat: ChatSettings) -> set[Event]:
    flags = {
        Event.PREPARATION: chat.notify_prep,
        Event.BATTLE_START: chat.notify_start,
        Event.REMINDER: chat.notify_remind,
        Event.WAR_END: chat.notify_end,
    }
    return {event for event, on in flags.items() if on}


def dm_event_key(player_tag: str) -> str:
    """Journal key for a personal reminder: one per player account in the war."""
    return f"{Event.REMINDER.value}:{player_tag}"
