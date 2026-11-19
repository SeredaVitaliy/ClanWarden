from datetime import timedelta

from cocbot.coc.client import NotFound
from cocbot.coc.models import CwlGroup, War, WarState
from cocbot.services.wars import WarService, compute_standings
from tests.factories import clan, member, war_json


class FakeClient:
    """Подменяет CocClient: отдаёт заранее подготовленные ответы и считает запросы."""

    def __init__(self, *, regular=None, group=None, cwl_wars=None):
        self.regular = regular or {"state": "notInWar"}
        self.group = group
        self.cwl_wars = cwl_wars or {}
        self.cwl_calls: list[str] = []

    async def get_current_war(self, tag):
        return War.from_api(self.regular)

    async def get_league_group(self, tag):
        return CwlGroup.from_api(self.group) if self.group else None

    async def get_cwl_war(self, war_tag):
        self.cwl_calls.append(war_tag)
        if war_tag not in self.cwl_wars:
            raise NotFound(404)
        return War.from_api(self.cwl_wars[war_tag], is_cwl=True, war_tag=war_tag)


def cwl_war(state, a, b, a_stars=0, b_stars=0):
    return war_json(
        state,
        ours=clan(a, a, [member(a + "1", "x", 1, 1 if state != "preparation" else 0)], a_stars, 50),
        theirs=clan(b, b, [member(b + "1", "y", 1)], b_stars, 40),
        attacks_per_member=1,
    )


def make_group():
    clans = ["#OURS", "#C2", "#C3", "#C4"]
    return {
        "state": "inWar",
        "season": "2026-01",
        "clans": [{"tag": t, "name": t, "clanLevel": 10} for t in clans],
        "rounds": [
            {"warTags": ["#R1A", "#R1B"]},
            {"warTags": ["#R2A", "#R2B"]},
            {"warTags": ["#R3A", "#R3B"]},
            {"warTags": ["#0", "#0"]},  # ещё не сформирован
        ],
    }


CWL_WARS = {
    # раунд 1 завершён: мы победили
    "#R1A": cwl_war("warEnded", "#C2", "#C3", 5, 3),
    "#R1B": cwl_war("warEnded", "#C4", "#OURS", 2, 6),
    # раунд 2 идёт: мы в поле opponent
    "#R2A": cwl_war("inWar", "#C2", "#OURS", 1, 2),
    "#R2B": cwl_war("inWar", "#C3", "#C4", 0, 0),
    # раунд 3 — подготовка
    "#R3A": cwl_war("preparation", "#OURS", "#C3"),
    "#R3B": cwl_war("preparation", "#C2", "#C4"),
}


async def test_current_cwl_finds_our_war_and_orients_it():
    client = FakeClient(group=make_group(), cwl_wars=CWL_WARS)
    service = WarService(client)

    rnd = await service.current_cwl("#OURS")
    assert rnd.round_number == 2
    assert rnd.war.state is WarState.IN_WAR
    assert rnd.war.clan.tag == "#OURS"  # развернули к нам
    assert rnd.war.opponent.tag == "#C2"


async def test_cwl_rounds_returns_prep_and_battle_and_caches_war_tags():
    client = FakeClient(group=make_group(), cwl_wars=CWL_WARS)
    service = WarService(client)

    _, rounds = await service.cwl_rounds("#OURS")
    assert [r.round_number for r in rounds] == [2, 3]

    client.cwl_calls.clear()
    await service.cwl_rounds("#OURS")
    # Во второй раз знаем наши warTag'и — по одному запросу на раунд.
    assert sorted(client.cwl_calls) == ["#R2A", "#R3A"]


async def test_active_wars_without_cwl():
    client = FakeClient(regular=war_json(end_in=timedelta(hours=5)))
    wars = await WarService(client).active_wars("#OURS")
    assert len(wars) == 1 and not wars[0].is_cwl


async def test_war_for_display_prefers_running_cwl():
    client = FakeClient(group=make_group(), cwl_wars=CWL_WARS)
    war = await WarService(client).war_for_display("#OURS")
    assert war.is_cwl and war.state is WarState.IN_WAR


def test_standings_with_win_bonus():
    group = CwlGroup.from_api(make_group())
    wars = [War.from_api(w, is_cwl=True, war_tag=t) for t, w in CWL_WARS.items()]
    table = {row.tag: row for row in compute_standings(group, wars)}

    # Мы: 6 звёзд + 10 за победу в 1 раунде + 2 звезды в идущем 2 раунде.
    assert table["#OURS"].stars == 18
    assert table["#OURS"].wins == 1
    # C2: 5 + 10 (победа над C3) + 1.
    assert table["#C2"].stars == 16
    first = compute_standings(group, wars)[0]
    assert first.tag == "#OURS"
