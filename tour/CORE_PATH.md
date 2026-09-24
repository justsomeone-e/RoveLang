# Core Path: Build with Rove

The Core Path is the recommended first route through the Tour of Rove. It is
project-driven: every chapter introduces a language idea because the next
small program needs it. It contains 25 carefully selected exercises. You do
not need to complete every practice exercise before moving on.

Use the normal Tour runner for the exercises. The IDs below are the existing
exercises in `tour/exercises`; this guide adds a learning story without
duplicating or replacing the verified exercise corpus.

## How to use this path

For every chapter:

1. Read the goal before opening the exercise.
2. Run the starter program once and observe its output or diagnostic.
3. Change only the marked code until the exercise passes.
4. Run it again with `rove run` when the lesson is complete.
5. Write one sentence explaining what changed and why.

The expected command from the repository root is:

```text
rove run tour/exercises/<exercise>.rove
```

Rove programs may use top-level statements; `fn main()` is not required for
these examples.

## Chapter 1: Your first Rove program

Goal: verify the toolchain, print a value, and understand the smallest
possible Rove program.

Exercises: `intro01`, `intro02`, `intro03`.

Build result: a program that prints a greeting and can be corrected from a
compiler diagnostic.

## Chapter 2: A typed profile

Goal: store information and update only the values that are intentionally
mutable.

Exercises: `variables01` through `variables05`, then `types01` through
`types06`.

Build result: a small profile CLI that prints a name, age, status, and a
calculated value. The important idea is that `let`, `var`, `const`, and type
annotations communicate intent to the compiler.

## Chapter 3: Decisions and repetition

Goal: make the program respond to data instead of printing a fixed script.

Exercises: `if01`, `if02`, `loops01` through `loops04`, `match01` through
`match03`, `math01` and `math02`.

Build result: a countdown and a small number-classification program. Practice
the difference between a statement that performs work and an expression that
produces a value.

## Chapter 4: Reusable behavior

Goal: move repeated logic into typed functions.

Exercises: `functions01` through `functions06`.

Build result: a number-guessing or score-calculation program with reusable
functions, return types, defaults, and recursion.

## Chapter 5: Model a real domain

Goal: represent related data instead of passing unrelated scalar variables.

Exercises: `arrays01` through `arrays06`, `structs01` through `structs05`,
`enums01` through `enums03`, and `traits01` through `traits03`.

Build result: an inventory or traffic-light simulator. Arrays hold collections,
structs hold domain data, enums model states, and traits describe shared
behavior.

## Chapter 6: Make failure explicit

Goal: distinguish valid results from recoverable failures.

Exercises: `errors01` through `errors03`, `null01` through `null04`, and
`result01` through `result04`.

Build result: a safe input validator or file-inspector core. Use `guard` for
preconditions, nullable values for absence, and `Result<T, E>` for operations
that can fail.

## Chapter 7: Compose the program

Goal: connect small operations into readable, resource-safe workflows.

Exercises: `pipeline01`, `pipeline02`, `defer01`, `defer02`,
`collections01`, and `collections02`.

Build result: a transformation pipeline that cleans, filters, and summarizes
input while guaranteeing cleanup with `defer`.

## Chapter 8: Use the ecosystem

Goal: turn a single file into a maintainable Rove program.

Exercises: `modules01` through `modules03`.

Build result: a small CLI split across modules and using standard-library
boundaries. This is the point where Rove stops being only an exercise language
and becomes useful for a real tool.

## Chapter 9: Add concurrency deliberately

Goal: understand asynchronous work and where failures become observable.

Exercises: `async01` and `async02`.

Build result: a task that is awaited more than once without rerunning the
underlying work, with failure handled at the await boundary.

## Chapter 10: Capstone

Choose one:

- `quiz01`: inventory score calculator
- `quiz02`: banking transaction ledger
- `quiz03`: character progression system

Then extend it with one module import, one explicit error path, one test, and
one user-visible improvement of your choice.

## Practice Lab and advanced track

The remaining exercises are not filler or a second mandatory course. They are
short focused drills for a topic you want to repeat. The modern-expression,
testing, and quiz modules are especially useful after finishing the Core Path.

When the native and WASM workflows are ready, they should become separate
advanced tracks rather than interrupting the first language-learning path.
