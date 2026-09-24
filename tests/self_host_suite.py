import os
import subprocess
import sys
import tempfile


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_PATH = os.path.join(ROOT_DIR, "src", "cli.py")
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.codegen.cpp_toolchain import CppToolchain


def _run_reported_example_regressions(native_compiler: str, temp_dir: str) -> None:
    """Exercise the Windows failures reported in GitHub issue #6."""
    environment = os.environ.copy()
    environment["ROVE_NO_PAUSE"] = "1"
    suffix = ".exe" if os.name == "nt" else ""
    cases = (
        (
            "07_foreign_cpp.rove",
            "foreign",
            ("C++ filesystem current path:", "Current directory name:"),
        ),
        (
            "03_null_safety.rove",
            "null_safety",
            (
                "User Profile: Anonymous Guest",
                "Access Level: Guest",
                "Verified User: Alice",
                "Verified Role: Engineer",
            ),
        ),
        (
            "04_in_file_tests.rove",
            "in_file_tests",
            (
                '[PASS] add(10, 20) == 30',
                '[PASS] concat_str("Holy", "Easy") == "Holy Easy"',
                "[PASS] numbers[1] == 200",
            ),
        ),
    )

    for example_name, output_name, expected_lines in cases:
        source_path = os.path.join(ROOT_DIR, "examples", example_name)
        executable_path = os.path.join(temp_dir, output_name + suffix)
        compiled = subprocess.run(
            [native_compiler, "compile", source_path, "-o", executable_path],
            cwd=ROOT_DIR,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        compiler_output = compiled.stdout + compiled.stderr
        assert compiled.returncode == 0, compiler_output
        assert "ROVE_BUILD_OK" in compiler_output, compiler_output
        assert "warning:" not in compiler_output.lower(), compiler_output

        executed = subprocess.run(
            [executable_path],
            cwd=ROOT_DIR,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        runtime_output = executed.stdout + executed.stderr
        assert executed.returncode == 0, runtime_output
        for expected in expected_lines:
            assert expected in runtime_output, (example_name, expected, runtime_output)


def run_self_host_suite() -> bool:
    print("=" * 70)
    print("ROVE NATIVE STAGE-1 -> STAGE-2 SELF-HOST CONFORMANCE")
    print("=" * 70)

    verify = subprocess.run(
        [sys.executable, CLI_PATH, "self-host", "verify"],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert verify.returncode == 0, verify.stderr or verify.stdout

    with tempfile.TemporaryDirectory(prefix="rove_self_host_suite_") as temp_dir:
        native_compiler = os.path.join(
            temp_dir, "rovec.exe" if os.name == "nt" else "rovec"
        )
        native_build = subprocess.run(
            [sys.executable, CLI_PATH, "self-host", "build", "-o", native_compiler],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        assert native_build.returncode == 0, native_build.stderr or native_build.stdout
        _run_reported_example_regressions(native_compiler, temp_dir)

        source_path = os.path.join(temp_dir, "sample.rove")
        output_path = os.path.join(temp_dir, "sample.cpp")
        with open(source_path, "w", encoding="utf-8") as source:
            source.write(
                "fn add(a: int, b: int) -> int { return a + b; }\n"
                "struct Worker { base: int }\n"
                "impl Worker {\n"
                "    async fn compute(self, value: int) -> int { return self.base + value; }\n"
                "}\n"
                "async fn compute() -> int { return 42; }\n"
                "async fn fail_async() -> int { throw \"async boom\"; }\n"
                "fn metric(fail: bool) -> Result<float, string> {\n"
                "    if fail { return Err(\"metric failed\"); }\n"
                "    return Ok(3.5);\n"
                "}\n"
                "async fn main() -> void {\n"
                "    let task: Task<int> = compute();\n"
                "    print(add(await task, await task));\n"
                "    print(9223372036854775807 + 1);\n"
                "    let worker = Worker(40);\n"
                "    print(await worker.compute(2));\n"
                "    try { print(await fail_async()); }\n"
                "    catch error { print(\"caught:\", error); }\n"
                "    let good = metric(false);\n"
                "    let bad = metric(true);\n"
                "    print(good.value);\n"
                "    print(bad.error);\n"
                "}\n"
            )

        compile_result = subprocess.run(
            [sys.executable, CLI_PATH, "self-host", "compile", source_path, "--output", output_path],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert compile_result.returncode == 0, compile_result.stderr or compile_result.stdout
        assert os.path.exists(output_path)
        with open(output_path, "r", encoding="utf-8") as generated:
            cpp = generated.read()
        assert "int64_t add(" in cpp
        assert "return _nyx_i64_add(a, b);" in cpp
        assert "_nyx_i64_add(static_cast<int64_t>(9223372036854775807), static_cast<int64_t>(1))" in cpp
        assert "NyxTask<int64_t> compute(" in cpp
        assert "NyxTask<int64_t> compute(int64_t value)" in cpp
        assert "_nyx_user_main().get();" in cpp
        executable_path = os.path.join(temp_dir, "sample.exe")
        compiled, message = CppToolchain.compile_cpp(output_path, executable_path)
        assert compiled, message
        return_code, output = CppToolchain.run_executable(executable_path)
        assert return_code == 0
        assert output.replace("\r\n", "\n").strip() == (
            "84\n-9223372036854775808\n42\ncaught: async boom\n3.5\nmetric failed"
        )

    print(
        "[PASS] Rove-authored frontend, native stage-2 bootstrap, reported examples, "
        "and output reproducibility verified"
    )
    return True


if __name__ == "__main__":
    sys.exit(0 if run_self_host_suite() else 1)
