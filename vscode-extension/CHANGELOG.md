# Change Log

## 5.0.2 — Daydream

- Highlight embedded C++, JavaScript, and Rust inside the corresponding
  `#native raw`, `#native cpp`, `#native js`, and `#native rust` blocks.
- Install the extension automatically from the Unix installer when VS Code,
  VS Code Insiders, or VSCodium is detected.

## 5.0.1 — Daydream

- Synchronize the extension package with the Nyx v5.0.1 compiler and language
  surface.
- Resolve the canonical `~/.nyx/bin/nyx` command on Linux and macOS as well as
  the Windows `nyx.cmd` shim.

## 4.0.0 — Nirvana

- Official release aligned with Nyx v4.0.0 Nirvana compiler and language specification.
- Updated syntax grammar with full support for v4 built-ins (`args`, `map`, `filter`, `fold`, `contains`, `is_number`).
- Added snippets for enums, type aliases, result handling (`Ok`/`Err`), and functional collection transforms (`map`/`filter`).
- Synchronized canonical completion catalog and language surface metadata (`language-surface.json`).
- Updated target options (`cpp`, `js`, `python`, `wasm`, `rust`, `react`, `asm`).
- Verified zero-latency LSP diagnostics and persistent integrated console execution.

## 4.0.0-rc.2

- Align the extension catalog and package version with the Bodhi RC2 compiler.
- Add the typed `std/web` surface to completion metadata.

## 4.0.0-rc.1

- Align the extension package with the Nyx v4.0.0-rc.1 release candidate.
- Added full syntax highlighting for string interpolation (`$"..."` with `{expression}` blocks).
- Added syntax grammar coverage for `yield`, boolean operators (`and`, `or`, `not`), and `Iterator`.
- Added new snippets for `trait` definitions, `impl Trait for Struct`, and `async fn`.
- Synced and verified `language-surface.json` compiler metadata catalog.
- Bundled official release candidate VSIX package (`nyx-language-support-4.0.0-rc.1.vsix`).

## 4.0.0-dev.2

- Removed STM32/Nucleo/freestanding targets and their board completions.
- Removed the obsolete `volatile`, `interrupt`, `critical`, `Buffer<T, N>`, and
  `buffer_ptr` language surface.
- Synced syntax highlighting, snippets, LSP completions, and the canonical
  43-keyword compiler catalog.

## 4.0.0-dev.1

- Added one-click Run, Build, Check, and Toolchain Doctor commands.
- Run and Build now use VS Code's persistent integrated task terminal.
- Synchronized completions, snippets, icons, and LSP startup with the v4 language surface.
- Promoted the visible extension identity to **Nyx Language Toolchain** and
  replaced the undersized dark marketplace mark with a larger transparent icon.
- Added manifest-level homepage, issue tracker, and gallery metadata.
- Added Command Palette links for GitHub, documentation, releases, the compiler
  roadmap, and issue reporting.
- Prefer the canonical `~/.nyx/bin/nyx` installation before `PATH` to avoid
  accidentally launching an older language server shim.
