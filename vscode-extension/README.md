# Rove Language Toolchain

The official VS Code companion for `.rove` files.

[GitHub Repository](https://github.com/justsomeone-e/RoveLang) ·
[Documentation](https://github.com/justsomeone-e/RoveLang#readme) ·
[Releases](https://github.com/justsomeone-e/RoveLang/releases) ·
[Compiler Roadmap](https://github.com/justsomeone-e/RoveLang/blob/main/docs/internals/ROADMAP_AND_BACKEND_GATES.md) ·
[Report an Issue](https://github.com/justsomeone-e/RoveLang/issues/new)

## What you get

- Syntax highlighting and canonical v4 completions
- LSP diagnostics, hover, completion, and go-to-definition
- One-click **Run**, **Build**, and **Check** commands
- Persistent integrated-terminal output, so native executables do not disappear after exit
- `Rove: Toolchain Doctor` environment diagnostics
- Direct access to the repository, documentation, releases, roadmap, and issue reporter

## Quick actions

Open the Command Palette with `Ctrl+Shift+P` (`Cmd+Shift+P` on macOS), then run:

| Command | Purpose |
| --- | --- |
| `Rove: Run Current File` | Compile and run the active source file. |
| `Rove: Build Current File` | Build without losing terminal output. |
| `Rove: Check Current File` | Parse and type-check without producing an artifact. |
| `Rove: Toolchain Doctor` | Diagnose Rove and native toolchain availability. |
| `Rove: Open GitHub Repository` | Open the Rove source repository. |
| `Rove: Open Documentation` | Open the language and toolchain documentation. |
| `Rove: Open Releases` | View published versions and release notes. |
| `Rove: Open Compiler Roadmap` | Inspect backend maturity and RC gates. |
| `Rove: Report an Issue` | Open a new GitHub issue. |

## Compiler discovery

By default, the extension prefers the canonical Rove installation at
`~/.rove/bin/rove` (`rove.cmd` on Windows) before searching `PATH`. Set
`rove.server.path` when you deliberately want to use another compiler build.

## Target requirements

| Target | Host requirement |
| --- | --- |
| `cpp` | Clang++, GCC/G++, or MSVC `cl` with C++20 support. |
| `js` | Node.js. |
| `python` | Python 3. |

Expose the native compiler on `PATH` or set `ROVE_CXX`, then run
`Rove: Toolchain Doctor` to verify the environment.

## Local installation

Open the generated `.vsix` file in VS Code, or run:

```text
code --install-extension rove-language-support-<version>.vsix
```

No marketplace download is required for a local package. After upgrading the
extension or compiler, run **Developer: Reload Window** once so VS Code restarts
the Rove language server with the new files.

The older Nyx extension does not register `.rove` files. Install this Rove VSIX
to make `.rove` use the Rove grammar and completion provider. For diagnostics,
hover, and go-to-definition, install the `rove` CLI or set `rove.server.path`.
