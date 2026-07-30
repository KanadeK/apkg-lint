from __future__ import annotations

import json
from pathlib import Path

from apkg_lint.config import Settings
from apkg_lint.package import load_package
from apkg_lint.reporting import (
    render_html,
    render_json,
    render_rules_json,
    render_rules_text,
    render_sarif,
    render_text,
)
from apkg_lint.rules import RULES, audit
from scripts.build_examples import build_broken_legacy, build_clean_modern


def _reports(tmp_path: Path):
    clean_path = tmp_path / "clean.apkg"
    broken_path = tmp_path / "broken.apkg"
    build_clean_modern(clean_path)
    build_broken_legacy(broken_path)
    settings = Settings()
    return [
        audit(load_package(clean_path, settings), settings),
        audit(load_package(broken_path, settings), settings),
    ]


def test_text_report_includes_status_repairs_and_errors(tmp_path: Path) -> None:
    text = render_text(_reports(tmp_path), [("bad.apkg", "broken <zip>")], color=False)
    assert "PASS  clean.apkg" in text
    assert "FAIL  broken.apkg" in text
    assert "fix:" in text
    assert "Could not inspect package: broken <zip>" in text
    colored = render_text(_reports(tmp_path), [], color=True)
    assert "\033[" in colored


def test_json_report_is_stable_and_structured(tmp_path: Path) -> None:
    payload = json.loads(render_json(_reports(tmp_path), [("bad.apkg", "broken")]))
    assert payload["tool"]["name"] == "apkg-lint"
    assert payload["summary"]["files"] == 2
    assert payload["summary"]["operational_errors"] == 1
    assert payload["reports"][0]["source"] == "clean.apkg"
    assert payload["reports"][1]["findings"]


def test_html_report_is_standalone_and_escapes_errors(tmp_path: Path) -> None:
    html = render_html(_reports(tmp_path), [("<bad>.apkg", "<script>alert(1)</script>")])
    assert html.startswith("<!doctype html>")
    assert "Deck preflight." in html
    assert "&lt;script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "No findings. This package passed." in html


def test_sarif_contains_rules_and_results(tmp_path: Path) -> None:
    payload = json.loads(render_sarif(_reports(tmp_path), [("bad.apkg", "broken")]))
    run = payload["runs"][0]
    assert payload["version"] == "2.1.0"
    assert len(run["tool"]["driver"]["rules"]) == len(RULES) + 1
    assert any(result["ruleId"] == "APKG000" for result in run["results"])
    assert any(result["ruleId"] == "NOTE001" for result in run["results"])


def test_rule_catalog_reporters() -> None:
    text = render_rules_text()
    payload = json.loads(render_rules_json())
    assert "NOTE001" in text
    assert len(payload["rules"]) == len(RULES)
