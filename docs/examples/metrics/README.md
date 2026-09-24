# Latency reports with one Rove module

`metrics.rove` contains the shared calculations. The website passes measured
milliseconds into its generated WASM wrapper and renders a downloadable report.
JavaScript/Python hosts import the same source compiled for their runtime.
All commands below run from the repository root.

## Native CLI

```sh
python src/cli.py build examples/metrics/cli.rove --target cpp
./build/cpp/cli.exe 42 95 380
```

On Windows PowerShell use `./build/cpp/cli.exe`; the current CLI build also names
its native artifact `.exe` on Unix. A C++20 compiler is needed for the build.
Invoke the resulting executable directly: `rove run` does not forward program
arguments. This application accepts 1–10,000 integer samples in the range
0–1,000,000 ms; the budget is 200 ms. Invalid input prints an error without a
report. Its current error path returns normally rather than a nonzero exit code.

Expected result for `42 95 380`:

```text
samples: 3
average_ms: 172.33333333333334
minimum_ms: 42
maximum_ms: 380
over_200_ms: 1
```

## Node.js integration

```sh
python src/cli.py build examples/metrics/metrics.rove --target js --esm
node examples/metrics/use_metrics.mjs build/js/metrics.mjs
```

Rove `int` results use BigInt on JavaScript; the host converts bounded counts
to Number for JSON. Float results are numbers.

## Python integration

```sh
python src/cli.py build examples/metrics/metrics.rove --target python
python examples/metrics/use_metrics.py build/python/metrics.py
```

Both integrations assert the result before printing JSON.

## Browser / WASM

```sh
python -m src.toolchain.docs_site
python -m http.server 8080 --directory docs
```

Open `http://localhost:8080`. The input accepts nonnegative finite decimal
milliseconds. The shared module assumes validated samples; empty arrays return
zero. `count_over` excludes values equal to the budget. Distribution bins use
inclusive lower and exclusive upper bounds. Hosts must not supply negative,
NaN, infinite or out-of-contract values.

Build and runtime regression verification:

```sh
python tests/docs_site_suite.py
```
