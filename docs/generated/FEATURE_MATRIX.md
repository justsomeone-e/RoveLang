# Rove compiler feature matrix

<!-- Generated from compiler/features.toml; do not edit by hand. -->

- Registry schema: `1`
- Language version: `5.0.3`
- Typed HIR schema: `1`
- Bundle ABI: `1`

## Frozen inventory

- 44 stable keywords
- 52 AST node kinds
- 47 Typed HIR node kinds
- 141 diagnostic codes
- 18 builtins and 73 intrinsics

## Backends

| Backend | Maturity | Family | Artifact | Features |
| --- | --- | --- | --- | ---: |
| `asm` | beta | native | assembly | 16 |
| `c` | experimental | native | c | 7 |
| `cpp` | stable | native | executable/library | 26 |
| `js` | stable | hosted | javascript | 26 |
| `llvm` | experimental | native | ll | 10 |
| `python` | stable | hosted | python | 26 |
| `react` | beta | web | tsx | 4 |
| `rust` | beta | native | rust | 11 |
| `wasm` | beta | web | wat/wasm | 16 |

## Compiler pipeline

| Stage | Status | Authority | Evidence |
| --- | --- | --- | --- |
| `lexer` | stable | `src/core/lexer.py` | `tests/bootstrap_lexer_test.py`<br>`tests/language_surface_suite.py` |
| `parser` | stable | `src/core/parser.py` | `tests/bootstrap_parser_test.py`<br>`tests/bootstrap_parser_corpus_test.py` |
| `module_graph` | experimental | `src/core/identities.py` | `tests/module_resolution_suite.py` |
| `type_checker` | stable | `src/core/type_checker.py` | `tests/bootstrap_typechecker_test.py`<br>`tests/negative_tests.py` |
| `typed_hir` | stable | `src/ir/model.py` | `tests/ir_suite.py` |
| `generic_instances` | experimental | `src/ir/instances.py` | `tests/ir_instances_suite.py` |
| `static_dispatch` | experimental | `src/ir/dispatch.py` | `tests/mir_dispatch_suite.py` |
| `hir_verifier` | stable | `src/ir/verifier.py` | `tests/ir_suite.py` |
| `runtime` | stable | `src/runtime` | `tests/numeric_semantics_suite.py`<br>`tests/cpp_e2e_suite.py`<br>`tests/js_e2e_suite.py` |
| `backends` | stable | `src/core/backend_capabilities.py` | `tests/capability_suite.py` |
| `mir` | experimental | `src/mir/model.py` | `tests/mir_suite.py`<br>`tests/mir_lowering_suite.py`<br>`tests/mir_cleanup_suite.py`<br>`tests/mir_memory_abi_suite.py`<br>`tests/mir_coroutine_suite.py` |
| `mir_legalization` | experimental | `src/mir/legalization.py` | `tests/mir_legalization_suite.py` |

## Feature contracts

| Feature | Maturity | Semantics | Backends | Evidence |
| --- | --- | --- | --- | --- |
| `array_iteration` | experimental | defined | `llvm` | `tests/llvm_scalar_suite.py` |
| `array_mutation` | beta | defined; failure: trapped | `wasm` | `tests/bundle_suite.py` |
| `arrays` | stable | defined | `asm`, `cpp`, `js`, `python`, `rust` | `tests/language_surface_suite.py` |
| `async_tasks` | stable | defined | `cpp`, `js`, `python` | `tests/language_surface_suite.py` |
| `canonical_scalar_text` | stable | defined | `c`, `cpp`, `js`, `llvm`, `python` | `tests/numeric_semantics_suite.py` |
| `channels` | stable | defined | `asm`, `cpp`, `js`, `python` | `tests/capability_suite.py` |
| `collection_combinators` | stable | defined | `cpp`, `js`, `python` | `tests/collection_api_suite.py` |
| `components` | beta | defined | `react` | `tests/test_react_target.py` |
| `control_flow` | stable | defined | `asm`, `c`, `cpp`, `js`, `llvm`, `python`, `rust`, `wasm` | `tests/language_surface_suite.py` |
| `encoding` | stable | defined | `js`, `python` | `tests/capability_suite.py` |
| `exceptions` | stable | defined | `cpp`, `js`, `python` | `tests/language_surface_suite.py` |
| `filesystem` | stable | defined | `asm`, `cpp`, `js`, `python` | `tests/fallible_stdlib_suite.py` |
| `float64_ieee` | stable | defined | `c`, `cpp`, `js`, `llvm`, `python` | `tests/numeric_semantics_suite.py` |
| `functions` | stable | defined | `asm`, `c`, `cpp`, `js`, `llvm`, `python`, `rust`, `wasm` | `tests/ir_suite.py` |
| `hash` | stable | defined | `js`, `python` | `tests/capability_suite.py` |
| `host_imports_v1` | beta | defined | `wasm` | `tests/web_bundle_suite.py` |
| `int64_wrap` | stable | defined | `c`, `cpp`, `js`, `llvm`, `python` | `tests/numeric_semantics_suite.py` |
| `iterator_yield` | stable | defined | `cpp`, `js`, `python` | `tests/language_surface_suite.py` |
| `json_lite` | stable | defined | `js`, `python` | `tests/capability_suite.py` |
| `math` | stable | defined | `js`, `python` | `tests/capability_suite.py` |
| `native_ffi` | stable | unsafe-only | `asm`, `cpp` | `tests/ffi_suite.py` |
| `native_linking` | stable | defined | `asm`, `cpp` | `tests/linking_suite.py` |
| `numeric` | beta | defined | `wasm` | `tests/bundle_suite.py` |
| `numeric_array_abi` | beta | defined; failure: trapped | `wasm` | `tests/bundle_suite.py` |
| `optionals` | stable | defined | `asm`, `cpp`, `js`, `python`, `rust` | `tests/hir_cpp_suite.py` |
| `pattern_match` | stable | defined | `asm`, `cpp`, `js`, `python`, `rust` | `tests/language_surface_suite.py` |
| `payload_enums` | stable | defined | `cpp`, `js`, `python` | `tests/payload_enum_suite.py` |
| `react19` | beta | defined | `react` | `tests/test_react_target.py` |
| `result_propagation` | stable | defined | `cpp`, `js`, `python`, `rust` | `tests/result_propagation_suite.py` |
| `scalar_arrays` | experimental | defined | `llvm` | `tests/llvm_scalar_suite.py` |
| `scalar_c17` | experimental | defined | `c` | `tests/c17_scalar_suite.py` |
| `scalar_llvm` | experimental | defined | `llvm` | `tests/llvm_scalar_suite.py` |
| `scalar_structs` | experimental | defined | `llvm` | `tests/llvm_scalar_suite.py` |
| `sockets` | stable | defined | `asm`, `cpp` | `tests/fallible_stdlib_suite.py` |
| `spawn` | stable | defined | `asm`, `cpp`, `js`, `python` | `tests/capability_suite.py` |
| `string_abi` | beta | defined; failure: trapped | `wasm` | `tests/bundle_suite.py` |
| `string_indexing` | beta | defined | `wasm` | `tests/bundle_suite.py` |
| `strings` | stable | defined | `asm`, `cpp`, `js`, `python`, `rust` | `tests/language_surface_suite.py` |
| `structs` | stable | defined | `asm`, `cpp`, `js`, `python`, `rust` | `tests/ir_suite.py` |
| `threads` | stable | defined | `asm`, `cpp` | `tests/platform_suite.py` |
| `time` | stable | defined | `js`, `python` | `tests/capability_suite.py` |
| `tsx` | beta | defined | `react` | `tests/test_react_target.py` |
| `typed_hir_v1` | stable | defined | `c`, `cpp`, `js`, `llvm`, `python`, `rust`, `wasm` | `tests/ir_suite.py` |
| `unicode` | stable | defined | `asm`, `cpp`, `js`, `python`, `react`, `rust`, `wasm` | `tests/language_surface_suite.py` |
| `unsafe_memory` | stable | unsafe-only | `asm`, `cpp`, `rust` | `tests/cpp_e2e_suite.py` |
| `wasi_args` | beta | defined | `wasm` | `tests/bundle_suite.py` |
| `wasi_environ` | beta | defined | `wasm` | `tests/bundle_suite.py` |
| `wasi_filesystem` | beta | defined | `wasm` | `tests/bundle_suite.py` |
| `wasi_preview1` | beta | defined | `wasm` | `tests/bundle_suite.py` |
| `wasm32` | beta | defined | `wasm` | `tests/bundle_suite.py` |
| `web_dom` | beta | defined | `wasm` | `tests/web_bundle_suite.py` |

## Per-feature pipeline status

| Feature | Parser | Checker | HIR | Runtime | Backend |
| --- | --- | --- | --- | --- | --- |
| `array_iteration` | implemented | implemented | implemented | partial | experimental |
| `array_mutation` | not-applicable | partial | partial | implemented | implemented |
| `arrays` | implemented | implemented | implemented | implemented | implemented |
| `async_tasks` | implemented | implemented | implemented | implemented | implemented |
| `canonical_scalar_text` | not-applicable | not-applicable | implemented | implemented | implemented |
| `channels` | implemented | implemented | implemented | implemented | implemented |
| `collection_combinators` | implemented | implemented | implemented | implemented | implemented |
| `components` | implemented | implemented | not-applicable | external | implemented |
| `control_flow` | implemented | implemented | implemented | implemented | implemented |
| `encoding` | not-applicable | not-applicable | implemented | implemented | implemented |
| `exceptions` | implemented | implemented | implemented | implemented | implemented |
| `filesystem` | not-applicable | not-applicable | implemented | implemented | implemented |
| `float64_ieee` | not-applicable | not-applicable | implemented | implemented | implemented |
| `functions` | implemented | implemented | implemented | implemented | implemented |
| `hash` | not-applicable | not-applicable | implemented | implemented | implemented |
| `host_imports_v1` | not-applicable | partial | partial | implemented | implemented |
| `int64_wrap` | not-applicable | not-applicable | implemented | implemented | implemented |
| `iterator_yield` | implemented | implemented | implemented | implemented | implemented |
| `json_lite` | not-applicable | not-applicable | implemented | implemented | implemented |
| `math` | not-applicable | not-applicable | implemented | implemented | implemented |
| `native_ffi` | not-applicable | not-applicable | implemented | implemented | implemented |
| `native_linking` | not-applicable | not-applicable | implemented | implemented | implemented |
| `numeric` | not-applicable | partial | partial | implemented | implemented |
| `numeric_array_abi` | not-applicable | partial | partial | implemented | implemented |
| `optionals` | implemented | implemented | implemented | implemented | implemented |
| `pattern_match` | implemented | implemented | implemented | implemented | implemented |
| `payload_enums` | implemented | implemented | implemented | implemented | implemented |
| `react19` | implemented | implemented | not-applicable | external | implemented |
| `result_propagation` | implemented | implemented | implemented | implemented | implemented |
| `scalar_arrays` | implemented | implemented | implemented | partial | experimental |
| `scalar_c17` | implemented | implemented | implemented | partial | experimental |
| `scalar_llvm` | implemented | implemented | implemented | partial | experimental |
| `scalar_structs` | implemented | implemented | implemented | partial | experimental |
| `sockets` | not-applicable | not-applicable | implemented | implemented | implemented |
| `spawn` | implemented | implemented | implemented | implemented | implemented |
| `string_abi` | not-applicable | partial | partial | implemented | implemented |
| `string_indexing` | not-applicable | partial | partial | implemented | implemented |
| `strings` | implemented | implemented | implemented | implemented | implemented |
| `structs` | implemented | implemented | implemented | implemented | implemented |
| `threads` | not-applicable | not-applicable | implemented | implemented | implemented |
| `time` | not-applicable | not-applicable | implemented | implemented | implemented |
| `tsx` | implemented | implemented | not-applicable | external | implemented |
| `typed_hir_v1` | not-applicable | implemented | implemented | not-applicable | implemented |
| `unicode` | implemented | implemented | implemented | implemented | implemented |
| `unsafe_memory` | implemented | implemented | implemented | implemented | implemented |
| `wasi_args` | not-applicable | partial | partial | implemented | implemented |
| `wasi_environ` | not-applicable | partial | partial | implemented | implemented |
| `wasi_filesystem` | not-applicable | partial | partial | implemented | implemented |
| `wasi_preview1` | not-applicable | partial | partial | implemented | implemented |
| `wasm32` | not-applicable | partial | partial | implemented | implemented |
| `web_dom` | not-applicable | partial | partial | implemented | implemented |

## Standard library contracts

| Module | Maturity | Targets |
| --- | --- | --- |
| `std/encoding` | stable | `asm`, `cpp`, `js`, `python` |
| `std/env` | stable | `asm`, `cpp` |
| `std/fs` | stable | `asm`, `cpp`, `js`, `python` |
| `std/hash` | stable | `asm`, `cpp`, `js`, `python` |
| `std/http` | experimental | `cpp` |
| `std/io` | stable | `asm`, `cpp`, `python` |
| `std/json` | deprecated | `asm`, `cpp`, `js`, `python` |
| `std/json_lite` | stable | `asm`, `cpp`, `js`, `python` |
| `std/math` | stable | `asm`, `cpp`, `js`, `python` |
| `std/memory` | stable | `asm`, `cpp` |
| `std/net` | stable | `asm`, `cpp` |
| `std/os` | stable | `asm`, `cpp` |
| `std/path` | stable | `asm`, `cpp`, `js`, `python` |
| `std/platform` | stable | `asm`, `cpp` |
| `std/process` | stable | `asm`, `cpp`, `js`, `python` |
| `std/str` | stable | `asm`, `cpp`, `js`, `python`, `rust` |
| `std/system` | experimental | `asm`, `cpp` |
| `std/terminal` | experimental | `asm`, `cpp` |
| `std/thread` | stable | `asm`, `cpp` |
| `std/time` | stable | `asm`, `cpp`, `js`, `python` |
| `std/web` | experimental | `wasm` |
