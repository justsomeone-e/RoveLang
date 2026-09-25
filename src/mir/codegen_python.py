"""Python 3 emitter for legalized scalar/control-flow MIR."""

from __future__ import annotations

import json
import keyword
import math
import re
from dataclasses import replace

from .codegen_cpp import MIRCodegenError
from .legalization import legalize_mir
from .model import (
    AggregateRValue, AssertTerminator, AssignStatement, BinaryRValue, CallTerminator,
    CastRValue, ConstOperand, ConstantIndexProjection, CopyOperand, DeinitStatement, DiscriminantRValue, FieldProjection,
    DropTerminator, GotoTerminator, IndexProjection, MIRFunction, MIRModule, MIRStructDef,
    MoveOperand, NopStatement, Operand, PayloadRValue, Place, ReturnTerminator,
    StorageDeadStatement, StorageLiveStatement, SuspendTerminator, SwitchIntTerminator,
    SwitchValueTerminator, ThrowTerminator, UnaryRValue, UnreachableTerminator, UseRValue,
)
from .types import MIRType


_RUNTIME = r'''import copy
import math
import sys

ROVE_I64_MASK = (1 << 64) - 1
ROVE_I64_SIGN = 1 << 63

class RoveUserThrow(Exception):
    def __init__(self, value):
        super().__init__(value)
        self.value = value

class RoveTask:
    def __init__(self, run):
        self.run = run
        self.done = False
        self.value = None
        self.error = None

    def __deepcopy__(self, memo):
        return self

    def await_result(self):
        if not self.done:
            run = self.run
            self.run = None
            if run is None:
                raise RuntimeError("attempted to await an uninitialized Rove task")
            try:
                self.value = run()
            except BaseException as error:
                self.error = error
            self.done = True
        if self.error is not None:
            raise self.error
        return rove_clone(self.value)

def rove_i64(value):
    value = int(value) & ROVE_I64_MASK
    return value - (1 << 64) if value & ROVE_I64_SIGN else value

def rove_i64_div(left, right):
    if right == 0:
        raise RuntimeError("division by zero")
    quotient = abs(left) // abs(right)
    if (left < 0) != (right < 0):
        quotient = -quotient
    return rove_i64(quotient)

def rove_i64_rem(left, right):
    if right == 0:
        raise RuntimeError("remainder by zero")
    return rove_i64(left - rove_i64_div(left, right) * right)

def rove_f64_div(left, right):
    left = float(left)
    right = float(right)
    if right != 0.0:
        return left / right
    if left == 0.0 or math.isnan(left):
        return math.nan
    negative = math.copysign(1.0, left) != math.copysign(1.0, right)
    return -math.inf if negative else math.inf

def rove_f64_rem(left, right):
    try:
        return math.fmod(float(left), float(right))
    except ValueError:
        return math.nan

def rove_clone(value):
    return copy.deepcopy(value)

def rove_index(value, index):
    position = int(index)
    if position < 0 or position >= len(value):
        raise IndexError(f"index {position} out of bounds for length {len(value)}")
    return value[position]

def rove_set_index(value, index, item):
    position = int(index)
    if position < 0 or position >= len(value):
        raise IndexError(f"index {position} out of bounds for length {len(value)}")
    value[position] = item

def rove_field(value, name):
    return value["fields"][name]

def rove_set_field(value, name, item):
    value["fields"][name] = item

def rove_f64_to_string(value):
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "-inf" if value < 0 else "inf"
    if value == 0.0:
        return "0"
    text = repr(value)
    negative = text.startswith("-")
    if negative:
        text = text[1:]
    mantissa, marker, exponent_text = text.partition("e")
    exponent = int(exponent_text) if marker else 0
    dot = mantissa.find(".")
    decimal = (len(mantissa) if dot < 0 else dot) + exponent
    digits = mantissa.replace(".", "")
    first = len(digits) - len(digits.lstrip("0"))
    decimal -= first
    digits = digits[first:].rstrip("0")
    if -6 < decimal <= 21:
        if decimal <= 0:
            result = "0." + "0" * -decimal + digits
        elif decimal >= len(digits):
            result = digits + "0" * (decimal - len(digits))
        else:
            result = digits[:decimal] + "." + digits[decimal:]
    else:
        result = digits[0] + ("." + digits[1:] if len(digits) > 1 else "")
        result += "e" + ("+" if decimal > 0 else "") + str(decimal - 1)
    return ("-" if negative else "") + result

def rove_display(value):
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, dict) and isinstance(value.get("tag"), str) and isinstance(value.get("payload"), list):
        payload = ", ".join(rove_display(item) for item in value["payload"])
        return f'{value["tag"]}({payload})'
    if isinstance(value, list):
        return "[" + ", ".join(rove_display(item) for item in value) + "]"
    if isinstance(value, dict) and "__type__" in value and "fields" in value:
        fields = ", ".join(rove_display(item) for item in value["fields"].values())
        return f'{value["__type__"]}({fields})'
    if isinstance(value, float):
        return rove_f64_to_string(value)
    return str(value)'''


def _identifier(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not clean or clean[0].isdigit() or keyword.iskeyword(clean):
        clean = "_" + clean
    return clean


class _PythonEmitter:
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
        self.current: MIRFunction | None = None
        self.local_types: dict[int, MIRType] = {}

    def emit(self) -> str:
        parts = ["# Experimental Rove legalized MIR -> Python 3 output.", _RUNTIME, ""]
        parts.extend(self._function(function) + "\n" for function in self.module.functions)
        by_name = {function.name: function for function in self.module.functions}
        entry = by_name.get("main") or by_name.get("__nyx_top_level")
        if entry is not None:
            parts.append("if __name__ == \"__main__\":")
            if entry.is_async:
                parts.extend((
                    "    try:",
                    f"        {self.function_names[entry.symbol]}().await_result()",
                    "    except RoveUserThrow as error:",
                    "        print(error.value, file=sys.stderr)",
                    "        raise SystemExit(1)",
                ))
            else:
                parts.append(f"    {self.function_names[entry.symbol]}()")
        return "\n".join(parts).rstrip() + "\n"

    def _function(self, function: MIRFunction) -> str:
        self.current = function
        self.local_types = {local.id: local.type for local in function.locals}
        parameters = ", ".join(f"l{local}" for local in function.parameters)
        signature = f"def {self.function_names[function.symbol]}({parameters}):"
        lines: list[str] = []
        parameter_ids = set(function.parameters)
        for local in function.locals:
            if local.id in parameter_ids or local.type.name in ("void", "any"):
                continue
            lines.append(f"    l{local.id} = {self._default(local.type)}")
        lines.extend(("    pc = 0", "    while True:"))
        for index, block in enumerate(function.blocks):
            branch = "if" if index == 0 else "elif"
            lines.append(f"        {branch} pc == {block.id}:")
            body: list[str] = []
            for statement in block.statements:
                body.extend(self._statement(statement))
            body.extend(self._terminator(block.terminator))
            lines.extend(f"            {line}" for line in (body or ["pass"]))
        lines.extend(("        else:", "            raise RuntimeError(\"invalid MIR block\")"))
        if function.is_async:
            rendered_lines = [signature, "    def rove_run():"]
            rendered_lines.extend(f"    {line}" for line in lines)
            rendered_lines.append("    return RoveTask(rove_run)")
        else:
            rendered_lines = [signature, *lines]
        self.current = None
        self.local_types = {}
        return "\n".join(rendered_lines)

    def _statement(self, value: object) -> list[str]:
        if isinstance(value, AssignStatement):
            if self._place_type(value.place).name in ("void", "any"):
                return []
            return [self._assign_place(value.place, self._rvalue(value.value))]
        if isinstance(value, (StorageLiveStatement, StorageDeadStatement, NopStatement)):
            return []
        if isinstance(value, DeinitStatement):
            return [self._assign_place(value.place, "None")]
        raise MIRCodegenError(f"illegal statement reached Python emitter: {type(value).__name__}")

    def _terminator(self, value: object) -> list[str]:
        if isinstance(value, GotoTerminator):
            return self._goto(value.target)
        if isinstance(value, SwitchIntTerminator):
            discriminator = self._operand(value.discriminator)
            discriminator_type = self._operand_type(value.discriminator)
            lines: list[str] = []
            for expected, target in value.targets:
                rendered = self._bool(bool(expected)) if discriminator_type.name == "bool" else str(expected)
                lines.append(f"if {discriminator} == {rendered}:")
                lines.extend(f"    {line}" for line in self._goto(target))
            lines.extend(self._goto(value.otherwise))
            return lines
        if isinstance(value, SwitchValueTerminator):
            discriminator = self._operand(value.discriminator)
            lines = []
            for expected, target in value.targets:
                lines.append(f"if {discriminator} == {self._constant(expected)}:")
                lines.extend(f"    {line}" for line in self._goto(target))
            lines.extend(self._goto(value.otherwise))
            return lines
        if isinstance(value, CallTerminator):
            if value.target is None:
                raise MIRCodegenError(f"call '{value.function}' has no continuation")
            arguments = ", ".join(self._operand(argument) for argument in value.arguments)
            if value.function == "builtin::print":
                displays = ", ".join(
                    f"rove_display({self._operand(argument)})" for argument in value.arguments
                )
                line = f"print({displays})" if displays else "print()"
            elif value.function == "builtin::len":
                if len(value.arguments) != 1 or value.destination is None:
                    raise MIRCodegenError("builtin::len requires one argument and a destination")
                line = f"{self._place(value.destination)} = rove_i64(len({self._operand(value.arguments[0])}))"
            elif value.function == "builtin::to_string":
                if len(value.arguments) != 1 or value.destination is None:
                    raise MIRCodegenError("builtin::to_string requires one argument and a destination")
                line = f"{self._place(value.destination)} = rove_display({self._operand(value.arguments[0])})"
            elif value.function in self.function_names:
                call = f"{self.function_names[value.function]}({arguments})"
                callee = self.functions[value.function]
                result = callee.locals[callee.return_local].type
                if value.destination is not None and result.name not in ("void", "any"):
                    line = f"l{value.destination.local} = {call}"
                else:
                    line = call
            else:
                raise MIRCodegenError(f"illegal runtime call reached Python emitter: {value.function}")
            if value.unwind is not None:
                if value.error_destination is None:
                    raise MIRCodegenError("Python MIR call unwind requires an error destination")
                return [
                    "try:",
                    f"    {line}",
                    "except RoveUserThrow as error:",
                    f"    {self._place(value.error_destination)} = error.value",
                    f"    pc = {value.unwind}",
                    "    continue",
                ] + self._goto(value.target)
            return [line] + self._goto(value.target)
        if isinstance(value, SuspendTerminator):
            task = self._operand(value.task)
            lines = ["try:", f"    {self._assign_place(value.destination, f'{task}.await_result()')}"]
            if value.unwind is not None:
                if value.error_destination is None:
                    raise MIRCodegenError("Python MIR suspend unwind requires an error destination")
                lines.extend((
                    "except RoveUserThrow as error:",
                    f"    {self._assign_place(value.error_destination, 'error.value')}",
                    f"    pc = {value.unwind}",
                    "    continue",
                ))
            else:
                lines.extend(("except RoveUserThrow:", "    raise"))
            lines.extend(self._goto(value.resume))
            return lines
        if isinstance(value, AssertTerminator):
            expected = self._bool(value.expected)
            return [
                f"if bool({self._operand(value.condition)}) is not {expected}:",
                f"    raise RuntimeError({json.dumps(value.message, ensure_ascii=False)})",
            ] + self._goto(value.target)
        if isinstance(value, DropTerminator):
            if value.unwind is not None:
                raise MIRCodegenError("Python MIR drop unwind edge was not legalized")
            return [self._assign_place(value.place, "None")] + self._goto(value.target)
        if isinstance(value, ThrowTerminator):
            rendered = self._operand(value.value)
            if value.target is not None and value.destination is not None:
                return [self._assign_place(value.destination, f"rove_display({rendered})")] + self._goto(
                    value.target
                )
            return [f"raise RoveUserThrow(rove_display({rendered}))"]
        if isinstance(value, ReturnTerminator):
            assert self.current is not None
            result = self.current.locals[self.current.return_local].type
            return ["return"] if result.name in ("void", "any") else ["return l0"]
        if isinstance(value, UnreachableTerminator):
            return ["raise RuntimeError(\"reached unreachable MIR terminator\")"]
        raise MIRCodegenError(f"illegal terminator reached Python emitter: {type(value).__name__}")

    @staticmethod
    def _goto(target: int) -> list[str]:
        return [f"pc = {target}", "continue"]

    def _rvalue(self, value: object) -> str:
        if isinstance(value, UseRValue):
            return self._operand(value.operand)
        if isinstance(value, BinaryRValue):
            return self._binary(value)
        if isinstance(value, CastRValue):
            operand = self._operand(value.operand)
            if value.kind == "optional-unwrap" or value.type.optional:
                return operand
            if value.type.name == "int":
                return f"rove_i64({operand})"
            if value.type.name in ("float", "f64"):
                return f"float({operand})"
            if value.type.name == "bool":
                return f"bool({operand})"
            if value.type.name == "string":
                return f"rove_display({operand})"
            return operand
        if isinstance(value, AggregateRValue):
            operands = [self._operand(operand) for operand in value.operands]
            if value.kind == "array":
                return "[" + ", ".join(operands) + "]"
            if value.kind == "struct":
                fields = value.fields or tuple(str(index) for index in range(len(operands)))
                body = ", ".join(f"{name!r}: {operand}" for name, operand in zip(fields, operands))
                return f"{{'__type__': {value.name!r}, 'fields': {{{body}}}}}"
            if value.kind in ("enum", "option", "result"):
                return (
                    f"{{'__type__': {value.type.name!r}, 'tag': {value.name!r}, "
                    f"'payload': [{', '.join(operands)}]}}"
                )
            raise MIRCodegenError(f"unsupported Python aggregate kind '{value.kind}'")
        if isinstance(value, DiscriminantRValue):
            return f"({self._operand(value.operand)})['tag']"
        if isinstance(value, PayloadRValue):
            return f"rove_index(({self._operand(value.operand)})['payload'], {value.index})"
        if isinstance(value, UnaryRValue):
            operand = self._operand(value.operand)
            if value.op in ("!", "not"):
                return f"not bool({operand})"
            if value.op == "+":
                return operand
            if value.op == "-" and value.type.name == "int":
                return f"rove_i64(-({operand}))"
            if value.op == "-":
                return f"-({operand})"
            if value.op == "~":
                return f"rove_i64(~({operand}))"
            raise MIRCodegenError(f"unsupported Python unary operation '{value.op}'")
        raise MIRCodegenError(f"illegal rvalue reached Python emitter: {type(value).__name__}")

    def _binary(self, value: BinaryRValue) -> str:
        left = self._operand(value.left)
        right = self._operand(value.right)
        left_type = self._operand_type(value.left)
        right_type = self._operand_type(value.right)
        if value.op in ("==", "!=", "<", "<=", ">", ">="):
            return f"({left} {value.op} {right})"
        if value.op == "+" and (left_type.name == "string" or right_type.name == "string"):
            return f"rove_display({left}) + rove_display({right})"
        if left_type.name in ("float", "f64") or right_type.name in ("float", "f64"):
            if value.op in ("+", "-", "*"):
                return f"({left} {value.op} {right})"
            if value.op == "/":
                return f"rove_f64_div({left}, {right})"
            if value.op == "%":
                return f"rove_f64_rem({left}, {right})"
        if value.op in ("+", "-", "*", "&", "|", "^"):
            return f"rove_i64(({left}) {value.op} ({right}))"
        if value.op == "/":
            return f"rove_i64_div({left}, {right})"
        if value.op == "%":
            return f"rove_i64_rem({left}, {right})"
        if value.op == "<<":
            return f"rove_i64(({left}) << (({right}) & 63))"
        if value.op == ">>":
            return f"rove_i64(({left}) >> (({right}) & 63))"
        raise MIRCodegenError(f"unsupported Python binary operation '{value.op}'")

    def _operand(self, value: Operand) -> str:
        if isinstance(value, ConstOperand):
            return self._typed_constant(value)
        if isinstance(value, (CopyOperand, MoveOperand)):
            rendered = self._place(value.place)
            return f"rove_clone({rendered})" if isinstance(value, CopyOperand) else rendered
        raise MIRCodegenError(f"illegal operand reached Python emitter: {type(value).__name__}")

    def _operand_type(self, value: Operand) -> MIRType:
        if isinstance(value, ConstOperand):
            return value.type
        if isinstance(value, (CopyOperand, MoveOperand)):
            return self._place_type(value.place)
        raise MIRCodegenError(f"unknown Python operand type: {type(value).__name__}")

    @staticmethod
    def _typed_constant(value: ConstOperand) -> str:
        if value.type.name == "int":
            return f"rove_i64({value.value})"
        if value.type.name == "string":
            return json.dumps(str(value.value), ensure_ascii=False)
        if value.type.name == "bool":
            return _PythonEmitter._bool(bool(value.value))
        if value.type.name in ("float", "f64"):
            number = float(value.value)
            if math.isnan(number):
                return "math.nan"
            if math.isinf(number):
                return "math.inf" if number > 0 else "-math.inf"
            return repr(number)
        raise MIRCodegenError(f"unsupported Python constant type '{value.type}'")

    @staticmethod
    def _constant(value: object) -> str:
        if value is True:
            return "True"
        if value is False:
            return "False"
        return repr(value)

    @staticmethod
    def _bool(value: bool) -> str:
        return "True" if value else "False"

    @staticmethod
    def _default(value: MIRType) -> str:
        if value.optional:
            return "None"
        if value.name == "Array":
            return "[]"
        return {"bool": "False", "int": "0", "float": "0.0", "f64": "0.0", "string": "\"\""}.get(value.name, "None")

    def _place(self, place: Place) -> str:
        rendered = f"l{place.local}"
        for projection in place.projections:
            if isinstance(projection, FieldProjection):
                rendered = f"rove_field({rendered}, {projection.name!r})"
            elif isinstance(projection, ConstantIndexProjection):
                rendered = f"rove_index({rendered}, {projection.index})"
            elif isinstance(projection, IndexProjection):
                rendered = f"rove_index({rendered}, l{projection.local})"
            else:
                raise MIRCodegenError(f"illegal projection reached Python emitter: {type(projection).__name__}")
        return rendered

    def _assign_place(self, place: Place, value: str) -> str:
        if not place.projections:
            return f"l{place.local} = {value}"
        parent = Place(place.local, place.projections[:-1])
        projection = place.projections[-1]
        rendered_parent = self._place(parent)
        if isinstance(projection, FieldProjection):
            return f"rove_set_field({rendered_parent}, {projection.name!r}, {value})"
        if isinstance(projection, ConstantIndexProjection):
            return f"rove_set_index({rendered_parent}, {projection.index}, {value})"
        if isinstance(projection, IndexProjection):
            return f"rove_set_index({rendered_parent}, l{projection.local}, {value})"
        raise MIRCodegenError(f"illegal assignment projection reached Python emitter: {type(projection).__name__}")

    def _place_type(self, place: Place) -> MIRType:
        value_type = self.local_types[place.local]
        for projection in place.projections:
            if value_type.optional:
                value_type = replace(value_type, optional=False)
            if isinstance(projection, FieldProjection):
                definition = self.structs.get(value_type.name)
                if definition is None:
                    raise MIRCodegenError(f"field projection requires a known struct, got '{value_type}'")
                field = next((item for item in definition.fields if item.name == projection.name), None)
                if field is None:
                    raise MIRCodegenError(f"struct '{definition.name}' has no field '{projection.name}'")
                value_type = field.type
            elif isinstance(projection, (ConstantIndexProjection, IndexProjection)):
                if value_type.name != "Array" or len(value_type.arguments) != 1:
                    raise MIRCodegenError(f"index projection requires Array<T>, got '{value_type}'")
                value_type = value_type.arguments[0]
            else:
                raise MIRCodegenError(f"unknown Python projection type: {type(projection).__name__}")
        return value_type


def emit_legalized_python(module: MIRModule) -> str:
    return _PythonEmitter(legalize_mir(module, "python", require_emitter=True)).emit()
