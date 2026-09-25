import os
import shutil
import subprocess
import sys
import tempfile

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src import compile_source
from src.core.backend_capabilities import BACKENDS


def _clang_available() -> bool:
    clang = shutil.which("clang")
    if not clang:
        return False
    try:
        proc = subprocess.run([clang, "--version"], capture_output=True, text=True, timeout=10)
        return proc.returncode == 0
    except Exception:
        return False


def _compile_and_run_c17(source: str, temp_dir: str, name: str = "prog") -> tuple[int, str]:
    result = compile_source(source, target="c", filename=f"<{name}>")
    assert result.success, f"C17 compilation failed: {result.diagnostics}"
    assert result.artifact is not None
    assert result.artifact.target == "c"
    assert result.artifact.kind == "c17"

    c_path = os.path.join(temp_dir, f"{name}.c")
    exe_path = os.path.join(temp_dir, f"{name}.exe")
    with open(c_path, "w", encoding="utf-8") as f:
        f.write(result.artifact.content)

    compile_cmd = [
        "clang",
        "-std=c17",
        "-Wall",
        "-Wextra",
        "-Werror",
        c_path,
        "-o",
        exe_path,
    ]
    proc = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, f"clang compilation failed:\n{proc.stderr}\nCode:\n{result.artifact.content}"

    run_proc = subprocess.run([exe_path], capture_output=True, text=True, timeout=15)
    return run_proc.returncode, run_proc.stdout.replace("\r\n", "\n")


def _run_cpp_oracle(source: str) -> str:
    from src.codegen.cpp_toolchain import CppToolchain

    result = compile_source(source, target="cpp", filename="<oracle>")
    assert result.success, f"CPP oracle compilation failed: {result.diagnostics}"
    with tempfile.TemporaryDirectory(prefix="c17_oracle_") as d:
        cpp_file = os.path.join(d, "oracle.cpp")
        exe_file = os.path.join(d, "oracle.exe")
        with open(cpp_file, "w", encoding="utf-8") as f:
            f.write(result.artifact.content)
        ok, msg = CppToolchain.compile_cpp(cpp_file, exe_file)
        assert ok, msg
        rc, out = CppToolchain.run_executable(exe_file)
        assert rc == 0, f"CPP oracle runtime error: {out}"
        return out.replace("\r\n", "\n")


def run_c17_scalar_suite() -> bool:
    print("=" * 70)
    print("ROVE C17 NATIVE SCALAR PILOT CONTRACT")
    print("=" * 70)

    # 1. Capability spec check
    c_backend = BACKENDS.get("c")
    assert c_backend is not None
    assert c_backend.name == "c"
    assert c_backend.maturity == "experimental"
    assert "scalar_c17" in c_backend.features
    assert "typed_hir_v1" in c_backend.features
    assert "int64_wrap" in c_backend.features

    if not _clang_available():
        print("[SKIP] clang C17 compiler not found in PATH")
        return True

    with tempfile.TemporaryDirectory(prefix="nyx_c17_suite_") as temp_dir:
        # 2. Basic scalar print
        basic_src = "fn main() { print(42) }\n"
        rc, out = _compile_and_run_c17(basic_src, temp_dir, "basic")
        assert rc == 0
        assert out.strip() == "42"

        # 3. Arithmetic, signed 64-bit wrapping overflow, and INT64_MIN / -1
        math_src = (
            "fn main() {\n"
            "    var a: int = 9223372036854775807;\n"
            "    var b: int = a + 1;\n"
            "    print(b);\n"
            "    var c: int = b - 1;\n"
            "    print(c);\n"
            "    var d: int = b * -1;\n"
            "    print(d);\n"
            "    var norm_div: int = 100 / 3;\n"
            "    print(norm_div);\n"
            "    var norm_mod: int = 100 % 3;\n"
            "    print(norm_mod);\n"
            "    var min_div: int = -9223372036854775808 / -1;\n"
            "    print(min_div);\n"
            "    var min_mod: int = -9223372036854775808 % -1;\n"
            "    print(min_mod);\n"
            "    var shifted: int = 1 << 4;\n"
            "    print(shifted);\n"
            "    var masked: int = (15 & 7) ^ 2;\n"
            "    print(masked);\n"
            "}\n"
        )
        rc, out = _compile_and_run_c17(math_src, temp_dir, "math")
        assert rc == 0
        oracle_out = _run_cpp_oracle(math_src)
        assert out == oracle_out, f"Parity mismatch with C++ oracle:\nC17: {out}\nCPP: {oracle_out}"

        # 4. Division by zero abort
        div_zero_src = "fn main() { var x: int = 10 / 0; print(x) }\n"
        rc, _ = _compile_and_run_c17(div_zero_src, temp_dir, "div_zero")
        assert rc != 0, "Expected non-zero exit code on integer division by zero"

        # 5. Functions, recursion, and control flow (while, if, break, continue)
        ctrl_src = (
            "fn fib(n: int) -> int {\n"
            "    if n <= 1 { return n }\n"
            "    return fib(n - 1) + fib(n - 2)\n"
            "}\n"
            "fn sum_filtered(limit: int) -> int {\n"
            "    var total: int = 0;\n"
            "    var i: int = 1;\n"
            "    while i <= limit {\n"
            "        if i == 5 {\n"
            "            set i = i + 1;\n"
            "            continue;\n"
            "        }\n"
            "        if i > 8 {\n"
            "            break;\n"
            "        }\n"
            "        set total = total + i;\n"
            "        set i = i + 1;\n"
            "    }\n"
            "    return total\n"
            "}\n"
            "fn main() {\n"
            "    print(fib(10));\n"
            "    print(sum_filtered(15));\n"
            "}\n"
        )
        rc, out = _compile_and_run_c17(ctrl_src, temp_dir, "ctrl")
        assert rc == 0
        oracle_out = _run_cpp_oracle(ctrl_src)
        assert out == oracle_out, f"Control flow parity mismatch:\nC17: {out}\nCPP: {oracle_out}"

        # 6. Floating point and boolean operations
        float_bool_src = (
            "fn compute(x: float, y: float) -> float {\n"
            "    return (x * y) + 1.25\n"
            "}\n"
            "fn logic(a: bool, b: bool) -> bool {\n"
            "    return (a and not b) or (not a and b)\n"
            "}\n"
            "fn main() {\n"
            "    print(compute(2.5, 4.0));\n"
            "    print(logic(true, false));\n"
            "    print(logic(true, true));\n"
            "    print(logic(false, false));\n"
            "}\n"
        )
        rc, out = _compile_and_run_c17(float_bool_src, temp_dir, "float_bool")
        assert rc == 0
        oracle_out = _run_cpp_oracle(float_bool_src)
        assert out == oracle_out, f"Float/bool parity mismatch:\nC17: {out}\nCPP: {oracle_out}"

        # 7. Rejection of unsupported non-scalar constructs
        unsupported_cases = [
            ("array", "fn main() { var arr = [1, 2, 3]; }\n"),
            ("struct", "struct Point { x: int } fn main() {}\n"),
            ("task", "async fn compute() -> int { return 1 }\nfn main() { var t = compute(); }\n"),
            ("exception", "fn main() { throw 42; }\n"),
            ("try_catch", "fn main() { try { print(1) } catch e { print(2) } }\n"),
        ]
        for label, code in unsupported_cases:
            res = compile_source(code, target="c", filename=f"<reject-{label}>")
            assert not res.success, f"C17 silently accepted unsupported construct '{label}'"
            assert res.diagnostics and res.diagnostics[0].code == "E3001"

    print("[PASS] Capability spec, scalar primitives, int64_wrap, control flow, clang C17 build, and strict rejection")
    return True


if __name__ == "__main__":
    sys.exit(0 if run_c17_scalar_suite() else 1)
