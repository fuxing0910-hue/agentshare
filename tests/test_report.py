"""Privacy-context regression tests for the HTML renderer and fresh exports."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

from agentshare.report import render_review


def bundle(text: str = "Hello") -> dict:
    return {
        "version": 1,
        "source_format": "claude",
        "events": [{"id": "e1", "kind": "assistant", "label": "Reply", "text": text, "status": "info", "time": ""}],
        "stats": {"events": 1, "redactions": {}, "omitted_tool_bodies": 0, "unsupported_records": 0},
        "warnings": [],
    }


class ReviewTests(unittest.TestCase):
    def test_script_terminators_and_html_are_escaped_in_data(self) -> None:
        hostile = '</script><img src="https://invalid.test/x" onerror="alert(1)">&\u2028\u2029'
        html = render_review(bundle(hostile))
        payload = re.search(r'<script id="review-data" type="application/json">(.*?)</script>', html, re.DOTALL)
        self.assertIsNotNone(payload)
        encoded = payload.group(1)
        self.assertNotIn("<", encoded)
        self.assertNotIn(">", encoded)
        self.assertNotIn("&", encoded)
        self.assertEqual(json.loads(encoded)["events"][0]["text"], hostile)
        self.assertNotIn('<img src="https://invalid.test/x"', html)

    def test_unknown_fields_never_enter_review(self) -> None:
        data = bundle()
        data["raw_source"] = "TOP_LEVEL_SECRET"
        data["events"][0]["raw_text"] = "EVENT_SECRET"
        html = render_review(data)
        self.assertNotIn("TOP_LEVEL_SECRET", html)
        self.assertNotIn("EVENT_SECRET", html)

    def test_default_selection_is_empty(self) -> None:
        html = render_review(bundle())
        self.assertIn("const selected = new Set();", html)
        self.assertIn('id="export-html" disabled', html)
        self.assertNotIn("localStorage", html)
        self.assertIn("connect-src 'none'", html)

    def test_empty_and_duplicate_source_identifiers(self) -> None:
        data = bundle()
        data["events"].append(dict(data["events"][0]))
        html = render_review(data)
        payload = re.search(r'<script id="review-data" type="application/json">(.*?)</script>', html, re.DOTALL).group(1)
        self.assertEqual([event["id"] for event in json.loads(payload)["events"]], ["e1", "e2"])
        self.assertIn("No reviewable messages", render_review({"events": []}))

    def test_detailed_warnings_are_collapsed_by_default(self) -> None:
        data = bundle()
        data["warnings"] = ["Pattern detection is incomplete."]
        html = render_review(data)
        details = re.search(r'<details id="warning-details"([^>]*)>(.*?)</details>', html, re.DOTALL)
        self.assertIsNotNone(details)
        self.assertNotIn("open", details.group(1))
        self.assertIn('id="warnings"', details.group(2))
        self.assertIn("What was removed and what may remain", details.group(2))


@unittest.skipUnless(shutil.which("node"), "Node is optional; needed to execute browser export helper tests")
class BrowserExportTests(unittest.TestCase):
    def export(self, format_name: str) -> str:
        template = Path(__file__).parents[1] / "agentshare" / "templates" / "review.html"
        source = template.read_text(encoding="utf-8")
        helpers = source.split("/* BEGIN EXPORT HELPERS */", 1)[1].split("/* END EXPORT HELPERS */", 1)[0]
        script = helpers + "\n" + r'''
const sourceEvents = [
  {id:'e1',kind:'user',label:'Review',text:'ORIGINAL_SELECTED_SECRET',status:'info',time:''},
  {id:'e2',kind:'tool',label:'EXCLUDED_LABEL_SECRET',text:'EXCLUDED_BODY_SECRET',status:'error',time:''}
];
const edited = new Map([['e1', '</script><img src="https://evil.test" onerror="alert(1)">\n```danger\n& selected edit']]);
const chosen = selectEditedEvents(sourceEvents, edited, new Set(['e1']));
'''
        script += f"process.stdout.write(buildSelected{format_name}(chosen));"
        result = subprocess.run([shutil.which("node"), "-e", script], capture_output=True, text=True, check=True, encoding="utf-8")
        return result.stdout

    def test_html_contains_selected_edited_text_only_and_no_scripts(self) -> None:
        result = self.export("Html")
        for excluded in ("ORIGINAL_SELECTED_SECRET", "EXCLUDED_LABEL_SECRET", "EXCLUDED_BODY_SECRET", "review-data"):
            self.assertNotIn(excluded, result)
        self.assertNotIn("<script", result.lower())
        self.assertNotIn("<img", result.lower())
        self.assertIn("&lt;/script&gt;&lt;img", result)
        self.assertIn("&amp; selected edit", result)

    def test_markdown_fence_cannot_be_closed_by_message_text(self) -> None:
        result = self.export("Markdown")
        self.assertIn("````text", result)
        self.assertIn("```danger", result)
        self.assertNotIn("EXCLUDED_BODY_SECRET", result)
        self.assertNotIn("ORIGINAL_SELECTED_SECRET", result)


if __name__ == "__main__":
    unittest.main()
