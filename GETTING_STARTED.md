# Getting Started with Rove

Welcome to **Rove**! This guide walks you from zero to building, testing, and packaging your first project.

---

## 1. Installation & Environment Check

Verify that Rove is properly configured by running:

```bash
he version
```

Output:
```text
===================================================================
⚡ Rove (he) Core v4.0.0-RELEASE — Enterprise Systems Toolchain
===================================================================
Detected Host Toolchains & Execution Engines:
  • C++20 Toolchain:      .../clang++.exe
  • JavaScript Engine:    .../node.exe
  • Rust Compiler:        .../rustc.exe
  • Python Reference:     .../python.exe
===================================================================
```

---

## 2. Creating Your First Project

Use the `rove new` command to scaffold a standard project:

```bash
rove new my_first_app
cd my_first_app
```

Your project directory will look like this:
```text
my_first_app/
├── rove.toml              # Package configuration
├── rove.lock              # Dependency lockfile
├── .gitignore            # Git ignore rules
└── src/
    └── main.rove          # Application source code
```

---

## 3. Writing Code & In-File Tests

Open `src/main.rove` in your editor:

```rove
#target cpp

struct User {
    name: string,
    age: int,
}

fn create_user(name: string, age: int) -> User {
    return User { name: name, age: age }
}

var u = create_user("Umut", 25)
print("Created user:", u.name, "Age:", u.age)

// In-file unit test block
test "user creation verification" {
    var test_u = create_user("Admin", 30)
    assert(test_u.age == 30, "Age must match")
    assert(test_u.name == "Admin", "Name must match")
}
```

---

## 4. Validating, Running & Testing

### Fast Type-Check (Zero Build Overhead)
```bash
rove check
```
Output:
```text
[*] Checking semantics & types for: src/main.rove
[✓] Check Passed: 0 syntax or semantic errors found.
```

### Running the Application
```bash
rove run
```
Output:
```text
[*] Running [cpp]: src/main.rove
Created user: Umut Age: 25
```

### Executing In-File Unit Tests
```bash
rove test src/main.rove
```

---

## 5. Compiling a Native Release Binary

To compile an optimized, self-contained native executable:

```bash
rove build --target cpp
```

Your executable will be available at `build/cpp/main.exe` and can be distributed to other machines without requiring Python or Node.js.
