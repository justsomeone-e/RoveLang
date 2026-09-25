"""C++20 emitter for the legalized scalar/control-flow MIR pilot."""

from __future__ import annotations

import json
import math
import re
from dataclasses import replace

from .legalization import MIRLegalizationError, legalize_mir
from .model import (
    AssertTerminator,
    AssignStatement,
    AggregateRValue,
    BinaryRValue,
    BorrowRValue,
    CallTerminator,
    CastRValue,
    ConstOperand,
    ConstantIndexProjection,
    CopyOperand,
    DeinitStatement,
    DerefProjection,
    DiscriminantRValue,
    FieldProjection,
    GotoTerminator,
    DropTerminator,
    MIRFunction,
    MIRModule,
    MIREnumDef,
    MIRStructDef,
    MoveOperand,
    NopStatement,
    Operand,
    Place,
    PayloadRValue,
    ReleaseStatement,
    RetainStatement,
    ReturnTerminator,
    StorageDeadStatement,
    StorageLiveStatement,
    SuspendTerminator,
    SwitchIntTerminator,
    SwitchValueTerminator,
    ThrowTerminator,
    IndexProjection,
    UnaryRValue,
    UnreachableTerminator,
    UseRValue,
)
from .types import MIRType


class MIRCodegenError(ValueError):
    code = "MIRG1010"

    def __init__(self, message: str):
        super().__init__(f"{self.code}: {message}")


_INTEGER_TYPES = frozenset({"int", "i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64"})
_FLOAT_TYPES = frozenset({"float", "f32", "f64"})


def _identifier(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not clean or clean[0].isdigit():
        clean = "_" + clean
    return clean


class _CppEmitter:
    def __init__(self, module: MIRModule):
        self.module = module
        self.function_names = {
            function.symbol: f"rove_fn_{_identifier(function.name)}"
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
        self.current: MIRFunction | None = None
        self.local_types: dict[int, MIRType] = {}

    def emit(self) -> str:
        declarations = [self._prototype(function) + ";" for function in self.module.functions]
        definitions = [self._function(function) for function in self.module.functions]
        parts = [
            "// Experimental Rove legalized MIR -> C++20 output.",
            "// The production Typed HIR C++ backend remains the parity oracle.",
            "#include <any>",
            "#include <bit>",
            "#include <cmath>",
            "#include <cstddef>",
            "#include <cstdint>",
            "#include <exception>",
            "#include <functional>",
            "#include <iostream>",
            "#include <limits>",
            "#include <charconv>",
            "#include <memory>",
            "#include <optional>",
            "#include <sstream>",
            "#include <stdexcept>",
            "#include <string>",
            "#include <utility>",
            "#include <vector>",
            "",
            self._runtime(),
            "",
            *self._struct_definitions(),
            "",
            *declarations,
            "",
            *definitions,
            self._entry_point(),
        ]
        return "\n".join(parts).rstrip() + "\n"

    @staticmethod
    def _runtime() -> str:
        return """namespace rove_mir_runtime {
struct user_throw {
    std::string value;
};

template <typename Value>
class task {
    struct state {
        std::function<Value()> run;
        std::optional<Value> value;
        std::exception_ptr error;
        bool done = false;
    };
    std::shared_ptr<state> state_;

public:
    task() : state_(std::make_shared<state>()) {}
    explicit task(std::function<Value()> run) : state_(std::make_shared<state>()) {
        state_->run = std::move(run);
    }

    Value await_result() const {
        if (!state_->done) {
            if (!state_->run) throw std::runtime_error("attempted to await an uninitialized Rove task");
            auto run = std::move(state_->run);
            state_->run = {};
            try {
                state_->value = run();
            } catch (...) {
                state_->error = std::current_exception();
            }
            state_->done = true;
        }
        if (state_->error) std::rethrow_exception(state_->error);
        return *state_->value;
    }
};

template <>
class task<void> {
    struct state {
        std::function<void()> run;
        std::exception_ptr error;
        bool done = false;
    };
    std::shared_ptr<state> state_;

public:
    task() : state_(std::make_shared<state>()) {}
    explicit task(std::function<void()> run) : state_(std::make_shared<state>()) {
        state_->run = std::move(run);
    }

    void await_result() const {
        if (!state_->done) {
            if (!state_->run) throw std::runtime_error("attempted to await an uninitialized Rove task");
            auto run = std::move(state_->run);
            state_->run = {};
            try {
                run();
            } catch (...) {
                state_->error = std::current_exception();
            }
            state_->done = true;
        }
        if (state_->error) std::rethrow_exception(state_->error);
    }
};

inline std::int64_t from_bits(std::uint64_t value) {
    return std::bit_cast<std::int64_t>(value);
}
inline std::uint64_t to_bits(std::int64_t value) {
    return std::bit_cast<std::uint64_t>(value);
}
inline std::int64_t add(std::int64_t left, std::int64_t right) {
    return from_bits(to_bits(left) + to_bits(right));
}
inline std::int64_t sub(std::int64_t left, std::int64_t right) {
    return from_bits(to_bits(left) - to_bits(right));
}
inline std::int64_t mul(std::int64_t left, std::int64_t right) {
    return from_bits(to_bits(left) * to_bits(right));
}
inline std::int64_t neg(std::int64_t value) {
    return from_bits(std::uint64_t{0} - to_bits(value));
}
inline std::int64_t div(std::int64_t left, std::int64_t right) {
    if (right == 0) throw std::runtime_error("division by zero");
    if (left == std::numeric_limits<std::int64_t>::min() && right == -1) return left;
    return left / right;
}
inline std::int64_t rem(std::int64_t left, std::int64_t right) {
    if (right == 0) throw std::runtime_error("remainder by zero");
    if (left == std::numeric_limits<std::int64_t>::min() && right == -1) return 0;
    return left % right;
}
inline std::int64_t shl(std::int64_t left, std::int64_t right) {
    return from_bits(to_bits(left) << (to_bits(right) & 63U));
}
inline std::int64_t shr(std::int64_t left, std::int64_t right) {
    return left >> (to_bits(right) & 63U);
}
template <typename Value>
Value& index(std::vector<Value>& values, std::int64_t position) {
    if (position < 0 || static_cast<std::uint64_t>(position) >= values.size())
        throw std::out_of_range("array index out of bounds");
    return values[static_cast<std::size_t>(position)];
}
template <typename Value>
const Value& index(const std::vector<Value>& values, std::int64_t position) {
    if (position < 0 || static_cast<std::uint64_t>(position) >= values.size())
        throw std::out_of_range("array index out of bounds");
    return values[static_cast<std::size_t>(position)];
}
inline std::string to_string(const std::string& value) { return value; }
inline std::string to_string(bool value) { return value ? "true" : "false"; }

inline std::string rove_f64_to_string(double value) {
    if (std::isnan(value)) return "nan";
    if (std::isinf(value)) return std::signbit(value) ? "-inf" : "inf";
    if (value == 0.0) return "0";
    char buffer[128];
    const auto converted = std::to_chars(
        buffer, buffer + sizeof(buffer), value, std::chars_format::general
    );
    if (converted.ec != std::errc{})
        throw std::runtime_error("Rove float formatting failed");
    std::string text(buffer, converted.ptr);
    const bool negative = text.front() == '-';
    if (negative) text.erase(text.begin());
    const auto marker = text.find_first_of("eE");
    std::string digits = text.substr(0, marker);
    const int exponent = marker == std::string::npos ? 0 : std::stoi(text.substr(marker + 1));
    const auto dot = digits.find('.');
    int decimal = static_cast<int>(dot == std::string::npos ? digits.size() : dot) + exponent;
    if (dot != std::string::npos) digits.erase(dot, 1);
    const auto first = digits.find_first_not_of('0');
    decimal -= static_cast<int>(first);
    digits.erase(0, first);
    while (digits.size() > 1 && digits.back() == '0') digits.pop_back();
    std::string result;
    if (decimal > -6 && decimal <= 21) {
        if (decimal <= 0) {
            result = "0." + std::string(static_cast<std::size_t>(-decimal), '0') + digits;
        } else if (static_cast<std::size_t>(decimal) >= digits.size()) {
            result = digits + std::string(static_cast<std::size_t>(decimal) - digits.size(), '0');
        } else {
            result = digits.substr(0, decimal) + "." + digits.substr(decimal);
        }
    } else {
        result = digits.substr(0, 1);
        if (digits.size() > 1) result += "." + digits.substr(1);
        result += "e";
        if (decimal > 0) result += "+";
        result += std::to_string(decimal - 1);
    }
    return (negative ? "-" : "") + result;
}

inline void rove_print_value(std::ostream& output, double value) {
    output << rove_f64_to_string(value);
}
template <typename Value>
void rove_print_value(std::ostream& output, const Value& value);
template <typename Value>
void rove_print_value(std::ostream& output, const std::vector<Value>& values);
template <typename Value>
void rove_print_value(std::ostream& output, const Value& value) {
    if constexpr (requires { output << value; }) {
        output << value;
    } else {
        throw std::runtime_error("unsupported Rove display value");
    }
}
template <typename Value>
void rove_print_value(std::ostream& output, const std::vector<Value>& values) {
    output << '[';
    for (std::size_t index = 0; index < values.size(); ++index) {
        if (index) output << ", ";
        rove_print_value(output, values[index]);
    }
    output << ']';
}
template <typename Value>
std::string to_string(const Value& value) {
    std::ostringstream stream;
    rove_print_value(stream, value);
    return stream.str();
}
inline void print_one(bool& first, double value) {
    if (!first) std::cout << ' ';
    first = false;
    std::cout << to_string(value);
}
template <typename Value>
void print_one(bool& first, const Value& value) {
    if (!first) std::cout << ' ';
    first = false;
    rove_print_value(std::cout, value);
}
template <typename... Values>
void print(const Values&... values) {
    bool first = true;
    std::cout << std::boolalpha;
    (print_one(first, values), ...);
    std::cout << '\\n';
}
}  // namespace rove_mir_runtime"""

    def _struct_definitions(self) -> list[str]:
        definitions: list[str] = [
            "struct rove_tagged_value {\n"
            "    std::string type_name;\n"
            "    std::string tag;\n"
            "    std::vector<std::any> payload;\n"
            "};",
            "std::ostream& operator<<(std::ostream& output, const rove_tagged_value& value);",
        ]
        for definition in self.enums.values():
            definitions.append(
                f"using rove_type_{_identifier(definition.name)} = rove_tagged_value;"
            )
        for definition in self.structs.values():
            lines = [f"struct rove_type_{_identifier(definition.name)} {{"]
            for field in definition.fields:
                lines.append(f"    {self._type(field.type)} {_identifier(field.name)}{{}};")
            lines.append("};")
            definitions.append("\n".join(lines))
        for definition in self.structs.values():
            name = f"rove_type_{_identifier(definition.name)}"
            definitions.append(
                f"std::ostream& operator<<(std::ostream& output, const {name}& value);"
            )
        for definition in self.structs.values():
            name = f"rove_type_{_identifier(definition.name)}"
            lines = [
                f"inline std::ostream& operator<<(std::ostream& output, const {name}& value) {{",
                f"    output << {json.dumps(definition.name + '(')};",
            ]
            for index, field in enumerate(definition.fields):
                if index:
                    lines.append('    output << ", ";')
                lines.append(
                    f"    rove_mir_runtime::rove_print_value(output, value.{_identifier(field.name)});"
                )
            lines.extend(("    return output << ')';", "}"))
            definitions.append("\n".join(lines))
        payload_types = [
            "std::int64_t", "double", "bool", "std::string", "rove_tagged_value",
            *(f"rove_type_{_identifier(name)}" for name in self.structs),
            *(self._type(value) for value in self._display_array_types()),
        ]
        payload_lines = [
            "inline void rove_print_payload(std::ostream& output, const std::any& item) {"
        ]
        for value_type in dict.fromkeys(payload_types):
            payload_lines.extend((
                f"    if (item.type() == typeid({value_type})) {{",
                "        rove_mir_runtime::rove_print_value("
                f"output, std::any_cast<const {value_type}&>(item));",
                "        return;",
                "    }",
            ))
        payload_lines.extend((
            '    throw std::runtime_error("unsupported Rove tagged display payload");',
            "}",
        ))
        definitions.append("\n".join(payload_lines))
        definitions.append(
            "inline std::ostream& operator<<(std::ostream& output, const rove_tagged_value& value) {\n"
            "    output << value.tag << '(';\n"
            "    for (std::size_t index = 0; index < value.payload.size(); ++index) {\n"
            "        if (index) output << \", \";\n"
            "        rove_print_payload(output, value.payload[index]);\n"
            "    }\n"
            "    return output << ')';\n"
            "}"
        )
        return definitions

    def _display_array_types(self) -> tuple[MIRType, ...]:
        found: dict[str, MIRType] = {}

        def visit(value_type: MIRType) -> None:
            key = value_type.canonical()
            if key in found:
                return
            found[key] = value_type
            for argument in value_type.arguments:
                visit(argument)

        for definition in self.module.type_definitions:
            if isinstance(definition, MIRStructDef):
                for field in definition.fields:
                    visit(field.type)
            elif isinstance(definition, MIREnumDef):
                for variant in definition.variants:
                    for payload in variant.payload_types:
                        visit(payload)
        for function in self.module.functions:
            for local in function.locals:
                visit(local.type)
        return tuple(
            found[key] for key in sorted(found)
            if found[key].name == "Array" and len(found[key].arguments) == 1
        )

    def _entry_point(self) -> str:
        by_name = {function.name: function for function in self.module.functions}
        entry = by_name.get("main") or by_name.get("__nyx_top_level")
        if entry is None:
            return "int main() { return 0; }"
        if entry.is_async:
            return f"int main() {{ {self.function_names[entry.symbol]}().await_result(); return 0; }}"
        return f"int main() {{ {self.function_names[entry.symbol]}(); return 0; }}"

    def _prototype(self, function: MIRFunction) -> str:
        name = self.function_names[function.symbol]
        parameters = ", ".join(
            f"{self._type(function.locals[local].type)} _{local}"
            for local in function.parameters
        )
        return_type = function.locals[function.return_local].type
        rendered_return = "void" if function.name == "main" and return_type.name == "any" else self._type(return_type)
        if function.is_async:
            rendered_return = f"rove_mir_runtime::task<{rendered_return}>"
        return f"static {rendered_return} {name}({parameters})"

    def _function(self, function: MIRFunction) -> str:
        self.current = function
        self.local_types = {local.id: local.type for local in function.locals}
        signature = self._prototype(function) + " {"
        lines: list[str] = []
        parameter_ids = set(function.parameters)
        for local in function.locals:
            if local.id in parameter_ids or local.type.name in ("void", "any"):
                continue
            if function.name == "main" and local.id == function.return_local and local.type.name == "any":
                continue
            lines.append(f"    {self._type(local.type)} _{local.id}{{}};")
        if function.blocks:
            lines.append("    goto bb0;")
        for block in function.blocks:
            lines.append(f"bb{block.id}:")
            for statement in block.statements:
                lines.extend(self._statement(statement))
            lines.extend(self._terminator(block.terminator))
        if function.is_async:
            return_type = function.locals[function.return_local].type
            body_return = "void" if function.name == "main" and return_type.name == "any" else self._type(return_type)
            rendered_lines = [
                signature,
                f"    return rove_mir_runtime::task<{body_return}>([=]() mutable -> {body_return} {{",
            ]
            rendered_lines.extend(f"    {line}" for line in lines)
            rendered_lines.extend(("    });", "}"))
        else:
            rendered_lines = [signature, *lines, "}"]
        self.current = None
        self.local_types = {}
        return "\n".join(rendered_lines)

    def _statement(self, statement: object) -> list[str]:
        if isinstance(statement, AssignStatement):
            destination_type = self._place_type(statement.place)
            if destination_type.name == "void":
                return []
            if self.current is not None and self.current.name == "main" and statement.place.local == 0:
                raise MIRCodegenError("MIR main may not assign its synthetic 'any' return local")
            return [f"    {self._place(statement.place)} = {self._rvalue(statement.value)};"]
        if isinstance(statement, (StorageLiveStatement, StorageDeadStatement, NopStatement)):
            return []
        if isinstance(statement, (RetainStatement, ReleaseStatement)):
            # C++ RAII performs retain/release through value copy/move and destruction.
            return []
        if isinstance(statement, DeinitStatement):
            return [f"    {self._place(statement.place)} = {{}};"]
        raise MIRCodegenError(f"illegal statement reached C++ emitter: {type(statement).__name__}")

    def _terminator(self, terminator: object) -> list[str]:
        if isinstance(terminator, GotoTerminator):
            return [f"    goto bb{terminator.target};"]
        if isinstance(terminator, SwitchIntTerminator):
            discriminator = self._operand(terminator.discriminator)
            lines: list[str] = []
            for index, (value, target) in enumerate(terminator.targets):
                prefix = "if" if index == 0 else "else if"
                lines.append(f"    {prefix} ({discriminator} == {self._constant(value)}) goto bb{target};")
            lines.append(f"    else goto bb{terminator.otherwise};" if terminator.targets else f"    goto bb{terminator.otherwise};")
            return lines
        if isinstance(terminator, SwitchValueTerminator):
            discriminator = self._operand(terminator.discriminator)
            discriminator_type = self._operand_type(terminator.discriminator)
            lines = []
            for index, (value, target) in enumerate(terminator.targets):
                prefix = "if" if index == 0 else "else if"
                if value is None and discriminator_type.optional:
                    condition = f"!({discriminator}).has_value()"
                elif discriminator_type.optional:
                    condition = f"({discriminator}).has_value() && ({discriminator}).value() == {self._constant(value)}"
                else:
                    condition = f"{discriminator} == {self._constant(value)}"
                lines.append(f"    {prefix} ({condition}) goto bb{target};")
            lines.append(f"    else goto bb{terminator.otherwise};" if terminator.targets else f"    goto bb{terminator.otherwise};")
            return lines
        if isinstance(terminator, CallTerminator):
            if terminator.target is None:
                raise MIRCodegenError(f"call '{terminator.function}' has no continuation")
            arguments = ", ".join(self._operand(argument) for argument in terminator.arguments)
            if terminator.function == "builtin::print":
                lines = [f"    rove_mir_runtime::print({arguments});"]
            elif terminator.function == "builtin::len":
                if len(terminator.arguments) != 1 or terminator.destination is None:
                    raise MIRCodegenError("builtin::len requires one argument and a destination")
                lines = [
                    f"    {self._place(terminator.destination)} = "
                    f"static_cast<std::int64_t>({self._operand(terminator.arguments[0])}.size());"
                ]
            elif terminator.function == "builtin::to_string":
                if len(terminator.arguments) != 1 or terminator.destination is None:
                    raise MIRCodegenError("builtin::to_string requires one argument and a destination")
                lines = [
                    f"    {self._place(terminator.destination)} = "
                    f"rove_mir_runtime::to_string({self._operand(terminator.arguments[0])});"
                ]
            elif terminator.function in self.function_names:
                call = f"{self.function_names[terminator.function]}({arguments})"
                callee = next(
                    function for function in self.module.functions
                    if function.symbol == terminator.function
                )
                callee_result = callee.locals[callee.return_local].type
                if (
                    terminator.destination is None
                    or self.local_types[terminator.destination.local].name in ("void", "any")
                    or callee_result.name in ("void", "any")
                ):
                    lines = [f"    {call};"]
                else:
                    lines = [f"    {self._place(terminator.destination)} = {call};"]
            else:
                raise MIRCodegenError(f"illegal runtime call reached C++ emitter: {terminator.function}")
            if terminator.unwind is not None:
                if terminator.error_destination is None:
                    raise MIRCodegenError("C++ MIR call unwind requires an error destination")
                wrapped = ["    try {"]
                wrapped.extend(f"    {line}" for line in lines)
                wrapped.extend((
                    "    } catch (const rove_mir_runtime::user_throw& thrown) {",
                    f"        {self._place(terminator.error_destination)} = thrown.value;",
                    f"        goto bb{terminator.unwind};",
                    "    }",
                    f"    goto bb{terminator.target};",
                ))
                return wrapped
            lines.append(f"    goto bb{terminator.target};")
            return lines
        if isinstance(terminator, SuspendTerminator):
            task = self._operand(terminator.task)
            destination_type = self._place_type(terminator.destination)
            awaited = f"{task}.await_result()"
            assignment = (
                f"    {awaited};"
                if destination_type.name in ("void", "any")
                else f"    {self._place(terminator.destination)} = {awaited};"
            )
            lines = [assignment]
            if terminator.unwind is not None:
                if terminator.error_destination is None:
                    raise MIRCodegenError("C++ MIR suspend unwind requires an error destination")
                lines = ["    try {", f"    {assignment}",
                         "    } catch (const rove_mir_runtime::user_throw& thrown) {",
                         f"        {self._place(terminator.error_destination)} = thrown.value;",
                         f"        goto bb{terminator.unwind};", "    }"]
            lines.append(f"    goto bb{terminator.resume};")
            return lines
        if isinstance(terminator, AssertTerminator):
            expected = "true" if terminator.expected else "false"
            message = json.dumps(terminator.message, ensure_ascii=False)
            return [
                f"    if (static_cast<bool>({self._operand(terminator.condition)}) != {expected}) ",
                f"        throw std::runtime_error({message});",
                f"    goto bb{terminator.target};",
            ]
        if isinstance(terminator, ThrowTerminator):
            thrown = self._operand(terminator.value)
            if terminator.target is not None and terminator.destination is not None:
                return [
                    f"    {self._place(terminator.destination)} = {thrown};",
                    f"    goto bb{terminator.target};",
                ]
            return [
                f"    throw rove_mir_runtime::user_throw{{rove_mir_runtime::to_string({thrown})}};"
            ]
        if isinstance(terminator, DropTerminator):
            if terminator.unwind is not None:
                raise MIRCodegenError("C++ MIR drop unwind edge was not legalized")
            return [
                f"    {self._place(terminator.place)} = {{}};",
                f"    goto bb{terminator.target};",
            ]
        if isinstance(terminator, ReturnTerminator):
            assert self.current is not None
            if self.current.name == "main" and self.local_types[self.current.return_local].name == "any":
                return ["    return;"]
            result_type = self.local_types[self.current.return_local]
            if result_type.name == "void":
                return ["    return;"]
            return [f"    return _{self.current.return_local};"]
        if isinstance(terminator, UnreachableTerminator):
            return ["    throw std::runtime_error(\"reached unreachable MIR terminator\");"]
        raise MIRCodegenError(f"illegal terminator reached C++ emitter: {type(terminator).__name__}")

    def _rvalue(self, value: object) -> str:
        if isinstance(value, UseRValue):
            return self._operand(value.operand)
        if isinstance(value, BinaryRValue):
            return self._binary(value)
        if isinstance(value, UnaryRValue):
            operand = self._operand(value.operand)
            if value.op in ("!", "not"):
                return f"(!static_cast<bool>({operand}))"
            if value.op == "-" and value.type.name in _INTEGER_TYPES:
                return f"rove_mir_runtime::neg({operand})"
            if value.op in ("+", "-"):
                return f"({value.op}{operand})"
            if value.op == "~":
                return f"rove_mir_runtime::from_bits(~rove_mir_runtime::to_bits({operand}))"
            raise MIRCodegenError(f"unsupported unary operation '{value.op}'")
        if isinstance(value, CastRValue):
            operand = self._operand(value.operand)
            if value.kind == "optional-unwrap":
                return f"({operand}).value()"
            if value.type.optional:
                return f"{self._type(value.type)}{{{operand}}}"
            return f"static_cast<{self._type(value.type)}>({operand})"
        if isinstance(value, AggregateRValue):
            operands = ", ".join(self._operand(operand) for operand in value.operands)
            if value.kind == "array":
                return f"{self._type(value.type)}{{{operands}}}"
            if value.kind == "struct":
                return f"{self._type(value.type)}{{{operands}}}"
            if value.kind in ("enum", "option", "result"):
                payload = ", ".join(
                    f"std::any({self._operand(operand)})" for operand in value.operands
                )
                return (
                    f"{self._type(value.type)}{{{json.dumps(value.type.name)}, "
                    f"{json.dumps(value.name)}, std::vector<std::any>{{{payload}}}}}"
                )
            raise MIRCodegenError(f"unsupported C++ aggregate kind '{value.kind}'")
        if isinstance(value, DiscriminantRValue):
            return f"({self._operand(value.operand)}).tag"
        if isinstance(value, PayloadRValue):
            return (
                f"std::any_cast<{self._type(value.type)}>("
                f"({self._operand(value.operand)}).payload.at({value.index}))"
            )
        if isinstance(value, BorrowRValue):
            return f"&({self._place(value.place)})"
        raise MIRCodegenError(f"illegal rvalue reached C++ emitter: {type(value).__name__}")

    def _binary(self, value: BinaryRValue) -> str:
        left = self._operand(value.left)
        right = self._operand(value.right)
        left_type = self._operand_type(value.left)
        right_type = self._operand_type(value.right)
        if value.op in ("==", "!=", "<", "<=", ">", ">="):
            return f"({left} {value.op} {right})"
        if value.op in ("+", "-", "*", "/", "%") and (
            left_type.name in _FLOAT_TYPES or right_type.name in _FLOAT_TYPES
        ):
            if value.op == "%":
                return f"std::fmod({left}, {right})"
            return f"({left} {value.op} {right})"
        if value.op == "+" and (left_type.name == "string" or right_type.name == "string"):
            return f"({left} + {right})"
        runtime_ops = {
            "+": "add", "-": "sub", "*": "mul", "/": "div", "%": "rem",
            "<<": "shl", ">>": "shr",
        }
        if value.op in runtime_ops:
            return f"rove_mir_runtime::{runtime_ops[value.op]}({left}, {right})"
        if value.op in ("&", "|", "^"):
            return (
                "rove_mir_runtime::from_bits("
                f"rove_mir_runtime::to_bits({left}) {value.op} rove_mir_runtime::to_bits({right}))"
            )
        raise MIRCodegenError(f"unsupported binary operation '{value.op}'")

    def _operand(self, operand: Operand) -> str:
        if isinstance(operand, ConstOperand):
            return self._typed_constant(operand)
        if isinstance(operand, (CopyOperand, MoveOperand)):
            rendered = self._place(operand.place)
            return f"std::move({rendered})" if isinstance(operand, MoveOperand) else rendered
        raise MIRCodegenError(f"illegal operand reached C++ emitter: {type(operand).__name__}")

    def _operand_type(self, operand: Operand) -> MIRType:
        if isinstance(operand, ConstOperand):
            return operand.type
        if isinstance(operand, (CopyOperand, MoveOperand)):
            return self._place_type(operand.place)
        raise MIRCodegenError(f"unknown operand type: {type(operand).__name__}")

    def _place(self, place: Place) -> str:
        rendered = f"_{place.local}"
        value_type = self.local_types[place.local]
        for projection in place.projections:
            if value_type.optional:
                rendered = f"({rendered}).value()"
                value_type = replace(value_type, optional=False)
            if isinstance(projection, FieldProjection):
                rendered = f"({rendered}).{_identifier(projection.name)}"
                value_type = self._field_type(value_type, projection.name)
            elif isinstance(projection, ConstantIndexProjection):
                rendered = f"rove_mir_runtime::index({rendered}, {projection.index})"
                value_type = self._index_type(value_type)
            elif isinstance(projection, IndexProjection):
                rendered = f"rove_mir_runtime::index({rendered}, _{projection.local})"
                value_type = self._index_type(value_type)
            elif isinstance(projection, DerefProjection):
                if not value_type.pointer:
                    raise MIRCodegenError(f"dereference requires a pointer, got '{value_type}'")
                rendered = f"(*{rendered})"
                value_type = replace(value_type, pointer=False)
            else:
                raise MIRCodegenError(f"illegal projection reached C++ emitter: {type(projection).__name__}")
        return rendered

    def _place_type(self, place: Place) -> MIRType:
        value_type = self.local_types[place.local]
        for projection in place.projections:
            if value_type.optional:
                value_type = replace(value_type, optional=False)
            if isinstance(projection, FieldProjection):
                value_type = self._field_type(value_type, projection.name)
            elif isinstance(projection, (ConstantIndexProjection, IndexProjection)):
                value_type = self._index_type(value_type)
            elif isinstance(projection, DerefProjection):
                if not value_type.pointer:
                    raise MIRCodegenError(f"dereference requires a pointer, got '{value_type}'")
                value_type = replace(value_type, pointer=False)
            else:
                raise MIRCodegenError(f"unknown projected place type: {type(projection).__name__}")
        return value_type

    def _field_type(self, value_type: MIRType, name: str) -> MIRType:
        definition = self.structs.get(value_type.name)
        if definition is None:
            raise MIRCodegenError(f"field projection requires a known struct, got '{value_type}'")
        for field in definition.fields:
            if field.name == name:
                return field.type
        raise MIRCodegenError(f"struct '{value_type.name}' has no field '{name}'")

    @staticmethod
    def _index_type(value_type: MIRType) -> MIRType:
        if value_type.name == "Array" and len(value_type.arguments) == 1:
            return value_type.arguments[0]
        raise MIRCodegenError(f"index projection requires Array<T>, got '{value_type}'")

    def _typed_constant(self, operand: ConstOperand) -> str:
        value = operand.value
        if operand.type.optional and value is None:
            return "std::nullopt"
        if operand.type.name in _INTEGER_TYPES:
            bits = int(value) & ((1 << 64) - 1)
            return f"rove_mir_runtime::from_bits(UINT64_C({bits}))"
        if operand.type.name in _FLOAT_TYPES:
            number = float(value)
            if math.isnan(number):
                return "std::numeric_limits<double>::quiet_NaN()"
            if math.isinf(number):
                sign = "" if number > 0 else "-"
                return f"{sign}std::numeric_limits<double>::infinity()"
            return repr(number)
        if operand.type.name == "bool":
            return "true" if bool(value) else "false"
        if operand.type.name == "string":
            return f"std::string({json.dumps(str(value), ensure_ascii=False)})"
        if operand.type.name == "char":
            return f"U{json.dumps(str(value), ensure_ascii=False)}"
        raise MIRCodegenError(f"unsupported constant type '{operand.type}'")

    @staticmethod
    def _constant(value: object) -> str:
        if value is None:
            return "std::nullopt"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            return repr(value)
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        raise MIRCodegenError(f"unsupported switch constant {value!r}")

    @staticmethod
    def _type(value: MIRType) -> str:
        if value.pointer:
            return f"{_CppEmitter._type(replace(value, pointer=False))}*"
        if value.optional:
            return f"std::optional<{_CppEmitter._type(replace(value, optional=False))}>"
        if value.name == "Array" and len(value.arguments) == 1:
            return f"std::vector<{_CppEmitter._type(value.arguments[0])}>"
        if value.name == "Task" and len(value.arguments) == 1:
            return f"rove_mir_runtime::task<{_CppEmitter._type(value.arguments[0])}>"
        if value.name in ("Option", "Result") and value.arguments:
            return "rove_tagged_value"
        if value.name == "void":
            return "void"
        if value.name == "bool":
            return "bool"
        if value.name in _INTEGER_TYPES:
            return "std::int64_t"
        if value.name in _FLOAT_TYPES:
            return "double"
        if value.name == "string":
            return "std::string"
        if value.name == "char":
            return "char32_t"
        if value.name and not value.arguments and not value.pointer and not value.is_function:
            return f"rove_type_{_identifier(value.name)}"
        raise MIRCodegenError(f"unsupported C++ MIR type '{value}'")


def emit_legalized_cpp(module: MIRModule) -> str:
    """Validate and emit the M5 C++ pilot without semantic fallback."""
    try:
        legalized = legalize_mir(module, "cpp", require_emitter=True)
    except MIRLegalizationError:
        raise
    return _CppEmitter(legalized).emit()
