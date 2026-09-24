"""Runtime, parity, and diagnostic contract for destructuring declarations."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.api import RoveCompiler
from src.codegen.cpp_toolchain import CppToolchain


PROGRAM = r'''
struct Point {
    x: int,
    y: int
}

fn make_pair() -> Array<int> {
    print("pair-called")
    return [20, 22]
}

fn make_point() -> Point {
    print("point-called")
    return Point(3, 4)
}

fn main() {
    let [left, right] = make_pair()
    let Point(x, y) = make_point()
    let [first, _] = [7, 9]
    print(left + right, x + y, first)
}
'''

COLLISION_PROGRAMS = (
    (
        "before",
        "let rove_internal_destructure_2 = 5; let [left, right] = [20, 22]; "
        "fn main() { print(rove_internal_destructure_2 + left + right) }",
    ),
    (
        "after",
        "let [left, right] = [20, 22]; let rove_internal_destructure_1 = 5; "
        "fn main() { print(rove_internal_destructure_1 + left + right) }",
    ),
    (
        "nested_sanitized",
        "fn main() { let nyx$internal$destructure$2 = 5; "
        "let [left, right] = [20, 22]; "
        "print(nyx$internal$destructure$2 + left + right) }",
    ),
)


def _compile(source: str, target: str):
    return RoveCompiler(ROOT_DIR).compile_source(
        source,
        target=target,
        filename=os.path.join(ROOT_DIR, f"destructuring-{target}.rove"),
    )


def _run(target: str, content: str, directory: str, stem: str) -> tuple[int, str]:
    if target == "cpp":
        source_path = os.path.join(directory, f"{stem}.cpp")
        executable_path = os.path.join(directory, f"{stem}.exe")
        with open(source_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        compiled, message = CppToolchain.compile_cpp(source_path, executable_path)
        assert compiled, message
        return CppToolchain.run_executable(executable_path)

    if target == "js":
        runtime = shutil.which("node")
        assert runtime is not None, "Node.js is required for destructuring coverage"
        path = os.path.join(directory, f"{stem}.js")
        command = [runtime, path]
    else:
        path = os.path.join(directory, f"{stem}.py")
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


def run_destructuring_suite() -> bool:
    with tempfile.TemporaryDirectory(prefix="nyx_destructuring_") as directory:
        for target in ("cpp", "js", "python"):
            result = _compile(PROGRAM, target)
            assert result.success, result.diagnostics
            assert result.artifact is not None
            return_code, output = _run(target, result.artifact.content, directory, f"destructuring_{target}")
            assert return_code == 0, f"{target} destructuring failed:\n{output}"
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            assert lines == ["pair-called", "point-called", "42 7 7"], (target, lines)

            top_level = _compile("let [a, b] = [5, 6]; fn main() { print(a + b) }", target)
            assert top_level.success, top_level.diagnostics
            assert top_level.artifact is not None
            top_code, top_output = _run(
                target, top_level.artifact.content, directory, f"destructuring_top_{target}"
            )
            assert top_code == 0, (target, top_output)
            assert [line.strip() for line in top_output.splitlines() if line.strip()] == ["11"]

            short = _compile("fn main() { let [a, b] = [1]; print(a, b) }", target)
            assert short.success, short.diagnostics
            assert short.artifact is not None
            short_code, short_output = _run(
                target, short.artifact.content, directory, f"destructuring_short_{target}"
            )
            assert short_code != 0, (target, short_output)
            assert "Array destructuring requires at least 2 elements" in short_output, (target, short_output)

            short_top = _compile("let [a, b] = [1]; fn main() { print(a, b) }", target)
            assert short_top.success, short_top.diagnostics
            assert short_top.artifact is not None
            short_top_code, short_top_output = _run(
                target, short_top.artifact.content, directory, f"destructuring_short_top_{target}"
            )
            assert short_top_code != 0, (target, short_top_output)
            assert "Array destructuring requires at least 2 elements" in short_top_output, (
                target,
                short_top_output,
            )

            for collision_name, collision_source in COLLISION_PROGRAMS:
                collision = _compile(collision_source, target)
                assert collision.success, (target, collision_name, collision.diagnostics)
                assert collision.artifact is not None
                collision_code, collision_output = _run(
                    target,
                    collision.artifact.content,
                    directory,
                    f"destructuring_collision_{collision_name}_{target}",
                )
                assert collision_code == 0, (target, collision_name, collision_output)
                assert [line.strip() for line in collision_output.splitlines() if line.strip()] == ["47"], (
                    target,
                    collision_name,
                    collision_output,
                )

    _assert_error("fn main() { let [a, b] = 42 }", "E2048")
    _assert_error(
        "struct Point { x: int, y: int } fn main() { let Point(x) = Point(1, 2) }",
        "E2050",
    )
    _assert_error(
        "struct Point { x: int, y: int } struct Size { width: int, height: int } "
        "fn main() { let Point(x, y) = Size(1, 2) }",
        "E2049",
    )

    print("[PASS] destructuring: runtime parity, hygienic temps, top-level ordering, bounds, and diagnostics")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_destructuring_suite() else 1)
