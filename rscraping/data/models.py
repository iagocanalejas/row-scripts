import collections
import json
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Optional

RaceName = collections.namedtuple("RaceName", ["race_id", "name"])


class Datasource(StrEnum):
    ACT = auto()
    LGT = auto()
    ARC = auto()
    ABE = auto()
    TRAINERAS = auto()
    INFOREMO = auto()

    @classmethod
    def has_value(cls, value: str) -> bool:
        return value is not None and value.lower() in [d for d in cls]

    @classmethod
    def is_OCR(cls, value: str) -> bool:
        return value is not None and value.lower() in [cls.INFOREMO]

    @classmethod
    def _missing_(cls, value: str) -> Optional["Datasource"]:
        value = value.lower()
        for member in cls:
            if member.value == value:
                return member
        return None

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return self.__str__()


@dataclass
class Lineup:
    race: str
    club: str
    coach: str
    delegate: str
    coxswain: str | None
    starboard: list[str]
    larboard: list[str]
    substitute: list[str]
    bow: str | None
    images: list[str]

    def to_json(self) -> str:
        d = {k: v for k, v in self.__dict__.items()}
        return json.dumps(d, indent=4, skipkeys=True, ensure_ascii=False)


@dataclass
class Race:
    name: str
    date: str
    day: int
    modality: str
    type: str
    league: str | None
    town: str | None
    organizer: str | None
    sponsor: str | None

    # normalized fields
    normalized_names: list[tuple[str, int | None]]

    # datasource data
    race_id: str
    url: str | None
    datasource: str
    gender: str | None

    participants: list["Participant"]

    # not available in all the datasource
    race_laps: int | None = None
    race_lanes: int | None = None
    cancelled: bool = False

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        d["participants"] = [p.to_dict() for p in d["participants"]]
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=4, skipkeys=True, ensure_ascii=False)


@dataclass
class Participant:
    gender: str
    category: str
    club_name: str
    lane: int | None
    series: int | None
    laps: list[str]
    distance: int | None
    handicap: str | None

    # normalized fields
    participant: str

    race: Race

    disqualified: bool = False

    # extra arguments
    lineup: Optional["Lineup"] = None

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k not in ["race"]}
        d["lineup"] = {k: v for k, v in self.lineup.__dict__.items() if k not in ["race"]} if self.lineup else None
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=4, skipkeys=True, ensure_ascii=False)
