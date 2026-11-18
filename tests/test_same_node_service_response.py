"""Regression tests for same-node reply metrics undercount / ZeroDivisionError.

When the last module of a request runs on the user's node, the reply is
delivered with a single-node path. ``Sim.__network_process`` records no link
row for that delivery, and no SINK_M event either. ``service_path_breakdown``
then treats the return stage as missing/incomplete, so ``service_response``
undercounts completed requests.

When every request stays on the same node, ``message_instances`` also hits:

    np.where(link_hops > 0, bytes_transmitted / link_hops, nan)

``np.where`` evaluates the division for every row. With an empty link trace,
``bytes_transmitted`` is an all-NaN object column and the division by zero
raises ``ZeroDivisionError``.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from yafs.application import create_applications_from_json
from yafs.core import Sim
from yafs.distribution import deterministic_distribution
from yafs.metrics import MetricsAnalyzer
from yafs.path_routing import DeviceSpeedAwareRouting
from yafs.placement import NoPlacementOfModules
from yafs.topology import Topology

APP_NAME = "SameNodeApp"
MODULE_NAME = "svc"
REQUEST_MESSAGE = "M.req"
REPLY_MESSAGE = "M.reply"
REQUEST_PERIOD = 10
STOP_TIME = 100
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


def _path_topology(size: int = 3) -> Topology:
    topology = Topology()
    graph = nx.path_graph(size)
    nx.set_edge_attributes(
        graph,
        name="PR",
        values={edge: 1 for edge in graph.edges()},
    )
    nx.set_edge_attributes(
        graph,
        name="BW",
        values={edge: 1 for edge in graph.edges()},
    )
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
    apps = create_applications_from_json(APP_DEFINITION)
    return apps[APP_NAME]


def _run_scenario(
    results_path: Path,
    *,
    module_node: int,
    user_nodes: list[int],
) -> tuple[int, MetricsAnalyzer]:
    topology = _path_topology()
    routing = DeviceSpeedAwareRouting()
    placement = NoPlacementOfModules(name="NoPlacement")
    sim = Sim(topology, default_results_path=str(results_path))

    app = _single_module_app()
    sim.deploy_app(app, placement, routing)
    sim.deploy_module(
        app.name,
        MODULE_NAME,
        app.services[MODULE_NAME],
        [module_node],
    )

    message = app.get_message(REQUEST_MESSAGE)
    for index, node in enumerate(user_nodes):
        sim.deploy_source(
            app.name,
            id_node=node,
            msg=message,
            distribution=deterministic_distribution(
                REQUEST_PERIOD,
                name=f"User-{index}",
            ),
        )

    sim.run(STOP_TIME)

    events = pd.read_csv(f"{results_path}.csv")
    processed = events[
        (events["type"] == Sim.NODE_METRIC) & (events["module"] == MODULE_NAME)
    ]
    analyzer = MetricsAnalyzer(
        defaultPath=str(results_path),
        app_definition=APP_DEFINITION,
    )
    return len(processed), analyzer


class SameNodeServiceResponseIntegrationTests(unittest.TestCase):
    """End-to-end reproduction of the three reported placements."""

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.results = Path(self._directory.name)

    def test_remote_module_counts_all_completed_requests(self) -> None:
        """Control: module on node 1, user on node 0 keeps replies on links."""
        processed, analyzer = _run_scenario(
            self.results / "remote",
            module_node=1,
            user_nodes=[0],
        )
        responses = analyzer.service_response(include_return_messages=True)
        self.assertEqual(processed, 9)
        self.assertEqual(len(responses), processed)

    def test_colocated_module_and_user_does_not_raise_or_undercount(self) -> None:
        """Module and user on node 0 must count every processed request."""
        processed, analyzer = _run_scenario(
            self.results / "colocated",
            module_node=0,
            user_nodes=[0],
        )
        self.assertEqual(processed, 9)
        responses = analyzer.service_response(include_return_messages=True)
        self.assertEqual(len(responses), processed)

    def test_mixed_users_count_both_local_and_remote_replies(self) -> None:
        """Users on nodes 0 and 2 with module on 0 must not drop local replies."""
        processed, analyzer = _run_scenario(
            self.results / "mixed",
            module_node=0,
            user_nodes=[0, 2],
        )
        self.assertEqual(processed, 18)
        responses = analyzer.service_response(include_return_messages=True)
        self.assertEqual(len(responses), processed)


class SameNodeMessageInstancesUnitTests(unittest.TestCase):
    """Focused checks for the empty-link division and missing return stage."""

    def test_message_instances_with_no_link_rows_does_not_divide_by_zero(self) -> None:
        events = pd.DataFrame(
            [
                {
                    "id": 1,
                    "type": "COMP_M",
                    "app": APP_NAME,
                    "module": MODULE_NAME,
                    "message": REQUEST_MESSAGE,
                    "DES.src": 0,
                    "DES.dst": 1,
                    "TOPO.src": 0,
                    "TOPO.dst": 0,
                    "module.src": "None",
                    "service": 0,
                    "time_in": 10.0,
                    "time_out": 10.3,
                    "time_emit": 10.0,
                    "time_reception": 10.0,
                }
            ]
        )
        links = pd.DataFrame(columns=list(MetricsAnalyzer.LINK_COLUMNS))
        analyzer = MetricsAnalyzer(
            app_definition=APP_DEFINITION,
            event_df=events,
            link_df=links,
        )

        instances = analyzer.message_instances()
        self.assertEqual(len(instances), 1)
        self.assertTrue(np.isnan(instances.iloc[0]["payload_bytes"]))

    def test_missing_return_stage_marks_request_incomplete(self) -> None:
        """Forward-only traces (no same-node reply record) stay incomplete."""
        events = pd.DataFrame(
            [
                {
                    "id": 1,
                    "type": "COMP_M",
                    "app": APP_NAME,
                    "module": MODULE_NAME,
                    "message": REQUEST_MESSAGE,
                    "DES.src": 0,
                    "DES.dst": 1,
                    "TOPO.src": 0,
                    "TOPO.dst": 0,
                    "module.src": "None",
                    "service": 0,
                    "time_in": 10.0,
                    "time_out": 10.3,
                    "time_emit": 10.0,
                    "time_reception": 10.0,
                }
            ]
        )
        links = pd.DataFrame(columns=list(MetricsAnalyzer.LINK_COLUMNS))
        analyzer = MetricsAnalyzer(
            app_definition=APP_DEFINITION,
            event_df=events,
            link_df=links,
        )

        paths = analyzer.service_path_breakdown(include_return_messages=True)
        self.assertEqual(len(paths), 1)
        self.assertFalse(bool(paths.iloc[0]["completed"]))
        self.assertIn(REPLY_MESSAGE, paths.iloc[0]["missing_messages"])
        self.assertEqual(
            len(analyzer.service_response(include_return_messages=True)),
            0,
        )

    def test_recorded_same_node_return_completes_the_path(self) -> None:
        """A SINK_M return row with an end time is enough for MetricsAnalyzer."""
        events = pd.DataFrame(
            [
                {
                    "id": 1,
                    "type": "COMP_M",
                    "app": APP_NAME,
                    "module": MODULE_NAME,
                    "message": REQUEST_MESSAGE,
                    "DES.src": 0,
                    "DES.dst": 1,
                    "TOPO.src": 0,
                    "TOPO.dst": 0,
                    "module.src": "None",
                    "service": 0,
                    "time_in": 10.0,
                    "time_out": 10.3,
                    "time_emit": 10.0,
                    "time_reception": 10.0,
                },
                {
                    "id": 1,
                    "type": "SINK_M",
                    "app": APP_NAME,
                    "module": "None",
                    "message": REPLY_MESSAGE,
                    "DES.src": 1,
                    "DES.dst": 0,
                    "TOPO.src": 0,
                    "TOPO.dst": 0,
                    "module.src": MODULE_NAME,
                    "service": 0,
                    "time_in": 10.3,
                    "time_out": 10.3,
                    "time_emit": 10.3,
                    "time_reception": 10.3,
                },
            ]
        )
        links = pd.DataFrame(columns=list(MetricsAnalyzer.LINK_COLUMNS))
        analyzer = MetricsAnalyzer(
            app_definition=APP_DEFINITION,
            event_df=events,
            link_df=links,
        )

        paths = analyzer.service_path_breakdown(include_return_messages=True)
        self.assertEqual(len(paths), 1)
        self.assertTrue(bool(paths.iloc[0]["completed"]))
        self.assertFalse(np.isnan(paths.iloc[0]["end_time"]))
        self.assertEqual(
            len(analyzer.service_response(include_return_messages=True)),
            1,
        )


if __name__ == "__main__":
    unittest.main()
