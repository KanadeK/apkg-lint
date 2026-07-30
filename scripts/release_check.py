"""Final source, history, reproducibility, and clean-install gate."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import venv
import zipfile
from pathlib import Path

from apkg_lint import __version__

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
EXPECTED_NAME = "KanadeK"
EXPECTED_EMAIL = "121669563+KanadeK@users.noreply.github.com"
GIT = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
REQUIRED_FILES = {
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    ".github/workflows/security.yml",
    "README.md",
    "README.zh-CN.md",
    "LICENSE",
    "CHANGELOG.md",
    "RELEASE_NOTES.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "docs/ACCEPTANCE.md",
    "docs/ARCHITECTURE.md",
    "docs/FORMAT_SUPPORT.md",
    "docs/RESEARCH.md",
    "docs/RULES.md",
    "docs/TROUBLESHOOTING.md",
    "action.yml",
}
_PLACEHOLDER_WORDS = (
    "T" + "BD",
    "T" + "ODO",
    "FIX" + "ME",
    "CHANGE" + "ME",
)
PLACEHOLDERS = re.compile(
    rf"\b(?:{'|'.join(_PLACEHOLDER_WORDS)})\b|example[.]com",
    re.IGNORECASE,
)


def _run(
    command: list[str],
    *,
    capture: bool = False,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        errors="replace",
        capture_output=capture,
        env=environment,
    )


def _capture_git(arguments: list[str]) -> str:
    return _run([*GIT, *arguments], capture=True).stdout.strip()


def _hashes() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(RELEASE.iterdir())
        if path.is_file()
    }


def _check_metadata() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    if project["version"] != __version__:
        raise RuntimeError("pyproject version and package version differ")
    missing = sorted(relative for relative in REQUIRED_FILES if not (ROOT / relative).is_file())
    if missing:
        raise RuntimeError(f"required release files are missing: {missing}")
    tracked = _capture_git(["ls-files", "-z"]).split("\x00")
    for relative in tracked:
        if not relative:
            continue
        path = ROOT / relative
        if path.suffix.lower() not in {".md", ".py", ".toml", ".yaml", ".yml"}:
            continue
        match = PLACEHOLDERS.search(path.read_text(encoding="utf-8"))
        if match:
            raise RuntimeError(f"unfinished placeholder {match.group(0)!r} in {relative}")


def _check_history(*, allow_dirty: bool) -> None:
    status = _capture_git(["status", "--porcelain=v1"])
    if status and not allow_dirty:
        raise RuntimeError(f"working tree is not clean:\n{status}")
    identity = _capture_git(["log", "-1", "--format=%an%x00%ae%x00%cn%x00%ce"]).split("\x00")
    expected = [EXPECTED_NAME, EXPECTED_EMAIL, EXPECTED_NAME, EXPECTED_EMAIL]
    if identity != expected:
        raise RuntimeError(f"unexpected HEAD author/committer: {identity}")
    history = _capture_git(["log", "--format=%B"])
    if re.search(r"(?im)^Co-authored-by:", history):
        raise RuntimeError("Co-authored-by trailer found in repository history")
    shortlog = _capture_git(["shortlog", "-sne", "HEAD"])
    if EXPECTED_NAME not in shortlog or EXPECTED_EMAIL not in shortlog:
        raise RuntimeError(f"unexpected contributor shortlog: {shortlog}")
    print(f"Git hygiene passed: {shortlog}")


def _check_wheel() -> Path:
    wheel = RELEASE / f"apkg_lint-{__version__}-py3-none-any.whl"
    if not wheel.is_file():
        raise RuntimeError(f"wheel is missing: {wheel.name}")
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    required = {
        "apkg_lint/__init__.py",
        "apkg_lint/cli.py",
        "apkg_lint/package.py",
        "apkg_lint/rules.py",
    }
    if not required <= names:
        raise RuntimeError(f"wheel is missing package files: {sorted(required - names)}")
    return wheel


def _check_dependencies() -> None:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    _run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "--skip-editable",
            "--progress-spinner",
            "off",
        ],
        environment=environment,
    )


def _clean_install(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="apkg-lint-wheel-") as temporary:
        environment = Path(temporary) / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = (
            environment / "Scripts" / "python.exe"
            if sys.platform == "win32"
            else environment / "bin" / "python"
        )
        _run([str(python), "-m", "pip", "install", str(wheel)])
        version = _run(
            [str(python), "-m", "apkg_lint", "--version"],
            capture=True,
        ).stdout.strip()
        if version != f"apkg-lint {__version__}":
            raise RuntimeError(f"clean install reported unexpected version: {version}")
        _run(
            [
                str(python),
                "-m",
                "apkg_lint",
                "check",
                "examples/clean-modern.apkg",
                "--fail-on",
                "warning",
                "--no-color",
            ]
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="development-only: permit uncommitted files",
    )
    parser.add_argument(
        "--skip-clean-install",
        action="store_true",
        help="development-only: skip the isolated wheel installation",
    )
    args = parser.parse_args()
    if os.environ.get("GITHUB_REF_TYPE") == "tag":
        expected_tag = f"v{__version__}"
        if os.environ.get("GITHUB_REF_NAME") != expected_tag:
            raise RuntimeError(f"release tag must be {expected_tag}")
    _check_metadata()
    _check_history(allow_dirty=args.allow_dirty)
    _check_dependencies()
    _run([sys.executable, "scripts/verify.py"])
    _run([sys.executable, "scripts/package_release.py"])
    first = _hashes()
    _run([sys.executable, "scripts/package_release.py"])
    second = _hashes()
    if first != second:
        changed = {
            name: {"first": first.get(name), "second": second.get(name)}
            for name in sorted(first.keys() | second.keys())
            if first.get(name) != second.get(name)
        }
        raise RuntimeError(f"release assets are not reproducible: {changed}")
    wheel = _check_wheel()
    if not args.skip_clean_install:
        _clean_install(wheel)
    print(
        f"Release check passed: v{__version__}, {len(second)} reproducible files, "
        "clean history and install."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
