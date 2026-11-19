"""Настройка группы админами: /setclan, /settopic, /settings, /setrules, /checklinks."""

from __future__ import annotations

import contextlib

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from cocbot import texts
from cocbot.bot.helpers import api_error_text, is_admin, is_group, reply
from cocbot.bot.keyboards import (
    AUTODELETE_CYCLE,
    REMIND_HOURS_CYCLE,
    SettingsCb,
    next_in_cycle,
    settings_menu,
)
from cocbot.coc.client import CocApiError, CocClient
from cocbot.coc.tags import normalize_tag
from cocbot.db import CHAT_TOGGLES, ChatSettings, Database
from cocbot.texts import e

router = Router(name="admin")

MAX_RULES_LENGTH = 1000


async def ensure_admin(message: Message, chat_settings: ChatSettings | None) -> bool:
    """Команда работает только в группе и только для админов. Иначе — объясняем почему."""
    if not is_group(message):
        await message.answer("Эта команда работает в группе клана.")
        return False
    if not await is_admin(message.bot, message, message.from_user):
        await reply(message, "Эта команда доступна только админам группы.", chat_settings)
        return False
    return True


@router.message(Command("setclan"))
async def cmd_setclan(
    message: Message,
    command: CommandObject,
    chat_settings: ChatSettings | None,
    db: Database,
    coc: CocClient,
) -> None:
    if not await ensure_admin(message, chat_settings):
        return
    tag = normalize_tag((command.args or "").split()[0]) if command.args else None
    if not tag:
        await reply(message, "Использование: <code>/setclan #ТЕГ_КЛАНА</code>", chat_settings)
        return
    try:
        clan = await coc.get_clan(tag)
    except CocApiError as exc:
        await reply(message, api_error_text(exc), chat_settings)
        return

    await db.set_chat_clan(message.chat.id, clan.tag)
    text = (
        f"✅ Группа привязана к клану <b>{e(clan.name)}</b> <code>{e(clan.tag)}</code> "
        f"({len(clan.members)} игроков).\n\n"
        "Буду присылать сюда старт войны, напоминание и итоги. Настроить: /settings\n"
        "Игрокам — привязать свои аккаунты: <code>/link #ТЕГ</code>"
    )
    if not clan.war_log_public:
        text += "\n\n⚠️ Журнал войн клана закрыт — так я не увижу войну. Откройте его в настройках клана."
    await reply(message, text, chat_settings)


@router.message(Command("settopic"))
async def cmd_settopic(message: Message, chat_settings: ChatSettings | None, db: Database) -> None:
    if not await ensure_admin(message, chat_settings):
        return
    if not message.message_thread_id or not message.is_topic_message:
        await reply(
            message, "Отправьте эту команду внутри темы, в которой должен работать бот.", chat_settings
        )
        return
    await db.set_chat_thread(message.chat.id, message.message_thread_id)
    await reply(message, "✅ Теперь я отвечаю и присылаю уведомления только в этой теме.", chat_settings)


@router.message(Command("unsettopic"))
async def cmd_unsettopic(message: Message, chat_settings: ChatSettings | None, db: Database) -> None:
    if not await ensure_admin(message, chat_settings):
        return
    await db.set_chat_thread(message.chat.id, None)
    await reply(message, "✅ Теперь я работаю во всём чате.", chat_settings)


@router.message(Command("setrules"))
async def cmd_setrules(
    message: Message, command: CommandObject, chat_settings: ChatSettings | None, db: Database
) -> None:
    if not await ensure_admin(message, chat_settings):
        return
    rules = (command.args or "").strip()
    if not rules:
        await db.set_chat_rules(message.chat.id, None)
        await reply(
            message,
            "Правила очищены.\nЗадать: <code>/setrules Первая атака — зеркало…</code> "
            "(можно в несколько строк)",
            chat_settings,
        )
        return
    if len(rules) > MAX_RULES_LENGTH:
        await reply(message, f"Слишком длинно — максимум {MAX_RULES_LENGTH} символов.", chat_settings)
        return
    await db.set_chat_rules(message.chat.id, rules)
    await reply(message, f"✅ Правила сохранены, покажу их в начале войны:\n\n{e(rules)}", chat_settings)


@router.message(Command("settings"))
async def cmd_settings(
    message: Message, chat_settings: ChatSettings | None, db: Database, coc: CocClient
) -> None:
    if not await ensure_admin(message, chat_settings):
        return
    chat = await db.ensure_chat(message.chat.id)
    clan_name = None
    if chat.clan_tag:
        with contextlib.suppress(CocApiError):
            clan_name = (await coc.get_clan(chat.clan_tag)).name
    await reply(
        message, texts.settings_text(chat, clan_name), chat_settings, reply_markup=settings_menu(chat)
    )


@router.callback_query(SettingsCb.filter())
async def on_settings(query: CallbackQuery, callback_data: SettingsCb, db: Database, coc: CocClient) -> None:
    message = query.message
    if not isinstance(message, Message):
        await query.answer()
        return
    chat_id = message.chat.id
    if not await is_admin(message.bot, chat_id, query.from_user):
        await query.answer("Настройки доступны только админам группы", show_alert=True)
        return

    chat = await db.ensure_chat(chat_id)
    action = callback_data.action
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
    clan_name = None
    if chat.clan_tag:
        with contextlib.suppress(CocApiError):
            clan_name = (await coc.get_clan(chat.clan_tag)).name
    with contextlib.suppress(TelegramBadRequest):
        await message.edit_text(texts.settings_text(chat, clan_name), reply_markup=settings_menu(chat))
    await query.answer()


@router.message(Command("checklinks"))
async def cmd_checklinks(
    message: Message, chat_settings: ChatSettings | None, db: Database, coc: CocClient
) -> None:
    if not await ensure_admin(message, chat_settings):
        return
    if not chat_settings or not chat_settings.clan_tag:
        await reply(message, "Сначала привяжите клан: /setclan #ТЕГ", chat_settings)
        return
    try:
        clan = await coc.get_clan(chat_settings.clan_tag)
    except CocApiError as exc:
        await reply(message, api_error_text(exc), chat_settings)
        return

    links = await db.links_for_tags([m.tag for m in clan.members])
    missing = [m for m in clan.members if m.tag not in links]
    lines = [
        f"🔗 <b>Привязки клана {e(clan.name)}</b>",
        f"Привязано: {len(links)} из {len(clan.members)}",
    ]
    if missing:
        lines.append("\nБез привязки:")
        lines += [f"• {e(m.name)} <code>{e(m.tag)}</code>" for m in missing]
        lines.append("\nКаждый может привязаться сам: <code>/link #ТЕГ</code>")
    else:
        lines.append("\n🎉 Все игроки привязали аккаунты.")
    await reply(message, "\n".join(lines), chat_settings)
