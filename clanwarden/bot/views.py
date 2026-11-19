"""Building replies shared by commands and menu buttons.

The same information is available both as a command (/war) and as a menu
button. Both entry points call the functions below, so the logic isn't duplicated.
"""

from __future__ import annotations

from datetime import UTC, datetime

from clanwarden import texts
from clanwarden.coc.client import CocApiError, CocClient
from clanwarden.db import Database
from clanwarden.i18n import Translator
from clanwarden.services.wars import WarService


def _now() -> datetime:
    return datetime.now(UTC)


async def view_war(t: Translator, wars: WarService, clan_tag: str) -> str:
    cwl = await wars.current_cwl(clan_tag)
    if cwl and cwl.war.state.is_active:
        return texts.cwl_round(t, cwl, _now())
    if war := await wars.regular_war(clan_tag):
        return texts.war_summary(t, war, _now())
    if cwl:
        return texts.cwl_round(t, cwl, _now())
    return t("not_in_war_long")


async def view_missed(t: Translator, wars: WarService, db: Database, clan_tag: str) -> str:
    war = await wars.war_for_display(clan_tag)
    if not war:
        return t("not_in_war")
    links = await db.links_for_tags([m.tag for m in war.clan.members])
    # No pings for an on-demand command — mentions belong in the scheduled reminder.
    return texts.missed_report(t, war, _now(), links, use_mentions=False)


async def view_cwl(t: Translator, wars: WarService, clan_tag: str) -> str:
    rnd = await wars.current_cwl(clan_tag)
    return texts.cwl_round(t, rnd, _now()) if rnd else t("not_in_cwl")


async def view_cwl_table(t: Translator, wars: WarService, clan_tag: str) -> str:
    result = await wars.cwl_standings(clan_tag)
    if not result:
        return t("not_in_cwl")
    group, standings = result
    return texts.cwl_table(t, group, standings, clan_tag)


async def view_me(t: Translator, wars: WarService, db: Database, client: CocClient, user_id: int) -> str:
    links = await db.user_links(user_id)
    war = None
    if links:
        # Show attacks in the war of the first linked account's clan.
        try:
            player = await client.get_player(links[0].player_tag)
            if player.clan:
                war = await wars.war_for_display(player.clan.tag)
        except CocApiError:
            war = None
    return texts.my_accounts(t, links, war)
