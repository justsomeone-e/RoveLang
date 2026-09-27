import os
import sys
import tempfile
import shutil
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

def run_smoke_test():
    print("=" * 70)
    print("⚡ ROVE CLEAN-ENVIRONMENT SMOKE TEST")
    print("=" * 70)

    temp_sandbox = tempfile.mkdtemp(prefix="rove_clean_smoke_")
    cli_py = os.path.join(BASE_DIR, "src", "cli.py")
    passed_steps = 0
    total_steps = 5

    try:
        # Step 1: rove doctor
        print("[1/5] Testing 'rove doctor' in fresh environment...")
        res = subprocess.run([sys.executable, cli_py, "doctor"], cwd=temp_sandbox, capture_output=True, encoding='utf-8', errors='replace')
        assert res.returncode == 0 and "Environment & Toolchain Diagnostics" in res.stdout
        print("  [PASS] 'rove doctor' ran cleanly")
        passed_steps += 1

        # Step 2: rove new
        print("[2/5] Testing 'rove new smoke_project' project scaffolding...")
        res = subprocess.run([sys.executable, cli_py, "new", "smoke_project"], cwd=temp_sandbox, capture_output=True, encoding='utf-8', errors='replace')
        assert res.returncode == 0 and "Created rove project" in res.stdout
        
        proj_dir = os.path.join(temp_sandbox, "smoke_project")
        assert os.path.exists(os.path.join(proj_dir, "rove.toml")), "rove.toml must exist"
        assert os.path.exists(os.path.join(proj_dir, "src", "main.rove")), "src/main.rove must exist"
        print("  [PASS] Project created with valid structure and manifest")
        passed_steps += 1

        # Step 3: rove check
        print("[3/5] Testing 'rove check' on generated project...")
        main_rove = os.path.join(proj_dir, "src", "main.rove")
        res = subprocess.run([sys.executable, cli_py, "check", main_rove], cwd=proj_dir, capture_output=True, encoding='utf-8', errors='replace')
        assert res.returncode == 0 and "Check Passed" in res.stdout
        print("  [PASS] Semantic validation passed with 0 errors")
        passed_steps += 1

        # Step 4: rove test
        print("[4/5] Testing 'rove test' for in-file unit tests...")
        res = subprocess.run([sys.executable, cli_py, "test", main_rove], cwd=proj_dir, capture_output=True, encoding='utf-8', errors='replace')
        if "Execution finished successfully" not in res.stdout:
            print("STEP 4 STDOUT:", repr(res.stdout))
            print("STEP 4 STDERR:", repr(res.stderr))
        assert res.returncode == 0 and "Execution finished successfully" in res.stdout
        print("  [PASS] In-file assertion battery passed")
        passed_steps += 1

        # Step 5: rove run across backends
        print("[5/5] Testing 'rove run' across python, js, and cpp...")
        res_py = subprocess.run([sys.executable, cli_py, "run", main_rove, "--target", "python"], cwd=proj_dir, capture_output=True, encoding='utf-8', errors='replace')
        assert res_py.returncode == 0 and "Hello, smoke_project from rove!" in res_py.stdout

        res_js = subprocess.run([sys.executable, cli_py, "run", main_rove, "--target", "js"], cwd=proj_dir, capture_output=True, encoding='utf-8', errors='replace')
        assert res_js.returncode == 0 and "Hello, smoke_project from rove!" in res_js.stdout

        # Verify C++ transpilation & compilation
        from src.codegen.cpp_toolchain import CppToolchain
        if CppToolchain.find_compiler():
            res_cpp = subprocess.run([sys.executable, cli_py, "run", main_rove, "--target", "cpp"], cwd=proj_dir, capture_output=True, encoding='utf-8', errors='replace')
            assert res_cpp.returncode == 0 and "Hello, smoke_project from rove!" in res_cpp.stdout
        else:
            res_cpp = subprocess.run([sys.executable, cli_py, "build", main_rove, "--target", "cpp"], cwd=proj_dir, capture_output=True, encoding='utf-8', errors='replace')
            assert res_cpp.returncode == 0 and os.path.exists(os.path.join(proj_dir, "build"))

        print("  [PASS] Multi-backend execution produced matching verified output")
        passed_steps += 1

    finally:
        shutil.rmtree(temp_sandbox, ignore_errors=True)

    print("=" * 70)
    print(f"[OK] Clean Environment Smoke Test: {passed_steps}/{total_steps} Passed")
    print("=" * 70)
    return passed_steps == total_steps

if __name__ == "__main__":
    ok = run_smoke_test()
    sys.exit(0 if ok else 1)
