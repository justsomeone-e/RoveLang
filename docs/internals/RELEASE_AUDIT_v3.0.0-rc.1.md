# Rove v3.0.0-rc.1 Release Audit

Audit date: 2026-08-29

Decision: **NOT READY TO TAG**. The next eligible release remains
`v3.0.0-rc.1`; the repository is not eligible for `v3.0.0` stable.

## Verified evidence

| Check | Result | Evidence |
|---|---:|---|
| Unified compiler/toolchain suite | PASS | All suites and 138/138 regression cases passed locally |
| Typed HIR corpus | PASS | 162/162 battery and bughunt programs lower and verify |
| HIR optimizer | PASS | 162/162 idempotence and raw/optimized WASM equivalence |
| Bundle ABI v1 | PASS | UTF-8, bounds, ownership, separate instances, and 100k stress |
| Stdlib public API audit | PASS | 21/21 modules accepted through the compiler API |
| Backend capability contract | PASS | Target aliases, rejection paths, and three-host parity |
| Installer/scaffold portability | PASS | Isolated install and generated project contain no fixed user path |
| Diff whitespace validation | PASS | `git diff --check` reports no whitespace errors |
| HIR-authoritative stable trio | PASS | `cpp`, `js`, and `python` emit exclusively from verified HIR; 162-source and 138-runtime suites pass |
| Native self-host bootstrap | PASS | Stage 1 builds standalone stage 2; stage 2 emits byte-identical stage-3 C++ and compiles/runs a fixture |

The unified suite passed before the final portability cleanup. The installer,
capability, compiler API, hardware, HIR, LSP, and bundle suites relevant to the
subsequent changes were rerun successfully. A final unified run is still
required immediately before tagging.

## Blocking findings

| ID | Blocker | Required closure |
|---|---|---|
| RC1-02 | Stage-1 bootstrap is orchestrated by Python | Native stage 1 must accept/reject the release corpus |
| RC1-03 | Syntax and integer semantics are not frozen | Approve and publish v3 grammar and numeric RFCs |
| RC1-04 | Release CI verifies only Ubuntu | Require Windows, Linux, and macOS jobs |
| RC1-05 | Version/docs disagree (`v3`, stale `v4`, stale changelog/manifest) | Establish one version source and update release docs |
| RC1-06 | Archives lack checksums and supply-chain metadata | Produce checksums; define provenance/SBOM policy |
| RC1-07 | Current implementation is uncommitted | Review the final diff and create an approved release commit |

## Stable-only blockers

| ID | Blocker | Required closure |
|---|---|---|
| STABLE-02 | Native C++ is reproducible, but bootstrap HIR parity is not yet proven | Rove-authored lowering produces the same canonical HIR fingerprints as stage 0 |
| STABLE-03 | Normal installation requires Python | Distributed native compiler handles ordinary builds without Python |
| STABLE-04 | Compatibility policy is unpublished | Freeze HIR, compiler/plugin API, and Bundle ABI compatibility rules |
| STABLE-05 | No RC soak evidence | Close all release-blocking RC defects before stable |

## Tag authorization checklist

- [ ] RC1-02 through RC1-07 are closed (RC1-01 is closed).
- [ ] A clean checkout passes the unified suite on all required operating systems.
- [ ] Release archives install and execute from paths containing spaces and Unicode.
- [ ] Archive contents and version strings match the requested tag.
- [ ] Product Owner explicitly authorizes commit, push, tag, and release publication.

No commit, push, tag, or release action is authorized by this audit.
