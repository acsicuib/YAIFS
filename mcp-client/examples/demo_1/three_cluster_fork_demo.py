from __future__ import annotations

import json
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "mcp-server" / "server.py"
OUTPUT_PATH = ROOT / "mcp-client" / "examples" / "three_cluster_fork_demo_output.json"


def _extract_payload(result):
    content = getattr(result, "content", None)
    if not content:
        return result

    text_chunks: list[str] = []
    for item in content:
        text = getattr(item, "text", None)
        if text:
            text_chunks.append(text)

    if not text_chunks:
        return result

    joined = "\n".join(text_chunks).strip()
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        return joined


async def call(session: ClientSession, name: str, arguments: dict) -> object:
    result = await session.call_tool(name, arguments=arguments)
    return _extract_payload(result)


async def main() -> None:
    params = StdioServerParameters(
        command="uv",
        args=["run", "python", str(SERVER_PATH)],
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            output: dict[str, object] = {}

            output["default_scenario"] = await call(session, "get_default_scenario", {})
            base = await call(
                session,
                "create_default_simulation",
                {
                    "seed": 2026,
                    "name": "baseline",
                },
            )
            output["create_default_simulation"] = base
            base_id = base["summary"]["id"]

            output["baseline_initial_clusters"] = await call(
                session,
                "list_simulation_clusters",
                {"simulation_id": base_id},
            )
            output["baseline_initial_users"] = await call(
                session,
                "list_simulation_users",
                {"simulation_id": base_id},
            )

            output["baseline_schedule_0_4000"] = await call(
                session,
                "run_simulation_for",
                {
                    "simulation_id": base_id,
                    "duration": 4000.0,
                    "step": 500.0,
                },
            )
            output["baseline_ready_4000"] = await call(
                session,
                "wait_simulation_until_ready",
                {
                    "simulation_id": base_id,
                    "poll_interval": 0.2,
                },
            )

            forked = await call(
                session,
                "fork_simulation",
                {
                    "simulation_id": base_id,
                    "child_name": "faulty-branch",
                },
            )
            output["fork_simulation"] = forked
            fork_id = forked["summary"]["id"]

            output["fork_remove_mec_cluster"] = await call(
                session,
                "remove_simulation_cluster",
                {
                    "simulation_id": fork_id,
                    "cluster_name": "mec-0",
                },
            )
            output["fork_clusters_after_removal"] = await call(
                session,
                "list_simulation_clusters",
                {"simulation_id": fork_id},
            )
            output["fork_users_after_removal"] = await call(
                session,
                "list_simulation_users",
                {"simulation_id": fork_id},
            )

            output["baseline_schedule_4000_12000"] = await call(
                session,
                "run_simulation_for",
                {
                    "simulation_id": base_id,
                    "duration": 8000.0,
                    "step": 500.0,
                },
            )
            output["fork_schedule_4000_12000"] = await call(
                session,
                "run_simulation_for",
                {
                    "simulation_id": fork_id,
                    "duration": 8000.0,
                    "step": 500.0,
                },
            )

            output["baseline_ready_12000"] = await call(
                session,
                "wait_simulation_until_ready",
                {
                    "simulation_id": base_id,
                    "poll_interval": 0.2,
                },
            )
            output["fork_ready_12000"] = await call(
                session,
                "wait_simulation_until_ready",
                {
                    "simulation_id": fork_id,
                    "poll_interval": 0.2,
                },
            )

            output["baseline_metrics_snapshot"] = await call(
                session,
                "get_simulation_network_metrics",
                {"simulation_id": base_id},
            )
            output["fork_metrics_snapshot"] = await call(
                session,
                "get_simulation_network_metrics",
                {"simulation_id": fork_id},
            )
            output["baseline_application_metrics"] = await call(
                session,
                "get_simulation_application_metrics",
                {"simulation_id": base_id},
            )
            output["fork_application_metrics"] = await call(
                session,
                "get_simulation_application_metrics",
                {"simulation_id": fork_id},
            )

            output["baseline_stop"] = await call(
                session,
                "stop_simulation",
                {"simulation_id": base_id},
            )
            output["fork_stop"] = await call(
                session,
                "stop_simulation",
                {"simulation_id": fork_id},
            )

    OUTPUT_PATH.write_text(
        json.dumps(output, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    print(str(OUTPUT_PATH))


if __name__ == "__main__":
    anyio.run(main)
