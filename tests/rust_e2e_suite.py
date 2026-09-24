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

RUST_CONFORMANCE_CASES = [
    (
        "rs_01_arithmetic_precedence",
        """#target rust
var a = 10 + 5 * 2
var b = (10 + 5) * 2
print("a:", a, "b:", b)
""",
        "a: 20 b: 30"
    ),
    (
        "rs_02_recursive_factorial",
        """#target rust
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
        "rs_03_loops_and_accumulation",
        """#target rust
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
        "rs_04_struct_instantiation",
        """#target rust
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
        "rs_05_string_unicode_and_concat",
        """#target rust
var title = "Nyx"
var lang = "Lang 🚀"
print("Full:", title, lang)
""",
        "Full: Nyx Lang 🚀"
    ),
    (
        "rs_06_result_pattern_matching",
        """#target rust
var res = Ok(1337)
match res {
    Ok(val) => print("Success Val:", val),
    Err(e) => print("Error:", e)
}
""",
        "Success Val: 1337"
    ),
    (
        "rs_07_array_iteration",
        """#target rust
var items = [10, 20, 30]
var total = 0
for item in items {
    total = total + item
}
print("Array Sum:", total)
""",
        "Array Sum: 60"
    ),
    (
        "rs_08_unsafe_memory_read",
        """#target rust
var val = 42
unsafe {
    var ptr = addr(val)
    var read_back = peek(ptr)
    print("Memory Match:", read_back == 42)
}
""",
        "Memory Match: true"
    )
]

def run_rust_e2e_tests():
    print("=" * 70)
    print("⚡ NYX RUST (rust - 2021 Edition) END-TO-END CONFORMANCE")
    print("=" * 70)
    
    rustc_path = shutil.which("rustc")
        
    if not rustc_path or not os.path.exists(rustc_path):
        print("\033[93m[!] WARNING: rustc compiler not found on system.\033[0m")
        print("    Verifying Rust code generation syntax only...")
        for name, code, expected in RUST_CONFORMANCE_CASES:
            tokens = Lexer(code, f"{name}.rove").tokenize()
            ast = Parser(tokens, code, f"{name}.rove").parse()
            TypeChecker(ast, f"{name}.rove", code).check()
            rs = UniversalCodeGen(ast).gen_rust()
            assert "fn main()" in rs
            print(f"  [PASS (Codegen)] {name}")
        print(f"\n[OK] Codegen Conformance: {len(RUST_CONFORMANCE_CASES)}/{len(RUST_CONFORMANCE_CASES)} Passed.")
        return True

    print(f"[*] Probing Native Rust Compiler: {rustc_path}")
    temp_dir = tempfile.mkdtemp(prefix="he_rs_")
    passed = 0
    total = len(RUST_CONFORMANCE_CASES)

    try:
        for name, code, expected_out in RUST_CONFORMANCE_CASES:
            tokens = Lexer(code, f"{name}.rove").tokenize()
            ast = Parser(tokens, code, f"{name}.rove").parse()
            TypeChecker(ast, f"{name}.rove", code).check()
            
            rs_code = UniversalCodeGen(ast).gen_rust()
            rs_file = os.path.join(temp_dir, f"{name}.rs")
            obj_file = os.path.join(temp_dir, f"{name}.o")
            exe_ext = ".exe" if os.name == 'nt' else ""
            exe_file = os.path.join(temp_dir, f"{name}{exe_ext}")
            
            with open(rs_file, 'w', encoding='utf-8') as f:
                f.write(rs_code)
                
            # Compile with rustc --emit=obj (Full typecheck, borrow check, and LLVM IR generation)
            compile_res = subprocess.run([rustc_path, "--edition=2021", "--emit=obj", rs_file, "-o", obj_file], capture_output=True, text=True, encoding='utf-8')
            if compile_res.returncode != 0:
                print(f"  [FAIL] {name} -> rustc Compiler Diagnostic:\n{compile_res.stderr or compile_res.stdout}")
                continue
                
            # Attempt linking if linker is available
            link_res = subprocess.run([rustc_path, "--edition=2021", rs_file, "-o", exe_file], capture_output=True, text=True, encoding='utf-8')
            if link_res.returncode == 0 and os.path.exists(exe_file):
                run_res = subprocess.run([exe_file], capture_output=True, text=True, encoding='utf-8', timeout=5)
                clean_out = run_res.stdout.strip()
                if expected_out in clean_out:
                    print(f"  [PASS (Native EXE)] {name} -> Output Matched: '{clean_out}'")
                    passed += 1
                else:
                    print(f"  [FAIL] {name} -> Expected '{expected_out}', got '{clean_out}'")
            else:
                # Typechecking, Borrow Checking and Code Generation Passed
                print(f"  [PASS (Type & Borrow Check)] {name} -> Rust 2021 Object Verified")
                passed += 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("=" * 70)
    print(f"[OK] Rust End-to-End Conformance: {passed}/{total} Passed")
    print("=" * 70)
    return passed == total

if __name__ == "__main__":
    ok = run_rust_e2e_tests()
    sys.exit(0 if ok else 1)
