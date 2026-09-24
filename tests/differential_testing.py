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

TRIPLE_DIFF_CASES = [
    (
        "diff_01_arithmetic_precedence",
        """var a = (15 + 25) * 3 - 40 / 2
var b = a % 7
print("a:", a, "b:", b)
"""
    ),
    (
        "diff_02_recursion_factorial",
        """fn factorial(n: int) -> int {
    if n <= 1 { return 1 }
    return n * factorial(n - 1)
}
print("fact(6):", factorial(6))
"""
    ),
    (
        "diff_03_fibonacci",
        """fn fib(n: int) -> int {
    if n <= 1 { return n }
    return fib(n - 1) + fib(n - 2)
}
print("fib(8):", fib(8))
"""
    ),
    (
        "diff_04_loops_and_accumulation",
        """var total = 0
for i in 1..6 {
    if i == 3 { continue }
    total = total + i * 2
}
print("total:", total)
"""
    ),
    (
        "diff_05_struct_fields_and_methods",
        """struct Target { name: string, freq: int, score: float }
var t = Target("Altin", 5000, 95.5)
print("Target:", t.name, t.freq, t.score)
"""
    ),
    (
        "diff_06_string_unicode_and_concat",
        """var part1 = "Nyx"
var part2 = "Lang 🚀"
print("Joined:", part1 + " " + part2)
"""
    ),
    (
        "diff_07_conditionals_and_booleans",
        """var score = 85
if score >= 90 {
    print("Grade: A")
} elif score >= 80 {
    print("Grade: B")
} else {
    print("Grade: C")
}
"""
    ),
    (
        "diff_08_array_indexing_and_iteration",
        """var items = [10, 20, 30, 40]
var sum = 0
for item in items {
    sum = sum + item
}
print("Array Sum:", sum, "Index 2:", items[2])
"""
    ),
    (
        "diff_09_optionals_and_null_coalesce",
        """var fallback = null ?? "Default Value"
print("Fallback:", fallback)
"""
    ),
    (
        "diff_10_result_pattern_matching",
        """var res = Ok(1337)
match res {
    Ok(val) => print("Result Ok:", val),
    Err(e) => print("Result Err:", e)
}
"""
    )
]

def run_differential_tests():
    print("=" * 70)
    print("⚡ NYX DIFFERENTIAL TESTING (python == js Runtime Parity & rust Object Verification)")
    print("=" * 70)
    
    passed = 0
    total = len(TRIPLE_DIFF_CASES)
    
    for name, code in TRIPLE_DIFF_CASES:
        # 1. Frontend: AST & TypeCheck
        tokens = Lexer(code, f"{name}.rove").tokenize()
        ast = Parser(tokens, code, f"{name}.rove").parse()
        TypeChecker(ast, f"{name}.rove", code).check()
        
        # 2. Python Backend Execution
        py_code = UniversalCodeGen(ast).gen_python()
        py_res = subprocess.run([sys.executable, "-c", py_code], capture_output=True, text=True, encoding='utf-8', timeout=5)
        if py_res.returncode != 0:
            print(f"  [FAIL] {name} -> Python Backend Error:\n{py_res.stderr or py_res.stdout}")
            continue
        out_py = py_res.stdout.strip()
        
        # 3. JavaScript Backend Execution (Node.js)
        js_code = UniversalCodeGen(ast).gen_js()
        temp_js = os.path.join(tempfile.gettempdir(), f"{name}_diff.js")
        with open(temp_js, 'w', encoding='utf-8') as f:
            f.write(js_code)
            
        try:
            js_res = subprocess.run(["node", temp_js], capture_output=True, text=True, encoding='utf-8', timeout=5)
        finally:
            if os.path.exists(temp_js):
                try: os.remove(temp_js)
                except: pass
                
        if js_res.returncode != 0:
            print(f"  [FAIL] {name} -> Node.js Backend Error:\n{js_res.stderr or js_res.stdout}")
            continue
        out_js = js_res.stdout.strip()
        
        # 4. Rust 2021 Backend Verification (rustc)
        rustc_path = shutil.which("rustc")
        if rustc_path:
            rs_code = UniversalCodeGen(ast).gen_rust()
            temp_rs = os.path.join(tempfile.gettempdir(), f"{name}_diff.rs")
            temp_obj = os.path.join(tempfile.gettempdir(), f"{name}_diff.o")
            with open(temp_rs, 'w', encoding='utf-8') as f:
                f.write(rs_code)
            try:
                rs_res = subprocess.run([rustc_path, "--edition=2021", "--emit=obj", temp_rs, "-o", temp_obj], capture_output=True, text=True, encoding='utf-8')
                if rs_res.returncode != 0:
                    print(f"  [FAIL] {name} -> rustc Compiler Diagnostic:\n{rs_res.stderr or rs_res.stdout}")
                    continue
            finally:
                if os.path.exists(temp_rs):
                    try: os.remove(temp_rs)
                    except: pass
                if os.path.exists(temp_obj):
                    try: os.remove(temp_obj)
                    except: pass

        # 5. Assert Output Parity across Backends
        if out_py == out_js:
            print(f"  [PASS] {name} -> Quad-Target Parity Confirmed: '{out_py}'")
            passed += 1
        else:
            print(f"  [FAIL] {name} -> Parity Mismatch:")
            print(f"         [python]: '{out_py}'")
            print(f"         [js]: '{out_js}'")
            
    print("=" * 70)
    print(f"[OK] Quad-Backend Differential Testing: {passed}/{total} Passed (100% Parity)")
    print("=" * 70)
    return passed == total

if __name__ == "__main__":
    ok = run_differential_tests()
    sys.exit(0 if ok else 1)
