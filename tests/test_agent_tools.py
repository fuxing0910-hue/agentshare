from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agentshare.agent_tools import TOOL_NAME, ToolError, call_tool, main, tool_definitions


class ToolDefinitionTests(unittest.TestCase):
    def test_four_official_provider_shapes_and_strict_parameters(self):
        for provider in ("openai", "deepseek", "claude", "gemini"):
            with self.subTest(provider=provider):
                tools = tool_definitions(provider)
                self.assertEqual(len(tools), 1)
                outer = tools[0]
                definition = outer["function"] if provider == "deepseek" else outer
                if provider == "deepseek":
                    self.assertEqual(set(outer), {"type", "function"})
                    self.assertEqual(outer["type"], "function")
                elif provider == "claude":
                    self.assertEqual(set(outer), {"name", "description", "input_schema"})
                else:
                    expected = {"type", "name", "description", "parameters"}
                    if provider == "openai":
                        expected.add("strict")
                        self.assertIs(outer["strict"], True)
                    self.assertEqual(set(outer), expected)
                    self.assertEqual(outer["type"], "function")
                self.assertEqual(definition["name"], TOOL_NAME)
                schema = definition["input_schema" if provider == "claude" else "parameters"]
                self.assertEqual(schema["type"], "object")
                self.assertIs(schema["additionalProperties"], False)
                self.assertEqual(set(schema["required"]), set(schema["properties"]))
                self.assertEqual(set(schema["required"]), {"transcript_path", "output_html_path", "format", "private_terms_path"})
                self.assertEqual(schema["properties"]["format"]["enum"], ["auto", "claude", "codex"])
                self.assertEqual(schema["properties"]["private_terms_path"]["type"], ["string", "null"])

    def test_definitions_are_fresh_and_unknown_provider_fails(self):
        tools = tool_definitions("openai")
        tools[0]["parameters"]["properties"].clear()
        self.assertEqual(len(tool_definitions("openai")[0]["parameters"]["properties"]), 4)
        with self.assertRaisesRegex(ToolError, "Unsupported provider"):
            tool_definitions("PRIVATE_UNKNOWN_PROVIDER")


class ToolExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.source = self.folder / "synthetic.jsonl"
        self.output = self.folder / "review.html"
        records = [
            {"type": "system", "sessionId": "RAW_PRIVATE_METADATA"},
            {"type": "user", "message": {"content": "Synthetic text for Acme Internal. fake@example.test ghp_FAKE_API_TOKEN_ONLY"}},
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "private-call", "name": "Bash", "input": {"command": "RAW_TOOL_INPUT_ONLY"}}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "private-call", "is_error": True, "content": "RAW_TOOL_BODY_ONLY"}]}},
        ]
        self.source.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    def arguments(self, **changes):
        values = {"transcript_path": str(self.source), "output_html_path": str(self.output), "format": "auto", "private_terms_path": None}
        values.update(changes)
        return values

    def test_real_synthetic_build_returns_metadata_only(self):
        terms = self.folder / "private-terms.txt"
        terms.write_text("Acme Internal\n", encoding="utf-8")
        original = self.source.read_bytes()
        captured = io.StringIO()
        with redirect_stdout(captured), redirect_stderr(captured):
            result = call_tool(TOOL_NAME, self.arguments(private_terms_path=str(terms)))
        self.assertEqual(result, {"review_path": str(self.output.resolve()), "manual_review_required": True, "selected_count": 0})
        self.assertEqual(captured.getvalue(), "")
        html = self.output.read_text(encoding="utf-8")
        for marker in ("RAW_PRIVATE_METADATA", "RAW_TOOL_INPUT_ONLY", "RAW_TOOL_BODY_ONLY", "fake@example.test", "FAKE_API_TOKEN_ONLY", "Acme Internal"):
            self.assertNotIn(marker, html)
            self.assertNotIn(marker, json.dumps(result))
        self.assertIn("Synthetic text", html)
        self.assertEqual(self.source.read_bytes(), original)

    def test_codex_synthetic_build(self):
        record = {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Synthetic Codex message"}]}}
        self.source.write_text(json.dumps(record), encoding="utf-8")
        result = call_tool(TOOL_NAME, self.arguments(format="codex"))
        self.assertEqual(result["selected_count"], 0)
        self.assertIn('"source_format":"codex"', self.output.read_text(encoding="utf-8"))

    def test_invalid_names_types_missing_and_unknown_arguments(self):
        bad_values = [None, [], "PRIVATE_ARGUMENT_TEXT", {}, self.arguments(extra="PRIVATE_EXTRA_VALUE")]
        for field in ("transcript_path", "output_html_path", "format", "private_terms_path"):
            values = self.arguments()
            del values[field]
            bad_values.append(values)
        for field, value in (("transcript_path", True), ("transcript_path", " "), ("output_html_path", 7), ("format", "PRIVATE_FORMAT"), ("format", []), ("private_terms_path", False), ("private_terms_path", "")):
            bad_values.append(self.arguments(**{field: value}))
        with self.assertRaises(ToolError):
            call_tool("PRIVATE_BAD_TOOL_NAME", self.arguments())
        for arguments in bad_values:
            with self.subTest(arguments=arguments), self.assertRaises(ToolError) as caught:
                call_tool(TOOL_NAME, arguments)
            self.assertNotIn("PRIVATE_", str(caught.exception))
        self.assertFalse(self.output.exists())

    def test_input_output_same_path_preserves_source(self):
        original = self.source.read_bytes()
        with self.assertRaises(ToolError):
            call_tool(TOOL_NAME, self.arguments(output_html_path=str(self.source)))
        self.assertEqual(self.source.read_bytes(), original)

    def test_output_term_alias_preserves_terms(self):
        terms = self.folder / "private-terms.txt"
        original = b"PRIVATE_TERM_VALUE\n"
        terms.write_bytes(original)
        with self.assertRaises(ToolError) as caught:
            call_tool(TOOL_NAME, self.arguments(output_html_path=str(terms), private_terms_path=str(terms)))
        self.assertNotIn("PRIVATE_TERM_VALUE", str(caught.exception))
        self.assertEqual(terms.read_bytes(), original)

    def test_input_hardlink_alias_is_protected(self):
        try:
            os.link(self.source, self.output)
        except (OSError, NotImplementedError):
            self.skipTest("Hardlinks unavailable.")
        original = self.source.read_bytes()
        with self.assertRaises(ToolError):
            call_tool(TOOL_NAME, self.arguments())
        self.assertEqual(self.source.read_bytes(), original)

    def test_cli_output_and_exception_contents_are_discarded(self):
        def noisy_cli(arguments):
            print("RAW_PRIVATE_STDOUT")
            import sys
            print("RAW_PRIVATE_STDERR", file=sys.stderr)
            raise RuntimeError("RAW_PRIVATE_EXCEPTION")
        captured = io.StringIO()
        with patch("agentshare.agent_tools.cli_main", side_effect=noisy_cli), redirect_stdout(captured), redirect_stderr(captured):
            with self.assertRaises(ToolError) as caught:
                call_tool(TOOL_NAME, self.arguments())
        self.assertEqual(captured.getvalue(), "")
        self.assertNotIn("RAW_PRIVATE", str(caught.exception))


class ToolCliTests(unittest.TestCase):
    def invoke(self, arguments):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(arguments)
        self.assertEqual(errors.getvalue(), "")
        return code, json.loads(output.getvalue())

    def test_list_all_providers_as_json(self):
        for provider in ("openai", "deepseek", "claude", "gemini"):
            code, data = self.invoke(["--list", "--provider", provider])
            self.assertEqual(code, 0)
            self.assertEqual(data, tool_definitions(provider))

    def test_request_build_json_result(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, output, request = root / "source.jsonl", root / "review.html", root / "request.json"
            source.write_text(json.dumps({"type": "user", "message": {"content": "Synthetic request message"}}), encoding="utf-8")
            request.write_text(json.dumps({"name": TOOL_NAME, "arguments": {"transcript_path": str(source), "output_html_path": str(output), "format": "auto", "private_terms_path": None}}), encoding="utf-8")
            code, data = self.invoke(["--request", str(request)])
            self.assertEqual(code, 0)
            self.assertEqual(set(data), {"review_path", "manual_review_required", "selected_count"})
            self.assertEqual(data["selected_count"], 0)
            self.assertTrue(output.exists())
            self.assertNotIn("Synthetic request message", json.dumps(data))

    def test_cli_errors_are_safe_json_with_exit_two(self):
        for arguments in ([], ["--list", "--provider", "PRIVATE_PROVIDER"], ["--PRIVATE_UNKNOWN_OPTION"], ["--request", "PRIVATE_MISSING_REQUEST_FILE"]):
            with self.subTest(arguments=arguments):
                code, data = self.invoke(arguments)
                self.assertEqual(code, 2)
                self.assertEqual(set(data), {"error"})
                self.assertNotIn("PRIVATE_", json.dumps(data))

    def test_failed_transcript_build_returns_only_safe_json(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, output, request = root / "source.jsonl", root / "review.html", root / "request.json"
            source.write_text('{PRIVATE_TRANSCRIPT_CONTENT', encoding="utf-8")
            request.write_text(json.dumps({"name": TOOL_NAME, "arguments": {"transcript_path": str(source), "output_html_path": str(output), "format": "auto", "private_terms_path": None}}), encoding="utf-8")
            code, data = self.invoke(["--request", str(request)])
            self.assertEqual(code, 2)
            self.assertEqual(set(data), {"error"})
            self.assertNotIn("PRIVATE_TRANSCRIPT_CONTENT", json.dumps(data))
            self.assertNotIn(str(source), json.dumps(data))
            self.assertFalse(output.exists())

    def test_malformed_or_ambiguous_requests_do_not_echo_content(self):
        cases = ('{PRIVATE_REQUEST_SECRET', '[]', '{"name":"PRIVATE_TOOL"}', '{"name":"PRIVATE_TOOL","name":"PRIVATE_DUPLICATE","arguments":{}}', '{"name":"PRIVATE_TOOL","arguments":NaN}')
        with tempfile.TemporaryDirectory() as folder:
            request = Path(folder) / "request.json"
            for value in cases:
                with self.subTest(value=value):
                    request.write_text(value, encoding="utf-8")
                    code, data = self.invoke(["--request", str(request)])
                    self.assertEqual(code, 2)
                    self.assertNotIn("PRIVATE_", json.dumps(data))


if __name__ == "__main__":
    unittest.main()
