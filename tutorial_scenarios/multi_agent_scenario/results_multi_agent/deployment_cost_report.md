# Deployment Cost Report

## Cost Model

| Cluster role | Node role | Cost per deployment |
| --- | --- | --- |
| CDC | control-plane | 0.0120 |
| CDC | worker | 0.0100 |
| EDC | control-plane | 0.0600 |
| EDC | worker | 0.0500 |
| MEC | control-plane | 0.3000 |
| MEC | worker | 0.2500 |

Assumption: the intended high-cost edge tier is `MEC` (interpreting the request as `CDC` very cheap, `EDC` medium, `MEC` highly costly).

## Summary

| Metric | Random | Greedy | Multi-Agent |
| --- | --- | --- | --- |
| Deployments | 41 | 387 | 110 |
| Total placement cost | 7.0900 | 96.7500 | 7.7800 |

## Cost by Application

| Scenario | Application | Deployments | Unique apps | Total cost | Mean node cost |
| --- | --- | --- | --- | --- | --- |
| Random | Perception Pipeline | 21 | 1 | 3.8500 | 0.1833 |
| Random | Coordination Pipeline | 14 | 1 | 2.6600 | 0.1900 |
| Random | Telemetry Monitoring | 6 | 1 | 0.5800 | 0.0967 |
| Greedy | Perception Pipeline | 177 | 59 | 44.2500 | 0.2500 |
| Greedy | Coordination Pipeline | 138 | 69 | 34.5000 | 0.2500 |
| Greedy | Telemetry Monitoring | 72 | 72 | 18.0000 | 0.2500 |
| Multi-Agent | Perception Pipeline | 51 | 1 | 4.1500 | 0.0814 |
| Multi-Agent | Coordination Pipeline | 36 | 1 | 2.8800 | 0.0800 |
| Multi-Agent | Telemetry Monitoring | 23 | 1 | 0.7500 | 0.0326 |

## Cost by Cluster Type

| Scenario | Cluster type | Deployments | Total cost | Mean node cost |
| --- | --- | --- | --- | --- |
| Random | MEC | 27 | 6.7500 | 0.2500 |
| Random | EDC | 5 | 0.2500 | 0.0500 |
| Random | CDC | 9 | 0.0900 | 0.0100 |
| Greedy | MEC | 387 | 96.7500 | 0.2500 |
| Multi-Agent | MEC | 27 | 6.7500 | 0.2500 |
| Multi-Agent | CDC | 78 | 0.7800 | 0.0100 |
| Multi-Agent | EDC | 5 | 0.2500 | 0.0500 |

## Top Cost Nodes

| Scenario | Node | Cluster type | Deployments | Total cost |
| --- | --- | --- | --- | --- |
| Random | mec-b-0-worker-1 | MEC | 2 | 0.5000 |
| Random | mec-f-1-worker-4 | MEC | 2 | 0.5000 |
| Random | mec-h-0-worker-3 | MEC | 2 | 0.5000 |
| Random | mec-j-0-worker-2 | MEC | 2 | 0.5000 |
| Random | mec-a-0-worker-3 | MEC | 1 | 0.2500 |
| Random | mec-b-2-worker-2 | MEC | 1 | 0.2500 |
| Random | mec-b-2-worker-4 | MEC | 1 | 0.2500 |
| Random | mec-c-0-worker-1 | MEC | 1 | 0.2500 |
| Random | mec-c-1-worker-2 | MEC | 1 | 0.2500 |
| Random | mec-d-1-worker-1 | MEC | 1 | 0.2500 |
| Greedy | mec-i-2-worker-1 | MEC | 12 | 3.0000 |
| Greedy | mec-f-2-worker-2 | MEC | 11 | 2.7500 |
| Greedy | mec-a-0-worker-1 | MEC | 9 | 2.2500 |
| Greedy | mec-e-1-worker-2 | MEC | 9 | 2.2500 |
| Greedy | mec-f-0-worker-3 | MEC | 9 | 2.2500 |
| Greedy | mec-j-2-worker-5 | MEC | 9 | 2.2500 |
| Greedy | mec-c-1-worker-3 | MEC | 8 | 2.0000 |
| Greedy | mec-f-1-worker-5 | MEC | 8 | 2.0000 |
| Greedy | mec-g-0-worker-1 | MEC | 8 | 2.0000 |
| Greedy | mec-i-0-worker-3 | MEC | 8 | 2.0000 |
| Multi-Agent | mec-b-0-worker-1 | MEC | 2 | 0.5000 |
| Multi-Agent | mec-f-1-worker-4 | MEC | 2 | 0.5000 |
| Multi-Agent | mec-h-0-worker-3 | MEC | 2 | 0.5000 |
| Multi-Agent | mec-j-0-worker-2 | MEC | 2 | 0.5000 |
| Multi-Agent | mec-a-0-worker-3 | MEC | 1 | 0.2500 |
| Multi-Agent | mec-b-2-worker-2 | MEC | 1 | 0.2500 |
| Multi-Agent | mec-b-2-worker-4 | MEC | 1 | 0.2500 |
| Multi-Agent | mec-c-0-worker-1 | MEC | 1 | 0.2500 |
| Multi-Agent | mec-c-1-worker-2 | MEC | 1 | 0.2500 |
| Multi-Agent | mec-d-1-worker-1 | MEC | 1 | 0.2500 |
