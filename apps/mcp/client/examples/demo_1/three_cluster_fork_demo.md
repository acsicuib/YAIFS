# Three Cluster Fork Demo

Sesion de ejemplo para el cliente/servidor MCP usando el lab
`case_three_cluster`.

## Objetivo

1. Crear una simulacion base.
2. Ejecutarla hasta `t=4000`.
3. Hacer `fork`.
4. En la rama hija borrar el cluster `mec-0`.
5. Continuar ambas simulaciones hasta `t=12000`.
6. Comparar su evolucion y metricas.

## Script reproducible

```bash
uv run python apps/mcp/client/examples/demo_1/three_cluster_fork_demo.py
```

El script guarda la salida detallada en:

- `apps/mcp/client/examples/demo_1/three_cluster_fork_demo_output.json`

## Flujo MCP que ejecuta

1. `get_default_scenario`
2. `create_default_simulation`
3. `list_simulation_clusters`
4. `list_simulation_users`
5. `run_simulation_for`
6. `wait_simulation_until_ready`
7. `fork_simulation`
8. `remove_simulation_cluster` sobre `mec-0` en la rama hija
9. `run_simulation_for` en ambas ramas
10. `wait_simulation_until_ready` en ambas ramas
11. `get_simulation_network_metrics`
12. `get_simulation_application_metrics`
13. `stop_simulation`

## Expectativa

La rama base mantiene los tres clusters originales.

La rama hija pierde `mec-0`, lo que implica:

- menos nodos disponibles
- servicios/VNFs afectados o no disponibles
- usuarios desconectados si dependian de ese cluster
- cambios en latencia, utilizacion y distancia recorrida por las peticiones

## Nota para entornos con `uv`

El script lanza el servidor MCP con:

```bash
uv run python apps/mcp/server/server.py
```

para reutilizar exactamente el entorno gestionado por `uv`.
