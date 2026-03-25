=================
Metrics Overview
=================

YAIFS 3.1 exposes metrics from two complementary layers through the compatible
``yafs`` package:

- offline trace analysis through ``yafs.metrics.MetricsAnalyzer``
- live deployment metrics through ``yafs.api.Simulation`` and ``SimulationService``

This split keeps the simulator core stable while providing richer analytical views.

Trace-based metrics
===================

These metrics are reconstructed from ``*.csv`` and ``*_link.csv``:

- message response and waiting times
- service response per application
- request hops
- link utilization
- traversed distance in kilometres
- mean topology congestion
- total used bandwidth
- total available bandwidth
- total number of links
- execution-time cost

Key APIs:

- ``MetricsAnalyzer.link_utilization(topology, include_unused=False)``
- ``MetricsAnalyzer.request_hops(app_name=None)``
- ``MetricsAnalyzer.average_application_response_latency(...)``
- ``MetricsAnalyzer.request_distance_breakdown(topology, app_name=None)``
- ``MetricsAnalyzer.application_distance_breakdown(topology)``
- ``MetricsAnalyzer.mean_topology_congestion(topology)``
- ``MetricsAnalyzer.total_bandwidth_used(topology)``
- ``MetricsAnalyzer.total_bandwidth_available(topology)``
- ``MetricsAnalyzer.total_links(topology)``
- ``MetricsAnalyzer.summarize_application_execution_metrics(topology)``

Deployment-based metrics
========================

These metrics are computed from the live simulation state:

- utilization of each node
- available and total CPU per node
- available and total RAM per node
- utilization of each cluster
- number of users assigned to each node
- placement cost per application
- inventory of active nodes
- inventory of active clusters

Key APIs:

- ``Simulation.list_nodes()``
- ``Simulation.list_clusters()``
- ``Simulation.list_nodes_in_cluster(cluster_name)``
- ``Simulation.count_nodes()``
- ``Simulation.count_clusters()``
- ``Simulation.get_node_resource_summary(node_id=None)``
- ``Simulation.get_node_cpu_summary(node_id)``
- ``Simulation.get_node_memory_summary(node_id)``
- ``Simulation.get_cluster_resource_summary()``
- ``Simulation.get_users_per_node()``
- ``Simulation.get_application_metrics_summary(...)``
- ``Simulation.get_network_metrics_summary(...)``
- ``SimulationService.list_nodes(simulation_id)``
- ``SimulationService.list_clusters(simulation_id)``
- ``SimulationService.list_nodes_in_cluster(simulation_id, cluster_name)``
- ``SimulationService.count_nodes(simulation_id)``
- ``SimulationService.count_clusters(simulation_id)``
- ``SimulationService.get_application_metrics(simulation_id, ...)``
- ``SimulationService.get_network_metrics(simulation_id, ...)``

Time-windowed application metrics
=================================

Application metrics can be analysed on a bounded time interval instead of over
the full life of the simulation.

Both ``Simulation.get_application_metrics_summary(...)`` and
``SimulationService.get_application_metrics(...)`` accept:

- ``from_time``: lower bound of the interval
- ``to_time``: upper bound of the interval
- ``time_column``: temporal coordinate used to filter requests, typically
  ``"end_time"`` or ``"start_time"``

At the service layer, the caller may also provide ``reference_time``. In that
case, ``from_time`` and ``to_time`` are interpreted relative to that numeric
origin selected by the user.

Examples:

.. code-block:: python

    # Absolute simulation time window
    report = service.get_application_metrics(
        simulation_id,
        from_time=4000.0,
        to_time=8000.0,
    )

    # Window relative to an origin chosen by the caller
    report = service.get_application_metrics(
        simulation_id,
        from_time=0.0,
        to_time=2000.0,
        reference_time=4000.0,
    )

The returned application counters use the following semantics:

- ``requests_total``: total number of requests emitted by users for that
  application in the analysed interval
- ``requests_successful``: subset of ``requests_total`` whose service completed
  successfully
- ``requests_unsuccessful``: subset of ``requests_total`` that did not complete
  successfully

The intended invariant is:

- ``requests_total = requests_successful + requests_unsuccessful``

This is useful when a branch must be compared only after a topology mutation,
after a deployment action, or after any other simulation time chosen by the
user. It avoids diluting local degradations with the complete historical trace.

Important semantic distinction
==============================

YAIFS now distinguishes two cost models:

- ``execution cost``: depends on service time and simulation workload
- ``placement cost``: depends only on deployed instances and node ``COST``

The service-layer summaries exposed by ``Simulation`` use placement cost so the
reported deployment cost is independent of simulation duration and request volume.

Distance assumptions
====================

- inter-cluster distance is taken from ``topology.json`` through ``distanceKm``
- intra-cluster links are considered negligible distance when ``distanceKm`` is omitted

Reference
=========

A detailed catalog of formulas, semantics, and examples is available in
``metrics.md`` at the project root.
