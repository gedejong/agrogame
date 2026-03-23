import pytest

from agrogame.cli import main


def test_cli_main_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    code = main()
    out = capsys.readouterr().out
    assert code == 0
    assert "AgroGame simulation CLI stub" in out
