"""Verified pass pipeline for experimental MIR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Tuple

from .model import MIRModule
from .serialization import fingerprint
from .verifier import verify_mir


class MIRPass(Protocol):
    name: str

    def run(self, module: MIRModule) -> MIRModule:
        ...


@dataclass(frozen=True, slots=True)
class MIRPassContract:
    """Declarative analysis/invariant contract for one MIR transform.

    MIR does not have an analysis cache yet. These fields make pass intent
    explicit now so a future cache can invalidate conservatively instead of
    guessing. A pass without an explicit contract defaults to invalidating all
    analyses.
    """

    required_analyses: Tuple[str, ...] = ()
    preserved_analyses: Tuple[str, ...] = ()
    invalidated_analyses: Tuple[str, ...] = ("*",)
    preserved_invariants: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        required = set(self.required_analyses)
        preserved = set(self.preserved_analyses)
        invalidated = set(self.invalidated_analyses)
        if "*" in preserved:
            raise ValueError("MIR pass contracts cannot preserve wildcard analysis '*'")
        if "*" in invalidated and len(invalidated) != 1:
            raise ValueError("Wildcard invalidation '*' must be the only invalidated analysis")
        overlap = preserved & invalidated
        if overlap:
            raise ValueError(
                "MIR pass contract both preserves and invalidates analyses: "
                + ", ".join(sorted(overlap))
            )
        if "" in required | preserved | invalidated | set(self.preserved_invariants):
            raise ValueError("MIR pass contract names must be non-empty")


DEFAULT_MIR_PASS_CONTRACT = MIRPassContract()


@dataclass(frozen=True, slots=True)
class MIRPassRecord:
    name: str
    changed: bool
    before_fingerprint: str
    after_fingerprint: str
    required_analyses: Tuple[str, ...] = ()
    preserved_analyses: Tuple[str, ...] = ()
    invalidated_analyses: Tuple[str, ...] = ("*",)
    preserved_invariants: Tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MIRPassResult:
    module: MIRModule
    records: Tuple[MIRPassRecord, ...]


class MIRPassManager:
    def __init__(self, passes: tuple[MIRPass, ...] = ()):
        self.passes = tuple(passes)

    def run(self, module: MIRModule) -> MIRPassResult:
        current = verify_mir(module)
        records = []
        for transform in self.passes:
            contract = getattr(transform, "contract", DEFAULT_MIR_PASS_CONTRACT)
            if not isinstance(contract, MIRPassContract):
                raise TypeError(
                    f"MIR pass {transform.name} contract must be MIRPassContract"
                )
            before = fingerprint(current)
            candidate = transform.run(current)
            if not isinstance(candidate, MIRModule):
                raise TypeError(f"MIR pass {transform.name} must return MIRModule")
            if candidate.schema_version != current.schema_version:
                raise ValueError(f"MIR pass {transform.name} changed the schema version")
            if candidate.source_name != current.source_name or candidate.target != current.target:
                raise ValueError(f"MIR pass {transform.name} changed module identity")
            verify_mir(candidate)
            after = fingerprint(candidate)
            records.append(MIRPassRecord(
                transform.name,
                before != after,
                before,
                after,
                contract.required_analyses,
                contract.preserved_analyses,
                contract.invalidated_analyses,
                contract.preserved_invariants,
            ))
            current = candidate
        return MIRPassResult(current, tuple(records))
