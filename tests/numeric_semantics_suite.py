import os
import shutil
import subprocess
import sys
import tempfile


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


from src import NyxCompiler
from src.codegen.cpp_toolchain import CppToolchain


SOURCE = """
fn rounded_equal(value: float) -> bool {
    return value == 9223372036854775808.0
}

fn main() {
    let max: int = 9223372036854775807
    let min: int = -9223372036854775808
    let hex_min: int = -0x8000000000000000

    print("literal-min:", min, hex_min)
    print("unary-plus:", +max)
    print("const-wrap:", 9223372036854775807 + 1)
    print("max+1:", max + 1)
    print("min-1:", min - 1)
    print("mul:", 3037000500 * 3037000500)
    print("neg-min:", -min)
    print("divmod:", -7 / 3, -7 % 3, 7 / -3, 7 % -3)
    print("min-divmod:", min / -1, min % -1)
    print("bits:", 1 << 63, -1 >> 1, 1 << 64)
    print("parse:", to_int("9223372036854775808"), to_int("-9223372036854775809"))
    print("mixed-wide-eq:", max == 9223372036854775808.0, rounded_equal(max))
    print("bool-string:", to_string(true), to_string(false))

    let promoted: float = 2
    print("mixed:", promoted / 4.0)
    print("len:", len([10, 20, 30]))

    let infinity: float = 1.0 / 0.0
    let not_a_number: float = 0.0 / 0.0
    if infinity > 0.0 { print("float-inf: yes") }
    if not_a_number != not_a_number { print("float-nan: yes") }
    print("float-divrem:", -7.5 / 2.0, -7.5 % 2.0)
    print("float-special:", infinity, not_a_number)
    print("float-format:", 2.0, 0.000001, 0.0000001, -0.0)
    print("float-string:", to_string(2.0), to_string(0.000001), to_string(0.0000001), to_string(-0.0))
}
"""


EXPECTED = """literal-min: -9223372036854775808 -9223372036854775808
unary-plus: 9223372036854775807
const-wrap: -9223372036854775808
max+1: -9223372036854775808
min-1: 9223372036854775807
mul: -9223372036709301616
neg-min: -9223372036854775808
divmod: -2 -1 -2 1
min-divmod: -9223372036854775808 0
bits: -9223372036854775808 -1 1
parse: -9223372036854775808 9223372036854775807
mixed-wide-eq: true true
bool-string: true false
mixed: 0.5
len: 3
float-inf: yes
float-nan: yes
float-divrem: -3.75 -1.5
float-special: inf nan
float-format: 2 0.000001 1e-7 0
float-string: 2 0.000001 1e-7 0"""


def _run(target: str, source: str, directory: str) -> str:
    if target == "cpp":
        cpp_path = os.path.join(directory, "numeric.cpp")
        executable = os.path.join(directory, "numeric.exe" if os.name == "nt" else "numeric")
        with open(cpp_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(source)
        compiled, message = CppToolchain.compile_cpp(cpp_path, executable)
        assert compiled, message
        return_code, output = CppToolchain.run_executable(executable)
        assert return_code == 0, output
        return output

    command = [sys.executable, "-c", source]
    if target == "js":
        node = shutil.which("node")
        assert node is not None, "Node.js is required for numeric parity"
        command = [node, "-e", source]
    result = subprocess.run(
        command,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout


def run_numeric_semantics_suite() -> bool:
    print("=" * 70)
    print("ROVE DETERMINISTIC NUMERIC SEMANTICS")
    print("=" * 70)

    compiler = NyxCompiler(ROOT_DIR)
    outputs = {}
    with tempfile.TemporaryDirectory(prefix="nyx_numeric_semantics_") as directory:
        for target in ("cpp", "js", "python"):
            result = compiler.compile_source(SOURCE, target=target, filename="numeric_semantics.rove")
            assert result.success, result.diagnostics
            assert result.artifact is not None
            output = _run(target, result.artifact.content, directory)
            outputs[target] = output.replace("\r\n", "\n").strip()

    assert outputs == {target: EXPECTED for target in ("cpp", "js", "python")}, outputs
    for literal in (
        "9223372036854775808",
        "-9223372036854775809",
        "0x8000000000000000",
    ):
        rejected = compiler.check_source(
            f"fn main() {{ let invalid: int = {literal} }}",
            target="cpp",
            filename="invalid_integer_literal.rove",
        )
        assert not rejected.success, literal
        assert rejected.diagnostics and rejected.diagnostics[0].code == "E2012", rejected.diagnostics

    print("[PASS] signed i64 literals/arithmetic, IEEE-754, and canonical formatting on 3 backends")
    return True


if __name__ == "__main__":
    sys.exit(0 if run_numeric_semantics_suite() else 1)
