#!/usr/bin/env python3
"""
Rove Typed HIR -> MIR bottleneck benchmark.

Run from the Rove repository root:

    python rove_hir_mir_benchmark.py --repetitions 25

Optional GC comparison:

    python rove_hir_mir_benchmark.py --repetitions 25 --gc-mode both

What it measures:
- Current normal Python Stage-0 compile path (compile_source -> HIR -> current backend)
- Isolated HIR -> MIR lowering
- MIR verification only
- Estimated current-pipeline + MIR overhead
- Same measurements with Python cyclic GC disabled, if requested

Important:
- lower_hir_to_mir() ALREADY calls verify_mir() internally in the current Rove tree.
- Therefore "HIR -> MIR" is the real current lowering cost including its built-in verification.
- "MIR verify only" is measured separately only to show verifier cost if run again.
"""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "tests" / "fixtures" / "compiler_benchmark.json"


def median_ms(values):
    return statistics.median(values)


def p95_ms(values):
    if len(values) < 2:
        return values[0]
    xs = sorted(values)
    idx = min(len(xs) - 1, max(0, round((len(xs) - 1) * 0.95)))
    return xs[idx]


def timed_call(fn):
    start = time.perf_counter_ns()
    value = fn()
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
    return value, elapsed_ms


def set_gc_mode(mode: str):
    if mode == "normal":
        gc.enable()
    elif mode == "disabled":
        gc.disable()
    else:
        raise ValueError(mode)


def benchmark_source(source_path: Path, target: str, repetitions: int, gc_mode: str):
    from src import api
    from src.mir import lower_hir_to_mir, verify_mir

    set_gc_mode(gc_mode)

    source = source_path.read_text(encoding="utf-8")
    compiler = api.RoveCompiler(str(source_path.parent))

    # Warm normal pipeline.
    warm = compiler.compile_source(source, filename=str(source_path), target=target)
    if not warm.success or warm.hir is None:
        raise RuntimeError(f"Warmup failed for {source_path}: {warm.diagnostics}")

    # Warm MIR path too.
    warm_mir = lower_hir_to_mir(warm.hir)
    verify_mir(warm_mir)

    normal_compile_ms = []
    hir_to_mir_ms = []
    verify_again_ms = []

    for _ in range(repetitions):
        # 1. Current real/normal Stage-0 compile path.
        result, elapsed = timed_call(
            lambda: compiler.compile_source(
                source,
                filename=str(source_path),
                target=target,
            )
        )
        if not result.success or result.hir is None:
            raise RuntimeError(f"Compile failed for {source_path}: {result.diagnostics}")
        normal_compile_ms.append(elapsed)

        # 2. Isolated HIR -> MIR path from the HIR we just produced.
        # NOTE: current lower_hir_to_mir() includes verify_mir() internally.
        mir, elapsed = timed_call(lambda: lower_hir_to_mir(result.hir))
        hir_to_mir_ms.append(elapsed)

        # 3. Measure an extra verifier pass separately.
        _, elapsed = timed_call(lambda: verify_mir(mir))
        verify_again_ms.append(elapsed)

    normal_med = median_ms(normal_compile_ms)
    mir_med = median_ms(hir_to_mir_ms)
    verify_med = median_ms(verify_again_ms)

    combined = normal_med + mir_med
    overhead_pct = (mir_med / normal_med * 100.0) if normal_med else 0.0
    combined_growth_pct = ((combined / normal_med) - 1.0) * 100.0 if normal_med else 0.0

    return {
        "source": source_path.relative_to(ROOT).as_posix(),
        "gcMode": gc_mode,
        "repetitions": repetitions,
        "normalCompile": {
            "medianMs": normal_med,
            "p95Ms": p95_ms(normal_compile_ms),
            "runsMs": normal_compile_ms,
        },
        "hirToMirIncludingInternalVerify": {
            "medianMs": mir_med,
            "p95Ms": p95_ms(hir_to_mir_ms),
            "runsMs": hir_to_mir_ms,
        },
        "extraMirVerifyOnly": {
            "medianMs": verify_med,
            "p95Ms": p95_ms(verify_again_ms),
            "runsMs": verify_again_ms,
        },
        "derived": {
            "mirCostAsPercentOfCurrentCompile": overhead_pct,
            "currentPlusMirMedianMs": combined,
            "currentPlusMirGrowthPercent": combined_growth_pct,
        },
    }


def aggregate(results):
    normal = [r["normalCompile"]["medianMs"] for r in results]
    mir = [r["hirToMirIncludingInternalVerify"]["medianMs"] for r in results]
    verify = [r["extraMirVerifyOnly"]["medianMs"] for r in results]

    normal_sum = sum(normal)
    mir_sum = sum(mir)
    verify_sum = sum(verify)

    return {
        "normalCompileCorpusMedianSumMs": normal_sum,
        "hirToMirCorpusMedianSumMs": mir_sum,
        "extraMirVerifyCorpusMedianSumMs": verify_sum,
        "mirCostAsPercentOfNormalCorpus": (mir_sum / normal_sum * 100.0) if normal_sum else 0.0,
        "normalPlusMirCorpusMs": normal_sum + mir_sum,
        "normalPlusMirGrowthPercent": (mir_sum / normal_sum * 100.0) if normal_sum else 0.0,
    }


def print_table(mode_results):
    print()
    print("Rove HIR/MIR bottleneck benchmark")
    print("=" * 96)
    print(
        f"{'source':38} {'GC':9} {'normal ms':>11} {'HIR->MIR ms':>12} "
        f"{'verify ms':>10} {'MIR/current':>12}"
    )
    print("-" * 96)

    for r in mode_results:
        print(
            f"{r['source'][-38:]:38} "
            f"{r['gcMode']:9} "
            f"{r['normalCompile']['medianMs']:11.3f} "
            f"{r['hirToMirIncludingInternalVerify']['medianMs']:12.3f} "
            f"{r['extraMirVerifyOnly']['medianMs']:10.3f} "
            f"{r['derived']['mirCostAsPercentOfCurrentCompile']:11.1f}%"
        )

    print("-" * 96)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=25)
    parser.add_argument(
        "--gc-mode",
        choices=("normal", "disabled", "both"),
        default="both",
        help="Compare normal CPython GC behavior with cyclic GC disabled.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "build" / "hir-mir-benchmark.json",
    )
    args = parser.parse_args()

    if not 3 <= args.repetitions <= 500:
        parser.error("--repetitions must be between 3 and 500")

    if not CORPUS.exists():
        raise SystemExit(
            f"Run this script from the Rove repository root. Missing: {CORPUS}"
        )

    manifest = json.loads(CORPUS.read_text(encoding="utf-8"))
    target = manifest.get("target", "cpp")
    sources = [(ROOT / p).resolve() for p in manifest["sources"]]

    modes = ["normal", "disabled"] if args.gc_mode == "both" else [args.gc_mode]

    all_results = []
    mode_summaries = {}

    original_gc = gc.isenabled()
    try:
        for mode in modes:
            results = [
                benchmark_source(path, target, args.repetitions, mode)
                for path in sources
            ]
            all_results.extend(results)
            mode_summaries[mode] = aggregate(results)
            print_table(results)

            s = mode_summaries[mode]
            print(
                f"{mode}: corpus normal={s['normalCompileCorpusMedianSumMs']:.3f} ms, "
                f"HIR->MIR={s['hirToMirCorpusMedianSumMs']:.3f} ms, "
                f"MIR/current={s['mirCostAsPercentOfNormalCorpus']:.1f}%"
            )
    finally:
        if original_gc:
            gc.enable()
        else:
            gc.disable()

    comparison = None
    if "normal" in mode_summaries and "disabled" in mode_summaries:
        n = mode_summaries["normal"]["normalCompileCorpusMedianSumMs"]
        d = mode_summaries["disabled"]["normalCompileCorpusMedianSumMs"]
        nm = mode_summaries["normal"]["hirToMirCorpusMedianSumMs"]
        dm = mode_summaries["disabled"]["hirToMirCorpusMedianSumMs"]
        comparison = {
            "normalCompileGcDisabledSpeedupPercent":
                ((n - d) / n * 100.0) if n else 0.0,
            "hirToMirGcDisabledSpeedupPercent":
                ((nm - dm) / nm * 100.0) if nm else 0.0,
        }

    report = {
        "schemaVersion": 1,
        "purpose": "Measure Python Stage-0 current compile path versus Typed HIR -> MIR lowering cost.",
        "python": sys.version,
        "target": target,
        "notes": [
            "Uses the existing tests/fixtures/compiler_benchmark.json corpus.",
            "Normal compile uses RoveCompiler.compile_source().",
            "HIR->MIR uses src.mir.lower_hir_to_mir().",
            "Current lower_hir_to_mir() already invokes verify_mir() internally.",
            "The separate verify-only measurement is intentionally an extra verifier pass.",
            "GC-disabled mode disables CPython cyclic GC only; reference counting remains active.",
            "This is a Python Stage-0 benchmark, not native rovec performance.",
        ],
        "summaries": mode_summaries,
        "gcComparison": comparison,
        "results": all_results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print()
    print(f"Wrote: {args.output}")

    if comparison:
        print(
            f"GC disabled speedup: normal compile "
            f"{comparison['normalCompileGcDisabledSpeedupPercent']:.1f}% | "
            f"HIR->MIR {comparison['hirToMirGcDisabledSpeedupPercent']:.1f}%"
        )


if __name__ == "__main__":
    main()
