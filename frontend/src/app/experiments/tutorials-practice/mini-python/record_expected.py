"""Record CPython's behaviour for the mini-python test table.

Run (from anywhere):
    D:/FInalAdaptiveTrainer/.venv/Scripts/python.exe record_expected.py

For every snippet below this runs the code under `sys.settrace` and records
  * the final stdout,
  * the sequence of executed line numbers ('line' events of the snippet's own frames,
    module level AND inside functions),
  * how it ended: ok / error (exception class and message) / limit.
and writes `expected.generated.ts`, which `cpython-table.test.ts` compares the TypeScript
interpreter against. The snippet table lives ONLY here; the TS side reads it from the generated file.

Two limits are enforced here exactly as the interpreter enforces them, because CPython would
otherwise run for a long time or 1000 frames deep:
  * MAX_STEPS line events (300): on the 301st event the run is recorded as status "limit";
  * MAX_DEPTH nested function frames (20): entering the 21st raises RecursionError from the tracer.
So for those snippets the comparison is "identical up to the cap", not "identical to a real run".
"""

import contextlib
import io
import json
import sys
import textwrap
from pathlib import Path

MAX_STEPS = 300
MAX_DEPTH = 20
FILENAME = "<snippet>"


class StepLimit(BaseException):
    pass


def record(code: str) -> dict:
    lines: list[int] = []
    depth = 0
    out = io.StringIO()

    def local_trace(frame, event, arg):
        nonlocal depth
        if event == "line":
            if len(lines) >= MAX_STEPS:
                raise StepLimit()
            lines.append(frame.f_lineno)
        elif event == "return":
            depth -= 1
        return local_trace

    def global_trace(frame, event, arg):
        nonlocal depth
        if frame.f_code.co_filename != FILENAME:
            return None
        if event == "call":
            if frame.f_code.co_name != "<module>":
                depth += 1
                if depth > MAX_DEPTH:
                    raise RecursionError("maximum recursion depth exceeded")
            return local_trace
        return None

    compiled = compile(code, FILENAME, "exec")
    status, error = "ok", None
    sys.settrace(global_trace)
    try:
        with contextlib.redirect_stdout(out):
            exec(compiled, {"__name__": "__main__"})
    except StepLimit:
        status = "limit"
    except Exception as exc:  # noqa: BLE001 - we want every class the snippet can raise
        status = "error"
        error = {"name": type(exc).__name__, "message": str(exc)}
    finally:
        sys.settrace(None)
    return {"stdout": out.getvalue(), "lines": lines, "status": status, "error": error}


CASES: list[tuple[str, str, str]] = []


def case(cid: str, topic: str, code: str) -> None:
    CASES.append((cid, topic, textwrap.dedent(code).strip("\n") + "\n"))


# ---- conditionals ---------------------------------------------------------------------------
case("cond_shadowed_elif", "conditionals", """
    score = 85
    if score >= 60:
        print("pass")
    elif score >= 80:
        print("good")
    else:
        print("fail")
""")
case("cond_parsons_order", "conditionals", """
    temp = 20
    if temp > 25:
        print("hot")
    elif temp > 15:
        print("warm")
    else:
        print("cold")
""")
case("cond_else_branch", "conditionals", """
    n = 0
    if n > 5:
        print("big")
    elif n > 1:
        print("mid")
    else:
        print("small")
    print("done")
""")
case("cond_nested_boolean", "conditionals", """
    a = 4
    b = 0
    if a > 2 and not b:
        if a % 2 == 0 or b:
            print("even and small b")
        else:
            print("odd")
    print("end")
""")
case("cond_no_match_fallthrough", "conditionals", """
    x = 1
    if x > 5:
        print("no")
    print("after")
""")
case("cond_chained_compare_in_is", "conditionals", """
    x = 3
    y = None
    print(1 < x < 5, x in [1, 2, 3], x not in [1, 2], y is None, y is not None, x == 3.0)
    if 1 < x < 5:
        print("between")
""")

# ---- while loops ----------------------------------------------------------------------------
case("while_condition_never_changes", "while", """
    count = 0
    while count < 3:
        print(count)
""")
case("while_off_by_one", "while", """
    n = 1
    while n < 4:
        print(n)
        n = n + 1
""")
case("while_true_break", "while", """
    n = 0
    while True:
        n += 1
        if n == 3:
            break
    print(n)
""")
case("while_continue_and_counter", "while", """
    i = 0
    total = 0
    while i < 6:
        i += 1
        if i % 2 == 0:
            continue
        total += i
    print(total)
""")
case("while_countdown_augmented", "while", """
    n = 3
    while n > 0:
        print(n)
        n -= 1
    print("liftoff")
""")
case("while_never_entered", "while", """
    n = 5
    while n < 0:
        print(n)
    print("skipped")
""")
case("while_nested_loops", "while", """
    i = 0
    while i < 2:
        j = 0
        while j < 2:
            print(i, j)
            j += 1
        i += 1
""")

# ---- for loops over lists and ranges (used inside every topic) -------------------------------
case("for_range_sum", "loops", """
    total = 0
    for i in range(4):
        total = total + i
    print(total)
""")
case("for_range_start_stop_step", "loops", """
    for i in range(2, 10, 3):
        print(i)
    for j in range(3, 0, -1):
        print(j)
""")
case("for_list_break_continue", "loops", """
    for x in [1, 2, 3, 4, 5]:
        if x == 2:
            continue
        if x == 4:
            break
        print(x)
""")
case("for_over_string_and_empty", "loops", """
    for ch in "hey":
        print(ch)
    for z in []:
        print(z)
    print("end")
""")
case("for_range_zero_iterations", "loops", """
    for i in range(0):
        print(i)
    print("none")
""")

# ---- functions ------------------------------------------------------------------------------
case("fn_print_vs_return", "functions", """
    def add(a, b):
        print(a + b)
    result = add(2, 3)
    print(result)
""")
case("fn_missing_return_is_none", "functions", """
    def double(n):
        n * 2
    print(double(4))
""")
case("fn_parsons_order", "functions", """
    def times_three(n):
        return n * 3
    result = times_three(4)
    print(result)
""")
case("fn_return_paths", "functions", """
    def sign(n):
        if n > 0:
            return "positive"
        elif n < 0:
            return "negative"
        return "zero"
    print(sign(5), sign(-2), sign(0))
""")
case("fn_reads_global_and_local", "functions", """
    rate = 3
    def scale(x):
        y = x * rate
        return y
    print(scale(4))
    print(rate)
""")
case("fn_calls_fn_and_return_early", "functions", """
    def first_even(items):
        for x in items:
            if x % 2 == 0:
                return x
        return None
    def show(items):
        print(first_even(items))
    show([1, 3, 4, 6])
    show([1, 3])
""")
case("fn_argument_is_alias", "functions", """
    def add_one(items):
        items.append(1)
    a = []
    add_one(a)
    add_one(a)
    print(a)
""")

# ---- lists ----------------------------------------------------------------------------------
case("list_negative_index", "lists", """
    a = [10, 20, 30, 40]
    print(a[-1], a[1])
""")
case("list_alias_append", "lists", """
    a = [1, 2, 3]
    b = a
    b.append(4)
    print(a)
""")
case("list_copy_is_separate", "lists", """
    a = [1, 2, 3]
    b = a.copy()
    c = list(a)
    b.append(4)
    print(a, b, c, a == c, a is c)
""")
case("list_index_assignment", "lists", """
    a = [5, 6, 7]
    a[0] = 9
    a[-1] = a[0] + 1
    print(a)
""")
case("list_pop_insert_extend", "lists", """
    a = [1, 2, 3]
    last = a.pop()
    first = a.pop(0)
    a.insert(1, 8)
    a.extend([4, 5])
    print(last, first, a, len(a))
""")
case("list_aug_add_is_in_place", "lists", """
    a = [1]
    b = a
    a += [2]
    c = a
    a = a + [3]
    print(a, b, c)
""")
case("list_repr_of_mixed_values", "lists", """
    print([1, "a", None, 2.5, True, [1, [2]]])
    print([])
""")
case("list_concat_repeat_nested", "lists", """
    a = [1, 2] + [3]
    b = [0] * 3
    grid = [[1, 2], [3, 4]]
    grid[1][0] = 9
    print(a, b, grid, grid[1][0], len(grid))
""")
case("list_sum_min_max_loop", "lists", """
    nums = [4, 9, 2]
    print(sum(nums), min(nums), max(nums), abs(-3))
    i = 0
    while i < len(nums):
        print(nums[i])
        i += 1
""")

# ---- recursion ------------------------------------------------------------------------------
case("rec_countdown_base_case", "recursion", """
    def countdown(n):
        if n == 0:
            print("go")
            return
        print(n)
        countdown(n - 1)
    countdown(2)
""")
case("rec_print_after_call", "recursion", """
    def show(n):
        if n == 0:
            return
        show(n - 1)
        print(n)
    show(3)
""")
case("rec_factorial", "recursion", """
    def fact(n):
        if n <= 1:
            return 1
        return n * fact(n - 1)
    print(fact(5))
    print(fact(15))
""")
case("rec_fibonacci_two_calls", "recursion", """
    def fib(n):
        if n < 2:
            return n
        return fib(n - 1) + fib(n - 2)
    print(fib(6))
""")
case("rec_no_base_case", "recursion", """
    def down(n):
        return down(n - 1)
    print(down(3))
""")
case("rec_sum_list", "recursion", """
    def total(items, i):
        if i == len(items):
            return 0
        return items[i] + total(items, i + 1)
    print(total([1, 2, 3, 4], 0))
""")

# ---- numbers, strings, operators ------------------------------------------------------------
case("num_int_float_ops", "operators", """
    print(7 / 2, 7 // 2, -7 // 2, 7 % 3, -7 % 3, 2 ** 10, 2 ** -1, 1.5 + 1, 10 / 5)
    print(0.1 + 0.2, 1 / 3, 2.0, -0.5 * 4, 7.5 // 2, -7.5 % 2)
""")
case("num_float_repr_extremes", "operators", """
    print(1e16, 1.5e-7, 123456789.0, 1e22, 0.0001, 0.00001, 2 ** 70)
""")
case("num_bool_arithmetic", "operators", """
    print(True + 1, 3 == 3.0, 1 < 2 < 3, True == 1, 2 > 3 or 7, str(True))
""")
case("op_and_or_return_operands", "operators", """
    print(0 or 5, 3 and 4, not 0, "" or "x", [] or [1], None and 1, 5 and 0)
""")
case("op_strings", "operators", """
    print("ab" * 3, "a" + "b", len("hello"), "b" in "abc", "abc"[1], "abc"[-1], "a" < "b")
    print(str(12) + "!", int("42") + 1, int(3.9), float(2), "x" == "x")
""")
case("op_print_forms", "operators", """
    print()
    print("a", 1, None, True, 2.0)
    print("done")
""")
case("op_unary_and_precedence", "operators", """
    print(-2 ** 2, (1 + 2) * 3, 2 + 3 * 4, -(3 - 5), 10 - 2 - 3, 2 ** 3 ** 2, not 1 == 2)
""")

# ---- errors, one per class the interpreter must name -------------------------------------------
case("err_name_error", "errors", """
    x = 1
    print(x)
    print(y)
""")
case("err_index_error_read", "errors", """
    a = [1, 2, 3]
    print(a[0])
    print(a[3])
""")
case("err_index_error_negative", "errors", """
    a = [1, 2, 3]
    print(a[-4])
""")
case("err_index_error_assign", "errors", """
    a = [1, 2, 3]
    a[3] = 4
""")
case("err_index_error_string", "errors", """
    s = "abc"
    print(s[3])
""")
case("err_index_error_pop_empty", "errors", """
    a = []
    a.pop()
""")
case("err_zero_division_true_div", "errors", """
    print(1)
    print(5 / 0)
""")
case("err_zero_division_floor_div", "errors", """
    print(5 // 0)
""")
case("err_zero_division_mod", "errors", """
    print(5 % 0)
""")
case("err_zero_division_in_loop", "errors", """
    n = 2
    while True:
        print(10 // n)
        n -= 1
""")
case("err_type_str_plus_int", "errors", """
    age = 5
    print("age: " + age)
""")
case("err_type_int_plus_str", "errors", """
    print(1 + "a")
""")
case("err_type_none_from_function", "errors", """
    def double(n):
        n * 2
    print(double(4) + 1)
""")
case("err_type_less_than_mixed", "errors", """
    print(3 < "a")
""")
case("err_type_not_subscriptable", "errors", """
    n = 5
    print(n[0])
""")
case("err_type_len_of_int", "errors", """
    print(len(5))
""")
case("err_type_missing_argument", "errors", """
    def add(a, b):
        return a + b
    print(add(1))
""")
case("err_type_too_many_arguments", "errors", """
    def one(a):
        return a
    print(one(1, 2))
""")
case("err_type_not_callable", "errors", """
    n = 5
    n()
""")
case("err_type_list_index_str", "errors", """
    a = [1, 2]
    print(a["0"])
""")
case("err_type_str_item_assign", "errors", """
    s = "abc"
    s[0] = "x"
""")
case("err_type_mult_str_by_float", "errors", """
    print("ab" * 1.5)
""")
case("err_type_neg_string", "errors", """
    print(-"a")
""")
case("err_unbound_local", "errors", """
    count = 0
    def bump():
        count = count + 1
        return count
    print(bump())
""")
case("err_attribute_none_append", "errors", """
    def make():
        items = []
        items.append(1)
    a = make()
    a.append(2)
""")
case("err_value_int_of_text", "errors", """
    print(int("abc"))
""")
case("err_recursion_depth_cap", "errors", """
    def down(n):
        print(n)
        return down(n + 1)
    down(0)
""")
case("err_name_error_before_def", "errors", """
    result = times_three(4)
    def times_three(n):
        return n * 3
""")

case("err_zero_division_float_div", "errors", """
    print(5.0 / 0)
""")
case("err_zero_division_float_floor", "errors", """
    print(5.0 // 0)
""")
case("err_zero_division_float_mod", "errors", """
    print(5 % 0.0)
""")
case("err_value_min_of_empty", "errors", """
    print(min([]))
""")
case("err_type_iterate_int", "errors", """
    for i in 5:
        print(i)
""")
case("err_type_range_of_float", "errors", """
    for i in range(2.5):
        print(i)
""")
case("err_value_range_step_zero", "errors", """
    print(len(range(0, 5, 0)))
""")
case("err_index_error_pop_index", "errors", """
    a = [1]
    a.pop(3)
""")
case("err_name_error_in_function", "errors", """
    def f():
        return missing + 1
    print(f())
""")
case("err_name_error_loop_variable_scope", "errors", """
    def f(n):
        for i in range(n):
            total = i
        return total
    print(f(2))
    print(f(0))
""")

# ---- extra behaviour the practice bank relies on ---------------------------------------------
case("for_list_grows_while_looping", "loops", """
    a = [1, 2]
    for x in a:
        if len(a) < 5:
            a.append(x + 10)
    print(a)
""")
case("fn_call_order_in_print", "functions", """
    def say(n):
        print("say", n)
        return n
    print(say(1) + say(2), say(3))
""")
case("fn_return_without_value_and_in_while", "functions", """
    def find(items, target):
        i = 0
        while i < len(items):
            if items[i] == target:
                return i
            i += 1
        return
    print(find([5, 6, 7], 7), find([1], 9))
""")
case("cond_elif_without_else_all_false", "conditionals", """
    v = -1
    if v > 0:
        print("pos")
    elif v == 0:
        print("zero")
    print("end")
""")
case("list_identity_and_equality", "lists", """
    a = [1, 2]
    b = a
    c = [1, 2]
    print(a is b, a is c, a == c, a != c)
    b[0] = 7
    print(a, c)
""")
case("rec_list_building", "recursion", """
    def build(n):
        if n == 0:
            return []
        rest = build(n - 1)
        rest.append(n)
        return rest
    print(build(4))
""")
case("rec_mutual_depth_ok", "recursion", """
    def depth(n):
        if n == 0:
            return 0
        return 1 + depth(n - 1)
    print(depth(19))
""")

# ---- the 300-step cap ------------------------------------------------------------------------
case("limit_while_true_pass", "limits", """
    while True:
        pass
""")
case("limit_for_inside_while", "limits", """
    n = 0
    while n < 3:
        for i in range(2):
            print(i)
""")


def main() -> None:
    results = []
    for cid, topic, code in CASES:
        results.append({"id": cid, "topic": topic, "code": code, **record(code)})
    here = Path(__file__).parent
    header = (
        "// biome-ignore-all lint: generated file\n"
        "// biome-ignore-all format: generated file\n"
        "// GENERATED by record_expected.py from CPython "
        f"{sys.version.split()[0]} - do not edit by hand.\n"
        "// Each case: the snippet, CPython's stdout, the executed line numbers (every 'line' event of\n"
        "// the snippet's own frames, module level and inside functions) and how the run ended.\n"
        f"// Caps applied while recording: {MAX_STEPS} line events, {MAX_DEPTH} nested function frames.\n\n"
        "export interface ExpectedCase {\n"
        "  id: string;\n"
        "  topic: string;\n"
        "  code: string;\n"
        "  stdout: string;\n"
        "  lines: number[];\n"
        '  status: "ok" | "error" | "limit";\n'
        "  error: { name: string; message: string } | null;\n"
        "}\n\n"
        f"export const CPYTHON_VERSION = {json.dumps(sys.version.split()[0])};\n\n"
    )
    body = "export const EXPECTED: ExpectedCase[] = " + json.dumps(results, indent=2) + ";\n"
    (here / "expected.generated.ts").write_text(header + body, encoding="utf-8", newline="\n")
    print(f"wrote {len(results)} cases")
    for r in results:
        tail = r["error"]["name"] if r["error"] else r["status"]
        print(f"{r['id']:38s} {tail:20s} lines={len(r['lines'])}")


if __name__ == "__main__":
    main()
