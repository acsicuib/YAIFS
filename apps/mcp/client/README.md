# MCP Client

Interactive CLI to talk to a model that, in turn, uses tools from
an MCP server to control the simulation.

This client is part of the YAIFS project branding. The simulator package and
Python imports remain `yafs` for compatibility.

## Architecture Idea

The recommended separation is:

1. The MCP server exposes simulator tools and resources.
2. The MCP client connects to that server.
3. The client calls a model with function calling.
4. The model decides when to use tools.
5. The client executes the MCP tool and returns the output to the model.

This keeps simulation logic, MCP protocol logic,
and model orchestration decoupled.

## Dependencies

This client needs:

- `mcp[cli]` to connect to the MCP server over `stdio`
- `rich` for terminal visual presentation
- `typer` as a base to evolve the CLI into a more declarative experience
- an OpenAI API key in `OPENAI_API_KEY`

Installation example:

```bash
uv add "mcp[cli]" rich typer
```

At startup, the client shows a `YAIFS` ASCII banner, a short
capabilities description, and quick usage examples in the terminal.

## Environment Variables

- `OPENAI_API_KEY`: required
- `OPENAI_MODEL`: optional, defaults to `gpt-5`
- `OPENAI_BASE_URL`: optional, defaults to `https://api.openai.com/v1`

The client can load these variables from a `.env` file.

By default it looks for:

- `apps/mcp/client/.env`

You can start from the template:

- [`env_copy`](/Users/isaac/Projects/YAFS/apps/mcp/client/env_copy)

Recommended flow:

```bash
cp apps/mcp/client/env_copy apps/mcp/client/.env
```

Then fill in at least:

```dotenv
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-5
OPENAI_BASE_URL=https://api.openai.com/v1
```

If you want to use another file, pass it with `--env-file`. The client does
not override environment variables that are already present in the shell. If
those are wrong, clear them and run again:

```bash
unset OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL
```

## Session Artifacts

Each client execution now creates or uses a session-specific artifacts
directory. If you do not pass `--artifacts-dir`, the client automatically
creates:

- `apps/mcp/client/artifacts/session-XXX-YYYYMMDD-HHMMSS/`

Inside that session folder, the client stores:

- `configurations/`: generated simulation configurations
- `results/`: simulation traces, CSV files and other outputs
- `logs/tool_calls.jsonl`: MCP tool invocations and their results
- `logs/model_responses.jsonl`: raw model responses from the OpenAI Responses API
- `logs/transcript.jsonl`: user/model conversation transcript
- `session.json`: metadata about the session, model, server command and paths

This session root is also passed to the MCP server so that generated
configurations and simulation results stay grouped with the rest of the logs.

If you want to force a specific session directory, pass `--artifacts-dir`:

```bash
uv run python apps/mcp/client/cli.py \
  --env-file apps/mcp/client/.env \
  --artifacts-dir apps/mcp/client/artifacts/session-010-20260327-101500 \
  --server-command uv \
  --server-arg run \
  --server-arg python \
  --server-arg apps/mcp/server/server.py
```

That directory will then contain:

- `apps/mcp/client/artifacts/session-010-20260327-101500/configurations`
- `apps/mcp/client/artifacts/session-010-20260327-101500/results`
- `apps/mcp/client/artifacts/session-010-20260327-101500/logs/`
- `apps/mcp/client/artifacts/session-010-20260327-101500/session.json`

If you want to override only the subdirectories used by the server, use:

- `--configurations-dir`
- `--results-dir`

If you want to override the tool log path, use `--tool-log-file`.
If that path is relative, it is resolved inside the session artifacts
directory.

## Usage

The client needs to know how to start the MCP server.

```bash
uv run python apps/mcp/client/cli.py \
  --env-file apps/mcp/client/.env \
  --server-command uv \
  --server-arg run \
  --server-arg python \
  --server-arg apps/mcp/server/server.py
```

If you prefer connecting it to another project managed with `uv`:

```bash
uv run python apps/mcp/client/cli.py \
  --env-file apps/mcp/client/.env \
  --lab-path tutorial_scenarios/using_service_layer_02/three-cluster  \
  --server-command uv \
  --server-arg run \
  --server-arg python \
  --server-arg apps/mcp/server/server.py
```

The `--lab-path` option does not create any simulation at startup.
It only sets the MCP server base `scenario_path` for that session and also
provides it to the model as context.

If you do not provide it, the client does not preload anything and there
should not be any default simulation.

If you prefer, you can still pass the path directly to the server with:

```bash
uv run python apps/mcp/client/cli.py \
  --env-file apps/mcp/client/.env \
  --server-command uv \
  --server-arg run \
  --server-arg python \
  --server-arg apps/mcp/server/server.py \
  --server-arg --scenario-path \
  --server-arg tutorial_scenarios/using_service_layer_02/three-cluster 
```

## Interactive Commands

- `/tools`: list detected MCP tools
- `/lab path/to/scenario`: set the lab/scenario path for the current session
- `/lab`: show the currently configured lab path
- `/paste`: enter multiline mode and finish with a line containing only `EOF`
- `/file path/to/file.json`: send the content of a file as a prompt
- `/help`: show help
- `/exit`: exit the client

If you started the client without `--lab-path`, you can set it later like this:

```text
you> /lab /Users/user/Projects/YAFS/lab_scenarios/case_three_cluster/three-cluster
```

This does not create any simulation automatically, but it leaves that path as
active context so the model can use `create_simulation` with that scenario.

## Viewing Invoked Tools

There are two visibility levels:

1. See tools available to the model:

```text
/tools
```

2. See tools actually invoked during the session:

```bash
uv run python apps/mcp/client/cli.py \
  --env-file apps/mcp/client/.env \
  --lab-path tutorial_scenarios/using_service_layer_02/three-cluster \
  --show-tool-calls \
  --server-command uv \
  --server-arg run \
  --server-arg python \
  --server-arg apps/mcp/server/server.py
```

The CLI prints the selected session folder at startup, and by default stores
the tool-call log in:

- `apps/mcp/client/artifacts/session-XXX-YYYYMMDD-HHMMSS/logs/tool_calls.jsonl`

It also stores:

- `apps/mcp/client/artifacts/session-XXX-YYYYMMDD-HHMMSS/logs/model_responses.jsonl`
- `apps/mcp/client/artifacts/session-XXX-YYYYMMDD-HHMMSS/logs/transcript.jsonl`
- `apps/mcp/client/artifacts/session-XXX-YYYYMMDD-HHMMSS/session.json`

You can change the tool-call path with `--tool-log-file`.

## Input Examples

### Paste Multiline JSON

If you want to paste JSON directly into the console, use `/paste` and end with
a line containing only `EOF`:

```text
you> /paste
paste> Enter multiline input. Finish with a line containing only EOF.
I want to create an application in the simulation using this JSON:
{
  "id": 2,
  "name": "Video Analytics",
  "latency_requirement": 25
}
EOF
```

### Send Content From a JSON File

If the content already exists in a file, you can send it entirely with `/file`:

```text
you> /file lab_scenarios/case_three_cluster/three-cluster/actions/create_application_example.json
```

You can also combine it with a more explicit instruction:

```text
you> /paste
paste> Enter multiline input. Finish with a line containing only EOF.
Create an application in the simulation using the content of this file:
lab_scenarios/case_three_cluster/three-cluster/actions/create_application_example.json

If you need parameters, use the full JSON as reference:
{
  "id": 2,
  "name": "Video Analytics",
  "latency_requirement": 25,
  "vnf_chain": ["PRE", "INF"]
}
EOF
```

## Notes

- The client uses OpenAI `Responses` endpoint with function calling.
- Available tools are fetched dynamically from `session.list_tools()`.
- The output of each MCP tool is returned to the model as
  `function_call_output`.
- If the server uses `stdio` transport, it must not write logs to `stdout`.
- Precedence order is: CLI flags > shell environment variables > `.env`.
- The client stores each session in its own artifacts folder by default.
- The client can log each tool call in console with `--show-tool-calls`.
