from __future__ import annotations

from pathlib import Path

import pytest

from apkg_lint.config import Limits, load_settings
from apkg_lint.model import Severity


def test_default_settings_and_overrides() -> None:
    settings = load_settings(None)
    assert settings.profile == "shared"
    assert settings.fail_on is Severity.WARNING
    assert settings.verify_media is True
    overridden = settings.with_overrides(
        profile="backup",
        fail_on=None,
        verify_media=False,
    )
    assert overridden.profile == "backup"
    assert overridden.fail_on is None
    assert overridden.verify_media is False
    assert settings.profile == "shared"


def test_loads_complete_config(tmp_path: Path) -> None:
    path = tmp_path / "apkg-lint.toml"
    path.write_text(
        """
[apkg_lint]
profile = "backup"
fail_on = "error"
ignore = ["media006"]
verify_media = false

[severity]
note002 = "error"

[limits]
max_members = 42
max_uncompressed_mb = 16
max_database_mb = 8
max_control_mb = 2
max_compression_ratio = 25.5
""".strip(),
        encoding="utf-8",
    )
    settings = load_settings(path)
    assert settings.profile == "backup"
    assert settings.fail_on is Severity.ERROR
    assert settings.ignored_rules == frozenset({"MEDIA006"})
    assert settings.severity_overrides == {"NOTE002": Severity.ERROR}
    assert settings.verify_media is False
    assert settings.limits == Limits(
        max_members=42,
        max_uncompressed_bytes=16 * 1024 * 1024,
        max_database_bytes=8 * 1024 * 1024,
        max_control_bytes=2 * 1024 * 1024,
        max_compression_ratio=25.5,
    )


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[unknown]\na=1", "unknown config sections"),
        ("apkg_lint = 1", "must be a table"),
        ("[apkg_lint]\nwat = 1", "unknown apkg_lint keys"),
        ('[apkg_lint]\nprofile = "server"', "profile must be"),
        ('[apkg_lint]\nfail_on = "fatal"', "unknown severity"),
        ('[apkg_lint]\nignore = "X"', "must be an array"),
        ('[apkg_lint]\nverify_media = "yes"', "must be true or false"),
        ("severity = 1", "must be a table"),
        ("[severity]\nX = 2", "unknown severity"),
        ("limits = 1", "must be a table"),
        ("[limits]\nunknown = 1", "unknown limits keys"),
        ("[limits]\nmax_members = 0", "positive integer"),
        ('[limits]\nmax_compression_ratio = "many"', "positive number"),
    ],
)
def test_rejects_invalid_config(tmp_path: Path, text: str, message: str) -> None:
    path = tmp_path / "bad.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_settings(path)


def test_severity_parser_lists_choices() -> None:
    assert Severity.parse(" Warning ") is Severity.WARNING
    with pytest.raises(ValueError, match="choose one of"):
        Severity.parse("fatal")
