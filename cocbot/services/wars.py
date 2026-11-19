"""Бизнес-логика вокруг войн: обычная война, ЛВК, таблица группы.

Главная сложность здесь — ЛВК. API отдаёт группу из 8 кланов и по 4 войны
на раунд, и сам не говорит, какая из них наша. Поэтому:
1. берём группу (/leaguegroup);
2. идём по раундам с конца и ищем войну, где участвует наш клан;
3. разворачиваем её так, чтобы наш клан был в `clan`.
Найденный warTag запоминаем: состав раунда после жеребьёвки не меняется,
и при следующем опросе хватает одного запроса вместо четырёх.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from cocbot.coc.client import CocClient, NotFound
from cocbot.coc.models import CwlGroup, CwlStanding, War, WarResult, WarState

log = logging.getLogger(__name__)

CWL_WIN_BONUS_STARS = 10


@dataclass(frozen=True)
class CwlRound:
    group: CwlGroup
    round_number: int  # с 1
    war: War  # развёрнута к нашему клану


class WarService:
    def __init__(self, client: CocClient) -> None:
        self.client = client
        # (clan_tag, season, round_index) -> warTag нашей войны
        self._our_war_tags: dict[tuple[str, str, int], str] = {}

    async def regular_war(self, clan_tag: str) -> War | None:
        war = await self.client.get_current_war(clan_tag)
        return None if war.state is WarState.NOT_IN_WAR else war

    async def _our_war_in_round(self, clan_tag: str, group: CwlGroup, index: int) -> War | None:
        key = (clan_tag, group.season, index)
        known = self._our_war_tags.get(key)
        if known:
            return (await self.client.get_cwl_war(known)).oriented(clan_tag)

        for war_tag in group.rounds[index]:
            try:
                war = await self.client.get_cwl_war(war_tag)
            except NotFound:
                continue
            if war.involves(clan_tag):
                self._our_war_tags[key] = war_tag
                return war.oriented(clan_tag)
        return None

    async def cwl_rounds(self, clan_tag: str) -> tuple[CwlGroup, list[CwlRound]] | None:
        """Текущие раунды ЛВК нашего клана: идущий бой и/или подготовка следующего.

        Возвращает до двух раундов, самый свежий последним.
        """
        group = await self.client.get_league_group(clan_tag)
        if not group or not group.is_active:
            return None

        found: list[CwlRound] = []
        for index in range(len(group.rounds) - 1, -1, -1):
            if not group.rounds[index]:
                continue
            war = await self._our_war_in_round(clan_tag, group, index)
            if not war:
                continue
            found.append(CwlRound(group=group, round_number=index + 1, war=war))
            # Ниже по раундам только завершённые войны — дальше не ищем.
            if war.state in (WarState.IN_WAR, WarState.ENDED):
                break
        return group, list(reversed(found))

    async def current_cwl(self, clan_tag: str) -> CwlRound | None:
        """Раунд ЛВК, который сейчас важнее всего показать: идущий бой, иначе подготовка."""
        result = await self.cwl_rounds(clan_tag)
        if not result:
            return None
        _, rounds = result
        for state in (WarState.IN_WAR, WarState.PREPARATION, WarState.ENDED):
            for rnd in reversed(rounds):
                if rnd.war.state is state:
                    return rnd
        return None

    async def active_wars(self, clan_tag: str) -> list[War]:
        """Все войны клана, по которым имеет смысл слать уведомления.

        Во время ЛВК обычной войны нет, но спрашиваем оба источника:
        так не нужно гадать, какой сейчас период.
        """
        wars: list[War] = []
        regular, cwl = await asyncio.gather(
            self.regular_war(clan_tag), self.cwl_rounds(clan_tag), return_exceptions=True
        )
        if isinstance(regular, BaseException):
            log.warning("Обычная война %s: %s", clan_tag, regular)
            if not isinstance(cwl, BaseException) and not cwl:
                raise regular
        elif regular:
            wars.append(regular)

        if isinstance(cwl, BaseException):
            log.warning("ЛВК %s: %s", clan_tag, cwl)
        elif cwl:
            wars.extend(r.war for r in cwl[1])
        return wars

    async def war_for_display(self, clan_tag: str) -> War | None:
        """Одна война для команды /war: ЛВК в приоритете, если она идёт."""
        cwl = await self.current_cwl(clan_tag)
        if cwl and cwl.war.state.is_active:
            return cwl.war
        regular = await self.regular_war(clan_tag)
        if regular:
            return regular
        return cwl.war if cwl else None

    async def cwl_standings(self, clan_tag: str) -> tuple[CwlGroup, list[CwlStanding]] | None:
        group = await self.client.get_league_group(clan_tag)
        if not group:
            return None
        tags = [t for rnd in group.rounds for t in rnd]
        wars = await asyncio.gather(*(self.client.get_cwl_war(t) for t in tags), return_exceptions=True)
        return group, compute_standings(group, [w for w in wars if isinstance(w, War)])


def compute_standings(group: CwlGroup, wars: list[War]) -> list[CwlStanding]:
    """Таблица группы ЛВК.

    Очки — сумма звёзд за все войны плюс 10 за каждую победу (как в игре).
    Победа засчитывается только в завершённой войне. При равенстве звёзд
    выше тот, у кого больше суммарное разрушение.
    """
    table = {c.tag: CwlStanding(tag=c.tag, name=c.name) for c in group.clans}

    for war in wars:
        if war.state not in (WarState.IN_WAR, WarState.ENDED):
            continue
        for side in (war.clan, war.opponent):
            row = table.setdefault(side.tag, CwlStanding(tag=side.tag, name=side.name))
            row.stars += side.stars
            row.destruction += side.destruction * war.team_size
        if war.state is WarState.ENDED:
            for side in (war.clan, war.opponent):
                table[side.tag].wars_played += 1
            winner = {WarResult.WIN: war.clan, WarResult.LOSE: war.opponent}.get(war.result)
            if winner:
                table[winner.tag].wins += 1
                table[winner.tag].stars += CWL_WIN_BONUS_STARS

    return sorted(table.values(), key=lambda r: (r.stars, r.destruction), reverse=True)
