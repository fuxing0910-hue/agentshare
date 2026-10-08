"""Render a local transcript review page from an already sanitized bundle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_MARKER = "__AGENTSHARE_BUNDLE_JSON__"
_EVENT_FIELDS = ("id", "kind", "label", "text", "status", "time")


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _review_data(bundle: dict[str, Any]) -> dict[str, Any]:
    """Whitelist review fields so parser metadata cannot enter the document."""
    events = []
    for position, event in enumerate(bundle.get("events", []), 1):
        if not isinstance(event, dict):
            continue
        item = {field: _text(event.get(field)) for field in _EVENT_FIELDS}
        item["id"] = f"e{position}"  # Unique UI identifiers, independent of source IDs.
        item["kind"] = item["kind"] if item["kind"] in {"user", "assistant", "tool"} else "tool"
        item["status"] = item["status"] if item["status"] in {"info", "error", "success"} else "info"
        events.append(item)
    stats = bundle.get("stats", {})
    stats = stats if isinstance(stats, dict) else {}
    redactions = stats.get("redactions", {})
    redactions = redactions if isinstance(redactions, dict) else {}
    return {
        "version": 1,
        "title": "AgentShare review",
        "source_format": _text(bundle.get("source_format")),
        "events": events,
        "stats": {
            "events": len(events),
            "omitted_tool_bodies": _count(stats.get("omitted_tool_bodies")),
            "unsupported_records": _count(stats.get("unsupported_records")),
            "redactions": {_text(key): _count(value) for key, value in redactions.items() if isinstance(key, str)},
        },
        "warnings": [warning for warning in bundle.get("warnings", []) if isinstance(warning, str)],
    }


def render_review(bundle: dict[str, Any]) -> str:
    """Return a self-contained HTML review; this is not the selected-only export.

    Input must already be sanitized. Unknown event and bundle fields are discarded.
    JSON is escaped for its HTML script-data context; message content is rendered
    through DOM textContent/textarea.value, never interpreted as HTML or Markdown.
    """
    if not isinstance(bundle, dict):
        raise TypeError("bundle must be a dictionary")
    payload = json.dumps(_review_data(bundle), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    for character, replacement in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        payload = payload.replace(character, replacement)
    template = (Path(__file__).with_name("templates") / "review.html").read_text(encoding="utf-8")
    if template.count(_MARKER) != 1:
        raise RuntimeError("review template must have exactly one data marker")
    return template.replace(_MARKER, payload)
