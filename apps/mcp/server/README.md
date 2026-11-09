# MCP Server

MCP server that exposes the YAIFS simulator using
`lab_scenarios/case_three_cluster/three-cluster` as the base scenario.

YAIFS is the public project branding. The Python package and imports remain
`yafs` for compatibility.

## Purpose

This server:

- creates a `SimulationService` instance
- exposes its operations as MCP tools
- uses the lab scenario as the default configuration
- communicates over `stdio`, designed to be launched by an MCP client

## Usage

Run with the default scenario:

```bash
uv run python apps/mcp/server/server.py
```

Expose one or more profiles. Repeat ``--profile`` to combine them. Omit it to expose every tool:

```bash
uv run python apps/mcp/server/server.py --profile experiment_designer
uv run python apps/mcp/server/server.py \
  --profile simulation_controller \
  --profile placement \
  --profile experiment_analyst
```

Profiles:

- ``experiment_designer`` creates scenarios, configurations, and simulations
- ``simulation_controller`` advances, pauses, observes, and changes processes, nodes, and clusters
- ``placement`` inspects the simulation, deploys and moves VNFs, advances and pauses the run, and queries metrics
- ``experiment_analyst`` queries metrics, topology, deployments, observed paths, and latency components

Placement reasoning uses four read-only analyst tools, in this order:

1. `get_topology` reads clusters, nodes, and configured links. `node_id` returns that node and its neighbors.
2. `get_deployments` reads where each VNF replica is placed. A service with no replica is undeployed.
3. `get_request_paths` groups requests that were actually traced. Link hops are recorded transmissions. A missing hop sequence is marked partial and is not replaced by a shortest path.
4. `get_latency_breakdown` separates measured link, queue, and processing time when the trace contains those times. The pieces are not required to add up to the end-to-end time.

After a placement change, advance the simulation and call the same tools again on the new window. Compare the observed groups and latency; the tools do not choose a placement.

Every profile also includes the read-only inventory: simulations, state, nodes, clusters, users, VNFs, placements, and processes.

Run with another scenario:

```bash
uv run python apps/mcp/server/server.py --scenario-path /path/to/scenario
```

Set default directories for generated configurations and results:

```bash
uv run python apps/mcp/server/server.py \
  --configurations-dir /path/configs \
  --results-dir /path/results
```

You can also provide them via environment variables:

- `YAFS_MCP_CONFIGURATIONS_DIR`
- `YAFS_MCP_RESULTS_DIR`

## Relevant Tools

In addition to the generic `yafs` MCP transport tools, this server adds:

- `get_default_scenario`
- `create_default_simulation`
- `create_default_simulation_configuration`
- `create_default_simulation_from_configuration`

The last two allow you to:

- generate a self-contained simulation configuration from the base
  scenario
- create a real simulation from that configuration

The configuration can be built by:

- specifying `cluster_count` and `nodes_per_cluster`
- specifying `topology_definition_path` with a topology JSON

The result is saved in `generated-configurations/<name>/` inside the
base scenario.

## Connection From the Client

Example with the `mcp-client` CLI:

```bash
uv run python apps/mcp/client/cli.py \
  --server-command uv \
  --server-arg run \
  --server-arg python \
  --server-arg apps/mcp/server/server.py
```

## Example Flow

1. Create a configuration with 4 clusters and 3 nodes per cluster

```text
create_default_simulation_configuration(
  configuration_name="four-clusters",
  cluster_count=4,
  nodes_per_cluster=3
)
```

2. Create a simulation using the generated configuration

```text
create_default_simulation_from_configuration(
  configuration_path=".../generated-configurations/four-clusters",
  seed=2026,
  name="four-clusters-run"
)
```
