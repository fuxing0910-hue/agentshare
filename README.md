# AgentShare

**Share the useful part of an AI coding session. Review what leaves your machine.**

AgentShare turns a local Claude Code or Codex JSONL transcript into an offline review page. It removes tool arguments and output bodies, applies visible redaction rules, and lets you edit and select messages before exporting a small HTML or Markdown evidence packet.

No account, model API, server, or runtime dependencies. Processing stays on your computer.

## Try the synthetic demo

```sh
git clone https://github.com/fuxing0910-hue/agentshare.git
cd agentshare
python -m agentshare demo --output demo-review.html
```

Open `demo-review.html` in a browser. Select a few events, edit their text, and export Markdown or HTML. The demo uses invented conversation data and deliberately fake secret strings; it is not a real user's transcript.

Python 3.10 or newer is required. You can also install the CLI with `python -m pip install .` and use `agentshare` instead of `python -m agentshare`.

## Review your own transcript

```sh
python -m agentshare build session.jsonl --output review.html
python -m agentshare build session.jsonl --format codex --output review.html
python -m agentshare build session.jsonl --term-file private-terms.txt --output review.html
```

The term file contains one literal phrase per line, such as a company name or internal identifier. Keep it private. The CLI reads only the input you specify; it does not search your session folders, run recorded commands, or upload anything.

The review page starts with **nothing selected**. Read the candidate messages, edit anything the rules missed, then choose the evidence to share. The exported document contains only selected, edited events. Excluded messages and the original transcript are not embedded in the exported file.

## What is preserved

| Input | Review output |
| --- | --- |
| User and assistant text | Text after rule-based replacements; editable before export |
| Tool calls and results | Tool labels and status only |
| Tool arguments and output bodies | Omitted |
| Session metadata and unknown records | Excluded; unsupported records counted |
| Original source transcript | Never attached to generated output |

Common credential formats, secret assignments, email addresses, home-directory paths, and your custom literal terms have dedicated replacement rules. Counts show what the rules changed. Text is rendered as text, so transcript HTML and code do not execute in the review page.

## Limits that matter

Redaction rules do not understand every secret, proprietary passage, or personal detail. **Review the final selection before sharing.** The initial review page contains candidate messages and should be kept private. Automatic replacements are an aid to review, not a guarantee that a document is safe to disclose.

The adapters support the documented shapes in [formats.md](docs/formats.md); upstream transcript formats can change. This is a transcript evidence exporter, not a command execution replay system. Unsupported events are reported rather than presented as a complete reconstruction.

## Development

```sh
python -m unittest discover -s tests -v
```

Tests cover redaction, malformed input, event normalization, omitted tool bodies, and safe HTML serialization. The implementation uses the Python standard library and standalone HTML/JavaScript.

## 中文快速开始

这个工具把 AI 编程会话整理成可审阅的分享材料。先在本地替换常见敏感信息，省略工具参数与完整输出，再逐条选择、编辑，导出独立 HTML 或 Markdown。无需 API Key。

先运行上面的 `demo` 命令体验，再用 `build` 处理自己明确指定的 JSONL 文件。自动规则无法识别所有敏感内容，分享前请检查最终选中的文字。演示数据全部为虚构。

## Context and contribution

The product focuses on a concrete [request for local transcript redaction and review](https://github.com/anthropics/claude-code/issues/57772). Existing projects such as [claude-code-transcripts](https://github.com/simonw/claude-code-transcripts) provide broader transcript publishing workflows. AgentShare is an original, smaller implementation focused on selective evidence export; it does not contain their code.

Useful contributions include small synthetic format fixtures, regression tests for replacement rules, and accessibility improvements. Please avoid posting real transcripts, keys, or private term lists in issues.

MIT licensed.
