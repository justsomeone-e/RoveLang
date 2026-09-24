"""Calling-convention and checked C-adapter contracts for Rove MIR."""

from __future__ import annotations

from dataclasses import dataclass

from .layout import LayoutEngine, TargetDataLayout, TypeLayout, data_layout_for_target
from .model import MIRFunction, MIRModule, MIRStructDef
from .types import MIRType


BUNDLE_ABI_V1_VERSION = 1
BUNDLE_ABI_V2_DRAFT_VERSION = 2
BUNDLE_ABI_V2_STATUS = "draft"


@dataclass(frozen=True, slots=True)
class ABIProfile:
    name: str
    data_layout: TargetDataLayout
    direct_aggregate_limit: int
    caller_releases_arguments: bool
    callee_transfers_return: bool


@dataclass(frozen=True, slots=True)
class ABIValue:
    type: MIRType
    layout: TypeLayout
    mode: str
    ownership: str


@dataclass(frozen=True, slots=True)
class FunctionABI:
    profile: str
    parameters: tuple[ABIValue, ...]
    result: ABIValue


@dataclass(frozen=True, slots=True)
class CAdapterContract:
    compatible: bool
    parameter_reasons: tuple[str, ...]
    result_reason: str


def abi_profile(name: str) -> ABIProfile:
    if name in ("bundle-v1", "bundle-v2-draft"):
        layout = data_layout_for_target("wasm")
        return ABIProfile(name, layout, layout.pointer_size, True, True)
    layout = data_layout_for_target(name)
    return ABIProfile(name, layout, layout.pointer_size * 2, True, True)


def classify_function_abi(
    module: MIRModule,
    function: MIRFunction,
    profile_name: str,
) -> FunctionABI:
    profile = abi_profile(profile_name)
    engine = LayoutEngine(module, profile.data_layout)
    locals_by_id = {local.id: local for local in function.locals}
    parameters = tuple(
        _classify_value(
            locals_by_id[local_id].type,
            engine,
            profile,
            is_return=False,
        )
        for local_id in function.parameters
    )
    result_type = locals_by_id[function.return_local].type
    result = _classify_value(result_type, engine, profile, is_return=True)
    return FunctionABI(profile.name, parameters, result)


def _classify_value(
    value_type: MIRType,
    engine: LayoutEngine,
    profile: ABIProfile,
    *,
    is_return: bool,
) -> ABIValue:
    layout = engine.layout_of(value_type)
    aggregate = layout.kind not in ("scalar", "pointer", "nullable-pointer", "runtime-handle")
    if value_type.name == "void":
        mode = "void"
    elif aggregate and layout.size > profile.direct_aggregate_limit:
        mode = "sret" if is_return else "indirect"
    else:
        mode = "direct"
    ownership = "transfer" if is_return and profile.callee_transfers_return else "borrow"
    if not is_return and layout.kind in ("owned-descriptor", "struct", "enum", "option", "result"):
        ownership = "borrow"
    return ABIValue(value_type, layout, mode, ownership)


def check_c_adapter(
    module: MIRModule,
    function: MIRFunction,
    profile_name: str = "c",
) -> CAdapterContract:
    definitions = {definition.name: definition for definition in module.type_definitions}
    local_map = {local.id: local for local in function.locals}
    parameter_reasons = tuple(
        _c_compatibility(local_map[local_id].type, definitions, set())
        for local_id in function.parameters
    )
    result_reason = _c_compatibility(local_map[function.return_local].type, definitions, set())
    return CAdapterContract(
        all(reason == "compatible" for reason in parameter_reasons)
        and result_reason == "compatible",
        parameter_reasons,
        result_reason,
    )


def _c_compatibility(
    value_type: MIRType,
    definitions: dict[str, object],
    active: set[str],
) -> str:
    if value_type.optional:
        return "optional values require an explicit tagged C adapter"
    if value_type.pointer:
        return "compatible"
    if value_type.is_function:
        return "function values require an explicit callback ABI"
    if value_type.name in {
        "void", "bool", "i8", "u8", "i16", "u16", "i32", "u32", "int", "i64", "u64",
        "f32", "float", "f64", "char", "uintptr",
    }:
        return "compatible"
    if value_type.name in ("string", "Array", "Option", "Result", "Task", "Channel", "Iterator", "any"):
        return f"{value_type.name} requires a generated ownership-aware C adapter"
    definition = definitions.get(value_type.name)
    if isinstance(definition, MIRStructDef):
        if definition.name in active:
            return "recursive by-value structs are not C-compatible"
        next_active = set(active)
        next_active.add(definition.name)
        incompatible = [
            f"field {field.name}: {reason}"
            for field in definition.fields
            if (reason := _c_compatibility(field.type, definitions, next_active)) != "compatible"
        ]
        return "compatible" if not incompatible else "; ".join(incompatible)
    return f"{value_type} has no explicit C representation contract"
