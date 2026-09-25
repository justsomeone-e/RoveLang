"""Rust 2021 source emission from canonical verified Rove HIR.

The Rust backend deliberately consumes only HIR.  It therefore observes the
same optimized value flow, symbol identities, numeric rules, and structured
backend rejection path as the stable hosted emitters.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import fields, is_dataclass
import math
import re
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from src.codegen.hir_cpp import ModuleTypeInference
from src.ir import (
    ANY,
    BOOL,
    FLOAT,
    INT,
    STRING,
    VOID,
    IRArray,
    IRAssert,
    IRAssign,
    IRAwait,
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
    IRResultPropagate,
    IRReturn,
    IRSpawn,
    IRStatement,
    IRStruct,
    IRTestBlock,
    IRThrow,
    IRTrait,
    IRTryCatch,
    IRType,
    IRTypeAlias,
    IRUnary,
    IRUnsafeBlock,
    IRVarDecl,
    IRWhile,
    verify_hir,
)


class RustEmissionError(ValueError):
    """Raised when verified HIR cannot be represented by the Rust contract."""


_RUST_RUNTIME = r'''
use std::fmt::Debug;
use std::io::{self, Write};
use std::sync::{Arc, LazyLock, Mutex};
use std::sync::mpsc::{self, Receiver, Sender};
use std::time::Duration;

trait RoveDisplay {
    fn rove_display(&self) -> String;
}

fn _rove_display<T: RoveDisplay + ?Sized>(value: &T) -> String {
    value.rove_display()
}

fn _rove_f64_to_string(value: f64) -> String {
    if value.is_nan() { return "nan".to_string(); }
    if value == f64::INFINITY { return "inf".to_string(); }
    if value == f64::NEG_INFINITY { return "-inf".to_string(); }
    if value == 0.0 { return "0".to_string(); }
    let magnitude = value.abs();
    if magnitude < 0.000001 || magnitude >= 1.0e21 {
        return format!("{:e}", value);
    }
    value.to_string()
}

impl RoveDisplay for i64 { fn rove_display(&self) -> String { self.to_string() } }
impl RoveDisplay for usize { fn rove_display(&self) -> String { self.to_string() } }
impl RoveDisplay for f64 { fn rove_display(&self) -> String { _rove_f64_to_string(*self) } }
impl RoveDisplay for bool {
    fn rove_display(&self) -> String {
        if *self { "true".to_string() } else { "false".to_string() }
    }
}
impl RoveDisplay for String { fn rove_display(&self) -> String { self.clone() } }
impl RoveDisplay for str { fn rove_display(&self) -> String { self.to_string() } }
impl RoveDisplay for () { fn rove_display(&self) -> String { String::new() } }
impl<T: RoveDisplay> RoveDisplay for Vec<T> {
    fn rove_display(&self) -> String {
        let values: Vec<String> = self.iter().map(RoveDisplay::rove_display).collect();
        format!("[{}]", values.join(", "))
    }
}
impl<T: RoveDisplay> RoveDisplay for Option<T> {
    fn rove_display(&self) -> String {
        match self {
            Some(value) => value.rove_display(),
            None => "null".to_string(),
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
enum RoveValue {
    Null,
    Int(i64),
    Float(f64),
    Bool(bool),
    String(String),
    Array(Vec<RoveValue>),
    Opaque(String),
}

impl RoveDisplay for RoveValue {
    fn rove_display(&self) -> String {
        match self {
            Self::Null => "null".to_string(),
            Self::Int(value) => value.rove_display(),
            Self::Float(value) => value.rove_display(),
            Self::Bool(value) => value.rove_display(),
            Self::String(value) => value.clone(),
            Self::Array(value) => value.rove_display(),
            Self::Opaque(value) => value.clone(),
        }
    }
}

fn _rove_expect_i64(value: RoveValue) -> i64 {
    match value {
        RoveValue::Int(value) => value,
        _ => panic!("Rove value must have type int"),
    }
}
fn _rove_expect_f64(value: RoveValue) -> f64 {
    match value {
        RoveValue::Float(value) => value,
        RoveValue::Int(value) => value as f64,
        _ => panic!("Rove value must have type float"),
    }
}
fn _rove_expect_bool(value: RoveValue) -> bool {
    match value {
        RoveValue::Bool(value) => value,
        _ => panic!("Rove condition must have type bool"),
    }
}
fn _rove_expect_string(value: RoveValue) -> String {
    match value {
        RoveValue::String(value) => value,
        _ => panic!("Rove value must have type string"),
    }
}

#[derive(Clone, Debug, PartialEq)]
enum RoveResult<T, E> {
    Ok(T),
    Err(E),
}

impl<T, E> RoveResult<T, E> {
    fn is_ok(&self) -> bool { matches!(self, Self::Ok(_)) }
    fn is_err(&self) -> bool { matches!(self, Self::Err(_)) }
    fn unwrap(self) -> T {
        match self {
            Self::Ok(value) => value,
            Self::Err(_) => panic!("called unwrap on Rove Err value"),
        }
    }
}

impl<T: RoveDisplay, E: RoveDisplay> RoveDisplay for RoveResult<T, E> {
    fn rove_display(&self) -> String {
        match self {
            Self::Ok(value) => format!("Ok({})", value.rove_display()),
            Self::Err(value) => format!("Err({})", value.rove_display()),
        }
    }
}

fn _rove_print(values: &[String]) {
    println!("{}", values.join(" "));
}

fn _rove_input(prompt: Option<&String>) -> String {
    if let Some(value) = prompt {
        print!("{}", value);
        let _ = io::stdout().flush();
    }
    let mut value = String::new();
    if io::stdin().read_line(&mut value).is_err() { return String::new(); }
    while value.ends_with('\n') || value.ends_with('\r') { value.pop(); }
    value
}

fn _rove_to_int(value: &String) -> i64 {
    let bytes = value.as_bytes();
    let mut cursor = 0usize;
    while cursor < bytes.len() && bytes[cursor].is_ascii_whitespace() { cursor += 1; }
    let mut negative = false;
    if cursor < bytes.len() && (bytes[cursor] == b'+' || bytes[cursor] == b'-') {
        negative = bytes[cursor] == b'-';
        cursor += 1;
    }
    let start = cursor;
    let mut result = 0u64;
    while cursor < bytes.len() && bytes[cursor].is_ascii_digit() {
        result = result.wrapping_mul(10).wrapping_add((bytes[cursor] - b'0') as u64);
        cursor += 1;
    }
    if cursor == start { return 0; }
    while cursor < bytes.len() && bytes[cursor].is_ascii_whitespace() { cursor += 1; }
    if cursor != bytes.len() { return 0; }
    if negative { 0u64.wrapping_sub(result) as i64 } else { result as i64 }
}

fn _rove_contains(value: &String, part: &String) -> bool { value.contains(part) }
fn _rove_is_number(value: &String) -> bool { value.trim().parse::<f64>().is_ok() }

trait RoveLength { fn rove_len(&self) -> i64; }
impl<T> RoveLength for Vec<T> { fn rove_len(&self) -> i64 { self.len() as i64 } }
impl RoveLength for String { fn rove_len(&self) -> i64 { self.len() as i64 } }
fn _rove_len<T: RoveLength + ?Sized>(value: &T) -> i64 { value.rove_len() }

fn _rove_string_index(value: &String, index: i64) -> String {
    if index < 0 { return String::new(); }
    value.as_bytes().get(index as usize)
        .map(|byte| String::from_utf8_lossy(&[*byte]).into_owned())
        .unwrap_or_default()
}

fn _rove_str_trim(s: String) -> String { s.trim().to_string() }
fn _rove_str_starts_with(s: String, prefix: String) -> bool { s.starts_with(&prefix) }
fn _rove_str_ends_with(s: String, suffix: String) -> bool { s.ends_with(&suffix) }
fn _rove_str_find_result(s: String, sub: String) -> RoveResult<i64, String> {
    match s.find(&sub) {
        Some(idx) => RoveResult::Ok(idx as i64),
        None => RoveResult::Err("substring not found".to_string()),
    }
}
fn _rove_str_to_upper(s: String) -> String { s.to_uppercase() }
fn _rove_str_to_lower(s: String) -> String { s.to_lowercase() }
fn _rove_str_replace(s: String, from_str: String, to_str: String) -> String {
    if from_str.is_empty() { return s; }
    s.replace(&from_str, &to_str)
}

fn _rove_i64_div(left: i64, right: i64) -> i64 {
    if right == 0 { panic!("integer division by zero"); }
    if left == i64::MIN && right == -1 { i64::MIN } else { left / right }
}
fn _rove_i64_mod(left: i64, right: i64) -> i64 {
    if right == 0 { panic!("integer division by zero"); }
    if left == i64::MIN && right == -1 { 0 } else { left % right }
}

unsafe fn _rove_peek(address: usize) -> i64 { *(address as *const i64) }
unsafe fn _rove_memdump(address: usize, length: i64) {
    let count = if length < 0 { 0usize } else { length as usize };
    for offset in (0..count).step_by(16) {
        print!("0x{:016X}: ", address.wrapping_add(offset));
        for index in offset..usize::min(offset + 16, count) {
            print!("{:02X} ", *((address + index) as *const u8));
        }
        println!();
    }
}
fn _rove_delay_ms(milliseconds: i64) {
    std::thread::sleep(Duration::from_millis(milliseconds.max(0) as u64));
}

#[derive(Clone, Debug)]
struct RoveChannel {
    sender: Sender<RoveValue>,
    receiver: Arc<Mutex<Receiver<RoveValue>>>,
}
impl PartialEq for RoveChannel {
    fn eq(&self, other: &Self) -> bool { Arc::ptr_eq(&self.receiver, &other.receiver) }
}
impl RoveDisplay for RoveChannel {
    fn rove_display(&self) -> String { "Channel".to_string() }
}
impl RoveChannel {
    fn send(&self, value: RoveValue) { let _ = self.sender.send(value); }
    fn receive(&self) -> RoveValue {
        self.receiver.lock().unwrap().recv().unwrap_or(RoveValue::Null)
    }
}
fn _rove_channel() -> RoveChannel {
    let (sender, receiver) = mpsc::channel();
    RoveChannel { sender, receiver: Arc::new(Mutex::new(receiver)) }
}
'''.strip()


_RUST_KEYWORDS = frozenset(
    "as break const continue crate else enum extern false fn for if impl in let loop "
    "match mod move mut pub ref return self Self static struct super trait true type "
    "unsafe use where while async await dyn abstract become box do final macro override "
    "priv typeof unsized virtual yield try union".split()
)


def _strip_optional(value_type: IRType) -> IRType:
    return value_type.with_optional(False) if value_type.optional else value_type


def _is_dynamic(value_type: IRType) -> bool:
    return value_type.is_unknown or any(_is_dynamic(item) for item in value_type.arguments)


class _RustTypeInference(ModuleTypeInference):
    def __init__(self, module: IRModule):
        super().__init__(module)

        def repair(value: object) -> None:
            if isinstance(value, IRVarDecl) and isinstance(value.expr, IRCall):
                if value.expr.callee == "peek":
                    self.symbol_types[value.symbol] = INT
            if isinstance(value, tuple):
                for item in value:
                    repair(item)
            elif is_dataclass(value):
                for field in fields(value):
                    repair(getattr(value, field.name))

        repair(module.items)

    def expression_type(self, node: IRExpr) -> IRType:
        if isinstance(node, IRCall) and node.callee == "peek":
            return INT
        return super().expression_type(node)


class HIRRustEmitter:
    """Emit a standalone Rust 2021 translation unit from typed HIR."""

    def __init__(self, module: IRModule):
        self.module = module
        self.inference = _RustTypeInference(module)
        self.symbol_names: Dict[str, str] = {}
        self.used_names: Set[str] = set()
        self.impls: Dict[str, List[IRImpl]] = defaultdict(list)
        self.globals: Dict[str, IRVarDecl] = {
            item.symbol: item for item in module.items if isinstance(item, IRVarDecl)
        }
        self.externs: Dict[str, IRExternFunction] = {
            item.symbol: item for item in module.items if isinstance(item, IRExternFunction)
        }
        self.declared_types: Set[str] = {
            item.name
            for item in module.items
            if isinstance(item, (IRStruct, IREnum, IRTypeAlias, IRTrait))
        }
        for item in module.items:
            if isinstance(item, (IRStruct, IRFunction)):
                self.declared_types.update(item.generic_params)
        self.current_return_type = VOID
        self.active_defers: Tuple[IRExpr, ...] = ()
        self.temporary_index = 0
        self._register_declarations()

    def emit(self) -> str:
        verify_hir(self.module)
        native_lines = self._emit_native_directives()
        declarations: List[str] = []

        for item in self.module.items:
            if isinstance(item, IRTypeAlias):
                declarations.extend(self._emit_type_alias(item))
            elif isinstance(item, IREnum):
                declarations.extend(self._emit_enum(item))
            elif isinstance(item, IRTrait):
                declarations.extend(self._emit_trait(item))
            elif isinstance(item, IRStruct):
                declarations.extend(self._emit_struct(item))

        for target_name in sorted(self.impls):
            for implementation in self.impls[target_name]:
                declarations.extend(self._emit_impl(implementation))

        for item in self.module.items:
            if isinstance(item, IRExternFunction):
                declarations.extend(self._emit_extern(item))
            elif isinstance(item, IRFunction):
                declarations.extend(self._emit_function(item))

        for item in self.module.items:
            if isinstance(item, IRVarDecl):
                declarations.extend(self._emit_global(item))

        main_lines = ["fn main() {"]
        for item in self.module.items:
            if isinstance(item, IRVarDecl):
                main_lines.append(f"    let _ = &*{self._symbol(item.symbol, item.name)};")

        top_level = [
            item for item in self.module.items
            if isinstance(item, IRStatement) and not isinstance(item, IRVarDecl)
        ]
        main_lines.extend(self._emit_block(top_level, 1, (), 0))
        user_main = next(
            (item for item in self.module.items if isinstance(item, IRFunction) and item.name == "main"),
            None,
        )
        if user_main is not None:
            main_lines.append(f"    {self._symbol(user_main.symbol, user_main.name)}();")
        main_lines.append("}")

        sections = [
            "// Auto-generated by Rove (rust)",
            "// Target: Rust 2021 Edition (canonical typed HIR v1)",
            "#![allow(dead_code, unused_imports, unused_mut, unused_variables, non_snake_case, non_upper_case_globals, unused_parens)]",
            "",
            _RUST_RUNTIME,
        ]
        if native_lines:
            sections.extend(("", "\n".join(native_lines)))
        if declarations:
            sections.extend(("", "\n".join(declarations).rstrip()))
        sections.extend(("", "\n".join(main_lines)))
        return "\n".join(sections).rstrip() + "\n"

    def _register_declarations(self) -> None:
        for item in self.module.items:
            if isinstance(item, IRImpl):
                self.impls[item.target_type].append(item)
            elif isinstance(item, (IRFunction, IRStruct, IRTrait, IRTypeAlias, IREnum, IRExternFunction, IRVarDecl)):
                if isinstance(item, IRVarDecl):
                    preferred = f"_rove_global_{item.name}"
                else:
                    preferred = "_rove_user_main" if isinstance(item, IRFunction) and item.name == "main" else item.name
                self._reserve_symbol(item.symbol, preferred)
            if isinstance(item, IRFunction):
                for parameter in item.params:
                    self._reserve_symbol(parameter.symbol, parameter.name)
            elif isinstance(item, IRImpl):
                for method in item.methods:
                    for parameter in method.params:
                        if parameter.name in ("self", "this"):
                            self.symbol_names[parameter.symbol] = "self"
                        else:
                            self._reserve_symbol(parameter.symbol, parameter.name)

    def _emit_native_directives(self) -> List[str]:
        lines = []
        for item in self.module.items:
            if not isinstance(item, IRNativeDirective):
                continue
            if item.kind == "use":
                lines.append(f"use {item.value};")
            elif item.kind == "raw":
                lines.append(item.value)
            elif item.kind in ("crate", "extern_crate"):
                lines.append(f"extern crate {item.value};")
            elif item.kind in ("include", "link"):
                raise RustEmissionError(
                    f"Rust target cannot consume C/C++ native directive '{item.kind}'; use #native use/raw"
                )
            else:
                raise RustEmissionError(f"Unknown native directive kind '{item.kind}'")
        return lines

    def _emit_type_alias(self, node: IRTypeAlias) -> List[str]:
        return [
            f"pub type {self._symbol(node.symbol, node.name)} = "
            f"{self._rust_type(node.actual_type)};"
        ]

    def _emit_enum(self, node: IREnum) -> List[str]:
        name = self._symbol(node.symbol, node.name)
        lines = ["#[derive(Clone, Copy, Debug, PartialEq, Eq)]", "#[repr(i64)]", f"pub enum {name} {{"]
        for member in node.members:
            suffix = "" if member.value is None else f" = {self._expr_as(member.value, INT)}"
            lines.append(f"    {self._identifier(member.name)}{suffix},")
        lines.extend(("}", f"impl RoveDisplay for {name} {{", "    fn rove_display(&self) -> String { (*self as i64).to_string() }", "}"))
        return lines

    def _emit_trait(self, node: IRTrait) -> List[str]:
        name = self._symbol(node.symbol, node.name)
        lines = [f"pub trait {name} {{"]
        for method in node.methods:
            lines.append("    " + self._method_signature(method, declaration=True) + ";")
        lines.append("}")
        return lines

    def _emit_struct(self, node: IRStruct) -> List[str]:
        name = self._symbol(node.symbol, node.name)
        generics = self._generic_declaration(node.generic_params)
        generic_use = self._generic_use(node.generic_params)
        lines = ["#[derive(Clone, Debug, PartialEq)]", f"pub struct {name}{generics} {{"]
        field_types: List[Tuple[IRParameter, IRType]] = []
        for field in node.fields:
            value_type = self.inference.field_type(node.name, field.name, field.type)
            field_types.append((field, value_type))
            lines.append(f"    pub {self._identifier(field.name)}: {self._rust_type(value_type)},")
        lines.append("}")

        impl_generics = self._generic_declaration(node.generic_params)
        lines.append(f"impl{impl_generics} RoveDisplay for {name}{generic_use} {{")
        lines.append("    fn rove_display(&self) -> String {")
        if node.fields:
            rendered = ", ".join(
                f'format!("{field.name}: {{}}", self.{self._identifier(field.name)}.rove_display())'
                for field, _ in field_types
            )
            lines.append(f"        format!(\"{name} {{{{ {{}} }}}}\", [{rendered}].join(\", \"))")
        else:
            lines.append(f'        "{name} {{}}".to_string()')
        lines.append("    }")
        lines.append("}")

        parameters = []
        initializers = []
        for field, value_type in field_types:
            parameter_name = f"_rove_{self._identifier(field.name)}"
            parameters.append(f"{parameter_name}: {self._rust_type(value_type)}")
            initializers.append(f"{self._identifier(field.name)}: {parameter_name}")
        lines.append("#[allow(non_snake_case)]")
        lines.append(
            f"pub fn {name}{generics}({', '.join(parameters)}) -> {name}{generic_use} {{"
        )
        lines.append(f"    {name} {{ {', '.join(initializers)} }}")
        lines.append("}")
        return lines

    def _emit_impl(self, node: IRImpl) -> List[str]:
        target = self._identifier(node.target_type)
        trait = f"{self._identifier(node.trait_name)} for " if node.trait_name else ""
        lines = [f"impl {trait}{target} {{"]
        for method in node.methods:
            lines.extend(self._emit_method(method, 1, public=node.trait_name is None))
        lines.append("}")
        return lines

    def _method_signature(self, node: IRFunction, *, declaration: bool = False) -> str:
        parameters = []
        for index, parameter in enumerate(node.params):
            if index == 0 and parameter.name in ("self", "this"):
                receiver = "&mut self" if self._method_mutates_self(node) else "&self"
                parameters.append(receiver)
                self.symbol_names[parameter.symbol] = "self"
                continue
            value_type = self.inference.type_of_symbol(parameter.symbol, parameter.type)
            mutable = "mut " if not declaration and self._symbol_assigned(node.body, parameter.symbol) else ""
            parameters.append(
                f"{mutable}{self._parameter_name(parameter)}: {self._rust_type(value_type)}"
            )
        return_type = self.inference.return_type(node)
        if node.is_async:
            raise RustEmissionError("Rust backend does not support Rove Task<T> yet")
        suffix = "" if return_type == VOID else f" -> {self._rust_type(return_type)}"
        return f"fn {self._identifier(node.name)}({', '.join(parameters)}){suffix}"

    def _emit_method(self, node: IRFunction, indent: int, *, public: bool) -> List[str]:
        prefix = "    " * indent
        visibility = "pub " if public else ""
        lines = [prefix + visibility + self._method_signature(node) + " {"]
        previous = self.current_return_type
        self.current_return_type = self.inference.return_type(node)
        try:
            lines.extend(self._emit_block(node.body, indent + 1, (), 0))
        finally:
            self.current_return_type = previous
        lines.append(prefix + "}")
        return lines

    def _emit_extern(self, node: IRExternFunction) -> List[str]:
        abi = "C" if node.abi.lower() in ("c", "extern_c") else node.abi
        params = []
        for parameter in node.params:
            value_type = self.inference.type_of_symbol(parameter.symbol, parameter.type)
            if value_type.name in ("string", "Array", "any") or value_type.optional:
                raise RustEmissionError(
                    f"extern function '{node.name}' parameter '{parameter.name}' needs an explicit scalar/pointer ABI type"
                )
            params.append(f"{self._parameter_name(parameter)}: {self._ffi_type(value_type)}")
        if node.varargs:
            params.append("...")
        result = "" if node.return_type == VOID else f" -> {self._ffi_type(node.return_type)}"
        return [
            f"unsafe extern \"{abi}\" {{",
            f"    pub fn {self._symbol(node.symbol, node.name)}({', '.join(params)}){result};",
            "}",
        ]

    def _emit_function(self, node: IRFunction) -> List[str]:
        if node.is_async:
            raise RustEmissionError("Rust backend does not support Rove Task<T> yet")
        params = []
        for parameter in node.params:
            value_type = self.inference.type_of_symbol(parameter.symbol, parameter.type)
            mutable = "mut " if self._symbol_assigned(node.body, parameter.symbol) else ""
            params.append(f"{mutable}{self._parameter_name(parameter)}: {self._rust_type(value_type)}")
        return_type = self.inference.return_type(node)
        suffix = "" if return_type == VOID else f" -> {self._rust_type(return_type)}"
        lines = [
            f"pub fn {self._symbol(node.symbol, node.name)}{self._generic_declaration(node.generic_params)}"
            f"({', '.join(params)}){suffix} {{"
        ]
        previous = self.current_return_type
        self.current_return_type = return_type
        try:
            lines.extend(self._emit_block(node.body, 1, (), 0))
        finally:
            self.current_return_type = previous
        lines.append("}")
        return lines

    def _emit_global(self, node: IRVarDecl) -> List[str]:
        value_type = self.inference.type_of_symbol(node.symbol, node.type)
        name = self._symbol(node.symbol, node.name)
        value = self._expr_as(node.expr, value_type)
        return [
            f"static {name}: LazyLock<Mutex<{self._rust_type(value_type)}>> =",
            f"    LazyLock::new(|| Mutex::new({value}));",
        ]

    def _emit_block(
        self,
        statements: Sequence[IRStatement],
        indent: int,
        inherited_defers: Tuple[IRExpr, ...],
        loop_defer_base: int,
    ) -> List[str]:
        lines: List[str] = []
        local_defers: List[IRExpr] = []
        for statement in statements:
            if isinstance(statement, IRDefer):
                local_defers.append(statement.expr)
                continue
            active = inherited_defers + tuple(local_defers)
            previous_defers = self.active_defers
            self.active_defers = active
            try:
                lines.extend(self._emit_statement(statement, indent, active, loop_defer_base))
            finally:
                self.active_defers = previous_defers
        prefix = "    " * indent
        for expression in reversed(local_defers):
            lines.append(f"{prefix}{self._expr(expression)};")
        return lines

    def _emit_statement(
        self,
        node: IRStatement,
        indent: int,
        active_defers: Tuple[IRExpr, ...],
        loop_defer_base: int,
    ) -> List[str]:
        prefix = "    " * indent
        if isinstance(node, IRVarDecl):
            value_type = self.inference.type_of_symbol(node.symbol, node.type)
            name = self._symbol(node.symbol, node.name)
            mutable = "" if node.is_const else "mut "
            return [
                f"{prefix}let {mutable}{name}: {self._rust_type(value_type)} = "
                f"{self._expr_as(node.expr, value_type)};"
            ]
        if isinstance(node, IRAssign):
            return self._emit_assignment(node, indent)
        if isinstance(node, IRExprStatement):
            return [f"{prefix}{self._expr(node.expr)};"]
        if isinstance(node, IRReturn):
            lines = [f"{prefix}{self._expr(expression)};" for expression in reversed(active_defers)]
            if node.expr is None:
                lines.append(f"{prefix}return;")
            else:
                lines.append(f"{prefix}return {self._expr_as(node.expr, self.current_return_type)};")
            return lines
        if isinstance(node, IRThrow):
            raise RustEmissionError("Rust backend does not support Rove exception semantics yet")
        if isinstance(node, IRIf):
            lines = [f"{prefix}if {self._condition(node.condition)} {{"]
            lines.extend(self._emit_block(node.then_branch, indent + 1, active_defers, loop_defer_base))
            for condition, body in node.elif_branches:
                lines.append(f"{prefix}}} else if {self._condition(condition)} {{")
                lines.extend(self._emit_block(body, indent + 1, active_defers, loop_defer_base))
            if node.else_branch is not None:
                lines.append(f"{prefix}}} else {{")
                lines.extend(self._emit_block(node.else_branch, indent + 1, active_defers, loop_defer_base))
            lines.append(f"{prefix}}}")
            return lines
        if isinstance(node, IRWhile):
            lines = [f"{prefix}while {self._condition(node.condition)} {{"]
            lines.extend(self._emit_block(node.body, indent + 1, active_defers, len(active_defers)))
            lines.append(f"{prefix}}}")
            return lines
        if isinstance(node, IRFor):
            variable = self._symbol(node.symbol, node.var_name)
            if node.collection_expr is not None:
                iterator = f"({self._expr(node.collection_expr)}).into_iter()"
            else:
                iterator = (
                    f"{self._expr_as(node.start_expr, INT)}..="
                    f"{self._expr_as(node.end_expr, INT)}"
                )
            lines = [f"{prefix}for mut {variable} in {iterator} {{"]
            lines.extend(self._emit_block(node.body, indent + 1, active_defers, len(active_defers)))
            lines.append(f"{prefix}}}")
            return lines
        if isinstance(node, IRBreak):
            lines = [f"{prefix}{self._expr(item)};" for item in reversed(active_defers[loop_defer_base:])]
            lines.append(f"{prefix}break;")
            return lines
        if isinstance(node, IRContinue):
            lines = [f"{prefix}{self._expr(item)};" for item in reversed(active_defers[loop_defer_base:])]
            lines.append(f"{prefix}continue;")
            return lines
        if isinstance(node, IRGuard):
            lines = [f"{prefix}if !({self._condition(node.condition)}) {{"]
            lines.extend(self._emit_block(node.else_body, indent + 1, active_defers, loop_defer_base))
            lines.append(f"{prefix}}}")
            return lines
        if isinstance(node, IRUnsafeBlock):
            lines = [f"{prefix}unsafe {{"]
            lines.extend(self._emit_block(node.body, indent + 1, active_defers, loop_defer_base))
            lines.append(f"{prefix}}}")
            return lines
        if isinstance(node, IRSpawn):
            lines = [f"{prefix}let _rove_spawn_handle = std::thread::spawn(move || {{"]
            lines.extend(self._emit_block(node.body, indent + 1, active_defers, loop_defer_base))
            lines.append(f"{prefix}}});")
            return lines
        if isinstance(node, IRAssert):
            message = self._string_literal(node.message or "Rove assertion failed")
            return [f"{prefix}assert!({self._condition(node.condition)}, {message});"]
        if isinstance(node, IRMatch):
            return self._emit_match(node, indent, active_defers, loop_defer_base)
        if isinstance(node, IRTryCatch):
            raise RustEmissionError("Rust backend does not support Rove exception semantics yet")
        if isinstance(node, IRTestBlock):
            lines = [f"{prefix}{{ // Rove test: {node.description}"]
            lines.extend(self._emit_block(node.body, indent + 1, active_defers, loop_defer_base))
            lines.append(f"{prefix}}}")
            return lines
        raise RustEmissionError(f"Unsupported Rust HIR statement: {type(node).__name__}")

    def _emit_assignment(self, node: IRAssign, indent: int) -> List[str]:
        prefix = "    " * indent
        target_type = self.inference.expression_type(node.target)
        value = self._expr_as(node.expr, target_type)
        if isinstance(node.target, IRReference) and node.target.symbol in self.globals:
            name = self._symbol(node.target.symbol, node.target.name)
            value_name = self._temporary("value")
            return [
                f"{prefix}let {value_name}: {self._rust_type(target_type)} = {value};",
                f"{prefix}*{name}.lock().unwrap() = {value_name};",
            ]
        root = self._root_reference(node.target)
        if root is not None and root.symbol in self.globals:
            guard = self._temporary("global")
            value_name = self._temporary("value")
            global_name = self._symbol(root.symbol, root.name)
            target = self._lvalue(node.target, global_guard=(root.symbol, guard))
            return [
                f"{prefix}let {value_name}: {self._rust_type(target_type)} = {value};",
                f"{prefix}{{",
                f"{prefix}    let mut {guard} = {global_name}.lock().unwrap();",
                f"{prefix}    {target} = {value_name};",
                f"{prefix}}}",
            ]
        return [f"{prefix}{self._lvalue(node.target)} = {value};"]

    def _emit_match(
        self,
        node: IRMatch,
        indent: int,
        active_defers: Tuple[IRExpr, ...],
        loop_defer_base: int,
    ) -> List[str]:
        prefix = "    " * indent
        temporary = self._temporary("match")
        lines = [f"{prefix}let {temporary} = {self._expr(node.expr)};"]
        opened = False
        for case in node.cases:
            pattern = case.pattern
            wildcard = (
                isinstance(pattern, IRLiteral) and pattern.value == "_"
            ) or (
                isinstance(pattern, IRReference) and pattern.name == "_"
            )
            if wildcard:
                lines.append(f"{prefix}{'else ' if opened else ''}{{")
            elif isinstance(pattern, IRCall) and pattern.callee in ("Ok", "Err"):
                variant = pattern.callee
                binding = self._temporary("match_value")
                if pattern.args and isinstance(pattern.args[0], IRReference):
                    binding = self._symbol(pattern.args[0].symbol, pattern.args[0].name)
                keyword = "else if" if opened else "if"
                lines.append(
                    f"{prefix}{keyword} let RoveResult::{variant}({binding}) = {temporary}.clone() {{"
                )
            elif isinstance(pattern, IRCall) and pattern.callee == "Some":
                binding = self._temporary("match_value")
                if pattern.args and isinstance(pattern.args[0], IRReference):
                    binding = self._symbol(pattern.args[0].symbol, pattern.args[0].name)
                keyword = "else if" if opened else "if"
                lines.append(
                    f"{prefix}{keyword} let Some({binding}) = {temporary}.clone() {{"
                )
            elif (isinstance(pattern, IRLiteral) and pattern.value is None) or (isinstance(pattern, IRReference) and pattern.name in ("None", "null")):
                keyword = "else if" if opened else "if"
                lines.append(f"{prefix}{keyword} {temporary}.is_none() {{")
            elif isinstance(pattern, IRCall):
                variant = self._identifier(pattern.callee)
                bindings = []
                for index, arg in enumerate(pattern.args):
                    if isinstance(arg, IRReference):
                        bindings.append(self._symbol(arg.symbol, arg.name))
                    else:
                        bindings.append(self._temporary(f"arg_{index}"))
                binding_str = f"({', '.join(bindings)})" if bindings else ""
                keyword = "else if" if opened else "if"
                lines.append(
                    f"{prefix}{keyword} let {variant}{binding_str} = {temporary}.clone() {{"
                )
            else:
                keyword = "else if" if opened else "if"
                lines.append(f"{prefix}{keyword} {temporary} == {self._expr(pattern)} {{")
            lines.extend(self._emit_block(case.body, indent + 1, active_defers, loop_defer_base))
            lines.append(f"{prefix}}}")
            opened = True
            if wildcard:
                break
        return lines

    def _condition(self, node: IRExpr) -> str:
        if node.type.is_unknown:
            return f"_rove_expect_bool({self._expr_as(node, ANY)})"
        return self._expr(node)

    def _expr(self, node: Optional[IRExpr], expected: Optional[IRType] = None) -> str:
        if node is None:
            return "()"
        if isinstance(node, IRLiteral):
            if node.value is None:
                return "None"
            if isinstance(node.value, bool):
                return "true" if node.value else "false"
            if isinstance(node.value, int):
                if node.value == -(1 << 63):
                    return "i64::MIN"
                return f"{node.value}_i64"
            if isinstance(node.value, float):
                if math.isnan(node.value):
                    return "f64::NAN"
                if math.isinf(node.value):
                    return "f64::INFINITY" if node.value > 0 else "f64::NEG_INFINITY"
                if node.value == 0.0 and math.copysign(1.0, node.value) < 0:
                    return "-0.0_f64"
                rendered = repr(node.value)
                if "." not in rendered and "e" not in rendered.lower():
                    rendered += ".0"
                return f"{rendered}_f64"
            if isinstance(node.value, str):
                return f"{self._string_literal(node.value)}.to_string()"
            raise RustEmissionError(f"Unsupported literal value {node.value!r}")
        if isinstance(node, IRReference):
            value_type = self.inference.type_of_symbol(node.symbol, node.type)
            if node.symbol in self.globals:
                name = self._symbol(node.symbol, node.name)
                val = self._temporary("val")
                return f"{{ let {val} = {name}.lock().unwrap().clone(); {val} }}"
            name = self._symbol(node.symbol, node.name)
            return name if self._is_copy_type(value_type) else f"{name}.clone()"
        if isinstance(node, IRBinary):
            return self._emit_binary(node)
        if isinstance(node, IRUnary):
            operand_type = self.inference.expression_type(node.expr)
            operand = self._expr(node.expr)
            if node.op in ("!", "not"):
                return f"!({self._condition(node.expr)})"
            if node.op == "+":
                return operand
            if node.op == "-" and operand_type.name == "int":
                return f"({operand}).wrapping_neg()"
            if node.op == "~" and operand_type.name == "int":
                return f"!({operand})"
            return f"{node.op}({operand})"
        if isinstance(node, IRAwait):
            raise RustEmissionError("Rust backend does not support Rove Task<T> yet")
        if isinstance(node, IRResultPropagate):
            result_type = self.inference.expression_type(node.expr)
            if result_type.name != "Result" or len(result_type.arguments) < 2:
                raise RustEmissionError("Result propagation requires Result<T, E>")
            value = self._temporary("propagate_value")
            error = self._temporary("propagate_error")
            cleanup = " ".join(
                f"{self._expr(expression)};" for expression in reversed(self.active_defers)
            )
            if cleanup:
                cleanup += " "
            return (
                f"(match {self._expr(node.expr)} {{ "
                f"RoveResult::Ok({value}) => {value}, "
                f"RoveResult::Err({error}) => {{ {cleanup}"
                f"return RoveResult::Err({error}); }} }})"
            )
        if isinstance(node, IRCall):
            return self._emit_call(node, expected)
        if isinstance(node, IRMemberAccess):
            return self._emit_member(node)
        if isinstance(node, IRIndexAccess):
            obj_type = self.inference.expression_type(node.obj)
            if obj_type.name == "string":
                return f"_rove_string_index(&({self._expr(node.obj)}), {self._expr_as(node.index, INT)})"
            return f"({self._expr(node.obj)})[{self._expr_as(node.index, INT)} as usize].clone()"
        if isinstance(node, IRArray):
            value_type = expected or self.inference.expression_type(node)
            element_type = value_type.arguments[0] if value_type.name == "Array" and value_type.arguments else ANY
            if not node.elements:
                return f"Vec::<{self._rust_type(element_type)}>::new()"
            return "vec![" + ", ".join(self._expr_as(item, element_type) for item in node.elements) + "]"
        if isinstance(node, IRNullCoalesce):
            result_type = expected or self.inference.expression_type(node)
            base = _strip_optional(result_type)
            return (
                f"({self._expr(node.left)}).unwrap_or_else(|| "
                f"{self._expr_as(node.right, base)})"
            )
        if isinstance(node, IRConditional):
            result_type = expected or self.inference.expression_type(node)
            return (
                f"(if {self._condition(node.condition)} {{ "
                f"{self._expr_as(node.then_expr, result_type)} "
                f"}} else {{ {self._expr_as(node.else_expr, result_type)} }})"
            )
        if isinstance(node, IRMatchExpression):
            result_type = expected or self.inference.expression_type(node)
            temporary = self._temporary("match")
            rendered = self._expr_as(node.cases[-1].value, result_type)
            for case in reversed(node.cases[:-1]):
                rendered = (
                    f"if {temporary} == {self._expr(case.pattern)} {{ "
                    f"{self._expr_as(case.value, result_type)} }} else {{ {rendered} }}"
                )
            return f"({{ let {temporary} = {self._expr(node.subject)}; {rendered} }})"
        if isinstance(node, IRLambda):
            params = []
            for parameter in node.params:
                params.append(
                    f"{self._parameter_name(parameter)}: {self._rust_type(parameter.type)}"
                )
            return f"Arc::new(move |{', '.join(params)}| {self._expr(node.body)})"
        raise RustEmissionError(f"Unsupported Rust HIR expression: {type(node).__name__}")

    def _emit_binary(self, node: IRBinary) -> str:
        result_type = self.inference.expression_type(node)
        left_type = self.inference.expression_type(node.left)
        right_type = self.inference.expression_type(node.right)
        if node.op == "+" and result_type.name == "string":
            return (
                f"format!(\"{{}}{{}}\", _rove_display(&({self._expr(node.left)})), "
                f"_rove_display(&({self._expr(node.right)})))"
            )
        if node.op in ("and", "&&", "or", "||"):
            operator = "&&" if node.op in ("and", "&&") else "||"
            return f"({self._condition(node.left)} {operator} {self._condition(node.right)})"
        if node.op in ("==", "!=", "<", ">", "<=", ">="):
            if left_type.name == "float" or right_type.name == "float":
                left = self._expr_as(node.left, FLOAT)
                right = self._expr_as(node.right, FLOAT)
            else:
                left = self._expr(node.left)
                right = self._expr_as(node.right, left_type)
            return f"({left} {node.op} {right})"
        if result_type.name == "int":
            left = self._expr_as(node.left, INT)
            right = self._expr_as(node.right, INT)
            methods = {
                "+": "wrapping_add",
                "-": "wrapping_sub",
                "*": "wrapping_mul",
                "&": "bitand",
                "|": "bitor",
                "^": "bitxor",
            }
            if node.op in methods:
                if node.op in ("&", "|", "^"):
                    return f"({left} {node.op} {right})"
                return f"({left}).{methods[node.op]}({right})"
            if node.op == "/":
                return f"_rove_i64_div({left}, {right})"
            if node.op == "%":
                return f"_rove_i64_mod({left}, {right})"
            if node.op == "<<":
                return f"({left}).wrapping_shl(({right} as u32) & 63)"
            if node.op == ">>":
                return f"({left}).wrapping_shr(({right} as u32) & 63)"
        if result_type.name == "float":
            left = self._expr_as(node.left, FLOAT)
            right = self._expr_as(node.right, FLOAT)
            return f"({left} {node.op} {right})"
        return f"({self._expr(node.left)} {node.op} {self._expr(node.right)})"

    def _emit_call(self, node: IRCall, expected: Optional[IRType]) -> str:
        if node.receiver is not None:
            receiver_type = _strip_optional(self.inference.expression_type(node.receiver))
            if node.callee in ("is_ok", "is_err"):
                return f"({self._expr(node.receiver)}).{node.callee}()"
            if node.callee == "unwrap" and not node.args:
                return f"({self._expr(node.receiver)}).unwrap()"
            if node.callee in ("len", "length", "size") and not node.args:
                return f"_rove_len(&({self._expr(node.receiver)}))"
            if node.callee == "push" and len(node.args) == 1:
                element_type = receiver_type.arguments[0] if receiver_type.arguments else ANY
                return f"{self._lvalue(node.receiver)}.push({self._expr_as(node.args[0], element_type)})"
            if node.callee == "send" and len(node.args) == 1:
                return f"{self._lvalue(node.receiver)}.send({self._expr_as(node.args[0], ANY)})"
            if node.callee == "receive" and not node.args:
                return f"{self._lvalue(node.receiver)}.receive()"
            function = self.inference.methods.get((receiver_type.name, node.callee))
            parameters = list(function.params) if function is not None else []
            if parameters and parameters[0].name in ("self", "this"):
                parameters = parameters[1:]
            args = self._render_call_arguments(node.args, parameters)
            receiver = self._lvalue(node.receiver) if isinstance(node.receiver, (IRReference, IRMemberAccess, IRIndexAccess)) else self._expr(node.receiver)
            return f"({receiver}).{self._identifier(node.callee)}({', '.join(args)})"

        if node.callee == "print":
            values = ", ".join(f"_rove_display(&({self._expr(arg)}))" for arg in node.args)
            return f"_rove_print(&[{values}])"
        if node.callee == "input":
            if not node.args:
                return "_rove_input(None)"
            return f"_rove_input(Some(&({self._expr_as(node.args[0], STRING)})))"
        if node.callee in ("to_string", "to_str"):
            return f"_rove_display(&({self._expr(node.args[0])}))"
        if node.callee == "to_int":
            return f"_rove_to_int(&({self._expr_as(node.args[0], STRING)}))"
        if node.callee == "contains":
            return (
                f"_rove_contains(&({self._expr_as(node.args[0], STRING)}), "
                f"&({self._expr_as(node.args[1], STRING)}))"
            )
        if node.callee == "is_number":
            return f"_rove_is_number(&({self._expr_as(node.args[0], STRING)}))"
        if node.callee == "len":
            return f"_rove_len(&({self._expr(node.args[0])}))"
        if node.callee == "args":
            return "std::env::args().collect::<Vec<String>>()"
        if node.callee == "addr":
            return f"(&{self._lvalue(node.args[0])} as *const _ as usize)"
        if node.callee == "peek":
            return f"_rove_peek({self._expr(node.args[0])} as usize)"
        if node.callee == "memdump":
            length = self._expr_as(node.args[1], INT) if len(node.args) > 1 else "16_i64"
            return f"_rove_memdump({self._expr(node.args[0])} as usize, {length})"
        if node.callee == "delay_ms":
            return f"_rove_delay_ms({self._expr_as(node.args[0], INT)})"
        if node.callee == "channel":
            return "_rove_channel()"
        if node.callee in ("Ok", "Err"):
            result_type = expected if expected is not None and expected.name == "Result" else node.type
            arguments = list(result_type.arguments)
            while len(arguments) < 2:
                arguments.append(ANY)
            index = 0 if node.callee == "Ok" else 1
            payload = self._expr_as(node.args[0], arguments[index]) if node.args else "()"
            return (
                f"RoveResult::<{self._rust_type(arguments[0])}, {self._rust_type(arguments[1])}>::"
                f"{node.callee}({payload})"
            )

        if node.callee_symbol.startswith("type::struct::"):
            struct = self.inference.structs.get(node.callee)
            parameters = list(struct.fields) if struct is not None else []
        else:
            function = self.inference.functions.get(node.callee_symbol)
            parameters = list(function.params) if function is not None else []
        args = self._render_call_arguments(node.args, parameters)
        callee = self._symbol(node.callee_symbol, node.callee)
        return f"{callee}({', '.join(args)})"

    def _render_call_arguments(
        self,
        arguments: Sequence[IRExpr],
        parameters: Sequence[IRParameter],
    ) -> List[str]:
        rendered = []
        for index, argument in enumerate(arguments):
            expected = (
                self.inference.type_of_symbol(parameters[index].symbol, parameters[index].type)
                if index < len(parameters) else None
            )
            rendered.append(self._expr_as(argument, expected) if expected is not None else self._expr(argument))
        for parameter in parameters[len(arguments):]:
            if parameter.default is None:
                break
            expected = self.inference.type_of_symbol(parameter.symbol, parameter.type)
            rendered.append(self._expr_as(parameter.default, expected))
        return rendered

    def _emit_member(self, node: IRMemberAccess) -> str:
        obj_type = self.inference.expression_type(node.obj)
        owner = _strip_optional(obj_type).name
        field_type = self.inference.field_type(owner, node.member, node.type)
        member = self._identifier(node.member)
        if owner == "Result" and member in ("is_ok", "is_err"):
            return f"({self._expr(node.obj)}).{member}()"
        if node.safe:
            obj = self._expr(node.obj)
            if obj_type.optional:
                combinator = "and_then" if field_type.optional else "map"
                return f"({obj}).as_ref().{combinator}(|value| value.{member}.clone())"
            access = f"({obj}).{member}.clone()"
            return access if field_type.optional else f"Some({access})"
        if isinstance(node.obj, IRReference) and node.obj.name in ("self", "this"):
            return f"self.{member}.clone()"
        return f"({self._expr(node.obj)}).{member}.clone()"

    def _expr_as(self, node: Optional[IRExpr], expected: Optional[IRType]) -> str:
        if node is None:
            return "()"
        if expected is None:
            return self._expr(node)
        actual = self.inference.expression_type(node)
        if expected.optional:
            base = _strip_optional(expected)
            if isinstance(node, IRLiteral) and node.value is None:
                return "None"
            if actual.optional:
                return self._expr(node, expected)
            return f"Some({self._expr_as(node, base)})"
        if expected.is_unknown:
            return self._into_dynamic(node, actual)
        if actual.is_unknown:
            value = self._expr(node)
            if expected.name == "int":
                return f"_rove_expect_i64({value})"
            if expected.name == "float":
                return f"_rove_expect_f64({value})"
            if expected.name == "bool":
                return f"_rove_expect_bool({value})"
            if expected.name == "string":
                return f"_rove_expect_string({value})"
        if expected.name == "float" and actual.name == "int":
            return f"({self._expr(node)} as f64)"
        if expected.name == "Result" and isinstance(node, IRCall) and node.callee in ("Ok", "Err"):
            return self._emit_call(node, expected)
        if expected.name == "Array" and isinstance(node, IRArray):
            return self._expr(node, expected)
        return self._expr(node, expected)

    def _into_dynamic(self, node: IRExpr, actual: IRType) -> str:
        value = self._expr(node)
        if actual.is_unknown:
            return value
        if actual.name == "int":
            return f"RoveValue::Int({value})"
        if actual.name == "float":
            return f"RoveValue::Float({value})"
        if actual.name == "bool":
            return f"RoveValue::Bool({value})"
        if actual.name == "string":
            return f"RoveValue::String({value})"
        if actual.name == "null":
            return "RoveValue::Null"
        if actual.name == "Array":
            element_type = actual.arguments[0] if actual.arguments else ANY
            if element_type.is_unknown:
                return f"RoveValue::Array({value})"
            return f"RoveValue::Array(({value}).into_iter().map(|item| {self._dynamic_from_name('item', element_type)}).collect())"
        return f"RoveValue::Opaque(_rove_display(&({value})))"

    def _dynamic_from_name(self, name: str, value_type: IRType) -> str:
        constructors = {
            "int": "Int",
            "float": "Float",
            "bool": "Bool",
            "string": "String",
        }
        variant = constructors.get(value_type.name)
        return f"RoveValue::{variant}({name})" if variant else f"RoveValue::Opaque(_rove_display(&{name}))"

    def _lvalue(
        self,
        node: IRExpr,
        *,
        global_guard: Optional[Tuple[str, str]] = None,
    ) -> str:
        if isinstance(node, IRReference):
            if global_guard is not None and node.symbol == global_guard[0]:
                return f"(*{global_guard[1]})"
            if node.symbol in self.globals:
                return f"(*{self._symbol(node.symbol, node.name)}.lock().unwrap())"
            return self._symbol(node.symbol, node.name)
        if isinstance(node, IRMemberAccess):
            return f"{self._lvalue(node.obj, global_guard=global_guard)}.{self._identifier(node.member)}"
        if isinstance(node, IRIndexAccess):
            return (
                f"{self._lvalue(node.obj, global_guard=global_guard)}"
                f"[{self._expr_as(node.index, INT)} as usize]"
            )
        raise RustEmissionError(f"Invalid Rust assignment/address target: {type(node).__name__}")

    def _root_reference(self, node: IRExpr) -> Optional[IRReference]:
        current = node
        while isinstance(current, (IRMemberAccess, IRIndexAccess)):
            current = current.obj
        return current if isinstance(current, IRReference) else None

    def _method_mutates_self(self, node: IRFunction) -> bool:
        self_symbols = {
            parameter.symbol for parameter in node.params if parameter.name in ("self", "this")
        }
        if not self_symbols:
            return False

        def visits(value: object) -> bool:
            if isinstance(value, IRAssign):
                root = self._root_reference(value.target)
                if root is not None and root.symbol in self_symbols:
                    return True
            if isinstance(value, tuple):
                return any(visits(item) for item in value)
            if is_dataclass(value):
                return any(visits(getattr(value, field.name)) for field in fields(value))
            return False

        return visits(node.body)

    def _symbol_assigned(self, value: object, symbol: str) -> bool:
        if isinstance(value, IRAssign):
            root = self._root_reference(value.target)
            if root is not None and root.symbol == symbol:
                return True
        if isinstance(value, tuple):
            return any(self._symbol_assigned(item, symbol) for item in value)
        if is_dataclass(value):
            return any(
                self._symbol_assigned(getattr(value, field.name), symbol)
                for field in fields(value)
            )
        return False

    def _rust_type(self, value_type: IRType) -> str:
        if value_type.optional:
            return f"Option<{self._rust_type(_strip_optional(value_type))}>"
        if value_type.pointer:
            return "usize"
        if value_type.is_function:
            params = ", ".join(self._rust_type(item) for item in value_type.parameter_types)
            result = self._rust_type(value_type.return_type or VOID)
            return f"Arc<dyn Fn({params}) -> {result} + Send + Sync>"
        mapping = {
            "any": "RoveValue",
            "void": "()",
            "null": "RoveValue",
            "bool": "bool",
            "int": "i64",
            "i8": "i8",
            "i16": "i16",
            "i32": "i32",
            "i64": "i64",
            "u8": "u8",
            "u16": "u16",
            "u32": "u32",
            "u64": "u64",
            "float": "f64",
            "f32": "f32",
            "f64": "f64",
            "string": "String",
            "uintptr": "usize",
            "Channel": "RoveChannel",
        }
        if value_type.name in mapping:
            return mapping[value_type.name]
        if value_type.name == "Array":
            element = value_type.arguments[0] if value_type.arguments else ANY
            return f"Vec<{self._rust_type(element)}>"
        if value_type.name == "Option":
            element = value_type.arguments[0] if value_type.arguments else ANY
            return f"Option<{self._rust_type(element)}>"
        if value_type.name == "Result":
            ok_type = value_type.arguments[0] if value_type.arguments else ANY
            err_type = value_type.arguments[1] if len(value_type.arguments) > 1 else ANY
            return f"RoveResult<{self._rust_type(ok_type)}, {self._rust_type(err_type)}>"
        if value_type.name == "Task":
            raise RustEmissionError("Rust backend does not support Rove Task<T> yet")
        if value_type.name not in self.declared_types:
            return "RoveValue"
        arguments = ""
        if value_type.arguments:
            arguments = "<" + ", ".join(self._rust_type(item) for item in value_type.arguments) + ">"
        return self._identifier(value_type.name) + arguments

    def _ffi_type(self, value_type: IRType) -> str:
        if value_type.pointer:
            return "*mut std::ffi::c_void"
        mapping = {
            "void": "()",
            "bool": "bool",
            "int": "i64",
            "i8": "i8",
            "i16": "i16",
            "i32": "i32",
            "i64": "i64",
            "u8": "u8",
            "u16": "u16",
            "u32": "u32",
            "u64": "u64",
            "float": "f64",
            "f32": "f32",
            "f64": "f64",
            "uintptr": "usize",
        }
        if value_type.name not in mapping:
            raise RustEmissionError(f"Type '{value_type.canonical()}' has no stable Rust FFI mapping")
        return mapping[value_type.name]

    @staticmethod
    def _is_copy_type(value_type: IRType) -> bool:
        return not value_type.optional and not value_type.pointer and value_type.name in (
            "bool", "int", "i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64",
            "float", "f32", "f64", "uintptr"
        )

    def _parameter_name(self, parameter: IRParameter) -> str:
        if parameter.name in ("self", "this"):
            self.symbol_names[parameter.symbol] = "self"
            return "self"
        return self._symbol(parameter.symbol, parameter.name)

    def _reserve_symbol(self, symbol: str, preferred: str) -> str:
        if symbol in self.symbol_names:
            return self.symbol_names[symbol]
        base = self._identifier(preferred)
        candidate = base
        suffix = 2
        while candidate in self.used_names:
            candidate = f"{base}_{suffix}"
            suffix += 1
        self.symbol_names[symbol] = candidate
        self.used_names.add(candidate)
        return candidate

    def _symbol(self, symbol: str, preferred: str) -> str:
        return self.symbol_names.get(symbol) or self._reserve_symbol(symbol, preferred)

    def _temporary(self, purpose: str) -> str:
        self.temporary_index += 1
        return f"_rove_{purpose}_{self.temporary_index}"

    @staticmethod
    def _identifier(name: str) -> str:
        clean = re.sub(r"[^A-Za-z0-9_]", "_", name or "rove_value")
        if not clean or clean[0].isdigit():
            clean = "rove_" + clean
        if clean in _RUST_KEYWORDS:
            clean += "_rove"
        return clean

    @staticmethod
    def _string_literal(value: str) -> str:
        parts = ['"']
        escapes = {
            "\\": "\\\\",
            '"': '\\"',
            "\n": "\\n",
            "\r": "\\r",
            "\t": "\\t",
            "\0": "\\0",
        }
        for character in value:
            if character in escapes:
                parts.append(escapes[character])
            elif ord(character) < 0x20 or ord(character) == 0x7F:
                parts.append(f"\\u{{{ord(character):x}}}")
            else:
                parts.append(character)
        parts.append('"')
        return "".join(parts)

    def _generic_declaration(self, parameters: Iterable[str]) -> str:
        values = [
            f"{self._identifier(item)}: Clone + Debug + PartialEq + RoveDisplay"
            for item in parameters
        ]
        return "" if not values else "<" + ", ".join(values) + ">"

    def _generic_use(self, parameters: Iterable[str]) -> str:
        values = [self._identifier(item) for item in parameters]
        return "" if not values else "<" + ", ".join(values) + ">"


def emit_rust(module: IRModule) -> str:
    return HIRRustEmitter(module).emit()
