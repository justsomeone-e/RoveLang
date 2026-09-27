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

## Review every change with borrow-checker-level rigor

"Borrow checker" describes the thoroughness of the engineering review, not a
request to implement Rust ownership rules in Rove. Apply this loop to compiler
code, tooling, docs, editor behavior, and UI alike:

1. Before editing, record the observed behavior and a small baseline check.
   List the invariant to preserve and the callers, generated artifacts, and
   supported targets that could be affected. If a bug is reproducible, capture
   a case that fails before the fix.
2. After each meaningful edit, inspect the changed code and its neighboring
   paths. Check success, failure, boundary, and compatibility cases. Trace
   control flow and state rather than assuming that a passing happy path is
   enough. If an assumption is unproven, inspect source or run a probe.
3. Verify through at least two relevant forms of evidence for behavioral work:
   a focused test plus an actual compiler/runtime execution, an independent
   oracle, a related integration suite, or rendered UI inspection. Choose
   checks that can catch different defects; repeating the identical command
   without a change or new hypothesis adds little confidence.
4. After the **last** code edit, rerun the affected checks. Then inspect the
   complete diff, staged files, names, generated output, and unrelated dirty
   state. If a check fails, determine whether the change caused it, fix the
   cause, and rerun the relevant check. Never report stale green results.
5. Before claiming completion, compare the outcome with every explicit user
   requirement and the applicable milestone exit gate. State what was executed,
   what was only reviewed, and what remains unverified. Do not silently reduce
   the requested scope to the portion that passed.

For ownership-affecting compiler changes, additionally trace construction,
copy, move, borrow, projection, overwrite, return, and destruction across every
relevant normal, throw, and suspend edge. Check initialization before use,
alias isolation, and exactly-once cleanup. If the model cannot prove a case,
keep it behind a verifier or capability gate instead of assuming it is safe.

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
