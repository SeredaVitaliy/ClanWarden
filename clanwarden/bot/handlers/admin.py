"""Group setup for admins: /setclan, /settopic, /settings, /setrules, /checklinks."""

from __future__ import annotations

import contextlib

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from clanwarden import texts
from clanwarden.bot.handlers.war import clan_name
from clanwarden.bot.helpers import api_error_key, is_admin, is_group, reply
from clanwarden.bot.keyboards import (
    AUTODELETE_CYCLE,
    REMIND_HOURS_CYCLE,
    SettingsCb,
    language_menu,
    next_in_cycle,
    settings_menu,
)
from clanwarden.coc.client import CocApiError, CocClient
from clanwarden.coc.tags import normalize_tag
from clanwarden.db import CHAT_TOGGLES, ChatSettings, Database
from clanwarden.i18n import Translator, normalize_language
from clanwarden.texts import e

router = Router(name="admin")

MAX_RULES_LENGTH = 1000


async def ensure_admin(message: Message, t: Translator, chat_settings: ChatSettings | None) -> bool:
    """Admin commands work only in groups and only for admins. Otherwise explain why."""
    if not is_group(message):
        await message.answer(t("group_only"))
        return False
    if not await is_admin(message.bot, message, message.from_user):
        await reply(message, t("admins_only"), chat_settings)
        return False
    return True


@router.message(Command("setclan"))
async def cmd_setclan(
    message: Message,
    command: CommandObject,
    t: Translator,
    chat_settings: ChatSettings | None,
    db: Database,
    coc: CocClient,
) -> None:
    if not await ensure_admin(message, t, chat_settings):
        return
    tag = normalize_tag(command.args.split()[0]) if command.args else None
    if not tag:
        await reply(message, t("setclan_usage"), chat_settings)
        return
    try:
        clan = await coc.get_clan(tag)
    except CocApiError as exc:
        await reply(message, t(api_error_key(exc)), chat_settings)
        return

    await db.set_chat_clan(message.chat.id, clan.tag)
    # First-time setup: pick up the admin's Telegram language as the group's language.
    admin_language = normalize_language(message.from_user.language_code) if message.from_user else None
    if chat_settings and not chat_settings.language and admin_language:
        await db.set_chat_language(message.chat.id, admin_language)
        t = Translator(admin_language)

    text = t("setclan_done", name=e(clan.name), tag=e(clan.tag), members=len(clan.members))
    if not clan.war_log_public:
        text += t("setclan_private_log")
    await reply(message, text, chat_settings)


@router.message(Command("settopic"))
async def cmd_settopic(
    message: Message, t: Translator, chat_settings: ChatSettings | None, db: Database
) -> None:
    if not await ensure_admin(message, t, chat_settings):
        return
    if not message.message_thread_id or not message.is_topic_message:
        await reply(message, t("settopic_need_topic"), chat_settings)
        return
    await db.set_chat_thread(message.chat.id, message.message_thread_id)
    await reply(message, t("settopic_done"), chat_settings)


@router.message(Command("unsettopic"))
async def cmd_unsettopic(
    message: Message, t: Translator, chat_settings: ChatSettings | None, db: Database
) -> None:
    if not await ensure_admin(message, t, chat_settings):
        return
    await db.set_chat_thread(message.chat.id, None)
    await reply(message, t("unsettopic_done"), chat_settings)


@router.message(Command("setrules"))
async def cmd_setrules(
    message: Message, command: CommandObject, t: Translator, chat_settings: ChatSettings | None, db: Database
) -> None:
    if not await ensure_admin(message, t, chat_settings):
        return
    rules = (command.args or "").strip()
    if not rules:
        await db.set_chat_rules(message.chat.id, None)
        await reply(message, t("rules_cleared"), chat_settings)
        return
    if len(rules) > MAX_RULES_LENGTH:
        await reply(message, t("rules_too_long", n=MAX_RULES_LENGTH), chat_settings)
        return
    await db.set_chat_rules(message.chat.id, rules)
    await reply(message, t("rules_saved", rules=e(rules)), chat_settings)


@router.message(Command("settings"))
async def cmd_settings(
    message: Message, t: Translator, chat_settings: ChatSettings | None, db: Database, coc: CocClient
) -> None:
    if not await ensure_admin(message, t, chat_settings):
        return
    chat = await db.ensure_chat(message.chat.id)
    text = texts.settings_text(t, chat, await clan_name(coc, chat))
    await reply(message, text, chat_settings, reply_markup=settings_menu(t, chat))


@router.callback_query(SettingsCb.filter())
async def on_settings(
    query: CallbackQuery, callback_data: SettingsCb, t: Translator, db: Database, coc: CocClient
) -> None:
    message = query.message
    if not isinstance(message, Message):
        await query.answer()
        return
    chat_id = message.chat.id
    if not await is_admin(message.bot, chat_id, query.from_user):
        await query.answer(t("settings_admins_only"), show_alert=True)
        return

    action = callback_data.action
    if action == "language":
        with contextlib.suppress(TelegramBadRequest):
            await message.edit_text(t("language_choose"), reply_markup=language_menu())
        await query.answer()
        return

    chat = await db.ensure_chat(chat_id)
    if action in CHAT_TOGGLES:
        await db.toggle_chat_flag(chat_id, action)
    elif action == "remind_hours":
        await db.set_chat_number(
            chat_id, "remind_hours", next_in_cycle(REMIND_HOURS_CYCLE, chat.remind_hours)
        )
    elif action == "autodelete":
        await db.set_chat_number(
            chat_id, "autodelete_min", next_in_cycle(AUTODELETE_CYCLE, chat.autodelete_min)
        )

    chat = await db.ensure_chat(chat_id)
    with contextlib.suppress(TelegramBadRequest):
        await message.edit_text(
            texts.settings_text(t, chat, await clan_name(coc, chat)), reply_markup=settings_menu(t, chat)
        )
    await query.answer()


@router.message(Command("checklinks"))
async def cmd_checklinks(
    message: Message, t: Translator, chat_settings: ChatSettings | None, db: Database, coc: CocClient
) -> None:
    if not await ensure_admin(message, t, chat_settings):
        return
    if not chat_settings or not chat_settings.clan_tag:
        await reply(message, t("checklinks_need_clan"), chat_settings)
        return
    try:
        clan = await coc.get_clan(chat_settings.clan_tag)
    except CocApiError as exc:
        await reply(message, t(api_error_key(exc)), chat_settings)
        return

    links = await db.links_for_tags([m.tag for m in clan.members])
    missing = [m for m in clan.members if m.tag not in links]
    lines = [
        t("checklinks_title", clan=e(clan.name)),
        t("checklinks_count", linked=len(links), total=len(clan.members)),
    ]
    if missing:
        lines.append(t("checklinks_missing"))
        lines += [f"• {e(m.name)} <code>{e(m.tag)}</code>" for m in missing]
        lines.append(t("checklinks_hint"))
    else:
        lines.append(t("checklinks_all"))
    await reply(message, "\n".join(lines), chat_settings)
