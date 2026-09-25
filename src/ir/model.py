"""Immutable structured typed high-level IR for Rove."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .types import IRType


HIR_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SourceSpan:
    source: str
    line: int
    column: int
    length: int = 1


@dataclass(frozen=True, slots=True)
class IRNode:
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class IRExpr(IRNode):
    type: IRType


@dataclass(frozen=True, slots=True)
class IRLiteral(IRExpr):
    value: object


@dataclass(frozen=True, slots=True)
class IRReference(IRExpr):
    name: str
    symbol: str


@dataclass(frozen=True, slots=True)
class IRBinary(IRExpr):
    left: IRExpr
    op: str
    right: IRExpr


@dataclass(frozen=True, slots=True)
class IRUnary(IRExpr):
    op: str
    expr: IRExpr


@dataclass(frozen=True, slots=True)
class IRAwait(IRExpr):
    expr: IRExpr


@dataclass(frozen=True, slots=True)
class IRResultPropagate(IRExpr):
    expr: IRExpr


@dataclass(frozen=True, slots=True)
class IRCall(IRExpr):
    callee: str
    callee_symbol: str
    args: Tuple[IRExpr, ...]
    receiver: Optional[IRExpr] = None


@dataclass(frozen=True, slots=True)
class IRMemberAccess(IRExpr):
    obj: IRExpr
    member: str
    safe: bool = False


@dataclass(frozen=True, slots=True)
class IRIndexAccess(IRExpr):
    obj: IRExpr
    index: IRExpr


@dataclass(frozen=True, slots=True)
class IRArray(IRExpr):
    elements: Tuple[IRExpr, ...]


@dataclass(frozen=True, slots=True)
class IRNullCoalesce(IRExpr):
    left: IRExpr
    right: IRExpr


@dataclass(frozen=True, slots=True)
class IRConditional(IRExpr):
    condition: IRExpr
    then_expr: IRExpr
    else_expr: IRExpr


@dataclass(frozen=True, slots=True)
class IRMatchExpressionCase:
    pattern: Optional[IRExpr]
    value: IRExpr


@dataclass(frozen=True, slots=True)
class IRMatchExpression(IRExpr):
    subject: IRExpr
    cases: Tuple[IRMatchExpressionCase, ...]


@dataclass(frozen=True, slots=True)
class IRLambda(IRExpr):
    params: Tuple["IRParameter", ...]
    body: IRExpr


@dataclass(frozen=True, slots=True)
class IRStatement(IRNode):
    pass


@dataclass(frozen=True, slots=True)
class IRVarDecl(IRStatement):
    name: str
    symbol: str
    type: IRType
    expr: IRExpr
    is_const: bool = False


@dataclass(frozen=True, slots=True)
class IRAssign(IRStatement):
    target: IRExpr
    expr: IRExpr


@dataclass(frozen=True, slots=True)
class IRExprStatement(IRStatement):
    expr: IRExpr


@dataclass(frozen=True, slots=True)
class IRReturn(IRStatement):
    expr: Optional[IRExpr]


@dataclass(frozen=True, slots=True)
class IRThrow(IRStatement):
    expr: IRExpr


@dataclass(frozen=True, slots=True)
class IRYield(IRStatement):
    expr: IRExpr


@dataclass(frozen=True, slots=True)
class IRIf(IRStatement):
    condition: IRExpr
    then_branch: Tuple[IRStatement, ...]
    elif_branches: Tuple[Tuple[IRExpr, Tuple[IRStatement, ...]], ...]
    else_branch: Optional[Tuple[IRStatement, ...]]


@dataclass(frozen=True, slots=True)
class IRWhile(IRStatement):
    condition: IRExpr
    body: Tuple[IRStatement, ...]


@dataclass(frozen=True, slots=True)
class IRFor(IRStatement):
    var_name: str
    symbol: str
    start_expr: Optional[IRExpr]
    end_expr: Optional[IRExpr]
    collection_expr: Optional[IRExpr]
    body: Tuple[IRStatement, ...]


@dataclass(frozen=True, slots=True)
class IRBreak(IRStatement):
    pass


@dataclass(frozen=True, slots=True)
class IRContinue(IRStatement):
    pass


@dataclass(frozen=True, slots=True)
class IRDefer(IRStatement):
    expr: IRExpr


@dataclass(frozen=True, slots=True)
class IRGuard(IRStatement):
    condition: IRExpr
    else_body: Tuple[IRStatement, ...]


@dataclass(frozen=True, slots=True)
class IRUnsafeBlock(IRStatement):
    body: Tuple[IRStatement, ...]


@dataclass(frozen=True, slots=True)
class IRSpawn(IRStatement):
    body: Tuple[IRStatement, ...]


@dataclass(frozen=True, slots=True)
class IRAssert(IRStatement):
    condition: IRExpr
    message: Optional[str]


@dataclass(frozen=True, slots=True)
class IRMatchCase:
    pattern: IRExpr
    body: Tuple[IRStatement, ...]


@dataclass(frozen=True, slots=True)
class IRMatch(IRStatement):
    expr: IRExpr
    cases: Tuple[IRMatchCase, ...]


@dataclass(frozen=True, slots=True)
class IRTryCatch(IRStatement):
    try_body: Tuple[IRStatement, ...]
    error_name: str
    error_symbol: str
    catch_body: Tuple[IRStatement, ...]


@dataclass(frozen=True, slots=True)
class IRTestBlock(IRStatement):
    description: str
    body: Tuple[IRStatement, ...]


@dataclass(frozen=True, slots=True)
class IRParameter:
    name: str
    symbol: str
    type: IRType
    default: Optional[IRExpr] = None

    @property
    def type_annot(self) -> IRType:
        return self.type


@dataclass(frozen=True, slots=True)
class IRFunction(IRNode):
    name: str
    symbol: str
    params: Tuple[IRParameter, ...]
    return_type: IRType
    body: Tuple[IRStatement, ...]
    generic_params: Tuple[str, ...] = ()
    is_async: bool = False
    doc_comment: str = ""


@dataclass(frozen=True, slots=True)
class IRStruct(IRNode):
    name: str
    symbol: str
    fields: Tuple[IRParameter, ...]
    generic_params: Tuple[str, ...] = ()
    doc_comment: str = ""


@dataclass(frozen=True, slots=True)
class IRTrait(IRNode):
    name: str
    symbol: str
    methods: Tuple[IRFunction, ...]


@dataclass(frozen=True, slots=True)
class IRImpl(IRNode):
    trait_name: Optional[str]
    target_type: str
    methods: Tuple[IRFunction, ...]


@dataclass(frozen=True, slots=True)
class IRTypeAlias(IRNode):
    name: str
    symbol: str
    actual_type: IRType


@dataclass(frozen=True, slots=True)
class IREnumMember:
    name: str
    value: Optional[IRExpr]
    payload_types: Tuple[IRType, ...] = ()
    is_variant: bool = False


@dataclass(frozen=True, slots=True)
class IREnum(IRNode):
    name: str
    symbol: str
    members: Tuple[IREnumMember, ...]
    generic_params: Tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IRExternFunction(IRNode):
    abi: str
    name: str
    symbol: str
    params: Tuple[IRParameter, ...]
    return_type: IRType
    varargs: bool = False


@dataclass(frozen=True, slots=True)
class IRNativeDirective(IRNode):
    kind: str
    value: str
    origin_module: str = ""


@dataclass(frozen=True, slots=True)
class IRForeignImport(IRNode):
    ecosystem: str
    module: str
    alias: str
    symbol: str
    source: str = ""


@dataclass(frozen=True, slots=True)
class IRModule:
    source_name: str
    target: str
    items: Tuple[IRNode, ...]
    schema_version: int = HIR_SCHEMA_VERSION

    @property
    def functions(self) -> Tuple[IRFunction, ...]:
        return tuple(item for item in self.items if isinstance(item, IRFunction))

    @property
    def top_level_statements(self) -> Tuple[IRStatement, ...]:
        return tuple(item for item in self.items if isinstance(item, IRStatement))
