import copy
import json
import logging
import logging.config
import math
import os
import random
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

import matplotlib.pyplot as plt
import networkx as nx

import pandas as pd
import numpy as np

from yafs.core import Sim
from yafs.application import create_applications_from_json
from yafs.topology import Topology
from yafs.metrics import Metrics, MetricsAnalyzer

from yafs.placement import JSONPlacement
from yafs.path_routing import DeviceSpeedAwareRouting
from yafs.distribution import (
    deterministic_distribution,
    deterministicDistributionStartPoint,
    exponential_distribution,
)

# TODO
# - [ ] The definition of the service should be configured in yaml file
# - [ ] The definition users behaviour
# - [ ] Initial placement of the services


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if np.isnan(numeric) or np.isinf(numeric):
        return default
    return float(numeric)


def _parse_cpu_capacity(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return _safe_float(value, 0.0)

    text = str(value).strip().lower()
    if not text:
        return 0.0
    if text.endswith("m"):
        return _safe_float(text[:-1], 0.0) / 1000.0
    return _safe_float(text, 0.0)


def _parse_memory_capacity(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return _safe_float(value, 0.0)

    text = str(value).strip().lower()
    if not text:
        return 0.0

    units = {
        "ki": 1.0 / 1024.0,
        "mi": 1.0,
        "gi": 1024.0,
        "ti": 1024.0 * 1024.0,
    }
    for suffix, factor in units.items():
        if text.endswith(suffix):
            return _safe_float(text[: -len(suffix)], 0.0) * factor

    if text.endswith("m"):
        return _safe_float(text[:-1], 0.0)
    return _safe_float(text, 0.0)


def _redirect_stdout_log_handlers_to_stderr() -> None:
    """
    MCP over stdio requires stdout to be reserved for protocol frames.

    When enabled via environment variable, move any logging StreamHandler
    currently targeting stdout over to stderr.
    """
    if os.environ.get("YAFS_MCP_STDIO_SAFE") != "1":
        return

    manager = logging.root.manager
    logger_names = list(manager.loggerDict.keys())
    candidate_loggers = [logging.getLogger()] + [
        logging.getLogger(name) for name in logger_names
    ]

    for logger in candidate_loggers:
        for handler in getattr(logger, "handlers", []):
            if (
                isinstance(handler, logging.StreamHandler)
                and getattr(handler, "stream", None) is sys.stdout
            ):
                handler.setStream(sys.stderr)


def _format_cpu_capacity(value: float) -> str:
    return str(float(value))


def _format_memory_capacity(value: float) -> str:
    return f"{float(value)}m"


DEFAULT_SERVICES_DEFINITION = "services.json"
DEFAULT_USERS_DEFINITION = "users.json"
DEFAULT_PLACEMENT_DEFINITION = "placements.json"
DEFAULT_TOPOLOGY = "topology.json"


@dataclass
class RegisteredProcess:
    name: str
    callback: Callable[..., Any]
    distribution: Any
    params: dict[str, Any] = field(default_factory=dict)
    kind: str | None = None
    definition: dict[str, Any] | None = None
    enabled: bool = True
    monitor_des: int | None = None
    activation_count: int = 0


class ProcessContext:
    """
    Stable runtime facade exposed to user-defined simulation processes.

    The context intentionally exposes domain operations instead of the raw
    ``Sim`` object so higher layers can evolve without coupling custom
    processes to core internals.
    """

    def __init__(
        self,
        simulation: "Simulation",
        *,
        process_name: str | None = None,
        process_des: int | None = None,
    ) -> None:
        self._simulation = simulation
        self.process_name = process_name
        self.process_des = process_des

    @property
    def now(self) -> float:
        return float(self._simulation.sim.env.now)

    @property
    def rng(self) -> random.Random:
        return self._simulation.sim.rng

    def list_nodes(self) -> list[dict[str, Any]]:
        return self._simulation.list_nodes()

    def list_clusters(self) -> list[dict[str, Any]]:
        return self._simulation.list_clusters()

    def list_users(
        self,
        *,
        app_ref: str | int | None = None,
        node_id: str | None = None,
        cluster_name: str | None = None,
    ) -> dict[str, Any]:
        return self._simulation.list_users(
            app_ref=app_ref,
            node_id=node_id,
            cluster_name=cluster_name,
        )

    def list_application_vnfs(self, app_ref: str | int) -> dict[str, Any]:
        return self._simulation.list_application_vnfs(app_ref)

    def get_node_resource_summary(
        self,
        node_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._simulation.get_node_resource_summary(node_id=node_id)

    def create_users(
        self,
        definition: str | Path | Mapping[str, Any],
        *,
        nodes: str | list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        return self._simulation.create_users(definition, nodes=nodes)

    def create_user(
        self,
        *,
        app_ref: str | int,
        message: str,
        node_id: str,
        lambda_value: float = 1.0,
    ) -> dict[str, Any]:
        created = self._simulation.create_users(
            {
                "sources": [
                    {
                        "app": app_ref,
                        "message": message,
                        "id_resource": node_id,
                        "lambda": lambda_value,
                    }
                ]
            }
        )
        return created["created"][0]

    def remove_user(self, user_des: int) -> dict[str, Any]:
        return self._simulation.remove_user(user_des)

    def remove_users_by_application(self, app_ref: str | int) -> dict[str, Any]:
        return self._simulation.remove_users_by_application(app_ref)

    def remove_users_by_node(self, node_id: str) -> dict[str, Any]:
        return self._simulation.remove_users_by_node(node_id)

    def remove_users_by_cluster(self, cluster_name: str) -> dict[str, Any]:
        return self._simulation.remove_users_by_cluster(cluster_name)

    def move_user(self, user_des: int, target_node_id: str) -> dict[str, Any]:
        return self._simulation.move_user(user_des, target_node_id)

    def move_users_to_node(
        self,
        source_node_id: str,
        target_node_id: str,
    ) -> dict[str, Any]:
        return self._simulation.move_users_to_node(source_node_id, target_node_id)

    def update_user_lambda(self, user_des: int, new_lambda: float) -> dict[str, Any]:
        return self._simulation.update_user_lambda(user_des, new_lambda)

    def update_application_users_lambda(
        self,
        app_ref: str | int,
        new_lambda: float,
    ) -> dict[str, Any]:
        return self._simulation.update_application_users_lambda(app_ref, new_lambda)

    def deploy_application_vnfs(
        self,
        app_ref: str | int,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._simulation.deploy_application_vnfs(app_ref, definition)

    def deploy_application_vnfs_generated(
        self,
        app_ref: str | int,
        *,
        strategy: str = "spread",
        allowed_nodes: list[str] | tuple[str, ...] | None = None,
        include_control_plane: bool = True,
        seed: int | None = None,
    ) -> dict[str, Any]:
        return self._simulation.deploy_application_vnfs_generated(
            app_ref,
            strategy=strategy,
            allowed_nodes=allowed_nodes,
            include_control_plane=include_control_plane,
            seed=seed,
        )

    def move_application_vnf(
        self,
        app_ref: str | int,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._simulation.move_application_vnf(app_ref, definition)

    def replicate_application_vnf(
        self,
        app_ref: str | int,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._simulation.replicate_application_vnf(app_ref, definition)

    def remove_application_vnf(
        self,
        app_ref: str | int,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._simulation.remove_application_vnf(app_ref, definition)

    def remove_application_vnfs(self, app_ref: str | int) -> dict[str, Any]:
        return self._simulation.remove_application_vnfs(app_ref)

    def create_cluster(
        self,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._simulation.create_cluster(definition)

    def create_nodes(
        self,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._simulation.create_nodes(definition)

    def update_node(
        self,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._simulation.update_node(definition)

    def remove_node(self, node_id: str) -> dict[str, Any]:
        return self._simulation.remove_node(node_id)

    def remove_cluster(self, cluster_name: str) -> dict[str, Any]:
        return self._simulation.remove_cluster(cluster_name)

    def remove_link(self, source_node_id: str, target_node_id: str) -> dict[str, Any]:
        return self._simulation.remove_link(source_node_id, target_node_id)

    def restore_link(self, source_node_id: str, target_node_id: str) -> dict[str, Any]:
        return self._simulation.restore_link(source_node_id, target_node_id)

    def restore_node(self, node_id: str) -> dict[str, Any]:
        return self._simulation.restore_node(node_id)


class RandomUserMobilityProcess:
    def __init__(
        self,
        *,
        app_ref: str | int,
        message: str,
        user_lambda: float = 1.0,
        candidate_nodes: list[str] | tuple[str, ...] | None = None,
        create_probability: float = 0.6,
        move_probability: float = 0.2,
        remove_probability: float = 0.2,
        max_users: int | None = None,
    ) -> None:
        self.app_ref = app_ref
        self.message = str(message)
        self.user_lambda = float(user_lambda)
        self.candidate_nodes = (
            None if candidate_nodes is None else [str(node) for node in candidate_nodes]
        )
        self.create_probability = float(create_probability)
        self.move_probability = float(move_probability)
        self.remove_probability = float(remove_probability)
        self.max_users = None if max_users is None else int(max_users)
        self.user_des: list[int] = []

    def _pick_node(self, context: ProcessContext) -> str:
        if self.candidate_nodes:
            return context.rng.choice(self.candidate_nodes)
        nodes = [str(item["node"]) for item in context.list_nodes()]
        if not nodes:
            raise ValueError("User mobility process requires at least one node")
        return context.rng.choice(nodes)

    def _create_user(self, context: ProcessContext) -> dict[str, Any]:
        created = context.create_user(
            app_ref=self.app_ref,
            message=self.message,
            node_id=self._pick_node(context),
            lambda_value=self.user_lambda,
        )
        self.user_des.append(int(created["des"]))
        return created

    def __call__(self, context: ProcessContext) -> None:
        if not self.user_des:
            self._create_user(context)
            return

        roll = context.rng.random()
        threshold_create = self.create_probability
        threshold_move = threshold_create + self.move_probability
        threshold_remove = threshold_move + self.remove_probability

        can_create = self.max_users is None or len(self.user_des) < self.max_users
        if can_create and roll < threshold_create:
            self._create_user(context)
            return

        if self.user_des and roll < threshold_move:
            user_des = int(context.rng.choice(self.user_des))
            try:
                context.move_user(user_des, self._pick_node(context))
            except ValueError:
                pass
            return

        if self.user_des and roll < threshold_remove:
            user_des = int(context.rng.choice(self.user_des))
            try:
                context.remove_user(user_des)
            finally:
                self.user_des = [value for value in self.user_des if int(value) != user_des]


class NodeFailureProcess:
    def __init__(
        self,
        *,
        node_id: str,
        repeat: bool = False,
    ) -> None:
        self.node_id = str(node_id)
        self.repeat = bool(repeat)
        self.executed = False

    def __call__(self, context: ProcessContext) -> None:
        if self.executed and not self.repeat:
            return
        context.remove_node(self.node_id)
        self.executed = True


class NodeRecoveryProcess:
    def __init__(
        self,
        *,
        node_id: str,
        repeat: bool = False,
    ) -> None:
        self.node_id = str(node_id)
        self.repeat = bool(repeat)
        self.executed = False

    def __call__(self, context: ProcessContext) -> None:
        if self.executed and not self.repeat:
            return
        context.restore_node(self.node_id)
        self.executed = True


class LinkFailureProcess:
    def __init__(
        self,
        *,
        source_node_id: str,
        target_node_id: str,
        repeat: bool = False,
    ) -> None:
        self.source_node_id = str(source_node_id)
        self.target_node_id = str(target_node_id)
        self.repeat = bool(repeat)
        self.executed = False

    def __call__(self, context: ProcessContext) -> None:
        if self.executed and not self.repeat:
            return
        context.remove_link(self.source_node_id, self.target_node_id)
        self.executed = True


class LinkRecoveryProcess:
    def __init__(
        self,
        *,
        source_node_id: str,
        target_node_id: str,
        repeat: bool = False,
    ) -> None:
        self.source_node_id = str(source_node_id)
        self.target_node_id = str(target_node_id)
        self.repeat = bool(repeat)
        self.executed = False

    def __call__(self, context: ProcessContext) -> None:
        if self.executed and not self.repeat:
            return
        context.restore_link(self.source_node_id, self.target_node_id)
        self.executed = True


class VnfRelocationProcess:
    def __init__(
        self,
        *,
        app_ref: str | int,
        module_name: str,
        candidate_nodes: list[str] | tuple[str, ...],
        source_node: str | None = None,
    ) -> None:
        nodes = [str(node) for node in candidate_nodes]
        if not nodes:
            raise ValueError("VNF relocation process requires at least one candidate node")
        self.app_ref = app_ref
        self.module_name = str(module_name)
        self.candidate_nodes = nodes
        self.source_node = None if source_node is None else str(source_node)

    def _next_node(self, current_node: str) -> str:
        if current_node in self.candidate_nodes:
            index = self.candidate_nodes.index(current_node)
            return self.candidate_nodes[(index + 1) % len(self.candidate_nodes)]
        return self.candidate_nodes[0]

    def __call__(self, context: ProcessContext) -> None:
        deployments = context.list_application_vnfs(self.app_ref)
        candidates = [
            item
            for item in deployments.get("vnfs", [])
            if str(item.get("vnf")) == self.module_name
        ]
        if not candidates:
            raise ValueError(
                f"Module '{self.module_name}' is not deployed for application '{self.app_ref}'"
            )

        deployments_for_module = candidates[0].get("deployments", [])
        if not deployments_for_module:
            raise ValueError(
                f"Module '{self.module_name}' has no active deployments for application '{self.app_ref}'"
            )

        selected = None
        if self.source_node is not None:
            for item in deployments_for_module:
                if str(item.get("node")) == self.source_node:
                    selected = item
                    break
            if selected is None:
                raise ValueError(
                    f"Module '{self.module_name}' is not deployed on source node '{self.source_node}'"
                )
        else:
            selected = sorted(
                deployments_for_module,
                key=lambda item: (str(item.get("node")), int(item.get("des"))),
            )[0]

        current_node = str(selected["node"])
        target_node = self._next_node(current_node)
        if current_node == target_node:
            return

        context.move_application_vnf(
            self.app_ref,
            {
                "module_name": self.module_name,
                "from_node": current_node,
                "to_node": target_node,
            },
        )


def _build_process_distribution(
    definition: Mapping[str, Any],
    *,
    fallback_name: str,
) -> Any:
    kind = str(definition.get("kind", "deterministic")).strip().lower()
    name = str(definition.get("name", fallback_name))

    if kind == "deterministic":
        return deterministic_distribution(
            time=float(definition["time"]),
            name=name,
        )
    if kind in {"deterministic_with_start", "deterministic_start"}:
        return deterministicDistributionStartPoint(
            start=float(definition["start"]),
            time=float(definition["time"]),
            name=name,
        )
    if kind == "exponential":
        return exponential_distribution(
            lambd=float(definition["lambd"]),
            seed=int(definition.get("seed", 1)),
            name=name,
        )

    raise ValueError(
        "Process activation kind must be one of: "
        "'deterministic', 'deterministic_with_start', or 'exponential'"
    )


def _build_process_callback(
    *,
    kind: str,
    params: Mapping[str, Any],
) -> Callable[..., Any]:
    process_kind = str(kind).strip().lower()

    if process_kind == "user_mobility_random":
        app_ref = params.get("app", params.get("app_ref"))
        if app_ref is None:
            raise ValueError("user_mobility_random requires 'app' or 'app_ref'")
        message = params.get("message")
        if not message:
            raise ValueError("user_mobility_random requires 'message'")
        return RandomUserMobilityProcess(
            app_ref=app_ref,
            message=str(message),
            user_lambda=float(params.get("lambda", params.get("user_lambda", 1.0))),
            candidate_nodes=params.get("candidate_nodes"),
            create_probability=float(params.get("create_probability", 0.6)),
            move_probability=float(params.get("move_probability", 0.2)),
            remove_probability=float(params.get("remove_probability", 0.2)),
            max_users=params.get("max_users"),
        )

    if process_kind == "node_failure":
        node_id = params.get("node_id")
        if not node_id:
            raise ValueError("node_failure requires 'node_id'")
        return NodeFailureProcess(
            node_id=str(node_id),
            repeat=bool(params.get("repeat", False)),
        )

    if process_kind == "node_recovery":
        node_id = params.get("node_id")
        if not node_id:
            raise ValueError("node_recovery requires 'node_id'")
        return NodeRecoveryProcess(
            node_id=str(node_id),
            repeat=bool(params.get("repeat", False)),
        )

    if process_kind == "link_failure":
        source_node_id = params.get("source_node_id", params.get("source"))
        target_node_id = params.get("target_node_id", params.get("target"))
        if not source_node_id or not target_node_id:
            raise ValueError(
                "link_failure requires 'source_node_id'/'source' and 'target_node_id'/'target'"
            )
        return LinkFailureProcess(
            source_node_id=str(source_node_id),
            target_node_id=str(target_node_id),
            repeat=bool(params.get("repeat", False)),
        )

    if process_kind == "link_recovery":
        source_node_id = params.get("source_node_id", params.get("source"))
        target_node_id = params.get("target_node_id", params.get("target"))
        if not source_node_id or not target_node_id:
            raise ValueError(
                "link_recovery requires 'source_node_id'/'source' and 'target_node_id'/'target'"
            )
        return LinkRecoveryProcess(
            source_node_id=str(source_node_id),
            target_node_id=str(target_node_id),
            repeat=bool(params.get("repeat", False)),
        )

    if process_kind == "vnf_relocation_round_robin":
        app_ref = params.get("app", params.get("app_ref"))
        if app_ref is None:
            raise ValueError("vnf_relocation_round_robin requires 'app' or 'app_ref'")
        module_name = params.get("module_name", params.get("vnf"))
        if not module_name:
            raise ValueError("vnf_relocation_round_robin requires 'module_name' or 'vnf'")
        candidate_nodes = params.get("candidate_nodes")
        if not candidate_nodes:
            raise ValueError("vnf_relocation_round_robin requires 'candidate_nodes'")
        return VnfRelocationProcess(
            app_ref=app_ref,
            module_name=str(module_name),
            candidate_nodes=candidate_nodes,
            source_node=params.get("source_node", params.get("from_node")),
        )

    raise ValueError(
        "Process kind must be one of: "
        "'user_mobility_random', 'node_failure', 'node_recovery', "
        "'link_failure', 'link_recovery', or 'vnf_relocation_round_robin'"
    )


class Infrastructure:
    @staticmethod
    def _resolve_scenario_file(
        path_to_lab_scenario: Path,
        explicit: str | Path | None,
        default_name: str,
    ) -> Path:
        if explicit is not None:
            candidate = Path(explicit)
            if not candidate.is_absolute():
                candidate = path_to_lab_scenario / candidate
            return candidate
        return path_to_lab_scenario / default_name

    def __init__(
        self,
        path_to_lab_scenario,
        *,
        results_path: str | Path | None = None,
        services_definition_path: str | Path | None = None,
        users_definition_path: str | Path | None = None,
        placement_definition_path: str | Path | None = None,
        topology_path: str | Path | None = None,
    ):
        try:
            self.path_to_lab_scenario = Path(path_to_lab_scenario)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"path_to_lab_scenario not found: {e}")

        self.services_definition_path = self._resolve_scenario_file(
            self.path_to_lab_scenario,
            services_definition_path,
            DEFAULT_SERVICES_DEFINITION,
        )
        self.users_definition_path = self._resolve_scenario_file(
            self.path_to_lab_scenario,
            users_definition_path,
            DEFAULT_USERS_DEFINITION,
        )
        self.placement_definition_path = self._resolve_scenario_file(
            self.path_to_lab_scenario,
            placement_definition_path,
            DEFAULT_PLACEMENT_DEFINITION,
        )
        self.topology_path = self._resolve_scenario_file(
            self.path_to_lab_scenario,
            topology_path,
            DEFAULT_TOPOLOGY,
        )

        if not self.path_to_lab_scenario.joinpath('logging.ini').exists():
            raise FileNotFoundError(f"logging.ini not found in {path_to_lab_scenario}")
        if not self.topology_path.exists():
            raise FileNotFoundError(
                f"topology definition not found: {self.topology_path}"
            )
        if not self.services_definition_path.exists():
            raise FileNotFoundError(
                f"services definition not found: {self.services_definition_path}"
            )
        if not self.placement_definition_path.exists():
            raise FileNotFoundError(
                f"placement definition not found: {self.placement_definition_path}"
            )
        if not self.users_definition_path.exists():
            raise FileNotFoundError(
                f"users definition not found: {self.users_definition_path}"
            )

        # Check logging.ini
        logging_config = self.path_to_lab_scenario.joinpath("logging.ini")
        logging.config.fileConfig(str(logging_config))
        _redirect_stdout_log_handlers_to_stderr()
        self.logger = logging.getLogger(__name__)

        self.topology = self.__create_topology()
        self.services = self.__create_services()
        self.placement = self.__create_placement()
        self.users = self.__create_users()
        self.routing = self.__create_routing()

        if results_path is None:
            self.folder_results = Path("results/")
        else:
            self.folder_results = Path(results_path)
        self.folder_results.mkdir(parents=True, exist_ok=True)
        self.folder_results = str(self.folder_results)+"/"

    def clone(self) -> "Infrastructure":
        """
        Create an independent copy of the current infrastructure state.

        The clone keeps the same scenario metadata and logger, but deep-copies
        all mutable simulation inputs so future changes can diverge per
        simulation branch.
        """
        cloned = Infrastructure.__new__(Infrastructure)
        cloned.path_to_lab_scenario = self.path_to_lab_scenario
        cloned.services_definition_path = self.services_definition_path
        cloned.users_definition_path = self.users_definition_path
        cloned.placement_definition_path = self.placement_definition_path
        cloned.topology_path = self.topology_path
        cloned.logger = self.logger
        cloned.topology = copy.deepcopy(self.topology)
        cloned.services = copy.deepcopy(self.services)
        cloned.service_definitions_data = copy.deepcopy(self.service_definitions_data)
        cloned._service_name_by_ref = copy.deepcopy(self._service_name_by_ref)
        cloned.placement = copy.deepcopy(self.placement)
        cloned.users = copy.deepcopy(self.users)
        cloned.routing = copy.deepcopy(self.routing)
        cloned.folder_results = self.folder_results
        return cloned

    def _register_service_definition(self, app_definition: Mapping[str, Any]) -> None:
        app_name = str(app_definition["name"])
        app_id = app_definition.get("id")

        if app_name in self.services:
            raise ValueError(f"Application already exists: {app_name}")
        if app_id is not None and app_id in self._service_name_by_ref:
            raise ValueError(f"Application id already exists: {app_id}")
        if app_id is not None and str(app_id) in self._service_name_by_ref:
            raise ValueError(f"Application id already exists: {app_id}")

        applications = create_applications_from_json([dict(app_definition)])
        self.services.update(applications)
        self.service_definitions_data.append(dict(app_definition))
        self._service_name_by_ref[app_name] = app_name
        if app_id is not None:
            self._service_name_by_ref[app_id] = app_name
            self._service_name_by_ref[str(app_id)] = app_name

    def add_service_definition(
        self,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        if isinstance(definition, (str, Path)):
            path = Path(definition)
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            payload = dict(definition)

        self._register_service_definition(payload)
        return {
            "status": "successful",
            "app": str(payload["name"]),
            "id": payload.get("id"),
            "module_count": len(payload.get("module", [])),
            "message_count": len(payload.get("message", [])),
            "transmission_count": len(payload.get("transmission", [])),
            "total_applications": len(self.services),
        }


    def __create_services(self):
        """
        Create a apps from a lab scenario.
        """
        dataApp = json.loads(
            self.services_definition_path.read_text(encoding="utf-8")
        )
        self.service_definitions_data = []
        self._service_name_by_ref = {}
        self.services = {}
        for app in dataApp:
            self._register_service_definition(app)
        return self.services

    def _resolve_app_name(self, app_ref):
        """
        Resolve legacy app identifiers to the canonical application name.
        """
        return self._service_name_by_ref.get(app_ref, app_ref)

    def __create_placement(self):
        """
        Create a placement from a lab scenario.
        """
        placementJson = json.loads(
            self.placement_definition_path.read_text(encoding="utf-8")
        )
        for item in placementJson.get("initialAllocation", []):
            if "app" in item:
                item["app"] = self._resolve_app_name(item["app"])
        placement = JSONPlacement(name="Placement", json=placementJson)
        return placement

    def __create_users(self):
        """
        Load user/source definitions from a lab scenario.
        """
        users = json.loads(
            self.users_definition_path.read_text(encoding="utf-8")
        )
        for user in users.get("sources", []):
            if "app" in user:
                user["app"] = self._resolve_app_name(user["app"])
        return users


    def __create_routing(self):
        """
        Create a routing from a lab scenario.
        """
        selectorPath = DeviceSpeedAwareRouting()
        return selectorPath

    def __create_topology(self):
        """
        Create a topology from a lab scenario.
        """
        data = json.loads(self.topology_path.read_text(encoding="utf-8"))

        g = nx.Graph()

        clusters = data.get("clusters", [])
        cluster_nodes = {}
        for cluster in clusters:
            cluster_name = cluster.get("name")
            nodes = cluster.get("nodes", [])
            cluster_nodes[cluster_name] = []

            for node in nodes:
                node_name = node.get("name")
                if node_name is None:
                    continue

                attrs = {
                    "cluster": cluster_name,
                    "cluster_role": cluster.get("role"),
                    "cluster_region": cluster.get("cluster_region", cluster.get("region")),
                    "node_role": node.get("role"),
                    "capacity": node.get("capacity", {}),
                    Topology.NODE_IPT: 100,
                }
                # Optional node metadata used by the metrics layer.
                # The JSON schema for lab scenarios may include:
                # - WATT / COST numeric values
                # - uptime as a pair [start, end] where end can be null
                # - model/type strings for reporting
                #
                # If model/type are missing, derive them from:
                # - cluster.role (MEC/EDC/CDC)
                # - node.role (control-plane/worker)
                node_role = attrs.get("node_role")
                cluster_role = attrs.get("cluster_role")

                if "model" in node:
                    attrs["model"] = node.get("model")
                elif cluster_role and node_role:
                    attrs["model"] = f"{cluster_role} {node_role}"
                elif node_role:
                    attrs["model"] = node_role

                if "type" in node:
                    attrs["type"] = node.get("type")
                elif cluster_role:
                    attrs["type"] = cluster_role

                if "WATT" in node:
                    attrs["WATT"] = node.get("WATT")
                if "COST" in node:
                    attrs["COST"] = node.get("COST")
                if "uptime" in node:
                    attrs["uptime"] = node.get("uptime")
                g.add_node(node_name, **attrs)
                cluster_nodes[cluster_name].append(node_name)

        def pick_cluster_endpoint(cluster_name: str) -> str | None:
            """Select a representative node for inter-cluster links."""
            nodes = cluster_nodes.get(cluster_name, [])
            if not nodes:
                return None
            for n in nodes:
                if g.nodes[n].get("node_role") == "control-plane":
                    return n
            return None

        # Intra-cluster connectivity: each node connected to all others
        for cluster_name, nodes in cluster_nodes.items():
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    g.add_edge(
                        nodes[i],
                        nodes[j],
                        PR=1,
                        BW=1,
                        intra_cluster=True,
                        cluster=cluster_name,
                    )

        for link in data.get("links", []):
            from_cluster = link.get("from")
            to_cluster = link.get("to")
            if from_cluster is None or to_cluster is None:
                continue

            src = pick_cluster_endpoint(from_cluster)
            dst = pick_cluster_endpoint(to_cluster)
            if src is None or dst is None:
                continue

            pr = link.get("targetOneWayLatencyMs", 1)
            bw = link.get("bandwidth", 1)
            g.add_edge(
                src,
                dst,
                PR=pr,
                BW=bw,
                distanceKm=link.get("distanceKm"),
                bidirectional=link.get("bidirectional", True),
                from_cluster=from_cluster,
                to_cluster=to_cluster,
            )

        t = Topology(logger=self.logger)
        t.create_topology_from_graph(g)
        for node_id, attrs in g.nodes(data=True):
            t.nodeAttributes[node_id] = {"id": node_id, **attrs}
        return t


    def plot(self, pos=None):
        """
        Plot the topology using NetworkX.
        """
        if pos is None:
            pos=nx.spring_layout(self.topology.G)
        nx.draw_networkx(self.topology.G, pos, with_labels=True)
        nx.draw_networkx_edge_labels(self.topology.G, pos,alpha=0.5,font_size=5,verticalalignment="top")

class Simulation:
    def __init__(
        self,
        infrastructure: Infrastructure,
        *,
        seed: int | None = None,
        results_suffix: str | None = None,
    ):
        self.infrastructure = infrastructure
        results_path = self.infrastructure.folder_results + "sim_trace"
        if results_suffix is not None:
            results_path = (
                self.infrastructure.folder_results + f"sim_trace_{results_suffix}"
            )
        self.sim = Sim(
            self.infrastructure.topology,
            default_results_path=results_path,
            logger=self.infrastructure.logger,
            seed=seed,
        )

        self._initialized = False
        self._lock = threading.RLock()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._stop_requested = threading.Event()

        self._thread: threading.Thread | None = None
        self._scheduled_until: float | None = None
        self._step: float = 1.0
        self._metrics_closed = False
        self._idle_event = threading.Event()
        self._idle_event.set()
        self.results_path = results_path
        self._registered_processes: dict[str, RegisteredProcess] = {}

    def _live_topology_info(self) -> dict[str, dict[str, Any]]:
        topology = getattr(self.sim, "topology", None)
        graph = getattr(topology, "G", None)
        if graph is None:
            return {}

        rows: dict[str, dict[str, Any]] = {}
        for node_id, attrs in graph.nodes(data=True):
            rows[str(node_id)] = {"id": node_id, **dict(attrs)}
        return rows

    @staticmethod
    def _node_attributes_from_cluster_definition(
        cluster_definition: Mapping[str, Any],
        node_definition: Mapping[str, Any],
    ) -> dict[str, Any]:
        cluster_name = cluster_definition.get("name")
        attrs = {
            "cluster": cluster_name,
            "cluster_role": cluster_definition.get("role"),
            "cluster_region": cluster_definition.get(
                "cluster_region",
                cluster_definition.get("region"),
            ),
            "node_role": node_definition.get("role"),
            "capacity": node_definition.get("capacity", {}),
            Topology.NODE_IPT: 100,
        }

        node_role = attrs.get("node_role")
        cluster_role = attrs.get("cluster_role")

        if "model" in node_definition:
            attrs["model"] = node_definition.get("model")
        elif cluster_role and node_role:
            attrs["model"] = f"{cluster_role} {node_role}"
        elif node_role:
            attrs["model"] = node_role

        if "type" in node_definition:
            attrs["type"] = node_definition.get("type")
        elif cluster_role:
            attrs["type"] = cluster_role

        if "WATT" in node_definition:
            attrs["WATT"] = node_definition.get("WATT")
        if "COST" in node_definition:
            attrs["COST"] = node_definition.get("COST")
        if "uptime" in node_definition:
            attrs["uptime"] = node_definition.get("uptime")

        return attrs

    def _pick_cluster_endpoint(self, cluster_name: str) -> str | None:
        graph = self.sim.topology.G
        cluster_nodes = []
        for node_id, attrs in graph.nodes(data=True):
            if str(attrs.get("cluster")) == str(cluster_name):
                cluster_nodes.append(str(node_id))

        if not cluster_nodes:
            return None

        for node_id in sorted(cluster_nodes):
            if graph.nodes[node_id].get("node_role") == "control-plane":
                return node_id
        return sorted(cluster_nodes)[0]

    def _cluster_metadata(self, cluster_name: str) -> dict[str, Any]:
        graph = self.sim.topology.G
        for _, attrs in graph.nodes(data=True):
            if str(attrs.get("cluster")) != str(cluster_name):
                continue
            return {
                "name": str(cluster_name),
                "role": attrs.get("cluster_role"),
                "cluster_region": attrs.get("cluster_region"),
                "region": attrs.get("cluster_region"),
            }
        raise ValueError(f"Cluster does not exist in the simulation: {cluster_name}")

    def _load_cluster_definition(
        self,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        if isinstance(definition, Mapping):
            return dict(definition)

        path = Path(definition)
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_application_definition(
        self,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        if isinstance(definition, Mapping):
            return dict(definition)

        path = Path(definition)
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _optional_payload_value(payload: Mapping[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in payload:
                return payload[key]
        return None

    def _build_process_context(
        self,
        *,
        process_name: str,
        process_des: int | None = None,
    ) -> ProcessContext:
        return ProcessContext(
            self,
            process_name=process_name,
            process_des=process_des,
        )

    def _invalidate_routing_cache(self) -> None:
        selector = getattr(self.infrastructure, "routing", None)
        if hasattr(selector, "clear_routing_cache"):
            selector.clear_routing_cache()
        elif hasattr(selector, "invalid_cache_value"):
            selector.invalid_cache_value = True

    def _invoke_registered_process(self, process_name: str) -> None:
        registration = self._registered_processes.get(process_name)
        if registration is None or not registration.enabled:
            return

        registration.activation_count += 1
        context = self._build_process_context(
            process_name=process_name,
            process_des=registration.monitor_des,
        )
        registration.callback(context, **dict(registration.params))

    def _deploy_registered_process(self, registration: RegisteredProcess) -> int | None:
        if not registration.enabled:
            registration.monitor_des = None
            return None

        if registration.monitor_des is not None:
            self.sim.stop_process(registration.monitor_des)

        distribution = copy.deepcopy(registration.distribution)
        monitor_des = self.sim.deploy_monitor(
            registration.name,
            self._invoke_registered_process,
            distribution,
            process_name=registration.name,
        )
        registration.monitor_des = monitor_des
        return monitor_des

    def register_process(
        self,
        name: str,
        callback: Callable[..., Any],
        distribution: Any,
        **params: Any,
    ) -> dict[str, Any]:
        with self._lock:
            process_name = str(name)
            if not process_name:
                raise ValueError("Process name must be non-empty")
            if process_name in self._registered_processes:
                raise ValueError(f"Process already exists in the simulation: {process_name}")

            registration = RegisteredProcess(
                name=process_name,
                callback=callback,
                distribution=copy.deepcopy(distribution),
                params=dict(params),
            )
            self._registered_processes[process_name] = registration

            if self._initialized:
                self._deploy_registered_process(registration)

            return {
                "status": "successful",
                "name": process_name,
                "enabled": registration.enabled,
                "initialized": self._initialized,
                "monitor_des": registration.monitor_des,
            }

    def register_process_definition(
        self,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            if isinstance(definition, Mapping):
                payload = dict(definition)
            else:
                path = Path(definition)
                payload = json.loads(path.read_text(encoding="utf-8"))

            name = payload.get("name")
            if not name:
                raise ValueError("Process definition requires a non-empty 'name'")

            kind = payload.get("kind")
            if not kind:
                raise ValueError("Process definition requires a non-empty 'kind'")

            activation_definition = payload.get("activation")
            if not isinstance(activation_definition, Mapping):
                raise ValueError("Process definition requires an 'activation' mapping")

            params = payload.get("params", {})
            if not isinstance(params, Mapping):
                raise ValueError("Process definition 'params' must be a mapping")

            callback = _build_process_callback(
                kind=str(kind),
                params=params,
            )
            distribution = _build_process_distribution(
                activation_definition,
                fallback_name=f"{name}-activation",
            )

            result = self.register_process(
                str(name),
                callback,
                distribution,
            )
            registration = self._registered_processes[str(name)]
            registration.kind = str(kind)
            registration.definition = copy.deepcopy(payload)
            result["kind"] = str(kind)
            result["definition"] = payload
            return result

    def list_processes(self) -> list[dict[str, Any]]:
        with self._lock:
            rows: list[dict[str, Any]] = []
            for name in sorted(self._registered_processes.keys()):
                registration = self._registered_processes[name]
                rows.append(
                    {
                        "name": name,
                        "kind": registration.kind,
                        "enabled": registration.enabled,
                        "monitor_des": registration.monitor_des,
                        "activation_count": registration.activation_count,
                    }
                )
            return rows

    def enable_process(self, name: str) -> dict[str, Any]:
        with self._lock:
            process_name = str(name)
            if process_name not in self._registered_processes:
                raise ValueError(f"Process does not exist in the simulation: {process_name}")

            registration = self._registered_processes[process_name]
            registration.enabled = True
            if self._initialized:
                self._deploy_registered_process(registration)

            return {
                "status": "successful",
                "name": process_name,
                "enabled": True,
                "monitor_des": registration.monitor_des,
            }

    def disable_process(self, name: str) -> dict[str, Any]:
        with self._lock:
            process_name = str(name)
            if process_name not in self._registered_processes:
                raise ValueError(f"Process does not exist in the simulation: {process_name}")

            registration = self._registered_processes[process_name]
            registration.enabled = False
            if registration.monitor_des is not None:
                self.sim.stop_process(registration.monitor_des)
                registration.monitor_des = None

            return {
                "status": "successful",
                "name": process_name,
                "enabled": False,
            }

    def remove_process(self, name: str) -> dict[str, Any]:
        with self._lock:
            process_name = str(name)
            registration = self._registered_processes.pop(process_name, None)
            if registration is None:
                raise ValueError(f"Process does not exist in the simulation: {process_name}")
            if registration.monitor_des is not None:
                self.sim.stop_process(registration.monitor_des)

            return {
                "status": "successful",
                "name": process_name,
                "activation_count": registration.activation_count,
            }

    def create_cluster(
        self,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            payload = self._load_cluster_definition(definition)
            clusters = payload.get("clusters", [])
            if len(clusters) != 1:
                raise ValueError("Cluster creation expects exactly one cluster definition")

            cluster_definition = clusters[0]
            cluster_name = cluster_definition.get("name")
            if not cluster_name:
                raise ValueError("Cluster definition requires a non-empty 'name'")

            if self._pick_cluster_endpoint(str(cluster_name)) is not None:
                raise ValueError(f"Cluster already exists in the simulation: {cluster_name}")

            graph = self.sim.topology.G
            created_nodes: list[str] = []

            for node_definition in cluster_definition.get("nodes", []):
                node_name = node_definition.get("name")
                if not node_name:
                    raise ValueError("Each node definition requires a non-empty 'name'")
                if graph.has_node(node_name):
                    raise ValueError(f"Node already exists in the simulation: {node_name}")

                attrs = self._node_attributes_from_cluster_definition(
                    cluster_definition,
                    node_definition,
                )
                graph.add_node(node_name, **attrs)
                self.sim.topology.nodeAttributes[node_name] = {
                    "id": node_name,
                    **attrs,
                }
                created_nodes.append(str(node_name))

            for i in range(len(created_nodes)):
                for j in range(i + 1, len(created_nodes)):
                    graph.add_edge(
                        created_nodes[i],
                        created_nodes[j],
                        PR=1,
                        BW=1,
                        intra_cluster=True,
                        cluster=cluster_name,
                    )

            created_links: list[dict[str, Any]] = []
            for link in payload.get("links", []):
                from_cluster = link.get("from")
                to_cluster = link.get("to")
                if from_cluster is None or to_cluster is None:
                    continue

                src = self._pick_cluster_endpoint(str(from_cluster))
                dst = self._pick_cluster_endpoint(str(to_cluster))
                if src is None or dst is None:
                    raise ValueError(
                        f"Cannot create link between clusters '{from_cluster}' and '{to_cluster}'"
                    )

                edge_attrs = {
                    "PR": link.get("targetOneWayLatencyMs", 1),
                    "BW": link.get("bandwidth", 1),
                    "distanceKm": link.get("distanceKm"),
                    "bidirectional": link.get("bidirectional", True),
                    "from_cluster": from_cluster,
                    "to_cluster": to_cluster,
                }
                graph.add_edge(src, dst, **edge_attrs)
                created_links.append({"src": src, "dst": dst, **edge_attrs})

            self._invalidate_routing_cache()

            return {
                "cluster": str(cluster_name),
                "nodes": created_nodes,
                "node_count": len(created_nodes),
                "links": created_links,
                "total_nodes": self.count_nodes(),
                "total_clusters": self.count_clusters(),
            }

    def create_application(
        self,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            payload = self._load_application_definition(definition)
            summary = self.infrastructure.add_service_definition(payload)

            app_name = str(payload["name"])
            initialized = self._initialized
            if initialized:
                app = self.infrastructure.services[app_name]
                self.sim.deploy_app(
                    app,
                    self.infrastructure.placement,
                    self.infrastructure.routing,
                )

            return {
                **summary,
                "initialized": initialized,
                "deployed": False,
                "users_enabled": False,
            }

    def create_users(
        self,
        definition: str | Path | Mapping[str, Any],
        *,
        nodes: str | list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            payload = self._load_cluster_definition(definition)
            source_definitions = payload.get("sources", [])
            if not source_definitions:
                raise ValueError("User creation expects a non-empty 'sources' list")

            if nodes is None:
                target_nodes: list[str] | None = None
            elif isinstance(nodes, str):
                target_nodes = [nodes]
            else:
                target_nodes = [str(node) for node in nodes]
            if target_nodes is not None and not target_nodes:
                raise ValueError("User creation requires at least one target node")

            graph = self.sim.topology.G
            created: list[dict[str, Any]] = []
            initialized = self._initialized

            for source in source_definitions:
                app_ref = source.get("app")
                message_name = source.get("message")
                if app_ref is None:
                    raise ValueError("Each user source requires an 'app'")
                if not message_name:
                    raise ValueError("Each user source requires a non-empty 'message'")

                app_name = str(self.infrastructure._resolve_app_name(app_ref))
                if app_name not in self.infrastructure.services:
                    raise ValueError(f"Application does not exist in the simulation: {app_ref}")

                app = self.infrastructure.services[app_name]
                try:
                    msg = app.get_message(message_name)
                except Exception as exc:
                    raise ValueError(
                        f"Message '{message_name}' does not exist in application '{app_name}'"
                    ) from exc

                lambda_value = source.get("lambda", 1)
                effective_nodes = (
                    target_nodes
                    if target_nodes is not None
                    else [str(source.get("id_resource"))]
                )
                if not effective_nodes or effective_nodes == ["None"]:
                    raise ValueError(
                        "Each user source requires 'id_resource' unless nodes are provided explicitly"
                    )

                for node_id in effective_nodes:
                    node_key = str(node_id)
                    if not graph.has_node(node_key):
                        raise ValueError(f"Node does not exist in the simulation: {node_key}")

                    user_item = {
                        "id_resource": node_key,
                        "app": app_name,
                        "message": str(message_name),
                        "lambda": lambda_value,
                    }
                    self.infrastructure.users.setdefault("sources", []).append(user_item)

                    des = None
                    if initialized:
                        dist = deterministic_distribution(
                            time=lambda_value,
                            name=f"Deterministic-{app_name}-{node_key}",
                        )
                        des = self.sim.deploy_source(
                            app_name,
                            id_node=node_key,
                            msg=msg,
                            distribution=dist,
                            source_definition=user_item,
                        )

                    created.append(
                        {
                            "app": app_name,
                            "node": node_key,
                            "message": str(message_name),
                            "lambda": lambda_value,
                            "des": des,
                        }
                    )

            service_ids = self._service_id_by_name()
            for item in created:
                item["id"] = service_ids.get(item["app"], item["app"])

            return {
                "status": "successful",
                "created": created,
                "created_count": len(created),
                "initialized": initialized,
            }

    @staticmethod
    def _set_distribution_lambda(distribution: Any, value: float) -> None:
        updated = False
        for attr in ("time", "lambd", "l"):
            if hasattr(distribution, attr):
                setattr(distribution, attr, value)
                updated = True
        if not updated:
            raise ValueError(
                "User distribution does not expose a mutable rate parameter"
            )

    def _update_user_lambda_value(self, des: int, new_lambda: float) -> dict[str, Any]:
        alloc_source = getattr(self.sim, "alloc_source", {}) or {}
        if des not in alloc_source:
            raise ValueError(f"User does not exist in the simulation: {des}")

        source = alloc_source[des]
        distribution = source.get("distribution")
        if distribution is None:
            raise ValueError(f"User {des} does not keep a mutable distribution reference")

        lambda_value = float(new_lambda)
        self._set_distribution_lambda(distribution, lambda_value)
        source["lambda"] = lambda_value

        definition = source.get("source_definition")
        if isinstance(definition, dict):
            definition["lambda"] = lambda_value

        return {
            "des": des,
            "id": self._service_id_by_name().get(str(source.get("app")), str(source.get("app"))),
            "app": str(source.get("app")),
            "node": str(source.get("id")),
            "message": source.get("name"),
            "lambda": lambda_value,
        }

    def update_user_lambda(self, user_des: int, new_lambda: float) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()
            item = self._update_user_lambda_value(int(user_des), float(new_lambda))
            return {
                "status": "successful",
                **item,
            }

    def update_application_users_lambda(
        self,
        app_ref: str | int,
        new_lambda: float,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            app_name = str(self.infrastructure._resolve_app_name(app_ref))
            if app_name not in self.infrastructure.services:
                raise ValueError(f"Application does not exist in the simulation: {app_ref}")

            alloc_source = getattr(self.sim, "alloc_source", {}) or {}
            updated: list[dict[str, Any]] = []
            for des, source in list(alloc_source.items()):
                if str(source.get("app")) != app_name:
                    continue
                updated.append(
                    self._update_user_lambda_value(int(des), float(new_lambda))
                )

            service_ids = self._service_id_by_name()
            return {
                "status": "successful",
                "id": service_ids.get(app_name, app_name),
                "app": app_name,
                "lambda": float(new_lambda),
                "updated": sorted(updated, key=lambda item: int(item["des"])),
                "updated_count": len(updated),
            }

    def _remove_users_matching(
        self,
        *,
        predicate,
    ) -> list[dict[str, Any]]:
        alloc_source = getattr(self.sim, "alloc_source", {}) or {}
        removed: list[dict[str, Any]] = []

        for des, source in list(alloc_source.items()):
            source_node = str(source.get("id"))
            app_name = str(source.get("app"))
            if not predicate(source_node, app_name, source):
                continue

            removed.append(
                {
                    "des": des,
                    "node": source_node,
                    "app": app_name,
                    "message": source.get("name"),
                }
            )
            self.sim.undeploy_source(des)

        return removed

    def remove_users_by_application(self, app_ref: str | int) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            app_name = str(self.infrastructure._resolve_app_name(app_ref))
            if app_name not in self.infrastructure.services:
                raise ValueError(f"Application does not exist in the simulation: {app_ref}")

            removed = self._remove_users_matching(
                predicate=lambda _node, source_app, _source: source_app == app_name
            )
            service_ids = self._service_id_by_name()
            return {
                "status": "successful",
                "id": service_ids.get(app_name, app_name),
                "app": app_name,
                "removed": sorted(
                    removed,
                    key=lambda item: (str(item["node"]), int(item["des"])),
                ),
                "removed_count": len(removed),
            }

    def remove_user(self, user_des: int) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            des = int(user_des)
            alloc_source = getattr(self.sim, "alloc_source", {}) or {}
            if des not in alloc_source:
                raise ValueError(f"User does not exist in the simulation: {des}")

            source = dict(alloc_source[des])
            app_name = str(source.get("app"))
            service_ids = self._service_id_by_name()
            self.sim.undeploy_source(des)

            return {
                "status": "successful",
                "des": des,
                "id": service_ids.get(app_name, app_name),
                "app": app_name,
                "node": str(source.get("id")),
                "message": source.get("name"),
            }

    def remove_users_by_node(self, node_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            node_key = str(node_id)
            if node_key not in self._live_topology_info():
                raise ValueError(f"Node does not exist in the simulation: {node_key}")

            removed = self._remove_users_matching(
                predicate=lambda source_node, _source_app, _source: source_node == node_key
            )
            affected_apps = sorted({str(item["app"]) for item in removed}, key=str)
            service_ids = self._service_id_by_name()
            return {
                "status": "successful",
                "node": node_key,
                "affected_applications": [
                    {
                        "id": service_ids.get(app_name, app_name),
                        "app": app_name,
                    }
                    for app_name in affected_apps
                ],
                "removed": sorted(
                    removed,
                    key=lambda item: (str(item["app"]), int(item["des"])),
                ),
                "removed_count": len(removed),
            }

    def remove_users_by_cluster(self, cluster_name: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            cluster_key = str(cluster_name)
            cluster_nodes = {
                str(item["node"]) for item in self.list_nodes_in_cluster(cluster_key)
            }
            if not cluster_nodes:
                raise ValueError(
                    f"Cluster does not exist in the simulation: {cluster_key}"
                )

            removed = self._remove_users_matching(
                predicate=lambda source_node, _source_app, _source: source_node in cluster_nodes
            )
            affected_apps = sorted({str(item["app"]) for item in removed}, key=str)
            service_ids = self._service_id_by_name()
            return {
                "status": "successful",
                "cluster": cluster_key,
                "affected_applications": [
                    {
                        "id": service_ids.get(app_name, app_name),
                        "app": app_name,
                    }
                    for app_name in affected_apps
                ],
                "removed": sorted(
                    removed,
                    key=lambda item: (str(item["node"]), str(item["app"]), int(item["des"])),
                ),
                "removed_count": len(removed),
            }

    def move_users_to_node(
        self,
        source_node_id: str,
        target_node_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            source_node = str(source_node_id)
            target_node = str(target_node_id)
            topology_info = self._live_topology_info()
            if source_node not in topology_info:
                raise ValueError(f"Source node does not exist in the simulation: {source_node}")
            if target_node not in topology_info:
                raise ValueError(f"Target node does not exist in the simulation: {target_node}")
            if source_node == target_node:
                raise ValueError("Source node and target node must be different")

            alloc_source = getattr(self.sim, "alloc_source", {}) or {}
            moved: list[dict[str, Any]] = []
            service_ids = self._service_id_by_name()

            for des, source in list(alloc_source.items()):
                current_node = str(source.get("id"))
                if current_node != source_node:
                    continue

                source["id"] = target_node
                self.sim.alloc_DES[des] = target_node
                definition = source.get("source_definition")
                if isinstance(definition, dict):
                    definition["id_resource"] = target_node

                app_name = str(source.get("app"))
                moved.append(
                    {
                        "des": des,
                        "id": service_ids.get(app_name, app_name),
                        "app": app_name,
                        "from_node": source_node,
                        "to_node": target_node,
                        "message": source.get("name"),
                    }
                )

            return {
                "status": "successful",
                "from_node": source_node,
                "to_node": target_node,
                "moved": sorted(moved, key=lambda item: int(item["des"])),
                "moved_count": len(moved),
            }

    def move_user(self, user_des: int, target_node_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            des = int(user_des)
            target_node = str(target_node_id)
            topology_info = self._live_topology_info()
            if target_node not in topology_info:
                raise ValueError(f"Target node does not exist in the simulation: {target_node}")

            alloc_source = getattr(self.sim, "alloc_source", {}) or {}
            if des not in alloc_source:
                raise ValueError(f"User does not exist in the simulation: {des}")

            source = alloc_source[des]
            source_node = str(source.get("id"))
            if source_node == target_node:
                raise ValueError("Source node and target node must be different")

            source["id"] = target_node
            self.sim.alloc_DES[des] = target_node
            definition = source.get("source_definition")
            if isinstance(definition, dict):
                definition["id_resource"] = target_node

            app_name = str(source.get("app"))
            service_ids = self._service_id_by_name()
            return {
                "status": "successful",
                "des": des,
                "id": service_ids.get(app_name, app_name),
                "app": app_name,
                "from_node": source_node,
                "to_node": target_node,
                "message": source.get("name"),
            }

    def deploy_application_vnfs(
        self,
        app_ref: str | int,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            app_name = str(self.infrastructure._resolve_app_name(app_ref))
            if app_name not in self.infrastructure.services:
                raise ValueError(f"Application does not exist in the simulation: {app_ref}")

            payload = self._load_application_definition(definition)
            placements = payload.get("placements", payload.get("initialAllocation", []))
            if not placements:
                raise ValueError(
                    "VNF deployment expects a non-empty 'placements' or 'initialAllocation' list"
                )

            app = self.infrastructure.services[app_name]
            services = app.services
            graph = self.sim.topology.G
            alloc_module = getattr(self.sim, "alloc_module", {}) or {}
            alloc_des = getattr(self.sim, "alloc_DES", {}) or {}
            service_ids = self._service_id_by_name()

            created: list[dict[str, Any]] = []
            skipped_existing: list[dict[str, Any]] = []

            for item in placements:
                item_app = item.get("app", app_ref)
                item_app_name = str(self.infrastructure._resolve_app_name(item_app))
                if item_app_name != app_name:
                    raise ValueError(
                        f"Placement entry app '{item_app}' does not match requested application '{app_ref}'"
                    )

                module_name = item.get("module_name") or item.get("vnf")
                node_id = item.get("id_resource") or item.get("node")
                if not module_name:
                    raise ValueError("Each placement entry requires 'module_name' or 'vnf'")
                if not node_id:
                    raise ValueError("Each placement entry requires 'id_resource' or 'node'")
                module_name = str(module_name)
                node_id = str(node_id)

                if module_name not in services:
                    raise ValueError(
                        f"Module '{module_name}' does not exist in application '{app_name}'"
                    )
                if not graph.has_node(node_id):
                    raise ValueError(f"Node does not exist in the simulation: {node_id}")

                already_deployed = False
                for des in alloc_module.get(app_name, {}).get(module_name, []):
                    if str(alloc_des.get(des)) == node_id:
                        already_deployed = True
                        break

                if already_deployed:
                    skipped_existing.append(
                        {
                            "vnf": module_name,
                            "node": node_id,
                        }
                    )
                    continue

                created_des = self.sim.deploy_module(
                    app_name,
                    module_name,
                    services[module_name],
                    [node_id],
                )
                for des in created_des:
                    created.append(
                        {
                            "vnf": module_name,
                            "node": node_id,
                            "des": des,
                        }
                    )

            return {
                "status": "successful",
                "id": service_ids.get(app_name, app_name),
                "app": app_name,
                "created": created,
                "created_count": len(created),
                "skipped_existing": skipped_existing,
                "deployment_count": sum(
                    len(v) for v in getattr(self.sim, "alloc_module", {}).get(app_name, {}).values()
                ),
            }

    def deploy_application_vnfs_generated(
        self,
        app_ref: str | int,
        *,
        strategy: str = "spread",
        allowed_nodes: list[str] | tuple[str, ...] | None = None,
        include_control_plane: bool = True,
        seed: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            app_name = str(self.infrastructure._resolve_app_name(app_ref))
            if app_name not in self.infrastructure.services:
                raise ValueError(f"Application does not exist in the simulation: {app_ref}")

            graph = self.sim.topology.G
            services = self.infrastructure.services[app_name].services
            module_names = sorted(str(name) for name in services.keys())
            if not module_names:
                raise ValueError(f"Application has no VNFs to deploy: {app_ref}")

            candidates: list[str] = []
            if allowed_nodes is None:
                for node_id, attrs in graph.nodes(data=True):
                    if not include_control_plane and attrs.get("node_role") == "control-plane":
                        continue
                    candidates.append(str(node_id))
            else:
                for node_id in allowed_nodes:
                    node_key = str(node_id)
                    if not graph.has_node(node_key):
                        raise ValueError(f"Node does not exist in the simulation: {node_key}")
                    if (
                        not include_control_plane
                        and graph.nodes[node_key].get("node_role") == "control-plane"
                    ):
                        continue
                    candidates.append(node_key)

            if not candidates:
                raise ValueError("No candidate nodes are available for generated placement")

            strategy_key = str(strategy).strip().lower()
            if strategy_key not in {"spread", "same-node", "random"}:
                raise ValueError(
                    "Generated placement strategy must be one of: 'spread', 'same-node', 'random'"
                )

            selected_nodes = list(candidates)
            rng = random.Random(seed if seed is not None else self.sim.seed)
            if strategy_key == "random":
                rng.shuffle(selected_nodes)

            placements: list[dict[str, Any]] = []
            if strategy_key == "same-node":
                node_id = selected_nodes[0]
                for module_name in module_names:
                    placements.append(
                        {
                            "app": app_name,
                            "module_name": module_name,
                            "id_resource": node_id,
                        }
                    )
            else:
                for index, module_name in enumerate(module_names):
                    node_id = selected_nodes[index % len(selected_nodes)]
                    placements.append(
                        {
                            "app": app_name,
                            "module_name": module_name,
                            "id_resource": node_id,
                        }
                    )

            summary = self.deploy_application_vnfs(
                app_name,
                {
                    "initialAllocation": placements,
                },
            )
            summary["strategy"] = strategy_key
            summary["candidate_nodes"] = sorted(candidates)
            summary["generated_placements"] = placements
            return summary

    def move_application_vnf(
        self,
        app_ref: str | int,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            app_name = str(self.infrastructure._resolve_app_name(app_ref))
            if app_name not in self.infrastructure.services:
                raise ValueError(f"Application does not exist in the simulation: {app_ref}")

            payload = self._load_application_definition(definition)
            module_name = payload.get("module_name") or payload.get("vnf")
            source_node = payload.get("from_node") or payload.get("source_node") or payload.get("from")
            target_node = payload.get("to_node") or payload.get("target_node") or payload.get("to") or payload.get("id_resource") or payload.get("node")
            if not module_name:
                raise ValueError("VNF move requires 'module_name' or 'vnf'")
            if not target_node:
                raise ValueError("VNF move requires 'to_node', 'target_node', 'id_resource', or 'node'")

            module_name = str(module_name)
            target_node = str(target_node)
            if source_node is not None:
                source_node = str(source_node)

            app = self.infrastructure.services[app_name]
            services = app.services
            if module_name not in services:
                raise ValueError(
                    f"Module '{module_name}' does not exist in application '{app_name}'"
                )

            graph = self.sim.topology.G
            if not graph.has_node(target_node):
                raise ValueError(f"Node does not exist in the simulation: {target_node}")

            alloc_module = getattr(self.sim, "alloc_module", {}) or {}
            alloc_des = getattr(self.sim, "alloc_DES", {}) or {}
            deployed_des = list(alloc_module.get(app_name, {}).get(module_name, []))
            if not deployed_des:
                raise ValueError(
                    f"Module '{module_name}' is not currently deployed for application '{app_name}'"
                )

            if any(str(alloc_des.get(des)) == target_node for des in deployed_des):
                raise ValueError(
                    f"Module '{module_name}' is already deployed on target node '{target_node}'"
                )

            candidates = [
                des
                for des in deployed_des
                if source_node is None or str(alloc_des.get(des)) == source_node
            ]
            if not candidates:
                raise ValueError(
                    f"Module '{module_name}' is not deployed on source node '{source_node}'"
                )
            if source_node is None and len(candidates) > 1:
                raise ValueError(
                    f"Module '{module_name}' has multiple deployments; specify 'from_node'"
                )

            des_to_move = candidates[0]
            actual_source_node = str(alloc_des.get(des_to_move))
            self.sim.undeploy_module(app_name, module_name, des_to_move)
            created_des = self.sim.deploy_module(
                app_name,
                module_name,
                services[module_name],
                [target_node],
            )
            new_des = created_des[0] if created_des else None

            service_ids = self._service_id_by_name()
            return {
                "status": "successful",
                "id": service_ids.get(app_name, app_name),
                "app": app_name,
                "vnf": module_name,
                "from_node": actual_source_node,
                "to_node": target_node,
                "removed_des": des_to_move,
                "created_des": new_des,
            }

    def replicate_application_vnf(
        self,
        app_ref: str | int,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            app_name = str(self.infrastructure._resolve_app_name(app_ref))
            if app_name not in self.infrastructure.services:
                raise ValueError(f"Application does not exist in the simulation: {app_ref}")

            payload = self._load_application_definition(definition)
            module_name = payload.get("module_name") or payload.get("vnf")
            target_node = (
                payload.get("to_node")
                or payload.get("target_node")
                or payload.get("to")
                or payload.get("id_resource")
                or payload.get("node")
            )
            if not module_name:
                raise ValueError("VNF replication requires 'module_name' or 'vnf'")
            if not target_node:
                raise ValueError(
                    "VNF replication requires 'to_node', 'target_node', 'id_resource', or 'node'"
                )

            module_name = str(module_name)
            target_node = str(target_node)

            app = self.infrastructure.services[app_name]
            services = app.services
            if module_name not in services:
                raise ValueError(
                    f"Module '{module_name}' does not exist in application '{app_name}'"
                )

            graph = self.sim.topology.G
            if not graph.has_node(target_node):
                raise ValueError(f"Node does not exist in the simulation: {target_node}")

            alloc_module = getattr(self.sim, "alloc_module", {}) or {}
            alloc_des = getattr(self.sim, "alloc_DES", {}) or {}
            deployed_des = list(alloc_module.get(app_name, {}).get(module_name, []))
            if not deployed_des:
                raise ValueError(
                    f"Module '{module_name}' is not currently deployed for application '{app_name}'"
                )

            if any(str(alloc_des.get(des)) == target_node for des in deployed_des):
                raise ValueError(
                    f"Module '{module_name}' is already deployed on target node '{target_node}'"
                )

            created_des = self.sim.deploy_module(
                app_name,
                module_name,
                services[module_name],
                [target_node],
            )
            new_des = created_des[0] if created_des else None

            service_ids = self._service_id_by_name()
            return {
                "status": "successful",
                "id": service_ids.get(app_name, app_name),
                "app": app_name,
                "vnf": module_name,
                "to_node": target_node,
                "created_des": new_des,
                "replica_count": len(
                    getattr(self.sim, "alloc_module", {})
                    .get(app_name, {})
                    .get(module_name, [])
                ),
            }

    def create_nodes(
        self,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            payload = self._load_cluster_definition(definition)
            nodes = payload.get("nodes", [])
            if not nodes:
                raise ValueError("Node creation expects a non-empty 'nodes' list")

            graph = self.sim.topology.G
            created_nodes: list[str] = []
            touched_clusters: set[str] = set()

            for node_definition in nodes:
                cluster_name = node_definition.get("on_cluster")
                node_name = node_definition.get("name")
                if not cluster_name:
                    raise ValueError("Each node definition requires a non-empty 'on_cluster'")
                if not node_name:
                    raise ValueError("Each node definition requires a non-empty 'name'")
                if graph.has_node(node_name):
                    raise ValueError(f"Node already exists in the simulation: {node_name}")

                cluster_definition = self._cluster_metadata(str(cluster_name))
                attrs = self._node_attributes_from_cluster_definition(
                    cluster_definition,
                    node_definition,
                )
                graph.add_node(node_name, **attrs)
                self.sim.topology.nodeAttributes[node_name] = {
                    "id": node_name,
                    **attrs,
                }
                created_nodes.append(str(node_name))
                touched_clusters.add(str(cluster_name))

            created_links: list[dict[str, Any]] = []
            for cluster_name in sorted(touched_clusters):
                cluster_nodes = sorted(
                    str(node_id)
                    for node_id, attrs in graph.nodes(data=True)
                    if str(attrs.get("cluster")) == cluster_name
                )
                for i in range(len(cluster_nodes)):
                    for j in range(i + 1, len(cluster_nodes)):
                        src = cluster_nodes[i]
                        dst = cluster_nodes[j]
                        if graph.has_edge(src, dst):
                            continue
                        edge_attrs = {
                            "PR": 1,
                            "BW": 1,
                            "intra_cluster": True,
                            "cluster": cluster_name,
                        }
                        graph.add_edge(src, dst, **edge_attrs)
                        created_links.append({"src": src, "dst": dst, **edge_attrs})

            self._invalidate_routing_cache()

            return {
                "nodes": created_nodes,
                "node_count": len(created_nodes),
                "clusters": sorted(touched_clusters),
                "links": created_links,
                "total_nodes": self.count_nodes(),
                "total_clusters": self.count_clusters(),
            }

    def update_node(
        self,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            payload = self._load_cluster_definition(definition)
            node_id = self._optional_payload_value(payload, "id", "node", "node_id")
            if not node_id:
                raise ValueError("Node update requires 'id', 'node', or 'node_id'")

            node_key = str(node_id)
            graph = self.sim.topology.G
            if not graph.has_node(node_key):
                raise ValueError(f"Node does not exist in the simulation: {node_key}")

            node_attrs = graph.nodes[node_key]
            capacity = dict(node_attrs.get("capacity", {}) or {})

            cpu_delta_raw = self._optional_payload_value(
                payload,
                "increment_cpu",
                "cpu",
            )
            memory_delta_raw = self._optional_payload_value(
                payload,
                "increment_memory",
                "memory",
            )
            ram_delta_raw = self._optional_payload_value(
                payload,
                "increment_ram",
                "ram",
            )
            cost_delta_raw = self._optional_payload_value(
                payload,
                "increment_cost",
                "cost",
                "COST",
            )

            cpu_delta = _parse_cpu_capacity(cpu_delta_raw) if cpu_delta_raw is not None else 0.0
            memory_delta = (
                _parse_memory_capacity(memory_delta_raw)
                if memory_delta_raw is not None
                else 0.0
            )
            ram_delta = (
                _parse_memory_capacity(ram_delta_raw)
                if ram_delta_raw is not None
                else 0.0
            )
            cost_delta = _safe_float(cost_delta_raw, 0.0) if cost_delta_raw is not None else 0.0

            if cpu_delta == 0.0 and memory_delta == 0.0 and ram_delta == 0.0 and cost_delta == 0.0:
                raise ValueError(
                    "Node update requires at least one increment among cpu, memory/ram, or cost"
                )

            current_cpu = _parse_cpu_capacity(capacity.get("cpu"))
            current_memory = _parse_memory_capacity(capacity.get("memory"))
            current_cost = _safe_float(node_attrs.get("COST"), 0.0)

            updated_cpu = max(current_cpu + cpu_delta, 0.0)
            updated_memory = max(current_memory + memory_delta + ram_delta, 0.0)
            updated_cost = max(current_cost + cost_delta, 0.0)

            capacity["cpu"] = _format_cpu_capacity(updated_cpu)
            capacity["memory"] = _format_memory_capacity(updated_memory)
            node_attrs["capacity"] = capacity
            if cost_delta_raw is not None or "COST" in node_attrs:
                node_attrs["COST"] = updated_cost

            self.sim.topology.nodeAttributes[node_key] = {
                "id": node_key,
                **dict(node_attrs),
            }

            return {
                "node": node_key,
                "cluster": node_attrs.get("cluster"),
                "cpu_total": updated_cpu,
                "memory_total": updated_memory,
                "cost": updated_cost,
            }

    def remove_node(self, node_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            node_key = str(node_id)
            graph = self.sim.topology.G
            if not graph.has_node(node_key):
                raise ValueError(f"Node does not exist in the simulation: {node_key}")

            node_attrs_snapshot = dict(graph.nodes[node_key])
            incident_edges = [
                (str(src), str(dst), dict(attrs))
                for src, dst, attrs in list(graph.edges(node_key, data=True))
            ]

            service_id_by_name: dict[str, Any] = {}
            for app_definition in self.infrastructure.service_definitions_data:
                app_name = str(app_definition.get("name"))
                service_id_by_name[app_name] = app_definition.get("id", app_name)

            des_on_node = [
                des
                for des, assigned_node in list(getattr(self.sim, "alloc_DES", {}).items())
                if str(assigned_node) == node_key
            ]

            affected_services: set[Any] = set()
            removed_module_des: list[int] = []
            removed_user_des: list[int] = []

            alloc_source = getattr(self.sim, "alloc_source", {}) or {}
            for des in list(des_on_node):
                if des not in alloc_source:
                    continue
                source = alloc_source.get(des, {})
                app_name = str(source.get("app"))
                affected_services.add(service_id_by_name.get(app_name, app_name))
                self.sim.undeploy_source(des)
                removed_user_des.append(des)

            alloc_module = getattr(self.sim, "alloc_module", {}) or {}
            for app_name, modules in alloc_module.items():
                for module_name, deployed_des in list(modules.items()):
                    for des in list(deployed_des):
                        assigned_node = getattr(self.sim, "alloc_DES", {}).get(des)
                        if str(assigned_node) != node_key:
                            continue
                        affected_services.add(
                            service_id_by_name.get(str(app_name), str(app_name))
                        )
                        self.sim.undeploy_module(app_name, module_name, des)
                        removed_module_des.append(des)

            remaining_des = [
                des
                for des, assigned_node in list(getattr(self.sim, "alloc_DES", {}).items())
                if str(assigned_node) == node_key
            ]
            for des in remaining_des:
                self.sim.stop_process(des)
                self.sim.alloc_DES.pop(des, None)

            topology = self.sim.topology
            if hasattr(topology, "archive_removed_node"):
                topology.archive_removed_node(node_key, node_attrs_snapshot)
            for src, dst, attrs in incident_edges:
                if hasattr(topology, "archive_removed_edge"):
                    topology.archive_removed_edge((src, dst), attrs)

            self.sim.topology.remove_node(node_key)

            entity_metrics = getattr(self.sim, "entity_metrics", None)
            if isinstance(entity_metrics, dict):
                entity_metrics.get("node", {}).pop(node_key, None)
                link_metrics = entity_metrics.get("link", {})
                for src, dst, _attrs in incident_edges:
                    canonical = Topology.canonical_edge((src, dst))
                    for edge_key in {
                        (src, dst),
                        (dst, src),
                        canonical,
                    }:
                        link_metrics.pop(edge_key, None)

            last_busy_time = getattr(self.sim, "last_busy_time", None)
            if isinstance(last_busy_time, dict):
                for src, dst, _attrs in incident_edges:
                    canonical = Topology.canonical_edge((src, dst))
                    for edge_key in {
                        (src, dst),
                        (dst, src),
                        canonical,
                    }:
                        last_busy_time.pop(edge_key, None)

            self._invalidate_routing_cache()

            unavailable_services: list[Any] = []
            for app_name, modules in getattr(self.sim, "alloc_module", {}).items():
                for deployed_des in modules.values():
                    if len(deployed_des) == 0:
                        service_id = service_id_by_name.get(str(app_name), str(app_name))
                        unavailable_services.append(service_id)
                        self.infrastructure.logger.warning(
                            "Application %s can no longer provide service after removing node %s",
                            app_name,
                            node_key,
                        )
                        break

            unavailable_services = sorted(set(unavailable_services), key=str)
            affected_service_list = sorted(set(affected_services), key=str)
            unplugged_users = len(removed_user_des)

            return {
                "status": "successful",
                "node": node_key,
                "id_services_affected": affected_service_list,
                "number_of_undeployed_vnf": len(removed_module_des),
                "number_of_unplugged_users": unplugged_users,
                "unavailable_services": unavailable_services,
                # "removed_des": sorted(removed_module_des + removed_user_des),
                "total_nodes": self.count_nodes(),
                "total_clusters": self.count_clusters(),
            }

    def remove_cluster(self, cluster_name: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            cluster_key = str(cluster_name)
            nodes = self.list_nodes_in_cluster(cluster_key)
            if not nodes:
                raise ValueError(
                    f"Cluster does not exist in the simulation: {cluster_key}"
                )

            removed_nodes: list[str] = []
            affected_services: set[Any] = set()
            unavailable_services: set[Any] = set()
            undeployed_vnfs = 0
            unplugged_users = 0

            for item in list(nodes):
                node_id = str(item["node"])
                summary = self.remove_node(node_id)
                removed_nodes.append(node_id)
                affected_services.update(summary.get("id_services_affected", []))
                unavailable_services.update(summary.get("unavailable_services", []))
                undeployed_vnfs += int(summary.get("number_of_undeployed_vnf", 0))
                unplugged_users += int(summary.get("number_of_unplugged_users", 0))

            return {
                "status": "successful",
                "cluster": cluster_key,
                "removed_nodes": sorted(removed_nodes),
                "node_count": len(removed_nodes),
                "id_services_affected": sorted(affected_services, key=str),
                "number_of_undeployed_vnf": undeployed_vnfs,
                "number_of_unplugged_users": unplugged_users,
                "unavailable_services": sorted(unavailable_services, key=str),
                "total_nodes": self.count_nodes(),
                "total_clusters": self.count_clusters(),
            }

    def remove_link(
        self,
        source_node_id: str,
        target_node_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            src = str(source_node_id)
            dst = str(target_node_id)
            graph = self.sim.topology.G
            if not graph.has_node(src):
                raise ValueError(f"Source node does not exist in the simulation: {src}")
            if not graph.has_node(dst):
                raise ValueError(f"Target node does not exist in the simulation: {dst}")
            if src == dst:
                raise ValueError("Source node and target node must be different")

            edge_key = Topology.canonical_edge((src, dst))
            if not graph.has_edge(*edge_key):
                raise ValueError(f"Link does not exist in the simulation: {src} <-> {dst}")

            attrs = dict(graph.edges[edge_key])
            if hasattr(self.sim.topology, "archive_removed_edge"):
                self.sim.topology.archive_removed_edge(edge_key, attrs)
            graph.remove_edge(*edge_key)

            entity_metrics = getattr(self.sim, "entity_metrics", None)
            if isinstance(entity_metrics, dict):
                entity_metrics.get("link", {}).pop(edge_key, None)

            last_busy_time = getattr(self.sim, "last_busy_time", None)
            if isinstance(last_busy_time, dict):
                last_busy_time.pop(edge_key, None)
                last_busy_time.pop((src, dst), None)
                last_busy_time.pop((dst, src), None)

            self._invalidate_routing_cache()

            return {
                "status": "successful",
                "source_node": src,
                "target_node": dst,
                "link": [edge_key[0], edge_key[1]],
                "attributes": attrs,
                "total_links": self.sim.topology.total_links(),
            }

    def restore_link(
        self,
        source_node_id: str,
        target_node_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            src = str(source_node_id)
            dst = str(target_node_id)
            graph = self.sim.topology.G
            if not graph.has_node(src):
                raise ValueError(f"Source node does not exist in the simulation: {src}")
            if not graph.has_node(dst):
                raise ValueError(f"Target node does not exist in the simulation: {dst}")
            if src == dst:
                raise ValueError("Source node and target node must be different")

            edge_key = Topology.canonical_edge((src, dst))
            if graph.has_edge(*edge_key):
                raise ValueError(f"Link already exists in the simulation: {src} <-> {dst}")

            attrs = self.sim.topology.removedEdgeAttributes.get(edge_key)
            if attrs is None:
                raise ValueError(f"No archived link exists for recovery: {src} <-> {dst}")

            graph.add_edge(edge_key[0], edge_key[1], **dict(attrs))
            entity_metrics = getattr(self.sim, "entity_metrics", None)
            if isinstance(entity_metrics, dict):
                entity_metrics.setdefault("link", {})[edge_key] = {
                    Topology.LINK_PR: attrs.get(Topology.LINK_PR),
                    Topology.LINK_BW: attrs.get(Topology.LINK_BW),
                }

            self._invalidate_routing_cache()

            return {
                "status": "successful",
                "source_node": src,
                "target_node": dst,
                "link": [edge_key[0], edge_key[1]],
                "attributes": dict(attrs),
                "total_links": self.sim.topology.total_links(),
            }

    def restore_node(self, node_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            node_key = str(node_id)
            graph = self.sim.topology.G
            if graph.has_node(node_key):
                raise ValueError(f"Node already exists in the simulation: {node_key}")

            topology = self.sim.topology
            archived_attrs = getattr(topology, "removedNodeAttributes", {}).get(node_key)
            if archived_attrs is None:
                raise ValueError(f"No archived node exists for recovery: {node_key}")

            graph.add_node(node_key, **dict(archived_attrs))
            topology.nodeAttributes[node_key] = {
                "id": node_key,
                **dict(archived_attrs),
            }

            entity_metrics = getattr(self.sim, "entity_metrics", None)
            if isinstance(entity_metrics, dict):
                entity_metrics.setdefault("node", {})[node_key] = {}

            restored_links: list[dict[str, Any]] = []
            removed_edges = getattr(topology, "removedEdgeAttributes", {})
            for edge_key, attrs in sorted(removed_edges.items(), key=lambda item: str(item[0])):
                src, dst = edge_key
                if node_key not in {str(src), str(dst)}:
                    continue
                if not graph.has_node(src) or not graph.has_node(dst):
                    continue
                if graph.has_edge(src, dst):
                    continue
                graph.add_edge(src, dst, **dict(attrs))
                restored_links.append(
                    {
                        "src": str(src),
                        "dst": str(dst),
                        **dict(attrs),
                    }
                )
                if isinstance(entity_metrics, dict):
                    entity_metrics.setdefault("link", {})[edge_key] = {
                        Topology.LINK_PR: attrs.get(Topology.LINK_PR),
                        Topology.LINK_BW: attrs.get(Topology.LINK_BW),
                    }

            self._invalidate_routing_cache()

            return {
                "status": "successful",
                "node": node_key,
                "cluster": archived_attrs.get("cluster"),
                "restored_links": restored_links,
                "restored_link_count": len(restored_links),
                "total_nodes": self.count_nodes(),
                "total_clusters": self.count_clusters(),
            }

    def remove_application_vnfs(self, app_ref: str | int) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            app_name = str(self.infrastructure._resolve_app_name(app_ref))
            alloc_module = getattr(self.sim, "alloc_module", {}) or {}
            if app_name not in alloc_module:
                raise ValueError(f"Application does not exist in the simulation: {app_ref}")

            service_ids = self._service_id_by_name()
            removed_des: list[int] = []
            removed_vnfs: list[str] = []

            for module_name, deployed_des in list(alloc_module[app_name].items()):
                removed_vnfs.append(str(module_name))
                for des in list(deployed_des):
                    self.sim.undeploy_module(app_name, module_name, des)
                    removed_des.append(des)

            unavailable_services = []
            if removed_des or removed_vnfs:
                unavailable_services.append(service_ids.get(app_name, app_name))

            return {
                "status": "successful",
                "id": service_ids.get(app_name, app_name),
                "app": app_name,
                "removed_vnfs": sorted(removed_vnfs),
                "number_of_removed_vnfs": len(removed_des),
                "removed_des": sorted(removed_des),
                "unavailable_services": unavailable_services,
            }

    def remove_application_vnf(
        self,
        app_ref: str | int,
        definition: str | Path | Mapping[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            app_name = str(self.infrastructure._resolve_app_name(app_ref))
            alloc_module = getattr(self.sim, "alloc_module", {}) or {}
            if app_name not in alloc_module:
                raise ValueError(f"Application does not exist in the simulation: {app_ref}")

            payload = self._load_application_definition(definition)
            module_name = payload.get("module_name") or payload.get("vnf")
            source_node = (
                payload.get("from_node")
                or payload.get("source_node")
                or payload.get("from")
                or payload.get("id_resource")
                or payload.get("node")
            )
            if not module_name:
                raise ValueError("VNF removal requires 'module_name' or 'vnf'")

            module_name = str(module_name)
            if source_node is not None:
                source_node = str(source_node)

            deployed_des = list(alloc_module.get(app_name, {}).get(module_name, []))
            if not deployed_des:
                raise ValueError(
                    f"Module '{module_name}' is not currently deployed for application '{app_name}'"
                )

            alloc_des = getattr(self.sim, "alloc_DES", {}) or {}
            candidates = [
                des
                for des in deployed_des
                if source_node is None or str(alloc_des.get(des)) == source_node
            ]
            if not candidates:
                raise ValueError(
                    f"Module '{module_name}' is not deployed on source node '{source_node}'"
                )

            removed: list[dict[str, Any]] = []
            for des in list(candidates):
                node_id = alloc_des.get(des)
                self.sim.undeploy_module(app_name, module_name, des)
                removed.append(
                    {
                        "des": des,
                        "node": str(node_id) if node_id is not None else None,
                    }
                )

            service_ids = self._service_id_by_name()
            remaining = len(
                getattr(self.sim, "alloc_module", {})
                .get(app_name, {})
                .get(module_name, [])
            )
            return {
                "status": "successful",
                "id": service_ids.get(app_name, app_name),
                "app": app_name,
                "vnf": module_name,
                "removed": sorted(
                    removed,
                    key=lambda item: (
                        "" if item["node"] is None else str(item["node"]),
                        int(item["des"]),
                    ),
                ),
                "removed_count": len(removed),
                "remaining_replicas": remaining,
            }

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        for app in self.infrastructure.services.values():
            self.sim.deploy_app(
                app,
                self.infrastructure.placement,
                self.infrastructure.routing,
            )

        # Replicates the setup phase of Sim.run() without executing env.run()
        # and without closing metrics, so the simulation can be advanced
        # incrementally and paused/resumed.
        self.sim.env.process(self.sim._Sim__network_process())  # noqa: SLF001

        for place in self.sim.placement_policy.items():
            for app_name in place[1]["apps"]:
                place[1]["placement_policy"].initial_allocation(self.sim, app_name)

        for user in self.infrastructure.users.get("sources", []):
            app_name = user["app"]
            app = self.sim.apps[app_name]
            msg = app.get_message(user["message"])
            node = user["id_resource"]
            dist = deterministic_distribution(
                time=user.get("lambda", 1),
                name=f"Deterministic-{app_name}-{node}",
            )
            self.sim.deploy_source(
                app_name,
                id_node=node,
                msg=msg,
                distribution=dist,
                source_definition=user,
            )

        for registration in self._registered_processes.values():
            self._deploy_registered_process(registration)

        self._initialized = True

    def _flush_metrics_if_needed(self) -> None:
        with self._lock:
            if self._metrics_closed:
                return
            try:
                self.sim.metrics.flush()
            except Exception:
                pass

    def _close_metrics_if_needed(self) -> None:
        with self._lock:
            if self._metrics_closed:
                return
            try:
                self.sim.metrics.flush()
            except Exception:
                pass
            try:
                self.sim.metrics.close()
            except Exception:
                pass
            self._metrics_closed = True

    def start_thread(self, step: float = 1.0) -> None:
        with self._lock:
            self._step = float(step)
            self._stop_requested.clear()
            self._pause_event.set()
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._run_loop,
                name="yafs-simulation-thread",
                daemon=True,
            )
            self._thread.start()

    def _run_loop(self) -> None:
        while not self._stop_requested.is_set():
            self._pause_event.wait()
            if self._stop_requested.is_set():
                break

            with self._lock:
                self._ensure_initialized()

                if self._scheduled_until is None:
                    time.sleep(0.01)
                    continue

                now = float(self.sim.env.now)
                if now >= float(self._scheduled_until):
                    self._flush_metrics_if_needed()
                    time.sleep(0.01)
                    continue

                next_until = min(now + self._step, float(self._scheduled_until))

            self.sim.until = next_until
            self._idle_event.clear()
            try:
                self.sim.env.run(until=next_until)
                if next_until >= float(self._scheduled_until):
                    self._flush_metrics_if_needed()
            finally:
                self._idle_event.set()

    def run_for(self, duration: float, *, step: float | None = None) -> dict[str, Any]:
        """
        Advance the simulation for a time window in a background thread.

        The method schedules execution and returns immediately with a state
        snapshot. Poll `get_state()` to observe progress.
        """
        with self._lock:
            self._ensure_initialized()
            if step is not None:
                self._step = float(step)
            self.start_thread(step=self._step)

            now = float(self.sim.env.now)
            self._scheduled_until = now + float(duration)
            return self.get_state()

    def run(
        self,
        *,
        stop_time: float,
        step: float | None = None,
        poll_interval: float = 0.01,
    ) -> dict[str, Any]:
        """
        Run the simulation until the requested stop time using the incremental
        execution loop, blocking until completion.
        """
        with self._lock:
            now = float(self.sim.env.now)
        duration = max(0.0, float(stop_time) - now)
        state = self.run_for(duration=duration, step=step)

        while True:
            current = self.get_state()
            if current["stop_requested"]:
                return current
            scheduled_until = current["scheduled_until"]
            if scheduled_until is not None and current["now"] >= float(scheduled_until):
                return current
            time.sleep(poll_interval)

    def pause(self) -> None:
        self._pause_event.clear()
        self._idle_event.wait()

    def resume(self) -> None:
        self._pause_event.set()

    def stop(self) -> None:
        self._stop_requested.set()
        self._pause_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._close_metrics_if_needed()

    def is_running(self) -> bool:
        t = self._thread
        if not (t is not None and t.is_alive() and self._pause_event.is_set()):
            return False
        scheduled_until = self._scheduled_until
        if scheduled_until is None:
            return False
        return float(self.sim.env.now) < float(scheduled_until)

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            alloc_module = getattr(self.sim, "alloc_module", {}) or {}
            alloc_module_count = 0
            for app_modules in alloc_module.values():
                for deployed in app_modules.values():
                    alloc_module_count += len(deployed)

            return {
                "now": float(self.sim.env.now),
                "initialized": self._initialized,
                "paused": not self._pause_event.is_set(),
                "stop_requested": self._stop_requested.is_set(),
                "scheduled_until": self._scheduled_until,
                "step": self._step,
                "network_buffer": int(getattr(self.sim, "network_pump", 0)),
                "alloc_source_count": len(getattr(self.sim, "alloc_source", {})),
                "alloc_module_count": alloc_module_count,
            }

    def get_metrics_snapshot(self) -> dict[str, Any]:
        """
        Lightweight metrics snapshot (does not parse CSV outputs).
        """
        with self._lock:
            return {
                "entity_metrics": getattr(self.sim, "entity_metrics", None),
                "unreachabled_links": int(
                    getattr(self.sim, "unreachabled_links", 0)
                ),
            }

    def get_application_metrics_summary(
        self,
        *,
        from_time: float | None = None,
        to_time: float | None = None,
        time_column: str = "end_time",
        response_strategy: str = "critical_path",
        include_return_messages: bool = True,
        egress_cost_per_gb: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Summarize application metrics over the requested time window.

        Parameters
        ----------
        from_time, to_time:
            Optional absolute simulation-time bounds applied to the aggregated
            service-response rows reconstructed from the CSV traces.
        time_column:
            Column used as the temporal axis for the filter. Typical values are
            ``"end_time"`` and ``"start_time"``.
        """
        with self._lock:
            self._ensure_initialized()
            self._flush_metrics_if_needed()

            analyzer = MetricsAnalyzer(
                defaultPath=self.results_path,
                app_definition=self.infrastructure.service_definitions_data,
            )

            response_summary = analyzer.summarize_service_response(
                from_time=from_time,
                to_time=to_time,
                time_column=time_column,
                strategy=response_strategy,
                include_return_messages=include_return_messages,
            )

            live_topology_info = self._live_topology_info()
            node_regions = {
                node_id: attrs.get("cluster_region")
                for node_id, attrs in live_topology_info.items()
                if attrs.get("cluster_region")
            }

            if egress_cost_per_gb is not None:
                egress_summary = analyzer.estimate_egress_cost(
                    node_regions=node_regions,
                    cost_per_gb=egress_cost_per_gb,
                    from_time=from_time,
                    to_time=to_time,
                    time_column=time_column,
                )
            else:
                egress_summary = None

            topology_info = live_topology_info
            placement_by_app: dict[str, dict[str, Any]] = {}
            alloc_module = getattr(self.sim, "alloc_module", {}) or {}
            alloc_des = getattr(self.sim, "alloc_DES", {}) or {}

            for app_key, modules in alloc_module.items():
                app_name = str(app_key)
                placement_cost = 0.0
                deployments = 0

                for deployed_des in modules.values():
                    for des in deployed_des:
                        node_id = alloc_des.get(des)
                        if node_id is None:
                            continue
                        node_attrs = topology_info.get(node_id, {})
                        placement_cost += float(node_attrs.get("COST", 0.0) or 0.0)
                        deployments += 1

                placement_by_app[app_name] = {
                    "placement_cost": placement_cost,
                    "deployments": deployments,
                }

            response_by_app = {
                str(row["app"]): dict(row)
                for row in response_summary.to_dict(orient="records")
            }
            egress_by_app = (
                {
                    str(row["app"]): float(row["egress_cost"])
                    for row in egress_summary.to_dict(orient="records")
                }
                if egress_summary is not None
                else {}
            )

            known_apps = sorted(str(name) for name in self.infrastructure.services.keys())

            results: list[dict[str, Any]] = []
            for app_name in known_apps:
                response_item = response_by_app.get(
                    app_name,
                    {
                        "app": app_name,
                        "requests_total": 0.0,
                        "requests_successful": 0.0,
                        "requests_unsuccessful": 0.0,
                        "response_mean": math.nan,
                        "response_p50": math.nan,
                        "response_p95": math.nan,
                        "response_max": math.nan,
                        "network_mean": math.nan,
                        "processing_mean": math.nan,
                        "waiting_mean": math.nan,
                    },
                )
                placement_item = placement_by_app.get(
                    app_name,
                    {
                        "placement_cost": 0.0,
                        "deployments": 0,
                    },
                )
                egress_cost = egress_by_app.get(app_name, 0.0)
                item = {
                    **response_item,
                    **placement_item,
                    "egress_cost": egress_cost,
                    "total_cost": placement_item["placement_cost"] + egress_cost,
                }
                results.append(item)

            return results

    def _module_resource_catalog(self) -> dict[str, dict[str, dict[str, float]]]:
        catalog: dict[str, dict[str, dict[str, float]]] = {}
        for app in self.infrastructure.service_definitions_data:
            app_name = str(app.get("name"))
            modules: dict[str, dict[str, float]] = {}
            for module in app.get("module", []):
                module_name = str(module.get("name"))
                modules[module_name] = {
                    "cpu": _safe_float(module.get("cpu"), 0.0),
                    "ram": _safe_float(
                        module.get("ram", module.get("RAM")),
                        0.0,
                    ),
                }
            catalog[app_name] = modules
        return catalog

    def _service_id_by_name(self) -> dict[str, Any]:
        mapping: dict[str, Any] = {}
        for app in self.infrastructure.service_definitions_data:
            app_name = str(app.get("name"))
            mapping[app_name] = app.get("id", app_name)
        return mapping

    @staticmethod
    def _resource_utilization(used: float, total: float) -> float:
        if total <= 0.0:
            return 0.0
        return max(min(used / total, 1.0), 0.0)

    def get_users_per_node(self) -> list[dict[str, Any]]:
        with self._lock:
            self._ensure_initialized()

            counts = {node_id: 0 for node_id in self._live_topology_info().keys()}
            for source in getattr(self.sim, "alloc_source", {}).values():
                node_id = str(source.get("id"))
                if node_id in counts:
                    counts[node_id] += 1

            return [
                {"node": node_id, "users": counts[node_id]}
                for node_id in sorted(counts, key=str)
            ]

    def list_users(
        self,
        *,
        app_ref: str | int | None = None,
        node_id: str | None = None,
        cluster_name: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            topology_info = self._live_topology_info()
            node_filter = str(node_id) if node_id is not None else None
            if node_filter is not None and node_filter not in topology_info:
                raise ValueError(f"Node does not exist in the simulation: {node_filter}")

            app_filter = None
            if app_ref is not None:
                app_filter = str(self.infrastructure._resolve_app_name(app_ref))
                if app_filter not in self.infrastructure.services:
                    raise ValueError(
                        f"Application does not exist in the simulation: {app_ref}"
                    )

            cluster_filter = str(cluster_name) if cluster_name is not None else None
            cluster_nodes: set[str] | None = None
            if cluster_filter is not None:
                cluster_nodes = {
                    str(item["node"]) for item in self.list_nodes_in_cluster(cluster_filter)
                }
                if not cluster_nodes:
                    raise ValueError(
                        f"Cluster does not exist in the simulation: {cluster_filter}"
                    )

            service_ids = self._service_id_by_name()
            alloc_source = getattr(self.sim, "alloc_source", {}) or {}
            users: list[dict[str, Any]] = []

            for des, source in sorted(alloc_source.items(), key=lambda item: int(item[0])):
                source_node = str(source.get("id"))
                app_name = str(source.get("app"))
                if app_filter is not None and app_name != app_filter:
                    continue
                if node_filter is not None and source_node != node_filter:
                    continue
                if cluster_nodes is not None and source_node not in cluster_nodes:
                    continue

                node_info = topology_info.get(source_node, {})
                users.append(
                    {
                        "des": des,
                        "id": service_ids.get(app_name, app_name),
                        "app": app_name,
                        "node": source_node,
                        "cluster": node_info.get("cluster"),
                        "message": source.get("name"),
                        "module": source.get("module"),
                        "lambda": source.get("lambda"),
                    }
                )

            return {
                "filters": {
                    "app": app_filter,
                    "node": node_filter,
                    "cluster": cluster_filter,
                },
                "users": users,
                "user_count": len(users),
            }

    def list_deployed_applications(self) -> list[Any]:
        with self._lock:
            self._ensure_initialized()

            service_ids = self._service_id_by_name()
            alloc_module = getattr(self.sim, "alloc_module", {}) or {}
            deployed: list[Any] = []
            for app_name, modules in alloc_module.items():
                total = sum(len(deployed_des) for deployed_des in modules.values())
                if total <= 0:
                    continue
                canonical_name = str(self.infrastructure._resolve_app_name(app_name))
                deployed.append(service_ids.get(canonical_name, canonical_name))
            return sorted(deployed, key=str)

    def list_application_vnfs(self, app_ref: str | int) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            app_name = str(self.infrastructure._resolve_app_name(app_ref))
            alloc_module = getattr(self.sim, "alloc_module", {}) or {}
            if app_name not in alloc_module:
                raise ValueError(f"Application does not exist in the simulation: {app_ref}")

            service_ids = self._service_id_by_name()
            alloc_des = getattr(self.sim, "alloc_DES", {}) or {}
            topology_info = self._live_topology_info()

            vnfs: list[dict[str, Any]] = []
            for module_name, deployed_des in sorted(
                alloc_module[app_name].items(),
                key=lambda item: str(item[0]),
            ):
                deployments: list[dict[str, Any]] = []
                for des in deployed_des:
                    node_id = alloc_des.get(des)
                    if node_id is None:
                        continue
                    node_key = str(node_id)
                    attrs = topology_info.get(node_key, {})
                    deployments.append(
                        {
                            "des": des,
                            "node": node_key,
                            "cluster": attrs.get("cluster"),
                        }
                    )

                vnfs.append(
                    {
                        "vnf": str(module_name),
                        "deployment_count": len(deployments),
                        "nodes": sorted(str(item["node"]) for item in deployments),
                        "deployments": sorted(
                            deployments,
                            key=lambda item: (str(item["node"]), int(item["des"])),
                        ),
                    }
                )

            return {
                "id": service_ids.get(app_name, app_name),
                "app": app_name,
                "vnfs": vnfs,
            }

    def list_node_placements(self, node_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()

            node_key = str(node_id)
            topology_info = self._live_topology_info()
            if node_key not in topology_info:
                raise ValueError(f"Node does not exist in the simulation: {node_key}")

            service_ids = self._service_id_by_name()
            alloc_module = getattr(self.sim, "alloc_module", {}) or {}
            alloc_des = getattr(self.sim, "alloc_DES", {}) or {}

            placements: list[dict[str, Any]] = []
            for app_name, modules in alloc_module.items():
                canonical_name = str(self.infrastructure._resolve_app_name(app_name))
                app_id = service_ids.get(canonical_name, canonical_name)
                for module_name, deployed_des in modules.items():
                    for des in deployed_des:
                        assigned_node = alloc_des.get(des)
                        if str(assigned_node) != node_key:
                            continue
                        placements.append(
                            {
                                "id": app_id,
                                "app": canonical_name,
                                "vnf": str(module_name),
                                "des": des,
                            }
                        )

            node_info = topology_info[node_key]
            return {
                "node": node_key,
                "cluster": node_info.get("cluster"),
                "placements": sorted(
                    placements,
                    key=lambda item: (str(item["app"]), str(item["vnf"]), int(item["des"])),
                ),
                "placement_count": len(placements),
            }

    def list_nodes(self) -> list[dict[str, Any]]:
        with self._lock:
            topology_info = self._live_topology_info()
            rows: list[dict[str, Any]] = []
            for node_id, attrs in topology_info.items():
                rows.append(
                    {
                        "node": str(node_id),
                        "cluster": attrs.get("cluster"),
                        "cluster_role": attrs.get("cluster_role"),
                        "cluster_region": attrs.get("cluster_region"),
                        "node_role": attrs.get("node_role"),
                    }
                )
            return sorted(rows, key=lambda item: item["node"])

    def list_clusters(self) -> list[dict[str, Any]]:
        with self._lock:
            clusters: dict[str, dict[str, Any]] = {}
            for item in self.list_nodes():
                cluster_name = item.get("cluster")
                if cluster_name is None:
                    continue
                entry = clusters.setdefault(
                    str(cluster_name),
                    {
                        "cluster": str(cluster_name),
                        "cluster_role": item.get("cluster_role"),
                        "cluster_region": item.get("cluster_region"),
                        "nodes": [],
                    },
                )
                entry["nodes"].append(item["node"])

            for entry in clusters.values():
                entry["nodes"].sort()
                entry["node_count"] = len(entry["nodes"])

            return sorted(clusters.values(), key=lambda item: item["cluster"])

    def list_nodes_in_cluster(self, cluster_name: str) -> list[dict[str, Any]]:
        cluster_key = str(cluster_name)
        return [
            item
            for item in self.list_nodes()
            if str(item.get("cluster")) == cluster_key
        ]

    def count_nodes(self) -> int:
        with self._lock:
            return len(self._live_topology_info())

    def count_clusters(self) -> int:
        with self._lock:
            return len(self.list_clusters())

    def get_node_resource_summary(
        self,
        node_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            self._ensure_initialized()

            topology_info = self._live_topology_info()
            resource_catalog = self._module_resource_catalog()
            alloc_module = getattr(self.sim, "alloc_module", {}) or {}
            alloc_des = getattr(self.sim, "alloc_DES", {}) or {}
            users_by_node = {
                item["node"]: item["users"] for item in self.get_users_per_node()
            }

            used: dict[str, dict[str, Any]] = {
                str(current_node): {
                    "cpu_used": 0.0,
                    "ram_used": 0.0,
                    "deployments": 0,
                }
                for current_node in topology_info.keys()
            }

            for app_name, modules in alloc_module.items():
                app_key = self.infrastructure._resolve_app_name(app_name)
                app_resources = resource_catalog.get(str(app_key), {})
                for module_name, deployed_des in modules.items():
                    module_resources = app_resources.get(
                        str(module_name),
                        {"cpu": 0.0, "ram": 0.0},
                    )
                    for des in deployed_des:
                        deployed_node = alloc_des.get(des)
                        if deployed_node is None:
                            continue
                        node_key = str(deployed_node)
                        if node_key not in used:
                            continue
                        used[node_key]["cpu_used"] += module_resources["cpu"]
                        used[node_key]["ram_used"] += module_resources["ram"]
                        used[node_key]["deployments"] += 1

            rows: list[dict[str, Any]] = []
            for current_node, attrs in topology_info.items():
                current_node_key = str(current_node)
                if node_id is not None and current_node_key != str(node_id):
                    continue

                capacity = attrs.get("capacity", {})
                cpu_total = _parse_cpu_capacity(capacity.get("cpu"))
                ram_total = _parse_memory_capacity(capacity.get("memory"))
                cpu_used = _safe_float(used[current_node_key]["cpu_used"], 0.0)
                ram_used = _safe_float(used[current_node_key]["ram_used"], 0.0)
                cpu_available = max(cpu_total - cpu_used, 0.0)
                ram_available = max(ram_total - ram_used, 0.0)
                cpu_utilization = self._resource_utilization(cpu_used, cpu_total)
                ram_utilization = self._resource_utilization(ram_used, ram_total)
                rows.append(
                    {
                        "node": current_node_key,
                        "cluster": attrs.get("cluster"),
                        "cpu_used": cpu_used,
                        "cpu_available": cpu_available,
                        "cpu_total": cpu_total,
                        "ram_used": ram_used,
                        "ram_available": ram_available,
                        "ram_total": ram_total,
                        "cpu_utilization": cpu_utilization,
                        "ram_utilization": ram_utilization,
                        "utilization": (cpu_utilization + ram_utilization) / 2.0,
                        "deployments": int(used[current_node_key]["deployments"]),
                        "users": int(users_by_node.get(current_node_key, 0)),
                    }
                )

            return sorted(rows, key=lambda item: item["node"])

    def get_node_cpu_summary(self, node_id: str) -> dict[str, Any]:
        rows = self.get_node_resource_summary(node_id=node_id)
        if not rows:
            return {
                "node": str(node_id),
                "cpu_used": 0.0,
                "cpu_available": 0.0,
                "cpu_total": 0.0,
                "cpu_utilization": 0.0,
            }
        row = rows[0]
        return {
            "node": row["node"],
            "cpu_used": row["cpu_used"],
            "cpu_available": row["cpu_available"],
            "cpu_total": row["cpu_total"],
            "cpu_utilization": row["cpu_utilization"],
        }

    def get_node_memory_summary(self, node_id: str) -> dict[str, Any]:
        rows = self.get_node_resource_summary(node_id=node_id)
        if not rows:
            return {
                "node": str(node_id),
                "ram_used": 0.0,
                "ram_available": 0.0,
                "ram_total": 0.0,
                "ram_utilization": 0.0,
            }
        row = rows[0]
        return {
            "node": row["node"],
            "ram_used": row["ram_used"],
            "ram_available": row["ram_available"],
            "ram_total": row["ram_total"],
            "ram_utilization": row["ram_utilization"],
        }

    def get_cluster_resource_summary(self) -> list[dict[str, Any]]:
        with self._lock:
            node_rows = self.get_node_resource_summary()
            if not node_rows:
                return []

            frame = pd.DataFrame.from_records(node_rows)
            summary = (
                frame.groupby("cluster", dropna=False)
                .agg(
                    cpu_used=("cpu_used", "sum"),
                    cpu_available=("cpu_available", "sum"),
                    cpu_total=("cpu_total", "sum"),
                    ram_used=("ram_used", "sum"),
                    ram_available=("ram_available", "sum"),
                    ram_total=("ram_total", "sum"),
                    deployments=("deployments", "sum"),
                    users=("users", "sum"),
                    nodes=("node", "count"),
                )
                .reset_index()
            )
            summary["cpu_utilization"] = np.where(
                summary["cpu_total"] > 0,
                summary["cpu_used"] / summary["cpu_total"],
                0.0,
            )
            summary["ram_utilization"] = np.where(
                summary["ram_total"] > 0,
                summary["ram_used"] / summary["ram_total"],
                0.0,
            )
            summary["utilization"] = (
                summary["cpu_utilization"] + summary["ram_utilization"]
            ) / 2.0

            return summary.sort_values("cluster").to_dict(orient="records")

    def get_network_metrics_summary(
        self,
        *,
        response_strategy: str = "critical_path",
        include_return_messages: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_initialized()
            self._flush_metrics_if_needed()

            topology = self.sim.topology
            analyzer = MetricsAnalyzer(
                defaultPath=self.results_path,
                app_definition=self.infrastructure.service_definitions_data,
            )

            return {
                "node_utilization": self.get_node_resource_summary(),
                "cluster_utilization": self.get_cluster_resource_summary(),
                "users_per_node": self.get_users_per_node(),
                "link_utilization": analyzer.link_utilization(
                    topology,
                    include_unused=True,
                ).to_dict(orient="records"),
                "request_hops": analyzer.request_hops().to_dict(orient="records"),
                "application_response_latency": (
                    analyzer.average_application_response_latency(
                        strategy=response_strategy,
                        include_return_messages=include_return_messages,
                    ).to_dict(orient="records")
                ),
                "request_distance_km": analyzer.request_distance_breakdown(
                    topology
                ).to_dict(orient="records"),
                "application_distance_km": analyzer.application_distance_breakdown(
                    topology
                ).to_dict(orient="records"),
                "mean_topology_congestion": analyzer.mean_topology_congestion(
                    topology
                ),
                "total_bandwidth_used": analyzer.total_bandwidth_used(topology),
                "total_bandwidth_available": analyzer.total_bandwidth_available(
                    topology
                ),
                "total_links": analyzer.total_links(topology),
            }

    def fork(self, *, results_suffix: str | None = None) -> "Simulation":
        """
        Clone (fork) the current simulation state into an independent instance.

        The fork recreates the simulation from the same scenario and seed, then
        deterministically replays it up to the parent's current simulation time.
        This avoids deep-copying live SimPy processes, which are backed by
        generator objects and cannot be cloned safely.
        """
        with self._lock:
            self.pause()
            self._ensure_initialized()
            current_now = float(self.sim.env.now)
            seed = self.sim.seed

            if results_suffix is None:
                results_suffix = f"fork_{int(current_now)}"

        child_infrastructure = self.infrastructure.clone()
        child = Simulation(
            infrastructure=child_infrastructure,
            seed=seed,
            results_suffix=results_suffix,
        )
        child._step = self._step
        for name, registration in self._registered_processes.items():
            child._registered_processes[name] = RegisteredProcess(
                name=registration.name,
                callback=registration.callback,
                distribution=copy.deepcopy(registration.distribution),
                params=copy.deepcopy(registration.params),
                kind=registration.kind,
                definition=copy.deepcopy(registration.definition),
                enabled=registration.enabled,
                activation_count=registration.activation_count,
            )

        if current_now > 0:
            child._ensure_initialized()
            child.sim.until = current_now
            child.sim.env.run(until=current_now)

        return child

    def print_debug_assignaments(self):
        self.sim.print_debug_assignaments()
