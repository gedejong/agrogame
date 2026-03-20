from __future__ import annotations

from pathlib import Path

from agrogame.config.cli import main


def test_cli_validate_crop_ok(capsys):
    code = main(["validate", "crop", "data/samples/crops.yaml"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Validation OK" in out


def test_cli_build_writes_output(tmp_path: Path, capsys):
    out = tmp_path / "built.yaml"
    code = main(["build", "crop", str(out), "data/samples/crops.yaml"])
    assert code == 0
    assert out.exists()
    assert "built from:" in out.read_text()
    # ensure YAML marker present
    assert "---\n" in out.read_text()
