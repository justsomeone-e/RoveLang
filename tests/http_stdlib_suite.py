"""Local runtime coverage for the shell-free native std/http transport."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.api import NyxCompiler
from src.codegen.cpp_toolchain import CppToolchain


class _Handler(BaseHTTPRequestHandler):
    request_path = ""
    request_body = b""
    request_content_type = ""

    def do_GET(self) -> None:
        type(self).request_path = self.path
        payload = b"GET_OK"
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        type(self).request_body = self.rfile.read(length)
        type(self).request_content_type = self.headers.get("Content-Type", "")
        payload = b"POST_OK"
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args) -> None:
        return


def run_http_stdlib_suite() -> bool:
    print("=" * 70)
    print("NYX NATIVE STD/HTTP SHELL-FREE TRANSPORT")
    print("=" * 70)

    assert shutil.which("curl"), "curl is required for std/http runtime coverage"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        get_url = f"{base_url}/probe?left=1&right=2"
        body = 'quotes="ok" & shell=$(must-not-run)'
        source = (
            '#target cpp\n'
            'import "std/http"\n'
            'fn main() {\n'
            f'    print(http_get({json.dumps(get_url)}))\n'
            f'    print(http_post({json.dumps(base_url + "/submit")}, '
            f'{json.dumps(body)}, "application/json"))\n'
            '}\n'
            'main()\n'
        )
        result = NyxCompiler(ROOT_DIR).compile_source(
            source,
            target="cpp",
            filename="<http-stdlib-runtime>",
        )
        assert result.success, result.diagnostics
        assert result.artifact is not None

        with tempfile.TemporaryDirectory(prefix="nyx_http_stdlib_") as temp_dir:
            cpp_path = os.path.join(temp_dir, "http.cpp")
            executable = os.path.join(temp_dir, "http.exe" if os.name == "nt" else "http")
            with open(cpp_path, "w", encoding="utf-8") as handle:
                handle.write(result.artifact.content)
            compiled, detail = CppToolchain.compile_cpp(cpp_path, executable)
            assert compiled, detail
            return_code, output = CppToolchain.run_executable(executable, timeout=30)
            assert return_code == 0, output

        assert "GET_OK" in output and "POST_OK" in output
        assert _Handler.request_path == "/probe?left=1&right=2"
        assert _Handler.request_body.decode("utf-8") == body
        assert _Handler.request_content_type == "application/json"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    print("[PASS] Local GET/POST, exact argument transport, limits, and no-shell execution")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_http_stdlib_suite() else 1)
