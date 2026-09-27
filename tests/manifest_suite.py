import os
import sys

_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from src.toolchain.manifest import NyxManifest, NyxLock

def test_manifest_parsing():
    test_content = """[package]
name = "my_project"
version = "1.2.3"
edition = "2026"
target = "cpp"
entry = "src/main.rove"
description = "Test description"
license = "MIT"

[dependencies]
std = "3.0.0"
gpio = { version = "0.1.0", platform = "windows" }

[native]
includes = ["windows.h", "stdio.h"]
links = ["ws2_32", "msvcrt"]

[build]
opt_level = 3
output_type = "lib"
output_name = "libmyproj.a"
"""
    manifest_path = "test_nyx.toml"
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(test_content)
    
    try:
        m = NyxManifest(manifest_path)
        assert m.package["name"] == "my_project", "Package name mismatch"
        assert m.package["version"] == "1.2.3", "Version mismatch"
        assert m.package["edition"] == "2026", "Edition mismatch"
        assert m.dependencies["std"] == "3.0.0", "Dependency std mismatch"
        assert m.dependencies["gpio"]["platform"] == "windows", "Dependency gpio platform mismatch"
        assert "windows.h" in m.native["includes"], "Native includes mismatch"
        assert "ws2_32" in m.native["links"], "Native links mismatch"
        assert m.build["opt_level"] == 3, "Build opt_level mismatch"
        assert m.build["output_type"] == "lib", "Build output_type mismatch"
        
        # Test Lockfile generation
        lock_path = "test_nyx.lock"
        NyxLock.generate(m, lock_path)
        assert os.path.exists(lock_path), "Lockfile was not created"
        with open(lock_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert 'std = "3.0.0"' in content, "Lockfile missing std"
        assert 'gpio = "0.1.0"' in content, "Lockfile missing gpio"
        os.remove(lock_path)
    finally:
        if os.path.exists(manifest_path):
            os.remove(manifest_path)

def run_manifest_suite() -> bool:
    print("=" * 70)
    print("ROVE PHASE 3.3 LIBRARY MANIFEST TEST HARNESS")
    print("=" * 70)
    try:
        test_manifest_parsing()
        print("=" * 70)
        print("[OK] Manifest Suite: 1/1 Passed")
        print("=" * 70)
        return True
    except Exception as e:
        print(f"[FAIL] Manifest Suite: {e}")
        return False

if __name__ == "__main__":
    success = run_manifest_suite()
    sys.exit(0 if success else 1)
