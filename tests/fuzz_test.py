import os
import sys
import io
import random
import string

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.core import Lexer, Parser, TypeChecker, DiagnosticEmitter

# Seeded for reproducible fuzzing
random.seed(42)

STATIC_FUZZ_CASES = [
    "(((((((((",
    "}}}}}}}}",
    "[[[[[[]",
    "(][){}",
    'var x = "unterminated string',
    'var x = 1.2.3.4.5',
    'var 0xZZZZ = 10',
    '0x',
    'var $$$$$ = &&&&',
    '?.?.?.',
    '-> -> ->',
    '|> |> |>',
    '+++++ 5',
    '===== 10',
    ';;;;;;;;;;',
    'struct struct struct',
    'fn fn() {}',
    'while for break continue',
    'return return return',
    'var x: int = = = = 10',
    'match match { => => }',
    'test test "unclosed',
    'unsafe { unsafe { unsafe {',
    'fn foo(,,,,) {}',
    'var a = [,,,,]',
    'var a = {::::}',
    '10 + * / 20',
    'true false null undefined NaN',
    '/// unclosed doc\nvar x = 10',
    'print((((((((((((((((1))))))))))))))))',
]

def generate_random_fuzz(count: int = 500):
    tokens_pool = [
        'var', 'let', 'const', 'fn', 'struct', 'if', 'elif', 'else', 'while',
        'for', 'in', 'return', 'break', 'continue', 'unsafe', 'spawn', 'test',
        'assert', 'match', 'Ok', 'Err', 'print', 'addr', 'peek', 'memdump',
        'int', 'string', 'float', 'bool', 'null', 'true', 'false',
        '(', ')', '{', '}', '[', ']', ':', ',', ';', '.', '..', '?.', '??',
        '+', '-', '*', '/', '%', '=', '==', '!=', '>', '<', '>=', '<=',
        '&&', '||', '!', '->', '=>', '|>', '$', '""', '"hello"', '123', '3.14',
        '0xFF', 'foo', 'bar', 'baz', '\n', ' '
    ]
    cases = []
    for _ in range(count):
        length = random.randint(3, 20)
        chosen = [random.choice(tokens_pool) for _ in range(length)]
        cases.append(" ".join(chosen))
    return cases

def run_fuzz_tests(num_random: int = 500):
    print(f"[*] Running Compiler Fuzz Testing Suite ({len(STATIC_FUZZ_CASES)} static + {num_random} randomized cases)...")
    
    all_cases = STATIC_FUZZ_CASES + generate_random_fuzz(num_random)
    crashes = 0
    clean_rejections = 0
    valid_parses = 0
    
    for idx, code in enumerate(all_cases, 1):
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        
        try:
            tokens = Lexer(code, f"fuzz_{idx}.rove").tokenize()
            ast = Parser(tokens, code, f"fuzz_{idx}.rove").parse()
            tc = TypeChecker(ast, f"fuzz_{idx}.rove", code)
            tc.check()
            valid_parses += 1
        except SystemExit:
            # Clean diagnostic emission via DiagnosticEmitter.emit_error()
            clean_rejections += 1
        except Exception as e:
            # Unhandled python exception / crash!
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            print(f"  [CRASH] Fuzz Case {idx} caused unhandled exception: {type(e).__name__}: {e}")
            print(f"  Code Snippet: {repr(code)}")
            crashes += 1
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    total = len(all_cases)
    print(f"  [OK] Fuzzing Completed: {total} total cases evaluated.")
    print(f"       - Clean Graceful Diagnostics: {clean_rejections}")
    print(f"       - Valid Programs:             {valid_parses}")
    print(f"       - Unhandled Crashes:          {crashes}")
    
    if crashes == 0:
        print("  [PASS] Compiler Fuzzing 100% Robust (Zero Unhandled Crashes)")
        return True
    else:
        print(f"  [FAIL] Compiler Fuzzing encountered {crashes} crashes!")
        return False

if __name__ == "__main__":
    ok = run_fuzz_tests(500)
    sys.exit(0 if ok else 1)
