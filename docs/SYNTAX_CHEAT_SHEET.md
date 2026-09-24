# Rove Syntax Rosetta Stone & Cheat Sheet

Compare Rove directly against Python, Rust, Go, TypeScript, and C++20.

| Feature | Rove | Python 3 | Rust | Go | C++20 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Variable** | `var x: int = 10;` | `x: int = 10` | `let x: i32 = 10;` | `var x int = 10` | `int x = 10;` |
| **Immutable** | `const K: int = 5;` | `K = 5` | `const K: i32 = 5;` | `const K = 5` | `constexpr int K = 5;` |
| **Function** | `fn add(a: int, b: int) -> int` | `def add(a: int, b: int) -> int:` | `fn add(a: i32, b: i32) -> i32` | `func add(a, b int) int` | `int add(int a, int b)` |
| **Early Exit** | `guard cond else { return; }` | `if not cond: return` | `if !cond { return; }` | `if !cond { return }` | `if (!cond) return;` |
| **Optional / Null** | `var s: string? = null;` | `s: Optional[str] = None` | `let s: Option<String> = None;` | `var s *string = nil` | `std::optional<string> s;` |
| **Coalescing** | `var v = s ?? "default";` | `v = s or "default"` | `let v = s.unwrap_or("default");` | *(manual if nil check)* | `s.value_or("default");` |
| **Struct** | `struct Point { x: int, y: int }` | `@dataclass class Point:` | `struct Point { x: i32, y: i32 }` | `type Point struct { X, Y int }` | `struct Point { int x, y; };` |
| **Methods** | `impl Point { fn sum(self) -> int }` | `class Point: def sum(self):` | `impl Point { fn sum(&self) -> i32 }` | `func (p Point) Sum() int` | `int Point::sum() const` |
| **Pattern Match**| `match val { 1 => ..., _ => ... }` | `match val: case 1: ...` | `match val { 1 => ..., _ => ... }` | `switch val { case 1: ... }` | `switch(val) { case 1: ... }` |
| **Concurrency** | `spawn { ... }` | `threading.Thread(...)` | `thread::spawn(...)` | `go func() { ... }()` | `std::jthread(...)` |
| **Compilation** | Native / JS / Py / WASM | Bytecode VM | Native LLVM | Native | Native Clang/GCC |