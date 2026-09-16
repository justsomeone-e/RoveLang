# Tour of Nyx 🌙

> An interactive, guided terminal tour of the Nyx programming language, inspired by `rustlings`, with high-fidelity ANSI graphics, instant diagnostics, and live file-watching.

```text
  ████████╗ ██████╗ ██╗   ██╗██████╗      ██████╗ ███████╗    ███╗   ██╗██╗   ██╗██╗  ██╗
  ╚══██╔══╝██╔═══██╗██║   ██║██╔══██╗    ██╔═══██╗██╔════╝    ████╗  ██║╚██╗ ██╔╝╚██╗██╔╝
     ██║   ██║   ██║██║   ██║██████╔╝    ██║   ██║█████╗      ██╔██╗ ██║ ╚████╔╝  ╚███╔╝ 
     ██║   ██║   ██║██║   ██║██╔══██╗    ██║   ██║██╔══╝      ██║╚██╗██║  ╚██╔╝   ██╔██╗ 
     ██║   ╚██████╔╝╚██████╔╝██║  ██║    ╚██████╔╝██║         ██║ ╚████║   ██║   ██╔╝ ██╗
     ╚═╝    ╚═════╝  ╚═════╝ ╚═╝  ╚═╝     ╚═════╝ ╚═╝         ╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝
```

---

## 🚀 Quick Start

From the repository root:
```bash
# Windows Command Prompt
tour.bat

# PowerShell
.\tour.ps1

# Linux / macOS
bash tour.sh

# Direct Python
python tour/tour.py

# Explicit Core Path invocation (also the launcher default)
python tour/tour.py core
```

Or double-click **`Tour of Nyx.bat`** on your Desktop!

---

## 🎮 Interactive Controls in Watch Mode

While in watch mode, the Tour monitors your current exercise file in real-time. Whenever you save changes in your code editor (like VS Code), the compiler immediately verifies your solution.

| Hotkey | Action | Description |
| :---: | :--- | :--- |
| **`n`** | **Next** | Advance to the next exercise |
| **`p`** | **Prev** | Go back to the previous exercise |
| **`h`** | **Hint** | View progressive hints for the current exercise |
| **`r`** | **Re-run** | Force a re-compilation / re-execution |
| **`l`** | **List** | Open full interactive curriculum tree |
| **`s`** | **Solution** | Toggle reference solution view if stuck |
| **`q`** | **Quit** | Save progress and exit cleanly |

---

## Learning route

The Tour has two layers:

- **Core Path:** a project-driven route for learning Nyx from the first print
  statement to a multi-module application. Read [`CORE_PATH.md`](CORE_PATH.md)
  first.
- **Practice Lab:** the complete verified exercise corpus. Use it to repeat a
  topic, compare solutions, or explore a feature outside the main route.

Each Core Path chapter answers four questions: why the feature exists, what
the smallest working example looks like, what you should change, and where
the feature is useful in a real program.

## Practice Lab curriculum (81 exercises across 21 modules)

The first modules establish the language fundamentals. Later modules require
observable behavior—typed error propagation, single evaluation, task reuse,
collection transformations, and real standard-library boundaries—rather than
repeating keywords in isolation.

1. **`00_intro`** (3 exercises)
   - `intro01`: Welcome to Nyx & verifying your environment.
   - `intro02`: Fixing syntax errors in string literals.
   - `intro03`: Line comments and uncommenting executable code.
2. **`01_variables`** (8 exercises)
   - `variables01`: Immutable bindings with `let`.
   - `variables02`: Mutable variables with `var` and `set`.
   - `variables03`: Static type annotations (`int`, `string`, `bool`).
   - `variables04`: Constant declarations with `const`.
   - `variables05`: Arithmetic operations and variable scoping.
   - `variables06`: Destructuring array patterns (`let [x, y] = coords`).
   - `variables07`: Variable shadowing across nested block scopes.
   - `variables08`: Discarding destructured values with `_`.
3. **`02_types`** (6 exercises)
   - `types01`: Scalar types: `int`, `float`, and widening.
   - `types02`: Boolean logic with `and`, `or`, and `not`.
   - `types03`: String concatenation and escapes.
   - `types04`: Measuring string length with `len()`.
   - `types05`: Character escape sequences (`\n`, `\t`, `\"`).
   - `types06`: Automatic `int` to `float` widening.
4. **`03_functions`** (6 exercises)
   - `functions01`: Function declarations with `fn`.
   - `functions02`: Parameters and explicit return types (`-> int`).
   - `functions03`: Expression-bodied functions (`fn square(x) = x * x`).
   - `functions04`: Trailing default parameter values.
   - `functions05`: Recursive function calls (`factorial`).
   - `functions06`: Multiple arguments and computational composition.
5. **`04_control_flow`** (9 exercises)
   - `if01`: Multi-branch `if` / `elif` / `else`.
   - `if02`: Value-producing `if` expressions.
   - `loops01`: Inclusive range loops (`for i in 1..5`).
   - `loops02`: State-driven `while` loops.
   - `loops03`: Unconditional `loop`, `break`, and `continue`.
   - `loops04`: Nested loops and multidimensional iteration.
   - `match01`: Pattern matching with mandatory wildcard `_`.
   - `match02`: Literal numeric matching with a wildcard fallback.
   - `match03`: Boolean value matching.
6. **`05_arrays`** (6 exercises)
   - `arrays01`: Array literals and 0-based indexing.
   - `arrays02`: In-place element modification with `set arr[i] = ...`.
   - `arrays03`: Iterating and aggregating array data.
   - `arrays04`: Appending items dynamically with `.push()`.
   - `arrays05`: Removing trailing items with `.pop()`.
   - `arrays06`: Multi-dimensional nested matrices.
7. **`06_structs`** (5 exercises)
   - `structs01`: Declaring and instantiating data structs.
   - `structs02`: Methods and `self` with `impl StructName`.
   - `structs03`: Nested structures and entity composition.
   - `structs04`: Struct constructor factory pattern.
   - `structs05`: Struct destructuring patterns (`let Point(x, y) = p`).
8. **`07_enums`** (3 exercises)
   - `enums01`: Declaring enums and referencing member variants.
   - `enums02`: Equality and variant comparison (`==`).
   - `enums03`: State machines driven by enum variants.
9. **`08_traits`** (3 exercises)
   - `traits01`: Trait definitions and contract implementations (`impl Trait for Type`).
   - `traits02`: Multi-trait polymorphism across shared types.
   - `traits03`: Trait methods with typed arguments.
10. **`09_error_handling`** (3 exercises)
    - `errors01`: Structured exceptions with `try`, `catch`, and `throw`.
    - `errors02`: Error message extraction and exception propagation.
    - `errors03`: Guarding against divide-by-zero errors.
11. **`10_null_safety`** (4 exercises)
    - `null01`: Optional types (`string?`, `null`) and null coalescing (`??`).
    - `null02`: Nullable integers and fallback values.
    - `null03`: Precondition enforcement with `guard ... else { return }`.
    - `null04`: Multi-condition guards for data validation.
12. **`11_pipelines`** (2 exercises)
    - `pipeline01`: Function composition with the pipeline operator (`|>`).
    - `pipeline02`: Multi-stage data processing pipeline.
13. **`12_defer`** (2 exercises)
    - `defer01`: Scope cleanup and guaranteed exit actions.
    - `defer02`: Multiple deferred cleanups executing in LIFO sequence.
14. **`13_math_and_logic`** (2 exercises)
    - `math01`: Modulo operator `%` and parity checks.
    - `math02`: Bitwise operators (`&`, `|`, `^`, `<<`).
15. **`14_testing`** (2 exercises)
    - `tests01`: In-file unit testing with `test "name" { assert(...) }`.
    - `tests02`: Multiple distinct test cases in a single file.
16. **`15_quizzes`** (3 capstone quizzes)
    - `quiz01`: RPG Inventory Score Calculator (structs, methods, loops, match, guards).
    - `quiz02`: Banking Transaction Ledger (structs, mutation, loops, error checks).
    - `quiz03`: Character Level-Up System (enums, traits, state progression).
17. **`16_modern_expressions`** (3 exercises)
    - `strings01`: Unicode-safe typed string interpolation.
    - `navigation01`: Nested optional traversal with `?.` and `??`.
    - `match04`: Single evaluation of a side-effecting match subject.
18. **`17_results`** (4 exercises)
    - `result01`: Payload enums and destructuring match arms.
    - `result02`: Recoverable domain failures with `Result<T, E>`.
    - `result03`: Typed early error propagation with postfix `?`.
    - `result04`: Composition of multiple fallible operations.
19. **`18_collection_transforms`** (2 exercises)
    - `collections01`: Direct iteration over typed domain objects.
    - `collections02`: Contextual lambdas with `map`, `filter`, and `fold`.
20. **`19_async_tasks`** (2 exercises)
    - `async01`: Reusing one `Task<T>` completion without rerunning work.
    - `async02`: Catching task failures at the `await` boundary.
21. **`20_modules_and_stdlib`** (3 exercises)
    - `modules01`: Selective imports from `std/math`.
    - `modules02`: Unicode Base64 round-trips and malformed-input results.
    - `modules03`: Honest flat-field extraction with `std/json_lite`.

---

## 🛠️ CLI Subcommands

```bash
# Core Path (default launcher behavior)
tour.bat

# Watch mode with the full Practice Lab
tour.bat --track all

# Direct Python watch mode (full Practice Lab)
python tour/tour.py

# Check only the Core Path
tour.bat --track core check-all

# Check all exercises and display overall progress table
tour.bat check-all

# Run a specific exercise
tour.bat run variables01

# Display hints for an exercise
tour.bat hint variables02

# List the full curriculum tree
tour.bat list

# Reset an exercise to its initial broken state
tour.bat reset variables01

# Reset all exercises and reset state
tour.bat reset all

# Reset the Core Path progress
tour.bat --track core reset all
```

---

## 🧪 Autonomous Test Suite

To verify that all 81 unsolved exercises fail as expected and all 81 reference solutions compile and pass with 0 errors:

```bash
python tour/verify_all.py
```
Output:
```text
======================================================================
Tour of Nyx - Autonomous Verification Suite (81 Exercises)
======================================================================
[01/81] ✅ PASS intro01        (Unsolved: FAIL as expected | Solved: OK in 411ms)
...
[81/81] ✅ PASS modules03      (Unsolved: FAIL as expected | Solved: OK in 404ms)
======================================================================
Verification Summary: 81/81 passed.
🎉 ALL 81 EXERCISES AND SOLUTIONS VERIFIED 100% CLEANLY!
======================================================================
```
