# M0 compiler identity contract

Status: internal identity foundation implemented on 2026-09-14. Public Typed
HIR v1 symbols and serialization remain unchanged.

Nyx currently carries many names as strings. That is sufficient for the v5
compiler, but it cannot safely support incremental compilation, multiple
frontends, package-scale semantic queries, or a new MIR. M0 therefore reserves
the following identity roles before any new IR is implemented.

## Identity roles

| Identity | Names | Stable within | Meaning |
| --- | --- | --- | --- |
| `SourceId` | source revision | one compiler database | Content-addressed source plus revision identity |
| `ModuleId` | source module | one dependency graph | Canonical module after path and package resolution |
| `NodeId` | syntax node | one parsed source revision | Concrete syntax occurrence; never reused after reparsing |
| `DefId` | declaration | one resolved package graph | `(package, module, declaration-path hash)` plus a transient local index |
| `SymbolId` | bound name | one semantic session | A binding or reference resolved to a `DefId` or local slot |
| `TypeId` | interned type | one compiler session | Canonical structural type identity |
| `InstanceId` | monomorphized definition | one compilation graph | A `DefId` plus canonical generic arguments and target-independent substitutions |
| `FeatureId` | language/backend capability | registry schema | Stable string key declared by `compiler/features.toml` |

Public serialization must use a versioned structural representation, not a
process-local integer. Dense integer forms are permitted only inside a compiler
session and must never be persisted as if they were stable across revisions.

## Allocation rules

1. `SourceId` changes whenever source bytes change and is the parent identity
   for spans and syntax nodes.
2. `NodeId` is allocated by the parser in source order and is invalidated when
   that source file is reparsed.
3. `DefId` is allocated after module resolution. Its public form includes the
   package/module identity and a declaration-path hash. Its local index is
   traversal metadata, so inserting a neighboring declaration does not change
   identity.
4. `SymbolId` is not derived from spelling. Shadowed names receive different
   identities, and every reference records the identity it resolved to.
5. `TypeId` is produced by interning canonical type structure. Aliases retain a
   `DefId`, while their resolved representation receives the same `TypeId` as
   the underlying type.
6. `InstanceId` is deterministic for one `DefId`, normalized type arguments,
   and target-independent substitution set. Target legalization is not part of
   this identity.
7. Synthetic compiler nodes use a reserved origin plus the identity of the
   source construct that caused their creation. They cannot impersonate source
   nodes.
8. IDs from different compiler sessions are never compared without first
   translating through a serialized stable key.

## Compatibility boundary

Typed HIR remains schema version 1. The present `symbol: string` fields remain
authoritative until an explicitly versioned HIR migration exists. Adding an
internal identity table is allowed, but changing serialized symbol meaning,
Bundle ABI v1, lockfile v1, or stable backend output is outside M0.

MIR may consume these identities only through verified lowering that keeps
source spans, symbol resolution, evaluation order, effects, and diagnostics.
The MIR stages are now registered as `experimental` in `compiler/features.toml`;
they remain off the default compilation path until their promotion gates pass.

## Current implementation

[`src/core/identities.py`](../../src/core/identities.py) provides structural,
serializable `SourceId`, `ModuleId`, `NodeId`, `DefId`, `SymbolId`, `TypeId`,
and `InstanceId` values. `ModuleLoader` records a side-channel `ModuleGraph`
with import edges, declaration-path `DefId` values, interned structural types,
and separate public-interface and implementation fingerprints. The established
flattened AST remains the compilation compatibility output while downstream
passes migrate to graph queries.

`tests/module_resolution_suite.py` proves the required M0 boundary: distinct
modules cannot collide, unchanged declarations retain deterministic `DefId`
keys, changed source invalidates `NodeId`, equal structural types intern to one
`TypeId`, implementation-only edits retain the interface fingerprint, and
identity tracking enabled/disabled produces byte-identical Typed HIR v1 JSON.
It also verifies that inserting a neighboring declaration does not change an
existing declaration's identity.

## Verified proof boundary

- identical definitions in separate modules do not collide;
- shadowed locals resolve to distinct symbols;
- an unchanged module produces deterministic public `DefId` keys;
- reparsing invalidates stale `NodeId` values;
- equivalent structural types intern to one `TypeId`;
- serialized HIR v1 remains byte-for-byte unchanged when identity tracking is
  enabled internally.
