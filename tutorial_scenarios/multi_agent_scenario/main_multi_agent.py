"""
MCP-driven multi-agent scenario for the large multi-agent topology.

The scenario keeps the same infrastructure and workload shape used in the
previous random/greedy experiments, but now adds two MCP-style agents:

- MonitoringAgent: inspects response, link, and node metrics every window.
- PlacementAgent: applies simple placement heuristics between windows.

The simulation is advanced through the service layer in actionable windows so
agents can observe and reconfigure the system at runtime.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import random
import statistics
import sys
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import networkx as nx
import pandas as pd

from yafs.distribution import deterministicDistributionStartPoint
from yafs.services import SimulationService
from yafs.transports import build_mcp_server

from tutorial_scenarios.multi_agent_scenario.main_random import (
    RandomMecUserBurstProcess,
    application_entry_messages,
    build_random_replica_definition,
    eligible_nodes,
    mec_worker_nodes,
    reduce_mec_worker_speed,
)


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


def build_parser() -> argparse.ArgumentParser:
    scenario_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to results_multi_agent under the scenario directory.",
    )
    parser.set_defaults(default_scenario_dir=scenario_dir)
    return parser


def build_config() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_CONFIG)


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


def summarize_payload(value: Any) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        summary: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(item, (str, int, float, bool)) or item is None:
                summary[key] = item
            elif isinstance(item, list):
                summary[key] = {"count": len(item)}
            elif isinstance(item, dict):
                summary[key] = {"keys": sorted(str(name) for name in item.keys())[:8]}
            else:
                summary[key] = str(type(item).__name__)
        return summary
    if isinstance(value, list):
        return {"count": len(value)}
    return value


class InteractionLogger:
    def __init__(self, service: SimulationService) -> None:
        self.service = service
        self.entries: list[dict[str, Any]] = []

    def _simulation_now(self, simulation_id: str | None) -> float | None:
        if not simulation_id:
            return None
        try:
            state = self.service.get_state(simulation_id)
        except Exception:
            return None
        return float(state.summary.now)

    def log_tool_call(
        self,
        *,
        actor: str,
        tool_name: str,
        simulation_id: str | None,
        request: Any,
        response: Any | None,
        ok: bool,
        error: str | None = None,
        wall_elapsed_s: float | None = None,
        before_now: float | None = None,
        after_now: float | None = None,
        window_index: int | None = None,
        note: str | None = None,
    ) -> None:
        self.entries.append(
            {
                "entry_type": "tool_call",
                "actor": actor,
                "tool_name": tool_name,
                "simulation_id": simulation_id,
                "simulation_now_before": before_now,
                "simulation_now_after": after_now,
                "window_index": window_index,
                "ok": ok,
                "error": error,
                "wall_elapsed_s": wall_elapsed_s,
                "request": summarize_payload(request),
                "response": summarize_payload(response),
                "note": note,
                "wall_time": time.time(),
            }
        )

    def log_message(
        self,
        *,
        actor: str,
        simulation_id: str | None,
        message_type: str,
        content: str,
        window_index: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.entries.append(
            {
                "entry_type": "agent_message",
                "actor": actor,
                "message_type": message_type,
                "content": content,
                "details": summarize_payload(details or {}),
                "simulation_id": simulation_id,
                "simulation_now": self._simulation_now(simulation_id),
                "window_index": window_index,
                "wall_time": time.time(),
            }
        )

    def write_jsonl(self, path: Path) -> None:
        lines = [json.dumps(item, ensure_ascii=True) for item in self.entries]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def write_markdown(self, path: Path) -> None:
        rows: list[list[str]] = []
        for index, item in enumerate(self.entries, start=1):
            if item["entry_type"] == "tool_call":
                rows.append(
                    [
                        str(index),
                        str(item.get("window_index", "-")),
                        f"{float(item.get('simulation_now_after') or item.get('simulation_now_before') or 0.0):.0f}",
                        str(item.get("actor", "-")),
                        f"tool:{item.get('tool_name', '-')}",
                        "ok" if item.get("ok") else "error",
                        str(item.get("note") or item.get("error") or "-"),
                    ]
                )
            else:
                rows.append(
                    [
                        str(index),
                        str(item.get("window_index", "-")),
                        f"{float(item.get('simulation_now') or 0.0):.0f}",
                        str(item.get("actor", "-")),
                        str(item.get("message_type", "-")),
                        "-",
                        str(item.get("content", "-")),
                    ]
                )
        header = "| # | Window | Sim time | Actor | Kind | Status | Detail |\n| --- | --- | --- | --- | --- | --- | --- |"
        body = "\n".join("| " + " | ".join(row) + " |" for row in rows) if rows else "| - | - | - | - | - | - | - |"
        path.write_text("# MCP Interaction Log\n\n" + header + "\n" + body + "\n", encoding="utf-8")


def resolve_results_trace_path(results_dir: Path, *, kind: str = "event") -> Path | None:
    if kind == "event":
        matches = sorted(
            [item for item in results_dir.glob("sim_trace*.csv") if not item.name.endswith("_link.csv")],
            key=lambda item: (item.stat().st_mtime, item.name),
        )
    else:
        matches = sorted(
            [item for item in results_dir.glob("sim_trace*_link.csv")],
            key=lambda item: (item.stat().st_mtime, item.name),
        )
    return matches[-1] if matches else None


class InProcessMcpClient:
    """
    Minimal in-process adapter that mirrors the MCP tool surface we use here.

    The agents interact with this client as if they were calling MCP tools.
    """

    def __init__(self, service: SimulationService, *, logger: InteractionLogger | None = None) -> None:
        self.service = service
        self.logger = logger

    def _call(
        self,
        tool_name: str,
        callback,
        *args,
        actor: str = "system",
        simulation_id: str | None = None,
        window_index: int | None = None,
        note: str | None = None,
        **kwargs,
    ):
        before_now = self.logger._simulation_now(simulation_id) if self.logger is not None else None
        started = time.time()
        try:
            response = _serialize(callback(*args, **kwargs))
        except Exception as exc:
            if self.logger is not None:
                self.logger.log_tool_call(
                    actor=actor,
                    tool_name=tool_name,
                    simulation_id=simulation_id,
                    request={"args": args, "kwargs": kwargs},
                    response=None,
                    ok=False,
                    error=str(exc),
                    wall_elapsed_s=time.time() - started,
                    before_now=before_now,
                    after_now=self.logger._simulation_now(simulation_id),
                    window_index=window_index,
                    note=note,
                )
            raise
        if self.logger is not None:
            self.logger.log_tool_call(
                actor=actor,
                tool_name=tool_name,
                simulation_id=simulation_id,
                request={"args": args, "kwargs": kwargs},
                response=response,
                ok=True,
                wall_elapsed_s=time.time() - started,
                before_now=before_now,
                after_now=self.logger._simulation_now(simulation_id),
                window_index=window_index,
                note=note,
            )
        return response

    def log_message(
        self,
        *,
        actor: str,
        simulation_id: str | None,
        message_type: str,
        content: str,
        window_index: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self.logger is None:
            return
        self.logger.log_message(
            actor=actor,
            simulation_id=simulation_id,
            message_type=message_type,
            content=content,
            window_index=window_index,
            details=details,
        )

    def create_simulation(self, *, actor: str = "system", note: str | None = None, **kwargs) -> dict[str, Any]:
        return self._call("create_simulation", self.service.create_simulation, actor=actor, note=note, **kwargs)

    def get_simulation_state(self, simulation_id: str, *, actor: str = "system", window_index: int | None = None) -> dict[str, Any]:
        return self._call("get_simulation_state", self.service.get_state, simulation_id, actor=actor, simulation_id=simulation_id, window_index=window_index)

    def get_simulation_application_metrics(
        self,
        simulation_id: str,
        *,
        actor: str = "MonitoringAgent",
        window_index: int | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        return self._call(
            "get_simulation_application_metrics",
            self.service.get_application_metrics,
            simulation_id,
            actor=actor,
            simulation_id=simulation_id,
            window_index=window_index,
            **kwargs,
        )

    def get_simulation_network_metrics(
        self,
        simulation_id: str,
        *,
        actor: str = "MonitoringAgent",
        window_index: int | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        return self._call(
            "get_simulation_network_metrics",
            self.service.get_network_metrics,
            simulation_id,
            actor=actor,
            simulation_id=simulation_id,
            window_index=window_index,
            **kwargs,
        )

    def list_simulation_nodes(self, simulation_id: str, *, actor: str = "system") -> list[dict[str, Any]]:
        return self._call("list_simulation_nodes", self.service.list_nodes, simulation_id, actor=actor, simulation_id=simulation_id)

    def list_simulation_users(self, simulation_id: str, *, actor: str = "PlacementAgent", window_index: int | None = None, **kwargs) -> dict[str, Any]:
        return self._call("list_simulation_users", self.service.list_users, simulation_id, actor=actor, simulation_id=simulation_id, window_index=window_index, **kwargs)

    def list_simulation_application_vnfs(
        self,
        simulation_id: str,
        app_id: str,
        *,
        actor: str = "PlacementAgent",
        window_index: int | None = None,
    ) -> dict[str, Any]:
        return self._call("list_simulation_application_vnfs", self.service.list_application_vnfs, simulation_id, app_id, actor=actor, simulation_id=simulation_id, window_index=window_index)

    def list_simulation_deployed_applications(self, simulation_id: str, *, actor: str = "system") -> list[Any]:
        return self._call("list_simulation_deployed_applications", self.service.list_deployed_applications, simulation_id, actor=actor, simulation_id=simulation_id)

    def list_simulation_node_placements(
        self,
        simulation_id: str,
        node_id: str,
        *,
        actor: str = "PlacementAgent",
        window_index: int | None = None,
    ) -> dict[str, Any]:
        return self._call("list_simulation_node_placements", self.service.list_node_placements, simulation_id, node_id, actor=actor, simulation_id=simulation_id, window_index=window_index)

    def deploy_application_vnfs(
        self,
        simulation_id: str,
        app_id: str | int,
        definition: dict[str, Any],
        *,
        actor: str = "system",
        window_index: int | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        return self._call("deploy_application_vnfs", self.service.deploy_application_vnfs, simulation_id, app_id, definition, actor=actor, simulation_id=simulation_id, window_index=window_index, note=note)

    def replicate_application_vnf(
        self,
        simulation_id: str,
        app_id: str | int,
        definition: dict[str, Any],
        *,
        actor: str = "PlacementAgent",
        window_index: int | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        return self._call("replicate_application_vnf", self.service.replicate_application_vnf, simulation_id, app_id, definition, actor=actor, simulation_id=simulation_id, window_index=window_index, note=note)

    def move_application_vnf(
        self,
        simulation_id: str,
        app_id: str | int,
        definition: dict[str, Any],
        *,
        actor: str = "PlacementAgent",
        window_index: int | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        return self._call("move_application_vnf", self.service.move_application_vnf, simulation_id, app_id, definition, actor=actor, simulation_id=simulation_id, window_index=window_index, note=note)

    def schedule_for(self, simulation_id: str, *, duration: float, step: float, actor: str = "system", window_index: int | None = None) -> dict[str, Any]:
        return self._call("schedule_for", self.service.schedule_for, simulation_id, duration=duration, step=step, actor=actor, simulation_id=simulation_id, window_index=window_index)

    def wait_until_ready(self, simulation_id: str, *, poll_interval: float = 0.05, actor: str = "system", window_index: int | None = None) -> dict[str, Any]:
        return self._call("wait_until_ready", self.service.wait_until_ready, simulation_id, poll_interval=poll_interval, actor=actor, simulation_id=simulation_id, window_index=window_index)

    def stop(self, simulation_id: str, *, actor: str = "system") -> dict[str, Any]:
        return self._call("stop_simulation", self.service.stop, simulation_id, actor=actor, simulation_id=simulation_id)


def canonical_edge(src: str, dst: str) -> tuple[str, str]:
    return (src, dst) if src <= dst else (dst, src)


def load_app_catalog(scenario_dir: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads((scenario_dir / "services.json").read_text(encoding="utf-8"))
    catalog: dict[str, dict[str, Any]] = {}
    for app_definition in payload:
        app_name = str(app_definition["name"])
        entry_module = None
        for message in app_definition.get("message", []):
            if str(message.get("s")) == "None":
                entry_module = str(message.get("d"))
                break
        catalog[app_name] = {
            "id": app_definition.get("id", app_name),
            "modules": [str(item["name"]) for item in app_definition.get("module", [])],
            "entry_module": entry_module,
            "latency_requirement": float(app_definition.get("latency_requirement", 0.0) or 0.0),
        }
    return catalog


def entry_messages_by_app(infrastructure) -> dict[str, str]:
    messages: dict[str, str] = {}
    for app_ref, message_name in application_entry_messages(infrastructure):
        app_name = str(infrastructure._resolve_app_name(app_ref))
        messages[app_name] = str(message_name)
    return messages


class HotspotUsersProcess:
    def __init__(
        self,
        *,
        app_ref: str | int,
        message: str,
        node_id: str,
        count: int,
        user_lambda: float,
        move_time: float | None = None,
        move_to: str | None = None,
        remove_time: float | None = None,
        remove_fraction: float = 0.0,
    ) -> None:
        self.app_ref = app_ref
        self.message = str(message)
        self.node_id = str(node_id)
        self.count = int(count)
        self.user_lambda = float(user_lambda)
        self.move_time = None if move_time is None else float(move_time)
        self.move_to = None if move_to is None else str(move_to)
        self.remove_time = None if remove_time is None else float(remove_time)
        self.remove_fraction = max(0.0, min(float(remove_fraction), 1.0))
        self.created = False
        self.moved = False
        self.removed = False
        self.user_des: list[int] = []

    def __call__(self, context) -> None:
        if not self.created:
            for _ in range(self.count):
                created = context.create_user(
                    app_ref=self.app_ref,
                    message=self.message,
                    node_id=self.node_id,
                    lambda_value=self.user_lambda,
                )
                self.user_des.append(int(created["des"]))
            self.created = True

        if (
            self.move_time is not None
            and self.move_to is not None
            and not self.moved
            and float(context.now) >= self.move_time
        ):
            remaining: list[int] = []
            for user_des in self.user_des:
                try:
                    context.move_user(user_des, self.move_to)
                except ValueError:
                    remaining.append(user_des)
                else:
                    remaining.append(user_des)
            self.user_des = remaining
            self.moved = True

        if (
            self.remove_time is not None
            and not self.removed
            and float(context.now) >= self.remove_time
        ):
            remove_count = int(round(len(self.user_des) * self.remove_fraction))
            remove_count = max(0, min(remove_count, len(self.user_des)))
            to_remove = set(self.user_des[:remove_count])
            for user_des in list(to_remove):
                try:
                    context.remove_user(user_des)
                except ValueError:
                    pass
            self.user_des = [user_des for user_des in self.user_des if user_des not in to_remove]
            self.removed = True


def register_hotspot_events(
    simulation,
    *,
    config: dict[str, Any],
    graph: nx.Graph,
    entry_messages: dict[str, str],
) -> int:
    registered = 0
    for index, event in enumerate(config.get("hotspot_events", [])):
        app_ref = event.get("app")
        if app_ref is None:
            raise ValueError("hotspot_users event requires an 'app'")
        app_name = str(simulation.infrastructure._resolve_app_name(app_ref))
        message = str(event.get("message") or entry_messages.get(app_name) or "")
        if not message:
            raise ValueError(f"hotspot_users event for '{app_name}' has no entry message")

        node_id = str(event.get("node") or "")
        if not node_id:
            raise ValueError("hotspot_users event requires a 'node'")
        if not graph.has_node(node_id):
            raise ValueError(f"hotspot_users target node does not exist: {node_id}")
        move_to = event.get("move_to")
        if move_to is not None and not graph.has_node(str(move_to)):
            raise ValueError(f"hotspot_users move target node does not exist: {move_to}")

        event_time = float(event.get("time", 0.0))
        interval = float(event.get("interval", config["simulation_duration"] + 1.0))
        if interval <= 0.0:
            raise ValueError("hotspot_users event interval must be positive")
        process = HotspotUsersProcess(
            app_ref=app_ref,
            message=message,
            node_id=node_id,
            count=int(event.get("count", 1)),
            user_lambda=float(event.get("user_lambda", config["user_lambda"])),
            move_time=event.get("move_time"),
            move_to=event.get("move_to"),
            remove_time=event.get("remove_time"),
            remove_fraction=float(event.get("remove_fraction", 0.0) or 0.0),
        )
        name = str(event.get("name") or f"HotspotUsers-{index}")
        distribution = deterministicDistributionStartPoint(
            event_time,
            interval,
            name=f"{name}-activation",
        )
        simulation.register_process(name, process, distribution)
        registered += 1
    return registered


def load_window_node_utilization(
    trace_path: Path,
    *,
    window_start: float,
    window_end: float,
) -> dict[str, float]:
    if not trace_path.exists():
        return {}
    frame = pd.read_csv(trace_path)
    if frame.empty:
        return {}
    comp = frame[frame["type"] == "COMP_M"].copy()
    if comp.empty:
        return {}
    comp["time_out"] = pd.to_numeric(comp["time_out"], errors="coerce")
    comp["time_in"] = pd.to_numeric(comp["time_in"], errors="coerce")
    comp = comp[(comp["time_out"] >= window_start) & (comp["time_out"] < window_end)].copy()
    if comp.empty:
        return {}
    comp["service_time"] = (comp["time_out"] - comp["time_in"]).clip(lower=0.0)
    duration = max(window_end - window_start, 1.0)
    grouped = (
        comp.groupby("TOPO.dst", dropna=False)["service_time"]
        .sum()
        .div(duration)
        .clip(lower=0.0)
    )
    return {str(node): float(value) for node, value in grouped.items()}


def load_window_link_utilization(
    trace_path: Path,
    *,
    window_start: float,
    window_end: float,
    graph: nx.Graph,
) -> dict[tuple[str, str], dict[str, float]]:
    if not trace_path.exists():
        return {}
    frame = pd.read_csv(trace_path)
    if frame.empty:
        return {}
    frame["ctime"] = pd.to_numeric(frame["ctime"], errors="coerce")
    frame["size"] = pd.to_numeric(frame["size"], errors="coerce")
    frame["latency"] = pd.to_numeric(frame["latency"], errors="coerce")
    frame["buffer"] = pd.to_numeric(frame["buffer"], errors="coerce")
    frame = frame[(frame["ctime"] >= window_start) & (frame["ctime"] < window_end)].copy()
    if frame.empty:
        return {}

    duration = max(window_end - window_start, 1.0)
    rows: dict[tuple[str, str], dict[str, float]] = {}
    grouped = (
        frame.groupby(["src", "dst"], dropna=False)
        .agg(
            messages=("message", "count"),
            total_size=("size", "sum"),
            latency_mean=("latency", "mean"),
            buffer_mean=("buffer", "mean"),
        )
        .reset_index()
    )
    for row in grouped.itertuples(index=False):
        edge = canonical_edge(str(row.src), str(row.dst))
        bw = float(graph.edges[edge].get("BW", 1.0) or 1.0) if graph.has_edge(*edge) else 1.0
        bandwidth_used = float(row.total_size or 0.0) / duration if duration > 0 else 0.0
        rows[edge] = {
            "messages": int(row.messages),
            "latency_mean": float(row.latency_mean or 0.0),
            "buffer_mean": float(row.buffer_mean or 0.0),
            "bandwidth_used": bandwidth_used,
            "bandwidth_available": bw,
            "utilization": bandwidth_used / bw if bw > 0.0 else 0.0,
        }
    return rows


class MonitoringAgent:
    def __init__(
        self,
        *,
        client: InProcessMcpClient,
        simulation_id: str,
        results_dir: Path,
        graph: nx.Graph,
        node_metadata: dict[str, dict[str, Any]],
        app_latency_requirements: dict[str, float],
        link_utilization_threshold: float = 0.00005,
        node_utilization_threshold: float = 0.25,
        overload_streak_windows: int = 2,
        egress_cost_per_gb: float = 0.02,
    ) -> None:
        self.client = client
        self.simulation_id = simulation_id
        self.results_dir = results_dir
        self.graph = graph
        self.node_metadata = node_metadata
        self.app_latency_requirements = {
            str(app_name): float(requirement)
            for app_name, requirement in app_latency_requirements.items()
            if float(requirement) > 0.0
        }
        self.link_utilization_threshold = float(link_utilization_threshold)
        self.node_utilization_threshold = float(node_utilization_threshold)
        self.overload_streak_windows = int(overload_streak_windows)
        self.egress_cost_per_gb = float(egress_cost_per_gb)
        self.node_overload_streaks: dict[str, int] = {}

    def observe(self, *, window_start: float, window_end: float, window_index: int) -> dict[str, Any]:
        app_metrics_response = self.client.get_simulation_application_metrics(
            self.simulation_id,
            actor="MonitoringAgent",
            window_index=window_index,
            from_time=window_start,
            to_time=window_end,
            reference_time=0.0,
            time_column="end_time",
            include_return_messages=True,
            egress_cost_per_gb=self.egress_cost_per_gb,
        )
        app_items = app_metrics_response.get("items", [])
        network_summary = self.client.get_simulation_network_metrics(
            self.simulation_id,
            actor="MonitoringAgent",
            window_index=window_index,
        )
        trace_path = resolve_results_trace_path(self.results_dir, kind="event")
        trace_link_path = resolve_results_trace_path(self.results_dir, kind="link")
        node_utilization = load_window_node_utilization(
            trace_path or self.results_dir / "missing_sim_trace.csv",
            window_start=window_start,
            window_end=window_end,
        )
        link_utilization = load_window_link_utilization(
            trace_link_path or self.results_dir / "missing_sim_trace_link.csv",
            window_start=window_start,
            window_end=window_end,
            graph=self.graph,
        )

        incidents: list[dict[str, Any]] = []
        apps_by_name = {str(item["app"]): item for item in app_items}
        for app_name, item in apps_by_name.items():
            raw_p95 = item.get("response_p95", math.nan)
            p95 = float(raw_p95) if raw_p95 is not None and math.isfinite(float(raw_p95)) else math.nan
            unsuccessful = int(item.get("requests_unsuccessful", 0) or 0)
            latency_requirement = self.app_latency_requirements.get(app_name)
            if latency_requirement is not None and math.isfinite(p95) and p95 > latency_requirement:
                incidents.append(
                    {
                        "type": "degradation",
                        "app": app_name,
                        "severity": "high" if p95 > 1.5 * latency_requirement else "medium",
                        "reason": (
                            f"response_p95={p95:.2f} exceeds "
                            f"latency_requirement={latency_requirement:.2f}"
                        ),
                    }
                )
            if unsuccessful > 0:
                incidents.append(
                    {
                        "type": "incident",
                        "app": app_name,
                        "severity": "high",
                        "reason": f"requests_unsuccessful={unsuccessful}",
                    }
                )

        congested_links: list[dict[str, Any]] = []
        for edge, info in link_utilization.items():
            utilization = float(info.get("utilization", 0.0) or 0.0)
            if utilization > self.link_utilization_threshold:
                incident = {
                    "type": "congestion",
                    "edge": edge,
                    "severity": "medium",
                    "reason": f"link_utilization={utilization:.6f}",
                }
                incidents.append(incident)
                congested_links.append(incident)

        overloaded_nodes: list[dict[str, Any]] = []
        next_streaks: dict[str, int] = {}
        for node_name, utilization in node_utilization.items():
            if utilization > self.node_utilization_threshold:
                streak = self.node_overload_streaks.get(node_name, 0) + 1
                next_streaks[node_name] = streak
                if streak >= self.overload_streak_windows:
                    incident = {
                        "type": "overload",
                        "node": node_name,
                        "severity": "high" if utilization > 0.5 else "medium",
                        "reason": f"node_utilization={utilization:.3f} streak={streak}",
                    }
                    incidents.append(incident)
                    overloaded_nodes.append(incident)
            else:
                next_streaks[node_name] = 0
        self.node_overload_streaks = next_streaks

        self.client.log_message(
            actor="MonitoringAgent",
            simulation_id=self.simulation_id,
            message_type="assessment",
            content=(
                f"window={window_index} incidents={len(incidents)} "
                f"overloaded_nodes={len(overloaded_nodes)} congested_links={len(congested_links)}"
            ),
            window_index=window_index,
            details={
                "window_start": window_start,
                "window_end": window_end,
                "incident_types": [item["type"] for item in incidents],
            },
        )

        return {
            "window_index": window_index,
            "window_start": window_start,
            "window_end": window_end,
            "app_metrics": app_items,
            "apps_by_name": apps_by_name,
            "network_summary": network_summary,
            "node_utilization": node_utilization,
            "link_utilization": link_utilization,
            "incidents": incidents,
            "overloaded_nodes": overloaded_nodes,
            "congested_links": congested_links,
        }


class PlacementAgent:
    def __init__(
        self,
        *,
        client: InProcessMcpClient,
        simulation_id: str,
        graph: nx.Graph,
        app_catalog: dict[str, dict[str, Any]],
        node_metadata: dict[str, dict[str, Any]],
        action_budget_per_window: int = 4,
        placement_cost_budget: float = 20.0,
        prefer_overload_when_present: bool = False,
    ) -> None:
        self.client = client
        self.simulation_id = simulation_id
        self.graph = graph
        self.app_catalog = app_catalog
        self.node_metadata = node_metadata
        self.action_budget_per_window = int(action_budget_per_window)
        self.placement_cost_budget = float(placement_cost_budget)
        self.prefer_overload_when_present = bool(prefer_overload_when_present)
        self.last_app_action_window: dict[str, int] = {}

    def _total_placement_cost(self, snapshot: dict[str, Any]) -> float:
        return sum(float(item.get("placement_cost", 0.0) or 0.0) for item in snapshot["app_metrics"])

    def _select_strategy(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        incident_types = [str(item.get("type")) for item in snapshot["incidents"]]
        congestion_count = incident_types.count("congestion")
        overload_count = incident_types.count("overload")
        degraded_count = sum(1 for item in incident_types if item in {"degradation", "incident"})
        total_cost = self._total_placement_cost(snapshot)

        if total_cost > self.placement_cost_budget:
            return {
                "name": "cost",
                "reason": f"placement_cost={total_cost:.4f} exceeds budget={self.placement_cost_budget:.4f}",
                "preferred_cluster_roles": ("EDC", "CDC", "MEC"),
                "replication_cost_weight": 60.0,
                "replication_utilization_weight": 25.0,
                "prefer_regional_nodes": True,
                "prioritize_moves": False,
                "prioritize_consolidation": True,
            }

        if overload_count > 0 and (
            self.prefer_overload_when_present or overload_count >= congestion_count
        ):
            return {
                "name": "overload",
                "reason": f"overloaded_nodes={overload_count} dominate the current window",
                "preferred_cluster_roles": ("MEC", "EDC", "CDC"),
                "replication_cost_weight": 20.0,
                "replication_utilization_weight": 55.0,
                "prefer_regional_nodes": True,
                "prioritize_moves": True,
                "prioritize_consolidation": False,
            }

        if congestion_count > 0 or degraded_count > 0:
            return {
                "name": "congestion",
                "reason": (
                    f"congested_links={congestion_count}, degraded_or_incident_apps={degraded_count}"
                ),
                "preferred_cluster_roles": ("MEC", "EDC"),
                "replication_cost_weight": 12.0,
                "replication_utilization_weight": 25.0,
                "prefer_regional_nodes": True,
                "prioritize_moves": False,
                "prioritize_consolidation": False,
            }

        return {
            "name": "balanced",
            "reason": "no dominant condition detected",
            "preferred_cluster_roles": ("MEC", "EDC", "CDC"),
            "replication_cost_weight": 20.0,
            "replication_utilization_weight": 35.0,
            "prefer_regional_nodes": True,
            "prioritize_moves": False,
            "prioritize_consolidation": False,
        }

    def _current_users_for_app(self, app_name: str, *, window_index: int | None = None) -> list[dict[str, Any]]:
        payload = self.client.list_simulation_users(
            self.simulation_id,
            app_id=app_name,
            actor="PlacementAgent",
            window_index=window_index,
        )
        return payload.get("users", [])

    def _dominant_region(self, users: list[dict[str, Any]]) -> str | None:
        if not users:
            return None
        counts: dict[str, int] = {}
        for item in users:
            node_name = str(item.get("node"))
            region = str(self.node_metadata.get(node_name, {}).get("cluster_region"))
            counts[region] = counts.get(region, 0) + 1
        return max(counts.items(), key=lambda item: (item[1], item[0]))[0] if counts else None

    def _weighted_distance(self, source: str, target: str) -> float:
        try:
            return float(nx.shortest_path_length(self.graph, source=source, target=target, weight="PR"))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return float("inf")

    def _choose_best_node(
        self,
        *,
        users: list[dict[str, Any]],
        preferred_region: str | None,
        excluded_nodes: set[str],
        node_utilization: dict[str, float],
        preferred_cluster_roles: tuple[str, ...] = ("MEC", "EDC", "CDC"),
        utilization_weight: float = 35.0,
        cost_weight: float = 20.0,
        prefer_regional_nodes: bool = True,
    ) -> str | None:
        user_nodes = [str(item["node"]) for item in users if str(item.get("node")) in self.node_metadata]
        if not user_nodes:
            return None

        candidates = [
            node_name
            for node_name, info in self.node_metadata.items()
            if str(info.get("node_role")) == "worker"
            and str(info.get("cluster_role")) in preferred_cluster_roles
            and node_name not in excluded_nodes
        ]
        if prefer_regional_nodes and preferred_region is not None:
            regional_candidates = [
                node_name
                for node_name in candidates
                if str(self.node_metadata[node_name].get("cluster_region")) == preferred_region
            ]
            if regional_candidates:
                candidates = regional_candidates
        if not candidates:
            return None

        ranked: list[tuple[float, str]] = []
        for node_name in candidates:
            distances = [self._weighted_distance(user_node, node_name) for user_node in user_nodes]
            finite_distances = [value for value in distances if math.isfinite(value)]
            if not finite_distances:
                continue
            mean_distance = statistics.fmean(finite_distances)
            utilization = float(node_utilization.get(node_name, 0.0) or 0.0)
            node_cost = float(self.node_metadata[node_name].get("cost", 0.0) or 0.0)
            region_penalty = 0.0
            if (
                prefer_regional_nodes
                and preferred_region is not None
                and str(self.node_metadata[node_name].get("cluster_region")) != preferred_region
            ):
                region_penalty = 25.0
            score = mean_distance + (utilization_weight * utilization) + (cost_weight * node_cost) + region_penalty
            ranked.append((score, node_name))

        if not ranked:
            return None
        ranked.sort(key=lambda item: (item[0], item[1]))
        return ranked[0][1]

    def _replicate_app_chain(
        self,
        *,
        app_name: str,
        target_node: str,
        window_index: int | None = None,
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        vnf_report = self.client.list_simulation_application_vnfs(
            self.simulation_id,
            app_name,
            actor="PlacementAgent",
            window_index=window_index,
        )
        existing_by_vnf = {
            str(item["vnf"]): {str(node) for node in item.get("nodes", [])}
            for item in vnf_report.get("vnfs", [])
        }
        for module_name in self.app_catalog[app_name]["modules"]:
            if target_node in existing_by_vnf.get(module_name, set()):
                continue
            try:
                response = self.client.replicate_application_vnf(
                    self.simulation_id,
                    app_name,
                    {"module_name": module_name, "to_node": target_node},
                    actor="PlacementAgent",
                    window_index=window_index,
                    note=f"replicate {module_name} for {app_name}",
                )
            except Exception as exc:
                actions.append(
                    {
                        "type": "replicate_failed",
                        "app": app_name,
                        "module": module_name,
                        "target_node": target_node,
                        "reason": str(exc),
                    }
                )
                continue
            actions.append(
                {
                    "type": "replicate",
                    "app": app_name,
                    "module": module_name,
                    "target_node": target_node,
                    "result": response.get("status", "unknown"),
                }
            )
        return actions

    def _move_from_overloaded_node(
        self,
        *,
        source_node: str,
        snapshot: dict[str, Any],
        strategy: dict[str, Any],
        window_index: int | None = None,
    ) -> dict[str, Any] | None:
        placements_payload = self.client.list_simulation_node_placements(
            self.simulation_id,
            source_node,
            actor="PlacementAgent",
            window_index=window_index,
        )
        placements = placements_payload.get("placements", [])
        if not placements:
            return None

        apps_by_name = snapshot["apps_by_name"]
        placements = sorted(
            placements,
            key=lambda item: (
                -float(apps_by_name.get(str(item["app"]), {}).get("response_p95", 0.0) or 0.0),
                str(item["app"]),
                str(item["vnf"]),
            ),
        )
        chosen = placements[0]
        app_name = str(chosen["app"])
        users = self._current_users_for_app(app_name, window_index=window_index)
        preferred_region = str(self.node_metadata.get(source_node, {}).get("cluster_region"))
        target_node = self._choose_best_node(
            users=users,
            preferred_region=preferred_region,
            excluded_nodes={source_node},
            node_utilization=snapshot["node_utilization"],
            preferred_cluster_roles=tuple(strategy["preferred_cluster_roles"]),
            utilization_weight=float(strategy["replication_utilization_weight"]),
            cost_weight=float(strategy["replication_cost_weight"]),
            prefer_regional_nodes=bool(strategy["prefer_regional_nodes"]),
        )
        if target_node is None:
            return None
        try:
            response = self.client.move_application_vnf(
                self.simulation_id,
                app_name,
                {
                    "module_name": str(chosen["vnf"]),
                    "from_node": source_node,
                    "to_node": target_node,
                },
                actor="PlacementAgent",
                window_index=window_index,
                note=f"move {chosen['vnf']} away from overloaded node",
            )
        except Exception as exc:
            return {
                "type": "move_failed",
                "app": app_name,
                "module": str(chosen["vnf"]),
                "from_node": source_node,
                "to_node": target_node,
                "reason": str(exc),
            }
        return {
            "type": "move",
            "app": app_name,
            "module": str(chosen["vnf"]),
            "from_node": source_node,
            "to_node": target_node,
            "result": response.get("status", "unknown"),
        }

    def _cheaper_consolidation_target(
        self,
        *,
        app_name: str,
        module_name: str,
        source_node: str,
        existing_nodes: set[str],
        snapshot: dict[str, Any],
    ) -> tuple[str, float] | None:
        source_info = self.node_metadata.get(source_node, {})
        source_cost = float(source_info.get("cost", 0.0) or 0.0)
        source_region = str(source_info.get("cluster_region"))
        candidates: list[tuple[int, int, float, float, str]] = []
        role_order = {"EDC": 0, "CDC": 1}

        for node_name, info in self.node_metadata.items():
            if node_name in existing_nodes or node_name == source_node:
                continue
            if str(info.get("node_role")) != "worker":
                continue
            cluster_role = str(info.get("cluster_role"))
            if cluster_role not in role_order:
                continue
            node_cost = float(info.get("cost", 0.0) or 0.0)
            if node_cost >= source_cost:
                continue
            region_penalty = 0 if str(info.get("cluster_region")) == source_region else 1
            candidates.append(
                (
                    role_order[cluster_role],
                    region_penalty,
                    float(snapshot["node_utilization"].get(node_name, 0.0) or 0.0),
                    node_cost,
                    node_name,
                )
            )

        if not candidates:
            return None
        candidates.sort()
        target_node = candidates[0][-1]
        target_cost = float(self.node_metadata[target_node].get("cost", 0.0) or 0.0)
        return target_node, source_cost - target_cost

    def _maybe_consolidate_cost(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        total_cost = self._total_placement_cost(snapshot)
        if total_cost <= self.placement_cost_budget:
            return None

        candidates: list[tuple[float, float, str, str, str, str, float]] = []
        apps_by_name = snapshot["apps_by_name"]
        for app_name in sorted(self.app_catalog):
            report = self.client.list_simulation_application_vnfs(
                self.simulation_id,
                app_name,
                actor="PlacementAgent",
                window_index=snapshot.get("window_index"),
            )
            app_p95 = float(apps_by_name.get(app_name, {}).get("response_p95", 0.0) or 0.0)
            for item in report.get("vnfs", []):
                module_name = str(item.get("vnf"))
                existing_nodes = {str(node) for node in item.get("nodes", [])}
                for deployment in item.get("deployments", []):
                    source_node = str(deployment.get("node"))
                    source_info = self.node_metadata.get(source_node, {})
                    if str(source_info.get("cluster_role")) != "MEC":
                        continue
                    target = self._cheaper_consolidation_target(
                        app_name=app_name,
                        module_name=module_name,
                        source_node=source_node,
                        existing_nodes=existing_nodes,
                        snapshot=snapshot,
                    )
                    if target is None:
                        continue
                    target_node, saving = target
                    candidates.append(
                        (
                            app_p95,
                            -saving,
                            app_name,
                            module_name,
                            source_node,
                            target_node,
                            saving,
                        )
                    )

        if not candidates:
            return None

        _, _, target_app, module_name, source_node, target_node, saving = sorted(candidates)[0]
        try:
            response = self.client.move_application_vnf(
                self.simulation_id,
                target_app,
                {
                    "module_name": module_name,
                    "from_node": source_node,
                    "to_node": target_node,
                },
                actor="PlacementAgent",
                window_index=snapshot.get("window_index"),
                note="consolidate VNF due to placement-cost budget",
            )
        except Exception as exc:
            return {
                "type": "consolidation_failed",
                "app": target_app,
                "module": module_name,
                "from_node": source_node,
                "to_node": target_node,
                "reason": str(exc),
            }
        return {
            "type": "consolidate",
            "app": target_app,
            "module": module_name,
            "from_node": source_node,
            "to_node": target_node,
            "estimated_saving": saving,
            "result": response.get("status", "unknown"),
        }

    def act(self, *, snapshot: dict[str, Any], window_index: int) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        apps_by_name = snapshot["apps_by_name"]
        strategy = self._select_strategy(snapshot)
        degraded_apps = sorted(
            {
                str(item["app"])
                for item in snapshot["incidents"]
                if item.get("type") in {"degradation", "incident"} and item.get("app") in self.app_catalog
            }
        )

        if bool(strategy["prioritize_moves"]):
            for incident in snapshot["overloaded_nodes"]:
                if len(actions) >= self.action_budget_per_window:
                    break
                action = self._move_from_overloaded_node(
                    source_node=str(incident["node"]),
                    snapshot=snapshot,
                    strategy=strategy,
                    window_index=window_index,
                )
                if action is not None:
                    actions.append(action)

        if bool(strategy["prioritize_consolidation"]) and len(actions) < self.action_budget_per_window:
            consolidation = self._maybe_consolidate_cost(snapshot)
            if consolidation is not None:
                actions.append(consolidation)

        for app_name in degraded_apps:
            if len(actions) >= self.action_budget_per_window:
                break
            if self.last_app_action_window.get(app_name) == window_index:
                continue
            users = self._current_users_for_app(app_name, window_index=window_index)
            if not users:
                continue
            dominant_region = self._dominant_region(users)
            vnf_report = self.client.list_simulation_application_vnfs(
                self.simulation_id,
                app_name,
                actor="PlacementAgent",
                window_index=window_index,
            )
            excluded_nodes = {
                str(node)
                for item in vnf_report.get("vnfs", [])
                for node in item.get("nodes", [])
            }
            target_node = self._choose_best_node(
                users=users,
                preferred_region=dominant_region,
                excluded_nodes=excluded_nodes,
                node_utilization=snapshot["node_utilization"],
                preferred_cluster_roles=tuple(strategy["preferred_cluster_roles"]),
                utilization_weight=float(strategy["replication_utilization_weight"]),
                cost_weight=float(strategy["replication_cost_weight"]),
                prefer_regional_nodes=bool(strategy["prefer_regional_nodes"]),
            )
            if target_node is None:
                continue
            chain_actions = self._replicate_app_chain(
                app_name=app_name,
                target_node=target_node,
                window_index=window_index,
            )
            if chain_actions:
                actions.extend(chain_actions)
                self.last_app_action_window[app_name] = window_index

        if not bool(strategy["prioritize_moves"]):
            for incident in snapshot["overloaded_nodes"]:
                if len(actions) >= self.action_budget_per_window:
                    break
                action = self._move_from_overloaded_node(
                    source_node=str(incident["node"]),
                    snapshot=snapshot,
                    strategy=strategy,
                    window_index=window_index,
                )
                if action is not None:
                    actions.append(action)

        if not bool(strategy["prioritize_consolidation"]) and len(actions) < self.action_budget_per_window:
            consolidation = self._maybe_consolidate_cost(snapshot)
            if consolidation is not None:
                actions.append(consolidation)

        self.client.log_message(
            actor="PlacementAgent",
            simulation_id=self.simulation_id,
            message_type="decision",
            content=(
                f"window={window_index} strategy={strategy['name']} "
                f"actions={len(actions[: self.action_budget_per_window])}"
            ),
            window_index=window_index,
            details={
                "strategy": strategy,
                "incident_count": len(snapshot["incidents"]),
                "actions": actions[: self.action_budget_per_window],
            },
        )

        return actions[: self.action_budget_per_window]


def try_build_transport(service: SimulationService) -> str:
    try:
        build_mcp_server(service, server_name="multi-agent-mcp")
        return "FastMCP server available"
    except Exception as exc:
        return f"in-process MCP adapter ({exc})"


def write_report(
    *,
    report_path: Path,
    config: dict[str, Any],
    transport_mode: str,
    window_logs: list[dict[str, Any]],
    final_metrics: list[dict[str, Any]],
) -> None:
    def table(headers: list[str], rows: list[list[str]]) -> str:
        head = "| " + " | ".join(headers) + " |"
        sep = "| " + " | ".join(["---"] * len(headers)) + " |"
        body = ["| " + " | ".join(row) + " |" for row in rows]
        return "\n".join([head, sep, *body])

    window_rows: list[list[str]] = []
    action_rows: list[list[str]] = []
    for item in window_logs:
        window_rows.append(
            [
                str(item["window_index"]),
                f"{item['window_start']:.0f}",
                f"{item['window_end']:.0f}",
                str(item["incident_count"]),
                str(item["action_count"]),
                str(item["top_app"] or "-"),
            ]
        )
        for action in item["actions"]:
            action_rows.append(
                [
                    str(item["window_index"]),
                    str(action.get("type", "-")),
                    str(action.get("app", "-")),
                    str(action.get("module", "-")),
                    str(action.get("from_node", "-")),
                    str(action.get("to_node", action.get("target_node", "-"))),
                ]
            )

    final_rows = [
        [
            str(item.get("app")),
            str(int(item.get("requests_total", 0) or 0)),
            str(int(item.get("requests_successful", 0) or 0)),
            str(int(item.get("requests_unsuccessful", 0) or 0)),
            f"{float(item.get('response_p95', 0.0) or 0.0):.2f}",
            f"{float(item.get('placement_cost', 0.0) or 0.0):.4f}",
            f"{float(item.get('egress_cost', 0.0) or 0.0):.4f}",
            f"{float(item.get('total_cost', 0.0) or 0.0):.4f}",
        ]
        for item in final_metrics
    ]

    content = "\n".join(
        [
            "# Multi-Agent MCP Scenario Report",
            "",
            "## Configuration",
            "",
            *[f"- {key}: `{value}`" for key, value in config.items()],
            f"- transport_mode: `{transport_mode}`",
            "",
            "## Window Summary",
            "",
            table(
                ["Window", "Start", "End", "Incidents", "Actions", "Top app by p95"],
                window_rows or [["-", "-", "-", "0", "0", "-"]],
            ),
            "",
            "## Placement Actions",
            "",
            table(
                ["Window", "Type", "App", "Module", "From", "To"],
                action_rows or [["-", "-", "-", "-", "-", "-"]],
            ),
            "",
            "## Final Metrics",
            "",
            table(
                [
                    "App",
                    "Requests total",
                    "Successful",
                    "Unsuccessful",
                    "Response p95",
                    "Placement cost",
                    "Egress cost",
                    "Total cost",
                ],
                final_rows or [["-", "0", "0", "0", "0.00", "0.0000", "0.0000", "0.0000"]],
            ),
            "",
        ]
    )
    report_path.write_text(content, encoding="utf-8")


def write_final_snapshots(
    *,
    snapshot_dir: Path,
    client: InProcessMcpClient,
    simulation_id: str,
    node_metadata: dict[str, dict[str, Any]],
    final_metrics: list[dict[str, Any]],
) -> None:
    deployed_apps = client.list_simulation_deployed_applications(simulation_id)
    placement_rows: list[dict[str, Any]] = []
    for app_name in deployed_apps:
        report = client.list_simulation_application_vnfs(simulation_id, str(app_name))
        for vnf_item in report.get("vnfs", []):
            for deployment in vnf_item.get("deployments", []):
                node_name = str(deployment.get("node"))
                metadata = node_metadata.get(node_name, {})
                placement_rows.append(
                    {
                        "app": str(report.get("app")),
                        "base_app": str(report.get("app")).split("::")[0],
                        "vnf": str(vnf_item.get("vnf")),
                        "des": deployment.get("des"),
                        "node": node_name,
                        "cluster": metadata.get("cluster"),
                        "cluster_role": metadata.get("cluster_role"),
                        "cluster_region": metadata.get("cluster_region"),
                        "node_cost": float(metadata.get("cost", 0.0) or 0.0),
                    }
                )

    (snapshot_dir / "final_application_metrics.json").write_text(
        json.dumps(final_metrics, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    (snapshot_dir / "final_placements.json").write_text(
        json.dumps(placement_rows, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def write_window_metrics(snapshot_dir: Path, window_logs: list[dict[str, Any]]) -> None:
    (snapshot_dir / "window_metrics.json").write_text(
        json.dumps(window_logs, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def main() -> None:
    args = build_parser().parse_args()
    scenario_dir = Path(args.default_scenario_dir)
    config = build_config()
    results_dir = args.results_dir or (scenario_dir / "results_multi_agent")
    results_dir.mkdir(parents=True, exist_ok=True)

    simulation_duration = (
        float(config["activation_interval"]) * float(config["activation_count"])
        + float(config["post_activation_tail"])
    )
    config["simulation_duration"] = simulation_duration

    service = SimulationService(default_results_root=results_dir)
    transport_mode = try_build_transport(service)
    interaction_logger = InteractionLogger(service)
    client = InProcessMcpClient(service, logger=interaction_logger)

    state = client.create_simulation(
        actor="system",
        note="initialize multi-agent simulation",
        scenario_path=scenario_dir,
        results_path=results_dir,
        seed=int(config["seed"]),
        name="multi-agent-mcp",
        placement_definition_path="empty_placements.json",
        users_definition_path="empty_users.json",
    )
    simulation_id = str(state["summary"]["id"])

    managed = service.registry.require(simulation_id)
    simulation = managed.simulation
    updated_mec_nodes = reduce_mec_worker_speed(
        simulation,
        mec_worker_ipt=float(config["mec_worker_ipt"]),
    )

    app_catalog = load_app_catalog(scenario_dir)
    config["app_latency_requirements"] = {
        app_name: float(app_info.get("latency_requirement", 0.0) or 0.0)
        for app_name, app_info in app_catalog.items()
    }
    node_rows = simulation.list_nodes()
    node_metadata = {
        str(item["node"]): {
            "cluster": item.get("cluster"),
            "cluster_role": item.get("cluster_role"),
            "cluster_region": item.get("cluster_region"),
            "node_role": item.get("node_role"),
            "cost": float(simulation.infrastructure.topology.G.nodes[str(item["node"])].get("COST", 0.0) or 0.0),
        }
        for item in node_rows
    }
    graph = simulation.infrastructure.topology.G

    user_nodes = mec_worker_nodes(simulation)
    if not user_nodes:
        raise RuntimeError("No MEC worker nodes are available for user placement")

    app_refs = [item.get("id", item["name"]) for item in simulation.infrastructure.service_definitions_data]
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
        client.deploy_application_vnfs(
            simulation_id,
            app_ref,
            definition,
            actor="system",
            note=f"initial random replica {replica_index}",
        )

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
    simulation.register_process("McpMultiAgentUserBurst", user_process, user_distribution)
    registered_hotspot_events = register_hotspot_events(
        simulation,
        config=config,
        graph=graph,
        entry_messages=entry_messages_by_app(simulation.infrastructure),
    )

    monitoring_agent = MonitoringAgent(
        client=client,
        simulation_id=simulation_id,
        results_dir=results_dir,
        graph=graph,
        node_metadata=node_metadata,
        app_latency_requirements=config["app_latency_requirements"],
        link_utilization_threshold=float(config["link_utilization_threshold"]),
        node_utilization_threshold=float(config["node_utilization_threshold"]),
        overload_streak_windows=int(config["overload_streak_windows"]),
        egress_cost_per_gb=float(config["egress_cost_per_gb"]),
    )
    placement_agent = PlacementAgent(
        client=client,
        simulation_id=simulation_id,
        graph=graph,
        app_catalog=app_catalog,
        node_metadata=node_metadata,
        action_budget_per_window=int(config["action_budget_per_window"]),
        placement_cost_budget=float(config["placement_cost_budget"]),
        prefer_overload_when_present=bool(config["prefer_overload_when_present"]),
    )

    window_logs: list[dict[str, Any]] = []
    window_index = 0
    current_time = 0.0
    start_time = time.time()
    try:
        while current_time < simulation_duration:
            duration = min(float(config["window_duration"]), simulation_duration - current_time)
            client.schedule_for(
                simulation_id,
                duration=duration,
                step=float(config["step"]),
                actor="system",
                window_index=window_index,
            )
            ready_state = client.wait_until_ready(
                simulation_id,
                poll_interval=0.02,
                actor="system",
                window_index=window_index,
            )
            now = float(ready_state["summary"]["now"])
            snapshot = monitoring_agent.observe(
                window_start=current_time,
                window_end=now,
                window_index=window_index,
            )
            actions = placement_agent.act(snapshot=snapshot, window_index=window_index)
            placement_strategy = "unknown"
            for entry in reversed(interaction_logger.entries):
                if (
                    entry.get("entry_type") == "agent_message"
                    and entry.get("actor") == "PlacementAgent"
                    and int(entry.get("window_index", -1)) == window_index
                ):
                    content = str(entry.get("content") or "")
                    marker = "strategy="
                    if marker in content:
                        placement_strategy = content.split(marker, 1)[1].split()[0].strip()
                    break
            top_app = None
            if snapshot["app_metrics"]:
                sorted_apps = sorted(
                    snapshot["app_metrics"],
                    key=lambda item: float(item.get("response_p95", 0.0) or 0.0),
                    reverse=True,
                )
                top_app = str(sorted_apps[0]["app"])
            window_logs.append(
                {
                    "window_index": window_index,
                    "window_start": current_time,
                    "window_end": now,
                    "incident_count": len(snapshot["incidents"]),
                    "congested_link_count": len(snapshot["congested_links"]),
                    "overloaded_node_count": len(snapshot["overloaded_nodes"]),
                    "placement_cost": sum(
                        float(item.get("placement_cost", 0.0) or 0.0) for item in snapshot["app_metrics"]
                    ),
                    "placement_strategy": placement_strategy,
                    "action_count": len(actions),
                    "top_app": top_app,
                    "actions": actions,
                }
            )
            current_time = now
            window_index += 1
    finally:
        client.stop(simulation_id, actor="system")

    final_metrics = client.get_simulation_application_metrics(
        simulation_id,
        from_time=0.0,
        to_time=simulation_duration,
        reference_time=0.0,
        time_column="end_time",
        include_return_messages=True,
        egress_cost_per_gb=float(config["egress_cost_per_gb"]),
    ).get("items", [])

    report_path = results_dir / "multi_agent_mcp_report.md"
    write_report(
        report_path=report_path,
        config=config | {"updated_mec_nodes": updated_mec_nodes, "registered_hotspot_events": registered_hotspot_events},
        transport_mode=transport_mode,
        window_logs=window_logs,
        final_metrics=final_metrics,
    )
    write_final_snapshots(
        snapshot_dir=results_dir,
        client=client,
        simulation_id=simulation_id,
        node_metadata=node_metadata,
        final_metrics=final_metrics,
    )
    write_window_metrics(results_dir, window_logs)
    interaction_logger.write_jsonl(results_dir / "mcp_interactions.jsonl")
    interaction_logger.write_markdown(results_dir / "mcp_interactions.md")

    print(f"\n--- {time.time() - start_time:.2f} seconds ---")
    print("Simulation Done!")
    print(f"simulation_id={simulation_id}")
    print(f"transport_mode={transport_mode}")
    print(f"MEC worker IPT configured to {config['mec_worker_ipt']:.1f} on {updated_mec_nodes} nodes")
    print(f"registered_hotspot_events={registered_hotspot_events}")
    print(f"windows_executed={len(window_logs)}")
    print(f"report={report_path}")
    print(f"mcp_log={results_dir / 'mcp_interactions.md'}")
    print("\nFinal application metrics:")
    for item in final_metrics:
        print(
            f"  app={item['app']} "
            f"requests_total={int(item.get('requests_total', 0) or 0)} "
            f"successful={int(item.get('requests_successful', 0) or 0)} "
            f"unsuccessful={int(item.get('requests_unsuccessful', 0) or 0)} "
            f"response_p95={float(item.get('response_p95', 0.0) or 0.0):.2f} "
            f"placement_cost={float(item.get('placement_cost', 0.0) or 0.0):.4f} "
            f"total_cost={float(item.get('total_cost', 0.0) or 0.0):.4f}"
        )


if __name__ == "__main__":
    main()
