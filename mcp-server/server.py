from __future__ import annotations

import argparse
import os
from dataclasses import asdict, is_dataclass
from pathlib import Path

from yafs.services import SimulationService
from yafs.transports.mcp_server import build_mcp_server


DEFAULT_SCENARIO_PATH = (
    Path(__file__).resolve().parent.parent
    / "lab_scenarios"
    / "case_three_cluster"
    / "three-cluster"
)
DEFAULT_CONFIG_ENV = "YAFS_MCP_CONFIGURATIONS_DIR"
DEFAULT_RESULTS_ENV = "YAFS_MCP_RESULTS_DIR"


def _jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if is_dataclass(value):
        return _jsonable(asdict(value))
    return str(value)


def create_server(
    *,
    scenario_path: Path,
    configuration_root: Path | None = None,
    results_root: Path | None = None,
):
    service = SimulationService(
        default_results_root=results_root,
        default_configuration_root=configuration_root,
    )
    app = build_mcp_server(service, server_name="yafs-three-cluster")

    @app.tool()
    def get_default_scenario() -> dict[str, object]:
        return {
            "scenario_path": str(scenario_path),
            "exists": scenario_path.exists(),
        }

    @app.tool()
    def create_default_simulation(
        seed: int | None = None,
        name: str | None = None,
        services_definition_path: str | None = None,
        users_definition_path: str | None = None,
        placement_definition_path: str | None = None,
        topology_path: str | None = None,
    ) -> dict[str, object]:
        state = service.create_simulation(
            scenario_path=scenario_path,
            seed=seed,
            name=name,
            services_definition_path=services_definition_path,
            users_definition_path=users_definition_path,
            placement_definition_path=placement_definition_path,
            topology_path=topology_path,
        )
        return _jsonable(state)

    @app.tool()
    def create_default_simulation_configuration(
        configuration_name: str,
        cluster_count: int | None = None,
        nodes_per_cluster: int | None = None,
        topology_definition_path: str | None = None,
    ) -> dict[str, object]:
        return _jsonable(
            service.create_simulation_configuration(
                base_scenario_path=scenario_path,
                configuration_name=configuration_name,
                topology_definition_path=topology_definition_path,
                cluster_count=cluster_count,
                nodes_per_cluster=nodes_per_cluster,
            )
        )

    @app.tool()
    def create_default_simulation_from_configuration(
        configuration_path: str,
        seed: int | None = None,
        name: str | None = None,
    ) -> dict[str, object]:
        return _jsonable(
            service.create_simulation_from_configuration(
                configuration_path=configuration_path,
                seed=seed,
                name=name,
            )
        )

    @app.resource("simulation://default-scenario")
    def default_scenario_resource() -> dict[str, object]:
        return {
            "scenario_path": str(scenario_path),
            "exists": scenario_path.exists(),
            "configuration_root": (
                None if configuration_root is None else str(configuration_root)
            ),
            "results_root": None if results_root is None else str(results_root),
        }

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the YAFS MCP server using the three-cluster lab scenario.",
    )
    parser.add_argument(
        "--scenario-path",
        default=str(DEFAULT_SCENARIO_PATH),
        help="Base scenario path used by create_default_simulation.",
    )
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "sse", "streamable-http"],
        help="MCP transport to use. Defaults to stdio.",
    )
    parser.add_argument(
        "--configurations-dir",
        default=os.environ.get(DEFAULT_CONFIG_ENV),
        help="Default directory where generated configurations will be stored.",
    )
    parser.add_argument(
        "--results-dir",
        default=os.environ.get(DEFAULT_RESULTS_ENV),
        help="Default directory where simulation traces will be stored.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    scenario_path = Path(args.scenario_path).resolve()
    os.environ["YAFS_MCP_STDIO_SAFE"] = "1"
    configuration_root = (
        None
        if not args.configurations_dir
        else Path(args.configurations_dir).resolve()
    )
    results_root = None if not args.results_dir else Path(args.results_dir).resolve()
    if configuration_root is not None:
        configuration_root.mkdir(parents=True, exist_ok=True)
    if results_root is not None:
        results_root.mkdir(parents=True, exist_ok=True)

    app = create_server(
        scenario_path=scenario_path,
        configuration_root=configuration_root,
        results_root=results_root,
    )
    app.run(args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
