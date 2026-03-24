"""
   @author: Isaac Lera
"""
import math
from pathlib import Path

from yafs.services.simulation_service import SimulationService


def print_application_metrics(label, metrics_report):
    print(f"  {label}:")
    if not metrics_report.items:
        print("    <no application metrics>")
        return

    for item in metrics_report.items:
        avg_response = "nan" if math.isnan(item.response_mean) else f"{item.response_mean:.5f}"
        print(
            "    - "
            f"{item.app}: "
            f"avg_response={avg_response}, "
            f"requests_total={int(item.requests_total)}, "
            f"requests_successful={int(item.requests_successful)}, "
            f"requests_unsuccessful={int(item.requests_unsuccessful)}, "
            f"placement_cost={item.placement_cost:.8f}, "
            f"total_cost={item.total_cost:.8f}"
        )


def print_topology_inventory(service, simulation_id):
    print("Topology inventory:")
    print(f"  nodes={service.count_nodes(simulation_id)}")
    print(f"  clusters={service.count_clusters(simulation_id)}")
    print(f"  cluster names={[item['cluster'] for item in service.list_clusters(simulation_id)]}")
    print(f"  mec-0 nodes={[item['node'] for item in service.list_nodes_in_cluster(simulation_id, 'mec-0')]}")


if __name__ == '__main__':

    timeHorizon = 10000
    scenario_path = Path(__file__).with_name("three-cluster")
    # Data for Actions
    add_cluster_path = scenario_path / "actions" / "add_new_cluster.json"
    add_nodes_path = scenario_path / "actions" / "add_new_nodes.json"

    service = SimulationService()

    # S0: simulacion raiz.
    s0 = service.create_simulation(
        scenario_path=scenario_path,
        results_path=scenario_path / "results",
        seed=2026,
        name="case-three-cluster-s0",
    )
    print(f"S0 created: id={s0.summary.id} now={s0.summary.now}")

    # S0 avanza su primera ventana temporal.
    service.schedule_for(s0.summary.id, duration=timeHorizon, step=2000.0)
    s0 = service.wait_until_ready(s0.summary.id)
    print(f"S0 ready after first window: id={s0.summary.id} now={s0.summary.now}")

    # S1 nace como fork de S0 en el tiempo actual de S0.
    s1 = service.fork(s0.summary.id)
    print(f"S1 forked from S0: id={s1.summary.id} now={s1.summary.now}")

    # S1 avanza su propia ventana temporal.
    service.schedule_for(s1.summary.id, duration=timeHorizon, step=2000.0)
    s1 = service.wait_until_ready(s1.summary.id)
    print(f"S1 ready after first window: id={s1.summary.id} now={s1.summary.now}")

    # S2 nace como fork de S1, independientemente de S0.
    s2 = service.fork(s1.summary.id)
    print(f"S2 forked from S1: id={s2.summary.id} now={s2.summary.now}")
    a = service.list_nodes(s2.summary.id) # acciópn implementada 
    print("Number of nodes in S2\n", len(a))
    
    print("Creating a new cluster\n", a)
    created_cluster = service.create_cluster(s2.summary.id, add_cluster_path)
    print(f"New cluster created in S2: {created_cluster}")

    b = service.list_nodes(s2.summary.id) # acciópn implementada 
    print("\t", b)
    print("\tNumber of nodes in S2\n", len(b))

    input("PAUSE FOR DEBUGGING")


    created_nodes = service.create_nodes(
        s2.summary.id,
        add_nodes_path,
    )
    print(f"New nodes created in S2: {created_nodes}")

    updated_node = service.update_node(
        s2.summary.id,
        "edc-cluster-new-1-worker-2",
        cpu="1",
        memory="256m",
        cost=10.0,
    )
    print(f"Node updated in S2: {updated_node}")

    removed_node = service.remove_node(s2.summary.id, "mec-0-worker-2") # Este nodo contiene el último VNF del servicio desplegado.
    print(f"Node removed in S2: {removed_node}")

    c = service.list_nodes(s2.summary.id) # acciópn implementada 
    
    print("Number of nodes in S2 after creating new nodes\n", len(c))

    input("PAUSE FOR DEBUGGING")


    # S2 avanza su propia ventana temporal.
    service.schedule_for(s2.summary.id, duration=timeHorizon, step=2000.0)
    print_topology_inventory(service, s2.summary.id)
    s2 = service.wait_until_ready(s2.summary.id)

    
    print(f"S2 ready after first window: id={s2.summary.id} now={s2.summary.now}")

    # S0 continua despues de haber creado y avanzado S1 y S2.
    service.schedule_for(s0.summary.id, duration=timeHorizon*3, step=2000.0)
    s0 = service.wait_until_ready(s0.summary.id)
    print(f"S0 ready after second window: id={s0.summary.id} now={s0.summary.now}")

    print("Timeline summary:")
    print(f"  S0 -> now={s0.summary.now}")
    print(f"  S1 -> now={s1.summary.now}")
    print(f"  S2 -> now={s2.summary.now}")

    print("Application metrics summary:")
    print_application_metrics("S0", service.get_application_metrics(s0.summary.id))
    print_application_metrics("S1", service.get_application_metrics(s1.summary.id))
    print_application_metrics("S2", service.get_application_metrics(s2.summary.id))

    print_application_metrics("S2", service.get_application_metrics(
        s2.summary.id,
        from_time=timeHorizon*2
    ))
