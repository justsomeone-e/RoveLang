"""Experimental C17 native scalar emitter for Rove HIR.

Consumes verified IRModule and emits standard C17 code for scalar primitives
(int64_t, double, bool, void), wrapping signed 64-bit integer arithmetic,
safe division, scalar control flow, and direct calls.

Rejects all non-scalar constructs (arrays, structs, exceptions, tasks, closures).
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Optional, Set, Tuple

from src.ir.model import (
    IRAssign,
    IRBinary,
    IRBreak,
    IRCall,
    IRConditional,
    IRContinue,
    IRExpr,
    IRExprStatement,
    IRFunction,
    IRIf,
    IRLiteral,
    IRModule,
    IRNode,
    IRParameter,
    IRReference,
    IRReturn,
    IRStatement,
    IRUnary,
    IRVarDecl,
    IRWhile,
    SourceSpan,
)
from src.ir.types import ANY, BOOL, FLOAT, INT, VOID, IRType

_C17_RESERVED = frozenset({
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "inline", "int", "long", "register", "restrict", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while", "_Alignas", "_Alignof",
    "_Atomic", "_Bool", "_Complex", "_Generic", "_Imaginary", "_Noreturn",
    "_Static_assert", "_Thread_local", "main",
})

_IDENTIFIER_CHARS = re.compile(r"[^0-9A-Za-z_]")

_C17_PRELUDE = """/* Rove C17 Experimental Scalar Pilot Runtime */
#define _CRT_SECURE_NO_WARNINGS
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <inttypes.h>

#ifdef _WIN32
#include <windows.h>
#endif

#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-function"
#pragma clang diagnostic ignored "-Wparentheses-equality"
#elif defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#pragma GCC diagnostic ignored "-Wparentheses"
#endif

#if defined(__GNUC__) || defined(__clang__)
#define ROVE_UNUSED __attribute__((unused))
#else
#define ROVE_UNUSED
#endif

static inline ROVE_UNUSED int64_t rove_i64_add(int64_t a, int64_t b) {
    return (int64_t)((uint64_t)a + (uint64_t)b);
}

static inline ROVE_UNUSED int64_t rove_i64_sub(int64_t a, int64_t b) {
    return (int64_t)((uint64_t)a - (uint64_t)b);
}

static inline ROVE_UNUSED int64_t rove_i64_mul(int64_t a, int64_t b) {
    return (int64_t)((uint64_t)a * (uint64_t)b);
}

static inline ROVE_UNUSED int64_t rove_i64_div(int64_t a, int64_t b) {
    if (b == 0) {
        fprintf(stderr, "integer division by zero\\n");
        exit(1);
    }
    if (a == INT64_MIN && b == -1) return INT64_MIN;
    return a / b;
}

static inline ROVE_UNUSED int64_t rove_i64_mod(int64_t a, int64_t b) {
    if (b == 0) {
        fprintf(stderr, "integer division by zero\\n");
        exit(1);
    }
    if (a == INT64_MIN && b == -1) return 0;
    return a % b;
}

static inline ROVE_UNUSED int64_t rove_i64_shl(int64_t a, int64_t b) {
    uint64_t shift = ((uint64_t)b) & 63U;
    return (int64_t)((uint64_t)a << shift);
}

static inline ROVE_UNUSED int64_t rove_i64_shr(int64_t a, int64_t b) {
    uint64_t shift = ((uint64_t)b) & 63U;
    return a >> shift;
}

static inline ROVE_UNUSED int64_t rove_i64_neg(int64_t a) {
    return (int64_t)(-(uint64_t)a);
}

static inline ROVE_UNUSED void rove_print_i64(int64_t v) {
    printf("%" PRId64 "\\n", v);
}

static inline ROVE_UNUSED void rove_print_f64(double v) {
    if (v == (double)(int64_t)v) {
        printf("%.1f\\n", v);
    } else {
        printf("%.16g\\n", v);
    }
}

static inline ROVE_UNUSED void rove_print_bool(bool v) {
    printf("%s\\n", v ? "true" : "false");
}

static inline ROVE_UNUSED void rove_print_str(const char* v) {
    printf("%s\\n", v);
}
"""


class C17EmissionError(ValueError):
    """Raised when the C17 scalar pilot encounters unsupported HIR constructs."""

    def __init__(self, message: str, span: SourceSpan):
        self.message = message
        self.span = span
        super().__init__(f"{span.source}:{span.line}:{span.column}: {message}")


class C17ScalarEmitter:
    """Emits clean C17 source from verified scalar Rove HIR."""

    def __init__(self, module: IRModule):
        self.module = module
        self.symbol_names: Dict[str, str] = {}
        self.function_map: Dict[str, IRFunction] = {}
        self.counter = 0

    def emit(self) -> str:
        self._validate_module()

        functions = [item for item in self.module.items if isinstance(item, IRFunction)]
        top_statements = [item for item in self.module.items if isinstance(item, IRStatement)]

        # Register functions
        for fn in functions:
            preferred = "_rove_user_main" if fn.name == "main" else fn.name
            emitted = self._identifier(preferred)
            self.symbol_names[fn.symbol] = emitted
            self.function_map[fn.name] = fn

        lines: List[str] = [_C17_PRELUDE]

        # Forward declarations of functions
        if functions:
            lines.append("/* Function Prototypes */")
            for fn in functions:
                lines.append(f"{self._function_prototype(fn)};")
            lines.append("")

        # Function implementations
        if functions:
            lines.append("/* Function Definitions */")
            for fn in functions:
                lines.extend(self._emit_function(fn))
                lines.append("")

        # Main function
        lines.append("int main(void) {")
        lines.append("#ifdef _WIN32")
        lines.append("    SetConsoleOutputCP(65001);")
        lines.append("    SetConsoleCP(65001);")
        lines.append("#endif")

        for stmt in top_statements:
            lines.extend(self._emit_statement(stmt, indent=1))

        user_main = self.function_map.get("main")
        if user_main is not None:
            if self._is_void_return(user_main):
                lines.append(f"    {self._symbol(user_main.symbol, 'main')}();")
                lines.append("    return 0;")
            else:
                lines.append(f"    return (int){self._symbol(user_main.symbol, 'main')}();")
        else:
            lines.append("    return 0;")

        lines.append("}")
        return "\n".join(lines).rstrip() + "\n"

    def _validate_module(self) -> None:
        """Ensure all nodes and types are supported scalar primitives."""
        for item in self.module.items:
            self._validate_node(item)

    def _validate_node(self, node: IRNode) -> None:
        if isinstance(node, IRFunction):
            self._check_scalar_type(node.return_type, node.span, "Function return")
            for param in node.params:
                self._check_scalar_type(param.type, param.default.span if param.default else node.span, "Parameter")
            for stmt in node.body:
                self._validate_node(stmt)
        elif isinstance(node, (IRVarDecl, IRAssign, IRExprStatement, IRReturn, IRIf, IRWhile, IRBreak, IRContinue)):
            if isinstance(node, IRVarDecl):
                self._check_scalar_type(node.type, node.span, "Variable")
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
        else:
            raise C17EmissionError(
                f"C17 scalar pilot does not support node '{type(node).__name__}'",
                getattr(node, "span", SourceSpan("<c17>", 1, 1)),
            )

    def _validate_expr(self, expr: IRExpr) -> None:
        if isinstance(expr, IRLiteral):
            if not isinstance(expr.value, (int, float, bool, str)):
                raise C17EmissionError(
                    f"C17 scalar pilot does not support literal of type '{type(expr.value).__name__}'",
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
                raise C17EmissionError("C17 scalar pilot does not support method calls with receivers", expr.span)
            for arg in expr.args:
                self._validate_expr(arg)
        else:
            raise C17EmissionError(
                f"C17 scalar pilot does not support expression '{type(expr).__name__}'",
                expr.span,
            )

    def _check_scalar_type(self, t: IRType, span: SourceSpan, context: str) -> None:
        if t.name not in ("int", "int64", "float", "float64", "bool", "void", "string", "any"):
            raise C17EmissionError(f"C17 scalar pilot does not support {context} type '{t}'", span)
        if t.optional or t.pointer:
            raise C17EmissionError(f"C17 scalar pilot does not support optional/pointer type '{t}'", span)

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
        if fn.return_type.name == "any":
            return not self._has_return_with_expr(fn.body)
        return False

    def _c_type(self, t: IRType) -> str:
        if t.name in ("int", "int64"):
            return "int64_t"
        if t.name in ("float", "float64"):
            return "double"
        if t.name == "bool":
            return "bool"
        if t.name == "void":
            return "void"
        if t.name == "string":
            return "const char*"
        return "int64_t"

    def _function_prototype(self, fn: IRFunction) -> str:
        if self._is_void_return(fn):
            ret = "void"
        else:
            ret = self._c_type(fn.return_type)
        name = self._symbol(fn.symbol, fn.name)
        if not fn.params:
            return f"static {ret} {name}(void)"
        params = ", ".join(
            f"{self._c_type(param.type)} {self._parameter_symbol(param.symbol, param.name)}"
            for param in fn.params
        )
        return f"static {ret} {name}({params})"

    def _emit_function(self, fn: IRFunction) -> List[str]:
        prototype = self._function_prototype(fn)
        lines = [f"{prototype} {{"]
        for stmt in fn.body:
            lines.extend(self._emit_statement(stmt, indent=1))
        if not self._is_void_return(fn):
            if not fn.body or not isinstance(fn.body[-1], IRReturn):
                lines.append("    return 0;")
        lines.append("}")
        return lines

    def _emit_statement(self, stmt: IRStatement, indent: int) -> List[str]:
        pad = "    " * indent
        lines: List[str] = []

        if isinstance(stmt, IRVarDecl):
            c_type = self._c_type(stmt.type)
            name = self._symbol(stmt.symbol, stmt.name)
            expr = self._emit_expr(stmt.expr)
            const_kw = "const " if stmt.is_const else ""
            lines.append(f"{pad}{const_kw}{c_type} {name} = {expr};")

        elif isinstance(stmt, IRAssign):
            target = self._emit_expr(stmt.target)
            expr = self._emit_expr(stmt.expr)
            lines.append(f"{pad}{target} = {expr};")

        elif isinstance(stmt, IRExprStatement):
            expr = self._emit_expr(stmt.expr)
            lines.append(f"{pad}{expr};")

        elif isinstance(stmt, IRReturn):
            if stmt.expr is not None:
                expr = self._emit_expr(stmt.expr)
                lines.append(f"{pad}return {expr};")
            else:
                lines.append(f"{pad}return;")

        elif isinstance(stmt, IRBreak):
            lines.append(f"{pad}break;")

        elif isinstance(stmt, IRContinue):
            lines.append(f"{pad}continue;")

        elif isinstance(stmt, IRWhile):
            cond = self._emit_condition(stmt.condition)
            lines.append(f"{pad}while ({cond}) {{")
            for s in stmt.body:
                lines.extend(self._emit_statement(s, indent + 1))
            lines.append(f"{pad}}}")

        elif isinstance(stmt, IRIf):
            cond = self._emit_condition(stmt.condition)
            lines.append(f"{pad}if ({cond}) {{")
            for s in stmt.then_branch:
                lines.extend(self._emit_statement(s, indent + 1))
            for elif_cond, elif_body in stmt.elif_branches:
                c = self._emit_condition(elif_cond)
                lines.append(f"{pad}}} else if ({c}) {{")
                for s in elif_body:
                    lines.extend(self._emit_statement(s, indent + 1))
            if stmt.else_branch is not None:
                lines.append(f"{pad}}} else {{")
                for s in stmt.else_branch:
                    lines.extend(self._emit_statement(s, indent + 1))
            lines.append(f"{pad}}}")

        return lines

    def _emit_condition(self, expr: IRExpr) -> str:
        s = self._emit_expr(expr)
        if s.startswith("(") and s.endswith(")"):
            # Strip outermost parens to avoid ((a == b)) clang warning
            inner = s[1:-1].strip()
            # Only strip if parens were balanced
            depth = 0
            balanced = True
            for ch in inner:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth < 0:
                        balanced = False
                        break
            if balanced and depth == 0:
                return inner
        return s

    def _emit_expr(self, expr: IRExpr) -> str:
        if isinstance(expr, IRLiteral):
            if isinstance(expr.value, bool):
                return "true" if expr.value else "false"
            if isinstance(expr.value, int):
                if expr.value == -9223372036854775808:
                    return "(-9223372036854775807LL - 1LL)"
                return f"INT64_C({expr.value})"
            if isinstance(expr.value, float):
                formatted = repr(expr.value)
                if "." not in formatted and "e" not in formatted and "E" not in formatted:
                    formatted += ".0"
                return formatted
            if isinstance(expr.value, str):
                encoded = "".join(
                    f"\\x{b:02x}" if b < 32 or b >= 127 or chr(b) in ('"', '\\') else chr(b)
                    for b in expr.value.encode("utf-8")
                )
                return f'"{encoded}"'
            return "0"

        if isinstance(expr, IRReference):
            return self._symbol(expr.symbol, expr.name)

        if isinstance(expr, IRUnary):
            inner = self._emit_expr(expr.expr)
            if expr.op in ("-", "+"):
                if expr.expr.type.name in ("int", "int64"):
                    if expr.op == "-":
                        return f"rove_i64_neg({inner})"
                    return inner
                return f"{expr.op}({inner})"
            if expr.op in ("!", "not"):
                return f"!({inner})"
            if expr.op == "~":
                return f"~({inner})"
            return f"{expr.op}({inner})"

        if isinstance(expr, IRBinary):
            left = self._emit_expr(expr.left)
            right = self._emit_expr(expr.right)
            is_int = expr.left.type.name in ("int", "int64")

            if expr.op == "+":
                return f"rove_i64_add({left}, {right})" if is_int else f"({left} + {right})"
            if expr.op == "-":
                return f"rove_i64_sub({left}, {right})" if is_int else f"({left} - {right})"
            if expr.op == "*":
                return f"rove_i64_mul({left}, {right})" if is_int else f"({left} * {right})"
            if expr.op == "/":
                return f"rove_i64_div({left}, {right})" if is_int else f"({left} / {right})"
            if expr.op == "%":
                return f"rove_i64_mod({left}, {right})" if is_int else f"fmod({left}, {right})"
            if expr.op == "<<":
                return f"rove_i64_shl({left}, {right})"
            if expr.op == ">>":
                return f"rove_i64_shr({left}, {right})"
            if expr.op in ("&", "|", "^"):
                return f"({left} {expr.op} {right})"
            if expr.op in ("==", "!=", "<", "<=", ">", ">="):
                return f"({left} {expr.op} {right})"
            if expr.op in ("and", "&&"):
                return f"({left} && {right})"
            if expr.op in ("or", "||"):
                return f"({left} || {right})"
            return f"({left} {expr.op} {right})"

        if isinstance(expr, IRConditional):
            cond = self._emit_expr(expr.condition)
            then_val = self._emit_expr(expr.then_expr)
            else_val = self._emit_expr(expr.else_expr)
            return f"(({cond}) ? ({then_val}) : ({else_val}))"

        if isinstance(expr, IRCall):
            if expr.callee == "print" and len(expr.args) == 1:
                arg = expr.args[0]
                arg_expr = self._emit_expr(arg)
                if arg.type.name in ("int", "int64"):
                    return f"rove_print_i64({arg_expr})"
                if arg.type.name in ("float", "float64"):
                    return f"rove_print_f64({arg_expr})"
                if arg.type.name == "bool":
                    return f"rove_print_bool({arg_expr})"
                if arg.type.name == "string":
                    return f"rove_print_str({arg_expr})"
                return f"rove_print_i64({arg_expr})"

            fn_name = self.symbol_names.get(expr.callee_symbol, self._identifier(expr.callee))
            arg_strs = [self._emit_expr(a) for a in expr.args]
            return f"{fn_name}({', '.join(arg_strs)})"

        raise C17EmissionError(f"C17 scalar pilot does not support expression '{type(expr).__name__}'", expr.span)

    def _parameter_symbol(self, symbol: str, preferred: str) -> str:
        if symbol not in self.symbol_names:
            self.symbol_names[symbol] = self._identifier(preferred)
        return self.symbol_names[symbol]

    def _symbol(self, symbol: str, preferred: str) -> str:
        if symbol in self.symbol_names:
            return self.symbol_names[symbol]
        base = self._identifier(preferred)
        if symbol.startswith("function::"):
            name = base
        elif "::param::" in symbol:
            name = base
        else:
            digest = hashlib.sha256(symbol.encode("utf-8")).hexdigest()[:8]
            name = f"{base}__rove_{digest}"
        self.symbol_names[symbol] = name
        return name

    @staticmethod
    def _identifier(name: str) -> str:
        clean = _IDENTIFIER_CHARS.sub("_", name)
        if not clean:
            clean = "_rove_var"
        if clean[0].isdigit():
            clean = "_" + clean
        if clean in _C17_RESERVED:
            clean += "_rove"
        return clean


def emit_c17(module: IRModule) -> str:
    """Convenience entry point for C17 code emission."""
    return C17ScalarEmitter(module).emit()
