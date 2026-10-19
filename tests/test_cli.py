import pandas as pd
import pytest

from datascope.cli import main


@pytest.fixture
def sample_csv(tmp_path):
    path = tmp_path / "data.csv"
    pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}).to_csv(path, index=False)
    return path


def test_cli_writes_report(sample_csv, tmp_path, monkeypatch, capsys):
    out = tmp_path / "out.html"
    monkeypatch.setattr("sys.argv", ["datascope", str(sample_csv), "-o", str(out)])
    main()
    assert out.exists()
    captured = capsys.readouterr()
    assert str(out) in captured.out


def test_cli_default_output_path(sample_csv, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["datascope", str(sample_csv)])
    main()
    assert (tmp_path / "data_profile_report.html").exists()


def test_cli_custom_name_and_sample_size(sample_csv, tmp_path, monkeypatch):
    out = tmp_path / "out.html"
    monkeypatch.setattr(
        "sys.argv",
        ["datascope", str(sample_csv), "-o", str(out), "--name", "my_dataset", "--sample-size", "50"],
    )
    main()
    assert out.exists()
