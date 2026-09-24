# Rove MIR and Bundle ABI v2 draft

Status: experimental design contract. Bundle ABI v1 remains the stable public
ABI and is not changed by this document.

## Logical values and storage

Typed HIR and MIR name logical Rove types. Physical size, alignment, field
offsets, enum tags, and payload offsets are computed later by
`src/mir/layout.py` from an explicit target data layout. Host Python object size
and alignment are never used as ABI evidence.

Owned `string` and `Array<T>` values use a three-word logical descriptor:
data pointer, length, and capacity. Runtime handles use one target pointer.
Struct fields are laid out in declaration order with explicit padding. Payload
enums use a fixed tag followed by an aligned maximum-size payload area.

## Calls and ownership

`src/mir/abi.py` classifies each parameter and result as `direct`, `indirect`,
`sret`, or `void`. Owned aggregate arguments are borrowed for the duration of a
call unless an operation explicitly moves them. Owned results transfer to the
caller. MIR retains copy, move, borrow, retain, release, deinit, and drop as
separate operations so an emitter cannot infer ownership from target syntax.

## Bundle compatibility

- Bundle ABI v1 remains version `1` and is the only stable browser/host ABI.
- Bundle ABI v2 is version `2`, status `draft`, and cannot be selected by the
  normal bundle command.
- A future v2 adapter must declare descriptor width, allocation owner, UTF-8
  ownership, array element layout, error channel, and disposal entry points.
- No v2 artifact may be labeled stable until v1/v2 coexistence and host-side
  lifetime tests pass.

## C adapters

Scalar integers, floats, booleans, characters, pointers, and recursively
C-compatible structs may cross a checked C boundary directly. Strings, arrays,
Option, Result, tasks, channels, iterators, dynamic values, payload enums, and
callbacks require generated adapters. Unsupported values are rejected with a
reason; no implicit representation guess is permitted.
