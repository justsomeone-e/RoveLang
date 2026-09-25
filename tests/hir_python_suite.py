import os
from pathlib import Path
import subprocess
import sys


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.codegen.hir_python import emit_python
from src.core import Lexer, Parser, TypeChecker
from src.ir import lower_to_hir, optimize_hir, verify_hir
from tests.battery138.run_battery import test_cases
from tests.differential_testing import TRIPLE_DIFF_CASES


def _emit(source: str, filename: str) -> str:
    tree = Parser(Lexer(source, filename).tokenize(), source, filename).parse()
    TypeChecker(tree, filename, source).check()
    hir = optimize_hir(lower_to_hir(tree, filename)).module
    verify_hir(hir)
    generated = emit_python(hir)
    compile(generated, filename + ".py", "exec")
    return generated


def _run(generated: str, timeout: int = 5) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", generated],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _canonical_battery_output(value: str) -> str:
    value = value.replace("\r\n", "\n").strip()
    return "\n".join(
        "true" if line == "True" else "false" if line == "False" else line
        for line in value.splitlines()
    )


def _run_corpus_compile() -> int:
    paths = []
    for relative in ("tests/battery138", "tests/bughunt"):
        paths.extend(sorted(Path(ROOT_DIR, relative).glob("*.rove")))
    assert len(paths) >= 162
    for path in paths:
        source = path.read_text(encoding="utf-8-sig")
        _emit(source, str(path))
    return len(paths)


def _run_battery_runtime() -> int:
    for name, source, expected_output in test_cases:
        generated = _emit(source, name + ".rove")
        runtime = _run(generated)
        assert runtime.returncode == 0, (name, runtime.stderr or runtime.stdout)
        actual = _canonical_battery_output(runtime.stdout)
        expected = _canonical_battery_output(expected_output or "")
        if name == "unsafe_05_memdump_call":
            assert actual.endswith(expected), (name, expected, actual)
        else:
            assert actual == expected, (name, expected, actual)
    return len(test_cases)


def _run_differential_fixtures() -> int:
    for name, source in TRIPLE_DIFF_CASES:
        first = _run(_emit(source, name + ".rove"))
        second = _run(_emit(source, name + ".rove"))
        assert first.returncode == second.returncode == 0
        assert first.stdout == second.stdout
    return len(TRIPLE_DIFF_CASES)


def _run_semantic_repairs() -> None:
    source = """
var value = 1
if true {
    var value = 2
    print(value)
}
print(value)

fn lifecycle(skip: bool) {
    defer print("first")
    if skip { return }
    defer print("second")
    print("body")
}

lifecycle(false)
lifecycle(true)
print(-7 / 3, -7 % 3)
"""
    generated = _emit(source, "semantic_repairs.rove")
    runtime = _run(generated)
    assert runtime.returncode == 0, runtime.stderr or runtime.stdout
    assert runtime.stdout.replace("\r\n", "\n").strip() == (
        "2\n"
        "1\n"
        "body\n"
        "second\n"
        "first\n"
        "first\n"
        "-2 -1"
    )
    assert ROOT_DIR.replace("\\", "/") not in generated.replace("\\", "/")


def _run_value_and_unicode_semantics() -> None:
    source = '''
struct Box { value: int }

fn mutate(values: Array<int>) {
    set values[0] = 7
}

fn main() {
    var first: Array<int> = [1, 2]
    var second: Array<int> = first
    set second[0] = 9
    print(first[0], second[0])

    var left: Box = Box(1)
    var right: Box = left
    set right.value = 9
    print(left.value, right.value)

    mutate(first)
    print(first[0])
    print("ş😀".len(), "ş😀"[0], "ş😀"[1])
    var joined: string = ""
    for character in "ş😀" { set joined = joined + character }
    print(joined)
    var text = "ş😀e\\u0301\\0"
    print(len(text), text.len(), text.length(), text.size(), text[0], text[1], text[2])
    print(text[3] == "\\u0301", text[4] == "\\0")
    print(len(text[-1]), len(text[5]), len(text[9223372036854775807]))
    var empty = ""
    print(len(empty[0]), len(empty[-1]))
}
'''
    runtime = _run(_emit(source, "value_unicode_semantics.rove"))
    assert runtime.returncode == 0, runtime.stderr or runtime.stdout
    assert runtime.stdout.replace("\r\n", "\n").strip() == "1 9\n1 9\n1\n2 ş 😀\nş😀\n5 5 5 5 ş 😀 e\ntrue true\n0 0 0\n0 0"


def run_hir_python_suite() -> bool:
    print("=" * 70)
    print("ROVE HIR-AUTHORITATIVE PYTHON BACKEND")
    print("=" * 70)
    corpus_count = _run_corpus_compile()
    runtime_count = _run_battery_runtime()
    differential_count = _run_differential_fixtures()
    _run_semantic_repairs()
    _run_value_and_unicode_semantics()
    print(
        f"[PASS] {corpus_count} compiled, {runtime_count} runtime cases, "
        f"{differential_count} deterministic fixtures, shadowing/defer/int semantics"
    )
    return True


if __name__ == "__main__":
    sys.exit(0 if run_hir_python_suite() else 1)
