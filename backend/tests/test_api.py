import unittest

from app import create_app
from helpers import AppCase

GOOD = {"soil_moisture": 50, "temperature": 24, "humidity": 55, "light": 55}


class ValidationTests(AppCase):
    def custom(self, **overrides):
        values = dict(GOOD)
        values.update(overrides)
        return self.call("put", "/api/simulation/custom", json={"values": values})

    def test_valid_custom_values_accepted(self):
        self.assertEqual(self.custom().status_code, 200)

    def test_out_of_bounds_values_rejected_with_field_errors(self):
        cases = {"soil_moisture": (-1, 100.5), "temperature": (-10.5, 60.1), "humidity": (-0.1, 101), "light": (-5, 150)}
        for field, bad_values in cases.items():
            for bad in bad_values:
                r = self.custom(**{field: bad})
                self.assertEqual(r.status_code, 422, (field, bad))
                self.assertIn(field, r.get_json()["error"]["fields"])

    def test_bounds_are_inclusive(self):
        for field, (lo, hi) in {"soil_moisture": (0, 100), "temperature": (-10, 60), "humidity": (0, 100), "light": (0, 100)}.items():
            self.assertEqual(self.custom(**{field: lo}).status_code, 200)
            self.assertEqual(self.custom(**{field: hi}).status_code, 200)

    def test_non_numeric_missing_and_special_values_rejected(self):
        for bad in ("abc", None, True, [], {}, "", "NaN", "Infinity", float("inf")):
            r = self.custom(soil_moisture=bad)
            self.assertEqual(r.status_code, 422, repr(bad))
        r = self.call("put", "/api/simulation/custom", 422, json={"values": {"soil_moisture": 50}})
        self.assertEqual(set(r.get_json()["error"]["fields"]), {"temperature", "humidity", "light"})
        self.call("put", "/api/simulation/custom", 422, json={"values": dict(GOOD, pressure=5)})
        self.call("put", "/api/simulation/custom", 422, json={"values": "nope"})
        self.call("put", "/api/simulation/custom", 422, json={})

    def test_numeric_strings_are_accepted_and_invalid_reading_is_never_stored(self):
        self.assertEqual(self.custom(soil_moisture="42.5").status_code, 200)
        self.data("post", "/api/simulation/tick", 201)
        self.custom(soil_moisture=500)
        count = self.conn.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0]
        self.assertEqual(count, 1)

    def test_ingest_function_rejects_bad_input_and_unknown_source(self):
        from app.errors import ValidationError
        from app.ingestion import ingest_reading
        pid = self.plant_id("Tulsi")
        with self.assertRaises(ValidationError):
            ingest_reading(self.conn, pid, dict(GOOD, humidity=140))
        with self.assertRaises(ValidationError):
            ingest_reading(self.conn, pid, GOOD, source="satellite")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0], 0)

    def test_esp32_readings_would_be_marked_real_and_flow_through_the_same_path(self):
        from app.ingestion import ingest_reading
        result = ingest_reading(self.conn, self.plant_id("Tulsi"), GOOD, source="esp32")
        self.assertFalse(result["reading"]["is_simulated"])
        self.assertEqual(result["reading"]["source"], "esp32")

    def test_scenario_endpoint(self):
        self.assertEqual(self.data("put", "/api/simulation/scenario", json={"scenario": "dry_soil"})["scenario"], "dry_soil")
        multi = self.data("put", "/api/simulation/scenario", json={"scenario": "multiple", "problems": ["low_light", "dry_soil"]})
        self.assertEqual(multi["problems"], ["low_light", "dry_soil"])
        self.call("put", "/api/simulation/scenario", 422, json={"scenario": "multiple", "problems": ["low_light"]})
        self.call("put", "/api/simulation/scenario", 422, json={"scenario": "nope"})
        self.call("put", "/api/simulation/scenario", 422, json={"scenario": "custom"})
        self.call("put", "/api/simulation/scenario", 422, json={"scenario": "custom", "values": {"soil_moisture": 500, **{k: 1 for k in ("temperature", "humidity", "light")}}})
        custom = self.data("put", "/api/simulation/scenario", json={"scenario": "custom", "values": GOOD})
        self.assertEqual(custom["custom_values"]["soil_moisture"], 50)


class SettingsTests(AppCase):
    def test_defaults_update_and_persistence(self):
        body = self.data("get", "/api/settings")
        self.assertEqual(body["values"]["sampling_interval_seconds"], 5)
        self.assertIn("schema", body)
        updated = self.data("put", "/api/settings", json={"sampling_interval_seconds": 10, "display_name": "Asha",
                                                          "time_format": "12h", "trend_window": 8})
        self.assertEqual(updated["values"]["display_name"], "Asha")
        self.assertEqual(self.data("get", "/api/settings")["values"]["trend_window"], 8)

    def test_invalid_settings_rejected(self):
        bad = [{"sampling_interval_seconds": 0}, {"sampling_interval_seconds": 99999}, {"sampling_interval_seconds": "x"},
               {"alert_min_severity": "info"}, {"auto_resolve_alerts": "yes"}, {"default_date_range": "1y"},
               {"display_name": "  "}, {"trend_window": 2.5}, {"trend_window": 1}, {"unknown_key": 1},
               {"critical_margin_soil_moisture": -3}]
        for payload in bad:
            r = self.call("put", "/api/settings", 422, json=payload)
            self.assertTrue(r.get_json()["error"]["fields"], payload)

    def test_partial_update_is_atomic(self):
        self.call("put", "/api/settings", 422, json={"display_name": "OK", "sampling_interval_seconds": -1})
        self.assertEqual(self.data("get", "/api/settings")["values"]["display_name"], "Demo user")

    def test_global_settings_do_not_overwrite_plant_profiles(self):
        before = self.data("get", f"/api/plants/{self.plant_id('Money Plant')}")
        self.data("put", "/api/settings", json={"critical_margin_soil_moisture": 40, "default_date_range": "30d"})
        after = self.data("get", f"/api/plants/{self.plant_id('Money Plant')}")
        self.assertEqual(before, after)

    def test_changed_margin_changes_classification_immediately(self):
        pid = self.plant_id("Money Plant")
        self.ingest("Money Plant", soil=22)
        status = self.data("get", f"/api/plants/{pid}/status")
        self.assertEqual(status["classifications"]["soil_moisture"]["classification"], "low")
        self.data("put", "/api/settings", json={"critical_margin_soil_moisture": 5})
        status = self.data("get", f"/api/plants/{pid}/status")
        self.assertEqual(status["classifications"]["soil_moisture"]["classification"], "critical_low")


class ErrorResponseTests(AppCase):
    def test_consistent_error_shape(self):
        for method, url, code in [("get", "/api/plants/9999", 404), ("get", "/api/nothing", 404),
                                  ("patch", "/api/plants", 405), ("post", "/api/plants", 400)]:
            r = self.call(method, url, code)
            error = r.get_json()["error"]
            self.assertIn("code", error)
            self.assertIn("message", error)

    def test_malformed_and_wrong_type_bodies(self):
        r = self.call("post", "/api/plants", 400, data="{not json", content_type="application/json")
        self.assertEqual(r.get_json()["error"]["code"], "invalid_json")
        self.call("post", "/api/plants", 400, json=[1, 2])
        self.call("put", "/api/settings", 400, data="x", content_type="text/plain")
        self.call("put", f"/api/plants/{self.plant_id('Tulsi')}", 400, json="text")

    def test_non_integer_path_ids_are_not_found(self):
        self.call("get", "/api/plants/abc", 404)
        self.call("delete", "/api/plants/abc", 404)

    def test_missing_resources(self):
        for method, url in [("put", "/api/plants/9999"), ("delete", "/api/plants/9999"),
                            ("get", "/api/plants/9999/status"), ("get", "/api/plants/9999/readings/latest"),
                            ("get", "/api/plants/9999/recommendations")]:
            self.call(method, url, 404, json={})

    def test_success_responses_use_data_envelope(self):
        for url in ("/api/health", "/api/meta", "/api/plants", "/api/settings", "/api/simulation", "/api/alerts"):
            self.assertIn("data", self.data("get", url) and self.call("get", url).get_json())

    def test_health_and_meta(self):
        health = self.data("get", "/api/health")
        self.assertEqual((health["status"], health["database"], health["data_source"]), ("ok", "ok", "simulator"))
        meta = self.data("get", "/api/meta")
        self.assertEqual(len(meta["scenarios"]), 7)
        self.assertEqual(list(meta["sensors"]), ["soil_moisture", "temperature", "humidity", "light"])
        self.assertNotIn("lux", meta["sensors"]["light"]["unit"].lower())

    def test_cors_allows_only_the_local_frontend_origins(self):
        ok = self.client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(ok.headers.get("Access-Control-Allow-Origin"), "http://localhost:5173")
        other = self.client.get("/api/health", headers={"Origin": "https://evil.example"})
        self.assertIsNone(other.headers.get("Access-Control-Allow-Origin"))
        self.assertNotEqual(ok.headers.get("Access-Control-Allow-Origin"), "*")


class WorkflowAndPersistenceTests(AppCase):
    """The ten-step workflow from the specification, plus restart persistence."""

    def test_full_workflow(self):
        # 1. create a plant and select it
        fern = self.data("post", "/api/plants", 201, json=self.plant_payload())
        self.data("put", "/api/plants/active", json={"plant_id": fern["id"]})
        # 2. start a simulation (dry soil scenario)
        self.data("put", "/api/settings", json={"sampling_interval_seconds": 60})
        self.data("put", "/api/simulation/scenario", json={"scenario": "dry_soil"})
        self.assertEqual(self.data("post", "/api/simulation/start")["state"], "running")
        # 3-4. generate readings, validated and stored
        for _ in range(3):
            self.data("post", "/api/simulation/tick", 201)
        # moisture is still on its way down: the trend shows it
        self.assertEqual(self.data("get", f"/api/plants/{fern['id']}/status")["trends"]["soil_moisture"]["direction"], "falling")
        for _ in range(9):
            self.data("post", "/api/simulation/tick", 201)
        latest = self.data("get", f"/api/plants/{fern['id']}/readings/latest")["reading"]
        self.assertEqual(latest["plant_id"], fern["id"])
        self.assertTrue(latest["is_simulated"])
        # 5-6. analysis, recommendation and alert
        status = self.data("get", f"/api/plants/{fern['id']}/status")
        self.assertEqual(status["health"]["status"], "needs_attention")
        self.assertEqual(status["recommendations"][0]["rule_id"], "soil_moisture_low")
        alerts = self.data("get", f"/api/alerts?plant_id={fern['id']}&status=active")["alerts"]
        self.assertEqual([a["alert_type"] for a in alerts], ["soil_moisture_low"])
        self.assertEqual(status["alert_counts"]["active_warning"], 1)
        # 7. dashboard data: latest reading, thresholds and trends are all present
        self.assertEqual(set(status["trends"]), {"soil_moisture", "temperature", "humidity", "light"})
        # 8. history for charts
        history = self.data("get", f"/api/plants/{fern['id']}/readings?range=today")
        self.assertEqual(history["count"], 13)
        # 9. switching plants never mixes records
        other = self.plant_id("Tulsi")
        self.data("put", "/api/plants/active", json={"plant_id": other})
        self.assertEqual(self.data("get", f"/api/plants/{other}/readings?range=today")["count"], 0)
        self.assertFalse(self.data("get", f"/api/plants/{other}/status")["has_data"])
        self.assertEqual(self.data("get", f"/api/alerts?plant_id={other}")["alerts"], [])
        self.assertEqual(self.data("get", f"/api/plants/{fern['id']}/readings?range=today")["count"], 13)
        self.data("post", "/api/simulation/tick", 201)   # simulation now follows the new active plant
        self.assertEqual(self.data("get", f"/api/plants/{other}/readings?range=today")["count"], 1)
        self.assertEqual(self.data("get", f"/api/plants/{fern['id']}/readings?range=today")["count"], 13)
        self.data("post", "/api/simulation/stop")

    def test_data_survives_application_restart(self):
        pid = self.plant_id("Money Plant")
        self.data("put", "/api/plants/active", json={"plant_id": pid})
        self.data("put", "/api/settings", json={"sampling_interval_seconds": 60, "display_name": "Persisted"})
        self.data("put", "/api/simulation/scenario", json={"scenario": "multiple", "problems": ["dry_soil", "low_light"]})
        self.data("post", "/api/simulation/start")
        for _ in range(8):
            self.data("post", "/api/simulation/tick", 201)
        before_alerts = self.data("get", "/api/alerts")["alerts"]
        before_status = self.data("get", f"/api/plants/{pid}/status")
        self.sim.shutdown()

        restarted = create_app(self.db_path)
        client = restarted.test_client()
        get = lambda url: client.get(url).get_json()["data"]
        self.assertEqual(get("/api/plants/active")["active_plant_id"], pid)
        self.assertEqual(get(f"/api/plants/{pid}/readings?range=today")["count"], 9)
        self.assertEqual(get("/api/settings")["values"]["display_name"], "Persisted")
        self.assertEqual(len(get("/api/plants")["plants"]), 4)
        self.assertEqual([a["id"] for a in get("/api/alerts")["alerts"]], [a["id"] for a in before_alerts])
        self.assertEqual(get(f"/api/plants/{pid}/status")["latest_reading"], before_status["latest_reading"])
        sim = get("/api/simulation")
        self.assertEqual(sim["state"], "stopped")                 # a restart never silently resumes the worker
        self.assertFalse(sim["worker_alive"])
        self.assertEqual((sim["scenario"], sim["problems"]), ("multiple", ["dry_soil", "low_light"]))
        # the simulation continues from the stored history, not from scratch
        before_last = before_status["latest_reading"]["soil_moisture"]
        new = client.post("/api/simulation/tick").get_json()["data"]["reading"]
        self.assertLessEqual(abs(new["soil_moisture"] - before_last), 5.5)
        restarted.extensions["simulation"].shutdown()


if __name__ == "__main__":
    unittest.main()
