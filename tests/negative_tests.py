import os
import sys
import io

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.core import Lexer, Parser, TypeChecker

negative_cases = [
    (
        "neg_type_01_var_decl_mismatch",
        '#target cpp\nvar x: int = "hello"',
        "E2001"
    ),
    (
        "neg_type_02_assign_mismatch",
        '#target cpp\nvar x: int = 10\nx = "string"',
        "E2002"
    ),
    (
        "neg_type_03_fn_arg_mismatch",
        '#target cpp\nfn add(a: int, b: int) -> int { return a + b }\nadd("hello", 5)',
        "E2003"
    ),
    (
        "neg_type_04_return_type_mismatch",
        '#target cpp\nfn foo(x: int) -> string { return x }\nfoo(10)',
        "E2004"
    ),
    (
        "neg_type_05_invalid_string_sub",
        '#target cpp\nvar res = "abc" - "x"',
        "E2005"
    ),
    (
        "neg_type_06_bool_mult",
        '#target cpp\nvar res = true * 5',
        "E2005"
    ),
    (
        "neg_type_07_struct_field_mismatch",
        '#target cpp\nstruct Hero { name: string, hp: int }\nvar h = Hero(123, "Knight")',
        "E2006"
    ),
    (
        "neg_syntax_01_missing_expr",
        '#target cpp\nvar x: int =',
        "E1000"
    ),
    (
        "neg_syntax_02_unclosed_paren",
        '#target cpp\nprint(10 + 20',
        "E1001"
    ),
    (
        "neg_safety_01_unsafe_peek",
        '#target cpp\nvar a = 1234\npeek(a)',
        "E1050"
    )
]

def run_negative_tests():
    print("[*] Running Negative & Rejection Test Suite (10 Error Diagnostics)...")
    passed = 0
    total = len(negative_cases)
    
    for name, code, expected_code in negative_cases:
        old_stdout = sys.stdout
        sys.stdout = buf = io.StringIO()
        caught_error_code = None
        
        try:
            tokens = Lexer(code, f"{name}.rove").tokenize()
            ast = Parser(tokens, code, f"{name}.rove").parse()
            tc = TypeChecker(ast, f"{name}.rove", code)
            tc.check()
        except (Exception, SystemExit):
            out = buf.getvalue()
            if f"error[{expected_code}]" in out:
                caught_error_code = expected_code
        finally:
            sys.stdout = old_stdout
            
        if caught_error_code == expected_code:
            print(f"  [PASS] {name} -> Correctly rejected with error[{expected_code}]")
            passed += 1
        else:
            print(f"  [FAIL] {name} -> Expected error[{expected_code}], got output:\n{buf.getvalue()}")
            
    print(f"  [OK] Negative Tests Result: {passed}/{total} Passed")
    return passed == total

if __name__ == "__main__":
    ok = run_negative_tests()
    sys.exit(0 if ok else 1)
