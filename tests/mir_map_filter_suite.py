"""Canonical MIR lowering and backend parity for immediate map/filter callbacks."""

from pathlib import Path
import sys
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api import RoveCompiler
from src.mir import (
    MIRInterpreter,
    MIRLegalizationError,
    MIRVerificationError,
    emit_legalized_cpp,
    emit_legalized_javascript,
    emit_legalized_python,
    legalize_mir,
    lower_hir_to_mir,
    verify_mir,
)
from src.mir.model import CallTerminator, ConstOperand
from src.mir.types import MIRType
from tests.mir_legalization_suite import _compile_and_run_cpp, _run_javascript, _run_python


SOURCE = '''
fn items() -> Array<int> { print("source"); return [1, 2, 3] }
fn scale(value: int, amount: int) -> int { return value + amount }
fn main() {
    let amount = 5
    var mapped = map(items(), item => scale(item, amount))
    var selected = filter(mapped, item => item > 6)
    print(mapped[0], selected[0], len(selected))
    let empty: Array<int> = []
    print(len(map(empty, item => item + amount)))
    var originals = [[1], [2]]
    var copies = map(originals, item => item)
    set copies[0][0] = 9
    print(originals[0][0], copies[0][0])
}
'''

EXPECTED = "source\n6 7 2\n0\n1 9\n"
THROW_SOURCE = '''
fn fail_map(value: int) -> int {
    if value == 2 { throw "map failed" }
    return value
}
fn fail_filter(value: int) -> bool {
    if value == 2 { throw "filter failed" }
    return true
}
fn main() {
    try { print(map([1, 2, 3], item => fail_map(item))) }
    catch error { print(error) }
    try { print(filter([1, 2, 3], item => fail_filter(item))) }
    catch error { print(error) }
}
'''
THROW_EXPECTED = "map failed\nfilter failed\n"


def run_mir_map_filter_suite() -> bool:
    compiler = RoveCompiler(str(ROOT))
    checked = compiler.check_source(SOURCE, filename="m6_map_filter.rove", target="cpp")
    assert checked.success, checked.diagnostics
    module = lower_hir_to_mir(checked.hir)
    remaining_combinator_calls = {
        "builtin::map", "builtin::filter",
    }
    assert not any(
        isinstance(block.terminator, CallTerminator)
        and block.terminator.function in remaining_combinator_calls
        for function in module.functions for block in function.blocks
    )
    assert any(
        isinstance(block.terminator, CallTerminator)
        and block.terminator.function == "intrinsic::rove_array_push"
        for function in module.functions for block in function.blocks
    )
    function, block = next(
        (function, block)
        for function in module.functions for block in function.blocks
        if isinstance(block.terminator, CallTerminator)
        and block.terminator.function == "intrinsic::rove_array_push"
    )
    malformed_call = replace(
        block.terminator,
        arguments=(block.terminator.arguments[0], ConstOperand(MIRType("string"), "bad")),
    )
    malformed_function = replace(
        function,
        blocks=tuple(
            replace(candidate, terminator=malformed_call) if candidate.id == block.id else candidate
            for candidate in function.blocks
        ),
    )
    malformed_module = replace(
        module,
        functions=tuple(
            malformed_function if candidate.symbol == function.symbol else candidate
            for candidate in module.functions
        ),
    )
    try:
        verify_mir(malformed_module)
        raise AssertionError("MIR verifier accepted an array push with the wrong element type")
    except MIRVerificationError as error:
        assert any(issue.code == "MIR0409" for issue in error.issues), error.issues
    for target in ("wasm", "rust", "c", "llvm"):
        try:
            legalize_mir(module, target)
            raise AssertionError(f"{target} unexpectedly legalized array push")
        except MIRLegalizationError as error:
            assert any(issue.code == "MIRG1007" for issue in error.issues), error.issues
    assert "\n".join(MIRInterpreter(module).run().output) + "\n" == EXPECTED
    for emit, run in (
        (emit_legalized_cpp, _compile_and_run_cpp),
        (emit_legalized_javascript, _run_javascript),
        (emit_legalized_python, _run_python),
    ):
        assert run(emit(module)) == EXPECTED
    throwing = compiler.check_source(
        THROW_SOURCE, filename="m6_map_filter_throw.rove", target="cpp",
    )
    assert throwing.success, throwing.diagnostics
    throwing_module = lower_hir_to_mir(throwing.hir)
    assert "\n".join(MIRInterpreter(throwing_module).run().output) + "\n" == THROW_EXPECTED
    for emit, run in (
        (emit_legalized_cpp, _compile_and_run_cpp),
        (emit_legalized_javascript, _run_javascript),
        (emit_legalized_python, _run_python),
    ):
        assert run(emit(throwing_module)) == THROW_EXPECTED
    print("[PASS] MIR map/filter typing, target gates, source order, empty input, ownership, and C++/JS/Python parity")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_mir_map_filter_suite() else 1)
