import os
import shutil
import sys
import tempfile


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.core import DiagnosticEmitter, check_program_graph
from src.core.diagnostics import DiagnosticError
from src.core.module_loader import ModuleLoader
from src.ir import lower_to_hir, verify_hir


def _write(path: str, source: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(source)


def run_module_graph_checker_suite() -> bool:
    temp_dir = tempfile.mkdtemp(prefix="nyx_graph_check_")
    previous = DiagnosticEmitter.EXIT_ON_ERROR
    DiagnosticEmitter.EXIT_ON_ERROR = False
    try:
        leaf = os.path.join(temp_dir, "leaf.nyx")
        left = os.path.join(temp_dir, "left.nyx")
        right = os.path.join(temp_dir, "right.nyx")
        root = os.path.join(temp_dir, "main.nyx")
        _write(leaf, "fn base() -> int { return 40; }\nvar shared: int = 2;\n")
        _write(left, 'import "./leaf"\nfn left() -> int { return base() + shared; }\n')
        _write(right, 'import { base } from "./leaf"\nfn right() -> int { return base(); }\n')
        _write(root, 'import "./left"\nimport "./right"\nprint(left() + right());\n')

        loader = ModuleLoader(base_dir=temp_dir)
        loaded = loader.load_program_graph(root)
        checked = check_program_graph(loaded)
        assert len(checked.modules) == 4
        assert checked.modules[-1].module_id == loaded.root
        hir = lower_to_hir(loaded.compatibility_program, root)
        verify_hir(hir)

        root_checker = checked.checker(loaded.root)
        assert "left" in root_checker.func_defs and "right" in root_checker.func_defs
        assert "base" not in root_checker.func_defs
        assert root_checker.lookup("shared") is None

        selective = os.path.join(temp_dir, "selective.nyx")
        _write(selective, 'import { base } from "./leaf"\nprint(base());\n')
        selective_loaded = ModuleLoader(base_dir=temp_dir).load_program_graph(selective)
        selective_checked = check_program_graph(selective_loaded)
        selective_checker = selective_checked.checker(selective_loaded.root)
        assert "base" in selective_checker.func_defs
        assert selective_checker.lookup("shared") is None

        print("[PASS] Per-module checker environments, direct/selective imports, and linked HIR")
        return True
    finally:
        DiagnosticEmitter.EXIT_ON_ERROR = previous
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(0 if run_module_graph_checker_suite() else 1)
