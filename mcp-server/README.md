# MCP Server

Servidor MCP para exponer el simulador YAFS usando como escenario base
`lab_scenarios/case_three_cluster/three-cluster`.

## Funcion

Este servidor:

- crea una instancia de `SimulationService`
- expone sus operaciones como herramientas MCP
- usa el escenario del lab como configuracion por defecto
- se comunica por `stdio`, pensado para ser lanzado por un cliente MCP

## Uso

Ejecutar con el escenario por defecto:

```bash
uv run python mcp-server/server.py
```

Ejecutar con otro escenario:

```bash
uv run python mcp-server/server.py --scenario-path /ruta/al/escenario
```

Configurar directorios por defecto para configuraciones generadas y resultados:

```bash
uv run python mcp-server/server.py \
  --configurations-dir /ruta/configs \
  --results-dir /ruta/results
```

Tambien puede recibirlos por variables de entorno:

- `YAFS_MCP_CONFIGURATIONS_DIR`
- `YAFS_MCP_RESULTS_DIR`

## Herramientas relevantes

Ademas de las herramientas genericas del transporte YAFS, este servidor añade:

- `get_default_scenario`
- `create_default_simulation`
- `create_default_simulation_configuration`
- `create_default_simulation_from_configuration`

Las dos ultimas permiten:

- generar una configuracion autocontenida de simulacion a partir del escenario
  base
- crear una simulacion real desde esa configuracion

La configuracion puede construirse:

- indicando `cluster_count` y `nodes_per_cluster`
- indicando `topology_definition_path` con un JSON de topologia

El resultado se guarda en `generated-configurations/<nombre>/` dentro del
escenario base.

## Conexion desde el cliente

Ejemplo con el CLI de `mcp-client`:

```bash
uv run python mcp-client/cli.py \
  --server-command uv \
  --server-arg run \
  --server-arg python \
  --server-arg mcp-server/server.py
```

## Ejemplo de flujo

1. Crear una configuracion con 4 clusters y 3 nodos por cluster

```text
create_default_simulation_configuration(
  configuration_name="four-clusters",
  cluster_count=4,
  nodes_per_cluster=3
)
```

2. Crear una simulacion usando la configuracion generada

```text
create_default_simulation_from_configuration(
  configuration_path=".../generated-configurations/four-clusters",
  seed=2026,
  name="four-clusters-run"
)
```
