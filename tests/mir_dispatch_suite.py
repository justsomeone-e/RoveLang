from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api import NyxCompiler
from src.ir import materialize_static_dispatch, verify_hir
from src.mir import MIRInterpreter, lower_hir_to_mir, verify_mir


def run_mir_dispatch_suite() -> bool:
    source = """
trait Show { fn show(self) -> string }
struct Point { x: int, y: int }
impl Show for Point {
    fn show(self) -> string {
        return "(" + to_string(self.x) + "," + to_string(self.y) + ")";
    }
}
fn main() { print("trait:", Point(10, 20).show()); }
"""
    checked = NyxCompiler(str(ROOT)).check_source(
        source, filename="<mir-static-dispatch>", target="cpp",
    )
    assert checked.success and checked.hir is not None, checked.diagnostics
    concrete = materialize_static_dispatch(checked.hir)
    verify_hir(concrete)
    assert not any(item.__class__.__name__ in {"IRTrait", "IRImpl"} for item in concrete.items)
    selected = next(function for function in concrete.functions if function.name == "show")
    assert selected.params[0].type.canonical() == "Point"
    main_function = next(function for function in concrete.functions if function.name == "main")
    print_call = main_function.body[0].expr
    show_call = print_call.args[1]
    assert show_call.callee_symbol == selected.symbol
    assert show_call.receiver is None and show_call.args[0].type.canonical() == "Point"

    mir = lower_hir_to_mir(checked.hir)
    verify_mir(mir)
    assert MIRInterpreter(mir).run().output == ("trait: (10,20)",)
    print("[PASS] Static trait dispatch selection, concrete self typing, and MIR execution")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_mir_dispatch_suite() else 1)
