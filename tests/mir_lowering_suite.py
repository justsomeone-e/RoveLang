from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api import RoveCompiler
from src.mir import MIRInterpreter, MIRTrap, lower_hir_to_mir, verify_mir


FIXTURE = ROOT / "tests" / "fixtures" / "mir" / "m2_scalar.rove"


def _checked(source: str, filename: str = "<m2>"):
    result = RoveCompiler(str(ROOT)).check_source(source, filename=filename, target="cpp")
    assert result.success and result.hir is not None, result.diagnostics
    return result.hir


def _run_cli_target(target: str) -> str:
    result = subprocess.run(
        [sys.executable, str(ROOT / "src" / "cli.py"), "run", str(FIXTURE), "--target", target],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.replace("\r\n", "\n")


def run_mir_lowering_suite() -> bool:
    print("=" * 70)
    print("ROVE M2 MIR SCALAR / CONTROL-FLOW LOWERING")
    print("=" * 70)

    source = FIXTURE.read_text(encoding="utf-8")
    hir = _checked(source, str(FIXTURE))
    mir = lower_hir_to_mir(hir)
    verify_mir(mir)
    executed = MIRInterpreter(mir).run()
    assert executed.output == ("13",), executed

    order_hir = _checked(
        "fn mark(value: int) -> int { print(value); return value }\n"
        "fn main() { print(mark(1) + mark(2)) }\n",
        "evaluation-order.rove",
    )
    order = MIRInterpreter(lower_hir_to_mir(order_hir)).run()
    assert order.output == ("1", "2", "3"), order.output

    numeric_hir = _checked(
        "fn main() {\n"
        "  print(9223372036854775807 + 1)\n"
        "  print(-7 / 3)\n"
        "  print(-7 % 3)\n"
        "}\n",
        "numeric-contract.rove",
    )
    numeric = MIRInterpreter(lower_hir_to_mir(numeric_hir)).run()
    assert numeric.output == ("-9223372036854775808", "-2", "-1"), numeric.output

    trap_hir = _checked("fn main() { print(1 / 0) }\n", "division-trap.rove")
    try:
        MIRInterpreter(lower_hir_to_mir(trap_hir)).run()
        raise AssertionError("MIR interpreter did not trap division by zero")
    except MIRTrap as error:
        assert "division by zero" in str(error)

    cpp_output = _run_cli_target("cpp")
    llvm_output = _run_cli_target("llvm")
    assert re.search(r"(?m)^13$", cpp_output), cpp_output
    assert re.search(r"(?m)^13$", llvm_output), llvm_output

    print("[PASS] scalar CFG, loops, branches, calls, order, i64 arithmetic, traps, C++ and LLVM parity")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_mir_lowering_suite() else 1)
