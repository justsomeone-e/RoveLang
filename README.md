# Rove

<p align="left">
  <a href="https://justsomeone-e.github.io/RoveLang/studio.html"><img src="https://img.shields.io/badge/Rove%20Studio-learn%20%26%20inspect-22C55E?style=for-the-badge&amp;logoColor=0F172A&amp;labelColor=0E1318" alt="Open Rove Studio"></a>
  <a href="https://justsomeone-e.github.io/RoveLang/"><img src="https://img.shields.io/badge/interactive%20tour-try%20in%20browser-00F0FF?style=for-the-badge&amp;logoColor=05070A&amp;labelColor=0E1318" alt="Try Tour of Rove Online"></a>
  <a href="VERSION"><img src="https://img.shields.io/badge/version-5.0.3-0E1318?style=for-the-badge&amp;logoColor=00F0FF&amp;labelColor=05070A" alt="Version"></a>
  <a href="https://github.com/justsomeone-e/RoveLang/releases"><img src="https://img.shields.io/badge/status-source%20preview-0E1318?style=for-the-badge&amp;logoColor=00F0FF&amp;labelColor=05070A" alt="Rove source preview"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-0E1318?style=for-the-badge&amp;logoColor=00F0FF&amp;labelColor=05070A" alt="Apache 2.0 License"></a>
  <a href="#backends"><img src="https://img.shields.io/badge/platforms-linux%20%7C%20win%20%7C%20macos-0E1318?style=for-the-badge&amp;labelColor=05070A" alt="Platforms"></a>
</p>

## About Rove

> *Did you ever dream of watching the stars from the gardens of Elysium?*

Rove began as **HolyEasyLang**, a small experiment by its developer: could
compiled programming become easier to approach without turning into a limited
toy language? There was no grand compiler platform at the beginning—only a
language, a growing collection of ideas, and the desire to see how far they
could be taken.

As native, JavaScript, Python, Rust, and WebAssembly targets were added, the
original direct AST-to-backend design could no longer guarantee that every
target understood a program in the same way. HolyEasyLang became **Nyx**, and
the project is now continuing as **Rove**. The compiler was rebuilt around one
checked representation shared by its
backends: **Typed HIR v1**.

Today, **Rove is a compiled, statically typed systems programming language
designed to keep source code approachable without hiding the machine
underneath it.**

A single compiler model lowers to native C++20, WebAssembly (WASM ABI v1), Node.js, and Python through an authoritative typed intermediate representation (**Typed HIR v1**) with byte-identical native self-hosting.

> [!IMPORTANT]
> **Nyx `v5.0.3` "Daydream"** is the last tag under the old name; a Rove release
> has not been published yet. This source tree uses the **Rove** identity.
> Existing `.nyx` source files, `nyx.toml`,
> `nyx.lock`, `nyx`, `nyxc`, and the versioned `nyx_host_v1` ABI remain accepted as
> compatibility surfaces while new projects use `.rove`, `rove.toml`, `rove.lock`,
> `rove`, and `rovec`.

<div align="center">
  <img src="assets/terminal_animated.svg?v=rove-preview-1" width="92%" alt="Rove interactive live execution"/>
</div>

<p align="left">
  <a href="https://justsomeone-e.github.io/RoveLang/"><b>TRY ONLINE (TOUR &amp; PLAYGROUND)</b></a> •
  <a href="#manifesto">MANIFESTO</a> •
  <a href="#language-tour">LANGUAGE TOUR</a> •
  <a href="#architecture">ARCHITECTURE</a> •
  <a href="#targets">TARGETS</a> •
  <a href="#bundle-abi">BUNDLE ABI</a> •
  <a href="#verification">VERIFICATION</a> •
  <a href="#install">INSTALL</a> •
  <a href="#tooling">TOOLING</a> • 
  <a href="#docs">DOCS</a>
</p>

---

<a id="manifesto"></a>

## `01` — The Engineering Manifesto

**Rove is a compiled, statically typed language for readable source code and explicit native targets.**

Rove keeps the source surface small while exposing target choices, generated code,
and runtime boundaries to the programmer.

```text
       High-Level Ergonomics                   Low-Level Machine Control
   ┌─────────────────────────────┐           ┌─────────────────────────────┐
   │ • Expression-bodied syntax  │           │ • Deterministic i64/f64     │
   │ • Values from if & match    │     ▲     │ • Zero-runtime cost defer   │
   │ • Linear pipe composition   │ ────┼──── │ • Deterministic scope exits │
   │ • First-class async Task<T> │     ▼     │ • Strict pointer-safe ABI   │
   │ • Unicode string transforms │           │ • No hidden GC stop-the-world│
   └─────────────────────────────┘           └─────────────────────────────┘
                                  ▲         ▲
                                  │         │
                       ONE UNIFIED COMPILER CONTRACT
```

Rove parses, type-checks, resolves modules, and lowers programs through one typed
intermediate representation (**Typed HIR v1**). Backends consume that checked
representation and report unsupported capabilities instead of silently changing
program semantics.

### Core Axioms

1. **Semantic Sovereignty**: The language semantics are established by the HIR v1 contract. Backends serve the specification; the specification never bends to target convenience.
2. **Correctness Before Feature Count**: A feature enters the language only after its lexer, parser, checker, HIR, verifier, backend, and differential tests pass:
   $$\text{Syntax} \longrightarrow \text{Lexer} \longrightarrow \text{Parser} \longrightarrow \text{Type Checker} \longrightarrow \text{HIR v1} \longrightarrow \text{Verifier} \longrightarrow \text{Backend} \longrightarrow \text{Differential Parity}$$
3. **No Leaky Boundaries**: When compiling to WebAssembly, memory and UTF-8 strings cross a versioned, pointer-free ABI without leaking raw pointers or allocator internals to host JavaScript/TypeScript.
4. **Reproducible Self-Hosting**: The production compiler compiles itself. A native stage-1 binary compiles stage 2, and stage 2 emits byte-identical stage-3 C++ output. Native `check`, `emit-cpp`, and `compile` work without Python; optional orchestration commands and the Python target still require it.
5. **Scope Discipline**: The v4 line intentionally decouples embedded microcontroller targets and focuses on native binaries (C++20), WebAssembly/Node.js, and Python/Rust tooling.

---

<a id="language-tour"></a>

## `02` — Language Tour

Rove supports top-level scripts and larger typed programs on the same language surface.

### Zero-Ceremony Scripting

For quick automation, pipelines, or algorithm prototyping, no `fn main()` or boilerplate wrapper is required. Top-level statements execute sequentially:

```rove
#target cpp

let base_freq: int = 5000
let multiplier: int = 2

// Direct top-level execution with pipelines
base_freq * multiplier |> print
```

### Functional Ergonomics & Value Semantics

Functions can be expression-bodied, branching produces values, and data flows naturally through forward-piping operators:

```rove
fn classify(code: int) -> string =
    match code {
        200 => "ok",
        404 => "not found",
        500 => "internal error",
        _   => "unknown"
    }

fn clamp_score(score: int) -> int =
    if score < 0 { 0 }
    else if score > 100 { 100 }
    else { score }

fn normalize_input(val: int) -> int =
    val * 2

fn main() {
    // Pipe composition with string interpolation
    let status = 200 |> classify
    let score  = 120 |> clamp_score |> normalize_input

    print($"Request status: {status} | Adjusted score: {score}")
}
```

### Systems Rigor: Safety, Scope, & Concurrency

When writing performance-critical systems code, Rove delivers structured safety without ceremony:

```rove
#target cpp

struct Build {
    name: string,
    score: int
}

trait Show {
    fn show(self) -> string
}

impl Show for Build {
    fn show(self) -> string {
        return $"{self.name}: {self.score}"
    }
}

// Typed, non-blocking Task primitive
async fn evaluate_metric(value: int) -> int {
    // Reject invalid input before the calculation
    guard value >= 0 else {
        throw "Metric value cannot be negative"
    }
    return value |> transform_metric
}

fn transform_metric(v: int) -> int = v * 2

async fn main() {
    let build = Build("production-host", 42)

    // LIFO scope cleanup (RAII semantics)
    defer print("[teardown] scope exited cleanly")

    // Concurrent task scheduling and resolution
    let task: Task<int> = evaluate_metric(build.score)
    let computed_score: int = await task

    // Explicit range iterations with loop control
    for pass in 1..4 {
        if pass == 2 { continue }
        print($"Running verification pass {pass}...")
    }

    let result = Build(build.name, computed_score)
    print($"Final artifact: {result.show()}")
}
```

Core v4 features: `let`/`var`/`const`, explicit `set`, `guard ... else`, `defer`, `match`, `if`/`elif`/`else`, `for` ranges, `while`, `loop`, `try`/`catch`/`throw`, `async`/`await`, `Task<T>`, pipelines (`|>`), structs, traits, implementations, in-file test blocks (`test "name" { assert(...) }`), null-safe navigation, string interpolation, and explicit `unsafe` boundaries. Complete grammar specification: [`docs/SYNTAX_SPEC.md`](docs/SYNTAX_SPEC.md).

> **Runnable Examples**: Check out the [`examples/`](examples/) directory for ready-to-run programs covering math scripts, DSP pipelines, null-safety, in-file test suites, memory inspectors, and foreign C++/Node.js/Python bindings.

---

<a id="architecture"></a>

## `03` — Compiler Architecture

The Rove toolchain operates through an authoritative, deterministic middle-end:

<div align="center">
  <img src="assets/pipeline_animated.svg?v=rove-preview-1" width="98%" alt="Rove compiler architecture pipeline"/>
</div>

```text
                      ROVE SOURCE CODE (.rove)
                               │
                               ▼
                   [ UTF-8 Lexer / Scanner ]
                               │
                               ▼
                   [ Canonical Syntax Parser ]
                               │
                               ▼
            [ Dependency Graph & Semantic Type Checker ]
                               │
                               ▼
                 ┌───────────────────────────┐
                 │    TYPED HIR v1 BOUNDARY   │  ◄── Single Source of Truth
                 │  (Canonical Deterministic) │
                 └───────────────────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
     HIR Verifier     Dead-Code Elimination   Deterministic Passes
            │                  │                  │
            └──────────────────┼──────────────────┘
                               │
                               ▼
               [ Capability-Gated Backend Emitter ]
         ┌─────────────┬─────────────┬─────────────┬─────────────┐
         ▼             ▼             ▼             ▼             ▼
       C++20       Node.js       Python 3     WASM ABI v1     Rust 2021
      (Native)    (ES2022)      (Reference)    (Wat/Wasm)     (Preview)
```

### Reproducible Native Self-Hosting

Rove does not depend on a host runtime. The production toolchain compiles itself through a hermetic bootstrap cycle:

```text
stage-0 bootstrap (Python reference)
       │
       ▼
native rovec (stage 1) ──► generates stage-2 C++ ──► compiled to native stage 2
                                                         │
                                                         ▼
                                       emits byte-identical stage-3 C++
```

* **No Python Dependency**: The distributed `rovec` native compiler performs `check`, `emit-cpp`, `compile`, and targets queries independently.
* **Topological Module Resolution**: Handles diamond dependencies, eliminates module duplicates, detects circular imports, and resolves symbols deterministically.

---

<a id="targets"></a>
<a id="backends"></a>

## `04` — Compiler & Backend Matrix

Rove exposes multiple code-generation backends with explicit capability gating. Targets that cannot support a language feature fail at compile time with a clear diagnostic instead of silently producing deviant runtime behavior.

```text
┌─────────────┬──────────────────────────────┬──────────────┬───────────────┐
│ Target      │ Artifact                     │ Maturity     │ HIR Authority │
├─────────────┼──────────────────────────────┼──────────────┼───────────────┤
│ cpp         │ C++20 / Native Executable    │ Stable       │ Authoritative │
│ js          │ ES2022 / Node.js Module      │ Stable       │ Authoritative │
│ python      │ Python 3 Standalone / Script │ Stable       │ Authoritative │
│ wasm        │ WAT + WASM ABI v1            │ Beta         │ Authoritative │
│ rust        │ Rust 2021 Source / Crate     │ Beta         │ Authoritative │
│ react       │ React 19 TSX Module / Hook   │ Beta         │ Tooling-Level │
│ asm         │ x86_64 Assembly (Intel)      │ Beta         │ via C++       │
└─────────────┴──────────────────────────────┴──────────────┴───────────────┘
```

### Concrete Machine Contract

| Subsystem | Exact Compiler Guarantee |
| :-- | :-- |
| **Source Standard** | Strictly UTF-8 encoded `.rove` files with 44 canonical v4 keywords. |
| **Integer Semantics** | Signed `i64` with defined two's-complement overflow wrapping, integer division, and bitwise shifts. |
| **Floating-Point** | IEEE-754 `binary64` with canonical cross-platform formatting for `nan`, `inf`, and `-0.0`. |
| **String Architecture** | UTF-8 sequences with embedded `\0` safety, `\uXXXX` escapes, interpolation, and zero implicit normalization mutations. |
| **Compilation Gate** | Checked against Typed HIR v1 verifier; pass runs deterministically across all environments. |
| **Native Toolchain** | Zero-dependency emission compatible with standard Clang++ (≥14), GCC/G++ (≥11), or MSVC (≥2019/2022). |

---

<a id="bundle-abi"></a>

## `05` — Zero-Leak WebAssembly: Bundle ABI v1

Compiling for the web should not require manually orchestrating memory offsets, byte lengths, and pointer arithmetic in JavaScript. Rove packages complete WebAssembly modules with type-safe host wrappers in a single command:

```bash
rove bundle src/crypto.rove --output dist/crypto
rove bundle src/crypto.rove --output dist/crypto --react
rove bundle src/crypto.rove --output dist/crypto --package --react --vue --svelte
```

### Emitted Artifact Suite

| Generated Artifact | Purpose & Role |
| :-- | :-- |
| `<module>.wat` | Human-readable, auditable WebAssembly text representation |
| `<module>.wasm` | Valid, standalone `wasm32` binary payload |
| `<module>.mjs` | ES2022 loader with grow-safe views, typed marshalling, host imports, and Promise caching |
| `<module>.d.ts` | 100% pointer-free TypeScript declaration interface |
| `<module>.react.tsx` | Native React 19 client hook with Concurrent Mode / Suspense safety |
| `package.json` | Optional npm manifest with conditional exports and Rove ABI metadata |
| `<module>.{react,vue,svelte}.{mjs,d.ts}` | Optional framework adapters for React 19, Vue 3, and Svelte 5 |

### Memory Protocol

ABI v1 requires modules to export `memory`, `__nyx_alloc(i32)`, `__nyx_free(i32, i32)`, and `__nyx_abi_version() -> 1`. Strings cross the boundary as a packed 64-bit scalar `(length << 32) | pointer`; numeric arrays use borrowed `(pointer, length)` pairs. The generated JavaScript layer refreshes views after heap growth, releases input buffers inside `finally` blocks, and frees caller-owned return strings immediately after decoding. Browser capabilities use the separately versioned `nyx_host_v1` import namespace. These names remain fixed for ABI v1. Versioning and ownership rules are defined in [`docs/internals/COMPATIBILITY_CONTRACTS.md`](docs/internals/COMPATIBILITY_CONTRACTS.md).

```tsx
'use client'

import { useRoveModule } from './crypto.react'

export function VerificationWidget() {
    const { hashToken } = useRoveModule()
    return <div>Digest: {hashToken("payload-secret")}</div>
}
```

*The generated Promise cache reuses the module instance under React Strict Mode.*

### Browser host API

`std/web` exposes typed opaque handles for DOM nodes, events, listeners, and
Canvas 2D operations. Rove code imports no browser globals directly; the
generated ESM loader supplies and validates host ABI v1. A complete keyboard
and animation-loop example lives in [`examples/web_pong`](examples/web_pong/README.md).

---

<a id="verification"></a>

## `06` — Verification

The repository checks language invariants across target boundaries with
focused suites. The Rove migration has targeted MIR legalization, self-host,
Bundle ABI, installer, editor, and documentation-site checks. The full
regression battery must be rerun before a Rove release is declared:

```bash
python tests/mir_legalization_suite.py
python tests/self_host_suite.py
python tests/docs_site_suite.py
python tests/run_all_tests.py
```

---

<a id="diagnostics"></a>

## `07` — Diagnostics v2

Compiler errors should instruct, not confuse. Rove diagnostics feature precise source spans, context snippets, and machine-actionable hints indexed in [`ERROR_REFERENCE.md`](ERROR_REFERENCE.md):

```text
error[E1302]: ambiguous symbol collision
  --> src/network/client.rove:24:9
   |
24 |     use protocol.packet
   |         ^^^^^^^^^^^^^^^
   |
   = note: symbol 'packet' is exported by both 'core::transport' and 'protocol'
   = help: qualify the import explicitly: 'use protocol::packet as WirePacket'
```

---

<a id="install"></a>

## `08` — Installation

Installers for Windows, Linux, and macOS are included in this source tree.
Published v5 binaries still use the Nyx names. The Rove installer builds from
this checkout until Rove release assets are published; it creates the `rove`
command (`rove.cmd` on Windows) alongside the native `rovec` compiler.

### Windows (PowerShell)

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

### Linux & macOS (Bash)

```bash
chmod +x install.sh
./install.sh
```

### Toolchain Dependencies

| Target | Host Requirement |
| :-- | :-- |
| **`cpp` (Default)** | Any standard C++20 compiler: Clang++, GCC/G++, or MSVC `cl` |
| **`js`** | Node.js (≥18 LTS with ES2022 support) |
| **`python`** | Python 3.10+ |
| **`rust`** | `rustc` / Cargo (2021 edition) |
| **`wasm`** | None (Rove bundles its own binary WAT/WASM assembler) |

Run the built-in diagnostic doctor to verify your environment:

```bash
rove doctor
```

---

<a id="tooling"></a>

## `09` — Developer Tooling & VS Code

Rove's editor support covers diagnostics, navigation, and common build commands.

<div align="center">
  <img src="assets/features_animated.svg?v=4.0.0" width="98%" alt="rove features"/>
</div>

### Local Visual Studio Code Extension

The repository includes a zero-telemetry local VS Code extension:

* **Language Server Protocol**: Built-in JSON-RPC server powering syntax diagnostics, hover documentation, completion, and definition lookups.
* **Persistent Execution Console**: Windows executables run in an integrated persistent shell—never closing abruptly before you inspect output.
* **Commands**: **Run**, **Build**, **Check**, and **Doctor** shortcuts with configurable keybindings.

Package it from `vscode-extension` with `npm ci` and `npm run package`, then
install the resulting VSIX with VS Code. A Rove VSIX has not been published yet.

Use VS Code's **Extensions: Install from VSIX...** command for the packaged file.

The Windows and Unix installers also register the bundled extension
automatically when VS Code, VS Code Insiders, or VSCodium is detected. Restart
the editor after installation; `.rove` files should display `Rove` as their
language mode.

---

<a id="workflow"></a>

## `10` — Command Line Workflow

```bash
# Initialize a new Rove project workspace
rove new telemetry_service
cd telemetry_service

# Run type checking and HIR semantic analysis
rove check src/main.rove

# Build and execute with the default native C++20 backend
rove run src/main.rove

# Compile an optimized standalone native release binary
rove build src/main.rove --target cpp --release

# Execute via the Node.js ES2022 backend
rove run src/main.rove --target js

# Emit standalone Intel-syntax x86_64 assembly (.s)
rove build src/main.rove --target asm

# Package for WebAssembly with TypeScript bindings
rove build src/main.rove --target wasm

# Choose an output directory and optionally emit the React 19 hook
rove bundle src/main.rove --output dist/bundle --react

# Run native self-hosting compiler commands directly
rovec check src/main.rove
rovec emit-cpp src/main.rove -o dist/main.cpp
rovec compile src/main.rove -o dist/main
```

---

<a id="roadmap"></a>

## `11` — Nirvana and the Road to v5

The Rove release lifecycle is bound to verifiable technical milestones rather than calendar estimates:

| Version | Codename | Conceptual Meaning | Core Architectural Milestone | Status |
| :-- | :-- | :-- | :-- | :-- |
| `v2.x` | — | — | Initial compiler pipeline, standard library, CLI baseline | Historical |
| `v3.x` | — | — | Bundle ABI, Unicode compliance, cross-backend parity | Historical |
| `v4.0.0-dev` | **Maya** | *Illusion / Appearance* | Microcontroller decoupling, typed HIR v1 expansion, self-hosting | Completed |
| `v4.0.0-rc.1` | **Samsara** | *Cycle of Existence* | First cross-platform release candidate, verification battery, VSIX | Published |
| `v4.0.0-rc.2` | **Bodhi** | *Awakening* | Browser host ABI, std/web, npm bundles, local dependencies | Published |
| `v4.0.0-rc.3` | **Moksha** | *Liberation* | Backend-parity development work incorporated into Nirvana | Not published separately |
| `v4.0.0` | **Nirvana** | *Stability* | Stable v4 language, toolchain, and ABI contract | Official Release |
| `v4.5.0` | **Ivory** | *Purity / Bridge* | Compatible tooling, library parity, package manager, and experimental C17/LLVM IR emitters | Release |
| `v5.0.0` | **Daydream** | *The next form imagined* | Direct LLVM pipeline, aggregate lowering, CLI integration, and preserved stable backend contracts | Official Release |
| `v5.0.1` | **Daydream** | *Reliability patch* | Windows installer resilience, native foreign imports, optional-null lowering, and corrected examples | Official Patch |
| `v5.0.2` | **Daydream** | *Checked compiler foundations* | MIR contracts, module/generic validation, backend pilots, installer hardening, and Tour learning path | Official Patch |
| `v5.0.3` | **Daydream** | *Studio maintenance* | Single-run browser preview, isolated Tour/Studio state, and documentation refresh | Tagged; Rove migration in source |
| `v6.0.0` | **Sepia** | *Memory / Preservation* | Future compiler milestone | Planned |
| `v7.0.0` | **Solace** | *Calm after complexity* | Future ecosystem milestone | Planned |
| `v8.0.0` | **Last Signal** | *The final transmission* | Long-term language-platform milestone | Long-term |

The [backend gates](docs/internals/ROADMAP_AND_BACKEND_GATES.md) keep maturity
claims explicit. New backends begin experimental; the v5 stable designation
does not promote LLVM or C17 beyond their documented capability contracts.

---

<a id="project-structure"></a>

## `12` — Project Structure

```text
rove/
├── compiler/          # Self-hosted compiler written in Rove (Frontend, HIR Lowerer, C++ Emitter)
├── src/
│   ├── core/          # Stage-0 Lexer, Parser, Type Checker, Module Resolution, Diagnostics
│   ├── ir/            # Typed HIR v1 definition, serialization passes, semantic verifier
│   ├── codegen/       # Target emitters (C++20, JS, Python, Rust, WASM, ASM), Native Linkers
│   ├── self_host/     # Stage reproducibility & bootstrap orchestration
│   ├── stdlib/        # Capability-gated standard library modules
│   └── cli.py         # Primary rove CLI entrypoint
├── vscode-extension/ # VS Code extension (LSP client, syntax, themes, snippets, task runners)
├── tests/             # Regression suites, backend parity, differential fuzzing, ABI tests
├── tools/             # Reproducible release packagers, SBOM generators, audit scripts
├── docs/              # Specifications, language references, and internal decision records
├── assets/            # Official visual identity assets and animated architecture diagrams
├── install.ps1        # Native Windows installer script
├── install.sh         # Native Linux / macOS installer script
└── VERSION            # Single source-of-truth version declaration
```

---

<a id="docs"></a>

## `13` — Documentation Index

| Resource | Scope |
| :-- | :-- |
| [`GETTING_STARTED.md`](GETTING_STARTED.md) | First project guide, basic workflows, and compiler flags |
| [`INSTALLATION.md`](INSTALLATION.md) | In-depth platform guide and native C++ compiler setup |
| [`LANGUAGE_REFERENCE.md`](LANGUAGE_REFERENCE.md) | Exhaustive language manual: types, ownership, and syntax |
| [`docs/SYNTAX_SPEC.md`](docs/SYNTAX_SPEC.md) | Formal EBNF grammar, expressions, types, and Task mechanics |
| [`CLI_REFERENCE.md`](CLI_REFERENCE.md) | Complete CLI documentation: flags, options, and commands |
| [`ERROR_REFERENCE.md`](ERROR_REFERENCE.md) | Comprehensive catalog of compiler diagnostic error codes |
| [`docs/internals/ROADMAP_AND_BACKEND_GATES.md`](docs/internals/ROADMAP_AND_BACKEND_GATES.md) | Architecture decision records, RFCs, and release gates |
| [`CHANGELOG.md`](CHANGELOG.md) | Chronological version history and migration notes |

---

<a id="contributing"></a>

## `14` — Contributing

We welcome contributions from systems engineers, compiler authors, and language enthusiasts.

Before opening a pull request, verify that:
1. **Determinism is Maintained**: Compiler output must be bit-for-bit identical across runs.
2. **HIR Contracts are Respected**: Never emit target code directly from the AST; all transformations must pass through Typed HIR v1.
3. **Verification Battery Passes**: All 138+ regression tests, 194 HIR parity tests, and 530 fuzz passes must succeed:
   ```bash
   python -m unittest discover tests
   rove self-host verify
   ```
4. **Diagnostics are Actionable**: Error messages must carry precise spans and clear explanations.

---

<a id="license"></a>

## `15` — License & Commercial Freedom

The Rove compiler, standard library, and associated tooling are licensed under the **Apache License, Version 2.0**.

### Commercial Freedom & Trademark Protection

**Your code is your own.**

- **No Viral Restrictions**: You are 100% free to license, distribute, sell, or keep proprietary any software, binaries, libraries, or WebAssembly modules you create with Rove.
- **Trademark Protection (Section 6)**: The Apache 2.0 license explicitly protects the Rove name, logo, and brand against unauthorized commercial hijacking, misrepresentation, or false endorsement.
- **Patent Grant (Section 3)**: Grants an explicit, perpetual patent license covering contributor patents to protect users and downstream developers.


See [`LICENSE`](LICENSE) for full legal terms.

