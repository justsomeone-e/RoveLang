import os
import subprocess
import sys
import warnings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

from src.core import Lexer, Parser, TypeChecker, TokenType
from src.core.ast_nodes import FunctionDefNode, StructDefNode
from src.codegen import UniversalCodeGen
from tests.battery138.run_battery import run_all_138 as run_battery138

def run_lexer_tests():
    print("[*] Running Lexer Unit Tests...")
    src = 'var x: int = 10 + 20; print("çğıöşü 🚀", x)'
    tokens = Lexer(src).tokenize()
    assert tokens[0].type == TokenType.VAR
    assert tokens[1].value == 'x'
    assert tokens[3].value == 'int'
    assert tokens[5].value == 10
    assert any(t.type == TokenType.STRING and 'çğıöşü' in t.value for t in tokens)
    print("  [PASS] Lexer tokenization & Unicode handling")

def run_parser_tests():
    print("[*] Running Parser Unit Tests...")
    src = """#target cpp
struct Point { x: int, y: int }
fn add_point(p1: Point, p2: Point) -> Point {
    return Point(p1.x + p2.x, p1.y + p2.y)
}
"""
    ast = Parser(Lexer(src).tokenize(), src).parse()
    assert ast.target == 'cpp'
    assert len(ast.statements) == 2

    metadata_src = """/// Return the input value.
async fn identity<T>(value: T) -> T { return value }
"""
    metadata_ast = Parser(Lexer(metadata_src).tokenize(), metadata_src).parse()
    identity_fn = metadata_ast.statements[0]
    assert isinstance(identity_fn, FunctionDefNode)
    assert identity_fn.generic_params == ["T"]
    assert identity_fn.is_async is True
    assert identity_fn.doc_comment == "Return the input value."
    assert identity_fn.line == 2 and identity_fn.col == 1
    print("  [PASS] Parser Struct & Function AST construction")

def run_type_checker_tests():
    print("[*] Running TypeChecker Semantic Tests...")
    src = """var a = 10
var b = 20.5
var c = "Hello"
var d = [1, 2, 3]
"""
    ast = Parser(Lexer(src).tokenize(), src).parse()
    tc = TypeChecker(ast, '<test>', src)
    tc.check()
    assert tc.lookup('a') == 'int'
    assert tc.lookup('b') == 'float'
    assert tc.lookup('c') == 'string'
    assert 'Array' in tc.lookup('d')
    print("  [PASS] TypeChecker Scope tracking & Inference")

def run_codegen_tests():
    print("[*] Running C++20 / Python Codegen Tests...")
    src = """#target cpp
struct User { name: string, age: int }
fn is_adult(u: User) -> bool { return u.age >= 18 }
"""
    ast = Parser(Lexer(src).tokenize(), src).parse()
    cpp = UniversalCodeGen(ast).gen_cpp()
    assert 'struct User {' in cpp
    assert 'User(' in cpp
    assert 'bool is_adult(' in cpp

    recursive_src = """struct FunctionParam { defaults: Array<ASTNode> }
struct ASTNode { params: Array<FunctionParam> }
"""
    recursive_ast = Parser(Lexer(recursive_src).tokenize(), recursive_src).parse()
    recursive_cpp = UniversalCodeGen(recursive_ast).gen_cpp()
    assert "FunctionParam();" in recursive_cpp
    assert "std::vector<ASTNode> defaults;" in recursive_cpp
    assert "std::vector<ASTNode> defaults{};" not in recursive_cpp
    assert "FunctionParam::FunctionParam() : defaults() {}" in recursive_cpp

    coalesce_src = "var present = 100 ?? 42\nvar missing = null ?? 42\n"
    coalesce_ast = Parser(Lexer(coalesce_src).tokenize(), coalesce_src).parse()
    TypeChecker(coalesce_ast, '<coalesce>', coalesce_src).check()
    python_code = UniversalCodeGen(coalesce_ast).gen_python()
    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        namespace = {"__name__": "nyx_codegen_test"}
        exec(compile(python_code, "<nyx_codegen_test>", "exec"), namespace)
    assert namespace["present"] == 100 and namespace["missing"] == 42
    print("  [PASS] C++ declarations and lazy Python null-coalescing")

def run_module_tests():
    print("[*] Running Module & Import Loader Unit Tests...")
    from src.core.module_loader import ModuleLoader
    main_file = os.path.join(BASE_DIR, "tests", "modules", "main_test.rove")
    loader = ModuleLoader(base_dir=os.path.dirname(main_file))
    ast = loader.load_program(main_file)
    assert any(isinstance(s, FunctionDefNode) and s.name == "calculate_discount" for s in ast.statements)
    assert any(isinstance(s, FunctionDefNode) and s.name == "pow" for s in ast.statements)
    print("  [PASS] Multi-file local and standard library module resolution")

from tests.negative_tests import run_negative_tests
from tests.fuzz_test import run_fuzz_tests
from tests.differential_testing import run_differential_tests
from tests.module_resolution_suite import run_module_suite
from tests.lsp_suite import run_lsp_suite
from tests.smoke_test_clean_environment import run_smoke_test
from tests.cpp_e2e_suite import run_cpp_e2e_tests
from tests.js_e2e_suite import run_js_e2e_tests
from tests.rust_e2e_suite import run_rust_e2e_tests
from tests.ffi_suite import run_ffi_suite
from tests.native_library_suite import run_native_library_suite
from tests.manifest_suite import run_manifest_suite
from tests.linking_suite import run_linking_suite
from tests.platform_suite import run_platform_suite
from tests.sdk_suite import run_sdk_suite
from tests.interop_suite import run_interop_suite
from tests.bootstrap_lexer_test import run_bootstrap_lexer_test
from tests.bootstrap_parser_test import run_bootstrap_parser_test
from tests.bootstrap_parser_corpus_test import run_parser_validation_corpus
from tests.bootstrap_typechecker_test import run_bootstrap_typechecker_test
from tests.cli_process_suite import run_cli_process_suite
from tests.bundle_suite import run_bundle_suite
from tests.web_bundle_suite import run_web_bundle_suite
from tests.docs_site_suite import run_docs_site_suite
from tests.self_host_suite import run_self_host_suite
from tests.capability_suite import run_capability_suite
from tests.http_stdlib_suite import run_http_stdlib_suite
from tests.foreign_import_suite import run_foreign_import_suite
from tests.payload_enum_suite import run_payload_enum_suite
from tests.result_propagation_suite import run_result_propagation_suite
from tests.collection_api_suite import run_collection_api_suite
from tests.fallible_stdlib_suite import run_fallible_stdlib_suite
from tests.default_arguments_suite import run_default_arguments_suite
from tests.destructuring_suite import run_destructuring_suite
from tests.compiler_api_suite import run_compiler_api_suite
from tests.installer_suite import run_installer_suite
from tests.ir_suite import run_ir_suite
from tests.hir_cpp_suite import run_hir_cpp_suite
from tests.hir_javascript_suite import run_hir_javascript_suite
from tests.hir_python_suite import run_hir_python_suite
from tests.hir_rust_suite import run_hir_rust_suite
from tests.c17_scalar_suite import run_c17_scalar_suite
from tests.language_surface_suite import run_language_surface_suite
from tests.numeric_semantics_suite import run_numeric_semantics_suite
from tests.maya_surface_suite import run_maya_surface_suite
from tests.release_packaging_suite import run_release_packaging_suite
from tests.version_contract_suite import run_version_contract_suite
from tests.toolchain_cli_suite import run_toolchain_cli_suite
from tests.package_manager_suite import run_package_manager_suite
from tests.llvm_scalar_suite import run_llvm_scalar_suite
from tests.feature_manifest_suite import run_feature_manifest_suite
from tests.mir_suite import run_mir_suite
from tests.mir_lowering_suite import run_mir_lowering_suite
from tests.mir_cleanup_suite import run_mir_cleanup_suite
from tests.mir_memory_abi_suite import run_mir_memory_abi_suite
from tests.mir_legalization_suite import run_mir_legalization_suite
from tests.ir_instances_suite import run_ir_instances_suite
from tests.mir_coroutine_suite import run_mir_coroutine_suite
from tests.mir_dispatch_suite import run_mir_dispatch_suite
from tests.module_graph_checker_suite import run_module_graph_checker_suite

def main():
    print("=" * 70)
    print("⚡ NYX SYSTEMS UNIFIED TEST FRAMEWORK")
    print("=" * 70)
    
    run_lexer_tests()
    run_parser_tests()
    run_type_checker_tests()
    run_codegen_tests()
    run_module_tests()

    cli_ok = run_cli_process_suite()

    toolchain_cli_ok = run_toolchain_cli_suite()

    bundle_ok = run_bundle_suite()

    print()
    web_bundle_ok = run_web_bundle_suite()
    docs_site_ok = run_docs_site_suite()

    print()
    self_host_ok = run_self_host_suite()

    print()
    capability_ok = run_capability_suite()

    print()
    http_stdlib_ok = run_http_stdlib_suite()

    print()
    foreign_import_ok = run_foreign_import_suite()

    print()
    payload_enum_ok = run_payload_enum_suite()

    print()
    result_propagation_ok = run_result_propagation_suite()

    print()
    collection_api_ok = run_collection_api_suite()

    print()
    fallible_stdlib_ok = run_fallible_stdlib_suite()


    print()
    default_arguments_ok = run_default_arguments_suite()

    print()
    destructuring_ok = run_destructuring_suite()

    print()
    compiler_api_ok = run_compiler_api_suite()

    print()
    ir_ok = run_ir_suite()

    print()
    hir_python_ok = run_hir_python_suite()

    print()
    hir_javascript_ok = run_hir_javascript_suite()

    print()
    hir_cpp_ok = run_hir_cpp_suite()

    print()
    hir_rust_ok = run_hir_rust_suite()

    print()
    c17_scalar_ok = run_c17_scalar_suite()

    print()
    pkg_mgr_ok = run_package_manager_suite()

    print()
    llvm_scalar_ok = run_llvm_scalar_suite()

    print()
    feature_manifest_ok = run_feature_manifest_suite()

    print()
    mir_ok = run_mir_suite()

    print()
    mir_lowering_ok = run_mir_lowering_suite()

    print()
    mir_cleanup_ok = run_mir_cleanup_suite()

    print()
    mir_memory_abi_ok = run_mir_memory_abi_suite()

    print()
    mir_legalization_ok = run_mir_legalization_suite()

    print()
    ir_instances_ok = run_ir_instances_suite()

    print()
    mir_coroutine_ok = run_mir_coroutine_suite()

    print()
    mir_dispatch_ok = run_mir_dispatch_suite()

    print()
    module_graph_checker_ok = run_module_graph_checker_suite()

    print()
    language_surface_ok = run_language_surface_suite()

    print()
    numeric_semantics_ok = run_numeric_semantics_suite()

    print()
    maya_surface_ok = run_maya_surface_suite()

    print()
    release_packaging_ok = run_release_packaging_suite()

    print()
    version_contract_ok = run_version_contract_suite()

    print()
    installer_ok = run_installer_suite()
    
    print()
    mod_ok = run_module_suite()
    
    print()
    lsp_ok = run_lsp_suite()
    
    print()
    smoke_ok = run_smoke_test()
    
    print()
    neg_ok = run_negative_tests()
    
    print()
    fuzz_ok = run_fuzz_tests(500) # Exactly 530 deterministic fuzz test cases
    
    print()
    diff_ok = run_differential_tests()
    
    print()
    js_ok = run_js_e2e_tests()
    
    print()
    rs_ok = run_rust_e2e_tests()
    
    print()
    e2e_ok = run_cpp_e2e_tests()

    print()
    ffi_ok = run_ffi_suite()

    print()
    natlib_ok = run_native_library_suite()

    print()
    man_ok = run_manifest_suite()

    print()
    link_ok = run_linking_suite()

    print()
    plat_ok = run_platform_suite()

    print()
    sdk_ok = run_sdk_suite()

    print()
    interop_ok = run_interop_suite()

    print()
    boot_lex_ok = run_bootstrap_lexer_test()

    print()
    boot_parse_ok = run_bootstrap_parser_test()

    print()
    boot_corpus_ok = run_parser_validation_corpus()

    print()
    boot_tc_ok = run_bootstrap_typechecker_test()
    
    print("\n[*] Executing 138-Point Exhaustive Regression Battery...")
    battery_ok = run_battery138()
    
    all_passed = (cli_ok and toolchain_cli_ok and bundle_ok and web_bundle_ok and self_host_ok and capability_ok and http_stdlib_ok and foreign_import_ok and payload_enum_ok and result_propagation_ok and collection_api_ok and fallible_stdlib_ok and default_arguments_ok and destructuring_ok and compiler_api_ok and ir_ok and hir_python_ok and hir_javascript_ok and hir_cpp_ok and hir_rust_ok and c17_scalar_ok and pkg_mgr_ok and llvm_scalar_ok and feature_manifest_ok and mir_ok and mir_lowering_ok and mir_cleanup_ok and mir_memory_abi_ok and mir_legalization_ok and ir_instances_ok and mir_coroutine_ok and mir_dispatch_ok and module_graph_checker_ok and language_surface_ok and numeric_semantics_ok and maya_surface_ok and release_packaging_ok and version_contract_ok and installer_ok and mod_ok and lsp_ok and smoke_ok and neg_ok and fuzz_ok and
                  diff_ok and js_ok and rs_ok and e2e_ok and ffi_ok and
                  natlib_ok and man_ok and link_ok and plat_ok and sdk_ok and interop_ok and boot_lex_ok and boot_parse_ok and boot_corpus_ok and boot_tc_ok and battery_ok)
    print("=" * 70)
    all_passed = all_passed and docs_site_ok
    if all_passed:
        print("🏆 ALL TEST SUITES PASSED (100% SUCCESS RATE)")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 70)
    
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()
