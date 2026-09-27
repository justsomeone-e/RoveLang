import os
import sys
import tempfile
import shutil

_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from src.codegen.cpp_toolchain import CppToolchain

def test_static_and_shared_linking():
    temp_dir = tempfile.mkdtemp(prefix="nyx_link_test_")
    try:
        # 1. Create a C++ source file for a library
        lib_cpp = os.path.join(temp_dir, "mylib.cpp")
        with open(lib_cpp, "w", encoding="utf-8") as f:
            f.write('''
extern "C" {
    int add_numbers(int a, int b) {
        return a + b;
    }
    int multiply_numbers(int a, int b) {
        return a * b;
    }
}
''')

        # 2. Test static library generation (.a)
        lib_a = os.path.join(temp_dir, "libmylib.a")
        ok_static, msg_static = CppToolchain.compile_cpp(lib_cpp, lib_a, output_type="lib")
        assert ok_static, f"Static library compilation failed: {msg_static}"
        assert os.path.exists(lib_a), f"Static library file not found: {lib_a}"
        assert os.path.getsize(lib_a) > 0, "Static library is empty"
        print("[PASS] link_01_static_archive_creation")

        # 3. Test shared library generation (.dll / .so)
        dll_name = "mylib.dll" if os.name == 'nt' else "libmylib.so"
        lib_dll = os.path.join(temp_dir, dll_name)
        ok_shared, msg_shared = CppToolchain.compile_cpp(lib_cpp, lib_dll, output_type="shared")
        assert ok_shared, f"Shared library compilation failed: {msg_shared}"
        assert os.path.exists(lib_dll), f"Shared library file not found: {lib_dll}"
        assert os.path.getsize(lib_dll) > 0, "Shared library is empty"
        print("[PASS] link_02_shared_library_creation")

        # 4. Test object file compilation (.o)
        lib_obj = os.path.join(temp_dir, "mylib.o")
        ok_obj, msg_obj = CppToolchain.compile_cpp(lib_cpp, lib_obj, output_type="obj")
        assert ok_obj, f"Object compilation failed: {msg_obj}"
        assert os.path.exists(lib_obj), f"Object file not found: {lib_obj}"
        assert os.path.getsize(lib_obj) > 0, "Object file is empty"
        print("[PASS] link_03_object_file_creation")

        # 5. Test compiling an executable linking against the static library
        main_cpp = os.path.join(temp_dir, "main.cpp")
        main_exe = os.path.join(temp_dir, "main.exe")
        with open(main_cpp, "w", encoding="utf-8") as f:
            f.write('''
#include <iostream>
extern "C" int add_numbers(int a, int b);
extern "C" int multiply_numbers(int a, int b);

int main() {
    int sum = add_numbers(20, 22);
    int prod = multiply_numbers(6, 7);
    std::cout << "Sum: " << sum << ", Prod: " << prod << std::endl;
    return 0;
}
''')
        ok_exe, msg_exe = CppToolchain.compile_cpp(main_cpp, main_exe, link_libraries=[lib_a])
        assert ok_exe, f"Executable linking failed: {msg_exe}"
        assert os.path.exists(main_exe), f"Executable file not found: {main_exe}"

        ret, out = CppToolchain.run_executable(main_exe)
        assert ret == 0, f"Executable returned non-zero code {ret}: {out}"
        assert "Sum: 42, Prod: 42" in out, f"Executable output mismatch: {out}"
        print("[PASS] link_04_executable_linking_static_archive")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def run_linking_suite() -> bool:
    print("=" * 70)
    print("ROVE PHASE 3.4 STATIC/SHARED LINKING TEST HARNESS")
    print("=" * 70)
    try:
        test_static_and_shared_linking()
        print("=" * 70)
        print("[OK] Linking Suite: 4/4 Passed")
        print("=" * 70)
        return True
    except Exception as e:
        print(f"[FAIL] Linking Suite: {e}")
        return False

if __name__ == "__main__":
    success = run_linking_suite()
    sys.exit(0 if success else 1)
