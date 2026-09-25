import os
import sys
import tempfile
import shutil

_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from src.core.lexer import Lexer
from src.core.parser import Parser
from src.core.type_checker import TypeChecker
from src.codegen.codegen import UniversalCodeGen
from src.codegen.cpp_toolchain import CppToolchain

def run_ffi_suite() -> bool:
    print("=" * 70)
    print("⚡ ROVE PHASE 3.0 NATIVE FFI & C/C++ CORE HARNESS")
    print("=" * 70)

    compiler = CppToolchain.find_compiler()
    if not compiler:
        print("[!] Native C++ compiler not found. Skipping FFI execution suite.")
        return True

    tests = [
        (
            "ffi_01_c_stdio_puts",
            """#target cpp
#native include <stdio.h>
extern "C" fn puts(s: string) -> int

puts("nyx Native FFI: stdio.h puts call works")
""",
            "nyx Native FFI: stdio.h puts call works"
        ),
        (
            "ffi_02_c_stdlib_abs_and_memory",
            """#target cpp
#native include <stdlib.h>
extern "C" fn abs(n: int) -> int
extern "C" fn malloc(size: int) -> *void
extern "C" fn free(p: *void) -> void

var n = abs(-1337)
print("Abs:", n)
unsafe {
    var p = malloc(64)
    print("Allocated:", addr(p) > 0)
    free(p)
}
""",
            "Abs: 1337\nAllocated: true"
        ),
        (
            "ffi_03_c_math_sqrt_and_pow",
            """#target cpp
#native include <math.h>
extern "C" fn sqrt(x: float) -> float
extern "C" fn pow(base: float, exp: float) -> float

var s = sqrt(144.0)
var p = pow(2.0, 10.0)
print("Math:", s, p)
""",
            "Math: 12 1024"
        ),
        (
            "ffi_04_c_string_strlen",
            """#target cpp
#native include <string.h>
extern "C" fn strlen(s: string) -> int

var len = strlen("Hello from nyx Native FFI")
print("Strlen:", len)
""",
            "Strlen: 25"
        )
    ]

    passed = 0
    total = len(tests)

    for name, source, expected in tests:
        print(f"[*] Testing {name}...")
        try:
            tokens = Lexer(source, f"{name}.rove").tokenize()
            ast = Parser(tokens, source, f"{name}.rove").parse()
            TypeChecker(ast, f"{name}.rove", source).check()

            codegen = UniversalCodeGen(ast)
            cpp_code = codegen.gen_cpp()
            link_libs = codegen.get_link_libraries()

            temp_dir = tempfile.mkdtemp(prefix="nyx_ffi_test_")
            try:
                cpp_file = os.path.join(temp_dir, f"{name}.cpp")
                exe_file = os.path.join(temp_dir, f"{name}.exe")
                with open(cpp_file, "w", encoding="utf-8") as f:
                    f.write(cpp_code)

                ok, msg = CppToolchain.compile_cpp(cpp_file, exe_file, link_libs)
                if not ok:
                    print(f"  [FAIL] Compilation Error: {msg}")
                    continue

                code, output = CppToolchain.run_executable(exe_file)
                output = output.strip().replace("\r\n", "\n")
                if expected in output:
                    print(f"  [PASS] {name} -> Output matched")
                    passed += 1
                else:
                    print(f"  [FAIL] {name} -> Expected:\n{expected}\nGot:\n{output}")
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            print(f"  [FAIL] {name} -> Exception: {e}")

    print("=" * 70)
    print(f"[OK] Native FFI Core Suite: {passed}/{total} Passed")
    print("=" * 70)
    return passed == total

if __name__ == "__main__":
    success = run_ffi_suite()
    sys.exit(0 if success else 1)
