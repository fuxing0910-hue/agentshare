"""Command-line entry point; transcript content is never printed to the terminal."""

import argparse
from pathlib import Path
import sys

from .core import InputError, build_bundle, demo_bundle


def read_terms(path):
    if path is None:
        return ()
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(256 * 1024 + 1)
        if len(data) > 256 * 1024:
            raise InputError("Term file exceeds 256 KiB.")
        return data.decode("utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError("Cannot read term file as UTF-8 text.") from exc


def files_alias(protected: Path, output: Path) -> bool:
    """Check spelling/symlink aliases and existing hardlinks before writing."""
    if protected.resolve() == output.resolve():
        return True
    try:
        return protected.samefile(output)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise InputError("Cannot verify that input and output are different files.") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create a local review before sharing an AI coding transcript.")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Read one explicitly selected local JSONL transcript.")
    build.add_argument("input", type=Path)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--format", choices=("auto", "claude", "codex"), default="auto")
    build.add_argument("--term-file", type=Path, help="UTF-8 text, one additional literal to omit per line.")
    demo = commands.add_parser("demo", help="Create a review from synthetic fake data.")
    demo.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            if files_alias(args.input, args.output):
                raise InputError("Input and output must be different files.")
            if args.term_file and files_alias(args.term_file, args.output):
                raise InputError("Term file and output must be different files.")
            bundle = build_bundle(args.input, args.format, read_terms(args.term_file))
        else:
            bundle = demo_bundle()
        from .report import render_review
        html = render_review(bundle)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(html, encoding="utf-8")
    except (InputError, OSError) as exc:
        message = str(exc) if isinstance(exc, InputError) else "Cannot write output file."
        print(f"AgentShare: {message}", file=sys.stderr)
        return 2
    print(f"Created local review: {bundle['stats']['events']} events. Open the output file and review before sharing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
