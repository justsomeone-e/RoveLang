"""Target-independent static method and trait dispatch materialization."""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace

from .model import (
    IRCall,
    IRFunction,
    IRImpl,
    IRModule,
    IRNode,
    IRParameter,
    IRReference,
    IRTrait,
)
from .types import ANY, IRType


class StaticDispatchError(ValueError):
    pass


def materialize_static_dispatch(module: IRModule) -> IRModule:
    """Resolve receiver calls to concrete impl methods before MIR lowering."""
    methods: dict[tuple[str, str], IRFunction] = {}
    self_types: dict[str, IRType] = {}
    for item in module.items:
        if not isinstance(item, IRImpl):
            continue
        target = IRType(item.target_type)
        for method in item.methods:
            key = (item.target_type, method.name)
            if key in methods:
                raise StaticDispatchError(
                    f"Ambiguous static dispatch for '{item.target_type}.{method.name}'"
                )
            methods[key] = method
            if method.params and method.params[0].name in ("self", "this"):
                self_types[method.params[0].symbol] = target

    if not methods:
        return module

    def transform(value: object) -> object:
        if isinstance(value, IRReference) and value.symbol in self_types:
            return replace(value, type=self_types[value.symbol])
        if isinstance(value, IRCall):
            receiver = transform(value.receiver) if value.receiver is not None else None
            arguments = tuple(transform(argument) for argument in value.args)
            assert receiver is None or isinstance(receiver, IRNode)
            key = (receiver.type.name, value.callee) if receiver is not None else None
            selected = methods.get(key) if key is not None else None
            if selected is None:
                return replace(value, receiver=receiver, args=arguments)
            return replace(
                value,
                callee=selected.name,
                callee_symbol=selected.symbol,
                receiver=None,
                args=(receiver,) + arguments,
            )
        if isinstance(value, IRNode) or is_dataclass(value):
            return replace(value, **{
                field.name: transform(getattr(value, field.name)) for field in fields(value)
            })
        if isinstance(value, tuple):
            return tuple(transform(item) for item in value)
        if isinstance(value, list):
            return [transform(item) for item in value]
        return value

    output: list[IRNode] = []
    for item in module.items:
        if isinstance(item, IRTrait):
            continue
        if isinstance(item, IRImpl):
            for method in item.methods:
                transformed = transform(method)
                assert isinstance(transformed, IRFunction)
                parameters = list(transformed.params)
                if parameters and parameters[0].name in ("self", "this"):
                    parameters[0] = replace(
                        parameters[0], type=IRType(item.target_type),
                    )
                output.append(replace(transformed, params=tuple(parameters)))
            continue
        transformed = transform(item)
        assert isinstance(transformed, IRNode)
        output.append(transformed)
    return replace(module, items=tuple(output))
