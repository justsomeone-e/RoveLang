import json
import os
import shutil
import sys
import tempfile


if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)


from src.codegen.codegen import UniversalCodeGen
from src.codegen.cpp_toolchain import CppToolchain
from src.core.lexer import Lexer as PyLexer
from src.core.language_surface import KEYWORD_TOKEN_TYPES
from src.core.parser import Parser
from src.core.tokens import TokenType


def _wire_escape(value: str) -> str:
    """Encode token text without losing embedded controls or UTF-8 data."""
    result = []
    for char in value:
        if char == "\\":
            result.append("\\\\")
        elif char == "\n":
            result.append("\\n")
        elif char == "\r":
            result.append("\\r")
        elif char == "\t":
            result.append("\\t")
        elif char == "\0":
            result.append("\\0")
        else:
            result.append(char)
    return "".join(result)


def _canonical_python_value(token) -> str:
    if token.type == TokenType.BOOLEAN:
        return "true" if token.value else "false"
    if token.type == TokenType.NULL:
        return "null"
    return str(token.value)


def _build_native_driver(base_lexer_code: str, test_sources) -> str:
    sections = [
        base_lexer_code,
        r'''
fn lexer_wire_escape(value: string) -> string {
    var result = ""
    for i in 0..len(value)-1 {
        var ch = value[i]
        if ch == "\\" { result = result + "\\\\" }
        elif ch == "\n" { result = result + "\\n" }
        elif ch == "\r" { result = result + "\\r" }
        elif ch == "\t" { result = result + "\\t" }
        elif ch == "\0" { result = result + "\\0" }
        else { result = result + ch }
    }
    return result
}

fn emit_lexer_case(case_name: string, source: string) {
    print("__NYX_CASE__\t" + case_name)
    var lexer = Lexer(lexer_characters(source), 0, 1, 1)
    var tokens = lexer.tokenize()
    for token in tokens {
        if token.type_name != "EOF" {
            print("__NYX_TOKEN__\t" + token.type_name + "\t" + lexer_wire_escape(token.value))
        }
    }
}
'''.strip(),
        "fn main() {",
    ]
    for name, source in test_sources:
        sections.append(
            f"    emit_lexer_case({json.dumps(name)}, {json.dumps(source, ensure_ascii=False)})"
        )
    sections.extend(["}", "", "main()", ""])
    return "\n\n".join(sections)


def _parse_native_stream(output: str):
    streams = {}
    current_case = None
    for line in output.splitlines():
        if line.startswith("__NYX_CASE__\t"):
            current_case = line.split("\t", 1)[1]
            streams[current_case] = []
            continue
        if line.startswith("__NYX_TOKEN__\t"):
            if current_case is None:
                raise AssertionError("Native lexer emitted a token before a case marker")
            fields = line.split("\t", 2)
            if len(fields) != 3:
                raise AssertionError(f"Malformed native token record: {line!r}")
            streams[current_case].append((fields[1], fields[2]))
    return streams


def run_bootstrap_lexer_test() -> bool:
    print("=" * 70)
    print("NYX SELF-HOST LEXER EXACT TYPE+VALUE PARITY")
    print("=" * 70)

    lexer_nyx_path = os.path.join(_root_dir, "compiler", "lexer.rove")
    with open(lexer_nyx_path, "r", encoding="utf-8") as handle:
        lexer_nyx_code = handle.read()

    if "fn main()" in lexer_nyx_code:
        base_lexer_code = lexer_nyx_code[: lexer_nyx_code.index("fn main()")].strip()
    else:
        base_lexer_code = lexer_nyx_code.strip()

    test_sources = [
        ("basic_math", 'var x: int = 100 + 20; print("Result:", x)'),
        (
            "block_and_doc_comments",
            "/* multiline\nblock comment */\n///   doc comment with trim   \t\n// line comment\nvar a = 10;",
        ),
        (
            "escaped_strings_and_controls",
            'var s1 = "line\\n tab\\t carriage\\r nul\\0 slash\\\\ quote\\\""; var s2 = \'single\\\'quote\';',
        ),
        (
            "unicode_literals_and_escapes",
            'var direct = "İstanbul 🌙 çığ ğüşö"; var nfc = "é"; var nfd = "e\\u0301";',
        ),
        (
            "canonical_numbers",
            "var a = 0007; var b = 0xFF; var c = 0X0a; var d = .500; var e = 001.2300; var f = 1.0;",
        ),
        (
            "ranges_and_operators",
            'for i in 0..10 { if a >= 10 && b != 20 || c == 30 { var s = val ?? "default"; var bits = (a << 2) | (b >> 1) & ~c ^ 3; } }',
        ),
        (
            "pipeline_and_arrows",
            "var res = x |> double |> add; fn cb(x: int) -> int; (a, b) => a + b; obj?.field;",
        ),
        (
            "extended_keywords",
            "async await spawn channel test assert defer guard throw input true false null unsafe extern type enum trait impl set const loop while match try catch continue break",
        ),
        ("complete_keyword_surface", " ".join(KEYWORD_TOKEN_TYPES)),
        ("removed_aliases_are_identifiers", "def val"),
        ("dollar_identifier_normalization", "$gold $$gold nyx$destructure$1"),
        (
            "native_directives_and_ffi",
            '#target cpp\n#native include <vector>\n#native link "user32.lib"\n#native use std::vector;\n#native raw int x = 42;\nextern "C" fn puts(s: string) -> int',
        ),
        (
            "native_raw_nested_block",
            "#native raw {\nint choose(int x) { if (x > 0) { return x; } return 0; }\n}",
        ),
        (
            "native_cpp_block_alias",
            "#native cpp {\n#include <cmath>\ndouble native_sin(double x) { return std::sin(x); }\n}",
        ),
        (
            "struct_and_impl",
            "struct Point { x: int, y: int }\nimpl Point { fn dist(self) -> int { return self.x + self.y } }",
        ),
        ("utf8_bom", "\ufeffvar after_bom = 42"),
    ]

    expected = {}
    for name, source in test_sources:
        py_tokens = PyLexer(source, f"{name}.rove").tokenize()
        expected[name] = [
            (token.type, _wire_escape(_canonical_python_value(token)))
            for token in py_tokens
            if token.type != TokenType.EOF
        ]

    driver_source = _build_native_driver(base_lexer_code, test_sources)
    temp_dir = tempfile.mkdtemp(prefix="nyx_test_lexer_exact_")
    exe_file = os.path.join(temp_dir, "nyx_lexer.exe")
    cpp_file = os.path.join(temp_dir, "nyx_lexer.cpp")
    try:
        driver_tokens = PyLexer(driver_source, "bootstrap_lexer_driver.rove").tokenize()
        driver_ast = Parser(
            driver_tokens, driver_source, "bootstrap_lexer_driver.rove"
        ).parse()
        cpp_code = UniversalCodeGen(driver_ast).gen_cpp()
        with open(cpp_file, "w", encoding="utf-8") as handle:
            handle.write(cpp_code)

        ok, message = CppToolchain.compile_cpp(cpp_file, exe_file)
        if not ok:
            print(f"FAILED: native driver compile error\n{message}")
            return False

        return_code, output = CppToolchain.run_executable(exe_file, timeout=20)
        if return_code != 0:
            print(f"FAILED: native driver exited with {return_code}\n{output}")
            return False

        actual = _parse_native_stream(output)
        all_passed = True
        for name, _source in test_sources:
            py_stream = expected[name]
            nyx_stream = actual.get(name)
            if nyx_stream is None:
                print(f"[FAIL] {name}: missing native case output")
                all_passed = False
                continue
            if py_stream != nyx_stream:
                mismatch_index = next(
                    (
                        index
                        for index, pair in enumerate(zip(py_stream, nyx_stream))
                        if pair[0] != pair[1]
                    ),
                    min(len(py_stream), len(nyx_stream)),
                )
                py_value = (
                    py_stream[mismatch_index]
                    if mismatch_index < len(py_stream)
                    else "<missing>"
                )
                nyx_value = (
                    nyx_stream[mismatch_index]
                    if mismatch_index < len(nyx_stream)
                    else "<missing>"
                )
                print(
                    f"[FAIL] {name}: token {mismatch_index} differs "
                    f"(Python={py_value!r}, Nyx={nyx_value!r}; "
                    f"lengths {len(py_stream)}/{len(nyx_stream)})"
                )
                all_passed = False
            else:
                print(f"[PASS] {name}: {len(py_stream)} exact tokens")

        print("=" * 70)
        print(
            "Exact bootstrap lexer parity: "
            + ("SUCCESS" if all_passed else "FAILURE")
        )
        print("=" * 70)
        return all_passed
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(0 if run_bootstrap_lexer_test() else 1)
