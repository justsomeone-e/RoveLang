"""Direct LLVM IR emitter for the legalized scalar/control-flow MIR pilot."""

from __future__ import annotations

import math
import re

from .codegen_cpp import MIRCodegenError
from .legalization import legalize_mir
from .model import (
    AssertTerminator,
    AssignStatement,
    BinaryRValue,
    CallTerminator,
    CastRValue,
    ConstOperand,
    CopyOperand,
    GotoTerminator,
    MIRFunction,
    MIRModule,
    MoveOperand,
    NopStatement,
    Operand,
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
            function.symbol: ("main" if function.name == "main" else f"nyx_fn_{_identifier(function.name)}")
            for function in module.functions
        }
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
            "; Experimental Nyx legalized MIR -> LLVM IR output.",
            "; The production Typed HIR LLVM emitter remains the parity oracle.",
            "declare i32 @printf(ptr, ...)",
            "declare void @exit(i32)",
            "",
            '@.fmt_i64 = private unnamed_addr constant [5 x i8] c"%lld\\00"',
            '@.fmt_f64 = private unnamed_addr constant [6 x i8] c"%.16g\\00"',
            '@.fmt_str = private unnamed_addr constant [3 x i8] c"%s\\00"',
            '@.space = private unnamed_addr constant [2 x i8] c" \\00"',
            '@.newline = private unnamed_addr constant [2 x i8] c"\\0A\\00"',
            '@.true = private unnamed_addr constant [5 x i8] c"true\\00"',
            '@.false = private unnamed_addr constant [6 x i8] c"false\\00"',
            "",
            self._division_helpers(),
        ]
        for value, (name, length) in self.string_names.items():
            escaped, _ = _escape_bytes(value)
            parts.append(f'@{name} = private unnamed_addr constant [{length} x i8] c"{escaped}"')
        if self.string_names:
            parts.append("")
        for function in self.module.functions:
            parts.append(self._function(function))
        return "\n".join(parts).rstrip() + "\n"

    @staticmethod
    def _division_helpers() -> str:
        return """define i64 @nyx_i64_div(i64 %left, i64 %right) {
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

define i64 @nyx_i64_rem(i64 %left, i64 %right) {
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

    def _collect_strings(self) -> None:
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
                terminator = block.terminator
                if isinstance(terminator, CallTerminator):
                    for argument in terminator.arguments:
                        operand(argument)
                elif isinstance(terminator, (SwitchIntTerminator, SwitchValueTerminator)):
                    operand(terminator.discriminator)
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
            destination = self.local_types[statement.place.local]
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
        raise MIRCodegenError(f"illegal statement reached LLVM emitter: {type(statement).__name__}")

    def _terminator(self, terminator: object) -> None:
        if isinstance(terminator, GotoTerminator):
            self.lines.append(f"  br label %bb{terminator.target}")
            return
        if isinstance(terminator, (SwitchIntTerminator, SwitchValueTerminator)):
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

    def _print(self, arguments: tuple[Operand, ...]) -> None:
        for index, argument in enumerate(arguments):
            if index:
                self.lines.append("  call i32 (ptr, ...) @printf(ptr @.space)")
            kind, value = self._operand(argument)
            if kind == "i64":
                self.lines.append(f"  call i32 (ptr, ...) @printf(ptr @.fmt_i64, i64 {value})")
            elif kind == "double":
                normalized = self._temp()
                self.lines.append(
                    f"  {normalized} = fadd double {value}, 0.000000e+00"
                )
                self.lines.append(
                    f"  call i32 (ptr, ...) @printf(ptr @.fmt_f64, double {normalized})"
                )
            elif kind == "i1":
                selected = self._temp()
                self.lines.append(f"  {selected} = select i1 {value}, ptr @.true, ptr @.false")
                self.lines.append(f"  call i32 (ptr, ...) @printf(ptr @.fmt_str, ptr {selected})")
            elif kind == "ptr":
                self.lines.append(f"  call i32 (ptr, ...) @printf(ptr @.fmt_str, ptr {value})")
            else:
                raise MIRCodegenError(f"LLVM print does not support value type '{kind}'")
        self.lines.append("  call i32 (ptr, ...) @printf(ptr @.newline)")

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
        raise MIRCodegenError(f"illegal rvalue reached LLVM emitter: {type(value).__name__}")

    def _binary(self, value: BinaryRValue) -> tuple[str, str]:
        left_type, left = self._operand(value.left)
        right_type, right = self._operand(value.right)
        if left_type != right_type:
            raise MIRCodegenError(f"LLVM binary operand mismatch: {left_type} and {right_type}")
        result = self._temp()
        if value.op in ("==", "!=", "<", "<=", ">", ">="):
            if left_type == "double":
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
            helper = "nyx_i64_div" if value.op == "/" else "nyx_i64_rem"
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

    def _operand(self, operand: Operand) -> tuple[str, str]:
        if isinstance(operand, ConstOperand):
            return self._type(operand.type), self._constant_operand(operand)
        if isinstance(operand, (CopyOperand, MoveOperand)):
            kind = self._type(self.local_types[operand.place.local])
            return kind, self._load(operand.place.local)
        raise MIRCodegenError(f"illegal operand reached LLVM emitter: {type(operand).__name__}")

    def _load(self, local: int) -> str:
        kind = self._type(self.local_types[local])
        temp = self._temp()
        self.lines.append(f"  {temp} = load {kind}, ptr %l{local}")
        return temp

    @staticmethod
    def _place(place: Place) -> str:
        if place.projections:
            raise MIRCodegenError("projected place reached scalar LLVM emitter")
        return f"%l{place.local}"

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

    @staticmethod
    def _type(value: MIRType) -> str:
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
        raise MIRCodegenError(f"unsupported LLVM MIR type '{value}'")

    def _temp(self) -> str:
        value = f"%t{self.temp}"
        self.temp += 1
        return value


def emit_legalized_llvm(module: MIRModule) -> str:
    """Validate and emit the M5 LLVM pilot without semantic fallback."""
    legalized = legalize_mir(module, "llvm", require_emitter=True)
    return _LLVMEmitter(legalized).emit()
