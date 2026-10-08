# Supported transcript shapes

AgentShare accepts one local UTF-8 JSONL file (optional UTF-8 BOM), up to 20 MiB. Each nonblank line must be a JSON object. Invalid lines fail with a line number; they do not silently produce a partial report. User/assistant messages longer than 100,000 characters are rejected.

## Claude Code

Top-level `type: user` or `type: assistant`, with a `message` object:

- `message.content` may be a text string.
- Array content supports `text` blocks, `tool_use` blocks and `tool_result` blocks in their original order.
- A tool call retains a name from the built-in allowlist (otherwise `Other tool`). Its arguments are omitted.
- A tool result links to the previously seen call label. Its body is omitted; explicit `is_error` determines an outcome when available.

Reasoning/thinking, images, metadata, unknown blocks and other record types are omitted. `unsupported_records` counts records without a recognized event; it is not a count of every unknown nested block.

## Codex

Top-level `type: response_item` with a `payload` object supports:

- `payload.type: message`, role `user` or `assistant`, and `input_text`/`output_text` content blocks.
- `function_call` and `custom_tool_call`: tool label only, arguments/input omitted.
- `function_call_output` and `custom_tool_call_output`: linked tool label only, output omitted.

Top-level `type: event_msg` with `payload.type: user_message` or `agent_message` uses the payload's text `message` field as a fallback. Matching fallback/canonical messages are deduplicated by occurrence, so legitimate repeated messages are retained.

Session metadata, reasoning, turn context, images, and other record types are omitted and counted. The adapters follow the shapes in the [upstream Codex protocol](https://github.com/openai/codex/tree/main/codex-rs/protocol). They are not a compatibility promise for every historical or future transcript version.

## Outcome and privacy rules

Tool outcome comes only from explicit `is_error`/`status` fields. AgentShare does not infer success from an output body that it has discarded. Many Codex output records consequently have an unknown/informational outcome.

Source filenames, session IDs, model metadata and absolute timestamps are excluded from the review bundle. Message text can still describe these things; replacement rules and manual review apply to text. Home-path replacement errs toward removing the remainder of an unquoted line, which may remove useful context as well. Custom literal terms are case-sensitive.

The omitted-body counter counts each tool-input or tool-output summary, not unique calls. The review page includes candidate text after replacements; only selected edited events enter a newly exported document.
