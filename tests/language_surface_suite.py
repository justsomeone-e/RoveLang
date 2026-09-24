import json
import os
import subprocess
import sys
import tempfile


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


from src import RoveCompiler
from src.codegen.cpp_toolchain import CppToolchain
from src.core.completion_catalog import completion_catalog
from src.core.language_surface import (
    EXPERIMENTAL_KEYWORDS,
    RESERVED_KEYWORDS,
    STABLE_KEYWORDS,
)
from src.core.lexer import Lexer
from src.core.tokens import TokenType


def _run_artifact_process(target: str, content: str, directory: str) -> subprocess.CompletedProcess[str]:
    if target == "cpp":
        source_path = os.path.join(directory, "surface.cpp")
        executable_path = os.path.join(directory, "surface.exe")
        with open(source_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        compiled, message = CppToolchain.compile_cpp(source_path, executable_path)
        assert compiled, message
        command = [executable_path]
    else:
        command = [sys.executable, "-c", content] if target == "python" else ["node", "-e", content]
    return subprocess.run(
        command,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )


def _run_artifact(target: str, content: str, directory: str) -> str:
    runtime = _run_artifact_process(target, content, directory)
    assert runtime.returncode == 0, runtime.stderr or runtime.stdout
    return runtime.stdout


def run_language_surface_suite() -> bool:
    print("=" * 70)
    print("ROVE 4.0 CANONICAL LANGUAGE SURFACE")
    print("=" * 70)

    with open(
        os.path.join(ROOT_DIR, "vscode-extension", "language-surface.json"),
        "r",
        encoding="utf-8",
    ) as handle:
        editor_surface = json.load(handle)
    assert editor_surface == completion_catalog()
    assert tuple(editor_surface["stableKeywords"]) == STABLE_KEYWORDS
    assert tuple(editor_surface["experimentalKeywords"]) == EXPERIMENTAL_KEYWORDS
    assert tuple(editor_surface["reservedKeywords"]) == RESERVED_KEYWORDS

    compiler = RoveCompiler(ROOT_DIR)
    for non_keyword in ("val", "def"):
        token = Lexer(non_keyword, "<language-surface>").tokenize()[0]
        assert token.type == TokenType.IDENT

    legacy_function = compiler.check_source(
        "def legacy() { return }",
        target="cpp",
        filename="legacy_def.rove",
    )
    assert not legacy_function.success

    source = """
fn main() {
    let limit: int = 4
    var total: int = 0
    for i in 0..limit {
        if i == 1 { continue }
        set total = total + i
    }
    if total == 9 {
        print("surface:", total)
    } else if total == 0 {
        print("wrong")
    } else {
        print("unexpected")
    }
}
"""
    with tempfile.TemporaryDirectory(prefix="nyx_language_surface_") as directory:
        for target in ("cpp", "js", "python"):
            result = compiler.compile_source(source, target=target, filename="surface.rove")
            assert result.success, result.diagnostics
            assert result.artifact is not None
            output = _run_artifact(target, result.artifact.content, directory)
            assert output.replace("\r\n", "\n").strip() == "surface: 9", (target, output)

        trait_source = """
trait Show {
    fn show(self) -> string
}

struct Point { x: int, y: int }

impl Show for Point {
    fn show(self) -> string {
        return "(" + to_string(self.x) + "," + to_string(self.y) + ")"
    }
}

fn main() { print("trait:", Point(10, 20).show()) }
"""
        for target in ("cpp", "js", "python"):
            result = compiler.compile_source(
                trait_source,
                target=target,
                filename="trait_contract.rove",
            )
            assert result.success, result.diagnostics
            assert result.artifact is not None
            output = _run_artifact(target, result.artifact.content, directory)
            assert output.replace("\r\n", "\n").strip() == "trait: (10,20)", (target, output)

        exception_source = """
fn fail() -> int { throw 42 }
fn main() {
    try { print(fail()) }
    catch error { print("caught:", error) }
}
"""
        for target in ("cpp", "js", "python"):
            result = compiler.compile_source(
                exception_source,
                target=target,
                filename="exceptions.rove",
            )
            assert result.success, result.diagnostics
            assert result.artifact is not None
            output = _run_artifact(target, result.artifact.content, directory)
            assert output.replace("\r\n", "\n").strip() == "caught: 42", (target, output)

        for target in ("rust", "react", "wasm"):
            result = compiler.compile_source(
                exception_source,
                target=target,
                filename=f"exceptions_{target}.rove",
            )
            assert not result.success, f"{target} silently accepted unsupported exception semantics"
            assert result.diagnostics and result.diagnostics[0].code == "E3001"

        async_source = """
struct Worker { base: int }

impl Worker {
    async fn compute(self, value: int) -> int {
        return self.base + value
    }
}

async fn compute() -> int { return 42 }
async fn fail_async() -> int { throw "async boom" }

async fn combine() -> int {
    let task: Task<int> = compute()
    let first: int = await task
    let second: int = await task
    return first + second
}

async fn main() {
    let result: int = await combine()
    print("async:", result)
    let worker = Worker(40)
    let method_result: int = await worker.compute(2)
    print("method:", method_result)
    try { let ignored: int = await fail_async() }
    catch error { print("caught:", error) }
}
"""
        for target in ("cpp", "js", "python"):
            result = compiler.compile_source(async_source, target=target, filename="async_tasks.rove")
            assert result.success, result.diagnostics
            assert result.artifact is not None
            output = _run_artifact(target, result.artifact.content, directory)
            assert output.replace("\r\n", "\n").strip() == (
                "async: 84\nmethod: 42\ncaught: async boom"
            ), (target, output)

        for target in ("rust", "react", "wasm"):
            result = compiler.compile_source(
                async_source,
                target=target,
                filename=f"async_tasks_{target}.rove",
            )
            assert not result.success, f"{target} silently accepted unsupported Task semantics"
            assert result.diagnostics and result.diagnostics[0].code == "E3001"

        dynamic_condition_source = """
fn dynamic(value) { return value }
fn main() {
    if dynamic(1) { print("truthiness leaked") }
}
"""
        for target in ("cpp", "js", "python"):
            result = compiler.compile_source(
                dynamic_condition_source,
                target=target,
                filename="dynamic_condition.rove",
            )
            assert result.success, result.diagnostics
            assert result.artifact is not None
            runtime = _run_artifact_process(target, result.artifact.content, directory)
            assert runtime.returncode != 0, f"{target} accepted non-bool dynamic truthiness"
            error_output = runtime.stderr + runtime.stdout
            assert "Rove condition must have type bool" in error_output, (target, error_output)

    immutable = compiler.check_source(
        "let fixed: int = 1\nset fixed = 2\n",
        target="cpp",
        filename="immutable.rove",
    )
    assert not immutable.success
    assert any(
        diagnostic.code == "HIR0007" and "constant 'fixed'" in diagnostic.message
        for diagnostic in immutable.diagnostics
    )

    for keyword in RESERVED_KEYWORDS:
        reserved = compiler.check_source(
            f'{keyword} "not implemented"\n',
            target="cpp",
            filename=f"reserved_{keyword}.rove",
        )
        assert not reserved.success, f"reserved keyword unexpectedly compiled: {keyword}"

    sync_await = compiler.check_source(
        "async fn compute() -> int { return 1 } fn bad() -> int { return await compute() }",
        target="cpp",
        filename="sync_await.rove",
    )
    assert not sync_await.success
    assert any(diagnostic.code == "E2010" for diagnostic in sync_await.diagnostics)

    non_task_await = compiler.check_source(
        "async fn bad() -> int { return await 1 }",
        target="cpp",
        filename="non_task_await.rove",
    )
    assert not non_task_await.success
    assert any(diagnostic.code == "E2011" for diagnostic in non_task_await.diagnostics)

    for source in (
        "let invalid: int = 9223372036854775808",
        "let invalid: int = -9223372036854775809",
    ):
        invalid_integer = compiler.check_source(
            source,
            target="cpp",
            filename="invalid_integer_literal.rove",
        )
        assert not invalid_integer.success
        assert any(diagnostic.code == "E2012" for diagnostic in invalid_integer.diagnostics)

    for source in (
        "if 1 { print(\"invalid\") }",
        "while \"yes\" { break }",
        "fn invalid() { guard 1 else { return } }",
    ):
        invalid_condition = compiler.check_source(
            source,
            target="cpp",
            filename="invalid_condition.rove",
        )
        assert not invalid_condition.success
        assert any(diagnostic.code == "E2013" for diagnostic in invalid_condition.diagnostics)

    invalid_traits = (
        (
            "trait Show { fn show(self) -> string } struct Point { x: int } "
            "impl Show for Point {}",
            "HIR0007",
        ),
        (
            "trait Show { fn show(self, value: int) -> string } struct Point { x: int } "
            "impl Show for Point { fn show(self, value: string) -> string { return value } }",
            "HIR0006",
        ),
        (
            "trait Show { fn show(self) -> string { return \"default\" } }",
            "HIR0009",
        ),
    )
    for source, expected_code in invalid_traits:
        invalid_trait = compiler.check_source(
            source,
            target="cpp",
            filename="invalid_trait.rove",
        )
        assert not invalid_trait.success
        assert any(diagnostic.code == expected_code for diagnostic in invalid_trait.diagnostics)

    print(
        f"[PASS] {len(STABLE_KEYWORDS)} stable keywords, exact editor contract, "
        "set/let/else-if/throw/Task/i64/trait/dynamic-bool semantics, backend gates, and three-backend runtime parity"
    )
    return True


if __name__ == "__main__":
    sys.exit(0 if run_language_surface_suite() else 1)
