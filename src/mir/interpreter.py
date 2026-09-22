"""Executable reference semantics for the scalar/control-flow MIR subset."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import math

from .model import (
    AssertTerminator,
    AggregateRValue,
    AssignStatement,
    BinaryRValue,
    BorrowRValue,
    CastRValue,
    CallTerminator,
    ConstantIndexProjection,
    ConstOperand,
    CopyOperand,
    DeinitStatement,
    DerefProjection,
    DiscriminantRValue,
    DropTerminator,
    FieldProjection,
    GotoTerminator,
    IndexProjection,
    MIRFunction,
    MIRModule,
    MoveOperand,
    NopStatement,
    Operand,
    PayloadRValue,
    Place,
    ReleaseStatement,
    RetainStatement,
    ReturnTerminator,
    StorageDeadStatement,
    StorageLiveStatement,
    SwitchIntTerminator,
    SwitchValueTerminator,
    SuspendTerminator,
    ThrowTerminator,
    UnaryRValue,
    UnreachableTerminator,
    UseRValue,
    VariantProjection,
)
from .verifier import verify_mir


_UNINITIALIZED = object()
_I64_MASK = (1 << 64) - 1
_I64_SIGN = 1 << 63


class MIRTrap(RuntimeError):
    pass


class _MIRUserThrow(Exception):
    def __init__(self, value: object):
        self.value = value
        super().__init__(str(value))


class _MIRTask:
    """Hot, memoized reference task matching Nyx repeated-await semantics."""

    def __init__(self, thunk):
        self.value = None
        self.error: BaseException | None = None
        try:
            self.value = thunk()
        except BaseException as error:
            self.error = error

    def await_result(self):
        if self.error is not None:
            raise self.error
        return self.value


@dataclass(slots=True)
class _BorrowReference:
    locals: list[object]
    place: Place
    mutable: bool


@dataclass(frozen=True, slots=True)
class MIRExecutionResult:
    value: object
    output: tuple[str, ...]
    steps: int


class MIRInterpreter:
    def __init__(self, module: MIRModule, *, max_steps: int = 100_000):
        self.module = verify_mir(module)
        self.max_steps = max_steps
        self.output: list[str] = []
        self.steps = 0
        self.retain_counts: dict[int, int] = {}
        self.functions = {function.symbol: function for function in module.functions}
        self.functions.update({function.name: function for function in module.functions})

    def run(self, entry: str | None = None, arguments: tuple[object, ...] = ()) -> MIRExecutionResult:
        try:
            if entry is not None:
                value = self._call(self._function(entry), arguments)
            else:
                value = None
                top_level = self.functions.get("function::__nyx_top_level")
                if top_level is not None:
                    value = self._call(top_level, ())
                else:
                    main = self.functions.get("main")
                    if main is not None:
                        value = self._call(main, arguments)
        except _MIRUserThrow as thrown:
            raise MIRTrap(f"uncaught Nyx throw: {self._format(thrown.value)}") from None
        return MIRExecutionResult(value, tuple(self.output), self.steps)

    def _function(self, name: str) -> MIRFunction:
        function = self.functions.get(name)
        if function is None:
            raise MIRTrap(f"Unknown MIR function '{name}'")
        return function

    def _call(self, function: MIRFunction, arguments: tuple[object, ...]) -> object:
        if len(arguments) != len(function.parameters):
            raise MIRTrap(
                f"Function '{function.name}' expected {len(function.parameters)} arguments, got {len(arguments)}"
            )
        locals_: list[object] = [_UNINITIALIZED] * len(function.locals)
        for local_id, value in zip(function.parameters, arguments):
            locals_[local_id] = value
        block_id = 0
        while True:
            self._tick()
            block = function.blocks[block_id]
            for statement in block.statements:
                self._tick()
                if isinstance(statement, AssignStatement):
                    self._write_place(
                        statement.place,
                        locals_,
                        self._rvalue(statement.value, locals_),
                    )
                elif isinstance(statement, StorageLiveStatement):
                    locals_[statement.local] = _UNINITIALIZED
                elif isinstance(statement, StorageDeadStatement):
                    locals_[statement.local] = _UNINITIALIZED
                elif isinstance(statement, RetainStatement):
                    value = self._read_place(statement.place, locals_, clone=False)
                    identity = id(value)
                    self.retain_counts[identity] = self.retain_counts.get(identity, 1) + 1
                elif isinstance(statement, ReleaseStatement):
                    value = self._read_place(statement.place, locals_, clone=False)
                    identity = id(value)
                    count = self.retain_counts.get(identity, 1)
                    if count <= 0:
                        raise MIRTrap("release of an already released MIR value")
                    self.retain_counts[identity] = count - 1
                elif isinstance(statement, DeinitStatement):
                    self._write_place(statement.place, locals_, _UNINITIALIZED)
                elif not isinstance(statement, NopStatement):
                    raise MIRTrap(f"Unsupported MIR statement {type(statement).__name__}")

            terminator = block.terminator
            if isinstance(terminator, GotoTerminator):
                block_id = terminator.target
            elif isinstance(terminator, SwitchIntTerminator):
                discriminator = self._operand(terminator.discriminator, locals_)
                block_id = next(
                    (target for value, target in terminator.targets if discriminator == value),
                    terminator.otherwise,
                )
            elif isinstance(terminator, SwitchValueTerminator):
                discriminator = self._operand(terminator.discriminator, locals_)
                block_id = next(
                    (target for value, target in terminator.targets if discriminator == value),
                    terminator.otherwise,
                )
            elif isinstance(terminator, ReturnTerminator):
                value = locals_[function.return_local]
                return None if value is _UNINITIALIZED else value
            elif isinstance(terminator, CallTerminator):
                values = tuple(self._operand(argument, locals_) for argument in terminator.arguments)
                try:
                    value = self._invoke(terminator.function, values)
                except _MIRUserThrow as thrown:
                    if terminator.unwind is None or terminator.error_destination is None:
                        raise
                    self._write_place(terminator.error_destination, locals_, thrown.value)
                    block_id = terminator.unwind
                    continue
                if terminator.destination is not None:
                    self._write_place(terminator.destination, locals_, value)
                if terminator.target is None:
                    raise MIRTrap(f"Call to '{terminator.function}' has no continuation")
                block_id = terminator.target
            elif isinstance(terminator, AssertTerminator):
                actual = bool(self._operand(terminator.condition, locals_))
                if actual != terminator.expected:
                    raise MIRTrap(terminator.message)
                block_id = terminator.target
            elif isinstance(terminator, DropTerminator):
                self._read_place(terminator.place, locals_, clone=False)
                self._write_place(terminator.place, locals_, _UNINITIALIZED)
                block_id = terminator.target
            elif isinstance(terminator, ThrowTerminator):
                value = self._operand(terminator.value, locals_)
                if terminator.target is None:
                    raise _MIRUserThrow(value)
                if terminator.destination is None:
                    raise MIRTrap("Caught throw requires a destination")
                self._write_place(terminator.destination, locals_, value)
                block_id = terminator.target
            elif isinstance(terminator, SuspendTerminator):
                task = self._operand(terminator.task, locals_)
                if not isinstance(task, _MIRTask):
                    raise MIRTrap("MIR suspend operand is not a Task")
                try:
                    value = task.await_result()
                except _MIRUserThrow as thrown:
                    if terminator.unwind is None or terminator.error_destination is None:
                        raise
                    self._write_place(terminator.error_destination, locals_, thrown.value)
                    block_id = terminator.unwind
                    continue
                self._write_place(terminator.destination, locals_, value)
                block_id = terminator.resume
            elif isinstance(terminator, UnreachableTerminator):
                raise MIRTrap("Reached unreachable MIR terminator")
            else:
                raise MIRTrap(f"Unsupported MIR terminator {type(terminator).__name__}")

    def _invoke(self, symbol: str, arguments: tuple[object, ...]) -> object:
        if symbol in self.functions:
            function = self.functions[symbol]
            if function.is_async:
                return _MIRTask(lambda: self._call(function, arguments))
            return self._call(function, arguments)
        name = symbol.split("::")[-1]
        if name == "print":
            self.output.append(" ".join(self._format(value) for value in arguments))
            return None
        if name == "to_string":
            return self._format(arguments[0])
        if name == "to_int":
            return self._wrap_i64(int(arguments[0]))
        if name == "contains":
            return arguments[1] in arguments[0]
        if name == "is_number":
            try:
                float(arguments[0])
                return True
            except (TypeError, ValueError):
                return False
        if name == "len":
            return len(arguments[0])
        if name == "Ok":
            return ("Ok", arguments[0])
        if name == "Err":
            return ("Err", arguments[0])
        raise MIRTrap(f"Reference interpreter has no implementation for call '{symbol}'")

    def _rvalue(self, value: object, locals_: list[object]) -> object:
        if isinstance(value, UseRValue):
            return self._operand(value.operand, locals_)
        if isinstance(value, BinaryRValue):
            left = self._operand(value.left, locals_)
            right = self._operand(value.right, locals_)
            return self._binary(value.op, left, right, value.type.name)
        if isinstance(value, UnaryRValue):
            operand = self._operand(value.operand, locals_)
            if value.op in ("!", "not"):
                return not bool(operand)
            if value.op == "-":
                result = -operand
                return self._wrap_i64(result) if value.type.name.startswith(("i", "u")) or value.type.name == "int" else result
            if value.op == "+":
                return operand
            if value.op == "~":
                return self._wrap_i64(~int(operand))
            raise MIRTrap(f"Unsupported unary operation '{value.op}'")
        if isinstance(value, CastRValue):
            operand = self._operand(value.operand, locals_)
            if value.type.name in ("float", "f32", "f64"):
                return float(operand)
            if value.type.name == "bool":
                return bool(operand)
            if value.type.name == "string":
                return self._format(operand)
            if value.type.name == "int" or value.type.name.startswith(("i", "u")):
                return self._wrap_i64(int(operand))
            return operand
        if isinstance(value, BorrowRValue):
            self._read_place(value.place, locals_, clone=False)
            return _BorrowReference(locals_, value.place, value.mutable)
        if isinstance(value, AggregateRValue):
            operands = tuple(self._operand(item, locals_) for item in value.operands)
            if value.kind == "array":
                return list(operands)
            if value.kind in ("enum", "result", "option"):
                return (value.name,) + operands
            if value.kind == "struct":
                field_names = value.fields or tuple(str(index) for index in range(len(operands)))
                return {
                    "__type__": value.name,
                    "fields": dict(zip(field_names, operands)),
                }
            raise MIRTrap(f"Unsupported aggregate kind '{value.kind}'")
        if isinstance(value, DiscriminantRValue):
            operand = self._operand(value.operand, locals_)
            if operand is None:
                return "None"
            if isinstance(operand, tuple) and operand:
                return operand[0]
            if isinstance(operand, dict) and "__tag__" in operand:
                return operand["__tag__"]
            return type(operand).__name__
        if isinstance(value, PayloadRValue):
            operand = self._operand(value.operand, locals_)
            if isinstance(operand, tuple) and len(operand) > value.index + 1:
                return operand[value.index + 1]
            if isinstance(operand, dict) and "payload" in operand:
                return operand["payload"][value.index]
            raise MIRTrap(f"Aggregate has no payload {value.index}")
        raise MIRTrap(f"Unsupported MIR rvalue {type(value).__name__}")

    def _operand(self, operand: Operand, locals_: list[object]) -> object:
        if isinstance(operand, ConstOperand):
            return operand.value
        if isinstance(operand, CopyOperand):
            return self._read_place(operand.place, locals_, clone=True)
        if isinstance(operand, MoveOperand):
            value = self._read_place(operand.place, locals_, clone=False)
            self._write_place(operand.place, locals_, _UNINITIALIZED)
            return value
        raise MIRTrap(f"Unsupported MIR operand {type(operand).__name__}")

    def _read_place(self, place: Place, locals_: list[object], *, clone: bool) -> object:
        if place.local < 0 or place.local >= len(locals_):
            raise MIRTrap(f"Unknown MIR local _{place.local}")
        value = locals_[place.local]
        if value is _UNINITIALIZED:
            raise MIRTrap(f"Read of uninitialized or moved local _{place.local}")
        for projection in place.projections:
            value = self._project(value, projection, locals_)
            if value is _UNINITIALIZED:
                raise MIRTrap(f"Read of moved value at _{place.local}")
        return self._clone(value) if clone else value

    def _write_place(self, place: Place, locals_: list[object], value: object) -> None:
        if not place.projections:
            locals_[place.local] = value
            return
        current = locals_[place.local]
        if current is _UNINITIALIZED:
            raise MIRTrap(f"Write through uninitialized local _{place.local}")
        for projection in place.projections[:-1]:
            current = self._project(current, projection, locals_)
            if current is _UNINITIALIZED:
                raise MIRTrap(f"Write through moved value at _{place.local}")
        self._assign_projection(current, place.projections[-1], locals_, value)

    def _project(self, value: object, projection: object, locals_: list[object]) -> object:
        if isinstance(projection, FieldProjection):
            if not isinstance(value, dict) or "fields" not in value:
                raise MIRTrap(f"Field projection '.{projection.name}' requires a struct")
            fields = value["fields"]
            if projection.name not in fields:
                raise MIRTrap(f"Struct has no field '{projection.name}'")
            return fields[projection.name]
        if isinstance(projection, ConstantIndexProjection):
            return self._index(value, projection.index)
        if isinstance(projection, IndexProjection):
            index = locals_[projection.local]
            if index is _UNINITIALIZED:
                raise MIRTrap(f"Index local _{projection.local} is uninitialized")
            return self._index(value, int(index))
        if isinstance(projection, DerefProjection):
            if not isinstance(value, _BorrowReference):
                raise MIRTrap("Dereference projection requires a MIR borrow")
            return self._read_place(value.place, value.locals, clone=False)
        if isinstance(projection, VariantProjection):
            if not isinstance(value, tuple) or not value or value[0] != projection.name:
                raise MIRTrap(f"Expected enum variant '{projection.name}'")
            if projection.index < 0 or projection.index + 1 >= len(value):
                raise MIRTrap(f"Variant '{projection.name}' has no payload {projection.index}")
            return value[projection.index + 1]
        raise MIRTrap(f"Unsupported place projection {type(projection).__name__}")

    def _assign_projection(
        self,
        container: object,
        projection: object,
        locals_: list[object],
        value: object,
    ) -> None:
        if isinstance(projection, FieldProjection):
            if not isinstance(container, dict) or "fields" not in container:
                raise MIRTrap(f"Field projection '.{projection.name}' requires a struct")
            if projection.name not in container["fields"]:
                raise MIRTrap(f"Struct has no field '{projection.name}'")
            container["fields"][projection.name] = value
            return
        if isinstance(projection, ConstantIndexProjection):
            self._set_index(container, projection.index, value)
            return
        if isinstance(projection, IndexProjection):
            index = locals_[projection.local]
            if index is _UNINITIALIZED:
                raise MIRTrap(f"Index local _{projection.local} is uninitialized")
            self._set_index(container, int(index), value)
            return
        if isinstance(projection, DerefProjection):
            if not isinstance(container, _BorrowReference) or not container.mutable:
                raise MIRTrap("Assignment through dereference requires a mutable MIR borrow")
            self._write_place(container.place, container.locals, value)
            return
        if isinstance(projection, VariantProjection):
            raise MIRTrap("Variant payload assignment is not part of Nyx value semantics")
        raise MIRTrap(f"Unsupported place projection {type(projection).__name__}")

    @staticmethod
    def _index(value: object, index: int) -> object:
        if not isinstance(value, (list, tuple, str)):
            raise MIRTrap("Index projection requires an array, tuple, or string")
        if index < 0 or index >= len(value):
            raise MIRTrap(f"index {index} out of bounds for length {len(value)}")
        return value[index]

    @staticmethod
    def _set_index(value: object, index: int, item: object) -> None:
        if not isinstance(value, list):
            raise MIRTrap("Indexed assignment requires a mutable array")
        if index < 0 or index >= len(value):
            raise MIRTrap(f"index {index} out of bounds for length {len(value)}")
        value[index] = item

    @staticmethod
    def _clone(value: object) -> object:
        if isinstance(value, _BorrowReference):
            return value
        return copy.deepcopy(value)

    def _binary(self, op: str, left: object, right: object, result_type: str) -> object:
        if op == "+":
            result = left + right
        elif op == "-":
            result = left - right
        elif op == "*":
            result = left * right
        elif op == "/":
            if result_type in ("float", "f32", "f64"):
                left = float(left)
                right = float(right)
                if right != 0.0:
                    result = left / right
                elif left == 0.0 or math.isnan(left):
                    result = math.nan
                else:
                    negative = math.copysign(1.0, left) != math.copysign(1.0, right)
                    result = -math.inf if negative else math.inf
            else:
                if right == 0:
                    raise MIRTrap("division by zero")
                quotient = abs(int(left)) // abs(int(right))
                result = -quotient if (left < 0) != (right < 0) else quotient
        elif op == "%":
            if result_type in ("float", "f32", "f64"):
                try:
                    result = math.fmod(float(left), float(right))
                except ValueError:
                    result = math.nan
            else:
                if right == 0:
                    raise MIRTrap("remainder by zero")
                quotient = abs(int(left)) // abs(int(right))
                if (left < 0) != (right < 0):
                    quotient = -quotient
                result = int(left) - quotient * int(right)
        elif op == "==":
            return left == right
        elif op == "!=":
            return left != right
        elif op == "<":
            return left < right
        elif op == "<=":
            return left <= right
        elif op == ">":
            return left > right
        elif op == ">=":
            return left >= right
        elif op in ("&", "|", "^"):
            result = {"&": int(left) & int(right), "|": int(left) | int(right), "^": int(left) ^ int(right)}[op]
        elif op in ("<<", ">>"):
            amount = int(right) & 63
            result = int(left) << amount if op == "<<" else int(left) >> amount
        else:
            raise MIRTrap(f"Unsupported binary operation '{op}'")
        if result_type == "int" or result_type.startswith(("i", "u")):
            return self._wrap_i64(int(result))
        return result

    def _tick(self) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise MIRTrap(f"MIR execution exceeded {self.max_steps} steps")

    @staticmethod
    def _wrap_i64(value: int) -> int:
        value &= _I64_MASK
        return value - (1 << 64) if value & _I64_SIGN else value

    @staticmethod
    def _format(value: object) -> str:
        if value is True:
            return "true"
        if value is False:
            return "false"
        if value is None:
            return "null"
        if isinstance(value, float):
            if math.isnan(value):
                return "nan"
            if math.isinf(value):
                return "inf" if value > 0 else "-inf"
            if value == 0.0:
                return "0"
        if isinstance(value, tuple) and value and isinstance(value[0], str):
            payload = ", ".join(MIRInterpreter._format(item) for item in value[1:])
            return f"{value[0]}({payload})"
        return str(value)
