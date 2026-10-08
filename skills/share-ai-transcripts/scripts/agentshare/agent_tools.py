"""Local function-tool definitions and dispatch; no model SDK or API calls.

Definition shapes follow OpenAI Responses, DeepSeek Chat Completions,
Claude Messages, and Gemini Interactions official function-calling formats.
"""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
from threading import Lock

from .__main__ import main as cli_main


TOOL_NAME = "prepare_transcript_review"
PROVIDERS = ("openai", "deepseek", "claude", "gemini")
DESCRIPTION = (
    "Prepare a private local review page from one explicitly user-specified "
    "Claude Code or Codex UTF-8 JSONL transcript. Omit tool arguments and output "
    "bodies and apply best-effort redaction; the user must select, edit, and "
    "inspect messages in a browser before exporting HTML or Markdown. Nothing "
    "is initially selected. Never upload or automatically share content, scan "
    "session folders, or execute recorded commands. This tool is not for "
    "general database auditing. Returns the local review path only, without "
    "transcript text; redaction does not guarantee removal of every secret."
)
_FIELDS = ("transcript_path", "output_html_path", "format", "private_terms_path")
_SCHEMA = {
    "type": "object",
    "properties": {
        "transcript_path": {
            "type": "string",
            "description": "Explicit local path to the user's Claude Code or Codex UTF-8 JSONL file; do not discover or scan for one.",
        },
        "output_html_path": {
            "type": "string",
            "description": "Local HTML review destination, different from the transcript and private term file. Keep the candidate review private.",
        },
        "format": {
            "type": "string", "enum": ["auto", "claude", "codex"],
            "description": "Transcript adapter; use auto to detect supported Claude Code or Codex shapes.",
        },
        "private_terms_path": {
            "type": ["string", "null"],
            "description": "Explicit local UTF-8 private term file, one literal per line, or null when unused. Do not return its contents.",
        },
    },
    "required": list(_FIELDS),
    "additionalProperties": False,
}
_CLI_LOCK = Lock()
_MAX_REQUEST_BYTES = 64 * 1024


class ToolError(ValueError):
    """A deliberately static error that does not contain input data."""


def tool_definitions(provider: str) -> list[dict]:
    """Return a fresh provider-specific tools array, without making API calls."""
    if provider not in PROVIDERS:
        raise ToolError("Unsupported provider.")
    definition = {"name": TOOL_NAME, "description": DESCRIPTION}
    schema = deepcopy(_SCHEMA)
    if provider == "claude":
        definition["input_schema"] = schema
        return [definition]
    definition["parameters"] = schema
    if provider == "deepseek":
        return [{"type": "function", "function": definition}]
    definition["type"] = "function"
    if provider == "openai":
        definition["strict"] = True
    return [definition]


def _validate_arguments(name: object, arguments: object) -> dict:
    if name != TOOL_NAME:
        raise ToolError("Unknown tool name.")
    if not isinstance(arguments, dict):
        raise ToolError("Tool arguments must be a JSON object.")
    if set(arguments) != set(_FIELDS):
        raise ToolError("Tool arguments must contain exactly all required fields.")
    for field in ("transcript_path", "output_html_path"):
        value = arguments[field]
        if not isinstance(value, str) or not value.strip():
            raise ToolError("Local input and output paths must be nonempty strings.")
    if not isinstance(arguments["format"], str) or arguments["format"] not in ("auto", "claude", "codex"):
        raise ToolError("Format must be auto, claude, or codex.")
    terms = arguments["private_terms_path"]
    if terms is not None and (not isinstance(terms, str) or not terms.strip()):
        raise ToolError("Private term path must be null or a nonempty string.")
    return arguments


def call_tool(name: str, arguments: dict) -> dict:
    """Build only a private candidate review and return no transcript content.

    ToolError contains a safe message. Existing CLI file-alias checks protect
    transcript/term files, including existing hardlinks. CLI output is discarded.
    """
    values = _validate_arguments(name, arguments)
    try:
        # Absolute paths prevent a filename beginning with '-' from becoming a
        # CLI option and give callers one unambiguous local result path.
        source = Path(values["transcript_path"]).resolve()
        output = Path(values["output_html_path"]).resolve()
        for path in (source, output):
            str(path).encode("utf-8")
        cli_arguments = ["build", str(source), "--output", str(output), "--format", values["format"]]
        if values["private_terms_path"] is not None:
            terms = Path(values["private_terms_path"]).resolve()
            str(terms).encode("utf-8")
            cli_arguments.extend(["--term-file", str(terms)])
        # CLI redirects are process-wide; serialize tool calls in this adapter.
        with _CLI_LOCK, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = cli_main(cli_arguments)
    except (Exception, SystemExit):
        raise ToolError("Review preparation failed. Check local paths and transcript format.") from None
    if result != 0:
        raise ToolError("Review build failed. Check paths, JSONL format, and output-file separation.")
    return {"review_path": str(output), "manual_review_required": True, "selected_count": 0}


def _reject_json_constant(value):
    raise ToolError("Request must contain valid JSON.")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ToolError("Request must not contain duplicate JSON fields.")
        result[key] = value
    return result


def _read_request(path: Path) -> dict:
    try:
        with path.open("rb") as stream:
            data = stream.read(_MAX_REQUEST_BYTES + 1)
        if len(data) > _MAX_REQUEST_BYTES:
            raise ToolError("JSON request exceeds 64 KiB.")
        request = json.loads(data.decode("utf-8-sig"), parse_constant=_reject_json_constant, object_pairs_hook=_unique_object)
    except ToolError:
        raise
    except (OSError, ValueError, RecursionError):
        raise ToolError("Cannot read a valid UTF-8 JSON request.") from None
    if not isinstance(request, dict) or set(request) != {"name", "arguments"}:
        raise ToolError("Request must contain exactly name and arguments.")
    return request


class _SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ToolError("Invalid command-line arguments.")


def main(argv=None) -> int:
    parser = _SafeParser(description="List model-tool definitions or execute an explicit local review request.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true", help="Print provider-specific tool definitions as JSON.")
    mode.add_argument("--request", type=Path, help="Read one local JSON object containing name and arguments.")
    parser.add_argument("--provider", choices=PROVIDERS, default="openai")
    try:
        args = parser.parse_args(argv)
        if args.list:
            result = tool_definitions(args.provider)
        else:
            request = _read_request(args.request)
            result = call_tool(request["name"], request["arguments"])
    except ToolError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True))
        return 2
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
