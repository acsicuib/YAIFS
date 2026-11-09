"""Count model actions and wall-clock time for experiment directories.

Each directory is one model run. Actions are model tool calls in
``actions.jsonl``. Elapsed time is ``elapsed_seconds`` in
``run_status.json``. Input and output tokens are the sums of
``prompt_tokens`` and ``completion_tokens`` in ``raw_responses.jsonl``.

From the repository root:

    uv run python tutorial_scenarios/delegating_LLM_decisions/summarize_experiments.py \
        tutorial_scenarios/delegating_LLM_decisions/results/20261008-112715/anthropic_claude-sonnet-5.5 \
        tutorial_scenarios/delegating_LLM_decisions/results/20261008-100136/openai_gpt-6-luna \
        tutorial_scenarios/delegating_LLM_decisions/results/20261008-110516/x-ai_grok-4.7
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return {}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def experiment_dirs(path: Path) -> list[Path]:
    if (path / "actions.jsonl").exists() or (path / "run_status.json").exists():
        return [path]
    found = sorted(
        item
        for item in path.iterdir()
        if item.is_dir() and (item / "run_status.json").exists()
    )
    if not found:
        raise FileNotFoundError(f"No experiment under {path}")
    return found


def format_elapsed(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    total = int(round(seconds))
    minutes, rest = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {rest}s"
    if minutes:
        return f"{minutes}m {rest}s"
    return f"{rest}s"


def usage_tokens(row: dict[str, Any]) -> tuple[int, int]:
    response = row.get("response")
    if not isinstance(response, dict):
        return 0, 0
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return 0, 0
    return (
        int(usage.get("prompt_tokens") or 0),
        int(usage.get("completion_tokens") or 0),
    )


def summarize(directory: Path) -> dict[str, Any]:
    status = load_json(directory / "run_status.json")
    actions = load_jsonl(directory / "actions.jsonl")
    model_calls = [
        row for row in actions if row.get("actor") in (None, "model")
    ]
    failed = sum(1 for row in model_calls if row.get("ok") is False)
    elapsed = status.get("elapsed_seconds")
    prompt_tokens = 0
    completion_tokens = 0
    for row in load_jsonl(directory / "raw_responses.jsonl"):
        prompt, completion = usage_tokens(row)
        prompt_tokens += prompt
        completion_tokens += completion
    return {
        "model": str(status.get("model") or directory.name),
        "actions": len(model_calls),
        "failed": failed,
        "elapsed_seconds": (
            float(elapsed) if elapsed is not None else None
        ),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "directory": directory,
    }


def print_table(rows: list[dict[str, Any]]) -> None:
    headers = (
        "Model",
        "Actions",
        "Failed",
        "Elapsed",
        "Seconds",
        "In tokens",
        "Out tokens",
    )
    body = [
        (
            str(row["model"]),
            str(row["actions"]),
            str(row["failed"]),
            format_elapsed(row["elapsed_seconds"]),
            (
                f"{row['elapsed_seconds']:.1f}"
                if row["elapsed_seconds"] is not None
                else "n/a"
            ),
            f"{row['prompt_tokens']:,}",
            f"{row['completion_tokens']:,}",
        )
        for row in rows
    ]
    widths = [
        max(len(header), *(len(item[index]) for item in body))
        for index, header in enumerate(headers)
    ]
    line = "  ".join(
        header.ljust(width) for header, width in zip(headers, widths)
    )
    print(line)
    print("  ".join("-" * width for width in widths))
    for item in body:
        print(
            "  ".join(
                value.ljust(width) for value, width in zip(item, widths)
            )
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directories",
        nargs="+",
        type=Path,
        help=(
            "Model run directories, or a parent directory that "
            "contains one subdirectory per model."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows: list[dict[str, Any]] = []
    for path in args.directories:
        for directory in experiment_dirs(path.resolve()):
            rows.append(summarize(directory))
    print_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
