"""Run the complete local quality gate."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], *, expected: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        text=True,
        errors="replace",
        capture_output=True,
    )
    if result.returncode != expected:
        raise RuntimeError(
            f"command returned {result.returncode}, expected {expected}: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result


def main() -> int:
    python = sys.executable
    _run([python, "-m", "ruff", "format", "--check", "."])
    _run([python, "-m", "ruff", "check", "."])
    _run([python, "-m", "mypy", "src", "scripts"])
    with tempfile.TemporaryDirectory(prefix=".apkg-lint-pytest-", dir=ROOT) as pytest_temp:
        _run(
            [
                python,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "--basetemp",
                pytest_temp,
                "--cov=apkg_lint",
                "--cov-report=term-missing",
                "--cov-report=xml",
            ]
        )
    _run([python, "scripts/build_examples.py", "--check"])
    _run(
        [
            python,
            "-m",
            "apkg_lint",
            "check",
            "examples/clean-modern.apkg",
            "--fail-on",
            "warning",
            "--no-color",
        ]
    )
    _run(
        [
            python,
            "-m",
            "apkg_lint",
            "check",
            "examples/broken-legacy.apkg",
            "--no-color",
        ],
        expected=1,
    )
    with tempfile.TemporaryDirectory(prefix="apkg-lint-verify-") as temporary:
        report_path = Path(temporary) / "report.json"
        _run(
            [
                python,
                "-m",
                "apkg_lint",
                "check",
                "examples/clean-modern.apkg",
                "--format",
                "json",
                "--output",
                str(report_path),
            ]
        )
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        if payload["summary"] != {
            "error": 0,
            "files": 1,
            "info": 0,
            "operational_errors": 0,
            "warning": 0,
        }:
            raise RuntimeError(f"clean JSON smoke returned an unexpected summary: {payload}")
    _run([python, "scripts/secret_scan.py"])
    _run([python, "-m", "build", "--no-isolation"])
    print("Full verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
