"""Compare response latency across experiment directories.

Each directory is one line: the p95 of ``service_response`` inside every
simulation-time window. The legend uses the model name from
``run_status.json``.

From the repository root:

    uv run python tutorial_scenarios/delegating_LLM_decisions/plot_latency_comparison.py \
        tutorial_scenarios/delegating_LLM_decisions/results/20261008-112715/anthropic_claude-sonnet-5.5 \
        tutorial_scenarios/delegating_LLM_decisions/results/20261008-100136/openai_gpt-6-luna \
        tutorial_scenarios/delegating_LLM_decisions/results/20261008-110516/x-ai_grok-4.7
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


WINDOW_DURATION = 200.0
SIMULATION_END = 5000.0

SERIES_STYLE = (
    ("#1F4E79", "o"),
    ("#C45C26", "s"),
    ("#2E7D4F", "D"),
    ("#6B3FA0", "^"),
    ("#0F6F8C", "v"),
)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return {}


def percentile(values: list[float], quantile: float) -> float | None:
    """Linear percentile, matching the usual pandas quantile."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def load_requests(path: Path) -> list[tuple[float, float]]:
    requests: list[tuple[float, float]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            end_time = row.get("end_time")
            latency = row.get("service_response")
            if end_time in (None, "") or latency in (None, ""):
                continue
            requests.append((float(end_time), float(latency)))
    return requests


def window_bounds(simulation_end: float, window: float) -> list[tuple[float, float]]:
    bounds: list[tuple[float, float]] = []
    start = 0.0
    while start < simulation_end - 1e-9:
        stop = min(start + window, simulation_end)
        bounds.append((start, stop))
        start = stop
    return bounds


def latency_series(
    requests: list[tuple[float, float]],
    *,
    simulation_end: float,
    window: float,
) -> tuple[list[float], list[float]]:
    times: list[float] = []
    values: list[float] = []
    bounds = window_bounds(simulation_end, window)
    last_index = len(bounds) - 1
    for index, (start, stop) in enumerate(bounds):
        if index == last_index:
            sample = [
                latency
                for end_time, latency in requests
                if start <= end_time <= stop
            ]
        else:
            sample = [
                latency
                for end_time, latency in requests
                if start <= end_time < stop
            ]
        p95 = percentile(sample, 0.95)
        if p95 is None:
            continue
        times.append(stop)
        values.append(p95)
    return times, values


def experiment_label(directory: Path) -> str:
    status = load_json(directory / "run_status.json")
    model = status.get("model")
    if model:
        return str(model)
    return directory.name


def series_for_directory(directory: Path) -> tuple[str, list[float], list[float]]:
    requests_path = directory / "latency_requests.csv"
    if not requests_path.exists():
        raise FileNotFoundError(
            f"No latency_requests.csv in {directory}"
        )
    status = load_json(directory / "run_status.json")
    simulation_end = float(status.get("simulation_end") or SIMULATION_END)
    window = float(status.get("window_duration") or WINDOW_DURATION)
    times, values = latency_series(
        load_requests(requests_path),
        simulation_end=simulation_end,
        window=window,
    )
    return experiment_label(directory), times, values


def plot_comparison(directories: list[Path], output: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 5.2))
    plotted = False
    for index, directory in enumerate(directories):
        label, times, values = series_for_directory(directory)
        if not times:
            continue
        plotted = True
        color, marker = SERIES_STYLE[index % len(SERIES_STYLE)]
        ax.plot(
            times,
            values,
            marker=marker,
            color=color,
            linewidth=1.8,
            markersize=5.5,
            label=label,
        )
    ax.set_xlabel("Simulation time")
    ax.set_ylabel("Response latency p95")
    if plotted:
        ax.legend(frameon=False)
    else:
        ax.text(0.5, 0.5, "No latency samples", ha="center", va="center")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=140)
    plt.close(fig)
    return output


def default_output(directories: list[Path]) -> Path:
    resolved = [path.resolve() for path in directories]
    if len(resolved) == 1:
        return resolved[0] / "latency_comparison.png"
    shared = resolved[0].parents
    for parent in shared:
        if all(parent in path.parents or path == parent for path in resolved):
            return parent / "latency_comparison.png"
    return Path("latency_comparison.png")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directories",
        nargs="+",
        type=Path,
        help="Experiment directories that contain latency_requests.csv.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="PNG path. Defaults to latency_comparison.png in the shared parent.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    directories = [path.resolve() for path in args.directories]
    output = args.output or default_output(directories)
    written = plot_comparison(directories, output.resolve())
    print(written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
