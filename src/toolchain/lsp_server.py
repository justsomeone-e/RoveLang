import sys
import json
import os
import re
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import unquote, urlparse
from pathlib import Path

_root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from src.api import RoveCompiler
from src.core.backend_capabilities import BACKENDS
from src.core.lexer import Lexer
from src.core.tokens import TokenType, Token
from src.core.ast_nodes import (
    EnumDefNode,
    ForNode,
    FunctionDefNode,
    ProgramNode,
    StructDefNode,
    TraitDefNode,
    TryCatchNode,
    TypeAliasNode,
    VarDeclNode,
)
from src.core.completion_catalog import completion_catalog
from src.core.language_surface import (
    EXPERIMENTAL_KEYWORDS,
    RESERVED_KEYWORDS,
    STABLE_KEYWORDS,
    TYPE_NAMES,
)

# Public aliases are retained for clients/tests that import this module.
KEYWORDS = list(STABLE_KEYWORDS)
TYPES = list(TYPE_NAMES)

COMPLETION_CATALOG = completion_catalog()
BUILTINS = [
    {
        "label": entry["label"],
        "detail": entry["detail"],
        "doc": entry["documentation"],
    }
    for entry in COMPLETION_CATALOG["builtinFunctions"]
]

SEMANTIC_TOKEN_TYPES = [
    "keyword",      # 0
    "type",         # 1
    "function",     # 2
    "variable",     # 3
    "parameter",    # 4
    "property",     # 5
    "string",       # 6
    "number",       # 7
    "operator",     # 8
    "comment",      # 9
]

SEMANTIC_TOKEN_MODIFIERS = [
    "declaration",     # 1 << 0 = 1
    "defaultLibrary",  # 1 << 1 = 2
]

OPERATOR_TYPES = {
    TokenType.PLUS, TokenType.MINUS, TokenType.MUL, TokenType.DIV, TokenType.MOD,
    TokenType.ASSIGN, TokenType.EQ, TokenType.NEQ, TokenType.GTE, TokenType.LTE,
    TokenType.GT, TokenType.LT, TokenType.ARROW, TokenType.FAT_ARROW, TokenType.PIPE,
    TokenType.SAFE_NAV, TokenType.NULL_COALESCE, TokenType.SHL, TokenType.SHR,
    TokenType.BIT_OR, TokenType.BIT_AND, TokenType.BIT_XOR, TokenType.BIT_NOT
}


class LspSymbolIndex:
    def __init__(self, uri: str, text: str, ast: Optional[ProgramNode]):
        self.uri = uri
        self.text = text
        self.ast = ast
        self.lines = text.splitlines()
        try:
            self.tokens = Lexer(text, "<lsp>").tokenize()
        except Exception:
            self.tokens = []

        # Function info: name -> {"node": ..., "line": ..., "span": (start, end), "params": [...], "local_vars": {...}}
        self.functions: Dict[str, Dict[str, Any]] = {}
        # Global declarations: name -> {"kind": ..., "node": ...}
        self.globals: Dict[str, Dict[str, Any]] = {}
        # Struct fields: struct_name -> list of field_names
        self.struct_fields: Dict[str, List[str]] = {}

        self._index_declarations()

    def _token_range(self, t: Token) -> dict:
        line_0 = max(0, t.line - 1)
        line_str = self.lines[line_0] if line_0 < len(self.lines) else ""
        val_str = str(t.value)
        col_0 = max(0, t.col - 1)
        start_char = len(line_str[:col_0].encode("utf-16-le")) // 2
        end_char = len(line_str[:col_0 + len(val_str)].encode("utf-16-le")) // 2
        return {
            "start": {"line": line_0, "character": start_char},
            "end": {"line": line_0, "character": end_char},
        }

    def _collect_local_vars(self, body: List[Any]) -> set:
        names = set()
        if not isinstance(body, list):
            return names
        for stmt in body:
            if isinstance(stmt, VarDeclNode):
                names.add(stmt.name)
            elif hasattr(stmt, "names") and isinstance(stmt.names, (list, set, tuple)):
                names.update(stmt.names)
            elif isinstance(stmt, ForNode):
                if hasattr(stmt, "var_name") and stmt.var_name:
                    names.add(stmt.var_name)
                if hasattr(stmt, "body") and isinstance(stmt.body, list):
                    names.update(self._collect_local_vars(stmt.body))
            elif isinstance(stmt, TryCatchNode):
                if hasattr(stmt, "err_name") and stmt.err_name:
                    names.add(stmt.err_name)
                if hasattr(stmt, "try_body") and isinstance(stmt.try_body, list):
                    names.update(self._collect_local_vars(stmt.try_body))
                if hasattr(stmt, "catch_body") and isinstance(stmt.catch_body, list):
                    names.update(self._collect_local_vars(stmt.catch_body))
            elif hasattr(stmt, "body") and isinstance(stmt.body, list):
                names.update(self._collect_local_vars(stmt.body))
            elif hasattr(stmt, "then_branch") and isinstance(stmt.then_branch, list):
                names.update(self._collect_local_vars(stmt.then_branch))
                if hasattr(stmt, "else_branch") and isinstance(stmt.else_branch, list):
                    names.update(self._collect_local_vars(stmt.else_branch))
        return names

    def _index_declarations(self):
        if self.ast and hasattr(self.ast, "statements"):
            for s in self.ast.statements:
                if isinstance(s, FunctionDefNode):
                    param_names = [
                        p.name if hasattr(p, "name") else (p[0] if isinstance(p, tuple) else str(p))
                        for p in getattr(s, "params", [])
                    ]
                    local_vars = self._collect_local_vars(getattr(s, "body", []))
                    self.functions[s.name] = {
                        "node": s,
                        "line": getattr(s, "line", 1),
                        "params": param_names,
                        "local_vars": local_vars,
                    }
                    self.globals[s.name] = {"kind": "function", "node": s}
                elif isinstance(s, StructDefNode):
                    fields = [
                        f.name if hasattr(f, "name") else (f[0] if isinstance(f, tuple) else str(f))
                        for f in getattr(s, "fields", [])
                    ]
                    self.struct_fields[s.name] = fields
                    self.globals[s.name] = {"kind": "struct", "node": s}
                elif isinstance(s, TraitDefNode):
                    self.globals[s.name] = {"kind": "trait", "node": s}
                elif isinstance(s, EnumDefNode):
                    self.globals[s.name] = {"kind": "enum", "node": s}
                elif isinstance(s, TypeAliasNode):
                    self.globals[s.name] = {"kind": "type_alias", "node": s}
                elif isinstance(s, VarDeclNode):
                    self.globals[s.name] = {"kind": "variable", "node": s}

        # Discover function spans via lexer tokens
        i = 0
        while i < len(self.tokens):
            t = self.tokens[i]
            if t.type == TokenType.FN and i + 1 < len(self.tokens):
                fn_name = str(self.tokens[i + 1].value)
                j = i + 1
                while j < len(self.tokens) and self.tokens[j].type != TokenType.LBRACE:
                    j += 1
                if j < len(self.tokens):
                    depth = 1
                    j += 1
                    while j < len(self.tokens) and depth > 0:
                        if self.tokens[j].type == TokenType.LBRACE:
                            depth += 1
                        elif self.tokens[j].type == TokenType.RBRACE:
                            depth -= 1
                        j += 1
                    end_line = self.tokens[j - 1].line if j > 0 else t.line
                    if fn_name in self.functions:
                        self.functions[fn_name]["span"] = (t.line, end_line)
                    else:
                        self.functions[fn_name] = {
                            "span": (t.line, end_line),
                            "params": [],
                            "local_vars": set(),
                        }
                    i = j
                    continue
            i += 1

    def find_token_at(self, line_0: int, char_0: int) -> Tuple[int, Optional[Token]]:
        candidates = []
        for i, t in enumerate(self.tokens):
            if t.type == TokenType.EOF or t.line - 1 != line_0:
                continue
            trange = self._token_range(t)
            s = trange["start"]["character"]
            e = trange["end"]["character"]
            if s <= char_0 <= e:
                candidates.append((i, t, s, e))

        if not candidates:
            return -1, None

        strict = [c for c in candidates if c[2] <= char_0 < c[3]]
        ident_strict = [c for c in strict if c[1].type == TokenType.IDENT]
        if ident_strict:
            return ident_strict[0][0], ident_strict[0][1]

        idents = [c for c in candidates if c[1].type == TokenType.IDENT]
        if idents:
            return idents[0][0], idents[0][1]

        if strict:
            return strict[0][0], strict[0][1]

        return candidates[0][0], candidates[0][1]

    def find_symbol_at(self, line_0: int, char_0: int) -> Optional[Dict[str, Any]]:
        target_index, target_token = self.find_token_at(line_0, char_0)
        if not target_token:
            return None

        word = str(target_token.value)
        is_builtin = any(b["label"] == word for b in BUILTINS) or word in TYPE_NAMES
        is_keyword = (
            word in STABLE_KEYWORDS or
            word in EXPERIMENTAL_KEYWORDS or
            word in RESERVED_KEYWORDS or
            target_token.type in (
                TokenType.FN, TokenType.RETURN, TokenType.VAR, TokenType.LET,
                TokenType.CONST, TokenType.STRUCT, TokenType.IF, TokenType.ELSE,
                TokenType.WHILE, TokenType.FOR, TokenType.PRINT
            )
        )
        if is_keyword:
            return {"name": word, "kind": "keyword", "range": self._token_range(target_token)}
        if is_builtin:
            return {"name": word, "kind": "builtin", "range": self._token_range(target_token)}

        if target_token.type != TokenType.IDENT:
            return None

        is_member = target_index > 0 and (
            self.tokens[target_index - 1].type == TokenType.DOT or
            self.tokens[target_index - 1].value == "?."
        )

        enclosing_fn = None
        for fn_name, fn_info in self.functions.items():
            span = fn_info.get("span", (fn_info.get("line", 1), 999999))
            if span[0] <= target_token.line <= span[1]:
                enclosing_fn = fn_name
                break

        if is_member:
            kind = "property"
            scope = "property"
            scope_names = set()
            for fields in self.struct_fields.values():
                scope_names.update(fields)
        elif enclosing_fn and (
            word in self.functions[enclosing_fn].get("params", []) or
            word in self.functions[enclosing_fn].get("local_vars", set())
        ):
            kind = "parameter" if word in self.functions[enclosing_fn].get("params", []) else "local"
            scope = f"function::{enclosing_fn}"
            scope_names = (
                set(self.functions[enclosing_fn].get("params", [])) |
                self.functions[enclosing_fn].get("local_vars", set())
            )
        elif word in self.globals:
            kind = self.globals[word]["kind"]
            scope = "global"
            scope_names = set(self.globals.keys())
        else:
            found_field = False
            for sname, fields in self.struct_fields.items():
                if word in fields:
                    kind = "property"
                    scope = "property"
                    scope_names = set()
                    for f in self.struct_fields.values():
                        scope_names.update(f)
                    found_field = True
                    break
            if not found_field:
                kind = "identifier"
                scope = "global"
                scope_names = set(self.globals.keys())

        return {
            "name": word,
            "kind": kind,
            "scope": scope,
            "scope_names": scope_names,
            "enclosing_fn": enclosing_fn,
            "range": self._token_range(target_token),
            "is_member": is_member,
        }

    def find_references(self, symbol_info: Dict[str, Any], include_decl: bool = True) -> List[dict]:
        if symbol_info["kind"] in ("keyword", "builtin"):
            return []

        word = symbol_info["name"]
        kind = symbol_info["kind"]
        scope = symbol_info["scope"]
        enclosing_fn = symbol_info.get("enclosing_fn")

        locations = []
        for i, t in enumerate(self.tokens):
            if t.type != TokenType.IDENT or str(t.value) != word:
                continue

            t_is_member = i > 0 and (
                self.tokens[i - 1].type == TokenType.DOT or
                self.tokens[i - 1].value == "?."
            )

            if kind == "property":
                is_field_def = i > 0 and self.tokens[i - 1].type in (TokenType.LBRACE, TokenType.COMMA)
                if t_is_member or is_field_def:
                    locations.append({"uri": self.uri, "range": self._token_range(t)})
                continue

            if t_is_member:
                continue

            if scope.startswith("function::"):
                target_fn = scope.split("::", 1)[1]
                fn_info = self.functions.get(target_fn, {})
                span = fn_info.get("span", (fn_info.get("line", 1), 999999))
                if span[0] <= t.line <= span[1]:
                    locations.append({"uri": self.uri, "range": self._token_range(t)})
            else:
                # Global reference: check if shadowed by a local symbol
                shadowed = False
                for fn_name, fn_info in self.functions.items():
                    span = fn_info.get("span", (fn_info.get("line", 1), 999999))
                    if span[0] <= t.line <= span[1]:
                        if word in fn_info.get("params", []) or word in fn_info.get("local_vars", set()):
                            shadowed = True
                            break
                if not shadowed:
                    locations.append({"uri": self.uri, "range": self._token_range(t)})

        if not include_decl and locations:
            locations = locations[1:]
        return locations

    def semantic_tokens(self) -> List[int]:
        raw_tokens = []
        for i, t in enumerate(self.tokens):
            if t.type == TokenType.EOF:
                continue
            line_0 = max(0, t.line - 1)
            line_str = self.lines[line_0] if line_0 < len(self.lines) else ""
            val_str = str(t.value)
            col_0 = max(0, t.col - 1)
            start_char = len(line_str[:col_0].encode("utf-16-le")) // 2
            length = len(val_str.encode("utf-16-le")) // 2

            t_type = None
            t_mod = 0

            if t.type == TokenType.DOC_COMMENT:
                t_type = 9  # comment
            elif t.type == TokenType.STRING:
                t_type = 6  # string
            elif t.type == TokenType.NUMBER:
                t_type = 7  # number
            elif t.type in OPERATOR_TYPES or val_str in ("+", "-", "*", "/", "=", "==", "!=", "->", "=>"):
                t_type = 8  # operator
            elif (
                t.type in (
                    TokenType.FN, TokenType.RETURN, TokenType.VAR, TokenType.LET,
                    TokenType.CONST, TokenType.STRUCT, TokenType.IF, TokenType.ELSE,
                    TokenType.WHILE, TokenType.FOR, TokenType.MATCH, TokenType.TRY,
                    TokenType.CATCH, TokenType.IN, TokenType.IMPORT, TokenType.TRAIT,
                    TokenType.ENUM, TokenType.TYPE_ALIAS, TokenType.DEFER, TokenType.ASYNC,
                    TokenType.AWAIT, TokenType.YIELD, TokenType.BREAK, TokenType.CONTINUE,
                    TokenType.PRINT
                ) or
                val_str in STABLE_KEYWORDS or
                val_str in EXPERIMENTAL_KEYWORDS or
                val_str in RESERVED_KEYWORDS
            ):
                t_type = 0  # keyword
            elif val_str in TYPE_NAMES:
                t_type = 1  # type
                t_mod = 2  # defaultLibrary
            elif t.type == TokenType.IDENT:
                prev_t = self.tokens[i - 1] if i > 0 else None
                next_t = self.tokens[i + 1] if i + 1 < len(self.tokens) else None
                if prev_t and prev_t.type in (TokenType.STRUCT, TokenType.TRAIT, TokenType.ENUM, TokenType.TYPE_ALIAS):
                    t_type = 1  # type
                    t_mod = 1  # declaration
                elif prev_t and (prev_t.type == TokenType.DOT or prev_t.value == "?."):
                    t_type = 5  # property
                elif prev_t and prev_t.type == TokenType.FN:
                    t_type = 2  # function
                    t_mod = 1  # declaration
                elif prev_t and prev_t.type in (TokenType.VAR, TokenType.LET, TokenType.CONST):
                    t_type = 3  # variable
                    t_mod = 1  # declaration
                elif next_t and next_t.type == TokenType.LPAREN:
                    t_type = 2  # function
                    if any(b["label"] == val_str for b in BUILTINS):
                        t_mod = 2  # defaultLibrary
                elif any(b["label"] == val_str for b in BUILTINS):
                    t_type = 2  # function
                    t_mod = 2  # defaultLibrary
                else:
                    t_type = 3  # variable

            if t_type is not None and length > 0:
                raw_tokens.append((line_0, start_char, length, t_type, t_mod))

        raw_tokens.sort(key=lambda x: (x[0], x[1]))

        data = []
        prev_line = 0
        prev_char = 0
        for line, col, length, t_type, t_mods in raw_tokens:
            delta_line = line - prev_line
            delta_char = col if delta_line > 0 else col - prev_char
            data.extend([delta_line, delta_char, length, t_type, t_mods])
            prev_line = line
            prev_char = col

        return data


class LanguageServer:
    def __init__(self):
        self.documents: Dict[str, str] = {}
        self.parsed_asts: Dict[str, ProgramNode] = {}
        self.symbol_indices: Dict[str, LspSymbolIndex] = {}

    def read_message(self) -> Optional[dict]:
        headers = {}
        while True:
            line = sys.stdin.buffer.readline().decode('utf-8')
            if not line or line == '\r\n' or line == '\n':
                break
            if ':' in line:
                k, v = line.split(':', 1)
                headers[k.strip().lower()] = v.strip()

        if 'content-length' not in headers:
            return None

        length = int(headers['content-length'])
        body = sys.stdin.buffer.read(length).decode('utf-8')
        return json.loads(body)

    def send_response(self, response_dict: dict):
        body = json.dumps(response_dict)
        header = f"Content-Length: {len(body.encode('utf-8'))}\r\nContent-Type: application/json-rpc; charset=utf-8\r\n\r\n"
        sys.stdout.buffer.write(header.encode('utf-8'))
        sys.stdout.buffer.write(body.encode('utf-8'))
        sys.stdout.buffer.flush()

    def send_diagnostics(self, uri: str, diagnostics: list):
        self.send_response({
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {
                "uri": uri,
                "diagnostics": diagnostics
            }
        })

    def get_fs_path(self, uri: str) -> str:
        parsed = urlparse(uri)
        path = unquote(parsed.path) if parsed.scheme == "file" else uri
        if parsed.netloc:
            path = f"//{parsed.netloc}{path}"
        if os.name == 'nt' and path.startswith("/") and len(path) > 2 and path[2] == ':':
            path = path[1:]
        return os.path.normpath(path)

    def validate_document(self, uri: str, text: str):
        filepath = self.get_fs_path(uri)
        base_dir = os.path.dirname(os.path.abspath(filepath)) if filepath else os.getcwd()
        result = RoveCompiler(base_dir).check_source(text, filename=filepath)
        diagnostics = []
        if result.success and result.ast is not None:
            self.parsed_asts[uri] = result.ast
            self.symbol_indices[uri] = LspSymbolIndex(uri, text, result.ast)
        else:
            self.parsed_asts.pop(uri, None)
            self.symbol_indices[uri] = LspSymbolIndex(uri, text, None)
            for diagnostic in result.diagnostics:
                line = max(0, diagnostic.line - 1)
                col = max(0, diagnostic.column - 1)
                source_lines = text.splitlines()
                source_line = source_lines[line] if line < len(source_lines) else ""
                start = len(source_line[:col].encode("utf-16-le")) // 2
                end = len(source_line[:col + diagnostic.length].encode("utf-16-le")) // 2
                message = f"[{diagnostic.code}] {diagnostic.message}"
                if diagnostic.expected:
                    message += f"\nExpected: {diagnostic.expected}"
                if diagnostic.found:
                    message += f"\nFound: {diagnostic.found}"
                if diagnostic.help:
                    message += f"\nHelp: {diagnostic.help}"
                if diagnostic.note:
                    message += f"\nNote: {diagnostic.note}"
                diagnostics.append({
                    "range": {
                        "start": {"line": line, "character": start},
                        "end": {"line": line, "character": end}
                    },
                    "severity": 1,
                    "code": diagnostic.code,
                    "source": "rove",
                    "message": message
                })

        self.send_diagnostics(uri, diagnostics)

    def get_symbol_index(self, uri: str) -> LspSymbolIndex:
        if uri not in self.symbol_indices:
            text = self.documents.get(uri, "")
            ast = self.parsed_asts.get(uri)
            self.symbol_indices[uri] = LspSymbolIndex(uri, text, ast)
        return self.symbol_indices[uri]

    def get_word_at_position(self, text: str, line_idx: int, char_idx: int) -> str:
        lines = text.splitlines()
        if line_idx < 0 or line_idx >= len(lines) or char_idx < 0:
            return ""
        line = lines[line_idx]
        # LSP defaults to UTF-16 code units; Python indexes Unicode code points.
        char_idx = len(line.encode("utf-16-le")[:char_idx * 2].decode("utf-16-le", errors="ignore"))
        if char_idx >= len(line):
            char_idx = len(line) - 1
        if char_idx < 0:
            return ""

        # Find word boundaries
        start = char_idx
        while start > 0 and (line[start - 1].isalnum() or line[start - 1] == '_'):
            start -= 1
        end = char_idx
        while end < len(line) and (line[end].isalnum() or line[end] == '_'):
            end += 1
        return line[start:end]

    def handle_hover(self, uri: str, pos: dict) -> Optional[dict]:
        text = self.documents.get(uri, "")
        word = self.get_word_at_position(text, pos.get("line", 0), pos.get("character", 0))
        if not word:
            return None

        # Check builtins
        for b in BUILTINS:
            if b["label"] == word:
                return {
                    "contents": {
                        "kind": "markdown",
                        "value": f"```rove\n{b['detail']}\n```\n\n{b['doc']}"
                    }
                }

        # Check types
        if word in TYPES:
            return {
                "contents": {
                    "kind": "markdown",
                    "value": f"```rove\ntype {word}\n```\n\nRove primitive/built-in type."
                }
            }

        # Search AST declarations
        ast = self.parsed_asts.get(uri)
        if ast:
            for s in ast.statements:
                if isinstance(s, FunctionDefNode) and s.name == word:
                    params_s = ", ".join(self._format_param(p) for p in s.params)
                    ret_s = f" -> {s.return_type}" if s.return_type else ""
                    return {
                        "contents": {
                            "kind": "markdown",
                            "value": f"```rove\nfn {s.name}({params_s}){ret_s}\n```"
                        }
                    }
                elif isinstance(s, StructDefNode) and s.name == word:
                    fields_s = ", ".join(self._format_param(f) for f in s.fields)
                    return {
                        "contents": {
                            "kind": "markdown",
                            "value": f"```rove\nstruct {s.name} {{ {fields_s} }}\n```"
                        }
                    }

        return None

    def _format_param(self, p: Any) -> str:
        if isinstance(p, tuple):
            return f"{p[0]}: {p[1]}" if len(p) > 1 and p[1] else str(p[0])
        if hasattr(p, "name"):
            type_node = getattr(p, "type_annot", None) or getattr(p, "type_node", None)
            t = getattr(type_node, "name", str(type_node)) if type_node else ""
            return f"{p.name}: {t}" if t else p.name
        return str(p)

    def handle_completion(self, uri: str, pos: dict) -> list:
        items = []

        # 1. Directives
        target_names = "|".join(BACKENDS)
        items.append({"label": "#target", "kind": 15, "detail": f"#target <{target_names}>", "documentation": "Sets compiler backend target"})
        items.append({"label": "#native include", "kind": 15, "detail": "#native include <header>", "documentation": "Includes C/C++ native header"})
        items.append({"label": "#native link", "kind": 15, "detail": '#native link "lib"', "documentation": "Links system library"})
        items.append({"label": "#native raw", "kind": 15, "detail": "#native raw { ... }", "documentation": "Inline C++ code block"})
        items.append({"label": "#native use", "kind": 15, "detail": '#native use "namespace"', "documentation": "Using namespace directive"})

        # 1. Keywords
        for kw in KEYWORDS:
            items.append({"label": kw, "kind": 14, "detail": "Rove stable keyword"})
        for kw in EXPERIMENTAL_KEYWORDS:
            items.append({
                "label": kw,
                "kind": 14,
                "detail": "Rove experimental keyword",
                "documentation": "Parsed by the frontend; cross-target semantics are not stable yet.",
            })

        # 2. Builtins
        for b in BUILTINS:
            items.append({"label": b["label"], "kind": 3, "detail": b["detail"], "documentation": b["doc"]})

        # 3. Types
        for t in TYPES:
            items.append({"label": t, "kind": 7, "detail": "Type"})

        # 4. AST Functions and Structs (including imported ones)
        ast = self.parsed_asts.get(uri)
        if ast:
            for s in ast.statements:
                if isinstance(s, FunctionDefNode):
                    params_s = ", ".join(self._format_param(p) for p in s.params)
                    ret_s = f" -> {s.return_type}" if s.return_type else ""
                    items.append({
                        "label": s.name,
                        "kind": 3,  # Function
                        "detail": f"fn {s.name}({params_s}){ret_s}",
                        "documentation": f"Declared in {getattr(s, '_origin_module', 'local file')}"
                    })
                elif isinstance(s, StructDefNode):
                    items.append({
                        "label": s.name,
                        "kind": 22,  # Struct
                        "detail": f"struct {s.name}",
                        "documentation": f"Declared in {getattr(s, '_origin_module', 'local file')}"
                    })

        # 5. Canonical standard-library catalog.
        for module in COMPLETION_CATALOG["stdlibModules"]:
            items.append({
                "label": module["name"],
                "kind": 9,
                "detail": module["detail"],
                "documentation": module["documentation"],
            })
        for symbol in COMPLETION_CATALOG["stdlibSymbols"]:
            kind = {
                "function": 3,
                "struct": 22,
                "enum": 13,
                "type": 7,
                "constant": 21,
            }.get(symbol["kind"], 1)
            items.append({
                "label": symbol["label"],
                "kind": kind,
                "detail": f"{symbol['detail']} · {symbol['module']}",
                "documentation": symbol["documentation"],
                "data": {"module": symbol["module"]},
            })

        # 6. Target and physical-board IDs
        for target in COMPLETION_CATALOG["targets"]:
            items.append({
                "label": target["name"],
                "kind": 20,
                "detail": target["detail"],
                "documentation": target["documentation"],
            })
        for board in COMPLETION_CATALOG["boards"]:
            items.append({
                "label": board["name"],
                "kind": 20,
                "detail": board["detail"],
                "documentation": board["documentation"],
            })

        # 7. Text fallback: keep local declarations visible while parser is broken
        text = self.documents.get(uri, "")
        source_patterns = (
            (r"\b(?:async\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*(?:->\s*([^\s{=]+))?", 3, "fn {0}({1}){2}"),
            (r"\bstruct\s+([A-Za-z_][A-Za-z0-9_]*)", 22, "struct {0}"),
            (r"\btrait\s+([A-Za-z_][A-Za-z0-9_]*)", 8, "trait {0}"),
            (r"\benum\s+([A-Za-z_][A-Za-z0-9_]*)", 13, "enum {0}"),
            (r"\btype\s+([A-Za-z_][A-Za-z0-9_]*)", 7, "type {0}"),
            (r"\b(?:var|let|const)\s+([A-Za-z_][A-Za-z0-9_]*)", 6, "local {0}"),
        )
        for pattern, kind, template in source_patterns:
            for match in re.finditer(pattern, text):
                groups = match.groups()
                if kind == 3:
                    suffix = f" -> {groups[2]}" if groups[2] else ""
                    detail = template.format(groups[0], groups[1], suffix)
                else:
                    detail = template.format(groups[0])
                items.append({
                    "label": groups[0],
                    "kind": kind,
                    "detail": detail,
                    "documentation": "Declared in the current document.",
                })

        # Deduplicate while preserving order
        deduplicated = []
        seen = set()
        for item in items:
            label = item["label"]
            if label in seen:
                continue
            seen.add(label)
            deduplicated.append(item)
        return deduplicated

    def handle_definition(self, uri: str, pos: dict) -> Optional[dict]:
        text = self.documents.get(uri, "")
        word = self.get_word_at_position(text, pos.get("line", 0), pos.get("character", 0))
        if not word:
            return None

        ast = self.parsed_asts.get(uri)
        if ast:
            for s in ast.statements:
                if isinstance(s, (FunctionDefNode, StructDefNode, TraitDefNode)) and getattr(s, "name", None) == word:
                    target_file = getattr(s, "_origin_module", self.get_fs_path(uri))
                    target_uri = Path(target_file).resolve().as_uri()
                    try:
                        line_no = max(0, int(getattr(s, "line", 1)) - 1)
                    except Exception:
                        line_no = 0
                    try:
                        col_no = max(0, int(getattr(s, "col", 1)) - 1)
                    except Exception:
                        col_no = 0
                    return {
                        "uri": target_uri,
                        "range": {
                            "start": {"line": line_no, "character": col_no},
                            "end": {"line": line_no, "character": col_no + len(word)}
                        }
                    }

        return None

    def handle_references(self, uri: str, pos: dict, context: Optional[dict] = None) -> list:
        index = self.get_symbol_index(uri)
        sym = index.find_symbol_at(pos.get("line", 0), pos.get("character", 0))
        if not sym or sym["kind"] in ("keyword", "builtin"):
            return []

        include_decl = context.get("includeDeclaration", True) if context else True
        locations = list(index.find_references(sym, include_decl=include_decl))

        # If it's a global symbol or property, also look in other open documents
        if sym["scope"] in ("global", "property"):
            for other_uri, other_text in self.documents.items():
                if other_uri == uri:
                    continue
                other_index = self.get_symbol_index(other_uri)
                other_refs = other_index.find_references(sym, include_decl=True)
                locations.extend(other_refs)

        return locations

    def handle_prepare_rename(self, uri: str, pos: dict) -> Optional[dict]:
        index = self.get_symbol_index(uri)
        sym = index.find_symbol_at(pos.get("line", 0), pos.get("character", 0))
        if not sym or sym["kind"] in ("keyword", "builtin"):
            return None
        return {"range": sym["range"], "placeholder": sym["name"]}

    def handle_rename(self, uri: str, pos: dict, new_name: str) -> dict:
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", new_name):
            return {"error": {"code": -32602, "message": f"Invalid identifier name '{new_name}'"}}
        if (
            new_name in STABLE_KEYWORDS or
            new_name in EXPERIMENTAL_KEYWORDS or
            new_name in RESERVED_KEYWORDS
        ):
            return {"error": {"code": -32602, "message": f"Cannot rename to reserved keyword '{new_name}'"}}
        if any(b["label"] == new_name for b in BUILTINS) or new_name in TYPE_NAMES:
            return {"error": {"code": -32602, "message": f"Cannot rename to built-in symbol or type '{new_name}'"}}

        index = self.get_symbol_index(uri)
        sym = index.find_symbol_at(pos.get("line", 0), pos.get("character", 0))
        if not sym:
            return {"error": {"code": -32602, "message": "No symbol found at position"}}
        if sym["kind"] in ("keyword", "builtin"):
            return {"error": {"code": -32602, "message": f"Cannot rename {sym['kind']} '{sym['name']}'"}}

        if new_name in sym.get("scope_names", set()):
            return {"error": {"code": -32602, "message": f"Symbol '{new_name}' is already declared in this scope"}}

        refs = self.handle_references(uri, pos, {"includeDeclaration": True})
        changes: Dict[str, List[dict]] = {}
        for r in refs:
            changes.setdefault(r["uri"], []).append({
                "range": r["range"],
                "newText": new_name,
            })
        return {"changes": changes}

    def handle_semantic_tokens(self, uri: str) -> dict:
        index = self.get_symbol_index(uri)
        data = index.semantic_tokens()
        return {"data": data}

    def run(self):
        while True:
            msg = self.read_message()
            if not msg:
                break

            method = msg.get("method")
            msg_id = msg.get("id")
            params = msg.get("params", {})

            if method == "initialize":
                self.send_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "capabilities": {
                            "textDocumentSync": 1,
                            "hoverProvider": True,
                            "completionProvider": {
                                "resolveProvider": False,
                                "triggerCharacters": [".", ":", ">", "\"", "{", "#", " ", "<", "/"]
                            },
                            "definitionProvider": True,
                            "referencesProvider": True,
                            "renameProvider": {
                                "prepareProvider": True
                            },
                            "semanticTokensProvider": {
                                "legend": {
                                    "tokenTypes": SEMANTIC_TOKEN_TYPES,
                                    "tokenModifiers": SEMANTIC_TOKEN_MODIFIERS
                                },
                                "full": True
                            }
                        }
                    }
                })
            elif method == "textDocument/didOpen":
                doc = params.get("textDocument", {})
                uri = doc.get("uri")
                text = doc.get("text", "")
                self.documents[uri] = text
                self.validate_document(uri, text)
            elif method == "textDocument/didChange":
                doc = params.get("textDocument", {})
                uri = doc.get("uri")
                changes = params.get("contentChanges", [])
                if changes:
                    text = changes[-1].get("text", "")
                    self.documents[uri] = text
                    self.validate_document(uri, text)
            elif method == "textDocument/didClose":
                uri = params.get("textDocument", {}).get("uri", "")
                self.documents.pop(uri, None)
                self.parsed_asts.pop(uri, None)
                self.symbol_indices.pop(uri, None)
                self.send_diagnostics(uri, [])
            elif method == "textDocument/hover":
                doc = params.get("textDocument", {})
                pos = params.get("position", {})
                hover_res = self.handle_hover(doc.get("uri", ""), pos)
                self.send_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": hover_res
                })
            elif method == "textDocument/completion":
                doc = params.get("textDocument", {})
                pos = params.get("position", {})
                comp_items = self.handle_completion(doc.get("uri", ""), pos)
                self.send_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": comp_items
                })
            elif method == "textDocument/definition":
                doc = params.get("textDocument", {})
                pos = params.get("position", {})
                def_res = self.handle_definition(doc.get("uri", ""), pos)
                self.send_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": def_res
                })
            elif method == "textDocument/references":
                doc = params.get("textDocument", {})
                pos = params.get("position", {})
                context = params.get("context", {})
                refs = self.handle_references(doc.get("uri", ""), pos, context)
                self.send_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": refs
                })
            elif method == "textDocument/prepareRename":
                doc = params.get("textDocument", {})
                pos = params.get("position", {})
                prep_res = self.handle_prepare_rename(doc.get("uri", ""), pos)
                self.send_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": prep_res
                })
            elif method == "textDocument/rename":
                doc = params.get("textDocument", {})
                pos = params.get("position", {})
                new_name = params.get("newName", "")
                rename_res = self.handle_rename(doc.get("uri", ""), pos, new_name)
                if "error" in rename_res:
                    self.send_response({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": rename_res["error"]
                    })
                else:
                    self.send_response({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": rename_res
                    })
            elif method == "textDocument/semanticTokens/full":
                doc = params.get("textDocument", {})
                tokens_res = self.handle_semantic_tokens(doc.get("uri", ""))
                self.send_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": tokens_res
                })
            elif method == "shutdown":
                self.send_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": None
                })
            elif method == "exit":
                sys.exit(0)
            elif msg_id is not None:
                self.send_response({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not supported: {method}"},
                })


# Backwards compatibility for integrations that imported the original typo.
RoveLanguageServer = LanguageServer
NyxLanguageServer = LanguageServer
NyxuageServer = LanguageServer


if __name__ == "__main__":
    LanguageServer().run()
