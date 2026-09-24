"""Fixed-corpus stage-0 compiler measurements; never a native compiler claim."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests/fixtures/compiler_benchmark.json"


def peak_rss():
    if os.name == "nt":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                    "PagefileUsage", "PeakPagefileUsage",
                )
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.PeakWorkingSetSize
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


def measure(source_path: Path, target: str, repetitions: int):
    from src import api
    from src.core.lexer import Lexer
    from src.core.parser import Parser

    source = source_path.read_text(encoding="utf-8")
    compiler = api.RoveCompiler(str(source_path.parent))

    def compile_once():
        result = compiler.compile_source(source, filename=str(source_path), target=target)
        if not result.success:
            raise RuntimeError(str(result.diagnostics))
        return result

    compile_once()
    records = []
    for _ in range(repetitions):
        stages = {name: 0.0 for name in ("lexer", "parser", "type_checker", "hir_lowering", "hir_verify", "hir_passes", "codegen")}

        def timed(name, function):
            def run(*args, **kwargs):
                start = time.perf_counter_ns()
                try:
                    return function(*args, **kwargs)
                finally:
                    stages[name] += (time.perf_counter_ns() - start) / 1e6
            return run

        hooks = ((Lexer, "tokenize", "lexer"), (Parser, "parse", "parser"),
                 (api.TypeChecker, "check", "type_checker"), (api, "lower_to_hir", "hir_lowering"),
                 (api, "verify_hir", "hir_verify"), (api, "optimize_hir", "hir_passes"),
                 (api.RoveCompiler, "_emit", "codegen"))
        with ExitStack() as stack:
            for owner, name, stage in hooks:
                wrapper = timed(stage, getattr(owner, name))
                if isinstance(vars(owner).get(name), staticmethod):
                    wrapper = staticmethod(wrapper)
                stack.enter_context(patch.object(owner, name, wrapper))
            start = time.perf_counter_ns()
            result = compile_once()
            stages["total"] = (time.perf_counter_ns() - start) / 1e6
        records.append(stages)
    # Keep allocation tracing out of timing runs.
    tracemalloc.start()
    compile_once()
    _, peak_python = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "source": source_path.relative_to(ROOT).as_posix(),
        "sourceSha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "artifactSha256": hashlib.sha256(result.artifact.content.encode()).hexdigest(),
        "runsMs": records,
        "medianMs": {stage: statistics.median(row[stage] for row in records) for stage in records[0]},
        "peakPythonAllocatedBytes": peak_python,
        "peakProcessRssBytes": peak_rss(),
    }


def measure_invalidation(corpus_dir: Path, repetitions: int) -> dict:
    from src import api
    main_file = corpus_dir / "main.rove"
    leaf_file = corpus_dir / "core_types.rove"
    leaf_content = leaf_file.read_text(encoding="utf-8")

    cold_times = []
    for _ in range(repetitions):
        compiler = api.RoveCompiler(str(corpus_dir))
        start = time.perf_counter_ns()
        res = compiler.compile_file(str(main_file), target="cpp")
        elapsed = (time.perf_counter_ns() - start) / 1e6
        if not res.success:
            raise RuntimeError(str(res.diagnostics))
        cold_times.append(elapsed)

    warm_times = []
    compiler = api.RoveCompiler(str(corpus_dir))
    compiler.compile_file(str(main_file), target="cpp")  # warmup
    for _ in range(repetitions):
        start = time.perf_counter_ns()
        res = compiler.compile_file(str(main_file), target="cpp")
        elapsed = (time.perf_counter_ns() - start) / 1e6
        if not res.success:
            raise RuntimeError(str(res.diagnostics))
        warm_times.append(elapsed)

    leaf_inval_times = []
    try:
        for i in range(repetitions):
            leaf_file.write_text(leaf_content + f"\n// invalidation test {i}\n", encoding="utf-8")
            start = time.perf_counter_ns()
            c = api.RoveCompiler(str(corpus_dir))
            res = c.compile_file(str(main_file), target="cpp")
            elapsed = (time.perf_counter_ns() - start) / 1e6
            if not res.success:
                raise RuntimeError(str(res.diagnostics))
            leaf_inval_times.append(elapsed)
    finally:
        leaf_file.write_text(leaf_content, encoding="utf-8")

    return {
        "schemaVersion": 1,
        "corpus": "import_invalidation",
        "target": "cpp",
        "scenarios": {
            "cold_compile_median_ms": statistics.median(cold_times),
            "warm_compile_median_ms": statistics.median(warm_times),
            "leaf_invalidated_median_ms": statistics.median(leaf_inval_times),
        },
        "runs": {
            "cold": cold_times,
            "warm": warm_times,
            "leaf_invalidated": leaf_inval_times,
        },
        "notes": [
            "Baseline measurement of import dependency graph recompilation.",
            "Demonstrates cache invalidation characteristics across leaf/middle/root dependencies.",
            "Policy: Do not add ad-hoc caching mechanisms without measured baseline proof.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/compiler-benchmark.json")
    parser.add_argument("--invalidation-output", type=Path, default=ROOT / "build/import-invalidation-benchmark.json")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--worker", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--invalidation", action="store_true", help="Measure import invalidation corpus")
    options = parser.parse_args()
    if not 1 <= options.repetitions <= 100:
        parser.error("--repetitions must be between 1 and 100")

    if options.invalidation:
        inval_corpus = ROOT / "tests/fixtures/import_invalidation"
        inval_res = measure_invalidation(inval_corpus, options.repetitions)
        options.invalidation_output.parent.mkdir(parents=True, exist_ok=True)
        options.invalidation_output.write_text(json.dumps(inval_res, indent=2) + "\n", encoding="utf-8")
        print(f"Measured import invalidation corpus: {options.invalidation_output}")
        return

    manifest = json.loads(CORPUS.read_text())
    if options.worker is not None:
        source = (ROOT / manifest["sources"][options.worker]).resolve()
        source.relative_to(ROOT)
        print(json.dumps(measure(source, manifest["target"], options.repetitions)))
        return
    results = []
    for index in range(len(manifest["sources"])):
        process = subprocess.run(
            [sys.executable, "-m", "src.toolchain.compiler_benchmark", "--worker", str(index),
             "--repetitions", str(options.repetitions)], cwd=ROOT, capture_output=True,
            text=True, encoding="utf-8", timeout=300,
        )
        if process.returncode:
            raise RuntimeError(process.stderr or process.stdout)
        results.append(json.loads(process.stdout))
    report = {
        "schemaVersion": 1, "engine": "Python stage-0 RoveCompiler API", "target": manifest["target"],
        "python": sys.version, "platform": platform.platform(), "machine": platform.machine(),
        "compilerVersion": (ROOT / "VERSION").read_text().strip(),
        "corpusSha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
        "notes": ["One warmup, fresh subprocess per corpus entry; file read excluded from timings.",
                  "Stage times are instrumented wall times; total includes module resolution and orchestration.",
                  "Peak RSS is the worker lifetime high-water mark, including imports and allocation tracing.",
                  "Python allocation peak comes from a separate untimed compilation.",
                  "No target executable is built or timed; not a native rovec benchmark or cache speedup claim."],
        "results": results,
    }
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Measured {len(results)} corpus entries: {options.output}")


if __name__ == "__main__":
    main()
