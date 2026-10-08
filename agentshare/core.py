"""Load only an explicit JSONL file and build a minimized export bundle."""

import json
from pathlib import Path
from typing import Iterable

from .adapters import AdapterError, parse_records
from .redact import Redactor


MAX_INPUT_BYTES = 20 * 1024 * 1024


class InputError(ValueError):
    """A clear, non-sensitive error suitable for displaying in the CLI."""


def _reject_nonfinite(value):
    raise ValueError("JSON constants must be finite.")


def read_records(path: str | Path) -> list[tuple[int, dict]]:
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise InputError("Cannot read input file.") from exc
    if len(data) > MAX_INPUT_BYTES:
        raise InputError("Input exceeds the 20 MiB file limit.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError("Input must be UTF-8 JSONL.") from exc
    records = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line, parse_constant=_reject_nonfinite)
        except (ValueError, RecursionError) as exc:
            column = getattr(exc, "colno", None)
            suffix = f" (column {column})" if column else ""
            raise InputError(f"Line {number}: invalid JSON{suffix}.") from exc
        if not isinstance(record, dict):
            raise InputError(f"Line {number}: expected a JSON object.")
        records.append((number, record))
    if not records:
        raise InputError("Input contains no JSON records.")
    return records


def _bundle(records: list[tuple[int, dict]], format: str = "auto", terms: Iterable[str] = ()) -> dict:
    try:
        selected, raw_events, omitted, unsupported = parse_records(records, format)
        redactor = Redactor(terms)
    except (AdapterError, ValueError) as exc:
        raise InputError(str(exc)) from exc
    events = []
    for number, event in enumerate(raw_events, 1):
        events.append({
            "id": f"e{number}", "kind": event.kind,
            "label": redactor.redact(event.label),
            "text": redactor.redact(event.text),
            "status": event.status, "time": "",
        })
    return {
        "version": 1, "title": "AgentShare review", "source_format": selected,
        "events": events,
        "stats": {"events": len(events), "omitted_tool_bodies": omitted,
                  "redactions": dict(sorted(redactor.counts.items())),
                  "unsupported_records": unsupported},
        "warnings": [
            "Automated redaction is incomplete. Review every selected event before sharing.",
            "Tool inputs and output bodies, source filenames, session IDs, and absolute timestamps are excluded.",
            "Only supported user/assistant text and tool summaries are retained. Reasoning, images, metadata, and other records are omitted.",
            "Tool outcomes use explicit status fields only; an omitted result body does not prove success or failure.",
            "Home-path redaction may omit the remainder of a line. Custom literal terms are case-sensitive.",
        ],
    }


def build_bundle(path: str | Path, format: str = "auto", terms: Iterable[str] = ()) -> dict:
    """Return a sanitized, allowlisted bundle; never include the source filename."""
    return _bundle(read_records(path), format, terms)


DEMO_CLAUDE = [
    {"type": "system", "sessionId": "synthetic-session-only", "cwd": "C:\\Users\\demo\\private-project"},
    {"type": "user", "message": {"role": "user", "content": "Synthetic demo: please inspect this failed test. Contact demo@example.test.\nFake token ghp_FAKE_DEMO_NOT_A_REAL_TOKEN.\nLocal path C:\\Users\\demo\\private-project\\test.py"}},
    {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "I will inspect the failure; tool arguments and output will be omitted from this review."}, {"type": "tool_use", "id": "synthetic-tool-1", "name": "Bash", "input": {"command": "echo FAKE_TOOL_INPUT_ONLY"}}]}},
    {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "synthetic-tool-1", "is_error": True, "content": "FAKE_TOOL_OUTPUT_ONLY: API_KEY=FAKE_PRIVATE_VALUE"}]}},
    {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "The tool reported an error. This export intentionally omits the output body; add a manually reviewed description before sharing."}]}},
]


def demo_bundle() -> dict:
    """Build the bundled synthetic example without requiring package data files."""
    return _bundle(list(enumerate(DEMO_CLAUDE, 1)), "claude")
