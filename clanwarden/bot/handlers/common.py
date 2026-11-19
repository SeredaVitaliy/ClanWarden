"""/start, /help, /language and the greeting when the bot is added to a group."""

from __future__ import annotations

import contextlib

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import JOIN_TRANSITION, ChatMemberUpdatedFilter, Command, CommandStart
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message

from clanwarden.bot.helpers import is_admin, is_group, reply
from clanwarden.bot.keyboards import LanguageCb, language_menu, main_menu
from clanwarden.db import ChatSettings, Database
from clanwarden.i18n import CATALOGS, LANGUAGE_NAMES, Translator, normalize_language

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(
    message: Message, t: Translator, chat_settings: ChatSettings | None, db: Database
) -> None:
    if is_group(message):
        if chat_settings and chat_settings.clan_tag:
            await reply(message, t("menu_prompt"), chat_settings, reply_markup=main_menu(t, True))
        else:
            await reply(message, t("group_welcome"), chat_settings)
        return
    if message.from_user:
        # Telegram only lets a bot message a user first after they pressed /start.
        language = normalize_language(message.from_user.language_code)
        await db.mark_user_started(message.from_user.id, language)
    await message.answer(t("help_private"), reply_markup=main_menu(t, False))


@router.message(Command("help"))
async def cmd_help(message: Message, t: Translator, chat_settings: ChatSettings | None) -> None:
    text = t("help_group") if is_group(message) else t("help_private") + "\n\n" + t("help_group")
    await reply(message, text, chat_settings)


@router.message(Command("language"))
async def cmd_language(message: Message, t: Translator, chat_settings: ChatSettings | None) -> None:
    if is_group(message) and not await is_admin(message.bot, message, message.from_user):
        await reply(message, t("admins_only"), chat_settings)
        return
    await reply(message, t("language_choose"), chat_settings, reply_markup=language_menu())


@router.callback_query(LanguageCb.filter())
async def on_language(query: CallbackQuery, callback_data: LanguageCb, db: Database) -> None:
    message = query.message
    code = callback_data.code
    if code not in CATALOGS or not isinstance(message, Message):
        await query.answer()
        return

    if is_group(message):
        if not await is_admin(message.bot, message.chat.id, query.from_user):
            await query.answer(Translator(code)("settings_admins_only"), show_alert=True)
            return
        await db.set_chat_language(message.chat.id, code)
    else:
        await db.set_user_language(query.from_user.id, code)

    t = Translator(code)
    with contextlib.suppress(TelegramBadRequest):
        await message.edit_text(t("language_set", name=LANGUAGE_NAMES[code]))
    await query.answer()


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def on_added_to_group(event: ChatMemberUpdated, db: Database) -> None:
    if event.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    # Greet in the language of whoever added the bot, and remember it for the group.
    language = normalize_language(event.from_user.language_code if event.from_user else None)
    chat = await db.ensure_chat(event.chat.id)
    if language and not chat.language:
        await db.set_chat_language(event.chat.id, language)
    await event.bot.send_message(event.chat.id, Translator(chat.language or language)("group_welcome"))


# A separate router included last: only updates nobody else handled end up here.
fallback_router = Router(name="fallback")


@fallback_router.message(F.chat.type == ChatType.PRIVATE)
async def private_fallback(message: Message, t: Translator) -> None:
    await message.answer(t("private_fallback"))
