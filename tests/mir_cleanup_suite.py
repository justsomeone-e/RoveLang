from pathlib import Path
import sys
from dataclasses import replace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api import RoveCompiler
from src.ir.model import IRLiteral
from src.ir.types import STRING
from src.ir.verifier import collect_hir_issues
from src.mir import MIRInterpreter, lower_hir_to_mir, print_mir, verify_mir
from src.mir.model import (
    AssignStatement,
    BinaryRValue,
    CallTerminator,
    CopyOperand,
    DeinitStatement,
    MoveOperand,
    ReturnTerminator,
    ThrowTerminator,
    UseRValue,
)


FIXTURE = ROOT / "tests" / "fixtures" / "mir" / "m3_control.rove"
LIFETIME_FIXTURE = ROOT / "tests" / "fixtures" / "mir" / "m3_lexical_cleanup.rove"
PATTERN_FIXTURE = ROOT / "tests" / "fixtures" / "mir" / "m3_match_pattern_cleanup.rove"


def _function(module, name: str):
    return next(function for function in module.functions if function.name == name)


def _local_ids(function, name: str) -> tuple[int, ...]:
    return tuple(local.id for local in function.locals if local.name == name)


def _deinit_count(function, local_ids: tuple[int, ...]) -> int:
    return sum(
        isinstance(statement, DeinitStatement)
        and statement.place.local in local_ids
        and not statement.place.projections
        for block in function.blocks
        for statement in block.statements
    )


def _assert_defer_precedes_deinit(function, label: str, local_name: str) -> None:
    local_ids = set(_local_ids(function, local_name))
    assert local_ids, (function.name, local_name)
    defer_continuations = {
        block.terminator.target
        for block in function.blocks
        if isinstance(block.terminator, CallTerminator)
        and block.terminator.function == "builtin::print"
        and block.terminator.arguments
        and getattr(block.terminator.arguments[0], "value", None) == label
        and block.terminator.target is not None
    }
    assert defer_continuations, (function.name, label)
    assert any(
        block.id in defer_continuations
        and any(
            isinstance(statement, DeinitStatement)
            and statement.place.local in local_ids
            for statement in block.statements
        )
        for block in function.blocks
    ), (function.name, label, local_name)


def _run_lexical_cleanup_contract() -> None:
    result = RoveCompiler(str(ROOT)).check_file(str(LIFETIME_FIXTURE), target="cpp")
    assert result.success and result.hir is not None, result.diagnostics
    mir = lower_hir_to_mir(result.hir)
    verify_mir(mir)

    replace = _function(mir, "replace_value")
    value_ids = _local_ids(replace, "value")
    assert len(value_ids) == 1
    # One deinit protects the overwrite; another closes the lexical lifetime.
    assert _deinit_count(replace, value_ids) == 2
    _assert_defer_precedes_deinit(replace, "replace-defer", "value")

    returned = _function(mir, "return_value")
    assert _deinit_count(returned, _local_ids(returned, "local")) == 1
    assert _deinit_count(returned, _local_ids(returned, "value")) == 1
    _assert_defer_precedes_deinit(returned, "return-defer", "local")

    loop = _function(mir, "loop_values")
    loop_value_ids = _local_ids(loop, "value")
    assert len(loop_value_ids) == 1
    # Normal fallthrough, continue, and break each close an initialized element.
    assert _deinit_count(loop, loop_value_ids) == 3
    _assert_defer_precedes_deinit(loop, "loop-defer", "value")

    caught = _function(mir, "catch_value")
    assert _deinit_count(caught, _local_ids(caught, "doomed")) >= 1
    assert _deinit_count(caught, _local_ids(caught, "err")) == 1
    _assert_defer_precedes_deinit(caught, "throw-defer", "doomed")

    thrown_local = _function(mir, "throw_owned_value")
    message_ids = set(_local_ids(thrown_local, "message"))
    assert len(message_ids) == 1
    _assert_defer_precedes_deinit(thrown_local, "throw-value-defer", "message")
    assert any(
        isinstance(block.terminator.value, MoveOperand)
        and block.terminator.value.place.local not in message_ids
        for block in thrown_local.blocks
        if isinstance(block.terminator, ThrowTerminator)
    ), "throw must preserve its value before lexical cleanup"

    argument_unwind = _function(mir, "argument_unwind")
    failing_argument = next(
        block.terminator for block in argument_unwind.blocks
        if isinstance(block.terminator, CallTerminator)
        and block.terminator.function == "function::fail_argument"
    )
    assert failing_argument.unwind is not None
    assert any(
        isinstance(statement, DeinitStatement)
        and argument_unwind.locals[statement.place.local].type.name == "Array"
        for statement in argument_unwind.blocks[failing_argument.unwind].statements
    ), "an earlier owned argument must be cleaned if a later argument throws"
    consuming_calls = [
        block.terminator for block in argument_unwind.blocks
        if isinstance(block.terminator, CallTerminator)
        and block.terminator.function == "function::consume_argument"
    ]
    assert len(consuming_calls) == 2
    assert all(isinstance(call.arguments[0], MoveOperand) for call in consuming_calls)

    propagated_argument = _function(mir, "propagate_result_argument")
    assert any(
        isinstance(block.terminator, ReturnTerminator)
        and any(
            isinstance(statement, DeinitStatement)
            and propagated_argument.locals[statement.place.local].type.name == "Array"
            for statement in block.statements
        )
        for block in propagated_argument.blocks
    ), "Result propagation must clean earlier owned arguments on early return"

    ordered_operands = _function(mir, "ordered_operand_unwind")
    failed_operands = [
        block.terminator for block in ordered_operands.blocks
        if isinstance(block.terminator, CallTerminator)
        and block.terminator.function == "function::fail_operand_text"
    ]
    assert len(failed_operands) == 2
    for failed_operand in failed_operands:
        assert failed_operand.unwind is not None
        assert any(
            isinstance(statement, DeinitStatement)
            and ordered_operands.locals[statement.place.local].type.name == "string"
            for statement in ordered_operands.blocks[failed_operand.unwind].statements
        ), "binary and array operands must close earlier string temporaries"

    call_unwind = _function(mir, "call_unwind")
    assert _deinit_count(call_unwind, _local_ids(call_unwind, "owned")) >= 1
    assert _deinit_count(call_unwind, _local_ids(call_unwind, "err")) == 1
    _assert_defer_precedes_deinit(call_unwind, "call-defer", "owned")

    unhandled = _function(mir, "unhandled_unwind")
    exploding_call = next(
        block.terminator
        for block in unhandled.blocks
        if isinstance(block.terminator, CallTerminator)
        and block.terminator.function == "function::relay_unwind"
    )
    assert exploding_call.unwind is not None
    assert exploding_call.error_destination is not None
    assert _deinit_count(unhandled, _local_ids(unhandled, "value")) >= 1
    _assert_defer_precedes_deinit(unhandled, "unhandled-defer", "value")

    matched = _function(mir, "match_value")
    message_ids = _local_ids(matched, "message")
    assert len(message_ids) == 1
    assert _deinit_count(matched, message_ids) == 1

    temporary_transfers = []
    for function in mir.functions:
        temporary_ids = {
            local.id for local in function.locals if local.kind == "temporary"
        }
        temporary_transfers.extend(
            statement.value.operand
            for block in function.blocks
            for statement in block.statements
            if isinstance(statement, AssignStatement)
            and isinstance(statement.value, UseRValue)
            and isinstance(statement.value.operand, MoveOperand)
            and statement.value.operand.place.local in temporary_ids
        )
    assert temporary_transfers

    discarded = _function(mir, "discard_temporary")
    discarded_temporary_ids = {
        local.id for local in discarded.locals if local.kind == "temporary"
    }
    assert any(
        isinstance(statement, DeinitStatement)
        and statement.place.local in discarded_temporary_ids
        for block in discarded.blocks
        for statement in block.statements
    )

    coalesced = _function(mir, "coalesce_owned_fallback")
    fallback_arrays = {
        local.id for local in coalesced.locals
        if local.kind == "temporary" and local.type.name == "Array"
    }
    assert fallback_arrays
    assert any(
        isinstance(statement, AssignStatement)
        and isinstance(statement.value, UseRValue)
        and isinstance(statement.value.operand, MoveOperand)
        and statement.value.operand.place.local in fallback_arrays
        for block in coalesced.blocks
        for statement in block.statements
    ), "an owned null-coalescing fallback must transfer instead of leaking a copy"

    executed = MIRInterpreter(mir).run()
    assert executed.output == (
        "replace-defer second",
        "return-defer argument",
        "returned",
        "loop-body keep",
        "loop-defer keep",
        "loop-defer skip",
        "loop-defer stop",
        "throw-defer try-local",
        "caught boom",
        "throw-value-defer owned-boom",
        "owned-caught owned-boom",
        "arg-caught arg-fail",
        "arg-consumed 2 3",
        "Err(argument-error) Ok(5)",
        "binary-caught operand-fail",
        "array-caught operand-fail",
        "call-defer call-local",
        "call-caught call-boom",
        "err bad",
        "4 2",
    ), executed.output


def _run_match_pattern_cleanup_contract() -> None:
    result = RoveCompiler(str(ROOT)).check_file(str(PATTERN_FIXTURE), target="cpp")
    assert result.success and result.hir is not None, result.diagnostics
    mir = lower_hir_to_mir(result.hir)
    verify_mir(mir)
    main = _function(mir, "main")
    compared_temporaries = []
    for block in main.blocks:
        for index, statement in enumerate(block.statements):
            if not (
                isinstance(statement, AssignStatement)
                and isinstance(statement.value, BinaryRValue)
                and statement.value.op == "=="
                and isinstance(statement.value.right, CopyOperand)
            ):
                continue
            local = statement.value.right.place.local
            if main.locals[local].kind != "temporary":
                continue
            compared_temporaries.append(local)
            assert index + 1 < len(block.statements)
            cleanup = block.statements[index + 1]
            assert isinstance(cleanup, DeinitStatement)
            assert cleanup.place.local == local
    assert len(compared_temporaries) == 3, compared_temporaries

    values = _local_ids(main, "values")
    assert len(values) == 1, values
    owned_binding = values[0]
    assert any(
        isinstance(statement, AssignStatement)
        and statement.place.local == owned_binding
        and isinstance(statement.value, UseRValue)
        and isinstance(statement.value.operand, MoveOperand)
        and main.locals[statement.value.operand.place.local].kind == "temporary"
        for block in main.blocks for statement in block.statements
    )
    assert _deinit_count(main, values) == 1
    assert _deinit_count(main, _local_ids(main, "other")) == 1

    for pattern in ("_", "value", '"_"'):
        source = f'fn main() {{ match 7 {{ {pattern} => print("first"), 1 => print("second") }} }}'
        rejected = RoveCompiler(str(ROOT)).check_source(source, target="cpp")
        assert not rejected.success
        assert any(diagnostic.code == "E2016" for diagnostic in rejected.diagnostics)

    incompatible_patterns = (
        ('fn main() { match 7 { "seven" => print("bad") } }', "E2001"),
        ('fn main() { match 7 { 7.0 => print("bad") } }', "E2001"),
        ('fn pattern() -> string { return "seven" } '
         'fn main() { match 7 { pattern() => print("bad") } }', "E2001"),
        ('fn main() { match 7 { Ok(value) => print(value) } }', "E2034"),
        ('fn choose(x: int) -> int = match x { 7.0 => 1, _ => 0 }', "E2001"),
    )
    for source, expected_code in incompatible_patterns:
        rejected = RoveCompiler(str(ROOT)).check_source(source, target="cpp")
        assert not rejected.success, source
        assert any(
            diagnostic.code == expected_code for diagnostic in rejected.diagnostics
        ), (source, rejected.diagnostics)

    checked = RoveCompiler(str(ROOT)).check_source(
        'fn main() { match 7 { 7 => print("ok") } }', target="cpp"
    )
    assert checked.success and checked.hir is not None
    function = next(item for item in checked.hir.items if item.name == "main")
    match_statement = function.body[0]
    case = match_statement.cases[0]
    invalid_case = replace(
        case, pattern=IRLiteral(case.pattern.span, STRING, "seven")
    )
    invalid_function = replace(
        function,
        body=(replace(match_statement, cases=(invalid_case,)),),
    )
    invalid_hir = replace(checked.hir, items=(invalid_function,))
    assert any(
        issue.code == "HIR0006" and "Match statement pattern" in issue.message
        for issue in collect_hir_issues(invalid_hir)
    )

    failure_call = next(
        block.terminator for block in main.blocks
        if isinstance(block.terminator, CallTerminator)
        and block.terminator.function == "function::fail"
    )
    assert failure_call.unwind is not None and failure_call.target is not None
    continuation = main.blocks[failure_call.target]
    comparison = next(
        statement.value for statement in continuation.statements
        if isinstance(statement, AssignStatement)
        and isinstance(statement.value, BinaryRValue)
        and statement.value.op == "=="
    )
    assert isinstance(comparison.left, CopyOperand)
    assert any(
        isinstance(statement, DeinitStatement)
        and statement.place.local == comparison.left.place.local
        for statement in main.blocks[failure_call.unwind].statements
    )
    assert MIRInterpreter(mir).run().output == (
        "stmt-hit", "expr-hit", "caught boom", "wildcard", "legacy-wildcard", "owned 3 2",
        "result Err(bad)", "bound borrowed", "source borrowed", "returned 2",
    )


def run_mir_cleanup_suite() -> bool:
    print("=" * 70)
    print("ROVE M3 MIR CANONICAL CONTROL / CLEANUP")
    print("=" * 70)

    result = RoveCompiler(str(ROOT)).check_file(str(FIXTURE), target="cpp")
    assert result.success and result.hir is not None, result.diagnostics
    mir = lower_hir_to_mir(result.hir)
    verify_mir(mir)
    text = print_mir(mir)
    for forbidden in ("IRIf", "IRFor", "IRGuard", "IRDefer", "IRTryCatch", "IRResultPropagate"):
        assert forbidden not in text

    executed = MIRInterpreter(mir).run()
    assert executed.output == (
        "false",
        "true",
        "10",
        "two",
        "10",
        "caught boom",
        "checked-cleanup",
        "use-cleanup",
        "Ok(8)",
        "checked-cleanup",
        "use-cleanup",
        "Err(bad)",
    ), executed.output

    propagated = _function(mir, "use_checked")
    temporary_by_id = {
        local.id: local for local in propagated.locals if local.kind == "temporary"
    }
    result_temporaries = {
        local_id for local_id, local in temporary_by_id.items()
        if local.type.name == "Result"
    }
    tag_temporaries = {
        local_id for local_id, local in temporary_by_id.items()
        if local.type.name == "string"
    }
    assert result_temporaries and tag_temporaries
    assert any(
        isinstance(statement, DeinitStatement)
        and statement.place.local in result_temporaries
        for block in propagated.blocks
        for statement in block.statements
    )
    assert sum(
        isinstance(statement, DeinitStatement)
        and statement.place.local in tag_temporaries
        for block in propagated.blocks
        for statement in block.statements
    ) >= 2

    _run_lexical_cleanup_contract()
    _run_match_pattern_cleanup_contract()

    print("[PASS] canonical control, lexical cleanup, unwind trampolines, and owned temporary transfer")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_mir_cleanup_suite() else 1)
