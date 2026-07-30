from __future__ import annotations

import json
from pathlib import Path

from apkg_lint.cli import main
from scripts.build_examples import build_broken_legacy, build_clean_modern


def test_clean_broken_and_implicit_commands(tmp_path: Path, capsys) -> None:
    clean = tmp_path / "clean.apkg"
    broken = tmp_path / "broken.apkg"
    build_clean_modern(clean)
    build_broken_legacy(broken)

    assert main(["check", str(clean), "--no-color"]) == 0
    assert "PASS" in capsys.readouterr().out
    assert main([str(clean), "--no-color"]) == 0
    assert "PASS" in capsys.readouterr().out
    assert main(["check", str(broken), "--no-color"]) == 1
    assert "NOTE001" in capsys.readouterr().out
    assert (
        main(
            [
                "check",
                str(broken),
                "--profile",
                "backup",
                "--fail-on",
                "none",
                "--no-color",
            ]
        )
        == 0
    )


def test_directory_json_and_html_output(tmp_path: Path, capsys) -> None:
    folder = tmp_path / "decks"
    folder.mkdir()
    build_clean_modern(folder / "clean.apkg")
    build_broken_legacy(folder / "broken.apkg")
    assert main(["check", str(folder), "--format", "json", "--fail-on", "none"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["files"] == 2

    output = tmp_path / "reports" / "report.html"
    assert (
        main(
            [
                "check",
                str(folder / "clean.apkg"),
                "--format",
                "html",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert "Deck preflight." in output.read_text(encoding="utf-8")


def test_rules_json(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["rules", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["rules"]


def test_operational_and_configuration_errors(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "missing.apkg"
    assert main(["check", str(missing), "--format", "json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["operational_errors"] == 1

    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["check", str(empty)]) == 2
    assert "no .apkg files found" in capsys.readouterr().err

    config = tmp_path / "bad.toml"
    config.write_text("[apkg_lint]\nprofile='invalid'\n", encoding="utf-8")
    assert main(["check", str(missing), "--config", str(config)]) == 2
    assert "invalid configuration" in capsys.readouterr().err


def test_default_config_is_discovered(tmp_path: Path, capsys, monkeypatch) -> None:
    broken = tmp_path / "broken.apkg"
    build_broken_legacy(broken)
    (tmp_path / "apkg-lint.toml").write_text(
        "[apkg_lint]\nprofile='backup'\nfail_on='none'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert main(["check", str(broken), "--no-color"]) == 0
    assert "SHARE001" not in capsys.readouterr().out


def test_report_write_failure_returns_two(tmp_path: Path, capsys) -> None:
    clean = tmp_path / "clean.apkg"
    build_clean_modern(clean)
    output_directory = tmp_path / "output"
    output_directory.mkdir()
    assert (
        main(
            [
                "check",
                str(clean),
                "--output",
                str(output_directory),
            ]
        )
        == 2
    )
    assert "could not write report" in capsys.readouterr().err
