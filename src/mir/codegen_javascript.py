"""Node.js ES2022 emitter for legalized scalar/control-flow MIR."""

from __future__ import annotations

import json
import math
import re
from dataclasses import replace

from .codegen_cpp import MIRCodegenError
from .legalization import legalize_mir
from .model import (
    AggregateRValue, AssertTerminator, AssignStatement, BinaryRValue, CallTerminator,
    CastRValue, ConstOperand, ConstantIndexProjection, CopyOperand, DiscriminantRValue, FieldProjection,
    GotoTerminator, IndexProjection, MIRFunction, MIRModule, MIRStructDef,
    MoveOperand, NopStatement, Operand, PayloadRValue, Place, ReturnTerminator,
    StorageDeadStatement, StorageLiveStatement, SwitchIntTerminator,
    SwitchValueTerminator, ThrowTerminator, UnaryRValue, UnreachableTerminator, UseRValue,
)
from .types import MIRType


_RUNTIME = r'''"use strict";

const nyxI64 = value => BigInt.asIntN(64, value);
class NyxUserThrow {
  constructor(value) { this.value = value; }
}
const nyxDiv = (left, right) => {
  if (right === 0n) throw new Error("division by zero");
  return nyxI64(left / right);
};
const nyxRem = (left, right) => {
  if (right === 0n) throw new Error("remainder by zero");
  return nyxI64(left % right);
};
const nyxClone = value => {
  if (Array.isArray(value)) return value.map(nyxClone);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, nyxClone(item)]));
  }
  return value;
};
const nyxIndex = (value, index) => {
  const position = Number(index);
  if (!Number.isInteger(position) || position < 0 || position >= value.length) {
    throw new RangeError(`index ${position} out of bounds for length ${value.length}`);
  }
  return value[position];
};
const nyxSetIndex = (value, index, item) => {
  const position = Number(index);
  if (!Number.isInteger(position) || position < 0 || position >= value.length) {
    throw new RangeError(`index ${position} out of bounds for length ${value.length}`);
  }
  value[position] = item;
};
const nyxField = (value, name) => value.fields[name];
const nyxSetField = (value, name, item) => { value.fields[name] = item; };
const nyxDisplay = value => {
  if (value === true) return "true";
  if (value === false) return "false";
  if (typeof value === "number") {
    if (Number.isNaN(value)) return "nan";
    if (value === Infinity) return "inf";
    if (value === -Infinity) return "-inf";
    if (Object.is(value, -0)) return "0";
  }
  return String(value);
};'''


def _identifier(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_$]", "_", value)
    if not clean or clean[0].isdigit():
        clean = "_" + clean
    return clean


class _JavaScriptEmitter:
    def __init__(self, module: MIRModule):
        self.module = module
        self.function_names = {
            function.symbol: f"nyxFn_{_identifier(function.name)}"
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
        parts = ["// Experimental Nyx legalized MIR -> Node.js ES2022 output.", _RUNTIME, ""]
        parts.extend(self._function(function) + "\n" for function in self.module.functions)
        by_name = {function.name: function for function in self.module.functions}
        entry = by_name.get("main") or by_name.get("__nyx_top_level")
        if entry is not None:
            parts.append(f"{self.function_names[entry.symbol]}();")
        return "\n".join(parts).rstrip() + "\n"

    def _function(self, function: MIRFunction) -> str:
        self.current = function
        self.local_types = {local.id: local.type for local in function.locals}
        parameters = ", ".join(f"l{local}" for local in function.parameters)
        lines = [f"function {self.function_names[function.symbol]}({parameters}) {{"]
        parameter_ids = set(function.parameters)
        for local in function.locals:
            if local.id in parameter_ids or local.type.name in ("void", "any"):
                continue
            lines.append(f"  let l{local.id} = {self._default(local.type)};")
        lines.extend(("  let pc = 0;", "  while (true) {", "    switch (pc) {"))
        for block in function.blocks:
            lines.append(f"      case {block.id}: {{")
            for statement in block.statements:
                lines.extend(f"        {line}" for line in self._statement(statement))
            lines.extend(f"        {line}" for line in self._terminator(block.terminator))
            lines.append("      }")
        lines.extend(("      default: throw new Error(\"invalid MIR block\");", "    }", "  }", "}"))
        self.current = None
        self.local_types = {}
        return "\n".join(lines)

    def _statement(self, value: object) -> list[str]:
        if isinstance(value, AssignStatement):
            if self._place_type(value.place).name in ("void", "any"):
                return []
            return [self._assign_place(value.place, self._rvalue(value.value))]
        if isinstance(value, (StorageLiveStatement, StorageDeadStatement, NopStatement)):
            return []
        raise MIRCodegenError(f"illegal statement reached JavaScript emitter: {type(value).__name__}")

    def _terminator(self, value: object) -> list[str]:
        if isinstance(value, GotoTerminator):
            return self._goto(value.target)
        if isinstance(value, SwitchIntTerminator):
            discriminator = self._operand(value.discriminator)
            value_type = self._operand_type(value.discriminator)
            lines: list[str] = []
            for expected, target in value.targets:
                rendered = ("true" if bool(expected) else "false") if value_type.name == "bool" else f"{expected}n"
                lines.append(f"if ({discriminator} === {rendered}) {{")
                lines.extend(f"  {line}" for line in self._goto(target))
                lines.append("}")
            lines.extend(self._goto(value.otherwise))
            return lines
        if isinstance(value, SwitchValueTerminator):
            discriminator = self._operand(value.discriminator)
            lines = []
            for expected, target in value.targets:
                lines.append(f"if ({discriminator} === {self._constant(expected)}) {{")
                lines.extend(f"  {line}" for line in self._goto(target))
                lines.append("}")
            lines.extend(self._goto(value.otherwise))
            return lines
        if isinstance(value, CallTerminator):
            if value.target is None:
                raise MIRCodegenError(f"call '{value.function}' has no continuation")
            arguments = ", ".join(self._operand(argument) for argument in value.arguments)
            if value.function == "builtin::print":
                line = f"console.log([{arguments}].map(nyxDisplay).join(\" \"));"
            elif value.function == "builtin::len":
                if len(value.arguments) != 1 or value.destination is None:
                    raise MIRCodegenError("builtin::len requires one argument and a destination")
                line = f"{self._place(value.destination)} = nyxI64(BigInt({self._operand(value.arguments[0])}.length));"
            elif value.function == "builtin::to_string":
                if len(value.arguments) != 1 or value.destination is None:
                    raise MIRCodegenError("builtin::to_string requires one argument and a destination")
                line = f"{self._place(value.destination)} = nyxDisplay({self._operand(value.arguments[0])});"
            elif value.function in self.function_names:
                call = f"{self.function_names[value.function]}({arguments})"
                callee = self.functions[value.function]
                if value.destination is not None and callee.locals[callee.return_local].type.name not in ("void", "any"):
                    line = f"l{value.destination.local} = {call};"
                else:
                    line = f"{call};"
            else:
                raise MIRCodegenError(f"illegal runtime call reached JavaScript emitter: {value.function}")
            if value.unwind is not None:
                if value.error_destination is None:
                    raise MIRCodegenError("JavaScript MIR call unwind requires an error destination")
                return [
                    "try {",
                    f"  {line}",
                    "} catch (error) {",
                    "  if (!(error instanceof NyxUserThrow)) throw error;",
                    f"  {self._place(value.error_destination)} = error.value;",
                    f"  pc = {value.unwind};",
                    "  continue;",
                    "}",
                ] + self._goto(value.target)
            return [line] + self._goto(value.target)
        if isinstance(value, AssertTerminator):
            expected = "true" if value.expected else "false"
            return [
                f"if (Boolean({self._operand(value.condition)}) !== {expected}) throw new Error({json.dumps(value.message)});"
            ] + self._goto(value.target)
        if isinstance(value, ThrowTerminator):
            rendered = self._operand(value.value)
            if value.target is not None and value.destination is not None:
                return [self._assign_place(value.destination, f"nyxDisplay({rendered})")] + self._goto(
                    value.target
                )
            return [f"throw new NyxUserThrow(nyxDisplay({rendered}));"]
        if isinstance(value, ReturnTerminator):
            assert self.current is not None
            result = self.current.locals[self.current.return_local].type
            return ["return;"] if result.name in ("void", "any") else ["return l0;"]
        if isinstance(value, UnreachableTerminator):
            return ["throw new Error(\"reached unreachable MIR terminator\");"]
        raise MIRCodegenError(f"illegal terminator reached JavaScript emitter: {type(value).__name__}")

    @staticmethod
    def _goto(target: int) -> list[str]:
        return [f"pc = {target};", "continue;"]

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
                return f"nyxI64(BigInt(Math.trunc(Number({operand}))))"
            if value.type.name in ("float", "f64"):
                return f"Number({operand})"
            if value.type.name == "bool":
                return f"Boolean({operand})"
            if value.type.name == "string":
                return f"nyxDisplay({operand})"
            return operand
        if isinstance(value, AggregateRValue):
            operands = [self._operand(operand) for operand in value.operands]
            if value.kind == "array":
                return "[" + ", ".join(operands) + "]"
            if value.kind == "struct":
                fields = value.fields or tuple(str(index) for index in range(len(operands)))
                body = ", ".join(f"{json.dumps(name)}: {operand}" for name, operand in zip(fields, operands))
                return f"{{__type__: {json.dumps(value.name)}, fields: {{{body}}}}}"
            if value.kind in ("enum", "option", "result"):
                return (
                    f"{{__type__: {json.dumps(value.type.name)}, tag: {json.dumps(value.name)}, "
                    f"payload: [{', '.join(operands)}]}}"
                )
            raise MIRCodegenError(f"unsupported JavaScript aggregate kind '{value.kind}'")
        if isinstance(value, DiscriminantRValue):
            return f"({self._operand(value.operand)}).tag"
        if isinstance(value, PayloadRValue):
            return f"nyxIndex(({self._operand(value.operand)}).payload, {value.index}n)"
        if isinstance(value, UnaryRValue):
            operand = self._operand(value.operand)
            if value.op in ("!", "not"):
                return f"!Boolean({operand})"
            if value.op == "+":
                return operand
            if value.op == "-" and value.type.name == "int":
                return f"nyxI64(-({operand}))"
            if value.op == "-":
                return f"-({operand})"
            if value.op == "~":
                return f"nyxI64(~({operand}))"
            raise MIRCodegenError(f"unsupported JavaScript unary operation '{value.op}'")
        raise MIRCodegenError(f"illegal rvalue reached JavaScript emitter: {type(value).__name__}")

    def _binary(self, value: BinaryRValue) -> str:
        left = self._operand(value.left)
        right = self._operand(value.right)
        left_type = self._operand_type(value.left)
        right_type = self._operand_type(value.right)
        if value.op in ("==", "!=", "<", "<=", ">", ">="):
            operation = {"==": "===", "!=": "!=="}.get(value.op, value.op)
            return f"({left} {operation} {right})"
        if value.op == "+" and (left_type.name == "string" or right_type.name == "string"):
            return f"String({left}) + String({right})"
        if left_type.name in ("float", "f64") or right_type.name in ("float", "f64"):
            if value.op in ("+", "-", "*", "/", "%"):
                return f"({left} {value.op} {right})"
        if value.op in ("+", "-", "*", "&", "|", "^"):
            return f"nyxI64(({left}) {value.op} ({right}))"
        if value.op == "/":
            return f"nyxDiv({left}, {right})"
        if value.op == "%":
            return f"nyxRem({left}, {right})"
        if value.op in ("<<", ">>"):
            return f"nyxI64(({left}) {value.op} BigInt.asUintN(6, {right}))"
        raise MIRCodegenError(f"unsupported JavaScript binary operation '{value.op}'")

    def _operand(self, value: Operand) -> str:
        if isinstance(value, ConstOperand):
            return self._typed_constant(value)
        if isinstance(value, (CopyOperand, MoveOperand)):
            rendered = self._place(value.place)
            return f"nyxClone({rendered})" if isinstance(value, CopyOperand) else rendered
        raise MIRCodegenError(f"illegal operand reached JavaScript emitter: {type(value).__name__}")

    def _operand_type(self, value: Operand) -> MIRType:
        if isinstance(value, ConstOperand):
            return value.type
        if isinstance(value, (CopyOperand, MoveOperand)):
            return self._place_type(value.place)
        raise MIRCodegenError(f"unknown JavaScript operand type: {type(value).__name__}")

    @staticmethod
    def _typed_constant(value: ConstOperand) -> str:
        if value.type.name == "int":
            return f"{value.value}n"
        if value.type.name == "string":
            return json.dumps(str(value.value), ensure_ascii=False)
        if value.type.name == "bool":
            return "true" if value.value else "false"
        if value.type.name in ("float", "f64"):
            number = float(value.value)
            if math.isnan(number): return "NaN"
            if math.isinf(number): return "Infinity" if number > 0 else "-Infinity"
            return repr(number)
        raise MIRCodegenError(f"unsupported JavaScript constant type '{value.type}'")

    @staticmethod
    def _constant(value: object) -> str:
        if value is True: return "true"
        if value is False: return "false"
        if isinstance(value, int): return f"{value}n"
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _default(value: MIRType) -> str:
        if value.optional:
            return "null"
        if value.name == "Array":
            return "[]"
        return {"bool": "false", "int": "0n", "float": "0", "f64": "0", "string": '""'}.get(value.name, "null")

    def _place(self, place: Place) -> str:
        rendered = f"l{place.local}"
        for projection in place.projections:
            if isinstance(projection, FieldProjection):
                rendered = f"nyxField({rendered}, {json.dumps(projection.name)})"
            elif isinstance(projection, ConstantIndexProjection):
                rendered = f"nyxIndex({rendered}, {projection.index}n)"
            elif isinstance(projection, IndexProjection):
                rendered = f"nyxIndex({rendered}, l{projection.local})"
            else:
                raise MIRCodegenError(f"illegal projection reached JavaScript emitter: {type(projection).__name__}")
        return rendered

    def _assign_place(self, place: Place, value: str) -> str:
        if not place.projections:
            return f"l{place.local} = {value};"
        parent = Place(place.local, place.projections[:-1])
        projection = place.projections[-1]
        rendered_parent = self._place(parent)
        if isinstance(projection, FieldProjection):
            return f"nyxSetField({rendered_parent}, {json.dumps(projection.name)}, {value});"
        if isinstance(projection, ConstantIndexProjection):
            return f"nyxSetIndex({rendered_parent}, {projection.index}n, {value});"
        if isinstance(projection, IndexProjection):
            return f"nyxSetIndex({rendered_parent}, l{projection.local}, {value});"
        raise MIRCodegenError(f"illegal assignment projection reached JavaScript emitter: {type(projection).__name__}")

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
                raise MIRCodegenError(f"unknown JavaScript projection type: {type(projection).__name__}")
        return value_type


def emit_legalized_javascript(module: MIRModule) -> str:
    return _JavaScriptEmitter(legalize_mir(module, "js", require_emitter=True)).emit()
