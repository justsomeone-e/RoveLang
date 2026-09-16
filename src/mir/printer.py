"""Deterministic human-readable MIR printer."""

from __future__ import annotations

from .model import (
    AssertTerminator,
    AssignStatement,
    AggregateRValue,
    BinaryRValue,
    BorrowRValue,
    CastRValue,
    CallTerminator,
    ConstOperand,
    ConstantIndexProjection,
    CopyOperand,
    DeinitStatement,
    DiscriminantRValue,
    DropTerminator,
    GotoTerminator,
    MIRModule,
    MIREnumDef,
    MIRStructDef,
    MoveOperand,
    NopStatement,
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
)


def _place(value: Place) -> str:
    rendered = f"_{value.local}"
    for projection in value.projections:
        name = type(projection).__name__
        if name == "FieldProjection":
            rendered += f".{projection.name}"
        elif name == "IndexProjection":
            rendered += f"[_{projection.local}]"
        elif isinstance(projection, ConstantIndexProjection):
            rendered += f"[{projection.index}]"
        elif isinstance(projection, VariantProjection):
            rendered += f" as {projection.name}.{projection.index}"
        else:
            rendered = f"(*{rendered})"
    return rendered


def _operand(value: object) -> str:
    if isinstance(value, ConstOperand):
        return f"const {value.value!r}: {value.type}"
    if isinstance(value, CopyOperand):
        return f"copy {_place(value.place)}"
    if isinstance(value, MoveOperand):
        return f"move {_place(value.place)}"
    raise TypeError(f"Unknown MIR operand {type(value).__name__}")


def _rvalue(value: object) -> str:
    if isinstance(value, UseRValue):
        return _operand(value.operand)
    if isinstance(value, BinaryRValue):
        return f"{value.op}({_operand(value.left)}, {_operand(value.right)}): {value.type}"
    if isinstance(value, UnaryRValue):
        return f"{value.op}({_operand(value.operand)}): {value.type}"
    if isinstance(value, CastRValue):
        return f"cast[{value.kind}]({_operand(value.operand)}): {value.type}"
    if isinstance(value, AggregateRValue):
        operands = ", ".join(_operand(item) for item in value.operands)
        fields = f" {{{', '.join(value.fields)}}}" if value.fields else ""
        return f"aggregate[{value.kind} {value.name}{fields}]({operands}): {value.type}"
    if isinstance(value, BorrowRValue):
        kind = "&mut" if value.mutable else "&"
        return f"borrow[{kind}]({_place(value.place)}): {value.type}"
    if isinstance(value, DiscriminantRValue):
        return f"discriminant({_operand(value.operand)}): {value.type}"
    if isinstance(value, PayloadRValue):
        return f"payload[{value.index}]({_operand(value.operand)}): {value.type}"
    raise TypeError(f"Unknown MIR rvalue {type(value).__name__}")


def _statement(value: object) -> str:
    if isinstance(value, AssignStatement):
        return f"{_place(value.place)} = {_rvalue(value.value)}"
    if isinstance(value, StorageLiveStatement):
        return f"StorageLive(_{value.local})"
    if isinstance(value, StorageDeadStatement):
        return f"StorageDead(_{value.local})"
    if isinstance(value, RetainStatement):
        return f"retain({_place(value.place)})"
    if isinstance(value, ReleaseStatement):
        return f"release({_place(value.place)})"
    if isinstance(value, DeinitStatement):
        return f"deinit({_place(value.place)})"
    if isinstance(value, NopStatement):
        return "nop"
    raise TypeError(f"Unknown MIR statement {type(value).__name__}")


def _terminator(value: object) -> str:
    if isinstance(value, GotoTerminator):
        return f"goto -> bb{value.target}"
    if isinstance(value, SwitchIntTerminator):
        targets = ", ".join(f"{key}: bb{target}" for key, target in value.targets)
        return f"switchInt({_operand(value.discriminator)}) -> [{targets}, otherwise: bb{value.otherwise}]"
    if isinstance(value, SwitchValueTerminator):
        targets = ", ".join(f"{key!r}: bb{target}" for key, target in value.targets)
        return f"switchValue({_operand(value.discriminator)}) -> [{targets}, otherwise: bb{value.otherwise}]"
    if isinstance(value, ReturnTerminator):
        return "return"
    if isinstance(value, CallTerminator):
        arguments = ", ".join(_operand(item) for item in value.arguments)
        destination = _place(value.destination) if value.destination is not None else "_"
        target = f"bb{value.target}" if value.target is not None else "unreachable"
        unwind = f", unwind bb{value.unwind}" if value.unwind is not None else ""
        return f"{destination} = call {value.function}({arguments}) -> {target}{unwind}"
    if isinstance(value, DropTerminator):
        unwind = f", unwind bb{value.unwind}" if value.unwind is not None else ""
        return f"drop {_place(value.place)} -> bb{value.target}{unwind}"
    if isinstance(value, AssertTerminator):
        unwind = f", unwind bb{value.unwind}" if value.unwind is not None else ""
        return (
            f"assert({_operand(value.condition)} == {str(value.expected).lower()}, "
            f"{value.message!r}) -> bb{value.target}{unwind}"
        )
    if isinstance(value, UnreachableTerminator):
        return "unreachable"
    if isinstance(value, ThrowTerminator):
        if value.target is None:
            return f"throw {_operand(value.value)} -> unwind"
        destination = _place(value.destination) if value.destination is not None else "_"
        return f"throw {_operand(value.value)} -> {destination}, bb{value.target}"
    if isinstance(value, SuspendTerminator):
        unwind = f", unwind bb{value.unwind}" if value.unwind is not None else ""
        return (
            f"{_place(value.destination)} = suspend[{value.suspend_id}] "
            f"{_operand(value.task)} -> bb{value.resume}{unwind}"
        )
    raise TypeError(f"Unknown MIR terminator {type(value).__name__}")


def print_mir(module: MIRModule) -> str:
    lines = [f"mir v{module.schema_version} {module.source_name!r} target {module.target} {{"]
    for definition in module.type_definitions:
        if isinstance(definition, MIRStructDef):
            fields = ", ".join(f"{field.name}: {field.type}" for field in definition.fields)
            lines.append(f"  struct {definition.name} [{definition.symbol}] {{ {fields} }}")
        elif isinstance(definition, MIREnumDef):
            variants = ", ".join(
                variant.name + (
                    "(" + ", ".join(str(item) for item in variant.payload_types) + ")"
                    if variant.payload_types else ""
                )
                for variant in definition.variants
            )
            lines.append(f"  enum {definition.name} [{definition.symbol}] {{ {variants} }}")
    for function in module.functions:
        parameters = ", ".join(f"_{local_id}" for local_id in function.parameters)
        effects = ", ".join(function.effects) if function.effects else "unannotated"
        async_marker = " async" if function.is_async else ""
        lines.append(
            f"  fn{async_marker} {function.name} [{function.symbol}]({parameters}) "
            f"effects [{effects}] {{"
        )
        if function.coroutine is not None:
            frame = ", ".join(f"_{local}" for local in function.coroutine.frame_locals)
            lines.append(
                f"    coroutine state _{function.coroutine.state_local} frame [{frame}]"
            )
            lines.append(
                "    coroutine lifecycle "
                f"start={function.coroutine.start_symbol} "
                f"resume={function.coroutine.resume_symbol} "
                f"destroy={function.coroutine.destroy_symbol}"
            )
            for point in function.coroutine.suspend_points:
                live = ", ".join(f"_{local}" for local in point.live_locals)
                lines.append(
                    f"    suspend_point {point.id}: bb{point.block} -> bb{point.resume} live [{live}]"
                )
        for local in function.locals:
            lines.append(f"    let _{local.id}: {local.type} // {local.kind} {local.name}")
        for block in function.blocks:
            lines.append(f"    bb{block.id}:")
            for statement in block.statements:
                lines.append(f"      {_statement(statement)}")
            lines.append(f"      {_terminator(block.terminator)}")
        lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"
