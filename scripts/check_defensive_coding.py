from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable


BROAD_EXCEPTS = {"Exception", "BaseException"}


def iter_py_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.py"):
        if "/.venv/" in str(p):
            continue
        yield p


class DefensiveVisitor(ast.NodeVisitor):
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.issues: list[str] = []

    def visit_Try(self, node: ast.Try) -> None:  # noqa: N802
        # Flag bare except: and broad excepts with only pass
        for handler in node.handlers:
            exc = handler.type
            names: list[str] = []
            if exc is None:
                names = ["<bare>"]
            elif isinstance(exc, ast.Name):
                names = [exc.id]
            elif isinstance(exc, ast.Tuple):
                for elt in exc.elts:
                    if isinstance(elt, ast.Name):
                        names.append(elt.id)
            # Determine if handler body is effectively empty
            body_effective = [
                stmt for stmt in handler.body if not isinstance(stmt, ast.Pass)
            ]
            if exc is None:
                self.issues.append(
                    f"{self.filename}:{handler.lineno} bare except: detected"
                )
            for nm in names:
                if nm in BROAD_EXCEPTS and not body_effective:
                    self.issues.append(
                        f"{self.filename}:{handler.lineno}"
                        f" broad except {nm} with no handling"
                    )
        self.generic_visit(node)


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    issues: list[str] = []
    for path in iter_py_files(root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception as e:  # it's okay to print parse error for this tool itself
            print(f"Could not parse {path}: {e}", file=sys.stderr)
            continue
        vis = DefensiveVisitor(str(path))
        vis.visit(tree)
        issues.extend(vis.issues)
    if issues:
        print("Defensive coding issues found:")
        for line in issues:
            print(" -", line)
        return 1
    print("No defensive coding issues found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
