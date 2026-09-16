from typing import Dict, List, Optional, Any, Set
import sys
from .ast_nodes import (
    ASTNode, ProgramNode, NumberNode, StringNode, BooleanNode, NullNode,
    IdentifierNode, BinaryOpNode, UnaryOpNode, AwaitNode, ResultPropagateNode, NullCoalesceNode, ConditionalExprNode, MemberAccessNode,
    IndexAccessNode, ArrayNode, LambdaNode, FunctionCallNode, VarDeclNode, DestructureDeclNode,
    AssignNode, TypeAliasNode, StructDefNode, TraitDefNode, ImplBlockNode,
    EnumDefNode, UnsafeBlockNode, SpawnNode, TestBlockNode, AssertNode,
    FunctionDefNode, MatchNode, MatchExprNode, TryCatchNode, IfNode, WhileNode, ForNode,
    ReturnNode, ThrowNode, YieldNode, BreakNode, ContinueNode, TypeNode, NativeIncludeNode,
    NativeLinkNode, NativeRawNode, NativeUseNode, ExternFnDeclNode,
    DeferNode, GuardNode, ImportNode
)
from .diagnostics import DiagnosticEmitter
from .foreign_bindings import ForeignCallableBinding, ForeignModuleBinding

_INT64_MIN = -(1 << 63)
_INT64_MAX = (1 << 63) - 1
_INTEGER_TYPES = frozenset(("int", "i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64", "uintptr"))
_FIXED_INTEGER_RANGES = {
    "i8": (-(1 << 7), (1 << 7) - 1),
    "i16": (-(1 << 15), (1 << 15) - 1),
    "i32": (-(1 << 31), (1 << 31) - 1),
    "i64": (_INT64_MIN, _INT64_MAX),
    "int": (_INT64_MIN, _INT64_MAX),
    "u8": (0, (1 << 8) - 1),
    "u16": (0, (1 << 16) - 1),
    "u32": (0, (1 << 32) - 1),
    "u64": (0, (1 << 64) - 1),
    "uintptr": (0, (1 << 64) - 1),
}


def _generic_type_parts(type_name: str) -> tuple[str, tuple[str, ...]]:
    text = type_name.strip()
    if "<" not in text or not text.endswith(">"):
        return text, ()
    base, raw_arguments = text.split("<", 1)
    raw_arguments = raw_arguments[:-1]
    arguments: List[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(raw_arguments):
        if character == "<":
            depth += 1
        elif character == ">":
            depth -= 1
        elif character == "," and depth == 0:
            arguments.append(raw_arguments[start:index].strip())
            start = index + 1
    arguments.append(raw_arguments[start:].strip())
    return base.strip(), tuple(arguments)


def _substitute_type(type_name: str, substitutions: Dict[str, str]) -> str:
    text = type_name.strip()
    suffix = "?" if text.endswith("?") else ""
    if suffix:
        text = text[:-1]
    pointer = "*" if text.startswith("*") else ""
    if pointer:
        text = text[1:]
    if text in substitutions:
        return pointer + substitutions[text] + suffix
    base, arguments = _generic_type_parts(text)
    if not arguments:
        return pointer + text + suffix
    rendered = ", ".join(_substitute_type(item, substitutions) for item in arguments)
    return f"{pointer}{base}<{rendered}>{suffix}"


def _collect_type_substitutions(
    pattern: str,
    actual: str,
    generic_params: Set[str],
    substitutions: Dict[str, str],
) -> bool:
    pattern = pattern.strip()
    actual = actual.strip()
    if pattern in generic_params:
        previous = substitutions.get(pattern)
        if previous is None or previous == "any":
            substitutions[pattern] = actual
            return True
        return actual == "any" or previous == actual
    pattern_base, pattern_arguments = _generic_type_parts(pattern.rstrip("?"))
    actual_base, actual_arguments = _generic_type_parts(actual.rstrip("?"))
    if pattern_base != actual_base or len(pattern_arguments) != len(actual_arguments):
        return True
    return all(
        _collect_type_substitutions(expected, found, generic_params, substitutions)
        for expected, found in zip(pattern_arguments, actual_arguments)
    )


class TypeChecker:
    def __init__(self, ast: ProgramNode, filepath: str = '<anonymous>', source: str = ''):
        self.ast = ast
        self.filepath = filepath
        self.source = source
        self.scopes: List[Dict[str, str]] = [{}]
        self.struct_defs: Dict[str, Dict[str, str]] = {}
        self.struct_generic_params: Dict[str, tuple[str, ...]] = {}
        self.type_aliases: Dict[str, str] = {}
        self.func_defs: Dict[str, Dict[str, Any]] = {}
        self.is_inside_unsafe = False
        self.current_return_type: Optional[str] = None
        self.current_is_async = False
        self.foreign_modules: Dict[str, ForeignModuleBinding] = {}
        self.foreign_types: Dict[str, Dict[str, ForeignCallableBinding]] = {}
        self.enum_variants: Dict[str, Dict[str, Any]] = {}
        self.generic_type_params: Set[str] = set()
        
        # Prepopulate builtin runtime functions
        self.builtins = {
            'print': 'void', 'input': 'string', 'to_string': 'string',
            'to_int': 'int', 'contains': 'bool', 'is_number': 'bool',
            'addr': 'uintptr', 'peek': 'uintptr', 'memdump': 'void',
            'delay_ms': 'void', 'channel': 'Channel', 'Ok': 'Result',
            'Err': 'Result', 'len': 'int', 'ord': 'int', 'char_code_at': 'int',
            'args': 'Array<string>', 'map': 'any', 'filter': 'any', 'fold': 'any'
        }
        for b, t in self.builtins.items():
            self.scopes[0][b] = t

    def current_scope(self) -> Dict[str, str]:
        return self.scopes[-1]

    def enter_scope(self):
        self.scopes.append({})

    def exit_scope(self):
        if len(self.scopes) > 1:
            self.scopes.pop()

    def lookup(self, name: str) -> Optional[str]:
        for s in reversed(self.scopes):
            if name in s:
                return s[name]
        return None

    def declare(self, name: str, type_name: str):
        self.current_scope()[name] = type_name

    def is_type_compatible(self, type_node: Optional[TypeNode], actual: str) -> bool:
        if not type_node or actual in ('any', None):
            return True
        if type_node.is_optional and actual == 'null':
            return True
        # Optional types accept their base type: int? accepts int
        if type_node.is_optional:
            base_name = type_node.name
            if self.is_compatible(base_name, actual):
                return True
        expected_str = str(type_node)
        return self.is_compatible(expected_str, actual)

    def is_compatible(self, expected: str, actual: str) -> bool:
        if expected in ('any', None) or actual in ('any', None):
            return True
        expected = self.resolve_alias(expected)
        actual = self.resolve_alias(actual)
        if expected == actual:
            return True
        if expected in self.generic_type_params:
            return True
        # Strip optional suffix for base type comparison
        exp_base = expected.rstrip('?')
        act_base = actual.rstrip('?')
        if exp_base == act_base:
            return True
        if exp_base in _INTEGER_TYPES and act_base in _INTEGER_TYPES:
            return True
        # Pointer compatibility (*void can accept any *T or vice versa)
        if exp_base.startswith('*') and act_base.startswith('*'):
            return True
        # int can widen to float
        if exp_base == 'float' and act_base == 'int':
            return True
        expected_name, expected_arguments = _generic_type_parts(exp_base)
        actual_name, actual_arguments = _generic_type_parts(act_base)
        if expected_arguments and actual_arguments and expected_name == actual_name:
            return len(expected_arguments) == len(actual_arguments) and all(
                self.is_compatible(expected_argument, actual_argument)
                for expected_argument, actual_argument in zip(expected_arguments, actual_arguments)
            )
        # Function pointer / callback compatibility
        if (exp_base.startswith('fn(') or exp_base.startswith('fn->') or exp_base.startswith('function')) and (act_base.startswith('fn(') or act_base.startswith('fn->') or act_base.startswith('function')):
            exp_ret = exp_base.split('->')[-1].strip() if '->' in exp_base else 'any'
            act_ret = act_base.split('->')[-1].strip() if '->' in act_base else 'any'
            return self.is_compatible(exp_ret, act_ret)
        # Generic prefix compatibility: Result<T, E> matches Result, Array<T> matches Array
        if (
            (exp_base.startswith('Result') and act_base.startswith('Result'))
            or (exp_base.startswith('Array') and act_base.startswith('Array'))
            or (exp_base.startswith('Task') and act_base.startswith('Task'))
        ):
            return True
        # null compatibility with Option / Nullable types
        if actual == 'null' and ('?' in expected or 'Option' in expected):
            return True
        return False

    def resolve_alias(self, type_name: str) -> str:
        """Resolve transparent aliases without looping on malformed cycles."""
        suffix = "?" if type_name.endswith("?") else ""
        current = type_name[:-1] if suffix else type_name
        seen: Set[str] = set()
        while current in self.type_aliases and current not in seen:
            seen.add(current)
            current = self.type_aliases[current]
        return current + suffix

    def _check_fixed_integer_literal(self, node: VarDeclNode):
        if not node.type_annot or not isinstance(node.expr, NumberNode):
            return
        type_name = node.type_annot.name
        bounds = _FIXED_INTEGER_RANGES.get(type_name)
        value = node.expr.value
        if not bounds or not isinstance(value, int) or isinstance(value, bool):
            return
        if not (bounds[0] <= value <= bounds[1]):
            DiagnosticEmitter.emit_error(
                self.filepath, self.source, node.expr.line, node.expr.col,
                "E2024", f"Integer literal does not fit in '{type_name}'",
                expected=f"{bounds[0]}..{bounds[1]}",
                found=str(value),
                help_msg=f"Choose a value representable by {type_name} or use a wider integer type.",
            )

    def check(self):
        self._validate_integer_literals(self.ast)

        # 1st Pass: Register all Structs & Functions
        for stmt in self.ast.statements:
            if isinstance(stmt, ImportNode) and stmt.ecosystem is not None:
                binding = stmt.binding if isinstance(stmt.binding, ForeignModuleBinding) else None
                module_type = (
                    binding.module_type
                    if binding is not None
                    else f"foreign-module::{stmt.ecosystem}::{stmt.path}"
                )
                self.declare(stmt.alias, module_type)
                if binding is not None:
                    self.foreign_modules[module_type] = binding
                    for type_name, type_binding in binding.types.items():
                        self.foreign_types[type_name] = dict(type_binding.methods)
            elif isinstance(stmt, StructDefNode):
                fields = {}
                for f in stmt.fields:
                    f_type = str(f.type_annot) if f.type_annot else 'any'
                    fields[f.name] = f_type
                self.struct_defs[stmt.name] = fields
                self.struct_generic_params[stmt.name] = tuple(stmt.generic_params)
                self.declare(stmt.name, stmt.name)
            elif isinstance(stmt, TypeAliasNode):
                actual = str(stmt.actual_type)
                self.type_aliases[stmt.name] = actual
                self.declare(stmt.name, actual)
            elif isinstance(stmt, EnumDefNode):
                self.declare(stmt.name, stmt.name)
                self.generic_type_params.update(stmt.generic_params)
                for member in stmt.members:
                    if not member.is_variant:
                        continue
                    if member.name in self.enum_variants:
                        previous = self.enum_variants[member.name]["enum"]
                        DiagnosticEmitter.emit_error(
                            self.filepath, self.source, stmt.line, stmt.col,
                            "E2033", f"Duplicate enum variant constructor '{member.name}'",
                            note=f"The name is already used by enum '{previous}'.",
                            help_msg="Variant constructor names must be unique within a module.",
                        )
                    params = [
                        (f"payload_{index}", str(payload_type))
                        for index, payload_type in enumerate(member.payload_types)
                    ]
                    definition = {
                        "enum": stmt.name,
                        "generic_params": tuple(stmt.generic_params),
                        "payload_types": tuple(str(item) for item in member.payload_types),
                        "ret": stmt.name,
                        "public_ret": stmt.name,
                        "params": params,
                        "is_enum_variant": True,
                    }
                    self.enum_variants[member.name] = definition
                    self.func_defs[member.name] = definition
                    self.declare(member.name, f"fn->{stmt.name}")
            elif isinstance(stmt, FunctionDefNode):
                ret_t = str(stmt.return_type) if stmt.return_type else 'any'
                params = [(p.name, str(p.type_annot) if p.type_annot else 'any') for p in stmt.params]
                defaults = [p.default_val for p in stmt.params]
                public_ret = f'Task<{ret_t}>' if stmt.is_async else ret_t
                self.func_defs[stmt.name] = {
                    'ret': ret_t,
                    'public_ret': public_ret,
                    'params': params,
                    'defaults': defaults,
                    'is_async': stmt.is_async,
                    'generic_params': tuple(stmt.generic_params),
                }
                self.declare(stmt.name, f'fn->{public_ret}')
            elif isinstance(stmt, ExternFnDeclNode):
                ret_t = str(stmt.return_type) if stmt.return_type else 'void'
                params = [(p.name, str(p.type_annot) if p.type_annot else 'any') for p in stmt.params]
                self.func_defs[stmt.name] = {'ret': ret_t, 'params': params, 'is_extern': True}
                self.declare(stmt.name, f'fn->{ret_t}')
            elif isinstance(stmt, VarDeclNode) and getattr(stmt, "_interface_only", False):
                declared = (
                    str(stmt.type_annot)
                    if stmt.type_annot is not None
                    else getattr(stmt, "inferred_type", "any")
                )
                self.declare(stmt.name, declared)

        # 2nd Pass: Full Semantic Analysis & Type Inference
        for stmt in self.ast.statements:
            if getattr(stmt, "_interface_only", False):
                continue
            self.visit(stmt)

    def _validate_integer_literals(self, value: object):
        """Reject invalid source literals before inference can skip a subtree."""
        if isinstance(value, NumberNode):
            if (
                isinstance(value.value, int)
                and not isinstance(value.value, bool)
                and not (_INT64_MIN <= value.value <= _INT64_MAX)
            ):
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, value.line, value.col,
                    "E2012", "Integer literal is outside the signed 64-bit range",
                    expected=f"{_INT64_MIN}..{_INT64_MAX}",
                    found=str(value.value),
                    help_msg="Use a signed 64-bit literal or compute the wrapped value at runtime.",
                )
        if isinstance(value, ASTNode):
            for child in vars(value).values():
                self._validate_integer_literals(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                self._validate_integer_literals(child)

    def _require_bool_condition(self, node: ASTNode, context: str):
        actual = self.infer_type(node)
        if actual not in ('bool', 'any'):
            DiagnosticEmitter.emit_error(
                self.filepath, self.source, node.line, node.col,
                "E2013", f"{context} condition must have type 'bool'",
                expected="bool",
                found=actual,
                help_msg="Compare the value explicitly instead of relying on implicit truthiness.",
            )

    def visit(self, node: Optional[ASTNode]):
        if not node:
            return

        if isinstance(node, (NativeIncludeNode, NativeLinkNode, NativeRawNode, NativeUseNode, ExternFnDeclNode, ImportNode)):
            return

        if isinstance(node, VarDeclNode):
            self._check_fixed_integer_literal(node)
            self.visit(node.expr)
            val_type = self.infer_type(node.expr)
            if node.type_annot:
                if not self.is_type_compatible(node.type_annot, val_type):
                    declared_name = str(node.type_annot)
                    DiagnosticEmitter.emit_error(
                        self.filepath, self.source, node.line, node.col,
                        "E2001", f"Type mismatch in variable declaration '{node.name}'",
                        expected=declared_name,
                        found=val_type,
                        help_msg=f"Cannot assign value of type '{val_type}' to variable '{node.name}' of type '{declared_name}'."
                    )
                declared_name = str(node.type_annot)
                self.declare(node.name, declared_name)
                node.inferred_type = declared_name
            else:
                self.declare(node.name, val_type)
                node.inferred_type = val_type

        elif isinstance(node, DestructureDeclNode):
            self.visit(node.expr)
            value_type = self.infer_type(node.expr)
            binding_types: List[str] = []
            if node.pattern_kind == "array":
                base, arguments = _generic_type_parts(value_type)
                if value_type != "any" and base != "Array":
                    DiagnosticEmitter.emit_error(
                        self.filepath, self.source, node.line, node.col,
                        "E2048", "Array destructuring requires an Array value",
                        expected="Array<T>", found=value_type,
                    )
                element_type = arguments[0] if arguments else "any"
                binding_types = [element_type] * len(node.names)
            else:
                fields = self.struct_defs.get(node.struct_name)
                if fields is None:
                    DiagnosticEmitter.emit_error(
                        self.filepath, self.source, node.line, node.col,
                        "E2049", f"Unknown struct destructuring pattern '{node.struct_name}'",
                        expected="declared struct", found=node.struct_name,
                    )
                if value_type != "any" and value_type != node.struct_name:
                    DiagnosticEmitter.emit_error(
                        self.filepath, self.source, node.line, node.col,
                        "E2049", "Struct destructuring value has the wrong type",
                        expected=node.struct_name, found=value_type,
                    )
                field_items = list((fields or {}).items())
                if len(node.names) != len(field_items):
                    DiagnosticEmitter.emit_error(
                        self.filepath, self.source, node.line, node.col,
                        "E2050", f"Struct pattern '{node.struct_name}' has the wrong number of bindings",
                        expected=str(len(field_items)), found=str(len(node.names)),
                    )
                binding_types = [field_type for _, field_type in field_items]

            for name, binding_type in zip(node.names, binding_types):
                if name != "_":
                    self.declare(name, binding_type)

        elif isinstance(node, AssignNode):
            val_type = self.infer_type(node.expr)
            if isinstance(node.target, IdentifierNode):
                existing = self.lookup(node.target.name)
                if existing and not self.is_compatible(existing, val_type):
                    DiagnosticEmitter.emit_error(
                        self.filepath, self.source, node.line, node.col,
                        "E2002", f"Type mismatch in assignment to '{node.target.name}'",
                        expected=existing,
                        found=val_type,
                        help_msg=f"Cannot assign value of type '{val_type}' to variable '{node.target.name}' of type '{existing}'."
                    )
                elif not existing:
                    self.declare(node.target.name, val_type)
            self.visit(node.target)
            self.visit(node.expr)

        elif isinstance(node, FunctionDefNode):
            self.enter_scope()
            prev_ret = self.current_return_type
            prev_async = self.current_is_async
            prev_generic_params = self.generic_type_params
            self.generic_type_params = prev_generic_params | set(node.generic_params)
            self.current_return_type = str(node.return_type) if node.return_type else None
            self.current_is_async = node.is_async
            for p in node.params:
                p_type = str(p.type_annot) if p.type_annot else 'any'
                self.declare(p.name, p_type)
            for s in node.body:
                self.visit(s)
            self.current_return_type = prev_ret
            self.current_is_async = prev_async
            self.generic_type_params = prev_generic_params
            self.exit_scope()

        elif isinstance(node, ReturnNode):
            if node.expr:
                self.visit(node.expr)
                ret_val_type = self.infer_type(node.expr)
                if self.current_return_type and not self.is_compatible(self.current_return_type, ret_val_type):
                    DiagnosticEmitter.emit_error(
                        self.filepath, self.source, node.line, node.col,
                        "E2004", f"Return type mismatch in function",
                        expected=self.current_return_type,
                        found=ret_val_type,
                        help_msg=f"Function was declared with return type '{self.current_return_type}', but returns a value of type '{ret_val_type}'."
                    )

        elif isinstance(node, ThrowNode):
            self.visit(node.expr)

        elif isinstance(node, YieldNode):
            value_type = self.infer_type(node.expr)
            owner_name, owner_arguments = _generic_type_parts(self.current_return_type or "")
            if self.current_return_type is None:
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.line, node.col,
                    "E2045", "yield is only valid inside an iterator function",
                    help_msg="Place yield inside a function returning Iterator<T>.",
                )
            elif owner_name != "Iterator" or len(owner_arguments) != 1:
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.line, node.col,
                    "E2046", "A function using yield must return Iterator<T>",
                    expected="Iterator<T>", found=self.current_return_type,
                )
            elif not self.is_compatible(owner_arguments[0], value_type):
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.line, node.col,
                    "E2047", "Yielded value has the wrong iterator element type",
                    expected=owner_arguments[0], found=value_type,
                )
            self.visit(node.expr)

        elif isinstance(node, AwaitNode):
            self.visit(node.expr)
            self.infer_type(node)

        elif isinstance(node, ResultPropagateNode):
            operand_type = self.infer_type(node.expr)
            operand_name, operand_arguments = _generic_type_parts(operand_type)
            return_name, return_arguments = _generic_type_parts(self.current_return_type or "")
            if self.current_return_type is None:
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.line, node.col,
                    "E2036", "Result propagation is only valid inside a function",
                    help_msg="Move '?' into a function that returns Result<T, E>.",
                )
            elif operand_name != "Result" or len(operand_arguments) != 2:
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.line, node.col,
                    "E2037", "The '?' operand must have type Result<T, E>",
                    expected="Result<T, E>", found=operand_type,
                    help_msg="Use '?' only on an expression that can return an error.",
                )
            elif return_name != "Result" or len(return_arguments) != 2:
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.line, node.col,
                    "E2038", "A function using '?' must return Result<T, E>",
                    expected="Result<T, E>", found=self.current_return_type,
                    help_msg="Change the function return type or handle the error with match.",
                )
            elif not self.is_compatible(return_arguments[1], operand_arguments[1]):
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.line, node.col,
                    "E2039", "Propagated Result error type is incompatible",
                    expected=return_arguments[1], found=operand_arguments[1],
                    help_msg="Map the error to the function's declared Result error type.",
                )
            self.visit(node.expr)

        elif isinstance(node, StructDefNode):
            pass

        elif isinstance(node, UnsafeBlockNode):
            prev = self.is_inside_unsafe
            self.is_inside_unsafe = True
            self.enter_scope()
            for s in node.body:
                self.visit(s)
            self.exit_scope()
            self.is_inside_unsafe = prev

        elif isinstance(node, DeferNode):
            self.visit(node.expr)

        elif isinstance(node, GuardNode):
            self._require_bool_condition(node.condition, "guard")
            self.enter_scope()
            for s in node.else_body: self.visit(s)
            self.exit_scope()

        elif isinstance(node, IfNode):
            self._require_bool_condition(node.condition, "if")
            self.enter_scope()
            for s in node.then_branch: self.visit(s)
            self.exit_scope()
            for cond, branch in node.elif_branches:
                self._require_bool_condition(cond, "elif")
                self.enter_scope()
                for s in branch: self.visit(s)
                self.exit_scope()
            if node.else_branch:
                self.enter_scope()
                for s in node.else_branch: self.visit(s)
                self.exit_scope()

        elif isinstance(node, WhileNode):
            self._require_bool_condition(node.condition, "while")
            self.enter_scope()
            for s in node.body: self.visit(s)
            self.exit_scope()

        elif isinstance(node, ForNode):
            self.enter_scope()
            if node.collection_expr:
                c_type = self.infer_type(node.collection_expr)
                collection_name, collection_arguments = _generic_type_parts(c_type)
                elem_type = collection_arguments[0] if collection_name in ('Array', 'Iterator') and len(collection_arguments) == 1 else ('string' if c_type == 'string' else 'any')
                self.declare(node.var_name, elem_type)
            else:
                self.declare(node.var_name, 'int')
            for s in node.body: self.visit(s)
            self.exit_scope()

        elif isinstance(node, MatchNode):
            subject_type = self.infer_type(node.expr)
            for pat, statements in node.cases:
                self.enter_scope()
                self._declare_pattern_bindings(pat, subject_type)
                for statement in statements:
                    self.visit(statement)
                self.exit_scope()

        elif isinstance(node, TryCatchNode):
            self.enter_scope()
            for s in node.try_body: self.visit(s)
            self.exit_scope()
            self.enter_scope()
            self.declare(node.err_name, 'string')
            for s in node.catch_body: self.visit(s)
            self.exit_scope()

        elif isinstance(node, ArrayNode):
            for element in node.elements:
                self.visit(element)

        elif isinstance(node, IndexAccessNode):
            index_type = self.infer_type(node.index_expr)
            if index_type not in _INTEGER_TYPES and index_type != 'any':
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.index_expr.line, node.index_expr.col,
                    'E2005', 'Collection index must be an integer',
                    expected='integer index',
                    found=index_type,
                    help_msg='Convert the index to an integer before indexing.',
                )
            self.visit(node.obj)
            self.visit(node.index_expr)

        elif isinstance(node, FunctionCallNode):
            if isinstance(node.callee, str) and node.callee in ("map", "filter", "fold"):
                self._infer_collection_builtin(node)
            if node.callee in ('peek', 'memdump') and not self.is_inside_unsafe:
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.line, node.col,
                    'E1050', f'Unsafe memory operation \'{node.callee}()\' called outside of unsafe block',
                    expected='unsafe { ... } block',
                    found='safe context',
                    help_msg='Wrap raw pointer dereferencing and memory inspections inside \'unsafe { ... }\'.'
                )
            
            foreign_callable = self._foreign_callable(node)
            if foreign_callable is not None:
                self._check_foreign_arguments(node, foreign_callable)
            # Check argument types if function is known
            elif node.callee in self.func_defs:
                definition = self.func_defs[node.callee]
                param_specs = definition['params']
                defaults = definition.get('defaults') or []
                # Resolve omitted trailing arguments by appending their default
                # value expressions so downstream lowering and code generation
                # always observe a fully-saturated call.
                while len(node.args) < len(param_specs):
                    index = len(node.args)
                    default = defaults[index] if index < len(defaults) else None
                    if default is None:
                        break
                    node.args.append(default)
                if len(node.args) != len(param_specs):
                    DiagnosticEmitter.emit_error(
                        self.filepath, self.source, node.line, node.col,
                        "E2007", f"Function '{node.callee}' expected {len(param_specs)} arguments, but got {len(node.args)}",
                        expected=f"{len(param_specs)} arguments",
                        found=f"{len(node.args)} arguments",
                        help_msg=f"Provide an argument for every parameter without a default value in '{node.callee}()'."
                    )
                generic_params = set(definition.get('generic_params') or ())
                substitutions: Dict[str, str] = {}
                argument_types = [self.infer_type(argument) for argument in node.args]
                for (_name, parameter_type), argument_type in zip(param_specs, argument_types):
                    _collect_type_substitutions(
                        parameter_type, argument_type, generic_params, substitutions,
                    )
                node.generic_substitutions = substitutions
                for idx, arg in enumerate(node.args):
                    if idx < len(param_specs):
                        p_name, p_type = param_specs[idx]
                        arg_type = argument_types[idx]
                        expected_type = _substitute_type(p_type, substitutions)
                        if not self.is_compatible(expected_type, arg_type):
                            DiagnosticEmitter.emit_error(
                                self.filepath, self.source, arg.line, arg.col,
                                "E2003", f"Argument type mismatch for parameter '{p_name}' in call to '{node.callee}()'",
                                expected=expected_type,
                                found=arg_type,
                                help_msg=f"Function '{node.callee}' expects type '{expected_type}' for argument '{p_name}', but received '{arg_type}'."
                            )
            elif node.callee in self.struct_defs:
                struct_fields = list(self.struct_defs[node.callee].items())
                generic_params = set(self.struct_generic_params.get(node.callee, ()))
                substitutions: Dict[str, str] = {}
                argument_types = [self.infer_type(argument) for argument in node.args]
                for (_name, field_type), argument_type in zip(struct_fields, argument_types):
                    _collect_type_substitutions(
                        field_type, argument_type, generic_params, substitutions,
                    )
                node.generic_substitutions = substitutions
                for idx, arg in enumerate(node.args):
                    if idx < len(struct_fields):
                        f_name, f_type = struct_fields[idx]
                        arg_type = argument_types[idx]
                        expected_type = _substitute_type(f_type, substitutions)
                        if not self.is_compatible(expected_type, arg_type):
                            DiagnosticEmitter.emit_error(
                                self.filepath, self.source, arg.line, arg.col,
                                "E2006", f"Struct field '{f_name}' type mismatch in constructor for '{node.callee}'",
                                expected=expected_type,
                                found=arg_type,
                                help_msg=f"Struct '{node.callee}' field '{f_name}' has type '{expected_type}', but received '{arg_type}'."
                            )
                            
            for a in node.args:
                self.visit(a)

        elif isinstance(node, MemberAccessNode):
            self.visit(node.obj)

        elif isinstance(node, BinaryOpNode):
            l_t = self.infer_type(node.left)
            r_t = self.infer_type(node.right)
            if l_t != 'any' and r_t != 'any' and node.op in ('-', '*', '/', '%') and ('string' in (l_t, r_t) or 'bool' in (l_t, r_t)):
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.line, node.col,
                    "E2005", f"Operator '{node.op}' is not supported between types '{l_t}' and '{r_t}'",
                    expected=f"numeric operands for '{node.op}'",
                    found=f"'{l_t}' {node.op} '{r_t}'",
                    help_msg=f"Operator '{node.op}' requires arithmetic operands (int or float)."
                )
            self.visit(node.left)
            self.visit(node.right)

        elif isinstance(node, (ConditionalExprNode, MatchExprNode)):
            self.infer_type(node)

    def infer_type(self, node: Optional[ASTNode]) -> str:
        if not node:
            return 'void'
        t = 'any'
        if isinstance(node, NumberNode):
            inferred = 'float' if isinstance(node.value, float) else 'int'
            node.inferred_type = inferred
            return inferred
        if isinstance(node, StringNode):
            node.inferred_type = 'string'
            return 'string'
        if isinstance(node, BooleanNode):
            node.inferred_type = 'bool'
            return 'bool'
        if isinstance(node, NullNode):
            node.inferred_type = 'null'
            return 'null'
        if isinstance(node, ArrayNode):
            if node.elements:
                inner = self.infer_type(node.elements[0])
                for element in node.elements[1:]:
                    self.infer_type(element)
                inferred = f'Array<{inner}>'
            else:
                inferred = 'Array<any>'
            node.inferred_type = inferred
            return inferred
        if isinstance(node, IndexAccessNode):
            collection_type = self.infer_type(node.obj)
            self.infer_type(node.index_expr)
            if collection_type.startswith('Array<') and collection_type.endswith('>'):
                inferred = collection_type[6:-1]
            elif collection_type == 'string':
                inferred = 'string'
            else:
                inferred = 'any'
            node.inferred_type = inferred
            return inferred
        if isinstance(node, IdentifierNode):
            t = self.lookup(node.name)
            if not t:
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.line, node.col,
                    "E2002", f"Undefined variable '{node.name}'",
                    expected="declared variable",
                    found=f"'{node.name}'",
                    help_msg=f"Variable '{node.name}' is referenced before declaration or outside its scope."
                )
            inferred = t if t else 'any'
            node.inferred_type = inferred
            return inferred
        if isinstance(node, BinaryOpNode):
            l_t = self.infer_type(node.left)
            r_t = self.infer_type(node.right)
            if node.op in ('==', '!=', '>', '<', '>=', '<=', 'and', 'or', '&&', '||'):
                inferred = 'bool'
            elif l_t == 'string' and r_t == 'string' and node.op == '+':
                inferred = 'string'
            elif l_t == 'float' or r_t == 'float':
                inferred = 'float'
            else:
                inferred = l_t if l_t != 'any' else r_t
            node.inferred_type = inferred
            return inferred
        if isinstance(node, AwaitNode):
            if not self.current_is_async:
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.line, node.col,
                    "E2010", "'await' is only valid inside an async function",
                    expected="async fn context",
                    found="synchronous context",
                    help_msg="Mark the containing function 'async' or remove 'await'.",
                )
            operand_type = self.infer_type(node.expr)
            if operand_type == 'any':
                node.inferred_type = 'any'
                return 'any'
            if not (operand_type.startswith('Task<') and operand_type.endswith('>')):
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.line, node.col,
                    "E2011", "'await' operand is not a Task",
                    expected="Task<T>",
                    found=operand_type,
                    help_msg="Await an async function call or another Task value.",
                )
            inferred = operand_type[5:-1]
            node.inferred_type = inferred
            return inferred
        if isinstance(node, ResultPropagateNode):
            operand_type = self.infer_type(node.expr)
            name, arguments = _generic_type_parts(operand_type)
            inferred = arguments[0] if name == "Result" and len(arguments) == 2 else "any"
            node.inferred_type = inferred
            return inferred
        if isinstance(node, ConditionalExprNode):
            self._require_bool_condition(node.condition, "if expression")
            branch_types = [self.infer_type(node.then_expr)]
            for condition, branch in node.elif_branches:
                self._require_bool_condition(condition, "elif expression")
                branch_types.append(self.infer_type(branch))
            branch_types.append(self.infer_type(node.else_expr))
            concrete = [value for value in branch_types if value != 'any']
            if not concrete:
                inferred = 'any'
            elif all(value == concrete[0] for value in concrete):
                inferred = concrete[0]
            elif all(value in ('int', 'float') for value in concrete):
                inferred = 'float'
            else:
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.line, node.col,
                    "E2001", "Conditional expression branches produce incompatible types",
                    expected=concrete[0],
                    found=", ".join(branch_types),
                    help_msg="Make every if/elif/else branch produce the same type.",
                )
                inferred = 'any'
            node.inferred_type = inferred
            return inferred
        if isinstance(node, MatchExprNode):
            subject_type = self.infer_type(node.expr)
            branch_types = []
            wildcard_indexes = []
            for index, (pattern, value) in enumerate(node.cases):
                is_wildcard = isinstance(pattern, IdentifierNode) and pattern.name == "_"
                if is_wildcard:
                    wildcard_indexes.append(index)
                elif isinstance(pattern, IdentifierNode):
                    DiagnosticEmitter.emit_error(
                        self.filepath, self.source, pattern.line, pattern.col,
                        "E2015", "Match expression identifiers are not binding patterns yet",
                        expected="literal pattern or _ fallback",
                        found=pattern.name,
                        help_msg="Use a literal arm now; Result/enum destructuring is a separate Maya feature.",
                    )
                else:
                    pattern_type = self.infer_type(pattern)
                    if not (
                        self.is_compatible(subject_type, pattern_type)
                        or self.is_compatible(pattern_type, subject_type)
                    ):
                        DiagnosticEmitter.emit_error(
                            self.filepath, self.source, pattern.line, pattern.col,
                            "E2001", "Match expression pattern type is incompatible with its subject",
                            expected=subject_type,
                            found=pattern_type,
                            help_msg="Use patterns with the same type as the matched value.",
                        )
                branch_types.append(self.infer_type(value))
            if wildcard_indexes != [len(node.cases) - 1]:
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.line, node.col,
                    "E2014", "Match expression must end with an exhaustive '_' fallback",
                    expected="_ => fallback as the final arm",
                    found="missing or non-final wildcard",
                    help_msg="A value-producing match must produce a value on every path.",
                )
            concrete = [value for value in branch_types if value != 'any']
            if not concrete:
                inferred = 'any'
            elif all(value == concrete[0] for value in concrete):
                inferred = concrete[0]
            elif all(value in ('int', 'float') for value in concrete):
                inferred = 'float'
            else:
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.line, node.col,
                    "E2001", "Match expression arms produce incompatible types",
                    expected=concrete[0],
                    found=", ".join(branch_types),
                    help_msg="Make every match arm produce the same type.",
                )
                inferred = 'any'
            node.inferred_type = inferred
            return inferred
        if isinstance(node, FunctionCallNode):
            collection_result = self._infer_collection_builtin(node)
            if collection_result is not None:
                node.inferred_type = collection_result
                return collection_result
            foreign_callable = self._foreign_callable(node)
            if foreign_callable is not None:
                inferred = foreign_callable.returns
            elif isinstance(node.callee, MemberAccessNode) and node.callee.member in ("len", "length", "size") and not node.args:
                receiver_type = self.infer_type(node.callee.obj)
                if receiver_type == "string" or receiver_type.startswith("Array") or receiver_type.startswith("Iterator"):
                    inferred = "int"
                else:
                    inferred = "any"
            elif node.callee in self.enum_variants:
                variant = self.enum_variants[node.callee]
                substitutions = {}
                for payload_type, argument in zip(variant["payload_types"], node.args):
                    _collect_type_substitutions(
                        payload_type,
                        self.infer_type(argument),
                        set(variant["generic_params"]),
                        substitutions,
                    )
                node.generic_substitutions = substitutions
                generic_params = variant["generic_params"]
                if generic_params:
                    arguments = ", ".join(substitutions.get(name, "any") for name in generic_params)
                    inferred = f'{variant["enum"]}<{arguments}>'
                else:
                    inferred = variant["enum"]
            elif node.callee in self.struct_defs:
                generic_params = self.struct_generic_params.get(node.callee, ())
                substitutions = dict(getattr(node, 'generic_substitutions', {}) or {})
                for (_name, field_type), argument in zip(
                    self.struct_defs[node.callee].items(), node.args,
                ):
                    _collect_type_substitutions(
                        field_type,
                        self.infer_type(argument),
                        set(generic_params),
                        substitutions,
                    )
                node.generic_substitutions = substitutions
                if generic_params:
                    arguments = ", ".join(substitutions.get(name, "any") for name in generic_params)
                    inferred = f"{node.callee}<{arguments}>"
                else:
                    inferred = node.callee
            elif node.callee in self.func_defs:
                definition = self.func_defs[node.callee]
                inferred = definition.get(
                    'public_ret',
                    definition['ret'],
                )
                generic_params = set(definition.get('generic_params') or ())
                if generic_params:
                    substitutions = dict(getattr(node, 'generic_substitutions', {}) or {})
                    for (_name, parameter_type), argument in zip(
                        definition['params'], node.args,
                    ):
                        _collect_type_substitutions(
                            parameter_type,
                            self.infer_type(argument),
                            generic_params,
                            substitutions,
                        )
                    node.generic_substitutions = substitutions
                    inferred = _substitute_type(inferred, substitutions)
            elif node.callee == "Ok" and node.args:
                inferred = f"Result<{self.infer_type(node.args[0])}, any>"
            elif node.callee == "Err" and node.args:
                inferred = f"Result<any, {self.infer_type(node.args[0])}>"
            elif node.callee in self.builtins:
                inferred = self.builtins[node.callee]
            else:
                inferred = 'any'
            node.inferred_type = inferred
            return inferred
        if isinstance(node, MemberAccessNode):
            obj_t = self.infer_type(node.obj)
            owner, arguments = _generic_type_parts(obj_t.rstrip('?'))
            if owner in self.struct_defs and node.member in self.struct_defs[owner]:
                substitutions = dict(zip(self.struct_generic_params.get(owner, ()), arguments))
                inferred = _substitute_type(self.struct_defs[owner][node.member], substitutions)
                node.inferred_type = inferred
                return inferred
            node.inferred_type = 'any'
            return 'any'
        node.inferred_type = 'any'
        return 'any'

    def _infer_lambda_with_types(self, node: LambdaNode, parameter_types: tuple[str, ...]) -> str:
        if len(node.params) != len(parameter_types):
            DiagnosticEmitter.emit_error(
                self.filepath, self.source, node.line, node.col,
                "E2042", "Collection callback has the wrong parameter count",
                expected=str(len(parameter_types)), found=str(len(node.params)),
                help_msg="Match the callback parameters required by map/filter/fold.",
            )
        self.enter_scope()
        try:
            for name, value_type in zip(node.params, parameter_types):
                self.declare(name, value_type)
            result = self.infer_type(node.body)
        finally:
            self.exit_scope()
        node.inferred_param_types = list(parameter_types)
        node.inferred_type = f"fn({', '.join(parameter_types)}) -> {result}"
        return result

    def _infer_collection_builtin(self, node: FunctionCallNode) -> Optional[str]:
        if not isinstance(node.callee, str) or node.callee not in ("map", "filter", "fold"):
            return None
        expected_count = 3 if node.callee == "fold" else 2
        if len(node.args) != expected_count:
            DiagnosticEmitter.emit_error(
                self.filepath, self.source, node.line, node.col,
                "E2041", f"'{node.callee}' has the wrong argument count",
                expected=str(expected_count), found=str(len(node.args)),
                help_msg="Use map(items, transform), filter(items, predicate), or fold(items, initial, reducer).",
            )
        collection_type = self.infer_type(node.args[0])
        collection_name, collection_arguments = _generic_type_parts(collection_type)
        if collection_name != "Array" or len(collection_arguments) != 1:
            DiagnosticEmitter.emit_error(
                self.filepath, self.source, node.args[0].line, node.args[0].col,
                "E2040", f"'{node.callee}' requires Array<T>",
                expected="Array<T>", found=collection_type,
                help_msg="Pass an array as the first argument.",
            )
        element_type = collection_arguments[0]
        callback_index = 2 if node.callee == "fold" else 1
        callback = node.args[callback_index]
        if not isinstance(callback, LambdaNode):
            DiagnosticEmitter.emit_error(
                self.filepath, self.source, callback.line, callback.col,
                "E2042", "Collection callback must be a lambda expression",
                expected="lambda", found=type(callback).__name__,
                help_msg="Use `item => expression` or `(acc, item) => expression`.",
            )
        if node.callee == "map":
            mapped_type = self._infer_lambda_with_types(callback, (element_type,))
            return f"Array<{mapped_type}>"
        if node.callee == "filter":
            predicate_type = self._infer_lambda_with_types(callback, (element_type,))
            if not self.is_compatible("bool", predicate_type):
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, callback.line, callback.col,
                    "E2043", "filter predicate must return bool",
                    expected="bool", found=predicate_type,
                )
            return collection_type
        accumulator_type = self.infer_type(node.args[1])
        reduced_type = self._infer_lambda_with_types(callback, (accumulator_type, element_type))
        if not self.is_compatible(accumulator_type, reduced_type):
            DiagnosticEmitter.emit_error(
                self.filepath, self.source, callback.line, callback.col,
                "E2044", "fold reducer must return the accumulator type",
                expected=accumulator_type, found=reduced_type,
            )
        return accumulator_type

    def _foreign_callable(self, node: FunctionCallNode) -> Optional[ForeignCallableBinding]:
        if not isinstance(node.callee, MemberAccessNode):
            return None
        receiver_type = self.infer_type(node.callee.obj)
        module = self.foreign_modules.get(receiver_type)
        if module is not None:
            binding = module.functions.get(node.callee.member)
            if binding is None:
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.line, node.col,
                    "E2030", f"Unknown foreign function '{node.callee.member}'",
                    note=f"The binding manifest for '{module.module}' does not declare this function.",
                    help_msg="Add an accurate entry to nyx.bindings.json or fix the function name.",
                )
            return binding
        methods = self.foreign_types.get(receiver_type)
        if methods is not None:
            binding = methods.get(node.callee.member)
            if binding is None:
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, node.line, node.col,
                    "E2030", f"Unknown foreign method '{node.callee.member}'",
                    note=f"The binding manifest for type '{receiver_type}' does not declare this method.",
                    help_msg="Add an accurate method entry to nyx.bindings.json or fix the method name.",
                )
            return binding
        return None

    def _check_foreign_arguments(
        self,
        node: FunctionCallNode,
        binding: ForeignCallableBinding,
    ) -> None:
        if len(node.args) != len(binding.params):
            DiagnosticEmitter.emit_error(
                self.filepath, self.source, node.line, node.col,
                "E2031", "Foreign call argument count mismatch",
                expected=f"{len(binding.params)} arguments",
                found=f"{len(node.args)} arguments",
                help_msg="Call the foreign API with the signature declared in its binding manifest.",
            )
        for index, (argument, expected) in enumerate(zip(node.args, binding.params), 1):
            actual = self.infer_type(argument)
            if not self.is_compatible(expected, actual):
                DiagnosticEmitter.emit_error(
                    self.filepath, self.source, argument.line, argument.col,
                    "E2032", f"Foreign argument {index} has the wrong type",
                    expected=expected,
                    found=actual,
                    help_msg="Match the argument type declared in the foreign binding manifest.",
                )

    def _declare_pattern_bindings(self, pattern: ASTNode, subject_type: str) -> None:
        if isinstance(pattern, IdentifierNode):
            if pattern.name != "_":
                self.declare(pattern.name, subject_type)
            return
        if isinstance(pattern, FunctionCallNode) and pattern.callee in ("Ok", "Err"):
            base, arguments = _generic_type_parts(subject_type)
            if base == "Result" and len(arguments) == 2:
                if len(pattern.args) != 1 or not isinstance(pattern.args[0], IdentifierNode):
                    DiagnosticEmitter.emit_error(
                        self.filepath, self.source, pattern.line, pattern.col,
                        "E2035", "Result pattern requires one payload binding",
                        expected="Ok(value) or Err(error)", found=str(len(pattern.args)),
                        help_msg="Bind one name, or use _ to ignore the payload.",
                    )
                argument = pattern.args[0]
                if argument.name != "_":
                    self.declare(argument.name, arguments[0 if pattern.callee == "Ok" else 1])
                return
        if not isinstance(pattern, FunctionCallNode) or pattern.callee not in self.enum_variants:
            return
        variant = self.enum_variants[pattern.callee]
        subject_base = subject_type.split("<", 1)[0]
        if subject_base != variant["enum"]:
            DiagnosticEmitter.emit_error(
                self.filepath, self.source, pattern.line, pattern.col,
                "E2034", f"Variant '{pattern.callee}' does not belong to matched type '{subject_type}'",
                expected=variant["enum"], found=subject_type,
                help_msg="Use a variant constructor from the enum being matched.",
            )
        generic_values = []
        if "<" in subject_type and subject_type.endswith(">"):
            generic_values = [item.strip() for item in subject_type.split("<", 1)[1][:-1].split(",")]
        substitutions = {
            name: generic_values[index]
            for index, name in enumerate(variant["generic_params"])
            if index < len(generic_values)
        }
        if len(pattern.args) != len(variant["payload_types"]):
            DiagnosticEmitter.emit_error(
                self.filepath, self.source, pattern.line, pattern.col,
                "E2035", f"Variant pattern '{pattern.callee}' has the wrong payload count",
                expected=str(len(variant["payload_types"])), found=str(len(pattern.args)),
                help_msg="Bind every payload declared by the enum variant.",
            )
        for argument, payload_type in zip(pattern.args, variant["payload_types"]):
            if isinstance(argument, IdentifierNode) and argument.name != "_":
                self.declare(argument.name, substitutions.get(payload_type, payload_type))
