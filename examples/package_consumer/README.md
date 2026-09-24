# Rove Package & Foreign Binding Consumer Example

This example demonstrates how a Rove project:
1. Declares and resolves a local package dependency (`stats_core`) via `rove.toml`.
2. Generates and verifies a deterministic lockfile (`rove.lock`) with cryptographic SHA256 integrity checksums.
3. Consumes exported algorithms and functions from the package.
4. Consumes foreign C++ platform bindings (`std::filesystem`) with type safety.

## Directory Structure

```
package_consumer/
├── rove.toml               # Project manifest declaring stats_core dependency
├── rove.lock               # Deterministic lockfile with package checksums
├── README.md              # Documentation and execution guide
├── packages/
│   └── stats_core/        # Local package dependency
│       ├── rove.toml       # stats_core manifest
│       └── src/
│           └── stats.rove  # stats_core algorithms (clamp, sum_ints, max_int)
└── src/
    └── main.rove           # Application consuming package and foreign bindings
```

## Running the Example

### Inspect Manifest & Dependencies
```bash
rove pkg
```

### Verify Deterministic Lockfile
```bash
rove install
```

### Compile & Execute
```bash
rove run src/main.rove
```
