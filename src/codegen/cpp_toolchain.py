import os
import sys
import subprocess
import shutil
import glob
import tempfile
from typing import Optional, Sequence, Tuple

class CppToolchain:
    _cached_compiler: Optional[str] = None
    _cached_ar: Optional[str] = None
    NATIVE_COMPILER_REQUIREMENT = (
        "cpp native builds require a working C++20 compiler: Clang++, "
        "GCC/G++, or MSVC cl. Install one and expose it on PATH, or set "
        "ROVE_CXX to the compiler executable. Run 'rove doctor' to verify it."
    )

    @staticmethod
    def test_compiler_capabilities(compiler_path: str) -> bool:
        """Verifies that the compiler can actually compile and run on the current host architecture."""
        import tempfile
        compiler_name = os.path.basename(compiler_path).lower()
        temp_dir = tempfile.gettempdir()
        probe_cpp = os.path.join(temp_dir, f"he_probe_{os.getpid()}.cpp")
        exe_ext = ".exe" if os.name == 'nt' else ""
        probe_exe = os.path.join(temp_dir, f"he_probe_{os.getpid()}{exe_ext}")
        
        with open(probe_cpp, "w", encoding="utf-8") as f:
            f.write("#include <iostream>\n#include <string>\nint main(){ std::cout << 42 << std::endl; return 0; }\n")
            
        try:
            if "cl" in compiler_name and "clang" not in compiler_name:
                cmd = [compiler_path, "/std:c++20", "/EHsc", probe_cpp, f"/Fe:{probe_exe}"]
                res = subprocess.run(cmd, capture_output=True, timeout=30)
            else:
                static_flag = ["-static"] if sys.platform != 'darwin' else []
                cmd = [compiler_path, "-std=c++20"] + static_flag + [probe_cpp, "-o", probe_exe]
                res = subprocess.run(cmd, capture_output=True, timeout=30)
                if res.returncode != 0:
                    # Fallback without -static (works for MSVC Clang and systems lacking static libc)
                    cmd = [compiler_path, "-std=c++20", probe_cpp, "-o", probe_exe]
                    res = subprocess.run(cmd, capture_output=True, timeout=30)
                
            if res.returncode != 0:
                return False
                
            if os.path.exists(probe_exe):
                bin_dir = os.path.dirname(compiler_path)
                env = {**os.environ, 'PATH': bin_dir + os.pathsep + os.environ.get('PATH', '')}
                run_res = subprocess.run([probe_exe], capture_output=True, text=True, env=env, timeout=15)
                return run_res.returncode == 0 and "42" in run_res.stdout
            return False
        except Exception:
            return False
        finally:
            if os.path.exists(probe_cpp):
                try: os.remove(probe_cpp)
                except: pass
            if os.path.exists(probe_exe):
                try: os.remove(probe_exe)
                except: pass

    @classmethod
    def _disk_cache_path(cls) -> str:
        home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or tempfile.gettempdir()
        cache_dir = os.path.join(home, ".rove")
        if os.path.exists(cache_dir):
            return os.path.join(cache_dir, "cxx_cache.txt")
        return os.path.join(tempfile.gettempdir(), "rove_cxx_cache.txt")

    @classmethod
    def find_compiler(cls) -> Optional[str]:
        if cls._cached_compiler and os.path.exists(cls._cached_compiler):
            return cls._cached_compiler

        cache_file = cls._disk_cache_path()
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = f.read().strip()
                if cached and os.path.isfile(cached):
                    cls._cached_compiler = cached
                    return cached
            except Exception:
                pass

        candidates = []

        # Explicit configuration wins and is validated by the same compile/run
        # capability probe as auto-discovered compilers.
        configured = (os.environ.get("ROVE_CXX") or os.environ.get("NYX_CXX") or "").strip()
        if configured:
            configured_path = shutil.which(configured)
            if not configured_path:
                configured_path = os.path.abspath(os.path.expanduser(configured))
            if os.path.isfile(configured_path):
                candidates.append(configured_path)
        
        # 1. PATH (prefer x86_64 or native)
        for c in ('x86_64-w64-mingw32-clang++', 'x86_64-w64-mingw32-g++', 'clang++', 'g++', 'cl', 'gcc'):
            path = shutil.which(c)
            if path and path not in candidates:
                candidates.append(path)

        # 2. WinGet Packages (specifically search x86_64)
        local_app_data = os.environ.get('LOCALAPPDATA', '')
        if local_app_data:
            for pat in ('*clang++*.exe', '*g++*.exe'):
                matches = glob.glob(os.path.join(local_app_data, 'Microsoft', 'WinGet', 'Packages', '**', pat), recursive=True)
                for m in matches:
                    if 'aarch64' not in m and 'arm' not in m and 'i686' not in m and m not in candidates:
                        candidates.append(m)

        # 3. Standard Windows Locations
        fixed_paths = [
            r'C:\msys64\ucrt64\bin\g++.exe',
            r'C:\msys64\mingw64\bin\g++.exe',
            r'C:\MinGW\bin\g++.exe',
            r'C:\Program Files\llvm-mingw\bin\x86_64-w64-mingw32-clang++.exe',
            r'C:\Program Files\LLVM\bin\clang++.exe',
            r'C:\tools\msys64\mingw64\bin\g++.exe',
        ]
        for p in fixed_paths:
            if os.path.exists(p) and p not in candidates:
                candidates.append(p)

        # Validate with active compilation and execution capability probe
        for cand in candidates:
            if cls.test_compiler_capabilities(cand):
                cls._cached_compiler = cand
                try:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        f.write(cand)
                except Exception:
                    pass
                return cand
                
        return None

    @classmethod
    def find_ar(cls) -> Optional[str]:
        if cls._cached_ar and os.path.exists(cls._cached_ar):
            return cls._cached_ar
        compiler = cls.find_compiler()
        if compiler:
            bin_dir = os.path.dirname(compiler)
            for ar_name in ('llvm-ar.exe', 'ar.exe', 'x86_64-w64-mingw32-ar.exe', 'llvm-ar', 'ar'):
                p = os.path.join(bin_dir, ar_name)
                if os.path.exists(p):
                    cls._cached_ar = p
                    return p
        for ar_name in ('llvm-ar', 'ar'):
            p = shutil.which(ar_name)
            if p:
                cls._cached_ar = p
                return p
        return None

    @classmethod
    def compile_cpp(cls, cpp_filepath: str, out_exe: Optional[str] = None, link_libraries: Optional[list] = None, output_type: str = "exe", include_dirs: Optional[list] = None, lib_dirs: Optional[list] = None) -> Tuple[bool, str]:
        compiler = cls.find_compiler()
        if not compiler:
            return False, cls.NATIVE_COMPILER_REQUIREMENT

        compiler_name = os.path.basename(compiler).lower()
        link_libs = link_libraries or []
        inc_args = [f"-I{d}" for d in (include_dirs or [])]
        libdir_args = [f"-L{d}" for d in (lib_dirs or [])]

        # Determine target file extension if not provided
        if not out_exe:
            base = os.path.splitext(cpp_filepath)[0]
            if output_type in ("lib", "static"):
                out_exe = f"{base}.a"
            elif output_type in ("shared", "dll"):
                out_exe = f"{base}.dll" if os.name == 'nt' else f"{base}.so"
            elif output_type in ("obj", "object"):
                out_exe = f"{base}.o"
            else:
                out_exe = f"{base}.exe" if os.name == 'nt' else base

        # Check inferred output_type from filename
        if out_exe.endswith(".a") or out_exe.endswith(".lib"):
            output_type = "lib"
        elif out_exe.endswith(".dll") or out_exe.endswith(".so") or out_exe.endswith(".dylib"):
            output_type = "shared"
        elif out_exe.endswith(".o") or out_exe.endswith(".obj"):
            output_type = "obj"

        # 1. Static Library (.a / .lib)
        if output_type == "lib":
            temp_obj = os.path.splitext(cpp_filepath)[0] + ".temp.o"
            cmd_obj = [compiler, "-std=c++20", "-O2", "-c", cpp_filepath, "-o", temp_obj] + inc_args
            try:
                res = subprocess.run(cmd_obj, capture_output=True, text=True)
                if res.returncode != 0:
                    return False, f"C++ Object Compilation Error:\n{res.stderr or res.stdout}"
                ar = cls.find_ar()
                if not ar:
                    return False, "Archive utility (ar / llvm-ar) not found in toolchain."
                cmd_ar = [ar, "rcs", out_exe, temp_obj]
                res_ar = subprocess.run(cmd_ar, capture_output=True, text=True)
                if os.path.exists(temp_obj):
                    try: os.remove(temp_obj)
                    except: pass
                if res_ar.returncode == 0:
                    return True, out_exe
                return False, f"Static Archive Error:\n{res_ar.stderr or res_ar.stdout}"
            except Exception as e:
                return False, f"Failed to build static library: {e}"

        # 2. Shared Library (.dll / .so)
        elif output_type == "shared":
            lib_args = [f"-l{l}" for l in link_libs]
            cmd = [compiler, "-std=c++20", "-shared", "-O2", cpp_filepath, "-o", out_exe] + inc_args + libdir_args + lib_args
            try:
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    return True, out_exe
                return False, f"Shared Library Error:\n{res.stderr or res.stdout}"
            except Exception as e:
                return False, f"Failed to build shared library: {e}"

        # 3. Object File (.o)
        elif output_type == "obj":
            cmd = [compiler, "-std=c++20", "-c", "-O2", cpp_filepath, "-o", out_exe] + inc_args
            try:
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    return True, out_exe
                return False, f"Object Compilation Error:\n{res.stderr or res.stdout}"
            except Exception as e:
                return False, f"Failed to compile object: {e}"

        # 4. Assembly Source (.s / .asm)
        elif output_type in ("asm", "s"):
            cmd = [compiler, "-std=c++20", "-S", "-masm=intel", "-O2", cpp_filepath, "-o", out_exe] + inc_args
            try:
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    return True, out_exe
                return False, f"Assembly Generation Error:\n{res.stderr or res.stdout}"
            except Exception as e:
                return False, f"Failed to generate assembly: {e}"

        # 4. Standard Executable (.exe)
        if "cl" in compiler_name and "clang" not in compiler_name:
            lib_args = [l if (l.endswith(".lib") or os.path.exists(l)) else f"{l}.lib" for l in link_libs]
            cmd = [compiler, "/std:c++20", "/EHsc", "/O2", cpp_filepath, f"/Fe:{out_exe}"] + inc_args + libdir_args + lib_args
            try:
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    return True, out_exe
                return False, f"C++ Compilation Error:\n{res.stderr or res.stdout}"
            except Exception as e:
                return False, f"Failed to execute compiler '{compiler}': {e}"
        else:
            lib_args = [l if (l.endswith(".a") or l.endswith(".lib") or l.endswith(".o") or os.path.exists(l)) else f"-l{l}" for l in link_libs]
            static_flag = ["-static"] if (sys.platform != 'darwin' and "-shared" not in inc_args) else []
            cmd = [compiler, "-std=c++20", "-O2"] + static_flag + [cpp_filepath, "-o", out_exe] + inc_args + libdir_args + lib_args
            try:
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    return True, out_exe
                # Fallback without -static
                cmd = [compiler, "-std=c++20", "-O2", cpp_filepath, "-o", out_exe] + inc_args + libdir_args + lib_args
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0:
                    return True, out_exe
                return False, f"C++ Compilation Error:\n{res.stderr or res.stdout}"
            except Exception as e:
                return False, f"Failed to execute compiler '{compiler}': {e}"

    @classmethod
    def run_executable(
        cls,
        exe_filepath: str,
        args: Optional[Sequence[str]] = None,
        timeout: Optional[int] = None,
        capture_output: bool = True,
    ) -> Tuple[int, str]:
        compiler = cls.find_compiler()
        env = os.environ.copy()
        if compiler:
            bin_dir = os.path.dirname(compiler)
            env['PATH'] = bin_dir + os.pathsep + env.get('PATH', '')
        try:
            command = [exe_filepath, *(str(arg) for arg in (args or ()))]
            if capture_output:
                res = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, timeout=timeout or 120)
                return res.returncode, res.stdout or res.stderr
            else:
                res = subprocess.run(command, env=env)
                return res.returncode, ""
        except subprocess.TimeoutExpired:
            return -1, f"Execution timed out ({timeout}s limit)"
        except Exception as e:
            return -1, f"Failed to run executable: {e}"
