---
title: Compiling a Systems Language Directly to LLVM IR Without C++ Hops: The Nyx Architecture
published: true
tags: compilers, llvm, webassembly, programming
canonical_url: https://github.com/justsomeone-e/nyx
cover_image: https://raw.githubusercontent.com/justsomeone-e/nyx/main/docs/assets/terminal_animated.svg
---

When building a new programming language, transpiling to C++ is the most tempting first shortcut. You inherit an optimizing compiler, an existing runtime, and portable platform targets.

Nyx started with that approach. But as our target matrix grew to include **WebAssembly (WASM ABI v1), Node.js, Python, and native binaries**, we ran headfirst into a fundamental problem that haunts multi-target compilers: **Semantic Drift**.

Here is how we solved it with a canonical **Typed HIR v1**, and how our newest release candidate (**v5.0.0-rc.1 "Daydream"**) bypasses the C++ intermediate entirely to emit native LLVM IR directly.

---

### The Problem: When AST Lowering Betrays You

In typical hobbyist and early-stage compilers, the frontend Abstract Syntax Tree (AST) lowers directly into whatever backend is active:

```text
               ┌─> C++ Backend  --> clang++
Nyx AST (v3) ──┼─> JS Backend   --> node
               └─> WASM Backend --> wat2wasm
```

This works until subtle language semantics diverge:
1. **Integer Overflow:** In C++, signed integer overflow is Undefined Behavior (UB). In JavaScript, numbers are double-precision IEEE floats (unless using BigInt). In WebAssembly, `i32`/`i64` wraps around deterministically.
2. **Value vs Reference:** Passing a struct to a function in C++ might copy by value, while in JavaScript an object is passed by reference.
3. **Control Flow Defer:** When a function returns early through a `Result<T, E>` check (`?` operator), does every backend run lexical defer cleanup in the exact same order?

Without a shared intermediate representation, you end up writing ad-hoc workarounds inside each backend generator.

---

### The Fix: Typed HIR v1 as the Single Source of Truth

To guarantee identical behavior across platforms, we redesigned Nyx around **Typed HIR v1** (Hierarchical Intermediate Representation):

```text
Nyx Source
   │
   ▼
Parser & Semantic Analyzer (Type Inference & Symbol Resolution)
   │
   ▼
Canonical Typed HIR v1 (Strict Type Annotations & CFG Blocks)
   ├──> C++20 (Production Stable)
   ├──> WebAssembly (WASM ABI v1 / Browser Studio)
   ├──> JavaScript ES2022 & Python 3
   └──> LLVM IR (Direct Native Pipeline)
```

By enforcing that **no backend may consume the raw AST**, Typed HIR becomes the semantic arbiter:
* Control flow is structured into explicit Basic Blocks with single terminators.
* Type annotations are fully resolved; all implicit conversions are made explicit.
* Bounds checks and panic abort paths are lowered before emission.

---

### Bypassing C++: Direct LLVM IR Emission

With `v5.0.0-rc.1`, we introduced a direct textual LLVM IR emitter (`src/codegen/llvm_scalar.py`). Instead of invoking `clang++` on an intermediate `.cpp` file, Nyx generates standard `.ll` assembly text:

```bash
nyx build -t llvm app.nyx --output build/
```

This produces `build/llvm/app.ll`, which is fed straight to the host `clang` driver to produce an optimized native executable.

#### 1. Preventing Poison & UB in Signed Arithmetic
In LLVM IR, the `add nsw` instruction treats signed overflow as poison. If the optimizer detects overflow, it can legally discard bounds checks or miscompile loops.

In Nyx, integers have guaranteed 64-bit wrapping semantics:
```llvm
; Safe signed addition without poison:
%res = add i64 %a, %b
```

For division, zero-division and `INT64_MIN / -1` (which triggers hardware `SIGFPE` on x86_64) are guarded before emission:
```llvm
%is_zero = icmp eq i64 %b, 0
br i1 %is_zero, label %div_abort, label %div_check_overflow

div_check_overflow:
%is_min = icmp eq i64 %a, -9223372036854775808
%is_neg_one = icmp eq i64 %b, -1
%is_overflow = and i1 %is_min, %is_neg_one
br i1 %is_overflow, label %div_overflow_wrap, label %div_safe
```

#### 2. Value-Semantic Aggregates & Stack Arrays
In systems programming, stack allocation beats heap churn every time. In Nyx v5, structs and fixed-size arrays are stack-owned and value-copied across call boundaries:

```nyx
struct Point {
    x: int,
    y: int
}

fn offset(p: Point) -> int {
    return p.x + p.y
}
```

This lowers to typed `alloca` memory slots with explicit `llvm.memcpy` calls on assignment:
```llvm
%struct.Point = type { i64, i64 }

define i64 @offset(%struct.Point* byval(%struct.Point) align 8 %p) {
    ; Direct GEP access with zero runtime overhead
    %field_x = getelementptr inbounds %struct.Point, %struct.Point* %p, i32 0, i32 0
    %val_x = load i64, i64* %field_x, align 8
    ...
}
```

---

### Reproducibility: The 3-Stage Bootstrap Gate

One of our strictest release requirements is **byte-identical self-hosting**:
* **Stage 1:** Python stage-0 compiler compiles `compiler/main.nyx` to a native binary (`nyxc_stage1`).
* **Stage 2:** `nyxc_stage1` compiles `compiler/main.nyx` to produce `nyxc_stage2`.
* **Stage 3:** `nyxc_stage2` compiles `compiler/main.nyx` to produce `nyxc_stage3`.

If `SHA256(nyxc_stage2) != SHA256(nyxc_stage3)`, the build is rejected immediately. Determinism is non-negotiable.

---

### Try It Yourself

Nyx is free, open source, and available under the Apache 2.0 license:

* **Interactive Browser Playground & Tour:** [justsomeone-e.github.io/nyx](https://justsomeone-e.github.io/nyx/)
* **GitHub Repository:** [github.com/justsomeone-e/nyx](https://github.com/justsomeone-e/nyx)
* **Quick Install (Linux/macOS):**
  ```bash
  curl -fsSL https://raw.githubusercontent.com/justsomeone-e/nyx/main/install.sh | bash
  ```
* **Quick Install (Windows PowerShell):**
  ```powershell
  irm https://raw.githubusercontent.com/justsomeone-e/nyx/main/install.ps1 | iex
  ```

If you enjoy language design, compiler internals, and LLVM/WASM lowerings, we'd love your feedback and stars on GitHub!
