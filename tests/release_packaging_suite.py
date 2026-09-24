import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import zipfile


ROOT_DIR = Path(__file__).resolve().parent.parent
PACKAGER = ROOT_DIR / "tools" / "release_package.py"
TEST_TAG = f"v{(ROOT_DIR / 'VERSION').read_text(encoding='utf-8').strip()}"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _package(output: Path) -> None:
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = "1700000000"
    result = subprocess.run(
        [
            sys.executable,
            str(PACKAGER),
            "--root",
            str(ROOT_DIR),
            "--output",
            str(output),
            "--tag",
            TEST_TAG,
        ],
        cwd=ROOT_DIR,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def run_release_packaging_suite() -> bool:
    print("=" * 70)
    print("ROVE DETERMINISTIC RELEASE ARCHIVE CONTRACT")
    print("=" * 70)
    with tempfile.TemporaryDirectory(prefix="rove_release_package_") as directory:
        base = Path(directory)
        first = base / "first"
        second = base / "second"
        _package(first)
        _package(second)

        names = (
            f"rove-{TEST_TAG}-universal.zip",
            f"rove-{TEST_TAG}-source.tar.gz",
        )
        for name in names:
            assert _digest(first / name) == _digest(second / name), name

        prefix = f"rove-{TEST_TAG}/"
        with zipfile.ZipFile(first / names[0]) as archive:
            members = archive.infolist()
            member_names = [member.filename for member in members]
            assert member_names == sorted(member_names, key=lambda value: value.encode("utf-8"))
            assert all(name.startswith(prefix) and "\\" not in name for name in member_names)
            assert prefix + "README.md" in member_names
            assert prefix + "LICENSE" in member_names
            assert len({member.date_time for member in members}) == 1

        with tarfile.open(first / names[1], "r:gz") as archive:
            members = archive.getmembers()
            member_names = [member.name for member in members]
            assert member_names == sorted(member_names, key=lambda value: value.encode("utf-8"))
            assert all(name.startswith(prefix) and "\\" not in name for name in member_names)
            assert prefix + "compiler/main.rove" in member_names
            assert prefix + "LICENSE" in member_names
            assert all(member.uid == 0 and member.gid == 0 for member in members)
            assert len({member.mtime for member in members}) == 1

    print("[PASS] ZIP/TAR byte reproducibility, canonical blobs, paths, modes, owners, and timestamps")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_release_packaging_suite() else 1)
