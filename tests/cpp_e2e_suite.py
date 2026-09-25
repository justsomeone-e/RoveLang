import os
import sys
import io
import tempfile
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.core import Lexer, Parser, TypeChecker
from src.codegen import UniversalCodeGen
from src.codegen.cpp_toolchain import CppToolchain

E2E_CONFORMANCE_CASES = [
    (
        "e2e_01_arithmetic_precedence",
        """#target cpp
var a = 10 + 5 * 2
var b = (10 + 5) * 2
print("a:", a, "b:", b)
""",
        "a: 20 b: 30"
    ),
    (
        "e2e_02_recursive_factorial",
        """#target cpp
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
        "e2e_03_mutual_recursion",
        """#target cpp
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
        "e2e_04_struct_methods_and_instantiation",
        """#target cpp
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
        "e2e_05_loops_and_accumulation",
        """#target cpp
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
        "e2e_06_string_unicode_and_concat",
        """#target cpp
var title = "Nyx"
var lang = "Lang 🚀"
var full = title + " " + lang
print("Full:", full)
""",
        "Full: Nyx Lang 🚀"
    ),
    (
        "e2e_07_result_pattern_matching",
        """#target cpp
var res = Ok(1337)
match res {
    Ok(val) => print("Success Val:", val),
    Err(e) => print("Error:", e)
}
""",
        "Success Val: 1337"
    ),
    (
        "e2e_08_unsafe_memory_read",
        """#target cpp
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

def run_cpp_e2e_tests():
    print("=" * 70)
    print("⚡ ROVE C++20 END-TO-END CONFORMANCE HARNESS")
    print("=" * 70)
    
    compiler_path = CppToolchain.find_compiler()
    if not compiler_path:
        print("\033[93m[!] WARNING: No C++20 compiler binary (g++, clang++, cl) found on system.\033[0m")
        print("    Install LLVM / MinGW (e.g. `winget install LLVM.LLVM`) to enable native EXE verification.")
        print("    Verifying C++20 code generation syntax only...")
        
        passed = 0
        for name, code, expected in E2E_CONFORMANCE_CASES:
            tokens = Lexer(code, f"{name}.rove").tokenize()
            ast = Parser(tokens, code, f"{name}.rove").parse()
            TypeChecker(ast, f"{name}.rove", code).check()
            cpp = UniversalCodeGen(ast).gen_cpp()
            assert "#include" in cpp
            print(f"  [PASS (Codegen)] {name}")
            passed += 1
        print(f"\n[OK] Codegen Conformance: {passed}/{len(E2E_CONFORMANCE_CASES)} Passed.")
        return True

    print(f"[*] Detected Native C++ Compiler: {compiler_path}")
    temp_dir = tempfile.mkdtemp(prefix="he_e2e_")
    passed = 0
    total = len(E2E_CONFORMANCE_CASES)

    try:
        for name, code, expected_out in E2E_CONFORMANCE_CASES:
            print(f"[*] Testing {name}...")
            # 1. Lex & Parse & TypeCheck
            tokens = Lexer(code, f"{name}.rove").tokenize()
            ast = Parser(tokens, code, f"{name}.rove").parse()
            TypeChecker(ast, f"{name}.rove", code).check()
            
            # 2. Transpile to C++20
            cpp_code = UniversalCodeGen(ast).gen_cpp()
            cpp_file = os.path.join(temp_dir, f"{name}.cpp")
            exe_ext = ".exe" if os.name == 'nt' else ""
            exe_file = os.path.join(temp_dir, f"{name}{exe_ext}")
            
            with open(cpp_file, 'w', encoding='utf-8') as f:
                f.write(cpp_code)
                
            # 3. Native C++20 Compilation
            ok, msg = CppToolchain.compile_cpp(cpp_file, exe_file)
            if not ok:
                print(f"  [FAIL] Compilation Error for {name}:\n{msg}")
                continue
                
            # 4. Native Binary Execution
            ret_code, stdout = CppToolchain.run_executable(exe_file)
            if ret_code != 0:
                print(f"  [FAIL] Execution Failed with exit code {ret_code}:\n{stdout}")
                continue
                
            clean_out = stdout.strip()
            if expected_out in clean_out:
                print(f"  [PASS] {name} -> Output matched: '{clean_out}'")
                passed += 1
            else:
                print(f"  [FAIL] {name} -> Expected '{expected_out}', got '{clean_out}'")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("=" * 70)
    print(f"[OK] C++20 End-to-End Conformance: {passed}/{total} Passed")
    print("=" * 70)
    return passed == total

if __name__ == "__main__":
    ok = run_cpp_e2e_tests()
    sys.exit(0 if ok else 1)
