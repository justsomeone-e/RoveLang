"""Target-independent generic instance discovery for Typed HIR.

This pass discovers the closed set of concrete generic instances that are
reachable from non-generic roots and materializes target-independent symbols.
Target ABI/export mangling remains a backend concern.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from typing import Iterable, Mapping

from src.core.identities import DefId, InstanceId, ModuleId, TypeInterner

from .model import IREnum, IRCall, IRFunction, IRModule, IRNode, IRStruct, IRType
from .types import ANY, is_exact_type


INSTANCE_PLAN_SCHEMA_VERSION = 2


class GenericInstanceError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class GenericInstance:
    instance_id: InstanceId
    definition: DefId
    symbol: str
    name: str
    kind: str
    arguments: tuple[IRType, ...]
    substitutions: tuple[tuple[str, IRType], ...]

    def stable_key(self) -> str:
        return self.instance_id.stable_key()


@dataclass(frozen=True, slots=True)
class GenericInstancePlan:
    instances: tuple[GenericInstance, ...]
    schema_version: int = INSTANCE_PLAN_SCHEMA_VERSION


def _concrete_name(instance: GenericInstance) -> str:
    return f"{instance.name}__rove_{instance.instance_id.stable_key()[-12:]}"


def _concrete_symbol(instance: GenericInstance) -> str:
    return f"{instance.symbol}::instance::{instance.instance_id.stable_key()[-16:]}"


def substitute_type(value: IRType, substitutions: Mapping[str, IRType]) -> IRType:
    """Apply generic substitutions recursively without mutating HIR types."""
    if (
        value.name in substitutions
        and not value.arguments
        and not value.parameter_types
        and value.return_type is None
    ):
        replacement = substitutions[value.name]
        return IRType(
            replacement.name,
            replacement.arguments,
            value.optional or replacement.optional,
            value.pointer or replacement.pointer,
            replacement.parameter_types,
            replacement.return_type,
        )
    return IRType(
        value.name,
        tuple(substitute_type(item, substitutions) for item in value.arguments),
        value.optional,
        value.pointer,
        tuple(substitute_type(item, substitutions) for item in value.parameter_types),
        substitute_type(value.return_type, substitutions) if value.return_type else None,
    )


def _unify(
    pattern: IRType,
    actual: IRType,
    generic_params: frozenset[str],
    substitutions: dict[str, IRType],
    function_name: str,
) -> None:
    if pattern.name in generic_params and not pattern.arguments:
        concrete = IRType(
            actual.name,
            actual.arguments,
            actual.optional and not pattern.optional,
            actual.pointer and not pattern.pointer,
            actual.parameter_types,
            actual.return_type,
        )
        previous = substitutions.get(pattern.name)
        if previous is not None and not is_exact_type(previous, concrete):
            raise GenericInstanceError(
                "GEN0002",
                f"Generic parameter '{pattern.name}' in '{function_name}' has conflicting "
                f"types '{previous.canonical()}' and '{concrete.canonical()}'",
            )
        substitutions[pattern.name] = concrete
        return
    if actual == ANY:
        return
    if (
        pattern.name != actual.name
        or pattern.optional != actual.optional
        or pattern.pointer != actual.pointer
        or len(pattern.arguments) != len(actual.arguments)
        or len(pattern.parameter_types) != len(actual.parameter_types)
        or bool(pattern.return_type) != bool(actual.return_type)
    ):
        return
    for expected, found in zip(pattern.arguments, actual.arguments):
        _unify(expected, found, generic_params, substitutions, function_name)
    for expected, found in zip(pattern.parameter_types, actual.parameter_types):
        _unify(expected, found, generic_params, substitutions, function_name)
    if pattern.return_type and actual.return_type:
        _unify(pattern.return_type, actual.return_type, generic_params, substitutions, function_name)


def _walk_calls(value: object) -> Iterable[IRCall]:
    if isinstance(value, IRCall):
        yield value
    if isinstance(value, IRType):
        return
    if isinstance(value, IRNode) or is_dataclass(value):
        for field in fields(value):
            yield from _walk_calls(getattr(value, field.name))
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _walk_calls(item)


def _walk_types(value: object) -> Iterable[IRType]:
    if isinstance(value, IRType):
        yield value
        for argument in value.arguments:
            yield from _walk_types(argument)
        for parameter in value.parameter_types:
            yield from _walk_types(parameter)
        if value.return_type is not None:
            yield from _walk_types(value.return_type)
        return
    if isinstance(value, IRNode) or is_dataclass(value):
        for field in fields(value):
            yield from _walk_types(getattr(value, field.name))
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _walk_types(item)


def collect_generic_instances(
    module: IRModule,
    symbol_definitions: Mapping[str, DefId] | None = None,
) -> GenericInstancePlan:
    """Collect reachable concrete generic function instances deterministically."""
    functions = {function.symbol: function for function in module.functions}
    structs = {
        item.name: item for item in module.items
        if isinstance(item, IRStruct) and item.generic_params
    }
    enums = {
        item.name: item for item in module.items
        if isinstance(item, IREnum) and item.generic_params
    }
    fallback_module = ModuleId("hir", module.source_name)
    definitions = {
        item.symbol: DefId.from_path(fallback_module, index, item.symbol)
        for index, item in enumerate(module.items)
        if isinstance(item, (IRFunction, IRStruct, IREnum))
    }
    definitions.update(symbol_definitions or {})
    interner = TypeInterner()
    discovered: dict[str, GenericInstance] = {}
    pending: list[tuple[IRFunction, dict[str, IRType]]] = []
    pending_structs: list[tuple[IRStruct, dict[str, IRType]]] = []
    pending_enums: list[tuple[IREnum, dict[str, IRType]]] = []

    roots: list[object] = list(module.top_level_statements)
    roots.extend(function.body for function in module.functions if not function.generic_params)

    def discover(call: IRCall, caller_substitutions: Mapping[str, IRType]) -> None:
        function = functions.get(call.callee_symbol)
        if function is None or not function.generic_params:
            return
        params = frozenset(function.generic_params)
        substitutions: dict[str, IRType] = {}
        for parameter, argument in zip(function.params, call.args):
            _unify(
                parameter.type,
                substitute_type(argument.type, caller_substitutions),
                params,
                substitutions,
                function.name,
            )
        missing = tuple(name for name in function.generic_params if name not in substitutions)
        if missing:
            raise GenericInstanceError(
                "GEN0001",
                f"Cannot infer generic parameters {missing} for '{function.name}'",
            )
        arguments = tuple(substitutions[name] for name in function.generic_params)
        definition = definitions[function.symbol]
        type_arguments = tuple(interner.intern(item) for item in arguments)
        type_substitutions = tuple(
            (name, interner.intern(substitutions[name])) for name in sorted(substitutions)
        )
        instance_id = InstanceId(definition, type_arguments, type_substitutions)
        key = instance_id.stable_key()
        if key in discovered:
            return
        instance = GenericInstance(
            instance_id,
            definition,
            function.symbol,
            function.name,
            "function",
            arguments,
            tuple((name, substitutions[name]) for name in function.generic_params),
        )
        discovered[key] = instance
        pending.append((function, substitutions))

    def discover_type(value: IRType, caller_substitutions: Mapping[str, IRType]) -> None:
        concrete = substitute_type(value, caller_substitutions)
        aggregate = structs.get(concrete.name) or enums.get(concrete.name)
        if aggregate is None or len(concrete.arguments) != len(aggregate.generic_params):
            return
        if any(argument == ANY or argument.name in caller_substitutions for argument in concrete.arguments):
            return
        substitutions = dict(zip(aggregate.generic_params, concrete.arguments))
        definition = definitions[aggregate.symbol]
        type_arguments = tuple(interner.intern(item) for item in concrete.arguments)
        type_substitutions = tuple(
            (name, interner.intern(substitutions[name])) for name in sorted(substitutions)
        )
        instance_id = InstanceId(definition, type_arguments, type_substitutions)
        key = instance_id.stable_key()
        if key in discovered:
            return
        discovered[key] = GenericInstance(
            instance_id,
            definition,
            aggregate.symbol,
            aggregate.name,
            "struct" if isinstance(aggregate, IRStruct) else "enum",
            concrete.arguments,
            tuple((name, substitutions[name]) for name in aggregate.generic_params),
        )
        if isinstance(aggregate, IRStruct):
            pending_structs.append((aggregate, substitutions))
        else:
            pending_enums.append((aggregate, substitutions))

    for root in roots:
        for call in _walk_calls(root):
            discover(call, {})
        for value_type in _walk_types(root):
            discover_type(value_type, {})
    while pending:
        function, substitutions = pending.pop(0)
        for call in _walk_calls(function.body):
            discover(call, substitutions)
        for value_type in _walk_types(function.body):
            discover_type(value_type, substitutions)
    while pending_structs:
        struct, substitutions = pending_structs.pop(0)
        for value_type in _walk_types(struct.fields):
            discover_type(value_type, substitutions)
    while pending_enums:
        enum, substitutions = pending_enums.pop(0)
        for value_type in _walk_types(enum.members):
            discover_type(value_type, substitutions)

    return GenericInstancePlan(tuple(discovered[key] for key in sorted(discovered)))


def materialize_generic_instances(
    module: IRModule,
    plan: GenericInstancePlan | None = None,
) -> IRModule:
    """Produce closed Typed HIR functions for a collected generic instance plan."""
    plan = plan or collect_generic_instances(module)
    functions = {function.symbol: function for function in module.functions}
    structs = {
        item.symbol: item for item in module.items if isinstance(item, IRStruct)
    }
    enums = {
        item.symbol: item for item in module.items if isinstance(item, IREnum)
    }
    variants = {
        f"enum::{enum.name}::variant::{member.name}": (enum, member)
        for enum in enums.values()
        for member in enum.members
        if member.is_variant
    }
    instances_by_signature = {
        (item.symbol, tuple(argument.canonical() for argument in item.arguments)): item
        for item in plan.instances if item.kind == "function"
    }
    aggregate_instances = {
        (item.name, tuple(argument.canonical() for argument in item.arguments)): item
        for item in plan.instances if item.kind in {"struct", "enum"}
    }

    def concrete_type(value: IRType, substitutions: Mapping[str, IRType]) -> IRType:
        value = substitute_type(value, substitutions)
        value = IRType(
            value.name,
            tuple(concrete_type(item, {}) for item in value.arguments),
            value.optional,
            value.pointer,
            tuple(concrete_type(item, {}) for item in value.parameter_types),
            concrete_type(value.return_type, {}) if value.return_type else None,
        )
        instance = aggregate_instances.get(
            (value.name, tuple(argument.canonical() for argument in value.arguments))
        )
        if instance is None:
            return value
        return IRType(
            _concrete_name(instance), (), value.optional, value.pointer,
            value.parameter_types, value.return_type,
        )

    def transform(
        value: object,
        substitutions: Mapping[str, IRType],
        owner: tuple[str, str] | None = None,
    ) -> object:
        if isinstance(value, IRType):
            return concrete_type(value, substitutions)
        if isinstance(value, IRCall):
            transformed_args = tuple(transform(item, substitutions, owner) for item in value.args)
            transformed_receiver = (
                transform(value.receiver, substitutions, owner)
                if value.receiver is not None else None
            )
            transformed_type = concrete_type(value.type, substitutions)
            target = functions.get(value.callee_symbol)
            callee = value.callee
            callee_symbol = value.callee_symbol
            if target is not None and target.generic_params:
                inferred: dict[str, IRType] = {}
                generic_params = frozenset(target.generic_params)
                for parameter, argument in zip(target.params, transformed_args):
                    _unify(
                        parameter.type,
                        argument.type,
                        generic_params,
                        inferred,
                        target.name,
                    )
                signature = tuple(inferred[name].canonical() for name in target.generic_params)
                instance = instances_by_signature.get((target.symbol, signature))
                if instance is None:
                    raise GenericInstanceError(
                        "GEN0003",
                        f"Missing collected instance for '{target.name}{signature}'",
                    )
                callee = _concrete_name(instance)
                callee_symbol = _concrete_symbol(instance)
            elif value.callee_symbol in structs and structs[value.callee_symbol].generic_params:
                struct = structs[value.callee_symbol]
                inferred: dict[str, IRType] = {}
                generic_params = frozenset(struct.generic_params)
                for field, argument in zip(struct.fields, transformed_args):
                    _unify(
                        field.type, argument.type, generic_params, inferred, struct.name,
                    )
                signature = tuple(inferred[name].canonical() for name in struct.generic_params)
                instance = instances_by_signature.get((struct.symbol, signature))
                if instance is None:
                    instance = aggregate_instances.get((struct.name, signature))
                if instance is None:
                    raise GenericInstanceError(
                        "GEN0003",
                        f"Missing collected aggregate instance for '{struct.name}{signature}'",
                    )
                callee = _concrete_name(instance)
                callee_symbol = _concrete_symbol(instance)
            elif value.callee_symbol in variants:
                enum, member = variants[value.callee_symbol]
                if enum.generic_params:
                    inferred: dict[str, IRType] = {}
                    generic_params = frozenset(enum.generic_params)
                    for payload_type, argument in zip(member.payload_types, transformed_args):
                        _unify(
                            payload_type, argument.type, generic_params, inferred, enum.name,
                        )
                    signature = tuple(inferred[name].canonical() for name in enum.generic_params)
                    instance = aggregate_instances.get((enum.name, signature))
                    if instance is None:
                        raise GenericInstanceError(
                            "GEN0003",
                            f"Missing collected enum instance for '{enum.name}{signature}'",
                        )
                    callee_symbol = (
                        f"enum::{_concrete_name(instance)}::variant::{member.name}"
                    )
            elif owner and callee_symbol.startswith(owner[0]):
                callee_symbol = owner[1] + callee_symbol[len(owner[0]):]
            return replace(
                value,
                type=transformed_type,
                callee=callee,
                callee_symbol=callee_symbol,
                args=transformed_args,
                receiver=transformed_receiver,
            )
        if isinstance(value, IRNode) or is_dataclass(value):
            changes = {}
            for field in fields(value):
                item = getattr(value, field.name)
                if (
                    owner
                    and field.name in {"symbol", "error_symbol"}
                    and isinstance(item, str)
                    and item.startswith(owner[0])
                ):
                    changes[field.name] = owner[1] + item[len(owner[0]):]
                else:
                    changes[field.name] = transform(item, substitutions, owner)
            return replace(value, **changes)
        if isinstance(value, tuple):
            return tuple(transform(item, substitutions, owner) for item in value)
        if isinstance(value, list):
            return [transform(item, substitutions, owner) for item in value]
        return value

    materialized_items: list[IRNode] = []
    instances_by_symbol: dict[str, list[GenericInstance]] = {}
    for instance in plan.instances:
        instances_by_symbol.setdefault(instance.symbol, []).append(instance)

    for item in module.items:
        if isinstance(item, (IRFunction, IRStruct, IREnum)) and item.generic_params:
            for instance in sorted(
                instances_by_symbol.get(item.symbol, ()), key=GenericInstance.stable_key,
            ):
                substitutions = dict(instance.substitutions)
                concrete_symbol = _concrete_symbol(instance)
                concrete = transform(item, substitutions, (item.symbol, concrete_symbol))
                assert isinstance(concrete, (IRFunction, IRStruct, IREnum))
                materialized_items.append(
                    replace(
                        concrete,
                        name=_concrete_name(instance),
                        symbol=concrete_symbol,
                        generic_params=(),
                    )
                )
        else:
            transformed = transform(item, {})
            assert isinstance(transformed, IRNode)
            materialized_items.append(transformed)
    return replace(module, items=tuple(materialized_items))
