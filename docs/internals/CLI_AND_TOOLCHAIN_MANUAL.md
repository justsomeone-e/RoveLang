# Nyx — CLI & Enterprise Toolchain Manual

## 1. Toolchain Overview

Nyx provides a unified `nyx` CLI covering project scaffolding, type-checking,
native compilation, direct execution, in-file testing, formatting, editor
services, documentation, and manifest/lockfile management.

```text
                                nyx CLI
                                   │
       ┌───────────┬───────────────┼───────────────┬───────────┐
       ↓           ↓               ↓               ↓           ↓
  [ nyx new ] [ nyx check ] [ nyx build ]  [ nyx run ] [ nyx test ]
```

---

## 2. Project Conventions & Manifest (`nyx.toml`)

Every Nyx project contains a `nyx.toml` manifest file at its root:

```toml
[package]
name = "my_project"
version = "0.1.0"
edition = "2026"
target = "cpp"          # Default target backend: cpp, python, js, rust
entry = "src/main.nyx"    # Application entrypoint

[dependencies]
# std = "4.0.0"
# math = "1.0.0"

[build]
opt_level = 2
debug = false
```

### Standard Project Layout
```text
my_project/
├── nyx.toml              # Package manifest
├── nyx.lock              # Deterministic dependency lockfile
├── .gitignore            # Standard git ignore rules
├── src/
│   └── main.nyx          # Main entrypoint
└── build/                # Output binaries and transpiled modules
    ├── cpp/
    │   └── main[.exe]    # Native C++20 executable (.exe on Windows)
    ├── js/
    │   └── main.js       # Node.js / Browser ESM Module
    └── rust/
        └── main.rs       # Rust 2021 Source
```

---

## 3. Command Reference

### Project Scaffolding
* `nyx new <project_name>`: Scaffolds a project with `nyx.toml`, `src/main.nyx`, and editor tasks.
* `nyx init [name]`: Initializes `nyx.toml` and `nyx.lock`; refuses to overwrite unless `--force` is explicit.

### Build & Verification
* `nyx check [file.nyx]`: Performs syntax and semantic validation without code generation.
* `nyx build [file.nyx] [--target <cpp|python|js|rust>]`: Emits or compiles into `build/<target>/`.
  * If targeting `cpp`, compiles directly to a native executable (`.exe` only on Windows).
  * If targeting `js`, emits an ES2022 Node.js module.
  * If targeting `rust`, emits clean, borrow-checked Rust 2021 code.
* `nyx run [file.nyx] [--target <cpp|python|js|rust>]`: Compiles and executes with the selected backend.
* `nyx build [file.nyx] --target js --esm`: Emits an import-safe ES2022 `.mjs`
  module. Public Nyx functions are explicit exports and `main()` is not invoked
  as an import side effect.
* `nyx build [file.nyx] --target wasm --wasi`: Emits the normal WASM artifact
  set with a WASI preview1 `fd_write` import and `_start` executable entry point.
  The RC3 profile currently supports string arguments to `print`; richer WASI
  filesystem/argument APIs remain separately capability-gated.
* `nyx clean`: Removes local `build/`, `target/`, and `__pycache__/` artifacts.

### Testing & Quality Assurance
* `nyx test`: Runs the unified compiler/backend regression framework.
* `nyx test <file.nyx>`: Runs in-file test blocks through the reference target.
* `nyx fmt <file.nyx>`: Applies string/comment-safe, idempotent source formatting.
* `nyx lint <file.nyx>`: Reports static style and unsafe-boundary warnings.
* `nyx debug <file.nyx>`: Opens a validated source-line inspector. It does not invent runtime values; runtime source maps remain future work.
* `nyx profile <file.nyx> [--target t]`: Executes a real compile+run and reports measured whole-program wall time. Function-level instrumentation is not yet available.
* `nyx doc <file.nyx>`: Generates escaped local HTML API documentation from `///` comments.

### Package Management
* `nyx add <package> [@version] [--path <directory>]`: Mutates `nyx.toml` and regenerates `nyx.lock`.
* `nyx remove <package>`: Removes one dependency from both manifest and lockfile.
* `nyx install`: Validates manifest dependencies and regenerates the lockfile.
* `nyx pkg`: Displays the current project, dependencies, native settings, and build configuration.

The RC2 package contract resolves recursive local path dependencies with
canonical slash-normalized relative paths, SHA-256 content fingerprints, and
cycle diagnostics. Both `nyx.toml` and `nyx.lock` use the same portable path
spelling on Windows, Linux, and macOS.
There is no remote package registry download; `nyx install` states this
explicitly and never reports a fake network installation.

### WebAssembly builds

`nyx build src/main.nyx --target wasm` writes the complete ABI v1 package to
`build/wasm/`: WAT, a WebAssembly binary, an ES2022 loader, and TypeScript
declarations. Use `nyx bundle src/main.nyx --output <dir> [--package] [--react]
[--vue] [--svelte]` when the output directory, npm metadata, or framework
adapters must be selected explicitly.

### Toolchain Diagnostics
* `nyx version`: Displays compiler version and detected host toolchains.
* `nyx doctor`: Reports actionable C++20, Node.js, Rust, and Python availability.
* `nyx targets --json`: Prints the machine-readable backend/stdlib capability contract; requires the optional Python orchestration layer.

### Arch Linux and editor setup

The native C++ target requires a host C++20 compiler. On Arch Linux install the
standard development toolchain before running Nyx programs:

```bash
sudo pacman -S --needed base-devel
nyx doctor
```

The Unix installer detects VS Code, VS Code Insiders, and VSCodium and installs
the Nyx grammar automatically. Node.js/npm enables the full LSP client; without
npm the syntax grammar is still installed and the installer reports that only
language-server features are unavailable. Restart the editor after installation
and confirm the language indicator reads `Nyx` for `.nyx` files.
## Target selection

`#target` is optional. Without an override Nyx uses the native C++20 target.
Target selection has one deterministic precedence order:

1. `--target <name>`, `--target=<name>`, or `-t <name>`
2. the source file's `#target <name>` directive
3. `nyx.toml`'s configured target
4. the native `cpp` default
