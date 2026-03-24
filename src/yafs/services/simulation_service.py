from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from pathlib import Path

from ..api import Infrastructure, Simulation
from .models import (
    ApplicationMetricsSummary,
    ManagedSimulation,
    SimulationApplicationMetrics,
    SimulationMetricsSnapshot,
    SimulationState,
    SimulationStatus,
    SimulationSummary,
)
from .registry import SimulationRegistry


class SimulationService:
    """
    High-level orchestration API for long-lived simulations.

    The service treats a simulation as an open-ended process. Execution is
    requested in scheduled windows, the simulation becomes ``idle`` when a
    scheduled window finishes, and it only becomes terminal after ``stop()``.
    """

    def __init__(
        self,
        registry: SimulationRegistry | None = None,
        *,
        default_results_root: str | Path | None = None,
        default_configuration_root: str | Path | None = None,
    ) -> None:
        self.registry = registry or SimulationRegistry()
        self._lock = threading.RLock()
        self.default_results_root = (
            None if default_results_root is None else Path(default_results_root)
        )
        self.default_configuration_root = (
            None
            if default_configuration_root is None
            else Path(default_configuration_root)
        )

    def create_simulation(
        self,
        *,
        scenario_path: str | Path,
        results_path: str | Path | None = None,
        seed: int | None = None,
        name: str | None = None,
        simulation_id: str | None = None,
        parent_id: str | None = None,
        services_definition_path: str | Path | None = None,
        users_definition_path: str | Path | None = None,
        placement_definition_path: str | Path | None = None,
        topology_path: str | Path | None = None,
    ) -> SimulationState:
        scenario = Path(scenario_path)
        if simulation_id is None:
            simulation_id = self._new_id()
        if name is None:
            name = simulation_id
        if results_path is None and self.default_results_root is not None:
            results_path = self.default_results_root

        infrastructure = Infrastructure(
            path_to_lab_scenario=scenario,
            results_path=results_path,
            services_definition_path=services_definition_path,
            users_definition_path=users_definition_path,
            placement_definition_path=placement_definition_path,
            topology_path=topology_path,
        )
        simulation = Simulation(
            infrastructure=infrastructure,
            seed=seed,
            results_suffix=simulation_id,
        )
        managed = ManagedSimulation(
            id=simulation_id,
            name=name,
            scenario_path=scenario,
            simulation=simulation,
            seed=seed,
            parent_id=parent_id,
        )
        self.registry.add(managed)
        return self.get_state(simulation_id)

    @staticmethod
    def _looks_like_scenario_directory(path: Path) -> bool:
        required_files = (
            "logging.ini",
            "topology.json",
            "services.json",
            "placements.json",
            "users.json",
        )
        return path.is_dir() and all((path / name).exists() for name in required_files)

    @staticmethod
    def _sanitize_configuration_name(name: str) -> str:
        cleaned = "".join(
            ch if ch.isalnum() or ch in {"-", "_"} else "-"
            for ch in str(name).strip()
        ).strip("-")
        if not cleaned:
            raise ValueError("Configuration name must contain alphanumeric characters")
        return cleaned

    @staticmethod
    def _role_for_cluster(index: int) -> str:
        default_roles = ["CDC", "MEC", "EDC"]
        if index < len(default_roles):
            return default_roles[index]
        return f"CLUSTER-{index}"

    @staticmethod
    def _cluster_name_for_role(role: str, index: int) -> str:
        normalized = str(role).lower().replace(" ", "-")
        return f"{normalized}-{index}"

    def _build_generated_topology_definition(
        self,
        *,
        cluster_count: int,
        nodes_per_cluster: int,
    ) -> dict[str, object]:
        if cluster_count < 1:
            raise ValueError("cluster_count must be >= 1")
        if nodes_per_cluster < 1:
            raise ValueError("nodes_per_cluster must be >= 1")

        clusters: list[dict[str, object]] = []
        links: list[dict[str, object]] = []

        for cluster_index in range(cluster_count):
            role = self._role_for_cluster(cluster_index)
            cluster_name = self._cluster_name_for_role(role, cluster_index)
            nodes = [
                {
                    "name": f"{cluster_name}-control-plane",
                    "role": "control-plane",
                    "capacity": {
                        "cpu": "2.0",
                        "memory": "4096m",
                    },
                }
            ]
            for worker_index in range(max(nodes_per_cluster - 1, 0)):
                nodes.append(
                    {
                        "name": f"{cluster_name}-worker-{worker_index + 1}",
                        "role": "worker",
                        "capacity": {
                            "cpu": "1.0",
                            "memory": "3072m",
                        },
                    }
                )

            clusters.append(
                {
                    "name": cluster_name,
                    "role": role,
                    "region": f"region-{chr(97 + (cluster_index % 26))}",
                    "nodes": nodes,
                }
            )

        for cluster_index in range(cluster_count - 1):
            links.append(
                {
                    "from": clusters[cluster_index]["name"],
                    "to": clusters[cluster_index + 1]["name"],
                    "bidirectional": True,
                    "distanceKm": 50 * (cluster_index + 1),
                    "targetOneWayLatencyMs": 10 * (cluster_index + 1),
                    "bandwidth": 1,
                }
            )

        return {
            "labName": "generated-topology",
            "description": (
                f"Generated topology with {cluster_count} clusters and "
                f"{nodes_per_cluster} nodes per cluster."
            ),
            "clusters": clusters,
            "links": links,
        }

    def _resolve_generated_topology_definition(
        self,
        *,
        base_scenario_path: Path,
        topology_definition_path: str | Path | None = None,
        topology_definition: dict[str, object] | None = None,
        cluster_count: int | None = None,
        nodes_per_cluster: int | None = None,
    ) -> dict[str, object]:
        if topology_definition is not None:
            return dict(topology_definition)
        if topology_definition_path is not None:
            path = Path(topology_definition_path)
            if not path.is_absolute():
                path = base_scenario_path / path
            return json.loads(path.read_text(encoding="utf-8"))
        if cluster_count is None:
            raise ValueError(
                "Configuration creation requires either topology_definition(_path) "
                "or cluster_count"
            )
        return self._build_generated_topology_definition(
            cluster_count=int(cluster_count),
            nodes_per_cluster=int(nodes_per_cluster or 3),
        )

    @staticmethod
    def _generated_node_groups(
        topology_definition: dict[str, object],
    ) -> tuple[list[str], list[str], list[str]]:
        all_nodes: list[str] = []
        worker_nodes: list[str] = []
        control_nodes: list[str] = []

        for cluster in topology_definition.get("clusters", []):
            for node in cluster.get("nodes", []):
                node_name = str(node["name"])
                all_nodes.append(node_name)
                if str(node.get("role")) == "control-plane":
                    control_nodes.append(node_name)
                else:
                    worker_nodes.append(node_name)

        return all_nodes, worker_nodes, control_nodes

    @staticmethod
    def _generate_placements(
        services_definition: list[dict[str, object]],
        *,
        all_nodes: list[str],
        worker_nodes: list[str],
        control_nodes: list[str],
    ) -> dict[str, object]:
        if not all_nodes:
            raise ValueError("Topology must contain at least one node")

        placement_nodes = worker_nodes or control_nodes or all_nodes
        fallback_nodes = control_nodes or all_nodes
        allocation: list[dict[str, object]] = []
        placement_index = 0

        for app in services_definition:
            modules = app.get("module", [])
            for module in modules:
                module_name = module.get("name")
                if not module_name:
                    continue

                if str(module_name).endswith("_ID"):
                    target_node = fallback_nodes[placement_index % len(fallback_nodes)]
                else:
                    target_node = placement_nodes[placement_index % len(placement_nodes)]

                allocation.append(
                    {
                        "module_name": module_name,
                        "app": app["id"],
                        "id_resource": target_node,
                    }
                )
                placement_index += 1

        return {"initialAllocation": allocation}

    @staticmethod
    def _generate_users(
        services_definition: list[dict[str, object]],
        *,
        worker_nodes: list[str],
        all_nodes: list[str],
    ) -> dict[str, object]:
        source_nodes = worker_nodes or all_nodes
        if not source_nodes:
            raise ValueError("Topology must contain at least one node")

        sources: list[dict[str, object]] = []
        source_index = 0
        for app in services_definition:
            source_message = None
            for message in app.get("message", []):
                if str(message.get("s")) == "None":
                    source_message = str(message["name"])
                    break
            if source_message is None:
                continue

            sources.append(
                {
                    "id_resource": source_nodes[source_index % len(source_nodes)],
                    "app": app["id"],
                    "message": source_message,
                    "lambda": 200,
                }
            )
            source_index += 1

        return {"sources": sources}

    def create_simulation_configuration(
        self,
        *,
        base_scenario_path: str | Path,
        configuration_name: str,
        topology_definition_path: str | Path | None = None,
        topology_definition: dict[str, object] | None = None,
        cluster_count: int | None = None,
        nodes_per_cluster: int | None = None,
        output_root: str | Path | None = None,
    ) -> dict[str, object]:
        base_path = Path(base_scenario_path)
        if not base_path.exists():
            raise FileNotFoundError(f"Base scenario path does not exist: {base_path}")

        config_name = self._sanitize_configuration_name(configuration_name)
        if output_root is None and self.default_configuration_root is not None:
            output_root = self.default_configuration_root
        if output_root is None:
            output_root = base_path / "generated-configurations"
        output_root = Path(output_root)
        config_path = output_root / config_name
        config_path.mkdir(parents=True, exist_ok=True)
        (config_path / "services").mkdir(parents=True, exist_ok=True)

        topology_data = self._resolve_generated_topology_definition(
            base_scenario_path=base_path,
            topology_definition_path=topology_definition_path,
            topology_definition=topology_definition,
            cluster_count=cluster_count,
            nodes_per_cluster=nodes_per_cluster,
        )

        services_source = Infrastructure._resolve_scenario_file(
            base_path,
            None,
            "services.json",
        )
        services_definition = json.loads(services_source.read_text(encoding="utf-8"))
        all_nodes, worker_nodes, control_nodes = self._generated_node_groups(
            topology_data
        )
        placements_definition = self._generate_placements(
            services_definition,
            all_nodes=all_nodes,
            worker_nodes=worker_nodes,
            control_nodes=control_nodes,
        )
        users_definition = self._generate_users(
            services_definition,
            worker_nodes=worker_nodes,
            all_nodes=all_nodes,
        )

        required_files_to_copy = [
            ("logging.ini", "logging.ini"),
            ("services.json", "services.json"),
        ]
        optional_files_to_copy = [
            ("services/kind-config.yaml", "services/kind-config.yaml"),
        ]
        for source_name, target_name in required_files_to_copy:
            source = base_path / source_name
            if not source.exists():
                raise FileNotFoundError(
                    f"Required base scenario file not found: {source}"
                )
            target = config_path / target_name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        for source_name, target_name in optional_files_to_copy:
            source = base_path / source_name
            if not source.exists():
                continue
            target = config_path / target_name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

        (config_path / "topology.json").write_text(
            json.dumps(topology_data, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        (config_path / "placements.json").write_text(
            json.dumps(placements_definition, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        (config_path / "users.json").write_text(
            json.dumps(users_definition, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

        metadata = {
            "configuration_name": config_name,
            "base_scenario_path": str(base_path.resolve()),
            "scenario_path": str(config_path.resolve()),
            "cluster_count": len(topology_data.get("clusters", [])),
            "node_count": len(all_nodes),
            "services_path": str((config_path / "services.json").resolve()),
            "placements_path": str((config_path / "placements.json").resolve()),
            "users_path": str((config_path / "users.json").resolve()),
            "topology_path": str((config_path / "topology.json").resolve()),
        }
        (config_path / "configuration.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

        return metadata

    def create_simulation_from_configuration(
        self,
        *,
        configuration_path: str | Path,
        results_path: str | Path | None = None,
        seed: int | None = None,
        name: str | None = None,
        simulation_id: str | None = None,
    ) -> SimulationState:
        config_path = Path(configuration_path)
        if config_path.is_file():
            metadata_path = config_path
            config_dir = config_path.parent
        else:
            metadata_path = config_path / "configuration.json"
            config_dir = config_path

        if not metadata_path.exists():
            if self._looks_like_scenario_directory(config_dir):
                return self.create_simulation(
                    scenario_path=config_dir,
                    results_path=results_path,
                    seed=seed,
                    name=name,
                    simulation_id=simulation_id,
                )
            raise FileNotFoundError(
                f"Configuration metadata not found: {metadata_path}"
            )

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        return self.create_simulation(
            scenario_path=config_dir,
            results_path=results_path,
            seed=seed,
            name=name,
            simulation_id=simulation_id,
            services_definition_path=Path(metadata["services_path"]),
            users_definition_path=Path(metadata["users_path"]),
            placement_definition_path=Path(metadata["placements_path"]),
            topology_path=Path(metadata["topology_path"]),
        )

    def list_simulations(self) -> list[SimulationSummary]:
        return [managed.to_summary() for managed in self.registry.list()]

    def get_state(self, simulation_id: str) -> SimulationState:
        managed = self.registry.require(simulation_id)
        self._refresh_status(managed)
        snapshot = managed.simulation.get_state()
        return SimulationState(
            summary=managed.to_summary(),
            initialized=snapshot["initialized"],
            paused=snapshot["paused"],
            stop_requested=snapshot["stop_requested"],
            step=snapshot["step"],
            network_buffer=snapshot["network_buffer"],
            alloc_source_count=snapshot["alloc_source_count"],
            alloc_module_count=snapshot["alloc_module_count"],
        )

    def get_metrics_snapshot(self, simulation_id: str) -> SimulationMetricsSnapshot:
        managed = self.registry.require(simulation_id)
        snapshot = managed.simulation.get_metrics_snapshot()
        return SimulationMetricsSnapshot(
            simulation_id=simulation_id,
            entity_metrics=snapshot["entity_metrics"],
            unreachabled_links=snapshot["unreachabled_links"],
        )

    def get_application_metrics(
        self,
        simulation_id: str,
        *,
        from_time: float | None = None,
        to_time: float | None = None,
        reference_time: float | None = None,
        time_column: str = "end_time",
        response_strategy: str = "critical_path",
        include_return_messages: bool = True,
        egress_cost_per_gb: float | None = None,
    ) -> SimulationApplicationMetrics:
        """
        Return application-level metrics for a simulation within a time window.

        Parameters
        ----------
        from_time, to_time:
            Optional time bounds. When ``reference_time`` is ``None``, they are
            interpreted as absolute simulation times. Otherwise they are
            interpreted relative to ``reference_time``.
        reference_time:
            Optional numeric origin chosen by the caller. For example, if
            ``reference_time=4000`` and ``from_time=0``, analysis starts at the
            absolute simulation time ``4000``.
        time_column:
            Temporal coordinate used to decide whether a request belongs to the
            requested window. Supported values depend on the reconstructed
            service-response table and typically include ``"end_time"`` and
            ``"start_time"``.

        Notes
        -----
        The returned counters follow this semantics:

        - ``requests_total`` counts requests emitted by users in the analysed
          interval.
        - ``requests_successful`` counts the subset that completed
          successfully.
        - ``requests_unsuccessful`` counts the subset that did not complete
          successfully.
        """
        managed = self.registry.require(simulation_id)
        self._refresh_status(managed)
        absolute_from_time = (
            None if from_time is None else float(from_time) + float(reference_time or 0.0)
        )
        absolute_to_time = (
            None if to_time is None else float(to_time) + float(reference_time or 0.0)
        )
        raw_items = managed.simulation.get_application_metrics_summary(
            from_time=absolute_from_time,
            to_time=absolute_to_time,
            time_column=time_column,
            response_strategy=response_strategy,
            include_return_messages=include_return_messages,
            egress_cost_per_gb=egress_cost_per_gb,
        )
        return SimulationApplicationMetrics(
            simulation_id=simulation_id,
            items=[ApplicationMetricsSummary(**item) for item in raw_items],
            from_time=from_time,
            to_time=to_time,
            reference_time=reference_time,
            absolute_from_time=absolute_from_time,
            absolute_to_time=absolute_to_time,
        )

    def get_network_metrics(
        self,
        simulation_id: str,
        *,
        response_strategy: str = "critical_path",
        include_return_messages: bool = True,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._refresh_status(managed)
        return managed.simulation.get_network_metrics_summary(
            response_strategy=response_strategy,
            include_return_messages=include_return_messages,
        )

    def list_nodes(self, simulation_id: str) -> list[dict[str, object]]:
        managed = self.registry.require(simulation_id)
        return managed.simulation.list_nodes()

    def list_deployed_applications(self, simulation_id: str) -> list[object]:
        managed = self.registry.require(simulation_id)
        return managed.simulation.list_deployed_applications()

    def list_application_vnfs(
        self,
        simulation_id: str,
        app_id: str | int,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        return managed.simulation.list_application_vnfs(app_id)

    def list_node_placements(
        self,
        simulation_id: str,
        node_id: str,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        return managed.simulation.list_node_placements(node_id)

    def list_users(
        self,
        simulation_id: str,
        *,
        app_id: str | int | None = None,
        node_id: str | None = None,
        cluster_name: str | None = None,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        return managed.simulation.list_users(
            app_ref=app_id,
            node_id=node_id,
            cluster_name=cluster_name,
        )

    def list_processes(self, simulation_id: str) -> list[dict[str, object]]:
        managed = self.registry.require(simulation_id)
        return managed.simulation.list_processes()

    def create_process(
        self,
        simulation_id: str,
        definition: str | Path | dict[str, object],
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "Process registration requires the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )

        payload: str | Path | dict[str, object]
        if isinstance(definition, (str, Path)):
            path = Path(definition)
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            payload = definition

        return managed.simulation.register_process_definition(payload)

    def enable_process(
        self,
        simulation_id: str,
        process_name: str,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "Process mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )
        return managed.simulation.enable_process(process_name)

    def disable_process(
        self,
        simulation_id: str,
        process_name: str,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "Process mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )
        return managed.simulation.disable_process(process_name)

    def remove_process(
        self,
        simulation_id: str,
        process_name: str,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "Process mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )
        return managed.simulation.remove_process(process_name)

    def update_user_lambda(
        self,
        simulation_id: str,
        user_des: int,
        new_lambda: float,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "User mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )
        return managed.simulation.update_user_lambda(user_des, new_lambda)

    def update_application_users_lambda(
        self,
        simulation_id: str,
        app_id: str | int,
        new_lambda: float,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "User mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )
        return managed.simulation.update_application_users_lambda(app_id, new_lambda)

    def move_users_to_node(
        self,
        simulation_id: str,
        source_node_id: str,
        target_node_id: str,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "User mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )
        return managed.simulation.move_users_to_node(source_node_id, target_node_id)

    def remove_application_vnfs(
        self,
        simulation_id: str,
        app_id: str | int,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "Application mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )
        return managed.simulation.remove_application_vnfs(app_id)

    def remove_application_vnf(
        self,
        simulation_id: str,
        app_id: str | int,
        definition: str | Path | dict[str, object],
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "Application mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )

        payload: str | Path | dict[str, object]
        if isinstance(definition, (str, Path)):
            path = Path(definition)
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            payload = definition

        return managed.simulation.remove_application_vnf(app_id, payload)

    def list_clusters(self, simulation_id: str) -> list[dict[str, object]]:
        managed = self.registry.require(simulation_id)
        return managed.simulation.list_clusters()

    def list_nodes_in_cluster(
        self,
        simulation_id: str,
        cluster_name: str,
    ) -> list[dict[str, object]]:
        managed = self.registry.require(simulation_id)
        return managed.simulation.list_nodes_in_cluster(cluster_name)

    def count_nodes(self, simulation_id: str) -> int:
        managed = self.registry.require(simulation_id)
        return managed.simulation.count_nodes()

    def count_clusters(self, simulation_id: str) -> int:
        managed = self.registry.require(simulation_id)
        return managed.simulation.count_clusters()

    def create_cluster(
        self,
        simulation_id: str,
        definition: str | Path | dict[str, object],
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "Topology mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )

        payload: str | Path | dict[str, object]
        if isinstance(definition, (str, Path)):
            path = Path(definition)
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            payload = definition

        return managed.simulation.create_cluster(payload)

    def create_application(
        self,
        simulation_id: str,
        definition: str | Path | dict[str, object],
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "Application mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )

        payload: str | Path | dict[str, object]
        if isinstance(definition, (str, Path)):
            path = Path(definition)
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            payload = definition

        return managed.simulation.create_application(payload)

    def create_users(
        self,
        simulation_id: str,
        definition: str | Path | dict[str, object],
        *,
        nodes: str | list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "User mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )

        payload: str | Path | dict[str, object]
        if isinstance(definition, (str, Path)):
            path = Path(definition)
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            payload = definition

        return managed.simulation.create_users(payload, nodes=nodes)

    def remove_users_by_application(
        self,
        simulation_id: str,
        app_id: str | int,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "User mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )
        return managed.simulation.remove_users_by_application(app_id)

    def remove_users_by_node(
        self,
        simulation_id: str,
        node_id: str,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "User mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )
        return managed.simulation.remove_users_by_node(node_id)

    def remove_users_by_cluster(
        self,
        simulation_id: str,
        cluster_name: str,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "User mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )
        return managed.simulation.remove_users_by_cluster(cluster_name)

    def deploy_application_vnfs(
        self,
        simulation_id: str,
        app_id: str | int,
        definition: str | Path | dict[str, object],
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "Application mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )

        payload: str | Path | dict[str, object]
        if isinstance(definition, (str, Path)):
            path = Path(definition)
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            payload = definition

        return managed.simulation.deploy_application_vnfs(app_id, payload)

    def deploy_application_vnfs_generated(
        self,
        simulation_id: str,
        app_id: str | int,
        *,
        strategy: str = "spread",
        allowed_nodes: list[str] | None = None,
        include_control_plane: bool = True,
        seed: int | None = None,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "Application mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )

        return managed.simulation.deploy_application_vnfs_generated(
            app_id,
            strategy=strategy,
            allowed_nodes=allowed_nodes,
            include_control_plane=include_control_plane,
            seed=seed,
        )

    def move_application_vnf(
        self,
        simulation_id: str,
        app_id: str | int,
        definition: str | Path | dict[str, object],
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "Application mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )

        payload: str | Path | dict[str, object]
        if isinstance(definition, (str, Path)):
            path = Path(definition)
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            payload = definition

        return managed.simulation.move_application_vnf(app_id, payload)

    def replicate_application_vnf(
        self,
        simulation_id: str,
        app_id: str | int,
        definition: str | Path | dict[str, object],
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "Application mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )

        payload: str | Path | dict[str, object]
        if isinstance(definition, (str, Path)):
            path = Path(definition)
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            payload = definition

        return managed.simulation.replicate_application_vnf(app_id, payload)

    def create_nodes(
        self,
        simulation_id: str,
        definition: str | Path | dict[str, object],
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "Topology mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )

        payload: str | Path | dict[str, object]
        if isinstance(definition, (str, Path)):
            path = Path(definition)
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            payload = definition

        return managed.simulation.create_nodes(payload)

    def update_node(
        self,
        simulation_id: str,
        node_id: str,
        *,
        cpu: object | None = None,
        memory: object | None = None,
        ram: object | None = None,
        cost: float | None = None,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "Topology mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )

        payload: dict[str, object] = {"id": node_id}
        if cpu is not None:
            payload["cpu"] = cpu
        if memory is not None:
            payload["memory"] = memory
        if ram is not None:
            payload["ram"] = ram
        if cost is not None:
            payload["cost"] = cost

        return managed.simulation.update_node(payload)

    def remove_node(
        self,
        simulation_id: str,
        node_id: str,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "Topology mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )

        return managed.simulation.remove_node(node_id)

    def remove_cluster(
        self,
        simulation_id: str,
        cluster_name: str,
    ) -> dict[str, object]:
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._refresh_status(managed)
        if managed.simulation.is_running():
            raise RuntimeError(
                "Topology mutations require the simulation to be ready; "
                "wait until the scheduled window finishes or pause it first"
            )

        return managed.simulation.remove_cluster(cluster_name)

    def schedule_for(
        self,
        simulation_id: str,
        *,
        duration: float,
        step: float | None = None,
    ) -> SimulationState:
        """
        Schedule an incremental execution window.

        ``duration`` is relative to the current simulation time. For example,
        if ``now`` is ``200`` and ``duration`` is ``50``, the simulation is
        scheduled until ``250`` and then returns to the ``idle`` state.

        ``step`` controls the pause/fork responsiveness. Smaller steps give
        finer control at the cost of more scheduling overhead.
        """
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        try:
            managed.simulation.run_for(duration=duration, step=step)
        except Exception as exc:
            managed.status = SimulationStatus.FAILED
            managed.last_error = str(exc)
            raise
        self._refresh_status(managed)
        return self.get_state(simulation_id)

    def run_for(
        self,
        simulation_id: str,
        *,
        duration: float,
        step: float | None = None,
    ) -> SimulationState:
        """
        Backwards-compatible alias for :meth:`schedule_for`.
        """
        return self.schedule_for(simulation_id, duration=duration, step=step)

    def wait_until_ready(
        self,
        simulation_id: str,
        *,
        poll_interval: float = 1.0,
    ) -> SimulationState:
        """
        Block until the simulation is ready for the next command.

        The method returns when the scheduled execution window has finished
        (status ``idle``), the simulation is paused, or the simulation is
        stopped/failed.
        """
        while True:
            state = self.get_state(simulation_id)
            scheduled_until = state.summary.scheduled_until
            if state.summary.status in {
                SimulationStatus.STOPPED,
                SimulationStatus.FAILED,
            }:
                return state
            if (
                scheduled_until is not None
                and state.summary.now >= float(scheduled_until)
                and state.summary.status
                in {
                    SimulationStatus.IDLE,
                    SimulationStatus.PAUSED,
                    SimulationStatus.INITIALIZED,
                }
            ):
                return state
            time.sleep(poll_interval)

    def wait_until_idle(
        self,
        simulation_id: str,
        *,
        poll_interval: float = 1.0,
    ) -> SimulationState:
        """
        Backwards-compatible alias for :meth:`wait_until_ready`.
        """
        return self.wait_until_ready(simulation_id, poll_interval=poll_interval)

    def pause(self, simulation_id: str) -> SimulationState:
        """
        Request a pause and wait until the current execution step completes.
        """
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        managed.simulation.pause()
        managed.status = SimulationStatus.PAUSED
        return self.get_state(simulation_id)

    def resume(self, simulation_id: str) -> SimulationState:
        """
        Resume a paused or idle simulation without changing its schedule.
        """
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        managed.simulation.resume()
        self._refresh_status(managed)
        return self.get_state(simulation_id)

    def stop(self, simulation_id: str) -> SimulationState:
        """
        Stop the simulation permanently.
        """
        managed = self.registry.require(simulation_id)
        if managed.status == SimulationStatus.STOPPED:
            return self.get_state(simulation_id)
        managed.simulation.stop()
        managed.status = SimulationStatus.STOPPED
        return self.get_state(simulation_id)

    def destroy(self, simulation_id: str) -> SimulationSummary:
        managed = self.registry.require(simulation_id)
        if managed.status not in {
            SimulationStatus.STOPPED,
            SimulationStatus.IDLE,
            SimulationStatus.FAILED,
        }:
            managed.simulation.stop()
            managed.status = SimulationStatus.STOPPED
        removed = self.registry.remove(simulation_id)
        if removed is None:
            raise KeyError(f"Unknown simulation id: {simulation_id}")
        return removed.to_summary()

    def fork(
        self,
        simulation_id: str,
        *,
        child_name: str | None = None,
        child_id: str | None = None,
        results_suffix: str | None = None,
        poll_interval: float = 0.01,
    ) -> SimulationState:
        """
        Fork a simulation once it is paused or no longer actively running.

        If a scheduled window is still executing, the method actively waits
        until the parent becomes safe to clone.
        """
        managed = self.registry.require(simulation_id)
        self._ensure_actionable(managed)
        self._wait_until_forkable(managed, poll_interval=poll_interval)
        if child_id is None:
            child_id = self._new_id()
        if child_name is None:
            child_name = f"{managed.name}-fork"
        if results_suffix is None:
            results_suffix = child_id

        child_simulation = managed.simulation.fork(results_suffix=results_suffix)
        child = ManagedSimulation(
            id=child_id,
            name=child_name,
            scenario_path=managed.scenario_path,
            simulation=child_simulation,
            seed=managed.seed,
            parent_id=managed.id,
            status=SimulationStatus.PAUSED,
        )
        self.registry.add(child)
        self._refresh_status(managed)
        return self.get_state(child_id)

    def clone(self, simulation_id: str, **kwargs: object) -> SimulationState:
        return self.fork(simulation_id, **kwargs)

    def _ensure_actionable(self, managed: ManagedSimulation) -> None:
        if managed.status in {
            SimulationStatus.STOPPED,
            SimulationStatus.FAILED,
        }:
            raise RuntimeError(
                f"Simulation {managed.id} is not actionable from state {managed.status}"
            )

    def _wait_until_forkable(
        self,
        managed: ManagedSimulation,
        *,
        poll_interval: float,
    ) -> None:
        while True:
            self._refresh_status(managed)
            if managed.status in {
                SimulationStatus.STOPPED,
                SimulationStatus.FAILED,
            }:
                self._ensure_actionable(managed)

            snapshot = managed.simulation.get_state()
            if snapshot["paused"] or not managed.simulation.is_running():
                return

            time.sleep(poll_interval)

    def _refresh_status(self, managed: ManagedSimulation) -> None:
        snapshot = managed.simulation.get_state()
        now = snapshot["now"]
        scheduled_until = snapshot["scheduled_until"]

        if managed.status == SimulationStatus.FAILED:
            return
        if snapshot["stop_requested"]:
            managed.status = SimulationStatus.STOPPED
            return
        if snapshot["initialized"] and scheduled_until is not None and now >= float(
            scheduled_until
        ):
            managed.status = SimulationStatus.IDLE
            return
        if snapshot["paused"] and snapshot["initialized"]:
            managed.status = SimulationStatus.PAUSED
            return
        if managed.simulation.is_running():
            managed.status = SimulationStatus.RUNNING
            return
        if snapshot["initialized"]:
            managed.status = SimulationStatus.INITIALIZED
            return
        managed.status = SimulationStatus.CREATED

    def _new_id(self) -> str:
        return f"sim-{uuid.uuid4().hex[:8]}"
