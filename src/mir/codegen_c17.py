"""C17 source emitter for legalized scalar/control-flow MIR."""

from __future__ import annotations

import json
import math
import re

from .codegen_cpp import MIRCodegenError
from .legalization import legalize_mir
from .model import (
    AggregateRValue, AssertTerminator, AssignStatement, BinaryRValue, CallTerminator,
    CastRValue, ConstantIndexProjection, ConstOperand, CopyOperand, DiscriminantRValue,
    FieldProjection, GotoTerminator, IndexProjection, MIRFunction, MIRModule, MIREnumDef,
    MIRStructDef, MoveOperand, NopStatement, Operand, PayloadRValue, Place, ReturnTerminator,
    StorageDeadStatement, StorageLiveStatement, SwitchIntTerminator,
    SwitchValueTerminator, UnaryRValue, UnreachableTerminator, UseRValue,
)
from .types import MIRType


_PRELUDE = r'''/* Experimental Nyx legalized MIR -> C17 output. */
#include <inttypes.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct NyxAllocation {
    char *value;
    struct NyxAllocation *next;
} NyxAllocation;

static NyxAllocation *nyx_allocations = NULL;

static void nyx_cleanup(void) {
    while (nyx_allocations != NULL) {
        NyxAllocation *allocation = nyx_allocations;
        nyx_allocations = allocation->next;
        free(allocation->value);
        free(allocation);
    }
}

static char *nyx_track_string(size_t length) {
    char *value = (char *)malloc(length);
    NyxAllocation *allocation = (NyxAllocation *)malloc(sizeof(NyxAllocation));
    if (value == NULL || allocation == NULL) {
        free(value);
        free(allocation);
        fputs("Nyx C17 allocation failed\n", stderr);
        exit(1);
    }
    allocation->value = value;
    allocation->next = nyx_allocations;
    nyx_allocations = allocation;
    return value;
}

static const char *nyx_concat(const char *left, const char *right) {
    size_t left_length = strlen(left);
    size_t right_length = strlen(right);
    char *result = nyx_track_string(left_length + right_length + 1);
    memcpy(result, left, left_length);
    memcpy(result + left_length, right, right_length + 1);
    return result;
}

typedef struct NyxArrayI64 {
    int64_t *data;
    size_t length;
} NyxArrayI64;

static NyxArrayI64 nyx_array_i64_make(const int64_t *source, size_t length) {
    NyxArrayI64 result = { NULL, length };
    if (length == 0) return result;
    result.data = (int64_t *)nyx_track_string(length * sizeof(int64_t));
    memcpy(result.data, source, length * sizeof(int64_t));
    return result;
}

static NyxArrayI64 nyx_array_i64_clone(NyxArrayI64 value) {
    return nyx_array_i64_make(value.data, value.length);
}

static int64_t *nyx_array_i64_at_mut(NyxArrayI64 *value, int64_t index) {
    if (index < 0 || (uint64_t)index >= value->length) {
        fputs("array index out of bounds\n", stderr);
        exit(1);
    }
    return &value->data[(size_t)index];
}

static void *nyx_box_array_i64(NyxArrayI64 value) {
    NyxArrayI64 *result = (NyxArrayI64 *)nyx_track_string(sizeof(NyxArrayI64));
    *result = nyx_array_i64_clone(value);
    return result;
}

typedef struct NyxArrayBool {
    bool *data;
    size_t length;
} NyxArrayBool;

static NyxArrayBool nyx_array_bool_make(const bool *source, size_t length) {
    NyxArrayBool result = { NULL, length };
    if (length == 0) return result;
    result.data = (bool *)nyx_track_string(length * sizeof(bool));
    memcpy(result.data, source, length * sizeof(bool));
    return result;
}

static NyxArrayBool nyx_array_bool_clone(NyxArrayBool value) {
    return nyx_array_bool_make(value.data, value.length);
}

static bool *nyx_array_bool_at_mut(NyxArrayBool *value, int64_t index) {
    if (index < 0 || (uint64_t)index >= value->length) {
        fputs("array index out of bounds\n", stderr);
        exit(1);
    }
    return &value->data[(size_t)index];
}

static void *nyx_box_array_bool(NyxArrayBool value) {
    NyxArrayBool *result = (NyxArrayBool *)nyx_track_string(sizeof(NyxArrayBool));
    *result = nyx_array_bool_clone(value);
    return result;
}

typedef struct NyxArrayString {
    const char **data;
    size_t length;
} NyxArrayString;

static NyxArrayString nyx_array_string_make(const char *const *source, size_t length) {
    NyxArrayString result = { NULL, length };
    if (length == 0) return result;
    result.data = (const char **)nyx_track_string(length * sizeof(const char *));
    memcpy(result.data, source, length * sizeof(const char *));
    return result;
}

static NyxArrayString nyx_array_string_clone(NyxArrayString value) {
    return nyx_array_string_make(value.data, value.length);
}

static const char **nyx_array_string_at_mut(NyxArrayString *value, int64_t index) {
    if (index < 0 || (uint64_t)index >= value->length) {
        fputs("array index out of bounds\n", stderr);
        exit(1);
    }
    return &value->data[(size_t)index];
}

static void *nyx_box_array_string(NyxArrayString value) {
    NyxArrayString *result = (NyxArrayString *)nyx_track_string(sizeof(NyxArrayString));
    *result = nyx_array_string_clone(value);
    return result;
}

typedef union NyxTaggedPayload {
    int64_t i64;
    bool boolean;
    const char *string;
    void *object;
} NyxTaggedPayload;

static uint64_t nyx_i64_bits(int64_t value) {
    uint64_t bits;
    memcpy(&bits, &value, sizeof(bits));
    return bits;
}

static int64_t nyx_i64_from_bits(uint64_t bits) {
    int64_t value;
    memcpy(&value, &bits, sizeof(value));
    return value;
}

static int64_t nyx_i64_add(int64_t left, int64_t right) {
    return nyx_i64_from_bits(nyx_i64_bits(left) + nyx_i64_bits(right));
}

static int64_t nyx_i64_sub(int64_t left, int64_t right) {
    return nyx_i64_from_bits(nyx_i64_bits(left) - nyx_i64_bits(right));
}

static int64_t nyx_i64_mul(int64_t left, int64_t right) {
    return nyx_i64_from_bits(nyx_i64_bits(left) * nyx_i64_bits(right));
}

static int64_t nyx_i64_div(int64_t left, int64_t right) {
    if (right == 0) { fputs("division by zero\n", stderr); exit(1); }
    if (left == INT64_MIN && right == -1) return INT64_MIN;
    return left / right;
}

static int64_t nyx_i64_rem(int64_t left, int64_t right) {
    if (right == 0) { fputs("remainder by zero\n", stderr); exit(1); }
    if (left == INT64_MIN && right == -1) return 0;
    return left % right;
}

static int64_t nyx_i64_shl(int64_t left, int64_t right) {
    return nyx_i64_from_bits(nyx_i64_bits(left) << (nyx_i64_bits(right) & 63U));
}

static int64_t nyx_i64_shr(int64_t left, int64_t right) {
    uint64_t count = nyx_i64_bits(right) & 63U;
    uint64_t bits = nyx_i64_bits(left);
    if (count == 0) return left;
    uint64_t shifted = bits >> count;
    if ((bits & (UINT64_C(1) << 63)) != 0) shifted |= UINT64_MAX << (64U - count);
    return nyx_i64_from_bits(shifted);
}

static int64_t nyx_i64_neg(int64_t value) {
    return nyx_i64_from_bits(UINT64_C(0) - nyx_i64_bits(value));
}

static void nyx_print_i64(int64_t value) { printf("%" PRId64, value); }
static void nyx_print_f64(double value) { printf("%.16g", value); }
static void nyx_print_bool(bool value) { fputs(value ? "true" : "false", stdout); }
static void nyx_print_string(const char *value) { fputs(value, stdout); }'''


def _identifier(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not clean or clean[0].isdigit():
        clean = "_" + clean
    return clean


class _C17Emitter:
    def __init__(self, module: MIRModule):
        self.module = module
        self.function_names = {
            function.symbol: f"nyx_fn_{_identifier(function.name)}"
            for function in module.functions
        }
        self.function_names.update({
            function.name: self.function_names[function.symbol]
            for function in module.functions
        })
        self.functions = {function.symbol: function for function in module.functions}
        self.functions.update({function.name: function for function in module.functions})
        self.structs = {
            definition.name: definition
            for definition in module.type_definitions
            if isinstance(definition, MIRStructDef)
        }
        self.enums = {
            definition.name: definition
            for definition in module.type_definitions
            if isinstance(definition, MIREnumDef)
        }
        self.current: MIRFunction | None = None
        self.local_types: dict[int, MIRType] = {}

    def emit(self) -> str:
        ordered_structs = self._ordered_structs()
        nested_arrays = self._nested_array_types()
        early_nested_arrays = tuple(
            value for value in nested_arrays
            if self._array_leaf(value).name in ("int", "bool", "string")
        )
        late_nested_arrays = tuple(
            value for value in nested_arrays if value not in early_nested_arrays
        )
        emitted_nested_arrays = set(early_nested_arrays)
        parts = [_PRELUDE, self._tagged_value_declaration()]
        if early_nested_arrays:
            parts.extend(("", "/* Nyx primitive-leaf nested-array declarations. */"))
            parts.extend(self._nested_array_declaration(value) for value in early_nested_arrays)
        parts.extend(("", "/* Nyx dependency-ordered nominal value declarations. */"))
        for definition in ordered_structs:
            required_arrays = tuple(
                value for value in self._nested_array_types_for_struct(definition)
                if value not in emitted_nested_arrays
            )
            parts.extend(self._nested_array_declaration(value) for value in required_arrays)
            emitted_nested_arrays.update(required_arrays)
            parts.append(self._struct_declaration(definition))
            parts.append(self._struct_array_type_declaration(definition))
            parts.append(self._struct_clone_declaration(definition))
            parts.append(self._struct_array_helpers(definition))
        remaining_nested_arrays = tuple(
            value for value in late_nested_arrays if value not in emitted_nested_arrays
        )
        if remaining_nested_arrays:
            parts.extend(("", "/* Nyx nested-array declarations. */"))
            parts.extend(self._nested_array_declaration(value) for value in remaining_nested_arrays)
        parts.extend(("", "/* Nyx function declarations. */"))
        parts.extend(self._prototype(function) + ";" for function in self.module.functions)
        parts.append("")
        parts.extend(self._function(function) + "\n" for function in self.module.functions)
        parts.append(self._entry_point())
        return "\n".join(parts).rstrip() + "\n"

    def _tagged_value_declaration(self) -> str:
        payload_slots = max(
            (len(variant.payload_types) for definition in self.enums.values()
             for variant in definition.variants),
            default=1,
        )
        payload_slots = max(payload_slots, 1)
        return f'''typedef struct NyxTaggedValue {{
    const char *tag;
    NyxTaggedPayload payload[{payload_slots}];
}} NyxTaggedValue;'''

    def _ordered_structs(self) -> tuple[MIRStructDef, ...]:
        ordered: list[MIRStructDef] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(definition: MIRStructDef) -> None:
            if definition.name in visited:
                return
            if definition.name in visiting:
                raise MIRCodegenError(
                    f"recursive by-value C17 struct '{definition.name}' was not legalized"
                )
            visiting.add(definition.name)
            for field in definition.fields:
                dependency_type = field.type
                if (
                    dependency_type.name == "Array"
                    and len(dependency_type.arguments) == 1
                ):
                    dependency_type = dependency_type.arguments[0]
                    while (
                        dependency_type.name == "Array"
                        and len(dependency_type.arguments) == 1
                    ):
                        dependency_type = dependency_type.arguments[0]
                dependency = self.structs.get(dependency_type.name)
                if dependency is not None:
                    visit(dependency)
            visiting.remove(definition.name)
            visited.add(definition.name)
            ordered.append(definition)

        for definition in self.structs.values():
            visit(definition)
        return tuple(ordered)

    def _struct_declaration(self, definition: MIRStructDef) -> str:
        name = self._struct_name(definition.name)
        fields = "\n".join(
            f"    {self._type(field.type)} {_identifier(field.name)};"
            for field in definition.fields
        )
        return f"typedef struct {name} {{\n{fields}\n}} {name};"

    def _struct_clone_declaration(self, definition: MIRStructDef) -> str:
        rendered = self._struct_name(definition.name)
        lines = [
            f"static {rendered} nyx_struct_{_identifier(definition.name)}_clone({rendered} value) {{",
            "    " + rendered + " result = value;",
        ]
        for field in definition.fields:
            name = _identifier(field.name)
            if field.type.name == "Array":
                suffix = self._array_suffix(field.type.arguments[0])
                lines.append(
                    f"    result.{name} = nyx_array_{suffix}_clone(value.{name});"
                )
            elif field.type.name in self.structs:
                lines.append(
                    f"    result.{name} = nyx_struct_{_identifier(field.type.name)}_clone(value.{name});"
                )
        lines.extend(("    return result;", "}"))
        return "\n".join(lines)

    def _struct_array_type_declaration(self, definition: MIRStructDef) -> str:
        element = self._struct_name(definition.name)
        array = self._array_type(MIRType("Array", (MIRType(definition.name),)))
        return f'''typedef struct {array} {{
    {element} *data;
    size_t length;
}} {array};'''

    def _struct_array_helpers(self, definition: MIRStructDef) -> str:
        element = self._struct_name(definition.name)
        array = self._array_type(MIRType("Array", (MIRType(definition.name),)))
        suffix = self._array_suffix(MIRType(definition.name))
        return f'''static {array} nyx_array_{suffix}_make(const {element} *source, size_t length) {{
    {array} result = {{ NULL, length }};
    if (length == 0) return result;
    result.data = ({element} *)nyx_track_string(length * sizeof({element}));
    for (size_t index = 0; index < length; ++index) {{
        result.data[index] = nyx_struct_{_identifier(definition.name)}_clone(source[index]);
    }}
    return result;
}}

static {array} nyx_array_{suffix}_clone({array} value) {{
    return nyx_array_{suffix}_make(value.data, value.length);
}}

static {element} *nyx_array_{suffix}_at_mut({array} *value, int64_t index) {{
    if (index < 0 || (uint64_t)index >= value->length) {{
        fputs("array index out of bounds\\n", stderr);
        exit(1);
    }}
    return &value->data[(size_t)index];
}}

static void *nyx_box_{_identifier(definition.name)}({element} value) {{
    {element} *result = ({element} *)nyx_track_string(sizeof({element}));
    *result = nyx_struct_{_identifier(definition.name)}_clone(value);
    return result;
}}

static void *nyx_box_array_{suffix}({array} value) {{
    {array} *result = ({array} *)nyx_track_string(sizeof({array}));
    *result = nyx_array_{suffix}_clone(value);
    return result;
}}'''

    def _nested_array_declaration(self, value: MIRType) -> str:
        element = value.arguments[0]
        outer = self._array_type(value)
        inner = self._array_type(element)
        outer_suffix = self._array_suffix(element)
        inner_suffix = self._array_suffix(element.arguments[0])
        return f'''typedef struct {outer} {{
    {inner} *data;
    size_t length;
}} {outer};

static {outer} nyx_array_{outer_suffix}_make(const {inner} *source, size_t length) {{
    {outer} result = {{ NULL, length }};
    if (length == 0) return result;
    result.data = ({inner} *)nyx_track_string(length * sizeof({inner}));
    for (size_t index = 0; index < length; ++index) {{
        result.data[index] = nyx_array_{inner_suffix}_clone(source[index]);
    }}
    return result;
}}

static {outer} nyx_array_{outer_suffix}_clone({outer} value) {{
    return nyx_array_{outer_suffix}_make(value.data, value.length);
}}

static {inner} *nyx_array_{outer_suffix}_at_mut({outer} *value, int64_t index) {{
    if (index < 0 || (uint64_t)index >= value->length) {{
        fputs("array index out of bounds\\n", stderr);
        exit(1);
    }}
    return &value->data[(size_t)index];
}}

static void *nyx_box_array_{outer_suffix}({outer} value) {{
    {outer} *result = ({outer} *)nyx_track_string(sizeof({outer}));
    *result = nyx_array_{outer_suffix}_clone(value);
    return result;
}}'''

    def _nested_array_types(self) -> tuple[MIRType, ...]:
        found: set[MIRType] = set()

        def visit(value: MIRType) -> None:
            if value.name != "Array" or len(value.arguments) != 1:
                return
            element = value.arguments[0]
            visit(element)
            if element.name == "Array" and self._is_supported_array(value):
                found.add(value)

        for function in self.module.functions:
            for local in function.locals:
                visit(local.type)
        for definition in self.structs.values():
            for field in definition.fields:
                visit(field.type)
        return tuple(sorted(found, key=self._array_depth))

    def _nested_array_types_for_struct(
        self, definition: MIRStructDef
    ) -> tuple[MIRType, ...]:
        found: set[MIRType] = set()

        def visit(value: MIRType) -> None:
            if value.name != "Array" or len(value.arguments) != 1:
                return
            element = value.arguments[0]
            visit(element)
            if element.name == "Array" and self._is_supported_array(value):
                found.add(value)

        for field in definition.fields:
            visit(field.type)
        return tuple(sorted(found, key=self._array_depth))

    @staticmethod
    def _array_depth(value: MIRType) -> int:
        depth = 0
        while value.name == "Array" and len(value.arguments) == 1:
            depth += 1
            value = value.arguments[0]
        return depth

    @staticmethod
    def _array_leaf(value: MIRType) -> MIRType:
        while value.name == "Array" and len(value.arguments) == 1:
            value = value.arguments[0]
        return value

    def _prototype(self, function: MIRFunction) -> str:
        parameters = ", ".join(
            f"{self._type(function.locals[local].type, function)} l{local}"
            for local in function.parameters
        ) or "void"
        return f"static {self._type(function.locals[function.return_local].type, function)} {self.function_names[function.symbol]}({parameters})"

    def _entry_point(self) -> str:
        by_name = {function.name: function for function in self.module.functions}
        entry = by_name.get("main") or by_name.get("__nyx_top_level")
        lines = ["int main(void) {", "    if (atexit(nyx_cleanup) != 0) return 1;"]
        if entry is not None:
            call = f"{self.function_names[entry.symbol]}()"
            result = self._type(entry.locals[entry.return_local].type, entry)
            lines.append(f"    {call};" if result == "void" else f"    (void){call};")
        lines.extend(("    return 0;", "}"))
        return "\n".join(lines)

    def _function(self, function: MIRFunction) -> str:
        self.current = function
        self.local_types = {local.id: local.type for local in function.locals}
        lines = [self._prototype(function) + " {"]
        parameter_ids = set(function.parameters)
        for local in function.locals:
            rendered = self._type(local.type, function)
            if local.id in parameter_ids or rendered == "void":
                continue
            lines.append(f"    {rendered} l{local.id} = {self._default(local.type)};")
        lines.extend(("    int pc = 0;", "    for (;;) {", "        switch (pc) {"))
        for block in function.blocks:
            lines.append(f"        case {block.id}:")
            for statement in block.statements:
                lines.extend(f"            {line}" for line in self._statement(statement))
            lines.extend(f"            {line}" for line in self._terminator(block.terminator))
        lines.extend(("        default:", "            fputs(\"invalid MIR block\\n\", stderr);", "            exit(1);", "        }", "    }", "}"))
        self.current = None
        self.local_types = {}
        return "\n".join(lines)

    def _statement(self, value: object) -> list[str]:
        if isinstance(value, AssignStatement):
            if value.place.projections:
                return [f"{self._place(value.place)} = {self._rvalue(value.value)};"]
            if self.local_types[value.place.local].name in ("void", "any"):
                return []
            return [f"l{value.place.local} = {self._rvalue(value.value)};"]
        if isinstance(value, (StorageLiveStatement, StorageDeadStatement, NopStatement)):
            return []
        raise MIRCodegenError(f"illegal statement reached C17 emitter: {type(value).__name__}")

    def _terminator(self, value: object) -> list[str]:
        if isinstance(value, GotoTerminator):
            return self._goto(value.target)
        if isinstance(value, (SwitchIntTerminator, SwitchValueTerminator)):
            discriminator = self._operand(value.discriminator)
            discriminator_type = self._operand_type(value.discriminator)
            lines: list[str] = []
            for expected, target in value.targets:
                rendered = self._constant(expected, discriminator_type)
                comparison = (
                    f"strcmp({discriminator}, {rendered}) == 0"
                    if discriminator_type.name == "string"
                    else f"{discriminator} == {rendered}"
                )
                lines.append(f"if ({comparison}) {{")
                lines.extend(f"    {line}" for line in self._goto(target))
                lines.append("}")
            lines.extend(self._goto(value.otherwise))
            return lines
        if isinstance(value, CallTerminator):
            if value.target is None:
                raise MIRCodegenError(f"call '{value.function}' has no continuation")
            arguments = ", ".join(self._operand(argument) for argument in value.arguments)
            if value.function == "builtin::print":
                lines = []
                for index, argument in enumerate(value.arguments):
                    if index:
                        lines.append("fputc(' ', stdout);")
                    lines.append(f"{self._print_function(self._operand_type(argument))}({self._operand(argument)});")
                lines.append("fputc('\\n', stdout);")
                return lines + self._goto(value.target)
            if value.function == "builtin::len":
                if len(value.arguments) != 1 or value.destination is None:
                    raise MIRCodegenError("builtin::len requires one argument and a destination")
                argument = value.arguments[0]
                argument_type = self._operand_type(argument)
                rendered = (
                    self._place(argument.place)
                    if isinstance(argument, (CopyOperand, MoveOperand))
                    else self._operand(argument)
                )
                if argument_type.name == "string":
                    length = f"strlen({rendered})"
                elif argument_type.name == "Array":
                    length = f"{rendered}.length"
                else:
                    raise MIRCodegenError(f"C17 len does not support MIR type '{argument_type}'")
                return [
                    f"l{value.destination.local} = (int64_t)({length});"
                ] + self._goto(value.target)
            if value.function not in self.function_names:
                raise MIRCodegenError(f"illegal runtime call reached C17 emitter: {value.function}")
            call = f"{self.function_names[value.function]}({arguments})"
            callee = self.functions[value.function]
            result = self._type(callee.locals[callee.return_local].type, callee)
            line = (
                f"l{value.destination.local} = {call};"
                if value.destination is not None and result != "void"
                else f"{call};"
            )
            return [line] + self._goto(value.target)
        if isinstance(value, AssertTerminator):
            expected = "true" if value.expected else "false"
            message = json.dumps(value.message, ensure_ascii=False)
            return [
                f"if (((bool)({self._operand(value.condition)})) != {expected}) {{",
                f"    fputs({message}, stderr);",
                "    fputc('\\n', stderr);",
                "    exit(1);",
                "}",
            ] + self._goto(value.target)
        if isinstance(value, ReturnTerminator):
            assert self.current is not None
            result = self._type(self.current.locals[self.current.return_local].type, self.current)
            return ["return;"] if result == "void" else ["return l0;"]
        if isinstance(value, UnreachableTerminator):
            return ["fputs(\"reached unreachable MIR terminator\\n\", stderr);", "exit(1);"]
        raise MIRCodegenError(f"illegal terminator reached C17 emitter: {type(value).__name__}")

    @staticmethod
    def _goto(target: int) -> list[str]:
        return [f"pc = {target};", "continue;"]

    def _rvalue(self, value: object) -> str:
        if isinstance(value, UseRValue):
            return self._operand(value.operand)
        if isinstance(value, CastRValue):
            operand = self._operand(value.operand)
            source_type = self._operand_type(value.operand)
            if value.kind == "implicit" and source_type == value.type:
                return operand
            if self._is_tagged_type(value.type):
                return operand
            if value.kind == "optional-unwrap":
                rendered = f"({operand}).payload[0].{self._tag_payload_field(value.type)}"
                if value.type.name in self.structs or value.type.name == "Array":
                    return f"(*({self._type(value.type)} *){rendered})"
                return rendered
            raise MIRCodegenError(
                f"unsupported C17 cast '{value.kind}' from '{source_type}' to '{value.type}'"
            )
        if isinstance(value, AggregateRValue):
            if value.kind == "array" and self._is_supported_array(value.type):
                operands = ", ".join(self._operand(operand) for operand in value.operands)
                element = value.type.arguments[0]
                source = f"({self._type(element)}[]){{ {operands} }}" if operands else "NULL"
                return f"nyx_array_{self._array_suffix(element)}_make({source}, {len(value.operands)})"
            if value.kind in ("enum", "option", "result") and self._is_tagged_type(value.type):
                if value.operands:
                    slots = []
                    for operand in value.operands:
                        payload_type = self._operand_type(operand)
                        field = self._tag_payload_field(payload_type)
                        rendered = self._operand(operand)
                        if field == "object":
                            rendered = f"{self._box_helper(payload_type)}({rendered})"
                        slots.append(f"{{ .{field} = {rendered} }}")
                    payload = ", ".join(slots)
                else:
                    payload = "{ .i64 = INT64_C(0) }"
                return (
                    f"(NyxTaggedValue){{ .tag = {json.dumps(value.name)}, "
                    f".payload = {{ {payload} }} }}"
                )
            if value.kind != "struct" or value.type.name not in self.structs:
                raise MIRCodegenError(f"unsupported C17 aggregate '{value.kind} {value.type}'")
            definition = self.structs[value.type.name]
            fields = value.fields or tuple(field.name for field in definition.fields)
            initializers = ", ".join(
                f".{_identifier(name)} = {self._operand(operand)}"
                for name, operand in zip(fields, value.operands)
            )
            return f"({self._type(value.type)}){{ {initializers} }}"
        if isinstance(value, DiscriminantRValue):
            return f"({self._operand(value.operand)}).tag"
        if isinstance(value, PayloadRValue):
            rendered = f"({self._operand(value.operand)}).payload[{value.index}].{self._tag_payload_field(value.type)}"
            if value.type.name in self.structs or value.type.name == "Array":
                return f"(*({self._type(value.type)} *){rendered})"
            return rendered
        if isinstance(value, BinaryRValue):
            return self._binary(value)
        if isinstance(value, UnaryRValue):
            operand = self._operand(value.operand)
            if value.op in ("!", "not"):
                return f"!({operand})"
            if value.op == "+":
                return operand
            if value.op == "-" and value.type.name == "int":
                return f"nyx_i64_neg({operand})"
            if value.op == "-":
                return f"-({operand})"
            if value.op == "~":
                return f"nyx_i64_from_bits(~nyx_i64_bits({operand}))"
            raise MIRCodegenError(f"unsupported C17 unary operation '{value.op}'")
        raise MIRCodegenError(f"illegal rvalue reached C17 emitter: {type(value).__name__}")

    def _binary(self, value: BinaryRValue) -> str:
        left = self._operand(value.left)
        right = self._operand(value.right)
        left_type = self._operand_type(value.left)
        right_type = self._operand_type(value.right)
        if value.op in ("==", "!=", "<", "<=", ">", ">="):
            if left_type.name == "string" and right_type.name == "string":
                relation = {"==": "== 0", "!=": "!= 0", "<": "< 0", "<=": "<= 0", ">": "> 0", ">=": ">= 0"}[value.op]
                return f"(strcmp({left}, {right}) {relation})"
            return f"({left} {value.op} {right})"
        if value.op == "+" and left_type.name == "string" and right_type.name == "string":
            return f"nyx_concat({left}, {right})"
        if left_type.name in ("float", "f64") or right_type.name in ("float", "f64"):
            if value.op in ("+", "-", "*", "/"):
                return f"({left} {value.op} {right})"
            if value.op == "%":
                return f"fmod({left}, {right})"
        operations = {
            "+": "nyx_i64_add", "-": "nyx_i64_sub", "*": "nyx_i64_mul",
            "/": "nyx_i64_div", "%": "nyx_i64_rem", "<<": "nyx_i64_shl",
            ">>": "nyx_i64_shr",
        }
        if value.op in operations:
            return f"{operations[value.op]}({left}, {right})"
        if value.op in ("&", "|", "^"):
            return f"nyx_i64_from_bits(nyx_i64_bits({left}) {value.op} nyx_i64_bits({right}))"
        raise MIRCodegenError(f"unsupported C17 binary operation '{value.op}'")

    def _operand(self, value: Operand) -> str:
        if isinstance(value, ConstOperand):
            return self._typed_constant(value)
        if isinstance(value, (CopyOperand, MoveOperand)):
            rendered = self._place(value.place)
            place_type = self._place_type(value.place)
            if isinstance(value, CopyOperand) and place_type.name == "Array":
                return f"nyx_array_{self._array_suffix(place_type.arguments[0])}_clone({rendered})"
            if isinstance(value, CopyOperand) and place_type.name in self.structs:
                return f"nyx_struct_{_identifier(place_type.name)}_clone({rendered})"
            return rendered
        raise MIRCodegenError(f"illegal operand reached C17 emitter: {type(value).__name__}")

    def _operand_type(self, value: Operand) -> MIRType:
        if isinstance(value, ConstOperand):
            return value.type
        if isinstance(value, (CopyOperand, MoveOperand)):
            return self._place_type(value.place)
        raise MIRCodegenError(f"unknown C17 operand type: {type(value).__name__}")

    @staticmethod
    def _typed_constant(value: ConstOperand) -> str:
        if value.type.name == "int":
            bits = int(value.value) & ((1 << 64) - 1)
            return f"nyx_i64_from_bits(UINT64_C({bits}))"
        if value.type.name == "string":
            return json.dumps(str(value.value), ensure_ascii=False)
        if value.type.name == "bool":
            return "true" if value.value else "false"
        if value.type.name in ("float", "f64"):
            number = float(value.value)
            if math.isnan(number):
                return "NAN"
            if math.isinf(number):
                return "INFINITY" if number > 0 else "-INFINITY"
            return repr(number)
        raise MIRCodegenError(f"unsupported C17 constant type '{value.type}'")

    @staticmethod
    def _constant(value: object, value_type: MIRType) -> str:
        if value_type.name == "string":
            return json.dumps(str(value), ensure_ascii=False)
        if value_type.name == "bool":
            return "true" if bool(value) else "false"
        return str(value)

    def _type(self, value: MIRType, function: MIRFunction | None = None) -> str:
        if value.name == "any" and function is not None and function.name in ("main", "__nyx_top_level"):
            return "void"
        mapping = {
            "void": "void", "bool": "bool", "int": "int64_t",
            "float": "double", "f64": "double", "string": "const char *",
        }
        if self._is_supported_array(value):
            return self._array_type(value)
        if self._is_tagged_type(value):
            return "NyxTaggedValue"
        rendered = self._struct_name(value.name) if value.name in self.structs else mapping.get(value.name)
        if rendered is None or value.optional or value.pointer or value.arguments:
            raise MIRCodegenError(f"unsupported C17 MIR type '{value}'")
        return rendered

    def _default(self, value: MIRType) -> str:
        if self._is_supported_array(value):
            return f"({self._array_type(value)}){{ NULL, 0 }}"
        if self._is_tagged_type(value):
            return "(NyxTaggedValue){ \"\", { { .i64 = INT64_C(0) } } }"
        if value.name in self.structs:
            return f"({self._type(value)}){{0}}"
        return {"bool": "false", "int": "INT64_C(0)", "float": "0.0", "f64": "0.0", "string": "\"\""}.get(value.name, "0")

    def _place(self, place: Place) -> str:
        rendered = f"l{place.local}"
        value_type = self.local_types[place.local]
        for projection in place.projections:
            if isinstance(projection, FieldProjection):
                definition = self.structs.get(value_type.name)
                field = next(
                    (item for item in definition.fields if item.name == projection.name),
                    None,
                ) if definition is not None else None
                if field is None:
                    raise MIRCodegenError(f"C17 struct '{value_type}' has no field '{projection.name}'")
                rendered += f".{_identifier(projection.name)}"
                value_type = field.type
            elif isinstance(projection, (IndexProjection, ConstantIndexProjection)):
                if not self._is_supported_array(value_type):
                    raise MIRCodegenError(f"C17 index projection requires a supported array, got '{value_type}'")
                index = f"l{projection.local}" if isinstance(projection, IndexProjection) else str(projection.index)
                element = value_type.arguments[0]
                rendered = f"(*nyx_array_{self._array_suffix(element)}_at_mut(&({rendered}), {index}))"
                value_type = element
            else:
                raise MIRCodegenError(f"illegal projection reached C17 emitter: {type(projection).__name__}")
        return rendered

    def _place_type(self, place: Place) -> MIRType:
        value_type = self.local_types[place.local]
        for projection in place.projections:
            if isinstance(projection, FieldProjection):
                definition = self.structs.get(value_type.name)
                field = next(
                    (item for item in definition.fields if item.name == projection.name),
                    None,
                ) if definition is not None else None
                if field is None:
                    raise MIRCodegenError(f"C17 struct '{value_type}' has no field '{projection.name}'")
                value_type = field.type
            elif isinstance(projection, (IndexProjection, ConstantIndexProjection)):
                if not self._is_supported_array(value_type):
                    raise MIRCodegenError(f"C17 index projection requires a supported array, got '{value_type}'")
                value_type = value_type.arguments[0]
            else:
                raise MIRCodegenError(f"illegal C17 projection type: {type(projection).__name__}")
        return value_type

    @staticmethod
    def _struct_name(value: str) -> str:
        return f"NyxStruct_{_identifier(value)}"

    def _is_supported_array(self, value: MIRType) -> bool:
        if value.name != "Array" or len(value.arguments) != 1:
            return False
        element = value.arguments[0]
        if element.optional or element.pointer:
            return False
        if element.name == "Array":
            return self._is_supported_array(element)
        return bool(
            not element.arguments
            and (
                element.name in ("int", "bool", "string")
                or element.name in self.structs
            )
        )

    def _array_type(self, value: MIRType) -> str:
        if not self._is_supported_array(value):
            raise MIRCodegenError(f"unsupported C17 array type '{value}'")
        element = value.arguments[0]
        if element.name == "Array":
            return f"NyxArrayNested_{_identifier(self._array_suffix(element))}"
        return {
            "int": "NyxArrayI64",
            "bool": "NyxArrayBool",
            "string": "NyxArrayString",
        }.get(element.name, f"NyxArrayStruct_{_identifier(element.name)}")

    def _array_suffix(self, element: MIRType) -> str:
        if element.name == "Array" and len(element.arguments) == 1:
            return f"nested_{self._array_suffix(element.arguments[0])}"
        return {
            "int": "i64",
            "bool": "bool",
            "string": "string",
        }.get(element.name, f"struct_{_identifier(element.name)}")

    def _is_tagged_type(self, value: MIRType) -> bool:
        return bool(
            value.name in ("Option", "Result")
            or (
                value.name in self.enums
                and not value.arguments
                and not value.optional
                and not value.pointer
            )
        )

    def _tag_payload_field(self, value: MIRType) -> str:
        mapping = {"int": "i64", "bool": "boolean", "string": "string"}
        field = mapping.get(value.name)
        if field is not None:
            return field
        if value.name in self.structs and not value.arguments and not value.optional and not value.pointer:
            return "object"
        if self._is_supported_array(value):
            return "object"
        raise MIRCodegenError(f"unsupported C17 tagged payload type '{value}'")

    def _box_helper(self, value: MIRType) -> str:
        if value.name in self.structs:
            return f"nyx_box_{_identifier(value.name)}"
        if self._is_supported_array(value):
            return f"nyx_box_array_{self._array_suffix(value.arguments[0])}"
        raise MIRCodegenError(f"unsupported C17 boxed payload type '{value}'")

    @staticmethod
    def _print_function(value: MIRType) -> str:
        mapping = {
            "bool": "nyx_print_bool", "int": "nyx_print_i64",
            "float": "nyx_print_f64", "f64": "nyx_print_f64",
            "string": "nyx_print_string",
        }
        result = mapping.get(value.name)
        if result is None:
            raise MIRCodegenError(f"C17 print does not support MIR type '{value}'")
        return result


def emit_legalized_c17(module: MIRModule) -> str:
    return _C17Emitter(legalize_mir(module, "c", require_emitter=True)).emit()
