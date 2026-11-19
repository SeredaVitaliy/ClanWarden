"""Привязка игровых аккаунтов к Telegram: /link, /unlink, /notify.

Привязка нужна, чтобы бот мог упомянуть человека в напоминании и написать
ему в личку. Чтобы нельзя было «занять» чужой тег, есть два уровня:
- без токена — можно привязать свободный тег;
- с API-токеном из настроек игры — привязка подтверждена, и такой тег
  можно забрать у другого человека (значит, аккаунт действительно твой).
"""

from __future__ import annotations

import contextlib

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from cocbot.bot.helpers import api_error_text, is_group, reply
from cocbot.bot.keyboards import UnlinkCb, unlink_menu
from cocbot.coc.client import CocApiError, CocClient, NotFound
from cocbot.coc.tags import normalize_tag
from cocbot.db import ChatSettings, Database
from cocbot.texts import e

router = Router(name="accounts")

MAX_LINKS_PER_USER = 10

LINK_USAGE = (
    "Использование: <code>/link #ТЕГ</code>\n"
    "Тег — в профиле игрока под ником.\n\n"
    "Чтобы подтвердить, что аккаунт твой: <code>/link #ТЕГ ТОКЕН</code>, "
    "токен — в игре: Настройки → Ещё настройки → API-токен. "
    "Лучше присылать токен мне в личку."
)


@router.message(Command("link"))
async def cmd_link(
    message: Message,
    command: CommandObject,
    chat_settings: ChatSettings | None,
    db: Database,
    coc: CocClient,
) -> None:
    user = message.from_user
    if not user:
        return
    parts = (command.args or "").split()
    if not parts:
        await reply(message, LINK_USAGE, chat_settings)
        return

    tag = normalize_tag(parts[0])
    if not tag:
        await reply(
            message, "Тег выглядит неправильно. Он состоит из символов 0289PYLQGRJCUV.", chat_settings
        )
        return
    token = parts[1] if len(parts) > 1 else None

    if token and is_group(message):
        # Токен одноразовый, но светить его в общем чате всё равно не стоит.
        with contextlib.suppress(TelegramAPIError):
            await message.delete()

    try:
        player = await coc.get_player(tag)
    except NotFound:
        await reply(message, f"Игрок <code>{e(tag)}</code> не найден.", chat_settings)
        return
    except CocApiError as exc:
        await reply(message, api_error_text(exc), chat_settings)
        return

    verified = False
    if token:
        try:
            verified = await coc.verify_player_token(tag, token)
        except CocApiError as exc:
            await reply(message, api_error_text(exc), chat_settings)
            return
        if not verified:
            await reply(
                message,
                "❌ Токен не подошёл. Он действует несколько минут — возьмите новый в игре.",
                chat_settings,
            )
            return

    existing = await db.get_link(tag)
    if existing and existing.telegram_id != user.id and not verified:
        await reply(
            message,
            f"Аккаунт <b>{e(player.name)}</b> уже привязан другим человеком.\n"
            "Если он твой — подтверди владение: <code>/link #ТЕГ ТОКЕН</code> (в личке).",
            chat_settings,
        )
        return
    if existing and existing.telegram_id == user.id and existing.verified:
        verified = True  # не теряем подтверждение при повторной привязке

    is_new_for_user = not existing or existing.telegram_id != user.id
    if is_new_for_user and len(await db.user_links(user.id)) >= MAX_LINKS_PER_USER:
        await reply(message, f"Можно привязать не больше {MAX_LINKS_PER_USER} аккаунтов.", chat_settings)
        return

    await db.save_link(tag, user.id, player.name, verified)
    status = "✅ подтверждён" if verified else "привязан"
    clan = f" из клана {e(player.clan.name)}" if player.clan else ""
    text = f"🔗 Аккаунт <b>{e(player.name)}</b> (ТХ{player.townhall}){clan} {status}."
    if is_group(message):
        text += "\n\nЧтобы получать личные напоминания, напиши мне /start в личку."
    await reply(message, text, chat_settings)


@router.message(Command("unlink"))
async def cmd_unlink(
    message: Message, command: CommandObject, chat_settings: ChatSettings | None, db: Database
) -> None:
    user = message.from_user
    if not user:
        return
    if command.args:
        tag = normalize_tag(command.args.split()[0])
        removed = bool(tag) and await db.delete_link(tag, user.id)
        text = f"🗑 Аккаунт <code>{e(tag)}</code> отвязан." if removed else "Этот тег не привязан к тебе."
        await reply(message, text, chat_settings)
        return

    links = await db.user_links(user.id)
    if not links:
        await reply(message, "У тебя нет привязанных аккаунтов.", chat_settings)
        return
    await reply(
        message,
        "Какой аккаунт отвязать?",
        chat_settings,
        reply_markup=unlink_menu([(link.player_tag, link.player_name or link.player_tag) for link in links]),
    )


@router.callback_query(UnlinkCb.filter())
async def on_unlink(query: CallbackQuery, callback_data: UnlinkCb, db: Database) -> None:
    # Удаляем только свою привязку: кнопку мог нажать другой участник группы.
    removed = await db.delete_link(callback_data.tag, query.from_user.id)
    if not removed:
        await query.answer("Это не твой аккаунт", show_alert=True)
        return
    await query.answer("Отвязано")
    if isinstance(query.message, Message):
        with contextlib.suppress(TelegramAPIError):
            await query.message.edit_text(f"🗑 Аккаунт <code>{e(callback_data.tag)}</code> отвязан.")


@router.message(Command("notify"))
async def cmd_notify(message: Message, chat_settings: ChatSettings | None, db: Database) -> None:
    user = message.from_user
    if not user:
        return
    enabled = await db.toggle_dm_reminders(user.id)
    if enabled:
        text = "🔔 Личные напоминания включены. Напишу, если у тебя останутся атаки перед концом войны."
        if is_group(message):
            text += "\nНе забудь написать мне /start в личку — иначе Telegram не даст мне написать первым."
    else:
        text = "🔕 Личные напоминания выключены."
    await reply(message, text, chat_settings)
