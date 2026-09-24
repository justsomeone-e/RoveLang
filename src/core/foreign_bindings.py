"""Versioned, data-only type contracts for foreign ecosystem modules."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from types import MappingProxyType
from typing import Dict, Mapping, Optional, Tuple


FOREIGN_BINDING_SCHEMA_VERSION = 1
_TYPE_NAME = re.compile(r"[A-Za-z_*][A-Za-z0-9_:.<>?, *-]*")


@dataclass(frozen=True)
class ForeignCallableBinding:
    params: Tuple[str, ...]
    returns: str


@dataclass(frozen=True)
class ForeignTypeBinding:
    name: str
    methods: Mapping[str, ForeignCallableBinding]


@dataclass(frozen=True)
class ForeignModuleBinding:
    ecosystem: str
    module: str
    functions: Mapping[str, ForeignCallableBinding]
    types: Mapping[str, ForeignTypeBinding]

    @property
    def module_type(self) -> str:
        return f"foreign-module::{self.ecosystem}::{self.module}"


class ForeignBindingRegistry:
    def __init__(self, modules: Mapping[Tuple[str, str], ForeignModuleBinding]):
        self._modules = MappingProxyType(dict(modules))

    def resolve(self, ecosystem: str, module: str) -> Optional[ForeignModuleBinding]:
        return self._modules.get((ecosystem, module))

    @classmethod
    def load(cls, base_dir: str) -> "ForeignBindingRegistry":
        builtin = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "bindings",
            "foreign_api_v1.json",
        )
        paths = [builtin]
        project = _find_project_manifest(base_dir)
        if project is not None:
            paths.append(project)

        modules: Dict[Tuple[str, str], ForeignModuleBinding] = {}
        for path in paths:
            if not os.path.isfile(path):
                continue
            for binding in _read_manifest(path):
                modules[(binding.ecosystem, binding.module)] = binding
        return cls(modules)


def _find_project_manifest(base_dir: str) -> Optional[str]:
    current = os.path.abspath(base_dir or os.getcwd())
    if os.path.isfile(current):
        current = os.path.dirname(current)
    while True:
        for filename in ("rove.bindings.json", "nyx.bindings.json"):
            candidate = os.path.join(current, filename)
            if os.path.isfile(candidate):
                return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _callable(value: object, context: str) -> ForeignCallableBinding:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    params = value.get("params", [])
    returns = value.get("returns", "void")
    if not isinstance(params, list) or not all(isinstance(item, str) for item in params):
        raise ValueError(f"{context}.params must be an array of type names")
    if not isinstance(returns, str) or not _TYPE_NAME.fullmatch(returns):
        raise ValueError(f"{context}.returns is not a valid type name")
    for parameter in params:
        if not _TYPE_NAME.fullmatch(parameter):
            raise ValueError(f"{context} contains invalid parameter type '{parameter}'")
    return ForeignCallableBinding(tuple(params), returns)


def _read_manifest(path: str) -> Tuple[ForeignModuleBinding, ...]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read foreign binding manifest '{path}': {error}") from error
    if not isinstance(data, dict) or data.get("schema_version") != FOREIGN_BINDING_SCHEMA_VERSION:
        raise ValueError(
            f"Foreign binding manifest '{path}' requires schema_version "
            f"{FOREIGN_BINDING_SCHEMA_VERSION}"
        )
    raw_modules = data.get("modules")
    if not isinstance(raw_modules, list):
        raise ValueError(f"Foreign binding manifest '{path}' requires a modules array")

    result = []
    for index, raw in enumerate(raw_modules):
        context = f"{path}:modules[{index}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{context} must be an object")
        ecosystem = raw.get("ecosystem")
        module = raw.get("module")
        if ecosystem not in ("cpp", "js", "python") or not isinstance(module, str) or not module:
            raise ValueError(f"{context} requires a supported ecosystem and non-empty module")
        raw_functions = raw.get("functions", {})
        raw_types = raw.get("types", {})
        if not isinstance(raw_functions, dict) or not isinstance(raw_types, dict):
            raise ValueError(f"{context} functions and types must be objects")
        functions = {
            name: _callable(spec, f"{context}.functions.{name}")
            for name, spec in raw_functions.items()
            if isinstance(name, str) and name
        }
        types: Dict[str, ForeignTypeBinding] = {}
        for type_name, type_spec in raw_types.items():
            if not isinstance(type_name, str) or not isinstance(type_spec, dict):
                raise ValueError(f"{context}.types entries must be named objects")
            methods_value = type_spec.get("methods", {})
            if not isinstance(methods_value, dict):
                raise ValueError(f"{context}.types.{type_name}.methods must be an object")
            methods = {
                name: _callable(spec, f"{context}.types.{type_name}.methods.{name}")
                for name, spec in methods_value.items()
                if isinstance(name, str) and name
            }
            types[type_name] = ForeignTypeBinding(type_name, MappingProxyType(methods))
        result.append(
            ForeignModuleBinding(
                ecosystem,
                module,
                MappingProxyType(functions),
                MappingProxyType(types),
            )
        )
    return tuple(result)
