from cocbot import texts
from cocbot.coc.models import War
from cocbot.db import Link
from tests.factories import NOW, clan, member, war_json


def test_names_are_html_escaped():
    ours = clan("#OURS", "<b>Клан</b>", [member("#P1", "a&b<script>", 1, 0)])
    war = War.from_api(war_json(ours=ours))
    text = texts.war_summary(war, NOW) + texts.missed_list(war, {}, use_mentions=False)
    assert "<script>" not in text
    assert "a&amp;b&lt;script&gt;" in text
    assert "&lt;b&gt;Клан&lt;/b&gt;" in text


def test_missed_list_mentions_linked_players():
    war = War.from_api(war_json())
    links = {"#P2": Link(player_tag="#P2", telegram_id=42, player_name="Bob", verified=True)}
    text = texts.missed_list(war, links, use_mentions=True)
    assert '<a href="tg://user?id=42">Bob</a>' in text
    assert "Alice" not in text  # уже провела обе атаки


def test_fmt_duration():
    from datetime import timedelta

    assert texts.fmt_duration(timedelta(hours=3, minutes=5)) == "3ч 5м"
    assert texts.fmt_duration(timedelta(minutes=40)) == "40м"
    assert texts.fmt_duration(timedelta(hours=2)) == "2ч"
    assert texts.fmt_duration(timedelta(seconds=-5)) == "0м"
