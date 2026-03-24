"""
Selection (routing/orchestration) algorithms for YAFS.

A selection algorithm has one mandatory function:

* ``get_path``: provides the route that a message should follow within
  the topology to reach its destination module. It can also be seen as
  an orchestration algorithm.
"""
import logging

import networkx as nx


class Selection(object):
    """
    Base class for selection (routing/orchestration) algorithms.

    A selection algorithm provides the route among topology entities so
    that a message reaches its destination module.

    .. note:: A class interface
    """

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.transmit = 0.0
        self.lat_acc = 0.0
        self.propagation = 0.0

    def get_path(
        self,
        sim,
        app_name,
        message,
        topology_src,
        alloc_DES,
        alloc_module,
        traffic,
        from_des,
    ):
        """
        Compute the path and destination DES for a given message.

        Returns
        -------
        path : list
            A path (or list of paths) among nodes.
        ids : list
            Identifiers of the destination modules (DES instances).

        Notes
        -----
        Both lists being empty implies that the message will not be
        sent to the destination.

        .. attention:: override required
        """
        self.logger.debug("Selection")
        path = []
        ids = []

        return path, ids

    def get_path_from_failure(
        self,
        sim,
        message,
        link,
        alloc_DES,
        alloc_module,
        traffic,
        ctime,
        from_des,
    ):
        """
        Recompute a path when a link in a message path is broken or unavailable.

        Notes
        -----
        Both returned lists being empty implies that the message will
        not be sent to the destination.

        .. attention:: this function is optional
        """
        path = []
        ids = []

        return path, ids

class OneRandomPath(Selection):
    """
    Among all the possible options, return a random path.
    """

    def get_path(
        self,
        sim,
        app_name,
        message,
        topology_src,
        alloc_DES,
        alloc_module,
        traffic,
        from_des,
    ):
        paths = []
        dst_idDES = []
        src_node = topology_src
        DES = alloc_module[message.app_name][message.dst]
        for idDES in DES:
            dst_node = alloc_DES[idDES]
            path_list = list(
                nx.all_simple_paths(
                    sim.topology.G,
                    source=src_node,
                    target=dst_node,
                )
            )
            one = sim.rng.randint(0, len(path_list) - 1)
            paths.append(path_list[one])
            dst_idDES.append(idDES)
        return paths, dst_idDES
class First_ShortestPath(Selection):
    """Among all possible shortest paths, return the first."""

    def get_path(
        self,
        sim,
        app_name,
        message,
        topology_src,
        alloc_DES,
        alloc_module,
        traffic,
        from_des,
    ):
        paths = []
        dst_idDES = []

        node_src = topology_src  # TOPOLOGY SOURCE where the message is generated.
        DES_dst = alloc_module[app_name][message.dst]

        # Among all possible paths we choose the shortest.
        best_path = []
        best_des = []
        for des in DES_dst:
            dst_node = alloc_DES[des]
            path = list(
                nx.shortest_path(sim.topology.G, source=node_src, target=dst_node)
            )
            best_path = [path]
            best_des = [des]

        return best_path, best_des
