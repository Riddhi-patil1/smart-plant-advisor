"""Pure value generator for the sensor simulator (no threads, no database).

Values are bounded, change from tick to tick and move *gradually* between scenarios:
* normal    : drifts toward the middle of the plant's preferred ranges and never leaves them
              once inside.
* problems  : the affected sensor steps toward a target beyond its warning threshold and then
              holds there (with small noise) so the condition is reliably detected.
* custom    : returns exactly the values the user entered.
"""
import random

from .constants import PARAMS, PROBLEM_KEYS, SCENARIOS, SENSORS
from .errors import ValidationError

DEFAULT_PROBLEMS = ["dry_soil", "low_humidity"]
STEP = {"soil_moisture": 4.0, "temperature": 0.8, "humidity": 3.0, "light": 5.0}
NOISE = {"soil_moisture": 0.4, "temperature": 0.15, "humidity": 0.5, "light": 0.8}


def problem_spec(key, ths):
    """(parameter, direction, boundary, target) for one environmental problem."""
    if key == "dry_soil":
        b = ths["soil_moisture"]["warn_low"]
        return "soil_moisture", "down", b, max(b - 4.0, b * 0.5)
    if key == "high_temperature":
        b = ths["temperature"]["warn_high"]
        return "temperature", "up", b, min(b + 3.0, 58.0)
    if key == "low_humidity":
        b = ths["humidity"]["warn_low"]
        return "humidity", "down", b, max(b - 10.0, b * 0.5)
    if key == "low_light":
        b = ths["light"]["warn_low"]
        return "light", "down", b, max(b - 15.0, b * 0.5)
    raise KeyError(key)


def clamp(value, lo, hi):
    return min(max(value, lo), hi)


class SimulationModel:
    def __init__(self, rng=None):
        self.rng = rng or random.Random()
        self.scenario = "normal"
        self.problems = list(DEFAULT_PROBLEMS)
        self.custom = None
        self.values = None  # last generated values (runtime state)

    # ---- configuration -------------------------------------------------
    def reset(self):
        self.scenario, self.problems, self.custom, self.values = "normal", list(DEFAULT_PROBLEMS), None, None

    def set_scenario(self, scenario, problems=None, custom=None):
        if scenario not in SCENARIOS:
            raise ValidationError("Unknown scenario.", {"scenario": "Must be one of: " + ", ".join(SCENARIOS) + "."})
        if scenario == "multiple":
            chosen = list(dict.fromkeys(problems if problems is not None else self.problems))
            bad = [p for p in chosen if p not in PROBLEM_KEYS]
            if bad or len(chosen) < 2:
                raise ValidationError(
                    "Choose at least two valid environmental problems.",
                    {"problems": "Select two or more of: " + ", ".join(PROBLEM_KEYS) + "."},
                )
            self.problems = chosen
        if scenario == "custom":
            if custom is None:
                raise ValidationError("Custom conditions need sensor values.", {"values": "Required for the custom scenario."})
            self.custom = dict(custom)
        self.scenario = scenario

    def seed_values(self, values):
        self.values = dict(values)

    # ---- generation ----------------------------------------------------
    def _initial(self, ths):
        return {p: round((ths[p]["pref_min"] + ths[p]["pref_max"]) / 2.0, 1) for p in PARAMS}

    def _drift_in_range(self, parameter, cur, ths):
        lo, hi = ths[parameter]["pref_min"], ths[parameter]["pref_max"]
        center, width = (lo + hi) / 2.0, hi - lo
        move = clamp((center - cur) * 0.35, -STEP[parameter], STEP[parameter])
        new = cur + move + self.rng.uniform(-1, 1) * width * 0.06
        was_inside = lo <= cur <= hi
        if was_inside or (cur < lo <= new) or (cur > hi >= new):
            new = clamp(new, lo, hi)
        new = round(new, 1)
        if was_inside or lo <= new <= hi:
            new = clamp(new, lo, hi)
        return new

    def _toward_problem(self, key, cur, ths):
        parameter, direction, boundary, target = problem_spec(key, ths)
        step, noise = STEP[parameter], NOISE[parameter]
        gap = target - cur
        if abs(gap) <= step:
            new = target + self.rng.uniform(-noise, noise)
        else:
            new = cur + (step if gap > 0 else -step) + self.rng.uniform(-noise, noise)
        if direction == "down" and new >= boundary and abs(gap) <= step:
            new = boundary - 0.5
        if direction == "down" and new < boundary:
            new = min(new, boundary - 0.5)
        if direction == "up" and new <= boundary and abs(gap) <= step:
            new = boundary + 0.5
        if direction == "up" and new > boundary:
            new = max(new, boundary + 0.5)
        return parameter, new

    def active_problems(self):
        if self.scenario == "multiple":
            return list(self.problems)
        if self.scenario in PROBLEM_KEYS:
            return [self.scenario]
        return []

    def next_values(self, ths):
        if self.scenario == "custom":
            self.values = dict(self.custom)
            return dict(self.values)
        cur = dict(self.values) if self.values else self._initial(ths)
        new = {p: self._drift_in_range(p, cur[p], ths) for p in PARAMS}
        for key in self.active_problems():
            parameter, value = self._toward_problem(key, cur[parameter_of(key)], ths)
            new[parameter] = value
        out = {}
        for p in PARAMS:
            meta = SENSORS[p]
            out[p] = round(clamp(new[p], meta["min"], meta["max"]), 1)
        self.values = dict(out)
        return out


def parameter_of(key):
    return {"dry_soil": "soil_moisture", "high_temperature": "temperature",
            "low_humidity": "humidity", "low_light": "light"}[key]
