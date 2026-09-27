from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import sys
import tempfile


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.codegen.cpp_toolchain import CppToolchain
from src.codegen.hir_cpp import emit_cpp
from src.core import Lexer, Parser, TypeChecker
from src.ir import lower_to_hir, optimize_hir, verify_hir
from src.self_host.bootstrap import _driver_source
from tests.battery138.run_battery import test_cases


_NATIVE_EXPECTED_OVERRIDES = {
    # Native cpp exposes actual address dereference semantics.  The legacy
    # Python battery oracle intentionally returned its fixed emulation value.
    "unsafe_01_basic_addr": "42",
}


def _emit(source: str, filename: str) -> str:
    tree = Parser(Lexer(source, filename).tokenize(), source, filename).parse()
    TypeChecker(tree, filename, source).check()
    hir = optimize_hir(lower_to_hir(tree, filename)).module
    verify_hir(hir)
    return emit_cpp(hir)


def _canonical_battery_output(value: str) -> str:
    value = value.replace("\r\n", "\n").strip()
    return "\n".join(
        "true" if line == "True" else "false" if line == "False" else line
        for line in value.splitlines()
    )


def _run_corpus_emission() -> int:
    paths = []
    for relative in ("tests/battery138", "tests/bughunt"):
        paths.extend(sorted(Path(ROOT_DIR, relative).glob("*.rove")))
    assert len(paths) >= 162
    for path in paths:
        _emit(path.read_text(encoding="utf-8-sig"), str(path))
    return len(paths)


def _compile_and_run_case(
    directory: str,
    index: int,
    name: str,
    source: str,
    expected_output: str,
) -> str:
    generated = _emit(source, name + ".rove")
    cpp_path = os.path.join(directory, f"{index:03d}_{name}.cpp")
    executable = os.path.join(directory, f"{index:03d}_{name}.exe")
    with open(cpp_path, "w", encoding="utf-8") as handle:
        handle.write(generated)
    compiled, message = CppToolchain.compile_cpp(cpp_path, executable)
    assert compiled, (name, message)
    return_code, output = CppToolchain.run_executable(executable)
    assert return_code == 0, (name, return_code, output)
    actual = _canonical_battery_output(output)
    expected = _canonical_battery_output(
        _NATIVE_EXPECTED_OVERRIDES.get(name, expected_output or "")
    )
    if name == "unsafe_05_memdump_call":
        assert actual.endswith(expected), (name, expected, actual)
    else:
        assert actual == expected, (name, expected, actual)
    return name


def _run_native_battery() -> int:
    workers = max(1, min(8, os.cpu_count() or 1))
    with tempfile.TemporaryDirectory(prefix="nyx_hir_cpp_battery_") as directory:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _compile_and_run_case,
                    directory,
                    index,
                    name,
                    source,
                    expected,
                ): name
                for index, (name, source, expected) in enumerate(test_cases)
            }
            failures = []
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as error:
                    details = str(error).replace("\r\n", "\n")
                    failures.append((futures[future], details[:1600]))
            assert not failures, "\n".join(f"{name}: {error}" for name, error in failures)
    return len(test_cases)


def _run_stage1_smoke() -> None:
    source = _driver_source("fn add(a: int, b: int) -> int { return a + b; }")
    generated = _emit(source, "<hir-stage1-smoke>")
    with tempfile.TemporaryDirectory(prefix="nyx_hir_cpp_stage1_") as directory:
        cpp_path = os.path.join(directory, "stage1.cpp")
        executable = os.path.join(directory, "stage1.exe")
        with open(cpp_path, "w", encoding="utf-8") as handle:
            handle.write(generated)
        compiled, message = CppToolchain.compile_cpp(cpp_path, executable)
        assert compiled, message
        return_code, output = CppToolchain.run_executable(executable)
        assert return_code == 0, output
        assert "SELF_HOST_OK" in output
        assert "int64_t add(int64_t a, int64_t b)" in output


def _run_cli_args_smoke() -> None:
    source = "fn main() { var values: Array<string> = args(); print(values[1]); }"
    generated = _emit(source, "<hir-cli-args-smoke>")
    assert "GetConsoleProcessList(process_ids, 2) == 1" in generated
    assert "    _rove_pause_if_standalone_console();\n    return 0;" in generated
    with tempfile.TemporaryDirectory(prefix="nyx_hir_cpp_args_") as directory:
        cpp_path = os.path.join(directory, "args.cpp")
        executable = os.path.join(directory, "args.exe")
        with open(cpp_path, "w", encoding="utf-8") as handle:
            handle.write(generated)
        compiled, message = CppToolchain.compile_cpp(cpp_path, executable)
        assert compiled, message
        return_code, output = CppToolchain.run_executable(executable, ("nyx-arg",))
        assert return_code == 0, output
        assert output.strip() == "nyx-arg", output


def _run_compact_runtime_smoke() -> None:
    generated = _emit('"Hello World" |> print', "<hir-compact-runtime>")
    assert generated.startswith(
        "// Auto-generated by Rove Compiler (cpp HIR backend, compact runtime)"
    )
    assert len(generated.splitlines()) < 160
    assert "RoveIterator" not in generated
    assert "NYX_WEAK" not in generated
    with tempfile.TemporaryDirectory(prefix="nyx_hir_cpp_compact_") as directory:
        cpp_path = os.path.join(directory, "compact.cpp")
        executable = os.path.join(directory, "compact.exe")
        with open(cpp_path, "w", encoding="utf-8") as handle:
            handle.write(generated)
        compiled, message = CppToolchain.compile_cpp(cpp_path, executable)
        assert compiled, message
        return_code, output = CppToolchain.run_executable(executable)
        assert return_code == 0, output
        assert output.strip() == "Hello World", output

    full_runtime = _emit(
        "fn main() { var value: int = 1; print(value + 2) }",
        "<hir-full-runtime-fallback>",
    )
    assert "cpp HIR backend, compact runtime" not in full_runtime
    assert "_rove_i64_add" in full_runtime


def _run_recursive_struct_constructor_contract() -> None:
    source = (
        "struct FunctionParam { defaults: Array<ASTNode> } "
        "struct ASTNode { params: Array<FunctionParam> } "
        "fn main() { print(42) }"
    )
    generated = _emit(source, "<hir-recursive-structs>")
    assert "FunctionParam();" in generated
    assert "std::vector<ASTNode> defaults;" in generated
    assert "std::vector<ASTNode> defaults{};" not in generated
    assert "FunctionParam::FunctionParam() : defaults() {}" in generated
    assert not any(
        line.strip() == "FunctionParam() = default;"
        for line in generated.splitlines()
    )


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
    generated = _emit(source, "value_unicode_semantics.rove")
    with tempfile.TemporaryDirectory(prefix="nyx_value_unicode_") as directory:
        cpp_path = os.path.join(directory, "semantics.cpp")
        executable = os.path.join(directory, "semantics.exe")
        with open(cpp_path, "w", encoding="utf-8") as handle:
            handle.write(generated)
        compiled, message = CppToolchain.compile_cpp(cpp_path, executable)
        assert compiled, message
        return_code, output = CppToolchain.run_executable(executable)
        assert return_code == 0, output
        assert output.replace("\r\n", "\n").strip() == "1 9\n1 9\n1\n2 ş 😀\nş😀\n5 5 5 5 ş 😀 e\ntrue true\n0 0 0\n0 0"


def run_hir_cpp_suite() -> bool:
    print("=" * 70)
    print("ROVE HIR-AUTHORITATIVE C++20 NATIVE BACKEND")
    print("=" * 70)
    compiler = CppToolchain.find_compiler()
    assert compiler is not None, "A working C++20 compiler is required for the HIR C++ suite"
    corpus_count = _run_corpus_emission()
    runtime_count = _run_native_battery()
    _run_stage1_smoke()
    _run_cli_args_smoke()
    _run_compact_runtime_smoke()
    _run_recursive_struct_constructor_contract()
    _run_value_and_unicode_semantics()
    print(
        f"[PASS] {corpus_count} emitted, {runtime_count} native runtime cases, "
        "Rove-authored stage1 frontend and argv runtime compiled and executed"
    )
    return True


if __name__ == "__main__":
    sys.exit(0 if run_hir_cpp_suite() else 1)
