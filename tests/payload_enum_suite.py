"""Runtime, typing, and capability coverage for Nyx payload enums."""

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
enum Outcome<T, E> {
    Success(T),
    Failure(E)
}

enum Event {
    Point(int, int),
    Tick()
}

fn main() {
    var ok: Outcome<int, string> = Success(42)
    match ok {
        Success(value) => print("OK", value),
        Failure(error) => print("ERR", error)
    }

    var failed: Outcome<int, string> = Failure("boom")
    match failed {
        Success(value) => print("OK", value),
        Failure(error) => print("ERR", error)
    }

    var point = Point(7, 5)
    match point {
        Point(x, y) => print("POINT", x + y),
        Tick() => print("TICK")
    }

    var tick = Tick()
    match tick {
        Point(x, y) => print("POINT", x + y),
        Tick() => print("TICK")
    }
}
'''


def _compile(source: str, target: str):
    return NyxCompiler(ROOT_DIR).compile_source(
        source,
        target=target,
        filename=os.path.join(ROOT_DIR, f"payload-enum-{target}.rove"),
    )


def _run_artifact(target: str, content: str, temp_dir: str) -> tuple[int, str]:
    if target == "cpp":
        source_path = os.path.join(temp_dir, "payload_enum.cpp")
        executable_path = os.path.join(temp_dir, "payload_enum.exe")
        with open(source_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        compiled, message = CppToolchain.compile_cpp(source_path, executable_path)
        assert compiled, message
        return CppToolchain.run_executable(executable_path)

    if target == "js":
        runtime = shutil.which("node")
        assert runtime is not None, "Node.js is required for payload enum coverage"
        path = os.path.join(temp_dir, "payload_enum.js")
        command = [runtime, path]
    else:
        path = os.path.join(temp_dir, "payload_enum.py")
        command = [sys.executable, path]

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return process.returncode, process.stdout + process.stderr


def _assert_error(source: str, code: str, target: str = "cpp") -> None:
    result = _compile(source, target)
    assert not result.success, f"expected {code}, compilation succeeded"
    assert any(diagnostic.code == code for diagnostic in result.diagnostics), result.diagnostics


def run_payload_enum_suite() -> bool:
    expected = ["OK 42", "ERR boom", "POINT 12", "TICK"]
    with tempfile.TemporaryDirectory(prefix="nyx_payload_enum_") as temp_dir:
        for target in ("cpp", "js", "python"):
            result = _compile(PROGRAM, target)
            assert result.success, result.diagnostics
            assert result.artifact is not None
            return_code, output = _run_artifact(target, result.artifact.content, temp_dir)
            assert return_code == 0, f"{target} payload enum runtime failed:\n{output}"
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            assert lines == expected, (target, lines)

    _assert_error("enum Event { Point(int, int) } var event = Point(1, \"bad\")", "E2003")
    _assert_error("enum Event { Point(int, int) } var event = Point(1)", "E2007")
    _assert_error(
        "enum Left { LeftValue(int) } enum Right { RightValue(int) } "
        "var value = LeftValue(1) match value { RightValue(item) => print(item) }",
        "E2034",
    )
    _assert_error(
        "enum Event { Point(int, int) } var value = Point(1, 2) "
        "match value { Point(x) => print(x) }",
        "E2035",
    )
    _assert_error(
        "enum First { Shared(int) } enum Second { Shared(string) }",
        "E2033",
    )

    unsupported = _compile("enum Event { Tick() } fn main() { var event = Tick() }", "rust")
    assert not unsupported.success
    assert any(
        "does not support payload enum semantics" in (diagnostic.note or diagnostic.rendered)
        for diagnostic in unsupported.diagnostics
    ), unsupported.diagnostics

    print("[PASS] payload enums: C++/JS/Python runtime, destructuring, typing, and target gate")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_payload_enum_suite() else 1)
