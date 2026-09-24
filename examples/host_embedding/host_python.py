"""Python Host for Rove Module.

Demonstrates compiling and embedding a Rove data transformation module
directly inside Python 3 using Rove's Python HIR backend.
"""

import os
import sys
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

def build_rove_python_module():
    src_path = HERE / "transformer.rove"
    out_dir = HERE / "py_build"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "transformer.py"
    
    cmd = [
        sys.executable,
        "-m", "src.cli", "build",
        str(src_path),
        "--target", "python",
    ]
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stderr or res.stdout)
        raise RuntimeError("Failed to build Rove python module")
    
    # Copy from build/python to our local dir if needed
    src_built = REPO_ROOT / "build" / "python" / "transformer.py"
    if src_built.exists():
        out_file.write_text(src_built.read_text(encoding="utf-8"), encoding="utf-8")
    return out_dir

def main():
    print("[*] Building Rove module for Python target...")
    build_dir = build_rove_python_module()
    sys.path.insert(0, str(build_dir))
    
    import transformer
    print("[+] Successfully imported Rove module into Python runtime!")
    
    # 1. Float sum
    floats = [10.5, 20.25, 30.25, 40.0]
    sum_res = transformer.sum_floats(floats)
    print(f"[+] sum_floats: {sum_res} (expected: 101.0)")
    assert sum_res == 101.0
    
    # 2. In-place integer array mutation
    ints = [10, 20, 30, 40]
    count = transformer.mutate_add_in_place(ints, 5)
    print(f"[+] mutate_add_in_place: count = {count}, ints = {ints}")
    assert count == 4
    assert ints == [15, 25, 35, 45]
    
    # 3. String formatting
    summary = transformer.format_summary("SensorTelemetry")
    print(f'[+] format_summary: "{summary}"')
    assert summary == "Summary: SensorTelemetry [OK]"
    
    print("\n[SUCCESS] Python host embedding verified successfully!")

if __name__ == "__main__":
    main()
