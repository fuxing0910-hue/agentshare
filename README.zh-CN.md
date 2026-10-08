# AgentShare

[English](README.md) | [简体中文](README.zh-CN.md)

**把 AI 编程会话里的有用片段整理成分享材料。先检查，再导出。**

[![测试](https://github.com/fuxing0910-hue/agentshare/actions/workflows/test.yml/badge.svg)](https://github.com/fuxing0910-hue/agentshare/actions/workflows/test.yml)

[中文项目页](https://fuxing0910-hue.github.io/agentshare/zh.html) · [纯合成交互演示](https://fuxing0910-hue.github.io/agentshare/demo.html) · [下载独立演示文件](https://github.com/fuxing0910-hue/agentshare/releases/download/v0.1.0/agentshare-demo.html) · [版本发布](https://github.com/fuxing0910-hue/agentshare/releases)

AgentShare 将本地 Claude Code 或 Codex 的 JSONL 会话文件转换成离线审阅页面。它省略工具参数和输出正文，用明确的规则替换部分敏感文字，让你逐条编辑、选择后，再导出独立的 HTML 或 Markdown 分享材料。

无需账号、模型 API、后端服务或额外运行时依赖。处理在你的电脑上完成。

## 先体验合成演示

直接打开[纯合成交互演示](https://fuxing0910-hue.github.io/agentshare/demo.html)，或在本地生成演示页面：

```sh
git clone https://github.com/fuxing0910-hue/agentshare.git
cd agentshare
python -m agentshare demo --output demo-review.html
```

用浏览器打开 `demo-review.html`，选择几条事件，编辑文字，然后导出 Markdown 或 HTML。演示对话和敏感字符串均为虚构，没有使用真实用户会话。

需要 **Python 3.10 或更高版本**。也可以在仓库目录运行 `python -m pip install .` 安装 CLI，随后将命令中的 `python -m agentshare` 换成 `agentshare`。

## 审阅自己的会话文件

```sh
python -m agentshare build session.jsonl --output review.html
python -m agentshare build session.jsonl --format codex --output review.html
python -m agentshare build session.jsonl --term-file private-terms.txt --output review.html
```

`--format` 支持 `auto`、`claude` 和 `codex`，默认自动识别。CLI 只读取你明确指定的输入文件，不搜索会话目录、不执行记录中的命令，也不上传内容。

`--term-file` 接受 UTF-8 文本词表，每行一个需要替换的字面词句，例如公司名称、内部项目名或标识符。词表区分大小写，忽略空行，去除词句首尾空白；较长词句优先匹配。请将词表保存在私人位置，不要提交到仓库或 issue。

审阅页面最初**没有选中任何事件**。先读候选文字，修改规则遗漏的内容，再选择确实需要分享的片段。新导出的文件只包含选中并编辑后的事件，不内嵌未选中的候选消息或原始 JSONL 文件。

## 保留与省略哪些内容

| 输入内容 | 审阅页面中的内容 |
| --- | --- |
| 用户与助手的正文 | 经过规则替换的文字，可在导出前编辑 |
| 工具调用与结果 | 工具标签及明确记录的状态 |
| 工具参数、输入与输出正文 | 省略 |
| 会话元数据与不支持的记录 | 排除；不支持的记录计数可见 |
| 原始 JSONL 文件 | 不作为附件加入生成的文件 |

替换规则覆盖部分常见凭据格式、秘密赋值、邮箱地址、home 目录路径，以及自定义字面词句。统计信息显示各类规则的替换次数。消息按纯文本显示，会话中的 HTML 和代码不会作为网页内容执行。

未知工具名称只显示为 `Other tool`。工具状态仅来自明确的 `is_error` 或 `status` 字段，不根据已省略的输出正文推断成功或失败；很多 Codex 工具结果因此显示为信息状态。

## 支持的格式与边界

输入是单个 UTF-8 JSONL 文件，可带 UTF-8 BOM，最大 **20 MiB**。每个非空行必须是一个 JSON 对象。JSON 格式错误会报告行号并终止，不生成部分成功的报告。用户或助手消息的可见正文超过 **100,000 个字符**时会被拒绝。

当前适配器支持：

- **Claude Code**：顶层 `user`、`assistant` 记录的 `message.content` 字符串，或其中的 `text`、`tool_use`、`tool_result` 块。
- **Codex**：`response_item` 中的用户/助手 `message` 及 `input_text`、`output_text` 块；`function_call`、`custom_tool_call` 与对应的输出记录。
- **Codex 文本回退**：`event_msg` 中的 `user_message`、`agent_message`。与标准消息匹配的回退记录按出现次数去重，保留实际重复的消息。

推理文字、图片、会话元数据、turn context 及其他未支持记录不会导出。`unsupported_records` 统计没有识别到事件的记录，不等于所有未知嵌套块的总数；省略正文的计数按工具输入/输出摘要计数，不按唯一工具调用计数。

详细结构见 [formats.md](docs/formats.md)。上游日志格式可能变化，本项目不承诺支持全部历史和未来版本。导出材料是会话片段，不是命令执行重放，也不是完整行为还原。

## 分享前仍需人工检查

自动规则无法理解所有秘密、专有内容或个人信息。**分享前，请检查最终选中的文字。** 初始审阅页面仍包含候选消息，应保留在私人位置；它和最终导出的精选材料是两个不同文件。

来源文件名、会话 ID、模型元数据及绝对时间不会作为元数据字段进入审阅包，但这些信息仍可能出现在用户或助手正文里。公司名称、业务代码、上下文透露的信息等也可能保留下来，需要你编辑或排除。

home 路径规则偏向多省略：遇到没有引号包围的路径，可能连同该行后面的有用文字一起替换。请检查替换后的上下文。替换次数只能说明规则做了哪些处理，不能证明文件已经适合公开。

## 开发与贡献

在仓库目录运行：

```sh
python -m unittest discover -s tests -v
```

测试覆盖敏感词替换、异常输入、事件归一化、工具正文省略、输入文件保护和 HTML 序列化。实现使用 Python 标准库以及独立 HTML/JavaScript。

欢迎提供小型合成格式样例、替换规则回归测试和可访问性改进。报告问题时请说明 Python 版本、操作系统、命令和预期行为，并使用虚构内容复现。完整要求见 [CONTRIBUTING.md](CONTRIBUTING.md)。**请勿上传真实私密会话、密钥或私人词表。**

## 项目背景

项目关注一个具体的[本地会话脱敏与审阅需求](https://github.com/anthropics/claude-code/issues/57772)。已有 [claude-code-transcripts](https://github.com/simonw/claude-code-transcripts) 等工具提供更广泛的会话发布流程；AgentShare 是围绕精选证据导出编写的较小实现，没有包含这些项目的代码。

本项目在 AI 辅助下开发，采用 [MIT 许可证](LICENSE)。
