import logging
import os
import re
from collections.abc import Generator
from typing import Any, override

from parsel.selector import Selector

from pyutils.strings import find_date, remove_parenthesis, whitespaces_clean
from rscraping.data.constants import (
    CATEGORY_ABSOLUT,
    GENDER_FEMALE,
    GENDER_MALE,
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

from ._protocol import HtmlParser

logger = logging.getLogger(os.path.dirname(os.path.realpath(__file__)))


class ACTHtmlParser(HtmlParser):
    DATASOURCE = Datasource.ACT

    @override
    def parse_race(self, selector: Selector, *, race_id: str, is_female: bool, **_) -> Race | None:
        name = self.get_name(selector)
        if not name:
            logger.error(f"{self.DATASOURCE}: no race found for {race_id=}")
            return None
        logger.info(f"{self.DATASOURCE}: found race {name}")

        t_date = find_date(name)
        if not t_date:
            raise ValueError(f"{self.DATASOURCE}: no date found for {name=}")

        gender = GENDER_FEMALE if is_female else GENDER_MALE

        normalized_names = normalize_name_parts(normalize_race_name(name))
        if len(normalized_names) == 0:
            logger.error(f"{self.DATASOURCE}: unable to normalize {name=}")
            return None
        normalized_names = [
            self._hardcoded_name_edition(remove_day_indicator(n), is_female=is_female, year=t_date.year, edition=e)
            for (n, e) in normalized_names
        ]
        logger.info(f"{self.DATASOURCE}: race normalized to {normalized_names=}")

        participants = self.get_participants(selector)

        race = Race(
            name=self.get_name(selector),
            normalized_names=normalized_names,
            date=t_date.strftime("%d/%m/%Y"),
            type=self.get_type(selector, participants),
            day=self.get_day(selector),
            modality=RACE_TRAINERA,
            league=self.get_league(selector, is_female),
            town=self.get_town(selector),
            organizer=self.get_organizer(selector),
            sponsor=find_race_sponsor(self.get_name(selector)),
            race_ids=[race_id],
            url=None,
            gender=gender,
            datasource=self.DATASOURCE.value,
            cancelled=self.is_cancelled(selector),
            race_laps=self.get_race_laps(selector),
            race_lanes=self.get_race_lanes(selector, participants),
            participants=[],
        )

        for row in participants:
            race.participants.append(
                Participant(
                    gender=gender,
                    category=CATEGORY_ABSOLUT,
                    club_name=self.get_club_name(row),
                    lane=self.get_lane(row),
                    series=self.get_series(selector, row),
                    laps=self.get_laps(row),
                    distance=self.get_distance(is_female),
                    handicap=None,
                    participant=normalize_club_name(self.get_club_name(row)).replace("ACT | ", ""),
                    race=race,
                    disqualified=self.is_disqualified(row),
                )
            )

        return race

    @override
    def parse_race_ids(self, selector: Selector, **_) -> Generator[str, Any, Any]:
        urls = selector.xpath('//*[@id="col-a"]/div/section/div[5]/table/tbody/tr[*]/td[*]/a/@href').getall()
        return (url_parts[-1] for url_parts in (url.split("r=") for url in urls))

    @override
    def parse_race_names(self, selector: Selector, **_) -> Generator[RaceName, Any, Any]:
        hrefs = selector.xpath('//*[@id="col-a"]/div/section/div[5]/table/tbody/tr[*]/td[*]/a').getall()
        selectors = [Selector(h) for h in hrefs]
        pairs = [(s.xpath("//*/@href").get("").split("r=")[-1], s.xpath("//*/text()").get("")) for s in selectors]
        return (RaceName(p[0], whitespaces_clean(p[1]).upper()) for p in pairs)

    @override
    def parse_lineup(self, *_, **__):
        raise NotImplementedError

    ####################################################
    #                     GETTERS                      #
    ####################################################

    def get_name(self, selector: Selector) -> str:
        return whitespaces_clean(selector.xpath('//*[@id="col-a"]/div/section/div[1]/h3/text()').get("")).upper()

    def get_day(self, selector: Selector) -> int:
        name = self.get_name(selector)
        if is_play_off(name):
            return 1 if "1" in remove_parenthesis(name) else 2

        matches = re.findall(r"\(?(\dJ|J\d)\)?", name)
        return int(re.findall(r"\d+", matches[0])[0].strip()) if matches else 1

    def get_type(self, selector: Selector, participants: list[Selector]) -> str:
        if is_play_off(self.get_name(selector)):
            return RACE_TIME_TRIAL
        lanes = list(self.get_lane(p) for p in participants)
        return RACE_TIME_TRIAL if all(int(lane) == int(lanes[0]) for lane in lanes) else RACE_CONVENTIONAL

    def get_league(self, selector: Selector, is_female: bool) -> str | None:
        return "ACT" if is_play_off(self.get_name(selector)) else "LIGA EUSKOTREN" if is_female else "EUSKO LABEL LIGA"

    def get_town(self, selector: Selector) -> str:
        value = selector.xpath('//*[@id="col-a"]/div/section/div[2]/table/tbody/tr/td[2]/text()').get("")
        return normalize_town(value)

    def get_organizer(self, selector: Selector) -> str | None:
        organizer = whitespaces_clean(
            selector.xpath('//*[@id="col-a"]/div/section/div[2]/table/tbody/tr/td[1]/text()').get("")
        ).upper()
        return organizer if organizer else None

    def get_race_lanes(self, selector: Selector, participants: list[Selector]) -> int:
        if self.get_type(selector, participants) == RACE_TIME_TRIAL:
            return 1
        lanes = list(self.get_lane(p) for p in participants)
        return max(int(lane) for lane in lanes)

    def get_race_laps(self, selector: Selector) -> int | None:
        columns = selector.xpath('//*[@id="col-a"]/div/section/div[3]/div[2]/div/table/tbody/tr').getall()
        columns = [Selector(c).xpath("//*/td/text()").getall() for c in columns]
        columns = max(len(c) - 3 for c in columns)
        return columns if columns > 1 else None

    def is_cancelled(self, selector: Selector) -> bool:
        # race_id=1301303104|1301302999
        # try to find the "No puntuable" text in the header
        return selector.xpath('//*[@id="col-a"]/div/section/div[1]/p/span/text()').get("").upper() == "NO PUNTUABLE"

    def get_participants(self, selector: Selector) -> list[Selector]:
        rows = selector.xpath('//*[@id="col-a"]/div/section/div[*]/div[2]/div/table/tbody/tr[*]').getall()
        return [Selector(text=t) for t in rows]

    def get_lane(self, participant: Selector) -> int:
        lane = participant.xpath("//*/td[1]/text()").get()
        return int(lane) if lane else 0

    def get_club_name(self, participant: Selector) -> str:
        name = participant.xpath("//*/td[2]/text()").get()
        return whitespaces_clean(name).upper() if name else ""

    def get_distance(self, is_female: bool) -> int:
        return 2778 if is_female else 5556

    def get_laps(self, participant: Selector) -> list[str]:
        laps = participant.xpath("//*/td/text()").getall()[2:-1]
        return [t.strftime("%M:%S.%f") for t in [normalize_lap_time(e) for e in laps if e] if t is not None]

    def is_disqualified(self, participant: Selector) -> bool:
        # race_id=1647864823
        # try to find the "Descal" text in the final crono
        laps = participant.xpath("//*/td/text()").getall()[2:-1]
        return whitespaces_clean(laps[-1]) == "Descal"

    def get_series(self, selector: Selector, participant: Selector) -> int:
        series = 1
        searching_name = participant.xpath("//*/td[2]/text()").get("")
        for table in selector.xpath('//*[@id="col-a"]/div/section/div[*]/div[2]/div/table/tbody').getall():
            for p in Selector(table).xpath("//*/tr/td[2]/text()").getall():
                if p == searching_name:
                    return series
            series += 1
        return 0

    ####################################################
    #                  NORMALIZATION                   #
    ####################################################
    @staticmethod
    def _hardcoded_name_edition(name: str, is_female: bool, year: int, edition: int | None) -> tuple[str, int | None]:
        if "ASTILLERO" in name:
            name, edition = "BANDERA AYUNTAMIENTO DE ASTILLERO", (year - 1970)

        if "ORIOKO" in name:
            name = "ORIOKO ESTROPADAK"

        if "CORREO IKURRIÑA" in name:
            name, edition = "EL CORREO IKURRIÑA", (year - 1986)

        if "EL CORTE" in name:
            name, edition = "GRAN PREMIO EL CORTE INGLÉS", (year - 1970)

        if is_play_off(name):
            name, edition = ("PLAY-OFF ACT (FEMENINO)", (year - 2016)) if is_female else ("PLAY-OFF ACT", (year - 2002))

        return name, edition
