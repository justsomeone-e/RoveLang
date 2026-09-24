"""Canonical Rove language-surface metadata.

This module is intentionally data-only.  The lexer, LSP, editor contract
tests, and documentation checks consume the same status classification so a
reserved spelling cannot accidentally be advertised as a working feature.
"""

from .tokens import TokenType


STABLE_KEYWORD_GROUPS = {
    "declaration": (
        "var", "let", "set", "const", "fn", "struct", "trait", "impl",
        "type", "enum", "extern",
    ),
    "control-flow": (
        "if", "elif", "else", "for", "in", "loop", "while", "match",
        "try", "catch", "throw", "yield", "return", "break", "continue", "await",
    ),
    "scope-and-safety": ("defer", "guard", "unsafe"),
    "concurrency": ("spawn", "async"),
    "modules": ("use", "import", "from", "as"),
    "testing": ("test", "assert"),
    "operators": ("and", "or", "not"),
    "literals": ("true", "false", "null"),
}

STABLE_KEYWORDS = tuple(
    keyword
    for keywords in STABLE_KEYWORD_GROUPS.values()
    for keyword in keywords
)

EXPERIMENTAL_KEYWORDS = ()

# These spellings are reserved by both lexers.  They are deliberately absent
# from normal completion until parser, HIR, and backend semantics exist.
RESERVED_KEYWORDS = ()

LEGACY_KEYWORD_ALIASES = {}

# These are lexed specially for compatibility with the original frontend, but
# are callable runtime names rather than statement/declaration keywords.
BUILTIN_NAMES = (
    "print", "input", "addr", "peek", "memdump", "channel", "Ok", "Err",
    "len", "args", "to_string", "to_int", "contains",
    "is_number", "delay_ms", "map", "filter", "fold",
)

TYPE_NAMES = (
    "int", "i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64",
    "float", "f32", "f64", "bool", "string", "char", "uintptr", "void", "any",
    "Array", "Iterator", "Option", "Result", "Channel", "Task",
)

KEYWORD_TOKEN_TYPES = {
    "var": TokenType.VAR,
    "let": TokenType.LET,
    "set": TokenType.SET,
    "const": TokenType.CONST,
    "fn": TokenType.FN,
    "struct": TokenType.STRUCT,
    "trait": TokenType.TRAIT,
    "impl": TokenType.IMPL,
    "type": TokenType.TYPE_ALIAS,
    "enum": TokenType.ENUM,
    "unsafe": TokenType.UNSAFE,
    "extern": TokenType.EXTERN,
    "async": TokenType.ASYNC,
    "await": TokenType.AWAIT,
    "spawn": TokenType.SPAWN,
    "channel": TokenType.CHANNEL,
    "test": TokenType.TEST,
    "assert": TokenType.ASSERT,
    "return": TokenType.RETURN,
    "continue": TokenType.CONTINUE,
    "break": TokenType.BREAK,
    "defer": TokenType.DEFER,
    "guard": TokenType.GUARD,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "elif": TokenType.ELIF,
    "for": TokenType.FOR,
    "in": TokenType.IN,
    "loop": TokenType.LOOP,
    "while": TokenType.WHILE,
    "match": TokenType.MATCH,
    "try": TokenType.TRY,
    "catch": TokenType.CATCH,
    "throw": TokenType.THROW,
    "yield": TokenType.YIELD,
    "use": TokenType.USE,
    "import": TokenType.IMPORT,
    "from": TokenType.FROM,
    "as": TokenType.AS,
    "print": TokenType.PRINT,
    "input": TokenType.INPUT,
    "addr": TokenType.ADDR,
    "peek": TokenType.PEEK,
    "memdump": TokenType.MEMDUMP,
    "and": TokenType.AND,
    "or": TokenType.OR,
    "not": TokenType.NOT,
    "true": TokenType.BOOLEAN,
    "false": TokenType.BOOLEAN,
    "null": TokenType.NULL,
}


def keyword_status(keyword: str) -> str:
    if keyword in STABLE_KEYWORDS:
        return "stable"
    if keyword in EXPERIMENTAL_KEYWORDS:
        return "experimental"
    if keyword in RESERVED_KEYWORDS:
        return "reserved"
    if keyword in LEGACY_KEYWORD_ALIASES:
        return "legacy"
    raise KeyError(keyword)
