# Agent integration / AI 接入

AgentShare prepares a **private, local review page from one explicitly supplied Claude Code or Codex JSONL file**. A person edits and selects messages before exporting. It does not upload transcripts or decide what is safe to publish.

AgentShare 将明确指定的一份 Claude Code / Codex JSONL 转成本地候选审阅页。人工编辑、选择消息后再导出；工具不会上传会话或自动分享。

For a complete task example and runnable install path, see [the bilingual transcript review guide](https://fuxing0910-hue.github.io/agentshare/claude-code-transcript-review.html).

## Choose an entry point

| Environment | Entry point | What must happen first |
| --- | --- | --- |
| Person reviewing a local transcript | [Zero-install browser tool](https://fuxing0910-hue.github.io/agentshare/try.html) | Choose the JSONL file; manually review and select messages before export. |
| Coding agent supporting Agent Skills | `share-ai-transcripts` skill | Install the skill into that agent's configured skill location. |
| Agent with a shell or Python runtime | Existing CLI or Python API | Install the package, or use a repository checkout. |
| GPT, DeepSeek, Claude or Gemini API application | Function declarations + local dispatcher | The application registers the declarations and executes requested calls. |
| Ordinary chat page | Its supported integrations | The host application must expose a suitable tool. A GitHub URL alone does not add one. |

模型和应用是两层：DeepSeek 模型也可以运行在支持 Skill 的编程代理里；普通聊天页面是否能调用文件工具，取决于该应用开放的接入方式。

The browser tool is a manual local-file entry point, not a tool automatically registered with a model. It starts with zero messages selected and accepts up to 20 MiB UTF-8 JSONL, 100,000 Unicode code points per visible message, and 5,000 candidates. Use the Python CLI for more candidates. Pattern replacements still require manual review.

浏览器入口无需安装、不上传文件，适合人工审阅；它不会自动注册成聊天模型的工具。初始选择 0 条消息，更多候选可使用下方 Python 流程，分享前仍需人工检查。

## Install the portable skill

From a project where you want the agent to use the tool:

```sh
npx skills add fuxing0910-hue/agentshare --skill share-ai-transcripts
```

The optional installer needs Node.js. The installed skill bundles its Python source and HTML template, so its runner needs only Python 3.10+, without pip, a repository checkout or a model API key. It does not scan real session directories.

查看 [Skills CLI](https://github.com/vercel-labs/skills) 支持的代理，使用 `--agent` 指定安装对象；不加 `-g` 时在当前项目安装。也可以下载完整的 `skills/share-ai-transcripts` 文件夹，保留其中的脚本和模板，放入应用支持的 Skill 目录。

Example request after installation:

> Prepare this Codex JSONL for sharing in a GitHub issue. Omit tool bodies and common credential patterns, create a local review page, and leave message selection and final review to me.

> 把我指定的 Codex JSONL 整理成 issue 分享材料，去掉工具正文并替换常见敏感模式，生成本地审阅页，由我手动选择和检查。

Read the installed [SKILL.md](../skills/share-ai-transcripts/SKILL.md) for the exact runner commands and boundaries.

## Register function tools in an API application

Install with `python -m pip install .`, then export declarations for the API you use:

```sh
python -m agentshare.agent_tools --list --provider openai
python -m agentshare.agent_tools --list --provider deepseek
python -m agentshare.agent_tools --list --provider claude
python -m agentshare.agent_tools --list --provider gemini
```

| Provider argument | Declaration format | Official contract |
| --- | --- | --- |
| `openai` | Responses API function tools, strict schema | [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling) |
| `deepseek` | Chat Completions `tools[].function` | [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) |
| `claude` | Messages tool definitions with `input_schema` | [Claude tool definitions](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools) |
| `gemini` | Interactions API function tools | [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling) |

`gemini` targets the **Interactions API**, not the different legacy `generateContent` envelope. `deepseek` does not enable beta strict mode. The application supplies the API client, credentials, model choice and tool-result message format.

Tool name: `prepare_transcript_review`. All four arguments are required; use `null` when no private term file is needed:

```json
{
  "name": "prepare_transcript_review",
  "arguments": {
    "transcript_path": "examples/demo-codex.jsonl",
    "output_html_path": "work/review.html",
    "format": "codex",
    "private_terms_path": null
  }
}
```

Save this as `request.json`, then dispatch it locally:

```sh
python -m agentshare.agent_tools --request request.json
```

Or register and dispatch inside your application:

```python
from agentshare.agent_tools import tool_definitions, call_tool

tools = tool_definitions("claude")  # Supply these to your API client's tools field.
result = call_tool("prepare_transcript_review", {
    "transcript_path": "examples/demo-codex.jsonl",
    "output_html_path": "work/review.html",
    "format": "codex",
    "private_terms_path": None,
})
```

The dispatcher validates the tool name and arguments, reuses input/output alias protection, and returns review metadata rather than transcript text. Success starts with zero selected messages and requires manual review. CLI errors exit 2 and return a safe JSON error. The dispatcher does not contact any model service.

将声明放进 API 请求的 `tools` 列表后，模型才有机会选择调用。应用接收到函数名称和参数后，在本地执行 `call_tool()`，再按该 API 的格式提交工具结果。不要把模型生成的函数名当作任意 shell 命令执行。

## Discovery and verification

The skill's task description and function descriptions state when to use the tool, its explicit inputs, outputs and limits. Public documentation also has a [plain-text index](https://fuxing0910-hue.github.io/agentshare/llms.txt). These make integration and retrieval easier; they do not create a global model tool registration or guarantee selection, search ranking or directory inclusion.

自动选择依赖任务相关性、工具已安装或已注册、运行权限和应用策略。仅发布仓库不会让所有 GPT、DeepSeek、Claude 或 Gemini 用户自动拥有这个工具。

Tests cover declaration formats, local dispatch, invalid arguments and protected input files. They are local contract and execution tests; no paid inference was used to measure selection rates. To check the standalone skill bundle:

```sh
python scripts/sync_skill.py --check
python scripts/smoke_skill.py --work-dir work/skill-smoke
```

[CLI and technical reference](reference.md) · [中文技术参考](reference.zh-CN.md)
