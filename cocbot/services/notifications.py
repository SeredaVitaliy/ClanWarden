"""Какие уведомления пора отправить.

Это чистая функция: на вход — война, текущее время, настройки чата и список
уже отправленного; на выход — список событий. Никаких запросов к API и
Telegram, поэтому её легко покрыть тестами на все пограничные случаи.

Почему не «таймер на 3 часа до конца»: бот может быть перезапущен, сервер
мог спать, война могла начаться раньше, чем бота добавили в группу. Подход
«на каждом опросе смотрим на состояние и сверяемся с журналом» устойчив ко
всему этому: событие отправится один раз, как только наступит его окно.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from cocbot.coc.models import War, WarState
from cocbot.db import ChatSettings


class Event(StrEnum):
    PREPARATION = "prep"  # нашли соперника, идёт день подготовки
    BATTLE_START = "start"  # начался день атак
    REMINDER = "remind"  # до конца осталось N часов, а атаки ещё есть
    WAR_END = "end"  # итоги войны


# Насколько «старое» событие ещё имеет смысл присылать. Например, если бота
# добавили в группу через 10 часов после начала войны, сообщение «война
# началась» уже не нужно, а через час — ещё уместно.
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
    """Ключ личного напоминания: по одному на каждый аккаунт игрока в войне."""
    return f"{Event.REMINDER.value}:{player_tag}"
