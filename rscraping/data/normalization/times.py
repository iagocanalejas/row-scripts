import re
from datetime import datetime, time

from pyutils.strings import apply_replaces


def normalize_lap_time(value: str) -> time | None:
    """
    Normalize the lap time to a standard time

    1. Try to fix ':18,62' | ':45'
    2. Try to fix '2102:48' | '25:2257'
    3. Try to fix '028:24'
    4. Try to fix '00:009'
    """
    if value.startswith(":"):
        # try to fix ':18,62' | ':45' page errors
        value = "00" + value
    parts = re.findall(r"\d+", value)
    if all(p == "00" for p in parts):
        return None
    if len(parts) == 1:
        # try to fix '20.55.07' page errors
        dot_parts = value.split(".")
        if len(dot_parts) == 3:
            return datetime.strptime(f"{dot_parts[0]}:{dot_parts[1]}.{dot_parts[2]}", "%M:%S.%f").time()
    if len(parts) == 2:
        # try to fix '2102:48' | '25:2257' page errors
        if len(parts[0]) == 3:
            # try to fix '028:24' page errors
            parts[0] = "0" + parts[0]
        if len(parts[1]) == 3:
            # try to fix '00:009' page errors
            parts[1] = parts[1][:-1]
        if len(parts[0]) == 4:
            return datetime.strptime(f"{parts[0][0:2]}:{parts[0][2:]},{parts[1]}", "%M:%S,%f").time()
        if len(parts[1]) == 4:
            return datetime.strptime(f"{parts[0]}:{parts[1][0:2]},{parts[1][2:]}", "%M:%S,%f").time()
        return datetime.strptime(f"{parts[0]}:{parts[1]}", "%M:%S").time()
    if len(parts) == 3:
        return datetime.strptime(f"{parts[0]}:{parts[1]},{parts[2]}", "%M:%S,%f").time()
    return None


MONTHS = {
    "ENERO": ["XANEIRO"],
    "FEBRERO": ["FEBREIRO"],
    "MARZO": [],
    "ABRIL": [],
    "MAYO": ["MAIO"],
    "JUNIO": ["XUÑO"],
    "JULIO": ["XULLO"],
    "AGOSTO": [],
    "SEPTIEMBRE": ["SEPTEMBRO"],
    "OCTUBRE": ["OUTUBRO"],
    "NOVIEMBRE": ["NOVEMBRO"],
    "DICIEMBRE": ["DECEMMBRO"],
}


def normalize_spanish_months(phrase: str) -> str:
    phrase = phrase.upper()
    return apply_replaces(phrase, MONTHS)
