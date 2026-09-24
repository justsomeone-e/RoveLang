# Rove v4.0.0-rc.1 Local Candidate Audit

Date: 2026-09-02
Current version: `4.0.0-rc.1`
Release tag: `v4.0.0-rc.1`

## Decision

The reviewed Windows candidate passes the complete unified framework, including
the compiler, typed HIR, backends, bundle, self-host, installer, VS Code/LSP,
interop, fuzz, and 138-point regression gates. Product Owner approval promotes
this commit to RC1. The tagged GitHub workflow remains authoritative for the
Linux verification job, four native platform artifacts, checksums, SBOM, and
provenance.

## Verified local evidence

| Gate | Result | Evidence |
| :-- | :--: | :-- |
| Unified framework | PASS | Complete local framework finished with `ALL TEST SUITES PASSED` |
| Regression battery | PASS | 138/138, zero failures |
| Native self-host | PASS | Rove-authored frontend, native stage 2, and byte-identical stage-3 C++ |
| Typed HIR | PASS | 162 programs, 17 stdlib modules, 194-case Rove/Python HIR byte parity |
| `cpp` HIR runtime | PASS | 162 emitted and 138 native runtime cases |
| `js` HIR runtime | PASS | 162 executed, 138 runtime cases, 10 deterministic fixtures |
| `python` HIR runtime | PASS | 162 compiled, 138 runtime cases, 10 deterministic fixtures |
| `rust` HIR emission | PASS | 159 supported corpus programs passed Rust 2021 metadata/borrow checking; exception, spawn, and channel fixtures rejected with E3001; 8/8 focused Rust cases |
| Language surface | PASS | 44 keywords, exact editor parity, traits, Task, exception, i64, and strict-bool contracts |
| Numeric semantics | PASS | Signed i64, IEEE binary64, and canonical scalar text on three stable backends |
| Bundle ABI v1 | PASS | Typed lowering, UTF-8, isolated instances, and 100,000-allocation stress |
| Capability model | PASS | Target aliases, target rejection, stdlib gates, and six-module parity |
| LSP | PASS | Completion, hover, definition, and CLI JSON-RPC framing: 4/4 |
| Native interoperability | PASS | C callback declarators, RAII, Result bridge, and generic Result context: 5/5 |
| Compiler robustness | PASS | 530 fuzz cases, zero unhandled crashes; 10/10 structured negative cases |
| Release archives | PASS | Byte-reproducible ZIP/TAR, canonical paths, modes, owners, and timestamps |
| Native-first installers | PASS | Exact native version signature, portable runtime allowlist, installed-wrapper LSP smoke, and Python fallback |
| Version contract | PASS | `VERSION`, CLI, native compiler, VS Code, README, and preserved animations agree |
| VS Code package | PASS | Contract test, VSIX packaging, local force install, canonical CLI resolution, persistent terminal commands, and project links |
| CLI toolchain behavior | PASS | Formatter idempotence and source preservation; real profile execution; honest source inspection; doc output; manifest/lock add/remove/install/pkg effects; negative exit codes |
| README | PASS | Language example parses/type-checks/lowers/verifies; local links and image assets resolve |

## Release engineering state

The release workflow defines four native platform artifacts, deterministic
source archives, the local-install VSIX, SHA-256 manifests, an SPDX 2.3 SBOM,
and signed provenance/SBOM attestations. The local contract verifies the
workflow and package layout; hosted attestations are evidence only after the
tagged workflow itself completes.

## Findings closed during this audit

- Canonical Boolean output fixtures now compare lowercase `true`/`false` on
  all three HIR-authoritative backends.
- C FFI callback parameters emit valid function-pointer declarators.
- Contextual `Result<T, E>` construction and Rove i64 literals preserve their
  exact host-language types.
- Native HIR type parsing trims generic component whitespace deterministically.
- The Rust 2021 backend now emits exclusively from canonical typed HIR; its
  beta contract passed the supported corpus and keeps Task, exception, spawn,
  and channel behavior as explicit capability rejections rather than approximations.
- Installers no longer copy VS Code development `node_modules` into the Rove
  runtime payload.
- Installers reject stale native executables that exit successfully without the
  exact `rovec <version> (native self-host)` signature, and the installed wrapper
  now passes an LSP initialize/shutdown protocol smoke test.
- The VS Code extension now runs native executables in a persistent terminal,
  diagnoses missing C++20 toolchains, prefers the canonical Rove installation,
  exposes repository/documentation/release/roadmap/issue links, and ships as a
  local VSIX.
- CLI quality/package commands no longer report success on missing files;
  profiling executes the selected backend, debug mode no longer fabricates
  runtime state, and manifest/lock mutations have a dedicated regression suite.
- README architecture and release claims now match the typed-HIR and native
  self-host implementation without removing the animated assets.

## Tagged workflow evidence

- [x] Canonical `cpp/js/python/rust/wasm/react/asm` target IDs and removal of the
      retired microcontroller surface.
- [x] Complete local unified regression framework.
- [x] Single version source and generated package surfaces set to
      `4.0.0-rc.1`.
- [x] Product Owner approval for the RC1 tag.
- [ ] Hosted Linux verification and four-platform native artifact matrix.
- [ ] Published checksums, SPDX SBOM, provenance, source archives, and VSIX.

## Stable blockers after RC1

- [ ] Complete the RC soak without an unresolved release-blocking defect.
- [ ] Publish HIR, compiler API, plugin API, Bundle ABI, and lockfile
      compatibility policies.
- [ ] Test and publish the rollback procedure.
- [ ] Re-run all eight gates for every backend advertised as stable.
