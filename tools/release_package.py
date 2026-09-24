#!/usr/bin/env python3
"""Create deterministic Rove source archives from canonical Git blobs."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile
import time
import zipfile


TAG_PATTERN = re.compile(r"v[0-9A-Za-z]+(?:[._-][0-9A-Za-z]+)*\Z")
REGULAR_MODES = {"100644": 0o644, "100755": 0o755}


def _git(root: Path, *args: str, text: bool = False):
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=text,
        encoding="utf-8" if text else None,
    )
    return result.stdout


def _tracked_blobs(root: Path) -> list[tuple[str, int, bytes]]:
    records = _git(root, "ls-files", "--stage", "-z").split(b"\0")
    entries: list[tuple[str, int, str]] = []
    for record in records:
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_id, stage = metadata.decode("ascii").split()
        if stage != "0":
            raise RuntimeError("Release packaging requires an index without merge conflicts")
        if mode not in REGULAR_MODES:
            path = os.fsdecode(raw_path)
            raise RuntimeError(f"Unsupported Git entry mode {mode} for {path!r}")
        path = os.fsdecode(raw_path).replace("\\", "/")
        normalized = PurePosixPath(path)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise RuntimeError(f"Unsafe tracked release path: {path!r}")
        entries.append((normalized.as_posix(), REGULAR_MODES[mode], object_id))
    batch_input = b"".join(f"{object_id}\n".encode("ascii") for _, _, object_id in entries)
    result = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=root,
        input=batch_input,
        check=True,
        capture_output=True,
    )
    payload = result.stdout
    offset = 0
    files: list[tuple[str, int, bytes]] = []
    for path, mode, expected_id in entries:
        header_end = payload.find(b"\n", offset)
        if header_end < 0:
            raise RuntimeError("Truncated git cat-file batch header")
        object_id, object_type, raw_size = payload[offset:header_end].decode("ascii").split()
        if object_id != expected_id or object_type != "blob":
            raise RuntimeError(f"Unexpected Git object for {path!r}")
        size = int(raw_size)
        content_start = header_end + 1
        content_end = content_start + size
        if content_end >= len(payload) or payload[content_end:content_end + 1] != b"\n":
            raise RuntimeError(f"Truncated Git blob for {path!r}")
        files.append((path, mode, payload[content_start:content_end]))
        offset = content_end + 1
    if offset != len(payload):
        raise RuntimeError("Unexpected trailing data from git cat-file batch")
    files.sort(key=lambda item: item[0].encode("utf-8"))
    if not files:
        raise RuntimeError("No tracked files found for release packaging")
    return files


def _source_epoch(root: Path) -> int:
    configured = os.environ.get("SOURCE_DATE_EPOCH")
    value = configured or _git(root, "show", "-s", "--format=%ct", "HEAD", text=True).strip()
    epoch = int(value)
    if epoch < 0:
        raise ValueError("SOURCE_DATE_EPOCH must not be negative")
    return epoch


def _write_zip(path: Path, prefix: str, epoch: int, files: list[tuple[str, int, bytes]]) -> None:
    # ZIP timestamps start at 1980 and have two-second precision.
    zip_epoch = max(epoch, 315532800)
    timestamp = list(time.gmtime(zip_epoch)[:6])
    timestamp[5] -= timestamp[5] % 2
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED, strict_timestamps=True) as archive:
        for relative, mode, content in files:
            info = zipfile.ZipInfo(f"{prefix}/{relative}", tuple(timestamp))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.extra = b""
            info.comment = b""
            archive.writestr(info, content)


def _write_tar_gz(path: Path, prefix: str, epoch: int, files: list[tuple[str, int, bytes]]) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", compresslevel=9, fileobj=raw, mtime=epoch) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT) as archive:
                for relative, mode, content in files:
                    info = tarfile.TarInfo(f"{prefix}/{relative}")
                    info.size = len(content)
                    info.mode = mode
                    info.mtime = epoch
                    info.uid = 0
                    info.gid = 0
                    info.uname = "root"
                    info.gname = "root"
                    archive.addfile(info, fileobj=_BytesReader(content))


class _BytesReader:
    def __init__(self, value: bytes):
        self.value = value
        self.offset = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.value) - self.offset
        start = self.offset
        self.offset = min(len(self.value), self.offset + size)
        return self.value[start:self.offset]


def package(root: Path, output: Path, tag: str) -> tuple[Path, Path]:
    root = root.resolve()
    output = output.resolve()
    if not TAG_PATTERN.fullmatch(tag):
        raise ValueError(f"Invalid release tag {tag!r}")
    if not (root / ".git").exists():
        raise RuntimeError(f"Release root is not a Git checkout: {root}")
    output.mkdir(parents=True, exist_ok=True)
    files = _tracked_blobs(root)
    epoch = _source_epoch(root)
    prefix = f"rove-{tag}"
    zip_path = output / f"rove-{tag}-universal.zip"
    tar_path = output / f"rove-{tag}-source.tar.gz"
    _write_zip(zip_path, prefix, epoch, files)
    _write_tar_gz(tar_path, prefix, epoch, files)
    return zip_path, tar_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    archives = package(args.root, args.output, args.tag)
    for archive in archives:
        print(f"{_sha256(archive)}  {archive.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
