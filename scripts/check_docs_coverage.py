#!/usr/bin/env python3
"""Verify the LLM-navigable knowledge base for #295.

Gate enforced on CI:
- every package directly under ``agrogame/`` (minus an explicit allowlist) has
  a corresponding markdown page under ``docs/`` with valid frontmatter;
- every frontmatter binds to an importable ``agrogame`` module and lists
  ``key_classes`` that exist as public symbols on that module;
- every required package's ``__init__.py`` docstring contains an absolute
  GitHub URL pointing at its docs page.

The script is intentionally dependency-light — only ``pyyaml`` (for frontmatter
parsing) and ``jsonschema`` (for schema validation) are required, both of which
are already in the project's main dependencies.

Usage:
    poetry run python scripts/check_docs_coverage.py
    poetry run python scripts/check_docs_coverage.py --package agrogame.events
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml
from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parent.parent
PKG_ROOT = ROOT / "agrogame"
DOCS_ROOT = ROOT / "docs"
SCHEMA_PATH = DOCS_ROOT / "knowledge-base-schema.json"
GITHUB_URL_BASE = "https://github.com/gedejong/agrogame/blob/main/docs/"

# Packages directly under agrogame/ that are exempt from the docs-page gate.
# Justified in docs/conventions.md (KB allowlist policy).
PACKAGE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "agrogame.analysis",
        "agrogame.config",
        "agrogame.dashboard",
        "agrogame.params",
        "agrogame.plots",
    }
)

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class DocPage:
    """A markdown page with parsed frontmatter."""

    path: Path
    frontmatter: dict
    body: str


@dataclass
class CheckResult:
    """Aggregated outcome of a documentation-coverage scan."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pages_seen: int = 0
    packages_required: int = 0

    def fail(self, msg: str) -> None:
        """Record a hard failure (exits non-zero)."""
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        """Record a soft warning (visible but does not fail)."""
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        """True iff no errors were recorded."""
        return not self.errors


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter from a markdown file. Returns ({}, text) if none."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    raw = m.group(1)
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML frontmatter: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    return data, text[m.end() :]


def _iter_required_packages() -> Iterable[str]:
    """Yield dotted module names of packages directly under agrogame/.

    Excludes the agrogame top-level package itself, leaf modules
    (like ``cli.py``), and any package in PACKAGE_ALLOWLIST.
    """
    for child in sorted(PKG_ROOT.iterdir()):
        if not child.is_dir():
            continue
        if not (child / "__init__.py").exists():
            continue
        dotted = f"agrogame.{child.name}"
        if dotted in PACKAGE_ALLOWLIST:
            continue
        yield dotted


def _load_doc_pages() -> list[DocPage]:
    """Read every ``docs/**/*.md`` file and return the ones with frontmatter."""
    pages: list[DocPage] = []
    for md in sorted(DOCS_ROOT.rglob("*.md")):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            fm, body = _parse_frontmatter(text)
        except ValueError as exc:
            raise ValueError(f"{md.relative_to(ROOT)}: {exc}") from exc
        if fm:
            pages.append(DocPage(path=md, frontmatter=fm, body=body))
    return pages


def _load_schema() -> Draft7Validator:
    """Load the KB frontmatter JSON Schema as a Draft 7 validator."""
    with SCHEMA_PATH.open(encoding="utf-8") as fh:
        schema = json.load(fh)
    return Draft7Validator(schema)


def _validate_pages(
    pages: list[DocPage], validator: Draft7Validator, result: CheckResult
) -> dict[str, DocPage]:
    """Validate each page against the schema; return module→page map."""
    by_module: dict[str, DocPage] = {}
    for page in pages:
        rel = page.path.relative_to(ROOT)
        errors = sorted(validator.iter_errors(page.frontmatter), key=lambda e: e.path)
        if errors:
            for err in errors:
                where = "/".join(str(p) for p in err.absolute_path) or "<root>"
                result.fail(f"{rel}: frontmatter invalid at {where}: {err.message}")
            continue
        module = page.frontmatter.get("module")
        if not isinstance(module, str):
            continue
        if module in by_module:
            other = by_module[module].path.relative_to(ROOT)
            result.fail(f"{rel}: module '{module}' already documented in {other}")
            continue
        by_module[module] = page
    return by_module


def _check_key_classes(page: DocPage, result: CheckResult) -> None:
    """Verify each ``key_classes`` entry is a public attribute of the module."""
    module_name = page.frontmatter["module"]
    classes = page.frontmatter.get("key_classes") or []
    if not classes:
        return
    try:
        mod = importlib.import_module(module_name)
    except ImportError as exc:
        result.fail(
            f"{page.path.relative_to(ROOT)}: cannot import {module_name!r} "
            f"to verify key_classes: {exc}"
        )
        return
    for cls in classes:
        if not hasattr(mod, cls):
            result.fail(
                f"{page.path.relative_to(ROOT)}: key_classes entry '{cls}' "
                f"is not exported by {module_name}"
            )


def _expected_doc_url(page: DocPage) -> str:
    """Return the canonical absolute GitHub URL for a docs page."""
    rel = page.path.relative_to(DOCS_ROOT).as_posix()
    return f"{GITHUB_URL_BASE}{rel}"


def _check_init_link(module_name: str, page: DocPage, result: CheckResult) -> None:
    """Verify the package's ``__init__.py`` docstring links to its docs page."""
    rel_pkg = module_name.replace("agrogame.", "agrogame/", 1).replace(".", "/")
    init_path = ROOT / rel_pkg / "__init__.py"
    if not init_path.exists():
        result.fail(f"{module_name}: expected {init_path.relative_to(ROOT)} to exist")
        return
    try:
        text = init_path.read_text(encoding="utf-8")
    except OSError as exc:
        result.fail(f"{init_path.relative_to(ROOT)}: cannot read: {exc}")
        return
    expected_url = _expected_doc_url(page)
    if expected_url not in text:
        result.fail(
            f"{init_path.relative_to(ROOT)}: top-of-file docstring must contain "
            f"absolute docs URL '{expected_url}'"
        )


def _filter_packages(packages: Iterable[str], only: str | None) -> list[str]:
    """Restrict to a single package when --package is supplied."""
    pkgs = list(packages)
    if only is None:
        return pkgs
    if only not in pkgs:
        raise SystemExit(
            f"--package {only!r} is not a required agrogame package "
            f"(or is in the allowlist). Required: {', '.join(pkgs)}"
        )
    return [only]


def run(only: str | None = None) -> CheckResult:
    """Run all checks and return an aggregated result."""
    result = CheckResult()
    if not SCHEMA_PATH.exists():
        result.fail(f"missing KB schema at {SCHEMA_PATH.relative_to(ROOT)}")
        return result
    validator = _load_schema()

    try:
        pages = _load_doc_pages()
    except ValueError as exc:
        result.fail(str(exc))
        return result
    result.pages_seen = len(pages)

    by_module = _validate_pages(pages, validator, result)

    required = _filter_packages(_iter_required_packages(), only)
    result.packages_required = len(required)

    for module_name in required:
        page = by_module.get(module_name)
        if page is None:
            result.fail(
                f"{module_name}: missing docs page with frontmatter "
                f"`module: {module_name}` (allowlist via PACKAGE_ALLOWLIST in "
                f"this script if intentional)"
            )
            continue
        _check_key_classes(page, result)
        _check_init_link(module_name, page, result)

    # Run key_classes check on every frontmatter page so non-required pages
    # (e.g. sub-package seed pages) are still validated.
    for module_name, page in by_module.items():
        if module_name in required:
            continue  # already checked
        _check_key_classes(page, result)

    return result


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package",
        help="Restrict to a single agrogame.<pkg>; useful for debugging.",
    )
    args = parser.parse_args()

    result = run(only=args.package)

    for w in result.warnings:
        print(f"warning: {w}", file=sys.stderr)
    for e in result.errors:
        print(f"error: {e}", file=sys.stderr)
    print(
        f"checked {result.pages_seen} doc pages against "
        f"{result.packages_required} required packages"
    )
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
