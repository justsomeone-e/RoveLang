"""Runtime and diagnostic coverage for ecosystem foreign imports."""

from __future__ import annotations

import os
import json
import shutil
import subprocess
import sys
import tempfile

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.api import NyxCompiler
from src.codegen.cpp_toolchain import CppToolchain


def _compile(source: str, target: str, base_dir: str = ROOT_DIR):
    return NyxCompiler(base_dir).compile_source(
        source,
        target=target,
        filename=os.path.join(base_dir, f"foreign-{target}.rove"),
    )


def run_foreign_import_suite() -> bool:
    cases = (
        (
            "cpp",
            '#target cpp\nimport cpp "std::filesystem" from "<filesystem>" as fs\nfn main() { var path = fs.current_path(); print(path.filename().string()) }\nmain()\n',
            "cpp",
        ),
        (
            "js",
            '#target js\nimport js "node:os" as os\nprint(os.platform())\n',
            "js",
        ),
        (
            "python",
            '#target python\nimport python "platform" as platform\nprint(platform.system())\n',
            "python",
        ),
    )

    with tempfile.TemporaryDirectory(prefix="nyx_foreign_import_") as temp_dir:
        for name, source, target in cases:
            result = _compile(source, target)
            assert result.success, result.diagnostics
            assert result.artifact is not None

            if target == "cpp":
                cpp_path = os.path.join(temp_dir, "foreign.cpp")
                exe_path = os.path.join(temp_dir, "foreign.exe")
                with open(cpp_path, "w", encoding="utf-8") as handle:
                    handle.write(result.artifact.content)
                compiled, message = CppToolchain.compile_cpp(cpp_path, exe_path)
                assert compiled, message
                return_code, output = CppToolchain.run_executable(exe_path)
            elif target == "js":
                node = shutil.which("node")
                assert node is not None, "Node.js is required for JavaScript foreign import coverage"
                js_path = os.path.join(temp_dir, "foreign.js")
                with open(js_path, "w", encoding="utf-8") as handle:
                    handle.write(result.artifact.content)
                process = subprocess.run(
                    [node, js_path], capture_output=True, text=True, encoding="utf-8", errors="replace"
                )
                return_code, output = process.returncode, process.stdout + process.stderr
            else:
                py_path = os.path.join(temp_dir, "foreign.py")
                with open(py_path, "w", encoding="utf-8") as handle:
                    handle.write(result.artifact.content)
                process = subprocess.run(
                    [sys.executable, py_path], capture_output=True, text=True, encoding="utf-8", errors="replace"
                )
                return_code, output = process.returncode, process.stdout + process.stderr

            assert return_code == 0, f"{name} foreign import failed:\n{output}"
            assert output.strip(), f"{name} foreign import produced no output"

        custom_manifest = {
            "schema_version": 1,
            "modules": [
                {
                    "ecosystem": "js",
                    "module": "node:path",
                    "functions": {
                        "basename": {"params": ["string"], "returns": "string"}
                    },
                    "types": {},
                }
            ],
        }
        with open(os.path.join(temp_dir, "rove.bindings.json"), "w", encoding="utf-8") as handle:
            json.dump(custom_manifest, handle)
        custom = _compile(
            '#target js\nimport js "node:path" as path\nprint(path.basename("a/file.txt"))\n',
            "js",
            temp_dir,
        )
        assert custom.success, custom.diagnostics
        custom_path = os.path.join(temp_dir, "custom.js")
        with open(custom_path, "w", encoding="utf-8") as handle:
            handle.write(custom.artifact.content)
        custom_run = subprocess.run(
            [shutil.which("node"), custom_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert custom_run.returncode == 0 and custom_run.stdout.strip() == "file.txt"

        with open(os.path.join(temp_dir, "rove.bindings.json"), "w", encoding="utf-8") as handle:
            json.dump({"schema_version": 99, "modules": []}, handle)
        invalid_manifest = _compile(
            '#target js\nimport js "node:path" as path\n',
            "js",
            temp_dir,
        )
        assert not invalid_manifest.success
        assert any(diagnostic.code == "E1420" for diagnostic in invalid_manifest.diagnostics)

    mismatch = _compile('#target python\nimport js "node:os" as os\n', "python")
    assert not mismatch.success
    assert any(diagnostic.code == "E1411" for diagnostic in mismatch.diagnostics)

    missing_header = _compile('#target cpp\nimport cpp "std::filesystem" as fs\n', "cpp")
    assert not missing_header.success
    assert any(diagnostic.code == "E1412" for diagnostic in missing_header.diagnostics)

    unsafe_header = _compile(
        '#target cpp\nimport cpp "std::filesystem" from "<filesystem> // injected" as fs\n',
        "cpp",
    )
    assert not unsafe_header.success

    unknown_api = _compile(
        '#target cpp\nimport cpp "std::filesystem" from "<filesystem>" as fs\nfs.not_a_real_api()\n',
        "cpp",
    )
    assert not unknown_api.success
    assert any(diagnostic.code == "E2030" for diagnostic in unknown_api.diagnostics)

    wrong_argument = _compile(
        '#target js\nimport js "node:fs" as fs\nfs.readFileSync(42, "utf8")\n',
        "js",
    )
    assert not wrong_argument.success
    assert any(diagnostic.code == "E2032" for diagnostic in wrong_argument.diagnostics)

    pending = _compile('#target rust\nimport rust "std::fs" as fs\n', "rust")
    assert not pending.success
    assert any(diagnostic.code == "E1413" for diagnostic in pending.diagnostics)

    print("[PASS] C++, Node.js, and Python foreign imports plus target diagnostics")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_foreign_import_suite() else 1)
