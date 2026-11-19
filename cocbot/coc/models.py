"""Модели данных Clash of Clans API.

Сырые JSON-ответы превращаем в dataclass'ы на входе в систему. Остальной код
работает с типизированными объектами и не гадает, есть ли в словаре ключ
"attacks" и список ли это.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum


class WarState(StrEnum):
    NOT_IN_WAR = "notInWar"
    PREPARATION = "preparation"
    IN_WAR = "inWar"
    ENDED = "warEnded"

    @classmethod
    def parse(cls, raw: str | None) -> WarState:
        try:
            return cls(raw)
        except ValueError:
            return cls.NOT_IN_WAR

    @property
    def is_active(self) -> bool:
        return self in (WarState.PREPARATION, WarState.IN_WAR)


class WarResult(StrEnum):
    WIN = "win"
    LOSE = "lose"
    TIE = "tie"


def parse_time(raw: str | None) -> datetime | None:
    """'20240131T120000.000Z' -> datetime в UTC."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=UTC)
    except ValueError:
        try:
            return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except ValueError:
            return None


@dataclass(frozen=True)
class Attack:
    attacker_tag: str
    defender_tag: str
    stars: int
    destruction: float
    order: int

    @classmethod
    def from_api(cls, data: dict) -> Attack:
        return cls(
            attacker_tag=data.get("attackerTag", ""),
            defender_tag=data.get("defenderTag", ""),
            stars=int(data.get("stars", 0)),
            destruction=float(data.get("destructionPercentage", 0)),
            order=int(data.get("order", 0)),
        )


@dataclass(frozen=True)
class WarMember:
    tag: str
    name: str
    map_position: int
    townhall: int
    attacks: tuple[Attack, ...] = ()

    @classmethod
    def from_api(cls, data: dict) -> WarMember:
        attacks = data.get("attacks") or []
        return cls(
            tag=data.get("tag", ""),
            name=data.get("name", "?"),
            map_position=int(data.get("mapPosition", 0)),
            townhall=int(data.get("townhallLevel", 0)),
            attacks=tuple(sorted((Attack.from_api(a) for a in attacks), key=lambda a: a.order)),
        )


@dataclass(frozen=True)
class WarClan:
    tag: str
    name: str
    stars: int
    destruction: float
    attacks_used: int
    members: tuple[WarMember, ...] = ()

    @classmethod
    def from_api(cls, data: dict | None) -> WarClan:
        data = data or {}
        members = sorted(
            (WarMember.from_api(m) for m in data.get("members") or []),
            key=lambda m: m.map_position,
        )
        return cls(
            tag=data.get("tag", ""),
            name=data.get("name", "?"),
            stars=int(data.get("stars", 0)),
            destruction=float(data.get("destructionPercentage", 0)),
            attacks_used=int(data.get("attacks", 0)),
            members=tuple(members),
        )


@dataclass(frozen=True)
class War:
    state: WarState
    team_size: int
    attacks_per_member: int
    preparation_start: datetime | None
    start: datetime | None
    end: datetime | None
    clan: WarClan
    opponent: WarClan
    is_cwl: bool = False
    war_tag: str | None = None

    @classmethod
    def from_api(cls, data: dict, *, is_cwl: bool = False, war_tag: str | None = None) -> War:
        # В ЛВК у каждого игрока одна атака, и API не всегда присылает поле.
        default_attacks = 1 if is_cwl else 2
        return cls(
            state=WarState.parse(data.get("state")),
            team_size=int(data.get("teamSize", 0)),
            attacks_per_member=int(data.get("attacksPerMember") or default_attacks),
            preparation_start=parse_time(data.get("preparationStartTime")),
            start=parse_time(data.get("startTime")),
            end=parse_time(data.get("endTime")),
            clan=WarClan.from_api(data.get("clan")),
            opponent=WarClan.from_api(data.get("opponent")),
            is_cwl=is_cwl,
            war_tag=war_tag,
        )

    # --- производные значения ---

    @property
    def key(self) -> str:
        """Стабильный идентификатор войны — по нему помним отправленные уведомления.

        Порядок кланов сортируем, чтобы ключ не зависел от того, с чьей стороны
        мы смотрим на войну. Время начала подготовки отличает две войны с одним
        и тем же соперником.
        """
        if self.war_tag:
            return f"cwl:{self.war_tag}"
        a, b = sorted((self.clan.tag, self.opponent.tag))
        prep = self.preparation_start.strftime("%Y%m%dT%H%M%S") if self.preparation_start else "?"
        return f"war:{a}:{b}:{prep}"

    @property
    def total_attacks(self) -> int:
        return self.team_size * self.attacks_per_member

    def involves(self, clan_tag: str) -> bool:
        return clan_tag in (self.clan.tag, self.opponent.tag)

    def oriented(self, our_tag: str) -> War:
        """Возвращает войну, где `clan` — это наш клан.

        В ЛВК API отдаёт войну без привязки к стороне: наш клан может оказаться
        и в `clan`, и в `opponent`.
        """
        if self.opponent.tag == our_tag:
            return replace(self, clan=self.opponent, opponent=self.clan)
        return self

    def attacks_left(self, member: WarMember) -> int:
        return max(self.attacks_per_member - len(member.attacks), 0)

    def members_with_attacks_left(self) -> list[WarMember]:
        return [m for m in self.clan.members if self.attacks_left(m) > 0]

    def find_member(self, tag: str) -> WarMember | None:
        return next((m for m in self.clan.members if m.tag == tag), None)

    @property
    def result(self) -> WarResult:
        """Итог с точки зрения нашего клана: больше звёзд, при равенстве — процент."""
        ours = (self.clan.stars, self.clan.destruction)
        theirs = (self.opponent.stars, self.opponent.destruction)
        if ours > theirs:
            return WarResult.WIN
        if ours < theirs:
            return WarResult.LOSE
        return WarResult.TIE


@dataclass(frozen=True)
class CwlClan:
    tag: str
    name: str
    level: int


@dataclass(frozen=True)
class CwlGroup:
    state: str  # preparation / inWar / ended
    season: str
    clans: tuple[CwlClan, ...]
    rounds: tuple[tuple[str, ...], ...]  # warTags по раундам, "#0" — раунд ещё не сформирован

    @classmethod
    def from_api(cls, data: dict) -> CwlGroup:
        return cls(
            state=data.get("state", "ended"),
            season=data.get("season", ""),
            clans=tuple(
                CwlClan(tag=c.get("tag", ""), name=c.get("name", "?"), level=int(c.get("clanLevel", 0)))
                for c in data.get("clans") or []
            ),
            rounds=tuple(
                tuple(t for t in r.get("warTags") or [] if t and t != "#0") for r in data.get("rounds") or []
            ),
        )

    @property
    def is_active(self) -> bool:
        return self.state in ("preparation", "inWar")

    def clan_name(self, tag: str) -> str:
        return next((c.name for c in self.clans if c.tag == tag), tag)


@dataclass
class CwlStanding:
    tag: str
    name: str
    stars: int = 0
    destruction: float = 0.0
    wins: int = 0
    wars_played: int = 0


@dataclass(frozen=True)
class PlayerClan:
    tag: str
    name: str


@dataclass(frozen=True)
class Player:
    tag: str
    name: str
    townhall: int
    clan: PlayerClan | None = None

    @classmethod
    def from_api(cls, data: dict) -> Player:
        clan = data.get("clan")
        return cls(
            tag=data.get("tag", ""),
            name=data.get("name", "?"),
            townhall=int(data.get("townHallLevel", 0)),
            clan=PlayerClan(tag=clan.get("tag", ""), name=clan.get("name", "?")) if clan else None,
        )


@dataclass(frozen=True)
class ClanMember:
    tag: str
    name: str
    role: str


@dataclass(frozen=True)
class Clan:
    tag: str
    name: str
    level: int
    war_log_public: bool
    members: tuple[ClanMember, ...] = field(default_factory=tuple)

    @classmethod
    def from_api(cls, data: dict) -> Clan:
        return cls(
            tag=data.get("tag", ""),
            name=data.get("name", "?"),
            level=int(data.get("clanLevel", 0)),
            war_log_public=bool(data.get("isWarLogPublic", False)),
            members=tuple(
                ClanMember(tag=m.get("tag", ""), name=m.get("name", "?"), role=m.get("role", "member"))
                for m in data.get("memberList") or []
            ),
        )
