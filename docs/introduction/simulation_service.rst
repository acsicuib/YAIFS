==========================
Simulation Service Guide
==========================

YAIFS 3.1 includes a high-level ``SimulationService`` for long-lived simulations.
In this API, a simulation is conceptually open-ended and only becomes terminal
when ``service.stop(...)`` is invoked.

Key ideas
=========

- ``service.schedule_for(simulation_id, duration=..., step=...)`` schedules an incremental execution window. ``duration`` is relative to the current simulated time, not an absolute final time.
- ``service.wait_until_ready(simulation_id)`` waits until the simulation is ready for the next command. This usually means the scheduled window has finished and the status is ``idle``.
- ``service.pause(simulation_id)`` pauses execution after the current internal ``step`` finishes.
- ``service.fork(simulation_id)`` waits until the parent simulation is paused or no longer running before cloning it.
- ``service.stop(simulation_id)`` is the terminal command. After ``stop``, the simulation cannot be resumed or scheduled again.

Status semantics
================

- ``created``: the simulation exists but has not been initialized yet.
- ``initialized``: the simulation has been initialized and is ready to run.
- ``running``: the simulation is actively executing a scheduled window.
- ``paused``: the simulation is paused and can be resumed or scheduled again.
- ``idle``: the last scheduled window has finished and the simulation is ready for the next command.
- ``stopped``: terminal state reached through ``service.stop(...)``.
- ``failed``: terminal state caused by an error.

Dynamic topology inventory
==========================

``SimulationService`` also exposes high-level queries for nodes and clusters:

- ``service.list_nodes(simulation_id)``
- ``service.list_clusters(simulation_id)``
- ``service.list_nodes_in_cluster(simulation_id, cluster_name)``
- ``service.count_nodes(simulation_id)``
- ``service.count_clusters(simulation_id)``
- ``service.create_cluster(simulation_id, definition)``
- ``service.create_nodes(simulation_id, definition)``
- ``service.update_node(simulation_id, node_id, cpu=..., memory=..., ram=..., cost=...)``
- ``service.remove_node(simulation_id, node_id)``
- ``service.remove_cluster(simulation_id, cluster_name)``

These actions are evaluated against the live topology of the simulation,
not against the initial ``topology.json``. This distinction is important
because YAIFS can add or remove nodes during execution through simulator
events and strategies.

In practice, the inventory is derived from the current graph stored in the
simulation core (``sim.topology.G``), so the returned nodes and clusters
reflect the state that is actually active at that simulation time.

Creating clusters dynamically
=============================

``service.create_cluster(simulation_id, definition)`` adds a new cluster to the
live topology of the simulation. The ``definition`` can be a path to a JSON
file or a dictionary with the same structure used by the topology definition:

- ``clusters`` with the new cluster and its nodes
- ``links`` with the inter-cluster links that attach the new cluster to the
  existing topology

The action updates the graph managed by the simulator itself, not only the
scenario files on disk. Newly created nodes are added to ``sim.topology.G`` and
to the topology metadata used by other ``yafs`` components.

For safety, this topology mutation should be executed only when the simulation
is ready for the next command, for example after
``service.wait_until_ready(simulation_id)`` or while it is paused.

Example:

.. code-block:: python

    service.schedule_for(created.summary.id, duration=20000, step=2000.0)
    state = service.wait_until_ready(created.summary.id)

    created_cluster = service.create_cluster(
        created.summary.id,
        Path("lab_scenarios/case_three_cluster/three-cluster/add_new_cluster.json"),
    )

    print(created_cluster["cluster"])
    print(created_cluster["total_nodes"])
    print(created_cluster["total_clusters"])

Adding nodes to an existing cluster
===================================

``service.create_nodes(simulation_id, definition)`` adds one or more nodes to
an existing cluster in the live topology. Each node definition must include the
target cluster through ``on_cluster``.

After adding the nodes, the service automatically creates the intra-cluster
links needed to connect the new nodes with the rest of the nodes already active
in that cluster.

Example:

.. code-block:: python

    created_nodes = service.create_nodes(
        created.summary.id,
        Path("lab_scenarios/case_three_cluster/three-cluster/add_new_nodes.json"),
    )

    print(created_nodes["node_count"])
    print(created_nodes["clusters"])
    print(created_nodes["total_nodes"])

Updating node characteristics
=============================

``service.update_node(...)`` increments the live characteristics of an existing
node. The target node is identified directly by its identifier and the updated
fields are optional. One or more of these increments can be provided:

- ``cpu``
- ``memory``
- ``ram``
- ``cost``

``memory`` and ``ram`` are treated as increments over the node memory capacity.

Example:

.. code-block:: python

    updated_node = service.update_node(
        created.summary.id,
        "edc-cluster-new-1-worker-2",
        cpu="10",
        memory="512m",
        cost=0.25,
    )

    print(updated_node["node"])
    print(updated_node["cpu_total"])
    print(updated_node["memory_total"])
    print(updated_node["cost"])

Removing a node
===============

``service.remove_node(simulation_id, node_id)`` removes a node from the live
topology of the simulation and also stops the DES processes associated with
that node.

The action:

- removes VNF processes deployed on that node
- disconnects users assigned to that node
- removes the node from the topology graph
- returns a summary of affected services and detached processes

Example:

.. code-block:: python

    removed_node = service.remove_node(
        created.summary.id,
        "mec-0-worker-1",
    )

    print(removed_node["id_services_affected"])
    print(removed_node["number_of_undeployed_vnf"])
    print(removed_node["number_of_unplugged_users"])

Removing a cluster
==================

``service.remove_cluster(simulation_id, cluster_name)`` removes all nodes that
belong to the requested cluster from the live topology.

The action reuses the node-removal semantics for every node in the cluster, so
it also:

- undeploys VNFs hosted on that cluster
- disconnects users attached to those nodes
- stops the corresponding DES processes
- returns the affected and unavailable services in aggregated form

Application placement actions
=============================

``SimulationService`` also exposes high-level actions to register, inspect, and
change application placements in the live simulation state:

- ``service.create_application(simulation_id, definition)``
- ``service.create_users(simulation_id, definition, nodes=...)``
- ``service.remove_users_by_application(simulation_id, app_id)``
- ``service.remove_users_by_node(simulation_id, node_id)``
- ``service.remove_users_by_cluster(simulation_id, cluster_name)``
- ``service.list_users(simulation_id, app_id=..., node_id=..., cluster_name=...)``
- ``service.update_user_lambda(simulation_id, user_des, new_lambda)``
- ``service.update_application_users_lambda(simulation_id, app_id, new_lambda)``
- ``service.move_users_to_node(simulation_id, source_node_id, target_node_id)``
- ``service.list_deployed_applications(simulation_id)``
- ``service.list_application_vnfs(simulation_id, app_id)``
- ``service.list_node_placements(simulation_id, node_id)``
- ``service.deploy_application_vnfs(simulation_id, app_id, definition)``
- ``service.move_application_vnf(simulation_id, app_id, definition)``
- ``service.replicate_application_vnf(simulation_id, app_id, definition)``
- ``service.remove_application_vnf(simulation_id, app_id, definition)``
- ``service.remove_application_vnfs(simulation_id, app_id)``

These actions mutate or inspect the current simulator state, not only the JSON
files used to bootstrap the scenario.

Creating an application
=======================

``service.create_application(simulation_id, definition)`` registers a new
application definition in the simulator using the same JSON structure as
``services_VNF_definition.json``.

The action only registers the application:

- it does not deploy VNFs
- it does not create users
- it makes the application available for later placement actions

Creating users
==============

``service.create_users(simulation_id, definition, nodes=...)`` creates one or
more user sources for already registered applications.

The ``definition`` follows the same schema as ``usersDefinition.json`` and must
contain a ``sources`` list. Each source typically includes:

- ``app``
- ``message``
- ``lambda``
- optionally ``id_resource``

The ``nodes`` argument is optional:

- if omitted, each source uses the ``id_resource`` declared in the JSON
- if provided, the action overrides ``id_resource`` and creates one user per
  source and per node listed in ``nodes``

When the simulation is already initialized, this action immediately creates the
corresponding source DES processes in the simulator. Otherwise, the users are
registered and will be deployed during initialization.

Removing users
==============

``SimulationService`` also supports removing user sources already attached to
the live simulation:

- ``service.remove_users_by_application(simulation_id, app_id)`` removes all
  users that emit requests for the requested application
- ``service.remove_users_by_node(simulation_id, node_id)`` removes all users
  attached to one node
- ``service.remove_users_by_cluster(simulation_id, cluster_name)`` removes all
  users attached to nodes that belong to one cluster

All these actions stop the associated source DES processes and return the
removed users with their node, application, message, and DES identifier.

Listing users
=============

``service.list_users(simulation_id, app_id=..., node_id=..., cluster_name=...)``
returns the active user sources currently deployed in the simulation.

Each user entry includes:

- ``des``
- application identifier and name
- ``node``
- ``cluster``
- ``message``
- ``module``

All filters are optional. This means the same action can be used to inspect:

- all active users
- only the users of one application
- only the users attached to one node
- only the users attached to one cluster

Updating user request frequency
===============================

Two actions are available to change the request frequency of active users:

- ``service.update_user_lambda(simulation_id, user_des, new_lambda)``
- ``service.update_application_users_lambda(simulation_id, app_id, new_lambda)``

The first action updates one user identified by its DES identifier. The second
updates all active users that emit requests for a given application.

In both cases, the new value is written into the user record kept by the
simulator and into the mutable distribution object associated with that user,
so the new inter-arrival time is reflected by the live DES process.

Moving users to another node
============================

``service.move_users_to_node(simulation_id, source_node_id, target_node_id)``
reassigns all users currently attached to one node so their next requests are
emitted from another node.

The action updates the live user allocation inside the simulator, including the
DES-to-node mapping and the stored user definition, without recreating the user
processes.

Listing deployed applications
=============================

``service.list_deployed_applications(simulation_id)`` returns only the
identifiers of the applications that currently have at least one VNF deployed.

Listing application VNFs
========================

``service.list_application_vnfs(simulation_id, app_id)`` returns the VNFs of a
given application and the nodes where each replica is deployed.

Each VNF entry includes its deployment count and the list of DES processes with
their node and cluster.

Listing placements on a node
============================

``service.list_node_placements(simulation_id, node_id)`` returns the live
placements currently hosted on a specific node.

Each placement item includes:

- the application identifier
- the application name
- the VNF name
- the DES identifier attached to that deployment

This is useful to inspect the actual workload hosted by a node before moving,
replicating, or removing placements.

Deploying VNFs for an existing application
==========================================

``service.deploy_application_vnfs(simulation_id, app_id, definition)`` deploys
one or more VNFs of an already registered application.

The ``definition`` may provide either ``placements`` or
``initialAllocation``. Each entry accepts these aliases:

- ``module_name`` or ``vnf``
- ``id_resource`` or ``node``

This action creates the corresponding DES processes in the simulator.

Moving a deployed VNF
=====================

``service.move_application_vnf(simulation_id, app_id, definition)`` moves an
existing VNF replica from one node to another.

The action removes the original DES process and creates a new DES process on
the target node. If the VNF has multiple replicas, the source node must be
provided explicitly.

Replicating a deployed VNF
==========================

``service.replicate_application_vnf(simulation_id, app_id, definition)``
creates a new replica of an already deployed VNF on another node without
removing the original one.

The ``definition`` accepts the same target-node aliases used by the move
action:

- ``module_name`` or ``vnf``
- ``to_node``, ``target_node``, ``to``, ``id_resource``, or ``node``

The target node must exist in the live topology and must not already host the
same VNF replica.

Removing one deployed VNF
=========================

``service.remove_application_vnf(simulation_id, app_id, definition)`` removes
one deployed VNF module from an application.

The ``definition`` must provide the VNF name through ``module_name`` or
``vnf``. It may also provide a node selector through ``from_node``,
``source_node``, ``from``, ``id_resource``, or ``node``:

- if no node is provided, all replicas of that VNF are removed
- if a node is provided, only the replica deployed on that node is removed

The action stops the corresponding DES processes and returns the removed
replicas plus the number of remaining replicas for that module.

Removing all VNFs of an application
===================================

``service.remove_application_vnfs(simulation_id, app_id)`` removes every VNF
replica currently deployed for the given application and stops the associated
DES processes.

The application definition remains registered in the simulator, so it can be
deployed again later.

Typical flow
============

.. code-block:: python

    from pathlib import Path

    from yafs.services.simulation_service import SimulationService

    service = SimulationService()
    created = service.create_simulation(
        scenario_path=Path("lab_scenarios/case_three_cluster/three-cluster"),
        seed=2026,
        name="case-three-cluster",
    )

    service.schedule_for(created.summary.id, duration=20000, step=2000.0)

    node_count = service.count_nodes(created.summary.id)
    cluster_names = [
        item["cluster"]
        for item in service.list_clusters(created.summary.id)
    ]

    state = service.wait_until_ready(created.summary.id)

    print(node_count)
    print(cluster_names)
    print(state.summary.now)

Time-windowed application metrics
=================================

``SimulationService.get_application_metrics(...)`` can analyse only a selected
portion of the trace instead of the whole accumulated history.

The method accepts:

- ``from_time`` and ``to_time`` to define the interval
- ``reference_time`` when the caller wants those bounds to be relative to a
  user-chosen origin
- ``time_column`` to decide whether requests are filtered by ``"end_time"``
  or by another supported temporal coordinate such as ``"start_time"``

Examples:

.. code-block:: python

    # Absolute simulation times
    report = service.get_application_metrics(
        created.summary.id,
        from_time=4000.0,
        to_time=8000.0,
    )

    # Relative interval over an origin explicitly chosen by the user
    report = service.get_application_metrics(
        created.summary.id,
        from_time=0.0,
        to_time=2000.0,
        reference_time=4000.0,
    )

Application request counters follow this semantics:

- ``requests_total`` is the total number of requests emitted by users in the
  analysed interval
- ``requests_successful`` is the subset that completed successfully
- ``requests_unsuccessful`` is the subset that did not complete successfully

Therefore:

- ``requests_total = requests_successful + requests_unsuccessful``

The returned ``SimulationApplicationMetrics`` object preserves both the user
window and the resolved absolute bounds so downstream tools can display exactly
which interval was analysed.

Typical node and cluster payloads
=================================

``service.list_nodes(simulation_id)`` returns one item per active node:

.. code-block:: python

    {
        "node": "mec-0-worker-1",
        "cluster": "mec-0",
        "cluster_role": "MEC",
        "cluster_region": "region-b",
        "node_role": "worker",
    }

``service.list_clusters(simulation_id)`` returns one item per active cluster:

.. code-block:: python

    {
        "cluster": "mec-0",
        "cluster_role": "MEC",
        "cluster_region": "region-b",
        "nodes": ["mec-0-control-plane", "mec-0-worker-1"],
        "node_count": 2,
    }

Compatibility note
==================

- ``service.run_for(...)`` remains available as an alias of ``service.schedule_for(...)``.
- ``service.wait_until_idle(...)`` remains available as an alias of ``service.wait_until_ready(...)``.
