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
from src.codegen.wasm_ir import BundleLowerer
from src.core.ast_nodes import ConditionalExprNode, FunctionDefNode, MatchExprNode, ReturnNode


SOURCE = '''
fn classify(x: int) -> string = if x < 0 {
    "negative"
} elif x == 0 {
    "zero"
} else {
    "positive"
}

fn choose(flag: bool) -> int = if flag { 42 } else { 7 }

fn status(code: int) -> string = match code {
    200 => "ok",
    404 => "missing",
    _ => "other"
}

fn next_code() -> int {
    print("match-subject")
    return 404
}

fn status_from_call() -> string = match next_code() {
    200 => "ok",
    404 => "missing",
    _ => "other"
}

print(classify(-1), classify(0), classify(1), choose(true), choose(false), status(200), status(404), status(500), status_from_call())
'''

WASM_SOURCE = '''
fn choose(flag: bool) -> int = if flag { 42 } else { 7 }
fn status_code(code: int) -> int = match code { 200 => 1, 404 => 2, _ => 0 }
'''
EXPECTED_OUTPUT = "match-subject\nnegative zero positive 42 7 ok missing other missing"


def _compile(target: str, source: str = SOURCE):
    result = NyxCompiler(ROOT_DIR).compile_source(
        source,
        target=target,
        filename=f"maya_surface_{target}.rove",
    )
    assert result.success, tuple(diagnostic.rendered for diagnostic in result.diagnostics)
    assert result.artifact is not None
    return result


def _run(command, *, cwd: str) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return completed.stdout.replace("\r\n", "\n").strip()


def _assert_ast_shape() -> None:
    result = NyxCompiler(ROOT_DIR).check_source(
        SOURCE,
        target="cpp",
        filename="maya_surface_ast.rove",
    )
    assert result.success, tuple(diagnostic.rendered for diagnostic in result.diagnostics)
    functions = {
        statement.name: statement
        for statement in result.ast.statements
        if isinstance(statement, FunctionDefNode)
    }
    classify = functions["classify"]
    choose = functions["choose"]
    status = functions["status"]
    assert len(classify.body) == len(choose.body) == 1
    assert isinstance(classify.body[0], ReturnNode)
    assert isinstance(classify.body[0].expr, ConditionalExprNode)
    assert len(classify.body[0].expr.elif_branches) == 1
    assert isinstance(choose.body[0], ReturnNode)
    assert isinstance(choose.body[0].expr, ConditionalExprNode)
    assert isinstance(status.body[0], ReturnNode)
    assert isinstance(status.body[0].expr, MatchExprNode)
    assert len(status.body[0].expr.cases) == 3


def _run_python(temp_dir: str) -> None:
    result = _compile("python")
    path = os.path.join(temp_dir, "maya_surface.py")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(result.artifact.content)
    assert _run([sys.executable, path], cwd=ROOT_DIR) == EXPECTED_OUTPUT


def _run_javascript(temp_dir: str) -> None:
    node = shutil.which("node")
    assert node, "Node.js is required for the JavaScript and WebAssembly Maya gates"
    result = _compile("js")
    path = os.path.join(temp_dir, "maya_surface.cjs")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(result.artifact.content)
    assert _run([node, path], cwd=ROOT_DIR) == EXPECTED_OUTPUT


def _run_cpp(temp_dir: str) -> None:
    assert CppToolchain.find_compiler(), "A C++20 compiler is required for the Maya native gate"
    result = _compile("cpp")
    cpp_path = os.path.join(temp_dir, "maya_surface.cpp")
    exe_path = os.path.join(temp_dir, "maya_surface.exe" if os.name == "nt" else "maya_surface")
    with open(cpp_path, "w", encoding="utf-8") as handle:
        handle.write(result.artifact.content)
    ok, message = CppToolchain.compile_cpp(cpp_path, exe_path)
    assert ok, message
    exit_code, output = CppToolchain.run_executable(exe_path)
    assert exit_code == 0, output
    assert output.replace("\r\n", "\n").strip() == EXPECTED_OUTPUT


def _run_rust(temp_dir: str) -> bool:
    rustc = shutil.which("rustc")
    assert rustc, "rustc is required for the Maya Rust gate"
    result = _compile("rust")
    rust_path = os.path.join(temp_dir, "maya_surface.rs")
    object_path = os.path.join(temp_dir, "maya_surface.o")
    exe_path = os.path.join(temp_dir, "maya_surface_rs.exe" if os.name == "nt" else "maya_surface_rs")
    with open(rust_path, "w", encoding="utf-8") as handle:
        handle.write(result.artifact.content)
    _run([rustc, "--edition=2021", "--emit=obj", rust_path, "-o", object_path], cwd=ROOT_DIR)
    linked = subprocess.run(
        [rustc, "--edition=2021", rust_path, "-o", exe_path],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    if linked.returncode != 0:
        linker_output = linked.stderr or linked.stdout
        if "link.exe" in linker_output and "not found" in linker_output:
            return False
        raise AssertionError(linker_output)
    assert _run([exe_path], cwd=ROOT_DIR) == EXPECTED_OUTPUT
    return True


def _run_wasm(temp_dir: str) -> None:
    node = shutil.which("node")
    assert node, "Node.js is required for the WebAssembly Maya gate"
    result = NyxCompiler(ROOT_DIR).check_source(
        WASM_SOURCE,
        target="wasm",
        filename="maya_surface_wasm.rove",
    )
    assert result.success, tuple(diagnostic.rendered for diagnostic in result.diagnostics)
    wasm = BundleLowerer(result.hir, "maya_surface").lower().to_wasm()
    wasm_path = os.path.join(temp_dir, "maya_surface.wasm")
    runner_path = os.path.join(temp_dir, "maya_surface_wasm.mjs")
    with open(wasm_path, "wb") as handle:
        handle.write(wasm)
    with open(runner_path, "w", encoding="utf-8") as handle:
        handle.write(
            "import fs from 'node:fs';\n"
            "const bytes = fs.readFileSync(process.argv[2]);\n"
            "if (!WebAssembly.validate(bytes)) throw new Error('invalid wasm');\n"
            "const { instance } = await WebAssembly.instantiate(bytes, {});\n"
            "if (instance.exports.choose(1) !== 42) throw new Error('true branch');\n"
            "if (instance.exports.choose(0) !== 7) throw new Error('false branch');\n"
            "if (instance.exports.status_code(200) !== 1) throw new Error('first match arm');\n"
            "if (instance.exports.status_code(404) !== 2) throw new Error('second match arm');\n"
            "if (instance.exports.status_code(500) !== 0) throw new Error('fallback match arm');\n"
            "console.log('42 7 1 2 0');\n"
        )
    assert _run([node, runner_path, wasm_path], cwd=ROOT_DIR) == "42 7 1 2 0"


def _assert_rejections() -> None:
    cases = (
        ("missing_else", "fn bad(flag: bool) -> int = if flag { 1 }", "E1012"),
        ("multiple_values", "fn bad(flag: bool) -> int = if flag { 1 2 } else { 0 }", "E1013"),
        ("non_bool_condition", "fn bad() -> int = if 1 { 1 } else { 0 }", "E2013"),
        ("branch_type_mismatch", 'fn bad(flag: bool) -> int = if flag { 1 } else { "no" }', "E2001"),
        ("match_missing_fallback", "fn bad(x: int) -> int = match x { 1 => 10 }", "E2014"),
        ("match_nonfinal_fallback", "fn bad(x: int) -> int = match x { _ => 0, 1 => 10 }", "E2014"),
        ("match_identifier_pattern", "fn bad(x: int) -> int = match x { value => 10, _ => 0 }", "E2015"),
        ("match_arm_type_mismatch", 'fn bad(x: int) -> int = match x { 1 => 10, _ => "no" }', "E2001"),
        ("match_missing_comma", "fn bad(x: int) -> int = match x { 1 => 10 _ => 0 }", "E1014"),
    )
    compiler = NyxCompiler(ROOT_DIR)
    for name, source, expected_code in cases:
        result = compiler.check_source(source, target="cpp", filename=f"{name}.rove")
        assert not result.success, name
        assert any(diagnostic.code == expected_code for diagnostic in result.diagnostics), (
            name,
            expected_code,
            tuple(diagnostic.code for diagnostic in result.diagnostics),
        )


def run_maya_surface_suite() -> bool:
    print("=" * 70)
    print("NYX MAYA EXPRESSIVE SURFACE / VALUE EXPRESSION GATE")
    print("=" * 70)
    _assert_ast_shape()
    _assert_rejections()
    with tempfile.TemporaryDirectory(prefix="nyx_maya_surface_") as temp_dir:
        _run_python(temp_dir)
        _run_javascript(temp_dir)
        _run_cpp(temp_dir)
        rust_runtime = _run_rust(temp_dir)
        _run_wasm(temp_dir)
    rust_gate = "Rust runtime" if rust_runtime else "Rust object/type/borrow check (MSVC linker unavailable)"
    print(
        "[PASS] Expression-bodied fn + lazy if/match expressions across "
        f"Python/JS/C++/{rust_gate}/WASM"
    )
    return True


if __name__ == "__main__":
    sys.exit(0 if run_maya_surface_suite() else 1)
