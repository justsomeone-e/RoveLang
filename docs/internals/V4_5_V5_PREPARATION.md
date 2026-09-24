# Rove v4.5.0 and v5.0.0 preparation log

Updated: September 6, 2026. Initial reviewed base commit: `a49e413`; the working
tree was dirty. `VERSION` and `rove.toml` were `4.0.0` when the preparation work
began and were later synchronized to `4.5.0`. This record is not evidence of a
release or a completed v5. Work is ordered
by dependencies and verifiable exit gates rather than dates.

The general release policy is in
[ROADMAP_AND_BACKEND_GATES.md](ROADMAP_AND_BACKEND_GATES.md), the change history
is in [CHANGELOG.md](../../CHANGELOG.md), and [TODO.md](../TODO.md) summarizes
tasks. This document records the detailed lowering and migration plan, research
decisions, implementation changes, and validation evidence for both releases.

## State verified in the source tree

| Component | Source | Actual state |
|---|---|---|
| Typed HIR | `src/ir/model.py`, `types.py`, `serialization.py` | Immutable tree-shaped HIR with schema v1, canonical JSON, and fingerprints; not SSA |
| Lowering | `src/ir/lowering.py`, `compiler/hir_lowering.rove` | Python and Rove frontend paths with a canonical byte-parity gate |
| Passes/verifier | `src/ir/passes.py`, `verifier.py` | Deterministic transformations and HIR validation |
| WASM | `src/codegen/wasm_ir.py` | HIR to a shared instruction graph to WAT and binary; not two independently handwritten codegen paths |
| Native self-host | `compiler/`, `tests/self_host_suite.py` | Native compiler emits C++; no C/LLVM self-host path yet |
| Backend registry | `src/core/backend_capabilities.py` | C++/JS/Python stable; Rust/WASM/React/ASM beta; `c` (C17 scalar) and `llvm` (LLVM IR scalar) registered as experimental |
| Benchmark | `src/toolchain/compiler_benchmark.py` | Measures Python stage 0; not evidence of native compiler acceleration |

WASM `int` arithmetic and `Array<int>` elements are currently i32. This is not
fully equivalent to the stable C++/JS/Python signed-i64 contract, and the
registry does not advertise `int64_wrap` for WASM. v4.5 documents this limit
instead of silently changing ABI v1 widths. An i64 internal representation and
ABI v2 remain separate v5 decisions.

## Implementation changelog

### Work already present when the session began

- Array/string `len`, `length`, and `size` return `int` in HIR; built-in
  `Result<T,E>` match payloads lower as `T`/`E`.
- Result-pattern binding type and scope were corrected in the Python type checker.
- LSP fixes existed for UTF-16 positions, diagnostic fields, closed documents,
  and unknown requests. References, rename, and semantic tokens were not yet
  complete at that point.
- The Metrics example, docs bundle generation, preview worker, and stage-0
  benchmark already existed. They were not created from scratch in this session.

### Corrections made after the initial investigation

1. **WASM numeric-array read lowering:** `IRIndexAccess` now compiles for borrowed
   `Array<int>` and `Array<float>` parameters. Previously, bundling stopped with
   `Unsupported expression 'IRIndexAccess'`.
2. **Single evaluation and bounds checks:** the index is evaluated once as a
   helper parameter. Negative indices, empty arrays, `index >= length`, and
   invalid descriptor ranges trap before loading. `ptr + length * stride` is
   calculated as i64 so wasm32 address overflow cannot bypass the check.
3. **Lazy Boolean lowering:** `and`/`or` and equivalent operators lower to
   `if (result i32)` branches. The incorrect eager evaluation through bitwise
   `i32.and/or` was removed.
4. **Regressions:** tests execute first/last elements, negative/empty/equal-to-length
   indices, i32/f64, nested access, side-effecting indices, short-circuiting,
   malformed raw ABI descriptors, and the last valid memory element. Unsupported
   string indexing and array-write paths reject compilation without leaving a
   failed bundle artifact.
5. **Generated examples:** Metrics/Pong bundles are regenerated with
   `python -m src.toolchain.docs_site` after lowering changes, and the hash
   manifest is kept aligned. Generated files are not edited manually.
6. **Stale release-test expectation:** commit `7a76cb3` intentionally removed the
   README footer while `tests/version_contract_suite.py` still required it. The
   obsolete footer assertion was removed; checks for the three active diagrams
   and all version mappings remain. The README design was not changed.

Code: `src/codegen/wasm_ir.py`. Tests: `tests/test_bundle.rove` and
`tests/bundle_suite.py`. The HIR schema, ABI version, and default target were
unchanged. Numeric-array reads do not imply owned arrays, array assignment,
string indexing, or full WASM runtime parity. Raw descriptor validation checks
the linear-memory range; it does not prove allocation ownership. A trap appears
in JavaScript as `WebAssembly.RuntimeError`, not as a catchable Rove exception.

## v4.5.0: ordered, compatible development

| ID | Priority / dependency | Deliverable | Exit criterion / state |
|---|---|---|---|
| 45-IR-1 | P0, first | Numeric-array reads and lazy Boolean WASM lowering | Implemented; bundle runtime regressions passed |
| 45-IR-2 | P0, after IR-1 | HIR node/type/span/capability inventory | Implemented; string/Iterator indexing type loss fixed, verifier generic/primitive rules tightened, Python/Rove canonical byte parity preserved |
| 45-LSP | P1, after symbol/span inventory | Source symbol index, references, prepareRename/rename, semantic tokens | Implemented; `LspSymbolIndex` covers shadowing, UTF-16, function/struct scopes, rename collision checks, and semanticTokens/full delta encoding; `lsp_suite` 7/7 passed |
| 45-PERF | P1, after correctness is green | Native frontend/codegen time and memory baseline | Implemented; `src/toolchain/compiler_benchmark.py` and `compiler_benchmark.json` record stage time/RSS/memory on a fixed four-source corpus in `build/compiler-benchmark.json` |
| 45-LIB | P1 | Stdlib string/path/process API inventory and real consumer examples | Distinguish errors from empty values for every added API; require Result and exact C++/JS/Python output; open |
| 45-WASM | P1, after IR-1 | Separate capability tasks: assignment/ownership, string indexing, and WASI args/env/files | ABI decision and positive/negative runtime tests for each task; unfinished capabilities remain disabled; open |
| 45-RUST | P1 | Defer/Result/value-copy coverage, payload enums, and async/runtime gaps | rustc runtime parity for every enabled capability; beta maturity does not change without evidence; open |
| 45-PKG | P1 | SemVer/registry/offline RFC and deterministic resolver | Keep local locks distinct from remote resolution; range/cycle/checksum/offline negative corpus; open |
| 45-V5 | P1 | Turn the C17/LLVM and migration design below into prototypes | C17 scalar pilot completed (`src/codegen/c17_scalar.py`, `tests/c17_scalar_suite.py`, backend `c`); LLVM IR and migration tools are next |
| 45-REL | Last, after all frozen-scope work | Release candidate and platform evidence | Full tests, self-hosting, four OS/architecture jobs, extension tests, checksums/SBOM, and packaging from the same revision; open |

Priority audits during 45-IR-2 included avoiding unnecessary `any` for
string/member/index results, preserving lexical symbol identity in emitters,
single evaluation for destructuring/default arguments, defer order on early
exit, behavior before/after passes, and rejecting unsupported HIR before output
is emitted. These must not be marked as fixed without implementation evidence.

For 45-PERF, `tests/bootstrap_typechecker_test.py` recompiles the native test
program for each semantic case. Its total duration is not direct Rove frontend
latency. Any harness optimization must first separate compilation from case
execution, then measure single-harness reuse/cache against the same
acceptance/rejection corpus.

At entry to a v4.5 release candidate, the selected P1 scope must be frozen.
Unfinished features move explicitly to a later release and are not presented as
stable. P0 correctness and release gates cannot be deferred.

## v5.0.0 Daydream: lowering and backend design record

Status: **design / implementation pending**. No C17 or LLVM emitter has been
added. Rewriting the entire v4 HIR is not a prerequisite.

Recommended order:

```text
v4.5 canonical HIR and semantic fixtures
    -> C17 scalar pilot
    -> LLVM scalar pilot and explicit control flow
    -> measure shared-lowering needs; add a narrow internal LIR only if justified
    -> runtime, ownership, Result/defer, ABI, and platform conformance
    -> migration tools and native bootstrap evidence
    -> v5 release candidate and release gate
```

### 50-C: experimental C17 pilot

Status: **the C17 scalar pilot is implemented** in
`src/codegen/c17_scalar.py`, tested by `tests/c17_scalar_suite.py`, and registered
as backend `c`. It was checked with `clang -std=c17 -Wall -Wextra -Werror`
against the C++ oracle.

- Input is verified HIR only. Initial coverage is `int`, `float`, `bool`, locals,
  arithmetic/comparison, direct calls, if/while, and return. String/Array/Struct,
  exceptions/Task, and foreign bindings are rejected until implemented.
- Do not rely on C signed overflow for Rove signed-i64 wrapping. Use unsigned
  arithmetic and defined signed-conversion helpers; branch explicitly for zero
  division/remainder and minimum-i64 divided by -1.
- Compile generated C17 with a real C toolchain and compare the same fixture
  against C++/JS/Python oracles. O0 and O2 results must agree, and reports must
  record platform/toolchain versions. C17 source generation alone is not native
  self-hosting.
- Do not consider beta before gates 1–7 pass or stable before all eight pass.

### 50-LLVM: experimental direct LLVM IR pilot

The first v5 development slice extends the direct emitter with scalar-field
structs represented as named LLVM aggregate types. Constructors, field reads,
direct local field writes, value copies, parameters, and returns are validated
against the C++ oracle by `tests/llvm_scalar_suite.py`. Aggregate fields,
generic structs, optional/safe access, and Arrays remain gated until their
layout, ownership, and cleanup contracts are implemented.

The second slice adds stack-owned `Array<int>`, `Array<float>`, and `Array<bool>`
locals using typed `{ length, data }` LLVM descriptors. Literal initialization,
bounds-checked reads and writes, and independent local copies are tested against
the C++ oracle. Scalar Arrays cross function-input boundaries by value: the
callee dynamically allocates stack storage and copies bytes with LLVM's memcpy
intrinsic, so mutations do not alias caller storage. `for value in array` lowers
to explicit condition/body/step/exit blocks with correct `break` and `continue`
targets. Array returns, rebinding, nested Arrays, and non-scalar elements remain
rejected until the ownership and cleanup ABI is defined.

The public CLI now exposes the same path: `rove build program.rove --target llvm`
writes `build/llvm/program.ll` and compiles that exact LLVM IR artifact to a
native executable with the host Clang toolchain. `rove run ... --target llvm`
uses the same direct path. No generated C++ source participates in either command.

- Initial HIR coverage matches 50-C and emits `.ll` without a C++ source hop.
  Validation requires real LLVM parsing/compilation. The supported LLVM major
  version must be pinned; the locally installed Clang version is not a product
  compatibility promise.
- Locals initially use entry-block alloca/load/store. A custom early SSA system
  is unnecessary. LLVM verification checks branches, terminators, types, and
  returns; SSA conversion is evaluated through measured official passes.
- Rove wrapping arithmetic does not use unproven `nsw`/`nuw`. Division/remainder,
  shift-count bounds, and lazy Boolean expressions require explicit lowering.
- Fast-math is off by default. Preserve NaN, signed zero, and binary64 fixtures.
  Obtain target triples/data layouts from the target toolchain rather than
  copying pointer/alignment values from another platform.
- Preserve source spans and symbol identity in HIR. Debug metadata is a separate
  deliverable; producing `.ll` alone is not debugger support.

### 50-LIR / 50-RUNTIME: sharing boundary

If a second emitter starts repeating the same semantic transformations, add an
internal LIR only after evidence demonstrates the need. There is no requirement
to migrate every hosted emitter initially. Public HIR JSON and internal LIR are
separate formats.

LIR acceptance criteria are typed values, unique symbol/block identities, one
terminator per block, valid branch targets, single evaluation, and source spans.
Fixtures separately verify lexical defer cleanup paths for Result
`?`/return/break/continue and Array/Struct copy/borrow rules. Exceptions,
Task/channel, and closure capture are not considered implemented without a
runtime design.

### 50-REF / 50-BOOT: independent validation and native distribution

- The OCaml reference frontend is only a frozen grammar to canonical
  HIR/diagnostics validator, not a mandatory replacement production compiler.
  It reuses the existing Python/Rove parity corpus for independent parse and
  diagnostic comparisons.
- Exposing a new backend through native `rovec` is separate work. A Python-based
  pilot emitter does not mean the native compiler supports C/LLVM.
- Preserve Stage1 -> Stage2 -> Stage3 evidence, clean installation, and packaging
  tests. Changing the default backend requires a separate release decision.

## Migration gate: which change requires which release?

| Surface | v4.5 rule | Migration required for v5 |
|---|---|---|
| Rove source semantics | Preserve the meaning of valid v4 code | For breaking proposals, provide before/after examples, diagnostics, and a conversion guide; never silently reinterpret source |
| HIR JSON / plugin API | Preserve schema v1 and canonical parity | Removing fields or changing meaning requires HIR v2, reader-side version checks, and v1 migration fixtures |
| Internal LIR | Does not yet exist and cannot replace public HIR | If needed, give it a separate internal version/fingerprint; it does not automatically enter the plugin contract |
| WASM Bundle ABI | Preserve v1 i32/UTF-8 ptr-len/borrow rules | i64 widths and owned Array/Struct returns require ABI v2 plus loader/type migration |
| Host imports | Preserve `nyx_host_v1` | Signature/lifetime changes require a new namespace and rejection of incompatible host versions |
| Package lock | Preserve current local-lock behavior | Registry identity, range resolution, and new required fields require a format decision, deterministic migration, and rejection of unknown formats |

Every breaking v5 change requires example source, old/new artifacts, user
impact, a conversion path, and a negative regression test. Changing a version
number is not migration. v5 release readiness requires the selected scope to
pass all eight backend gates; both C and LLVM do not have to become stable.
Go/JVM/.NET/Lua are outside this preparation effort.

## Research sources and their effect on Rove

Checked against official sources on September 6, 2026. The implementation
decisions below are Rove design choices, not rules automatically imposed on Rove
by the referenced standards.

- [WebAssembly instruction semantics](https://webassembly.github.io/spec/core/exec/instructions.html):
  `unreachable` traps and `if` executes only the selected branch. A load's
  linear-memory bound does not know the Rove logical array length, so logical
  bounds and widened descriptor checks occur before loading. No new WASM 3.0
  feature dependency was introduced.
- [LLVM add semantics](https://llvm.org/docs/LangRef.html#add-instruction) and
  [sdiv semantics](https://llvm.org/docs/LangRef.html#sdiv-instruction): wrapping
  differs from `nsw`/`nuw` poison; zero and overflow division need guards. Shift
  and target-layout rules come from the same Language Reference.
- [LLVM UB manual](https://llvm.org/docs/UndefinedBehavior.html): poison/UB can
  change behavior under optimization; successful parsing is insufficient.
- [WG14 N1570](https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf),
  sections 6.2.5, 6.5, and 6.5.7, is the openly available C11 wording for
  unsigned modulo, signed overflow, and shifts. It is not presented as the C17
  final standard; the [WG14 project list](https://open-std.org/jtc1/sc22/wg14/www/projects.html)
  identifies C17 as ISO/IEC 9899:2018. The pilot is validated in real C17 mode.

## Validation record for this revision

- TESTED: `python tests/c17_scalar_suite.py`; the experimental C17 scalar pilot
  compiled and ran under `clang -std=c17 -Wall -Wextra -Werror` without warnings
  or errors. Signed-i64 wrapping, safe zero division and `INT64_MIN / -1`
  abort/wrap behavior, scalar control flow, recursion (`fib`), and strict
  compile-time rejection of non-scalar data (`Array`, `Struct`) matched the C++
  oracle exactly.
- TESTED: `python tests/ir_suite.py`; 162 programs, 18 stdlib modules, 196-case
  Rove/Python canonical HIR byte parity, string indexing, and negative
  `IRVerifier` tests passed, including primitive member access (`HIR0006`) and
  struct generic/optional field validation.
- TESTED: `python tests/bundle_suite.py`; the new fixture reproduced the old
  `IRIndexAccess` failure and passed after the fix, including 100,000-allocation
  stress, bounds/short-circuit regressions, and negative compilation scenarios.
- TESTED: `python -m src.toolchain.docs_site`; Metrics/Pong outputs were regenerated.
- The first full-battery run caught a byte mismatch between the new lowering and
  the stale `docs/generated/metrics/metrics.wasm`. The artifacts were regenerated
  through the source command and the next docs-site validation passed.
- TESTED: the combined battery passed self-host reproducibility, 197-case
  Python/Rove canonical HIR parity, the 162-program corpus, C++/JS/Python runtime
  and Rust metadata/runtime gates, language/numeric/Maya surfaces, and
  deterministic ZIP/TAR packaging.
- The second combined run stopped at the pre-existing README footer assertion.
  Commit history confirmed that the footer had been removed intentionally, and
  the test was corrected. `run_version_contract_suite` passed; the 23 suites
  after that point were then executed through the same runner functions and
  returned 23/23 `True` with process exit 0. This verifies every runner component
  in two sections, not as one uninterrupted full-suite pass. The newly added
  bundle negative tests also passed separately through
  `python tests/bundle_suite.py`.
- TESTED: the remaining group passed installer, module/LSP/smoke, 530 fuzz cases
  with zero unhandled crashes, differential and JS/Rust/C++ end-to-end, FFI,
  library, manifest, link, platform, SDK, interop, bootstrap lexer/parser/type
  checker, and the 138/138 regression battery.
- TESTED: `npm --prefix vscode-extension test` passed.
- VALIDATED: `git diff --check` and local Markdown links across six
  planning/changelog documents passed.
- Environment: Windows, Python 3.12.10, Node.js 24.19.0, Clang 22.1.8.
- NOT TESTED: Linux/macOS CI, independent WAT assembly, clean-machine validation
  of platform-native release packages, and the v5 C17/LLVM runtime. The pilots
  had not yet been implemented at the time of this record. This work did not
  commit, tag, push, or publish a release.

Rerun everything on the next revision with
`python -u tests/run_all_tests.py`.

If WASM code generation changes, first regenerate site artifacts with
`python -m src.toolchain.docs_site`, then run bundle/docs-site tests and the full
battery.

## Starting point for the next session

1. Run `git status --short` and inspect changes made after this record.
2. Continue from this validation record and the 45-IR-2 inventory; do not redesign
   completed array-read or lazy-Boolean work.
3. If new lowering changes type information, update the Python and Rove lowerers
   together and run HIR byte parity plus self-host validation.
4. Record each new task ID in this file and in the `CHANGELOG.md` Unreleased
   section. Preserve exact commands, TESTED/REVIEWED/NOT TESTED distinctions,
   and any open defects.
