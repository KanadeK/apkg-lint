"""Command-line interface."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from apkg_lint import __version__
from apkg_lint.config import Settings, load_settings
from apkg_lint.model import AuditReport, Severity
from apkg_lint.package import PackageReadError, load_package
from apkg_lint.reporting import (
    OperationalError,
    render_html,
    render_json,
    render_rules_json,
    render_rules_text,
    render_sarif,
    render_text,
)
from apkg_lint.rules import audit


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="apkg-lint",
        description="Offline preflight and CI linting for Anki .apkg decks.",
    )
    parser.add_argument("--version", action="version", version=f"apkg-lint {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="inspect one or more APKG files")
    check.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="APKG file or directory; directories are searched recursively",
    )
    check.add_argument(
        "--config",
        type=Path,
        help="TOML configuration (default: ./apkg-lint.toml when present)",
    )
    check.add_argument("--profile", choices=["shared", "backup"])
    check.add_argument(
        "--fail-on",
        choices=["error", "warning", "info", "none"],
        help="minimum severity that returns exit code 1",
    )
    check.add_argument(
        "--no-verify-media",
        action="store_true",
        help="skip decompression/hash checks for media payloads",
    )
    check.add_argument(
        "--format",
        choices=["text", "json", "html", "sarif"],
        default="text",
        dest="output_format",
    )
    check.add_argument("-o", "--output", type=Path, help="write the report to this file")
    check.add_argument("--no-color", action="store_true", help="disable ANSI colors")

    rules = subparsers.add_parser("rules", help="list built-in rule metadata")
    rules.add_argument("--format", choices=["text", "json"], default="text")
    return parser


def _discover(paths: list[Path]) -> list[Path]:
    discovered: dict[str, Path] = {}
    for path in paths:
        expanded = path.expanduser()
        if expanded.is_dir():
            for candidate in expanded.rglob("*.apkg"):
                if candidate.is_file():
                    discovered[str(candidate.resolve()).casefold()] = candidate.resolve()
        else:
            discovered[str(expanded.resolve()).casefold()] = expanded.resolve()
    return [discovered[key] for key in sorted(discovered)]


def _fail_on(value: str | None, current: Severity | None) -> Severity | None:
    if value is None:
        return current
    if value == "none":
        return None
    return Severity.parse(value)


def _settings(args: argparse.Namespace) -> Settings:
    config_path = args.config
    default_config = Path("apkg-lint.toml")
    if config_path is None and default_config.is_file():
        config_path = default_config
    loaded = load_settings(config_path)
    return loaded.with_overrides(
        profile=args.profile,
        fail_on=_fail_on(args.fail_on, loaded.fail_on),
        verify_media=False if args.no_verify_media else None,
    )


def _render(
    output_format: str,
    reports: list[AuditReport],
    errors: list[OperationalError],
    *,
    color: bool,
) -> str:
    if output_format == "json":
        return render_json(reports, errors)
    if output_format == "html":
        return render_html(reports, errors)
    if output_format == "sarif":
        return render_sarif(reports, errors)
    return render_text(reports, errors, color=color)


def _write(content: str, output: Path | None) -> None:
    if output is None:
        sys.stdout.write(content)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")


def _check(args: argparse.Namespace) -> int:
    try:
        settings = _settings(args)
    except (OSError, ValueError) as exc:
        print(f"apkg-lint: invalid configuration: {exc}", file=sys.stderr)
        return 2
    paths = _discover(args.paths)
    if not paths:
        print("apkg-lint: no .apkg files found", file=sys.stderr)
        return 2

    reports: list[AuditReport] = []
    errors: list[OperationalError] = []
    for path in paths:
        try:
            reports.append(audit(load_package(path, settings), settings))
        except (OSError, PackageReadError) as exc:
            errors.append((path.name, str(exc)))

    color = (
        args.output_format == "text"
        and args.output is None
        and not args.no_color
        and "NO_COLOR" not in os.environ
        and sys.stdout.isatty()
    )
    try:
        _write(
            _render(args.output_format, reports, errors, color=color),
            args.output,
        )
    except OSError as exc:
        print(f"apkg-lint: could not write report: {exc}", file=sys.stderr)
        return 2
    if errors:
        return 2
    if settings.fail_on is not None and any(
        finding.severity >= settings.fail_on for report in reports for finding in report.findings
    ):
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if arguments and arguments[0] not in {"check", "rules", "-h", "--help", "--version"}:
        arguments.insert(0, "check")
    args = _parser().parse_args(arguments)
    if args.command == "rules":
        sys.stdout.write(render_rules_json() if args.format == "json" else render_rules_text())
        return 0
    return _check(args)
