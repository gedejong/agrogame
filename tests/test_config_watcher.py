from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from agrogame.config.watcher import _Handler
from agrogame.config.cli import main


def test_handler_filters_extensions(tmp_path: Path):
    seen: list[Path] = []

    def on_change(paths: list[Path]) -> None:
        seen.extend(paths)

    h = _Handler(on_change, {".yaml", ".json"})
    # Directory event ignored
    h.on_any_event(SimpleNamespace(is_directory=True, src_path=str(tmp_path / "d")))
    # Non-matching extension ignored
    h.on_any_event(
        SimpleNamespace(is_directory=False, src_path=str(tmp_path / "a.txt"))
    )
    # Matching extension triggers
    y = tmp_path / "a.yaml"
    h.on_any_event(SimpleNamespace(is_directory=False, src_path=str(y)))

    assert seen == [y]


def test_cli_wizard(capsys):
    code = main(["wizard"])  # placeholder implementation
    out = capsys.readouterr().out
    assert code == 0
    assert "Interactive builder" in out
