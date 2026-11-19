"""Команды и кнопки про войну: /war, /missed, /cwl, /cwltable, /menu."""

from __future__ import annotations

import contextlib

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from cocbot import texts
from cocbot.bot import views
from cocbot.bot.helpers import UserFacingError, api_error_text, is_admin, is_group, reply, resolve_clan
from cocbot.bot.keyboards import MenuCb, back_button, main_menu, settings_menu
from cocbot.coc.client import CocApiError, CocClient
from cocbot.db import ChatSettings, Database
from cocbot.services.wars import WarService

router = Router(name="war")


async def _render(
    action: str,
    *,
    arg: str | None,
    chat: ChatSettings | None,
    user_id: int | None,
    db: Database,
    wars: WarService,
    coc: CocClient,
) -> str:
    try:
        if action == "me":
            return await views.view_me(wars, db, coc, user_id)
        clan_tag = await resolve_clan(arg=arg, chat=chat, user_id=user_id, db=db, client=coc)
        if action == "war":
            return await views.view_war(wars, clan_tag)
        if action == "missed":
            return await views.view_missed(wars, db, clan_tag, chat)
        if action == "cwl":
            return await views.view_cwl(wars, clan_tag)
        if action == "cwltable":
            return await views.view_cwl_table(wars, clan_tag)
    except UserFacingError as exc:
        return str(exc)
    except CocApiError as exc:
        return api_error_text(exc)
    raise ValueError(f"Неизвестное действие {action}")


@router.message(Command("war", "missed", "cwl", "cwltable", "me"))
async def cmd_war(
    message: Message,
    command: CommandObject,
    chat_settings: ChatSettings | None,
    db: Database,
    wars: WarService,
    coc: CocClient,
) -> None:
    action = command.command.lower()
    await message.bot.send_chat_action(message.chat.id, "typing", message_thread_id=message.message_thread_id)
    text = await _render(
        action,
        arg=command.args,
        chat=chat_settings,
        user_id=message.from_user.id if message.from_user else None,
        db=db,
        wars=wars,
        coc=coc,
    )
    await reply(message, text, chat_settings)


@router.message(Command("menu"))
async def cmd_menu(message: Message, chat_settings: ChatSettings | None) -> None:
    await reply(message, "Что показать?", chat_settings, reply_markup=main_menu(is_group(message)))


@router.callback_query(MenuCb.filter())
async def on_menu(
    query: CallbackQuery,
    callback_data: MenuCb,
    chat_settings: ChatSettings | None,
    db: Database,
    wars: WarService,
    coc: CocClient,
) -> None:
    message = query.message
    if not isinstance(message, Message):
        await query.answer("Меню устарело, вызовите /menu", show_alert=True)
        return
    action = callback_data.action
    group = is_group(message)

    if action == "main":
        text, markup = "Что показать?", main_menu(group)
    elif action == "help":
        text, markup = (texts.HELP_GROUP if group else texts.HELP_PRIVATE), back_button()
    elif action == "settings":
        if not group or not chat_settings:
            await query.answer()
            return
        if not await is_admin(message.bot, message.chat.id, query.from_user):
            await query.answer("Настройки доступны только админам группы", show_alert=True)
            return
        clan_name = None
        if chat_settings.clan_tag:
            with contextlib.suppress(CocApiError):
                clan_name = (await coc.get_clan(chat_settings.clan_tag)).name
        text, markup = texts.settings_text(chat_settings, clan_name), settings_menu(chat_settings)
    else:
        await query.answer("Загружаю…")
        text = await _render(
            action, arg=None, chat=chat_settings, user_id=query.from_user.id, db=db, wars=wars, coc=coc
        )
        markup = back_button(refresh_action=action)

    with contextlib.suppress(TelegramBadRequest):  # "message is not modified" при «Обновить» без изменений
        await message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
    with contextlib.suppress(TelegramBadRequest):
        await query.answer()
