"""Executable WebAssembly emitter for the legalized MIR pilot."""

from __future__ import annotations

import re
import hashlib
import struct as binary_struct

from src.codegen.wasm_ir import DataSegment, F64, I32, I64, VOID, FunctionIR, Instruction, ModuleIR

from .codegen_cpp import MIRCodegenError
from .layout import LayoutEngine
from .legalization import legalize_mir
from .model import (
    AggregateRValue,
    AssertTerminator,
    AssignStatement,
    BinaryRValue,
    CallTerminator,
    CastRValue,
    ConstOperand,
    ConstantIndexProjection,
    CopyOperand,
    DeinitStatement,
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
    ReturnTerminator,
    StorageDeadStatement,
    StorageLiveStatement,
    SwitchIntTerminator,
    SwitchValueTerminator,
    UnaryRValue,
    UnreachableTerminator,
    UseRValue,
)
from .types import MIRType


def _identifier(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_]", "_", value)
    return clean if clean and not clean[0].isdigit() else "_" + clean


class _WasmEmitter:
    def __init__(self, module: MIRModule):
        self.module = module
        self.function_names = {
            function.symbol: _identifier(function.name) for function in module.functions
        }
        self.function_names.update({
            function.name: self.function_names[function.symbol] for function in module.functions
        })
        if len(set(self.function_names[function.symbol] for function in module.functions)) != len(module.functions):
            raise MIRCodegenError("MIR function names collide after WebAssembly identifier normalization")
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
        self.layouts = LayoutEngine(module, "wasm")
        self.data: list[DataSegment] = []
        self.string_literals: dict[str, int] = {}
        self.next_data_offset = 1024
        self.current: MIRFunction | None = None
        self.local_types: dict[int, MIRType] = {}
        self.local_names: dict[int, str] = {}
        self.tag_locals: dict[int, dict[str, int]] = {}
        self.owned_clone_helpers: dict[MIRType, FunctionIR | None] = {}

    def lower(self) -> ModuleIR:
        lowered = [self._function(function) for function in self.module.functions]
        assert all(helper is not None for helper in self.owned_clone_helpers.values())
        functions = (
            self._integer_runtime() + self._array_runtime() + self._string_runtime()
            + list(self.owned_clone_helpers.values()) + lowered
        )
        heap_start = max(2048, (self.next_data_offset + 7) & ~7)
        return ModuleIR(self.module.source_name, functions, self.data, heap_start)

    @staticmethod
    def _integer_runtime() -> list[FunctionIR]:
        minimum = -(1 << 63)
        common = [
            Instruction("local.get", "right"), Instruction("i64.eqz"),
            Instruction("if"), Instruction("unreachable"), Instruction("end"),
            Instruction("local.get", "left"), Instruction("i64.const", minimum), Instruction("i64.eq"),
            Instruction("local.get", "right"), Instruction("i64.const", -1), Instruction("i64.eq"),
            Instruction("i32.and"),
        ]
        divide = FunctionIR(
            "__rove_mir_div", [("left", I64), ("right", I64)], I64,
            body=common + [
                Instruction("if_result", I64), Instruction("i64.const", minimum), Instruction("else"),
                Instruction("local.get", "left"), Instruction("local.get", "right"),
                Instruction("i64.div_s"), Instruction("end"),
            ], export=False,
        )
        remainder = FunctionIR(
            "__rove_mir_rem", [("left", I64), ("right", I64)], I64,
            body=common + [
                Instruction("if_result", I64), Instruction("i64.const", 0), Instruction("else"),
                Instruction("local.get", "left"), Instruction("local.get", "right"),
                Instruction("i64.rem_s"), Instruction("end"),
            ], export=False,
        )
        return [divide, remainder]

    @staticmethod
    def _string_runtime() -> list[FunctionIR]:
        compare = FunctionIR(
            "rove_string_compare", [("left", I32), ("right", I32)], I32,
            locals=[
                ("left_data", I32), ("right_data", I32),
                ("left_length", I32), ("right_length", I32), ("index", I32),
                ("difference", I32),
            ],
            body=[
                Instruction("local.get", "left"), Instruction("i32.load"),
                Instruction("local.set", "left_data"),
                Instruction("local.get", "right"), Instruction("i32.load"),
                Instruction("local.set", "right_data"),
                Instruction("local.get", "left"), Instruction("i32.const", 4),
                Instruction("i32.add"), Instruction("i32.load"),
                Instruction("local.set", "left_length"),
                Instruction("local.get", "right"), Instruction("i32.const", 4),
                Instruction("i32.add"), Instruction("i32.load"),
                Instruction("local.set", "right_length"),
                Instruction("block", "rove_compare_done"),
                Instruction("loop", "rove_compare_next"),
                Instruction("local.get", "index"), Instruction("local.get", "left_length"),
                Instruction("i32.ge_s"), Instruction("br_if", "rove_compare_done"),
                Instruction("local.get", "index"), Instruction("local.get", "right_length"),
                Instruction("i32.ge_s"), Instruction("br_if", "rove_compare_done"),
                Instruction("local.get", "left_data"), Instruction("local.get", "index"),
                Instruction("i32.add"), Instruction("i32.load8_u"),
                Instruction("local.get", "right_data"), Instruction("local.get", "index"),
                Instruction("i32.add"), Instruction("i32.load8_u"),
                Instruction("i32.sub"), Instruction("local.tee", "difference"),
                Instruction("if"), Instruction("local.get", "difference"),
                Instruction("return"), Instruction("end"),
                Instruction("local.get", "index"), Instruction("i32.const", 1),
                Instruction("i32.add"), Instruction("local.set", "index"),
                Instruction("br", "rove_compare_next"),
                Instruction("end"), Instruction("end"),
                Instruction("local.get", "left_length"),
                Instruction("local.get", "right_length"), Instruction("i32.sub"),
                Instruction("return"),
            ],
            export=False,
        )
        concat = FunctionIR(
            "rove_string_concat", [("left", I32), ("right", I32)], I32,
            locals=[
                ("left_length", I32), ("right_length", I32),
                ("total", I32), ("descriptor", I32), ("data", I32),
            ],
            body=[
                Instruction("local.get", "left"), Instruction("i32.const", 4),
                Instruction("i32.add"), Instruction("i32.load"),
                Instruction("local.set", "left_length"),
                Instruction("local.get", "right"), Instruction("i32.const", 4),
                Instruction("i32.add"), Instruction("i32.load"),
                Instruction("local.set", "right_length"),
                Instruction("local.get", "left_length"), Instruction("local.get", "right_length"),
                Instruction("i32.add"), Instruction("local.tee", "total"),
                Instruction("i32.const", 0), Instruction("i32.lt_s"),
                Instruction("if"), Instruction("unreachable"), Instruction("end"),
                Instruction("i32.const", 12), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "descriptor"),
                Instruction("local.get", "total"), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "data"),
                Instruction("local.get", "descriptor"), Instruction("local.get", "data"),
                Instruction("i32.store"),
                Instruction("local.get", "descriptor"), Instruction("i32.const", 4),
                Instruction("i32.add"), Instruction("local.get", "total"),
                Instruction("i32.store"),
                Instruction("local.get", "descriptor"), Instruction("i32.const", 8),
                Instruction("i32.add"), Instruction("local.get", "total"),
                Instruction("i32.store"),
                Instruction("local.get", "data"), Instruction("local.get", "left"),
                Instruction("i32.load"), Instruction("local.get", "left_length"),
                Instruction("memory.copy"),
                Instruction("local.get", "data"), Instruction("local.get", "left_length"),
                Instruction("i32.add"), Instruction("local.get", "right"),
                Instruction("i32.load"), Instruction("local.get", "right_length"),
                Instruction("memory.copy"),
                Instruction("local.get", "descriptor"), Instruction("return"),
            ],
            export=False,
        )
        return [compare, concat]

    @staticmethod
    def _array_runtime() -> list[FunctionIR]:
        alloc = FunctionIR(
            "__rove_mir_alloc", [("size", I32)], I32,
            locals=[("old_ptr", I32), ("new_ptr", I32), ("current_bytes", I32), ("pages", I32)],
            body=[
                Instruction("local.get", "size"), Instruction("i32.const", 0), Instruction("i32.le_s"),
                Instruction("if"), Instruction("i32.const", 0), Instruction("return"), Instruction("end"),
                Instruction("global.get", "heap_ptr"), Instruction("local.tee", "old_ptr"),
                Instruction("local.get", "size"), Instruction("i32.add"), Instruction("i32.const", 7),
                Instruction("i32.add"), Instruction("i32.const", -8), Instruction("i32.and"),
                Instruction("local.tee", "new_ptr"), Instruction("local.get", "old_ptr"),
                Instruction("i32.lt_s"), Instruction("if"), Instruction("unreachable"), Instruction("end"),
                Instruction("memory.size"), Instruction("i32.const", 16), Instruction("i32.shl"),
                Instruction("local.tee", "current_bytes"), Instruction("local.get", "new_ptr"),
                Instruction("i32.lt_s"), Instruction("if"),
                Instruction("local.get", "new_ptr"), Instruction("local.get", "current_bytes"),
                Instruction("i32.sub"), Instruction("i32.const", 65535), Instruction("i32.add"),
                Instruction("i32.const", 16), Instruction("i32.shr_s"), Instruction("local.tee", "pages"),
                Instruction("memory.grow"), Instruction("i32.const", -1), Instruction("i32.eq"),
                Instruction("if"), Instruction("unreachable"), Instruction("end"), Instruction("end"),
                Instruction("local.get", "new_ptr"), Instruction("global.set", "heap_ptr"),
                Instruction("local.get", "old_ptr"), Instruction("return"),
            ],
            export=False,
        )
        clone = FunctionIR(
            "__rove_mir_array_clone_i64", [("desc", I32)], I32,
            locals=[("new_desc", I32), ("new_data", I32), ("len", I32), ("bytes", I32)],
            body=[
                Instruction("local.get", "desc"), Instruction("i32.eqz"), Instruction("if"),
                Instruction("i32.const", 0), Instruction("return"), Instruction("end"),
                Instruction("local.get", "desc"), Instruction("i32.const", 4), Instruction("i32.add"),
                Instruction("i32.load"), Instruction("local.tee", "len"), Instruction("i32.const", 8),
                Instruction("i32.mul"), Instruction("local.set", "bytes"),
                Instruction("i32.const", 12), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_desc"),
                Instruction("local.get", "bytes"), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_data"),
                Instruction("local.get", "new_data"), Instruction("local.get", "desc"),
                Instruction("i32.load"), Instruction("local.get", "bytes"), Instruction("memory.copy"),
                Instruction("local.get", "new_desc"), Instruction("local.get", "new_data"),
                Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 4), Instruction("i32.add"),
                Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 8), Instruction("i32.add"),
                Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("return"),
            ],
            export=False,
        )
        clone_i32 = FunctionIR(
            "__rove_mir_array_clone_i32", [("desc", I32)], I32,
            locals=[("new_desc", I32), ("new_data", I32), ("len", I32), ("bytes", I32)],
            body=[
                Instruction("local.get", "desc"), Instruction("i32.eqz"), Instruction("if"),
                Instruction("i32.const", 0), Instruction("return"), Instruction("end"),
                Instruction("local.get", "desc"), Instruction("i32.const", 4), Instruction("i32.add"),
                Instruction("i32.load"), Instruction("local.tee", "len"), Instruction("i32.const", 4),
                Instruction("i32.mul"), Instruction("local.set", "bytes"),
                Instruction("i32.const", 12), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_desc"),
                Instruction("local.get", "bytes"), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_data"),
                Instruction("local.get", "new_data"), Instruction("local.get", "desc"),
                Instruction("i32.load"), Instruction("local.get", "bytes"), Instruction("memory.copy"),
                Instruction("local.get", "new_desc"), Instruction("local.get", "new_data"),
                Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 4), Instruction("i32.add"),
                Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 8), Instruction("i32.add"),
                Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("return"),
            ],
            export=False,
        )
        clone_string = FunctionIR(
            "__rove_mir_array_clone_string", [("desc", I32)], I32,
            locals=[("new_desc", I32), ("new_data", I32), ("len", I32), ("bytes", I32)],
            body=[
                Instruction("local.get", "desc"), Instruction("i32.eqz"), Instruction("if"),
                Instruction("i32.const", 0), Instruction("return"), Instruction("end"),
                Instruction("local.get", "desc"), Instruction("i32.const", 4), Instruction("i32.add"),
                Instruction("i32.load"), Instruction("local.tee", "len"), Instruction("i32.const", 12),
                Instruction("i32.mul"), Instruction("local.set", "bytes"),
                Instruction("i32.const", 12), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_desc"),
                Instruction("local.get", "bytes"), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_data"),
                Instruction("local.get", "new_data"), Instruction("local.get", "desc"),
                Instruction("i32.load"), Instruction("local.get", "bytes"), Instruction("memory.copy"),
                Instruction("local.get", "new_desc"), Instruction("local.get", "new_data"),
                Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 4), Instruction("i32.add"),
                Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 8), Instruction("i32.add"),
                Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("return"),
            ],
            export=False,
        )
        clone_blob = FunctionIR(
            "__rove_mir_array_clone_blob", [("desc", I32), ("element_size", I32)], I32,
            locals=[("new_desc", I32), ("new_data", I32), ("len", I32), ("bytes", I32)],
            body=[
                Instruction("local.get", "desc"), Instruction("i32.eqz"), Instruction("if"),
                Instruction("i32.const", 0), Instruction("return"), Instruction("end"),
                Instruction("local.get", "desc"), Instruction("i32.const", 4), Instruction("i32.add"),
                Instruction("i32.load"), Instruction("local.tee", "len"),
                Instruction("local.get", "element_size"), Instruction("i32.mul"),
                Instruction("local.set", "bytes"),
                Instruction("i32.const", 12), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_desc"),
                Instruction("local.get", "bytes"), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_data"),
                Instruction("local.get", "new_data"), Instruction("local.get", "desc"),
                Instruction("i32.load"), Instruction("local.get", "bytes"), Instruction("memory.copy"),
                Instruction("local.get", "new_desc"), Instruction("local.get", "new_data"),
                Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 4), Instruction("i32.add"),
                Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 8), Instruction("i32.add"),
                Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("return"),
            ],
            export=False,
        )
        clone_nested_i64 = FunctionIR(
            "__rove_mir_array_clone_nested_i64", [("desc", I32)], I32,
            locals=[
                ("new_desc", I32), ("new_data", I32), ("len", I32),
                ("bytes", I32), ("i", I32), ("source_element", I32),
                ("cloned_element", I32),
            ],
            body=[
                Instruction("local.get", "desc"), Instruction("i32.eqz"), Instruction("if"),
                Instruction("i32.const", 0), Instruction("return"), Instruction("end"),
                Instruction("local.get", "desc"), Instruction("i32.const", 4), Instruction("i32.add"),
                Instruction("i32.load"), Instruction("local.tee", "len"), Instruction("i32.const", 12),
                Instruction("i32.mul"), Instruction("local.set", "bytes"),
                Instruction("i32.const", 12), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_desc"),
                Instruction("local.get", "bytes"), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_data"),
                Instruction("local.get", "new_desc"), Instruction("local.get", "new_data"),
                Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 4), Instruction("i32.add"),
                Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 8), Instruction("i32.add"),
                Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("i32.const", 0), Instruction("local.set", "i"),
                Instruction("block", "nested_clone_break"),
                Instruction("loop", "nested_clone_loop"),
                Instruction("local.get", "i"), Instruction("local.get", "len"),
                Instruction("i32.ge_s"), Instruction("br_if", "nested_clone_break"),
                Instruction("local.get", "desc"), Instruction("i32.load"),
                Instruction("local.get", "i"), Instruction("i32.const", 12),
                Instruction("i32.mul"), Instruction("i32.add"),
                Instruction("local.tee", "source_element"),
                Instruction("call", "__rove_mir_array_clone_i64"),
                Instruction("local.set", "cloned_element"),
                Instruction("local.get", "new_data"), Instruction("local.get", "i"),
                Instruction("i32.const", 12), Instruction("i32.mul"), Instruction("i32.add"),
                Instruction("local.get", "cloned_element"), Instruction("i32.const", 12),
                Instruction("memory.copy"),
                Instruction("local.get", "i"), Instruction("i32.const", 1), Instruction("i32.add"),
                Instruction("local.set", "i"), Instruction("br", "nested_clone_loop"),
                Instruction("end"), Instruction("end"),
                Instruction("local.get", "new_desc"), Instruction("return"),
            ],
            export=False,
        )
        clone_nested_i32 = FunctionIR(
            "__rove_mir_array_clone_nested_i32", [("desc", I32)], I32,
            locals=[
                ("new_desc", I32), ("new_data", I32), ("len", I32),
                ("bytes", I32), ("i", I32), ("source_element", I32),
                ("cloned_element", I32),
            ],
            body=[
                Instruction("local.get", "desc"), Instruction("i32.eqz"), Instruction("if"),
                Instruction("i32.const", 0), Instruction("return"), Instruction("end"),
                Instruction("local.get", "desc"), Instruction("i32.const", 4), Instruction("i32.add"),
                Instruction("i32.load"), Instruction("local.tee", "len"), Instruction("i32.const", 12),
                Instruction("i32.mul"), Instruction("local.set", "bytes"),
                Instruction("i32.const", 12), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_desc"),
                Instruction("local.get", "bytes"), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_data"),
                Instruction("local.get", "new_desc"), Instruction("local.get", "new_data"),
                Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 4), Instruction("i32.add"),
                Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 8), Instruction("i32.add"),
                Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("i32.const", 0), Instruction("local.set", "i"),
                Instruction("block", "nested_clone_break"),
                Instruction("loop", "nested_clone_loop"),
                Instruction("local.get", "i"), Instruction("local.get", "len"),
                Instruction("i32.ge_s"), Instruction("br_if", "nested_clone_break"),
                Instruction("local.get", "desc"), Instruction("i32.load"),
                Instruction("local.get", "i"), Instruction("i32.const", 12),
                Instruction("i32.mul"), Instruction("i32.add"),
                Instruction("local.tee", "source_element"),
                Instruction("call", "__rove_mir_array_clone_i32"),
                Instruction("local.set", "cloned_element"),
                Instruction("local.get", "new_data"), Instruction("local.get", "i"),
                Instruction("i32.const", 12), Instruction("i32.mul"), Instruction("i32.add"),
                Instruction("local.get", "cloned_element"), Instruction("i32.const", 12),
                Instruction("memory.copy"),
                Instruction("local.get", "i"), Instruction("i32.const", 1), Instruction("i32.add"),
                Instruction("local.set", "i"), Instruction("br", "nested_clone_loop"),
                Instruction("end"), Instruction("end"),
                Instruction("local.get", "new_desc"), Instruction("return"),
            ],
            export=False,
        )
        clone_nested_string = FunctionIR(
            "__rove_mir_array_clone_nested_string", [("desc", I32)], I32,
            locals=[
                ("new_desc", I32), ("new_data", I32), ("len", I32),
                ("bytes", I32), ("i", I32), ("source_element", I32),
                ("cloned_element", I32),
            ],
            body=[
                Instruction("local.get", "desc"), Instruction("i32.eqz"), Instruction("if"),
                Instruction("i32.const", 0), Instruction("return"), Instruction("end"),
                Instruction("local.get", "desc"), Instruction("i32.const", 4), Instruction("i32.add"),
                Instruction("i32.load"), Instruction("local.tee", "len"), Instruction("i32.const", 12),
                Instruction("i32.mul"), Instruction("local.set", "bytes"),
                Instruction("i32.const", 12), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_desc"),
                Instruction("local.get", "bytes"), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_data"),
                Instruction("local.get", "new_desc"), Instruction("local.get", "new_data"),
                Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 4), Instruction("i32.add"),
                Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 8), Instruction("i32.add"),
                Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("i32.const", 0), Instruction("local.set", "i"),
                Instruction("block", "nested_clone_break"),
                Instruction("loop", "nested_clone_loop"),
                Instruction("local.get", "i"), Instruction("local.get", "len"),
                Instruction("i32.ge_s"), Instruction("br_if", "nested_clone_break"),
                Instruction("local.get", "desc"), Instruction("i32.load"),
                Instruction("local.get", "i"), Instruction("i32.const", 12),
                Instruction("i32.mul"), Instruction("i32.add"),
                Instruction("local.tee", "source_element"),
                Instruction("call", "__rove_mir_array_clone_string"),
                Instruction("local.set", "cloned_element"),
                Instruction("local.get", "new_data"), Instruction("local.get", "i"),
                Instruction("i32.const", 12), Instruction("i32.mul"), Instruction("i32.add"),
                Instruction("local.get", "cloned_element"), Instruction("i32.const", 12),
                Instruction("memory.copy"),
                Instruction("local.get", "i"), Instruction("i32.const", 1), Instruction("i32.add"),
                Instruction("local.set", "i"), Instruction("br", "nested_clone_loop"),
                Instruction("end"), Instruction("end"),
                Instruction("local.get", "new_desc"), Instruction("return"),
            ],
            export=False,
        )
        clone_nested_blob = FunctionIR(
            "__rove_mir_array_clone_nested_blob", [("desc", I32), ("element_size", I32)], I32,
            locals=[
                ("new_desc", I32), ("new_data", I32), ("len", I32),
                ("bytes", I32), ("i", I32), ("source_element", I32),
                ("cloned_element", I32),
            ],
            body=[
                Instruction("local.get", "desc"), Instruction("i32.eqz"), Instruction("if"),
                Instruction("i32.const", 0), Instruction("return"), Instruction("end"),
                Instruction("local.get", "desc"), Instruction("i32.const", 4), Instruction("i32.add"),
                Instruction("i32.load"), Instruction("local.tee", "len"), Instruction("i32.const", 12),
                Instruction("i32.mul"), Instruction("local.set", "bytes"),
                Instruction("i32.const", 12), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_desc"),
                Instruction("local.get", "bytes"), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_data"),
                Instruction("local.get", "new_desc"), Instruction("local.get", "new_data"),
                Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 4), Instruction("i32.add"),
                Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 8), Instruction("i32.add"),
                Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("i32.const", 0), Instruction("local.set", "i"),
                Instruction("block", "nested_clone_break"),
                Instruction("loop", "nested_clone_loop"),
                Instruction("local.get", "i"), Instruction("local.get", "len"),
                Instruction("i32.ge_s"), Instruction("br_if", "nested_clone_break"),
                Instruction("local.get", "desc"), Instruction("i32.load"),
                Instruction("local.get", "i"), Instruction("i32.const", 12),
                Instruction("i32.mul"), Instruction("i32.add"),
                Instruction("local.tee", "source_element"),
                Instruction("local.get", "element_size"),
                Instruction("call", "__rove_mir_array_clone_blob"),
                Instruction("local.set", "cloned_element"),
                Instruction("local.get", "new_data"), Instruction("local.get", "i"),
                Instruction("i32.const", 12), Instruction("i32.mul"), Instruction("i32.add"),
                Instruction("local.get", "cloned_element"), Instruction("i32.const", 12),
                Instruction("memory.copy"),
                Instruction("local.get", "i"), Instruction("i32.const", 1), Instruction("i32.add"),
                Instruction("local.set", "i"), Instruction("br", "nested_clone_loop"),
                Instruction("end"), Instruction("end"),
                Instruction("local.get", "new_desc"), Instruction("return"),
            ],
            export=False,
        )
        clone_recursive = FunctionIR(
            "__rove_mir_array_clone_recursive",
            [("desc", I32), ("depth", I32), ("element_size", I32)], I32,
            locals=[
                ("new_desc", I32), ("new_data", I32), ("len", I32),
                ("bytes", I32), ("i", I32), ("source_element", I32),
                ("cloned_element", I32),
            ],
            body=[
                Instruction("local.get", "depth"), Instruction("i32.eqz"), Instruction("if"),
                Instruction("local.get", "desc"), Instruction("local.get", "element_size"),
                Instruction("call", "__rove_mir_array_clone_blob"), Instruction("return"),
                Instruction("end"),
                Instruction("local.get", "desc"), Instruction("i32.eqz"), Instruction("if"),
                Instruction("i32.const", 0), Instruction("return"), Instruction("end"),
                Instruction("local.get", "desc"), Instruction("i32.const", 4), Instruction("i32.add"),
                Instruction("i32.load"), Instruction("local.tee", "len"),
                Instruction("i32.const", 0), Instruction("i32.lt_s"),
                Instruction("local.get", "len"), Instruction("i32.const", 178956970),
                Instruction("i32.gt_s"), Instruction("i32.or"),
                Instruction("if"), Instruction("unreachable"), Instruction("end"),
                Instruction("local.get", "len"), Instruction("i32.const", 12),
                Instruction("i32.mul"), Instruction("local.set", "bytes"),
                Instruction("i32.const", 12), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_desc"),
                Instruction("local.get", "bytes"), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "new_data"),
                Instruction("local.get", "new_desc"), Instruction("local.get", "new_data"),
                Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 4),
                Instruction("i32.add"), Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("local.get", "new_desc"), Instruction("i32.const", 8),
                Instruction("i32.add"), Instruction("local.get", "len"), Instruction("i32.store"),
                Instruction("i32.const", 0), Instruction("local.set", "i"),
                Instruction("block", "recursive_clone_break"),
                Instruction("loop", "recursive_clone_loop"),
                Instruction("local.get", "i"), Instruction("local.get", "len"),
                Instruction("i32.ge_s"), Instruction("br_if", "recursive_clone_break"),
                Instruction("local.get", "desc"), Instruction("i32.load"),
                Instruction("local.get", "i"), Instruction("i32.const", 12),
                Instruction("i32.mul"), Instruction("i32.add"),
                Instruction("local.set", "source_element"),
                Instruction("local.get", "source_element"),
                Instruction("local.get", "depth"), Instruction("i32.const", 1),
                Instruction("i32.sub"), Instruction("local.get", "element_size"),
                Instruction("call", "__rove_mir_array_clone_recursive"),
                Instruction("local.set", "cloned_element"),
                Instruction("local.get", "new_data"), Instruction("local.get", "i"),
                Instruction("i32.const", 12), Instruction("i32.mul"), Instruction("i32.add"),
                Instruction("local.get", "cloned_element"), Instruction("i32.const", 12),
                Instruction("memory.copy"),
                Instruction("local.get", "i"), Instruction("i32.const", 1),
                Instruction("i32.add"), Instruction("local.set", "i"),
                Instruction("br", "recursive_clone_loop"),
                Instruction("end"), Instruction("end"),
                Instruction("local.get", "new_desc"), Instruction("return"),
            ],
            export=False,
        )
        get = FunctionIR(
            "__rove_mir_array_get_i64", [("desc", I32), ("index", I64)], I64,
            body=[
                Instruction("local.get", "desc"), Instruction("i32.eqz"),
                Instruction("if"), Instruction("unreachable"), Instruction("end"),
                Instruction("local.get", "index"), Instruction("i64.const", 0), Instruction("i64.lt_s"),
                Instruction("local.get", "index"), Instruction("local.get", "desc"),
                Instruction("i32.const", 4), Instruction("i32.add"), Instruction("i32.load"),
                Instruction("i64.extend_i32_u"), Instruction("i64.ge_s"), Instruction("i32.or"),
                Instruction("if"), Instruction("unreachable"), Instruction("end"),
                Instruction("local.get", "desc"), Instruction("i32.load"),
                Instruction("local.get", "index"), Instruction("i32.wrap_i64"),
                Instruction("i32.const", 8), Instruction("i32.mul"), Instruction("i32.add"),
                Instruction("i64.load"), Instruction("return"),
            ],
            export=False,
        )
        set_value = FunctionIR(
            "__rove_mir_array_set_i64", [("desc", I32), ("index", I64), ("value", I64)], VOID,
            body=[
                Instruction("local.get", "desc"), Instruction("i32.eqz"),
                Instruction("if"), Instruction("unreachable"), Instruction("end"),
                Instruction("local.get", "index"), Instruction("i64.const", 0), Instruction("i64.lt_s"),
                Instruction("local.get", "index"), Instruction("local.get", "desc"),
                Instruction("i32.const", 4), Instruction("i32.add"), Instruction("i32.load"),
                Instruction("i64.extend_i32_u"), Instruction("i64.ge_s"), Instruction("i32.or"),
                Instruction("if"), Instruction("unreachable"), Instruction("end"),
                Instruction("local.get", "desc"), Instruction("i32.load"),
                Instruction("local.get", "index"), Instruction("i32.wrap_i64"),
                Instruction("i32.const", 8), Instruction("i32.mul"), Instruction("i32.add"),
                Instruction("local.get", "value"), Instruction("i64.store"), Instruction("return"),
            ],
            export=False,
        )
        get_i32 = FunctionIR(
            "__rove_mir_array_get_i32", [("desc", I32), ("index", I64)], I32,
            body=[
                Instruction("local.get", "desc"), Instruction("i32.eqz"),
                Instruction("if"), Instruction("unreachable"), Instruction("end"),
                Instruction("local.get", "index"), Instruction("i64.const", 0), Instruction("i64.lt_s"),
                Instruction("local.get", "index"), Instruction("local.get", "desc"),
                Instruction("i32.const", 4), Instruction("i32.add"), Instruction("i32.load"),
                Instruction("i64.extend_i32_u"), Instruction("i64.ge_s"), Instruction("i32.or"),
                Instruction("if"), Instruction("unreachable"), Instruction("end"),
                Instruction("local.get", "desc"), Instruction("i32.load"),
                Instruction("local.get", "index"), Instruction("i32.wrap_i64"),
                Instruction("i32.const", 4), Instruction("i32.mul"), Instruction("i32.add"),
                Instruction("i32.load"), Instruction("return"),
            ],
            export=False,
        )
        set_i32 = FunctionIR(
            "__rove_mir_array_set_i32", [("desc", I32), ("index", I64), ("value", I32)], VOID,
            body=[
                Instruction("local.get", "desc"), Instruction("local.get", "index"),
                Instruction("i32.const", 4), Instruction("call", "__rove_mir_array_get_blob"),
                Instruction("local.get", "value"), Instruction("i32.store"), Instruction("return"),
            ],
            export=False,
        )
        get_string = FunctionIR(
            "__rove_mir_array_get_string", [("desc", I32), ("index", I64)], I32,
            body=[
                Instruction("local.get", "desc"), Instruction("i32.eqz"),
                Instruction("if"), Instruction("unreachable"), Instruction("end"),
                Instruction("local.get", "index"), Instruction("i64.const", 0), Instruction("i64.lt_s"),
                Instruction("local.get", "index"), Instruction("local.get", "desc"),
                Instruction("i32.const", 4), Instruction("i32.add"), Instruction("i32.load"),
                Instruction("i64.extend_i32_u"), Instruction("i64.ge_s"), Instruction("i32.or"),
                Instruction("if"), Instruction("unreachable"), Instruction("end"),
                Instruction("local.get", "desc"), Instruction("i32.load"),
                Instruction("local.get", "index"), Instruction("i32.wrap_i64"),
                Instruction("i32.const", 12), Instruction("i32.mul"), Instruction("i32.add"),
                Instruction("return"),
            ],
            export=False,
        )
        set_string = FunctionIR(
            "__rove_mir_array_set_string", [("desc", I32), ("index", I64), ("value", I32)], VOID,
            body=[
                Instruction("local.get", "desc"), Instruction("local.get", "index"),
                Instruction("call", "__rove_mir_array_get_string"),
                Instruction("local.get", "value"), Instruction("i32.const", 12),
                Instruction("memory.copy"), Instruction("return"),
            ],
            export=False,
        )
        get_blob = FunctionIR(
            "__rove_mir_array_get_blob", [("desc", I32), ("index", I64), ("element_size", I32)], I32,
            body=[
                Instruction("local.get", "desc"), Instruction("i32.eqz"),
                Instruction("if"), Instruction("unreachable"), Instruction("end"),
                Instruction("local.get", "index"), Instruction("i64.const", 0), Instruction("i64.lt_s"),
                Instruction("local.get", "index"), Instruction("local.get", "desc"),
                Instruction("i32.const", 4), Instruction("i32.add"), Instruction("i32.load"),
                Instruction("i64.extend_i32_u"), Instruction("i64.ge_s"), Instruction("i32.or"),
                Instruction("if"), Instruction("unreachable"), Instruction("end"),
                Instruction("local.get", "desc"), Instruction("i32.load"),
                Instruction("local.get", "index"), Instruction("i32.wrap_i64"),
                Instruction("local.get", "element_size"), Instruction("i32.mul"), Instruction("i32.add"),
                Instruction("return"),
            ],
            export=False,
        )
        set_blob = FunctionIR(
            "__rove_mir_array_set_blob",
            [("desc", I32), ("index", I64), ("value", I32), ("element_size", I32)], VOID,
            body=[
                Instruction("local.get", "desc"), Instruction("local.get", "index"),
                Instruction("local.get", "element_size"), Instruction("call", "__rove_mir_array_get_blob"),
                Instruction("local.get", "value"), Instruction("local.get", "element_size"),
                Instruction("memory.copy"), Instruction("return"),
            ],
            export=False,
        )
        clone_bytes = FunctionIR(
            "__rove_mir_clone_bytes", [("ptr", I32), ("size", I32)], I32,
            locals=[("new_ptr", I32)],
            body=[
                Instruction("local.get", "ptr"), Instruction("i32.eqz"), Instruction("if"),
                Instruction("i32.const", 0), Instruction("return"), Instruction("end"),
                Instruction("local.get", "size"), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.tee", "new_ptr"), Instruction("local.get", "ptr"),
                Instruction("local.get", "size"), Instruction("memory.copy"),
                Instruction("local.get", "new_ptr"), Instruction("return"),
            ],
            export=False,
        )
        return [
            alloc, clone, clone_i32, clone_string, clone_blob, clone_nested_i64,
            clone_nested_i32, clone_nested_string, clone_nested_blob,
            clone_recursive, get, set_value,
            get_i32, set_i32, get_string, set_string, get_blob, set_blob, clone_bytes,
        ]

    def _function(self, function: MIRFunction) -> FunctionIR:
        self.current = function
        self.local_types = {local.id: local.type for local in function.locals}
        self.local_names = {local.id: f"l{local.id}" for local in function.locals}
        self.tag_locals = self._discriminant_locals(function)
        result = self._type(function.locals[function.return_local].type, function)
        params = [
            (self.local_names[local], self._local_type(local, function))
            for local in function.parameters
        ]
        parameter_ids = set(function.parameters)
        locals_ = [
            (self.local_names[local.id], self._local_type(local.id, function))
            for local in function.locals
            if local.id not in parameter_ids and self._local_type(local.id, function) != VOID
        ]
        locals_.append(("pc", I32))
        if any(local.type.name == "Array" for local in function.locals):
            locals_.extend((("__rove_array_desc", I32), ("__rove_array_data", I32)))
        if any(self._is_memory_aggregate(local.type) for local in function.locals):
            locals_.append(("__rove_struct_ptr", I32))
        if any(self._is_result_compatible(local.type) for local in function.locals):
            locals_.append(("__rove_cast_source", I32))
        body = [Instruction("i32.const", function.blocks[0].id), Instruction("local.set", "pc")]
        body.extend((Instruction("block", "function_exit"), Instruction("loop", "dispatch")))
        for block in function.blocks:
            body.extend((
                Instruction("local.get", "pc"),
                Instruction("i32.const", block.id),
                Instruction("i32.eq"),
                Instruction("if"),
            ))
            for statement in block.statements:
                self._statement(statement, body)
            self._terminator(block.terminator, body)
            body.append(Instruction("end"))
        body.extend((Instruction("unreachable"), Instruction("end"), Instruction("end")))
        if result != VOID:
            body.append(Instruction("unreachable"))
        lowered = FunctionIR(self.function_names[function.symbol], params, result, locals_, body)
        self.current = None
        self.local_types = {}
        self.local_names = {}
        self.tag_locals = {}
        return lowered

    def _statement(self, statement: object, body: list[Instruction]) -> None:
        if isinstance(statement, AssignStatement):
            if statement.place.projections:
                if isinstance(
                    statement.place.projections[-1],
                    (IndexProjection, ConstantIndexProjection),
                ):
                    body.extend(self._array_place(statement.place))
                    parent_type = self._place_type(Place(
                        statement.place.local, statement.place.projections[:-1]
                    ))
                    element_type = parent_type.arguments[0]
                    if element_type.name in ("float", "f64"):
                        body.extend((
                            Instruction("i32.const", 8),
                            Instruction("call", "__rove_mir_array_get_blob"),
                        ))
                        body.extend(self._rvalue(statement.value))
                        body.append(Instruction("f64.store"))
                        return
                    body.extend(self._rvalue(statement.value))
                    if element_type.name in self.structs:
                        body.append(Instruction("i32.const", self.layouts.layout_of(element_type).size))
                        helper = "__rove_mir_array_set_blob"
                    elif element_type.name == "Array":
                        body.append(Instruction("i32.const", 12))
                        helper = "__rove_mir_array_set_blob"
                    else:
                        if element_type == MIRType("string"):
                            helper = "__rove_mir_array_set_string"
                        elif element_type == MIRType("bool"):
                            helper = "__rove_mir_array_set_i32"
                        else:
                            helper = "__rove_mir_array_set_i64"
                    body.append(Instruction("call", helper))
                    return
                body.extend(self._field_address(statement.place))
                body.extend(self._rvalue(statement.value))
                field_type = self._place_type(statement.place)
                if field_type == MIRType("string") or field_type.name in self.structs or field_type.name == "Array":
                    body.extend((
                        Instruction("i32.const", self.layouts.layout_of(field_type).size),
                        Instruction("memory.copy"),
                    ))
                else:
                    body.append(Instruction(self._store_instruction(field_type)))
                return
            body.extend(self._rvalue(statement.value))
            body.append(Instruction("local.set", self.local_names[statement.place.local]))
            return
        if isinstance(statement, (StorageLiveStatement, StorageDeadStatement, NopStatement)):
            return
        if isinstance(statement, DeinitStatement):
            self._clear_place(statement.place, body)
            return
        raise MIRCodegenError(f"illegal statement reached WebAssembly emitter: {type(statement).__name__}")

    def _terminator(self, value: object, body: list[Instruction]) -> None:
        if isinstance(value, GotoTerminator):
            self._goto(value.target, body)
            return
        if isinstance(value, SwitchIntTerminator):
            operand_type = self._operand_type(value.discriminator)
            for expected, target in value.targets:
                body.extend(self._operand(value.discriminator))
                body.append(Instruction(f"{self._type(operand_type)}.const", expected))
                body.append(Instruction(f"{self._type(operand_type)}.eq"))
                body.append(Instruction("if"))
                self._goto(target, body)
                body.append(Instruction("end"))
            self._goto(value.otherwise, body)
            return
        if isinstance(value, SwitchValueTerminator):
            local = (
                value.discriminator.place.local
                if isinstance(value.discriminator, (CopyOperand, MoveOperand))
                and not value.discriminator.place.projections
                else None
            )
            mapping = self.tag_locals.get(local if local is not None else -1)
            if mapping is None:
                raise MIRCodegenError("Wasm SwitchValue requires a legalized enum discriminant")
            for expected, target in value.targets:
                if expected not in mapping:
                    raise MIRCodegenError(f"Unknown Wasm enum discriminant '{expected}'")
                body.extend(self._operand(value.discriminator))
                body.append(Instruction("i32.const", mapping[expected]))
                body.append(Instruction("i32.eq"))
                body.append(Instruction("if"))
                self._goto(target, body)
                body.append(Instruction("end"))
            self._goto(value.otherwise, body)
            return
        if isinstance(value, CallTerminator):
            if value.target is None:
                raise MIRCodegenError(f"call '{value.function}' has no continuation")
            if value.function == "builtin::len":
                if len(value.arguments) != 1 or value.destination is None:
                    raise MIRCodegenError("builtin::len requires one argument and a destination")
                argument_type = self._operand_type(value.arguments[0])
                if argument_type.name not in ("Array", "string"):
                    raise MIRCodegenError("Wasm MIR builtin::len currently requires Array<int> or string")
                body.extend(self._operand(value.arguments[0]))
                body.extend((
                    Instruction("i32.const", 4), Instruction("i32.add"), Instruction("i32.load"),
                    Instruction("i64.extend_i32_u"),
                    Instruction("local.set", self.local_names[value.destination.local]),
                ))
                self._goto(value.target, body)
                return
            callee = self.functions.get(value.function)
            if callee is None:
                raise MIRCodegenError(f"runtime call '{value.function}' reached the pure WebAssembly pilot")
            for argument in value.arguments:
                body.extend(self._operand(argument))
            body.append(Instruction("call", self.function_names[value.function]))
            result_type = self._type(callee.locals[callee.return_local].type, callee)
            if value.destination is not None and result_type != VOID:
                body.append(Instruction("local.set", self.local_names[value.destination.local]))
            elif result_type != VOID:
                body.append(Instruction("drop"))
            self._goto(value.target, body)
            return
        if isinstance(value, AssertTerminator):
            body.extend(self._operand(value.condition))
            if value.expected:
                body.append(Instruction("i32.eqz"))
            body.extend((Instruction("if"), Instruction("unreachable"), Instruction("end")))
            self._goto(value.target, body)
            return
        if isinstance(value, DropTerminator):
            if value.unwind is not None:
                raise MIRCodegenError("Wasm MIR drop unwind edge was not legalized")
            self._clear_place(value.place, body)
            self._goto(value.target, body)
            return
        if isinstance(value, ReturnTerminator):
            assert self.current is not None
            result_type = self._type(self.current.locals[self.current.return_local].type, self.current)
            if result_type != VOID:
                body.append(Instruction("local.get", self.local_names[self.current.return_local]))
            body.append(Instruction("return"))
            return
        if isinstance(value, UnreachableTerminator):
            body.append(Instruction("unreachable"))
            return
        raise MIRCodegenError(f"illegal terminator reached WebAssembly emitter: {type(value).__name__}")

    def _clear_place(self, place: Place, body: list[Instruction]) -> None:
        if place.projections:
            value_type = self._place_type(place)
            if isinstance(place.projections[-1], (IndexProjection, ConstantIndexProjection)):
                parent_type = self._place_type(Place(
                    place.local, place.projections[:-1]
                ))
                element_type = parent_type.arguments[0]
                body.extend(self._array_place(place))
                if element_type == MIRType("string"):
                    body.extend((
                        Instruction("call", "__rove_mir_array_get_string"),
                        Instruction("i32.const", 0),
                        Instruction("i32.const", 12),
                        Instruction("memory.fill"),
                    ))
                    return
                if element_type.name in self.structs:
                    size = self.layouts.layout_of(element_type).size
                    body.extend((
                        Instruction("i32.const", size),
                        Instruction("call", "__rove_mir_array_get_blob"),
                        Instruction("i32.const", 0),
                        Instruction("i32.const", size),
                        Instruction("memory.fill"),
                    ))
                    return
                if element_type.name == "Array":
                    body.extend((
                        Instruction("i32.const", 12),
                        Instruction("call", "__rove_mir_array_get_blob"),
                        Instruction("i32.const", 0),
                        Instruction("i32.const", 12),
                        Instruction("memory.fill"),
                    ))
                    return
                if element_type == MIRType("bool"):
                    body.extend((
                        Instruction("i32.const", 0),
                        Instruction("call", "__rove_mir_array_set_i32"),
                    ))
                    return
                if element_type == MIRType("int"):
                    body.extend((
                        Instruction("i64.const", 0),
                        Instruction("call", "__rove_mir_array_set_i64"),
                    ))
                    return
                if element_type.name in ("float", "f64"):
                    body.extend((
                        Instruction("i32.const", 8),
                        Instruction("call", "__rove_mir_array_get_blob"),
                        Instruction("f64.const", 0.0), Instruction("f64.store"),
                    ))
                    return
                raise MIRCodegenError(
                    f"Wasm MIR cannot clear array element type '{element_type}'"
                )
            if isinstance(place.projections[-1], FieldProjection):
                body.extend(self._field_address(place))
                if value_type == MIRType("string"):
                    size = 12
                elif value_type.name in self.structs:
                    size = self.layouts.layout_of(value_type).size
                elif value_type.name == "Array":
                    size = 12
                else:
                    wasm_type = self._type(value_type, self.current)
                    if wasm_type == I64:
                        body.extend((Instruction("i64.const", 0), Instruction("i64.store")))
                    elif wasm_type == F64:
                        body.extend((Instruction("f64.const", 0.0), Instruction("f64.store")))
                    elif wasm_type == I32:
                        body.extend((
                            Instruction("i32.const", 0),
                            Instruction(self._store_instruction(value_type)),
                        ))
                    else:
                        raise MIRCodegenError(
                            f"Wasm MIR cannot clear projected value type '{value_type}'"
                        )
                    return
                body.extend((
                    Instruction("i32.const", 0),
                    Instruction("i32.const", size),
                    Instruction("memory.fill"),
                ))
                return
            raise MIRCodegenError("Wasm MIR deinit/drop requires a field or index projection")
        assert self.current is not None
        value_type = self.current.locals[place.local].type
        wasm_type = self._type(value_type, self.current)
        if wasm_type == I64:
            body.append(Instruction("i64.const", 0))
        elif wasm_type == F64:
            body.append(Instruction("f64.const", 0.0))
        elif wasm_type == I32:
            body.append(Instruction("i32.const", 0))
        else:
            raise MIRCodegenError(
                f"Wasm MIR cannot clear value type '{value_type}'"
            )
        body.append(Instruction("local.set", self.local_names[place.local]))

    @staticmethod
    def _goto(target: int, body: list[Instruction]) -> None:
        body.extend((
            Instruction("i32.const", target),
            Instruction("local.set", "pc"),
            Instruction("br", "dispatch"),
        ))

    def _rvalue(self, value: object) -> list[Instruction]:
        if isinstance(value, UseRValue):
            return self._operand(value.operand)
        if isinstance(value, CastRValue):
            source_type = self._operand_type(value.operand)
            if source_type == value.type:
                return self._operand(value.operand)
            if source_type == MIRType("int") and value.type.name in ("float", "f64"):
                return self._operand(value.operand) + [Instruction("f64.convert_i64_s")]
            if source_type.name in ("float", "f64") and value.type.name in ("float", "f64"):
                return self._operand(value.operand)
            if self._is_result_compatible(source_type) and self._is_result_compatible(value.type):
                source_layout = self.layouts.layout_of(source_type)
                target_layout = self.layouts.layout_of(value.type)
                if (
                    source_layout.size == target_layout.size
                    and source_layout.payload_offset == target_layout.payload_offset
                ):
                    return self._operand(value.operand)
                copy_bytes = min(
                    source_layout.size - source_layout.payload_offset,
                    target_layout.size - target_layout.payload_offset,
                )
                return self._operand(value.operand) + [
                    Instruction("local.set", "__rove_cast_source"),
                    Instruction("i32.const", target_layout.size), Instruction("call", "__rove_mir_alloc"),
                    Instruction("local.set", "__rove_struct_ptr"),
                    Instruction("local.get", "__rove_struct_ptr"),
                    Instruction("local.get", "__rove_cast_source"), Instruction("i32.load"),
                    Instruction("i32.store"),
                    Instruction("local.get", "__rove_struct_ptr"),
                    Instruction("i32.const", target_layout.payload_offset), Instruction("i32.add"),
                    Instruction("local.get", "__rove_cast_source"),
                    Instruction("i32.const", source_layout.payload_offset), Instruction("i32.add"),
                    Instruction("i32.const", copy_bytes), Instruction("memory.copy"),
                    Instruction("local.get", "__rove_struct_ptr"),
                ]
            raise MIRCodegenError(f"Wasm MIR cast '{source_type}' -> '{value.type}' is not legalized")
        if isinstance(value, AggregateRValue):
            if value.kind in ("enum", "result"):
                if value.kind == "enum":
                    definition = self.enums.get(value.type.name)
                    if definition is None:
                        raise MIRCodegenError(f"Unknown Wasm MIR enum '{value.type.name}'")
                    variant_index = next(
                        (index for index, variant in enumerate(definition.variants) if variant.name == value.name),
                        None,
                    )
                    if variant_index is None:
                        raise MIRCodegenError(f"Unknown Wasm MIR enum variant '{value.type.name}.{value.name}'")
                    payload_types = definition.variants[variant_index].payload_types
                else:
                    if not self._is_result_compatible(value.type):
                        raise MIRCodegenError("Wasm MIR result pilot requires scalar, string, or struct payloads")
                    if value.name not in ("Ok", "Err"):
                        raise MIRCodegenError(f"Unknown Wasm MIR Result variant '{value.name}'")
                    variant_index = 0 if value.name == "Ok" else 1
                    payload_types = (value.type.arguments[variant_index],)
                if len(value.operands) != len(payload_types):
                    raise MIRCodegenError(f"Wasm MIR enum payload arity mismatch for '{value.name}'")
                layout = self.layouts.layout_of(value.type)
                output = [
                    Instruction("i32.const", layout.size), Instruction("call", "__rove_mir_alloc"),
                    Instruction("local.set", "__rove_struct_ptr"),
                    Instruction("local.get", "__rove_struct_ptr"),
                    Instruction("i32.const", variant_index), Instruction("i32.store"),
                ]
                for index, (payload_type, operand) in enumerate(zip(payload_types, value.operands)):
                    if (
                        value.kind == "enum"
                        and payload_type not in (
                            MIRType("int"), MIRType("bool"), MIRType("float"),
                            MIRType("f64"), MIRType("string"),
                        )
                        and payload_type.name not in self.structs
                    ):
                        raise MIRCodegenError(
                            f"Wasm MIR enum payload '{value.type.name}.{value.name}[{index}]' is not int, bool, float, string, or struct"
                        )
                    if (
                        value.kind == "enum"
                        and payload_type != MIRType("int")
                        and len(payload_types) != 1
                    ):
                        raise MIRCodegenError("Wasm MIR non-int enum payload must be the variant's only payload")
                    if value.kind == "result" and payload_type not in (
                        MIRType("int"), MIRType("bool"), MIRType("float"),
                        MIRType("f64"), MIRType("string"),
                    ) and payload_type.name not in self.structs:
                        raise MIRCodegenError(
                            f"Wasm MIR Result payload '{value.name}' is not int, bool, float, string, or struct"
                        )
                    payload_offset = layout.payload_offset + (index * 8 if value.kind == "enum" else 0)
                    output.extend((
                        Instruction("local.get", "__rove_struct_ptr"),
                        Instruction("i32.const", payload_offset),
                        Instruction("i32.add"),
                    ))
                    output.extend(self._operand(operand))
                    if payload_type == MIRType("string") or payload_type.name in self.structs:
                        output.extend((
                            Instruction("i32.const", self.layouts.layout_of(payload_type).size),
                            Instruction("memory.copy"),
                        ))
                    else:
                        output.append(Instruction(self._store_instruction(payload_type)))
                output.append(Instruction("local.get", "__rove_struct_ptr"))
                return output
            if value.kind == "struct":
                definition = self.structs.get(value.type.name)
                if definition is None:
                    raise MIRCodegenError(f"Unknown Wasm MIR struct '{value.type.name}'")
                layout = self.layouts.layout_of(value.type)
                fields = value.fields or tuple(field.name for field in definition.fields)
                output = [
                    Instruction("i32.const", layout.size), Instruction("call", "__rove_mir_alloc"),
                    Instruction("local.set", "__rove_struct_ptr"),
                ]
                for name, operand in zip(fields, value.operands):
                    field = next((item for item in layout.fields if item.name == name), None)
                    if field is None or (
                        field.type not in (
                            MIRType("int"), MIRType("bool"), MIRType("float"),
                            MIRType("f64"), MIRType("string"),
                        )
                        and field.type.name not in self.structs
                        and field.type.name != "Array"
                    ):
                        raise MIRCodegenError(
                            f"Wasm MIR struct field '{value.type.name}.{name}' is not int, bool, float, string, array, or struct"
                        )
                    output.extend((
                        Instruction("local.get", "__rove_struct_ptr"),
                        Instruction("i32.const", field.offset), Instruction("i32.add"),
                    ))
                    output.extend(self._operand(operand))
                    if field.type == MIRType("string") or field.type.name in self.structs or field.type.name == "Array":
                        output.extend((
                            Instruction("i32.const", self.layouts.layout_of(field.type).size),
                            Instruction("memory.copy"),
                        ))
                    else:
                        output.append(Instruction(self._store_instruction(field.type)))
                output.append(Instruction("local.get", "__rove_struct_ptr"))
                return output
            if value.kind != "array" or value.type.name != "Array" or len(value.type.arguments) != 1:
                raise MIRCodegenError("Wasm MIR aggregate pilot requires Array<T>")
            element_type = value.type.arguments[0]
            if element_type.name in ("int", "float", "f64"):
                element_size = 8
            elif element_type == MIRType("bool"):
                element_size = 4
            elif element_type == MIRType("string") or element_type.name in self.structs:
                element_size = self.layouts.layout_of(element_type).size
            elif element_type.name == "Array" and len(element_type.arguments) == 1:
                element_size = 12
            else:
                raise MIRCodegenError(
                    "Wasm MIR aggregate pilot supports primitive, struct, and recursively nested array values"
                )
            output = [
                Instruction("i32.const", 12), Instruction("call", "__rove_mir_alloc"),
                Instruction("local.set", "__rove_array_desc"),
                Instruction("i32.const", len(value.operands) * element_size),
                Instruction("call", "__rove_mir_alloc"), Instruction("local.set", "__rove_array_data"),
                Instruction("local.get", "__rove_array_desc"),
                Instruction("local.get", "__rove_array_data"), Instruction("i32.store"),
            ]
            for offset in (4, 8):
                output.extend((
                    Instruction("local.get", "__rove_array_desc"), Instruction("i32.const", offset),
                    Instruction("i32.add"), Instruction("i32.const", len(value.operands)),
                    Instruction("i32.store"),
                ))
            for index, operand in enumerate(value.operands):
                output.extend((
                    Instruction("local.get", "__rove_array_data"),
                    Instruction("i32.const", index * element_size), Instruction("i32.add"),
                ))
                output.extend(self._operand(operand))
                if (
                    element_type == MIRType("string")
                    or element_type.name in self.structs
                    or element_type.name == "Array"
                ):
                    output.extend((Instruction("i32.const", element_size), Instruction("memory.copy")))
                elif element_type == MIRType("bool"):
                    output.append(Instruction("i32.store"))
                elif element_type.name in ("float", "f64"):
                    output.append(Instruction("f64.store"))
                else:
                    output.append(Instruction("i64.store"))
            output.append(Instruction("local.get", "__rove_array_desc"))
            return output
        if isinstance(value, DiscriminantRValue):
            return self._aggregate_subject(value.operand) + [Instruction("i32.load")]
        if isinstance(value, PayloadRValue):
            subject_type = self._operand_type(value.operand)
            if not self._is_tagged_aggregate(subject_type):
                raise MIRCodegenError("Wasm MIR payload pilot requires an enum or Result")
            if (
                value.type not in (
                    MIRType("int"), MIRType("bool"), MIRType("float"),
                    MIRType("f64"), MIRType("string"),
                )
                and value.type.name not in self.structs
            ):
                raise MIRCodegenError("Wasm MIR payload pilot requires an int, bool, float, string, or struct payload")
            if (
                subject_type.name in self.enums
                and value.type not in (
                    MIRType("int"), MIRType("bool"), MIRType("float"),
                    MIRType("f64"), MIRType("string"),
                )
                and value.type.name not in self.structs
            ):
                raise MIRCodegenError("Wasm MIR enum payload pilot requires an int, bool, float, string, or struct payload")
            if (
                subject_type.name in self.enums
                and value.type != MIRType("int")
                and value.index != 0
            ):
                raise MIRCodegenError("Wasm MIR non-int enum payload must be the first and only payload")
            layout = self.layouts.layout_of(subject_type)
            address = self._aggregate_subject(value.operand) + [
                Instruction("i32.const", layout.payload_offset + value.index * 8),
                Instruction("i32.add"),
            ]
            if value.type == MIRType("string"):
                return address
            if value.type.name in self.structs:
                return address + self._clone_value(value.type)
            return address + [Instruction(self._load_instruction(value.type))]
        if isinstance(value, BinaryRValue):
            left_type = self._operand_type(value.left)
            if left_type == MIRType("string"):
                if value.op == "+":
                    return self._operand(value.left) + self._operand(value.right) + [
                        Instruction("call", "rove_string_concat")
                    ]
                comparisons = {
                    "==": "eq", "!=": "ne", "<": "lt_s", "<=": "le_s",
                    ">": "gt_s", ">=": "ge_s",
                }
                operation = comparisons.get(value.op)
                if operation is not None:
                    return self._operand(value.left) + self._operand(value.right) + [
                        Instruction("call", "rove_string_compare"),
                        Instruction("i32.const", 0), Instruction(f"i32.{operation}"),
                    ]
                raise MIRCodegenError(f"unsupported Wasm string operation '{value.op}'")
            if left_type.name in ("float", "f64"):
                float_operations = {
                    "+": "add", "-": "sub", "*": "mul", "/": "div",
                    "==": "eq", "!=": "ne", "<": "lt", "<=": "le",
                    ">": "gt", ">=": "ge",
                }
                operation = float_operations.get(value.op)
                if operation is None:
                    raise MIRCodegenError(f"unsupported Wasm float operation '{value.op}'")
                return self._operand(value.left) + self._operand(value.right) + [
                    Instruction(f"f64.{operation}")
                ]
            wasm_type = self._type(left_type)
            operations = {
                "+": "add", "-": "sub", "*": "mul",
                "&": "and", "|": "or", "^": "xor", "<<": "shl", ">>": "shr_s",
                "==": "eq", "!=": "ne", "<": "lt_s", "<=": "le_s", ">": "gt_s", ">=": "ge_s",
            }
            operation = operations.get(value.op)
            if value.op in ("/", "%"):
                helper = "__rove_mir_div" if value.op == "/" else "__rove_mir_rem"
                return self._operand(value.left) + self._operand(value.right) + [Instruction("call", helper)]
            if operation is None:
                raise MIRCodegenError(f"unsupported WebAssembly binary operation '{value.op}'")
            return self._operand(value.left) + self._operand(value.right) + [
                Instruction(f"{wasm_type}.{operation}")
            ]
        if isinstance(value, UnaryRValue):
            operand = self._operand(value.operand)
            if value.op in ("!", "not"):
                return operand + [Instruction("i32.eqz")]
            if value.op == "+":
                return operand
            if value.op == "-":
                if self._operand_type(value.operand).name in ("float", "f64"):
                    return operand + [Instruction("f64.neg")]
                return [Instruction("i64.const", 0)] + operand + [Instruction("i64.sub")]
            if value.op == "~":
                return operand + [Instruction("i64.const", -1), Instruction("i64.xor")]
            raise MIRCodegenError(f"unsupported WebAssembly unary operation '{value.op}'")
        raise MIRCodegenError(f"illegal rvalue reached WebAssembly emitter: {type(value).__name__}")

    def _operand(self, value: Operand) -> list[Instruction]:
        if isinstance(value, ConstOperand):
            wasm_type = self._type(value.type)
            if value.type == MIRType("string"):
                return [Instruction("i32.const", self._intern_string(str(value.value)))]
            constant = int(value.value) if value.type.name == "bool" else value.value
            return [Instruction(f"{wasm_type}.const", constant)]
        if isinstance(value, (CopyOperand, MoveOperand)):
            if value.place.projections:
                if isinstance(
                    value.place.projections[-1],
                    (IndexProjection, ConstantIndexProjection),
                ):
                    parent_type = self._place_type(Place(
                        value.place.local, value.place.projections[:-1]
                    ))
                    element_type = parent_type.arguments[0]
                    output = self._array_place(value.place)
                    if element_type.name in self.structs:
                        output.extend((
                            Instruction("i32.const", self.layouts.layout_of(element_type).size),
                            Instruction("call", "__rove_mir_array_get_blob"),
                        ))
                        output.extend(self._clone_value(element_type))
                        return output
                    if element_type.name == "Array":
                        output.extend((
                            Instruction("i32.const", 12),
                            Instruction("call", "__rove_mir_array_get_blob"),
                        ))
                        output.extend(self._clone_value(element_type))
                        return output
                    if element_type == MIRType("string"):
                        helper = "__rove_mir_array_get_string"
                    elif element_type == MIRType("bool"):
                        helper = "__rove_mir_array_get_i32"
                    elif element_type.name in ("float", "f64"):
                        return output + [
                            Instruction("i32.const", 8),
                            Instruction("call", "__rove_mir_array_get_blob"),
                            Instruction("f64.load"),
                        ]
                    else:
                        helper = "__rove_mir_array_get_i64"
                    return output + [Instruction("call", helper)]
                field_type = self._place_type(value.place)
                address = self._field_address(value.place)
                if field_type.name in self.structs or field_type.name == "Array":
                    return address + self._clone_value(field_type)
                if field_type == MIRType("string"):
                    return address
                return address + [Instruction(self._load_instruction(field_type))]
            local_type = self.local_types[value.place.local]
            output = [Instruction("local.get", self.local_names[value.place.local])]
            if local_type.name == "Array" and isinstance(value, CopyOperand):
                output.extend(self._clone_value(local_type))
            elif local_type.name == "Array" and isinstance(value, MoveOperand):
                output.extend((
                    Instruction("i32.const", 0),
                    Instruction("local.set", self.local_names[value.place.local]),
                ))
            elif self._is_memory_aggregate(local_type):
                if isinstance(value, CopyOperand):
                    output.extend(self._clone_value(local_type))
                else:
                    output.extend((
                        Instruction("i32.const", 0),
                        Instruction("local.set", self.local_names[value.place.local]),
                    ))
            return output
        raise MIRCodegenError(f"illegal operand reached WebAssembly emitter: {type(value).__name__}")

    def _deep_array_clone(self, value_type: MIRType) -> list[Instruction]:
        depth = 0
        leaf = value_type
        while leaf.name == "Array" and len(leaf.arguments) == 1:
            depth += 1
            leaf = leaf.arguments[0]
        if depth < 2:
            raise MIRCodegenError(f"Wasm recursive array clone requires a nested Array, got '{value_type}'")
        element_size = 4 if leaf == MIRType("bool") else self.layouts.layout_of(leaf).size
        return [
            Instruction("i32.const", depth - 1),
            Instruction("i32.const", element_size),
            Instruction("call", "__rove_mir_array_clone_recursive"),
        ]

    def _struct_has_array(self, value_type: MIRType, seen: frozenset[str] = frozenset()) -> bool:
        if value_type.name not in self.structs or value_type.name in seen:
            return False
        definition = self.structs[value_type.name]
        return any(
            field.type.name == "Array"
            or self._struct_has_array(field.type, seen | {value_type.name})
            for field in definition.fields
        )

    def _array_needs_owned_clone(self, value_type: MIRType) -> bool:
        leaf = value_type
        while leaf.name == "Array" and len(leaf.arguments) == 1:
            leaf = leaf.arguments[0]
        return self._struct_has_array(leaf)

    def _tagged_owned_payloads(self, value_type: MIRType) -> tuple[tuple[int, MIRType], ...]:
        if value_type.name in self.enums:
            variants = (
                variant.payload_types for variant in self.enums[value_type.name].variants
            )
        elif self._is_result_compatible(value_type):
            variants = ((argument,) for argument in value_type.arguments)
        else:
            return ()
        return tuple(
            (index, payloads[0])
            for index, payloads in enumerate(variants)
            if len(payloads) == 1 and self._struct_has_array(payloads[0])
        )

    def _clone_value(self, value_type: MIRType) -> list[Instruction]:
        if value_type.name in self.structs:
            if self._struct_has_array(value_type):
                return [Instruction("call", self._ensure_owned_clone(value_type))]
            return [
                Instruction("i32.const", self.layouts.layout_of(value_type).size),
                Instruction("call", "__rove_mir_clone_bytes"),
            ]
        if self._is_tagged_aggregate(value_type):
            if self._tagged_owned_payloads(value_type):
                return [Instruction("call", self._ensure_owned_clone(value_type))]
            return [
                Instruction("i32.const", self.layouts.layout_of(value_type).size),
                Instruction("call", "__rove_mir_clone_bytes"),
            ]
        if value_type.name != "Array" or len(value_type.arguments) != 1:
            raise MIRCodegenError(f"Wasm MIR cannot clone aggregate '{value_type}'")
        if self._array_needs_owned_clone(value_type):
            return [Instruction("call", self._ensure_owned_clone(value_type))]
        element_type = value_type.arguments[0]
        if element_type.name == "Array":
            inner_type = element_type.arguments[0]
            if inner_type.name == "Array":
                return self._deep_array_clone(value_type)
            if inner_type == MIRType("string"):
                helper = "__rove_mir_array_clone_nested_string"
            elif inner_type == MIRType("bool"):
                helper = "__rove_mir_array_clone_nested_i32"
            elif inner_type.name in self.structs or inner_type.name in ("float", "f64"):
                return [
                    Instruction("i32.const", self.layouts.layout_of(inner_type).size),
                    Instruction("call", "__rove_mir_array_clone_nested_blob"),
                ]
            else:
                helper = "__rove_mir_array_clone_nested_i64"
            return [Instruction("call", helper)]
        if element_type == MIRType("string"):
            helper = "__rove_mir_array_clone_string"
        elif element_type == MIRType("bool"):
            helper = "__rove_mir_array_clone_i32"
        elif element_type.name in self.structs or element_type.name in ("float", "f64"):
            return [
                Instruction("i32.const", self.layouts.layout_of(element_type).size),
                Instruction("call", "__rove_mir_array_clone_blob"),
            ]
        else:
            helper = "__rove_mir_array_clone_i64"
        return [Instruction("call", helper)]

    def _ensure_owned_clone(self, value_type: MIRType) -> str:
        name = "__rove_mir_clone_owned_" + hashlib.sha256(
            str(value_type).encode("utf-8")
        ).hexdigest()[:12]
        if value_type in self.owned_clone_helpers:
            return name
        self.owned_clone_helpers[value_type] = None
        if value_type.name in self.structs:
            layout = self.layouts.layout_of(value_type)
            body = [
                Instruction("local.get", "source"), Instruction("i32.eqz"),
                Instruction("if"), Instruction("i32.const", 0),
                Instruction("return"), Instruction("end"),
                Instruction("local.get", "source"),
                Instruction("i32.const", layout.size),
                Instruction("call", "__rove_mir_clone_bytes"),
                Instruction("local.set", "copy"),
            ]
            for field in layout.fields:
                if field.type.name != "Array" and not self._struct_has_array(field.type):
                    continue
                body.extend((
                    Instruction("local.get", "copy"),
                    Instruction("i32.const", field.offset), Instruction("i32.add"),
                    Instruction("local.get", "source"),
                    Instruction("i32.const", field.offset), Instruction("i32.add"),
                ))
                body.extend(self._clone_value(field.type))
                body.extend((
                    Instruction("i32.const", self.layouts.layout_of(field.type).size),
                    Instruction("memory.copy"),
                ))
            body.extend((Instruction("local.get", "copy"), Instruction("return")))
            helper = FunctionIR(
                name, [("source", I32)], I32, locals=[("copy", I32)],
                body=body, export=False,
            )
        elif self._is_tagged_aggregate(value_type):
            layout = self.layouts.layout_of(value_type)
            body = [
                Instruction("local.get", "source"), Instruction("i32.eqz"),
                Instruction("if"), Instruction("i32.const", 0),
                Instruction("return"), Instruction("end"),
                Instruction("local.get", "source"),
                Instruction("i32.const", layout.size),
                Instruction("call", "__rove_mir_clone_bytes"),
                Instruction("local.set", "copy"),
            ]
            for tag, payload_type in self._tagged_owned_payloads(value_type):
                body.extend((
                    Instruction("local.get", "source"), Instruction("i32.load"),
                    Instruction("i32.const", tag), Instruction("i32.eq"),
                    Instruction("if"),
                    Instruction("local.get", "copy"),
                    Instruction("i32.const", layout.payload_offset), Instruction("i32.add"),
                    Instruction("local.get", "source"),
                    Instruction("i32.const", layout.payload_offset), Instruction("i32.add"),
                ))
                body.extend(self._clone_value(payload_type))
                body.extend((
                    Instruction("i32.const", self.layouts.layout_of(payload_type).size),
                    Instruction("memory.copy"), Instruction("end"),
                ))
            body.extend((Instruction("local.get", "copy"), Instruction("return")))
            helper = FunctionIR(
                name, [("source", I32)], I32, locals=[("copy", I32)],
                body=body, export=False,
            )
        else:
            element_type = value_type.arguments[0]
            element_size = 4 if element_type == MIRType("bool") else self.layouts.layout_of(element_type).size
            body = [
                Instruction("local.get", "source"), Instruction("i32.eqz"),
                Instruction("if"), Instruction("i32.const", 0),
                Instruction("return"), Instruction("end"),
                Instruction("local.get", "source"), Instruction("i32.const", element_size),
                Instruction("call", "__rove_mir_array_clone_blob"),
                Instruction("local.set", "copy"),
                Instruction("local.get", "source"), Instruction("i32.const", 4),
                Instruction("i32.add"), Instruction("i32.load"),
                Instruction("local.set", "length"),
                Instruction("block", "clone_done"), Instruction("loop", "clone_next"),
                Instruction("local.get", "index"), Instruction("local.get", "length"),
                Instruction("i32.ge_s"), Instruction("br_if", "clone_done"),
                Instruction("local.get", "copy"), Instruction("i32.load"),
                Instruction("local.get", "index"), Instruction("i32.const", element_size),
                Instruction("i32.mul"), Instruction("i32.add"),
                Instruction("local.get", "source"), Instruction("i32.load"),
                Instruction("local.get", "index"), Instruction("i32.const", element_size),
                Instruction("i32.mul"), Instruction("i32.add"),
            ]
            body.extend(self._clone_value(element_type))
            body.extend((
                Instruction("i32.const", element_size), Instruction("memory.copy"),
                Instruction("local.get", "index"), Instruction("i32.const", 1),
                Instruction("i32.add"), Instruction("local.set", "index"),
                Instruction("br", "clone_next"), Instruction("end"), Instruction("end"),
                Instruction("local.get", "copy"), Instruction("return"),
            ))
            helper = FunctionIR(
                name, [("source", I32)], I32,
                locals=[("copy", I32), ("length", I32), ("index", I32)],
                body=body, export=False,
            )
        self.owned_clone_helpers[value_type] = helper
        return name

    def _operand_type(self, value: Operand) -> MIRType:
        if isinstance(value, ConstOperand):
            return value.type
        if isinstance(value, (CopyOperand, MoveOperand)):
            value_type = self.local_types[value.place.local]
            for projection in value.place.projections:
                if isinstance(projection, (IndexProjection, ConstantIndexProjection)):
                    if value_type.name != "Array" or len(value_type.arguments) != 1:
                        raise MIRCodegenError(f"Wasm MIR index requires Array<T>, got '{value_type}'")
                    value_type = value_type.arguments[0]
                elif isinstance(projection, FieldProjection):
                    definition = self.structs.get(value_type.name)
                    field = next(
                        (item for item in definition.fields if item.name == projection.name),
                        None,
                    ) if definition is not None else None
                    if field is None:
                        raise MIRCodegenError(
                            f"Wasm MIR field requires a known struct field, got '{value_type}.{projection.name}'"
                        )
                    value_type = field.type
                else:
                    raise MIRCodegenError(
                        f"illegal projection reached WebAssembly emitter: {type(projection).__name__}"
                    )
            return value_type
        raise MIRCodegenError(f"unknown WebAssembly operand type: {type(value).__name__}")

    def _type(self, value: MIRType, function: MIRFunction | None = None) -> str:
        if value.name == "any" and function is not None and function.name in ("main", "__nyx_top_level"):
            return VOID
        if value.name == "void":
            return VOID
        if value.name == "bool":
            return I32
        if value.name == "int":
            return I64
        if value.name == "string":
            return I32
        if value.name in ("float", "f64"):
            return F64
        if value.name == "Array" and len(value.arguments) == 1:
            element_type = value.arguments[0]
            while element_type.name == "Array" and len(element_type.arguments) == 1:
                element_type = element_type.arguments[0]
            if (
                element_type in (
                    MIRType("int"), MIRType("bool"), MIRType("float"),
                    MIRType("f64"), MIRType("string"),
                )
                or element_type.name in self.structs
            ):
                return I32
        if value.name in self.structs:
            return I32
        if value.name in self.enums:
            return I32
        if self._is_result_compatible(value):
            return I32
        raise MIRCodegenError(f"unsupported WebAssembly MIR type '{value}'")

    def _store_instruction(self, value_type: MIRType) -> str:
        if value_type == MIRType("bool"):
            return "i32.store8"
        return f"{self._type(value_type)}.store"

    def _load_instruction(self, value_type: MIRType) -> str:
        if value_type == MIRType("bool"):
            return "i32.load8_u"
        return f"{self._type(value_type)}.load"

    def _array_place(self, place: Place) -> list[Instruction]:
        if not place.projections or not isinstance(
            place.projections[-1], (IndexProjection, ConstantIndexProjection)
        ):
            raise MIRCodegenError("Wasm MIR array place must end in an index")
        return self._projected_place(place)

    def _field_address(self, place: Place) -> list[Instruction]:
        if not place.projections or not isinstance(place.projections[-1], FieldProjection):
            raise MIRCodegenError("Wasm MIR struct place must end in a field")
        return self._projected_place(place)

    def _projected_place(self, place: Place) -> list[Instruction]:
        value_type = self.local_types[place.local]
        output = [Instruction("local.get", self.local_names[place.local])]
        for index, projection in enumerate(place.projections):
            if isinstance(projection, FieldProjection):
                layout = self.layouts.layout_of(value_type)
                field = next((item for item in layout.fields if item.name == projection.name), None)
                if field is None:
                    raise MIRCodegenError(
                        f"Wasm MIR struct field '{value_type}.{projection.name}' is unknown"
                    )
                output.extend((Instruction("i32.const", field.offset), Instruction("i32.add")))
                value_type = field.type
                continue
            if not isinstance(projection, (IndexProjection, ConstantIndexProjection)):
                raise MIRCodegenError(
                    f"illegal projection reached WebAssembly emitter: {type(projection).__name__}"
                )
            if value_type.name != "Array" or len(value_type.arguments) != 1:
                raise MIRCodegenError(f"Wasm MIR index requires Array<T>, got '{value_type}'")
            if isinstance(projection, ConstantIndexProjection):
                output.append(Instruction("i64.const", projection.index))
            else:
                output.append(Instruction("local.get", self.local_names[projection.local]))
            value_type = value_type.arguments[0]
            if index + 1 < len(place.projections):
                element_size = 4 if value_type == MIRType("bool") else self.layouts.layout_of(value_type).size
                output.extend((
                    Instruction("i32.const", element_size),
                    Instruction("call", "__rove_mir_array_get_blob"),
                ))
        return output

    def _place_type(self, place: Place) -> MIRType:
        value_type = self.local_types[place.local]
        for projection in place.projections:
            if isinstance(projection, (IndexProjection, ConstantIndexProjection)):
                if value_type.name != "Array" or len(value_type.arguments) != 1:
                    raise MIRCodegenError(f"Wasm MIR index requires Array<T>, got '{value_type}'")
                value_type = value_type.arguments[0]
            elif isinstance(projection, FieldProjection):
                definition = self.structs.get(value_type.name)
                field = next(
                    (item for item in definition.fields if item.name == projection.name),
                    None,
                ) if definition is not None else None
                if field is None:
                    raise MIRCodegenError(f"Wasm MIR struct '{value_type}' has no field '{projection.name}'")
                value_type = field.type
            else:
                raise MIRCodegenError(f"Wasm MIR place type cannot resolve '{type(projection).__name__}'")
        return value_type

    def _intern_string(self, value: str) -> int:
        existing = self.string_literals.get(value)
        if existing is not None:
            return existing
        encoded = value.encode("utf-8")
        data_offset = self.next_data_offset
        if encoded:
            self.data.append(DataSegment(data_offset, encoded))
            self.next_data_offset += len(encoded)
        self.next_data_offset = (self.next_data_offset + 3) & ~3
        descriptor_offset = self.next_data_offset
        self.data.append(DataSegment(
            descriptor_offset,
            binary_struct.pack("<III", data_offset, len(encoded), len(encoded)),
        ))
        self.next_data_offset += 12
        self.string_literals[value] = descriptor_offset
        return descriptor_offset

    def _local_type(self, local: int, function: MIRFunction) -> str:
        if local in self.tag_locals:
            return I32
        return self._type(function.locals[local].type, function)

    def _discriminant_locals(self, function: MIRFunction) -> dict[int, dict[str, int]]:
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
                definition = self.enums.get(subject_type.name if subject_type else "")
                if definition is not None:
                    result[statement.place.local] = {
                        variant.name: index for index, variant in enumerate(definition.variants)
                    }
                elif (
                    subject_type is not None
                    and subject_type.name == "Result"
                    and self._is_result_compatible(subject_type)
                ):
                    result[statement.place.local] = {"Ok": 0, "Err": 1}
        return result

    def _aggregate_subject(self, operand: Operand) -> list[Instruction]:
        if not isinstance(operand, (CopyOperand, MoveOperand)) or operand.place.projections:
            raise MIRCodegenError("Wasm enum operation requires a direct aggregate local")
        return [Instruction("local.get", self.local_names[operand.place.local])]

    def _is_tagged_aggregate(self, value_type: MIRType) -> bool:
        return value_type.name in self.enums or self._is_result_compatible(value_type)

    def _is_memory_aggregate(self, value_type: MIRType) -> bool:
        return value_type.name == "Array" or value_type.name in self.structs or self._is_tagged_aggregate(value_type)

    def _is_result_compatible(self, value_type: MIRType) -> bool:
        def compatible(argument: MIRType) -> bool:
            return argument in (
                MIRType("int"), MIRType("bool"), MIRType("float"),
                MIRType("f64"), MIRType("string"), MIRType("any"),
            ) or (
                argument.name in self.structs
                and not argument.arguments
                and not argument.optional
                and not argument.pointer
            )

        return bool(
            value_type.name == "Result"
            and len(value_type.arguments) == 2
            and all(compatible(argument) for argument in value_type.arguments)
            and any(argument.name != "any" for argument in value_type.arguments)
        )


def lower_legalized_wasm(module: MIRModule) -> ModuleIR:
    return _WasmEmitter(legalize_mir(module, "wasm", require_emitter=True)).lower()


def emit_legalized_wasm(module: MIRModule) -> bytes:
    return lower_legalized_wasm(module).to_wasm()


def emit_legalized_wat(module: MIRModule) -> str:
    return lower_legalized_wasm(module).to_wat()
