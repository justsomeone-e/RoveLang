"""Immutable control-flow MIR model.

The schema is experimental and independent from public Typed HIR schema v1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .types import MIRType


MIR_SCHEMA_VERSION = 3


@dataclass(frozen=True, slots=True)
class MIRSpan:
    source: str
    line: int
    column: int
    length: int = 1


@dataclass(frozen=True, slots=True)
class FieldProjection:
    name: str


@dataclass(frozen=True, slots=True)
class IndexProjection:
    local: int


@dataclass(frozen=True, slots=True)
class ConstantIndexProjection:
    index: int


@dataclass(frozen=True, slots=True)
class DerefProjection:
    pass


@dataclass(frozen=True, slots=True)
class VariantProjection:
    name: str
    index: int


Projection = (
    FieldProjection
    | IndexProjection
    | ConstantIndexProjection
    | DerefProjection
    | VariantProjection
)


@dataclass(frozen=True, slots=True)
class Place:
    local: int
    projections: Tuple[Projection, ...] = ()


@dataclass(frozen=True, slots=True)
class ConstOperand:
    type: MIRType
    value: object


@dataclass(frozen=True, slots=True)
class CopyOperand:
    place: Place


@dataclass(frozen=True, slots=True)
class MoveOperand:
    place: Place


Operand = ConstOperand | CopyOperand | MoveOperand


@dataclass(frozen=True, slots=True)
class UseRValue:
    operand: Operand


@dataclass(frozen=True, slots=True)
class BinaryRValue:
    op: str
    left: Operand
    right: Operand
    type: MIRType


@dataclass(frozen=True, slots=True)
class UnaryRValue:
    op: str
    operand: Operand
    type: MIRType


@dataclass(frozen=True, slots=True)
class CastRValue:
    kind: str
    operand: Operand
    type: MIRType


@dataclass(frozen=True, slots=True)
class AggregateRValue:
    kind: str
    name: str
    operands: Tuple[Operand, ...]
    type: MIRType
    fields: Tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BorrowRValue:
    place: Place
    mutable: bool
    type: MIRType


@dataclass(frozen=True, slots=True)
class DiscriminantRValue:
    operand: Operand
    type: MIRType


@dataclass(frozen=True, slots=True)
class PayloadRValue:
    operand: Operand
    index: int
    type: MIRType


RValue = (
    UseRValue
    | BinaryRValue
    | UnaryRValue
    | CastRValue
    | AggregateRValue
    | BorrowRValue
    | DiscriminantRValue
    | PayloadRValue
)


@dataclass(frozen=True, slots=True)
class AssignStatement:
    place: Place
    value: RValue
    span: MIRSpan


@dataclass(frozen=True, slots=True)
class StorageLiveStatement:
    local: int
    span: MIRSpan


@dataclass(frozen=True, slots=True)
class StorageDeadStatement:
    local: int
    span: MIRSpan


@dataclass(frozen=True, slots=True)
class RetainStatement:
    place: Place
    span: MIRSpan


@dataclass(frozen=True, slots=True)
class ReleaseStatement:
    place: Place
    span: MIRSpan


@dataclass(frozen=True, slots=True)
class DeinitStatement:
    place: Place
    span: MIRSpan


@dataclass(frozen=True, slots=True)
class NopStatement:
    span: MIRSpan


Statement = (
    AssignStatement
    | StorageLiveStatement
    | StorageDeadStatement
    | RetainStatement
    | ReleaseStatement
    | DeinitStatement
    | NopStatement
)


@dataclass(frozen=True, slots=True)
class GotoTerminator:
    target: int
    span: MIRSpan


@dataclass(frozen=True, slots=True)
class SwitchIntTerminator:
    discriminator: Operand
    targets: Tuple[Tuple[int, int], ...]
    otherwise: int
    span: MIRSpan


@dataclass(frozen=True, slots=True)
class SwitchValueTerminator:
    discriminator: Operand
    targets: Tuple[Tuple[object, int], ...]
    otherwise: int
    span: MIRSpan


@dataclass(frozen=True, slots=True)
class ReturnTerminator:
    span: MIRSpan


@dataclass(frozen=True, slots=True)
class CallTerminator:
    function: str
    arguments: Tuple[Operand, ...]
    destination: Place | None
    target: int | None
    unwind: int | None
    span: MIRSpan
    error_destination: Place | None = None


@dataclass(frozen=True, slots=True)
class DropTerminator:
    place: Place
    target: int
    unwind: int | None
    span: MIRSpan


@dataclass(frozen=True, slots=True)
class AssertTerminator:
    condition: Operand
    expected: bool
    message: str
    target: int
    unwind: int | None
    span: MIRSpan


@dataclass(frozen=True, slots=True)
class UnreachableTerminator:
    span: MIRSpan


@dataclass(frozen=True, slots=True)
class ThrowTerminator:
    value: Operand
    target: int | None
    destination: Place | None
    span: MIRSpan


@dataclass(frozen=True, slots=True)
class SuspendTerminator:
    task: Operand
    destination: Place
    resume: int
    suspend_id: int
    span: MIRSpan
    unwind: int | None = None
    error_destination: Place | None = None


Terminator = (
    GotoTerminator
    | SwitchIntTerminator
    | SwitchValueTerminator
    | ReturnTerminator
    | CallTerminator
    | DropTerminator
    | AssertTerminator
    | UnreachableTerminator
    | ThrowTerminator
    | SuspendTerminator
)


@dataclass(frozen=True, slots=True)
class MIRLocal:
    id: int
    name: str
    type: MIRType
    kind: str
    span: MIRSpan


@dataclass(frozen=True, slots=True)
class MIRBasicBlock:
    id: int
    statements: Tuple[Statement, ...]
    terminator: Terminator


@dataclass(frozen=True, slots=True)
class MIRSuspendPoint:
    id: int
    block: int
    resume: int
    live_locals: Tuple[int, ...]


@dataclass(frozen=True, slots=True)
class MIRCoroutine:
    state_local: int
    frame_locals: Tuple[int, ...]
    suspend_points: Tuple[MIRSuspendPoint, ...]
    start_symbol: str
    resume_symbol: str
    destroy_symbol: str


@dataclass(frozen=True, slots=True)
class MIRFunction:
    name: str
    symbol: str
    locals: Tuple[MIRLocal, ...]
    parameters: Tuple[int, ...]
    return_local: int
    blocks: Tuple[MIRBasicBlock, ...]
    span: MIRSpan
    effects: Tuple[str, ...] = ()
    is_async: bool = False
    coroutine: MIRCoroutine | None = None


@dataclass(frozen=True, slots=True)
class MIRField:
    name: str
    type: MIRType


@dataclass(frozen=True, slots=True)
class MIRStructDef:
    name: str
    symbol: str
    fields: Tuple[MIRField, ...]


@dataclass(frozen=True, slots=True)
class MIREnumVariant:
    name: str
    payload_types: Tuple[MIRType, ...]


@dataclass(frozen=True, slots=True)
class MIREnumDef:
    name: str
    symbol: str
    variants: Tuple[MIREnumVariant, ...]


MIRTypeDefinition = MIRStructDef | MIREnumDef


@dataclass(frozen=True, slots=True)
class MIRModule:
    source_name: str
    target: str
    functions: Tuple[MIRFunction, ...]
    type_definitions: Tuple[MIRTypeDefinition, ...] = ()
    schema_version: int = MIR_SCHEMA_VERSION
