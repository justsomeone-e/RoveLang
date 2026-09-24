import os
import subprocess
import sys
import tempfile
import json
from unittest import mock


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_PATH = os.path.join(ROOT_DIR, "src", "cli.py")
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.codegen.cpp_toolchain import CppToolchain
from src.cli import get_entry_file, get_target_from_args


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, CLI_PATH, *args],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def run_cli_process_suite() -> bool:
    print("[*] Running CLI Process Exit-Code Tests...")
    with tempfile.TemporaryDirectory(prefix="nyx_cli_exit_") as temp_dir:
        directive_path = os.path.join(temp_dir, "directive.rove")
        with open(directive_path, "w", encoding="utf-8") as source_file:
            source_file.write(
                '#target js\nimport js "node:os" as os\nprint(os.platform())\n'
            )
        plain_path = os.path.join(temp_dir, "plain.rove")
        with open(plain_path, "w", encoding="utf-8") as source_file:
            source_file.write(
                'import cpp "std::filesystem" from "<filesystem>" as fs\n'
                'print(fs.current_path().string())\n'
            )

        assert get_target_from_args("python", directive_path, []) == "js"
        assert get_target_from_args("python", directive_path, ["-t", "rust"]) == "rust"
        assert get_target_from_args("python", directive_path, ["--target=python"]) == "python"
        assert get_target_from_args("python", plain_path, []) == "python"
        assert get_target_from_args(None, plain_path, []) == "cpp"
        assert get_entry_file("missing.rove", ["-t", "js", plain_path]) == plain_path
        assert get_entry_file("missing.rove", ["--target=js", plain_path]) == plain_path

        directive_check = _run_cli("check", directive_path)
        assert directive_check.returncode == 0, directive_check.stdout + directive_check.stderr
        native_default_check = _run_cli("check", plain_path)
        assert native_default_check.returncode == 0, native_default_check.stdout + native_default_check.stderr

        source_path = os.path.join(temp_dir, "runtime_failure.rove")
        with open(source_path, "w", encoding="utf-8") as source_file:
            source_file.write(
                "fn main() {\n"
                "    var values = [1]\n"
                "    print(values[5])\n"
                "}\n"
            )

        run_result = _run_cli("run", source_path, "--target", "python")
        assert run_result.returncode != 0, "nyx run swallowed the child runtime failure"

        test_result = _run_cli("test", source_path)
        assert test_result.returncode != 0, "nyx test swallowed the child runtime failure"
        assert "Execution finished successfully" not in test_result.stdout

        invalid_path = os.path.join(temp_dir, "invalid.rove")
        with open(invalid_path, "w", encoding="utf-8") as source_file:
            source_file.write('var count: int = "wrong"\n')
        check_result = _run_cli("check", invalid_path)
        assert check_result.returncode != 0, "nyx check returned success for invalid source"
        assert "error[E2001]" in check_result.stdout

        inspect_path = os.path.join(temp_dir, "inspect.rove")
        with open(inspect_path, "w", encoding="utf-8") as source_file:
            source_file.write(
                "struct Point { x: int, y: int }\n"
                "fn sum(point: Point) -> int { return point.x + point.y }\n"
                "fn main() { print(sum(Point(2, 3))) }\n"
            )

        ast_json = _run_cli("emit", "ast", inspect_path, "--json")
        assert ast_json.returncode == 0, ast_json.stdout + ast_json.stderr
        ast_document = json.loads(ast_json.stdout)
        assert ast_document["stage"] == "ast"
        assert ast_document["schema_version"] == 1
        assert ast_document["root"]["node"] == "ProgramNode"

        hir_json = _run_cli("emit", "hir", inspect_path, "--json")
        assert hir_json.returncode == 0, hir_json.stdout + hir_json.stderr
        hir_document = json.loads(hir_json.stdout)
        assert hir_document["stage"] == "hir"
        assert hir_document["hir_schema_version"] == 1
        assert len(hir_document["fingerprint"]) == 64
        assert hir_document["root"]["node"] == "IRModule"

        inspected_hir = _run_cli("inspect", "hir", inspect_path)
        assert inspected_hir.returncode == 0, inspected_hir.stdout + inspected_hir.stderr
        assert "HIR inspection schema v1" in inspected_hir.stdout
        assert "IRFunction" in inspected_hir.stdout
        rejected_output = _run_cli(
            "inspect", "ast", inspect_path, "-o", os.path.join(temp_dir, "forbidden.json")
        )
        assert rejected_output.returncode == 1
        assert "read-only" in rejected_output.stdout

        dependency_path = os.path.join(temp_dir, "dependency.rove")
        with open(dependency_path, "w", encoding="utf-8") as source_file:
            source_file.write("fn answer() -> int { return 42 }\n")
        graph_path = os.path.join(temp_dir, "graph.rove")
        with open(graph_path, "w", encoding="utf-8") as source_file:
            source_file.write('import "./dependency"\nprint(answer())\n')
        graph_json = _run_cli("inspect", "module-graph", graph_path, "--json")
        assert graph_json.returncode == 0, graph_json.stdout + graph_json.stderr
        graph_document = json.loads(graph_json.stdout)
        assert graph_document["stage"] == "module-graph"
        assert graph_document["root"]["module_count"] == 2
        root_module = next(
            item
            for item in graph_document["root"]["modules"]
            if item["id"] == graph_document["root"]["module"]
        )
        assert len(root_module["imports"]) == 1

        native_layout = _run_cli(
            "inspect", "layout", inspect_path, "--target", "cpp", "--json"
        )
        assert native_layout.returncode == 0, native_layout.stdout + native_layout.stderr
        native_layout_document = json.loads(native_layout.stdout)
        native_point = next(
            item
            for item in native_layout_document["root"]["types"]
            if item["type"] == "Point"
        )
        assert (native_point["size"], native_point["alignment"]) == (16, 8)
        assert [field["offset"] for field in native_point["fields"]] == [0, 8]

        wasm_layout = _run_cli(
            "inspect", "layout", inspect_path, "--target", "wasm", "--json"
        )
        assert wasm_layout.returncode == 0, wasm_layout.stdout + wasm_layout.stderr
        wasm_layout_document = json.loads(wasm_layout.stdout)
        assert wasm_layout_document["root"]["data_layout"]["pointer_size"] == 4

        types_json = _run_cli("inspect", "types", inspect_path, "--json")
        assert types_json.returncode == 0, types_json.stdout + types_json.stderr
        types_document = json.loads(types_json.stdout)
        point_type = next(
            item
            for item in types_document["root"]["declarations"]
            if item.get("name") == "Point"
        )
        sum_type = next(
            item
            for item in types_document["root"]["declarations"]
            if item.get("name") == "sum"
        )
        assert point_type["fields"] == [
            {"name": "x", "type": "int"},
            {"name": "y", "type": "int"},
        ]
        assert sum_type["parameters"] == [{"name": "point", "type": "Point"}]
        assert sum_type["return_type"] == "int"

        capabilities_json = _run_cli(
            "inspect", "capabilities", inspect_path, "--target", "llvm", "--json"
        )
        assert capabilities_json.returncode == 0, (
            capabilities_json.stdout + capabilities_json.stderr
        )
        capabilities_document = json.loads(capabilities_json.stdout)
        assert capabilities_document["root"]["status"] == "satisfied"
        assert capabilities_document["root"]["required_features"] == []
        assert capabilities_document["root"]["backend"]["name"] == "llvm"
        assert capabilities_document["root"]["mir"]["target"] == "llvm"

        async_fixture = os.path.join(
            ROOT_DIR, "tests", "fixtures", "mir", "m5_async_tasks.rove"
        )
        rejected_capabilities = _run_cli(
            "inspect", "capabilities", async_fixture, "--target", "llvm", "--json"
        )
        assert rejected_capabilities.returncode == 0, (
            rejected_capabilities.stdout + rejected_capabilities.stderr
        )
        rejected_document = json.loads(rejected_capabilities.stdout)
        assert rejected_document["root"]["status"] == "rejected"
        assert rejected_document["root"]["required_features"] == [
            "async_tasks", "exceptions"
        ]
        assert rejected_document["root"]["missing_features"] == [
            "async_tasks", "exceptions"
        ]

        backend_json = _run_cli("explain-backend", "llvm", "--json")
        assert backend_json.returncode == 0, backend_json.stdout + backend_json.stderr
        backend_document = json.loads(backend_json.stdout)
        assert backend_document["canonical_target"] == "llvm"
        assert backend_document["backend"]["maturity"] == "experimental"
        assert backend_document["mir"]["target"] == "llvm"

        unknown_stage = _run_cli("emit", "bytecode", inspect_path)
        assert unknown_stage.returncode == 1
        assert "Unknown compiler stage" in unknown_stage.stdout

        benchmark_help = _run_cli("bench", "compiler", "--help")
        assert benchmark_help.returncode == 0
        assert "Python stage-0 compiler only" in benchmark_help.stdout
        unknown_benchmark = _run_cli("bench", "runtime")
        assert unknown_benchmark.returncode == 1
        assert "Unknown benchmark" in unknown_benchmark.stdout

    with mock.patch.object(CppToolchain, "find_compiler", return_value=None):
        compiled, message = CppToolchain.compile_cpp("unused.cpp")
    assert not compiled
    assert "Clang++" in message and "GCC/G++" in message and "MSVC cl" in message
    assert "ROVE_CXX" in message and "rove doctor" in message

    print(
        "  [PASS] child failures, diagnostics, AST/HIR/module-graph/layout/type/capability inspection "
        "contracts, backend explanations, benchmark routing, and native toolchain guidance propagate"
    )
    return True


if __name__ == "__main__":
    sys.exit(0 if run_cli_process_suite() else 1)
