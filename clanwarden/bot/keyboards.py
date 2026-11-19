from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from clanwarden.db import ChatSettings
from clanwarden.i18n import LANGUAGE_NAMES, Translator


class MenuCb(CallbackData, prefix="m"):
    action: str


class SettingsCb(CallbackData, prefix="s"):
    action: str


class UnlinkCb(CallbackData, prefix="u"):
    tag: str


class LanguageCb(CallbackData, prefix="l"):
    code: str


REMIND_HOURS_CYCLE = (1, 2, 3, 4, 6, 8, 12)
AUTODELETE_CYCLE = (0, 5, 15, 60)


def next_in_cycle(cycle: tuple[int, ...], current: int) -> int:
    for value in cycle:
        if value > current:
            return value
    return cycle[0]


def main_menu(t: Translator, is_group: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t("btn_war"), callback_data=MenuCb(action="war"))
    kb.button(text=t("btn_missed"), callback_data=MenuCb(action="missed"))
    kb.button(text=t("btn_cwl"), callback_data=MenuCb(action="cwl"))
    kb.button(text=t("btn_cwl_table"), callback_data=MenuCb(action="cwltable"))
    kb.button(text=t("btn_me"), callback_data=MenuCb(action="me"))
    if is_group:
        kb.button(text=t("btn_settings"), callback_data=MenuCb(action="settings"))
    kb.button(text=t("btn_help"), callback_data=MenuCb(action="help"))
    kb.adjust(2)
    return kb.as_markup()


def back_button(t: Translator, refresh_action: str | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if refresh_action:
        kb.button(text=t("btn_refresh"), callback_data=MenuCb(action=refresh_action))
    kb.button(text=t("btn_menu"), callback_data=MenuCb(action="main"))
    kb.adjust(2)
    return kb.as_markup()


def settings_menu(t: Translator, chat: ChatSettings) -> InlineKeyboardMarkup:
    def row(label: str, action: str, on: bool | None = None) -> InlineKeyboardButton:
        text = f"{'✅' if on else '❌'} {label}" if on is not None else label
        return InlineKeyboardButton(text=text, callback_data=SettingsCb(action=action).pack())

    autodelete = t("autodelete_after", n=chat.autodelete_min) if chat.autodelete_min else t("autodelete_off")
    rows = [
        [row(t("opt_prep"), "notify_prep", chat.notify_prep)],
        [row(t("opt_start"), "notify_start", chat.notify_start)],
        [
            row(t("btn_opt_remind"), "notify_remind", chat.notify_remind),
            row(t("btn_remind_hours", h=chat.remind_hours), "remind_hours"),
        ],
        [row(t("opt_end"), "notify_end", chat.notify_end)],
        [row(t("btn_mentions"), "mention_players", chat.mention_players)],
        [row(t("btn_autodelete", value=autodelete), "autodelete")],
        [row(t("btn_language"), "language")],
        [InlineKeyboardButton(text=t("btn_menu"), callback_data=MenuCb(action="main").pack())],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def language_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for code, name in LANGUAGE_NAMES.items():
        kb.button(text=name, callback_data=LanguageCb(code=code))
    kb.adjust(2)
    return kb.as_markup()


def unlink_menu(t: Translator, tags_with_names: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for tag, name in tags_with_names:
        kb.button(text=t("btn_unlink", name=name, tag=tag), callback_data=UnlinkCb(tag=tag))
    kb.adjust(1)
    return kb.as_markup()
