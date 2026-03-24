"""
Placement (allocation) algorithms for YAFS.

Each placement algorithm must provide two core methods:

* ``initial_allocation``: invoked at the start of the simulation.
* ``run``: invoked during the simulation according to the configured
  activation distribution.
"""

import logging
class Placement(object):
    """
    Base class for placement (allocation) algorithms.

    A placement algorithm controls where to locate service modules and their
    replicas on the different nodes of the topology, according to load
    criteria or other objectives.

    .. note:: A class interface

    Args:
        name (str): Associated name for the placement policy.

        activation_dist (Distribution): Distribution that determines when
            :meth:`run` is invoked during simulation time.

    Kwargs:
        param (dict): Parameters for ``activation_dist``.

    """

    def __init__(self, name, activation_dist=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.name = name
        self.activation_dist = activation_dist
        self.scaleServices = []


    def scaleService(self, scale):
        """
        Configure how many replicas of specific modules should be deployed.

        ``scale`` is usually a dictionary where keys are module names and
        values are the desired number of replicas.
        """
        self.scaleServices = scale

    def get_next_activation(self):
        """
        Return the next simulation time at which this placement should run.
        """
        return self.activation_dist.next()
    def initial_allocation(self, sim, app_name):
        """
        Perform the initial allocation of modules in the topology.

        Args:
            sim (:mod:`yafs.core.Sim`):
                Simulation object.

            app_name (str):
                Application identifier.

        .. attention:: override required
        """

    def run(self, sim):
        """
        (Optionally) change the assignment of the modules during simulation.

        Args:
            sim (:mod:`yafs.core.Sim`): Simulation object.
        """
        self.logger.debug("Activating - RUN - Placement")


class JSONPlacement(Placement):
    def __init__(self, json, **kwargs):
        super(JSONPlacement, self).__init__(**kwargs)
        self.data = json

    def initial_allocation(self, sim, app_name):
        """
        Allocate modules according to a JSON specification.

        The JSON structure is expected to contain an ``initialAllocation``
        list with elements of the form::

            {
                "app": "<app_name>",
                "module_name": "<module>",
                "id_resource": <node_id>
            }
        """
        for item in self.data["initialAllocation"]:
            if app_name == item["app"]:
                # app_name = item["app"]
                module = item["module_name"]
                idtopo = item["id_resource"]
                app = sim.apps[app_name]
                services = app.services
                sim.deploy_module(app_name, module, services[module], [idtopo])


class JSONPlacementOnCloud(Placement):
    def __init__(self, json, idCloud, **kwargs):
        super(JSONPlacementOnCloud, self).__init__(**kwargs)
        self.data = json
        self.idCloud = idCloud

    def initial_allocation(self, sim, app_name):
        """
        Allocate all modules of an application to a single cloud node.

        The JSON structure is similar to :class:`JSONPlacement`, but
        ``id_resource`` is ignored and ``idCloud`` is used instead.
        """
        for item in self.data["initialAllocation"]:
            if app_name == item["app"]:
                app_name = item["app"]
                module = item["module_name"]

                app = sim.apps[app_name]
                services = app.services
                sim.deploy_module(app_name, module, services[module], [self.idCloud])
class ClusterPlacement(Placement):
    """
    Place application services in a cluster of nodes.

    This implementation locates the services of the application in the
    "cluster" regardless of where the sources or sinks are located.

    It only runs once, in the initialization.

    """
    def initial_allocation(self, sim, app_name):
        # Find the cluster node/resource.
        value = {"model": "Cluster"}
        id_cluster = sim.topology.find_IDs(value)  # There is only ONE Cluster.
        value = {"model": "m-"}
        id_mobiles = sim.topology.find_IDs(value)

        # Given an application we get its modules implemented.
        app = sim.apps[app_name]
        services = app.services

        for module in services.keys():
            if "Coordinator" == module:
                if "Coordinator" in self.scaleServices.keys():
                    # Deploy as many modules as requested in the scale config.
                    for rep in range(0, self.scaleServices["Coordinator"]):
                        sim.deploy_module(
                            app_name, module, services[module], id_cluster
                        )

            elif "Calculator" == module:
                if "Calculator" in self.scaleServices.keys():
                    for rep in range(0, self.scaleServices["Calculator"]):
                        sim.deploy_module(
                            app_name, module, services[module], id_cluster
                        )

            elif "Client" == module:
                sim.deploy_module(app_name, module, services[module], id_mobiles)


class EdgePlacement(Placement):
    """
    Place application services across cluster, edge (proxy), and mobile nodes.

    It only runs once, in the initialization.

    """
    def initial_allocation(self, sim, app_name):
        # Find the cluster node/resource.
        value = {"model": "Cluster"}
        id_cluster = sim.topology.find_IDs(value)  # There is only ONE Cluster.
        value = {"model": "d-"}
        id_proxies = sim.topology.find_IDs(value)
        value = {"model": "m-"}
        id_mobiles = sim.topology.find_IDs(value)

        # Given an application we get its modules implemented.
        app = sim.apps[app_name]
        services = app.services

        for module in services.keys():
            if "Coordinator" == module:
                # Coordinator is deployed on the cluster.
                sim.deploy_module(app_name, module, services[module], id_cluster)
            elif "Calculator" == module:
                # Calculator is deployed on edge/proxy nodes.
                sim.deploy_module(app_name, module, services[module], id_proxies)
            elif "Client" == module:
                # Client is deployed on mobile nodes.
                sim.deploy_module(app_name, module, services[module], id_mobiles)


class NoPlacementOfModules(Placement):
    """
    Placement strategy that does not allocate any modules.

    Useful for scenarios where modules are manually deployed elsewhere,
    or placement is completely external to this mechanism.

    """
    def initial_allocation(self, sim, app_name):
        # There are no modules to be allocated in this strategy.
        return None
