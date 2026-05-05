"""Tests for scripts/check_docs_coverage.py (#295).

Smoke + unit coverage. The realistic-state check (running against the actual
repo) lives at the bottom and asserts the gate currently passes; the helper
tests use temporary directories with monkey-patched paths so the gate's
failure modes can be exercised without polluting the repo.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
from pathlib import Path

import pytest

# Load the script as a module so we can call run() directly.
ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / "scripts" / "check_docs_coverage.py"
_spec = importlib.util.spec_from_file_location("check_docs_coverage", _SCRIPT)
assert _spec is not None and _spec.loader is not None
check_docs_coverage = importlib.util.module_from_spec(_spec)
sys.modules["check_docs_coverage"] = check_docs_coverage
_spec.loader.exec_module(check_docs_coverage)


def _make_pkg(root: Path, name: str, init_body: str = '"""docstring."""\n') -> Path:
    """Create a Python package directory with the given __init__.py body."""
    pkg = root / name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text(init_body)
    return pkg


def _make_doc(
    docs: Path,
    filename: str,
    *,
    module: str | None = None,
    extra_frontmatter: dict | None = None,
    body: str = "Body text.\n",
) -> Path:
    """Write a docs page with optional YAML frontmatter."""
    docs.mkdir(parents=True, exist_ok=True)
    if module is None and not extra_frontmatter:
        text = body
    else:
        fm: dict = {}
        if module is not None:
            fm["module"] = module
            fm.setdefault("doc_type", "module")
        if extra_frontmatter:
            fm.update(extra_frontmatter)
        # Render minimal YAML (avoid pulling pyyaml into the test if not installed)
        import yaml

        text = "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n" + body
    path = docs / filename
    path.write_text(text)
    return path


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """Build a tiny fake repo and point the check script at it.

    The schema and helper constants are monkey-patched onto the module so
    each test can declare its own packages and docs pages independently.
    """
    pkg_root = tmp_path / "agrogame"
    docs_root = tmp_path / "docs"
    pkg_root.mkdir()
    docs_root.mkdir()
    # Top-level package marker
    (pkg_root / "__init__.py").write_text('"""top-level."""\n')

    # Schema: copy the real one in so we test against the production schema.
    schema_dst = docs_root / "knowledge-base-schema.json"
    schema_dst.write_text((ROOT / "docs" / "knowledge-base-schema.json").read_text())

    monkeypatch.setattr(check_docs_coverage, "ROOT", tmp_path)
    monkeypatch.setattr(check_docs_coverage, "PKG_ROOT", pkg_root)
    monkeypatch.setattr(check_docs_coverage, "DOCS_ROOT", docs_root)
    monkeypatch.setattr(check_docs_coverage, "SCHEMA_PATH", schema_dst)
    # Reset allowlist so each test controls coverage requirements explicitly.
    monkeypatch.setattr(check_docs_coverage, "PACKAGE_ALLOWLIST", frozenset())

    return tmp_path, pkg_root, docs_root


def test_pass_with_complete_kb(fake_repo):
    """A package + matching docs page + __init__.py URL → green."""
    tmp_path, pkg_root, docs_root = fake_repo
    init = textwrap.dedent(
        '''\
        """foo package.

        Docs: https://github.com/gedejong/agrogame/blob/main/docs/foo.md
        """
        '''
    )
    _make_pkg(pkg_root, "foo", init_body=init)
    _make_doc(docs_root, "foo.md", module="agrogame.foo")

    result = check_docs_coverage.run()
    assert result.ok, result.errors
    assert result.packages_required == 1
    assert result.pages_seen == 1


def test_missing_docs_page_fails(fake_repo):
    """A required package without a docs page is a hard error."""
    _, pkg_root, _ = fake_repo
    _make_pkg(pkg_root, "foo")
    result = check_docs_coverage.run()
    assert not result.ok
    assert any("missing docs page" in e for e in result.errors)


def test_allowlist_skips_package(fake_repo, monkeypatch):
    """Packages in PACKAGE_ALLOWLIST do not require a docs page."""
    _, pkg_root, _ = fake_repo
    _make_pkg(pkg_root, "foo")
    monkeypatch.setattr(
        check_docs_coverage, "PACKAGE_ALLOWLIST", frozenset({"agrogame.foo"})
    )
    result = check_docs_coverage.run()
    assert result.ok, result.errors
    assert result.packages_required == 0


def test_invalid_frontmatter_fails(fake_repo):
    """Frontmatter that doesn't match the schema fails the gate."""
    _, pkg_root, docs_root = fake_repo
    docs_url = "https://github.com/gedejong/agrogame/blob/main/docs/foo.md"
    _make_pkg(
        pkg_root,
        "foo",
        init_body=f'"""\nDocs: {docs_url}\n"""\n',
    )
    # Missing required `doc_type` field
    (docs_root / "foo.md").write_text("---\nmodule: agrogame.foo\n---\nBody.\n")
    result = check_docs_coverage.run()
    assert not result.ok
    assert any("frontmatter invalid" in e for e in result.errors)


def test_key_classes_must_be_importable(fake_repo, monkeypatch):
    """A `key_classes` entry that doesn't exist on the module is an error."""
    tmp_path, pkg_root, docs_root = fake_repo
    init = textwrap.dedent(
        '''\
        """foo.

        Docs: https://github.com/gedejong/agrogame/blob/main/docs/foo.md
        """
        class Real:
            pass
        '''
    )
    _make_pkg(pkg_root, "foo", init_body=init)
    _make_doc(
        docs_root,
        "foo.md",
        module="agrogame.foo",
        extra_frontmatter={"key_classes": ["Real", "Imaginary"]},
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    # Drop any cached module so importlib loads our fake one.
    sys.modules.pop("agrogame", None)
    sys.modules.pop("agrogame.foo", None)
    try:
        result = check_docs_coverage.run()
    finally:
        sys.modules.pop("agrogame.foo", None)
        sys.modules.pop("agrogame", None)
    assert not result.ok
    assert any("Imaginary" in e for e in result.errors)


def test_init_must_contain_absolute_url(fake_repo):
    """An `__init__.py` docstring without the absolute docs URL fails."""
    _, pkg_root, docs_root = fake_repo
    _make_pkg(pkg_root, "foo", init_body='"""no link here."""\n')
    _make_doc(docs_root, "foo.md", module="agrogame.foo")
    result = check_docs_coverage.run()
    assert not result.ok
    assert any("absolute docs URL" in e for e in result.errors)


def test_duplicate_module_binding_fails(fake_repo):
    """Two docs pages declaring the same `module` is a hard error."""
    _, pkg_root, docs_root = fake_repo
    init = textwrap.dedent(
        '''\
        """foo.

        Docs: https://github.com/gedejong/agrogame/blob/main/docs/foo.md
        """
        '''
    )
    _make_pkg(pkg_root, "foo", init_body=init)
    _make_doc(docs_root, "foo.md", module="agrogame.foo")
    _make_doc(docs_root, "foo-alt.md", module="agrogame.foo")
    result = check_docs_coverage.run()
    assert not result.ok
    assert any("already documented" in e for e in result.errors)


def test_package_filter_restricts_scope(fake_repo):
    """`--package` filter narrows the gate to a single module."""
    _, pkg_root, docs_root = fake_repo
    init = textwrap.dedent(
        '''\
        """foo.

        Docs: https://github.com/gedejong/agrogame/blob/main/docs/foo.md
        """
        '''
    )
    _make_pkg(pkg_root, "foo", init_body=init)
    _make_pkg(pkg_root, "bar")  # has no docs — would normally fail
    _make_doc(docs_root, "foo.md", module="agrogame.foo")
    result = check_docs_coverage.run(only="agrogame.foo")
    assert result.ok, result.errors
    assert result.packages_required == 1


def test_package_filter_rejects_unknown(fake_repo):
    """`--package` with a non-existent / allowlisted package raises."""
    _, pkg_root, _ = fake_repo
    _make_pkg(pkg_root, "foo")
    with pytest.raises(SystemExit):
        check_docs_coverage.run(only="agrogame.does_not_exist")


def test_real_repo_passes():
    """The check passes against the live repo state."""
    result = check_docs_coverage.run()
    assert result.ok, "\n".join(result.errors)
    assert result.packages_required >= 8


def test_schema_validates_example_frontmatter():
    """The schema accepts the canonical example frontmatter from the AC."""
    schema_path = ROOT / "docs" / "knowledge-base-schema.json"
    schema = json.loads(schema_path.read_text())
    from jsonschema import Draft7Validator

    validator = Draft7Validator(schema)
    example = {
        "module": "agrogame.soil.water",
        "doc_type": "module",
        "references": ["FAO-56 (Allen et al. 1998), §3"],
        "key_classes": ["WaterParams", "WaterState", "WaterModule", "WaterRuntime"],
        "key_events": ["WaterStateUpdated", "WaterStressComputed"],
        "primary_tests": [
            "tests/soil/water/",
            "tests/integration/test_realism.py::test_water_balance",
        ],
        "related_adrs": ["ADR-002", "ADR-006"],
    }
    errors = list(validator.iter_errors(example))
    assert errors == []
