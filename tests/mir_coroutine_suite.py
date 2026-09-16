from dataclasses import replace
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api import NyxCompiler
from src.mir import (
    MIRInterpreter,
    collect_mir_issues,
    lower_hir_to_mir,
    print_mir,
    verify_mir,
)


def run_mir_coroutine_suite() -> bool:
    source = """
async fn compute() -> int { return 21; }
async fn main() {
    let task: Task<int> = compute();
    let first: int = await task;
    let second: int = await task;
    print(first + second);
}
"""
    checked = NyxCompiler(str(ROOT)).check_source(
        source, filename="<mir-coroutine>", target="cpp",
    )
    assert checked.success and checked.hir is not None, checked.diagnostics
    mir = lower_hir_to_mir(checked.hir)
    verify_mir(mir)
    main_function = next(function for function in mir.functions if function.name == "main")
    assert main_function.coroutine is not None
    assert len(main_function.coroutine.suspend_points) == 2
    assert tuple(point.id for point in main_function.coroutine.suspend_points) == (0, 1)
    assert main_function.coroutine.start_symbol.endswith("::coroutine::start")
    assert main_function.coroutine.resume_symbol.endswith("::coroutine::resume")
    assert main_function.coroutine.destroy_symbol.endswith("::coroutine::destroy")
    first, second = main_function.coroutine.suspend_points
    task_local = next(local.id for local in main_function.locals if local.name == "task")
    first_value = next(local.id for local in main_function.locals if local.name == "first")
    assert task_local in first.live_locals and task_local in second.live_locals
    assert first_value not in first.live_locals and first_value in second.live_locals
    assert MIRInterpreter(mir).run().output == ("42",)
    rendered = print_mir(mir)
    assert "coroutine state" in rendered and "suspend_point 1" in rendered

    broken = replace(
        mir,
        functions=tuple(
            replace(function, coroutine=None) if function.name == "main" else function
            for function in mir.functions
        ),
    )
    issues = collect_mir_issues(broken)
    assert any(issue.code == "MIR0112" for issue in issues)

    throwing_source = """
async fn fail() -> int { throw "async boom"; }
async fn main() {
    try {
        let value: int = await fail();
        print(value);
    } catch err {
        print(err);
    }
}
"""
    throwing = NyxCompiler(str(ROOT)).check_source(
        throwing_source, filename="<mir-coroutine-throw>", target="cpp",
    )
    assert throwing.success and throwing.hir is not None, throwing.diagnostics
    throwing_mir = lower_hir_to_mir(throwing.hir)
    verify_mir(throwing_mir)
    assert MIRInterpreter(throwing_mir).run().output == ("async boom",)
    throwing_main = next(function for function in throwing_mir.functions if function.name == "main")
    assert any(
        getattr(block.terminator, "unwind", None) is not None
        and block.terminator.__class__.__name__ == "SuspendTerminator"
        for block in throwing_main.blocks
    )
    print("[PASS] MIR coroutine frame, precise suspend liveness, repeated await, and metadata rejection")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_mir_coroutine_suite() else 1)
