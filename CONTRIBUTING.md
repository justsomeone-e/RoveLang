# Contributing to Rove

Rove is a compiler and toolchain. Changes to language meaning, MIR, runtime
behavior, and public formats need evidence across the layers they affect. Read
the [README](README.md) for the current toolchain and
[compiler roadmap](docs/internals/ROVE_DEEP_COMPILER_ARCHITECTURE.md) before
changing those boundaries. Search existing issues and pull requests before
starting substantial work.

Security vulnerabilities belong in the private process described in
[SECURITY.md](SECURITY.md). Do not disclose exploit details in an issue or pull
request.

## Set up a checkout

Fork or clone the repository and work on a topic branch. The required tools
depend on the area you change: Python runs the repository's test harness and
optional compiler orchestration; a C++20 toolchain, Node.js, Rust, or other
target toolchains are needed only for the corresponding executable backend
checks. See [installation instructions](INSTALLATION.md) for platform setup.

Use **Rove** in new user-facing text, code, and examples. New source files use
`.rove`. Keep the deliberate legacy aliases and Bundle ABI v1 symbols described
in the [migration guide](docs/ROVE_MIGRATION.md); renaming a versioned ABI
symbol in place breaks existing hosts.

## Make a focused change

- Explain the observed problem and the behavior your change produces. Keep the
  diff scoped to the owning layer and preserve unrelated working code.
- For a compiler fix, check parsing and types, Typed HIR, canonical MIR,
  legalization, the backend, and runtime behavior where they are affected. A
  backend must reject unsupported semantics before emission rather than
  silently approximate them.
- Add a regression case that fails before a semantic fix. Include a rejection
  case when changing a verifier, capability gate, or diagnostic. Compare
  results with the MIR interpreter or another backend when parity matters.
- Update documentation for changed commands, syntax, compatibility, or target
  support. Do not promote an experimental backend based only on source output.

## Verify the result

Run the focused checks for the files you changed, then inspect `git diff --check`
and the complete diff. Common entry points are:

```bash
python tests/ir_suite.py
python tests/mir_suite.py
python tests/mir_legalization_suite.py
python tests/self_host_suite.py
```

For VS Code extension changes, run `npm test` in `vscode-extension/`. For
Wasm code generation changes, regenerate the checked-in documentation example
with `python -m src.toolchain.docs_site`, inspect the generated diff, then run
`python tests/docs_site_suite.py`.

The broader regression command is `python -u tests/run_all_tests.py`; the
[CI workflow](.github/workflows/ci.yml) runs it across supported hosts. State
which checks you actually ran and which target runtimes or platforms remain
unverified. A type-check or build is not a runtime-parity result.

## Open a pull request

Describe the concrete before/after behavior, affected contracts, migration
impact, and validation results. Link the relevant issue when one exists.
Keep unrelated changes out of the pull request and use separate commits for
distinct logical changes. The project is licensed under
[Apache License 2.0](LICENSE).
