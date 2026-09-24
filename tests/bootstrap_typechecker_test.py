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
from src.core.type_checker import TypeChecker as PyTypeChecker
from src.codegen.codegen import UniversalCodeGen
from src.codegen.cpp_toolchain import CppToolchain

def run_bootstrap_typechecker_test() -> bool:
    print("=" * 70)
    print("⚡ NYX PHASE 4.0.6 EXHAUSTIVE SEMANTIC TYPECHECKER HARNESS")
    print("=" * 70)

    with open(os.path.join(_root_dir, "compiler", "parser.rove"), "r", encoding="utf-8") as f:
        parser_content = f.read()
    parser_lines = [l for l in parser_content.split("\n") if not (l.startswith("#target") or l.startswith("#native"))]
    parser_body = "\n".join(parser_lines)

    with open(os.path.join(_root_dir, "compiler", "lexer.rove"), "r", encoding="utf-8") as f:
        lexer_content = f.read()
    lexer_impl_start = lexer_content.index("// NYX_LEXER_SUPPORT_BEGIN:")
    lexer_impl_end = lexer_content.index("fn main()") if "fn main()" in lexer_content else len(lexer_content)
    lexer_code = lexer_content[lexer_impl_start:lexer_impl_end].strip()

    with open(os.path.join(_root_dir, "compiler", "type_checker.rove"), "r", encoding="utf-8") as f:
        tc_content = f.read()
    tc_lines = [l for l in tc_content.split("\n") if not (l.startswith("#target") or l.startswith("#native"))]
    tc_body = "\n".join(tc_lines)

    combined_base = f"""#target cpp
#native include <string>
#native include <vector>

{parser_body}

{lexer_code}

{tc_body}
"""

    valid_cases = [
        ("valid_types_and_arithmetic", "var x: int = 10 + 20; var f: float = 10; var s: string = \"hello\";"),
        ("valid_function_return", "fn calc(a: int, b: int) -> int { return a + b; }"),
        ("valid_expression_body", "fn calc(a: int, b: int) -> int = a + b;"),
        ("valid_conditional_expression", "fn classify(x: int) -> string = if x < 0 { \"negative\" } elif x == 0 { \"zero\" } else { \"positive\" };"),
        ("valid_conditional_numeric_widening", "fn choose(flag: bool) -> float = if flag { 1 } else { 2.5 };"),
        ("valid_match_expression", "fn status(code: int) -> string = match code { 200 => \"ok\", 404 => \"missing\", _ => \"other\" };"),
        ("valid_match_expression_call_subject", "fn source() -> int = 1; fn good() -> int = match source() { 1 => 10, _ => 0 };"),
        ("valid_optional_types", "var opt1: string? = null; var opt2: string? = \"active\";"),
        ("valid_struct_field_access", "struct Point { x: int, y: int }\nvar p: Point = Point(10, 20); var px: int = p.x;"),
        ("valid_async_await", "async fn compute() -> int { return 42; } async fn run() -> int { let task: Task<int> = compute(); return await task; }"),
        ("valid_i64_min_literals", "let decimal: int = -9223372036854775808; let hex: int = -0x8000000000000000; let positive: int = +1;"),
        ("valid_default_argument_decl", "fn greet(name: string = \"world\") { print(name); }"),
        ("valid_default_argument_call", "fn greet(name: string = \"world\") { print(name); } fn main() { greet(); }"),
        ("valid_array_destructuring", "let [left, right] = [20, 22]; var total: int = left + right;"),
        ("valid_struct_destructuring", "struct Point { x: int, y: int } let Point(x, y) = Point(3, 4); var total: int = x + y;"),
        ("valid_transparent_type_alias", "type Handle = int; var raw: int = 1; var handle: Handle = raw; fn use_handle(value: Handle) -> int = value; var result: int = use_handle(handle);")
    ]

    all_passed = True
    print("\n--- 1. Valid Semantic Cases (Acceptance Parity) ---")
    for name, src in valid_cases:
        print(f"[*] Validating: {name} ...", end=" ")

        # Python TypeChecker
        py_tokens = PyLexer(src, f"{name}.rove").tokenize()
        py_ast = PyParser(py_tokens, src, f"{name}.rove").parse()
        py_tc = PyTypeChecker(py_ast, f"{name}.rove", src)
        py_accepted = True
        try:
            py_tc.check()
        except:
            py_accepted = False

        # Native Nyx TypeChecker
        escaped_src = src.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        runner_code = f"""{combined_base}

fn main() {{
    var code = "{escaped_src}"
    var lex = Lexer(lexer_characters(code), 0, 1, 1)
    var tokens = lex.tokenize()
    var p = Parser(tokens, 0, false, "", "")
    var ast = p.parse_program()
    var tc = TypeChecker([], [], [], [], "", false, false, "")
    var ok = tc.check_program(ast)
    if ok {{
        print("SEMANTIC_OK")
    }} else {{
        print("SEMANTIC_ERROR:", tc.error_msg)
    }}
}}

main()
"""
        tokens_ast = PyLexer(runner_code, f"{name}_tc_driver.rove").tokenize()
        ast = PyParser(tokens_ast, runner_code, f"{name}_tc_driver.rove").parse()
        cpp_code = UniversalCodeGen(ast).gen_cpp()

        temp_dir = tempfile.mkdtemp(prefix="nyx_tc_")
        exe_file = os.path.join(temp_dir, "nyx_tc.exe")
        cpp_file = os.path.join(temp_dir, "nyx_tc.cpp")

        nyx_accepted = False
        try:
            with open(cpp_file, "w", encoding="utf-8") as f:
                f.write(cpp_code)

            ok, msg = CppToolchain.compile_cpp(cpp_file, exe_file)
            if ok:
                code, output = CppToolchain.run_executable(exe_file)
                if "SEMANTIC_OK" in output:
                    nyx_accepted = True
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        if py_accepted and nyx_accepted:
            print("PASS (Accepted by both)")
        else:
            print(f"FAILED (Py={py_accepted}, Nyx={nyx_accepted})")
            all_passed = False

    print("\n--- 2. Invalid Semantic Cases (Rejection Parity) ---")
    invalid_cases = [
        ("type_mismatch_var", "var x: int = \"string_val\";"),
        ("return_type_mismatch", "fn get_num() -> int { return \"not_a_num\"; }"),
        ("undefined_variable", "var a: int = 10; var b: int = undefined_var + 5;"),
        ("wrong_function_arg_type", "fn square(x: int) -> int { return x * x; }\nsquare(\"invalid\");"),
        ("wrong_argument_count", "fn mult(a: int, b: int) -> int { return a * b; }\nmult(10);"),
        ("scope_leak", "fn compute() -> int { if true { var local_val: int = 42; } return local_val; }"),
        ("elif_scope_leak", "fn compute() -> int { if false { return 0; } elif true { var branch_val: int = 42; } return branch_val; }"),
        ("await_outside_async", "async fn compute() -> int { return 1; } fn bad() -> int { return await compute(); }"),
        ("await_non_task", "async fn bad() -> int { return await 1; }"),
        ("positive_i64_literal_overflow", "let bad: int = 9223372036854775808;"),
        ("negative_i64_literal_overflow", "let bad: int = -9223372036854775809;"),
        ("hex_i64_literal_overflow", "let bad: int = 0x8000000000000000;"),
        ("if_int_truthiness", "if 1 { print(\"bad\"); }"),
        ("while_string_truthiness", "while \"yes\" { break; }"),
        ("guard_int_truthiness", "fn bad() { guard 1 else { return; } }"),
        ("conditional_expression_int_truthiness", "fn bad() -> int = if 1 { 1 } else { 0 };"),
        ("conditional_expression_type_mismatch", "fn bad(flag: bool) -> int = if flag { 1 } else { \"no\" };"),
        ("match_expression_missing_fallback", "fn bad(x: int) -> int = match x { 1 => 10 };"),
        ("match_expression_nonfinal_fallback", "fn bad(x: int) -> int = match x { _ => 0, 1 => 10 };"),
        ("match_expression_type_mismatch", "fn bad(x: int) -> int = match x { 1 => 10, _ => \"no\" };"),
        ("missing_required_argument", "fn f(a: int, b: int = 2) { print(a, b); } fn main() { f(); }"),
        ("array_destructuring_non_array", "let [a, b] = 42;"),
        ("struct_destructuring_wrong_arity", "struct Point { x: int, y: int } let Point(x) = Point(1, 2);")
    ]

    for name, src in invalid_cases:
        print(f"[*] Testing Rejection: {name} ...", end=" ")

        # Python TypeChecker Rejection
        py_rejected = False
        try:
            py_tokens = PyLexer(src, f"{name}.rove").tokenize()
            py_ast = PyParser(py_tokens, src, f"{name}.rove").parse()
            py_tc = PyTypeChecker(py_ast, f"{name}.rove", src)
            try:
                py_tc.check()
            except SystemExit:
                py_rejected = True
        except:
            py_rejected = True

        # Native Nyx TypeChecker Rejection
        escaped_src = src.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        runner_code = f"""{combined_base}

fn main() {{
    var code = "{escaped_src}"
    var lex = Lexer(lexer_characters(code), 0, 1, 1)
    var tokens = lex.tokenize()
    var p = Parser(tokens, 0, false, "", "")
    var ast = p.parse_program()
    var tc = TypeChecker([], [], [], [], "", false, false, "")
    var ok = tc.check_program(ast)
    if ok {{
        print("SEMANTIC_OK")
    }} else {{
        print("SEMANTIC_REJECTED:", tc.error_msg)
    }}
}}

main()
"""
        tokens_ast = PyLexer(runner_code, f"{name}_tc_driver.rove").tokenize()
        ast = PyParser(tokens_ast, runner_code, f"{name}_tc_driver.rove").parse()
        cpp_code = UniversalCodeGen(ast).gen_cpp()

        temp_dir = tempfile.mkdtemp(prefix="nyx_tc_rej_")
        exe_file = os.path.join(temp_dir, "nyx_tc.exe")
        cpp_file = os.path.join(temp_dir, "nyx_tc.cpp")

        nyx_rejected = False
        try:
            with open(cpp_file, "w", encoding="utf-8") as f:
                f.write(cpp_code)

            ok, msg = CppToolchain.compile_cpp(cpp_file, exe_file)
            if ok:
                code, output = CppToolchain.run_executable(exe_file)
                if "SEMANTIC_REJECTED:" in output:
                    nyx_rejected = True
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        if py_rejected and nyx_rejected:
            print("PASS (Dual Rejection - Both Python & Nyx TypeCheckers Rejected)")
        else:
            print(f"FAILED (Py={py_rejected}, Nyx={nyx_rejected})")
            all_passed = False

    print("=" * 70)
    print(f"Phase 4.0.6 TypeChecker Parity Result: {'SUCCESS' if all_passed else 'FAILURE'}")
    print("=" * 70)
    return all_passed

if __name__ == "__main__":
    success = run_bootstrap_typechecker_test()
    sys.exit(0 if success else 1)
