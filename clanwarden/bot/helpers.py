"""Shared helpers for handlers."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message, User

from clanwarden.coc.client import (
    AccessDenied,
    CocApiError,
    CocClient,
    InvalidIp,
    Maintenance,
    NotFound,
    RateLimited,
)
from clanwarden.coc.tags import normalize_tag
from clanwarden.db import ChatSettings, Database

log = logging.getLogger(__name__)


class UserFacingError(Exception):
    """An error whose message can be shown to the user. Carries an i18n key."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def is_group(message: Message) -> bool:
    return message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


def api_error_key(exc: CocApiError) -> str:
    """Map an API error to a message the user can act on."""
    if isinstance(exc, InvalidIp):
        log.error("The CoC API rejected this server's IP: %s", exc.message)
        return "err_invalid_ip"
    if isinstance(exc, AccessDenied):
        return "err_private_log"
    if isinstance(exc, NotFound):
        return "err_not_found"
    if isinstance(exc, Maintenance):
        return "err_maintenance"
    if isinstance(exc, RateLimited):
        return "err_rate_limited"
    log.warning("CoC API error: %s", exc)
    return "err_api"


async def is_admin(bot: Bot, message_or_chat_id: Message | int, user: User | None) -> bool:
    if isinstance(message_or_chat_id, Message):
        message = message_or_chat_id
        # An anonymous admin posts on behalf of the group itself.
        if message.sender_chat and message.sender_chat.id == message.chat.id:
            return True
        chat_id = message.chat.id
    else:
        chat_id = message_or_chat_id
    if not user:
        return False
    try:
        member = await bot.get_chat_member(chat_id, user.id)
    except TelegramAPIError:
        return False
    return member.status in ("creator", "administrator")


async def resolve_clan(
    *,
    arg: str | None,
    chat: ChatSettings | None,
    user_id: int | None,
    db: Database,
    client: CocClient,
) -> str:
    """Figure out which clan the user means.

    Order: tag passed as an argument → the group's clan → the clan of the
    user's first linked account (for private chats).
    """
    if arg:
        tag = normalize_tag(arg.split()[0])
        if not tag:
            raise UserFacingError("err_bad_clan_tag")
        return tag
    if chat and chat.clan_tag:
        return chat.clan_tag
    if chat is not None:
        raise UserFacingError("err_no_clan")

    if user_id:
        for link in await db.user_links(user_id):
            try:
                player = await client.get_player(link.player_tag)
            except CocApiError:
                continue
            if player.clan:
                return player.clan.tag
    raise UserFacingError("err_which_clan")


def schedule_delete(bot: Bot, chat_id: int, message_ids: list[int], minutes: int) -> None:
    """Delete messages after N minutes to keep the clan chat clean.

    Timers live in memory: deletions scheduled before a restart are lost.
    That's an accepted trade-off for an MVP.
    """
    if minutes <= 0 or not message_ids:
        return

    async def _later() -> None:
        await asyncio.sleep(minutes * 60)
        for mid in message_ids:
            with contextlib.suppress(TelegramAPIError):
                await bot.delete_message(chat_id, mid)

    asyncio.get_running_loop().create_task(_later())


async def reply(message: Message, text: str, chat: ChatSettings | None, **kwargs) -> Message:
    sent = await message.answer(text, disable_web_page_preview=True, **kwargs)
    if chat and chat.autodelete_min and is_group(message):
        schedule_delete(
            message.bot, message.chat.id, [message.message_id, sent.message_id], chat.autodelete_min
        )
    return sent
