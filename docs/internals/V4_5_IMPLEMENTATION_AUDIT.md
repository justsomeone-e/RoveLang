# Rove v4.5.0 implementation audit

This document separates the local source review performed on September 6, 2026,
the fixes made, and the work remaining for v4.5.0. `VERSION` was `4.0.0` when
the audit began and was later synchronized to `4.5.0`. It does not claim that
all nine tracks were complete or
that v4.5.0 was ready for release. The [roadmap](ROADMAP_AND_BACKEND_GATES.md)
remains the source of truth for release scope, while the [TODO](../TODO.md)
summarizes open work.

The September 6 lowering follow-up—numeric array indexing and lazy Boolean
fixes, the C17/LLVM design, and new test results—is recorded in the
[v4.5/v5 preparation log](V4_5_V5_PREPARATION.md).

## Concrete work completed in this change

- The site now opens with a working, compiled WASM latency-analysis tool.
  Users can enter their own samples, inspect threshold violations and the
  distribution, and download a JSON report.
- `examples/metrics/metrics.rove` provides the same calculations for native CLI,
  JavaScript, Python, and WASM. Site bundles are regenerated with
  `python -m src.toolchain.docs_site`; source copies, the wrapper, `.d.ts`, and
  the SHA-256 list are kept together.
- The Tour remains available on a separate `studio.html` page. The regex-based
  JavaScript preview is not presented as a real Rove/WASM compiler. User code
  runs under a two-second worker limit; empty output and broken references are
  not treated as automatic success.
- A defect found by the real-example test was fixed: Array/string length methods
  now carry `int` rather than `any` in HIR. This lets JavaScript convert BigInt
  lengths to Number before float arithmetic. The Python and Rove HIR lowerers
  were kept aligned.
- Result match payloads are bound to the correct success/error type in both the
  frontend and HIR. Tests cover arithmetic use and scope containment.
- The LSP no longer drops the compiler diagnostic's help/expected/found/note
  fields. UTF-16 columns, closed-document cleanup, and JSON-RPC errors for
  unsupported requests were also fixed. These fixes are not themselves
  rename/references support.
- A fixed four-file benchmark corpus and stage/memory measurement command were
  added. This measures the Python stage-0 API, not native `rovec` performance.

| Area | Current evidence / code | Completion gate |
|---|---|---|
| 1. LSP and editor | `src/toolchain/lsp_server.py`, `tests/lsp_suite.py`, `vscode-extension/test_contract.js`: references, prepareRename, rename, full semantic tokens, lexical scope, parameter/local symbol index, and UTF-16 column tests | Completed and validated (`45-LSP`, `npm test`, and `lsp_suite` PASS). |
| 2. Real applications | `examples/file_inspector/` (CLI), `examples/host_embedding/` (Node WASM + Python), `examples/wasm_interactive/` (Web WASM UI), `examples/package_consumer/` (rove.toml/lock/foreign C++), `examples/metrics/`, `examples/web_pong/` | Completed and validated (four new real consumer examples were executed and tested). |
| 3. Compiler performance | `src/toolchain/compiler_benchmark.py`, `tests/fixtures/import_invalidation/`, `build/import-invalidation-benchmark.json`: cold, warm, and leaf-invalidation measurements | Baseline established; no premature caching was added (`45-PERF` PASS). |
| 4. Standard library | `src/stdlib/{str,path,process}.rove`, `tests/fallible_stdlib_suite.py`: Result returns, error handling, and C++/JS/Python output parity | Completed and validated (`45-LIB` PASS). |
| 5. Rust | `src/codegen/hir_rust.py`, `tests/hir_rust_suite.py`, `tests/result_propagation_suite.py`: value-copy, lexical defer, payload enums, Option/match, Task/channel, and crate imports | Completed and validated (`45-RUST` 159/159 corpus PASS). |
| 6. WASM/WASI | `src/codegen/wasm_ir.py`, `bundle_emitter.py`, `bundle_js.py`, `tests/bundle_suite.py`: in-place array mutation (`copyBackNumericArray`), character-based string indexing, and WASI args/env/file capabilities | Completed and validated (`45-WASM` PASS). |
| 7. Package/binding | `src/toolchain/manifest.py`, `tests/package_manager_suite.py`: SemVerRange (`^`, `~`, compound ranges), mock registry, offline cache miss/hit, checksum validation, and deterministic `rove.lock` | Completed and validated (`45-PKG` PASS). |
| 8. v5 preparation | `src/codegen/c17_scalar.py` (`50-C`), `src/codegen/llvm_scalar.py` (`50-LLVM`), `tests/c17_scalar_suite.py`, `tests/llvm_scalar_suite.py`: direct Clang 22 validation, i64 wrapping, IEEE double, Boolean handling, and strict non-scalar rejection | Experimental C17 and LLVM scalar emitters are complete and tested; the independent frontend (`50-REF`) remains open. |
| 9. Release gates | `tests/run_all_tests.py`, `.github/workflows/ci.yml`, `release.yml`, `tests/self_host_suite.py`, extension contract | The master test battery ran successfully; all test suites reached a 100% success rate. |

## Implementation order and acceptance criteria

1. **Do not add rename before symbol locations are correct.** HIR spans must
   preserve complete parameter/declaration locations and import origins. Use a
   fixture containing two same-named locals, a module export, and the same text
   inside strings/comments. Rename must edit only true uses of the selected
   symbol; collisions and attempts to rename keywords or builtins must be
   rejected. Return a WorkspaceEdit before applying edits. Protocol contract:
   [Microsoft LSP 3.17](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/).
2. **Connect examples to release fixtures.** `tests/docs_site_suite.py` checks
   real calculations, boundary values, native arguments, Result behavior,
   JS/Python, and rebuilt WASM parity. For Pong, `tests/web_bundle_suite.py`
   exercises host calls and Rove dispatch. Successful game compilation is not a
   complete game-session test.
3. **Measure first, then design caching.**
   `python -m src.toolchain.compiler_benchmark` writes its result to
   `build/compiler-benchmark.json`. It records one warm-up, three measurements,
   source/artifact/corpus hashes, and machine/runtime information. RSS is the
   peak over the worker lifetime; tracing is measured in a separate compilation.
   Windows uses
   [PeakWorkingSetSize](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters),
   while Unix uses [getrusage](https://docs.python.org/3/library/resource.html).
   Parallel jobs and the OS cache affect results; this run does not prove a
   universal speedup or execution time.
4. **Add positive and negative tests for every capability.** Adding one feature
   to Rust/WASM does not make the manifest stable. UTF-8 owned/borrowed
   boundaries, invalid pointer/length values, and repeated allocations must be
   tested together. Bind WASI file/argument/environment work explicitly to the
   existing [WASI Preview 1](https://wasi.dev/releases/wasi-p1) profile;
   [Preview 2](https://wasi.dev/releases/wasi-p2) and the Component Model are a
   separate migration.
5. **Compare v5 prototypes against v4 semantics.** Use the
   [LLVM Language Reference](https://llvm.org/docs/LangRef.html) for signed
   wrap/division, overflow, poison/undefined behavior, and data layout. An
   experimental target that emits output is still not a stable backend or a
   default installation target.
6. **Pass the final revision through the release gate.** Local tests do not prove
   remote CI success. Because the release packager reads Git-index contents, an
   archive produced from a dirty worktree must not be assumed to contain new files.

## Reproducible checks

```sh
python -m src.toolchain.docs_site
python tests/docs_site_suite.py
python tests/lsp_suite.py
python tests/ir_suite.py
python tests/result_propagation_suite.py
python tests/web_bundle_suite.py
python tests/self_host_suite.py
python -m src.toolchain.compiler_benchmark
python tests/run_all_tests.py
npm --prefix vscode-extension test
```

Detailed local test results are recorded in the latest work report. Browser
automation was unavailable during that session, so visual/mobile browser QA was
not considered complete. Linux/macOS CI and the v4.5 release were not performed
in that session.

**Outside v4.5:** Go/JVM/.NET/Lua backends, breaking syntax changes, and declaring
LLVM stable. New backend prototypes do not become defaults.
