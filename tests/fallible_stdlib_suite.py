"""Fallible stdlib APIs must preserve errors as typed Result values."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.api import NyxCompiler
from src.codegen.cpp_toolchain import CppToolchain


def _run(target: str, content: str, directory: str) -> tuple[int, str]:
    if target == "cpp":
        source_path = os.path.join(directory, "fallible_fs.cpp")
        executable_path = os.path.join(directory, "fallible_fs.exe")
        with open(source_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        compiled, message = CppToolchain.compile_cpp(source_path, executable_path)
        assert compiled, message
        return CppToolchain.run_executable(executable_path)
    if target == "js":
        runtime = shutil.which("node")
        assert runtime is not None
        path = os.path.join(directory, "fallible_fs.js")
        command = [runtime, path]
    else:
        path = os.path.join(directory, "fallible_fs.py")
        command = [sys.executable, path]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return process.returncode, process.stdout + process.stderr


def run_fallible_stdlib_suite() -> bool:
    with tempfile.TemporaryDirectory(prefix="nyx_fallible_stdlib_") as directory:
        data_path = os.path.join(directory, "empty.txt").replace("\\", "/")
        missing_path = os.path.join(directory, "missing.txt").replace("\\", "/")
        source = f'''
import "std/fs"
import "std/encoding"
import "std/json_lite"
import "std/time"
import "std/path"
import "std/str"
import "std/process"
fn main() {{
    print("write", write_string("{data_path}", "").unwrap())
    print("empty-bytes", len(read_to_string("{data_path}").unwrap()))
    match read_to_string("{missing_path}") {{
        Ok(value) => print("unexpected", value),
        Err(error) => print("missing-error")
    }}
    print("remove", remove_file("{data_path}").unwrap())
    print("decoded", base64_decode("Tnl4").unwrap())
    match base64_decode("%%%") {{ Ok(value) => print("unexpected", value), Err(error) => print("base64-error") }}
    print("json-zero", get_int("{{\\\"count\\\":0}}", "count").unwrap())
    match get_string("{{\\\"name\\\":\\\"nyx\\\"}}", "missing") {{ Ok(value) => print("unexpected", value), Err(error) => print("json-error") }}
    match sleep_ms(-1) {{ Ok(value) => print("unexpected", value), Err(error) => print("time-error") }}
    print("path-join", join("foo", "bar.rove"))
    print("path-base", basename("src/lib/test.rove"))
    print("path-dir", dirname("src/lib/test.rove"))
    print("path-ext", extname("src/lib/test.rove"))
    print("str-trim", trim("  nyx  "))
    match find("hello world", "world") {{ Ok(idx) => print("str-find", idx), Err(err) => print("str-find-error") }}
    match find("hello", "missing") {{ Ok(idx) => print("unexpected", idx), Err(err) => print("str-find-missing") }}
    match get_env("NONEXISTENT_VAR_NYX_TEST") {{ Ok(val) => print("unexpected", val), Err(err) => print("env-missing") }}
}}
'''
        for target in ("cpp", "js", "python"):
            result = NyxCompiler(ROOT_DIR).compile_source(
                source, target=target, filename=os.path.join(directory, f"fallible-{target}.rove")
            )
            assert result.success, (target, result.diagnostics)
            assert result.artifact is not None
            return_code, output = _run(target, result.artifact.content, directory)
            assert return_code == 0, (target, output)
            assert [line.strip() for line in output.splitlines() if line.strip()] == [
                "write true", "empty-bytes 0", "missing-error", "remove true",
                "decoded Nyx", "base64-error", "json-zero 0", "json-error", "time-error",
                "path-join foo/bar.rove", "path-base test.rove", "path-dir src/lib", "path-ext .rove",
                "str-trim nyx", "str-find 6", "str-find-missing", "env-missing"
            ], (target, output)

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def serve_once():
            connection, _address = listener.accept()
            with connection:
                assert connection.recv(16) == b"ping"
                connection.sendall(b"pong")
            listener.close()

        server = threading.Thread(target=serve_once, daemon=True)
        server.start()
        network_source = f'''
import "std/net"
import "std/process"
fn main() {{
    match exec_cmd("cmd /c exit 7") {{ Ok(code) => print("process-ok"), Err(error) => print("process-error") }}
    var sock = tcp_connect("127.0.0.1", {port}).unwrap()
    print("send", tcp_send(sock, "ping").unwrap())
    print("recv", tcp_recv(sock, 16).unwrap())
    print("close", tcp_close(sock).unwrap())
    match tcp_connect("", 80) {{ Ok(value) => print("unexpected", value), Err(error) => print("connect-error") }}
}}
'''
        result = NyxCompiler(ROOT_DIR).compile_source(
            network_source, target="cpp", filename=os.path.join(directory, "fallible-net.rove")
        )
        assert result.success, result.diagnostics
        source_path = os.path.join(directory, "fallible_net.cpp")
        executable_path = os.path.join(directory, "fallible_net.exe")
        with open(source_path, "w", encoding="utf-8") as handle:
            handle.write(result.artifact.content)
        compiled, message = CppToolchain.compile_cpp(
            source_path, executable_path, link_libraries=["ws2_32"] if os.name == "nt" else []
        )
        assert compiled, message
        return_code, output = CppToolchain.run_executable(executable_path)
        server.join(timeout=5)
        assert not server.is_alive(), "localhost test server did not finish"
        assert return_code == 0, output
        assert [line.strip() for line in output.splitlines() if line.strip()] == [
            "process-ok", "send true", "recv pong", "close true", "connect-error"
        ], output

    print("[PASS] fallible fs/encoding/json parity plus process/network Result contracts")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_fallible_stdlib_suite() else 1)
