"""Executable wasm32 allocator checks at the heap wrap boundary."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.codegen.wasm_ir import ModuleIR, _runtime_functions
from src.mir.codegen_wasm import _WasmEmitter


def _allocator_module(kind: str, heap_start: int) -> bytes:
    function = (
        _runtime_functions()[1]
        if kind == "bundle"
        else _WasmEmitter._array_runtime()[0]
    )
    function.export = True
    return ModuleIR(kind, [function], [], heap_start).to_wasm()


def run_wasm_allocator_suite() -> bool:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for executable Wasm allocator checks"
    with tempfile.TemporaryDirectory(prefix="rove_wasm_alloc_") as temporary:
        directory = Path(temporary)
        for kind in ("bundle", "mir"):
            for name, start in (("normal", 131064), ("overflow", -8)):
                (directory / f"{kind}_{name}.wasm").write_bytes(
                    _allocator_module(kind, start)
                )
        script = directory / "check.mjs"
        script.write_text(
            "import fs from 'node:fs';\n"
            "import assert from 'node:assert/strict';\n"
            "async function load(name) {\n"
            "  const bytes = fs.readFileSync(new URL(`./${name}.wasm`, import.meta.url));\n"
            "  return (await WebAssembly.instantiate(bytes)).instance.exports;\n"
            "}\n"
            "for (const [kind, symbol] of [['bundle', '__nyx_alloc'], "
            "['mir', '__rove_mir_alloc']]) {\n"
            "  const normal = await load(`${kind}_normal`);\n"
            "  assert.equal(normal[symbol](16), 131064);\n"
            "  assert.equal(normal.memory.buffer.byteLength, 3 * 65536);\n"
            "  assert.equal(normal[symbol](16), 131080);\n"
            "  const overflow = await load(`${kind}_overflow`);\n"
            "  if (kind === 'bundle') assert.equal(overflow[symbol](16), 0);\n"
            "  else assert.throws(() => overflow[symbol](16), WebAssembly.RuntimeError);\n"
            "}\n",
            encoding="utf-8", newline="\n",
        )
        result = subprocess.run(
            [node, str(script)], cwd=ROOT, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    print("[PASS] Bundle and MIR Wasm allocators grow memory and reject heap wrap")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_wasm_allocator_suite() else 1)
