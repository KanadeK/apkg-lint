"""Build reproducible release artifacts and checksums."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from apkg_lint import __version__

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
RELEASE = ROOT / "release"
SOURCE_DATE_EPOCH = "1767225600"
ZIP_TIME = (2026, 1, 1, 0, 0, 0)
EXAMPLE_FILES = (
    "examples/clean-modern.apkg",
    "examples/broken-legacy.apkg",
    "examples/apkg-lint.toml",
    "examples/broken-report.json",
    "examples/broken-report.html",
    "examples/broken-report.sarif",
    "schema/apkg-lint-report-v1.schema.json",
    "docs/ACCEPTANCE.md",
    "docs/TROUBLESHOOTING.md",
)


def _reset_directory(path: Path) -> None:
    resolved = path.resolve()
    if resolved.parent != ROOT.resolve() or resolved.name not in {"dist", "release"}:
        raise RuntimeError(f"refusing to reset unexpected directory: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir()


def _zip_examples(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for relative in EXAMPLE_FILES:
            source = ROOT / relative
            if not source.is_file():
                raise RuntimeError(f"release input is missing: {relative}")
            info = zipfile.ZipInfo(f"apkg-lint-{__version__}/{relative}", ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(
                info,
                source.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    _reset_directory(DIST)
    _reset_directory(RELEASE)
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--outdir",
            str(DIST),
        ],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    expected = {
        f"apkg_lint-{__version__}-py3-none-any.whl",
        f"apkg_lint-{__version__}.tar.gz",
    }
    built = {path.name for path in DIST.iterdir() if path.is_file()}
    if built != expected:
        raise RuntimeError(f"unexpected build outputs: expected {expected}, got {built}")
    for source in DIST.iterdir():
        if source.is_file():
            shutil.copy2(source, RELEASE / source.name)
    _zip_examples(RELEASE / f"apkg-lint-{__version__}-examples.zip")
    shutil.copy2(
        ROOT / "schema" / "apkg-lint-report-v1.schema.json",
        RELEASE / "apkg-lint-report-v1.schema.json",
    )
    assets = sorted(path for path in RELEASE.iterdir() if path.is_file())
    checksums = "".join(f"{_sha256(path)}  {path.name}\n" for path in assets)
    (RELEASE / "SHA256SUMS").write_text(checksums, encoding="ascii", newline="\n")
    print(f"Built {len(assets)} release assets plus SHA256SUMS for v{__version__}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
