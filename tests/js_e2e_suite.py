import os
import sys
import subprocess
import tempfile
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.core import Lexer, Parser, TypeChecker
from src.codegen import UniversalCodeGen

JS_CONFORMANCE_CASES = [
    (
        "js_01_arithmetic_precedence",
        """#target js
var a = 10 + 5 * 2
var b = (10 + 5) * 2
print("a:", a, "b:", b)
""",
        "a: 20 b: 30"
    ),
    (
        "js_02_recursive_factorial",
        """#target js
fn factorial(n: int) -> int {
    if n <= 1 {
        return 1
    }
    return n * factorial(n - 1)
}
print("fact(6):", factorial(6))
""",
        "fact(6): 720"
    ),
    (
        "js_03_mutual_recursion",
        """#target js
fn is_even(n: int) -> bool {
    if n == 0 { return true }
    return is_odd(n - 1)
}

fn is_odd(n: int) -> bool {
    if n == 0 { return false }
    return is_even(n - 1)
}
print("even(10):", is_even(10), "odd(7):", is_odd(7))
""",
        "even(10): true odd(7): true"
    ),
    (
        "js_04_struct_instantiation",
        """#target js
struct Target {
    name: string,
    freq: int,
    signal: float
}

var t = Target("Altin", 5000, 98.5)
print("Target:", t.name, t.freq, t.signal)
""",
        "Target: Altin 5000 98.5"
    ),
    (
        "js_05_loops_and_accumulation",
        """#target js
var sum = 0
for i in 1..10 {
    if i == 5 {
        continue
    }
    sum = sum + i
}
print("Sum excluding 5:", sum)
""",
        "Sum excluding 5: 50"
    ),
    (
        "js_06_string_unicode_and_concat",
        """#target js
var title = "Nyx"
var lang = "Lang 🚀"
var full = title + " " + lang
print("Full:", full)
""",
        "Full: Nyx Lang 🚀"
    ),
    (
        "js_07_result_pattern_matching",
        """#target js
var res = Ok(1337)
match res {
    Ok(val) => print("Success Val:", val),
    Err(e) => print("Error:", e)
}
""",
        "Success Val: 1337"
    ),
    (
        "js_08_array_iteration",
        """#target js
var items = [10, 20, 30]
var total = 0
for item in items {
    total = total + item
}
print("Array Sum:", total)
""",
        "Array Sum: 60"
    )
]

def run_js_e2e_tests():
    print("=" * 70)
    print("⚡ NYX JS (Node.js ES2022) END-TO-END CONFORMANCE HARNESS")
    print("=" * 70)
    
    passed = 0
    total = len(JS_CONFORMANCE_CASES)
    
    for name, code, expected_out in JS_CONFORMANCE_CASES:
        tokens = Lexer(code, f"{name}.rove").tokenize()
        ast = Parser(tokens, code, f"{name}.rove").parse()
        TypeChecker(ast, f"{name}.rove", code).check()
        
        js_code = UniversalCodeGen(ast).gen_js()
        temp_js = os.path.join(tempfile.gettempdir(), f"{name}.js")
        with open(temp_js, 'w', encoding='utf-8') as f:
            f.write(js_code)
            
        try:
            res = subprocess.run(["node", temp_js], capture_output=True, text=True, encoding='utf-8', timeout=5)
            if res.returncode == 0:
                clean_out = res.stdout.strip()
                if expected_out in clean_out:
                    print(f"  [PASS] {name} -> Node.js Output Matched: '{clean_out}'")
                    passed += 1
                else:
                    print(f"  [FAIL] {name} -> Expected '{expected_out}', got '{clean_out}'")
            else:
                print(f"  [FAIL] {name} -> Node.js Runtime Error:\n{res.stderr or res.stdout}")
        except Exception as e:
            print(f"  [FAIL] {name} -> Exception: {e}")
        finally:
            if os.path.exists(temp_js):
                try: os.remove(temp_js)
                except: pass
            
    print("=" * 70)
    print(f"[OK] JS (Node.js) End-to-End Conformance: {passed}/{total} Passed")
    print("=" * 70)
    return passed == total

if __name__ == "__main__":
    ok = run_js_e2e_tests()
    sys.exit(0 if ok else 1)
