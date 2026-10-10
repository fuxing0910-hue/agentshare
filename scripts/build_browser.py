"""Build the portable browser trial with standard-library tooling only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentshare.core import demo_bundle  # noqa: E402

BRIDGE_TOKEN = "__AGENTSHARE_DOWNLOAD_TOKEN__"


def browser_review_template() -> str:
    """Keep the CLI template unchanged; bridge only hosted browser downloads."""
    template = (ROOT / "agentshare" / "templates" / "review.html").read_text(encoding="utf-8")
    bridge = """
// Sandbox downloads are delegated to the parent, without same-origin access.
download = function(content, filename, mime) {
  window.parent.postMessage({type:'agentshare-download',token:'__AGENTSHARE_DOWNLOAD_TOKEN__',content,filename,mime,selected_count:selected.size}, '*');
  document.getElementById('download-status').textContent = `Download requested: ${filename} with ${selected.size} selected messages.`;
};
"""
    before, separator, after = template.rpartition("</script>")
    if not separator or BRIDGE_TOKEN in template:
        raise RuntimeError("review template cannot receive the browser download bridge")
    return before + bridge + separator + after


def script_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    for character, escaped in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        payload = payload.replace(character, escaped)
    return payload


def build() -> str:
    shell = (ROOT / "browser" / "try.html").read_text(encoding="utf-8")
    marker = "__BROWSER_ASSETS_JSON__"
    if shell.count(marker) != 1:
        raise RuntimeError("browser shell must have exactly one data marker")
    bridge_source = (ROOT / "browser" / "download_bridge.js").read_text(encoding="utf-8")
    assets = {
        "template": browser_review_template(),
        "parser": (ROOT / "browser" / "parser.js").read_text(encoding="utf-8"),
        "demo": demo_bundle(),
        "shell": shell,
        "bridge": bridge_source,
    }
    if assets["template"].count("__AGENTSHARE_BUNDLE_JSON__") != 1:
        raise RuntimeError("review template must have exactly one data marker")
    code_marker = "__DOWNLOAD_BRIDGE_JS__"
    if shell.count(code_marker) != 1:
        raise RuntimeError("browser shell must have exactly one download bridge marker")
    if "</script" in bridge_source.lower():
        raise RuntimeError("download bridge must be safe in an inline script context")
    return shell.replace(code_marker, bridge_source).replace(marker, script_json(assets))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if site/try.html is stale")
    args = parser.parse_args()
    destination = ROOT / "site" / "try.html"
    content = build().encode("utf-8")
    if args.check:
        if not destination.exists() or destination.read_bytes() != content:
            print("Browser trial is stale; run python scripts/build_browser.py.", file=sys.stderr)
            return 1
        print("Browser trial matches its sources.")
        return 0
    destination.write_bytes(content)
    print("Built site/try.html.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
