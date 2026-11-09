"""Run the multi-agent scenario through the YAFS MCP server and three models.

The base simulation is the workload from ``tutorial_scenarios/multi_agent_scenario``:
the same topology, services, empty users, empty placements, initial replicas,
MEC user bursts, and hotspot events. The MCP server exposes the YAFS tools
from ``yafs.transports.build_mcp_server``, the same surface used by
``apps/mcp/server``.

Each model receives ``DEFAULT_PROMPT`` first. Later turns only continue the
conversation. Each provider call stores the raw request body (the messages
and tool results sent to the model) and the raw response. Model actions,
latency over simulation time, and provider-call cost are written under the
results directory.

From the repository root:

    uv run python tutorial_scenarios/delegating_LLM_decisions/main_multi_agent_MCP_LLMs.py

Credentials are read from ``tutorial_scenarios/delegating_LLM_decisions/.env``
(``OPENAI_API_KEY`` and ``OPENAI_BASE_URL``).
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import math
import os
import random
import sys
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from yafs.distribution import deterministicDistributionStartPoint
from yafs.services import SimulationService
from yafs.transports import McpProfile, build_mcp_server
from tutorial_scenarios.multi_agent_scenario.main_multi_agent import (
    entry_messages_by_app,
    register_hotspot_events,
)
from tutorial_scenarios.multi_agent_scenario.main_random import (
    RandomMecUserBurstProcess,
    application_entry_messages,
    build_random_replica_definition,
    eligible_nodes,
    mec_worker_nodes,
    reduce_mec_worker_speed,
)


EXPERIMENT_DIR = Path(__file__).resolve().parent
SCENARIO_DIR = PROJECT_ROOT / "tutorial_scenarios" / "multi_agent_scenario"
DEFAULT_RESULTS_DIR = EXPERIMENT_DIR / "results"
DEFAULT_ENV_FILE = EXPERIMENT_DIR / ".env"
BASE_SIMULATION_NAME = "base"
MODEL_TOOL_RESULT_LIMIT = 8000

MODELS = [
    "openai/gpt-6-luna",
    "x-ai/grok-4.7",
    "anthropic/claude-sonnet-5.5",
]

DEFAULT_CONFIG: dict[str, Any] = {
    "seed": 2026,
    "replica_count": 20,
    "activation_interval": 200.0,
    "activation_count": 20,
    "post_activation_tail": 1000.0,
    "users_per_activation": 10,
    "user_lambda": 100.0,
    "window_duration": 200.0,
    "step": 50.0,
    "mec_worker_ipt": 10.0,
    "link_utilization_threshold": 0.5,
    "node_utilization_threshold": 0.08,
    "overload_streak_windows": 1,
    "placement_cost_budget": 8.70,
    "action_budget_per_window": 4,
    "prefer_overload_when_present": True,
    "egress_cost_per_gb": 0.02,
    "hotspot_events": [
        {
            "name": "HotspotUsers-Perception-MEC-I",
            "time": 1000.0,
            "app": "Perception Pipeline",
            "node": "mec-i-1-worker-3",
            "count": 60,
            "user_lambda": 15.0,
            "move_time": 1800.0,
            "move_to": "mec-i-1-worker-4",
            "remove_time": 2600.0,
            "remove_fraction": 0.4,
            "interval": 200.0,
        }
    ],
}

DEFAULT_PROMPT = (
    "You are an autonomous agent responsible for controlling "
    "an existing YAIFS simulation through MCP tools.\n\n"
    "SIMULATION CONTEXT\n"
    "Base simulation name: {name}\n"
    "Simulation ID: {simulation_id}\n"
    "Configured end time: {end}\n"
    "The topology, services, initial VNF replicas, MEC user arrivals, "
    "and hotspot events are already configured.\n\n"
    "OBJECTIVE\n"
    "Your primary goal is to minimize the latency of deployed "
    "applications throughout the simulation.\n"
    "Use the available MCP tools to observe the environment, "
    "analyze its behavior, and make decisions that improve "
    "application performance.\n\n"
    "SIMULATION CONTROL\n"
    "You decide when to inspect metrics, advance simulation time, "
    "and modify application deployments.\n"
    "After run_simulation_for, this session waits until the "
    "requested simulation window finishes before your next decision.\n"
    "You may choose different simulation window durations "
    "depending on the observed system behavior.\n\n"
    "EXPERIMENTATION\n"
    "You may use simulation forks to explore alternative decisions "
    "without modifying the original simulation.\n"
    "Forked simulations evolve independently and can be used "
    "to compare alternative strategies before applying changes "
    "to the base simulation.\n\n"
    "DECISION MAKING\n"
    "Base your decisions exclusively on information obtained "
    "through the available MCP tools.\n"
    "You are free to decide which actions to take, when to take "
    "them, and whether intervention is necessary.\n"
    "Avoid unnecessary changes when the system is performing well.\n"
    "Evaluate the consequences of your actions using simulation "
    "metrics whenever possible.\n\n"
    "TERMINATION\n"
    "Continue controlling the base simulation until it reaches "
    "the configured end time ({end}).\n"
    "Do not terminate the experiment prematurely. You need to control the simulation until it reaches the configured end time.\n"
)

def configured_simulation_end(config: dict[str, Any]) -> float:
    """Return the simulation stop time used by the multi-agent scenario."""
    return (
        float(config["activation_interval"]) * float(config["activation_count"])
        + float(config["post_activation_tail"])
    )


def format_time(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def render_default_prompt(base: dict[str, Any]) -> str:
    end = format_time(float(base["simulation_end"]))
    return DEFAULT_PROMPT.format(
        name=base["name"],
        simulation_id=base["simulation_id"],
        end=end,
    )


def build_config() -> dict[str, Any]:
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["simulation_duration"] = configured_simulation_end(config)
    return config


def model_slug(model: str) -> str:
    return "".join(
        char if char.isalnum() or char in "-._" else "_"
        for char in model
    )


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    module_name = type(value).__module__
    if module_name == "numpy" and hasattr(value, "item"):
        return jsonable(value.item())
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if is_dataclass(value):
        return jsonable(asdict(value))
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump())
    return str(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(jsonable(payload), indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(jsonable(payload), ensure_ascii=True) + "\n")
        handle.flush()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def redact_secrets(text: str) -> str:
    cleaned = text
    marker = "sk-"
    while marker in cleaned:
        start = cleaned.find(marker)
        end = start + len(marker)
        while end < len(cleaned) and cleaned[end] not in " \n\r\t\"',":
            end += 1
        cleaned = cleaned[:start] + "sk-REDACTED" + cleaned[end:]
    return cleaned


def find_simulation_now(value: Any) -> float | None:
    if isinstance(value, dict):
        summary = value.get("summary")
        if isinstance(summary, dict) and "now" in summary:
            try:
                return float(summary["now"])
            except (TypeError, ValueError):
                pass
        if "now" in value and "status" in value:
            try:
                return float(value["now"])
            except (TypeError, ValueError):
                pass
        for item in value.values():
            found = find_simulation_now(item)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_simulation_now(item)
            if found is not None:
                return found
    return None


def parse_json_text(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def clip_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]..."


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    def cell(value: object) -> str:
        return str(value).replace("|", "/").replace("\n", " ")

    head = "| " + " | ".join(cell(item) for item in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = [
        "| " + " | ".join(cell(item) for item in row) + " |"
        for row in rows
    ]
    if not body:
        body = ["| " + " | ".join("-" for _ in headers) + " |"]
    return "\n".join([head, separator, *body])


def format_usd(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.6f}"


def format_metric(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def server_log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def prepare_base_simulation(
    service: SimulationService,
    *,
    scenario_dir: Path,
    results_dir: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Create the multi-agent workload and name it ``base``."""
    required = (
        "logging.ini",
        "topology.json",
        "services.json",
        "empty_users.json",
        "empty_placements.json",
    )
    missing = [name for name in required if not (scenario_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Scenario {scenario_dir} is missing: {', '.join(missing)}"
        )

    state = service.create_simulation(
        scenario_path=scenario_dir,
        results_path=results_dir,
        seed=int(config["seed"]),
        name=BASE_SIMULATION_NAME,
        placement_definition_path="empty_placements.json",
        users_definition_path="empty_users.json",
    )
    simulation_id = str(state.summary.id)
    simulation = service.registry.require(simulation_id).simulation
    updated_mec_nodes = reduce_mec_worker_speed(
        simulation,
        mec_worker_ipt=float(config["mec_worker_ipt"]),
    )

    app_refs = [
        item.get("id", item["name"])
        for item in simulation.infrastructure.service_definitions_data
    ]
    if not app_refs:
        raise RuntimeError("The scenario does not define any application")

    deployment_nodes = eligible_nodes(simulation)
    placement_rng = random.Random(int(config["seed"]))
    for replica_index in range(int(config["replica_count"])):
        app_ref = app_refs[replica_index % len(app_refs)]
        definition = build_random_replica_definition(
            simulation,
            app_ref,
            rng=placement_rng,
            candidate_nodes=deployment_nodes,
        )
        service.deploy_application_vnfs(simulation_id, app_ref, definition)

    user_nodes = mec_worker_nodes(simulation)
    if not user_nodes:
        raise RuntimeError("No MEC worker nodes are available for user placement")

    user_process = RandomMecUserBurstProcess(
        app_message_pairs=application_entry_messages(simulation.infrastructure),
        candidate_nodes=user_nodes,
        users_per_activation=int(config["users_per_activation"]),
        user_lambda=float(config["user_lambda"]),
        max_activations=int(config["activation_count"]),
    )
    user_distribution = deterministicDistributionStartPoint(
        float(config["activation_interval"]),
        float(config["activation_interval"]),
        name="McpMultiAgentUserBurst",
    )
    simulation.register_process(
        "McpMultiAgentUserBurst",
        user_process,
        user_distribution,
    )
    registered_hotspots = register_hotspot_events(
        simulation,
        config=config,
        graph=simulation.infrastructure.topology.G,
        entry_messages=entry_messages_by_app(simulation.infrastructure),
    )
    return {
        "name": BASE_SIMULATION_NAME,
        "simulation_id": simulation_id,
        "simulation_end": float(config["simulation_duration"]),
        "window_duration": float(config["window_duration"]),
        "scenario_path": str(scenario_dir),
        "seed": int(config["seed"]),
        "replica_count": int(config["replica_count"]),
        "updated_mec_nodes": int(updated_mec_nodes),
        "registered_hotspot_events": int(registered_hotspots),
        "config": config,
    }


def _remember_action(results_dir: Path, name: str, payload: dict[str, Any]) -> str:
    folder = results_dir / "applied_actions"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%H%M%S%f")
    path = folder / f"{stamp}_{name}.json"
    write_json(path, payload)
    return str(path)


def build_experiment_server(
    service: SimulationService,
    *,
    base: dict[str, Any],
    results_dir: Path,
):
    """Expose the Placement profile plus direct placement actions.

    The Placement profile includes the inventory, placement, controller,
    and analyst tool groups.
    """
    app = build_mcp_server(
        service,
        server_name="yaifs-base-simulation",
        profiles=[McpProfile.PLACEMENT],
    )
    simulation_id = str(base["simulation_id"])

    @app.tool()
    def get_base_simulation() -> dict[str, Any]:
        """Return the existing base simulation id, clock, and configured end."""
        state = service.get_state(simulation_id)
        summary = state.summary
        return jsonable(
            {
                **base,
                "now": summary.now,
                "status": str(summary.status),
                "deployed_applications": service.list_deployed_applications(
                    simulation_id
                ),
            }
        )

    @app.tool()
    def apply_deploy_application_vnfs(
        simulation_id: str,
        app: str,
        placements: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Deploy VNFs. Each placement has module_name and id_resource."""
        payload = {"app": app, "placements": placements}
        recorded = _remember_action(results_dir, "deploy", payload)
        result = service.deploy_application_vnfs(simulation_id, app, payload)
        return jsonable({**result, "action_file": recorded})

    @app.tool()
    def apply_move_application_vnf(
        simulation_id: str,
        app: str,
        vnf: str,
        to_node: str,
        from_node: str = "",
    ) -> dict[str, Any]:
        """Move one VNF. Fields match the service-layer move action JSON."""
        payload: dict[str, Any] = {"vnf": vnf, "to_node": to_node}
        if from_node:
            payload["from_node"] = from_node
        recorded = _remember_action(results_dir, "move", payload)
        result = service.move_application_vnf(simulation_id, app, payload)
        return jsonable({**result, "action_file": recorded})

    @app.tool()
    def apply_replicate_application_vnf(
        simulation_id: str,
        app: str,
        vnf: str,
        to_node: str,
    ) -> dict[str, Any]:
        """Replicate one VNF onto to_node."""
        payload = {"vnf": vnf, "to_node": to_node}
        recorded = _remember_action(results_dir, "replicate", payload)
        result = service.replicate_application_vnf(simulation_id, app, payload)
        return jsonable({**result, "action_file": recorded})

    @app.tool()
    def apply_remove_application_vnf(
        simulation_id: str,
        app: str,
        vnf: str,
        node: str = "",
    ) -> dict[str, Any]:
        """Remove one VNF. Pass node when more than one copy exists."""
        payload: dict[str, Any] = {"vnf": vnf}
        if node:
            payload["node"] = node
        recorded = _remember_action(results_dir, "remove", payload)
        result = service.remove_application_vnf(simulation_id, app, payload)
        return jsonable({**result, "action_file": recorded})

    return app


def serve(results_dir: Path) -> int:
    """Start the MCP server with the base simulation already created."""
    os.environ["YAFS_MCP_STDIO_SAFE"] = "1"
    results_dir.mkdir(parents=True, exist_ok=True)
    config = build_config()
    try:
        server_log(f"Preparing base simulation in {results_dir}")
        service = SimulationService(default_results_root=results_dir)
        base = prepare_base_simulation(
            service,
            scenario_dir=SCENARIO_DIR,
            results_dir=results_dir,
            config=config,
        )
        write_json(results_dir / "base_simulation.json", base)
        app = build_experiment_server(
            service,
            base=base,
            results_dir=results_dir,
        )
        server_log(
            "Base simulation "
            f"{base['simulation_id']} ready until t={base['simulation_end']}"
        )
    except Exception:
        failure = traceback.format_exc()
        (results_dir / "bootstrap_error.txt").write_text(failure, encoding="utf-8")
        server_log(failure)
        return 1

    app.run("stdio")
    return 0


def build_system_context(base: dict[str, Any]) -> str:
    return render_default_prompt(base)


def tool_result_text(result: Any) -> str:
    content = getattr(result, "content", None)
    if content is None and isinstance(result, dict):
        content = result.get("content")
    parts: list[str] = []
    for item in content or []:
        if isinstance(item, dict):
            text = item.get("text")
        else:
            text = getattr(item, "text", None)
        if text:
            parts.append(str(text))
    if parts:
        return "\n".join(parts)
    return json.dumps(jsonable(result), ensure_ascii=True)


def mcp_tool_to_openai(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
    if not isinstance(schema, dict):
        schema = {"type": "object", "properties": {}}
    parameters = jsonable(schema)
    if not isinstance(parameters, dict) or parameters.get("type") != "object":
        parameters = {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": getattr(tool, "name"),
            "description": getattr(tool, "description", "") or "",
            "parameters": parameters,
        },
    }


def parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        parsed = parse_json_text(raw)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"Tool arguments are not a JSON object: {raw!r}")


class ProviderClient:
    """OpenAI-compatible chat client.

    Records the raw request body sent to the provider and the raw response.
    The request is the conversation forwarded from MCP, including tool
    results. The API key is not written to disk.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        raw_request_path: Path,
        raw_response_path: Path,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.raw_request_path = raw_request_path
        self.raw_response_path = raw_response_path

    def create_chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        turn: int,
        sim_time: float,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "usage": {"include": True},
        }
        append_jsonl(
            self.raw_request_path,
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "model": self.model,
                "turn": turn,
                "sim_time": sim_time,
                "url": f"{self.base_url}/chat/completions",
                "request": payload,
            },
        )
        body = json.dumps(payload).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(2):
            request = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "X-Title": "YAIFS MCP experiment",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=180) as response:
                    raw = json.loads(response.read().decode("utf-8"))
                append_jsonl(
                    self.raw_response_path,
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "model": self.model,
                        "turn": turn,
                        "sim_time": sim_time,
                        "response": raw,
                    },
                )
                return raw
            except urllib.error.HTTPError as exc:
                detail = redact_secrets(exc.read().decode("utf-8", errors="replace"))
                last_error = RuntimeError(
                    f"Provider API error {exc.code}: {detail}"
                )
                if exc.code in {429, 500, 502, 503} and attempt == 0:
                    time.sleep(2)
                    continue
                break
            except urllib.error.URLError as exc:
                last_error = RuntimeError(f"Provider connection error: {exc}")
                break
        assert last_error is not None
        append_jsonl(
            self.raw_response_path,
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "model": self.model,
                "turn": turn,
                "sim_time": sim_time,
                "error": redact_secrets(str(last_error)),
            },
        )
        raise last_error


def fetch_model_pricing(base_url: str) -> dict[str, dict[str, float]]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/models",
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    prices: dict[str, dict[str, float]] = {}
    for item in payload.get("data", []):
        pricing = item.get("pricing") or {}
        model_id = item.get("id")
        if not model_id:
            continue
        try:
            prices[str(model_id)] = {
                "prompt": float(pricing.get("prompt") or 0.0),
                "completion": float(pricing.get("completion") or 0.0),
                "request": float(pricing.get("request") or 0.0),
            }
        except (TypeError, ValueError):
            continue
    return prices


def call_cost_usd(
    usage: dict[str, Any],
    pricing: dict[str, float] | None,
) -> tuple[float | None, str]:
    if usage.get("cost") is not None:
        try:
            return float(usage["cost"]), "provider"
        except (TypeError, ValueError):
            pass
    if not pricing:
        return None, "unknown"
    prompt_tokens = float(usage.get("prompt_tokens") or 0.0)
    completion_tokens = float(usage.get("completion_tokens") or 0.0)
    cost = (
        prompt_tokens * pricing["prompt"]
        + completion_tokens * pricing["completion"]
        + pricing["request"]
    )
    return cost, "token_price"


def assistant_message(message: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": "assistant",
        "content": message.get("content") or "",
    }
    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        payload["tool_calls"] = tool_calls
    return payload


def tool_call_parts(call: dict[str, Any]) -> tuple[str, str, Any]:
    function = call.get("function") if isinstance(call.get("function"), dict) else {}
    name = str(function.get("name") or call.get("name") or "")
    call_id = str(call.get("id") or call.get("call_id") or "")
    arguments = function.get("arguments", call.get("arguments", "{}"))
    return name, call_id, arguments


async def invoke_tool(
    session: Any,
    *,
    name: str,
    arguments: dict[str, Any],
) -> tuple[str, bool]:
    try:
        result = await session.call_tool(name, arguments=arguments)
    except Exception as exc:
        return redact_secrets(str(exc)), False
    text = tool_result_text(result)
    is_error = bool(getattr(result, "isError", False))
    if isinstance(result, dict):
        is_error = bool(result.get("isError", is_error))
    return text, not is_error


def observed_now(text: str) -> float | None:
    parsed = parse_json_text(text)
    if parsed is None:
        return None
    return find_simulation_now(parsed)


async def read_simulation_now(session: Any, simulation_id: str) -> float | None:
    text, ok = await invoke_tool(
        session,
        name="get_simulation_state",
        arguments={"simulation_id": simulation_id},
    )
    if not ok:
        return None
    return observed_now(text)


def series_stat(values: pd.Series, how: str) -> float | None:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return None
    if how == "mean":
        return float(clean.mean())
    if how == "p95":
        return float(clean.quantile(0.95))
    raise ValueError(how)


def latency_frame(results_dir: Path, simulation_id: str) -> pd.DataFrame:
    from yafs.metrics import MetricsAnalyzer

    trace = results_dir / f"sim_trace_{simulation_id}.csv"
    if not trace.exists():
        raise FileNotFoundError(f"Simulation trace was not written: {trace}")
    analyzer = MetricsAnalyzer(
        defaultPath=str(trace),
        app_definition=str(SCENARIO_DIR / "services.json"),
    )
    frame = analyzer.service_response(include_return_messages=True)
    if frame.empty:
        return pd.DataFrame(columns=["app", "end_time", "service_response"])
    return frame


def window_bounds(simulation_end: float, window: float) -> list[tuple[float, float]]:
    bounds: list[tuple[float, float]] = []
    start = 0.0
    while start < simulation_end - 1e-9:
        stop = min(start + window, simulation_end)
        bounds.append((start, stop))
        start = stop
    return bounds


def slice_window(
    frame: pd.DataFrame,
    start: float,
    stop: float,
    *,
    last: bool,
) -> pd.DataFrame:
    if frame.empty:
        return frame
    if last:
        mask = (frame["end_time"] >= start) & (frame["end_time"] <= stop)
    else:
        mask = (frame["end_time"] >= start) & (frame["end_time"] < stop)
    return frame.loc[mask]


def build_latency_windows(
    frame: pd.DataFrame,
    *,
    simulation_end: float,
    window: float,
) -> list[dict[str, Any]]:
    apps = sorted(str(app) for app in frame["app"].dropna().unique()) if not frame.empty else []
    bounds = window_bounds(simulation_end, window)
    windows: list[dict[str, Any]] = []
    for index, (start, stop) in enumerate(bounds):
        chunk = slice_window(frame, start, stop, last=index == len(bounds) - 1)
        applications = []
        for app in apps:
            app_rows = chunk[chunk["app"] == app] if not chunk.empty else chunk
            applications.append(
                {
                    "app": app,
                    "requests": int(len(app_rows)),
                    "response_mean": series_stat(app_rows["service_response"], "mean")
                    if not app_rows.empty
                    else None,
                    "response_p95": series_stat(app_rows["service_response"], "p95")
                    if not app_rows.empty
                    else None,
                }
            )
        windows.append(
            {
                "window_start": start,
                "window_end": stop,
                "requests": int(len(chunk)),
                "response_mean": series_stat(chunk["service_response"], "mean")
                if not chunk.empty
                else None,
                "response_p95": series_stat(chunk["service_response"], "p95")
                if not chunk.empty
                else None,
                "applications": applications,
            }
        )
    return windows


def overall_latency(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    rows = []
    for app, app_rows in frame.groupby("app", dropna=False):
        rows.append(
            {
                "app": str(app),
                "requests": int(len(app_rows)),
                "response_mean": series_stat(app_rows["service_response"], "mean"),
                "response_p95": series_stat(app_rows["service_response"], "p95"),
            }
        )
    return rows


def load_actions(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def model_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = [
        item
        for item in actions
        if item.get("actor") == "model"
    ]
    return sorted(
        selected,
        key=lambda item: (
            float(item["simulation_now"])
            if item.get("simulation_now") is not None
            else math.inf,
            int(item.get("turn") or 0),
        ),
    )


def action_windows(
    actions: list[dict[str, Any]],
    *,
    simulation_end: float,
    window: float,
) -> list[dict[str, Any]]:
    bounds = window_bounds(simulation_end, window)
    rows = []
    for index, (start, stop) in enumerate(bounds):
        chosen = []
        for action in actions:
            now = action.get("simulation_now")
            if now is None:
                continue
            moment = float(now)
            if index == len(bounds) - 1:
                inside = start <= moment <= stop
            else:
                inside = start <= moment < stop
            if inside:
                chosen.append(action)
        rows.append(
            {
                "window_start": start,
                "window_end": stop,
                "action_count": len(chosen),
                "tools": [str(item.get("tool")) for item in chosen],
            }
        )
    return rows


def provider_calls_from_log(
    path: Path,
    pricing: dict[str, float] | None,
) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    calls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
        usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
        cost, source = call_cost_usd(usage, pricing)
        if entry.get("error"):
            cost = None
            source = "error"
        calls.append(
            {
                "timestamp": entry.get("timestamp"),
                "turn": entry.get("turn"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "cost_usd": cost,
                "cost_source": source,
                "error": entry.get("error"),
            }
        )
    return calls


def write_latency_plot(path: Path, windows: list[dict[str, Any]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    apps: list[str] = []
    for window in windows:
        for item in window.get("applications", []):
            name = str(item.get("app"))
            if name not in apps:
                apps.append(name)

    fig, ax = plt.subplots(figsize=(10, 5))
    for app in apps:
        xs = []
        ys = []
        for window in windows:
            for item in window.get("applications", []):
                if item.get("app") == app and item.get("response_p95") is not None:
                    xs.append(float(window["window_end"]))
                    ys.append(float(item["response_p95"]))
        if xs:
            ax.plot(xs, ys, marker="o", linewidth=1.5, label=app)
    ax.set_xlabel("Simulation time")
    ax.set_ylabel("Response latency p95")
    ax.set_title("Latency evolution")
    if apps:
        ax.legend()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def write_actions_plot(
    path: Path,
    actions: list[dict[str, Any]],
    *,
    simulation_end: float | None = None,
    title: str | None = None,
) -> None:
    """Draw MCP calls on Placement, Analysis, and Control bands."""
    from tutorial_scenarios.delegating_LLM_decisions.plot_action_timeline import (
        plot_category_timeline,
    )

    plot_category_timeline(
        actions,
        path,
        simulation_end=simulation_end,
        title=title,
    )


def write_cost_plot(path: Path, calls: list[dict[str, Any]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cumulative = []
    total = 0.0
    seen = False
    for index, call in enumerate(calls, start=1):
        cost = call.get("cost_usd")
        if cost is None:
            continue
        seen = True
        total += float(cost)
        cumulative.append((index, total))

    fig, ax = plt.subplots(figsize=(10, 4))
    if not seen:
        ax.text(0.5, 0.5, "Provider cost was not reported", ha="center", va="center")
        ax.set_axis_off()
    else:
        ax.plot(
            [item[0] for item in cumulative],
            [item[1] for item in cumulative],
            marker="o",
        )
        ax.set_xlabel("Provider call")
        ax.set_ylabel("Cumulative cost (USD)")
        ax.set_title("Provider call cost")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def write_run_report(path: Path, analysis: dict[str, Any]) -> None:
    action_rows = [
        [
            str(item.get("turn", "-")),
            format_metric(item.get("simulation_now"))
            if item.get("simulation_now") is not None
            else "n/a",
            str(item.get("tool", "-")),
            "ok" if item.get("ok") else "error",
            clip_text(json.dumps(item.get("arguments", {}), ensure_ascii=True), 180),
        ]
        for item in analysis.get("actions", [])
    ]
    latency_rows = [
        [
            format_time(float(item["window_start"])),
            format_time(float(item["window_end"])),
            str(item.get("requests", 0)),
            format_metric(item.get("response_mean")),
            format_metric(item.get("response_p95")),
        ]
        for item in analysis.get("latency_windows", [])
        if int(item.get("requests") or 0) > 0
    ]
    overall_rows = [
        [
            str(item.get("app")),
            str(item.get("requests", 0)),
            format_metric(item.get("response_mean")),
            format_metric(item.get("response_p95")),
        ]
        for item in analysis.get("overall_latency", [])
    ]
    cost_rows = [
        [
            str(item.get("turn", "-")),
            str(item.get("prompt_tokens", "-")),
            str(item.get("completion_tokens", "-")),
            format_usd(item.get("cost_usd")),
            str(item.get("cost_source", "-")),
        ]
        for item in analysis.get("provider_calls", [])
    ]
    lines = [
        f"# MCP model run: {analysis.get('model')}",
        "",
        "## Run",
        "",
        f"- Simulation id: `{analysis.get('simulation_id')}`",
        f"- Configured end: `{analysis.get('simulation_end')}`",
        f"- Final simulation time: `{analysis.get('final_simulation_time')}`",
        f"- Reached configured end: `{analysis.get('reached_end')}`",
        f"- Stop reason: `{analysis.get('stopped_reason')}`",
        f"- Model actions: `{len(analysis.get('actions', []))}`",
        f"- Provider calls: `{analysis.get('provider_call_count')}`",
        f"- Prompt tokens: `{analysis.get('prompt_tokens')}`",
        f"- Completion tokens: `{analysis.get('completion_tokens')}`",
        f"- Provider cost (USD): `{format_usd(analysis.get('provider_cost_usd'))}`",
        "",
        "## Actions over time",
        "",
        markdown_table(
            ["Turn", "Sim time", "Tool", "Status", "Arguments"],
            action_rows,
        ),
        "",
        "## Latency evolution",
        "",
        markdown_table(
            ["Start", "End", "Requests", "Mean", "p95"],
            latency_rows,
        ),
        "",
        "## Overall latency",
        "",
        markdown_table(
            ["Application", "Requests", "Mean", "p95"],
            overall_rows,
        ),
        "",
        "## Provider call cost",
        "",
        markdown_table(
            ["Turn", "Prompt tokens", "Completion tokens", "USD", "Source"],
            cost_rows,
        ),
        "",
    ]
    if analysis.get("latency_error"):
        lines.extend(["## Latency note", "", str(analysis["latency_error"]), ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def analyze_model_dir(
    model_dir: Path,
    *,
    pricing: dict[str, float] | None,
) -> dict[str, Any]:
    status_path = model_dir / "run_status.json"
    status = read_json(status_path) if status_path.exists() else {}
    simulation_end = float(
        status.get("simulation_end") or configured_simulation_end(build_config())
    )
    window = float(status.get("window_duration") or DEFAULT_CONFIG["window_duration"])
    simulation_id = str(status.get("simulation_id") or "")
    logged_actions = load_actions(model_dir / "actions.jsonl")
    actions = model_actions(logged_actions)
    calls = provider_calls_from_log(model_dir / "raw_responses.jsonl", pricing)
    known_costs = [float(item["cost_usd"]) for item in calls if item.get("cost_usd") is not None]
    prompt_tokens = sum(int(item.get("prompt_tokens") or 0) for item in calls)
    completion_tokens = sum(int(item.get("completion_tokens") or 0) for item in calls)

    latency_error = None
    windows: list[dict[str, Any]] = []
    overall: list[dict[str, Any]] = []
    try:
        frame = latency_frame(model_dir, simulation_id)
        windows = build_latency_windows(
            frame,
            simulation_end=simulation_end,
            window=window,
        )
        overall = overall_latency(frame)
        if not frame.empty:
            export = frame[["app", "end_time", "service_response"]].copy()
            export.to_csv(model_dir / "latency_requests.csv", index=False)
    except Exception as exc:
        latency_error = str(exc)

    analysis = {
        "model": status.get("model"),
        "simulation_id": simulation_id,
        "simulation_end": simulation_end,
        "window_duration": window,
        "final_simulation_time": status.get("final_simulation_time"),
        "reached_end": status.get("reached_end"),
        "stopped_reason": status.get("stopped_reason"),
        "actions": actions,
        "action_windows": action_windows(
            actions,
            simulation_end=simulation_end,
            window=window,
        ),
        "latency_windows": windows,
        "overall_latency": overall,
        "latency_error": latency_error,
        "provider_calls": calls,
        "provider_call_count": len(calls),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "provider_cost_usd": sum(known_costs) if known_costs else None,
    }
    write_json(model_dir / "analysis.json", analysis)
    write_run_report(model_dir / "analysis.md", analysis)
    try:
        write_latency_plot(model_dir / "latency_evolution.png", windows)
        write_actions_plot(
            model_dir / "actions_over_time.png",
            logged_actions,
            simulation_end=simulation_end,
            title=str(status.get("model") or model_dir.name),
        )
        write_cost_plot(model_dir / "provider_cost.png", calls)
    except Exception as exc:
        (model_dir / "plot_error.txt").write_text(str(exc), encoding="utf-8")
    return analysis


def write_comparison(
    run_root: Path,
    analyses: list[dict[str, Any]],
) -> None:
    rows = []
    for item in analyses:
        final_latency = None
        populated = [
            window
            for window in item.get("latency_windows", [])
            if window.get("response_p95") is not None
        ]
        if populated:
            final_latency = populated[-1].get("response_p95")
        rows.append(
            [
                str(item.get("model")),
                format_metric(item.get("final_simulation_time"))
                if item.get("final_simulation_time") is not None
                else "n/a",
                "yes" if item.get("reached_end") else "no",
                str(len(item.get("actions", []))),
                format_metric(final_latency),
                format_usd(item.get("provider_cost_usd")),
                str(item.get("stopped_reason") or "-"),
            ]
        )
    lines = [
        "# MCP model comparison",
        "",
        markdown_table(
            [
                "Model",
                "Final sim time",
                "Reached end",
                "Actions",
                "Last window p95",
                "Provider cost USD",
                "Stop reason",
            ],
            rows,
        ),
        "",
    ]
    (run_root / "comparison.md").write_text("\n".join(lines), encoding="utf-8")
    write_json(run_root / "comparison.json", analyses)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 5))
    plotted = False
    for item in analyses:
        xs = []
        ys = []
        for window in item.get("latency_windows", []):
            if window.get("response_p95") is None:
                continue
            xs.append(float(window["window_end"]))
            ys.append(float(window["response_p95"]))
        if xs:
            plotted = True
            ax.plot(xs, ys, marker="o", label=str(item.get("model")))
    ax.set_xlabel("Simulation time")
    ax.set_ylabel("Response latency p95")
    ax.set_title("Latency evolution by model")
    if plotted:
        ax.legend()
    else:
        ax.text(0.5, 0.5, "No latency samples", ha="center", va="center")
    fig.tight_layout()
    fig.savefig(run_root / "comparison_latency.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4))
    labels = [str(item.get("model")) for item in analyses]
    costs = [
        float(item["provider_cost_usd"])
        if item.get("provider_cost_usd") is not None
        else 0.0
        for item in analyses
    ]
    ax.bar(labels, costs)
    ax.tick_params(axis="x", rotation=20)
    ax.set_ylabel("Provider cost (USD)")
    ax.set_title("Provider call cost by model")
    fig.tight_layout()
    fig.savefig(run_root / "comparison_cost.png", dpi=140)
    plt.close(fig)


async def run_model(
    *,
    model: str,
    model_dir: Path,
    api_key: str,
    base_url: str,
    max_turns: int,
    max_stalls: int,
) -> dict[str, Any]:
    from mcp import ClientSession
    from mcp import StdioServerParameters
    from mcp.client.stdio import stdio_client

    model_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "raw_requests.jsonl",
        "raw_responses.jsonl",
        "actions.jsonl",
        "transcript.jsonl",
    ):
        target = model_dir / name
        if target.exists():
            target.unlink()

    env = os.environ.copy()
    env["YAFS_MCP_STDIO_SAFE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[
            str(Path(__file__).resolve()),
            "--serve",
            "--results-dir",
            str(model_dir),
        ],
        env=env,
        cwd=str(model_dir),
    )
    started = time.perf_counter()
    status: dict[str, Any] = {
        "model": model,
        "simulation_end": configured_simulation_end(build_config()),
        "window_duration": float(DEFAULT_CONFIG["window_duration"]),
        "stopped_reason": "error",
        "reached_end": False,
        "final_simulation_time": None,
        "simulation_id": None,
    }

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(
            read,
            write,
            read_timeout_seconds=timedelta(hours=6),
        ) as session:
            await session.initialize()
            base_path = model_dir / "base_simulation.json"
            if not base_path.exists():
                raise RuntimeError(
                    "The MCP server did not write base_simulation.json. "
                    "See bootstrap_error.txt in the model directory."
                )
            base = read_json(base_path)
            simulation_id = str(base["simulation_id"])
            simulation_end = float(base["simulation_end"])
            status.update(
                {
                    "simulation_id": simulation_id,
                    "simulation_end": simulation_end,
                    "window_duration": float(base["window_duration"]),
                }
            )
            tool_result = await session.list_tools()
            tools = [
                mcp_tool_to_openai(tool)
                for tool in getattr(tool_result, "tools", [])
            ]
            provider = ProviderClient(
                api_key=api_key,
                model=model,
                base_url=base_url,
                raw_request_path=model_dir / "raw_requests.jsonl",
                raw_response_path=model_dir / "raw_responses.jsonl",
            )
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": build_system_context(base)},
                {
                    "role": "user",
                    "content": render_default_prompt(base),
                },
            ]
            append_jsonl(
                model_dir / "transcript.jsonl",
                {"role": "user", "content": messages[-1]["content"]},
            )
            sim_now = 0.0
            stalls = 0
            reason = "max_turns"
            for turn in range(1, max_turns + 1):
                if sim_now + 1e-3 >= simulation_end:
                    reason = "reached_end"
                    break
                print(
                    f"{model}: turn {turn}, simulation time "
                    f"{format_time(sim_now)}/{format_time(simulation_end)}",
                    flush=True,
                )
                try:
                    response = provider.create_chat(
                        messages=messages,
                        tools=tools,
                        turn=turn,
                        sim_time=sim_now,
                    )
                except Exception as exc:
                    reason = "error"
                    status["error"] = redact_secrets(str(exc))
                    break
                choice = (response.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                text = str(message.get("content") or "").strip()
                if text:
                    append_jsonl(
                        model_dir / "transcript.jsonl",
                        {"role": "assistant", "turn": turn, "content": text},
                    )
                messages.append(assistant_message(message))
                tool_calls = message.get("tool_calls") or []
                if not tool_calls:
                    current = await read_simulation_now(session, simulation_id)
                    if current is not None:
                        sim_now = current
                    if sim_now + 1e-3 >= simulation_end:
                        reason = "reached_end"
                        break
                    stalls += 1
                    if stalls >= max_stalls:
                        reason = "stalled"
                        break
                    nudge = (
                        f"The simulation time is {format_time(sim_now)}. "
                        f"The configured end time is {format_time(simulation_end)}. "
                        "Continue until the simulation reaches that time. "
                        "Use the MCP tools to advance the simulation, inspect "
                        "it, and apply any actions you decide."
                    )
                    messages.append({"role": "user", "content": nudge})
                    append_jsonl(
                        model_dir / "transcript.jsonl",
                        {"role": "user", "turn": turn, "content": nudge},
                    )
                    continue

                stalls = 0
                called: list[str] = []
                for call in tool_calls:
                    name, call_id, raw_arguments = tool_call_parts(call)
                    if not call_id:
                        call_id = f"call_{turn}_{len(called)}"
                    try:
                        arguments = parse_tool_arguments(raw_arguments)
                        argument_error = None
                    except ValueError as exc:
                        arguments = {"raw": raw_arguments}
                        argument_error = str(exc)
                    if argument_error is None:
                        result_text, ok = await invoke_tool(
                            session,
                            name=name,
                            arguments=arguments,
                        )
                        error = None if ok else result_text
                    else:
                        result_text = argument_error
                        ok = False
                        error = argument_error
                    moment = observed_now(result_text)
                    if moment is not None:
                        sim_now = moment
                    append_jsonl(
                        model_dir / "actions.jsonl",
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "actor": "model",
                            "turn": turn,
                            "tool": name,
                            "arguments": arguments,
                            "ok": ok,
                            "error": error,
                            "simulation_now": moment,
                            "result": clip_text(result_text, 4000),
                        },
                    )
                    append_jsonl(
                        model_dir / "transcript.jsonl",
                        {
                            "role": "tool",
                            "turn": turn,
                            "tool": name,
                            "ok": ok,
                        },
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": clip_text(result_text, MODEL_TOOL_RESULT_LIMIT),
                        }
                    )
                    called.append(name)

                scheduled = any(
                    name == "run_simulation_for"
                    for name in called
                )
                waited = "wait_simulation_until_ready" in called
                if scheduled and not waited:
                    wait_text, wait_ok = await invoke_tool(
                        session,
                        name="wait_simulation_until_ready",
                        arguments={
                            "simulation_id": simulation_id,
                            "poll_interval": 0.2,
                        },
                    )
                    wait_now = observed_now(wait_text)
                    if wait_now is not None:
                        sim_now = wait_now
                    append_jsonl(
                        model_dir / "actions.jsonl",
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "actor": "harness",
                            "turn": turn,
                            "tool": "wait_simulation_until_ready",
                            "arguments": {"simulation_id": simulation_id},
                            "ok": wait_ok,
                            "error": None if wait_ok else wait_text,
                            "simulation_now": wait_now,
                            "result": clip_text(wait_text, 1000),
                            "note": "Wait for the advance requested by the model",
                        },
                    )

                current = await read_simulation_now(session, simulation_id)
                if current is not None:
                    sim_now = current
                if sim_now + 1e-3 >= simulation_end:
                    reason = "reached_end"
                    break
            else:
                reason = "max_turns"

            try:
                await invoke_tool(
                    session,
                    name="wait_simulation_until_ready",
                    arguments={"simulation_id": simulation_id, "poll_interval": 0.2},
                )
                final_text, _final_ok = await invoke_tool(
                    session,
                    name="get_simulation_state",
                    arguments={"simulation_id": simulation_id},
                )
                final_now = observed_now(final_text)
                if final_now is not None:
                    sim_now = final_now
                await invoke_tool(
                    session,
                    name="stop_simulation",
                    arguments={"simulation_id": simulation_id},
                )
            except Exception as exc:
                status["shutdown_error"] = str(exc)

            if sim_now + 1e-3 >= simulation_end:
                reason = "reached_end"
            status.update(
                {
                    "stopped_reason": reason,
                    "final_simulation_time": sim_now,
                    "reached_end": sim_now + 1e-3 >= simulation_end,
                    "elapsed_seconds": time.perf_counter() - started,
                }
            )
            write_json(model_dir / "run_status.json", status)
    return status


async def run_experiment(args: argparse.Namespace) -> int:
    load_env_file(Path(args.env_file))
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is required.", file=sys.stderr)
        return 2
    base_url = os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    models = list(args.models or MODELS)
    if args.results_dir is None:
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        run_root = DEFAULT_RESULTS_DIR / stamp
    else:
        run_root = Path(args.results_dir)
    run_root.mkdir(parents=True, exist_ok=True)

    try:
        catalog = fetch_model_pricing(base_url)
    except Exception as exc:
        print(f"Could not load provider pricing: {exc}", flush=True)
        catalog = {}

    print(f"Results: {run_root}", flush=True)
    print(f"Base scenario: {SCENARIO_DIR}", flush=True)
    print(
        "Configured simulation end: "
        f"{format_time(configured_simulation_end(build_config()))}",
        flush=True,
    )
    analyses: list[dict[str, Any]] = []
    for model in models:
        model_dir = run_root / model_slug(model)
        print(f"Starting {model}", flush=True)
        try:
            await run_model(
                model=model,
                model_dir=model_dir,
                api_key=api_key,
                base_url=base_url,
                max_turns=int(args.max_turns),
                max_stalls=int(args.max_stalls),
            )
        except Exception as exc:
            failure = traceback.format_exc()
            model_dir.mkdir(parents=True, exist_ok=True)
            (model_dir / "run_error.txt").write_text(failure, encoding="utf-8")
            if not (model_dir / "run_status.json").exists():
                write_json(
                    model_dir / "run_status.json",
                    {
                        "model": model,
                        "stopped_reason": "error",
                        "reached_end": False,
                        "error": redact_secrets(str(exc)),
                        "simulation_end": configured_simulation_end(build_config()),
                        "window_duration": float(DEFAULT_CONFIG["window_duration"]),
                    },
                )
            print(f"{model} failed: {exc}", flush=True)
        try:
            analyses.append(
                analyze_model_dir(model_dir, pricing=catalog.get(model))
            )
        except Exception as exc:
            (model_dir / "analysis_error.txt").write_text(
                traceback.format_exc(),
                encoding="utf-8",
            )
            print(f"Analysis failed for {model}: {exc}", flush=True)

    if analyses:
        try:
            write_comparison(run_root, analyses)
        except Exception:
            (run_root / "comparison_error.txt").write_text(
                traceback.format_exc(),
                encoding="utf-8",
            )
    print(f"Finished. Reports are in {run_root}", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Control the multi-agent base simulation with MCP-backed models."
        )
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Run the MCP server for one already prepared results directory.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help=(
            "Run directory. In server mode this is the model directory. "
            "Defaults to results/<timestamp>/ under this scenario."
        ),
    )
    parser.add_argument(
        "--model",
        dest="models",
        action="append",
        default=None,
        help="Provider model id. Repeat to select a subset of MODELS.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help="Env file with OPENAI_API_KEY and OPENAI_BASE_URL.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=120,
        help="Maximum provider calls for one model.",
    )
    parser.add_argument(
        "--max-stalls",
        type=int,
        default=6,
        help="Stop after this many replies that do not call a tool.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.serve:
        if args.results_dir is None:
            print("--results-dir is required in server mode.", file=sys.stderr)
            return 2
        return serve(args.results_dir.resolve())
    try:
        return asyncio.run(run_experiment(args))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
