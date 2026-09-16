"""Target legalization contracts for the experimental MIR pipeline.

Legalization is a hard gate: a backend may only receive operations explicitly
listed by its profile. M5 currently migrates C++ and LLVM plus deliberately
bounded WebAssembly, Rust, JavaScript, Python, and C17 pilots.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from src.core.backend_capabilities import normalize_backend_name, resolve_backend

from .model import (
    AggregateRValue,
    AssertTerminator,
    AssignStatement,
    BinaryRValue,
    BorrowRValue,
    CallTerminator,
    CastRValue,
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
    MIRSpan,
    MIREnumDef,
    MIRStructDef,
    MoveOperand,
    NopStatement,
    PayloadRValue,
    Place,
    ReleaseStatement,
    RetainStatement,
    ReturnTerminator,
    StorageDeadStatement,
    StorageLiveStatement,
    SwitchIntTerminator,
    SwitchValueTerminator,
    ThrowTerminator,
    UnaryRValue,
    UnreachableTerminator,
    UseRValue,
    VariantProjection,
)
from .types import MIRType
from .verifier import verify_mir
from .effects import infer_module_effects


MIR_LEGALIZATION_SCHEMA_VERSION = 3
MIR_BACKEND_MIGRATION_ORDER = ("cpp", "llvm", "wasm", "rust", "js", "python", "c")


@dataclass(frozen=True, slots=True)
class MIRBackendProfile:
    target: str
    migration_rank: int
    migration_status: str
    integer_width: int
    overflow: str
    exceptions: bool
    threads: bool
    ownership: str
    abi: str
    legal_statements: frozenset[str]
    legal_rvalues: frozenset[str]
    legal_terminators: frozenset[str]
    legal_projections: frozenset[str]
    legal_types: frozenset[str]
    legal_runtime_calls: frozenset[str]
    legal_binary_ops: frozenset[str]
    legal_unary_ops: frozenset[str]
    legal_effects: frozenset[str]

    @property
    def emitter_available(self) -> bool:
        return self.migration_status == "pilot"

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target,
            "migration_rank": self.migration_rank,
            "migration_status": self.migration_status,
            "integer_width": self.integer_width,
            "overflow": self.overflow,
            "exceptions": self.exceptions,
            "threads": self.threads,
            "ownership": self.ownership,
            "abi": self.abi,
            "legal_statements": sorted(self.legal_statements),
            "legal_rvalues": sorted(self.legal_rvalues),
            "legal_terminators": sorted(self.legal_terminators),
            "legal_projections": sorted(self.legal_projections),
            "legal_types": sorted(self.legal_types),
            "legal_runtime_calls": sorted(self.legal_runtime_calls),
            "legal_binary_ops": sorted(self.legal_binary_ops),
            "legal_unary_ops": sorted(self.legal_unary_ops),
            "legal_effects": sorted(self.legal_effects),
        }


_SCALAR_STATEMENTS = frozenset({
    AssignStatement.__name__,
    StorageLiveStatement.__name__,
    StorageDeadStatement.__name__,
    NopStatement.__name__,
})
_SCALAR_RVALUES = frozenset({
    UseRValue.__name__,
    BinaryRValue.__name__,
    UnaryRValue.__name__,
    CastRValue.__name__,
})
_SCALAR_TERMINATORS = frozenset({
    GotoTerminator.__name__,
    SwitchIntTerminator.__name__,
    SwitchValueTerminator.__name__,
    ReturnTerminator.__name__,
    CallTerminator.__name__,
    AssertTerminator.__name__,
    UnreachableTerminator.__name__,
})
_SCALAR_TYPES = frozenset({"void", "bool", "string", "int", "float", "f64"})
_SCALAR_RUNTIME = frozenset({"builtin::print"})
_SCALAR_BINARY_OPS = frozenset({
    "+", "-", "*", "/", "%", "&", "|", "^", "<<", ">>",
    "==", "!=", "<", "<=", ">", ">=",
})
_SCALAR_UNARY_OPS = frozenset({"!", "not", "+", "-", "~"})


def _profile(
    target: str,
    rank: int,
    *,
    status: str,
    integer_width: int,
    exceptions: bool,
    threads: bool,
    ownership: str,
    abi: str,
) -> MIRBackendProfile:
    return MIRBackendProfile(
        target=target,
        migration_rank=rank,
        migration_status=status,
        integer_width=integer_width,
        overflow="wrap",
        exceptions=exceptions,
        threads=threads,
        ownership=ownership,
        abi=abi,
        legal_statements=_SCALAR_STATEMENTS,
        legal_rvalues=_SCALAR_RVALUES,
        legal_terminators=_SCALAR_TERMINATORS,
        legal_projections=frozenset(),
        legal_types=_SCALAR_TYPES,
        legal_runtime_calls=_SCALAR_RUNTIME,
        legal_binary_ops=_SCALAR_BINARY_OPS,
        legal_unary_ops=_SCALAR_UNARY_OPS,
        legal_effects=frozenset({"pure", "io"}),
    )


MIR_BACKEND_PROFILES = {
    "cpp": _profile(
        "cpp", 1, status="pilot", integer_width=64, exceptions=True,
        threads=True, ownership="native-raii", abi="native-x64",
    ),
    "llvm": _profile(
        "llvm", 2, status="pilot", integer_width=64, exceptions=False,
        threads=False, ownership="explicit-runtime", abi="native-x64",
    ),
    "wasm": _profile(
        "wasm", 3, status="pilot", integer_width=64, exceptions=False,
        threads=False, ownership="linear-memory-runtime", abi="bundle-v1-wasm32",
    ),
    "rust": _profile(
        "rust", 4, status="pilot", integer_width=64, exceptions=False,
        threads=False, ownership="rust-values", abi="rust-2021",
    ),
    "js": _profile(
        "js", 5, status="pilot", integer_width=64, exceptions=True,
        threads=False, ownership="garbage-collected", abi="node-es2022",
    ),
    "python": _profile(
        "python", 6, status="pilot", integer_width=64, exceptions=True,
        threads=False, ownership="garbage-collected", abi="python-3",
    ),
    "c": _profile(
        "c", 7, status="pilot", integer_width=64, exceptions=False,
        threads=False, ownership="explicit-runtime", abi="c17-native",
    ),
}

# C++ is migrated first and therefore owns the initial aggregate legalization
# surface. Other targets remain deliberately scalar until their runtime/layout
# adapters are implemented and tested.
MIR_BACKEND_PROFILES["cpp"] = replace(
    MIR_BACKEND_PROFILES["cpp"],
    legal_rvalues=MIR_BACKEND_PROFILES["cpp"].legal_rvalues | frozenset({
        AggregateRValue.__name__, BorrowRValue.__name__, DiscriminantRValue.__name__,
        PayloadRValue.__name__,
    }),
    legal_statements=MIR_BACKEND_PROFILES["cpp"].legal_statements | frozenset({
        DeinitStatement.__name__, ReleaseStatement.__name__, RetainStatement.__name__,
    }),
    legal_terminators=MIR_BACKEND_PROFILES["cpp"].legal_terminators | frozenset({
        DropTerminator.__name__, ThrowTerminator.__name__,
    }),
    legal_projections=frozenset({
        DerefProjection.__name__, FieldProjection.__name__, IndexProjection.__name__,
        ConstantIndexProjection.__name__,
    }),
    legal_types=MIR_BACKEND_PROFILES["cpp"].legal_types | frozenset({"Array", "Option", "Result"}),
    legal_runtime_calls=MIR_BACKEND_PROFILES["cpp"].legal_runtime_calls | frozenset({
        "builtin::len", "builtin::to_string",
    }),
    legal_effects=MIR_BACKEND_PROFILES["cpp"].legal_effects | frozenset({
        "may_allocate", "may_throw", "unsafe",
    }),
)

# The first MIR-to-Wasm slice is deliberately pure and integer-focused. Heap
# values, host calls, casts, and aggregate ABI lowering stay behind the gate.
MIR_BACKEND_PROFILES["wasm"] = replace(
    MIR_BACKEND_PROFILES["wasm"],
    legal_rvalues=frozenset({
        AggregateRValue.__name__, BinaryRValue.__name__, CastRValue.__name__, DiscriminantRValue.__name__,
        PayloadRValue.__name__, UnaryRValue.__name__, UseRValue.__name__,
    }),
    legal_terminators=frozenset({
        AssertTerminator.__name__, CallTerminator.__name__, GotoTerminator.__name__,
        ReturnTerminator.__name__, SwitchIntTerminator.__name__, SwitchValueTerminator.__name__,
        UnreachableTerminator.__name__,
    }),
    legal_projections=frozenset({
        FieldProjection.__name__, IndexProjection.__name__, ConstantIndexProjection.__name__,
    }),
    legal_types=frozenset({"void", "bool", "int", "string", "Array"}),
    legal_runtime_calls=frozenset({"builtin::len"}),
    legal_effects=MIR_BACKEND_PROFILES["wasm"].legal_effects | frozenset({"may_allocate"}),
)

# Rust maps Nyx value ownership onto Rust moves/clones and non-unwinding drops.
# Raw borrows/dereferences and unwind cleanup remain behind the legalization gate.
MIR_BACKEND_PROFILES["rust"] = replace(
    MIR_BACKEND_PROFILES["rust"],
    legal_rvalues=frozenset({
        AggregateRValue.__name__, BinaryRValue.__name__, BorrowRValue.__name__, CastRValue.__name__,
        DiscriminantRValue.__name__, PayloadRValue.__name__, UnaryRValue.__name__,
        UseRValue.__name__,
    }),
    legal_statements=MIR_BACKEND_PROFILES["rust"].legal_statements | frozenset({
        DeinitStatement.__name__, ReleaseStatement.__name__, RetainStatement.__name__,
    }),
    legal_terminators=MIR_BACKEND_PROFILES["rust"].legal_terminators | frozenset({
        DropTerminator.__name__,
    }),
    legal_projections=frozenset({
        DerefProjection.__name__, FieldProjection.__name__, IndexProjection.__name__,
        ConstantIndexProjection.__name__,
    }),
    legal_types=MIR_BACKEND_PROFILES["rust"].legal_types | frozenset({"Array"}),
    legal_runtime_calls=MIR_BACKEND_PROFILES["rust"].legal_runtime_calls | frozenset({
        "builtin::len", "builtin::to_string",
    }),
    legal_effects=MIR_BACKEND_PROFILES["rust"].legal_effects | frozenset({
        "may_allocate", "unsafe",
    }),
)

# JavaScript uses BigInt for the Nyx i64 contract. Casts and heap/aggregate
# values remain excluded until their host representation is versioned.
MIR_BACKEND_PROFILES["js"] = replace(
    MIR_BACKEND_PROFILES["js"],
    legal_rvalues=frozenset({
        AggregateRValue.__name__, BinaryRValue.__name__, CastRValue.__name__,
        DiscriminantRValue.__name__, PayloadRValue.__name__, UnaryRValue.__name__,
        UseRValue.__name__,
    }),
    legal_projections=frozenset({
        FieldProjection.__name__, IndexProjection.__name__, ConstantIndexProjection.__name__,
    }),
    legal_terminators=MIR_BACKEND_PROFILES["js"].legal_terminators | frozenset({
        ThrowTerminator.__name__,
    }),
    legal_types=MIR_BACKEND_PROFILES["js"].legal_types | frozenset({"Array", "Option", "Result"}),
    legal_runtime_calls=MIR_BACKEND_PROFILES["js"].legal_runtime_calls | frozenset({
        "builtin::len", "builtin::to_string",
    }),
    legal_effects=MIR_BACKEND_PROFILES["js"].legal_effects | frozenset({
        "may_allocate", "may_throw",
    }),
)

# Python has arbitrary-precision integers, so the emitter inserts explicit
# signed-i64 normalization. Casts and aggregate values remain gated.
MIR_BACKEND_PROFILES["python"] = replace(
    MIR_BACKEND_PROFILES["python"],
    legal_rvalues=frozenset({
        AggregateRValue.__name__, BinaryRValue.__name__, CastRValue.__name__,
        DiscriminantRValue.__name__, PayloadRValue.__name__, UnaryRValue.__name__,
        UseRValue.__name__,
    }),
    legal_projections=frozenset({
        FieldProjection.__name__, IndexProjection.__name__, ConstantIndexProjection.__name__,
    }),
    legal_terminators=MIR_BACKEND_PROFILES["python"].legal_terminators | frozenset({
        ThrowTerminator.__name__,
    }),
    legal_types=MIR_BACKEND_PROFILES["python"].legal_types | frozenset({"Array", "Option", "Result"}),
    legal_runtime_calls=MIR_BACKEND_PROFILES["python"].legal_runtime_calls | frozenset({
        "builtin::len", "builtin::to_string",
    }),
    legal_effects=MIR_BACKEND_PROFILES["python"].legal_effects | frozenset({
        "may_allocate", "may_throw",
    }),
)

# C17 uses explicit bit conversions and a tiny tracked allocation runtime.
# Supported acyclic value structs, recursive arrays, multi-primitive tagged
# payloads, and one ownership-bearing tagged payload are legalized explicitly;
# cleanup edges remain gated.
MIR_BACKEND_PROFILES["c"] = replace(
    MIR_BACKEND_PROFILES["c"],
    legal_rvalues=frozenset({
        AggregateRValue.__name__, BinaryRValue.__name__, CastRValue.__name__,
        DiscriminantRValue.__name__, PayloadRValue.__name__, UnaryRValue.__name__,
        UseRValue.__name__,
    }),
    legal_projections=frozenset({
        FieldProjection.__name__, IndexProjection.__name__, ConstantIndexProjection.__name__,
    }),
    legal_types=MIR_BACKEND_PROFILES["c"].legal_types | frozenset({"Array", "Option", "Result"}),
    legal_runtime_calls=MIR_BACKEND_PROFILES["c"].legal_runtime_calls | frozenset({"builtin::len"}),
    legal_effects=MIR_BACKEND_PROFILES["c"].legal_effects | frozenset({"may_allocate"}),
)


@dataclass(frozen=True, slots=True)
class MIRLegalizationIssue:
    code: str
    message: str
    span: MIRSpan
    target: str


class MIRLegalizationError(ValueError):
    def __init__(self, issues: Iterable[MIRLegalizationIssue]):
        self.issues = tuple(issues)
        summary = "; ".join(f"{issue.code}: {issue.message}" for issue in self.issues)
        super().__init__(summary)


def resolve_mir_backend_profile(target: str) -> MIRBackendProfile | None:
    canonical = normalize_backend_name(target)
    if resolve_backend(canonical) is None:
        return None
    return MIR_BACKEND_PROFILES.get(canonical)


def mir_backend_manifest() -> dict[str, object]:
    return {
        "schema_version": MIR_LEGALIZATION_SCHEMA_VERSION,
        "migration_order": list(MIR_BACKEND_MIGRATION_ORDER),
        "profiles": [MIR_BACKEND_PROFILES[name].to_dict() for name in MIR_BACKEND_MIGRATION_ORDER],
    }


class _Legalizer:
    def __init__(self, module: MIRModule, target: str, *, require_emitter: bool):
        self.module = module
        self.target = normalize_backend_name(target)
        self.profile = resolve_mir_backend_profile(self.target)
        self.require_emitter = require_emitter
        self.issues: list[MIRLegalizationIssue] = []
        self.user_functions = {function.symbol for function in module.functions}
        self.type_definitions = {definition.name: definition for definition in module.type_definitions}
        self.local_types: dict[int, MIRType] = {}
        self.wasm_tag_locals: dict[int, dict[str, int]] = {}
        self.inferred_effects = {
            function.symbol: function.effects
            for function in infer_module_effects(module).functions
        }

    def collect(self) -> tuple[MIRLegalizationIssue, ...]:
        span = self._module_span()
        if resolve_backend(self.target) is None:
            self._issue("MIRG1000", f"Unknown MIR target '{self.target}'", span)
            return tuple(self.issues)
        if self.profile is None:
            self._issue(
                "MIRG1001",
                f"Target '{self.target}' has no MIR legalization profile",
                span,
            )
            return tuple(self.issues)
        if self.require_emitter and not self.profile.emitter_available:
            self._issue(
                "MIRG1009",
                f"Target '{self.target}' has a legalization contract but no migrated MIR emitter",
                span,
            )
            return tuple(self.issues)
        for definition in self.module.type_definitions:
            if self.target == "c" and isinstance(definition, MIRStructDef):
                for field in definition.fields:
                    if not self._c_value_field_compatible(
                        field.type, (definition.name,)
                    ):
                        self._issue(
                            "MIRG1002",
                            f"The C17 MIR struct pilot requires acyclic by-value int, bool, "
                            f"string, or nominal-struct fields; "
                            f"'{definition.name}.{field.name}' is '{field.type}'",
                            span,
                        )
                continue
            if self.target == "c" and isinstance(definition, MIREnumDef):
                for variant in definition.variants:
                    has_unsupported_payload = any(
                        not self._c_payload_compatible(payload_type)
                        for payload_type in variant.payload_types
                    )
                    has_multi_object_payload = len(variant.payload_types) > 1 and any(
                        payload_type.name not in ("int", "bool", "string")
                        or payload_type.arguments
                        or payload_type.optional
                        or payload_type.pointer
                        for payload_type in variant.payload_types
                    )
                    if has_unsupported_payload or has_multi_object_payload:
                        self._issue(
                            "MIRG1002",
                            f"The C17 MIR enum pilot permits multiple primitive payloads or "
                            f"one supported array/nominal-struct payload; "
                            f"'{definition.name}.{variant.name}' has "
                            f"{', '.join(str(item) for item in variant.payload_types) or 'no payload'}",
                            span,
                        )
                continue
            if self.target == "wasm" and isinstance(definition, MIRStructDef):
                for field in definition.fields:
                    nested = self.type_definitions.get(field.type.name)
                    if field.type not in (
                        MIRType("int"), MIRType("bool"), MIRType("string")
                    ) and not (
                        isinstance(nested, MIRStructDef)
                        and not field.type.arguments
                        and not field.type.optional
                        and not field.type.pointer
                    ):
                        self._issue(
                            "MIRG1002",
                            f"The Wasm MIR struct pilot requires int, bool, string, or nominal struct fields; "
                            f"'{definition.name}.{field.name}' is '{field.type}'",
                            span,
                        )
                continue
            if self.target == "wasm" and isinstance(definition, MIREnumDef):
                for variant in definition.variants:
                    for payload_type in variant.payload_types:
                        if (
                            payload_type not in (
                                MIRType("int"), MIRType("bool"), MIRType("string")
                            )
                            and not isinstance(self.type_definitions.get(payload_type.name), MIRStructDef)
                        ):
                            self._issue(
                                "MIRG1002",
                                f"The Wasm MIR enum pilot requires int, bool, string, or nominal struct payloads; "
                                f"'{definition.name}.{variant.name}' contains '{payload_type}'",
                                span,
                            )
                    if len(variant.payload_types) > 1 and any(
                        payload_type != MIRType("int") for payload_type in variant.payload_types
                    ):
                        self._issue(
                            "MIRG1002",
                            f"The Wasm MIR enum pilot permits non-int payloads only as a single payload; "
                            f"'{definition.name}.{variant.name}' has {len(variant.payload_types)} payloads",
                            span,
                        )
                continue
            if self.target in {"cpp", "rust", "js", "python"} and isinstance(definition, MIRStructDef):
                for field in definition.fields:
                    self._type(field.type, span)
                continue
            if self.target in {"cpp", "rust", "js", "python"} and isinstance(definition, MIREnumDef):
                for variant in definition.variants:
                    for payload_type in variant.payload_types:
                        self._type(payload_type, span)
                continue
            kind = "enum" if isinstance(definition, MIREnumDef) else "aggregate"
            self._issue(
                "MIRG1002",
                f"Target '{self.target}' MIR pilot does not yet legalize {kind} type '{definition.name}'",
                span,
            )
        for function in self.module.functions:
            self._function(function)
        return tuple(self.issues)

    def _function(self, function: MIRFunction) -> None:
        assert self.profile is not None
        effects = function.effects or self.inferred_effects.get(function.symbol, ())
        illegal_effects = tuple(
            effect for effect in effects if effect not in self.profile.legal_effects
        )
        if illegal_effects:
            self._issue(
                "MIRG1011",
                f"Function '{function.name}' requires effects {illegal_effects} that are not legal for target '{self.target}'",
                function.span,
            )
        self.local_types = {local.id: local.type for local in function.locals}
        self.wasm_tag_locals = self._wasm_discriminant_locals(function) if self.target == "wasm" else {}
        discarded_any = {
            terminator.destination.local
            for block in function.blocks
            for terminator in (block.terminator,)
            if isinstance(terminator, CallTerminator)
            and terminator.destination is not None
            and terminator.function in self.user_functions
            and any(
                candidate.symbol == terminator.function
                and candidate.name == "main"
                and candidate.locals[candidate.return_local].type.name == "any"
                for candidate in self.module.functions
            )
        }
        for local in function.locals:
            if self.target == "wasm" and local.id in self.wasm_tag_locals:
                continue
            if local.type.name == "any" and local.id == function.return_local and function.name == "main":
                continue
            if local.type.name == "any" and local.id in discarded_any:
                continue
            self._type(local.type, local.span)
        for block in function.blocks:
            for statement in block.statements:
                name = type(statement).__name__
                if name not in self.profile.legal_statements:
                    self._issue("MIRG1003", f"Statement '{name}' is not legal for target '{self.target}'", statement.span)
                    continue
                if isinstance(statement, AssignStatement):
                    self._place(statement.place, statement.span)
                    self._rvalue(statement.value, statement.span)
                elif isinstance(statement, (RetainStatement, ReleaseStatement, DeinitStatement)):
                    self._place(statement.place, statement.span)
            terminator = block.terminator
            name = type(terminator).__name__
            if name not in self.profile.legal_terminators:
                self._issue("MIRG1006", f"Terminator '{name}' is not legal for target '{self.target}'", terminator.span)
                continue
            self._terminator(terminator)
        self.local_types = {}
        self.wasm_tag_locals = {}

    def _rvalue(self, value: object, span: MIRSpan) -> None:
        assert self.profile is not None
        name = type(value).__name__
        if name not in self.profile.legal_rvalues:
            self._issue("MIRG1004", f"Rvalue '{name}' is not legal for target '{self.target}'", span)
            return
        if isinstance(value, UseRValue):
            self._operand(value.operand, span)
        elif isinstance(value, BinaryRValue):
            self._operand(value.left, span)
            self._operand(value.right, span)
            self._type(value.type, span)
            if value.op not in self.profile.legal_binary_ops:
                self._issue(
                    "MIRG1010",
                    f"Binary operation '{value.op}' is not legal for target '{self.target}'",
                    span,
                )
        elif isinstance(value, UnaryRValue):
            self._operand(value.operand, span)
            self._type(value.type, span)
            if value.op not in self.profile.legal_unary_ops:
                self._issue(
                    "MIRG1010",
                    f"Unary operation '{value.op}' is not legal for target '{self.target}'",
                    span,
                )
        elif isinstance(value, CastRValue):
            self._operand(value.operand, span)
            self._type(value.type, span)
            if self.target == "wasm":
                source_type = self._operand_mir_type(value.operand)
                if not (
                    source_type == value.type
                    or (
                        self._wasm_result_compatible(source_type)
                        and self._wasm_result_compatible(value.type)
                    )
                ):
                    self._issue(
                        "MIRG1004",
                        f"Wasm MIR cast '{source_type}' -> '{value.type}' is not legalized",
                        span,
                    )
        elif isinstance(value, AggregateRValue):
            allowed_kinds = {
                "cpp": {"array", "struct", "enum", "option", "result"},
                "wasm": {"array", "struct", "enum", "result"},
                "rust": {"array", "struct", "enum"},
                "js": {"array", "struct", "enum", "option", "result"},
                "python": {"array", "struct", "enum", "option", "result"},
                "c": {"array", "struct", "enum", "option", "result"},
            }.get(self.target, set())
            if value.kind not in allowed_kinds:
                self._issue(
                    "MIRG1004",
                    f"Aggregate kind '{value.kind}' is not legal for target '{self.target}'",
                    span,
                )
            for operand in value.operands:
                self._operand(operand, span)
            self._type(value.type, span)
        elif isinstance(value, DiscriminantRValue):
            self._operand(value.operand, span)
            if self.target != "wasm":
                self._type(value.type, span)
        elif isinstance(value, PayloadRValue):
            self._operand(value.operand, span)
            self._type(value.type, span)
        elif isinstance(value, BorrowRValue):
            self._place(value.place, span)
            self._type(value.type, span)

    def _terminator(self, value: object) -> None:
        if isinstance(value, (SwitchIntTerminator, SwitchValueTerminator)):
            self._operand(value.discriminator, value.span)
            if self.target == "wasm" and isinstance(value, SwitchValueTerminator):
                local = (
                    value.discriminator.place.local
                    if isinstance(value.discriminator, (CopyOperand, MoveOperand))
                    and not value.discriminator.place.projections
                    else None
                )
                mapping = self.wasm_tag_locals.get(local if local is not None else -1)
                if mapping is None or any(expected not in mapping for expected, _ in value.targets):
                    self._issue(
                        "MIRG1006",
                        "Wasm SwitchValue requires a legalized nominal-enum discriminant",
                        value.span,
                    )
        elif isinstance(value, CallTerminator):
            for argument in value.arguments:
                self._operand(argument, value.span)
            if value.destination is not None:
                self._place(value.destination, value.span)
            has_unwind = value.unwind is not None or value.error_destination is not None
            valid_cpp_unwind = (
                self.target in {"cpp", "js", "python"}
                and value.unwind is not None
                and value.error_destination is not None
            )
            if has_unwind and not valid_cpp_unwind:
                self._issue(
                    "MIRG1008",
                    f"Unwind edges are not legalized by the '{self.target}' MIR pilot",
                    value.span,
                )
            if value.function not in self.user_functions and value.function not in self.profile.legal_runtime_calls:
                self._issue(
                    "MIRG1007",
                    f"Runtime call '{value.function}' is not legal for target '{self.target}'",
                    value.span,
                )
        elif isinstance(value, AssertTerminator):
            self._operand(value.condition, value.span)
            if value.unwind is not None:
                self._issue(
                    "MIRG1008",
                    f"Unwind edges are not legalized by the '{self.target}' MIR pilot",
                    value.span,
                )
        elif isinstance(value, ThrowTerminator):
            self._operand(value.value, value.span)
            if value.destination is not None:
                self._place(value.destination, value.span)
        elif isinstance(value, DropTerminator):
            self._place(value.place, value.span)
            if value.unwind is not None:
                self._issue(
                    "MIRG1008",
                    f"Unwind edges are not legalized by the '{self.target}' MIR pilot",
                    value.span,
                )

    def _operand(self, value: object, span: MIRSpan) -> None:
        if isinstance(value, ConstOperand):
            self._type(value.type, span)
        elif isinstance(value, (CopyOperand, MoveOperand)):
            self._place(value.place, span)

    def _place(self, place: Place, span: MIRSpan) -> None:
        assert self.profile is not None
        if self.target == "wasm" and place.projections:
            if all(isinstance(projection, FieldProjection) for projection in place.projections):
                value_type = self.local_types.get(place.local)
                for projection in place.projections:
                    definition = self.type_definitions.get(value_type.name if value_type else "")
                    field = next(
                        (item for item in definition.fields if item.name == projection.name),
                        None,
                    ) if isinstance(definition, MIRStructDef) else None
                    if field is None:
                        self._issue(
                            "MIRG1005",
                            f"The Wasm MIR field pilot requires a known field, got "
                            f"'{value_type}.{projection.name}'",
                            span,
                        )
                        break
                    value_type = field.type
            elif not all(
                isinstance(projection, (IndexProjection, ConstantIndexProjection))
                for projection in place.projections
            ):
                self._issue(
                    "MIRG1005",
                    "The Wasm MIR aggregate pilot supports a field chain or an index projection chain",
                    span,
                )
            else:
                value_type = self.local_types.get(place.local)
                for projection in place.projections:
                    if value_type is None or value_type.name != "Array" or len(value_type.arguments) != 1:
                        self._issue(
                            "MIRG1005",
                            f"The Wasm MIR index pilot requires an Array<T> at every index, got '{value_type}'",
                            span,
                        )
                        break
                    value_type = value_type.arguments[0]
        if self.target == "c" and place.projections:
            base_type = self.local_types.get(place.local)
            projection = place.projections[0]
            valid = False
            if len(place.projections) == 1 and isinstance(projection, FieldProjection):
                definition = self.type_definitions.get(base_type.name if base_type else "")
                field = next(
                    (item for item in definition.fields if item.name == projection.name),
                    None,
                ) if isinstance(definition, MIRStructDef) else None
                valid = field is not None and self._c_value_field_compatible(field.type)
            else:
                value_type = base_type
                valid = True
                for item in place.projections:
                    if isinstance(item, (IndexProjection, ConstantIndexProjection)):
                        if not self._c_array_compatible(value_type):
                            valid = False
                            break
                        value_type = value_type.arguments[0]
                    elif isinstance(item, FieldProjection):
                        definition = self.type_definitions.get(value_type.name if value_type else "")
                        field = next(
                            (candidate for candidate in definition.fields if candidate.name == item.name),
                            None,
                        ) if isinstance(definition, MIRStructDef) else None
                        if field is None or not self._c_value_field_compatible(field.type):
                            valid = False
                            break
                        value_type = field.type
                    else:
                        valid = False
                        break
            if not valid:
                self._issue(
                    "MIRG1005",
                    f"The C17 MIR pilot requires known primitive fields or supported array indices, got '{base_type}'",
                    span,
                )
        for projection in place.projections:
            name = type(projection).__name__
            if name not in self.profile.legal_projections:
                self._issue(
                    "MIRG1005",
                    f"Projection '{name}' is not legal for target '{self.target}'",
                    span,
                )

    def _type(self, value: MIRType, span: MIRSpan) -> None:
        assert self.profile is not None
        if self.target in {"cpp", "rust"} and value.pointer:
            self._type(replace(value, pointer=False), span)
            return
        if self.target in {"cpp", "rust", "js", "python"} and value.optional:
            self._type(replace(value, optional=False), span)
            return
        if self.target == "wasm" and value.name == "Array" and len(value.arguments) == 1:
            element_type = value.arguments[0]
            if (
                element_type not in (MIRType("int"), MIRType("bool"), MIRType("string"))
                and not isinstance(self.type_definitions.get(element_type.name), MIRStructDef)
                and element_type not in (
                    MIRType("Array", (MIRType("int"),)),
                    MIRType("Array", (MIRType("bool"),)),
                    MIRType("Array", (MIRType("string"),)),
                )
                and not (
                    element_type.name == "Array"
                    and len(element_type.arguments) == 1
                    and isinstance(self.type_definitions.get(element_type.arguments[0].name), MIRStructDef)
                )
            ):
                self._issue(
                    "MIRG1002",
                    f"The Wasm MIR pilot supports primitive/struct arrays and nested int/string arrays, got '{value}'",
                    span,
                )
            return
        if self.target == "wasm" and value.name == "Result" and len(value.arguments) == 2:
            if not self._wasm_result_compatible(value):
                self._issue(
                    "MIRG1002",
                    f"The Wasm MIR Result pilot supports int, bool, string, and nominal struct payloads, got '{value}'",
                    span,
                )
            return
        if (
            self.target == "wasm"
            and isinstance(self.type_definitions.get(value.name), (MIRStructDef, MIREnumDef))
            and not value.arguments
        ):
            return
        if (
            self.target == "c"
            and isinstance(self.type_definitions.get(value.name), MIRStructDef)
            and not value.arguments
            and not value.optional
            and not value.pointer
        ):
            return
        if self.target == "c" and self._c_array_compatible(value):
            return
        if self.target == "c" and value.name in ("Option", "Result") and value.arguments:
            if all(
                argument.name == "any" or self._c_payload_compatible(argument)
                for argument in value.arguments
            ) and any(argument.name != "any" for argument in value.arguments):
                return
        if (
            self.target == "c"
            and isinstance(self.type_definitions.get(value.name), MIREnumDef)
            and not value.arguments
            and not value.optional
            and not value.pointer
        ):
            return
        if self.target in {"cpp", "rust", "js", "python"} and value.name == "Array" and len(value.arguments) == 1:
            self._type(value.arguments[0], span)
            return
        if self.target in {"cpp", "js", "python"} and value.name in ("Option", "Result") and value.arguments:
            for argument in value.arguments:
                if argument.name != "any":
                    self._type(argument, span)
            return
        if (
            self.target in {"cpp", "rust", "js", "python"}
            and isinstance(
                self.type_definitions.get(value.name),
                (MIRStructDef, MIREnumDef),
            )
            and not value.arguments
        ):
            return
        if value.optional or value.pointer or value.is_function or value.arguments:
            self._issue("MIRG1002", f"Type '{value}' is not legal for target '{self.target}'", span)
            return
        if value.name not in self.profile.legal_types:
            self._issue("MIRG1002", f"Type '{value}' is not legal for target '{self.target}'", span)

    def _issue(self, code: str, message: str, span: MIRSpan) -> None:
        self.issues.append(MIRLegalizationIssue(code, message, span, self.target))

    def _wasm_discriminant_locals(self, function: MIRFunction) -> dict[int, dict[str, int]]:
        result: dict[int, dict[str, int]] = {}
        for block in function.blocks:
            for statement in block.statements:
                if not isinstance(statement, AssignStatement) or statement.place.projections:
                    continue
                if not isinstance(statement.value, DiscriminantRValue):
                    continue
                operand = statement.value.operand
                if not isinstance(operand, (CopyOperand, MoveOperand)) or operand.place.projections:
                    continue
                subject_type = self.local_types.get(operand.place.local)
                definition = self.type_definitions.get(subject_type.name if subject_type else "")
                if isinstance(definition, MIREnumDef):
                    result[statement.place.local] = {
                        variant.name: index for index, variant in enumerate(definition.variants)
                    }
                elif (
                    subject_type is not None
                    and subject_type.name == "Result"
                    and self._wasm_result_compatible(subject_type)
                ):
                    result[statement.place.local] = {"Ok": 0, "Err": 1}
        return result

    def _operand_mir_type(self, operand: object) -> MIRType | None:
        if isinstance(operand, ConstOperand):
            return operand.type
        if isinstance(operand, (CopyOperand, MoveOperand)):
            value_type = self.local_types.get(operand.place.local)
            for projection in operand.place.projections:
                if value_type is None:
                    return None
                if isinstance(projection, (IndexProjection, ConstantIndexProjection)):
                    if value_type.name != "Array" or len(value_type.arguments) != 1:
                        return None
                    value_type = value_type.arguments[0]
                elif isinstance(projection, FieldProjection):
                    definition = self.type_definitions.get(value_type.name)
                    field = next(
                        (item for item in definition.fields if item.name == projection.name),
                        None,
                    ) if isinstance(definition, MIRStructDef) else None
                    if field is None:
                        return None
                    value_type = field.type
                else:
                    return None
            return value_type
        return None

    def _wasm_result_compatible(self, value_type: MIRType | None) -> bool:
        def compatible(argument: MIRType) -> bool:
            return (
                argument.name in ("int", "bool", "string", "any")
                or isinstance(self.type_definitions.get(argument.name), MIRStructDef)
            )

        return bool(
            value_type is not None
            and value_type.name == "Result"
            and len(value_type.arguments) == 2
            and all(compatible(argument) for argument in value_type.arguments)
            and any(argument.name != "any" for argument in value_type.arguments)
        )

    def _c_array_compatible(self, value_type: MIRType | None) -> bool:
        if value_type is None or value_type.name != "Array" or len(value_type.arguments) != 1:
            return False
        element = value_type.arguments[0]
        if element.optional or element.pointer:
            return False
        if element.name == "Array":
            return self._c_array_compatible(element)
        return bool(
            not element.arguments
            and (
                element.name in ("int", "bool", "string")
                or self._c_value_field_compatible(element)
            )
        )

    def _c_payload_compatible(self, value_type: MIRType) -> bool:
        if self._c_array_compatible(value_type):
            return True
        return bool(
            (
                value_type.name in ("int", "bool", "string")
                or self._c_value_field_compatible(value_type)
            )
            and not value_type.arguments
            and not value_type.optional
            and not value_type.pointer
        )

    def _c_value_field_compatible(
        self, value_type: MIRType, stack: tuple[str, ...] = ()
    ) -> bool:
        if value_type.optional or value_type.pointer:
            return False
        if value_type.name == "Array" and len(value_type.arguments) == 1:
            element = value_type
            while element.name == "Array" and len(element.arguments) == 1:
                element = element.arguments[0]
                if element.optional or element.pointer:
                    return False
            if element.arguments:
                return False
            if element.name in ("int", "bool", "string"):
                return True
            return self._c_value_field_compatible(element, stack)
        if value_type.arguments:
            return False
        if value_type.name in ("int", "bool", "string"):
            return True
        definition = self.type_definitions.get(value_type.name)
        if not isinstance(definition, MIRStructDef) or definition.name in stack:
            return False
        next_stack = stack + (definition.name,)
        return all(
            self._c_value_field_compatible(field.type, next_stack)
            for field in definition.fields
        )

    def _module_span(self) -> MIRSpan:
        if self.module.functions:
            return self.module.functions[0].span
        return MIRSpan(self.module.source_name, 1, 1)


def collect_legalization_issues(
    module: MIRModule,
    target: str,
    *,
    require_emitter: bool = False,
) -> tuple[MIRLegalizationIssue, ...]:
    verify_mir(module)
    return _Legalizer(module, target, require_emitter=require_emitter).collect()


def legalize_mir(
    module: MIRModule,
    target: str,
    *,
    require_emitter: bool = False,
) -> MIRModule:
    """Return verified target-legal MIR or raise with stable diagnostics."""
    issues = collect_legalization_issues(module, target, require_emitter=require_emitter)
    if issues:
        raise MIRLegalizationError(issues)
    return module
