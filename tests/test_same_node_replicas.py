"""Same-node module replicas: API, routing, and metrics.

Two placements of the same module name on one node are two independent DES
processes with the same functionality: same ``module`` label, same node, but
distinct DES ids, distinct consumer pipes, and distinct metric identities.

Core ``Sim.deploy_module`` already assigns a fresh DES id per placement. The
Simulation API must accept that via ``replicate_application_vnf`` and
``deploy_application_vnfs`` (Prolog-style ``replicate(Si, self)``). Routing
must treat each DES as a distinct replica, and metrics must record valid
per-replica events.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import networkx as nx
import pandas as pd

from tests.fork_support import create_service, run_for, simulation_of
from yafs.application import create_applications_from_json
from yafs.core import Sim
from yafs.distribution import deterministic_distribution
from yafs.metrics import MetricsAnalyzer
from yafs.path_routing import DeviceSpeedAwareRouting
from yafs.placement import NoPlacementOfModules
from yafs.topology import Topology

APP_NAME = "SameNodeReplicaApp"
MODULE_NAME = "svc"
REQUEST_MESSAGE = "M.req"
REPLY_MESSAGE = "M.reply"
APP_DEFINITION = [
    {
        "id": APP_NAME,
        "name": APP_NAME,
        "has_backward_return": True,
        "module": [
            {
                "id": APP_NAME,
                "name": MODULE_NAME,
                "type": "MODULE",
                "RAM": 1,
            }
        ],
        "message": [
            {
                "id": 0,
                "name": REQUEST_MESSAGE,
                "s": "None",
                "d": MODULE_NAME,
                "bytes": 20,
                "instructions": 30,
            },
            {
                "id": 1,
                "name": REPLY_MESSAGE,
                "s": MODULE_NAME,
                "d": "None",
                "bytes": 20,
                "instructions": 30,
            },
        ],
        "transmission": [
            {
                "message_in": REQUEST_MESSAGE,
                "module": MODULE_NAME,
                "message_out": REPLY_MESSAGE,
            }
        ],
    }
]

# App 0 module already placed on this node in using_service_layer_01.
EXISTING_APP = 0
EXISTING_MODULE = "0_TM"
EXISTING_NODE = "mec-0-worker-2"
OTHER_NODE = "mec-0-worker-1"


def _module_replicas(simulation, app_ref, module_name: str) -> list:
    """Force lazy init and return DES ids for one module."""
    app_name = str(simulation.infrastructure._resolve_app_name(app_ref))
    simulation.list_application_vnfs(app_ref)
    return list(
        simulation.sim.alloc_module.get(app_name, {}).get(module_name, [])
    )


def _path_topology(size: int = 3) -> Topology:
    topology = Topology()
    graph = nx.path_graph(size)
    nx.set_edge_attributes(graph, name="PR", values={edge: 1 for edge in graph.edges()})
    nx.set_edge_attributes(graph, name="BW", values={edge: 1 for edge in graph.edges()})
    nx.set_node_attributes(
        graph,
        name="IPT",
        values={node: 100 for node in graph},
    )
    topology.G = graph
    topology.nodeAttributes = {
        node: {"id": node, **dict(graph.nodes[node])} for node in graph.nodes()
    }
    return topology


def _single_module_app():
    return create_applications_from_json(APP_DEFINITION)[APP_NAME]


def _pipe_key(app_name: str, module_name: str, des: int) -> str:
    return f"{app_name}{module_name}{int(des)}"


def _assert_distinct_same_node_processes(
    test_case: unittest.TestCase,
    sim: Sim,
    *,
    app_name: str,
    module_name: str,
    node_id,
    des_a: int,
    des_b: int,
) -> None:
    """Same functionality (module name), same node, different DES processes."""
    test_case.assertNotEqual(
        int(des_a),
        int(des_b),
        "same-node replicas must use different DES process ids",
    )
    test_case.assertEqual(sim.alloc_DES[des_a], node_id)
    test_case.assertEqual(sim.alloc_DES[des_b], node_id)
    test_case.assertIn(des_a, sim.alloc_module[app_name][module_name])
    test_case.assertIn(des_b, sim.alloc_module[app_name][module_name])
    test_case.assertTrue(sim.des_process_running.get(des_a, False))
    test_case.assertTrue(sim.des_process_running.get(des_b, False))

    pipe_a = _pipe_key(app_name, module_name, des_a)
    pipe_b = _pipe_key(app_name, module_name, des_b)
    test_case.assertNotEqual(pipe_a, pipe_b)
    test_case.assertIn(pipe_a, sim.consumer_pipes)
    test_case.assertIn(pipe_b, sim.consumer_pipes)
    test_case.assertIsNot(sim.consumer_pipes[pipe_a], sim.consumer_pipes[pipe_b])


class CoreSameNodeReplicaTests(unittest.TestCase):
    """Engine-level placement of two replicas on one node."""

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.results = Path(self._directory.name)

    def test_same_module_name_on_same_node_gets_distinct_des_ids(self) -> None:
        """Two MODULE placements with the same name are two DES processes."""
        topology = _path_topology()
        app = _single_module_app()
        sim = Sim(topology, default_results_path=str(self.results / "core"))
        sim.deploy_app(app, NoPlacementOfModules(name="NoPlacement"), DeviceSpeedAwareRouting())

        first = sim.deploy_module(
            app.name,
            MODULE_NAME,
            app.services[MODULE_NAME],
            [0],
        )
        second = sim.deploy_module(
            app.name,
            MODULE_NAME,
            app.services[MODULE_NAME],
            [0],
        )

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        des_a, des_b = first[0], second[0]
        replicas = sim.alloc_module[app.name][MODULE_NAME]
        self.assertEqual(sorted(replicas), sorted([des_a, des_b]))
        self.assertEqual(len(set(replicas)), 2)
        _assert_distinct_same_node_processes(
            self,
            sim,
            app_name=app.name,
            module_name=MODULE_NAME,
            node_id=0,
            des_a=des_a,
            des_b=des_b,
        )

    def test_routing_and_metrics_distinguish_same_node_replicas(self) -> None:
        """Routing round-robins same-node DES; traces keep distinct DES.dst."""
        topology = _path_topology()
        routing = DeviceSpeedAwareRouting()
        app = _single_module_app()
        results_path = self.results / "routing-metrics"
        sim = Sim(topology, default_results_path=str(results_path))
        sim.deploy_app(app, NoPlacementOfModules(name="NoPlacement"), routing)

        first = sim.deploy_module(
            app.name,
            MODULE_NAME,
            app.services[MODULE_NAME],
            [1],
        )[0]
        second = sim.deploy_module(
            app.name,
            MODULE_NAME,
            app.services[MODULE_NAME],
            [1],
        )[0]
        _assert_distinct_same_node_processes(
            self,
            sim,
            app_name=app.name,
            module_name=MODULE_NAME,
            node_id=1,
            des_a=first,
            des_b=second,
        )

        message = app.get_message(REQUEST_MESSAGE)
        for index in range(6):
            sim.deploy_source(
                app.name,
                id_node=0,
                msg=message,
                distribution=deterministic_distribution(
                    10,
                    name=f"User-{index}",
                ),
            )

        sim.run(80)

        events = pd.read_csv(f"{results_path}.csv")
        processed = events[
            (events["type"] == Sim.NODE_METRIC) & (events["module"] == MODULE_NAME)
        ]
        served = set(int(value) for value in processed["DES.dst"].dropna())
        self.assertEqual(served, {int(first), int(second)})
        self.assertGreaterEqual(len(processed), 2)
        self.assertGreater(routing.counter[int(first)], 0)
        self.assertGreater(routing.counter[int(second)], 0)

        analyzer = MetricsAnalyzer(
            defaultPath=str(results_path),
            app_definition=APP_DEFINITION,
        )
        responses = analyzer.service_response(include_return_messages=True)
        self.assertGreater(len(responses), 0)
        self.assertFalse(responses["service_response"].isna().any())
        summary = analyzer.summarize_service_response(include_return_messages=True)
        self.assertGreater(len(summary), 0)
        self.assertFalse(summary["response_mean"].isna().any())


class ApiSameNodeReplicaTests(unittest.TestCase):
    """Simulation API must accept replicate(Si, self) on a free node."""

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.results = Path(self._directory.name)

    def test_replicate_to_different_node_succeeds(self) -> None:
        """Control: replicating onto a free node is already supported."""
        service, simulation_id = create_service(self.results / "other-node")
        simulation = simulation_of(service, simulation_id)
        before = _module_replicas(simulation, EXISTING_APP, EXISTING_MODULE)

        result = service.replicate_application_vnf(
            simulation_id,
            EXISTING_APP,
            {
                "module_name": EXISTING_MODULE,
                "to_node": OTHER_NODE,
            },
        )

        after = _module_replicas(simulation, EXISTING_APP, EXISTING_MODULE)
        self.assertEqual(result["status"], "successful")
        self.assertEqual(result["to_node"], OTHER_NODE)
        self.assertEqual(len(after), len(before) + 1)
        self.assertEqual(
            str(simulation.sim.alloc_DES[result["created_des"]]),
            OTHER_NODE,
        )

    def test_replicate_to_same_node_creates_second_replica(self) -> None:
        """replicate(Si, self) must add another DES even if Si already hosts it."""
        service, simulation_id = create_service(self.results / "same-node")
        simulation = simulation_of(service, simulation_id)
        before = _module_replicas(simulation, EXISTING_APP, EXISTING_MODULE)
        self.assertTrue(
            any(
                str(simulation.sim.alloc_DES.get(des)) == EXISTING_NODE
                for des in before
            ),
            f"{EXISTING_MODULE} should already be on {EXISTING_NODE}",
        )

        result = service.replicate_application_vnf(
            simulation_id,
            EXISTING_APP,
            {
                "module_name": EXISTING_MODULE,
                "to_node": EXISTING_NODE,
            },
        )

        after = _module_replicas(simulation, EXISTING_APP, EXISTING_MODULE)
        created = result["created_des"]
        self.assertEqual(result["status"], "successful")
        self.assertEqual(result["to_node"], EXISTING_NODE)
        self.assertEqual(result["replica_count"], len(before) + 1)
        self.assertEqual(len(after), len(before) + 1)
        self.assertNotIn(created, before)
        same_node = [
            des
            for des in after
            if str(simulation.sim.alloc_DES.get(des)) == EXISTING_NODE
        ]
        self.assertGreaterEqual(len(same_node), 2)
        self.assertEqual(len(set(same_node)), len(same_node))
        original = next(des for des in same_node if des != created)
        app_name = str(simulation.infrastructure._resolve_app_name(EXISTING_APP))
        _assert_distinct_same_node_processes(
            self,
            simulation.sim,
            app_name=app_name,
            module_name=EXISTING_MODULE,
            node_id=EXISTING_NODE,
            des_a=original,
            des_b=created,
        )

    def test_deploy_application_vnfs_creates_second_same_node_replica(self) -> None:
        """Bulk deploy must not skip a same-node placement that asks for another replica."""
        service, simulation_id = create_service(self.results / "bulk-same-node")
        simulation = simulation_of(service, simulation_id)
        before = _module_replicas(simulation, EXISTING_APP, EXISTING_MODULE)

        result = service.deploy_application_vnfs(
            simulation_id,
            EXISTING_APP,
            {
                "placements": [
                    {
                        "app": EXISTING_APP,
                        "module_name": EXISTING_MODULE,
                        "id_resource": EXISTING_NODE,
                    }
                ]
            },
        )

        after = _module_replicas(simulation, EXISTING_APP, EXISTING_MODULE)
        self.assertEqual(result["status"], "successful")
        self.assertEqual(result["created_count"], 1)
        self.assertEqual(result["skipped_existing"], [])
        self.assertEqual(len(after), len(before) + 1)
        created = result["created"][0]["des"]
        self.assertNotIn(created, before)
        same_node = [
            des
            for des in after
            if str(simulation.sim.alloc_DES.get(des)) == EXISTING_NODE
        ]
        self.assertGreaterEqual(len(same_node), 2)
        self.assertEqual(len(set(int(des) for des in same_node)), len(same_node))
        original = next(des for des in same_node if des != created)
        app_name = str(simulation.infrastructure._resolve_app_name(EXISTING_APP))
        _assert_distinct_same_node_processes(
            self,
            simulation.sim,
            app_name=app_name,
            module_name=EXISTING_MODULE,
            node_id=EXISTING_NODE,
            des_a=original,
            des_b=created,
        )

    def test_api_same_node_replicas_appear_in_deployments_and_metrics(self) -> None:
        """After replicate(Si, self), both DES stay visible and produce metrics."""
        service, simulation_id = create_service(self.results / "api-metrics")
        simulation = simulation_of(service, simulation_id)
        before = _module_replicas(simulation, EXISTING_APP, EXISTING_MODULE)

        result = service.replicate_application_vnf(
            simulation_id,
            EXISTING_APP,
            {
                "module_name": EXISTING_MODULE,
                "to_node": EXISTING_NODE,
            },
        )
        created = result["created_des"]
        same_node_before = [
            des
            for des in before
            if str(simulation.sim.alloc_DES.get(des)) == EXISTING_NODE
        ]
        self.assertEqual(len(same_node_before), 1)
        original = same_node_before[0]
        self.assertNotEqual(int(original), int(created))
        app_name = str(simulation.infrastructure._resolve_app_name(EXISTING_APP))
        _assert_distinct_same_node_processes(
            self,
            simulation.sim,
            app_name=app_name,
            module_name=EXISTING_MODULE,
            node_id=EXISTING_NODE,
            des_a=original,
            des_b=created,
        )

        listing = simulation.list_application_vnfs(EXISTING_APP)
        module_row = next(
            row for row in listing["vnfs"] if str(row["vnf"]) == EXISTING_MODULE
        )
        listed_des = {int(item["des"]) for item in module_row["deployments"]}
        self.assertIn(int(original), listed_des)
        self.assertIn(int(created), listed_des)
        self.assertGreaterEqual(module_row["deployment_count"], 2)
        self.assertEqual(
            module_row["nodes"].count(EXISTING_NODE),
            sum(
                1
                for item in module_row["deployments"]
                if str(item["node"]) == EXISTING_NODE
            ),
        )

        run_for(service, simulation_id, 2000.0)
        simulation._flush_metrics_if_needed()
        events = pd.read_csv(f"{simulation.results_path}.csv")
        processed = events[
            (events["type"] == "COMP_M") & (events["module"] == EXISTING_MODULE)
        ]
        self.assertGreater(len(processed), 0)
        served = set(int(value) for value in processed["DES.dst"].dropna())
        self.assertTrue(
            {int(original), int(created)}.issubset(served),
            f"expected both same-node replicas in DES.dst, got {served}",
        )

        facts = simulation.read_deployment_facts()
        app_name = str(simulation.infrastructure._resolve_app_name(EXISTING_APP))
        replicas = facts["allocations"][app_name][EXISTING_MODULE]
        self.assertIn(original, replicas)
        self.assertIn(created, replicas)
        self.assertEqual(
            str(facts["alloc_des"][original]),
            EXISTING_NODE,
        )
        self.assertEqual(
            str(facts["alloc_des"][created]),
            EXISTING_NODE,
        )


if __name__ == "__main__":
    unittest.main()
