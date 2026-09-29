from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api import RoveCompiler
from src.mir import (
    MIRInterpreter, MIRLoweringError, emit_legalized_cpp, emit_legalized_javascript,
    emit_legalized_python, emit_legalized_rust, lower_hir_to_mir,
)
from src.mir.model import CallTerminator
from tests.mir_legalization_suite import (
    _assert_rust_runtime, _compile_and_run_cpp, _run_javascript, _run_python,
)


def run_mir_fold_suite() -> bool:
    source = (ROOT / "tests/fixtures/mir/m6_fold.rove").read_text(encoding="utf-8")
    compiler = RoveCompiler(str(ROOT))
    checked = compiler.check_source(source, filename="m6_fold.rove", target="cpp")
    assert checked.success, checked.diagnostics
    module = lower_hir_to_mir(checked.hir)
    assert not any(
        isinstance(block.terminator, CallTerminator)
        and block.terminator.function == "builtin::fold"
        for function in module.functions for block in function.blocks
    )
    expected = "source\ninitial\n12\n7\nab\n11\n1 9\n23\nreducer failed\n"
    assert "\n".join(MIRInterpreter(module).run().output) + "\n" == expected
    for emit, run in (
        (emit_legalized_cpp, _compile_and_run_cpp),
        (emit_legalized_javascript, _run_javascript),
        (emit_legalized_python, _run_python),
    ):
        assert run(emit(module)) == expected
    _assert_rust_runtime(emit_legalized_rust(module), expected)
    for source, code in (
        ('fn main() { print(fold(1, 0, (a, b) => a + b)) }', "E2040"),
        ('fn main() { print(fold([1], 0, item => item)) }', "E2042"),
        ('fn main() { print(fold([1], 0, (a, b) => "wrong")) }', "E2044"),
    ):
        rejected = compiler.check_source(source, filename="invalid-fold.rove", target="cpp")
        assert not rejected.success
        assert any(item.code == code for item in rejected.diagnostics), rejected.diagnostics
    local_return = compiler.check_source(
        'fn read() -> Result<int, string> { return Err("bad") }\n'
        'fn probe() -> Result<int, string> { let initial: Result<int, string> = Ok(0); '
        'return fold([1], initial, (acc, item) => Ok(read()?)) }\n',
        filename="fold-local-return.rove", target="cpp",
    )
    assert local_return.success, local_return.diagnostics
    try:
        lower_hir_to_mir(local_return.hir)
        raise AssertionError("Reducer-local return was inlined into the enclosing function")
    except MIRLoweringError as error:
        assert "closure control lowering" in str(error)
    print("[PASS] MIR fold captures, evaluation order, empty/nested/owned reducers, unwind, and C++/Rust/JS/Python gates")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_mir_fold_suite() else 1)
