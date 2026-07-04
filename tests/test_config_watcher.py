from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest

from agrogame.config.watcher import _Handler
from agrogame.config.cli import main


def test_handler_filters_extensions(tmp_path: Path) -> None:
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


def test_cli_wizard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The `wizard` subcommand drives run_wizard over stdin/stdout."""
    import io

    out_path = tmp_path / "soil.yaml"
    # soil path, accept defaults, then supply the output path.
    script = "soil\n\n\n" + "\n" * 9 + f"{out_path}\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(script))
    code = main(["wizard"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Scaffold which config?" in out
    assert out_path.exists()
