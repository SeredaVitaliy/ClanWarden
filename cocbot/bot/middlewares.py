from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from cocbot.db import Database

# Команды настройки работают в любой теме — иначе нельзя было бы
# перенести бота в другую тему.
SETUP_COMMANDS = ("/settopic", "/unsettopic", "/setclan", "/settings")


class ChatContextMiddleware(BaseMiddleware):
    """Подкладывает в хендлер настройки группы (`chat_settings`) и фильтрует темы.

    Если админ привязал бота к теме (/settopic), сообщения из других тем
    игнорируются — бот не мешает обычной переписке в группе.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        message = event.message if isinstance(event, CallbackQuery) else event
        chat_settings = None

        if isinstance(message, Message) and message.chat.type in ("group", "supergroup"):
            db: Database = data["db"]
            chat_settings = await db.ensure_chat(message.chat.id)
            if isinstance(event, Message) and chat_settings.thread_id:
                words = (event.text or "").split()
                command = words[0].split("@")[0].lower() if words else ""
                if event.message_thread_id != chat_settings.thread_id and command not in SETUP_COMMANDS:
                    return None

        data["chat_settings"] = chat_settings
        return await handler(event, data)
