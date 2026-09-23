"""Structural, symbol, type, and control-flow verification for Rove HIR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .builtins import BUILTINS, INTRINSICS
from .model import (
    HIR_SCHEMA_VERSION,
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
    IRMatchExpression,
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
    SourceSpan,
)
from .types import ANY, BOOL, FLOAT, INT, NULL, STRING, VOID, IRType, function_type, is_assignable, is_coercible, task_of


@dataclass(frozen=True, slots=True)
class IRVerificationIssue:
    code: str
    message: str
    span: SourceSpan

    def __str__(self) -> str:
        return f"{self.span.source}:{self.span.line}:{self.span.column}: {self.code}: {self.message}"


class IRVerificationError(ValueError):
    def __init__(self, issues: Iterable[IRVerificationIssue]):
        self.issues = tuple(issues)
        detail = "\n".join(str(issue) for issue in self.issues)
        super().__init__(f"HIR verification failed with {len(self.issues)} issue(s)\n{detail}")


@dataclass(frozen=True, slots=True)
class _Definition:
    name: str
    kind: str
    type: IRType
    span: SourceSpan
    parameters: Tuple[IRParameter, ...] = ()
    required_args: int = 0
    max_args: Optional[int] = 0
    varargs: bool = False
    is_const: bool = False
    generic_params: Tuple[str, ...] = ()


class IRVerifier:
    """Verify HIR without mutating it or depending on a target backend."""

    _COMPARISON_OPS = frozenset(("==", "!=", "<", ">", "<=", ">="))
    _LOGICAL_OPS = frozenset(("and", "or", "&&", "||"))
    _ARITHMETIC_OPS = frozenset(("+", "-", "*", "/", "%"))
    _BITWISE_OPS = frozenset(("|", "&", "^", "<<", ">>"))
    _UNARY_OPS = frozenset(("-", "+", "!", "not", "~", "*"))

    def __init__(self, module: IRModule, *, require_definite_returns: bool = True):
        self.module = module
        self.require_definite_returns = require_definite_returns
        self.issues: List[IRVerificationIssue] = []
        self.definitions: Dict[str, _Definition] = {}
        self._issue_keys: Set[Tuple[str, str, SourceSpan]] = set()
        self._checked_spans: Set[int] = set()
        self._checked_types: Set[IRType] = set()
        self._inside_async = False
        self._current_return_type: Optional[IRType] = None
        self.type_aliases: Dict[str, IRType] = {
            item.name: item.actual_type
            for item in module.items
            if isinstance(item, IRTypeAlias)
        }
        self.structs: Dict[str, IRStruct] = {
            item.name: item
            for item in module.items
            if isinstance(item, IRStruct)
        }

    def _substitute_generics(self, target: IRType, subs: Dict[str, IRType]) -> IRType:
        if not subs:
            return target
        if target.name in subs:
            res = subs[target.name]
            if target.optional:
                res = res.with_optional(True)
            if target.pointer:
                res = IRType(
                    res.name, res.arguments, res.optional, True,
                    res.parameter_types, res.return_type,
                )
            return res
        return IRType(
            target.name,
            tuple(self._substitute_generics(arg, subs) for arg in target.arguments),
            target.optional,
            target.pointer,
            tuple(self._substitute_generics(arg, subs) for arg in target.parameter_types),
            self._substitute_generics(target.return_type, subs) if target.return_type else None,
        )

    def _infer_generic_substitutions(
        self,
        pattern: IRType,
        actual: IRType,
        generic_params: Set[str],
        substitutions: Dict[str, IRType],
        span: SourceSpan,
    ) -> None:
        if pattern.name in generic_params and not pattern.arguments:
            concrete = IRType(
                actual.name,
                actual.arguments,
                actual.optional and not pattern.optional,
                actual.pointer and not pattern.pointer,
                actual.parameter_types,
                actual.return_type,
            )
            previous = substitutions.get(pattern.name)
            if previous is not None and previous != concrete:
                self._issue(
                    "HIR0006",
                    f"Generic parameter '{pattern.name}' has conflicting concrete types "
                    f"'{previous}' and '{concrete}'",
                    span,
                )
            else:
                substitutions[pattern.name] = concrete
            return
        if pattern.name != actual.name or len(pattern.arguments) != len(actual.arguments):
            return
        for expected, found in zip(pattern.arguments, actual.arguments):
            self._infer_generic_substitutions(
                expected, found, generic_params, substitutions, span,
            )

    def verify(self) -> IRModule:
        module_span = SourceSpan(self.module.source_name or "<unknown>", 1, 1)
        if self.module.schema_version != HIR_SCHEMA_VERSION:
            self._issue(
                "HIR0001",
                f"Unsupported HIR schema {self.module.schema_version}; expected {HIR_SCHEMA_VERSION}",
                module_span,
            )
        if not self.module.source_name:
            self._issue("HIR0009", "Module source_name must not be empty", module_span)
        if not self.module.target:
            self._issue("HIR0009", "Module target must not be empty", module_span)

        self._install_builtins(module_span)
        self._collect_module_definitions()
        self._validate_impl_contracts()
        active = {
            symbol
            for symbol in self.definitions
            if symbol.startswith("builtin::") or symbol.startswith("intrinsic::")
        }
        active.update(self._predeclared_module_symbols())

        for item in self.module.items:
            self._visit_top_level(item, active)
            if isinstance(item, IRVarDecl):
                active.add(item.symbol)

        if self.issues:
            raise IRVerificationError(self.issues)
        return self.module

    def _install_builtins(self, span: SourceSpan) -> None:
        self._install_signatures(BUILTINS, "builtin", span)
        self._install_signatures(INTRINSICS, "intrinsic", span)

    def _install_signatures(self, signatures, kind: str, span: SourceSpan) -> None:
        for name, signature in signatures.items():
            params = tuple(
                IRParameter(f"arg{index}", f"{kind}::{name}::param::{index}", value_type)
                for index, value_type in enumerate(signature.parameters)
            )
            self.definitions[f"{kind}::{name}"] = _Definition(
                name,
                kind,
                signature.type,
                span,
                params,
                signature.min_args,
                signature.max_args,
                signature.max_args is None,
            )

    def _collect_module_definitions(self) -> None:
        for item in self.module.items:
            self._collect_top_level(item)

    def _validate_impl_contracts(self) -> None:
        traits = {
            item.name: item for item in self.module.items if isinstance(item, IRTrait)
        }
        concrete_types = {
            item.name for item in self.module.items if isinstance(item, IRStruct)
        }
        seen_impls: Set[Tuple[Optional[str], str]] = set()

        for trait in traits.values():
            method_names: Set[str] = set()
            for method in trait.methods:
                if method.name in method_names:
                    self._issue(
                        "HIR0004",
                        f"Duplicate method '{method.name}' in trait '{trait.name}'",
                        method.span,
                    )
                method_names.add(method.name)
                if not method.params or method.params[0].name not in ("self", "this"):
                    self._issue(
                        "HIR0007",
                        f"Trait method '{trait.name}.{method.name}' must declare self first",
                        method.span,
                    )

        for item in self.module.items:
            if not isinstance(item, IRImpl):
                continue
            identity = (item.trait_name, item.target_type)
            if identity in seen_impls:
                label = item.trait_name or "inherent"
                self._issue(
                    "HIR0004",
                    f"Duplicate {label} implementation for '{item.target_type}'",
                    item.span,
                )
            seen_impls.add(identity)

            if item.target_type not in concrete_types:
                self._issue(
                    "HIR0005",
                    f"Implementation targets unknown struct '{item.target_type}'",
                    item.span,
                )

            methods: Dict[str, IRFunction] = {}
            for method in item.methods:
                if method.name in methods:
                    self._issue(
                        "HIR0004",
                        f"Duplicate method '{method.name}' in implementation for '{item.target_type}'",
                        method.span,
                    )
                methods[method.name] = method
                if (
                    item.trait_name
                    and (not method.params or method.params[0].name not in ("self", "this"))
                ):
                    self._issue(
                        "HIR0007",
                        f"Method '{item.target_type}.{method.name}' must declare self first",
                        method.span,
                    )

            if not item.trait_name:
                continue
            trait = traits.get(item.trait_name)
            if trait is None:
                self._issue(
                    "HIR0005",
                    f"Implementation references unknown trait '{item.trait_name}'",
                    item.span,
                )
                continue

            for requirement in trait.methods:
                implementation = methods.get(requirement.name)
                if implementation is None:
                    self._issue(
                        "HIR0007",
                        f"Implementation of '{item.trait_name}' for '{item.target_type}' "
                        f"is missing method '{requirement.name}'",
                        item.span,
                    )
                    continue
                self._validate_method_signature(
                    item.trait_name,
                    item.target_type,
                    requirement,
                    implementation,
                )

    def _validate_method_signature(
        self,
        trait_name: str,
        target_type: str,
        requirement: IRFunction,
        implementation: IRFunction,
    ) -> None:
        required_params = self._method_value_parameters(requirement)
        actual_params = self._method_value_parameters(implementation)
        mismatch = (
            requirement.is_async != implementation.is_async
            or requirement.return_type != implementation.return_type
            or len(required_params) != len(actual_params)
            or any(
                expected.type != actual.type
                for expected, actual in zip(required_params, actual_params)
            )
        )
        if mismatch:
            required_signature = self._method_signature(requirement)
            actual_signature = self._method_signature(implementation)
            self._issue(
                "HIR0006",
                f"Method '{target_type}.{requirement.name}' does not satisfy trait "
                f"'{trait_name}': expected {required_signature}, found {actual_signature}",
                implementation.span,
            )

    @staticmethod
    def _method_value_parameters(method: IRFunction) -> Tuple[IRParameter, ...]:
        if method.params and method.params[0].name in ("self", "this"):
            return method.params[1:]
        return method.params

    @classmethod
    def _method_signature(cls, method: IRFunction) -> str:
        parameters = ", ".join(str(param.type) for param in cls._method_value_parameters(method))
        async_prefix = "async " if method.is_async else ""
        return f"{async_prefix}fn({parameters}) -> {method.return_type}"

    def _collect_top_level(self, node: IRNode) -> None:
        self._check_span(node)
        if isinstance(node, IRFunction):
            self._define_function(node, "function")
            self._collect_parameters(node.params, "parameter")
            self._collect_block(node.body)
        elif isinstance(node, IRStruct):
            result = IRType(
                node.name,
                tuple(IRType(name) for name in node.generic_params),
            )
            self._define(
                node.symbol,
                _Definition(
                    node.name,
                    "struct",
                    function_type((field.type for field in node.fields), result),
                    node.span,
                    node.fields,
                    sum(field.default is None for field in node.fields),
                    len(node.fields),
                    False,
                    False,
                    node.generic_params,
                ),
            )
            self._collect_parameters(node.fields, "field")
        elif isinstance(node, IRTrait):
            self._define(node.symbol, _Definition(node.name, "trait", IRType(node.name), node.span))
            for method in node.methods:
                self._define_function(method, "trait-method")
                self._collect_parameters(method.params, "parameter")
                self._collect_block(method.body)
        elif isinstance(node, IRImpl):
            for method in node.methods:
                self._define_function(method, "impl-method")
                self._collect_parameters(method.params, "parameter")
                self._collect_block(method.body)
        elif isinstance(node, IRTypeAlias):
            self._define(node.symbol, _Definition(node.name, "type-alias", node.actual_type, node.span))
        elif isinstance(node, IREnum):
            self._define(node.symbol, _Definition(node.name, "enum", IRType(node.name), node.span))
            for member in node.members:
                if member.value is not None:
                    self._collect_expr(member.value)
                if member.is_variant:
                    symbol = f"enum::{node.name}::variant::{member.name}"
                    parameters = tuple(
                        IRParameter(
                            f"payload_{index}",
                            f"{symbol}::param::{index}",
                            payload_type,
                        )
                        for index, payload_type in enumerate(member.payload_types)
                    )
                    self._define_callable(
                        symbol, member.name, "enum-variant", parameters,
                        IRType(node.name, tuple(IRType(name) for name in node.generic_params)),
                        node.span, False, node.generic_params,
                    )
        elif isinstance(node, IRExternFunction):
            self._define_callable(
                node.symbol,
                node.name,
                "extern",
                node.params,
                node.return_type,
                node.span,
                node.varargs,
            )
            self._collect_parameters(node.params, "parameter")
        elif isinstance(node, IRNativeDirective):
            return
        elif isinstance(node, IRForeignImport):
            self._define(
                node.symbol,
                _Definition(node.alias, "foreign-module", IRType(f"foreign::{node.ecosystem}"), node.span),
            )
        elif isinstance(node, IRStatement):
            self._collect_statement(node)
        else:
            self._issue("HIR0009", f"Unsupported top-level node {type(node).__name__}", node.span)

    def _collect_parameters(self, parameters: Tuple[IRParameter, ...], kind: str) -> None:
        for parameter in parameters:
            self._define(
                parameter.symbol,
                _Definition(parameter.name, kind, parameter.type, self._parameter_span(parameter)),
            )
            if parameter.default is not None:
                self._collect_expr(parameter.default)

    def _collect_block(self, statements: Tuple[IRStatement, ...]) -> None:
        for statement in statements:
            self._collect_statement(statement)

    def _collect_statement(self, node: IRStatement) -> None:
        self._check_span(node)
        if isinstance(node, IRVarDecl):
            self._define(
                node.symbol,
                _Definition(node.name, "variable", node.type, node.span, is_const=node.is_const),
            )
            self._collect_expr(node.expr)
        elif isinstance(node, IRAssign):
            self._collect_expr(node.target)
            self._collect_expr(node.expr)
        elif isinstance(node, IRExprStatement):
            self._collect_expr(node.expr)
        elif isinstance(node, IRReturn):
            if node.expr is not None:
                self._collect_expr(node.expr)
        elif isinstance(node, IRThrow):
            self._collect_expr(node.expr)
        elif isinstance(node, IRYield):
            self._collect_expr(node.expr)
        elif isinstance(node, IRIf):
            self._collect_expr(node.condition)
            self._collect_block(node.then_branch)
            for condition, branch in node.elif_branches:
                self._collect_expr(condition)
                self._collect_block(branch)
            if node.else_branch is not None:
                self._collect_block(node.else_branch)
        elif isinstance(node, IRWhile):
            self._collect_expr(node.condition)
            self._collect_block(node.body)
        elif isinstance(node, IRFor):
            item_type = INT
            if node.collection_expr is not None:
                collection_type = node.collection_expr.type
                if collection_type.name in ("Array", "Iterator") and collection_type.arguments:
                    item_type = collection_type.arguments[0]
                elif collection_type == STRING:
                    item_type = STRING
                else:
                    item_type = ANY
            self._define(node.symbol, _Definition(node.var_name, "loop-variable", item_type, node.span))
            for expr in (node.start_expr, node.end_expr, node.collection_expr):
                if expr is not None:
                    self._collect_expr(expr)
            self._collect_block(node.body)
        elif isinstance(node, (IRBreak, IRContinue)):
            return
        elif isinstance(node, IRDefer):
            self._collect_expr(node.expr)
        elif isinstance(node, IRGuard):
            self._collect_expr(node.condition)
            self._collect_block(node.else_body)
        elif isinstance(node, (IRUnsafeBlock, IRSpawn, IRTestBlock)):
            self._collect_block(node.body)
        elif isinstance(node, IRAssert):
            self._collect_expr(node.condition)
        elif isinstance(node, IRMatch):
            self._collect_expr(node.expr)
            for case in node.cases:
                self._collect_pattern(case.pattern)
                self._collect_block(case.body)
        elif isinstance(node, IRTryCatch):
            self._collect_block(node.try_body)
            self._define(
                node.error_symbol,
                _Definition(node.error_name, "catch", STRING, node.span),
            )
            self._collect_block(node.catch_body)
        else:
            self._issue("HIR0009", f"Unsupported statement node {type(node).__name__}", node.span)

    def _collect_pattern(self, expr: IRExpr) -> None:
        if isinstance(expr, IRReference) and expr.symbol != "pattern::_":
            self._define(expr.symbol, _Definition(expr.name, "pattern-binding", expr.type, expr.span))
            return
        if isinstance(expr, IRCall):
            if expr.receiver is not None:
                self._collect_expr(expr.receiver)
            for argument in expr.args:
                self._collect_pattern(argument)
            return
        self._collect_expr(expr)

    def _collect_expr(self, expr: IRExpr) -> None:
        self._check_span(expr)
        if isinstance(expr, IRLambda):
            self._collect_parameters(expr.params, "lambda-parameter")
            self._collect_expr(expr.body)
        elif isinstance(expr, IRBinary):
            self._collect_expr(expr.left)
            self._collect_expr(expr.right)
        elif isinstance(expr, IRUnary):
            self._collect_expr(expr.expr)
        elif isinstance(expr, IRAwait):
            self._collect_expr(expr.expr)
        elif isinstance(expr, IRResultPropagate):
            self._collect_expr(expr.expr)
        elif isinstance(expr, IRCall):
            if expr.receiver is not None:
                self._collect_expr(expr.receiver)
            for argument in expr.args:
                self._collect_expr(argument)
        elif isinstance(expr, IRMemberAccess):
            self._collect_expr(expr.obj)
        elif isinstance(expr, IRIndexAccess):
            self._collect_expr(expr.obj)
            self._collect_expr(expr.index)
        elif isinstance(expr, IRArray):
            for element in expr.elements:
                self._collect_expr(element)
        elif isinstance(expr, IRNullCoalesce):
            self._collect_expr(expr.left)
            self._collect_expr(expr.right)
        elif isinstance(expr, IRConditional):
            self._collect_expr(expr.condition)
            self._collect_expr(expr.then_expr)
            self._collect_expr(expr.else_expr)
        elif isinstance(expr, IRMatchExpression):
            self._collect_expr(expr.subject)
            for case in expr.cases:
                if case.pattern is not None:
                    self._collect_expr(case.pattern)
                self._collect_expr(case.value)
        elif isinstance(expr, (IRLiteral, IRReference)):
            return
        else:
            self._issue("HIR0009", f"Unsupported expression node {type(expr).__name__}", expr.span)

    def _define_function(self, node: IRFunction, kind: str) -> None:
        public_result = task_of(node.return_type) if node.is_async else node.return_type
        self._define_callable(
            node.symbol,
            node.name,
            kind,
            node.params,
            public_result,
            node.span,
            False,
            node.generic_params,
        )

    def _define_callable(
        self,
        symbol: str,
        name: str,
        kind: str,
        parameters: Tuple[IRParameter, ...],
        result: IRType,
        span: SourceSpan,
        varargs: bool,
        generic_params: Tuple[str, ...] = (),
    ) -> None:
        required = sum(parameter.default is None for parameter in parameters)
        self._define(
            symbol,
            _Definition(
                name,
                kind,
                function_type((parameter.type for parameter in parameters), result),
                span,
                parameters,
                required,
                None if varargs else len(parameters),
                varargs,
                False,
                generic_params,
            ),
        )

    def _define(self, symbol: str, definition: _Definition) -> None:
        if not symbol:
            self._issue("HIR0009", f"{definition.kind} '{definition.name}' has an empty symbol identity", definition.span)
            return
        existing = self.definitions.get(symbol)
        if existing is not None:
            self._issue(
                "HIR0004",
                f"Duplicate symbol identity '{symbol}' for {definition.kind} '{definition.name}' "
                f"(already used by {existing.kind} '{existing.name}')",
                definition.span,
            )
            return
        self.definitions[symbol] = definition

    def _predeclared_module_symbols(self) -> Set[str]:
        result: Set[str] = set()
        for item in self.module.items:
            if isinstance(item, (IRFunction, IRStruct, IRTrait, IRTypeAlias, IREnum, IRExternFunction, IRForeignImport)):
                result.add(item.symbol)
            if isinstance(item, IREnum):
                result.update(
                    f"enum::{item.name}::variant::{member.name}"
                    for member in item.members if member.is_variant
                )
        return result

    def _visit_top_level(self, node: IRNode, active: Set[str]) -> None:
        self._check_span(node)
        if isinstance(node, IRFunction):
            self._visit_function(node, active)
        elif isinstance(node, IRStruct):
            parameter_active = set(active)
            for parameter in node.fields:
                self._visit_parameter_default(parameter, parameter_active)
                parameter_active.add(parameter.symbol)
        elif isinstance(node, IRTrait):
            for method in node.methods:
                self._visit_trait_method(method, active)
        elif isinstance(node, IRImpl):
            for method in node.methods:
                self._visit_function(method, active)
        elif isinstance(node, IRTypeAlias):
            self._check_type(node.actual_type, node.span)
        elif isinstance(node, IREnum):
            generic_params = set(node.generic_params)
            for member in node.members:
                if not member.name:
                    self._issue("HIR0009", "Enum member name must not be empty", node.span)
                if member.value is not None:
                    self._visit_expr(member.value, active)
                if member.is_variant and member.value is not None:
                    self._issue("HIR0009", "Payload enum variant cannot also have a discriminant", node.span)
                for payload_type in member.payload_types:
                    self._check_type(payload_type, node.span)
                    if payload_type.name in generic_params:
                        continue
        elif isinstance(node, IRExternFunction):
            self._check_type(node.return_type, node.span)
            parameter_active = set(active)
            for parameter in node.params:
                self._visit_parameter_default(parameter, parameter_active)
                parameter_active.add(parameter.symbol)
        elif isinstance(node, IRNativeDirective):
            if node.kind not in ("include", "link", "raw", "use"):
                self._issue("HIR0009", f"Unknown native directive kind '{node.kind}'", node.span)
        elif isinstance(node, IRForeignImport):
            if node.ecosystem not in ("cpp", "js", "python", "rust", "wasm"):
                self._issue("HIR0009", f"Unknown foreign ecosystem '{node.ecosystem}'", node.span)
            if not node.module or not node.alias or not node.symbol:
                self._issue("HIR0009", "Foreign import requires module, alias, and symbol", node.span)
        elif isinstance(node, IRStatement):
            self._visit_statement(node, active, loop_depth=0, return_type=None)

    def _visit_function(self, node: IRFunction, active: Set[str]) -> None:
        previous_async = self._inside_async
        previous_return_type = self._current_return_type
        self._inside_async = node.is_async
        self._current_return_type = node.return_type
        try:
            self._check_type(node.return_type, node.span)
            local_active = set(active)
            for parameter in node.params:
                self._visit_parameter_default(parameter, local_active)
                local_active.add(parameter.symbol)
            self._visit_block(node.body, local_active, loop_depth=0, return_type=node.return_type)
            if (
                self.require_definite_returns
                and node.return_type not in (ANY, VOID)
                and node.return_type.name != "Iterator"
                and not self._block_definitely_returns(node.body)
            ):
                self._issue(
                    "HIR0007",
                    f"Function '{node.name}' can fall through without returning '{node.return_type}'",
                    node.span,
                )
        finally:
            self._inside_async = previous_async
            self._current_return_type = previous_return_type

    def _visit_trait_method(self, node: IRFunction, active: Set[str]) -> None:
        """Validate a trait signature without treating it as an implementation."""
        self._check_type(node.return_type, node.span)
        parameter_active = set(active)
        for parameter in node.params:
            self._visit_parameter_default(parameter, parameter_active)
            parameter_active.add(parameter.symbol)
        if node.body:
            self._issue(
                "HIR0009",
                f"Trait method '{node.name}' must be a signature without a body",
                node.span,
            )

    def _visit_parameter_default(self, parameter: IRParameter, active: Set[str]) -> None:
        self._check_type(parameter.type, self._parameter_span(parameter))
        if parameter.default is not None:
            self._visit_expr(parameter.default, active)
            self._expect_compatible(
                parameter.type,
                parameter.default.type,
                parameter.default.span,
                f"Default value for parameter '{parameter.name}'",
            )

    def _visit_block(
        self,
        statements: Tuple[IRStatement, ...],
        active: Set[str],
        *,
        loop_depth: int,
        return_type: Optional[IRType],
    ) -> None:
        block_active = set(active)
        for statement in statements:
            self._visit_statement(statement, block_active, loop_depth=loop_depth, return_type=return_type)
            if isinstance(statement, IRVarDecl):
                block_active.add(statement.symbol)

    def _visit_statement(
        self,
        node: IRStatement,
        active: Set[str],
        *,
        loop_depth: int,
        return_type: Optional[IRType],
    ) -> None:
        self._check_span(node)
        if isinstance(node, IRVarDecl):
            self._check_type(node.type, node.span)
            self._visit_expr(node.expr, active)
            self._expect_compatible(node.type, node.expr.type, node.span, f"Variable '{node.name}'")
        elif isinstance(node, IRAssign):
            self._visit_expr(node.target, active)
            self._visit_expr(node.expr, active)
            if not isinstance(node.target, (IRReference, IRMemberAccess, IRIndexAccess)):
                self._issue("HIR0009", "Assignment target is not assignable", node.target.span)
            if isinstance(node.target, IRReference):
                definition = self.definitions.get(node.target.symbol)
                if definition is not None and definition.is_const:
                    self._issue("HIR0007", f"Cannot assign to constant '{definition.name}'", node.target.span)
            self._expect_compatible(node.target.type, node.expr.type, node.span, "Assignment")
        elif isinstance(node, IRExprStatement):
            self._visit_expr(node.expr, active)
        elif isinstance(node, IRReturn):
            if return_type is None:
                self._issue("HIR0007", "Return statement is outside a function", node.span)
            elif node.expr is None:
                if return_type not in (ANY, VOID):
                    self._issue("HIR0006", f"Expected return value of type '{return_type}'", node.span)
            else:
                self._visit_expr(node.expr, active)
                if return_type == VOID:
                    self._issue("HIR0006", "Void function cannot return a value", node.span)
                else:
                    self._expect_compatible(return_type, node.expr.type, node.span, "Return value")
        elif isinstance(node, IRThrow):
            self._visit_expr(node.expr, active)
        elif isinstance(node, IRYield):
            self._visit_expr(node.expr, active)
            if return_type is None or return_type.name != "Iterator" or len(return_type.arguments) != 1:
                self._issue("HIR0021", "yield requires an Iterator<T> function", node.span)
            else:
                self._expect_compatible(return_type.arguments[0], node.expr.type, node.span, "Yield value")
        elif isinstance(node, IRIf):
            self._visit_condition(node.condition, active, "if")
            self._visit_block(node.then_branch, active, loop_depth=loop_depth, return_type=return_type)
            for condition, branch in node.elif_branches:
                self._visit_condition(condition, active, "elif")
                self._visit_block(branch, active, loop_depth=loop_depth, return_type=return_type)
            if node.else_branch is not None:
                self._visit_block(node.else_branch, active, loop_depth=loop_depth, return_type=return_type)
        elif isinstance(node, IRWhile):
            self._visit_condition(node.condition, active, "while")
            self._visit_block(node.body, active, loop_depth=loop_depth + 1, return_type=return_type)
        elif isinstance(node, IRFor):
            range_form = node.start_expr is not None or node.end_expr is not None
            collection_form = node.collection_expr is not None
            if range_form == collection_form or (range_form and (node.start_expr is None or node.end_expr is None)):
                self._issue("HIR0009", "For loop must use exactly one complete range or one collection", node.span)
            for expr in (node.start_expr, node.end_expr):
                if expr is not None:
                    self._visit_expr(expr, active)
                    self._expect_compatible(INT, expr.type, expr.span, "For-loop range bound")
            item_type = INT
            if node.collection_expr is not None:
                self._visit_expr(node.collection_expr, active)
                collection_type = node.collection_expr.type
                if collection_type.name in ("Array", "Iterator") and collection_type.arguments:
                    item_type = collection_type.arguments[0]
                elif collection_type == STRING:
                    item_type = STRING
                elif collection_type not in (ANY, STRING):
                    self._issue("HIR0006", f"Type '{collection_type}' is not iterable", node.collection_expr.span)
            definition = self.definitions.get(node.symbol)
            if definition is not None and not (
                is_assignable(definition.type, item_type)
                or is_coercible(item_type, definition.type)
            ):
                self._issue("HIR0006", f"Loop variable '{node.var_name}' has incompatible type", node.span)
            loop_active = set(active)
            loop_active.add(node.symbol)
            self._visit_block(node.body, loop_active, loop_depth=loop_depth + 1, return_type=return_type)
        elif isinstance(node, (IRBreak, IRContinue)):
            if loop_depth == 0:
                self._issue("HIR0007", f"{type(node).__name__[2:-4].lower()} is outside a loop", node.span)
        elif isinstance(node, IRDefer):
            self._visit_expr(node.expr, active)
        elif isinstance(node, IRGuard):
            self._visit_condition(node.condition, active, "guard")
            self._visit_block(node.else_body, active, loop_depth=loop_depth, return_type=return_type)
            if not self._block_definitely_exits(node.else_body):
                self._issue("HIR0007", "Guard else block must exit the current control flow", node.span)
        elif isinstance(node, IRUnsafeBlock):
            self._visit_block(node.body, active, loop_depth=loop_depth, return_type=return_type)
        elif isinstance(node, IRSpawn):
            self._visit_block(node.body, active, loop_depth=0, return_type=None)
        elif isinstance(node, IRAssert):
            self._visit_condition(node.condition, active, "assert")
        elif isinstance(node, IRMatch):
            self._visit_expr(node.expr, active)
            if not node.cases:
                self._issue("HIR0009", "Match statement must contain at least one case", node.span)
            for index, case in enumerate(node.cases):
                is_fallback = isinstance(case.pattern, IRReference) or (
                    isinstance(case.pattern, IRLiteral) and case.pattern.value == "_"
                )
                if is_fallback and index != len(node.cases) - 1:
                    self._issue("HIR0009", "Match statement fallback must be the final arm", case.pattern.span)
                bindings = self._pattern_bindings(case.pattern)
                pattern_active = set(active)
                pattern_active.update(bindings)
                self._visit_pattern(case.pattern, pattern_active)
                if not is_fallback:
                    self._expect_compatible(
                        node.expr.type,
                        case.pattern.type,
                        case.pattern.span,
                        "Match statement pattern",
                    )
                self._visit_block(case.body, pattern_active, loop_depth=loop_depth, return_type=return_type)
        elif isinstance(node, IRTryCatch):
            self._visit_block(node.try_body, active, loop_depth=loop_depth, return_type=return_type)
            catch_active = set(active)
            catch_active.add(node.error_symbol)
            self._visit_block(node.catch_body, catch_active, loop_depth=loop_depth, return_type=return_type)
        elif isinstance(node, IRTestBlock):
            self._visit_block(node.body, active, loop_depth=0, return_type=None)
        else:
            self._issue("HIR0009", f"Unsupported statement node {type(node).__name__}", node.span)

    def _visit_condition(self, expr: IRExpr, active: Set[str], context: str) -> None:
        self._visit_expr(expr, active)
        if expr.type not in (ANY, BOOL):
            self._issue("HIR0006", f"{context} condition must be bool, found '{expr.type}'", expr.span)

    def _visit_pattern(self, expr: IRExpr, active: Set[str]) -> None:
        if isinstance(expr, IRCall) and expr.callee_symbol.startswith("pattern-constructor::"):
            for argument in expr.args:
                self._visit_pattern(argument, active)
            return
        self._visit_expr(expr, active)

    def _visit_expr(self, expr: IRExpr, active: Set[str]) -> None:
        self._check_span(expr)
        self._check_type(expr.type, expr.span)
        if isinstance(expr, IRLiteral):
            actual = self._literal_type(expr.value)
            if actual is None:
                self._issue("HIR0009", f"Unsupported literal value {type(expr.value).__name__}", expr.span)
            else:
                if (
                    isinstance(expr.value, int)
                    and not isinstance(expr.value, bool)
                    and not (-(1 << 63) <= expr.value <= (1 << 63) - 1)
                ):
                    self._issue(
                        "HIR0009",
                        f"Integer literal '{expr.value}' is outside the signed 64-bit range",
                        expr.span,
                    )
                self._expect_compatible(expr.type, actual, expr.span, "Literal")
        elif isinstance(expr, IRReference):
            if expr.symbol == "pattern::_":
                return
            definition = self.definitions.get(expr.symbol)
            if definition is None:
                self._issue("HIR0005", f"Reference '{expr.name}' uses unknown symbol '{expr.symbol}'", expr.span)
            elif expr.symbol not in active:
                self._issue("HIR0005", f"Reference '{expr.name}' is outside its lexical scope", expr.span)
            elif definition.kind not in ("pattern-binding",):
                self._expect_compatible(definition.type, expr.type, expr.span, f"Reference '{expr.name}'")
        elif isinstance(expr, IRBinary):
            self._visit_expr(expr.left, active)
            self._visit_expr(expr.right, active)
            self._verify_binary(expr)
        elif isinstance(expr, IRUnary):
            self._visit_expr(expr.expr, active)
            self._verify_unary(expr)
        elif isinstance(expr, IRAwait):
            self._visit_expr(expr.expr, active)
            if not self._inside_async:
                self._issue("HIR0007", "await expression is outside an async function", expr.span)
            if expr.expr.type == ANY:
                return
            if expr.expr.type.name != "Task" or len(expr.expr.type.arguments) != 1:
                self._issue(
                    "HIR0006",
                    f"await operand must be Task<T>, found '{expr.expr.type}'",
                    expr.expr.span,
                )
            else:
                self._expect_compatible(
                    expr.expr.type.arguments[0],
                    expr.type,
                    expr.span,
                    "Await result",
                )
        elif isinstance(expr, IRResultPropagate):
            self._visit_expr(expr.expr, active)
            operand = expr.expr.type
            owner = self._current_return_type
            if operand.name != "Result" or len(operand.arguments) != 2:
                self._issue("HIR0006", f"'?' operand must be Result<T, E>, found '{operand}'", expr.span)
            else:
                self._expect_compatible(operand.arguments[0], expr.type, expr.span, "Result propagation value")
            if owner is None or owner.name != "Result" or len(owner.arguments) != 2:
                self._issue("HIR0007", "Result propagation requires a Result-returning function", expr.span)
            elif operand.name == "Result" and len(operand.arguments) == 2:
                self._expect_compatible(owner.arguments[1], operand.arguments[1], expr.span, "Result propagation error")
        elif isinstance(expr, IRCall):
            if expr.receiver is not None:
                self._visit_expr(expr.receiver, active)
            for argument in expr.args:
                self._visit_expr(argument, active)
            self._verify_call(expr, active)
        elif isinstance(expr, IRMemberAccess):
            self._visit_expr(expr.obj, active)
            if not expr.member:
                self._issue("HIR0009", "Member name must not be empty", expr.span)
            elif expr.obj.type.name in ("int", "float", "bool", "void", "null"):
                self._issue("HIR0006", f"Type '{expr.obj.type}' cannot have members", expr.span)
            elif expr.obj.type.name in self.structs:
                struct_def = self.structs[expr.obj.type.name]
                field_map = {f.name: f.type for f in struct_def.fields}
                if expr.member not in field_map:
                    self._issue("HIR0006", f"Struct '{expr.obj.type.name}' has no member '{expr.member}'", expr.span)
                else:
                    raw_expected = field_map[expr.member]
                    subs = {}
                    if struct_def.generic_params and len(struct_def.generic_params) == len(expr.obj.type.arguments):
                        subs = dict(zip(struct_def.generic_params, expr.obj.type.arguments))
                    expected_type = self._substitute_generics(raw_expected, subs)
                    if expr.safe:
                        expected_type = expected_type.with_optional(True)
                    self._expect_compatible(expected_type, expr.type, expr.span, f"Member '{expr.member}'")
        elif isinstance(expr, IRIndexAccess):
            self._visit_expr(expr.obj, active)
            self._visit_expr(expr.index, active)
            self._expect_compatible(INT, expr.index.type, expr.index.span, "Index")
            if expr.obj.type.name not in ("Array", "Iterator", "string", "any"):
                self._issue("HIR0006", f"Type '{expr.obj.type}' cannot be indexed", expr.obj.span)
            elif expr.obj.type.name == "Array" and expr.obj.type.arguments:
                self._expect_compatible(expr.obj.type.arguments[0], expr.type, expr.span, "Array index result")
            elif expr.obj.type.name == "Iterator" and expr.obj.type.arguments:
                self._expect_compatible(expr.obj.type.arguments[0], expr.type, expr.span, "Iterator index result")
            elif expr.obj.type.name == "string":
                self._expect_compatible(STRING, expr.type, expr.span, "String index result")
        elif isinstance(expr, IRArray):
            element_type = expr.type.arguments[0] if expr.type.name == "Array" and expr.type.arguments else ANY
            if expr.type.name != "Array" or len(expr.type.arguments) != 1:
                self._issue("HIR0003", f"Array expression has invalid type '{expr.type}'", expr.span)
            for element in expr.elements:
                self._visit_expr(element, active)
                self._expect_compatible(element_type, element.type, element.span, "Array element")
        elif isinstance(expr, IRNullCoalesce):
            self._visit_expr(expr.left, active)
            self._visit_expr(expr.right, active)
            expected = expr.right.type if expr.left.type.name == "null" else expr.left.type.with_optional(False)
            self._expect_compatible(expected, expr.right.type, expr.right.span, "Null-coalescing fallback")
            self._expect_compatible(expected, expr.type, expr.span, "Null-coalescing result")
        elif isinstance(expr, IRConditional):
            self._visit_condition(expr.condition, active, "Conditional expression")
            self._visit_expr(expr.then_expr, active)
            self._visit_expr(expr.else_expr, active)
            self._expect_compatible(expr.type, expr.then_expr.type, expr.then_expr.span, "Conditional then branch")
            self._expect_compatible(expr.type, expr.else_expr.type, expr.else_expr.span, "Conditional else branch")
        elif isinstance(expr, IRMatchExpression):
            self._visit_expr(expr.subject, active)
            wildcard_indexes = []
            for index, case in enumerate(expr.cases):
                if case.pattern is None:
                    wildcard_indexes.append(index)
                else:
                    self._visit_expr(case.pattern, active)
                    self._expect_compatible(
                        expr.subject.type,
                        case.pattern.type,
                        case.pattern.span,
                        "Match expression pattern",
                    )
                self._visit_expr(case.value, active)
                self._expect_compatible(
                    expr.type,
                    case.value.type,
                    case.value.span,
                    "Match expression arm",
                )
            if wildcard_indexes != [len(expr.cases) - 1]:
                self._issue(
                    "HIR0019",
                    "Match expression must end with exactly one wildcard arm",
                    expr.span,
                )
        elif isinstance(expr, IRLambda):
            if not expr.type.is_function:
                self._issue("HIR0003", f"Lambda has non-function type '{expr.type}'", expr.span)
            lambda_active = set(active)
            for parameter in expr.params:
                self._visit_parameter_default(parameter, lambda_active)
                lambda_active.add(parameter.symbol)
            self._visit_expr(expr.body, lambda_active)
            if expr.type.is_function:
                if len(expr.type.parameter_types) != len(expr.params):
                    self._issue("HIR0003", "Lambda parameter count does not match its function type", expr.span)
                if expr.type.return_type is not None:
                    self._expect_compatible(expr.type.return_type, expr.body.type, expr.body.span, "Lambda result")
        else:
            self._issue("HIR0009", f"Unsupported expression node {type(expr).__name__}", expr.span)

    def _verify_call(self, expr: IRCall, active: Set[str]) -> None:
        if not expr.callee:
            self._issue("HIR0009", "Call callee name must not be empty", expr.span)
        if expr.receiver is not None:
            if not expr.callee_symbol.startswith("method::"):
                self._issue("HIR0009", "Receiver call must use a method symbol", expr.span)
            return
        definition = self.definitions.get(expr.callee_symbol)
        if definition is None:
            self._issue(
                "HIR0005",
                f"Call '{expr.callee}' uses unknown symbol '{expr.callee_symbol}'",
                expr.span,
            )
            return
        if expr.callee_symbol not in active:
            self._issue("HIR0005", f"Call target '{expr.callee}' is outside its lexical scope", expr.span)
            return
        if not definition.type.is_function:
            self._issue("HIR0008", f"Symbol '{expr.callee_symbol}' is not callable", expr.span)
            return
        if definition.name != expr.callee:
            self._issue(
                "HIR0010",
                f"Call name '{expr.callee}' does not match symbol name '{definition.name}'",
                expr.span,
            )
        count = len(expr.args)
        if count < definition.required_args or (
            definition.max_args is not None and count > definition.max_args
        ):
            maximum = "unbounded" if definition.max_args is None else str(definition.max_args)
            self._issue(
                "HIR0008",
                f"Call '{expr.callee}' has {count} argument(s); expected {definition.required_args}..{maximum}",
                expr.span,
            )
        substitutions: Dict[str, IRType] = {}
        generic_params = set(definition.generic_params)
        for argument, parameter in zip(expr.args, definition.parameters):
            self._infer_generic_substitutions(
                parameter.type, argument.type, generic_params, substitutions, argument.span,
            )
        # Some constructors (notably payload enum variants) cannot infer every
        # generic parameter from their payload list. The concrete expression
        # type is the remaining source of truth for those return-only params.
        if definition.type.return_type is not None:
            self._infer_generic_substitutions(
                definition.type.return_type,
                expr.type,
                generic_params,
                substitutions,
                expr.span,
            )
        for index, (argument, parameter) in enumerate(zip(expr.args, definition.parameters)):
            self._expect_compatible(
                self._substitute_generics(parameter.type, substitutions),
                argument.type,
                argument.span,
                f"Argument {index + 1} of '{expr.callee}'",
            )
        result = self._substitute_generics(definition.type.return_type or VOID, substitutions)
        self._expect_compatible(result, expr.type, expr.span, f"Result of '{expr.callee}'")

    def _verify_binary(self, expr: IRBinary) -> None:
        op = expr.op
        if op in self._COMPARISON_OPS:
            self._expect_compatible(BOOL, expr.type, expr.span, f"Result of '{op}'")
            return
        if op in self._LOGICAL_OPS:
            for operand in (expr.left, expr.right):
                if operand.type not in (ANY, BOOL, INT):
                    self._issue("HIR0006", f"Logical operand has invalid type '{operand.type}'", operand.span)
            self._expect_compatible(BOOL, expr.type, expr.span, f"Result of '{op}'")
            return
        if op in self._BITWISE_OPS:
            self._expect_compatible(INT, expr.left.type, expr.left.span, f"Left operand of '{op}'")
            self._expect_compatible(INT, expr.right.type, expr.right.span, f"Right operand of '{op}'")
            self._expect_compatible(INT, expr.type, expr.span, f"Result of '{op}'")
            return
        if op in self._ARITHMETIC_OPS:
            if op == "+" and STRING in (expr.left.type, expr.right.type):
                self._expect_compatible(STRING, expr.type, expr.span, "String concatenation result")
                return
            for operand in (expr.left, expr.right):
                if not operand.type.is_numeric and not operand.type.is_unknown:
                    self._issue("HIR0006", f"Arithmetic operand has invalid type '{operand.type}'", operand.span)
            expected = FLOAT if FLOAT in (expr.left.type, expr.right.type) else INT
            if expr.left.type.is_unknown or expr.right.type.is_unknown:
                expected = ANY
            self._expect_compatible(expected, expr.type, expr.span, f"Result of '{op}'")
            return
        self._issue("HIR0009", f"Unknown binary operator '{op}'", expr.span)

    def _verify_unary(self, expr: IRUnary) -> None:
        if expr.op not in self._UNARY_OPS:
            self._issue("HIR0009", f"Unknown unary operator '{expr.op}'", expr.span)
            return
        if expr.op in ("!", "not"):
            if expr.expr.type not in (ANY, BOOL, INT):
                self._issue("HIR0006", f"Logical operand has invalid type '{expr.expr.type}'", expr.expr.span)
            self._expect_compatible(BOOL, expr.type, expr.span, "Logical negation result")
        elif expr.op == "~":
            self._expect_compatible(INT, expr.expr.type, expr.expr.span, "Bitwise-not operand")
            self._expect_compatible(INT, expr.type, expr.span, "Bitwise-not result")
        elif expr.op in ("-", "+"):
            if not expr.expr.type.is_numeric and not expr.expr.type.is_unknown:
                self._issue("HIR0006", f"Numeric unary operand has invalid type '{expr.expr.type}'", expr.expr.span)
            self._expect_compatible(expr.expr.type, expr.type, expr.span, "Unary result")

    def _check_span(self, node: IRNode) -> None:
        identity = id(node)
        if identity in self._checked_spans:
            return
        self._checked_spans.add(identity)
        span = node.span
        if not span.source or span.line < 1 or span.column < 1 or span.length < 1:
            self._issue("HIR0002", f"Invalid source span {span!r}", span)

    def _check_type(self, value_type: IRType, span: SourceSpan) -> None:
        if value_type in self._checked_types:
            return
        self._checked_types.add(value_type)
        if not value_type.name:
            self._issue("HIR0003", "Type name must not be empty", span)
        if value_type.return_type is None and value_type.parameter_types:
            self._issue("HIR0003", f"Non-function type '{value_type.name}' has parameter types", span)
        if value_type.return_type is not None and value_type.name != "fn":
            self._issue("HIR0003", f"Callable type must use canonical name 'fn', found '{value_type.name}'", span)
        if value_type.name == "void" and (value_type.optional or value_type.arguments):
            self._issue("HIR0003", f"Invalid decorated void type '{value_type}'", span)
        for argument in value_type.arguments:
            self._check_type(argument, span)
        for parameter in value_type.parameter_types:
            self._check_type(parameter, span)
        if value_type.return_type is not None:
            self._check_type(value_type.return_type, span)

    def _expect_compatible(
        self,
        expected: IRType,
        actual: IRType,
        span: SourceSpan,
        context: str,
    ) -> None:
        resolved_expected = self._resolve_alias(expected)
        resolved_actual = self._resolve_alias(actual)
        if not (
            is_assignable(resolved_expected, resolved_actual)
            or is_coercible(resolved_actual, resolved_expected)
        ):
            self._issue("HIR0006", f"{context}: expected '{expected}', found '{actual}'", span)

    def _resolve_alias(self, value_type: IRType) -> IRType:
        seen: Set[str] = set()
        resolved = value_type
        while resolved.name in self.type_aliases and resolved.name not in seen:
            seen.add(resolved.name)
            target = self.type_aliases[resolved.name]
            resolved = IRType(
                target.name,
                target.arguments,
                resolved.optional or target.optional,
                resolved.pointer or target.pointer,
                target.parameter_types,
                target.return_type,
            )
        if resolved.arguments:
            resolved = IRType(
                resolved.name,
                tuple(self._resolve_alias(item) for item in resolved.arguments),
                resolved.optional,
                resolved.pointer,
                resolved.parameter_types,
                resolved.return_type,
            )
        return resolved

    def _pattern_bindings(self, expr: IRExpr) -> Set[str]:
        result: Set[str] = set()
        if isinstance(expr, IRReference) and expr.symbol != "pattern::_":
            result.add(expr.symbol)
        elif isinstance(expr, IRCall):
            for argument in expr.args:
                result.update(self._pattern_bindings(argument))
        return result

    @classmethod
    def _block_definitely_returns(cls, statements: Tuple[IRStatement, ...]) -> bool:
        return any(cls._statement_definitely_returns(statement) for statement in statements)

    @classmethod
    def _statement_definitely_returns(cls, statement: IRStatement) -> bool:
        if isinstance(statement, (IRReturn, IRThrow)):
            return True
        if isinstance(statement, IRIf):
            branches = [statement.then_branch, *(branch for _, branch in statement.elif_branches)]
            return statement.else_branch is not None and all(
                cls._block_definitely_returns(branch) for branch in (*branches, statement.else_branch)
            )
        if isinstance(statement, IRTryCatch):
            return cls._block_definitely_returns(statement.try_body) and cls._block_definitely_returns(statement.catch_body)
        if isinstance(statement, IRUnsafeBlock):
            return cls._block_definitely_returns(statement.body)
        if isinstance(statement, IRMatch):
            has_fallback = bool(statement.cases) and isinstance(
                statement.cases[-1].pattern, IRReference
            )
            if statement.cases and isinstance(statement.cases[-1].pattern, IRLiteral):
                has_fallback = statement.cases[-1].pattern.value == "_"
            return has_fallback and all(cls._block_definitely_returns(case.body) for case in statement.cases)
        return False

    @classmethod
    def _block_definitely_exits(cls, statements: Tuple[IRStatement, ...]) -> bool:
        for statement in statements:
            if isinstance(statement, (IRReturn, IRThrow, IRBreak, IRContinue)):
                return True
            if cls._statement_definitely_returns(statement):
                return True
        return False

    @staticmethod
    def _literal_type(value: object) -> Optional[IRType]:
        if value is None:
            return NULL
        if isinstance(value, bool):
            return BOOL
        if isinstance(value, int):
            return INT
        if isinstance(value, float):
            return FLOAT
        if isinstance(value, str):
            return STRING
        return None

    def _parameter_span(self, parameter: IRParameter) -> SourceSpan:
        if parameter.default is not None:
            return parameter.default.span
        return SourceSpan(self.module.source_name or "<unknown>", 1, 1)

    def _issue(self, code: str, message: str, span: SourceSpan) -> None:
        key = (code, message, span)
        if key not in self._issue_keys:
            self._issue_keys.add(key)
            self.issues.append(IRVerificationIssue(code, message, span))


def collect_hir_issues(
    module: IRModule,
    *,
    require_definite_returns: bool = True,
) -> Tuple[IRVerificationIssue, ...]:
    verifier = IRVerifier(module, require_definite_returns=require_definite_returns)
    try:
        verifier.verify()
    except IRVerificationError as error:
        return error.issues
    return ()


def verify_hir(module: IRModule, *, require_definite_returns: bool = True) -> IRModule:
    return IRVerifier(module, require_definite_returns=require_definite_returns).verify()
