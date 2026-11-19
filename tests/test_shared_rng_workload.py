"""Same seed must yield the same users across different placements.

``ProcessContext.rng`` is a per-process stream seeded from
``f"{simulation_seed}:{process_name}"``. Message forwarding keeps using
``Sim.rng``. That separation stops placement traffic from rewriting the
workload, so comparisons such as ``main_random.py`` versus
``main_greedy.py`` under one seed differ only in placement.
"""

from __future__ import annotations

import hashlib
import json
import random
import tempfile
import unittest
from pathlib import Path

from yafs.api import Infrastructure, Simulation
from yafs.distribution import deterministicDistributionStartPoint
from yafs.topology import Topology

SEED = 0
PROCESS_NAME = "RandomMecUserBurst"
APP_A = "AppA"
APP_B = "AppB"
MODULE_FRONTEND = "frontend"
MODULE_BACKEND = "backend"
MSG_A0 = "A.req"
MSG_A1 = "A.mid"
MSG_A2 = "A.reply"
MSG_B0 = "B.req"
MSG_B1 = "B.mid"
MSG_B2 = "B.reply"

LOGGING_INI = """\
[loggers]
keys=root

[handlers]
keys=consoleHandler

[formatters]
keys=simpleFormatter

[logger_root]
level=WARNING
handlers=consoleHandler

[handler_consoleHandler]
class=StreamHandler
level=WARNING
formatter=simpleFormatter
args=(sys.stderr,)

[formatter_simpleFormatter]
format=%(levelname)s - %(message)s
"""

TOPOLOGY = {
    "labName": "shared-rng-workload",
    "description": "Minimal continuum for process-RNG workload tests",
    "clusters": [
        {
            "name": "mec-0",
            "role": "MEC",
            "region": "region-a",
            "cluster_region": "region-a",
            "nodes": [
                {
                    "name": "mec-0-control-plane",
                    "role": "control-plane",
                    "capacity": {"cpu": "2.0", "memory": "4096m"},
                },
                {
                    "name": "mec-0-worker-1",
                    "role": "worker",
                    "capacity": {"cpu": "1.0", "memory": "3072m"},
                },
                {
                    "name": "mec-0-worker-2",
                    "role": "worker",
                    "capacity": {"cpu": "1.0", "memory": "3072m"},
                },
            ],
        },
        {
            "name": "edc-0",
            "role": "EDC",
            "region": "region-b",
            "cluster_region": "region-b",
            "nodes": [
                {
                    "name": "edc-0-control-plane",
                    "role": "control-plane",
                    "capacity": {"cpu": "2.0", "memory": "4096m"},
                },
                {
                    "name": "edc-0-worker-1",
                    "role": "worker",
                    "capacity": {"cpu": "1.0", "memory": "3072m"},
                },
            ],
        },
    ],
    "links": [
        {
            "from": "mec-0",
            "to": "edc-0",
            "targetOneWayLatencyMs": 5,
            "bandwidth": 10,
            "bidirectional": True,
        }
    ],
}


def _app_definition(
    *,
    app_id: str,
    app_name: str,
    msg0: str,
    msg1: str,
    msg2: str,
    instructions: int,
) -> dict:
    return {
        "id": app_id,
        "name": app_name,
        "has_backward_return": True,
        "vnf_chain": [MODULE_FRONTEND, MODULE_BACKEND],
        "module": [
            {
                "id": f"{app_id}-fe",
                "name": MODULE_FRONTEND,
                "type": "MODULE",
                "RAM": 1,
            },
            {
                "id": f"{app_id}-be",
                "name": MODULE_BACKEND,
                "type": "MODULE",
                "RAM": 1,
            },
        ],
        "message": [
            {
                "id": 0,
                "name": msg0,
                "s": "None",
                "d": MODULE_FRONTEND,
                "bytes": 20,
                "instructions": instructions,
            },
            {
                "id": 1,
                "name": msg1,
                "s": MODULE_FRONTEND,
                "d": MODULE_BACKEND,
                "bytes": 20,
                "instructions": instructions,
            },
            {
                "id": 2,
                "name": msg2,
                "s": MODULE_BACKEND,
                "d": "None",
                "bytes": 20,
                "instructions": instructions,
            },
        ],
        "transmission": [
            {
                "message_in": msg0,
                "module": MODULE_FRONTEND,
                "message_out": msg1,
            },
            {
                "message_in": msg1,
                "module": MODULE_BACKEND,
                "message_out": msg2,
            },
        ],
    }


SERVICES = [
    _app_definition(
        app_id=APP_A,
        app_name=APP_A,
        msg0=MSG_A0,
        msg1=MSG_A1,
        msg2=MSG_A2,
        instructions=200,
    ),
    _app_definition(
        app_id=APP_B,
        app_name=APP_B,
        msg0=MSG_B0,
        msg1=MSG_B1,
        msg2=MSG_B2,
        instructions=200,
    ),
]


class RecordingUserBurstProcess:
    """Mirrors ``RandomMecUserBurstProcess`` and records each created user."""

    def __init__(
        self,
        *,
        app_message_pairs: list[tuple[str, str]],
        candidate_nodes: list[str],
        users_per_activation: int,
        user_lambda: float,
        max_activations: int,
    ) -> None:
        self.app_message_pairs = list(app_message_pairs)
        self.candidate_nodes = [str(node) for node in candidate_nodes]
        self.users_per_activation = int(users_per_activation)
        self.user_lambda = float(user_lambda)
        self.max_activations = int(max_activations)
        self.activation_count = 0
        self.created_requests: list[tuple[float, str, str]] = []

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
            self.created_requests.append(
                (float(context.now), str(node_id), str(app_ref))
            )


WORKER_NODES = ["mec-0-worker-1", "mec-0-worker-2", "edc-0-worker-1"]

GREEDY_PLACEMENTS = {
    "initialAllocation": [
        {
            "app": APP_A,
            "module_name": MODULE_FRONTEND,
            "id_resource": "mec-0-worker-1",
        },
        {
            "app": APP_A,
            "module_name": MODULE_BACKEND,
            "id_resource": "mec-0-worker-1",
        },
        {
            "app": APP_B,
            "module_name": MODULE_FRONTEND,
            "id_resource": "mec-0-worker-1",
        },
        {
            "app": APP_B,
            "module_name": MODULE_BACKEND,
            "id_resource": "mec-0-worker-1",
        },
    ]
}


def _write_scenario(
    directory: Path,
    *,
    placements: dict | None = None,
) -> None:
    (directory / "logging.ini").write_text(LOGGING_INI, encoding="utf-8")
    (directory / "topology.json").write_text(
        json.dumps(TOPOLOGY, indent=2),
        encoding="utf-8",
    )
    (directory / "services.json").write_text(
        json.dumps(SERVICES, indent=2),
        encoding="utf-8",
    )
    placement_payload = (
        placements if placements is not None else {"initialAllocation": []}
    )
    (directory / "placements.json").write_text(
        json.dumps(placement_payload, indent=2),
        encoding="utf-8",
    )
    (directory / "users.json").write_text(
        json.dumps({"sources": []}, indent=2),
        encoding="utf-8",
    )


def _worker_nodes(simulation: Simulation) -> list[str]:
    nodes: list[str] = []
    for item in simulation.list_nodes():
        if str(item.get("node_role")) != "worker":
            continue
        nodes.append(str(item["node"]))
    return nodes


def _set_worker_ipt(simulation: Simulation, ipt: float) -> None:
    graph = simulation.infrastructure.topology.G
    for _node_name, attrs in graph.nodes(data=True):
        if str(attrs.get("node_role")) != "worker":
            continue
        attrs[Topology.NODE_IPT] = float(ipt)


def _fingerprint(requests: list[tuple[float, str, str]]) -> str:
    payload = "|".join(
        f"{emission:.6f}:{node}:{app}" for emission, node, app in requests
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _deploy_random_style(simulation: Simulation, workers: list[str]) -> None:
    """Scattered multi-replica placement, analogous to ``main_random.py``."""
    _set_worker_ipt(simulation, ipt=2.0)
    for replica_index in range(3):
        app_ref = APP_A if replica_index % 2 == 0 else APP_B
        frontend_node = workers[replica_index % len(workers)]
        backend_node = workers[(replica_index + 1) % len(workers)]
        simulation.deploy_application_vnfs(
            app_ref,
            {
                "initialAllocation": [
                    {
                        "app": app_ref,
                        "module_name": MODULE_FRONTEND,
                        "id_resource": frontend_node,
                    },
                    {
                        "app": app_ref,
                        "module_name": MODULE_BACKEND,
                        "id_resource": backend_node,
                    },
                ]
            },
        )


def _deploy_greedy_style(simulation: Simulation, workers: list[str]) -> None:
    """Single colocated replica per app, analogous to ``main_greedy.py``."""
    _set_worker_ipt(simulation, ipt=200.0)
    home = workers[0]
    for app_ref in (APP_A, APP_B):
        simulation.deploy_application_vnfs(
            app_ref,
            {
                "initialAllocation": [
                    {
                        "app": app_ref,
                        "module_name": MODULE_FRONTEND,
                        "id_resource": home,
                    },
                    {
                        "app": app_ref,
                        "module_name": MODULE_BACKEND,
                        "id_resource": home,
                    },
                ]
            },
        )


def _run_scenario(
    scenario_dir: Path,
    results_dir: Path,
    *,
    placement: str,
    seed: int = SEED,
) -> tuple[list[tuple[float, str, str]], str]:
    infrastructure = Infrastructure(
        path_to_lab_scenario=scenario_dir,
        results_path=results_dir,
    )
    simulation = Simulation(infrastructure=infrastructure, seed=seed)
    workers = _worker_nodes(simulation)
    if len(workers) < 2:
        raise RuntimeError("Expected at least two worker nodes")

    if placement == "random":
        _deploy_random_style(simulation, workers)
    elif placement == "greedy":
        _deploy_greedy_style(simulation, workers)
    else:
        raise ValueError(f"Unknown placement style: {placement}")

    user_process = RecordingUserBurstProcess(
        app_message_pairs=[(APP_A, MSG_A0), (APP_B, MSG_B0)],
        candidate_nodes=workers,
        users_per_activation=4,
        user_lambda=10.0,
        max_activations=6,
    )
    simulation.register_process(
        PROCESS_NAME,
        user_process,
        deterministicDistributionStartPoint(
            20.0,
            40.0,
            name=f"{PROCESS_NAME}-activation",
        ),
    )

    try:
        simulation.run(stop_time=280.0, step=40.0)
    finally:
        simulation.stop()

    requests = list(user_process.created_requests)
    return requests, _fingerprint(requests)


def _start_burst_simulation(
    scenario_dir: Path,
    results_dir: Path,
    *,
    seed: int = SEED,
    max_activations: int = 6,
) -> tuple[Simulation, RecordingUserBurstProcess]:
    infrastructure = Infrastructure(
        path_to_lab_scenario=scenario_dir,
        results_path=results_dir,
    )
    simulation = Simulation(infrastructure=infrastructure, seed=seed)
    workers = _worker_nodes(simulation)
    if len(workers) < 2:
        raise RuntimeError("Expected at least two worker nodes")

    user_process = RecordingUserBurstProcess(
        app_message_pairs=[(APP_A, MSG_A0), (APP_B, MSG_B0)],
        candidate_nodes=workers,
        users_per_activation=4,
        user_lambda=10.0,
        max_activations=max_activations,
    )
    simulation.register_process(
        PROCESS_NAME,
        user_process,
        deterministicDistributionStartPoint(
            20.0,
            40.0,
            name=f"{PROCESS_NAME}-activation",
        ),
    )
    return simulation, user_process


def _process_registration(simulation: Simulation):
    return simulation._registered_processes[PROCESS_NAME]


def _user_fingerprint(simulation: Simulation) -> list[tuple]:
    report = simulation.list_users()
    return [
        (
            item["des"],
            item["app"],
            item["node"],
            item["message"],
            item["lambda"],
        )
        for item in report["users"]
    ]


class SharedRngWorkloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        self.scenario_dir = self.root / "scenario"
        self.scenario_dir.mkdir()
        _write_scenario(self.scenario_dir)

    def test_process_context_rng_is_independent_of_sim_rng(self) -> None:
        results = self.root / "alias"
        results.mkdir()
        infrastructure = Infrastructure(
            path_to_lab_scenario=self.scenario_dir,
            results_path=results,
        )
        simulation = Simulation(infrastructure=infrastructure, seed=SEED)
        try:
            simulation.register_process(
                PROCESS_NAME,
                lambda context: None,
                deterministicDistributionStartPoint(
                    1.0,
                    1.0,
                    name=f"{PROCESS_NAME}-activation",
                ),
            )
            context = simulation._build_process_context(
                process_name=PROCESS_NAME,
            )
            self.assertIsNot(context.rng, simulation.sim.rng)
            expected = random.Random(f"{SEED}:{PROCESS_NAME}")
            self.assertEqual(context.rng.random(), expected.random())
            simulation.sim.rng.random()
            self.assertEqual(context.rng.random(), expected.random())
        finally:
            simulation.stop()

    def test_identical_placements_reproduce_the_same_user_stream(self) -> None:
        first_requests, first_digest = _run_scenario(
            self.scenario_dir,
            self.root / "same-a",
            placement="random",
        )
        second_requests, second_digest = _run_scenario(
            self.scenario_dir,
            self.root / "same-b",
            placement="random",
        )
        self.assertGreater(len(first_requests), 0)
        self.assertEqual(first_requests, second_requests)
        self.assertEqual(first_digest, second_digest)

    def test_random_versus_greedy_keep_the_same_user_stream(self) -> None:
        """Same seed and user process must keep users identical across placements.

        Placement traffic still advances ``Sim.rng``, but the user process
        draws from its own stream, so ``main_random.py`` versus
        ``main_greedy.py`` comparisons are not confounded by workload drift.
        """
        random_requests, random_digest = _run_scenario(
            self.scenario_dir,
            self.root / "shared-random",
            placement="random",
        )
        greedy_requests, greedy_digest = _run_scenario(
            self.scenario_dir,
            self.root / "shared-greedy",
            placement="greedy",
        )

        self.assertGreater(len(random_requests), 0)
        self.assertEqual(len(random_requests), len(greedy_requests))
        self.assertEqual(random_requests, greedy_requests)
        self.assertEqual(random_digest, greedy_digest)

    def test_fork_keeps_user_stream_when_sim_rng_diverges(self) -> None:
        """A fork must copy the process RNG so later users stay aligned.

        After the fork, the child burns ``Sim.rng`` and adds a denser
        placement. Message decisions therefore diverge, but the per-process
        stream must keep creating the same users on both branches.
        """
        fork_scenario = self.root / "fork-scenario"
        fork_scenario.mkdir()
        _write_scenario(fork_scenario, placements=GREEDY_PLACEMENTS)

        parent, parent_process = _start_burst_simulation(
            fork_scenario,
            self.root / "fork-parent",
            max_activations=8,
        )
        child = None
        try:
            parent.run(stop_time=120.0, step=20.0)
            self.assertGreater(len(parent_process.created_requests), 0)

            parent_registration = _process_registration(parent)
            self.assertIsNotNone(parent_registration.rng)
            self.assertNotEqual(
                parent_registration.rng.getstate(),
                random.Random(f"{SEED}:{PROCESS_NAME}").getstate(),
            )

            child = parent.fork(results_suffix="workload_child")
            child_registration = _process_registration(child)
            child_process = child_registration.callback

            self.assertIsNot(parent_registration.rng, child_registration.rng)
            self.assertEqual(
                parent_registration.rng.getstate(),
                child_registration.rng.getstate(),
            )
            self.assertEqual(
                parent_process.created_requests,
                child_process.created_requests,
            )
            self.assertEqual(_user_fingerprint(parent), _user_fingerprint(child))
            users_at_fork = len(parent_process.created_requests)

            parent_sim_before = parent.sim.rng.getstate()
            for _ in range(500):
                child.sim.rng.random()
            self.assertEqual(parent.sim.rng.getstate(), parent_sim_before)
            self.assertNotEqual(
                parent.sim.rng.getstate(),
                child.sim.rng.getstate(),
            )

            _deploy_random_style(child, WORKER_NODES)

            parent.run(stop_time=280.0, step=20.0)
            child.run(stop_time=280.0, step=20.0)

            self.assertGreater(len(parent_process.created_requests), users_at_fork)
            self.assertEqual(
                parent_process.created_requests,
                child_process.created_requests,
            )
            self.assertEqual(
                _fingerprint(parent_process.created_requests),
                _fingerprint(child_process.created_requests),
            )
            self.assertEqual(
                parent_registration.rng.getstate(),
                child_registration.rng.getstate(),
            )
            self.assertIsNot(parent_registration.rng, child_registration.rng)
        finally:
            parent.stop()
            if child is not None:
                child.stop()


if __name__ == "__main__":
    unittest.main()

