"""Simulation lifecycle manager (backend-owned state, one worker thread at most).

States: stopped -> running <-> paused -> stopped.  Invalid transitions raise ConflictError.
The worker thread is created only by start(); a lock plus an explicit "is a worker alive?"
check make duplicate loops impossible. Browser timers are never used to drive readings.
"""
import json
import threading
import time

from . import advisory, ingestion, plants, readings
from . import settings as settings_store
from .constants import SCENARIOS
from .db import connect, transaction, utc_now
from .errors import ConflictError
from .simulation_model import DEFAULT_PROBLEMS, SimulationModel
from .sources import SimulatedSource


class SimulationManager:
    def __init__(self, db_path, rng=None):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._source = SimulatedSource(SimulationModel(rng))
        self._thread = None
        self._stop_event = threading.Event()
        self._state = "stopped"
        self._interval = 5.0
        self._tick_count = 0
        self._last_reading_at = None
        self._last_error = None
        self._started_at = None
        self._values_plant_id = None
        self._continue_from_history = True
        self._load()

    @property
    def model(self):
        return self._source.model

    # ---- persistence ---------------------------------------------------
    def _load(self):
        conn = connect(self.db_path)
        try:
            row = conn.execute("SELECT * FROM simulation_state WHERE id = 1").fetchone()
            self._interval = float(settings_store.get_all(conn)["sampling_interval_seconds"])
            if row:
                self.model.scenario = row["scenario"] if row["scenario"] in SCENARIOS else "normal"
                self.model.problems = json.loads(row["problems"]) if row["problems"] else list(DEFAULT_PROBLEMS)
                self.model.custom = json.loads(row["custom_values"]) if row["custom_values"] else None
                if self.model.scenario == "custom" and not self.model.custom:
                    self.model.scenario = "normal"
                self._tick_count = row["tick_count"]
                self._last_reading_at = row["last_reading_at"]
            # A restart never resumes a worker: persisted running/paused state becomes stopped.
            with transaction(conn):
                conn.execute("UPDATE simulation_state SET state = 'stopped', updated_at = ? WHERE id = 1", (utc_now(),))
        finally:
            conn.close()

    def _persist(self, conn=None):
        own = conn is None
        conn = conn or connect(self.db_path)
        try:
            with transaction(conn):
                conn.execute(
                    "UPDATE simulation_state SET state = ?, scenario = ?, problems = ?, custom_values = ?, "
                    "tick_count = ?, last_reading_at = ?, updated_at = ? WHERE id = 1",
                    (self._state, self.model.scenario, json.dumps(self.model.problems),
                     json.dumps(self.model.custom) if self.model.custom else None,
                     self._tick_count, self._last_reading_at, utc_now()),
                )
        finally:
            if own:
                conn.close()

    # ---- status ----------------------------------------------------------
    def status(self):
        with self._lock:
            conn = connect(self.db_path)
            try:
                plant_id = plants.get_active_plant_id(conn)
            finally:
                conn.close()
            return {
                "state": self._state,
                "scenario": self.model.scenario,
                "scenario_label": SCENARIOS[self.model.scenario]["label"],
                "problems": list(self.model.problems),
                "custom_values": dict(self.model.custom) if self.model.custom else None,
                "interval_seconds": self._interval,
                "active_plant_id": plant_id,
                "tick_count": self._tick_count,
                "last_reading_at": self._last_reading_at,
                "started_at": self._started_at,
                "last_error": self._last_error,
                "worker_alive": bool(self._thread and self._thread.is_alive()),
                "data_source": "simulator",
                "is_simulated": True,
            }

    # ---- one tick ----------------------------------------------------------
    def _tick_locked(self):
        conn = connect(self.db_path)
        try:
            plant_id = plants.get_active_plant_id(conn)
            if plant_id is None:
                raise ConflictError("No active plant is selected.")
            plant = plants.get_plant(conn, plant_id)
            settings = settings_store.get_all(conn)
            ths = advisory.thresholds(plant, settings)
            if self._values_plant_id != plant_id:
                # New (or first) plant: start from its own latest reading, never another plant's values.
                latest = readings.latest(conn, plant_id) if self._continue_from_history else None
                if latest:
                    self.model.seed_values({p: latest[p] for p in ths})
                else:
                    self.model.values = None
                self._values_plant_id = plant_id
            values, scenario = self._source.read(plant, ths)
            result = ingestion.ingest_reading(conn, plant_id, values, source=self._source.name, scenario=scenario)
            self._tick_count += 1
            self._last_reading_at = result["reading"]["recorded_at"]
            self._last_error = None
            self._persist(conn)
            return result
        finally:
            conn.close()

    def generate_one(self):
        """Create exactly one reading now, whatever the lifecycle state is."""
        with self._lock:
            try:
                return self._tick_locked()
            except ConflictError:
                raise
            except Exception as exc:  # surfaced through status as well
                self._last_error = str(exc)
                raise

    # ---- lifecycle -------------------------------------------------------------
    def start(self):
        with self._lock:
            if self._state != "stopped":
                raise ConflictError(f"The simulation is already {self._state}.")
            if self._thread and self._thread.is_alive():
                raise ConflictError("A simulation worker is still shutting down; try again in a moment.")
            self._tick_locked()  # first reading immediately; raises if no active plant
            self._state = "running"
            self._started_at = utc_now()
            self._stop_event = threading.Event()
            self._thread = threading.Thread(target=self._run, args=(self._stop_event,), name="simulation-worker", daemon=True)
            self._persist()
            self._thread.start()
        return self.status()

    def pause(self):
        with self._lock:
            if self._state != "running":
                raise ConflictError(f"Only a running simulation can be paused (state: {self._state}).")
            self._state = "paused"
            self._persist()
        return self.status()

    def resume(self):
        with self._lock:
            if self._state != "paused":
                raise ConflictError(f"Only a paused simulation can be resumed (state: {self._state}).")
            self._state = "running"
            self._persist()
        return self.status()

    def stop(self):
        with self._lock:
            if self._state == "stopped":
                raise ConflictError("The simulation is already stopped.")
            self._state = "stopped"
            self._stop_event.set()
            thread, self._thread = self._thread, None
            self._persist()
        if thread is not None:
            thread.join(timeout=5)  # joined outside the lock so the worker can finish its tick
        return self.status()

    def reset(self):
        """Stop the worker and restore scenario and runtime state. Stored readings are kept."""
        with self._lock:
            was_active = self._state != "stopped"
        if was_active:
            self.stop()
        with self._lock:
            self.model.reset()
            self._tick_count = 0
            self._last_reading_at = None
            self._last_error = None
            self._started_at = None
            self._values_plant_id = None
            self._continue_from_history = False
            self._persist()
        return self.status()

    def set_scenario(self, scenario, problems=None, custom=None):
        with self._lock:
            self.model.set_scenario(scenario, problems, custom)
            self._persist()
        return self.status()

    def set_interval(self, seconds):
        with self._lock:
            self._interval = float(seconds)

    def shutdown(self):
        with self._lock:
            self._stop_event.set()
            thread, self._thread = self._thread, None
            self._state = "stopped"
        if thread is not None:
            thread.join(timeout=5)

    # ---- worker ------------------------------------------------------------------
    def _run(self, stop_event):
        last = time.monotonic()
        while not stop_event.wait(0.2):
            with self._lock:
                if stop_event.is_set():
                    break
                if self._state != "running":
                    last = time.monotonic()
                    continue
                if time.monotonic() - last < self._interval:
                    continue
                last = time.monotonic()
                try:
                    self._tick_locked()
                except Exception as exc:  # keep the worker alive; report through status
                    self._last_error = str(exc)
