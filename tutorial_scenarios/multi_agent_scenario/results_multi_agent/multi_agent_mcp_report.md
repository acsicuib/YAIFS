# Multi-Agent MCP Scenario Report

## Configuration

- seed: `2026`
- replica_count: `20`
- activation_interval: `200.0`
- activation_count: `20`
- post_activation_tail: `1000.0`
- users_per_activation: `10`
- user_lambda: `100.0`
- window_duration: `200.0`
- step: `50.0`
- mec_worker_ipt: `10.0`
- link_utilization_threshold: `0.5`
- node_utilization_threshold: `0.08`
- overload_streak_windows: `1`
- placement_cost_budget: `8.7`
- action_budget_per_window: `4`
- prefer_overload_when_present: `True`
- egress_cost_per_gb: `0.02`
- hotspot_events: `[{'name': 'HotspotUsers-Perception-MEC-I', 'time': 1000.0, 'app': 'Perception Pipeline', 'node': 'mec-i-1-worker-3', 'count': 60, 'user_lambda': 15.0, 'move_time': 1800.0, 'move_to': 'mec-i-1-worker-4', 'remove_time': 2600.0, 'remove_fraction': 0.4, 'interval': 200.0}]`
- simulation_duration: `5000.0`
- app_latency_requirements: `{'Perception Pipeline': 120.0, 'Coordination Pipeline': 75.0, 'Telemetry Monitoring': 50.0}`
- updated_mec_nodes: `100`
- registered_hotspot_events: `1`
- transport_mode: `FastMCP server available`

## Window Summary

| Window | Start | End | Incidents | Actions | Top app by p95 |
| --- | --- | --- | --- | --- | --- |
| 0 | 0 | 200 | 0 | 0 | Coordination Pipeline |
| 1 | 200 | 400 | 0 | 0 | Perception Pipeline |
| 2 | 400 | 600 | 4 | 4 | Perception Pipeline |
| 3 | 600 | 800 | 8 | 2 | Perception Pipeline |
| 4 | 800 | 1000 | 23 | 4 | Perception Pipeline |
| 5 | 1000 | 1200 | 48 | 4 | Perception Pipeline |
| 6 | 1200 | 1400 | 54 | 4 | Perception Pipeline |
| 7 | 1400 | 1600 | 56 | 4 | Perception Pipeline |
| 8 | 1600 | 1800 | 65 | 4 | Perception Pipeline |
| 9 | 1800 | 2000 | 78 | 4 | Perception Pipeline |
| 10 | 2000 | 2200 | 83 | 4 | Perception Pipeline |
| 11 | 2200 | 2400 | 89 | 4 | Perception Pipeline |
| 12 | 2400 | 2600 | 96 | 4 | Perception Pipeline |
| 13 | 2600 | 2800 | 101 | 4 | Perception Pipeline |
| 14 | 2800 | 3000 | 109 | 4 | Perception Pipeline |
| 15 | 3000 | 3200 | 113 | 4 | Perception Pipeline |
| 16 | 3200 | 3400 | 119 | 4 | Perception Pipeline |
| 17 | 3400 | 3600 | 120 | 4 | Perception Pipeline |
| 18 | 3600 | 3800 | 124 | 4 | Perception Pipeline |
| 19 | 3800 | 4000 | 125 | 4 | Perception Pipeline |
| 20 | 4000 | 4200 | 130 | 4 | Perception Pipeline |
| 21 | 4200 | 4400 | 135 | 4 | Perception Pipeline |
| 22 | 4400 | 4600 | 133 | 4 | Perception Pipeline |
| 23 | 4600 | 4800 | 131 | 4 | Perception Pipeline |
| 24 | 4800 | 5000 | 135 | 4 | Perception Pipeline |

## Placement Actions

| Window | Type | App | Module | From | To |
| --- | --- | --- | --- | --- | --- |
| 2 | replicate | Perception Pipeline | 0_ING | - | edc-a-worker-1 |
| 2 | replicate | Perception Pipeline | 0_FUS | - | edc-a-worker-1 |
| 2 | replicate | Perception Pipeline | 0_PLN | - | edc-a-worker-1 |
| 2 | replicate | Telemetry Monitoring | 0_MON | - | edc-h-worker-1 |
| 3 | consolidate | Telemetry Monitoring | 0_MON | mec-e-0-worker-3 | edc-a-worker-2 |
| 3 | replicate | Telemetry Monitoring | 0_MON | - | cdc-b-0-worker-1 |
| 4 | replicate | Perception Pipeline | 0_ING | - | edc-a-worker-3 |
| 4 | replicate | Perception Pipeline | 0_FUS | - | edc-a-worker-3 |
| 4 | replicate | Perception Pipeline | 0_PLN | - | edc-a-worker-3 |
| 4 | replicate | Telemetry Monitoring | 0_MON | - | edc-g-worker-1 |
| 5 | consolidate | Telemetry Monitoring | 0_MON | mec-h-1-worker-5 | edc-g-worker-2 |
| 5 | replicate | Perception Pipeline | 0_ING | - | edc-i-worker-1 |
| 5 | replicate | Perception Pipeline | 0_FUS | - | edc-i-worker-1 |
| 5 | replicate | Perception Pipeline | 0_PLN | - | edc-i-worker-1 |
| 6 | move | Perception Pipeline | 0_FUS | edc-i-worker-1 | edc-i-worker-2 |
| 6 | move | Coordination Pipeline | 0_NEG | mec-a-0-worker-3 | cdc-a-1-worker-1 |
| 6 | move | Perception Pipeline | 0_ING | mec-b-0-worker-1 | cdc-a-1-worker-1 |
| 6 | move | Coordination Pipeline | 0_DIS | mec-d-3-worker-1 | cdc-a-1-worker-1 |
| 7 | move | Perception Pipeline | 0_ING | cdc-a-1-worker-1 | cdc-a-1-worker-2 |
| 7 | move | Perception Pipeline | 0_ING | edc-i-worker-1 | edc-g-worker-3 |
| 7 | move | Perception Pipeline | 0_FUS | edc-i-worker-2 | edc-g-worker-3 |
| 7 | move_failed | Perception Pipeline | 0_ING | mec-c-0-worker-1 | cdc-a-1-worker-2 |
| 8 | move | Perception Pipeline | 0_FUS | edc-g-worker-3 | edc-i-worker-2 |
| 8 | move | Perception Pipeline | 0_ING | mec-c-0-worker-1 | cdc-a-1-worker-3 |
| 8 | move_failed | Perception Pipeline | 0_ING | mec-f-1-worker-2 | cdc-a-1-worker-3 |
| 8 | move_failed | Perception Pipeline | 0_ING | mec-f-1-worker-4 | cdc-a-1-worker-3 |
| 9 | move | Perception Pipeline | 0_FUS | edc-i-worker-2 | edc-g-worker-1 |
| 9 | move | Perception Pipeline | 0_ING | mec-f-1-worker-4 | cdc-a-1-worker-4 |
| 9 | move | Coordination Pipeline | 0_DIS | mec-f-2-worker-2 | cdc-a-1-worker-4 |
| 9 | move | Coordination Pipeline | 0_DIS | mec-h-1-worker-1 | cdc-b-0-worker-10 |
| 10 | move | Perception Pipeline | 0_ING | cdc-a-1-worker-4 | cdc-a-1-worker-5 |
| 10 | move | Perception Pipeline | 0_FUS | edc-g-worker-1 | edc-i-worker-2 |
| 10 | move_failed | Perception Pipeline | 0_ING | mec-f-1-worker-2 | cdc-a-1-worker-5 |
| 10 | move | Perception Pipeline | 0_ING | mec-i-1-worker-3 | edc-i-worker-2 |
| 11 | move | Perception Pipeline | 0_PLN | edc-i-worker-1 | cdc-b-0-worker-12 |
| 11 | move | Perception Pipeline | 0_FUS | edc-i-worker-2 | cdc-b-0-worker-12 |
| 11 | move | Perception Pipeline | 0_ING | mec-f-1-worker-2 | cdc-a-1-worker-6 |
| 11 | move_failed | Perception Pipeline | 0_FUS | mec-h-0-worker-3 | cdc-b-0-worker-12 |
| 12 | move | Coordination Pipeline | 0_DIS | cdc-a-1-worker-1 | cdc-a-1-worker-7 |
| 12 | move | Perception Pipeline | 0_FUS | cdc-b-0-worker-12 | edc-i-worker-1 |
| 12 | move | Perception Pipeline | 0_ING | edc-i-worker-2 | edc-i-worker-1 |
| 12 | move_failed | Perception Pipeline | 0_FUS | mec-h-0-worker-3 | edc-i-worker-1 |
| 13 | move | Perception Pipeline | 0_FUS | edc-i-worker-1 | cdc-b-0-worker-13 |
| 13 | move_failed | Perception Pipeline | 0_FUS | mec-h-0-worker-3 | cdc-b-0-worker-13 |
| 13 | move | Perception Pipeline | 0_PLN | mec-i-0-worker-4 | cdc-b-0-worker-13 |
| 13 | replicate | Perception Pipeline | 0_ING | - | cdc-b-0-worker-15 |
| 14 | move | Perception Pipeline | 0_FUS | cdc-b-0-worker-15 | cdc-b-0-worker-12 |
| 14 | move | Perception Pipeline | 0_FUS | edc-a-worker-1 | cdc-a-1-worker-8 |
| 14 | move_failed | Perception Pipeline | 0_FUS | edc-a-worker-3 | cdc-a-1-worker-8 |
| 14 | move_failed | Perception Pipeline | 0_FUS | mec-h-0-worker-3 | cdc-b-0-worker-12 |
| 15 | move | Perception Pipeline | 0_FUS | cdc-a-1-worker-8 | cdc-a-1-worker-9 |
| 15 | move | Perception Pipeline | 0_FUS | cdc-b-0-worker-12 | cdc-b-0-worker-18 |
| 15 | move_failed | Perception Pipeline | 0_FUS | edc-a-worker-3 | cdc-a-1-worker-9 |
| 15 | move_failed | Perception Pipeline | 0_FUS | mec-h-0-worker-3 | cdc-b-0-worker-18 |
| 16 | move | Coordination Pipeline | 0_NEG | cdc-a-1-worker-1 | cdc-a-1-worker-8 |
| 16 | move | Perception Pipeline | 0_FUS | cdc-a-1-worker-9 | cdc-a-1-worker-8 |
| 16 | move_failed | Perception Pipeline | 0_FUS | edc-a-worker-3 | cdc-a-1-worker-8 |
| 16 | move | Perception Pipeline | 0_PLN | mec-b-0-worker-1 | cdc-a-1-worker-8 |
| 17 | move | Perception Pipeline | 0_FUS | cdc-a-1-worker-8 | cdc-a-1-worker-1 |
| 17 | move | Perception Pipeline | 0_FUS | cdc-b-0-worker-13 | cdc-b-0-worker-19 |
| 17 | move_failed | Perception Pipeline | 0_FUS | edc-a-worker-3 | cdc-a-1-worker-1 |
| 17 | move_failed | Perception Pipeline | 0_FUS | mec-h-0-worker-3 | cdc-b-0-worker-19 |
| 18 | move | Perception Pipeline | 0_FUS | cdc-a-1-worker-1 | cdc-a-1-worker-9 |
| 18 | move | Perception Pipeline | 0_PLN | cdc-a-1-worker-8 | cdc-a-1-worker-9 |
| 18 | move | Perception Pipeline | 0_FUS | cdc-b-0-worker-19 | cdc-b-0-worker-13 |
| 18 | move_failed | Perception Pipeline | 0_FUS | edc-a-worker-3 | cdc-a-1-worker-9 |
| 19 | move | Coordination Pipeline | 0_NEG | cdc-a-1-worker-8 | cdc-a-1-worker-1 |
| 19 | move | Perception Pipeline | 0_FUS | cdc-a-1-worker-9 | cdc-a-1-worker-1 |
| 19 | move | Perception Pipeline | 0_FUS | cdc-b-0-worker-13 | cdc-b-0-worker-12 |
| 19 | move_failed | Perception Pipeline | 0_FUS | edc-a-worker-3 | cdc-a-1-worker-1 |
| 20 | move | Perception Pipeline | 0_FUS | cdc-a-1-worker-1 | cdc-a-1-worker-8 |
| 20 | move | Perception Pipeline | 0_PLN | cdc-a-1-worker-9 | cdc-a-1-worker-8 |
| 20 | move | Perception Pipeline | 0_FUS | cdc-b-0-worker-12 | cdc-b-0-worker-13 |
| 20 | move_failed | Perception Pipeline | 0_FUS | edc-a-worker-3 | cdc-a-1-worker-8 |
| 21 | move | Coordination Pipeline | 0_NEG | cdc-a-1-worker-1 | cdc-a-1-worker-9 |
| 21 | move | Perception Pipeline | 0_FUS | cdc-a-1-worker-8 | cdc-a-1-worker-9 |
| 21 | move | Perception Pipeline | 0_FUS | cdc-b-0-worker-13 | cdc-b-0-worker-19 |
| 21 | move_failed | Perception Pipeline | 0_FUS | edc-a-worker-3 | cdc-a-1-worker-9 |
| 22 | move | Perception Pipeline | 0_PLN | cdc-a-1-worker-8 | cdc-a-1-worker-1 |
| 22 | move | Perception Pipeline | 0_FUS | cdc-a-1-worker-9 | cdc-a-1-worker-1 |
| 22 | move | Perception Pipeline | 0_FUS | cdc-b-0-worker-19 | cdc-b-0-worker-13 |
| 22 | move_failed | Perception Pipeline | 0_FUS | edc-a-worker-3 | cdc-a-1-worker-1 |
| 23 | move | Perception Pipeline | 0_FUS | cdc-a-1-worker-1 | cdc-a-1-worker-8 |
| 23 | move | Coordination Pipeline | 0_NEG | cdc-a-1-worker-9 | cdc-a-1-worker-8 |
| 23 | move | Perception Pipeline | 0_FUS | cdc-b-0-worker-13 | cdc-b-0-worker-19 |
| 23 | move_failed | Perception Pipeline | 0_FUS | edc-a-worker-3 | cdc-a-1-worker-8 |
| 24 | move | Perception Pipeline | 0_PLN | cdc-a-1-worker-1 | cdc-a-1-worker-9 |
| 24 | move | Perception Pipeline | 0_FUS | cdc-a-1-worker-8 | cdc-a-1-worker-9 |
| 24 | move | Perception Pipeline | 0_FUS | cdc-b-0-worker-19 | cdc-b-0-worker-13 |
| 24 | move_failed | Perception Pipeline | 0_FUS | edc-a-worker-3 | cdc-a-1-worker-9 |

## Final Metrics

| App | Requests total | Successful | Unsuccessful | Response p95 | Placement cost | Egress cost | Total cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Coordination Pipeline | 1796 | 1779 | 17 | 130.55 | 2.0300 | 0.0000 | 2.0300 |
| Perception Pipeline | 14108 | 2096 | 12012 | 1380.87 | 3.0500 | 0.0000 | 3.0500 |
| Telemetry Monitoring | 1816 | 1784 | 32 | 74.20 | 0.3400 | 0.0000 | 0.3400 |
