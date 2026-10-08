---
name: share-ai-transcripts
description: "Prepare a local, redacted review of a user-specified Claude Code or Codex JSONL transcript for selective HTML/Markdown sharing. 将指定 AI 编程会话脱敏、审阅并精选导出；不自动扫描或上传。"
---

# Share AI Transcripts

Create a local AgentShare review page from one explicitly specified transcript. The skill includes its runtime source and template; it needs Python 3.10+ and does not require pip, a repository checkout, network access, an account, or an API key.

Use the actual installed skill directory and an available Python 3.10+ executable in these commands:

```sh
python "<skill-dir>/scripts/run.py" demo --output "<output-dir>/demo-review.html"
python "<skill-dir>/scripts/run.py" build "<input-file>.jsonl" --output "<output-dir>/review.html"
```

`build` accepts `--format auto|claude|codex` (default `auto`) and `--term-file <UTF-8-file>`. A term file contains one additional literal phrase per line; terms are case-sensitive. Use user-supplied terms, keep the file private, and do not print its contents.

Input must be UTF-8 JSONL, at most 20 MiB; visible messages exceeding 100,000 characters are rejected. Only supported Claude Code/Codex record shapes are retained.

Read only the transcript the user identifies. If an actual transcript is requested without a file path or attachment, obtain that input before building; do not scan session folders to find one. Run `demo` only for a synthetic demonstration. Choose a distinct output file; do not overwrite input or term files. Do not install dependencies or contact a service for this workflow.

The generated review omits tool inputs/output bodies and metadata, applies best-effort text replacements, and initially selects no events. Open the HTML in a browser or provide its local path. Selecting and editing events is a browser review step; the user must inspect the final selection before exporting HTML or Markdown. A generated review is not already a selected-only export.

Keep the candidate review private. Only the selected, edited events enter a newly exported file. Never claim that the AI or replacement rules can identify every secret or determine that material is safe to disclose. Unsupported transcript records are omitted; this is not command replay. Errors stop the build rather than silently producing a partial report.

This skill creates local files. Uploading, publishing, or sending them requires a separate explicit user request. Report the output path, supported source format, and the need for human review without repeating sensitive transcript text.

Bundled AgentShare source is MIT licensed; see `scripts/LICENSE`.
