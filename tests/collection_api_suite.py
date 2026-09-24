"""Typed map/filter/fold contracts across the supported HIR backends."""

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
fn main() {
    var items = [1, 2, 3, 4]
    var doubled = map(items, item => item * 2)
    var selected = filter(doubled, item => item > 4)
    var total = fold(selected, 0, (sum, item) => sum + item)
    print(total)
}
'''


def _compile(source: str, target: str):
    return NyxCompiler(ROOT_DIR).compile_source(
        source,
        target=target,
        filename=os.path.join(ROOT_DIR, f"collection-api-{target}.rove"),
    )


def _run(target: str, content: str, directory: str) -> tuple[int, str]:
    if target == "cpp":
        source_path = os.path.join(directory, "collection_api.cpp")
        executable_path = os.path.join(directory, "collection_api.exe")
        with open(source_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        compiled, message = CppToolchain.compile_cpp(source_path, executable_path)
        assert compiled, message
        return CppToolchain.run_executable(executable_path)

    if target == "js":
        runtime = shutil.which("node")
        assert runtime is not None, "Node.js is required for collection API coverage"
        path = os.path.join(directory, "collection_api.js")
        command = [runtime, path]
    else:
        path = os.path.join(directory, "collection_api.py")
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


def run_collection_api_suite() -> bool:
    with tempfile.TemporaryDirectory(prefix="nyx_collection_api_") as directory:
        for target in ("cpp", "js", "python"):
            result = _compile(PROGRAM, target)
            assert result.success, result.diagnostics
            assert result.artifact is not None
            return_code, output = _run(target, result.artifact.content, directory)
            assert return_code == 0, f"{target} collection API failed:\n{output}"
            assert output.strip() == "14", (target, output)

    _assert_error('fn main() { var value = map("no", item => item) }', "E2040")
    _assert_error("fn main() { var value = map([1], 1) }", "E2042")
    _assert_error("fn main() { var value = filter([1], item => item) }", "E2043")
    _assert_error("fn main() { var value = fold([1], 0, (sum, item) => \"bad\") }", "E2044")

    unsupported = _compile("fn main() { print(fold([1, 2], 0, (a, b) => a + b)) }", "rust")
    assert not unsupported.success
    assert any(
        "does not support collection combinators" in (diagnostic.note or diagnostic.rendered)
        for diagnostic in unsupported.diagnostics
    ), unsupported.diagnostics

    print("[PASS] Typed map/filter/fold: C++/JS/Python runtime, diagnostics, and target gate")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_collection_api_suite() else 1)
