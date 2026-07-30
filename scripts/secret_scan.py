"""Small dependency-free secret scan for release gating."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".html",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "generic bearer token": re.compile(
        r"(?i)\b(?:authorization|token)\s*[:=]\s*['\"]?bearer\s+[A-Za-z0-9._~+/=-]{20,}"
    ),
}


def _candidate_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "ls-files", "-z"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if result.returncode == 0 and result.stdout:
        relative = [item.decode("utf-8") for item in result.stdout.split(b"\x00") if item]
        return [ROOT / item for item in relative]
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and ".venv" not in path.parts
        and ".git" not in path.parts
        and path.suffix.lower() in TEXT_SUFFIXES
    ]


def main() -> int:
    findings: list[str] = []
    scanned = 0
    for path in _candidate_paths():
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{path.relative_to(ROOT)}: {label}")
    if findings:
        raise RuntimeError("possible secrets found:\n" + "\n".join(findings))
    print(f"Secret scan passed: {scanned} text files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
