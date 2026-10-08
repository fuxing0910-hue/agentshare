"""Small, explicit adapters. Raw tool bodies never become message text.

Supported Codex shapes follow openai/codex protocol ResponseItem and RolloutItem.
This module intentionally ignores reasoning, metadata, images, and unknown blocks.
"""

from collections import Counter
from dataclasses import dataclass


MAX_MESSAGE_CHARS = 100_000


class AdapterError(ValueError):
    """An input cannot be represented within the documented limits."""


@dataclass
class RawEvent:
    kind: str
    label: str
    text: str
    status: str = "info"


# Never put an arbitrary tool name into an export: names may contain secrets.
TOOL_NAMES = {
    "Bash": "Bash", "Read": "Read", "Write": "Write", "Edit": "Edit",
    "MultiEdit": "MultiEdit", "Glob": "Glob", "Grep": "Grep",
    "Task": "Task", "Agent": "Agent", "WebFetch": "WebFetch",
    "WebSearch": "WebSearch", "TodoWrite": "TodoWrite", "Skill": "Skill",
    "AskUserQuestion": "AskUserQuestion", "exec_command": "exec_command",
    "shell": "shell", "shell_command": "shell_command",
    "apply_patch": "apply_patch", "write_stdin": "write_stdin",
    "update_plan": "update_plan", "read_file": "read_file",
    "list_dir": "list_dir", "find_file": "find_file",
    "grep_files": "grep_files", "functions.exec_command": "exec_command",
    "functions.apply_patch": "apply_patch", "functions.write_stdin": "write_stdin",
}


def tool_label(name: object) -> str:
    return TOOL_NAMES.get(name, "Other tool") if isinstance(name, str) else "Other tool"


def message_event(kind: str, text: str, line: int) -> RawEvent | None:
    if len(text) > MAX_MESSAGE_CHARS:
        raise AdapterError(f"Line {line}: message exceeds {MAX_MESSAGE_CHARS:,} characters.")
    if not text.strip():
        return None
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise AdapterError(f"Line {line}: message contains an invalid Unicode surrogate.") from exc
    return RawEvent(kind, "User message" if kind == "user" else "Assistant message", text)


def status_for(payload: dict) -> str:
    """Read only explicit outcome fields, never infer success from an output body."""
    if payload.get("is_error") is True:
        return "error"
    if payload.get("is_error") is False:
        return "success"
    value = payload.get("status")
    if value in ("failed", "error", "failure"):
        return "error"
    if value in ("completed", "success", "succeeded"):
        return "success"
    return "info"


def text_blocks(content: object, types: tuple[str, ...]) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        block["text"] for block in content
        if isinstance(block, dict) and block.get("type") in types
        and isinstance(block.get("text"), str)
    )


def detect_format(records: list[tuple[int, dict]]) -> str:
    kinds = set()
    for _, record in records:
        kind = record.get("type")
        if kind in ("response_item", "event_msg", "session_meta", "turn_context"):
            kinds.add("codex")
        elif kind in ("user", "assistant") and isinstance(record.get("message"), dict):
            kinds.add("claude")
    if len(kinds) > 1:
        raise AdapterError("Mixed Claude and Codex records: select one transcript file.")
    if not kinds:
        raise AdapterError("No supported Claude or Codex records found. Choose a supported JSONL transcript.")
    return kinds.pop()


def parse_claude(records: list[tuple[int, dict]]) -> tuple[list[RawEvent], int, int]:
    events, tools = [], {}
    omitted, unsupported = 0, 0
    for line, record in records:
        role = record.get("type")
        message = record.get("message")
        if role not in ("user", "assistant") or not isinstance(message, dict):
            unsupported += 1
            continue
        content = message.get("content")
        recognized = False
        if isinstance(content, str):
            event = message_event(role, content, line)
            if event:
                events.append(event)
                recognized = True
        elif isinstance(content, list):
            # Bound the complete visible message, not each block separately.
            message_event(role, text_blocks(content, ("text",)), line)
            # Preserve visible block order, including text on either side of a tool.
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text" and isinstance(block.get("text"), str):
                    event = message_event(role, block["text"], line)
                    if event:
                        events.append(event)
                    recognized = True
                elif block_type == "tool_use":
                    label = tool_label(block.get("name"))
                    call_id = block.get("id")
                    if isinstance(call_id, str):
                        tools[call_id] = label
                    events.append(RawEvent("tool", label, "Tool input omitted."))
                    omitted += 1
                    recognized = True
                elif block_type == "tool_result":
                    call_id = block.get("tool_use_id")
                    label = tools.get(call_id, "Other tool") if isinstance(call_id, str) else "Other tool"
                    events.append(RawEvent("tool", label, "Tool output omitted.", status_for(block)))
                    omitted += 1
                    recognized = True
        if not recognized:
            unsupported += 1
    return events, omitted, unsupported


def codex_message(payload: dict, line: int) -> RawEvent | None:
    role = payload.get("role")
    if payload.get("type") != "message" or role not in ("user", "assistant"):
        return None
    text = text_blocks(payload.get("content"), ("input_text", "output_text"))
    return message_event(role, text, line)


def parse_codex(records: list[tuple[int, dict]]) -> tuple[list[RawEvent], int, int]:
    events, tools = [], {}
    omitted, unsupported = 0, 0
    # event_msg often repeats response_item text. Consume matching occurrences,
    # rather than globally deduplicating legitimate repeated messages like "yes".
    canonical = Counter()
    for line, record in records:
        if record.get("type") == "response_item" and isinstance(record.get("payload"), dict):
            event = codex_message(record["payload"], line)
            if event:
                canonical[(event.kind, event.text)] += 1
    for line, record in records:
        record_type = record.get("type")
        payload = record.get("payload")
        if not isinstance(payload, dict):
            unsupported += 1
            continue
        payload_type = payload.get("type")
        if record_type == "response_item":
            if payload_type == "message":
                event = codex_message(payload, line)
                if event:
                    events.append(event)
                else:
                    unsupported += 1
            elif payload_type in ("function_call", "custom_tool_call"):
                label = tool_label(payload.get("name"))
                call_id = payload.get("call_id")
                if isinstance(call_id, str):
                    tools[call_id] = label
                events.append(RawEvent("tool", label, "Tool input omitted.", status_for(payload)))
                omitted += 1
            elif payload_type in ("function_call_output", "custom_tool_call_output"):
                call_id = payload.get("call_id")
                label = tools.get(call_id, "Other tool") if isinstance(call_id, str) else "Other tool"
                events.append(RawEvent("tool", label, "Tool output omitted.", status_for(payload)))
                omitted += 1
            else:
                unsupported += 1
        elif record_type == "event_msg" and payload_type in ("user_message", "agent_message"):
            role = "user" if payload_type == "user_message" else "assistant"
            text = payload.get("message")
            if not isinstance(text, str):
                unsupported += 1
                continue
            event = message_event(role, text, line)
            if not event:
                unsupported += 1
                continue
            key = (role, text)
            if canonical[key]:
                canonical[key] -= 1
            else:
                events.append(event)
        else:
            unsupported += 1
    return events, omitted, unsupported


def parse_records(records: list[tuple[int, dict]], format: str = "auto") -> tuple[str, list[RawEvent], int, int]:
    if format not in ("auto", "claude", "codex"):
        raise AdapterError("Format must be auto, claude, or codex.")
    selected = detect_format(records) if format == "auto" else format
    parser = parse_claude if selected == "claude" else parse_codex
    events, omitted, unsupported = parser(records)
    if not events:
        raise AdapterError(f"No supported message or tool events for {selected} format.")
    return selected, events, omitted, unsupported
