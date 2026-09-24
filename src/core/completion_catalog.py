"""Canonical completion metadata shared by the LSP and editor package.

The catalog is derived from compiler registries and parsed Rove stdlib sources,
so editor suggestions cannot drift into APIs that do not exist.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from .ast_nodes import (
    EnumDefNode,
    FunctionDefNode,
    StructDefNode,
    TypeAliasNode,
    VarDeclNode,
)
from .backend_capabilities import BACKENDS, STDLIB_CONTRACTS
from .language_surface import (
    BUILTIN_NAMES,
    EXPERIMENTAL_KEYWORDS,
    RESERVED_KEYWORDS,
    STABLE_KEYWORDS,
    TYPE_NAMES,
)
from .lexer import Lexer
from .parser import Parser


_BUILTIN_DETAILS = {
    "print": ("fn print(...args) -> void", "Writes values to standard output."),
    "input": ('fn input(prompt: string = "") -> string', "Reads one line from standard input."),
    "addr": ("unsafe fn addr(value) -> uintptr", "Returns the address of a value inside an unsafe boundary."),
    "peek": ("unsafe fn peek(address: uintptr) -> uintptr", "Reads a machine word from a raw address."),
    "memdump": ("unsafe fn memdump(address: uintptr, count: int = 16) -> void", "Prints raw bytes for diagnostics."),
    "channel": ("fn channel<T>() -> Channel<T>", "Creates a typed CSP channel."),
    "Ok": ("fn Ok<T>(value: T) -> Result<T, any>", "Constructs a successful Result value."),
    "Err": ("fn Err<E>(error: E) -> Result<any, E>", "Constructs an error Result value."),
    "len": ("fn len<T>(value: T) -> int", "Returns a collection, buffer, or string length."),
    "args": ("fn args() -> Array<string>", "Returns process command-line arguments on hosted targets."),
    "to_string": ("fn to_string<T>(value: T) -> string", "Formats a value using canonical Rove scalar text."),
    "to_int": ("fn to_int(value: string) -> int", "Parses a signed Rove integer."),
    "contains": ("fn contains(value: string, part: string) -> bool", "Tests whether a string contains a substring."),
    "is_number": ("fn is_number(value: string) -> bool", "Tests whether text has numeric syntax."),
    "delay_ms": ("fn delay_ms(milliseconds: int) -> void", "Suspends or delays for the requested milliseconds."),
    "map": ("fn map<T, U>(items: Array<T>, transform: fn(T) -> U) -> Array<U>", "Transforms each array element in order."),
    "filter": ("fn filter<T>(items: Array<T>, predicate: fn(T) -> bool) -> Array<T>", "Keeps array elements whose predicate is true."),
    "fold": ("fn fold<T, A>(items: Array<T>, initial: A, reducer: fn(A, T) -> A) -> A", "Reduces an array from left to right."),
}


def _type_text(value: Any, default: str = "any") -> str:
    if value is None:
        return default
    rendered = str(value)
    return rendered if rendered else default


def _function_detail(node: FunctionDefNode) -> str:
    generic = f"<{', '.join(node.generic_params)}>" if node.generic_params else ""
    params = ", ".join(
        f"{parameter.name}: {_type_text(parameter.type_annot)}"
        for parameter in node.params
    )
    return f"fn {node.name}{generic}({params}) -> {_type_text(node.return_type, 'void')}"


def _stdlib_catalog(root: Path) -> tuple[List[dict], List[dict]]:
    modules: List[dict] = []
    symbols: List[dict] = []
    stdlib_dir = root / "src" / "stdlib"
    for module_name, contract in sorted(STDLIB_CONTRACTS.items()):
        source_path = stdlib_dir / f"{module_name}.rove"
        if not source_path.is_file():
            continue
        module_path = f"std/{module_name}"
        modules.append({
            "name": module_path,
            "detail": f"Rove stdlib · {contract.maturity}",
            "documentation": contract.note or f"Standard library module {module_path}.",
            "targets": sorted(contract.targets),
        })

        source = source_path.read_text(encoding="utf-8-sig")
        ast = Parser(Lexer(source, str(source_path)).tokenize(), source, str(source_path)).parse()
        for statement in ast.statements:
            name = getattr(statement, "name", "")
            if not name or name.startswith("_"):
                continue
            if isinstance(statement, FunctionDefNode):
                kind = "function"
                detail = _function_detail(statement)
            elif isinstance(statement, StructDefNode):
                kind = "struct"
                detail = f"struct {name}"
            elif isinstance(statement, EnumDefNode):
                kind = "enum"
                detail = f"enum {name}"
            elif isinstance(statement, TypeAliasNode):
                kind = "type"
                detail = f"type {name} = {_type_text(statement.actual_type)}"
            elif isinstance(statement, VarDeclNode) and statement.is_const:
                kind = "constant"
                detail = f"const {name}: {_type_text(statement.type_annot)}"
            else:
                continue
            symbols.append({
                "label": name,
                "kind": kind,
                "detail": detail,
                "module": module_path,
                "documentation": getattr(statement, "doc_comment", "") or f"Declared by {module_path}.",
                "targets": sorted(contract.targets),
            })
    return modules, symbols


@lru_cache(maxsize=1)
def completion_catalog() -> Dict[str, list]:
    root = Path(__file__).resolve().parents[2]
    modules, symbols = _stdlib_catalog(root)
    builtins = [
        {
            "label": name,
            "detail": _BUILTIN_DETAILS[name][0],
            "documentation": _BUILTIN_DETAILS[name][1],
        }
        for name in BUILTIN_NAMES
    ]
    targets = [
        {
            "name": name,
            "detail": spec.display_name,
            "documentation": f"{spec.artifact} · {spec.maturity}",
        }
        for name, spec in sorted(BACKENDS.items())
    ]
    return {
        "stableKeywords": list(STABLE_KEYWORDS),
        "experimentalKeywords": list(EXPERIMENTAL_KEYWORDS),
        "reservedKeywords": list(RESERVED_KEYWORDS),
        "builtinNames": list(BUILTIN_NAMES),
        "typeNames": list(TYPE_NAMES),
        "builtinFunctions": builtins,
        "stdlibModules": modules,
        "stdlibSymbols": symbols,
        "targets": targets,
        "boards": [],
    }
