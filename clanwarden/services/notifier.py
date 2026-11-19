"""Background polling and notification delivery.

Every POLL_INTERVAL_SECONDS:
1. load all groups that have a clan and group them by clan tag — if one clan
   is connected to two groups, the API is called only once;
2. for each of the clan's wars decide (``plan_events``) what is due;
3. send it and record it in the ``sent_events`` journal.

The journal is written *after* a successful send. If Telegram is unreachable,
the event will be retried on the next poll instead of being lost.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from clanwarden import texts
from clanwarden.coc.client import CocApiError, InvalidIp, Maintenance
from clanwarden.coc.models import War, WarState
from clanwarden.db import ChatSettings, Database, Link
from clanwarden.i18n import Translator
from clanwarden.services.notifications import Event, dm_event_key, enabled_events, plan_events
from clanwarden.services.wars import WarService

log = logging.getLogger(__name__)


async def send_html(bot: Bot, chat_id: int, text: str, thread_id: int | None = None) -> int | None:
    """Send a message, handling the usual Telegram errors. Returns message_id or None."""
    for _ in range(3):
        try:
            msg = await bot.send_message(
                chat_id, text, message_thread_id=thread_id, disable_web_page_preview=True
            )
            return msg.message_id
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
        except TelegramBadRequest as exc:
            # The topic was deleted or closed — fall back to the main chat instead of going silent.
            if thread_id and "thread" in str(exc).lower():
                log.warning(
                    "Topic %s in chat %s is unavailable, posting to the main chat", thread_id, chat_id
                )
                thread_id = None
                continue
            log.error("Failed to send to %s: %s", chat_id, exc)
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
        log.info("War polling started, interval %ss", self.interval)
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Error in the notification loop")
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
                    "The CoC API key doesn't allow this server's IP. Create a new key at "
                    "developer.clashofclans.com for the current IP. API response: %s",
                    exc.message,
                )
                return
            except Maintenance:
                log.info("Clash of Clans is under maintenance, skipping this poll")
                return
            except CocApiError as exc:
                log.warning("Clan %s: %s", clan_tag, exc)
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
            war, now, remind_hours=chat.remind_hours, enabled=enabled_events(chat), already_sent=sent
        )
        t = Translator(chat.language)
        for event in events:
            text = self._render(t, event, war, now, chat, links)
            try:
                message_id = await send_html(self.bot, chat.chat_id, text, chat.thread_id)
            except TelegramForbiddenError:
                log.warning("The bot was removed from chat %s — dropping its settings", chat.chat_id)
                await self.db.delete_chat(chat.chat_id)
                return
            if message_id:
                await self.db.mark_sent(chat.chat_id, war.key, event.value)
                log.info("Chat %s: sent %s (%s)", chat.chat_id, event.value, war.key)

    async def _notify_players(
        self, war: War, now: datetime, links: dict[str, Link], chats: list[ChatSettings]
    ) -> None:
        """Personal reminders for players who still have attacks left."""
        if war.state is not WarState.IN_WAR or not war.end:
            return
        remind_hours = min(c.remind_hours for c in chats)
        if not timedelta(0) < war.end - now <= timedelta(hours=remind_hours):
            return

        pending = [(m, links[m.tag]) for m in war.members_with_attacks_left() if m.tag in links]
        recipients = await self.db.dm_recipients(list({link.telegram_id for _, link in pending}))
        for member, link in pending:
            if link.telegram_id not in recipients:
                continue
            key = dm_event_key(member.tag)
            if key in await self.db.sent_events(link.telegram_id, war.key):
                continue
            t = Translator(recipients[link.telegram_id])
            try:
                message_id = await send_html(
                    self.bot, link.telegram_id, texts.dm_reminder(t, war, now, member)
                )
            except TelegramForbiddenError:
                # The user blocked the bot — stop trying.
                await self.db.disable_dm_reminders(link.telegram_id)
                continue
            if message_id:
                await self.db.mark_sent(link.telegram_id, war.key, key)

    @staticmethod
    def _render(
        t: Translator, event: Event, war: War, now: datetime, chat: ChatSettings, links: dict[str, Link]
    ) -> str:
        if event is Event.PREPARATION:
            return texts.notify_preparation(t, war, now)
        if event is Event.BATTLE_START:
            return texts.notify_battle_start(t, war, now, chat.rules)
        if event is Event.REMINDER:
            return texts.notify_reminder(t, war, now, links, use_mentions=chat.mention_players)
        return texts.notify_war_end(t, war, now)
