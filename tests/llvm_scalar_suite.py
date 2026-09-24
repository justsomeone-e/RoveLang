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


def _compile_and_run_llvm(
    source: str,
    temp_dir: str,
    name: str = "prog",
    optimization: str = "-O2",
) -> tuple[int, str]:
    result = compile_source(source, target="llvm", filename=f"<{name}>")
    assert result.success, f"LLVM compilation failed: {result.diagnostics}"
    assert result.artifact is not None
    assert result.artifact.target == "llvm"
    assert result.artifact.kind == "llvm-ir"

    ll_path = os.path.join(temp_dir, f"{name}.ll")
    exe_path = os.path.join(temp_dir, f"{name}.exe" if sys.platform == "win32" else name)
    with open(ll_path, "w", encoding="utf-8") as f:
        f.write(result.artifact.content)

    compile_cmd = [
        "clang",
        optimization,
        ll_path,
        "-o",
        exe_path,
    ]
    if sys.platform != "win32":
        compile_cmd.append("-lm")
    proc = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, f"clang compilation failed:\n{proc.stderr}\nIR:\n{result.artifact.content}"

    run_proc = subprocess.run([exe_path], capture_output=True, text=True, timeout=15)
    return run_proc.returncode, run_proc.stdout.replace("\r\n", "\n")


def _run_cpp_oracle(source: str) -> str:
    from src.codegen.cpp_toolchain import CppToolchain

    result = compile_source(source, target="cpp", filename="<oracle>")
    assert result.success, f"CPP oracle compilation failed: {result.diagnostics}"
    with tempfile.TemporaryDirectory(prefix="llvm_oracle_") as d:
        cpp_file = os.path.join(d, "oracle.cpp")
        exe_file = os.path.join(d, "oracle.exe" if sys.platform == "win32" else "oracle")
        with open(cpp_file, "w", encoding="utf-8") as f:
            f.write(result.artifact.content)
        ok, msg = CppToolchain.compile_cpp(cpp_file, exe_file)
        assert ok, msg
        rc, out = CppToolchain.run_executable(exe_file)
        assert rc == 0, f"CPP oracle runtime error: {out}"
        return out.replace("\r\n", "\n")


def run_llvm_scalar_suite() -> bool:
    print("=" * 70)
    print("NYX DIRECT LLVM IR SCALAR PILOT CONTRACT")
    print("=" * 70)

    # 1. Capability spec check
    llvm_backend = BACKENDS.get("llvm")
    assert llvm_backend is not None
    assert llvm_backend.name == "llvm"
    assert llvm_backend.maturity == "experimental"
    assert "scalar_llvm" in llvm_backend.features
    assert "typed_hir_v1" in llvm_backend.features
    assert "int64_wrap" in llvm_backend.features
    assert "array_iteration" in llvm_backend.features
    assert "scalar_arrays" in llvm_backend.features
    assert "scalar_structs" in llvm_backend.features

    if not _clang_available():
        print("[SKIP] clang compiler not found in PATH")
        return True

    with tempfile.TemporaryDirectory(prefix="nyx_llvm_suite_") as temp_dir:
        # 2. Basic scalar print
        basic_src = "fn main() { print(42) }\n"
        rc, out = _compile_and_run_llvm(basic_src, temp_dir, "basic")
        assert rc == 0
        assert out.strip() == "42"

        multi_print_src = 'fn main() { print("answer", 42, true, 2.5) }\n'
        rc, out = _compile_and_run_llvm(multi_print_src, temp_dir, "multi_print")
        assert rc == 0
        multi_print_oracle = _run_cpp_oracle(multi_print_src)
        assert out == multi_print_oracle, (
            f"Multi-argument print parity mismatch:\nLLVM: {out!r}\nCPP: {multi_print_oracle!r}"
        )

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
        rc, out = _compile_and_run_llvm(math_src, temp_dir, "math")
        assert rc == 0
        oracle_out = _run_cpp_oracle(math_src)
        assert out == oracle_out, f"Parity mismatch with C++ oracle:\nLLVM: {out}\nCPP: {oracle_out}"

        # 4. Division by zero abort
        div_zero_src = "fn main() { var x: int = 10 / 0; print(x) }\n"
        rc, _ = _compile_and_run_llvm(div_zero_src, temp_dir, "div_zero")
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
        rc, out = _compile_and_run_llvm(ctrl_src, temp_dir, "ctrl")
        assert rc == 0
        oracle_out = _run_cpp_oracle(ctrl_src)
        assert out == oracle_out, f"Control flow parity mismatch:\nLLVM: {out}\nCPP: {oracle_out}"

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
        rc, out = _compile_and_run_llvm(float_bool_src, temp_dir, "float_bool")
        assert rc == 0
        oracle_out = _run_cpp_oracle(float_bool_src)
        assert out == oracle_out, f"Float/bool parity mismatch:\nLLVM: {out}\nCPP: {oracle_out}"

        # 7. Scalar-field structs are LLVM aggregate values and cross function
        # boundaries by value.
        struct_src = (
            "struct Point { x: int, y: float, active: bool }\n"
            "fn score(p: Point) -> float {\n"
            "    if p.active { return p.x + p.y }\n"
            "    return 0.0\n"
            "}\n"
            "fn main() {\n"
            "    var original: Point = Point(40, 1.5, true);\n"
            "    var copied: Point = original;\n"
            "    copied.x = 99;\n"
            "    print(original.x);\n"
            "    print(copied.x);\n"
            "    print(score(copied));\n"
            "}\n"
        )
        rc, out = _compile_and_run_llvm(struct_src, temp_dir, "struct_value")
        assert rc == 0
        oracle_out = _run_cpp_oracle(struct_src)
        assert out == oracle_out, f"Struct value parity mismatch:\nLLVM: {out}\nCPP: {oracle_out}"

        # 8. Stack-owned scalar arrays use checked indexing and deep local copies.
        array_src = (
            "fn mutate_copy(values: Array<int>) -> int {\n"
            "    values[0] = 77;\n"
            "    var second: Array<int> = values;\n"
            "    second[1] = 88;\n"
            "    return values[0] + second[1]\n"
            "}\n"
            "fn sum_selected(values: Array<int>) -> int {\n"
            "    var total: int = 0;\n"
            "    for value in values {\n"
            "        if value == 2 { continue }\n"
            "        if value > 3 { break }\n"
            "        set total = total + value;\n"
            "    }\n"
            "    return total\n"
            "}\n"
            "fn main() {\n"
            "    var original: Array<int> = [10, 20, 30];\n"
            "    var copied: Array<int> = original;\n"
            "    copied[1] = 99;\n"
            "    print(original[1]);\n"
            "    print(copied[1]);\n"
            "    print(copied.len());\n"
            "    print(mutate_copy(original));\n"
            "    print(original[0]);\n"
            "    var selected: Array<int> = [1, 2, 3, 4, 5];\n"
            "    print(sum_selected(selected));\n"
            "    var weights: Array<float> = [1.5, 2.25];\n"
            "    print(weights[0] + weights[1]);\n"
            "    var flags: Array<bool> = [true, false];\n"
            "    print(flags[0]);\n"
            "}\n"
        )
        rc, out = _compile_and_run_llvm(array_src, temp_dir, "array_value")
        assert rc == 0
        oracle_out = _run_cpp_oracle(array_src)
        assert out == oracle_out, f"Array value parity mismatch:\nLLVM: {out}\nCPP: {oracle_out}"
        rc_o0, out_o0 = _compile_and_run_llvm(array_src, temp_dir, "array_value_o0", "-O0")
        assert rc_o0 == 0
        assert out_o0 == oracle_out, f"Array O0 parity mismatch:\nLLVM: {out_o0}\nCPP: {oracle_out}"

        for name, index in (("negative", -1), ("past_end", 3)):
            bounds_src = f"fn main() {{ var values: Array<int> = [1, 2, 3]; print(values[{index}]); }}\n"
            rc, _ = _compile_and_run_llvm(bounds_src, temp_dir, f"array_{name}")
            assert rc != 0, f"Expected non-zero exit code for {name} Array index"

        # 9. The public CLI writes .ll and compiles that exact artifact to native code.
        cli_source = os.path.join(temp_dir, "cli_llvm.rove")
        with open(cli_source, "w", encoding="utf-8") as handle:
            handle.write("fn main() { print(42) }\n")
        cli = subprocess.run(
            [
                sys.executable,
                os.path.join(ROOT_DIR, "src", "cli.py"),
                "build",
                cli_source,
                "--target",
                "llvm",
            ],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert cli.returncode == 0, f"CLI LLVM build failed:\n{cli.stdout}\n{cli.stderr}"
        cli_build_dir = os.path.join(temp_dir, "build", "llvm")
        assert os.path.isfile(os.path.join(cli_build_dir, "cli_llvm.ll"))
        cli_executable = os.path.join(
            cli_build_dir,
            "cli_llvm.exe" if sys.platform == "win32" else "cli_llvm",
        )
        assert os.path.isfile(cli_executable)
        cli_run = subprocess.run([cli_executable], capture_output=True, text=True, timeout=15)
        assert cli_run.returncode == 0
        assert cli_run.stdout.strip() == "42"

        # 10. Rejection of unsupported aggregate/runtime constructs
        unsupported_cases = [
            ("array_return", "fn make() -> Array<int> { return [1, 2] } fn main() {}\n"),
            ("nested_array", "fn main() { var matrix = [[1, 2], [3, 4]]; }\n"),
            ("aggregate_struct", "struct Named { name: string } fn main() { var n = Named(\"nyx\"); }\n"),
            ("task", "async fn compute() -> int { return 1 }\nfn main() { var t = compute(); }\n"),
            ("exception", "fn main() { throw 42; }\n"),
            ("try_catch", "fn main() { try { print(1) } catch e { print(2) } }\n"),
        ]
        for label, code in unsupported_cases:
            res = compile_source(code, target="llvm", filename=f"<reject-{label}>")
            assert not res.success, f"LLVM silently accepted unsupported construct '{label}'"
            assert res.diagnostics and res.diagnostics[0].code == "E3001"

    print("[PASS] Capability spec, scalar primitives, scalar Arrays/Structs, int64_wrap, control flow, clang LLVM IR build, and strict rejection")
    return True


if __name__ == "__main__":
    sys.exit(0 if run_llvm_scalar_suite() else 1)
