"""Deliberately narrow Typed HIR to MIR skeleton lowering for M1.

M2 owns expression and control-flow lowering. M1 only proves declarations,
locals, blocks, terminators, serialization, and verification without fabricating
semantics for function bodies.
"""

from __future__ import annotations

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
    ):
        self.function = function
        self.structs = structs
        self.enums = enums
        self.variants = variants
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
        self.exception_targets: list[tuple[int, Place, int]] = []
        self.temporary_counter = 0
        self.suspend_counter = 0

    def lower(self):
        for parameter in self.function.params:
            self.locals[parameter.symbol] = self.builder.new_local(
                parameter.name,
                from_hir_type(parameter.type),
                kind="parameter",
                span=_span(parameter.default.span) if parameter.default is not None else self.span,
            )
        self.current = self.builder.new_block()
        self._lower_scoped(self.function.body)
        if self.current is not None and not self.builder.is_terminated(self.current):
            self.builder.set_terminator(self.current, ReturnTerminator(self.span))
        return self.builder.finish()

    def _lower_statements(self, statements: tuple[IRStatement, ...]) -> None:
        for statement in statements:
            if self.current is None:
                break
            self._lower_statement(statement)

    def _lower_scoped(self, statements: tuple[IRStatement, ...]) -> None:
        self.defer_scopes.append([])
        try:
            self._lower_statements(statements)
            if self.current is not None:
                self._emit_defer_frame(self.defer_scopes[-1])
        finally:
            self.defer_scopes.pop()

    def _lower_statement(self, node: IRStatement) -> None:
        span = _span(node.span)
        if isinstance(node, IRVarDecl):
            local = self.builder.new_local(node.name, from_hir_type(node.type), "variable", span)
            self.locals[node.symbol] = local
            value = self._lower_expr(node.expr)
            value = self._coerce(value, node.expr.type, node.type, span)
            self._push(AssignStatement(Place(local), UseRValue(value), span))
            return
        if isinstance(node, IRAssign):
            target = self._lower_place(node.target)
            value = self._lower_expr(node.expr)
            value = self._coerce(value, node.expr.type, node.target.type, span)
            self._push(AssignStatement(target, UseRValue(value), span))
            return
        if isinstance(node, IRExprStatement):
            self._lower_expr(node.expr)
            return
        if isinstance(node, IRReturn):
            if node.expr is not None:
                value = self._lower_expr(node.expr)
                value = self._coerce(value, node.expr.type, self.function.return_type, span)
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
            if self.exception_targets:
                target, destination, keep_depth = self.exception_targets[-1]
                self._emit_cleanups(keep_depth)
                self._terminate(ThrowTerminator(value, target, destination, span))
            else:
                self._emit_cleanups(0)
                self._terminate(ThrowTerminator(value, None, None, span))
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
                node.message or "Nyx assertion failed",
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
        self._lower_scoped(node.body)
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
        self._lower_scoped(node.catch_body)
        self._goto_if_open(join_block, span)
        self.current = join_block

    def _lower_match_statement(self, node: IRMatch) -> None:
        span = _span(node.span)
        subject = self._materialize(self._lower_expr(node.expr), node.expr.type, _span(node.expr.span))
        join = self.builder.new_block()
        wildcard_body = None
        tag_operand: Operand | None = None
        for case in node.cases:
            if isinstance(case.pattern, IRReference) and case.pattern.name == "_":
                wildcard_body = case.body
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
                case_block = self.builder.new_block()
                next_block = self.builder.new_block()
                self._terminate(SwitchValueTerminator(
                    tag_operand,
                    ((variant_name, case_block),),
                    next_block,
                    _span(case.pattern.span),
                ))
                self.current = case_block
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
                    self._push(AssignStatement(
                        Place(local),
                        PayloadRValue(subject, index, from_hir_type(payload_type)),
                        _span(binding.span),
                    ))
                self._lower_scoped(case.body)
                self._goto_if_open(join, span)
                self.current = next_block
                continue
            pattern = self._lower_expr(case.pattern)
            condition_local = self._new_temporary(BOOL, _span(case.pattern.span))
            self._push(AssignStatement(
                Place(condition_local),
                BinaryRValue("==", subject, pattern, from_hir_type(BOOL)),
                _span(case.pattern.span),
            ))
            case_block = self.builder.new_block()
            next_block = self.builder.new_block()
            self._terminate(SwitchIntTerminator(CopyOperand(Place(condition_local)), ((1, case_block),), next_block, span))
            self.current = case_block
            self._lower_scoped(case.body)
            self._goto_if_open(join, span)
            self.current = next_block
        if wildcard_body is not None:
            self._lower_scoped(wildcard_body)
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
            operands = tuple(self._lower_expr(element) for element in node.elements)
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
            left = self._lower_expr(node.left)
            right = self._lower_expr(node.right)
            local = self._new_temporary(node.type, span)
            self._push(AssignStatement(
                Place(local),
                BinaryRValue(node.op, left, right, from_hir_type(node.type)),
                span,
            ))
            return CopyOperand(Place(local))
        if isinstance(node, IRUnary):
            operand = self._lower_expr(node.expr)
            local = self._new_temporary(node.type, span)
            self._push(AssignStatement(
                Place(local),
                UnaryRValue(node.op, operand, from_hir_type(node.type)),
                span,
            ))
            return CopyOperand(Place(local))
        if isinstance(node, IRAwait):
            task = self._lower_expr(node.expr)
            destination = self._new_temporary(node.type, span)
            resume = self.builder.new_block()
            suspend_id = self.suspend_counter
            self.suspend_counter += 1
            unwind = self.exception_targets[-1] if self.exception_targets else None
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
            return CopyOperand(Place(destination))
        if isinstance(node, IRCall):
            arguments = []
            if node.receiver is not None:
                arguments.append(self._lower_expr(node.receiver))
            arguments.extend(self._lower_expr(argument) for argument in node.args)
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
            unwind = self.exception_targets[-1] if self.exception_targets else None
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
        self._push(AssignStatement(Place(result), UseRValue(then_value), span))
        self._goto_if_open(join, span)
        self.current = else_block
        else_value = self._lower_expr(node.else_expr)
        self._push(AssignStatement(Place(result), UseRValue(else_value), span))
        self._goto_if_open(join, span)
        self.current = join
        return CopyOperand(Place(result))

    def _lower_null_coalesce(self, node: IRNullCoalesce) -> Operand:
        span = _span(node.span)
        left = self._materialize(self._lower_expr(node.left), node.left.type, _span(node.left.span))
        result = self._new_temporary(node.type, span)
        fallback_block = self.builder.new_block()
        present_block = self.builder.new_block()
        join = self.builder.new_block()
        self._terminate(SwitchValueTerminator(left, ((None, fallback_block),), present_block, span))
        self.current = present_block
        self._push(AssignStatement(
            Place(result),
            CastRValue("optional-unwrap", left, from_hir_type(node.type)),
            span,
        ))
        self._terminate(GotoTerminator(join, span))
        self.current = fallback_block
        fallback = self._lower_expr(node.right)
        self._push(AssignStatement(Place(result), UseRValue(fallback), span))
        self._goto_if_open(join, span)
        self.current = join
        return CopyOperand(Place(result))

    def _lower_match_expression(self, node: IRMatchExpression) -> Operand:
        span = _span(node.span)
        subject = self._materialize(self._lower_expr(node.subject), node.subject.type, _span(node.subject.span))
        result = self._new_temporary(node.type, span)
        join = self.builder.new_block()
        wildcard = None
        for case in node.cases:
            if case.pattern is None:
                wildcard = case.value
                continue
            pattern = self._lower_expr(case.pattern)
            condition = self._new_temporary(BOOL, _span(case.pattern.span))
            self._push(AssignStatement(
                Place(condition),
                BinaryRValue("==", subject, pattern, from_hir_type(BOOL)),
                _span(case.pattern.span),
            ))
            value_block = self.builder.new_block()
            next_block = self.builder.new_block()
            self._terminate(SwitchIntTerminator(CopyOperand(Place(condition)), ((1, value_block),), next_block, span))
            self.current = value_block
            value = self._lower_expr(case.value)
            self._push(AssignStatement(Place(result), UseRValue(value), span))
            self._goto_if_open(join, span)
            self.current = next_block
        if wildcard is None:
            raise MIRLoweringError("MIR match expression requires a wildcard arm", span)
        value = self._lower_expr(wildcard)
        self._push(AssignStatement(Place(result), UseRValue(value), span))
        self._goto_if_open(join, span)
        self.current = join
        return CopyOperand(Place(result))

    def _lower_result_propagate(self, node: IRResultPropagate) -> Operand:
        span = _span(node.span)
        result_value = self._materialize(self._lower_expr(node.expr), node.expr.type, _span(node.expr.span))
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
        self._terminate(GotoTerminator(join, span))
        self.current = error_block
        self._push(AssignStatement(Place(0), UseRValue(result_value), span))
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
        return value.place

    def _new_temporary(self, value_type, span: MIRSpan) -> int:
        self.temporary_counter += 1
        return self.builder.new_local(
            f"_tmp{self.temporary_counter}",
            from_hir_type(value_type),
            "temporary",
            span,
        )

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
            CastRValue("implicit", operand, from_hir_type(target_type)),
            span,
        ))
        return CopyOperand(Place(local))

    def _emit_defer_frame(self, frame: list[IRExpr]) -> None:
        for expression in reversed(frame):
            if self.current is None:
                return
            self._lower_expr(expression)

    def _emit_cleanups(self, keep_depth: int) -> None:
        for frame in reversed(self.defer_scopes[keep_depth:]):
            self._emit_defer_frame(frame)

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
    functions = [
        _FunctionLowerer(function, structs, enums, variants).lower()
        for function in hir.functions
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
        functions.append(_FunctionLowerer(synthetic, structs, enums, variants).lower())
    module = elaborate_coroutines(MIRModule(
        hir.source_name,
        hir.target,
        tuple(functions),
        type_definitions,
    ))
    module = infer_module_effects(module)
    verify_mir(module)
    return module
