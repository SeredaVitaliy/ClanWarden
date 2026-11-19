from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from cocbot.db import ChatSettings


class MenuCb(CallbackData, prefix="m"):
    action: str


class SettingsCb(CallbackData, prefix="s"):
    action: str


class UnlinkCb(CallbackData, prefix="u"):
    tag: str


REMIND_HOURS_CYCLE = (1, 2, 3, 4, 6, 8, 12)
AUTODELETE_CYCLE = (0, 5, 15, 60)


def next_in_cycle(cycle: tuple[int, ...], current: int) -> int:
    for value in cycle:
        if value > current:
            return value
    return cycle[0]


def main_menu(is_group: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⚔️ Война", callback_data=MenuCb(action="war"))
    kb.button(text="❗ Кто не атаковал", callback_data=MenuCb(action="missed"))
    kb.button(text="🏆 ЛВК", callback_data=MenuCb(action="cwl"))
    kb.button(text="📊 Таблица ЛВК", callback_data=MenuCb(action="cwltable"))
    kb.button(text="👤 Мои аккаунты", callback_data=MenuCb(action="me"))
    if is_group:
        kb.button(text="⚙️ Настройки", callback_data=MenuCb(action="settings"))
    kb.button(text="❓ Помощь", callback_data=MenuCb(action="help"))
    kb.adjust(2)
    return kb.as_markup()


def back_button(refresh_action: str | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if refresh_action:
        kb.button(text="🔄 Обновить", callback_data=MenuCb(action=refresh_action))
    kb.button(text="« Меню", callback_data=MenuCb(action="main"))
    kb.adjust(2)
    return kb.as_markup()


def settings_menu(chat: ChatSettings) -> InlineKeyboardMarkup:
    def mark(on: bool) -> str:
        return "✅" if on else "❌"

    rows = [
        [
            InlineKeyboardButton(
                text=f"{mark(chat.notify_prep)} Соперник найден",
                callback_data=SettingsCb(action="notify_prep").pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{mark(chat.notify_start)} Начало войны",
                callback_data=SettingsCb(action="notify_start").pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{mark(chat.notify_remind)} Напоминание",
                callback_data=SettingsCb(action="notify_remind").pack(),
            ),
            InlineKeyboardButton(
                text=f"⏰ за {chat.remind_hours} ч", callback_data=SettingsCb(action="remind_hours").pack()
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"{mark(chat.notify_end)} Итоги войны",
                callback_data=SettingsCb(action="notify_end").pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{mark(chat.mention_players)} Упоминания игроков",
                callback_data=SettingsCb(action="mention_players").pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=f"🧹 Автоудаление: {f'{chat.autodelete_min} мин' if chat.autodelete_min else 'выкл'}",
                callback_data=SettingsCb(action="autodelete").pack(),
            )
        ],
        [InlineKeyboardButton(text="« Меню", callback_data=MenuCb(action="main").pack())],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def unlink_menu(tags_with_names: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for tag, name in tags_with_names:
        kb.button(text=f"❌ {name} ({tag})", callback_data=UnlinkCb(tag=tag))
    kb.adjust(1)
    return kb.as_markup()
