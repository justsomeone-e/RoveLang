# Rove Native CLI Example: File & Process Inspector

This example demonstrates how to build a native CLI tool using Rove and the standard library:
- `std/path`: Portable path operations (`path_join`, `path_basename`, `path_dirname`, `path_ext`, `path_is_abs`).
- `std/process`: Fallible process information and environment inspection (`process_get_pid`, `process_get_cwd`, `process_get_env`) returning `Result<T, E>`.
- `std/str`: String operations (`str_split`, `str_join`, `str_trim`).

## How to Compile & Run

```bash
# Compile to native C++ executable
python -m src.cli build examples/file_inspector/file_inspector.rove -o build/file_inspector.exe

# Run the executable
./build/file_inspector.exe src
```
