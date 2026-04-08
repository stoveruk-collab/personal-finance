from datetime import date

from personal_finance.date_ranges import resolve_month_date_range, resolve_period


def test_current_month_uses_today_as_end_date():
    result = resolve_month_date_range(month=4, year=2026, today=date(2026, 4, 7))
    assert result.start == date(2026, 4, 1)
    assert result.end == date(2026, 4, 7)


def test_past_month_uses_calendar_month_end():
    result = resolve_month_date_range(month=3, year=2026, today=date(2026, 4, 7))
    assert result.start == date(2026, 3, 1)
    assert result.end == date(2026, 3, 31)


def test_period_text_uses_supplied_year():
    year, month, result = resolve_period("April", year=2026, today=date(2026, 4, 7))
    assert (year, month) == (2026, 4)
    assert result.start == date(2026, 4, 1)
    assert result.end == date(2026, 4, 7)

