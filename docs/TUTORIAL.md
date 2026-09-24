# Learn Rove in 15 Minutes

> **Rove**: Designed to combine **Python's simplicity**, **Rust's memory safety**, and **C++20's bare-metal execution speed**.

---

## 1. Variables and Types

Rove provides strong static typing with local type inference:

```rove
var name: string = "Rove";
var count: int = 42;
var pi: float = 3.14159;
var is_active: bool = true;

// Inferred variables
var total = 100; // int inferred
```

---

## 2. Functions and Returns

Functions are declared with `fn`, typed parameters, and `->` for return types:

```rove
fn multiply(a: int, b: int) -> int {
    return a * b;
}

fn greet(person: string) -> string {
    return "Hello, " + person + "!";
}
```

---

## 3. Guard Statements (Early Exit)

Avoid pyramid-of-doom nested `if` statements with `guard`:

```rove
fn process_order(quantity: int) -> int {
    guard quantity > 0 else {
        print("Invalid quantity!");
        return -1;
    }
    
    return quantity * 10;
}
```

---

## 4. First-Class Null Safety

Optional variables are declared with `?` and unwrapped with `??` (coalescing) or `?.` (safe navigation):

```rove
var nickname: string? = null;

// Null-coalescing default
var greeting_name = nickname ?? "Guest";

// Safe navigation
var length = nickname?.len() ?? 0;
```

---

## 5. Structs and Implementation Blocks

Rove separates pure state definition (`struct`) from behavioral methods (`impl`):

```rove
struct Rectangle {
    width: int,
    height: int
}

impl Rectangle {
    fn area(self) -> int {
        return self.width * self.height;
    }
    
    fn is_square(self) -> bool {
        return self.width == self.height;
    }
}
```

---

## 6. Pattern Matching

Use exhaustive `match` expressions for branching:

```rove
var status_code = 200;

match status_code {
    200 => print("OK"),
    404 => print("Not Found"),
    500 => print("Internal Error"),
    _   => print("Unknown Status")
}
```

---

## 7. Multi-Target Compilation

The same clean Rove source code compiles without changes across any target:

```bash
# 1. Native C++20 Executable
rove run main.rove --target cpp

# 2. Node.js ES2022 Module
rove run main.rove --target js

# 3. Python 3 Reference Module
rove run main.rove --target python

# 4. WebAssembly & React 19 Bundle
rove bundle main.rove -o dist/
```