import datetime as dt
import os
import sys
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nse_calendar import is_nse_equity_trading_day, latest_completed_nse_session


INDIA_TZ = ZoneInfo("Asia/Kolkata")


class NSECalendarTests(unittest.TestCase):
    def test_october_three_day_closure_resolves_to_thursday_session(self):
        self.assertTrue(is_nse_equity_trading_day(dt.date(2026, 10, 1)))
        self.assertFalse(is_nse_equity_trading_day(dt.date(2026, 10, 2)))
        self.assertFalse(is_nse_equity_trading_day(dt.date(2026, 10, 3)))
        self.assertFalse(is_nse_equity_trading_day(dt.date(2026, 10, 4)))
        self.assertEqual(
            latest_completed_nse_session(dt.datetime(2026, 10, 5, 1, 30, tzinfo=INDIA_TZ)),
            dt.date(2026, 10, 1),
        )

    def test_after_close_uses_today_but_holiday_friday_uses_thursday(self):
        self.assertEqual(
            latest_completed_nse_session(dt.datetime(2026, 10, 5, 16, 0, tzinfo=INDIA_TZ)),
            dt.date(2026, 10, 5),
        )
        self.assertEqual(
            latest_completed_nse_session(dt.datetime(2026, 10, 2, 20, 0, tzinfo=INDIA_TZ)),
            dt.date(2026, 10, 1),
        )

    def test_known_weekday_holiday_after_weekend_is_skipped(self):
        self.assertEqual(
            latest_completed_nse_session(dt.datetime(2026, 9, 14, 20, 0, tzinfo=INDIA_TZ)),
            dt.date(2026, 9, 11),
        )


if __name__ == "__main__":
    unittest.main()
