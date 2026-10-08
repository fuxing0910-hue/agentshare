#!/usr/bin/env python3
"""Maintain the source-only AgentShare runtime at one fixed skill path."""

import argparse
from pathlib import Path
import shutil
import sys


REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "agentshare"
SKILL_SCRIPTS = REPO / "skills" / "share-ai-transcripts" / "scripts"
VENDORED = SKILL_SCRIPTS / "agentshare"
SOURCE_LICENSE = REPO / "LICENSE"
VENDORED_LICENSE = SKILL_SCRIPTS / "LICENSE"


def safe_path(path: Path) -> None:
    """Reject redirected managed paths before any copy or deletion."""
    if not path.resolve().is_relative_to(REPO):
        raise ValueError("Managed path must remain inside this repository.")
    if path.resolve() != path.absolute():
        raise ValueError("Managed source and destination paths cannot be redirected.")
    current = REPO
    for part in path.relative_to(REPO).parts:
        current = current / part
        junction = getattr(current, "is_junction", lambda: False)
        if current.is_symlink() or junction():
            raise ValueError("Managed source and destination paths cannot contain links.")


def source_files() -> dict[Path, Path]:
    safe_path(SOURCE)
    safe_path(SOURCE_LICENSE)
    if not SOURCE.is_dir() or not SOURCE_LICENSE.is_file():
        raise ValueError("Expected repository package and LICENSE are missing.")
    result = {}
    for path in sorted(SOURCE.rglob("*")):
        relative = path.relative_to(SOURCE)
        if "__pycache__" in relative.parts or path.suffix in (".pyc", ".pyo"):
            continue
        safe_path(path)
        if path.is_file() and (path.suffix == ".py" or relative.parts[0] == "templates"):
            result[relative] = path
    if not result or Path("templates/review.html") not in result:
        raise ValueError("Expected runtime source and review template are missing.")
    return result


def vendored_files() -> dict[Path, Path]:
    safe_path(SKILL_SCRIPTS)
    safe_path(VENDORED)
    if not VENDORED.exists():
        return {}
    if not VENDORED.is_dir():
        raise ValueError("Vendored package path must be a directory.")
    result = {}
    for path in sorted(VENDORED.rglob("*")):
        safe_path(path)
        if path.is_file():
            result[path.relative_to(VENDORED)] = path
    return result


def differences(expected: dict[Path, Path], actual: dict[Path, Path]) -> list[str]:
    problems = []
    for relative, source in expected.items():
        if relative not in actual:
            problems.append(f"missing: {relative.as_posix()}")
        elif source.read_bytes() != actual[relative].read_bytes():
            problems.append(f"changed: {relative.as_posix()}")
    for relative in sorted(actual.keys() - expected.keys()):
        problems.append(f"unexpected: {relative.as_posix()}")
    safe_path(VENDORED_LICENSE)
    if not VENDORED_LICENSE.is_file():
        problems.append("missing: scripts/LICENSE")
    elif SOURCE_LICENSE.read_bytes() != VENDORED_LICENSE.read_bytes():
        problems.append("changed: scripts/LICENSE")
    return problems


def synchronize(expected: dict[Path, Path], actual: dict[Path, Path]) -> None:
    # Paths and every existing descendant were verified by the manifest reads.
    # Remove stale files individually; never recursively remove a computed tree.
    for relative in actual.keys() - expected.keys():
        stale = VENDORED / relative
        safe_path(stale)
        stale.unlink()
    VENDORED.mkdir(parents=True, exist_ok=True)
    for relative, source in expected.items():
        destination = VENDORED / relative
        safe_path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    for directory in sorted((path for path in VENDORED.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
        safe_path(directory)
        if not any(directory.iterdir()):
            directory.rmdir()
    safe_path(VENDORED_LICENSE)
    shutil.copyfile(SOURCE_LICENSE, VENDORED_LICENSE)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if vendored source or LICENSE differs; do not modify files.")
    args = parser.parse_args(argv)
    try:
        expected, actual = source_files(), vendored_files()
        if args.check:
            problems = differences(expected, actual)
            if problems:
                print("Skill runtime is out of sync:")
                for problem in problems:
                    print(f"  {problem}")
                return 1
        else:
            synchronize(expected, actual)
            problems = differences(expected, vendored_files())
            if problems:
                raise ValueError("Skill runtime did not match source after synchronization.")
    except (OSError, ValueError) as exc:
        print(f"Skill sync failed: {exc}", file=sys.stderr)
        return 2
    print(f"Skill runtime matches {len(expected)} source files and LICENSE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
