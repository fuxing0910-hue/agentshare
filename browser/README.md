# Portable browser trial

`site/try.html` lets a visitor use AgentShare with their own Claude Code or Codex
JSONL file before installing the Python CLI or Skill. It is a generated,
self-contained document: no CDN, third-party package, upload endpoint, analytics,
account, or persistent browser storage.

The parent document reads only an explicitly chosen file and sends its bytes to a
local Blob Web Worker. `parser.js` mirrors the Python adapter and redaction
pipeline. Only the minimized bundle is inserted into the existing review
template, with JSON escaped for the HTML script-data context. The review runs in
a sandboxed iframe with `allow-scripts allow-downloads` and without
`allow-same-origin`. Candidate text is rendered by the template's `textContent`
and textarea values. Its existing selection, editing, HTML, and Markdown export
code stays unchanged. The browser build appends a download override to delegate
selected export text to the parent using a narrow `postMessage` protocol. The
parent accepts only the current iframe window, opaque `null` origin, a fresh
per-review random token, fixed filenames and MIME types, a positive selection
count, and bounded content. It prepares a parent-origin Blob download and an
explicit save link; no same-origin permission is added to the iframe. Status
reports a download request rather than claiming that a file reached disk.

No messages are selected initially. Reset terminates any active worker, revokes
its Blob URL, removes the candidate document, navigates the iframe to a blank
document, and clears the file selection and private terms. Downloads already
saved to disk remain there.

## Build and checks

From the repository root:

```sh
python scripts/build_browser.py
python scripts/build_browser.py --check
python -m unittest discover -s tests -v
```

The build needs only Python's standard library. Browser parity tests additionally
need Node.js 18 or newer, use no browser engine, and run the same synthetic
fixtures through the JavaScript parser and Python implementation. CI requires
Node rather than silently skipping those checks. Fixtures cover supported
Claude/Codex adapters, block order, occurrence-based duplicate handling, raw tool
and metadata omission, unknown tool names, prototype-like identifiers, common
redaction categories, literal term ordering, invalid UTF-8 and surrogates,
unsupported/mixed formats, file/message/term limits, astral Unicode character
counts, malformed JSON, and closing-script/HTML injection containment. Separate
human or CUA browser checks are needed for the file picker, Worker startup,
sandboxed editing, and actual downloads.

If Python adapter/redaction behavior or the review template changes, update the
JavaScript behavior and its fixture coverage, then regenerate `site/try.html`.
The fixture checks establish agreement for covered cases, not identical regex
engine behavior for every possible Unicode string.

## Browser-specific limits

- UTF-8 JSONL, at most 20 MiB, with 100,000 Unicode code points per visible
  message; combined Claude text blocks are bounded together.
- At most 5,000 candidate events may be rendered in the browser UI. A larger
  bundle is rejected with a Python CLI fallback; it is never silently truncated.
- At most 1,000 distinct private terms, each at most 4,096 code points. Terms are
  case-sensitive literal matches, applied after built-in patterns.
- A browser with Blob Web Workers, fatal UTF-8 `TextDecoder`, Unicode property
  regular expressions, regex lookbehind, and sandboxed downloads is required.
- Automatic redaction is incomplete. The user must inspect every selected
  message before sharing. The review document contains all candidates and should
  stay private; selected exports include only chosen messages and current edits.

`site/try.html` can be served statically by GitHub Pages. Its download link saves
the whole browser tool for local use after the initial page load, including when
already running from a local file. It reconstructs the initial document from
immutable source assets and does not serialize the active DOM or include the
user's transcript, edited text, file selection, or private terms. Browser or
enterprise policy may disallow Workers or sandboxed downloads; the Python CLI is
the fallback.
