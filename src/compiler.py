import os, shutil, subprocess, sys
try:
    from src.core import Lexer, Parser, TypeChecker, DiagnosticEmitter
    from .codegen import UniversalCodeGen
    from .runtime import get_runtime_env
except (ImportError, ValueError):
    from src.core import Lexer, Parser, TypeChecker, DiagnosticEmitter
    from src.codegen import UniversalCodeGen
    from src.runtime import get_runtime_env
class Compiler:
    def __init__(self, filepath: str, target_override: str = None):
        self.filepath = filepath
        self.target_override = target_override

    def compile(self, run_immediately: bool = True):
        if not os.path.exists(self.filepath):
            print(f"Error: Source file '{self.filepath}' not found!")
            sys.exit(1)

        with open(self.filepath, 'r', encoding='utf-8') as f:
            source = f.read()

        # Step 1 & 2: Load program and resolve module imports
        from src.core.module_loader import ModuleLoader
        loader = ModuleLoader(base_dir=os.path.dirname(os.path.abspath(self.filepath)))
        ast = loader.load_program(self.filepath, source)

        # Step 3: Type Checking & Semantic Analysis
        type_checker = TypeChecker(ast, self.filepath, source)
        type_checker.check()

        # Target selection
        target = self.target_override or ast.target or "cpp"
        codegen = UniversalCodeGen(ast)

        base_name = os.path.splitext(self.filepath)[0]

        if target == "cpp":
            cpp_out = codegen.gen_cpp()
            out_file = base_name + ".cpp"
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(cpp_out)
            print(f"[*] Rove Compiling: {self.filepath} -> [Target: cpp]")
            print(f"[+] Output generated: {out_file}")

        elif target == "react":
            tsx_out = codegen.gen_react()
            out_file = base_name + ".tsx"
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(tsx_out)
            print(f"[*] Rove Compiling: {self.filepath} -> [Target: react]")
            print(f"[+] Output generated: {out_file}")

        elif target == "wasm":
            wat_out = codegen.gen_wasm()
            out_file = base_name + ".wat"
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(wat_out)
            print(f"[*] Rove Compiling: {self.filepath} -> [Target: wasm]")
            print(f"[+] Output generated: {out_file}")

        elif target in ("c", "llvm"):
            from src.api import RoveCompiler

            result = RoveCompiler(os.path.dirname(os.path.abspath(self.filepath))).compile_source(
                source,
                filename=self.filepath,
                target=target,
            )
            if not result.success or result.artifact is None:
                for diagnostic in result.diagnostics:
                    print(diagnostic.rendered)
                return 1
            out_file = base_name + result.artifact.extension
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(result.artifact.content)
            print(f"[*] Rove Compiling: {self.filepath} -> [Target: {target}]")
            print(f"[+] Output generated: {out_file}")
            if not run_immediately:
                return 0
            clang = shutil.which("clang")
            if not clang:
                print("Runtime Execution Error: Clang was not found on PATH.")
                return 1
            executable = base_name + (".exe" if sys.platform == "win32" else "")
            command = [clang, "-O2"]
            if target == "c":
                command.append("-std=c17")
            command.extend([out_file, "-o", executable])
            if sys.platform != "win32":
                command.append("-lm")
            compiled = subprocess.run(command, capture_output=True, text=True)
            if compiled.returncode != 0:
                print(f"Runtime Compilation Error: {compiled.stderr or compiled.stdout}")
                return compiled.returncode or 1
            return subprocess.run([os.path.abspath(executable)]).returncode

        elif target == "python":
            py_out = codegen.gen_python()
            out_file = base_name + ".py"
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(py_out)
            print(f"[*] Rove Compiling: {self.filepath} -> [Target: python]")
            print(f"[+] Output generated: {out_file}")

        elif target == "js":
            js_out = codegen.gen_js()
            out_file = base_name + ".js"
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(js_out)
            print(f"[*] Rove Compiling: {self.filepath} -> [Target: js]")
            print(f"[+] Output generated: {out_file}")

        if run_immediately:
            print("\n" + "="*50)
            print("[+] Program Output:\n")
            py_runner_code = codegen.gen_python()
            env = get_runtime_env()
            try:
                exec(py_runner_code, env)
            except Exception as e:
                print(f"\nRuntime Execution Error: {e}")
            print("\n" + "="*50)
            print("[OK] Execution finished successfully.\n")
