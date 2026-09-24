# Rove v4.0 — Formal Language & Compiler Specification

## 1. Architecture Overview

Rove is a statically analyzed, multi-target programming language with deterministic
type inference, structured diagnostics, and native code-generation targets.

```text
              Rove Source (*.rove)
                            │
                     [ 1. Lexer ] ─── Tokens
                            │
                    [ 2. Parser ] ─── Pure AST
                            │
                 [ 3. TypeChecker ] ─── Typed / Validated AST
                            │
                 ┌──────────┴──────────┐
                 │                     │
          [ C++20 Codegen ]    [ Python Codegen ]
           (cpp -> .cpp)      (python -> .py)
                 │                     │
           Clang / GCC            Python Runner
                 │                     │
          Native Binary (.exe)    Interpreted
```

---

## 2. Core Grammar & Syntax

### 2.1 Variables & Declarations
```rove
var x: int = 10         // Explicit type annotation
var y = 20.5            // Inferred float
let $silver = 8700      // Scoped immutable variable with optional $ sigil
const PI = 3.14159      // Constant declaration
```

### 2.2 Functions & Return Types
```rove
fn add(a: int, b: int) -> int {
    return a + b
}

fn square(value: int) -> int = value * value
```

### 2.3 Structs & Data Modeling
```rove
struct Target {
    name: string,
    freq: int,
    signal: float
}

var t = Target("Altin", 5000, 95.0)
```

### 2.4 Optionals & Safe Navigation
```rove
var user: User? = null
var city = user?.address?.city ?? "Default City"
```

### 2.5 Result & Pattern Matching
```rove
var res = Ok(1337)
match res {
    Ok(val) => print("Success:", val),
    Err(e) => print("Error:", e),
    _ => print("Fallback")
}
```

Value-producing conditionals and literal matches are expressions:

```rove
fn sign(value: int) -> int = if value < 0 { -1 } else if value == 0 { 0 } else { 1 }

fn status(code: int) -> string = match code {
    200 => "ok",
    404 => "missing",
    _ => "other"
}
```

### 2.6 Unsafe Memory Primitives
Raw memory operations (`addr`, `peek`, `memdump`) are strictly constrained inside `unsafe { ... }` blocks:
```rove
var val = 42
unsafe {
    var ptr = addr(val)
    var read_back = peek(ptr)
    assert(read_back == 42)
}
```

---

## 3. Error Diagnostic System (`E1000..E2006`)

All compile-time syntax and semantic errors produce rustc-style source-located diagnostics with underlined caret (`^^^^^`) pointers:

* `E1000`: Unexpected Token in Expression
* `E1001`: Unclosed Parenthesis / Bracket
* `E1012`: Missing `else` in a value-producing `if`
* `E1013`: Invalid value block (more than one expression)
* `E1014`: Invalid value-producing `match` arm syntax
* `E1050`: Unsafe Memory Operation in Safe Context
* `E2001`: Variable Declaration Type Mismatch
* `E2002`: Variable Assignment Type Mismatch
* `E2003`: Function Argument Type Mismatch
* `E2004`: Function Return Type Mismatch
* `E2005`: Incompatible Operator Operands
* `E2006`: Struct Constructor Field Type Mismatch
* `E2014`: Non-exhaustive value-producing `match`
* `E2015`: Unsupported binding pattern in a value-producing `match`

---

## 4. Package Management (`rove.toml` & `rove.lock`)

```toml
[package]
name = "my_project"
version = "0.1.0"
edition = "2026"

[dependencies]
std = "4.0.0"
math = "1.0.0"

[build]
opt_level = 2
output_type = "exe"
```

CLI Commands:
* `rove init [name]`
* `rove add <package> [@version]`
* `rove remove <package>`
* `rove install` (manifest validation and deterministic lockfile refresh; no remote registry fetch in RC1)
* `rove pkg`
* `rove test [file.rove]`
* `rove build [file.rove]`
* `rove run [file.rove]`
