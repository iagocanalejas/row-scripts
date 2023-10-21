import logging
import re
from collections.abc import Generator
from datetime import date, datetime
from typing import Any, override

from parsel import Selector

from pyutils.strings import whitespaces_clean
from rscraping.data.constants import (
    GENDER_FEMALE,
    GENDER_MALE,
    PARTICIPANT_CATEGORY_ABSOLUT,
    RACE_CONVENTIONAL,
    RACE_TIME_TRIAL,
    RACE_TRAINERA,
)
from rscraping.data.functions import is_play_off
from rscraping.data.models import Datasource, Participant, Race, RaceName
from rscraping.data.normalization.clubs import normalize_club_name
from rscraping.data.normalization.races import (
    find_race_sponsor,
    normalize_name_parts,
    normalize_race_name,
    remove_day_indicator,
)
from rscraping.data.normalization.times import normalize_lap_time
from rscraping.data.normalization.towns import normalize_town

from ._parser import HtmlParser

logger = logging.getLogger(__name__)


class LGTHtmlParser(HtmlParser):
    DATASOURCE = Datasource.LGT

    @override
    def parse_race(
        self,
        selector: Selector,
        results_selector: Selector,
        race_id: str,
        **_,
    ) -> Race | None:
        name = self.get_name(selector)
        if not name or name.upper() == "EREWEWEWERW" or name.upper() == "REGATA" or "?" in name:  # wtf
            logger.error(f"{self.DATASOURCE}: no race found for {race_id=}")
            return None
        logger.info(f"{self.DATASOURCE}: found race {name}")

        t_date = self.get_date(selector)
        league = self.get_league(selector)
        is_female = any(e in name for e in ["FEMENINA", "FEMININA"]) or (league is not None and "F" in league.split())
        gender = GENDER_FEMALE if is_female else GENDER_MALE

        normalized_names = normalize_name_parts(normalize_race_name(name))
        if len(normalized_names) == 0:
            logger.error(f"{self.DATASOURCE}: unable to normalize {name=}")
            return None
        normalized_names = [
            self._hardcoded_playoff_edition(self._normalize_race_name(n, t_date), year=t_date.year, edition=e)
            for (n, e) in normalized_names
        ]
        logger.info(f"{self.DATASOURCE}: race normalized to {normalized_names=}")

        participants = self.get_participants(results_selector)
        race_laps = self.get_race_laps(results_selector)
        if race_laps < 0:
            logger.error(f"{self.DATASOURCE}: unable to parse laps {normalized_names=}")
            return None

        race = Race(
            name=self.get_name(selector),
            normalized_names=normalized_names,
            date=t_date.strftime("%d/%m/%Y"),
            type=self.get_type(participants),
            day=self.get_day(selector),
            modality=RACE_TRAINERA,
            league=league,
            town=self.get_town(selector),
            organizer=self.get_organizer(selector),
            sponsor=find_race_sponsor(self.get_name(selector)),
            race_id=race_id,
            url=None,
            datasource=self.DATASOURCE.value,
            gender=gender,
            cancelled=self.is_cancelled(participants),
            race_laps=race_laps,
            race_lanes=self.get_race_lanes(participants),
            participants=[],
        )

        for row in participants:
            race.participants.append(
                Participant(
                    gender=gender,
                    category=PARTICIPANT_CATEGORY_ABSOLUT,
                    club_name=self.get_club_name(row),
                    lane=self.get_lane(row),
                    series=self.get_series(results_selector, row),
                    laps=self.get_laps(row),
                    distance=self.get_distance(),
                    handicap=None,
                    participant=normalize_club_name(self.get_club_name(row)),
                    race=race,
                    disqualified=self.is_disqualified(row),
                )
            )

        return race

    @override
    def parse_race_ids(self, selector: Selector, **_) -> Generator[str, Any, Any]:
        urls = selector.xpath("//*/div/div/div[*]/div/a/@href").getall()
        return (u.split("/")[-1].split("-")[0] for u in urls[0:])

    @override
    def parse_race_names(self, selector: Selector, **_) -> Generator[RaceName, Any, Any]:
        values = [Selector(u) for u in selector.xpath("//*/div/div/div[*]/div").getall()]
        values = [
            (
                u.xpath("//*/a/@href").get("").split("/")[-1].split("-")[0],
                u.xpath("//*/table/tr/td[2]/text()").get(""),
            )
            for u in values
        ]
        return (RaceName(p[0], whitespaces_clean(p[1]).upper()) for p in values)

    @override
    def parse_lineup(self, **_):
        raise NotImplementedError

    ####################################################
    #                     GETTERS                      #
    ####################################################

    def is_valid_race(self, selector: Selector) -> bool:
        return bool(self.get_name(selector))

    def get_name(self, selector: Selector) -> str:
        return whitespaces_clean(selector.xpath('//*[@id="regata"]/div/div/div[3]/div[2]/h1/text()').get("")).upper()

    def get_date(self, selector: Selector) -> date:
        value = whitespaces_clean(selector.xpath('//*[@id="regata"]/div/div/div[3]/div[2]/p[2]/text()').get(""))
        return datetime.strptime(value, "%d/%m/%Y").date()

    def get_day(self, selector: Selector) -> int:
        name = self.get_name(selector)
        if "XORNADA" in name:
            day = int(re.findall(r" \d+", name)[0].strip())
            return day
        if is_play_off(name):  # exception case
            if "1" in name:
                return 1
            if "2" in name:
                return 2
            return 2 if self.get_date(selector).isoweekday() == 7 else 1  # 2 for sunday
        return 1

    def get_type(self, participants: list[Selector]) -> str:
        lanes = list(self.get_lane(p) for p in participants)
        return RACE_TIME_TRIAL if all(int(lane) == int(lanes[0]) for lane in lanes) else RACE_CONVENTIONAL

    def get_league(self, selector: Selector) -> str | None:
        if is_play_off(self.get_name(selector)):
            return "LGT"
        return whitespaces_clean(selector.xpath('//*[@id="regata"]/div/div/div[3]/div[2]/p[3]/span/text()').get(""))

    def get_town(self, selector: Selector) -> str:
        value = selector.xpath('//*[@id="regata"]/div/div/div[3]/div[2]/p[1]/text()').get("")
        return normalize_town(value)

    def get_organizer(self, selector: Selector) -> str | None:
        organizer = selector.xpath('//*[@id="regata"]/div/div/div[3]/div[1]/text()').get("")
        organizer = whitespaces_clean(organizer).upper().replace("ORGANIZA:", "").strip() if organizer else None
        return normalize_club_name(organizer) if organizer else None

    def get_race_lanes(self, participants: list[Selector]) -> int:
        if self.get_type(participants) == RACE_TIME_TRIAL:
            return 1
        lanes = list(self.get_lane(p) for p in participants)
        return max(int(lane) for lane in lanes)

    def get_race_laps(self, results_selector: Selector) -> int:
        return len(results_selector.xpath('//*[@id="tabla-tempos"]/tr[1]/th').getall()) - 2

    def is_cancelled(self, participants: list[Selector]) -> bool:
        # race_id=114
        # assume no final time is set for cancelled races (as in the example)
        times = [p.xpath("//*/td/text()").getall()[-1] for p in participants]
        return len([x for x in times if x == "-"]) > len(times) / 3

    def get_participants(self, results_selector: Selector) -> list[Selector]:
        def is_valid(row: Selector) -> bool:
            if len(row.xpath("//*/td").getall()) <= 1:
                return False
            maybe_name = row.xpath("//*/td[2]/text()").get("")
            return bool(maybe_name) and maybe_name != "LIBRE"

        return [
            Selector(p)
            for p in results_selector.xpath('//*[@id="tabla-tempos"]/tr').getall()[1:]
            if is_valid(Selector(p))
        ]

    def get_lane(self, participant: Selector) -> int:
        lane = participant.xpath("//*/td[1]/text()").get()
        return int(lane) if lane else 0

    def get_club_name(self, participant: Selector) -> str:
        name = participant.xpath("//*/td[2]/text()").get()
        return whitespaces_clean(name).upper() if name else ""

    def get_distance(self) -> int:
        return 5556

    def get_laps(self, participant: Selector) -> list[str]:
        laps = participant.xpath("//*/td/text()").getall()[2:]
        return [t.strftime("%M:%S.%f") for t in [normalize_lap_time(e) for e in laps if e] if t is not None]

    def is_disqualified(self, participant: Selector) -> bool:
        # race_id=168
        # try to find the "-" text in the final crono
        laps = participant.xpath("//*/td/text()").getall()[2:]
        return whitespaces_clean(laps[-1]) == "-"

    def get_series(self, results_selector: Selector, participant: Selector) -> int:
        series = 1
        searching_name = participant.xpath("//*/td[2]/text()").get("")
        rows = [Selector(p) for p in results_selector.xpath('//*[@id="tabla-tempos"]/tr[*]').getall()]
        for row in rows:
            row_name = row.xpath("//*/td[2]/text()").get()
            if row_name is not None and row_name == searching_name:
                return series
            if len(row.xpath("//*/td").getall()) == 1:
                series += 1
        return 0

    ####################################################
    #                  NORMALIZATION                   #
    ####################################################

    @staticmethod
    def _normalize_race_name(name: str, t_date: date) -> str:
        name = remove_day_indicator(name)

        if "TERESA HERRERA" in name:  # lgt never saves the final
            return "TROFEO TERESA HERRERA" if t_date.isoweekday() == 7 else "TROFEO TERESA HERRERA (CLASIFICATORIA)"

        if "PLAY" in name:
            return "PLAY-OFF LGT"

        # remove gender
        for g in ["FEMENINA", "FEMININA"]:
            name = name.replace(g, "")

        return whitespaces_clean(name)

    @staticmethod
    def _hardcoded_playoff_edition(name: str, year: int, edition: int | None) -> tuple[str, int | None]:
        if is_play_off(name):
            return name, (year - 2011)
        return name, edition
