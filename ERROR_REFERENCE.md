# Rove — Compiler Diagnostic & Error Catalog

This document details all semantic errors emitted by the Rove `TypeChecker` (`src/core/type_checker.py`), including why they occur and how to resolve them.

---

## 1. Type & Mutability Errors (`E1000..E1099`)

### `E1000: Duplicate Variable Declaration`
* **Cause**: A variable with the same identifier is declared more than once in the same local scope.
* **Example**:
  ```rove
  var x: int = 10
  var x: string = "hello"  // [E1000]
  ```
* **Fix**: Use reassignment `x = 20` or declare with a distinct variable name.

### `E1001: Type Mismatch`
* **Cause**: The expression assigned or returned does not match the explicitly declared or inferred type.
* **Example**:
  ```rove
  var count: int = "42"  // [E1001]
  ```
* **Fix**: Convert the value (`to_int("42")`) or change the annotation to `string`.

### `E1002: Unknown Type`
* **Cause**: A type annotation refers to a struct, primitive, or generic that has not been imported or defined.
* **Example**:
  ```rove
  var item: NonExistentType = null  // [E1002]
  ```
* **Fix**: Declare the struct or verify spelling.

### `E1003: Cannot Mutate Immutable Binding`
* **Cause**: A variable declared with `val` (immutable constant) is being reassigned.
* **Example**:
  ```rove
  val PI: float = 3.14159
  PI = 3.14  // [E1003]
  ```
* **Fix**: Declare with `var` if the binding is intended to be mutable.

---

## 2. Function & Call Errors (`E1100..E1199`)

### `E1100: Undefined Function / Callee`
* **Cause**: Calling a function that does not exist in the current scope or standard library.
* **Example**:
  ```rove
  compute_physics(100)  // [E1100]
  ```
* **Fix**: Define `fn compute_physics(...)` before calling or import its module.

### `E1101: Argument Count Mismatch`
* **Cause**: Passing fewer or more arguments than the function signature expects.
* **Example**:
  ```rove
  fn add(a: int, b: int) -> int { return a + b }
  add(10)  // [E1101] (Expected 2, got 1)
  ```
* **Fix**: Supply all required positional arguments.

### `E1102: Return Type Mismatch`
* **Cause**: The returned expression does not match the function's annotated return type.
* **Example**:
  ```rove
  fn get_age() -> int {
      return "twenty"  // [E1102]
  }
  ```
* **Fix**: Ensure return expressions match the declared signature.

---

## 3. Struct, Trait & Memory Errors (`E1200..E2006`)

### `E1200: Undefined Struct Field`
* **Cause**: Accessing or assigning a field that does not exist on the struct instance.
* **Example**:
  ```rove
  struct Point { x: int, y: int }
  var p = Point { x: 10, y: 20 }
  print(p.z)  // [E1200]
  ```
* **Fix**: Verify field names in the struct definition.

### `E2000: Unsafe Operation Outside Unsafe Block`
* **Cause**: Performing raw pointer arithmetic, calling `addr()`, `peek()`, or inline assembly outside an `unsafe { ... }` block.
* **Example**:
  ```rove
  var ptr = addr(val)  // [E2000]
  ```
* **Fix**: Wrap low-level memory operations in an `unsafe` block:
  ```rove
  unsafe {
      var ptr = addr(val)
  }
  ```

---

## 4. Diagnostic Display Standard

All diagnostics include source filename, 1-indexed line and column numbers, error code, visual source preview, and caret indicator:

```text
Error[E1001]: Type Mismatch in 'main.rove':3:18
  3 | var count: int = "42"
    |                  ^^^^ Expected 'int', found 'string'
```
