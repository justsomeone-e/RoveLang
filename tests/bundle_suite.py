import json
import os
import shutil
import subprocess
import sys
import tempfile


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_PATH = os.path.join(ROOT_DIR, "src", "cli.py")
SOURCE_PATH = os.path.join(ROOT_DIR, "tests", "test_bundle.rove")


def run_bundle_suite() -> bool:
    print("=" * 70)
    print("ROVE BUNDLE TYPED-IR / WASM ABI CONFORMANCE")
    print("=" * 70)
    node = shutil.which("node")
    if not node:
        print("[!] Node.js not found. Bundle runtime conformance cannot run.")
        return False

    with tempfile.TemporaryDirectory(prefix="rove_bundle_ir_") as output_dir:
        bundle = subprocess.run(
            [sys.executable, CLI_PATH, "bundle", SOURCE_PATH, "--output", output_dir, "--react", "--vue", "--svelte", "--package"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert bundle.returncode == 0, bundle.stderr or bundle.stdout

        module_path = os.path.join(output_dir, "test_bundle.mjs")
        wasm_path = os.path.join(output_dir, "test_bundle.wasm")
        wat_path = os.path.join(output_dir, "test_bundle.wat")
        assert os.path.exists(module_path) and os.path.exists(wasm_path) and os.path.exists(wat_path)
        package_path = os.path.join(output_dir, "package.json")
        with open(package_path, "r", encoding="utf-8") as package_file:
            package_manifest = json.load(package_file)
        assert package_manifest["type"] == "module"
        assert package_manifest["exports"]["."]["types"] == "./test_bundle.d.ts"
        assert package_manifest["exports"]["./react"]["import"] == "./test_bundle.react.mjs"
        assert package_manifest["exports"]["./vue"]["import"] == "./test_bundle.vue.mjs"
        assert package_manifest["exports"]["./svelte"]["import"] == "./test_bundle.svelte.mjs"
        assert package_manifest["peerDependencies"]["react"].startswith(">=19")
        react_module_path = os.path.join(output_dir, "test_bundle.react.mjs")
        assert os.path.isfile(react_module_path)
        react_syntax = subprocess.run(
            [node, "--check", react_module_path], capture_output=True, text=True, encoding="utf-8"
        )
        assert react_syntax.returncode == 0, react_syntax.stderr
        for adapter in ("vue", "svelte"):
            adapter_path = os.path.join(output_dir, f"test_bundle.{adapter}.mjs")
            syntax = subprocess.run([node, "--check", adapter_path], capture_output=True, text=True, encoding="utf-8")
            assert syntax.returncode == 0, syntax.stderr

        build_workspace = os.path.join(output_dir, "build_workspace")
        os.makedirs(build_workspace)
        build = subprocess.run(
            [sys.executable, CLI_PATH, "build", SOURCE_PATH, "--target", "wasm"],
            cwd=build_workspace,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert build.returncode == 0, build.stderr or build.stdout
        build_dir = os.path.join(build_workspace, "build", "wasm")
        for extension in (".wat", ".wasm", ".mjs", ".d.ts"):
            assert os.path.isfile(os.path.join(build_dir, "test_bundle" + extension)), (
                f"rove build --target wasm did not emit {extension}"
            )
        assert not os.path.exists(os.path.join(build_dir, "test_bundle.react.tsx"))

        wasi_source = os.path.join(output_dir, "wasi_hello.rove")
        wasi_output = os.path.join(output_dir, "wasi_bundle")
        with open(wasi_source, "w", encoding="utf-8", newline="\n") as source_file:
            source_file.write('fn main() { print("hello", "Rove WASI") }\n')
        wasi_bundle = subprocess.run(
            [sys.executable, CLI_PATH, "bundle", wasi_source, "--output", wasi_output, "--wasi"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert wasi_bundle.returncode == 0, wasi_bundle.stderr or wasi_bundle.stdout
        wasi_wasm_path = os.path.join(wasi_output, "wasi_hello.wasm")
        wasi_wat_path = os.path.join(wasi_output, "wasi_hello.wat")
        with open(wasi_wat_path, "r", encoding="utf-8") as wat_file:
            wasi_wat = wat_file.read()
        assert '(import "wasi_snapshot_preview1" "fd_write"' in wasi_wat
        assert '(export "_start")' in wasi_wat
        assert '(export "main")' not in wasi_wat

        wasi_runner_path = os.path.join(output_dir, "verify_wasi.mjs")
        with open(wasi_runner_path, "w", encoding="utf-8", newline="\n") as runner:
            runner.write(
                "import fs from 'node:fs';\n"
                "const bytes = fs.readFileSync(process.argv[2]);\n"
                "let instance; let output = '';\n"
                "const imports = { wasi_snapshot_preview1: { fd_write(fd, iovs, count, nwritten) {\n"
                "  if (fd !== 1) return 8; const memory = instance.exports.memory; const view = new DataView(memory.buffer); let written = 0;\n"
                "  for (let i = 0; i < count; i++) { const ptr = view.getUint32(iovs + i * 8, true); const len = view.getUint32(iovs + i * 8 + 4, true); output += new TextDecoder().decode(new Uint8Array(memory.buffer, ptr, len)); written += len; }\n"
                "  view.setUint32(nwritten, written, true); return 0;\n"
                "} } };\n"
                "({ instance } = await WebAssembly.instantiate(bytes, imports));\n"
                "instance.exports._start();\n"
                "if (output !== 'hello Rove WASI\\n') throw new Error(JSON.stringify(output));\n"
            )
        wasi_runtime = subprocess.run(
            [node, wasi_runner_path, wasi_wasm_path],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert wasi_runtime.returncode == 0, wasi_runtime.stderr or wasi_runtime.stdout

        struct_source = os.path.join(output_dir, "struct_abi.rove")
        struct_output = os.path.join(output_dir, "struct_bundle")
        with open(struct_source, "w", encoding="utf-8", newline="\n") as source_file:
            source_file.write(
                "struct Point { x: int, y: float, active: bool }\n"
                "fn score(point: Point) -> float {\n"
                "  if point.active { return point.x + point.y }\n"
                "  return 0.0\n"
                "}\n"
            )
        struct_bundle = subprocess.run(
            [sys.executable, CLI_PATH, "bundle", struct_source, "--output", struct_output],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert struct_bundle.returncode == 0, struct_bundle.stderr or struct_bundle.stdout
        struct_module = os.path.join(struct_output, "struct_abi.mjs")
        struct_types = os.path.join(struct_output, "struct_abi.d.ts")
        with open(struct_types, "r", encoding="utf-8") as types_file:
            declarations = types_file.read()
        assert "export interface Point" in declarations
        assert "score(point: Point): number" in declarations
        struct_runtime = subprocess.run(
            [
                node,
                "--input-type=module",
                "-e",
                (
                    "import {pathToFileURL} from 'node:url'; "
                    f"const {{initRoveModule}}=await import(pathToFileURL({json.dumps(struct_module)}).href); "
                    "const api=await initRoveModule(); "
                    "if(api.score({x:7,y:0.5,active:true})!==7.5)throw new Error('struct true'); "
                    "if(api.score({x:7,y:0.5,active:false})!==0)throw new Error('struct false');"
                ),
            ],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert struct_runtime.returncode == 0, struct_runtime.stderr or struct_runtime.stdout

        alternate_source = os.path.join(output_dir, "alternate.rove")
        alternate_output = os.path.join(output_dir, "alternate_bundle")
        with open(alternate_source, "w", encoding="utf-8") as source_file:
            source_file.write(
                "fn add_numbers(a: int, b: int) -> int { return a - b; }\n"
                "fn compute_power(base: int, exp: int) -> int { return base + exp; }\n"
                "fn greet_developer(name: string) -> string { return name; }\n"
            )
        alternate = subprocess.run(
            [sys.executable, CLI_PATH, "bundle", alternate_source, "--output", alternate_output],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert alternate.returncode == 0, alternate.stderr or alternate.stdout
        alternate_wasm_path = os.path.join(alternate_output, "alternate.wasm")

        host_source = os.path.join(output_dir, "host_import.rove")
        host_output = os.path.join(output_dir, "host_import_bundle")
        with open(host_source, "w", encoding="utf-8") as source_file:
            source_file.write(
                'extern "WASM:test_host" fn host_add(a: int, b: int) -> int\n'
                'extern "WASM:test_host" fn host_text_len(value: string) -> int\n'
                "fn add_via_host(a: int, b: int) -> int { return host_add(a, b); }\n"
                'fn text_len_via_host(value: string) -> int { return host_text_len(value); }\n'
            )
        host_bundle = subprocess.run(
            [sys.executable, CLI_PATH, "bundle", host_source, "--output", host_output],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert host_bundle.returncode == 0, host_bundle.stderr or host_bundle.stdout

        for name, source, diagnostic in (
            ("struct_index", "struct Point { x: int }\nfn at(p: Point, index: int) -> int { return p[index]; }", "cannot be indexed"),
            ("struct_write", "struct Point { x: int }\nfn write(p: Point) -> void { set p.x = 3; }", "Bundle assignment currently requires"),
        ):
            rejected_source = os.path.join(output_dir, name + ".rove")
            rejected_output = os.path.join(output_dir, name + "_bundle")
            with open(rejected_source, "w", encoding="utf-8") as source_file:
                source_file.write(source + "\n")
            rejected = subprocess.run(
                [sys.executable, CLI_PATH, "bundle", rejected_source, "--output", rejected_output],
                cwd=ROOT_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            assert rejected.returncode != 0, f"bundle accepted unsupported {name}"
            assert diagnostic in (rejected.stdout + rejected.stderr), rejected.stdout + rejected.stderr
            assert not os.path.exists(rejected_output), f"failed {name} left partial artifacts"

        partial_source = os.path.join(output_dir, "partial_return.rove")
        partial_output = os.path.join(output_dir, "partial_return_bundle")
        with open(partial_source, "w", encoding="utf-8") as source_file:
            source_file.write(
                "fn partial(flag: int) -> int {\n"
                "    if flag > 0 { return 1; }\n"
                "}\n"
            )
        partial = subprocess.run(
            [sys.executable, CLI_PATH, "bundle", partial_source, "--output", partial_output],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert partial.returncode != 0, "bundle accepted a value function with a fall-through path"
        assert "can fall through" in (partial.stdout + partial.stderr)
        assert not os.path.exists(partial_output), "failed bundle left a partial output directory"

        runner_path = os.path.join(output_dir, "verify.mjs")
        with open(runner_path, "w", encoding="utf-8") as runner:
            runner.write(
                "import fs from 'node:fs';\n"
                "import { pathToFileURL } from 'node:url';\n"
                "const modulePath = process.argv[2];\n"
                "const wasmPath = process.argv[3];\n"
                "const alternateWasmPath = process.argv[4];\n"
                "const hostModulePath = process.argv[5];\n"
                "const hostWasmPath = process.argv[6];\n"
                "const bytes = fs.readFileSync(wasmPath);\n"
                "if (!WebAssembly.validate(bytes)) throw new Error('invalid WebAssembly binary');\n"
                "const generated = await import(pathToFileURL(modulePath));\n"
                "if (generated.initNyxModule !== generated.initRoveModule || generated.createNyxModule !== generated.createRoveModule) throw new Error('legacy bundle aliases changed');\n"
                "const api = await generated.initRoveModule(wasmPath);\n"
                "const unicodeInput = 'İstanbul 🌙 çığ ğüşö\\u0000é';\n"
                "const expected = `Hello from Rove WebAssembly, ${unicodeInput}!`;\n"
                "if (api.add_numbers(15, 27) !== 42) throw new Error('numeric lowering failed');\n"
                "if (api.next_counter() !== 1 || api.next_counter() !== 2) throw new Error('WASM mutable global failed');\n"
                "if (api.is_positive(1) !== true || api.is_positive(0) !== false) throw new Error('boolean ABI failed');\n"
                "if (typeof api.is_positive(1) !== 'boolean') throw new Error('boolean ABI leaked i32');\n"
                "if (api.compute_power(2, 10) !== 1024) throw new Error('loop/local lowering failed');\n"
                "if (api.sum_values(new Int32Array([1, 0, 2, 3])) !== 6) throw new Error('i32 array iteration failed');\n"
                "if (api.sum_float_values([1.5, 2.25]) !== 3.75) throw new Error('f64 array iteration failed');\n"
                "if (api.array_length([3, 4, 5]) !== 3) throw new Error('array method lowering failed');\n"
                "if (api.int_at([-7, 0, 2147483647], 0) !== -7 || api.int_at([-7, 0, 2147483647], 2) !== 2147483647) throw new Error('i32 index failed');\n"
                "if (api.float_at(new Float64Array([1.25, -2.5]), 1) !== -2.5) throw new Error('f64 index failed');\n"
                "if (api.nested_at([10, 20], [1]) !== 20 || api.index_once([41, 99]) !== 42) throw new Error('index evaluation order failed');\n"
                "for (const fn of [api.int_at, api.float_at]) { for (const [values, index] of [[[], 0], [[1], -1], [[1], 1], [[1], 2147483647], [[1], -2147483648]]) {\n"
                "  let trapped = false; try { fn(values, index); } catch (error) { if (!(error instanceof WebAssembly.RuntimeError)) throw error; trapped = true; }\n"
                "  if (!trapped) throw new Error('array bounds did not trap');\n"
                "} }\n"
                "if (api.guarded_at([], 0) || api.guarded_at([1], -1) || api.guarded_at([1], 1) || !api.guarded_at([1], 0)) throw new Error('and short circuit failed');\n"
                "if (!api.empty_or_positive([]) || !api.empty_or_positive([1]) || api.empty_or_positive([-1])) throw new Error('or short circuit failed');\n"
                "const { instance: raw } = await WebAssembly.instantiate(bytes);\n"
                "const memoryBytes = raw.exports.memory.buffer.byteLength;\n"
                "for (const fn of [raw.exports.int_at, raw.exports.float_at]) { for (const args of [[0, -1, 0], [memoryBytes - 2, 1, 0], [-4, 2, 1], [0, 1073741825, 0], [memoryBytes, 1, 0]]) {\n"
                "  let trapped = false; try { fn(...args); } catch (error) { if (!(error instanceof WebAssembly.RuntimeError)) throw error; trapped = true; }\n"
                "  if (!trapped) throw new Error('invalid array descriptor did not trap');\n"
                "} }\n"
                "new DataView(raw.exports.memory.buffer).setInt32(memoryBytes - 4, 123, true);\n"
                "if (raw.exports.int_at(memoryBytes - 4, 1, 0) !== 123) throw new Error('last valid memory element failed');\n"
                "const mutableInts = new Int32Array([10, 20, 30]);\n"
                "api.set_int_at(mutableInts, 1, 99);\n"
                "if (mutableInts[1] !== 99) throw new Error('set_int_at failed');\n"
                "const mutableFloats = new Float64Array([1.5, 2.5, 3.5]);\n"
                "api.set_float_at(mutableFloats, 0, 42.125);\n"
                "if (mutableFloats[0] !== 42.125) throw new Error('set_float_at failed');\n"
                "if (!api.char_matches('Rove', 0, 'R') || !api.char_matches('Rove', 3, 'e') || api.char_matches('Rove', 1, 'z')) throw new Error('char_matches failed');\n"
                "if (api.char_slice('hello', 0) !== 'h' || api.char_slice('hello', 4) !== 'o') throw new Error('char_slice failed');\n"
                "let trappedSet = false; try { api.set_int_at(mutableInts, 10, 5); } catch (e) { if (e instanceof WebAssembly.RuntimeError) trappedSet = true; }\n"
                "if (!trappedSet) throw new Error('set_int_at out of bounds did not trap');\n"
                "let trappedChar = false; try { api.char_slice('abc', 5); } catch (e) { if (e instanceof WebAssembly.RuntimeError) trappedChar = true; }\n"
                "if (!trappedChar) throw new Error('char_slice out of bounds did not trap');\n"
                "if (api.string_length('İstanbul') !== 9) throw new Error('string method lowering failed');\n"
                "if (api.choose_label(true, 'Rove') !== 'enabled: Rove' || api.choose_label(false, 'Rove') !== 'disabled: Rove') throw new Error('string conditional lowering failed');\n"
                "if (api.greet_developer(unicodeInput) !== expected) throw new Error('UTF-8 string lowering failed');\n"
                "if (api.echo_via_call(unicodeInput) !== unicodeInput) throw new Error('internal string parameter call failed');\n"
                "if (api.literal_via_call() !== 'internal UTF-8: İstanbul 🌙') throw new Error('internal string literal call failed');\n"
                "for (let i = 0; i < 100000; i++) {\n"
                "  if (api.greet_developer('x') !== 'Hello from Rove WebAssembly, x!') {\n"
                "    throw new Error(`stress mismatch at ${i}`);\n"
                "  }\n"
                "}\n"
                "const alternateApi = await generated.initRoveModule(alternateWasmPath);\n"
                "if (alternateApi.add_numbers(10, 3) !== 7) throw new Error('alternate instance mismatch');\n"
                "if (api.add_numbers(10, 3) !== 13) throw new Error('module instances share mutable state');\n"
                "if (generated.add_numbers(10, 3) !== 7) throw new Error('default API did not select latest init');\n"
                "const isolatedA = await generated.createRoveModule(wasmPath);\n"
                "const isolatedB = await generated.createRoveModule(wasmPath);\n"
                "if (isolatedA === isolatedB) throw new Error('createRoveModule reused a cached API');\n"
                "if (isolatedA.next_counter() !== 1 || isolatedB.next_counter() !== 1) throw new Error('WASM globals leaked across instances');\n"
                "const hostGenerated = await import(pathToFileURL(hostModulePath));\n"
                "let hostMemory;\n"
                "const hostApi = await hostGenerated.createRoveModule(hostWasmPath, { imports: { test_host: {\n"
                "  host_add: (a, b) => a + b,\n"
                "  host_text_len: (ptr, len) => { if (!hostMemory) return len; return new Uint8Array(hostMemory.buffer, ptr, len).length; },\n"
                "} } });\n"
                "if (hostApi.add_via_host(20, 22) !== 42) throw new Error('WASM numeric host import failed');\n"
                "if (hostApi.text_len_via_host('İstanbul') !== 9) throw new Error('WASM string host import failed');\n"
                "console.log(JSON.stringify({ add: 42, power: 1024, stress: 100000, unicode: true, isolated: true }));\n"
            )

        runtime = subprocess.run(
            [
                node,
                runner_path,
                module_path,
                wasm_path,
                alternate_wasm_path,
                os.path.join(host_output, "host_import.mjs"),
                os.path.join(host_output, "host_import.wasm"),
            ],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert runtime.returncode == 0, runtime.stderr or runtime.stdout
        result = json.loads(runtime.stdout.strip().splitlines()[-1])
        assert result == {"add": 42, "power": 1024, "stress": 100000, "unicode": True, "isolated": True}

        with open(wat_path, "r", encoding="utf-8") as wat_file:
            wat = wat_file.read()
        assert "loop $for_loop_" in wat
        assert "memory.copy" in wat
        assert "i32.mul" in wat
        assert "call $echo_inner" in wat

    print("[PASS] Typed lowering, checked array reads and in-place writes, string indexing and char returns, lazy Boolean guards, build/bundle artifacts, definite returns, UTF-8 ABI, isolated instances, and 100k allocation stress")
    return True


if __name__ == "__main__":
    sys.exit(0 if run_bundle_suite() else 1)
