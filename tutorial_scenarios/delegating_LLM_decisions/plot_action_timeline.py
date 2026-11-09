"""Plot model actions along simulation time.

Stacked bars count actions inside each time window:

    uv run python tutorial_scenarios/delegating_LLM_decisions/plot_action_timeline.py \
        tutorial_scenarios/delegating_LLM_decisions/results/20261007-165027

Category lanes follow the placement profile: Inventory, Placement, Analyst,
and Controller. Each tool keeps its own marker. A call on a forked
simulation carries a superscript, starting at 2; the parent simulation
is unmarked. A scheduled controller block, such as
``wait_simulation_until_ready``, is a horizontal arrow on that
simulation's own clock:

    uv run python tutorial_scenarios/delegating_LLM_decisions/plot_action_timeline.py \
        --style categories \
        tutorial_scenarios/delegating_LLM_decisions/results/20261008-100136

Hide that legend with ``--no-legend``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from yafs.transports.mcp_server import mcp_tool_group


WINDOW_DURATION = 200.0
SIMULATION_END = 5000.0

ACTION_LABELS = {
    "replicate": "Replicate VNF",
    "move_vnf": "Move VNF",
    "remove_vnf": "Remove VNF",
    "deploy": "Deploy VNFs",
    "update_user_lambda": "Update user lambda",
    "update_app_lambda": "Update application lambda",
    "move_users": "Move users",
}

ACTION_COLORS = {
    "replicate": "#4C78A8",
    "move_vnf": "#F58518",
    "remove_vnf": "#E45756",
    "deploy": "#54A24B",
    "update_user_lambda": "#72B7B2",
    "update_app_lambda": "#B279A2",
    "move_users": "#FF9DA6",
}

TOOL_TYPES = {
    "apply_replicate_application_vnf": "replicate",
    "replicate_simulation_application_vnf": "replicate",
    "apply_move_application_vnf": "move_vnf",
    "move_simulation_application_vnf": "move_vnf",
    "apply_remove_application_vnf": "remove_vnf",
    "remove_simulation_application_vnf": "remove_vnf",
    "remove_simulation_application_vnfs": "remove_vnf",
    "apply_deploy_application_vnfs": "deploy",
    "deploy_simulation_application_vnfs": "deploy",
    "deploy_simulation_application_vnfs_generated": "deploy",
    "update_simulation_user_lambda": "update_user_lambda",
    "update_simulation_application_users_lambda": "update_app_lambda",
    "move_simulation_users_to_node": "move_users",
}

FALLBACK_COLORS = (
    "#9D755D",
    "#BAB0AC",
    "#4E79A7",
    "#59A14F",
    "#EDC948",
    "#B07AA1",
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return {}


def action_type(tool: str) -> str:
    if tool in TOOL_TYPES:
        return TOOL_TYPES[tool]
    return tool


def action_label(action: str) -> str:
    if action in ACTION_LABELS:
        return ACTION_LABELS[action]
    return action.replace("_", " ")


def action_color(action: str, extras: dict[str, str]) -> str:
    if action in ACTION_COLORS:
        return ACTION_COLORS[action]
    if action not in extras:
        extras[action] = FALLBACK_COLORS[len(extras) % len(FALLBACK_COLORS)]
    return extras[action]


def timed_actions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach a simulation time to each model action.

    Placement tools do not echo the clock. The time is the action's own
    ``simulation_now`` when present, otherwise the latest clock already
    seen in the log.
    """
    last_now: float | None = None
    selected: list[dict[str, Any]] = []
    for row in rows:
        moment = row.get("simulation_now")
        if moment is not None:
            last_now = float(moment)
        if row.get("actor") != "model":
            continue
        when = float(moment) if moment is not None else last_now
        if when is None:
            continue
        selected.append(
            {
                "time": when,
                "type": action_type(str(row.get("tool") or "unknown")),
            }
        )
    return selected


def window_starts(simulation_end: float, window: float) -> list[float]:
    starts: list[float] = []
    cursor = 0.0
    while cursor < simulation_end - 1e-9:
        starts.append(cursor)
        cursor += window
    return starts


def stack_counts(
    actions: list[dict[str, Any]],
    *,
    simulation_end: float,
    window: float,
) -> tuple[list[float], list[str], dict[str, list[int]]]:
    starts = window_starts(simulation_end, window)
    types = []
    for action in actions:
        if action["type"] not in types:
            types.append(action["type"])
    preferred = [name for name in ACTION_LABELS if name in types]
    types = preferred + [name for name in types if name not in preferred]
    counts = {name: [0 for _ in starts] for name in types}
    if not starts:
        return starts, types, counts
    last_index = len(starts) - 1
    for action in actions:
        index = int(action["time"] // window)
        if index > last_index:
            index = last_index
        if index < 0:
            index = 0
        counts[action["type"]][index] += 1
    return starts, types, counts


def find_model_dirs(path: Path) -> list[Path]:
    if (path / "actions.jsonl").exists():
        return [path]
    found = sorted(
        item.parent
        for item in path.glob("*/actions.jsonl")
        if item.is_file()
    )
    if not found:
        raise FileNotFoundError(f"No actions.jsonl under {path}")
    return found


def plot_model(
    ax: Any,
    *,
    model_dir: Path,
    extras: dict[str, str],
) -> list[str]:
    status = load_json(model_dir / "run_status.json")
    window = float(status.get("window_duration") or WINDOW_DURATION)
    simulation_end = float(status.get("simulation_end") or SIMULATION_END)
    actions = timed_actions(load_jsonl(model_dir / "actions.jsonl"))
    starts, types, counts = stack_counts(
        actions,
        simulation_end=simulation_end,
        window=window,
    )
    bottoms = [0 for _ in starts]
    for name in types:
        values = counts[name]
        ax.bar(
            [start + window / 2.0 for start in starts],
            values,
            width=window * 0.9,
            bottom=bottoms,
            color=action_color(name, extras),
            label=action_label(name),
            linewidth=0,
        )
        bottoms = [base + value for base, value in zip(bottoms, values)]
    ax.set_xlim(0, simulation_end)
    ax.set_xlabel("Simulation time")
    ax.set_ylabel("Actions")
    title = status.get("model") or model_dir.name
    ax.set_title(str(title))
    return types


def plot_run(results: Path, output: Path | None) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    model_dirs = find_model_dirs(results)
    extras: dict[str, str] = {}
    fig, axes = plt.subplots(
        nrows=len(model_dirs),
        ncols=1,
        figsize=(11, 3.6 * len(model_dirs)),
        squeeze=False,
        sharex=True,
    )
    seen: list[str] = []
    for ax, model_dir in zip(axes[:, 0], model_dirs):
        for name in plot_model(ax, model_dir=model_dir, extras=extras):
            if name not in seen:
                seen.append(name)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    if len(model_dirs) > 1:
        for ax in axes[1:, 0]:
            extra_handles, extra_labels = ax.get_legend_handles_labels()
            for handle, label in zip(extra_handles, extra_labels):
                if label not in labels:
                    handles.append(handle)
                    labels.append(label)
    fig.legend(
        handles,
        labels,
        loc="upper center",
        ncol=min(len(labels), 4),
        frameon=False,
        bbox_to_anchor=(0.5, 1.0),
    )
    fig.tight_layout(rect=(0, 0, 1, 0.92 if labels else 1))
    if output is None:
        if len(model_dirs) == 1:
            output = model_dirs[0] / "actions_stacked_timeline.png"
        else:
            output = results / "actions_stacked_timeline.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=140)
    plt.close(fig)
    return output


# Top to bottom. Controller stays on the time axis because its arrows
# span the scheduled blocks.
CATEGORY_ORDER = ("Inventory", "Placement", "Analytics", "Control")

BAND_COLORS = {
    "Inventory": "#e8f1fa",
    "Placement": "#fce6e6",
    "Analytics": "#f2ffeb",
    "Control": "#c8ccdb",
}

# Lower alpha keeps the bands pale so the markers stay readable.
BAND_ALPHA = 0.38

WAIT_TOOL = "wait_simulation_until_ready"
RUN_TOOL = "run_simulation_for"
FORK_TOOL = "fork_simulation"
SPAN_MATCH = 1.5
ARROW_COLOR = "#6E243C"
SPAN_LANE = 0.12
_SUPERSCRIPT_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹"

# Experiment wrappers that are not in the MCP catalog. Each one maps to
# the catalog tool it calls, so it inherits that tool's group.
TOOL_ALIASES = {
    "apply_deploy_application_vnfs": "deploy_simulation_application_vnfs",
    "apply_move_application_vnf": "move_simulation_application_vnf",
    "apply_replicate_application_vnf": "replicate_simulation_application_vnf",
    "apply_remove_application_vnf": "remove_simulation_application_vnf",
    "get_base_simulation": "get_simulation_state",
}

GROUP_LABELS = {
    "inventory": "Inventory",
    "placement": "Placement",
    "controller": "Control",
    "analyst": "Analytics",
}

TOOL_LABELS = {
    "apply_deploy_application_vnfs": "Deploy VNFs",
    "deploy_simulation_application_vnfs": "Deploy VNFs",
    "deploy_simulation_application_vnfs_generated": "Deploy generated VNFs",
    "apply_replicate_application_vnf": "Replicate VNF",
    "replicate_simulation_application_vnf": "Replicate VNF",
    "apply_move_application_vnf": "Move VNF",
    "move_simulation_application_vnf": "Move VNF",
    "apply_remove_application_vnf": "Remove VNF",
    "remove_simulation_application_vnf": "Remove VNF",
    "remove_simulation_application_vnfs": "Remove VNFs",
    "update_simulation_user_lambda": "Update user lambda",
    "update_simulation_application_users_lambda": "Update application lambda",
    "move_simulation_users_to_node": "Move users",
    "get_simulation_application_metrics": "Application metrics",
    "get_latency_breakdown": "Latency breakdown",
    "get_simulation_network_metrics": "Network metrics",
    "get_deployments": "Deployments",
    "get_topology": "Topology",
    "get_request_paths": "Request paths",
    "get_simulation_state": "Simulation state",
    "get_base_simulation": "Base simulation",
    "list_simulation_users": "Users",
    "list_simulation_processes": "Processes",
    "list_simulation_node_placements": "Node placements",
    "list_simulation_nodes_in_cluster": "Cluster nodes",
    "list_simulation_application_vnfs": "Application VNFs",
    "list_simulation_deployed_applications": "Deployed applications",
    "list_simulation_nodes": "Nodes",
    "list_simulation_clusters": "Clusters",
    "list_simulations": "Simulations",
    "count_simulation_nodes": "Node count",
    "count_simulation_clusters": "Cluster count",
    RUN_TOOL: "Run simulation",
    WAIT_TOOL: "Wait until ready",
    "disable_simulation_process": "Disable process",
    "enable_simulation_process": "Enable process",
    "remove_simulation_process": "Remove process",
    "pause_simulation": "Pause",
    "resume_simulation": "Resume",
    "stop_simulation": "Stop",
    "fork_simulation": "Fork",
    "update_simulation_node": "Update node",
    "remove_simulation_node": "Remove node",
    "remove_simulation_cluster": "Remove cluster",
}

RESERVED_STYLES = {
    WAIT_TOOL: ("s", "#242424"),
    RUN_TOOL: ("^", "#9C4221"),
}

MARKER_POOL = (
    "o",
    "D",
    "v",
    "P",
    "X",
    "*",
    "h",
    "p",
    "d",
    "H",
    "<",
    ">",
    "8",
)

COLOR_POOL = (
    "#1F4E79",
    "#2E7D4F",
    "#6B3FA0",
    "#B45309",
    "#0F6F8C",
    "#9B2C2C",
    "#3F6212",
    "#1E3A5F",
    "#7C3AED",
    "#9A3412",
    "#155E75",
    "#3F3F46",
    "#A16207",
    "#365314",
    "#831843",
    "#134E4A",
)


def category_of(tool: str) -> str:
    """Classify one call with the placement-profile groups."""
    canonical = TOOL_ALIASES.get(tool, tool)
    group = mcp_tool_group(canonical)
    if group in GROUP_LABELS:
        return GROUP_LABELS[group]
    if tool.startswith("apply_"):
        return "Placement"
    return "Inventory"


def tool_label(tool: str) -> str:
    if tool in TOOL_LABELS:
        return TOOL_LABELS[tool]
    return tool.replace("_", " ")


def tool_style(tool: str) -> tuple[str, str]:
    """Return a stable marker and color for one tool."""
    if tool in RESERVED_STYLES:
        return RESERVED_STYLES[tool]
    ordered = sorted(
        name
        for name in TOOL_LABELS
        if name not in RESERVED_STYLES
    )
    if tool in ordered:
        index = ordered.index(tool)
    else:
        index = len(ordered) + sum(ord(char) for char in tool)
    return (
        MARKER_POOL[index % len(MARKER_POOL)],
        COLOR_POOL[index % len(COLOR_POOL)],
    )


def result_summary(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("result")
    payload: Any = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text.startswith("{"):
            return {}
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return {}
    if not isinstance(payload, dict):
        return {}
    summary = payload.get("summary")
    if isinstance(summary, dict):
        return summary
    return {}


def run_span(
    row: dict[str, Any],
    origin: float | None,
) -> dict[str, Any] | None:
    """Return the simulation interval scheduled by ``run_simulation_for``."""
    arguments = row.get("arguments") or {}
    summary = result_summary(row)
    end = summary.get("scheduled_until")
    duration = arguments.get("duration")
    if end is not None and duration is not None:
        end_value = float(end)
        duration_value = float(duration)
        if duration_value > 0:
            return {
                "start": end_value - duration_value,
                "end": end_value,
                "duration": duration_value,
            }
    if end is not None and origin is not None:
        end_value = float(end)
        origin_value = float(origin)
        if end_value > origin_value:
            return {
                "start": origin_value,
                "end": end_value,
                "duration": end_value - origin_value,
            }
    return None


def _superscript(value: int) -> str:
    """Render ``value`` as a unicode superscript, such as 2 -> ²."""
    return "".join(
        _SUPERSCRIPT_DIGITS[int(char)] for char in str(value)
    )


def _simulation_id(row: dict[str, Any]) -> str | None:
    arguments = row.get("arguments") or {}
    value = arguments.get("simulation_id")
    if value:
        return str(value)
    return None


def _forked_simulation(row: dict[str, Any]) -> tuple[str, str] | None:
    """Return ``(child_id, child_name)`` created by a successful fork."""
    if str(row.get("tool") or "") != FORK_TOOL:
        return None
    if not row.get("ok", True):
        return None
    summary = result_summary(row)
    child = summary.get("id")
    parent = _simulation_id(row)
    if not child or not parent or str(child) == parent:
        return None
    name = summary.get("name") or str(child)
    return str(child), str(name)


def simulation_forks(
    actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Number forked simulations in creation order, starting at 2.

    The parent simulation is omitted. The first successful fork is 2,
    the next is 3, and so on.
    """
    forks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in actions:
        created = _forked_simulation(row)
        if created is None:
            continue
        child, name = created
        if child in seen:
            continue
        seen.add(child)
        forks.append(
            {
                "id": child,
                "name": name,
                "mark": len(forks) + 2,
            }
        )
    return forks


def _mark_of(
    simulation_id: str | None,
    marks: dict[str, int],
) -> int | None:
    if simulation_id is None:
        return None
    return marks.get(simulation_id)


def _event(
    when: float,
    tool: str,
    row: dict[str, Any],
    mark: int | None,
) -> dict[str, Any]:
    event = {
        "time": float(when),
        "tool": tool,
        "category": category_of(tool),
        "ok": bool(row.get("ok", True)),
    }
    if mark is not None:
        event["mark"] = mark
    return event


def spread_duplicates(events: list[dict[str, Any]]) -> None:
    """Separate repeated calls of one tool at the same simulation time."""
    groups: dict[tuple[str, float], list[dict[str, Any]]] = {}
    for event in events:
        if event["tool"] in (RUN_TOOL, WAIT_TOOL):
            continue
        key = (str(event["tool"]), round(float(event["time"]), 3))
        groups.setdefault(key, []).append(event)
    for group in groups.values():
        count = len(group)
        if count < 2:
            continue
        gap = 55.0
        origin = float(group[0]["time"]) - gap * (count - 1) / 2.0
        for index, event in enumerate(group):
            event["time"] = origin + index * gap


def dedupe_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, float, float]] = set()
    for span in spans:
        if span["end"] <= span["start"] + 1e-9:
            continue
        key = (
            span.get("mark"),
            round(float(span["start"]), 3),
            round(float(span["end"]), 3),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(span)
    return unique


def _tag_span(
    span: dict[str, Any],
    mark: int | None,
) -> dict[str, Any]:
    tagged = dict(span)
    if mark is not None:
        tagged["mark"] = mark
    return tagged


def build_category_series(
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Place model calls on each simulation's clock and collect spans.

    Placement calls often omit ``simulation_now``. Each simulation keeps
    the latest time already observed for its own id, including harness
    waits, so a call is drawn at that simulation's time. A fork starts
    the child clock at the time reported by the fork result.
    """
    forks = simulation_forks(actions)
    marks = {str(item["id"]): int(item["mark"]) for item in forks}
    events: list[dict[str, Any]] = []
    spans: list[dict[str, Any]] = []
    pending: dict[str, dict[str, Any]] = {}
    clocks: dict[str, float] = {}

    for row in actions:
        sid = _simulation_id(row)
        origin = clocks.get(sid) if sid is not None else None
        moment = row.get("simulation_now")
        if sid is not None and moment is not None:
            clocks[sid] = float(moment)
        created = _forked_simulation(row)
        if created is not None:
            child_id, _name = created
            summary = result_summary(row)
            child_now = summary.get("now")
            if child_now is not None:
                clocks[child_id] = float(child_now)
            elif moment is not None:
                clocks[child_id] = float(moment)
            elif origin is not None:
                clocks[child_id] = float(origin)
        if row.get("actor") not in (None, "model"):
            continue
        when = float(moment) if moment is not None else origin
        tool = str(row.get("tool") or "unknown")
        mark = _mark_of(sid, marks)
        key = sid or ""

        if tool == RUN_TOOL:
            span = run_span(row, origin)
            held = pending.pop(key, None)
            if held is not None:
                spans.append(held)
            if span is not None:
                pending[key] = _tag_span(span, mark)
                when = span["start"]
            if when is None:
                continue
            events.append(_event(when, tool, row, mark))
            continue

        if tool == WAIT_TOOL:
            held = pending.get(key)
            matched = (
                held is not None
                and when is not None
                and abs(when - float(held["end"])) <= SPAN_MATCH
            )
            if matched:
                spans.append(pending.pop(key))
            elif (
                origin is not None
                and when is not None
                and when > origin + 1e-3
            ):
                spans.append(
                    _tag_span(
                        {
                            "start": float(origin),
                            "end": float(when),
                            "duration": float(when) - float(origin),
                        },
                        mark,
                    )
                )
            if when is None:
                continue
            events.append(_event(when, tool, row, mark))
            continue

        if when is None:
            continue
        events.append(_event(when, tool, row, mark))

    spans.extend(pending.values())
    spread_duplicates(events)
    return {
        "events": events,
        "spans": dedupe_spans(spans),
        "forks": forks,
    }


def _assign_span_lanes(
    spans: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Stack scheduled blocks that cover the same simulation interval.

    Parent blocks are placed first so they keep the lowest lane when a
    fork advances across the same times.
    """
    ordered = sorted(
        spans,
        key=lambda span: (
            0 if span.get("mark") is None else 1,
            float(span["start"]),
            float(span["end"]),
        ),
    )
    lane_ends: list[float] = []
    placed: list[dict[str, Any]] = []
    for span in ordered:
        start = float(span["start"])
        end = float(span["end"])
        lane: int | None = None
        for index, lane_end in enumerate(lane_ends):
            if start >= lane_end - 1e-6:
                lane = index
                break
        if lane is None:
            lane = len(lane_ends)
            lane_ends.append(end)
        else:
            lane_ends[lane] = end
        tagged = dict(span)
        tagged["lane"] = lane
        placed.append(tagged)
    return placed, max(len(lane_ends), 1)


def _span_lane_extra(lane_count: int) -> float:
    return max(lane_count - 1, 0) * SPAN_LANE


def _tools_by_category(
    events: list[dict[str, Any]],
) -> dict[str, list[str]]:
    grouped = {name: [] for name in CATEGORY_ORDER}
    seen: set[str] = set()
    for event in events:
        tool = str(event["tool"])
        if tool in seen:
            continue
        grouped[category_of(tool)].append(tool)
        seen.add(tool)
    return grouped


def _band_height(category: str, tools: list[str]) -> float:
    """Size a band from the lanes it actually draws.

    Control keeps one compact row for the scheduled-block arrows and a
    short stack for the other controller calls.
    """
    lane = 0.15
    pad = 0.16
    if category == "Control":
        upper = [tool for tool in tools if tool != WAIT_TOOL]
        arrow = 0.34
        markers = pad + lane * max(len(upper) - 1, 0)
        return arrow + markers + 0.10
    return pad + lane * max(len(tools), 1)


def _band_layout(
    grouped: dict[str, list[str]],
) -> tuple[dict[str, float], dict[str, float], float]:
    heights = {
        category: _band_height(category, grouped.get(category, []))
        for category in CATEGORY_ORDER
    }
    bases: dict[str, float] = {}
    cursor = 0.0
    for category in reversed(CATEGORY_ORDER):
        bases[category] = cursor
        cursor += heights[category]
    return bases, heights, cursor


def _visible_band(color: str) -> str:
    """Blend a band color with white at BAND_ALPHA."""
    red = int(color[1:3], 16)
    green = int(color[3:5], 16)
    blue = int(color[5:7], 16)

    def mix(channel: int) -> int:
        return round(channel * BAND_ALPHA + 255 * (1.0 - BAND_ALPHA))

    return f"#{mix(red):02X}{mix(green):02X}{mix(blue):02X}"


def _lane_y(
    rank: int,
    count: int,
    low: float,
    high: float,
) -> float:
    """Stack tool lanes around the middle of a band.

    A crowded band uses the full height. A band with only a few tools stays
    clustered, so the markers still read as one category.
    """
    if count <= 1:
        return (low + high) / 2.0
    full = high - low
    step = min(full / (count - 1), max(full / 12.0, 0.13))
    used = step * (count - 1)
    top = (low + high) / 2.0 + used / 2.0
    return top - rank * step


def _format_duration(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.1f}"


def draw_category_timeline(
    ax: Any,
    actions: list[dict[str, Any]],
    *,
    simulation_end: float | None = None,
    title: str | None = None,
) -> dict[str, list[Any]]:
    """Draw the four placement-profile bands on ``ax``."""
    from matplotlib.lines import Line2D

    series = build_category_series(actions)
    events = series["events"]
    spans, lane_count = _assign_span_lanes(series["spans"])
    lane_extra = _span_lane_extra(lane_count)
    if not events and not spans:
        ax.text(
            0.5,
            0.5,
            "No model actions",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        ax.set_axis_off()
        return {}

    grouped = _tools_by_category(events)
    bases, heights, total = _band_layout(grouped)
    if lane_extra:
        heights["Control"] += lane_extra
        total += lane_extra
        for category in CATEGORY_ORDER:
            if category != "Control":
                bases[category] += lane_extra
    boundary = 0.0
    for category in reversed(CATEGORY_ORDER):
        height = heights[category]
        if boundary > 0:
            ax.axhline(boundary, color="white", linewidth=1.4, zorder=1)
        ax.axhspan(
            boundary,
            boundary + height,
            facecolor=BAND_COLORS[category],
            edgecolor="none",
            alpha=BAND_ALPHA,
            zorder=0,
        )
        boundary += height

    positions: dict[str, float] = {}
    for category, tools in grouped.items():
        base = bases[category]
        height = heights[category]
        if category == "Control":
            upper = [tool for tool in tools if tool != WAIT_TOOL]
            arrow_y = base + 0.16
            if WAIT_TOOL in tools or spans:
                positions[WAIT_TOOL] = arrow_y
            marker_lift = lane_extra if spans else 0.0
            low = base + (
                0.36 + marker_lift
                if (WAIT_TOOL in tools or spans)
                else 0.08
            )
            high = base + height - 0.06
            for rank, tool in enumerate(upper):
                positions[tool] = _lane_y(rank, len(upper), low, high)
            continue
        low = base + height * 0.12
        high = base + height * 0.88
        for rank, tool in enumerate(tools):
            positions[tool] = _lane_y(rank, len(tools), low, high)

    controller_base = bases["Control"]
    controller_height = heights["Control"]
    arrow_y = positions.get(
        WAIT_TOOL,
        controller_base + controller_height * 0.30,
    )

    def _wait_at(span: dict[str, Any], bound: float) -> bool:
        return any(
            event["tool"] == WAIT_TOOL
            and event.get("mark") == span.get("mark")
            and abs(float(event["time"]) - bound) <= SPAN_MATCH
            for event in events
        )

    for span in spans:
        span_y = arrow_y + int(span.get("lane") or 0) * SPAN_LANE
        start_has_wait = _wait_at(span, float(span["start"]))
        end_has_wait = _wait_at(span, float(span["end"]))
        if not start_has_wait:
            ax.plot(
                [span["start"], span["start"]],
                [span_y - 0.045, span_y + 0.045],
                color=ARROW_COLOR,
                linewidth=1.25,
                solid_capstyle="butt",
                zorder=2,
            )
        ax.annotate(
            "",
            xy=(span["end"], span_y),
            xytext=(span["start"], span_y),
            arrowprops={
                "arrowstyle": "-|>",
                "color": ARROW_COLOR,
                "lw": 1.25,
                "shrinkA": 8 if start_has_wait else 1,
                "shrinkB": 8 if end_has_wait else 0,
                "mutation_scale": 11,
            },
            zorder=2,
        )
        caption = _format_duration(float(span["duration"]))
        if span.get("mark") is not None:
            caption += _superscript(int(span["mark"]))
        ax.text(
            (span["start"] + span["end"]) / 2.0,
            span_y,
            caption,
            ha="center",
            va="center",
            fontsize=8,
            color=ARROW_COLOR,
            zorder=3,
            bbox={
                "facecolor": _visible_band(BAND_COLORS["Control"]),
                "edgecolor": "none",
                "pad": 0.15,
            },
        )

    legend_tools: list[str] = []
    for category in CATEGORY_ORDER:
        for tool in grouped[category]:
            if tool not in legend_tools:
                legend_tools.append(tool)

    for tool in legend_tools:
        marker, color = tool_style(tool)
        rows = [event for event in events if event["tool"] == tool]
        ok_rows = [event for event in rows if event["ok"]]
        bad_rows = [event for event in rows if not event["ok"]]
        y_value = positions[tool]
        if ok_rows:
            ax.scatter(
                [event["time"] for event in ok_rows],
                [y_value for _ in ok_rows],
                marker=marker,
                s=78,
                c=color,
                edgecolors="white",
                linewidths=0.5,
                zorder=4,
            )
        if bad_rows:
            ax.scatter(
                [event["time"] for event in bad_rows],
                [y_value for _ in bad_rows],
                marker=marker,
                s=88,
                c=color,
                edgecolors="#C00000",
                linewidths=1.1,
                zorder=5,
            )
        for event in rows:
            mark = event.get("mark")
            if mark is None:
                continue
            ax.annotate(
                _superscript(int(mark)),
                xy=(float(event["time"]), y_value),
                xytext=(4, 3),
                textcoords="offset points",
                ha="left",
                va="bottom",
                fontsize=12,
                color="#1A1A1A",
                zorder=6,
            )

    grouped_handles: dict[str, list[Any]] = {
        category: [] for category in CATEGORY_ORDER
    }
    for tool in legend_tools:
        marker, color = tool_style(tool)
        grouped_handles[category_of(tool)].append(
            Line2D(
                [0],
                [0],
                marker=marker,
                linestyle="None",
                color=color,
                markerfacecolor=color,
                markeredgecolor="white",
                markersize=9,
                label=tool_label(tool),
            )
        )
    if spans:
        grouped_handles["Control"].append(
            Line2D(
                [0],
                [0],
                color=ARROW_COLOR,
                marker="|",
                markersize=10,
                linewidth=1.3,
                label="Scheduled block",
            )
        )

    times = [float(event["time"]) for event in events]
    for span in spans:
        times.extend((float(span["start"]), float(span["end"])))
    if simulation_end is not None:
        times.append(float(simulation_end))
    x_max = max(times) if times else 1.0
    pad = max(x_max * 0.035, 1.0)
    ax.set_xlim(-pad * 0.25, x_max + pad)
    ax.set_ylim(-0.02, total + 0.02)
    ax.set_yticks(
        [
            bases[name] + heights[name] / 2.0
            for name in CATEGORY_ORDER
        ]
    )
    ax.set_yticklabels(list(CATEGORY_ORDER), fontsize=12)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("Simulation time", color="#7A2348")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color("#7A2348")
    ax.spines["bottom"].set_linewidth(1.2)
    ax.tick_params(axis="x", colors="#333333")
    return grouped_handles


def _legend_columns(count: int) -> int:
    if count > 4:
        return 2
    return 1


def _legend_item_rows(count: int) -> int:
    columns = _legend_columns(count)
    return (count + columns - 1) // columns


def _legend_block_rows(grouped_handles: dict[str, list[Any]]) -> int:
    rows = 1
    for handles in grouped_handles.values():
        if not handles:
            continue
        rows = max(rows, _legend_item_rows(len(handles)) + 1)
    return rows


def _place_grouped_legends(
    fig: Any,
    grouped_handles: dict[str, list[Any]],
    *,
    bottom: float,
    height: float,
) -> None:
    """One legend per group, on the same background as its band."""
    categories = [
        category
        for category in CATEGORY_ORDER
        if grouped_handles.get(category)
    ]
    if not categories:
        return
    gap = 0.012
    left = 0.08
    slot = (0.90 - gap * (len(categories) - 1)) / len(categories)
    top = bottom + height
    for index, category in enumerate(categories):
        handles = grouped_handles[category]
        anchor_x = left + index * (slot + gap) + slot / 2.0
        legend = fig.legend(
            handles,
            [handle.get_label() for handle in handles],
            loc="upper center",
            bbox_to_anchor=(anchor_x, top),
            bbox_transform=fig.transFigure,
            frameon=True,
            fontsize=7.5,
            title=category,
            ncol=_legend_columns(len(handles)),
            borderpad=0.55,
        )
        legend.get_title().set_fontsize(12)
        legend.get_title().set_fontweight("bold")
        frame = legend.get_frame()
        frame.set_facecolor(_visible_band(BAND_COLORS[category]))
        frame.set_edgecolor("none")
        frame.set_linewidth(0)


def plot_category_timeline(
    actions: list[dict[str, Any]],
    output: Path,
    *,
    simulation_end: float | None = None,
    title: str | None = None,
    legend: bool = True,
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    series = build_category_series(actions)
    grouped = _tools_by_category(series["events"])
    _bases, _heights, total = _band_layout(grouped)
    _spans, lane_count = _assign_span_lanes(series["spans"])
    total += _span_lane_extra(lane_count)
    legend_rows = _legend_block_rows(
        {
            category: list(tools)
            + (["span"] if category == "Control" and series["spans"] else [])
            for category, tools in grouped.items()
        }
    )
    xlabel_in = 0.55
    gap_in = 0.18 if legend else 0.0
    legend_in = (0.26 * legend_rows + 0.15) if legend else 0.0
    top_pad = 0.08
    plot_in = max(4.2, 1.05 * total)
    fig_h = xlabel_in + plot_in + gap_in + legend_in + top_pad
    fig = plt.figure(figsize=(12.6, fig_h))
    ax = fig.add_axes(
        [
            0.14,
            xlabel_in / fig_h,
            0.82,
            plot_in / fig_h,
        ]
    )
    grouped_handles = draw_category_timeline(
        ax,
        actions,
        simulation_end=simulation_end,
        title=title,
    )
    if legend:
        _place_grouped_legends(
            fig,
            grouped_handles,
            bottom=(xlabel_in + plot_in + gap_in) / fig_h,
            height=legend_in / fig_h,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=140)
    plt.close(fig)
    return output


def plot_category_run(
    results: Path,
    output: Path | None,
    *,
    legend: bool = True,
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    model_dirs = find_model_dirs(results)
    if len(model_dirs) == 1:
        model_dir = model_dirs[0]
        status = load_json(model_dir / "run_status.json")
        simulation_end = status.get("simulation_end")
        if output is None:
            output = model_dir / "actions_by_category.png"
        return plot_category_timeline(
            load_jsonl(model_dir / "actions.jsonl"),
            output,
            simulation_end=(
                float(simulation_end) if simulation_end is not None else None
            ),
            title=str(status.get("model") or model_dir.name),
            legend=legend,
        )

    merged: dict[str, list[Any]] = {
        category: [] for category in CATEGORY_ORDER
    }
    seen: set[str] = set()
    fig, axes = plt.subplots(
        nrows=len(model_dirs),
        ncols=1,
        figsize=(12.6, 6.2 * len(model_dirs)),
        squeeze=False,
        sharex=True,
    )
    for ax, model_dir in zip(axes[:, 0], model_dirs):
        status = load_json(model_dir / "run_status.json")
        simulation_end = status.get("simulation_end")
        title = str(status.get("model") or model_dir.name)
        grouped_handles = draw_category_timeline(
            ax,
            load_jsonl(model_dir / "actions.jsonl"),
            simulation_end=(
                float(simulation_end) if simulation_end is not None else None
            ),
            title=title,
        )
        for category, handles in grouped_handles.items():
            for handle in handles:
                label = handle.get_label()
                if label in seen:
                    continue
                merged[category].append(handle)
                seen.add(label)
    if legend:
        legend_rows = _legend_block_rows(merged)
        legend_h = min(0.22, 0.02 * legend_rows + 0.04)
        fig.tight_layout(rect=(0, 0, 1, 1 - legend_h - 0.02))
        _place_grouped_legends(
            fig,
            merged,
            bottom=1.0 - legend_h - 0.005,
            height=legend_h,
        )
    else:
        fig.tight_layout()
    if output is None:
        if len(model_dirs) == 1:
            output = model_dirs[0] / "actions_by_category.png"
        else:
            output = results / "actions_by_category.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=140)
    plt.close(fig)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "results",
        type=Path,
        help="Model directory or run directory that contains actions.jsonl.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "PNG path. Defaults to actions_stacked_timeline.png, "
            "or actions_by_category.png with --style categories."
        ),
    )
    parser.add_argument(
        "--style",
        choices=("stacked", "categories"),
        default="stacked",
        help=(
            "stacked counts actions per window; "
            "categories draws Inventory, Placement, Analyst, and Control."
        ),
    )
    parser.add_argument(
        "--legend",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Show the category legend above the plot. "
            "Use --no-legend to omit it. Applies to --style categories."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    results = args.results.resolve()
    if args.style == "categories":
        output = plot_category_run(
            results,
            args.output,
            legend=args.legend,
        )
    else:
        output = plot_run(results, args.output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
