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
    emit_legalized_c17,
    emit_legalized_javascript,
    emit_legalized_llvm,
    emit_legalized_python,
    emit_legalized_rust,
    legalize_mir,
    lower_hir_to_mir,
    verify_mir,
)
from src.mir.model import CallTerminator, ConstOperand
from src.mir.types import MIRType
from tests.mir_legalization_suite import (
    _assert_rust_runtime, _compile_and_run_c17, _compile_and_run_cpp, _compile_and_run_llvm,
    _run_javascript, _run_python,
)


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
C17_SOURCE = '''
struct Cell { label: string, nums: Array<int> }
fn main() {
    print(map([true, false], item => !item))
    print(filter([1.5, 2.5], item => item > 2.0))
    print(map(["a", "b"], item => item + "!"))
    var cells = [Cell("a", [1]), Cell("b", [2])]
    var picked = filter(cells, item => item.nums[0] > 1)
    print(picked[0].label)
    var copied = map(cells, item => item)
    set copied[0].nums[0] = 9
    print(cells[0].nums[0], copied[0].nums[0])
}
'''
C17_EXPECTED = "[false, true]\n[2.5]\n[a!, b!]\nb\n1 9\n"
LLVM_SOURCE = '''
struct Cell { label: string, nums: Array<int> }
fn main() {
    print(map([true, false], item => !item))
    print(filter([1.5, 2.5], item => item > 2.0))
    print(map(["a", "b"], item => item))
    var cells = [Cell("a", [1]), Cell("b", [2])]
    var picked = filter(cells, item => item.nums[0] > 1)
    print(picked[0].label)
    var copied = map(cells, item => item)
    set copied[0].nums[0] = 9
    print(cells[0].nums[0], copied[0].nums[0])
}
'''
LLVM_EXPECTED = "[false, true]\n[2.5]\n[a, b]\nb\n1 9\n"
LLVM_ZERO_SIZED_SOURCE = '''
struct Empty {}
fn main() {
    var values = map([Empty(), Empty()], item => item)
    print(len(values))
    print(len(filter(values, item => true)))
}
'''
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
    legalize_mir(module, "wasm")
    assert "\n".join(MIRInterpreter(module).run().output) + "\n" == EXPECTED
    for emit, run in (
        (emit_legalized_cpp, _compile_and_run_cpp),
        (emit_legalized_c17, _compile_and_run_c17),
        (emit_legalized_llvm, _compile_and_run_llvm),
        (emit_legalized_javascript, _run_javascript),
        (emit_legalized_python, _run_python),
    ):
        assert run(emit(module)) == EXPECTED
    _assert_rust_runtime(emit_legalized_rust(module), EXPECTED)
    c17_checked = compiler.check_source(
        C17_SOURCE, filename="m6_c17_map_filter.rove", target="cpp",
    )
    assert c17_checked.success, c17_checked.diagnostics
    c17_module = lower_hir_to_mir(c17_checked.hir)
    assert "\n".join(MIRInterpreter(c17_module).run().output) + "\n" == C17_EXPECTED
    assert _compile_and_run_c17(emit_legalized_c17(c17_module)) == C17_EXPECTED
    llvm_checked = compiler.check_source(
        LLVM_SOURCE, filename="m6_llvm_map_filter.rove", target="cpp",
    )
    assert llvm_checked.success, llvm_checked.diagnostics
    llvm_module = lower_hir_to_mir(llvm_checked.hir)
    assert "\n".join(MIRInterpreter(llvm_module).run().output) + "\n" == LLVM_EXPECTED
    assert _compile_and_run_llvm(emit_legalized_llvm(llvm_module)) == LLVM_EXPECTED
    empty_checked = compiler.check_source(
        LLVM_ZERO_SIZED_SOURCE, filename="m6_llvm_empty_struct.rove", target="cpp",
    )
    assert empty_checked.success, empty_checked.diagnostics
    empty_module = lower_hir_to_mir(empty_checked.hir)
    assert "\n".join(MIRInterpreter(empty_module).run().output) + "\n" == "2\n2\n"
    assert _compile_and_run_llvm(emit_legalized_llvm(empty_module)) == "2\n2\n"
    bad_unary = compiler.check_source(
        "fn main() { print(map([true], item => ~item)) }",
        filename="m6_map_invalid_unary.rove", target="cpp",
    )
    assert not bad_unary.success
    assert any(item.code == "E2005" for item in bad_unary.diagnostics), bad_unary.diagnostics
    throwing = compiler.check_source(
        THROW_SOURCE, filename="m6_map_filter_throw.rove", target="cpp",
    )
    assert throwing.success, throwing.diagnostics
    throwing_module = lower_hir_to_mir(throwing.hir)
    assert "\n".join(MIRInterpreter(throwing_module).run().output) + "\n" == THROW_EXPECTED
    for target in ("c", "llvm"):
        try:
            legalize_mir(throwing_module, target)
            raise AssertionError(f"{target} unexpectedly legalized map/filter unwind")
        except MIRLegalizationError as error:
            assert any(issue.code == "MIRG1011" for issue in error.issues), error.issues
    for emit, run in (
        (emit_legalized_cpp, _compile_and_run_cpp),
        (emit_legalized_javascript, _run_javascript),
        (emit_legalized_python, _run_python),
    ):
        assert run(emit(throwing_module)) == THROW_EXPECTED
    _assert_rust_runtime(emit_legalized_rust(throwing_module), THROW_EXPECTED)
    print("[PASS] MIR map/filter typing, target gates, source order, nested ownership, C17/C++/LLVM/JS/Python parity, and Rust gate")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_mir_map_filter_suite() else 1)
