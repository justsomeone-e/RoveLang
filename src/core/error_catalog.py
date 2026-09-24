"""
Rove Diagnostic Error Catalog
Comprehensive knowledge base for compiler error codes, explaining causes and resolutions.
Used by `rove explain <error_code>`.
"""

CATALOG = {
    "E1000": {
        "title": "Unexpected Token in Expression",
        "category": "Syntax Error",
        "description": "The parser encountered a token that cannot begin or continue a valid Rove expression.",
        "bad_example": "var x = + * 5;",
        "good_example": "var x = 10 * 5;",
        "solution": "Check expression operator placement and ensure all operands are provided."
    },
    "E1001": {
        "title": "Unexpected Token / Syntax Error",
        "category": "Syntax Error",
        "description": "A token was found where a different token (such as a parenthesis, comma, or semicolon) was expected.",
        "bad_example": "var x = (10 + 20;",
        "good_example": "var x = (10 + 20);",
        "solution": "Ensure all opened parentheses '(', braces '{', and brackets '[' have matching closing tokens."
    },
    "E1002": {
        "title": "Invalid Type Identifier",
        "category": "Syntax Error",
        "description": "The parser expected a valid primitive or custom type name (such as int, float, string, bool, or a struct name).",
        "bad_example": "var count: 123 = 10;",
        "good_example": "var count: int = 10;",
        "solution": "Specify a valid type name like int, float, string, bool, Array<T>, or a defined Struct."
    },
    "E1003": {
        "title": "Unclosed Generic Argument List",
        "category": "Syntax Error",
        "description": "A generic type argument list was opened with '<' but not closed with '>'.",
        "bad_example": "var items: Array<string = [];",
        "good_example": "var items: Array<string> = [];",
        "solution": "Close the generic type parameter list with '>'."
    },
    "E1004": {
        "title": "Missing Assignment Operator in Variable Declaration",
        "category": "Syntax Error",
        "description": "A variable was declared with 'var' and a type, but the '=' assignment operator was omitted.",
        "bad_example": "var x int 10;",
        "good_example": "var x: int = 10;",
        "solution": "Add a colon ':' before the type and '=' before the initialization value."
    },
    "E1005": {
        "title": "Malformed Import or Test Description",
        "category": "Syntax Error",
        "description": "An import statement was missing the 'from' keyword, or a test block lacked a description string.",
        "bad_example": "import { add } \"math.rove\";",
        "good_example": "import { add } from \"math.rove\";",
        "solution": "Ensure 'import { symbols } from \"path\"' syntax is used."
    },
    "E1006": {
        "title": "Missing Module Path String",
        "category": "Syntax Error",
        "description": "An import statement did not provide a string literal specifying the target module path.",
        "bad_example": "import std/fs;",
        "good_example": "import \"std/fs\";",
        "solution": "Enclose the module path in double quotes, e.g., import \"std/fs\" or import \"./math\"."
    },
    "E1050": {
        "title": "Unsafe Operation Outside Unsafe Block",
        "category": "Safety Violation",
        "description": "Low-level raw pointer, memory manipulation, or FFI call was executed without an enclosing 'unsafe { ... }' block.",
        "bad_example": "var addr = @addr(my_var);",
        "good_example": "unsafe { var addr = @addr(my_var); }",
        "solution": "Wrap all low-level memory operations inside an 'unsafe { ... }' block to mark explicit boundary safety."
    },
    "E1300": {
        "title": "Circular Module Dependency Detected",
        "category": "Module Resolution",
        "description": "Two or more modules mutually import each other in a closed cycle.",
        "bad_example": "A.rove imports B.rove, and B.rove imports A.rove",
        "good_example": "Factor shared structs and types into a third module 'types.rove' imported by both.",
        "solution": "Refactor common dependencies into a shared leaf module to keep the dependency graph a Directed Acyclic Graph (DAG)."
    },
    "E1301": {
        "title": "Module Not Found",
        "category": "Module Resolution",
        "description": "The compiler could not locate the imported file in the standard library or relative to current file.",
        "bad_example": "import \"./non_existent_module\";",
        "good_example": "import \"std/fs\";",
        "solution": "Verify the relative file path or ensure the standard library module name is spelled correctly."
    },
    "E1302": {
        "title": "Ambiguous Symbol Collision in Multi-Module Import",
        "category": "Module Resolution",
        "description": "Two imported modules expose a public symbol with the exact same identifier name into global scope.",
        "bad_example": "import \"std/json\"; import \"my_json\"; // both define 'get_string'",
        "good_example": "Use qualified access or import specific distinct symbols.",
        "solution": "Use selective symbol imports 'import { symbol } from ...' to prevent collisions."
    },
    "E2001": {
        "title": "Variable Declaration Type Mismatch",
        "category": "Type Error",
        "description": "The expression evaluated for variable initialization does not match the explicitly declared type annotation.",
        "bad_example": "var count: int = \"hello\";",
        "good_example": "var count: int = 42;",
        "solution": "Ensure the assigned value matches the declared type, or use explicit conversion."
    },
    "E2002": {
        "title": "Undefined Variable or Scope Leak",
        "category": "Semantic Error",
        "description": "A variable was referenced that was never declared or was declared inside an inaccessible local scope.",
        "bad_example": "fn test() { if true { var x = 10; } return x; }",
        "good_example": "fn test() { var x = 10; return x; }",
        "solution": "Declare the variable in an enclosing scope before accessing it, and verify identifier spelling."
    },
    "E2003": {
        "title": "Function Argument Type Mismatch",
        "category": "Type Error",
        "description": "A function argument was passed with a type that differs from the parameter signature.",
        "bad_example": "fn square(x: int) -> int { return x * x; }\nsquare(\"invalid\");",
        "good_example": "square(5);",
        "solution": "Verify parameter types in the function signature and pass arguments of matching types."
    },
    "E2004": {
        "title": "Function Return Type Mismatch",
        "category": "Type Error",
        "description": "The type of the expression in a 'return' statement does not match the declared return type of the enclosing function.",
        "bad_example": "fn compute() -> int { return \"finished\"; }",
        "good_example": "fn compute() -> int { return 100; }",
        "solution": "Return a value matching the function's declared return type, or change the function signature."
    },
    "E2007": {
        "title": "Wrong Argument Count in Function Call",
        "category": "Semantic Error",
        "description": "A function was invoked with fewer or more arguments than required by its signature.",
        "bad_example": "fn multiply(a: int, b: int) -> int { return a * b; }\nmultiply(10);",
        "good_example": "multiply(10, 20);",
        "solution": "Supply the exact number of required arguments specified in the function signature."
    }
}

def get_error_info(code: str):
    return CATALOG.get(code.upper().strip())
