import os
import sys
import tempfile
import shutil

_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from src.core.module_loader import ModuleLoader
from src.core.type_checker import TypeChecker
from src.codegen.codegen import UniversalCodeGen
from src.codegen.cpp_toolchain import CppToolchain

def run_native_library_suite() -> bool:
    print("=" * 70)
    print("⚡ ROVE PHASE 3.2 NATIVE LIBRARY API & STDLIB HARNESS")
    print("=" * 70)

    compiler = CppToolchain.find_compiler()
    if not compiler:
        print("[!] Native C++ compiler not found. Skipping Native Library execution suite.")
        return True

    tests = [
        (
            "lib_01_std_memory_abstraction",
            """#target cpp
import "std/memory"

var buffer = allocate(256)
print("Buffer allocated successfully:", addr(buffer) > 0)
fill_zero(buffer, 256)
release(buffer)
""",
            "Buffer allocated successfully: true"
        ),
        (
            "lib_03_std_time_sleep",
            """#target cpp
import "std/time"

sleep_ms(5)
print("Time sleep completed")
""",
            "Time sleep completed"
        )
    ]

    passed = 0
    total = len(tests)

    for name, source, expected in tests:
        print(f"[*] Testing {name}...")
        try:
            loader = ModuleLoader(base_dir=os.path.join(_root_dir, "tests"))
            ast = loader.load_program("<memory>", source)
            TypeChecker(ast, f"{name}.rove", source).check()

            codegen = UniversalCodeGen(ast)
            cpp_code = codegen.gen_cpp()
            link_libs = codegen.get_link_libraries()

            temp_dir = tempfile.mkdtemp(prefix="nyx_natlib_test_")
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
    print(f"[OK] Native Library API Suite: {passed}/{total} Passed")
    print("=" * 70)
    return passed == total

if __name__ == "__main__":
    success = run_native_library_suite()
    sys.exit(0 if success else 1)
