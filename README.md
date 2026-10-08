# AgentShare

[English](README.md) | [简体中文](README.zh-CN.md)

**Share the useful part of an AI coding session. Review what leaves your machine.**

You want to show a teammate a failed test and the explanation that fixed it. Your Claude Code or Codex transcript also contains credentials, local paths, and a long tool output. AgentShare builds a local review page: edit the remaining text, select the relevant messages, then export a focused HTML or Markdown file.

**[Try the interactive demo →](https://fuxing0910-hue.github.io/agentshare/demo.html)** · [Project site](https://fuxing0910-hue.github.io/agentshare/) · [Releases](https://github.com/fuxing0910-hue/agentshare/releases)

[How to redact and selectively export a Claude Code/Codex transcript](https://fuxing0910-hue.github.io/agentshare/claude-code-transcript-review.html) — offline JSONL review, editable messages, HTML/Markdown export, and agent installation.

The demo is entirely synthetic. It opens the complete review interface, with nothing selected.

- **Choose what to share.** Nothing is selected by default; exports contain only selected, edited messages.
- **Reduce noisy context.** Tool arguments and output bodies are omitted; visible rules replace common credential, email, and home-path patterns.
- **Keep processing local.** Python standard library, standalone review page, no model API or third-party runtime dependencies.

**Review before sharing:** rules cannot find every secret. Keep the initial candidate review private and inspect your final selection.

![AgentShare review workspace: transformation counts, editable messages, and selected-only export](docs/images/demo-preview.jpg)

## Run it locally

Requires Python 3.10+.

```sh
git clone https://github.com/fuxing0910-hue/agentshare.git
cd agentshare
python -m agentshare demo --output demo-review.html
```

Open `demo-review.html`, choose messages, edit their text, and download HTML or Markdown. To process your own explicitly selected file:

```sh
python -m agentshare build session.jsonl --format codex --output review.html
python -m agentshare build session.jsonl --term-file private-terms.txt --output review.html
```

`--format` accepts `auto`, `claude`, or `codex`; the default is `auto`. A private term file lists one literal phrase per line. Install with `python -m pip install .` to use the `agentshare` command.

## Let a coding agent use it

Ask a compatible agent:

> Turn this Codex JSONL into shareable review material. Remove common credential patterns and tool output, then leave the candidate page for my manual review.

There are four entry points:

- **CLI:** `python -m agentshare build …` for local file-to-review tasks.
- **Python API:** `build_bundle()` plus `render_review()` for integrations.
- **Function tools:** declaration exports for GPT, DeepSeek, Claude and Gemini API applications, with one validated local dispatcher.
- **Installable skill:** [share-ai-transcripts](skills/share-ai-transcripts/SKILL.md), task instructions that help an agent match a natural-language request to the local workflow.

Install the skill directly from this repository:

```sh
npx skills add fuxing0910-hue/agentshare --skill share-ai-transcripts
```

The Skills CLI discovers and installs instructions from the specified repository. Node.js is needed only for that optional installer; the skill's commands run on Python 3.10+. This direct-install command does not depend on a directory listing or ranking.

For executable routing, supported inputs, and installation choices, see [the agent integration guide](docs/agents.md). A Python integration can build the same review:

```python
from pathlib import Path
from agentshare import build_bundle
from agentshare.report import render_review

bundle = build_bundle("session.jsonl", format="codex", terms=["internal-project"])
Path("review.html").write_text(render_review(bundle), encoding="utf-8")
```

The AI-assisted workflow prepares review material. Message selection, final inspection, and sharing remain deliberate steps.

## Support and boundaries

The adapters support documented Claude Code and Codex JSONL shapes. Unknown records are counted; upstream formats can change. Automatic replacements miss contextual secrets and proprietary text. The initial review contains all candidates and is different from a selected export.

[Complete technical reference](docs/reference.md) · [Supported transcript formats](docs/formats.md) · [Contributing](CONTRIBUTING.md) · [MIT License](LICENSE)

```sh
python -m unittest discover -s tests -v
```

Developed with AI assistance. Original implementation; see the reference for project context and detailed limitations.
