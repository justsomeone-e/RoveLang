# -*- coding: utf-8 -*-
"""
Verification Test Harness for Tour of Rove
Autonomously tests every manifest exercise and its reference solution.
"""

import os
import sys
import json
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from runner import RoveRunner


def verify_all():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.abspath(os.path.join(base_dir, ".."))
    exercises_file = os.path.join(base_dir, "exercises.json")

    with open(exercises_file, "r", encoding="utf-8") as f:
        exercises = json.load(f)

    runner = RoveRunner(repo_dir=repo_dir)

    print("=" * 70)
    print(f"Tour of Rove - Autonomous Verification Suite ({len(exercises)} Exercises)")
    print("=" * 70)

    all_passed = True
    results = []

    for idx, ex in enumerate(exercises, 1):
        ex_id = ex["id"]
        mode = ex["mode"]
        ex_path = os.path.join(base_dir, ex["path"])
        sol_path = os.path.join(base_dir, ex["solution"])

        # 1. Test Exercise (Unsolved state)
        ex_dict = {"path": ex_path, "mode": mode}
        t0 = time.time()
        ex_res = runner.verify(ex_dict)
        ex_dur = (time.time() - t0) * 1000

        # In intro01, exercise is pre-solved. For others, it must fail.
        expected_fail = (ex_id != "intro01")
        if expected_fail and ex_res.success:
            print(f"[{idx:02d}/{len(exercises)}] ❌ {ex_id}: Expected unsolved exercise to fail, but it passed!")
            all_passed = False
            results.append((ex_id, False, "Unsolved passed unexpectedly"))
            continue
        elif not expected_fail and not ex_res.success:
            print(f"[{idx:02d}/{len(exercises)}] ❌ {ex_id}: Pre-solved exercise failed: {ex_res.error}")
            all_passed = False
            results.append((ex_id, False, f"Intro failed: {ex_res.error}"))
            continue

        # 2. Test Solution
        sol_dict = {"path": sol_path, "mode": mode}
        t0 = time.time()
        sol_res = runner.verify(sol_dict)
        sol_dur = (time.time() - t0) * 1000

        if not sol_res.success:
            print(f"[{idx:02d}/{len(exercises)}] ❌ {ex_id} SOLUTION FAILED ({mode}):", flush=True)
            print(f"    Error: {sol_res.error}", flush=True)
            all_passed = False
            results.append((ex_id, False, f"Solution failed: {sol_res.error}"))
        else:
            status = "✅ PASS"
            print(f"[{idx:02d}/{len(exercises)}] {status} {ex_id:<14} (Unsolved: FAIL as expected | Solved: OK in {sol_dur:.0f}ms)", flush=True)
            results.append((ex_id, True, "OK"))

    print("=" * 70)
    passed_count = sum(1 for r in results if r[1])
    print(f"Verification Summary: {passed_count}/{len(exercises)} passed.")
    if all_passed:
        print(f"🎉 ALL {len(exercises)} EXERCISES AND SOLUTIONS VERIFIED 100% CLEANLY!")
    else:
        print("⚠️ Some exercises or solutions failed verification.")
    print("=" * 70)
    return all_passed


if __name__ == "__main__":
    success = verify_all()
    sys.exit(0 if success else 1)
