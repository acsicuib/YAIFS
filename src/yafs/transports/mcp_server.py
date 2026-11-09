from __future__ import annotations

from collections.abc import Collection
from dataclasses import asdict, is_dataclass
from enum import StrEnum
from typing import Any

from ..services import SimulationService


class McpProfile(StrEnum):
    """Tool catalog offered by one MCP server process."""

    EXPERIMENT_DESIGNER = "experiment_designer"
    SIMULATION_CONTROLLER = "simulation_controller"
    PLACEMENT = "placement"
    EXPERIMENT_ANALYST = "experiment_analyst"


_PROFILE_INSTRUCTIONS = {
    McpProfile.EXPERIMENT_DESIGNER: (
        "Experiment Designer: create scenarios, configurations, and simulations."
    ),
    McpProfile.SIMULATION_CONTROLLER: (
        "Simulation Controller: advance, pause, observe, and modify a running simulation."
    ),
    McpProfile.PLACEMENT: (
        "Placement: inspect inventory, deploy and move VNFs, advance and "
        "pause the simulation, and query application and network metrics."
    ),
    McpProfile.EXPERIMENT_ANALYST: (
        "Experiment Analyst: query metrics and compare simulation results."
    ),
}

# Read-only inventory shared by every profile.
_INVENTORY_TOOLS = frozenset(
    {
        "list_simulations",
        "get_simulation_state",
        "list_simulation_nodes",
        "list_simulation_clusters",
        "list_simulation_nodes_in_cluster",
        "count_simulation_nodes",
        "count_simulation_clusters",
        "list_simulation_deployed_applications",
        "list_simulation_application_vnfs",
        "list_simulation_node_placements",
        "list_simulation_users",
        "list_simulation_processes",
    }
)

_DESIGNER_TOOLS = frozenset(
    {
        "create_simulation",
        "create_simulation_configuration",
        "create_simulation_from_configuration",
        "create_simulation_application",
        "create_simulation_users",
        "create_simulation_process",
        "create_simulation_cluster",
        "create_simulation_nodes",
        "destroy_simulation",
        "update_simulation_user_lambda",
        "update_simulation_application_users_lambda",
        "move_simulation_users_to_node",
        "remove_simulation_users_by_application",
        "remove_simulation_users_by_node",
        "remove_simulation_users_by_cluster",
    }
)

_PLACEMENT_TOOLS = frozenset(
    {
        "deploy_simulation_application_vnfs",
        "deploy_simulation_application_vnfs_generated",
        "move_simulation_application_vnf",
        "replicate_simulation_application_vnf",
        "remove_simulation_application_vnfs",
        "remove_simulation_application_vnf",
    }
)

_CONTROLLER_TOOLS = frozenset(
    {
        "enable_simulation_process",
        "disable_simulation_process",
        "remove_simulation_process",
        "update_simulation_node",
        "remove_simulation_node",
        "remove_simulation_cluster",
        "run_simulation_for",
        "pause_simulation",
        "resume_simulation",
        "fork_simulation",
        "wait_simulation_until_ready",
        "stop_simulation",
    }
)

_ANALYST_TOOLS = frozenset(
    {
        "get_simulation_application_metrics",
        "get_simulation_network_metrics",
        "get_topology",
        "get_deployments",
        "get_request_paths",
        "get_latency_breakdown",
    }
)

_PROFILE_TOOLS = {
    McpProfile.EXPERIMENT_DESIGNER: _INVENTORY_TOOLS | _DESIGNER_TOOLS,
    McpProfile.SIMULATION_CONTROLLER: _INVENTORY_TOOLS | _CONTROLLER_TOOLS,
    McpProfile.PLACEMENT: _INVENTORY_TOOLS | _PLACEMENT_TOOLS | _CONTROLLER_TOOLS | _ANALYST_TOOLS,
    McpProfile.EXPERIMENT_ANALYST: _INVENTORY_TOOLS | _ANALYST_TOOLS,
}

_CLASSIFIED_TOOLS = (
    _INVENTORY_TOOLS
    | _DESIGNER_TOOLS
    | _CONTROLLER_TOOLS
    | _PLACEMENT_TOOLS
    | _ANALYST_TOOLS
)

_TOOL_GROUPS = (
    ("inventory", _INVENTORY_TOOLS),
    ("placement", _PLACEMENT_TOOLS),
    ("controller", _CONTROLLER_TOOLS),
    ("analyst", _ANALYST_TOOLS),
    ("designer", _DESIGNER_TOOLS),
)


def mcp_tool_group(name: str) -> str | None:
    """Return the catalog group that defines one MCP tool.

    The placement profile is the union of inventory, placement, controller,
    and analyst. Designer-only tools are reported separately.
    """
    for group, tools in _TOOL_GROUPS:
        if name in tools:
            return group
    return None


def resolve_mcp_profiles(
    profiles: Collection[str] | None,
) -> frozenset[McpProfile] | None:
    """Return the selected profiles.

    ``None`` means the full catalog. A single profile name is accepted as a string.
    """
    if profiles is None:
        return None
    if isinstance(profiles, str):
        profiles = [profiles]
    if len(profiles) == 0:
        raise ValueError(
            "Select at least one MCP profile, or omit profiles to expose the full catalog."
        )

    selected: list[McpProfile] = []
    unknown: list[str] = []
    for item in profiles:
        try:
            selected.append(McpProfile(str(item)))
        except ValueError:
            unknown.append(str(item))
    if unknown:
        valid = ", ".join(profile.value for profile in McpProfile)
        names = ", ".join(repr(name) for name in unknown)
        raise ValueError(f"Unknown MCP profile {names}. Valid profiles: {valid}.")
    return frozenset(selected)


def profile_enabled(
    profiles: Collection[str] | None,
    profile: McpProfile | str,
) -> bool:
    """Return whether ``profile`` is active. An omitted catalog enables every profile."""
    selected = resolve_mcp_profiles(profiles)
    if selected is None:
        return True
    return McpProfile(profile) in selected


def _tool_names_for(profiles: Collection[str] | None) -> frozenset[str] | None:
    selected = resolve_mcp_profiles(profiles)
    if selected is None:
        return None
    names: set[str] = set()
    for profile in selected:
        names.update(_PROFILE_TOOLS[profile])
    return frozenset(names)


def _server_instructions(profiles: Collection[str] | None) -> str | None:
    selected = resolve_mcp_profiles(profiles)
    if selected is None:
        return None
    lines = ["This server exposes YAFS tools for the selected profiles."]
    for profile in McpProfile:
        if profile in selected:
            lines.append(_PROFILE_INSTRUCTIONS[profile])
    return " ".join(lines)


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


def build_mcp_server(
    service: SimulationService,
    *,
    server_name: str = "yafs-sim",
    profiles: Collection[str] | None = None,
):
    """
    Build an optional MCP transport around the service layer.

    ``profiles`` selects one or more catalogs. Omit it to expose every tool.
    Several profiles expose the union of their tools. The dependency is imported
    lazily so the service layer can evolve without forcing an MCP runtime on
    all users of the library.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "MCP transport requires the optional dependency 'mcp'. "
            "Install it to expose SimulationService over MCP."
        ) from exc

    app = FastMCP(server_name, instructions=_server_instructions(profiles))
    allowed_tools = _tool_names_for(profiles)
    analyst_enabled = profile_enabled(profiles, McpProfile.EXPERIMENT_ANALYST)

    def tool(fn=None):
        def decorate(func):
            name = func.__name__
            if name not in _CLASSIFIED_TOOLS:
                raise RuntimeError(f"Tool {name} is not assigned to an MCP profile.")
            if allowed_tools is None or name in allowed_tools:
                return app.tool()(func)
            return func

        if fn is not None:
            return decorate(fn)
        return decorate

    def resource(uri: str):
        def decorate(func):
            if analyst_enabled:
                return app.resource(uri)(func)
            return func

        return decorate

    @tool()
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
        """Create a new simulation instance from a scenario.

        Returns the simulation ID.
        """
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

    @tool()
    def create_simulation_configuration(
        base_scenario_path: str,
        configuration_name: str,
        topology_definition_path: str | None = None,
        cluster_count: int | None = None,
        nodes_per_cluster: int | None = None,
        output_root: str | None = None,
    ) -> dict[str, Any]:
        """Generate a self-contained scenario configuration from a base scenario."""
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

    @tool()
    def create_simulation_from_configuration(
        configuration_path: str,
        results_path: str | None = None,
        seed: int | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Create a simulation from a generated configuration directory."""
        return _serialize(
            service.create_simulation_from_configuration(
                configuration_path=configuration_path,
                results_path=results_path,
                seed=seed,
                name=name,
            )
        )

    @tool()
    def list_simulations() -> list[dict[str, Any]]:
        """List the simulations currently registered on this server."""
        return _serialize(service.list_simulations())

    @tool()
    def get_simulation_state(simulation_id: str) -> dict[str, Any]:
        """Return the status, clock, and summary of one simulation."""
        return _serialize(service.get_state(simulation_id))

    @tool()
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
        """Return application latency and cost metrics for a time window.

        The result keeps one detailed item per application and also includes
        by_app latency, node and link utilization, and the user count.
        """
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

    @tool()
    def get_simulation_network_metrics(
        simulation_id: str,
        response_strategy: str = "critical_path",
        include_return_messages: bool = True,
    ) -> dict[str, Any]:
        """Return network metrics for one simulation."""
        return _serialize(
            service.get_network_metrics(
                simulation_id,
                response_strategy=response_strategy,
                include_return_messages=include_return_messages,
            )
        )

    @tool()
    def get_topology(
        simulation_id: str,
        cluster_id: str | None = None,
        node_id: str | None = None,
        include_resources: bool = True,
    ) -> dict[str, Any]:
        """Read physical clusters, nodes, and network links with their attributes.

        node_id returns that node, its neighbors, and the links that touch it.
        cluster_id returns the cluster plus links with an end in the cluster.
        This tool does not recommend a placement or change state.
        """
        return _serialize(
            service.get_topology(
                simulation_id,
                cluster_id=cluster_id,
                node_id=node_id,
                include_resources=include_resources,
            )
        )

    @tool()
    def get_deployments(
        simulation_id: str,
        application_id: str | None = None,
        service_id: str | None = None,
    ) -> dict[str, Any]:
        """Read current application and VNF replica placement and host nodes.

        A service with no replica is reported as undeployed. This tool does
        not deploy, migrate, or modify services.
        """
        return _serialize(
            service.get_deployments(
                simulation_id,
                application_id=application_id,
                service_id=service_id,
            )
        )

    @tool()
    def get_request_paths(
        simulation_id: str,
        application_id: str,
        start_time: float | None = None,
        end_time: float | None = None,
        user_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Read observed request routes from users through selected VNF replicas.

        Paths are grouped from trace rows that share a request id. Link hops
        are recorded transmissions, not a computed shortest path. limit bounds
        the number of groups and the response reports truncation.
        """
        return _serialize(
            service.get_request_paths(
                simulation_id,
                application_id,
                start_time=start_time,
                end_time=end_time,
                user_id=user_id,
                limit=limit,
            )
        )

    @tool()
    def get_latency_breakdown(
        simulation_id: str,
        application_id: str,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> dict[str, Any]:
        """Read observed end-to-end latency and the measured latency components.

        Components are reported only where the trace records them. They are
        not forced to sum to the end-to-end wall clock.
        """
        return _serialize(
            service.get_latency_breakdown(
                simulation_id,
                application_id,
                start_time=start_time,
                end_time=end_time,
            )
        )

    @tool()
    def list_simulation_nodes(simulation_id: str) -> list[dict[str, Any]]:
        """List the nodes in a simulation."""
        return _serialize(service.list_nodes(simulation_id))

    @tool()
    def list_simulation_clusters(simulation_id: str) -> list[dict[str, Any]]:
        """List the clusters in a simulation."""
        return _serialize(service.list_clusters(simulation_id))

    @tool()
    def list_simulation_nodes_in_cluster(
        simulation_id: str,
        cluster_name: str,
    ) -> list[dict[str, Any]]:
        """List the nodes that belong to one cluster."""
        return _serialize(service.list_nodes_in_cluster(simulation_id, cluster_name))

    @tool()
    def count_simulation_nodes(simulation_id: str) -> int:
        """Return the number of nodes in a simulation."""
        return _serialize(service.count_nodes(simulation_id))

    @tool()
    def count_simulation_clusters(simulation_id: str) -> int:
        """Return the number of clusters in a simulation."""
        return _serialize(service.count_clusters(simulation_id))

    @tool()
    def create_simulation_application(
        simulation_id: str,
        definition_path: str,
    ) -> dict[str, Any]:
        """Add an application from a JSON definition file."""
        return _serialize(service.create_application(simulation_id, definition_path))

    @tool()
    def create_simulation_users(
        simulation_id: str,
        definition_path: str,
        nodes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create users from a JSON definition file."""
        return _serialize(
            service.create_users(simulation_id, definition_path, nodes=nodes)
        )

    @tool()
    def remove_simulation_users_by_application(
        simulation_id: str,
        app_id: str,
    ) -> dict[str, Any]:
        """Remove the users of one application."""
        return _serialize(service.remove_users_by_application(simulation_id, app_id))

    @tool()
    def remove_simulation_users_by_node(
        simulation_id: str,
        node_id: str,
    ) -> dict[str, Any]:
        """Remove the users placed on one node."""
        return _serialize(service.remove_users_by_node(simulation_id, node_id))

    @tool()
    def remove_simulation_users_by_cluster(
        simulation_id: str,
        cluster_name: str,
    ) -> dict[str, Any]:
        """Remove the users placed in one cluster."""
        return _serialize(service.remove_users_by_cluster(simulation_id, cluster_name))

    @tool()
    def update_simulation_user_lambda(
        simulation_id: str,
        user_des: int,
        new_lambda: float,
    ) -> dict[str, Any]:
        """Change the arrival rate of one user."""
        return _serialize(service.update_user_lambda(simulation_id, user_des, new_lambda))

    @tool()
    def update_simulation_application_users_lambda(
        simulation_id: str,
        app_id: str,
        new_lambda: float,
    ) -> dict[str, Any]:
        """Change the arrival rate of every user of one application."""
        return _serialize(
            service.update_application_users_lambda(simulation_id, app_id, new_lambda)
        )

    @tool()
    def move_simulation_users_to_node(
        simulation_id: str,
        source_node_id: str,
        target_node_id: str,
    ) -> dict[str, Any]:
        """Move users from one node to another."""
        return _serialize(
            service.move_users_to_node(
                simulation_id,
                source_node_id,
                target_node_id,
            )
        )

    @tool()
    def list_simulation_deployed_applications(
        simulation_id: str,
    ) -> list[Any]:
        """List applications that currently have deployed VNFs."""
        return _serialize(service.list_deployed_applications(simulation_id))

    @tool()
    def list_simulation_application_vnfs(
        simulation_id: str,
        app_id: str,
    ) -> dict[str, Any]:
        """List the VNFs of one application and the nodes where they run."""
        return _serialize(service.list_application_vnfs(simulation_id, app_id))

    @tool()
    def list_simulation_node_placements(
        simulation_id: str,
        node_id: str,
    ) -> dict[str, Any]:
        """List the VNFs placed on one node."""
        return _serialize(service.list_node_placements(simulation_id, node_id))

    @tool()
    def list_simulation_users(
        simulation_id: str,
        app_id: str | None = None,
        node_id: str | None = None,
        cluster_name: str | None = None,
    ) -> dict[str, Any]:
        """List users, optionally filtered by application, node, or cluster."""
        return _serialize(
            service.list_users(
                simulation_id,
                app_id=app_id,
                node_id=node_id,
                cluster_name=cluster_name,
            )
        )

    @tool()
    def list_simulation_processes(
        simulation_id: str,
    ) -> list[dict[str, Any]]:
        """List the processes registered in a simulation."""
        return _serialize(service.list_processes(simulation_id))

    @tool()
    def create_simulation_process(
        simulation_id: str,
        definition_path: str,
    ) -> dict[str, Any]:
        """Register a custom process from a JSON definition file."""
        return _serialize(service.create_process(simulation_id, definition_path))

    @tool()
    def enable_simulation_process(
        simulation_id: str,
        process_name: str,
    ) -> dict[str, Any]:
        """Enable a registered custom process."""
        return _serialize(service.enable_process(simulation_id, process_name))

    @tool()
    def disable_simulation_process(
        simulation_id: str,
        process_name: str,
    ) -> dict[str, Any]:
        """Disable a registered custom process without removing it."""
        return _serialize(service.disable_process(simulation_id, process_name))

    @tool()
    def remove_simulation_process(
        simulation_id: str,
        process_name: str,
    ) -> dict[str, Any]:
        """Remove a registered custom process."""
        return _serialize(service.remove_process(simulation_id, process_name))

    @tool()
    def remove_simulation_application_vnfs(
        simulation_id: str,
        app_id: str,
    ) -> dict[str, Any]:
        """Remove every VNF of one application."""
        return _serialize(service.remove_application_vnfs(simulation_id, app_id))

    @tool()
    def remove_simulation_application_vnf(
        simulation_id: str,
        app_id: str,
        definition_path: str,
    ) -> dict[str, Any]:
        """Remove one VNF using a JSON definition file."""
        return _serialize(
            service.remove_application_vnf(simulation_id, app_id, definition_path)
        )

    @tool()
    def deploy_simulation_application_vnfs(
        simulation_id: str,
        app_id: str,
        definition_path: str,
    ) -> dict[str, Any]:
        """Deploy the VNFs of one application from a JSON definition file."""
        return _serialize(
            service.deploy_application_vnfs(simulation_id, app_id, definition_path)
        )

    @tool()
    def deploy_simulation_application_vnfs_generated(
        simulation_id: str,
        app_id: str,
        strategy: str = "spread",
        allowed_nodes: list[str] | None = None,
        include_control_plane: bool = True,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """Deploy VNFs of one application using a generated placement."""
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

    @tool()
    def move_simulation_application_vnf(
        simulation_id: str,
        app_id: str,
        definition_path: str,
    ) -> dict[str, Any]:
        """Move one VNF using a JSON definition file."""
        return _serialize(
            service.move_application_vnf(simulation_id, app_id, definition_path)
        )

    @tool()
    def replicate_simulation_application_vnf(
        simulation_id: str,
        app_id: str,
        definition_path: str,
    ) -> dict[str, Any]:
        """Replicate one VNF onto another node using a JSON definition file."""
        return _serialize(
            service.replicate_application_vnf(simulation_id, app_id, definition_path)
        )

    @tool()
    def create_simulation_cluster(
        simulation_id: str,
        definition_path: str,
    ) -> dict[str, Any]:
        """Add a cluster from a JSON definition file."""
        return _serialize(service.create_cluster(simulation_id, definition_path))

    @tool()
    def create_simulation_nodes(
        simulation_id: str,
        definition_path: str,
    ) -> dict[str, Any]:
        """Add nodes from a JSON definition file."""
        return _serialize(service.create_nodes(simulation_id, definition_path))

    @tool()
    def update_simulation_node(
        simulation_id: str,
        node_id: str,
        cpu: float | None = None,
        memory: str | None = None,
        ram: str | None = None,
        cost: float | None = None,
    ) -> dict[str, Any]:
        """Update the CPU, memory, RAM, or cost of one node."""
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

    @tool()
    def remove_simulation_node(
        simulation_id: str,
        node_id: str,
    ) -> dict[str, Any]:
        """Remove one node from the topology."""
        return _serialize(service.remove_node(simulation_id, node_id))

    @tool()
    def remove_simulation_cluster(
        simulation_id: str,
        cluster_name: str,
    ) -> dict[str, Any]:
        """Remove one cluster and its nodes."""
        return _serialize(service.remove_cluster(simulation_id, cluster_name))

    @tool()
    def run_simulation_for(
        simulation_id: str,
        duration: float,
        step: float | None = None,
    ) -> dict[str, Any]:
        """Advance the simulation for a duration relative to the current time."""
        return _serialize(
            service.schedule_for(simulation_id, duration=duration, step=step)
        )

    @tool()
    def pause_simulation(simulation_id: str) -> dict[str, Any]:
        """Pause a running simulation after the current step."""
        return _serialize(service.pause(simulation_id))

    @tool()
    def resume_simulation(simulation_id: str) -> dict[str, Any]:
        """Resume a paused simulation."""
        return _serialize(service.resume(simulation_id))

    @tool()
    def fork_simulation(
        simulation_id: str,
        child_name: str | None = None,
        child_id: str | None = None,
    ) -> dict[str, Any]:
        """
    Create an independent child simulation from the current state
    of an existing simulation.

    The child inherits the parent's state at the fork point,
    allowing alternative decisions and what-if experiments
    without modifying the original simulation.

    Both simulations can evolve independently, enabling
    comparisons between different strategies or actions.
    """
        return _serialize(
            service.fork(
                simulation_id,
                child_name=child_name,
                child_id=child_id,
            )
        )

    @tool()
    def wait_simulation_until_ready(
        simulation_id: str,
        poll_interval: float = 1.0,
    ) -> dict[str, Any]:
        """Wait until the scheduled window has finished and the simulation is ready."""
        return _serialize(
            service.wait_until_ready(
                simulation_id,
                poll_interval=poll_interval,
            )
        )

    @tool()
    def stop_simulation(simulation_id: str) -> dict[str, Any]:
        """Stop the simulation permanently."""
        return _serialize(service.stop(simulation_id))

    @tool()
    def destroy_simulation(simulation_id: str) -> dict[str, Any]:
        """Stop a simulation and remove it from the server."""
        return _serialize(service.destroy(simulation_id))

    @resource("simulation://{simulation_id}/state")
    def simulation_state_resource(simulation_id: str) -> dict[str, Any]:
        return _serialize(service.get_state(simulation_id))

    @resource("simulation://{simulation_id}/metrics")
    def simulation_metrics_resource(simulation_id: str) -> dict[str, Any]:
        return _serialize(service.get_metrics_snapshot(simulation_id))

    return app
