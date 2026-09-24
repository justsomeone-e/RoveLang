"""C17 source emitter for legalized Rove MIR."""

from __future__ import annotations

import json
import math
import re

from .codegen_cpp import MIRCodegenError
from .legalization import legalize_mir
from .model import (
    AggregateRValue, AssertTerminator, AssignStatement, BinaryRValue, CallTerminator,
    CastRValue, ConstantIndexProjection, ConstOperand, CopyOperand, DeinitStatement, DiscriminantRValue,
    DropTerminator, FieldProjection, GotoTerminator, IndexProjection, MIRFunction, MIRModule, MIREnumDef,
    MIRStructDef, MoveOperand, NopStatement, Operand, PayloadRValue, Place, ReturnTerminator,
    StorageDeadStatement, StorageLiveStatement, SwitchIntTerminator,
    SwitchValueTerminator, UnaryRValue, UnreachableTerminator, UseRValue,
)
from .types import MIRType


_PRELUDE = r'''/* Experimental Rove legalized MIR -> C17 output. */
#include <inttypes.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct RoveAllocation {
    char *value;
    struct RoveAllocation *next;
} RoveAllocation;

static RoveAllocation *rove_allocations = NULL;

static void rove_cleanup(void) {
    while (rove_allocations != NULL) {
        RoveAllocation *allocation = rove_allocations;
        rove_allocations = allocation->next;
        free(allocation->value);
        free(allocation);
    }
}

static char *rove_track_string(size_t length) {
    char *value = (char *)malloc(length);
    RoveAllocation *allocation = (RoveAllocation *)malloc(sizeof(RoveAllocation));
    if (value == NULL || allocation == NULL) {
        free(value);
        free(allocation);
        fputs("Rove C17 allocation failed\n", stderr);
        exit(1);
    }
    allocation->value = value;
    allocation->next = rove_allocations;
    rove_allocations = allocation;
    return value;
}

static const char *rove_concat(const char *left, const char *right) {
    size_t left_length = strlen(left);
    size_t right_length = strlen(right);
    char *result = rove_track_string(left_length + right_length + 1);
    memcpy(result, left, left_length);
    memcpy(result + left_length, right, right_length + 1);
    return result;
}

typedef struct RoveArrayI64 {
    int64_t *data;
    size_t length;
} RoveArrayI64;

static RoveArrayI64 rove_array_i64_make(const int64_t *source, size_t length) {
    RoveArrayI64 result = { NULL, length };
    if (length == 0) return result;
    result.data = (int64_t *)rove_track_string(length * sizeof(int64_t));
    memcpy(result.data, source, length * sizeof(int64_t));
    return result;
}

static RoveArrayI64 rove_array_i64_clone(RoveArrayI64 value) {
    return rove_array_i64_make(value.data, value.length);
}

static int64_t *rove_array_i64_at_mut(RoveArrayI64 *value, int64_t index) {
    if (index < 0 || (uint64_t)index >= value->length) {
        fputs("array index out of bounds\n", stderr);
        exit(1);
    }
    return &value->data[(size_t)index];
}

static void *rove_box_array_i64(RoveArrayI64 value) {
    RoveArrayI64 *result = (RoveArrayI64 *)rove_track_string(sizeof(RoveArrayI64));
    *result = rove_array_i64_clone(value);
    return result;
}

typedef struct RoveArrayBool {
    bool *data;
    size_t length;
} RoveArrayBool;

static RoveArrayBool rove_array_bool_make(const bool *source, size_t length) {
    RoveArrayBool result = { NULL, length };
    if (length == 0) return result;
    result.data = (bool *)rove_track_string(length * sizeof(bool));
    memcpy(result.data, source, length * sizeof(bool));
    return result;
}

static RoveArrayBool rove_array_bool_clone(RoveArrayBool value) {
    return rove_array_bool_make(value.data, value.length);
}

static bool *rove_array_bool_at_mut(RoveArrayBool *value, int64_t index) {
    if (index < 0 || (uint64_t)index >= value->length) {
        fputs("array index out of bounds\n", stderr);
        exit(1);
    }
    return &value->data[(size_t)index];
}

static void *rove_box_array_bool(RoveArrayBool value) {
    RoveArrayBool *result = (RoveArrayBool *)rove_track_string(sizeof(RoveArrayBool));
    *result = rove_array_bool_clone(value);
    return result;
}

typedef struct RoveArrayString {
    const char **data;
    size_t length;
} RoveArrayString;

static RoveArrayString rove_array_string_make(const char *const *source, size_t length) {
    RoveArrayString result = { NULL, length };
    if (length == 0) return result;
    result.data = (const char **)rove_track_string(length * sizeof(const char *));
    memcpy(result.data, source, length * sizeof(const char *));
    return result;
}

static RoveArrayString rove_array_string_clone(RoveArrayString value) {
    return rove_array_string_make(value.data, value.length);
}

static const char **rove_array_string_at_mut(RoveArrayString *value, int64_t index) {
    if (index < 0 || (uint64_t)index >= value->length) {
        fputs("array index out of bounds\n", stderr);
        exit(1);
    }
    return &value->data[(size_t)index];
}

static void *rove_box_array_string(RoveArrayString value) {
    RoveArrayString *result = (RoveArrayString *)rove_track_string(sizeof(RoveArrayString));
    *result = rove_array_string_clone(value);
    return result;
}

typedef union RoveTaggedPayload {
    int64_t i64;
    double f64;
    bool boolean;
    const char *string;
    void *object;
} RoveTaggedPayload;

static uint64_t rove_i64_bits(int64_t value) {
    uint64_t bits;
    memcpy(&bits, &value, sizeof(bits));
    return bits;
}

static int64_t rove_i64_from_bits(uint64_t bits) {
    int64_t value;
    memcpy(&value, &bits, sizeof(value));
    return value;
}

static int64_t rove_i64_add(int64_t left, int64_t right) {
    return rove_i64_from_bits(rove_i64_bits(left) + rove_i64_bits(right));
}

static int64_t rove_i64_sub(int64_t left, int64_t right) {
    return rove_i64_from_bits(rove_i64_bits(left) - rove_i64_bits(right));
}

static int64_t rove_i64_mul(int64_t left, int64_t right) {
    return rove_i64_from_bits(rove_i64_bits(left) * rove_i64_bits(right));
}

static int64_t rove_i64_div(int64_t left, int64_t right) {
    if (right == 0) { fputs("division by zero\n", stderr); exit(1); }
    if (left == INT64_MIN && right == -1) return INT64_MIN;
    return left / right;
}

static int64_t rove_i64_rem(int64_t left, int64_t right) {
    if (right == 0) { fputs("remainder by zero\n", stderr); exit(1); }
    if (left == INT64_MIN && right == -1) return 0;
    return left % right;
}

static int64_t rove_i64_shl(int64_t left, int64_t right) {
    return rove_i64_from_bits(rove_i64_bits(left) << (rove_i64_bits(right) & 63U));
}

static int64_t rove_i64_shr(int64_t left, int64_t right) {
    uint64_t count = rove_i64_bits(right) & 63U;
    uint64_t bits = rove_i64_bits(left);
    if (count == 0) return left;
    uint64_t shifted = bits >> count;
    if ((bits & (UINT64_C(1) << 63)) != 0) shifted |= UINT64_MAX << (64U - count);
    return rove_i64_from_bits(shifted);
}

static int64_t rove_i64_neg(int64_t value) {
    return rove_i64_from_bits(UINT64_C(0) - rove_i64_bits(value));
}

typedef struct RoveDisplaySink {
    char *data;
    size_t length;
    size_t capacity;
    bool capture;
} RoveDisplaySink;

static void rove_display_write(RoveDisplaySink *sink, const char *text) {
    if (!sink->capture) {
        fputs(text, stdout);
        return;
    }
    size_t length = strlen(text);
    if (length > SIZE_MAX - sink->length - 1) {
        fputs("Rove C17 display length overflow\n", stderr);
        exit(1);
    }
    size_t required = sink->length + length + 1;
    if (required > sink->capacity) {
        size_t capacity = sink->capacity ? sink->capacity : 64;
        while (capacity < required) {
            if (capacity > SIZE_MAX / 2) {
                capacity = required;
                break;
            }
            capacity *= 2;
        }
        char *data = (char *)realloc(sink->data, capacity);
        if (data == NULL) {
            fputs("Rove C17 display allocation failed\n", stderr);
            exit(1);
        }
        sink->data = data;
        sink->capacity = capacity;
    }
    memcpy(sink->data + sink->length, text, length + 1);
    sink->length += length;
}

static void rove_display_char(RoveDisplaySink *sink, char value) {
    char text[2] = { value, '\0' };
    rove_display_write(sink, text);
}

static const char *rove_display_finish(RoveDisplaySink *sink) {
    char *result = rove_track_string(sink->length + 1);
    if (sink->length != 0) memcpy(result, sink->data, sink->length);
    result[sink->length] = '\0';
    free(sink->data);
    sink->data = NULL;
    return result;
}

static void rove_print_i64(int64_t value, RoveDisplaySink *sink) {
    char text[64];
    int length = snprintf(text, sizeof(text), "%" PRId64, value);
    if (length < 0 || (size_t)length >= sizeof(text)) exit(1);
    rove_display_write(sink, text);
}
static void rove_print_f64(double value, RoveDisplaySink *sink) {
    if (isnan(value)) {
        rove_display_write(sink, "nan");
        return;
    }
    if (isinf(value)) {
        rove_display_write(sink, signbit(value) ? "-inf" : "inf");
        return;
    }
    if (value == 0.0) {
        rove_display_write(sink, "0");
        return;
    }

    char candidate[64] = {0};
    uint64_t original_bits;
    memcpy(&original_bits, &value, sizeof(original_bits));
    for (int precision = 1; precision <= 17; ++precision) {
        int length = snprintf(candidate, sizeof(candidate), "%.*g", precision, value);
        if (length < 0 || (size_t)length >= sizeof(candidate)) exit(1);
        char *end = NULL;
        double parsed = strtod(candidate, &end);
        uint64_t parsed_bits;
        memcpy(&parsed_bits, &parsed, sizeof(parsed_bits));
        if (*end == '\0' && parsed_bits == original_bits) break;
        if (precision == 17) {
            fputs("Rove C17 float formatting failed\n", stderr);
            exit(1);
        }
    }

    const char *body = candidate;
    bool negative = *body == '-';
    if (negative) ++body;
    const char *exponent_mark = strchr(body, 'e');
    int shift = exponent_mark ? (int)strtol(exponent_mark + 1, NULL, 10) : 0;
    char digits[32];
    int digit_count = 0;
    int decimal_point = -1;
    for (const char *cursor = body; *cursor != '\0' && cursor != exponent_mark; ++cursor) {
        if (*cursor == '.') decimal_point = digit_count;
        else digits[digit_count++] = *cursor;
    }
    if (decimal_point < 0) decimal_point = digit_count;
    while (digit_count > 1 && digits[0] == '0') {
        memmove(digits, digits + 1, (size_t)--digit_count);
        --decimal_point;
    }
    while (digit_count > 1 && digits[digit_count - 1] == '0') --digit_count;
    int decimal = decimal_point + shift;
    int exponent = decimal - 1;
    char text[128];
    size_t length = 0;
    if (negative) text[length++] = '-';
    if (exponent >= -6 && exponent < 21) {
        if (decimal <= 0) {
            text[length++] = '0';
            text[length++] = '.';
            for (int index = 0; index < -decimal; ++index) text[length++] = '0';
            memcpy(text + length, digits, (size_t)digit_count);
            length += (size_t)digit_count;
        } else if (decimal >= digit_count) {
            memcpy(text + length, digits, (size_t)digit_count);
            length += (size_t)digit_count;
            for (int index = digit_count; index < decimal; ++index) text[length++] = '0';
        } else {
            memcpy(text + length, digits, (size_t)decimal);
            length += (size_t)decimal;
            text[length++] = '.';
            memcpy(text + length, digits + decimal, (size_t)(digit_count - decimal));
            length += (size_t)(digit_count - decimal);
        }
    } else {
        text[length++] = digits[0];
        if (digit_count > 1) {
            text[length++] = '.';
            memcpy(text + length, digits + 1, (size_t)(digit_count - 1));
            length += (size_t)(digit_count - 1);
        }
        int written = snprintf(text + length, sizeof(text) - length,
                               exponent >= 0 ? "e+%d" : "e%d", exponent);
        if (written < 0 || (size_t)written >= sizeof(text) - length) exit(1);
        length += (size_t)written;
    }
    text[length] = '\0';
    rove_display_write(sink, text);
}
static void rove_print_bool(bool value, RoveDisplaySink *sink) {
    rove_display_write(sink, value ? "true" : "false");
}
static void rove_print_string(const char *value, RoveDisplaySink *sink) {
    rove_display_write(sink, value);
}'''


def _identifier(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not clean or clean[0].isdigit():
        clean = "_" + clean
    return clean


class _C17Emitter:
    def __init__(self, module: MIRModule):
        self.module = module
        self.function_names = {
            function.symbol: f"rove_fn_{_identifier(function.name)}"
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
        self.display_names: dict[MIRType, str] = {}

    def emit(self) -> str:
        ordered_structs = self._ordered_structs()
        nested_arrays = self._nested_array_types()
        early_nested_arrays = tuple(
            value for value in nested_arrays
            if self._array_leaf(value).name in ("int", "bool", "string", "float", "f64")
        )
        late_nested_arrays = tuple(
            value for value in nested_arrays if value not in early_nested_arrays
        )
        emitted_nested_arrays = set(early_nested_arrays)
        parts = [
            _PRELUDE,
            self._floating_array_declaration("float"),
            self._floating_array_declaration("f64"),
            self._tagged_value_declaration(),
        ]
        if early_nested_arrays:
            parts.extend(("", "/* Rove primitive-leaf nested-array declarations. */"))
            parts.extend(self._nested_array_declaration(value) for value in early_nested_arrays)
        parts.extend(("", "/* Rove dependency-ordered nominal value declarations. */"))
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
            parts.extend(("", "/* Rove nested-array declarations. */"))
            parts.extend(self._nested_array_declaration(value) for value in remaining_nested_arrays)
        self._collect_display_types()
        if self.display_names:
            parts.extend(("", "/* Rove canonical value display. */"))
            parts.extend(
                f"static void {name}({self._type(value)} value, RoveDisplaySink *sink);"
                for value, name in self.display_names.items()
            )
            parts.extend(
                self._display_definition(value, name)
                for value, name in self.display_names.items()
            )
        parts.extend(("", "/* Rove function declarations. */"))
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
        return f'''typedef struct RoveTaggedValue {{
    const char *tag;
    RoveTaggedPayload payload[{payload_slots}];
}} RoveTaggedValue;'''

    @staticmethod
    def _floating_array_declaration(kind: str) -> str:
        name = "RoveArrayFloat" if kind == "float" else "RoveArrayF64"
        return f'''typedef struct {name} {{
    double *data;
    size_t length;
}} {name};

static {name} rove_array_{kind}_make(const double *source, size_t length) {{
    {name} result = {{ NULL, length }};
    if (length == 0) return result;
    result.data = (double *)rove_track_string(length * sizeof(double));
    memcpy(result.data, source, length * sizeof(double));
    return result;
}}

static {name} rove_array_{kind}_clone({name} value) {{
    return rove_array_{kind}_make(value.data, value.length);
}}

static double *rove_array_{kind}_at_mut({name} *value, int64_t index) {{
    if (index < 0 || (uint64_t)index >= value->length) {{
        fputs("array index out of bounds\\n", stderr);
        exit(1);
    }}
    return &value->data[(size_t)index];
}}

static void *rove_box_array_{kind}({name} value) {{
    {name} *result = ({name} *)rove_track_string(sizeof({name}));
    *result = rove_array_{kind}_clone(value);
    return result;
}}'''

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
            f"static {rendered} rove_struct_{_identifier(definition.name)}_clone({rendered} value) {{",
            "    " + rendered + " result = value;",
        ]
        for field in definition.fields:
            name = _identifier(field.name)
            if field.type.name == "Array":
                suffix = self._array_suffix(field.type.arguments[0])
                lines.append(
                    f"    result.{name} = rove_array_{suffix}_clone(value.{name});"
                )
            elif field.type.name in self.structs:
                lines.append(
                    f"    result.{name} = rove_struct_{_identifier(field.type.name)}_clone(value.{name});"
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
        return f'''static {array} rove_array_{suffix}_make(const {element} *source, size_t length) {{
    {array} result = {{ NULL, length }};
    if (length == 0) return result;
    result.data = ({element} *)rove_track_string(length * sizeof({element}));
    for (size_t index = 0; index < length; ++index) {{
        result.data[index] = rove_struct_{_identifier(definition.name)}_clone(source[index]);
    }}
    return result;
}}

static {array} rove_array_{suffix}_clone({array} value) {{
    return rove_array_{suffix}_make(value.data, value.length);
}}

static {element} *rove_array_{suffix}_at_mut({array} *value, int64_t index) {{
    if (index < 0 || (uint64_t)index >= value->length) {{
        fputs("array index out of bounds\\n", stderr);
        exit(1);
    }}
    return &value->data[(size_t)index];
}}

static void *rove_box_{_identifier(definition.name)}({element} value) {{
    {element} *result = ({element} *)rove_track_string(sizeof({element}));
    *result = rove_struct_{_identifier(definition.name)}_clone(value);
    return result;
}}

static void *rove_box_array_{suffix}({array} value) {{
    {array} *result = ({array} *)rove_track_string(sizeof({array}));
    *result = rove_array_{suffix}_clone(value);
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

static {outer} rove_array_{outer_suffix}_make(const {inner} *source, size_t length) {{
    {outer} result = {{ NULL, length }};
    if (length == 0) return result;
    result.data = ({inner} *)rove_track_string(length * sizeof({inner}));
    for (size_t index = 0; index < length; ++index) {{
        result.data[index] = rove_array_{inner_suffix}_clone(source[index]);
    }}
    return result;
}}

static {outer} rove_array_{outer_suffix}_clone({outer} value) {{
    return rove_array_{outer_suffix}_make(value.data, value.length);
}}

static {inner} *rove_array_{outer_suffix}_at_mut({outer} *value, int64_t index) {{
    if (index < 0 || (uint64_t)index >= value->length) {{
        fputs("array index out of bounds\\n", stderr);
        exit(1);
    }}
    return &value->data[(size_t)index];
}}

static void *rove_box_array_{outer_suffix}({outer} value) {{
    {outer} *result = ({outer} *)rove_track_string(sizeof({outer}));
    *result = rove_array_{outer_suffix}_clone(value);
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

    def _collect_display_types(self) -> None:
        for function in self.module.functions:
            self.current = function
            self.local_types = {local.id: local.type for local in function.locals}
            for block in function.blocks:
                terminator = block.terminator
                if isinstance(terminator, CallTerminator) and terminator.function in {
                    "builtin::print", "builtin::to_string"
                }:
                    for argument in terminator.arguments:
                        self._register_display(self._operand_type(argument))
        self.current = None
        self.local_types = {}

    def _register_display(self, value: MIRType) -> None:
        if value.name in {"int", "bool", "string", "float", "f64"} and not value.arguments:
            return
        if value in self.display_names:
            return
        self.display_names[value] = f"rove_print_value_{len(self.display_names)}"
        if value.name == "Array":
            self._register_display(value.arguments[0])
        elif value.name in self.structs:
            for field in self.structs[value.name].fields:
                self._register_display(field.type)
        else:
            for _, payloads in self._display_variants(value):
                for payload in payloads:
                    if payload.name != "any":
                        self._register_display(payload)

    def _display_variants(self, value: MIRType) -> tuple[tuple[str, tuple[MIRType, ...]], ...]:
        if value.name == "Option":
            payload = value.arguments[0]
            return (("Some", () if payload.name == "any" else (payload,)), ("None", ()))
        if value.name == "Result":
            good, error = value.arguments
            return (
                ("Ok", () if good.name == "any" else (good,)),
                ("Err", () if error.name == "any" else (error,)),
            )
        definition = self.enums[value.name]
        return tuple((variant.name, variant.payload_types) for variant in definition.variants)

    def _display_call(self, value: MIRType, expression: str, sink: str = "sink") -> str:
        return f"{self._print_function(value)}({expression}, {sink});"

    def _display_definition(self, value: MIRType, name: str) -> str:
        lines = [f"static void {name}({self._type(value)} value, RoveDisplaySink *sink) {{"]
        if value.name == "Array":
            lines.extend((
                "    rove_display_char(sink, '[');",
                "    for (size_t index = 0; index < value.length; ++index) {",
                "        if (index) rove_display_write(sink, \", \");",
                "        " + self._display_call(value.arguments[0], "value.data[index]"),
                "    }",
                "    rove_display_char(sink, ']');",
            ))
        elif value.name in self.structs:
            definition = self.structs[value.name]
            lines.append(f"    rove_display_write(sink, {json.dumps(value.name + '(')});")
            for index, field in enumerate(definition.fields):
                if index:
                    lines.append('    rove_display_write(sink, ", ");')
                lines.append("    " + self._display_call(field.type, f"value.{_identifier(field.name)}"))
            lines.append("    rove_display_char(sink, ')');")
        else:
            variants = self._display_variants(value)
            for index, (tag, payloads) in enumerate(variants):
                prefix = "if" if index == 0 else "else if"
                lines.append(f"    {prefix} (strcmp(value.tag, {json.dumps(tag)}) == 0) {{")
                lines.append(f"        rove_display_write(sink, {json.dumps(tag + '(')});")
                for slot, payload in enumerate(payloads):
                    if slot:
                        lines.append('        rove_display_write(sink, ", ");')
                    field = self._tag_payload_field(payload)
                    expression = f"value.payload[{slot}].{field}"
                    if field == "object":
                        expression = f"(*({self._type(payload)} *){expression})"
                    lines.append("        " + self._display_call(payload, expression))
                lines.extend(("        rove_display_char(sink, ')');", "    }"))
            if variants:
                lines.append("    else {")
            lines.extend((
                '        fputs("invalid Rove C17 tagged display value\\n", stderr);',
                "        exit(1);",
            ))
            if variants:
                lines.append("    }")
        lines.append("}")
        return "\n".join(lines)

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
        lines = ["int main(void) {", "    if (atexit(rove_cleanup) != 0) return 1;"]
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
        if isinstance(value, DeinitStatement):
            place = self._place(value.place)
            return [f"memset(&({place}), 0, sizeof({place}));"]
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
                lines = ["{", "    RoveDisplaySink sink = {0};"]
                for index, argument in enumerate(value.arguments):
                    if index:
                        lines.append("    rove_display_char(&sink, ' ');")
                    lines.append("    " + self._display_call(
                        self._operand_type(argument), self._operand(argument), "&sink"
                    ))
                lines.extend(("    fputc('\\n', stdout);", "}"))
                return lines + self._goto(value.target)
            if value.function == "builtin::to_string":
                if len(value.arguments) != 1 or value.destination is None:
                    raise MIRCodegenError(
                        "builtin::to_string requires one argument and a destination"
                    )
                argument = value.arguments[0]
                call = self._display_call(
                    self._operand_type(argument), self._operand(argument), "&sink"
                )
                return [
                    "{",
                    "    RoveDisplaySink sink = {0};",
                    "    sink.capture = true;",
                    f"    {call}",
                    f"    {self._place(value.destination)} = rove_display_finish(&sink);",
                    "}",
                ] + self._goto(value.target)
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
        if isinstance(value, DropTerminator):
            if value.unwind is not None:
                raise MIRCodegenError("C17 MIR drop unwind edge was not legalized")
            place = self._place(value.place)
            return [f"memset(&({place}), 0, sizeof({place}));"] + self._goto(value.target)
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
            if (
                value.kind == "implicit"
                and source_type.name == "int"
                and value.type.name in ("float", "f64")
                and not source_type.optional
                and not value.type.optional
            ):
                return f"((double)({operand}))"
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
                return f"rove_array_{self._array_suffix(element)}_make({source}, {len(value.operands)})"
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
                    f"(RoveTaggedValue){{ .tag = {json.dumps(value.name)}, "
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
                return f"rove_i64_neg({operand})"
            if value.op == "-":
                return f"-({operand})"
            if value.op == "~":
                return f"rove_i64_from_bits(~rove_i64_bits({operand}))"
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
            return f"rove_concat({left}, {right})"
        if left_type.name in ("float", "f64") or right_type.name in ("float", "f64"):
            if value.op in ("+", "-", "*", "/"):
                return f"({left} {value.op} {right})"
            if value.op == "%":
                return f"fmod({left}, {right})"
        operations = {
            "+": "rove_i64_add", "-": "rove_i64_sub", "*": "rove_i64_mul",
            "/": "rove_i64_div", "%": "rove_i64_rem", "<<": "rove_i64_shl",
            ">>": "rove_i64_shr",
        }
        if value.op in operations:
            return f"{operations[value.op]}({left}, {right})"
        if value.op in ("&", "|", "^"):
            return f"rove_i64_from_bits(rove_i64_bits({left}) {value.op} rove_i64_bits({right}))"
        raise MIRCodegenError(f"unsupported C17 binary operation '{value.op}'")

    def _operand(self, value: Operand) -> str:
        if isinstance(value, ConstOperand):
            return self._typed_constant(value)
        if isinstance(value, (CopyOperand, MoveOperand)):
            rendered = self._place(value.place)
            place_type = self._place_type(value.place)
            if isinstance(value, CopyOperand) and place_type.name == "Array":
                return f"rove_array_{self._array_suffix(place_type.arguments[0])}_clone({rendered})"
            if isinstance(value, CopyOperand) and place_type.name in self.structs:
                return f"rove_struct_{_identifier(place_type.name)}_clone({rendered})"
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
            return f"rove_i64_from_bits(UINT64_C({bits}))"
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
            return "RoveTaggedValue"
        rendered = self._struct_name(value.name) if value.name in self.structs else mapping.get(value.name)
        if rendered is None or value.optional or value.pointer or value.arguments:
            raise MIRCodegenError(f"unsupported C17 MIR type '{value}'")
        return rendered

    def _default(self, value: MIRType) -> str:
        if self._is_supported_array(value):
            return f"({self._array_type(value)}){{ NULL, 0 }}"
        if self._is_tagged_type(value):
            return "(RoveTaggedValue){ \"\", { { .i64 = INT64_C(0) } } }"
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
                rendered = f"(*rove_array_{self._array_suffix(element)}_at_mut(&({rendered}), {index}))"
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
        return f"RoveStruct_{_identifier(value)}"

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
                element.name in ("int", "bool", "string", "float", "f64")
                or element.name in self.structs
            )
        )

    def _array_type(self, value: MIRType) -> str:
        if not self._is_supported_array(value):
            raise MIRCodegenError(f"unsupported C17 array type '{value}'")
        element = value.arguments[0]
        if element.name == "Array":
            return f"RoveArrayNested_{_identifier(self._array_suffix(element))}"
        return {
            "int": "RoveArrayI64",
            "bool": "RoveArrayBool",
            "string": "RoveArrayString",
            "float": "RoveArrayFloat",
            "f64": "RoveArrayF64",
        }.get(element.name, f"RoveArrayStruct_{_identifier(element.name)}")

    def _array_suffix(self, element: MIRType) -> str:
        if element.name == "Array" and len(element.arguments) == 1:
            return f"nested_{self._array_suffix(element.arguments[0])}"
        return {
            "int": "i64",
            "bool": "bool",
            "string": "string",
            "float": "float",
            "f64": "f64",
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
        mapping = {
            "int": "i64", "bool": "boolean", "string": "string",
            "float": "f64", "f64": "f64",
        }
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
            return f"rove_box_{_identifier(value.name)}"
        if self._is_supported_array(value):
            return f"rove_box_array_{self._array_suffix(value.arguments[0])}"
        raise MIRCodegenError(f"unsupported C17 boxed payload type '{value}'")

    def _print_function(self, value: MIRType) -> str:
        mapping = {
            "bool": "rove_print_bool", "int": "rove_print_i64",
            "float": "rove_print_f64", "f64": "rove_print_f64",
            "string": "rove_print_string",
        }
        result = self.display_names.get(value) or mapping.get(value.name)
        if result is None:
            raise MIRCodegenError(f"C17 print does not support MIR type '{value}'")
        return result


def emit_legalized_c17(module: MIRModule) -> str:
    return _C17Emitter(legalize_mir(module, "c", require_emitter=True)).emit()
