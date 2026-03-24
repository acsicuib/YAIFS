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


print(response)
print(links)
print(distance)