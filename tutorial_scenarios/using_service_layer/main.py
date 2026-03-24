"""
Service-layer adaptation of tutorial_scenarios/03_topologyChanges.

The experiment creates a root simulation and then forks it before each node
failure to compare four branches:
- S0: root simulation (no failures)
- S1: one node failure
- S2: two node failures
- S3: three node failures
"""

from __future__ import annotations

import math
from pathlib import Path

from yafs.services.simulation_service import SimulationService


SIMULATION_HORIZON = 20_000.0
STEP = 2_000.0
FORK_WINDOW = 4_000.0
FAILURE_NODES = [
    "mec-0-worker-2",
    "mec-0-worker-1",
    "edc-0-worker-2",
]


def _run_for(service: SimulationService, sim_id: str, duration: float) -> float:
    """Run a simulation branch for a relative duration and return current time."""
    if duration <= 0:
        return service.get_state(sim_id).summary.now

    service.schedule_for(sim_id, duration=duration, step=STEP)
    state = service.wait_until_ready(sim_id)
    return state.summary.now


def _run_until(
    service: SimulationService,
    sim_id: str,
    target_time: float,
) -> float:
    """Run a simulation branch until target_time."""
    state = service.get_state(sim_id)
    remaining = target_time - state.summary.now
    return _run_for(service, sim_id, remaining)


def _print_application_metrics(
    service: SimulationService,
    label: str,
    sim_id: str,
) -> None:
    report = service.get_application_metrics(sim_id)
    print(f"{label} (id={sim_id}):")
    if not report.items:
        print("  <no metrics available>")
        return

    for item in report.items:
        avg_response = "nan" if math.isnan(item.response_mean) else f"{item.response_mean:.5f}"
        print(
            "  - "
            f"app={item.app}, "
            f"avg_response={avg_response}, "
            f"requests_total={int(item.requests_total)}, "
            f"successful={int(item.requests_successful)}, "
            f"unsuccessful={int(item.requests_unsuccessful)}, "
            f"placement_cost={item.placement_cost:.8f}, "
            f"total_cost={item.total_cost:.8f}"
        )


def _print_topology_state(
    service: SimulationService,
    label: str,
    sim_id: str,
) -> None:
    node_count = service.count_nodes(sim_id)
    cluster_count = service.count_clusters(sim_id)
    node_names = [item["node"] for item in service.list_nodes(sim_id)]
    print(
        f"{label}: nodes={node_count}, clusters={cluster_count}, "
        f"node_names={node_names}"
    )


def main() -> None:
    scenario_path = Path(__file__).parent
    results_path = scenario_path / "results"

    service = SimulationService()
    seed = 2026

    s0 = service.create_simulation(
        scenario_path=scenario_path,
        results_path=results_path,
        seed=seed,
        name="topology-changes-root",
    )
    print(f"S0 created -> id={s0.summary.id}, now={s0.summary.now}")

    now = _run_for(service, s0.summary.id, FORK_WINDOW)
    print(f"S0 warmup completed -> now={now}")

    s1 = service.fork(s0.summary.id, child_name="topology-changes-1-failure")
    print(f"S1 forked from S0 -> id={s1.summary.id}, now={s1.summary.now}")
    service.remove_node(s1.summary.id, FAILURE_NODES[0])
    print(f"S1 failure applied -> removed node: {FAILURE_NODES[0]}")
    now = _run_for(service, s1.summary.id, FORK_WINDOW)
    print(f"S1 reached second checkpoint -> now={now}")

    s2 = service.fork(s1.summary.id, child_name="topology-changes-2-failures")
    print(f"S2 forked from S1 -> id={s2.summary.id}, now={s2.summary.now}")
    service.remove_node(s2.summary.id, FAILURE_NODES[1])
    print(f"S2 second failure applied -> removed node: {FAILURE_NODES[1]}")
    now = _run_for(service, s2.summary.id, FORK_WINDOW)
    print(f"S2 reached third checkpoint -> now={now}")

    s3 = service.fork(s2.summary.id, child_name="topology-changes-3-failures")
    print(f"S3 forked from S2 -> id={s3.summary.id}, now={s3.summary.now}")
    service.remove_node(s3.summary.id, FAILURE_NODES[2])
    print(f"S3 third failure applied -> removed node: {FAILURE_NODES[2]}")

    s0_now = _run_until(service, s0.summary.id, SIMULATION_HORIZON)
    s1_now = _run_until(service, s1.summary.id, SIMULATION_HORIZON)
    s2_now = _run_until(service, s2.summary.id, SIMULATION_HORIZON)
    s3_now = _run_until(service, s3.summary.id, SIMULATION_HORIZON)

    print("\nTimeline summary:")
    print(f"  S0 (0 failures) -> now={s0_now}")
    print(f"  S1 (1 failure) -> now={s1_now}")
    print(f"  S2 (2 failures) -> now={s2_now}")
    print(f"  S3 (3 failures) -> now={s3_now}")

    print("\nTopology summary:")
    _print_topology_state(service, "S0", s0.summary.id)
    _print_topology_state(service, "S1", s1.summary.id)
    _print_topology_state(service, "S2", s2.summary.id)
    _print_topology_state(service, "S3", s3.summary.id)

    print("\nApplication metrics summary:")
    _print_application_metrics(service, "S0", s0.summary.id)
    _print_application_metrics(service, "S1", s1.summary.id)
    _print_application_metrics(service, "S2", s2.summary.id)
    _print_application_metrics(service, "S3", s3.summary.id)


if __name__ == "__main__":
    main()
