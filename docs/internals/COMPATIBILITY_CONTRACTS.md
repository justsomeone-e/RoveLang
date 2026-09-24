# Rove v4 Compatibility Contracts

Status: `v4.0.0 Nirvana` stable contract, effective upon publication.
The stable semantic set is `cpp`, `js`, and `python`; other backends retain
their documented capability and maturity levels. v4.5.0 must preserve this
contract. Breaking changes require a versioned migration as described below.

## Source and diagnostics

- Valid source accepted by a v4 stable compiler must not change meaning within
  the v4 line.
- Structured diagnostic codes may gain clearer text, but an existing code is
  not reused for a different failure category within v4.
- New syntax requires Python/Rove parser acceptance parity and canonical HIR
  parity before it can enter a release candidate.

## Typed HIR and compiler API

- Canonical HIR uses `schema_version = 1`.
- Plugins and compiler-API transforms must preserve the schema version and
  return verifier-valid HIR. Unknown versions are rejected, never guessed.
- Adding an optional node field is compatible only when canonical serialization
  and every authoritative backend define its default behavior. Removing or
  reinterpreting a field requires a new HIR schema version.

## Bundle ABI v1

Every generated module exports:

- `memory`
- `__nyx_alloc(size: i32) -> i32`
- `__nyx_free(ptr: i32, size: i32)`
- `__nyx_abi_version() -> i32`, returning `1`

Rove `int`/`bool` use `i32` at this boundary and `float` uses `f64`. Strings use
UTF-8 and return as packed `i64`: `(byte_length << 32) | unsigned_pointer`.
String and numeric-array inputs are borrowed only for the duration of a call.
Returned string buffers are caller-owned and the generated loader releases
them after decoding. Bounds and ABI mismatches fail explicitly.

Changing value widths, packed-string layout, allocation ownership, or required
exports requires Bundle ABI v2. Adding a new optional export is compatible.

The current beta WASM lowerer also uses i32 for Rove integer arithmetic; it does
not claim the stable hosted backends' full signed-i64 contract. Numeric-array
parameter reads check logical indices and descriptor memory ranges before
loading; violations trap (`WebAssembly.RuntimeError` in JavaScript). This does
not enable array assignment, owned arrays, or catchable Rove exceptions. See
the [v5 migration plan](V4_5_V5_PREPARATION.md) before changing integer widths.

## Browser host ABI v1

Browser imports live under the `nyx_host_v1` WebAssembly namespace. Handles are
opaque nonzero `i32` values; `0` means no value. Host strings are borrowed UTF-8
`(pointer, byte_length)` pairs. A module using `std/web` calls
`_nyx_host_abi_version()`, and the generated loader rejects any result other
than `1`.

These names remain part of ABI v1 after the public Rove rename. Changing them
requires a separately versioned ABI and a migration path for existing hosts.

New optional host functions may be added within v1. Renaming imports, changing
signatures, changing handle lifetime, or changing event dispatch semantics
requires a new host namespace.

## Package and lock formats

- Generated npm packages expose the core module at `.` and framework adapters
  through explicit conditional-export subpaths.
- Local dependency paths in `rove.toml` and `rove.lock` are relative to the
  owning project, slash-normalized, and resolved before use. Local lock entries
  include a deterministic SHA-256 source fingerprint.
- Unknown required lock fields or unsupported format versions must fail closed.
  Cosmetic key ordering and newly optional metadata are compatible changes.

## Release policy

Release tags must equal `v` plus the exact repository `VERSION`. CI verifies
this before creating assets. Any incompatible contract change is reserved for
a new schema, ABI namespace, or major Rove version.
