"""Общие помощники для хендлеров."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message, User

from cocbot.coc.client import (
    AccessDenied,
    CocApiError,
    CocClient,
    InvalidIp,
    Maintenance,
    NotFound,
    RateLimited,
)
from cocbot.coc.tags import normalize_tag
from cocbot.db import ChatSettings, Database

log = logging.getLogger(__name__)


class UserFacingError(Exception):
    """Ошибка, текст которой можно показать пользователю как есть."""


def is_group(message: Message) -> bool:
    return message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


def api_error_text(exc: CocApiError) -> str:
    if isinstance(exc, InvalidIp):
        log.error("CoC API отклонил IP сервера: %s", exc.message)
        return "⚠️ Бот не может обратиться к API игры: ключ не подходит к IP сервера. Сообщите владельцу бота."
    if isinstance(exc, AccessDenied):
        return (
            "🔒 Журнал войн клана закрыт. Глава или соруководитель может открыть его: "
            "клан → Настройки → «Журнал войн: открыт»."
        )
    if isinstance(exc, NotFound):
        return "🤷 Клан или игрок не найден. Проверьте тег."
    if isinstance(exc, Maintenance):
        return "🛠 Clash of Clans сейчас на техобслуживании. Попробуйте позже."
    if isinstance(exc, RateLimited):
        return "🐢 Слишком много запросов к API игры. Попробуйте через минуту."
    log.warning("Ошибка CoC API: %s", exc)
    return "😵 API игры сейчас не отвечает. Попробуйте позже."


async def is_admin(bot: Bot, message_or_chat_id: Message | int, user: User | None) -> bool:
    if isinstance(message_or_chat_id, Message):
        message = message_or_chat_id
        # Анонимный админ пишет от имени самой группы.
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
    """Какой клан имеет в виду пользователь.

    Порядок: тег из аргумента команды → клан группы → клан первого
    привязанного аккаунта (для личных сообщений).
    """
    if arg:
        tag = normalize_tag(arg.split()[0])
        if not tag:
            raise UserFacingError("Некорректный тег клана. Пример: <code>/war #2PP</code>")
        return tag
    if chat and chat.clan_tag:
        return chat.clan_tag
    if chat is not None:
        raise UserFacingError("К этой группе ещё не привязан клан. Админ может сделать это: /setclan #ТЕГ")

    if user_id:
        for link in await db.user_links(user_id):
            try:
                player = await client.get_player(link.player_tag)
            except CocApiError:
                continue
            if player.clan:
                return player.clan.tag
    raise UserFacingError(
        "Не понимаю, про какой клан речь. Привяжите аккаунт (/link #ТЕГ) "
        "или укажите тег клана: <code>/war #ТЕГ</code>"
    )


def schedule_delete(bot: Bot, chat_id: int, message_ids: list[int], minutes: int) -> None:
    """Удалить сообщения через N минут, чтобы не засорять чат клана.

    Таймеры живут в памяти: после перезапуска бота уже запланированные
    удаления пропадут. Для MVP это осознанный компромисс.
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
