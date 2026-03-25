# Unified Core-Layer Scenario: the legacy

This tutorial scenario consolidates the behavior showcased in the YAFS repository:
- `tutorial_scenarios/01_basicExample`
- `tutorial_scenarios/02_serviceMovement`
- `tutorial_scenarios/03_topologyChanges`
- `tutorial_scenarios/04_userMovement`

The goal is to demonstrate, in one run, how YAIFS still handles the same raw primitives defined in YAFS:
- initial deployment and traffic generation
- dynamic service relocation
- dynamic topology mutations
- dynamic user lifecycle and movement

## What This Experiment Simulates

The script `main.py` creates a topology, deploys applications and users, and
then applies runtime changes through a custom DES monitor (`UnifiedDynamics`).
This produces a single experiment where infrastructure and demand evolve over
time.

## Topology

- Base topology: `networkx.generators.binomial_tree(size=5)`.
- Node attribute:
  - `IPT=100` for every node.
- Edge attributes:
  - `PR=1`, `BW=1` for initial edges.
- Initial graph export:
  - `results/graph_binomial_tree_5.gexf`.
- Final graph export after dynamic changes:
  - `results/final_topology.gexf`.

## Applications and Placement

- 7 applications (`id` from `0` to `6`).
- Each app has one module (`<app_id>_01`) and one user message
  (`M.USER.APP.<app_id>`).
- Initial placement deploys all service modules on node `0` using
  `JSONPlacement`.
- Routing policy: `DeviceSpeedAwareRouting`.

## Users

Two user types coexist in this scenario:

- Static users:
  - Four initial users are deployed at nodes `1`, `2`, `3`, and `4`.
  - They generate deterministic traffic based on configured lambda values.
- Dynamic users:
  - Created/updated/removed at runtime by the custom monitor.
  - Each dynamic user is attached to a random app and a random node.

## Custom DES Runtime Behavior (`UnifiedDynamics`)

The custom monitor is deployed with:
- Start time: `stop_time / 4`
- Period: `stop_time / 20`

On each activation it invalidates routing cache and may perform the following:

- Topology mutation:
  - Triggered with 50% probability.
  - If triggered:
    - 70% chance: add a new node (`IPT=100`) connected to two random nodes
      (`BW=10`, `PR=10`).
    - 30% chance: remove a random node that is not node `0` and has no active
      entities.
- Service movement:
  - Triggered with 60% probability.
  - Iterates deployed services and relocates them to random nodes if there is
    no duplicate instance already on target.
- User lifecycle:
  - If no dynamic users exist, creates one.
  - Otherwise:
    - 60% create a new dynamic user.
    - 20% move one dynamic user to another random node.
    - 20% remove one dynamic user.

## Output Files

After execution, files are generated in `results/`:

- `sim_trace.csv`: request-level service trace created by the core simulator.
- `sim_trace_link.csv`: network-level message trace created by the core simulator.
- `graph_binomial_tree_5.gexf`: initial topology.
- `final_topology.gexf`: topology at simulation end.

In addition, the script prints the final DES-process assignments, including their topology location (TOPO), the deployed service/application type (SRC.Mod), and other customized modules such as users (Modules).

```text
----------------------------------------
DES     | TOPO  | Src.Mod       | Modules
----------------------------------------
0       | 1     | M.USER.APP.0  | --
1       | 2     | M.USER.APP.1  | --
2       | 3     | M.USER.APP.2  | --
3       | 4     | M.USER.APP.3  | --
13      | 12    | M.USER.APP.3  | --
15      | 29    | M.USER.APP.5  | --
30      | 15    | M.USER.APP.4  | --
38      | 22    | M.USER.APP.2  | --
45      | 11    | M.USER.APP.6  | --
53      | 17    | M.USER.APP.0  | --
54      | 19    | M.USER.APP.3  | --
62      | 8     | M.USER.APP.5  | --
77      | 1     | M.USER.APP.6  | --
78      | 15    | --            | 0_01
79      | 22    | --            | 1_01
80      | 3     | --            | 2_01
81      | 32    | --            | 3_01
82      | 9     | --            | 4_01
83      | 2     | --            | 5_01
84      | 8     | --            | 6_01
85      | 11    | M.USER.APP.2  | --
----------------------------------------
```

## Run

From this directory:

```bash
uv run main.py
```

## Why This Scenario Is Useful

We want to preserve the simulator's legacy behavior. YAFS still works well, but as you will notice, its primitives are difficult to understand and use terminology that is closer to a discrete-event simulation model.

