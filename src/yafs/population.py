"""
Population (workload) algorithms for YAFS.

Each population algorithm has two main responsibilities:

* ``initial_allocation``: invoked at the start of the simulation.
* ``run``: invoked during the simulation according to a temporal
  activation distribution.
"""
import logging


class Population(object):
    """
    Base class for population (workload) algorithms.

    A population algorithm controls how the message generation of sensor
    modules is associated with nodes in the topology. This association
    is done through generation controllers that are bound to messages
    and then assigned to one or more nodes, both at initialization and
    optionally during the execution of the simulation.

    .. note:: A class interface

    Args:
        name (str): Associated name.

        activation_dist (Distribution): Distribution that activates the
            :meth:`run` method during execution.

    Kwargs:
        param (dict): Parameters for ``activation_dist``.

    """
    def __init__(self, name, activation_dist=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.name = name
        self.activation_dist = activation_dist

        self.src_control = []
        self.sink_control = []

    def set_sink_control(self, values):
        """
        Register the location of sink modules.

        Parameters
        ----------
        values :
            Typically a dictionary describing the sink configuration
            (e.g. model, number of instances, module name).
        """
        self.sink_control.append(values)

    def get_next_activation(self):
        """
        Return the next simulation time at which this population should run.
        """
        return self.activation_dist.next()

    def set_src_control(self, values):
        """
        Store the controllers of each message generator (sources).

        Args:
            values (dict): Configuration for a source controller.
        """
        self.src_control.append(values)


    def initial_allocation(self, sim, app_name):
        """
        Given an ecosystem and an application, start the allocation of
        pure sources in the topology.

        .. attention:: override required
        """
        self.run(sim)

    # override
    def run(self, sim):
        """
        Change the assignment of modules that generate messages.

        Args:
            sim (:mod:`yafs.core.Sim`): Simulation object.
        """
        self.logger.debug("Activating - RUN - Population")
        # User definition of the Population evolution should be provided
        # in subclasses.
class Statical(Population):
    """
    Static population algorithm.

    This implementation statically assigns the generation of sources to
    specific nodes in the topology. It is only invoked during the
    initialization phase.

    Extends: :mod: Population
    """

    def initial_allocation(self, sim, app_name):
        # Assignment of SINK and SOURCE pure modules.
        for id_entity in sim.topology.nodeAttributes:
            entity = sim.topology.nodeAttributes[id_entity]
            for ctrl in self.sink_control:
                # A node can have several sink modules.
                if entity["model"] == ctrl["model"]:
                    # In this node there is a sink.
                    module = ctrl["module"]
                    for number in range(ctrl["number"]):
                        sim.deploy_sink(app_name, node=id_entity, module=module)
            # end for sink control

            for ctrl in self.src_control:
                # A node can have several source modules
                if entity["model"] == ctrl["model"]:
                    msg = ctrl["message"]
                    dst = ctrl["distribution"]
                    for number in range(ctrl["number"]):
                        idsrc = sim.deploy_source(
                            app_name, id_node=id_entity, msg=msg, distribution=dst
                        )
                        # The idsrc can be used to control the deactivation of
                        # the process in a dynamic behaviour.

            # end for src control

        # end assignments
