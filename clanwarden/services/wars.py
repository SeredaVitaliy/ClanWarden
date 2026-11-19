"""War domain logic: regular wars, Clan War League, group standings.

The tricky part is CWL. The API returns a group of 8 clans with 4 wars per
round and doesn't say which one is ours. So we:
1. fetch the group (/leaguegroup);
2. walk the rounds from the latest and find the war our clan is in;
3. orient it so that our clan is in `clan`.
The found warTag is cached: a round's pairings never change after the draw,
so the next poll needs one request instead of four.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace

from clanwarden.coc.client import CocClient, NotFound
from clanwarden.coc.models import CwlGroup, CwlStanding, War, WarResult, WarState

log = logging.getLogger(__name__)

CWL_WIN_BONUS_STARS = 10


@dataclass(frozen=True)
class CwlRound:
    group: CwlGroup
    round_number: int  # 1-based
    war: War  # oriented towards our clan


class WarService:
    def __init__(self, client: CocClient) -> None:
        self.client = client
        # (clan_tag, season, round_index) -> warTag of our war
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
        """Our clan's recent CWL rounds: the last finished one, the battle in progress
        and the next preparation. Returns up to three rounds, the latest last.

        The last finished round matters: when a new round starts, the previous one
        ends at the same moment, and without it the bot would never see that war as
        ended — no results notification and no stats.
        """
        group = await self.client.get_league_group(clan_tag)
        if not group:
            return None

        found: list[CwlRound] = []
        for index in range(len(group.rounds) - 1, -1, -1):
            if not group.rounds[index]:
                continue
            war = await self._our_war_in_round(clan_tag, group, index)
            if not war:
                continue
            found.append(
                CwlRound(group=group, round_number=index + 1, war=replace(war, cwl_season=group.season))
            )
            # Everything before the latest finished round is older history — stop here.
            if war.state is WarState.ENDED:
                break
        return group, list(reversed(found))

    async def current_cwl(self, clan_tag: str) -> CwlRound | None:
        """The CWL round most worth showing now: the battle in progress, otherwise preparation."""
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
        """All of the clan's wars that may need notifications.

        There's no regular war during CWL, but we ask both sources anyway —
        that way we never have to guess which period it is.
        """
        wars: list[War] = []
        regular, cwl = await asyncio.gather(
            self.regular_war(clan_tag), self.cwl_rounds(clan_tag), return_exceptions=True
        )
        if isinstance(regular, BaseException):
            log.warning("Regular war %s: %s", clan_tag, regular)
            if not isinstance(cwl, BaseException) and not cwl:
                raise regular
        elif regular:
            wars.append(regular)

        if isinstance(cwl, BaseException):
            log.warning("CWL %s: %s", clan_tag, cwl)
        elif cwl:
            wars.extend(r.war for r in cwl[1])
        return wars

    async def war_for_display(self, clan_tag: str) -> War | None:
        """A single war for /war: CWL takes priority while it's running."""
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
    """CWL group standings.

    Score is the sum of stars over all wars plus 10 per war win (as in the game).
    A win only counts once the war has ended. Ties on stars are broken by
    total destruction — the sum of each war's destruction percentage, as in the game.
    """
    table = {c.tag: CwlStanding(tag=c.tag, name=c.name) for c in group.clans}

    for war in wars:
        if war.state not in (WarState.IN_WAR, WarState.ENDED):
            continue
        for side in (war.clan, war.opponent):
            row = table.setdefault(side.tag, CwlStanding(tag=side.tag, name=side.name))
            row.stars += side.stars
            row.destruction += side.destruction
        if war.state is WarState.ENDED:
            for side in (war.clan, war.opponent):
                table[side.tag].wars_played += 1
            winner = {WarResult.WIN: war.clan, WarResult.LOSE: war.opponent}.get(war.result)
            if winner:
                table[winner.tag].wins += 1
                table[winner.tag].stars += CWL_WIN_BONUS_STARS

    return sorted(table.values(), key=lambda r: (r.stars, r.destruction), reverse=True)
