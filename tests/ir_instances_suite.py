import os
import sys


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.core import Lexer, Parser, TypeChecker
from src.ir import (
    collect_generic_instances,
    lower_to_hir,
    materialize_generic_instances,
    verify_hir,
)
from src.mir import MIRInterpreter, lower_hir_to_mir, verify_mir


def _hir(source: str):
    tree = Parser(Lexer(source).tokenize(), source).parse()
    TypeChecker(tree, "<generic-instance-test>", source).check()
    return lower_to_hir(tree, "<generic-instance-test>")


def run_ir_instances_suite() -> bool:
    source = """
fn identity<T>(value: T) -> T { return value; }
fn wrap<T>(value: T) -> T { return identity(value); }
fn main() {
    let first: int = identity(41);
    let second: string = identity("nyx");
    let repeated: int = wrap(first);
    print(first, second, repeated);
}
"""
    module = _hir(source)
    main_function = next(function for function in module.functions if function.name == "main")
    first_call = main_function.body[0].expr
    second_call = main_function.body[1].expr
    assert first_call.type.canonical() == "int"
    assert second_call.type.canonical() == "string"

    first = collect_generic_instances(module)
    second = collect_generic_instances(module)
    assert first.schema_version == 2
    assert [item.stable_key() for item in first.instances] == [
        item.stable_key() for item in second.instances
    ]
    observed = sorted(
        (item.name, tuple(value.canonical() for value in item.arguments))
        for item in first.instances if item.kind == "function"
    )
    assert observed == [
        ("identity", ("int",)),
        ("identity", ("string",)),
        ("wrap", ("int",)),
    ]
    assert len({item.stable_key() for item in first.instances}) == 3

    reordered = _hir("""
fn unrelated() -> int { return 0; }
fn identity<T>(value: T) -> T { return value; }
fn wrap<T>(value: T) -> T { return identity(value); }
fn main() {
    let first: int = identity(41);
    let second: string = identity("nyx");
    let repeated: int = wrap(first);
    print(first, second, repeated);
}
""")
    reordered_plan = collect_generic_instances(reordered)
    assert {
        (item.name, tuple(value.canonical() for value in item.arguments)): item.stable_key()
        for item in first.instances
    } == {
        (item.name, tuple(value.canonical() for value in item.arguments)): item.stable_key()
        for item in reordered_plan.instances
    }

    concrete = materialize_generic_instances(module, first)
    verify_hir(concrete)
    assert all(not function.generic_params for function in concrete.functions)
    assert sum(function.name.startswith("identity__nyx_") for function in concrete.functions) == 2
    assert sum(function.name.startswith("wrap__nyx_") for function in concrete.functions) == 1
    concrete_main = next(function for function in concrete.functions if function.name == "main")
    assert concrete_main.body[0].expr.callee.startswith("identity__nyx_")
    mir = lower_hir_to_mir(concrete)
    verify_mir(mir)
    executed = MIRInterpreter(mir).run()
    assert executed.output == ("41 nyx 41",), executed.output
    direct = lower_hir_to_mir(module)
    verify_mir(direct)
    assert MIRInterpreter(direct).run().output == ("41 nyx 41",)

    aggregate_hir = _hir("""
struct Box<T> { value: T }
fn main() {
    let box: Box<int> = Box(7);
    let copy: Box<int> = box;
    print(copy.value);
}
""")
    verify_hir(aggregate_hir)
    aggregate_plan = collect_generic_instances(aggregate_hir)
    aggregate = [item for item in aggregate_plan.instances if item.kind == "struct"]
    assert len(aggregate) == 1
    assert aggregate[0].name == "Box" and aggregate[0].arguments[0].canonical() == "int"
    aggregate_concrete = materialize_generic_instances(aggregate_hir, aggregate_plan)
    verify_hir(aggregate_concrete)
    concrete_box = next(item for item in aggregate_concrete.items if item.__class__.__name__ == "IRStruct")
    assert concrete_box.name.startswith("Box__nyx_")
    aggregate_mir = lower_hir_to_mir(aggregate_hir)
    verify_mir(aggregate_mir)
    assert MIRInterpreter(aggregate_mir).run().output == ("7",)

    enum_hir = _hir("""
enum Maybe<T> { Some(T), None() }
fn main() {
    let value: Maybe<int> = Some(9);
    print(1);
}
""")
    verify_hir(enum_hir)
    enum_plan = collect_generic_instances(enum_hir)
    enum_instances = [item for item in enum_plan.instances if item.kind == "enum"]
    assert len(enum_instances) == 1
    enum_concrete = materialize_generic_instances(enum_hir, enum_plan)
    verify_hir(enum_concrete)
    concrete_enum = next(item for item in enum_concrete.items if item.__class__.__name__ == "IREnum")
    assert concrete_enum.name.startswith("Maybe__nyx_")
    enum_main = next(function for function in enum_concrete.functions if function.name == "main")
    assert enum_main.body[0].expr.callee_symbol.startswith("enum::Maybe__nyx_")
    enum_mir = lower_hir_to_mir(enum_hir)
    verify_mir(enum_mir)
    assert MIRInterpreter(enum_mir).run().output == ("1",)
    print("[PASS] Generic inference, reorder-stable InstanceIds, materialized HIR, and MIR execution")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_ir_instances_suite() else 1)
