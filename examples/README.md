# Rove Runnable Examples

This directory contains standalone, runnable examples demonstrating the syntax, type system, concurrency primitives, and multi-target compilation features of Rove.

## Index of Examples

| File | Primary Focus | Targets |
| :-- | :-- | :-- |
| [`01_math.rove`](01_math.rove) | Top-level scripting, arithmetic expressions, zero-ceremony execution | `cpp`, `js`, `python` |
| [`02_radar_dsp.rove`](02_radar_dsp.rove) | Typed variables, pipeline operator (`\|>`), formatted output | `cpp`, `js`, `python` |
| [`03_null_safety.rove`](03_null_safety.rove) | Optional types (`T?`), safe navigation (`?.`), null coalescing (`??`) | `cpp`, `js`, `python` |
| [`04_in_file_tests.rove`](04_in_file_tests.rove) | In-file test suites (`test "..." { assert(...) }`), native assertion checks | `cpp` |
| [`05_system_inspector.rove`](05_system_inspector.rove) | Standard library `std/system` inspection (OS, CPU threads, RAM) | `cpp` |
| [`06_memory_inspector.rove`](06_memory_inspector.rove) | `unsafe` blocks, raw pointers (`addr`), memory inspection (`peek`, `memdump`) | `cpp` |
| [`07_foreign_cpp.rove`](07_foreign_cpp.rove) | Foreign function interface to C++ standard library (`<filesystem>`) | `cpp` |
| [`08_foreign_node.rove`](08_foreign_node.rove) | Foreign function interface to Node.js modules (`node:os`) | `js` |
| [`09_foreign_python.rove`](09_foreign_python.rove) | Foreign function interface to Python standard modules (`platform`) | `python` |
| [`10_concurrent_tasks.rove`](10_concurrent_tasks.rove) | Asynchronous functions (`async fn`), `Task<T>`, `await`, `guard`, and `defer` | `cpp`, `js`, `python` |
| [`11_data_pipeline.rove`](11_data_pipeline.rove) | Domain structs, traits (`impl Trait for Struct`), pattern matching, stream pipelines | `cpp`, `js`, `python` |
| [`12_pong_game.rove`](12_pong_game.rove) | Interactive playable Pong game (Player vs CPU), physics, input, ASCII arena | `cpp`, `js`, `python` |
| [`file_inspector/`](file_inspector/) | Native CLI tool consuming `std/path`, `std/process`, and `std/str` | `cpp` |
| [`host_embedding/`](host_embedding/) | Shared transformer module embedded in Node.js (WASM ABI v1) and Python hosts | `wasm`, `python` |
| [`wasm_interactive/`](wasm_interactive/) | Browser interactive arithmetic engine powered by a compiled Rove WebAssembly core | `wasm` |
| [`package_consumer/`](package_consumer/) | Package dependency resolver (`rove.toml`, `rove.lock`) and C++ foreign binding consumer | `cpp` |
| [`web_pong/`](web_pong/) | Interactive playable Pong in the browser with `std/web` | `wasm` |
| [`web_site/`](web_site/) | Full interactive WebAssembly portal (Canvas 2D, 7 animation/game modes, 5 procedural music tracks, DJ launchpad, Pong 2.0, fireworks show, gravity vortex, byte inspector, benchmarks) | `wasm` |

## How to Run

Execute any example with your target backend of choice:

```bash
# Run with the native C++20 backend (default)
rove run examples/10_concurrent_tasks.rove --target cpp

# Run with the Node.js backend
rove run examples/10_concurrent_tasks.rove --target js

# Run with the Python reference backend
rove run examples/10_concurrent_tasks.rove --target python

# Or check syntax and type validity only:
rove check examples/11_data_pipeline.rove
```
