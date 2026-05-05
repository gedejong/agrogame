#!/usr/bin/env python3
"""Enforce 100% docstring coverage on canonical class types (#296).

The naming convention in `docs/conventions.md` §2 reserves the suffixes
``Params`` / ``State`` / ``Module`` / ``Runtime`` for canonical domain
classes. Per Phase 3 of #293, every public class with one of these
suffixes must carry a docstring — `interrogate`'s percentage gate isn't
expressive enough to require 100% on a name pattern only, so this AST
walker enforces it directly.

Private classes (``_Foo``) are skipped — they're internal helpers and
fall under interrogate's project-wide gate instead.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SUFFIXES = ("Params", "State", "Module", "Runtime")
PKG_ROOT = Path(__file__).resolve().parent.parent / "agrogame"
EXCLUDE_DIRS = frozenset({"dashboard", "plots"})


def _is_excluded(path: Path) -> bool:
    """True if any segment of the file path is in the excluded set."""
    return any(part in EXCLUDE_DIRS for part in path.parts)


def find_missing(root: Path = PKG_ROOT) -> list[str]:
    """Return ``"path:line ClassName"`` for every undocumented canonical class."""
    missing: list[str] = []
    for py in sorted(root.rglob("*.py")):
        if _is_excluded(py):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, OSError) as exc:
            print(f"warning: cannot parse {py}: {exc}", file=sys.stderr)
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if node.name.startswith("_"):
                continue
            if not node.name.endswith(SUFFIXES):
                continue
            if not ast.get_docstring(node):
                rel = py.relative_to(root.parent)
                missing.append(f"{rel}:{node.lineno} {node.name}")
    return missing


def main() -> int:
    """CLI entry point: print any offenders to stderr and exit non-zero."""
    missing = find_missing()
    if not missing:
        print("OK: every public *Params/*State/*Module/*Runtime class has a docstring")
        return 0
    print(
        f"error: {len(missing)} canonical class(es) missing docstrings:",
        file=sys.stderr,
    )
    for m in missing:
        print(f"  {m}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
