"""Target-independent MIR effect inference and canonical ordering."""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace

from .model import (
    AggregateRValue,
    AssignStatement,
    BinaryRValue,
    CallTerminator,
    CopyOperand,
    DropTerminator,
    MIREnumDef,
    MIRFunction,
    MIRModule,
    MIRStructDef,
    ThrowTerminator,
)
from .types import MIRType


MIR_EFFECT_ORDER = (
    "may_allocate",
    "may_throw",
    "may_suspend",
    "may_block",
    "io",
    "unsafe",
    "host_call",
)
VALID_MIR_EFFECTS = frozenset(("pure",) + MIR_EFFECT_ORDER)


def _copy_may_allocate(
    value: MIRType,
    definitions: dict[str, MIRStructDef | MIREnumDef],
    seen: frozenset[str] = frozenset(),
) -> bool:
    if value.pointer:
        return False
    if value.name in {"string", "Array"}:
        return True
    if value.name in {"Option", "Result"}:
        return any(_copy_may_allocate(item, definitions, seen) for item in value.arguments)
    definition = definitions.get(value.name)
    if definition is None or value.name in seen:
        return False
    nested_seen = seen | {value.name}
    if isinstance(definition, MIRStructDef):
        return any(
            _copy_may_allocate(field.type, definitions, nested_seen)
            for field in definition.fields
        )
    return any(
        _copy_may_allocate(payload, definitions, nested_seen)
        for variant in definition.variants
        for payload in variant.payload_types
    )


def _contains_allocating_copy(
    value: object,
    function: MIRFunction,
    definitions: dict[str, MIRStructDef | MIREnumDef],
) -> bool:
    if isinstance(value, CopyOperand):
        return _copy_may_allocate(function.locals[value.place.local].type, definitions)
    if is_dataclass(value):
        return any(
            _contains_allocating_copy(getattr(value, field.name), function, definitions)
            for field in fields(value)
        )
    if isinstance(value, (tuple, list)):
        return any(_contains_allocating_copy(item, function, definitions) for item in value)
    return False


def _direct_effects(
    function: MIRFunction,
    definitions: dict[str, MIRStructDef | MIREnumDef],
) -> tuple[set[str], set[str]]:
    effects: set[str] = set()
    calls: set[str] = set()
    if function.is_async:
        effects.add("may_suspend")

    for block in function.blocks:
        for statement in block.statements:
            if not isinstance(statement, AssignStatement):
                continue
            value = statement.value
            if isinstance(value, AggregateRValue) and value.kind == "array":
                effects.add("may_allocate")
            elif (
                isinstance(value, BinaryRValue)
                and value.op == "+"
                and value.type.name == "string"
            ):
                effects.add("may_allocate")
            if _contains_allocating_copy(value, function, definitions):
                effects.add("may_allocate")

        terminator = block.terminator
        if isinstance(terminator, ThrowTerminator):
            effects.add("may_throw")
        elif isinstance(terminator, DropTerminator) and terminator.unwind is not None:
            effects.add("may_throw")
        elif isinstance(terminator, CallTerminator):
            if _contains_allocating_copy(terminator.arguments, function, definitions):
                effects.add("may_allocate")
            if terminator.unwind is not None:
                effects.add("may_throw")
            function_name = terminator.function
            if function_name in ("builtin::print", "builtin::input", "builtin::args"):
                effects.add("io")
            elif function_name == "builtin::delay_ms":
                effects.add("may_block")
            elif function_name == "builtin::to_string":
                effects.add("may_allocate")
            elif function_name.startswith("builtin::"):
                if function_name != "builtin::len":
                    effects.add("host_call")
            else:
                calls.add(function_name)
    return effects, calls


def infer_module_effects(module: MIRModule) -> MIRModule:
    """Infer a conservative fixed-point effect set for every MIR function."""
    direct: dict[str, set[str]] = {}
    calls: dict[str, set[str]] = {}
    aliases: dict[str, str] = {}
    definitions = {
        definition.name: definition
        for definition in module.type_definitions
        if isinstance(definition, (MIRStructDef, MIREnumDef))
    }
    for function in module.functions:
        effects, callees = _direct_effects(function, definitions)
        direct[function.symbol] = effects
        calls[function.symbol] = callees
        aliases[function.symbol] = function.symbol
        aliases[function.name] = function.symbol

    changed = True
    while changed:
        changed = False
        for symbol, callees in calls.items():
            combined = set(direct[symbol])
            for callee in callees:
                resolved = aliases.get(callee)
                if resolved is None:
                    combined.update(("host_call", "may_throw"))
                else:
                    combined.update(direct[resolved])
            if combined != direct[symbol]:
                direct[symbol] = combined
                changed = True

    functions = []
    for function in module.functions:
        effects = direct[function.symbol]
        canonical = tuple(item for item in MIR_EFFECT_ORDER if item in effects)
        functions.append(replace(function, effects=canonical or ("pure",)))
    return replace(module, functions=tuple(functions))
