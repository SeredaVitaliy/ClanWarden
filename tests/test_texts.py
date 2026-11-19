from datetime import timedelta

from clanwarden import texts
from clanwarden.coc.models import War
from clanwarden.db import Link
from clanwarden.i18n import CATALOGS, Translator, normalize_language
from tests.factories import NOW, clan, member, war_json

EN, RU = Translator("en"), Translator("ru")


def test_names_are_html_escaped():
    ours = clan("#OURS", "<b>Clan</b>", [member("#P1", "a&b<script>", 1, 0)])
    war = War.from_api(war_json(ours=ours))
    text = texts.war_summary(EN, war, NOW) + texts.missed_list(EN, war, {}, use_mentions=False)
    assert "<script>" not in text
    assert "a&amp;b&lt;script&gt;" in text
    assert "&lt;b&gt;Clan&lt;/b&gt;" in text


def test_missed_list_mentions_linked_players():
    war = War.from_api(war_json())
    links = {"#P2": Link(player_tag="#P2", telegram_id=42, player_name="Bob", verified=True)}
    text = texts.missed_list(EN, war, links, use_mentions=True)
    assert '<a href="tg://user?id=42">Bob</a>' in text
    assert "Alice" not in text  # already used both attacks


def test_fmt_duration_is_localized():
    assert texts.fmt_duration(EN, timedelta(hours=3, minutes=5)) == "3h 5m"
    assert texts.fmt_duration(RU, timedelta(hours=3, minutes=5)) == "3ч 5м"
    assert texts.fmt_duration(EN, timedelta(minutes=40)) == "40m"
    assert texts.fmt_duration(EN, timedelta(seconds=-5)) == "0m"


def test_same_war_in_both_languages():
    war = War.from_api(war_json())
    assert "Battle day" in texts.war_summary(EN, war, NOW)
    assert "День атак" in texts.war_summary(RU, war, NOW)


def test_catalogs_have_the_same_keys():
    # A missing key would silently fall back to English — catch it here instead.
    assert set(CATALOGS["ru"]) == set(CATALOGS["en"])


def test_catalog_placeholders_match():
    import string

    def fields(template):
        return {name for _, name, _, _ in string.Formatter().parse(template) if name}

    for key, template in CATALOGS["en"].items():
        assert fields(CATALOGS["ru"][key]) == fields(template), key


def test_language_normalization():
    assert normalize_language("ru") == "ru"
    assert normalize_language("en-US") == "en"
    assert normalize_language("de") is None
    assert normalize_language(None) is None
    assert Translator("de").language == "en"
