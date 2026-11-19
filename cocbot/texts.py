"""Тексты сообщений.

Используем parse_mode=HTML, а не Markdown: в никах игроков бывают *, _ и `,
которые ломают Markdown-разметку. В HTML достаточно экранировать три символа,
что и делает html.escape.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from html import escape

from cocbot.coc.models import CwlGroup, CwlStanding, War, WarMember, WarResult, WarState
from cocbot.db import ChatSettings, Link
from cocbot.services.wars import CwlRound

STATE_TITLES = {
    WarState.PREPARATION: "🛡 День подготовки",
    WarState.IN_WAR: "⚔️ День атак",
    WarState.ENDED: "🏁 Война завершена",
    WarState.NOT_IN_WAR: "😴 Войны нет",
}

RESULT_TITLES = {
    WarResult.WIN: "🏆 Победа!",
    WarResult.LOSE: "💀 Поражение",
    WarResult.TIE: "🤝 Ничья",
}


def e(value: object) -> str:
    return escape(str(value), quote=False)


def fmt_duration(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    if total <= 0:
        return "0м"
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    if hours and minutes:
        return f"{hours}ч {minutes}м"
    if hours:
        return f"{hours}ч"
    return f"{minutes}м"


def mention(telegram_id: int, label: str) -> str:
    return f'<a href="tg://user?id={telegram_id}">{e(label)}</a>'


def _war_title(war: War, round_number: int | None = None) -> str:
    kind = f"ЛВК, раунд {round_number}" if war.is_cwl and round_number else ("ЛВК" if war.is_cwl else "КВ")
    return f"<b>{e(war.clan.name)}</b> vs <b>{e(war.opponent.name)}</b> · {kind}, {war.team_size}×{war.team_size}"


def _score(war: War) -> str:
    return (
        f"⭐ {war.clan.stars} : {war.opponent.stars}   "
        f"💥 {war.clan.destruction:.1f}% : {war.opponent.destruction:.1f}%\n"
        f"🗡 Атаки: {war.clan.attacks_used}/{war.total_attacks} : "
        f"{war.opponent.attacks_used}/{war.total_attacks}"
    )


def _timing(war: War, now: datetime) -> str:
    if war.state is WarState.PREPARATION and war.start:
        return f"⏳ До начала боя: <b>{fmt_duration(war.start - now)}</b>"
    if war.state is WarState.IN_WAR and war.end:
        return f"⏳ До конца войны: <b>{fmt_duration(war.end - now)}</b>"
    return ""


def war_summary(war: War, now: datetime, round_number: int | None = None) -> str:
    lines = [STATE_TITLES[war.state], _war_title(war, round_number)]
    timing = _timing(war, now)
    if timing:
        lines.append(timing)
    if war.state in (WarState.IN_WAR, WarState.ENDED):
        lines.append("")
        lines.append(_score(war))
    if war.state is WarState.IN_WAR:
        left = sum(war.attacks_left(m) for m in war.clan.members)
        lines.append(f"\nОсталось атак у клана: <b>{left}</b>")
    if war.state is WarState.ENDED:
        lines.append(f"\n{RESULT_TITLES[war.result]}")
    return "\n".join(lines)


def _member_line(war: War, member: WarMember, links: dict[str, Link], use_mentions: bool) -> str:
    name = e(member.name)
    link = links.get(member.tag)
    if use_mentions and link:
        name = mention(link.telegram_id, member.name)
    left = war.attacks_left(member)
    suffix = f" — осталось {left}" if war.attacks_per_member > 1 else ""
    return f"{member.map_position}. {name}{suffix}"


def missed_list(war: War, links: dict[str, Link], *, use_mentions: bool, ended: bool = False) -> str:
    members = war.members_with_attacks_left()
    if not members:
        return "🎉 Все атаки сделаны!"
    title = "❗ Не провели атаки:" if ended else "❗ Ещё не атаковали:"
    lines = [title] + [_member_line(war, m, links, use_mentions) for m in members]
    unlinked = sum(1 for m in members if m.tag not in links)
    if use_mentions and unlinked:
        lines.append(f"\n<i>Без привязки к Telegram: {unlinked}. Привязать: /link #ТЕГ</i>")
    return "\n".join(lines)


def missed_report(war: War, now: datetime, links: dict[str, Link], *, use_mentions: bool) -> str:
    if war.state is WarState.PREPARATION:
        return f"{_war_title(war)}\nИдёт подготовка, атаки ещё недоступны.\n{_timing(war, now)}"
    parts = [_war_title(war)]
    timing = _timing(war, now)
    if timing:
        parts.append(timing)
    parts += ["", missed_list(war, links, use_mentions=use_mentions, ended=war.state is WarState.ENDED)]
    return "\n".join(parts)


# --- уведомления ---


def notify_preparation(war: War, now: datetime) -> str:
    return (
        "🔎 <b>Соперник найден!</b>\n"
        f"{_war_title(war)}\n"
        f"{_timing(war, now)}\n\n"
        "Самое время проверить базу и войска осад."
    )


def notify_battle_start(war: War, now: datetime, rules: str | None) -> str:
    text = f"🔥 <b>Война началась!</b>\n{_war_title(war)}\n{_timing(war, now)}"
    if rules:
        text += f"\n\n📌 <b>Правила клана:</b>\n{e(rules)}"
    return text


def notify_reminder(war: War, now: datetime, links: dict[str, Link], *, use_mentions: bool) -> str:
    return (
        f"⏰ <b>До конца войны {fmt_duration(war.end - now) if war.end else '?'}!</b>\n"
        f"{_war_title(war)}\n\n" + missed_list(war, links, use_mentions=use_mentions)
    )


def notify_war_end(war: War, now: datetime) -> str:
    text = war_summary(war, now)
    missed = war.members_with_attacks_left()
    if missed:
        names = ", ".join(e(m.name) for m in missed)
        text += f"\n\n❗ Не провели атаки: {names}"
    return text


def dm_reminder(war: War, now: datetime, member: WarMember) -> str:
    left = war.attacks_left(member)
    attacks_word = "атака" if left == 1 else "атаки"
    return (
        f"⏰ <b>{e(member.name)}</b>, у тебя осталась {left} {attacks_word}!\n"
        f"{_war_title(war)}\n"
        f"До конца: <b>{fmt_duration(war.end - now) if war.end else '?'}</b>\n\n"
        "<i>Выключить личные напоминания: /notify</i>"
    )


# --- ЛВК ---


def cwl_round(rnd: CwlRound, now: datetime) -> str:
    total_rounds = len(rnd.group.rounds)
    text = war_summary(rnd.war, now, round_number=rnd.round_number)
    return f"🏆 <b>Лига войн кланов</b> · сезон {e(rnd.group.season)} · раунд {rnd.round_number}/{total_rounds}\n\n{text}"


def cwl_table(group: CwlGroup, standings: list[CwlStanding], our_tag: str) -> str:
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = [f"📊 <b>Таблица ЛВК</b> · сезон {e(group.season)}", ""]
    for place, row in enumerate(standings, start=1):
        prefix = medals.get(place, f"{place}.")
        name = e(row.name)
        if row.tag == our_tag:
            name = f"<b>{name}</b> ⬅️"
        lines.append(f"{prefix} {name} — ⭐ {row.stars} · 💥 {row.destruction:.0f}% · W{row.wins}")
    lines.append("\n<i>Звёзды учитывают +10 за победу в войне. Разрушение — суммарное.</i>")
    return "\n".join(lines)


# --- аккаунты ---


def my_accounts(links: list[Link], war: War | None, now: datetime) -> str:
    if not links:
        return (
            "У тебя пока нет привязанных аккаунтов.\n\n"
            "Привязать: <code>/link #ТЕГ</code>\n"
            "Тег — в профиле игрока в игре, под ником."
        )
    lines = ["👤 <b>Твои аккаунты</b>", ""]
    for link in links:
        mark = "✅" if link.verified else "▫️"
        lines.append(f"{mark} {e(link.player_name or link.player_tag)} <code>{e(link.player_tag)}</code>")
        if war and war.state in (WarState.IN_WAR, WarState.ENDED):
            member = war.find_member(link.player_tag)
            if member is None:
                lines.append("    не участвует в текущей войне")
            elif not member.attacks:
                lines.append(f"    атак нет · осталось {war.attacks_left(member)}")
            else:
                for atk in member.attacks:
                    lines.append(f"    ⭐{atk.stars} · {atk.destruction:.0f}%")
                if war.attacks_left(member):
                    lines.append(f"    осталось атак: {war.attacks_left(member)}")
    if any(not link.verified for link in links):
        lines.append(
            "\n<i>▫️ — не подтверждён. Подтвердить владение: /link #ТЕГ ТОКЕН "
            "(токен — в настройках игры → Ещё настройки → API-токен).</i>"
        )
    return "\n".join(lines)


# --- справка и настройки ---

HELP_GROUP = """<b>CoC War Bot</b> — следит за войнами клана и напоминает про атаки.

<b>Война</b>
/war — текущая война или ЛВК
/missed — кто ещё не атаковал
/cwl — раунд ЛВК · /cwltable — таблица группы

<b>Аккаунты</b>
/link #ТЕГ — привязать аккаунт игры
/unlink #ТЕГ — отвязать
/me — мои аккаунты и атаки
/notify — личные напоминания вкл/выкл

<b>Для админов группы</b>
/setclan #ТЕГ — привязать клан к группе
/settopic — бот пишет только в эту тему
/settings — уведомления и напоминания
/setrules текст — правила, которые бот покажет в начале войны
/checklinks — кто в клане не привязал аккаунт

/menu — то же самое кнопками"""

HELP_PRIVATE = """👋 <b>Привет! Я CoC War Bot.</b>

Я слежу за войнами кланов Clash of Clans: присылаю в группу клана старт войны, напоминания за несколько часов до конца со списком тех, кто не атаковал, и итоги. В личку могу напоминать лично тебе.

<b>Как начать:</b>
1. Добавь меня в группу клана.
2. Админ группы пишет <code>/setclan #ТЕГ_КЛАНА</code>.
3. Каждый игрок пишет <code>/link #ТЕГ_ИГРОКА</code> — чтобы его упоминали в напоминаниях.

В личке команды /war, /missed, /cwl работают для клана твоего привязанного аккаунта (или укажи тег: <code>/war #ТЕГ</code>).

/help — все команды"""


GROUP_WELCOME = """👋 Всем привет! Я буду следить за войнами вашего клана.

<b>Админу группы:</b> привяжите клан командой <code>/setclan #ТЕГ_КЛАНА</code>.
Если в группе есть темы — напишите /settopic в нужной теме.

<b>Игрокам:</b> привяжите свои аккаунты <code>/link #ТЕГ</code>, чтобы я мог позвать вас, когда останутся атаки.

Все команды: /help"""


def _flag(value: bool) -> str:
    return "✅" if value else "❌"


def settings_text(chat: ChatSettings, clan_name: str | None) -> str:
    clan = f"{e(clan_name)} <code>{e(chat.clan_tag)}</code>" if chat.clan_tag else "не привязан (/setclan)"
    thread = f"тема #{chat.thread_id}" if chat.thread_id else "весь чат"
    autodelete = f"через {chat.autodelete_min} мин" if chat.autodelete_min else "выкл"
    return (
        "⚙️ <b>Настройки группы</b>\n\n"
        f"Клан: {clan}\n"
        f"Где отвечаю: {thread}\n\n"
        f"{_flag(chat.notify_prep)} Соперник найден\n"
        f"{_flag(chat.notify_start)} Начало войны\n"
        f"{_flag(chat.notify_remind)} Напоминание за {chat.remind_hours} ч до конца\n"
        f"{_flag(chat.notify_end)} Итоги войны\n"
        f"{_flag(chat.mention_players)} Упоминать игроков в напоминаниях\n"
        f"🧹 Автоудаление ответов: {autodelete}\n"
        f"📌 Правила: {'заданы' if chat.rules else 'нет'}"
    )
