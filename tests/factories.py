"""Сборщики JSON в формате Clash of Clans API для тестов."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

NOW = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)


def api_time(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S.000Z")


def member(tag: str, name: str, position: int, attacks: int = 0, stars: int = 2) -> dict:
    return {
        "tag": tag,
        "name": name,
        "mapPosition": position,
        "townhallLevel": 15,
        "attacks": [
            {
                "attackerTag": tag,
                "defenderTag": "#Q0",
                "stars": stars,
                "destructionPercentage": 75,
                "order": i + 1,
            }
            for i in range(attacks)
        ],
    }


def clan(tag: str, name: str, members: list[dict], stars: int = 0, destruction: float = 0.0) -> dict:
    return {
        "tag": tag,
        "name": name,
        "stars": stars,
        "destructionPercentage": destruction,
        "attacks": sum(len(m["attacks"]) for m in members),
        "members": members,
    }


def war_json(
    state: str = "inWar",
    *,
    ours: dict | None = None,
    theirs: dict | None = None,
    end_in: timedelta = timedelta(hours=10),
    now: datetime = NOW,
    attacks_per_member: int | None = 2,
) -> dict:
    end = now + end_in
    start = end - timedelta(hours=24)
    prep = start - timedelta(hours=23)
    data = {
        "state": state,
        "teamSize": 2,
        "preparationStartTime": api_time(prep),
        "startTime": api_time(start),
        "endTime": api_time(end),
        "clan": ours or clan("#OURS", "Наши", [member("#P1", "Alice", 1, 2), member("#P2", "Bob", 2, 0)]),
        "opponent": theirs
        or clan("#THEM", "Враги", [member("#E1", "Eve", 1, 1), member("#E2", "Mallory", 2, 0)]),
    }
    if attacks_per_member is not None:
        data["attacksPerMember"] = attacks_per_member
    return data
