import unittest
from datetime import datetime, timedelta, timezone

from app.analytics import resolve_range
from app.db import to_iso
from app.errors import ValidationError
from helpers import AppCase

MONEY = "Money Plant"


def ago(**kw):
    return to_iso(datetime.now(timezone.utc) - timedelta(**kw))


class RangeTests(unittest.TestCase):
    def test_presets_and_custom(self):
        for key in ("today", "7d", "30d"):
            start, end, label = resolve_range(key)
            self.assertLess(start, end)
            self.assertEqual(label, key)
        s, e, label = resolve_range(None, "2026-01-01", "2026-01-31")
        self.assertEqual(label, "custom")
        self.assertLess(s, e)

    def test_date_only_end_is_inclusive_of_the_whole_day(self):
        s, e, _ = resolve_range(None, "2026-03-05", "2026-03-05")
        self.assertGreater(datetime.fromisoformat(e.replace("Z", "+00:00")) - datetime.fromisoformat(s.replace("Z", "+00:00")),
                           timedelta(hours=23))

    def test_invalid_ranges(self):
        for args in [("yesterday", None, None), (None, "2026-02-01", "2026-01-01"), (None, "nonsense", None),
                     (None, None, "2026-01-01"), (None, "2020-01-01", "2026-01-01"), (None, "2026-13-45", None)]:
            with self.assertRaises(ValidationError, msg=args):
                resolve_range(*args)


class AnalyticsTests(AppCase):
    def seed_readings(self):
        # Five readings at known times for Money Plant: 3 days old, 2 days old, 2 x today-ish, 40 days old
        self.ingest(MONEY, soil=50, temp=20, recorded_at=ago(days=40))
        self.ingest(MONEY, soil=45, temp=22, recorded_at=ago(days=3))
        self.ingest(MONEY, soil=30, temp=26, recorded_at=ago(days=2))
        self.ingest(MONEY, soil=20, temp=34, recorded_at=ago(minutes=30))
        self.ingest(MONEY, soil=10, temp=36, recorded_at=ago(minutes=10))
        self.pid = self.plant_id(MONEY)

    def summary(self, query):
        return self.data("get", f"/api/analytics/summary?plant_id={self.pid}&{query}")

    def test_min_max_avg_and_counts_per_period(self):
        self.seed_readings()
        s30 = self.summary("range=30d")
        self.assertEqual(s30["reading_count"], 4)          # the 40-day-old reading is outside 30d
        moisture = s30["sensors"]["soil_moisture"]
        self.assertEqual((moisture["min"], moisture["max"]), (10, 45))
        self.assertAlmostEqual(moisture["avg"], (45 + 30 + 20 + 10) / 4)
        s7 = self.summary("range=7d")
        self.assertEqual(s7["reading_count"], 4)
        today = self.summary("range=today")
        self.assertEqual(today["reading_count"], 2)
        self.assertEqual(today["sensors"]["soil_moisture"]["max"], 20)

    def test_custom_range_filters_by_date(self):
        self.seed_readings()
        day = (datetime.now(timezone.utc) - timedelta(days=3)).astimezone().strftime("%Y-%m-%d")
        s = self.summary(f"from={day}&to={day}")
        self.assertEqual(s["reading_count"], 1)
        self.assertEqual(s["sensors"]["soil_moisture"]["min"], 45)

    def test_trend_summary(self):
        self.seed_readings()
        s = self.summary("range=30d")
        self.assertEqual(s["sensors"]["soil_moisture"]["trend"], "falling")
        self.assertEqual(s["sensors"]["temperature"]["trend"], "rising")
        self.assertEqual(s["sensors"]["soil_moisture"]["change"], -35)

    def test_condition_alert_health_and_recommendation_summaries(self):
        self.seed_readings()
        s = self.summary("range=30d")
        self.assertEqual(sum(s["conditions"]["soil_moisture"].values()), 4)
        self.assertEqual(s["conditions"]["soil_moisture"]["normal"], 1)
        self.assertEqual(s["conditions"]["soil_moisture"]["low"], 2)
        self.assertEqual(s["conditions"]["soil_moisture"]["critical_low"], 1)
        self.assertEqual(sum(s["health"].values()), 4)
        self.assertEqual(s["alerts"]["by_severity"]["critical"] + s["alerts"]["by_severity"]["warning"], s["alerts"]["total"])
        self.assertGreaterEqual(s["alerts"]["total"], 2)
        self.assertEqual(s["alerts"]["active"] + s["alerts"]["resolved"], s["alerts"]["total"])
        rules = {r["rule_id"]: r for r in s["recommendations"]}
        self.assertEqual(rules["soil_moisture_low"]["readings"], 2)
        self.assertEqual(rules["soil_moisture_low"]["category"], "watering")
        self.assertIn("Watering recommended", rules["soil_moisture_low"]["title"])
        self.assertNotIn("soil_moisture_normal", rules)   # informational notes are not counted
        self.assertEqual(s["data_source"], "simulated")

    def test_empty_period_returns_clear_empty_summary(self):
        s = self.data("get", f"/api/analytics/summary?plant_id={self.plant_id(MONEY)}&range=7d")
        self.assertFalse(s["has_data"])
        self.assertEqual(s["reading_count"], 0)
        self.assertIsNone(s["sensors"]["soil_moisture"]["min"])
        self.assertEqual(s["recommendations"], [])
        history = self.data("get", f"/api/plants/{self.plant_id(MONEY)}/readings?range=7d")
        self.assertEqual((history["points"], history["count"]), ([], 0))

    def test_history_is_ordered_scoped_to_plant_and_range(self):
        self.seed_readings()
        self.ingest("Tulsi", soil=60, recorded_at=ago(minutes=5))
        h = self.data("get", f"/api/plants/{self.pid}/readings?range=30d")
        self.assertEqual(h["count"], 4)
        times = [p["recorded_at"] for p in h["points"]]
        self.assertEqual(times, sorted(times))
        self.assertEqual({p["soil_moisture"] for p in h["points"]}, {45, 30, 20, 10})
        self.assertEqual(h["data_source"], "simulated")

    def test_history_downsamples_large_ranges(self):
        for i in range(60):
            self.ingest(MONEY, soil=40 + (i % 10), recorded_at=ago(minutes=100 - i))
        h = self.data("get", f"/api/plants/{self.plant_id(MONEY)}/readings?range=today&max_points=20")
        self.assertTrue(h["downsampled"])
        self.assertEqual(h["count"], 60)
        self.assertLessEqual(len(h["points"]), 20)

    def test_invalid_analytics_requests(self):
        self.call("get", "/api/analytics/summary", 422)                           # missing plant_id
        self.call("get", "/api/analytics/summary?plant_id=abc", 422)
        self.call("get", "/api/analytics/summary?plant_id=9999", 404)
        pid = self.plant_id(MONEY)
        self.call("get", f"/api/analytics/summary?plant_id={pid}&range=forever", 422)
        self.call("get", f"/api/analytics/summary?plant_id={pid}&from=2026-02-01&to=2026-01-01", 422)
        self.call("get", f"/api/analytics/summary?plant_id={pid}&from=garbage", 422)
        self.call("get", f"/api/plants/{pid}/readings?range=bad", 422)
        self.call("get", f"/api/plants/{pid}/readings?max_points=1", 422)
        self.call("get", "/api/plants/9999/readings", 404)

    def test_default_range_comes_from_settings(self):
        self.seed_readings()
        self.data("put", "/api/settings", json={"default_date_range": "today"})
        self.assertEqual(self.data("get", f"/api/analytics/summary?plant_id={self.pid}")["reading_count"], 2)

    def test_report_identifies_data_as_simulated(self):
        self.seed_readings()
        report = self.data("get", f"/api/analytics/report?plant_id={self.pid}&range=30d")
        self.assertEqual(report["data_source"], "simulated")
        headings = [s["heading"] for s in report["sections"]]
        for expected in ("Overview", "Environmental trends", "Condition classifications", "Alerts", "Recommendations", "Notes"):
            self.assertIn(expected, headings)
        self.assertIn("SIMULATED", report["markdown"])
        self.assertIn("Money Plant", report["markdown"])
        self.assertIn("advisory", report["markdown"].lower())

    def test_report_for_empty_period(self):
        report = self.data("get", f"/api/analytics/report?plant_id={self.plant_id('Tulsi')}&range=today")
        self.assertIn("No data", [s["heading"] for s in report["sections"]])
        self.assertIn("SIMULATED", report["markdown"])


if __name__ == "__main__":
    unittest.main()
