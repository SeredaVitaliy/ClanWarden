"""Сборка ответов для команд и кнопок меню.

Одна и та же информация доступна и командой (/war), и кнопкой в меню.
Чтобы не дублировать логику, обе точки входа вызывают функции отсюда.
"""

from __future__ import annotations

from datetime import UTC, datetime

from cocbot import texts
from cocbot.coc.client import CocApiError, CocClient
from cocbot.db import ChatSettings, Database
from cocbot.services.wars import WarService


def _now() -> datetime:
    return datetime.now(UTC)


async def view_war(wars: WarService, clan_tag: str) -> str:
    cwl = await wars.current_cwl(clan_tag)
    if cwl and cwl.war.state.is_active:
        return texts.cwl_round(cwl, _now())
    war = await wars.regular_war(clan_tag)
    if war:
        return texts.war_summary(war, _now())
    if cwl:
        return texts.cwl_round(cwl, _now())
    return "😴 Сейчас клан не воюет. Как только начнётся поиск или подготовка — здесь появится информация."


async def view_missed(wars: WarService, db: Database, clan_tag: str, chat: ChatSettings | None) -> str:
    war = await wars.war_for_display(clan_tag)
    if not war:
        return "😴 Сейчас клан не воюет."
    links = await db.links_for_tags([m.tag for m in war.clan.members])
    # В ответ на команду не упоминаем — пинг уместен в напоминании, а не по каждому запросу.
    return texts.missed_report(war, _now(), links, use_mentions=False)


async def view_cwl(wars: WarService, clan_tag: str) -> str:
    rnd = await wars.current_cwl(clan_tag)
    if not rnd:
        return "🏆 Клан сейчас не участвует в Лиге войн кланов."
    return texts.cwl_round(rnd, _now())


async def view_cwl_table(wars: WarService, clan_tag: str) -> str:
    result = await wars.cwl_standings(clan_tag)
    if not result:
        return "🏆 Клан сейчас не участвует в Лиге войн кланов."
    group, standings = result
    return texts.cwl_table(group, standings, clan_tag)


async def view_me(wars: WarService, db: Database, client: CocClient, user_id: int) -> str:
    links = await db.user_links(user_id)
    war = None
    if links:
        # Показываем атаки в войне клана первого аккаунта.
        try:
            player = await client.get_player(links[0].player_tag)
            if player.clan:
                war = await wars.war_for_display(player.clan.tag)
        except CocApiError:
            war = None
    return texts.my_accounts(links, war, _now())
