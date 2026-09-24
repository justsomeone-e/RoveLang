"""Experimental LLVM IR native scalar emitter for Rove HIR.

Consumes verified IRModule and emits standard LLVM IR text (.ll) for scalar primitives
(int64, double, bool, void), scalar-field structs, signed 64-bit integer arithmetic
with wrapping overflow, safe division/modulo guards, scalar control flow, recursion,
and direct calls.

Supports stack-owned scalar arrays with checked indexing and independent local
copies. Rejects escaping arrays, aggregate fields, exceptions, tasks, and closures.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from src.ir.model import (
    IRAssign,
    IRArray,
    IRBinary,
    IRBreak,
    IRCall,
    IRConditional,
    IRContinue,
    IRExpr,
    IRExprStatement,
    IRFor,
    IRFunction,
    IRIf,
    IRIndexAccess,
    IRLiteral,
    IRMemberAccess,
    IRModule,
    IRNode,
    IRParameter,
    IRReference,
    IRReturn,
    IRStatement,
    IRStruct,
    IRUnary,
    IRVarDecl,
    IRWhile,
    SourceSpan,
)
from src.ir.types import IRType

_IDENTIFIER_CHARS = re.compile(r"[^0-9A-Za-z_]")

_LLVM_PRELUDE = """; Rove Direct LLVM IR Emitter (Experimental Native Scalar)

declare i32 @printf(ptr, ...)
declare void @exit(i32)
declare double @fmod(double, double)
declare void @llvm.memcpy.p0.p0.i64(ptr, ptr, i64, i1)

@__nyx_fmt_i64 = private unnamed_addr constant [6 x i8] c"%lld\\0A\\00"
@__nyx_fmt_f64_int = private unnamed_addr constant [6 x i8] c"%.1f\\0A\\00"
@__nyx_fmt_f64_gen = private unnamed_addr constant [7 x i8] c"%.16g\\0A\\00"
@__nyx_str_true = private unnamed_addr constant [6 x i8] c"true\\0A\\00"
@__nyx_str_false = private unnamed_addr constant [7 x i8] c"false\\0A\\00"
@__nyx_write_true = private unnamed_addr constant [5 x i8] c"true\\00"
@__nyx_write_false = private unnamed_addr constant [6 x i8] c"false\\00"
@__nyx_fmt_str = private unnamed_addr constant [4 x i8] c"%s\\0A\\00"
@__nyx_write_i64 = private unnamed_addr constant [5 x i8] c"%lld\\00"
@__nyx_write_f64_int = private unnamed_addr constant [5 x i8] c"%.1f\\00"
@__nyx_write_f64_gen = private unnamed_addr constant [6 x i8] c"%.16g\\00"
@__nyx_write_str = private unnamed_addr constant [3 x i8] c"%s\\00"
@__nyx_space = private unnamed_addr constant [2 x i8] c" \\00"
@__nyx_newline = private unnamed_addr constant [2 x i8] c"\\0A\\00"
@__nyx_err_div_zero = private unnamed_addr constant [26 x i8] c"integer division by zero\\0A\\00"
@__nyx_err_bounds = private unnamed_addr constant [27 x i8] c"array index out of bounds\\0A\\00"

define void @nyx_print_i64(i64 %v) {
entry:
  %0 = call i32 (ptr, ...) @printf(ptr @__nyx_fmt_i64, i64 %v)
  ret void
}

define void @nyx_print_f64(double %v) {
entry:
  %v_i64 = fptosi double %v to i64
  %v_round = sitofp i64 %v_i64 to double
  %is_int = fcmp oeq double %v, %v_round
  br i1 %is_int, label %print_int_fmt, label %print_gen_fmt

print_int_fmt:
  %call1 = call i32 (ptr, ...) @printf(ptr @__nyx_fmt_f64_int, double %v)
  ret void

print_gen_fmt:
  %call2 = call i32 (ptr, ...) @printf(ptr @__nyx_fmt_f64_gen, double %v)
  ret void
}

define void @nyx_print_bool(i1 %v) {
entry:
  br i1 %v, label %print_t, label %print_f

print_t:
  %c1 = call i32 (ptr, ...) @printf(ptr @__nyx_str_true)
  ret void

print_f:
  %c2 = call i32 (ptr, ...) @printf(ptr @__nyx_str_false)
  ret void
}

define void @nyx_print_str(ptr %v) {
entry:
  %c = call i32 (ptr, ...) @printf(ptr @__nyx_fmt_str, ptr %v)
  ret void
}

define void @nyx_write_i64(i64 %v) {
entry:
  %0 = call i32 (ptr, ...) @printf(ptr @__nyx_write_i64, i64 %v)
  ret void
}

define void @nyx_write_f64(double %v) {
entry:
  %v_i64 = fptosi double %v to i64
  %v_round = sitofp i64 %v_i64 to double
  %is_int = fcmp oeq double %v, %v_round
  br i1 %is_int, label %write_int_fmt, label %write_gen_fmt

write_int_fmt:
  %call1 = call i32 (ptr, ...) @printf(ptr @__nyx_write_f64_int, double %v)
  ret void

write_gen_fmt:
  %call2 = call i32 (ptr, ...) @printf(ptr @__nyx_write_f64_gen, double %v)
  ret void
}

define void @nyx_write_bool(i1 %v) {
entry:
  br i1 %v, label %write_t, label %write_f

write_t:
  %c1 = call i32 (ptr, ...) @printf(ptr @__nyx_write_str, ptr @__nyx_write_true)
  ret void

write_f:
  %c2 = call i32 (ptr, ...) @printf(ptr @__nyx_write_str, ptr @__nyx_write_false)
  ret void
}

define void @nyx_write_str(ptr %v) {
entry:
  %c = call i32 (ptr, ...) @printf(ptr @__nyx_write_str, ptr %v)
  ret void
}

define i64 @__nyx_i64_div(i64 %a, i64 %b) {
entry:
  %is_zero = icmp eq i64 %b, 0
  br i1 %is_zero, label %div_by_zero, label %check_overflow

div_by_zero:
  %err_call = call i32 (ptr, ...) @printf(ptr @__nyx_err_div_zero)
  call void @exit(i32 1)
  unreachable

check_overflow:
  %is_min_a = icmp eq i64 %a, -9223372036854775808
  %is_neg_one = icmp eq i64 %b, -1
  %is_ovf = and i1 %is_min_a, %is_neg_one
  br i1 %is_ovf, label %overflow_ret, label %normal_div

overflow_ret:
  ret i64 -9223372036854775808

normal_div:
  %res = sdiv i64 %a, %b
  ret i64 %res
}

define i64 @__nyx_i64_mod(i64 %a, i64 %b) {
entry:
  %is_zero = icmp eq i64 %b, 0
  br i1 %is_zero, label %mod_by_zero, label %check_overflow

mod_by_zero:
  %err_call = call i32 (ptr, ...) @printf(ptr @__nyx_err_div_zero)
  call void @exit(i32 1)
  unreachable

check_overflow:
  %is_min_a = icmp eq i64 %a, -9223372036854775808
  %is_neg_one = icmp eq i64 %b, -1
  %is_ovf = and i1 %is_min_a, %is_neg_one
  br i1 %is_ovf, label %overflow_ret, label %normal_mod

overflow_ret:
  ret i64 0

normal_mod:
  %res = srem i64 %a, %b
  ret i64 %res
}

define void @__nyx_array_check(i64 %index, i64 %length) {
entry:
  %negative = icmp slt i64 %index, 0
  %past_end = icmp sge i64 %index, %length
  %invalid = or i1 %negative, %past_end
  br i1 %invalid, label %bounds_error, label %valid

bounds_error:
  %err_call = call i32 (ptr, ...) @printf(ptr @__nyx_err_bounds)
  call void @exit(i32 1)
  unreachable

valid:
  ret void
}
"""


class LLVMEmissionError(ValueError):
    """Raised when the LLVM scalar pilot encounters unsupported HIR constructs."""

    def __init__(self, message: str, span: SourceSpan):
        self.message = message
        self.span = span
        super().__init__(f"{span.source}:{span.line}:{span.column}: {message}")


class BasicBlock:
    """Represents a basic block in LLVM IR."""

    def __init__(self, label: str):
        self.label = label
        self.instructions: List[str] = []
        self.terminated: bool = False

    def emit(self, instr: str) -> None:
        if not self.terminated:
            self.instructions.append(instr)

    def terminate(self, instr: str) -> None:
        if not self.terminated:
            self.instructions.append(instr)
            self.terminated = True


class LLVMScalarEmitter:
    """Direct LLVM IR text emitter from verified scalar and scalar-struct Rove HIR."""

    def __init__(self, module: IRModule):
        self.module = module
        self.symbol_names: Dict[str, str] = {}
        self.function_map: Dict[str, IRFunction] = {}
        self.struct_map: Dict[str, IRStruct] = {
            item.name: item for item in module.items if isinstance(item, IRStruct)
        }
        self.array_types: Set[str] = set()
        self.string_constants: List[Tuple[str, str, int]] = []  # (global_name, escaped_str, byte_len)
        self.string_map: Dict[str, str] = {}

        # Per-function state
        self.blocks: List[BasicBlock] = []
        self.entry_allocas: List[str] = []
        self.local_ptrs: Dict[str, Tuple[str, str]] = {}  # symbol -> (ptr_name, llvm_type)
        self.array_locals: Dict[str, Tuple[str, str, str]] = {}
        self.loop_stack: List[Tuple[str, str]] = []  # (continue_label, break_label)
        self.temp_counter: int = 0
        self.label_counter: int = 0

    def emit(self) -> str:
        self._validate_module()

        structs = [item for item in self.module.items if isinstance(item, IRStruct)]
        functions = [item for item in self.module.items if isinstance(item, IRFunction)]
        top_statements = [item for item in self.module.items if isinstance(item, IRStatement)]

        # Register functions
        for fn in functions:
            preferred = "_nyx_user_main" if fn.name == "main" else fn.name
            emitted = self._identifier(preferred)
            self.symbol_names[fn.symbol] = emitted
            self.function_map[fn.name] = fn

        function_codes: List[str] = []

        # Emit user functions
        for fn in functions:
            function_codes.append(self._emit_function(fn))

        # Emit runtime main function
        function_codes.append(self._emit_main_function(top_statements))

        # Assemble file
        lines: List[str] = [_LLVM_PRELUDE]

        if structs:
            lines.append("; Rove Struct Types")
            for struct in structs:
                fields = ", ".join(self._llvm_type(field.type) for field in struct.fields)
                lines.append(f"{self._llvm_struct_type(struct.name)} = type {{ {fields} }}")
            lines.append("")

        if self.array_types:
            lines.append("; Rove Stack Array Descriptors")
            for element_type in sorted(self.array_types):
                lines.append(f"{self._llvm_array_type_name(element_type)} = type {{ i64, ptr }}")
            lines.append("")

        # String constants
        if self.string_constants:
            lines.append("; String Constants")
            for gname, esc_str, blen in self.string_constants:
                lines.append(f"@{gname} = private unnamed_addr constant [{blen} x i8] c\"{esc_str}\"")
            lines.append("")

        lines.extend(function_codes)
        return "\n".join(lines).rstrip() + "\n"

    def _validate_module(self) -> None:
        for item in self.module.items:
            self._validate_node(item)

    def _validate_node(self, node: IRNode) -> None:
        if isinstance(node, IRStruct):
            if node.generic_params:
                raise LLVMEmissionError("LLVM struct pilot does not support generic structs", node.span)
            for field in node.fields:
                if field.type.name not in ("int", "int64", "float", "float64", "bool"):
                    raise LLVMEmissionError(
                        f"LLVM struct pilot requires scalar fields; field '{field.name}' has type '{field.type}'",
                        node.span,
                    )
                self._check_scalar_type(field.type, node.span, f"Struct field '{field.name}'")
        elif isinstance(node, IRFunction):
            if node.return_type.name == "Array":
                raise LLVMEmissionError("LLVM array pilot does not support Array return values yet", node.span)
            self._check_scalar_type(node.return_type, node.span, "Function return")
            for param in node.params:
                self._check_scalar_type(param.type, param.default.span if param.default else node.span, "Parameter")
            for stmt in node.body:
                self._validate_node(stmt)
        elif isinstance(node, (IRVarDecl, IRAssign, IRExprStatement, IRReturn, IRIf, IRWhile, IRFor, IRBreak, IRContinue)):
            if isinstance(node, IRVarDecl):
                self._check_scalar_type(node.type, node.span, "Variable")
                if node.type.name == "Array" and not isinstance(node.expr, (IRArray, IRReference)):
                    raise LLVMEmissionError(
                        "LLVM array locals must be initialized from an array literal or local Array value",
                        node.span,
                    )
                self._validate_expr(node.expr)
            elif isinstance(node, IRAssign):
                self._validate_expr(node.target)
                self._validate_expr(node.expr)
            elif isinstance(node, IRExprStatement):
                self._validate_expr(node.expr)
            elif isinstance(node, IRReturn):
                if node.expr is not None:
                    self._validate_expr(node.expr)
            elif isinstance(node, IRIf):
                self._validate_expr(node.condition)
                for s in node.then_branch:
                    self._validate_node(s)
                for cond, branch in node.elif_branches:
                    self._validate_expr(cond)
                    for s in branch:
                        self._validate_node(s)
                if node.else_branch is not None:
                    for s in node.else_branch:
                        self._validate_node(s)
            elif isinstance(node, IRWhile):
                self._validate_expr(node.condition)
                for s in node.body:
                    self._validate_node(s)
            elif isinstance(node, IRFor):
                if node.collection_expr is None or node.collection_expr.type.name != "Array":
                    raise LLVMEmissionError(
                        "LLVM aggregate pilot currently supports only for-in Array loops",
                        node.span,
                    )
                self._array_element_llvm_type(node.collection_expr.type, node.span)
                self._validate_expr(node.collection_expr)
                for s in node.body:
                    self._validate_node(s)
        else:
            raise LLVMEmissionError(
                f"LLVM scalar emitter does not support node '{type(node).__name__}'",
                getattr(node, "span", SourceSpan("<llvm>", 1, 1)),
            )

    def _validate_expr(self, expr: IRExpr) -> None:
        if isinstance(expr, IRLiteral):
            if not isinstance(expr.value, (int, float, bool, str)):
                raise LLVMEmissionError(
                    f"LLVM scalar emitter does not support literal of type '{type(expr.value).__name__}'",
                    expr.span,
                )
        elif isinstance(expr, IRReference):
            pass
        elif isinstance(expr, IRBinary):
            self._validate_expr(expr.left)
            self._validate_expr(expr.right)
        elif isinstance(expr, IRUnary):
            self._validate_expr(expr.expr)
        elif isinstance(expr, IRConditional):
            self._validate_expr(expr.condition)
            self._validate_expr(expr.then_expr)
            self._validate_expr(expr.else_expr)
        elif isinstance(expr, IRCall):
            if expr.receiver is not None:
                if not (
                    expr.receiver.type.name == "Array"
                    and expr.callee in ("len", "length", "size")
                    and not expr.args
                ):
                    raise LLVMEmissionError(
                        "LLVM aggregate pilot supports only zero-argument Array len/length/size methods",
                        expr.span,
                    )
                self._validate_expr(expr.receiver)
            for arg in expr.args:
                self._validate_expr(arg)
        elif isinstance(expr, IRMemberAccess):
            if expr.safe:
                raise LLVMEmissionError("LLVM struct pilot does not support safe member access", expr.span)
            self._validate_expr(expr.obj)
            struct = self.struct_map.get(expr.obj.type.name)
            if struct is None or expr.member not in {field.name for field in struct.fields}:
                raise LLVMEmissionError(
                    f"LLVM struct pilot cannot resolve member '{expr.member}' on '{expr.obj.type}'",
                    expr.span,
                )
        elif isinstance(expr, IRArray):
            self._array_element_llvm_type(expr.type, expr.span)
            for element in expr.elements:
                self._validate_expr(element)
        elif isinstance(expr, IRIndexAccess):
            if expr.obj.type.name != "Array":
                raise LLVMEmissionError("LLVM array pilot only supports Array indexing", expr.span)
            self._array_element_llvm_type(expr.obj.type, expr.span)
            self._validate_expr(expr.obj)
            self._validate_expr(expr.index)
        else:
            raise LLVMEmissionError(
                f"LLVM scalar emitter does not support expression '{type(expr).__name__}'",
                expr.span,
            )

    def _check_scalar_type(self, t: IRType, span: SourceSpan, context: str) -> None:
        if t.name == "Array":
            self._array_element_llvm_type(t, span)
        elif t.name not in ("int", "int64", "float", "float64", "bool", "void", "string", "any") and t.name not in self.struct_map:
            raise LLVMEmissionError(f"LLVM scalar emitter does not support {context} type '{t}'", span)
        if t.optional or t.pointer:
            raise LLVMEmissionError(f"LLVM scalar emitter does not support optional/pointer type '{t}'", span)

    def _has_return_with_expr(self, stmts: Tuple[IRStatement, ...]) -> bool:
        for stmt in stmts:
            if isinstance(stmt, IRReturn) and stmt.expr is not None:
                return True
            if isinstance(stmt, IRIf):
                if self._has_return_with_expr(stmt.then_branch):
                    return True
                for _, branch in stmt.elif_branches:
                    if self._has_return_with_expr(branch):
                        return True
                if stmt.else_branch and self._has_return_with_expr(stmt.else_branch):
                    return True
            if isinstance(stmt, IRWhile):
                if self._has_return_with_expr(stmt.body):
                    return True
        return False

    def _is_void_return(self, fn: IRFunction) -> bool:
        if fn.return_type.name == "void":
            return True
        if fn.return_type.name in ("any", "unknown"):
            return not self._has_return_with_expr(fn.body)
        return False

    def _llvm_type(self, t: IRType) -> str:
        name = t.name
        if name in ("int", "int64"):
            return "i64"
        if name in ("float", "float64"):
            return "double"
        if name == "bool":
            return "i1"
        if name == "void":
            return "void"
        if name == "string":
            return "ptr"
        if name == "any":
            return "i64"
        if name == "Array":
            element_type = self._array_element_llvm_type(t, SourceSpan("<llvm>", 1, 1))
            self.array_types.add(element_type)
            return self._llvm_array_type_name(element_type)
        if name in self.struct_map:
            return self._llvm_struct_type(name)
        raise LLVMEmissionError(f"Unsupported IR type '{t}' in LLVM emission", SourceSpan("<llvm>", 1, 1))

    def _llvm_struct_type(self, name: str) -> str:
        return f"%nyx.struct.{self._identifier(name)}"

    @staticmethod
    def _llvm_array_type_name(element_type: str) -> str:
        suffix = {"i64": "i64", "double": "f64", "i1": "bool"}[element_type]
        return f"%nyx.array.{suffix}"

    def _array_element_llvm_type(self, array_type: IRType, span: SourceSpan) -> str:
        if array_type.name != "Array" or len(array_type.arguments) != 1:
            raise LLVMEmissionError(f"Malformed Array type '{array_type}'", span)
        element = array_type.arguments[0]
        if element.name in ("int", "int64") and not element.optional and not element.pointer:
            return "i64"
        if element.name in ("float", "float64") and not element.optional and not element.pointer:
            return "double"
        if element.name == "bool" and not element.optional and not element.pointer:
            return "i1"
        raise LLVMEmissionError(
            f"LLVM array pilot supports only Array<int>, Array<float>, and Array<bool>; found '{array_type}'",
            span,
        )

    @staticmethod
    def _array_element_size(element_type: str) -> int:
        return {"i64": 8, "double": 8, "i1": 1}[element_type]

    def _temp(self, prefix: str = "t") -> str:
        self.temp_counter += 1
        return f"%{prefix}.{self.temp_counter}"

    def _label(self, prefix: str = "bb") -> str:
        self.label_counter += 1
        return f"{prefix}.{self.label_counter}"

    def _alloc_string(self, text: str) -> str:
        if text in self.string_map:
            return self.string_map[text]
        raw_bytes = text.encode("utf-8") + b"\0"
        escaped_parts = []
        for b in raw_bytes:
            if 32 <= b <= 126 and b not in (ord('"'), ord('\\')):
                escaped_parts.append(chr(b))
            else:
                escaped_parts.append(f"\\{b:02X}")
        esc_str = "".join(escaped_parts)
        gname = f"__str_{len(self.string_constants)}"
        self.string_constants.append((gname, esc_str, len(raw_bytes)))
        self.string_map[text] = gname
        return gname

    def _emit_function(self, fn: IRFunction) -> str:
        self.blocks = []
        self.entry_allocas = []
        self.local_ptrs = {}
        self.array_locals = {}
        self.loop_stack = []
        self.temp_counter = 0
        self.label_counter = 0

        fn_name = self.symbol_names.get(fn.symbol, self._identifier(fn.name))
        is_void = self._is_void_return(fn)
        ret_type = "void" if is_void else self._llvm_type(fn.return_type)

        params_decl: List[str] = []
        entry_block = BasicBlock("entry")
        self.blocks.append(entry_block)

        for param in fn.params:
            ptype = self._llvm_type(param.type)
            arg_name = f"%arg_{self._identifier(param.name)}"
            params_decl.append(f"{ptype} {arg_name}")

            # Entry alloca
            addr_name = f"%alloca_{self._identifier(param.name)}_{len(self.entry_allocas)}"
            self.entry_allocas.append(f"  {addr_name} = alloca {ptype}")
            if param.type.name == "Array":
                element_type = self._array_element_llvm_type(param.type, fn.span)
                length = self._temp("array_param_len")
                source_data = self._temp("array_param_source")
                cloned_data = self._temp("array_param_data")
                byte_length = self._temp("array_param_bytes")
                descriptor_0 = self._temp("array_param_desc")
                descriptor_1 = self._temp("array_param_desc")
                self.entry_allocas.extend(
                    [
                        f"  {length} = extractvalue {ptype} {arg_name}, 0",
                        f"  {source_data} = extractvalue {ptype} {arg_name}, 1",
                        f"  {cloned_data} = alloca {element_type}, i64 {length}",
                        f"  {byte_length} = mul i64 {length}, {self._array_element_size(element_type)}",
                        f"  call void @llvm.memcpy.p0.p0.i64(ptr {cloned_data}, ptr {source_data}, i64 {byte_length}, i1 false)",
                        f"  {descriptor_0} = insertvalue {ptype} poison, i64 {length}, 0",
                        f"  {descriptor_1} = insertvalue {ptype} {descriptor_0}, ptr {cloned_data}, 1",
                        f"  store {ptype} {descriptor_1}, ptr {addr_name}",
                    ]
                )
                self.array_locals[param.symbol] = (addr_name, element_type, length)
            else:
                self.entry_allocas.append(f"  store {ptype} {arg_name}, ptr {addr_name}")
            self.local_ptrs[param.symbol] = (addr_name, ptype)

        current = entry_block
        for stmt in fn.body:
            current = self._emit_statement(stmt, current)

        # Function epilogue
        if not current.terminated:
            if ret_type == "void":
                current.terminate("  ret void")
            else:
                current.terminate("  unreachable")

        header = f"define {ret_type} @{fn_name}({', '.join(params_decl)}) {{"
        return self._render_blocks(header)

    def _emit_main_function(self, top_statements: List[IRStatement]) -> str:
        self.blocks = []
        self.entry_allocas = []
        self.local_ptrs = {}
        self.array_locals = {}
        self.loop_stack = []
        self.temp_counter = 0
        self.label_counter = 0

        entry_block = BasicBlock("entry")
        self.blocks.append(entry_block)

        current = entry_block
        for stmt in top_statements:
            current = self._emit_statement(stmt, current)

        user_main = self.function_map.get("main")
        if user_main is not None:
            if self._is_void_return(user_main):
                current.emit("  call void @_nyx_user_main()")
                current.terminate("  ret i32 0")
            else:
                user_ret_type = self._llvm_type(user_main.return_type)
                if user_ret_type == "i64":
                    r64 = self._temp("user_main_ret")
                    current.emit(f"  {r64} = call i64 @_nyx_user_main()")
                    r32 = self._temp("ret32")
                    current.emit(f"  {r32} = trunc i64 {r64} to i32")
                    current.terminate(f"  ret i32 {r32}")
                else:
                    current.emit(f"  call {user_ret_type} @_nyx_user_main()")
                    current.terminate("  ret i32 0")
        else:
            if not current.terminated:
                current.terminate("  ret i32 0")

        header = "define i32 @main() {"
        return self._render_blocks(header)

    def _render_blocks(self, header: str) -> str:
        lines: List[str] = [header]
        if self.blocks:
            entry_instrs = self.entry_allocas + self.blocks[0].instructions
            self.blocks[0].instructions = entry_instrs

        for b in self.blocks:
            if not b.terminated:
                b.terminate("  unreachable")
            lines.append(f"{b.label}:")
            for inst in b.instructions:
                lines.append(inst)
        lines.append("}")
        return "\n".join(lines)

    def _emit_statement(self, stmt: IRStatement, block: BasicBlock) -> BasicBlock:
        if block.terminated:
            block = BasicBlock(self._label("dead"))
            self.blocks.append(block)

        if isinstance(stmt, IRVarDecl):
            if stmt.type.name == "Array":
                return self._emit_array_var_decl(stmt, block)
            vtype = self._llvm_type(stmt.type)
            clean_name = self._identifier(stmt.name)
            addr_name = f"%alloca_{clean_name}_{self.label_counter}_{len(self.entry_allocas)}"
            self.entry_allocas.append(f"  {addr_name} = alloca {vtype}")
            self.local_ptrs[stmt.symbol] = (addr_name, vtype)

            val, val_type, block = self._emit_expr(stmt.expr, block)
            val = self._coerce(val, val_type, vtype, block)
            block.emit(f"  store {vtype} {val}, ptr {addr_name}")
            return block

        if isinstance(stmt, IRAssign):
            if isinstance(stmt.target, IRIndexAccess):
                element_ptr, element_type, block = self._emit_array_element_ptr(
                    stmt.target.obj,
                    stmt.target.index,
                    block,
                    stmt.span,
                )
                value, value_type, block = self._emit_expr(stmt.expr, block)
                value = self._coerce(value, value_type, element_type, block)
                block.emit(f"  store {element_type} {value}, ptr {element_ptr}")
                return block

            if isinstance(stmt.target, IRReference):
                if stmt.target.type.name == "Array":
                    raise LLVMEmissionError(
                        "LLVM array pilot does not support rebinding an existing Array yet",
                        stmt.span,
                    )
                if stmt.target.symbol not in self.local_ptrs:
                    raise LLVMEmissionError(f"Undefined variable in assignment: {stmt.target.name}", stmt.span)
                addr_name, vtype = self.local_ptrs[stmt.target.symbol]
                val, val_type, block = self._emit_expr(stmt.expr, block)
                val = self._coerce(val, val_type, vtype, block)
                block.emit(f"  store {vtype} {val}, ptr {addr_name}")
                return block

            if isinstance(stmt.target, IRMemberAccess) and isinstance(stmt.target.obj, IRReference):
                owner = stmt.target.obj
                local = self.local_ptrs.get(owner.symbol)
                struct = self.struct_map.get(owner.type.name)
                if local is None or struct is None:
                    raise LLVMEmissionError(
                        f"LLVM struct pilot cannot assign member '{stmt.target.member}' on this value",
                        stmt.span,
                    )
                field_index = next(
                    (index for index, field in enumerate(struct.fields) if field.name == stmt.target.member),
                    None,
                )
                if field_index is None:
                    raise LLVMEmissionError(
                        f"LLVM struct pilot cannot resolve member '{stmt.target.member}' on '{owner.type}'",
                        stmt.span,
                    )
                owner_ptr, owner_ty = local
                field_ty = self._llvm_type(struct.fields[field_index].type)
                field_ptr = self._temp("field_ptr")
                block.emit(
                    f"  {field_ptr} = getelementptr inbounds {owner_ty}, ptr {owner_ptr}, "
                    f"i32 0, i32 {field_index}"
                )
                val, val_type, block = self._emit_expr(stmt.expr, block)
                val = self._coerce(val, val_type, field_ty, block)
                block.emit(f"  store {field_ty} {val}, ptr {field_ptr}")
                return block

            raise LLVMEmissionError(
                f"Assignment target must be a local reference or direct struct member, got {type(stmt.target).__name__}",
                stmt.span,
            )

        if isinstance(stmt, IRExprStatement):
            _, _, block = self._emit_expr(stmt.expr, block)
            return block

        if isinstance(stmt, IRReturn):
            if stmt.expr is not None:
                val, val_type, block = self._emit_expr(stmt.expr, block)
                block.terminate(f"  ret {val_type} {val}")
            else:
                block.terminate("  ret void")
            return block

        if isinstance(stmt, IRBreak):
            if not self.loop_stack:
                raise LLVMEmissionError("Break outside of loop", stmt.span)
            _, exit_lbl = self.loop_stack[-1]
            block.terminate(f"  br label %{exit_lbl}")
            return block

        if isinstance(stmt, IRContinue):
            if not self.loop_stack:
                raise LLVMEmissionError("Continue outside of loop", stmt.span)
            cond_lbl, _ = self.loop_stack[-1]
            block.terminate(f"  br label %{cond_lbl}")
            return block

        if isinstance(stmt, IRFor):
            if stmt.collection_expr is None or stmt.collection_expr.type.name != "Array":
                raise LLVMEmissionError(
                    "LLVM aggregate pilot currently supports only for-in Array loops",
                    stmt.span,
                )

            descriptor, descriptor_type, block = self._emit_expr(stmt.collection_expr, block)
            element_type = self._array_element_llvm_type(stmt.collection_expr.type, stmt.span)
            length = self._temp("for_len")
            data = self._temp("for_data")
            block.emit(f"  {length} = extractvalue {descriptor_type} {descriptor}, 0")
            block.emit(f"  {data} = extractvalue {descriptor_type} {descriptor}, 1")

            index_ptr = f"%alloca_for_index_{self.label_counter}_{len(self.entry_allocas)}"
            value_ptr = f"%alloca_{self._identifier(stmt.var_name)}_{self.label_counter}_{len(self.entry_allocas) + 1}"
            self.entry_allocas.append(f"  {index_ptr} = alloca i64")
            self.entry_allocas.append(f"  {value_ptr} = alloca {element_type}")
            self.local_ptrs[stmt.symbol] = (value_ptr, element_type)
            block.emit(f"  store i64 0, ptr {index_ptr}")

            cond_block = BasicBlock(self._label("for.cond"))
            body_block = BasicBlock(self._label("for.body"))
            step_block = BasicBlock(self._label("for.step"))
            exit_block = BasicBlock(self._label("for.exit"))
            block.terminate(f"  br label %{cond_block.label}")

            self.blocks.append(cond_block)
            index = self._temp("for_index")
            cond_block.emit(f"  {index} = load i64, ptr {index_ptr}")
            has_next = self._temp("for_has_next")
            cond_block.emit(f"  {has_next} = icmp slt i64 {index}, {length}")
            cond_block.terminate(
                f"  br i1 {has_next}, label %{body_block.label}, label %{exit_block.label}"
            )

            self.blocks.append(body_block)
            element_ptr = self._temp("for_element_ptr")
            body_block.emit(
                f"  {element_ptr} = getelementptr inbounds {element_type}, ptr {data}, i64 {index}"
            )
            element = self._temp("for_element")
            body_block.emit(f"  {element} = load {element_type}, ptr {element_ptr}")
            body_block.emit(f"  store {element_type} {element}, ptr {value_ptr}")

            self.loop_stack.append((step_block.label, exit_block.label))
            current = body_block
            for nested in stmt.body:
                current = self._emit_statement(nested, current)
            self.loop_stack.pop()
            if not current.terminated:
                current.terminate(f"  br label %{step_block.label}")

            self.blocks.append(step_block)
            current_index = self._temp("for_step_index")
            step_block.emit(f"  {current_index} = load i64, ptr {index_ptr}")
            next_index = self._temp("for_next_index")
            step_block.emit(f"  {next_index} = add i64 {current_index}, 1")
            step_block.emit(f"  store i64 {next_index}, ptr {index_ptr}")
            step_block.terminate(f"  br label %{cond_block.label}")

            self.blocks.append(exit_block)
            return exit_block

        if isinstance(stmt, IRWhile):
            cond_block = BasicBlock(self._label("while.cond"))
            body_block = BasicBlock(self._label("while.body"))
            exit_block = BasicBlock(self._label("while.exit"))

            block.terminate(f"  br label %{cond_block.label}")

            self.blocks.append(cond_block)
            c_val, c_type, cur_cond = self._emit_expr(stmt.condition, cond_block)
            c_val = self._to_bool(c_val, c_type, cur_cond)
            cur_cond.terminate(f"  br i1 {c_val}, label %{body_block.label}, label %{exit_block.label}")

            self.blocks.append(body_block)
            self.loop_stack.append((cond_block.label, exit_block.label))
            cur = body_block
            for s in stmt.body:
                cur = self._emit_statement(s, cur)
            self.loop_stack.pop()

            if not cur.terminated:
                cur.terminate(f"  br label %{cond_block.label}")

            self.blocks.append(exit_block)
            return exit_block

        if isinstance(stmt, IRIf):
            then_block = BasicBlock(self._label("if.then"))
            merge_block = BasicBlock(self._label("if.merge"))

            elif_blocks: List[Tuple[BasicBlock, BasicBlock]] = []
            for _ in stmt.elif_branches:
                elif_c = BasicBlock(self._label("if.elif.cond"))
                elif_b = BasicBlock(self._label("if.elif.body"))
                elif_blocks.append((elif_c, elif_b))

            else_block = BasicBlock(self._label("if.else")) if stmt.else_branch is not None else None

            cond_val, cond_type, cur_cond = self._emit_expr(stmt.condition, block)
            cond_val = self._to_bool(cond_val, cond_type, cur_cond)

            first_false_lbl = elif_blocks[0][0].label if elif_blocks else (else_block.label if else_block else merge_block.label)
            cur_cond.terminate(f"  br i1 {cond_val}, label %{then_block.label}, label %{first_false_lbl}")

            # Then
            self.blocks.append(then_block)
            cur = then_block
            for s in stmt.then_branch:
                cur = self._emit_statement(s, cur)
            if not cur.terminated:
                cur.terminate(f"  br label %{merge_block.label}")

            # Elifs
            for idx, (c_expr, b_stmts) in enumerate(stmt.elif_branches):
                c_block, b_block = elif_blocks[idx]
                self.blocks.append(c_block)
                cv, ct, cur_c = self._emit_expr(c_expr, c_block)
                cv = self._to_bool(cv, ct, cur_c)
                next_false = elif_blocks[idx + 1][0].label if idx + 1 < len(elif_blocks) else (else_block.label if else_block else merge_block.label)
                cur_c.terminate(f"  br i1 {cv}, label %{b_block.label}, label %{next_false}")

                self.blocks.append(b_block)
                cur = b_block
                for s in b_stmts:
                    cur = self._emit_statement(s, cur)
                if not cur.terminated:
                    cur.terminate(f"  br label %{merge_block.label}")

            # Else
            if else_block is not None:
                self.blocks.append(else_block)
                cur = else_block
                for s in stmt.else_branch:
                    cur = self._emit_statement(s, cur)
                if not cur.terminated:
                    cur.terminate(f"  br label %{merge_block.label}")

            # Merge
            self.blocks.append(merge_block)
            return merge_block

        raise LLVMEmissionError(f"Unsupported statement type '{type(stmt).__name__}'", stmt.span)

    def _emit_array_var_decl(self, stmt: IRVarDecl, block: BasicBlock) -> BasicBlock:
        descriptor_type = self._llvm_type(stmt.type)
        element_type = self._array_element_llvm_type(stmt.type, stmt.span)
        descriptor_ptr = f"%alloca_{self._identifier(stmt.name)}_{self.label_counter}_{len(self.entry_allocas)}"
        self.entry_allocas.append(f"  {descriptor_ptr} = alloca {descriptor_type}")

        if isinstance(stmt.expr, IRArray):
            length = str(len(stmt.expr.elements))
            data_ptr = f"%array_data_{self._identifier(stmt.name)}_{len(self.entry_allocas)}"
            self.entry_allocas.append(f"  {data_ptr} = alloca {element_type}, i64 {length}")
            for index, element in enumerate(stmt.expr.elements):
                value, value_type, block = self._emit_expr(element, block)
                value = self._coerce(value, value_type, element_type, block)
                slot = self._temp("array_slot")
                block.emit(f"  {slot} = getelementptr inbounds {element_type}, ptr {data_ptr}, i64 {index}")
                block.emit(f"  store {element_type} {value}, ptr {slot}")
        elif isinstance(stmt.expr, IRReference):
            source = self.array_locals.get(stmt.expr.symbol)
            if source is None:
                raise LLVMEmissionError(
                    "LLVM array pilot can copy only a local or parameter Array value",
                    stmt.span,
                )
            source_descriptor_ptr, source_element_type, length = source
            if source_element_type != element_type:
                raise LLVMEmissionError("LLVM Array copy element types do not match", stmt.span)
            data_ptr = f"%array_data_{self._identifier(stmt.name)}_{len(self.entry_allocas)}"
            self.entry_allocas.append(f"  {data_ptr} = alloca {element_type}, i64 {length}")
            source_descriptor = self._temp("array_source")
            block.emit(f"  {source_descriptor} = load {descriptor_type}, ptr {source_descriptor_ptr}")
            source_data = self._temp("array_source_data")
            block.emit(f"  {source_data} = extractvalue {descriptor_type} {source_descriptor}, 1")
            byte_length = self._temp("array_copy_bytes")
            block.emit(f"  {byte_length} = mul i64 {length}, {self._array_element_size(element_type)}")
            block.emit(
                f"  call void @llvm.memcpy.p0.p0.i64(ptr {data_ptr}, ptr {source_data}, "
                f"i64 {byte_length}, i1 false)"
            )
        else:
            raise LLVMEmissionError(
                "LLVM array locals must be initialized from an array literal or local Array value",
                stmt.span,
            )

        descriptor_0 = self._temp("array_desc")
        block.emit(f"  {descriptor_0} = insertvalue {descriptor_type} poison, i64 {length}, 0")
        descriptor_1 = self._temp("array_desc")
        block.emit(f"  {descriptor_1} = insertvalue {descriptor_type} {descriptor_0}, ptr {data_ptr}, 1")
        block.emit(f"  store {descriptor_type} {descriptor_1}, ptr {descriptor_ptr}")
        self.local_ptrs[stmt.symbol] = (descriptor_ptr, descriptor_type)
        self.array_locals[stmt.symbol] = (descriptor_ptr, element_type, length)
        return block

    def _emit_array_element_ptr(
        self,
        array_expr: IRExpr,
        index_expr: IRExpr,
        block: BasicBlock,
        span: SourceSpan,
    ) -> Tuple[str, str, BasicBlock]:
        if array_expr.type.name != "Array":
            raise LLVMEmissionError("LLVM array indexing requires an Array value", span)
        element_type = self._array_element_llvm_type(array_expr.type, span)
        descriptor_type = self._llvm_type(array_expr.type)
        descriptor, actual_type, block = self._emit_expr(array_expr, block)
        if actual_type != descriptor_type:
            raise LLVMEmissionError("LLVM Array descriptor type mismatch", span)
        index, index_type, block = self._emit_expr(index_expr, block)
        index = self._coerce(index, index_type, "i64", block)
        length = self._temp("array_len")
        block.emit(f"  {length} = extractvalue {descriptor_type} {descriptor}, 0")
        block.emit(f"  call void @__nyx_array_check(i64 {index}, i64 {length})")
        data = self._temp("array_data")
        block.emit(f"  {data} = extractvalue {descriptor_type} {descriptor}, 1")
        element_ptr = self._temp("array_element")
        block.emit(f"  {element_ptr} = getelementptr inbounds {element_type}, ptr {data}, i64 {index}")
        return element_ptr, element_type, block

    def _emit_expr(self, expr: IRExpr, block: BasicBlock) -> Tuple[str, str, BasicBlock]:
        if isinstance(expr, IRLiteral):
            if isinstance(expr.value, bool):
                return "1" if expr.value else "0", "i1", block
            if isinstance(expr.value, int):
                return str(expr.value), "i64", block
            if isinstance(expr.value, float):
                formatted = repr(expr.value)
                if "." not in formatted and "e" not in formatted and "E" not in formatted:
                    formatted += ".0"
                return formatted, "double", block
            if isinstance(expr.value, str):
                gname = self._alloc_string(expr.value)
                return f"@{gname}", "ptr", block
            return "0", "i64", block

        if isinstance(expr, IRReference):
            if expr.symbol not in self.local_ptrs:
                raise LLVMEmissionError(f"Undefined symbol '{expr.name}'", expr.span)
            addr_name, vtype = self.local_ptrs[expr.symbol]
            res = self._temp("val")
            block.emit(f"  {res} = load {vtype}, ptr {addr_name}")
            return res, vtype, block

        if isinstance(expr, IRMemberAccess):
            obj_val, obj_ty, block = self._emit_expr(expr.obj, block)
            struct = self.struct_map.get(expr.obj.type.name)
            if struct is None:
                raise LLVMEmissionError(
                    f"LLVM struct pilot cannot read member '{expr.member}' from '{expr.obj.type}'",
                    expr.span,
                )
            field_index = next(
                (index for index, field in enumerate(struct.fields) if field.name == expr.member),
                None,
            )
            if field_index is None:
                raise LLVMEmissionError(
                    f"LLVM struct pilot cannot resolve member '{expr.member}' on '{expr.obj.type}'",
                    expr.span,
                )
            field_ty = self._llvm_type(struct.fields[field_index].type)
            result = self._temp("field")
            block.emit(f"  {result} = extractvalue {obj_ty} {obj_val}, {field_index}")
            return result, field_ty, block

        if isinstance(expr, IRIndexAccess):
            element_ptr, element_type, block = self._emit_array_element_ptr(
                expr.obj,
                expr.index,
                block,
                expr.span,
            )
            result = self._temp("array_value")
            block.emit(f"  {result} = load {element_type}, ptr {element_ptr}")
            return result, element_type, block

        if isinstance(expr, IRArray):
            raise LLVMEmissionError(
                "LLVM array literals are currently supported only as direct local initializers",
                expr.span,
            )

        if isinstance(expr, IRUnary):
            inner_val, inner_ty, block = self._emit_expr(expr.expr, block)
            if expr.op in ("-", "+"):
                if inner_ty == "i64":
                    if expr.op == "-":
                        res = self._temp("neg")
                        block.emit(f"  {res} = sub i64 0, {inner_val}")
                        return res, "i64", block
                    return inner_val, "i64", block
                elif inner_ty == "double":
                    if expr.op == "-":
                        res = self._temp("fneg")
                        block.emit(f"  {res} = fneg double {inner_val}")
                        return res, "double", block
                    return inner_val, "double", block
            if expr.op in ("!", "not"):
                b_val = self._to_bool(inner_val, inner_ty, block)
                res = self._temp("not")
                block.emit(f"  {res} = xor i1 {b_val}, 1")
                return res, "i1", block
            if expr.op == "~":
                res = self._temp("bitnot")
                block.emit(f"  {res} = xor i64 {inner_val}, -1")
                return res, "i64", block
            return inner_val, inner_ty, block

        if isinstance(expr, IRBinary):
            # Short-circuit logical and / or
            if expr.op in ("and", "&&"):
                return self._emit_short_circuit_and(expr.left, expr.right, block)
            if expr.op in ("or", "||"):
                return self._emit_short_circuit_or(expr.left, expr.right, block)

            left_val, left_ty, block = self._emit_expr(expr.left, block)
            right_val, right_ty, block = self._emit_expr(expr.right, block)

            is_float = left_ty == "double" or right_ty == "double"
            if is_float:
                left_val = self._coerce(left_val, left_ty, "double", block)
                right_val = self._coerce(right_val, right_ty, "double", block)
                ty = "double"
            else:
                left_val = self._coerce(left_val, left_ty, "i64", block)
                right_val = self._coerce(right_val, right_ty, "i64", block)
                ty = "i64"

            if expr.op == "+":
                res = self._temp("add")
                opc = "fadd" if is_float else "add"
                block.emit(f"  {res} = {opc} {ty} {left_val}, {right_val}")
                return res, ty, block
            if expr.op == "-":
                res = self._temp("sub")
                opc = "fsub" if is_float else "sub"
                block.emit(f"  {res} = {opc} {ty} {left_val}, {right_val}")
                return res, ty, block
            if expr.op == "*":
                res = self._temp("mul")
                opc = "fmul" if is_float else "mul"
                block.emit(f"  {res} = {opc} {ty} {left_val}, {right_val}")
                return res, ty, block
            if expr.op == "/":
                if is_float:
                    res = self._temp("fdiv")
                    block.emit(f"  {res} = fdiv double {left_val}, {right_val}")
                    return res, "double", block
                res = self._temp("div")
                block.emit(f"  {res} = call i64 @__nyx_i64_div(i64 {left_val}, i64 {right_val})")
                return res, "i64", block
            if expr.op == "%":
                if is_float:
                    res = self._temp("fmod")
                    block.emit(f"  {res} = call double @fmod(double {left_val}, double {right_val})")
                    return res, "double", block
                res = self._temp("mod")
                block.emit(f"  {res} = call i64 @__nyx_i64_mod(i64 {left_val}, i64 {right_val})")
                return res, "i64", block
            if expr.op == "<<":
                s_reg = self._temp("shift")
                block.emit(f"  {s_reg} = and i64 {right_val}, 63")
                res = self._temp("shl")
                block.emit(f"  {res} = shl i64 {left_val}, {s_reg}")
                return res, "i64", block
            if expr.op == ">>":
                s_reg = self._temp("shift")
                block.emit(f"  {s_reg} = and i64 {right_val}, 63")
                res = self._temp("ashr")
                block.emit(f"  {res} = ashr i64 {left_val}, {s_reg}")
                return res, "i64", block
            if expr.op in ("&", "|", "^"):
                res = self._temp("bitwise")
                opc = {"&": "and", "|": "or", "^": "xor"}[expr.op]
                block.emit(f"  {res} = {opc} i64 {left_val}, {right_val}")
                return res, "i64", block
            if expr.op in ("==", "!=", "<", "<=", ">", ">="):
                res = self._temp("cmp")
                if is_float:
                    fpred = {
                        "==": "oeq", "!=": "one", "<": "olt",
                        "<=": "ole", ">": "ogt", ">=": "oge"
                    }[expr.op]
                    block.emit(f"  {res} = fcmp {fpred} double {left_val}, {right_val}")
                else:
                    ipred = {
                        "==": "eq", "!=": "ne", "<": "slt",
                        "<=": "sle", ">": "sgt", ">=": "sge"
                    }[expr.op]
                    block.emit(f"  {res} = icmp {ipred} i64 {left_val}, {right_val}")
                return res, "i1", block

            raise LLVMEmissionError(f"Unsupported binary operator '{expr.op}'", expr.span)

        if isinstance(expr, IRConditional):
            cond_val, cond_ty, block = self._emit_expr(expr.condition, block)
            cond_val = self._to_bool(cond_val, cond_ty, block)

            res_ty = self._llvm_type(expr.type)
            addr_res = f"%alloca_cond_{self.label_counter}_{len(self.entry_allocas)}"
            self.entry_allocas.append(f"  {addr_res} = alloca {res_ty}")

            then_block = BasicBlock(self._label("cond.then"))
            else_block = BasicBlock(self._label("cond.else"))
            merge_block = BasicBlock(self._label("cond.merge"))

            block.terminate(f"  br i1 {cond_val}, label %{then_block.label}, label %{else_block.label}")

            self.blocks.append(then_block)
            tv, tt, cur_then = self._emit_expr(expr.then_expr, then_block)
            tv = self._coerce(tv, tt, res_ty, cur_then)
            cur_then.emit(f"  store {res_ty} {tv}, ptr {addr_res}")
            cur_then.terminate(f"  br label %{merge_block.label}")

            self.blocks.append(else_block)
            ev, et, cur_else = self._emit_expr(expr.else_expr, else_block)
            ev = self._coerce(ev, et, res_ty, cur_else)
            cur_else.emit(f"  store {res_ty} {ev}, ptr {addr_res}")
            cur_else.terminate(f"  br label %{merge_block.label}")

            self.blocks.append(merge_block)
            final_res = self._temp("cond_val")
            merge_block.emit(f"  {final_res} = load {res_ty}, ptr {addr_res}")
            return final_res, res_ty, merge_block

        if isinstance(expr, IRCall):
            if (
                expr.receiver is not None
                and expr.receiver.type.name == "Array"
                and expr.callee in ("len", "length", "size")
                and not expr.args
            ):
                descriptor, descriptor_type, block = self._emit_expr(expr.receiver, block)
                length = self._temp("array_len")
                block.emit(f"  {length} = extractvalue {descriptor_type} {descriptor}, 0")
                return length, "i64", block

            if expr.callee == "print":
                for index, argument in enumerate(expr.args):
                    if index:
                        block.emit("  call i32 (ptr, ...) @printf(ptr @__nyx_space)")
                    arg_val, arg_ty, block = self._emit_expr(argument, block)
                    writer = {
                        "i64": "nyx_write_i64",
                        "double": "nyx_write_f64",
                        "i1": "nyx_write_bool",
                        "ptr": "nyx_write_str",
                    }.get(arg_ty)
                    if writer is None:
                        raise LLVMEmissionError(
                            f"LLVM print does not support value type '{arg_ty}'",
                            argument.span,
                        )
                    block.emit(f"  call void @{writer}({arg_ty} {arg_val})")
                block.emit("  call i32 (ptr, ...) @printf(ptr @__nyx_newline)")
                return "", "void", block

            struct = self.struct_map.get(expr.callee)
            if struct is not None and expr.callee_symbol == struct.symbol:
                struct_ty = self._llvm_struct_type(struct.name)
                aggregate = "poison"
                for index, (argument, field) in enumerate(zip(expr.args, struct.fields)):
                    arg_val, arg_ty, block = self._emit_expr(argument, block)
                    field_ty = self._llvm_type(field.type)
                    arg_val = self._coerce(arg_val, arg_ty, field_ty, block)
                    inserted = self._temp("struct")
                    block.emit(
                        f"  {inserted} = insertvalue {struct_ty} {aggregate}, "
                        f"{field_ty} {arg_val}, {index}"
                    )
                    aggregate = inserted
                return aggregate, struct_ty, block

            target_name = self.symbol_names.get(expr.callee_symbol, self._identifier(expr.callee))
            target_fn = self.function_map.get(expr.callee)

            arg_pairs: List[str] = []
            for idx, a in enumerate(expr.args):
                av, at, block = self._emit_expr(a, block)
                if target_fn and idx < len(target_fn.params):
                    expected_ty = self._llvm_type(target_fn.params[idx].type)
                    av = self._coerce(av, at, expected_ty, block)
                    at = expected_ty
                arg_pairs.append(f"{at} {av}")

            ret_ty = self._llvm_type(target_fn.return_type) if target_fn else "i64"
            if ret_ty == "void":
                block.emit(f"  call void @{target_name}({', '.join(arg_pairs)})")
                return "", "void", block
            res = self._temp("call")
            block.emit(f"  {res} = call {ret_ty} @{target_name}({', '.join(arg_pairs)})")
            return res, ret_ty, block

        raise LLVMEmissionError(f"Unsupported expression '{type(expr).__name__}'", expr.span)

    def _emit_short_circuit_and(self, left: IRExpr, right: IRExpr, block: BasicBlock) -> Tuple[str, str, BasicBlock]:
        addr_sc = f"%alloca_sc_{self.label_counter}_{len(self.entry_allocas)}"
        self.entry_allocas.append(f"  {addr_sc} = alloca i1")

        lv, lt, block = self._emit_expr(left, block)
        lv = self._to_bool(lv, lt, block)
        block.emit(f"  store i1 {lv}, ptr {addr_sc}")

        rhs_block = BasicBlock(self._label("sc.rhs"))
        done_block = BasicBlock(self._label("sc.done"))

        block.terminate(f"  br i1 {lv}, label %{rhs_block.label}, label %{done_block.label}")

        self.blocks.append(rhs_block)
        rv, rt, cur_rhs = self._emit_expr(right, rhs_block)
        rv = self._to_bool(rv, rt, cur_rhs)
        cur_rhs.emit(f"  store i1 {rv}, ptr {addr_sc}")
        cur_rhs.terminate(f"  br label %{done_block.label}")

        self.blocks.append(done_block)
        res = self._temp("sc_res")
        done_block.emit(f"  {res} = load i1, ptr {addr_sc}")
        return res, "i1", done_block

    def _emit_short_circuit_or(self, left: IRExpr, right: IRExpr, block: BasicBlock) -> Tuple[str, str, BasicBlock]:
        addr_sc = f"%alloca_sc_{self.label_counter}_{len(self.entry_allocas)}"
        self.entry_allocas.append(f"  {addr_sc} = alloca i1")

        lv, lt, block = self._emit_expr(left, block)
        lv = self._to_bool(lv, lt, block)
        block.emit(f"  store i1 {lv}, ptr {addr_sc}")

        rhs_block = BasicBlock(self._label("sc.rhs"))
        done_block = BasicBlock(self._label("sc.done"))

        block.terminate(f"  br i1 {lv}, label %{done_block.label}, label %{rhs_block.label}")

        self.blocks.append(rhs_block)
        rv, rt, cur_rhs = self._emit_expr(right, rhs_block)
        rv = self._to_bool(rv, rt, cur_rhs)
        cur_rhs.emit(f"  store i1 {rv}, ptr {addr_sc}")
        cur_rhs.terminate(f"  br label %{done_block.label}")

        self.blocks.append(done_block)
        res = self._temp("sc_res")
        done_block.emit(f"  {res} = load i1, ptr {addr_sc}")
        return res, "i1", done_block

    def _to_bool(self, val: str, ty: str, block: BasicBlock) -> str:
        if ty == "i1":
            return val
        if ty == "i64":
            res = self._temp("tobool")
            block.emit(f"  {res} = icmp ne i64 {val}, 0")
            return res
        if ty == "double":
            res = self._temp("tobool")
            block.emit(f"  {res} = fcmp one double {val}, 0.0")
            return res
        return val

    def _coerce(self, val: str, from_ty: str, to_ty: str, block: BasicBlock) -> str:
        if from_ty == to_ty:
            return val
        if from_ty == "i64" and to_ty == "double":
            res = self._temp("conv")
            block.emit(f"  {res} = sitofp i64 {val} to double")
            return res
        if from_ty == "double" and to_ty == "i64":
            res = self._temp("conv")
            block.emit(f"  {res} = fptosi double {val} to i64")
            return res
        if from_ty == "i1" and to_ty == "i64":
            res = self._temp("conv")
            block.emit(f"  {res} = zext i1 {val} to i64")
            return res
        if from_ty == "i64" and to_ty == "i1":
            res = self._temp("conv")
            block.emit(f"  {res} = icmp ne i64 {val}, 0")
            return res
        return val

    @staticmethod
    def _identifier(name: str) -> str:
        clean = _IDENTIFIER_CHARS.sub("_", name)
        if not clean:
            clean = "_nyx_var"
        if clean[0].isdigit():
            clean = "_" + clean
        return clean


def emit_llvm(module: IRModule) -> str:
    """Convenience entry point for LLVM IR emission."""
    return LLVMScalarEmitter(module).emit()
