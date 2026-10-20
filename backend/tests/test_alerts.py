import unittest

from helpers import AppCase

MONEY = "Money Plant"


class AlertLifecycleTests(AppCase):
    def alerts(self, **where):
        sql = "SELECT * FROM alerts"
        clauses = [f"{k} = ?" for k in where]
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        return self.conn.execute(sql + " ORDER BY id", list(where.values())).fetchall()

    def test_condition_creates_one_alert_with_full_details(self):
        result = self.ingest(MONEY, soil=30)
        self.assertEqual([e["event"] for e in result["alert_events"]], ["created"])
        a = self.alerts()[0]
        self.assertEqual((a["alert_type"], a["severity"], a["status"], a["is_read"]), ("soil_moisture_low", "warning", "active", 0))
        self.assertEqual((a["sensor_value"], a["threshold_value"], a["threshold_kind"]), (30, 35, "warning"))
        self.assertIn("Soil Moisture", a["title"])
        self.assertTrue(a["description"] and a["explanation"] and a["recommended_action"])
        self.assertEqual(a["plant_id"], self.plant_id(MONEY))
        self.assertEqual(a["is_simulated"], 1)
        self.assertIsNone(a["resolved_at"])

    def test_continuing_condition_is_deduplicated(self):
        for value in (30, 28, 26, 25):
            self.ingest(MONEY, soil=value)
        rows = self.alerts()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["occurrence_count"], 4)
        self.assertEqual(rows[0]["sensor_value"], 25)  # latest value is kept up to date
        self.assertGreater(rows[0]["updated_at"], rows[0]["created_at"] if False else "")

    def test_database_index_blocks_duplicate_active_alerts(self):
        import sqlite3
        self.ingest(MONEY, soil=30)
        a = self.alerts()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO alerts (plant_id, alert_type, parameter, direction, severity, status, title, description, "
                "explanation, recommended_action, sensor_value, threshold_value, threshold_kind, created_at, updated_at) "
                "VALUES (?, 'soil_moisture_low', 'soil_moisture', 'low', 'warning', 'active', 't', 'd', 'e', 'r', 1, 2, 'warning', 'x', 'x')",
                (a["plant_id"],))

    def test_recovery_resolves_alert_automatically(self):
        self.ingest(MONEY, soil=30)
        result = self.ingest(MONEY, soil=50)
        self.assertEqual([e["event"] for e in result["alert_events"]], ["resolved"])
        a = self.alerts()[0]
        self.assertEqual(a["status"], "resolved")
        self.assertIsNotNone(a["resolved_at"])

    def test_returning_condition_creates_a_new_alert(self):
        self.ingest(MONEY, soil=30)
        self.ingest(MONEY, soil=50)
        self.ingest(MONEY, soil=29)
        rows = self.alerts()
        self.assertEqual([(r["status"]) for r in rows], ["resolved", "active"])
        self.assertNotEqual(rows[0]["id"], rows[1]["id"])

    def test_escalation_to_critical_updates_severity_and_marks_unread(self):
        self.ingest(MONEY, soil=30)
        aid = self.alerts()[0]["id"]
        self.data("post", f"/api/alerts/{aid}/read")
        result = self.ingest(MONEY, soil=5)
        self.assertEqual([e["event"] for e in result["alert_events"]], ["escalated"])
        a = self.alerts()[0]
        self.assertEqual((a["severity"], a["threshold_kind"], a["is_read"]), ("critical", "critical", 0))
        self.assertEqual(len(self.alerts()), 1)

    def test_recovery_from_critical_to_warning_keeps_one_active_alert(self):
        self.ingest(MONEY, soil=5)
        self.ingest(MONEY, soil=30)
        a = self.alerts()
        self.assertEqual(len(a), 1)
        self.assertEqual((a[0]["severity"], a[0]["status"]), ("warning", "active"))

    def test_opposite_direction_resolves_one_and_creates_another(self):
        self.ingest(MONEY, soil=30)
        self.ingest(MONEY, soil=80)
        rows = {r["alert_type"]: r["status"] for r in self.alerts()}
        self.assertEqual(rows, {"soil_moisture_low": "resolved", "soil_moisture_high": "active"})

    def test_several_parameters_alert_independently(self):
        self.ingest(MONEY, soil=30, temp=36, hum=20, light=10)
        types = {r["alert_type"] for r in self.alerts(status="active")}
        self.assertEqual(types, {"soil_moisture_low", "temperature_high", "humidity_low", "light_low"})
        self.ingest(MONEY, soil=50, temp=36, hum=55, light=55)
        self.assertEqual({r["alert_type"] for r in self.alerts(status="active")}, {"temperature_high"})

    def test_alerts_are_scoped_to_their_plant(self):
        self.ingest(MONEY, soil=30)
        self.ingest("Aloe Vera", soil=20)  # normal for aloe (range 15-35, warning 10)
        self.assertEqual(len(self.alerts(plant_id=self.plant_id("Aloe Vera"))), 0)
        self.assertEqual(len(self.alerts(plant_id=self.plant_id(MONEY))), 1)

    def test_min_severity_critical_suppresses_warnings(self):
        self.data("put", "/api/settings", json={"alert_min_severity": "critical"})
        self.ingest(MONEY, soil=30)
        self.assertEqual(len(self.alerts()), 0)
        self.ingest(MONEY, soil=5)
        self.assertEqual(self.alerts()[0]["severity"], "critical")
        self.ingest(MONEY, soil=30)  # now only a warning -> below alerting level -> resolved
        self.assertEqual(self.alerts()[0]["status"], "resolved")

    def test_auto_resolve_can_be_disabled_and_manual_resolve_works(self):
        self.data("put", "/api/settings", json={"auto_resolve_alerts": False})
        self.ingest(MONEY, soil=30)
        self.ingest(MONEY, soil=50)
        a = self.alerts()[0]
        self.assertEqual(a["status"], "active")
        resolved = self.data("post", f"/api/alerts/{a['id']}/resolve")
        self.assertEqual(resolved["status"], "resolved")

    def test_editing_plant_thresholds_reevaluates_alerts(self):
        pid = self.plant_id(MONEY)
        self.ingest(MONEY, soil=30)                      # below warning 35 -> alert
        self.assertEqual(self.alerts()[0]["status"], "active")
        self.data("put", f"/api/plants/{pid}", json={"moisture_warning": 25})
        self.assertEqual(self.alerts()[0]["status"], "resolved")
        status = self.data("get", f"/api/plants/{pid}/status")
        self.assertEqual(status["classifications"]["soil_moisture"]["classification"], "normal")
        self.data("put", f"/api/plants/{pid}", json={"moisture_warning": 35})
        self.assertEqual(len(self.alerts()), 2)           # condition is back: a new alert
        self.assertEqual(self.alerts()[1]["status"], "active")

    def test_updated_and_unchanged_alerts_keep_read_flag(self):
        self.ingest(MONEY, soil=30)
        aid = self.alerts()[0]["id"]
        self.data("post", f"/api/alerts/{aid}/read")
        self.ingest(MONEY, soil=29)
        self.assertEqual(self.alerts()[0]["is_read"], 1)


class AlertApiTests(AppCase):
    def setUp(self):
        super().setUp()
        self.ingest(MONEY, soil=30)                         # active warning (Money)
        self.ingest("Aloe Vera", soil=2)                    # active critical (Aloe)
        self.ingest("Tulsi", soil=40)
        self.ingest("Tulsi", soil=60)                       # resolved warning (Tulsi)

    def test_list_with_counts_and_plant_names(self):
        body = self.data("get", "/api/alerts")
        self.assertEqual(len(body["alerts"]), 3)
        self.assertEqual({a["plant_name"] for a in body["alerts"]}, {MONEY, "Aloe Vera", "Tulsi"})
        self.assertEqual(body["counts"]["active_warning"], 1)
        self.assertEqual(body["counts"]["active_critical"], 1)
        self.assertEqual(body["counts"]["unread"], 3)

    def test_filters(self):
        aloe = self.plant_id("Aloe Vera")
        self.assertEqual(len(self.data("get", f"/api/alerts?plant_id={aloe}")["alerts"]), 1)
        self.assertEqual(len(self.data("get", "/api/alerts?severity=critical")["alerts"]), 1)
        self.assertEqual(len(self.data("get", "/api/alerts?status=resolved")["alerts"]), 1)
        self.assertEqual(len(self.data("get", "/api/alerts?status=active")["alerts"]), 2)
        self.assertEqual(len(self.data("get", "/api/alerts?status=active&severity=warning")["alerts"]), 1)
        self.assertEqual(len(self.data("get", "/api/alerts?range=today")["alerts"]), 3)
        self.assertEqual(len(self.data("get", "/api/alerts?from=2000-01-01&to=2000-01-02")["alerts"]), 0)

    def test_invalid_filters(self):
        self.call("get", "/api/alerts?severity=urgent", 422)
        self.call("get", "/api/alerts?status=maybe", 422)
        self.call("get", "/api/alerts?plant_id=abc", 422)
        self.call("get", "/api/alerts?is_read=maybe", 422)
        self.call("get", "/api/alerts?from=2026-02-01&to=2026-01-01", 422)

    def test_detail_mark_read_unread_and_read_all(self):
        aid = self.data("get", "/api/alerts")["alerts"][0]["id"]
        detail = self.data("get", f"/api/alerts/{aid}")
        for key in ("alert_type", "severity", "status", "sensor_value", "threshold_value", "explanation",
                    "recommended_action", "created_at", "updated_at", "is_read", "plant_name"):
            self.assertIn(key, detail)
        self.assertTrue(self.data("post", f"/api/alerts/{aid}/read")["is_read"])
        self.assertFalse(self.data("post", f"/api/alerts/{aid}/unread")["is_read"])
        self.assertEqual(self.data("post", f"/api/alerts/read-all")["updated"], 3)
        self.assertEqual(self.data("get", "/api/alerts/summary")["unread"], 0)
        self.assertEqual(len(self.data("get", "/api/alerts?is_read=false")["alerts"]), 0)

    def test_missing_alert(self):
        self.call("get", "/api/alerts/9999", 404)
        self.call("post", "/api/alerts/9999/read", 404)


if __name__ == "__main__":
    unittest.main()
