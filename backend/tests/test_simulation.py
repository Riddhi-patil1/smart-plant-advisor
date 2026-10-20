import random
import threading
import time
import unittest

from app import advisory
from app.errors import ConflictError, ValidationError
from app.simulation_model import SimulationModel
from helpers import AppCase, example_plant
from app.settings import DEFAULTS

PLANTS = ("Money Plant", "Aloe Vera", "Tulsi", "Snake Plant")


def run_model(plant_name, scenario, ticks=40, seed=7, **kwargs):
    ths = advisory.thresholds(example_plant(plant_name), DEFAULTS)
    model = SimulationModel(random.Random(seed))
    model.set_scenario(scenario, **kwargs)
    series = [model.next_values(ths) for _ in range(ticks)]
    return ths, series


def classes(ths, values):
    return advisory.classify_all(values, ths)


class ScenarioTests(unittest.TestCase):
    def test_normal_stays_inside_preferred_ranges_for_every_plant(self):
        for name in PLANTS:
            ths, series = run_model(name, "normal", ticks=150)
            for values in series:
                for p, c in classes(ths, values).items():
                    self.assertEqual(c["classification"], "normal", (name, p, values))
                    self.assertTrue(c["in_preferred_range"], (name, p, values))
            # values actually change over time
            self.assertGreater(len({v["soil_moisture"] for v in series}), 5)

    def test_dry_soil_declines_gradually_then_stays_below_warning(self):
        for name in PLANTS:
            ths, series = run_model(name, "dry_soil")
            moisture = [v["soil_moisture"] for v in series]
            warn = ths["soil_moisture"]["warn_low"]
            self.assertGreaterEqual(moisture[0], warn, "first reading should not already be a jump below threshold")
            self.assertLess(moisture[-1], warn)
            self.assertTrue(all(m < warn for m in moisture[-10:]), name)
            self.assertLess(moisture[-1], moisture[0])
            steps = [b - a for a, b in zip(moisture, moisture[1:])]
            self.assertLessEqual(max(steps), 1.0, "only noise-sized upward moves")
            self.assertGreaterEqual(min(steps), -4.9, "gradual decline, not a jump")
            # other sensors remain normal
            end = classes(ths, series[-1])
            self.assertEqual(end["temperature"]["classification"], "normal")

    def test_high_temperature_rises_above_threshold(self):
        for name in PLANTS:
            ths, series = run_model(name, "high_temperature")
            temps = [v["temperature"] for v in series]
            self.assertLessEqual(temps[0], ths["temperature"]["warn_high"])
            self.assertTrue(all(t > ths["temperature"]["warn_high"] for t in temps[-10:]), name)
            self.assertLessEqual(max(temps), 60)

    def test_low_humidity_and_low_light(self):
        for name in PLANTS:
            ths, series = run_model(name, "low_humidity")
            self.assertTrue(all(v["humidity"] < ths["humidity"]["pref_min"] for v in series[-10:]), name)
            ths, series = run_model(name, "low_light")
            self.assertTrue(all(v["light"] < ths["light"]["pref_min"] for v in series[-10:]), name)

    def test_multiple_problems_combine_the_selected_issues(self):
        ths, series = run_model("Money Plant", "multiple", problems=["dry_soil", "high_temperature", "low_light"])
        end = classes(ths, series[-1])
        off = [p for p, c in end.items() if c["classification"] != "normal"]
        self.assertEqual(sorted(off), ["light", "soil_moisture", "temperature"])
        self.assertEqual(end["humidity"]["classification"], "normal")

    def test_multiple_requires_two_valid_problems(self):
        model = SimulationModel()
        with self.assertRaises(ValidationError):
            model.set_scenario("multiple", problems=["dry_soil"])
        with self.assertRaises(ValidationError):
            model.set_scenario("multiple", problems=["dry_soil", "nonsense"])
        model.set_scenario("multiple", problems=["dry_soil", "low_light"])
        self.assertEqual(model.problems, ["dry_soil", "low_light"])

    def test_custom_returns_exact_values(self):
        ths = advisory.thresholds(example_plant(), DEFAULTS)
        model = SimulationModel()
        wanted = {"soil_moisture": 12.5, "temperature": 31.0, "humidity": 44.0, "light": 63.0}
        model.set_scenario("custom", custom=wanted)
        for _ in range(3):
            self.assertEqual(model.next_values(ths), wanted)

    def test_custom_requires_values_and_unknown_scenario_rejected(self):
        model = SimulationModel()
        with self.assertRaises(ValidationError):
            model.set_scenario("custom")
        with self.assertRaises(ValidationError):
            model.set_scenario("tornado")

    def test_all_values_stay_inside_sensor_bounds(self):
        for scenario in ("normal", "dry_soil", "high_temperature", "low_humidity", "low_light"):
            for name in PLANTS:
                _, series = run_model(name, scenario, ticks=80)
                for v in series:
                    self.assertTrue(0 <= v["soil_moisture"] <= 100 and -10 <= v["temperature"] <= 60)
                    self.assertTrue(0 <= v["humidity"] <= 100 and 0 <= v["light"] <= 100)

    def test_switching_back_to_normal_recovers_gradually(self):
        ths = advisory.thresholds(example_plant(), DEFAULTS)
        model = SimulationModel(random.Random(3))
        model.set_scenario("dry_soil")
        for _ in range(20):
            model.next_values(ths)
        model.set_scenario("normal")
        series = [model.next_values(ths)["soil_moisture"] for _ in range(30)]
        self.assertGreater(series[-1], ths["soil_moisture"]["warn_low"])
        self.assertTrue(all(abs(b - a) <= 5.3 for a, b in zip(series, series[1:])))


class ScenarioEndToEndTests(AppCase):
    """Each scenario run through the manager: stored readings, analysis and alerts."""

    def run_scenario(self, scenario, ticks=25, **kwargs):
        self.sim.reset()
        self.sim.set_scenario(scenario, **kwargs)
        for _ in range(ticks):
            self.sim.generate_one()

    def active_types(self, plant="Money Plant"):
        rows = self.conn.execute("SELECT alert_type FROM alerts WHERE status='active' AND plant_id=?",
                                 (self.plant_id(plant),)).fetchall()
        return {r["alert_type"] for r in rows}

    def test_normal_creates_no_alerts_and_healthy_status(self):
        self.run_scenario("normal")
        self.assertEqual(self.active_types(), set())
        status = self.data("get", f"/api/plants/{self.plant_id('Money Plant')}/status")
        self.assertEqual(status["health"]["status"], "healthy")

    def test_dry_soil_raises_soil_moisture_alert(self):
        self.run_scenario("dry_soil")
        self.assertEqual(self.active_types(), {"soil_moisture_low"})

    def test_high_temperature_raises_temperature_alert(self):
        self.run_scenario("high_temperature")
        self.assertEqual(self.active_types(), {"temperature_high"})

    def test_low_humidity_and_low_light_raise_their_alerts(self):
        self.run_scenario("low_humidity")
        self.assertEqual(self.active_types(), {"humidity_low"})
        self.run_scenario("low_light")
        self.assertEqual(self.active_types(), {"light_low"})  # humidity recovered (auto-resolved)

    def test_multiple_problems_raise_multiple_alerts_and_critical_health(self):
        self.run_scenario("multiple", problems=["dry_soil", "high_temperature", "low_light"])
        self.assertEqual(self.active_types(), {"soil_moisture_low", "temperature_high", "light_low"})
        status = self.data("get", f"/api/plants/{self.plant_id('Money Plant')}/status")
        self.assertEqual(status["health"]["status"], "critical")

    def test_custom_conditions_are_stored_exactly(self):
        self.sim.reset()
        self.data("put", "/api/simulation/custom", json={"values": {
            "soil_moisture": 12, "temperature": 24, "humidity": 55, "light": 55}})
        body = self.data("post", "/api/simulation/tick", 201)
        r = body["reading"]
        self.assertEqual((r["soil_moisture"], r["scenario"], r["source"], r["is_simulated"]),
                         (12, "custom", "simulator", True))
        self.assertEqual(r["classes"]["soil_moisture"], "critical_low")
        self.assertEqual(body["health"]["status"], "critical")
        self.assertEqual(self.active_types(), {"soil_moisture_low"})

    def test_readings_are_marked_simulated_with_scenario(self):
        self.run_scenario("dry_soil", ticks=3)
        row = self.conn.execute("SELECT source, is_simulated, scenario FROM sensor_readings").fetchone()
        self.assertEqual((row["source"], row["is_simulated"], row["scenario"]), ("simulator", 1, "dry_soil"))


class LifecycleTests(AppCase):
    def workers(self):
        return [t for t in threading.enumerate() if t.name == "simulation-worker" and t.is_alive()]

    def reading_count(self):
        return self.conn.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0]

    def test_initial_state_is_stopped(self):
        s = self.sim.status()
        self.assertEqual((s["state"], s["worker_alive"], s["scenario"]), ("stopped", False, "normal"))

    def wait_until(self, predicate, timeout=5.0, step=0.1):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(step)
        return predicate()

    def test_start_pause_resume_stop(self):
        self.sim.set_interval(1)
        s = self.sim.start()
        self.assertEqual((s["state"], s["worker_alive"], s["tick_count"]), ("running", True, 1))
        self.assertEqual(self.reading_count(), 1)  # first reading is immediate
        self.assertTrue(self.wait_until(lambda: self.reading_count() >= 2, timeout=5.0))

        self.assertEqual(self.sim.pause()["state"], "paused")
        paused_count = self.reading_count()
        time.sleep(1.2)
        self.assertEqual(self.reading_count(), paused_count, "no readings while paused")

        self.assertEqual(self.sim.resume()["state"], "running")
        self.assertTrue(self.wait_until(lambda: self.reading_count() > paused_count, timeout=5.0))

        s = self.sim.stop()
        self.assertEqual((s["state"], s["worker_alive"]), ("stopped", False))
        stopped_count = self.reading_count()
        time.sleep(1.0)
        self.assertEqual(self.reading_count(), stopped_count, "no readings after stop")
        self.assertEqual(self.workers(), [])

    def test_invalid_transitions_are_rejected(self):
        with self.assertRaises(ConflictError):
            self.sim.pause()
        with self.assertRaises(ConflictError):
            self.sim.resume()
        with self.assertRaises(ConflictError):
            self.sim.stop()
        self.sim.set_interval(60)
        self.sim.start()
        with self.assertRaises(ConflictError):
            self.sim.start()
        with self.assertRaises(ConflictError):
            self.sim.resume()
        self.sim.pause()
        with self.assertRaises(ConflictError):
            self.sim.start()
        with self.assertRaises(ConflictError):
            self.sim.pause()

    def test_never_more_than_one_worker(self):
        self.sim.set_interval(60)
        self.sim.start()
        for _ in range(3):
            with self.assertRaises(ConflictError):
                self.sim.start()
        self.assertEqual(len(self.workers()), 1)
        self.sim.pause(), self.sim.resume()
        self.assertEqual(len(self.workers()), 1)
        self.sim.stop()
        self.sim.start()
        self.assertEqual(len(self.workers()), 1)
        self.sim.stop()
        self.assertEqual(len(self.workers()), 0)

    def test_reset_restores_scenario_and_runtime_but_keeps_history(self):
        self.sim.set_scenario("multiple", problems=["dry_soil", "low_light"])
        self.sim.set_interval(60)
        self.sim.start()
        self.sim.generate_one()
        before = self.reading_count()
        s = self.sim.reset()
        self.assertEqual((s["state"], s["scenario"], s["tick_count"], s["worker_alive"]), ("stopped", "normal", 0, False))
        self.assertEqual(s["problems"], ["dry_soil", "low_humidity"])
        self.assertIsNone(s["custom_values"])
        self.assertEqual(self.reading_count(), before, "reset must not delete stored readings")
        self.assertEqual(self.workers(), [])
        # runtime restarts from the plant's baseline, not from the old (problem) values
        r = self.sim.generate_one()["reading"]
        self.assertEqual(r["scenario"], "normal")
        self.assertEqual(r["classes"]["soil_moisture"], "normal")

    def test_reset_when_already_stopped_is_fine(self):
        self.assertEqual(self.sim.reset()["state"], "stopped")

    def test_generate_one_works_in_any_state_and_needs_active_plant(self):
        self.sim.generate_one()
        self.assertEqual(self.sim.status()["state"], "stopped")
        self.assertEqual(self.reading_count(), 1)
        for p in self.data("get", "/api/plants")["plants"]:
            self.data("delete", f"/api/plants/{p['id']}")
        with self.assertRaises(ConflictError):
            self.sim.generate_one()
        with self.assertRaises(ConflictError):
            self.sim.start()
        self.assertEqual(self.sim.status()["state"], "stopped")

    def test_interval_setting_is_applied_to_the_simulator(self):
        self.data("put", "/api/settings", json={"sampling_interval_seconds": 2.5})
        self.assertEqual(self.data("get", "/api/simulation")["interval_seconds"], 2.5)

    def test_simulation_follows_active_plant_without_mixing_records(self):
        a, b = self.plant_id("Money Plant"), self.plant_id("Aloe Vera")
        self.data("put", "/api/plants/active", json={"plant_id": a})
        self.sim.generate_one()
        self.data("put", "/api/plants/active", json={"plant_id": b})
        self.sim.generate_one()
        self.sim.generate_one()
        counts = {r["plant_id"]: r["n"] for r in self.conn.execute(
            "SELECT plant_id, COUNT(*) n FROM sensor_readings GROUP BY plant_id")}
        self.assertEqual(counts, {a: 1, b: 2})

    def test_api_lifecycle_endpoints_and_conflicts(self):
        self.data("put", "/api/settings", json={"sampling_interval_seconds": 60})
        self.assertEqual(self.data("post", "/api/simulation/start")["state"], "running")
        self.call("post", "/api/simulation/start", 409)
        self.assertEqual(self.data("post", "/api/simulation/pause")["state"], "paused")
        self.call("post", "/api/simulation/pause", 409)
        self.assertEqual(self.data("post", "/api/simulation/resume")["state"], "running")
        self.assertEqual(self.data("post", "/api/simulation/stop")["state"], "stopped")
        self.call("post", "/api/simulation/stop", 409)
        self.assertEqual(self.data("post", "/api/simulation/reset")["state"], "stopped")


if __name__ == "__main__":
    unittest.main()
