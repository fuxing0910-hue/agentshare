import json
import io
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agentshare.core import InputError, build_bundle, demo_bundle
from agentshare.redact import Redactor
from agentshare.__main__ import main


class BundleTests(unittest.TestCase):
    def bundle(self, records, format="auto", terms=()):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "PRIVATE_SOURCE_FILENAME.jsonl"
            source.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
            return build_bundle(source, format, terms)

    def test_claude_security_boundary(self):
        records = [
            {"type": "system", "sessionId": "PRIVATE_SESSION_ID", "cwd": "PRIVATE_CWD"},
            {"type": "assistant", "timestamp": "PRIVATE_TIMESTAMP", "message": {"model": "PRIVATE_MODEL", "content": [
                {"type": "text", "text": "Visible message."},
                {"type": "tool_use", "id": "PRIVATE_TOOL_ID", "name": "PRIVATE_TOOL_NAME", "input": {"command": "PRIVATE_TOOL_INPUT"}},
                {"type": "thinking", "thinking": "PRIVATE_REASONING"},
            ]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "PRIVATE_TOOL_ID", "content": [{"type": "text", "text": "PRIVATE_TOOL_OUTPUT"}], "is_error": True},
                {"type": "image", "source": {"data": "PRIVATE_IMAGE"}},
            ]}},
        ]
        result = self.bundle(records)
        serialized = json.dumps(result)
        for marker in ("PRIVATE_SOURCE_FILENAME", "PRIVATE_SESSION_ID", "PRIVATE_CWD", "PRIVATE_TIMESTAMP", "PRIVATE_MODEL", "PRIVATE_TOOL_ID", "PRIVATE_TOOL_NAME", "PRIVATE_TOOL_INPUT", "PRIVATE_TOOL_OUTPUT", "PRIVATE_REASONING", "PRIVATE_IMAGE"):
            self.assertNotIn(marker, serialized)
        self.assertEqual(result["source_format"], "claude")
        self.assertEqual(result["events"][1]["label"], "Other tool")
        self.assertEqual(result["events"][2]["status"], "error")
        self.assertEqual(result["stats"]["omitted_tool_bodies"], 2)
        self.assertEqual(result["stats"]["unsupported_records"], 1)

    def test_codex_canonical_and_fallback_occurrence_dedup(self):
        records = [
            {"type": "event_msg", "payload": {"type": "user_message", "message": "yes"}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "yes"}]}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": "yes"}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "yes"}]}},
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "fallback only"}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "complete"}]}},
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "complete"}},
        ]
        result = self.bundle(records)
        self.assertEqual([event["text"] for event in result["events"]], ["yes", "yes", "fallback only", "complete"])

    def test_codex_tools_and_nonmessage_metadata_are_excluded(self):
        records = [
            {"type": "session_meta", "payload": {"id": "PRIVATE_SESSION", "cwd": "PRIVATE_CWD"}},
            {"type": "response_item", "payload": {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "PRIVATE_INSTRUCTIONS"}]}},
            {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "call_id": "PRIVATE_CALL", "arguments": "PRIVATE_ARGUMENTS", "namespace": "PRIVATE_NAMESPACE"}},
            {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "PRIVATE_CALL", "output": "PRIVATE_OUTPUT", "status": "failed"}},
            {"type": "response_item", "payload": {"type": "reasoning", "summary": [{"text": "PRIVATE_REASONING"}]}},
            {"type": "event_msg", "payload": {"type": "agent_reasoning", "text": "PRIVATE_REASONING2"}},
        ]
        result = self.bundle(records)
        self.assertNotIn("PRIVATE_", json.dumps(result))
        self.assertEqual(len(result["events"]), 2)
        self.assertEqual(result["events"][1]["label"], "exec_command")
        self.assertEqual(result["events"][1]["status"], "error")
        self.assertEqual(result["stats"]["unsupported_records"], 4)

    def test_result_body_does_not_infer_outcome(self):
        result = self.bundle([{"type": "response_item", "payload": {"type": "function_call_output", "call_id": "c", "output": "Error: exit_code=1; secret body"}}])
        self.assertEqual(result["events"][0]["status"], "info")
        self.assertNotIn("exit_code", json.dumps(result))

    def test_custom_terms_apply_to_labels_and_text(self):
        result = self.bundle([{"type": "assistant", "message": {"content": [{"type": "text", "text": "Acme Corporation at Acme"}, {"type": "tool_use", "name": "Bash", "input": "omit"}]}}], terms=("Acme", "Acme Corporation", "Bash", " "))
        self.assertNotIn("Acme", json.dumps(result))
        self.assertNotIn("Corporation", json.dumps(result))
        self.assertNotIn("Bash", result["events"][1]["label"])
        self.assertEqual(result["stats"]["redactions"]["custom"], 3)

    def test_malformed_line_fails_without_partial_bundle_or_raw_snippet(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.jsonl"
            source.write_text('{"type":"user","message":{"content":"valid"}}\n{SECRET_BROKEN_CONTENT', encoding="utf-8")
            with self.assertRaisesRegex(InputError, "Line 2: invalid JSON") as caught:
                build_bundle(source)
            self.assertNotIn("SECRET_BROKEN_CONTENT", str(caught.exception))

    def test_nonfinite_or_nonobject_records_fail(self):
        for raw in ('{"type":"user","value":NaN}', "[]"):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / "input.jsonl"
                source.write_text(raw, encoding="utf-8")
                with self.assertRaisesRegex(InputError, "Line 1"):
                    build_bundle(source)

    def test_file_and_message_limits(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.jsonl"
            source.write_text('{"type":"user","message":{"content":"a"}}', encoding="utf-8")
            with patch("agentshare.core.MAX_INPUT_BYTES", 10):
                with self.assertRaisesRegex(InputError, "20 MiB"):
                    build_bundle(source)
        with self.assertRaisesRegex(InputError, "Line 1: message exceeds"):
            self.bundle([{"type": "user", "message": {"content": "a" * 100_001}}])
        with self.assertRaisesRegex(InputError, "Line 1: message exceeds"):
            self.bundle([{"type": "assistant", "message": {"content": [{"type": "text", "text": "a" * 60_000}, {"type": "text", "text": "b" * 60_000}]}}])

    def test_invalid_surrogate_fails_cleanly(self):
        with self.assertRaisesRegex(InputError, "invalid Unicode surrogate"):
            self.bundle([{"type": "user", "message": {"content": "\ud800"}}])

    def test_bom_blank_lines_and_static_bundle_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.jsonl"
            source.write_bytes(b'\xef\xbb\xbf\n{"type":"user","message":{"content":"hello"}}\n')
            result = build_bundle(source)
        self.assertEqual(result["title"], "AgentShare review")
        self.assertEqual(result["events"][0]["time"], "")
        self.assertEqual(result["events"][0]["id"], "e1")

    def test_mixed_unknown_empty_and_wrong_format_fail(self):
        for records, format in (([], "auto"), ([{"type": "unknown"}], "auto"), ([{"type": "user", "message": {"content": "x"}}], "codex"), ([{"type": "user", "message": {"content": "x"}}, {"type": "response_item", "payload": {"type": "message", "role": "user", "content": "x"}}], "auto")):
            with self.subTest(records=records, format=format), self.assertRaises(InputError):
                self.bundle(records, format)

    def test_demo_contains_only_synthetic_reviewable_content(self):
        result = demo_bundle()
        text = json.dumps(result)
        self.assertIn("Synthetic demo", text)
        self.assertNotIn("FAKE_TOOL_INPUT_ONLY", text)
        self.assertNotIn("FAKE_TOOL_OUTPUT_ONLY", text)
        self.assertNotIn("ghp_FAKE", text)
        self.assertNotIn("demo@example.test", text)


class RedactionTests(unittest.TestCase):
    def test_common_secret_categories(self):
        values = {
            "github_token": "ghp_FAKEONLYabcdefgh123456 github_pat_FAKEONLYabcdefgh123456",
            "api_token": "sk-proj-FAKEONLYabcdefgh123456",
            "aws_key": "AKIAFAKEONLY12345678",
            "bearer": "Bearer FAKEONLYabcdefgh123456",
            "assignment": 'API_KEY="FAKE ONLY secret" password=FakeOnlySecret token: FakeOnlyToken',
            "email": "test.user+demo@example.test",
            "home_path": 'C:\\Users\\Jane Doe\\Team Folder\\private.txt',
            "private_key": "-----BEGIN PRIVATE KEY-----\nFAKE_ONLY\n-----END PRIVATE KEY-----",
        }
        for category, value in values.items():
            with self.subTest(category=category):
                redactor = Redactor()
                result = redactor.redact(value)
                self.assertIn(f"[REDACTED:{category}]", result)
                self.assertGreater(redactor.counts[category], 0)
                self.assertNotIn("FAKEONLY", result)
                self.assertNotIn("FakeOnly", result)

    def test_unix_home_paths(self):
        for text in ("/home/demo/private/test.py", "/Users/demo/private/test.py", "/root/private.txt", "~/private/test.py"):
            with self.subTest(text=text):
                result = Redactor().redact(text)
                self.assertEqual(result, "[REDACTED:home_path]")

    def test_literals_are_longest_first_and_not_regex(self):
        redactor = Redactor(("a.b", "a.b-c", "", "  "))
        self.assertEqual(redactor.redact("a.b-c a.b axb"), "[REDACTED:custom] [REDACTED:custom] axb")
        self.assertEqual(redactor.counts["custom"], 2)

    def test_custom_prefix_does_not_defeat_builtin_secret_detection(self):
        for term, value, tail in (("sk-", "sk-proj-FAKEONLYabcdefgh123456", "FAKEONLYabcdefgh123456"), ("ghp_", "ghp_FAKEONLYabcdefgh123456", "FAKEONLYabcdefgh123456"), ("Bearer", "Bearer FAKEONLYabcdefgh123456", "FAKEONLYabcdefgh123456")):
            with self.subTest(term=term):
                result = Redactor((term,)).redact(value)
                self.assertNotIn(tail, result)


class CliFileProtectionTests(unittest.TestCase):
    def make_hardlink(self, source, alias):
        try:
            os.link(source, alias)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Hardlinks unavailable on this platform: {type(exc).__name__}.")

    def test_output_hardlink_to_input_is_rejected_without_modifying_input(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.jsonl"
            output = Path(folder) / "different-name.html"
            original = b'{"type":"user","message":{"content":"PRIVATE_ORIGINAL_TEXT"}}\n'
            source.write_bytes(original)
            self.make_hardlink(source, output)
            errors = io.StringIO()
            with redirect_stderr(errors), redirect_stdout(io.StringIO()):
                exit_code = main(["build", str(source), "--output", str(output)])
            self.assertEqual(exit_code, 2)
            self.assertIn("Input and output must be different files.", errors.getvalue())
            self.assertNotIn("PRIVATE_ORIGINAL_TEXT", errors.getvalue())
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(output.read_bytes(), original)

    def test_output_hardlink_to_termfile_is_rejected_without_modifying_terms(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.jsonl"
            terms = Path(folder) / "terms.txt"
            output = Path(folder) / "different-name.html"
            source_bytes = b'{"type":"user","message":{"content":"hello"}}\n'
            term_bytes = b"PRIVATE_CUSTOM_TERM\n"
            source.write_bytes(source_bytes)
            terms.write_bytes(term_bytes)
            self.make_hardlink(terms, output)
            errors = io.StringIO()
            with redirect_stderr(errors), redirect_stdout(io.StringIO()):
                exit_code = main(["build", str(source), "--term-file", str(terms), "--output", str(output)])
            self.assertEqual(exit_code, 2)
            self.assertIn("Term file and output must be different files.", errors.getvalue())
            self.assertNotIn("PRIVATE_CUSTOM_TERM", errors.getvalue())
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(terms.read_bytes(), term_bytes)
            self.assertEqual(output.read_bytes(), term_bytes)


if __name__ == "__main__":
    unittest.main()
