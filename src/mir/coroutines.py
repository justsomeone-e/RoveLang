"""Target-independent coroutine frame and suspend-point elaboration."""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace

from .model import (
    AssertTerminator,
    AssignStatement,
    CallTerminator,
    DropTerminator,
    GotoTerminator,
    MIRCoroutine,
    MIRFunction,
    MIRModule,
    MIRSuspendPoint,
    Place,
    ReturnTerminator,
    SuspendTerminator,
    SwitchIntTerminator,
    SwitchValueTerminator,
    ThrowTerminator,
)


def _place_locals(value: object) -> set[int]:
    found: set[int] = set()
    if isinstance(value, Place):
        found.add(value.local)
        for projection in value.projections:
            local = getattr(projection, "local", None)
            if isinstance(local, int):
                found.add(local)
        return found
    if is_dataclass(value):
        for field in fields(value):
            found.update(_place_locals(getattr(value, field.name)))
    elif isinstance(value, (tuple, list)):
        for item in value:
            found.update(_place_locals(item))
    return found


def _successors(terminator: object) -> tuple[int, ...]:
    if isinstance(terminator, GotoTerminator):
        return (terminator.target,)
    if isinstance(terminator, (SwitchIntTerminator, SwitchValueTerminator)):
        return tuple(target for _value, target in terminator.targets) + (terminator.otherwise,)
    if isinstance(terminator, CallTerminator):
        return tuple(target for target in (terminator.target, terminator.unwind) if target is not None)
    if isinstance(terminator, (DropTerminator, AssertTerminator)):
        values = [terminator.target]
        if terminator.unwind is not None:
            values.append(terminator.unwind)
        return tuple(values)
    if isinstance(terminator, ThrowTerminator):
        return () if terminator.target is None else (terminator.target,)
    if isinstance(terminator, SuspendTerminator):
        values = [terminator.resume]
        if terminator.unwind is not None:
            values.append(terminator.unwind)
        return tuple(values)
    return ()


def _block_use_def(block) -> tuple[set[int], set[int]]:
    used: set[int] = set()
    defined: set[int] = set()

    def use(value: object) -> None:
        used.update(_place_locals(value) - defined)

    for statement in block.statements:
        if isinstance(statement, AssignStatement):
            use(statement.value)
            if statement.place.projections:
                use(statement.place)
            else:
                defined.add(statement.place.local)
        else:
            use(statement)
    terminator = block.terminator
    if isinstance(terminator, CallTerminator):
        use(terminator.arguments)
        if terminator.destination is not None and not terminator.destination.projections:
            defined.add(terminator.destination.local)
    elif isinstance(terminator, SuspendTerminator):
        use(terminator.task)
        if not terminator.destination.projections:
            defined.add(terminator.destination.local)
        if terminator.error_destination is not None and not terminator.error_destination.projections:
            defined.add(terminator.error_destination.local)
    else:
        use(terminator)
    return used, defined


def elaborate_coroutine(function: MIRFunction) -> MIRFunction:
    if not function.is_async:
        return function
    state_locals = tuple(local.id for local in function.locals if local.kind == "coroutine-state")
    if len(state_locals) != 1:
        return function
    uses_defs = {block.id: _block_use_def(block) for block in function.blocks}
    live_in = {block.id: set() for block in function.blocks}
    live_out = {block.id: set() for block in function.blocks}
    changed = True
    while changed:
        changed = False
        for block in reversed(function.blocks):
            next_out: set[int] = set()
            for successor in _successors(block.terminator):
                next_out.update(live_in[successor])
            used, defined = uses_defs[block.id]
            next_in = used | (next_out - defined)
            if next_out != live_out[block.id] or next_in != live_in[block.id]:
                live_out[block.id] = next_out
                live_in[block.id] = next_in
                changed = True

    points: list[MIRSuspendPoint] = []
    frame_locals: set[int] = set(state_locals)
    for block in function.blocks:
        terminator = block.terminator
        if not isinstance(terminator, SuspendTerminator):
            continue
        live = set(live_in[terminator.resume])
        live.discard(terminator.destination.local)
        live.update(_place_locals(terminator.task))
        live.add(terminator.destination.local)
        live.discard(function.return_local)
        ordered = tuple(sorted(live))
        frame_locals.update(ordered)
        points.append(MIRSuspendPoint(
            terminator.suspend_id, block.id, terminator.resume, ordered,
        ))
    return replace(function, coroutine=MIRCoroutine(
        state_locals[0],
        tuple(sorted(frame_locals)),
        tuple(sorted(points, key=lambda point: point.id)),
        f"{function.symbol}::coroutine::start",
        f"{function.symbol}::coroutine::resume",
        f"{function.symbol}::coroutine::destroy",
    ))


def elaborate_coroutines(module: MIRModule) -> MIRModule:
    return replace(module, functions=tuple(
        elaborate_coroutine(function) for function in module.functions
    ))
