"""Linking game accounts to Telegram: /link, /unlink, /notify.

A link lets the bot mention a player in reminders and message them privately.
So that nobody can "claim" someone else's tag, there are two levels:
- without a token — you can link a tag nobody has linked yet;
- with the API token from the game settings — the link is verified, and such
  a link can take a tag over from another user (it proves the account is yours).
"""

from __future__ import annotations

import contextlib

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from clanwarden.bot.helpers import api_error_key, is_group, reply
from clanwarden.bot.keyboards import UnlinkCb, unlink_menu
from clanwarden.coc.client import CocApiError, CocClient, NotFound
from clanwarden.coc.tags import normalize_tag
from clanwarden.db import ChatSettings, Database
from clanwarden.i18n import Translator
from clanwarden.texts import e

router = Router(name="accounts")

MAX_LINKS_PER_USER = 10


@router.message(Command("link"))
async def cmd_link(
    message: Message,
    command: CommandObject,
    t: Translator,
    chat_settings: ChatSettings | None,
    db: Database,
    coc: CocClient,
) -> None:
    user = message.from_user
    if not user:
        return
    parts = (command.args or "").split()
    if not parts:
        await reply(message, t("link_usage"), chat_settings)
        return

    tag = normalize_tag(parts[0])
    if not tag:
        await reply(message, t("link_bad_tag"), chat_settings)
        return
    token = parts[1] if len(parts) > 1 else None

    if token and is_group(message):
        # The token is single-use, but it still shouldn't sit in a group chat.
        with contextlib.suppress(TelegramAPIError):
            await message.delete()

    try:
        player = await coc.get_player(tag)
    except NotFound:
        await reply(message, t("player_not_found", tag=e(tag)), chat_settings)
        return
    except CocApiError as exc:
        await reply(message, t(api_error_key(exc)), chat_settings)
        return

    verified = False
    if token:
        try:
            verified = await coc.verify_player_token(tag, token)
        except CocApiError as exc:
            await reply(message, t(api_error_key(exc)), chat_settings)
            return
        if not verified:
            await reply(message, t("token_invalid"), chat_settings)
            return

    existing = await db.get_link(tag)
    if existing and existing.telegram_id != user.id and not verified:
        await reply(message, t("link_taken", name=e(player.name)), chat_settings)
        return
    if existing and existing.telegram_id == user.id and existing.verified:
        verified = True  # re-linking shouldn't lose the verification

    is_new_for_user = not existing or existing.telegram_id != user.id
    if is_new_for_user and len(await db.user_links(user.id)) >= MAX_LINKS_PER_USER:
        await reply(message, t("link_limit", n=MAX_LINKS_PER_USER), chat_settings)
        return

    await db.save_link(tag, user.id, player.name, verified)
    text = t(
        "link_done",
        name=e(player.name),
        th=player.townhall,
        clan=t("link_from_clan", clan=e(player.clan.name)) if player.clan else "",
        status=t("link_status_verified" if verified else "link_status_linked"),
    )
    if is_group(message):
        text += t("link_dm_hint")
    await reply(message, text, chat_settings)


@router.message(Command("unlink"))
async def cmd_unlink(
    message: Message, command: CommandObject, t: Translator, chat_settings: ChatSettings | None, db: Database
) -> None:
    user = message.from_user
    if not user:
        return
    if command.args:
        tag = normalize_tag(command.args.split()[0])
        removed = bool(tag) and await db.delete_link(tag, user.id)
        text = t("unlink_done", tag=e(tag)) if removed else t("unlink_not_yours")
        await reply(message, text, chat_settings)
        return

    links = await db.user_links(user.id)
    if not links:
        await reply(message, t("no_links"), chat_settings)
        return
    options = [(link.player_tag, link.player_name or link.player_tag) for link in links]
    await reply(message, t("unlink_choose"), chat_settings, reply_markup=unlink_menu(t, options))


@router.callback_query(UnlinkCb.filter())
async def on_unlink(query: CallbackQuery, callback_data: UnlinkCb, t: Translator, db: Database) -> None:
    # Only your own link can be removed: anyone in the group could press the button.
    if not await db.delete_link(callback_data.tag, query.from_user.id):
        await query.answer(t("not_your_account"), show_alert=True)
        return
    await query.answer(t("unlinked_toast"))
    if isinstance(query.message, Message):
        with contextlib.suppress(TelegramAPIError):
            await query.message.edit_text(t("unlink_done", tag=e(callback_data.tag)))


@router.message(Command("notify"))
async def cmd_notify(
    message: Message, t: Translator, chat_settings: ChatSettings | None, db: Database
) -> None:
    user = message.from_user
    if not user:
        return
    if await db.toggle_dm_reminders(user.id):
        text = t("notify_on")
        if is_group(message):
            text += t("notify_on_group_hint")
    else:
        text = t("notify_off")
    await reply(message, text, chat_settings)
