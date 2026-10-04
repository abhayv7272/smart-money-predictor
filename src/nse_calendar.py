"""Small, explicit NSE cash/equity trading calendar helpers.

The 2026 weekday holidays are transcribed from NSE circular NSE/CMTR/71775
(12 Dec 2025). Add each new year's official NSE calendar here when published;
weekends are excluded for all years.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

INDIA_TZ = ZoneInfo("Asia/Kolkata")
NSE_MARKET_CLOSE = time(15, 30)

# NSE Capital Market / Equity Segment full-day weekday closures for calendar 2026.
# Source: NSE circular NSE/CMTR/71775, "Trading holidays for calendar year 2026".
NSE_EQUITY_HOLIDAYS = {
    2026: frozenset(
        date.fromisoformat(value)
        for value in (
            "2026-01-26",  # Republic Day
            "2026-03-03",  # Holi
            "2026-03-26",  # Shri Ram Navami
            "2026-03-31",  # Shri Mahavir Jayanti
            "2026-04-03",  # Good Friday
            "2026-04-14",  # Dr. Baba Saheb Ambedkar Jayanti
            "2026-05-01",  # Maharashtra Day
            "2026-05-28",  # Bakri Id
            "2026-06-26",  # Muharram
            "2026-09-14",  # Ganesh Chaturthi
            "2026-10-02",  # Mahatma Gandhi Jayanti
            "2026-10-20",  # Dussehra
            "2026-11-10",  # Diwali-Balipratipada
            "2026-11-24",  # Prakash Gurpurb Sri Guru Nanak Dev
            "2026-12-25",  # Christmas
        )
    ),
}


def is_nse_equity_trading_day(day: date) -> bool:
    """Return whether `day` is a regular NSE equity trading session."""
    if isinstance(day, datetime):
        day = day.date()
    return day.weekday() < 5 and day not in NSE_EQUITY_HOLIDAYS.get(day.year, frozenset())


def latest_completed_nse_session(now: datetime | None = None) -> date:
    """Return the last completed NSE equity session in India local time.

    Before the normal 15:30 IST close, today's session is not yet complete. After
    close, a weekday holiday, or a weekend, walk backward over both holidays and
    weekends to the last valid exchange session.
    """
    current = now or datetime.now(INDIA_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=INDIA_TZ)
    else:
        current = current.astimezone(INDIA_TZ)

    candidate = current.date()
    if current.time().replace(tzinfo=None) < NSE_MARKET_CLOSE:
        candidate -= timedelta(days=1)
    while not is_nse_equity_trading_day(candidate):
        candidate -= timedelta(days=1)
    return candidate
