from collections import Counter

import networkx as nx

from yafs.selection import Selection


class DeviceSpeedAwareRouting(Selection):
    """
    Routing policy that selects the closest service instance (DES) in hops.

    Among multiple instances at the same minimum distance, a simple
    round‑robin mechanism is applied to balance the load.
    """

    def __init__(self):
        # Cache structures used by the selection interface.
        self.cache = {}
        self.counter = Counter(list())
        self.invalid_cache_value = True

        # key: (node_src, service_name)
        # value: (path, des_id)
        self.controlServices = {}

        super(DeviceSpeedAwareRouting, self).__init__()

    def compute_BEST_DES(self, node_src, alloc_DES, sim, DES_dst, message):
        """
        Compute the best DES instance to serve a request.

        The best instance is the one with the shortest path (in hops)
        from ``node_src``. If several instances share the same minimal
        path length, a round‑robin policy is used between them.
        """
        try:
            best_length = float("inf")
            min_path = []
            best_des = None
            candidates_same_node = []

            for des_id in DES_dst:
                node_dst = alloc_DES[des_id]
                path = list(
                    nx.shortest_path(sim.topology.G, source=node_src, target=node_dst)
                )
                path_len = len(path)

                if path_len < best_length:
                    best_length = path_len
                    min_path = path
                    best_des = des_id
                    candidates_same_node = []
                elif path_len == best_length:
                    # Another instance of the service is deployed at the same
                    # distance (often in the same node).
                    if len(candidates_same_node) == 0 and best_des is not None:
                        candidates_same_node.append(best_des)
                    candidates_same_node.append(des_id)

            # There are two or more options: apply round‑robin scheduling.
            if len(candidates_same_node) > 0:
                best_index = 0
                min_counter = float("inf")
                for idx, service in enumerate(candidates_same_node):
                    # If this service has never been used, pick it immediately.
                    if service not in self.counter:
                        return min_path, service
                    # Otherwise, keep the least used service.
                    if self.counter[service] < min_counter:
                        min_counter = self.counter[service]
                        best_index = idx
                return min_path, candidates_same_node[best_index]
            else:
                return min_path, best_des

        except (nx.NetworkXNoPath, nx.NodeNotFound):
            self.logger.warning(
                "There is no path between two nodes: %s - %s ", node_src, message.dst
            )
            # print("Simulation must end?)"
            return [], None

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
        Return the path and DES destination for a given message.
        """
        node_src = topology_src  # Entity that sends the message.
        service = message.dst  # Name of the service.

        # Software modules that can serve the message.
        DES_dst = alloc_module[app_name][message.dst]

        # The number of nodes controls the cache lifetime. If the topology
        # changes, the cache is cleared elsewhere.
        path, des = self.compute_BEST_DES(node_src, alloc_DES, sim, DES_dst, message)

        try:
            dc = int(des)
            self.counter[dc] += 1
            self.controlServices[(node_src, service)] = (path, des)
        except (TypeError, ValueError):
            # The node is not linked with other nodes or des is None.
            return [], None

        return [path], [des]

    def clear_routing_cache(self):
        """
        Clear any cached routing decisions.
        """
        self.invalid_cache_value = False
        self.cache = {}
        self.counter = Counter(list())
        self.controlServices = {}

    def get_path_from_failure(
        self, sim, message, link, alloc_DES, alloc_module, traffic, ctime, from_des
    ):
        """
        Recompute a path when a link fails.
        """
        idx = message.path.index(link[0])
        # print "IDX: ",idx
        if idx == len(message.path):
            # The node that serves the request – not a possible case here.
            return [], []
        else:
            # From this point to the failed entity the system must re-route.
            node_src = message.path[idx]
            # print "SRC: ",node_src

            node_dst = message.path[len(message.path) - 1]
            # print "DST: ",node_dst
            # print "INT: ",message.dst_int

            path, des = self.get_path(
                sim,
                message.app_name,
                message,
                node_src,
                alloc_DES,
                alloc_module,
                traffic,
                from_des,
            )
            if len(path[0]) > 0:
                # Concatenate the previous path with the new path.
                concPath = message.path[0 : message.path.index(path[0][0])] + path[0]
                newINT = node_src

                message.dst_int = newINT
                return [concPath], des
            else:
                return [], []
