"""
Plot a multi-agent timeline with congestion, overload, cost, and actions.

Each subplot shows the metric over simulation time and overlays vertical lines
for the placement strategy applied in each window.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


STRATEGY_COLORS = {
    "congestion": "#d1495b",
    "overload": "#edae49",
    "cost": "#00798c",
    "balanced": "#4f5d75",
    "unknown": "#9aa0a6",
}


ACTION_COLORS = {
    "replicate": "#457b9d",
    "move": "#2a9d8f",
    "consolidate": "#8d6b94",
    "replicate_failed": "#8d99ae",
    "move_failed": "#8d99ae",
    "consolidation_failed": "#8d99ae",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    scenario_dir = Path(__file__).resolve().parent
    results_dir = scenario_dir / "results_multi_agent"
    parser.add_argument(
        "--window-metrics",
        type=Path,
        default=results_dir / "window_metrics.json",
        help="Window metrics JSON emitted by main_multi_agent.py",
    )
    parser.add_argument(
        "--mcp-log",
        type=Path,
        default=results_dir / "mcp_interactions.jsonl",
        help="MCP interaction log used as a fallback for strategy labels.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=results_dir / "multi_agent_strategy_timeline.png",
        help="Output PNG path.",
    )
    parser.add_argument(
        "--title",
        default="Multi-Agent Timeline",
        help="Figure title.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Skip opening an interactive plot window.",
    )
    return parser


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_strategy_by_window(path: Path) -> dict[int, str]:
    if not path.exists():
        return {}
    mapping: dict[int, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        item = json.loads(raw_line)
        if item.get("entry_type") != "agent_message":
            continue
        if item.get("actor") != "PlacementAgent":
            continue
        if item.get("message_type") != "decision":
            continue
        window_index = int(item.get("window_index", -1))
        content = str(item.get("content") or "")
        strategy = "unknown"
        marker = "strategy="
        if marker in content:
            strategy = content.split(marker, 1)[1].split()[0].strip()
        mapping[window_index] = strategy
    return mapping


def enrich_window_metrics(window_logs: list[dict[str, Any]], strategy_map: dict[int, str]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in window_logs:
        clone = dict(item)
        window_index = int(clone.get("window_index", -1))
        if not clone.get("placement_strategy"):
            clone["placement_strategy"] = strategy_map.get(window_index, "unknown")
        enriched.append(clone)
    return enriched


def action_type_counts(window_logs: list[dict[str, Any]]) -> tuple[list[str], dict[str, list[int]]]:
    action_types = sorted(
        {
            str(action.get("type", "unknown"))
            for item in window_logs
            for action in item.get("actions", [])
        }
    )
    counts = {action_type: [] for action_type in action_types}
    for item in window_logs:
        window_counts = {action_type: 0 for action_type in action_types}
        for action in item.get("actions", []):
            action_type = str(action.get("type", "unknown"))
            if action_type in window_counts:
                window_counts[action_type] += 1
        for action_type in action_types:
            counts[action_type].append(window_counts[action_type])
    return action_types, counts


def infer_bar_width(x_values: list[float]) -> float:
    if len(x_values) < 2:
        return 20.0
    deltas = [
        right - left
        for left, right in zip(x_values, x_values[1:])
        if right > left
    ]
    return 0.62 * min(deltas) if deltas else 20.0


def plot_timeline(window_logs: list[dict[str, Any]], *, output_path: Path, title: str, show_plot: bool) -> None:
    if not window_logs:
        raise RuntimeError("No window metrics available to plot")

    window_logs = sorted(window_logs, key=lambda item: (float(item.get("window_end", 0.0)), int(item.get("window_index", 0))))
    x_values = [float(item.get("window_end", 0.0)) for item in window_logs]
    congested_links = [int(item.get("congested_link_count", 0) or 0) for item in window_logs]
    overloaded_nodes = [int(item.get("overloaded_node_count", 0) or 0) for item in window_logs]
    placement_cost = [float(item.get("placement_cost", 0.0) or 0.0) for item in window_logs]
    strategies = [str(item.get("placement_strategy") or "unknown") for item in window_logs]
    action_types, action_counts = action_type_counts(window_logs)

    fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True)
    fig.suptitle(title, fontsize=14, fontweight="bold")

    series = [
        ("Congested links", congested_links, "#d1495b"),
        ("Overloaded nodes", overloaded_nodes, "#edae49"),
        ("Placement cost", placement_cost, "#00798c"),
    ]
    for ax, (label, values, color) in zip(axes, series):
        ax.plot(x_values, values, color=color, marker="o", linewidth=2.0, markersize=4.5)
        ax.fill_between(x_values, values, color=color, alpha=0.18)
        ax.set_ylabel(label)
        ax.grid(True, axis="y", alpha=0.25)
        ymax = max(values) if values else 0.0
        for time_value, strategy in zip(x_values, strategies):
            ax.axvline(
                x=time_value,
                color=STRATEGY_COLORS.get(strategy, STRATEGY_COLORS["unknown"]),
                linestyle="--",
                linewidth=1.2,
                alpha=0.65,
            )
        if ymax <= 0:
            ax.set_ylim(0.0, 1.0)
        else:
            ax.set_ylim(0.0, ymax * 1.18)

    action_ax = axes[3]
    bottoms = [0] * len(x_values)
    bar_width = infer_bar_width(x_values)
    for index, action_type in enumerate(action_types):
        values = action_counts[action_type]
        color = ACTION_COLORS.get(action_type, f"C{index}")
        action_ax.bar(
            x_values,
            values,
            bottom=bottoms,
            width=bar_width,
            color=color,
            alpha=0.82,
            label=action_type,
        )
        bottoms = [left + right for left, right in zip(bottoms, values)]
    for time_value, strategy in zip(x_values, strategies):
        action_ax.axvline(
            x=time_value,
            color=STRATEGY_COLORS.get(strategy, STRATEGY_COLORS["unknown"]),
            linestyle="--",
            linewidth=1.2,
            alpha=0.65,
        )
    action_ax.set_ylabel("Actions")
    action_ax.grid(True, axis="y", alpha=0.25)
    action_ymax = max(bottoms) if bottoms else 0
    action_ax.set_ylim(0.0, max(1.0, action_ymax * 1.25))

    axes[-1].set_xlabel("Simulation time")

    strategy_handles = [
        Line2D([0], [0], color=color, linestyle="--", linewidth=2, label=name)
        for name, color in STRATEGY_COLORS.items()
        if name in set(strategies)
    ]
    metric_handles = [
        Line2D([0], [0], color=color, linewidth=3, label=label)
        for label, _, color in series
    ]
    axes[0].legend(handles=metric_handles + strategy_handles, loc="upper left", ncol=3, fontsize=9)
    if action_types:
        action_ax.legend(loc="upper left", ncol=min(4, len(action_types)), fontsize=9)

    plt.tight_layout(rect=(0, 0, 1, 0.97))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    if show_plot:
        plt.show()
    plt.close(fig)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.window_metrics.exists():
        raise FileNotFoundError(
            f"Window metrics file not found: {args.window_metrics}. Run main_multi_agent.py first."
        )

    window_logs = load_json(args.window_metrics)
    strategy_map = load_strategy_by_window(args.mcp_log)
    window_logs = enrich_window_metrics(window_logs, strategy_map)
    plot_timeline(
        window_logs,
        output_path=args.output,
        title=str(args.title),
        show_plot=not bool(args.no_show),
    )


if __name__ == "__main__":
    main()
