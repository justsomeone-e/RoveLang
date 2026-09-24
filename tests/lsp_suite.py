import json
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_PATH = os.path.join(BASE_DIR, "src", "cli.py")
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from src.toolchain.lsp_server import NyxuageServer
from src.core.language_surface import (
    EXPERIMENTAL_KEYWORDS,
    RESERVED_KEYWORDS,
    STABLE_KEYWORDS,
)

def run_lsp_suite():
    print("=" * 70)
    print("⚡ NYX LSP v2 IDE SERVICE HARNESS")
    print("=" * 70)

    server = NyxuageServer()
    diagnostics = []
    server.send_diagnostics = lambda uri, items: diagnostics.append((uri, items))
    unicode_source = 'print("😀"); var value: int = missing'
    unicode_uri = "file:///unicode.rove"
    server.validate_document(unicode_uri, unicode_source)
    diagnostic = diagnostics[-1][1][0]
    assert "Help:" in diagnostic["message"] and "outside its scope" in diagnostic["message"]
    expected_column = len(unicode_source[:unicode_source.index("missing")].encode("utf-16-le")) // 2
    assert diagnostic["range"]["start"]["character"] == expected_column
    assert server.get_word_at_position(unicode_source, 0, expected_column) == "missing"
    assert server.get_word_at_position(unicode_source, -1, 0) == ""
    test_uri = "file:///C:/test_project/main.rove"
    test_code = """import "std/math"

struct Point { x: int, y: int }

fn calculate_distance(p1: Point, p2: Point) -> float {
    var dx = abs(p1.x - p2.x)
    var dy = abs(p1.y - p2.y)
    return dx + dy
}

var pt = Point(10, 20)
print(calculate_distance(pt, pt))
"""
    server.documents[test_uri] = test_code
    server.validate_document(test_uri, test_code)

    # 1. Test Autocompletion
    print("[*] Testing LSP Autocompletion (Local & stdlib imported symbols)...")
    comp_items = server.handle_completion(test_uri, {"line": 10, "character": 5})
    labels = [item["label"] for item in comp_items]
    assert "abs" in labels, "Imported stdlib function 'abs' must appear in completions"
    assert "pow" in labels, "Imported stdlib function 'pow' must appear in completions"
    assert "Point" in labels, "Local struct 'Point' must appear in completions"
    assert "calculate_distance" in labels, "Local function 'calculate_distance' must appear in completions"
    assert "print" in labels and "match" in labels
    for canonical_label in (
        "append_string",
        "fnv1a_64_hex",
        "cpp",
        "args",
    ):
        assert canonical_label in labels, f"Missing canonical completion: {canonical_label}"
    assert len(comp_items) >= 140, "Canonical completion catalog unexpectedly shrank"
    assert set(STABLE_KEYWORDS).issubset(labels)
    assert set(EXPERIMENTAL_KEYWORDS).issubset(labels)
    assert set(RESERVED_KEYWORDS).isdisjoint(labels)
    assert "val" not in labels

    with open(os.path.join(BASE_DIR, "vscode-extension", "language-surface.json"), "r", encoding="utf-8") as handle:
        editor_surface = json.load(handle)
    assert tuple(editor_surface["stableKeywords"]) == STABLE_KEYWORDS
    assert tuple(editor_surface["experimentalKeywords"]) == EXPERIMENTAL_KEYWORDS
    assert tuple(editor_surface["reservedKeywords"]) == RESERVED_KEYWORDS
    print(f"  [PASS] Autocompletion returned {len(comp_items)} verified symbols")

    incomplete_uri = "file:///C:/test_project/incomplete.rove"
    incomplete_source = "fn local_helper(value: int) -> int {\n    let local_value = value +\n"
    server.documents[incomplete_uri] = incomplete_source
    server.validate_document(incomplete_uri, incomplete_source)
    incomplete_labels = {
        item["label"]
        for item in server.handle_completion(incomplete_uri, {"line": 1, "character": 28})
    }
    assert "local_helper" in incomplete_labels
    assert "local_value" in incomplete_labels
    print("  [PASS] Half-written source keeps local declarations available")

    # 2. Test Hover Information
    print("[*] Testing LSP Hover Tooltips...")
    hover_fn = server.handle_hover(test_uri, {"line": 4, "character": 5})  # 'calculate_distance'
    assert hover_fn is not None and "calculate_distance" in hover_fn["contents"]["value"]
    hover_struct = server.handle_hover(test_uri, {"line": 2, "character": 8})  # 'Point'
    assert hover_struct is not None and "struct Point" in hover_struct["contents"]["value"]
    hover_builtin = server.handle_hover(test_uri, {"line": 11, "character": 2})  # 'print'
    assert hover_builtin is not None and "Writes values" in hover_builtin["contents"]["value"]
    print("  [PASS] Hover cards correctly formatted Markdown signatures")

    # 3. Test Go To Definition
    print("[*] Testing LSP Go-To-Definition...")
    def_res = server.handle_definition(test_uri, {"line": 11, "character": 8})  # 'calculate_distance'
    assert def_res is not None
    assert def_res["range"]["start"]["line"] == 4, "Should point to line 5 (0-indexed 4)"
    print("  [PASS] Go-To-Definition resolved exact AST source location")

    # 4. Test References (45-LSP)
    print("[*] Testing LSP Find References...")
    refs_fn = server.handle_references(test_uri, {"line": 4, "character": 5}, {"includeDeclaration": True})
    assert len(refs_fn) == 2, f"Expected 2 references to calculate_distance, got {len(refs_fn)}"
    refs_fn_no_decl = server.handle_references(test_uri, {"line": 4, "character": 5}, {"includeDeclaration": False})
    assert len(refs_fn_no_decl) == 1
    refs_dx = server.handle_references(test_uri, {"line": 5, "character": 9}, {"includeDeclaration": True})
    assert len(refs_dx) == 2
    refs_kw = server.handle_references(test_uri, {"line": 4, "character": 1})
    assert refs_kw == []
    print("  [PASS] References resolved declarations, callsites, and function scopes")

    # 5. Test Prepare Rename & Rename (45-LSP)
    print("[*] Testing LSP Prepare Rename & Rename...")
    prep_fn = server.handle_prepare_rename(test_uri, {"line": 4, "character": 5})
    assert prep_fn is not None and prep_fn["placeholder"] == "calculate_distance"
    prep_kw = server.handle_prepare_rename(test_uri, {"line": 4, "character": 1})
    assert prep_kw is None
    prep_builtin = server.handle_prepare_rename(test_uri, {"line": 11, "character": 2})
    assert prep_builtin is None

    # Rename function
    res_fn = server.handle_rename(test_uri, {"line": 4, "character": 5}, "calc_dist")
    assert "changes" in res_fn and len(res_fn["changes"][test_uri]) == 2
    # Rename local variable
    res_dx = server.handle_rename(test_uri, {"line": 5, "character": 9}, "delta_x")
    assert "changes" in res_dx and len(res_dx["changes"][test_uri]) == 2
    # Reject scope collision: dx -> dy
    res_coll = server.handle_rename(test_uri, {"line": 5, "character": 9}, "dy")
    assert "error" in res_coll and "already declared" in res_coll["error"]["message"]
    # Reject keyword rename: dx -> let
    res_kw = server.handle_rename(test_uri, {"line": 5, "character": 9}, "let")
    assert "error" in res_kw and "reserved keyword" in res_kw["error"]["message"]
    # Reject builtin rename: print -> my_print
    res_b = server.handle_rename(test_uri, {"line": 11, "character": 2}, "my_print")
    assert "error" in res_b and "Cannot rename" in res_b["error"]["message"]
    print("  [PASS] Rename verified placeholder ranges, workspace edits, collisions, and rejections")

    # 6. Test Semantic Tokens (45-LSP)
    print("[*] Testing LSP Semantic Tokens...")
    sem_res = server.handle_semantic_tokens(test_uri)
    assert "data" in sem_res and len(sem_res["data"]) > 0
    assert len(sem_res["data"]) % 5 == 0, "Semantic tokens array must be multiple of 5"
    print(f"  [PASS] Semantic tokens delta encoding returned {len(sem_res['data']) // 5} tokens")

    # 7. Verify the real CLI process speaks framed JSON-RPC without import errors.
    print("[*] Testing CLI LSP JSON-RPC process contract...")
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {"textDocument": {"uri": test_uri, "text": test_code}}},
        {"jsonrpc": "2.0", "id": 2, "method": "textDocument/references", "params": {"textDocument": {"uri": test_uri}, "position": {"line": 4, "character": 5}, "context": {"includeDeclaration": True}}},
        {"jsonrpc": "2.0", "id": 3, "method": "textDocument/prepareRename", "params": {"textDocument": {"uri": test_uri}, "position": {"line": 4, "character": 5}}},
        {"jsonrpc": "2.0", "id": 4, "method": "textDocument/rename", "params": {"textDocument": {"uri": test_uri}, "position": {"line": 4, "character": 5}, "newName": "calc_dist"}},
        {"jsonrpc": "2.0", "id": 5, "method": "textDocument/semanticTokens/full", "params": {"textDocument": {"uri": test_uri}}},
        {"jsonrpc": "2.0", "id": 6, "method": "workspace/executeCommand", "params": {"command": "nonexistent"}},
        {"jsonrpc": "2.0", "id": 7, "method": "shutdown", "params": {}},
        {"jsonrpc": "2.0", "method": "exit", "params": {}},
    ]
    wire_input = b""
    for message in messages:
        body = json.dumps(message).encode("utf-8")
        wire_input += f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
    process = subprocess.run(
        [sys.executable, CLI_PATH, "lsp"],
        cwd=BASE_DIR,
        input=wire_input,
        capture_output=True,
    )
    assert process.returncode == 0, process.stderr.decode("utf-8", errors="replace")
    output = process.stdout
    assert b'"id": 1' in output and b'"hoverProvider": true' in output
    assert b'"referencesProvider": true' in output
    assert b'"semanticTokensProvider"' in output
    assert b'"id": 2' in output and b'"range"' in output
    assert b'"id": 3' in output and b'"placeholder": "calculate_distance"' in output
    assert b'"id": 4' in output and b'"calc_dist"' in output
    assert b'"id": 5' in output and b'"data"' in output
    assert b'"id": 6' in output and b'"code": -32601' in output
    assert b'"id": 7' in output and b'"result": null' in output
    print("  [PASS] nyx lsp full wire JSON-RPC protocol verified")

    print("=" * 70)
    print("[OK] LSP v2 Conformance: 7/7 Passed")
    print("=" * 70)
    return True

if __name__ == "__main__":
    ok = run_lsp_suite()
    sys.exit(0 if ok else 1)
