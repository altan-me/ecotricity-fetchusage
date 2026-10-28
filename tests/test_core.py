"""Tests for the risky paths: parsing, date presets, backfill gaps, money."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import database
import ecotricity


class ParseValuesTest(unittest.TestCase):
    def test_maps_period_start_and_weekday(self):
        data = {
            "indicatorValueResponses": [{
                "featureValueResponses": [{
                    "values": [
                        {"value": 1.5, "measuringPeriod": {
                            "2026-03-15T00:00:00.000+13:00":
                            "2026-03-16T00:00:00.000+13:00"}},
                        {"value": 2.0, "measuringPeriod": {
                            "2026-03-16T00:00:00.000+13:00":
                            "2026-03-17T00:00:00.000+13:00"}},
                    ]
                }]
            }]
        }
        self.assertEqual(ecotricity.parse_values(data), [
            {"date": "2026-03-15", "weekday": "Sun", "value": 1.5},
            {"date": "2026-03-16", "weekday": "Mon", "value": 2.0},
        ])

    def test_empty_response(self):
        self.assertEqual(ecotricity.parse_values({}), [])


class DateRangeTest(unittest.TestCase):
    def setUp(self):
        self._portal_now = ecotricity.portal_now
        self._timezone = ecotricity.PORTAL_TIMEZONE
        ecotricity.PORTAL_TIMEZONE = timezone.utc
        ecotricity.portal_now = lambda: datetime(2026, 3, 15, 10, 0)

    def tearDown(self):
        ecotricity.portal_now = self._portal_now
        ecotricity.PORTAL_TIMEZONE = self._timezone

    def test_last_7_days_is_a_week_window(self):
        self.assertEqual(ecotricity.calculate_date_range("last 7 days"), (
            "2026-03-08T00:00:00.000+00:00",
            "2026-03-15T00:00:00.000+00:00",
            "WEEK",
        ))

    def test_last_month_covers_previous_calendar_month(self):
        self.assertEqual(ecotricity.calculate_date_range("last month"), (
            "2026-02-01T00:00:00.000+00:00",
            "2026-03-01T00:00:00.000+00:00",
            "MONTH",
        ))

    def test_unknown_preset_stops(self):
        with self.assertRaises(SystemExit):
            ecotricity.calculate_date_range("since forever")


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self._db_path = database.DB_PATH
        self._tmp = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self._tmp.name) / "test.db"
        database.init_db()

    def tearDown(self):
        database.DB_PATH = self._db_path
        self._tmp.cleanup()


class BackfillRangeTest(DatabaseTestCase):
    def test_groups_consecutive_missing_days(self):
        database.insert_consumption_data([
            {"date": "2026-01-01", "weekday": "Thu", "value": 1.0},
            {"date": "2026-01-05", "weekday": "Mon", "value": 1.0},
        ])
        self.assertEqual(
            database.get_missing_date_ranges("2026-01-01", "2026-01-05"),
            [("2026-01-02", "2026-01-04")],
        )

    def test_recent_failure_is_not_retried(self):
        database.record_fetch_attempt("2026-01-03", success=False,
                                      error_message="no data")
        self.assertEqual(
            database.get_missing_date_ranges("2026-01-01", "2026-01-03"), [])

    def test_later_success_clears_failure(self):
        database.record_fetch_attempt("2026-01-03", success=False)
        database.record_fetch_attempt("2026-01-03", success=True)
        self.assertEqual(
            database.get_missing_date_ranges("2026-01-01", "2026-01-03"),
            [("2026-01-01", "2026-01-03")],
        )


class StatisticsTest(DatabaseTestCase):
    def test_all_time_includes_data_older_than_a_year(self):
        old = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        database.insert_consumption_data([
            {"date": old, "weekday": "Mon", "value": 1.0},
            {"date": today, "weekday": "Thu", "value": 2.0},
        ])
        self.assertEqual(database.get_statistics(days=None)["count"], 2)
        self.assertEqual(database.get_statistics(days=365)["count"], 1)

    def test_cost_includes_gst(self):
        self.assertAlmostEqual(database.calculate_cost(10), 2.44375)


if __name__ == "__main__":
    unittest.main()
