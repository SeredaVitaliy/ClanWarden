"""Сборка приложения: зависимости, роутеры, фоновые задачи."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats

from cocbot.bot.handlers import accounts, admin, common, war
from cocbot.bot.middlewares import ChatContextMiddleware
from cocbot.coc.client import CocClient
from cocbot.config import Settings
from cocbot.db import Database
from cocbot.services.notifier import Notifier
from cocbot.services.wars import WarService

log = logging.getLogger(__name__)

PRIVATE_COMMANDS = [
    BotCommand(command="menu", description="Меню"),
    BotCommand(command="me", description="Мои аккаунты и атаки"),
    BotCommand(command="war", description="Текущая война"),
    BotCommand(command="missed", description="Кто не атаковал"),
    BotCommand(command="cwl", description="Лига войн кланов"),
    BotCommand(command="link", description="Привязать аккаунт: /link #ТЕГ"),
    BotCommand(command="unlink", description="Отвязать аккаунт"),
    BotCommand(command="notify", description="Личные напоминания вкл/выкл"),
    BotCommand(command="help", description="Помощь"),
]

GROUP_COMMANDS = [
    BotCommand(command="war", description="Текущая война"),
    BotCommand(command="missed", description="Кто не атаковал"),
    BotCommand(command="cwl", description="Раунд ЛВК"),
    BotCommand(command="cwltable", description="Таблица ЛВК"),
    BotCommand(command="me", description="Мои аккаунты и атаки"),
    BotCommand(command="link", description="Привязать аккаунт: /link #ТЕГ"),
    BotCommand(command="menu", description="Меню"),
    BotCommand(command="settings", description="Настройки (админы)"),
    BotCommand(command="help", description="Помощь"),
]


def build_dispatcher(db: Database, coc: CocClient, wars: WarService) -> Dispatcher:
    # Зависимости кладём в dispatcher — aiogram передаст их в хендлеры по имени
    # аргумента (db, coc, wars). Без глобальных переменных, как было раньше.
    dp = Dispatcher(db=db, coc=coc, wars=wars)
    middleware = ChatContextMiddleware()
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)
    dp.include_routers(common.router, war.router, accounts.router, admin.router, common.fallback_router)
    return dp


async def bootstrap_chat(db: Database, settings: Settings) -> None:
    """Совместимость со старой версией: группа и клан из .env."""
    if settings.bootstrap_chat_id and settings.bootstrap_clan_tag:
        chat = await db.get_chat(settings.bootstrap_chat_id)
        if not chat or not chat.clan_tag:
            await db.set_chat_clan(settings.bootstrap_chat_id, settings.bootstrap_clan_tag)
            if settings.bootstrap_thread_id:
                await db.set_chat_thread(settings.bootstrap_chat_id, settings.bootstrap_thread_id)
            log.info(
                "Группа %s привязана к клану %s из переменных окружения",
                settings.bootstrap_chat_id,
                settings.bootstrap_clan_tag,
            )


async def run(settings: Settings) -> None:
    db = Database(settings.database_path)
    await db.connect()
    await bootstrap_chat(db, settings)

    coc = CocClient(settings.coc_token, settings.coc_base_url)
    wars = WarService(coc)
    bot = Bot(settings.telegram_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher(db, coc, wars)

    me = await bot.get_me()
    log.info("Запущен как @%s", me.username)
    await bot.set_my_commands(PRIVATE_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(GROUP_COMMANDS, scope=BotCommandScopeAllGroupChats())

    notifier = Notifier(bot, db, wars, settings.poll_interval)
    notifier_task = asyncio.create_task(notifier.run(), name="notifier")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        notifier_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await notifier_task
        await coc.close()
        await bot.session.close()
        await db.close()
