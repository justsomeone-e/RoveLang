"""Direct LLVM IR emitter for the legalized scalar/control-flow MIR pilot."""

from __future__ import annotations

import math
import re

from .codegen_cpp import MIRCodegenError
from .legalization import legalize_mir
from .model import (
    AggregateRValue,
    AssertTerminator,
    AssignStatement,
    BinaryRValue,
    CallTerminator,
    CastRValue,
    ConstOperand,
    ConstantIndexProjection,
    CopyOperand,
    DeinitStatement,
    DiscriminantRValue,
    DropTerminator,
    FieldProjection,
    GotoTerminator,
    IndexProjection,
    MIRFunction,
    MIRModule,
    MIREnumDef,
    MIRStructDef,
    MoveOperand,
    NopStatement,
    Operand,
    PayloadRValue,
    Place,
    ReturnTerminator,
    StorageDeadStatement,
    StorageLiveStatement,
    SwitchIntTerminator,
    SwitchValueTerminator,
    UnaryRValue,
    UnreachableTerminator,
    UseRValue,
)
from .types import MIRType


_INTEGER_TYPES = frozenset({"int"})
_FLOAT_TYPES = frozenset({"float", "f64"})


def _identifier(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not clean or clean[0].isdigit():
        clean = "_" + clean
    return clean


def _escape_bytes(value: str) -> tuple[str, int]:
    data = value.encode("utf-8") + b"\0"
    rendered = "".join(chr(byte) if 32 <= byte <= 126 and byte not in (34, 92) else f"\\{byte:02X}" for byte in data)
    return rendered, len(data)


class _LLVMEmitter:
    def __init__(self, module: MIRModule):
        self.module = module
        self.function_names = {
            function.symbol: ("main" if function.name == "main" else f"rove_fn_{_identifier(function.name)}")
            for function in module.functions
        }
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
        self.array_types = self._collect_array_types()
        self.string_names: dict[str, tuple[str, int]] = {}
        self.temp = 0
        self.synthetic_block = 0
        self.lines: list[str] = []
        self.extra_blocks: list[list[str]] = []
        self.current: MIRFunction | None = None
        self.local_types: dict[int, MIRType] = {}

    def emit(self) -> str:
        self._collect_strings()
        parts = [
            "; Experimental Rove legalized MIR -> LLVM IR output.",
            "; The production Typed HIR LLVM emitter remains the parity oracle.",
            "declare i32 @printf(ptr, ...)",
            "declare i32 @snprintf(ptr, i64, ptr, ...)",
            "declare double @strtod(ptr, ptr)",
            "declare ptr @strchr(ptr, i32)",
            "declare i32 @atoi(ptr)",
            "declare i32 @putchar(i32)",
            "declare void @exit(i32)",
            "declare void @free(ptr)",
            "declare ptr @malloc(i64)",
            "declare i32 @strcmp(ptr, ptr)",
            "declare i64 @strlen(ptr)",
            "declare void @llvm.memcpy.p0.p0.i64(ptr, ptr, i64, i1 immarg)",
            "",
            '@.fmt_i64 = private unnamed_addr constant [5 x i8] c"%lld\\00"',
            '@.fmt_f64_candidate = private unnamed_addr constant [5 x i8] c"%.*g\\00"',
            '@.fmt_f64_exponent = private unnamed_addr constant [4 x i8] c"%+d\\00"',
            '@.f64_nan = private unnamed_addr constant [4 x i8] c"nan\\00"',
            '@.f64_inf = private unnamed_addr constant [4 x i8] c"inf\\00"',
            '@.f64_negative_inf = private unnamed_addr constant [5 x i8] c"-inf\\00"',
            '@.f64_zeros = private unnamed_addr constant [22 x i8] c"0000000000000000000000"',
            '@.fmt_str = private unnamed_addr constant [3 x i8] c"%s\\00"',
            '@.space = private unnamed_addr constant [2 x i8] c" \\00"',
            '@.newline = private unnamed_addr constant [2 x i8] c"\\0A\\00"',
            '@.open = private unnamed_addr constant [2 x i8] c"(\\00"',
            '@.close = private unnamed_addr constant [2 x i8] c")\\00"',
            '@.array_open = private unnamed_addr constant [2 x i8] c"[\\00"',
            '@.array_close = private unnamed_addr constant [2 x i8] c"]\\00"',
            '@.comma = private unnamed_addr constant [3 x i8] c", \\00"',
            '@.true = private unnamed_addr constant [5 x i8] c"true\\00"',
            '@.false = private unnamed_addr constant [6 x i8] c"false\\00"',
            "%rove_tagged = type { ptr, [4 x i64] }",
            "",
            self._division_helpers(),
            self._float_display_helpers(),
            self._array_helpers(),
        ]
        parts.extend(self._owned_array_type_declarations())
        parts.extend(self._struct_type_declarations())
        if self.array_types or self.structs:
            parts.append("")
            parts.extend(self._owned_array_helpers())
            parts.append("")
            parts.extend(self._struct_clone_helpers())
            parts.append("")
        tagged_helpers = self._tagged_lifecycle_helpers()
        if tagged_helpers:
            parts.extend(tagged_helpers)
            parts.append("")
        for value, (name, length) in self.string_names.items():
            escaped, _ = _escape_bytes(value)
            parts.append(f'@{name} = private unnamed_addr constant [{length} x i8] c"{escaped}"')
        if self.string_names:
            parts.append("")
        for function in self.module.functions:
            parts.append(self._function(function))
        return "\n".join(parts).rstrip() + "\n"

    @staticmethod
    def _float_display_helpers() -> str:
        return r"""define void @rove_emit_chars(ptr %source, i32 %length) {
entry:
  %index = alloca i32
  store i32 0, ptr %index
  br label %check
check:
  %current = load i32, ptr %index
  %more = icmp slt i32 %current, %length
  br i1 %more, label %body, label %done
body:
  %address = getelementptr i8, ptr %source, i32 %current
  %character = load i8, ptr %address
  %wide = zext i8 %character to i32
  call i32 @putchar(i32 %wide)
  %next = add i32 %current, 1
  store i32 %next, ptr %index
  br label %check
done:
  ret void
}

define void @rove_print_f64(double %value) {
entry:
  %bits = bitcast double %value to i64
  %absolute = and i64 %bits, 9223372036854775807
  %nan = icmp ugt i64 %absolute, 9218868437227405312
  br i1 %nan, label %print_nan, label %check_inf
print_nan:
  call i32 (ptr, ...) @printf(ptr @.fmt_str, ptr @.f64_nan)
  ret void
check_inf:
  %inf = icmp eq i64 %absolute, 9218868437227405312
  br i1 %inf, label %print_inf, label %check_zero
print_inf:
  %inf_negative = icmp slt i64 %bits, 0
  %inf_text = select i1 %inf_negative, ptr @.f64_negative_inf, ptr @.f64_inf
  call i32 (ptr, ...) @printf(ptr @.fmt_str, ptr %inf_text)
  ret void
check_zero:
  %zero = icmp eq i64 %absolute, 0
  br i1 %zero, label %print_zero, label %prepare
print_zero:
  call i32 @putchar(i32 48)
  ret void
prepare:
  %candidate = alloca [64 x i8]
  %digits = alloca [32 x i8]
  %precision_slot = alloca i32
  %scan_slot = alloca i32
  %count_slot = alloca i32
  %dot_slot = alloca i32
  %first_slot = alloca i32
  %last_slot = alloca i32
  store i32 1, ptr %precision_slot
  br label %candidate_loop
candidate_loop:
  %precision = load i32, ptr %precision_slot
  call i32 (ptr, i64, ptr, ...) @snprintf(
      ptr %candidate, i64 64, ptr @.fmt_f64_candidate, i32 %precision, double %value)
  %parsed = call double @strtod(ptr %candidate, ptr null)
  %parsed_bits = bitcast double %parsed to i64
  %round_trips = icmp eq i64 %parsed_bits, %bits
  %maximum = icmp eq i32 %precision, 17
  %stop = or i1 %round_trips, %maximum
  br i1 %stop, label %parse_start, label %next_precision
next_precision:
  %increased = add i32 %precision, 1
  store i32 %increased, ptr %precision_slot
  br label %candidate_loop
parse_start:
  %first_character = load i8, ptr %candidate
  %negative = icmp eq i8 %first_character, 45
  %unsigned_body = getelementptr i8, ptr %candidate, i32 1
  %body = select i1 %negative, ptr %unsigned_body, ptr %candidate
  %marker = call ptr @strchr(ptr %body, i32 101)
  %has_exponent = icmp ne ptr %marker, null
  br i1 %has_exponent, label %parse_exponent, label %scan_init
parse_exponent:
  %exponent_text = getelementptr i8, ptr %marker, i32 1
  %parsed_exponent = call i32 @atoi(ptr %exponent_text)
  br label %scan_init
scan_init:
  %shift = phi i32 [ 0, %parse_start ], [ %parsed_exponent, %parse_exponent ]
  store i32 0, ptr %scan_slot
  store i32 0, ptr %count_slot
  store i32 -1, ptr %dot_slot
  br label %scan_check
scan_check:
  %scan_index = load i32, ptr %scan_slot
  %source_address = getelementptr i8, ptr %body, i32 %scan_index
  %source_character = load i8, ptr %source_address
  %terminator = icmp eq i8 %source_character, 0
  %exponent_marker = icmp eq i8 %source_character, 101
  %end = or i1 %terminator, %exponent_marker
  br i1 %end, label %leading_init, label %scan_character
scan_character:
  %dot = icmp eq i8 %source_character, 46
  br i1 %dot, label %scan_dot, label %scan_digit
scan_dot:
  %dot_position = load i32, ptr %count_slot
  store i32 %dot_position, ptr %dot_slot
  br label %scan_advance
scan_digit:
  %digit_index = load i32, ptr %count_slot
  %digit_address = getelementptr i8, ptr %digits, i32 %digit_index
  store i8 %source_character, ptr %digit_address
  %next_count = add i32 %digit_index, 1
  store i32 %next_count, ptr %count_slot
  br label %scan_advance
scan_advance:
  %next_scan = add i32 %scan_index, 1
  store i32 %next_scan, ptr %scan_slot
  br label %scan_check
leading_init:
  store i32 0, ptr %first_slot
  br label %leading_check
leading_check:
  %first = load i32, ptr %first_slot
  %count = load i32, ptr %count_slot
  %leading_limit = sub i32 %count, 1
  %can_trim_leading = icmp slt i32 %first, %leading_limit
  br i1 %can_trim_leading, label %leading_read, label %trailing_init
leading_read:
  %leading_address = getelementptr i8, ptr %digits, i32 %first
  %leading_character = load i8, ptr %leading_address
  %leading_zero = icmp eq i8 %leading_character, 48
  br i1 %leading_zero, label %leading_advance, label %trailing_init
leading_advance:
  %next_first = add i32 %first, 1
  store i32 %next_first, ptr %first_slot
  br label %leading_check
trailing_init:
  %total = load i32, ptr %count_slot
  store i32 %total, ptr %last_slot
  br label %trailing_check
trailing_check:
  %last = load i32, ptr %last_slot
  %trimmed_first = load i32, ptr %first_slot
  %trailing_limit = add i32 %trimmed_first, 1
  %can_trim_trailing = icmp sgt i32 %last, %trailing_limit
  br i1 %can_trim_trailing, label %trailing_read, label %ready
trailing_read:
  %previous = sub i32 %last, 1
  %trailing_address = getelementptr i8, ptr %digits, i32 %previous
  %trailing_character = load i8, ptr %trailing_address
  %trailing_zero = icmp eq i8 %trailing_character, 48
  br i1 %trailing_zero, label %trailing_advance, label %ready
trailing_advance:
  store i32 %previous, ptr %last_slot
  br label %trailing_check
ready:
  %raw_dot = load i32, ptr %dot_slot
  %no_dot = icmp slt i32 %raw_dot, 0
  %raw_count = load i32, ptr %count_slot
  %point = select i1 %no_dot, i32 %raw_count, i32 %raw_dot
  %adjusted = add i32 %point, %shift
  %first_digit = load i32, ptr %first_slot
  %decimal = sub i32 %adjusted, %first_digit
  %last_digit = load i32, ptr %last_slot
  %length = sub i32 %last_digit, %first_digit
  %trimmed_digits = getelementptr i8, ptr %digits, i32 %first_digit
  br i1 %negative, label %print_negative, label %select_notation
print_negative:
  call i32 @putchar(i32 45)
  br label %select_notation
select_notation:
  %above_lower = icmp sgt i32 %decimal, -6
  %below_upper = icmp sle i32 %decimal, 21
  %fixed = and i1 %above_lower, %below_upper
  br i1 %fixed, label %fixed_select, label %scientific
fixed_select:
  %leading_fraction = icmp sle i32 %decimal, 0
  br i1 %leading_fraction, label %fixed_fraction, label %fixed_whole_select
fixed_fraction:
  call i32 @putchar(i32 48)
  call i32 @putchar(i32 46)
  %fraction_zeros = sub i32 0, %decimal
  call void @rove_emit_chars(ptr @.f64_zeros, i32 %fraction_zeros)
  call void @rove_emit_chars(ptr %trimmed_digits, i32 %length)
  br label %done
fixed_whole_select:
  %whole = icmp sge i32 %decimal, %length
  br i1 %whole, label %fixed_whole, label %fixed_split
fixed_whole:
  call void @rove_emit_chars(ptr %trimmed_digits, i32 %length)
  %whole_zeros = sub i32 %decimal, %length
  call void @rove_emit_chars(ptr @.f64_zeros, i32 %whole_zeros)
  br label %done
fixed_split:
  call void @rove_emit_chars(ptr %trimmed_digits, i32 %decimal)
  call i32 @putchar(i32 46)
  %fraction_start = getelementptr i8, ptr %trimmed_digits, i32 %decimal
  %fraction_length = sub i32 %length, %decimal
  call void @rove_emit_chars(ptr %fraction_start, i32 %fraction_length)
  br label %done
scientific:
  call void @rove_emit_chars(ptr %trimmed_digits, i32 1)
  %has_fraction = icmp sgt i32 %length, 1
  br i1 %has_fraction, label %scientific_fraction, label %scientific_exponent
scientific_fraction:
  call i32 @putchar(i32 46)
  %scientific_fraction_start = getelementptr i8, ptr %trimmed_digits, i32 1
  %scientific_fraction_length = sub i32 %length, 1
  call void @rove_emit_chars(ptr %scientific_fraction_start, i32 %scientific_fraction_length)
  br label %scientific_exponent
scientific_exponent:
  call i32 @putchar(i32 101)
  %exponent = sub i32 %decimal, 1
  call i32 (ptr, ...) @printf(ptr @.fmt_f64_exponent, i32 %exponent)
  br label %done
done:
  ret void
}"""

    def _struct_type_declarations(self) -> list[str]:
        declarations: list[str] = []
        for definition in self.structs.values():
            fields = ", ".join(self._type(field.type) for field in definition.fields)
            declarations.append(f"%rove_type_{_identifier(definition.name)} = type {{ {fields} }}")
        return declarations

    def _collect_array_types(self) -> tuple[MIRType, ...]:
        found: dict[str, MIRType] = {}

        def visit(value_type: MIRType) -> None:
            if value_type.name == "Array" and len(value_type.arguments) == 1:
                visit(value_type.arguments[0])
                found[value_type.canonical()] = value_type
                return
            for argument in value_type.arguments:
                visit(argument)

        for definition in self.module.type_definitions:
            if isinstance(definition, MIRStructDef):
                for field in definition.fields:
                    visit(field.type)
            elif isinstance(definition, MIREnumDef):
                for variant in definition.variants:
                    for payload_type in variant.payload_types:
                        visit(payload_type)
        for function in self.module.functions:
            for local in function.locals:
                visit(local.type)
        return tuple(found[key] for key in sorted(found))

    def _owned_array_type_declarations(self) -> list[str]:
        declarations: list[str] = []
        for value_type in self.array_types:
            array = self._array_spec(value_type)
            if array is None or array[2] is not None:
                continue
            descriptor_type, _element_type, _stride, _suffix = array
            declarations.append(f"{descriptor_type} = type {{ ptr, i64 }}")
        return declarations

    def _owned_array_helpers(self) -> list[str]:
        helpers: list[str] = []
        for value_type in self.array_types:
            array = self._array_spec(value_type)
            if array is None or array[2] is not None:
                continue
            descriptor_type, element_type, _stride, suffix = array
            element_mir_type = value_type.arguments[0]
            nested_array = self._array_spec(element_mir_type)
            struct_element = self.structs.get(element_mir_type.name)
            helpers.append(f"""define {descriptor_type} @rove_array_{suffix}_clone({descriptor_type} %value) {{
entry:
  %data = extractvalue {descriptor_type} %value, 0
  %length = extractvalue {descriptor_type} %value, 1
  %size_ptr = getelementptr {element_type}, ptr null, i32 1
  %element_size = ptrtoint ptr %size_ptr to i64
  %bytes = mul i64 %length, %element_size
  %copy = call ptr @malloc(i64 %bytes)
  %index_slot = alloca i64
  store i64 0, ptr %index_slot
  br label %check
check:
  %index = load i64, ptr %index_slot
  %more = icmp slt i64 %index, %length
  br i1 %more, label %body, label %done
body:
  %source_ptr = getelementptr inbounds {element_type}, ptr %data, i64 %index
  %source = load {element_type}, ptr %source_ptr
{self._owned_array_clone_instruction(element_type, element_mir_type, nested_array, struct_element)}
  %destination_ptr = getelementptr inbounds {element_type}, ptr %copy, i64 %index
  store {element_type} %element, ptr %destination_ptr
  %next = add i64 %index, 1
  store i64 %next, ptr %index_slot
  br label %check
done:
  %with_data = insertvalue {descriptor_type} poison, ptr %copy, 0
  %result = insertvalue {descriptor_type} %with_data, i64 %length, 1
  ret {descriptor_type} %result
}}

define ptr @rove_array_{suffix}_at(ptr %descriptor, i64 %index) {{
entry:
  %length_ptr = getelementptr inbounds {descriptor_type}, ptr %descriptor, i32 0, i32 1
  %length = load i64, ptr %length_ptr
  %negative = icmp slt i64 %index, 0
  %past_end = icmp sge i64 %index, %length
  %invalid = or i1 %negative, %past_end
  br i1 %invalid, label %fail, label %valid
fail:
  call void @exit(i32 1)
  unreachable
valid:
  %data_ptr = getelementptr inbounds {descriptor_type}, ptr %descriptor, i32 0, i32 0
  %data = load ptr, ptr %data_ptr
  %element = getelementptr inbounds {element_type}, ptr %data, i64 %index
  ret ptr %element
}}

define void @rove_array_{suffix}_destroy(ptr %descriptor) {{
entry:
  %data_ptr = getelementptr inbounds {descriptor_type}, ptr %descriptor, i32 0, i32 0
  %data = load ptr, ptr %data_ptr
  %length_ptr = getelementptr inbounds {descriptor_type}, ptr %descriptor, i32 0, i32 1
  %length = load i64, ptr %length_ptr
  %index_slot = alloca i64
  store i64 0, ptr %index_slot
  br label %check
check:
  %index = load i64, ptr %index_slot
  %more = icmp slt i64 %index, %length
  br i1 %more, label %body, label %done
body:
  %element = getelementptr inbounds {element_type}, ptr %data, i64 %index
{self._owned_array_destroy_instruction(element_mir_type, nested_array, struct_element)}
  %next = add i64 %index, 1
  store i64 %next, ptr %index_slot
  br label %check
done:
  call void @free(ptr %data)
  store {descriptor_type} zeroinitializer, ptr %descriptor
  ret void
}}""")
        return helpers

    @staticmethod
    def _owned_array_clone_instruction(
        element_type: str,
        element_mir_type: MIRType,
        nested_array: tuple[str, str, int | None, str] | None,
        struct_element: MIRStructDef | None,
    ) -> str:
        if nested_array is not None:
            descriptor_type, _nested_element, _stride, nested_suffix = nested_array
            return (
                f"  %element = call {descriptor_type} "
                f"@rove_array_{nested_suffix}_clone({descriptor_type} %source)"
            )
        if struct_element is not None:
            return (
                f"  %element = call {element_type} "
                f"@rove_struct_{_identifier(element_mir_type.name)}_clone({element_type} %source)"
            )
        raise MIRCodegenError(
            f"LLVM owned array helper cannot clone element type '{element_mir_type}'"
        )

    @staticmethod
    def _owned_array_destroy_instruction(
        element_mir_type: MIRType,
        nested_array: tuple[str, str, int | None, str] | None,
        struct_element: MIRStructDef | None,
    ) -> str:
        if nested_array is not None:
            _descriptor_type, _nested_element, _stride, nested_suffix = nested_array
            return f"  call void @rove_array_{nested_suffix}_destroy(ptr %element)"
        if struct_element is not None:
            return (
                f"  call void @rove_struct_{_identifier(element_mir_type.name)}_destroy(ptr %element)"
            )
        raise MIRCodegenError(
            f"LLVM owned array helper cannot destroy element type '{element_mir_type}'"
        )

    def _struct_clone_helpers(self) -> list[str]:
        helpers: list[str] = []
        for definition in self.structs.values():
            struct_type = self._type(MIRType(definition.name))
            lines = [
                f"define {struct_type} @rove_struct_{_identifier(definition.name)}_clone({struct_type} %value) {{",
                "entry:",
            ]
            aggregate = "poison"
            for index, field in enumerate(definition.fields):
                field_type = self._type(field.type)
                extracted = f"%field{index}"
                lines.append(
                    f"  {extracted} = extractvalue {struct_type} %value, {index}"
                )
                copied = extracted
                array = self._array_spec(field.type)
                if array is not None:
                    descriptor_type, _element_type, _stride, suffix = array
                    copied = f"%copy{index}"
                    lines.append(
                        f"  {copied} = call {descriptor_type} @rove_array_{suffix}_clone({descriptor_type} {extracted})"
                    )
                elif field.type.name in self.structs:
                    copied = f"%copy{index}"
                    lines.append(
                        f"  {copied} = call {field_type} @rove_struct_{_identifier(field.type.name)}_clone({field_type} {extracted})"
                    )
                inserted = f"%result{index}"
                lines.append(
                    f"  {inserted} = insertvalue {struct_type} {aggregate}, {field_type} {copied}, {index}"
                )
                aggregate = inserted
            lines.extend((f"  ret {struct_type} {aggregate}", "}"))
            helpers.append("\n".join(lines))
            destroy = [
                f"define void @rove_struct_{_identifier(definition.name)}_destroy(ptr %value) {{",
                "entry:",
            ]
            for index, field in enumerate(definition.fields):
                array = self._array_spec(field.type)
                if array is None and field.type.name not in self.structs:
                    continue
                field_ptr = f"%field{index}"
                destroy.append(
                    f"  {field_ptr} = getelementptr inbounds {struct_type}, ptr %value, i32 0, i32 {index}"
                )
                if array is not None:
                    _descriptor_type, _element_type, _stride, suffix = array
                    destroy.append(
                        f"  call void @rove_array_{suffix}_destroy(ptr {field_ptr})"
                    )
                else:
                    destroy.append(
                        f"  call void @rove_struct_{_identifier(field.type.name)}_destroy(ptr {field_ptr})"
                    )
            destroy.extend((f"  store {struct_type} zeroinitializer, ptr %value", "  ret void", "}"))
            helpers.append("\n".join(destroy))
        return helpers

    def _tagged_lifecycle_helpers(self) -> list[str]:
        helpers: list[str] = []
        tagged_types = {
            local.type
            for function in self.module.functions
            for local in function.locals
            if self._tag_has_boxed_payload(local.type)
        }
        for value_type in sorted(tagged_types, key=lambda item: item.canonical()):
            helpers.extend((
                self._tagged_clone_helper(value_type),
                self._tagged_destroy_helper(value_type),
            ))
        return helpers

    def _tagged_clone_helper(self, value_type: MIRType) -> str:
        helper = self._tagged_helper_name(value_type)
        variants = self._tag_lifecycle_variants(value_type)
        lines = [
            f"define %rove_tagged @{helper}_clone(%rove_tagged %value) {{",
            "entry:",
            "  %tag = extractvalue %rove_tagged %value, 0",
            "  %is_null = icmp eq ptr %tag, null",
            "  br i1 %is_null, label %fallback, label %check0",
        ]
        boxed_variants = [
            (
                name,
                tuple(
                    (index, payload)
                    for index, payload in enumerate(payloads)
                    if self._is_boxed_tag_payload(payload)
                ),
            )
            for name, payloads in variants
            if any(self._is_boxed_tag_payload(payload) for payload in payloads)
        ]
        for ordinal, (name, boxed_payloads) in enumerate(boxed_variants):
            next_label = f"check{ordinal + 1}" if ordinal + 1 < len(boxed_variants) else "fallback"
            tag_name = self.string_names[name][0]
            lines.extend((
                f"check{ordinal}:",
                f"  %cmp{ordinal} = call i32 @strcmp(ptr %tag, ptr @{tag_name})",
                f"  %matched{ordinal} = icmp eq i32 %cmp{ordinal}, 0",
                f"  br i1 %matched{ordinal}, label %clone{ordinal}, label %{next_label}",
                f"clone{ordinal}:",
            ))
            aggregate = "%value"
            for index, payload_type in boxed_payloads:
                suffix_id = f"{ordinal}_{index}"
                llvm_type = self._type(payload_type)
                lines.extend((
                    f"  %encoded{suffix_id} = extractvalue %rove_tagged %value, 1, {index}",
                    f"  %box{suffix_id} = inttoptr i64 %encoded{suffix_id} to ptr",
                    f"  %payload{suffix_id} = load {llvm_type}, ptr %box{suffix_id}",
                ))
                cloned = f"%payload{suffix_id}"
                array = self._array_spec(payload_type)
                if array is not None:
                    descriptor_type, _element_type, _stride, suffix = array
                    cloned = f"%clone_payload{suffix_id}"
                    lines.append(
                        f"  {cloned} = call {descriptor_type} @rove_array_{suffix}_clone({descriptor_type} %payload{suffix_id})"
                    )
                else:
                    cloned = f"%clone_payload{suffix_id}"
                    lines.append(
                        f"  {cloned} = call {llvm_type} @rove_struct_{_identifier(payload_type.name)}_clone({llvm_type} %payload{suffix_id})"
                    )
                lines.extend((
                    f"  %size_ptr{suffix_id} = getelementptr {llvm_type}, ptr null, i32 1",
                    f"  %size{suffix_id} = ptrtoint ptr %size_ptr{suffix_id} to i64",
                    f"  %copy_box{suffix_id} = call ptr @malloc(i64 %size{suffix_id})",
                    f"  store {llvm_type} {cloned}, ptr %copy_box{suffix_id}",
                    f"  %copy_encoded{suffix_id} = ptrtoint ptr %copy_box{suffix_id} to i64",
                    f"  %result{suffix_id} = insertvalue %rove_tagged {aggregate}, i64 %copy_encoded{suffix_id}, 1, {index}",
                ))
                aggregate = f"%result{suffix_id}"
            lines.append(f"  ret %rove_tagged {aggregate}")
        lines.extend(("fallback:", "  ret %rove_tagged %value", "}"))
        return "\n".join(lines)

    def _tagged_destroy_helper(self, value_type: MIRType) -> str:
        helper = self._tagged_helper_name(value_type)
        variants = self._tag_lifecycle_variants(value_type)
        lines = [
            f"define void @{helper}_destroy(ptr %slot) {{",
            "entry:",
            "  %value = load %rove_tagged, ptr %slot",
            "  %tag = extractvalue %rove_tagged %value, 0",
            "  %is_null = icmp eq ptr %tag, null",
            "  br i1 %is_null, label %clear, label %check0",
        ]
        boxed_variants = [
            (
                name,
                tuple(
                    (index, payload)
                    for index, payload in enumerate(payloads)
                    if self._is_boxed_tag_payload(payload)
                ),
            )
            for name, payloads in variants
            if any(self._is_boxed_tag_payload(payload) for payload in payloads)
        ]
        for ordinal, (name, boxed_payloads) in enumerate(boxed_variants):
            next_label = f"check{ordinal + 1}" if ordinal + 1 < len(boxed_variants) else "clear"
            tag_name = self.string_names[name][0]
            lines.extend((
                f"check{ordinal}:",
                f"  %cmp{ordinal} = call i32 @strcmp(ptr %tag, ptr @{tag_name})",
                f"  %matched{ordinal} = icmp eq i32 %cmp{ordinal}, 0",
                f"  br i1 %matched{ordinal}, label %destroy{ordinal}, label %{next_label}",
                f"destroy{ordinal}:",
            ))
            for index, payload_type in boxed_payloads:
                suffix_id = f"{ordinal}_{index}"
                lines.extend((
                    f"  %encoded{suffix_id} = extractvalue %rove_tagged %value, 1, {index}",
                    f"  %box{suffix_id} = inttoptr i64 %encoded{suffix_id} to ptr",
                ))
                array = self._array_spec(payload_type)
                if array is not None:
                    _descriptor_type, _element_type, _stride, suffix = array
                    lines.append(f"  call void @rove_array_{suffix}_destroy(ptr %box{suffix_id})")
                else:
                    lines.append(
                        f"  call void @rove_struct_{_identifier(payload_type.name)}_destroy(ptr %box{suffix_id})"
                    )
                lines.append(f"  call void @free(ptr %box{suffix_id})")
            lines.append("  br label %clear")
        lines.extend((
            "clear:",
            "  store %rove_tagged zeroinitializer, ptr %slot",
            "  ret void",
            "}",
        ))
        return "\n".join(lines)

    @staticmethod
    def _division_helpers() -> str:
        return """define i64 @rove_i64_div(i64 %left, i64 %right) {
entry:
  %zero = icmp eq i64 %right, 0
  br i1 %zero, label %fail, label %check
fail:
  call void @exit(i32 1)
  unreachable
check:
  %is_min = icmp eq i64 %left, -9223372036854775808
  %is_neg_one = icmp eq i64 %right, -1
  %overflow = and i1 %is_min, %is_neg_one
  br i1 %overflow, label %wrapped, label %normal
wrapped:
  ret i64 -9223372036854775808
normal:
  %value = sdiv i64 %left, %right
  ret i64 %value
}

define i64 @rove_i64_rem(i64 %left, i64 %right) {
entry:
  %zero = icmp eq i64 %right, 0
  br i1 %zero, label %fail, label %check
fail:
  call void @exit(i32 1)
  unreachable
check:
  %is_min = icmp eq i64 %left, -9223372036854775808
  %is_neg_one = icmp eq i64 %right, -1
  %overflow = and i1 %is_min, %is_neg_one
  br i1 %overflow, label %wrapped, label %normal
wrapped:
  ret i64 0
normal:
  %value = srem i64 %left, %right
  ret i64 %value
}
"""

    @staticmethod
    def _array_helpers() -> str:
        sections: list[str] = []
        for descriptor, element, stride, suffix in (
            ("%rove_array_i64", "i64", 8, "i64"),
            ("%rove_array_bool", "i1", 1, "bool"),
            ("%rove_array_f64", "double", 8, "f64"),
            ("%rove_array_string", "ptr", 8, "string"),
        ):
            sections.append(
                f"""{descriptor} = type {{ ptr, i64 }}

define {descriptor} @rove_array_{suffix}_clone({descriptor} %value) {{
entry:
  %data = extractvalue {descriptor} %value, 0
  %length = extractvalue {descriptor} %value, 1
  %bytes = mul i64 %length, {stride}
  %copy = call ptr @malloc(i64 %bytes)
  call void @llvm.memcpy.p0.p0.i64(ptr %copy, ptr %data, i64 %bytes, i1 false)
  %with_data = insertvalue {descriptor} poison, ptr %copy, 0
  %result = insertvalue {descriptor} %with_data, i64 %length, 1
  ret {descriptor} %result
}}

define ptr @rove_array_{suffix}_at(ptr %descriptor, i64 %index) {{
entry:
  %length_ptr = getelementptr inbounds {descriptor}, ptr %descriptor, i32 0, i32 1
  %length = load i64, ptr %length_ptr
  %negative = icmp slt i64 %index, 0
  %past_end = icmp sge i64 %index, %length
  %invalid = or i1 %negative, %past_end
  br i1 %invalid, label %fail, label %valid
fail:
  call void @exit(i32 1)
  unreachable
valid:
  %data_ptr = getelementptr inbounds {descriptor}, ptr %descriptor, i32 0, i32 0
  %data = load ptr, ptr %data_ptr
  %element = getelementptr inbounds {element}, ptr %data, i64 %index
  ret ptr %element
}}

define void @rove_array_{suffix}_destroy(ptr %descriptor) {{
entry:
  %data_ptr = getelementptr inbounds {descriptor}, ptr %descriptor, i32 0, i32 0
  %data = load ptr, ptr %data_ptr
  call void @free(ptr %data)
  store {descriptor} zeroinitializer, ptr %descriptor
  ret void
}}"""
            )
        return "\n\n".join(sections) + "\n"

    def _collect_strings(self) -> None:
        for text in (
            "Ok",
            "Err",
            "Some",
            "None",
            *(variant.name for definition in self.enums.values() for variant in definition.variants),
            *(definition.name for definition in self.structs.values()),
        ):
            if text not in self.string_names:
                self.string_names[text] = (
                    f".str.{len(self.string_names)}", _escape_bytes(text)[1]
                )

        def operand(value: Operand) -> None:
            if isinstance(value, ConstOperand) and value.type.name == "string":
                text = str(value.value)
                if text not in self.string_names:
                    self.string_names[text] = (f".str.{len(self.string_names)}", _escape_bytes(text)[1])

        for function in self.module.functions:
            for block in function.blocks:
                for statement in block.statements:
                    if not isinstance(statement, AssignStatement):
                        continue
                    value = statement.value
                    if isinstance(value, UseRValue):
                        operand(value.operand)
                    elif isinstance(value, BinaryRValue):
                        operand(value.left)
                        operand(value.right)
                    elif isinstance(value, (UnaryRValue, CastRValue)):
                        operand(value.operand)
                    elif isinstance(value, AggregateRValue):
                        if value.kind in {"enum", "option", "result"}:
                            text = value.name
                            if text not in self.string_names:
                                self.string_names[text] = (
                                    f".str.{len(self.string_names)}",
                                    _escape_bytes(text)[1],
                                )
                        for item in value.operands:
                            operand(item)
                terminator = block.terminator
                if isinstance(terminator, CallTerminator):
                    for argument in terminator.arguments:
                        operand(argument)
                elif isinstance(terminator, (SwitchIntTerminator, SwitchValueTerminator)):
                    operand(terminator.discriminator)
                    if isinstance(terminator, SwitchValueTerminator):
                        for case, _target in terminator.targets:
                            text = str(case)
                            if text not in self.string_names:
                                self.string_names[text] = (
                                    f".str.{len(self.string_names)}",
                                    _escape_bytes(text)[1],
                                )
                elif isinstance(terminator, AssertTerminator):
                    operand(terminator.condition)

    def _function(self, function: MIRFunction) -> str:
        self.current = function
        self.local_types = {local.id: local.type for local in function.locals}
        self.temp = 0
        self.synthetic_block = 0
        self.extra_blocks = []
        parameters = ", ".join(
            f"{self._type(function.locals[local].type)} %arg{local}"
            for local in function.parameters
        )
        return_type = "i32" if function.name == "main" else self._type(function.locals[0].type)
        lines = [f"define {return_type} @{self.function_names[function.symbol]}({parameters}) {{", "entry:"]
        for local in function.locals:
            if local.type.name == "void":
                continue
            if function.name == "main" and local.id == 0 and local.type.name == "any":
                continue
            lines.append(f"  %l{local.id} = alloca {self._type(local.type)}")
        for local in function.parameters:
            lines.append(f"  store {self._type(self.local_types[local])} %arg{local}, ptr %l{local}")
        lines.append("  br label %bb0")
        for block in function.blocks:
            self.lines = [f"bb{block.id}:"]
            for statement in block.statements:
                self._statement(statement)
            self._terminator(block.terminator)
            lines.extend(self.lines)
        for block in self.extra_blocks:
            lines.extend(block)
        lines.append("}")
        self.current = None
        self.local_types = {}
        return "\n".join(lines) + "\n"

    def _statement(self, statement: object) -> None:
        if isinstance(statement, AssignStatement):
            destination = self._place_type(statement.place)
            if destination.name == "void":
                return
            if self.current is not None and self.current.name == "main" and statement.place.local == 0:
                raise MIRCodegenError("MIR main may not assign its synthetic 'any' return local")
            value_type, value = self._rvalue(statement.value)
            expected = self._type(destination)
            if value_type != expected:
                raise MIRCodegenError(f"LLVM assignment type mismatch: expected {expected}, got {value_type}")
            self.lines.append(f"  store {value_type} {value}, ptr {self._place(statement.place)}")
            return
        if isinstance(statement, (StorageLiveStatement, StorageDeadStatement, NopStatement)):
            return
        if isinstance(statement, DeinitStatement):
            self._destroy_place(statement.place)
            return
        raise MIRCodegenError(f"illegal statement reached LLVM emitter: {type(statement).__name__}")

    def _terminator(self, terminator: object) -> None:
        if isinstance(terminator, GotoTerminator):
            self.lines.append(f"  br label %bb{terminator.target}")
            return
        if isinstance(terminator, SwitchValueTerminator):
            value_type, value = self._operand(terminator.discriminator)
            if value_type != "ptr":
                raise MIRCodegenError(
                    f"LLVM SwitchValue requires a string discriminator, got '{value_type}'"
                )
            self._string_switch(value, terminator.targets, terminator.otherwise)
            return
        if isinstance(terminator, SwitchIntTerminator):
            value_type, value = self._operand(terminator.discriminator)
            targets = " ".join(
                f"{value_type} {self._constant(case, value_type)}, label %bb{target}"
                for case, target in terminator.targets
            )
            self.lines.append(f"  switch {value_type} {value}, label %bb{terminator.otherwise} [ {targets} ]")
            return
        if isinstance(terminator, CallTerminator):
            if terminator.target is None:
                raise MIRCodegenError(f"call '{terminator.function}' has no continuation")
            if terminator.function == "builtin::print":
                self._print(tuple(terminator.arguments))
            elif terminator.function == "builtin::len":
                if len(terminator.arguments) != 1 or terminator.destination is None:
                    raise MIRCodegenError("builtin::len requires one argument and a destination")
                argument = terminator.arguments[0]
                argument_type = self._operand_mir_type(argument)
                array = self._array_spec(argument_type)
                length = self._temp()
                if array is not None:
                    descriptor_type, _element_type, _stride, _suffix = array
                    _, descriptor = self._operand(argument, clone_owned=False)
                    self.lines.append(
                        f"  {length} = extractvalue {descriptor_type} {descriptor}, 1"
                    )
                elif argument_type == MIRType("string"):
                    _, string_value = self._operand(argument, clone_owned=False)
                    self.lines.append(f"  {length} = call i64 @strlen(ptr {string_value})")
                else:
                    raise MIRCodegenError(
                        "LLVM builtin::len pilot requires string or a supported Array value"
                    )
                self.lines.append(
                    f"  store i64 {length}, ptr {self._place(terminator.destination)}"
                )
                if (
                    isinstance(argument, MoveOperand)
                    and self._type_requires_drop(argument_type)
                ):
                    self._destroy_place(argument.place)
            elif terminator.function in self.function_names:
                arguments = [self._operand(argument) for argument in terminator.arguments]
                rendered = ", ".join(f"{kind} {value}" for kind, value in arguments)
                function = next(item for item in self.module.functions if item.symbol == terminator.function)
                result_type = self._type(function.locals[0].type)
                if result_type == "void":
                    self.lines.append(f"  call void @{self.function_names[terminator.function]}({rendered})")
                else:
                    temp = self._temp()
                    self.lines.append(f"  {temp} = call {result_type} @{self.function_names[terminator.function]}({rendered})")
                    if terminator.destination is None:
                        raise MIRCodegenError(f"non-void call '{terminator.function}' has no destination")
                    self.lines.append(f"  store {result_type} {temp}, ptr {self._place(terminator.destination)}")
            else:
                raise MIRCodegenError(f"illegal runtime call reached LLVM emitter: {terminator.function}")
            self.lines.append(f"  br label %bb{terminator.target}")
            return
        if isinstance(terminator, AssertTerminator):
            value_type, value = self._operand(terminator.condition)
            if value_type != "i1":
                raise MIRCodegenError("LLVM assertion condition must be i1")
            failure = f"assert_fail_{self.synthetic_block}"
            self.synthetic_block += 1
            true_target = f"bb{terminator.target}" if terminator.expected else failure
            false_target = failure if terminator.expected else f"bb{terminator.target}"
            self.lines.append(f"  br i1 {value}, label %{true_target}, label %{false_target}")
            self.extra_blocks.append([failure + ":", "  call void @exit(i32 1)", "  unreachable"])
            return
        if isinstance(terminator, DropTerminator):
            if terminator.unwind is not None:
                raise MIRCodegenError("LLVM MIR drop unwind edge was not legalized")
            self._destroy_place(terminator.place)
            self.lines.append(f"  br label %bb{terminator.target}")
            return
        if isinstance(terminator, ReturnTerminator):
            assert self.current is not None
            if self.current.name == "main":
                self.lines.append("  ret i32 0")
                return
            result_type = self._type(self.local_types[self.current.return_local])
            if result_type == "void":
                self.lines.append("  ret void")
                return
            temp = self._load(self.current.return_local)
            self.lines.append(f"  ret {result_type} {temp}")
            return
        if isinstance(terminator, UnreachableTerminator):
            self.lines.append("  unreachable")
            return
        raise MIRCodegenError(f"illegal terminator reached LLVM emitter: {type(terminator).__name__}")

    def _string_switch(
        self,
        value: str,
        targets: tuple[tuple[object, int], ...],
        otherwise: int,
    ) -> None:
        if not targets:
            self.lines.append(f"  br label %bb{otherwise}")
            return
        for index, (case, target) in enumerate(targets):
            case_name = self.string_names[str(case)][0]
            compared = self._temp()
            matched = self._temp()
            self.lines.append(f"  {compared} = call i32 @strcmp(ptr {value}, ptr @{case_name})")
            self.lines.append(f"  {matched} = icmp eq i32 {compared}, 0")
            if index + 1 == len(targets):
                next_target = f"bb{otherwise}"
            else:
                next_target = f"string_switch_{self.synthetic_block}"
                self.synthetic_block += 1
            self.lines.append(
                f"  br i1 {matched}, label %bb{target}, label %{next_target}"
            )
            if index + 1 != len(targets):
                self.lines.append(next_target + ":")

    def _print(self, arguments: tuple[Operand, ...]) -> None:
        for index, argument in enumerate(arguments):
            if index:
                self.lines.append("  call i32 (ptr, ...) @printf(ptr @.space)")
            kind, value = self._operand(argument, clone_owned=False)
            value_type = self._operand_mir_type(argument)
            if kind == "%rove_tagged" and value_type is not None:
                self._print_tagged(value_type, value)
            else:
                self._print_typed_value(value_type, kind, value)
            if (
                isinstance(argument, MoveOperand)
                and value_type is not None
                and self._type_requires_drop(value_type)
            ):
                self._destroy_place(argument.place)
        self.lines.append("  call i32 (ptr, ...) @printf(ptr @.newline)")

    def _print_scalar(self, kind: str, value: str) -> None:
        if kind == "i64":
            self.lines.append(f"  call i32 (ptr, ...) @printf(ptr @.fmt_i64, i64 {value})")
        elif kind == "double":
            self.lines.append(f"  call void @rove_print_f64(double {value})")
        elif kind == "i1":
            selected = self._temp()
            self.lines.append(f"  {selected} = select i1 {value}, ptr @.true, ptr @.false")
            self.lines.append(f"  call i32 (ptr, ...) @printf(ptr @.fmt_str, ptr {selected})")
        elif kind == "ptr":
            self.lines.append(f"  call i32 (ptr, ...) @printf(ptr @.fmt_str, ptr {value})")
        else:
            raise MIRCodegenError(f"LLVM print does not support value type '{kind}'")

    def _print_tagged(self, value_type: MIRType, value: str) -> None:
        variants = self._tag_variants(value_type)
        if variants is None:
            raise MIRCodegenError(
                f"LLVM print does not support tagged value type '{value_type}'"
            )
        tag = self._temp()
        self.lines.append(f"  {tag} = extractvalue %rove_tagged {value}, 0")
        self._print_scalar("ptr", tag)
        self.lines.append("  call i32 (ptr, ...) @printf(ptr @.open)")

        serial = self.synthetic_block
        self.synthetic_block += 1
        done_label = f"tag_print_done_{serial}"
        fallback_label = f"tag_print_fallback_{serial}"
        variant_labels = [f"tag_print_variant_{serial}_{index}" for index in range(len(variants))]
        for index, ((name, _payloads), label) in enumerate(zip(variants, variant_labels)):
            compared = self._temp()
            matched = self._temp()
            tag_name = self.string_names[name][0]
            self.lines.append(f"  {compared} = call i32 @strcmp(ptr {tag}, ptr @{tag_name})")
            self.lines.append(f"  {matched} = icmp eq i32 {compared}, 0")
            next_label = (
                fallback_label
                if index + 1 == len(variants)
                else f"tag_print_check_{serial}_{index + 1}"
            )
            self.lines.append(
                f"  br i1 {matched}, label %{label}, label %{next_label}"
            )
            if index + 1 != len(variants):
                self.lines.append(next_label + ":")
        if not variants:
            self.lines.append(f"  br label %{fallback_label}")

        self.lines.append(fallback_label + ":")
        self.lines.append(f"  br label %{done_label}")
        for label, (_name, payloads) in zip(variant_labels, variants):
            self.lines.append(label + ":")
            for index, payload_type in enumerate(payloads):
                if index:
                    self.lines.append("  call i32 (ptr, ...) @printf(ptr @.comma)")
                kind, payload = self._decode_tag_payload(value, index, payload_type)
                self._print_typed_value(payload_type, kind, payload)
            self.lines.append(f"  br label %{done_label}")
        self.lines.append(done_label + ":")
        self.lines.append("  call i32 (ptr, ...) @printf(ptr @.close)")

    def _print_typed_value(self, value_type: MIRType, kind: str, value: str) -> None:
        if self._array_spec(value_type) is not None:
            self._print_array(value_type, value)
            return
        if value_type.name in self.structs:
            self._print_struct(value_type, value)
            return
        self._print_scalar(kind, value)

    def _print_struct(self, value_type: MIRType, value: str) -> None:
        definition = self.structs[value_type.name]
        name = self.string_names[definition.name][0]
        self._print_scalar("ptr", f"@{name}")
        self.lines.append("  call i32 (ptr, ...) @printf(ptr @.open)")
        for index, field in enumerate(definition.fields):
            if index:
                self.lines.append("  call i32 (ptr, ...) @printf(ptr @.comma)")
            field_value = self._temp()
            field_kind = self._type(field.type)
            self.lines.append(
                f"  {field_value} = extractvalue {self._type(value_type)} {value}, {index}"
            )
            self._print_typed_value(field.type, field_kind, field_value)
        self.lines.append("  call i32 (ptr, ...) @printf(ptr @.close)")

    def _print_array(self, value_type: MIRType, value: str) -> None:
        array = self._array_spec(value_type)
        if array is None:
            raise MIRCodegenError(f"LLVM print does not support array type '{value_type}'")
        descriptor_type, element_type, _stride, _suffix = array
        serial = self.synthetic_block
        self.synthetic_block += 1
        check_label = f"array_print_check_{serial}"
        body_label = f"array_print_body_{serial}"
        comma_label = f"array_print_comma_{serial}"
        value_label = f"array_print_value_{serial}"
        done_label = f"array_print_done_{serial}"
        data = self._temp()
        length = self._temp()
        index_slot = self._temp()
        self.lines.extend((
            "  call i32 (ptr, ...) @printf(ptr @.array_open)",
            f"  {data} = extractvalue {descriptor_type} {value}, 0",
            f"  {length} = extractvalue {descriptor_type} {value}, 1",
            f"  {index_slot} = alloca i64",
            f"  store i64 0, ptr {index_slot}",
            f"  br label %{check_label}",
            check_label + ":",
        ))
        index = self._temp()
        more = self._temp()
        self.lines.extend((
            f"  {index} = load i64, ptr {index_slot}",
            f"  {more} = icmp slt i64 {index}, {length}",
            f"  br i1 {more}, label %{body_label}, label %{done_label}",
            body_label + ":",
        ))
        has_prefix = self._temp()
        self.lines.extend((
            f"  {has_prefix} = icmp ne i64 {index}, 0",
            f"  br i1 {has_prefix}, label %{comma_label}, label %{value_label}",
            comma_label + ":",
            "  call i32 (ptr, ...) @printf(ptr @.comma)",
            f"  br label %{value_label}",
            value_label + ":",
        ))
        element_ptr = self._temp()
        element = self._temp()
        self.lines.extend((
            f"  {element_ptr} = getelementptr inbounds {element_type}, ptr {data}, i64 {index}",
            f"  {element} = load {element_type}, ptr {element_ptr}",
        ))
        self._print_typed_value(value_type.arguments[0], element_type, element)
        next_index = self._temp()
        self.lines.extend((
            f"  {next_index} = add i64 {index}, 1",
            f"  store i64 {next_index}, ptr {index_slot}",
            f"  br label %{check_label}",
            done_label + ":",
            "  call i32 (ptr, ...) @printf(ptr @.array_close)",
        ))

    def _tag_variants(
        self, value_type: MIRType
    ) -> tuple[tuple[str, tuple[MIRType, ...]], ...] | None:
        if value_type.name == "Result" and len(value_type.arguments) == 2:
            ok_type, error_type = value_type.arguments
            if ok_type.name == "any" or error_type.name == "any":
                return None
            return (("Ok", (ok_type,)), ("Err", (error_type,)))
        if value_type.name == "Option" and len(value_type.arguments) == 1:
            payload_type = value_type.arguments[0]
            if payload_type.name == "any":
                return None
            return (("Some", (payload_type,)), ("None", ()))
        definition = self.enums.get(value_type.name)
        if definition is None:
            return None
        return tuple(
            (variant.name, variant.payload_types) for variant in definition.variants
        )

    def _tag_lifecycle_variants(
        self, value_type: MIRType
    ) -> tuple[tuple[str, tuple[MIRType, ...]], ...]:
        if value_type.name == "Result" and len(value_type.arguments) == 2:
            ok_type, error_type = value_type.arguments
            return (("Ok", (ok_type,)), ("Err", (error_type,)))
        if value_type.name == "Option" and len(value_type.arguments) == 1:
            return (("Some", (value_type.arguments[0],)), ("None", ()))
        definition = self.enums.get(value_type.name)
        if definition is None:
            return ()
        return tuple(
            (variant.name, variant.payload_types) for variant in definition.variants
        )

    def _is_boxed_tag_payload(self, value_type: MIRType) -> bool:
        return bool(
            self._array_spec(value_type) is not None
            or (
                value_type.name in self.structs
                and not value_type.arguments
                and not value_type.optional
                and not value_type.pointer
            )
        )

    def _tag_has_boxed_payload(self, value_type: MIRType) -> bool:
        return any(
            self._is_boxed_tag_payload(payload)
            for _name, payloads in self._tag_lifecycle_variants(value_type)
            for payload in payloads
        )

    def _type_requires_drop(
        self, value_type: MIRType, stack: tuple[str, ...] = ()
    ) -> bool:
        if self._array_spec(value_type) is not None or self._tag_has_boxed_payload(value_type):
            return True
        if value_type.name in stack:
            return False
        definition = self.structs.get(value_type.name)
        return bool(
            definition is not None
            and any(
                self._type_requires_drop(field.type, stack + (value_type.name,))
                for field in definition.fields
            )
        )

    @staticmethod
    def _type_mangle(value_type: MIRType) -> str:
        rendered = value_type.name
        if value_type.arguments:
            rendered += "_" + "_".join(
                _LLVMEmitter._type_mangle(argument) for argument in value_type.arguments
            )
        if value_type.pointer:
            rendered = "ptr_" + rendered
        if value_type.optional:
            rendered += "_optional"
        return _identifier(rendered)

    def _tagged_helper_name(self, value_type: MIRType) -> str:
        return f"rove_tagged_{self._type_mangle(value_type)}"

    def _rvalue(self, value: object) -> tuple[str, str]:
        if isinstance(value, UseRValue):
            return self._operand(value.operand)
        if isinstance(value, BinaryRValue):
            return self._binary(value)
        if isinstance(value, UnaryRValue):
            kind, operand = self._operand(value.operand)
            result = self._temp()
            if value.op in ("!", "not") and kind == "i1":
                self.lines.append(f"  {result} = xor i1 {operand}, true")
            elif value.op == "-" and kind == "i64":
                self.lines.append(f"  {result} = sub i64 0, {operand}")
            elif value.op == "-" and kind == "double":
                self.lines.append(f"  {result} = fneg double {operand}")
            elif value.op == "+":
                return kind, operand
            elif value.op == "~" and kind == "i64":
                self.lines.append(f"  {result} = xor i64 {operand}, -1")
            else:
                raise MIRCodegenError(f"unsupported LLVM unary operation '{value.op}' for {kind}")
            return kind, result
        if isinstance(value, CastRValue):
            source_type, operand = self._operand(value.operand)
            target_type = self._type(value.type)
            if source_type == target_type:
                return target_type, operand
            result = self._temp()
            instruction = {
                ("i64", "double"): "sitofp",
                ("double", "i64"): "fptosi",
                ("i1", "i64"): "zext",
                ("i64", "i1"): "trunc",
            }.get((source_type, target_type))
            if instruction is None:
                raise MIRCodegenError(f"unsupported LLVM cast {source_type} -> {target_type}")
            self.lines.append(f"  {result} = {instruction} {source_type} {operand} to {target_type}")
            return target_type, result
        if isinstance(value, AggregateRValue):
            if value.kind == "array":
                array = self._array_spec(value.type)
                if array is None:
                    raise MIRCodegenError(
                        f"LLVM array aggregate requires a supported Array type, got '{value.type}'"
                    )
                descriptor_type, element_type, stride, _suffix = array
                data = self._temp()
                if stride is None:
                    size_ptr = self._temp()
                    element_size = self._temp()
                    bytes_count = self._temp()
                    self.lines.extend((
                        f"  {size_ptr} = getelementptr {element_type}, ptr null, i32 1",
                        f"  {element_size} = ptrtoint ptr {size_ptr} to i64",
                        f"  {bytes_count} = mul i64 {len(value.operands)}, {element_size}",
                        f"  {data} = call ptr @malloc(i64 {bytes_count})",
                    ))
                else:
                    self.lines.append(
                        f"  {data} = call ptr @malloc(i64 {len(value.operands) * stride})"
                    )
                for index, operand in enumerate(value.operands):
                    operand_type, rendered = self._operand(operand)
                    if operand_type != element_type:
                        raise MIRCodegenError(
                            f"LLVM array element expects {element_type}, got {operand_type}"
                        )
                    element = self._temp()
                    self.lines.append(
                        f"  {element} = getelementptr inbounds {element_type}, ptr {data}, i64 {index}"
                    )
                    self.lines.append(f"  store {element_type} {rendered}, ptr {element}")
                with_data = self._temp()
                aggregate = self._temp()
                self.lines.append(
                    f"  {with_data} = insertvalue {descriptor_type} poison, ptr {data}, 0"
                )
                self.lines.append(
                    f"  {aggregate} = insertvalue {descriptor_type} {with_data}, i64 {len(value.operands)}, 1"
                )
                return descriptor_type, aggregate
            if value.kind in {"enum", "option", "result"}:
                if len(value.operands) > 4:
                    raise MIRCodegenError(
                        "LLVM tagged-value pilot supports at most four payload values"
                    )
                tag_name = self.string_names[value.name][0]
                tagged = self._temp()
                self.lines.append(
                    f"  {tagged} = insertvalue %rove_tagged poison, ptr @{tag_name}, 0"
                )
                initialized = self._temp()
                self.lines.append(
                    f"  {initialized} = insertvalue %rove_tagged {tagged}, [4 x i64] zeroinitializer, 1"
                )
                aggregate = initialized
                for index, operand in enumerate(value.operands):
                    encoded = self._encode_tag_payload(operand)
                    inserted = self._temp()
                    self.lines.append(
                        f"  {inserted} = insertvalue %rove_tagged {aggregate}, i64 {encoded}, 1, {index}"
                    )
                    aggregate = inserted
                return "%rove_tagged", aggregate
            if value.kind != "struct":
                raise MIRCodegenError(
                    f"unsupported LLVM aggregate kind '{value.kind}'"
                )
            definition = self.structs.get(value.type.name)
            if definition is None or len(definition.fields) != len(value.operands):
                raise MIRCodegenError(
                    f"LLVM struct aggregate requires a complete definition for '{value.type}'"
                )
            aggregate_type = self._type(value.type)
            aggregate = "poison"
            for index, (field, operand) in enumerate(zip(definition.fields, value.operands)):
                operand_type, rendered = self._operand(operand)
                expected = self._type(field.type)
                if operand_type != expected:
                    raise MIRCodegenError(
                        f"LLVM struct field '{definition.name}.{field.name}' expects {expected}, got {operand_type}"
                    )
                inserted = self._temp()
                self.lines.append(
                    f"  {inserted} = insertvalue {aggregate_type} {aggregate}, {operand_type} {rendered}, {index}"
                )
                aggregate = inserted
            return aggregate_type, aggregate
        if isinstance(value, DiscriminantRValue):
            operand_type, operand = self._operand(value.operand, clone_owned=False)
            if operand_type != "%rove_tagged":
                raise MIRCodegenError(
                    f"LLVM discriminant requires a tagged value, got '{operand_type}'"
                )
            result = self._temp()
            self.lines.append(
                f"  {result} = extractvalue %rove_tagged {operand}, 0"
            )
            return "ptr", result
        if isinstance(value, PayloadRValue):
            operand_type, operand = self._operand(value.operand, clone_owned=False)
            if operand_type != "%rove_tagged":
                raise MIRCodegenError(
                    f"LLVM payload projection requires a tagged value, got '{operand_type}'"
                )
            return self._decode_tag_payload(
                operand,
                value.index,
                value.type,
                clone_payload=isinstance(value.operand, CopyOperand),
                consume_box=isinstance(value.operand, MoveOperand),
            )
        raise MIRCodegenError(f"illegal rvalue reached LLVM emitter: {type(value).__name__}")

    def _encode_tag_payload(self, operand: Operand) -> str:
        kind, rendered = self._operand(operand)
        value_type = self._operand_mir_type(operand)
        if self._is_boxed_tag_payload(value_type):
            size_ptr = self._temp()
            size = self._temp()
            boxed = self._temp()
            encoded = self._temp()
            self.lines.extend((
                f"  {size_ptr} = getelementptr {kind}, ptr null, i32 1",
                f"  {size} = ptrtoint ptr {size_ptr} to i64",
                f"  {boxed} = call ptr @malloc(i64 {size})",
                f"  store {kind} {rendered}, ptr {boxed}",
                f"  {encoded} = ptrtoint ptr {boxed} to i64",
            ))
            return encoded
        if kind == "i64":
            return rendered
        encoded = self._temp()
        if kind == "i1":
            self.lines.append(f"  {encoded} = zext i1 {rendered} to i64")
        elif kind == "ptr":
            self.lines.append(f"  {encoded} = ptrtoint ptr {rendered} to i64")
        elif kind == "double":
            self.lines.append(f"  {encoded} = bitcast double {rendered} to i64")
        else:
            raise MIRCodegenError(
                f"LLVM tagged payload does not support value type '{kind}'"
            )
        return encoded

    def _decode_tag_payload(
        self,
        operand: str,
        index: int,
        value_type: MIRType,
        *,
        clone_payload: bool = False,
        consume_box: bool = False,
    ) -> tuple[str, str]:
        if not 0 <= index < 4:
            raise MIRCodegenError(
                f"LLVM tagged payload index {index} is outside the four-slot pilot"
            )
        encoded = self._temp()
        self.lines.append(
            f"  {encoded} = extractvalue %rove_tagged {operand}, 1, {index}"
        )
        kind = self._type(value_type)
        if self._is_boxed_tag_payload(value_type):
            boxed = self._temp()
            decoded = self._temp()
            self.lines.append(f"  {boxed} = inttoptr i64 {encoded} to ptr")
            self.lines.append(f"  {decoded} = load {kind}, ptr {boxed}")
            if clone_payload:
                cloned = self._temp()
                array = self._array_spec(value_type)
                if array is not None:
                    descriptor_type, _element_type, _stride, suffix = array
                    self.lines.append(
                        f"  {cloned} = call {descriptor_type} @rove_array_{suffix}_clone({descriptor_type} {decoded})"
                    )
                else:
                    self.lines.append(
                        f"  {cloned} = call {kind} @rove_struct_{_identifier(value_type.name)}_clone({kind} {decoded})"
                    )
                return kind, cloned
            if consume_box:
                self.lines.append(f"  call void @free(ptr {boxed})")
            return kind, decoded
        if kind == "i64":
            return kind, encoded
        decoded = self._temp()
        if kind == "i1":
            self.lines.append(f"  {decoded} = trunc i64 {encoded} to i1")
        elif kind == "ptr":
            self.lines.append(f"  {decoded} = inttoptr i64 {encoded} to ptr")
        elif kind == "double":
            self.lines.append(f"  {decoded} = bitcast i64 {encoded} to double")
        else:
            raise MIRCodegenError(
                f"LLVM tagged payload does not support result type '{value_type}'"
            )
        return kind, decoded

    def _binary(self, value: BinaryRValue) -> tuple[str, str]:
        left_type, left = self._operand(value.left)
        right_type, right = self._operand(value.right)
        if left_type != right_type:
            raise MIRCodegenError(f"LLVM binary operand mismatch: {left_type} and {right_type}")
        result = self._temp()
        if value.op in ("==", "!=", "<", "<=", ">", ">="):
            if left_type == "ptr":
                compared = self._temp()
                self.lines.append(
                    f"  {compared} = call i32 @strcmp(ptr {left}, ptr {right})"
                )
                predicate = {
                    "==": "eq", "!=": "ne", "<": "slt", "<=": "sle",
                    ">": "sgt", ">=": "sge",
                }[value.op]
                self.lines.append(f"  {result} = icmp {predicate} i32 {compared}, 0")
            elif left_type == "double":
                predicate = {"==": "oeq", "!=": "one", "<": "olt", "<=": "ole", ">": "ogt", ">=": "oge"}[value.op]
                self.lines.append(f"  {result} = fcmp {predicate} double {left}, {right}")
            else:
                predicate = {"==": "eq", "!=": "ne", "<": "slt", "<=": "sle", ">": "sgt", ">=": "sge"}[value.op]
                self.lines.append(f"  {result} = icmp {predicate} {left_type} {left}, {right}")
            return "i1", result
        if left_type == "double":
            operation = {"+": "fadd", "-": "fsub", "*": "fmul", "/": "fdiv", "%": "frem"}.get(value.op)
            if operation is None:
                raise MIRCodegenError(f"unsupported LLVM floating operation '{value.op}'")
            self.lines.append(f"  {result} = {operation} double {left}, {right}")
            return "double", result
        if left_type != "i64":
            raise MIRCodegenError(f"unsupported LLVM binary type '{left_type}'")
        if value.op in ("/", "%"):
            helper = "rove_i64_div" if value.op == "/" else "rove_i64_rem"
            self.lines.append(f"  {result} = call i64 @{helper}(i64 {left}, i64 {right})")
            return "i64", result
        if value.op in ("<<", ">>"):
            masked = self._temp()
            self.lines.append(f"  {masked} = and i64 {right}, 63")
            operation = "shl" if value.op == "<<" else "ashr"
            self.lines.append(f"  {result} = {operation} i64 {left}, {masked}")
            return "i64", result
        operation = {"+": "add", "-": "sub", "*": "mul", "&": "and", "|": "or", "^": "xor"}.get(value.op)
        if operation is None:
            raise MIRCodegenError(f"unsupported LLVM integer operation '{value.op}'")
        self.lines.append(f"  {result} = {operation} i64 {left}, {right}")
        return "i64", result

    def _operand(self, operand: Operand, *, clone_owned: bool = True) -> tuple[str, str]:
        if isinstance(operand, ConstOperand):
            return self._type(operand.type), self._constant_operand(operand)
        if isinstance(operand, (CopyOperand, MoveOperand)):
            value_type = self._place_type(operand.place)
            kind = self._type(value_type)
            loaded = self._load(operand.place)
            array = self._array_spec(value_type)
            if isinstance(operand, CopyOperand) and clone_owned and array is not None:
                descriptor_type, _element_type, _stride, suffix = array
                cloned = self._temp()
                self.lines.append(
                    f"  {cloned} = call {descriptor_type} @rove_array_{suffix}_clone({descriptor_type} {loaded})"
                )
                return kind, cloned
            if isinstance(operand, CopyOperand) and clone_owned and value_type.name in self.structs:
                cloned = self._temp()
                self.lines.append(
                    f"  {cloned} = call {kind} @rove_struct_{_identifier(value_type.name)}_clone({kind} {loaded})"
                )
                return kind, cloned
            if (
                isinstance(operand, CopyOperand)
                and clone_owned
                and self._tag_has_boxed_payload(value_type)
            ):
                cloned = self._temp()
                helper = self._tagged_helper_name(value_type)
                self.lines.append(
                    f"  {cloned} = call %rove_tagged @{helper}_clone(%rove_tagged {loaded})"
                )
                return kind, cloned
            return kind, loaded
        raise MIRCodegenError(f"illegal operand reached LLVM emitter: {type(operand).__name__}")

    def _operand_mir_type(self, operand: Operand) -> MIRType:
        if isinstance(operand, ConstOperand):
            return operand.type
        if isinstance(operand, (CopyOperand, MoveOperand)):
            return self._place_type(operand.place)
        raise MIRCodegenError(f"unknown LLVM operand type: {type(operand).__name__}")

    def _load(self, place: Place | int) -> str:
        if isinstance(place, int):
            place = Place(place)
        kind = self._type(self._place_type(place))
        temp = self._temp()
        self.lines.append(f"  {temp} = load {kind}, ptr {self._place(place)}")
        return temp

    def _place(self, place: Place) -> str:
        rendered = f"%l{place.local}"
        value_type = self.local_types[place.local]
        for projection in place.projections:
            if isinstance(projection, (ConstantIndexProjection, IndexProjection)):
                array = self._array_spec(value_type)
                if array is None:
                    raise MIRCodegenError(
                        "LLVM index projection requires "
                        f"Array<int|bool|float|string|acyclic-struct>, got '{value_type}'"
                    )
                _descriptor_type, _element_type, _stride, suffix = array
                index = (
                    str(projection.index)
                    if isinstance(projection, ConstantIndexProjection)
                    else self._load(projection.local)
                )
                projected = self._temp()
                self.lines.append(
                    f"  {projected} = call ptr @rove_array_{suffix}_at(ptr {rendered}, i64 {index})"
                )
                rendered = projected
                value_type = value_type.arguments[0]
                continue
            if not isinstance(projection, FieldProjection):
                raise MIRCodegenError(
                    f"illegal projection reached LLVM struct emitter: {type(projection).__name__}"
                )
            definition = self.structs.get(value_type.name)
            if definition is None:
                raise MIRCodegenError(
                    f"LLVM field projection requires a known struct, got '{value_type}'"
                )
            index = next(
                (offset for offset, field in enumerate(definition.fields) if field.name == projection.name),
                None,
            )
            if index is None:
                raise MIRCodegenError(
                    f"LLVM struct '{definition.name}' has no field '{projection.name}'"
                )
            projected = self._temp()
            self.lines.append(
                f"  {projected} = getelementptr inbounds {self._type(value_type)}, ptr {rendered}, i32 0, i32 {index}"
            )
            rendered = projected
            value_type = definition.fields[index].type
        return rendered

    def _place_type(self, place: Place) -> MIRType:
        value_type = self.local_types[place.local]
        for projection in place.projections:
            if isinstance(projection, (ConstantIndexProjection, IndexProjection)):
                if self._array_spec(value_type) is None:
                    raise MIRCodegenError(
                        "LLVM index projection requires "
                        f"Array<int|bool|float|string|acyclic-struct>, got '{value_type}'"
                    )
                value_type = value_type.arguments[0]
                continue
            if not isinstance(projection, FieldProjection):
                raise MIRCodegenError(
                    f"illegal projection type reached LLVM struct emitter: {type(projection).__name__}"
                )
            definition = self.structs.get(value_type.name)
            field = next(
                (field for field in definition.fields if field.name == projection.name),
                None,
            ) if definition is not None else None
            if field is None:
                raise MIRCodegenError(
                    f"LLVM field projection requires '{value_type}.{projection.name}'"
                )
            value_type = field.type
        return value_type

    def _destroy_place(self, place: Place) -> None:
        value_type = self._place_type(place)
        rendered = self._place(place)
        array = self._array_spec(value_type)
        if array is not None:
            _descriptor_type, _element_type, _stride, suffix = array
            self.lines.append(f"  call void @rove_array_{suffix}_destroy(ptr {rendered})")
            return
        if value_type.name in self.structs:
            self.lines.append(
                f"  call void @rove_struct_{_identifier(value_type.name)}_destroy(ptr {rendered})"
            )
            return
        if self._tag_has_boxed_payload(value_type):
            helper = self._tagged_helper_name(value_type)
            self.lines.append(f"  call void @{helper}_destroy(ptr {rendered})")
            return
        self.lines.append(f"  store {self._type(value_type)} zeroinitializer, ptr {rendered}")

    def _constant_operand(self, operand: ConstOperand) -> str:
        value = operand.value
        kind = self._type(operand.type)
        if kind == "i64":
            bits = int(value) & ((1 << 64) - 1)
            return str(bits - (1 << 64) if bits & (1 << 63) else bits)
        if kind == "i1":
            return "true" if bool(value) else "false"
        if kind == "double":
            number = float(value)
            if not math.isfinite(number):
                raise MIRCodegenError("non-finite LLVM constants are not part of the MIR pilot")
            return format(number, ".17e")
        if kind == "ptr":
            return "@" + self.string_names[str(value)][0]
        raise MIRCodegenError(f"unsupported LLVM constant type '{operand.type}'")

    @staticmethod
    def _constant(value: object, kind: str) -> str:
        if kind == "i1":
            return "true" if bool(value) else "false"
        if kind == "i64":
            return str(int(value))
        raise MIRCodegenError(f"unsupported LLVM switch constant type '{kind}'")

    def _array_spec(self, value: MIRType) -> tuple[str, str, int | None, str] | None:
        if value.name != "Array" or len(value.arguments) != 1:
            return None
        element = value.arguments[0]
        primitive = {
            MIRType("int"): ("%rove_array_i64", "i64", 8, "i64"),
            MIRType("bool"): ("%rove_array_bool", "i1", 1, "bool"),
            MIRType("float"): ("%rove_array_f64", "double", 8, "f64"),
            MIRType("f64"): ("%rove_array_f64", "double", 8, "f64"),
            MIRType("string"): ("%rove_array_string", "ptr", 8, "string"),
        }.get(element)
        if primitive is not None:
            return primitive
        if (
            element.name in self.structs
            and not element.arguments
            and not element.optional
            and not element.pointer
        ):
            identifier = _identifier(element.name)
            return (
                f"%rove_array_struct_{identifier}",
                f"%rove_type_{identifier}",
                None,
                f"struct_{identifier}",
            )
        nested = self._array_spec(element)
        if nested is not None:
            nested_descriptor, _nested_element, _nested_stride, nested_suffix = nested
            suffix = f"array_{nested_suffix}"
            return (
                f"%rove_array_{suffix}",
                nested_descriptor,
                None,
                suffix,
            )
        return None

    def _type(self, value: MIRType) -> str:
        if value.name == "void":
            return "void"
        if value.name == "bool":
            return "i1"
        if value.name in _INTEGER_TYPES:
            return "i64"
        if value.name in _FLOAT_TYPES:
            return "double"
        if value.name == "string":
            return "ptr"
        array = self._array_spec(value)
        if array is not None:
            return array[0]
        if value.name in {"Option", "Result"} and value.arguments:
            return "%rove_tagged"
        if value.name in self.enums and not value.arguments and not value.optional and not value.pointer:
            return "%rove_tagged"
        if value.name in self.structs and not value.arguments and not value.optional and not value.pointer:
            return f"%rove_type_{_identifier(value.name)}"
        raise MIRCodegenError(f"unsupported LLVM MIR type '{value}'")

    def _temp(self) -> str:
        value = f"%t{self.temp}"
        self.temp += 1
        return value


def emit_legalized_llvm(module: MIRModule) -> str:
    """Validate and emit the M5 LLVM pilot without semantic fallback."""
    legalized = legalize_mir(module, "llvm", require_emitter=True)
    return _LLVMEmitter(legalized).emit()
