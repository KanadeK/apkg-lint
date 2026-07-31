from pathlib import Path

import pytest

from scripts.release_check import PLACEHOLDERS, _validate_release_tag

ROOT = Path(__file__).resolve().parents[1]


def test_placeholder_scanner_detects_unfinished_content() -> None:
    for placeholder in ("T" + "BD", "T" + "ODO", "FIX" + "ME", "CHANGE" + "ME"):
        assert PLACEHOLDERS.search(f"release status: {placeholder}")
    assert PLACEHOLDERS.search("https://example" + ".com/project")


def test_placeholder_scanner_does_not_match_its_own_source() -> None:
    source = (ROOT / "scripts" / "release_check.py").read_text(encoding="utf-8")
    assert PLACEHOLDERS.search(source) is None


def test_release_tag_validation_accepts_manual_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RELEASE_TAG", "v0.1.0")
    _validate_release_tag()
    monkeypatch.setenv("RELEASE_TAG", "v9.9.9")
    with pytest.raises(RuntimeError, match=r"release tag must be v0\.1\.0"):
        _validate_release_tag()
