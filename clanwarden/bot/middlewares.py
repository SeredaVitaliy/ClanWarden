from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from clanwarden.db import ChatSettings, Database
from clanwarden.i18n import Translator, normalize_language

# Setup commands work in any topic — otherwise the bot could never be moved to another topic.
SETUP_COMMANDS = ("/settopic", "/unsettopic", "/setclan", "/settings", "/language")


class ChatContextMiddleware(BaseMiddleware):
    """Injects ``chat_settings`` and a translator ``t`` into handlers, and filters topics.

    Language resolution:
    - group: the language chosen with /language, otherwise English;
    - private chat: the user's chosen language, otherwise their Telegram language.

    If an admin bound the bot to a topic (/settopic), messages from other topics
    are ignored so the bot doesn't get in the way of normal conversation.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        db: Database = data["db"]
        message = event.message if isinstance(event, CallbackQuery) else event
        user: User | None = getattr(event, "from_user", None)
        chat_settings: ChatSettings | None = None

        if isinstance(message, Message) and message.chat.type in ("group", "supergroup"):
            chat_settings = await db.ensure_chat(message.chat.id)
            if (
                isinstance(event, Message)
                and chat_settings.thread_id
                and event.message_thread_id != chat_settings.thread_id
                and not _is_setup_command(event)
            ):
                return None
            language = chat_settings.language
        else:
            language = await db.user_language(user.id) if user else None
            language = language or normalize_language(user.language_code if user else None)

        data["chat_settings"] = chat_settings
        data["t"] = Translator(language)
        return await handler(event, data)


def _is_setup_command(message: Message) -> bool:
    words = (message.text or "").split()
    return bool(words) and words[0].split("@")[0].lower() in SETUP_COMMANDS
