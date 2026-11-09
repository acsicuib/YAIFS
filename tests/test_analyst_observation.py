"""Analyst observation tools: traces, placement, and the MCP catalog."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from tests.fork_support import create_service
from yafs.services import SimulationService
from yafs.services.observation import (
    build_deployments_view,
    build_latency_breakdown,
    build_request_paths,
    build_topology_view,
)
from yafs.transports.mcp_server import build_mcp_server


def _events(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame.from_records(list(rows))


def _request(request_id: int, replica: int, node: str, completion: float) -> dict:
    return {
        "id": request_id,
        "type": "COMP_M",
        "app": "App",
        "module": "backend",
        "message": "M.1",
        "DES.src": 1,
        "DES.dst": replica,
        "TOPO.src": "user-node",
        "TOPO.dst": node,
        "time_in": completion - 2,
        "time_out": completion,
        "time_emit": completion - 5,
        "time_reception": completion - 3,
        "time_wait": 1.0,
        "time_service": 2.0,
    }


def _source(request_id: int, completion: float) -> dict:
    return {
        "id": request_id,
        "type": "SRC_M",
        "app": "App",
        "module": "None",
        "message": "M.0",
        "DES.src": 7,
        "DES.dst": 7,
        "TOPO.src": "user-node",
        "TOPO.dst": "user-node",
        "time_in": completion - 5,
        "time_out": completion - 5,
        "time_emit": completion - 5,
        "time_reception": completion - 5,
        "time_wait": 0.0,
        "time_service": 0.0,
    }


class ObservationViewTests(unittest.TestCase):
    def test_node_filter_returns_the_neighborhood(self) -> None:
        nodes = [
            {"id": "a", "cluster": "c1", "cluster_role": "MEC", "cluster_region": "r", "node_role": "worker"},
            {"id": "b", "cluster": "c1", "cluster_role": "MEC", "cluster_region": "r", "node_role": "worker"},
            {"id": "c", "cluster": "c2", "cluster_role": "CDC", "cluster_region": "r", "node_role": "worker"},
        ]
        links = [
            {"source_id": "a", "destination_id": "b", "delay": 1.0, "bandwidth": 10.0, "properties": {}},
            {"source_id": "b", "destination_id": "c", "delay": 4.0, "bandwidth": 8.0, "properties": {}},
        ]
        view = build_topology_view(
            directed=False,
            nodes=nodes,
            links=links,
            node_id="a",
            include_resources=False,
        )
        self.assertEqual(view["scope"], "node_neighborhood")
        self.assertFalse(view["directed"])
        self.assertEqual([item["node_id"] for item in view["nodes"]], ["a", "b"])
        self.assertEqual(view["links"][0]["delay"], 1.0)
        self.assertEqual(view["links"][0]["bandwidth"], 10.0)

    def test_two_replicas_stay_distinct(self) -> None:
        view = build_deployments_view(
            definitions=[
                {
                    "id": "app-a",
                    "name": "App",
                    "vnf_chain": ["frontend", "backend"],
                    "module": [{"name": "frontend"}, {"name": "backend"}],
                }
            ],
            allocations={"App": {"backend": [3, 4], "frontend": []}},
            alloc_des={3: "mec-1", 4: "cdc-1"},
            application_id="app-a",
        )
        services = {item["service_id"]: item for item in view["applications"][0]["services"]}
        self.assertEqual(services["frontend"]["status"], "undeployed")
        replicas = services["backend"]["replicas"]
        self.assertEqual(
            [(item["replica_id"], item["node_id"]) for item in replicas],
            [("4", "cdc-1"), ("3", "mec-1")],
        )

    def test_distinct_replicas_form_distinct_path_groups(self) -> None:
        events = _events(
            _source(1, 10),
            _request(1, 3, "mec-1", 10),
            _source(2, 12),
            _request(2, 4, "cdc-1", 12),
        )
        links = pd.DataFrame.from_records(
            [
                {"id": 1, "app": "App", "message": "M.1", "src": "user-node", "dst": "mec-1", "latency": 1.0, "ctime": 5},
                {"id": 2, "app": "App", "message": "M.1", "src": "user-node", "dst": "cdc-1", "latency": 2.0, "ctime": 7},
            ]
        )
        view = build_request_paths(
            application_id="App",
            events=events,
            links=links,
            limit=100,
        )
        self.assertEqual(view["availability"], "complete")
        self.assertEqual(view["group_count"], 2)
        nodes = {group["service_hops"][0]["node_id"] for group in view["groups"]}
        self.assertEqual(nodes, {"mec-1", "cdc-1"})
        self.assertFalse(view["truncated"])

    def test_missing_link_rows_are_partial(self) -> None:
        events = _events(_source(1, 10), _request(1, 3, "mec-1", 10))
        view = build_request_paths(
            application_id="App",
            events=events,
            links=pd.DataFrame(),
            limit=10,
        )
        self.assertEqual(view["availability"], "partial")
        self.assertEqual(view["groups"][0]["network_hops"], [])
        self.assertIn("physical_link_sequence", view["groups"][0]["missing_details"])

    def test_time_window_keeps_only_matching_completions(self) -> None:
        events = _events(
            _source(1, 10),
            _request(1, 3, "mec-1", 10),
            _source(2, 80),
            _request(2, 3, "mec-1", 80),
        )
        view = build_request_paths(
            application_id="App",
            events=events,
            links=pd.DataFrame(),
            start_time=0,
            end_time=20,
            limit=10,
        )
        self.assertEqual(view["groups"][0]["request_count"], 1)
        self.assertEqual(view["groups"][0]["request_ids"], ["1"])

    def test_limit_reports_truncation(self) -> None:
        rows = []
        for request_id in range(1, 4):
            rows.append(_source(request_id, float(request_id)))
            rows.append(_request(request_id, request_id, f"n{request_id}", float(request_id)))
        view = build_request_paths(
            application_id="App",
            events=_events(*rows),
            links=pd.DataFrame(),
            limit=2,
        )
        self.assertTrue(view["truncated"])
        self.assertEqual(view["group_count"], 3)
        self.assertEqual(len(view["groups"]), 2)

    def test_empty_trace_is_not_a_zero_latency(self) -> None:
        view = build_latency_breakdown(
            application_id="App",
            events=pd.DataFrame(),
            links=pd.DataFrame(),
        )
        self.assertEqual(view["availability"], "empty")
        self.assertEqual(view["sample_count"], 0)
        self.assertIsNone(view["end_to_end"])
        self.assertEqual(view["components"], [])

    def test_latency_components_are_measured_and_not_marked_additive(self) -> None:
        events = _events(_source(1, 10), _request(1, 3, "mec-1", 10))
        links = pd.DataFrame.from_records(
            [
                {"id": 1, "app": "App", "message": "M.1", "src": "user-node", "dst": "mec-1", "latency": 1.5, "ctime": 5},
            ]
        )
        view = build_latency_breakdown(application_id="App", events=events, links=links)
        self.assertFalse(view["additive"])
        self.assertEqual(view["sample_count"], 1)
        names = {item["component"] for item in view["components"]}
        self.assertIn("link_latency", names)
        self.assertIn("processing", names)
        self.assertEqual(view["end_to_end"]["sample_count"], 1)

    def test_invalid_window_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_request_paths(
                application_id="App",
                events=pd.DataFrame(),
                links=pd.DataFrame(),
                start_time=5,
                end_time=1,
            )


class AnalystServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.service, self.simulation_id = create_service(Path(self._directory.name))

    def test_tools_do_not_advance_or_move_replicas(self) -> None:
        before = self.service.get_state(self.simulation_id)
        deployments = self.service.get_deployments(self.simulation_id)
        topology = self.service.get_topology(self.simulation_id)
        after = self.service.get_state(self.simulation_id)
        self.assertEqual(before.summary.now, after.summary.now)
        self.assertEqual(topology["simulation_id"], self.simulation_id)
        self.assertGreater(len(topology["data"]["nodes"]), 1)
        self.assertFalse(topology["data"]["directed"])
        self.assertGreater(len(deployments["data"]["applications"]), 0)
        replicas = [
            replica
            for application in deployments["data"]["applications"]
            for service in application["services"]
            for replica in service["replicas"]
        ]
        self.assertGreater(len(replicas), 1)
        application_id = deployments["data"]["applications"][0]["name"]
        paths = self.service.get_request_paths(self.simulation_id, application_id)
        self.assertIn(paths["data"]["availability"], {"empty", "unavailable"})
        self.assertIsNone(self.service.get_latency_breakdown(self.simulation_id, application_id)["data"]["end_to_end"])
        self.assertEqual(self.service.get_state(self.simulation_id).summary.now, before.summary.now)

    def test_unknown_simulation_and_application_raise(self) -> None:
        with self.assertRaises(KeyError):
            self.service.get_topology("missing-sim")
        with self.assertRaises(ValueError):
            self.service.get_request_paths(self.simulation_id, "missing-app")


class AnalystCatalogTests(unittest.TestCase):
    def test_analyst_profile_lists_the_tools_with_descriptions(self) -> None:
        app = build_mcp_server(
            SimulationService(),
            profiles=["experiment_analyst"],
        )

        tools = asyncio.run(app.list_tools())
        by_name = {tool.name: tool for tool in tools}
        for name in (
            "get_topology",
            "get_deployments",
            "get_request_paths",
            "get_latency_breakdown",
        ):
            self.assertIn(name, by_name)
            self.assertTrue(by_name[name].description)
            self.assertIn("simulation_id", by_name[name].inputSchema["properties"])
