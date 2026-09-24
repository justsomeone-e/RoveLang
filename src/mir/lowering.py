"""Deliberately narrow Typed HIR to MIR skeleton lowering for M1.

M2 owns expression and control-flow lowering. M1 only proves declarations,
locals, blocks, terminators, serialization, and verification without fabricating
semantics for function bodies.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass

from src.ir.model import (
    IRAssign,
    IRArray,
    IRAssert,
    IRAwait,
    IRBinary,
    IRBreak,
    IRCall,
    IRConditional,
    IRContinue,
    IRDefer,
    IRExpr,
    IRExprStatement,
    IRFunction,
    IRFor,
    IRGuard,
    IRIf,
    IRIndexAccess,
    IRLiteral,
    IRMatch,
    IRMatchExpression,
    IRModule,
    IRMemberAccess,
    IRNullCoalesce,
    IRReference,
    IRReturn,
    IRResultPropagate,
    IRStatement,
    IRThrow,
    IRTryCatch,
    IRUnary,
    IRVarDecl,
    IRWhile,
    IREnum,
    IREnumMember,
    IRStruct,
    SourceSpan,
)
from src.ir.types import ANY, BOOL, INT, STRING, VOID, IRType, is_coercible
from src.ir.instances import materialize_generic_instances
from src.ir.dispatch import materialize_static_dispatch

from .builder import MIRFunctionBuilder
from .model import (
    AssertTerminator,
    AggregateRValue,
    AssignStatement,
    BinaryRValue,
    CastRValue,
    CallTerminator,
    ConstantIndexProjection,
    ConstOperand,
    CopyOperand,
    DeinitStatement,
    DiscriminantRValue,
    GotoTerminator,
    FieldProjection,
    IndexProjection,
    MIREnumDef,
    MIREnumVariant,
    MIRField,
    MIRModule,
    MIRSpan,
    MIRStructDef,
    MoveOperand,
    Operand,
    PayloadRValue,
    Place,
    ReturnTerminator,
    SwitchIntTerminator,
    SwitchValueTerminator,
    SuspendTerminator,
    ThrowTerminator,
    UnaryRValue,
    UseRValue,
)
from .types import from_hir_type
from .coroutines import elaborate_coroutines
from .verifier import _verify_and_infer_mir


class MIRLoweringError(ValueError):
    def __init__(self, message: str, span: MIRSpan):
        self.message = message
        self.span = span
        super().__init__(f"{span.source}:{span.line}:{span.column}: {message}")


def _span(value: SourceSpan) -> MIRSpan:
    return MIRSpan(value.source, value.line, value.column, value.length)


def _walk_hir(value: object):
    if isinstance(value, (str, bytes, int, float, bool, type(None))):
        return
    if is_dataclass(value):
        yield value
        for field in fields(value):
            yield from _walk_hir(getattr(value, field.name))
        return
    if isinstance(value, (tuple, list)):
        for item in value:
            yield from _walk_hir(item)


def _throwing_function_symbols(
    functions: tuple[IRFunction, ...],
) -> frozenset[str]:
    known = {function.symbol for function in functions}
    direct: dict[str, bool] = {}
    calls: dict[str, set[str]] = {}
    for function in functions:
        nodes = tuple(_walk_hir(function.body))
        direct[function.symbol] = any(isinstance(node, IRThrow) for node in nodes)
        calls[function.symbol] = {
            node.callee_symbol
            for node in nodes
            if isinstance(node, IRCall) and node.callee_symbol in known
        }
    throwing = {symbol for symbol, value in direct.items() if value}
    changed = True
    while changed:
        changed = False
        for symbol, callees in calls.items():
            if symbol not in throwing and any(callee in throwing for callee in callees):
                throwing.add(symbol)
                changed = True
    return frozenset(throwing)


def lower_hir_skeleton(hir: IRModule) -> MIRModule:
    """Lower the semantics-free M1 subset and reject everything assigned to M2+."""
    top_level_statements = tuple(item for item in hir.items if isinstance(item, IRStatement))
    if top_level_statements:
        span = _span(top_level_statements[0].span)
        raise MIRLoweringError("M1 does not lower top-level executable statements", span)

    functions = []
    for item in hir.items:
        if not isinstance(item, IRFunction):
            continue
        span = _span(item.span)
        if item.body:
            raise MIRLoweringError(
                f"M1 only lowers empty function bodies; '{item.name}' requires M2 lowering",
                span,
            )
        builder = MIRFunctionBuilder(
            item.name,
            item.symbol,
            from_hir_type(item.return_type),
            span,
            is_async=item.is_async,
        )
        for parameter in item.params:
            builder.new_local(
                parameter.name,
                from_hir_type(parameter.type),
                kind="parameter",
                span=span,
            )
        entry = builder.new_block()
        builder.set_terminator(entry, ReturnTerminator(span))
        functions.append(builder.finish())

    module = elaborate_coroutines(MIRModule(hir.source_name, hir.target, tuple(functions)))
    return _verify_and_infer_mir(module)


class _FunctionLowerer:
    def __init__(
        self,
        function: IRFunction,
        structs: dict[str, IRStruct],
        enums: dict[str, IREnum],
        variants: dict[str, tuple[IREnum, IREnumMember]],
        throwing_functions: frozenset[str],
        async_functions: frozenset[str],
    ):
        self.function = function
        self.structs = structs
        self.enums = enums
        self.variants = variants
        self.throwing_functions = throwing_functions
        self.async_functions = async_functions
        self.span = _span(function.span)
        self.builder = MIRFunctionBuilder(
            function.name,
            function.symbol,
            from_hir_type(function.return_type),
            self.span,
            is_async=function.is_async,
        )
        self.locals: dict[str, int] = {}
        self.current: int | None = None
        self.loop_targets: list[tuple[int, int, int]] = []
        self.defer_scopes: list[list[IRExpr]] = []
        self.drop_scopes: list[list[int]] = []
        self.drop_spans: dict[int, MIRSpan] = {}
        self.active_cleanup_frames: set[int] = set()
        self.structs_by_name = {item.name: item for item in structs.values()}
        self.enums_by_name = {item.name: item for item in enums.values()}
        self.exception_targets: list[tuple[int, Place, int]] = []
        self.temporary_locals: set[int] = set()
        self.temporary_counter = 0
        self.suspend_counter = 0

    def lower(self):
        parameter_drops: list[int] = []
        for parameter in self.function.params:
            local = self.builder.new_local(
                parameter.name,
                from_hir_type(parameter.type),
                kind="parameter",
                span=_span(parameter.default.span) if parameter.default is not None else self.span,
            )
            self.locals[parameter.symbol] = local
            if self._type_needs_drop(parameter.type):
                parameter_drops.append(local)
                self.drop_spans[local] = self.span
        self.current = self.builder.new_block()
        self._lower_scoped(self.function.body, parameter_drops)
        if self.current is not None and not self.builder.is_terminated(self.current):
            self.builder.set_terminator(self.current, ReturnTerminator(self.span))
        return self.builder.finish()

    def _lower_statements(self, statements: tuple[IRStatement, ...]) -> None:
        for statement in statements:
            if self.current is None:
                break
            self._lower_statement(statement)

    def _lower_scoped(
        self,
        statements: tuple[IRStatement, ...],
        initial_drop_locals: list[int] | tuple[int, ...] = (),
    ) -> None:
        self.defer_scopes.append([])
        self.drop_scopes.append(list(initial_drop_locals))
        try:
            self._lower_statements(statements)
            if self.current is not None:
                self._emit_cleanup_frame(len(self.defer_scopes) - 1)
        finally:
            self.defer_scopes.pop()
            self.drop_scopes.pop()

    def _lower_statement(self, node: IRStatement) -> None:
        span = _span(node.span)
        if isinstance(node, IRVarDecl):
            local = self.builder.new_local(node.name, from_hir_type(node.type), "variable", span)
            self.locals[node.symbol] = local
            value = self._lower_expr(node.expr)
            value = self._coerce(value, node.expr.type, node.type, span)
            value = self._consume_temporary(value, node.type)
            self._push(AssignStatement(Place(local), UseRValue(value), span))
            self._register_drop(local, node.type, span)
            return
        if isinstance(node, IRAssign):
            target = self._lower_place(node.target)
            value = self._lower_expr(node.expr)
            value = self._coerce(value, node.expr.type, node.target.type, span)
            value = self._consume_temporary(value, node.target.type)
            if self._type_needs_drop(node.target.type):
                self._push(DeinitStatement(target, span))
            self._push(AssignStatement(target, UseRValue(value), span))
            return
        if isinstance(node, IRExprStatement):
            value = self._lower_expr(node.expr)
            self._discard_temporary(value, node.expr.type, span)
            return
        if isinstance(node, IRReturn):
            if node.expr is not None:
                value = self._lower_expr(node.expr)
                value = self._coerce(value, node.expr.type, self.function.return_type, span)
                value = self._consume_temporary(value, self.function.return_type)
                self._push(AssignStatement(Place(0), UseRValue(value), span))
            self._emit_cleanups(0)
            self._terminate(ReturnTerminator(span))
            return
        if isinstance(node, IRIf):
            self._lower_if(node)
            return
        if isinstance(node, IRWhile):
            self._lower_while(node)
            return
        if isinstance(node, IRBreak):
            if not self.loop_targets:
                raise MIRLoweringError("break used outside a MIR loop", span)
            break_target, _, keep_depth = self.loop_targets[-1]
            self._emit_cleanups(keep_depth)
            self._terminate(GotoTerminator(break_target, span))
            return
        if isinstance(node, IRContinue):
            if not self.loop_targets:
                raise MIRLoweringError("continue used outside a MIR loop", span)
            _, continue_target, keep_depth = self.loop_targets[-1]
            self._emit_cleanups(keep_depth)
            self._terminate(GotoTerminator(continue_target, span))
            return
        if isinstance(node, IRFor):
            self._lower_for(node)
            return
        if isinstance(node, IRDefer):
            if not self.defer_scopes:
                raise MIRLoweringError("defer requires a lexical scope", span)
            self.defer_scopes[-1].append(node.expr)
            return
        if isinstance(node, IRGuard):
            self._lower_guard(node)
            return
        if isinstance(node, IRThrow):
            value = self._lower_expr(node.expr)
            # Cleanup may deinitialize the source local before the throw edge
            # reads it. Preserve the value outside the lexical drop frames.
            thrown_local = self._new_temporary(node.expr.type, span)
            self._push(AssignStatement(
                Place(thrown_local),
                UseRValue(self._consume_temporary(value, node.expr.type)),
                span,
            ))
            thrown_value = MoveOperand(Place(thrown_local))
            if self.exception_targets:
                target, destination, keep_depth = self.exception_targets[-1]
                self._emit_cleanups(keep_depth)
                self._terminate(ThrowTerminator(thrown_value, target, destination, span))
            else:
                self._emit_cleanups(0)
                self._terminate(ThrowTerminator(thrown_value, None, None, span))
            return
        if isinstance(node, IRTryCatch):
            self._lower_try_catch(node)
            return
        if isinstance(node, IRMatch):
            self._lower_match_statement(node)
            return
        if isinstance(node, IRAssert):
            condition = self._lower_expr(node.condition)
            continuation = self.builder.new_block()
            self._terminate(AssertTerminator(
                condition,
                True,
                node.message or "Rove assertion failed",
                continuation,
                None,
                span,
            ))
            self.current = continuation
            return
        raise MIRLoweringError(
            f"M2 does not lower statement {type(node).__name__}",
            span,
        )

    def _lower_if(self, node: IRIf) -> None:
        join = self.builder.new_block()
        branches = ((node.condition, node.then_branch),) + node.elif_branches
        for condition, body in branches:
            condition_value = self._lower_expr(condition)
            then_block = self.builder.new_block()
            next_block = self.builder.new_block()
            self._terminate(SwitchIntTerminator(
                condition_value,
                ((1, then_block),),
                next_block,
                _span(condition.span),
            ))
            self.current = then_block
            self._lower_scoped(body)
            self._goto_if_open(join, _span(condition.span))
            self.current = next_block
        if node.else_branch is not None:
            self._lower_scoped(node.else_branch)
        self._goto_if_open(join, _span(node.span))
        self.current = join

    def _lower_while(self, node: IRWhile) -> None:
        condition_block = self.builder.new_block()
        body_block = self.builder.new_block()
        exit_block = self.builder.new_block()
        self._goto_if_open(condition_block, _span(node.span))
        self.current = condition_block
        condition = self._lower_expr(node.condition)
        self._terminate(SwitchIntTerminator(
            condition,
            ((1, body_block),),
            exit_block,
            _span(node.condition.span),
        ))
        keep_depth = len(self.defer_scopes)
        self.loop_targets.append((exit_block, condition_block, keep_depth))
        self.current = body_block
        self._lower_scoped(node.body)
        self._goto_if_open(condition_block, _span(node.span))
        self.loop_targets.pop()
        self.current = exit_block

    def _lower_for(self, node: IRFor) -> None:
        if node.collection_expr is not None:
            self._lower_collection_for(node)
            return
        if node.start_expr is None or node.end_expr is None:
            raise MIRLoweringError("Malformed MIR for-loop source", _span(node.span))
        span = _span(node.span)
        loop_local = self.builder.new_local(node.var_name, from_hir_type(node.start_expr.type), "variable", span)
        self.locals[node.symbol] = loop_local
        start = self._lower_expr(node.start_expr)
        end = self._materialize(self._lower_expr(node.end_expr), node.end_expr.type, _span(node.end_expr.span))
        self._push(AssignStatement(Place(loop_local), UseRValue(start), span))

        condition_block = self.builder.new_block()
        body_block = self.builder.new_block()
        increment_block = self.builder.new_block()
        exit_block = self.builder.new_block()
        self._goto_if_open(condition_block, span)
        self.current = condition_block
        condition_local = self._new_temporary(BOOL, span)
        self._push(AssignStatement(
            Place(condition_local),
            BinaryRValue("<", CopyOperand(Place(loop_local)), end, from_hir_type(BOOL)),
            span,
        ))
        self._terminate(SwitchIntTerminator(CopyOperand(Place(condition_local)), ((1, body_block),), exit_block, span))
        keep_depth = len(self.defer_scopes)
        self.loop_targets.append((exit_block, increment_block, keep_depth))
        self.current = body_block
        self._lower_scoped(node.body)
        self._goto_if_open(increment_block, span)
        self.loop_targets.pop()

        self.current = increment_block
        next_local = self._new_temporary(node.start_expr.type, span)
        self._push(AssignStatement(
            Place(next_local),
            BinaryRValue(
                "+", CopyOperand(Place(loop_local)), ConstOperand(from_hir_type(node.start_expr.type), 1),
                from_hir_type(node.start_expr.type),
            ),
            span,
        ))
        self._push(AssignStatement(Place(loop_local), UseRValue(CopyOperand(Place(next_local))), span))
        self._terminate(GotoTerminator(condition_block, span))
        self.current = exit_block

    def _lower_collection_for(self, node: IRFor) -> None:
        collection_expr = node.collection_expr
        if collection_expr is None:
            raise MIRLoweringError("Collection loop has no collection", _span(node.span))
        span = _span(node.span)
        collection = self._materialize(
            self._lower_expr(collection_expr),
            collection_expr.type,
            _span(collection_expr.span),
        )
        if not isinstance(collection, CopyOperand):
            raise MIRLoweringError("Collection value could not be materialized", span)
        collection_drop = self._owned_temporary_local(
            collection, collection_expr.type
        )
        if collection_drop is not None:
            self._register_drop(collection_drop, collection_expr.type, span)
        element_type = collection_expr.type.arguments[0] if collection_expr.type.arguments else ANY
        loop_local = self.builder.new_local(
            node.var_name,
            from_hir_type(element_type),
            "variable",
            span,
        )
        self.locals[node.symbol] = loop_local
        index_local = self.builder.new_local("_iter_index", from_hir_type(INT), "temporary", span)
        length_local = self.builder.new_local("_iter_length", from_hir_type(INT), "temporary", span)
        self._push(AssignStatement(
            Place(index_local),
            UseRValue(ConstOperand(from_hir_type(INT), 0)),
            span,
        ))
        continuation = self.builder.new_block()
        self._terminate(CallTerminator(
            "builtin::len",
            (collection,),
            Place(length_local),
            continuation,
            None,
            span,
        ))

        condition_block = continuation
        body_block = self.builder.new_block()
        increment_block = self.builder.new_block()
        exit_block = self.builder.new_block()
        self.current = condition_block
        condition_local = self._new_temporary(BOOL, span)
        self._push(AssignStatement(
            Place(condition_local),
            BinaryRValue(
                "<",
                CopyOperand(Place(index_local)),
                CopyOperand(Place(length_local)),
                from_hir_type(BOOL),
            ),
            span,
        ))
        self._terminate(SwitchIntTerminator(
            CopyOperand(Place(condition_local)),
            ((1, body_block),),
            exit_block,
            span,
        ))

        keep_depth = len(self.defer_scopes)
        self.loop_targets.append((exit_block, increment_block, keep_depth))
        self.current = body_block
        self._push(AssignStatement(
            Place(loop_local),
            UseRValue(CopyOperand(Place(
                collection.place.local,
                collection.place.projections + (IndexProjection(index_local),),
            ))),
            span,
        ))
        loop_drop_locals = [loop_local] if self._type_needs_drop(element_type) else []
        if loop_drop_locals:
            self.drop_spans[loop_local] = span
        self._lower_scoped(node.body, loop_drop_locals)
        self._goto_if_open(increment_block, span)
        self.loop_targets.pop()

        self.current = increment_block
        next_local = self._new_temporary(INT, span)
        self._push(AssignStatement(
            Place(next_local),
            BinaryRValue(
                "+",
                CopyOperand(Place(index_local)),
                ConstOperand(from_hir_type(INT), 1),
                from_hir_type(INT),
            ),
            span,
        ))
        self._push(AssignStatement(
            Place(index_local),
            UseRValue(CopyOperand(Place(next_local))),
            span,
        ))
        self._terminate(GotoTerminator(condition_block, span))
        self.current = exit_block

    def _lower_guard(self, node: IRGuard) -> None:
        span = _span(node.span)
        condition = self._lower_expr(node.condition)
        success = self.builder.new_block()
        failure = self.builder.new_block()
        self._terminate(SwitchIntTerminator(condition, ((1, success),), failure, span))
        self.current = failure
        self._lower_scoped(node.else_body)
        self._goto_if_open(success, span)
        self.current = success

    def _lower_try_catch(self, node: IRTryCatch) -> None:
        span = _span(node.span)
        catch_block = self.builder.new_block()
        join_block = self.builder.new_block()
        error_local = self.builder.new_local(node.error_name, from_hir_type(STRING), "variable", span)
        self.locals[node.error_symbol] = error_local
        keep_depth = len(self.defer_scopes)
        self.exception_targets.append((catch_block, Place(error_local), keep_depth))
        self._lower_scoped(node.try_body)
        self.exception_targets.pop()
        self._goto_if_open(join_block, span)
        self.current = catch_block
        self.drop_spans[error_local] = span
        self._lower_scoped(node.catch_body, [error_local])
        self._goto_if_open(join_block, span)
        self.current = join_block

    def _lower_match_statement(self, node: IRMatch) -> None:
        span = _span(node.span)
        subject = self._materialize(self._lower_expr(node.expr), node.expr.type, _span(node.expr.span))
        subject_drop = self._owned_temporary_local(subject, node.expr.type)
        if subject_drop is not None:
            self.drop_spans[subject_drop] = span
        join = self.builder.new_block()
        fallback_body = None
        fallback_binding: IRReference | None = None
        tag_operand: Operand | None = None
        tag_drop: int | None = None
        for case in node.cases:
            if isinstance(case.pattern, IRLiteral) and case.pattern.value == "_":
                fallback_body = case.body
                fallback_binding = None
                continue
            if isinstance(case.pattern, IRReference):
                fallback_body = case.body
                fallback_binding = (
                    case.pattern if case.pattern.name != "_" else None
                )
                continue
            pattern_variant: tuple[str, tuple[IRType, ...]] | None = None
            if isinstance(case.pattern, IRCall):
                if case.pattern.callee_symbol in self.variants:
                    _, variant = self.variants[case.pattern.callee_symbol]
                    pattern_variant = (variant.name, variant.payload_types)
                elif (
                    case.pattern.callee_symbol in ("builtin::Ok", "builtin::Err")
                    and node.expr.type.name == "Result"
                    and len(node.expr.type.arguments) == 2
                ):
                    result_index = 0 if case.pattern.callee_symbol == "builtin::Ok" else 1
                    pattern_variant = (
                        "Ok" if result_index == 0 else "Err",
                        (node.expr.type.arguments[result_index],),
                    )
            if pattern_variant is not None:
                variant_name, payload_types = pattern_variant
                if tag_operand is None:
                    tag_local = self._new_temporary(STRING, span)
                    self._push(AssignStatement(
                        Place(tag_local),
                        DiscriminantRValue(subject, from_hir_type(STRING)),
                        span,
                    ))
                    tag_operand = CopyOperand(Place(tag_local))
                    tag_drop = tag_local
                    self.drop_spans[tag_local] = span
                case_block = self.builder.new_block()
                next_block = self.builder.new_block()
                self._terminate(SwitchValueTerminator(
                    tag_operand,
                    ((variant_name, case_block),),
                    next_block,
                    _span(case.pattern.span),
                ))
                self.current = case_block
                binding_drop_locals = [
                    local for local in (subject_drop, tag_drop) if local is not None
                ]
                for index, binding in enumerate(case.pattern.args):
                    if not isinstance(binding, IRReference) or binding.name == "_":
                        continue
                    payload_type = (
                        payload_types[index]
                        if index < len(payload_types)
                        else binding.type
                    )
                    local = self.builder.new_local(
                        binding.name,
                        from_hir_type(payload_type),
                        "variable",
                        _span(binding.span),
                    )
                    self.locals[binding.symbol] = local
                    if self._type_needs_drop(payload_type):
                        binding_drop_locals.append(local)
                        self.drop_spans[local] = _span(binding.span)
                    self._push(AssignStatement(
                        Place(local),
                        PayloadRValue(subject, index, from_hir_type(payload_type)),
                        _span(binding.span),
                    ))
                self._lower_scoped(case.body, binding_drop_locals)
                self._goto_if_open(join, span)
                self.current = next_block
                continue
            pattern = self._lower_expr_with_temporary_cleanup(
                case.pattern,
                tuple(
                    local for local in (subject_drop, tag_drop) if local is not None
                ),
            )
            comparison_pattern = (
                self._coerce(pattern, case.pattern.type, node.expr.type, _span(case.pattern.span))
                if case.pattern.type.is_numeric and node.expr.type.is_numeric
                and case.pattern.type != node.expr.type
                else pattern
            )
            condition_local = self._new_temporary(BOOL, _span(case.pattern.span))
            self._push(AssignStatement(
                Place(condition_local),
                BinaryRValue("==", subject, comparison_pattern, from_hir_type(BOOL)),
                _span(case.pattern.span),
            ))
            self._discard_temporary(
                pattern, case.pattern.type, _span(case.pattern.span)
            )
            case_block = self.builder.new_block()
            next_block = self.builder.new_block()
            self._terminate(SwitchIntTerminator(CopyOperand(Place(condition_local)), ((1, case_block),), next_block, span))
            self.current = case_block
            self._lower_scoped(
                case.body,
                [local for local in (subject_drop, tag_drop) if local is not None],
            )
            self._goto_if_open(join, span)
            self.current = next_block
        if fallback_body is not None:
            fallback_drops = [
                local for local in (subject_drop, tag_drop) if local is not None
            ]
            if fallback_binding is not None:
                binding = self.builder.new_local(
                    fallback_binding.name,
                    from_hir_type(node.expr.type),
                    "variable",
                    _span(fallback_binding.span),
                )
                self.locals[fallback_binding.symbol] = binding
                bound_value = (
                    MoveOperand(subject.place)
                    if subject_drop is not None and isinstance(subject, CopyOperand)
                    else subject
                )
                self._push(AssignStatement(
                    Place(binding), UseRValue(bound_value),
                    _span(fallback_binding.span),
                ))
                fallback_drops = [local for local in fallback_drops if local != subject_drop]
                if self._type_needs_drop(node.expr.type):
                    fallback_drops.append(binding)
                    self.drop_spans[binding] = _span(fallback_binding.span)
            self._lower_scoped(
                fallback_body,
                fallback_drops,
            )
        elif self.current is not None:
            for local in reversed(
                [local for local in (subject_drop, tag_drop) if local is not None]
            ):
                self._push(DeinitStatement(Place(local), self.drop_spans[local]))
        self._goto_if_open(join, span)
        self.current = join

    def _lower_expr(self, node: IRExpr) -> Operand:
        span = _span(node.span)
        if isinstance(node, IRLiteral):
            return ConstOperand(from_hir_type(node.type), node.value)
        if isinstance(node, IRReference):
            local = self.locals.get(node.symbol)
            if local is None:
                raise MIRLoweringError(f"Unresolved MIR local for '{node.name}'", span)
            return CopyOperand(Place(local))
        if isinstance(node, IRArray):
            operands = self._lower_ordered_operands(node.elements)
            local = self._new_temporary(node.type, span)
            self._push(AssignStatement(
                Place(local),
                AggregateRValue("array", "Array", operands, from_hir_type(node.type)),
                span,
            ))
            return CopyOperand(Place(local))
        if isinstance(node, IRMemberAccess):
            enum_definition = (
                self.enums.get(node.obj.symbol)
                if isinstance(node.obj, IRReference)
                else None
            )
            if enum_definition is not None:
                member = next(
                    (candidate for candidate in enum_definition.members if candidate.name == node.member),
                    None,
                )
                if member is None:
                    raise MIRLoweringError(
                        f"Unknown enum member '{enum_definition.name}.{node.member}'",
                        span,
                    )
                local = self._new_temporary(node.type, span)
                self._push(AssignStatement(
                    Place(local),
                    AggregateRValue(
                        "enum",
                        member.name,
                        (),
                        from_hir_type(node.type),
                    ),
                    span,
                ))
                return CopyOperand(Place(local))
            if node.safe:
                return self._lower_safe_member(node)
            return CopyOperand(self._lower_address(node))
        if isinstance(node, IRIndexAccess):
            return CopyOperand(self._lower_address(node))
        if isinstance(node, IRBinary):
            if node.op in ("and", "or", "&&", "||"):
                return self._lower_short_circuit(node)
            left, right = self._lower_ordered_operands((node.left, node.right))
            if node.left.type.is_numeric and node.right.type.is_numeric:
                if (
                    is_coercible(node.left.type, node.right.type)
                    and not is_coercible(node.right.type, node.left.type)
                ):
                    left = self._coerce(left, node.left.type, node.right.type, span)
                elif (
                    is_coercible(node.right.type, node.left.type)
                    and not is_coercible(node.left.type, node.right.type)
                ):
                    right = self._coerce(right, node.right.type, node.left.type, span)
            local = self._new_temporary(node.type, span)
            self._push(AssignStatement(
                Place(local),
                BinaryRValue(node.op, left, right, from_hir_type(node.type)),
                span,
            ))
            return CopyOperand(Place(local))
        if isinstance(node, IRUnary):
            operand = self._consume_temporary(
                self._lower_expr(node.expr), node.expr.type
            )
            local = self._new_temporary(node.type, span)
            self._push(AssignStatement(
                Place(local),
                UnaryRValue(node.op, operand, from_hir_type(node.type)),
                span,
            ))
            return CopyOperand(Place(local))
        if isinstance(node, IRAwait):
            task = self._lower_expr(node.expr)
            task_drop = self._owned_temporary_local(task, node.expr.type)
            if task_drop is not None:
                self.drop_spans[task_drop] = _span(node.expr.span)
                if self.drop_scopes and task_drop not in self.drop_scopes[-1]:
                    self.drop_scopes[-1].append(task_drop)
            destination = self._new_temporary(node.type, span)
            resume = self.builder.new_block()
            suspend_id = self.suspend_counter
            self.suspend_counter += 1
            try:
                unwind = self._build_unwind_cleanup_edge(span, can_unwind=True)
            finally:
                if (
                    task_drop is not None
                    and self.drop_scopes
                    and task_drop in self.drop_scopes[-1]
                ):
                    self.drop_scopes[-1].remove(task_drop)
            self._terminate(SuspendTerminator(
                task,
                Place(destination),
                resume,
                suspend_id,
                span,
                unwind[0] if unwind else None,
                unwind[1] if unwind else None,
            ))
            self.current = resume
            if task_drop is not None:
                self._push(DeinitStatement(Place(task_drop), span))
            return CopyOperand(Place(destination))
        if isinstance(node, IRCall):
            argument_nodes = (
                ((node.receiver,) if node.receiver is not None else ()) + node.args
            )
            arguments = self._lower_ordered_operands(argument_nodes)
            struct = self.structs.get(node.callee_symbol)
            if struct is not None:
                local = self._new_temporary(node.type, span)
                self._push(AssignStatement(
                    Place(local),
                    AggregateRValue(
                        "struct",
                        struct.name,
                        tuple(arguments),
                        from_hir_type(node.type),
                        tuple(field.name for field in struct.fields),
                    ),
                    span,
                ))
                return CopyOperand(Place(local))
            variant_entry = self.variants.get(node.callee_symbol)
            if variant_entry is not None:
                enum, variant = variant_entry
                local = self._new_temporary(node.type, span)
                self._push(AssignStatement(
                    Place(local),
                    AggregateRValue(
                        "enum",
                        variant.name,
                        tuple(arguments),
                        from_hir_type(node.type),
                        tuple(str(index) for index in range(len(arguments))),
                    ),
                    span,
                ))
                return CopyOperand(Place(local))
            if node.callee_symbol in ("builtin::Ok", "builtin::Err"):
                local = self._new_temporary(node.type, span)
                self._push(AssignStatement(
                    Place(local),
                    AggregateRValue(
                        "result",
                        node.callee,
                        tuple(arguments),
                        from_hir_type(node.type),
                    ),
                    span,
                ))
                return CopyOperand(Place(local))
            destination = self._new_temporary(node.type, span)
            continuation = self.builder.new_block()
            can_unwind = (
                node.callee_symbol in self.throwing_functions
                and node.callee_symbol not in self.async_functions
            )
            unwind = self._build_unwind_cleanup_edge(span, can_unwind=can_unwind)
            self._terminate(CallTerminator(
                node.callee_symbol,
                tuple(arguments),
                Place(destination),
                continuation,
                unwind[0] if unwind else None,
                span,
                unwind[1] if unwind else None,
            ))
            self.current = continuation
            return CopyOperand(Place(destination))
        if isinstance(node, IRConditional):
            return self._lower_conditional(node)
        if isinstance(node, IRNullCoalesce):
            return self._lower_null_coalesce(node)
        if isinstance(node, IRMatchExpression):
            return self._lower_match_expression(node)
        if isinstance(node, IRResultPropagate):
            return self._lower_result_propagate(node)
        raise MIRLoweringError(f"M2 does not lower expression {type(node).__name__}", span)

    def _lower_safe_member(self, node: IRMemberAccess) -> Operand:
        span = _span(node.span)
        base = self._materialize(
            self._lower_expr(node.obj),
            node.obj.type,
            _span(node.obj.span),
        )
        if not isinstance(base, CopyOperand):
            raise MIRLoweringError("Safe-navigation base could not be materialized", span)
        base_drop = self._owned_temporary_local(base, node.obj.type)
        result = self._new_temporary(node.type, span)
        none_block = self.builder.new_block()
        present_block = self.builder.new_block()
        join = self.builder.new_block()
        self._terminate(SwitchValueTerminator(base, ((None, none_block),), present_block, span))
        self.current = none_block
        self._push(AssignStatement(
            Place(result),
            UseRValue(ConstOperand(from_hir_type(node.type), None)),
            span,
        ))
        if base_drop is not None:
            self._push(DeinitStatement(Place(base_drop), span))
        self._terminate(GotoTerminator(join, span))
        self.current = present_block
        projected = Place(
            base.place.local,
            base.place.projections + (FieldProjection(node.member),),
        )
        self._push(AssignStatement(
            Place(result),
            CastRValue("optional-inject", CopyOperand(projected), from_hir_type(node.type)),
            span,
        ))
        if base_drop is not None:
            self._push(DeinitStatement(Place(base_drop), span))
        self._goto_if_open(join, span)
        self.current = join
        return CopyOperand(Place(result))

    def _lower_short_circuit(self, node: IRBinary) -> Operand:
        span = _span(node.span)
        result = self._new_temporary(node.type, span)
        left = self._lower_expr(node.left)
        right_block = self.builder.new_block()
        constant_block = self.builder.new_block()
        join = self.builder.new_block()
        is_and = node.op in ("and", "&&")
        if is_and:
            targets, otherwise = ((1, right_block),), constant_block
            constant = False
        else:
            targets, otherwise = ((1, constant_block),), right_block
            constant = True
        self._terminate(SwitchIntTerminator(left, targets, otherwise, span))
        self.current = constant_block
        self._push(AssignStatement(Place(result), UseRValue(ConstOperand(from_hir_type(node.type), constant)), span))
        self._terminate(GotoTerminator(join, span))
        self.current = right_block
        right = self._lower_expr(node.right)
        self._push(AssignStatement(Place(result), UseRValue(right), span))
        self._goto_if_open(join, span)
        self.current = join
        return CopyOperand(Place(result))

    def _lower_conditional(self, node: IRConditional) -> Operand:
        span = _span(node.span)
        result = self._new_temporary(node.type, span)
        condition = self._lower_expr(node.condition)
        then_block = self.builder.new_block()
        else_block = self.builder.new_block()
        join = self.builder.new_block()
        self._terminate(SwitchIntTerminator(condition, ((1, then_block),), else_block, span))
        self.current = then_block
        then_value = self._lower_expr(node.then_expr)
        then_value = self._consume_temporary(then_value, node.then_expr.type)
        self._push(AssignStatement(Place(result), UseRValue(then_value), span))
        self._goto_if_open(join, span)
        self.current = else_block
        else_value = self._lower_expr(node.else_expr)
        else_value = self._consume_temporary(else_value, node.else_expr.type)
        self._push(AssignStatement(Place(result), UseRValue(else_value), span))
        self._goto_if_open(join, span)
        self.current = join
        return CopyOperand(Place(result))

    def _lower_null_coalesce(self, node: IRNullCoalesce) -> Operand:
        span = _span(node.span)
        left = self._materialize(self._lower_expr(node.left), node.left.type, _span(node.left.span))
        left_drop = self._owned_temporary_local(left, node.left.type)
        result = self._new_temporary(node.type, span)
        fallback_block = self.builder.new_block()
        present_block = self.builder.new_block()
        join = self.builder.new_block()
        self._terminate(SwitchValueTerminator(left, ((None, fallback_block),), present_block, span))
        self.current = present_block
        present_value: Operand = (
            MoveOperand(left.place)
            if left_drop is not None and isinstance(left, CopyOperand)
            else left
        )
        self._push(AssignStatement(
            Place(result),
            CastRValue("optional-unwrap", present_value, from_hir_type(node.type)),
            span,
        ))
        self._terminate(GotoTerminator(join, span))
        self.current = fallback_block
        if left_drop is not None:
            self._push(DeinitStatement(Place(left_drop), span))
        fallback = self._lower_expr(node.right)
        fallback = self._consume_temporary(fallback, node.right.type)
        self._push(AssignStatement(Place(result), UseRValue(fallback), span))
        self._goto_if_open(join, span)
        self.current = join
        return CopyOperand(Place(result))

    def _lower_match_expression(self, node: IRMatchExpression) -> Operand:
        span = _span(node.span)
        subject = self._materialize(self._lower_expr(node.subject), node.subject.type, _span(node.subject.span))
        subject_drop = self._owned_temporary_local(subject, node.subject.type)
        if subject_drop is not None:
            self.drop_spans[subject_drop] = span
        result = self._new_temporary(node.type, span)
        join = self.builder.new_block()
        wildcard = None
        for case in node.cases:
            if case.pattern is None:
                wildcard = case.value
                continue
            pattern = self._lower_expr_with_temporary_cleanup(
                case.pattern,
                () if subject_drop is None else (subject_drop,),
            )
            comparison_pattern = (
                self._coerce(pattern, case.pattern.type, node.subject.type, _span(case.pattern.span))
                if case.pattern.type.is_numeric and node.subject.type.is_numeric
                and case.pattern.type != node.subject.type
                else pattern
            )
            condition = self._new_temporary(BOOL, _span(case.pattern.span))
            self._push(AssignStatement(
                Place(condition),
                BinaryRValue("==", subject, comparison_pattern, from_hir_type(BOOL)),
                _span(case.pattern.span),
            ))
            self._discard_temporary(
                pattern, case.pattern.type, _span(case.pattern.span)
            )
            value_block = self.builder.new_block()
            next_block = self.builder.new_block()
            self._terminate(SwitchIntTerminator(CopyOperand(Place(condition)), ((1, value_block),), next_block, span))
            self.current = value_block
            value = self._lower_expr_with_temporary_cleanup(
                case.value,
                () if subject_drop is None else (subject_drop,),
            )
            value = self._consume_temporary(value, case.value.type)
            self._push(AssignStatement(Place(result), UseRValue(value), span))
            if subject_drop is not None:
                self._push(DeinitStatement(Place(subject_drop), span))
            self._goto_if_open(join, span)
            self.current = next_block
        if wildcard is None:
            raise MIRLoweringError("MIR match expression requires a wildcard arm", span)
        value = self._lower_expr_with_temporary_cleanup(
            wildcard,
            () if subject_drop is None else (subject_drop,),
        )
        value = self._consume_temporary(value, wildcard.type)
        self._push(AssignStatement(Place(result), UseRValue(value), span))
        if subject_drop is not None:
            self._push(DeinitStatement(Place(subject_drop), span))
        self._goto_if_open(join, span)
        self.current = join
        return CopyOperand(Place(result))

    def _lower_result_propagate(self, node: IRResultPropagate) -> Operand:
        span = _span(node.span)
        result_value = self._materialize(self._lower_expr(node.expr), node.expr.type, _span(node.expr.span))
        result_drop = self._owned_temporary_local(result_value, node.expr.type)
        payload = self._new_temporary(node.type, span)
        tag = self._new_temporary(STRING, span)
        self._push(AssignStatement(
            Place(tag),
            DiscriminantRValue(result_value, from_hir_type(STRING)),
            span,
        ))
        ok_block = self.builder.new_block()
        error_block = self.builder.new_block()
        join = self.builder.new_block()
        self._terminate(SwitchValueTerminator(CopyOperand(Place(tag)), (("Ok", ok_block),), error_block, span))
        self.current = ok_block
        self._push(AssignStatement(
            Place(payload),
            PayloadRValue(result_value, 0, from_hir_type(node.type)),
            span,
        ))
        self._push(DeinitStatement(Place(tag), span))
        if result_drop is not None:
            self._push(DeinitStatement(Place(result_drop), span))
        self._terminate(GotoTerminator(join, span))
        self.current = error_block
        self._push(DeinitStatement(Place(tag), span))
        propagated: Operand = (
            MoveOperand(result_value.place)
            if result_drop is not None and isinstance(result_value, CopyOperand)
            else result_value
        )
        self._push(AssignStatement(Place(0), UseRValue(propagated), span))
        self._emit_cleanups(0)
        self._terminate(ReturnTerminator(span))
        self.current = join
        return CopyOperand(Place(payload))

    def _lower_place(self, node: IRExpr) -> Place:
        if isinstance(node, IRMemberAccess) and node.safe:
            raise MIRLoweringError("Safe-navigation is not an assignment target", _span(node.span))
        return self._lower_address(node)

    def _lower_address(self, node: IRExpr) -> Place:
        if isinstance(node, IRReference):
            local = self.locals.get(node.symbol)
            if local is None:
                raise MIRLoweringError(f"Unresolved MIR assignment target '{node.name}'", _span(node.span))
            return Place(local)
        if isinstance(node, IRMemberAccess):
            base = self._addressable_base(node.obj)
            return Place(
                base.local,
                base.projections + (FieldProjection(node.member),),
            )
        if isinstance(node, IRIndexAccess):
            base = self._addressable_base(node.obj)
            if isinstance(node.index, IRLiteral) and isinstance(node.index.value, int):
                projection = ConstantIndexProjection(node.index.value)
            else:
                index = self._materialize(
                    self._lower_expr(node.index),
                    node.index.type,
                    _span(node.index.span),
                )
                if not isinstance(index, CopyOperand) or index.place.projections:
                    index_local = self._new_temporary(node.index.type, _span(node.index.span))
                    self._push(AssignStatement(
                        Place(index_local),
                        UseRValue(index),
                        _span(node.index.span),
                    ))
                else:
                    index_local = index.place.local
                projection = IndexProjection(index_local)
            return Place(base.local, base.projections + (projection,))
        raise MIRLoweringError(
            f"Expression {type(node).__name__} is not an addressable MIR place",
            _span(node.span),
        )

    def _addressable_base(self, node: IRExpr) -> Place:
        if isinstance(node, (IRReference, IRMemberAccess, IRIndexAccess)):
            return self._lower_address(node)
        value = self._materialize(self._lower_expr(node), node.type, _span(node.span))
        if not isinstance(value, CopyOperand):
            raise MIRLoweringError("Projected value could not be materialized", _span(node.span))
        temporary = self._owned_temporary_local(value, node.type)
        if temporary is not None:
            self._register_drop(temporary, node.type, _span(node.span))
        return value.place

    def _new_temporary(self, value_type, span: MIRSpan) -> int:
        self.temporary_counter += 1
        local = self.builder.new_local(
            f"_tmp{self.temporary_counter}",
            from_hir_type(value_type),
            "temporary",
            span,
        )
        self.temporary_locals.add(local)
        return local

    def _materialize(self, operand: Operand, value_type, span: MIRSpan) -> Operand:
        if isinstance(operand, CopyOperand):
            return operand
        local = self._new_temporary(value_type, span)
        self._push(AssignStatement(Place(local), UseRValue(operand), span))
        return CopyOperand(Place(local))

    def _coerce(self, operand: Operand, source_type, target_type, span: MIRSpan) -> Operand:
        if source_type == target_type:
            return operand
        if not is_coercible(source_type, target_type):
            raise MIRLoweringError(f"Cannot convert {source_type} to {target_type}", span)
        local = self._new_temporary(target_type, span)
        self._push(AssignStatement(
            Place(local),
            CastRValue(
                "implicit",
                self._consume_temporary(operand, source_type),
                from_hir_type(target_type),
            ),
            span,
        ))
        return CopyOperand(Place(local))

    def _consume_temporary(self, operand: Operand, value_type: IRType) -> Operand:
        if self._owned_temporary_local(operand, value_type) is not None:
            assert isinstance(operand, CopyOperand)
            return MoveOperand(operand.place)
        return operand

    def _lower_ordered_operands(self, expressions: tuple[IRExpr, ...]) -> tuple[Operand, ...]:
        """Keep earlier owned values live until all later operands are ready."""
        operands: list[Operand] = []
        pending_drops: list[int] = []
        frame = self.drop_scopes[-1] if self.drop_scopes else None
        try:
            for expression in expressions:
                value = self._lower_expr(expression)
                temporary = self._owned_temporary_local(value, expression.type)
                if temporary is not None and frame is not None:
                    self._register_drop(temporary, expression.type, _span(expression.span))
                    pending_drops.append(temporary)
                operands.append(self._consume_temporary(value, expression.type))
        finally:
            if frame is not None:
                for temporary in pending_drops:
                    frame.remove(temporary)
        return tuple(operands)

    def _owned_temporary_local(
        self, operand: Operand, value_type: IRType
    ) -> int | None:
        if (
            isinstance(operand, CopyOperand)
            and not operand.place.projections
            and operand.place.local in self.temporary_locals
            and self._type_needs_drop(value_type)
        ):
            return operand.place.local
        return None

    def _discard_temporary(
        self, operand: Operand, value_type: IRType, span: MIRSpan
    ) -> None:
        local = self._owned_temporary_local(operand, value_type)
        if local is not None:
            self._push(DeinitStatement(Place(local), span))

    def _lower_expr_with_temporary_cleanup(
        self, expression: IRExpr, locals_: tuple[int, ...]
    ) -> Operand:
        if not locals_ or not self.drop_scopes:
            return self._lower_expr(expression)
        frame = self.drop_scopes[-1]
        added = [local for local in locals_ if local not in frame]
        frame.extend(added)
        try:
            return self._lower_expr(expression)
        finally:
            for local in added:
                frame.remove(local)

    def _emit_defer_frame(self, frame: list[IRExpr]) -> None:
        for expression in reversed(frame):
            if self.current is None:
                return
            value = self._lower_expr(expression)
            self._discard_temporary(value, expression.type, _span(expression.span))

    def _emit_cleanup_frame(self, index: int) -> None:
        if index not in self.active_cleanup_frames:
            self.active_cleanup_frames.add(index)
            try:
                self._emit_defer_frame(self.defer_scopes[index])
            finally:
                self.active_cleanup_frames.remove(index)
        if self.current is None:
            return
        for local in reversed(self.drop_scopes[index]):
            self._push(DeinitStatement(
                Place(local), self.drop_spans.get(local, self.span)
            ))

    def _emit_cleanups(self, keep_depth: int) -> None:
        for index in range(len(self.defer_scopes) - 1, keep_depth - 1, -1):
            self._emit_cleanup_frame(index)

    def _build_unwind_cleanup_edge(
        self, span: MIRSpan, *, can_unwind: bool
    ) -> tuple[int, Place] | None:
        if not can_unwind:
            return None
        if self.exception_targets:
            catch_target, error_destination, keep_depth = self.exception_targets[-1]
        else:
            if not any(self.defer_scopes) and not any(self.drop_scopes):
                return None
            error_local = self._new_temporary(STRING, span)
            catch_target = -1
            error_destination = Place(error_local)
            keep_depth = 0
        source_block = self.current
        cleanup_block = self.builder.new_block()
        self.current = cleanup_block
        active_target = self.exception_targets.pop() if self.exception_targets else None
        try:
            self._emit_cleanups(keep_depth)
            if catch_target >= 0:
                self._goto_if_open(catch_target, span)
            elif self.current is not None:
                self._terminate(ThrowTerminator(
                    MoveOperand(error_destination), None, None, span
                ))
        finally:
            if active_target is not None:
                self.exception_targets.append(active_target)
            self.current = source_block
        return cleanup_block, error_destination

    def _register_drop(self, local: int, value_type: IRType, span: MIRSpan) -> None:
        if not self.drop_scopes or not self._type_needs_drop(value_type):
            return
        self.drop_scopes[-1].append(local)
        self.drop_spans[local] = span

    def _type_needs_drop(
        self, value_type: IRType, stack: tuple[str, ...] = ()
    ) -> bool:
        if value_type.pointer or value_type.is_function:
            return False
        if value_type.name in {"string", "Array", "Task"}:
            return True
        if value_type.name in {"Option", "Result"} or value_type.optional:
            return any(
                self._type_needs_drop(argument, stack)
                for argument in value_type.arguments
            ) or value_type.name == "string"
        if value_type.name in stack:
            return False
        struct = self.structs_by_name.get(value_type.name)
        if struct is not None:
            return any(
                self._type_needs_drop(
                    field.type, stack + (value_type.name,)
                )
                for field in struct.fields
            )
        enum = self.enums_by_name.get(value_type.name)
        if enum is not None:
            return any(
                self._type_needs_drop(
                    payload_type, stack + (value_type.name,)
                )
                for member in enum.members
                for payload_type in member.payload_types
            )
        return False

    def _push(self, statement) -> None:
        if self.current is None:
            raise MIRLoweringError("Cannot append after a terminating control-flow edge", statement.span)
        self.builder.push_statement(self.current, statement)

    def _terminate(self, terminator) -> None:
        if self.current is None:
            raise MIRLoweringError("Control-flow block is already terminated", terminator.span)
        self.builder.set_terminator(self.current, terminator)
        self.current = None

    def _goto_if_open(self, target: int, span: MIRSpan) -> None:
        if self.current is not None and not self.builder.is_terminated(self.current):
            self.builder.set_terminator(self.current, GotoTerminator(target, span))
        self.current = None


def lower_hir_to_mir(hir: IRModule) -> MIRModule:
    """Lower executable Typed HIR into verified target-independent MIR."""
    hir = materialize_static_dispatch(hir)
    if any(getattr(item, "generic_params", ()) for item in hir.items):
        hir = materialize_generic_instances(hir)
    structs = {
        item.symbol: item
        for item in hir.items
        if isinstance(item, IRStruct)
    }
    enums = {
        item.symbol: item
        for item in hir.items
        if isinstance(item, IREnum)
    }
    variants = {
        f"enum::{enum.name}::variant::{member.name}": (enum, member)
        for enum in enums.values()
        for member in enum.members
        if member.is_variant
    }
    type_definitions = tuple(
        MIRStructDef(
            item.name,
            item.symbol,
            tuple(MIRField(field.name, from_hir_type(field.type)) for field in item.fields),
        )
        if isinstance(item, IRStruct)
        else MIREnumDef(
            item.name,
            item.symbol,
            tuple(
                MIREnumVariant(
                    member.name,
                    tuple(from_hir_type(value) for value in member.payload_types),
                )
                for member in item.members
            ),
        )
        for item in hir.items
        if isinstance(item, (IRStruct, IREnum))
    )
    hir_functions = tuple(hir.functions)
    throwing_functions = _throwing_function_symbols(hir_functions)
    async_functions = frozenset(
        function.symbol for function in hir_functions if function.is_async
    )
    functions = [
        _FunctionLowerer(
            function,
            structs,
            enums,
            variants,
            throwing_functions,
            async_functions,
        ).lower()
        for function in hir_functions
    ]
    if hir.top_level_statements:
        synthetic = IRFunction(
            span=hir.top_level_statements[0].span,
            name="__nyx_top_level",
            symbol="function::__nyx_top_level",
            params=(),
            return_type=VOID,
            body=hir.top_level_statements,
        )
        functions.append(_FunctionLowerer(
            synthetic,
            structs,
            enums,
            variants,
            throwing_functions,
            async_functions,
        ).lower())
    module = elaborate_coroutines(MIRModule(
        hir.source_name,
        hir.target,
        tuple(functions),
        type_definitions,
    ))
    return _verify_and_infer_mir(module)
