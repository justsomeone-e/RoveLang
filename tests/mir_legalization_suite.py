from dataclasses import replace
from pathlib import Path
import json
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api import RoveCompiler
from src.codegen.cpp_toolchain import CppToolchain
from src.mir import (
    AggregateRValue,
    AssignStatement,
    BinaryRValue,
    BorrowRValue,
    CallTerminator,
    CastRValue,
    ConstOperand,
    CopyOperand,
    DeinitStatement,
    DerefProjection,
    DropTerminator,
    MIR_BACKEND_MIGRATION_ORDER,
    MIR_BACKEND_PROFILES,
    MIRFunctionBuilder,
    MIRInterpreter,
    MIRLegalizationError,
    MIRModule,
    MIRSpan,
    MIRType,
    MoveOperand,
    Place,
    ReleaseStatement,
    RetainStatement,
    ReturnTerminator,
    UseRValue,
    collect_legalization_issues,
    emit_legalized_c17,
    emit_legalized_cpp,
    emit_legalized_javascript,
    emit_legalized_llvm,
    emit_legalized_python,
    emit_legalized_rust,
    emit_legalized_wasm,
    emit_legalized_wat,
    legalize_mir,
    lower_hir_to_mir,
    mir_backend_manifest,
)
from src.mir.model import MIRField, MIRStructDef, SuspendTerminator


SCALAR_FIXTURE = ROOT / "tests" / "fixtures" / "mir" / "m2_scalar.rove"
AGGREGATE_FIXTURE = ROOT / "tests" / "fixtures" / "mir" / "m4_aggregates.rove"
PAYLOAD_FIXTURE = ROOT / "tour" / "solutions" / "17_results" / "result01.rove"
CONTROL_FIXTURE = ROOT / "tests" / "fixtures" / "mir" / "m3_control.rove"
PATTERN_CLEANUP_FIXTURE = ROOT / "tests" / "fixtures" / "mir" / "m3_match_pattern_cleanup.rove"
NESTED_VALUES_FIXTURE = ROOT / "tests" / "fixtures" / "mir" / "m5_nested_values.rove"
ASYNC_FIXTURE = ROOT / "tests" / "fixtures" / "mir" / "m5_async_tasks.rove"
LLVM_STRUCT_FIXTURE = ROOT / "tests" / "fixtures" / "mir" / "m5_llvm_structs.rove"
LLVM_ARRAY_FIXTURE = ROOT / "tests" / "fixtures" / "mir" / "m5_llvm_arrays.rove"
LLVM_NESTED_ARRAY_FIXTURE = ROOT / "tests" / "fixtures" / "mir" / "m5_llvm_nested_arrays.rove"
LLVM_STRUCT_ARRAY_FIXTURE = ROOT / "tests" / "fixtures" / "mir" / "m5_llvm_struct_arrays.rove"
LLVM_TAGGED_FIXTURE = ROOT / "tests" / "fixtures" / "mir" / "m5_llvm_tagged.rove"
LLVM_OWNED_TAGGED_FIXTURE = ROOT / "tests" / "fixtures" / "mir" / "m5_llvm_owned_tagged.rove"
RUST_VALIDATION_MODE = "runtime"


def _lower(path: Path):
    checked = RoveCompiler(str(ROOT)).check_file(str(path), target="cpp")
    assert checked.success and checked.hir is not None, checked.diagnostics
    return lower_hir_to_mir(checked.hir)


def _lower_source(source: str, filename: str):
    checked = RoveCompiler(str(ROOT)).check_source(source, filename=filename, target="cpp")
    assert checked.success and checked.hir is not None, checked.diagnostics
    return lower_hir_to_mir(checked.hir)


def _run_legacy_cpp() -> str:
    result = subprocess.run(
        [sys.executable, str(ROOT / "src" / "cli.py"), "run", str(SCALAR_FIXTURE), "--target", "cpp"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.replace("\r\n", "\n")


def _compile_and_run_cpp(source: str) -> str:
    with tempfile.TemporaryDirectory(prefix="nyx_mir_codegen_") as temporary:
        source_path = Path(temporary) / "program.cpp"
        executable = Path(temporary) / ("program.exe" if os.name == "nt" else "program")
        source_path.write_text(source, encoding="utf-8", newline="\n")
        compiled, detail = CppToolchain.compile_cpp(str(source_path), str(executable))
        assert compiled, detail
        return_code, output = CppToolchain.run_executable(str(executable), timeout=30)
        assert return_code == 0, output
        return output.replace("\r\n", "\n")


def _compile_and_run_c17(source: str) -> str:
    clang = shutil.which("clang")
    assert clang is not None, "clang is required by the C17 MIR runtime gate"
    with tempfile.TemporaryDirectory(prefix="nyx_mir_c17_") as temporary:
        source_path = Path(temporary) / "program.c"
        executable = Path(temporary) / ("program.exe" if os.name == "nt" else "program")
        source_path.write_text(source, encoding="utf-8", newline="\n")
        compiled = subprocess.run(
            [clang, "-std=c17", "-O2", str(source_path), "-o", str(executable)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        assert compiled.returncode == 0, compiled.stdout + compiled.stderr + "\n" + source
        executed = subprocess.run(
            [str(executable)], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        assert executed.returncode == 0, executed.stdout + executed.stderr
        return executed.stdout.replace("\r\n", "\n")


def _compile_and_run_llvm(source: str) -> str:
    clang = shutil.which("clang")
    assert clang is not None, "clang is required by the existing LLVM conformance target"
    with tempfile.TemporaryDirectory(prefix="nyx_mir_llvm_") as temporary:
        source_path = Path(temporary) / "program.ll"
        executable = Path(temporary) / ("program.exe" if os.name == "nt" else "program")
        source_path.write_text(source, encoding="utf-8", newline="\n")
        compiled = subprocess.run(
            [clang, "-O2", str(source_path), "-o", str(executable)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        assert compiled.returncode == 0, compiled.stdout + compiled.stderr + "\n" + source
        executed = subprocess.run(
            [str(executable)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30
        )
        assert executed.returncode == 0, executed.stdout + executed.stderr
        return executed.stdout.replace("\r\n", "\n")


def _assert_rust_runtime(source: str, expected: str) -> None:
    global RUST_VALIDATION_MODE
    rustc = shutil.which("rustc")
    assert rustc is not None, "rustc is required by the Rust MIR runtime gate"
    with tempfile.TemporaryDirectory(prefix="nyx_mir_rust_") as temporary:
        source_path = Path(temporary) / "program.rs"
        executable = Path(temporary) / ("program.exe" if os.name == "nt" else "program")
        source_path.write_text(source, encoding="utf-8", newline="\n")

        def check_metadata() -> None:
            metadata = Path(temporary) / "program.rmeta"
            checked = subprocess.run(
                [rustc, "--edition=2021", "--emit=metadata", "-O", str(source_path), "-o", str(metadata)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
            )
            assert checked.returncode == 0, checked.stdout + checked.stderr + "\n" + source

        def compile_rust():
            command = [
                rustc, "--edition=2021", "-O",
                str(source_path), "-o", str(executable),
            ]
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )

        def assert_executable() -> None:
            executed = subprocess.run(
                [str(executable)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            assert executed.returncode == 0, executed.stdout + executed.stderr
            assert executed.stdout.replace("\r\n", "\n") == expected

        if RUST_VALIDATION_MODE.startswith("metadata-only"):
            check_metadata()
            return
        compiled = compile_rust()
        compiler_output = compiled.stdout + compiled.stderr
        missing_windows_linker = (
            os.name == "nt"
            and "link.exe" in compiler_output
            and ("not found" in compiler_output or "program not found" in compiler_output)
        )
        if compiled.returncode != 0 and missing_windows_linker:
            check_metadata()
            RUST_VALIDATION_MODE = "metadata-only (Windows SDK linker unavailable)"
            return
        assert compiled.returncode == 0, compiler_output + "\n" + source
        assert_executable()


def _run_javascript(source: str) -> str:
    node = shutil.which("node")
    assert node is not None, "Node.js is required by the JavaScript MIR runtime gate"
    with tempfile.TemporaryDirectory(prefix="nyx_mir_js_") as temporary:
        source_path = Path(temporary) / "program.mjs"
        source_path.write_text(source, encoding="utf-8", newline="\n")
        executed = subprocess.run(
            [node, str(source_path)], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        assert executed.returncode == 0, executed.stdout + executed.stderr + "\n" + source
        return executed.stdout.replace("\r\n", "\n")


def _run_python(source: str) -> str:
    with tempfile.TemporaryDirectory(prefix="nyx_mir_python_") as temporary:
        source_path = Path(temporary) / "program.py"
        source_path.write_text(source, encoding="utf-8", newline="\n")
        executed = subprocess.run(
            [sys.executable, str(source_path)], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        assert executed.returncode == 0, executed.stdout + executed.stderr + "\n" + source
        return executed.stdout.replace("\r\n", "\n")


def _run_wasm_export(
    wasm: bytes,
    function: str,
    *arguments: int | float,
    expect_trap: bool = False,
) -> str:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for the WebAssembly runtime gate"
    with tempfile.TemporaryDirectory(prefix="nyx_mir_wasm_") as temporary:
        wasm_path = Path(temporary) / "program.wasm"
        script_path = Path(temporary) / "run.mjs"
        wasm_path.write_bytes(wasm)
        encoded_arguments = ", ".join(
            f"{argument}n" if isinstance(argument, int) else repr(argument)
            for argument in arguments
        )
        script_path.write_text(
            "import fs from 'node:fs';\n"
            "const bytes = fs.readFileSync(new URL('./program.wasm', import.meta.url));\n"
            "const { instance } = await WebAssembly.instantiate(bytes, {});\n"
            f"console.log(String(instance.exports[{json.dumps(function)}]({encoded_arguments})));\n",
            encoding="utf-8",
            newline="\n",
        )
        executed = subprocess.run(
            [node, str(script_path)], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if expect_trap:
            assert executed.returncode != 0, "WebAssembly call unexpectedly succeeded"
            assert "RuntimeError" in executed.stderr, executed.stdout + executed.stderr
            return ""
        assert executed.returncode == 0, executed.stdout + executed.stderr
        return executed.stdout.replace("\r\n", "\n")


def _ownership_module() -> MIRModule:
    span = MIRSpan("m5-ownership.rove", 1, 1)
    int_type = MIRType("int")
    pointer_type = MIRType("int", pointer=True)
    builder = MIRFunctionBuilder("main", "function::main", MIRType("any"), span)
    value = builder.new_local("value", int_type)
    reference = builder.new_local("reference", pointer_type)
    observed = builder.new_local("observed", int_type)
    sink = builder.new_local("sink", int_type)
    entry = builder.new_block()
    after_print = builder.new_block()
    exit_block = builder.new_block()
    builder.push_statement(entry, AssignStatement(
        Place(value), UseRValue(ConstOperand(int_type, 42)), span
    ))
    builder.push_statement(entry, AssignStatement(
        Place(reference), BorrowRValue(Place(value), False, pointer_type), span
    ))
    builder.push_statement(entry, RetainStatement(Place(reference), span))
    builder.push_statement(entry, AssignStatement(
        Place(observed),
        UseRValue(CopyOperand(Place(reference, (DerefProjection(),)))),
        span,
    ))
    builder.push_statement(entry, ReleaseStatement(Place(reference), span))
    builder.push_statement(entry, AssignStatement(
        Place(sink), UseRValue(MoveOperand(Place(observed))), span
    ))
    builder.push_statement(entry, DeinitStatement(Place(reference), span))
    builder.set_terminator(entry, CallTerminator(
        "builtin::print", (CopyOperand(Place(sink)),), None, after_print, None, span
    ))
    builder.set_terminator(after_print, DropTerminator(Place(sink), exit_block, None, span))
    builder.set_terminator(exit_block, ReturnTerminator(span))
    return MIRModule("m5-ownership.rove", "cpp", (builder.finish(),))


def _rust_value_ownership_module() -> MIRModule:
    span = MIRSpan("m5-rust-ownership.rove", 1, 1)
    string_type = MIRType("string")
    builder = MIRFunctionBuilder("main", "function::main", MIRType("any"), span)
    source = builder.new_local("source", string_type)
    copied = builder.new_local("copied", string_type)
    moved = builder.new_local("moved", string_type)
    entry = builder.new_block()
    after_print = builder.new_block()
    after_drop = builder.new_block()
    builder.push_statement(entry, AssignStatement(
        Place(source), UseRValue(ConstOperand(string_type, "owned")), span
    ))
    builder.push_statement(entry, AssignStatement(
        Place(copied), UseRValue(CopyOperand(Place(source))), span
    ))
    builder.push_statement(entry, RetainStatement(Place(copied), span))
    builder.push_statement(entry, ReleaseStatement(Place(copied), span))
    builder.push_statement(entry, AssignStatement(
        Place(moved), UseRValue(MoveOperand(Place(source))), span
    ))
    builder.set_terminator(entry, CallTerminator(
        "builtin::print",
        (CopyOperand(Place(copied)), CopyOperand(Place(moved))),
        None,
        after_print,
        None,
        span,
    ))
    builder.push_statement(after_print, DeinitStatement(Place(copied), span))
    builder.set_terminator(after_print, DropTerminator(Place(moved), after_drop, None, span))
    builder.set_terminator(after_drop, ReturnTerminator(span))
    return MIRModule("m5-rust-ownership.rove", "rust", (builder.finish(),))


def _rust_mutable_borrow_module() -> MIRModule:
    span = MIRSpan("m5-rust-mutable-borrow.rove", 1, 1)
    int_type = MIRType("int")
    pointer_type = MIRType("int", pointer=True)
    builder = MIRFunctionBuilder("main", "function::main", MIRType("any"), span)
    value = builder.new_local("value", int_type)
    reference = builder.new_local("reference", pointer_type)
    entry = builder.new_block()
    after_print = builder.new_block()
    builder.push_statement(entry, AssignStatement(
        Place(value), UseRValue(ConstOperand(int_type, 41)), span
    ))
    builder.push_statement(entry, AssignStatement(
        Place(reference), BorrowRValue(Place(value), True, pointer_type), span
    ))
    builder.push_statement(entry, AssignStatement(
        Place(reference, (DerefProjection(),)), UseRValue(ConstOperand(int_type, 42)), span
    ))
    builder.set_terminator(entry, CallTerminator(
        "builtin::print", (CopyOperand(Place(value)),), None, after_print, None, span
    ))
    builder.push_statement(after_print, DeinitStatement(Place(reference), span))
    builder.set_terminator(after_print, ReturnTerminator(span))
    return MIRModule("m5-rust-mutable-borrow.rove", "rust", (builder.finish(),))


def _llvm_value_lifecycle_module() -> MIRModule:
    span = MIRSpan("m5-llvm-value-lifecycle.rove", 1, 1)
    int_type = MIRType("int")
    string_type = MIRType("string")
    array_type = MIRType("Array", (int_type,))
    owned_type = MIRType("Owned")
    builder = MIRFunctionBuilder("main", "function::main", MIRType("any"), span)
    original = builder.new_local("original", array_type, "variable", span)
    copied = builder.new_local("copied", array_type, "variable", span)
    owned = builder.new_local("owned", owned_type, "variable", span)
    entry = builder.new_block()
    after_array_drop = builder.new_block()
    exit_block = builder.new_block()

    builder.push_statement(entry, AssignStatement(
        Place(original),
        AggregateRValue(
            "array",
            "Array",
            (ConstOperand(int_type, 4), ConstOperand(int_type, 5)),
            array_type,
        ),
        span,
    ))
    builder.push_statement(entry, AssignStatement(
        Place(copied), UseRValue(CopyOperand(Place(original))), span
    ))
    builder.push_statement(entry, AssignStatement(
        Place(owned),
        AggregateRValue(
            "struct",
            "Owned",
            (CopyOperand(Place(original)), ConstOperand(string_type, "nyx")),
            owned_type,
            ("values", "label"),
        ),
        span,
    ))
    builder.push_statement(entry, DeinitStatement(Place(original), span))
    builder.set_terminator(
        entry, DropTerminator(Place(copied), after_array_drop, None, span)
    )
    builder.set_terminator(
        after_array_drop, DropTerminator(Place(owned), exit_block, None, span)
    )
    builder.set_terminator(exit_block, ReturnTerminator(span))
    function = replace(builder.finish(), effects=("may_allocate",))
    definition = MIRStructDef(
        "Owned",
        "type::Owned",
        (MIRField("values", array_type), MIRField("label", string_type)),
    )
    return MIRModule(
        "m5-llvm-value-lifecycle.rove", "llvm", (function,), (definition,)
    )


def _array_lifecycle_module() -> MIRModule:
    span = MIRSpan("m5-array-lifecycle.rove", 1, 1)
    int_type = MIRType("int")
    array_type = MIRType("Array", (int_type,))
    builder = MIRFunctionBuilder("main", "function::main", MIRType("any"), span)
    original = builder.new_local("original", array_type, "variable", span)
    copied = builder.new_local("copied", array_type, "variable", span)
    entry = builder.new_block()
    exit_block = builder.new_block()
    builder.push_statement(entry, AssignStatement(
        Place(original),
        AggregateRValue(
            "array",
            "Array",
            (ConstOperand(int_type, 4), ConstOperand(int_type, 5)),
            array_type,
        ),
        span,
    ))
    builder.push_statement(entry, AssignStatement(
        Place(copied), UseRValue(CopyOperand(Place(original))), span
    ))
    builder.push_statement(entry, DeinitStatement(Place(original), span))
    builder.set_terminator(
        entry, DropTerminator(Place(copied), exit_block, None, span)
    )
    builder.set_terminator(exit_block, ReturnTerminator(span))
    return MIRModule(
        span.source,
        "wasm",
        (replace(builder.finish(), effects=("may_allocate",)),),
    )


def _unsupported_operation_module() -> MIRModule:
    span = MIRSpan("m5-unsupported-operation.rove", 1, 1)
    int_type = MIRType("int")
    builder = MIRFunctionBuilder("power", "function::power", int_type, span)
    entry = builder.new_block()
    builder.push_statement(entry, AssignStatement(
        Place(0),
        BinaryRValue("**", ConstOperand(int_type, 2), ConstOperand(int_type, 8), int_type),
        span,
    ))
    builder.set_terminator(entry, ReturnTerminator(span))
    return MIRModule("m5-unsupported-operation.rove", "cpp", (builder.finish(),))


def _llvm_contract_rejection_modules() -> dict[str, MIRModule]:
    span = MIRSpan("m5-llvm-contract-rejections.rove", 1, 1)
    bool_type = MIRType("bool")
    int_type = MIRType("int")
    float_type = MIRType("float")
    string_type = MIRType("string")
    array_type = MIRType("Array", (int_type,))

    ordered_bool = MIRFunctionBuilder(
        "main", "function::main", MIRType("any"), span
    )
    ordered_result = ordered_bool.new_local("ordered", bool_type, "variable", span)
    ordered_entry = ordered_bool.new_block()
    ordered_bool.push_statement(ordered_entry, AssignStatement(
        Place(ordered_result),
        BinaryRValue(
            "<", ConstOperand(bool_type, False), ConstOperand(bool_type, True), bool_type
        ),
        span,
    ))
    ordered_bool.set_terminator(ordered_entry, ReturnTerminator(span))

    mixed_operands = MIRFunctionBuilder(
        "main", "function::main", MIRType("any"), span
    )
    mixed_result = mixed_operands.new_local("equal", bool_type, "variable", span)
    mixed_entry = mixed_operands.new_block()
    mixed_operands.push_statement(mixed_entry, AssignStatement(
        Place(mixed_result),
        BinaryRValue(
            "==", ConstOperand(int_type, 7), ConstOperand(float_type, 7.0), bool_type
        ),
        span,
    ))
    mixed_operands.set_terminator(mixed_entry, ReturnTerminator(span))

    invalid_cast = MIRFunctionBuilder(
        "main", "function::main", MIRType("any"), span
    )
    cast_result = invalid_cast.new_local("casted", int_type, "variable", span)
    cast_entry = invalid_cast.new_block()
    invalid_cast.push_statement(cast_entry, AssignStatement(
        Place(cast_result),
        CastRValue("explicit", ConstOperand(string_type, "7"), int_type),
        span,
    ))
    invalid_cast.set_terminator(cast_entry, ReturnTerminator(span))

    invalid_len = MIRFunctionBuilder(
        "main", "function::main", MIRType("any"), span
    )
    length = invalid_len.new_local("length", int_type, "variable", span)
    len_entry = invalid_len.new_block()
    len_exit = invalid_len.new_block()
    invalid_len.set_terminator(len_entry, CallTerminator(
        "builtin::len",
        (ConstOperand(bool_type, True),),
        Place(length),
        len_exit,
        None,
        span,
    ))
    invalid_len.set_terminator(len_exit, ReturnTerminator(span))

    recursive = MIRStructDef(
        "Recursive",
        "type::Recursive",
        (MIRField("next", MIRType("Recursive")),),
    )
    return {
        "ordered-bool": MIRModule(
            span.source, "llvm", (ordered_bool.finish(),)
        ),
        "mixed-operands": MIRModule(
            span.source, "llvm", (mixed_operands.finish(),)
        ),
        "string-to-int-cast": MIRModule(
            span.source, "llvm", (invalid_cast.finish(),)
        ),
        "invalid-len": MIRModule(
            span.source, "llvm", (invalid_len.finish(),)
        ),
        "recursive-struct": MIRModule(
            span.source, "llvm", (), (recursive,)
        ),
    }


def run_mir_legalization_suite() -> bool:
    print("=" * 70)
    print("ROVE M5 MIR LEGALIZATION / C++ MIGRATION PILOT")
    print("=" * 70)

    manifest = mir_backend_manifest()
    assert json.loads(json.dumps(manifest)) == manifest
    assert manifest["schema_version"] == 3
    assert tuple(manifest["migration_order"]) == MIR_BACKEND_MIGRATION_ORDER
    assert tuple(profile["target"] for profile in manifest["profiles"]) == MIR_BACKEND_MIGRATION_ORDER
    assert all(
        MIR_BACKEND_PROFILES[target].migration_status == "pilot"
        for target in MIR_BACKEND_MIGRATION_ORDER
    )

    scalar = _lower(SCALAR_FIXTURE)
    assert legalize_mir(scalar, "native", require_emitter=True) is scalar
    assert not collect_legalization_issues(scalar, "cpp", require_emitter=True)
    expected = MIRInterpreter(scalar).run().output
    assert expected == ("13",), expected

    generated = emit_legalized_cpp(scalar)
    assert "nyx_mir_runtime::add" in generated
    assert "goto bb" in generated
    migrated_output = _compile_and_run_cpp(generated)
    assert migrated_output == "13\n", migrated_output
    llvm_output = _compile_and_run_llvm(emit_legalized_llvm(scalar))
    assert llvm_output == migrated_output, llvm_output
    assert "\n13\n" in "\n" + _run_legacy_cpp(), "legacy C++ oracle did not print 13"

    numeric = _lower_source(
        "fn compute(x: float, y: float) -> float { return (x * y) + 1.25 }\n"
        "fn main() {\n"
        "  let min: int = -9223372036854775808\n"
        "  print(9223372036854775807 + 1)\n"
        "  print(-7 / 3, -7 % 3)\n"
        "  print(\"min-divmod\", min / -1, min % -1)\n"
        "  print(\"bits\", 1 << 64, -1 >> 65)\n"
        "  print(\"answer\", compute(2.5, 4.0), true)\n"
        "}\n",
        "m5-numeric.rove",
    )
    expected_numeric = "\n".join(MIRInterpreter(numeric).run().output) + "\n"
    assert expected_numeric == (
        "-9223372036854775808\n-2 -1\n"
        "min-divmod -9223372036854775808 0\n"
        "bits 1 -1\nanswer 11.25 true\n"
    )
    assert _compile_and_run_cpp(emit_legalized_cpp(numeric)) == expected_numeric
    assert _compile_and_run_llvm(emit_legalized_llvm(numeric)) == expected_numeric
    _assert_rust_runtime(emit_legalized_rust(numeric), expected_numeric)
    assert _run_javascript(emit_legalized_javascript(numeric)) == expected_numeric
    assert _run_python(emit_legalized_python(numeric)) == expected_numeric
    assert _compile_and_run_c17(emit_legalized_c17(numeric)) == expected_numeric

    mixed_numeric = _lower_source(
        "fn equal(x: int, y: float) -> bool { return x == y }\n"
        "fn add(x: int, y: float) -> float { return x + y }\n"
        "fn choose(x: float) -> int = match x { 7 => 1, _ => 0 }\n"
        "fn main() {\n"
        "  let value: float = 7.0\n"
        "  match value { 7 => print(\"stmt\"), _ => print(\"miss\") }\n"
        "  print(equal(7, value), add(7, 2.0) == 9.0, choose(value))\n"
        "  print(\"rounded\", equal(9223372036854775807, 9223372036854775808.0))\n"
        "}\n",
        "m5-mixed-numeric-match.rove",
    )
    expected_mixed_numeric = "stmt\ntrue true 1\nrounded true\n"
    assert "\n".join(MIRInterpreter(mixed_numeric).run().output) + "\n" == (
        expected_mixed_numeric
    )
    for target, emitter, runner in (
        ("cpp", emit_legalized_cpp, _compile_and_run_cpp),
        ("llvm", emit_legalized_llvm, _compile_and_run_llvm),
        ("js", emit_legalized_javascript, _run_javascript),
        ("python", emit_legalized_python, _run_python),
        ("c", emit_legalized_c17, _compile_and_run_c17),
    ):
        assert not collect_legalization_issues(
            mixed_numeric, target, require_emitter=True
        )
        assert runner(emitter(mixed_numeric)) == expected_mixed_numeric
    assert not collect_legalization_issues(
        mixed_numeric, "rust", require_emitter=True
    )
    _assert_rust_runtime(emit_legalized_rust(mixed_numeric), expected_mixed_numeric)

    floating = _lower_source(
        "fn main() { print(1.0 / 0.0, 0.0 / 0.0, -7.5 % 2.0, -0.0) }\n",
        "m5-floating.rove",
    )
    expected_floating = "inf nan -1.5 0\n"
    assert "\n".join(MIRInterpreter(floating).run().output) + "\n" == expected_floating
    assert _compile_and_run_cpp(emit_legalized_cpp(floating)) == expected_floating
    assert _compile_and_run_llvm(emit_legalized_llvm(floating)) == expected_floating
    _assert_rust_runtime(emit_legalized_rust(floating), expected_floating)
    assert _run_javascript(emit_legalized_javascript(floating)) == expected_floating
    assert _run_python(emit_legalized_python(floating)) == expected_floating
    assert _compile_and_run_c17(emit_legalized_c17(floating)) == expected_floating

    float_text = _lower_source(
        "fn show(x: float) -> int { print(x, to_string(x)); return 0 }\n"
        "fn main() {\n"
        "  show(2.0)\n"
        "  show(-0.0)\n"
        "  show(0.000001)\n"
        "  show(0.0000001)\n"
        "  show(-0.0000001)\n"
        "  show(100000000000000000000.0)\n"
        "  show(1000000000000000000000.0)\n"
        "  show(1.2345678901234567)\n"
        "  show(1.0 / 0.0)\n"
        "  show(-1.0 / 0.0)\n"
        "  show(0.0 / 0.0)\n"
        "}\n",
        "m5-float-text-contract.rove",
    )
    # Explicit source-contract oracle, independent of the MIR interpreter.
    expected_float_text = (
        "2 2\n0 0\n0.000001 0.000001\n1e-7 1e-7\n-1e-7 -1e-7\n"
        "100000000000000000000 100000000000000000000\n"
        "1e+21 1e+21\n1.2345678901234567 1.2345678901234567\n"
        "inf inf\n-inf -inf\nnan nan\n"
    )
    assert "\n".join(MIRInterpreter(float_text).run().output) + "\n" == expected_float_text
    for emitter, runner in (
        (emit_legalized_cpp, _compile_and_run_cpp),
        (emit_legalized_c17, _compile_and_run_c17),
        (emit_legalized_javascript, _run_javascript),
        (emit_legalized_python, _run_python),
    ):
        assert runner(emitter(float_text)) == expected_float_text
    _assert_rust_runtime(emit_legalized_rust(float_text), expected_float_text)

    llvm_float_text = _lower_source(
        "fn main() {\n"
        "  print(2.0, -0.0, 0.000001, 0.0000001, -0.0000001)\n"
        "  print(100000000000000000000.0, 1000000000000000000000.0)\n"
        "  print(1.2345678901234567, 1.0 / 0.0, -1.0 / 0.0, 0.0 / 0.0)\n"
        "}\n",
        "m5-llvm-float-text-contract.rove",
    )
    expected_llvm_float_text = (
        "2 0 0.000001 1e-7 -1e-7\n"
        "100000000000000000000 1e+21\n"
        "1.2345678901234567 inf -inf nan\n"
    )
    assert "\n".join(MIRInterpreter(llvm_float_text).run().output) + "\n" == (
        expected_llvm_float_text
    )
    assert _compile_and_run_llvm(emit_legalized_llvm(llvm_float_text)) == (
        expected_llvm_float_text
    )

    float_span = MIRSpan("m5-float-display.rove", 1, 1)
    float_type = MIRType("float")
    float_builder = MIRFunctionBuilder(
        "main", "function::main", MIRType("any"), float_span
    )
    float_block = float_builder.new_block()
    float_bits = [
        0, 1, 0x8000000000000000, 0x7FEFFFFFFFFFFFFF,
        0x0010000000000000, 0x000FFFFFFFFFFFFF,
        0x3FF0000000000000, 0x4340000000000000,
    ]
    float_rng = random.Random(1776)
    float_bits.extend(float_rng.getrandbits(64) for _ in range(512))
    for bits in float_bits:
        value = struct.unpack(">d", bits.to_bytes(8, "big"))[0]
        next_block = float_builder.new_block()
        float_builder.set_terminator(float_block, CallTerminator(
            "builtin::print", (ConstOperand(float_type, value),),
            None, next_block, None, float_span,
        ))
        float_block = next_block
    float_builder.set_terminator(float_block, ReturnTerminator(float_span))
    float_module = MIRModule(float_span.source, "c", (float_builder.finish(),))
    assert not collect_legalization_issues(float_module, "c", require_emitter=True)
    expected_float_display = "\n".join(MIRInterpreter(float_module).run().output) + "\n"
    for emitter, runner in (
        (emit_legalized_cpp, _compile_and_run_cpp),
        (emit_legalized_llvm, _compile_and_run_llvm),
        (emit_legalized_c17, _compile_and_run_c17),
        (emit_legalized_javascript, _run_javascript),
        (emit_legalized_python, _run_python),
    ):
        assert runner(emitter(float_module)) == expected_float_display

    unknown = collect_legalization_issues(scalar, "moonvm")
    assert {issue.code for issue in unknown} == {"MIRG1000"}, unknown

    unprofiled = collect_legalization_issues(scalar, "asm")
    assert {issue.code for issue in unprofiled} == {"MIRG1001"}, unprofiled

    wasm = _lower_source(
        "fn sum_without_two(limit: int) -> int {\n"
        "  var total: int = 0\n"
        "  var i: int = 0\n"
        "  while i < limit {\n"
        "    if i != 2 { set total = total + i }\n"
        "    set i = i + 1\n"
        "  }\n"
        "  return total\n"
        "}\n"
        "fn safe_div(left: int, right: int) -> int { return left / right }\n"
        "fn safe_rem(left: int, right: int) -> int { return left % right }\n",
        "m5-wasm.rove",
    )
    assert not collect_legalization_issues(wasm, "wasm", require_emitter=True)
    assert MIRInterpreter(wasm).run("sum_without_two", (6,)).value == 13
    assert "loop $dispatch" in emit_legalized_wat(wasm)
    wasm_bytes = emit_legalized_wasm(wasm)
    assert _run_wasm_export(wasm_bytes, "sum_without_two", 6) == "13\n"
    minimum = -(1 << 63)
    assert MIRInterpreter(wasm).run("safe_div", (minimum, -1)).value == minimum
    assert _run_wasm_export(wasm_bytes, "safe_div", minimum, -1) == f"{minimum}\n"
    assert _run_wasm_export(wasm_bytes, "safe_rem", minimum, -1) == "0\n"
    _run_wasm_export(wasm_bytes, "safe_div", 1, 0, expect_trap=True)
    shifted = _lower_source("fn shifted(x: int) -> int { return x << 64 }\n", "m5-shift.rove")
    assert not collect_legalization_issues(shifted, "wasm", require_emitter=True)
    assert _run_wasm_export(emit_legalized_wasm(shifted), "shifted", 7) == "7\n"

    wasm_array = _lower_source(
        "fn array_probe() -> int {\n"
        "  var original = [1, 2, 3]\n"
        "  var copied = original\n"
        "  set copied[0] = 9\n"
        "  return original[0] * 100 + copied[0] * 10 + len(copied)\n"
        "}\n",
        "m5-wasm-array.rove",
    )
    assert not collect_legalization_issues(wasm_array, "wasm", require_emitter=True)
    assert MIRInterpreter(wasm_array).run("array_probe").value == 193
    wasm_array_wat = emit_legalized_wat(wasm_array)
    assert "call $__nyx_mir_array_clone_i64" in wasm_array_wat
    assert "i64.load" in wasm_array_wat and "i64.store" in wasm_array_wat
    assert _run_wasm_export(emit_legalized_wasm(wasm_array), "array_probe") == "193\n"

    wasm_bool_array = _lower_source(
        "fn bool_array_probe() -> int {\n"
        "  var original = [true, false]\n"
        "  var copied = original\n"
        "  set copied[0] = false\n"
        "  var score = len(copied)\n"
        "  if original[0] { set score = score + 100 }\n"
        "  if copied[0] { set score = score + 10 }\n"
        "  if copied[1] { set score = score + 1 }\n"
        "  return score\n"
        "}\n",
        "m5-wasm-bool-array.rove",
    )
    assert not collect_legalization_issues(wasm_bool_array, "wasm", require_emitter=True)
    assert MIRInterpreter(wasm_bool_array).run("bool_array_probe").value == 102
    wasm_bool_array_wat = emit_legalized_wat(wasm_bool_array)
    assert "call $__nyx_mir_array_clone_i32" in wasm_bool_array_wat
    assert "call $__nyx_mir_array_get_i32" in wasm_bool_array_wat
    assert "call $__nyx_mir_array_set_i32" in wasm_bool_array_wat
    assert _run_wasm_export(
        emit_legalized_wasm(wasm_bool_array), "bool_array_probe"
    ) == "102\n"

    wasm_nested_array = _lower_source(
        "fn nested_array_probe() -> int {\n"
        "  var original = [[1, 2], [3, 4]]\n"
        "  var copied = original\n"
        "  set copied[0][0] = 9\n"
        "  set copied[1] = [7, 8]\n"
        "  return original[0][0] * 1000 + copied[0][0] * 100 + "
        "original[1][0] * 10 + copied[1][0]\n"
        "}\n",
        "m5-wasm-nested-array.rove",
    )
    assert not collect_legalization_issues(wasm_nested_array, "wasm", require_emitter=True)
    assert MIRInterpreter(wasm_nested_array).run("nested_array_probe").value == 1937
    wasm_nested_array_wat = emit_legalized_wat(wasm_nested_array)
    assert "call $__nyx_mir_array_clone_nested_i64" in wasm_nested_array_wat
    assert wasm_nested_array_wat.count("call $__nyx_mir_array_get_blob") >= 2
    assert "memory.fill" in wasm_nested_array_wat
    assert _run_wasm_export(
        emit_legalized_wasm(wasm_nested_array), "nested_array_probe"
    ) == "1937\n"

    wasm_nested_string_array = _lower_source(
        "fn nested_string_array_probe() -> int {\n"
        "  var original = [[\"a\"], [\"bb\"]]\n"
        "  var copied = original\n"
        "  set copied[0][0] = \"hello\"\n"
        "  set copied[1] = [\"compiler\"]\n"
        "  return len(original[0][0]) * 1000 + len(copied[0][0]) * 100 + "
        "len(original[1][0]) * 10 + len(copied[1][0])\n"
        "}\n",
        "m5-wasm-nested-string-array.rove",
    )
    assert not collect_legalization_issues(
        wasm_nested_string_array, "wasm", require_emitter=True
    )
    assert MIRInterpreter(wasm_nested_string_array).run("nested_string_array_probe").value == 1528
    wasm_nested_string_array_wat = emit_legalized_wat(wasm_nested_string_array)
    assert "call $__nyx_mir_array_clone_nested_string" in wasm_nested_string_array_wat
    assert _run_wasm_export(
        emit_legalized_wasm(wasm_nested_string_array), "nested_string_array_probe"
    ) == "1528\n"

    wasm_nested_bool_array = _lower_source(
        "fn nested_bool_array_probe() -> int {\n"
        "  var original = [[true, false], [false, true]]\n"
        "  var copied = original\n"
        "  set copied[0][0] = false\n"
        "  set copied[1] = [true, false]\n"
        "  var score = 0\n"
        "  if original[0][0] { set score = score + 1000 }\n"
        "  if copied[0][0] { set score = score + 100 }\n"
        "  if original[1][1] { set score = score + 10 }\n"
        "  if copied[1][0] { set score = score + 1 }\n"
        "  return score\n"
        "}\n",
        "m5-wasm-nested-bool-array.rove",
    )
    assert not collect_legalization_issues(
        wasm_nested_bool_array, "wasm", require_emitter=True
    )
    assert MIRInterpreter(wasm_nested_bool_array).run("nested_bool_array_probe").value == 1011
    wasm_nested_bool_array_wat = emit_legalized_wat(wasm_nested_bool_array)
    assert "call $__nyx_mir_array_clone_nested_i32" in wasm_nested_bool_array_wat
    assert _run_wasm_export(
        emit_legalized_wasm(wasm_nested_bool_array), "nested_bool_array_probe"
    ) == "1011\n"

    wasm_nested_struct_array = _lower_source(
        "struct Cell { value: int, label: string }\n"
        "fn nested_struct_array_probe() -> int {\n"
        "  var original = [[Cell(1, \"a\")], [Cell(2, \"bb\")]]\n"
        "  var copied = original\n"
        "  set copied[0][0] = Cell(9, \"hello\")\n"
        "  set copied[1] = [Cell(7, \"compiler\")]\n"
        "  let original_first = original[0][0]\n"
        "  let copied_first = copied[0][0]\n"
        "  let original_second = original[1][0]\n"
        "  let copied_second = copied[1][0]\n"
        "  return original_first.value * 10000 + copied_first.value * 1000 + "
        "len(copied_first.label) * 100 + original_second.value * 10 + "
        "len(copied_second.label)\n"
        "}\n",
        "m5-wasm-nested-struct-array.rove",
    )
    assert not collect_legalization_issues(
        wasm_nested_struct_array, "wasm", require_emitter=True
    )
    assert MIRInterpreter(wasm_nested_struct_array).run("nested_struct_array_probe").value == 19528
    wasm_nested_struct_array_wat = emit_legalized_wat(wasm_nested_struct_array)
    assert "call $__nyx_mir_array_clone_nested_blob" in wasm_nested_struct_array_wat
    assert _run_wasm_export(
        emit_legalized_wasm(wasm_nested_struct_array), "nested_struct_array_probe"
    ) == "19528\n"

    wasm_struct = _lower_source(
        "struct Pair { x: int, y: int }\n"
        "fn struct_probe() -> int {\n"
        "  var original = Pair(4, 5)\n"
        "  var copied = original\n"
        "  set copied.x = 9\n"
        "  return original.x * 100 + copied.x * 10 + copied.y\n"
        "}\n",
        "m5-wasm-struct.rove",
    )
    assert not collect_legalization_issues(wasm_struct, "wasm", require_emitter=True)
    assert MIRInterpreter(wasm_struct).run("struct_probe").value == 495
    wasm_struct_wat = emit_legalized_wat(wasm_struct)
    assert "call $__nyx_mir_clone_bytes" in wasm_struct_wat
    assert "memory.copy" in wasm_struct_wat
    assert _run_wasm_export(emit_legalized_wasm(wasm_struct), "struct_probe") == "495\n"

    wasm_enum = _lower_source(
        "enum Signal { Ready(int), Empty() }\n"
        "fn enum_probe(value: int) -> int {\n"
        "  let signal = Ready(value)\n"
        "  match signal {\n"
        "    Ready(payload) => return payload + 1,\n"
        "    Empty() => return 0\n"
        "  }\n"
        "  return -1\n"
        "}\n",
        "m5-wasm-enum.rove",
    )
    assert not collect_legalization_issues(wasm_enum, "wasm", require_emitter=True)
    assert MIRInterpreter(wasm_enum).run("enum_probe", (41,)).value == 42
    wasm_enum_wat = emit_legalized_wat(wasm_enum)
    assert "call $__nyx_mir_clone_bytes" in wasm_enum_wat
    assert "i32.load" in wasm_enum_wat and "i64.load" in wasm_enum_wat
    assert _run_wasm_export(emit_legalized_wasm(wasm_enum), "enum_probe", 41) == "42\n"

    wasm_result = _lower_source(
        "fn make_result(code: int) -> Result<int, int> {\n"
        "  if code == 0 { return Ok(40) }\n"
        "  return Err(code)\n"
        "}\n"
        "fn result_probe(code: int) -> int {\n"
        "  match make_result(code) {\n"
        "    Ok(value) => return value + 2,\n"
        "    Err(error) => return error\n"
        "  }\n"
        "  return -1\n"
        "}\n",
        "m5-wasm-result.rove",
    )
    assert not collect_legalization_issues(wasm_result, "wasm", require_emitter=True)
    assert MIRInterpreter(wasm_result).run("result_probe", (0,)).value == 42
    assert MIRInterpreter(wasm_result).run("result_probe", (7,)).value == 7
    wasm_result_bytes = emit_legalized_wasm(wasm_result)
    assert _run_wasm_export(wasm_result_bytes, "result_probe", 0) == "42\n"
    assert _run_wasm_export(wasm_result_bytes, "result_probe", 7) == "7\n"

    wasm_bool_result = _lower_source(
        "fn bool_result_probe() -> int {\n"
        "  let result: Result<int, bool> = Err(true)\n"
        "  match result {\n"
        "    Ok(value) => return value,\n"
        "    Err(flag) => { if flag { return 7 } return 3 }\n"
        "  }\n"
        "  return -1\n"
        "}\n",
        "m5-wasm-bool-result.rove",
    )
    assert not collect_legalization_issues(wasm_bool_result, "wasm", require_emitter=True)
    assert MIRInterpreter(wasm_bool_result).run("bool_result_probe").value == 7
    wasm_bool_result_wat = emit_legalized_wat(wasm_bool_result)
    assert "i32.store" in wasm_bool_result_wat and "i32.load" in wasm_bool_result_wat
    wasm_bool_result_output = _run_wasm_export(emit_legalized_wasm(wasm_bool_result), "bool_result_probe")
    assert wasm_bool_result_output == "7\n", wasm_bool_result_output

    wasm_bool_aggregates = _lower_source(
        "struct Flags { enabled: bool, count: int, done: bool }\n"
        "enum Toggle { State(bool), Missing() }\n"
        "fn bool_struct_probe() -> int {\n"
        "  var original = Flags(true, 7, false)\n"
        "  var copied = original\n"
        "  set copied.enabled = false\n"
        "  set copied.done = true\n"
        "  var score = original.count * 10\n"
        "  if original.enabled { set score = score + 100 }\n"
        "  if copied.done { set score = score + 1 }\n"
        "  return score\n"
        "}\n"
        "fn bool_enum_probe() -> int {\n"
        "  let toggle = State(true)\n"
        "  match toggle {\n"
        "    State(value) => { if value { return 7 } return 3 },\n"
        "    Missing() => return 0\n"
        "  }\n"
        "  return -1\n"
        "}\n",
        "m5-wasm-bool-aggregates.rove",
    )
    wasm_bool_aggregate_issues = collect_legalization_issues(
        wasm_bool_aggregates, "wasm", require_emitter=True
    )
    assert not wasm_bool_aggregate_issues, wasm_bool_aggregate_issues
    assert MIRInterpreter(wasm_bool_aggregates).run("bool_struct_probe").value == 171
    assert MIRInterpreter(wasm_bool_aggregates).run("bool_enum_probe").value == 7
    wasm_bool_aggregate_wat = emit_legalized_wat(wasm_bool_aggregates)
    assert "i32.store8" in wasm_bool_aggregate_wat
    assert "i32.load8_u" in wasm_bool_aggregate_wat
    wasm_bool_aggregate_bytes = emit_legalized_wasm(wasm_bool_aggregates)
    assert _run_wasm_export(wasm_bool_aggregate_bytes, "bool_struct_probe") == "171\n"
    assert _run_wasm_export(wasm_bool_aggregate_bytes, "bool_enum_probe") == "7\n"

    wasm_float_array = _lower_source(
        "fn array_probe() -> float {\n"
        "  var original = [1.5, -2.25, 3.75]\n"
        "  var copied = original\n"
        "  set copied[1] = 8.5\n"
        "  return original[1] + copied[1] + original[2]\n"
        "}\n"
        "fn nested_probe() -> float {\n"
        "  var original = [[1.5, 2.5], [-3.25]]\n"
        "  var copied = original\n"
        "  set copied[0][1] = 9.75\n"
        "  set copied[1] = [4.5]\n"
        "  return original[0][1] + copied[0][1] + original[1][0] + copied[1][0]\n"
        "}\n"
        "fn detached_inner() -> float {\n"
        "  var outer = [[1.0, 2.0]]\n"
        "  var inner = outer[0]\n"
        "  set inner[0] = 9.0\n"
        "  return outer[0][0] + inner[0]\n"
        "}\n"
        "fn empty_length() -> int {\n"
        "  let values: Array<float> = []\n"
        "  return len(values)\n"
        "}\n"
        "fn signed_zero() -> float { let values = [-0.0]; return 1.0 / values[0] }\n"
        "fn bad_index(index: int) -> float { let values = [1.5]; return values[index] }\n",
        "m5-wasm-float-array.rove",
    )
    wasm_float_array_issues = collect_legalization_issues(
        wasm_float_array, "wasm", require_emitter=True
    )
    assert not wasm_float_array_issues, wasm_float_array_issues
    wasm_float_array_wat = emit_legalized_wat(wasm_float_array)
    assert "f64.load" in wasm_float_array_wat and "f64.store" in wasm_float_array_wat
    assert "call $__nyx_mir_array_clone_nested_blob" in wasm_float_array_wat
    wasm_float_array_bytes = emit_legalized_wasm(wasm_float_array)
    for function in ("array_probe", "nested_probe", "detached_inner", "empty_length", "signed_zero"):
        expected = MIRInterpreter(wasm_float_array).run(function).value
        actual = _run_wasm_export(wasm_float_array_bytes, function).strip()
        assert float(actual) == expected, (function, actual, expected)
    _run_wasm_export(wasm_float_array_bytes, "bad_index", -1, expect_trap=True)
    _run_wasm_export(wasm_float_array_bytes, "bad_index", 1, expect_trap=True)
    wasm_float_aggregates = _lower_source(
        "struct Sample { value: float, mark: int }\n"
        "struct Box { sample: Sample, delta: float }\n"
        "enum Reading { Value(float), Missing() }\n"
        "fn struct_probe(value: float) -> float {\n"
        "  var original = Sample(value, 7)\n"
        "  var copied = original\n"
        "  set copied.value = -2.25\n"
        "  return original.value + copied.value\n"
        "}\n"
        "fn nested_probe() -> float {\n"
        "  var original = Box(Sample(1.25, 3), 2.5)\n"
        "  var copied = original\n"
        "  set copied.sample.value = 9.0\n"
        "  return original.sample.value + copied.sample.value + original.delta\n"
        "}\n"
        "fn struct_array_probe() -> float {\n"
        "  var original = [Sample(1.5, 1), Sample(2.5, 2)]\n"
        "  var copied = original\n"
        "  set copied[0] = Sample(9.0, 1)\n"
        "  let before = original[0]\n"
        "  let after = copied[0]\n"
        "  return before.value + after.value\n"
        "}\n"
        "fn enum_probe(value: float) -> float {\n"
        "  let reading = Value(value)\n"
        "  match reading {\n"
        "    Value(number) => return number * 2.0,\n"
        "    Missing() => return 0.0\n"
        "  }\n"
        "  return -1.0\n"
        "}\n"
        "fn result_ok(value: float) -> float {\n"
        "  let item: Result<float, string> = Ok(value)\n"
        "  match item {\n"
        "    Ok(number) => return number,\n"
        "    Err(message) => return -1.0\n"
        "  }\n"
        "  return -2.0\n"
        "}\n"
        "fn result_error() -> int {\n"
        "  let item: Result<float, string> = Err(\"bad\")\n"
        "  match item {\n"
        "    Ok(number) => return 0,\n"
        "    Err(message) => return len(message)\n"
        "  }\n"
        "  return -1\n"
        "}\n",
        "m5-wasm-float-aggregates.rove",
    )
    wasm_float_aggregate_issues = collect_legalization_issues(
        wasm_float_aggregates, "wasm", require_emitter=True
    )
    assert not wasm_float_aggregate_issues, wasm_float_aggregate_issues
    wasm_float_aggregate_wat = emit_legalized_wat(wasm_float_aggregates)
    assert "f64.store" in wasm_float_aggregate_wat and "f64.load" in wasm_float_aggregate_wat
    wasm_float_aggregate_bytes = emit_legalized_wasm(wasm_float_aggregates)
    for function, arguments in (
        ("struct_probe", (3.5,)), ("nested_probe", ()),
        ("struct_array_probe", ()), ("enum_probe", (-1.25,)),
        ("result_ok", (4.75,)), ("result_error", ()),
    ):
        expected = MIRInterpreter(wasm_float_aggregates).run(function, arguments).value
        actual = _run_wasm_export(wasm_float_aggregate_bytes, function, *arguments).strip()
        assert float(actual) == expected, (function, arguments, actual, expected)
    wasm_float_scalar = _lower_source(
        "fn arithmetic(left: float, right: float) -> float {\n"
        "  return (left * right + 1.25) / 2.0\n"
        "}\n"
        "fn subtract(left: float, right: float) -> float { return left - right }\n"
        "fn negate(value: float) -> float { return -value }\n"
        "fn positive(value: float) -> float { return +value }\n"
        "fn convert(value: int) -> float { return value }\n"
        "fn add_int(value: int, delta: float) -> float { return value + delta }\n"
        "fn choose(value: float) -> int = match value { 7 => 1, _ => 0 }\n"
        "fn equal(left: float, right: float) -> bool { return left == right }\n"
        "fn unequal(left: float, right: float) -> bool { return left != right }\n"
        "fn less(left: float, right: float) -> bool { return left < right }\n"
        "fn less_equal(left: float, right: float) -> bool { return left <= right }\n"
        "fn greater(left: float, right: float) -> bool { return left > right }\n"
        "fn greater_equal(left: float, right: float) -> bool { return left >= right }\n"
        "fn divide(left: float, right: float) -> float { return left / right }\n",
        "m5-wasm-float-scalar.rove",
    )
    assert not collect_legalization_issues(wasm_float_scalar, "wasm", require_emitter=True)
    wasm_float_wat = emit_legalized_wat(wasm_float_scalar)
    assert "f64.convert_i64_s" in wasm_float_wat
    assert "f64.neg" in wasm_float_wat
    wasm_float_bytes = emit_legalized_wasm(wasm_float_scalar)
    for function, arguments in (
        ("arithmetic", (3.0, -2.5)), ("subtract", (3.0, 1.25)),
        ("negate", (2.75,)),
        ("positive", (-2.75,)), ("convert", (7,)),
        ("convert", (9223372036854775807,)),
        ("add_int", (7, 2.5)),
        ("divide", (1.0, 0.0)), ("divide", (1.0, -0.0)),
        ("divide", (0.0, 0.0)),
    ):
        expected = MIRInterpreter(wasm_float_scalar).run(function, arguments).value
        actual = _run_wasm_export(wasm_float_bytes, function, *arguments).strip()
        if expected != expected:
            assert actual == "NaN", (function, arguments, actual)
        else:
            assert float(actual) == expected, (function, arguments, actual, expected)
    for function, arguments in (
        ("choose", (7.0,)), ("choose", (8.0,)),
        ("equal", (1.5, 1.5)), ("equal", (1.5, 2.5)),
        ("unequal", (1.5, 2.5)), ("unequal", (1.5, 1.5)),
        ("less", (-0.0, 0.0)), ("less", (-2.0, 1.0)),
        ("less_equal", (1.5, 1.5)), ("greater", (3.0, 2.0)),
        ("greater_equal", (2.0, 2.0)), ("greater_equal", (1.0, 2.0)),
    ):
        expected = MIRInterpreter(wasm_float_scalar).run(function, arguments).value
        assert _run_wasm_export(wasm_float_bytes, function, *arguments) == f"{int(expected)}\n"
    wasm_float_remainder = _lower_source(
        "fn remainder(left: float, right: float) -> float { return left % right }\n",
        "m5-wasm-float-remainder.rove",
    )
    assert {issue.code for issue in collect_legalization_issues(
        wasm_float_remainder, "wasm", require_emitter=True
    )} == {"MIRG1010"}
    wasm_string_struct = _lower_source(
        "struct Label { text: string }\n"
        "fn string_struct_probe() -> int {\n"
        "  var original = Label(\"nyx\")\n"
        "  var copied = original\n"
        "  set copied.text = \"compiler\"\n"
        "  return len(original.text) * 100 + len(copied.text)\n"
        "}\n",
        "m5-wasm-string-struct.rove",
    )
    assert not collect_legalization_issues(wasm_string_struct, "wasm", require_emitter=True)
    assert MIRInterpreter(wasm_string_struct).run("string_struct_probe").value == 308
    wasm_string_struct_wat = emit_legalized_wat(wasm_string_struct)
    assert "(data (i32.const" in wasm_string_struct_wat and "memory.copy" in wasm_string_struct_wat
    assert _run_wasm_export(emit_legalized_wasm(wasm_string_struct), "string_struct_probe") == "308\n"

    wasm_string_ops = _lower_source(
        "struct TextBox { text: string }\n"
        "fn equal_copy() -> bool {\n"
        "  let first = TextBox(\"same\")\n"
        "  let second = first\n"
        "  return first.text == second.text\n"
        "}\n"
        "fn equal_concat() -> bool {\n"
        "  let first = TextBox(\"a\")\n"
        "  let second = TextBox(\"b\")\n"
        "  return first.text + second.text == \"ab\"\n"
        "}\n"
        "fn unequal() -> bool {\n"
        "  let first = TextBox(\"ab\")\n"
        "  let second = TextBox(\"ac\")\n"
        "  return first.text != second.text\n"
        "}\n"
        "fn order(left: string, right: string) -> bool { return left < right }\n"
        "fn prefix() -> bool { return order(\"ab\", \"abc\") }\n"
        "fn utf8() -> bool { return order(\"é\", \"🙂\") }\n"
        "fn reverse() -> bool { return order(\"z\", \"a\") }\n"
        "fn less_equal() -> bool {\n"
        "  let first = TextBox(\"same\")\n"
        "  let second = first\n"
        "  return first.text <= second.text\n"
        "}\n"
        "fn greater() -> bool {\n"
        "  let first = TextBox(\"zz\")\n"
        "  let second = TextBox(\"aa\")\n"
        "  return first.text > second.text\n"
        "}\n"
        "fn greater_equal() -> bool {\n"
        "  let first = TextBox(\"a\")\n"
        "  let second = TextBox(\"b\")\n"
        "  return first.text >= second.text\n"
        "}\n"
        "fn empty_concat() -> bool {\n"
        "  let empty = TextBox(\"\")\n"
        "  return empty.text + \"\" == \"\"\n"
        "}\n",
        "m5-wasm-string-operations.rove",
    )
    assert not collect_legalization_issues(wasm_string_ops, "wasm", require_emitter=True)
    wasm_string_ops_wat = emit_legalized_wat(wasm_string_ops)
    assert "call $rove_string_compare" in wasm_string_ops_wat
    assert "call $rove_string_concat" in wasm_string_ops_wat
    wasm_string_ops_bytes = emit_legalized_wasm(wasm_string_ops)
    for function, expected in (
        ("equal_copy", True), ("equal_concat", True),
        ("unequal", True), ("prefix", True), ("utf8", True),
        ("reverse", False), ("less_equal", True), ("greater", True),
        ("greater_equal", False), ("empty_concat", True),
    ):
        assert MIRInterpreter(wasm_string_ops).run(function).value is expected
        assert _run_wasm_export(wasm_string_ops_bytes, function) == (
            f"{int(expected)}\n"
        )

    string_type = MIRType("string")
    bad_wasm_span = MIRSpan("m5-wasm-string-op-gate.rove", 1, 1)
    bad_wasm_string = MIRFunctionBuilder(
        "bad_string", "function::bad_string", string_type, bad_wasm_span,
    )
    bad_wasm_block = bad_wasm_string.new_block()
    bad_wasm_string.push_statement(bad_wasm_block, AssignStatement(
        Place(0), BinaryRValue(
            "&", ConstOperand(string_type, "a"),
            ConstOperand(string_type, "b"), string_type,
        ), bad_wasm_span,
    ))
    bad_wasm_string.set_terminator(
        bad_wasm_block, ReturnTerminator(bad_wasm_span)
    )
    bad_wasm_module = MIRModule(
        bad_wasm_span.source, "wasm", (bad_wasm_string.finish(),)
    )
    assert {issue.code for issue in collect_legalization_issues(
        bad_wasm_module, "wasm", require_emitter=True
    )} == {"MIRG1010"}

    wasm_nested_struct = _lower_source(
        "struct Point { x: int }\n"
        "struct Box { point: Point, label: string }\n"
        "fn nested_struct_probe() -> int {\n"
        "  var original = Box(Point(2), \"a\")\n"
        "  var copied = original\n"
        "  set copied.point.x = 9\n"
        "  set copied.label = \"hello\"\n"
        "  return original.point.x * 100 + copied.point.x * 10 + len(copied.label)\n"
        "}\n",
        "m5-wasm-nested-struct.rove",
    )
    assert not collect_legalization_issues(wasm_nested_struct, "wasm", require_emitter=True)
    assert MIRInterpreter(wasm_nested_struct).run("nested_struct_probe").value == 295
    assert _run_wasm_export(
        emit_legalized_wasm(wasm_nested_struct), "nested_struct_probe"
    ) == "295\n"

    wasm_string_array = _lower_source(
        "fn string_array_probe() -> int {\n"
        "  var original = [\"a\", \"bb\"]\n"
        "  var copied = original\n"
        "  set copied[0] = \"hello\"\n"
        "  return len(original[0]) * 100 + len(copied[0]) * 10 + len(copied)\n"
        "}\n",
        "m5-wasm-string-array.rove",
    )
    assert not collect_legalization_issues(wasm_string_array, "wasm", require_emitter=True)
    assert MIRInterpreter(wasm_string_array).run("string_array_probe").value == 152
    wasm_string_array_wat = emit_legalized_wat(wasm_string_array)
    assert "call $__nyx_mir_array_clone_string" in wasm_string_array_wat
    assert "call $__nyx_mir_array_set_string" in wasm_string_array_wat
    assert _run_wasm_export(
        emit_legalized_wasm(wasm_string_array), "string_array_probe"
    ) == "152\n"

    wasm_struct_array = _lower_source(
        "struct Item { score: int, label: string }\n"
        "fn struct_array_probe() -> int {\n"
        "  var original = [Item(1, \"a\"), Item(2, \"bb\")]\n"
        "  var copied = original\n"
        "  set copied[0] = Item(9, \"hello\")\n"
        "  var detached = copied[1]\n"
        "  set detached.score = 7\n"
        "  set detached.label = \"compiler\"\n"
        "  let original_first = original[0]\n"
        "  let copied_first = copied[0]\n"
        "  let copied_second = copied[1]\n"
        "  return original_first.score * 10000 + copied_first.score * 1000 + "
        "len(copied_first.label) * 100 + copied_second.score * 10 + len(detached.label)\n"
        "}\n",
        "m5-wasm-struct-array.rove",
    )
    assert not collect_legalization_issues(wasm_struct_array, "wasm", require_emitter=True)
    assert MIRInterpreter(wasm_struct_array).run("struct_array_probe").value == 19528
    wasm_struct_array_wat = emit_legalized_wat(wasm_struct_array)
    assert "call $__nyx_mir_array_clone_blob" in wasm_struct_array_wat
    assert "call $__nyx_mir_array_get_blob" in wasm_struct_array_wat
    assert "call $__nyx_mir_array_set_blob" in wasm_struct_array_wat
    assert _run_wasm_export(
        emit_legalized_wasm(wasm_struct_array), "struct_array_probe"
    ) == "19528\n"

    wasm_string_enum = _lower_source(
        "enum Message { Text(string), Empty() }\n"
        "fn string_enum_probe() -> int {\n"
        "  let message = Text(\"hello\")\n"
        "  match message {\n"
        "    Text(value) => return len(value),\n"
        "    Empty() => return 0\n"
        "  }\n"
        "  return -1\n"
        "}\n",
        "m5-wasm-string-enum.rove",
    )
    assert not collect_legalization_issues(wasm_string_enum, "wasm", require_emitter=True)
    assert MIRInterpreter(wasm_string_enum).run("string_enum_probe").value == 5
    assert _run_wasm_export(
        emit_legalized_wasm(wasm_string_enum), "string_enum_probe"
    ) == "5\n"

    wasm_struct_enum = _lower_source(
        "struct EnumCell { value: int, label: string }\n"
        "enum Packet { Data(EnumCell), Empty() }\n"
        "fn struct_enum_probe() -> int {\n"
        "  let packet = Data(EnumCell(8, \"nyx\"))\n"
        "  match packet {\n"
        "    Data(cell) => return cell.value * 10 + len(cell.label),\n"
        "    Empty() => return 0\n"
        "  }\n"
        "  return -1\n"
        "}\n",
        "m5-wasm-struct-enum.rove",
    )
    assert not collect_legalization_issues(wasm_struct_enum, "wasm", require_emitter=True)
    assert MIRInterpreter(wasm_struct_enum).run("struct_enum_probe").value == 83
    assert _run_wasm_export(
        emit_legalized_wasm(wasm_struct_enum), "struct_enum_probe"
    ) == "83\n"

    wasm_string_result = _lower_source(
        "fn string_result_probe() -> int {\n"
        "  let result: Result<int, string> = Err(\"oops\")\n"
        "  match result {\n"
        "    Ok(value) => return value,\n"
        "    Err(message) => return len(message)\n"
        "  }\n"
        "  return -1\n"
        "}\n",
        "m5-wasm-string-result.rove",
    )
    assert not collect_legalization_issues(wasm_string_result, "wasm", require_emitter=True)
    assert MIRInterpreter(wasm_string_result).run("string_result_probe").value == 4
    assert _run_wasm_export(
        emit_legalized_wasm(wasm_string_result), "string_result_probe"
    ) == "4\n"

    wasm_struct_result = _lower_source(
        "struct ResultCell { value: int, label: string }\n"
        "fn struct_result_ok_probe() -> int {\n"
        "  let result: Result<ResultCell, string> = Ok(ResultCell(7, \"nyx\"))\n"
        "  match result {\n"
        "    Ok(cell) => return cell.value * 10 + len(cell.label),\n"
        "    Err(message) => return len(message)\n"
        "  }\n"
        "  return -1\n"
        "}\n"
        "fn struct_result_err_probe() -> int {\n"
        "  let result: Result<ResultCell, string> = Err(\"failure\")\n"
        "  match result {\n"
        "    Ok(cell) => return cell.value,\n"
        "    Err(message) => return len(message)\n"
        "  }\n"
        "  return -1\n"
        "}\n",
        "m5-wasm-struct-result.rove",
    )
    assert not collect_legalization_issues(wasm_struct_result, "wasm", require_emitter=True)
    assert MIRInterpreter(wasm_struct_result).run("struct_result_ok_probe").value == 73
    assert MIRInterpreter(wasm_struct_result).run("struct_result_err_probe").value == 7
    wasm_struct_result_bytes = emit_legalized_wasm(wasm_struct_result)
    assert _run_wasm_export(wasm_struct_result_bytes, "struct_result_ok_probe") == "73\n"
    assert _run_wasm_export(wasm_struct_result_bytes, "struct_result_err_probe") == "7\n"
    rejected_wasm = {issue.code for issue in collect_legalization_issues(scalar, "wasm")}
    assert "MIRG1007" in rejected_wasm, rejected_wasm

    unsupported_operation = _unsupported_operation_module()
    for target in MIR_BACKEND_MIGRATION_ORDER:
        issues = collect_legalization_issues(unsupported_operation, target, require_emitter=True)
        assert {issue.code for issue in issues} == {"MIRG1010"}, (target, issues)

    llvm_contract_rejections = _llvm_contract_rejection_modules()
    expected_llvm_rejection_codes = {
        "ordered-bool": {"MIRG1010"},
        "mixed-operands": {"MIRG1010"},
        "string-to-int-cast": {"MIRG1004"},
        "invalid-len": {"MIRG1007"},
        "recursive-struct": {"MIRG1002"},
    }
    for name, rejected_module in llvm_contract_rejections.items():
        issues = collect_legalization_issues(
            rejected_module, "llvm", require_emitter=True
        )
        assert {issue.code for issue in issues} == expected_llvm_rejection_codes[name], (
            name,
            issues,
        )
        try:
            emit_legalized_llvm(rejected_module)
            raise AssertionError(f"LLVM emitter accepted illegal MIR contract case '{name}'")
        except MIRLegalizationError:
            pass

    struct_display_prefix = (
        "struct Cell { value: int, label: string }\n"
        "enum Packet { Data(Cell), Empty() }\n"
    )
    for name, expression in (
        ("direct", 'print(Cell(2, "rove"))'),
        ("array", 'print([Cell(2, "rove")])'),
        ("tagged", 'print(Data(Cell(2, "rove")))'),
        ("to-string", 'print(to_string(Cell(2, "rove")))'),
    ):
        struct_display = _lower_source(
            struct_display_prefix + f"fn main() {{ {expression} }}\n",
            f"m5-struct-display-{name}-gate.rove",
        )
        for target in MIR_BACKEND_MIGRATION_ORDER:
            issues = collect_legalization_issues(
                struct_display, target, require_emitter=True
            )
            if target in {"cpp", "rust", "js", "python", "c"} or (
                target == "llvm" and name != "to-string"
            ):
                assert not issues, (name, issues)
                continue
            assert any(
                issue.code == "MIRG1007"
                and "Nominal struct display is not legalized"
                in issue.message
                for issue in issues
            ), (name, target, issues)

    suspending = _lower_source("async fn pending() -> void {}\n", "m5-suspend-effect.rove")
    assert suspending.functions[0].effects == ("may_suspend",)
    for target in tuple(item for item in MIR_BACKEND_MIGRATION_ORDER if item not in {"cpp", "rust", "js", "python"}):
        issues = collect_legalization_issues(suspending, target, require_emitter=True)
        assert {issue.code for issue in issues} == {"MIRG1011"}, (target, issues)
    assert not collect_legalization_issues(suspending, "rust", require_emitter=True)
    assert not collect_legalization_issues(suspending, "js", require_emitter=True)
    assert not collect_legalization_issues(suspending, "python", require_emitter=True)
    assert not collect_legalization_issues(suspending, "cpp", require_emitter=True)

    aggregate = _lower(AGGREGATE_FIXTURE)
    assert not collect_legalization_issues(aggregate, "cpp", require_emitter=True)
    expected_aggregate = "\n".join(MIRInterpreter(aggregate).run().output) + "\n"
    assert expected_aggregate == "1 9 9\nNyx\n9\n2\n3\n"
    assert _compile_and_run_cpp(emit_legalized_cpp(aggregate)) == expected_aggregate
    assert not collect_legalization_issues(aggregate, "js", require_emitter=True)
    assert _run_javascript(emit_legalized_javascript(aggregate)) == expected_aggregate
    assert not collect_legalization_issues(aggregate, "python", require_emitter=True)
    assert _run_python(emit_legalized_python(aggregate)) == expected_aggregate
    assert not collect_legalization_issues(aggregate, "rust", require_emitter=True)
    _assert_rust_runtime(emit_legalized_rust(aggregate), expected_aggregate)

    payload = _lower(PAYLOAD_FIXTURE)
    assert not collect_legalization_issues(payload, "cpp", require_emitter=True)
    expected_payload = "\n".join(MIRInterpreter(payload).run().output) + "\n"
    assert expected_payload == "hello\n"
    assert _compile_and_run_cpp(emit_legalized_cpp(payload)) == expected_payload
    assert not collect_legalization_issues(payload, "js", require_emitter=True)
    assert _run_javascript(emit_legalized_javascript(payload)) == expected_payload
    assert not collect_legalization_issues(payload, "python", require_emitter=True)
    assert _run_python(emit_legalized_python(payload)) == expected_payload
    assert not collect_legalization_issues(payload, "rust", require_emitter=True)
    _assert_rust_runtime(emit_legalized_rust(payload), expected_payload)

    control = _lower(CONTROL_FIXTURE)
    assert not collect_legalization_issues(control, "cpp", require_emitter=True)
    expected_control = "\n".join(MIRInterpreter(control).run().output) + "\n"
    assert _compile_and_run_cpp(emit_legalized_cpp(control)) == expected_control
    assert not collect_legalization_issues(control, "js", require_emitter=True)
    assert _run_javascript(emit_legalized_javascript(control)) == expected_control
    assert not collect_legalization_issues(control, "python", require_emitter=True)
    assert _run_python(emit_legalized_python(control)) == expected_control
    assert not collect_legalization_issues(control, "rust", require_emitter=True)
    generated_rust_control = emit_legalized_rust(control)
    assert "Result<i64, String>" in generated_rust_control
    assert "impl<T: RoveDisplay, E: RoveDisplay> RoveDisplay for Result<T, E>" in generated_rust_control
    assert "invalid Ok branch selected during Result re-homing" in generated_rust_control
    _assert_rust_runtime(generated_rust_control, expected_control)

    nested_values = _lower(NESTED_VALUES_FIXTURE)
    expected_nested_values = "\n".join(MIRInterpreter(nested_values).run().output) + "\n"
    assert expected_nested_values == "56 34 3\nOk([3, 4]) Err(bad)\n"
    assert not collect_legalization_issues(nested_values, "llvm", require_emitter=True)
    generated_llvm_nested = emit_legalized_llvm(nested_values)
    assert "call i64 @strlen" in generated_llvm_nested
    assert "array_print_check" in generated_llvm_nested
    assert _compile_and_run_llvm(generated_llvm_nested) == expected_nested_values
    result_probe = next(
        function for function in nested_values.functions
        if function.name == "result_probe"
    )
    owned_temporary_ids = {
        local.id for local in result_probe.locals
        if local.kind == "temporary" and local.type.name in {"Result", "string"}
    }
    assert owned_temporary_ids
    assert any(
        isinstance(statement, DeinitStatement)
        and statement.place.local in owned_temporary_ids
        for block in result_probe.blocks
        for statement in block.statements
    ), "temporary match subject/tag values must close on matched exits"
    assert not collect_legalization_issues(nested_values, "cpp", require_emitter=True)
    assert _compile_and_run_cpp(emit_legalized_cpp(nested_values)) == expected_nested_values
    assert not collect_legalization_issues(nested_values, "js", require_emitter=True)
    assert _run_javascript(emit_legalized_javascript(nested_values)) == expected_nested_values
    assert not collect_legalization_issues(nested_values, "python", require_emitter=True)
    assert _run_python(emit_legalized_python(nested_values)) == expected_nested_values
    assert not collect_legalization_issues(nested_values, "rust", require_emitter=True)
    generated_rust_nested = emit_legalized_rust(nested_values)
    assert "Result<Vec<i64>, String>" in generated_rust_nested
    assert "RoveType_Packet::Data" in generated_rust_nested
    _assert_rust_runtime(generated_rust_nested, expected_nested_values)

    async_tasks = _lower(ASYNC_FIXTURE)
    assert not collect_legalization_issues(async_tasks, "rust", require_emitter=True)
    expected_async_tasks = "\n".join(MIRInterpreter(async_tasks).run().output) + "\n"
    assert expected_async_tasks == "compute\n42\nawait-defer await-local\nasync boom\n"
    unhandled_async = next(
        function for function in async_tasks.functions
        if function.name == "unhandled_async"
    )
    unhandled_suspend = next(
        block.terminator
        for block in unhandled_async.blocks
        if isinstance(block.terminator, SuspendTerminator)
    )
    assert unhandled_suspend.unwind is not None
    assert unhandled_suspend.error_destination is not None
    assert any(
        isinstance(statement, DeinitStatement)
        and unhandled_async.locals[statement.place.local].name == "value"
        for block in unhandled_async.blocks
        for statement in block.statements
    )
    for function in async_tasks.functions:
        blocks = {block.id: block for block in function.blocks}
        for block in function.blocks:
            suspend = block.terminator
            if not isinstance(suspend, SuspendTerminator):
                continue
            if not isinstance(suspend.task, CopyOperand):
                continue
            task_local = function.locals[suspend.task.place.local]
            if task_local.kind != "temporary" or task_local.type.name != "Task":
                continue
            assert any(
                isinstance(statement, DeinitStatement)
                and statement.place.local == task_local.id
                for statement in blocks[suspend.resume].statements
            ), "a directly-awaited task temporary must close on the resume edge"
            if suspend.unwind is not None:
                assert sum(
                    isinstance(statement, DeinitStatement)
                    and statement.place.local == task_local.id
                    for candidate in function.blocks
                    for statement in candidate.statements
                ) >= 2, "a directly-awaited task temporary must close on success and unwind"
    assert not collect_legalization_issues(async_tasks, "cpp", require_emitter=True)
    generated_cpp_async = emit_legalized_cpp(async_tasks)
    assert "class task" in generated_cpp_async
    assert ".await_result()" in generated_cpp_async
    assert _compile_and_run_cpp(generated_cpp_async) == expected_async_tasks
    generated_rust_async = emit_legalized_rust(async_tasks)
    assert "struct RoveTask<T>" in generated_rust_async
    assert "RoveTaskState::Ready(result) => return result.clone()" in generated_rust_async
    assert ".await_result()" in generated_rust_async
    _assert_rust_runtime(generated_rust_async, expected_async_tasks)
    assert not collect_legalization_issues(async_tasks, "js", require_emitter=True)
    generated_javascript_async = emit_legalized_javascript(async_tasks)
    assert "class RoveTask" in generated_javascript_async
    assert ".awaitResult()" in generated_javascript_async
    assert _run_javascript(generated_javascript_async) == expected_async_tasks
    assert not collect_legalization_issues(async_tasks, "python", require_emitter=True)
    generated_python_async = emit_legalized_python(async_tasks)
    assert "class RoveTask" in generated_python_async
    assert ".await_result()" in generated_python_async
    assert _run_python(generated_python_async) == expected_async_tasks

    llvm_structs = _lower(LLVM_STRUCT_FIXTURE)
    assert not collect_legalization_issues(llvm_structs, "llvm", require_emitter=True)
    expected_llvm_structs = "\n".join(MIRInterpreter(llvm_structs).run().output) + "\n"
    assert expected_llvm_structs == "4 9 true false\n1 9 nyx llvm\n"
    generated_llvm_structs = emit_legalized_llvm(llvm_structs)
    assert "%rove_type_Envelope = type" in generated_llvm_structs
    assert "insertvalue %rove_type_Envelope" in generated_llvm_structs
    assert "getelementptr inbounds %rove_type_Envelope" in generated_llvm_structs
    assert "@rove_struct_Owned_clone" in generated_llvm_structs
    assert "@rove_array_i64_clone" in generated_llvm_structs
    assert _compile_and_run_llvm(generated_llvm_structs) == expected_llvm_structs

    llvm_arrays = _lower(LLVM_ARRAY_FIXTURE)
    assert not collect_legalization_issues(llvm_arrays, "llvm", require_emitter=True)
    expected_llvm_arrays = "\n".join(MIRInterpreter(llvm_arrays).run().output) + "\n"
    assert expected_llvm_arrays == "1 9 3 1\ntrue false 2\nnyx llvm 2\n"
    generated_llvm_arrays = emit_legalized_llvm(llvm_arrays)
    assert "%rove_array_i64 = type" in generated_llvm_arrays
    assert "@rove_array_i64_clone" in generated_llvm_arrays
    assert "@rove_array_i64_at" in generated_llvm_arrays
    assert "@rove_array_bool_clone" in generated_llvm_arrays
    assert "@rove_array_string_clone" in generated_llvm_arrays
    assert _compile_and_run_llvm(generated_llvm_arrays) == expected_llvm_arrays

    llvm_float_arrays = _lower_source(
        "struct Cell { samples: Array<float> }\n"
        "enum Packet { Data(Array<float>), Empty() }\n"
        "fn main() {\n"
        "  var values = [2.0, -0.0, 0.0000001]\n"
        "  let copied = values\n"
        "  values[0] = 9.0\n"
        "  print(values, copied, values[2], len(values))\n"
        "  print(Cell(copied))\n"
        "  print(Data(values))\n"
        "  let good: Result<Array<float>, string> = Ok(copied)\n"
        "  print(good)\n"
        "  print([[1.0, 2.5], [3.0]])\n"
        "}\n",
        "m5-llvm-float-arrays.rove",
    )
    expected_llvm_float_arrays = (
        "[9, 0, 1e-7] [2, 0, 1e-7] 1e-7 3\n"
        "Cell([2, 0, 1e-7])\n"
        "Data([9, 0, 1e-7])\n"
        "Ok([2, 0, 1e-7])\n"
        "[[1, 2.5], [3]]\n"
    )
    assert "\n".join(MIRInterpreter(llvm_float_arrays).run().output) + "\n" == (
        expected_llvm_float_arrays
    )
    assert not collect_legalization_issues(
        llvm_float_arrays, "llvm", require_emitter=True
    )
    generated_llvm_float_arrays = emit_legalized_llvm(llvm_float_arrays)
    assert "%rove_array_f64 = type" in generated_llvm_float_arrays
    assert "@rove_array_f64_clone" in generated_llvm_float_arrays
    assert "@rove_array_f64_destroy" in generated_llvm_float_arrays
    assert "@rove_array_array_f64_clone" in generated_llvm_float_arrays
    assert _compile_and_run_llvm(generated_llvm_float_arrays) == (
        expected_llvm_float_arrays
    )
    for emitter, runner in (
        (emit_legalized_cpp, _compile_and_run_cpp),
        (emit_legalized_c17, _compile_and_run_c17),
        (emit_legalized_javascript, _run_javascript),
        (emit_legalized_python, _run_python),
    ):
        assert runner(emitter(llvm_float_arrays)) == expected_llvm_float_arrays
    _assert_rust_runtime(emit_legalized_rust(llvm_float_arrays), expected_llvm_float_arrays)

    llvm_struct_arrays = _lower(LLVM_STRUCT_ARRAY_FIXTURE)
    llvm_struct_array_issues = collect_legalization_issues(
        llvm_struct_arrays, "llvm", require_emitter=True
    )
    assert not llvm_struct_array_issues, llvm_struct_array_issues
    expected_llvm_struct_arrays = "\n".join(
        MIRInterpreter(llvm_struct_arrays).run().output
    ) + "\n"
    assert expected_llvm_struct_arrays == "7 9 2 7 3\n"
    generated_llvm_struct_arrays = emit_legalized_llvm(llvm_struct_arrays)
    assert "%rove_array_struct_Cell = type" in generated_llvm_struct_arrays
    assert "@rove_array_struct_Cell_clone" in generated_llvm_struct_arrays
    assert "@rove_array_struct_Cell_destroy" in generated_llvm_struct_arrays
    assert "@rove_struct_Cell_clone" in generated_llvm_struct_arrays
    assert "@rove_array_i64_clone" in generated_llvm_struct_arrays
    assert "@rove_tagged_CellBatch_clone" in generated_llvm_struct_arrays
    assert "@rove_tagged_CellBatch_destroy" in generated_llvm_struct_arrays
    assert _compile_and_run_llvm(
        generated_llvm_struct_arrays
    ) == expected_llvm_struct_arrays

    llvm_nested_arrays = _lower(LLVM_NESTED_ARRAY_FIXTURE)
    llvm_nested_array_issues = collect_legalization_issues(
        llvm_nested_arrays, "llvm", require_emitter=True
    )
    assert not llvm_nested_array_issues, llvm_nested_array_issues
    expected_llvm_nested_arrays = "\n".join(
        MIRInterpreter(llvm_nested_arrays).run().output
    ) + "\n"
    assert expected_llvm_nested_arrays == (
        "[[1, 2], [3]] 2 1\n"
        "4 8\n"
        "Data([[1, 2], [3]])\n"
    )
    generated_llvm_nested_arrays = emit_legalized_llvm(llvm_nested_arrays)
    assert "%rove_array_array_i64 = type" in generated_llvm_nested_arrays
    assert "@rove_array_array_i64_clone" in generated_llvm_nested_arrays
    assert "@rove_array_array_i64_destroy" in generated_llvm_nested_arrays
    assert "@rove_tagged_Matrix_clone" in generated_llvm_nested_arrays
    assert "array_print_check" in generated_llvm_nested_arrays
    assert _compile_and_run_llvm(
        generated_llvm_nested_arrays
    ) == expected_llvm_nested_arrays

    llvm_lifecycle = _llvm_value_lifecycle_module()
    assert not collect_legalization_issues(
        llvm_lifecycle, "llvm", require_emitter=True
    )
    generated_llvm_lifecycle = emit_legalized_llvm(llvm_lifecycle)
    assert "call void @rove_array_i64_destroy" in generated_llvm_lifecycle
    assert "call void @rove_struct_Owned_destroy" in generated_llvm_lifecycle
    assert "call void @free" in generated_llvm_lifecycle
    assert _compile_and_run_llvm(generated_llvm_lifecycle) == ""

    for lifecycle_target in ("js", "python", "c"):
        lifecycle_issues = collect_legalization_issues(
            llvm_lifecycle, lifecycle_target, require_emitter=True
        )
        assert not lifecycle_issues, (lifecycle_target, lifecycle_issues)
    generated_javascript_lifecycle = emit_legalized_javascript(llvm_lifecycle)
    assert "= undefined" in generated_javascript_lifecycle
    assert _run_javascript(generated_javascript_lifecycle) == ""
    generated_python_lifecycle = emit_legalized_python(llvm_lifecycle)
    assert "= None" in generated_python_lifecycle
    assert _run_python(generated_python_lifecycle) == ""
    generated_c17_lifecycle = emit_legalized_c17(llvm_lifecycle)
    assert "memset(&(l" in generated_c17_lifecycle
    assert _compile_and_run_c17(generated_c17_lifecycle) == ""
    wasm_lifecycle = _array_lifecycle_module()
    assert not collect_legalization_issues(
        wasm_lifecycle, "wasm", require_emitter=True
    )
    generated_wasm_lifecycle = emit_legalized_wasm(wasm_lifecycle)
    assert _run_wasm_export(generated_wasm_lifecycle, "main") == "undefined\n"

    llvm_tagged = _lower(LLVM_TAGGED_FIXTURE)
    assert not collect_legalization_issues(
        llvm_tagged, "llvm", require_emitter=True
    )
    expected_llvm_tagged = "\n".join(MIRInterpreter(llvm_tagged).run().output) + "\n"
    assert expected_llvm_tagged == (
        "ok 4\nerr division by zero\nnumber 7\ntext nyx\n"
        "strings true true true\nOk(8) Err(bad)\nIdle()\n"
    )
    generated_llvm_tagged = emit_legalized_llvm(llvm_tagged)
    assert "%rove_tagged = type { ptr, [4 x i64] }" in generated_llvm_tagged
    assert "extractvalue %rove_tagged" in generated_llvm_tagged
    assert "call i32 @strcmp" in generated_llvm_tagged
    assert "tag_print_variant" in generated_llvm_tagged
    assert _compile_and_run_llvm(generated_llvm_tagged) == expected_llvm_tagged

    llvm_owned_tagged = _lower(LLVM_OWNED_TAGGED_FIXTURE)
    llvm_owned_tagged_issues = collect_legalization_issues(
        llvm_owned_tagged, "llvm", require_emitter=True
    )
    assert not llvm_owned_tagged_issues, llvm_owned_tagged_issues
    expected_llvm_owned_tagged = "\n".join(
        MIRInterpreter(llvm_owned_tagged).run().output
    ) + "\n"
    assert expected_llvm_owned_tagged == (
        "12 34 0 56 2 23\nOk([3, 4]) Err(bad)\n"
        "[7, 8]\nPair([1, 2], [3, 4])\n"
    )
    generated_llvm_owned_tagged = emit_legalized_llvm(llvm_owned_tagged)
    assert "@rove_tagged_Batch_clone" in generated_llvm_owned_tagged
    assert "@rove_tagged_Batch_destroy" in generated_llvm_owned_tagged
    assert "@rove_tagged_Result_Array_int_string_destroy" in generated_llvm_owned_tagged
    assert "call ptr @malloc" in generated_llvm_owned_tagged
    assert "call void @free" in generated_llvm_owned_tagged
    assert "array_print_check" in generated_llvm_owned_tagged
    assert _compile_and_run_llvm(
        generated_llvm_owned_tagged
    ) == expected_llvm_owned_tagged

    llvm_struct_display = _lower_source(
        "struct Cell { value: int, label: string }\n"
        "struct Envelope { cell: Cell, flags: Array<bool> }\n"
        "enum Packet { Data(Envelope), Empty() }\n"
        "fn main() {\n"
        "  print(Cell(2, \"rove\"))\n"
        "  print([Cell(1, \"a\"), Cell(3, \"b\")])\n"
        "  print(Data(Envelope(Cell(4, \"x\"), [true, false])))\n"
        "  let good: Result<Envelope, string> = "
        "Ok(Envelope(Cell(5, \"ok\"), [false]))\n"
        "  print(good)\n"
        "}\n",
        "m5-llvm-struct-display.rove",
    )
    expected_llvm_struct_display = (
        "Cell(2, rove)\n"
        "[Cell(1, a), Cell(3, b)]\n"
        "Data(Envelope(Cell(4, x), [true, false]))\n"
        "Ok(Envelope(Cell(5, ok), [false]))\n"
    )
    assert "\n".join(MIRInterpreter(llvm_struct_display).run().output) + "\n" == (
        expected_llvm_struct_display
    )
    assert not collect_legalization_issues(
        llvm_struct_display, "llvm", require_emitter=True
    )
    assert _compile_and_run_llvm(emit_legalized_llvm(llvm_struct_display)) == (
        expected_llvm_struct_display
    )
    assert _compile_and_run_cpp(emit_legalized_cpp(llvm_struct_display)) == (
        expected_llvm_struct_display
    )
    assert not collect_legalization_issues(
        llvm_struct_display, "c", require_emitter=True
    )
    assert _compile_and_run_c17(emit_legalized_c17(llvm_struct_display)) == (
        expected_llvm_struct_display
    )
    c17_display = _lower_source(
        "enum Signal { Ready(int, bool, string), Idle() }\n"
        "fn main() {\n"
        "  print([true, false], [\"rove\", \"c17\"])\n"
        "  print(Ready(7, true, \"go\"), Idle())\n"
        "}\n",
        "m5-c17-display.rove",
    )
    expected_c17_display = "[true, false] [rove, c17]\nReady(7, true, go) Idle()\n"
    assert "\n".join(MIRInterpreter(c17_display).run().output) + "\n" == (
        expected_c17_display
    )
    assert not collect_legalization_issues(c17_display, "c", require_emitter=True)
    assert _compile_and_run_c17(emit_legalized_c17(c17_display)) == expected_c17_display
    c17_float_aggregates = _lower_source(
        "struct Sample { value: float, readings: Array<float> }\n"
        "enum Packet { Point(float, float), Samples(Array<float>), Empty() }\n"
        "fn main() {\n"
        "  let sample = Sample(2.0, [1.25, -0.0])\n"
        "  print(sample, to_string(sample.readings))\n"
        "  var values = [2.0, 3.5]\n"
        "  let copied = values\n"
        "  values[0] = 9.0\n"
        "  print(values, copied)\n"
        "  print(Point(1.0, -0.0), Samples([0.00001, 2.0]))\n"
        "  let good: Result<Array<float>, string> = Ok([1.5, 2.5])\n"
        "  print(to_string(good))\n"
        "  print([[1.0], [2.0, -0.0]])\n"
        "}\n",
        "m5-c17-float-aggregates.rove",
    )
    expected_c17_float_aggregates = (
        "Sample(2, [1.25, 0]) [1.25, 0]\n"
        "[9, 3.5] [2, 3.5]\n"
        "Point(1, 0) Samples([0.00001, 2])\n"
        "Ok([1.5, 2.5])\n"
        "[[1], [2, 0]]\n"
    )
    assert "\n".join(MIRInterpreter(c17_float_aggregates).run().output) + "\n" == (
        expected_c17_float_aggregates
    )
    assert not collect_legalization_issues(
        c17_float_aggregates, "c", require_emitter=True
    )
    for emitter, runner in (
        (emit_legalized_cpp, _compile_and_run_cpp),
        (emit_legalized_c17, _compile_and_run_c17),
        (emit_legalized_javascript, _run_javascript),
        (emit_legalized_python, _run_python),
    ):
        assert runner(emitter(c17_float_aggregates)) == expected_c17_float_aggregates
    f64_span = MIRSpan("m5-c17-f64-array.rove", 1, 1)
    f64_type = MIRType("f64")
    f64_array_type = MIRType("Array", (f64_type,))
    f64_builder = MIRFunctionBuilder(
        "main", "function::main", MIRType("any"), f64_span
    )
    f64_local = f64_builder.new_local("values", f64_array_type)
    f64_entry = f64_builder.new_block()
    f64_after = f64_builder.new_block()
    f64_builder.push_statement(f64_entry, AssignStatement(
        Place(f64_local), AggregateRValue(
            "array", "Array",
            (ConstOperand(f64_type, 1.0), ConstOperand(f64_type, -0.0)),
            f64_array_type,
        ), f64_span,
    ))
    f64_builder.set_terminator(f64_entry, CallTerminator(
        "builtin::print", (CopyOperand(Place(f64_local)),),
        None, f64_after, None, f64_span,
    ))
    f64_builder.set_terminator(f64_after, ReturnTerminator(f64_span))
    f64_module = MIRModule(
        f64_span.source, "c",
        (replace(f64_builder.finish(), effects=("may_allocate", "io")),),
    )
    assert not collect_legalization_issues(f64_module, "c", require_emitter=True)
    assert MIRInterpreter(f64_module).run().output == ("[1, 0]",)
    assert _compile_and_run_c17(emit_legalized_c17(f64_module)) == (
        "[1, 0]\n"
    )
    assert not collect_legalization_issues(f64_module, "llvm", require_emitter=True)
    assert _compile_and_run_llvm(emit_legalized_llvm(f64_module)) == (
        "[1, 0]\n"
    )
    c17_to_string = _lower_source(
        "struct Cell { value: int }\n"
        "enum Batch { Cells(Array<Array<Cell>>), Empty() }\n"
        "fn main() {\n"
        "  print(to_string(Cells([[Cell(1)], [Cell(2), Cell(3)]])))\n"
        "  let good: Result<Cell, string> = Ok(Cell(4))\n"
        "  print(to_string(good), to_string(Empty()))\n"
        "  print(to_string(-7), to_string(false))\n"
        f'  print(to_string("{"x" * 128}"))\n'
        "}\n",
        "m5-c17-to-string.rove",
    )
    expected_c17_to_string = (
        "Cells([[Cell(1)], [Cell(2), Cell(3)]])\n"
        "Ok(Cell(4)) Empty()\n"
        "-7 false\n"
        + "x" * 128 + "\n"
    )
    assert "\n".join(MIRInterpreter(c17_to_string).run().output) + "\n" == (
        expected_c17_to_string
    )
    assert not collect_legalization_issues(c17_to_string, "c", require_emitter=True)
    assert _compile_and_run_c17(emit_legalized_c17(c17_to_string)) == (
        expected_c17_to_string
    )
    c17_unsupported_display = _lower_source(
        "struct Maybe { value: string? }\n"
        "fn main() { print(Maybe(null)) }\n",
        "m5-c17-unsupported-display.rove",
    )
    assert any(
        issue.code == "MIRG1007" and "C17 display cannot format" in issue.message
        for issue in collect_legalization_issues(
            c17_unsupported_display, "c", require_emitter=True
        )
    )
    c17_float_to_string = _lower_source(
        "fn main() {\n"
        "  print(to_string(2.0), to_string(-0.0), to_string(0.00001))\n"
        "  print(to_string(0.0001), to_string(1000000000000000.0))\n"
        "  print(to_string(10000000000000000.0), "
        "to_string(1.2345678901234567))\n"
        "  print(to_string(1.0 / 0.0), to_string(0.0 / 0.0))\n"
        "}\n",
        "m5-c17-float-to-string.rove",
    )
    expected_c17_float = (
        "2 0 0.00001\n"
        "0.0001 1000000000000000\n"
        "10000000000000000 1.2345678901234567\n"
        "inf nan\n"
    )
    assert "\n".join(MIRInterpreter(c17_float_to_string).run().output) + "\n" == (
        expected_c17_float
    )
    assert not collect_legalization_issues(
        c17_float_to_string, "c", require_emitter=True
    )
    assert _compile_and_run_c17(emit_legalized_c17(c17_float_to_string)) == (
        expected_c17_float
    )
    assert _run_javascript(emit_legalized_javascript(llvm_struct_display)) == (
        expected_llvm_struct_display
    )
    assert _run_python(emit_legalized_python(llvm_struct_display)) == (
        expected_llvm_struct_display
    )
    generated_rust_struct_display = emit_legalized_rust(llvm_struct_display)
    assert "impl RoveDisplay for RoveType_Cell" in generated_rust_struct_display
    assert "impl RoveDisplay for RoveType_Packet" in generated_rust_struct_display
    _assert_rust_runtime(generated_rust_struct_display, expected_llvm_struct_display)
    struct_to_string = _lower_source(
        "struct Cell { value: int, label: string }\n"
        "fn main() { print(to_string(Cell(6, \"rove\"))) }\n",
        "m5-struct-to-string.rove",
    )
    assert MIRInterpreter(struct_to_string).run().output == ("Cell(6, rove)",)
    for target, emitter, runner in (
        ("cpp", emit_legalized_cpp, _compile_and_run_cpp),
        ("c", emit_legalized_c17, _compile_and_run_c17),
        ("js", emit_legalized_javascript, _run_javascript),
        ("python", emit_legalized_python, _run_python),
    ):
        assert not collect_legalization_issues(
            struct_to_string, target, require_emitter=True
        )
        assert runner(emitter(struct_to_string)) == "Cell(6, rove)\n"
    assert not collect_legalization_issues(
        struct_to_string, "rust", require_emitter=True
    )
    _assert_rust_runtime(emit_legalized_rust(struct_to_string), "Cell(6, rove)\n")
    nested_struct_tag = _lower_source(
        "struct Cell { value: int }\n"
        "enum Batch { Cells(Array<Array<Cell>>), Empty() }\n"
        "fn main() { print(Cells([[Cell(1)], [Cell(2), Cell(3)]])) }\n",
        "m5-nested-struct-tag-display.rove",
    )
    expected_nested_struct_tag = "Cells([[Cell(1)], [Cell(2), Cell(3)]])\n"
    assert MIRInterpreter(nested_struct_tag).run().output == (
        "Cells([[Cell(1)], [Cell(2), Cell(3)]])",
    )
    for target, emitter, runner in (
        ("cpp", emit_legalized_cpp, _compile_and_run_cpp),
        ("llvm", emit_legalized_llvm, _compile_and_run_llvm),
        ("c", emit_legalized_c17, _compile_and_run_c17),
        ("js", emit_legalized_javascript, _run_javascript),
        ("python", emit_legalized_python, _run_python),
    ):
        assert not collect_legalization_issues(
            nested_struct_tag, target, require_emitter=True
        )
        assert runner(emitter(nested_struct_tag)) == expected_nested_struct_tag
    assert not collect_legalization_issues(
        nested_struct_tag, "rust", require_emitter=True
    )
    _assert_rust_runtime(
        emit_legalized_rust(nested_struct_tag), expected_nested_struct_tag
    )

    unsupported_cpp_struct_display = _lower_source(
        "struct Maybe { value: string? }\n"
        "fn main() { print(Maybe(null)) }\n",
        "m5-cpp-optional-struct-display-gate.rove",
    )
    assert any(
        issue.code == "MIRG1007" and "Nominal struct display" in issue.message
        for issue in collect_legalization_issues(
            unsupported_cpp_struct_display, "cpp", require_emitter=True
        )
    )

    nested_array_display = _lower_source(
        "enum Batch { Flags(Array<Array<bool>>), Labels(Array<Array<string>>) }\n"
        "fn main() {\n"
        "  print([[true, false], [false]], [[\"a\", \"b\"], [\"c\"]])\n"
        "  print(Flags([[true]]), Labels([[\"rove\"]]))\n"
        "}\n",
        "m5-nested-array-display.rove",
    )
    expected_nested_array_display = (
        "[[true, false], [false]] [[a, b], [c]]\n"
        "Flags([[true]]) Labels([[rove]])\n"
    )
    assert "\n".join(MIRInterpreter(nested_array_display).run().output) + "\n" == (
        expected_nested_array_display
    )
    assert not collect_legalization_issues(
        nested_array_display, "llvm", require_emitter=True
    )
    assert _compile_and_run_llvm(emit_legalized_llvm(nested_array_display)) == (
        expected_nested_array_display
    )
    assert _run_javascript(emit_legalized_javascript(nested_array_display)) == (
        expected_nested_array_display
    )
    assert _run_python(emit_legalized_python(nested_array_display)) == (
        expected_nested_array_display
    )

    llvm_rejected_array = _lower_source(
        "fn main() { let values: Array<float?> = [null]; print(len(values)) }\n",
        "m5-llvm-optional-float-array-rejected.rove",
    )
    llvm_rejected_array_issues = collect_legalization_issues(
        llvm_rejected_array, "llvm", require_emitter=True
    )
    assert any(
        issue.code == "MIRG1002"
        and "supports Array<int|bool|float|string|acyclic-struct>" in issue.message
        for issue in llvm_rejected_array_issues
    ), llvm_rejected_array_issues

    cpp_call_unwind = _lower_source(
        "fn local_catch() -> int {\n"
        "  try { throw \"local\" } catch err { return len(err) }\n"
        "  return 0\n"
        "}\n"
        "fn fail() -> int {\n"
        "  defer print(\"cleanup\")\n"
        "  throw \"boom\"\n"
        "  return 0\n"
        "}\n"
        "fn main() {\n"
        "  try { print(fail()) } catch err { print(\"caught\", err) }\n"
        "  print(\"local\", local_catch())\n"
        "}\n",
        "m5-cpp-call-unwind.rove",
    )
    cpp_call_unwind_issues = collect_legalization_issues(
        cpp_call_unwind, "cpp", require_emitter=True
    )
    assert not cpp_call_unwind_issues, cpp_call_unwind_issues
    expected_cpp_call_unwind = "\n".join(
        MIRInterpreter(cpp_call_unwind).run().output
    ) + "\n"
    assert expected_cpp_call_unwind == "cleanup\ncaught boom\nlocal 5\n"
    generated_cpp_call_unwind = emit_legalized_cpp(cpp_call_unwind)
    assert "catch (const nyx_mir_runtime::user_throw& thrown)" in generated_cpp_call_unwind
    assert _compile_and_run_cpp(generated_cpp_call_unwind) == expected_cpp_call_unwind
    assert not collect_legalization_issues(
        cpp_call_unwind, "js", require_emitter=True
    )
    assert _run_javascript(
        emit_legalized_javascript(cpp_call_unwind)
    ) == expected_cpp_call_unwind
    assert not collect_legalization_issues(
        cpp_call_unwind, "python", require_emitter=True
    )
    assert _run_python(emit_legalized_python(cpp_call_unwind)) == expected_cpp_call_unwind
    assert not collect_legalization_issues(
        cpp_call_unwind, "rust", require_emitter=True
    )
    generated_rust_call_unwind = emit_legalized_rust(cpp_call_unwind)
    assert "RoveCallResult" in generated_rust_call_unwind
    assert "match rove_fn_fail()" in generated_rust_call_unwind
    assert "Err(rove_throw)" in generated_rust_call_unwind
    rust_inferred_unwind = replace(
        cpp_call_unwind,
        functions=tuple(replace(function, effects=()) for function in cpp_call_unwind.functions),
    )
    assert "RoveCallResult" in emit_legalized_rust(rust_inferred_unwind)
    _assert_rust_runtime(generated_rust_call_unwind, expected_cpp_call_unwind)

    pattern_cleanup = _lower(PATTERN_CLEANUP_FIXTURE)
    expected_pattern_cleanup = (
        "stmt-hit\nexpr-hit\ncaught boom\nwildcard\nlegacy-wildcard\nowned 3 2\n"
        "result Err(bad)\nbound borrowed\nsource borrowed\nreturned 2\n"
    )
    assert "\n".join(MIRInterpreter(pattern_cleanup).run().output) + "\n" == (
        expected_pattern_cleanup
    )
    for target, emitter, runner in (
        ("cpp", emit_legalized_cpp, _compile_and_run_cpp),
        ("js", emit_legalized_javascript, _run_javascript),
        ("python", emit_legalized_python, _run_python),
    ):
        assert not collect_legalization_issues(
            pattern_cleanup, target, require_emitter=True
        )
        assert runner(emitter(pattern_cleanup)) == expected_pattern_cleanup
    assert not collect_legalization_issues(
        pattern_cleanup, "rust", require_emitter=True
    )
    _assert_rust_runtime(
        emit_legalized_rust(pattern_cleanup), expected_pattern_cleanup
    )

    owned_throw = _lower_source(
        "fn main() {\n"
        "  try {\n"
        "    let message: string = \"boom\"\n"
        "    defer print(\"defer\", message)\n"
        "    throw message\n"
        "  } catch err { print(\"caught\", err) }\n"
        "}\n",
        "m5-owned-throw.rove",
    )
    expected_owned_throw = "defer boom\ncaught boom\n"
    assert "\n".join(MIRInterpreter(owned_throw).run().output) + "\n" == expected_owned_throw
    assert not collect_legalization_issues(owned_throw, "cpp", require_emitter=True)
    assert _compile_and_run_cpp(emit_legalized_cpp(owned_throw)) == expected_owned_throw
    for target, emit, run in (
        ("js", emit_legalized_javascript, _run_javascript),
        ("python", emit_legalized_python, _run_python),
    ):
        assert not collect_legalization_issues(owned_throw, target, require_emitter=True)
        assert run(emit(owned_throw)) == expected_owned_throw
    assert not collect_legalization_issues(owned_throw, "rust", require_emitter=True)
    _assert_rust_runtime(emit_legalized_rust(owned_throw), expected_owned_throw)

    argument_unwind = _lower_source(
        "fn make_values() -> Array<int> { return [1, 2] }\n"
        "fn fail() -> int { throw \"arg-fail\"; return 0 }\n"
        "fn consume(values: Array<int>, number: int) -> void { print(len(values), number) }\n"
        "fn main() {\n"
        "  try { consume(make_values(), fail()) }\n"
        "  catch err { print(\"caught\", err) }\n"
        "  consume(make_values(), 3)\n"
        "}\n",
        "m5-argument-unwind.rove",
    )
    expected_argument_unwind = "caught arg-fail\n2 3\n"
    assert "\n".join(MIRInterpreter(argument_unwind).run().output) + "\n" == expected_argument_unwind
    assert not collect_legalization_issues(argument_unwind, "cpp", require_emitter=True)
    assert _compile_and_run_cpp(emit_legalized_cpp(argument_unwind)) == expected_argument_unwind
    for target, emit, run in (
        ("js", emit_legalized_javascript, _run_javascript),
        ("python", emit_legalized_python, _run_python),
    ):
        assert not collect_legalization_issues(argument_unwind, target, require_emitter=True)
        assert run(emit(argument_unwind)) == expected_argument_unwind
    assert not collect_legalization_issues(argument_unwind, "rust", require_emitter=True)
    _assert_rust_runtime(emit_legalized_rust(argument_unwind), expected_argument_unwind)

    ordered_operand_unwind = _lower_source(
        "fn make_text() -> string { return \"left\" }\n"
        "fn fail_text() -> string { throw \"operand-fail\"; return \"\" }\n"
        "fn main() {\n"
        "  try { print(make_text() + fail_text()) }\n"
        "  catch err { print(\"binary\", err) }\n"
        "  try { let values: Array<string> = [make_text(), fail_text()] }\n"
        "  catch err { print(\"array\", err) }\n"
        "}\n",
        "m5-ordered-operand-unwind.rove",
    )
    expected_ordered_unwind = "binary operand-fail\narray operand-fail\n"
    assert "\n".join(MIRInterpreter(ordered_operand_unwind).run().output) + "\n" == expected_ordered_unwind
    assert not collect_legalization_issues(ordered_operand_unwind, "cpp", require_emitter=True)
    assert _compile_and_run_cpp(emit_legalized_cpp(ordered_operand_unwind)) == expected_ordered_unwind
    for target, emit, run in (
        ("js", emit_legalized_javascript, _run_javascript),
        ("python", emit_legalized_python, _run_python),
    ):
        assert not collect_legalization_issues(ordered_operand_unwind, target, require_emitter=True)
        assert run(emit(ordered_operand_unwind)) == expected_ordered_unwind
    assert not collect_legalization_issues(ordered_operand_unwind, "rust", require_emitter=True)
    _assert_rust_runtime(emit_legalized_rust(ordered_operand_unwind), expected_ordered_unwind)

    assert not collect_legalization_issues(scalar, "rust", require_emitter=True)
    _assert_rust_runtime(emit_legalized_rust(scalar), "13\n")
    assert not collect_legalization_issues(scalar, "js", require_emitter=True)
    assert _run_javascript(emit_legalized_javascript(scalar)) == "13\n"
    assert not collect_legalization_issues(scalar, "python", require_emitter=True)
    assert _run_python(emit_legalized_python(scalar)) == "13\n"
    assert not collect_legalization_issues(scalar, "c", require_emitter=True)
    assert _compile_and_run_c17(emit_legalized_c17(scalar)) == "13\n"

    c17_struct = _lower_source(
        "struct Pair { x: int, y: int }\n"
        "fn main() {\n"
        "  var original = Pair(4, 5)\n"
        "  var copied = original\n"
        "  set copied.x = 9\n"
        "  print(original.x * 100 + copied.x * 10 + copied.y)\n"
        "}\n",
        "m5-c17-struct.rove",
    )
    assert not collect_legalization_issues(c17_struct, "c", require_emitter=True)
    expected_c17_struct = "\n".join(MIRInterpreter(c17_struct).run().output) + "\n"
    assert expected_c17_struct == "495\n"
    generated_c17_struct = emit_legalized_c17(c17_struct)
    assert "typedef struct RoveStruct_Pair" in generated_c17_struct
    assert ".x =" in generated_c17_struct
    assert _compile_and_run_c17(generated_c17_struct) == expected_c17_struct

    c17_mixed_struct = _lower_source(
        "struct Record { count: int, active: bool, label: string }\n"
        "fn main() {\n"
        "  var original = Record(4, true, \"nyx\")\n"
        "  var copied = original\n"
        "  set copied.count = 9\n"
        "  set copied.active = false\n"
        "  set copied.label = \"mir\"\n"
        "  print(original.count, original.active, original.label)\n"
        "  print(copied.count, copied.active, copied.label)\n"
        "}\n",
        "m5-c17-mixed-struct.rove",
    )
    c17_mixed_struct_issues = collect_legalization_issues(
        c17_mixed_struct, "c", require_emitter=True
    )
    assert not c17_mixed_struct_issues, c17_mixed_struct_issues
    expected_c17_mixed_struct = "\n".join(MIRInterpreter(c17_mixed_struct).run().output) + "\n"
    assert expected_c17_mixed_struct == "4 true nyx\n9 false mir\n"
    generated_c17_mixed_struct = emit_legalized_c17(c17_mixed_struct)
    assert "bool active;" in generated_c17_mixed_struct
    assert "const char * label;" in generated_c17_mixed_struct
    assert _compile_and_run_c17(generated_c17_mixed_struct) == expected_c17_mixed_struct

    c17_nested_struct = _lower_source(
        "struct Point { x: int, y: int }\n"
        "struct Frame { point: Point, active: bool, label: string }\n"
        "fn main() {\n"
        "  var original = Frame(Point(1, 2), true, \"first\")\n"
        "  var copied = original\n"
        "  set copied.point.x = 9\n"
        "  var frames = [original]\n"
        "  var frames_copy = frames\n"
        "  set frames_copy[0].point.y = 8\n"
        "  print(original.point.x, copied.point.x, frames[0].point.y, frames_copy[0].point.y)\n"
        "}\n",
        "m5-c17-nested-struct.rove",
    )
    c17_nested_struct_issues = collect_legalization_issues(
        c17_nested_struct, "c", require_emitter=True
    )
    assert not c17_nested_struct_issues, c17_nested_struct_issues
    expected_c17_nested_struct = "\n".join(
        MIRInterpreter(c17_nested_struct).run().output
    ) + "\n"
    assert expected_c17_nested_struct == "1 9 2 8\n"
    generated_c17_nested_struct = emit_legalized_c17(c17_nested_struct)
    assert generated_c17_nested_struct.index("RoveStruct_Point {") < generated_c17_nested_struct.index(
        "RoveStruct_Frame {"
    )
    assert "RoveStruct_Point point;" in generated_c17_nested_struct
    assert _compile_and_run_c17(generated_c17_nested_struct) == expected_c17_nested_struct

    c17_array_field_struct = _lower_source(
        "struct Buffer { values: Array<int>, flags: Array<bool>, words: Array<string> }\n"
        "fn main() {\n"
        "  var original = Buffer([1, 2], [true], [\"nyx\"])\n"
        "  var copied = original\n"
        "  set copied.values[0] = 9\n"
        "  set copied.flags[0] = false\n"
        "  set copied.words[0] = \"mir\"\n"
        "  var buffers = [original]\n"
        "  var buffers_copy = buffers\n"
        "  set buffers_copy[0].values[1] = 8\n"
        "  print(original.values[0], copied.values[0], original.flags[0], copied.flags[0])\n"
        "  print(original.words[0], copied.words[0], buffers[0].values[1], buffers_copy[0].values[1])\n"
        "}\n",
        "m5-c17-array-field-struct.rove",
    )
    c17_array_field_issues = collect_legalization_issues(
        c17_array_field_struct, "c", require_emitter=True
    )
    assert not c17_array_field_issues, c17_array_field_issues
    expected_c17_array_field = "\n".join(
        MIRInterpreter(c17_array_field_struct).run().output
    ) + "\n"
    assert expected_c17_array_field == "1 9 true false\nnyx mir 2 8\n"
    generated_c17_array_field = emit_legalized_c17(c17_array_field_struct)
    assert "RoveArrayI64 values;" in generated_c17_array_field
    assert "result.values = rove_array_i64_clone(value.values);" in generated_c17_array_field
    assert "rove_struct_Buffer_clone(source[index])" in generated_c17_array_field
    assert _compile_and_run_c17(generated_c17_array_field) == expected_c17_array_field

    c17_struct_array_field = _lower_source(
        "struct Sample { value: int, valid: bool }\n"
        "struct BatchRecord { samples: Array<Sample>, name: string }\n"
        "fn main() {\n"
        "  var original = BatchRecord([Sample(2, true), Sample(3, false)], \"nyx\")\n"
        "  var copied = original\n"
        "  set copied.samples[0].value = 9\n"
        "  set copied.samples[1].valid = true\n"
        "  print(original.samples[0].value, copied.samples[0].value)\n"
        "  print(original.samples[1].valid, copied.samples[1].valid, copied.name)\n"
        "}\n",
        "m5-c17-struct-array-field.rove",
    )
    c17_struct_array_field_issues = collect_legalization_issues(
        c17_struct_array_field, "c", require_emitter=True
    )
    assert not c17_struct_array_field_issues, c17_struct_array_field_issues
    expected_c17_struct_array_field = "\n".join(
        MIRInterpreter(c17_struct_array_field).run().output
    ) + "\n"
    assert expected_c17_struct_array_field == "2 9\nfalse true nyx\n"
    generated_c17_struct_array_field = emit_legalized_c17(c17_struct_array_field)
    assert generated_c17_struct_array_field.index("RoveStruct_Sample {") < generated_c17_struct_array_field.index(
        "RoveStruct_BatchRecord {"
    )
    assert "RoveArrayStruct_Sample samples;" in generated_c17_struct_array_field
    assert "result.samples = rove_array_struct_Sample_clone(value.samples);" in generated_c17_struct_array_field
    assert _compile_and_run_c17(
        generated_c17_struct_array_field
    ) == expected_c17_struct_array_field

    c17_nested_array_field = _lower_source(
        "struct Matrix { rows: Array<Array<int>>, flags: Array<Array<bool>>, labels: Array<Array<string>> }\n"
        "fn main() {\n"
        "  var original = Matrix([[1, 2]], [[true]], [[\"nyx\"]])\n"
        "  var copied = original\n"
        "  set copied.rows[0][1] = 9\n"
        "  set copied.flags[0][0] = false\n"
        "  set copied.labels[0][0] = \"mir\"\n"
        "  print(original.rows[0][1], copied.rows[0][1])\n"
        "  print(original.flags[0][0], copied.flags[0][0])\n"
        "  print(original.labels[0][0], copied.labels[0][0])\n"
        "}\n",
        "m5-c17-nested-array-field.rove",
    )
    c17_nested_array_field_issues = collect_legalization_issues(
        c17_nested_array_field, "c", require_emitter=True
    )
    assert not c17_nested_array_field_issues, c17_nested_array_field_issues
    expected_c17_nested_array_field = "\n".join(
        MIRInterpreter(c17_nested_array_field).run().output
    ) + "\n"
    assert expected_c17_nested_array_field == "2 9\ntrue false\nnyx mir\n"
    generated_c17_nested_array_field = emit_legalized_c17(c17_nested_array_field)
    assert generated_c17_nested_array_field.index(
        "RoveArrayNested_nested_i64 {"
    ) < generated_c17_nested_array_field.index("RoveStruct_Matrix {")
    assert "result.rows = rove_array_nested_i64_clone(value.rows);" in generated_c17_nested_array_field
    assert _compile_and_run_c17(
        generated_c17_nested_array_field
    ) == expected_c17_nested_array_field

    c17_nested_struct_array_field = _lower_source(
        "struct Sample { value: int, valid: bool }\n"
        "struct SampleGrid { groups: Array<Array<Sample>>, name: string }\n"
        "fn main() {\n"
        "  var original = SampleGrid([[Sample(2, true), Sample(3, false)]], \"nyx\")\n"
        "  var copied = original\n"
        "  set copied.groups[0][0].value = 9\n"
        "  set copied.groups[0][1].valid = true\n"
        "  print(original.groups[0][0].value, copied.groups[0][0].value)\n"
        "  print(original.groups[0][1].valid, copied.groups[0][1].valid, copied.name)\n"
        "}\n",
        "m5-c17-nested-struct-array-field.rove",
    )
    c17_nested_struct_array_field_issues = collect_legalization_issues(
        c17_nested_struct_array_field, "c", require_emitter=True
    )
    assert not c17_nested_struct_array_field_issues, c17_nested_struct_array_field_issues
    expected_c17_nested_struct_array_field = "\n".join(
        MIRInterpreter(c17_nested_struct_array_field).run().output
    ) + "\n"
    assert expected_c17_nested_struct_array_field == "2 9\nfalse true nyx\n"
    generated_c17_nested_struct_array_field = emit_legalized_c17(
        c17_nested_struct_array_field
    )
    assert generated_c17_nested_struct_array_field.index(
        "RoveArrayNested_nested_struct_Sample {"
    ) < generated_c17_nested_struct_array_field.index("RoveStruct_SampleGrid {")
    assert "result.groups = rove_array_nested_struct_Sample_clone(value.groups);" in (
        generated_c17_nested_struct_array_field
    )
    assert _compile_and_run_c17(
        generated_c17_nested_struct_array_field
    ) == expected_c17_nested_struct_array_field

    c17_recursive_struct = MIRModule(
        "m5-c17-recursive-struct-rejected.rove",
        "c",
        (),
        (
            MIRStructDef(
                "Recursive",
                "type::Recursive",
                (MIRField("next", MIRType("Recursive")),),
            ),
        ),
    )
    recursive_struct_issues = collect_legalization_issues(c17_recursive_struct, "c")
    assert any(
        issue.code == "MIRG1002" and "acyclic by-value" in issue.message
        for issue in recursive_struct_issues
    ), recursive_struct_issues

    c17_array = _lower_source(
        "fn main() {\n"
        "  var original = [4, 5]\n"
        "  var copied = original\n"
        "  set copied[0] = 9\n"
        "  var index = 1\n"
        "  set copied[index] = 7\n"
        "  print(original[0] * 1000 + copied[0] * 100 + original[1] * 10 + copied[1])\n"
        "  print(len(original) * 10 + len(copied))\n"
        "}\n",
        "m5-c17-array.rove",
    )
    assert not collect_legalization_issues(c17_array, "c", require_emitter=True)
    expected_c17_array = "\n".join(MIRInterpreter(c17_array).run().output) + "\n"
    assert expected_c17_array == "4957\n22\n"
    generated_c17_array = emit_legalized_c17(c17_array)
    assert "typedef struct RoveArrayI64" in generated_c17_array
    assert "rove_array_i64_clone" in generated_c17_array
    assert "rove_array_i64_at_mut" in generated_c17_array
    assert _compile_and_run_c17(generated_c17_array) == expected_c17_array

    c17_bool_string_arrays = _lower_source(
        "fn main() {\n"
        "  var original_flags = [true, false]\n"
        "  var copied_flags = original_flags\n"
        "  set copied_flags[0] = false\n"
        "  set copied_flags[1] = true\n"
        "  print(original_flags[0], copied_flags[0], copied_flags[1], len(copied_flags))\n"
        "  var original_words = [\"nyx\", \"c17\"]\n"
        "  var copied_words = original_words\n"
        "  set copied_words[0] = \"mir\"\n"
        "  print(original_words[0], copied_words[0], copied_words[1], len(copied_words))\n"
        "}\n",
        "m5-c17-bool-string-arrays.rove",
    )
    assert not collect_legalization_issues(c17_bool_string_arrays, "c", require_emitter=True)
    expected_c17_bool_string = "\n".join(MIRInterpreter(c17_bool_string_arrays).run().output) + "\n"
    assert expected_c17_bool_string == "true false true 2\nnyx mir c17 2\n"
    generated_c17_bool_string = emit_legalized_c17(c17_bool_string_arrays)
    assert "typedef struct RoveArrayBool" in generated_c17_bool_string
    assert "typedef struct RoveArrayString" in generated_c17_bool_string
    assert _compile_and_run_c17(generated_c17_bool_string) == expected_c17_bool_string

    c17_struct_array = _lower_source(
        "struct Cell { x: int, y: int }\n"
        "fn main() {\n"
        "  var original = [Cell(1, 2), Cell(3, 4)]\n"
        "  var copied = original\n"
        "  set copied[0].x = 9\n"
        "  print(original[0].x * 1000 + copied[0].x * 100 + copied[1].y * 10 + len(copied))\n"
        "}\n",
        "m5-c17-struct-array.rove",
    )
    assert not collect_legalization_issues(c17_struct_array, "c", require_emitter=True)
    expected_c17_struct_array = "\n".join(MIRInterpreter(c17_struct_array).run().output) + "\n"
    assert expected_c17_struct_array == "1942\n"
    generated_c17_struct_array = emit_legalized_c17(c17_struct_array)
    assert "typedef struct RoveArrayStruct_Cell" in generated_c17_struct_array
    assert "rove_array_struct_Cell_clone" in generated_c17_struct_array
    assert _compile_and_run_c17(generated_c17_struct_array) == expected_c17_struct_array

    c17_nested_array = _lower_source(
        "fn main() {\n"
        "  var original = [[1, 2], [3, 4]]\n"
        "  var copied = original\n"
        "  set copied[0][1] = 9\n"
        "  print(original[0][1] * 1000 + copied[0][1] * 100 + copied[1][0] * 10 + len(copied))\n"
        "}\n",
        "m5-c17-nested-array.rove",
    )
    assert not collect_legalization_issues(c17_nested_array, "c", require_emitter=True)
    expected_c17_nested_array = "\n".join(MIRInterpreter(c17_nested_array).run().output) + "\n"
    assert expected_c17_nested_array == "2932\n"
    generated_c17_nested_array = emit_legalized_c17(c17_nested_array)
    assert "typedef struct RoveArrayNested_nested_i64" in generated_c17_nested_array
    assert "rove_array_nested_i64_clone" in generated_c17_nested_array
    assert _compile_and_run_c17(generated_c17_nested_array) == expected_c17_nested_array

    c17_recursive_arrays = _lower_source(
        "struct NestedCell { value: int }\n"
        "fn main() {\n"
        "  var flags = [[true, false]]\n"
        "  var flags_copy = flags\n"
        "  set flags_copy[0][0] = false\n"
        "  var words = [[\"nyx\"]]\n"
        "  var words_copy = words\n"
        "  set words_copy[0][0] = \"mir\"\n"
        "  var cells = [[NestedCell(3)]]\n"
        "  var cells_copy = cells\n"
        "  set cells_copy[0][0].value = 8\n"
        "  var cubes = [[[1, 2]]]\n"
        "  var cubes_copy = cubes\n"
        "  set cubes_copy[0][0][1] = 9\n"
        "  print(flags[0][0], flags_copy[0][0], words[0][0], words_copy[0][0])\n"
        "  print(cells[0][0].value, cells_copy[0][0].value, cubes[0][0][1], cubes_copy[0][0][1])\n"
        "}\n",
        "m5-c17-recursive-arrays.rove",
    )
    assert not collect_legalization_issues(c17_recursive_arrays, "c", require_emitter=True)
    expected_c17_recursive_arrays = "\n".join(
        MIRInterpreter(c17_recursive_arrays).run().output
    ) + "\n"
    assert expected_c17_recursive_arrays == "true false nyx mir\n3 8 2 9\n"
    generated_c17_recursive_arrays = emit_legalized_c17(c17_recursive_arrays)
    assert "RoveArrayNested_nested_bool" in generated_c17_recursive_arrays
    assert "RoveArrayNested_nested_string" in generated_c17_recursive_arrays
    assert "RoveArrayNested_nested_struct_NestedCell" in generated_c17_recursive_arrays
    assert "RoveArrayNested_nested_nested_i64" in generated_c17_recursive_arrays
    assert _compile_and_run_c17(generated_c17_recursive_arrays) == expected_c17_recursive_arrays

    c17_tagged = _lower_source(
        "enum Signal { Ready(int), Empty() }\n"
        "fn decode(value: int) -> int {\n"
        "  let signal = Ready(value)\n"
        "  match signal {\n"
        "    Ready(payload) => return payload + 1,\n"
        "    Empty() => return 0\n"
        "  }\n"
        "  return -1\n"
        "}\n"
        "fn make_result(code: int) -> Result<int, string> {\n"
        "  if code == 0 { return Ok(40) }\n"
        "  return Err(\"fail\")\n"
        "}\n"
        "fn result_probe(code: int) -> int {\n"
        "  match make_result(code) {\n"
        "    Ok(value) => return value + 2,\n"
        "    Err(message) => return len(message)\n"
        "  }\n"
        "  return -1\n"
        "}\n"
        "fn main() { print(decode(41), result_probe(0), result_probe(7)) }\n",
        "m5-c17-tagged.rove",
    )
    assert not collect_legalization_issues(c17_tagged, "c", require_emitter=True)
    expected_c17_tagged = "\n".join(MIRInterpreter(c17_tagged).run().output) + "\n"
    assert expected_c17_tagged == "42 42 4\n"
    generated_c17_tagged = emit_legalized_c17(c17_tagged)
    assert "typedef struct RoveTaggedValue" in generated_c17_tagged
    assert ".tag = \"Ready\"" in generated_c17_tagged
    assert ".tag = \"Ok\"" in generated_c17_tagged
    assert ".tag = \"Err\"" in generated_c17_tagged
    assert _compile_and_run_c17(generated_c17_tagged) == expected_c17_tagged

    c17_multi_payload = _lower_source(
        "enum Event { Data(int, bool, string), Empty() }\n"
        "fn inspect(event: Event) -> int {\n"
        "  match event {\n"
        "    Data(count, valid, label) => {\n"
        "      if valid { return count * 10 + len(label) }\n"
        "      return len(label)\n"
        "    },\n"
        "    Empty() => return 0\n"
        "  }\n"
        "  return -1\n"
        "}\n"
        "fn main() { print(inspect(Data(4, true, \"nyx\")), inspect(Data(9, false, \"mir\"))) }\n",
        "m5-c17-multi-payload.rove",
    )
    assert not collect_legalization_issues(c17_multi_payload, "c", require_emitter=True)
    expected_c17_multi_payload = "\n".join(
        MIRInterpreter(c17_multi_payload).run().output
    ) + "\n"
    assert expected_c17_multi_payload == "43 3\n"
    generated_c17_multi_payload = emit_legalized_c17(c17_multi_payload)
    assert "RoveTaggedPayload payload[3];" in generated_c17_multi_payload
    assert ".payload[1].boolean" in generated_c17_multi_payload
    assert ".payload[2].string" in generated_c17_multi_payload
    assert _compile_and_run_c17(
        generated_c17_multi_payload
    ) == expected_c17_multi_payload

    c17_multi_object_payload = _lower_source(
        "enum Unsupported { Pair(Array<int>, int) }\n"
        "fn main() { print(0) }\n",
        "m5-c17-multi-object-payload-rejected.rove",
    )
    c17_multi_object_issues = collect_legalization_issues(
        c17_multi_object_payload, "c", require_emitter=True
    )
    assert any(
        issue.code == "MIRG1002" and "multiple primitive payloads" in issue.message
        for issue in c17_multi_object_issues
    ), c17_multi_object_issues

    c17_array_tagged = _lower_source(
        "enum Batch { Data(Array<int>), Empty() }\n"
        "struct Envelope { values: Array<int> }\n"
        "enum EnvelopeBatch { Wrapped(Envelope), Missing() }\n"
        "fn enum_array_probe() -> int {\n"
        "  var source = [1, 2]\n"
        "  let batch = Data(source)\n"
        "  set source[0] = 9\n"
        "  match batch {\n"
        "    Data(values) => return values[0] * 10 + len(values),\n"
        "    Empty() => return 0\n"
        "  }\n"
        "  return -1\n"
        "}\n"
        "fn make_array_result() -> Result<Array<int>, string> {\n"
        "  return Ok([3, 4])\n"
        "}\n"
        "fn result_array_probe() -> int {\n"
        "  match make_array_result() {\n"
        "    Ok(values) => return values[0] * 10 + values[1],\n"
        "    Err(message) => return len(message)\n"
        "  }\n"
        "  return -1\n"
        "}\n"
        "fn struct_array_payload_probe() -> int {\n"
        "  var source = [5, 6]\n"
        "  let batch = Wrapped(Envelope(source))\n"
        "  set source[0] = 9\n"
        "  match batch {\n"
        "    Wrapped(envelope) => return envelope.values[0] * 10 + envelope.values[1],\n"
        "    Missing() => return 0\n"
        "  }\n"
        "  return -1\n"
        "}\n"
        "fn main() { print(enum_array_probe(), result_array_probe(), struct_array_payload_probe()) }\n",
        "m5-c17-array-tagged.rove",
    )
    c17_array_tagged_issues = collect_legalization_issues(
        c17_array_tagged, "c", require_emitter=True
    )
    assert not c17_array_tagged_issues, c17_array_tagged_issues
    expected_c17_array_tagged = "\n".join(
        MIRInterpreter(c17_array_tagged).run().output
    ) + "\n"
    assert expected_c17_array_tagged == "12 34 56\n"
    generated_c17_array_tagged = emit_legalized_c17(c17_array_tagged)
    assert "rove_box_array_i64" in generated_c17_array_tagged
    assert "rove_box_Envelope" in generated_c17_array_tagged
    assert ".tag = \"Data\"" in generated_c17_array_tagged
    assert _compile_and_run_c17(generated_c17_array_tagged) == expected_c17_array_tagged

    c17_struct_tagged = _lower_source(
        "struct PayloadCell { value: int }\n"
        "enum Packet { Data(PayloadCell), Empty() }\n"
        "fn packet_probe() -> int {\n"
        "  let packet = Data(PayloadCell(8))\n"
        "  match packet {\n"
        "    Data(cell) => return cell.value,\n"
        "    Empty() => return 0\n"
        "  }\n"
        "  return -1\n"
        "}\n"
        "fn make_cell(ok: bool) -> Result<PayloadCell, string> {\n"
        "  if ok { return Ok(PayloadCell(7)) }\n"
        "  return Err(\"bad\")\n"
        "}\n"
        "fn cell_probe(ok: bool) -> int {\n"
        "  match make_cell(ok) {\n"
        "    Ok(cell) => return cell.value,\n"
        "    Err(message) => return len(message)\n"
        "  }\n"
        "  return -1\n"
        "}\n"
        "fn main() { print(packet_probe(), cell_probe(true), cell_probe(false)) }\n",
        "m5-c17-struct-tagged.rove",
    )
    assert not collect_legalization_issues(c17_struct_tagged, "c", require_emitter=True)
    expected_c17_struct_tagged = "\n".join(MIRInterpreter(c17_struct_tagged).run().output) + "\n"
    assert expected_c17_struct_tagged == "8 7 3\n"
    generated_c17_struct_tagged = emit_legalized_c17(c17_struct_tagged)
    assert "rove_box_PayloadCell" in generated_c17_struct_tagged
    assert ".payload = { { .object =" in generated_c17_struct_tagged
    assert _compile_and_run_c17(generated_c17_struct_tagged) == expected_c17_struct_tagged

    ownership = _ownership_module()
    assert not collect_legalization_issues(ownership, "cpp", require_emitter=True)
    expected_ownership = "\n".join(MIRInterpreter(ownership).run().output) + "\n"
    assert expected_ownership == "42\n"
    generated_ownership = emit_legalized_cpp(ownership)
    assert "std::move" in generated_ownership
    assert "int64_t*" in generated_ownership
    assert _compile_and_run_cpp(generated_ownership) == expected_ownership
    assert not collect_legalization_issues(ownership, "rust", require_emitter=True)
    generated_rust_borrow = emit_legalized_rust(ownership)
    assert "RovePtr<int" not in generated_rust_borrow
    assert "RovePtr<i64>" in generated_rust_borrow
    assert "RovePtr::borrow(" in generated_rust_borrow
    assert ".read()" in generated_rust_borrow
    _assert_rust_runtime(generated_rust_borrow, expected_ownership)

    rust_ownership = _rust_value_ownership_module()
    assert not collect_legalization_issues(rust_ownership, "rust", require_emitter=True)
    expected_rust_ownership = "\n".join(MIRInterpreter(rust_ownership).run().output) + "\n"
    assert expected_rust_ownership == "owned owned\n"
    generated_rust_ownership = emit_legalized_rust(rust_ownership)
    assert "std::mem::replace" in generated_rust_ownership
    assert "drop(" in generated_rust_ownership
    _assert_rust_runtime(generated_rust_ownership, expected_rust_ownership)

    mutable_borrow = _rust_mutable_borrow_module()
    assert not collect_legalization_issues(mutable_borrow, "rust", require_emitter=True)
    expected_mutable_borrow = "\n".join(MIRInterpreter(mutable_borrow).run().output) + "\n"
    assert expected_mutable_borrow == "42\n"
    generated_mutable_borrow = emit_legalized_rust(mutable_borrow)
    assert "RovePtr::borrow_mut(" in generated_mutable_borrow
    assert ".write()" in generated_mutable_borrow
    _assert_rust_runtime(generated_mutable_borrow, expected_mutable_borrow)

    aggregate_codes = {issue.code for issue in collect_legalization_issues(aggregate, "llvm")}
    assert aggregate_codes == {"MIRG1002"}, aggregate_codes
    try:
        emit_legalized_llvm(aggregate)
        raise AssertionError("aggregate MIR bypassed the LLVM legalization gate")
    except MIRLegalizationError as error:
        assert {issue.code for issue in error.issues} == aggregate_codes
    wasm_rejected = {issue.code for issue in collect_legalization_issues(aggregate, "wasm")}
    assert "MIRG1002" in wasm_rejected and "MIRG1004" in wasm_rejected, wasm_rejected
    c_rejected = {issue.code for issue in collect_legalization_issues(aggregate, "c")}
    assert "MIRG1002" in c_rejected, c_rejected

    if RUST_VALIDATION_MODE != "runtime":
        print(f"[INFO] Rust generated sources validated in {RUST_VALIDATION_MODE} mode")
    rust_evidence = (
        "executable Rust"
        if RUST_VALIDATION_MODE == "runtime"
        else "Rust metadata/type-check"
    )
    print(
        "[PASS] 7 target profiles, stable negative diagnostics, no-fallback gate, "
        "scalar/aggregate/payload/ownership MIR interpreter parity, C++/LLVM pilots with nested LLVM value structs, recursively deep-copied Array<int|bool|float|string|acyclic-struct> including nested arrays and tagged struct-array ownership, primitive/string tagged Result+enum payloads with canonical display, boxed multi-array/struct tagged payload clone/drop parity plus direct/tagged primitive/nested-array display and consuming-builtin cleanup, explicit LLVM deinit/drop destruction, and LLVM emitter-contract negatives, "
        f"executable Wasm/JavaScript/Python/C17 CFG pilots, {rust_evidence} validation, C17 acyclic deep-cloned value structs/recursive Array<int|bool|float|f64|string|struct>/nested collection fields/tagged multi-primitive|array|struct and binary64 display/to_string parity, Rust/JS/Python "
        "aggregate parity, Wasm Array<int|bool|float|string|struct>+nested int|bool|float|string|struct arrays/nested int+bool+float+string-struct/int+bool+float+string+struct-enum/Result<int|float|struct,int|bool|float|string> parity, "
        "C++/Rust/JS/Python local and interprocedural throw/catch parity, C++/LLVM/Rust/JS/Python nested struct-enum/Result<Array<int>,string> parity, C++/Rust/JS/Python lazy memoized async/await with suspend-unwind parity, Rust/JS/Python payload-enum parity, "
        "all-target non-unwinding deinit/drop consumption and Rust value ownership/borrow/drop, "
        "and legacy C++ oracle"
    )
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_mir_legalization_suite() else 1)
