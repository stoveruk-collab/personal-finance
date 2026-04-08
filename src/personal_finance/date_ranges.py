from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date


MONTH_LOOKUP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date


def month_from_text(value: str) -> int:
    key = value.strip().lower()
    if key not in MONTH_LOOKUP:
        raise ValueError(f"Unsupported month value: {value}")
    return MONTH_LOOKUP[key]


def resolve_month_date_range(month: int, year: int, today: date | None = None) -> DateRange:
    current = today or date.today()
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date(year, month, last_day)

    if year == current.year and month == current.month:
        end = current
    elif start > current:
        raise ValueError("Cannot build a download range for a future month.")
    else:
        end = month_end

    return DateRange(start=start, end=end)


def resolve_period(period: str, year: int | None = None, today: date | None = None) -> tuple[int, int, DateRange]:
    current = today or date.today()
    cleaned = period.strip()

    if "-" in cleaned and len(cleaned) == 7:
        year_part, month_part = cleaned.split("-", 1)
        month = int(month_part)
        resolved_year = int(year_part)
    else:
        month = month_from_text(cleaned)
        resolved_year = year or current.year

    return resolved_year, month, resolve_month_date_range(month=month, year=resolved_year, today=current)

