# Multi-Agent Scenario

This scenario implements a simulation on the YAFS API layer for a large hierarchical environment with `CDC`, `EDC`, and `MEC` clusters.

## What this scenario models

- A multi-region topology with:
  - 3 `CDC` clusters
  - 10 `EDC` clusters
  - multiple `MEC` clusters associated with each `EDC`
- A catalog of 3 applications:
  - `Perception Pipeline`
  - `Coordination Pipeline`
  - `Telemetry Monitoring`
- An initial deployment of `20` application copies, placing their VNFs randomly on `worker` nodes
- A periodic process that creates users dynamically during the simulation
- Custom routing that assigns users to application replicas in round-robin

## Topology

The infrastructure definition is in:

- [topology.json](topology.json)

Main characteristics:

- `CDC`
  - `cdc-a-0`
  - `cdc-a-1`
  - `cdc-b-0`
- `EDC`
  - `edc-a` through `edc-j`
- `MEC`
  - each `EDC` has between 2 and 4 `MEC` clusters
  - each `MEC` has between 3 and 5 `workers`

## Applications

Applications are defined in:

- [services.json](services.json)

There are currently 3 applications:

- `Perception Pipeline` with 3 VNFs and p95 SLO `120`
- `Coordination Pipeline` with 2 VNFs and p95 SLO `75`
- `Telemetry Monitoring` with 1 VNF and p95 SLO `50`

The `latency_requirement` field is interpreted as a p95 service-response SLO in simulation time units.

## Main execution

The main script is:

- [main.py](main.py)

This script:

1. loads the topology and applications using `Infrastructure(...)`
2. starts with:
   - [empty_placements.json](empty_placements.json)
   - [empty_users.json](empty_users.json)
3. deploys `20` application replicas with random placement
4. registers a custom process that:
   - runs every `200` time units
   - generates `20` users per activation
   - picks one of the 3 applications at random
   - places users randomly on `worker` nodes in `MEC` clusters
5. stops the simulation `500` time units after the fifth activation

With the current configuration:

- activations: `t=200, 400, 600, 800, 1000`
- simulation end: `t=1500`

## Custom routing

This scenario does not use the default `DeviceSpeedAwareRouting`.

Instead it uses a custom selector defined in `main.py`:

- `CircularReplicaRouting`

Behavior:

- for each application it keeps a list of deployed replicas
- when a user requests an application for the first time, a replica is assigned in round-robin
- all subsequent requests from that user for the same application keep going to the same replica
- VNFs in the chain are also resolved within that same replica

Conceptual example:

- user 1 -> `app X`, replica 1
- user 2 -> `app X`, replica 2
- user 3 -> `app X`, replica 3
- ...
- user n -> `app X`, replica 1 again

## Metrics printed at the end

When the run finishes, `main.py` prints:

- VNF deployment summary per application
- placement cost per application
- number of `app_instances` vs `vnf_deployments`
- VNF distribution by cluster type:
  - `CDC`
  - `EDC`
  - `MEC`
- response time metrics:
  - `requests_total`
  - `requests_successful`
  - `requests_unsuccessful`
  - `response_mean`
  - `p50`
  - `p95`
  - `max`
- mean response time breakdown:
  - `network_mean`
  - `processing_mean`
  - `waiting_mean`

## Multi-agent placement (`main_multi_agent.py`)

[main_multi_agent.py](main_multi_agent.py) runs a monitoring agent and a placement agent on top of the YAFS MCP-style API. It steps the simulation in windows, observes congestion and overload, and applies placement actions within a budget.

The random, greedy, and multi-agent runs now share the same scripted `HotspotUsers` event for `Perception Pipeline` and configure MEC workers with `IPT=10.0`. In the multi-agent run, the overload-oriented thresholds let the placement agent react to that stress with replication, movement, and consolidation decisions.

### Results directory

Outputs go under the scenario directory unless you pass `--results-dir`:

- Default: `results_multi_agent/`

You can override the location explicitly:

```bash
uv run tutorial_scenarios/multi_agent_scenario/main_multi_agent.py \
  --results-dir tutorial_scenarios/multi_agent_scenario/results_multi_agent
```

### When artifacts are written

Files such as `window_metrics.json`, `mcp_interactions.jsonl`, `multi_agent_mcp_report.md`, and final placement snapshots are written **only after** the run completes the full window loop and finishes successfully. If the process exits with an error or is interrupted during simulation, that directory may be missing files or may not match what downstream scripts expect.

### Example

From the project root:

```bash
uv run tutorial_scenarios/multi_agent_scenario/main_multi_agent.py
```

After `Simulation Done!` appears, `window_metrics.json` should exist under `tutorial_scenarios/multi_agent_scenario/results_multi_agent/`.

## Auxiliary scripts

### Hierarchical topology visualization

- [plot_topology.py](plot_topology.py)

This script:

- loads `topology.json`
- builds a graph with `networkx`
- draws clusters at levels `CDC -> EDC -> MEC`

Usage:

```bash
uv run tutorial_scenarios/multi_agent_scenario/plot_topology.py
```

To save the figure:

```bash
uv run tutorial_scenarios/multi_agent_scenario/plot_topology.py \
  --output tutorial_scenarios/multi_agent_scenario/results/topology_layout.png \
  --no-show
```

### Temporal visualization of response time breakdown

- [plot_response_breakdown.py](plot_response_breakdown.py)

This script:

- reads:
  - `results/sim_trace.csv`
  - `results/sim_trace_link.csv`
- reconstructs per-application response using `MetricsAnalyzer`
- aggregates over time windows
- plots the temporal evolution of:
  - `Network`
  - `Processing`
  - `Waiting`
  - `Response mean`
- can also plot placement cost and deployed VNF counts with `--cost-output`; random and greedy placements are reconstructed through the YAFS API, while multi-agent uses the generated final placement snapshot.

Usage:

```bash
uv run tutorial_scenarios/multi_agent_scenario/plot_response_breakdown.py
```

To save the figure:

```bash
uv run tutorial_scenarios/multi_agent_scenario/plot_response_breakdown.py \
  --output tutorial_scenarios/multi_agent_scenario/results/response_breakdown.png \
  --no-show
```

To change temporal granularity:

```bash
uv run tutorial_scenarios/multi_agent_scenario/plot_response_breakdown.py --window 50
```

To save the placement cost/VNF comparison:

```bash
uv run tutorial_scenarios/multi_agent_scenario/plot_response_breakdown.py \
  --cost-output tutorial_scenarios/multi_agent_scenario/results_multi_agent/placement_cost_vnf_comparison.png \
  --no-show
```

### Multi-agent strategy timeline

- [plot_multi_agent_timeline.py](plot_multi_agent_timeline.py)

Reads `window_metrics.json` (and optionally `mcp_interactions.jsonl` for strategy labels) produced by `main_multi_agent.py` and plots congestion, overload, cost, and actions over time.

Defaults assume `results_multi_agent/` under this scenario directory. When you use a custom `--results-dir`, pass the same paths:

```bash
uv run tutorial_scenarios/multi_agent_scenario/plot_multi_agent_timeline.py \
  --window-metrics tutorial_scenarios/multi_agent_scenario/results_multi_agent/window_metrics.json \
  --mcp-log tutorial_scenarios/multi_agent_scenario/results_multi_agent/mcp_interactions.jsonl \
  --output tutorial_scenarios/multi_agent_scenario/results_multi_agent/multi_agent_strategy_timeline.png \
  --no-show
```

### Other entrypoints and reports

- [main_random.py](main_random.py), [main_greedy.py](main_greedy.py): alternate placement experiments.
- [analyze_mec_failure_impact.py](analyze_mec_failure_impact.py), [report_mec_failure_impact.py](report_mec_failure_impact.py): MEC failure analysis and reporting.
- [analyze_random_nominal_latency.py](analyze_random_nominal_latency.py), [report_deployment_costs.py](report_deployment_costs.py): additional analyses used by this tutorial layout.

## Auxiliary files

- [logging.ini](logging.ini)
- [empty_placements.json](empty_placements.json)
- [empty_users.json](empty_users.json)

These files let you run the scenario from the API layer without relying on a placement or static users defined up front.

## Running

From the project root:

```bash
uv run tutorial_scenarios/multi_agent_scenario/main.py
```

Multi-agent run (example):

```bash
uv run tutorial_scenarios/multi_agent_scenario/main_multi_agent.py
```
