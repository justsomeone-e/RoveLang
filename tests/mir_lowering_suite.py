from pathlib import Path
import re
import subprocess
import sys
import tempfile


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


def _run_cli_target(target: str, source_path: Path = FIXTURE) -> str:
    result = subprocess.run(
        [sys.executable, str(ROOT / "src" / "cli.py"), "run", str(source_path), "--target", target],
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

    result_array_source = (
        "fn make() -> Result<Array<int>, string> { return Ok([10, 11]) }\n"
        "fn main() {\n"
        "  var outcome = make()\n"
        "  match outcome {\n"
        "    Ok(values) => { set values[0] = 12; print(values[0], values[1]) },\n"
        "    Err(message) => print(message)\n"
        "  }\n"
        "}\n"
    )
    result_array_hir = _checked(result_array_source, "result-array-pattern.rove")
    main_function = next(item for item in result_array_hir.items if item.name == "main")
    ok_case, err_case = main_function.body[1].cases
    assert ok_case.pattern.args[0].type.canonical() == "Array<int>"
    assert err_case.pattern.args[0].type.canonical() == "string"
    result_array_mir = lower_hir_to_mir(result_array_hir)
    verify_mir(result_array_mir)
    assert MIRInterpreter(result_array_mir).run().output == ("12 11",)
    with tempfile.TemporaryDirectory(prefix="rove_result_pattern_") as directory:
        source_path = Path(directory, "result-array-pattern.rove")
        source_path.write_text(result_array_source, encoding="utf-8")
        assert re.search(r"(?m)^12 11$", _run_cli_target("cpp", source_path))

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
