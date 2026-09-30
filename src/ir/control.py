"""Control-flow facts shared by hosted HIR emitters."""

from dataclasses import fields, is_dataclass
from typing import Iterable

from .model import IRAwait, IRCall, IRExpr, IRLambda, IRReference


def _children(value: object):
    if is_dataclass(value):
        for field in fields(value):
            if field.name not in ("span", "type"):
                yield getattr(value, field.name)
    elif isinstance(value, (tuple, list)):
        yield from value


def immediate_callback_suspends(value: object) -> bool:
    """Collection callbacks execute immediately, including their suspension."""
    return (
        isinstance(value, IRCall)
        and value.callee_symbol in ("builtin::map", "builtin::filter", "builtin::fold")
        and bool(value.args)
        and isinstance(value.args[-1], IRLambda)
        and expression_suspends(value.args[-1].body)
    )


def expression_suspends(value: object) -> bool:
    if isinstance(value, IRAwait):
        return True
    if isinstance(value, IRLambda):
        return False
    return immediate_callback_suspends(value) or any(
        expression_suspends(child) for child in _children(value)
    )


def free_local_references(
    expression: IRExpr, bound_symbols: Iterable[str] = (),
) -> tuple[IRReference, ...]:
    """Find value captures, including captures needed by nested callbacks."""
    references: dict[str, IRReference] = {}

    def visit(value: object, bound: frozenset[str]) -> None:
        if isinstance(value, IRReference):
            if (
                value.symbol not in bound
                and not value.symbol.startswith("module::")
                and ("::local::" in value.symbol or "::param::" in value.symbol)
            ):
                references.setdefault(value.symbol, value)
        elif isinstance(value, IRLambda):
            visit(value.body, bound | frozenset(param.symbol for param in value.params))
        else:
            for child in _children(value):
                visit(child, bound)

    visit(expression, frozenset(bound_symbols))
    return tuple(references.values())
