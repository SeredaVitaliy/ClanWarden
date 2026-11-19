from datetime import timedelta

import pytest

from cocbot.coc.models import War, WarResult, WarState, parse_time
from cocbot.coc.tags import encode_tag, normalize_tag
from tests.factories import clan, member, war_json


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("#2PP", "#2PP"),
        ("2pp", "#2PP"),
        ("  #2pp  ", "#2PP"),
        ("#2PO", "#2P0"),  # буква O -> ноль
        ("#ABC", None),  # A и B не входят в алфавит тегов
        ("", None),
        (None, None),
        ("#2", None),  # слишком короткий
    ],
)
def test_normalize_tag(raw, expected):
    assert normalize_tag(raw) == expected


def test_encode_tag():
    assert encode_tag("#2PP") == "%232PP"


def test_parse_time():
    dt = parse_time("20260110T120000.000Z")
    assert (dt.year, dt.hour, dt.tzinfo is not None) == (2026, 12, True)
    assert parse_time("garbage") is None
    assert parse_time(None) is None


def test_war_parsing_and_attacks_left():
    war = War.from_api(war_json())
    assert war.state is WarState.IN_WAR
    assert war.total_attacks == 4
    bob = war.find_member("#P2")
    assert war.attacks_left(bob) == 2
    assert [m.name for m in war.members_with_attacks_left()] == ["Bob"]


def test_unknown_state_is_not_in_war():
    assert War.from_api({"state": "somethingNew"}).state is WarState.NOT_IN_WAR


def test_cwl_defaults_to_one_attack():
    war = War.from_api(war_json(attacks_per_member=None), is_cwl=True, war_tag="#W1")
    assert war.attacks_per_member == 1


def test_oriented_swaps_sides_and_key_is_stable():
    war = War.from_api(war_json())
    flipped = war.oriented("#THEM")
    assert flipped.clan.tag == "#THEM"
    assert flipped.opponent.tag == "#OURS"
    assert flipped.key == war.key
    assert war.oriented("#OURS") is war


def test_key_differs_between_wars_with_same_opponent():
    first = War.from_api(war_json())
    second = War.from_api(war_json(end_in=timedelta(days=3)))
    assert first.key != second.key


@pytest.mark.parametrize(
    ("ours", "theirs", "expected"),
    [
        ((10, 80.0), (9, 99.0), WarResult.WIN),
        ((9, 99.0), (10, 50.0), WarResult.LOSE),
        ((10, 90.0), (10, 85.0), WarResult.WIN),  # при равенстве звёзд решает процент
        ((10, 90.0), (10, 90.0), WarResult.TIE),
    ],
)
def test_result(ours, theirs, expected):
    data = war_json(
        "warEnded",
        ours=clan("#OURS", "A", [member("#P1", "a", 1)], *ours),
        theirs=clan("#THEM", "B", [member("#E1", "b", 1)], *theirs),
    )
    assert War.from_api(data).result is expected
