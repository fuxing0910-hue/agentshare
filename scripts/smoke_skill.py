#!/usr/bin/env python3
"""Exercise only a copied skill with Python isolated from checkout and site packages."""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "share-ai-transcripts"


def review_bundle(path: Path) -> tuple[str, dict]:
    html = path.read_text(encoding="utf-8")
    match = re.search(r'<script id="review-data" type="application/json">(.*?)</script>', html, re.DOTALL)
    if match is None:
        raise AssertionError("Generated review has no embedded review bundle.")
    return html, json.loads(match.group(1))


def run(runner: Path, folder: Path, *arguments: str) -> None:
    # -I ignores PYTHONPATH and user site; -S also excludes global site packages.
    result = subprocess.run([sys.executable, "-I", "-S", str(runner), *arguments], cwd=folder, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise AssertionError(f"Portable CLI failed with exit {result.returncode}: {result.stderr}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, default=REPO / "work" / "skill-smoke", help="Scratch root for the isolated temporary directory.")
    args = parser.parse_args(argv)
    work = args.work_dir.resolve()
    if not SKILL.is_dir():
        raise AssertionError("Skill directory is missing.")
    for path in SKILL.rglob("*"):
        junction = getattr(path, "is_junction", lambda: False)
        if path.is_symlink() or junction() or not path.resolve().is_relative_to(SKILL.resolve()):
            raise AssertionError("Portable smoke does not copy redirected skill files.")
    work.mkdir(parents=True, exist_ok=True)
    # TemporaryDirectory owns a fresh generated child of the fixed work folder.
    with tempfile.TemporaryDirectory(prefix="portable-", dir=work) as temporary:
        folder = Path(temporary).resolve()
        if not folder.is_relative_to(work):
            raise AssertionError("Portable scratch path must remain in the work directory.")
        copied = folder / "share-ai-transcripts"
        shutil.copytree(SKILL, copied, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        runner = copied / "scripts" / "run.py"
        demo = folder / "demo-review.html"
        run(runner, folder, "demo", "--output", str(demo))
        demo_html, demo_data = review_bundle(demo)
        assert demo_data["source_format"] == "claude" and len(demo_data["events"]) == 5
        assert "FAKE_TOOL_INPUT_ONLY" not in demo_html and "FAKE_TOOL_OUTPUT_ONLY" not in demo_html
        terms = folder / "private-terms.txt"
        terms.write_text("Acme Internal\n", encoding="utf-8")
        text = "Synthetic portable test for Acme Internal. Contact fake.person@example.test. Fake key ghp_FAKE_PORTABLE_TOKEN_ONLY."
        claude = [
            {"type": "system", "cwd": "PRIVATE_METADATA_ONLY"},
            {"type": "user", "message": {"content": text}},
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "id": "private-call", "input": {"command": "RAW_TOOL_INPUT_ONLY"}}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "private-call", "is_error": True, "content": "RAW_TOOL_OUTPUT_ONLY"}]}},
        ]
        codex = [
            {"type": "session_meta", "payload": {"cwd": "PRIVATE_METADATA_ONLY"}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": text}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}},
            {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "call_id": "private-call", "arguments": "RAW_TOOL_INPUT_ONLY"}},
            {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "private-call", "output": "RAW_TOOL_OUTPUT_ONLY"}},
        ]
        for source_format, records in (("claude", claude), ("codex", codex)):
            source = folder / f"synthetic-{source_format}.jsonl"
            source.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
            original = source.read_bytes()
            output = folder / f"review-{source_format}.html"
            run(runner, folder, "build", str(source), "--output", str(output), "--format", source_format, "--term-file", str(terms))
            html, bundle = review_bundle(output)
            assert bundle["source_format"] == source_format and len(bundle["events"]) == 3
            assert bundle["stats"]["omitted_tool_bodies"] == 2
            for omitted in ("PRIVATE_METADATA_ONLY", "RAW_TOOL_INPUT_ONLY", "RAW_TOOL_OUTPUT_ONLY", "private-call", "Acme Internal", "fake.person@example.test", "FAKE_PORTABLE_TOKEN_ONLY"):
                assert omitted not in html, f"Excluded synthetic marker survived: {omitted}"
            assert source.read_bytes() == original
        assert not list(copied.rglob("__pycache__")), "Skill execution wrote bytecode caches."
        print("Portable skill smoke passed: demo + Claude/Codex synthetic builds, isolated Python, no checkout dependencies.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
