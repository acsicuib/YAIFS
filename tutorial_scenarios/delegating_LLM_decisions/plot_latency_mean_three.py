"""Mean response latency for Luna, Sonnet, and the multi-agent run.

Each series is the mean of the per-application mean latencies in a
simulation-time window. LLM directories use ``latency_requests.csv``.
The multi-agent directory uses the newest ``sim_trace_*.csv`` and the
same service-response metric as the LLM export. The script also prints
the mean and sample standard deviation of that window series over the
whole simulation.

From the repository root:

    uv run python tutorial_scenarios/delegating_LLM_decisions/plot_latency_mean_three.py
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


WINDOW_DURATION = 200.0
SIMULATION_END = 5000.0
SCENARIO_DIR = Path(__file__).resolve().parent
MULTI_AGENT_DIR = (
    SCENARIO_DIR.parent / "multi_agent_scenario"
)
SERVICES_JSON = MULTI_AGENT_DIR / "services.json"

DEFAULT_DIRECTORIES = (
    (
        "Claude Sonnet 5.5",
        SCENARIO_DIR
        / "results/20261008-112715/anthropic_claude-sonnet-5.5",
    ),
    (
        "GPT-6 Luna",
        SCENARIO_DIR / "results/20261008-100136/openai_gpt-6-luna",
    ),
    (
        "Multi-agent strategy",
        MULTI_AGENT_DIR / "results_multi_agent",
    ),
)

# color, marker, linewidth, markersize, linestyle
SERIES_STYLE = (
    ("#9B1B6A", "o", 2.5, 4.2, "-"),
    ("#D55E00", "s", 1.9, 4.8, "-"),
    ("#0057E7", "^", 2.15, 4.4, "--"),
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


def sample_std(values: list[float]) -> float | None:
    """Sample standard deviation of one latency series."""
    count = len(values)
    if count < 2:
        return None
    center = sum(values) / count
    variance = sum((value - center) ** 2 for value in values) / (count - 1)
    return variance ** 0.5


def window_bounds(
    simulation_end: float, window: float
) -> list[tuple[float, float]]:
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


def load_requests_csv(path: Path) -> list[tuple[str, float, float]]:
    requests: list[tuple[str, float, float]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            end_time = row.get("end_time")
            latency = row.get("service_response")
            if end_time in (None, "") or latency in (None, ""):
                continue
            requests.append(
                (
                    str(row.get("app") or ""),
                    float(end_time),
                    float(latency),
                )
            )
    return requests


def latest_event_trace(directory: Path) -> Path:
    matches = [
        item
        for item in directory.glob("sim_trace_*.csv")
        if not item.name.endswith("_link.csv")
    ]
    if not matches:
        raise FileNotFoundError(
            f"No sim_trace_*.csv in {directory}"
        )
    matches.sort(key=lambda item: (item.stat().st_mtime, item.name))
    return matches[-1]


def load_requests_from_trace(trace: Path) -> list[tuple[str, float, float]]:
    from yafs.metrics import MetricsAnalyzer

    analyzer = MetricsAnalyzer(
        defaultPath=str(trace),
        app_definition=str(SERVICES_JSON),
    )
    frame = analyzer.service_response(include_return_messages=True)
    if frame.empty:
        return []
    requests: list[tuple[str, float, float]] = []
    for row in frame.itertuples(index=False):
        end_time = getattr(row, "end_time", None)
        latency = getattr(row, "service_response", None)
        if end_time is None or latency is None:
            continue
        requests.append((str(row.app), float(end_time), float(latency)))
    return requests


def load_requests(directory: Path) -> list[tuple[str, float, float]]:
    requests_path = directory / "latency_requests.csv"
    if requests_path.exists():
        return load_requests_csv(requests_path)
    return load_requests_from_trace(latest_event_trace(directory))


def timing(directory: Path) -> tuple[float, float]:
    status = load_json(directory / "run_status.json")
    simulation_end = float(status.get("simulation_end") or SIMULATION_END)
    window = float(status.get("window_duration") or WINDOW_DURATION)
    return simulation_end, window


def series_for_directory(
    label: str, directory: Path
) -> tuple[str, list[float], list[float]]:
    simulation_end, window = timing(directory)
    times, values = latency_series(
        load_requests(directory),
        simulation_end=simulation_end,
        window=window,
    )
    return label, times, values


def print_latency_summary(series: list[tuple[str, Path]]) -> None:
    """Mean and sample standard deviation of each plotted series."""
    headers = ("Series", "Windows", "Mean", "Std")
    body: list[tuple[str, str, str, str]] = []
    for label, directory in series:
        name, _times, values = series_for_directory(label, directory)
        center = mean(values)
        spread = sample_std(values)
        body.append(
            (
                name,
                str(len(values)),
                f"{center:.4f}" if center is not None else "n/a",
                f"{spread:.4f}" if spread is not None else "n/a",
            )
        )
    widths = [
        max(len(header), *(len(item[index]) for item in body))
        for index, header in enumerate(headers)
    ]
    print(
        "  ".join(
            header.ljust(width) for header, width in zip(headers, widths)
        )
    )
    print("  ".join("-" * width for width in widths))
    for item in body:
        print(
            "  ".join(
                value.ljust(width) for value, width in zip(item, widths)
            )
        )


def plot_comparison(
    series: list[tuple[str, Path]], output: Path
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10.4, 5.4))
    plotted = False
    for index, (label, directory) in enumerate(series):
        name, times, values = series_for_directory(label, directory)
        if not times:
            continue
        plotted = True
        color, marker, linewidth, markersize, linestyle = SERIES_STYLE[
            index % len(SERIES_STYLE)
        ]
        ax.plot(
            times,
            values,
            marker=marker,
            color=color,
            linestyle=linestyle,
            linewidth=linewidth,
            markersize=markersize,
            markerfacecolor="white",
            markeredgecolor=color,
            markeredgewidth=1.0,
            markevery=2,
            label=name,
            zorder=3 - index,
        )
    ax.set_xlabel("Simulation time", fontsize=14)
    ax.set_ylabel("Mean response latency", fontsize=14)
    ax.tick_params(labelsize=11)
    ax.grid(axis="y", color="#D9D9D9", linewidth=0.6)
    if plotted:
        ax.legend(frameon=False, fontsize=12)
    else:
        ax.text(0.5, 0.5, "No latency samples", ha="center", va="center")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=140)
    plt.close(fig)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=SCENARIO_DIR / "results" / "latency_mean_three.png",
        help="PNG path.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    series = [
        (label, path.resolve()) for label, path in DEFAULT_DIRECTORIES
    ]
    written = plot_comparison(series, args.output.resolve())
    print(written)
    print_latency_summary(series)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
