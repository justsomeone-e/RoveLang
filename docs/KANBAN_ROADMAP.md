# Rove Historical Kanban (Archived)

This document preserves the role of the original pre-v4 planning board, but it
is no longer an active task list. Its lexer, parser, C++ code generation,
functions, control flow, arrays, structs, modules, native interop, and VS Code
milestones have either shipped or been superseded by the typed-HIR v4 design.

The only current sources of truth are:

- [`TODO.md`](TODO.md) for open implementation and release work;
- [`internals/ROADMAP_AND_BACKEND_GATES.md`](internals/ROADMAP_AND_BACKEND_GATES.md)
  for backend maturity, release gates, codenames, and post-RC targets;
- [`internals/RELEASE_AUDIT_v4.0.0-rc.1.md`](internals/RELEASE_AUDIT_v4.0.0-rc.1.md)
  for the RC1 release blockers.

Rove source files use the `.rove` extension. The v4 canonical hosted target IDs
are `cpp`, `js`, `python`, `rust`, `wasm`, `react`, and `asm`.
