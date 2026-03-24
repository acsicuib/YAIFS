"""
Service movement tutorial implemented with the API layer primitives.

This scenario keeps the semantic behavior from tutorial_scenarios/02_serviceMovement:
services are periodically moved to random nodes while the simulation is running.
"""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path

import numpy as np
import pandas as pd

from yafs.api import Infrastructure, ProcessContext, Simulation
from yafs.distribution import deterministicDistributionStartPoint


class RandomServiceMovementProcess:
    """Moves each deployed VNF to another random node on each activation."""

    def __init__(self, app_refs: list[str | int]) -> None:
        self.app_refs = list(app_refs)
        self.activations = 0

    def __call__(self, context: ProcessContext) -> None:
        self.activations += 1
        logging.info("Activating RandomServiceMovement - #%s", self.activations)

        node_ids = [str(item["node"]) for item in context.list_nodes()]
        if len(node_ids) < 2:
            return

        rng = context.rng
        for app_ref in self.app_refs:
            vnf_report = context.list_application_vnfs(app_ref)
            for vnf_item in vnf_report.get("vnfs", []):
                module_name = str(vnf_item["vnf"])
                occupied_nodes = {str(node) for node in vnf_item.get("nodes", [])}
                deployments = list(vnf_item.get("deployments", []))

                for deployment in deployments:
                    source_node = str(deployment["node"])
                    candidates = [
                        node for node in node_ids
                        if node not in occupied_nodes and node != source_node
                    ]
                    if not candidates:
                        continue

                    target_node = rng.choice(candidates)
                    context.move_application_vnf(
                        app_ref,
                        {
                            "module_name": module_name,
                            "from_node": source_node,
                            "to_node": target_node,
                        },
                    )
                    occupied_nodes.discard(source_node)
                    occupied_nodes.add(target_node)
                    logging.info(
                        "Moved service %s (app=%s) from %s to %s",
                        module_name,
                        app_ref,
                        source_node,
                        target_node,
                    )


def print_result_summary(results_path: str) -> None:
    trace_link_path = Path(f"{results_path}_link.csv")
    trace_path = Path(f"{results_path}.csv")

    if not trace_link_path.exists() or not trace_path.exists():
        print("No trace files were generated yet.")
        return

    dfl = pd.read_csv(trace_link_path)
    print(f"Number of total messages between nodes: {len(dfl)}")

    df = pd.read_csv(trace_path)
    print(f"Number of requests handled by deployed services: {len(df)}")

    if df.empty:
        return

    sample_app = df["app"].iloc[0]
    df_app = df[df.app == sample_app].copy()
    print(df_app.head())
    print(f"Different nodes where app {sample_app} is deployed")
    print(np.unique(df_app["TOPO.dst"]))
    print("Number of requests handled at each position: node_id - requests")
    print(df_app.groupby(["TOPO.dst"])["id"].count())


def main() -> None:
    scenario_dir = Path(__file__).parent
    results_dir = scenario_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    simulation_duration = 20_000
    seed = 0
    random.seed(seed)

    infrastructure = Infrastructure(
        path_to_lab_scenario=scenario_dir,
        results_path=results_dir,
    )
    simulation = Simulation(infrastructure=infrastructure, seed=seed)

    app_refs: list[str | int] = [
        item.get("id", item["name"])
        for item in infrastructure.service_definitions_data
    ]
    process = RandomServiceMovementProcess(app_refs=app_refs)
    process_distribution = deterministicDistributionStartPoint(
        simulation_duration / 4.0,
        simulation_duration / 20.0,
        name="RandomServiceMovement",
    )

    simulation.register_process(
        "RandomServiceMovement",
        process,
        process_distribution,
    )

    start_time = time.time()
    try:
        logging.info("Performing simulation with API layer primitives")
        simulation.run(stop_time=simulation_duration, step=2_000.0)
    finally:
        simulation.stop()

    print(f"\n--- {time.time() - start_time:.2f} seconds ---")
    print("Simulation Done!")
    print_result_summary(simulation.results_path)


if __name__ == "__main__":
    main()
