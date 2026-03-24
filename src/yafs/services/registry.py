from __future__ import annotations

import threading
from collections.abc import Iterable

from .models import ManagedSimulation


class SimulationRegistry:
    def __init__(self) -> None:
        self._items: dict[str, ManagedSimulation] = {}
        self._lock = threading.RLock()

    def add(self, managed: ManagedSimulation) -> ManagedSimulation:
        with self._lock:
            self._items[managed.id] = managed
            return managed

    def get(self, simulation_id: str) -> ManagedSimulation | None:
        with self._lock:
            return self._items.get(simulation_id)

    def require(self, simulation_id: str) -> ManagedSimulation:
        managed = self.get(simulation_id)
        if managed is None:
            raise KeyError(f"Unknown simulation id: {simulation_id}")
        return managed

    def remove(self, simulation_id: str) -> ManagedSimulation | None:
        with self._lock:
            return self._items.pop(simulation_id, None)

    def list(self) -> list[ManagedSimulation]:
        with self._lock:
            return list(self._items.values())

    def values(self) -> Iterable[ManagedSimulation]:
        return self.list()
