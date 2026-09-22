"""Structural and type verification for experimental Nyx MIR."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from typing import Iterable

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
    DiscriminantRValue,
    DropTerminator,
    DerefProjection,
    FieldProjection,
    GotoTerminator,
    IndexProjection,
    MIRBasicBlock,
    MIRFunction,
    MIREnumDef,
    MIRModule,
    MIRSpan,
    MoveOperand,
    Operand,
    Place,
    PayloadRValue,
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
    MIRStructDef,
    MIR_SCHEMA_VERSION,
)
from .types import MIRType
from .effects import VALID_MIR_EFFECTS, infer_module_effects


@dataclass(frozen=True, slots=True)
class MIRVerificationIssue:
    code: str
    message: str
    span: MIRSpan


class MIRVerificationError(ValueError):
    def __init__(self, issues: Iterable[MIRVerificationIssue]):
        self.issues = tuple(issues)
        summary = "; ".join(f"{issue.code}: {issue.message}" for issue in self.issues)
        super().__init__(summary)


class MIRVerifier:
    def __init__(self, module: MIRModule):
        self.module = module
        self.issues: list[MIRVerificationIssue] = []
        self.type_definitions = {
            definition.name: definition
            for definition in getattr(module, "type_definitions", ())
        }
        self._ownership_issue_keys: set[tuple[str, int, int, str]] = set()
        self.inferred_effects = {
            function.symbol: function.effects
            for function in infer_module_effects(module).functions
        } if isinstance(module, MIRModule) else {}

    def collect(self) -> tuple[MIRVerificationIssue, ...]:
        if not isinstance(self.module, MIRModule):
            fallback = MIRSpan("<mir>", 1, 1)
            return (MIRVerificationIssue("MIR0000", "Root value is not MIRModule", fallback),)
        if self.module.schema_version != MIR_SCHEMA_VERSION:
            self._issue(
                "MIR0001",
                f"Unsupported MIR schema {self.module.schema_version}; expected {MIR_SCHEMA_VERSION}",
                self._module_span(),
            )
        symbols = [function.symbol for function in self.module.functions]
        if len(symbols) != len(set(symbols)):
            self._issue("MIR0002", "Function symbols must be unique", self._module_span())
        self._verify_type_definitions()
        for function in self.module.functions:
            self._verify_function(function)
        return tuple(self.issues)

    def _verify_type_definitions(self) -> None:
        definitions = getattr(self.module, "type_definitions", ())
        names = [definition.name for definition in definitions]
        symbols = [definition.symbol for definition in definitions]
        if len(names) != len(set(names)) or len(symbols) != len(set(symbols)):
            self._issue("MIR0003", "MIR type names and symbols must be unique", self._module_span())
        for definition in definitions:
            if isinstance(definition, MIRStructDef):
                field_names = [field.name for field in definition.fields]
                if len(field_names) != len(set(field_names)):
                    self._issue(
                        "MIR0004",
                        f"Struct '{definition.name}' contains duplicate fields",
                        self._module_span(),
                    )
                if any(not isinstance(field.type, MIRType) for field in definition.fields):
                    self._issue("MIR0005", f"Struct '{definition.name}' has an invalid field type", self._module_span())
            elif isinstance(definition, MIREnumDef):
                variant_names = [variant.name for variant in definition.variants]
                if len(variant_names) != len(set(variant_names)):
                    self._issue(
                        "MIR0006",
                        f"Enum '{definition.name}' contains duplicate variants",
                        self._module_span(),
                    )
                if any(
                    not isinstance(payload, MIRType)
                    for variant in definition.variants
                    for payload in variant.payload_types
                ):
                    self._issue("MIR0007", f"Enum '{definition.name}' has an invalid payload type", self._module_span())
            else:
                self._issue("MIR0008", f"Unknown MIR type definition {type(definition).__name__}", self._module_span())

    def _verify_function(self, function: MIRFunction) -> None:
        self._verify_span(function.span)
        if function.effects:
            unknown_effects = set(function.effects) - VALID_MIR_EFFECTS
            if unknown_effects:
                self._issue(
                    "MIR0110",
                    f"Function '{function.name}' declares unknown effects {sorted(unknown_effects)}",
                    function.span,
                )
            expected_effects = self.inferred_effects.get(function.symbol, ())
            if not unknown_effects and function.effects != expected_effects:
                self._issue(
                    "MIR0111",
                    f"Function '{function.name}' effect set {function.effects} does not match inferred {expected_effects}",
                    function.span,
                )
        local_ids = [local.id for local in function.locals]
        if local_ids != list(range(len(function.locals))):
            self._issue("MIR0100", "Local ids must be dense and ordered from zero", function.span)
        local_map = {local.id: local for local in function.locals}
        if function.return_local not in local_map:
            self._issue("MIR0101", "Return local does not exist", function.span)
        elif local_map[function.return_local].kind != "return":
            self._issue("MIR0102", "Return local must have kind 'return'", function.span)
        if len(function.parameters) != len(set(function.parameters)):
            self._issue("MIR0103", "Parameter local ids must be unique", function.span)
        for parameter in function.parameters:
            if parameter not in local_map:
                self._issue("MIR0104", f"Parameter local {parameter} does not exist", function.span)
            elif local_map[parameter].kind != "parameter":
                self._issue("MIR0105", f"Local {parameter} is not a parameter", function.span)
        for local in function.locals:
            self._verify_span(local.span)
            if not isinstance(local.type, MIRType):
                self._issue("MIR0106", f"Local {local.id} has an invalid type", local.span)

        if function.is_async and function.coroutine is None:
            self._issue("MIR0112", f"Async function '{function.name}' lacks coroutine metadata", function.span)
        if not function.is_async and function.coroutine is not None:
            self._issue("MIR0113", f"Synchronous function '{function.name}' carries coroutine metadata", function.span)
        if function.coroutine is not None:
            coroutine = function.coroutine
            state = local_map.get(coroutine.state_local)
            if state is None or state.kind != "coroutine-state" or state.type.name != "int":
                self._issue("MIR0114", "Coroutine state local must be an int coroutine-state local", function.span)
            for local_id in coroutine.frame_locals:
                if local_id not in local_map:
                    self._issue("MIR0114", f"Coroutine frame references unknown local {local_id}", function.span)
            point_ids = [point.id for point in coroutine.suspend_points]
            if point_ids != list(range(len(point_ids))):
                self._issue("MIR0115", "Coroutine suspend ids must be dense and ordered", function.span)
            lifecycle = (
                coroutine.start_symbol,
                coroutine.resume_symbol,
                coroutine.destroy_symbol,
            )
            if any(not symbol for symbol in lifecycle) or len(set(lifecycle)) != 3:
                self._issue("MIR0116", "Coroutine lifecycle symbols must be non-empty and distinct", function.span)

        block_ids = [block.id for block in function.blocks]
        if not function.blocks:
            self._issue("MIR0200", "Function requires an entry block", function.span)
            return
        if block_ids != list(range(len(function.blocks))):
            self._issue("MIR0201", "Block ids must be dense and ordered from zero", function.span)
        valid_blocks = set(block_ids)
        issue_count_before_blocks = len(self.issues)
        for block in function.blocks:
            self._verify_block(block, local_map, valid_blocks)
        if (
            block_ids == list(range(len(function.blocks)))
            and len(self.issues) == issue_count_before_blocks
        ):
            self._verify_ownership(function)

    def _verify_block(self, block: MIRBasicBlock, locals_by_id: dict, valid_blocks: set[int]) -> None:
        for statement in block.statements:
            span = getattr(statement, "span", self._module_span())
            self._verify_span(span)
            if isinstance(statement, AssignStatement):
                destination_type = self._place_type(statement.place, locals_by_id, span)
                value_type = self._rvalue_type(statement.value, locals_by_id, span)
                if (
                    destination_type is not None
                    and value_type is not None
                    and destination_type != value_type
                ):
                    self._issue(
                        "MIR0300",
                        f"Assignment type mismatch: {destination_type} <- {value_type}",
                        span,
                    )
            elif isinstance(statement, (StorageLiveStatement, StorageDeadStatement)):
                self._require_local(statement.local, locals_by_id, span)
            elif isinstance(statement, (RetainStatement, ReleaseStatement, DeinitStatement)):
                self._place_type(statement.place, locals_by_id, span)
            elif type(statement).__name__ != "NopStatement":
                self._issue("MIR0301", f"Unknown statement {type(statement).__name__}", span)

        terminator = block.terminator
        span = getattr(terminator, "span", self._module_span())
        self._verify_span(span)
        if isinstance(terminator, GotoTerminator):
            self._require_block(terminator.target, valid_blocks, span)
        elif isinstance(terminator, SwitchIntTerminator):
            self._operand_type(terminator.discriminator, locals_by_id, span)
            values = [value for value, _ in terminator.targets]
            if len(values) != len(set(values)):
                self._issue("MIR0400", "Switch values must be unique", span)
            for _, target in terminator.targets:
                self._require_block(target, valid_blocks, span)
            self._require_block(terminator.otherwise, valid_blocks, span)
        elif isinstance(terminator, SwitchValueTerminator):
            self._operand_type(terminator.discriminator, locals_by_id, span)
            values = [repr(value) for value, _ in terminator.targets]
            if len(values) != len(set(values)):
                self._issue("MIR0404", "Switch values must be unique", span)
            for _, target in terminator.targets:
                self._require_block(target, valid_blocks, span)
            self._require_block(terminator.otherwise, valid_blocks, span)
        elif isinstance(terminator, CallTerminator):
            for argument in terminator.arguments:
                self._operand_type(argument, locals_by_id, span)
            if terminator.destination is not None:
                self._place_type(terminator.destination, locals_by_id, span)
                if terminator.target is None:
                    self._issue("MIR0401", "Call destination requires a continuation target", span)
            if terminator.target is not None:
                self._require_block(terminator.target, valid_blocks, span)
            if terminator.unwind is not None:
                self._require_block(terminator.unwind, valid_blocks, span)
                if terminator.error_destination is None:
                    self._issue("MIR0405", "Unwind edge requires an error destination", span)
            if terminator.error_destination is not None:
                self._place_type(terminator.error_destination, locals_by_id, span)
        elif isinstance(terminator, DropTerminator):
            self._place_type(terminator.place, locals_by_id, span)
            self._require_block(terminator.target, valid_blocks, span)
            if terminator.unwind is not None:
                self._require_block(terminator.unwind, valid_blocks, span)
        elif isinstance(terminator, AssertTerminator):
            condition_type = self._operand_type(terminator.condition, locals_by_id, span)
            if condition_type is not None and condition_type.name != "bool":
                self._issue("MIR0402", "Assert condition must be bool", span)
            self._require_block(terminator.target, valid_blocks, span)
            if terminator.unwind is not None:
                self._require_block(terminator.unwind, valid_blocks, span)
        elif isinstance(terminator, ThrowTerminator):
            self._operand_type(terminator.value, locals_by_id, span)
            if terminator.target is not None:
                self._require_block(terminator.target, valid_blocks, span)
                if terminator.destination is None:
                    self._issue("MIR0406", "Caught throw requires an error destination", span)
            if terminator.destination is not None:
                self._place_type(terminator.destination, locals_by_id, span)
        elif isinstance(terminator, SuspendTerminator):
            task_type = self._operand_type(terminator.task, locals_by_id, span)
            destination_type = self._place_type(terminator.destination, locals_by_id, span)
            if task_type is not None:
                if task_type.name != "Task" or len(task_type.arguments) != 1:
                    self._issue("MIR0407", f"Suspend operand must be Task<T>, got {task_type}", span)
                elif destination_type is not None and destination_type != task_type.arguments[0]:
                    self._issue(
                        "MIR0407",
                        f"Suspend destination type {destination_type} does not match {task_type.arguments[0]}",
                        span,
                    )
            self._require_block(terminator.resume, valid_blocks, span)
            if terminator.unwind is not None:
                self._require_block(terminator.unwind, valid_blocks, span)
                if terminator.error_destination is None:
                    self._issue("MIR0408", "Suspend unwind requires an error destination", span)
            if terminator.error_destination is not None:
                self._place_type(terminator.error_destination, locals_by_id, span)
            if terminator.suspend_id < 0:
                self._issue("MIR0115", "Suspend id must be non-negative", span)
        elif not isinstance(terminator, (ReturnTerminator, UnreachableTerminator)):
            self._issue("MIR0403", "Block requires exactly one known terminator", span)

    def _rvalue_type(self, value: object, locals_by_id: dict, span: MIRSpan) -> MIRType | None:
        if isinstance(value, UseRValue):
            return self._operand_type(value.operand, locals_by_id, span)
        if isinstance(value, BinaryRValue):
            self._operand_type(value.left, locals_by_id, span)
            self._operand_type(value.right, locals_by_id, span)
            return value.type
        if isinstance(value, UnaryRValue):
            self._operand_type(value.operand, locals_by_id, span)
            return value.type
        if isinstance(value, CastRValue):
            self._operand_type(value.operand, locals_by_id, span)
            return value.type
        if isinstance(value, BorrowRValue):
            self._place_type(value.place, locals_by_id, span)
            if not value.type.pointer:
                self._issue("MIR0504", "Borrow rvalue must produce a pointer type", span)
            return value.type
        if isinstance(value, AggregateRValue):
            for operand in value.operands:
                self._operand_type(operand, locals_by_id, span)
            if value.fields and len(value.fields) != len(value.operands):
                self._issue("MIR0505", "Aggregate field and operand counts differ", span)
            if value.kind == "struct":
                definition = self.type_definitions.get(value.name)
                if not isinstance(definition, MIRStructDef):
                    self._issue("MIR0506", f"Unknown MIR struct aggregate '{value.name}'", span)
                elif len(definition.fields) != len(value.operands):
                    self._issue(
                        "MIR0507",
                        f"Struct '{value.name}' expects {len(definition.fields)} fields, got {len(value.operands)}",
                        span,
                    )
            return value.type
        if isinstance(value, DiscriminantRValue):
            self._operand_type(value.operand, locals_by_id, span)
            return value.type
        if isinstance(value, PayloadRValue):
            self._operand_type(value.operand, locals_by_id, span)
            if value.index < 0:
                self._issue("MIR0503", "Payload index must be non-negative", span)
            return value.type
        self._issue("MIR0500", f"Unknown rvalue {type(value).__name__}", span)
        return None

    def _operand_type(self, operand: Operand, locals_by_id: dict, span: MIRSpan) -> MIRType | None:
        if isinstance(operand, ConstOperand):
            if not isinstance(operand.type, MIRType):
                self._issue("MIR0502", "Constant operand has an invalid type", span)
                return None
            return operand.type
        if isinstance(operand, (CopyOperand, MoveOperand)):
            return self._place_type(operand.place, locals_by_id, span)
        self._issue("MIR0501", f"Unknown operand {type(operand).__name__}", span)
        return None

    def _place_type(self, place: Place, locals_by_id: dict, span: MIRSpan) -> MIRType | None:
        local = self._require_local(place.local, locals_by_id, span)
        current = local.type if local is not None else None
        for projection in place.projections:
            if isinstance(projection, IndexProjection):
                index_local = self._require_local(projection.local, locals_by_id, span)
                if index_local is not None and index_local.type.name not in (
                    "int", "i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "uintptr"
                ):
                    self._issue("MIR0603", "Index projection local must be an integer", span)
                current = self._indexed_type(current, span)
            elif isinstance(projection, ConstantIndexProjection):
                if projection.index < 0:
                    self._issue("MIR0604", "Constant index projection must be non-negative", span)
                current = self._indexed_type(current, span)
            elif isinstance(projection, FieldProjection):
                definition = self.type_definitions.get(current.name if current is not None else "")
                if not isinstance(definition, MIRStructDef):
                    self._issue("MIR0605", f"Field projection requires a known struct, got {current}", span)
                    current = None
                else:
                    field = next((item for item in definition.fields if item.name == projection.name), None)
                    if field is None:
                        self._issue(
                            "MIR0606",
                            f"Struct '{definition.name}' has no field '{projection.name}'",
                            span,
                        )
                        current = None
                    else:
                        current = field.type
            elif isinstance(projection, DerefProjection):
                if current is None or not current.pointer:
                    self._issue("MIR0607", f"Dereference requires a pointer type, got {current}", span)
                    current = None
                else:
                    current = replace(current, pointer=False)
            elif isinstance(projection, VariantProjection):
                definition = self.type_definitions.get(current.name if current is not None else "")
                if not isinstance(definition, MIREnumDef):
                    self._issue("MIR0608", f"Variant projection requires a known enum, got {current}", span)
                    current = None
                else:
                    variant = next((item for item in definition.variants if item.name == projection.name), None)
                    if variant is None or projection.index < 0 or projection.index >= len(variant.payload_types):
                        self._issue(
                            "MIR0609",
                            f"Invalid payload projection {projection.name}.{projection.index}",
                            span,
                        )
                        current = None
                    else:
                        current = variant.payload_types[projection.index]
            else:
                self._issue("MIR0602", f"Unknown place projection {type(projection).__name__}", span)
                current = None
        return current

    def _indexed_type(self, current: MIRType | None, span: MIRSpan) -> MIRType | None:
        if current is None:
            return None
        if current.name == "Array" and current.arguments:
            return current.arguments[0]
        if current.name == "string":
            return MIRType("char")
        self._issue("MIR0610", f"Index projection requires Array<T> or string, got {current}", span)
        return None

    def _verify_ownership(self, function: MIRFunction) -> None:
        """Run conservative definite-initialization and move-state analysis."""
        initial = ["uninit"] * len(function.locals)
        for parameter in function.parameters:
            initial[parameter] = "init"
        incoming: dict[int, tuple[str, ...]] = {0: tuple(initial)}
        worklist = deque([0])
        in_worklist = {0}
        while worklist:
            block_id = worklist.popleft()
            in_worklist.remove(block_id)
            state = list(incoming[block_id])
            edges = self._ownership_transfer(function.blocks[block_id], state, report=False)
            for target, edge_state in edges:
                previous = incoming.get(target)
                merged = edge_state if previous is None else tuple(
                    left if left == right else "maybe"
                    for left, right in zip(previous, edge_state)
                )
                if previous != merged:
                    incoming[target] = merged
                    if target not in in_worklist:
                        worklist.append(target)
                        in_worklist.add(target)

        for block in function.blocks:
            state = incoming.get(block.id)
            if state is not None:
                self._ownership_transfer(block, list(state), report=True)

    def _ownership_transfer(
        self,
        block: MIRBasicBlock,
        state: list[str],
        *,
        report: bool,
    ) -> list[tuple[int, tuple[str, ...]]]:
        for statement in block.statements:
            span = statement.span
            if isinstance(statement, AssignStatement):
                self._ownership_rvalue(statement.value, state, span, report)
                if statement.place.projections:
                    self._ownership_require(statement.place, state, span, report, "write")
                else:
                    state[statement.place.local] = "init"
            elif isinstance(statement, StorageLiveStatement):
                state[statement.local] = "uninit"
            elif isinstance(statement, StorageDeadStatement):
                state[statement.local] = "dead"
            elif isinstance(statement, (RetainStatement, ReleaseStatement)):
                self._ownership_require(statement.place, state, span, report, "ownership operation")
            elif isinstance(statement, DeinitStatement):
                self._ownership_consume(statement.place, state, span, report, "deinit")

        terminator = block.terminator
        span = terminator.span
        if isinstance(terminator, GotoTerminator):
            return [(terminator.target, tuple(state))]
        if isinstance(terminator, (SwitchIntTerminator, SwitchValueTerminator)):
            self._ownership_operand(terminator.discriminator, state, span, report)
            targets = [target for _, target in terminator.targets] + [terminator.otherwise]
            return [(target, tuple(state)) for target in dict.fromkeys(targets)]
        if isinstance(terminator, CallTerminator):
            for argument in terminator.arguments:
                self._ownership_operand(argument, state, span, report)
            edges: list[tuple[int, tuple[str, ...]]] = []
            if terminator.target is not None:
                normal = list(state)
                if terminator.destination is not None and not terminator.destination.projections:
                    normal[terminator.destination.local] = "init"
                elif terminator.destination is not None:
                    self._ownership_require(terminator.destination, normal, span, report, "call destination")
                edges.append((terminator.target, tuple(normal)))
            if terminator.unwind is not None:
                unwind = list(state)
                if terminator.error_destination is not None and not terminator.error_destination.projections:
                    unwind[terminator.error_destination.local] = "init"
                elif terminator.error_destination is not None:
                    self._ownership_require(terminator.error_destination, unwind, span, report, "unwind destination")
                edges.append((terminator.unwind, tuple(unwind)))
            return edges
        if isinstance(terminator, DropTerminator):
            dropped = list(state)
            self._ownership_consume(terminator.place, dropped, span, report, "drop")
            edges = [(terminator.target, tuple(dropped))]
            if terminator.unwind is not None:
                edges.append((terminator.unwind, tuple(dropped)))
            return edges
        if isinstance(terminator, AssertTerminator):
            self._ownership_operand(terminator.condition, state, span, report)
            edges = [(terminator.target, tuple(state))]
            if terminator.unwind is not None:
                edges.append((terminator.unwind, tuple(state)))
            return edges
        if isinstance(terminator, ThrowTerminator):
            self._ownership_operand(terminator.value, state, span, report)
            if terminator.target is None:
                return []
            caught = list(state)
            if terminator.destination is not None and not terminator.destination.projections:
                caught[terminator.destination.local] = "init"
            elif terminator.destination is not None:
                self._ownership_require(terminator.destination, caught, span, report, "throw destination")
            return [(terminator.target, tuple(caught))]
        if isinstance(terminator, SuspendTerminator):
            self._ownership_operand(terminator.task, state, span, report)
            resumed = list(state)
            if terminator.destination.projections:
                self._ownership_require(
                    terminator.destination, resumed, span, report, "suspend destination",
                )
            else:
                resumed[terminator.destination.local] = "init"
            edges = [(terminator.resume, tuple(resumed))]
            if terminator.unwind is not None:
                failed = list(state)
                if terminator.error_destination is not None and not terminator.error_destination.projections:
                    failed[terminator.error_destination.local] = "init"
                edges.append((terminator.unwind, tuple(failed)))
            return edges
        return []

    def _ownership_rvalue(
        self,
        value: object,
        state: list[str],
        span: MIRSpan,
        report: bool,
    ) -> None:
        if isinstance(value, UseRValue):
            self._ownership_operand(value.operand, state, span, report)
        elif isinstance(value, BinaryRValue):
            self._ownership_operand(value.left, state, span, report)
            self._ownership_operand(value.right, state, span, report)
        elif isinstance(value, UnaryRValue):
            self._ownership_operand(value.operand, state, span, report)
        elif isinstance(value, CastRValue):
            self._ownership_operand(value.operand, state, span, report)
        elif isinstance(value, AggregateRValue):
            for operand in value.operands:
                self._ownership_operand(operand, state, span, report)
        elif isinstance(value, BorrowRValue):
            self._ownership_require(value.place, state, span, report, "borrow")
        elif isinstance(value, (DiscriminantRValue, PayloadRValue)):
            self._ownership_operand(value.operand, state, span, report)

    def _ownership_operand(
        self,
        operand: Operand,
        state: list[str],
        span: MIRSpan,
        report: bool,
    ) -> None:
        if isinstance(operand, CopyOperand):
            self._ownership_require(operand.place, state, span, report, "copy")
        elif isinstance(operand, MoveOperand):
            self._ownership_consume(operand.place, state, span, report, "move")

    def _ownership_require(
        self,
        place: Place,
        state: list[str],
        span: MIRSpan,
        report: bool,
        operation: str,
    ) -> bool:
        if place.local < 0 or place.local >= len(state):
            return False
        value_state = state[place.local]
        if value_state == "init":
            return True
        if not report:
            return False
        if value_state == "moved":
            code, detail = "MIR0801", "moved"
        elif value_state == "dead":
            code, detail = "MIR0802", "storage-dead"
        elif value_state == "maybe":
            code, detail = "MIR0803", "not initialized on every incoming path"
        else:
            code, detail = "MIR0800", "uninitialized"
        self._ownership_issue(
            code,
            f"Cannot {operation} {detail} place _{place.local}",
            span,
        )
        return False

    def _ownership_consume(
        self,
        place: Place,
        state: list[str],
        span: MIRSpan,
        report: bool,
        operation: str,
    ) -> None:
        if place.local < 0 or place.local >= len(state):
            return
        if state[place.local] != "init":
            if report and operation in ("drop", "deinit") and state[place.local] == "moved":
                self._ownership_issue(
                    "MIR0804",
                    f"Cannot {operation} already moved place _{place.local}",
                    span,
                )
            else:
                self._ownership_require(place, state, span, report, operation)
            return
        state[place.local] = "moved"

    def _ownership_issue(self, code: str, message: str, span: MIRSpan) -> None:
        key = (code, span.line, span.column, message)
        if key not in self._ownership_issue_keys:
            self._ownership_issue_keys.add(key)
            self._issue(code, message, span)

    def _require_local(self, local_id: int, locals_by_id: dict, span: MIRSpan):
        local = locals_by_id.get(local_id)
        if local is None:
            self._issue("MIR0600", f"Unknown local {local_id}", span)
        return local

    def _require_block(self, block_id: int, valid_blocks: set[int], span: MIRSpan) -> None:
        if block_id not in valid_blocks:
            self._issue("MIR0601", f"Unknown block {block_id}", span)

    def _verify_span(self, span: object) -> None:
        if not isinstance(span, MIRSpan):
            self._issue("MIR0700", "Invalid source span", self._module_span())
        elif span.line < 1 or span.column < 1 or span.length < 1:
            self._issue("MIR0701", "Source span coordinates must be positive", span)

    def _module_span(self) -> MIRSpan:
        if self.module.functions:
            return self.module.functions[0].span
        return MIRSpan(self.module.source_name or "<mir>", 1, 1)

    def _issue(self, code: str, message: str, span: MIRSpan) -> None:
        self.issues.append(MIRVerificationIssue(code, message, span))


def collect_mir_issues(module: MIRModule) -> tuple[MIRVerificationIssue, ...]:
    return MIRVerifier(module).collect()


def verify_mir(module: MIRModule) -> MIRModule:
    issues = collect_mir_issues(module)
    if issues:
        raise MIRVerificationError(issues)
    return module
