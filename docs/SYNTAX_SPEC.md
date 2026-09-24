# Rove v4 Syntax and Semantic Contract

Status: `v4.0.0` (`Nirvana`) stable source contract, effective when the v4.0.0
release is published. Backend support remains defined by capability metadata.

This file defines the compatibility boundary for Rove source. The readable
examples live in [`../LANGUAGE_REFERENCE.md`](../LANGUAGE_REFERENCE.md). The
machine-readable keyword and target contracts live in
`src/core/language_surface.py` and `src/core/backend_capabilities.py`.

## 1. Source and lexical rules

- Source files use UTF-8 and the `.rove` extension.
- Whitespace separates tokens but is otherwise insignificant.
- A semicolon is optional after a complete statement.
- `//` starts a line comment and `///` starts a documentation comment.
- Identifiers are case-sensitive.
- Strings support `\\`, `\"`, `\n`, `\r`, `\t`, `\0`, and `\uXXXX` escapes.
- Unicode normalization is never implicit.

The stable v4 surface contains 43 keywords. Their exact grouping and editor
order are generated from `STABLE_KEYWORD_GROUPS`; editor completion is required
to match that contract exactly. The pre-v4 `def` alias is not a keyword;
function declarations use only `fn`.

## 2. Grammar outline

The following EBNF is a compact compatibility outline. Parser conformance is
proved by exact Python/Rove AST parity tests.

```ebnf
program          = { item | statement } EOF ;

item             = function | struct | trait | implementation | enum
                 | type_alias | extern_function | import | native_directive
                 | test_block ;

import           = "import" string [ "as" identifier ]
                 | "import" "{" identifier { "," identifier } "}"
                   "from" string
                 | "import" ecosystem string [ "from" string ]
                   "as" identifier ;
ecosystem        = "cpp" | "js" | "python" | "rust" | "wasm" ;

function         = [ "async" ] "fn" identifier [ generic_parameters ]
                   "(" [ parameters ] ")" [ "->" type ]
                   ( block | "=" expression [ ";" ] ) ;
trait_method     = [ "async" ] "fn" identifier [ generic_parameters ]
                   "(" [ parameters ] ")" [ "->" type ] ;
struct           = "struct" identifier [ generic_parameters ]
                   "{" [ fields ] "}" ;
trait            = "trait" identifier "{" { trait_method } "}" ;
implementation   = "impl" identifier [ "for" identifier ]
                   "{" { function } "}" ;
enum             = "enum" identifier [ generic_parameters ] "{"
                   enum_member { "," enum_member } [ "," ] "}" ;
enum_member      = identifier [ "(" [ type { "," type } ] ")"
                   | "=" expression ] ;

statement        = declaration | assignment | expression
                 | if_statement | for_statement | while_statement
                 | loop_statement | match_statement | try_statement
                 | guard_statement | defer_statement | unsafe_block
                 | spawn_block | return_statement | throw_statement
                 | break_statement | continue_statement ;

declaration      = ( "var" | "let" | "const" ) identifier
                   [ ":" type ] "=" expression ;
assignment       = [ "set" ] assignable "=" expression ;
if_statement     = "if" expression block
                   { ( "elif" expression | "else" "if" expression ) block }
                   [ "else" block ] ;
for_statement    = "for" identifier "in" expression block ;
while_statement  = "while" expression block ;
loop_statement   = "loop" block ;
try_statement    = "try" block "catch" identifier block ;
throw_statement  = "throw" expression ;

expression       = pipeline | if_expression | match_expression ;
if_expression    = "if" expression value_block
                   { ( "elif" expression | "else" "if" expression ) value_block }
                   "else" value_block ;
match_expression = "match" expression "{"
                   { literal "=>" value_expression "," }
                   "_" "=>" value_expression [ "," ] "}" ;
value_expression = expression | value_block ;
value_block      = "{" expression [ ";" ] "}" ;
pipeline         = null_coalesce { "|>" call_target } ;
null_coalesce    = logical_or { "??" logical_or } ;
unary            = ( "!" | "not" | "-" | "+" | "~" | "await" ) unary
                 | postfix ;
postfix          = primary { call | member | safe_member | index | "?" } ;
```

Foreign imports require an explicit alias. In the current development
contract, `cpp`, `js`, and `python` are executable integrations; `import rust`
and `import wasm` remain reserved and produce `E1413` until their package
resolution and general foreign-module lowering exist. Versioned WASM host
functions use the separate `extern "WASM:<namespace>"` contract already used by
`std/web`; they are not general `import wasm` modules. A C++ import also
requires its header:

```rove
import cpp "std::filesystem" from "<filesystem>" as fs
import js "node:os" as os
import python "platform" as platform
```

Operator precedence, from tightest to loosest, is postfix, unary,
multiplicative, additive, shifts, comparisons, equality, bitwise AND/XOR/OR,
logical AND/OR, null coalescing, then pipeline.

## 3. Binding contract

- `var` creates a rebindable binding.
- `let` and `const` create non-rebindable bindings.
- Binding immutability is shallow. It does not imply a recursively immutable
  object graph or a C++-style const receiver.
- `set x = value` and `x = value` have the same assignment semantics. `set` is
  the preferred explicit spelling.
- `let [a, b] = array` destructures an `Array<T>` after one evaluation and uses
  checked bounds behavior. `_` discards a position.
- `let Point(x, y) = point` destructures every struct field positionally in
  declaration order. The pattern type, initializer type, and arity must match.
- Nested, tuple, and `..rest` destructuring are reserved for later contracts.
- HIR verification, rather than target-language syntax, enforces rebinding.
- Trait methods are bodyless signatures. Trait implementations must name a
  declared trait and struct, provide `self` first, and exactly match every
  required method's async marker, value-parameter types, and return type.
- Inherent implementations may also declare associated functions without
  `self`; only methods called on an instance declare `self` first.

## 4. Type and control-flow contract

- `int` has the canonical signed 64-bit hosted representation.
- `float` has the canonical IEEE-754 binary64 hosted representation.
- `i8/i16/i32/i64`, `u8/u16/u32/u64`, and `f32/f64` select concrete storage
  widths on declaring native and Rust backends. Literal narrowing is
  rejected before code generation.
- Source integer literals are restricted to
  `-9223372036854775808..9223372036854775807`; `E2012` rejects any other
  magnitude before HIR lowering. Direct negation of decimal or hexadecimal 2⁶³
  forms the minimum value.
- Signed integer overflow wraps modulo 2⁶⁴; it never invokes target-language
  undefined behavior or loses precision through a JavaScript `Number`.
- Integer division truncates toward zero. Remainder has the dividend's sign.
  Shift counts are masked to six bits.
- Floating division follows IEEE-754 binary64, including infinities and NaN.
  Floating `%` is the truncating `fmod` operation.
- Canonical numeric string conversion is target-independent: `nan`, `inf`,
  `-inf`, no exponent zero-padding, and negative zero rendered as `0`.
- Canonical boolean text is lowercase `true` or `false`.
- Implicit `int` to `float` widening performs binary64 conversion at the use
  boundary and never rewrites the source binding's type. No implicit `float`
  to `int` narrowing exists.
- Constant folding uses these same rules, including i64 wrap, masked shifts,
  truncating division, and mixed-number widening. Optimization cannot change a
  program's numeric result.
- `cpp`, `js`, and `python` advertise `int64_wrap`, `float64_ieee`, and
  `canonical_scalar_text`. `wasm` remains a beta `wasm32` numeric contract.
- Conditions require `bool`; implicit truthiness is not part of v4. A value
  whose type remains `any` is checked at the condition boundary and raises a
  runtime type error unless its actual value is exactly Boolean.
- `a..b` is inclusive at both ends.
- `break` and `continue` require an enclosing loop.
- `return` requires an enclosing function and must match its declared result.
- `fn name(...) -> T = expression` is exactly one implicit return; it does not
  change return typing or evaluation order.
- An `if` used as an expression requires `else`, every arm produces one value,
  and arm types must agree (with the normal `int` to `float` widening rule).
- A value-producing `match` supports literal arms and must end with exactly one
  `_` fallback. Its arm values have the same type-unification rule as an
  if-expression. Its subject is evaluated exactly once before pattern
  comparisons, including calls and other side-effecting expressions.
- Statement `match` remains the pattern-binding form for `Ok(value)`,
  `Err(error)`, payload enum variants such as `Point(x, y)`, and unit variants
  such as `Tick()`.
- Payload enum constructor names are module-level and must be unique. Their
  generic arguments are inferred from payload values or may be fixed by a
  variable/function type annotation. C++, JavaScript, and Python implement
  payload enums; other targets reject them before emission through the
  capability registry.
- `guard condition else { ... }` executes its else body when the condition is
  false; that body is expected to leave the guarded path.
- `defer expression` executes once when its lexical scope exits, including an
  exit caused by return or a propagated exception.
- Postfix `expr?` accepts only `Result<T, E>`. On `Ok(value)` it evaluates to
  `value`; on `Err(error)` it returns that error from the nearest enclosing
  `Result<U, E>` function. The operand is evaluated exactly once, the outer
  error type must accept the propagated error, and using `?` outside such a
  function is a compile-time error. C++, JavaScript, and Python implement this
  contract; other targets reject it through the capability registry.

## 5. Task contract

- Calling `async fn f(...) -> T` produces `Task<T>`.
- `await value` is valid only in an async function.
- The operand of `await` must be `Task<T>` and the expression type is `T`.
- A task represents one shared completion and may be awaited repeatedly.
- Success values and thrown errors are replayed consistently to every awaiter.
- Task start timing is unspecified; code must not depend on eager versus deferred
  scheduling.
- Cancellation and structured-concurrency ownership are not part of RC1.

`cpp`, `js`, and `python` implement this contract respectively with a shared
future, a Promise, and a reusable wrapper around one `asyncio.Task`.

## 6. Exception contract

- `throw expression` transfers control to the nearest matching `catch`.
- The caught value uses Rove's canonical string conversion at the exception
  boundary.
- An uncaught error terminates the top-level task/program with failure.
- Exceptions cross `Task<T>` at `await`; they are not converted to success
  values.

Exceptions and tasks are capability-gated. A backend without the feature must
emit `E3001` before code generation.

## 7. HIR authority

The source frontend lowers to immutable typed HIR v1. A backend may only consume
verified HIR for a stable designation. The verifier owns:

- symbol identity and declaration-before-use;
- type compatibility and callable arity;
- immutable-binding checks;
- loop, return, await, and assignment placement;
- HIR schema and structural validity.

Backend-specific source rewrites or silent feature approximations are forbidden.
Unsupported behavior must be rejected through the versioned capability registry.

## 8. Compatibility rule

After RC1, existing valid v4 source cannot change meaning within the v4 line.
New syntax must be additive, have exact Python/Rove frontend parity, lower to
target-neutral HIR, and either pass runtime parity on every declaring backend or
be rejected by an explicit capability gate.

## 9. Language evolution rule

Microcontroller and freestanding firmware targets are not part of the active
v4 language contract. The former `volatile`, `interrupt`, `critical`,
`Buffer<T, N>`, and `buffer_ptr` surface has been removed from both frontends.
A future fixed-size collection must be target-neutral and enter through a new
syntax RFC.

New syntax must introduce a distinct, testable semantic operation. Alias
keywords that only duplicate an existing spelling are rejected. Every accepted
syntax RFC requires Python/Rove frontend parity, type-checker coverage, canonical
HIR lowering, structured negative diagnostics, and backend capability tests.
