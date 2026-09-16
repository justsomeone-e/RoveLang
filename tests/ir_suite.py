import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from dataclasses import fields, is_dataclass, replace


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src import CompilerPlugin, NyxCompiler, compile_source
from src.codegen.cpp_toolchain import CppToolchain
from src.codegen.wasm_ir import BundleLowerer
from src.core import Lexer, Parser, TypeChecker
from src.core.backend_capabilities import BACKENDS
from src.ir import (
    INT,
    STRING,
    IRAssign,
    IRAwait,
    IRBinary,
    IRBreak,
    IRFunction,
    IRIf,
    IRIndexAccess,
    IRLiteral,
    IRMemberAccess,
    IRModule,
    IRParameter,
    IRReference,
    IRReturn,
    IRStruct,
    IRType,
    IRVarDecl,
    SourceSpan,
    array_of,
    collect_hir_issues,
    fingerprint,
    is_abi_compatible,
    is_assignable,
    is_coercible,
    is_exact_type,
    lower_to_hir,
    optimize_hir,
    to_json,
    verify_hir,
)


GOLDEN_FINGERPRINT = "bde68976f695bb510d36c0d805a98b91111e1b6df0a09b1e4225f6c6ded11705"


def _frontend(source: str, filename: str = "<ir-test>") -> IRModule:
    tree = Parser(Lexer(source).tokenize(), source).parse()
    TypeChecker(tree, filename, source).check()
    return lower_to_hir(tree, filename)


def _symbols(value) -> list[str]:
    result = []
    if is_dataclass(value):
        for field in fields(value):
            item = getattr(value, field.name)
            if field.name == "symbol" and isinstance(item, str):
                result.append(item)
            result.extend(_symbols(item))
    elif isinstance(value, (tuple, list)):
        for item in value:
            result.extend(_symbols(item))
    return result


def _program_corpus_files():
    files = []
    for relative in ("tests/battery138", "tests/bughunt"):
        files.extend(sorted(Path(ROOT_DIR, relative).glob("*.nyx")))
    return files


def _run_corpus() -> int:
    files = _program_corpus_files()
    assert len(files) >= 162
    for path in files:
        source = path.read_text(encoding="utf-8-sig")
        hir = _frontend(source, str(path))
        verify_hir(hir)
        first = optimize_hir(hir)
        second = optimize_hir(first.module)
        assert fingerprint(first.module) == fingerprint(second.module), path
    return len(files)


def _run_canonical_and_scope_checks() -> None:
    source = "fn add(a: int, b: int) -> int { var c = a + b; return c }\n"
    first = _frontend(source, "<ir-golden>")
    second = _frontend(source, "<ir-golden>")
    verify_hir(first)
    assert to_json(first) == to_json(second)
    assert fingerprint(first) == fingerprint(second) == GOLDEN_FINGERPRINT
    assert " " not in to_json(first)

    shadowed = _frontend(
        "fn pick(x: int) -> int {\n"
        "  if true { var x = 2; return x }\n"
        "  else { return x }\n"
        "}\n",
        "<ir-shadowing>",
    )
    verify_hir(shadowed)
    local_symbols = [symbol for symbol in _symbols(shadowed) if "::local::" in symbol]
    assert len(set(local_symbols)) == 1
    parameter_symbols = [symbol for symbol in _symbols(shadowed) if "::param::" in symbol]
    assert parameter_symbols and set(local_symbols).isdisjoint(parameter_symbols)


def _run_type_relation_checks() -> None:
    nested_int = array_of(array_of(INT))
    nested_string = array_of(array_of(STRING))
    assert is_exact_type(nested_int, array_of(array_of(INT)))
    assert not is_exact_type(nested_int, nested_string)
    assert is_assignable(INT.with_optional(), INT)
    assert not is_assignable(IRType("i32"), INT)
    assert is_coercible(IRType("i32"), INT)
    assert is_coercible(INT, IRType("float"))
    assert not is_coercible(IRType("int", pointer=True), IRType("string", pointer=True))
    assert is_abi_compatible(IRType("i64"), IRType("u64"), "cpp")
    assert is_abi_compatible(IRType("uintptr"), IRType("u32"), "wasm")
    assert is_abi_compatible(IRType("uintptr"), IRType("u64"), "c")
    assert not is_abi_compatible(STRING, IRType("int", pointer=True), "cpp")


def _run_nyx_authored_hir_parity() -> int:
    compiler_dir = Path(ROOT_DIR, "compiler")

    def component(name: str) -> str:
        source = (compiler_dir / name).read_text(encoding="utf-8")
        return "\n".join(
            line for line in source.splitlines()
            if not line.lstrip().startswith("#target")
            and not line.lstrip().startswith("#native")
        )

    lexer = component("lexer.nyx")
    lexer = lexer[lexer.index("// NYX_LEXER_SUPPORT_BEGIN:"):]
    if "fn main()" in lexer:
        lexer = lexer[:lexer.index("fn main()")]

    corpus = [
        (
            "function_and_locals",
            "fn add(a: int, b: int) -> int { var c = a + b; return c }\n",
        ),
        (
            "expression_body_and_conditional",
            'fn classify(x: int) -> string = if x < 0 { "negative" } elif x == 0 { "zero" } else { "positive" }\n',
        ),
        (
            "value_match_expression",
            'fn status(code: int) -> string = match code { 200 => "ok", 404 => "missing", _ => "other" }\n',
        ),
        (
            "unicode_nul_and_numbers",
            'fn values() -> string { var a: int = 0x2a; var f: float = 001.2500; var s: string = "e\\u0301\\0"; return s }\n',
        ),
        (
            "literal_unicode_columns",
            'fn text() -> string { var s = "ş😀e\\u0301\\0"; return s }\n',
        ),
        (
            "if_elif_else",
            "fn classify(x: int) -> int { if x > 0 { return 1 } elif x == 0 { return 0 } else { return -1 } }\n",
        ),
        (
            "range_and_while",
            "fn sum() -> int { var total: int = 0; for i in 0..3 { set total = total + i } while false { break } return total }\n",
        ),
        (
            "collection_for",
            "fn sum_items(items: Array<int>) -> int { var total: int = 0; for item in items { set total = total + item } return total }\n",
        ),
        (
            "struct_constructor_and_index",
            "struct Point { x: int, y: int } fn first() -> int { var points: Array<Point> = [Point(1, 2)]; return points[0].x }\n",
        ),
        (
            "type_alias_and_enum",
            "type UserID = int; enum Color { Red, Green = 5, Blue } const default_id: int = 7\n",
        ),
        (
            "payload_enum",
            'enum Outcome<T, E> { Success(T), Failure(E) }\nfn run() { var result = Success(42); match result { Success(value) => print(value), Failure(error) => print(error) } }\n',
        ),
        (
            "result_propagation",
            'fn read() -> Result<int, string> { return Ok(1) }\nfn run() -> Result<int, string> { var value = read()?; return Ok(value) }\n',
        ),
        (
            "pipeline",
            "fn increment(value: int) -> int { return value + 1 } fn run() -> int { return 41 |> increment }\n",
        ),
        (
            "lambda_and_call",
            "fn apply() -> int { var twice = x => x * 2; return twice(21) }\n",
        ),
        (
            "default_arguments",
            'fn greet(name: string = "world") -> string { return name }\nfn run() -> string { return greet() }\n',
        ),
        (
            "array_destructuring",
            "fn run() -> int { let [left, right] = [20, 22]; return left + right }\n",
        ),
        (
            "struct_destructuring",
            "struct Point { x: int, y: int } fn run() -> int { let Point(x, y) = Point(3, 4); return x + y }\n",
        ),
        (
            "destructuring_temp_collision_before",
            "let nyx_internal_destructure_2 = 5; let [left, right] = [20, 22]; fn run() -> int { return nyx_internal_destructure_2 + left + right }\n",
        ),
        (
            "destructuring_temp_collision_after",
            "let [left, right] = [20, 22]; let nyx_internal_destructure_1 = 5; fn run() -> int { return nyx_internal_destructure_1 + left + right }\n",
        ),
        (
            "destructuring_temp_collision_nested",
            "fn run() -> int { let nyx$internal$destructure$2 = 5; let [left, right] = [20, 22]; return nyx$internal$destructure$2 + left + right }\n",
        ),
        (
            "collection_combinators",
            "fn run() -> int { var items = [1, 2, 3, 4]; var doubled = map(items, item => item * 2); var selected = filter(doubled, item => item > 4); return fold(selected, 0, (total, item) => total + item) }\n",
        ),
        (
            "safe_member_and_coalesce",
            'struct User { name: string } fn display(user: User?) -> string { return user?.name ?? "anonymous" }\n',
        ),
        (
            "match_cases",
            'fn label(value: int) -> string { match value { 1 => { return "one" } 2 => { return "two" } } return "unknown" }\n',
        ),
        (
            "try_catch",
            'fn attempt() { try { print("work") } catch err { print(err) } }\n',
        ),
        (
            "throw_and_catch",
            'fn fail() -> int { throw 42 } fn attempt() { try { print(fail()) } catch err { print(err) } }\n',
        ),
        (
            "defer_and_guard",
            'fn cleanup() { print("clean") } fn guarded(ok: bool) { defer cleanup(); guard ok else { return } }\n',
        ),
        (
            "unsafe_spawn_test_assert",
            'fn tasks() { unsafe { var pointer = addr(0) } spawn { print("task") } } test "truth" { assert(true, "must hold") }\n',
        ),
        (
            "native_and_extern",
            '#native include <cstdio>\n#native link "user32.lib"\nextern "C" fn puts(value: string) -> int;\n',
        ),
        (
            "foreign_import",
            'import cpp "std::filesystem" from "<filesystem>" as fs\nfn current() { print(fs.current_path().string()) }\n',
        ),
        (
            "bitwise_precedence",
            "fn bits(a: int, b: int) -> int { return ((a << 2) | (b >> 1)) ^ (~a & b) }\n",
        ),
        (
            "generic_doc_async",
            "/// identity docs\nasync fn identity<T>(value: T) -> T { return value }\n/// box docs\nstruct Box<T> { value: T }\n",
        ),
        (
            "async_await_task",
            "async fn compute() -> int { return 42 } async fn run() -> int { let task: Task<int> = compute(); return await task }\n",
        ),
        (
            "trait_impl",
            'trait Show { fn show(self) -> string { return "" } } struct Item { name: string } impl Show for Item { fn show(self) -> string { return self.name } }\n',
        ),
        (
            "string_and_iterator_indexing",
            'fn first_char(text: string) -> string { return text[0] }\n',
        ),
    ]
    for path in _program_corpus_files():
        relative_name = path.relative_to(ROOT_DIR).as_posix()
        corpus.append(
            (
                f"corpus/{relative_name}",
                path.read_text(encoding="utf-8-sig"),
            )
        )

    driver_sections = ["fn main() {"]
    expected = {}
    for index, (name, program) in enumerate(corpus):
        source_name = f"<ir-parity:{name}>"
        expected[name] = to_json(_frontend(program, source_name))
        driver_sections.extend(
            (
                f"    print({json.dumps(f'@@HIR_CASE@@{index}:{name}')})",
                f"    var source_{index} = {json.dumps(program, ensure_ascii=False)}",
                f"    var lexer_{index} = Lexer(lexer_characters(source_{index}), 0, 1, 1)",
                f"    var tokens_{index} = lexer_{index}.tokenize()",
                f"    var parser_{index} = Parser(tokens_{index}, 0, false, \"\", \"\")",
                f"    var ast_{index} = parser_{index}.parse_program()",
                f"    if parser_{index}.has_error {{",
                f"        print(\"@@HIR_ERROR@@parse:\" + parser_{index}.error_msg)",
                "    } else {",
                f"        var lowerer_{index} = HIRLowerer({json.dumps(source_name)}, \"cpp\", [], [], [], [], 0, \"module\", false, \"\")",
                f"        var hir_{index} = lowerer_{index}.lower_program(ast_{index})",
                f"        if lowerer_{index}.has_error {{ print(\"@@HIR_ERROR@@lower:\" + lowerer_{index}.error_msg) }}",
                f"        else {{ print(hir_{index}.to_json()) }}",
                "    }",
            )
        )
    driver_sections.extend(("}", "main()"))
    driver = "\n" + "\n".join(driver_sections) + "\n"
    source = (
        "#target cpp\n"
        "#native include <string>\n"
        "#native include <vector>\n"
        + "\n\n".join((
            component("parser.nyx"),
            lexer,
            component("hir.nyx"),
            component("hir_lowering.nyx"),
        ))
        + driver
    )
    result = NyxCompiler(ROOT_DIR).compile_source(
        source,
        target="cpp",
        filename="<nyx-authored-hir-parity>",
    )
    assert result.success, result.diagnostics
    assert result.artifact is not None

    with tempfile.TemporaryDirectory(prefix="nyx_authored_hir_parity_") as temp_dir:
        cpp_path = os.path.join(temp_dir, "hir_parity.cpp")
        executable_path = os.path.join(temp_dir, "hir_parity.exe")
        with open(cpp_path, "w", encoding="utf-8") as handle:
            handle.write(result.artifact.content)
        compiled, message = CppToolchain.compile_cpp(cpp_path, executable_path)
        assert compiled, message
        return_code, output = CppToolchain.run_executable(executable_path)
        assert return_code == 0, output
        native = {}
        current_name = None
        for line in output.splitlines():
            if line.startswith("@@HIR_CASE@@"):
                _index, _separator, current_name = line[len("@@HIR_CASE@@"):].partition(":")
                continue
            if current_name is not None:
                native[current_name] = line
                current_name = None

        for name, _program in corpus:
            actual = native.get(name, "<missing>")
            assert not actual.startswith("@@HIR_ERROR@@"), f"{name}: {actual}"
            assert actual == expected[name], (
                f"Nyx/Python HIR mismatch for {name}:\n"
                f"Python: {expected[name]}\n"
                f"Nyx:    {actual}"
            )
    return len(corpus)


def _run_negative_verifier_checks() -> None:
    span = SourceSpan("<invalid-hir>", 1, 1)

    unresolved = IRModule(
        "<invalid-hir>",
        "cpp",
        (IRAssign(span, IRReference(span, INT, "x", "missing::x"), IRLiteral(span, INT, 1)),),
    )
    assert "HIR0005" in {issue.code for issue in collect_hir_issues(unresolved)}

    duplicate = IRModule(
        "<invalid-hir>",
        "cpp",
        (
            IRVarDecl(span, "a", "local::same", INT, IRLiteral(span, INT, 1)),
            IRVarDecl(span, "b", "local::same", INT, IRLiteral(span, INT, 2)),
        ),
    )
    assert "HIR0004" in {issue.code for issue in collect_hir_issues(duplicate)}

    mismatch = IRModule(
        "<invalid-hir>",
        "cpp",
        (IRVarDecl(span, "count", "local::count", INT, IRLiteral(span, STRING, "wrong")),),
    )
    assert "HIR0006" in {issue.code for issue in collect_hir_issues(mismatch)}

    oversized_integer = IRModule(
        "<invalid-hir>",
        "cpp",
        (IRVarDecl(span, "huge", "local::huge", INT, IRLiteral(span, INT, 1 << 63)),),
    )
    assert any(
        issue.code == "HIR0009" and "signed 64-bit" in issue.message
        for issue in collect_hir_issues(oversized_integer)
    )

    bad_control_flow = IRModule("<invalid-hir>", "cpp", (IRBreak(span),))
    assert "HIR0007" in {issue.code for issue in collect_hir_issues(bad_control_flow)}

    integer_condition = IRModule(
        "<invalid-hir>",
        "cpp",
        (IRIf(span, IRLiteral(span, INT, 1), (), (), None),),
    )
    assert any(
        issue.code == "HIR0006" and "condition must be bool" in issue.message
        for issue in collect_hir_issues(integer_condition)
    )

    missing_return = IRModule(
        "<invalid-hir>",
        "cpp",
        (IRFunction(span, "answer", "function::answer", (), INT, ()),),
    )
    issues = collect_hir_issues(missing_return)
    assert any(issue.code == "HIR0007" and "fall through" in issue.message for issue in issues)

    invalid_await = IRModule(
        "<invalid-hir>",
        "cpp",
        (
            IRFunction(
                span,
                "bad_await",
                "function::bad_await",
                (),
                INT,
                (IRReturn(span, IRAwait(span, INT, IRLiteral(span, INT, 1))),),
            ),
        ),
    )
    await_issues = collect_hir_issues(invalid_await)
    assert any(issue.code == "HIR0007" and "outside an async" in issue.message for issue in await_issues)
    assert any(issue.code == "HIR0006" and "Task<T>" in issue.message for issue in await_issues)

    mismatched_index = IRModule(
        "<invalid-hir>",
        "cpp",
        (
            IRVarDecl(
                span,
                "bad_elem",
                "local::bad_elem",
                STRING,
                IRIndexAccess(
                    span,
                    STRING,
                    IRLiteral(span, array_of(INT), (1, 2)),
                    IRLiteral(span, INT, 0),
                ),
            ),
        ),
    )
    assert any(
        issue.code == "HIR0006" and "Array index result" in issue.message
        for issue in collect_hir_issues(mismatched_index)
    )

    mismatched_string_index = IRModule(
        "<invalid-hir>",
        "cpp",
        (
            IRVarDecl(
                span,
                "bad_char",
                "local::bad_char",
                INT,
                IRIndexAccess(
                    span,
                    INT,
                    IRLiteral(span, STRING, "hello"),
                    IRLiteral(span, INT, 0),
                ),
            ),
        ),
    )
    assert any(
        issue.code == "HIR0006" and "String index result" in issue.message
        for issue in collect_hir_issues(mismatched_string_index)
    )

    primitive_member = IRModule(
        "<invalid-hir>",
        "cpp",
        (
            IRVarDecl(
                span,
                "val",
                "local::val",
                INT,
                IRMemberAccess(
                    span,
                    INT,
                    IRLiteral(span, INT, 42),
                    "length",
                ),
            ),
        ),
    )
    assert any(
        issue.code == "HIR0006" and "cannot have members" in issue.message
        for issue in collect_hir_issues(primitive_member)
    )

    point_struct = IRStruct(
        span,
        "Point",
        "type::struct::Point",
        (
            IRParameter("x", "type::struct::Point::field::x", INT),
            IRParameter("y", "type::struct::Point::field::y", INT),
        ),
    )
    missing_member = IRModule(
        "<invalid-hir>",
        "cpp",
        (
            point_struct,
            IRVarDecl(span, "p", "local::p", IRType("Point"), IRLiteral(span, IRType("Point"), None)),
            IRVarDecl(
                span,
                "val",
                "local::val",
                INT,
                IRMemberAccess(
                    span,
                    INT,
                    IRReference(span, IRType("Point"), "p", "local::p"),
                    "z",
                ),
            ),
        ),
    )
    assert any(
        issue.code == "HIR0006" and "has no member 'z'" in issue.message
        for issue in collect_hir_issues(missing_member)
    )

    mismatched_member_type = IRModule(
        "<invalid-hir>",
        "cpp",
        (
            point_struct,
            IRVarDecl(span, "p", "local::p", IRType("Point"), IRLiteral(span, IRType("Point"), None)),
            IRVarDecl(
                span,
                "val",
                "local::val",
                STRING,
                IRMemberAccess(
                    span,
                    STRING,
                    IRReference(span, IRType("Point"), "p", "local::p"),
                    "x",
                ),
            ),
        ),
    )
    assert any(
        issue.code == "HIR0006" and "Member 'x'" in issue.message
        for issue in collect_hir_issues(mismatched_member_type)
    )


def _run_optimizer_checks() -> None:
    source = (
        "fn calc(flag: int) -> int {\n"
        "  var value = (20 + 22) * 2\n"
        "  if flag > 0 { return value } else { return value - 1 }\n"
        "  var unreachable = 999\n"
        "}\n"
        "var fallback = null ?? \"nyx\"\n"
        "while false { print(\"never\") }\n"
    )
    raw = _frontend(source, "<optimizer>")
    verify_hir(raw)
    optimized = optimize_hir(raw)
    verify_hir(optimized.module)
    assert [record.name for record in optimized.records] == ["constant-fold", "dead-code-elimination"]
    assert all(record.changed for record in optimized.records)
    calc = optimized.module.functions[0]
    assert len(calc.body) == 2
    assert isinstance(calc.body[0], IRVarDecl)
    assert isinstance(calc.body[0].expr, IRLiteral) and calc.body[0].expr.value == 84
    assert isinstance(optimized.module.items[1], IRVarDecl)
    assert isinstance(optimized.module.items[1].expr, IRLiteral)
    assert optimized.module.items[1].expr.value == "nyx"
    assert len(optimized.module.items) == 2
    assert fingerprint(optimized.module) == fingerprint(optimize_hir(optimized.module).module)

    deterministic_numbers = _frontend(
        "fn keep(n: int) -> string {\n"
        "  var quotient = 8 / 2\n"
        "  var bits = 1 << 3\n"
        "  var wrapped = 9223372036854775807 + 1\n"
        "  var min_quotient = -9223372036854775808 / -1\n"
        "  return \"n=\" + n\n"
        "}\n",
        "<deterministic-numeric-folding>",
    )
    numeric_result = optimize_hir(deterministic_numbers).module.functions[0]
    assert isinstance(numeric_result.body[0].expr, IRLiteral)
    assert numeric_result.body[0].expr.value == 4
    assert isinstance(numeric_result.body[1].expr, IRLiteral)
    assert numeric_result.body[1].expr.value == 8
    assert isinstance(numeric_result.body[2].expr, IRLiteral)
    assert numeric_result.body[2].expr.value == -(1 << 63)
    assert isinstance(numeric_result.body[3].expr, IRLiteral)
    assert numeric_result.body[3].expr.value == -(1 << 63)
    assert isinstance(numeric_result.body[4].expr, IRBinary)


def _run_wasm_equivalence() -> None:
    node = shutil.which("node")
    assert node, "Node.js is required for HIR/WASM semantic equivalence"
    source = (
        "fn calc(x: int) -> int {\n"
        "  var base = (20 + 22) * 2\n"
        "  if x >= 0 { return base + x } else { return base - x }\n"
        "  var unreachable = 999\n"
        "}\n"
    )
    raw = _frontend(source, "<wasm-equivalence>")
    optimized = optimize_hir(raw).module
    raw_module = BundleLowerer(raw, "raw").lower()
    optimized_module = BundleLowerer(optimized, "optimized").lower()
    optimized_calc = next(function for function in optimized_module.functions if function.name == "calc")
    assert any(instruction.op == "i32.const" and instruction.arg == 84 for instruction in optimized_calc.body)

    with tempfile.TemporaryDirectory(prefix="nyx_hir_equivalence_") as temp_dir:
        raw_path = os.path.join(temp_dir, "raw.wasm")
        optimized_path = os.path.join(temp_dir, "optimized.wasm")
        with open(raw_path, "wb") as handle:
            handle.write(raw_module.to_wasm())
        with open(optimized_path, "wb") as handle:
            handle.write(optimized_module.to_wasm())
        script = (
            "const fs = require('node:fs');"
            "const load = async p => (await WebAssembly.instantiate(fs.readFileSync(p))).instance.exports;"
            "(async()=>{const a=await load(process.argv[1]);const b=await load(process.argv[2]);"
            "const xs=[-7,0,9];const av=xs.map(x=>a.calc(x));const bv=xs.map(x=>b.calc(x));"
            "if(JSON.stringify(av)!==JSON.stringify(bv))throw new Error('semantic mismatch');"
            "console.log(JSON.stringify(av));})().catch(e=>{console.error(e);process.exit(1)});"
        )
        runtime = subprocess.run(
            [node, "-e", script, raw_path, optimized_path],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert runtime.returncode == 0, runtime.stderr or runtime.stdout
        assert json.loads(runtime.stdout.strip()) == [91, 84, 93]


def _run_plugin_hir_contract() -> None:
    class RewriteAnswer(CompilerPlugin):
        name = "rewrite-answer"

        def __init__(self):
            self.events = []

        def after_lower(self, context, hir):
            self.events.append(("lower", fingerprint(hir)))

        def transform_hir(self, context, hir):
            self.events.append(("transform", fingerprint(hir)))
            function = hir.functions[0]
            statement = function.body[0]
            assert isinstance(statement, IRReturn) and isinstance(statement.expr, IRLiteral)
            left = IRLiteral(statement.expr.span, INT, 20)
            right = IRLiteral(statement.expr.span, INT, 22)
            expression = IRBinary(statement.expr.span, INT, left, "+", right)
            rewritten = replace(function, body=(replace(statement, expr=expression),))
            return replace(hir, items=(rewritten,))

        def after_optimize(self, context, hir):
            self.events.append(("optimize", fingerprint(hir)))
            expression = hir.functions[0].body[0].expr
            assert isinstance(expression, IRLiteral) and expression.value == 42

    plugin = RewriteAnswer()
    result = compile_source(
        "fn answer() -> int { return 41 }\n",
        target="wasm",
        filename="answer.nyx",
        plugins=(plugin,),
    )
    assert result.success, result.diagnostics
    assert result.hir is not None and result.artifact is not None
    assert [event[0] for event in plugin.events] == ["lower", "transform", "optimize"]
    assert "i32.const 42" in result.artifact.content
    metadata = result.to_dict(include_content=False)
    assert metadata["hir"]["fingerprint"] == fingerprint(result.hir)
    assert [item["name"] for item in metadata["passes"]] == [
        "constant-fold",
        "dead-code-elimination",
    ]

    python_plugin = RewriteAnswer()
    python_result = compile_source(
        "fn answer() -> int { return 41 }\n",
        target="python",
        filename="answer.nyx",
        plugins=(python_plugin,),
    )
    assert python_result.success, python_result.diagnostics
    assert python_result.artifact is not None
    namespace = {"__name__": "nyx_hir_plugin_test"}
    exec(compile(python_result.artifact.content, "<python-plugin>", "exec"), namespace)
    assert namespace["answer"]() == 42
    assert [event[0] for event in python_plugin.events] == ["lower", "transform", "optimize"]

    javascript_plugin = RewriteAnswer()
    javascript_result = compile_source(
        "fn answer() -> int { return 41 }\n",
        target="js",
        filename="answer.nyx",
        plugins=(javascript_plugin,),
    )
    assert javascript_result.success, javascript_result.diagnostics
    assert javascript_result.artifact is not None
    assert "return 42n;" in javascript_result.artifact.content
    assert [event[0] for event in javascript_plugin.events] == ["lower", "transform", "optimize"]

    cpp_plugin = RewriteAnswer()
    cpp_result = compile_source(
        "fn answer() -> int { return 41 }\n",
        target="cpp",
        filename="answer.nyx",
        plugins=(cpp_plugin,),
    )
    assert cpp_result.success, cpp_result.diagnostics
    assert cpp_result.artifact is not None
    assert "return static_cast<int64_t>(42);" in cpp_result.artifact.content
    assert [event[0] for event in cpp_plugin.events] == ["lower", "transform", "optimize"]

    class InvalidTransform(CompilerPlugin):
        name = "invalid-transform"

        def transform_hir(self, context, hir):
            return None

    invalid = compile_source(
        "fn answer() -> int { return 41 }\n",
        target="wasm",
        plugins=(InvalidTransform(),),
    )
    assert not invalid.success and invalid.diagnostics[0].code == "E9001"
    assert "must return IRModule" in invalid.diagnostics[0].note


def _run_stdlib_hir_contract() -> int:
    compiler = NyxCompiler(ROOT_DIR)
    modules = BACKENDS["cpp"].to_dict()["stdlib_modules"]
    for module_name in modules:
        result = compiler.check_source(
            f'import "std/{module_name}"\n',
            filename=f"<stdlib:{module_name}>",
            target="cpp",
        )
        assert result.success, (module_name, result.diagnostics)
        assert result.hir is not None

    unknown = compiler.check_source(
        "fn invalid_intrinsic() -> int { return _nyx_missing_intrinsic() }\n",
        filename="<unknown-intrinsic>",
        target="cpp",
    )
    assert not unknown.success and unknown.diagnostics[0].code == "HIRL0001"
    return len(modules)


def run_ir_suite() -> bool:
    print("=" * 70)
    print("NYX TYPED HIR / VERIFIED PASS PIPELINE")
    print("=" * 70)
    corpus_count = _run_corpus()
    _run_canonical_and_scope_checks()
    _run_type_relation_checks()
    hir_parity_count = _run_nyx_authored_hir_parity()
    _run_negative_verifier_checks()
    _run_optimizer_checks()
    _run_wasm_equivalence()
    _run_plugin_hir_contract()
    stdlib_count = _run_stdlib_hir_contract()
    print(
        f"[PASS] {corpus_count} programs, {stdlib_count} stdlib modules, canonical snapshot, "
        f"{hir_parity_count}-case Nyx/Python HIR byte parity, exact/assignable/coercible/ABI type relations, negative verifier, "
        "idempotent passes, WASM equivalence, "
        "and plugin HIR contract"
    )
    return True


if __name__ == "__main__":
    sys.exit(0 if run_ir_suite() else 1)
