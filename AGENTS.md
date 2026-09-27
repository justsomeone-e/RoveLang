# Rove repository agent instructions

These instructions apply to work in this repository. Act as the engineer
responsible for correctness of the change, not as a code generator trying to
maximize output. User instructions take precedence. A passing check proves only
the behavior it actually exercised.

## Establish the current state

1. Read `git status --short --branch` and `git worktree list` before editing.
   Preserve unrelated and untracked work. Do not reset, clean, force-push, or
   delete important files without explicit authorization.
2. Read the relevant source, its callers, the nearest tests, and `VERSION`.
   For compiler architecture, read
   `docs/internals/ROVE_DEEP_COMPILER_ARCHITECTURE.md` and the applicable
   contract in `docs/internals/ROADMAP_AND_BACKEND_GATES.md`. Check source and
   tests against those documents; a roadmap is not implementation evidence.
3. Identify the public boundary before changing it: source syntax, Typed HIR,
   Canonical MIR, diagnostic, runtime behavior, ABI, file format, CLI, editor
   protocol, or generated artifact. State the migration consequence if the
   boundary changes.
4. Keep the task in a bounded vertical slice. Fix the owning layer, inspect
   callers and side effects, then verify. Do not widen a local repair into an
   unrelated refactor or add a new backend simply to increase coverage.

## Naming and compatibility

- **Rove** is the public name. New source and project files use `.rove`,
  `rove.toml`, `rove.lock`, `rove`, and `rovec`; user-facing docs, Studio, Tour,
  and examples use Rove. Read `docs/ROVE_MIGRATION.md` before a rename.
- Legacy `.nyx` input and names explicitly listed as compatibility aliases are
  supported during migration. Bundle ABI v1 symbols such as `__nyx_top_level`
  and `nyx_host_v1` are versioned contracts. Do not mechanically rename or
  remove them. A new ABI identity needs a new version and migration path.
- Keep the editor's canonical `.rove` experience working. If a feature is
  temporarily routed through legacy `.nyx` tooling, verify the actual `.rove`
  workflow and document the compatibility route; do not call the alias a native
  `.rove` implementation.

## Compiler authority and acceptance

- The production compiler currently uses checked Typed HIR v1. Canonical MIR
  and its migrated emitters have explicit pilot boundaries. Do not silently
  redirect the default compiler path or promote a pilot to stable.
- Source semantics belong in parsing, checking, Typed HIR, canonical lowering,
  and MIR as appropriate. A backend may choose a representation, ABI adapter,
  or target runtime; it may not invent evaluation order, ownership, errors,
  numeric behavior, or cleanup semantics.
- Every MIR transformation must preserve types, source spans, block targets,
  effect information, and deterministic serialization where promised. Verify
  both the input and output of a pass. Malformed MIR must fail in the verifier;
  target-incompatible MIR must fail in legalization with a stable diagnostic
  before emitter dispatch. No approximate fallback is acceptable.
- Preserve the signed-i64, binary64, UTF-8, string/display, left-to-right
  evaluation, Result, user-throw versus runtime-trap, and lexical-cleanup
  contracts where the changed feature touches them. Compare against the MIR
  interpreter and the old backend oracle when they cover the same behavior.
- Do not describe parsing, emitting an artifact, or compiling generated code
  as semantic parity. A backend's claimed maturity requires positive,
  negative, runtime, and differential evidence for its declared surface.

## Ownership review: treat every value like a borrow-checker case

For an ownership-affecting change, trace each value through construction,
assignment, copy, move, borrow, projection, call, return, and destruction.
Check every CFG edge: fallthrough, branch, loop, early return, `?`, throw,
catch, call unwind, suspend, and suspend unwind. Answer these questions before
declaring the change correct:

- Is a value initialized before every read? Can a moved value be read again?
- Does each owned value have one valid owner at each point? Can a mutable alias
  observe a copy or projected write that should be isolated?
- Does copy detach every nested owned field and tagged payload required by
  Rove value semantics? Does move transfer without an accidental second copy?
- Does each initialized value receive its required cleanup exactly once on
  every exit? Can overwrite, partial move, drop, or a throwing deferred action
  cause a leak, double drop, or use-after-move?
- Does layout use target-defined size, alignment, and offsets rather than an
  assumed slot width? Are bounds, tag, and type checks applied before access?

If the current model cannot prove a case, keep it behind a capability or
verifier gate and state the limitation. Do not pretend Rove has Rust's borrow
checker; this is the standard of review for its current explicit ownership
model.

## Verification proportional to the change

- Add a focused regression that would fail before a semantic fix. Exercise an
  admitted case and a rejected case when changing legalization. For value
  semantics, test both observed result and copy isolation; for cleanup, cover
  the relevant alternate CFG exit. Test the actual target artifact where the
  target toolchain is available.
- Use the relevant focused suites: `tests/mir_suite.py`,
  `tests/mir_lowering_suite.py`, `tests/mir_cleanup_suite.py`,
  `tests/mir_memory_abi_suite.py`, `tests/mir_legalization_suite.py`,
  `tests/self_host_suite.py`, and `tests/docs_site_suite.py`. Run the affected
  suite again after the final source edit. Do not report an earlier pass as
  post-fix evidence.
- After a Wasm codegen change, run `python -m src.toolchain.docs_site` before
  the docs-site suite so checked-in generated Wasm bytes match the source.
  Inspect generated diffs; include only expected artifacts.
- `python tests/run_all_tests.py` is a release-level battery, not a substitute
  for focused debugging. Run it when the scope or release gate requires it.
  Distinguish toolchain metadata/type checks from executable Rust tests and
  local results from cross-platform CI or hosted-site verification.
- Review `git diff --check`, the complete staged diff, file moves/deletions,
  generated output, and accidental legacy branding before committing.

## Delivery and reporting

Commit by logical change when commits are requested; preserve unrelated dirty
files. Push only when authorized. Never rewrite published history for
convenience. Report the behavior changed, the exact checks executed and their
outcomes, the remaining unverified surfaces, and the milestone status without
inflating it. Keep M5 marked in progress until its documented exit gate is met
across the full declared MIR surface and every listed backend.
