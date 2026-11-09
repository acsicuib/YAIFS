"""Shared helpers for fork reproducibility tests."""

from __future__ import annotations

import csv
import random
from pathlib import Path

import numpy as np

from yafs.api import Simulation
from yafs.services.simulation_service import SimulationService

SCENARIO = (
    Path(__file__).resolve().parents[1]
    / "tutorial_scenarios"
    / "using_service_layer_01"
)
SEED = 2026
STEP = 500.0

MOBILITY_PROCESS = {
    "name": "user-mobility",
    "kind": "user_mobility_random",
    "activation": {
        "kind": "exponential",
        "lambd": 200,
        "seed": 7,
        "name": "mobility-activation",
    },
    "params": {
        "app": 0,
        "message": "M.AR.0_0",
        "lambda": 400,
        "candidate_nodes": [
            "edc-0-worker-1",
            "mec-0-worker-1",
            "mec-0-worker-2",
        ],
        "create_probability": 0.7,
        "move_probability": 0.2,
        "remove_probability": 0.1,
        "max_users": 5,
    },
}


def create_service(
    results_path: Path,
    *,
    seed: int = SEED,
    name: str = "root",
) -> tuple[SimulationService, str]:
    """Create one simulation rooted at the service-layer scenario."""
    service = SimulationService()
    state = service.create_simulation(
        scenario_path=SCENARIO,
        results_path=results_path,
        seed=seed,
        name=name,
    )
    return service, state.summary.id


def simulation_of(
    service: SimulationService,
    simulation_id: str,
) -> Simulation:
    """Return the live simulation object owned by the service."""
    return service.registry.require(simulation_id).simulation


def run_for(
    service: SimulationService,
    simulation_id: str,
    duration: float,
    *,
    step: float = STEP,
) -> float:
    """Advance one branch and return its simulation time."""
    service.schedule_for(simulation_id, duration=duration, step=step)
    state = service.wait_until_ready(simulation_id, poll_interval=0.01)
    return float(state.summary.now)


def enable_mobility(service: SimulationService, simulation_id: str) -> None:
    """Register the random user-generation process before the run."""
    service.create_process(simulation_id, MOBILITY_PROCESS)


def user_rows(simulation: Simulation) -> list[tuple]:
    """Return stable user identities for equality checks."""
    report = simulation.list_users()
    return [
        (
            item["des"],
            item["app"],
            item["node"],
            item["message"],
            item["lambda"],
        )
        for item in report["users"]
    ]


def trace_tables(simulation: Simulation) -> list[list[list[str]]]:
    """Read event and link traces written by one branch."""
    simulation._flush_metrics_if_needed()
    tables: list[list[list[str]]] = []
    for suffix in (".csv", "_link.csv"):
        path = Path(f"{simulation.results_path}{suffix}")
        with path.open(newline="", encoding="utf-8") as handle:
            tables.append(list(csv.reader(handle)))
    return tables


def generator_state(generator: object):
    """Return the internal state of a stdlib or NumPy generator."""
    if hasattr(generator, "get_state"):
        return generator.get_state()
    return generator.getstate()


def states_equal(left, right) -> bool:
    """Compare stdlib and NumPy generator states by value."""
    if isinstance(left, tuple) and left and left[0] == "MT19937":
        if not isinstance(right, tuple) or right[0] != "MT19937":
            return False
        return (
            bool(np.array_equal(left[1], right[1]))
            and int(left[2]) == int(right[2])
            and left[3] == right[3]
            and left[4] == right[4]
        )
    return left == right


def virgin_sim_rng(seed: int):
    """State of a simulation generator that has not drawn yet."""
    return random.Random(seed).getstate()


def virgin_numpy_rng(seed: int):
    """State of a freshly seeded NumPy generator."""
    return np.random.RandomState(seed).get_state()
