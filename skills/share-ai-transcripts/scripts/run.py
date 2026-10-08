#!/usr/bin/env python3
"""Run the bundled AgentShare CLI without installation or a checkout."""

from pathlib import Path
import sys


def main() -> int:
    if sys.version_info < (3, 10):
        print("AgentShare requires Python 3.10 or newer.", file=sys.stderr)
        return 2
    # Keep the installed skill source-only, and put its own package first even
    # when the caller has another AgentShare checkout or installation.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from agentshare.__main__ import main as cli_main
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
