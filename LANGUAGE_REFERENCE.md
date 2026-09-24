# Rove v4 Language Reference

This document describes the `v4.0.0-rc.2` (`Bodhi`) source-language contract.
Rove source files use the `.rove` extension and are built with the `rove` CLI.
Backend availability is a capability decision, not a change to language syntax.

## 1. Bindings and assignment

```rove
var attempts: int = 0       // mutable binding
let limit: int = 3          // immutable binding
const APP_NAME = "Rove"      // immutable binding

set attempts = attempts + 1
```

`let` and `const` prevent rebinding. They do not deep-freeze a struct, array, or
other value reachable through the binding. `set target = value` is the explicit
assignment form; `target = value` remains equivalent for source compatibility.

Array and positional struct destructuring declarations bind several names while
evaluating the initializer exactly once:

```rove
let [left, right] = read_pair()

struct Point { x: int, y: int }
let Point(x, y) = Point(10, 20)
let [first, _] = values       // `_` discards one position
```

An array pattern requires an `Array<T>`; insufficient input fails through a
checked bounds path. A struct pattern must name a declared struct and provide
one position for every field in declaration order. Nested and `..rest` patterns
are not part of this first contract.

```rove
struct Counter { value: int }

let counter = Counter(0)
set counter.value = 1       // valid: the binding still refers to the same Counter
// set counter = Counter(2) // error: counter is an immutable binding
```

## 2. Core types

The portable scalar types are `int`, `float`, `bool`, `string`, `char`,
`uintptr`, and `void`. Generic library/compiler types include `Array<T>`,
`Option<T>`, `Result<T, E>`, `Channel<T>`, and `Task<T>`.

Fixed-width scalar spellings are `i8`, `i16`, `i32`, `i64`, `u8`, `u16`,
`u32`, `u64`, `f32`, and `f64`. They select concrete storage widths on native
and Rust backends. A directly assigned integer literal
must fit its declared width (`E2024`); implicit narrowing is not permitted.
The hosted cross-backend arithmetic contract remains the canonical `int` and
`float` contract below until width-specific overflow semantics are frozen for
JavaScript and Python.

`int` is a signed 64-bit two's-complement value. Addition, subtraction,
multiplication, negation, bitwise operations, and left shift wrap modulo 2⁶⁴.
Integer division truncates toward zero, remainder keeps the dividend's sign,
and shift counts are reduced modulo 64. Division by zero raises an error.
Integer literals must be between `-9223372036854775808` and
`9223372036854775807`; an out-of-range literal is `E2012`. The minimum value is
accepted in its directly negated decimal or hexadecimal spelling.

`float` is IEEE-754 binary64. Division by zero produces the corresponding
infinity or NaN; `%` uses a truncating remainder with the dividend's sign.
Canonical text uses `nan`, `inf`, `-inf`, normalized exponents such as `1e-7`,
and renders negative zero as `0`. Finite values use a shortest round-tripping
decimal without a redundant `.0`. Nonzero magnitudes from `1e-6` (inclusive)
to `1e21` (exclusive) use fixed notation; other magnitudes use scientific
notation with an explicit `+` for positive exponents and no exponent padding.

An `int` widens to `float` by IEEE-754 binary64 conversion when required by an
operator, parameter, field, or return type. The conversion can round integers
whose magnitude exceeds 2⁵³; it never changes the original `int` binding's
type. `float` does not narrow to `int` implicitly. Canonical booleans are
rendered as lowercase `true` and `false`.

The full numeric and scalar-text contract is declared by `cpp`, `js`, and
`python`. The beta `wasm` ABI remains explicitly `wasm32` and does not claim
signed-i64 conformance until its numeric ABI is revised.

```rove
let answer: int = 42
let ratio: float = 0.5
let title: string = "Rove"
let maybe_name: string? = null
let values: Array<int> = [1, 2, 3]
```

Strings are Unicode values. Literals support common escapes, embedded `\0`,
four-hex-digit Unicode escapes such as `\u0301`, and interpolation:

```rove
let city = "İstanbul"
print($"hello, {city} 🌙")
```

Rove does not normalize Unicode automatically; NFC and NFD spellings remain
distinct byte sequences.

## 3. Functions

```rove
fn add(a: int, b: int) -> int {
    return a + b
}

fn greet(name: string) {
    print("Hello, " + name)
}

fn square(value: int) -> int = value * value

fn classify(value: int) -> string = if value < 0 {
    "negative"
} elif value == 0 {
    "zero"
} else {
    "positive"
}
```

Parameters and return values are typed. A missing return annotation means
`void` unless the compiler can safely infer a value type in an inference-enabled
context. `= expression` is an expression-bodied function and behaves as one
implicit `return`. A value-producing `if` requires an `else`; each arm contains
one expression and every arm must have a compatible result type.

A parameter may declare a default value with `= expression`. An omitted trailing
argument is filled with that default value at the call site, so the default is
re-evaluated on every call. Only trailing parameters may be omitted; a required
parameter before an omitted one is an arity error.

```rove
fn greet(name: string = "world", times: int = 1) {
    var count: int = 0
    while count < times {
        print("hi", name)
        set count = count + 1
    }
}

greet()                 // name = "world", times = 1
greet("rove")            // name = "rove",  times = 1
greet("rove", 3)         // name = "rove",  times = 3
```

A default value whose type does not match its declared parameter type is a
compile-time error, as is omitting a parameter that has no default.

## 4. Async tasks

```rove
async fn compute() -> int {
    return 42
}

async fn main() {
    let task: Task<int> = compute()
    let first: int = await task
    let second: int = await task
    print(first + second)
}
```

An `async fn ... -> T` call returns `Task<T>`. `await` is valid only inside an
async function and unwraps one `Task<T>` to `T`. A task is reusable: awaiting the
same task more than once observes the same completion. Errors thrown by the task
propagate at `await` and can be caught normally. The exact instant at which a
task begins execution is intentionally not part of the language contract.

The `Task<T>` ABI is currently implemented by `cpp`, `js`, and `python`.
Other targets reject it with a capability diagnostic instead of silently
changing its behavior.

## 5. Control flow

```rove
if score >= 90 {
    print("A")
} else if score >= 80 {
    print("B")
} else {
    print("C")
}

for i in 1..10 {
    if i == 5 { continue }
    print(i)
}

var remaining = 3
while remaining > 0 {
    set remaining = remaining - 1
}

loop {
    break
}
```

`a..b` is an inclusive range. `elif` and `else if` are equivalent spellings.
`break` and `continue` are valid only inside loops. Conditions accept only
`bool`; a dynamically typed `any` value is checked at runtime rather than
using C++/JavaScript/Python truthiness.

`match` can also produce a value without a `return` in every arm:

```rove
fn http_label(code: int) -> string = match code {
    200 => "ok",
    404 => "missing",
    _ => "other"
}
```

The final `_` fallback is mandatory and arm values must share a compatible
type. Maya's first value-match form accepts literals. The subject is evaluated
exactly once, including calls and other side-effecting expressions:

```rove
let label = match read_status() { 200 => "ok", _ => "other" }
```

`guard` expresses an early-exit precondition, while `defer` runs an expression
when the current scope exits:

```rove
fn save(value: string?) {
    guard value != null else { return }
    defer print("save finished")
    print(value)
}
```

## 6. Structs, traits, and implementations

```rove
struct Point {
    x: int,
    y: int
}

trait Show {
    fn show(self) -> string
}

impl Show for Point {
    fn show(self) -> string {
        return $"({self.x}, {self.y})"
    }
}

let point = Point(10, 20)
print(point.show())
```

An inherent implementation omits the trait name: `impl Point { ... }`.
Instance methods declare `self` explicitly as their first parameter; an
inherent implementation may also contain an associated function without
`self`. Trait methods are signatures, not default implementations, and
therefore have no body. An `impl Trait for Type` must provide every required
method with the same async marker, parameter types, and return type. The target
must be a declared struct.

## 7. Errors and cleanup

```rove
fn parse_port(value: int) -> int {
    if value < 1 { throw "port must be positive" }
    return value
}

try {
    print(parse_port(0))
} catch error {
    print("caught:", error)
}
```

`throw` converts its value to the canonical Rove string representation for the
current exception boundary. `try`/`catch`/`throw` are available on `cpp`,
`js`, and `python`; unsupported targets fail during capability validation.

For recoverable domain errors that are part of an API, prefer `Result<T, E>` and
pattern matching:

```rove
let result: Result<int, string> = Ok(42)

match result {
    Ok(value) => print(value),
    Err(error) => print(error),
    _ => print("unreachable")
}
```

Statement `match` keeps `"_"` as a legacy wildcard for source compatibility;
use `_` in new code. Comparison patterns must match the subject type, except
that an `int` pattern may widen to a `float` subject.

## 8. Pipelines and null safety

```rove
fn doubled(value: int) -> int { return value * 2 }

let result = 21 |> doubled
let display_name = user?.profile?.name ?? "anonymous"
```

`value |> function` passes `value` as the next call's input. `?.` propagates
absence and `??` supplies a fallback.

## 9. Modules

```rove
import "./helper"
import "std/math"
import { sqrt, clamp } from "std/math"
```

Local modules use `.rove` files. Standard-library availability is target-specific
and can be inspected with `rove targets --json`.

Local packages can be locked without a registry:

```text
rove add physics --path ../physics
rove install
```

The lockfile records canonical relative paths and source-content checksums;
recursive dependency cycles are rejected.

For WebAssembly browser programs, `std/web` provides opaque `WebElement`,
`WebEvent`, and `WebListener` handles plus DOM, event, animation-frame, and
Canvas 2D functions. These calls require the generated `rove_host_v1` adapter
and are rejected on non-WASM targets.

## 10. Tests and unsafe boundaries

```rove
test "addition" {
    assert(add(2, 3) == 5, "addition must be exact")
}

unsafe {
    let address = addr(answer)
    print(peek(address))
}
```

Raw memory operations must remain inside an explicit `unsafe` boundary.

## 11. CLI

```text
rove check main.rove
rove run main.rove --target cpp
rove build main.rove --target js
rove bundle main.rove --output dist --package --react --vue --svelte
rove test main.rove
rove self-host verify
rove targets --json
```

The canonical stable hosted backends are `cpp` (C++20/native), `js`
(ES2022/Node.js), and `python` (Python 3). `wasm`, `rust`, `react`, and `asm`
expose narrower, machine-readable capability sets and must
reject unsupported semantics.
