import io
import json
import subprocess
import sys

import pytest

from piimask.cli import main

TEXT = "Contact jane.doe@example.com or 07700 900123 about NHS number 943 476 5919."


def run(argv, stdin, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    return main(argv)


def test_scan_counts_and_exit_codes(monkeypatch, capsys):
    assert run(["scan"], TEXT, monkeypatch) == 1
    out = json.loads(capsys.readouterr().out)
    assert out == {"found": 3, "counts": {"EMAIL": 1, "UK_PHONE": 1, "NHS_NUMBER": 1}}
    assert "jane" not in json.dumps(out)  # scan never prints the values
    assert run(["scan"], "nothing personal here", monkeypatch) == 0


def test_mask_json(monkeypatch, capsys):
    assert run(["mask", "--json"], TEXT, monkeypatch) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["text"] == "Contact <EMAIL_1> or <UK_PHONE_1> about NHS number <NHS_NUMBER_1>."
    assert out["counts"] == {"EMAIL": 1, "UK_PHONE": 1, "NHS_NUMBER": 1}


def test_mask_then_restore_with_files(tmp_path, capsys):
    source = tmp_path / "in.txt"
    source.write_text(TEXT, encoding="utf-8")
    mapping = tmp_path / "mapping.json"
    assert main(["mask", str(source), "--mapping-out", str(mapping)]) == 0
    masked = tmp_path / "masked.txt"
    masked.write_text(capsys.readouterr().out, encoding="utf-8")
    assert "07700" not in masked.read_text(encoding="utf-8")
    assert main(["restore", str(masked), "--mapping", str(mapping)]) == 0
    assert capsys.readouterr().out == TEXT


def test_unknown_kind_is_a_usage_error(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        run(["scan", "--kinds", "email,passport"], TEXT, monkeypatch)
    assert exc.value.code == 2
    assert "PASSPORT" in capsys.readouterr().err


def test_python_dash_m():
    result = subprocess.run([sys.executable, "-m", "piimask", "--version"], capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout.startswith("piimask ")
