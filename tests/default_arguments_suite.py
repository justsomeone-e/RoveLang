"""Runtime and diagnostic contract for default argument values."""

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
fn greet(name: string = "world", times: int = 1) -> int {
    var count: int = 0
    while count < times {
        print("hi", name)
        set count = count + 1
    }
    return count
}

fn main() {
    print(greet())
    print(greet("nyx"))
    print(greet("nyx", 3))
}
'''


def _compile(source: str, target: str):
    return NyxCompiler(ROOT_DIR).compile_source(
        source,
        target=target,
        filename=os.path.join(ROOT_DIR, f"default-arguments-{target}.rove"),
    )


def _run(target: str, content: str, directory: str) -> tuple[int, str]:
    if target == "cpp":
        source_path = os.path.join(directory, "default_arguments.cpp")
        executable_path = os.path.join(directory, "default_arguments.exe")
        with open(source_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        compiled, message = CppToolchain.compile_cpp(source_path, executable_path)
        assert compiled, message
        return CppToolchain.run_executable(executable_path)

    if target == "js":
        runtime = shutil.which("node")
        assert runtime is not None, "Node.js is required for default argument coverage"
        path = os.path.join(directory, "default_arguments.js")
        command = [runtime, path]
    else:
        path = os.path.join(directory, "default_arguments.py")
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


def run_default_arguments_suite() -> bool:
    with tempfile.TemporaryDirectory(prefix="nyx_default_arguments_") as directory:
        for target in ("cpp", "js", "python"):
            result = _compile(PROGRAM, target)
            assert result.success, result.diagnostics
            assert result.artifact is not None
            return_code, output = _run(target, result.artifact.content, directory)
            assert return_code == 0, f"{target} default arguments failed:\n{output}"
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            assert lines == ["hi world", "1", "hi nyx", "1", "hi nyx", "hi nyx", "hi nyx", "3"], (target, lines)

    # Omitting a parameter that has no default remains an arity error.
    _assert_error(
        "fn add(a: int, b: int = 2) -> int { return a + b } fn main() { print(add()) }",
        "E2007",
    )
    # A default value that does not match its declared type is still rejected.
    _assert_error(
        "fn add(a: int = \"nope\") -> int { return a } fn main() { print(add()) }",
        "E2003",
    )

    print("[PASS] default arguments: C++/JS/Python runtime, partial application, and diagnostics")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_default_arguments_suite() else 1)
