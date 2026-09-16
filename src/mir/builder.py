"""Checked construction helpers for experimental MIR functions."""

from __future__ import annotations

from dataclasses import dataclass

from .model import (
    MIRBasicBlock,
    MIRFunction,
    MIRLocal,
    MIRSpan,
    Statement,
    Terminator,
)
from .types import MIRType


@dataclass
class _OpenBlock:
    id: int
    statements: list[Statement]
    terminator: Terminator | None = None


class MIRFunctionBuilder:
    def __init__(
        self,
        name: str,
        symbol: str,
        return_type: MIRType,
        span: MIRSpan,
        *,
        is_async: bool = False,
    ):
        self.name = name
        self.symbol = symbol
        self.span = span
        self.is_async = is_async
        self._locals: list[MIRLocal] = [MIRLocal(0, "_return", return_type, "return", span)]
        self.coroutine_state_local: int | None = None
        if is_async:
            self.coroutine_state_local = 1
            self._locals.append(MIRLocal(1, "_coroutine_state", MIRType("int"), "coroutine-state", span))
        self._parameters: list[int] = []
        self._blocks: list[_OpenBlock] = []

    def new_local(self, name: str, type: MIRType, kind: str = "temporary", span: MIRSpan | None = None) -> int:
        local_id = len(self._locals)
        self._locals.append(MIRLocal(local_id, name, type, kind, span or self.span))
        if kind == "parameter":
            self._parameters.append(local_id)
        return local_id

    def new_block(self) -> int:
        block_id = len(self._blocks)
        self._blocks.append(_OpenBlock(block_id, []))
        return block_id

    def push_statement(self, block: int, statement: Statement) -> None:
        open_block = self._block(block)
        if open_block.terminator is not None:
            raise ValueError(f"Block {block} is already terminated")
        open_block.statements.append(statement)

    def set_terminator(self, block: int, terminator: Terminator) -> None:
        open_block = self._block(block)
        if open_block.terminator is not None:
            raise ValueError(f"Block {block} already has a terminator")
        open_block.terminator = terminator

    def is_terminated(self, block: int) -> bool:
        return self._block(block).terminator is not None

    def finish(self) -> MIRFunction:
        if not self._blocks:
            raise ValueError("MIR function requires an entry block")
        incomplete = [block.id for block in self._blocks if block.terminator is None]
        if incomplete:
            raise ValueError(f"MIR blocks require exactly one terminator: {incomplete}")
        return MIRFunction(
            name=self.name,
            symbol=self.symbol,
            locals=tuple(self._locals),
            parameters=tuple(self._parameters),
            return_local=0,
            blocks=tuple(
                MIRBasicBlock(block.id, tuple(block.statements), block.terminator)
                for block in self._blocks
            ),
            span=self.span,
            is_async=self.is_async,
        )

    def _block(self, block: int) -> _OpenBlock:
        if block < 0 or block >= len(self._blocks):
            raise IndexError(f"Unknown MIR block {block}")
        return self._blocks[block]
