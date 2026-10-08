# Contributing to AgentShare

Small, reproducible contributions are welcome: synthetic transcript fixtures, adapter fixes, redaction regression tests, and accessibility improvements.

## Report a problem

Include your operating system, Python version, the command you ran, expected behavior, and actual behavior. Replace filenames and other identifiers with invented values. If a transcript shape causes the problem, provide the smallest **synthetic** JSONL fixture that reproduces it.

Do not upload real private conversations, API keys, source code from private projects, screenshots containing sensitive text, or private term lists. Use deliberately fake strings when testing credential rules. Check terminal output before posting it.

## Submit a change

1. Explain the concrete behavior the change fixes.
2. Add a focused regression test when changing parsing, redaction, or export behavior. For new formats, include a small synthetic fixture and document which fields are supported or omitted.
3. Run `python -m unittest discover -s tests -v` from the repository root.
4. Update the relevant documentation, including [README.md](README.md) and [README.zh-CN.md](README.zh-CN.md) when user-facing behavior changes.

Keep processing local. The project uses the Python standard library and standalone HTML/JavaScript; changes should retain that scope unless a different design is discussed first. Redaction improvements should describe what they detect and what they miss, without claiming complete confidentiality.

## 中文说明

欢迎提交合成 JSONL 样例、格式适配修复、脱敏回归测试和可访问性改进。问题报告请包含操作系统、Python 版本、执行命令、预期行为与实际行为，用最小的虚构样例复现。

请勿上传真实私密会话、密钥、内部项目代码、含敏感文字的截图或私人词表。测试敏感字符串时使用明确的假值，分享终端输出前也请检查内容。修改用户可见行为时，请同步中英文 README，并运行上面的测试命令。不要宣称任何规则能保证删除全部敏感信息。
