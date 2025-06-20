import ast
import pytest

from pyward.rules.optimization_rules import (
    check_unused_imports,
    check_unreachable_code,
    check_string_concat_in_loop,
    check_len_call_in_loop,
    check_range_len_pattern,
    check_append_in_loop,
    check_unused_variables,
    run_all_optimization_checks,
)


def test_check_unused_imports_single_unused():
    source = (
        "import os\n"
        "import sys\n"
        "print(os.getcwd())\n"
    )
    tree = ast.parse(source)
    issues = check_unused_imports(tree)
    assert issues == [
        "[Optimization] Line 2: Imported name 'sys' is never used."
    ]


def test_check_unused_imports_all_used():
    source = (
        "import math\n"
        "from collections import deque\n"
        "x = math.pi\n"
        "d = deque([1, 2, 3])\n"
    )
    tree = ast.parse(source)
    issues = check_unused_imports(tree)
    assert issues == []


def test_check_unreachable_code_function_level():
    source = (
        "def foo():\n"
        "    return 1\n"
        "    x = 2\n"
        "    y = 3\n"
    )
    tree = ast.parse(source)
    issues = check_unreachable_code(tree)
    assert "[Optimization] Line 3: This code is unreachable." in issues
    assert "[Optimization] Line 4: This code is unreachable." in issues
    assert len(issues) == 2


def test_check_unreachable_code_module_level():
    source = (
        "x = 1\n"
        "raise ValueError('oops')\n"
        "y = 2\n"
    )
    tree = ast.parse(source)
    issues = check_unreachable_code(tree)
    assert issues == [
        "[Optimization] Line 3: This code is unreachable."
    ]


def test_check_string_concat_in_loop_detected():
    source = (
        "s = ''\n"
        "for i in range(3):\n"
        "    s = s + 'a'\n"
    )
    tree = ast.parse(source)
    issues = check_string_concat_in_loop(tree)
    assert any(
        "String concatenation in loop for 's'" in msg for msg in issues
    ), f"Unexpected issues: {issues}"


def test_check_string_concat_in_loop_augassign():
    source = (
        "s = ''\n"
        "while True:\n"
        "    s += 'a'\n"
        "    break\n"
    )
    tree = ast.parse(source)
    issues = check_string_concat_in_loop(tree)
    assert any(
        "Augmented assignment 's += ..." in msg for msg in issues
    ), f"Unexpected issues: {issues}"


def test_check_len_call_in_loop_detected():
    source = (
        "arr = [1, 2, 3]\n"
        "for element in arr:\n"
        "    n = len(arr)\n"
    )
    tree = ast.parse(source)
    issues = check_len_call_in_loop(tree)
    assert any(
        "Call to len() inside loop" in msg for msg in issues
    ), f"Unexpected issues: {issues}"


def test_check_len_call_in_loop_not_in_loop():
    source = (
        "arr = [1, 2, 3]\n"
        "n = len(arr)\n"
    )
    tree = ast.parse(source)
    issues = check_len_call_in_loop(tree)
    assert issues == []


def test_check_range_len_pattern_detected():
    source = (
        "a = [10, 20, 30]\n"
        "for i in range(len(a)):\n"
        "    print(a[i])\n"
    )
    tree = ast.parse(source)
    issues = check_range_len_pattern(tree)
    assert issues == [
        "[Optimization] Line 2: Loop over 'range(len(...))'. Consider using 'enumerate()' to iterate directly over the sequence."
    ]


def test_check_range_len_pattern_not_detected():
    source = (
        "a = [10, 20, 30]\n"
        "for i, val in enumerate(a):\n"
        "    print(val)\n"
    )
    tree = ast.parse(source)
    issues = check_range_len_pattern(tree)
    assert issues == []


def test_check_append_in_loop_detected():
    source = (
        "lst = []\n"
        "for i in range(3):\n"
        "    lst.append(i)\n"
    )
    tree = ast.parse(source)
    issues = check_append_in_loop(tree)
    assert issues == [
        "[Optimization] Line 3: Using list.append() inside a loop. Consider using a list comprehension for better performance."
    ]


def test_check_append_in_loop_not_in_loop():
    source = (
        "lst = []\n"
        "lst.append(1)\n"
    )
    tree = ast.parse(source)
    issues = check_append_in_loop(tree)
    assert issues == []


def test_check_unused_variables_detected():
    source = (
        "x = 1\n"
        "y = 2\n"
        "print(x)\n"
    )
    tree = ast.parse(source)
    issues = check_unused_variables(tree)
    assert issues == [
        "[Optimization] Line 2: Variable 'y' is assigned but never used."
    ]


def test_check_unused_variables_ignores_underscore():
    source = (
        "_temp = 5\n"
        "print(_temp)\n"
        "z = 10\n"
    )
    tree = ast.parse(source)
    issues = check_unused_variables(tree)
    assert issues == [
        "[Optimization] Line 3: Variable 'z' is assigned but never used."
    ]


def test_run_all_optimization_checks_combined():
    source = (
        "import os\n"
        "import sys\n"
        "x = 1\n"
        "y = 2\n"
        "def foo():\n"
        "    return 3\n"
        "    z = 4\n"
        "for i in range(len([1, 2])):\n"
        "    s = ''\n"
        "    s = s + 'a'\n"
        "    lst = []\n"
        "    lst.append(i)\n"
    )
    issues = run_all_optimization_checks(source)

    # Expect at least: unused import 'sys', unused variable 'y', unreachable 'z',
    # range(len(...)), string concat, append in loop
    expected_substrings = [
        "Imported name 'sys' is never used",
        "Variable 'y' is assigned but never used",
        "Line 7: This code is unreachable",
        "Loop over 'range(len(...))'",
        "String concatenation in loop for 's'",
        "Using list.append() inside a loop",
    ]
    for substring in expected_substrings:
        assert any(substring in msg for msg in issues), f"Missing issue containing: {substring}"


if __name__ == "__main__":
    pytest.main()
