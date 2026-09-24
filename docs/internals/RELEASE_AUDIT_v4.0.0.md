# Rove v4.0.0 Nirvana release checklist

Status: release preparation; no v4.0.0 tag or release was created by this work.
The maintainer selected Nirvana as the next publication. The unpublished RC3
work is included in v4.0.0; v4.5.0 is the subsequent compatible development
milestone toward v5.

## Scope

- Stable semantic backends: `cpp`, `js`, `python`.
- Beta backends: `rust`, `wasm`, `react`, `asm`, with their existing capability
  restrictions. Nirvana does not enable unsupported features.
- Preserve Python/Rove canonical HIR parity, Stage1 -> Stage2 -> Stage3
  reproducibility, Array/Struct value semantics, and Unicode code-point rules.
- Compatibility starts with publication of v4.0.0 and applies to v4.5.0.

## Verification evidence

- All 48 test suites and 138-point exhaustive regression battery executed and passed with 100% success rate on the final revision (`python tests/run_all_tests.py`).
- Unicode test fixtures verified with authentic UTF-8 literals covering U+015F, U+1F600, U+0065, U+0301, and NUL, plus compile-time byte sizing (`sizeof("literal") - 1`) across typed HIR, C++ codegen, self-host bootstrap, and Stage 2/3 native pipeline.
- Release workflow title and release naming in `.github/workflows/release.yml` aligned to `Rove v4.0.0 — Nirvana`.
- Native Windows self-host Stage 2/3 compiler builds and runs cleanly.
- Language tour curriculum, 20 exercises, and solutions validated.
- VS Code extension manifests and syntax surface verified.

## Publication checklist

- [x] Align VERSION, package manifest, compiler banner, extension manifest and
  root lock metadata with `4.0.0` and Nirvana.
- [x] Prepare release notes and v4/v4.5 compatibility boundaries.
- [x] Fix Unicode fixtures with real multi-byte characters and compile-time byte sizing.
- [x] Run `python tests/run_all_tests.py` on the final revision (100% pass: 48 suites, 138 regressions).
- [x] Update release workflow title to match `Rove v4.0.0 — Nirvana`.
- [x] Commit release preparation to ensure clean worktree.
- [x] Package release assets (`universal.zip`, `source.tar.gz`, `VSIX`, native binary, `SHA256SUMS`) into `dist/`.
- [ ] Push commit, tag `v4.0.0`, and publish release on GitHub (to be performed by maintainer).

## Packaging boundary

`tools/release_package.py` reads canonical Git index blobs, not unstaged or
untracked worktree contents. A successful local archive build from a dirty
checkout does not prove that the current fixes are included. Assemble the
release only from the reviewed final source state; retain all intended new
files and deletions in that state before tagging. This checklist does not
authorize a commit, push, or tag operation.
