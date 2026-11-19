"""Message rendering.

Every function takes a ``Translator`` (``t``) and returns ready-to-send HTML.

We use parse_mode=HTML rather than Markdown on purpose: player names often
contain ``*``, ``_`` or backticks, which break Markdown entities. With HTML
we only need to escape ``<``, ``>`` and ``&`` — that's what ``e()`` does.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from html import escape

from clanwarden.coc.models import CwlGroup, CwlStanding, War, WarMember, WarResult, WarState
from clanwarden.db import ChatSettings, Link
from clanwarden.i18n import LANGUAGE_NAMES, Translator
from clanwarden.services.wars import CwlRound

STATE_KEYS = {
    WarState.PREPARATION: "state_preparation",
    WarState.IN_WAR: "state_in_war",
    WarState.ENDED: "state_ended",
    WarState.NOT_IN_WAR: "state_not_in_war",
}

RESULT_KEYS = {
    WarResult.WIN: "result_win",
    WarResult.LOSE: "result_lose",
    WarResult.TIE: "result_tie",
}


def e(value: object) -> str:
    """Escape text for Telegram HTML."""
    return escape(str(value), quote=False)


def fmt_duration(t: Translator, delta: timedelta) -> str:
    total = int(delta.total_seconds())
    if total <= 0:
        return t("dur_m", m=0)
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    if hours and minutes:
        return t("dur_hm", h=hours, m=minutes)
    if hours:
        return t("dur_h", h=hours)
    return t("dur_m", m=minutes)


def mention(telegram_id: int, label: str) -> str:
    """A clickable name that notifies the user, even if they have no @username."""
    return f'<a href="tg://user?id={telegram_id}">{e(label)}</a>'


def war_title(t: Translator, war: War, round_number: int | None = None) -> str:
    if war.is_cwl:
        kind = t("kind_cwl_round", n=round_number) if round_number else t("kind_cwl")
    else:
        kind = t("kind_war")
    size = f"{war.team_size}×{war.team_size}"
    return f"<b>{e(war.clan.name)}</b> vs <b>{e(war.opponent.name)}</b> · {kind}, {size}"


def _score(t: Translator, war: War) -> str:
    return (
        f"⭐ {war.clan.stars} : {war.opponent.stars}   "
        f"💥 {war.clan.destruction:.1f}% : {war.opponent.destruction:.1f}%\n"
        f"{t('score_attacks')}: {war.clan.attacks_used}/{war.total_attacks} : "
        f"{war.opponent.attacks_used}/{war.total_attacks}"
    )


def timing(t: Translator, war: War, now: datetime) -> str:
    if war.state is WarState.PREPARATION and war.start:
        return t("until_start", time=fmt_duration(t, war.start - now))
    if war.state is WarState.IN_WAR and war.end:
        return t("until_end", time=fmt_duration(t, war.end - now))
    return ""


def war_summary(t: Translator, war: War, now: datetime, round_number: int | None = None) -> str:
    lines = [t(STATE_KEYS[war.state]), war_title(t, war, round_number)]
    if when := timing(t, war, now):
        lines.append(when)
    if war.state in (WarState.IN_WAR, WarState.ENDED):
        lines += ["", _score(t, war)]
    if war.state is WarState.IN_WAR:
        left = sum(war.attacks_left(m) for m in war.clan.members)
        lines.append("\n" + t("clan_attacks_left", n=left))
    if war.state is WarState.ENDED:
        lines.append("\n" + t(RESULT_KEYS[war.result]))
    return "\n".join(lines)


def _member_line(
    t: Translator, war: War, member: WarMember, links: dict[str, Link], use_mentions: bool
) -> str:
    link = links.get(member.tag)
    name = mention(link.telegram_id, member.name) if use_mentions and link else e(member.name)
    suffix = t("member_left", n=war.attacks_left(member)) if war.attacks_per_member > 1 else ""
    return f"{member.map_position}. {name}{suffix}"


def missed_list(
    t: Translator, war: War, links: dict[str, Link], *, use_mentions: bool, ended: bool = False
) -> str:
    members = war.members_with_attacks_left()
    if not members:
        return t("all_attacked")
    lines = [t("missed_title_ended" if ended else "missed_title")]
    lines += [_member_line(t, war, m, links, use_mentions) for m in members]
    unlinked = sum(1 for m in members if m.tag not in links)
    if use_mentions and unlinked:
        lines.append("\n" + t("missed_unlinked", n=unlinked))
    return "\n".join(lines)


def missed_report(
    t: Translator, war: War, now: datetime, links: dict[str, Link], *, use_mentions: bool
) -> str:
    if war.state is WarState.PREPARATION:
        return f"{war_title(t, war)}\n{t('prep_no_attacks')}\n{timing(t, war, now)}"
    parts = [war_title(t, war)]
    if when := timing(t, war, now):
        parts.append(when)
    ended = war.state is WarState.ENDED
    parts += ["", missed_list(t, war, links, use_mentions=use_mentions, ended=ended)]
    return "\n".join(parts)


# --- notifications ---


def notify_preparation(t: Translator, war: War, now: datetime) -> str:
    return t("notify_prep", title=war_title(t, war), timing=timing(t, war, now))


def notify_battle_start(t: Translator, war: War, now: datetime, rules: str | None) -> str:
    text = t("notify_start", title=war_title(t, war), timing=timing(t, war, now))
    if rules:
        text += t("notify_rules", rules=e(rules))
    return text


def notify_reminder(
    t: Translator, war: War, now: datetime, links: dict[str, Link], *, use_mentions: bool
) -> str:
    return t(
        "notify_remind",
        time=fmt_duration(t, war.end - now) if war.end else "?",
        title=war_title(t, war),
        missed=missed_list(t, war, links, use_mentions=use_mentions),
    )


def notify_war_end(t: Translator, war: War, now: datetime) -> str:
    text = war_summary(t, war, now)
    if missed := war.members_with_attacks_left():
        text += t("notify_end_missed", names=", ".join(e(m.name) for m in missed))
    return text


def dm_reminder(t: Translator, war: War, now: datetime, member: WarMember) -> str:
    left = war.attacks_left(member)
    head = t("dm_remind_one" if left == 1 else "dm_remind_many", name=e(member.name), n=left)
    body = t(
        "dm_remind_body",
        title=war_title(t, war),
        time=fmt_duration(t, war.end - now) if war.end else "?",
    )
    return f"{head}\n{body}"


# --- Clan War League ---


def cwl_round(t: Translator, rnd: CwlRound, now: datetime) -> str:
    header = t("cwl_header", season=e(rnd.group.season), n=rnd.round_number, total=len(rnd.group.rounds))
    return f"{header}\n\n{war_summary(t, rnd.war, now, round_number=rnd.round_number)}"


def cwl_table(t: Translator, group: CwlGroup, standings: list[CwlStanding], our_tag: str) -> str:
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = [t("cwl_table_title", season=e(group.season)), ""]
    for place, row in enumerate(standings, start=1):
        name = e(row.name)
        if row.tag == our_tag:
            name = f"<b>{name}</b> ⬅️"
        prefix = medals.get(place, f"{place}.")
        lines.append(f"{prefix} {name} — ⭐ {row.stars} · 💥 {row.destruction:.0f}% · W{row.wins}")
    lines.append("\n" + t("cwl_table_note"))
    return "\n".join(lines)


# --- accounts ---


def my_accounts(t: Translator, links: list[Link], war: War | None) -> str:
    if not links:
        return t("accounts_none")
    lines = [t("accounts_title"), ""]
    show_attacks = war is not None and war.state in (WarState.IN_WAR, WarState.ENDED)
    for link in links:
        mark = "✅" if link.verified else "▫️"
        lines.append(f"{mark} {e(link.player_name or link.player_tag)} <code>{e(link.player_tag)}</code>")
        if not show_attacks:
            continue
        member = war.find_member(link.player_tag)
        if member is None:
            lines.append(t("acc_not_in_war"))
        elif not member.attacks:
            lines.append(t("acc_no_attacks", n=war.attacks_left(member)))
        else:
            lines += [f"    ⭐{atk.stars} · {atk.destruction:.0f}%" for atk in member.attacks]
            if left := war.attacks_left(member):
                lines.append(t("acc_left", n=left))
    if any(not link.verified for link in links):
        lines.append("\n" + t("acc_unverified_hint"))
    return "\n".join(lines)


# --- settings ---


def _flag(value: bool) -> str:
    return "✅" if value else "❌"


def settings_text(t: Translator, chat: ChatSettings, clan_name: str | None) -> str:
    clan = (
        f"{e(clan_name or '')} <code>{e(chat.clan_tag)}</code>" if chat.clan_tag else t("settings_clan_none")
    )
    where = t("settings_topic", id=chat.thread_id) if chat.thread_id else t("settings_whole_chat")
    autodelete = t("autodelete_after", n=chat.autodelete_min) if chat.autodelete_min else t("autodelete_off")
    return "\n".join(
        [
            t("settings_title"),
            "",
            t("settings_clan", clan=clan),
            t("settings_where", where=where),
            t("settings_language", value=LANGUAGE_NAMES[t.language]),
            "",
            f"{_flag(chat.notify_prep)} {t('opt_prep')}",
            f"{_flag(chat.notify_start)} {t('opt_start')}",
            f"{_flag(chat.notify_remind)} {t('opt_remind', h=chat.remind_hours)}",
            f"{_flag(chat.notify_end)} {t('opt_end')}",
            f"{_flag(chat.mention_players)} {t('opt_mentions')}",
            t("settings_autodelete", value=autodelete),
            t("settings_rules", value=t("rules_set") if chat.rules else t("rules_none")),
        ]
    )
