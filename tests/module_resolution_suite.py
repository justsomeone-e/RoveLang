import os
import sys
import tempfile
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

from src.core.module_loader import ModuleLoader
from src.core.diagnostics import DiagnosticEmitter, DiagnosticError
from src.core.type_checker import TypeChecker
from src.ir import lower_to_hir, to_json
from src.ir.types import INT, array_of

def run_module_suite():
    print("=" * 70)
    print("⚡ ROVE MODULE SYSTEM & RESOLUTION HARNESS")
    print("=" * 70)

    # Disable exit on error so we can test negative compiler diagnostics
    DiagnosticEmitter.EXIT_ON_ERROR = False
    temp_dir = tempfile.mkdtemp(prefix="rove_mod_test_")
    passed = 0
    total = 4

    try:
        # Test 1: Diamond Dependency Resolution (A -> B, A -> C, B -> D, C -> D)
        print("[*] Testing Diamond Dependency Resolution (A -> B, A -> C, B -> D, C -> D)...")
        mod_d = os.path.join(temp_dir, "d.rove")
        mod_b = os.path.join(temp_dir, "b.rove")
        mod_c = os.path.join(temp_dir, "c.rove")
        mod_a = os.path.join(temp_dir, "a.rove")

        with open(mod_d, "w", encoding="utf-8") as f:
            f.write("fn shared_base() -> int { return 42 }\n")
        with open(mod_b, "w", encoding="utf-8") as f:
            f.write("import \"./d\"\nfn from_b() -> int { return shared_base() + 1 }\n")
        with open(mod_c, "w", encoding="utf-8") as f:
            f.write("import \"./d\"\nfn from_c() -> int { return shared_base() + 2 }\n")
        with open(mod_a, "w", encoding="utf-8") as f:
            f.write("import \"./b\"\nimport \"./c\"\nvar total = from_b() + from_c()\n")

        loader = ModuleLoader(base_dir=temp_dir)
        bundle = loader.load_program_graph(mod_a)
        ast = bundle.compatibility_program
        func_names = [getattr(s, "name", None) for s in ast.statements]
        print("  DEBUG NAMES:", func_names)
        assert func_names.count("shared_base") == 1, "Diamond dependency node 'shared_base' must be deduplicated"
        assert "from_b" in func_names and "from_c" in func_names
        graph_records = tuple(loader.module_graph.modules.values())
        assert len(graph_records) == 4
        root_record = next(record for record in graph_records if record.filepath == mod_a)
        assert {item.path for item in root_record.imports} == {"b", "c"}
        assert loader.module_graph.resolve_visible(root_record.module_id, "from_b") is not None
        assert loader.module_graph.resolve_visible(root_record.module_id, "from_c") is not None
        assert loader.module_graph.resolve_visible(root_record.module_id, "shared_base") is None
        b_record = next(record for record in graph_records if record.filepath == mod_b)
        assert loader.module_graph.resolve_visible(b_record.module_id, "shared_base") is not None
        initialization = loader.module_graph.initialization_order(root_record.module_id)
        positions = {module.path: index for index, module in enumerate(initialization)}
        assert positions["d"] < positions["b"] < positions["a"]
        assert positions["d"] < positions["c"] < positions["a"]
        assert len(bundle.modules) == 4
        root_program = bundle.module(bundle.root)
        root_names = [getattr(statement, "name", None) for statement in root_program.statements]
        assert "shared_base" not in root_names and "from_b" not in root_names
        assert "total" in root_names
        b_program = bundle.module(next(record.module_id for record in graph_records if record.filepath == mod_b))
        assert "from_b" in [getattr(statement, "name", None) for statement in b_program.statements]
        initial_graph = loader.module_graph
        with open(mod_d, "w", encoding="utf-8") as f:
            f.write("fn shared_base() -> int { return 43 }\n")
        implementation_loader = ModuleLoader(base_dir=temp_dir)
        implementation_loader.load_program(mod_a)
        assert {item.path for item in implementation_loader.module_graph.invalidated_since(initial_graph)} == {"d"}

        with open(mod_d, "w", encoding="utf-8") as f:
            f.write("fn shared_base(value: int) -> int { return value }\n")
        interface_loader = ModuleLoader(base_dir=temp_dir)
        interface_loader.load_program(mod_a)
        assert {item.path for item in interface_loader.module_graph.invalidated_since(initial_graph)} == {
            "a", "b", "c", "d"
        }
        print("  [PASS] Diamond dependency successfully resolved and deduplicated (0 collisions)")
        passed += 1

        # Test 2: Ambiguous Symbol Collision Detection (E1302)
        print("[*] Testing Ambiguous Symbol Collision Detection (E1302)...")
        mod_x = os.path.join(temp_dir, "x.rove")
        mod_y = os.path.join(temp_dir, "y.rove")
        mod_main = os.path.join(temp_dir, "ambig_main.rove")

        with open(mod_x, "w", encoding="utf-8") as f:
            f.write("fn calculate() -> int { return 10 }\n")
        with open(mod_y, "w", encoding="utf-8") as f:
            f.write("fn calculate() -> int { return 20 }\n")
        with open(mod_main, "w", encoding="utf-8") as f:
            f.write("import \"./x\"\nimport \"./y\"\nvar res = calculate()\n")

        try:
            loader = ModuleLoader(base_dir=temp_dir)
            loader.load_program(mod_main)
            print("  [FAIL] Expected E1302 Ambiguous Symbol Collision error")
        except DiagnosticError as de:
            assert de.code == "E1302"
            print(f"  [PASS] Successfully caught Ambiguous Symbol Collision (Code: {de.code})")
            passed += 1

        # Test 3: Module Not Found with candidate paths search (E1301)
        print("[*] Testing Module Not Found with Diagnostics v2 (E1301)...")
        mod_missing = os.path.join(temp_dir, "missing_main.rove")
        with open(mod_missing, "w", encoding="utf-8") as f:
            f.write("import \"./non_existent_module\"\n")

        try:
            loader = ModuleLoader(base_dir=temp_dir)
            loader.load_program(mod_missing)
            print("  [FAIL] Expected E1301 Module Not Found error")
        except DiagnosticError as de:
            assert de.code == "E1301"
            print(f"  [PASS] Successfully caught Module Not Found (Code: {de.code})")
            passed += 1

        # Test 4: stable compiler identities and interface/implementation split
        print("[*] Testing Stable Compiler Identities & Module Fingerprints...")
        identity_path = os.path.join(temp_dir, "identity.rove")
        sibling_path = os.path.join(temp_dir, "sibling.rove")
        with open(identity_path, "w", encoding="utf-8") as f:
            f.write("fn answer() -> int { return 1 }\n")
        with open(sibling_path, "w", encoding="utf-8") as f:
            f.write("fn answer() -> int { return 1 }\n")

        first_loader = ModuleLoader(base_dir=temp_dir)
        first_loader.load_program(identity_path)
        first_record = next(iter(first_loader.module_graph.modules.values()))
        first_node = first_loader.module_graph.node_id(first_record.module_id, 0)
        first_type = first_loader.module_graph.types.intern(array_of(INT))
        assert first_type == first_loader.module_graph.types.intern(array_of(INT))

        with open(identity_path, "w", encoding="utf-8") as f:
            f.write("fn answer() -> int { return 2 }\n")
        second_loader = ModuleLoader(base_dir=temp_dir)
        second_loader.load_program(identity_path)
        second_record = next(iter(second_loader.module_graph.modules.values()))
        second_node = second_loader.module_graph.node_id(second_record.module_id, 0)
        assert first_record.definitions[0].stable_key() == second_record.definitions[0].stable_key()
        assert first_record.interface_fingerprint == second_record.interface_fingerprint
        assert first_record.implementation_fingerprint != second_record.implementation_fingerprint
        assert first_node != second_node

        with open(identity_path, "w", encoding="utf-8") as f:
            f.write("fn inserted() -> int { return 0 }\nfn answer() -> int { return 2 }\n")
        inserted_loader = ModuleLoader(base_dir=temp_dir)
        inserted_loader.load_program(identity_path)
        inserted_record = next(iter(inserted_loader.module_graph.modules.values()))
        original_answer = first_loader.module_graph.resolve_export(first_record.module_id, "answer")
        shifted_answer = inserted_loader.module_graph.resolve_export(inserted_record.module_id, "answer")
        assert original_answer == shifted_answer
        assert original_answer.stable_key() == shifted_answer.stable_key()

        with open(identity_path, "w", encoding="utf-8") as f:
            f.write("fn answer() -> int { return 2 }\nfn inserted() -> int { return 0 }\n")
        reordered_loader = ModuleLoader(base_dir=temp_dir)
        reordered_loader.load_program(identity_path)
        reordered_record = next(iter(reordered_loader.module_graph.modules.values()))
        assert inserted_record.interface_fingerprint == reordered_record.interface_fingerprint

        sibling_loader = ModuleLoader(base_dir=temp_dir)
        sibling_loader.load_program(sibling_path)
        sibling_record = next(iter(sibling_loader.module_graph.modules.values()))
        assert first_record.definitions[0] != sibling_record.definitions[0]

        tracked_loader = ModuleLoader(base_dir=temp_dir, track_identities=True)
        tracked_ast = tracked_loader.load_program(identity_path)
        TypeChecker(tracked_ast, identity_path, "fn answer() -> int { return 2 }\n").check()
        tracked_hir = lower_to_hir(tracked_ast, identity_path)
        plain_loader = ModuleLoader(base_dir=temp_dir, track_identities=False)
        plain_ast = plain_loader.load_program(identity_path)
        TypeChecker(plain_ast, identity_path, "fn answer() -> int { return 2 }\n").check()
        plain_hir = lower_to_hir(plain_ast, identity_path)
        assert to_json(tracked_hir) == to_json(plain_hir)
        print("  [PASS] Stable DefId, stale NodeId invalidation, TypeId interning, split fingerprints, and byte-identical HIR v1")
        passed += 1

    finally:
        DiagnosticEmitter.EXIT_ON_ERROR = True
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("=" * 70)
    print(f"[OK] Module System Harness: {passed}/{total} Passed")
    print("=" * 70)
    return passed == total

if __name__ == "__main__":
    ok = run_module_suite()
    sys.exit(0 if ok else 1)
