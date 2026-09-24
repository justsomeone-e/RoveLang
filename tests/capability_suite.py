import json
import os
import shutil
import subprocess
import sys
import tempfile


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_PATH = os.path.join(ROOT_DIR, "src", "cli.py")
PARITY_SOURCE = os.path.join(ROOT_DIR, "tests", "test_parity_matrix.rove")
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.core.backend_capabilities import (
    BACKENDS,
    CAPABILITY_SCHEMA_VERSION,
    get_stdlib_contract,
    normalize_backend_name,
    resolve_backend,
    stdlib_module_from_import,
    stdlib_modules_for_target,
)
from src.core.diagnostics import DiagnosticEmitter, DiagnosticError
from src.core.module_loader import ModuleLoader
from src.api import RoveCompiler


def _write(path: str, source: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(source)


def run_capability_suite() -> bool:
    print("=" * 70)
    print("ROVE BACKEND / STDLIB CAPABILITY CONTRACT")
    print("=" * 70)

    assert normalize_backend_name("python") == "python"
    assert normalize_backend_name("node") == "js"
    assert normalize_backend_name("ll") == "llvm"
    assert resolve_backend("stm32") is None
    assert normalize_backend_name("desktop") == "cpp"
    assert "fs" in stdlib_modules_for_target("js")
    assert "fs" not in stdlib_modules_for_target("rust")
    for target in ("cpp", "js", "python"):
        assert {"int64_wrap", "float64_ieee", "canonical_scalar_text"} <= BACKENDS[target].features
    for target in ("cpp", "js", "python", "rust", "wasm"):
        assert "typed_hir_v1" in BACKENDS[target].features
    for target in ("cpp", "js", "python"):
        assert {"channels", "spawn"} <= BACKENDS[target].features
    assert {"channels", "spawn"}.isdisjoint(BACKENDS["rust"].features)
    for target in ("asm", "react"):
        assert "typed_hir_v1" not in BACKENDS[target].features
    assert "int64_wrap" not in BACKENDS["wasm"].features
    assert "wasm32" in BACKENDS["wasm"].features
    assert {
        "host_imports_v1", "numeric_array_abi", "wasi_preview1", "web_dom"
    } <= BACKENDS["wasm"].features
    assert "web" in stdlib_modules_for_target("wasm")
    assert "web" not in stdlib_modules_for_target("cpp")
    assert get_stdlib_contract("web.rove") == get_stdlib_contract("web")
    assert get_stdlib_contract("web.nyx") == get_stdlib_contract("web")
    assert stdlib_module_from_import("std/web.rove") == "web"
    assert stdlib_module_from_import("std/web.nyx") == "web"
    assert "http" in stdlib_modules_for_target("cpp")
    assert "http" not in stdlib_modules_for_target("js")

    http_source_path = os.path.join(ROOT_DIR, "src", "stdlib", "http.rove")
    with open(http_source_path, "r", encoding="utf-8") as handle:
        http_source = handle.read()
    assert "popen(" not in http_source and "_popen(" not in http_source
    assert "execvp(" in http_source and "CreateProcessA(" in http_source

    cli_manifest = subprocess.run(
        [sys.executable, CLI_PATH, "targets", "--json"],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert cli_manifest.returncode == 0, cli_manifest.stderr or cli_manifest.stdout
    manifest = json.loads(cli_manifest.stdout)
    assert manifest["schema_version"] == CAPABILITY_SCHEMA_VERSION
    assert {backend["name"] for backend in manifest["backends"]} >= {
        "cpp", "c", "llvm", "js", "python", "rust", "react", "wasm"
    }

    propagated = (
        "fn read() -> Result<int, string> { return Ok(1) }\n"
        "fn run() -> Result<int, string> { let value = read()?; return Ok(value) }\n"
    )
    for target in ("asm", "wasm", "react"):
        rejected = RoveCompiler(ROOT_DIR).compile_source(
            propagated,
            target=target,
            filename=f"capability-{target}.rove",
        )
        assert not rejected.success, f"{target} silently accepted unsupported Result propagation"
        assert rejected.diagnostics and rejected.diagnostics[0].code == "E3001"
        assert "supported targets: cpp, js, python, rust" in rejected.diagnostics[0].note

    previous_exit_mode = DiagnosticEmitter.EXIT_ON_ERROR
    DiagnosticEmitter.EXIT_ON_ERROR = False
    try:
        with tempfile.TemporaryDirectory(prefix="rove_capability_") as temp_dir:
            js_source = os.path.join(temp_dir, "js_ok.rove")
            _write(js_source, '#target js\nimport "std/fs"\nfn main() {}\n')
            js_ast = ModuleLoader(base_dir=temp_dir).load_program(js_source)
            assert js_ast.target == "js"

            llvm_source = os.path.join(temp_dir, "llvm_ok.rove")
            _write(llvm_source, '#target llvm\nfn answer() -> int { return 42 }\n')
            llvm_ast = ModuleLoader(base_dir=temp_dir).load_program(llvm_source)
            assert llvm_ast.target == "llvm"
            llvm_result = RoveCompiler(temp_dir).compile_file(llvm_source)
            assert llvm_result.success, llvm_result.diagnostics
            assert llvm_result.target == "llvm"
            assert llvm_result.artifact is not None
            assert llvm_result.artifact.extension == ".ll"

            wrong_web_source = os.path.join(temp_dir, "wrong_web_target.rove")
            _write(wrong_web_source, '#target cpp\nimport "std/web"\nfn main() {}\n')
            try:
                ModuleLoader(base_dir=temp_dir).load_program(wrong_web_source)
                raise AssertionError("cpp accepted wasm-only std/web")
            except DiagnosticError as error:
                assert error.code == "E1400"

            native_http_source = os.path.join(temp_dir, "native_http_ok.rove")
            _write(native_http_source, '#target cpp\nimport "std/http"\nfn main() {}\n')
            native_http_ast = ModuleLoader(base_dir=temp_dir).load_program(native_http_source)
            assert native_http_ast.target == "cpp"

            portable_str = os.path.join(temp_dir, "portable_str.rove")
            _write(
                portable_str,
                'import "std/str"\n'
                'fn main() {\n'
                '    print(concat_three("a", "b", "c"))\n'
                '    print(wrap_with("x", "[", "]"))\n'
                '    print(contains_substring("nyx-platform", "platform"))\n'
                '}\n',
            )
            for target in ("cpp", "js", "python"):
                portable_run = subprocess.run(
                    [sys.executable, CLI_PATH, "run", portable_str, "--target", target],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                assert portable_run.returncode == 0, portable_run.stderr or portable_run.stdout
                normalized = portable_run.stdout.replace("\r\n", "\n").lower()
                assert "abc\n[x]\ntrue" in normalized, f"std/str parity failed for {target}: {normalized}"

            rust_build = subprocess.run(
                [sys.executable, CLI_PATH, "build", portable_str, "--target", "rust"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert rust_build.returncode == 0, rust_build.stderr or rust_build.stdout
            rust_source_path = os.path.join(temp_dir, "build", "rust", "portable_str.rs")
            rustc = shutil.which("rustc")
            assert rustc, "rustc is required for the rust capability contract"
            rust_check = subprocess.run(
                [rustc, "--edition=2021", "--emit=metadata", rust_source_path],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert rust_check.returncode == 0, rust_check.stderr or rust_check.stdout

            for target in ("cpp", "js", "python"):
                parity_run = subprocess.run(
                    [sys.executable, CLI_PATH, "run", PARITY_SOURCE, "--target", target],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                parity_output = parity_run.stdout + parity_run.stderr
                assert parity_run.returncode == 0, parity_output
                assert "[FAIL]" not in parity_output, f"stdlib parity failed for {target}: {parity_output}"
                assert "[SUCCESS] All 6 Stdlib Modules" in parity_output

            rust_source = os.path.join(temp_dir, "rust_reject.rove")
            _write(rust_source, '#target rust\nimport "std/fs"\nfn main() {}\n')
            try:
                ModuleLoader(base_dir=temp_dir).load_program(rust_source)
                raise AssertionError("rust accepted unsupported std/fs")
            except DiagnosticError as error:
                assert error.code == "E1400"

            unknown_source = os.path.join(temp_dir, "unknown_target.rove")
            _write(unknown_source, '#target moonvm\nfn main() {}\n')
            try:
                ModuleLoader(base_dir=temp_dir).load_program(unknown_source)
                raise AssertionError("unknown target was accepted")
            except DiagnosticError as error:
                assert error.code == "E1401"

            unknown_build = subprocess.run(
                [sys.executable, CLI_PATH, "build", unknown_source, "--target", "moonvm"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert unknown_build.returncode != 0
            assert "Unknown target" in (unknown_build.stdout + unknown_build.stderr)
    finally:
        DiagnosticEmitter.EXIT_ON_ERROR = previous_exit_mode

    print("[PASS] Aliases, HIR authority manifest, target gates, std/str, and 6-module parity")
    return True


if __name__ == "__main__":
    sys.exit(0 if run_capability_suite() else 1)
