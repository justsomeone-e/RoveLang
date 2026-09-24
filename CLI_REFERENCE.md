# 💻 Rove CLI & Command Reference

The `rove` toolchain provides project scaffolding, validation, multi-target
compilation, testing, formatting, language services, and deterministic
manifest/lockfile management.

---

## 🛠️ Commands Overview

```bash
rove <command> [arguments] [options]
```

### 1. `rove new <project_name>`
Creates a standard Rove project structure:
```text
my_project/
├── rove.toml
├── rove.lock
├── .gitignore
└── src/
    └── main.rove
```

### 2. `rove init [name]`
Initializes `rove.toml` and `rove.lock`. Existing manifests require explicit `--force`.

### 3. `rove check [file.rove]`
Performs fast static semantic and type-checking across project source files without invoking backend compilers.

### 4. `rove build [file.rove] [--target <backend>] [--release]`
Transpiles and builds the program into the `build/<target>/` directory.
Supported targets:
* `--target cpp` (Default: C++20 / Native Executable)
* `--target js` (Node.js ES2022 Module)
* `--target python` (Python 3)
* `--target rust` (Rust 2021 Source)
* `--target wasm` (WAT, WebAssembly binary, ES2022 loader, and TypeScript declarations)
* `--target react` (React 19 TSX preview)
* `--target asm` (Intel-syntax x86_64 assembly through the native toolchain)

Native console executables finish when `main` returns; use `rove run file.rove` to keep their
output visible in the current terminal instead of double-clicking the EXE.

### 5. `rove run [file.rove] [--target <backend>]`
Builds and executes the entrypoint immediately on the specified host backend.

### 6. `rove test [file.rove | all]`
* If a file is specified: Runs in-file `test "..." { assert(...) }` blocks.
* If omitted or `all`: Runs the master regression test framework.

### 7. `rove doctor`
Diagnoses host system dependencies (Python, LLVM Clang, Node.js, Rust, and Git) and outputs remediation instructions for missing compilers.

### 8. `rove lsp`
Launches the JSON-RPC 2.0 Language Server Protocol daemon for editor integrations (VS Code, Neovim, Emacs).

### 9. `rove fmt <file.rove>`
Applies string/comment-safe, idempotent source formatting. Missing files return nonzero.

### 10. `rove clean`
Removes temporary build artifacts and directories (`build/`, `target/`, `__pycache__`).

### 11. `rove lint <file.rove>`
Reports style and unsafe-boundary warnings without treating warnings as process failures.

### 12. `rove debug <file.rove>`
Opens the validated source-line inspector. Runtime values are not fabricated;
runtime source maps and variable inspection are not part of RC1.

### 13. `rove profile <file.rove> [--target <backend>]`
Runs the real compile+execute path and reports measured whole-program wall time.
It does not print synthetic function timings.

### 14. `rove doc <file.rove>`
Generates escaped HTML API documentation from `///` comments.

### 15. `rove add <package> [@version] [--path <directory>]`
Adds an explicit dependency to `rove.toml` and regenerates `rove.lock`. Local
path dependencies are resolved recursively, cycle-checked, content-hashed, and
recorded with canonical relative paths.

### 16. `rove remove <package>`
Removes a dependency from the manifest and lockfile. Missing dependencies return nonzero.

### 17. `rove install`
Validates manifest dependencies and regenerates `rove.lock`. The RC2 contract
supports deterministic local path dependencies; remote registry download is
not enabled.

### 18. `rove pkg`
Displays project metadata, dependencies, native settings, and build configuration.

### 19. `rove targets [--json]`
Displays the human-readable or machine-readable backend and standard-library
capability contract.

### 20. `rove bundle <file.rove> --output <dir> [--package] [--react] [--vue] [--svelte]`
Writes the WASM ABI v1 package to an explicit directory. `--package` adds an
npm manifest; framework flags add typed React 19, Vue 3, or Svelte 5 adapters.
Vue and Svelte adapters require `--package`.
