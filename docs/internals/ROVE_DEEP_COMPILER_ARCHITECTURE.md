# Rove Deep Compiler Architecture and Formal Roadmap

Status: implementation roadmap with per-milestone evidence. M0-M4 are
implemented as recorded below; full M5 backend parity, formal proofs, ABI
revisions, and later milestones remain open.

Audience: compiler contributors deciding what semantic work is safe to build
next. This is a living architecture and implementation roadmap, not the Rove
language specification and not a claim that the research agenda has been
formally proved.

## Current state at a glance

Validation scope for this snapshot: the last full
`python -u tests/run_all_tests.py` battery is recorded for the checked MIR
foundation release. After the Rust throw/catch and typed `Result<T, E>` slices,
plus the first C++, Rust, JavaScript, and Python `async` task adapters,
the M1-M4 targeted suites and the full M5 legalization suite are green. C++,
LLVM, Wasm, JavaScript, Python, and C17 runtime gates executed locally; every
Rust artifact passed `rustc` metadata/type checking, while Rust runtime linking
remains unverified locally. The default `link.exe` is unavailable; an explicit
bundled `lld-link` attempt also failed because Windows SDK import libraries
such as `kernel32.lib` are absent.
This is repository regression evidence, not hosted multi-platform release evidence.

| Milestone | State | Implemented boundary | Current evidence | Exit-gate gap |
| --- | --- | --- | --- | --- |
| M0 identities/contracts | Foundation implemented | Stable source/module/definition/type identities, feature manifest, non-flattened parsed module graph | Full battery; focused module/manifest suites also pass | Compatibility linking still flattens the final AST/HIR program |
| M1 MIR skeleton | Complete | Versioned model, verifier, printer, serialization, pass fingerprints and CLI tooling | Full battery; `tests/mir_suite.py` passes | None for the stated M1 boundary |
| M2 scalar CFG | Complete | Executable scalar/control-flow MIR and reference interpreter | Full battery; `tests/mir_lowering_suite.py` passes | None for the stated scalar boundary |
| M3 cleanup semantics | Complete for currently lowered HIR | Shared short-circuit, match/guard, Result propagation, defer/unwind CFG, lexical cleanup for source-owned bindings, and single-consumer temporary transfer/discard | Full battery; `tests/mir_cleanup_suite.py` passes, including overwrite, return, break, continue, throw/catch, call/suspend unwind, loop-binding, pattern-binding, comparison-pattern and ignored-owned-expression cleanup edges | Multi-use/control-flow temporary lifetime elaboration and general partial-move analysis remain M5 work; new source constructs must prove that no emitter-local lowering remains |
| M4 memory/ABI | Complete | Aggregate places, ownership operations, verifier, layouts and ABI classification | `tests/mir_memory_abi_suite.py` plus executable C++/JavaScript/Python flat and nested value-parity fixtures | None for the stated M4 boundary; ABI v2 remains a later versioned track |
| M5 backend migration | In progress | Versioned legalization and bounded executable pilots for all listed targets | `tests/mir_legalization_suite.py` passes locally with executable non-Rust gates and explicit Rust metadata-only fallback | Full MIR-surface differential parity, Rust runtime confirmation, remaining target async adapters and aggregate/runtime cases |
| M6-M8 platform expansion | Not complete | Isolated static-dispatch, generic-instance and coroutine foundations | Full battery; focused dispatch/instance/coroutine suites pass | Vertical language slices, ecosystem work, backend promotion and formal validation |
| M9-M24 platform scale | Planned; some foundations exist | Optimizer, target model, workspace, registry, tooling, debug, FFI, concurrency, unsafe, instrumentation, editions and supply-chain tracks | No single completion claim; individual evidence is recorded per track below | Each track requires its own implementation, negative, reproducibility and integration gates |

The non-negotiable migration rule is: **do not delete an existing emitter's
semantic lowering until the replacement MIR path passes positive, negative,
runtime, and differential-parity tests.**

Sections 19-24 are a long-term formal-methods research agenda. They define a
possible proof direction and trusted boundary; they are not release gates for
the current executable compiler unless a milestone explicitly adopts one.

Rove should grow by strengthening a small target-independent semantic core, not
by adding keywords or duplicating lowering logic across emitters. The intended
long-term shape is a language platform whose source semantics, intermediate
representations, runtime contracts, target legalization, and observable
behavior are explicit and independently verifiable.

## 1. Current architectural pressure

Rove already has a structured Typed HIR and multiple backend implementations.
The current HIR remains source-oriented and tree-shaped rather than a
control-flow or SSA representation. Backend emitters independently lower many
of the same constructs, including branching, loops, pattern matching, `defer`,
`guard`, `spawn`, `await`, exceptions, and Result propagation.

That repetition creates three risks:

1. A language feature can acquire different semantics in different emitters.
2. Every new feature multiplies implementation and regression work by the
   number of backends.
3. Backend capability errors may be discovered too late, after semantic
   lowering has already entered an emitter.

The required direction is:

```text
Source
  -> AST
  -> name and type resolution
  -> Typed HIR v1
  -> Rove MIR
  -> target legalization
  -> emitter and runtime adapter
  -> target artifact
```

Typed HIR should remain the public, source-oriented compiler and plugin
contract until an explicitly versioned migration replaces it. MIR should begin
as an internal compiler representation.

## 2. Hidden foundations that must precede scale

### 2.1 Stable compiler identities

Large modules, incremental compilation, generics, and separate compilation
need identities that do not depend on display names or import order:

```text
SourceId
PackageId
ModuleId
DefId
TypeId
LocalId
BlockId
InstanceId
CodegenUnitId
```

Imported declarations should not be flattened into one root program as the
long-term module model. The compiler should preserve a module graph and expose
only a module's public interface to dependants.

### 2.2 Exact type identity

Type checking, assignment compatibility, ABI compatibility, and exact type
identity are different questions and should not share one permissive helper:

```text
is_exact_type(left, right)
is_assignable(expected, actual)
is_coercible(source, destination)
is_abi_compatible(left, right, target)
```

Canonical type identity must include generic arguments, optionality, pointer
kind, function parameters, return type, calling convention where relevant, and
resolved nominal identity.

### 2.3 A real module graph

The module graph should retain:

```text
module identity
source identity
public declarations
private declarations
imports and re-exports
initialization dependencies
foreign dependencies
interface fingerprint
implementation fingerprint
```

A private implementation change should not invalidate unrelated dependant
modules when the public interface fingerprint is unchanged.

### 2.4 Current repository evidence

The architectural pressure above is visible in the current implementation. The
following findings distinguish implemented foundations from remaining design
work.

#### Generic declarations retain names; reachable instances now have identities

[`IRFunction`](../../src/ir/model.py#L263), `IRStruct`, and `IREnum` carry
`generic_params` as tuples of strings. `src/ir/instances.py` now infers
substitutions for reachable generic function calls, recursively discovers calls
made by instantiated generic bodies, deduplicates recursion, and assigns
deterministic `InstanceId` values based on `DefId` and interned concrete
`TypeId` arguments. Generic call result types are substituted before entering
Typed HIR, so `identity<T>(1)` has type `int` rather than leaking `T`.

This is not complete monomorphization. The current model still lacks resolved
`GenericParamId` values, constraint records, and trait-selected method
instances. Function bodies plus reachable generic struct and enum layouts are
cloned with concrete substitutions before MIR lowering. When
callers supply module-graph `DefId` values the collector uses them; its
source-local fallback exists only while flattened HIR remains the compatibility
path.

Remaining consequences include:

- generic trait methods do not yet have dedicated selected instances;
- trait-bound resolution can leak into backend-specific logic;
- C++, Rust, LLVM, and Wasm can accidentally choose different generic
  representations or lowering behavior.

The required replacement concepts are:

```text
GenericParamId
GenericConstraint
SubstitutionMap
MonomorphInstance
CanonicalTypeId
```

#### Type relations are separated; legacy compatibility remains transitional

[`src/ir/types.py`](../../src/ir/types.py) now exposes four distinct predicates:

```text
is_exact_type(left, right)
is_assignable(expected, actual)
is_coercible(source, destination)
is_abi_compatible(left, right, target)
```

HIR verification and MIR coercion use the precise assignment/coercion
predicates. Nested generic arguments are compared recursively, with `any`
acting only as the explicit unresolved-type wildcard. ABI compatibility is
currently conservative and scalar-layout based. The old `compatible()` helper
remains only for unmigrated HIR consumers and preserves their historical loose
generic/pointer behavior; it is not an identity or ABI authority. Nominal
layout compatibility still depends on the future canonical layout engine.

#### Async now has target-independent suspend and frame semantics

The HIR contains [`IRAwait`](../../src/ir/model.py#L57),
[`IRSpawn`](../../src/ir/model.py#L214), and the
[`IRFunction.is_async`](../../src/ir/model.py#L270) flag.

MIR schema v3 lowers every `await` to a numbered `SuspendTerminator` with an
explicit resume block and destination. `src/mir/coroutines.py` performs
backward liveness, records the locals that survive each suspension, and builds
a deterministic coroutine-frame description with a dedicated state local.
Every frame publishes target-independent `start`, `resume`, and `destroy`
lifecycle symbols for legalization adapters.
The reference interpreter models hot, memoized Tasks, including repeated await
of the same Task. User throws stored by a failed Task cross the suspend edge to
the surrounding MIR unwind destination without catching runtime traps. The
verifier rejects missing/malformed coroutine metadata.

The remaining contract and lowering work is:

```text
cancellation
backend-specific frame allocation and destruction
```

The shared MIR now owns suspension identity and frame liveness. The remaining
lifecycle decisions belong in the Rove Task contract and target legalization,
not in direct backend syntax generation.

#### A module graph now accompanies the flattened compatibility AST

[`ModuleLoader.load_program()`](../../src/core/module_loader.py) still prepends
collected imported declarations to root statements for compatibility. It now
also retains a non-flattened [`ModuleGraph`](../../src/core/identities.py) with
stable source/module/definition identities, import edges, interned type IDs,
and separate interface/implementation fingerprints.

Definition identity uses a module-qualified declaration-path hash rather than
the declaration's transient list position. Inserting a different public
declaration before an existing definition therefore changes its local index
without changing its `DefId` equality or stable key.
Public interface records are canonicalized independently of source declaration
order, avoiding invalidation from harmless reordering. The graph also computes
a deterministic dependency-first initialization order and rejects cycles in
that ordering. `resolve_visible()` now performs module-local/direct-import name
resolution over `DefId` values, honors selective-import filters, keeps local
definitions shadowing imports, and reports ambiguous candidate identities.

`ModuleLoader.load_program_graph()` now exposes a `LoadedProgramGraph` whose
module table retains each parsed AST under its own `ModuleId`; its root module
contains only root declarations/imports rather than transitively prepended
bodies. The old flattened `compatibility_program` is carried explicitly beside
that graph instead of masquerading as the module model.

This establishes deterministic identity, invalidation, and a real parsed-module
container without changing Typed HIR v1 bytes. Downstream checking and HIR
resolution still consume the explicit compatibility AST, so the following
migration work remains:

```text
public and private visibility
same-named private declarations
separate compilation units
cyclic interface diagnostics
parallel compilation
```

The next replacement step is to make name/type resolution consume graph records
and public interface fingerprints directly, then remove flattening only behind
an explicitly versioned compiler boundary.

#### Traits now have a bounded static-dispatch model

[`IRTrait`](../../src/ir/model.py#L284) and
[`IRImpl`](../../src/ir/model.py#L291) carry methods and target names.
`src/ir/dispatch.py` resolves receiver calls to one concrete implementation,
turns the receiver into an ordinary first argument, concretizes the `self`
type, and exposes the selected method as a normal function before MIR lowering.
The MIR interpreter corpus proves that the resulting call no longer depends on
backend method lookup.

The model does not yet distinguish:

```text
resolved TraitId and ImplId
associated types
generic bounds
dynamic dispatch
witness or vtable layout
object-safety rules
```

The implemented bounded path resolves static dispatch before MIR:

```text
trait call
  -> resolve implementation
  -> select concrete function
  -> apply substitutions
  -> monomorphize
  -> emit an ordinary MIR call
```

Ambiguous same-target method candidates are rejected by the materializer.
Generic trait constraints, associated types, specialization, and dynamic trait
objects remain a separate type-system and ABI project.

#### Existing pass fingerprints are a useful foundation

The HIR [`PassManager`](../../src/ir/passes.py#L545) already fingerprints input
and output around each pass and can verify every transformed module. This is a
useful seed for deterministic MIR pass records and later incremental query
keys, but it is not itself a complete incremental compiler.

## 3. Staged MIR architecture

Rove should avoid one representation that accepts every high-level and
low-level construct at once. A staged representation provides explicit
invariants and smaller verifier surfaces.

```text
Typed HIR
   |
   v
Build MIR
   Structured source semantics may still be visible.
   |
   v
Cleanup MIR
   `defer`, `?`, destructuring, and unwind cleanup are explicit.
   |
   v
Canonical MIR
   Control flow is a CFG and expressions are unnested.
   |
   +--> Native SSA or LLVM-legal MIR
   +--> Wasm-legal MIR
   +--> Rust-legal MIR
   +--> source-backend legal MIR
```

The first MIR implementation should be non-SSA. SSA can be introduced as a
derived representation for optimization and native code generation after the
canonical CFG, ownership, and cleanup semantics are stable.

### 3.1 Core MIR vocabulary

```text
Storage:
  local
  temporary
  argument
  return_slot
  static
  coroutine_field

Place:
  local
  field
  index
  dereference
  downcast

RValue:
  use
  constant
  unary
  binary
  cast
  aggregate
  discriminant
  length
  reference

Statement:
  assign
  storage_live
  storage_dead
  retain
  release
  drop
  bounds_check
  assert
  intrinsic

Terminator:
  goto
  branch
  switch
  call
  return
  throw
  resume_unwind
  suspend
  spawn
  unreachable
  trap
```

`match`, `guard`, `defer`, postfix `?`, destructuring, safe navigation, null
coalescing, and structured loops should not survive into Canonical MIR. They
must lower into primitive control flow while preserving single evaluation and
source spans.

### 3.2 MIR invariants

Every MIR stage must have a verifier. Canonical MIR should require at least:

```text
- Every basic block has exactly one terminator.
- Every branch target exists.
- Block arguments agree with predecessor values and types.
- Every local and temporary has a unique typed identity.
- Values are initialized before use.
- Storage is not accessed after StorageDead.
- A moved value is not reused.
- A value is dropped at most once.
- Every expression with effects is evaluated exactly once.
- Result payloads are read only after discriminant refinement.
- Every source operation retains provenance to a source span.
```

### 3.3 Pass manager

Each pass should declare:

```text
name
accepted MIR stage
produced MIR stage
required analyses
invalidated analyses
operations it may introduce
preserved invariants
```

The verifier should run before and after each development/debug pass. The pass
pipeline should support textual dumps, timing, fingerprints, and minimal crash
reproducers.

## 4. Central semantic lowering

The following constructs should be lowered once before backend code generation:

```text
and/or                    -> short-circuit CFG
if expression             -> branch plus destination
match                     -> discriminant and switch CFG
guard                     -> branch plus early exit
postfix ?                 -> Result switch plus early return
defer                     -> cleanup chain
try/catch                 -> normal and unwind edges
for                       -> iterator protocol
destructuring             -> projections with one source evaluation
safe navigation           -> optional switch
null coalescing           -> optional switch
closure                   -> environment plus function
async/await               -> coroutine state machine
trait call                -> resolved static or dynamic dispatch
```

No emitter should independently decide the language meaning of these features.

## 5. Effects and capabilities

Functions and calls should carry an internal effect set:

```text
pure
may_allocate
may_throw
may_suspend
may_block
io
unsafe
host_call
```

The first implementation need not add user-facing effect syntax. Internal
effects allow the compiler to:

- reject suspension in a non-async context;
- reject filesystem operations in a browser-only profile;
- distinguish an ordinary Result from exceptional unwinding;
- preserve ordering around observable operations;
- prevent optimizations from moving effectful calls;
- calculate a program's required capability set.

Implementation status (2026-09-14): MIR schema v3 stores canonical effect
metadata and the source async marker on every lowered function.
`src/mir/effects.py` computes direct effects and propagates callee effects to a
fixed point over the module call graph. `src/mir/verifier.py` rejects unknown
or stale declarations with `MIR0110` and `MIR0111`. This is internal metadata;
there is deliberately no user-facing effect syntax yet. Async functions are
conservatively marked `may_suspend` until coroutine lowering can prove a
smaller set.

Capabilities may later be declared by a package manifest:

```toml
[capabilities]
allow = ["fs.read", "stdout"]
deny = ["network", "process.spawn"]
```

## 6. Result, exception, panic, and trap

These must remain distinct:

```text
Result<T, E>  normal typed value and control flow
throw         catchable exceptional control flow
panic         runtime failure governed by a panic policy
trap          non-catchable target/runtime safety termination
```

Postfix `?` on `Result<T, E>` should become a discriminant branch and early
return, not an exception. Calls that may throw need explicit normal and unwind
successors. Cleanup elaboration must ensure all relevant `defer` and `drop`
operations run on return, break, continue, and unwind paths.

The MIR should retain abstract unwind semantics. LLVM's Windows and Itanium
exception representations differ, so platform-specific landing pads,
personalities, and tables belong in target legalization rather than source
semantics.

## 7. Generics and trait solving

### 7.1 Generic identities

The compiler needs:

```text
GenericParamId
GenericConstraint
SubstitutionMap
MonomorphInstance
CanonicalTypeId
```

HIR should retain generic declarations and constraints. The initial MIR path
should receive concrete monomorphized instances. A collector discovers all
reachable concrete functions, methods, statics, and layouts before codegen.

Implementation status (2026-09-15): the first target-independent collector is
implemented in `src/ir/instances.py` for reachable generic functions. It uses
canonical concrete type arguments, deterministic `InstanceId` keys, recursive
call discovery, and duplicate-instance suppression. `tests/ir_instances_suite.py`
covers two concrete instantiations, transitive generic calls, deduplication,
stable repeated collection, concrete HIR materialization, generic struct layout
materialization, and MIR interpreter execution. `lower_hir_to_mir`
automatically materializes reachable generic functions, structs, and enums
before CFG lowering. Constraints, static trait dispatch, and migrated backend
parity remain open.

Monomorphization keys must include canonical type arguments and relevant
compile-time parameters. Collection requires recursion/cycle guards and a code
size budget.

Target-language templates must not become the source of Rove generic semantics.
C++ and Rust emitters should receive already-resolved concrete instances. JS
and Python may erase representation details only after Rove-level checking. JVM
or .NET reification can be introduced later through target legalization.

### 7.2 Trait solver

Trait solving should be independent from ordinary compatibility checks and
emitters:

```text
Goal: T implements Display

Result:
  Proven(ImplId, substitutions)
  Ambiguous
  NoSolution
  Overflow
```

Initial support should use static dispatch:

```text
trait call
  -> resolve ImplId
  -> select concrete method
  -> apply substitutions
  -> monomorphize
  -> ordinary MIR call
```

Dynamic trait objects, object safety, witness tables, and vtables should be a
later and separately gated feature.

### 7.3 Parametricity

Generic code should use only operations granted by its constraints. A function
such as `identity<T>(value: T) -> T` cannot inspect or change an unknown `T`.
This rule must come from the type system rather than incidental emitter
behavior.

## 8. Async, Task, spawn, and channels

`async` cannot remain a function flag plus direct target syntax. Lowering needs:

```text
coroutine analysis
live-across-suspend analysis
coroutine frame layout
suspend point identities
start/resume/complete/destroy paths
cancellation path
exception propagation
debug source mapping
```

The language contract must define:

- whether a Task is hot or cold;
- whether one Task can be awaited more than once;
- when execution begins;
- how cancellation is observed;
- whether cancellation runs `defer` and `drop`;
- how child failure reaches its parent;
- whether channels are FIFO;
- whether channel sends copy or move values;
- how channel closure is represented;
- how a single-thread Wasm profile preserves semantics.

Two explicit execution profiles are preferable to one ambiguous operation:

```text
task-local     deterministic cooperative scheduling
task-threaded  platform-backed parallel scheduling
```

Canonical async events can be represented as:

```text
Ready(task)
Poll(task)
Suspend(task, reason)
Wake(task)
Complete(task, value)
Cancel(task)
```

Small programs can be model-checked across possible schedules instead of
depending only on nondeterministic real-thread tests.

## 9. Memory, ownership, and layout

The language specification must distinguish:

```text
value identity
object identity
address
storage
lifetime
ownership
borrowing
aliasing
mutation
initialization
drop
pointer provenance
```

Questions that require explicit answers include:

- whether nested arrays and structs are deep-copied;
- how function arguments and returns transfer values;
- how closure capture copies or borrows values;
- what moves into a coroutine frame;
- how long an FFI borrow remains valid;
- whether self-referential values are representable;
- which actions are permitted inside `unsafe`;
- whether safe code can exhibit a data race or use-after-free.

### 9.1 Layout engine

Logical type, storage layout, and calling convention should be independent:

```text
LogicalType
  Array<int>
  Option<User>
  Result<T, E>

StorageLayout
  size
  alignment
  field offsets
  discriminant
  payload layout

CallingConvention
  direct
  indirect
  sret
  scalar pair
  borrowed pointer
  owned pointer
```

Suggested modules:

```text
src/layout/model.py
src/layout/target.py
src/layout/engine.py
src/layout/abi.py
src/layout/verify.py
```

Rust or C++ implementation layout must not become Rove ABI by accident. A future
C-compatible representation should be an explicit ABI attribute backed by a
versioned RFC and conformance tests.

## 10. Backend legalization

Each backend should publish a machine-readable legal contract:

```yaml
backend: wasm
integer_width: 32
overflow: wrap
exceptions: false
threads: false
ownership: linear-memory-runtime
legal_mir:
  - scalar
  - structured-control
  - borrowed-array
reject:
  - unwind
  - native-pointer
  - threaded-spawn
```

Legalization must either:

1. convert an operation and its types to target-legal MIR; or
2. emit a stable capability diagnostic.

An illegal operation reaching an emitter is an internal compiler error. There
must be no silent fallback or approximate semantic mapping.

Recommended migration order:

```text
C++ -> LLVM -> Wasm -> Rust -> JavaScript -> Python -> C17
```

C++ first preserves the existing native oracle while exercising the full MIR
surface. LLVM and Wasm then force precise CFG, layout, and integer semantics.
Rust validates ownership mapping. JS and Python migrate after semantics no
longer depend on source-emitter shortcuts.

### 10.1 Backend portfolio beyond the current targets

Rove should distinguish a semantic backend, an ecosystem adapter, and an
interoperability profile. Producing another file extension is not by itself a
new useful backend.

```text
Semantic backend
  Own legalization, runtime mapping, output contract, and parity corpus.

Ecosystem adapter
  Reuses an existing backend while exposing another ecosystem's packages or
  type declarations.

Interop profile
  Uses a stable ABI to call or be called by another language.
```

#### Tier A: high-value semantic backends

| Target | Primary value | Main semantic mismatch | Recommended first form |
| --- | --- | --- | --- |
| Go | Services, command-line tools, networking, and Go packages | Rove lexical `defer`, Task behavior, exceptions, value copies, goroutines, and channels | Generated Go source |
| C#/.NET | .NET libraries, desktop/server applications, and a rich managed runtime | Value/reference distinction, generics, exception identity, Task cancellation, and disposal | Generated C# source |
| Java/JVM | Java/Kotlin libraries and the JVM deployment ecosystem | Boxing, erased/reified generic boundaries, class initialization, exceptions, and object identity | Generated Java source |

Go must not receive a direct syntax substitution for `defer`: Go executes
deferred calls when the surrounding function returns, while Rove lexical defer
is defined at scope exit. Go goroutines and channels are useful implementation
mechanisms, but Rove Task and Channel contracts remain authoritative.

C# Task exceptions, cancellation, value types, reference types, and disposal
require an explicit runtime adapter. A Rove `Result<T, E>` remains an ordinary
sum value and must not silently become a .NET exception.

The first JVM backend should emit Java source. Kotlin libraries are accessed
through JVM bindings; Kotlin does not initially require a second semantic
backend. Direct JVM bytecode becomes worthwhile only after stack-map frames,
verification, object layout, generics, and exception tables are understood and
covered by target-specific tests.

#### Tier B: strategic optional backends

| Target | Add when | Main blocker | Initial strategy |
| --- | --- | --- | --- |
| Lua | Embedded scripting, games, or modding becomes a primary direction | Dynamic tables, number policy, GC identity, errors, and coroutine semantics | Lua source plus a small runtime |
| Zig | Rove needs better C-library consumption or freestanding/native tooling | Error unions, comptime, allocation ownership, target ABI, and async differences | Zig source or C ABI adapter |
| Swift | Apple application and framework integration becomes important | ARC ownership, value semantics, async behavior, module resilience, and platform ABI scope | Swift source and generated C bridge |
| Ruby | Dynamic scripting and RubyGem integration has demonstrated users | Open classes, reflection, exceptions, block/closure semantics, and object identity | Ruby source or C-extension adapter |
| Dart | Flutter or Dart server consumers exist | Futures, isolates, GC values, null safety, and FFI ownership | Dart source plus `dart:ffi` bridge |
| BEAM | Actor/distributed systems become a product goal | Isolated processes, immutable messages, selective receive, supervision, and failure semantics | Erlang or Elixir source with a dedicated actor profile |

Lua is more valuable as an embedding target than as another general-purpose
source output. Its runtime contract must select an exact Lua version and define
integer, floating, table, coroutine, error, and garbage-collection boundaries.

Zig is attractive because it has explicit C ABI primitives and C translation
tooling. That makes it useful for Rove native interoperability, but it does not
remove the need for exact target triples, flags, ownership, and ABI validation.

Swift should not be described as universally ABI-stable. Swift's published ABI
stability commitment is platform-specific, historically centered on Apple
platforms. Rove should therefore prefer generated Swift source and a C boundary
before claiming portable binary interoperability.

BEAM deserves a separate actor-oriented target profile rather than pretending
that Rove shared-memory `spawn` and Channel behavior naturally matches Erlang
processes and mailboxes. Erlang processes use isolated mailboxes and selective
receive; adopting that model would be a semantic feature, not an emitter trick.

#### Tier C: adapters rather than duplicate backends

| Surface | Decision | Reason |
| --- | --- | --- |
| TypeScript | Extend the JavaScript backend's typed output | TypeScript erases types and preserves JavaScript runtime behavior, so a separate runtime backend adds little |
| Kotlin | Build a JVM ecosystem adapter first | Kotlin and Java interoperate on the JVM; a separate Kotlin emitter would duplicate JVM legalization |
| React/Vue/Svelte | Keep as generated web adapters | These are consumer frameworks, not independent Rove semantic targets |
| Objective-C | Reach through Swift/C adapters initially | A dedicated semantic backend provides limited new reach |

TypeScript declarations, source maps, ESM packaging, and typed host adapters
should therefore be features of the JavaScript/Wasm toolchain rather than a
second definition of Rove semantics.

#### Tier D: reference languages, not immediate output targets

Haxe and Nim are valuable comparison projects for language ergonomics,
conditional compilation, portable libraries, and multi-target design. Emitting
Haxe or Nim from Rove does not immediately unlock a unique runtime or package
ecosystem comparable to Go, .NET, or JVM, and would insert another compiler
between Rove and the final target.

They should initially be used for comparative conformance research:

```text
feature ergonomics
portable versus target-specific standard-library structure
conditional compilation boundaries
generated-code debugging
package and build integration
runtime footprint
```

#### Backend admission rule

A proposed backend enters implementation only when it has:

```text
1. A real consumer application.
2. A target semantic-difference document.
3. A target legalization profile.
4. A runtime and ownership mapping.
5. A package or FFI integration story.
6. Positive and negative conformance fixtures.
7. A maintained official toolchain in CI.
8. A reason it cannot be served by an existing adapter.
```

The recommended portfolio order is therefore:

```text
Finish shared MIR and current backends
  -> Go
  -> C#/.NET
  -> Java/JVM plus Kotlin bindings
  -> choose one demand-driven specialist:
       Lua for embedding
       Zig for native/C interoperability
       Swift for Apple platforms
       Dart for Flutter
       BEAM for actor systems
  -> reconsider the remaining targets using real adoption evidence
```

## 11. ABI and interoperability

Bundle ABI v1 should remain stable. More expressive interoperability should use
separately versioned contracts:

```text
Bundle ABI v1       current compatibility contract
Bundle ABI v2       richer Rove host ABI
WIT component mode  standardized Wasm component integration
```

FFI functions require machine-readable preconditions and postconditions:

```text
requires:
  pointer addresses `length` initialized bytes
  allocation remains live for the call duration

ensures:
  returned owned pointer belongs to the caller
  destroy may be called exactly once
```

C ABI should be the initial stable native boundary. Raw C++ or Rust ABI should
not be treated as cross-toolchain stable. Higher-level ecosystem imports should
use generated adapters, stable C shims, Wasm components, or explicitly pinned
same-toolchain profiles.

## 12. Standard library topology

The standard library should separate portable semantics from host adapters:

```text
std/core       available everywhere
std/portable   behaviorally equal implementations
std/sys        native/system targets
std/web        browser and Wasm hosts
std/node       Node.js host APIs
std/python     Python host APIs
std/jvm        future JVM adapters
std/dotnet     future .NET adapters
```

Target-specific code is acceptable inside controlled adapters. Target branches
should not spread through ordinary Rove application code. The compiler should
resolve capabilities and select adapters before target emission.

## 13. Incremental compilation

The compiler should become a deterministic query graph:

```text
read_source(SourceId)
  -> tokenize(SourceId)
  -> parse(ModuleId)
  -> collect_interface(ModuleId)
  -> resolve_names(ModuleId)
  -> typecheck_item(DefId)
  -> lower_hir(DefId)
  -> instantiate(InstanceId)
  -> lower_mir(InstanceId)
  -> legalize(Target, InstanceId)
  -> emit(CodegenUnitId)
```

Cache keys must include:

```text
compiler version
HIR and MIR schema versions
target triple and profile
optimization level
feature flags
source fingerprint
dependency interface fingerprints
runtime ABI version
```

Incremental caching should begin only after stable identities, deterministic
serialization, module boundaries, pure queries, and public interface hashes
exist. Otherwise a fast cache can produce stale or semantically invalid builds.

### 13.1 Compiler performance plan

Compiler speed must be improved from measurements, not from assumptions. Rove
should record cold and warm timings for tokenization, parsing, interface
collection, name resolution, type checking, HIR/MIR lowering, legalization,
code generation, and the external native compiler invocation. A benchmark
result is scoped to its machine, toolchain, corpus, and build profile; it is not
a universal compiler-speed claim.

The implementation order is:

1. Measure each compiler phase and retain a fixed benchmark corpus.
2. Cache parsed modules, collected interfaces, and typed HIR using the query
   keys above.
3. Invalidate only changed modules and declarations whose public interfaces or
   dependencies changed.
4. Lower and emit independent modules in parallel, while preserving
   deterministic output ordering and diagnostics.
5. Reuse native object files through an explicitly configured compiler cache
   such as `ccache` or `sccache` when the external toolchain supports it.
6. Emit target runtime support on demand. A generated unit must include only
   the helper families reachable from its legalized operations and selected
   capabilities; unused coroutine, Result, channel, HAL, MMIO, filesystem, and
   process support must not be copied into a scalar program. Keep an explicit
   full-runtime fallback until every fragment has dependency and parity tests.
7. Add a persistent compiler process/daemon only after query boundaries and
   cache invalidation are correct; it must not become a second source of
   compiler semantics.
8. Move the stable frontend path to the native `rovec` implementation in
   bounded slices, with differential parity against the reference frontend.

The first demand-driven C++ slice is implemented: a translation unit whose
only runtime surface is scalar/string `print`, CLI argument capture, and the
standalone-console guard receives a compact runtime. Any unknown helper,
aggregate, async function, native/foreign declaration, or advanced runtime type
falls back to the established full runtime. The exact `"Hello World" |> print`
probe shrank from roughly eight hundred generated lines to 122 lines and was
compiled and executed locally. This is a source-size result for one probe, not
yet a general compile-time benchmark or a completed runtime-fragment graph.

The first warm-build success criterion should be concrete: an unchanged
project must avoid parsing, type-checking, lowering, and native recompilation
for unaffected modules. Cache hits must still verify compiler version, target,
feature flags, dependency interfaces, runtime ABI, and source fingerprints.
Correctness and deterministic invalidation take priority over a fast but stale
build.

## 14. Debug information and provenance

MIR must retain source information from its first implementation:

```text
SourceSpan
InlineOrigin
LexicalScopeId
VariableDebugName
GeneratedFromNodeId
```

Required tooling:

```text
rove emit ast
rove emit hir
rove emit mir
rove emit mir --after cleanup
rove verify mir
rove explain E3001
rove explain-backend rust
rove compile --save-temps
```

Generated target locations should map back to Rove source ranges. Native LLVM
output should eventually emit DWARF or CodeView metadata. JavaScript should
emit source maps. Diagnostics from generated C++ or other source backends should
be translated back through a generated-range map.

### 14.1 CLI and toolchain UX

The CLI is a product boundary over compiler services, not a second semantic
implementation. Commands must call the same parser, resolver, Typed HIR, MIR,
legalization, package graph, diagnostics, and capability services used by the
library API. A CLI command may select and present a compiler stage; it may not
reimplement that stage or silently choose a different semantic fallback.

Intended command surface:

```text
rove
|-- new / init
|-- check
|-- build / run / clean
|-- test / bench
|-- fmt / lint / fix
|-- doc / debug / profile
|-- emit
|   |-- ast
|   |-- hir
|   `-- mir [--after <pass>] [--codegen --target <target>]
|-- inspect
|   |-- module-graph
|   |-- types
|   |-- capabilities
|   |-- layout
|   `-- mir
|-- verify
|   |-- mir
|   |-- package
|   `-- reproducible-build
|-- explain <diagnostic>
|-- explain-backend <target>
|-- prove optimization <pass-or-record>
|-- targets
|-- backend
|   |-- init
|   |-- verify
|   |-- test
|   `-- publish
|-- package / publish
|-- self-host
|-- doctor / version
`-- lsp / repl / tour
```

Current status must remain explicit:

| Command family | Status in the current CLI | Required next contract |
| --- | --- | --- |
| `new`, `init`, `check`, `build`, `run`, `clean` | Implemented | Workspace graph and incremental-query integration |
| `test`, `fmt`, `lint`, `doc`, `debug`, `profile` | Implemented bounded tools | Stable machine-readable reports and workspace-wide execution |
| `targets --json --mir` | Implemented | Resolve and display concrete capability plans, not only support tables |
| `emit mir [--json] [--codegen]` | Implemented experimental MIR surface | Named pass snapshots, provenance maps, and schema compatibility policy |
| `verify mir` | Implemented | Package, reproducibility, ABI, and backend-verification entry points |
| `emit ast`, `emit hir`, `inspect ast|hir|mir|module-graph|layout|types|capabilities` | Implemented read-only inspection v1 | Preserve stable schema envelopes, add named MIR pass snapshots, and replace direct feature checks with resolved capability plans when that resolver exists |
| `explain` | Implemented diagnostic catalog | Expand catalog coverage while preserving stable diagnostic codes |
| `explain-backend` | Implemented backend/MIR contract view | Add resolved capability-plan explanations when the resolver exists |
| `bench compiler`, `bench compiler-invalidation` | Implemented fixed-corpus stage-0 measurements | Add native `rovec`, backend/runtime and reproducible cross-machine benchmark contracts |
| `fix` | Planned | Machine-applicable edit contracts with preview and conflict handling |
| `prove optimization` | Planned research tooling | Proof-record schema plus interpreter/differential validation; never a marketing-only success message |
| `backend init/verify/test/publish` | Planned | Versioned backend SDK, conformance corpus, signing, and registry policy |
| `package`, `publish` | Planned | Reproducible package format, lockfile integrity, signatures, and registry authorization |
| `compile --save-temps` | Planned spelling | Preserve source maps and every selected stage without changing compilation semantics |

UX invariants:

- every mutating or networked command has an explicit dry-run or preview where
  practical, and destructive actions name their exact targets;
- human output and `--json` output are separate stable contracts;
- diagnostics retain stable codes, source spans, suggested fixes, and a direct
  `rove explain <code>` path;
- `emit`, `inspect`, `verify`, and `prove` are read-only unless an output path is
  explicitly supplied;
- target aliases resolve through the canonical target registry and every
  unsupported capability reports the rejected requirement and available
  alternatives;
- command help states backend maturity (`stable`, `beta`, `experimental`) and
  never presents source emission as semantic parity;
- exit codes distinguish invalid user source, unavailable toolchains, failed
  tests, internal compiler errors, and rejected capability plans;
- shell completion and LSP/editor actions are generated from the same command
  and diagnostic registries rather than duplicated lists.

CLI exit gate:

```text
Every documented command maps to one versioned compiler/toolchain service.
Human and JSON output have golden tests.
No command bypasses legalization, capability resolution, lockfile validation,
or the selected diagnostic policy.
Read-only inspection commands are deterministic for identical compiler inputs.
```

## 15. Reference interpreter and observable behavior

Stable semantics should not use the C++ emitter as the sole oracle. Rove needs a
small, deliberately slow MIR interpreter.

```text
Source
  -> Typed HIR
  -> MIR
  -> MIR interpreter
```

Every backend can then be checked against that interpreter.

Program behavior should be represented as an observable event trace rather
than only stdout:

```text
ReadFile(path, result)
WriteFile(path, bytes)
HostCall(namespace, function, arguments)
Print(text)
Spawn(task_id)
Suspend(task_id)
Resume(task_id)
Throw(type, value)
Return(value)
Trap(reason)
```

For deterministic sequential code, one program should have one trace. For I/O
or concurrency, the semantics may permit a set of traces.

## 16. Rove semantic constitution

Every operation must be classified as:

```text
defined behavior
implementation-defined behavior
compile-time error
catchable runtime error
trap
unsafe-only behavior
```

At minimum, the specification must settle:

- signed and unsigned overflow;
- division by zero and signed minimum divided by minus one;
- floating NaN, infinity, comparison, and conversion behavior;
- evaluation order for arguments, operands, and initializers;
- negative and out-of-range indexing;
- Unicode code point versus grapheme behavior;
- shallow versus deep value copying;
- drop and defer order;
- multiple exceptions during cleanup;
- FFI exception boundaries;
- data races and atomics;
- pointer provenance and invalid addresses;
- global initialization and module ordering.

Safe Rove should avoid undefined behavior. A valid safe program should produce a
defined value, structured error, defined trap, or compile-time rejection.

LLVM lowering must avoid unjustified `nsw`, `nuw`, `inbounds`, alias, lifetime,
and initialization assumptions. Otherwise an apparently safe Rove operation can
become LLVM poison or undefined behavior after optimization.

## 17. Abstract machine and operational semantics

Rove should have a target-independent abstract machine:

```text
MachineState {
  control: InstructionPointer
  stack: FrameStack
  heap: ObjectStore
  tasks: TaskSet
  scheduler: SchedulerState
  output: EventTrace
  exception: Optional<Exception>
}
```

Execution is a transition relation:

```text
State -> State'
```

A smaller formal core can be described with:

```text
Types:
tau ::= Unit | Bool | Int64 | Float64
      | Array tau
      | Struct S
      | Result tau tau
      | Task tau
      | tau -> tau

Expressions:
e ::= value
    | variable
    | let x = e in e
    | set place = e
    | if e then e else e
    | call e(e...)
    | return e
    | throw e
    | spawn e
    | await e

Runtime configuration:
<expression, environment, heap, continuation, scheduler>
```

High-level language features desugar into this core. The formal core, rather
than generated C++, defines Rove program meaning.

```text
for        -> iterator plus while
match      -> discriminant plus switch
?          -> Result switch
defer      -> explicit cleanup continuation
closure    -> environment struct plus function
async      -> coroutine state machine
trait call -> resolved function or witness call
```

Keeping this calculus deliberately small means proofs target a compact semantic
core instead of every surface-language spelling independently.

## 18. Type-system judgments

Typing can be expressed as:

```text
Gamma |- expression : Type ! Effects
```

That judgment states that an expression has a type and may produce a defined
set of effects under an environment.

Bidirectional checking separates synthesis from checking:

```text
Gamma |- expression => Type
Gamma |- expression <= ExpectedType
```

This is especially useful for contextual lambdas, generic calls, enum
constructors, collection literals, and overload resolution.

The formal metatheory should establish:

```text
weakening
substitution
canonical forms
progress
preservation
sequential determinism
```

## 19. Logical relations, memory reasoning, and separation logic

### 19.1 Logical relations

Generics, representation independence, and higher-order functions cannot be
fully validated with example programs alone. A logical relation can classify
related values and expressions by type:

```text
V[[tau]] = values related at type tau
E[[tau]] = expressions whose executions produce related results at type tau
```

For example:

```rove
fn identity<T>(x: T) -> T = x
```

A parametric logical relation expresses that this function cannot inspect an
unknown `T` except through capabilities granted by constraints. The same
technique can support reasoning about:

```text
generic parametricity
private representation hiding
optimizer equivalence
trait implementation equivalence
safe abstraction boundaries
```

### 19.2 Separation logic

Ownership can be modeled as exclusive resources rather than informal emitter
conventions. Separation logic expresses disjoint ownership with a separating
conjunction:

```text
owns(x, object_a) * owns(y, object_b)
```

A move transfers ownership:

```text
owns(x, object)
  -> owns(y, object)
```

After the transition, access through `x` can no longer be derived. A value copy
creates a distinct object with equal contents:

```text
owns(a, array_1)
  -> owns(a, array_1) * owns(b, array_2)
     and contents(array_1) = contents(array_2)
     and array_1 != array_2
```

Channel send can transfer ownership between tasks. Resource obligations can
ensure memory, locks, files, and foreign handles are released exactly once.

### 19.3 Step-indexed semantics

Recursive types, mutable references, closures, and asynchronous state may
require step-indexed logical relations:

```text
V[[tau]]_n
```

This means that a value behaves as type `tau` for at least `n` execution steps.
Induction proceeds over `n = 0, 1, 2, ...`, avoiding circular definitions for:

```text
recursive structs and enums
closures capturing closures
trait objects
mutable references
async tasks
higher-order FFI callbacks
```

### 19.4 Kripke worlds

Kripke worlds can track future-valid extensions of heap allocations, ownership
invariants, tasks, capabilities, and foreign resources.

```text
W = {
  allocated_locations,
  ownership_invariants,
  active_tasks,
  capability_tokens,
  foreign_resources
}

W <= W'
```

`W <= W'` states that execution has extended the world validly. It lets the
formal model ask whether a captured value remains valid when a closure is
called later, whether a suspended coroutine frame remains live, whether a
foreign handle survives between calls, and whether a capability was legally
transferred to another task.

## 20. Contextual equivalence and secure compilation

Two source programs are contextually equivalent when no valid Rove context can
distinguish them:

```text
P ~= Q
iff
for every valid context C, C[P] and C[Q] have equivalent observations
```

Compiler correctness should preserve observable behavior. A stronger secure
compilation goal is full abstraction:

```text
P ~=Rove Q
iff
compile(P) ~=Target compile(Q)
```

This prevents a target context from observing representation details that are
not observable in Rove, such as hidden object identity, padding, generated
fields, or raw linear-memory layouts.

Concrete leakage risks include:

- JavaScript object identity exposing a distinction that Rove value-copy
  semantics hide;
- Python reflection exposing generated storage fields;
- a C++ host reading padding or an internal discriminant;
- a Wasm host inspecting raw linear-memory representation;
- a Rust target exposing a target-specific drop order.

Complete full abstraction is a research-scale goal. Practical intermediate
steps are:

```text
representation hiding
capability isolation
checked FFI adapters
robust safety at component boundaries
versioned host contracts
```

## 21. Compiler simulation and semantic preservation

For each lowering stage, define a relation between source and target machine
states:

```text
HIR state H ~ MIR state M
```

If H takes a step, M should take zero or more corresponding steps and restore
the relation:

```text
H -> H'
M ->* M'
H' ~ M'
```

The complete compiler theorem should be composed from pass-local simulation or
refinement results:

```text
Typed HIR
  ~ Build MIR
  ~ Cleanup MIR
  ~ Canonical MIR
  ~ Target MIR
  ~ emitted target program
```

Depending on the transformation, the relation may be established with:

```text
forward simulation
backward simulation
bisimulation
trace refinement
```

For a representative HIR-to-MIR relation `H ~ M`, the expected local shape is:

```text
H -> H'
M ->* M'
H' ~ M'
```

One HIR step may therefore correspond to zero or more MIR steps while restoring
the relation afterward.

Important proof obligations include:

```text
type preservation
progress
ownership uniqueness
absence of use-after-free in safe code
race freedom under the safe concurrency model
cleanup exactly once
lowering simulation
backend behavioral refinement
```

## 22. Translation validation and proof-carrying passes

End-to-end formal verification of every optimizer is not required at the
beginning. A practical translation validator checks each concrete
transformation:

```text
before = MIR
after = optimize(before)

verify(after)
validate(after refines before)
```

Initial bounded validation can cover scalar values, finite heaps, bounded loop
iterations, and single-function transformations.

Passes may eventually produce certificates:

```text
transformed MIR
transformation certificate
```

A small checker validates the certificate. The optimizer may remain large and
untrusted while the checker becomes part of the trusted computing base.

## 23. Separate compilation and linking

Compiler correctness must eventually extend beyond a monolithic program:

```text
compile(A plus B)
  ~=
link(compile(A), compile(B))
```

The linker model must account for:

```text
symbol identity
duplicate definitions
visibility and re-exports
generic instance sharing
module initialization order
ABI agreement
runtime singleton state
foreign callbacks
dynamic loading
version skew
```

Correct modules must not become incorrect only because they were compiled
separately and linked later.

## 24. Trusted computing base

Formal claims are limited by the components that remain trusted:

```text
language specification
formal semantics
proof kernel
MIR verifier
certificate checker
backend validator
runtime
assembler and linker
operating system
hardware
```

The design goal is to move complexity outside the trusted core:

```text
large optimizer          untrusted
small certificate checker trusted

large backend            untrusted
small output validator   trusted
```

Proof-producing automation, tactics, and AI-generated proofs must be checked by
a small proof kernel. AI assistance then affects productivity but not the
validity criterion.

```text
large automatic prover
  -> produces proof term
  -> small kernel checks proof term

AI-generated proof            untrusted
optimization certificate      untrusted
small proof checker           trusted
Rove formal specification      trusted
```

A faulty tactic, optimizer, or AI agent may fail to produce an accepted proof,
but it must not be able to convince the kernel of an invalid theorem.

## 25. Bootstrap and reproducibility

The self-host chain should retain:

```text
Stage0 -> Stage1 -> Stage2 -> Stage3
```

Stage equality is useful but does not alone prove compiler correctness. The
trust analysis must include:

- whether Stage0 can inject behavior;
- whether compiler source and binary correspond;
- whether absolute paths, locale, timestamps, and environment leak into output;
- which runtime and standard library sources were used;
- whether independent bootstrap implementations agree.

A future diverse double compilation experiment can compare compilers produced
through independent bootstrap paths.

## 26. Conformance corpus

Tests should be organized by semantic feature rather than backend:

```text
tests/conformance/
  arithmetic/
  control_flow/
  functions/
  modules/
  generics/
  traits/
  ownership/
  arrays/
  strings/
  result/
  exceptions/
  async/
  ffi/
  diagnostics/
```

Each fixture should carry metadata:

```yaml
feature: result-propagation
targets: [cpp, js, python, rust]
profiles: [hosted]
expect:
  stdout: "42\n"
  exit_code: 0
  diagnostic: null
  mir_contains: [switch, return]
```

CI layers:

```text
PR smoke
feature parity
nightly differential and fuzz
release platform and ABI gates
long-running soak
```

A feature is complete only when parser, checker, HIR, MIR, verifier, legalizer,
backend, runtime, positive tests, negative tests, parity tests, and
documentation agree.

## 27. Generated and metamorphic testing

A typed random generator should produce valid HIR programs:

```text
generate typed HIR
  -> verify HIR
  -> lower MIR
  -> interpret MIR
  -> compile supported targets
  -> compare observations
```

An invalid-MIR mutator should verify that malformed states are rejected:

```text
remove a terminator
use a value after move
corrupt a block argument
read the wrong enum payload
skip required cleanup
resume a completed coroutine
```

Metamorphic properties include:

```text
alpha-renaming does not change behavior
adding an unused declaration does not change behavior
splitting a basic block does not change behavior
constant folding preserves behavior
dead-code elimination preserves behavior
parentheses do not alter defined evaluation order
```

Found failures should be automatically minimized into permanent regression
fixtures.

## 28. Suggested implementation modules

```text
src/mir/model.py
src/mir/types.py
src/mir/builder.py
src/mir/lowering.py
src/mir/cleanup.py
src/mir/verifier.py
src/mir/serialization.py
src/mir/printer.py
src/mir/interpreter.py
src/mir/passes.py

src/layout/model.py
src/layout/target.py
src/layout/engine.py
src/layout/abi.py
src/layout/verify.py

src/semantics/events.py
src/semantics/effects.py
src/semantics/capabilities.py

src/incremental/keys.py
src/incremental/queries.py
src/incremental/cache.py
src/incremental/graph.py
```

Formal work may eventually live in:

```text
formal/
  CoreSyntax.v
  CoreTypes.v
  CoreSemantics.v
  MemoryModel.v
  Effects.v
  Ownership.v
  Concurrency.v
  HIRSemantics.v
  MIRSemantics.v

  Lowering/
    HIRToMIR.v
    CleanupElaboration.v
    ClosureConversion.v
    CoroutineLowering.v
    Monomorphization.v

  Proofs/
    Progress.v
    Preservation.v
    Determinism.v
    RaceFreedom.v
    MemorySafety.v
    SemanticPreservation.v

  Extraction/
    ReferenceInterpreter.v
    MIRVerifier.v
    CertificateChecker.v
```

The proof assistant and final file extension are not decided by this document.
Rocq is a strong candidate because CompCert and Iris demonstrate relevant
compiler, ownership, and concurrency verification techniques.

## 29. M0-M8 execution map

This milestone map turns the architecture into bounded implementation batches.
Milestones are ordered by dependency. A later milestone must not compensate for
an incomplete invariant or semantic contract in an earlier milestone.

### M0: inventory, contracts, and feature manifest

Implementation status (2026-09-08): complete. The canonical registry is
[`compiler/features.toml`](../../compiler/features.toml), its deterministic
output is [`docs/generated/FEATURE_MATRIX.md`](../generated/FEATURE_MATRIX.md),
and `tests/feature_manifest_suite.py` rejects drift from compiler registries.
Stable identity rules are frozen in
[`M0_COMPILER_IDENTITIES.md`](M0_COMPILER_IDENTITIES.md). This milestone adds
no MIR implementation and does not alter the default compilation path.

Purpose: freeze the current observable surface before introducing another IR.

Work:

- inventory every AST and HIR node, type form, builtin, intrinsic, effectful
  operation, diagnostic, standard-library capability, and backend;
- introduce stable `SourceId`, `ModuleId`, `DefId`, `TypeId`, and `InstanceId`
  designs;
- create `compiler/features.toml` as the canonical machine-readable feature
  registry;
- record each feature's parser, checker, HIR, runtime, and backend status;
- preserve HIR schema v1, Bundle ABI v1, lockfile contracts, and stable backend
  behavior;
- classify existing behavior as defined, implementation-defined, rejected,
  trapped, or unsafe-only.

Exit gate:

```text
The feature matrix is generated from one canonical manifest.
Every existing stable behavior has a named conformance fixture.
No MIR implementation has changed default compiler output.
```

### M1: MIR skeleton and tooling

Implementation status (2026-09-09): complete for the M1 boundary. The
experimental implementation lives in `src/mir/`; `tests/mir_suite.py` covers
construction, malformed CFG rejection, canonical round-tripping, printing,
fingerprints, pass validation, and CLI subprocess behavior. The original
semantics-free skeleton remains available as `lower_hir_skeleton`; `rove emit
mir` now uses the subsequently completed executable lowering path. The default
HIR-to-backend route remains unchanged.

MIR schema v3 records `effects`, `is_async`, and target-independent coroutine
metadata on functions.
Lowering annotates these fields through target-independent fixed-point effect
inference before verification; hand-built unannotated fixtures remain accepted
for focused structural tests.

Purpose: create the representation without migrating production codegen.

Work:

```text
src/mir/model.py
src/mir/types.py
src/mir/builder.py
src/mir/lowering.py
src/mir/verifier.py
src/mir/serialization.py
src/mir/printer.py
src/mir/passes.py
```

- define functions, locals, places, blocks, statements, and terminators;
- require typed values, unique block identities, valid branch targets, one
  terminator per block, and retained source spans;
- provide deterministic textual and canonical serialized forms;
- add `rove emit mir` and `rove verify mir` behind an experimental path;
- fingerprint every pass input and output;
- keep all current emitters on the existing verified HIR route.

Exit gate:

```text
MIR round-trips deterministically.
The verifier rejects intentionally malformed fixtures.
The normal compiler path remains byte-for-byte unaffected where promised.
```

### M2: scalar and structured-control lowering

Implementation status (2026-09-09): complete for the scalar boundary.
`src/mir/lowering.py` constructs explicit CFG for scalar expressions, calls,
top-level code, branches, and loops. `src/mir/interpreter.py` is the executable
reference semantics. `tests/mir_lowering_suite.py` checks evaluation order,
i64 wrapping and division traps, malformed CFG rejection, and observed parity
with the existing C++ and LLVM oracles.

Purpose: prove the basic HIR-to-MIR path before ownership or async complexity.

Work:

- literals, local declarations, assignments, parameters, and returns;
- integer, floating, Boolean, comparison, and conversion operations;
- function calls and top-level execution;
- `if`, `while`, `break`, and `continue` CFG construction;
- strict left-to-right evaluation and single evaluation of effectful operands;
- defined overflow, division, cast, and trap behavior;
- a small MIR reference interpreter for this subset.

Exit gate:

```text
HIR and MIR interpreter observations agree.
C++ and LLVM scalar outputs agree with the MIR interpreter.
Malformed control-flow graphs are rejected before emission.
```

### M3: canonical desugaring and cleanup

Implementation status (through 2026-09-20): complete for the currently typed HIR
surface. Short-circuit/value control flow, null coalescing, literal match,
range iteration, guards, Result propagation, lexical defer chains, and
try/catch unwind edges are represented canonically in MIR. Potentially throwing
user calls are identified by a fixed-point HIR call graph. Their call and
`await` unwind edges enter cleanup trampolines before either a catch destination
or an unhandled rethrow; a defer that throws does not recursively execute itself. Source-owned
parameters, locals, collection-loop bindings, catch bindings, and payload
bindings receive lexical deinit on every initialized exit path.
`tests/mir_cleanup_suite.py` checks normal, return, break, continue, direct
throw, interprocedural call-unwind, and pattern/catch exits. Aggregate patterns,
collection iteration, and projected safe navigation are completed by M4 because
they require aggregate places and variant payloads.

Purpose: remove repeated semantic lowering from individual emitters.

Work:

- short-circuit `and` and `or`;
- value-producing `if` and `match`;
- `guard`, destructuring, safe navigation, and null coalescing;
- postfix Result propagation;
- lexical `defer` cleanup chains;
- `try`/`catch`, normal edges, unwind edges, panic, and trap separation;
- `for` lowering through a defined iterator protocol;
- cleanup correctness for return, throw, break, continue, call unwind, and
  suspend unwind.

Exit gate:

```text
Canonical MIR contains no structured constructs assigned to this milestone.
Every exit path executes each required cleanup exactly once.
Emitters no longer independently lower these source semantics.
```

### M4: aggregates, ownership, memory, and ABI

Implementation status (through 2026-09-19): the M4 exit gate is closed for the
declared stable targets (C++20, Node.js ES2022, and Python 3). MIR carries
struct/enum definitions, aggregate construction,
field/index/dereference/variant projections, and explicit copy, move, borrow,
retain, release, deinit, and drop operations. The verifier performs
conservative CFG-wide initialization and move-state analysis. `src/mir/layout.py`
defines deterministic native-x64, hosted-x64, and wasm32 storage layouts;
`src/mir/abi.py` classifies direct/indirect/sret calls, preserves Bundle ABI v1,
and exposes Bundle ABI v2 only as a draft. `tests/mir_memory_abi_suite.py`
covers value-copy behavior, aggregate loops, payload enums, move/drop failures,
layout offsets, calling conventions, and checked C adapter boundaries.
`tests/mir_legalization_suite.py` executes flat and nested array/struct copy
isolation, projected mutation, enum-wrapped structs, and array-bearing Result
behavior against the MIR interpreter on all three stable targets.

Purpose: make value semantics and physical representation explicit.

Work:

- arrays, structs, payload enums, Option, and Result layouts;
- places for field, index, dereference, and variant projection;
- explicit copy, move, borrow, retain, release, and drop operations;
- initialization and move-state analysis;
- target-independent logical types and target-specific storage layouts;
- argument, return, indirect return, and ownership calling conventions;
- Bundle ABI v2 design without breaking Bundle ABI v1;
- explicit C-compatible FFI representation and checked adapter contracts.

Exit gate:

```text
Array and struct value behavior is identical across stable targets.
The verifier detects use-after-move and double-drop states.
ABI fixtures validate size, alignment, field offsets, and ownership transfer.
```

### M5: backend migration through legalization

Purpose: make MIR the shared semantic source while retaining target-specific
representations and runtimes.

Migration order:

```text
C++ -> LLVM -> Wasm -> Rust -> JavaScript -> Python -> C17
```

Work:

- define legal operation, type, effect, runtime, and ABI profiles per backend;
- create target legalization passes rather than emitter fallbacks;
- reject every unsupported operation with a stable capability diagnostic;
- migrate one backend at a time while the old path remains available as an
  oracle;
- delete repeated emitter lowering only after differential parity passes;
- retain C++ as the default until release gates justify a change.

Exit gate:

```text
No illegal MIR operation reaches an emitter.
Every migrated backend passes positive, negative, runtime, and parity corpora.
Fallback to approximate target semantics is impossible.
```

Implementation status (through 2026-09-25):

- `src/mir/legalization.py` publishes versioned operation, type, runtime,
  ownership, effect, and ABI profiles in the required migration order;
- legalization contract schema v3 publishes explicit binary and unary
  operation allowlists plus legal effect sets for every target, so unknown
  operations and unsupported effects are rejected before emitter dispatch
  rather than failing inside generated code;
- stable `MIRG1000`-`MIRG1011` diagnostics reject unknown targets, missing
  profiles, illegal types/operations/projections, unsupported runtime calls,
  unwind edges, unavailable emitters, emitter-contract violations, and effects
  without a target lowering;
- `src/mir/codegen_cpp.py`, `src/mir/codegen_llvm.py`, and
  `src/mir/codegen_wasm.py`, `src/mir/codegen_rust.py`,
  `src/mir/codegen_javascript.py`, `src/mir/codegen_python.py`, plus
  `src/mir/codegen_c17.py` are real consumers of legalized MIR. LLVM's generated
  internal types and helper symbols now use `rove_` names; the separately
  versioned Bundle ABI v1 identities are unchanged. The C++
  and LLVM shared pilot scope begins with scalar values,
  explicit CFG control flow, calls, assertions, wrapping `int64` arithmetic,
  division traps, strings, floats, and canonical `print` output. The C++ pilot
  additionally legalizes arrays, checked index projections, structs, fields,
  optionals, payload enums, `Result`, lexical cleanup CFG, direct caught throws,
  and interprocedural call-unwind edges. A dedicated user-throw carrier keeps
  language exceptions distinct from runtime traps. LLVM additionally legalizes
  acyclic nominal structs with scalar or nested-struct fields, by-value
  construction/copy/return, chained field projection, and projected mutation
  using named LLVM types, `insertvalue`, and typed `getelementptr`. Its first
  ownership-bearing aggregate slice covers
  recursively nested `Array<int|bool|float|string|acyclic-struct>` through
  typed `{data, length}` descriptors with allocation, bounds-checked indexing,
  `len`, deep copy on MIR copy
  operands, by-value calls/returns, and move-preserving descriptor transfer.
  Nested-array and struct-array clones recursively clone each element rather
  than copying descriptor bytes, so values such as `Array<Array<int>>` and
  `Array<StructWithArray>` remain isolated across
  aggregate construction, assignment, calls, returns, and tagged payloads.
  The `float`/`f64` array slice uses binary64 elements in the same descriptor
  and clone/destroy path. Its executable fixture covers copy isolation,
  projected mutation, indexing, `len`, nested arrays, and array-bearing
  struct, enum, and Result values across admitted backends. Optional float
  arrays remain rejected by LLVM legalization until their representation is
  specified.
  Nominal structs may contain admitted array descriptors and recursively clone
  ownership-bearing fields while preserving scalar/string fields. Recursive
  by-value and recursive array/struct cycles remain rejected by legalization.
  Nominal-struct display uses `TypeName(field1, field2, ...)` in declaration
  order, recursively applying the existing scalar/array/tagged display rules.
  The MIR interpreter, C++, LLVM, Rust, JavaScript, Python, and C17 now use this
  display contract for direct structs, arrays of structs, and struct payloads
  in enum and Result values. The C17 executable gate also covers primitive
  arrays, empty enum variants, and multi-primitive enum payloads. C++, LLVM,
  Rust, JavaScript, Python, and C17 also implement `to_string(Struct)` with the
  same form. LLVM routes `print` and `to_string`
  through one typed display path; the latter captures UTF-8 output in a
  growable runtime buffer. Captured LLVM strings remain process-owned until
  string lifetime tracking is part of this pilot; repeated `to_string` calls
  can retain those buffers. Rust's generated `RoveDisplay` implementations
  pass metadata/type checks on this host; executable Rust
  parity remains unverified here. C17 shares one typed display path between
  `print` and `to_string`, with an owned capture buffer tracked by its existing
  allocation runtime. Wasm still rejects `print` of nominal structs. The MIR
  interpreter, C++, LLVM, Python, C17, and Rust emitters now follow the existing
  source scalar-text contract: integral floats omit `.0`, either zero sign
  prints as `0`, and shortest round-tripping decimals
  use fixed notation for magnitudes in `[1e-6, 1e21)`. Scientific exponents
  omit padding and retain `+` for positive exponents. C++ uses `to_chars`;
  C17 and LLVM select the first decimal precision that round-trips through
  binary64. The local C++/C17/LLVM/JavaScript/Python runtime gate covers an
  explicit contract oracle, boundary bit patterns, and 512 seeded binary64
  patterns against the MIR interpreter. The tested `print` paths include LLVM;
  `to_string` and nested aggregate coverage apply only to admitted backends.
  Rust passed generated-code metadata/type checking, but executable Rust float
  parity is unverified on this Windows host. LLVM's captured `to_string` path
  has executable struct/array/tagged/float coverage; this does not establish
  full backend parity. The seeded runtime gate is
  evidence on the tested standard libraries, not a cross-platform proof.
  Legalization rejects unsupported display shapes before backend emission.
  C++'s tagged payload printer now dispatches the MIR types present in the
  module, including recursively nested struct arrays, and reports an unsupported
  runtime value instead of silently printing `<payload>`.
  Explicit
  non-unwinding MIR `DeinitStatement` and `DropTerminator` operations release
  array storage and recursively destroy ownership-bearing struct fields. Source
  lowering now inserts `DeinitStatement` for ownership-bearing source parameters
  and lexical bindings on normal fallthrough, return, break, continue, throw,
  catch, collection-loop and pattern-binding exits. It also deinitializes an old
  whole-local or projected field/index value after the replacement expression is
  evaluated and before the assignment overwrites it. Projected replacement is an
  atomic MIR contract: projected `DeinitStatement` must be immediately followed
  by assignment to the same place (`MIR0805` otherwise). Deferred expressions run
  before lexical deinit so they may still observe live bindings. Ownership-bearing
  compiler temporaries with a direct single consumer transfer through `MoveOperand`;
  ignored owned expression results receive explicit deinit. Branch-specific
  cleanup now covers safe-navigation/null-coalescing bases, Result propagation
  values and discriminant tags, match-statement subjects/tags, and match-expression
  subjects. An ownership-bearing null-coalescing fallback transfers its temporary
  into the join result instead of leaving a hidden copied allocation. Collection
  and projected-base temporaries are attached to the surrounding lexical cleanup
  frame. Match-statement and match-expression comparison patterns now keep
  ownership-bearing temporaries live through equality and deinitialize them
  immediately afterward; match-statement pattern calls also keep owned subjects
  and tags in the unwind cleanup frame. The M3 structural gate checks all three
  comparison paths and the caught-throw edge. Statement-match `_` and named
  fallback arms now parse without lambda ambiguity; named arms retain the
  subject type, move an owned temporary into the binding (or copy a source
  local), and clean up the binding on exit. Both HIR and source checking require
  a fallback arm to be final. Legacy `"_"` remains an `IRLiteral` in Typed HIR
  v1 for byte compatibility, while MIR treats it as a fallback. Comparison
  patterns must have a subject-compatible type; an `int` pattern against a
  `float` subject receives an explicit MIR cast. Mixed `int`/`float` binary operands
  are likewise converted before their MIR operation. LLVM legalization rejects
  mismatched operands before emission, and C17/Rust lower the `int`-to-`float`
  cast. The fixture exercises these paths, a tagged-Result
  fallback and an exhaustive named arm returning a value through the MIR
  interpreter and executable C++/JavaScript/Python gates; Rust passes
  source/metadata checks on this Windows host. The integral-valued float
  display discrepancy is corrected in the interpreter/C++/LLVM/Python/C17
  paths. Rust's normalization passes metadata/type checking but still needs
  executable confirmation. A
  directly-awaited temporary `Task<T>` is now closed on both its resume
  and suspend-unwind paths, while a named task stays live for repeated awaits
  until its lexical cleanup. This does not yet claim complete lifetime
  elaboration for every multi-use/control-flow-joined temporary. Projected moves
  now fail with stable `MIR0806` instead of silently treating a field move as a
  whole-root move; general place-sensitive partial moves remain future work.
  Unwind-capable drop terminators and arena reclamation also remain open.
  A bounded tagged-value ABI (`{tag, four i64 payload slots}`) covers
  primitive/string `Result` and nominal-enum construction, copying,
  discriminant switches, payload projection, calls, returns, and canonical
  `Tag(payload)` display. Up to four primitive/string, supported array, or
  acyclic nominal-struct payloads share the fixed slots; aggregate payloads are
  boxed behind typed pointers. Type-specific clone/destroy helpers deep-copy all
  boxes in the active variant at MIR copy boundaries, release every payload and
  box during deinit/drop, and leave scalar alternatives on the same ABI. Payload
  extraction clones from a borrowed tag, so matching a value cannot alias or
  consume the original. Primitive arrays use canonical
  `[item, ...]` display both directly and inside `Tag([item, ...])`. Moved
  ownership-bearing arguments to LLVM `print` and `len` are destroyed after the
  builtin consumes them instead of leaking a compiler temporary. LLVM `len`
  accepts strings as well as admitted arrays, closing executable parity for the
  shared nested struct-enum and `Result<Array<int>, string>` fixture. Direct,
  array-element, enum-payload, and Result-payload nominal-struct display now
  matches the MIR interpreter's positional `TypeName(...)` form in an
  executable LLVM fixture.
  Recursive array display for bool/string elements now uses the same Rove
  formatting in the MIR interpreter and Python MIR runtime as in LLVM and
  JavaScript; a direct and tagged nested-array fixture checks executable
  parity across those four paths.
  LLVM-specific contract checks now reject invalid
  scalar operator/type pairs, unsupported casts, recursive by-value structs,
  malformed `len` calls, non-printable aggregates, and invalid field/index
  projections before emitter dispatch;
- the C++ async adapter consumes canonical suspend and suspend-unwind edges
  through a shared lazy `task<T>` state. Execution occurs once on first await,
  repeated awaits replay the stored value or exception, and only `user_throw`
  enters a Rove catch path;
- the C++ ownership mapping covers borrow/dereference, copy/move, deinit, and
  non-unwinding drop. Explicit MIR retain/release operations map to C++ RAII
  copy/move/destruction instead of emitting a second reference-counting layer;
- the Rust ownership mapping now lowers copy to `Clone`, move to typed
  `std::mem::replace` (including non-`Default` `Result<T, E>` values),
  retain/release to Rust value semantics, and explicit deinit
  and non-unwinding drop without introducing a second reference-counting layer.
  Borrow/dereference uses a typed `RovePtr<T>` carrier that preserves the MIR
  mutable-borrow check instead of exposing an unchecked raw pointer surface.
  User `throw` and call-unwind edges use an explicit `RoveCallResult<T>` carrier;
  caught Rove throws are routed to the MIR error destination while unrelated
  Rust panics remain outside the language exception path. Source-language
  `Result<T, E>` values use native typed Rust results, including canonical
  tagged display (including nested arrays), discriminant/payload access, and safe re-homing when the
  unused inferred branch is temporarily `any`. The first Rust async adapter
  consumes canonical `SuspendTerminator` edges through a lazy memoized
  `RoveTask<T>` carrier, preserving repeated-await results and routing task
  throws through explicit suspend-unwind destinations;
- every migrated backend now consumes explicit non-unwinding MIR deinit/drop
  operations for its admitted value surface. C++, Rust, and LLVM use their
  native/destructor adapters; JavaScript and Python clear host references; C17
  clears the value while its tracked allocator retains process-exit ownership;
  Wasm clears local descriptors and legalized projected field/index storage
  while its current bump arena retains module-lifetime ownership. This is
  operation parity, not a claim of equivalent reclamation timing;
- the first Wasm slice accepts pure `int`/`bool` functions, user calls, and
  dispatcher-based CFG. It emits both WAT and binary Wasm; the later bounded
  aggregate runtime described below admits specific strings, casts, and heap
  values while unrelated host calls and unsupported heap shapes remain rejected
  at legalization.
  String `+` allocates a fresh UTF-8 descriptor and copies both byte ranges;
  equality and ordering compare descriptor contents byte by byte, so equal
  strings in distinct allocations compare equal. The executable gate covers
  copied fields, concatenation, empty strings, prefixes, and UTF-8 ordering.
  Wasm legalization checks operand and result types for scalar binary/unary
  operations before emitter dispatch and reports `MIRG1010` for an unsupported
  pair. These allocations follow the pilot's existing module-lifetime arena.
  Scalar `float`/`f64` now lowers to Wasm `f64` for arithmetic, comparisons,
  unary sign, and signed `int`-to-`float` conversion. Executable parity checks
  include mixed `int`/`float` expressions and numeric `match` patterns,
  large integer rounding, signed zero, division by zero, and NaN.
  Float remainder remains rejected with `MIRG1010` until its `fmod` semantics
  has a runtime adapter.
  The aggregate slice supports `Array<int>`, `Array<bool>`, `Array<float>`,
  `Array<string>`, and `Array<struct>` through a wasm32
  `{data, length, capacity}` descriptor, deep copy, move clearing,
  bounds-checked index reads/writes, descriptor-aware immutable UTF-8 string
  elements, inline layout-sized struct elements, detached element copies, and
  `len`. Float elements use binary64 loads and stores, with byte-exact copies.
  Recursively nested int, bool, float, string, and nominal-struct arrays
  deep-clone every inner descriptor and data allocation and accept checked
  multi-index reads/writes. The executable gate covers three to five array
  levels, empty arrays, detached projected copies, and by-value calls/returns;
  an inner array read first resolves the checked element address, then makes a
  detached copy. Other aggregate element types remain rejected before emitter
  dispatch. An explicitly typed empty literal such as
  `let values: Array<float> = []` now receives its concrete element type in
  Typed HIR, before MIR lowering; the Python and self-hosted Rove HIR paths
  pass the same parity case. Structs with int, byte-sized bool, binary64 float,
  and immutable UTF-8 string fields use deterministic wasm32 field offsets,
  width-correct `i32.store8`/`i32.load8_u` bool access, descriptor-aware field
  construction/assignment, byte-level value copies, and checked field selection.
  Nested nominal structs are stored inline and chained field projections use
  layout-derived offsets while preserving outer value-copy isolation. Structs
  may also own supported arrays, including nested arrays and arrays of structs
  with array fields. Type-specific clone helpers recursively detach these fields
  through struct and array copies, calls, returns, and field assignments;
  mixed field/index projection chains use checked element addresses. The
  executable gate includes a finite `Array<Node>` recursive value, empty
  fields, projected writes, detached array elements, and invalid-index traps.
  Enum and Result payloads containing an array-owning struct remain rejected
  until tagged copies receive the same deep-clone path. Nominal enums with int payloads or one
  bool/float/immutable string/nominal-struct payload keep their canonical named MIR tags while Wasm
  legalization maps them to deterministic `i32` discriminants and stores
  payloads at layout-defined offsets. Results with int, bool, float, string, or
  nominal-struct payloads share the same tagged representation and are verified on both `Ok` and `Err`
  control-flow paths.
  When typed-HIR inference temporarily introduces `any` on the unused Result
  branch, Wasm cast legalization re-homes the tag and payload into the target
  layout rather than treating unequal layouts as the same pointer.
  WebAssembly-native masked shifts now match the canonical signed-i64 rule.
  Checked division/remainder helpers preserve Rove's
  divide-by-zero trap and signed `MIN / -1` wrapping contract;
- `rove emit mir <file> --codegen --target cpp|llvm|wasm|rust|js|python|c` exposes the
  textual pilot artifacts without changing the default Typed HIR compilation
  route;
- C++ and LLVM pilot output is compiled and executed against both the MIR
  interpreter and the legacy C++ backend oracle in
  `tests/mir_legalization_suite.py`;
- Wasm binary output is instantiated and executed by Node's WebAssembly engine
  against the MIR interpreter. The established Bundle ABI suite remains green;
- the Rust 2021 pilot maps scalar values, strings, copy/move operands, wrapping
  integer arithmetic, user calls, `print`, and MIR CFG through a Rust `match`
  dispatcher. Generated source is compiled and executed by `rustc` against the
  MIR interpreter and the shared numeric corpus. Its first aggregate slice maps
  arrays to `Vec<T>`, structs to generated nominal Rust types, nullable values
  to `Option<T>`, source results to `Result<T, E>`, and Rove copy boundaries to
  explicit clones. Payload enums and results use typed variant extraction.
  Rust async functions lower to lazy shared tasks whose result or user throw is
  evaluated once and replayed on subsequent awaits;
- the Node.js ES2022 pilot preserves Rove `int` as 64-bit `BigInt` rather than
  lossy JavaScript `number`, including wrapping arithmetic, signed division,
  remainder, shifts, scalar CFG, user calls, and canonical `print` formatting.
  Its aggregate slice uses checked array/field projections and explicit deep
  copies so host object aliasing cannot violate Rove value semantics; tagged
  payload objects preserve enum, Option, and Result discriminants and use the
  canonical `Tag(payload)` display form, including nested numeric arrays. Async
  functions return lazy memoized `RoveTask` objects rather than eager host
  promises, so repeated awaits replay one result and suspend-unwind catches only
  Rove user throws;
- the Python 3 pilot explicitly normalizes arbitrary-precision Python integers
  to Rove signed i64 after arithmetic, preserves truncating signed division and
  remainder, and executes scalar CFG, user calls, and canonical output. Arrays,
  structs, optionals, projected mutation, iteration, and copies execute against
  the MIR interpreter with `deepcopy` at Rove copy boundaries. Tagged payload
  dictionaries preserve enum, Option, and Result discriminants. A lazy
  canonical formatter renders those dictionaries as `Tag(payload)` instead of
  leaking the host representation. A lazy memoized Python task carrier consumes the same suspend and suspend-unwind MIR
  edges while preserving host exceptions outside Rove catch blocks;
- the C++, Rust, JavaScript, and Python pilots lower interprocedural user
  `throw`/`catch` and supported suspend-unwind through dedicated carriers and
  canonical cleanup trampolines, preserving lexical cleanup output while
  leaving host runtime failures outside the language catch path;
- the experimental Rust, JavaScript, and Python MIR Task adapters now emit
  `RoveTask` names consistently. The local M5 legalization suite passed after
  this naming change; Rust was type-checked as metadata only because runtime
  linking is unavailable on this Windows host. This does not close the M5
  semantic-parity gate;
- a direct `throw` now transfers its evaluated value into a temporary outside
  lexical drop frames before `defer` and deinit run. This prevents a local
  `string` throw from reading a moved value after cleanup. The M3 cleanup suite
  and M5 interpreter/C++/JavaScript/Python parity checks pass for a caught
  owned-local throw; generated Rust passes metadata/type checking. General
  multi-use temporary lifetime analysis and drop-unwind edges remain open;
- owned operands of calls, array literals, and non-short-circuit binary
  expressions now remain in the lexical cleanup frame while later operands are
  evaluated left to right. A later throw deinitializes earlier temporaries;
  Result `?` also closes earlier call arguments before early return. Once all
  operands are ready, the pending cleanup is removed and the consuming operation
  receives each move. The M3 cleanup suite checks the unwind/early-return edges,
  and M5 interpreter/C++/JavaScript/Python parity fixtures pass; Rust generated
  code passes metadata/type checking. This covers ordered operand evaluation,
  not general temporary-lifetime elaboration;
- the C17 pilot uses explicit unsigned-bit conversion for defined signed-i64
  wrapping, masks shifts, handles the signed division edge, tracks temporary
  concatenated strings, and compiles real scalar CFG with Clang in C17 mode.
  Its aggregate slice emits acyclic nominal C structs with int, bool, float, string,
  and recursively nested nominal-struct fields, including construction,
  by-value copies, field reads, and projected field assignment. Declarations
  are dependency ordered and recursive by-value layouts are rejected. Direct
  arrays of int, bool, float/f64, and string plus recursively nested arrays of primitives
  or supported structs are legal struct fields; generated
  recursive clone helpers preserve their value isolation through struct copies,
  arrays of structs, function boundaries, and boxed tagged payloads. Natural
  nested generic closers such as `Array<Array<int>>` are parsed contextually
  without changing expression-level right-shift semantics;
  Arrays of int, bool, float/f64, string, and supported nominal structs, including nested
  combinations of those array types, use explicit
  `{data, length}` representations, tracked allocation, deep value copies,
  checked constant/dynamic index reads and writes, and `len`. Tagged enum,
  Option, and Result values preserve their discriminants. Enum variants may
  carry multiple indexed int, bool, float/f64, immutable string, supported
  array, and nominal-struct payloads. Each array or struct payload occupies its
  own boxed slot; the executable gate covers mixed scalar/object slots,
  copied enum values, match extraction, and display. Unsupported aggregate
  leaves remain rejected. C17 now renders
  admitted arrays, structs, and tagged payloads recursively through typed
  `rove_print_value_*` helpers for both stdout and captured `to_string` output;
  its generated internal types and helpers use
  the Rove name while the established `__nyx_top_level` entry identity remains
  unchanged;
- remaining multi-use/control-flow compiler-temporary lifetime elaboration, general
  place-sensitive partial-move/drop analysis, drop unwind edges, per-allocation
  reclamation for arena-backed targets,
  remaining Wasm aggregate combinations such as array-bearing tagged payloads,
  Wasm nominal-struct printing, and broader
  target runtime surfaces remain
  open M5 work. Every migration-order target now has a bounded executable pilot;
  none of those pilots imply full backend parity. C++, Rust, JavaScript, and
  Python have bounded lazy, memoized Task adapters for the shared
  coroutine-frame/suspend contract. LLVM, Wasm, and C17 still reject
  `may_suspend` with `MIRG1011`; emitters may not improvise async semantics
  independently.

Therefore M5 infrastructure, the broad C++ slice, LLVM scalar path, and first
executable Wasm, Rust, JavaScript, Python, and C17 slices are implemented. The M5 exit gate
remains open until the full MIR surface and each listed backend complete
differential parity.

### M6: vertical language-surface expansion

Purpose: resume source-language growth without recreating backend duplication.

Candidate order:

```text
closures
generic constraints
static trait dispatch
iterator protocol and yield
visibility and module exports
named arguments
async state machines
channels and select
```

Every feature must complete one vertical slice:

```text
grammar
parser
name resolution
type checker
Typed HIR
MIR lowering
MIR verification
target legalization
runtime
positive tests
negative tests
cross-target parity
documentation
```

Exit gate:

```text
A feature cannot be marked supported from syntax or one emitter alone.
The feature manifest and generated capability documentation agree with tests.
```

### M7: standard library, packages, and ecosystem adapters

Purpose: turn compiler capability into applications people can actually build.

Work:

- split `std/core`, `std/portable`, `std/sys`, and host-specific adapters;
- expand collections, iteration, strings, paths, processes, networking, time,
  serialization, and concurrency under consistent Result contracts;
- generate typed binding manifests and adapter stubs;
- preserve deterministic package resolution, checksums, and offline operation;
- add WIT Component Model output as a separate Wasm profile;
- provide real native CLI, server, embedding, package, and web consumers;
- keep target-specific implementation code behind capability boundaries.

Exit gate:

```text
Portable APIs have defined cross-target observations.
Host-specific APIs fail at capability checking rather than late emission.
Each supported ecosystem has at least one real end-to-end consumer.
```

### M8: new backends, verification, and promotion

Purpose: add ecosystems only after the shared semantic path is stable.

Backend order:

```text
Go -> C#/.NET -> Java/JVM
```

Lua may move earlier only if embedded scripting becomes a primary product
direction. Initial Go, C#, and Java implementations should emit source and use
their official toolchains. Direct CIL or JVM bytecode emission is a later
optimization, not an initial requirement.

Work:

- require a target legalization profile and runtime adapter before an emitter;
- use a concrete acceptance application for every new backend;
- add translation validation for critical MIR optimizations;
- begin formalizing the scalar/control-flow Rove Core;
- extract or implement a trusted reference interpreter and MIR verifier;
- require clean platform CI, reproducible artifacts, checksums, SBOM, and
  provenance before maturity promotion.

Exit gate:

```text
A backend is not promoted because it merely produces a file.
It must compile, run, reject unsupported semantics, and pass differential tests.
Formal claims clearly identify their trusted computing base and proof boundary.
```

## 30. M9-M24 platform scale roadmap

M0-M8 establish the semantic core. M9-M24 extend that core into a complete
toolchain and platform. These are roadmap commitments, not current support
claims; a track becomes implemented only after its own executable gate passes.

### M9: optimizer architecture

Build a target-independent optimization layer after canonical MIR and before
target legalization. The intended pipeline is:

```text
Canonical MIR -> Optimization MIR -> derived SSA -> analyses -> transforms
  -> verified MIR -> target legalization
```

Required foundations are dominator trees, liveness, call-graph and loop
analysis, constant propagation, dead-code elimination, inlining policy, LICM,
SROA, bounds-check analysis, escape analysis, and a conservative alias model.
SSA is a derived representation; ownership and canonical control-flow
invariants remain authoritative. Every transform needs before/after
fingerprints, negative verifier cases, and differential observations.

### M10: cross-compilation, target model and capability resolution

Replace ad-hoc target names with a versioned `TargetSpec` containing:

```text
architecture, operating_system, environment, ABI, endian, pointer_width,
cpu_features, object_format, linker, sysroot, libc, freestanding
```

`rove build --target` must resolve a canonical target triple, select a layout,
legalization profile, runtime, linker and artifact naming policy. Hosted,
WASI and freestanding targets must be separate profiles; a native C++ emitter
alone is not evidence of embedded support.

The current capability registry is a target-feature contract: it can answer
whether a named feature or standard-library module is supported and it rejects
unsupported combinations. It is not yet a resolver. The planned resolver must
turn an abstract request into an explicit, inspectable plan before MIR
legalization:

```text
CapabilityRequest -> CapabilityResolver -> CapabilityPlan -> legalization
```

The request language must distinguish three relations:

```text
requires   a capability is mandatory
one_of     one explicitly permitted implementation must be selected
optional   use the capability when available; otherwise use the defined absence path
```

Resolution must use a declared preference order and may select a runtime
adapter only when that adapter advertises the required semantic contract. For
example, `parallel_execution` may select native threads, Wasm threads or
cooperative tasks only if the program explicitly permits those alternatives;
the resolver must not silently replace threaded semantics with a single-thread
approximation. A scalar implementation of SIMD may be an automatic fallback
only when the observable semantics are proven equivalent. Every selected
provider, adapter, fallback reason and target assumption must be recorded in
the plan and available to diagnostics (`rove explain`).

No emitter may re-decide capability selection. If no permitted provider can
satisfy the request, compilation must stop with a stable capability error.
Resolver tests must cover positive selection, preference ordering, rejected
fallbacks, adapter contracts, plan serialization and target reproducibility.

### M11: build system and workspaces

Define the build graph for `rove build`, multi-package workspaces, build scripts,
feature flags, debug/release profiles, target-specific dependencies, artifact
caches and deterministic parallel scheduling. The graph must distinguish
source, interface, implementation and generated-artifact fingerprints and must
never execute an untrusted build script without an explicit capability policy.

### M12: package platform

Extend the existing lockfile, offline cache and checksum foundations into a
registry protocol with `rove publish`, `rove search`, `rove update` and `rove audit`.
The contract includes namespaces, ownership, yanked/deprecated versions,
private registries, signed metadata, source and binary caches, resolver
backtracking, and reproducible package archives. Registry metadata changes
must be integrity-checked just like package contents.

### M13: developer tooling platform

Promote the existing LSP and editor contract into a versioned tooling surface:
completion, hover, diagnostics, semantic tokens, go-to-definition, references,
rename, inlay hints, code actions, formatter, linter, `rove fix`, `rove doc`,
`rove test` and `rove bench`. Diagnostics must preserve stable codes, spans,
notes, expected/found types and machine-readable fix-its.

### M14: debugger and profiler

Define DWARF and CodeView emission, source maps across HIR/MIR/legalization,
breakpoints, variable inspection, watch expressions, async frame display,
CPU sampling, allocation and memory profiling. Debug information must be
derived from retained provenance rather than emitter-specific guesses.

### M15: cross-language FFI generator

Generate checked bindings from C headers and explicit C++ wrapper contracts,
with Rust/Python adapters and Wasm WIT output as separate targets. Pointer
ownership, calling convention, layout, nullability, varargs and lifetime
contracts must be represented in the manifest and rejected before emission;
parsing a header is not proof that its ABI is safe.

### M16: concurrency memory model

Specify atomics, `Relaxed`, `Acquire`, `Release`, `AcqRel` and `SeqCst`
ordering, synchronization edges, happens-before, data-race definition and
visibility. Define the Rove equivalents of `Send`/`Sync` for tasks, channels and
shared values. The reference interpreter and MIR verifier must agree on the
observable subset before target adapters are admitted.

### M17: unsafe model

Make `unsafe` a typed contract, not a blanket escape hatch. Specify raw-pointer
provenance, alignment, initialization, dereference lifetime, aliasing,
MMIO/FFI boundaries and which operations require an unsafe block. Unsafe code
may opt out of selected guarantees, but it must not silently change safe-code
semantics.

### M18: compiler instrumentation

Add opt-in bounds, initialization, ownership, undefined-behavior and race
instrumentation with stable diagnostics and runtime policies. Instrumentation
must preserve source provenance, be removable for release builds, and have
positive and negative fixtures so a sanitizer result is not confused with a
proof of safety.

### M19: PGO and LTO

Define reproducible profile capture, profile validation, code-generation-unit
policy, thin/full LTO boundaries and cache invalidation. PGO/LTO may optimize
only after MIR verification and must retain enough provenance for debugging
and translation validation.

### M20: compatibility and editions

Introduce versioned language editions in the manifest, deprecation diagnostics,
edition-aware parsing and a `rove migrate --edition` tool. Old editions must
remain buildable under their documented rules while new editions can evolve
without silently changing existing source meaning.

### M21: plugin architecture

Version compiler plugins, lint plugins, backend interfaces and procedural
tools. Plugins receive explicit phase contracts and capabilities, cannot mutate
trusted identities or bypass verification, and must declare compatibility with
compiler, HIR, MIR and ABI schema versions.

### M22: supply-chain security

Unify package signatures, provenance attestations, SBOMs, reproducible builds,
dependency audits and trusted release metadata. Existing release checksums and
SBOM generation are foundations, not a complete package trust model. Verify
that attestations refer to the exact artifact bytes being published.

### M23: embedded and freestanding profile

Define allocator-free and `no_std` profiles, startup/linker contracts,
interrupts, timers, MMIO, memory maps, ARM/RISC-V layouts, HAL capabilities,
flashing and debug workflows. `#native` and C++ generation are insufficient
without a complete freestanding runtime and board-level acceptance fixture.

### M24: AI compiler protocol

Expose structured JSON diagnostics, fix-its, compiler state and proof/checker
results for human and machine clients. An AI may propose code, an optimization
or a proof, but the Rove parser, HIR verifier, MIR verifier and translation
validator remain authoritative:

```text
proposal -> parse/check -> HIR verify -> MIR verify -> validate -> accept/reject
```

AI output must never be treated as evidence merely because it is plausible or
because another model agrees with it.

Each M9-M24 track requires a design record, a canonical manifest entry, an
executable acceptance corpus, rejection tests, reproducibility evidence and a
documented exit gate before it can be promoted.

## 31. Delivery phases

### v5.1: compiler foundations

- Stable SourceId, ModuleId, DefId, TypeId, and InstanceId.
- Preserved module graph and public interface fingerprints.
- Exact type identity separated from assignment compatibility.
- MIR model, printer, serialization, and verifier.
- `rove emit mir` and `rove verify mir`.

### v5.2: control flow and cleanup

- CFG lowering.
- Short-circuit logic.
- Match, guard, destructuring, and Result propagation.
- Lexical defer and drop cleanup chains.
- Abstract exception and unwind edges.
- Internal effect metadata.

### v5.3: generics and dispatch

- Recursive type substitution engine (function boundary implemented).
- Monomorphization collector (reachable generic functions and concrete HIR
  function bodies plus struct and enum layouts implemented; method
  materialization remains open).
- Stable instance identity and target-independent instance symbols (implemented);
  target ABI/export mangling remains open.
- Generic constraints and diagnostics.
- Static trait dispatch (non-generic concrete impl selection implemented).
- Duplicate-instantiation cache.

### v5.4: ownership, layout, and ABI

- Explicit ownership operations.
- Drop elaboration.
- Target data layouts.
- Aggregate calling conventions.
- Bundle ABI v2 draft.
- Explicit C-compatible FFI representation.

### v5.5: async runtime

- Coroutine frame construction.
- Suspend, resume, completion, and destruction.
- Formal Task behavior.
- Channel and cancellation contracts.
- C++, Rust, JavaScript, and Wasm runtime adapters.

### v5.6: backend migration

- C++ consumes MIR.
- LLVM consumes legalized MIR.
- Wasm consumes legalized MIR.
- Rust consumes legalized MIR.
- JavaScript, Python, and C17 migrate after semantic parity.
- Repeated semantic lowering is removed from emitters.

### v6: semantic platform

- MIR becomes the default compiler route.
- Incremental query engine.
- Source-level debug metadata.
- WIT Component profile.
- Expanded portable and host standard libraries.
- Go source-backend pilot.
- C#/.NET and Java/JVM backend RFCs.
- Initial formal Rove Core and executable reference semantics.

## 32. Formalization maturity levels

Formal work should advance gradually:

```text
Level 0  precise English contracts
Level 1  executable reference interpreter
Level 2  property-based and differential testing
Level 3  MIR translation validator
Level 4  formal scalar and control-flow core
Level 5  mechanized type soundness
Level 6  verified critical lowering passes
Level 7  end-to-end semantic preservation
```

The project should not block practical compiler progress on complete formal
verification. Each level should produce usable tooling and stronger evidence.

## 33. Immediate starting sequence

The first implementation batch should remain narrow:

1. Publish a MIR design record defining stage boundaries and invariants.
2. Introduce stable compiler identities and stop relying on display names where
   MIR requires resolved identities.
3. Implement MIR model, canonical serialization, printer, and verifier.
4. Lower literals, locals, assignments, arithmetic, calls, branches, loops, and
   returns behind an experimental compiler path.
5. Implement the reference MIR interpreter for that scalar subset.
6. Differentially compare interpreter, C++, and LLVM results.
7. Add cleanup, Result propagation, match, aggregates, and ownership one
   vertical semantic slice at a time.

No new public keyword is required for this sequence.

## 34. Research references

- Rust MIR: <https://rustc-dev-guide.rust-lang.org/mir/index.html>
- Rust MIR passes: <https://rustc-dev-guide.rust-lang.org/mir/passes.html>
- Rust monomorphization: <https://rustc-dev-guide.rust-lang.org/backend/monomorph.html>
- Rust incremental compilation: <https://rustc-dev-guide.rust-lang.org/queries/incremental-compilation.html>
- Rust type layout: <https://doc.rust-lang.org/stable/reference/type-layout.html>
- Rust memory model: <https://doc.rust-lang.org/reference/memory-model.html>
- LLVM language reference: <https://llvm.org/docs/LangRef.html>
- LLVM undefined behavior: <https://llvm.org/docs/UndefinedBehavior.html>
- LLVM exception handling: <https://llvm.org/docs/ExceptionHandling.html>
- LLVM coroutines: <https://llvm.org/docs/Coroutines.html>
- LLVM source-level debugging: <https://llvm.org/docs/SourceLevelDebugging.html>
- MLIR dialect conversion: <https://mlir.llvm.org/docs/DialectConversion/>
- MLIR pass management: <https://mlir.llvm.org/docs/PassManagement/>
- WebAssembly specification: <https://webassembly.github.io/spec/>
- WebAssembly Component Model: <https://github.com/WebAssembly/component-model>
- WebAssembly Canonical ABI: <https://component-model.bytecodealliance.org/advanced/canonical-abi.html>
- Haxe standard library organization: <https://haxe.org/documentation/introduction/stdlib-introduction.html>
- CompCert semantic preservation: <https://compcert.org/man/manual001.html>
- Alive2 translation validation: <https://github.com/AliveToolkit/alive2>
- K Framework: <https://kframework.org/docs/user_manual/>
- Iris concurrent separation logic: <https://iris-project.org/>
- Rocq trusted kernel: <https://github.com/rocq-prover/rocq/blob/master/doc/sphinx/language/core/index.rst>
- Fully abstract compilation: <https://doi.org/10.1145/2951913.2951941>
- Go language specification: <https://go.dev/ref/spec>
- Go memory model: <https://go.dev/ref/mem>
- .NET asynchronous programming: <https://learn.microsoft.com/en-us/dotnet/csharp/asynchronous-programming/>
- JVM specification: <https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html>
- Lua 5.4 reference manual: <https://www.lua.org/manual/5.4/>
- Zig language reference and C interoperability: <https://ziglang.org/documentation/master/>
- Kotlin and Java interoperability: <https://kotlinlang.org/docs/java-interop.html>
- Kotlin coroutine semantics: <https://kotlinlang.org/spec/asynchronous-programming-with-coroutines.html>
- TypeScript runtime and type erasure: <https://www.typescriptlang.org/docs/handbook/typescript-from-scratch>
- Swift ABI stability: <https://www.swift.org/blog/abi-stability-and-more/>
- Ruby documentation and C extension guide: <https://www.ruby-lang.org/en/documentation/>
- Dart C interoperability: <https://dart.dev/interop/c-interop>
- Erlang process semantics: <https://www.erlang.org/doc/system/ref_man_processes.html>

## 35. Final principle

Rove should not measure language maturity by keyword count or backend count.
Maturity should mean:

```text
The source program has a target-independent meaning.
Every lowering stage has explicit invariants.
Every backend either preserves that meaning or rejects the program clearly.
No backend silently approximates unsupported semantics.
The evidence can progress from tests to executable validation and eventually
to machine-checked proofs.
```

The long-term differentiator is not merely that Rove can emit many languages.
It is that high-level, approachable syntax can lower into a small, precise,
observable, and increasingly verifiable semantic core across all targets.

Formal verification proves conformance to a specification; it does not prove
that humans chose the intended specification. Rove should therefore maintain
three mutually checked sources of truth:

```text
Human intent
  readable language contract

Formal model
  mathematical semantics

Executable evidence
  reference interpreter and conformance corpus
```

A material disagreement among these sources should block a stable release. The
ultimate evidence chain is:

```text
English specification
        <->
Formal semantics
        <->
Reference interpreter
        <->
Typed HIR and MIR
        <->
Generated target
        <->
Observed execution
```

The goal is for every edge in this chain to have an explicit validation method
rather than relying on one backend or one test suite as the definition of the
language.
