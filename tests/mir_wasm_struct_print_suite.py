"""Executable WASI stdout parity for the bounded MIR struct display slice."""

from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api import RoveCompiler
from src.mir import (
    MIRInterpreter,
    MIRLegalizationError,
    collect_legalization_issues,
    emit_legalized_wasm,
    emit_legalized_wat,
    lower_hir_to_mir,
)


def _lower(source: str, filename: str):
    checked = RoveCompiler(str(ROOT)).check_source(source, filename=filename, target="cpp")
    assert checked.success and checked.hir is not None, checked.diagnostics
    return lower_hir_to_mir(checked.hir)


def _run_wasi(wasm: bytes, export: str, *, partial: bool = False) -> str:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for executable Wasm parity"
    with tempfile.TemporaryDirectory(prefix="rove_mir_wasi_print_") as temporary:
        wasm_path = Path(temporary) / "program.wasm"
        script_path = Path(temporary) / "run.mjs"
        wasm_path.write_bytes(wasm)
        reported_bytes = "Math.max(0, written - 1)" if partial else "written"
        script_path.write_text(
            "import fs from 'node:fs';\n"
            "const wasmBytes = fs.readFileSync(new URL('./program.wasm', import.meta.url));\n"
            "const chunks = [];\n"
            "let memory;\n"
            "const wasi = { fd_write(fd, iovs, count, nwritten) {\n"
            "  if (fd !== 1) return 8;\n"
            "  const view = new DataView(memory.buffer);\n"
            "  let written = 0;\n"
            "  for (let index = 0; index < count; index++) {\n"
            "    const ptr = view.getUint32(iovs + index * 8, true);\n"
            "    const length = view.getUint32(iovs + index * 8 + 4, true);\n"
            "    chunks.push(Buffer.from(new Uint8Array(memory.buffer, ptr, length)));\n"
            "    written += length;\n"
            "  }\n"
            f"  view.setUint32(nwritten, {reported_bytes}, true);\n"
            "  return 0;\n"
            "}};\n"
            "const { instance } = await WebAssembly.instantiate(wasmBytes, "
            "{ wasi_snapshot_preview1: wasi });\n"
            "memory = instance.exports.memory;\n"
            f"instance.exports[{json.dumps(export)}]();\n"
            "process.stdout.write(Buffer.concat(chunks));\n",
            encoding="utf-8",
            newline="\n",
        )
        result = subprocess.run(
            [node, str(script_path)], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if partial:
            assert result.returncode != 0 and "RuntimeError" in result.stderr, (
                result.stdout + result.stderr
            )
            return ""
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout.replace("\r\n", "\n")


def main() -> None:
    source = (
        "struct Label { text: string, enabled: bool }\n"
        "struct Packet { label: Label, suffix: string }\n"
        "struct Empty {}\n"
        "fn main() {\n"
        '  let word = "rö" + "ve"\n'
        '  let first = Packet(Label(word, true), "!")\n'
        '  print(first, "ok", false)\n'
        "  print(Empty())\n"
        "}\n"
    )
    module = _lower(source, "m5-wasm-struct-print.rove")
    expected = "\n".join(MIRInterpreter(module).run().output) + "\n"
    assert expected == "Packet(Label(röve, true), !) ok false\nEmpty()\n"
    assert not collect_legalization_issues(module, "wasm", require_emitter=True)
    wat = emit_legalized_wat(module)
    assert '(import "wasi_snapshot_preview1" "fd_write"' in wat
    wasm = emit_legalized_wasm(module)
    assert _run_wasi(wasm, "main") == expected
    _run_wasi(wasm, "main", partial=True)

    integer_source = (
        "struct Counter { value: int, label: string, enabled: bool }\n"
        "struct Packet { counter: Counter, tail: int }\n"
        "fn main() {\n"
        "  let minimum = -9223372036854775807 - 1\n"
        "  let maximum = 9223372036854775807\n"
        '  print(Packet(Counter(minimum, "Rove", true), maximum), 0, -7, 42)\n'
        "  print(minimum, maximum)\n"
        "}\n"
    )
    integer_module = _lower(integer_source, "m5-wasm-integer-struct-print.rove")
    integer_expected = (
        "Packet(Counter(-9223372036854775808, Rove, true), "
        "9223372036854775807) 0 -7 42\n"
        "-9223372036854775808 9223372036854775807\n"
    )
    assert "\n".join(MIRInterpreter(integer_module).run().output) + "\n" == integer_expected
    assert not collect_legalization_issues(integer_module, "wasm", require_emitter=True)
    assert "__rove_mir_print_int" in emit_legalized_wat(integer_module)
    assert _run_wasi(emit_legalized_wasm(integer_module), "main") == integer_expected

    pure = _lower("fn answer() -> int { return 7 }\n", "m5-wasm-pure.rove")
    assert not collect_legalization_issues(pure, "wasm", require_emitter=True)
    assert "(import " not in emit_legalized_wat(pure)

    for name, unsupported in (
        ("float-field", "struct Count { value: float }\nfn main() { print(Count(1.5)) }\n"),
        ("float", "fn main() { print(1.5) }\n"),
        ("array", "struct Label { text: string }\nfn main() { print([Label(\"x\")]) }\n"),
    ):
        rejected = _lower(unsupported, f"m5-wasm-print-{name}-reject.rove")
        issues = collect_legalization_issues(rejected, "wasm", require_emitter=True)
        assert any(issue.code == "MIRG1007" for issue in issues), (name, issues)
        try:
            emit_legalized_wasm(rejected)
            raise AssertionError(f"Wasm emitter accepted unsupported display '{name}'")
        except MIRLegalizationError:
            pass

    print("[PASS] Conditional WASI import, signed-i64/struct stdout parity, and display gates")


if __name__ == "__main__":
    main()
