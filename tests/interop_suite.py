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

from src.core.lexer import Lexer
from src.core.parser import Parser
from src.core.type_checker import TypeChecker
from src.codegen.codegen import UniversalCodeGen
from src.codegen.cpp_toolchain import CppToolchain

def run_interop_suite() -> bool:
    print("=" * 70)
    print("⚡ ROVE PHASE 3.8 ADVANCED NATIVE INTEROP & C++ BRIDGE HARNESS")
    print("=" * 70)

    compiler = CppToolchain.find_compiler()
    if not compiler:
        print("[!] Native C++ compiler not found. Skipping Interop execution suite.")
        return True

    tests = [
        (
            "interop_00_documented_cpp_block",
            '''#target cpp
#native cpp {
#include <cmath>
double native_sin(double x) { return std::sin(x); }
}

extern "C++" fn native_sin(x: float) -> float

fn main() {
    print("native sin:", native_sin(0.0))
}

main()
''',
            "native sin: 0"
        ),
        (
            "interop_01_native_use",
            """#target cpp
#native include <vector>
#native use std::vector;

fn main() {
    print("Native use directive test successful")
}

main()
""",
            "Native use directive test successful"
        ),
        (
            "interop_02_function_pointer_callback_ffi",
            '''#target cpp
#native raw extern "C" int64_t execute_callback(int64_t a, int64_t b, int64_t(*cb)(int64_t, int64_t)) { return cb(a, b); }

extern "C" fn execute_callback(a: int, b: int, cb: fn(int, int) -> int) -> int

fn add_op(x: int, y: int) -> int {
    return x + y
}

fn mul_op(x: int, y: int) -> int {
    return x * y
}

fn main() {
    var res1 = execute_callback(10, 20, add_op)
    var res2 = execute_callback(5, 6, mul_op)
    print("Add callback:", res1)
    print("Mul callback:", res2)
}

main()
''',
            "Add callback: 30\nMul callback: 30"
        ),
        (
            "interop_03_raii_struct_destructor",
            """#target cpp

struct AutoResource {
    id: int
}

impl AutoResource {
    fn drop(self) {
        print("AutoResource dropped with id:", self.id)
    }
}

fn scoped_work() {
    var r = AutoResource(999)
    print("Inside scoped_work with resource:", r.id)
}

fn main() {
    print("Before scoped_work")
    scoped_work()
    print("After scoped_work")
}

main()
""",
            "Inside scoped_work with resource: 999\nAutoResource dropped with id: 999\nAfter scoped_work"
        ),
        (
            "interop_04_result_error_bridge",
            """#target cpp

fn might_fail(should_fail: bool) -> Result<int, string> {
    if should_fail {
        return Err("Operation failed intentionally")
    }
    return Ok(42)
}

fn main() {
    var r1 = might_fail(false)
    if r1.is_ok {
        print("Success:", r1.value)
    }
    
    var r2 = might_fail(true)
    if not r2.is_ok {
        print("Caught Error:", r2.error)
    }
}

main()
""",
            "Success: 42\nCaught Error: Operation failed intentionally"
        ),
        (
            "interop_05_generic_result_context",
            """#target cpp

fn metric(should_fail: bool) -> Result<float, string> {
    if should_fail {
        return Err("metric failed")
    }
    return Ok(3.5)
}

fn main() {
    var good = metric(false)
    var bad = metric(true)
    print("Metric:", good.value)
    print("Metric error:", bad.error)
}

main()
""",
            "Metric: 3.5\nMetric error: metric failed"
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

            temp_dir = tempfile.mkdtemp(prefix="nyx_interop_test_")
            try:
                cpp_file = os.path.join(temp_dir, f"{name}.cpp")
                exe_file = os.path.join(temp_dir, f"{name}.exe")
                with open(cpp_file, "w", encoding="utf-8") as f:
                    f.write(cpp_code)

                ok, msg = CppToolchain.compile_cpp(cpp_file, exe_file, link_libs)
                if not ok:
                    print(f"  [FAIL] Compilation Error: {msg}\n--- C++ Code ---\n{cpp_code}")
                    continue

                code, output = CppToolchain.run_executable(exe_file)
                output = output.strip().replace("\r\n", "\n")
                if expected in output:
                    print(f"  [PASS] {name} -> Output matched")
                    passed += 1
                else:
                    print(f"  [FAIL] {name} -> Output mismatch")
                    print(f"    Expected: {repr(expected)}")
                    print(f"    Got:      {repr(output)}")
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  [FAIL] {name} Exception: {e}")

    print("=" * 70)
    print(f"Phase 3.8 Interop Summary: {passed}/{total} Passed")
    print("=" * 70)
    return passed == total

if __name__ == "__main__":
    success = run_interop_suite()
    sys.exit(0 if success else 1)
