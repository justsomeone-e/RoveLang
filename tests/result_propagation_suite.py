"""Runtime and diagnostic contract for postfix Result propagation (`expr?`)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.api import NyxCompiler
from src.codegen.cpp_toolchain import CppToolchain


PROGRAM = r'''
fn source(ok: bool) -> Result<int, string> {
    if ok { return Ok(40) }
    return Err("boom")
}

fn calculate(ok: bool) -> Result<int, string> {
    var value = source(ok)?
    return Ok(value + 2)
}

fn main() {
    match calculate(true) {
        Ok(value) => print("OK", value),
        Err(error) => print("ERR", error)
    }
    match calculate(false) {
        Ok(value) => print("OK", value),
        Err(error) => print("ERR", error)
    }
}
'''


def _compile(source: str, target: str):
    return NyxCompiler(ROOT_DIR).compile_source(
        source,
        target=target,
        filename=os.path.join(ROOT_DIR, f"result-propagation-{target}.rove"),
    )


def _run(target: str, content: str, directory: str) -> tuple[int, str]:
    if target == "cpp":
        source_path = os.path.join(directory, "result_propagation.cpp")
        executable_path = os.path.join(directory, "result_propagation.exe")
        with open(source_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        compiled, message = CppToolchain.compile_cpp(source_path, executable_path)
        assert compiled, message
        return CppToolchain.run_executable(executable_path)

    if target == "rust":
        runtime = shutil.which("rustc")
        assert runtime is not None, "rustc is required for Rust Result propagation coverage"
        path = os.path.join(directory, "result_propagation.rs")
        executable = os.path.join(
            directory, "result_propagation-rust" + (".exe" if os.name == "nt" else "")
        )
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        compiled = subprocess.run(
            [runtime, "--edition=2021", path, "-o", executable],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert compiled.returncode == 0, compiled.stderr or compiled.stdout
        command = [executable]
    elif target == "js":
        runtime = shutil.which("node")
        assert runtime is not None, "Node.js is required for Result propagation coverage"
        path = os.path.join(directory, "result_propagation.js")
        command = [runtime, path]
    else:
        path = os.path.join(directory, "result_propagation.py")
        command = [sys.executable, path]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    process = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return process.returncode, process.stdout + process.stderr


def _assert_error(source: str, code: str) -> None:
    result = _compile(source, "cpp")
    assert not result.success, f"expected {code}, compilation succeeded"
    assert any(diagnostic.code == code for diagnostic in result.diagnostics), result.diagnostics


def run_result_propagation_suite() -> bool:
    with tempfile.TemporaryDirectory(prefix="nyx_result_propagation_") as directory:
        for target in ("cpp", "js", "python", "rust"):
            result = _compile(PROGRAM, target)
            assert result.success, result.diagnostics
            assert result.artifact is not None
            return_code, output = _run(target, result.artifact.content, directory)
            assert return_code == 0, f"{target} Result propagation failed:\n{output}"
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            assert lines == ["OK 42", "ERR boom"], (target, lines)

    _assert_error(
        "fn read() -> Result<int, string> { return Ok(1) } var value = read()?",
        "E2036",
    )
    _assert_error("fn run() -> Result<int, string> { var value = 1?; return Ok(value) }", "E2037")
    _assert_error(
        "fn read() -> Result<int, string> { return Ok(1) } fn run() -> int { return read()? }",
        "E2038",
    )
    _assert_error(
        "fn read() -> Result<int, int> { return Err(1) } "
        "fn run() -> Result<int, string> { var value = read()?; return Ok(value) }",
        "E2039",
    )

    print("[PASS] Result '?': C++/JS/Python/Rust early return and typing diagnostics")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_result_propagation_suite() else 1)
