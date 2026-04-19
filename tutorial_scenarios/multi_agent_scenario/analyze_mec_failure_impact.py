from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    scenario_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Estimate the impact of a MEC-node failure on users for random and greedy experiments."
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
    return parser.parse_args()


def load_mec_worker_nodes(topology_path: Path) -> set[str]:
    payload = json.loads(topology_path.read_text(encoding="utf-8"))
    mec_nodes: set[str] = set()
    for cluster in payload.get("clusters", []):
        if str(cluster.get("role")) != "MEC":
            continue
        for node in cluster.get("nodes", []):
            if str(node.get("role")) != "worker":
                continue
            node_name = node.get("name")
            if node_name is not None:
                mec_nodes.add(str(node_name))
    return mec_nodes


def reconstruct_user_assignments(trace_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = pd.read_csv(trace_path)
    src = frame[frame["type"] == "SRC_M"].copy()
    comp = frame[frame["type"] == "COMP_M"].copy()

    src["user_des"] = pd.to_numeric(src["DES.src"], errors="coerce")
    comp["node"] = comp["TOPO.dst"].astype(str)

    request_map = src[["id", "app", "user_des"]].drop_duplicates()
    merged = comp.merge(request_map, on=["id", "app"], how="inner")
    merged["assignment_key"] = (
        merged["user_des"].astype("Int64").astype(str) + "::" + merged["app"].astype(str)
    )

    assignment_nodes = (
        merged.groupby(["assignment_key", "user_des", "app"], dropna=False)["node"]
        .agg(lambda values: sorted(set(str(value) for value in values)))
        .reset_index()
    )
    return frame, assignment_nodes


def summarize_failure_impact(
    frame: pd.DataFrame,
    assignment_nodes: pd.DataFrame,
    *,
    mec_nodes: set[str],
) -> dict:
    src_rows = frame[frame["type"] == "SRC_M"].copy() if not frame.empty else pd.DataFrame()
    deployed_users = int(src_rows["DES.src"].nunique()) if not src_rows.empty else 0

    if assignment_nodes.empty:
        return {
            "deployed_users": deployed_users,
            "total_assignments": 0,
            "mec_nodes_total": len(mec_nodes),
            "mec_nodes_with_hosted_apps": 0,
            "average_affected_users_all_mec": 0.0,
            "average_affected_users_active_mec": 0.0,
            "probability_user_affected_all_mec": 0.0,
            "probability_user_affected_active_mec": 0.0,
            "per_node": [],
        }

    per_node: list[dict] = []
    total_assignments = int(assignment_nodes["assignment_key"].nunique())

    for mec_node in sorted(mec_nodes):
        mask = assignment_nodes["node"].apply(lambda nodes: mec_node in nodes)
        affected = int(mask.sum())
        per_node.append(
            {
                "mec_node": mec_node,
                "affected_users": affected,
                "affected_probability": affected / total_assignments if total_assignments > 0 else 0.0,
            }
        )

    active_nodes = [item for item in per_node if item["affected_users"] > 0]
    avg_all = sum(item["affected_users"] for item in per_node) / len(per_node) if per_node else 0.0
    avg_active = sum(item["affected_users"] for item in active_nodes) / len(active_nodes) if active_nodes else 0.0
    prob_all = avg_all / total_assignments if total_assignments > 0 else 0.0
    prob_active = avg_active / total_assignments if total_assignments > 0 else 0.0

    return {
        "deployed_users": deployed_users,
        "total_assignments": total_assignments,
        "mec_nodes_total": len(per_node),
        "mec_nodes_with_hosted_apps": len(active_nodes),
        "average_affected_users_all_mec": avg_all,
        "average_affected_users_active_mec": avg_active,
        "probability_user_affected_all_mec": prob_all,
        "probability_user_affected_active_mec": prob_active,
        "per_node": sorted(per_node, key=lambda item: (-item["affected_users"], item["mec_node"])),
    }


def print_summary(label: str, summary: dict) -> None:
    print(f"\n{label}")
    print(f"  deployed_users={summary['deployed_users']}")
    print(f"  total_user_app_assignments={summary['total_assignments']}")
    print(f"  mec_nodes_total={summary['mec_nodes_total']}")
    print(f"  mec_nodes_with_hosted_apps={summary['mec_nodes_with_hosted_apps']}")
    print(f"  average_affected_users_all_mec={summary['average_affected_users_all_mec']:.2f}")
    print(f"  average_affected_users_active_mec={summary['average_affected_users_active_mec']:.2f}")
    print(
        "  probability_user_affected_all_mec="
        f"{100.0 * summary['probability_user_affected_all_mec']:.2f}%"
    )
    print(
        "  probability_user_affected_active_mec="
        f"{100.0 * summary['probability_user_affected_active_mec']:.2f}%"
    )
    print("  top_5_most_impactful_mec_nodes:")
    for item in summary["per_node"][:5]:
        print(
            f"    - node={item['mec_node']} "
            f"affected_users={item['affected_users']} "
            f"affected_probability={100.0 * item['affected_probability']:.2f}%"
        )


def main() -> None:
    args = parse_args()
    mec_nodes = load_mec_worker_nodes(args.topology)

    random_frame, random_assignments = reconstruct_user_assignments(args.random_trace)
    greedy_frame, greedy_assignments = reconstruct_user_assignments(args.greedy_trace)

    random_summary = summarize_failure_impact(random_frame, random_assignments, mec_nodes=mec_nodes)
    greedy_summary = summarize_failure_impact(greedy_frame, greedy_assignments, mec_nodes=mec_nodes)

    print_summary("Random scenario", random_summary)
    print_summary("Greedy scenario", greedy_summary)


if __name__ == "__main__":
    main()
