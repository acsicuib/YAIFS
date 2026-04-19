"""
Basic API-layer scenario for the multi-agent topology.

The script loads the scenario topology and application catalog, then deploys
20 random application replicas across the infrastructure by placing each VNF
on a random eligible node.
"""

from __future__ import annotations

import copy
import random
import time
from pathlib import Path

import networkx as nx

from yafs.api import Infrastructure, Simulation
from yafs.distribution import deterministicDistributionStartPoint
from yafs.selection import Selection
from yafs.topology import Topology


class CircularReplicaRouting(Selection):
    def __init__(self) -> None:
        super().__init__()
        self.replicas_by_app: dict[str, list[dict[str, int]]] = {}
        self.assignment_by_user: dict[tuple[str, int], int] = {}
        self.next_replica_index: dict[str, int] = {}

    def register_replica(self, app_name: str, replica_modules: dict[str, int]) -> None:
        replicas = self.replicas_by_app.setdefault(str(app_name), [])
        replicas.append({str(module): int(des) for module, des in replica_modules.items()})

    def _replica_index_for_user(self, app_name: str, user_des: int) -> int:
        key = (str(app_name), int(user_des))
        if key in self.assignment_by_user:
            return self.assignment_by_user[key]

        replicas = self.replicas_by_app.get(str(app_name), [])
        if not replicas:
            raise ValueError(f"No replicas are registered for application '{app_name}'")

        index = self.next_replica_index.get(str(app_name), 0) % len(replicas)
        self.assignment_by_user[key] = index
        self.next_replica_index[str(app_name)] = (index + 1) % len(replicas)
        return index

    def _target_des(self, app_name: str, module_name: str, user_des: int) -> int | None:
        replicas = self.replicas_by_app.get(str(app_name), [])
        if not replicas:
            return None
        replica_index = self._replica_index_for_user(app_name, user_des)
        replica = replicas[replica_index]
        return replica.get(str(module_name))

    def get_path(
        self,
        sim,
        app_name,
        message,
        topology_src,
        alloc_DES,
        alloc_module,
        traffic,
        from_des,
    ):
        user_des = getattr(message, "original_DES_src", None)
        if user_des is None:
            user_des = from_des

        target_des = self._target_des(str(app_name), str(message.dst), int(user_des))
        if target_des is None:
            return [], [None]

        try:
            target_node = alloc_DES[target_des]
            path = list(nx.shortest_path(sim.topology.G, source=topology_src, target=target_node))
            return [path], [target_des]
        except (nx.NetworkXNoPath, nx.NodeNotFound, KeyError):
            return [], [None]

    def get_path_from_failure(
        self,
        sim,
        message,
        link,
        alloc_DES,
        alloc_module,
        traffic,
        ctime,
        from_des,
    ):
        user_des = getattr(message, "original_DES_src", None)
        if user_des is None:
            user_des = from_des

        target_des = self._target_des(str(message.app_name), str(message.dst), int(user_des))
        if target_des is None:
            return [], []

        try:
            idx = message.path.index(link[0])
            node_src = message.path[idx]
            node_dst = alloc_DES[target_des]
            path = list(nx.shortest_path(sim.topology.G, source=node_src, target=node_dst))
            return [path], [target_des]
        except (ValueError, nx.NetworkXNoPath, nx.NodeNotFound, KeyError):
            return [], []


class RandomMecUserBurstProcess:
    def __init__(
        self,
        *,
        app_message_pairs: list[tuple[str | int, str]],
        candidate_nodes: list[str],
        users_per_activation: int,
        user_lambda: float,
        max_activations: int,
    ) -> None:
        if not app_message_pairs:
            raise ValueError("RandomMecUserBurstProcess requires at least one application")
        if not candidate_nodes:
            raise ValueError("RandomMecUserBurstProcess requires candidate MEC worker nodes")

        self.app_message_pairs = list(app_message_pairs)
        self.candidate_nodes = [str(node) for node in candidate_nodes]
        self.users_per_activation = int(users_per_activation)
        self.user_lambda = float(user_lambda)
        self.max_activations = int(max_activations)
        self.activation_count = 0

    def __call__(self, context) -> None:
        if self.activation_count >= self.max_activations:
            return
        self.activation_count += 1
        rng = context.rng

        for _ in range(self.users_per_activation):
            app_ref, message = rng.choice(self.app_message_pairs)
            node_id = rng.choice(self.candidate_nodes)
            context.create_user(
                app_ref=app_ref,
                message=message,
                node_id=node_id,
                lambda_value=self.user_lambda,
            )


class HotspotUsersProcess:
    def __init__(
        self,
        *,
        app_ref: str | int,
        message: str,
        node_id: str,
        count: int,
        user_lambda: float,
        move_time: float | None = None,
        move_to: str | None = None,
        remove_time: float | None = None,
        remove_fraction: float = 0.0,
    ) -> None:
        self.app_ref = app_ref
        self.message = str(message)
        self.node_id = str(node_id)
        self.count = int(count)
        self.user_lambda = float(user_lambda)
        self.move_time = None if move_time is None else float(move_time)
        self.move_to = None if move_to is None else str(move_to)
        self.remove_time = None if remove_time is None else float(remove_time)
        self.remove_fraction = max(0.0, min(float(remove_fraction), 1.0))
        self.created = False
        self.moved = False
        self.removed = False
        self.user_des: list[int] = []

    def __call__(self, context) -> None:
        if not self.created:
            for _ in range(self.count):
                created = context.create_user(
                    app_ref=self.app_ref,
                    message=self.message,
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


def eligible_nodes(simulation: Simulation) -> list[str]:
    nodes: list[str] = []
    for item in simulation.list_nodes():
        if str(item.get("node_role")) == "control-plane":
            continue
        nodes.append(str(item["node"]))
    return nodes


def build_random_replica_definition(
    simulation: Simulation,
    app_ref: str | int,
    *,
    rng: random.Random,
    candidate_nodes: list[str],
) -> dict:
    app_name = str(simulation.infrastructure._resolve_app_name(app_ref))
    module_names = sorted(
        str(name) for name in simulation.infrastructure.services[app_name].services.keys()
    )
    report = simulation.list_application_vnfs(app_ref)
    occupied_by_module = {
        str(vnf_item["vnf"]): {str(node) for node in vnf_item.get("nodes", [])}
        for vnf_item in report.get("vnfs", [])
    }
    placements: list[dict[str, object]] = []

    for module_name in module_names:
        occupied = occupied_by_module.get(module_name, set())
        available = [node for node in candidate_nodes if node not in occupied]
        if not available:
            raise RuntimeError(
                f"No available node remains for module '{module_name}' of application '{app_ref}'"
            )

        placements.append(
            {
                "app": app_ref,
                "module_name": module_name,
                "id_resource": rng.choice(available),
            }
        )

    return {"initialAllocation": placements}


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


def application_entry_messages(infrastructure: Infrastructure) -> list[tuple[str | int, str]]:
    pairs: list[tuple[str | int, str]] = []
    for app_definition in infrastructure.service_definitions_data:
        app_ref = app_definition.get("id", app_definition["name"])
        message_name = None
        for message in app_definition.get("message", []):
            if str(message.get("s")) == "None":
                message_name = str(message["name"])
                break
        if message_name is None:
            raise RuntimeError(
                f"Application {app_definition.get('name')} has no entry message with source 'None'"
            )
        pairs.append((app_ref, message_name))
    return pairs


def application_entry_message_by_name(infrastructure: Infrastructure) -> dict[str, tuple[str | int, str]]:
    entries: dict[str, tuple[str | int, str]] = {}
    for app_definition in infrastructure.service_definitions_data:
        app_name = str(app_definition["name"])
        app_ref = app_definition.get("id", app_definition["name"])
        for message in app_definition.get("message", []):
            if str(message.get("s")) == "None":
                entries[app_name] = (app_ref, str(message["name"]))
                break
    return entries


def deploy_random_replicas(
    simulation: Simulation,
    *,
    app_refs: list[str | int],
    replica_count: int,
    seed: int,
) -> list[dict]:
    rng = random.Random(seed)
    nodes = eligible_nodes(simulation)
    if not nodes:
        raise RuntimeError("The topology has no worker nodes available for random placement")

    deployments: list[dict] = []
    for replica_index in range(replica_count):
        app_ref = app_refs[replica_index % len(app_refs)]
        definition = build_random_replica_definition(
            simulation,
            app_ref,
            rng=rng,
            candidate_nodes=nodes,
        )
        summary = simulation.deploy_application_vnfs(app_ref, definition)
        replica_modules = {
            str(item["vnf"]): int(item["des"])
            for item in summary["created"]
        }
        routing = simulation.infrastructure.routing
        if hasattr(routing, "register_replica"):
            routing.register_replica(str(summary["app"]), replica_modules)
        deployments.append(
            {
                "replica_index": replica_index,
                "app": summary["app"],
                "created_count": summary["created_count"],
                "placements": copy.deepcopy(summary["created"]),
            }
        )
    return deployments


def print_deployment_summary(deployments: list[dict]) -> None:
    print("Replica deployment summary:")
    for item in deployments:
        print(
            f"  replica={item['replica_index']:02d} "
            f"app={item['app']} "
            f"created_vnfs={item['created_count']}"
        )


def print_application_summary(simulation: Simulation, app_refs: list[str | int]) -> None:
    print("\nFinal application placement summary:")
    for app_ref in app_refs:
        report = simulation.list_application_vnfs(app_ref)
        total = sum(int(vnf["deployment_count"]) for vnf in report.get("vnfs", []))
        print(f"  app={report['app']} total_vnf_deployments={total}")
        for vnf_item in report.get("vnfs", []):
            print(
                f"    - {vnf_item['vnf']}: "
                f"{vnf_item['deployment_count']} deployments on {vnf_item['nodes']}"
            )


def print_cost_summary(simulation: Simulation) -> None:
    print("\nPlacement cost summary:")
    metrics = simulation.get_application_metrics_summary(include_return_messages=True)
    total_placement_cost = 0.0

    for item in metrics:
        placement_cost = float(item.get("placement_cost", 0.0) or 0.0)
        vnf_deployments = int(item.get("deployments", 0) or 0)
        app_name = str(item["app"])
        module_count = len(simulation.infrastructure.services[app_name].services)
        app_instances = 0 if module_count <= 0 else vnf_deployments // module_count
        total_placement_cost += placement_cost
        print(
            f"  app={app_name} "
            f"app_instances={app_instances} "
            f"vnf_deployments={vnf_deployments} "
            f"placement_cost={placement_cost:.4f}"
        )

    print(f"  total_placement_cost={total_placement_cost:.4f}")


def print_cluster_role_distribution(simulation: Simulation, app_refs: list[str | int]) -> None:
    node_index = {
        str(item["node"]): item
        for item in simulation.list_nodes()
    }
    totals = {"CDC": 0, "EDC": 0, "MEC": 0}
    per_app: dict[str, dict[str, int]] = {}

    for app_ref in app_refs:
        report = simulation.list_application_vnfs(app_ref)
        app_totals = {"CDC": 0, "EDC": 0, "MEC": 0}

        for vnf_item in report.get("vnfs", []):
            for deployment in vnf_item.get("deployments", []):
                node_name = str(deployment["node"])
                role = str(node_index.get(node_name, {}).get("cluster_role", "UNKNOWN"))
                if role in app_totals:
                    app_totals[role] += 1
                    totals[role] += 1

        per_app[report["app"]] = app_totals

    total_vnfs = sum(totals.values())
    print("\nVNF distribution by cluster type:")
    for app_name, app_totals in per_app.items():
        app_total = sum(app_totals.values())
        print(
            f"  app={app_name} total={app_total} "
            f"CDC={app_totals['CDC']} EDC={app_totals['EDC']} MEC={app_totals['MEC']}"
        )

    print(
        f"  overall total={total_vnfs} "
        f"CDC={totals['CDC']} EDC={totals['EDC']} MEC={totals['MEC']}"
    )


def print_response_time_summary(simulation: Simulation) -> None:
    print("\nResponse time metrics:")
    metrics = simulation.get_application_metrics_summary(include_return_messages=True)
    for item in metrics:
        response_mean = item.get("response_mean")
        response_p50 = item.get("response_p50")
        response_p95 = item.get("response_p95")
        response_max = item.get("response_max")
        network_mean = item.get("network_mean")
        processing_mean = item.get("processing_mean")
        waiting_mean = item.get("waiting_mean")

        def fmt(value: object) -> str:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return "nan"
            if numeric != numeric:
                return "nan"
            return f"{numeric:.4f}"

        print(
            f"  app={item['app']} "
            f"requests_total={int(item.get('requests_total', 0) or 0)} "
            f"successful={int(item.get('requests_successful', 0) or 0)} "
            f"unsuccessful={int(item.get('requests_unsuccessful', 0) or 0)} "
            f"response_mean={fmt(response_mean)} "
            f"network_mean={fmt(network_mean)} "
            f"processing_mean={fmt(processing_mean)} "
            f"waiting_mean={fmt(waiting_mean)} "
            f"p50={fmt(response_p50)} "
            f"p95={fmt(response_p95)} "
            f"max={fmt(response_max)}"
        )


def print_response_time_composition(simulation: Simulation) -> None:
    print("\nResponse time composition:")
    metrics = simulation.get_application_metrics_summary(include_return_messages=True)

    def safe_metric(value: object) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return float("nan")
        return numeric

    for item in metrics:
        app_name = str(item["app"])
        response_mean = safe_metric(item.get("response_mean", float("nan")))
        network_mean = safe_metric(item.get("network_mean", float("nan")))
        processing_mean = safe_metric(item.get("processing_mean", float("nan")))
        waiting_mean = safe_metric(item.get("waiting_mean", float("nan")))

        if response_mean != response_mean or response_mean <= 0.0:
            print(f"  app={app_name} no successful responses to decompose")
            continue

        network_pct = 100.0 * network_mean / response_mean
        processing_pct = 100.0 * processing_mean / response_mean
        waiting_pct = 100.0 * waiting_mean / response_mean

        dominant = max(
            [
                ("network", network_mean),
                ("processing", processing_mean),
                ("waiting", waiting_mean),
            ],
            key=lambda item: item[1],
        )[0]

        print(
            f"  app={app_name} "
            f"network={network_mean:.4f} ({network_pct:.1f}%) "
            f"processing={processing_mean:.4f} ({processing_pct:.1f}%) "
            f"waiting={waiting_mean:.4f} ({waiting_pct:.1f}%) "
            f"dominant={dominant}"
        )


def main() -> None:
    scenario_dir = Path(__file__).resolve().parent
    results_dir = scenario_dir / "results_random"
    results_dir.mkdir(parents=True, exist_ok=True)

    seed = 2026
    replica_count = 20
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
    infrastructure.routing = CircularReplicaRouting()
    simulation = Simulation(infrastructure=infrastructure, seed=seed)
    updated_mec_nodes = reduce_mec_worker_speed(
        simulation,
        mec_worker_ipt=mec_worker_ipt,
    )

    app_refs: list[str | int] = [
        item.get("id", item["name"])
        for item in infrastructure.service_definitions_data
    ]
    if not app_refs:
        raise RuntimeError("No applications were loaded from services.json")

    mec_nodes = mec_worker_nodes(simulation)
    if not mec_nodes:
        raise RuntimeError("No MEC worker nodes are available for user placement")

    user_process = RandomMecUserBurstProcess(
        app_message_pairs=application_entry_messages(infrastructure),
        candidate_nodes=mec_nodes,
        users_per_activation=users_per_activation,
        user_lambda=user_lambda,
        max_activations=activation_count,
    )
    user_distribution = deterministicDistributionStartPoint(
        activation_interval,
        activation_interval,
        name="RandomMecUserBurst",
    )

    start_time = time.time()
    try:
        deployments = deploy_random_replicas(
            simulation,
            app_refs=app_refs,
            replica_count=replica_count,
            seed=seed,
        )
        simulation.register_process(
            "RandomMecUserBurst",
            user_process,
            user_distribution,
        )
        entry_by_app = application_entry_message_by_name(infrastructure)
        hotspot_app_ref, hotspot_message = entry_by_app[str(hotspot_event["app"])]
        simulation.register_process(
            str(hotspot_event["name"]),
            HotspotUsersProcess(
                app_ref=hotspot_app_ref,
                message=hotspot_message,
                node_id=str(hotspot_event["node"]),
                count=int(hotspot_event["count"]),
                user_lambda=float(hotspot_event["user_lambda"]),
                move_time=float(hotspot_event["move_time"]),
                move_to=str(hotspot_event["move_to"]),
                remove_time=float(hotspot_event["remove_time"]),
                remove_fraction=float(hotspot_event["remove_fraction"]),
            ),
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
    print_application_summary(simulation, app_refs)
    print_cost_summary(simulation)
    print_cluster_role_distribution(simulation, app_refs)
    print_response_time_summary(simulation)
    print_response_time_composition(simulation)


if __name__ == "__main__":
    main()
