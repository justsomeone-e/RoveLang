# Rove Host Embedding Example

This example demonstrates how a single Rove module (`transformer.rove`) can be embedded and consumed by both **Node.js (WebAssembly / ES2022)** and **Python 3** hosts.

## Architecture

- **`transformer.rove`**: High-performance pure data transformation logic written once in Rove:
  - `sum_floats(data: Array<float>) -> float`: Computes vector sums across host boundaries.
  - `mutate_add_in_place(data: Array<int>, offset: int) -> int`: Mutates memory in-place without extraneous reallocations.
  - `format_summary(title: string) -> string`: Interoperable UTF-8 string generation.
- **Node.js Host (`host_node.mjs`)**: Consumes the WebAssembly binary and ES module generated via `rove bundle --package`.
- **Python Host (`host_python.py`)**: Consumes the Python module generated via `rove build --target python`.

## Running the Examples

### 1. Node.js (WASM) Host

First, bundle the Rove module into WebAssembly:
```bash
rove bundle transformer.rove -o bundle --package
```

Then run the Node.js host:
```bash
node host_node.mjs
```

### 2. Python Host

Run the Python host script directly (which builds and imports the module):
```bash
python host_python.py
```
