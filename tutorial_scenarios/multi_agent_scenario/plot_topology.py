from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx


LEVEL_BY_ROLE = {
    "CDC": 0,
    "EDC": 1,
    "MEC": 2,
}

COLOR_BY_ROLE = {
    "CDC": "#d1495b",
    "EDC": "#edae49",
    "MEC": "#00798c",
}


def load_topology(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_cluster_graph(topology: dict) -> tuple[nx.Graph, dict[str, dict]]:
    graph = nx.Graph()
    cluster_index: dict[str, dict] = {}

    for cluster in topology["clusters"]:
        name = cluster["name"]
        role = cluster["role"]
        region = cluster.get("region", cluster.get("cluster_region", "unknown"))
        worker_count = sum(1 for node in cluster["nodes"] if node["role"] == "worker")

        cluster_index[name] = cluster
        graph.add_node(
            name,
            role=role,
            region=region,
            worker_count=worker_count,
            total_nodes=len(cluster["nodes"]),
            label=f"{name} | {region}\nworkers={worker_count}",
        )

    for link in topology["links"]:
        graph.add_edge(
            link["from"],
            link["to"],
            latency=link.get("targetOneWayLatencyMs"),
            distance=link.get("distanceKm"),
        )

    return graph, cluster_index


def hierarchical_layout(graph: nx.Graph) -> dict[str, tuple[float, float]]:
    groups: dict[int, list[str]] = {0: [], 1: [], 2: [], 3: []}

    for node, data in graph.nodes(data=True):
        level = LEVEL_BY_ROLE.get(data.get("role"), 3)
        groups[level].append(node)

    for names in groups.values():
        names.sort()

    positions: dict[str, tuple[float, float]] = {}
    y_by_level = {
        0: 2.0,
        1: 1.0,
        2: 0.0,
        3: -1.0,
    }

    for level, names in groups.items():
        if not names:
            continue

        count = len(names)
        for index, name in enumerate(names):
            x = 0.0 if count == 1 else index - (count - 1) / 2.0
            positions[name] = (x, y_by_level[level])

    return positions


def draw_graph(graph: nx.Graph, output_path: Path | None = None, show_plot: bool = True) -> None:
    positions = hierarchical_layout(graph)
    labels = {node: data["label"] for node, data in graph.nodes(data=True)}
    colors = [COLOR_BY_ROLE.get(data.get("role"), "#6c757d") for _, data in graph.nodes(data=True)]

    plt.figure(figsize=(24, 14))
    nx.draw_networkx_edges(graph, positions, alpha=0.35, width=1.4)
    nx.draw_networkx_nodes(
        graph,
        positions,
        node_color=colors,
        node_size=2500,
        edgecolors="#222222",
        linewidths=0.8,
    )
    nx.draw_networkx_labels(graph, positions, labels=labels, font_size=8)

    # plt.title("Multi-agent topology hierarchy (CDC -> EDC -> MEC)")
    plt.axis("off")
    plt.tight_layout()

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=200, bbox_inches="tight")

    if show_plot:
        plt.show()
    else:
        plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot a hierarchical view of the multi-agent scenario topology."
    )
    scenario_dir = Path(__file__).resolve().parent
    parser.add_argument(
        "--topology",
        type=Path,
        default=scenario_dir / "topology.json",
        help="Path to the topology JSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to save the generated figure.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not open a plot window; useful when only saving the figure.",
    )
    args = parser.parse_args()

    topology = load_topology(args.topology)
    graph, _ = build_cluster_graph(topology)
    draw_graph(graph, output_path=args.output, show_plot=not args.no_show)


if __name__ == "__main__":
    main()
