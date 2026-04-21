from __future__ import annotations

import argparse
import copy
import json
import random
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tutorial_scenarios.multi_agent_scenario.main_greedy import (
    Infrastructure,
    Simulation,
    clone_application_definition,
    mec_worker_nodes,
    nearest_worker_node,
    worker_nodes,
)
from tutorial_scenarios.multi_agent_scenario.main_random import (
    CircularReplicaRouting,
    deploy_random_replicas,
)

SCENARIO_ORDER = {"Random": 0, "Greedy": 1, "Multi-Agent": 2}
DEFAULT_SEED = 2026
DEFAULT_REPLICA_COUNT = 20
DEFAULT_ACTIVATION_COUNT = 20
DEFAULT_USERS_PER_ACTIVATION = 10
DEFAULT_HOTSPOT_EVENT = {
    "app": "Perception Pipeline",
    "node": "mec-i-1-worker-3",
    "count": 60,
}


def parse_args() -> argparse.Namespace:
    scenario_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description=(
            "Compare the temporal response-time breakdown of the random, greedy, "
            "and multi-agent scenarios using the generated sim_trace.csv files."
        )
    )
    parser.add_argument(
        "--random-trace",
        type=Path,
        default=scenario_dir / "results_random" / "sim_trace.csv",
        help="Path to the random scenario event trace CSV.",
    )
    parser.add_argument(
        "--greedy-trace",
        type=Path,
        default=scenario_dir / "results_greedy" / "sim_trace.csv",
        help="Path to the greedy scenario event trace CSV.",
    )
    parser.add_argument(
        "--multi-trace",
        type=Path,
        default=scenario_dir / "results_multi_agent",
        help="Path to the multi-agent scenario event trace CSV or results directory.",
    )
    parser.add_argument(
        "--window",
        type=float,
        default=100.0,
        help="Window size used to aggregate response metrics over time.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output path for the temporal comparison image.",
    )
    parser.add_argument(
        "--bars-output",
        type=Path,
        default=None,
        help="Optional output path for the global bar-chart comparison image.",
    )
    parser.add_argument(
        "--topology",
        type=Path,
        default=scenario_dir / "topology.json",
        help="Path to the topology JSON used to map nodes to cluster types.",
    )
    parser.add_argument(
        "--utilization-output",
        type=Path,
        default=None,
        help="Optional output path for the node-utilization comparison image.",
    )
    parser.add_argument(
        "--boxplots-output",
        type=Path,
        default=None,
        help="Optional output path for the per-application breakdown boxplots image.",
    )
    parser.add_argument(
        "--cost-output",
        type=Path,
        default=None,
        help="Optional output path for the placement cost and VNF deployment comparison image.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not open a matplotlib window.",
    )
    return parser.parse_args()


def resolve_trace_path(path: Path, *, kind: str = "event") -> Path:
    candidate = path.expanduser().resolve()
    if candidate.is_file():
        return candidate

    directory = candidate if candidate.is_dir() else candidate.parent
    if not directory.exists():
        raise FileNotFoundError(f"Trace path does not exist: {path}")

    if kind == "event":
        patterns = ["sim_trace.csv", "sim_trace_*.csv"]
        excluded_suffix = "_link.csv"
    else:
        patterns = ["sim_trace_link.csv", "sim_trace_*_link.csv"]
        excluded_suffix = None

    matches: list[Path] = []
    for pattern in patterns:
        for item in directory.glob(pattern):
            if excluded_suffix is not None and item.name.endswith(excluded_suffix):
                continue
            matches.append(item)
    matches = sorted(set(matches), key=lambda item: (item.stat().st_mtime, item.name))
    if not matches:
        raise FileNotFoundError(f"No {kind} trace matching {path} was found")
    return matches[-1]


def load_trace(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(resolve_trace_path(path, kind="event"))
    if frame.empty:
        return frame

    numeric_columns = ["id", "time_in", "time_out", "time_emit", "time_reception"]
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame["base_app"] = frame["app"].astype(str).str.split("::").str[0]
    return frame


def load_node_cluster_roles(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for cluster in payload.get("clusters", []):
        cluster_role = str(cluster.get("role", "UNKNOWN"))
        for node in cluster.get("nodes", []):
            node_name = node.get("name")
            if node_name is not None:
                mapping[str(node_name)] = cluster_role
    return mapping


def results_dir_from_path(path: Path) -> Path:
    candidate = path.expanduser().resolve()
    if candidate.is_file():
        return candidate.parent
    if candidate.is_dir():
        return candidate
    return candidate.parent


def build_node_metadata(simulation: Simulation) -> dict[str, dict[str, str | float]]:
    metadata: dict[str, dict[str, str | float]] = {}
    graph = simulation.infrastructure.topology.G
    for item in simulation.list_nodes():
        node_name = str(item["node"])
        attrs = graph.nodes[node_name]
        metadata[node_name] = {
            "cluster_role": str(item.get("cluster_role", "UNKNOWN")),
            "node_role": str(item.get("node_role", "UNKNOWN")),
            "cost": float(attrs.get("COST", item.get("cost", item.get("COST", 0.0)) or 0.0) or 0.0),
        }
    return metadata


def summarize_placement_rows(rows: list[dict[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "scenario",
                "base_app",
                "deployments",
                "unique_apps",
                "placement_cost",
                "mean_node_cost",
            ]
        )

    return (
        frame.groupby(["scenario", "base_app"], dropna=False)
        .agg(
            deployments=("module", "count"),
            unique_apps=("app", "nunique"),
            placement_cost=("node_cost", "sum"),
            mean_node_cost=("node_cost", "mean"),
        )
        .reset_index()
    )


def reconstruct_random_placement_rows(
    *,
    scenario_dir: Path,
    seed: int = DEFAULT_SEED,
    replica_count: int = DEFAULT_REPLICA_COUNT,
) -> list[dict[str, object]]:
    infrastructure = Infrastructure(
        path_to_lab_scenario=scenario_dir,
        results_path=Path("/tmp") / "yafs_plot_response_breakdown_random",
        placement_definition_path="empty_placements.json",
        users_definition_path="empty_users.json",
    )
    infrastructure.routing = CircularReplicaRouting()
    simulation = Simulation(infrastructure=infrastructure, seed=seed)
    node_metadata = build_node_metadata(simulation)
    app_refs = [item.get("id", item["name"]) for item in infrastructure.service_definitions_data]
    deployments = deploy_random_replicas(
        simulation,
        app_refs=app_refs,
        replica_count=replica_count,
        seed=seed,
    )

    rows: list[dict[str, object]] = []
    for deployment in deployments:
        app_name = str(deployment["app"])
        for item in deployment.get("placements", []):
            node_name = str(item["node"])
            metadata = node_metadata[node_name]
            rows.append(
                {
                    "scenario": "Random",
                    "app": app_name,
                    "base_app": app_name.split("::")[0],
                    "module": str(item["vnf"]),
                    "node": node_name,
                    "cluster_role": str(metadata["cluster_role"]),
                    "node_cost": float(metadata["cost"]),
                }
            )
    return rows


def reconstruct_greedy_placement_rows(
    *,
    scenario_dir: Path,
    seed: int = DEFAULT_SEED,
    activation_count: int = DEFAULT_ACTIVATION_COUNT,
    users_per_activation: int = DEFAULT_USERS_PER_ACTIVATION,
) -> list[dict[str, object]]:
    infrastructure = Infrastructure(
        path_to_lab_scenario=scenario_dir,
        results_path=Path("/tmp") / "yafs_plot_response_breakdown_greedy",
        placement_definition_path="empty_placements.json",
        users_definition_path="empty_users.json",
    )
    simulation = Simulation(infrastructure=infrastructure, seed=seed)
    node_metadata = build_node_metadata(simulation)
    deployment_nodes = worker_nodes(simulation)
    user_nodes = mec_worker_nodes(simulation)
    app_templates = [copy.deepcopy(item) for item in infrastructure.service_definitions_data]
    rng = random.Random(seed)

    rows: list[dict[str, object]] = []
    instance_counter = 0
    total_nominal_users = activation_count * users_per_activation

    def add_instance(template: dict, *, user_node: str, instance_tag: str) -> None:
        base_name = str(template["name"])
        deployment_node = nearest_worker_node(
            simulation,
            source_node=user_node,
            candidate_nodes=deployment_nodes,
        )
        app_definition, _ = clone_application_definition(template, instance_tag=instance_tag)
        app_ref = app_definition["id"]
        simulation.create_application(app_definition)
        placement_definition = {
            "initialAllocation": [
                {
                    "app": app_ref,
                    "module_name": module["name"],
                    "id_resource": deployment_node,
                }
                for module in app_definition.get("module", [])
            ]
        }
        summary = simulation.deploy_application_vnfs(app_ref, placement_definition)
        metadata = node_metadata[deployment_node]
        for item in summary.get("created", []):
            rows.append(
                {
                    "scenario": "Greedy",
                    "app": str(summary["app"]),
                    "base_app": base_name,
                    "module": str(item["vnf"]),
                    "node": deployment_node,
                    "cluster_role": str(metadata["cluster_role"]),
                    "node_cost": float(metadata["cost"]),
                }
            )

    for _ in range(total_nominal_users):
        template = copy.deepcopy(rng.choice(app_templates))
        instance_counter += 1
        add_instance(
            template,
            user_node=str(rng.choice(user_nodes)),
            instance_tag=f"appinst{instance_counter:04d}",
        )

    hotspot_template = next(
        (
            copy.deepcopy(item)
            for item in infrastructure.service_definitions_data
            if str(item.get("name")) == str(DEFAULT_HOTSPOT_EVENT["app"])
        ),
        None,
    )
    if hotspot_template is None:
        raise RuntimeError(f"Hotspot application not found: {DEFAULT_HOTSPOT_EVENT['app']}")

    for hotspot_index in range(int(DEFAULT_HOTSPOT_EVENT["count"])):
        add_instance(
            copy.deepcopy(hotspot_template),
            user_node=str(DEFAULT_HOTSPOT_EVENT["node"]),
            instance_tag=f"hotspot{hotspot_index + 1:04d}",
        )

    return rows


def load_multi_agent_placement_rows(results_path: Path) -> list[dict[str, object]]:
    snapshot_path = results_dir_from_path(results_path) / "final_placements.json"
    if not snapshot_path.exists():
        return []

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for item in payload:
        rows.append(
            {
                "scenario": "Multi-Agent",
                "app": str(item["app"]),
                "base_app": str(item.get("base_app", str(item["app"]).split("::")[0])),
                "module": str(item["vnf"]),
                "node": str(item["node"]),
                "cluster_role": str(item.get("cluster_role", "UNKNOWN")),
                "node_cost": float(item.get("node_cost", 0.0) or 0.0),
            }
        )
    return rows


def build_placement_summary(
    *,
    scenario_dir: Path,
    multi_results_path: Path,
) -> pd.DataFrame:
    rows = [
        *reconstruct_random_placement_rows(scenario_dir=scenario_dir),
        *reconstruct_greedy_placement_rows(scenario_dir=scenario_dir),
        *load_multi_agent_placement_rows(multi_results_path),
    ]
    return summarize_placement_rows(rows)


def build_request_breakdown(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    src_rows = frame[frame["type"] == "SRC_M"].copy()
    comp_rows = frame[frame["type"] == "COMP_M"].copy()

    src_summary = (
        src_rows.groupby(["base_app", "app", "id"], dropna=False)
        .agg(
            start_time=("time_emit", "min"),
            source_node=("TOPO.src", "first"),
        )
        .reset_index()
    )

    comp_rows["processing_component"] = (comp_rows["time_out"] - comp_rows["time_in"]).clip(lower=0.0)
    comp_rows["waiting_component"] = (comp_rows["time_in"] - comp_rows["time_reception"]).clip(lower=0.0)

    comp_summary = (
        comp_rows.groupby(["base_app", "app", "id"], dropna=False)
        .agg(
            end_time=("time_out", "max"),
            processing_time=("processing_component", "sum"),
            waiting_time=("waiting_component", "sum"),
        )
        .reset_index()
    )

    merged = src_summary.merge(comp_summary, on=["base_app", "app", "id"], how="inner")
    if merged.empty:
        return merged

    merged["response_time"] = (merged["end_time"] - merged["start_time"]).clip(lower=0.0)
    merged["network_time"] = (
        merged["response_time"] - merged["processing_time"] - merged["waiting_time"]
    ).clip(lower=0.0)
    return merged


def build_window_series(requests: pd.DataFrame, *, window: float, label: str) -> pd.DataFrame:
    if requests.empty:
        return pd.DataFrame()

    duration = float(requests["end_time"].max())
    rows: list[dict[str, float | str]] = []
    start = 0.0

    while start < duration:
        end = min(start + window, duration)
        chunk = requests[(requests["end_time"] >= start) & (requests["end_time"] < end)].copy()
        if not chunk.empty:
            summary = (
                chunk.groupby("base_app", dropna=False)
                .agg(
                    response_mean=("response_time", "mean"),
                    network_mean=("network_time", "mean"),
                    processing_mean=("processing_time", "mean"),
                    waiting_mean=("waiting_time", "mean"),
                    requests=("id", "nunique"),
                )
                .reset_index()
            )
            summary["window_start"] = start
            summary["window_end"] = end
            summary["window_mid"] = (start + end) / 2.0
            summary["scenario"] = label
            rows.extend(summary.to_dict(orient="records"))
        start = end

    return pd.DataFrame.from_records(rows)


def safe_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def plot_comparison(
    frame: pd.DataFrame,
    *,
    output: Path | None,
    show_plot: bool,
) -> None:
    if frame.empty:
        raise RuntimeError("No response-time data could be reconstructed from the provided CSV traces")

    apps = sorted(frame["base_app"].dropna().astype(str).unique())
    scenarios = sorted(
        frame["scenario"].dropna().astype(str).unique(),
        key=lambda item: (SCENARIO_ORDER.get(item, 99), item),
    )
    figure, axes = plt.subplots(
        len(apps),
        len(scenarios),
        figsize=(5.4 * len(scenarios), 4.5 * len(apps)),
        sharex=True,
        sharey=False,
    )

    if len(apps) == 1 and len(scenarios) == 1:
        axes = [[axes]]
    elif len(apps) == 1:
        axes = [axes]
    elif len(scenarios) == 1:
        axes = [[axis] for axis in axes]

    colors = {
        "network_mean": "#d1495b",
        "processing_mean": "#00798c",
        "waiting_mean": "#edae49",
    }

    for row_index, app_name in enumerate(apps):
        for col_index, scenario in enumerate(scenarios):
            axis = axes[row_index][col_index]
            app_frame = frame[
                (frame["base_app"].astype(str) == app_name)
                & (frame["scenario"].astype(str) == scenario)
            ].copy()
            app_frame = app_frame.sort_values("window_mid")
            axis.set_title(scenario if row_index == 0 else "", fontsize=14,fontweight="bold")
            axis.set_ylabel("")
            if col_index == 0:
                axis.text(
                    -0.14,
                    0.5,
                    app_name,
                    transform=axis.transAxes,
                    rotation=90,
                    ha="center",
                    va="center",
                    fontsize=14,
                    fontweight="bold",
                    clip_on=False,
                )
                axis.text(
                    -0.10,
                    0.5,
                    "Time units",
                    transform=axis.transAxes,
                    rotation=90,
                    ha="center",
                    va="center",
                    fontsize=11,
                    clip_on=False,
                )

            if app_frame.empty:
                axis.text(0.5, 0.5, "No data", ha="center", va="center", transform=axis.transAxes)
                axis.grid(alpha=0.2)
                continue

            x = safe_series(app_frame["window_mid"])
            network = safe_series(app_frame["network_mean"])
            processing = safe_series(app_frame["processing_mean"])
            waiting = safe_series(app_frame["waiting_mean"])
            total = safe_series(app_frame["response_mean"])

            axis.stackplot(
                x,
                network,
                processing,
                waiting,
                labels=["Network", "Processing", "Waiting"],
                colors=[
                    colors["network_mean"],
                    colors["processing_mean"],
                    colors["waiting_mean"],
                ],
                alpha=0.8,
            )
            axis.plot(x, total, color="#222222", linewidth=1.5, label="Response mean")
            axis.grid(alpha=0.2)
            if row_index == 0 and col_index == 0:
                axis.legend(loc="upper left")

    for axis in axes[-1]:
        axis.set_xlabel("Simulation time")

    #figure.suptitle("Response-time breakdown comparison", fontsize=14)
    figure.tight_layout()

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=200, bbox_inches="tight")

    if show_plot:
        plt.show()
    else:
        plt.close(figure)


def build_global_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    return (
        frame.groupby(["scenario", "base_app"], dropna=False)
        .agg(
            response_mean=("response_time", "mean"),
            network_mean=("network_time", "mean"),
            processing_mean=("processing_time", "mean"),
            waiting_mean=("waiting_time", "mean"),
            requests=("id", "nunique"),
        )
        .reset_index()
    )


def build_node_utilization_summary(
    frame: pd.DataFrame,
    *,
    scenario: str,
    node_cluster_roles: dict[str, str],
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    comp_rows = frame[frame["type"] == "COMP_M"].copy()
    if comp_rows.empty:
        return pd.DataFrame()

    comp_rows["service_time"] = (comp_rows["time_out"] - comp_rows["time_in"]).clip(lower=0.0)
    comp_rows["cluster_type"] = comp_rows["TOPO.dst"].astype(str).map(node_cluster_roles).fillna("UNKNOWN")
    observation_window = float(frame["time_out"].max() - frame["time_emit"].min())
    if observation_window <= 0.0:
        observation_window = 1.0

    per_node = (
        comp_rows.groupby(["cluster_type", "TOPO.dst"], dropna=False)
        .agg(
            total_service_time=("service_time", "sum"),
            events=("id", "count"),
        )
        .reset_index()
    )
    per_node["utilization"] = (per_node["total_service_time"] / observation_window).clip(lower=0.0)
    per_node["scenario"] = scenario

    return (
        per_node.groupby(["scenario", "cluster_type"], dropna=False)
        .agg(
            mean_utilization=("utilization", "mean"),
            median_utilization=("utilization", "median"),
            max_utilization=("utilization", "max"),
            nodes=("TOPO.dst", "nunique"),
        )
        .reset_index()
    )


def plot_global_bars(
    summary: pd.DataFrame,
    *,
    output: Path | None,
    show_plot: bool,
) -> None:
    if summary.empty:
        raise RuntimeError("No aggregated response-time data is available for the bar chart")

    apps = sorted(summary["base_app"].dropna().astype(str).unique())
    scenarios = sorted(
        summary["scenario"].dropna().astype(str).unique(),
        key=lambda item: (SCENARIO_ORDER.get(item, 99), item),
    )
    metrics = [
        ("network_mean", "Network", "#d1495b"),
        ("processing_mean", "Processing", "#00798c"),
        ("waiting_mean", "Waiting", "#edae49"),
    ]

    figure, axes = plt.subplots(len(apps), 1, figsize=(5.0 + 2.8 * len(scenarios), 4.2 * len(apps)), sharex=True)
    if len(apps) == 1:
        axes = [axes]

    x = np.arange(len(scenarios))
    width = 0.22

    for axis, app_name in zip(axes, apps):
        app_frame = summary[summary["base_app"].astype(str) == app_name].copy()
        app_frame["scenario"] = pd.Categorical(app_frame["scenario"], categories=scenarios, ordered=True)
        app_frame = app_frame.sort_values("scenario")

        for offset, (column, label, color) in zip([-width, 0.0, width], metrics):
            values = []
            for scenario in scenarios:
                row = app_frame[app_frame["scenario"] == scenario]
                if row.empty:
                    values.append(0.0)
                else:
                    values.append(float(row.iloc[0][column]))
            axis.bar(x + offset, values, width=width, label=label, color=color, alpha=0.9)

        total_values = []
        for scenario in scenarios:
            row = app_frame[app_frame["scenario"] == scenario]
            if row.empty:
                total_values.append(0.0)
            else:
                total_values.append(float(row.iloc[0]["response_mean"]))
        axis.plot(x, total_values, color="#222222", marker="o", linewidth=1.5, label="Response mean")
        axis.set_title(str(app_name))
        axis.set_ylabel("Mean time")
        axis.grid(axis="y", alpha=0.2)
        axis.set_xticks(x, scenarios)
        axis.legend(loc="upper left")

    axes[-1].set_xlabel("Scenario")
    figure.suptitle("Global response-time breakdown comparison", fontsize=14)
    figure.tight_layout()

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=200, bbox_inches="tight")

    if show_plot:
        plt.show()
    else:
        plt.close(figure)


def plot_node_utilization_bars(
    summary: pd.DataFrame,
    *,
    output: Path | None,
    show_plot: bool,
) -> None:
    if summary.empty:
        raise RuntimeError("No node utilization data is available for plotting")

    cluster_types = ["CDC", "EDC", "MEC"]
    scenarios = sorted(
        summary["scenario"].dropna().astype(str).unique(),
        key=lambda item: (SCENARIO_ORDER.get(item, 99), item),
    )
    metrics = [
        ("mean_utilization", "Mean", "#00798c"),
        ("median_utilization", "Median", "#edae49"),
        ("max_utilization", "Max", "#d1495b"),
    ]

    figure, axes = plt.subplots(1, len(cluster_types), figsize=(16, 4.5), sharey=False)
    if len(cluster_types) == 1:
        axes = [axes]

    x = np.arange(len(scenarios))
    width = 0.22

    for axis, cluster_type in zip(axes, cluster_types):
        cluster_frame = summary[summary["cluster_type"].astype(str) == cluster_type].copy()
        cluster_frame["scenario"] = pd.Categorical(cluster_frame["scenario"], categories=scenarios, ordered=True)
        cluster_frame = cluster_frame.sort_values("scenario")

        for offset, (column, label, color) in zip([-width, 0.0, width], metrics):
            values = []
            for scenario in scenarios:
                row = cluster_frame[cluster_frame["scenario"] == scenario]
                values.append(0.0 if row.empty else float(row.iloc[0][column]))
            axis.bar(x + offset, values, width=width, label=label, color=color, alpha=0.9)

        node_counts = []
        for scenario in scenarios:
            row = cluster_frame[cluster_frame["scenario"] == scenario]
            node_counts.append(0 if row.empty else int(row.iloc[0]["nodes"]))

        axis.set_title(f"{cluster_type} nodes")
        axis.set_ylabel("Utilization")
        axis.set_xticks(x, [f"{scenario}\n(nodes={count})" for scenario, count in zip(scenarios, node_counts)])
        axis.grid(axis="y", alpha=0.2)
        axis.legend(loc="upper left")

    figure.suptitle("Mean node utilization by cluster type", fontsize=14)
    figure.tight_layout()

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=200, bbox_inches="tight")

    if show_plot:
        plt.show()
    else:
        plt.close(figure)


def plot_placement_cost_bars(
    summary: pd.DataFrame,
    *,
    output: Path | None,
    show_plot: bool,
) -> None:
    if summary.empty:
        raise RuntimeError("No placement cost data is available for plotting")

    apps = sorted(summary["base_app"].dropna().astype(str).unique())
    scenarios = sorted(
        summary["scenario"].dropna().astype(str).unique(),
        key=lambda item: (SCENARIO_ORDER.get(item, 99), item),
    )

    figure, axes = plt.subplots(
        len(apps),
        2,
        figsize=(11.5, 3.9 * len(apps)),
        sharex=False,
    )
    if len(apps) == 1:
        axes = np.array([axes])

    colors = {
        "Random": "#457b9d",
        "Greedy": "#edae49",
        "Multi-Agent": "#2a9d8f",
    }

    for row_index, app_name in enumerate(apps):
        app_frame = summary[summary["base_app"].astype(str) == app_name].copy()
        app_frame["scenario"] = pd.Categorical(app_frame["scenario"], categories=scenarios, ordered=True)
        app_frame = app_frame.sort_values("scenario")

        cost_values = []
        deployment_values = []
        for scenario in scenarios:
            row = app_frame[app_frame["scenario"] == scenario]
            if row.empty:
                cost_values.append(0.0)
                deployment_values.append(0)
            else:
                cost_values.append(float(row.iloc[0]["placement_cost"]))
                deployment_values.append(int(row.iloc[0]["deployments"]))

        bar_colors = [colors.get(scenario, "#8d99ae") for scenario in scenarios]
        cost_axis = axes[row_index][0]
        deployment_axis = axes[row_index][1]

        cost_axis.bar(scenarios, cost_values, color=bar_colors, alpha=0.9)
        cost_axis.set_title(f"{app_name} | placement cost")
        cost_axis.set_ylabel("Cost")
        cost_axis.grid(axis="y", alpha=0.2)
        for index, value in enumerate(cost_values):
            cost_axis.text(index, value, f"{value:.2f}", ha="center", va="bottom", fontsize=9)

        deployment_axis.bar(scenarios, deployment_values, color=bar_colors, alpha=0.9)
        deployment_axis.set_title(f"{app_name} | VNF deployments")
        deployment_axis.set_ylabel("VNFs")
        deployment_axis.grid(axis="y", alpha=0.2)
        for index, value in enumerate(deployment_values):
            deployment_axis.text(index, value, str(value), ha="center", va="bottom", fontsize=9)

    figure.suptitle("Placement cost and deployed VNF comparison", fontsize=14)
    figure.tight_layout()

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=200, bbox_inches="tight")

    if show_plot:
        plt.show()
    else:
        plt.close(figure)


def print_placement_summary(summary: pd.DataFrame) -> None:
    if summary.empty:
        print("\nPlacement cost and VNF deployment summary: no data")
        return

    display = summary.copy()
    display["scenario"] = pd.Categorical(
        display["scenario"],
        categories=sorted(
            display["scenario"].dropna().astype(str).unique(),
            key=lambda item: (SCENARIO_ORDER.get(item, 99), item),
        ),
        ordered=True,
    )
    display = display.sort_values(["scenario", "base_app"])
    print("\nPlacement cost and VNF deployment summary:")
    for row in display.itertuples(index=False):
        print(
            f"  scenario={row.scenario} "
            f"app={row.base_app} "
            f"vnfs={int(row.deployments)} "
            f"unique_apps={int(row.unique_apps)} "
            f"placement_cost={float(row.placement_cost):.4f} "
            f"mean_node_cost={float(row.mean_node_cost):.4f}"
        )


def plot_breakdown_boxplots(
    requests: pd.DataFrame,
    *,
    output: Path | None,
    show_plot: bool,
) -> None:
    if requests.empty:
        raise RuntimeError("No request-level breakdown data is available for plotting")

    apps = sorted(requests["base_app"].dropna().astype(str).unique())
    scenarios = sorted(
        requests["scenario"].dropna().astype(str).unique(),
        key=lambda item: (SCENARIO_ORDER.get(item, 99), item),
    )
    metrics = [
        ("network_time", "Network", "#d1495b"),
        ("processing_time", "Processing", "#00798c"),
        ("waiting_time", "Waiting", "#edae49"),
    ]

    figure, axes = plt.subplots(
        len(apps),
        len(scenarios),
        figsize=(5.4 * len(scenarios), 4.8 * len(apps)),
        sharey=False,
    )

    if len(apps) == 1 and len(scenarios) == 1:
        axes = [[axes]]
    elif len(apps) == 1:
        axes = [axes]
    elif len(scenarios) == 1:
        axes = [[axis] for axis in axes]

    for row_index, app_name in enumerate(apps):
        for col_index, scenario in enumerate(scenarios):
            axis = axes[row_index][col_index]
            app_frame = requests[
                (requests["base_app"].astype(str) == app_name)
                & (requests["scenario"].astype(str) == scenario)
            ].copy()

            if app_frame.empty:
                axis.set_title(f"{app_name} | {scenario}")
                axis.text(0.5, 0.5, "No data", ha="center", va="center", transform=axis.transAxes)
                axis.axis("off")
                continue

            box_values = [safe_series(app_frame[column]).to_numpy() for column, _, _ in metrics]
            box = axis.boxplot(
                box_values,
                tick_labels=[label for _, label, _ in metrics],
                patch_artist=True,
                showfliers=False,
                medianprops={"color": "#222222", "linewidth": 1.4},
                whiskerprops={"color": "#555555", "linewidth": 1.0},
                capprops={"color": "#555555", "linewidth": 1.0},
            )

            for patch, (_, _, color) in zip(box["boxes"], metrics):
                patch.set_facecolor(color)
                patch.set_alpha(0.8)
                patch.set_edgecolor("#444444")

            axis.set_title(f"{app_name} | {scenario}")
            axis.set_ylabel("Time")
            axis.grid(axis="y", alpha=0.2)

    figure.suptitle(
        "Request-level response-time breakdown boxplots",
        fontsize=14,
    )
    figure.tight_layout()

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=200, bbox_inches="tight")

    if show_plot:
        plt.show()
    else:
        plt.close(figure)


def main() -> None:
    args = parse_args()

    random_requests = build_request_breakdown(load_trace(args.random_trace))
    greedy_requests = build_request_breakdown(load_trace(args.greedy_trace))
    multi_requests = build_request_breakdown(load_trace(args.multi_trace))
    random_requests["scenario"] = "Random"
    greedy_requests["scenario"] = "Greedy"
    multi_requests["scenario"] = "Multi-Agent"
    random_trace = load_trace(args.random_trace)
    greedy_trace = load_trace(args.greedy_trace)
    multi_trace = load_trace(args.multi_trace)
    node_cluster_roles = load_node_cluster_roles(args.topology)
    scenario_dir = Path(__file__).resolve().parent

    random_series = build_window_series(random_requests, window=float(args.window), label="Random")
    greedy_series = build_window_series(greedy_requests, window=float(args.window), label="Greedy")
    multi_series = build_window_series(multi_requests, window=float(args.window), label="Multi-Agent")
    comparison = pd.concat([random_series, greedy_series, multi_series], ignore_index=True)
    request_comparison = pd.concat([random_requests, greedy_requests, multi_requests], ignore_index=True)
    global_summary = build_global_summary(request_comparison)
    utilization_summary = pd.concat(
        [
            build_node_utilization_summary(
                random_trace,
                scenario="Random",
                node_cluster_roles=node_cluster_roles,
            ),
            build_node_utilization_summary(
                greedy_trace,
                scenario="Greedy",
                node_cluster_roles=node_cluster_roles,
            ),
            build_node_utilization_summary(
                multi_trace,
                scenario="Multi-Agent",
                node_cluster_roles=node_cluster_roles,
            ),
        ],
        ignore_index=True,
    )
    placement_summary = build_placement_summary(
        scenario_dir=scenario_dir,
        multi_results_path=args.multi_trace,
    )

    plot_comparison(comparison, output=args.output, show_plot=not args.no_show)
    plot_global_bars(
        global_summary,
        output=args.bars_output,
        show_plot=not args.no_show,
    )
    plot_node_utilization_bars(
        utilization_summary,
        output=args.utilization_output,
        show_plot=not args.no_show,
    )
    plot_breakdown_boxplots(
        request_comparison,
        output=args.boxplots_output,
        show_plot=not args.no_show,
    )
    plot_placement_cost_bars(
        placement_summary,
        output=args.cost_output,
        show_plot=not args.no_show,
    )
    print_placement_summary(placement_summary)


if __name__ == "__main__":
    main()
