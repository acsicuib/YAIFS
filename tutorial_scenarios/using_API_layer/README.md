# API-Layer Scenario: Service Movement

This tutorial scenario reproduces the semantics of:
- `tutorial_scenarios/02_serviceMovement`

but implemented with the API-layer primitives in:
- `src/yafs/api.py`

The goal is to show the same dynamic relocation behavior using the higher-level
runtime API (`Infrastructure`, `Simulation`, `register_process`,
`ProcessContext`) instead of directly manipulating the core simulator internals.

## What This Experiment Simulates

The script `main.py` loads a complete lab scenario from this folder
(`topology.json`, `services.json`, `placements.json`, `users.json`) and runs
the simulation while a custom process (`RandomServiceMovementProcess`) is
periodically activated.

On each activation, the process:
- inspects current VNF deployments,
- selects random destination nodes,
- moves VNFs using API operations.

This preserves the key behavior of the original `02_serviceMovement` tutorial:
service instances change location over time while requests keep arriving.

## Topology

This scenario uses a three-cluster topology:
- `mec-0`
- `edc-0`
- `cdc-0`

Each cluster contains control-plane and worker nodes defined in
`topology.json`, and inter-cluster links are also defined there.

## Applications, Placement, and Users

- Applications are loaded from `services.json`.
- Initial VNF placement is loaded from `placements.json`.
- Initial traffic sources are loaded from `users.json`.

All these artifacts are consumed through:
- `Infrastructure(path_to_lab_scenario=...)`
- `Simulation(infrastructure=..., seed=...)`

## Runtime Process (API Layer)

The movement process is registered with:
- `simulation.register_process(...)`
- distribution: `deterministicDistributionStartPoint(stop_time/4, stop_time/20)`

The callback receives a `ProcessContext` and uses:
- `context.list_nodes()`
- `context.list_application_vnfs(app_ref)`
- `context.move_application_vnf(app_ref, definition)`

This is the API-layer equivalent of the monitor strategy used in
`02_serviceMovement/main.py`.

## Output Files

After execution, files are generated in `results/`:
- `sim_trace.csv`: request-level service trace.
- `sim_trace_link.csv`: network-level message trace.

The script also prints a short summary in stdout, including:
- total network messages,
- total handled requests,
- sample request distribution by destination node.

## Run

From this directory:

```bash
uv run main.py
```
## Output Files

After execution, files are generated in `results/`:

In addition, some prints are generated with information and metrics about the simulation results:

```text
Number of total messages between nodes: 2017
Number of requests handled by deployed services: 990
   id    type                     app module   message  ...  service    time_in   time_out  time_emit time_reception
0   1   SRC_M  Augmented Reality (AR)    NaN  M.AR.0_0  ...      0.0  200.00000  200.00000  200.00000      200.00000
1   2   SRC_M  Augmented Reality (AR)    NaN  M.AR.0_0  ...      0.0  200.00000  200.00000  200.00000      200.00000
3   2  COMP_M  Augmented Reality (AR)   0_TM  M.AR.0_0  ...      0.3  201.00002  201.30002  200.00000      201.00002
4   2  COMP_M  Augmented Reality (AR)   0_VT  M.AR.0_1  ...      0.3  202.30004  202.60004  201.30002      202.30004
5   1  COMP_M  Augmented Reality (AR)   0_TM  M.AR.0_0  ...      0.3  212.00006  212.30006  200.00000      212.00006

[5 rows x 15 columns]
Different nodes where app Augmented Reality (AR) is deployed
['cdc-0-control-plane' 'cdc-0-worker-1' 'edc-0-control-plane'
 'edc-0-worker-1' 'edc-0-worker-2' 'mec-0-control-plane' 'mec-0-worker-1'
 'mec-0-worker-2']
Number of requests handled at each position: node_id - requests
TOPO.dst
cdc-0-control-plane     98
cdc-0-worker-1          60
edc-0-control-plane     50
edc-0-worker-1         179
edc-0-worker-2          60
mec-0-control-plane     70
mec-0-worker-1         197
mec-0-worker-2          78
```
## Why This Scenario Is Useful

It demonstrates how to implement dynamic runtime behavior with the new API
primitives while preserving the original YAFS service-movement semantics.
This makes custom behaviors easier to write and maintain than direct low-level
manipulation of simulator internals.

