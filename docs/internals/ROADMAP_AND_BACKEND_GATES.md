# Rove v4 Nirvana, v4.5 Ivory, v5 Daydream, and Backend Roadmap

This document is the release-planning source of truth for the Rove compiler. Backend
capabilities exposed by the compiler remain machine-readable through
`rove targets --json`.

The dated implementation changelog, ordered v4.5/v5 milestones, lowering
research, migration design, and current validation are maintained in
[V4_5_V5_PREPARATION.md](V4_5_V5_PREPARATION.md). The current stable release is
`v5.0.0 Daydream`; future milestone names do not imply implemented features.

## Release decision

- Published stable releases: `v4.0.0 Nirvana`, `v4.5.0 Ivory`, and
  `v5.0.0 Daydream`.
- The unpublished v4 RC3 work was incorporated into Nirvana; Ivory then
  preserved v4 compatibility while preparing the v5 compiler pipeline.
- Daydream promotes the v5 language and toolchain line, not every backend:
  direct LLVM IR and C17 remain experimental capability-gated targets.
- Version alignment is not publication evidence. Record final-revision tests,
  platform results, and artifacts in the [release checklist](RELEASE_AUDIT_v4.0.0.md).
- Python remains a stage-0 bootstrap and optional orchestration tool, not a
  dependency of the distributed native compiler.
- `cpp`, `js`, and `python` are the stable semantic parity set. A backend with
  a narrower contract must reject unsupported behavior explicitly.

## Compiler architecture

```text
Rove source
  -> frontend (lexer, parser, type checker)
  -> canonical typed HIR v1
  -> verified deterministic passes
  -> backend
  -> target artifact
```

Backends must consume verified HIR. Direct AST emitters are migration-only and
cannot receive a new `stable` designation. `rust` now consumes HIR directly;
its beta label remains because Task/exception/concurrency support, retained
runtime parity, and cross-platform Gate 8 evidence are intentionally incomplete.

## Current backend status

| Target | Artifact | Registry maturity | HIR authority | v5 contract |
|---|---|---:|---:|---|
| `cpp` | C++20 / native binary | stable | Yes | Keep native runtime and self-host parity green |
| `js` | ES2022 / Node.js | stable | Yes | Keep exact hosted semantics green |
| `python` | Python 3 | stable | Yes | Keep exact hosted semantics green |
| `wasm` | WAT / WASM ABI v1 | beta | Yes | i32 numeric profile; checked numeric-array reads, WASI preview1 and borrowed scalar-struct ABI |
| `rust` | Rust 2021 | beta | Yes | Result propagation; keep other unsupported runtime features gated |
| `react` | React 19 TSX | beta | No | Treat as web tooling, not semantic oracle |
| `asm` | x86_64 assembly via C++ | beta | No | Keep beta |
| `c` | ISO C17 source / native binary | experimental | Yes | Scalar subset with strict rejection |
| `llvm` | LLVM IR / native binary | experimental | Yes | Scalar, scalar-field struct, and stack-owned scalar-array subset |

## Eight backend gates

1. Registered capability and artifact contract.
2. Complete HIR node coverage with no AST dependency.
3. Defined numeric, string, ownership, error, and control-flow semantics.
4. Valid target artifact produced by the official target toolchain.
5. Structured negative diagnostics with stable error codes.
6. Deterministic fuzzing with no compiler crash or invalid artifact.
7. Differential runtime parity against canonical semantic fixtures.
8. Windows, Linux, and macOS CI plus packaging and documentation audit.

## Self-hosting and the Python boundary

Completed:

1. The Rove-authored lexer, parser, type checker, typed-HIR lowerer, and HIR C++
   emitter build into the standalone native `rovec` compiler.
2. Python and Rove frontends have exact accepted/rejected corpus and canonical
   HIR parity.
3. Stage 1 builds stage 2; stage 2 emits byte-identical stage-3 C++ from the
   same compiler sources and compiles a native fixture.
4. Native-first installers route `check`, `emit-cpp`, `compile`, and
   version queries to `rovec` without Python.

`rove targets --json` uses the optional Python orchestration layer to report the
full backend registry. The standalone `rovec` compiler emits C++ only.

Python remains intentionally available for three roles: recreating stage 1
from zero, optional legacy/orchestration commands, and the `python` target runtime.
It is no longer the production compiler architecture.

## v4 language freeze

The RC1 candidate freezes:

- 44 canonical keywords shared exactly by the lexer, self-host frontend, LSP,
  grammar, and VS Code extension;
- `fn` as the only function declaration spelling (`def` is an identifier);
- shallow immutable `let`/`const` bindings and explicit `set` assignment;
- bodyless trait signatures with verified implementation contracts;
- `Task<T>`, `await`, exceptions, `guard`, `defer`, `match`, interpolation, and
  pipelines;
- fixed-width scalars and explicit unsafe/native interoperability boundaries;
- strict Boolean conditions;
- signed i64 wrap/division/shift semantics, IEEE binary64 semantics, canonical
  scalar text, and identical constant-folding behavior.

Expression-bodied functions, value-producing `if`/`match`, array/struct
destructuring, Result propagation, default arguments, collection iteration,
and `yield` syntax are implemented. The full iterator protocol, closures, rest
patterns, compile-time `when`, named arguments, and visibility syntax remain
RFC candidates. No grammar change lands after RC1 without a compatibility
proof.

## Release codenames

Release names do not create artificial releases; unused RC names are skipped.

| Release | Codename |
|---|---|
| `v4.0.0-dev.*` | Maya |
| `v4.0.0-beta.*` | Nocturne |
| `v4.0.0-rc.1` | Samsara |
| `v4.0.0-rc.2` | Bodhi |
| `v4.0.0-rc.3` (unpublished; included in Nirvana) | Moksha |
| `v4.0.0` | Nirvana |
| `v4.5.0` | Ivory |
| `v5.0.0` | Daydream |
| `v6.0.0` | Sepia |
| `v7.0.0` | Solace |
| `v8.0.0` | Last Signal |

## New target order after RC1

1. `c`: portable C17 source backend and a smaller bootstrap surface.
2. `llvm`: direct LLVM IR native backend; no C++ source hop.
3. `go`: Go service/concurrency backend with explicit channel mapping.
4. `jvm`: JVM backend with Java 21 class-file compatibility as its baseline.
5. `dotnet`: .NET 10 managed backend.
6. `lua`: Lua 5.4 embedding and game-scripting backend.

Every new target starts experimental and must pass all eight gates. `zig` is
deferred until its language/toolchain contract is stable enough to freeze a
backend against it.

## OCaml reference frontend

`rove-ocaml` is a post-RC1 verification track, not a rewrite of the production
compiler. It will:

- parse the frozen Rove grammar independently;
- emit canonical HIR JSON;
- compare HIR fingerprints and structured diagnostics with the primary
  frontend;
- contain no backend, package manager, or runtime implementation.

This gives Rove a second implementation capable of detecting shared assumptions
without delaying the HIR migration or self-hosting chain.

## Nirvana release gate

- Run the full battery from clean Windows, Linux x64, macOS x64, and macOS arm64
  environments; retain the CI evidence.
- Make release archives deterministic and reject machine-specific paths.
- Synchronize the CLI, native compiler, changelog, README, and editor manifest
  to `4.0.0`; create the matching tag only after final-revision validation.
- Keep `nyx_host_v1`, Bundle ABI v1, generated TypeScript types, and npm exports
  under direct conformance tests.
- Keep the pure-Rove browser Pong fixture free of handwritten application logic
  in JavaScript; the generated adapter is the only host bridge.
- Verify recursive local dependency locks are path-normalized, cycle-safe, and
  content-addressed.
- Publish archive and native-binary SHA-256 manifests plus provenance/SBOM.
- Run the release audit twice from clean checkouts and retain observed RC
  feedback. The RC3 label is not a separate publication requirement.

## Stable gate

- The final v4 source revision has no unresolved release-blocking defect;
  previous RC test results do not certify later changes.
- Stable backends pass all eight gates from clean environments.
- Compiler API, plugin API, HIR schema, Bundle ABI, and package lockfile formats
  have published compatibility rules.
- Release artifacts have checksums, provenance/SBOM, and a tested rollback.

## v4.5.0: preparation for v5

The nine-track implementation audit and concrete acceptance criteria are in
[V4_5_IMPLEMENTATION_AUDIT.md](V4_5_IMPLEMENTATION_AUDIT.md). It distinguishes
implemented work from remaining LSP, runtime, package, and release gates.

v4.5.0 is a compatible v4 milestone, not a rewrite or a blanket promotion of
beta backends. v4.0.x remains the path for focused fixes after Nirvana.

1. Improve diagnostics and editor navigation: references, rename, and semantic
   tokens, with fixtures covering module boundaries and shadowed symbols.
2. Expand practical examples across native CLI tools, JavaScript/Python
   integrations, and WASM applications. Games are one example category.
3. Measure frontend/codegen time and memory on a fixed corpus before changing
   module caching or runtime emission. Preserve self-host reproducibility.
4. Extend standard-library APIs compatibly, with consistent Result errors and
   runtime parity on the stable backend set.
5. Advance Rust/WASM capability gaps individually. Require runtime and negative
   conformance evidence before enabling a capability or changing maturity.
6. Prepare C/LLVM backend and independent-frontend RFCs for v5. Any prototypes
   remain experimental and cannot change v4 output or installation defaults.
7. Publish the v5 migration design before changing source meaning, HIR schema,
   Bundle ABI, host namespaces, or package lockfile requirements.
8. Extend deterministic local locks toward versioned dependency resolution,
   remote registry design, typed bindings, offline operation, and checksum tests.
9. Require final-revision source compatibility, stable backend parity, self-host
   reproducibility, platform CI, extension tests, checksums, SBOM and release assets.

Go/JVM/.NET/Lua backends, breaking syntax and declaring LLVM stable are outside
v4.5. C17/LLVM prototypes stay experimental and do not become default backends.

Completion requires the v4 regression corpus to remain valid, documented
compatibility for every addition, and clean platform validation. Items are
priorities for planning; they are not claims of implemented functionality.

## v5.0.0 Daydream delivered scope

Daydream delivers the C17 scalar pilot, direct LLVM scalar and aggregate pilot,
canonical compiler API integration, and `rove build`/`rove run` LLVM workflows.
The LLVM runtime/ownership surface, complete standard-library lowering, and a
direct native self-host emitter remain post-v5 experimental work; see the
[v5 lowering design](V4_5_V5_PREPARATION.md). C++20 remains the default backend
until replacement bootstrap and parity evidence exists.

## Primary references

- [LLVM Language Reference](https://llvm.org/docs/LangRef.html)
- [Go specification and compatibility promise](https://go.dev/ref/spec)
- [Java Virtual Machine Specification](https://docs.oracle.com/javase/specs/)
- [.NET support policy](https://dotnet.microsoft.com/en-us/platform/support/policy)
- [OCaml language documentation](https://ocaml.org/docs)
