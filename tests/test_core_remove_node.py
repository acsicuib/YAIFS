"""Regression test: Sim.remove_node stops every process on the removed node."""

import networkx as nx

from yafs.application import create_applications_from_json
from yafs.core import Sim
from yafs.path_routing import DeviceSpeedAwareRouting
from yafs.placement import JSONPlacement
from yafs.topology import Topology


def _single_module_app(name):
    return {
        "id": name, "name": name, "HwReqs": 1, "MaxReqs": 200, "MaxLatency": 50,
        "transmission": [{"message_in": f"M.{name}", "module": f"{name}_01"}],
        "module": [{"id": 1, "name": f"{name}_01", "type": "MODULE", "RAM": 1}],
        "message": [{"id": 0, "name": f"M.{name}", "s": "None", "d": f"{name}_01",
                     "bytes": 20, "instructions": 30}],
    }


def test_remove_node_stops_every_process_on_the_node(tmp_path):
    t = Topology()
    t.G = nx.path_graph(5)
    nx.set_edge_attributes(t.G, 1, "PR")
    nx.set_edge_attributes(t.G, 1, "BW")
    nx.set_node_attributes(t.G, 100, "IPT")
    apps = create_applications_from_json([_single_module_app(0), _single_module_app(1)])
    placement = JSONPlacement(name="Placement", json={"initialAllocation": [
        {"app": 0, "module_name": "0_01", "id_resource": 2},
        {"app": 1, "module_name": "1_01", "id_resource": 2},
    ]})
    sim = Sim(t, default_results_path=str(tmp_path / "trace"))
    for app in apps.values():
        sim.deploy_app(app, placement, DeviceSpeedAwareRouting())
    sim.run(1)
    on_node = [des for des, node in sim.alloc_DES.items() if node == 2]
    assert len(on_node) == 2

    sim.remove_node(2)

    assert 2 not in sim.alloc_DES.values()
    assert sim.alloc_module[0]["0_01"] == [] and sim.alloc_module[1]["1_01"] == []
    assert not any(sim.des_process_running[des] for des in on_node)
