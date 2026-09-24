"""Typed std/web host ABI and generated browser adapter conformance."""

import json
import os
import shutil
import subprocess
import sys
import tempfile


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_PATH = os.path.join(ROOT_DIR, "src", "cli.py")
SOURCE_PATH = os.path.join(ROOT_DIR, "tests", "test_web_bundle.rove")
PONG_PATH = os.path.join(ROOT_DIR, "examples", "web_pong", "pong.rove")


def run_web_bundle_suite() -> bool:
    print("=" * 70)
    print("ROVE STD/WEB + WASM HOST ABI V1 CONFORMANCE")
    print("=" * 70)
    node = shutil.which("node")
    if not node:
        print("[!] Node.js not found. Web host ABI conformance cannot run.")
        return False

    with tempfile.TemporaryDirectory(prefix="rove_web_bundle_") as output_dir:
        result = subprocess.run(
            [sys.executable, CLI_PATH, "bundle", SOURCE_PATH, "--output", output_dir],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, result.stderr or result.stdout

        module_path = os.path.join(output_dir, "test_web_bundle.mjs")
        wasm_path = os.path.join(output_dir, "test_web_bundle.wasm")
        wat_path = os.path.join(output_dir, "test_web_bundle.wat")
        dts_path = os.path.join(output_dir, "test_web_bundle.d.ts")

        with open(wat_path, "r", encoding="utf-8") as handle:
            wat = handle.read()
        assert '(import "nyx_host_v1" "_nyx_web_query"' in wat
        assert '(import "nyx_host_v1" "_nyx_host_abi_version"' in wat
        assert '(import "nyx_host_v1" "_nyx_web_canvas_fill_rect"' in wat

        with open(dts_path, "r", encoding="utf-8") as handle:
            dts = handle.read()
        assert "update_status(selector: string, value: string): number" in dts
        assert "createRoveModule" in dts and "RoveModuleOptions" in dts
        assert "createNyxModule" in dts and "NyxModuleOptions" in dts

        runner_path = os.path.join(output_dir, "verify_web.mjs")
        with open(runner_path, "w", encoding="utf-8") as handle:
            handle.write(
                "import { pathToFileURL } from 'node:url';\n"
                "const generated = await import(pathToFileURL(process.argv[2]));\n"
                "const calls = [];\n"
                "if (generated.createNyxModule !== generated.createRoveModule) throw new Error('legacy bundle alias changed');\n"
                "const api = await generated.createRoveModule(process.argv[3], { imports: { nyx_host_v1: {\n"
                "  _nyx_host_abi_version: () => 1,\n"
                "  _nyx_web_query: (_ptr, len) => { calls.push(['query', len]); return 17; },\n"
                "  _nyx_web_set_text: (handle, _ptr, len) => { calls.push(['text', handle, len]); },\n"
                "  _nyx_web_canvas_set_fill_style: (handle, _ptr, len) => { calls.push(['style', handle, len]); },\n"
                "  _nyx_web_canvas_fill_rect: (handle, x, y, w, h) => { calls.push(['rect', handle, x, y, w, h]); },\n"
                "} } });\n"
                "if (api.update_status('#status', 'ready') !== 17) throw new Error('typed WebElement result failed');\n"
                "if (api.draw_box(9) !== 1) throw new Error('canvas wrapper failed');\n"
                "const expected = [['query', 7], ['text', 17, 5], ['style', 9, 7], ['rect', 9, 10, 20, 30, 40]];\n"
                "if (JSON.stringify(calls) !== JSON.stringify(expected)) throw new Error(JSON.stringify(calls));\n"
                "const defaultApi = await generated.createRoveModule(process.argv[3]);\n"
                "let rejected = false;\n"
                "try { defaultApi.update_status('#status', 'ready'); } catch (error) { rejected = String(error).includes('browser DOM host'); }\n"
                "if (!rejected) throw new Error('Node host did not reject DOM use clearly');\n"
                "let abiRejected = false;\n"
                "try { await generated.createRoveModule(process.argv[3], { imports: { nyx_host_v1: { _nyx_host_abi_version: () => 2 } } }); } catch (error) { abiRejected = String(error).includes('host ABI version'); }\n"
                "if (!abiRejected) throw new Error('incompatible host ABI was accepted');\n"
                "console.log(JSON.stringify({ hostAbi: 1, calls: calls.length, nodeGuard: true }));\n"
            )

        runtime = subprocess.run(
            [node, runner_path, module_path, wasm_path],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert runtime.returncode == 0, runtime.stderr or runtime.stdout
        payload = json.loads(runtime.stdout.strip().splitlines()[-1])
        assert payload == {"hostAbi": 1, "calls": 4, "nodeGuard": True}

    with tempfile.TemporaryDirectory(prefix="rove_web_pong_") as output_dir:
        result = subprocess.run(
            [sys.executable, CLI_PATH, "bundle", PONG_PATH, "--output", output_dir, "--package"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, result.stderr or result.stdout
        module_path = os.path.join(output_dir, "pong.mjs")
        wasm_path = os.path.join(output_dir, "pong.wasm")
        package_path = os.path.join(output_dir, "package.json")
        with open(package_path, "r", encoding="utf-8") as handle:
            package = json.load(handle)
        assert package["rove"] == {"abi": 1, "hostAbi": 1, "target": "wasm32"}
        assert package["nyx"] == package["rove"]

        runner_path = os.path.join(output_dir, "verify_pong.mjs")
        with open(runner_path, "w", encoding="utf-8") as handle:
            handle.write(
                "import { pathToFileURL } from 'node:url';\n"
                "const generated = await import(pathToFileURL(process.argv[2]));\n"
                "const calls = []; let next = 10;\n"
                "const host = {\n"
                "  _nyx_host_abi_version: () => 1,\n"
                "  _nyx_web_document: () => 1,\n"
                "  _nyx_web_query: (_p, l) => { calls.push(['query', l]); return 2; },\n"
                "  _nyx_web_create: (_p, l) => { calls.push(['create', l]); return 3; },\n"
                "  _nyx_web_set_attribute: (h, _np, nl, _vp, vl) => calls.push(['attribute', h, nl, vl]),\n"
                "  _nyx_web_append: (p, c) => calls.push(['append', p, c]),\n"
                "  _nyx_web_listen: (h, _p, l, cb) => { calls.push(['listen', h, l, cb]); return next++; },\n"
                "  _nyx_web_request_animation_frame: (cb) => calls.push(['frame', cb]),\n"
                "  _nyx_web_event_key: () => 87,\n"
                "  _nyx_web_canvas_clear: (h) => calls.push(['clear', h]),\n"
                "  _nyx_web_canvas_set_fill_style: (h, _p, l) => calls.push(['style', h, l]),\n"
                "  _nyx_web_canvas_fill_rect: (h, x, y, w, ht) => calls.push(['rect', h, x, y, w, ht]),\n"
                "};\n"
                "const api = await generated.createRoveModule(process.argv[3], { imports: { nyx_host_v1: host } });\n"
                "if (api.pong_start() !== 1) throw new Error('pong_start failed');\n"
                "if (!calls.some(x => x[0] === 'listen' && x[3] === 1)) throw new Error('keyboard listener missing');\n"
                "if (!calls.some(x => x[0] === 'frame' && x[1] === 2)) throw new Error('animation frame missing');\n"
                "const before = calls.length; api.rove_dispatch(1, 99); api.rove_dispatch(2, 0);\n"
                "if (calls.length <= before) throw new Error('dispatch produced no drawing work');\n"
                "console.log(JSON.stringify({ started: true, calls: calls.length }));\n"
            )
        runtime = subprocess.run(
            [node, runner_path, module_path, wasm_path],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert runtime.returncode == 0, runtime.stderr or runtime.stdout
        payload = json.loads(runtime.stdout.strip().splitlines()[-1])
        assert payload["started"] is True and payload["calls"] >= 15

    print("[PASS] Versioned host ABI, DOM guard, canvas calls, and Rove Pong")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_web_bundle_suite() else 1)
