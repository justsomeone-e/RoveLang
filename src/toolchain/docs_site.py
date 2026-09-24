"""Rebuild the static site's real WASM artifacts from their Rove sources."""
from pathlib import Path
import hashlib
import json
import shutil

from src.cli import cmd_bundle

ROOT = Path(__file__).resolve().parents[2]


def _artifact_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix in (".d", ".ts", ".mjs", ".js", ".rove", ".wat", ".json", ".html", ".css", ".md"):
        return data.replace(b"\r\n", b"\n")
    return data


def build_site():
    docs = ROOT / "docs"
    artifacts = []
    for name, source in (
        ("metrics", ROOT / "examples/metrics/metrics.rove"),
        ("pong", ROOT / "examples/web_pong/pong.rove"),
    ):
        output = docs / "generated" / name
        if cmd_bundle(str(source), str(output), emit_package=True) != 0:
            raise RuntimeError(f"Failed to bundle {source.name}")
        (output / source.name).write_bytes(_artifact_bytes(source))
        for path in sorted(output.iterdir()):
            if path.is_file():
                norm = _artifact_bytes(path)
                if norm != path.read_bytes():
                    path.write_bytes(norm)
                artifacts.append({"path": path.relative_to(docs).as_posix(), "sha256": hashlib.sha256(norm).hexdigest()})
    examples = docs / "examples/metrics"
    examples.mkdir(parents=True, exist_ok=True)
    for filename in ("README.md", "metrics.rove", "cli.rove", "use_metrics.mjs", "use_metrics.py"):
        src_p = ROOT / "examples/metrics" / filename
        (examples / filename).write_bytes(_artifact_bytes(src_p))
    manifest_text = json.dumps({
        "compilerVersion": (ROOT / "VERSION").read_text().strip(),
        "rebuild": "python -m src.toolchain.docs_site",
        "artifacts": artifacts,
    }, indent=2) + "\n"
    (docs / "generated/manifest.json").write_bytes(manifest_text.encode("utf-8"))


if __name__ == "__main__":
    build_site()
