from datetime import timedelta

from cocbot.coc.models import War
from cocbot.services.notifications import Event, plan_events
from tests.factories import NOW, clan, member, war_json

ALL = set(Event)


def plan(war, now=NOW, sent=frozenset(), enabled=ALL, remind_hours=3):
    return plan_events(war, now, remind_hours=remind_hours, enabled=set(enabled), already_sent=set(sent))


def test_preparation_event():
    war = War.from_api(war_json("preparation", end_in=timedelta(hours=30)))
    assert plan(war) == [Event.PREPARATION]


def test_battle_start_only_soon_after_start():
    # Война началась 30 минут назад: end = start + 24h.
    fresh = War.from_api(war_json(end_in=timedelta(hours=23, minutes=30)))
    assert Event.BATTLE_START in plan(fresh)

    # Бота добавили через 10 часов после начала — «война началась» уже не нужно.
    old = War.from_api(war_json(end_in=timedelta(hours=14)))
    assert Event.BATTLE_START not in plan(old)


def test_reminder_window():
    inside = War.from_api(war_json(end_in=timedelta(hours=2)))
    outside = War.from_api(war_json(end_in=timedelta(hours=5)))
    assert Event.REMINDER in plan(inside)
    assert Event.REMINDER not in plan(outside)
    assert Event.REMINDER in plan(outside, remind_hours=6)


def test_no_reminder_when_everyone_attacked():
    done = clan("#OURS", "Наши", [member("#P1", "A", 1, 2), member("#P2", "B", 2, 2)])
    war = War.from_api(war_json(ours=done, end_in=timedelta(hours=1)))
    assert Event.REMINDER not in plan(war)


def test_war_end_with_grace_period():
    recent = War.from_api(war_json("warEnded", end_in=-timedelta(hours=1)))
    stale = War.from_api(war_json("warEnded", end_in=-timedelta(days=1)))
    assert plan(recent) == [Event.WAR_END]
    assert plan(stale) == []


def test_already_sent_and_disabled_events_are_skipped():
    war = War.from_api(war_json(end_in=timedelta(hours=1)))
    assert plan(war, sent={"remind"}) == []
    assert plan(war, enabled={Event.WAR_END}) == []
