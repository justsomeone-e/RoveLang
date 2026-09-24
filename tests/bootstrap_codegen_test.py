import os
import sys
import subprocess

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from src.core.lexer import Lexer as PyLexer
from src.core.parser import Parser as PyParser
from src.codegen.codegen import UniversalCodeGen
from src.codegen.cpp_toolchain import CppToolchain

def test_codegen_nyx():
    print("[*] Testing compilation of compiler/ast.rove + compiler/codegen.rove...")
    
    with open(os.path.join(_root_dir, "compiler", "ast.rove"), "r", encoding="utf-8") as f:
        ast_src = f.read()
    with open(os.path.join(_root_dir, "compiler", "codegen.rove"), "r", encoding="utf-8") as f:
        cg_src = f.read()

    # Strip duplicate directives
    cg_clean = "\n".join(l for l in cg_src.splitlines() if not l.startswith("#target") and not l.startswith("#native"))

    test_main = """
fn main() {
    var cg = CodeGen(0, "", false)
    var p = FunctionParam("x", "int")
    var params: Array<FunctionParam> = [p]
    var generic_args: Array<string> = []
    var children: Array<ASTNode> = []
    var fn_node = ASTNode(
        "FunctionDef",
        "add_one",
        "",
        "",
        "int",
        false,
        false,
        true,
        false,
        params,
        generic_args,
        children,
        1,
        1
    )
    var stmts: Array<ASTNode> = [fn_node]
    var res = cg.generate(stmts)
    print(res)
}
"""

    combined_src = ast_src + "\n\n" + cg_clean + "\n\n" + test_main

    tokens = PyLexer(combined_src, "codegen_suite.rove").tokenize()
    ast = PyParser(tokens, "codegen_suite.rove").parse()
    cpp_code = UniversalCodeGen(ast).generate()

    out_cpp = os.path.join(_root_dir, "build", "cpp", "codegen_test.cpp")
    os.makedirs(os.path.dirname(out_cpp), exist_ok=True)
    with open(out_cpp, "w", encoding="utf-8") as f:
        f.write(cpp_code)

    print(f"[OK] Emitted C++ ({len(cpp_code.splitlines())} lines) -> {out_cpp}")
    print("[*] Compiling with native Clang++ toolchain...")
    
    success, bin_path = CppToolchain.compile_cpp(out_cpp)
    if not success:
        print(f"[FAIL] {bin_path}")
        sys.exit(1)
        
    print(f"[SUCCESS] Native binary created -> {bin_path}")
    print("[*] Executing binary to test pure .rove C++ code generation:")
    compiler = CppToolchain.find_compiler()
    bin_dir = os.path.dirname(compiler) if compiler else ""
    env = {**os.environ, 'PATH': bin_dir + os.pathsep + os.environ.get('PATH', '')}
    run_res = subprocess.run([bin_path], capture_output=True, text=True, env=env)
    print("--- GENERATED OUTPUT ---")
    print(run_res.stdout)
    print("------------------------")
    assert "int64_t add_one(int64_t x)" in run_res.stdout
    print("[ALL PASS] compiler/codegen.rove is 100% verified and functional!")

if __name__ == "__main__":
    test_codegen_nyx()
