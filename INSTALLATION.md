# 📦 Rove Installation Guide

This guide covers the Rove source checkout on Windows, Linux, and macOS.
Published v5 binaries still use the Nyx names; a tagged Rove release is not
available yet.

---

## 1. Prerequisites

The locally built `rovec` performs native `check`, `emit-cpp`, `compile`, and
target discovery without Python. The unified `rove` command uses Python 3.10+
for orchestration features such as the REPL, formatter, package manager, and
language server. To compile native executables (`cpp`), install a modern C++20
compiler (`clang++`, `g++`, or MSVC `cl`).

| Platform | Recommended Toolchain | Quick Install Command |
| :--- | :--- | :--- |
| **Windows** | LLVM Clang or LLVM-MinGW | `winget install LLVM.LLVM` or `winget install MartinStorsjo.LLVM-MinGW.UCRT` |
| **Ubuntu / Debian** | Clang 16+ or GCC 12+ | `sudo apt update && sudo apt install -y clang nodejs` |
| **Fedora / RHEL** | Clang or GCC | `sudo dnf install -y clang nodejs` |
| **macOS** | Apple Clang (Xcode CLI) | `xcode-select --install` or `brew install llvm` |

---

## 2. Install from this checkout

### Windows (PowerShell)
Run in an elevated or standard PowerShell terminal from the repository root:
```powershell
.\install.ps1
```
This installs to `~/.rove` and appends `~/.rove/bin` to your User `PATH`.
The installer creates `rove.cmd` as the unified Windows command alongside
the native `rovec.exe` compiler.

The VS Code extension is optional. If PowerShell blocks an `npm.ps1` shim, the
installer prefers `npm.cmd`/`npm.exe`; an editor-install failure no longer
prevents the core compiler from being installed.

### Linux / macOS (Bash)
```bash
./install.sh
```

---

## 3. Manual Installation (From Source)

1. Clone the repository:
   ```bash
   git clone --branch rove/compiler-architecture-and-migration https://github.com/justsomeone-e/RoveLang.git
   cd RoveLang
   ```

2. Verify host diagnostics:
   * **Windows**:
     ```powershell
     python src/cli.py doctor
     ```
   * **Linux / macOS**:
     ```bash
     python3 src/cli.py doctor
     ```

3. Add Rove to your `PATH`:
   * **Windows**: Add `%USERPROFILE%\.rove\bin` to your User `PATH`.
   * **Linux / macOS**: Add `export PATH="$PATH:$HOME/.rove/bin"` in `~/.bashrc` or `~/.zshrc`.

---

## 4. Verifying Installation

Run:
```bash
rove doctor
```
Output should indicate detected compilers and runtimes with green checkmarks `[✓]`.
