"""Tests for scripts/check_class_docstrings.py (#296)."""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / "scripts" / "check_class_docstrings.py"
_spec = importlib.util.spec_from_file_location("check_class_docstrings", _SCRIPT)
assert _spec is not None and _spec.loader is not None
check_class_docstrings = importlib.util.module_from_spec(_spec)
sys.modules["check_class_docstrings"] = check_class_docstrings
_spec.loader.exec_module(check_class_docstrings)


def _write_pkg(root: Path, body: str) -> None:
    """Write a tiny `agrogame/foo/__init__.py` with `body` for AST scanning."""
    (root / "agrogame").mkdir()
    (root / "agrogame" / "__init__.py").write_text("")
    (root / "agrogame" / "foo").mkdir()
    (root / "agrogame" / "foo" / "__init__.py").write_text(body)


def test_documented_canonical_class_passes(tmp_path):
    """A *Params/*State/*Module/*Runtime class with a docstring is OK."""
    _write_pkg(
        tmp_path,
        textwrap.dedent(
            '''\
            class FooParams:
                """params docstring."""
                pass

            class FooState:
                """state docstring."""
                pass
            '''
        ),
    )
    missing = check_class_docstrings.find_missing(tmp_path / "agrogame")
    assert missing == []


def test_undocumented_canonical_class_flagged(tmp_path):
    """A *Module class without a docstring is flagged."""
    _write_pkg(
        tmp_path,
        "class FooModule:\n    pass\n",
    )
    missing = check_class_docstrings.find_missing(tmp_path / "agrogame")
    assert len(missing) == 1
    assert "FooModule" in missing[0]


def test_non_canonical_class_ignored(tmp_path):
    """Classes whose names don't end in the canonical suffixes are not checked."""
    _write_pkg(tmp_path, "class FooHelper:\n    pass\n")
    assert check_class_docstrings.find_missing(tmp_path / "agrogame") == []


def test_private_class_ignored(tmp_path):
    """`_FooParams` (private) is exempt — it's an internal helper."""
    _write_pkg(tmp_path, "class _FooParams:\n    pass\n")
    assert check_class_docstrings.find_missing(tmp_path / "agrogame") == []


def test_excluded_dirs_skipped(tmp_path):
    """`agrogame/dashboard/...` and `agrogame/plots/...` are not scanned."""
    (tmp_path / "agrogame" / "dashboard").mkdir(parents=True)
    (tmp_path / "agrogame" / "__init__.py").write_text("")
    (tmp_path / "agrogame" / "dashboard" / "__init__.py").write_text("")
    (tmp_path / "agrogame" / "dashboard" / "models.py").write_text(
        "class FooParams:\n    pass\n"
    )
    assert check_class_docstrings.find_missing(tmp_path / "agrogame") == []


def test_real_repo_passes():
    """Live repo: every public canonical class has a docstring."""
    missing = check_class_docstrings.find_missing()
    assert missing == [], "\n".join(missing)
