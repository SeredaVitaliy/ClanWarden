"""War commands and menu buttons: /war, /missed, /cwl, /cwltable, /me, /menu."""

from __future__ import annotations

import contextlib

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from clanwarden import texts
from clanwarden.bot import views
from clanwarden.bot.helpers import UserFacingError, api_error_key, is_admin, is_group, reply, resolve_clan
from clanwarden.bot.keyboards import MenuCb, back_button, main_menu, settings_menu
from clanwarden.coc.client import CocApiError, CocClient
from clanwarden.coc.tags import normalize_tag
from clanwarden.db import ChatSettings, Database
from clanwarden.i18n import Translator
from clanwarden.services.wars import WarService

router = Router(name="war")


async def render(
    action: str,
    t: Translator,
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
            return await views.view_me(t, wars, db, coc, user_id)
        if action == "stats":
            return await _render_stats(t, arg, chat=chat, user_id=user_id, db=db, coc=coc)
        clan_tag = await resolve_clan(arg=arg, chat=chat, user_id=user_id, db=db, client=coc)
        if action == "war":
            return await views.view_war(t, wars, clan_tag)
        if action == "missed":
            return await views.view_missed(t, wars, db, clan_tag)
        if action == "cwl":
            return await views.view_cwl(t, wars, clan_tag)
        if action == "cwltable":
            return await views.view_cwl_table(t, wars, clan_tag)
    except UserFacingError as exc:
        return t(exc.key)
    except CocApiError as exc:
        return t(api_error_key(exc))
    raise ValueError(f"Unknown action {action}")


async def _render_stats(
    t: Translator,
    arg: str | None,
    *,
    chat: ChatSettings | None,
    user_id: int | None,
    db: Database,
    coc: CocClient,
) -> str:
    """`/stats [N] [cwl]` for the clan, `/stats #TAG` for one player.

    Numbers are checked first: "200" is also a syntactically valid tag.
    """
    args = (arg or "").split()
    for word in args:
        if not word.isdigit() and word.lower() != "cwl" and (tag := normalize_tag(word)):
            return await views.view_player_stats(t, db, tag)
    clan_tag = await resolve_clan(arg=None, chat=chat, user_id=user_id, db=db, client=coc)
    return await views.view_stats(t, db, coc, clan_tag, args)


async def clan_name(coc: CocClient, chat: ChatSettings) -> str | None:
    if not chat.clan_tag:
        return None
    with contextlib.suppress(CocApiError):
        return (await coc.get_clan(chat.clan_tag)).name
    return None


@router.message(Command("war", "missed", "cwl", "cwltable", "me", "stats"))
async def cmd_war(
    message: Message,
    command: CommandObject,
    t: Translator,
    chat_settings: ChatSettings | None,
    db: Database,
    wars: WarService,
    coc: CocClient,
) -> None:
    await message.bot.send_chat_action(message.chat.id, "typing", message_thread_id=message.message_thread_id)
    text = await render(
        command.command.lower(),
        t,
        arg=command.args,
        chat=chat_settings,
        user_id=message.from_user.id if message.from_user else None,
        db=db,
        wars=wars,
        coc=coc,
    )
    await reply(message, text, chat_settings)


@router.message(Command("menu"))
async def cmd_menu(message: Message, t: Translator, chat_settings: ChatSettings | None) -> None:
    await reply(message, t("menu_prompt"), chat_settings, reply_markup=main_menu(t, is_group(message)))


@router.callback_query(MenuCb.filter())
async def on_menu(
    query: CallbackQuery,
    callback_data: MenuCb,
    t: Translator,
    chat_settings: ChatSettings | None,
    db: Database,
    wars: WarService,
    coc: CocClient,
) -> None:
    message = query.message
    if not isinstance(message, Message):
        await query.answer(t("menu_outdated"), show_alert=True)
        return
    action = callback_data.action
    group = is_group(message)

    if action == "main":
        text, markup = t("menu_prompt"), main_menu(t, group)
    elif action == "help":
        text, markup = t("help_group" if group else "help_private"), back_button(t)
    elif action == "settings":
        if not group or not chat_settings:
            await query.answer()
            return
        if not await is_admin(message.bot, message.chat.id, query.from_user):
            await query.answer(t("settings_admins_only"), show_alert=True)
            return
        text = texts.settings_text(t, chat_settings, await clan_name(coc, chat_settings))
        markup = settings_menu(t, chat_settings)
    else:
        await query.answer(t("loading"))
        text = await render(
            action, t, arg=None, chat=chat_settings, user_id=query.from_user.id, db=db, wars=wars, coc=coc
        )
        markup = back_button(t, refresh_action=action)

    # "message is not modified" when Refresh changes nothing — that's fine.
    with contextlib.suppress(TelegramBadRequest):
        await message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
    with contextlib.suppress(TelegramBadRequest):
        await query.answer()
