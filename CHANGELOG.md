# Rove Changelog

All notable changes to the Rove compiler, toolchain, and standard library are documented in this file.

---

## [5.0.3] - 2026-09-16 (Daydream)

### Fixed

* Prevent the browser preview from executing `main()` twice when the source
  already contains an explicit `main()` call.
* Bust evaluator and Worker caches so published Studio pages receive the fix.
* Keep Studio examples separate from Tour exercise edits and local progress.
* Remove decorative emoji from the documentation and public site surfaces.

### Site

* Refine the landing page hierarchy with a compact release snapshot.
* Replace the overloaded Studio layout with clearer target, example, inspect,
  output, and local-build controls.

### Verification

* Browser preview and Node evaluator smoke checks confirm one output for one
  explicit `main()` call.
* HTML/JavaScript syntax, emoji scan, and diff checks pass.

## [5.0.2] - 2026-09-16 (Daydream)

### Fixed

* Make Windows architecture detection and npm executable discovery null-safe
  for Windows PowerShell environments where command/runtime metadata is absent.
* Register the experimental native `std/http` module for the C++ target and
  replace shell-interpolated curl commands with bounded, direct process
  execution on Windows and POSIX hosts.
* Install Rove editor support from the Unix installer for VS Code, VS Code
  Insiders, and VSCodium; syntax highlighting remains available even when npm
  is absent, while the installer reports that LSP dependencies are unavailable.
* Emit extensionless native executables on Linux and macOS instead of applying
  the Windows-only `.exe` suffix.
* Embed C++, JavaScript, and Rust grammar scopes inside matching `#native`
  blocks in the VS Code syntax grammar.

### Compiler

* Extend the experimental Rust MIR pilot with native payload enums,
  discriminant checks, typed payload extraction, and executable parity tests.
* Add checked compiler identity, generic-instance, static-dispatch, coroutine,
  effect, and per-module graph foundations with focused verification suites.
* Expand MIR lowering, verification, legalization, and backend pilot coverage
  while preserving explicit capability rejection for unsupported targets.

### Tour and documentation

* Add the project-driven Core Path and exercise metadata to the Tour of Rove.
* Document the Deep Compiler M9-M24 roadmap, capability-resolution design, and
  the boundary between implemented evidence and future work.

### Verification

* The final source revision passed the full local regression harness: 138/138
  suites passed with exit code 0. Hosted CI, release packaging, and native
  multi-platform artifacts remain workflow evidence rather than local claims.

## [5.0.1] - 2026-09-08 (Daydream)

### Fixed

* Register foreign-import aliases in the Rove-authored type checker before
  checking function bodies, so native `rovec` accepts C++ namespace imports.
* Emit `std::nullopt` when a Rove `null` initializes, assigns, or returns an
  optional value in the self-hosted C++ backend.
* Suppress MSVC's legacy `getenv` deprecation diagnostics in generated C++ and
  prefer `npm.cmd`/`npm.exe` when PowerShell execution policy blocks `npm.ps1`.
* Correct the intentionally failing string assertion in the in-file test
  example and document the distinction between release `rovec.exe` and the
  installer-created `rove.cmd` wrapper.

## [5.0.0] - 2026-09-07 (Daydream)

Rove v5.0.0 promotes the Daydream language and toolchain line to stable while
preserving the established C++20, JavaScript, Python, Typed HIR v1, and Bundle
ABI v1 contracts. The direct LLVM IR and C17 paths ship as experimental
backends with strict capability rejection; their presence does not imply full
language or standard-library parity.

### Release status

* Promote the compiler, native self-host banner, package manifests, VS Code
  extension, documentation site, and release metadata to `5.0.0`.
* Keep C++20 as the default native backend and retain JavaScript and Python as
  stable parity targets.
* Ship the direct LLVM IR pipeline and C17 emitter under their existing
  experimental maturity contracts.
* Preserve Stage1 → Stage2 → Stage3 reproducibility and Python/Rove canonical
  Typed HIR parity as release gates.
* Publish platform-native compiler binaries, deterministic source archives,
  VSIX, SHA-256 manifests, SBOM, and provenance only after the tagged workflow
  passes.

## [5.0.0-rc.1] - 2026-09-06 (Daydream)

### Experimental LLVM backend

* Add scalar-field Rove structs to the direct LLVM IR backend as named LLVM
  aggregate types.
* Pass and return supported structs by value, lower constructors with
  `insertvalue`, lower field reads with `extractvalue`, and lower direct local
  field writes with typed `getelementptr` operations.
* Verify independent struct-copy behavior and function-boundary parity against
  the C++ backend with a real Clang execution test. Arrays, strings in structs,
  nested aggregate fields, generic structs, and safe member access remain
  explicitly unsupported.
* Add stack-owned `Array<int>`, `Array<float>`, and `Array<bool>` locals to the
  direct LLVM backend. Array literals use typed descriptors, reads and writes
  perform signed logical bounds checks, and local copies duplicate every element
  instead of aliasing storage. `len()`, `length()`, and `size()` read the shared
  descriptor length as i64.
* Pass scalar Arrays to functions by value. Function entry uses a dynamic stack
  allocation and `llvm.memcpy` so mutations cannot alias caller storage.
* Lower `for value in array` to explicit condition/body/step/exit blocks. Array
  iteration supports `break` and routes `continue` through the increment block.
* Keep Array returns, rebinding, nested arrays, and non-scalar elements
  explicitly gated until the v5 ownership and cleanup ABI is defined.
* Wire the experimental C17 and LLVM targets into `rove build` and `rove run`.
  LLVM builds now preserve the generated `.ll`, compile that exact IR with the
  host Clang toolchain, and produce a native executable without a C++ source hop.

## [4.5.0] - 2026-09-06 (Ivory)

Rove v4.5.0 establishes the stable bridge release toward v5, providing standard library
parity, deterministic package management, import invalidation benchmarking, and experimental
C17 and LLVM IR direct emitters while preserving full v4 backward compatibility.
Verification evidence and test battery metrics are recorded in
[v4.5 implementation audit](docs/internals/V4_5_IMPLEMENTATION_AUDIT.md).

### Compiler and lowering

* Preserve `int` HIR types for Array/string length methods and specialize
  built-in Result match payloads in the Python and Rove HIR lowerers.
* Lower string indexing (`string[i]`) and `Iterator<T>` indexing with concrete
  element types in both Python (`src/ir/lowering.py`) and self-hosted Rove
  (`compiler/hir_lowering.rove`) lowerers, eliminating `any` type loss while
  preserving 100% canonical byte parity.
* Strengthen `IRVerifier` type contracts: reject member access on primitive
  types (`int`, `float`, `bool`, `void`, `null`) with structured diagnostic
  `HIR0006`, validate struct field existence and optionality, perform generic
  type parameter substitution on struct member lookups, and verify string
  and collection element indexing result types.
* Add experimental C17 scalar emitter (`src/codegen/c17_scalar.py`) consuming
  verified `IRModule`. Implements 64-bit wrapping integer arithmetic (`rove_i64_add`,
  `rove_i64_sub`, etc.), safe division and modulus (aborting with exit code 1 on zero
  divisor and wrapping `INT64_MIN / -1`), scalar control flow (`if`/`else`, `while`,
  `break`, `continue`), float and boolean logic, and strict rejection of non-scalar
  types with `C17EmissionError`.
* Register experimental `"c"` target capability in `src/core/backend_capabilities.py`
  and integrate compilation routing in `src/api.py`.
* Lower numeric-array parameter reads (`values[index]`) to checked WASM loads.
  Evaluate the index once, reject negative/out-of-range indices, and validate
  descriptor byte ranges with widened arithmetic before loading memory.
* Preserve short-circuit evaluation of WASM Boolean `and`/`or` expressions,
  including bounds guards whose right-hand side must not execute.
* Extend bundle runtime regressions for i32/f64 reads, nested/side-effecting
  indices, invalid host descriptors, memory boundaries, and unsupported writes
  and string indexing. WASM remains beta with the existing ABI-v1 i32 contract.
* Implement 45-WASM capabilities: in-place numeric array mutations (`copyBackNumericArray`),
  checked string character element reads, and WASI args/env/file capabilities.
* Implement 45-RUST backend parity: array and struct value copying semantics, lexical
  defer scope unwinding, payload enum variant extraction, Option/match expression arms,
  Task/channel concurrency primitives, and crate import resolution.
* Add experimental direct LLVM IR scalar emitter (`src/codegen/llvm_scalar.py`) targeting
  `x86_64-w64-windows-gnu` (Clang 22). Implements direct `.ll` text emission, 64-bit wrapping
  integer arithmetic, IEEE 754 float math, boolean logic, entry-block `alloca` memory
  architecture, mem2reg-friendly phi-free branch merges, short-circuit `and`/`or` flow,
  safe zero-division abort guard, and strict compile-time rejection of non-scalar constructs.
* Register experimental `"llvm"` target capability in `src/core/backend_capabilities.py`
  and integrate compilation routing in `src/api.py`.
* Standard library parity (45-LIB): completed `std/str`, `std/path`, and `std/process`
  modules with Result-wrapped fallible operations and cross-backend exact output parity
  across C++20, JavaScript (Node.js), and Python 3.

### Tooling and examples

* Implement 45-LSP Language Server Protocol features (`src/toolchain/lsp_server.py`):
  symbol index (`LspSymbolIndex`) with function scope, local variables, parameters,
  and struct fields; `textDocument/references` respecting local function scopes and
  lexical shadowing; `textDocument/prepareRename` returning exact token range and
  placeholder; `textDocument/rename` generating workspace edits, rejecting reserved
  keywords and builtins, and detecting scope collisions; and `textDocument/semanticTokens/full`
  delta encoding across keywords, types, functions, variables, parameters, properties,
  strings, numbers, and operators.
* Preserve diagnostic help/expected/found/notes in LSP messages; correct UTF-16
  positions, document-close cleanup, and unsupported-request responses.
* Add a fixed-corpus Python stage-0 compiler timing/memory benchmark.
* Performance baseline and import invalidation corpus (45-PERF): added multi-module
  invalidation test corpus (`tests/fixtures/import_invalidation/`) and recorded
  cold, warm, and invalidated timing/memory baselines without premature caching.
* Package Manager (45-PKG): implemented Semantic Versioning range evaluator (`SemVerRange`)
  supporting caret (`^`), tilde (`~`), wildcards, and compound ranges; mock registry protocol;
  offline cache miss and hit handling; SHA-256 package checksum verification; and
  deterministic lockfile generation and verification (`RoveLock`).
* Add the Metrics CLI/JS/Python/WASM example, generated documentation-site
  bundles and checksums, and isolated worker-based learning previews.
* Rebuild Metrics/Pong artifacts after the WASM lowering correction.
* Added four consumer applications:
  - `examples/file_inspector/`: Native CLI tool consuming `std/path`, `std/process`, and `std/str`.
  - `examples/host_embedding/`: Polyglot data transformer module embedded in both Node.js (WASM ABI v1 package) and Python 3 hosts.
  - `examples/wasm_interactive/`: Interactive WebAssembly arithmetic and combinatorics engine with browser UI.
  - `examples/package_consumer/`: Real package consumer demonstrating `rove.toml` local dependencies, deterministic `rove.lock` verification, and native C++ filesystem foreign bindings.
* VS Code Language Toolchain extension: synchronized canonical language surface metadata
  (`vscode-extension/language-surface.json`) including the experimental `"llvm"` target,
  verified with test contract suite.

### Release validation

* Remove the obsolete version-test requirement for the README footer that was
  intentionally removed in `7a76cb3`; preserve active diagram and version checks.
* Add C17 scalar regression suite (`tests/c17_scalar_suite.py`) validating strict
  compilation under `clang -std=c17 -Wall -Wextra -Werror` with C++ oracle parity across
  recursion (`fib`), loops, arithmetic wrapping, safe division, and non-scalar rejection.
* Expand `tests/lsp_suite.py` to 7/7 conformance tests verifying references,
  prepareRename, rename, semantic tokens, and live CLI wire JSON-RPC communication.

### Planning

* Define v4.5 compatibility gates and v5 C17/LLVM lowering, runtime, independent
  frontend, and migration milestones. Planned backends and ABI v2 are not
  implemented or promoted by this preparation work.

## [4.0.0] - Nirvana (release preparation)

### Nirvana stable v4 contract

* Consolidated the unpublished RC3 work into the v4.0.0 stable release scope.
  C++, JavaScript, and Python retain the stable semantic contract; Rust,
  WebAssembly, React, and assembly retain their existing beta status.
* Removed quadratic full-source UTF-8 rescanning from the self-host lexer and
  preserved complete UTF-8 byte lengths in generated C++ string literals.
* Aligned string index boundaries and collection length methods across the
  stable backends, with Unicode, combining-mark, and embedded-NUL regressions.
* Required release conformance on Windows, Linux, Intel macOS, and ARM macOS.

* Added typed-HIR postfix `?` lowering to the Rust backend with LIFO `defer`
  execution before propagated error returns.
* Added import-safe JavaScript ESM builds with explicit exports and preserved
  signed 64-bit integer behavior.
* Added WASI preview1 executable output and borrowed scalar-struct WebAssembly
  ABI marshalling with generated TypeScript interfaces.
* Tightened capability-derived diagnostics for backend features that remain
  unsupported.
* Expanded Tour of Rove to 81 verified exercises across 21 modules and removed
  retired duplicate lesson files.
* Closed hosted-backend semantic gaps for Array/Struct value copies and Unicode
  code-point length, indexing, and iteration.
* Expanded typed browser/Canvas examples without introducing handwritten
  application logic into the generated host bridge.

### Validation

* The unified test framework, native self-host chain, backend conformance,
  release packaging, extension tests, and 81/81 Tour verification remain
  release gates.

## [4.0.0-rc.2] - 2026-09-04

### Bodhi release candidate

* Added complete `.wat`/`.wasm`/`.mjs`/`.d.ts` output to ordinary WASM builds.
* Added versioned `rove_host_v1` imports and the typed `std/web` DOM, event,
  lifecycle, and Canvas API.
* Added npm-ready bundle manifests and React 19, Vue 3, and Svelte 5 adapters.
* Added pure-Rove browser Pong and host-simulated runtime conformance tests.
* Expanded WASM lowering for host/internal calls, booleans, mutable globals,
  numeric arrays, collection loops, built-in `len()` methods, and conditional
  UTF-8 string results.
* Added recursive deterministic local path dependencies with slash-normalized
  manifests, source checksums, and cycle diagnostics.
* Made aliases transparently compatible in both the Python and Rove-authored
  type checkers.

### Validation

* Bundle ABI v1, host ABI v1, framework artifact syntax, local package locks,
  canonical language surface, HIR parity, and native bootstrap remain direct
  release gates.

## [4.0.0-rc.1] - 2026-09-02

### Release candidate

* Promoted the compiler-focused v4 line to its first public release candidate,
  **Samsara**. This is an evaluation and soak release; `v4.0.0 Nirvana` remains
  the future stable milestone.
* Completed default-argument lowering in both frontends and the Rove-authored
  HIR path, including omitted trailing arguments and required-argument
  diagnostics.
* Added flat array and struct destructuring declarations with single RHS
  evaluation, checked cardinality diagnostics, const preservation, and exact
  Python/Rove HIR parity.
* Hardened destructuring lowering against user-identifier collisions and made
  top-level bounds failures deterministic across C++, JavaScript, and Python.
* Expanded typed standard-library, collection, fallible-result, and foreign
  binding test coverage; unsupported target behavior remains behind explicit
  capability gates rather than silently approximated.
* Updated the native compiler banner, VS Code package, documentation, and
  pinned installer instructions to one version source: `4.0.0-rc.1`.

### Validation

* The unified local test framework passed: self-host, 194-case HIR
  parity, backend runtime/compile gates, installer/LSP/fuzz checks, and the
  138-point regression battery.
* The tagged GitHub workflow is the source of release-asset checksums, SBOM,
  provenance, platform-native binaries, and the packaged VS Code extension.

## [4.0.0-dev.2] - 2026-08-31

### Scope reset: microcontroller support removed

* Removed STM32F1/F4, Nucleo, RP2040, AVR, generic embedded, and freestanding
  firmware targets from the backend registry and CLI.
* Removed board profiles, custom board manifests, STM32Cube/CMSIS resolution,
  linker/startup/runtime assets, firmware flashing, and ELF/HEX/BIN build paths.
* Removed the physical hardware standard-library surface: `std/board`,
  `std/gpio`, `std/adc`, `std/pwm`, `std/spi`, `std/i2c`, `std/serial`,
  `std/timer`, `std/interrupt`, and `std/mmio`.
* Removed embedded-only language residue from both Python and Rove-authored
  frontends: `volatile`, `interrupt`, `critical`, `Buffer<T, N>`, and
  `buffer_ptr`. The canonical surface is now 43 keywords.
* Removed obsolete hardware fixtures, editor snippets/completions, documentation,
  and regression suites. Historical releases and Git history retain the deleted
  implementation.

### Why

Rove was trying to maintain a language, seven application backends, self-hosting,
IDE tooling, and a broad physical-board platform simultaneously. The firmware
layer was larger than the project could support without weakening compiler
correctness. Dev.2 deliberately narrows v4 toward the compiler itself: typed HIR,
native/WASM output, self-hosting, readable Nim/Haxe-inspired syntax, diagnostics,
and deterministic tooling. Fixed-size collections may return later only through
a target-neutral language RFC.

### Validation

* Python/Rove frontend and 184-case canonical HIR byte parity passed.
* 530 fuzz cases completed with zero unhandled compiler crashes.
* Python, JavaScript, C++20, and Rust backend conformance passed.
* VS Code/LSP, installer, FFI, SDK, interop, and clean-environment smoke suites passed.
* The 138-point exhaustive regression battery passed 138/138.

## [4.0.0-dev.1] - 2026-08-29

### Compiler architecture

* Rove-authored lexer, parser, type checker, typed-HIR lowerer, and HIR C++
  emitter now form a reproducible native stage1 -> stage2 bootstrap.
* `cpp`, `js`, `python`, `rust`, and `wasm` consume canonical verified HIR;
  non-HIR targets retain beta or experimental status.
* The Rust 2021 emitter now preserves Rove value semantics, strict Boolean
  boundaries, Option/Result lowering, lexical `defer`, and wrapping i64 code
  directly from HIR. Unsupported Task, exception, spawn, and channel semantics
  fail with `E3001`; beta status remains until runtime and Gate 8 evidence.
* Native-first installers provide `rovec check`, `emit-cpp`, and `compile`
  without a Python runtime.

### Frozen v4 semantics

* 46 canonical keywords with `fn` as the sole function declaration spelling;
  embedded targets add `volatile`, `interrupt`, and `critical`.
* Signed i64 wrapping arithmetic, IEEE binary64, canonical scalar text, and
  optimizer/backend parity.
* Strict Boolean conditions, including runtime type checks at dynamic `any`
  boundaries.
* Verified trait contracts, shallow immutable bindings, reusable `Task<T>`,
  and exception propagation across awaits.
* Fixed-width scalar spellings and a first-class embedded control surface
  replace routine `#native raw` use for shared state and interrupt handlers.
* Embedded-only `Buffer<T, N>` adds allocation-free fixed storage, checked
  capacities/indexes, and pointer-length bulk-I/O interop without native code.
* Maya adds expression-bodied functions plus value-producing `if` and
  exhaustive literal `match` expressions. The Python and Rove-authored
  frontends produce byte-identical HIR, and declared backends share the same
  branch typing and lazy evaluation rules.

### Embedded systems

* Data-driven Nucleo profiles, custom `board.toml`, STM32CubeProgrammer/OpenOCD
  command generation, and board connector aliases.
* Register-level STM32F4 GPIO, UART, SPI, I2C, ADC, PWM, timers, NVIC, and
  volatile MMIO APIs with bounded error paths and buffer-based bulk transfers.
* F410 now uses its real TIM5/TIM6 and IRQ map and rejects unavailable
  TIM2-backed PWM; F401/F411/F446 retain their board-specific timer maps.
* Standalone ELF/HEX/BIN builds for NUCLEO-F401RE, F410RB, F411RE, and F446RE.
* Official STM32Cube sparse installer/provider resolves CMSIS device selectors,
  startup assembly, system C, IRQ maps, and Nucleo linker scripts for 21 more
  profiles. Mixed C/C++/ASM compilation and GNU-ld/LLD normalization are covered
  by a 25-board ARM ELF/HEX/BIN integration matrix.
* A minimal weak CMSIS freestanding CRT supplies constructor arrays and memory
  primitives without overriding a user-configured libc/compiler runtime.
* Removed desktop HAL simulations that previously printed success without
  touching hardware.

### Release engineering

* Deterministic ZIP/TAR source archives from canonical Git blobs.
* Four native platform artifacts, SHA-256 manifests, SPDX 2.3 SBOM output,
  and signed GitHub provenance/SBOM attestations.

### CLI toolchain integrity

* `fmt`, `lint`, `debug`, `profile`, `doc`, `add`, `remove`, `install`, and
  `pkg` now propagate failure exit codes and are covered by real filesystem and
  process-effect tests.
* Formatting is string/comment-safe and idempotent; profiling measures an
  actual compile+run instead of printing synthetic routines; the source
  inspector no longer invents runtime variables or memory.
* Package commands mutate and verify `rove.toml`/`rove.lock` with explicit
  versions. RC1 intentionally exposes no remote registry fetch and says so.

## [2.0.0-beta.1] - 2026-08-28 (Beta 1 Public Release)

### Major Additions
* **Multi-Backend Architecture**:
  * `cpp`: ISO C++20 backend frozen at Gate 8 (Production Native `.exe` via LLVM Clang / MinGW-w64).
  * `python`: Canonical reference evaluation engine.
  * `js`: Node.js ES2022 backend frozen at Gate 8.
  * `rust`: Rust 2021 active conformance backend (Gate 6).
* **Module & Import Altyapısı (`src/core/module_loader.py`)**:
  * Local relative imports (`import "./utils"`).
  * Standard library module imports (`import "std/math"`).
  * Selective symbol imports (`import { abs_val, power } from "std/math"`).
  * Diamond dependency deduplication ($A \to B, A \to C, B \to D, C \to D$).
  * Ambiguous symbol collision detection (`error[E1302]`).
* **Diagnostics v2 Standard**:
  * Rustc-style visual errors with dynamic span carets (`^^^^`), error catalog codes (`E1000` to `E2006`), `searched paths:`, `note:`, and actionable `help:`.
* **Standard Library Expansion (`src/stdlib/`)**:
  * `std/math.rove` (`abs_val`, `max_val`, `min_val`, `power`, `clamp`, `gcd`, `sign`).
  * `std/str.rove` (`is_empty_str`, `concat_three`, `wrap_with`, `contains_substring`).
  * `std/io.rove` (`println_str`, `println_int`, `println_bool`, `prompt_input`).
  * `std/fs.rove` (`join_paths`, `file_extension`, `is_source_file`).
* **Toolchain & Release Engineering**:
  * `rove new`, `rove init`, `rove check`, `rove build`, `rove run`, `rove test`, `rove clean`, `rove doctor`, `rove lsp`.
  * `rove.toml` project manifest and deterministic `rove.lock` SHA256 locking.
  * Language Server Protocol v2 with autocomplete, hover signatures, and go-to-definition.
* **Test Verification**:
  * 138/138 Regression Battery (100%).
  * 10/10 Differential Parity across backends.
  * 530/530 Deterministic Fuzz cases (0 unhandled crashes).
  * 8/8 Native C++20 EXE conformance tests.
