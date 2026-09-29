import sys
from typing import List, Any
from .tokens import TokenType, Token
from .diagnostics import DiagnosticEmitter
from .language_surface import KEYWORD_TOKEN_TYPES

class Lexer:
    def __init__(self, source: str, filepath: str = "<memory>"):
        self.source = source.lstrip('\ufeff')
        self.filepath = filepath
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: List[Token] = []

    def error(self, msg: str):
        DiagnosticEmitter.emit_error(self.filepath, self.source, self.line, self.col, "E0001", "Lexer Error", help_msg=msg)

    def tokenize(self) -> List[Token]:
        length = len(self.source)
        while self.pos < length:
            ch = self.source[self.pos]

            if ch == '\n':
                self.line += 1
                self.col = 1
                self.pos += 1
                continue
            if ch.isspace():
                self.col += 1
                self.pos += 1
                continue

            # Doc comment ///
            if self.source[self.pos:self.pos+3] == "///":
                start_col = self.col
                self.pos += 3; self.col += 3
                start_doc = self.pos
                while self.pos < length and self.source[self.pos] != '\n':
                    self.pos += 1; self.col += 1
                doc_text = self.source[start_doc:self.pos].strip()
                self.tokens.append(Token(TokenType.DOC_COMMENT, doc_text, self.line, start_col))
                continue

            # Line comment //
            if self.source[self.pos:self.pos+2] == "//":
                while self.pos < length and self.source[self.pos] != '\n':
                    self.pos += 1
                continue

            # Block comment /* ... */
            if self.source[self.pos:self.pos+2] == "/*":
                self.pos += 2; self.col += 2
                while self.pos + 1 < length and not (self.source[self.pos] == '*' and self.source[self.pos + 1] == '/'):
                    if self.source[self.pos] == '\n':
                        self.line += 1; self.col = 1
                    else:
                        self.col += 1
                    self.pos += 1
                if self.pos + 1 >= length:
                    self.error("Unterminated block comment")
                self.pos += 2; self.col += 2
                continue

            # Directives: #target and #native
            if ch == '#' and self.source[self.pos:self.pos+7] == "#target":
                start_col = self.col
                self.pos += 7; self.col += 7
                while self.pos < length and self.source[self.pos].isspace() and self.source[self.pos] != '\n':
                    self.pos += 1; self.col += 1
                start_val = self.pos
                while self.pos < length and (self.source[self.pos].isalnum() or self.source[self.pos] == '_'):
                    self.pos += 1; self.col += 1
                target_val = self.source[start_val:self.pos]
                self.tokens.append(Token(TokenType.TARGET_DIR, target_val, self.line, start_col))
                continue

            if ch == '#' and self.source[self.pos:self.pos+7] == "#native":
                start_col = self.col
                self.pos += 7; self.col += 7
                while self.pos < length and self.source[self.pos].isspace() and self.source[self.pos] != '\n':
                    self.pos += 1; self.col += 1
                
                # 1. #native include <stdio.h> / "header.h"
                if self.source[self.pos:self.pos+7] == "include":
                    self.pos += 7; self.col += 7
                    while self.pos < length and self.source[self.pos].isspace() and self.source[self.pos] != '\n':
                        self.pos += 1; self.col += 1
                    start_hdr = self.pos
                    while self.pos < length and self.source[self.pos] != '\n' and self.source[self.pos] != ';':
                        self.pos += 1; self.col += 1
                    hdr = self.source[start_hdr:self.pos].strip()
                    self.tokens.append(Token(TokenType.NATIVE_INCLUDE, hdr, self.line, start_col))
                    continue

                # 2. #native link "lib" / user32
                if self.source[self.pos:self.pos+4] == "link":
                    self.pos += 4; self.col += 4
                    while self.pos < length and self.source[self.pos].isspace() and self.source[self.pos] != '\n':
                        self.pos += 1; self.col += 1
                    start_lib = self.pos
                    while self.pos < length and self.source[self.pos] != '\n' and self.source[self.pos] != ';':
                        self.pos += 1; self.col += 1
                    lib = self.source[start_lib:self.pos].strip().strip('"\'')
                    self.tokens.append(Token(TokenType.NATIVE_LINK, lib, self.line, start_col))
                    continue

                # 3. #native use namespace std / std::vector
                if self.source[self.pos:self.pos+3] == "use" and (self.pos + 3 >= length or self.source[self.pos+3].isspace()):
                    self.pos += 3; self.col += 3
                    while self.pos < length and self.source[self.pos].isspace() and self.source[self.pos] != '\n':
                        self.pos += 1; self.col += 1
                    start_use = self.pos
                    while self.pos < length and self.source[self.pos] != '\n' and self.source[self.pos] != ';':
                        self.pos += 1; self.col += 1
                    use_target = self.source[start_use:self.pos].strip()
                    self.tokens.append(Token(TokenType.NATIVE_USE, use_target, self.line, start_col))
                    continue

                # 4. #native raw { ... } or the documented C++ alias
                native_block_keyword = None
                if self.source[self.pos:self.pos+3] == "raw":
                    native_block_keyword = "raw"
                elif self.source[self.pos:self.pos+3] == "cpp":
                    native_block_keyword = "cpp"
                if native_block_keyword is not None:
                    self.pos += 3; self.col += 3
                    while self.pos < length and self.source[self.pos].isspace():
                        if self.source[self.pos] == '\n':
                            self.line += 1
                            self.col = 1
                        else:
                            self.col += 1
                        self.pos += 1
                    if self.pos < length and self.source[self.pos] == '{':
                        self.pos += 1
                        self.col += 1
                        brace_depth = 1
                        start_raw = self.pos
                        while self.pos < length and brace_depth > 0:
                            ch = self.source[self.pos]
                            if ch == '{':
                                brace_depth += 1
                            elif ch == '}':
                                brace_depth -= 1
                                if brace_depth == 0:
                                    break
                            if ch == '\n':
                                self.line += 1
                                self.col = 1
                            else:
                                self.col += 1
                            self.pos += 1
                        raw_body = self.source[start_raw:self.pos].strip()
                        if self.pos < length and self.source[self.pos] == '}':
                            self.pos += 1
                            self.col += 1
                        self.tokens.append(Token(TokenType.NATIVE_RAW, raw_body, self.line, start_col))
                        continue

                start_raw = self.pos
                while self.pos < length and self.source[self.pos] != '\n':
                    self.pos += 1; self.col += 1
                raw = self.source[start_raw:self.pos].strip()
                if raw.startswith(("raw ", "cpp ")):
                    raw = raw[4:].strip()
                self.tokens.append(Token(TokenType.NATIVE_RAW, raw, self.line, start_col))
                continue

            # Multi-character symbols
            if self.source[self.pos:self.pos+2] == "?.":
                self.tokens.append(Token(TokenType.SAFE_NAV, "?.", self.line, self.col))
                self.pos += 2; self.col += 2; continue
            if self.source[self.pos:self.pos+2] == "??":
                self.tokens.append(Token(TokenType.NULL_COALESCE, "??", self.line, self.col))
                self.pos += 2; self.col += 2; continue
            if self.source[self.pos:self.pos+2] == "=>":
                self.tokens.append(Token(TokenType.FAT_ARROW, "=>", self.line, self.col))
                self.pos += 2; self.col += 2; continue
            if self.source[self.pos:self.pos+2] == "->":
                self.tokens.append(Token(TokenType.ARROW, "->", self.line, self.col))
                self.pos += 2; self.col += 2; continue
            if self.source[self.pos:self.pos+2] == "|>":
                self.tokens.append(Token(TokenType.PIPE, "|>", self.line, self.col))
                self.pos += 2; self.col += 2; continue
            if self.source[self.pos:self.pos+2] == "..":
                self.tokens.append(Token(TokenType.DOTDOT, "..", self.line, self.col))
                self.pos += 2; self.col += 2; continue
            if self.source[self.pos:self.pos+2] == "==":
                self.tokens.append(Token(TokenType.EQ, "==", self.line, self.col))
                self.pos += 2; self.col += 2; continue
            if self.source[self.pos:self.pos+2] == "!=":
                self.tokens.append(Token(TokenType.NEQ, "!=", self.line, self.col))
                self.pos += 2; self.col += 2; continue
            if self.source[self.pos:self.pos+2] == ">=":
                self.tokens.append(Token(TokenType.GTE, ">=", self.line, self.col))
                self.pos += 2; self.col += 2; continue
            if self.source[self.pos:self.pos+2] == "<=":
                self.tokens.append(Token(TokenType.LTE, "<=", self.line, self.col))
                self.pos += 2; self.col += 2; continue
            if self.source[self.pos:self.pos+2] == "<<":
                self.tokens.append(Token(TokenType.SHL, "<<", self.line, self.col))
                self.pos += 2; self.col += 2; continue
            if self.source[self.pos:self.pos+2] == ">>":
                self.tokens.append(Token(TokenType.SHR, ">>", self.line, self.col))
                self.pos += 2; self.col += 2; continue
            if self.source[self.pos:self.pos+2] == "&&":
                self.tokens.append(Token(TokenType.AND, "and", self.line, self.col))
                self.pos += 2; self.col += 2; continue
            if self.source[self.pos:self.pos+2] == "||":
                self.tokens.append(Token(TokenType.OR, "or", self.line, self.col))
                self.pos += 2; self.col += 2; continue

            # String Interpolation: $"Hello {name}!"
            if ch == '$' and self.pos + 1 < length and self.source[self.pos + 1] in ('"', "'"):
                start_col = self.col
                self.pos += 1; self.col += 1
                quote = self.source[self.pos]
                self.pos += 1; self.col += 1
                
                parts = []
                buf = []
                while self.pos < length and self.source[self.pos] != quote:
                    if self.source[self.pos] == '\\' and self.pos + 1 < length:
                        esc = self.source[self.pos + 1]
                        if esc == 'n': buf.append('\n')
                        elif esc == 't': buf.append('\t')
                        elif esc == 'r': buf.append('\r')
                        elif esc == '0': buf.append('\0')
                        elif esc == '\\': buf.append('\\')
                        elif esc == '{': buf.append('{')
                        elif esc == quote: buf.append(quote)
                        else: buf.append(esc)
                        self.pos += 2; self.col += 2
                    elif self.source[self.pos] == '{':
                        str_val = "".join(buf)
                        buf = []
                        parts.append(('str', str_val))
                        self.pos += 1; self.col += 1
                        expr_buf = []
                        b_depth = 1
                        while self.pos < length and b_depth > 0:
                            if self.source[self.pos] == '{':
                                b_depth += 1
                            elif self.source[self.pos] == '}':
                                b_depth -= 1
                                if b_depth == 0:
                                    break
                            expr_buf.append(self.source[self.pos])
                            if self.source[self.pos] == '\n':
                                self.line += 1; self.col = 1
                            else:
                                self.col += 1
                            self.pos += 1
                        if self.pos < length and self.source[self.pos] == '}':
                            self.pos += 1; self.col += 1
                        expr_code = "".join(expr_buf).strip()
                        if expr_code:
                            parts.append(('expr', expr_code))
                    else:
                        if self.source[self.pos] == '\n':
                            self.line += 1; self.col = 1
                        else:
                            self.col += 1
                        buf.append(self.source[self.pos])
                        self.pos += 1
                if self.pos >= length:
                    self.error("Unterminated interpolated string literal")
                self.pos += 1; self.col += 1
                parts.append(('str', "".join(buf)))

                self.tokens.append(Token(TokenType.LPAREN, "(", self.line, start_col))
                first = True
                for ptype, pval in parts:
                    if ptype == 'str':
                        if not first:
                            self.tokens.append(Token(TokenType.PLUS, "+", self.line, start_col))
                        self.tokens.append(Token(TokenType.STRING, pval, self.line, start_col))
                        first = False
                    elif ptype == 'expr':
                        if not first:
                            self.tokens.append(Token(TokenType.PLUS, "+", self.line, start_col))
                        sub_lexer = Lexer(f"to_string({pval})", self.filepath)
                        sub_tokens = [t for t in sub_lexer.tokenize() if t.type != TokenType.EOF]
                        self.tokens.extend(sub_tokens)
                        first = False
                self.tokens.append(Token(TokenType.RPAREN, ")", self.line, start_col))
                continue

            # Strings
            if ch in ('"', "'"):
                quote = ch
                start_col = self.col
                self.pos += 1; self.col += 1
                buf = []
                while self.pos < length and self.source[self.pos] != quote:
                    if self.source[self.pos] == '\\' and self.pos + 1 < length:
                        esc = self.source[self.pos + 1]
                        if esc == 'n': buf.append('\n')
                        elif esc == 't': buf.append('\t')
                        elif esc == 'r': buf.append('\r')
                        elif esc == '0': buf.append('\0')
                        elif esc == 'u' and self.pos + 5 < length:
                            hex_digits = self.source[self.pos+2:self.pos+6]
                            try:
                                buf.append(chr(int(hex_digits, 16)))
                                self.pos += 6; self.col += 6
                                continue
                            except:
                                buf.append('u')
                        elif esc == '\\': buf.append('\\')
                        elif esc == quote: buf.append(quote)
                        else: buf.append(esc)
                        self.pos += 2; self.col += 2
                    else:
                        if self.source[self.pos] == '\n':
                            self.line += 1; self.col = 1
                        else:
                            self.col += 1
                        buf.append(self.source[self.pos])
                        self.pos += 1
                if self.pos >= length:
                    self.error("Unterminated string literal")
                self.pos += 1; self.col += 1
                self.tokens.append(Token(TokenType.STRING, "".join(buf), self.line, start_col))
                continue

            # Numbers
            if ch.isdigit() or (ch == '.' and self.pos + 1 < length and self.source[self.pos + 1].isdigit()):
                start_col = self.col
                start_pos = self.pos
                if ch == '0' and self.pos + 1 < length and self.source[self.pos + 1] in ('x', 'X'):
                    self.pos += 2; self.col += 2
                    hex_start = self.pos
                    while self.pos < length and (self.source[self.pos].isdigit() or self.source[self.pos] in "abcdefABCDEF"):
                        self.pos += 1; self.col += 1
                    if self.pos == hex_start:
                        self.error("Invalid hexadecimal literal '0x' missing digits")
                    val = int(self.source[start_pos:self.pos], 16)
                    self.tokens.append(Token(TokenType.NUMBER, val, self.line, start_col))
                    continue

                is_float = False
                dot_count = 0
                while self.pos < length and (self.source[self.pos].isdigit() or self.source[self.pos] == '.'):
                    if self.source[self.pos] == '.':
                        if self.pos + 1 < length and self.source[self.pos + 1] == '.':
                            break
                        dot_count += 1
                        if dot_count > 1:
                            self.error(f"Invalid floating-point literal with multiple decimal points")
                        is_float = True
                    self.pos += 1; self.col += 1
                raw_num = self.source[start_pos:self.pos]
                val = float(raw_num) if is_float else int(raw_num)
                self.tokens.append(Token(TokenType.NUMBER, val, self.line, start_col))
                continue

            # Identifiers & Keywords ($ accepted)
            if ch.isalpha() or ch == '_' or ch == '$':
                start_col = self.col
                start_pos = self.pos
                while self.pos < length and (self.source[self.pos].isalnum() or self.source[self.pos] in ('_', '$')):
                    self.pos += 1; self.col += 1
                ident = self.source[start_pos:self.pos]
                clean = ident.lstrip('$')

                if clean in KEYWORD_TOKEN_TYPES:
                    tt = KEYWORD_TOKEN_TYPES[clean]
                    v = True if clean == "true" else (False if clean == "false" else (None if clean == "null" else clean))
                    self.tokens.append(Token(tt, v, self.line, start_col))
                else:
                    self.tokens.append(Token(TokenType.IDENT, clean, self.line, start_col))
                continue

            single = {
                '=': TokenType.ASSIGN, '+': TokenType.PLUS, '-': TokenType.MINUS,
                '*': TokenType.MUL, '/': TokenType.DIV, '%': TokenType.MOD,
                '>': TokenType.GT, '<': TokenType.LT, '!': TokenType.NOT,
                '|': TokenType.BIT_OR, '&': TokenType.BIT_AND, '^': TokenType.BIT_XOR, '~': TokenType.BIT_NOT,
                '(': TokenType.LPAREN, ')': TokenType.RPAREN,
                '[': TokenType.LBRACKET, ']': TokenType.RBRACKET,
                '{': TokenType.LBRACE, '}': TokenType.RBRACE,
                ',': TokenType.COMMA, ':': TokenType.COLON, '.': TokenType.DOT,
                '?': TokenType.QUESTION, ';': TokenType.SEMICOLON
            }
            if ch in single:
                self.tokens.append(Token(single[ch], ch, self.line, self.col))
                self.pos += 1; self.col += 1
                continue

            self.error(f"Unexpected character: '{ch}'")

        self.tokens.append(Token(TokenType.EOF, "EOF", self.line, self.col))
        return self.tokens
