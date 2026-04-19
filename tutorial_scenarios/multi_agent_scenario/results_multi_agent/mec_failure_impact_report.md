# MEC Failure Impact Report

## Inputs

- Topology: `/Users/isaac/Projects/YAFS/tutorial_scenarios/multi_agent_scenario/topology.json`
- Random trace: `/Users/isaac/Projects/YAFS/tutorial_scenarios/multi_agent_scenario/results_random/sim_trace.csv`
- Greedy trace: `/Users/isaac/Projects/YAFS/tutorial_scenarios/multi_agent_scenario/results_greedy/sim_trace.csv`
- Multi-Agent trace: `/Users/isaac/Projects/YAFS/tutorial_scenarios/multi_agent_scenario/results_multi_agent/sim_trace_sim-624d87ab.csv`

## Summary

| Metric | Random | Greedy | Multi-Agent |
| --- | --- | --- | --- |
| Deployed users | 200 | 200 | 200 |
| Observed user-app assignments | 122 | 200 | 200 |
| MEC workers total | 100 | 100 | 100 |
| Active MEC workers | 22 | 90 | 19 |
| Average affected users (all MEC workers) | 1.15 | 2.00 | 1.18 |
| Average affected users (active MEC workers) | 5.23 | 2.22 | 6.21 |
| Affected-user probability (all MEC workers) | 0.94% | 1.00% | 0.59% |
| Affected-user probability (active MEC workers) | 4.28% | 1.11% | 3.11% |

## Interpretation

- Random concentra las aplicaciones observadas en menos `workers MEC`, por lo que un nodo activo tiende a ser más crítico.
- Greedy reparte el impacto de fallo entre más nodos, reduciendo el número medio de usuarios afectados cuando cae un `worker MEC` activo.
- Multi-Agent reduce el riesgo medio condicionado a caída de un `worker MEC` activo frente a la referencia aleatoria.
- En `random`, el número de asignaciones observadas es inferior al número de usuarios desplegados; el informe se basa en las asignaciones con ejecución observada en traza.

## Most Impactful MEC Workers: Random

| Rank | MEC worker | Affected users | Affected probability |
| --- | --- | --- | --- |
| 1 | mec-b-0-worker-1 | 10 | 8.20% |
| 2 | mec-e-0-worker-3 | 9 | 7.38% |
| 3 | mec-d-1-worker-1 | 8 | 6.56% |
| 4 | mec-f-2-worker-2 | 8 | 6.56% |
| 5 | mec-h-1-worker-5 | 7 | 5.74% |
| 6 | mec-b-2-worker-4 | 6 | 4.92% |
| 7 | mec-c-0-worker-1 | 6 | 4.92% |
| 8 | mec-c-1-worker-2 | 6 | 4.92% |
| 9 | mec-d-3-worker-1 | 6 | 4.92% |
| 10 | mec-f-1-worker-2 | 6 | 4.92% |

## Most Impactful MEC Workers: Greedy

| Rank | MEC worker | Affected users | Affected probability |
| --- | --- | --- | --- |
| 1 | mec-a-0-worker-1 | 6 | 3.00% |
| 2 | mec-d-2-worker-1 | 6 | 3.00% |
| 3 | mec-d-3-worker-3 | 5 | 2.50% |
| 4 | mec-f-0-worker-1 | 5 | 2.50% |
| 5 | mec-f-2-worker-1 | 5 | 2.50% |
| 6 | mec-f-2-worker-3 | 5 | 2.50% |
| 7 | mec-d-1-worker-4 | 4 | 2.00% |
| 8 | mec-e-0-worker-2 | 4 | 2.00% |
| 9 | mec-e-0-worker-3 | 4 | 2.00% |
| 10 | mec-f-0-worker-3 | 4 | 2.00% |

## Most Impactful MEC Workers: Multi-Agent

| Rank | MEC worker | Affected users | Affected probability |
| --- | --- | --- | --- |
| 1 | mec-j-1-worker-4 | 11 | 5.50% |
| 2 | mec-j-2-worker-3 | 11 | 5.50% |
| 3 | mec-a-0-worker-3 | 9 | 4.50% |
| 4 | mec-d-2-worker-1 | 8 | 4.00% |
| 5 | mec-d-3-worker-1 | 8 | 4.00% |
| 6 | mec-f-1-worker-2 | 8 | 4.00% |
| 7 | mec-b-0-worker-1 | 7 | 3.50% |
| 8 | mec-d-1-worker-1 | 7 | 3.50% |
| 9 | mec-f-2-worker-2 | 7 | 3.50% |
| 10 | mec-b-2-worker-4 | 6 | 3.00% |

## Per-Application Breakdown

### Coordination Pipeline

| Metric | Random | Greedy | Multi-Agent |
| --- | --- | --- | --- |
| Deployed users | 70 | 76 | 79 |
| Observed user-app assignments | 39 | 76 | 79 |
| Active MEC workers | 10 | 54 | 10 |
| Average affected users (all MEC workers) | 0.47 | 0.76 | 0.74 |
| Average affected users (active MEC workers) | 4.70 | 1.41 | 7.40 |
| Affected-user probability (all MEC workers) | 1.21% | 1.00% | 0.94% |
| Affected-user probability (active MEC workers) | 12.05% | 1.85% | 9.37% |

Random top MEC workers

| Rank | MEC worker | Affected users | Affected probability |
| --- | --- | --- | --- |
| 1 | mec-d-1-worker-1 | 8 | 20.51% |
| 2 | mec-f-2-worker-2 | 8 | 20.51% |
| 3 | mec-d-3-worker-1 | 6 | 15.38% |
| 4 | mec-g-0-worker-3 | 5 | 12.82% |
| 5 | mec-h-1-worker-1 | 5 | 12.82% |

Greedy top MEC workers

| Rank | MEC worker | Affected users | Affected probability |
| --- | --- | --- | --- |
| 1 | mec-h-0-worker-1 | 4 | 5.26% |
| 2 | mec-b-0-worker-2 | 3 | 3.95% |
| 3 | mec-d-1-worker-4 | 3 | 3.95% |
| 4 | mec-e-0-worker-3 | 3 | 3.95% |
| 5 | mec-h-1-worker-1 | 3 | 3.95% |

Multi-Agent top MEC workers

| Rank | MEC worker | Affected users | Affected probability |
| --- | --- | --- | --- |
| 1 | mec-j-1-worker-4 | 11 | 13.92% |
| 2 | mec-j-2-worker-3 | 11 | 13.92% |
| 3 | mec-a-0-worker-3 | 9 | 11.39% |
| 4 | mec-d-2-worker-1 | 8 | 10.13% |
| 5 | mec-d-3-worker-1 | 8 | 10.13% |

### Perception Pipeline

| Metric | Random | Greedy | Multi-Agent |
| --- | --- | --- | --- |
| Deployed users | 57 | 62 | 66 |
| Observed user-app assignments | 36 | 62 | 66 |
| Active MEC workers | 11 | 44 | 7 |
| Average affected users (all MEC workers) | 0.52 | 0.62 | 0.40 |
| Average affected users (active MEC workers) | 4.73 | 1.41 | 5.71 |
| Affected-user probability (all MEC workers) | 1.44% | 1.00% | 0.61% |
| Affected-user probability (active MEC workers) | 13.13% | 2.27% | 8.66% |

Random top MEC workers

| Rank | MEC worker | Affected users | Affected probability |
| --- | --- | --- | --- |
| 1 | mec-b-0-worker-1 | 10 | 27.78% |
| 2 | mec-b-2-worker-4 | 6 | 16.67% |
| 3 | mec-c-0-worker-1 | 6 | 16.67% |
| 4 | mec-c-1-worker-2 | 6 | 16.67% |
| 5 | mec-f-1-worker-2 | 6 | 16.67% |

Greedy top MEC workers

| Rank | MEC worker | Affected users | Affected probability |
| --- | --- | --- | --- |
| 1 | mec-a-0-worker-1 | 3 | 4.84% |
| 2 | mec-d-3-worker-3 | 3 | 4.84% |
| 3 | mec-j-2-worker-3 | 3 | 4.84% |
| 4 | mec-a-1-worker-1 | 2 | 3.23% |
| 5 | mec-b-2-worker-2 | 2 | 3.23% |

Multi-Agent top MEC workers

| Rank | MEC worker | Affected users | Affected probability |
| --- | --- | --- | --- |
| 1 | mec-f-1-worker-2 | 8 | 12.12% |
| 2 | mec-b-0-worker-1 | 7 | 10.61% |
| 3 | mec-b-2-worker-4 | 6 | 9.09% |
| 4 | mec-f-1-worker-4 | 6 | 9.09% |
| 5 | mec-i-1-worker-3 | 6 | 9.09% |

### Telemetry Monitoring

| Metric | Random | Greedy | Multi-Agent |
| --- | --- | --- | --- |
| Deployed users | 73 | 62 | 55 |
| Observed user-app assignments | 47 | 62 | 55 |
| Active MEC workers | 2 | 46 | 2 |
| Average affected users (all MEC workers) | 0.16 | 0.62 | 0.04 |
| Average affected users (active MEC workers) | 8.00 | 1.35 | 2.00 |
| Affected-user probability (all MEC workers) | 0.34% | 1.00% | 0.07% |
| Affected-user probability (active MEC workers) | 17.02% | 2.17% | 3.64% |

Random top MEC workers

| Rank | MEC worker | Affected users | Affected probability |
| --- | --- | --- | --- |
| 1 | mec-e-0-worker-3 | 9 | 19.15% |
| 2 | mec-h-1-worker-5 | 7 | 14.89% |
| 3 | mec-a-0-worker-1 | 0 | 0.00% |
| 4 | mec-a-0-worker-2 | 0 | 0.00% |
| 5 | mec-a-0-worker-3 | 0 | 0.00% |

Greedy top MEC workers

| Rank | MEC worker | Affected users | Affected probability |
| --- | --- | --- | --- |
| 1 | mec-d-2-worker-1 | 3 | 4.84% |
| 2 | mec-e-0-worker-2 | 3 | 4.84% |
| 3 | mec-b-1-worker-4 | 2 | 3.23% |
| 4 | mec-b-2-worker-1 | 2 | 3.23% |
| 5 | mec-c-0-worker-3 | 2 | 3.23% |

Multi-Agent top MEC workers

| Rank | MEC worker | Affected users | Affected probability |
| --- | --- | --- | --- |
| 1 | mec-e-0-worker-3 | 2 | 3.64% |
| 2 | mec-h-1-worker-5 | 2 | 3.64% |
| 3 | mec-a-0-worker-1 | 0 | 0.00% |
| 4 | mec-a-0-worker-2 | 0 | 0.00% |
| 5 | mec-a-0-worker-3 | 0 | 0.00% |
