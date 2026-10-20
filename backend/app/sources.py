"""Sensor-source abstraction: data acquisition is separated from analysis and storage.

A source only *produces raw values*. It never touches the database, thresholds or alerts;
those belong to ``ingestion.ingest_reading``. This version ships one source, the simulator.
A future ESP32 source would implement the same interface (or push values straight into
``ingest_reading`` from an HTTP endpoint).
"""
from abc import ABC, abstractmethod

from .simulation_model import SimulationModel


class SensorSource(ABC):
    name = "abstract"
    is_simulated = True

    @abstractmethod
    def read(self, plant, thresholds):
        """Return ``(values, scenario_key)`` where values maps sensor name to a float."""


class SimulatedSource(SensorSource):
    name = "simulator"
    is_simulated = True

    def __init__(self, model=None):
        self.model = model or SimulationModel()

    def read(self, plant, thresholds):
        values = self.model.next_values(thresholds)
        return values, self.model.scenario
