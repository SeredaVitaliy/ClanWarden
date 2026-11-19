"""Render README preview images from the bot's real message templates.

    pip install playwright && playwright install chromium
    python scripts/render_previews.py

Every message in the pictures is produced by the same `clanwarden.texts`
functions the bot uses, fed with demo data. So when a template changes,
re-running this script keeps the README images truthful.
Output: docs/images/preview-en.png, docs/images/preview-ru.png
"""

from __future__ import annotations

import html
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clanwarden import texts  # noqa: E402
from clanwarden.bot.keyboards import settings_menu  # noqa: E402
from clanwarden.coc.models import CwlGroup, War  # noqa: E402
from clanwarden.db import ChatSettings, Link, PlayerStats, WarRecord  # noqa: E402
from clanwarden.i18n import Translator  # noqa: E402
from clanwarden.services.wars import CwlRound, compute_standings  # noqa: E402

NOW = datetime(2026, 11, 20, 18, 0, tzinfo=UTC)
OUT = ROOT / "docs" / "images"


# --- demo data -------------------------------------------------------------


def _time(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S.000Z")


def _member(tag: str, name: str, pos: int, attacks: list[int]) -> dict:
    return {
        "tag": tag,
        "name": name,
        "mapPosition": pos,
        "townhallLevel": 16 - pos // 5,
        "attacks": [
            {
                "attackerTag": tag,
                "defenderTag": "#Q",
                "stars": s,
                "destructionPercentage": 60 + s * 13,
                "order": i,
            }
            for i, s in enumerate(attacks)
        ],
    }


NAMES = [
    "Alex", "Snow", "Ragnar", "Maria", "Kenji", "Viking", "Luna", "Dmitry",
    "Shadow", "Bjorn", "Nika", "Phoenix", "Tom", "Iris", "Goblin King",
]  # fmt: skip
ATTACKS = [[3, 3], [3], [3, 2], [], [3, 3], [2, 3], [3], [3, 3], [], [2, 2], [3, 3], [3], [2], [3, 2], [1, 2]]


def regular_war() -> War:
    members = [_member(f"#P{i}", n, i + 1, ATTACKS[i]) for i, n in enumerate(NAMES)]
    end = NOW + timedelta(hours=2, minutes=41)
    data = {
        "state": "inWar",
        "teamSize": 15,
        "attacksPerMember": 2,
        "preparationStartTime": _time(end - timedelta(hours=47)),
        "startTime": _time(end - timedelta(hours=24)),
        "endTime": _time(end),
        "clan": {"tag": "#IRON", "name": "Iron Legion", "stars": 37, "destructionPercentage": 81.4,
                 "attacks": 23, "members": members},
        "opponent": {"tag": "#NIGHT", "name": "Night Raiders", "stars": 33, "destructionPercentage": 74.9,
                     "attacks": 21, "members": []},
    }  # fmt: skip
    return War.from_api(data)


def cwl() -> tuple[CwlRound, CwlGroup, list[War]]:
    clans = ["Iron Legion", "Night Raiders", "Frost Giants", "Red Dragons",
             "Sky Hunters", "Stone Wall", "Wild Wolves", "Golden Army"]  # fmt: skip
    group = CwlGroup.from_api(
        {
            "state": "inWar",
            "season": "2026-11",
            "clans": [{"tag": f"#C{i}", "name": n, "clanLevel": 20} for i, n in enumerate(clans)],
            "rounds": [{"warTags": [f"#W{r}{p}" for p in range(4)]} for r in range(7)],
        }
    )
    results = [  # (round, pairs, stars) for finished rounds
        [(0, 1, 38, 35), (2, 3, 41, 30), (4, 5, 33, 36), (6, 7, 29, 40)],
        [(0, 2, 42, 37), (1, 3, 35, 35), (4, 6, 39, 31), (5, 7, 30, 38)],
    ]
    wars: list[War] = []
    for r, pairs in enumerate(results):
        for p, (a, b, sa, sb) in enumerate(pairs):
            wars.append(
                War.from_api(
                    {
                        "state": "warEnded",
                        "teamSize": 15,
                        "attacksPerMember": 1,
                        "clan": {
                            "tag": f"#C{a}",
                            "name": clans[a],
                            "stars": sa,
                            "destructionPercentage": 80.0,
                        },
                        "opponent": {
                            "tag": f"#C{b}",
                            "name": clans[b],
                            "stars": sb,
                            "destructionPercentage": 75.0,
                        },
                    },
                    is_cwl=True,
                    war_tag=f"#W{r}{p}",
                )  # fmt: skip
            )
    end = NOW + timedelta(hours=11, minutes=5)
    current = War.from_api(
        {
            "state": "inWar", "teamSize": 15, "attacksPerMember": 1,
            "startTime": _time(end - timedelta(hours=24)), "endTime": _time(end),
            "clan": {"tag": "#C0", "name": "Iron Legion", "stars": 21, "destructionPercentage": 74.3, "attacks": 9,
                     "members": [_member(f"#P{i}", n, i + 1, [3, 2, 3][i % 3:i % 3 + 1] if i < 9 else [])
                                 for i, n in enumerate(NAMES)]},
            "opponent": {"tag": "#C3", "name": "Red Dragons", "stars": 18, "destructionPercentage": 65.0, "attacks": 8},
        },
        is_cwl=True, war_tag="#W20",
    )  # fmt: skip
    return CwlRound(group=group, round_number=3, war=current), group, wars + [current]


def stats() -> tuple[WarRecord, list[PlayerStats]]:
    rows = [
        ("Alex", 10, 20, 20, 54, 15, 1720), ("Kenji", 10, 20, 20, 52, 14, 1690),
        ("Dmitry", 10, 19, 20, 50, 13, 1610), ("Nika", 9, 18, 18, 46, 11, 1500),
        ("Ragnar", 10, 18, 20, 44, 9, 1530), ("Snow", 10, 16, 20, 41, 10, 1300),
        ("Viking", 8, 16, 16, 38, 7, 1310), ("Maria", 10, 14, 20, 33, 6, 1100),
        ("Shadow", 7, 9, 14, 20, 3, 690),
    ]  # fmt: skip
    players = [PlayerStats(f"#P{i}", *row) for i, row in enumerate(rows)]
    return WarRecord(wars=10, wins=7, losses=2, ties=1), players


# --- rendering --------------------------------------------------------------


def telegram_html_to_web(text: str) -> str:
    """Telegram's HTML subset → web HTML: keep b/i/code/a, turn newlines into <br>."""
    text = re.sub(r'<a href="tg://user\?id=\d+">', '<a class="mention">', text)
    return text.replace("\n", "<br>")


def bubble(text: str, keyboard: list[list[str]] | None = None, time: str = "18:00") -> str:
    buttons = ""
    if keyboard:
        rows = "".join(
            '<div class="kb-row">'
            + "".join(f'<div class="kb-btn">{html.escape(b)}</div>' for b in row)
            + "</div>"
            for row in keyboard
        )
        buttons = f'<div class="kb">{rows}</div>'
    return f"""
    <div class="msg">
      <div class="avatar">CW</div>
      <div class="col">
        <div class="bubble"><div class="author">Clan Warden</div>{telegram_html_to_web(text)}
          <span class="time">{time}</span></div>
        {buttons}
      </div>
    </div>"""


CSS = """
* { box-sizing: border-box; }
body { margin: 0; background: #0e1621; font-family: 'Fira Sans', 'Noto Color Emoji', sans-serif; }
.chat { width: 560px; padding: 22px 18px 10px; display: flex; flex-direction: column; gap: 16px;
        background: radial-gradient(circle at 20% 10%, #1b2a3a 0%, #0e1621 60%); }
.header { color: #8fa3b8; font-size: 13px; text-align: center; margin-bottom: 2px; }
.header b { color: #e9eef3; font-size: 15px; display: block; }
.msg { display: flex; gap: 8px; align-items: flex-end; }
.avatar { width: 34px; height: 34px; border-radius: 50%; flex: none; background: linear-gradient(135deg,#f5a623,#c0392b);
          color: white; font-weight: 700; font-size: 13px; display: flex; align-items: center; justify-content: center; }
.col { display: flex; flex-direction: column; gap: 4px; max-width: 470px; }
.bubble { background: #182533; color: #e9eef3; border-radius: 14px 14px 14px 4px; padding: 8px 12px 18px;
          font-size: 14.5px; line-height: 1.42; position: relative; min-width: 180px; }
.author { color: #f5a623; font-weight: 600; font-size: 13.5px; margin-bottom: 3px; }
.time { position: absolute; right: 10px; bottom: 4px; font-size: 11px; color: #6d8196; }
code { font-family: 'DejaVu Sans Mono', monospace; font-size: 12.5px; background: #0f1b27; padding: 1px 4px; border-radius: 4px; }
i { color: #9fb0c2; }
a.mention { color: #6ab3f3; text-decoration: none; }
.kb { display: flex; flex-direction: column; gap: 4px; }
.kb-row { display: flex; gap: 4px; }
.kb-btn { flex: 1; text-align: center; background: rgba(36,52,70,.92); color: #e9eef3; border-radius: 8px;
          padding: 7px 6px; font-size: 13.5px; }
"""


def page(t: Translator, title: str, subtitle: str) -> str:
    war = regular_war()
    links = {f"#P{i}": Link(f"#P{i}", 1000 + i, n, True) for i, n in enumerate(NAMES) if i not in (8,)}
    rnd, group, cwl_wars = cwl()
    record, players = stats()
    settings = ChatSettings(
        chat_id=-1, clan_tag="#IRON", thread_id=None, remind_hours=3, notify_prep=True, notify_start=True,
        notify_remind=True, notify_end=True, mention_players=True, autodelete_min=0, rules=None,
        language=t.language,
    )  # fmt: skip
    keyboard = [[button.text for button in row] for row in settings_menu(t, settings).inline_keyboard]

    messages = [
        bubble(texts.notify_reminder(t, war, NOW, links, use_mentions=True), time="15:19"),
        bubble(texts.cwl_round(t, rnd, NOW), time="16:02"),
        bubble(texts.cwl_table(t, group, compute_standings(group, cwl_wars), "#C0"), time="16:02"),
        bubble(texts.clan_stats(t, "Iron Legion", record, players), time="17:40"),
        bubble(texts.settings_text(t, settings, "Iron Legion"), keyboard, time="17:58"),
    ]
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{CSS}</style></head>
    <body><div class="chat"><div class="header"><b>{title}</b>{subtitle}</div>{"".join(messages)}</div></body></html>"""


def main() -> None:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    pages = {
        "en": page(Translator("en"), "Iron Legion · Clan chat", "Clan Warden demo"),
        "ru": page(Translator("ru"), "Iron Legion · Чат клана", "Демонстрация Clan Warden"),
    }
    with sync_playwright() as p:
        executable = next(
            (c for c in ("/usr/bin/google-chrome", "/usr/bin/chromium") if Path(c).exists()), None
        )
        browser = p.chromium.launch(executable_path=executable) if executable else p.chromium.launch()
        tab = browser.new_page(viewport={"width": 560, "height": 800}, device_scale_factor=2)
        for lang, content in pages.items():
            tab.set_content(content)
            tab.wait_for_timeout(300)
            tab.locator(".chat").screenshot(path=str(OUT / f"preview-{lang}.png"))
            print(f"written docs/images/preview-{lang}.png")
        browser.close()


if __name__ == "__main__":
    main()
