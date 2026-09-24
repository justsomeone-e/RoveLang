"""Real WASM/native/hosted regressions and static documentation integrity."""
from pathlib import Path
from html.parser import HTMLParser
import hashlib
import json
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api import NyxCompiler
from src.codegen.cpp_toolchain import CppToolchain
from src.cli import cmd_bundle
from tests.fallible_stdlib_suite import _run


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            assert attrs["id"] not in self.ids, f"Duplicate ID: {attrs['id']}"
            self.ids.add(attrs["id"])
        for key in ("href", "src"):
            if attrs.get(key):
                self.links.append(attrs[key])


def _artifact_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix in (".d", ".ts", ".mjs", ".js", ".rove", ".wat", ".json", ".html", ".css", ".md"):
        return data.replace(b"\r\n", b"\n")
    return data


def static_integrity():
    docs = ROOT / "docs"
    for page in docs.rglob("*.html"):
        parsed = Links()
        parsed.feed(page.read_text(encoding="utf-8"))
        for url in parsed.links:
            parts = urlsplit(url)
            if parts.scheme or parts.netloc:
                continue
            path = (page.parent / unquote(parts.path)).resolve() if parts.path else page
            assert path.exists(), (page, url)
            if parts.fragment and path.suffix == ".html":
                target = Links()
                target.feed(path.read_text(encoding="utf-8"))
                assert unquote(parts.fragment) in target.ids, (page, url)
    manifest = json.loads((docs / "generated/manifest.json").read_text())
    assert manifest["compilerVersion"] == (ROOT / "VERSION").read_text().strip()
    for artifact in manifest["artifacts"]:
        assert hashlib.sha256(_artifact_bytes(docs / artifact["path"])).hexdigest() == artifact["sha256"]
    for name, source in (("metrics", "examples/metrics/metrics.rove"), ("pong", "examples/web_pong/pong.rove")):
        assert _artifact_bytes(ROOT / source) == _artifact_bytes(docs / "generated" / name / f"{name}.rove")


def run_docs_site_suite():
    static_integrity()
    compiler = NyxCompiler(str(ROOT / "examples/metrics"))
    source = (ROOT / "examples/metrics/metrics.rove").read_text()
    program = source + '''
fn checked(flag: bool) -> Result<int, string> {
    if flag { return Ok(6) }
    return Err("invalid")
}
fn main() {
    let values: Array<float> = [10.0, 20.0, 60.0]
    print(average(values), minimum(values), maximum(values), count_over(values, 20.0))
    print(12.0 / values.length(), 12.0 / values.size(), 12.0 / "abc".len())
    match checked(true) { Ok(value) => print(value * 0.5), Err(error) => print(error) }
    match checked(false) { Ok(value) => print(value * 0.5), Err(error) => print(error + " input") }
}
'''
    with tempfile.TemporaryDirectory(prefix="nyx_docs_") as temporary:
        directory = Path(temporary)
        for target in ("cpp", "js", "python"):
            compiled = compiler.compile_source(program, target=target)
            assert compiled.success, (target, compiled.diagnostics)
            code, output = _run(target, compiled.artifact.content, temporary)
            assert code == 0, (target, output)
            lines = output.strip().splitlines()
            assert [float(value) for value in lines[0].split()] == [30, 10, 60, 1], (target, output)
            assert [float(value) for value in lines[1].split()] == [4, 4, 4], (target, output)
            assert float(lines[2]) == 3 and lines[3] == "invalid input", (target, output)

        for invalid in (
            'fn read() -> Result<int, string> { return Ok(1) } match read() { Ok(a, b) => print(a) }',
            'fn read() -> Result<int, string> { return Ok(1) } match read() { Ok(a) => print(a) } var outside: int = a',
        ):
            assert not compiler.check_source(invalid).success

        cli = compiler.compile_source((ROOT / "examples/metrics/cli.rove").read_text(), target="cpp", filename=str(ROOT / "examples/metrics/cli.rove"))
        assert cli.success, cli.diagnostics
        cpp = directory / "metrics_cli.cpp"
        exe = directory / "metrics_cli.exe"
        cpp.write_text(cli.artifact.content, encoding="utf-8")
        ok, message = CppToolchain.compile_cpp(str(cpp), str(exe))
        assert ok, message
        code, output = CppToolchain.run_executable(str(exe), args=["42", "95", "380"], timeout=10)
        assert code == 0 and "samples: 3" in output and "over_200_ms: 1" in output, output
        for invalid in ("nope", "-1", "1000001", "1e2", "1.5", "01"):
            code, output = CppToolchain.run_executable(str(exe), args=[invalid], timeout=10)
            assert "Error:" in output and "samples:" not in output, (invalid, output)

        assert cmd_bundle(str(ROOT / "examples/metrics/metrics.rove"), str(directory)) == 0
        assert (directory / "metrics.wasm").read_bytes() == (ROOT / "docs/generated/metrics/metrics.wasm").read_bytes()
        runner = directory / "verify.mjs"
        runner.write_text('''
import assert from 'node:assert/strict';
import { createNyxModule } from './metrics.mjs';
const api = await createNyxModule();
assert.equal(api.average([42, 95, 380]), 517 / 3);
assert.equal(api.minimum([42, 95, 380]), 42);
assert.equal(api.maximum([42, 95, 380]), 380);
assert.equal(api.count_over([0, 200, 201], 200), 1);
assert.equal(api.count_between([0, 49, 50, 99, 100], 50, 100), 2);
assert.equal(api.average([]), 0);
assert.equal(api.minimum([]), 0);
assert.equal(api.maximum([]), 0);
const large = Array.from({length: 10000}, (_, index) => index / 10);
for (let i = 0; i < 1000; i++) {
  assert.equal(api.sample_count(large), 10000);
  assert.ok(Math.abs(api.average(large) - 499.95) < 1e-8);
  assert.equal(api.maximum(large), 999.9);
}
assert.equal(api.minimum([7]), 7);
console.log('WASM values, boundaries, empty arrays and repeated 10k-sample calls passed');
''', encoding="utf-8")
        runtime = subprocess.run(["node", str(runner)], capture_output=True, text=True, timeout=60)
        assert runtime.returncode == 0, runtime.stdout + runtime.stderr
    for script in ("home.js", "app.js", "evaluator.js", "preview-worker.js"):
        subprocess.run(["node", "--check", str(ROOT / "docs" / script)], check=True, capture_output=True)
    print("[PASS] Site links/hashes, real WASM stress, native CLI and C++/JS/Python numeric/Result regressions")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_docs_site_suite() else 1)
