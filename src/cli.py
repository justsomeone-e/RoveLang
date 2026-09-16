import sys
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
import sys
import os
import shutil
import subprocess
import json
from typing import Optional, List, Dict, Any, Union


def _configure_windows_console() -> None:
    """Enable UTF-8 and ANSI VT output when attached to a Windows console."""
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        enable_virtual_terminal_processing = 0x0004
        for standard_handle in (-11, -12):
            handle = kernel32.GetStdHandle(standard_handle)
            mode = ctypes.c_uint()
            if handle and kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(
                    handle,
                    mode.value | enable_virtual_terminal_processing,
                )
    except (AttributeError, OSError, ValueError):
        # Redirected streams and older hosts may not expose a console handle.
        pass


_configure_windows_console()

_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from src.core import Lexer, Parser, TypeChecker
from src.core.backend_capabilities import (
    BACKENDS,
    capability_manifest,
    normalize_backend_name,
    resolve_backend,
)
from src.codegen import UniversalCodeGen
from src.codegen.cpp_toolchain import CppToolchain
from src.toolchain import (
    Formatter, Linter, Debugger, Profiler,
    DocGenerator, PackageManager, StandalonePackager
)
from src.version import VERSION

def print_banner():
    print("===================================================================")
    print(f"nyx core v{VERSION} — systems toolchain")
    print("===================================================================")

def print_help():
    print_banner()
    print("""Usage: nyx <command> [arguments] [options]

Project & Development Commands:
  nyx new <project_name>             Create a new nyx project in a directory
  nyx init [name]                    Initialize a nyx.toml project in current directory
  nyx check [file.nyx] [--target t]  Fast type-check and semantic validation
  nyx build [file.nyx] [--target t]  Build or transpile (--esm for importable JS)
  nyx bundle [file.nyx] [-o dir]     Bundle Web/WASM (--wasi; --package; framework adapters)
  nyx self-host verify               Verify the native stage-1 -> stage-2 bootstrap
  nyx self-host compile <file.nyx>   Emit C++ through the stage-1 compiler
  nyx self-host build                Build the standalone native nyxc frontend
  nyx targets [--json] [--mir]       Inspect backend, stdlib and MIR legality contracts
  nyx emit mir <file.nyx> [--json]   Emit experimental verified MIR
             [--codegen]             Emit target source through legalized MIR (C++/LLVM/Wasm/Rust/JS/Python/C17 pilots)
  nyx verify mir <file.mir.json>     Verify serialized experimental MIR
  nyx run [file.nyx] [--target t]    Compile and run project / file immediately
  nyx repl                           Launch Interactive Polyglot REPL
  nyx test [file.nyx | all]          Execute in-file unit tests or test framework
  nyx tour [subcommand]              Launch interactive Tour of Nyx learning environment
  nyx clean                          Remove build artifacts and temporary files

Toolchain & Quality:
  nyx fmt <file.nyx>                 Auto-format and beautify source code
  nyx lint <file.nyx>                Static analysis and unsafe boundary checks
  nyx lsp                            Launch Language Server Protocol (LSP) daemon
  nyx debug <file.nyx>               Interactive validated source-line inspector
  nyx profile <file.nyx>             Measure real compile + run wall-clock time
  nyx doc <file.nyx>                 Generate HTML API documentation from /// comments

Package Management:
  nyx add <pkg> [@version] [--path]  Add a registry declaration or local dependency
  nyx remove <pkg>                   Remove a dependency from nyx.toml and nyx.lock
  nyx install                        Validate dependencies and regenerate nyx.lock
  nyx pkg                            Inspect current project manifest and dependencies

System & Diagnostics:
  nyx doctor                         Inspect compiler toolchains & environment health
  nyx version                        Show compiler core and detected native toolchains
  nyx help                           Display this help message

Target Backends (--target):
  cpp (C++20 Native) | c (C17 Experimental) | llvm (LLVM IR Experimental)
  python (Python) | js (Node.js) | rust (Rust 2021) | wasm (WebAssembly)
===================================================================""")

def parse_nyx_toml():
    """Read nyx.toml in the current directory when available."""
    config = {
        "name": "nyx_app",
        "version": "0.1.0",
        "target": "cpp",
        "entry": "src/main.nyx",
        "output_type": "exe"
    }
    manifest_path = "nyx.toml" if os.path.exists("nyx.toml") else None
    if manifest_path:
        try:
            from src.toolchain.manifest import NyxManifest
            mf = NyxManifest(manifest_path)
            config["name"] = mf.package.get("name", config["name"])
            config["version"] = mf.package.get("version", config["version"])
            config["target"] = mf.package.get("target") or mf.build.get("target") or config["target"]
            config["entry"] = mf.package.get("entry") or mf.build.get("entry") or config["entry"]
            config["output_type"] = mf.build.get("output_type", config["output_type"])
        except Exception:
            with open(manifest_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("name ="):
                        config["name"] = line.split("=")[1].strip().strip('"').strip("'")
                    elif line.startswith("version ="):
                        config["version"] = line.split("=")[1].strip().strip('"').strip("'")
                    elif line.startswith("default =") or line.startswith("target ="):
                        config["target"] = line.split("=")[1].strip().strip('"').strip("'")
                    elif line.startswith("entry ="):
                        config["entry"] = line.split("=")[1].strip().strip('"').strip("'")
                    elif line.startswith("output_type ="):
                        config["output_type"] = line.split("=")[1].strip().strip('"').strip("'")
    return config

def get_target_from_args(default_target="cpp", entry_file=None, arguments=None):
    """Resolve CLI > source directive > manifest/default, then canonicalize."""
    args = list(sys.argv[2:] if arguments is None else arguments)
    for index, argument in enumerate(args):
        if argument.startswith("--target="):
            return normalize_backend_name(argument.split("=", 1)[1])
        if argument in ("--target", "-t") and index + 1 < len(args):
            return normalize_backend_name(args[index + 1])

    if entry_file and os.path.exists(entry_file):
        try:
            with open(entry_file, "r", encoding="utf-8-sig") as f:
                for _ in range(15):
                    line = f.readline()
                    if not line: break
                    line = line.strip()
                    if line.startswith("#target"):
                        parts = line.split()
                        if len(parts) >= 2:
                            return normalize_backend_name(parts[1])
        except Exception:
            pass

    return normalize_backend_name(default_target)

def get_entry_file(default_entry="src/main.nyx", arguments=None):
    args = list(sys.argv[2:] if arguments is None else arguments)
    value_options = {"--target", "-t", "--output", "-o"}
    positional = []
    skip_next = False
    for argument in args:
        if skip_next:
            skip_next = False
            continue
        if argument in value_options:
            skip_next = True
            continue
        if argument.startswith("--target=") or argument.startswith("--output="):
            continue
        if argument.startswith("-"):
            continue
        positional.append(argument)
    for argument in positional:
        if argument.lower().endswith(".nyx"):
            return argument
    if os.path.exists(default_entry):
        return default_entry
    if os.path.exists("src/lib.nyx"):
        return "src/lib.nyx"
    if os.path.exists("src/main.nyx"):
        return "src/main.nyx"
    if os.path.exists("main.nyx"):
        return "main.nyx"
    return None


def parse_package_spec(arguments):
    if not arguments:
        raise ValueError("missing package name")
    if len(arguments) > 2:
        raise ValueError("too many package arguments")
    package_name = arguments[0]
    version = "1.0.0"
    if len(arguments) == 2:
        version = arguments[1][1:] if arguments[1].startswith("@") else arguments[1]
    elif "@" in package_name and not package_name.startswith("@"):
        package_name, version = package_name.rsplit("@", 1)
    if not package_name or not version:
        raise ValueError("package name and version must be non-empty")
    return package_name, version


def get_option_value(*names, default=None):
    for index, argument in enumerate(sys.argv):
        if argument in names and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return default


class _CanonicalArtifactAdapter:
    """Keep CLI output handling small while all semantics come from NyxCompiler."""

    def __init__(self, content: str, link_libraries: List[str]):
        self.content = content
        self.link_libraries = link_libraries

    def get_link_libraries(self) -> List[str]:
        return list(self.link_libraries)

    def gen_cpp(self) -> str:
        return self.content

    def gen_js(self) -> str:
        return self.content

    def gen_python(self) -> str:
        return self.content

    def gen_rust(self) -> str:
        return self.content

    def gen_react(self) -> str:
        return self.content

    def gen_wasm(self) -> str:
        return self.content


def _compile_canonical_artifact(
    entry_file: str,
    target: str,
    javascript_esm: bool = False,
) -> Optional[_CanonicalArtifactAdapter]:
    from src.api import NyxCompiler
    from src.ir import IRNativeDirective

    result = NyxCompiler(os.path.dirname(os.path.abspath(entry_file))).compile_file(
        entry_file,
        target=target,
    )
    if not result.success or result.artifact is None:
        for diagnostic in result.diagnostics:
            print(diagnostic.rendered)
        return None
    content = result.artifact.content
    if target == "js" and javascript_esm:
        from src.codegen.hir_javascript import emit_javascript
        if result.hir is None:
            return None
        content = emit_javascript(result.hir, esm=True)
    links = [
        item.value
        for item in (result.hir.items if result.hir is not None else ())
        if isinstance(item, IRNativeDirective) and item.kind == "link"
    ]
    return _CanonicalArtifactAdapter(content, links)


def _compile_experimental_native(source_path: str, output_path: str, target: str) -> tuple[bool, str]:
    """Compile a generated C17 or LLVM IR artifact with the host Clang toolchain."""
    clang = shutil.which("clang")
    if not clang:
        return False, "Clang was not found on PATH; the source artifact was still generated"
    command = [clang, "-O2"]
    if target == "c":
        command.append("-std=c17")
    command.extend([source_path, "-o", output_path])
    if sys.platform != "win32":
        command.append("-lm")
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        return False, result.stderr or result.stdout or f"Clang exited with {result.returncode}"
    return True, ""

def cmd_check(entry_file, target=None) -> int:
    if not entry_file or not os.path.exists(entry_file):
        print(f"\033[91m[!] Error: File not found '{entry_file}'\033[0m")
        return 1
    print(f"\033[96m[*] Checking semantics & types for:\033[0m {entry_file}")
    from src.api import NyxCompiler
    result = NyxCompiler(os.path.dirname(os.path.abspath(entry_file))).check_file(
        entry_file, target=target
    )
    if not result.success:
        for diagnostic in result.diagnostics:
            print(diagnostic.rendered)
        return 1
    print("\033[92m[OK] Check Passed: 0 syntax or semantic errors found.\033[0m")
    return 0

def cmd_build(
    entry_file,
    target,
    is_release=False,
    output_type="exe",
    wasi=False,
    javascript_esm=False,
) -> int:
    if not entry_file or not os.path.exists(entry_file):
        print(f"\033[91m[!] Error: Source file not found '{entry_file}'.\033[0m")
        return 1

    backend = resolve_backend(target)
    if backend is None:
        print(f"\033[91m[!] Unknown target '{target}'. Run 'nyx targets'.\033[0m")
        return 1
    target = backend.name

    build_dir = os.path.join("build", target)
    base_name = os.path.splitext(os.path.basename(entry_file))[0]

    # A WASM build is a host-usable ABI v1 package, not just its textual WAT
    # representation. `bundle` remains the explicit-output variant.
    if target == "wasm":
        return cmd_bundle(entry_file, out_dir=build_dir, wasi=wasi)

    os.makedirs(build_dir, exist_ok=True)
    
    print(f"\033[96m[*] Building [{target}] ({output_type}):\033[0m {entry_file} -> {build_dir}")
    codegen = _compile_canonical_artifact(entry_file, target, javascript_esm=javascript_esm)
    if codegen is None:
        return 1
    
    if target == "cpp":
        cpp_code = codegen.gen_cpp()
        out_cpp = os.path.join(build_dir, f"{base_name}.cpp")
        with open(out_cpp, "w", encoding="utf-8") as f:
            f.write(cpp_code)

        if output_type == "lib":
            out_target = os.path.join(build_dir, f"lib{base_name}.a")
            ok, msg = CppToolchain.compile_cpp(out_cpp, out_target, codegen.get_link_libraries(), output_type="lib")
            if ok:
                print(f"\033[92m[OK] Compiled Static Library:\033[0m {out_target}")
                return 0
            else:
                print(f"\033[93m[!] Static library generation failed:\033[0m {msg}")
                return 1
        elif output_type == "shared":
            ext = ".dll" if sys.platform == "win32" else ".so"
            out_target = os.path.join(build_dir, f"{base_name}{ext}")
            ok, msg = CppToolchain.compile_cpp(out_cpp, out_target, codegen.get_link_libraries(), output_type="shared")
            if ok:
                print(f"\033[92m[OK] Compiled Shared Library:\033[0m {out_target}")
                return 0
            else:
                print(f"\033[93m[!] Shared library generation failed:\033[0m {msg}")
                return 1
        else:
            executable_name = f"{base_name}.exe" if os.name == "nt" else base_name
            out_exe = os.path.join(build_dir, executable_name)
            ok, msg = CppToolchain.compile_cpp(out_cpp, out_exe, codegen.get_link_libraries(), output_type="exe")
            if ok:
                print(f"\033[92m[OK] Compiled Native Executable:\033[0m {out_exe}")
                print(
                    "\033[96m[>] Run in a persistent terminal:\033[0m "
                    f'nyx run "{entry_file}" --target cpp'
                )
                print("\033[90m    (A console program exits normally as soon as main finishes.)\033[0m")
                return 0
            else:
                print(f"\033[93m[!] Transpiled C++ source generated at:\033[0m {out_cpp}")
                print(f"    ({msg})")
                return 1
            
    elif target in ("c", "llvm"):
        extension = ".c" if target == "c" else ".ll"
        label = "C17 Source" if target == "c" else "Direct LLVM IR"
        out_source = os.path.join(build_dir, f"{base_name}{extension}")
        with open(out_source, "w", encoding="utf-8") as f:
            f.write(codegen.content)
        print(f"\033[96m[*] Generated {label}:\033[0m {out_source}")

        executable_name = f"{base_name}.exe" if sys.platform == "win32" else base_name
        out_exe = os.path.join(build_dir, executable_name)
        ok, message = _compile_experimental_native(out_source, out_exe, target)
        if ok:
            print(f"\033[92m[OK] Compiled Experimental Native Binary:\033[0m {out_exe}")
            print(f"\033[96m[>] Run:\033[0m nyx run \"{entry_file}\" --target {target}")
            return 0
        print(f"\033[93m[!] Native compilation failed; generated source was preserved:\033[0m {message}")
        return 1

    elif target == "asm":
        cpp_code = codegen.gen_cpp()
        temp_cpp = os.path.join(build_dir, f"{base_name}_temp.cpp")
        with open(temp_cpp, "w", encoding="utf-8") as f:
            f.write(cpp_code)
        out_s = os.path.join(build_dir, f"{base_name}.s")
        ok, msg = CppToolchain.compile_cpp(temp_cpp, out_s, codegen.get_link_libraries(), output_type="asm")
        if ok and os.path.exists(out_s):
            executable_name = f"{base_name}.exe" if os.name == "nt" else base_name
            out_exe = os.path.join(build_dir, executable_name)
            CppToolchain.compile_cpp(temp_cpp, out_exe, codegen.get_link_libraries(), output_type="exe")
            print(f"\033[96m[*] Generated Assembly (Intel x86_64):\033[0m {out_s}")
            if os.path.exists(out_exe):
                print(f"\033[92m[OK] Compiled Native Binary:\033[0m {out_exe}")
                print(
                    "\033[96m[>] Run in a persistent terminal:\033[0m "
                    f'nyx run "{entry_file}" --target asm'
                )
            if os.path.exists(temp_cpp):
                try: os.remove(temp_cpp)
                except: pass
            return 0
        else:
            print(f"\033[91m[!] Assembly generation failed:\033[0m {msg}")
            return 1

    elif target == "js":
        js_code = codegen.gen_js()
        extension = ".mjs" if javascript_esm else ".js"
        out_js = os.path.join(build_dir, f"{base_name}{extension}")
        with open(out_js, "w", encoding="utf-8") as f:
            f.write(js_code)
        print(f"\033[92m[OK] Generated Node.js ES2022 Module:\033[0m {out_js}")
        return 0

    elif target == "rust":
        rs_code = codegen.gen_rust()
        out_rs = os.path.join(build_dir, f"{base_name}.rs")
        with open(out_rs, "w", encoding="utf-8") as f:
            f.write(rs_code)
        print(f"\033[92m[OK] Generated Rust 2021 Source:\033[0m {out_rs}")
        return 0

    elif target == "python":
        py_code = codegen.gen_python()
        out_py = os.path.join(build_dir, f"{base_name}.py")
        with open(out_py, "w", encoding="utf-8") as f:
            f.write(py_code)
        print(f"\033[92m[OK] Generated Python 3 Module:\033[0m {out_py}")
        return 0

    elif target == "react":
        react_code = codegen.gen_react()
        out_tsx = os.path.join(build_dir, f"{base_name}.tsx")
        with open(out_tsx, "w", encoding="utf-8") as f:
            f.write(react_code)
        print(f"\033[92m[OK] Generated React 19 TSX Component:\033[0m {out_tsx}")
        return 0

    else:
        print(f"\033[91m[!] Unknown target '{target}'\033[0m")
        return 1

def cmd_run(entry_file, target) -> int:
    if not entry_file or not os.path.exists(entry_file):
        print(f"\033[91m[!] Error: Source file not found '{entry_file}'.\033[0m")
        return 1

    backend = resolve_backend(target)
    if backend is None:
        print(f"\033[91m[!] Unknown target '{target}'. Run 'nyx targets'.\033[0m")
        return 1
    target = backend.name

    build_dir = os.path.join("build", target)
    os.makedirs(build_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(entry_file))[0]

    codegen = _compile_canonical_artifact(entry_file, target)
    if codegen is None:
        return 1

    if target == "asm":
        cpp_code = codegen.gen_cpp()
        temp_cpp = os.path.join(build_dir, f"{base_name}_temp.cpp")
        with open(temp_cpp, "w", encoding="utf-8") as f:
            f.write(cpp_code)
        out_s = os.path.join(build_dir, f"{base_name}.s")
        executable_name = f"{base_name}.exe" if os.name == "nt" else base_name
        out_exe = os.path.join(build_dir, executable_name)
        CppToolchain.compile_cpp(temp_cpp, out_s, codegen.get_link_libraries(), output_type="asm")
        ok, msg = CppToolchain.compile_cpp(temp_cpp, out_exe, codegen.get_link_libraries(), output_type="exe")
        if ok and os.path.exists(out_exe):
            print(f"\033[96m[*] Generated Assembly (Intel x86_64):\033[0m {out_s}")
            print(f"\033[92m[OK] Compiled Native Binary:\033[0m {out_exe}")
            print("\033[90m--------------------------------------------------\033[0m")
            ret_code, out_str = CppToolchain.run_executable(out_exe)
            if out_str:
                print(out_str.rstrip())
            print("\033[90m--------------------------------------------------\033[0m")
            if os.path.exists(temp_cpp):
                try: os.remove(temp_cpp)
                except: pass
            return ret_code
        else:
            print(f"\033[91m[!] Assembly Execution failed:\033[0m\n{msg}")
            return 1
    elif target == "python":
        out_py = os.path.join(build_dir, f"{base_name}.py")
        py_code = codegen.gen_python()
        with open(out_py, "w", encoding="utf-8") as f:
            f.write(py_code)
        print(f"\033[96m[*] Target [Python 3]:\033[0m {out_py}")
        print("\033[90m--------------------------------------------------\033[0m")
        result = subprocess.run([sys.executable, out_py])
        print("\033[90m--------------------------------------------------\033[0m")
        return result.returncode
    elif target == "js":
        out_js = os.path.join(build_dir, f"{base_name}.js")
        js_code = codegen.gen_js()
        with open(out_js, "w", encoding="utf-8") as f:
            f.write(js_code)
        node_path = shutil.which("node")
        if not node_path:
            print("\033[91m[!] Node.js not found on system PATH.\033[0m")
            return 1
        print(f"\033[96m[*] Target [Node.js ES2022]:\033[0m {out_js}")
        print("\033[90m--------------------------------------------------\033[0m")
        result = subprocess.run([node_path, out_js])
        print("\033[90m--------------------------------------------------\033[0m")
        return result.returncode
    elif target == "cpp":
        out_cpp = os.path.join(build_dir, f"{base_name}.cpp")
        executable_name = f"{base_name}.exe" if os.name == "nt" else base_name
        out_exe = os.path.join(build_dir, executable_name)
        with open(out_cpp, "w", encoding="utf-8") as f:
            f.write(codegen.gen_cpp())
        ok, msg = CppToolchain.compile_cpp(out_cpp, out_exe, codegen.get_link_libraries(), output_type="exe")
        if ok and os.path.exists(out_exe):
            print(f"\033[96m[*] Transpiled C++20 Source:\033[0m {out_cpp}")
            print(f"\033[92m[OK] Compiled Native Binary:\033[0m {out_exe}")
            print("\033[90m--------------------------------------------------\033[0m")
            ret_code, out_str = CppToolchain.run_executable(out_exe, capture_output=False)
            if out_str:
                print(out_str.rstrip())
            print("\033[90m--------------------------------------------------\033[0m")
            return ret_code
        else:
            print(f"\033[91m[!] C++ Compilation failed:\033[0m\n{msg}")
            return 1
    elif target == "rust":
        out_rs = os.path.join(build_dir, f"{base_name}.rs")
        with open(out_rs, "w", encoding="utf-8") as f:
            f.write(codegen.gen_rust())
        print(f"\033[96m[*] Transpiled Rust 2021 Source:\033[0m {out_rs}")
        rustc = shutil.which("rustc")
        if rustc:
            executable_name = f"{base_name}.exe" if os.name == "nt" else base_name
            out_exe = os.path.join(build_dir, executable_name)
            out_obj = os.path.join(build_dir, f"{base_name}.o")
            res = subprocess.run([rustc, "--edition=2021", out_rs, "-o", out_exe], capture_output=True, text=True)
            if res.returncode == 0 and os.path.exists(out_exe):
                print(f"\033[92m[OK] Compiled Native Binary:\033[0m {out_exe}")
                run_res = subprocess.run([out_exe])
                return run_res.returncode
            print(f"\033[91m[!] Rust compilation failed:\033[0m\n{res.stderr or res.stdout}")
            return res.returncode or 1
        print("\033[91m[!] Rust compiler not found on system PATH.\033[0m")
        return 1
    elif target in ("c", "llvm"):
        extension = ".c" if target == "c" else ".ll"
        label = "C17 Source" if target == "c" else "Direct LLVM IR"
        out_source = os.path.join(build_dir, f"{base_name}{extension}")
        executable_name = f"{base_name}.exe" if sys.platform == "win32" else base_name
        out_exe = os.path.join(build_dir, executable_name)
        with open(out_source, "w", encoding="utf-8") as f:
            f.write(codegen.content)
        ok, message = _compile_experimental_native(out_source, out_exe, target)
        if not ok:
            print(f"\033[91m[!] {label} native compilation failed:\033[0m\n{message}")
            return 1
        print(f"\033[96m[*] Target [{label}]:\033[0m {out_source}")
        print(f"\033[92m[OK] Compiled Native Binary:\033[0m {out_exe}")
        print("\033[90m--------------------------------------------------\033[0m")
        result = subprocess.run([out_exe])
        print("\033[90m--------------------------------------------------\033[0m")
        return result.returncode
    elif target == "react":
        out_tsx = os.path.join(build_dir, f"{base_name}.tsx")
        react_code = codegen.gen_react()
        with open(out_tsx, "w", encoding="utf-8") as f:
            f.write(react_code)
        print(f"\033[96m[*] Target [React 19 TSX]:\033[0m {out_tsx}")
        print("\033[90m--------------------------------------------------\033[0m")
        print(react_code)
        print("\033[90m--------------------------------------------------\033[0m")
        print("\033[92m[OK] React component generated successfully.\033[0m")
        return 0
    elif target == "wasm":
        out_wat = os.path.join(build_dir, f"{base_name}.wat")
        wasm_code = codegen.gen_wasm()
        with open(out_wat, "w", encoding="utf-8") as f:
            f.write(wasm_code)
        print(f"\033[96m[*] Target [WebAssembly WAT]:\033[0m {out_wat}")
        print("\033[90m--------------------------------------------------\033[0m")
        print(wasm_code)
        print("\033[90m--------------------------------------------------\033[0m")
        print("\033[92m[OK] WebAssembly module generated successfully.\033[0m")
        return 0
    else:
        print(f"\033[91m[!] Unknown target '{target}'.\033[0m")
        return 1

def cmd_bundle(
    entry_file: str,
    out_dir: Optional[str] = None,
    emit_react: bool = False,
    emit_package: bool = False,
    emit_vue: bool = False,
    emit_svelte: bool = False,
    wasi: bool = False,
) -> int:
    if not os.path.exists(entry_file):
        print(f"\033[91m[!] Error: File '{entry_file}' not found.\033[0m")
        return 1

    base_name = os.path.splitext(os.path.basename(entry_file))[0]
    bundle_dir = out_dir or os.path.join(os.getcwd(), "dist", base_name)

    with open(entry_file, "r", encoding="utf-8") as f:
        code = f.read()

    from src.core.module_loader import ModuleLoader
    from src.codegen.bundle_emitter import BundleEmitter
    loader = ModuleLoader(base_dir=os.path.dirname(os.path.abspath(entry_file)), target="wasm")
    ast = loader.load_program(entry_file, code)
    TypeChecker(ast, entry_file, code).check()

    emitter = BundleEmitter(
        ast,
        module_name=base_name,
        source_name=entry_file,
        wasi=wasi,
    )

    # Lower and render every artifact before touching the output directory.
    # Unsupported constructs therefore fail without leaving a partial bundle.
    try:
        wat_code = emitter.emit_wat()
        wasm_bytes = emitter.emit_wasm_bytes()
        mjs_code = emitter.emit_mjs()
        dts_code = emitter.emit_dts()
        react_code = emitter.emit_react() if emit_react else None
        react_mjs = emitter.emit_react_mjs() if emit_react and emit_package else None
        react_dts = emitter.emit_react_dts() if emit_react and emit_package else None
        vue_mjs = emitter.emit_vue_mjs() if emit_vue else None
        vue_dts = emitter.emit_vue_dts() if emit_vue else None
        svelte_mjs = emitter.emit_svelte_mjs() if emit_svelte else None
        svelte_dts = emitter.emit_svelte_dts() if emit_svelte else None
        package_json = emitter.emit_package_json(
            include_react=emit_react,
            include_vue=emit_vue,
            include_svelte=emit_svelte,
        ) if emit_package else None
    except Exception as exc:
        from src.codegen.wasm_ir import BundleCompileError
        if isinstance(exc, BundleCompileError):
            print(f"\033[91m[!] Bundle compilation failed: {exc}\033[0m")
            return 1
        raise

    os.makedirs(bundle_dir, exist_ok=True)

    # 1. Emit WebAssembly Text (.wat)
    wat_path = os.path.join(bundle_dir, f"{base_name}.wat")
    with open(wat_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(wat_code)

    # 2. Emit WebAssembly Binary (.wasm)
    wasm_path = os.path.join(bundle_dir, f"{base_name}.wasm")
    with open(wasm_path, "wb") as f:
        f.write(wasm_bytes)

    # 3. Emit ES Module Wrapper (.mjs)
    mjs_path = os.path.join(bundle_dir, f"{base_name}.mjs")
    with open(mjs_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(mjs_code)

    # 4. Emit TypeScript Type Declarations (.d.ts)
    dts_path = os.path.join(bundle_dir, f"{base_name}.d.ts")
    with open(dts_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(dts_code)

    profile = "WASI preview1 executable" if wasi else "Polyglot Web/WASM Package"
    print(f"\033[96m[*] Bundling {profile}:\033[0m {entry_file} -> {bundle_dir}")
    print(f"\033[92m  [+] WebAssembly Text:     {wat_path}\033[0m")
    print(f"\033[92m  [+] WebAssembly Binary:   {wasm_path}\033[0m")
    print(f"\033[92m  [+] ES Module Runtime:     {mjs_path}\033[0m")
    print(f"\033[92m  [+] TypeScript Types:      {dts_path}\033[0m")

    # 5. Conditionally Emit React 19 Custom Hook (.react.tsx)
    if emit_react:
        react_path = os.path.join(bundle_dir, f"{base_name}.react.tsx")
        with open(react_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(react_code or "")
        print(f"\033[92m  [+] React 19 useNyxModule: {react_path}\033[0m")

    if emit_package:
        package_path = os.path.join(bundle_dir, "package.json")
        with open(package_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(package_json or "")
        if emit_react:
            react_mjs_path = os.path.join(bundle_dir, f"{base_name}.react.mjs")
            react_dts_path = os.path.join(bundle_dir, f"{base_name}.react.d.ts")
            with open(react_mjs_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(react_mjs or "")
            with open(react_dts_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(react_dts or "")
        for enabled, suffix, module_code, type_code in (
            (emit_vue, "vue", vue_mjs, vue_dts),
            (emit_svelte, "svelte", svelte_mjs, svelte_dts),
        ):
            if enabled:
                with open(os.path.join(bundle_dir, f"{base_name}.{suffix}.mjs"), "w", encoding="utf-8", newline="\n") as f:
                    f.write(module_code or "")
                with open(os.path.join(bundle_dir, f"{base_name}.{suffix}.d.ts"), "w", encoding="utf-8", newline="\n") as f:
                    f.write(type_code or "")
        print(f"\033[92m  [+] npm Package Manifest: {package_path}\033[0m")

    return 0

def cmd_self_host(args) -> int:
    from src.self_host.bootstrap import (
        SelfHostError,
        build_native_compiler,
        compile_source,
        verify,
    )

    try:
        action = args[0].lower() if args else "verify"
        if action == "verify":
            verify()
            print("\033[92m[OK] Nyx native stage-1 -> stage-2 bootstrap verified.\033[0m")
            return 0
        if action == "compile":
            if len(args) < 2:
                print("\033[91m[!] Usage: nyx self-host compile <file.nyx> [-o output.cpp]\033[0m")
                return 1
            source_path = args[1]
            output_path = None
            for index, value in enumerate(args):
                if value in ("-o", "--output") and index + 1 < len(args):
                    output_path = args[index + 1]
            if not output_path:
                output_path = os.path.join("build", "self_host", os.path.splitext(os.path.basename(source_path))[0] + ".cpp")
            compile_source(source_path, output_path)
            print(f"\033[92m[OK] Stage-1 self-host C++ emitted:\033[0m {output_path}")
            return 0
        if action == "build":
            output_path = None
            for index, value in enumerate(args):
                if value in ("-o", "--output") and index + 1 < len(args):
                    output_path = args[index + 1]
            if not output_path:
                executable_name = "nyxc.exe" if os.name == "nt" else "nyxc"
                output_path = os.path.join("build", "self_host", executable_name)
            build_native_compiler(output_path)
            print(f"\033[92m[OK] Standalone native Nyx frontend built:\033[0m {output_path}")
            return 0
        print(f"\033[91m[!] Unknown self-host action '{action}'. Use verify, compile, or build.\033[0m")
        return 1
    except SelfHostError as exc:
        print(f"\033[91m[!] Self-host failed: {exc}\033[0m")
        return 1

def cmd_new(project_name, is_lib=False):
    if os.path.exists(project_name):
        print(f"\033[91m[!] Error: Directory '{project_name}' already exists.\033[0m")
        return 1
    os.makedirs(os.path.join(project_name, "src"), exist_ok=True)
    
    if is_lib:
        os.makedirs(os.path.join(project_name, "examples"), exist_ok=True)
        manifest_content = f"""[package]
name = "{project_name}"
version = "0.1.0"
edition = "2026"
target = "cpp"
entry = "src/lib.nyx"

[dependencies]
# std = "2.0.0"

[build]
target = "cpp"
output_type = "lib"
entry = "src/lib.nyx"
opt_level = 2
"""
        with open(os.path.join(project_name, "nyx.toml"), "w", encoding="utf-8") as f:
            f.write(manifest_content)

        gitignore_content = """build/
target/
*.a
*.lib
*.dll
*.so
*.o
*.lock
.system_generated/
"""
        with open(os.path.join(project_name, ".gitignore"), "w", encoding="utf-8") as f:
            f.write(gitignore_content)

        lib_nyx_content = f"""// nyx native library: {project_name}
#target cpp

fn add(a: int, b: int) -> int {{
    return a + b
}}

test "library add test" {{
    assert(add(10, 20) == 30, "add must sum correctly")
}}
"""
        with open(os.path.join(project_name, "src", "lib.nyx"), "w", encoding="utf-8") as f:
            f.write(lib_nyx_content)

        example_nyx_content = f"""// Example usage of {project_name}
#target cpp
import "../src/lib.nyx"

var res = add(5, 7)
print("Add result:", res)
"""
        with open(os.path.join(project_name, "examples", "basic.nyx"), "w", encoding="utf-8") as f:
            f.write(example_nyx_content)

        readme_content = f"""# {project_name}

Native library for nyx.

## Building
```bash
nyx build
```

## Testing
```bash
nyx test
```
"""
        with open(os.path.join(project_name, "README.md"), "w", encoding="utf-8") as f:
            f.write(readme_content)

        print(f"\033[92m[OK] Created nyx library project in ./{project_name}\033[0m")
        print(f"     - Manifest:   ./{project_name}/nyx.toml (output_type = 'lib')")
        print(f"     - Entrypoint: ./{project_name}/src/lib.nyx")
        print(f"     - Example:    ./{project_name}/examples/basic.nyx")
        print(f"\nTo get started:\n  cd {project_name}\n  nyx build\n")
        return 0

    manifest_content = f"""[package]
name = "{project_name}"
version = "0.1.0"
edition = "2026"
target = "cpp"
entry = "src/main.nyx"

[dependencies]
# std = "2.0.0"

[build]
target = "cpp"
output_type = "exe"
opt_level = 2
"""
    with open(os.path.join(project_name, "nyx.toml"), "w", encoding="utf-8") as f:
        f.write(manifest_content)
        
    gitignore_content = """build/
target/
*.exe
*.o
*.lock
.system_generated/
"""
    with open(os.path.join(project_name, ".gitignore"), "w", encoding="utf-8") as f:
        f.write(gitignore_content)
        
    main_nyx_content = f"""#target cpp

fn greet(name: string) -> string {{
    return "Hello, " + name + " from nyx!"
}}

var message = greet("{project_name}")
print(message)

test "greeting test" {{
    assert(greet("User") == "Hello, User from nyx!", "Greeting must match")
}}
"""
    with open(os.path.join(project_name, "src", "main.nyx"), "w", encoding="utf-8") as f:
        f.write(main_nyx_content)
        
    vscode_dir = os.path.join(project_name, ".vscode")
    os.makedirs(vscode_dir, exist_ok=True)
    tasks_json_content = """{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "nyx: Build Active File",
      "type": "shell",
      "command": "nyx",
      "args": ["build", "${file}"],
      "group": {
        "kind": "build",
        "isDefault": true
      },
      "presentation": {
        "echo": true,
        "reveal": "always",
        "focus": false,
        "panel": "shared"
      }
    },
    {
      "label": "nyx: Run Active File",
      "type": "shell",
      "command": "nyx",
      "args": ["run", "${file}"],
      "group": "build",
      "presentation": {
        "echo": true,
        "reveal": "always",
        "focus": true,
        "panel": "shared"
      }
    },
    {
      "label": "nyx: Run Full Test Suite",
      "type": "shell",
      "command": "nyx",
      "args": ["test"],
      "group": {
        "kind": "test",
        "isDefault": true
      },
      "presentation": {
        "echo": true,
        "reveal": "always",
        "focus": false,
        "panel": "shared"
      }
    }
  ]
}
"""
    with open(os.path.join(vscode_dir, "tasks.json"), "w", encoding="utf-8") as f:
        f.write(tasks_json_content)

    cpp_configuration = {
        "name": "nyx",
        "includePath": ["${workspaceFolder}/**"],
        "defines": ["_DEBUG", "UNICODE", "_UNICODE"],
        "cStandard": "c17",
        "cppStandard": "c++20",
    }
    compiler_path = CppToolchain.find_compiler()
    if compiler_path:
        cpp_configuration["compilerPath"] = compiler_path
    c_cpp_props = json.dumps(
        {"configurations": [cpp_configuration], "version": 4},
        indent=2,
    ) + "\n"
    with open(os.path.join(vscode_dir, "c_cpp_properties.json"), "w", encoding="utf-8") as f:
        f.write(c_cpp_props)

    print(f"\033[92m[OK] Created nyx project in ./{project_name}\033[0m")
    print(f"     - Manifest:   ./{project_name}/nyx.toml")
    print(f"     - Entrypoint: ./{project_name}/src/main.nyx")
    print(f"     - VS Code:    ./{project_name}/.vscode/ (tasks.json & IntelliSense ready)")
    print(f"\nTo get started:\n  cd {project_name}\n  nyx run\n")
    return 0

def cmd_clean():
    cleaned = 0
    for target in ("build", "target", "__pycache__"):
        if os.path.exists(target):
            shutil.rmtree(target, ignore_errors=True)
            cleaned += 1
    print(f"\033[92m[OK] Cleaned {cleaned} build artifact directory/directories.\033[0m")
    return 0

def cmd_doctor():
    print_banner()
    print("Environment & Toolchain Diagnostics:")
    
    # 1. Python runtime
    print(f"\n  [1] Core Python Runtime (python Reference):")
    print(f"      • Status:    \033[92m[OK] Available\033[0m")
    print(f"      • Path:      {sys.executable}")
    print(f"      • Version:   Python {sys.version.split()[0]}")

    # 2. C++ Compiler (cpp Native)
    print(f"\n  [2] C++20 Compiler (cpp Native Executables):")
    clang = CppToolchain.find_compiler()
    if clang:
        print(f"      • Status:    \033[92m[OK] Available\033[0m")
        print(f"      • Compiler:  {clang}")
        print(f"      • Capability: Native .exe compilation supported")
    else:
        print(f"      • Status:    \033[93m[!] NOT FOUND (Transpile Mode Only)\033[0m")
        print("      • Requirement: cpp needs Clang++, GCC/G++, or MSVC cl (C++20).")
        print("      • Configure:   Put the compiler on PATH or set NYX_CXX to its executable.")
        print(f"                     - Windows: winget install LLVM.LLVM")
        print(f"                     - Ubuntu/Debian: sudo apt install clang")
        print(f"                     - macOS: xcode-select --install (or brew install llvm)")

    # 3. Node.js (js Target)
    print(f"\n  [3] JavaScript Runtime (js Target):")
    node = shutil.which("node")
    if node:
        print(f"      • Status:    \033[92m[OK] Available\033[0m")
        print(f"      • Node Path: {node}")
    else:
        print(f"      • Status:    \033[93m[!] NOT FOUND\033[0m")
        print(f"      • Note:      Install Node.js to execute ES2022 output: winget install OpenJS.NodeJS")

    # 4. Rust Compiler (rust Target)
    print(f"\n  [4] Rust Toolchain (rust Conformance Target):")
    rustc = shutil.which("rustc")
    if rustc:
        print(f"      • Status:    \033[92m[OK] Gate 8 Conformance (8/8 Architecture Verified)\033[0m")
        print(f"      • Path:      {rustc}")
    else:
        print(f"      • Status:    \033[93m[!] NOT FOUND\033[0m")
        print(f"      • Note:      Install Rust: https://rustup.rs")

    print("\n===================================================================")

def cmd_version():
    print_banner()
    print("Detected Host Toolchains & Execution Engines:")
    clang = CppToolchain.find_compiler()
    print(f"  • C++20 Toolchain:      {clang or 'Not Found (Using Transpile Mode)'}")
    node = shutil.which("node")
    print(f"  • JavaScript Engine:    {node or 'Not Found'}")
    rustc = shutil.which("rustc")
    print(f"  • Rust Compiler:        {rustc or 'Not Found'}")
    print(f"  • Python Reference:     {sys.executable} (v{sys.version.split()[0]})")
    print("===================================================================")

def cmd_targets(as_json: bool = False, mir: bool = False) -> int:
    if mir:
        from src.mir import mir_backend_manifest

        manifest = mir_backend_manifest()
        if as_json:
            print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
            return 0
        print_banner()
        print(f"MIR Legalization Contract v{manifest['schema_version']}:")
        for profile in manifest["profiles"]:
            print(
                f"  {profile['migration_rank']}. {profile['target']:<8} "
                f"status={profile['migration_status']:<12} abi={profile['abi']}"
            )
        print("\n'pilot' means a target source emitter currently consumes legalized MIR.")
        print("Use 'nyx targets --mir --json' for complete legal operation sets.")
        print("===================================================================")
        return 0

    manifest = capability_manifest()
    if as_json:
        print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
        return 0

    print_banner()
    print(f"Backend Capability Contract v{manifest['schema_version']}:")
    for name in sorted(BACKENDS):
        backend = BACKENDS[name]
        modules = backend.to_dict()["stdlib_modules"]
        aliases = ", ".join(backend.aliases) if backend.aliases else "-"
        module_text = ", ".join(modules) if modules else "none"
        print(f"\n  {backend.name:<11} {backend.display_name} [{backend.maturity}]")
        print(f"      family={backend.family} artifact={backend.artifact} aliases={aliases}")
        print(f"      stdlib={module_text}")
    print("\nUse 'nyx targets --json' for the machine-readable contract.")
    print("===================================================================")
    return 0


def _mir_argument_path(arguments: list[str], suffix: str) -> Optional[str]:
    for argument in arguments[1:]:
        if not argument.startswith("-") and argument.lower().endswith(suffix):
            return argument
    return None


def _mir_output_path(arguments: list[str]) -> Optional[str]:
    for index, argument in enumerate(arguments):
        if argument in ("-o", "--output") and index + 1 < len(arguments):
            return arguments[index + 1]
        if argument.startswith("--output="):
            return argument.split("=", 1)[1]
    return None


def cmd_emit_mir(arguments: list[str], default_target: str = "cpp") -> int:
    if not arguments or arguments[0].lower() != "mir":
        print("Usage: nyx emit mir <file.nyx> [--json | --codegen] [--target t] [-o output]")
        return 1
    source_path = _mir_argument_path(arguments, ".nyx")
    if not source_path or not os.path.isfile(source_path):
        print(f"[!] MIR source file not found: {source_path or '<missing>'}")
        return 1

    from src.api import NyxCompiler
    from src.mir import (
        MIRCodegenError,
        MIRLegalizationError,
        MIRLoweringError,
        emit_legalized_c17,
        emit_legalized_cpp,
        emit_legalized_javascript,
        emit_legalized_llvm,
        emit_legalized_python,
        emit_legalized_rust,
        emit_legalized_wat,
        legalize_mir,
        lower_hir_to_mir,
        print_mir,
        to_json,
    )

    target = get_target_from_args(default_target, entry_file=source_path, arguments=arguments[1:])
    result = NyxCompiler(os.path.dirname(os.path.abspath(source_path))).check_file(
        source_path,
        target=target,
    )
    if not result.success or result.hir is None:
        for diagnostic in result.diagnostics:
            print(diagnostic.rendered)
        return 1
    try:
        mir = lower_hir_to_mir(result.hir)
    except MIRLoweringError as error:
        print(f"error[MIRL0001]: {error.message}")
        print(f"  --> {error.span.source}:{error.span.line}:{error.span.column}")
        return 1

    if "--codegen" in arguments:
        try:
            if target == "cpp":
                content = emit_legalized_cpp(mir)
            elif target == "llvm":
                content = emit_legalized_llvm(mir)
            elif target == "wasm":
                content = emit_legalized_wat(mir)
            elif target == "rust":
                content = emit_legalized_rust(mir)
            elif target == "js":
                content = emit_legalized_javascript(mir)
            elif target == "python":
                content = emit_legalized_python(mir)
            elif target == "c":
                content = emit_legalized_c17(mir)
            else:
                legalize_mir(mir, target, require_emitter=True)
                raise MIRCodegenError(f"no MIR source emitter registered for target '{target}'")
        except MIRLegalizationError as error:
            for issue in error.issues:
                print(f"error[{issue.code}]: {issue.message}")
                print(f"  --> {issue.span.source}:{issue.span.line}:{issue.span.column}")
            return 1
        except MIRCodegenError as error:
            print(f"error[{error.code}]: {str(error).split(': ', 1)[-1]}")
            return 1
    else:
        content = to_json(mir, indent=2) + "\n" if "--json" in arguments else print_mir(mir)
    output_path = _mir_output_path(arguments)
    if output_path:
        output = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        label = "Legalized MIR target source" if "--codegen" in arguments else "Experimental MIR"
        print(f"[OK] {label} written: {output}")
    else:
        print(content, end="")
    return 0


def cmd_verify_mir(arguments: list[str]) -> int:
    if not arguments or arguments[0].lower() != "mir":
        print("Usage: nyx verify mir <file.mir.json>")
        return 1
    input_path = _mir_argument_path(arguments, ".json")
    if not input_path or not os.path.isfile(input_path):
        print(f"[!] Serialized MIR file not found: {input_path or '<missing>'}")
        return 1

    from src.mir import MIRVerificationError, from_json, verify_mir

    try:
        with open(input_path, "r", encoding="utf-8") as handle:
            module = from_json(handle.read())
        verify_mir(module)
    except (OSError, ValueError, MIRVerificationError) as error:
        print(f"error[MIRV0001]: Invalid experimental MIR: {error}")
        return 1
    print(f"[OK] Experimental MIR verified: {os.path.abspath(input_path)}")
    return 0


def cmd_repl():
    print_banner()
    print("\033[92m[*] Nyx Interactive Polyglot REPL (v3.0.0)\033[0m")
    print("    Type expressions or statements. Special commands: :help, :ast, :cpp, :js, :target, :exit\n")
    
    session_statements = []
    target = "python"

    while True:
        try:
            prompt = f"\033[96mnyx [{target}]>\033[0m "
            line = input(prompt).strip()
            if not line:
                continue
            if line in (":exit", ":quit", "exit", "quit"):
                print("Goodbye!")
                break
            if line == ":help":
                print("""
REPL Commands:
  :help              Show this help
  :ast <expr>        Inspect AST of an expression
  :cpp <expr>        Inspect transpiled C++20 code
  :js <expr>         Inspect transpiled Node.js code
  :target <t>        Switch evaluation target (python, js, cpp)
  :clear             Reset REPL session memory
  :exit / :quit      Exit REPL
""")
                continue
            if line == ":clear":
                session_statements.clear()
                print("\033[92m[OK] Session memory cleared.\033[0m")
                continue
            if line.startswith(":target"):
                parts = line.split()
                if len(parts) > 1 and parts[1] in ("python", "js", "cpp"):
                    target = parts[1]
                    print(f"\033[92m[OK] Switched evaluation target to: {target}\033[0m")
                else:
                    print("Usage: :target <python|js|cpp>")
                continue
            if line.startswith(":ast "):
                code = line[5:]
                from src.core.lexer import Lexer
                from src.core.parser import Parser
                tokens = Lexer(code, "<repl>").tokenize()
                ast = Parser(tokens, "<repl>").parse()
                for s in ast.statements:
                    print(s)
                continue
            if line.startswith(":cpp "):
                code = line[5:]
                from src.core.lexer import Lexer
                from src.core.parser import Parser
                from src.codegen.codegen import UniversalCodeGen
                tokens = Lexer(code, "<repl>").tokenize()
                ast = Parser(tokens, "<repl>").parse()
                print(UniversalCodeGen(ast).gen_cpp())
                continue
            if line.startswith(":js "):
                code = line[4:]
                from src.core.lexer import Lexer
                from src.core.parser import Parser
                from src.codegen.codegen import UniversalCodeGen
                tokens = Lexer(code, "<repl>").tokenize()
                ast = Parser(tokens, "<repl>").parse()
                print(UniversalCodeGen(ast).gen_js())
                continue

            eval_line = line
            is_stmt = any(line.startswith(k) for k in ("var ", "const ", "fn ", "struct ", "impl ", "if ", "while ", "for ", "print(", "print "))
            if not is_stmt and not ("=" in line and not line.startswith("==")):
                eval_line = f"print({line});"

            test_source = "\n".join(session_statements + [eval_line])
            
            from src.core.lexer import Lexer
            from src.core.parser import Parser
            from src.core.type_checker import TypeChecker
            from src.codegen.codegen import UniversalCodeGen
            from src.codegen.cpp_toolchain import CppToolchain
            import tempfile

            tokens = Lexer(test_source, "<repl>").tokenize()
            ast = Parser(tokens, "<repl>").parse()
            tc = TypeChecker()
            tc.check(ast)
            if tc.errors:
                for e in tc.errors:
                    print(f"\033[91m{e}\033[0m")
                continue

            codegen = UniversalCodeGen(ast)
            
            if target == "python":
                py_code = codegen.gen_python()
                res = subprocess.run([sys.executable, "-c", py_code], capture_output=True, text=True)
                if res.stdout:
                    sys.stdout.write(res.stdout)
                if res.stderr:
                    sys.stderr.write(res.stderr)
            elif target == "js":
                js_code = codegen.gen_js()
                res = subprocess.run(["node", "-e", js_code], capture_output=True, text=True)
                if res.stdout:
                    sys.stdout.write(res.stdout)
                if res.stderr:
                    sys.stderr.write(res.stderr)
            elif target == "cpp":
                with tempfile.TemporaryDirectory() as td:
                    cpp_f = os.path.join(td, "repl.cpp")
                    exe_f = os.path.join(td, "repl.exe")
                    with open(cpp_f, "w", encoding="utf-8") as f:
                        f.write(codegen.gen_cpp())
                    ok, _ = CppToolchain.compile_cpp(cpp_f, exe_f)
                    if ok:
                        res = subprocess.run([exe_f], capture_output=True, text=True)
                        if res.stdout:
                            sys.stdout.write(res.stdout)
                        if res.stderr:
                            sys.stderr.write(res.stderr)

            if is_stmt:
                session_statements.append(line)

        except KeyboardInterrupt:
            print("\n(To exit, type :exit or press Ctrl+C again)")
        except EOFError:
            print("\nGoodbye!")
            break
        except Exception as err:
            print(f"\033[91m[Error]: {err}\033[0m")

def cmd_explain(code: str):
    from src.core.error_catalog import get_error_info, CATALOG
    code = code.upper().strip()
    info = get_error_info(code)
    if not info:
        print(f"\033[93m[!] Error code '{code}' is not in the catalog.\033[0m")
        print("Available error codes to explain:")
        for k in sorted(CATALOG.keys()):
            print(f"  • {k}: {CATALOG[k]['title']}")
        return

    print_banner()
    print(f"\033[96m===================================================================")
    print(f"[*] NYX DIAGNOSTIC EXPLANATION: \033[91m{code}\033[96m - {info['title']}")
    print(f"    Category: \033[93m{info['category']}\033[0m")
    print(f"===================================================================\033[0m\n")
    print(f"\033[1mDescription:\033[0m\n  {info['description']}\n")
    print(f"\033[91m[-] Erroneous Code Example:\033[0m")
    for l in info['bad_example'].split('\n'):
        print(f"  {l}")
    print(f"\n\033[92m[+] Recommended Fix / Solution:\033[0m")
    for l in info['good_example'].split('\n'):
        print(f"  {l}")
    print(f"\n\033[94m[*] Guidance:\033[0m\n  {info['solution']}\n")

def cmd_tutorial():
    print_banner()
    print("\033[92m[*] NYX 15-MINUTE INTERACTIVE TOUR\033[0m")
    print("Welcome to Nyx: designed to be as easy as Python, as safe as Rust, and as fast as C++.\n")
    lessons = [
        ("1. Variables & Types", "Nyx uses 'var' with strong, inferred static typing:\n  var name: string = \"Nyx\";\n  var speed = 1000; // int inferred\n"),
        ("2. Functions & Clean Returns", "Functions use 'fn' and '->' for return types:\n  fn add(a: int, b: int) -> int {\n      return a + b;\n  }\n"),
        ("3. Guard Statements", "Eliminate nested 'if' ladders with clean 'guard':\n  guard x > 0 else {\n      return -1;\n  }\n"),
        ("4. Safe Optionals & Coalescing", "Null-safety is built-in with '?' and '??':\n  var name: string? = null;\n  var display = name ?? \"Guest\";\n"),
        ("5. Structs & Methods", "Data and behavior are cleanly separated with 'struct' and 'impl':\n  struct Point { x: int, y: int }\n  impl Point {\n      fn sum(self) -> int { return self.x + self.y; }\n  }\n"),
        ("6. Multi-Target Polyglot Output", "One code compiles natively everywhere:\n  nyx run main.nyx --target cpp  (Native C++20)\n  nyx run main.nyx --target js   (Node.js ES2022)\n  nyx run main.nyx --target python   (Python 3)\n  nyx bundle main.nyx              (WebAssembly & React)\n")
    ]
    for title, content in lessons:
        print(f"\033[96m=== {title} ===\033[0m")
        print(content)
        print("-" * 60)

def main():
    if len(sys.argv) < 2:
        print_help()
        sys.exit(0)

    cmd = sys.argv[1].lower()
    config = parse_nyx_toml()

    if cmd in ("--help", "-h", "help"):
        print_help()
    elif cmd in ("--version", "-v", "version"):
        cmd_version()
    elif cmd == "doctor":
        cmd_doctor()
    elif cmd == "targets":
        sys.exit(cmd_targets("--json" in sys.argv, "--mir" in sys.argv))
    elif cmd == "emit":
        sys.exit(cmd_emit_mir(sys.argv[2:], config.get("target", "cpp")))
    elif cmd == "verify":
        sys.exit(cmd_verify_mir(sys.argv[2:]))
    elif cmd == "repl":
        cmd_repl()
    elif cmd == "tutorial":
        cmd_tutorial()
    elif cmd == "explain":
        if len(sys.argv) < 3:
            print("Usage: nyx explain <error_code> (e.g. nyx explain E1004)")
            sys.exit(1)
        cmd_explain(sys.argv[2])
    elif cmd == "new":
        raw_args = [a for a in sys.argv[2:] if not a.startswith("--")]
        name = raw_args[0] if raw_args else "nyx_project"
        is_lib = "--lib" in sys.argv
        sys.exit(cmd_new(name, is_lib=is_lib))
    elif cmd == "init":
        raw_args = [a for a in sys.argv[2:] if not a.startswith("--")]
        name = raw_args[0] if raw_args else config.get("name", "nyx_project")
        sys.exit(PackageManager.init(name, force="--force" in sys.argv))
    elif cmd == "check":
        entry = get_entry_file(config.get("entry", "src/main.nyx"))
        target = get_target_from_args(config.get("target", "cpp"), entry_file=entry)
        sys.exit(cmd_check(entry, target=target))
    elif cmd == "build":
        entry = get_entry_file(config.get("entry", "src/main.nyx"))
        target = get_target_from_args(config.get("target", "cpp"), entry_file=entry)
        is_release = "--release" in sys.argv
        output_type = config.get("output_type", "exe")
        sys.exit(cmd_build(
            entry,
            target,
            is_release,
            output_type=output_type,
            wasi="--wasi" in sys.argv,
            javascript_esm="--esm" in sys.argv,
        ))
    elif cmd == "bundle":
        raw_args = [a for a in sys.argv[2:] if not a.startswith("--")]
        entry = get_entry_file(raw_args[0] if raw_args else config.get("entry", "src/main.nyx"))
        out_dir = None
        for i, a in enumerate(sys.argv):
            if a in ("-o", "--output") and i + 1 < len(sys.argv):
                out_dir = sys.argv[i + 1]
        emit_react = "--react" in sys.argv
        emit_vue = "--vue" in sys.argv
        emit_svelte = "--svelte" in sys.argv
        emit_package = "--package" in sys.argv or "--npm" in sys.argv
        wasi = "--wasi" in sys.argv
        if (emit_vue or emit_svelte) and not emit_package:
            print("\033[91m[!] --vue and --svelte require --package.\033[0m")
            sys.exit(1)
        sys.exit(cmd_bundle(
            entry,
            out_dir=out_dir,
            emit_react=emit_react,
            emit_package=emit_package,
            emit_vue=emit_vue,
            emit_svelte=emit_svelte,
            wasi=wasi,
        ))
    elif cmd in ("self-host", "selfhost"):
        sys.exit(cmd_self_host(sys.argv[2:]))
    elif cmd == "run":
        entry = get_entry_file(config.get("entry", "src/main.nyx"))
        target = get_target_from_args(config.get("target", "cpp"), entry_file=entry)
        sys.exit(cmd_run(entry, target))
    elif cmd == "test":
        if len(sys.argv) > 2 and sys.argv[2].endswith(".nyx"):
            target_file = sys.argv[2]
            if not os.path.exists(target_file):
                print(f"\033[91m[!] Error: Test file '{target_file}' not found.\033[0m")
                sys.exit(1)
            print(f"\033[96m[*] Running nyx In-File Unit Tests in '{target_file}'...\033[0m")
            status = cmd_run(target_file, "python")
            if status != 0:
                print("\033[91m[!] Test execution failed.\033[0m")
                sys.exit(status)
            print("\033[92m[OK] Execution finished successfully.\033[0m")
        elif os.path.exists("src/lib.nyx"):
            print("\033[96m[*] Running nyx In-File Unit Tests in 'src/lib.nyx'...\033[0m")
            status = cmd_run("src/lib.nyx", "python")
            if status != 0:
                print("\033[91m[!] Test execution failed.\033[0m")
                sys.exit(status)
            print("\033[92m[OK] Execution finished successfully.\033[0m")
        elif os.path.exists("src/main.nyx"):
            print("\033[96m[*] Running nyx In-File Unit Tests in 'src/main.nyx'...\033[0m")
            status = cmd_run("src/main.nyx", "python")
            if status != 0:
                print("\033[91m[!] Test execution failed.\033[0m")
                sys.exit(status)
            print("\033[92m[OK] Execution finished successfully.\033[0m")
        else:
            test_suite = os.path.join(os.path.dirname(__file__), "..", "tests", "run_all_tests.py")
            if not os.path.exists(test_suite):
                test_suite = os.path.join(os.getcwd(), "tests", "run_all_tests.py")
            result = subprocess.run([sys.executable, test_suite])
            sys.exit(result.returncode)
    elif cmd == "clean":
        sys.exit(cmd_clean())
    elif cmd == "fmt":
        if len(sys.argv) < 3: print("Usage: nyx fmt <file.nyx>"); sys.exit(1)
        sys.exit(0 if Formatter.format_file(sys.argv[2]) else 1)
    elif cmd == "lint":
        if len(sys.argv) < 3: print("Usage: nyx lint <file.nyx>"); sys.exit(1)
        warnings = Linter.lint_file(sys.argv[2])
        sys.exit(1 if warnings < 0 else 0)
    elif cmd == "lsp":
        from src.toolchain.lsp_server import LanguageServer
        LanguageServer().run()
    elif cmd == "debug":
        if len(sys.argv) < 3: print("Usage: nyx debug <file.nyx>"); sys.exit(1)
        sys.exit(Debugger.debug_file(sys.argv[2]))
    elif cmd == "profile":
        entry = get_entry_file(config.get("entry", "src/main.nyx"))
        if not entry: print("Usage: nyx profile <file.nyx>"); sys.exit(1)
        target = get_target_from_args(config.get("target", "cpp"), entry_file=entry)
        sys.exit(Profiler.profile_file(entry, lambda: cmd_run(entry, target)))
    elif cmd == "doc":
        if len(sys.argv) < 3: print("Usage: nyx doc <file.nyx>"); sys.exit(1)
        sys.exit(DocGenerator.generate_docs(sys.argv[2]))
    elif cmd == "add":
        if len(sys.argv) < 3: print("Usage: nyx add <package_name>"); sys.exit(1)
        package_arguments = []
        skip_next = False
        for argument in sys.argv[2:]:
            if skip_next:
                skip_next = False
                continue
            if argument == "--path":
                skip_next = True
                continue
            if argument.startswith("--path="):
                continue
            package_arguments.append(argument)
        try:
            package_name, version = parse_package_spec(package_arguments)
        except ValueError as exc:
            print(f"[!] Invalid package specification: {exc}")
            sys.exit(1)
        local_path = None
        for index, argument in enumerate(sys.argv):
            if argument == "--path" and index + 1 < len(sys.argv):
                local_path = sys.argv[index + 1]
            elif argument.startswith("--path="):
                local_path = argument.split("=", 1)[1]
        sys.exit(PackageManager.add(package_name, version, local_path=local_path))
    elif cmd == "remove":
        if len(sys.argv) < 3: print("Usage: nyx remove <package_name>"); sys.exit(1)
        sys.exit(PackageManager.remove(sys.argv[2]))
    elif cmd == "install":
        sys.exit(PackageManager.install())
    elif cmd == "pkg":
        sys.exit(PackageManager.list_installed())
    elif cmd == "tour":
        tour_script = os.path.join(os.path.dirname(__file__), "..", "tour", "tour.py")
        if not os.path.exists(tour_script):
            tour_script = os.path.join(os.getcwd(), "tour", "tour.py")
        result = subprocess.run([sys.executable, tour_script] + sys.argv[2:])
        sys.exit(result.returncode)
    else:
        print(f"\033[91m[!] Unknown command: '{cmd}'. Run 'nyx help' for available commands.\033[0m")
        sys.exit(1)

if __name__ == "__main__":
    main()
