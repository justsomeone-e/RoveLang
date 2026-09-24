from dataclasses import replace
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api import NyxCompiler
from src.mir import (
    AggregateRValue,
    AssignStatement,
    BorrowRValue,
    ConstOperand,
    ConstantIndexProjection,
    CopyOperand,
    DeinitStatement,
    DropTerminator,
    DerefProjection,
    FieldProjection,
    GotoTerminator,
    LayoutEngine,
    MIRFunctionBuilder,
    MIRInterpreter,
    MIRModule,
    MIRSpan,
    MIRStructDef,
    MIRType,
    MoveOperand,
    Place,
    ReturnTerminator,
    ReleaseStatement,
    RetainStatement,
    UseRValue,
    check_c_adapter,
    classify_function_abi,
    collect_mir_issues,
    from_json,
    lower_hir_to_mir,
    to_json,
)
from src.mir.model import MIRField


def _lower(path: Path):
    checked = NyxCompiler(str(ROOT)).check_file(str(path))
    assert checked.success and checked.hir is not None, checked.diagnostics
    return lower_hir_to_mir(checked.hir)


def _ownership_modules() -> tuple[MIRModule, MIRModule]:
    span = MIRSpan("ownership.rove", 1, 1)
    int_type = MIRType("int")

    moved = MIRFunctionBuilder("moved", "function::moved", MIRType("void"), span)
    value = moved.new_local("value", int_type)
    sink = moved.new_local("sink", int_type)
    after = moved.new_local("after", int_type)
    entry = moved.new_block()
    moved.push_statement(entry, AssignStatement(
        Place(value), UseRValue(ConstOperand(int_type, 7)), span
    ))
    moved.push_statement(entry, AssignStatement(
        Place(sink), UseRValue(MoveOperand(Place(value))), span
    ))
    moved.push_statement(entry, AssignStatement(
        Place(after), UseRValue(CopyOperand(Place(value))), span
    ))
    moved.set_terminator(entry, ReturnTerminator(span))

    dropped = MIRFunctionBuilder("dropped", "function::dropped", MIRType("void"), span)
    drop_value = dropped.new_local("value", int_type)
    first = dropped.new_block()
    second = dropped.new_block()
    exit_block = dropped.new_block()
    dropped.push_statement(first, AssignStatement(
        Place(drop_value), UseRValue(ConstOperand(int_type, 9)), span
    ))
    dropped.set_terminator(first, DropTerminator(Place(drop_value), second, None, span))
    dropped.set_terminator(second, DropTerminator(Place(drop_value), exit_block, None, span))
    dropped.set_terminator(exit_block, ReturnTerminator(span))

    return (
        MIRModule("ownership.rove", "cpp", (moved.finish(),)),
        MIRModule("ownership.rove", "cpp", (dropped.finish(),)),
    )


def _borrow_module() -> MIRModule:
    span = MIRSpan("borrow.rove", 1, 1)
    int_type = MIRType("int")
    pointer_type = MIRType("int", pointer=True)
    builder = MIRFunctionBuilder("borrowed", "function::borrowed", int_type, span)
    value = builder.new_local("value", int_type)
    reference = builder.new_local("reference", pointer_type)
    entry = builder.new_block()
    builder.push_statement(entry, AssignStatement(
        Place(value), UseRValue(ConstOperand(int_type, 42)), span
    ))
    builder.push_statement(entry, AssignStatement(
        Place(reference), BorrowRValue(Place(value), False, pointer_type), span
    ))
    builder.push_statement(entry, RetainStatement(Place(reference), span))
    builder.push_statement(entry, AssignStatement(
        Place(0),
        UseRValue(CopyOperand(Place(reference, (DerefProjection(),)))),
        span,
    ))
    builder.push_statement(entry, ReleaseStatement(Place(reference), span))
    builder.set_terminator(entry, ReturnTerminator(span))
    return MIRModule("borrow.rove", "cpp", (builder.finish(),))


def _projected_replacement_modules() -> tuple[MIRModule, MIRModule]:
    span = MIRSpan("projected-replacement.rove", 1, 1)
    string_type = MIRType("string")
    array_type = MIRType("Array", (string_type,))
    projected = Place(1, (ConstantIndexProjection(0),))

    valid = MIRFunctionBuilder("valid", "function::valid", MIRType("void"), span)
    values = valid.new_local("values", array_type)
    entry = valid.new_block()
    valid.push_statement(entry, AssignStatement(
        Place(values),
        AggregateRValue("array", "Array", (ConstOperand(string_type, "old"),), array_type),
        span,
    ))
    valid.push_statement(entry, DeinitStatement(projected, span))
    valid.push_statement(entry, AssignStatement(
        projected, UseRValue(ConstOperand(string_type, "new")), span
    ))
    valid.set_terminator(entry, ReturnTerminator(span))

    invalid = MIRFunctionBuilder("invalid", "function::invalid", MIRType("void"), span)
    invalid_values = invalid.new_local("values", array_type)
    invalid_entry = invalid.new_block()
    invalid.push_statement(invalid_entry, AssignStatement(
        Place(invalid_values),
        AggregateRValue("array", "Array", (ConstOperand(string_type, "old"),), array_type),
        span,
    ))
    invalid.push_statement(
        invalid_entry,
        DeinitStatement(Place(invalid_values, (ConstantIndexProjection(0),)), span),
    )
    invalid.set_terminator(invalid_entry, ReturnTerminator(span))

    return (
        MIRModule("projected-replacement.rove", "cpp", (valid.finish(),)),
        MIRModule("projected-replacement.rove", "cpp", (invalid.finish(),)),
    )


def _projected_move_module() -> MIRModule:
    span = MIRSpan("projected-move.rove", 1, 1)
    int_type = MIRType("int")
    cell_type = MIRType("Cell")
    definition = MIRStructDef(
        "Cell", "type::Cell", (MIRField("value", int_type),)
    )
    builder = MIRFunctionBuilder("projected_move", "function::projected_move", MIRType("void"), span)
    cell = builder.new_local("cell", cell_type)
    sink = builder.new_local("sink", int_type)
    entry = builder.new_block()
    builder.push_statement(entry, AssignStatement(
        Place(cell),
        AggregateRValue(
            "struct", "Cell", (ConstOperand(int_type, 7),), cell_type, ("value",)
        ),
        span,
    ))
    builder.push_statement(entry, AssignStatement(
        Place(sink),
        UseRValue(MoveOperand(Place(cell, (FieldProjection("value"),)))),
        span,
    ))
    builder.set_terminator(entry, ReturnTerminator(span))
    return MIRModule(
        "projected-move.rove", "cpp", (builder.finish(),), (definition,)
    )


def run_mir_memory_abi_suite() -> bool:
    print("=" * 70)
    print("NYX M4 MIR AGGREGATE / MEMORY / ABI CONTRACT")
    print("=" * 70)

    aggregate_module = _lower(ROOT / "tests" / "fixtures" / "mir" / "m4_aggregates.rove")
    assert from_json(to_json(aggregate_module)) == aggregate_module
    observed = MIRInterpreter(aggregate_module).run().output
    assert observed == ("1 9 9", "Nyx", "9", "2", "3"), observed
    assert any(
        isinstance(statement, DeinitStatement)
        and aggregate_module.functions[-1].locals[statement.place.local].kind == "temporary"
        for block in aggregate_module.functions[-1].blocks
        for statement in block.statements
    ), "safe-navigation/null-coalescing temporaries must close on every branch"

    payload_module = _lower(ROOT / "tour" / "solutions" / "17_results" / "result01.rove")
    assert MIRInterpreter(payload_module).run().output == ("hello",)
    static_enum_module = _lower(ROOT / "tour" / "solutions" / "07_enums" / "enums03.rove")
    assert MIRInterpreter(static_enum_module).run().output == (
        "Traffic light transitions verified!",
    )

    moved, dropped = _ownership_modules()
    assert "MIR0801" in {issue.code for issue in collect_mir_issues(moved)}
    assert "MIR0804" in {issue.code for issue in collect_mir_issues(dropped)}
    borrowed = _borrow_module()
    assert not collect_mir_issues(borrowed)
    assert MIRInterpreter(borrowed).run("borrowed").value == 42
    projected_valid, projected_invalid = _projected_replacement_modules()
    assert not collect_mir_issues(projected_valid)
    assert "MIR0805" in {
        issue.code for issue in collect_mir_issues(projected_invalid)
    }
    assert "MIR0806" in {
        issue.code for issue in collect_mir_issues(_projected_move_module())
    }

    point = next(
        definition
        for definition in aggregate_module.type_definitions
        if isinstance(definition, MIRStructDef) and definition.name == "Point"
    )
    native = LayoutEngine(aggregate_module, "cpp")
    wasm = LayoutEngine(aggregate_module, "wasm")
    point_native = native.layout_of(MIRType(point.name))
    assert (point_native.size, point_native.alignment) == (16, 8)
    assert tuple(field.offset for field in point_native.fields) == (0, 8)
    assert native.layout_of(MIRType("Array", (MIRType("int"),))).size == 24
    assert wasm.layout_of(MIRType("Array", (MIRType("int"),))).size == 12

    synthetic = aggregate_module.functions[-1]
    point_return = replace(
        synthetic,
        locals=(replace(synthetic.locals[0], type=MIRType("Point")),) + synthetic.locals[1:],
    )
    direct = classify_function_abi(
        replace(aggregate_module, functions=(point_return,)),
        point_return,
        "cpp",
    )
    assert direct.result.mode == "direct"
    assert check_c_adapter(aggregate_module, point_return).result_reason == "compatible"

    print(
        "[PASS] aggregate value copies, projected places, collection iteration, enum payloads, "
        "move/drop analysis, atomic projected replacement, projected-move rejection, x64/wasm32 layouts, "
        "calling convention and C adapters"
    )
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_mir_memory_abi_suite() else 1)
