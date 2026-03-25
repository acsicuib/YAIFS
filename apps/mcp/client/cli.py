from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.text import Text
except ImportError:  # pragma: no cover - graceful fallback for partial installs
    Console = None
    Panel = None
    Syntax = None
    Text = None


SYSTEM_PROMPT = """
You are an assistant controlling a YAIFS simulation through MCP tools.
The public project branding is YAIFS, while the Python package remains yafs.
Prefer inspecting state before acting.
When interacting with the simulator:
- Use tools instead of inventing simulator state.
- Make small, reversible actions when possible.
- Explain briefly what you changed or observed.
- If the user asks for a simulation action, decide which MCP tool to call.
- Use create_simulation for a raw lab/scenario directory containing files like
  logging.ini, topology.json, services.json, placements.json and users.json.
- Use create_simulation_from_configuration only for generated configuration
  directories or files that include configuration.json metadata.
"""

MULTILINE_END_MARKER = "EOF"
YAIFS_ASCII = r"""
██╗   ██╗ █████╗ ██╗███████╗███████╗
╚██╗ ██╔╝██╔══██╗██║██╔════╝██╔════╝
 ╚████╔╝ ███████║██║█████╗  ███████╗
  ╚██╔╝  ██╔══██║██║██╔══╝  ╚════██║
   ██║   ██║  ██║██║██║     ███████║
   ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝     ╚══════╝
"""


def _build_console() -> Any:
    if Console is None:
        return None
    return Console(highlight=True)


def _console_print(console: Any, message: str, *, style: str | None = None) -> None:
    if console is None:
        print(message)
        return
    console.print(message, style=style)


def _render_welcome(
    console: Any,
    *,
    model: str,
    server_command: str,
    has_lab_path: bool,
) -> None:
    if console is None or Panel is None or Text is None:
        print(YAIFS_ASCII)
        print("YAIFS MCP Client v.1.0")
        return

    logo = Text(YAIFS_ASCII.strip("\n"), style="bold cyan")
    subtitle = Text("YAIFS MCP Client", style="bold white")
    capabilities = Text()
    capabilities.append(
        "Control YAIFS simulations in your own language.\n",
        style="white",
    )
    capabilities.append(
        "Explore labs, create simulations, run forks, pause/resume, and analyze metrics.\n",
        style="white",
    )
    console.print(
        Panel(
            Text.assemble(logo, "\n", subtitle, "\n\n", capabilities),
            # border_style="cyan",
            border_style="bright_magenta",
            title="Yet Another Intelligent Fog Simulator",
            subtitle=f"model={model} | server={server_command}",
            expand=False,
        )
    )

    info_lines = [
        "[bold]Getting started[/bold]",
        "- Use [cyan]/tools[/cyan] to list available MCP tools.",
        "- Use [cyan]/lab /path/to/lab[/cyan] to set a scenario for this session.",
        "- Ask for actions like run, pause, fork/clone, or inspect the simulation.",
    ]
    if has_lab_path:
        info_lines.append(
            "- This session starts with a [cyan]lab-path[/cyan] already set."
        )
    console.print(Panel("\n".join(info_lines), border_style="blue", expand=False))

    if Syntax is not None:
        console.print(
            Panel(
                Syntax(
                    "you> /lab /Users/isaac/Projects/YAFS/lab_scenarios/case_three_cluster/three-cluster\n"
                    "you> create a simulation named demo and run it for 500 units\n"
                    "you> fork it and remove a cluster to compare metrics",
                    "text",
                    theme="ansi_dark",
                    line_numbers=False,
                ),
                title="Examples",
                border_style="green",
                expand=False,
            )
        )


def _load_env_file(path: str) -> None:
    """
    Load simple KEY=VALUE pairs from a .env-like file into os.environ.

    Existing environment variables are preserved.
    """
    env_path = os.path.abspath(path)
    if not os.path.exists(env_path):
        return

    with open(env_path, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key or key in os.environ:
                continue

            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            os.environ[key] = value


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value))
    return str(value)


def _extract_text_from_response(response: dict[str, Any]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    parts: list[str] = []
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                text = content.get("text", "")
                if text:
                    parts.append(text)
    return "\n".join(parts).strip()


def _read_multiline_prompt() -> str:
    print(
        "paste> Enter multiline input. Finish with a line "
        f"containing only {MULTILINE_END_MARKER}."
    )
    lines: list[str] = []
    while True:
        line = input()
        if line == MULTILINE_END_MARKER:
            break
        lines.append(line)
    return "\n".join(lines)


def _read_prompt_from_file(path_str: str) -> str:
    prompt_path = Path(path_str).expanduser()
    if not prompt_path.is_absolute():
        prompt_path = Path.cwd() / prompt_path
    with prompt_path.open(encoding="utf-8") as handle:
        return handle.read()


class OpenAIResponsesClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def create_response(
        self,
        *,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "input": input_items,
            "tools": tools,
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/responses",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"OpenAI API error {exc.code}: {detail}"
            ) from exc


class MCPChatClient:
    def __init__(
        self,
        session: Any,
        llm: OpenAIResponsesClient,
        *,
        tool_log_path: str | None = None,
        show_tool_calls: bool = False,
        session_context: list[str] | None = None,
    ) -> None:
        self.session = session
        self.llm = llm
        self.tool_log_path = tool_log_path
        self.show_tool_calls = show_tool_calls
        self.history: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": SYSTEM_PROMPT.strip(),
                    }
                ],
            }
        ]
        for context_line in session_context or []:
            self.history.append(
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": context_line,
                        }
                    ],
                }
            )
        self.tool_specs: list[dict[str, Any]] = []
        self.tool_names: list[str] = []
        self.current_lab_path: str | None = None

    async def initialize(self) -> None:
        tool_result = await self.session.list_tools()
        tools = getattr(tool_result, "tools", [])
        self.tool_specs = [self._mcp_tool_to_openai(tool) for tool in tools]
        self.tool_names = [spec["name"] for spec in self.tool_specs]

    def set_lab_path(self, path: str) -> None:
        self.current_lab_path = path
        self.history.append(
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "The current lab/scenario path selected by the user is "
                            f"{path}. Treat it as a raw scenario directory unless the "
                            "user explicitly says it is a generated configuration."
                        ),
                    }
                ],
            }
        )

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        result = await self.session.call_tool(tool_name, arguments=arguments)
        self._log_tool_call(
            tool_name=tool_name,
            arguments=arguments,
            result=result,
        )
        return result

    def _log_tool_call(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "arguments": _jsonable(arguments),
            "result": _jsonable(result),
        }
        if self.show_tool_calls:
            print(f"tool> {tool_name} {json.dumps(entry['arguments'], ensure_ascii=True)}")
        if not self.tool_log_path:
            return
        log_path = os.path.abspath(self.tool_log_path)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")

    def _mcp_tool_to_openai(self, tool: Any) -> dict[str, Any]:
        schema = getattr(tool, "inputSchema", None)
        if schema is None:
            schema = getattr(tool, "input_schema", None)
        if schema is None:
            schema = {"type": "object", "properties": {}}

        return {
            "type": "function",
            "name": getattr(tool, "name"),
            "description": getattr(tool, "description", "") or "",
            "parameters": _jsonable(schema),
            "strict": False,
        }

    async def ask(self, prompt: str) -> str:
        conversation = list(self.history)
        conversation.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    }
                ],
            }
        )

        while True:
            response = self.llm.create_response(
                input_items=conversation,
                tools=self.tool_specs,
            )
            output_items = response.get("output", [])
            conversation.extend(output_items)

            function_calls = [
                item for item in output_items if item.get("type") == "function_call"
            ]
            if not function_calls:
                final_text = _extract_text_from_response(response)
                if not final_text:
                    final_text = "(no text response)"
                self.history = conversation
                return final_text

            for call in function_calls:
                tool_name = call["name"]
                arguments = json.loads(call.get("arguments") or "{}")
                result = await self.call_tool(tool_name, arguments)
                conversation.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps(_jsonable(result), ensure_ascii=True),
                    }
                )


async def run_cli(args: argparse.Namespace) -> int:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        print(
            "Missing dependency: install `mcp[cli]` before using this client.",
            file=sys.stderr,
        )
        return 2

    _load_env_file(args.env_file)

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is required.", file=sys.stderr)
        return 2

    model = args.model or os.environ.get("OPENAI_MODEL", "gpt-5")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    server_env = dict(os.environ)
    server_args = list(args.server_args)
    session_context: list[str] = []
    console = _build_console()

    artifacts_dir = args.artifacts_dir
    configurations_dir = args.configurations_dir
    results_dir = args.results_dir
    if artifacts_dir:
        artifacts_root = os.path.abspath(artifacts_dir)
        if configurations_dir is None:
            configurations_dir = os.path.join(artifacts_root, "configurations")
        if results_dir is None:
            results_dir = os.path.join(artifacts_root, "results")

    if configurations_dir is not None:
        abs_configurations_dir = os.path.abspath(configurations_dir)
        os.makedirs(abs_configurations_dir, exist_ok=True)
        server_env["YAFS_MCP_CONFIGURATIONS_DIR"] = abs_configurations_dir
    if results_dir is not None:
        abs_results_dir = os.path.abspath(results_dir)
        os.makedirs(abs_results_dir, exist_ok=True)
        server_env["YAFS_MCP_RESULTS_DIR"] = abs_results_dir

    if args.lab_path:
        abs_lab_path = os.path.abspath(args.lab_path)
        if "--scenario-path" not in server_args:
            server_args.extend(["--scenario-path", abs_lab_path])
        session_context.append(
            "The default lab scenario path for this session is "
            f"{abs_lab_path}. No simulation is created automatically at startup."
        )

    server_params = StdioServerParameters(
        command=args.server_command,
        args=server_args,
        env=server_env,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            llm = OpenAIResponsesClient(
                api_key=api_key,
                model=model,
                base_url=base_url,
            )
            chat = MCPChatClient(
                session,
                llm,
                tool_log_path=args.tool_log_file,
                show_tool_calls=args.show_tool_calls,
                session_context=session_context,
            )
            await chat.initialize()
            if args.lab_path:
                chat.set_lab_path(abs_lab_path)

            _render_welcome(
                console,
                model=model,
                server_command=args.server_command,
                has_lab_path=bool(args.lab_path),
            )
            # _console_print(
            #     console,
            #     f"Connected to MCP server. Tools: {', '.join(chat.tool_names)}",
            #     style="bold green",
            # )

            _console_print(console, "Type /help for commands.", style="dim")

            while True:
                try:
                    prompt = input("you> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    return 0

                if not prompt:
                    continue
                if prompt in {"/exit", "/quit"}:
                    return 0
                if prompt == "/help":
                    _console_print(console, "/tools  list MCP tools")
                    _console_print(console, "/lab    set or show the current lab/scenario path context")
                    _console_print(console, "/paste  enter multiline input mode")
                    _console_print(console, "/file   send the contents of a file as the prompt")
                    _console_print(console, "/exit   quit the client")
                    continue
                if prompt == "/tools":
                    for name in chat.tool_names:
                        _console_print(console, name, style="cyan")
                    continue
                if prompt == "/lab":
                    if chat.current_lab_path:
                        _console_print(console, chat.current_lab_path, style="cyan")
                    else:
                        _console_print(console, "No lab path set for this session.", style="yellow")
                    continue
                if prompt.startswith("/lab "):
                    lab_path = prompt[len("/lab ") :].strip()
                    if not lab_path:
                        _console_print(console, "error> Usage: /lab path/to/scenario", style="bold red")
                        continue
                    abs_lab_path = os.path.abspath(os.path.expanduser(lab_path))
                    chat.set_lab_path(abs_lab_path)
                    _console_print(console, f"lab> {abs_lab_path}", style="bold cyan")
                    continue
                if prompt == "/paste":
                    try:
                        prompt = _read_multiline_prompt()
                    except (EOFError, KeyboardInterrupt):
                        print()
                        continue
                    if not prompt.strip():
                        continue
                elif prompt.startswith("/file "):
                    file_path = prompt[len("/file ") :].strip()
                    if not file_path:
                        _console_print(console, "error> Usage: /file path/to/input.json", style="bold red")
                        continue
                    try:
                        prompt = _read_prompt_from_file(file_path)
                    except OSError as exc:
                        _console_print(console, f"error> Could not read file: {exc}", style="bold red")
                        continue

                try:
                    answer = await chat.ask(prompt)
                except Exception as exc:
                    _console_print(console, f"error> {exc}", style="bold red")
                    continue

                _console_print(console, f"model> {answer}", style="white")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interactive MCP client for controlling a simulation with an LLM.",
    )
    parser.add_argument(
        "--server-command",
        required=True,
        help="Executable used to start the MCP server, e.g. uv or python.",
    )
    parser.add_argument(
        "--artifacts-dir",
        default=None,
        help="Base directory for conversation artifacts. Defaults configs/results under it.",
    )
    parser.add_argument(
        "--lab-path",
        default=None,
        help="Base lab/scenario path passed to the MCP server as --scenario-path without creating a simulation.",
    )
    parser.add_argument(
        "--configurations-dir",
        default=None,
        help="Directory to store generated simulation configurations for this conversation.",
    )
    parser.add_argument(
        "--results-dir",
        default=None,
        help="Directory to store simulation traces/results for this conversation.",
    )
    parser.add_argument(
        "--env-file",
        default="apps/mcp/client/.env",
        help="Path to a .env file loaded before reading environment variables.",
    )
    parser.add_argument(
        "--server-arg",
        dest="server_args",
        action="append",
        default=[],
        help="Argument passed to the MCP server command. Repeat as needed.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="OpenAI model name. Defaults to OPENAI_MODEL or gpt-5.",
    )
    parser.add_argument(
        "--show-tool-calls",
        action="store_true",
        help="Print each MCP tool invocation as it happens.",
    )
    parser.add_argument(
        "--tool-log-file",
        default="apps/mcp/client/tool_calls.jsonl",
        help="Write MCP tool invocations to this JSONL file.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="OpenAI API key. Defaults to OPENAI_API_KEY.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(run_cli(args))


if __name__ == "__main__":
    raise SystemExit(main())
