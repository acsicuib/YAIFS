from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..api import Simulation


class SimulationStatus(StrEnum):
    CREATED = "created"
    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED = "paused"
    IDLE = "idle"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(slots=True)
class SimulationSummary:
    id: str
    name: str
    scenario_path: str
    seed: int | None
    status: SimulationStatus
    created_at: str
    parent_id: str | None = None
    scheduled_until: float | None = None
    now: float = 0.0
    error: str | None = None


@dataclass(slots=True)
class SimulationState:
    summary: SimulationSummary
    initialized: bool
    paused: bool
    stop_requested: bool
    step: float
    network_buffer: int
    alloc_source_count: int
    alloc_module_count: int


@dataclass(slots=True)
class SimulationMetricsSnapshot:
    simulation_id: str
    entity_metrics: Any
    unreachabled_links: int


@dataclass(slots=True)
class ApplicationMetricsSummary:
    app: str
    requests_total: float
    requests_successful: float
    requests_unsuccessful: float
    response_mean: float
    response_p50: float
    response_p95: float
    response_max: float
    network_mean: float
    processing_mean: float
    waiting_mean: float
    placement_cost: float
    deployments: int
    egress_cost: float
    total_cost: float


@dataclass(slots=True)
class SimulationApplicationMetrics:
    simulation_id: str
    items: list[ApplicationMetricsSummary]
    from_time: float | None = None
    to_time: float | None = None
    reference_time: float | None = None
    absolute_from_time: float | None = None
    absolute_to_time: float | None = None


@dataclass(slots=True)
class ManagedSimulation:
    id: str
    name: str
    scenario_path: Path
    simulation: Simulation
    seed: int | None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    parent_id: str | None = None
    status: SimulationStatus = SimulationStatus.CREATED
    last_error: str | None = None

    def to_summary(self) -> SimulationSummary:
        snapshot = self.simulation.get_state()
        return SimulationSummary(
            id=self.id,
            name=self.name,
            scenario_path=str(self.scenario_path),
            seed=self.seed,
            status=self.status,
            created_at=self.created_at.isoformat(),
            parent_id=self.parent_id,
            scheduled_until=snapshot["scheduled_until"],
            now=snapshot["now"],
            error=self.last_error,
        )
