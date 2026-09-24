"""Deterministic, verified transformation passes for Rove HIR."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Optional, Protocol, Tuple

from .model import (
    IRAssign,
    IRArray,
    IRAssert,
    IRAwait,
    IRResultPropagate,
    IRBinary,
    IRBreak,
    IRCall,
    IRContinue,
    IRConditional,
    IRDefer,
    IREnum,
    IREnumMember,
    IRExpr,
    IRExprStatement,
    IRExternFunction,
    IRForeignImport,
    IRFor,
    IRFunction,
    IRGuard,
    IRIf,
    IRImpl,
    IRIndexAccess,
    IRLambda,
    IRLiteral,
    IRMatch,
    IRMatchCase,
    IRMatchExpression,
    IRMatchExpressionCase,
    IRMemberAccess,
    IRModule,
    IRNativeDirective,
    IRNode,
    IRNullCoalesce,
    IRParameter,
    IRReference,
    IRReturn,
    IRSpawn,
    IRStatement,
    IRStruct,
    IRTestBlock,
    IRThrow,
    IRYield,
    IRTrait,
    IRTryCatch,
    IRTypeAlias,
    IRUnary,
    IRUnsafeBlock,
    IRVarDecl,
    IRWhile,
)
from .serialization import fingerprint
from .types import BOOL, FLOAT, INT, STRING, IRType
from .verifier import verify_hir


@dataclass(frozen=True, slots=True)
class PassRecord:
    name: str
    changed: bool
    before_fingerprint: str
    after_fingerprint: str


@dataclass(frozen=True, slots=True)
class PassPipelineResult:
    module: IRModule
    records: Tuple[PassRecord, ...]

    @property
    def changed(self) -> bool:
        return any(record.changed for record in self.records)


class IRPass(Protocol):
    name: str

    def run(self, module: IRModule) -> IRModule:
        ...


class HIRTransformer:
    """Complete immutable HIR tree transformer used by optimization passes."""

    def transform_module(self, module: IRModule) -> IRModule:
        return replace(module, items=tuple(self.transform_top_level(item) for item in module.items))

    def transform_top_level(self, node: IRNode) -> IRNode:
        if isinstance(node, IRFunction):
            return replace(
                node,
                params=tuple(self.transform_parameter(parameter) for parameter in node.params),
                body=self.transform_block(node.body),
            )
        if isinstance(node, IRStruct):
            return replace(node, fields=tuple(self.transform_parameter(field) for field in node.fields))
        if isinstance(node, IRTrait):
            return replace(
                node,
                methods=tuple(self.transform_top_level(method) for method in node.methods),
            )
        if isinstance(node, IRImpl):
            return replace(
                node,
                methods=tuple(self.transform_top_level(method) for method in node.methods),
            )
        if isinstance(node, IREnum):
            return replace(
                node,
                members=tuple(
                    IREnumMember(
                        member.name,
                        self.transform_expr(member.value) if member.value is not None else None,
                        member.payload_types,
                        member.is_variant,
                    )
                    for member in node.members
                ),
            )
        if isinstance(node, IRExternFunction):
            return replace(
                node,
                params=tuple(self.transform_parameter(parameter) for parameter in node.params),
            )
        if isinstance(node, (IRTypeAlias, IRNativeDirective, IRForeignImport)):
            return node
        if isinstance(node, IRStatement):
            return self.transform_statement(node)
        raise TypeError(f"Unsupported HIR top-level node: {type(node).__name__}")

    def transform_parameter(self, parameter: IRParameter) -> IRParameter:
        if parameter.default is None:
            return parameter
        return replace(parameter, default=self.transform_expr(parameter.default))

    def transform_block(self, statements: Tuple[IRStatement, ...]) -> Tuple[IRStatement, ...]:
        return tuple(self.transform_statement(statement) for statement in statements)

    def transform_statement(self, node: IRStatement) -> IRStatement:
        if isinstance(node, IRVarDecl):
            return replace(node, expr=self.transform_expr(node.expr))
        if isinstance(node, IRAssign):
            return replace(node, target=self.transform_expr(node.target), expr=self.transform_expr(node.expr))
        if isinstance(node, IRExprStatement):
            return replace(node, expr=self.transform_expr(node.expr))
        if isinstance(node, IRReturn):
            return replace(node, expr=self.transform_expr(node.expr) if node.expr is not None else None)
        if isinstance(node, IRThrow):
            return replace(node, expr=self.transform_expr(node.expr))
        if isinstance(node, IRYield):
            return replace(node, expr=self.transform_expr(node.expr))
        if isinstance(node, IRIf):
            return replace(
                node,
                condition=self.transform_expr(node.condition),
                then_branch=self.transform_block(node.then_branch),
                elif_branches=tuple(
                    (self.transform_expr(condition), self.transform_block(branch))
                    for condition, branch in node.elif_branches
                ),
                else_branch=self.transform_block(node.else_branch) if node.else_branch is not None else None,
            )
        if isinstance(node, IRWhile):
            return replace(node, condition=self.transform_expr(node.condition), body=self.transform_block(node.body))
        if isinstance(node, IRFor):
            return replace(
                node,
                start_expr=self.transform_expr(node.start_expr) if node.start_expr is not None else None,
                end_expr=self.transform_expr(node.end_expr) if node.end_expr is not None else None,
                collection_expr=(
                    self.transform_expr(node.collection_expr) if node.collection_expr is not None else None
                ),
                body=self.transform_block(node.body),
            )
        if isinstance(node, (IRBreak, IRContinue)):
            return node
        if isinstance(node, IRDefer):
            return replace(node, expr=self.transform_expr(node.expr))
        if isinstance(node, IRGuard):
            return replace(
                node,
                condition=self.transform_expr(node.condition),
                else_body=self.transform_block(node.else_body),
            )
        if isinstance(node, IRUnsafeBlock):
            return replace(node, body=self.transform_block(node.body))
        if isinstance(node, IRSpawn):
            return replace(node, body=self.transform_block(node.body))
        if isinstance(node, IRAssert):
            return replace(node, condition=self.transform_expr(node.condition))
        if isinstance(node, IRMatch):
            return replace(
                node,
                expr=self.transform_expr(node.expr),
                cases=tuple(
                    IRMatchCase(self.transform_expr(case.pattern), self.transform_block(case.body))
                    for case in node.cases
                ),
            )
        if isinstance(node, IRTryCatch):
            return replace(
                node,
                try_body=self.transform_block(node.try_body),
                catch_body=self.transform_block(node.catch_body),
            )
        if isinstance(node, IRTestBlock):
            return replace(node, body=self.transform_block(node.body))
        raise TypeError(f"Unsupported HIR statement node: {type(node).__name__}")

    def transform_expr(self, node: IRExpr) -> IRExpr:
        if isinstance(node, (IRLiteral, IRReference)):
            return node
        if isinstance(node, IRBinary):
            return replace(node, left=self.transform_expr(node.left), right=self.transform_expr(node.right))
        if isinstance(node, IRUnary):
            return replace(node, expr=self.transform_expr(node.expr))
        if isinstance(node, IRAwait):
            return replace(node, expr=self.transform_expr(node.expr))
        if isinstance(node, IRResultPropagate):
            return replace(node, expr=self.transform_expr(node.expr))
        if isinstance(node, IRCall):
            return replace(
                node,
                args=tuple(self.transform_expr(argument) for argument in node.args),
                receiver=self.transform_expr(node.receiver) if node.receiver is not None else None,
            )
        if isinstance(node, IRMemberAccess):
            return replace(node, obj=self.transform_expr(node.obj))
        if isinstance(node, IRIndexAccess):
            return replace(node, obj=self.transform_expr(node.obj), index=self.transform_expr(node.index))
        if isinstance(node, IRArray):
            return replace(node, elements=tuple(self.transform_expr(element) for element in node.elements))
        if isinstance(node, IRNullCoalesce):
            return replace(node, left=self.transform_expr(node.left), right=self.transform_expr(node.right))
        if isinstance(node, IRConditional):
            return replace(
                node,
                condition=self.transform_expr(node.condition),
                then_expr=self.transform_expr(node.then_expr),
                else_expr=self.transform_expr(node.else_expr),
            )
        if isinstance(node, IRMatchExpression):
            return replace(
                node,
                subject=self.transform_expr(node.subject),
                cases=tuple(
                    IRMatchExpressionCase(
                        self.transform_expr(case.pattern) if case.pattern is not None else None,
                        self.transform_expr(case.value),
                    )
                    for case in node.cases
                ),
            )
        if isinstance(node, IRLambda):
            return replace(
                node,
                params=tuple(self.transform_parameter(parameter) for parameter in node.params),
                body=self.transform_expr(node.body),
            )
        raise TypeError(f"Unsupported HIR expression node: {type(node).__name__}")


class ConstantFoldPass(HIRTransformer):
    name = "constant-fold"
    _INT_MASK = (1 << 64) - 1
    _INT_SIGN = 1 << 63

    def run(self, module: IRModule) -> IRModule:
        return self.transform_module(module)

    def transform_expr(self, node: IRExpr) -> IRExpr:
        folded = super().transform_expr(node)
        if isinstance(folded, IRUnary) and isinstance(folded.expr, IRLiteral):
            value = self._fold_unary(folded.op, folded.expr.value, folded.type)
            if value is not _NO_FOLD:
                return IRLiteral(folded.span, folded.type, value)
        if isinstance(folded, IRBinary):
            short_circuit = self._fold_short_circuit(folded)
            if short_circuit is not None:
                return short_circuit
            if isinstance(folded.left, IRLiteral) and isinstance(folded.right, IRLiteral):
                value = self._fold_binary(
                    folded.op,
                    folded.left.value,
                    folded.right.value,
                    folded.type,
                )
                if value is not _NO_FOLD:
                    return IRLiteral(folded.span, folded.type, value)
        if isinstance(folded, IRNullCoalesce) and isinstance(folded.left, IRLiteral):
            selected = folded.right if folded.left.value is None else folded.left
            return replace(selected, span=folded.span, type=folded.type)
        if isinstance(folded, IRConditional) and isinstance(folded.condition, IRLiteral):
            if isinstance(folded.condition.value, bool):
                selected = folded.then_expr if folded.condition.value else folded.else_expr
                return replace(selected, span=folded.span, type=folded.type)
        return folded

    def _fold_short_circuit(self, node: IRBinary) -> Optional[IRLiteral]:
        if not isinstance(node.left, IRLiteral):
            return None
        truth = self._truth_value(node.left.value)
        if truth is None:
            return None
        if node.op in ("and", "&&") and not truth:
            return IRLiteral(node.span, node.type, False)
        if node.op in ("or", "||") and truth:
            return IRLiteral(node.span, node.type, True)
        return None

    def _fold_unary(self, op: str, value: object, result_type: IRType) -> object:
        if op in ("!", "not"):
            truth = self._truth_value(value)
            return not truth if truth is not None else _NO_FOLD
        if op == "+" and self._is_number(value):
            return value
        if result_type == INT and self._is_int(value):
            if op == "-":
                return self._wrap_i64(-value)
            if op == "~":
                return self._wrap_i64(~value)
        if op == "-" and isinstance(value, float):
            result = -value
            return result if self._safe_number(result) else _NO_FOLD
        return _NO_FOLD

    def _fold_binary(
        self,
        op: str,
        left: object,
        right: object,
        result_type: IRType,
    ) -> object:
        try:
            if op == "+":
                if isinstance(left, str) and isinstance(right, str):
                    return left + right
            if result_type == INT and self._is_int(left) and self._is_int(right):
                if op == "+":
                    return self._wrap_i64(left + right)
                if op == "-":
                    return self._wrap_i64(left - right)
                if op == "*":
                    return self._wrap_i64(left * right)
                if op == "/":
                    if right == 0:
                        return _NO_FOLD
                    return self._wrap_i64(self._trunc_div(left, right))
                if op == "%":
                    if right == 0:
                        return _NO_FOLD
                    quotient = self._trunc_div(left, right)
                    return self._wrap_i64(left - quotient * right)
                if op == "&":
                    return self._wrap_i64(left & right)
                if op == "^":
                    return self._wrap_i64(left ^ right)
                if op == "|":
                    return self._wrap_i64(left | right)
                if op == "<<":
                    return self._wrap_i64(left << (right & 63))
                if op == ">>":
                    return self._wrap_i64(left >> (right & 63))
            if result_type == FLOAT and self._is_number(left) and self._is_number(right):
                left_float = float(left)
                right_float = float(right)
                if op == "+":
                    result = left_float + right_float
                    return result if self._safe_number(result) else _NO_FOLD
                if op == "-":
                    result = left_float - right_float
                    return result if self._safe_number(result) else _NO_FOLD
                if op == "*":
                    result = left_float * right_float
                    return result if self._safe_number(result) else _NO_FOLD
            elif op in ("==", "!=") and self._same_comparable_domain(left, right):
                if self._is_number(left) and self._is_number(right) and (
                    isinstance(left, float) or isinstance(right, float)
                ):
                    equal = float(left) == float(right)
                else:
                    equal = left == right
                return equal if op == "==" else not equal
            elif op in ("<", ">", "<=", ">=") and self._same_ordered_domain(left, right):
                if self._is_number(left) and self._is_number(right) and (
                    isinstance(left, float) or isinstance(right, float)
                ):
                    left = float(left)
                    right = float(right)
                return {
                    "<": left < right,
                    ">": left > right,
                    "<=": left <= right,
                    ">=": left >= right,
                }[op]
            elif op in ("and", "&&", "or", "||"):
                left_truth = self._truth_value(left)
                right_truth = self._truth_value(right)
                if left_truth is not None and right_truth is not None:
                    return (left_truth and right_truth) if op in ("and", "&&") else (left_truth or right_truth)
        except (ArithmeticError, TypeError, ValueError, OverflowError):
            return _NO_FOLD
        return _NO_FOLD

    @staticmethod
    def _truth_value(value: object) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            return value != 0
        return None

    @staticmethod
    def _is_int(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    @classmethod
    def _is_number(cls, value: object) -> bool:
        return cls._is_int(value) or isinstance(value, float)

    @classmethod
    def _wrap_i64(cls, value: int) -> int:
        bits = value & cls._INT_MASK
        return bits - (1 << 64) if bits & cls._INT_SIGN else bits

    @staticmethod
    def _trunc_div(left: int, right: int) -> int:
        quotient = abs(left) // abs(right)
        return -quotient if (left < 0) != (right < 0) else quotient

    @classmethod
    def _safe_number(cls, value: object) -> bool:
        return isinstance(value, float) and value == value and value not in (float("inf"), float("-inf"))

    @classmethod
    def _same_comparable_domain(cls, left: object, right: object) -> bool:
        if cls._is_number(left) and cls._is_number(right):
            return True
        return type(left) is type(right) and isinstance(left, (str, bool, type(None)))

    @classmethod
    def _same_ordered_domain(cls, left: object, right: object) -> bool:
        return (cls._is_number(left) and cls._is_number(right)) or (
            isinstance(left, str) and isinstance(right, str)
        )

class DeadCodeEliminationPass(HIRTransformer):
    name = "dead-code-elimination"

    def run(self, module: IRModule) -> IRModule:
        return self.transform_module(module)

    def transform_module(self, module: IRModule) -> IRModule:
        items = []
        for item in module.items:
            transformed = self.transform_top_level(item)
            if isinstance(transformed, IRWhile) and self._literal_false(transformed.condition):
                continue
            items.append(transformed)
        return replace(module, items=tuple(items))

    def transform_block(self, statements: Tuple[IRStatement, ...]) -> Tuple[IRStatement, ...]:
        result = []
        terminated = False
        for statement in statements:
            if terminated:
                continue
            transformed = self.transform_statement(statement)
            if isinstance(transformed, IRWhile) and self._literal_false(transformed.condition):
                continue
            result.append(transformed)
            terminated = self._terminates_block(transformed)
        return tuple(result)

    @classmethod
    def _terminates_block(cls, statement: IRStatement) -> bool:
        if isinstance(statement, (IRReturn, IRThrow, IRBreak, IRContinue)):
            return True
        if isinstance(statement, IRIf):
            branches = (statement.then_branch,) + tuple(branch for _, branch in statement.elif_branches)
            return statement.else_branch is not None and all(
                cls._block_terminates(branch) for branch in branches + (statement.else_branch,)
            )
        if isinstance(statement, IRTryCatch):
            return cls._block_terminates(statement.try_body) and cls._block_terminates(statement.catch_body)
        if isinstance(statement, IRUnsafeBlock):
            return cls._block_terminates(statement.body)
        if isinstance(statement, IRMatch):
            exhaustive = any(
                isinstance(case.pattern, IRReference) and case.pattern.symbol == "pattern::_"
                for case in statement.cases
            )
            return exhaustive and all(cls._block_terminates(case.body) for case in statement.cases)
        return False

    @classmethod
    def _block_terminates(cls, statements: Tuple[IRStatement, ...]) -> bool:
        return any(cls._terminates_block(statement) for statement in statements)

    @staticmethod
    def _literal_false(expr: IRExpr) -> bool:
        return isinstance(expr, IRLiteral) and (
            expr.value is False or (isinstance(expr.value, int) and not isinstance(expr.value, bool) and expr.value == 0)
        )


class _NoFold:
    pass


_NO_FOLD = _NoFold()


class PassManager:
    def __init__(
        self,
        passes: Iterable[IRPass],
        *,
        verify_each: bool = True,
        require_definite_returns: bool = True,
    ):
        self.passes = tuple(passes)
        self.verify_each = verify_each
        self.require_definite_returns = require_definite_returns
        names = [item.name for item in self.passes]
        if any(not name for name in names):
            raise ValueError("HIR pass names must not be empty")
        if len(names) != len(set(names)):
            raise ValueError("HIR pass names must be unique within a pipeline")

    def run(self, module: IRModule) -> PassPipelineResult:
        current = module
        records = []
        if self.verify_each:
            verify_hir(current, require_definite_returns=self.require_definite_returns)
        for compiler_pass in self.passes:
            before = fingerprint(current)
            transformed = compiler_pass.run(current)
            if not isinstance(transformed, IRModule):
                raise TypeError(f"HIR pass '{compiler_pass.name}' must return IRModule")
            if self.verify_each:
                verify_hir(transformed, require_definite_returns=self.require_definite_returns)
            after = fingerprint(transformed)
            records.append(PassRecord(compiler_pass.name, before != after, before, after))
            current = transformed
        return PassPipelineResult(current, tuple(records))


DEFAULT_PASSES: Tuple[IRPass, ...] = (
    ConstantFoldPass(),
    DeadCodeEliminationPass(),
)


def optimize_hir(
    module: IRModule,
    *,
    verify_each: bool = True,
    require_definite_returns: bool = True,
) -> PassPipelineResult:
    return PassManager(
        DEFAULT_PASSES,
        verify_each=verify_each,
        require_definite_returns=require_definite_returns,
    ).run(module)
