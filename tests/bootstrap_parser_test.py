import os
import sys
import tempfile
import shutil

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from src.core.lexer import Lexer as PyLexer
from src.core.parser import Parser as PyParser
from src.core.ast_nodes import (
    ProgramNode, VarDeclNode, DestructureDeclNode, AssignNode, NumberNode, StringNode, BooleanNode,
    NullNode, IdentifierNode, BinaryOpNode, UnaryOpNode, AwaitNode, ResultPropagateNode, FunctionCallNode,
    FunctionDefNode, StructDefNode, ImplBlockNode, TraitDefNode, IfNode, WhileNode,
    ForNode, MatchNode, MatchExprNode, UnsafeBlockNode, SpawnNode, ReturnNode, ThrowNode, BreakNode, ContinueNode,
    NativeIncludeNode, NativeLinkNode, NativeUseNode, NativeRawNode, ExternFnDeclNode,
    MemberAccessNode, IndexAccessNode, NullCoalesceNode, ConditionalExprNode, LambdaNode, ArrayNode,
    TypeAliasNode, EnumDefNode, TestBlockNode, AssertNode, TryCatchNode,
    DeferNode, GuardNode, ImportNode
)
from src.codegen.codegen import UniversalCodeGen
from src.codegen.cpp_toolchain import CppToolchain

def py_ast_to_canonical(node) -> str:
    if isinstance(node, ProgramNode):
        stmts = " ".join(py_ast_to_canonical(s) for s in node.statements)
        return f"(Program name='main' body=[{stmts}])"
    if isinstance(node, VarDeclNode):
        t = str(node.type_annot) if node.type_annot else ""
        const_s = " const=true" if node.is_const else ""
        type_s = f" type='{t}'" if t else ""
        return f"(VarDecl name='{node.name}'{type_s}{const_s} body=[{py_ast_to_canonical(node.expr)}])"
    if isinstance(node, DestructureDeclNode):
        name_s = f" name='{node.struct_name}'" if node.struct_name else ""
        const_s = " const=true" if node.is_const else ""
        bindings = " ".join(f"(Identifier name='{name}')" for name in node.names)
        return (
            f"(DestructureDecl{name_s} val='{node.pattern_kind}'{const_s} "
            f"body=[{bindings} {py_ast_to_canonical(node.expr)}])"
        )
    if isinstance(node, AssignNode):
        return f"(Assign op='=' body=[{py_ast_to_canonical(node.target)} {py_ast_to_canonical(node.expr)}])"
    if isinstance(node, NumberNode):
        return f"(Number val='{node.value}' type='int')"
    if isinstance(node, StringNode):
        return f"(String val='{node.value}' type='string')"
    if isinstance(node, BooleanNode):
        return f"(Boolean val='{str(node.value).lower()}' type='bool')"
    if isinstance(node, NullNode):
        return f"(Null val='null' type='null')"
    if isinstance(node, IdentifierNode):
        return f"(Identifier name='{node.name}')"
    if isinstance(node, BinaryOpNode):
        return f"(BinaryOp op='{node.op}' body=[{py_ast_to_canonical(node.left)} {py_ast_to_canonical(node.right)}])"
    if isinstance(node, UnaryOpNode):
        return f"(UnaryOp op='{node.op}' body=[{py_ast_to_canonical(node.expr)}])"
    if isinstance(node, AwaitNode):
        return f"(Await body=[{py_ast_to_canonical(node.expr)}])"
    if isinstance(node, ResultPropagateNode):
        return f"(ResultPropagate body=[{py_ast_to_canonical(node.expr)}])"
    if isinstance(node, NullCoalesceNode):
        return f"(NullCoalesce op='??' body=[{py_ast_to_canonical(node.left)} {py_ast_to_canonical(node.right)}])"
    if isinstance(node, ConditionalExprNode):
        branches = "".join(
            f" (ConditionalBranch body=[{py_ast_to_canonical(condition)} {py_ast_to_canonical(value)}])"
            for condition, value in node.elif_branches
        )
        return (
            f"(ConditionalExpr body=[{py_ast_to_canonical(node.condition)} "
            f"{py_ast_to_canonical(node.then_expr)}{branches} "
            f"{py_ast_to_canonical(node.else_expr)}])"
        )
    if isinstance(node, MatchExprNode):
        cases = "".join(
            f" (MatchExprCase body=[{py_ast_to_canonical(pattern)} {py_ast_to_canonical(value)}])"
            for pattern, value in node.cases
        )
        return f"(MatchExpr body=[{py_ast_to_canonical(node.expr)}{cases}])"
    if isinstance(node, LambdaNode):
        params_s = ", ".join(f"{name}: " for name in node.params)
        params_attr = f" params=[{params_s}]" if params_s else ""
        return f"(Lambda{params_attr} body=[{py_ast_to_canonical(node.body)}])"
    if isinstance(node, ArrayNode):
        elements = " ".join(py_ast_to_canonical(element) for element in node.elements)
        return f"(Array body=[{elements}])"
    if isinstance(node, FunctionCallNode):
        if isinstance(node.callee, MemberAccessNode):
            callee_s = py_ast_to_canonical(node.callee.obj)
            return f"(MemberAccess name='{node.callee.member}' body=[{callee_s} (MethodCall name='{node.callee.member}')])"
        args = " ".join(py_ast_to_canonical(a) for a in node.args)
        body_s = f" body=[{args}]" if args else ""
        return f"(FunctionCall name='{node.callee}'{body_s})"
    if isinstance(node, FunctionDefNode):
        params_s = ", ".join(f"{p.name}: {str(p.type_annot) if p.type_annot else ''}" for p in node.params)
        ret = str(node.return_type) if node.return_type else "void"
        body = " ".join(py_ast_to_canonical(s) for s in node.body)
        value_attr = f" val='{node.doc_comment}'" if node.doc_comment else ""
        async_attr = " async=true" if node.is_async else ""
        params_attr = f" params=[{params_s}]" if params_s else ""
        return f"(FunctionDef name='{node.name}'{value_attr} type='{ret}'{async_attr}{params_attr} body=[{body}])"
    if isinstance(node, StructDefNode):
        params_s = ", ".join(f"{p.name}: {str(p.type_annot) if p.type_annot else ''}" for p in node.fields)
        value_attr = f" val='{node.doc_comment}'" if node.doc_comment else ""
        return f"(StructDef name='{node.name}'{value_attr} params=[{params_s}])"
    if isinstance(node, ImplBlockNode):
        methods = " ".join(py_ast_to_canonical(m) for m in node.methods)
        trait_attr = f" val='{node.trait_name}'" if node.trait_name else ""
        return f"(ImplBlock name='{node.target_type}'{trait_attr} body=[{methods}])"
    if isinstance(node, TraitDefNode):
        methods = " ".join(py_ast_to_canonical(m) for m in node.methods)
        return f"(TraitDef name='{node.name}' body=[{methods}])"
    if isinstance(node, TypeAliasNode):
        return f"(TypeAlias name='{node.name}' type='{node.actual_type}')"
    if isinstance(node, EnumDefNode):
        members = []
        for member in node.members:
            value_attr = f" body=[{py_ast_to_canonical(member.value)}]" if member.value else ""
            payload_attr = ""
            if member.is_variant:
                payload_attr = " params=[" + ", ".join(str(item) for item in member.payload_types) + "]"
            members.append(f"(EnumMember name='{member.name}'{payload_attr}{value_attr})")
        generics_attr = " params=[" + ", ".join(node.generic_params) + "]" if node.generic_params else ""
        return f"(EnumDef name='{node.name}'{generics_attr} body=[{' '.join(members)}])"
    if isinstance(node, ImportNode):
        name_attr = f" name='{node.alias}'" if node.alias else ""
        ecosystem_attr = f" op='{node.ecosystem}'" if node.ecosystem else ""
        source_attr = f" type='{node.source}'" if node.source else ""
        return f"(Import{name_attr} val='{node.path}'{ecosystem_attr}{source_attr})"
    if isinstance(node, IfNode):
        then_b = " ".join(py_ast_to_canonical(s) for s in node.then_branch)
        elif_b = ""
        for elif_cond, elif_body in node.elif_branches:
            elif_stmts = " ".join(py_ast_to_canonical(s) for s in elif_body)
            elif_b += f" (ElifBlock body=[{py_ast_to_canonical(elif_cond)} {elif_stmts}])"
        else_b = ""
        if node.else_branch:
            else_stmts = " ".join(py_ast_to_canonical(s) for s in node.else_branch)
            else_b = f" (ElseBlock body=[{else_stmts}])"
        return f"(If body=[{py_ast_to_canonical(node.condition)} {then_b}{elif_b}{else_b}])"
    if isinstance(node, WhileNode):
        body = " ".join(py_ast_to_canonical(s) for s in node.body)
        return f"(While body=[{py_ast_to_canonical(node.condition)} {body}])"
    if isinstance(node, ForNode):
        first = node.start_expr if node.start_expr is not None else node.collection_expr
        start = py_ast_to_canonical(first) if first else "(Null)"
        end = py_ast_to_canonical(node.end_expr) if node.end_expr else "(Null)"
        body = " ".join(py_ast_to_canonical(s) for s in node.body)
        return f"(For name='{node.var_name}' body=[{start} {end} {body}])"
    if isinstance(node, MemberAccessNode):
        return f"(MemberAccess name='{node.member}' body=[{py_ast_to_canonical(node.obj)}])"
    if isinstance(node, IndexAccessNode):
        return f"(IndexAccess body=[{py_ast_to_canonical(node.obj)} {py_ast_to_canonical(node.index_expr)}])"
    if isinstance(node, UnsafeBlockNode):
        body = " ".join(py_ast_to_canonical(s) for s in node.body)
        return f"(UnsafeBlock body=[{body}])"
    if isinstance(node, SpawnNode):
        body = " ".join(py_ast_to_canonical(s) for s in node.body)
        return f"(Spawn body=[{body}])"
    if isinstance(node, MatchNode):
        cases_s = []
        for pat, blk in node.cases:
            if isinstance(blk, list):
                blk_s = " ".join(py_ast_to_canonical(s) for s in blk)
            elif isinstance(blk, UnsafeBlockNode):
                blk_s = " ".join(py_ast_to_canonical(s) for s in blk.body)
            else:
                blk_s = py_ast_to_canonical(blk)
            cases_s.append(f"{py_ast_to_canonical(pat)} (MatchCase body=[{blk_s}])")
        return f"(Match body=[{py_ast_to_canonical(node.expr)} {' '.join(cases_s)}])"
    if isinstance(node, ReturnNode):
        if node.expr is None:
            return "(Return)"
        return f"(Return body=[{py_ast_to_canonical(node.expr)}])"
    if isinstance(node, ThrowNode):
        return f"(Throw body=[{py_ast_to_canonical(node.expr)}])"
    if isinstance(node, BreakNode):
        return "(Break)"
    if isinstance(node, ContinueNode):
        return "(Continue)"
    if isinstance(node, DeferNode):
        return f"(Defer body=[{py_ast_to_canonical(node.expr)}])"
    if isinstance(node, GuardNode):
        body = " ".join(py_ast_to_canonical(s) for s in node.else_body)
        return f"(Guard body=[{py_ast_to_canonical(node.condition)} {body}])"
    if isinstance(node, AssertNode):
        value_attr = f" val='{node.message}'" if node.message else ""
        return f"(Assert{value_attr} body=[{py_ast_to_canonical(node.condition)}])"
    if isinstance(node, TestBlockNode):
        body = " ".join(py_ast_to_canonical(s) for s in node.body)
        return f"(TestBlock val='{node.description}' body=[{body}])"
    if isinstance(node, TryCatchNode):
        try_body = " ".join(py_ast_to_canonical(s) for s in node.try_body)
        catch_body = " ".join(py_ast_to_canonical(s) for s in node.catch_body)
        return (
            f"(TryCatch name='{node.err_name}' body=["
            f"(TryBlock body=[{try_body}]) "
            f"(CatchBlock name='{node.err_name}' body=[{catch_body}])])"
        )
    if isinstance(node, ExternFnDeclNode):
        params_s = ", ".join(f"{p.name}: {p.type_annot.name if p.type_annot else ''}" for p in node.params)
        ret = node.return_type.name if node.return_type else "void"
        return f"(ExternFn name='{node.name}' val='{node.abi}' type='{ret}' params=[{params_s}])"
    if isinstance(node, NativeIncludeNode):
        return f"(Directive name='native_include' val='{node.header}')"
    if isinstance(node, NativeLinkNode):
        return f"(Directive name='native_link' val='{node.library}')"
    if isinstance(node, NativeUseNode):
        return f"(Directive name='native_use' val='{node.target}')"
    if isinstance(node, NativeRawNode):
        return f"(Directive name='native_raw' val='{node.raw}')"
    return f"({type(node).__name__})"

def run_bootstrap_parser_test() -> bool:
    print("=" * 70)
    print("⚡ NYX PHASE 4.0.4 - 4.0.5 EXHAUSTIVE BOOTSTRAP PARSER PARITY HARNESS")
    print("=" * 70)

    with open(os.path.join(_root_dir, "compiler", "parser.nyx"), "r", encoding="utf-8") as f:
        parser_content = f.read()

    # Strip top directives from parser_content
    parser_lines = [l for l in parser_content.split("\n") if not (l.startswith("#target") or l.startswith("#native"))]
    parser_body = "\n".join(parser_lines)

    with open(os.path.join(_root_dir, "compiler", "lexer.nyx"), "r", encoding="utf-8") as f:
        lexer_content = f.read()

    # Reuse lexer support while keeping parser.nyx's canonical Token struct.
    lexer_support_start = lexer_content.index("// NYX_LEXER_SUPPORT_BEGIN:")
    lexer_impl_end = lexer_content.index("fn main()") if "fn main()" in lexer_content else len(lexer_content)
    lexer_code = lexer_content[lexer_support_start:lexer_impl_end].strip()

    combined_base = f"""#target cpp
#native include <string>
#native include <vector>

{parser_body}

{lexer_code}
"""

    test_cases = [
        ("simple_var_and_math", "var x: int = 10 + 20 * 30;"),
        ("function_definition", "fn add(a: int, b: int) -> int { return a + b; }"),
        ("expression_body_function", "fn add(a: int, b: int) -> int = a + b;"),
        ("conditional_expression", "fn classify(x: int) -> string = if x < 0 { \"negative\" } elif x == 0 { \"zero\" } else { \"positive\" };"),
        ("conditional_expression_else_if", "fn choose(x: int) -> int = if x < 0 { -1 } else if x == 0 { 0 } else { 1 };"),
        ("match_expression", 'fn status(code: int) -> string = match code { 200 => "ok", 404 => "missing", _ => "other" };'),
        ("match_expression_braced_arms", "fn sign(x: int) -> int = match x { -1 => { -1 }, 0 => { 0 }, _ => { 1 } };"),
        ("struct_definition", "struct Point { x: int, y: int }"),
        ("array_destructuring", "let [left, right] = [20, 22];"),
        ("struct_destructuring", "struct Point { x: int, y: int } let Point(x, y) = Point(3, 4);"),
        ("impl_and_methods", "impl Point { fn dist(self) -> int { return self.x + self.y; } }"),
        ("if_else_branches", "if a > 10 { print(\"Large\"); } else { print(\"Small\"); }"),
        ("if_elif_else_branches", "if a > 10 { print(\"Large\"); } elif a == 10 { print(\"Equal\"); } else { print(\"Small\"); }"),
        ("else_if_alias", "if a > 10 { print(\"Large\"); } else if a == 10 { print(\"Equal\"); } else { print(\"Small\"); }"),
        ("let_and_set", "let limit: int = 10; var current: int = 0; set current = limit;"),
        ("while_and_break", "while true { break; }"),
        ("for_range_loop", "for i in 0..10 { continue; }"),
        ("unsafe_block", "unsafe { var ptr = addr(x); }"),
        ("match_pattern", "match x { 1 => { print(\"One\"); } 2 => { print(\"Two\"); } }"),
        ("match_result_commas", 'match r { Ok(v) => print("OK", v), Err(e) => print("ERR", e), "_" => print("OTHER") }'),
        ("extern_ffi_decl", "extern \"C\" fn puts(s: string) -> int;"),
        ("native_directives", "#native include <vector>\n#native link \"user32.lib\"\n#native use std::vector;"),
        ("bitwise_shift_precedence", "var x = 1 | 2 ^ 3 & 4 << 1 + 2;"),
        ("null_coalesce", "var x = maybe ?? \"fallback\";"),
        ("pipeline_simple", "var x = 5 |> double;"),
        ("pipeline_call", "var x = 5 |> clamp(0, 10);"),
        ("lambda_single", "var twice = x => x * 2;"),
        ("lambda_empty", "var answer = () => 42;"),
        ("lambda_multi", "var add = (left, right) => left + right;"),
        ("generic_channel_and_input", "var ch = channel<int>(); var name = input();"),
        ("nested_generic_closers_and_shift", "struct Matrix { rows: Array<Array<Array<int>>> } fn half(x: int) -> int { return x >> 1; }"),
        ("unary_pointer_bit_not_and_plus", "var value = *ptr; var inverted = ~mask; var positive = +1;"),
        ("signed_i64_min_literals", "let decimal: int = -9223372036854775808; let hex: int = -0x8000000000000000;"),
        ("async_generic_with_doc", "/// identity docs\nasync fn identity<T>(value: T) -> T { return value; }"),
        ("async_await", "async fn compute() -> int { return 42; } async fn run() -> int { return await compute(); }"),
        ("result_propagation", "fn read() -> Result<int, string> { return Ok(1) } fn run() -> Result<int, string> { var value = read()?; return Ok(value) }"),
        ("generic_struct_with_doc", "/// box docs\nstruct Box<T> { value: T }"),
        ("type_alias_and_enum", "type UserID = int; enum Color { Red, Green = 5, Blue }"),
        ("payload_enum", "enum Result<T, E> { Ok(T), Err(E) } enum Event { Tick(), Point(int, int) }"),
        ("trait_impl_target", "trait Show { fn show(self) { return; } } impl Show for Item { fn show(self) { return; } }"),
        ("imports", "import \"std/math\"; import \"./item\" as item; import { add, sub } from \"./ops\";"),
        ("foreign_imports", 'import cpp "std::filesystem" from "<filesystem>" as fs; import js "node:os" as os; import python "platform" as platform;'),
        ("test_and_assert", "test \"math works\" { assert(1 + 1 == 2, \"bad math\"); }"),
        ("try_catch", "try { print(\"work\"); } catch err { print(err); }"),
        ("throw_and_catch", "fn fail() { throw \"boom\"; } try { fail(); } catch err { print(err); }"),
        ("defer_and_guard", "fn guarded(ok: bool) { defer cleanup(); guard ok else { return; } }"),
        ("collection_for", "for item in items { print(item); }"),
        ("loop_sugar", "loop { break; }")
    ]

    expected = []
    native_sections = []
    for index, (name, src) in enumerate(test_cases):
        py_tokens = PyLexer(src, f"{name}.nyx").tokenize()
        py_ast = PyParser(py_tokens, src, f"{name}.nyx").parse()
        expected.append(py_ast_to_canonical(py_ast))

        escaped_src = (
            src.replace('\\', '\\\\')
            .replace('"', '\\"')
            .replace('\r', '\\r')
            .replace('\n', '\\n')
            .replace('\t', '\\t')
        )
        native_sections.append(f"""
    var code_{index} = "{escaped_src}"
    var lexer_{index} = Lexer(lexer_characters(code_{index}), 0, 1, 1)
    var tokens_{index} = lexer_{index}.tokenize()
    var parser_{index} = Parser(tokens_{index}, 0, false, "", "")
    var ast_{index} = parser_{index}.parse_program()
    if parser_{index}.has_error {{
        print("@@ERROR@@{index}:" + parser_{index}.error_msg)
    }} else {{
        print("@@CASE@@{index}")
        print(ast_{index}.to_str())
    }}
""")

    runner_code = (
        combined_base
        + "\nfn main() {\n"
        + "".join(native_sections)
        + "}\n\nmain()\n"
    )
    tokens_ast = PyLexer(runner_code, "parser_parity_driver.nyx").tokenize()
    ast = PyParser(tokens_ast, runner_code, "parser_parity_driver.nyx").parse()
    cpp_code = UniversalCodeGen(ast).gen_cpp()

    all_passed = True
    temp_dir = tempfile.mkdtemp(prefix="nyx_test_parser_")
    exe_file = os.path.join(temp_dir, "nyx_parser.exe")
    cpp_file = os.path.join(temp_dir, "nyx_parser.cpp")
    native_results = {}
    native_errors = {}
    try:
        with open(cpp_file, "w", encoding="utf-8") as f:
            f.write(cpp_code)

        ok, msg = CppToolchain.compile_cpp(cpp_file, exe_file)
        if not ok:
            print(f"Native parser driver compile failed:\n{msg}")
            return False

        return_code, output = CppToolchain.run_executable(exe_file)
        if return_code != 0:
            print(f"Native parser driver exited with {return_code}:\n{output}")
            return False
        lines = output.splitlines()
        line_index = 0
        while line_index < len(lines):
            line = lines[line_index]
            if line.startswith("@@CASE@@"):
                case_index = int(line[len("@@CASE@@"):])
                native_results[case_index] = lines[line_index + 1] if line_index + 1 < len(lines) else ""
                line_index += 2
                continue
            if line.startswith("@@ERROR@@"):
                case_text, _, message = line[len("@@ERROR@@"):].partition(":")
                native_errors[int(case_text)] = message
            line_index += 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    for index, (name, _src) in enumerate(test_cases):
        print(f"[*] Verifying AST Parity: {name} ...", end=" ")
        if index in native_errors:
            print(f"FAILED (native parse error: {native_errors[index]})")
            all_passed = False
        elif native_results.get(index) == expected[index]:
            print("PASS (Exact Canonical AST Match)")
        else:
            print("FAILED (AST mismatch)")
            print(f"  Py:  {expected[index]}")
            print(f"  Nyx: {native_results.get(index, '<missing>')}")
            all_passed = False

    print("=" * 70)
    print(f"Exhaustive Bootstrap Parser Parity Result: {'SUCCESS' if all_passed else 'FAILURE'}")
    print("=" * 70)
    return all_passed

if __name__ == "__main__":
    success = run_bootstrap_parser_test()
    sys.exit(0 if success else 1)
