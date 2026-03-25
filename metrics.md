# Metrics Guide

This document summarizes the metrics currently available in YAIFS after
the metrics layer refactor.

YAIFS now exposes metrics from two complementary perspectives through the
compatible `yafs` Python package:

- `yafs.metrics.MetricsAnalyzer`: offline analysis over `*.csv` and `*_link.csv`
- `yafs.api.Simulation`: live metrics derived from the current deployment state

The design goal is to keep `core.py` unchanged while offering richer metrics on top of the existing simulator outputs and placement state.

## Metric Sources

There are three data sources behind these metrics:

- Event trace: `results.csv`
  It contains module execution events per request and per message.
- Link trace: `results_link.csv`
  It contains every network hop traversed by each message.
- Live simulation state:
  It includes deployed modules, deployed sources, node capacities, and topology attributes.

As a consequence:

- response-time and network-path metrics come from CSV traces
- CPU, RAM, placement utilization, and users-per-node come from the live simulation state
- placement cost is independent of simulation time and depends only on the deployed instances

## Available APIs

### Offline metrics

Main entry point:

```python
from yafs.metrics import MetricsAnalyzer

metrics = MetricsAnalyzer(
    defaultPath="results/sim_trace",
    app_definition=app_definition_json,
)
```

Useful methods:

- `message_instances()`
- `message_breakdown()`
- `link_breakdown()`
- `request_breakdown()`
- `service_path_breakdown()`
- `service_response()`
- `summarize_service_response()`
- `application_execution_cost_breakdown(topology)`
- `summarize_application_execution_cost(topology)`
- `summarize_application_execution_metrics(topology)`
- `estimate_egress_cost(node_regions, cost_per_gb)`
- `link_utilization(topology, include_unused=False)`
- `request_hops(app_name=None)`
- `average_application_response_latency(...)`
- `request_distance_breakdown(topology, app_name=None)`
- `application_distance_breakdown(topology)`
- `mean_topology_congestion(topology)`
- `total_bandwidth_used(topology)`
- `total_bandwidth_available(topology)`
- `total_links(topology)`

Backward-compatible aliases are still available:

- `application_cost_breakdown(...)`
- `summarize_application_cost(...)`
- `summarize_application_metrics(...)`

These aliases still refer to execution-time cost, not placement cost.

### Live simulation metrics

Main entry point:

```python
from yafs.services.simulation_service import SimulationService

service = SimulationService()
report = service.get_network_metrics(simulation_id)
```

Or directly on the simulation object:

- `get_users_per_node()`
- `get_node_resource_summary(node_id=None)`
- `get_node_cpu_summary(node_id)`
- `get_node_memory_summary(node_id)`
- `get_cluster_resource_summary()`
- `get_network_metrics_summary(...)`
- `get_application_metrics_summary(...)`

Application metrics can also be restricted to a time interval by using
`from_time`, `to_time`, and `time_column`. At the `SimulationService` layer,
`reference_time` can be passed when those bounds should be interpreted relative
to a numeric origin chosen explicitly by the caller.

## Metrics Catalog

### 1. Node utilization

Source:
- live deployment state

API:
- `Simulation.get_node_resource_summary()`

Returned values per node:

- `cpu_used`
- `cpu_available`
- `cpu_total`
- `ram_used`
- `ram_available`
- `ram_total`
- `cpu_utilization`
- `ram_utilization`
- `utilization`
- `deployments`
- `users`

Definition:

- `cpu_used`: sum of the `cpu` requirements of all deployed modules on that node
- `ram_used`: sum of the `ram` requirements of all deployed modules on that node
- `cpu_total`: node capacity from `topology.json`
- `ram_total`: node capacity from `topology.json`
- `cpu_available = max(cpu_total - cpu_used, 0)`
- `ram_available = max(ram_total - ram_used, 0)`
- `cpu_utilization = cpu_used / cpu_total`
- `ram_utilization = ram_used / ram_total`
- `utilization = (cpu_utilization + ram_utilization) / 2`

Notes:

- Node utilization is placement-based, not time-based.
- CPU capacity accepts values such as `"2.0"` or `"500m"`.
- Memory capacity accepts values such as `"4096m"`, `"512Mi"`, or `"4Gi"`.

### 2. CPU available and total for a node

Source:
- live deployment state

API:
- `Simulation.get_node_cpu_summary(node_id)`

Returned fields:

- `cpu_used`
- `cpu_available`
- `cpu_total`
- `cpu_utilization`

### 3. RAM available and total for a node

Source:
- live deployment state

API:
- `Simulation.get_node_memory_summary(node_id)`

Returned fields:

- `ram_used`
- `ram_available`
- `ram_total`
- `ram_utilization`

### 4. Cluster utilization

Source:
- live deployment state

API:
- `Simulation.get_cluster_resource_summary()`

Definition:

Each cluster aggregates the node-level CPU and RAM metrics:

- `cluster_cpu_used = sum(node.cpu_used)`
- `cluster_cpu_total = sum(node.cpu_total)`
- `cluster_ram_used = sum(node.ram_used)`
- `cluster_ram_total = sum(node.ram_total)`
- `cluster_cpu_utilization = cluster_cpu_used / cluster_cpu_total`
- `cluster_ram_utilization = cluster_ram_used / cluster_ram_total`
- `cluster_utilization = (cluster_cpu_utilization + cluster_ram_utilization) / 2`

Returned fields also include:

- `deployments`
- `users`
- `nodes`

### 5. Number of users assigned to each node

Source:
- live deployment state

API:
- `Simulation.get_users_per_node()`

Definition:

It counts the deployed source processes in `alloc_source` grouped by topology node.

### 6. Link utilization

Source:
- link trace `*_link.csv`

API:
- `MetricsAnalyzer.link_utilization(topology, include_unused=False)`

Returned fields per physical link:

- `messages`
- `requests`
- `total_size`
- `latency_mean`
- `buffer_mean`
- `bandwidth_used`
- `bandwidth_available`
- `utilization`
- `distance_km`

Definition:

- `bandwidth_used = total_transmitted_size / observation_window`
- `bandwidth_available = edge.BW`
- `utilization = bandwidth_used / bandwidth_available`

Notes:

- This is an average utilization over the observed metrics window, not an instantaneous one.
- If `include_unused=True`, the result also includes links with zero traffic.

### 7. Total hops of a request

Source:
- link trace `*_link.csv`

API:
- `MetricsAnalyzer.request_hops(app_name=None)`

Definition:

- `total_hops = number of rows in _link.csv for that (request id, app)`

This counts the complete network traversal of the request across all messages of the service.

### 8. Mean response latency of an application

Source:
- event trace plus service definition

API:
- `MetricsAnalyzer.average_application_response_latency(...)`
- `MetricsAnalyzer.summarize_service_response(...)`
- `Simulation.get_application_metrics_summary(...)`

Definition:

The response is reconstructed from the service path defined in `services_VNF_definition.json`, including the backward return when `has_backward_return` is enabled or the last message has `d == "None"`.

### 9. Total distance in kilometres traversed by a service

Source:
- link trace plus topology distances

API:
- `MetricsAnalyzer.request_distance_breakdown(topology, app_name=None)`
- `MetricsAnalyzer.application_distance_breakdown(topology)`

Definition:

For each request:

- sum the `distanceKm` of every traversed edge in `_link.csv`

Assumption:

- intra-cluster links are treated as negligible distance when `distanceKm` is omitted

Implementation support in topology:

- `Topology.get_edge_distance(...)`
- `Topology.path_distance(...)`
- `Topology.shortest_path_distance(...)`

### 10. Mean congestion level of the whole topology

Source:
- link trace plus topology

API:
- `MetricsAnalyzer.mean_topology_congestion(topology)`

Definition:

- arithmetic mean of `utilization` across all physical links
- includes unused links with utilization `0`

### 11. Total bandwidth used

Source:
- link trace plus topology

API:
- `MetricsAnalyzer.total_bandwidth_used(topology)`

Definition:

- sum of the average `bandwidth_used` over all observed links

### 12. Total bandwidth available

Source:
- topology

API:
- `MetricsAnalyzer.total_bandwidth_available(topology)`
- `Topology.total_bandwidth()`

Definition:

- sum of `BW` over all physical links in the topology

### 13. Total number of links

Source:
- topology

API:
- `MetricsAnalyzer.total_links(topology)`
- `Topology.total_links()`

Definition:

- number of physical edges in the topology graph

## Cost Semantics

YAIFS now distinguishes two cost concepts:

### Execution cost

Source:
- CSV traces plus topology node `COST`

API:
- `application_execution_cost_breakdown(...)`
- `summarize_application_execution_cost(...)`
- `summarize_application_execution_metrics(...)`

Definition:

- execution time aggregated per node multiplied by the node `COST`

This depends on workload and simulation duration.

### Placement cost

Source:
- live deployment state plus topology node `COST`

API:
- `Simulation.get_application_metrics_summary(...)`

Definition:

- sum of the `COST` of the nodes where the application has deployed module instances

This is independent of the number of requests and of the simulated time.

### Time-windowed application metrics

Source:
- reconstructed service response from `*.csv` and `*_link.csv`

API:
- `Simulation.get_application_metrics_summary(...)`
- `SimulationService.get_application_metrics(...)`

Definition:

- first reconstruct one response row per request
- then keep only the rows whose temporal coordinate falls inside the requested
  interval
- finally aggregate requests, response mean, percentiles, waiting time, network
  time, and costs over that filtered subset

Request counters semantics:

- `requests_total`: total number of requests emitted by users for the application
  inside the analysed interval
- `requests_successful`: subset of `requests_total` whose service completed
  successfully
- `requests_unsuccessful`: subset of `requests_total` whose service did not
  complete successfully

Invariant:

- `requests_total = requests_successful + requests_unsuccessful`

Parameters:

- `from_time`: lower bound of the interval
- `to_time`: upper bound of the interval
- `time_column`: temporal axis used for filtering, usually `end_time` or `start_time`
- `reference_time`: optional extra origin accepted by `SimulationService`; when
  provided, absolute bounds become `reference_time + from_time` and
  `reference_time + to_time`

This is useful when a branch must be analysed only after a deployment change,
after a node failure, or after any other user-selected simulation time.

## Typical Example

```python
from pathlib import Path

from yafs.api import Infrastructure, Simulation
from yafs.metrics import MetricsAnalyzer

scenario = Path("lab_scenarios/case_three_cluster/three-cluster")

infrastructure = Infrastructure(path_to_lab_scenario=scenario)
simulation = Simulation(infrastructure=infrastructure, seed=2026)

simulation.run_for(duration=10000, step=2000.0)

node_metrics = simulation.get_node_resource_summary()
cluster_metrics = simulation.get_cluster_resource_summary()
network_metrics = simulation.get_network_metrics_summary()

analyzer = MetricsAnalyzer(
    defaultPath=simulation.results_path,
    app_definition=infrastructure.service_definitions_data,
)

response = analyzer.average_application_response_latency()
links = analyzer.link_utilization(infrastructure.topology, include_unused=True)
distance = analyzer.application_distance_breakdown(infrastructure.topology)
```

## Assumptions and Current Limits

- Resource utilization uses the module requirements defined in `services_VNF_definition.json`.
- CPU and RAM utilization do not model transient runtime consumption; they model deployed reservation.
- Bandwidth utilization is computed as an average over the observed trace window.
- Inter-cluster distance must be defined in `topology.json` through `distanceKm` if you want non-zero values.
- Intra-cluster links are assumed to have negligible distance when not explicitly defined.
