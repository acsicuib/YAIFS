"""
Greedy API-layer scenario for the multi-agent topology.

Each generated user is assigned exactly one application instance. A dedicated
copy of that application is created and all its VNFs are deployed on the
worker node closest to the user.
"""

from __future__ import annotations

import copy
import random
import time
from pathlib import Path

import networkx as nx
import pandas as pd

from yafs.api import Infrastructure, Simulation
from yafs.distribution import deterministicDistributionStartPoint
from yafs.topology import Topology


def worker_nodes(simulation: Simulation) -> list[str]:
    nodes: list[str] = []
    for item in simulation.list_nodes():
        if str(item.get("node_role")) != "worker":
            continue
        nodes.append(str(item["node"]))
    return nodes


def mec_worker_nodes(simulation: Simulation) -> list[str]:
    nodes: list[str] = []
    for item in simulation.list_nodes():
        if str(item.get("cluster_role")) != "MEC":
            continue
        if str(item.get("node_role")) != "worker":
            continue
        nodes.append(str(item["node"]))
    return nodes


def reduce_mec_worker_speed(
    simulation: Simulation,
    *,
    mec_worker_ipt: float,
) -> int:
    updated = 0
    graph = simulation.infrastructure.topology.G
    for node_name, attrs in graph.nodes(data=True):
        if str(attrs.get("cluster_role")) != "MEC":
            continue
        if str(attrs.get("node_role")) != "worker":
            continue
        attrs[Topology.NODE_IPT] = float(mec_worker_ipt)
        updated += 1
    return updated


def nearest_worker_node(
    simulation: Simulation,
    *,
    source_node: str,
    candidate_nodes: list[str],
) -> str:
    graph = simulation.infrastructure.topology.G
    ranked: list[tuple[int, str]] = []

    for node in candidate_nodes:
        try:
            distance = nx.shortest_path_length(graph, source=source_node, target=node)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
        ranked.append((int(distance), str(node)))

    if not ranked:
        raise RuntimeError(f"No reachable worker node was found from source node '{source_node}'")

    ranked.sort(key=lambda item: (item[0], item[1]))
    return ranked[0][1]


def clone_application_definition(
    base_definition: dict,
    *,
    instance_tag: str,
) -> tuple[dict, str]:
    payload = copy.deepcopy(base_definition)
    original_name = str(payload["name"])
    new_name = f"{original_name}::{instance_tag}"
    payload["name"] = new_name
    payload["id"] = new_name

    module_map: dict[str, str] = {}
    for module in payload.get("module", []):
        old_name = str(module["name"])
        new_module_name = f"{instance_tag}__{old_name}"
        module_map[old_name] = new_module_name
        module["name"] = new_module_name

    message_map: dict[str, str] = {}
    entry_message_name = None
    for message in payload.get("message", []):
        old_name = str(message["name"])
        new_message_name = f"{instance_tag}__{old_name}"
        message_map[old_name] = new_message_name
        message["name"] = new_message_name
        if str(message.get("s")) != "None":
            message["s"] = module_map[str(message["s"])]
        if str(message.get("d")) != "None":
            message["d"] = module_map[str(message["d"])]
        if str(message.get("s")) == "None":
            entry_message_name = new_message_name

    for transmission in payload.get("transmission", []):
        transmission["message_in"] = message_map[str(transmission["message_in"])]
        transmission["module"] = module_map[str(transmission["module"])]
        if "message_out" in transmission:
            transmission["message_out"] = message_map[str(transmission["message_out"])]

    if entry_message_name is None:
        raise RuntimeError(f"Application template '{original_name}' has no entry message")

    return payload, entry_message_name


class GreedyUserApplicationBurstProcess:
    def __init__(
        self,
        *,
        simulation: Simulation,
        app_templates: list[dict],
        candidate_user_nodes: list[str],
        candidate_deployment_nodes: list[str],
        users_per_activation: int,
        user_lambda: float,
        max_activations: int,
    ) -> None:
        self.simulation = simulation
        self.app_templates = [copy.deepcopy(item) for item in app_templates]
        self.candidate_user_nodes = [str(node) for node in candidate_user_nodes]
        self.candidate_deployment_nodes = [str(node) for node in candidate_deployment_nodes]
        self.users_per_activation = int(users_per_activation)
        self.user_lambda = float(user_lambda)
        self.max_activations = int(max_activations)
        self.activation_count = 0
        self.instance_counter = 0
        self.created_by_base_app: dict[str, int] = {}

    def __call__(self, context) -> None:
        if self.activation_count >= self.max_activations:
            return
        self.activation_count += 1
        rng = context.rng

        for _ in range(self.users_per_activation):
            template = copy.deepcopy(rng.choice(self.app_templates))
            base_name = str(template["name"])
            self.instance_counter += 1
            instance_tag = f"appinst{self.instance_counter:04d}"

            user_node = rng.choice(self.candidate_user_nodes)
            deployment_node = nearest_worker_node(
                self.simulation,
                source_node=user_node,
                candidate_nodes=self.candidate_deployment_nodes,
            )

            app_definition, entry_message_name = clone_application_definition(
                template,
                instance_tag=instance_tag,
            )
            app_ref = app_definition["id"]

            self.simulation.create_application(app_definition)
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
            context.deploy_application_vnfs(app_ref, placement_definition)
            context.create_user(
                app_ref=app_ref,
                message=entry_message_name,
                node_id=user_node,
                lambda_value=self.user_lambda,
            )
            self.created_by_base_app[base_name] = self.created_by_base_app.get(base_name, 0) + 1


class GreedyHotspotUsersProcess:
    def __init__(
        self,
        *,
        simulation: Simulation,
        app_template: dict,
        node_id: str,
        candidate_deployment_nodes: list[str],
        count: int,
        user_lambda: float,
        move_time: float | None = None,
        move_to: str | None = None,
        remove_time: float | None = None,
        remove_fraction: float = 0.0,
    ) -> None:
        self.simulation = simulation
        self.app_template = copy.deepcopy(app_template)
        self.node_id = str(node_id)
        self.candidate_deployment_nodes = [str(node) for node in candidate_deployment_nodes]
        self.count = int(count)
        self.user_lambda = float(user_lambda)
        self.move_time = None if move_time is None else float(move_time)
        self.move_to = None if move_to is None else str(move_to)
        self.remove_time = None if remove_time is None else float(remove_time)
        self.remove_fraction = max(0.0, min(float(remove_fraction), 1.0))
        self.created = False
        self.moved = False
        self.removed = False
        self.instance_counter = 0
        self.user_des: list[int] = []

    def __call__(self, context) -> None:
        if not self.created:
            deployment_node = nearest_worker_node(
                self.simulation,
                source_node=self.node_id,
                candidate_nodes=self.candidate_deployment_nodes,
            )
            for _ in range(self.count):
                self.instance_counter += 1
                instance_tag = f"hotspot{self.instance_counter:04d}"
                app_definition, entry_message_name = clone_application_definition(
                    self.app_template,
                    instance_tag=instance_tag,
                )
                app_ref = app_definition["id"]
                self.simulation.create_application(app_definition)
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
                context.deploy_application_vnfs(app_ref, placement_definition)
                created = context.create_user(
                    app_ref=app_ref,
                    message=entry_message_name,
                    node_id=self.node_id,
                    lambda_value=self.user_lambda,
                )
                self.user_des.append(int(created["des"]))
            self.created = True

        if (
            self.move_time is not None
            and self.move_to is not None
            and not self.moved
            and float(context.now) >= self.move_time
        ):
            for user_des in self.user_des:
                try:
                    context.move_user(user_des, self.move_to)
                except ValueError:
                    pass
            self.moved = True

        if (
            self.remove_time is not None
            and not self.removed
            and float(context.now) >= self.remove_time
        ):
            remove_count = int(round(len(self.user_des) * self.remove_fraction))
            remove_count = max(0, min(remove_count, len(self.user_des)))
            to_remove = set(self.user_des[:remove_count])
            for user_des in list(to_remove):
                try:
                    context.remove_user(user_des)
                except ValueError:
                    pass
            self.user_des = [user_des for user_des in self.user_des if user_des not in to_remove]
            self.removed = True


def print_created_application_summary(process: GreedyUserApplicationBurstProcess) -> None:
    total = sum(process.created_by_base_app.values())
    print("\nCreated application instances:")
    for app_name in sorted(process.created_by_base_app):
        print(f"  base_app={app_name} created_instances={process.created_by_base_app[app_name]}")
    print(f"  total_created_instances={total}")


def print_response_time_summary_by_base_app(results_dir: Path) -> None:
    print("\nResponse time metrics by base application:")
    trace_path = results_dir / "sim_trace.csv"
    if not trace_path.exists():
        print("  no trace file found")
        return

    frame = pd.read_csv(trace_path)
    if frame.empty:
        print("  trace file is empty")
        return

    grouped = (
        frame.groupby(["app", "id"], dropna=False)
        .agg(
            time_emit=("time_emit", "min"),
            time_out=("time_out", "max"),
        )
        .reset_index()
    )
    grouped["response_time"] = grouped["time_out"] - grouped["time_emit"]
    grouped["base_app"] = grouped["app"].astype(str).str.split("::").str[0]

    summary = (
        grouped.groupby("base_app", dropna=False)
        .agg(
            requests_total=("id", "nunique"),
            response_mean=("response_time", "mean"),
            response_p95=("response_time", lambda series: series.quantile(0.95)),
            response_max=("response_time", "max"),
        )
        .reset_index()
    )

    for row in summary.itertuples(index=False):
        print(
            f"  base_app={row.base_app} "
            f"requests_total={int(row.requests_total)} "
            f"response_mean={float(row.response_mean):.4f} "
            f"response_p95={float(row.response_p95):.4f} "
            f"response_max={float(row.response_max):.4f}"
        )


def main() -> None:
    scenario_dir = Path(__file__).resolve().parent
    results_dir = scenario_dir / "results_greedy"
    results_dir.mkdir(parents=True, exist_ok=True)

    seed = 2026
    # replica_count = 20
    activation_interval = 200.0
    activation_count = 20
    post_activation_tail = 1000.0
    users_per_activation = 10
    user_lambda = 100.0
    simulation_duration = activation_interval * activation_count + post_activation_tail
    mec_worker_ipt = 10.0
    hotspot_event = {
        "name": "HotspotUsers-Perception-MEC-I",
        "time": 1000.0,
        "app": "Perception Pipeline",
        "node": "mec-i-1-worker-3",
        "count": 60,
        "user_lambda": 15.0,
        "move_time": 1800.0,
        "move_to": "mec-i-1-worker-4",
        "remove_time": 2600.0,
        "remove_fraction": 0.4,
        "interval": 200.0,
    }

    infrastructure = Infrastructure(
        path_to_lab_scenario=scenario_dir,
        results_path=results_dir,
        placement_definition_path="empty_placements.json",
        users_definition_path="empty_users.json",
    )
    simulation = Simulation(infrastructure=infrastructure, seed=seed)
    updated_mec_nodes = reduce_mec_worker_speed(
        simulation,
        mec_worker_ipt=mec_worker_ipt,
    )

    deployment_nodes = worker_nodes(simulation)
    if not deployment_nodes:
        raise RuntimeError("No worker nodes are available for greedy placement")

    user_nodes = mec_worker_nodes(simulation)
    if not user_nodes:
        raise RuntimeError("No MEC worker nodes are available for user placement")

    process = GreedyUserApplicationBurstProcess(
        simulation=simulation,
        app_templates=infrastructure.service_definitions_data,
        candidate_user_nodes=user_nodes,
        candidate_deployment_nodes=deployment_nodes,
        users_per_activation=users_per_activation,
        user_lambda=user_lambda,
        max_activations=activation_count,
    )
    distribution = deterministicDistributionStartPoint(
        activation_interval,
        activation_interval,
        name="GreedyUserApplicationBurst",
    )
    hotspot_template = next(
        (
            copy.deepcopy(item)
            for item in infrastructure.service_definitions_data
            if str(item.get("name")) == str(hotspot_event["app"])
        ),
        None,
    )
    if hotspot_template is None:
        raise RuntimeError(f"Hotspot application not found: {hotspot_event['app']}")
    hotspot_process = GreedyHotspotUsersProcess(
        simulation=simulation,
        app_template=hotspot_template,
        node_id=str(hotspot_event["node"]),
        candidate_deployment_nodes=deployment_nodes,
        count=int(hotspot_event["count"]),
        user_lambda=float(hotspot_event["user_lambda"]),
        move_time=float(hotspot_event["move_time"]),
        move_to=str(hotspot_event["move_to"]),
        remove_time=float(hotspot_event["remove_time"]),
        remove_fraction=float(hotspot_event["remove_fraction"]),
    )

    start_time = time.time()
    try:
        simulation.register_process(
            "GreedyUserApplicationBurst",
            process,
            distribution,
        )
        simulation.register_process(
            str(hotspot_event["name"]),
            hotspot_process,
            deterministicDistributionStartPoint(
                float(hotspot_event["time"]),
                float(hotspot_event["interval"]),
                name=f"{hotspot_event['name']}-activation",
            ),
        )
        simulation.run(stop_time=simulation_duration, step=2_000.0)
    finally:
        simulation.stop()

    print(f"\n--- {time.time() - start_time:.2f} seconds ---")
    print("Simulation Done!")
    print(f"MEC worker IPT configured to {mec_worker_ipt:.1f} on {updated_mec_nodes} nodes")
    print_created_application_summary(process)
    print(
        f"  hotspot_base_app={hotspot_event['app']} "
        f"created_instances={hotspot_process.instance_counter} "
        f"remaining_users={len(hotspot_process.user_des)}"
    )
    print_response_time_summary_by_base_app(results_dir)


if __name__ == "__main__":
    main()
