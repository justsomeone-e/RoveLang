# Migrating from Nyx to Rove

Rove is the new public name of the Nyx language and toolchain. The language
semantics do not change merely because of the rename.

## Canonical names

| Previous name | Canonical Rove name |
| --- | --- |
| `program.nyx` | `program.rove` |
| `nyx.toml` | `rove.toml` |
| `nyx.lock` | `rove.lock` |
| `nyx` | `rove` |
| `nyxc` | `rovec` |
| `NyxCompiler` | `RoveCompiler` |
| `createNyxModule` | `createRoveModule` |
| `initNyxModule` | `initRoveModule` |

## Compatibility

The old source extension, manifest and lockfile names, CLI launchers, Python API
name, and JavaScript bundle entry points remain available during the transition.
Rove prefers the canonical name when both old and new project files exist.

The WebAssembly symbols beginning with `__nyx_` and the import namespace
`nyx_host_v1` are part of Bundle ABI v1. They intentionally retain their names;
renaming them in place would break existing hosts and compiled modules. A future
ABI revision may introduce Rove-native symbol names under a new versioned
contract.

## Project migration

1. Rename source files from `.nyx` to `.rove`.
2. Rename `nyx.toml` and `nyx.lock` to `rove.toml` and `rove.lock`.
3. Replace user-facing `nyx` commands with `rove` and `nyxc` with `rovec`.
4. For WebAssembly hosts, adopt `initRoveModule` and `createRoveModule`; the old
   exports remain aliases.

No source-language rewrite is required.
