# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import shutil
import subprocess

_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

from src.codegen.cpp_toolchain import CppToolchain

def run_sdk_suite() -> bool:
    print("=" * 70)
    print("ROVE PHASE 3.7 NATIVE SDK & CLI TEST HARNESS")
    print("=" * 70)
    sys.stdout.flush()

    compiler = CppToolchain.find_compiler()
    ar = CppToolchain.find_ar()
    if not compiler or not ar:
        print("[!] Compiler or AR toolchain not found. Skipping SDK compilation suite.")
        return True

    temp_dir = tempfile.mkdtemp(prefix="nyx_sdk_test_")
    passed = 0
    total = 3

    try:
        cli_py = os.path.join(_root_dir, "src", "cli.py")
        lib_name = "math_sdk_test"
        lib_dir = os.path.join(temp_dir, lib_name)

        # 1. Test nyx new <name> --lib
        print(f"[*] Testing sdk_01_create_library_project...")
        res = subprocess.run([sys.executable, cli_py, "new", lib_name, "--lib"], cwd=temp_dir, capture_output=True, text=True, encoding="utf-8")
        if res.returncode == 0 and os.path.exists(os.path.join(lib_dir, "nyx.toml")) and os.path.exists(os.path.join(lib_dir, "src", "lib.rove")) and os.path.exists(os.path.join(lib_dir, "examples", "basic.rove")):
            print("  [PASS] sdk_01_create_library_project -> Scaffolding matched")
            passed += 1
        else:
            print(f"  [FAIL] sdk_01_create_library_project -> Failed: {res.stderr or res.stdout}")

        # 2. Test nyx build (library mode)
        print(f"[*] Testing sdk_02_build_library_project...")
        res = subprocess.run([sys.executable, cli_py, "build"], cwd=lib_dir, capture_output=True, text=True, encoding="utf-8")
        lib_file = os.path.join(lib_dir, "build", "cpp", "liblib.a")
        if res.returncode == 0 and os.path.exists(lib_file):
            print(f"  [PASS] sdk_02_build_library_project -> Built {os.path.basename(lib_file)}")
            passed += 1
        else:
            print(f"  [FAIL] sdk_02_build_library_project -> Failed: {res.stderr or res.stdout}")

        # 3. Test nyx run examples/basic.rove
        print(f"[*] Testing sdk_03_run_example_project...")
        res = subprocess.run([sys.executable, cli_py, "run", "examples/basic.rove"], cwd=lib_dir, capture_output=True, text=True, encoding="utf-8")
        if res.returncode == 0 and "Add result: 12" in res.stdout:
            print("  [PASS] sdk_03_run_example_project -> Output matched (Add result: 12)")
            passed += 1
        else:
            print(f"  [FAIL] sdk_03_run_example_project -> Failed:\nExpected: Add result: 12\nGot: {res.stdout}\nErr: {res.stderr}")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("=" * 70)
    print(f"[OK] Native SDK & CLI Suite: {passed}/{total} Passed")
    print("=" * 70)
    sys.stdout.flush()
    return passed == total

if __name__ == "__main__":
    success = run_sdk_suite()
    sys.exit(0 if success else 1)