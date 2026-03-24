=================
``yafs.services``
=================

.. automodule:: yafs.services
    :members:
    :undoc-members:
    :inherited-members:

SimulationService Topology Inventory
====================================

The high-level service layer exposes topology inventory actions over the live
state of each simulation:

- ``SimulationService.list_nodes(simulation_id)``
- ``SimulationService.list_clusters(simulation_id)``
- ``SimulationService.list_nodes_in_cluster(simulation_id, cluster_name)``
- ``SimulationService.count_nodes(simulation_id)``
- ``SimulationService.count_clusters(simulation_id)``
- ``SimulationService.create_cluster(simulation_id, definition)``
- ``SimulationService.create_nodes(simulation_id, definition)``
- ``SimulationService.update_node(simulation_id, node_id, cpu=..., memory=..., ram=..., cost=...)``
- ``SimulationService.remove_node(simulation_id, node_id)``
- ``SimulationService.remove_cluster(simulation_id, cluster_name)``

SimulationService Application Actions
=====================================

The high-level service layer also exposes application lifecycle and placement
actions over the live state of each simulation:

- ``SimulationService.create_application(simulation_id, definition)``
- ``SimulationService.create_users(simulation_id, definition, nodes=...)``
- ``SimulationService.remove_users_by_application(simulation_id, app_id)``
- ``SimulationService.remove_users_by_node(simulation_id, node_id)``
- ``SimulationService.remove_users_by_cluster(simulation_id, cluster_name)``
- ``SimulationService.list_users(simulation_id, app_id=..., node_id=..., cluster_name=...)``
- ``SimulationService.update_user_lambda(simulation_id, user_des, new_lambda)``
- ``SimulationService.update_application_users_lambda(simulation_id, app_id, new_lambda)``
- ``SimulationService.move_users_to_node(simulation_id, source_node_id, target_node_id)``
- ``SimulationService.list_deployed_applications(simulation_id)``
- ``SimulationService.list_application_vnfs(simulation_id, app_id)``
- ``SimulationService.list_node_placements(simulation_id, node_id)``
- ``SimulationService.deploy_application_vnfs(simulation_id, app_id, definition)``
- ``SimulationService.move_application_vnf(simulation_id, app_id, definition)``
- ``SimulationService.replicate_application_vnf(simulation_id, app_id, definition)``
- ``SimulationService.remove_application_vnf(simulation_id, app_id, definition)``
- ``SimulationService.remove_application_vnfs(simulation_id, app_id)``

These methods do not rely on the initial JSON scenario definition alone. They
query the topology currently attached to the simulation core, so they reflect
node additions, removals, and other dynamic changes that may occur during the
execution of the simulator. The application actions likewise inspect or mutate
the live DES deployments managed by the simulation core.

See also :doc:`../introduction/simulation_service`.
