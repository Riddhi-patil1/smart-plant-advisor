import unittest

from app import advisory
from app.settings import DEFAULTS
from helpers import example_plant


def analyze(plant_name, soil, temp, hum, light, **setting_overrides):
    settings = dict(DEFAULTS, **setting_overrides)
    plant = example_plant(plant_name)
    return advisory.analyze(plant, {"soil_moisture": soil, "temperature": temp, "humidity": hum, "light": light}, settings)


class ClassificationTests(unittest.TestCase):
    def test_threshold_ordering_for_every_plant(self):
        for name in ("Money Plant", "Aloe Vera", "Tulsi", "Snake Plant"):
            ths = advisory.thresholds(example_plant(name), DEFAULTS)
            for p, th in ths.items():
                self.assertLess(th["crit_low"], th["warn_low"]) if th["warn_low"] > 0 else self.assertLessEqual(th["crit_low"], th["warn_low"])
                self.assertLessEqual(th["warn_low"], th["pref_min"])
                self.assertLessEqual(th["pref_max"], th["warn_high"])
                self.assertLess(th["warn_high"], th["crit_high"])

    def test_soil_moisture_levels_for_money_plant(self):
        # warning threshold 35, preferred 40-60, critical below 20
        cases = {50: "normal", 38: "normal", 35: "normal", 34.9: "low", 19: "critical_low", 60: "normal",
                 60.1: "high", 90: "critical_high"}
        for value, expected in cases.items():
            result = analyze("Money Plant", value, 24, 55, 55)
            self.assertEqual(result["classifications"]["soil_moisture"]["classification"], expected, value)

    def test_labels_are_low_normal_high_critical(self):
        labels = {analyze("Money Plant", v, 24, 55, 55)["classifications"]["soil_moisture"]["label"]
                  for v in (10, 30, 50, 70, 95)}
        self.assertEqual(labels, {"Critical", "Low", "Normal", "High"})

    def test_normal_but_outside_preferred_range_carries_a_note(self):
        c = analyze("Money Plant", 38, 24, 55, 55)["classifications"]["soil_moisture"]
        self.assertEqual(c["classification"], "normal")
        self.assertFalse(c["in_preferred_range"])
        self.assertIn("preferred range", c["note"])

    def test_same_reading_is_judged_per_plant(self):
        money = analyze("Money Plant", 20, 24, 55, 55)["classifications"]["soil_moisture"]["classification"]
        snake = analyze("Snake Plant", 20, 24, 55, 55)["classifications"]["soil_moisture"]["classification"]
        self.assertEqual((money, snake), ("low", "normal"))

    def test_temperature_humidity_light_detection(self):
        r = analyze("Money Plant", 50, 36, 20, 10)["classifications"]
        self.assertIn(r["temperature"]["classification"], ("high", "critical_high"))
        self.assertIn(r["humidity"]["classification"], ("low", "critical_low"))
        self.assertIn(r["light"]["classification"], ("low", "critical_low"))
        r = analyze("Money Plant", 50, 10, 95, 99)["classifications"]
        self.assertIn(r["temperature"]["classification"], ("low", "critical_low"))
        self.assertIn(r["humidity"]["classification"], ("high", "critical_high"))
        self.assertIn(r["light"]["classification"], ("high", "critical_high"))

    def test_global_margin_changes_critical_point_but_not_plant_profile(self):
        tight = advisory.thresholds(example_plant(), dict(DEFAULTS, critical_margin_soil_moisture=5))
        wide = advisory.thresholds(example_plant(), dict(DEFAULTS, critical_margin_soil_moisture=30))
        self.assertGreater(tight["soil_moisture"]["crit_low"], wide["soil_moisture"]["crit_low"])
        self.assertEqual(tight["soil_moisture"]["warn_low"], wide["soil_moisture"]["warn_low"])


class OverallHealthTests(unittest.TestCase):
    def test_all_normal_is_healthy(self):
        self.assertEqual(analyze("Money Plant", 50, 24, 55, 55)["health"]["status"], "healthy")

    def test_one_normal_reading_never_hides_a_problem(self):
        for args in [(50, 24, 55, 5), (50, 36, 55, 55), (20, 24, 55, 55), (50, 24, 10, 55)]:
            health = analyze("Money Plant", *args)["health"]
            self.assertNotEqual(health["status"], "healthy", args)

    def test_single_warning_needs_attention(self):
        health = analyze("Money Plant", 30, 24, 55, 55)["health"]
        self.assertEqual(health["status"], "needs_attention")
        self.assertTrue(any("Soil Moisture" in f["message"] for f in health["factors"]))

    def test_any_critical_reading_is_critical(self):
        self.assertEqual(analyze("Money Plant", 5, 24, 55, 55)["health"]["status"], "critical")

    def test_three_warnings_escalate_to_critical(self):
        health = analyze("Money Plant", 30, 33, 35, 55)["health"]
        self.assertEqual(health["status"], "critical")
        self.assertTrue(any("outside their thresholds" in f["message"] for f in health["factors"]))

    def test_health_explains_factors(self):
        health = analyze("Money Plant", 30, 33, 55, 55)["health"]
        self.assertEqual(health["status"], "needs_attention")
        self.assertEqual(len([f for f in health["factors"] if f["severity"]]), 2)
        self.assertIn("needs attention", health["summary"])


class RecommendationTests(unittest.TestCase):
    def rec(self, result, rule_id):
        return next(r for r in result["recommendations"] if r["rule_id"] == rule_id)

    def test_low_moisture_gives_explainable_watering_recommendation(self):
        result = analyze("Money Plant", 30, 24, 55, 55)
        rec = self.rec(result, "soil_moisture_low")
        self.assertEqual(rec["category"], "watering")
        self.assertEqual(rec["severity"], "warning")
        self.assertIn("30%", rec["message"])
        self.assertIn("35%", rec["message"])
        self.assertIn("Rule:", rec["explanation"])
        self.assertIn("simulated", rec["explanation"])
        self.assertTrue(rec["advisory"])
        self.assertEqual(rec["values"]["value"], 30)
        self.assertEqual(rec["values"]["warning_threshold"], 35)
        self.assertTrue(any("Plant guidance:" in a for a in rec["actions"]))
        self.assertIn("Advisory only", result["advisory_note"])

    def test_adequate_moisture_says_no_watering_and_is_not_timer_based(self):
        rec = self.rec(analyze("Money Plant", 50, 24, 55, 55), "soil_moisture_normal")
        self.assertEqual(rec["severity"], "info")
        self.assertIn("No watering", rec["title"])
        self.assertIn("not on elapsed time", " ".join(rec["actions"]))

    def test_high_moisture_advises_holding_off(self):
        rec = self.rec(analyze("Money Plant", 75, 24, 55, 55), "soil_moisture_high")
        self.assertEqual(rec["category"], "watering")
        self.assertIn("Do not water", rec["actions"][0])

    def test_environment_advice_is_separate_from_watering(self):
        result = analyze("Money Plant", 50, 36, 20, 10)
        cats = {r["rule_id"]: r["category"] for r in result["recommendations"]}
        self.assertEqual(cats["soil_moisture_normal"], "watering")
        for rid, cat in cats.items():
            if not rid.startswith("soil_moisture"):
                self.assertEqual(cat, "environment")
        self.assertEqual(len([c for c in cats.values() if c == "environment"]), 3)

    def test_recommendations_are_sorted_most_severe_first(self):
        result = analyze("Money Plant", 5, 33, 55, 55)
        severities = [r["severity"] for r in result["recommendations"]]
        self.assertEqual(severities, sorted(severities, key=["critical", "warning", "info"].index))

    def test_recommendation_follows_the_plants_own_guidance_and_thresholds(self):
        aloe = analyze("Aloe Vera", 8, 24, 30, 70)
        rec = self.rec(aloe, "soil_moisture_low")
        self.assertIn("Aloe Vera", rec["message"])
        self.assertIn("10%", rec["message"])
        self.assertTrue(any("deeply but infrequently" in a for a in rec["actions"]))

    def test_every_non_normal_rule_has_a_catalog_entry(self):
        for p in ("soil_moisture", "temperature", "humidity", "light"):
            for code in ("low", "high", "critical_low", "critical_high"):
                if (p, code) in advisory.RULE_TITLES:
                    self.assertIn(advisory.rule_id(p, code), advisory.RULE_CATALOG)


if __name__ == "__main__":
    unittest.main()
