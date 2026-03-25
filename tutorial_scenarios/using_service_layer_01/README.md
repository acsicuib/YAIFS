# Service-Layer Scenario: Topology Changes With Forks

This tutorial adapts the behavior of:
- `tutorial_scenarios/03_topologyChanges`

but implemented with:
- `yafs.services.simulation_service.SimulationService`

The objective is to compare four simulation branches created from forks:
- `S0`: root simulation (no node failures)
- `S1`: one node failure
- `S2`: two cumulative node failures
- `S3`: three cumulative node failures

## Forking Strategy

The script starts from a root simulation and runs an initial warmup window.
Then, before each new failure, it creates a fork:

1. `S1` is forked from `S0`, then the first node is removed.
2. `S2` is forked from `S1`, then the second node is removed.
3. `S3` is forked from `S2`, then the third node is removed.

This preserves a clean branch structure to compare:
- baseline (`S0`)
- 1-failure branch (`S1`)
- 2-failure branch (`S2`)
- 3-failure branch (`S3`)

## Scenario Configuration

This folder includes a three-cluster scenario, similar to:
- `lab_scenarios/case_three_cluster/three-cluster`

Files:
- `topology.json`
- `services.json`
- `placements.json`
- `users.json`
- `logging.ini`

## Output

After running, the script prints:
- timeline summary for `S0/S1/S2/S3`,
- topology inventory per branch,
- application metrics per branch.

Results are written under:
- `results/`

```text
tutorial_scenarios/using_service_layer/results
├── sim_trace_sim-1239f7a1.csv
├── sim_trace_sim-1239f7a1_link.csv
├── sim_trace_sim-132a0faf.csv
├── sim_trace_sim-132a0faf_link.csv
...
```

In addition some prints are done:

```text
...
Timeline summary:
  S0 (0 failures) -> now=20000.0
  S1 (1 failure) -> now=20000.0
  S2 (2 failures) -> now=20000.0
  S3 (3 failures) -> now=20000.0

Topology summary:
S0: nodes=8, clusters=3, node_names=['cdc-0-control-plane', 'cdc-0-worker-1', 'edc-0-control-plane', 'edc-0-worker-1', 'edc-0-worker-2', 'mec-0-control-plane', 'mec-0-worker-1', 'mec-0-worker-2']
S1: nodes=7, clusters=3, node_names=['cdc-0-control-plane', 'cdc-0-worker-1', 'edc-0-control-plane', 'edc-0-worker-1', 'edc-0-worker-2', 'mec-0-control-plane', 'mec-0-worker-1']
S2: nodes=6, clusters=3, node_names=['cdc-0-control-plane', 'cdc-0-worker-1', 'edc-0-control-plane', 'edc-0-worker-1', 'edc-0-worker-2', 'mec-0-control-plane']
S3: nodes=5, clusters=3, node_names=['cdc-0-control-plane', 'cdc-0-worker-1', 'edc-0-control-plane', 'edc-0-worker-1', 'mec-0-control-plane']

Application metrics summary:
S0 (id=sim-7da57128):
  - app=Augmented Reality (AR), avg_response=69.90016, requests_total=198, successful=198, unsuccessful=0, placement_cost=0.24000000, total_cost=0.24000000
  - app=mIoTs, avg_response=35.60016, requests_total=99, successful=99, unsuccessful=0, placement_cost=0.07000000, total_cost=0.07000000
S1 (id=sim-9b619937):
  - app=Augmented Reality (AR), avg_response=69.90016, requests_total=198, successful=38, unsuccessful=160, placement_cost=0.17000000, total_cost=0.17000000
  - app=mIoTs, avg_response=26.46881, requests_total=99, successful=99, unsuccessful=0, placement_cost=0.07000000, total_cost=0.07000000
S2 (id=sim-e7151267):
  - app=Augmented Reality (AR), avg_response=nan, requests_total=138, successful=0, unsuccessful=138, placement_cost=0.10000000, total_cost=0.10000000
  - app=mIoTs, avg_response=24.30012, requests_total=99, successful=39, unsuccessful=60, placement_cost=0.00000000, total_cost=0.00000000
S3 (id=sim-c1cf8db6):
  - app=Augmented Reality (AR), avg_response=nan, requests_total=198, successful=0, unsuccessful=198, placement_cost=0.10000000, total_cost=0.10000000
  - app=mIoTs, avg_response=nan, requests_total=59, successful=0, unsuccessful=59, placement_cost=0.00000000, total_cost=0.00000000

````


## Run

From this directory:

```bash
uv run main.py
```
