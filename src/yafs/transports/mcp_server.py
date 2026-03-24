from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from ..services import SimulationService


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


def build_mcp_server(service: SimulationService, *, server_name: str = "yafs-sim"):
    """
    Build an optional MCP transport around the service layer.

    The dependency is imported lazily so the service layer can evolve without
    forcing an MCP runtime on all users of the library.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "MCP transport requires the optional dependency 'mcp'. "
            "Install it to expose SimulationService over MCP."
        ) from exc

    app = FastMCP(server_name)

    @app.tool()
    def create_simulation(
        scenario_path: str,
        results_path: str | None = None,
        seed: int | None = None,
        name: str | None = None,
        services_definition_path: str | None = None,
        users_definition_path: str | None = None,
        placement_definition_path: str | None = None,
        topology_path: str | None = None,
    ) -> dict[str, Any]:
        return _serialize(
            service.create_simulation(
                scenario_path=scenario_path,
                results_path=results_path,
                seed=seed,
                name=name,
                services_definition_path=services_definition_path,
                users_definition_path=users_definition_path,
                placement_definition_path=placement_definition_path,
                topology_path=topology_path,
            )
        )

    @app.tool()
    def create_simulation_configuration(
        base_scenario_path: str,
        configuration_name: str,
        topology_definition_path: str | None = None,
        cluster_count: int | None = None,
        nodes_per_cluster: int | None = None,
        output_root: str | None = None,
    ) -> dict[str, Any]:
        return _serialize(
            service.create_simulation_configuration(
                base_scenario_path=base_scenario_path,
                configuration_name=configuration_name,
                topology_definition_path=topology_definition_path,
                cluster_count=cluster_count,
                nodes_per_cluster=nodes_per_cluster,
                output_root=output_root,
            )
        )

    @app.tool()
    def create_simulation_from_configuration(
        configuration_path: str,
        results_path: str | None = None,
        seed: int | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        return _serialize(
            service.create_simulation_from_configuration(
                configuration_path=configuration_path,
                results_path=results_path,
                seed=seed,
                name=name,
            )
        )

    @app.tool()
    def list_simulations() -> list[dict[str, Any]]:
        return _serialize(service.list_simulations())

    @app.tool()
    def get_simulation_state(simulation_id: str) -> dict[str, Any]:
        return _serialize(service.get_state(simulation_id))

    @app.tool()
    def get_simulation_application_metrics(
        simulation_id: str,
        from_time: float | None = None,
        to_time: float | None = None,
        reference_time: float | None = None,
        time_column: str = "end_time",
        response_strategy: str = "critical_path",
        include_return_messages: bool = True,
        egress_cost_per_gb: float | None = None,
    ) -> dict[str, Any]:
        return _serialize(
            service.get_application_metrics(
                simulation_id,
                from_time=from_time,
                to_time=to_time,
                reference_time=reference_time,
                time_column=time_column,
                response_strategy=response_strategy,
                include_return_messages=include_return_messages,
                egress_cost_per_gb=egress_cost_per_gb,
            )
        )

    @app.tool()
    def get_simulation_network_metrics(
        simulation_id: str,
        response_strategy: str = "critical_path",
        include_return_messages: bool = True,
    ) -> dict[str, Any]:
        return _serialize(
            service.get_network_metrics(
                simulation_id,
                response_strategy=response_strategy,
                include_return_messages=include_return_messages,
            )
        )

    @app.tool()
    def list_simulation_nodes(simulation_id: str) -> list[dict[str, Any]]:
        return _serialize(service.list_nodes(simulation_id))

    @app.tool()
    def list_simulation_clusters(simulation_id: str) -> list[dict[str, Any]]:
        return _serialize(service.list_clusters(simulation_id))

    @app.tool()
    def list_simulation_nodes_in_cluster(
        simulation_id: str,
        cluster_name: str,
    ) -> list[dict[str, Any]]:
        return _serialize(service.list_nodes_in_cluster(simulation_id, cluster_name))

    @app.tool()
    def count_simulation_nodes(simulation_id: str) -> int:
        return _serialize(service.count_nodes(simulation_id))

    @app.tool()
    def count_simulation_clusters(simulation_id: str) -> int:
        return _serialize(service.count_clusters(simulation_id))

    @app.tool()
    def create_simulation_application(
        simulation_id: str,
        definition_path: str,
    ) -> dict[str, Any]:
        return _serialize(service.create_application(simulation_id, definition_path))

    @app.tool()
    def create_simulation_users(
        simulation_id: str,
        definition_path: str,
        nodes: list[str] | None = None,
    ) -> dict[str, Any]:
        return _serialize(
            service.create_users(simulation_id, definition_path, nodes=nodes)
        )

    @app.tool()
    def remove_simulation_users_by_application(
        simulation_id: str,
        app_id: str,
    ) -> dict[str, Any]:
        return _serialize(service.remove_users_by_application(simulation_id, app_id))

    @app.tool()
    def remove_simulation_users_by_node(
        simulation_id: str,
        node_id: str,
    ) -> dict[str, Any]:
        return _serialize(service.remove_users_by_node(simulation_id, node_id))

    @app.tool()
    def remove_simulation_users_by_cluster(
        simulation_id: str,
        cluster_name: str,
    ) -> dict[str, Any]:
        return _serialize(service.remove_users_by_cluster(simulation_id, cluster_name))

    @app.tool()
    def update_simulation_user_lambda(
        simulation_id: str,
        user_des: int,
        new_lambda: float,
    ) -> dict[str, Any]:
        return _serialize(service.update_user_lambda(simulation_id, user_des, new_lambda))

    @app.tool()
    def update_simulation_application_users_lambda(
        simulation_id: str,
        app_id: str,
        new_lambda: float,
    ) -> dict[str, Any]:
        return _serialize(
            service.update_application_users_lambda(simulation_id, app_id, new_lambda)
        )

    @app.tool()
    def move_simulation_users_to_node(
        simulation_id: str,
        source_node_id: str,
        target_node_id: str,
    ) -> dict[str, Any]:
        return _serialize(
            service.move_users_to_node(
                simulation_id,
                source_node_id,
                target_node_id,
            )
        )

    @app.tool()
    def list_simulation_deployed_applications(
        simulation_id: str,
    ) -> list[Any]:
        return _serialize(service.list_deployed_applications(simulation_id))

    @app.tool()
    def list_simulation_application_vnfs(
        simulation_id: str,
        app_id: str,
    ) -> dict[str, Any]:
        return _serialize(service.list_application_vnfs(simulation_id, app_id))

    @app.tool()
    def list_simulation_node_placements(
        simulation_id: str,
        node_id: str,
    ) -> dict[str, Any]:
        return _serialize(service.list_node_placements(simulation_id, node_id))

    @app.tool()
    def list_simulation_users(
        simulation_id: str,
        app_id: str | None = None,
        node_id: str | None = None,
        cluster_name: str | None = None,
    ) -> dict[str, Any]:
        return _serialize(
            service.list_users(
                simulation_id,
                app_id=app_id,
                node_id=node_id,
                cluster_name=cluster_name,
            )
        )

    @app.tool()
    def list_simulation_processes(
        simulation_id: str,
    ) -> list[dict[str, Any]]:
        return _serialize(service.list_processes(simulation_id))

    @app.tool()
    def create_simulation_process(
        simulation_id: str,
        definition_path: str,
    ) -> dict[str, Any]:
        return _serialize(service.create_process(simulation_id, definition_path))

    @app.tool()
    def enable_simulation_process(
        simulation_id: str,
        process_name: str,
    ) -> dict[str, Any]:
        return _serialize(service.enable_process(simulation_id, process_name))

    @app.tool()
    def disable_simulation_process(
        simulation_id: str,
        process_name: str,
    ) -> dict[str, Any]:
        return _serialize(service.disable_process(simulation_id, process_name))

    @app.tool()
    def remove_simulation_process(
        simulation_id: str,
        process_name: str,
    ) -> dict[str, Any]:
        return _serialize(service.remove_process(simulation_id, process_name))

    @app.tool()
    def remove_simulation_application_vnfs(
        simulation_id: str,
        app_id: str,
    ) -> dict[str, Any]:
        return _serialize(service.remove_application_vnfs(simulation_id, app_id))

    @app.tool()
    def remove_simulation_application_vnf(
        simulation_id: str,
        app_id: str,
        definition_path: str,
    ) -> dict[str, Any]:
        return _serialize(
            service.remove_application_vnf(simulation_id, app_id, definition_path)
        )

    @app.tool()
    def deploy_simulation_application_vnfs(
        simulation_id: str,
        app_id: str,
        definition_path: str,
    ) -> dict[str, Any]:
        return _serialize(
            service.deploy_application_vnfs(simulation_id, app_id, definition_path)
        )

    @app.tool()
    def deploy_simulation_application_vnfs_generated(
        simulation_id: str,
        app_id: str,
        strategy: str = "spread",
        allowed_nodes: list[str] | None = None,
        include_control_plane: bool = True,
        seed: int | None = None,
    ) -> dict[str, Any]:
        return _serialize(
            service.deploy_application_vnfs_generated(
                simulation_id,
                app_id,
                strategy=strategy,
                allowed_nodes=allowed_nodes,
                include_control_plane=include_control_plane,
                seed=seed,
            )
        )

    @app.tool()
    def move_simulation_application_vnf(
        simulation_id: str,
        app_id: str,
        definition_path: str,
    ) -> dict[str, Any]:
        return _serialize(
            service.move_application_vnf(simulation_id, app_id, definition_path)
        )

    @app.tool()
    def replicate_simulation_application_vnf(
        simulation_id: str,
        app_id: str,
        definition_path: str,
    ) -> dict[str, Any]:
        return _serialize(
            service.replicate_application_vnf(simulation_id, app_id, definition_path)
        )

    @app.tool()
    def create_simulation_cluster(
        simulation_id: str,
        definition_path: str,
    ) -> dict[str, Any]:
        return _serialize(service.create_cluster(simulation_id, definition_path))

    @app.tool()
    def create_simulation_nodes(
        simulation_id: str,
        definition_path: str,
    ) -> dict[str, Any]:
        return _serialize(service.create_nodes(simulation_id, definition_path))

    @app.tool()
    def update_simulation_node(
        simulation_id: str,
        node_id: str,
        cpu: float | None = None,
        memory: str | None = None,
        ram: str | None = None,
        cost: float | None = None,
    ) -> dict[str, Any]:
        return _serialize(
            service.update_node(
                simulation_id,
                node_id,
                cpu=cpu,
                memory=memory,
                ram=ram,
                cost=cost,
            )
        )

    @app.tool()
    def remove_simulation_node(
        simulation_id: str,
        node_id: str,
    ) -> dict[str, Any]:
        return _serialize(service.remove_node(simulation_id, node_id))

    @app.tool()
    def remove_simulation_cluster(
        simulation_id: str,
        cluster_name: str,
    ) -> dict[str, Any]:
        return _serialize(service.remove_cluster(simulation_id, cluster_name))

    @app.tool()
    def run_simulation_for(
        simulation_id: str,
        duration: float,
        step: float | None = None,
    ) -> dict[str, Any]:
        return _serialize(
            service.schedule_for(simulation_id, duration=duration, step=step)
        )

    @app.tool()
    def schedule_simulation_for(
        simulation_id: str,
        duration: float,
        step: float | None = None,
    ) -> dict[str, Any]:
        return _serialize(
            service.schedule_for(simulation_id, duration=duration, step=step)
        )

    @app.tool()
    def pause_simulation(simulation_id: str) -> dict[str, Any]:
        return _serialize(service.pause(simulation_id))

    @app.tool()
    def resume_simulation(simulation_id: str) -> dict[str, Any]:
        return _serialize(service.resume(simulation_id))

    @app.tool()
    def fork_simulation(
        simulation_id: str,
        child_name: str | None = None,
        child_id: str | None = None,
    ) -> dict[str, Any]:
        return _serialize(
            service.fork(
                simulation_id,
                child_name=child_name,
                child_id=child_id,
            )
        )

    @app.tool()
    def wait_simulation_until_ready(
        simulation_id: str,
        poll_interval: float = 1.0,
    ) -> dict[str, Any]:
        return _serialize(
            service.wait_until_ready(
                simulation_id,
                poll_interval=poll_interval,
            )
        )

    @app.tool()
    def stop_simulation(simulation_id: str) -> dict[str, Any]:
        return _serialize(service.stop(simulation_id))

    @app.tool()
    def destroy_simulation(simulation_id: str) -> dict[str, Any]:
        return _serialize(service.destroy(simulation_id))

    @app.resource("simulation://{simulation_id}/state")
    def simulation_state_resource(simulation_id: str) -> dict[str, Any]:
        return _serialize(service.get_state(simulation_id))

    @app.resource("simulation://{simulation_id}/metrics")
    def simulation_metrics_resource(simulation_id: str) -> dict[str, Any]:
        return _serialize(service.get_metrics_snapshot(simulation_id))

    return app
