from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable, List, Tuple

from pypdf import PdfReader


HEADING_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*chapter\s+\d+\b", re.IGNORECASE),
    re.compile(r"^\s*\d+\.?\s+[A-Z][A-Za-z ,\-]{5,}$"),
)


def _iter_page_texts(pdf_path: Path) -> Iterable[str]:
    reader = PdfReader(str(pdf_path))
    for page in reader.pages:
        yield page.extract_text() or ""


def _is_heading(line: str) -> bool:
    s = line.strip()
    if len(s) < 6:
        return False
    for pat in HEADING_PATTERNS:
        if pat.match(s):
            return True
    return False


def split_into_docs(pages: List[str], chunk_pages: int = 8) -> List[Tuple[str, str]]:
    """Split raw page texts into (title, markdown) documents.

    Heuristics: start a new doc on detected headings; otherwise split by chunk_pages.
    """
    docs: List[Tuple[str, str]] = []
    current_lines: List[str] = []
    current_title: str | None = None
    pages_since_split = 0

    for page in pages:
        pages_since_split += 1
        lines = page.splitlines()
        for line in lines:
            if _is_heading(line) and current_lines:
                # flush current
                title = current_title or "Section"
                docs.append((title.strip(), "\n".join(current_lines).strip()))
                current_lines = []
                current_title = line.strip()
                pages_since_split = 0
            elif current_title is None and _is_heading(line):
                current_title = line.strip()
            current_lines.append(line)
        # chunk split fallback
        if pages_since_split >= chunk_pages and current_lines:
            title = current_title or f"Section (pp~{len(docs) * chunk_pages + 1})"
            docs.append((title.strip(), "\n".join(current_lines).strip()))
            current_lines = []
            current_title = None
            pages_since_split = 0

    if current_lines:
        title = current_title or "Section (end)"
        docs.append((title.strip(), "\n".join(current_lines).strip()))
    return docs


def sanitize_title(title: str, index: int) -> Tuple[str, str]:
    safe = re.sub(r"[^A-Za-z0-9\- ]+", "", title)[:60].strip() or f"Section-{index:03d}"
    slug = re.sub(r"\s+", "-", safe).lower()
    return safe, slug


def write_docs(docs: List[Tuple[str, str]], out_dir: Path) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for i, (title, body) in enumerate(docs, start=1):
        safe, slug = sanitize_title(title, i)
        path = out_dir / f"{i:03d}-{slug}.md"
        content = f"### {safe}\n\n" + body + "\n"
        path.write_text(content)
        written.append(path)
    # index page
    index_md = [
        "### Soil Microbiology – Key Concepts",
        "",
        "Generated from PDF extraction.",
    ]
    for p in written:
        index_md.append(f"- [{p.stem[4:].replace('-', ' ').title()}](./{p.name})")
    (out_dir / "index.md").write_text("\n".join(index_md) + "\n")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract PDF to markdown chunks")
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--chunk-pages", type=int, default=8)
    args = parser.parse_args()

    pages = list(_iter_page_texts(args.pdf))
    docs = split_into_docs(pages, chunk_pages=max(1, int(args.chunk_pages)))
    written = write_docs(docs, args.out_dir)
    print(f"Wrote {len(written)} sections to {args.out_dir}")


if __name__ == "__main__":
    main()
