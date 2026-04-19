from __future__ import annotations

import argparse
import statistics
from pathlib import Path

import networkx as nx

from tutorial_scenarios.multi_agent_scenario.main_random import (
    CircularReplicaRouting,
    Infrastructure,
    Simulation,
    deploy_random_replicas,
    mec_worker_nodes,
)


def module_chain_by_app(infrastructure: Infrastructure) -> dict[str, list[str]]:
    chains: dict[str, list[str]] = {}
    for app_definition in infrastructure.service_definitions_data:
        app_name = str(app_definition["name"])
        chains[app_name] = [str(item["name"]) for item in app_definition.get("module", [])]
    return chains


def nominal_path_latency(graph: nx.Graph, source: str, target: str) -> tuple[float, int]:
    path = nx.shortest_path(graph, source=source, target=target)
    latency = 0.0
    for index in range(len(path) - 1):
        latency += float(graph.edges[path[index], path[index + 1]].get("PR", 0.0) or 0.0)
    return latency, max(len(path) - 1, 0)


def summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "mean": 0.0, "median": 0.0, "p95": 0.0, "max": 0.0}
    ordered = sorted(values)
    p95_index = min(int(round(0.95 * (len(ordered) - 1))), len(ordered) - 1)
    return {
        "min": float(ordered[0]),
        "mean": float(statistics.fmean(ordered)),
        "median": float(statistics.median(ordered)),
        "p95": float(ordered[p95_index]),
        "max": float(ordered[-1]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze nominal per-replica latencies for the random scenario deployment."
    )
    parser.add_argument(
        "--scenario-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Scenario directory containing topology/services definitions.",
    )
    parser.add_argument(
        "--replica-count",
        type=int,
        default=20,
        help="Number of random replicas to deploy for the analysis.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=2026,
        help="Seed used to reproduce the random placement.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    scenario_dir = args.scenario_dir.resolve()

    infrastructure = Infrastructure(
        scenario_dir,
        placement_definition_path="empty_placements.json",
        users_definition_path="empty_users.json",
        results_path=scenario_dir / "tmp_nominal_latency_results",
    )
    infrastructure.routing = CircularReplicaRouting()
    simulation = Simulation(infrastructure)
    graph = infrastructure.topology.G

    app_refs = [item.get("id", item["name"]) for item in infrastructure.service_definitions_data]
    deployments = deploy_random_replicas(
        simulation=simulation,
        app_refs=app_refs,
        replica_count=args.replica_count,
        seed=args.seed,
    )

    chains = module_chain_by_app(infrastructure)
    mec_workers = mec_worker_nodes(simulation)

    replica_rows: list[dict[str, object]] = []
    per_app_cycle_means: dict[str, list[float]] = {}
    per_app_internal_means: dict[str, list[float]] = {}

    for deployment in deployments:
        app_name = str(deployment["app"])
        module_order = chains[app_name]
        placement_map = {
            str(item["vnf"]): str(item["node"])
            for item in deployment.get("placements", [])
        }
        segment_rows: list[tuple[str, str, str, str, float, int]] = []
        internal_latency = 0.0
        internal_hops = 0

        for source_module, target_module in zip(module_order, module_order[1:]):
            source_node = placement_map[source_module]
            target_node = placement_map[target_module]
            segment_latency, segment_hops = nominal_path_latency(graph, source_node, target_node)
            internal_latency += segment_latency
            internal_hops += segment_hops
            segment_rows.append(
                (
                    source_module,
                    source_node,
                    target_module,
                    target_node,
                    segment_latency,
                    segment_hops,
                )
            )

        entry_node = placement_map[module_order[0]]
        exit_node = placement_map[module_order[-1]]

        access_in_values: list[float] = []
        access_out_values: list[float] = []
        cycle_values: list[float] = []
        for worker_node in mec_workers:
            access_in, _ = nominal_path_latency(graph, worker_node, entry_node)
            access_out, _ = nominal_path_latency(graph, exit_node, worker_node)
            access_in_values.append(access_in)
            access_out_values.append(access_out)
            cycle_values.append(access_in + internal_latency + access_out)

        access_in_summary = summarize(access_in_values)
        access_out_summary = summarize(access_out_values)
        cycle_summary = summarize(cycle_values)

        replica_rows.append(
            {
                "app": app_name,
                "replica_index": int(deployment["replica_index"]),
                "entry_node": entry_node,
                "exit_node": exit_node,
                "internal_latency": internal_latency,
                "internal_hops": internal_hops,
                "access_in": access_in_summary,
                "access_out": access_out_summary,
                "cycle": cycle_summary,
                "segments": segment_rows,
            }
        )
        per_app_cycle_means.setdefault(app_name, []).append(cycle_summary["mean"])
        per_app_internal_means.setdefault(app_name, []).append(internal_latency)

    replica_rows.sort(key=lambda item: float(item["cycle"]["mean"]), reverse=True)

    print("Random deployment nominal latency analysis")
    print(f"  scenario_dir={scenario_dir}")
    print(f"  seed={args.seed}")
    print(f"  replica_count={args.replica_count}")
    print(f"  mec_workers={len(mec_workers)}")
    print()
    print("Per-application summary")
    for app_name in sorted(per_app_cycle_means):
        cycle_values = per_app_cycle_means[app_name]
        internal_values = per_app_internal_means[app_name]
        print(
            f"  app={app_name} replicas={len(cycle_values)} "
            f"internal_nominal_mean={statistics.fmean(internal_values):.2f} "
            f"cycle_nominal_mean={statistics.fmean(cycle_values):.2f}"
        )

    print()
    print("Replica details sorted by nominal cycle mean")
    for item in replica_rows:
        cycle = item["cycle"]
        access_in = item["access_in"]
        access_out = item["access_out"]
        print(
            f"  replica={item['replica_index']:02d} app={item['app']} "
            f"internal={item['internal_latency']:.2f} hops={item['internal_hops']} "
            f"cycle_mean={cycle['mean']:.2f} cycle_p95={cycle['p95']:.2f} cycle_max={cycle['max']:.2f}"
        )
        print(
            f"    entry={item['entry_node']} exit={item['exit_node']} "
            f"access_in[min/mean/max]={access_in['min']:.2f}/{access_in['mean']:.2f}/{access_in['max']:.2f} "
            f"access_out[min/mean/max]={access_out['min']:.2f}/{access_out['mean']:.2f}/{access_out['max']:.2f}"
        )
        for source_module, source_node, target_module, target_node, latency, hops in item["segments"]:
            print(
                f"    segment={source_module}->{target_module} "
                f"{source_node}->{target_node} nominal={latency:.2f} hops={hops}"
            )


if __name__ == "__main__":
    main()
