from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api import RoveCompiler
from src.mir import (
    AggregateRValue,
    AssignStatement,
    ConstOperand,
    CopyOperand,
    DiscriminantRValue,
    DropTerminator,
    GotoTerminator,
    MIRBasicBlock,
    MIRFunctionBuilder,
    MIRLocal,
    MIRLoweringError,
    MIRModule,
    MIRPassContract,
    MIRPassManager,
    MIRSpan,
    MIRType,
    MIRVerificationError,
    PayloadRValue,
    Place,
    ReturnTerminator,
    SuspendTerminator,
    UseRValue,
    collect_mir_issues,
    elaborate_coroutine,
    fingerprint,
    from_json,
    lower_hir_skeleton,
    lower_hir_to_mir,
    print_mir,
    to_json,
    verify_mir,
)
from src.mir.model import (
    IndexProjection,
    MIREnumDef,
    MIREnumVariant,
    MIRField,
    MIRStructDef,
    MoveOperand,
)


def _valid_module() -> MIRModule:
    span = MIRSpan("example.rove", 1, 1)
    int_type = MIRType("int")
    builder = MIRFunctionBuilder("identity", "module::fn::identity", int_type, span)
    parameter = builder.new_local("value", int_type, "parameter")
    temporary = builder.new_local("copy", int_type)
    entry = builder.new_block()
    exit_block = builder.new_block()
    builder.push_statement(
        entry,
        AssignStatement(Place(temporary), UseRValue(ConstOperand(int_type, 7)), span),
    )
    builder.set_terminator(entry, GotoTerminator(exit_block, span))
    builder.set_terminator(exit_block, ReturnTerminator(span))
    function = builder.finish()
    assert function.parameters == (parameter,)
    return MIRModule("example.rove", "cpp", (function,))


class _IdentityPass:
    name = "identity"

    def run(self, module: MIRModule) -> MIRModule:
        return module


class _PreservingIdentityPass:
    name = "preserving-identity"
    contract = MIRPassContract(
        required_analyses=("effects",),
        preserved_analyses=("effects",),
        invalidated_analyses=(),
        preserved_invariants=("verified_mir",),
    )

    def run(self, module: MIRModule) -> MIRModule:
        return module


def run_mir_suite() -> bool:
    print("=" * 70)
    print("ROVE M1 EXPERIMENTAL MIR CONTRACT")
    print("=" * 70)

    module = _valid_module()
    verify_mir(module)
    canonical = to_json(module)
    assert " " not in canonical
    assert from_json(canonical) == module
    assert to_json(from_json(canonical)) == canonical
    assert fingerprint(from_json(canonical)) == fingerprint(module)

    rendered = print_mir(module)
    assert "fn identity [module::fn::identity](_1)" in rendered
    assert "bb0:" in rendered and "goto -> bb1" in rendered and "return" in rendered
    assert "effects [unannotated]" in rendered
    assert print_mir(from_json(canonical)) == rendered

    pass_result = MIRPassManager((_IdentityPass(),)).run(module)
    assert pass_result.module == module and len(pass_result.records) == 1
    assert not pass_result.records[0].changed
    assert pass_result.records[0].before_fingerprint == pass_result.records[0].after_fingerprint
    assert pass_result.records[0].invalidated_analyses == ("*",)

    preserving = MIRPassManager((_PreservingIdentityPass(),)).run(module)
    preserving_record = preserving.records[0]
    assert preserving_record.required_analyses == ("effects",)
    assert preserving_record.preserved_analyses == ("effects",)
    assert preserving_record.invalidated_analyses == ()
    assert preserving_record.preserved_invariants == ("verified_mir",)

    try:
        MIRPassContract(
            preserved_analyses=("effects",),
            invalidated_analyses=("effects",),
        )
        raise AssertionError("MIR pass contract accepted contradictory analysis policy")
    except ValueError as error:
        assert "preserves and invalidates" in str(error)

    function = module.functions[0]
    bad_target = replace(
        module,
        functions=(replace(
            function,
            blocks=(
                replace(function.blocks[0], terminator=GotoTerminator(99, function.span)),
                function.blocks[1],
            ),
        ),),
    )
    assert {issue.code for issue in collect_mir_issues(bad_target)} == {"MIR0601"}

    bad_assignment = replace(
        module,
        functions=(replace(
            function,
            blocks=(
                replace(
                    function.blocks[0],
                    statements=(AssignStatement(
                        Place(2),
                        UseRValue(ConstOperand(MIRType("string"), "wrong")),
                        function.span,
                    ),),
                ),
                function.blocks[1],
            ),
        ),),
    )
    assert "MIR0300" in {issue.code for issue in collect_mir_issues(bad_assignment)}

    int_type = MIRType("int")
    string_type = MIRType("string")
    choice_type = MIRType("Choice")
    result_type = MIRType("Result", (int_type, string_type))
    option_type = MIRType("Option", (int_type,))
    choice_definition = MIREnumDef(
        "Choice", "type::Choice", (MIREnumVariant("Value", (int_type,)),)
    )
    for kind, name, aggregate_type, operands, definitions, expected_code in (
        ("enum", "Value", MIRType("Missing"), (ConstOperand(int_type, 7),), (), "MIR0508"),
        (
            "enum", "Missing", choice_type, (ConstOperand(int_type, 7),),
            (choice_definition,), "MIR0509",
        ),
        ("enum", "Value", choice_type, (), (choice_definition,), "MIR0510"),
        (
            "enum", "Value", MIRType("Choice", optional=True),
            (ConstOperand(int_type, 7),), (choice_definition,), "MIR0520",
        ),
        (
            "enum", "Value", choice_type, (ConstOperand(string_type, "wrong"),),
            (choice_definition,), "MIR0514",
        ),
        (
            "result", "Ok", MIRType("Result", (int_type,)),
            (ConstOperand(int_type, 7),), (), "MIR0511",
        ),
        (
            "result", "Ok", MIRType("Result", (int_type, string_type), optional=True),
            (ConstOperand(int_type, 7),), (), "MIR0511",
        ),
        ("result", "Other", result_type, (ConstOperand(int_type, 7),), (), "MIR0512"),
        ("result", "Ok", result_type, (), (), "MIR0513"),
        ("result", "Ok", result_type, (ConstOperand(string_type, "wrong"),), (), "MIR0515"),
        (
            "result", "Err", result_type,
            (ConstOperand(MIRType("string"), "bad"), ConstOperand(int_type, 7)),
            (), "MIR0513",
        ),
        ("option", "Some", MIRType("Option"), (ConstOperand(int_type, 7),), (), "MIR0516"),
        (
            "option", "Some", MIRType("Option", (int_type,), pointer=True),
            (ConstOperand(int_type, 7),), (), "MIR0516",
        ),
        ("option", "Other", option_type, (), (), "MIR0517"),
        ("option", "Some", option_type, (), (), "MIR0518"),
        ("option", "None", option_type, (ConstOperand(int_type, 7),), (), "MIR0518"),
        ("option", "Some", option_type, (ConstOperand(string_type, "wrong"),), (), "MIR0519"),
    ):
        tagged = MIRFunctionBuilder("tagged", "module::fn::tagged", MIRType("void"), function.span)
        result = tagged.new_local("value", aggregate_type)
        tagged_entry = tagged.new_block()
        tagged.push_statement(tagged_entry, AssignStatement(
            Place(result), AggregateRValue(kind, name, operands, aggregate_type), function.span
        ))
        tagged.set_terminator(tagged_entry, ReturnTerminator(function.span))
        malformed = MIRModule("invalid-aggregate.rove", "cpp", (tagged.finish(),), definitions)
        assert {issue.code for issue in collect_mir_issues(malformed)} == {expected_code}, (
            kind, name, aggregate_type
        )
        try:
            verify_mir(malformed)
            raise AssertionError("Malformed tagged aggregate passed MIR verification")
        except MIRVerificationError as error:
            assert {issue.code for issue in error.issues} == {expected_code}

    for kind, name, aggregate_type, operands in (
        ("option", "None", option_type, ()),
        ("option", "Some", option_type, (ConstOperand(int_type, 7),)),
        ("result", "Ok", MIRType("Result", (MIRType("any"), string_type)),
         (ConstOperand(int_type, 7),)),
    ):
        tagged = MIRFunctionBuilder("tagged", "module::fn::tagged", MIRType("void"), function.span)
        result = tagged.new_local("value", aggregate_type)
        tagged_entry = tagged.new_block()
        tagged.push_statement(tagged_entry, AssignStatement(
            Place(result), AggregateRValue(kind, name, operands, aggregate_type), function.span
        ))
        tagged.set_terminator(tagged_entry, ReturnTerminator(function.span))
        verify_mir(MIRModule("valid-aggregate.rove", "cpp", (tagged.finish(),)))

    cell_type = MIRType("Cell")
    cell_definition = MIRStructDef("Cell", "type::Cell", (MIRField("value", int_type),))
    for aggregate_type, operands, fields, expected_code in (
        (MIRType("Other"), (ConstOperand(int_type, 7),), ("value",), "MIR0526"),
        (MIRType("Cell", optional=True), (ConstOperand(int_type, 7),), ("value",), "MIR0526"),
        (cell_type, (ConstOperand(int_type, 7),), ("other",), "MIR0527"),
        (cell_type, (ConstOperand(int_type, 7),), (), "MIR0527"),
        (cell_type, (ConstOperand(string_type, "wrong"),), ("value",), "MIR0528"),
        (cell_type, (ConstOperand(MIRType("null", optional=True), None),), ("value",), "MIR0528"),
    ):
        struct = MIRFunctionBuilder("struct", "module::fn::struct", MIRType("void"), function.span)
        destination = struct.new_local("cell", aggregate_type)
        entry = struct.new_block()
        struct.push_statement(entry, AssignStatement(
            Place(destination),
            AggregateRValue("struct", "Cell", operands, aggregate_type, fields),
            function.span,
        ))
        struct.set_terminator(entry, ReturnTerminator(function.span))
        malformed = MIRModule("invalid-struct.rove", "cpp", (struct.finish(),), (cell_definition,))
        assert {issue.code for issue in collect_mir_issues(malformed)} == {expected_code}, (
            aggregate_type, operands, fields
        )

    result_field = MIRType("Result", (int_type, string_type))
    result_holder = MIRStructDef("ResultHolder", "type::ResultHolder", (MIRField("value", result_field),))
    result_builder = MIRFunctionBuilder("result_field", "module::fn::result_field", MIRType("void"), function.span)
    result_local = result_builder.new_local("holder", MIRType("ResultHolder"))
    result_entry = result_builder.new_block()
    result_builder.push_statement(result_entry, AssignStatement(
        Place(result_local),
        AggregateRValue("struct", "ResultHolder", (ConstOperand(MIRType("null", optional=True), None),),
                        MIRType("ResultHolder"), ("value",)),
        function.span,
    ))
    result_builder.set_terminator(result_entry, ReturnTerminator(function.span))
    assert {issue.code for issue in collect_mir_issues(MIRModule(
        "invalid-result-field.rove", "cpp", (result_builder.finish(),), (result_holder,)
    ))} == {"MIR0528"}

    dynamic_definition = MIRStructDef("Dynamic", "type::Dynamic", (MIRField("value", MIRType("any")),))
    optional_definition = MIRStructDef("Optional", "type::Optional", (MIRField("value", MIRType("int", optional=True)),))
    for aggregate_type, definition, operand in (
        (cell_type, cell_definition, ConstOperand(int_type, 7)),
        (MIRType("Dynamic"), dynamic_definition, ConstOperand(int_type, 7)),
        (MIRType("Optional"), optional_definition, ConstOperand(int_type, 7)),
        (MIRType("Optional"), optional_definition, ConstOperand(MIRType("null", optional=True), None)),
    ):
        struct = MIRFunctionBuilder("struct", "module::fn::struct", MIRType("void"), function.span)
        destination = struct.new_local("value", aggregate_type)
        entry = struct.new_block()
        struct.push_statement(entry, AssignStatement(
            Place(destination),
            AggregateRValue("struct", definition.name, (operand,),
                            aggregate_type, ("value",)),
            function.span,
        ))
        struct.set_terminator(entry, ReturnTerminator(function.span))
        verify_mir(MIRModule("valid-struct.rove", "cpp", (struct.finish(),), (definition,)))

    for subject_type, index, payload_type, definitions, expected_code in (
        (int_type, 0, int_type, (), "MIR0521"),
        (choice_type, 1, int_type, (choice_definition,), "MIR0522"),
        (
            MIRType("Empty"), 0, int_type,
            (MIREnumDef("Empty", "type::Empty", ()),), "MIR0522",
        ),
        (choice_type, 0, string_type, (choice_definition,), "MIR0523"),
        (result_type, 1, int_type, (), "MIR0522"),
        (result_type, 0, MIRType("bool"), (), "MIR0523"),
        (option_type, 0, string_type, (), "MIR0523"),
    ):
        extraction = MIRFunctionBuilder("extract", "module::fn::extract", MIRType("void"), function.span)
        subject = extraction.new_local("subject", subject_type, "parameter")
        destination = extraction.new_local("payload", payload_type)
        extraction_entry = extraction.new_block()
        extraction.push_statement(extraction_entry, AssignStatement(
            Place(destination), PayloadRValue(CopyOperand(Place(subject)), index, payload_type),
            function.span,
        ))
        extraction.set_terminator(extraction_entry, ReturnTerminator(function.span))
        malformed = MIRModule("invalid-payload.rove", "cpp", (extraction.finish(),), definitions)
        assert {issue.code for issue in collect_mir_issues(malformed)} == {expected_code}, (
            subject_type, index, payload_type
        )

    for subject_type, payload_type, definitions in (
        (choice_type, int_type, (choice_definition,)),
        (result_type, string_type, ()),
        (option_type, int_type, ()),
    ):
        extraction = MIRFunctionBuilder("extract", "module::fn::extract", MIRType("void"), function.span)
        subject = extraction.new_local("subject", subject_type, "parameter")
        destination = extraction.new_local("payload", payload_type)
        extraction_entry = extraction.new_block()
        extraction.push_statement(extraction_entry, AssignStatement(
            Place(destination), PayloadRValue(CopyOperand(Place(subject)), 0, payload_type),
            function.span,
        ))
        extraction.set_terminator(extraction_entry, ReturnTerminator(function.span))
        verify_mir(MIRModule("valid-payload.rove", "cpp", (extraction.finish(),), definitions))

    for subject_type, tag_type, definitions, expected_code in (
        (int_type, string_type, (), "MIR0524"),
        (MIRType("Choice", optional=True), string_type, (choice_definition,), "MIR0524"),
        (MIRType("Result", (int_type,)), string_type, (), "MIR0524"),
        (MIRType("Option"), string_type, (), "MIR0524"),
        (choice_type, int_type, (choice_definition,), "MIR0525"),
    ):
        discriminant = MIRFunctionBuilder("tag", "module::fn::tag", MIRType("void"), function.span)
        subject = discriminant.new_local("subject", subject_type, "parameter")
        destination = discriminant.new_local("tag", tag_type)
        entry = discriminant.new_block()
        discriminant.push_statement(entry, AssignStatement(
            Place(destination), DiscriminantRValue(CopyOperand(Place(subject)), tag_type),
            function.span,
        ))
        discriminant.set_terminator(entry, ReturnTerminator(function.span))
        malformed = MIRModule("invalid-discriminant.rove", "cpp", (discriminant.finish(),), definitions)
        assert {issue.code for issue in collect_mir_issues(malformed)} == {expected_code}, (
            subject_type, tag_type
        )

    for subject_type, definitions in (
        (choice_type, (choice_definition,)),
        (result_type, ()),
        (option_type, ()),
    ):
        discriminant = MIRFunctionBuilder("tag", "module::fn::tag", MIRType("void"), function.span)
        subject = discriminant.new_local("subject", subject_type, "parameter")
        destination = discriminant.new_local("tag", string_type)
        entry = discriminant.new_block()
        discriminant.push_statement(entry, AssignStatement(
            Place(destination), DiscriminantRValue(CopyOperand(Place(subject)), string_type),
            function.span,
        ))
        discriminant.set_terminator(entry, ReturnTerminator(function.span))
        verify_mir(MIRModule("valid-discriminant.rove", "cpp", (discriminant.finish(),), definitions))

    duplicate_local = replace(
        module,
        functions=(replace(
            function,
            locals=function.locals + (MIRLocal(2, "duplicate", MIRType("int"), "temporary", function.span),),
        ),),
    )
    assert "MIR0100" in {issue.code for issue in collect_mir_issues(duplicate_local)}

    # A dynamic place index is a read of its local, including on projected
    # writes and drops. The base array being initialized is not sufficient.
    for initialize_index, move_index, operation, expected_codes in (
        (False, False, "read", {"MIR0800"}),
        (False, False, "write", {"MIR0800"}),
        (False, False, "drop", {"MIR0800"}),
        (True, True, "read", {"MIR0801"}),
        (True, False, "read", set()),
    ):
        indexed = MIRFunctionBuilder("indexed", "module::fn::indexed", MIRType("void"), function.span)
        values = indexed.new_local("values", MIRType("Array", (int_type,)), "parameter")
        index = indexed.new_local("index", int_type)
        destination = indexed.new_local("destination", int_type)
        entry = indexed.new_block()
        if initialize_index:
            indexed.push_statement(entry, AssignStatement(
                Place(index), UseRValue(ConstOperand(int_type, 0)), function.span,
            ))
        if move_index:
            indexed.push_statement(entry, AssignStatement(
                Place(destination), UseRValue(MoveOperand(Place(index))), function.span,
            ))
        element = Place(values, (IndexProjection(index),))
        if operation == "read":
            indexed.push_statement(entry, AssignStatement(
                Place(destination), UseRValue(CopyOperand(element)), function.span,
            ))
            indexed.set_terminator(entry, ReturnTerminator(function.span))
        elif operation == "write":
            indexed.push_statement(entry, AssignStatement(
                element, UseRValue(ConstOperand(int_type, 9)), function.span,
            ))
            indexed.set_terminator(entry, ReturnTerminator(function.span))
        else:
            exit_block = indexed.new_block()
            indexed.set_terminator(entry, DropTerminator(element, exit_block, None, function.span))
            indexed.set_terminator(exit_block, ReturnTerminator(function.span))
        indexed_module = MIRModule("indexed.rove", "cpp", (indexed.finish(),))
        assert {issue.code for issue in collect_mir_issues(indexed_module)} == expected_codes, (
            initialize_index, move_index, operation,
        )

    for initialize_index, expected_codes in ((False, {"MIR0800"}), (True, set())):
        suspended = MIRFunctionBuilder(
            "suspended", "module::fn::suspended", MIRType("void"), function.span, is_async=True,
        )
        task = suspended.new_local("task", MIRType("Task", (int_type,)), "parameter")
        errors = suspended.new_local("errors", MIRType("Array", (string_type,)), "parameter")
        index = suspended.new_local("index", int_type)
        destination = suspended.new_local("destination", int_type)
        entry = suspended.new_block()
        resumed = suspended.new_block()
        unwound = suspended.new_block()
        if initialize_index:
            suspended.push_statement(entry, AssignStatement(
                Place(index), UseRValue(ConstOperand(int_type, 0)), function.span,
            ))
        suspended.set_terminator(entry, SuspendTerminator(
            CopyOperand(Place(task)), Place(destination), resumed, 0, function.span,
            unwind=unwound,
            error_destination=Place(errors, (IndexProjection(index),)),
        ))
        suspended.set_terminator(resumed, ReturnTerminator(function.span))
        suspended.set_terminator(unwound, ReturnTerminator(function.span))
        suspended_module = MIRModule(
            "suspended.rove", "cpp", (elaborate_coroutine(suspended.finish()),),
        )
        assert {issue.code for issue in collect_mir_issues(suspended_module)} == expected_codes

    effect_source = RoveCompiler(str(ROOT)).check_source(
        "fn pure_value() -> int { return 1 }\n"
        "fn allocate() -> int { var values = [1, 2]; return len(values) }\n"
        "struct Owned { values: Array<int> }\n"
        "fn copy_array(values: Array<int>) -> int { var copied = values; return len(copied) }\n"
        "fn copy_owned(value: Owned) -> int { var copied = value; return len(copied.values) }\n"
        "fn copy_text(value: string) -> int { var copied = value; return len(copied) }\n"
        "fn emit() { print(\"nyx\") }\n"
        "fn caller() { emit() }\n"
        "async fn pending() {}\n",
        filename="effects.rove",
        target="cpp",
    )
    assert effect_source.success and effect_source.hir is not None
    effect_mir = lower_hir_to_mir(effect_source.hir)
    effects = {function.name: function.effects for function in effect_mir.functions}
    assert effects == {
        "pure_value": ("pure",),
        "allocate": ("may_allocate",),
        "copy_array": ("may_allocate",),
        "copy_owned": ("may_allocate",),
        "copy_text": ("may_allocate",),
        "emit": ("io",),
        "caller": ("io",),
        "pending": ("may_suspend",),
    }
    bad_effects = replace(
        effect_mir,
        functions=(replace(effect_mir.functions[0], effects=("io",)),)
        + effect_mir.functions[1:],
    )
    assert "MIR0111" in {issue.code for issue in collect_mir_issues(bad_effects)}

    empty = RoveCompiler(str(ROOT)).check_source(
        "fn empty() {}\n",
        filename="empty.rove",
        target="cpp",
    )
    assert empty.success and empty.hir is not None
    skeleton = lower_hir_skeleton(empty.hir)
    verify_mir(skeleton)
    assert skeleton.functions[0].blocks[0].terminator == ReturnTerminator(
        skeleton.functions[0].span
    )

    executable = RoveCompiler(str(ROOT)).check_source(
        'fn main() { print("M2") }\n',
        filename="m2-required.rove",
        target="cpp",
    )
    assert executable.success and executable.hir is not None
    try:
        lower_hir_skeleton(executable.hir)
        raise AssertionError("M1 silently lowered an executable function body")
    except MIRLoweringError as error:
        assert "requires M2 lowering" in str(error)

    span = MIRSpan("builder.rove", 1, 1)
    incomplete = MIRFunctionBuilder("bad", "bad", MIRType("void"), span)
    incomplete.new_block()
    try:
        incomplete.finish()
        raise AssertionError("Builder accepted a block without a terminator")
    except ValueError as error:
        assert "exactly one terminator" in str(error)

    with tempfile.TemporaryDirectory(prefix="rove_mir_cli_") as directory:
        source_path = Path(directory, "empty.rove")
        json_path = Path(directory, "empty.mir.json")
        source_path.write_text("fn empty() {}\n", encoding="utf-8")
        emitted = subprocess.run(
            [
                sys.executable,
                str(ROOT / "src" / "cli.py"),
                "emit",
                "mir",
                str(source_path),
                "--json",
                "-o",
                str(json_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert emitted.returncode == 0, emitted.stdout + emitted.stderr
        verify_mir(from_json(json_path.read_text(encoding="utf-8")))
        verified = subprocess.run(
            [sys.executable, str(ROOT / "src" / "cli.py"), "verify", "mir", str(json_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert verified.returncode == 0, verified.stdout + verified.stderr
        assert "Experimental MIR verified" in verified.stdout

    print("[PASS] MIR model, builder, verifier, round-trip, printer, fingerprints, effect inference, CLI, and M1 gate")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_mir_suite() else 1)
