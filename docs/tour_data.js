window.ROVE_TOUR_DATA = [
  {
    "id": "intro01",
    "name": "intro01",
    "topic": "00_intro",
    "topicTitle": "00. Welcome & Intro",
    "title": "Welcome to Rove",
    "mode": "run",
    "description": "Run your very first Rove program to verify your environment.",
    "hints": [
      "This exercise is already solved! Just check that it compiles and runs.",
      "Press 'n' in the terminal to advance to the next exercise."
    ],
    "code": "// Welcome to Tour of Rove!\n// This exercise is already solved to get you started.\n// In future exercises, you will fix errors and write code.\n//\n// Press 'n' in the Tour terminal or modify this file to experiment!\n\nfn main() {\n    print(\"Hello, Rove Explorer! Welcome to the Tour of Rove.\")\n}\n\nmain()\n",
    "solution": "fn main() {\n    print(\"Hello, Rove Explorer! Welcome to the Tour of Rove.\")\n}\n\nmain()\n"
  },
  {
    "id": "intro02",
    "name": "intro02",
    "topic": "00_intro",
    "topicTitle": "00. Welcome & Intro",
    "title": "Fixing Syntax Errors",
    "mode": "run",
    "description": "Fix a missing closing quote in a print statement.",
    "hints": [
      "Look at line 6: the string is missing a closing quote character '\"'.",
      "Strings in Rove must start and end with matching quotation marks."
    ],
    "code": "// I AM NOT DONE\n// TODO: Fix the syntax error in the print statement below.\n// In Rove, strings must be closed with matching quotes.\n\nfn main() {\n    print(\"Welcome to modern systems programming with Rove!\n}\n\nmain()\n",
    "solution": "fn main() {\n    print(\"Welcome to modern systems programming with Rove!\")\n}\n\nmain()\n"
  },
  {
    "id": "intro03",
    "name": "intro03",
    "topic": "00_intro",
    "topicTitle": "00. Welcome & Intro",
    "title": "Comments in Rove",
    "mode": "run",
    "description": "Uncomment code using double slash // line comments.",
    "hints": [
      "Lines starting with '//' are ignored by the compiler.",
      "Remove '//' before `let message = \"Rove is fast!\"` and the print call."
    ],
    "code": "// I AM NOT DONE\n// In Rove, comments start with `//` and are ignored by the compiler.\n// TODO: Uncomment the declaration of `message` and the print call!\n\nfn main() {\n    // let message = \"Rove is fast!\"\n    let message = \"\"\n    assert(message == \"Rove is fast!\", \"message must equal 'Rove is fast!'\")\n    print(message)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let message = \"Rove is fast!\"\n    assert(message == \"Rove is fast!\", \"message must equal 'Rove is fast!'\")\n    print(message)\n}\n\nmain()\n"
  },
  {
    "id": "variables01",
    "name": "variables01",
    "topic": "01_variables",
    "topicTitle": "01. Variables & Mutability",
    "title": "Immutable Bindings with let",
    "mode": "run",
    "description": "Declare an immutable variable using the let keyword.",
    "hints": [
      "In Rove, variables cannot be introduced without a keyword.",
      "Use `let x = 42` to introduce an immutable binding."
    ],
    "code": "// I AM NOT DONE\n// In Rove, bindings are introduced with `let` (immutable) or `var` (mutable).\n// TODO: Declare `x` with value 42 using the `let` keyword.\n\nfn main() {\n    // Declare x here:\n\n    print(\"x is:\", x)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let x = 42\n    print(\"x is:\", x)\n}\n\nmain()\n"
  },
  {
    "id": "variables02",
    "name": "variables02",
    "topic": "01_variables",
    "topicTitle": "01. Variables & Mutability",
    "title": "Mutable Variables with var and set",
    "mode": "run",
    "description": "Allow variable mutation by changing let to var.",
    "hints": [
      "`let count = 10` creates an immutable binding.",
      "Change `let count = 10` to `var count = 10`."
    ],
    "code": "// I AM NOT DONE\n// In Rove, immutable bindings created with `let` cannot be modified.\n// To allow mutation, declare the variable with `var`, and update it with `set`.\n// TODO: Change `let` to `var` so that `count` can be incremented.\n\nfn main() {\n    let count = 10\n    set count = count + 5\n    print(\"Updated count:\", count)\n}\n\nmain()\n",
    "solution": "fn main() {\n    var count = 10\n    set count = count + 5\n    print(\"Updated count:\", count)\n}\n\nmain()\n"
  },
  {
    "id": "variables03",
    "name": "variables03",
    "topic": "01_variables",
    "topicTitle": "01. Variables & Mutability",
    "title": "Type Annotations",
    "mode": "check",
    "description": "Fix a type mismatch where a string was assigned to an int.",
    "hints": [
      "`let age: int` declares that `age` must be an integer.",
      "Change \"twenty\" to an integer literal like `20`."
    ],
    "code": "// I AM NOT DONE\n// Rove is statically typed. You can annotate variables with `: type`.\n// Types include `int`, `float`, `string`, `bool`.\n// TODO: Fix the type mismatch below so the compiler is satisfied.\n\nfn check_types() {\n    let age: int = \"twenty\"\n    let name: string = \"Rove\"\n    let active: bool = true\n}\n",
    "solution": "fn check_types() {\n    let age: int = 20\n    let name: string = \"Rove\"\n    let active: bool = true\n}\n"
  },
  {
    "id": "variables04",
    "name": "variables04",
    "topic": "01_variables",
    "topicTitle": "01. Variables & Mutability",
    "title": "Constants with const",
    "mode": "run",
    "description": "Understand that const values cannot be reassigned.",
    "hints": [
      "Constants declared with `const` cannot be updated.",
      "Read from `MAX_USERS` into a new local variable instead of reassigning it."
    ],
    "code": "// I AM NOT DONE\n// `const` declares compile-time immutable values.\n// Attempting to reassign a `const` is a compile-time error.\n// TODO: Fix the code so `MAX_USERS` is not illegally reassigned.\n\nconst MAX_USERS: int = 100\n\nfn main() {\n    set MAX_USERS = 200\n    print(\"Max users limit:\", MAX_USERS)\n}\n\nmain()\n",
    "solution": "const MAX_USERS: int = 100\n\nfn main() {\n    let current_limit = MAX_USERS\n    print(\"Max users limit:\", current_limit)\n}\n\nmain()\n"
  },
  {
    "id": "variables05",
    "name": "variables05",
    "topic": "01_variables",
    "topicTitle": "01. Variables & Mutability",
    "title": "Arithmetic & Scopes",
    "mode": "run",
    "description": "Compute and declare the area of a rectangle.",
    "hints": [
      "Declare `let area = width * height` before the print statement."
    ],
    "code": "// I AM NOT DONE\n// TODO: Calculate the area of a rectangle with width 7 and height 6.\n// Store the result in `area` and print it.\n\nfn main() {\n    let width = 7\n    let height = 6\n    // Declare `area` and compute width * height\n    print(\"Rectangle area:\", area)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let width = 7\n    let height = 6\n    let area = width * height\n    print(\"Rectangle area:\", area)\n}\n\nmain()\n"
  },
  {
    "id": "variables06",
    "name": "variables06",
    "topic": "01_variables",
    "topicTitle": "01. Variables & Mutability",
    "title": "Array Destructuring",
    "mode": "run",
    "description": "Unpack coordinates using array destructuring.",
    "hints": [
      "Use `let [x, y] = coords` to unpack the two values at once."
    ],
    "code": "// I AM NOT DONE\n// Rove supports array destructuring: `let [first, second] = [val1, val2]`\n// TODO: Destructure `coords` into `x` and `y`.\n\nfn main() {\n    let coords = [100, 250]\n    // Destructure here:\n    let x = 0\n    let y = 0\n    assert(x == 100 and y == 250, \"x and y must be destructured from coords!\")\n    print(\"X:\", x, \"Y:\", y)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let coords = [100, 250]\n    let [x, y] = coords\n    assert(x == 100 and y == 250, \"x and y must be destructured from coords!\")\n    print(\"X:\", x, \"Y:\", y)\n}\n\nmain()\n"
  },
  {
    "id": "variables07",
    "name": "variables07",
    "topic": "01_variables",
    "topicTitle": "01. Variables & Mutability",
    "title": "Struct Destructuring",
    "mode": "run",
    "description": "Unpack fields from a struct using positional destructuring.",
    "hints": [
      "Write `let Point(px, py) = p` to bind `px` and `py`."
    ],
    "code": "// I AM NOT DONE\n// Rove also supports positional struct destructuring:\n//   `let Point(x, y) = point_instance`\n// TODO: Destructure `p` into `px` and `py`.\n\nstruct Point {\n    x: int,\n    y: int\n}\n\nfn main() {\n    let p = Point(30, 70)\n    // Destructure Point(px, py) from p:\n    let px = 0\n    let py = 0\n\n    assert(px == 30 and py == 70, \"px and py must match p.x and p.y!\")\n    print(\"Destructured Point:\", px, py)\n}\n\nmain()\n",
    "solution": "struct Point {\n    x: int,\n    y: int\n}\n\nfn main() {\n    let p = Point(30, 70)\n    let Point(px, py) = p\n    assert(px == 30 and py == 70, \"px and py must match p.x and p.y!\")\n    print(\"Destructured Point:\", px, py)\n}\n\nmain()\n"
  },
  {
    "id": "variables08",
    "name": "variables08",
    "topic": "01_variables",
    "topicTitle": "01. Variables & Mutability",
    "title": "Discarding Values with Underscore",
    "mode": "run",
    "description": "Discard unused values during destructuring with _.",
    "hints": [
      "Use `_` to ignore unwanted items: `let [first, _] = pair`."
    ],
    "code": "// I AM NOT DONE\n// When destructuring, you can discard unwanted values using `_`:\n//   `let [first, _] = values`\n// TODO: Extract only `first_val` and ignore the second value with `_`.\n\nfn main() {\n    let pair = [42, 999]\n    // Destructure first_val and discard the second with _:\n    let first_val = 0\n\n    assert(first_val == 42, \"first_val must be 42!\")\n    print(\"Extracted first value:\", first_val)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let pair = [42, 999]\n    let [first_val, _] = pair\n    assert(first_val == 42, \"first_val must be 42!\")\n    print(\"Extracted first value:\", first_val)\n}\n\nmain()\n"
  },
  {
    "id": "types01",
    "name": "types01",
    "topic": "02_types",
    "topicTitle": "02. Primitive & System Types",
    "title": "Integers and Floats",
    "mode": "check",
    "description": "Specify the correct float type for decimal values.",
    "hints": [
      "0.75 has a decimal point, making it a `float`, not an `int`.",
      "Change `let ratio: int` to `let ratio: float`."
    ],
    "code": "// I AM NOT DONE\n// Rove integers do not automatically narrow from float without explicit conversion.\n// Float literals have a decimal point (e.g. 3.14).\n// TODO: Fix the type declaration so `ratio` has the correct type `float`.\n\nfn demo_numerics() {\n    let count: int = 50\n    let ratio: int = 0.75\n}\n",
    "solution": "fn demo_numerics() {\n    let count: int = 50\n    let ratio: float = 0.75\n}\n"
  },
  {
    "id": "types02",
    "name": "types02",
    "topic": "02_types",
    "topicTitle": "02. Primitive & System Types",
    "title": "Booleans and Logic",
    "mode": "run",
    "description": "Combine boolean flags using the `or` keyword.",
    "hints": [
      "In Rove, boolean OR is expressed with `or` (or `||`).",
      "Write `let is_allowed: bool = is_admin or has_token`."
    ],
    "code": "// I AM NOT DONE\n// Rove uses words `and`, `or`, and `not` for boolean logic.\n// TODO: Set `is_allowed` to true when `is_admin` is true OR `has_token` is true.\n\nfn main() {\n    let is_admin: bool = false\n    let has_token: bool = true\n    let is_allowed: bool = false // Fix this condition!\n    assert(is_allowed == true, \"Access should be allowed when token is present!\")\n    print(\"Access allowed:\", is_allowed)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let is_admin: bool = false\n    let has_token: bool = true\n    let is_allowed: bool = is_admin or has_token\n    assert(is_allowed == true, \"Access should be allowed when token is present!\")\n    print(\"Access allowed:\", is_allowed)\n}\n\nmain()\n"
  },
  {
    "id": "types03",
    "name": "types03",
    "topic": "02_types",
    "topicTitle": "02. Primitive & System Types",
    "title": "Strings and Concatenation",
    "mode": "run",
    "description": "Concatenate string variables using the + operator.",
    "hints": [
      "Use `first + \" \" + last` to concatenate with a space."
    ],
    "code": "// I AM NOT DONE\n// Strings in Rove can be concatenated using the `+` operator.\n// TODO: Combine `first` and `last` with a space to form \"Rove Language\".\n\nfn main() {\n    let first = \"Rove\"\n    let last = \"Language\"\n    let full_name = first // Fix concatenation here\n    assert(full_name == \"Rove Language\", \"full_name must be 'Rove Language'!\")\n    print(\"Full name:\", full_name)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let first = \"Rove\"\n    let last = \"Language\"\n    let full_name = first + \" \" + last\n    assert(full_name == \"Rove Language\", \"full_name must be 'Rove Language'!\")\n    print(\"Full name:\", full_name)\n}\n\nmain()\n"
  },
  {
    "id": "types04",
    "name": "types04",
    "topic": "02_types",
    "topicTitle": "02. Primitive & System Types",
    "title": "String Length",
    "mode": "run",
    "description": "Determine the length of a string using len().",
    "hints": [
      "`len(s)` returns the character length of string `s`.",
      "Write `let length = len(title)`."
    ],
    "code": "// I AM NOT DONE\n// The built-in function `len(string)` returns the length of a string.\n// TODO: Calculate the length of `title` using `len(...)`.\n\nfn main() {\n    let title = \"Antigravity\"\n    let length = 0 // Compute len(title)\n\n    assert(length == 11, \"Length of 'Antigravity' must be 11!\")\n    print(\"Title length is:\", length)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let title = \"Antigravity\"\n    let length = len(title)\n    assert(length == 11, \"Length of 'Antigravity' must be 11!\")\n    print(\"Title length is:\", length)\n}\n\nmain()\n"
  },
  {
    "id": "types05",
    "name": "types05",
    "topic": "02_types",
    "topicTitle": "02. Primitive & System Types",
    "title": "Escape Sequences",
    "mode": "run",
    "description": "Use newline \\n and tab \\t escapes in string literals.",
    "hints": [
      "Use `\"Line 1\\nLine 2\"` to insert a newline."
    ],
    "code": "// I AM NOT DONE\n// Rove string literals support standard escape sequences like `\\n` (newline) and `\\t` (tab).\n// TODO: Create a two-line string with \"Hello\" on line 1 and \"World\" on line 2.\n\nfn main() {\n    let text = \"Hello World\" // Use \\n between Hello and World\n    assert(text == \"Hello\\nWorld\", \"text must contain a newline escape \\n\")\n    print(text)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let text = \"Hello\\nWorld\"\n    assert(text == \"Hello\\nWorld\", \"text must contain a newline escape \\n\")\n    print(text)\n}\n\nmain()\n"
  },
  {
    "id": "types06",
    "name": "types06",
    "topic": "02_types",
    "topicTitle": "02. Primitive & System Types",
    "title": "Integer Widening",
    "mode": "run",
    "description": "Observe automatic int widening to float in mixed expressions.",
    "hints": [
      "In Rove, adding an int to a float widens the int to float automatically.",
      "Write `let result: float = base + fraction`."
    ],
    "code": "// I AM NOT DONE\n// An `int` automatically widens to `float` when combined with a float operator.\n// TODO: Add `base` (int) and `fraction` (float) together and store in `result: float`.\n\nfn main() {\n    let base: int = 10\n    let fraction: float = 0.5\n    let result: float = 0.0 // Add base + fraction\n\n    assert(result == 10.5, \"result must be 10.5\")\n    print(\"Widened calculation:\", result)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let base: int = 10\n    let fraction: float = 0.5\n    let result: float = base + fraction\n\n    assert(result == 10.5, \"result must be 10.5\")\n    print(\"Widened calculation:\", result)\n}\n\nmain()\n"
  },
  {
    "id": "functions01",
    "name": "functions01",
    "topic": "03_functions",
    "topicTitle": "03. Functions & Expressions",
    "title": "Function Declaration",
    "mode": "run",
    "description": "Define a void function using the fn keyword.",
    "hints": [
      "Define `fn call_me() { print(\"Called successfully!\") }`."
    ],
    "code": "// I AM NOT DONE\n// In Rove, functions are declared with the `fn` keyword.\n// TODO: Define a function named `call_me` that prints \"Called successfully!\".\n\nfn main() {\n    call_me()\n}\n\nmain()\n",
    "solution": "fn call_me() {\n    print(\"Called successfully!\")\n}\n\nfn main() {\n    call_me()\n}\n\nmain()\n"
  },
  {
    "id": "functions02",
    "name": "functions02",
    "topic": "03_functions",
    "topicTitle": "03. Functions & Expressions",
    "title": "Parameters and Return Types",
    "mode": "run",
    "description": "Write a function returning the product of two integers.",
    "hints": [
      "Inside `multiply`, write `return a * b`."
    ],
    "code": "// I AM NOT DONE\n// Functions specify parameter types and return types: `fn name(a: int) -> int`\n// TODO: Complete the `multiply` function so it returns `a * b`.\n\nfn multiply(a: int, b: int) -> int {\n    // Add return statement\n}\n\nfn main() {\n    let result = multiply(6, 7)\n    assert(result == 42, \"6 * 7 must be 42\")\n    print(\"6 * 7 =\", result)\n}\n\nmain()\n",
    "solution": "fn multiply(a: int, b: int) -> int {\n    return a * b\n}\n\nfn main() {\n    let result = multiply(6, 7)\n    assert(result == 42, \"6 * 7 must be 42\")\n    print(\"6 * 7 =\", result)\n}\n\nmain()\n"
  },
  {
    "id": "functions03",
    "name": "functions03",
    "topic": "03_functions",
    "topicTitle": "03. Functions & Expressions",
    "title": "Expression-Bodied Functions",
    "mode": "run",
    "description": "Define a concise expression-bodied function using =.",
    "hints": [
      "Write `fn cube(x: int) -> int = x * x * x`."
    ],
    "code": "// I AM NOT DONE\n// In Rove, concise functions can use expression bodies:\n//   fn square(x: int) -> int = x * x\n// TODO: Define an expression-bodied function `cube` that computes `x * x * x`.\n\n// Define `cube` here:\n\nfn main() {\n    let res = cube(3)\n    assert(res == 27, \"Cube of 3 must be 27\")\n    print(\"Cube of 3 is:\", res)\n}\n\nmain()\n",
    "solution": "fn cube(x: int) -> int = x * x * x\n\nfn main() {\n    let res = cube(3)\n    assert(res == 27, \"Cube of 3 must be 27\")\n    print(\"Cube of 3 is:\", res)\n}\n\nmain()\n"
  },
  {
    "id": "functions04",
    "name": "functions04",
    "topic": "03_functions",
    "topicTitle": "03. Functions & Expressions",
    "title": "Default Parameter Values",
    "mode": "run",
    "description": "Supply a default parameter value for omitted arguments.",
    "hints": [
      "Change `title: string` to `title: string = \"Adventurer\"` in the parameter list."
    ],
    "code": "// I AM NOT DONE\n// Parameters can declare default values: `fn greet(name: string, title: string = \"Explorer\")`\n// Trailing parameters with defaults can be omitted by the caller.\n// TODO: Add a default value \"Adventurer\" to `title`.\n\nfn greet(name: string, title: string) {\n    print(\"Greetings, \" + title + \" \" + name + \"!\")\n}\n\nfn main() {\n    greet(\"Kurt\", \"Captain\")\n    greet(\"Rove\") // Should use default title!\n}\n\nmain()\n",
    "solution": "fn greet(name: string, title: string = \"Adventurer\") {\n    print(\"Greetings, \" + title + \" \" + name + \"!\")\n}\n\nfn main() {\n    greet(\"Kurt\", \"Captain\")\n    greet(\"Rove\")\n}\n\nmain()\n"
  },
  {
    "id": "functions05",
    "name": "functions05",
    "topic": "03_functions",
    "topicTitle": "03. Functions & Expressions",
    "title": "Multiple Default Parameters",
    "mode": "run",
    "description": "Provide multiple trailing parameters with default values.",
    "hints": [
      "Declare `fn make_sandwich(bread: string, filling: string = \"Cheese\", toasted: bool = true)`."
    ],
    "code": "// I AM NOT DONE\n// Multiple trailing parameters can declare defaults in Rove.\n// TODO: Give `filling` the default \"Cheese\" and `toasted` the default `true`.\n\nfn make_sandwich(bread: string, filling: string, toasted: bool) -> string {\n    let toast_str = if toasted { \"Toasted\" } else { \"Fresh\" }\n    return toast_str + \" \" + filling + \" on \" + bread\n}\n\nfn main() {\n    let s1 = make_sandwich(\"Rye\", \"Turkey\", false)\n    let s2 = make_sandwich(\"Sourdough\") // Should use defaults: Cheese and true!\n\n    assert(s1 == \"Fresh Turkey on Rye\", \"s1 must match custom arguments\")\n    assert(s2 == \"Toasted Cheese on Sourdough\", \"s2 must use default values\")\n    print(s1)\n    print(s2)\n}\n\nmain()\n",
    "solution": "fn make_sandwich(bread: string, filling: string = \"Cheese\", toasted: bool = true) -> string {\n    let toast_str = if toasted { \"Toasted\" } else { \"Fresh\" }\n    return toast_str + \" \" + filling + \" on \" + bread\n}\n\nfn main() {\n    let s1 = make_sandwich(\"Rye\", \"Turkey\", false)\n    let s2 = make_sandwich(\"Sourdough\")\n\n    assert(s1 == \"Fresh Turkey on Rye\", \"s1 must match custom arguments\")\n    assert(s2 == \"Toasted Cheese on Sourdough\", \"s2 must use default values\")\n    print(s1)\n    print(s2)\n}\n\nmain()\n"
  },
  {
    "id": "functions06",
    "name": "functions06",
    "topic": "03_functions",
    "topicTitle": "03. Functions & Expressions",
    "title": "Recursive Functions",
    "mode": "run",
    "description": "Implement the factorial function recursively in Rove.",
    "hints": [
      "Base case: `if n <= 1 { return 1 }`.",
      "Recursive step: `return n * factorial(n - 1)`."
    ],
    "code": "// I AM NOT DONE\n// Functions can call themselves recursively with a base case.\n// TODO: Implement the recursive `factorial(n: int) -> int` function!\n\nfn factorial(n: int) -> int {\n    // Add base case and recursive call!\n    return 0\n}\n\nfn main() {\n    let res = factorial(5)\n    assert(res == 120, \"factorial(5) must be 120 (5 * 4 * 3 * 2 * 1)!\")\n    print(\"5! =\", res)\n}\n\nmain()\n",
    "solution": "fn factorial(n: int) -> int {\n    if n <= 1 {\n        return 1\n    }\n    return n * factorial(n - 1)\n}\n\nfn main() {\n    let res = factorial(5)\n    assert(res == 120, \"factorial(5) must be 120 (5 * 4 * 3 * 2 * 1)!\")\n    print(\"5! =\", res)\n}\n\nmain()\n"
  },
  {
    "id": "if01",
    "name": "if01",
    "topic": "04_control_flow",
    "topicTitle": "04. Control Flow & Loops",
    "title": "Conditional Branching",
    "mode": "run",
    "description": "Structure multi-way branching using elif and else.",
    "hints": [
      "Add `elif temp > 15 { return \"Warm\" } else { return \"Cold\" }`."
    ],
    "code": "// I AM NOT DONE\n// In Rove, `if`, `elif` (or `else if`), and `else` control branch execution.\n// TODO: Complete the temperature check:\n// If temp > 30 return \"Hot\", elif temp > 15 return \"Warm\", else return \"Cold\".\n\nfn check_temp(temp: int) -> string {\n    if temp > 30 {\n        return \"Hot\"\n    }\n    // Add elif and else arms here!\n    return \"Unknown\"\n}\n\nfn main() {\n    assert(check_temp(35) == \"Hot\", \"35 must be Hot\")\n    assert(check_temp(20) == \"Warm\", \"20 must be Warm\")\n    assert(check_temp(5) == \"Cold\", \"5 must be Cold\")\n    print(\"All temperature checks passed!\")\n}\n\nmain()\n",
    "solution": "fn check_temp(temp: int) -> string {\n    if temp > 30 {\n        return \"Hot\"\n    } elif temp > 15 {\n        return \"Warm\"\n    } else {\n        return \"Cold\"\n    }\n}\n\nfn main() {\n    assert(check_temp(35) == \"Hot\", \"35 must be Hot\")\n    assert(check_temp(20) == \"Warm\", \"20 must be Warm\")\n    assert(check_temp(5) == \"Cold\", \"5 must be Cold\")\n    print(\"All temperature checks passed!\")\n}\n\nmain()\n"
  },
  {
    "id": "if02",
    "name": "if02",
    "topic": "04_control_flow",
    "topicTitle": "04. Control Flow & Loops",
    "title": "If as an Expression",
    "mode": "check",
    "description": "Ensure all branches of an if expression return the same type.",
    "hints": [
      "The `else` arm returns integer `0`, but `status` expects a `string`.",
      "Change `0` to a string like `\"disconnected\"`."
    ],
    "code": "// I AM NOT DONE\n// In Rove, `if` can be an expression returning a value!\n// All branches must return the same type.\n// TODO: Fix the branch return types so `status` is consistently a `string`.\n\nfn get_status(is_online: bool) -> string {\n    let status: string = if is_online {\n        \"connected\"\n    } else {\n        0 // Error: 0 is an int, but string was expected!\n    }\n    return status\n}\n",
    "solution": "fn get_status(is_online: bool) -> string {\n    let status: string = if is_online {\n        \"connected\"\n    } else {\n        \"disconnected\"\n    }\n    return status\n}\n"
  },
  {
    "id": "loops01",
    "name": "loops01",
    "topic": "04_control_flow",
    "topicTitle": "04. Control Flow & Loops",
    "title": "Range For Loops",
    "mode": "run",
    "description": "Sum numbers from 1 to 5 using an inclusive range loop.",
    "hints": [
      "`1..4` only goes up to 4.",
      "Change the range to `1..5`."
    ],
    "code": "// I AM NOT DONE\n// Rove provides inclusive range loops: `for i in start..end`\n// For example, `1..5` iterates through 1, 2, 3, 4, 5.\n// TODO: Sum all numbers from 1 to 5 inclusive and verify the total is 15.\n\nfn main() {\n    var total: int = 0\n    for i in 1..4 { // Fix the range!\n        set total = total + i\n    }\n    assert(total == 15, \"Sum from 1 to 5 must equal 15!\")\n    print(\"Sum 1..5 is:\", total)\n}\n\nmain()\n",
    "solution": "fn main() {\n    var total: int = 0\n    for i in 1..5 {\n        set total = total + i\n    }\n    assert(total == 15, \"Sum from 1 to 5 must equal 15!\")\n    print(\"Sum 1..5 is:\", total)\n}\n\nmain()\n"
  },
  {
    "id": "loops02",
    "name": "loops02",
    "topic": "04_control_flow",
    "topicTitle": "04. Control Flow & Loops",
    "title": "While Loops",
    "mode": "run",
    "description": "Count down to 0 in a while loop.",
    "hints": [
      "Change `while countdown > 1` to `while countdown > 0`."
    ],
    "code": "// I AM NOT DONE\n// A `while` loop runs while its boolean condition is true.\n// Remember to update mutable variables with `set`.\n// TODO: Make the loop count all the way down to 0!\n\nfn main() {\n    var countdown = 3\n    while countdown > 1 { // Should count down until 0!\n        print(\"T-minus\", countdown)\n        set countdown = countdown - 1\n    }\n    assert(countdown == 0, \"Countdown must reach 0!\")\n    print(\"Liftoff!\")\n}\n\nmain()\n",
    "solution": "fn main() {\n    var countdown = 3\n    while countdown > 0 {\n        print(\"T-minus\", countdown)\n        set countdown = countdown - 1\n    }\n    assert(countdown == 0, \"Countdown must reach 0!\")\n    print(\"Liftoff!\")\n}\n\nmain()\n"
  },
  {
    "id": "loops03",
    "name": "loops03",
    "topic": "04_control_flow",
    "topicTitle": "04. Control Flow & Loops",
    "title": "Loop, Break, and Continue",
    "mode": "run",
    "description": "Break out of an unconditional loop after 4 steps.",
    "hints": [
      "Inside the loop, add `if step == 4 { break }`."
    ],
    "code": "// I AM NOT DONE\n// `loop` creates an unconditional loop.\n// Use `break` to exit and `continue` to skip to the next iteration.\n// TODO: Stop the loop when `step` reaches 4 using `break`.\n\nfn main() {\n    var step = 0\n    loop {\n        set step = step + 1\n        print(\"Step:\", step)\n        // Add break condition here when step == 4!\n\n        if step > 10 {\n            throw \"Loop runaway: failed to break at step 4!\"\n        }\n    }\n    assert(step == 4, \"Loop must stop exactly at step 4!\")\n    print(\"Done after 4 steps!\")\n}\n\nmain()\n",
    "solution": "fn main() {\n    var step = 0\n    loop {\n        set step = step + 1\n        print(\"Step:\", step)\n        if step == 4 {\n            break\n        }\n        if step > 10 {\n            throw \"Loop runaway: failed to break at step 4!\"\n        }\n    }\n    assert(step == 4, \"Loop must stop exactly at step 4!\")\n    print(\"Done after 4 steps!\")\n}\n\nmain()\n"
  },
  {
    "id": "loops04",
    "name": "loops04",
    "topic": "04_control_flow",
    "topicTitle": "04. Control Flow & Loops",
    "title": "Nested Loops",
    "mode": "run",
    "description": "Traverse a 2D coordinate space using nested for loops.",
    "hints": [
      "In the inner loop, accumulate: `set total = total + (r * 10 + c)`."
    ],
    "code": "// I AM NOT DONE\n// Nested loops allow traversing 2D grids and matrices.\n// TODO: Iterate row `r` from 1..2, and col `c` from 1..2.\n// Multiply r by 10 and add c, accumulating into `total`.\n// Expected: (11) + (12) + (21) + (22) = 66!\n\nfn main() {\n    var total = 0\n    for r in 1..2 {\n        for c in 1..2 {\n            // Add (r * 10 + c) to total\n        }\n    }\n    assert(total == 66, \"Nested loop total must be 66!\")\n    print(\"Grid traversal sum:\", total)\n}\n\nmain()\n",
    "solution": "fn main() {\n    var total = 0\n    for r in 1..2 {\n        for c in 1..2 {\n            set total = total + (r * 10 + c)\n        }\n    }\n    assert(total == 66, \"Nested loop total must be 66!\")\n    print(\"Grid traversal sum:\", total)\n}\n\nmain()\n"
  },
  {
    "id": "match01",
    "name": "match01",
    "topic": "04_control_flow",
    "topicTitle": "04. Control Flow & Loops",
    "title": "Pattern Matching",
    "mode": "check",
    "description": "Supply the mandatory wildcard _ fallback in a match expression.",
    "hints": [
      "In Rove, pattern matching must be exhaustive.",
      "Add `_ => \"Unknown\"` as the final match arm."
    ],
    "code": "// I AM NOT DONE\n// Rove `match` requires an exhaustive pattern match, so the fallback `_` is mandatory.\n// TODO: Add the mandatory `_ => ...` wildcard fallback arm to satisfy the compiler.\n\nfn describe_status(code: int) -> string {\n    let label = match code {\n        200 => \"OK\",\n        404 => \"Not Found\",\n        500 => \"Server Error\"\n    }\n    return label\n}\n",
    "solution": "fn describe_status(code: int) -> string {\n    let label = match code {\n        200 => \"OK\",\n        404 => \"Not Found\",\n        500 => \"Server Error\",\n        _ => \"Unknown\"\n    }\n    return label\n}\n"
  },
  {
    "id": "match02",
    "name": "match02",
    "topic": "04_control_flow",
    "topicTitle": "04. Control Flow & Loops",
    "title": "Match Value Expressions",
    "mode": "run",
    "description": "Convert numerical grades to letter ratings using match.",
    "hints": [
      "Map 1 => \"Bronze\", 2 => \"Silver\", 3 => \"Gold\", _ => \"Unranked\"."
    ],
    "code": "// I AM NOT DONE\n// `match` evaluates to a value directly.\n// TODO: Complete the `get_tier` function using `match tier`:\n//   1 => \"Bronze\"\n//   2 => \"Silver\"\n//   3 => \"Gold\"\n//   _ => \"Unranked\"\n\nfn get_tier(tier: int) -> string {\n    return match tier {\n        1 => \"Bronze\",\n        _ => \"Unranked\"\n    }\n}\n\nfn main() {\n    assert(get_tier(3) == \"Gold\", \"Tier 3 must be Gold\")\n    assert(get_tier(2) == \"Silver\", \"Tier 2 must be Silver\")\n    print(\"Tier 3 is:\", get_tier(3))\n}\n\nmain()\n",
    "solution": "fn get_tier(tier: int) -> string {\n    return match tier {\n        1 => \"Bronze\",\n        2 => \"Silver\",\n        3 => \"Gold\",\n        _ => \"Unranked\"\n    }\n}\n\nfn main() {\n    assert(get_tier(3) == \"Gold\", \"Tier 3 must be Gold\")\n    assert(get_tier(2) == \"Silver\", \"Tier 2 must be Silver\")\n    print(\"Tier 3 is:\", get_tier(3))\n}\n\nmain()\n"
  },
  {
    "id": "match03",
    "name": "match03",
    "topic": "04_control_flow",
    "topicTitle": "04. Control Flow & Loops",
    "title": "Matching Booleans",
    "mode": "run",
    "description": "Match on boolean states to produce human-readable labels.",
    "hints": [
      "Match true => \"Enabled\", false => \"Disabled\", _ => \"Unknown\"."
    ],
    "code": "// I AM NOT DONE\n// `match` works seamlessly on booleans and strings too.\n// TODO: Match `flag`: `true => \"Enabled\"`, `false => \"Disabled\"`, `_ => \"Unknown\"`.\n\nfn describe_flag(flag: bool) -> string {\n    return match flag {\n        true => \"Enabled\",\n        _ => \"Unknown\"\n    }\n}\n\nfn main() {\n    assert(describe_flag(true) == \"Enabled\", \"true should be Enabled\")\n    assert(describe_flag(false) == \"Disabled\", \"false should be Disabled\")\n    print(\"Flag states verified!\")\n}\n\nmain()\n",
    "solution": "fn describe_flag(flag: bool) -> string {\n    return match flag {\n        true => \"Enabled\",\n        false => \"Disabled\",\n        _ => \"Unknown\"\n    }\n}\n\nfn main() {\n    assert(describe_flag(true) == \"Enabled\", \"true should be Enabled\")\n    assert(describe_flag(false) == \"Disabled\", \"false should be Disabled\")\n    print(\"Flag states verified!\")\n}\n\nmain()\n"
  },
  {
    "id": "arrays01",
    "name": "arrays01",
    "topic": "05_arrays",
    "topicTitle": "05_arrays",
    "title": "Arrays and Indexing",
    "mode": "run",
    "description": "Access array elements using 0-based indexing.",
    "hints": [
      "In a 0-indexed array, the second item is at index 1.",
      "Write `let item = inventory[1]`."
    ],
    "code": "// I AM NOT DONE\n// Arrays are written `[elem1, elem2, ...]` with 0-based indexing `arr[0]`.\n// TODO: Print the second item (\"Sapphire\") from the inventory array.\n\nfn main() {\n    let inventory = [\"Ruby\", \"Sapphire\", \"Emerald\"]\n    let item = inventory[0] // Change index to 1!\n    assert(item == \"Sapphire\", \"Selected item must be Sapphire!\")\n    print(\"Selected item:\", item)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let inventory = [\"Ruby\", \"Sapphire\", \"Emerald\"]\n    let item = inventory[1]\n    assert(item == \"Sapphire\", \"Selected item must be Sapphire!\")\n    print(\"Selected item:\", item)\n}\n\nmain()\n"
  },
  {
    "id": "arrays02",
    "name": "arrays02",
    "topic": "05_arrays",
    "topicTitle": "05_arrays",
    "title": "Modifying Array Elements",
    "mode": "run",
    "description": "Update an array element using set array[index] = value.",
    "hints": [
      "Use `set scores[1] = 999` to update the middle element."
    ],
    "code": "// I AM NOT DONE\n// Array elements can be updated using `set array[index] = new_value`.\n// TODO: Update the middle element (index 1) to 999.\n\nfn main() {\n    var scores = [10, 20, 30]\n    // Set index 1 to 999\n    assert(scores[1] == 999, \"Middle score must be updated to 999!\")\n    print(\"Modified scores:\", scores[0], scores[1], scores[2])\n}\n\nmain()\n",
    "solution": "fn main() {\n    var scores = [10, 20, 30]\n    set scores[1] = 999\n    assert(scores[1] == 999, \"Middle score must be updated to 999!\")\n    print(\"Modified scores:\", scores[0], scores[1], scores[2])\n}\n\nmain()\n"
  },
  {
    "id": "arrays03",
    "name": "arrays03",
    "topic": "05_arrays",
    "topicTitle": "05_arrays",
    "title": "Array Aggregation",
    "mode": "run",
    "description": "Sum the elements of an array with a loop.",
    "hints": [
      "Inside the loop, update `sum` with `set sum = sum + values[i]`."
    ],
    "code": "// I AM NOT DONE\n// TODO: Loop through the array and compute the sum of all elements.\n// Expected output: \"Total sum: 150\"\n\nfn main() {\n    let values = [10, 20, 30, 40, 50]\n    var sum: int = 0\n    for i in 0..4 {\n        // Add values[i] to sum\n    }\n    assert(sum == 150, \"Sum of all 5 items must be 150!\")\n    print(\"Total sum:\", sum)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let values = [10, 20, 30, 40, 50]\n    var sum: int = 0\n    for i in 0..4 {\n        set sum = sum + values[i]\n    }\n    assert(sum == 150, \"Sum of all 5 items must be 150!\")\n    print(\"Total sum:\", sum)\n}\n\nmain()\n"
  },
  {
    "id": "arrays04",
    "name": "arrays04",
    "topic": "05_arrays",
    "topicTitle": "05_arrays",
    "title": "Array Length",
    "mode": "run",
    "description": "Inspect dynamic array capacity and item counts with len().",
    "hints": [
      "Use `len(languages)` to get the item count."
    ],
    "code": "// I AM NOT DONE\n// The built-in `len(array)` function returns the count of items in an array.\n// TODO: Measure the number of elements in `languages`.\n\nfn main() {\n    let languages = [\"Rove\", \"C++\", \"Rust\", \"Python\"]\n    let count = 0 // Compute len(languages)\n\n    assert(count == 4, \"languages array must have 4 items!\")\n    print(\"Tracked languages count:\", count)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let languages = [\"Rove\", \"C++\", \"Rust\", \"Python\"]\n    let count = len(languages)\n    assert(count == 4, \"languages array must have 4 items!\")\n    print(\"Tracked languages count:\", count)\n}\n\nmain()\n"
  },
  {
    "id": "arrays05",
    "name": "arrays05",
    "topic": "05_arrays",
    "topicTitle": "05_arrays",
    "title": "Pushing Array Elements",
    "mode": "run",
    "description": "Append elements dynamically to a mutable array using push().",
    "hints": [
      "Call `arr.push(30)` to append 30."
    ],
    "code": "// I AM NOT DONE\n// Arrays support dynamic appending via the `.push(value)` method.\n// TODO: Append `30` to `numbers` so that its length becomes 3.\n\nfn main() {\n    var numbers = [10, 20]\n    // Append 30 here:\n\n    assert(len(numbers) == 3, \"numbers array should contain 3 elements\")\n    assert(numbers[2] == 30, \"last element should be 30\")\n    print(\"Updated array length:\", len(numbers))\n}\n\nmain()\n",
    "solution": "fn main() {\n    var numbers = [10, 20]\n    numbers.push(30)\n    assert(len(numbers) == 3, \"numbers array should contain 3 elements\")\n    assert(numbers[2] == 30, \"last element should be 30\")\n    print(\"Updated array length:\", len(numbers))\n}\n\nmain()\n"
  },
  {
    "id": "arrays06",
    "name": "arrays06",
    "topic": "05_arrays",
    "topicTitle": "05_arrays",
    "title": "Finding Max Element",
    "mode": "run",
    "description": "Find the highest value in an integer array using a loop.",
    "hints": [
      "Inside the loop: `if nums[i] > max_val { set max_val = nums[i] }`."
    ],
    "code": "// I AM NOT DONE\n// TODO: Find the maximum number in `nums` and store it in `max_val`.\n\nfn main() {\n    let nums = [14, 88, 42, 95, 33]\n    var max_val = nums[0]\n\n    for i in 1..4 {\n        // Update max_val if nums[i] is greater!\n    }\n\n    assert(max_val == 95, \"Maximum value must be 95!\")\n    print(\"Highest score found:\", max_val)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let nums = [14, 88, 42, 95, 33]\n    var max_val = nums[0]\n\n    for i in 1..4 {\n        if nums[i] > max_val {\n            set max_val = nums[i]\n        }\n    }\n\n    assert(max_val == 95, \"Maximum value must be 95!\")\n    print(\"Highest score found:\", max_val)\n}\n\nmain()\n"
  },
  {
    "id": "structs01",
    "name": "structs01",
    "topic": "06_structs",
    "topicTitle": "06. Structs & Implementations",
    "title": "Defining and Instantiating Structs",
    "mode": "run",
    "description": "Define a struct Point with x and y fields.",
    "hints": [
      "Declare: `struct Point { x: int, y: int }` before `main`."
    ],
    "code": "// I AM NOT DONE\n// Structs group related fields: `struct Name { field1: type, ... }`\n// Instantiate with `Name(val1, val2)`.\n// TODO: Define a struct `Point` with fields `x: int` and `y: int`.\n\n// Define struct Point here:\n\nfn main() {\n    let p = Point(15, 25)\n    print(\"Point coordinates:\", p.x, p.y)\n}\n\nmain()\n",
    "solution": "struct Point {\n    x: int,\n    y: int\n}\n\nfn main() {\n    let p = Point(15, 25)\n    print(\"Point coordinates:\", p.x, p.y)\n}\n\nmain()\n"
  },
  {
    "id": "structs02",
    "name": "structs02",
    "topic": "06_structs",
    "topicTitle": "06. Structs & Implementations",
    "title": "Methods with Inherent impl",
    "mode": "run",
    "description": "Add the self parameter to a struct method.",
    "hints": [
      "In Rove, methods take `self` as their first parameter.",
      "Change `fn area() -> int` to `fn area(self) -> int`."
    ],
    "code": "// I AM NOT DONE\n// Methods are implemented in an `impl StructName` block.\n// The first parameter must be `self`.\n// TODO: Add `self` to the `area` method signature.\n\nstruct Rectangle {\n    width: int,\n    height: int\n}\n\nimpl Rectangle {\n    fn area() -> int { // Fix signature to take self!\n        return self.width * self.height\n    }\n}\n\nfn main() {\n    let rect = Rectangle(8, 5)\n    print(\"Rectangle area:\", rect.area())\n}\n\nmain()\n",
    "solution": "struct Rectangle {\n    width: int,\n    height: int\n}\n\nimpl Rectangle {\n    fn area(self) -> int {\n        return self.width * self.height\n    }\n}\n\nfn main() {\n    let rect = Rectangle(8, 5)\n    print(\"Rectangle area:\", rect.area())\n}\n\nmain()\n"
  },
  {
    "id": "structs03",
    "name": "structs03",
    "topic": "06_structs",
    "topicTitle": "06. Structs & Implementations",
    "title": "Nested Structs",
    "mode": "run",
    "description": "Compose structs containing other structs as fields.",
    "hints": [
      "Access nested field with `player.position.x`."
    ],
    "code": "// I AM NOT DONE\n// Structs can contain instances of other structs as fields.\n// TODO: Access the player's nested X position through `player.position.x`.\n\nstruct Position {\n    x: int,\n    y: int\n}\n\nstruct Player {\n    name: string,\n    position: Position\n}\n\nfn main() {\n    let pos = Position(120, 80)\n    let player = Player(\"Aria\", pos)\n\n    let player_x = 0 // Read player.position.x\n\n    assert(player_x == 120, \"player_x must equal 120!\")\n    print(\"Player position on X:\", player_x)\n}\n\nmain()\n",
    "solution": "struct Position {\n    x: int,\n    y: int\n}\n\nstruct Player {\n    name: string,\n    position: Position\n}\n\nfn main() {\n    let pos = Position(120, 80)\n    let player = Player(\"Aria\", pos)\n    let player_x = player.position.x\n\n    assert(player_x == 120, \"player_x must equal 120!\")\n    print(\"Player position on X:\", player_x)\n}\n\nmain()\n"
  },
  {
    "id": "structs04",
    "name": "structs04",
    "topic": "06_structs",
    "topicTitle": "06. Structs & Implementations",
    "title": "Mutating Struct Fields",
    "mode": "run",
    "description": "Mutate internal struct fields using set instance.field = value.",
    "hints": [
      "Use `set hero.health = hero.health - 25` to apply damage."
    ],
    "code": "// I AM NOT DONE\n// Mutable struct bindings allow field reassignment via `set target.field = val`.\n// TODO: Damage `hero` by subtracting 25 from `hero.health`.\n\nstruct Hero {\n    name: string,\n    health: int\n}\n\nfn main() {\n    var hero = Hero(\"Kurt\", 100)\n    // Subtract 25 damage:\n\n    assert(hero.health == 75, \"Hero health must be 75 after 25 damage!\")\n    print(\"Hero remaining health:\", hero.health)\n}\n\nmain()\n",
    "solution": "struct Hero {\n    name: string,\n    health: int\n}\n\nfn main() {\n    var hero = Hero(\"Kurt\", 100)\n    set hero.health = hero.health - 25\n    assert(hero.health == 75, \"Hero health must be 75 after 25 damage!\")\n    print(\"Hero remaining health:\", hero.health)\n}\n\nmain()\n"
  },
  {
    "id": "structs05",
    "name": "structs05",
    "topic": "06_structs",
    "topicTitle": "06. Structs & Implementations",
    "title": "Constructor Functions",
    "mode": "run",
    "description": "Write a factory function that constructs and validates a struct.",
    "hints": [
      "Return `Rectangle(size, size)` for square dimensions."
    ],
    "code": "// I AM NOT DONE\n// You can write factory functions to construct initialized structs.\n// TODO: Complete `create_square(size: int) -> Rectangle` returning width=size, height=size.\n\nstruct Rectangle {\n    width: int,\n    height: int\n}\n\nfn create_square(size: int) -> Rectangle {\n    // Return Rectangle with width and height equal to size\n}\n\nfn main() {\n    let sq = create_square(12)\n    assert(sq.width == 12 and sq.height == 12, \"Square dimensions must both equal 12\")\n    print(\"Square created:\", sq.width, \"x\", sq.height)\n}\n\nmain()\n",
    "solution": "struct Rectangle {\n    width: int,\n    height: int\n}\n\nfn create_square(size: int) -> Rectangle {\n    return Rectangle(size, size)\n}\n\nfn main() {\n    let sq = create_square(12)\n    assert(sq.width == 12 and sq.height == 12, \"Square dimensions must both equal 12\")\n    print(\"Square created:\", sq.width, \"x\", sq.height)\n}\n\nmain()\n"
  },
  {
    "id": "enums01",
    "name": "enums01",
    "topic": "07_enums",
    "topicTitle": "07_enums",
    "title": "Enum Declarations",
    "mode": "run",
    "description": "Declare an enum and access its member variants.",
    "hints": [
      "Declare `enum Status { Idle, Running, Paused, Stopped }`."
    ],
    "code": "// I AM NOT DONE\n// Enums declare a set of discrete named variants:\n//   enum Color { Red, Green, Blue }\n// Access variants via `Color.Red`.\n// TODO: Declare an enum `Status` with Idle, Running, and Stopped variants.\n\n// Declare enum Status here:\n\nfn main() {\n    let current = Status.Running\n    print(\"Current system status:\", current)\n}\n\nmain()\n",
    "solution": "enum Status {\n    Idle,\n    Running,\n    Stopped\n}\n\nfn main() {\n    let current = Status.Running\n    print(\"Current system status:\", current)\n}\n\nmain()\n"
  },
  {
    "id": "enums02",
    "name": "enums02",
    "topic": "07_enums",
    "topicTitle": "07_enums",
    "title": "Enum Variant Comparisons",
    "mode": "run",
    "description": "Compare enum values using the equality operator ==.",
    "hints": [
      "Compare `hero_dir == Direction.East`."
    ],
    "code": "// I AM NOT DONE\n// Enum variants can be compared with `==` and `!=`.\n// TODO: Verify if `hero_dir` is facing `Direction.East`.\n\nenum Direction {\n    North,\n    South,\n    East,\n    West\n}\n\nfn main() {\n    let hero_dir = Direction.East\n    let is_facing_east = false // Compare hero_dir == Direction.East\n\n    assert(is_facing_east == true, \"Hero must be facing East!\")\n    print(\"Hero facing East:\", is_facing_east)\n}\n\nmain()\n",
    "solution": "enum Direction {\n    North,\n    South,\n    East,\n    West\n}\n\nfn main() {\n    let hero_dir = Direction.East\n    let is_facing_east = (hero_dir == Direction.East)\n\n    assert(is_facing_east == true, \"Hero must be facing East!\")\n    print(\"Hero facing East:\", is_facing_east)\n}\n\nmain()\n"
  },
  {
    "id": "enums03",
    "name": "enums03",
    "topic": "07_enums",
    "topicTitle": "07_enums",
    "title": "State Machines with Enums",
    "mode": "run",
    "description": "Model a traffic light state machine transition.",
    "hints": [
      "If current is Red return Green; if Green return Yellow; else return Red."
    ],
    "code": "// I AM NOT DONE\n// Enums are ideal for state machines.\n// TODO: Complete `next_light`: Red -> Green -> Yellow -> Red.\n\nenum Light {\n    Red,\n    Green,\n    Yellow\n}\n\nfn next_light(current: Light) -> Light {\n    // TODO: Implement the transition sequence: Red -> Green -> Yellow -> Red\n    return Light.Red\n}\n\nfn main() {\n    let l1 = Light.Red\n    let l2 = next_light(l1)\n    let l3 = next_light(l2)\n\n    assert(l2 == Light.Green, \"Red must transition to Green\")\n    assert(l3 == Light.Yellow, \"Green must transition to Yellow\")\n    print(\"Traffic light transitions verified!\")\n}\n\nmain()\n",
    "solution": "enum Light {\n    Red,\n    Green,\n    Yellow\n}\n\nfn next_light(current: Light) -> Light {\n    if current == Light.Red {\n        return Light.Green\n    } elif current == Light.Green {\n        return Light.Yellow\n    } else {\n        return Light.Red\n    }\n}\n\nfn main() {\n    let l1 = Light.Red\n    let l2 = next_light(l1)\n    let l3 = next_light(l2)\n\n    assert(l2 == Light.Green, \"Red must transition to Green\")\n    assert(l3 == Light.Yellow, \"Green must transition to Yellow\")\n    print(\"Traffic light transitions verified!\")\n}\n\nmain()\n"
  },
  {
    "id": "traits01",
    "name": "traits01",
    "topic": "08_traits",
    "topicTitle": "08_traits",
    "title": "Traits and Interfaces",
    "mode": "run",
    "description": "Implement a trait method on a struct.",
    "hints": [
      "Implement `fn describe(self) -> string { return \"Player \" + self.name }` inside `impl Describable for Player`."
    ],
    "code": "// I AM NOT DONE\n// A `trait` defines a contract of method signatures:\n//   trait Describable { fn describe(self) -> string }\n// An `impl Trait for Struct` must provide every required method.\n// TODO: Implement `describe` for `Player`.\n\ntrait Describable {\n    fn describe(self) -> string\n}\n\nstruct Player {\n    name: string,\n    level: int\n}\n\nimpl Describable for Player {\n    // Add describe(self) -> string implementation here!\n}\n\nfn main() {\n    let p = Player(\"Hero\", 1)\n    let desc = p.describe()\n    assert(desc == \"Player Hero\", \"describe must return 'Player ' + self.name\")\n    print(desc)\n}\n\nmain()\n",
    "solution": "trait Describable {\n    fn describe(self) -> string\n}\n\nstruct Player {\n    name: string,\n    level: int\n}\n\nimpl Describable for Player {\n    fn describe(self) -> string {\n        return \"Player \" + self.name\n    }\n}\n\nfn main() {\n    let p = Player(\"Hero\", 1)\n    let desc = p.describe()\n    assert(desc == \"Player Hero\", \"describe must return 'Player ' + self.name\")\n    print(desc)\n}\n\nmain()\n"
  },
  {
    "id": "traits02",
    "name": "traits02",
    "topic": "08_traits",
    "topicTitle": "08_traits",
    "title": "Multiple Trait Implementations",
    "mode": "run",
    "description": "Implement the same trait across multiple distinct structs.",
    "hints": [
      "Implement `fn area(self) -> int { return self.side * self.side }` for Square."
    ],
    "code": "// I AM NOT DONE\n// Multiple structs can implement the same trait contract.\n// TODO: Implement `Area` for `Square`.\n\ntrait Area {\n    fn area(self) -> int\n}\n\nstruct Rect {\n    w: int,\n    h: int\n}\n\nimpl Area for Rect {\n    fn area(self) -> int {\n        return self.w * self.h\n    }\n}\n\nstruct Square {\n    side: int\n}\n\n// TODO: Implement Area for Square here:\n\nfn main() {\n    let r = Rect(4, 5)\n    let s = Square(6)\n\n    assert(r.area() == 20, \"Rect area must be 20\")\n    assert(s.area() == 36, \"Square area must be 36\")\n    print(\"Rect area:\", r.area(), \"Square area:\", s.area())\n}\n\nmain()\n",
    "solution": "trait Area {\n    fn area(self) -> int\n}\n\nstruct Rect {\n    w: int,\n    h: int\n}\n\nimpl Area for Rect {\n    fn area(self) -> int {\n        return self.w * self.h\n    }\n}\n\nstruct Square {\n    side: int\n}\n\nimpl Area for Square {\n    fn area(self) -> int {\n        return self.side * self.side\n    }\n}\n\nfn main() {\n    let r = Rect(4, 5)\n    let s = Square(6)\n\n    assert(r.area() == 20, \"Rect area must be 20\")\n    assert(s.area() == 36, \"Square area must be 36\")\n    print(\"Rect area:\", r.area(), \"Square area:\", s.area())\n}\n\nmain()\n"
  },
  {
    "id": "traits03",
    "name": "traits03",
    "topic": "08_traits",
    "topicTitle": "08_traits",
    "title": "Trait Methods with Parameters",
    "mode": "run",
    "description": "Define and implement trait methods that accept arguments.",
    "hints": [
      "Signature: `fn scale(self, factor: int) -> int`."
    ],
    "code": "// I AM NOT DONE\n// Trait methods can take extra parameters in addition to `self`.\n// TODO: Implement `scale(self, factor: int) -> int` for `Score`.\n\ntrait Scalable {\n    fn scale(self, factor: int) -> int\n}\n\nstruct Score {\n    points: int\n}\n\nimpl Scalable for Score {\n    // Implement scale here! Return self.points * factor\n}\n\nfn main() {\n    let sc = Score(15)\n    let doubled = sc.scale(2)\n    assert(doubled == 30, \"Scaled score must be 30\")\n    print(\"Scaled points:\", doubled)\n}\n\nmain()\n",
    "solution": "trait Scalable {\n    fn scale(self, factor: int) -> int\n}\n\nstruct Score {\n    points: int\n}\n\nimpl Scalable for Score {\n    fn scale(self, factor: int) -> int {\n        return self.points * factor\n    }\n}\n\nfn main() {\n    let sc = Score(15)\n    let doubled = sc.scale(2)\n    assert(doubled == 30, \"Scaled score must be 30\")\n    print(\"Scaled points:\", doubled)\n}\n\nmain()\n"
  },
  {
    "id": "errors01",
    "name": "errors01",
    "topic": "09_error_handling",
    "topicTitle": "09_error_handling",
    "title": "Try, Catch, and Throw",
    "mode": "run",
    "description": "Catch an exception with try / catch.",
    "hints": [
      "Wrap the call `validate_pin(9999)` with `try { ... } catch err { print(\"Caught error!\") }`."
    ],
    "code": "// I AM NOT DONE\n// Rove supports structured exceptions with `try`, `catch`, and `throw`.\n// TODO: Catch the error thrown by `validate_pin` and print \"Caught error!\".\n\nfn validate_pin(pin: int) {\n    if pin != 1234 {\n        throw \"Invalid PIN entered\"\n    }\n}\n\nfn main() {\n    // Wrap with try / catch:\n    validate_pin(9999)\n    print(\"Done\")\n}\n\nmain()\n",
    "solution": "fn validate_pin(pin: int) {\n    if pin != 1234 {\n        throw \"Invalid PIN entered\"\n    }\n}\n\nfn main() {\n    try {\n        validate_pin(9999)\n    } catch err {\n        print(\"Caught error!\")\n    }\n    print(\"Done\")\n}\n\nmain()\n"
  },
  {
    "id": "errors02",
    "name": "errors02",
    "topic": "09_error_handling",
    "topicTitle": "09_error_handling",
    "title": "Input Validation Exceptions",
    "mode": "run",
    "description": "Throw an error when an input value fails domain constraints.",
    "hints": [
      "If `port < 1` throw \"Port must be positive\"."
    ],
    "code": "// I AM NOT DONE\n// Functions can guard against invalid arguments by throwing descriptive errors.\n// TODO: If `port < 1`, throw \"Port must be positive\"!\n\nfn check_port(port: int) -> int {\n    // Add validation check here!\n    return port\n}\n\nfn main() {\n    var caught = false\n    try {\n        check_port(0)\n    } catch e {\n        set caught = true\n    }\n\n    assert(caught == true, \"check_port(0) must throw an error!\")\n    assert(check_port(8080) == 8080, \"Valid port 8080 should return intact\")\n    print(\"Port validation verified successfully!\")\n}\n\nmain()\n",
    "solution": "fn check_port(port: int) -> int {\n    if port < 1 {\n        throw \"Port must be positive\"\n    }\n    return port\n}\n\nfn main() {\n    var caught = false\n    try {\n        check_port(0)\n    } catch e {\n        set caught = true\n    }\n\n    assert(caught == true, \"check_port(0) must throw an error!\")\n    assert(check_port(8080) == 8080, \"Valid port 8080 should return intact\")\n    print(\"Port validation verified successfully!\")\n}\n\nmain()\n"
  },
  {
    "id": "errors03",
    "name": "errors03",
    "topic": "09_error_handling",
    "topicTitle": "09_error_handling",
    "title": "Recovery with Fallback",
    "mode": "run",
    "description": "Safely recover from an exception and provide a fallback value.",
    "hints": [
      "In catch block: `set result = -1`."
    ],
    "code": "// I AM NOT DONE\n// Exceptions can be recovered from cleanly by setting a safe fallback.\n// TODO: If `risky_divide` fails, catch the error and fallback `result = -1`.\n\nfn risky_divide(a: int, b: int) -> int {\n    if b == 0 {\n        throw \"Division by zero\"\n    }\n    return a / b\n}\n\nfn main() {\n    var result = 0\n    try {\n        set result = risky_divide(10, 0)\n    } catch err {\n        // Fallback to -1 on error:\n    }\n\n    assert(result == -1, \"Fallback result must be -1 on error!\")\n    print(\"Recovered with safe fallback:\", result)\n}\n\nmain()\n",
    "solution": "fn risky_divide(a: int, b: int) -> int {\n    if b == 0 {\n        throw \"Division by zero\"\n    }\n    return a / b\n}\n\nfn main() {\n    var result = 0\n    try {\n        set result = risky_divide(10, 0)\n    } catch err {\n        set result = -1\n    }\n\n    assert(result == -1, \"Fallback result must be -1 on error!\")\n    print(\"Recovered with safe fallback:\", result)\n}\n\nmain()\n"
  },
  {
    "id": "null01",
    "name": "null01",
    "topic": "10_null_safety",
    "topicTitle": "10_null_safety",
    "title": "Nullable Types and Coalescing",
    "mode": "run",
    "description": "Provide a default value using the null coalescing operator ??.",
    "hints": [
      "Write `let display_name: string = nickname ?? \"Guest\"`."
    ],
    "code": "// I AM NOT DONE\n// Optional types are written with a trailing `?` (e.g. `string?`, `int?`).\n// The null coalescing operator `??` provides a fallback value if the left is null.\n// TODO: Use `??` to provide \"Guest\" when `nickname` is null.\n\nfn main() {\n    let nickname: string? = null\n    let display_name: string = nickname // Use ?? \"Guest\"\n    assert(display_name == \"Guest\", \"display_name must fallback to 'Guest' when nickname is null!\")\n    print(\"Welcome,\", display_name)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let nickname: string? = null\n    let display_name: string = nickname ?? \"Guest\"\n    assert(display_name == \"Guest\", \"display_name must fallback to 'Guest' when nickname is null!\")\n    print(\"Welcome,\", display_name)\n}\n\nmain()\n"
  },
  {
    "id": "null02",
    "name": "null02",
    "topic": "10_null_safety",
    "topicTitle": "10_null_safety",
    "title": "Nullable Integers",
    "mode": "run",
    "description": "Handle optional integers int? with fallback defaults.",
    "hints": [
      "Write `let points = extra_score ?? 10`."
    ],
    "code": "// I AM NOT DONE\n// Scalar numbers can also be optional: `int?`, `float?`.\n// TODO: Fallback to `10` when `extra_score` is null using `??`.\n\nfn calculate_total(base: int, extra_score: int?) -> int {\n    let points = 0 // Use extra_score ?? 10\n    return base + points\n}\n\nfn main() {\n    let t1 = calculate_total(50, null)\n    let t2 = calculate_total(50, 25)\n\n    assert(t1 == 60, \"t1 with null extra_score must equal 60\")\n    assert(t2 == 75, \"t2 with 25 extra_score must equal 75\")\n    print(\"Calculated scores:\", t1, t2)\n}\n\nmain()\n",
    "solution": "fn calculate_total(base: int, extra_score: int?) -> int {\n    let points = extra_score ?? 10\n    return base + points\n}\n\nfn main() {\n    let t1 = calculate_total(50, null)\n    let t2 = calculate_total(50, 25)\n\n    assert(t1 == 60, \"t1 with null extra_score must equal 60\")\n    assert(t2 == 75, \"t2 with 25 extra_score must equal 75\")\n    print(\"Calculated scores:\", t1, t2)\n}\n\nmain()\n"
  },
  {
    "id": "null03",
    "name": "null03",
    "topic": "10_null_safety",
    "topicTitle": "10_null_safety",
    "title": "Guard Preconditions",
    "mode": "run",
    "description": "Guard against invalid parameters with early return.",
    "hints": [
      "Add `guard energy > 0 else { return \"blocked\" }` at the top of perform_action."
    ],
    "code": "// I AM NOT DONE\n// `guard condition else { return }` ensures a condition holds before continuing.\n// If the condition is false, the `else` block executes immediately.\n// TODO: Add a guard ensuring `energy > 0` else return \"blocked\"!\n\nfn perform_action(energy: int) -> string {\n    // Add guard statement here:\n    // guard energy > 0 else {\n    //     return \"blocked\"\n    // }\n\n    return \"success\"\n}\n\nfn main() {\n    let res1 = perform_action(0)  // Should be blocked by guard!\n    let res2 = perform_action(50) // Should succeed\n    assert(res1 == \"blocked\", \"0 energy must be blocked by guard!\")\n    assert(res2 == \"success\", \"50 energy must succeed!\")\n    print(\"Guards verified successfully!\")\n}\n\nmain()\n",
    "solution": "fn perform_action(energy: int) -> string {\n    guard energy > 0 else {\n        return \"blocked\"\n    }\n\n    return \"success\"\n}\n\nfn main() {\n    let res1 = perform_action(0)\n    let res2 = perform_action(50)\n    assert(res1 == \"blocked\", \"0 energy must be blocked by guard!\")\n    assert(res2 == \"success\", \"50 energy must succeed!\")\n    print(\"Guards verified successfully!\")\n}\n\nmain()\n"
  },
  {
    "id": "null04",
    "name": "null04",
    "topic": "10_null_safety",
    "topicTitle": "10_null_safety",
    "title": "Multi-Condition Guards",
    "mode": "run",
    "description": "Protect operations with multi-condition guard statements.",
    "hints": [
      "Write `guard age >= 18 and has_license else { return false }`."
    ],
    "code": "// I AM NOT DONE\n// `guard` conditions can combine multiple checks with `and` / `or`.\n// TODO: Require that `age >= 18 and has_license` holds; else return `false`.\n\nfn can_rent_car(age: int, has_license: bool) -> bool {\n    // Add guard statement here!\n\n    return true\n}\n\nfn main() {\n    assert(can_rent_car(16, true) == false, \"Underage cannot rent\")\n    assert(can_rent_car(22, false) == false, \"No license cannot rent\")\n    assert(can_rent_car(25, true) == true, \"Adult with license can rent\")\n    print(\"Rental permissions verified!\")\n}\n\nmain()\n",
    "solution": "fn can_rent_car(age: int, has_license: bool) -> bool {\n    guard age >= 18 and has_license else {\n        return false\n    }\n\n    return true\n}\n\nfn main() {\n    assert(can_rent_car(16, true) == false, \"Underage cannot rent\")\n    assert(can_rent_car(22, false) == false, \"No license cannot rent\")\n    assert(can_rent_car(25, true) == true, \"Adult with license can rent\")\n    print(\"Rental permissions verified!\")\n}\n\nmain()\n"
  },
  {
    "id": "pipeline01",
    "name": "pipeline01",
    "topic": "11_pipelines",
    "topicTitle": "11_pipelines",
    "title": "Pipeline Operator (|&gt;)",
    "mode": "run",
    "description": "Chain function calls using the pipeline operator.",
    "hints": [
      "Write `let result = initial |> increment |> double_val`."
    ],
    "code": "// I AM NOT DONE\n// The pipe operator `|>` chains data through functions:\n//   `value |> fn1 |> fn2` passes the result of each call to the next.\n// TODO: Pipe `initial` through `increment` and then `double_val`.\n\nfn increment(x: int) -> int {\n    return x + 1\n}\n\nfn double_val(x: int) -> int {\n    return x * 2\n}\n\nfn main() {\n    let initial = 4\n    // (4 + 1) * 2 = 10\n    let result = initial // Fix using |> increment |> double_val\n    assert(result == 10, \"Pipelined result of (4 + 1) * 2 must be 10!\")\n    print(\"Pipelined result:\", result)\n}\n\nmain()\n",
    "solution": "fn increment(x: int) -> int {\n    return x + 1\n}\n\nfn double_val(x: int) -> int {\n    return x * 2\n}\n\nfn main() {\n    let initial = 4\n    let result = initial |> increment |> double_val\n    assert(result == 10, \"Pipelined result of (4 + 1) * 2 must be 10!\")\n    print(\"Pipelined result:\", result)\n}\n\nmain()\n"
  },
  {
    "id": "pipeline02",
    "name": "pipeline02",
    "topic": "11_pipelines",
    "topicTitle": "11_pipelines",
    "title": "Data Processing Pipelines",
    "mode": "run",
    "description": "Process data through a multi-stage math pipeline.",
    "hints": [
      "Chain: `raw_val |> add_tax |> apply_discount`."
    ],
    "code": "// I AM NOT DONE\n// Pipelines make multi-stage transformations clean and readable.\n// TODO: Pipe `raw_val` through `add_tax` and then `apply_discount`.\n// 100 + 20 (tax) = 120 -> 120 - 15 (discount) = 105!\n\nfn add_tax(price: int) -> int {\n    return price + 20\n}\n\nfn apply_discount(price: int) -> int {\n    return price - 15\n}\n\nfn main() {\n    let raw_val = 100\n    // Chain with |>:\n    let final_price = raw_val\n\n    assert(final_price == 105, \"final_price must equal 105!\")\n    print(\"Pipelined checkout total:\", final_price)\n}\n\nmain()\n",
    "solution": "fn add_tax(price: int) -> int {\n    return price + 20\n}\n\nfn apply_discount(price: int) -> int {\n    return price - 15\n}\n\nfn main() {\n    let raw_val = 100\n    let final_price = raw_val |> add_tax |> apply_discount\n\n    assert(final_price == 105, \"final_price must equal 105!\")\n    print(\"Pipelined checkout total:\", final_price)\n}\n\nmain()\n"
  },
  {
    "id": "defer01",
    "name": "defer01",
    "topic": "12_defer",
    "topicTitle": "12. Defer & RAII Scope Cleanup",
    "title": "Scope Cleanup with defer",
    "mode": "run",
    "description": "Ensure cleanup actions run on scope exit with defer.",
    "hints": [
      "Add `defer release_lock()` inside `do_critical_work()` so cleanup runs on return."
    ],
    "code": "// I AM NOT DONE\n// `defer expression` schedules an expression to run when the surrounding function exits.\n// TODO: Use `defer` so `release_lock()` is guaranteed to run when `do_critical_work` exits.\n\nvar cleanup_state: Array<bool> = [false]\n\nfn release_lock() {\n    set cleanup_state[0] = true\n}\n\nfn do_critical_work() {\n    set cleanup_state[0] = false\n    // TODO: Add defer release_lock() here.\n    print(\"Performing critical work with lock held...\")\n}\n\nfn main() {\n    do_critical_work()\n    assert(cleanup_state[0] == true, \"Cleanup must run automatically via defer upon exit!\")\n    print(\"Lock safely released:\", cleanup_state[0])\n}\n\nmain()\n",
    "solution": "var cleanup_state: Array<bool> = [false]\n\nfn release_lock() {\n    set cleanup_state[0] = true\n}\n\nfn do_critical_work() {\n    set cleanup_state[0] = false\n    defer release_lock()\n    print(\"Performing critical work with lock held...\")\n}\n\nfn main() {\n    do_critical_work()\n    assert(cleanup_state[0] == true, \"Cleanup must run automatically via defer upon exit!\")\n    print(\"Lock safely released:\", cleanup_state[0])\n}\n\nmain()\n"
  },
  {
    "id": "defer02",
    "name": "defer02",
    "topic": "12_defer",
    "topicTitle": "12. Defer & RAII Scope Cleanup",
    "title": "Multiple Defer Execution",
    "mode": "run",
    "description": "Observe that defer statements execute when exiting their scope.",
    "hints": [
      "Add `defer cleanup_step1()` and then `defer cleanup_step2()`; deferred calls run in LIFO order."
    ],
    "code": "// I AM NOT DONE\n// Multiple defer calls execute in last-in, first-out order before return.\n// TODO: Add both cleanup calls so `cleanup_order` becomes \"21\".\n\nvar cleanup_log: Array<string> = [\"\"]\n\nfn cleanup_step1() {\n    set cleanup_log[0] = cleanup_log[0] + \"1\"\n}\n\nfn cleanup_step2() {\n    set cleanup_log[0] = cleanup_log[0] + \"2\"\n}\n\nfn process_batch() {\n    set cleanup_log[0] = \"\"\n    print(\"Batch processing in progress...\")\n    // TODO: Add defer cleanup_step1() and defer cleanup_step2()\n}\n\nfn main() {\n    process_batch()\n    assert(cleanup_log[0] == \"21\", \"Deferred cleanup must execute in LIFO order!\")\n    print(\"Cleanup order:\", cleanup_log[0])\n}\n\nmain()\n",
    "solution": "var cleanup_log: Array<string> = [\"\"]\n\nfn cleanup_step1() {\n    set cleanup_log[0] = cleanup_log[0] + \"1\"\n}\n\nfn cleanup_step2() {\n    set cleanup_log[0] = cleanup_log[0] + \"2\"\n}\n\nfn process_batch() {\n    set cleanup_log[0] = \"\"\n    print(\"Batch processing in progress...\")\n    defer cleanup_step1()\n    defer cleanup_step2()\n}\n\nfn main() {\n    process_batch()\n    assert(cleanup_log[0] == \"21\", \"Deferred cleanup must execute in LIFO order!\")\n    print(\"Cleanup order:\", cleanup_log[0])\n}\n\nmain()\n"
  },
  {
    "id": "math01",
    "name": "math01",
    "topic": "13_math_and_logic",
    "topicTitle": "13_math_and_logic",
    "title": "Modulo and Divisibility",
    "mode": "run",
    "description": "Check if numbers are even or odd using the modulo operator %.",
    "hints": [
      "A number is even if `n % 2 == 0`."
    ],
    "code": "// I AM NOT DONE\n// The modulo operator `%` calculates the remainder of integer division.\n// TODO: Complete `is_even(n: int) -> bool` using `n % 2`.\n\nfn is_even(n: int) -> bool {\n    // Return true if n % 2 == 0\n    return false\n}\n\nfn main() {\n    assert(is_even(42) == true, \"42 must be even\")\n    assert(is_even(17) == false, \"17 must be odd\")\n    print(\"Even/odd tests passed!\")\n}\n\nmain()\n",
    "solution": "fn is_even(n: int) -> bool {\n    return n % 2 == 0\n}\n\nfn main() {\n    assert(is_even(42) == true, \"42 must be even\")\n    assert(is_even(17) == false, \"17 must be odd\")\n    print(\"Even/odd tests passed!\")\n}\n\nmain()\n"
  },
  {
    "id": "math02",
    "name": "math02",
    "topic": "13_math_and_logic",
    "topicTitle": "13_math_and_logic",
    "title": "Bitwise Operations",
    "mode": "run",
    "description": "Perform bitwise AND &, OR |, and left-shift << operations.",
    "hints": [
      "`1 << 4` shifts 1 left by 4 bits (16).",
      "`flags | 1` sets the lowest bit."
    ],
    "code": "// I AM NOT DONE\n// Rove supports bitwise operators: `&` (AND), `|` (OR), `^` (XOR), and `<<` (shift).\n// TODO:\n// 1. Shift 1 left by 4 bits to get 16 (`1 << 4`).\n// 2. Bitwise OR `flags` with `1` to set the flag.\n\nfn main() {\n    let shifted = 0 // Compute 1 << 4\n    let flags = 8\n    let updated = 0 // Compute flags | 1\n\n    assert(shifted == 16, \"1 << 4 must be 16\")\n    assert(updated == 9, \"8 | 1 must be 9\")\n    print(\"Shifted:\", shifted, \"Updated flags:\", updated)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let shifted = 1 << 4\n    let flags = 8\n    let updated = flags | 1\n\n    assert(shifted == 16, \"1 << 4 must be 16\")\n    assert(updated == 9, \"8 | 1 must be 9\")\n    print(\"Shifted:\", shifted, \"Updated flags:\", updated)\n}\n\nmain()\n"
  },
  {
    "id": "tests01",
    "name": "tests01",
    "topic": "14_testing",
    "topicTitle": "14_testing",
    "title": "In-File Unit Testing",
    "mode": "test",
    "description": "Fix an assertion error in an in-file unit test.",
    "hints": [
      "The assertion checks `assert(result == 5, ...)`, but `add(2, 2)` equals 4!",
      "Change `5` to `4` in the assertion."
    ],
    "code": "// I AM NOT DONE\n// Rove has first-class unit tests using `test \"name\" { assert(...) }`.\n// When run with `rove test`, all assertions are verified.\n// TODO: Fix the broken assertion below so the test passes.\n\nfn add(a: int, b: int) -> int {\n    return a + b\n}\n\ntest \"verify addition\" {\n    var result = add(2, 2)\n    assert(result == 5, \"2 + 2 must equal 4!\")\n    print(\"  [PASS] 2 + 2 == 4\")\n}\n",
    "solution": "fn add(a: int, b: int) -> int {\n    return a + b\n}\n\ntest \"verify addition\" {\n    var result = add(2, 2)\n    assert(result == 4, \"2 + 2 must equal 4!\")\n    print(\"  [PASS] 2 + 2 == 4\")\n}\n"
  },
  {
    "id": "tests02",
    "name": "tests02",
    "topic": "14_testing",
    "topicTitle": "14_testing",
    "title": "Multiple In-File Tests",
    "mode": "test",
    "description": "Add a second test block to verify subtraction.",
    "hints": [
      "Add a test block: `test \"verify subtraction\" { assert(sub(10, 4) == 6, ...) }`."
    ],
    "code": "// I AM NOT DONE\n// Multiple test blocks can be declared in a single file.\n// TODO: Add a second test block named \"subtraction test\" that asserts `sub(10, 4) == 6`.\n\nfn sub(a: int, b: int) -> int {\n    return a - b\n}\n\ntest \"subtraction test\" {\n    var res = sub(10, 4)\n    assert(res == 0, \"10 - 4 must equal 6!\")\n    print(\"  [PASS] 10 - 4 == 6\")\n}\n",
    "solution": "fn sub(a: int, b: int) -> int {\n    return a - b\n}\n\ntest \"subtraction test\" {\n    var res = sub(10, 4)\n    assert(res == 6, \"10 - 4 must equal 6!\")\n    print(\"  [PASS] 10 - 4 == 6\")\n}\n"
  },
  {
    "id": "quiz01",
    "name": "quiz01",
    "topic": "15_quizzes",
    "topicTitle": "15_quizzes",
    "title": "Capstone Quiz: RPG Inventory Score",
    "mode": "run",
    "description": "Accumulate total gear score across an array of item structs.",
    "hints": [
      "Loop `for i in 0..2`.",
      "Inside the loop: `let item = items[i]`, then `set total_score = total_score + item.calculate_value()`."
    ],
    "code": "// I AM NOT DONE\n// CAPSTONE QUIZ 1: RPG Inventory Scorer\n// Combine what you learned: Structs, Methods, Loops, Match, and Guard!\n//\n// Calculate the total gear score of an adventurer's items.\n// Rarity multiplier:\n//   \"Common\"    => 1\n//   \"Rare\"      => 2\n//   \"Legendary\" => 5\n//   _           => 0\n//\n// Item score = item.base_power * rarity_multiplier\n// Expected total gear score for the given items:\n//   Sword (10 * 1 = 10) + Shield (20 * 2 = 40) + Ring (10 * 5 = 50) = 100!\n\nstruct Item {\n    name: string,\n    base_power: int,\n    rarity: string\n}\n\nimpl Item {\n    fn calculate_value(self) -> int {\n        let mult = match self.rarity {\n            \"Common\" => 1,\n            \"Rare\" => 2,\n            \"Legendary\" => 5,\n            _ => 0\n        }\n        return self.base_power * mult\n    }\n}\n\nfn main() {\n    let items = [\n        Item(\"Iron Sword\", 10, \"Common\"),\n        Item(\"Silver Shield\", 20, \"Rare\"),\n        Item(\"Dragon Ring\", 10, \"Legendary\")\n    ]\n\n    var total_score: int = 0\n    // TODO: Loop through items 0..2, call item.calculate_value(),\n    // and accumulate into `total_score`!\n\n    assert(total_score == 100, \"Total gear score must be 100!\")\n    print(\"Total Gear Score:\", total_score)\n}\n\nmain()\n",
    "solution": "struct Item {\n    name: string,\n    base_power: int,\n    rarity: string\n}\n\nimpl Item {\n    fn calculate_value(self) -> int {\n        let mult = match self.rarity {\n            \"Common\" => 1,\n            \"Rare\" => 2,\n            \"Legendary\" => 5,\n            _ => 0\n        }\n        return self.base_power * mult\n    }\n}\n\nfn main() {\n    let items = [\n        Item(\"Iron Sword\", 10, \"Common\"),\n        Item(\"Silver Shield\", 20, \"Rare\"),\n        Item(\"Dragon Ring\", 10, \"Legendary\")\n    ]\n\n    var total_score: int = 0\n    for i in 0..2 {\n        let item = items[i]\n        set total_score = total_score + item.calculate_value()\n    }\n\n    assert(total_score == 100, \"Total gear score must be 100!\")\n    print(\"Total Gear Score:\", total_score)\n}\n\nmain()\n"
  },
  {
    "id": "quiz02",
    "name": "quiz02",
    "topic": "15_quizzes",
    "topicTitle": "15_quizzes",
    "title": "Capstone Quiz: Banking Ledger System",
    "mode": "run",
    "description": "Implement a banking ledger with deposits, withdrawals, and balance guards.",
    "hints": [
      "In `deposit`: guard `amount > 0` else return `self.balance`.",
      "In `withdraw`: guard `amount > 0 and self.balance >= amount` else return `self.balance`."
    ],
    "code": "// I AM NOT DONE\n// CAPSTONE QUIZ 2: Banking Ledger System\n// Model a secure bank account:\n// 1. Deposits must only accept positive amounts (> 0).\n// 2. Withdrawals must not overdraw the account (amount <= balance).\n//\n// TODO: Implement `deposit` and `withdraw` with proper `guard` checks!\n\nstruct Account {\n    owner: string,\n    balance: int\n}\n\nimpl Account {\n    fn deposit(self, amount: int) -> int {\n        // Add guard ensuring amount > 0 else return self.balance!\n        return self.balance\n    }\n\n    fn withdraw(self, amount: int) -> int {\n        // Add guard ensuring amount > 0 and self.balance >= amount else return self.balance!\n        return self.balance\n    }\n}\n\nfn main() {\n    var acc = Account(\"Kurt\", 500)\n\n    // Deposit 200 -> balance becomes 700\n    let b1 = acc.deposit(200)\n    set acc.balance = b1\n\n    // Invalid withdraw (1000 > 700) -> blocked, stays 700\n    let b2 = acc.withdraw(1000)\n    set acc.balance = b2\n\n    // Valid withdraw (300) -> balance becomes 400\n    let b3 = acc.withdraw(300)\n    set acc.balance = b3\n\n    assert(acc.balance == 400, \"Final balance after transactions must be 400!\")\n    print(\"Account owner:\", acc.owner, \"Final verified balance:\", acc.balance)\n}\n\nmain()\n",
    "solution": "struct Account {\n    owner: string,\n    balance: int\n}\n\nimpl Account {\n    fn deposit(self, amount: int) -> int {\n        guard amount > 0 else { return self.balance }\n        return self.balance + amount\n    }\n\n    fn withdraw(self, amount: int) -> int {\n        guard amount > 0 else { return self.balance }\n        guard self.balance >= amount else { return self.balance }\n        return self.balance - amount\n    }\n}\n\nfn main() {\n    var acc = Account(\"Kurt\", 500)\n\n    let b1 = acc.deposit(200)\n    set acc.balance = b1\n\n    let b2 = acc.withdraw(1000)\n    set acc.balance = b2\n\n    let b3 = acc.withdraw(300)\n    set acc.balance = b3\n\n    assert(acc.balance == 400, \"Final balance after transactions must be 400!\")\n    print(\"Account owner:\", acc.owner, \"Final verified balance:\", acc.balance)\n}\n\nmain()\n"
  },
  {
    "id": "quiz03",
    "name": "quiz03",
    "topic": "15_quizzes",
    "topicTitle": "15_quizzes",
    "title": "Capstone Quiz: Character Level-Up System",
    "mode": "run",
    "description": "Calculate hero stat boosts and level-ups using pipelines and match.",
    "hints": [
      "Use `self.attack |> add_buff |> double_buff` inside `boosted_attack`.",
      "Match on `self.level`: 10 => \"Champion\", 5 => \"Knight\", _ => \"Novice\"."
    ],
    "code": "// I AM NOT DONE\n// CAPSTONE QUIZ 3: Character Level-Up System\n// Combine Pipelines, Structs, Methods, and Pattern Matching!\n//\n// TODO:\n// 1. Implement `boosted_attack` by piping `self.attack` through `add_buff` (+10) then `double_buff` (*2).\n//    For attack = 20: (20 + 10) * 2 = 60!\n// 2. Return title based on level: 10 => \"Champion\", 5 => \"Knight\", _ => \"Novice\".\n\nfn add_buff(val: int) -> int {\n    return val + 10\n}\n\nfn double_buff(val: int) -> int {\n    return val * 2\n}\n\nstruct Hero {\n    name: string,\n    level: int,\n    attack: int\n}\n\nimpl Hero {\n    fn boosted_attack(self) -> int {\n        // Pipe self.attack through add_buff and double_buff:\n        return self.attack\n    }\n\n    fn title(self) -> string {\n        return match self.level {\n            10 => \"Champion\",\n            5 => \"Knight\",\n            _ => \"Novice\"\n        }\n    }\n}\n\nfn main() {\n    let hero = Hero(\"Kurt\", 10, 20)\n\n    let final_atk = hero.boosted_attack()\n    let rank = hero.title()\n\n    assert(final_atk == 60, \"Boosted attack must be (20 + 10) * 2 = 60!\")\n    assert(rank == \"Champion\", \"Level 10 hero must have rank 'Champion'!\")\n    print(\"Hero:\", hero.name, \"Rank:\", rank, \"Attack:\", final_atk)\n}\n\nmain()\n",
    "solution": "fn add_buff(val: int) -> int {\n    return val + 10\n}\n\nfn double_buff(val: int) -> int {\n    return val * 2\n}\n\nstruct Hero {\n    name: string,\n    level: int,\n    attack: int\n}\n\nimpl Hero {\n    fn boosted_attack(self) -> int {\n        return self.attack |> add_buff |> double_buff\n    }\n\n    fn title(self) -> string {\n        return match self.level {\n            10 => \"Champion\",\n            5 => \"Knight\",\n            _ => \"Novice\"\n        }\n    }\n}\n\nfn main() {\n    let hero = Hero(\"Kurt\", 10, 20)\n\n    let final_atk = hero.boosted_attack()\n    let rank = hero.title()\n\n    assert(final_atk == 60, \"Boosted attack must be (20 + 10) * 2 = 60!\")\n    assert(rank == \"Champion\", \"Level 10 hero must have rank 'Champion'!\")\n    print(\"Hero:\", hero.name, \"Rank:\", rank, \"Attack:\", final_atk)\n}\n\nmain()\n"
  },
  {
    "id": "strings01",
    "name": "strings01",
    "topic": "16_modern_expressions",
    "topicTitle": "16. Modern Expressions & Navigation",
    "title": "Unicode-Safe String Interpolation",
    "mode": "run",
    "description": "Build readable Unicode text with typed interpolation instead of manual concatenation.",
    "hints": [
      "Interpolated strings begin with `$\"` and evaluate expressions inside `{...}`.",
      "Use `$\"{city}: {signals} signals [night]\"`; Rove preserves the Unicode text without normalization."
    ],
    "code": "// I AM NOT DONE\n// Interpolation keeps values typed until they are formatted and avoids long\n// chains of string concatenation. Unicode text remains intact.\n// TODO: build exactly \"İstanbul: 3 signals [night]\" with one interpolated string.\n\nfn main() {\n    let city = \"İstanbul\"\n    let signals = 3\n    let summary = city\n\n    assert(summary == \"İstanbul: 3 signals [night]\", \"summary must include both values\")\n    print(summary)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let city = \"İstanbul\"\n    let signals = 3\n    let summary = $\"{city}: {signals} signals [night]\"\n\n    assert(summary == \"İstanbul: 3 signals [night]\", \"summary must include both values\")\n    print(summary)\n}\n\nmain()\n"
  },
  {
    "id": "navigation01",
    "name": "navigation01",
    "topic": "16_modern_expressions",
    "topicTitle": "16. Modern Expressions & Navigation",
    "title": "Safe Navigation Through Nested Data",
    "mode": "run",
    "description": "Traverse nullable struct fields with ?. and provide one explicit fallback with ??.",
    "hints": [
      "Each `?.` stops the member chain when its left side is null.",
      "Use `profile?.address?.city ?? \"unknown\"` so absence is handled once at the boundary."
    ],
    "code": "// I AM NOT DONE\n// A profile, its address, or the city may be absent. Do not add nested ifs.\n// TODO: safely read the city and fall back to \"unknown\".\n\nstruct Address { city: string? }\nstruct Profile { address: Address? }\n\nfn city_label(profile: Profile?) -> string {\n    return \"missing\"\n}\n\nfn main() {\n    let absent: Profile? = null\n    let present: Profile? = Profile(Address(\"Kyoto\"))\n    assert(city_label(absent) == \"unknown\", \"absent profile needs a fallback\")\n    assert(city_label(present) == \"Kyoto\", \"present city must survive navigation\")\n    print(city_label(absent), city_label(present))\n}\n\nmain()\n",
    "solution": "struct Address { city: string? }\nstruct Profile { address: Address? }\n\nfn city_label(profile: Profile?) -> string {\n    return profile?.address?.city ?? \"unknown\"\n}\n\nfn main() {\n    let absent: Profile? = null\n    let present: Profile? = Profile(Address(\"Kyoto\"))\n    assert(city_label(absent) == \"unknown\", \"absent profile needs a fallback\")\n    assert(city_label(present) == \"Kyoto\", \"present city must survive navigation\")\n    print(city_label(absent), city_label(present))\n}\n\nmain()\n"
  },
  {
    "id": "match04",
    "name": "match04",
    "topic": "16_modern_expressions",
    "topicTitle": "16. Modern Expressions & Navigation",
    "title": "Single-Evaluation Match",
    "mode": "run",
    "description": "Use a value-producing match so a side-effecting subject is evaluated exactly once.",
    "hints": [
      "Calling `read_status()` in every condition repeats its side effect.",
      "A match subject is evaluated once: `match read_status() { 200 => ..., _ => ... }`."
    ],
    "code": "// I AM NOT DONE\n// Repeated calls can observe different state or repeat expensive work.\n// TODO: replace the repeated if checks with one value-producing match.\n\nfn read_status(state: Array<int>) -> int {\n    set state[0] = state[0] + 1\n    if state[0] == 1 { return 500 }\n    return 404\n}\n\nfn status_label(state: Array<int>) -> string {\n    if read_status(state) == 200 { return \"ok\" }\n    if read_status(state) == 404 { return \"missing\" }\n    return \"other\"\n}\n\nfn main() {\n    let state = [0]\n    let label = status_label(state)\n    assert(label == \"other\", \"the first status must map to other\")\n    assert(state[0] == 1, \"the status source must be evaluated exactly once\")\n    print(label, \"reads:\", state[0])\n}\n\nmain()\n",
    "solution": "fn read_status(state: Array<int>) -> int {\n    set state[0] = state[0] + 1\n    if state[0] == 1 { return 500 }\n    return 404\n}\n\nfn status_label(state: Array<int>) -> string {\n    return match read_status(state) {\n        200 => \"ok\",\n        404 => \"missing\",\n        _ => \"other\"\n    }\n}\n\nfn main() {\n    let state = [0]\n    let label = status_label(state)\n    assert(label == \"other\", \"the first status must map to other\")\n    assert(state[0] == 1, \"the status source must be evaluated exactly once\")\n    print(label, \"reads:\", state[0])\n}\n\nmain()\n"
  },
  {
    "id": "result01",
    "name": "result01",
    "topic": "17_results",
    "topicTitle": "17. Result<T, E> & Fallible APIs",
    "title": "Payload Enums as Domain Data",
    "mode": "run",
    "description": "Model alternatives that carry typed data and destructure their payloads in match arms.",
    "hints": [
      "A payload variant is declared as `Message(string)` and constructed as `Message(\"...\")`.",
      "Bind the payload in the pattern: `Message(text) => text`."
    ],
    "code": "// I AM NOT DONE\n// Unlike a plain enum, each Event variant carries the data relevant to it.\n// TODO: return the text stored inside Message instead of a fixed label.\n\nenum Event {\n    Message(string),\n    Connected(int),\n    Tick()\n}\n\nfn describe(event: Event) -> string {\n    match event {\n        Message(text) => return \"message\",\n        Connected(id) => return $\"client {id}\",\n        Tick() => return \"tick\"\n    }\n    return \"unknown\"\n}\n\nfn main() {\n    assert(describe(Message(\"hello\")) == \"hello\", \"Message must expose its payload\")\n    assert(describe(Connected(7)) == \"client 7\", \"Connected must preserve its id\")\n    print(describe(Message(\"hello\")))\n}\n\nmain()\n",
    "solution": "enum Event {\n    Message(string),\n    Connected(int),\n    Tick()\n}\n\nfn describe(event: Event) -> string {\n    match event {\n        Message(text) => return text,\n        Connected(id) => return $\"client {id}\",\n        Tick() => return \"tick\"\n    }\n    return \"unknown\"\n}\n\nfn main() {\n    assert(describe(Message(\"hello\")) == \"hello\", \"Message must expose its payload\")\n    assert(describe(Connected(7)) == \"client 7\", \"Connected must preserve its id\")\n    print(describe(Message(\"hello\")))\n}\n\nmain()\n"
  },
  {
    "id": "result02",
    "name": "result02",
    "topic": "17_results",
    "topicTitle": "17. Result<T, E> & Fallible APIs",
    "title": "Recoverable Errors with Result",
    "mode": "run",
    "description": "Represent an expected failure with Result<T, E> and force callers to handle both outcomes.",
    "hints": [
      "Return `Err(\"division by zero\")` when the denominator is zero.",
      "Return `Ok(left / right)` for the successful branch."
    ],
    "code": "// I AM NOT DONE\n// Invalid user input is an expected outcome, not necessarily an exception.\n// TODO: make divide return Err for zero and Ok for valid division.\n\nfn divide(left: int, right: int) -> Result<int, string> {\n    return Ok(0)\n}\n\nfn main() {\n    match divide(12, 3) {\n        Ok(value) => assert(value == 4, \"12 / 3 must be 4\"),\n        Err(error) => assert(false, \"valid division unexpectedly failed\")\n    }\n    match divide(12, 0) {\n        Ok(value) => assert(false, \"division by zero must not succeed\"),\n        Err(error) => assert(error == \"division by zero\", \"error must explain the failure\")\n    }\n    print(\"both Result branches verified\")\n}\n\nmain()\n",
    "solution": "fn divide(left: int, right: int) -> Result<int, string> {\n    if right == 0 { return Err(\"division by zero\") }\n    return Ok(left / right)\n}\n\nfn main() {\n    match divide(12, 3) {\n        Ok(value) => assert(value == 4, \"12 / 3 must be 4\"),\n        Err(error) => assert(false, \"valid division unexpectedly failed\")\n    }\n    match divide(12, 0) {\n        Ok(value) => assert(false, \"division by zero must not succeed\"),\n        Err(error) => assert(error == \"division by zero\", \"error must explain the failure\")\n    }\n    print(\"both Result branches verified\")\n}\n\nmain()\n"
  },
  {
    "id": "result03",
    "name": "result03",
    "topic": "17_results",
    "topicTitle": "17. Result<T, E> & Fallible APIs",
    "title": "Propagating Result with ?",
    "mode": "run",
    "description": "Propagate Err from a Result-returning function while continuing with the unwrapped Ok value.",
    "hints": [
      "Postfix `?` unwraps Ok and immediately returns Err from the enclosing Result function.",
      "Use `let value = source(ok)?`; the enclosing function already has a compatible error type."
    ],
    "code": "// I AM NOT DONE\n// `unwrap()` turns an expected error into a runtime failure.\n// TODO: propagate the error from source with postfix ? instead.\n\nfn source(ok: bool) -> Result<int, string> {\n    if ok { return Ok(40) }\n    return Err(\"offline\")\n}\n\nfn calculate(ok: bool) -> Result<int, string> {\n    let value = source(ok).unwrap()\n    return Ok(value + 2)\n}\n\nfn main() {\n    match calculate(true) {\n        Ok(value) => assert(value == 42, \"successful value must be transformed\"),\n        Err(error) => assert(false, \"successful calculation unexpectedly failed\")\n    }\n    match calculate(false) {\n        Ok(value) => assert(false, \"failure must propagate\"),\n        Err(error) => assert(error == \"offline\", \"original error must be preserved\")\n    }\n    print(\"Result propagation verified\")\n}\n\nmain()\n",
    "solution": "fn source(ok: bool) -> Result<int, string> {\n    if ok { return Ok(40) }\n    return Err(\"offline\")\n}\n\nfn calculate(ok: bool) -> Result<int, string> {\n    let value = source(ok)?\n    return Ok(value + 2)\n}\n\nfn main() {\n    match calculate(true) {\n        Ok(value) => assert(value == 42, \"successful value must be transformed\"),\n        Err(error) => assert(false, \"successful calculation unexpectedly failed\")\n    }\n    match calculate(false) {\n        Ok(value) => assert(false, \"failure must propagate\"),\n        Err(error) => assert(error == \"offline\", \"original error must be preserved\")\n    }\n    print(\"Result propagation verified\")\n}\n\nmain()\n"
  },
  {
    "id": "result04",
    "name": "result04",
    "topic": "17_results",
    "topicTitle": "17. Result<T, E> & Fallible APIs",
    "title": "Composing Fallible Operations",
    "mode": "run",
    "description": "Compose multiple Result-producing functions without losing the first failure.",
    "hints": [
      "Use postfix `?` after each operation that may fail.",
      "Unwrap both `parse_port(text)?` and `validate_port(port)?`, then return `Ok(valid)`."
    ],
    "code": "// I AM NOT DONE\n// A boundary function should preserve the exact error from the step that failed.\n// TODO: compose parse_port and validate_port with ?.\n\nfn parse_port(text: string) -> Result<int, string> {\n    if text == \"8080\" { return Ok(8080) }\n    return Err(\"not a supported port literal\")\n}\n\nfn validate_port(port: int) -> Result<int, string> {\n    if port > 0 { return Ok(port) }\n    return Err(\"port must be positive\")\n}\n\nfn load_port(text: string) -> Result<int, string> {\n    return Ok(0)\n}\n\nfn main() {\n    match load_port(\"8080\") {\n        Ok(port) => assert(port == 8080, \"valid port must survive both steps\"),\n        Err(error) => assert(false, \"valid port unexpectedly failed\")\n    }\n    match load_port(\"bad\") {\n        Ok(port) => assert(false, \"bad text must not become a port\"),\n        Err(error) => assert(error == \"not a supported port literal\", \"preserve parse error\")\n    }\n    print(\"fallible composition verified\")\n}\n\nmain()\n",
    "solution": "fn parse_port(text: string) -> Result<int, string> {\n    if text == \"8080\" { return Ok(8080) }\n    return Err(\"not a supported port literal\")\n}\n\nfn validate_port(port: int) -> Result<int, string> {\n    if port > 0 { return Ok(port) }\n    return Err(\"port must be positive\")\n}\n\nfn load_port(text: string) -> Result<int, string> {\n    let port = parse_port(text)?\n    let valid = validate_port(port)?\n    return Ok(valid)\n}\n\nfn main() {\n    match load_port(\"8080\") {\n        Ok(port) => assert(port == 8080, \"valid port must survive both steps\"),\n        Err(error) => assert(false, \"valid port unexpectedly failed\")\n    }\n    match load_port(\"bad\") {\n        Ok(port) => assert(false, \"bad text must not become a port\"),\n        Err(error) => assert(error == \"not a supported port literal\", \"preserve parse error\")\n    }\n    print(\"fallible composition verified\")\n}\n\nmain()\n"
  },
  {
    "id": "collections01",
    "name": "collections01",
    "topic": "18_collection_transforms",
    "topicTitle": "18. Map, Filter & Fold",
    "title": "Iterating Domain Collections",
    "mode": "run",
    "description": "Iterate Array<T> values directly and aggregate fields from typed structs.",
    "hints": [
      "`for item in items` binds each array element without an index.",
      "Only add `reading.value` when `reading.valid` is true."
    ],
    "code": "// I AM NOT DONE\n// Real collections usually contain domain values, not bare integers.\n// TODO: sum only valid sensor readings.\n\nstruct Reading { value: int, valid: bool }\n\nfn valid_total(readings: Array<Reading>) -> int {\n    var total = 0\n    for reading in readings {\n        set total = total + reading.value\n    }\n    return total\n}\n\nfn main() {\n    let readings = [Reading(10, true), Reading(900, false), Reading(7, true)]\n    let total = valid_total(readings)\n    assert(total == 17, \"invalid readings must be excluded\")\n    print(\"valid total:\", total)\n}\n\nmain()\n",
    "solution": "struct Reading { value: int, valid: bool }\n\nfn valid_total(readings: Array<Reading>) -> int {\n    var total = 0\n    for reading in readings {\n        if reading.valid {\n            set total = total + reading.value\n        }\n    }\n    return total\n}\n\nfn main() {\n    let readings = [Reading(10, true), Reading(900, false), Reading(7, true)]\n    let total = valid_total(readings)\n    assert(total == 17, \"invalid readings must be excluded\")\n    print(\"valid total:\", total)\n}\n\nmain()\n"
  },
  {
    "id": "collections02",
    "name": "collections02",
    "topic": "18_collection_transforms",
    "topicTitle": "18. Map, Filter & Fold",
    "title": "Typed map, filter, and fold",
    "mode": "run",
    "description": "Build a typed collection transformation with contextual lambdas and a left-to-right fold.",
    "hints": [
      "First map each value to its double, then retain values greater than 4.",
      "Use `fold(selected, 0, (total, value) => total + value)`; the expected result is 14."
    ],
    "code": "// I AM NOT DONE\n// map transforms, filter selects, and fold reduces in left-to-right order.\n// TODO: select every doubled value greater than 4, not only values above 6.\n\nfn main() {\n    let values = [1, 2, 3, 4]\n    let doubled = map(values, value => value * 2)\n    let selected = filter(doubled, value => value > 6)\n    let total = fold(selected, 0, (sum, value) => sum + value)\n\n    assert(total == 14, \"6 + 8 must produce 14\")\n    print(\"transformed total:\", total)\n}\n\nmain()\n",
    "solution": "fn main() {\n    let values = [1, 2, 3, 4]\n    let doubled = map(values, value => value * 2)\n    let selected = filter(doubled, value => value > 4)\n    let total = fold(selected, 0, (sum, value) => sum + value)\n\n    assert(total == 14, \"6 + 8 must produce 14\")\n    print(\"transformed total:\", total)\n}\n\nmain()\n"
  },
  {
    "id": "async01",
    "name": "async01",
    "topic": "19_async_tasks",
    "topicTitle": "19. Async Task Orchestration",
    "title": "Reusable Task Handles",
    "mode": "run",
    "description": "Store one Task<T> and await the same completion more than once without rerunning its body.",
    "hints": [
      "Calling `compute()` twice creates two tasks and executes the function twice.",
      "Create `let task: Task<int> = compute()` once, then await `task` for both values."
    ],
    "code": "// I AM NOT DONE\n// A Task is a reusable handle to one completion.\n// TODO: call compute once and await the same task twice.\n\nasync fn compute(calls: Array<int>) -> int {\n    set calls[0] = calls[0] + 1\n    return 21\n}\n\nasync fn main() {\n    let calls = [0]\n    let first: int = await compute(calls)\n    let second: int = await compute(calls)\n    assert(first + second == 42, \"both awaits must observe value 21\")\n    assert(calls[0] == 1, \"the task body must run once\")\n    print(\"task total:\", first + second)\n}\n",
    "solution": "async fn compute(calls: Array<int>) -> int {\n    set calls[0] = calls[0] + 1\n    return 21\n}\n\nasync fn main() {\n    let calls = [0]\n    let task: Task<int> = compute(calls)\n    let first: int = await task\n    let second: int = await task\n    assert(first + second == 42, \"both awaits must observe value 21\")\n    assert(calls[0] == 1, \"the task body must run once\")\n    print(\"task total:\", first + second)\n}\n"
  },
  {
    "id": "async02",
    "name": "async02",
    "topic": "19_async_tasks",
    "topicTitle": "19. Async Task Orchestration",
    "title": "Errors Surface at await",
    "mode": "run",
    "description": "Catch an asynchronous failure at the await boundary where it becomes observable.",
    "hints": [
      "Creating the task does not handle its eventual error.",
      "Place `let value: int = await task` inside `try`, then inspect the error in `catch`."
    ],
    "code": "// I AM NOT DONE\n// Task failures become observable when the task is awaited.\n// TODO: catch the error raised by await and verify its message.\n\nasync fn fetch_score() -> int {\n    throw \"score service unavailable\"\n}\n\nasync fn main() {\n    let task: Task<int> = fetch_score()\n    let value: int = await task\n    print(value)\n}\n",
    "solution": "async fn fetch_score() -> int {\n    throw \"score service unavailable\"\n}\n\nasync fn main() {\n    let task: Task<int> = fetch_score()\n    try {\n        let value: int = await task\n        assert(false, \"failed task must not produce a value\")\n    } catch error {\n        assert(error == \"score service unavailable\", \"await must preserve the task error\")\n        print(\"caught:\", error)\n    }\n}\n"
  },
  {
    "id": "modules01",
    "name": "modules01",
    "topic": "20_modules_and_stdlib",
    "topicTitle": "20. Modules, Imports & Web",
    "title": "Selective Standard-Library Imports",
    "mode": "run",
    "description": "Import only the std/math symbols a module needs and combine their typed results.",
    "hints": [
      "Use `import { sin, cos } from \"std/math\"` at the top of the file.",
      "At angle 0, `sin(0.0) + cos(0.0)` is exactly `1.0`."
    ],
    "code": "// I AM NOT DONE\n// Selective imports make dependencies visible at the module boundary.\n// TODO: import sin and cos, then combine their values at angle zero.\n\nimport { sin, cos } from \"std/math\"\n\nfn main() {\n    let value = sin(0.0)\n    assert(value == 1.0, \"sin(0) + cos(0) must be 1\")\n    print(\"unit-circle identity:\", value)\n}\n\nmain()\n",
    "solution": "import { sin, cos } from \"std/math\"\n\nfn main() {\n    let value = sin(0.0) + cos(0.0)\n    assert(value == 1.0, \"sin(0) + cos(0) must be 1\")\n    print(\"unit-circle identity:\", value)\n}\n\nmain()\n"
  },
  {
    "id": "modules02",
    "name": "modules02",
    "topic": "20_modules_and_stdlib",
    "topicTitle": "20. Modules, Imports & Web",
    "title": "Fallible Base64 Decoding",
    "mode": "run",
    "description": "Use std/encoding while keeping malformed external data in an explicit Result path.",
    "hints": [
      "Encode the original text, then pass that encoded value to `base64_decode`.",
      "Check `is_ok` before calling `unwrap()`; malformed input must remain a failed Result."
    ],
    "code": "// I AM NOT DONE\n// Decoding external text can fail, so the API returns Result<string, string>.\n// TODO: decode the encoded message rather than malformed input.\n\nimport \"std/encoding\"\n\nfn main() {\n    let original = \"Rove\"\n    let encoded = base64_encode(original)\n    let decoded = base64_decode(\"%%%\")\n\n    assert(decoded.is_ok, \"the generated Base64 text must decode\")\n    assert(decoded.unwrap() == original, \"valid encoded text must round-trip\")\n    print(encoded, decoded.unwrap())\n}\n\nmain()\n",
    "solution": "import \"std/encoding\"\n\nfn main() {\n    let original = \"Rove\"\n    let encoded = base64_encode(original)\n    let decoded = base64_decode(encoded)\n    let malformed = base64_decode(\"%%%\")\n\n    assert(decoded.is_ok, \"the generated Base64 text must decode\")\n    assert(decoded.unwrap() == original, \"valid encoded text must round-trip\")\n    assert(not malformed.is_ok, \"malformed input must remain an error\")\n    print(encoded, decoded.unwrap())\n}\n\nmain()\n"
  },
  {
    "id": "modules03",
    "name": "modules03",
    "topic": "20_modules_and_stdlib",
    "topicTitle": "20. Modules, Imports & Web",
    "title": "Honest json_lite Boundaries",
    "mode": "run",
    "description": "Extract supported top-level JSON fields and handle a missing field without pretending json_lite is a full parser.",
    "hints": [
      "Read `name` with get_string and `version` with get_int, then unwrap known-good fields.",
      "The missing `channel` field must report `is_ok == false`."
    ],
    "code": "// I AM NOT DONE\n// std/json_lite intentionally extracts flat top-level string and int fields.\n// TODO: request the real `version` key and preserve the missing-field error.\n\nimport \"std/json_lite\"\n\nfn main() {\n    let document = \"{\\\"name\\\":\\\"rove\\\",\\\"version\\\":4}\"\n    let name = get_string(document, \"name\").unwrap()\n    let version = get_int(document, \"release\").unwrap()\n    let missing = get_string(document, \"channel\")\n\n    assert(name == \"rove\", \"name must be extracted\")\n    assert(version == 4, \"version must be extracted as an int\")\n    assert(not missing.is_ok, \"the absent field must remain an error\")\n    print(name, version)\n}\n\nmain()\n",
    "solution": "import \"std/json_lite\"\n\nfn main() {\n    let document = \"{\\\"name\\\":\\\"rove\\\",\\\"version\\\":4}\"\n    let name = get_string(document, \"name\").unwrap()\n    let version = get_int(document, \"version\").unwrap()\n    let missing = get_string(document, \"channel\")\n\n    assert(name == \"rove\", \"name must be extracted\")\n    assert(version == 4, \"version must be extracted as an int\")\n    assert(not missing.is_ok, \"the absent field must remain an error\")\n    print(name, version)\n}\n\nmain()\n"
  }
];
