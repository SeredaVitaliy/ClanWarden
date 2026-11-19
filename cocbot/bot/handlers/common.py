"""/start, /help, приветствие при добавлении в группу."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import JOIN_TRANSITION, ChatMemberUpdatedFilter, Command, CommandStart
from aiogram.types import ChatMemberUpdated, Message

from cocbot import texts
from cocbot.bot.helpers import is_group, reply
from cocbot.bot.keyboards import main_menu
from cocbot.db import ChatSettings, Database

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message, chat_settings: ChatSettings | None, db: Database) -> None:
    if is_group(message):
        if chat_settings and chat_settings.clan_tag:
            await reply(message, "Что показать?", chat_settings, reply_markup=main_menu(True))
        else:
            await reply(message, texts.GROUP_WELCOME, chat_settings)
        return
    if message.from_user:
        # Только после /start в личке Telegram разрешает боту писать человеку первым.
        await db.mark_user_started(message.from_user.id)
    await message.answer(texts.HELP_PRIVATE, reply_markup=main_menu(False))


@router.message(Command("help"))
async def cmd_help(message: Message, chat_settings: ChatSettings | None) -> None:
    text = texts.HELP_GROUP if is_group(message) else texts.HELP_PRIVATE + "\n\n" + texts.HELP_GROUP
    await reply(message, text, chat_settings)


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def on_added_to_group(event: ChatMemberUpdated, db: Database) -> None:
    if event.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    await db.ensure_chat(event.chat.id)
    await event.bot.send_message(event.chat.id, texts.GROUP_WELCOME)


# Отдельный роутер подключается последним: сюда попадает только то,
# что не обработали остальные.
fallback_router = Router(name="fallback")


@fallback_router.message(F.chat.type == ChatType.PRIVATE)
async def private_fallback(message: Message) -> None:
    await message.answer("Не знаю такой команды. Нажми /menu или /help.")
