"""Read-only compiler-stage inspection contracts for the Rove CLI and tools."""

from __future__ import annotations

from dataclasses import is_dataclass
import json
from typing import Any, TYPE_CHECKING

from src.core.ast_nodes import ASTNode, EnumMember, FunctionParam
from src.ir import IRModule, fingerprint, to_data
from src.mir.layout import LayoutEngine, MIRLayoutError
from src.mir.model import MIREnumDef, MIRModule, MIRStructDef
from src.mir.types import MIRType

if TYPE_CHECKING:
    from src.core.module_loader import LoadedProgramGraph


AST_INSPECTION_SCHEMA_VERSION = 1
HIR_INSPECTION_SCHEMA_VERSION = 1
MODULE_GRAPH_INSPECTION_SCHEMA_VERSION = 1
LAYOUT_INSPECTION_SCHEMA_VERSION = 1
TYPE_INSPECTION_SCHEMA_VERSION = 1
CAPABILITY_INSPECTION_SCHEMA_VERSION = 1


def ast_to_data(value: Any) -> Any:
    """Convert parser nodes to deterministic, JSON-safe inspection data."""
    if isinstance(value, (ASTNode, FunctionParam, EnumMember)):
        result = {"node": type(value).__name__}
        for name in sorted(vars(value)):
            if not name.startswith("_"):
                result[name] = ast_to_data(getattr(value, name))
        return result
    if isinstance(value, tuple):
        return [ast_to_data(item) for item in value]
    if isinstance(value, list):
        return [ast_to_data(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): ast_to_data(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if is_dataclass(value):
        # Parser extensions occasionally carry immutable value objects. Reuse
        # the canonical HIR serializer for those instead of stringifying them.
        return to_data(value)
    raise TypeError(
        f"AST value is not inspectable without an explicit schema: {type(value).__name__}"
    )


def ast_document(ast: ASTNode, source: str) -> dict[str, Any]:
    return {
        "schema_version": AST_INSPECTION_SCHEMA_VERSION,
        "stage": "ast",
        "source": source,
        "root": ast_to_data(ast),
    }


def hir_document(hir: IRModule) -> dict[str, Any]:
    return {
        "schema_version": HIR_INSPECTION_SCHEMA_VERSION,
        "stage": "hir",
        "source": hir.source_name,
        "target": hir.target,
        "hir_schema_version": hir.schema_version,
        "fingerprint": fingerprint(hir),
        "root": to_data(hir),
    }


def module_graph_document(loaded: "LoadedProgramGraph") -> dict[str, Any]:
    """Serialize retained module boundaries without exposing mutable loader state."""
    modules = []
    for module_id, record in sorted(
        loaded.graph.modules.items(), key=lambda item: item[0].stable_key()
    ):
        modules.append({
            "id": module_id.stable_key(),
            "path": record.filepath,
            "source_id": record.source_id.stable_key(),
            "imports": [item.stable_key() for item in record.imports],
            "exports": [
                {"name": name, "definition": definition.stable_key()}
                for name, definition in record.exports
            ],
            "interface_fingerprint": record.interface_fingerprint,
            "implementation_fingerprint": record.implementation_fingerprint,
        })
    root_record = loaded.graph.record(loaded.root)
    return {
        "schema_version": MODULE_GRAPH_INSPECTION_SCHEMA_VERSION,
        "stage": "module-graph",
        "source": root_record.filepath,
        "root": {
            "module": loaded.root.stable_key(),
            "module_count": len(modules),
            "modules": modules,
        },
    }


def _layout_types(module: MIRModule) -> list[MIRType]:
    found: dict[str, MIRType] = {}

    def visit(value_type: MIRType) -> None:
        key = value_type.canonical()
        if key in found:
            return
        found[key] = value_type
        for argument in value_type.arguments:
            visit(argument)
        for parameter in value_type.parameter_types:
            visit(parameter)
        if value_type.return_type is not None:
            visit(value_type.return_type)

    for definition in module.type_definitions:
        visit(MIRType(definition.name))
        if isinstance(definition, MIRStructDef):
            for field in definition.fields:
                visit(field.type)
        elif isinstance(definition, MIREnumDef):
            for variant in definition.variants:
                for payload in variant.payload_types:
                    visit(payload)
    for function in module.functions:
        for local in function.locals:
            visit(local.type)
    return [found[key] for key in sorted(found)]


def layout_document(module: MIRModule, target: str) -> dict[str, Any]:
    engine = LayoutEngine(module, target)
    types = []
    for value_type in _layout_types(module):
        item: dict[str, Any] = {"type": value_type.canonical()}
        try:
            layout = engine.layout_of(value_type)
        except MIRLayoutError as error:
            item["error"] = str(error)
        else:
            item.update({
                "kind": layout.kind,
                "size": layout.size,
                "alignment": layout.alignment,
                "tag_size": layout.tag_size,
                "payload_offset": layout.payload_offset,
                "fields": [
                    {
                        "name": field.name,
                        "type": field.type.canonical(),
                        "offset": field.offset,
                        "size": field.layout.size,
                        "alignment": field.layout.alignment,
                    }
                    for field in layout.fields
                ],
                "variants": [
                    {
                        "name": variant.name,
                        "payload_size": variant.payload_size,
                        "payload_alignment": variant.payload_alignment,
                    }
                    for variant in layout.variants
                ],
            })
        types.append(item)
    data_layout = engine.target
    return {
        "schema_version": LAYOUT_INSPECTION_SCHEMA_VERSION,
        "stage": "layout",
        "source": module.source_name,
        "target": target,
        "root": {
            "data_layout": {
                "name": data_layout.name,
                "pointer_size": data_layout.pointer_size,
                "pointer_alignment": data_layout.pointer_alignment,
                "aggregate_alignment": data_layout.aggregate_alignment,
                "endian": data_layout.endian,
            },
            "types": types,
        },
    }


def types_document(hir: IRModule) -> dict[str, Any]:
    from src.ir import (
        IREnum,
        IRExternFunction,
        IRFunction,
        IRImpl,
        IRStruct,
        IRTrait,
        IRTypeAlias,
    )

    declarations: list[dict[str, Any]] = []

    def function_data(function: IRFunction | IRExternFunction) -> dict[str, Any]:
        item = {
            "kind": "extern-function" if isinstance(function, IRExternFunction) else "function",
            "name": function.name,
            "symbol": function.symbol,
            "parameters": [
                {"name": parameter.name, "type": parameter.type.canonical()}
                for parameter in function.params
            ],
            "return_type": function.return_type.canonical(),
        }
        if isinstance(function, IRFunction):
            item["generic_parameters"] = list(function.generic_params)
            item["async"] = function.is_async
        else:
            item["abi"] = function.abi
            item["varargs"] = function.varargs
        return item

    for item in hir.items:
        if isinstance(item, (IRFunction, IRExternFunction)):
            declarations.append(function_data(item))
        elif isinstance(item, IRStruct):
            declarations.append({
                "kind": "struct",
                "name": item.name,
                "symbol": item.symbol,
                "generic_parameters": list(item.generic_params),
                "fields": [
                    {"name": field.name, "type": field.type.canonical()}
                    for field in item.fields
                ],
            })
        elif isinstance(item, IREnum):
            declarations.append({
                "kind": "enum",
                "name": item.name,
                "symbol": item.symbol,
                "generic_parameters": list(item.generic_params),
                "variants": [
                    {
                        "name": member.name,
                        "payload_types": [value.canonical() for value in member.payload_types],
                    }
                    for member in item.members
                ],
            })
        elif isinstance(item, IRTypeAlias):
            declarations.append({
                "kind": "type-alias",
                "name": item.name,
                "symbol": item.symbol,
                "type": item.actual_type.canonical(),
            })
        elif isinstance(item, IRTrait):
            declarations.append({
                "kind": "trait",
                "name": item.name,
                "symbol": item.symbol,
                "methods": [function_data(method) for method in item.methods],
            })
        elif isinstance(item, IRImpl):
            declarations.append({
                "kind": "impl",
                "trait": item.trait_name,
                "target_type": item.target_type,
                "methods": [function_data(method) for method in item.methods],
            })
    declarations.sort(
        key=lambda item: (
            str(item.get("kind", "")),
            str(item.get("name", item.get("target_type", ""))),
            str(item.get("symbol", "")),
        )
    )
    return {
        "schema_version": TYPE_INSPECTION_SCHEMA_VERSION,
        "stage": "types",
        "source": hir.source_name,
        "target": hir.target,
        "root": {
            "declaration_count": len(declarations),
            "declarations": declarations,
        },
    }


def capability_document(hir: IRModule) -> dict[str, Any]:
    from src.api import backend_feature_requirements
    from src.core.backend_capabilities import resolve_backend
    from src.mir import mir_backend_manifest

    backend = resolve_backend(hir.target)
    if backend is None:
        raise ValueError(f"Unknown backend '{hir.target}'")
    required = backend_feature_requirements(hir)
    missing = tuple(feature for feature in required if feature not in backend.features)
    mir_profile = next(
        (
            profile
            for profile in mir_backend_manifest()["profiles"]
            if profile["target"] == backend.name
        ),
        None,
    )
    return {
        "schema_version": CAPABILITY_INSPECTION_SCHEMA_VERSION,
        "stage": "capabilities",
        "source": hir.source_name,
        "target": backend.name,
        "root": {
            "status": "satisfied" if not missing else "rejected",
            "required_features": list(required),
            "missing_features": list(missing),
            "backend": backend.to_dict(),
            "mir": mir_profile,
            "note": (
                "This is the current direct feature contract, not a fallback or adapter plan."
            ),
        },
    }


def inspection_json(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def render_inspection_tree(document: dict[str, Any]) -> str:
    """Render the same inspection document as a complete human-readable tree."""
    header = [
        f"{document['stage'].upper()} inspection schema v{document['schema_version']}",
        f"source: {document['source']}",
    ]
    if "target" in document:
        header.append(f"target: {document['target']}")
    if "fingerprint" in document:
        header.append(f"fingerprint: {document['fingerprint']}")
    lines = header + [""]
    _render_value(document["root"], lines, 0, None)
    return "\n".join(lines).rstrip() + "\n"


def _render_value(
    value: Any,
    lines: list[str],
    depth: int,
    label: str | None,
) -> None:
    indent = "  " * depth
    prefix = f"{label}: " if label is not None else ""
    if isinstance(value, dict):
        node_name = value.get("node")
        if isinstance(node_name, str):
            lines.append(f"{indent}{prefix}{node_name}")
            for name, item in value.items():
                if name != "node":
                    _render_value(item, lines, depth + 1, name)
            return
        lines.append(f"{indent}{prefix}{{")
        for name, item in value.items():
            _render_value(item, lines, depth + 1, name)
        lines.append(f"{indent}}}")
        return
    if isinstance(value, list):
        lines.append(f"{indent}{prefix}[{len(value)}]")
        for index, item in enumerate(value):
            _render_value(item, lines, depth + 1, f"[{index}]")
        return
    lines.append(f"{indent}{prefix}{json.dumps(value, ensure_ascii=False)}")


__all__ = [
    "AST_INSPECTION_SCHEMA_VERSION",
    "CAPABILITY_INSPECTION_SCHEMA_VERSION",
    "HIR_INSPECTION_SCHEMA_VERSION",
    "LAYOUT_INSPECTION_SCHEMA_VERSION",
    "MODULE_GRAPH_INSPECTION_SCHEMA_VERSION",
    "TYPE_INSPECTION_SCHEMA_VERSION",
    "ast_document",
    "capability_document",
    "hir_document",
    "inspection_json",
    "layout_document",
    "module_graph_document",
    "render_inspection_tree",
    "types_document",
]
