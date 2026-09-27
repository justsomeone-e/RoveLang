"""Deterministic target storage layouts for logical MIR types."""

from __future__ import annotations

from dataclasses import dataclass

from .model import MIREnumDef, MIRModule, MIRStructDef
from .types import MIRType


class MIRLayoutError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TargetDataLayout:
    name: str
    pointer_size: int
    pointer_alignment: int
    aggregate_alignment: int
    endian: str = "little"


@dataclass(frozen=True, slots=True)
class FieldLayout:
    name: str
    type: MIRType
    offset: int
    layout: "TypeLayout"


@dataclass(frozen=True, slots=True)
class VariantLayout:
    name: str
    payload_size: int
    payload_alignment: int


@dataclass(frozen=True, slots=True)
class TypeLayout:
    type: MIRType
    size: int
    alignment: int
    kind: str
    fields: tuple[FieldLayout, ...] = ()
    variants: tuple[VariantLayout, ...] = ()
    tag_size: int = 0
    payload_offset: int = 0


NATIVE_X64 = TargetDataLayout("native-x86_64", 8, 8, 16)
WASM32 = TargetDataLayout("wasm32", 4, 4, 8)
HOSTED_X64 = TargetDataLayout("hosted-x86_64", 8, 8, 16)

TARGET_DATA_LAYOUTS = {
    "cpp": NATIVE_X64,
    "llvm": NATIVE_X64,
    "c": NATIVE_X64,
    "asm": NATIVE_X64,
    "rust": NATIVE_X64,
    "wasm": WASM32,
    "js": HOSTED_X64,
    "python": HOSTED_X64,
    "react": HOSTED_X64,
}


def data_layout_for_target(target: str) -> TargetDataLayout:
    try:
        return TARGET_DATA_LAYOUTS[target]
    except KeyError as error:
        raise MIRLayoutError(f"No MIR data layout is defined for target '{target}'") from error


class LayoutEngine:
    def __init__(self, module: MIRModule, target: str | TargetDataLayout):
        self.module = module
        self.target = data_layout_for_target(target) if isinstance(target, str) else target
        self.definitions = {definition.name: definition for definition in module.type_definitions}
        self._cache: dict[MIRType, TypeLayout] = {}
        self._active: set[MIRType] = set()

    def layout_of(self, value_type: MIRType) -> TypeLayout:
        cached = self._cache.get(value_type)
        if cached is not None:
            return cached
        if value_type in self._active:
            raise MIRLayoutError(
                f"Recursive by-value type '{value_type}' requires an explicit pointer or descriptor"
            )
        self._active.add(value_type)
        try:
            result = self._compute(value_type)
        finally:
            self._active.remove(value_type)
        self._cache[value_type] = result
        return result

    def _compute(self, value_type: MIRType) -> TypeLayout:
        pointer_size = self.target.pointer_size
        pointer_alignment = self.target.pointer_alignment
        if value_type.pointer or value_type.is_function:
            return TypeLayout(value_type, pointer_size, pointer_alignment, "pointer")

        scalar = {
            "void": (0, 1),
            "bool": (1, 1),
            "i8": (1, 1),
            "u8": (1, 1),
            "i16": (2, 2),
            "u16": (2, 2),
            "i32": (4, 4),
            "u32": (4, 4),
            "char": (4, 4),
            "int": (8, 8),
            "i64": (8, 8),
            "u64": (8, 8),
            "float": (8, 8),
            "f64": (8, 8),
            "f32": (4, 4),
            "uintptr": (pointer_size, pointer_alignment),
        }.get(value_type.name)
        if scalar is not None and not value_type.optional:
            return TypeLayout(value_type, scalar[0], scalar[1], "scalar")

        if value_type.name in ("string", "Array") and not value_type.optional:
            return TypeLayout(
                value_type,
                pointer_size * 3,
                pointer_alignment,
                "owned-descriptor",
            )
        if value_type.name in ("Task", "Channel", "Iterator") and not value_type.optional:
            return TypeLayout(value_type, pointer_size, pointer_alignment, "runtime-handle")
        if value_type.name == "any" and not value_type.optional:
            return TypeLayout(value_type, pointer_size * 2, pointer_alignment, "tagged-dynamic")

        definition = self.definitions.get(value_type.name)
        if isinstance(definition, MIRStructDef) and not value_type.optional:
            return self._struct_layout(value_type, definition)
        if isinstance(definition, MIREnumDef) and not value_type.optional:
            return self._enum_layout(value_type, definition)

        if value_type.name == "Option" and value_type.arguments:
            return self._tagged_layout(value_type, (value_type.arguments[0],), "option")
        if value_type.name == "Result" and value_type.arguments:
            return self._tagged_layout(value_type, value_type.arguments[:2], "result")
        if value_type.optional:
            base = MIRType(
                value_type.name,
                value_type.arguments,
                False,
                value_type.pointer,
                value_type.parameter_types,
                value_type.return_type,
            )
            if base.pointer:
                return TypeLayout(value_type, pointer_size, pointer_alignment, "nullable-pointer")
            return self._tagged_layout(value_type, (base,), "optional")

        raise MIRLayoutError(f"No physical layout is defined for MIR type '{value_type}'")

    def _struct_layout(self, value_type: MIRType, definition: MIRStructDef) -> TypeLayout:
        offset = 0
        alignment = 1
        fields: list[FieldLayout] = []
        for field in definition.fields:
            field_layout = self.layout_of(field.type)
            offset = _align_up(offset, field_layout.alignment)
            fields.append(FieldLayout(field.name, field.type, offset, field_layout))
            offset += field_layout.size
            alignment = max(alignment, field_layout.alignment)
        alignment = min(max(alignment, 1), self.target.aggregate_alignment)
        return TypeLayout(
            value_type,
            _align_up(offset, alignment),
            alignment,
            "struct",
            tuple(fields),
        )

    def _enum_layout(self, value_type: MIRType, definition: MIREnumDef) -> TypeLayout:
        variants = []
        payload_size = 0
        payload_alignment = 1
        for variant in definition.variants:
            layout = self._tuple_payload_layout(variant.payload_types)
            variants.append(VariantLayout(variant.name, layout[0], layout[1]))
            payload_size = max(payload_size, layout[0])
            payload_alignment = max(payload_alignment, layout[1])
        tag_size = 4
        alignment = min(
            max(tag_size, payload_alignment),
            self.target.aggregate_alignment,
        )
        payload_offset = _align_up(tag_size, payload_alignment)
        return TypeLayout(
            value_type,
            _align_up(payload_offset + payload_size, alignment),
            alignment,
            "enum",
            variants=tuple(variants),
            tag_size=tag_size,
            payload_offset=payload_offset,
        )

    def _tagged_layout(
        self,
        value_type: MIRType,
        payload_types: tuple[MIRType, ...],
        kind: str,
    ) -> TypeLayout:
        payload_size = 0
        payload_alignment = 1
        variants = [] if kind == "result" else [VariantLayout("None", 0, 1)]
        for index, payload_type in enumerate(payload_types):
            layout = self.layout_of(payload_type)
            payload_size = max(payload_size, layout.size)
            payload_alignment = max(payload_alignment, layout.alignment)
            name = "Some" if kind != "result" else ("Ok" if index == 0 else "Err")
            variants.append(VariantLayout(name, layout.size, layout.alignment))
        tag_size = 1
        payload_offset = _align_up(tag_size, payload_alignment)
        alignment = min(max(payload_alignment, 1), self.target.aggregate_alignment)
        return TypeLayout(
            value_type,
            _align_up(payload_offset + payload_size, alignment),
            alignment,
            kind,
            variants=tuple(variants),
            tag_size=tag_size,
            payload_offset=payload_offset,
        )

    def _tuple_payload_layout(self, payload_types: tuple[MIRType, ...]) -> tuple[int, int]:
        offsets = self.tuple_payload_offsets(payload_types)
        alignment = max(
            (self.layout_of(payload_type).alignment for payload_type in payload_types),
            default=1,
        )
        size = (
            offsets[-1] + self.layout_of(payload_types[-1]).size
            if offsets else 0
        )
        return _align_up(size, alignment), alignment

    def tuple_payload_offsets(self, payload_types: tuple[MIRType, ...]) -> tuple[int, ...]:
        """Return each field's offset within an enum variant's payload."""
        offsets = []
        offset = 0
        for payload_type in payload_types:
            layout = self.layout_of(payload_type)
            offset = _align_up(offset, layout.alignment)
            offsets.append(offset)
            offset += layout.size
        return tuple(offsets)


def _align_up(value: int, alignment: int) -> int:
    if alignment <= 0:
        raise MIRLayoutError("Alignment must be positive")
    return (value + alignment - 1) // alignment * alignment
