# MCP Client

CLI interactivo para hablar con un modelo que, a su vez, usa herramientas de
un servidor MCP para controlar la simulacion.

## Idea de arquitectura

La separacion recomendada es:

1. El servidor MCP expone herramientas y recursos del simulador.
2. El cliente MCP conecta con ese servidor.
3. El cliente llama a un modelo con function calling.
4. El modelo decide cuando usar herramientas.
5. El cliente ejecuta la herramienta MCP y devuelve la salida al modelo.

Eso mantiene desacopladas la logica de simulacion, la logica del protocolo MCP
y la orquestacion del modelo.

## Dependencias

Este cliente necesita:

- `mcp[cli]` para conectar con el servidor MCP por `stdio`
- `rich` para la presentacion visual del terminal
- `typer` como base para evolucionar la CLI a una experiencia mas declarativa
- una API key de OpenAI en `OPENAI_API_KEY`

Ejemplo de instalacion:

```bash
uv add "mcp[cli]" rich typer
```

Al arrancar, el cliente muestra un banner ASCII de `YAIFS`, una pequena
descripcion de capacidades y ejemplos rapidos de uso en terminal.

## Variables de entorno

- `OPENAI_API_KEY`: obligatoria
- `OPENAI_MODEL`: opcional, por defecto `gpt-5`
- `OPENAI_BASE_URL`: opcional, por defecto `https://api.openai.com/v1`

El cliente puede cargar estas variables desde un fichero `.env`.

Por defecto busca:

- `mcp-client/.env`

Puedes partir de la plantilla:

- [`env_copy`](/Users/isaac/Projects/YAFS/mcp-client/env_copy)

Flujo recomendado:

```bash
cp mcp-client/env_copy mcp-client/.env
```

Luego rellena al menos:

```dotenv
OPENAI_API_KEY=tu_clave
OPENAI_MODEL=gpt-5
OPENAI_BASE_URL=https://api.openai.com/v1
```

Si quieres usar otro fichero, puedes indicarlo con `--env-file`.

## Guardar configuraciones y resultados

Al arrancar el cliente puedes fijar un directorio base de artefactos para toda
la conversacion. El cliente se lo pasa al servidor MCP y este lo usa por
defecto para:

- configuraciones generadas
- trazas y resultados de simulacion

La opcion mas simple es `--artifacts-dir`:

```bash
uv run python mcp-client/cli.py \
  --env-file mcp-client/.env \
  --artifacts-dir mcp-client/artifacts/session-001 \
  --server-command uv \
  --server-arg run \
  --server-arg python \
  --server-arg mcp-server/server.py
```

Eso crea y usa automaticamente:

- `mcp-client/artifacts/session-001/configurations`
- `mcp-client/artifacts/session-001/results`

Si quieres separarlos manualmente, usa:

- `--configurations-dir`
- `--results-dir`

## Uso

El cliente necesita saber como arrancar el servidor MCP.

```bash
uv run python mcp-client/cli.py \
  --env-file mcp-client/.env \
  --artifacts-dir mcp-client/artifacts/default-session \
  --server-command uv \
  --server-arg run \
  --server-arg python \
  --server-arg path/to/your_mcp_server.py
```

Si prefieres conectarlo a otro proyecto gestionado con `uv`:

```bash
uv run python mcp-client/cli.py \
  --env-file mcp-client/.env \
  --artifacts-dir mcp-client/artifacts/default-session \
  --lab-path lab_scenarios/case_three_cluster/three-cluster \
  --server-command uv \
  --server-arg run \
  --server-arg python \
  --server-arg mcp-server/server.py
```

La opcion `--lab-path` no crea ninguna simulacion al arrancar. Solo fija el
`scenario_path` base del servidor MCP para esa sesion y se lo da tambien como
contexto al modelo.

Si no la indicas, el cliente no precarga nada y no debe existir ninguna
simulacion por defecto.

Si prefieres, puedes seguir pasando el path directamente al servidor con:

```bash
uv run python mcp-client/cli.py \
  --env-file mcp-client/.env \
  --server-command uv \
  --server-arg run \
  --server-arg python \
  --server-arg mcp-server/server.py \
  --server-arg --scenario-path \
  --server-arg lab_scenarios/case_three_cluster/three-cluster
```

## Comandos interactivos

- `/tools`: lista las herramientas MCP detectadas
- `/lab path/to/scenario`: fija durante la sesion la ruta del laboratorio o escenario
- `/lab`: muestra la ruta de laboratorio actualmente fijada
- `/paste`: entra en modo multilinea y termina con una linea que contenga solo `EOF`
- `/file path/to/file.json`: envia el contenido de un fichero como prompt
- `/help`: muestra ayuda
- `/exit`: sale del cliente

Si arrancaste el cliente sin `--lab-path`, puedes fijarlo mas tarde asi:

```text
you> /lab /Users/isaac/Projects/YAFS/lab_scenarios/case_three_cluster/three-cluster
```

Eso no crea ninguna simulacion automaticamente, pero deja esa ruta como
contexto activo para que el modelo use `create_simulation` con ese escenario.

## Ver tools invocadas

Hay dos niveles de visibilidad:

1. Ver las tools disponibles para el modelo:

```text
/tools
```

2. Ver las tools realmente invocadas durante la sesion:

```bash
uv run python mcp-client/cli.py \
  --env-file mcp-client/.env \
  --artifacts-dir mcp-client/artifacts/default-session \
  --lab-path lab_scenarios/case_three_cluster/three-cluster \
  --server-command uv \
  --server-arg run \
  --server-arg python \
  --server-arg mcp-server/server.py
```

Ademas, el cliente guarda por defecto un historial JSONL en:

- [`tool_calls.jsonl`](/Users/isaac/Projects/YAFS/mcp-client/tool_calls.jsonl)

Puedes cambiar la ruta con `--tool-log-file`.

## Ejemplos de entrada

### Pegar un JSON multilinea

Si quieres pegar un JSON directamente en la consola, usa `/paste` y finaliza con
una linea que contenga solo `EOF`:

```text
you> /paste
paste> Enter multiline input. Finish with a line containing only EOF.
Quiero crear una aplicacion en la simulacion usando este JSON:
{
  "id": 2,
  "name": "Video Analytics",
  "latency_requirement": 25
}
EOF
```

### Enviar el contenido de un fichero JSON

Si el contenido ya existe en un fichero, puedes enviarlo completo con `/file`:

```text
you> /file lab_scenarios/case_three_cluster/three-cluster/actions/create_application_example.json
```

Tambien puedes combinarlo con una instruccion mas explicita:

```text
you> /paste
paste> Enter multiline input. Finish with a line containing only EOF.
Crea una aplicacion en la simulacion usando el contenido de este fichero:
lab_scenarios/case_three_cluster/three-cluster/actions/create_application_example.json

Si necesitas parametros, usa el JSON completo como referencia:
{
  "id": 2,
  "name": "Video Analytics",
  "latency_requirement": 25,
  "vnf_chain": ["PRE", "INF"]
}
EOF
```

## Notas

- El cliente usa el endpoint `Responses` de OpenAI con function calling.
- Las herramientas disponibles se obtienen dinamicamente desde `session.list_tools()`.
- La salida de cada herramienta MCP se devuelve al modelo como
  `function_call_output`.
- Si el servidor usa transporte `stdio`, no debe escribir logs por `stdout`.
- El orden de precedencia es: flags CLI > variables del entorno del shell > `.env`.
- El cliente puede registrar cada tool call en consola y en JSONL.
