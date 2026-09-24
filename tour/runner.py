# -*- coding: utf-8 -*-
"""
Tour of Rove - Compilation & Test Runner
Executes native Rove compiler checks, builds, runs, and tests.
"""

import os
import re
import sys
import time
import tempfile
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class TestResult:
    success: bool
    output: str
    error: str
    duration_ms: float


class RoveRunner:
    def __init__(self, repo_dir: Optional[str] = None):
        self.repo_dir = repo_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.rovec_exe = self._find_rovec()
        self.cli_py = os.path.join(self.repo_dir, "src", "cli.py")
        self.python_exe = sys.executable

    def _find_rovec(self) -> str:
        """Find the native rovec.exe compiler."""
        # 1. User .rove bin
        user_rovec = os.path.expanduser(r"~\.rove\bin\rovec.exe")
        if os.path.isfile(user_rovec):
            return user_rovec

        # 2. Repo build or bin
        repo_rovec = os.path.join(self.repo_dir, "bin", "rovec.exe")
        if os.path.isfile(repo_rovec):
            return repo_rovec

        repo_build_rovec = os.path.join(self.repo_dir, "build", "native", "rovec.exe")
        if os.path.isfile(repo_build_rovec):
            return repo_build_rovec

        # 3. Path
        import shutil
        found = shutil.which("rovec")
        if found:
            return found

        return "rovec"

    def check(self, file_path: str) -> TestResult:
        """Run fast static type and syntax check using Rove canonical compiler."""
        t0 = time.perf_counter()
        abs_path = os.path.abspath(file_path)

        if not os.path.isfile(abs_path):
            return TestResult(False, "", f"File not found: {file_path}", 0.0)

        # 1. Native in-process compiler check (blazing fast ~5ms, supports all language features)
        try:
            if self.repo_dir not in sys.path:
                sys.path.insert(0, self.repo_dir)
            from src.api import RoveCompiler
            compiler = RoveCompiler(os.path.dirname(abs_path))
            result = compiler.check_file(abs_path)
            dur = (time.perf_counter() - t0) * 1000
            if result.success:
                return TestResult(True, "ROVE_CHECK_OK", "", dur)
            else:
                rendered = "\n".join(d.rendered for d in result.diagnostics)
                return TestResult(False, "", rendered or "Semantic or syntax error found", dur)
        except Exception:
            pass

        # 2. Fallback to rovec check
        try:
            proc = subprocess.run(
                [self.rovec_exe, "check", abs_path],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=self.repo_dir
            )
            dur = (time.perf_counter() - t0) * 1000
            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()

            if proc.returncode == 0 and "ROVE_CHECK_OK" in stdout:
                return TestResult(True, stdout, "", dur)
            else:
                err_msg = stdout or stderr or "Unknown compiler check failure"
                return TestResult(False, "", err_msg, dur)
        except subprocess.TimeoutExpired:
            return TestResult(False, "", "Compiler check timed out after 10 seconds", 10000.0)
        except Exception as e:
            return TestResult(False, "", str(e), 0.0)

    def run_file(self, file_path: str, native: bool = False) -> TestResult:
        """Compile and execute a Rove program."""
        t0 = time.perf_counter()
        abs_path = os.path.abspath(file_path)

        # Fast check first
        check_res = self.check(abs_path)
        if not check_res.success:
            return check_res

        if native:
            # Native C++ compilation
            with tempfile.TemporaryDirectory() as tmpdir:
                out_exe = os.path.join(tmpdir, "tour_exec.exe")
                try:
                    c_proc = subprocess.run(
                        [self.rovec_exe, "compile", abs_path, "-o", out_exe],
                        capture_output=True,
                        text=True,
                        timeout=20,
                        cwd=self.repo_dir
                    )
                    if c_proc.returncode == 0 and os.path.isfile(out_exe):
                        r_proc = subprocess.run(
                            [out_exe],
                            capture_output=True,
                            text=True,
                            timeout=10,
                            cwd=os.path.dirname(abs_path)
                        )
                        dur = (time.perf_counter() - t0) * 1000
                        if r_proc.returncode == 0:
                            return TestResult(True, r_proc.stdout.strip(), "", dur)
                        else:
                            err = r_proc.stderr.strip() or r_proc.stdout.strip()
                            return TestResult(False, r_proc.stdout.strip(), err, dur)
                except Exception:
                    pass

        # Fast execution via CLI target python
        return self._run_via_cli_py(abs_path, t0, target="python")

    def _run_via_cli_py(self, abs_path: str, t0: float, target: str = "python") -> TestResult:
        """Execute via src/cli.py run --target <target>."""
        try:
            cmd = [self.python_exe, self.cli_py, "run", abs_path, "--target", target]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
                cwd=self.repo_dir
            )
            dur = (time.perf_counter() - t0) * 1000
            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()

            # Clean internal CLI status banners
            cleaned_lines = []
            ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
            for line in stdout.splitlines():
                plain_line = ansi_escape.sub("", line)
                if not plain_line.startswith("[*] Target") and not plain_line.startswith("[*] Transpiled") and not plain_line.startswith("[OK] Compiled") and not plain_line.startswith("-----"):
                    cleaned_lines.append(line)
            clean_out = "\n".join(cleaned_lines).strip()

            if proc.returncode == 0:
                return TestResult(True, clean_out, "", dur)
            else:
                return TestResult(False, clean_out, stderr or clean_out or "Execution failed", dur)
        except Exception as e:
            return TestResult(False, "", str(e), 0.0)

    def test_file(self, file_path: str) -> TestResult:
        """Run in-file tests using Rove test runner."""
        t0 = time.perf_counter()
        abs_path = os.path.abspath(file_path)

        # Fast check first
        check_res = self.check(abs_path)
        if not check_res.success:
            return check_res

        try:
            proc = subprocess.run(
                [self.python_exe, self.cli_py, "test", abs_path],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=self.repo_dir
            )
            dur = (time.perf_counter() - t0) * 1000
            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()

            if proc.returncode == 0:
                # Filter out test harness banners
                out_lines = [l for l in stdout.splitlines() if "[PASS]" in l or not l.startswith("[*]")]
                return TestResult(True, "\n".join(out_lines).strip(), "", dur)
            else:
                # Extract assertion error
                err = stderr or stdout
                for line in err.splitlines():
                    if "AssertionError" in line:
                        err = line.strip()
                        break
                return TestResult(False, stdout, err, dur)
        except Exception as e:
            return TestResult(False, "", str(e), 0.0)

    def verify(self, exercise: dict) -> TestResult:
        """Verify an exercise based on its declared mode."""
        mode = exercise.get("mode", "check")
        path = exercise["path"]
        if not os.path.isabs(path):
            path = os.path.join(self.repo_dir, "tour", path)

        if mode == "run":
            return self.run_file(path)
        elif mode == "test":
            return self.test_file(path)
        else:
            return self.check(path)
