from pathlib import Path

from scripts.release_check import PLACEHOLDERS

ROOT = Path(__file__).resolve().parents[1]


def test_placeholder_scanner_detects_unfinished_content() -> None:
    for placeholder in ("T" + "BD", "T" + "ODO", "FIX" + "ME", "CHANGE" + "ME"):
        assert PLACEHOLDERS.search(f"release status: {placeholder}")
    assert PLACEHOLDERS.search("https://example" + ".com/project")


def test_placeholder_scanner_does_not_match_its_own_source() -> None:
    source = (ROOT / "scripts" / "release_check.py").read_text(encoding="utf-8")
    assert PLACEHOLDERS.search(source) is None
