"""
Unified tutorial scenario using core simulator APIs.

This script merges the capabilities shown in tutorial scenarios 01, 02, 03 and 04:
- Basic deployment on a generated topology
- Dynamic service relocation
- Dynamic topology mutations (add/remove nodes)
- Dynamic user lifecycle (create/move/remove)
"""

import logging
import logging.config
import random
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from yafs.application import create_applications_from_json
from yafs.core import Sim
from yafs.distribution import (
    deterministic_distribution,
    deterministicDistributionStartPoint,
)
from yafs.path_routing import DeviceSpeedAwareRouting
from yafs.placement import JSONPlacement
from yafs.topology import Topology


APP_DEFINITIONS = [
    {
        "id": app_id,
        "name": app_id,
        "HwReqs": 1,
        "MaxReqs": 200,
        "MaxLatency": 50,
        "transmission": [
            {
                "message_in": f"M.USER.APP.{app_id}",
                "module": f"{app_id}_01",
            }
        ],
        "module": [
            {
                "id": app_id,
                "name": f"{app_id}_01",
                "type": "MODULE",
                "RAM": 1,
            }
        ],
        "message": [
            {
                "id": app_id,
                "name": f"M.USER.APP.{app_id}",
                "s": "None",
                "d": f"{app_id}_01",
                "bytes": 20,
                "instructions": 30,
            }
        ],
    }
    for app_id in range(7)
]

INITIAL_ALLOCATION = {
    "initialAllocation": [
        {"module_name": f"{app_id}_01", "app": app_id, "id_resource": 0}
        for app_id in range(7)
    ]
}

INITIAL_USERS = [
    {"id_resource": 1, "app": 0, "message": "M.USER.APP.0", "lambda": 200},
    {"id_resource": 2, "app": 1, "message": "M.USER.APP.1", "lambda": 200},
    {"id_resource": 3, "app": 2, "message": "M.USER.APP.2", "lambda": 500},
    {"id_resource": 4, "app": 3, "message": "M.USER.APP.3", "lambda": 500},
]


class UnifiedDynamics:
    """Monitor that mutates services, topology and users during simulation."""

    def __init__(self, app_ids: list[int]):
        self.activations = 0
        self.app_ids = app_ids
        self.dynamic_users = []
        self.dynamic_user_locations = {}

    @staticmethod
    def _nodes_list(sim: Sim) -> list[int]:
        return list(sim.topology.G.nodes())

    def _deploy_static_users(self, sim: Sim) -> None:
        for user in INITIAL_USERS:
            app_name = user["app"]
            app = sim.apps[app_name]
            message = app.get_message(user["message"])
            distribution = deterministic_distribution(
                user["lambda"], name="DeterministicStaticUsers"
            )
            sim.deploy_source(
                app_name,
                id_node=user["id_resource"],
                msg=message,
                distribution=distribution,
            )

    def _create_dynamic_user(self, sim: Sim) -> int:
        app_name = random.choice(self.app_ids)
        app = sim.apps[app_name]
        message = app.get_message(f"M.USER.APP.{app_name}")
        distribution = deterministic_distribution(
            30, name="DeterministicDynamicUsers"
        )
        node = random.choice(self._nodes_list(sim))
        user_des = sim.deploy_source(
            app_name, id_node=node, msg=message, distribution=distribution
        )
        self.dynamic_users.append(user_des)
        self.dynamic_user_locations[user_des] = node
        return user_des

    @staticmethod
    def _get_current_services(sim: Sim) -> defaultdict[str, list[int]]:
        deployed_services = defaultdict(list)
        for app_name, services in sim.alloc_module.items():
            for service_name, des_ids in services.items():
                for des in des_ids:
                    node = sim.alloc_DES.get(des)
                    if node in sim.topology.G.nodes():
                        deployed_services[service_name].append(node)

        return deployed_services

    @staticmethod
    def _is_service_in_node(sim: Sim, service_name: str, node: int) -> bool:
        app_name = int(service_name.split("_", 1)[0])
        all_des_in_node = [des for des, host in sim.alloc_DES.items() if host == node]
        app_services = sim.alloc_module.get(app_name, {})
        for des in app_services.get(service_name, []):
            if des in all_des_in_node:
                return True
        return False

    @staticmethod
    def _undeploy_service(sim: Sim, service_name: str, node: int) -> None:
        app_name = int(service_name.split("_", 1)[0])
        des = sim.get_DES_from_Service_In_Node(node, app_name, service_name)
        if des:
            sim.undeploy_module(app_name, service_name, des)

    @staticmethod
    def _deploy_service(sim: Sim, service_name: str, node: int) -> None:
        app_name = int(service_name.split("_", 1)[0])
        app = sim.apps[app_name]
        sim.deploy_module(app_name, service_name, app.services[service_name], [node])

    def _mutate_services(self, sim: Sim) -> None:
        if random.random() > 0.6:
            return

        services = self._get_current_services(sim)
        for service_name, nodes in services.items():
            for current_node in nodes:
                new_node = random.choice(self._nodes_list(sim))
                if self._is_service_in_node(sim, service_name, new_node):
                    continue
                self._undeploy_service(sim, service_name, current_node)
                self._deploy_service(sim, service_name, new_node)
                logging.info(
                    "Moved service %s from node %s to node %s",
                    service_name,
                    current_node,
                    new_node,
                )

    def _mutate_topology(self, sim: Sim) -> None:
        if random.random() > 0.5:
            return

        nodes = self._nodes_list(sim)
        if random.random() < 0.7:
            node_a = random.choice(nodes)
            node_b = random.choice(nodes)
            new_id = max(nodes) + 1
            sim.topology.G.add_node(new_id, IPT=100)
            sim.topology.G.add_edge(node_a, new_id, BW=10, PR=10)
            sim.topology.G.add_edge(new_id, node_b, BW=10, PR=10)
            logging.info(
                "Created node %s between nodes %s and %s",
                new_id,
                node_a,
                node_b,
            )
            return

        active_nodes = set(sim.alloc_DES.values())
        removable = [node for node in nodes if node != 0 and node not in active_nodes]
        if len(removable) <= 2:
            return

        node_to_remove = random.choice(removable)
        sim.remove_node(node_to_remove)
        logging.info("Removed node %s", node_to_remove)

    def _mutate_users(self, sim: Sim) -> None:
        self.dynamic_users = [user for user in self.dynamic_users if user in sim.alloc_DES]
        self.dynamic_user_locations = {
            user: sim.alloc_DES[user]
            for user in self.dynamic_users
            if user in sim.alloc_DES
        }

        if not self.dynamic_users:
            user_des = self._create_dynamic_user(sim)
            logging.info(
                "Created first dynamic user %s on node %s",
                user_des,
                self.dynamic_user_locations[user_des],
            )
            return

        event = random.random()
        if event < 0.6:
            user_des = self._create_dynamic_user(sim)
            logging.info(
                "Created dynamic user %s on node %s",
                user_des,
                self.dynamic_user_locations[user_des],
            )
            return

        if event < 0.8:
            user_des = random.choice(self.dynamic_users)
            new_node = random.choice(self._nodes_list(sim))
            old_node = self.dynamic_user_locations.get(user_des)
            sim.alloc_DES[user_des] = new_node
            self.dynamic_user_locations[user_des] = new_node
            logging.info(
                "Moved dynamic user %s from node %s to node %s",
                user_des,
                old_node,
                new_node,
            )
            return

        user_des = random.choice(self.dynamic_users)
        sim.undeploy_source(user_des)
        self.dynamic_users.remove(user_des)
        node = self.dynamic_user_locations.pop(user_des, None)
        logging.info("Removed dynamic user %s from node %s", user_des, node)

    def __call__(self, sim: Sim, routing: DeviceSpeedAwareRouting) -> None:
        self.activations += 1
        routing.invalid_cache_value = True
        self._mutate_topology(sim)
        self._mutate_services(sim)
        self._mutate_users(sim)


def build_topology(size: int, folder_results: Path) -> Topology:
    topology = Topology()
    topology.G = nx.generators.binomial_tree(size)

    edge_attributes = {edge: 1 for edge in topology.G.edges()}
    nx.set_edge_attributes(topology.G, name="PR", values=edge_attributes)
    nx.set_edge_attributes(topology.G, name="BW", values=edge_attributes)
    nx.set_node_attributes(topology.G, name="IPT", values={n: 100 for n in topology.G})

    nx.write_gexf(topology.G, str(folder_results / f"graph_binomial_tree_{size}.gexf"))
    return topology


def run_simulation(stop_time: int, seed: int, folder_results: Path) -> None:
    random.seed(seed)
    logging.info("Running unified tutorial iteration %s", seed)

    topology = build_topology(size=5, folder_results=folder_results)
    apps = create_applications_from_json(APP_DEFINITIONS)
    placement = JSONPlacement(name="Placement", json=INITIAL_ALLOCATION)
    routing = DeviceSpeedAwareRouting()

    sim = Sim(topology, default_results_path=str(folder_results / "sim_trace"))
    for app in apps.values():
        sim.deploy_app(app, placement, routing)

    dynamics = UnifiedDynamics(app_ids=[app["id"] for app in APP_DEFINITIONS])
    dynamics._deploy_static_users(sim)

    monitor_distribution = deterministicDistributionStartPoint(
        stop_time / 4.0, stop_time / 20.0, name="UnifiedDynamics"
    )
    sim.deploy_monitor(
        "UnifiedDynamics",
        dynamics,
        monitor_distribution,
        **{"sim": sim, "routing": routing},
    )

    sim.run(stop_time)
    sim.print_debug_assignaments()
    nx.write_gexf(sim.topology.G, str(folder_results / "final_topology.gexf"))

    logging.info("Dynamic users alive at end: %s", len(dynamics.dynamic_users))
    logging.info("Topology nodes at end: %s", len(sim.topology.G.nodes()))


def print_result_summary(folder_results: Path) -> None:
    trace_link = pd.read_csv(folder_results / "sim_trace_link.csv")
    trace = pd.read_csv(folder_results / "sim_trace.csv")

    print(f"Total network messages: {len(trace_link)}")
    print(f"Total handled requests: {len(trace)}")
    print(f"Apps requested: {np.unique(trace.app)}")

    if len(trace) > 0:
        sample_app = int(trace.app.iloc[0])
        sample = trace[trace.app == sample_app].copy()
        print(f"\nSample stats for app {sample_app}:")
        print(f"- Requests: {len(sample)}")
        print(f"- Deployment nodes: {np.unique(sample['TOPO.dst'])}")
        print(f"- Service DES ids: {np.unique(sample['DES.dst'])}")


if __name__ == "__main__":
    scenario_dir = Path(__file__).parent
    results_dir = scenario_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    logging_config = scenario_dir / "logging.ini"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = results_dir / f"logFile_{timestamp}.log"
    logging.config.fileConfig(
        logging_config,
        defaults={"logfilename": str(log_filename)},
        disable_existing_loggers=False,
    )

    start = time.time()
    run_simulation(stop_time=20000, seed=0, folder_results=results_dir)
    print(f"\n--- {time.time() - start:.2f} seconds ---")
    print("Simulation Done!")

    print_result_summary(results_dir)
