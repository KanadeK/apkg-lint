"""Configuration loading and command-line override handling."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from apkg_lint.model import Severity


@dataclass(frozen=True)
class Limits:
    max_members: int = 100_000
    max_uncompressed_bytes: int = 4 * 1024 * 1024 * 1024
    max_database_bytes: int = 2 * 1024 * 1024 * 1024
    max_control_bytes: int = 64 * 1024 * 1024
    max_compression_ratio: float = 1_000.0


@dataclass(frozen=True)
class Settings:
    profile: str = "shared"
    fail_on: Severity | None = Severity.WARNING
    ignored_rules: frozenset[str] = frozenset()
    severity_overrides: dict[str, Severity] = field(default_factory=dict)
    verify_media: bool = True
    limits: Limits = Limits()

    def with_overrides(
        self,
        *,
        profile: str | None = None,
        fail_on: Severity | object | None = ...,
        verify_media: bool | None = None,
    ) -> Settings:
        updates: dict[str, Any] = {}
        if profile is not None:
            updates["profile"] = profile
        if fail_on is not ...:
            updates["fail_on"] = fail_on
        if verify_media is not None:
            updates["verify_media"] = verify_media
        return replace(self, **updates)


def _positive_int(value: Any, key: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{key} must be a positive integer")
    return value


def _positive_number(value: Any, key: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{key} must be a positive number")
    return float(value)


def load_settings(path: Path | None) -> Settings:
    if path is None:
        return Settings()
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    allowed_top = {"apkg_lint", "severity", "limits"}
    unknown_top = set(raw) - allowed_top
    if unknown_top:
        raise ValueError(f"unknown config sections: {', '.join(sorted(unknown_top))}")

    core = raw.get("apkg_lint", {})
    if not isinstance(core, dict):
        raise ValueError("[apkg_lint] must be a table")
    allowed_core = {"profile", "fail_on", "ignore", "verify_media"}
    unknown_core = set(core) - allowed_core
    if unknown_core:
        raise ValueError(f"unknown apkg_lint keys: {', '.join(sorted(unknown_core))}")
    profile = core.get("profile", "shared")
    if profile not in {"shared", "backup"}:
        raise ValueError("profile must be 'shared' or 'backup'")
    fail_value = core.get("fail_on", "warning")
    fail_on = None if fail_value == "none" else Severity.parse(str(fail_value))
    ignored = core.get("ignore", [])
    if not isinstance(ignored, list) or not all(isinstance(item, str) for item in ignored):
        raise ValueError("apkg_lint.ignore must be an array of rule IDs")
    verify_media = core.get("verify_media", True)
    if not isinstance(verify_media, bool):
        raise ValueError("apkg_lint.verify_media must be true or false")

    severity_raw = raw.get("severity", {})
    if not isinstance(severity_raw, dict):
        raise ValueError("[severity] must be a table")
    severity_overrides = {
        str(rule_id).upper(): Severity.parse(str(value)) for rule_id, value in severity_raw.items()
    }

    limits_raw = raw.get("limits", {})
    if not isinstance(limits_raw, dict):
        raise ValueError("[limits] must be a table")
    allowed_limits = {
        "max_members",
        "max_uncompressed_mb",
        "max_database_mb",
        "max_control_mb",
        "max_compression_ratio",
    }
    unknown_limits = set(limits_raw) - allowed_limits
    if unknown_limits:
        raise ValueError(f"unknown limits keys: {', '.join(sorted(unknown_limits))}")
    mib = 1024 * 1024
    defaults = Limits()
    limits = Limits(
        max_members=_positive_int(
            limits_raw.get("max_members", defaults.max_members), "limits.max_members"
        ),
        max_uncompressed_bytes=_positive_int(
            limits_raw.get("max_uncompressed_mb", defaults.max_uncompressed_bytes // mib),
            "limits.max_uncompressed_mb",
        )
        * mib,
        max_database_bytes=_positive_int(
            limits_raw.get("max_database_mb", defaults.max_database_bytes // mib),
            "limits.max_database_mb",
        )
        * mib,
        max_control_bytes=_positive_int(
            limits_raw.get("max_control_mb", defaults.max_control_bytes // mib),
            "limits.max_control_mb",
        )
        * mib,
        max_compression_ratio=_positive_number(
            limits_raw.get("max_compression_ratio", defaults.max_compression_ratio),
            "limits.max_compression_ratio",
        ),
    )
    return Settings(
        profile=profile,
        fail_on=fail_on,
        ignored_rules=frozenset(item.upper() for item in ignored),
        severity_overrides=severity_overrides,
        verify_media=verify_media,
        limits=limits,
    )
