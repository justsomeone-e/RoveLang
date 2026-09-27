from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


from src import CompilerPlugin, RoveCompiler
from src.ir import HIRTransformer, IRExpr, IRLiteral
from tests.numeric_semantics_suite import SOURCE as NUMERIC_SOURCE


RUSTC = shutil.which("rustc")


def _rustc_metadata(source_path: str, output_path: str) -> subprocess.CompletedProcess:
    assert RUSTC is not None, "rustc is required for the HIR Rust suite"
    return subprocess.run(
        [RUSTC, "--edition=2021", "--emit=metadata", source_path, "-o", output_path],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def _run_corpus_contract(compiler: RoveCompiler) -> tuple[int, int]:
    paths = []
    for relative in ("tests/battery138", "tests/bughunt"):
        paths.extend(sorted(Path(ROOT_DIR, relative).glob("*.rove")))
    assert len(paths) >= 162

    emitted = []
    rejected = []
    for path in paths:
        result = compiler.compile_source(
            path.read_text(encoding="utf-8-sig"),
            target="rust",
            filename=str(path),
        )
        if not result.success:
            rejected.append((path.name, result))
            continue
        assert result.artifact is not None
        assert result.artifact.kind == "rust"
        assert "canonical typed HIR v1" in result.artifact.content
        emitted.append((path.name, result.artifact.content))

    assert {name for name, _ in rejected} == {
        "10_1_try_catch.rove",
        "unsafe_03_spawn_bg.rove",
        "unsafe_04_channel_create.rove",
    }, [(name, result.diagnostics) for name, result in rejected]
    for rejected_name, rejected_result in rejected:
        assert rejected_result.diagnostics
        assert rejected_result.diagnostics[0].code == "E3001"
        expected_note = {
            "10_1_try_catch.rove": "exception semantics",
            "unsafe_03_spawn_bg.rove": "spawn semantics",
            "unsafe_04_channel_create.rove": "channel semantics",
        }[rejected_name]
        assert expected_note in rejected_result.diagnostics[0].note

    workers = max(1, min(8, os.cpu_count() or 1))
    with tempfile.TemporaryDirectory(prefix="nyx_hir_rust_corpus_") as directory:
        def compile_case(index: int, name: str, source: str) -> tuple[str, subprocess.CompletedProcess]:
            source_path = os.path.join(directory, f"case_{index:03d}.rs")
            output_path = os.path.join(directory, f"case_{index:03d}.rmeta")
            with open(source_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(source)
            return name, _rustc_metadata(source_path, output_path)

        failures = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(compile_case, index, name, source)
                for index, (name, source) in enumerate(emitted)
            ]
            for future in as_completed(futures):
                name, process = future.result()
                if process.returncode != 0:
                    failures.append((name, process.stderr or process.stdout))
        assert not failures, "\n".join(
            f"{name}: {message[:2000]}" for name, message in sorted(failures)
        )
    return len(emitted), len(rejected)


def _compile_metadata(compiler: RoveCompiler, source: str, name: str) -> str:
    result = compiler.compile_source(source, target="rust", filename=name + ".rove")
    assert result.success, result.diagnostics
    assert result.artifact is not None
    generated = result.artifact.content
    with tempfile.TemporaryDirectory(prefix="nyx_hir_rust_contract_") as directory:
        source_path = os.path.join(directory, name + ".rs")
        output_path = os.path.join(directory, name + ".rmeta")
        with open(source_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(generated)
        process = _rustc_metadata(source_path, output_path)
        assert process.returncode == 0, process.stderr or process.stdout
    return generated


class _ReplaceFortyOne(HIRTransformer):
    def transform_expr(self, node: IRExpr) -> IRExpr:
        transformed = super().transform_expr(node)
        if isinstance(transformed, IRLiteral) and transformed.value == 41:
            return replace(transformed, value=42)
        return transformed


class _HIRRewritePlugin(CompilerPlugin):
    name = "rust-hir-rewrite"

    def transform_hir(self, context, hir):
        assert context.target == "rust"
        return _ReplaceFortyOne().transform_module(hir)


def _run_semantic_contracts(compiler: RoveCompiler) -> None:
    trait_source = """
trait Show { fn show(self) -> string }
struct Point { x: int, y: int }
impl Show for Point {
    fn show(self) -> string {
        return "(" + to_string(self.x) + "," + to_string(self.y) + ")"
    }
}
fn main() { print("trait:", Point(10, 20).show()) }
"""
    _compile_metadata(compiler, trait_source, "trait_contract")

    dynamic_source = """
fn dynamic(value) { return value }
fn main() { if dynamic(1) { print("truthiness leaked") } }
"""
    dynamic = _compile_metadata(compiler, dynamic_source, "dynamic_bool")
    assert "_rove_expect_bool(RoveValue::Int(" in dynamic

    defer_source = """
fn lifecycle(skip: bool) {
    defer print("first")
    if skip { return }
    defer print("second")
    print("body")
}
fn main() { lifecycle(false); lifecycle(true) }
"""
    deferred = _compile_metadata(compiler, defer_source, "defer_contract")
    assert deferred.count('"first".to_string()') >= 2
    assert deferred.find('"second".to_string()', deferred.find("pub fn lifecycle")) < deferred.rfind('"first".to_string()')

    propagate_source = """
fn source(ok: bool) -> Result<int, string> {
    if ok { return Ok(40) }
    return Err("boom")
}
fn calculate(ok: bool) -> Result<int, string> {
    defer print("cleanup")
    var value = source(ok)?
    return Ok(value + 2)
}
fn main() {
    match calculate(false) {
        Ok(value) => print(value),
        Err(error) => print(error)
    }
}
"""
    propagated = _compile_metadata(compiler, propagate_source, "result_propagation_contract")
    error_branch = propagated.find("RoveResult::Err(_rove_propagate_error_")
    cleanup = propagated.find('"cleanup".to_string()', error_branch)
    early_return = propagated.find("return RoveResult::Err(_rove_propagate_error_", error_branch)
    assert 0 <= error_branch < cleanup < early_return

    numeric = _compile_metadata(compiler, NUMERIC_SOURCE, "numeric_contract")
    for marker in ("wrapping_add", "wrapping_sub", "wrapping_mul", "_rove_i64_div", "_rove_i64_mod"):
        assert marker in numeric, marker

    global_update = _compile_metadata(
        compiler,
        "var total = 0\nfor value in 1..3 { total = total + value }\nprint(total)",
        "global_update_locking",
    )
    value_pos = global_update.find("let _rove_value_")
    write_lock_pos = global_update.find("*_rove_global_total.lock().unwrap() =", value_pos)
    assert value_pos >= 0 and write_lock_pos > value_pos
    read_lock_pos = global_update.find("_rove_global_total.lock().unwrap()", value_pos)
    value_end_pos = global_update.find(";", value_pos)
    assert value_pos < read_lock_pos < value_end_pos < write_lock_pos

    plugin_compiler = RoveCompiler(ROOT_DIR, plugins=(_HIRRewritePlugin(),))
    rewritten = _compile_metadata(plugin_compiler, "fn main() { print(41) }", "hir_plugin")
    assert "42_i64" in rewritten and "41_i64" not in rewritten

    first = compiler.compile_source(
        "fn main() { print(\"deterministic\", 42) }",
        target="rust",
        filename="deterministic.rove",
    )
    second = compiler.compile_source(
        "fn main() { print(\"deterministic\", 42) }",
        target="rust",
        filename="deterministic.rove",
    )
    assert first.success and second.success
    assert first.artifact is not None and second.artifact is not None
    assert first.artifact.content == second.artifact.content
    assert ROOT_DIR.replace("\\", "/") not in first.artifact.content.replace("\\", "/")


def run_hir_rust_suite() -> bool:
    print("=" * 70)
    print("ROVE HIR-AUTHORITATIVE RUST 2021 BACKEND")
    print("=" * 70)
    assert RUSTC is not None, "rustc is required for the HIR Rust suite"
    compiler = RoveCompiler(ROOT_DIR)
    emitted, rejected = _run_corpus_contract(compiler)
    _run_semantic_contracts(compiler)
    print(
        f"[PASS] {emitted} corpus programs passed rustc metadata/borrow checking; "
        f"{rejected} unsupported capability programs rejected; typed-HIR plugin, "
        "trait, defer, dynamic-bool, numeric, and deterministic emission contracts passed"
    )
    return True


if __name__ == "__main__":
    sys.exit(0 if run_hir_rust_suite() else 1)
