"""Rust 2021 source emitter for legalized scalar/control-flow MIR."""

from __future__ import annotations

import json
import math
import re
from dataclasses import replace

from .codegen_cpp import MIRCodegenError
from .effects import infer_module_effects
from .legalization import legalize_mir
from .model import (
    AggregateRValue,
    AssertTerminator,
    AssignStatement,
    BinaryRValue,
    BorrowRValue,
    CastRValue,
    CallTerminator,
    ConstOperand,
    ConstantIndexProjection,
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
    MIREnumDef,
    MIRStructDef,
    MoveOperand,
    NopStatement,
    Operand,
    PayloadRValue,
    Place,
    ReleaseStatement,
    RetainStatement,
    ReturnTerminator,
    StorageDeadStatement,
    StorageLiveStatement,
    SuspendTerminator,
    SwitchIntTerminator,
    SwitchValueTerminator,
    ThrowTerminator,
    UnaryRValue,
    UnreachableTerminator,
    UseRValue,
)
from .types import MIRType


_RUNTIME = r'''trait RoveDisplay {
    fn rove_display(&self) -> String;
}

impl RoveDisplay for i64 { fn rove_display(&self) -> String { self.to_string() } }
impl RoveDisplay for bool {
    fn rove_display(&self) -> String {
        if *self { "true".to_string() } else { "false".to_string() }
    }
}
impl RoveDisplay for f64 {
    fn rove_display(&self) -> String {
        if self.is_nan() { return "nan".to_string(); }
        if *self == f64::INFINITY { return "inf".to_string(); }
        if *self == f64::NEG_INFINITY { return "-inf".to_string(); }
        if *self == 0.0 { return "0".to_string(); }
        let text = self.to_string();
        let (negative, body) = if let Some(body) = text.strip_prefix('-') {
            (true, body)
        } else {
            (false, text.as_str())
        };
        let (mantissa, exponent) = if let Some(marker) = body.find(|c: char| c == 'e' || c == 'E') {
            (&body[..marker], body[marker + 1..].parse::<i32>().expect("Rove float exponent"))
        } else {
            (body, 0)
        };
        let dot = mantissa.find('.').unwrap_or(mantissa.len());
        let digits = mantissa.replace('.', "");
        let first = digits.len() - digits.trim_start_matches('0').len();
        let decimal = dot as i32 + exponent - first as i32;
        let digits = digits[first..].trim_end_matches('0');
        let rendered = if decimal > -6 && decimal <= 21 {
            if decimal <= 0 {
                format!("0.{}{}", "0".repeat((-decimal) as usize), digits)
            } else if decimal as usize >= digits.len() {
                format!("{}{}", digits, "0".repeat(decimal as usize - digits.len()))
            } else {
                format!("{}.{}", &digits[..decimal as usize], &digits[decimal as usize..])
            }
        } else {
            let fraction = if digits.len() > 1 { format!(".{}", &digits[1..]) }
                           else { String::new() };
            let exponent = decimal - 1;
            format!("{}{}e{}{}", &digits[..1], fraction,
                    if exponent >= 0 { "+" } else { "" }, exponent)
        };
        if negative { format!("-{rendered}") } else { rendered }
    }
}
impl RoveDisplay for String { fn rove_display(&self) -> String { self.clone() } }
impl<T: RoveDisplay> RoveDisplay for Vec<T> {
    fn rove_display(&self) -> String {
        let payload = self.iter().map(RoveDisplay::rove_display).collect::<Vec<_>>().join(", ");
        format!("[{}]", payload)
    }
}
impl<T: RoveDisplay, E: RoveDisplay> RoveDisplay for Result<T, E> {
    fn rove_display(&self) -> String {
        match self {
            Ok(value) => format!("Ok({})", value.rove_display()),
            Err(error) => format!("Err({})", error.rove_display()),
        }
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

#[derive(Clone, Debug)]
struct RoveUserThrow {
    message: String,
}

type RoveCallResult<T> = Result<T, RoveUserThrow>;

enum RoveTaskState<T> {
    Pending(Option<Box<dyn FnOnce() -> RoveCallResult<T>>>),
    Ready(RoveCallResult<T>),
}

#[derive(Clone)]
struct RoveTask<T> {
    state: std::rc::Rc<std::cell::RefCell<RoveTaskState<T>>>,
}

impl<T> Default for RoveTask<T> {
    fn default() -> Self {
        Self {
            state: std::rc::Rc::new(std::cell::RefCell::new(
                RoveTaskState::Pending(None),
            )),
        }
    }
}

impl<T: Clone + 'static> RoveTask<T> {
    fn new<F>(run: F) -> Self
    where
        F: FnOnce() -> RoveCallResult<T> + 'static,
    {
        Self {
            state: std::rc::Rc::new(std::cell::RefCell::new(
                RoveTaskState::Pending(Some(Box::new(run))),
            )),
        }
    }

    fn await_result(&self) -> RoveCallResult<T> {
        let pending = {
            let mut state = self.state.borrow_mut();
            match &mut *state {
                RoveTaskState::Ready(result) => return result.clone(),
                RoveTaskState::Pending(run) => run.take(),
            }
        };
        let result = pending
            .expect("attempted to await an uninitialized Rove task")();
        *self.state.borrow_mut() = RoveTaskState::Ready(result.clone());
        result
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
struct RoveAny;

struct RovePtr<T> {
    ptr: *mut T,
    mutable: bool,
}

impl<T> Copy for RovePtr<T> {}
impl<T> Clone for RovePtr<T> { fn clone(&self) -> Self { *self } }
impl<T> Default for RovePtr<T> {
    fn default() -> Self { Self { ptr: std::ptr::null_mut(), mutable: false } }
}

impl<T> RovePtr<T> {
    fn borrow(value: &T) -> Self {
        Self { ptr: value as *const T as *mut T, mutable: false }
    }

    fn borrow_mut(value: &mut T) -> Self {
        Self { ptr: value as *mut T, mutable: true }
    }

    unsafe fn read(&self) -> &T {
        if self.ptr.is_null() { panic!("null Rove MIR pointer dereference"); }
        unsafe { &*self.ptr }
    }

    unsafe fn write(&mut self) -> &mut T {
        if self.ptr.is_null() { panic!("null Rove MIR pointer dereference"); }
        if !self.mutable { panic!("assignment through immutable Rove MIR borrow"); }
        unsafe { &mut *self.ptr }
    }
}

fn rove_display<T: RoveDisplay + ?Sized>(value: &T) -> String { value.rove_display() }

fn rove_i64_div(left: i64, right: i64) -> i64 {
    if right == 0 { panic!("division by zero"); }
    if left == i64::MIN && right == -1 { i64::MIN } else { left / right }
}

fn rove_i64_rem(left: i64, right: i64) -> i64 {
    if right == 0 { panic!("remainder by zero"); }
    if left == i64::MIN && right == -1 { 0 } else { left % right }
}

fn rove_index<T>(values: &[T], index: i64) -> &T {
    if index < 0 || index as usize >= values.len() { panic!("array index out of bounds"); }
    &values[index as usize]
}

fn rove_index_mut<T>(values: &mut [T], index: i64) -> &mut T {
    if index < 0 || index as usize >= values.len() { panic!("array index out of bounds"); }
    &mut values[index as usize]
}'''


def _identifier(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not clean or clean[0].isdigit():
        clean = "_" + clean
    return clean


class _RustEmitter:
    def __init__(self, module: MIRModule):
        self.module = infer_module_effects(module)
        module = self.module
        self.function_names = {
            function.symbol: f"rove_fn_{_identifier(function.name)}"
            for function in module.functions
        }
        self.function_names.update({
            function.name: self.function_names[function.symbol]
            for function in module.functions
        })
        self.functions = {function.symbol: function for function in module.functions}
        self.functions.update({function.name: function for function in module.functions})
        self.structs = {
            definition.name: definition
            for definition in module.type_definitions
            if isinstance(definition, MIRStructDef)
        }
        self.enums = {
            definition.name: definition
            for definition in module.type_definitions
            if isinstance(definition, MIREnumDef)
        }
        self.current: MIRFunction | None = None
        self.local_types: dict[int, MIRType] = {}

    def emit(self) -> str:
        self.display_names = self._collect_display_names()
        parts = [
            "// Experimental Rove legalized MIR -> Rust 2021 output.",
            "#![allow(dead_code, nonstandard_style, unused_assignments, unused_mut, unused_parens, unused_variables, unreachable_code)]",
            "",
            _RUNTIME,
            "",
        ]
        parts.extend(self._struct_definition(definition) + "\n" for definition in self.structs.values())
        parts.extend(self._enum_definition(definition) + "\n" for definition in self.enums.values())
        parts.extend(self._function(function) + "\n" for function in self.module.functions)
        parts.append(self._entry_point())
        return "\n".join(parts).rstrip() + "\n"

    def _struct_definition(self, definition: MIRStructDef) -> str:
        type_name = f"RoveType_{_identifier(definition.name)}"
        lines = ["#[derive(Clone, Debug, Default, PartialEq)]", f"struct {type_name} {{"]
        for field in definition.fields:
            lines.append(f"    {_identifier(field.name)}: {self._type(field.type)},")
        lines.append("}")
        if definition.name in self.display_names:
            fields = ", ".join(
                f"self.{_identifier(field.name)}.rove_display()"
                for field in definition.fields
            )
            lines.extend((
                f"impl RoveDisplay for {type_name} {{",
                "    fn rove_display(&self) -> String {",
                f"        let fields: Vec<String> = vec![{fields}];",
                f"        format!({json.dumps(definition.name + '({})')}, fields.join(\", \"))",
                "    }",
                "}",
            ))
        return "\n".join(lines)

    def _enum_definition(self, definition: MIREnumDef) -> str:
        type_name = f"RoveType_{_identifier(definition.name)}"
        lines = ["#[derive(Clone, Debug, PartialEq)]", f"enum {type_name} {{"]
        for variant in definition.variants:
            payload = ", ".join(self._type(item) for item in variant.payload_types)
            suffix = f"({payload})" if payload else ""
            lines.append(f"    {_identifier(variant.name)}{suffix},")
        lines.append("}")
        if definition.variants:
            first = definition.variants[0]
            defaults = ", ".join("Default::default()" for _ in first.payload_types)
            suffix = f"({defaults})" if defaults else ""
            lines.extend((
                f"impl Default for {type_name} {{",
                f"    fn default() -> Self {{ Self::{_identifier(first.name)}{suffix} }}",
                "}",
            ))
        if definition.name in self.display_names:
            lines.extend((
                f"impl RoveDisplay for {type_name} {{",
                "    fn rove_display(&self) -> String {",
                "        match self {",
            ))
            for variant in definition.variants:
                bindings = [f"value{index}" for index in range(len(variant.payload_types))]
                pattern = f"Self::{_identifier(variant.name)}"
                if bindings:
                    pattern += f"({', '.join(bindings)})"
                    values = ", ".join(
                        f"{binding}.rove_display()" for binding in bindings
                    )
                    lines.append(
                        f"            {pattern} => format!("
                        f"{json.dumps(variant.name + '({})')}, "
                        f"[{values}].join(\", \")),"
                    )
                else:
                    lines.append(
                        f"            {pattern} => "
                        f"{json.dumps(variant.name + '()')}.to_string(),"
                    )
            lines.extend(("        }", "    }", "}"))
        return "\n".join(lines)

    def _collect_display_names(self) -> set[str]:
        names: set[str] = set()
        visited: set[str] = set()

        def visit(value_type: MIRType) -> None:
            key = value_type.canonical()
            if key in visited:
                return
            visited.add(key)
            for argument in value_type.arguments:
                visit(argument)
            definition = self.structs.get(value_type.name)
            if definition is not None:
                names.add(definition.name)
                for field in definition.fields:
                    visit(field.type)
            definition_enum = self.enums.get(value_type.name)
            if definition_enum is not None:
                names.add(definition_enum.name)
                for variant in definition_enum.variants:
                    for payload in variant.payload_types:
                        visit(payload)

        previous_types = self.local_types
        for function in self.module.functions:
            self.local_types = {local.id: local.type for local in function.locals}
            for block in function.blocks:
                terminator = block.terminator
                if isinstance(terminator, CallTerminator) and terminator.function in {
                    "builtin::print", "builtin::to_string",
                }:
                    for argument in terminator.arguments:
                        visit(self._operand_type(argument))
                elif isinstance(terminator, ThrowTerminator):
                    visit(self._operand_type(terminator.value))
        self.local_types = previous_types
        return names

    def _entry_point(self) -> str:
        by_name = {function.name: function for function in self.module.functions}
        entry = by_name.get("main") or by_name.get("__nyx_top_level")
        if entry is None:
            return "fn main() {}"
        if entry.is_async:
            return (
                "fn main() {\n"
                f"    if let Err(thrown) = {self.function_names[entry.symbol]}().await_result() {{\n"
                "        eprintln!(\"{}\", thrown.message);\n"
                "        std::process::exit(1);\n"
                "    }\n"
                "}"
            )
        if self._may_throw(entry):
            return (
                "fn main() {\n"
                f"    if let Err(thrown) = {self.function_names[entry.symbol]}() {{\n"
                "        eprintln!(\"{}\", thrown.message);\n"
                "        std::process::exit(1);\n"
                "    }\n"
                "}"
            )
        return f"fn main() {{ {self.function_names[entry.symbol]}(); }}"

    def _function(self, function: MIRFunction) -> str:
        self.current = function
        self.local_types = {local.id: local.type for local in function.locals}
        parameters = ", ".join(
            f"mut l{local}: {self._type(function.locals[local].type, function)}"
            for local in function.parameters
        )
        return_type = self._type(function.locals[function.return_local].type, function)
        if function.is_async:
            suffix = f" -> RoveTask<{return_type}>"
        elif self._may_throw(function):
            suffix = f" -> RoveCallResult<{return_type}>"
        else:
            suffix = "" if return_type == "()" else f" -> {return_type}"
        signature = f"fn {self.function_names[function.symbol]}({parameters}){suffix} {{"
        lines: list[str] = []
        parameter_ids = set(function.parameters)
        for local in function.locals:
            rendered = self._type(local.type, function)
            if local.id in parameter_ids or rendered == "()":
                continue
            lines.append(f"    let mut l{local.id}: {rendered} = {self._default(local.type)};")
        lines.extend(("    let mut pc: usize = 0;", "    loop {", "        match pc {"))
        for block in function.blocks:
            lines.append(f"            {block.id} => {{")
            for statement in block.statements:
                lines.extend(f"                {line}" for line in self._statement(statement))
            lines.extend(f"                {line}" for line in self._terminator(block.terminator))
            lines.append("            }")
        lines.extend(("            _ => unreachable!(\"invalid MIR block\"),", "        }", "    }"))
        if function.is_async:
            rendered_lines = [signature, "    RoveTask::new(move || {"]
            rendered_lines.extend(f"    {line}" for line in lines)
            rendered_lines.extend(("    })", "}"))
        else:
            rendered_lines = [signature, *lines, "}"]
        self.current = None
        self.local_types = {}
        return "\n".join(rendered_lines)

    def _statement(self, statement: object) -> list[str]:
        if isinstance(statement, AssignStatement):
            destination = self._place_type(statement.place)
            if destination.name in ("void", "any"):
                return []
            return [self._assign_place(statement.place, self._rvalue(statement.value))]
        if isinstance(statement, (StorageLiveStatement, StorageDeadStatement, NopStatement)):
            return []
        if isinstance(statement, (RetainStatement, ReleaseStatement)):
            # MIR copy/move operands already carry the value ownership action.
            return []
        if isinstance(statement, DeinitStatement):
            return [self._assign_place(statement.place, self._default(self._place_type(statement.place)))]
        raise MIRCodegenError(f"illegal statement reached Rust emitter: {type(statement).__name__}")

    def _terminator(self, value: object) -> list[str]:
        if isinstance(value, GotoTerminator):
            return self._goto(value.target)
        if isinstance(value, SwitchIntTerminator):
            discriminator = self._operand(value.discriminator)
            discriminator_type = self._operand_type(value.discriminator)
            lines: list[str] = []
            for expected, target in value.targets:
                rendered = (
                    "true" if bool(expected) else "false"
                ) if discriminator_type.name == "bool" else self._constant(expected)
                lines.append(f"if {discriminator} == {rendered} {{")
                lines.extend(f"    {line}" for line in self._goto(target))
                lines.append("}")
            lines.extend(self._goto(value.otherwise))
            return lines
        if isinstance(value, SwitchValueTerminator):
            discriminator = self._operand(value.discriminator)
            discriminator_type = self._operand_type(value.discriminator)
            lines = []
            for expected, target in value.targets:
                if expected is None and discriminator_type.optional:
                    condition = f"({discriminator}).is_none()"
                elif discriminator_type.optional:
                    condition = f"({discriminator}).as_ref() == Some(&{self._constant(expected)})"
                else:
                    condition = f"{discriminator} == {self._constant(expected)}"
                lines.append(f"if {condition} {{")
                lines.extend(f"    {line}" for line in self._goto(target))
                lines.append("}")
            lines.extend(self._goto(value.otherwise))
            return lines
        if isinstance(value, CallTerminator):
            if value.target is None:
                raise MIRCodegenError(f"call '{value.function}' has no continuation")
            arguments = ", ".join(self._operand(argument) for argument in value.arguments)
            if value.function == "builtin::print":
                displays = ", ".join(
                    f"rove_display(&{self._operand(argument)})" for argument in value.arguments
                )
                line = "println!();" if not displays else f"println!(\"{{}}\", [{displays}].join(\" \"));"
            elif value.function == "builtin::len":
                if len(value.arguments) != 1 or value.destination is None:
                    raise MIRCodegenError("builtin::len requires one argument and a destination")
                line = f"{self._place(value.destination)} = {self._operand(value.arguments[0])}.len() as i64;"
            elif value.function == "builtin::to_string":
                if len(value.arguments) != 1 or value.destination is None:
                    raise MIRCodegenError("builtin::to_string requires one argument and a destination")
                line = f"{self._place(value.destination)} = rove_display(&{self._operand(value.arguments[0])});"
            elif value.function in self.function_names:
                call = f"{self.function_names[value.function]}({arguments})"
                callee = self.functions[value.function]
                result = self._type(callee.locals[callee.return_local].type, callee)
                if self._may_throw(callee) and not callee.is_async:
                    if value.unwind is not None:
                        if value.error_destination is None:
                            raise MIRCodegenError("Rust MIR call unwind requires an error destination")
                        lines = [f"match {call} {{", "    Ok(rove_value) => {"]
                        if value.destination is not None and result != "()":
                            lines.append(f"        {self._assign_place(value.destination, 'rove_value')}")
                        lines.extend(f"        {item}" for item in self._goto(value.target))
                        lines.extend(("    }", "    Err(rove_throw) => {"))
                        lines.append(
                            f"        {self._assign_place(value.error_destination, 'rove_throw.message')}"
                        )
                        lines.extend(f"        {item}" for item in self._goto(value.unwind))
                        lines.extend(("    }", "}"))
                        return lines
                    call = f"{call}?"
                if value.destination is not None and result != "()":
                    line = self._assign_place(value.destination, call)
                else:
                    line = f"{call};"
            else:
                raise MIRCodegenError(f"illegal runtime call reached Rust emitter: {value.function}")
            return [line] + self._goto(value.target)
        if isinstance(value, SuspendTerminator):
            task = self._operand(value.task)
            lines = [f"match {task}.await_result() {{", "    Ok(rove_value) => {"]
            lines.append(f"        {self._assign_place(value.destination, 'rove_value')}")
            lines.extend(f"        {item}" for item in self._goto(value.resume))
            lines.extend(("    }", "    Err(rove_throw) => {"))
            if value.unwind is not None:
                if value.error_destination is None:
                    raise MIRCodegenError("Rust MIR suspend unwind requires an error destination")
                lines.append(
                    f"        {self._assign_place(value.error_destination, 'rove_throw.message')}"
                )
                lines.extend(f"        {item}" for item in self._goto(value.unwind))
            else:
                lines.append("        return Err(rove_throw);")
            lines.extend(("    }", "}"))
            return lines
        if isinstance(value, AssertTerminator):
            condition = self._operand(value.condition)
            expected = "true" if value.expected else "false"
            return [
                f"if ({condition}) != {expected} {{ panic!({json.dumps(value.message)}); }}"
            ] + self._goto(value.target)
        if isinstance(value, DropTerminator):
            if value.unwind is not None:
                raise MIRCodegenError("Rust MIR drop unwind edge was not legalized")
            return [f"drop({self._take_place(value.place)});"] + self._goto(value.target)
        if isinstance(value, ThrowTerminator):
            thrown = self._operand(value.value)
            if value.target is not None:
                if value.destination is None:
                    raise MIRCodegenError("Rust MIR caught throw requires a destination")
                return [
                    self._assign_place(value.destination, thrown),
                    *self._goto(value.target),
                ]
            return [
                f"return Err(RoveUserThrow {{ message: rove_display(&{thrown}) }});"
            ]
        if isinstance(value, ReturnTerminator):
            assert self.current is not None
            result = self._type(self.current.locals[self.current.return_local].type, self.current)
            if self.current.is_async or self._may_throw(self.current):
                return ["return Ok(());"] if result == "()" else ["return Ok(l0);"]
            return ["return;"] if result == "()" else ["return l0;"]
        if isinstance(value, UnreachableTerminator):
            return ["unreachable!(\"reached unreachable MIR terminator\");"]
        raise MIRCodegenError(f"illegal terminator reached Rust emitter: {type(value).__name__}")

    @staticmethod
    def _goto(target: int) -> list[str]:
        return [f"pc = {target};", "continue;"]

    @staticmethod
    def _may_throw(function: MIRFunction) -> bool:
        return "may_throw" in function.effects

    def _rvalue(self, value: object) -> str:
        if isinstance(value, UseRValue):
            return self._operand(value.operand)
        if isinstance(value, BinaryRValue):
            return self._binary(value)
        if isinstance(value, CastRValue):
            operand = self._operand(value.operand)
            source_type = self._operand_type(value.operand)
            if (
                value.kind == "implicit"
                and source_type.name == "int"
                and value.type.name in ("float", "f64")
                and not source_type.optional
                and not value.type.optional
            ):
                return f"({operand} as f64)"
            if (
                source_type.name == "Result"
                and value.type.name == "Result"
                and len(source_type.arguments) == 2
                and len(value.type.arguments) == 2
            ):
                return self._result_cast(operand, source_type, value.type)
            if value.kind == "optional-unwrap":
                return f"({operand}).expect(\"optional unwrap failed\")"
            if value.type.optional:
                return f"Some({operand})"
            return operand
        if isinstance(value, AggregateRValue):
            operands = [self._operand(operand) for operand in value.operands]
            if value.kind == "array":
                return "vec![" + ", ".join(operands) + "]"
            if value.kind == "struct":
                fields = value.fields or tuple(str(index) for index in range(len(operands)))
                body = ", ".join(f"{_identifier(name)}: {operand}" for name, operand in zip(fields, operands))
                return f"RoveType_{_identifier(value.name)} {{ {body} }}"
            if value.kind == "enum":
                suffix = f"({', '.join(operands)})" if operands else ""
                return f"RoveType_{_identifier(value.type.name)}::{_identifier(value.name)}{suffix}"
            if value.kind == "result":
                if len(operands) != 1 or value.name not in ("Ok", "Err"):
                    raise MIRCodegenError(
                        f"Rust Result aggregate requires one Ok/Err payload, got '{value.name}'"
                    )
                return f"{value.name}({operands[0]})"
            raise MIRCodegenError(f"unsupported Rust aggregate kind '{value.kind}'")
        if isinstance(value, DiscriminantRValue):
            operand_type = self._operand_type(value.operand)
            if operand_type.name == "Result" and len(operand_type.arguments) == 2:
                return (
                    "match &" + self._operand(value.operand)
                    + " { Ok(_) => String::from(\"Ok\"), Err(_) => String::from(\"Err\") }"
                )
            definition = self.enums.get(operand_type.name)
            if definition is None:
                raise MIRCodegenError(f"Rust discriminant requires a known enum, got '{operand_type}'")
            arms = []
            type_name = f"RoveType_{_identifier(definition.name)}"
            for variant in definition.variants:
                pattern = "(..)" if variant.payload_types else ""
                arms.append(
                    f"{type_name}::{_identifier(variant.name)}{pattern} => String::from({json.dumps(variant.name)})"
                )
            return "match &" + self._operand(value.operand) + " { " + ", ".join(arms) + " }"
        if isinstance(value, PayloadRValue):
            operand_type = self._operand_type(value.operand)
            if operand_type.name == "Result" and len(operand_type.arguments) == 2:
                ok_type, err_type = operand_type.arguments
                arms = []
                if ok_type == value.type:
                    arms.append("Ok(rove_payload) => rove_payload")
                else:
                    arms.append("Ok(_) => panic!(\"Result payload variant mismatch\")")
                if err_type == value.type:
                    arms.append("Err(rove_payload) => rove_payload")
                else:
                    arms.append("Err(_) => panic!(\"Result payload variant mismatch\")")
                return "match " + self._operand(value.operand) + " { " + ", ".join(arms) + " }"
            definition = self.enums.get(operand_type.name)
            if definition is None:
                raise MIRCodegenError(f"Rust payload requires a known enum, got '{operand_type}'")
            type_name = f"RoveType_{_identifier(definition.name)}"
            arms = []
            for variant in definition.variants:
                if value.index >= len(variant.payload_types) or variant.payload_types[value.index] != value.type:
                    continue
                bindings = ["_" for _ in variant.payload_types]
                bindings[value.index] = "rove_payload"
                arms.append(
                    f"{type_name}::{_identifier(variant.name)}({', '.join(bindings)}) => rove_payload"
                )
            if not arms:
                raise MIRCodegenError(
                    f"enum '{definition.name}' has no payload {value.index} of type '{value.type}'"
                )
            return (
                "match " + self._operand(value.operand) + " { "
                + ", ".join(arms) + ", _ => panic!(\"enum payload mismatch\") }"
            )
        if isinstance(value, BorrowRValue):
            rendered = self._place(value.place, mutable=value.mutable)
            projected_reference = bool(value.place.projections) and isinstance(
                value.place.projections[-1], (DerefProjection, IndexProjection, ConstantIndexProjection)
            )
            if value.mutable:
                argument = rendered if projected_reference else f"&mut {rendered}"
                return f"RovePtr::borrow_mut({argument})"
            argument = rendered if projected_reference else f"&{rendered}"
            return f"RovePtr::borrow({argument})"
        if isinstance(value, UnaryRValue):
            operand = self._operand(value.operand)
            if value.op in ("!", "not"):
                return f"!({operand})"
            if value.op == "+":
                return operand
            if value.op == "-" and value.type.name == "int":
                return f"({operand}).wrapping_neg()"
            if value.op == "-":
                return f"-({operand})"
            if value.op == "~":
                return f"!({operand})"
            raise MIRCodegenError(f"unsupported Rust unary operation '{value.op}'")
        raise MIRCodegenError(f"illegal rvalue reached Rust emitter: {type(value).__name__}")

    def _binary(self, value: BinaryRValue) -> str:
        left = self._operand(value.left)
        right = self._operand(value.right)
        left_type = self._operand_type(value.left)
        right_type = self._operand_type(value.right)
        if value.op in ("==", "!=", "<", "<=", ">", ">="):
            return f"({left} {value.op} {right})"
        if value.op == "+" and (left_type.name == "string" or right_type.name == "string"):
            return f"format!(\"{{}}{{}}\", {left}, {right})"
        if left_type.name in ("float", "f64") or right_type.name in ("float", "f64"):
            if value.op in ("+", "-", "*", "/", "%"):
                return f"({left} {value.op} {right})"
        integer_operations = {
            "+": "wrapping_add", "-": "wrapping_sub", "*": "wrapping_mul",
        }
        if value.op in integer_operations:
            return f"({left}).{integer_operations[value.op]}({right})"
        if value.op == "/":
            return f"rove_i64_div({left}, {right})"
        if value.op == "%":
            return f"rove_i64_rem({left}, {right})"
        if value.op == "<<":
            return f"({left}).wrapping_shl(({right} as u32) & 63)"
        if value.op == ">>":
            return f"({left}).wrapping_shr(({right} as u32) & 63)"
        if value.op in ("&", "|", "^"):
            return f"({left} {value.op} {right})"
        raise MIRCodegenError(f"unsupported Rust binary operation '{value.op}'")

    def _result_cast(self, operand: str, source: MIRType, target: MIRType) -> str:
        source_ok, source_err = source.arguments
        target_ok, target_err = target.arguments
        ok_value = self._result_branch_cast("rove_ok", source_ok, target_ok, "Ok")
        err_value = self._result_branch_cast("rove_err", source_err, target_err, "Err")
        return (
            f"match {operand} {{ "
            f"Ok(rove_ok) => Ok({ok_value}), "
            f"Err(rove_err) => Err({err_value}) }}"
        )

    @staticmethod
    def _result_branch_cast(binding: str, source: MIRType, target: MIRType, tag: str) -> str:
        if source == target:
            return binding
        if source.name == "any":
            return f"panic!(\"invalid {tag} branch selected during Result re-homing\")"
        if target.name == "any":
            return "RoveAny"
        raise MIRCodegenError(
            f"Rust MIR Result cast cannot convert '{source}' to '{target}'"
        )

    def _operand(self, value: Operand) -> str:
        if isinstance(value, ConstOperand):
            return self._typed_constant(value)
        if isinstance(value, (CopyOperand, MoveOperand)):
            rendered = self._place(value.place)
            if isinstance(value, CopyOperand):
                return rendered + ".clone()"
            return self._take_place(value.place)
        raise MIRCodegenError(f"illegal operand reached Rust emitter: {type(value).__name__}")

    def _operand_type(self, value: Operand) -> MIRType:
        if isinstance(value, ConstOperand):
            return value.type
        if isinstance(value, (CopyOperand, MoveOperand)):
            return self._place_type(value.place)
        raise MIRCodegenError(f"unknown Rust operand type: {type(value).__name__}")

    @staticmethod
    def _typed_constant(value: ConstOperand) -> str:
        if value.type.optional and value.value is None:
            return "None"
        if value.type.name == "string":
            return f"String::from({json.dumps(str(value.value), ensure_ascii=False)})"
        if value.type.name == "bool":
            return "true" if value.value else "false"
        if value.type.name in ("float", "f64"):
            number = float(value.value)
            if math.isnan(number):
                return "f64::NAN"
            if math.isinf(number):
                return "f64::INFINITY" if number > 0 else "f64::NEG_INFINITY"
            return repr(number)
        return str(value.value)

    @staticmethod
    def _constant(value: object) -> str:
        if value is True:
            return "true"
        if value is False:
            return "false"
        if isinstance(value, str):
            return f"String::from({json.dumps(value, ensure_ascii=False)})"
        return str(value)

    @staticmethod
    def _type(value: MIRType, function: MIRFunction | None = None) -> str:
        if value.name == "any" and function is not None and function.name in ("main", "__nyx_top_level"):
            return "()"
        if value.optional:
            return f"Option<{_RustEmitter._type(replace(value, optional=False), function)}>"
        if value.pointer:
            return f"RovePtr<{_RustEmitter._type(replace(value, pointer=False), function)}>"
        if value.name == "Array" and len(value.arguments) == 1:
            return f"Vec<{_RustEmitter._type(value.arguments[0], function)}>"
        if value.name == "Task" and len(value.arguments) == 1:
            return f"RoveTask<{_RustEmitter._type(value.arguments[0], function)}>"
        if value.name == "Result" and len(value.arguments) == 2:
            return (
                f"Result<{_RustEmitter._type(value.arguments[0], function)}, "
                f"{_RustEmitter._type(value.arguments[1], function)}>"
            )
        mapping = {
            "void": "()", "any": "RoveAny", "bool": "bool", "int": "i64",
            "float": "f64", "f64": "f64", "string": "String",
        }
        rendered = mapping.get(value.name, f"RoveType_{_identifier(value.name)}")
        if value.arguments:
            raise MIRCodegenError(f"unsupported Rust MIR type '{value}'")
        return rendered

    @staticmethod
    def _default(value: MIRType) -> str:
        if value.optional:
            return "None"
        if value.pointer:
            return "Default::default()"
        if value.name == "Array":
            return "Vec::new()"
        if value.name == "Task":
            return "Default::default()"
        if value.name == "Result" and len(value.arguments) == 2:
            return "Ok(Default::default())"
        return {"bool": "false", "int": "0", "float": "0.0", "f64": "0.0", "string": "String::new()"}.get(value.name, "Default::default()")

    def _place(self, place: Place, *, mutable: bool = False) -> str:
        rendered = f"l{place.local}"
        value_type = self.local_types[place.local]
        for projection in place.projections:
            if value_type.optional:
                accessor = "as_mut" if mutable else "as_ref"
                rendered = f"({rendered}).{accessor}().expect(\"optional projection failed\")"
                value_type = replace(value_type, optional=False)
            if isinstance(projection, FieldProjection):
                rendered = f"({rendered}).{_identifier(projection.name)}"
                value_type = self._field_type(value_type, projection.name)
            elif isinstance(projection, ConstantIndexProjection):
                helper = "rove_index_mut" if mutable else "rove_index"
                borrow = "&mut " if mutable else "&"
                rendered = f"{helper}({borrow}{rendered}, {projection.index})"
                value_type = self._index_type(value_type)
            elif isinstance(projection, IndexProjection):
                helper = "rove_index_mut" if mutable else "rove_index"
                borrow = "&mut " if mutable else "&"
                rendered = f"{helper}({borrow}{rendered}, l{projection.local})"
                value_type = self._index_type(value_type)
            elif isinstance(projection, DerefProjection):
                if not value_type.pointer:
                    raise MIRCodegenError(f"dereference requires a pointer, got '{value_type}'")
                accessor = "write" if mutable else "read"
                rendered = f"unsafe {{ ({rendered}).{accessor}() }}"
                value_type = replace(value_type, pointer=False)
            else:
                raise MIRCodegenError(f"illegal projection reached Rust emitter: {type(projection).__name__}")
        return rendered

    def _assign_place(self, place: Place, value: str) -> str:
        rendered = self._place(place, mutable=True)
        prefix = "*" if place.projections and isinstance(
            place.projections[-1], (DerefProjection, IndexProjection, ConstantIndexProjection)
        ) else ""
        return f"{prefix}{rendered} = {value};"

    def _take_place(self, place: Place) -> str:
        rendered = self._place(place, mutable=True)
        replacement = self._default(self._place_type(place))
        if place.projections and isinstance(
            place.projections[-1], (DerefProjection, IndexProjection, ConstantIndexProjection)
        ):
            return f"std::mem::replace({rendered}, {replacement})"
        return f"std::mem::replace(&mut {rendered}, {replacement})"

    def _place_type(self, place: Place) -> MIRType:
        value_type = self.local_types[place.local]
        for projection in place.projections:
            if value_type.optional:
                value_type = replace(value_type, optional=False)
            if isinstance(projection, FieldProjection):
                value_type = self._field_type(value_type, projection.name)
            elif isinstance(projection, (ConstantIndexProjection, IndexProjection)):
                value_type = self._index_type(value_type)
            elif isinstance(projection, DerefProjection):
                if not value_type.pointer:
                    raise MIRCodegenError(f"dereference requires a pointer, got '{value_type}'")
                value_type = replace(value_type, pointer=False)
            else:
                raise MIRCodegenError(f"unknown Rust projection type: {type(projection).__name__}")
        return value_type

    def _field_type(self, value_type: MIRType, name: str) -> MIRType:
        definition = self.structs.get(value_type.name)
        if definition is None:
            raise MIRCodegenError(f"field projection requires a known struct, got '{value_type}'")
        field = next((item for item in definition.fields if item.name == name), None)
        if field is None:
            raise MIRCodegenError(f"struct '{definition.name}' has no field '{name}'")
        return field.type

    @staticmethod
    def _index_type(value_type: MIRType) -> MIRType:
        if value_type.name == "Array" and len(value_type.arguments) == 1:
            return value_type.arguments[0]
        raise MIRCodegenError(f"index projection requires Array<T>, got '{value_type}'")


def emit_legalized_rust(module: MIRModule) -> str:
    return _RustEmitter(legalize_mir(module, "rust", require_emitter=True)).emit()
