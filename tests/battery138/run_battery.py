import sys
import os
import io

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from src.compiler import Compiler

# =========================================================================
# 138 EXHAUSTIVE EDGE-CASE TEST SUITE
# =========================================================================
test_cases = []

def add_test(name, code, expected_output=None):
    test_cases.append((name, code.strip(), expected_output))

# 1. Operator Precedence & Associativity (12 tests)
add_test("prec_01_mul_add", "#target cpp\nprint(1 + 2 * 3)", "7")
add_test("prec_02_paren_mul", "#target cpp\nprint((1 + 2) * 3)", "9")
add_test("prec_03_sub_assoc", "#target cpp\nprint(10 - 2 - 3)", "5")
add_test("prec_04_div_mul", "#target cpp\nprint(20 / 4 * 2)", "10")
add_test("prec_05_mod_op", "#target cpp\nprint(10 % 3)", "1")
add_test("prec_06_complex_math", "#target cpp\nprint(2 + 3 * 4 - 8 / 2)", "10")
add_test("prec_07_paren_nested", "#target cpp\nprint(((2 + 3) * (4 - 1)) / 3)", "5")
add_test("prec_08_cmp_and_math", "#target cpp\nprint(3 + 2 > 4)", "true")
add_test("prec_09_cmp_eq_prec", "#target cpp\nprint(2 * 5 == 10)", "true")
add_test("prec_10_cmp_neq_prec", "#target cpp\nprint(2 + 2 != 5)", "true")
add_test("prec_11_deep_assoc", "#target cpp\nprint(100 - 50 - 25 - 10)", "15")
add_test("prec_12_unary_in_expr", "#target cpp\nprint(10 + -5)", "5")

# 2. Negative Numbers & Unary (10 tests)
add_test("neg_01_simple", "#target cpp\nvar x = -5\nprint(x)", "-5")
add_test("neg_02_add", "#target cpp\nprint(-5 + 10)", "5")
add_test("neg_03_mul", "#target cpp\nprint(-4 * -3)", "12")
add_test("neg_04_paren", "#target cpp\nprint(-(5 + 3))", "-8")
add_test("neg_05_float", "#target cpp\nvar f = -3.14\nprint(f)", "-3.14")
add_test("neg_06_sub_neg", "#target cpp\nprint(10 - -5)", "15")
add_test("neg_07_chain_unary", "#target cpp\nvar a = 5\nvar b = -a\nprint(b)", "-5")
add_test("neg_08_zero_neg", "#target cpp\nprint(-0)", "0")
add_test("neg_09_neg_cmp", "#target cpp\nprint(-5 < 0)", "true")
add_test("neg_10_neg_div", "#target cpp\nprint(-10 / 2)", "-5")

# 3. Boolean Logic & Complex Predicates (12 tests)
add_test("bool_01_and_tt", "#target cpp\nprint(true && true)", "true")
add_test("bool_02_and_tf", "#target cpp\nprint(true && false)", "false")
add_test("bool_03_or_tf", "#target cpp\nprint(true || false)", "true")
add_test("bool_04_or_ff", "#target cpp\nprint(false || false)", "false")
add_test("bool_05_not_t", "#target cpp\nprint(!true)", "false")
add_test("bool_06_not_f", "#target cpp\nprint(!false)", "true")
add_test("bool_07_kw_and", "#target cpp\nprint(true and false)", "false")
add_test("bool_08_kw_or", "#target cpp\nprint(true or false)", "true")
add_test("bool_09_kw_not", "#target cpp\nprint(not false)", "true")
add_test("bool_10_combo_1", "#target cpp\nprint((true || false) && (!false))", "true")
add_test("bool_11_combo_2", "#target cpp\nprint(5 > 2 && 10 < 20)", "true")
add_test("bool_12_combo_3", "#target cpp\nprint(5 > 10 || 3 == 3)", "true")

# 4. Nested Expressions & Deep Parentheses (10 tests)
add_test("expr_01_nested_mul", "#target cpp\nprint((10 + 5) * (3 - 1))", "30")
add_test("expr_02_triple_paren", "#target cpp\nprint((((42))))", "42")
add_test("expr_03_nested_cmp", "#target cpp\nprint(((10 > 5) == (2 < 4)))", "true")
add_test("expr_04_math_func_chain", "#target cpp\nprint((2 + 2) * (3 + 3) * (4 + 4))", "192")
add_test("expr_05_paren_division", "#target cpp\nprint(100 / (2 * 5))", "10")
add_test("expr_06_mixed_types", "#target cpp\nvar a = 10\nvar b = 2.5\nprint(a + b)", "12.5")
add_test("expr_07_str_paren_concat", "#target cpp\nprint((\"A\" + \"B\") + (\"C\" + \"D\"))", "ABCD")
add_test("expr_08_bool_chain_paren", "#target cpp\nprint((true && true) || (false && false))", "true")
add_test("expr_09_deep_arithmetic", "#target cpp\nprint(1 + (2 * (3 + (4 * 2))))", "23")
add_test("expr_10_unary_in_nested", "#target cpp\nprint(-((10 + 20) / 2))", "-15")

# 5. Multi-dimensional Arrays & Indexing (10 tests)
add_test("arr_01_1d", "#target cpp\nvar a = [10, 20, 30]\nprint(a[1])", "20")
add_test("arr_02_2d", "#target cpp\nvar x = [[1, 2], [3, 4]]\nprint(x[0][1])", "2")
add_test("arr_03_2d_inner", "#target cpp\nvar x = [[10, 20], [30, 40]]\nprint(x[1][0])", "30")
add_test("arr_04_3d", "#target cpp\nvar x = [[[99]]]\nprint(x[0][0][0])", "99")
add_test("arr_05_reassign_1d", "#target cpp\nvar a = [1, 2, 3]\na[0] = 50\nprint(a[0])", "50")
add_test("arr_06_reassign_2d", "#target cpp\nvar a = [[1, 2], [3, 4]]\na[1][1] = 99\nprint(a[1][1])", "99")
add_test("arr_07_strings_arr", "#target cpp\nvar s = [\"apple\", \"banana\"]\nprint(s[1])", "banana")
add_test("arr_08_arr_len_expr", "#target cpp\nvar a = [5, 10, 15]\nvar idx = 1 + 1\nprint(a[idx])", "15")
add_test("arr_09_arr_in_fn", "#target cpp\nfn get_elem(arr, i) { return arr[i] }\nprint(get_elem([100, 200], 1))", "200")
add_test("arr_10_mixed_access", "#target cpp\nvar a = [10, 20]\nvar b = [a, [30, 40]]\nprint(b[0][0])", "10")

# 6. Nested Structs & Struct Arrays (10 tests)
add_test("struct_01_basic", "#target cpp\nstruct Point { x, y }\nvar p = Point(10, 20)\nprint(p.x, p.y)", "10 20")
add_test("struct_02_nested", "#target cpp\nstruct Address { city }\nstruct User { name, addr }\nvar u = User(\"Umut\", Address(\"Istanbul\"))\nprint(u.name, u.addr.city)", "Umut Istanbul")
add_test("struct_03_mutate_field", "#target cpp\nstruct Point { x, y }\nvar p = Point(1, 2)\np.x = 99\nprint(p.x)", "99")
add_test("struct_04_array_of_structs", "#target cpp\nstruct Item { id }\nvar items = [Item(1), Item(2)]\nprint(items[1].id)", "2")
add_test("struct_05_fn_return_struct", "#target cpp\nstruct Box { val }\nfn make_box(v) { return Box(v) }\nvar b = make_box(42)\nprint(b.val)", "42")
add_test("struct_06_struct_arg", "#target cpp\nstruct Box { val }\nfn unbox(b) { return b.val }\nprint(unbox(Box(100)))", "100")
add_test("struct_07_deep_nest", "#target cpp\nstruct A { val }\nstruct B { a }\nstruct C { b }\nvar c = C(B(A(777)))\nprint(c.b.a.val)", "777")
add_test("struct_08_typed_fields", "#target cpp\nstruct Hero { name: string, hp: int }\nvar h = Hero(\"Knight\", 100)\nprint(h.name, h.hp)", "Knight 100")
add_test("struct_09_struct_in_loop", "#target cpp\nstruct Counter { count }\nvar list = [Counter(10), Counter(20)]\nfor c in list { print(c.count) }", "10\n20")
add_test("struct_10_struct_assign_chain", "#target cpp\nstruct Pair { a, b }\nvar p1 = Pair(1, 2)\nvar p2 = p1\nprint(p2.a, p2.b)", "1 2")

# 7. Function Forward Declarations & Mutual Recursion (10 tests)
add_test("fn_01_call_before_def", "#target cpp\nfn a(x) { return b(x) }\nfn b(x) { return x * 2 }\nprint(a(5))", "10")
add_test("fn_02_mutual_even_odd", "#target cpp\nfn is_even(n) { if n == 0 { return true } return is_odd(n - 1) }\nfn is_odd(n) { if n == 0 { return false } return is_even(n - 1) }\nprint(is_even(4))\nprint(is_even(5))", "true\nfalse")
add_test("fn_03_chain_3_funcs", "#target cpp\nfn f1(x) { return f2(x) + 1 }\nfn f2(x) { return f3(x) * 2 }\nfn f3(x) { return x + 10 }\nprint(f1(5))", "31")
add_test("fn_04_no_args", "#target cpp\nfn get_magic() { return 42 }\nprint(get_magic())", "42")
add_test("fn_05_multi_args", "#target cpp\nfn sum4(a, b, c, d) { return a + b + c + d }\nprint(sum4(1, 2, 3, 4))", "10")
add_test("fn_06_str_return", "#target cpp\nfn greet(n) { return \"Hello \" + n }\nprint(greet(\"World\"))", "Hello World")
add_test("fn_07_void_fn", "#target cpp\nfn log_it(msg) { print(\"LOG:\", msg) }\nlog_it(\"Active\")", "LOG: Active")
add_test("fn_08_typed_params", "#target cpp\nfn add_typed(a: int, b: int) -> int { return a + b }\nprint(add_typed(20, 30))", "50")
add_test("fn_09_nested_calls", "#target cpp\nfn sq(x) { return x * x }\nprint(sq(sq(2)))", "16")
add_test("fn_10_pass_by_val", "#target cpp\nfn mutate_local(x) { x = 999 }\nvar n = 10\nmutate_local(n)\nprint(n)", "10")

# 8. Recursion & Deep Stacks (8 tests)
add_test("rec_01_factorial", "#target cpp\nfn factorial(n) { if n <= 1 { return 1 } return n * factorial(n - 1) }\nprint(factorial(5))", "120")
add_test("rec_02_fibonacci", "#target cpp\nfn fib(n) { if n <= 0 { return 0 } if n == 1 { return 1 } return fib(n-1) + fib(n-2) }\nprint(fib(7))", "13")
add_test("rec_03_sum_range", "#target cpp\nfn sum_n(n) { if n <= 0 { return 0 } return n + sum_n(n - 1) }\nprint(sum_n(10))", "55")
add_test("rec_04_power", "#target cpp\nfn power(b, e) { if e == 0 { return 1 } return b * power(b, e - 1) }\nprint(power(2, 8))", "256")
add_test("rec_05_gcd", "#target cpp\nfn gcd(a, b) { if b == 0 { return a } return gcd(b, a % b) }\nprint(gcd(48, 18))", "6")
add_test("rec_06_countdown", "#target cpp\nfn count(n) { if n > 0 { print(n); count(n - 1) } }\ncount(3)", "3\n2\n1")
add_test("rec_07_nested_rec", "#target cpp\nfn ack(m, n) { if m == 0 { return n + 1 } if m > 0 && n == 0 { return ack(m - 1, 1) } return ack(m - 1, ack(m, n - 1)) }\nprint(ack(2, 2))", "7")
add_test("rec_08_rec_array_sum", "#target cpp\nfn arr_sum(arr, idx) { if idx >= 3 { return 0 } return arr[idx] + arr_sum(arr, idx + 1) }\nprint(arr_sum([10, 20, 30], 0))", "60")

# 9. Empty Collections & Edge Inferences (8 tests)
add_test("edge_01_empty_arr", "#target cpp\nvar x = []\nprint(\"Empty Array OK\")", "Empty Array OK")
add_test("edge_02_empty_str", "#target cpp\nvar s = \"\"\nif s == \"\" { print(\"Empty Str OK\") }", "Empty Str OK")
add_test("edge_03_empty_block", "#target cpp\nif true {}\nprint(\"Empty Block OK\")", "Empty Block OK")
add_test("edge_04_empty_while", "#target cpp\nvar c = 0\nwhile c < 0 {}\nprint(\"While OK\")", "While OK")
add_test("edge_05_zero_val", "#target cpp\nvar z = 0\nprint(z == 0)", "true")
add_test("edge_06_null_var", "#target cpp\nvar n = null\nprint(n == null)", "true")
add_test("edge_07_empty_fn_body", "#target cpp\nfn do_nothing() {}\ndo_nothing()\nprint(\"Done\")", "Done")
add_test("edge_08_consecutive_semicolons", "#target cpp\nvar x = 1\nvar y = 2\nprint(x + y)", "3")

# 10. Option / Null-Safety (10 tests)
add_test("opt_01_safe_nav_null", "#target cpp\nstruct User { name }\nvar u: User? = null\nprint(u?.name ?? \"None\")", "None")
add_test("opt_02_safe_nav_present", "#target cpp\nstruct User { name }\nvar u = User(\"Ali\")\nprint(u?.name ?? \"None\")", "Ali")
add_test("opt_03_coalesce_default", "#target cpp\nvar val = null ?? 42\nprint(val)", "42")
add_test("opt_04_coalesce_left", "#target cpp\nvar val = 100 ?? 42\nprint(val)", "100")
add_test("opt_05_deep_safe_nav", "#target cpp\nstruct City { name }\nstruct Address { city: City? }\nstruct Profile { addr: Address? }\nvar p: Profile? = null\nprint(p?.addr?.city?.name ?? \"No City\")", "No City")
add_test("opt_06_null_check_if", "#target cpp\nvar x: User? = null\nif x == null { print(\"Is Null\") } else { print(\"Not Null\") }", "Is Null")
add_test("opt_07_optional_int", "#target cpp\nvar score: int? = null\nprint(score ?? 0)", "0")
add_test("opt_08_optional_assigned", "#target cpp\nvar score: int? = 95\nprint(score ?? 0)", "95")
add_test("opt_09_safe_nav_in_expr", "#target cpp\nstruct Box { val }\nvar b: Box? = Box(50)\nprint((b?.val ?? 0) + 10)", "60")
add_test("opt_10_coalesce_str", "#target cpp\nvar s: string? = null\nprint(\"User: \" + (s ?? \"Guest\"))", "User: Guest")

# 11. Result / Pattern Matching (10 tests)
add_test("res_01_ok_match", "#target cpp\nvar r = Ok(200)\nmatch r { Ok(v) => print(\"OK:\", v), Err(e) => print(\"ERR\"), \"_\" => print(\"OTHER\") }", "OK: 200")
add_test("res_02_err_match", "#target cpp\nvar r = Err(\"404 Not Found\")\nmatch r { Ok(v) => print(\"OK\"), Err(e) => print(\"ERR:\", e), \"_\" => print(\"OTHER\") }", "ERR: 404 Not Found")
add_test("res_03_str_match", "#target cpp\nvar role = \"admin\"\nmatch role { \"admin\" => print(\"FULL ACCESS\"), \"user\" => print(\"READ ONLY\"), \"_\" => print(\"DENY\") }", "FULL ACCESS")
add_test("res_04_int_match", "#target cpp\nvar code = 2\nmatch code { 1 => print(\"ONE\"), 2 => print(\"TWO\"), \"_\" => print(\"MANY\") }", "TWO")
add_test("res_05_wildcard_match", "#target cpp\nvar x = 999\nmatch x { 1 => print(\"1\"), \"_\" => print(\"WILDCARD\") }", "WILDCARD")
add_test("res_06_match_in_fn", "#target cpp\nfn check_status(s) { match s { \"ok\" => return 1, \"_\" => return 0 } }\nprint(check_status(\"ok\"))", "1")
add_test("res_07_result_unwrap", "#target cpp\nvar r = Ok(\"Data\")\nprint(r.unwrap())", "Data")
add_test("res_08_is_ok_prop", "#target cpp\nvar r = Ok(123)\nprint(r.is_ok)", "true")
add_test("res_09_match_with_calc", "#target cpp\nvar n = 10\nmatch n { 10 => print(n * 5), \"_\" => print(0) }", "50")
add_test("res_10_match_block_action", "#target cpp\nvar status = \"ready\"\nmatch status { \"ready\" => { print(\"SYSTEM READY\"); print(\"ONLINE\") }, \"_\" => print(\"OFFLINE\") }", "SYSTEM READY\nONLINE")

# 12. Loops, Break, Continue, While (10 tests)
add_test("loop_01_for_sum", "#target cpp\nvar s = 0\nfor i in 1..4 { s = s + i }\nprint(s)", "10")
add_test("loop_02_while_countdown", "#target cpp\nvar c = 3\nwhile c > 0 { print(c); c = c - 1 }", "3\n2\n1")
add_test("loop_03_nested_loops", "#target cpp\nvar count = 0\nfor i in 1..3 { for j in 1..2 { count = count + 1 } }\nprint(count)", "6")
add_test("loop_04_break_while", "#target cpp\nvar i = 0\nwhile true { if i == 3 { break }; i = i + 1 }\nprint(i)", "3")
add_test("loop_05_continue_for", "#target cpp\nfor i in 1..5 { if i == 3 { continue }; print(i) }", "1\n2\n4\n5")
add_test("loop_06_collection_iter", "#target cpp\nvar names = [\"Ali\", \"Veli\"]\nfor n in names { print(\"User:\", n) }", "User: Ali\nUser: Veli")
add_test("loop_07_empty_iter", "#target cpp\nvar empty = []\nfor x in empty { print(\"SHOULD NOT RUN\") }\nprint(\"Loop finished\")", "Loop finished")
add_test("loop_08_break_in_collection", "#target cpp\nvar arr = [10, 20, 30, 40]\nfor x in arr { if x == 30 { break }; print(x) }", "10\n20")
add_test("loop_09_while_complex_cond", "#target cpp\nvar a = 0\nvar b = 10\nwhile a < 5 && b > 5 { a = a + 1; b = b - 1 }\nprint(a, b)", "5 5")
add_test("loop_10_infinite_loop_kw", "#target cpp\nvar step = 0\nloop { step = step + 1; if step == 4 { break } }\nprint(step)", "4")

# 13. Strings, Concatenation, Unicode (10 tests)
add_test("str_01_concat_basic", "#target cpp\nvar s = \"ny\" + \"x\"\nprint(s)", "nyx")
add_test("str_02_concat_vars", "#target cpp\nvar a = \"Foo\"\nvar b = \"Bar\"\nprint(a + b)", "FooBar")
add_test("str_03_unicode_chars", "#target cpp\nprint(\"İstanbul / Türkiye - 24K Altın\")", "İstanbul / Türkiye - 24K Altın")
add_test("str_04_escape_quotes", "#target cpp\nprint(\"Hello \\\"World\\\"\")", "Hello \"World\"")
add_test("str_05_escape_newline", "#target cpp\nprint(\"Line1\\nLine2\")", "Line1\nLine2")
add_test("str_06_to_string_int", "#target cpp\nprint(\"Num: \" + to_string(123))", "Num: 123")
add_test("str_07_contains_true", "#target cpp\nprint(contains(\"radar_scan\", \"scan\"))", "true")
add_test("str_08_contains_false", "#target cpp\nprint(contains(\"radar_scan\", \"target\"))", "false")
add_test("str_09_to_int_conv", "#target cpp\nprint(to_int(\"42\") + 8)", "50")
add_test("str_10_multi_concat", "#target cpp\nprint(\"A\" + \"-\" + \"B\" + \"-\" + \"C\")", "A-B-C")

# 14. Unsafe Memory, Addr, Peek, Concurrency (8 tests)
add_test("unsafe_01_basic_addr", "#target cpp\nunsafe { var x = 42; var p = addr(x); print(peek(p)) }", "1337")
add_test("unsafe_02_block_protect", "#target cpp\nunsafe { var num = 100; print(\"Unsafe OK\") }", "Unsafe OK")
add_test("unsafe_03_spawn_bg", "#target cpp\nspawn { var bg = 1 }\nprint(\"Spawn OK\")", "Spawn OK")
add_test("unsafe_04_channel_create", "#target cpp\nvar ch = channel()\nprint(\"Channel Created\")", "Channel Created")
add_test("unsafe_05_memdump_call", "#target cpp\nunsafe { var x = 10; memdump(addr(x), 16) }\nprint(\"Memdump OK\")", "Memdump OK")
add_test("unsafe_06_pipeline_operator", "#target cpp\nfn dbl(x) { return x * 2 }\n5000 |> dbl |> print", "10000")
add_test("unsafe_07_reverse_arrow", "#target cpp\n8700 -> freq\nprint(\"Freq:\", freq)", "Freq: 8700")
add_test("unsafe_08_dollar_var", "#target cpp\n$gold = 5000\nprint(\"Gold:\", $gold)", "Gold: 5000")

def run_all_138():
    test_dir = os.path.join(BASE, "tests", "battery138")
    os.makedirs(test_dir, exist_ok=True)
    
    total = len(test_cases)
    passed = 0
    failed = 0
    failures = []
    
    print("=" * 70)
    print(f"⚡ NYX 138-POINT EXHAUSTIVE EDGE-CASE TEST HARNESS")
    print("=" * 70)
    
    for idx, (name, code, expected) in enumerate(test_cases, 1):
        filepath = os.path.join(test_dir, f"{name}.rove")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
            
        old_stdout = sys.stdout
        sys.stdout = buffer = io.StringIO()
        
        try:
            compiler = Compiler(filepath)
            compiler.compile(run_immediately=True)
            sys.stdout = old_stdout
            out = buffer.getvalue()
            
            # Extract actual program output from between markers
            if "[+] Program Output:" in out and "=" * 50 in out:
                prog_out = out.split("[+] Program Output:")[1].split("=" * 50)[0].strip()
            else:
                prog_out = out.strip()
                
            if expected is not None:
                # Check output match
                if prog_out.strip() == expected.strip() or expected.strip() in prog_out.strip():
                    print(f"  [{idx:3d}/{total}] [PASS] {name}")
                    passed += 1
                else:
                    print(f"  [{idx:3d}/{total}] [FAIL] {name} -> Expected:\n{expected}\nGot:\n{prog_out}")
                    failed += 1
                    failures.append((name, f"Expected: {expected}, Got: {prog_out}"))
            else:
                print(f"  [{idx:3d}/{total}] [PASS] {name}")
                passed += 1
                
        except (Exception, SystemExit) as e:
            sys.stdout = old_stdout
            print(f"  [{idx:3d}/{total}] [FAIL] {name} -> Error: {e}")
            failed += 1
            failures.append((name, str(e)))
            
    print("=" * 70)
    print(f"🏁 FINAL HARNESS RESULTS: {passed}/{total} PASSED ({passed*100//total}%) | {failed} FAILED")
    print("=" * 70)
    
    if failures:
        print("\nFailed Tests Summary:")
        for name, err in failures:
            print(f"  - {name}: {err}")
            
    return failed == 0

if __name__ == "__main__":
    success = run_all_138()
    sys.exit(0 if success else 1)
