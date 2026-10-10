"""Browser/Python parity and standalone build checks, without a browser engine."""

import base64
import json
import os
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from agentshare.core import DEMO_CLAUDE, InputError, build_bundle
from agentshare.report import render_review
from scripts.build_browser import build, browser_review_template

ROOT = Path(__file__).resolve().parents[1]


def encoded(records):
    return "\n".join(json.dumps(record, ensure_ascii=True) for record in records).encode("utf-8")


def claude(text):
    return [{"type": "user", "message": {"content": text}}]


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if not cls.node:
            if os.environ.get("CI"):
                raise RuntimeError("Node.js is required for browser parity checks in CI.")
            raise unittest.SkipTest("Node.js not available; browser parity checks need Node 18+.")

    def javascript(self, cases):
        result = subprocess.run(
            [self.node, str(ROOT / "tests" / "browser_runner.cjs")],
            input=json.dumps(cases), text=True, encoding="utf-8", capture_output=True, check=True,
        )
        return json.loads(result.stdout)

    def compare(self, cases):
        requests = []
        for case in cases:
            requests.append({"base64": base64.b64encode(case["data"]).decode("ascii"),
                             "format": case.get("format", "auto"), "terms": case.get("terms", []),
                             "render": case.get("render", False)})
        results = self.javascript(requests)
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "PRIVATE_SOURCE_FILENAME.jsonl"
            for case, result in zip(cases, results):
                with self.subTest(name=case["name"]):
                    source.write_bytes(case["data"])
                    try:
                        expected = build_bundle(source, case.get("format", "auto"), case.get("terms", []))
                    except InputError as error:
                        self.assertIn("error", result)
                        # Python includes a parser column; JavaScript deliberately
                        # omits engine-specific error snippets and positions.
                        self.assertEqual(result["error"], str(error).split(" (column")[0] + ("." if " (column" in str(error) else ""))
                    else:
                        self.assertNotIn("error", result)
                        self.assertEqual(result["bundle"], expected)
                        if case.get("render"):
                            self.assertEqual(result["html"], render_review(expected))
        return results

    def test_adapters_and_minimized_metadata_match_python(self):
        cases = [{"name": "synthetic demo", "data": encoded(DEMO_CLAUDE)},
                 {"name": "codex example", "data": (ROOT / "examples" / "demo-codex.jsonl").read_bytes()}]
        records = [
            {"type": "system", "sessionId": "PRIVATE_SESSION", "cwd": "PRIVATE_CWD"},
            {"type": "assistant", "timestamp": "PRIVATE_TIMESTAMP", "message": {"model": "PRIVATE_MODEL", "content": [
                {"type": "text", "text": "before"},
                {"type": "tool_use", "id": "__proto__", "name": "Bash", "input": "PRIVATE_INPUT"},
                {"type": "text", "text": "after"},
                {"type": "thinking", "thinking": "PRIVATE_REASONING"},
                {"type": "tool_use", "id": "constructor", "name": "PRIVATE_TOOL_NAME", "input": "PRIVATE_INPUT_2"}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "__proto__", "is_error": False, "content": "PRIVATE_OUTPUT"},
                {"type": "tool_result", "tool_use_id": "constructor", "status": "failed", "content": "PRIVATE_OUTPUT_2"},
                {"type": "text", "text": "   "}, {"type": "image", "source": "PRIVATE_IMAGE"}]}},
            {"type": "assistant", "message": {"content": []}},
        ]
        cases.append({"name": "Claude ordered blocks and prototype IDs", "data": encoded(records), "render": True})
        records = [
            {"type": "session_meta", "payload": {"id": "PRIVATE_SESSION", "cwd": "PRIVATE_CWD"}},
            *[{"type": "event_msg", "payload": {"type": "user_message", "message": "yes"}},
              {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "yes"}]}}] * 2,
            {"type": "event_msg", "payload": {"type": "user_message", "message": "yes"}},
            {"type": "response_item", "payload": {"type": "message", "role": "developer", "content": "PRIVATE_INSTRUCTIONS"}},
            {"type": "response_item", "payload": {"type": "function_call", "call_id": "__proto__", "name": "functions.exec_command", "arguments": "PRIVATE_INPUT"}},
            {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "__proto__", "output": "PRIVATE_OUTPUT failed with error"}},
            {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "constructor", "call_id": "constructor", "input": "PRIVATE_INPUT"}},
            {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "constructor", "status": "completed", "output": "PRIVATE_OUTPUT"}},
            {"type": "response_item", "payload": {"type": "reasoning", "summary": "PRIVATE_REASONING"}},
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "fallback"}},
        ]
        cases.append({"name": "Codex duplicates, explicit statuses, prototypes", "data": encoded(records)})
        results = self.compare(cases)
        for result in results[2:]:
            self.assertNotIn("PRIVATE_", json.dumps(result))
        self.assertEqual([event["text"] for event in results[2]["bundle"]["events"]][:3], ["before", "Tool input omitted.", "after"])
        self.assertEqual([event["text"] for event in results[3]["bundle"]["events"]][:3], ["yes", "yes", "yes"])

    def test_redaction_categories_and_literal_terms_match_python(self):
        texts = [
            'API_KEY="FAKE ONLY secret" password=FakeOnlySecret token: FakeOnlyToken authorization: FakeAuth',
            'ghp_FAKEONLYabcdefgh123456 github_pat_FAKEONLYabcdefgh123456 sk-proj-FAKEONLYabcdefgh123456',
            'AKIAFAKEONLY12345678 Bearer FAKEONLYabcdefgh123456 test.user+demo@example.test',
            'C:\\Users\\Jane Doe\\Team Folder\\private.txt', '/home/demo/private.txt', '/Users/demo/private.txt', '/root/private.txt', '~/private/test.py',
            '-----BEGIN RSA PRIVATE KEY-----\nFAKE_ONLY\n-----END RSA PRIVATE KEY-----',
            'a.b-c a.b axb Acme Corporation at Acme',
            '中API_KEY=literal 中test@example.test 文ghp_FAKEONLYabcdefgh123456',
        ]
        self.compare([{"name": f"pattern {index}", "data": encoded(claude(text)), "terms": ["Acme", "Acme Corporation", "a.b", "a.b-c", "sk-", "ghp_", "Bearer", "User"]} for index, text in enumerate(texts)])

    def test_limits_unicode_formats_and_errors_match_python(self):
        cases = [
            {"name": "BOM and blanks", "data": b'\xef\xbb\xbf\n' + encoded(claude("hello 😀 中文"))},
            {"name": "mid-file BOM is rejected", "data": encoded(claude("hello")) + b'\n\xef\xbb\xbf'},
            {"name": "astral within codepoint limit", "data": encoded(claude("😀" * 100000))},
            {"name": "astral over limit", "data": encoded(claude("😀" * 100001))},
            {"name": "all visible blocks bound", "data": encoded([{"type": "assistant", "message": {"content": [{"type": "text", "text": "a" * 60000}, {"type": "text", "text": "b" * 60000}]}}])},
            {"name": "invalid Unicode high surrogate", "data": encoded(claude("\ud800"))},
            {"name": "invalid Unicode low surrogate", "data": encoded(claude("\udc00"))},
            {"name": "malformed second line", "data": encoded(claude("valid")) + b'\n{PRIVATE_INVALID_SOURCE'},
            {"name": "invalid UTF8", "data": b'\xffPRIVATE_INVALID_SOURCE'},
            {"name": "nonfinite", "data": b'{"type":"user","value":NaN}'},
            {"name": "nonobject", "data": b'[]'},
            {"name": "empty", "data": b'  \r\n'},
            {"name": "unsupported", "data": encoded([{"type": "unknown"}])},
            {"name": "wrong explicit format", "data": encoded(claude("hello")), "format": "codex"},
            {"name": "mixed formats", "data": encoded(claude("hello") + [{"type": "session_meta", "payload": {}}])},
            {"name": "oversize file", "data": b' ' * (20 * 1024 * 1024 + 1)},
            {"name": "oversize private term", "data": encoded(claude("hello")), "terms": ["x" * 4097]},
            {"name": "too many private terms", "data": encoded(claude("hello")), "terms": [f"term-{index}" for index in range(1001)]},
        ]
        results = self.compare(cases)
        for result in results:
            if "error" in result:
                self.assertNotIn("PRIVATE_", result["error"])

    def test_html_injection_is_text_and_build_is_self_contained(self):
        payload = '</script><img src=x onerror=alert(1)><script>alert("injected")</script> & > ` ``` 😀'
        result = self.compare([{"name": "closing-script injection", "data": encoded(claude(payload)), "render": True}])[0]
        html = result["html"]
        data = html.split('<script id="review-data" type="application/json">', 1)[1].split('</script>', 1)[0]
        self.assertNotIn("<", data)
        self.assertEqual(json.loads(data)["events"][0]["text"], payload)
        standalone = build()
        self.assertEqual((ROOT / "site" / "try.html").read_bytes(), standalone.encode("utf-8"))
        self.assertIn('sandbox="allow-scripts allow-downloads"', standalone)
        self.assertNotIn('allow-same-origin', standalone)
        assets = standalone.split('<script id="trial-assets" type="application/json">', 1)[1].split('</script>', 1)[0]
        self.assertNotIn("<", assets)
        self.assertEqual(json.loads(assets)["template"], browser_review_template())
        for forbidden in ('fetch(', 'XMLHttpRequest', 'localStorage', 'sessionStorage', 'indexedDB', '<script src=', 'navigator.sendBeacon'):
            self.assertNotIn(forbidden, standalone)

    def test_parent_download_protocol_and_private_free_offline_tool(self):
        standalone = build()
        assets = json.loads(standalone.split('<script id="trial-assets" type="application/json">', 1)[1].split('</script>', 1)[0])
        result = subprocess.run(
            [self.node, str(ROOT / "tests" / "browser_bridge_runner.cjs")],
            input=json.dumps({"assets": assets, "standalone": standalone}), text=True,
            encoding="utf-8", capture_output=True, check=True,
        )
        self.assertEqual(result.stdout.strip(), "Download bridge checks passed.")

    def test_form_controls_do_not_shadow_native_form_methods(self):
        class FormControls(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_form = False
                self.identifiers = set()

            def handle_starttag(self, tag, attrs):
                if tag == "form":
                    self.in_form = True
                if self.in_form and tag in {"input", "button", "select", "textarea", "fieldset", "output"}:
                    self.identifiers.update(value for key, value in attrs if key in {"id", "name"} and value)

            def handle_endtag(self, tag):
                if tag == "form":
                    self.in_form = False

        controls = FormControls()
        controls.feed(build())
        reserved = {"reset", "submit", "requestSubmit", "checkValidity", "reportValidity"}
        self.assertFalse(controls.identifiers & reserved, "Form named controls shadow native methods.")
        self.assertIn("clear-review", controls.identifiers)


if __name__ == "__main__":
    unittest.main()
