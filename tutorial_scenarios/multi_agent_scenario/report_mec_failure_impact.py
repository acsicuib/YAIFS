from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from tutorial_scenarios.multi_agent_scenario.analyze_mec_failure_impact import (
    load_mec_worker_nodes,
    reconstruct_user_assignments,
    summarize_failure_impact,
)

SCENARIO_ORDER = ["Random", "Greedy", "Multi-Agent"]


def parse_args() -> argparse.Namespace:
    scenario_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description=(
            "Generate a Markdown report describing the impact of MEC-worker failures "
            "for the random and greedy experiments."
        )
    )
    parser.add_argument(
        "--topology",
        type=Path,
        default=scenario_dir / "topology.json",
        help="Path to the topology JSON.",
    )
    parser.add_argument(
        "--random-trace",
        type=Path,
        default=scenario_dir / "results_random" / "sim_trace.csv",
        help="Path to the random scenario sim_trace.csv.",
    )
    parser.add_argument(
        "--greedy-trace",
        type=Path,
        default=scenario_dir / "results_greedy" / "sim_trace.csv",
        help="Path to the greedy scenario sim_trace.csv.",
    )
    parser.add_argument(
        "--multi-trace",
        type=Path,
        default=scenario_dir / "results_multi_agent",
        help="Path to the multi-agent scenario sim_trace.csv or results directory.",
    )
    parser.add_argument(
        "--top-nodes",
        type=int,
        default=10,
        help="Number of most impactful MEC workers to include per scenario.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=scenario_dir / "results_greedy" / "mec_failure_impact_report.md",
        help="Output Markdown report path.",
    )
    return parser.parse_args()


def resolve_trace_path(path: Path) -> Path:
    candidate = path.expanduser().resolve()
    if candidate.is_file():
        return candidate
    directory = candidate if candidate.is_dir() else candidate.parent
    if not directory.exists():
        raise FileNotFoundError(f"Trace path does not exist: {path}")
    matches = sorted(
        {
            item
            for pattern in ("sim_trace.csv", "sim_trace_*.csv")
            for item in directory.glob(pattern)
            if not item.name.endswith("_link.csv")
        },
        key=lambda item: (item.stat().st_mtime, item.name),
    )
    if not matches:
        raise FileNotFoundError(f"No event trace matching {path} was found")
    return matches[-1]


def fmt_float(value: float) -> str:
    return f"{float(value):.2f}"


def fmt_pct(value: float) -> str:
    return f"{100.0 * float(value):.2f}%"


def scenario_summary_rows(summaries: dict[str, dict]) -> list[list[str]]:
    return [
        ["Deployed users", *[str(summaries[name]["deployed_users"]) for name in SCENARIO_ORDER]],
        ["Observed user-app assignments", *[str(summaries[name]["total_assignments"]) for name in SCENARIO_ORDER]],
        ["MEC workers total", *[str(summaries[name]["mec_nodes_total"]) for name in SCENARIO_ORDER]],
        ["Active MEC workers", *[str(summaries[name]["mec_nodes_with_hosted_apps"]) for name in SCENARIO_ORDER]],
        [
            "Average affected users (all MEC workers)",
            *[fmt_float(summaries[name]["average_affected_users_all_mec"]) for name in SCENARIO_ORDER],
        ],
        [
            "Average affected users (active MEC workers)",
            *[fmt_float(summaries[name]["average_affected_users_active_mec"]) for name in SCENARIO_ORDER],
        ],
        [
            "Affected-user probability (all MEC workers)",
            *[fmt_pct(summaries[name]["probability_user_affected_all_mec"]) for name in SCENARIO_ORDER],
        ],
        [
            "Affected-user probability (active MEC workers)",
            *[fmt_pct(summaries[name]["probability_user_affected_active_mec"]) for name in SCENARIO_ORDER],
        ],
    ]


def render_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    body_lines = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_line, separator_line, *body_lines])


def build_top_nodes_table(summary: dict, *, top_nodes: int) -> str:
    rows: list[list[str]] = []
    for rank, item in enumerate(summary["per_node"][:top_nodes], start=1):
        rows.append(
            [
                str(rank),
                str(item["mec_node"]),
                str(item["affected_users"]),
                fmt_pct(item["affected_probability"]),
            ]
        )
    if not rows:
        rows.append(["-", "-", "0", "0.00%"])
    return render_markdown_table(
        ["Rank", "MEC worker", "Affected users", "Affected probability"],
        rows,
    )


def summarize_by_app(
    frame: pd.DataFrame,
    assignment_nodes: pd.DataFrame,
    *,
    mec_nodes: set[str],
) -> dict[str, dict]:
    frame = frame.copy()
    assignment_nodes = assignment_nodes.copy()
    if not frame.empty:
        frame["base_app"] = frame["app"].astype(str).str.split("::").str[0]
    else:
        frame["base_app"] = pd.Series(dtype=str)
    if not assignment_nodes.empty:
        assignment_nodes["base_app"] = assignment_nodes["app"].astype(str).str.split("::").str[0]
    else:
        assignment_nodes["base_app"] = pd.Series(dtype=str)

    app_names = sorted(
        {
            *frame.loc[frame["type"] == "SRC_M", "base_app"].dropna().astype(str).unique().tolist(),
            *assignment_nodes["base_app"].dropna().astype(str).unique().tolist(),
        }
    )
    result: dict[str, dict] = {}
    for app_name in app_names:
        app_frame = frame[frame["base_app"].astype(str) == app_name].copy()
        app_assignments = assignment_nodes[assignment_nodes["base_app"].astype(str) == app_name].copy()
        result[app_name] = summarize_failure_impact(app_frame, app_assignments, mec_nodes=mec_nodes)
    return result


def build_app_summary_table(
    app_name: str,
    *,
    summaries: dict[str, dict],
) -> str:
    rows = [
        ["Deployed users", *[str(summaries[name]["deployed_users"]) for name in SCENARIO_ORDER]],
        ["Observed user-app assignments", *[str(summaries[name]["total_assignments"]) for name in SCENARIO_ORDER]],
        ["Active MEC workers", *[str(summaries[name]["mec_nodes_with_hosted_apps"]) for name in SCENARIO_ORDER]],
        [
            "Average affected users (all MEC workers)",
            *[fmt_float(summaries[name]["average_affected_users_all_mec"]) for name in SCENARIO_ORDER],
        ],
        [
            "Average affected users (active MEC workers)",
            *[fmt_float(summaries[name]["average_affected_users_active_mec"]) for name in SCENARIO_ORDER],
        ],
        [
            "Affected-user probability (all MEC workers)",
            *[fmt_pct(summaries[name]["probability_user_affected_all_mec"]) for name in SCENARIO_ORDER],
        ],
        [
            "Affected-user probability (active MEC workers)",
            *[fmt_pct(summaries[name]["probability_user_affected_active_mec"]) for name in SCENARIO_ORDER],
        ],
    ]
    section_lines = [
        f"### {app_name}",
        "",
        render_markdown_table(["Metric", *SCENARIO_ORDER], rows),
        "",
    ]
    for scenario_name in SCENARIO_ORDER:
        section_lines.extend(
            [
                f"{scenario_name} top MEC workers",
                "",
                build_top_nodes_table(summaries[scenario_name], top_nodes=5),
                "",
            ]
        )
    return "\n".join(
        section_lines
    )


def build_report(
    *,
    summaries: dict[str, dict],
    app_summaries: dict[str, dict[str, dict]],
    top_nodes: int,
    random_trace: Path,
    greedy_trace: Path,
    multi_trace: Path,
    topology: Path,
) -> str:
    summary_rows = scenario_summary_rows(summaries)
    summary_table = render_markdown_table(["Metric", *SCENARIO_ORDER], summary_rows)

    observations: list[str] = []
    random_summary = summaries["Random"]
    greedy_summary = summaries["Greedy"]
    multi_summary = summaries["Multi-Agent"]
    if random_summary["mec_nodes_with_hosted_apps"] < greedy_summary["mec_nodes_with_hosted_apps"]:
        observations.append(
            "Random concentra las aplicaciones observadas en menos `workers MEC`, por lo que un nodo activo tiende a ser más crítico."
        )
    if random_summary["average_affected_users_active_mec"] > greedy_summary["average_affected_users_active_mec"]:
        observations.append(
            "Greedy reparte el impacto de fallo entre más nodos, reduciendo el número medio de usuarios afectados cuando cae un `worker MEC` activo."
        )
    if multi_summary["probability_user_affected_active_mec"] < random_summary["probability_user_affected_active_mec"]:
        observations.append(
            "Multi-Agent reduce el riesgo medio condicionado a caída de un `worker MEC` activo frente a la referencia aleatoria."
        )
    if random_summary["total_assignments"] < random_summary["deployed_users"]:
        observations.append(
            "En `random`, el número de asignaciones observadas es inferior al número de usuarios desplegados; el informe se basa en las asignaciones con ejecución observada en traza."
        )

    observation_lines = "\n".join(f"- {item}" for item in observations) if observations else "- No notable differences detected."

    app_sections: list[str] = []
    for app_name in sorted(app_summaries):
        app_sections.append(
            build_app_summary_table(
                app_name,
                summaries=app_summaries[app_name],
            )
        )

    return "\n".join(
        [
            "# MEC Failure Impact Report",
            "",
            "## Inputs",
            "",
            f"- Topology: `{topology}`",
            f"- Random trace: `{random_trace}`",
            f"- Greedy trace: `{greedy_trace}`",
            f"- Multi-Agent trace: `{multi_trace}`",
            "",
            "## Summary",
            "",
            summary_table,
            "",
            "## Interpretation",
            "",
            observation_lines,
            "",
            *[
                part
                for scenario_name in SCENARIO_ORDER
                for part in (
                    f"## Most Impactful MEC Workers: {scenario_name}",
                    "",
                    build_top_nodes_table(summaries[scenario_name], top_nodes=top_nodes),
                    "",
                )
            ],
            "## Per-Application Breakdown",
            "",
            *app_sections,
        ]
    )


def main() -> None:
    args = parse_args()
    mec_nodes = load_mec_worker_nodes(args.topology)

    trace_paths = {
        "Random": resolve_trace_path(args.random_trace),
        "Greedy": resolve_trace_path(args.greedy_trace),
        "Multi-Agent": resolve_trace_path(args.multi_trace),
    }
    frames: dict[str, pd.DataFrame] = {}
    assignments: dict[str, pd.DataFrame] = {}
    summaries: dict[str, dict] = {}
    per_app_by_scenario: dict[str, dict[str, dict]] = {name: {} for name in SCENARIO_ORDER}
    for scenario_name, trace_path in trace_paths.items():
        frame, assignment_nodes = reconstruct_user_assignments(trace_path)
        frames[scenario_name] = frame
        assignments[scenario_name] = assignment_nodes
        summaries[scenario_name] = summarize_failure_impact(frame, assignment_nodes, mec_nodes=mec_nodes)
        per_app_by_scenario[scenario_name] = summarize_by_app(frame, assignment_nodes, mec_nodes=mec_nodes)

    app_summaries: dict[str, dict[str, dict]] = {}
    empty_summary = summarize_failure_impact(pd.DataFrame(), pd.DataFrame(), mec_nodes=set())
    for app_name in sorted(
        {
            app
            for mapping in per_app_by_scenario.values()
            for app in mapping.keys()
        }
    ):
        app_summaries[app_name] = {
            scenario_name: per_app_by_scenario.get(scenario_name, {}).get(app_name, empty_summary)
            for scenario_name in SCENARIO_ORDER
        }

    report = build_report(
        summaries=summaries,
        app_summaries=app_summaries,
        top_nodes=int(args.top_nodes),
        random_trace=trace_paths["Random"],
        greedy_trace=trace_paths["Greedy"],
        multi_trace=trace_paths["Multi-Agent"],
        topology=args.topology,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
