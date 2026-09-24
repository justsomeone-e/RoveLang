import os
import platform
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

def run_platform_suite() -> bool:
    print("=" * 70)
    print("NYX PHASE 3.5 PLATFORM ABSTRACTION HARNESS")
    print("=" * 70)

    compiler = CppToolchain.find_compiler()
    if not compiler:
        print("[!] Native C++ compiler not found. Skipping Platform execution suite.")
        return True

    host_os = "windows" if os.name == "nt" else ("macos" if sys.platform == "darwin" else "linux")
    machine = platform.machine().lower()
    host_arch = "x86_64" if machine in {"amd64", "x86_64"} else ("arm64" if machine in {"arm64", "aarch64"} else machine)

    tests = [
        (
            "plat_01_platform_info",
            """#target cpp
import "std/platform"

print("OS:", os_name())
print("Arch:", arch())
print("Is Windows:", is_windows())
""",
            f"OS: {host_os}\nArch: {host_arch}\nIs Windows: {'true' if os.name == 'nt' else 'false'}"
        ),
        (
            "plat_02_env_vars",
            """#target cpp
import "std/env"

var has_p = has_env("PATH")
print("Has PATH env:", has_p)
""",
            "Has PATH env: true"
        ),
        (
            "plat_03_process_exec",
            """#target cpp
import "std/process"

var status = exec_cmd("echo nyx_process_ok").unwrap()
print("Exec status is zero:", status == 0)
""",
            "nyx_process_ok\nExec status is zero: true"
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

            temp_dir = tempfile.mkdtemp(prefix="nyx_plat_test_")
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
    print(f"[OK] Platform Abstraction Suite: {passed}/{total} Passed")
    print("=" * 70)
    return passed == total

if __name__ == "__main__":
    success = run_platform_suite()
    sys.exit(0 if success else 1)
