"""
NLP Time Parser — Convert German time expressions to APScheduler triggers.

Regex-based (no LLM — fast, deterministic, offline).

Examples:
    "in 5 Minuten"           → DateTrigger(run_date=now+5min)
    "um 14 Uhr"              → DateTrigger(run_date=today@14:00)
    "jeden Montag um 9"      → CronTrigger(day_of_week='mon', hour=9)
    "alle 2 Stunden"         → IntervalTrigger(hours=2)
    "morgen um 10"            → DateTrigger(run_date=tomorrow@10:00)
    "in einer halben Stunde"  → DateTrigger(run_date=now+30min)
    "taeglich um 8"           → CronTrigger(hour=8)
"""

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# German day names → APScheduler day_of_week
DAY_MAP = {
    "montag": "mon", "montags": "mon",
    "dienstag": "tue", "dienstags": "tue",
    "mittwoch": "wed", "mittwochs": "wed",
    "donnerstag": "thu", "donnerstags": "thu",
    "freitag": "fri", "freitags": "fri",
    "samstag": "sat", "samstags": "sat",
    "sonntag": "sun", "sonntags": "sun",
}

# German number words
WORD_NUMBERS = {
    "eine": 1, "einer": 1, "einem": 1, "eins": 1, "ein": 1,
    "zwei": 2, "drei": 3, "vier": 4, "fuenf": 5, "fünf": 5,
    "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10,
    "elf": 11, "zwoelf": 12, "zwölf": 12,
    "fuffzehn": 15, "fuenfzehn": 15, "fünfzehn": 15,
    "zwanzig": 20, "dreissig": 30, "dreißig": 30,
    "vierzig": 40, "fuenfzig": 50, "fünfzig": 50,
}


@dataclass
class ParsedTime:
    """Result of parsing a German time expression."""
    trigger_type: str                       # "date", "cron", "interval"
    trigger_config: Dict[str, Any]          # APScheduler trigger kwargs
    human_description: str                  # "in 5 Minuten"
    max_runs: Optional[int] = None          # 1 for one-shot, None for recurring
    remaining_text: str = ""                # Action text with time stripped


def _parse_number(text: str) -> Optional[int]:
    """Parse a German number word or digit string to int."""
    text = text.strip().lower()
    if text.isdigit():
        return int(text)
    return WORD_NUMBERS.get(text)


def parse_time_expression(
    text: str,
    timezone: str = "Europe/Berlin",
) -> Optional[ParsedTime]:
    """
    Parse a German time expression into an APScheduler trigger config.

    Args:
        text: Full user text (e.g. "Erinnere mich in 5 Minuten an den Termin")
        timezone: IANA timezone string

    Returns:
        ParsedTime or None if no time expression found
    """
    original = text
    lower = text.lower().strip()

    # Try each pattern in priority order
    for parser in _PARSERS:
        result = parser(lower, original, timezone)
        if result is not None:
            return result

    return None


# =====================================================================
# Pattern parsers (each returns ParsedTime or None)
# =====================================================================

def _parse_in_x_minutes(lower: str, original: str, tz: str) -> Optional[ParsedTime]:
    """'in 5 Minuten', 'in einer Stunde', 'in 3 Tagen'"""
    # "in einer halben Stunde" — special case
    m = re.search(r"\bin\s+einer?\s+halben\s+stunde\b", lower)
    if m:
        remaining = _strip_match(original, m)
        return ParsedTime(
            trigger_type="date",
            trigger_config={"run_date": (datetime.now() + timedelta(minutes=30)).isoformat()},
            human_description="in einer halben Stunde",
            max_runs=1,
            remaining_text=remaining,
        )

    # "in X Minuten/Stunden/Tagen/Sekunden"
    m = re.search(
        r"\bin\s+(\d+|eine[mnr]?|zwei|drei|vier|f[uü]nf|sechs|sieben|acht|neun|zehn"
        r"|elf|zw[oö]lf|f[uü]nfzehn|zwanzig|dreissig|drei[sß]ig|vierzig|f[uü]nfzig)"
        r"\s+(minuten?|stunden?|tagen?|sekunden?)\b",
        lower,
    )
    if m:
        num = _parse_number(m.group(1))
        if num is None:
            return None
        unit = m.group(2).rstrip("n").rstrip("e")  # minuten→minut→minut
        delta = _unit_to_timedelta(num, unit)
        if delta is None:
            return None
        remaining = _strip_match(original, m)
        return ParsedTime(
            trigger_type="date",
            trigger_config={"run_date": (datetime.now() + delta).isoformat()},
            human_description=f"in {num} {m.group(2).capitalize()}",
            max_runs=1,
            remaining_text=remaining,
        )
    return None


def _parse_um_uhr(lower: str, original: str, tz: str) -> Optional[ParsedTime]:
    """'um 14 Uhr', 'um 14:30', 'um 9 Uhr 30'"""
    m = re.search(r"\bum\s+(\d{1,2})(?::(\d{2}))?\s*(?:uhr)?\s*(\d{2})?\b", lower)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or m.group(3) or 0)
        if hour > 23 or minute > 59:
            return None

        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)

        remaining = _strip_match(original, m)
        return ParsedTime(
            trigger_type="date",
            trigger_config={"run_date": target.isoformat()},
            human_description=f"um {hour:02d}:{minute:02d} Uhr",
            max_runs=1,
            remaining_text=remaining,
        )
    return None


def _parse_morgen_um(lower: str, original: str, tz: str) -> Optional[ParsedTime]:
    """'morgen um 10', 'uebermorgen um 14 Uhr'"""
    m = re.search(r"\b(morgen|[uü]bermorgen)\s+um\s+(\d{1,2})(?::(\d{2}))?\s*(?:uhr)?\b", lower)
    if m:
        days_offset = 1 if m.group(1).startswith("morgen") else 2
        hour = int(m.group(2))
        minute = int(m.group(3) or 0)
        if hour > 23 or minute > 59:
            return None

        target = datetime.now() + timedelta(days=days_offset)
        target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)

        day_word = "morgen" if days_offset == 1 else "uebermorgen"
        remaining = _strip_match(original, m)
        return ParsedTime(
            trigger_type="date",
            trigger_config={"run_date": target.isoformat()},
            human_description=f"{day_word} um {hour:02d}:{minute:02d}",
            max_runs=1,
            remaining_text=remaining,
        )
    return None


def _parse_jeden_wochentag(lower: str, original: str, tz: str) -> Optional[ParsedTime]:
    """'jeden Montag um 9', 'jede Woche Freitag um 17 Uhr'"""
    day_pattern = "|".join(DAY_MAP.keys())
    m = re.search(
        rf"\b(?:jeden?|jede[mnrs]?)\s*(?:woche\s+)?({day_pattern})\s+um\s+(\d{{1,2}})(?::(\d{{2}}))?\s*(?:uhr)?\b",
        lower,
    )
    if m:
        day_key = m.group(1).lower()
        day_of_week = DAY_MAP.get(day_key)
        hour = int(m.group(2))
        minute = int(m.group(3) or 0)
        if day_of_week is None or hour > 23 or minute > 59:
            return None

        remaining = _strip_match(original, m)
        return ParsedTime(
            trigger_type="cron",
            trigger_config={"day_of_week": day_of_week, "hour": hour, "minute": minute},
            human_description=f"jeden {day_key.capitalize()} um {hour:02d}:{minute:02d}",
            max_runs=None,
            remaining_text=remaining,
        )
    return None


def _parse_taeglich(lower: str, original: str, tz: str) -> Optional[ParsedTime]:
    """'taeglich um 8', 'jeden Tag um 9'"""
    m = re.search(r"\b(?:t[aä]glich|jeden\s+tag)\s+um\s+(\d{1,2})(?::(\d{2}))?\s*(?:uhr)?\b", lower)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        if hour > 23 or minute > 59:
            return None

        remaining = _strip_match(original, m)
        return ParsedTime(
            trigger_type="cron",
            trigger_config={"hour": hour, "minute": minute},
            human_description=f"taeglich um {hour:02d}:{minute:02d}",
            max_runs=None,
            remaining_text=remaining,
        )
    return None


def _parse_alle_x(lower: str, original: str, tz: str) -> Optional[ParsedTime]:
    """'alle 2 Stunden', 'alle 30 Minuten', 'alle 5 Sekunden'"""
    m = re.search(
        r"\balle\s+(\d+|eine[mnr]?|zwei|drei|vier|f[uü]nf|sechs|sieben|acht|neun|zehn)"
        r"\s+(minuten?|stunden?|tagen?|sekunden?|wochen?)\b",
        lower,
    )
    if m:
        num = _parse_number(m.group(1))
        if num is None:
            return None
        unit = m.group(2)
        config = _unit_to_interval_config(num, unit)
        if config is None:
            return None

        remaining = _strip_match(original, m)
        return ParsedTime(
            trigger_type="interval",
            trigger_config=config,
            human_description=f"alle {num} {m.group(2).capitalize()}",
            max_runs=None,
            remaining_text=remaining,
        )
    return None


def _parse_stuendlich_woechentlich(lower: str, original: str, tz: str) -> Optional[ParsedTime]:
    """'stuendlich', 'woechentlich', 'minuetlich'"""
    patterns = {
        r"\bst[uü]ndlich\b": ({"hours": 1}, "stuendlich"),
        r"\bw[oö]chentlich\b": ({"weeks": 1}, "woechentlich"),
        r"\bmin[uü]tlich\b": ({"minutes": 1}, "minuetlich"),
        r"\bt[aä]glich\b(?!\s+um)": ({"days": 1}, "taeglich"),
    }
    for pattern, (config, desc) in patterns.items():
        m = re.search(pattern, lower)
        if m:
            remaining = _strip_match(original, m)
            return ParsedTime(
                trigger_type="interval",
                trigger_config=config,
                human_description=desc,
                max_runs=None,
                remaining_text=remaining,
            )
    return None


# =====================================================================
# Helpers
# =====================================================================

def _unit_to_timedelta(num: int, unit: str) -> Optional[timedelta]:
    """Convert German time unit to timedelta."""
    unit = unit.lower().rstrip("n").rstrip("e")
    if unit.startswith("minut"):
        return timedelta(minutes=num)
    elif unit.startswith("stund"):
        return timedelta(hours=num)
    elif unit.startswith("tag"):
        return timedelta(days=num)
    elif unit.startswith("sekund"):
        return timedelta(seconds=num)
    return None


def _unit_to_interval_config(num: int, unit: str) -> Optional[Dict[str, int]]:
    """Convert German time unit to APScheduler IntervalTrigger kwargs."""
    unit = unit.lower()
    if unit.startswith("minut"):
        return {"minutes": num}
    elif unit.startswith("stund"):
        return {"hours": num}
    elif unit.startswith("tag"):
        return {"days": num}
    elif unit.startswith("sekund"):
        return {"seconds": num}
    elif unit.startswith("woch"):
        return {"weeks": num}
    return None


def _strip_match(original: str, match: re.Match) -> str:
    """Remove the matched time expression from the original text."""
    before = original[:match.start()].strip()
    after = original[match.end():].strip()
    result = f"{before} {after}".strip()
    # Clean up common prefixes left behind
    for prefix in ["erinnere mich", "erinnere mich an", "erinner mich an",
                    "erinnere mich daran", "sag mir", "mach", "starte",
                    "an ", "dass ", "daran "]:
        if result.lower().startswith(prefix):
            result = result[len(prefix):].strip()
    # Clean up trailing/leading punctuation
    result = result.strip(" ,:;-–—")
    return result


# Ordered parser list (more specific patterns first)
_PARSERS = [
    _parse_morgen_um,
    _parse_jeden_wochentag,
    _parse_taeglich,
    _parse_alle_x,
    _parse_stuendlich_woechentlich,
    _parse_in_x_minutes,
    _parse_um_uhr,
]
