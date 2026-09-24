"""Target-neutral Rove type identities used by the structured typed HIR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Tuple


INTEGER_TYPE_NAMES = frozenset(("int", "i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "uintptr"))


@dataclass(frozen=True, slots=True)
class IRType:
    name: str
    arguments: Tuple["IRType", ...] = ()
    optional: bool = False
    pointer: bool = False
    parameter_types: Tuple["IRType", ...] = ()
    return_type: Optional["IRType"] = None

    @property
    def is_function(self) -> bool:
        return self.return_type is not None

    @property
    def is_numeric(self) -> bool:
        return self.name in INTEGER_TYPE_NAMES | {"float", "f32", "f64"} and not self.optional and not self.pointer

    @property
    def is_unknown(self) -> bool:
        return self.name == "any"

    def with_optional(self, optional: bool = True) -> "IRType":
        return IRType(
            self.name,
            self.arguments,
            optional,
            self.pointer,
            self.parameter_types,
            self.return_type,
        )

    def canonical(self) -> str:
        if self.is_function:
            params = ",".join(item.canonical() for item in self.parameter_types)
            rendered = f"fn({params})->{self.return_type.canonical()}"
        else:
            rendered = self.name
            if self.arguments:
                rendered += "<" + ",".join(item.canonical() for item in self.arguments) + ">"
            if self.pointer:
                rendered = "*" + rendered
        if self.optional:
            rendered += "?"
        return rendered

    def __str__(self) -> str:
        return self.canonical()


ANY = IRType("any")
VOID = IRType("void")
NULL = IRType("null", optional=True)
BOOL = IRType("bool")
INT = IRType("int")
FLOAT = IRType("float")
STRING = IRType("string")


def array_of(element_type: IRType) -> IRType:
    return IRType("Array", (element_type,))


def task_of(result_type: IRType) -> IRType:
    return IRType("Task", (result_type,))


def function_type(parameters: Iterable[IRType], result: IRType) -> IRType:
    return IRType("fn", parameter_types=tuple(parameters), return_type=result)


def from_type_node(type_node: object, default: IRType = ANY) -> IRType:
    if type_node is None:
        return default
    if isinstance(type_node, IRType):
        return type_node

    name = str(getattr(type_node, "name", type_node))
    generic_args = tuple(from_type_node(item) for item in getattr(type_node, "generic_args", ()) or ())
    optional = bool(getattr(type_node, "is_optional", False))
    pointer = bool(getattr(type_node, "is_pointer", False))
    if getattr(type_node, "is_fn_type", False):
        params = tuple(from_type_node(item) for item in getattr(type_node, "param_types", ()) or ())
        result = from_type_node(getattr(type_node, "return_type", None), VOID)
        return IRType("fn", optional=optional, parameter_types=params, return_type=result)
    return IRType(name, generic_args, optional, pointer)


def from_inferred_name(name: object, default: IRType = ANY) -> IRType:
    if isinstance(name, IRType):
        return name
    if not name:
        return default
    text = str(name).strip()
    optional = text.endswith("?")
    if optional:
        text = text[:-1]
    pointer = text.startswith("*")
    if pointer:
        text = text[1:]
    generic_start = text.find("<")
    if generic_start > 0 and text.endswith(">"):
        generic_name = text[:generic_start].strip()
        inner = text[generic_start + 1:-1]
        arguments = []
        depth = 0
        start = 0
        for index, character in enumerate(inner):
            if character == "<":
                depth += 1
            elif character == ">":
                depth -= 1
            elif character == "," and depth == 0:
                arguments.append(from_inferred_name(inner[start:index].strip()))
                start = index + 1
        if inner.strip():
            arguments.append(from_inferred_name(inner[start:].strip()))
        return IRType(generic_name, tuple(arguments), optional, pointer)
    return IRType(text, optional=optional, pointer=pointer)


def is_exact_type(left: IRType, right: IRType) -> bool:
    """Return whether two resolved HIR type identities are identical."""
    return left == right


def is_assignable(expected: IRType, actual: IRType) -> bool:
    """Check assignment without inserting a numeric or pointer conversion."""
    if expected.is_unknown or actual.is_unknown:
        return True
    if actual.name == "null":
        return expected.optional or expected.name in ("Option", "Result")
    if is_exact_type(expected, actual):
        return True
    if expected.optional and not actual.optional:
        return is_assignable(expected.with_optional(False), actual)
    if expected.optional != actual.optional or expected.pointer != actual.pointer:
        return False
    if expected.is_function or actual.is_function:
        return False
    if expected.name == actual.name and len(expected.arguments) == len(actual.arguments):
        return all(
            is_assignable(left, right)
            for left, right in zip(expected.arguments, actual.arguments)
        )
    return False


def is_coercible(source: IRType, destination: IRType) -> bool:
    """Check whether the frontend may insert a defined implicit conversion."""
    if is_assignable(destination, source):
        return True
    if source.optional or destination.optional or source.pointer or destination.pointer:
        return False
    if source.name in INTEGER_TYPE_NAMES and destination.name in INTEGER_TYPE_NAMES:
        return True
    if source.name in INTEGER_TYPE_NAMES and destination.name in ("float", "f32", "f64"):
        return True
    return False


def is_abi_compatible(left: IRType, right: IRType, target: str) -> bool:
    """Conservatively compare scalar representation for a concrete target ABI."""
    if left.optional != right.optional or left.is_function or right.is_function:
        return is_exact_type(left, right)
    if is_exact_type(left, right):
        return True

    normalized_target = {
        "c17": "c",
        "javascript": "js",
        "node": "js",
        "react": "js",
    }.get(target.lower(), target.lower())
    if normalized_target in ("js", "python"):
        return False

    pointer_bits = 32 if normalized_target == "wasm" else 64
    if left.pointer or right.pointer:
        return left.pointer and right.pointer and pointer_bits > 0

    integer_widths = {
        "i8": 8, "u8": 8,
        "i16": 16, "u16": 16,
        "i32": 32, "u32": 32,
        "int": 64, "i64": 64, "u64": 64,
        "uintptr": pointer_bits,
    }
    float_widths = {"f32": 32, "float": 64, "f64": 64}
    if left.name in integer_widths and right.name in integer_widths:
        return integer_widths[left.name] == integer_widths[right.name]
    if left.name in float_widths and right.name in float_widths:
        return float_widths[left.name] == float_widths[right.name]
    return False


def compatible(expected: IRType, actual: IRType) -> bool:
    """Legacy transitional compatibility; do not use for identity or ABI checks."""
    if is_assignable(expected, actual) or is_coercible(actual, expected):
        return True
    # Transitional uninstantiated generic and pointer behavior retained only
    # for old HIR consumers while they migrate to the precise predicates.
    if expected.pointer and actual.pointer:
        return True
    if expected.name == actual.name and (not expected.arguments or not actual.arguments):
        return True
    if expected.name == actual.name and expected.arguments and actual.arguments:
        return len(expected.arguments) == len(actual.arguments) and all(
            compatible(left, right) for left, right in zip(expected.arguments, actual.arguments)
        )
    return False
