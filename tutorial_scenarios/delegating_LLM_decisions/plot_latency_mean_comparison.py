"""Compare mean response latency across experiment directories.

Each directory is one line. A point is the mean of the three application
mean latencies in that simulation-time window, so each application has the
same weight. The legend uses the model name from ``run_status.json``.

From the repository root:

    uv run python tutorial_scenarios/delegating_LLM_decisions/plot_latency_mean_comparison.py \
        tutorial_scenarios/delegating_LLM_decisions/results/20261008-112715/anthropic_claude-sonnet-5.5 \
        tutorial_scenarios/delegating_LLM_decisions/results/20261008-100136/openai_gpt-6-luna 
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


def mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def load_requests(path: Path) -> list[tuple[str, float, float]]:
    requests: list[tuple[str, float, float]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            end_time = row.get("end_time")
            latency = row.get("service_response")
            if end_time in (None, "") or latency in (None, ""):
                continue
            requests.append(
                (str(row.get("app") or ""), float(end_time), float(latency))
            )
    return requests


def window_bounds(simulation_end: float, window: float) -> list[tuple[float, float]]:
    bounds: list[tuple[float, float]] = []
    start = 0.0
    while start < simulation_end - 1e-9:
        stop = min(start + window, simulation_end)
        bounds.append((start, stop))
        start = stop
    return bounds


def window_requests(
    requests: list[tuple[str, float, float]],
    start: float,
    stop: float,
    *,
    last: bool,
) -> list[tuple[str, float]]:
    selected: list[tuple[str, float]] = []
    for app, end_time, latency in requests:
        if last:
            inside = start <= end_time <= stop
        else:
            inside = start <= end_time < stop
        if inside:
            selected.append((app, latency))
    return selected


def application_mean(requests: list[tuple[str, float]]) -> float | None:
    """Mean of the per-application means in one window."""
    grouped: dict[str, list[float]] = {}
    for app, latency in requests:
        grouped.setdefault(app, []).append(latency)
    app_means = [
        value
        for values in grouped.values()
        if (value := mean(values)) is not None
    ]
    return mean(app_means)


def latency_series(
    requests: list[tuple[str, float, float]],
    *,
    simulation_end: float,
    window: float,
) -> tuple[list[float], list[float]]:
    times: list[float] = []
    values: list[float] = []
    bounds = window_bounds(simulation_end, window)
    last_index = len(bounds) - 1
    for index, (start, stop) in enumerate(bounds):
        sample = window_requests(
            requests,
            start,
            stop,
            last=index == last_index,
        )
        value = application_mean(sample)
        if value is None:
            continue
        times.append(stop)
        values.append(value)
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
    ax.set_xlabel("Simulation time", fontsize=14)
    ax.set_ylabel("Mean response latency", fontsize=14)
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
        return resolved[0] / "latency_mean_comparison.png"
    shared = resolved[0].parents
    for parent in shared:
        if all(parent in path.parents or path == parent for path in resolved):
            return parent / "latency_mean_comparison.png"
    return Path("latency_mean_comparison.png")


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
        help=(
            "PNG path. Defaults to latency_mean_comparison.png "
            "in the shared parent."
        ),
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
