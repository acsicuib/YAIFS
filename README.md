```text
██╗   ██╗ █████╗ ██╗███████╗███████╗
╚██╗ ██╔╝██╔══██╗██║██╔════╝██╔════╝
 ╚████╔╝ ███████║██║█████╗  ███████╗
  ╚██╔╝  ██╔══██║██║██╔══╝  ╚════██║
   ██║   ██║  ██║██║██║     ███████║
   ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝     ╚══════╝
```
⚡ YAIFS :: Yet Another Intelligent Fog System ⚡


YAIFS is released under the MIT License. However, we would like to know in which projects or publications you have used or mentioned YAIFS.

```text
           AI Agent
             │
+---------------+
|  MCP      ◀┘  | ◀── User
+---------------+
|  SERVICE  ◀┘  | ◀── User
+---------------+
|  API          | ◀── User
+---------------+
+---------------+
|  CORE         | ◀── User
+---------------+
```

**Please consider using the following citation when you use YAFS**:

```bash
    Pending

```

Bibtex:
```
    Pending
  
```

Resources
---------

- API
- USER GUIDE
- EXAMPLES
  


Installation
------------

YAIFS supports Python 3.12 (last compatibility check on Python 3.12).  YAIFS uses [uv](https://docs.astral.sh/uv/) as python project manager.

1. Clone the project in your local folder:

```bash
git clone https://github.com/acsicuib/YAIFS.git
```

2. Install dependencies:

```bash
cd YAIFS/
uv sync
uv pip install -e .
```

Getting started
---------------



MCP Client
----------
MCP client enables you to chat with 

To run a simple  configuration of MCP:

```bash
uv run python mcp-client/cli.py \
  --env-file mcp-client/.env \
  --server-command uv \
  --server-arg run \
  --server-arg python \
  --server-arg mcp-server/server.py \
  --server-arg --scenario-path \
  --server-arg lab_scenarios/case_three_cluster/three-cluster
```

You can find more information in specific folders /mcp-client and /mcp-server


Simulation Service API
----------------------

YAIFS includes a high-level `SimulationService` for long-lived simulations. In
this API, a simulation is conceptually open-ended and only becomes terminal when
`service.stop(...)` is invoked.

Key ideas:

* `service.schedule_for(simulation_id, duration=..., step=...)` schedules an incremental execution window. `duration` is relative to the current simulated time, not an absolute final time.
* `service.wait_until_ready(simulation_id)` waits until the simulation is ready for the next command. This usually means the scheduled window has finished and the status is `idle`.
* `service.pause(simulation_id)` pauses execution after the current internal `step` finishes.
* `service.fork(simulation_id)` waits until the parent simulation is paused or no longer running before cloning it.
* `service.stop(simulation_id)` is the terminal command. After `stop`, the simulation cannot be resumed or scheduled again.

Status semantics:

* `created`: the simulation exists but has not been initialized yet.
* `initialized`: the simulation has been initialized and is ready to run.
* `running`: the simulation is actively executing a scheduled window.
* `paused`: the simulation is paused and can be resumed or scheduled again.
* `idle`: the last scheduled window has finished and the simulation is ready for the next command.
* `stopped`: terminal state reached through `service.stop(...)`.
* `failed`: terminal state caused by an error.

Typical flow:

```python
from pathlib import Path

from yafs.services.simulation_service import SimulationService

service = SimulationService()
created = service.create_simulation(
    scenario_path=Path("lab_scenarios/case_three_cluster/three-cluster"),
    seed=2026,
    name="case-three-cluster",
)

service.schedule_for(created.summary.id, duration=20000, step=2000.0)
state = service.wait_until_ready(created.summary.id)

forked = service.fork(created.summary.id)
service.schedule_for(forked.summary.id, duration=20000, step=2000.0)
fork_state = service.wait_until_ready(forked.summary.id)

service.stop(created.summary.id)
service.stop(forked.summary.id)
```

Compatibility note:

* `service.run_for(...)` remains available as an alias of `service.schedule_for(...)`.
* `service.wait_until_idle(...)` remains available as an alias of `service.wait_until_ready(...)`.


Metrics
-------

YAFS 3.1 includes an expanded metrics layer with two complementary views:

* Offline analysis through `yafs.metrics.MetricsAnalyzer` over `*.csv` and `*_link.csv`
* Live deployment and infrastructure metrics through `Simulation` and `SimulationService`

The current catalog includes:

* node utilization
* CPU available and total per node
* RAM available and total per node
* cluster utilization
* users assigned per node
* link utilization
* total hops per request
* mean response latency per application
* traversed distance in kilometres per request and per application
* mean topology congestion
* total used bandwidth
* total available bandwidth
* total number of links
* execution cost and placement cost as separate concepts

Reference documents:

* [metrics.md](metrics.md)
* [Metrics Overview](docs/introduction/metrics.rst)




Documentation and Help
----------------------


Changelog
-----------
- 24/03/2026 The new version of YAFS, called YAIFS is published.

Acknowledgment
--------------

- The authors acknowledge financial support through grant project number PID2024-158637OB-I00 (AEI/FEDER, UE).
- Thanks to the small community of contributors who have been improving the code and providing new suggestions over the years.


Please [send us your reference so we can publish it](mailto:isaac.lera@uib.es)! And of course, feel free to add your references or works using YAIFS! 
