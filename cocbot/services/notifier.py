"""Фоновый опрос API и рассылка уведомлений.

Раз в POLL_INTERVAL_SECONDS:
1. берём все группы с привязанным кланом и группируем по тегу клана —
   если один клан подключён в двух группах, в API ходим один раз;
2. для каждой войны клана решаем (plan_events), что пора отправить;
3. отправляем и записываем в журнал sent_events.

Запись в журнал идёт после успешной отправки. Если Telegram недоступен,
событие попробуем отправить на следующем опросе, а не потеряем.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from cocbot import texts
from cocbot.coc.client import CocApiError, InvalidIp, Maintenance
from cocbot.coc.models import War, WarState
from cocbot.db import ChatSettings, Database, Link
from cocbot.services.notifications import Event, dm_event_key, enabled_events, plan_events
from cocbot.services.wars import WarService

log = logging.getLogger(__name__)


async def send_html(bot: Bot, chat_id: int, text: str, thread_id: int | None = None) -> int | None:
    """Отправка с обработкой типичных ошибок Telegram. Возвращает message_id или None."""
    for _ in range(3):
        try:
            msg = await bot.send_message(
                chat_id,
                text,
                message_thread_id=thread_id,
                disable_web_page_preview=True,
            )
            return msg.message_id
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
        except TelegramBadRequest as exc:
            # Тему удалили или закрыли — пишем в общий чат, а не молчим.
            if thread_id and "thread" in str(exc).lower():
                log.warning("Тема %s в чате %s недоступна, пишу в общий чат", thread_id, chat_id)
                thread_id = None
                continue
            log.error("Не удалось отправить в %s: %s", chat_id, exc)
            return None
    return None


class Notifier:
    def __init__(self, bot: Bot, db: Database, wars: WarService, interval: int) -> None:
        self.bot = bot
        self.db = db
        self.wars = wars
        self.interval = interval
        self._last_prune: datetime | None = None

    async def run(self) -> None:
        log.info("Опрос войн запущен, интервал %s с", self.interval)
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Ошибка в цикле уведомлений")
            await asyncio.sleep(self.interval)

    async def tick(self, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        by_clan: dict[str, list[ChatSettings]] = defaultdict(list)
        for chat in await self.db.configured_chats():
            by_clan[chat.clan_tag].append(chat)

        for clan_tag, chats in by_clan.items():
            try:
                wars = await self.wars.active_wars(clan_tag)
            except InvalidIp as exc:
                log.error(
                    "Ключ CoC API не подходит для IP этого сервера. Создайте новый ключ "
                    "на developer.clashofclans.com для текущего IP. Ответ API: %s",
                    exc.message,
                )
                return
            except Maintenance:
                log.info("Clash of Clans на техобслуживании, пропускаю опрос")
                return
            except CocApiError as exc:
                log.warning("Клан %s: %s", clan_tag, exc)
                continue

            for war in wars:
                links = await self.db.links_for_tags([m.tag for m in war.clan.members])
                for chat in chats:
                    await self._notify_chat(chat, war, now, links)
                await self._notify_players(war, now, links, chats)

        if not self._last_prune or now - self._last_prune > timedelta(days=1):
            await self.db.prune_sent_events()
            self._last_prune = now

    async def _notify_chat(self, chat: ChatSettings, war: War, now: datetime, links: dict[str, Link]) -> None:
        sent = await self.db.sent_events(chat.chat_id, war.key)
        events = plan_events(
            war,
            now,
            remind_hours=chat.remind_hours,
            enabled=enabled_events(chat),
            already_sent=sent,
        )
        for event in events:
            text = self._render(event, war, now, chat, links)
            try:
                message_id = await send_html(self.bot, chat.chat_id, text, chat.thread_id)
            except TelegramForbiddenError:
                log.warning("Бота удалили из чата %s — отключаю его настройки", chat.chat_id)
                await self.db.delete_chat(chat.chat_id)
                return
            if message_id:
                await self.db.mark_sent(chat.chat_id, war.key, event.value)
                log.info("Чат %s: отправлено %s (%s)", chat.chat_id, event.value, war.key)

    async def _notify_players(
        self, war: War, now: datetime, links: dict[str, Link], chats: list[ChatSettings]
    ) -> None:
        """Личные напоминания игрокам, у которых остались атаки."""
        if war.state is not WarState.IN_WAR or not war.end:
            return
        remind_hours = min(c.remind_hours for c in chats)
        left = war.end - now
        if not timedelta(0) < left <= timedelta(hours=remind_hours):
            return

        pending = [(m, links[m.tag]) for m in war.members_with_attacks_left() if m.tag in links]
        recipients = await self.db.dm_recipients(list({link.telegram_id for _, link in pending}))
        for member, link in pending:
            if link.telegram_id not in recipients:
                continue
            key = dm_event_key(member.tag)
            if key in await self.db.sent_events(link.telegram_id, war.key):
                continue
            try:
                message_id = await send_html(self.bot, link.telegram_id, texts.dm_reminder(war, now, member))
            except TelegramForbiddenError:
                # Человек заблокировал бота — больше не пытаемся.
                await self.db.toggle_dm_reminders(link.telegram_id)
                continue
            if message_id:
                await self.db.mark_sent(link.telegram_id, war.key, key)

    @staticmethod
    def _render(event: Event, war: War, now: datetime, chat: ChatSettings, links: dict[str, Link]) -> str:
        if event is Event.PREPARATION:
            return texts.notify_preparation(war, now)
        if event is Event.BATTLE_START:
            return texts.notify_battle_start(war, now, chat.rules)
        if event is Event.REMINDER:
            return texts.notify_reminder(war, now, links, use_mentions=chat.mention_players)
        return texts.notify_war_end(war, now)
