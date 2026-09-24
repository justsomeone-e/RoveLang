import json
import os
import re
import subprocess
import sys


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.self_host.bootstrap import _native_driver_source
from src.version import VERSION


def run_version_contract_suite() -> bool:
    print("=" * 70)
    print("ROVE SINGLE-SOURCE VERSION CONTRACT")
    print("=" * 70)
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?", VERSION)

    with open(os.path.join(ROOT_DIR, "VERSION"), encoding="utf-8") as handle:
        assert handle.read().strip() == VERSION
    with open(os.path.join(ROOT_DIR, "vscode-extension", "package.json"), encoding="utf-8") as handle:
        package = json.load(handle)
    with open(os.path.join(ROOT_DIR, "vscode-extension", "package-lock.json"), encoding="utf-8") as handle:
        package_lock = json.load(handle)
    assert package["version"] == VERSION
    assert package_lock["version"] == VERSION
    assert package_lock["packages"][""]["version"] == VERSION

    with open(os.path.join(ROOT_DIR, "compiler", "main.rove"), encoding="utf-8") as handle:
        assert f"Version: v{VERSION}" in handle.read()
    assert f'rovec {VERSION} (native self-host)' in _native_driver_source()

    with open(os.path.join(ROOT_DIR, "README.md"), encoding="utf-8") as handle:
        readme = handle.read()
    assert (f"`{VERSION}`" in readme) or (f"`v{VERSION}`" in readme)
    assert "v3.0.0" not in readme
    for animated_asset in (
        "terminal_animated.svg",
        "pipeline_animated.svg",
        "features_animated.svg",
    ):
        assert readme.count(animated_asset) == 1, animated_asset

    cli = subprocess.run(
        [sys.executable, os.path.join(ROOT_DIR, "src", "cli.py"), "--version"],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert cli.returncode == 0, cli.stderr or cli.stdout
    assert f"rove core v{VERSION}" in cli.stdout

    print(
        f"[PASS] VERSION, CLI, native self-host, compiler source, VS Code, and "
        f"README agree on {VERSION}; active animated assets are preserved"
    )
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_version_contract_suite() else 1)
