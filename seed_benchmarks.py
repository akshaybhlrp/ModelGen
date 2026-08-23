#!/usr/bin/env python3
import json
import sqlite3
from pathlib import Path
from kernel import init_db, store

SEEDS_50 = [
    # 1. Algorithms
    ("sort_list", """def sort_list(lst: list) -> list:
    return sorted(lst)""",
     "def test():\n    assert sort_list([3, 1, 2]) == [1, 2, 3]\n    assert sort_list([]) == []\n    assert sort_list([5]) == [5]\n",
     "list", "list"),

    ("binary_search", """def binary_search(arr: list, target: int) -> int:
    l, r = 0, len(arr) - 1
    while l <= r:
        mid = (l + r) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            l = mid + 1
        else:
            r = mid - 1
    return -1""",
     "def test():\n    assert binary_search([1, 2, 3, 4, 5], 3) == 2\n    assert binary_search([1, 2, 4], 3) == -1\n    assert binary_search([], 1) == -1\n",
     "list, int", "int"),

    ("fibonacci", """def fibonacci(n: int) -> int:
    if n <= 0:
        return 0
    elif n == 1:
        return 1
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b""",
     "def test():\n    assert fibonacci(0) == 0\n    assert fibonacci(1) == 1\n    assert fibonacci(7) == 13\n",
     "int", "int"),

    ("factorial", """def factorial(n: int) -> int:
    if n <= 1:
        return 1
    res = 1
    for i in range(2, n + 1):
        res *= i
    return res""",
     "def test():\n    assert factorial(0) == 1\n    assert factorial(1) == 1\n    assert factorial(5) == 120\n",
     "int", "int"),

    ("gcd", """def gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a""",
     "def test():\n    assert gcd(48, 18) == 6\n    assert gcd(10, 5) == 5\n    assert gcd(7, 3) == 1\n",
     "int, int", "int"),

    ("is_prime", """def is_prime(n: int) -> bool:
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True""",
     "def test():\n    assert is_prime(2) == True\n    assert is_prime(11) == True\n    assert is_prime(4) == False\n    assert is_prime(1) == False\n",
     "int", "bool"),

    ("merge_sorted", """def merge_sorted(a: list, b: list) -> list:
    res = []
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] <= b[j]:
            res.append(a[i])
            i += 1
        else:
            res.append(b[j])
            j += 1
    res.extend(a[i:])
    res.extend(b[j:])
    return res""",
     "def test():\n    assert merge_sorted([1, 3, 5], [2, 4, 6]) == [1, 2, 3, 4, 5, 6]\n    assert merge_sorted([], [1]) == [1]\n",
     "list, list", "list"),

    ("max_subarray_sum", """def max_subarray_sum(nums: list) -> int:
    if not nums:
        return 0
    max_so_far = current_max = nums[0]
    for x in nums[1:]:
        current_max = max(x, current_max + x)
        max_so_far = max(max_so_far, current_max)
    return max_so_far""",
     "def test():\n    assert max_subarray_sum([-2, 1, -3, 4, -1, 2, 1, -5, 4]) == 6\n    assert max_subarray_sum([1, 2, 3]) == 6\n",
     "list", "int"),

    ("power", """def power(x: int, y: int) -> int:
    return x ** y""",
     "def test():\n    assert power(2, 3) == 8\n    assert power(5, 0) == 1\n",
     "int, int", "int"),

    ("lcm", """def lcm(a: int, b: int) -> int:
    def _gcd(x, y):
        while y:
            x, y = y, x % y
        return x
    return (a * b) // _gcd(a, b) if a and b else 0""",
     "def test():\n    assert lcm(4, 6) == 12\n    assert lcm(5, 7) == 35\n",
     "int, int", "int"),

    # 2. Strings
    ("reverse_str", """def reverse_str(s: str) -> str:
    return s[::-1]""",
     "def test():\n    assert reverse_str('hello') == 'olleh'\n    assert reverse_str('') == ''\n",
     "str", "str"),

    ("is_palindrome", """def is_palindrome(s: str) -> bool:
    return s == s[::-1]""",
     "def test():\n    assert is_palindrome('radar') == True\n    assert is_palindrome('hello') == False\n    assert is_palindrome('') == True\n",
     "str", "bool"),

    ("count_vowels", """def count_vowels(s: str) -> int:
    return sum(1 for c in s.lower() if c in 'aeiou')""",
     "def test():\n    assert count_vowels('apple') == 2\n    assert count_vowels('xyz') == 0\n",
     "str", "int"),

    ("to_title_case", """def to_title_case(s: str) -> str:
    return s.title()""",
     "def test():\n    assert to_title_case('hello world') == 'Hello World'\n",
     "str", "str"),

    ("remove_whitespace", """def remove_whitespace(s: str) -> str:
    return ''.join(s.split())""",
     "def test():\n    assert remove_whitespace(' a b c ') == 'abc'\n",
     "str", "str"),

    ("is_anagram", """def is_anagram(s1: str, s2: str) -> bool:
    return sorted(s1) == sorted(s2)""",
     "def test():\n    assert is_anagram('listen', 'silent') == True\n    assert is_anagram('hello', 'world') == False\n",
     "str, str", "bool"),

    ("rle_encode", """def rle_encode(s: str) -> str:
    if not s:
        return ''
    res = []
    count = 1
    for i in range(1, len(s)):
        if s[i] == s[i-1]:
            count += 1
        else:
            res.append(f'{s[i-1]}{count}')
            count = 1
    res.append(f'{s[-1]}{count}')
    return ''.join(res)""",
     "def test():\n    assert rle_encode('aabcccccaaa') == 'a2b1c5a3'\n",
     "str", "str"),

    ("truncate_str", """def truncate_str(s: str, max_len: int) -> str:
    if len(s) > max_len:
        return s[:max_len] + '...'
    return s""",
     "def test():\n    assert truncate_str('hello world', 5) == 'hello...'\n    assert truncate_str('hi', 5) == 'hi'\n",
     "str, int", "str"),

    ("first_unique_char", """def first_unique_char(s: str):
    from collections import Counter
    counts = Counter(s)
    for c in s:
        if counts[c] == 1:
            return c
    return None""",
     "def test():\n    assert first_unique_char('swiss') == 'w'\n    assert first_unique_char('aabb') is None\n",
     "str", "Optional[str]"),

    ("camel_to_snake", """def camel_to_snake(s: str) -> str:
    import re
    return re.sub(r'(?<!^)(?=[A-Z])', '_', s).lower()""",
     "def test():\n    assert camel_to_snake('camelCaseTest') == 'camel_case_test'\n",
     "str", "str"),

    # 3. Data Structures & Lists
    ("remove_duplicates", """def remove_duplicates(lst: list) -> list:
    seen = set()
    res = []
    for x in lst:
        if x not in seen:
            seen.add(x)
            res.append(x)
    return res""",
     "def test():\n    assert remove_duplicates([1, 2, 2, 3, 1]) == [1, 2, 3]\n    assert remove_duplicates([]) == []\n",
     "list", "list"),

    ("flatten_list", """def flatten_list(nested: list) -> list:
    res = []
    def _flat(items):
        for item in items:
            if isinstance(item, list):
                _flat(item)
            else:
                res.append(item)
    _flat(nested)
    return res""",
     "def test():\n    assert flatten_list([[1, 2], [3, [4, 5]]]) == [1, 2, 3, 4, 5]\n",
     "list", "list"),

    ("chunk_list", """def chunk_list(lst: list, n: int) -> list:
    if n <= 0:
        return [lst]
    return [lst[i:i + n] for i in range(0, len(lst), n)]""",
     "def test():\n    assert chunk_list([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]\n",
     "list, int", "list"),

    ("rotate_list", """def rotate_list(lst: list, k: int) -> list:
    if not lst:
        return []
    k = k % len(lst)
    return lst[-k:] + lst[:-k]""",
     "def test():\n    assert rotate_list([1, 2, 3, 4, 5], 2) == [4, 5, 1, 2, 3]\n",
     "list, int", "list"),

    ("list_intersection", """def list_intersection(a: list, b: list) -> list:
    return list(set(a) & set(b))""",
     "def test():\n    assert sorted(list_intersection([1, 2, 3], [2, 3, 4])) == [2, 3]\n",
     "list, list", "list"),

    ("invert_dict", """def invert_dict(d: dict) -> dict:
    return {v: k for k, v in d.items()}""",
     "def test():\n    assert invert_dict({'a': 1, 'b': 2}) == {1: 'a', 2: 'b'}\n",
     "dict", "dict"),

    ("merge_dicts_lists", """def merge_dicts_lists(d1: dict, d2: dict) -> dict:
    res = {}
    for k in set(d1.keys()) | set(d2.keys()):
        vals = []
        if k in d1:
            vals.append(d1[k])
        if k in d2:
            vals.append(d2[k])
        res[k] = vals
    return res""",
     "def test():\n    assert merge_dicts_lists({'a': 1}, {'a': 2, 'b': 3}) == {'a': [1, 2], 'b': [3]}\n",
     "dict, dict", "dict"),

    ("second_largest", """def second_largest(lst: list):
    unique = list(set(lst))
    if len(unique) < 2:
        return None
    unique.sort()
    return unique[-2]""",
     "def test():\n    assert second_largest([10, 20, 4, 45, 99]) == 45\n    assert second_largest([5, 5]) is None\n",
     "list", "Optional[int]"),

    ("partition", """def partition(lst: list, predicate) -> tuple:
    true_items = [x for x in lst if predicate(x)]
    false_items = [x for x in lst if not predicate(x)]
    return true_items, false_items""",
     "def test():\n    evens, odds = partition([1, 2, 3, 4], lambda x: x % 2 == 0)\n    assert evens == [2, 4]\n    assert odds == [1, 3]\n",
     "list, callable", "tuple"),

    ("frequency_count", """def frequency_count(lst: list) -> dict:
    from collections import Counter
    return dict(Counter(lst))""",
     "def test():\n    assert frequency_count(['a', 'b', 'a']) == {'a': 2, 'b': 1}\n",
     "list", "dict"),

    # 4. Math & Numeric
    ("calculate_mean", """def calculate_mean(lst: list) -> float:
    return sum(lst) / len(lst) if lst else 0.0""",
     "def test():\n    assert calculate_mean([1, 2, 3, 4, 5]) == 3.0\n",
     "list", "float"),

    ("calculate_median", """def calculate_median(lst: list):
    if not lst:
        return 0
    s = sorted(lst)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2""",
     "def test():\n    assert calculate_median([1, 3, 2]) == 2\n    assert calculate_median([1, 2, 3, 4]) == 2.5\n",
     "list", "number"),

    ("is_armstrong", """def is_armstrong(n: int) -> bool:
    digits = [int(d) for d in str(n)]
    p = len(digits)
    return sum(d ** p for d in digits) == n""",
     "def test():\n    assert is_armstrong(153) == True\n    assert is_armstrong(123) == False\n",
     "int", "bool"),

    ("celsius_to_fahrenheit", """def celsius_to_fahrenheit(c: float) -> float:
    return (c * 9/5) + 32.0""",
     "def test():\n    assert celsius_to_fahrenheit(0) == 32.0\n    assert celsius_to_fahrenheit(100) == 212.0\n",
     "float", "float"),

    ("to_binary_string", """def to_binary_string(n: int) -> str:
    return bin(n)[2:]""",
     "def test():\n    assert to_binary_string(10) == '1010'\n    assert to_binary_string(0) == '0'\n",
     "int", "str"),

    ("euclidean_distance", """def euclidean_distance(p1: tuple, p2: tuple) -> float:
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5""",
     "def test():\n    assert euclidean_distance((0, 0), (3, 4)) == 5.0\n",
     "tuple, tuple", "float"),

    ("sieve_of_eratosthenes", """def sieve_of_eratosthenes(n: int) -> list:
    if n < 2:
        return []
    primes = [True] * (n + 1)
    primes[0] = primes[1] = False
    for p in range(2, int(n ** 0.5) + 1):
        if primes[p]:
            for i in range(p * p, n + 1, p):
                primes[i] = False
    return [i for i, is_p in enumerate(primes) if is_p]""",
     "def test():\n    assert sieve_of_eratosthenes(10) == [2, 3, 5, 7]\n",
     "int", "list"),

    ("find_divisors", """def find_divisors(n: int) -> list:
    divs = []
    for i in range(1, int(n ** 0.5) + 1):
        if n % i == 0:
            divs.append(i)
            if i*i != n:
                divs.append(n // i)
    return sorted(divs)""",
     "def test():\n    assert find_divisors(12) == [1, 2, 3, 4, 6, 12]\n",
     "int", "list"),

    ("calculate_variance", """def calculate_variance(lst: list) -> float:
    if not lst:
        return 0.0
    mean = sum(lst) / len(lst)
    return sum((x - mean) ** 2 for x in lst) / len(lst)""",
     "def test():\n    assert calculate_variance([2, 4, 4, 4, 5, 5, 7, 9]) == 4.0\n",
     "list", "float"),

    ("is_perfect_square", """def is_perfect_square(n: int) -> bool:
    if n < 0:
        return False
    r = int(n ** 0.5)
    return r * r == n""",
     "def test():\n    assert is_perfect_square(16) == True\n    assert is_perfect_square(14) == False\n",
     "int", "bool"),

    # 5. Utilities & Logic
    ("clamp", """def clamp(val, low, high):
    return max(low, min(val, high))""",
     "def test():\n    assert clamp(5, 1, 10) == 5\n    assert clamp(-5, 0, 10) == 0\n    assert clamp(15, 0, 10) == 10\n",
     "number, number, number", "number"),

    ("is_monotonically_increasing", """def is_monotonically_increasing(lst: list) -> bool:
    return all(lst[i] <= lst[i+1] for i in range(len(lst) - 1))""",
     "def test():\n    assert is_monotonically_increasing([1, 2, 2, 3]) == True\n    assert is_monotonically_increasing([1, 3, 2]) == False\n",
     "list", "bool"),

    ("eval_rpn", """def eval_rpn(tokens: list) -> int:
    stack = []
    ops = {
        '+': lambda a, b: a + b,
        '-': lambda a, b: a - b,
        '*': lambda a, b: a * b,
        '/': lambda a, b: int(a / b)
    }
    for t in tokens:
        if t in ops:
            b, a = stack.pop(), stack.pop()
            stack.append(ops[t](a, b))
        else:
            stack.append(int(t))
    return stack[0]""",
     "def test():\n    assert eval_rpn(['2', '1', '+', '3', '*']) == 9\n",
     "list", "int"),

    ("is_balanced_brackets", """def is_balanced_brackets(s: str) -> bool:
    stack = []
    mapping = {')': '(', '}': '{', ']': '['}
    for char in s:
        if char in mapping.values():
            stack.append(char)
        elif char in mapping:
            if not stack or stack[-1] != mapping[char]:
                return False
            stack.pop()
    return len(stack) == 0""",
     "def test():\n    assert is_balanced_brackets('{[()]}') == True\n    assert is_balanced_brackets('{[(])}') == False\n",
     "str", "bool"),

    ("find_missing_number", """def find_missing_number(nums: list) -> int:
    n = len(nums)
    expected = n * (n + 1) // 2
    return expected - sum(nums)""",
     "def test():\n    assert find_missing_number([3, 0, 1]) == 2\n",
     "list", "int"),

    ("transpose_matrix", """def transpose_matrix(matrix: list) -> list:
    if not matrix:
        return []
    return [list(row) for row in zip(*matrix)]""",
     "def test():\n    assert transpose_matrix([[1, 2], [3, 4], [5, 6]]) == [[1, 3, 5], [2, 4, 6]]\n",
     "list", "list"),

    ("permutations_list", """def permutations_list(lst: list) -> list:
    import itertools
    return [list(p) for p in itertools.permutations(lst)]""",
     "def test():\n    assert sorted(permutations_list([1, 2])) == [[1, 2], [2, 1]]\n",
     "list", "list"),

    ("deep_dict_equal", """def deep_dict_equal(d1, d2) -> bool:
    return d1 == d2""",
     "def test():\n    assert deep_dict_equal({'a': [1, {'b': 2}]}, {'a': [1, {'b': 2}]}) == True\n    assert deep_dict_equal({'a': 1}, {'a': 2}) == False\n",
     "dict, dict", "bool"),

    ("int_to_roman", """def int_to_roman(num: int) -> str:
    val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syb = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
    res = []
    i = 0
    while num > 0:
        for _ in range(num // val[i]):
            res.append(syb[i])
            num -= val[i]
        i += 1
    return "".join(res)""",
     "def test():\n    assert int_to_roman(1994) == 'MCMXCIV'\n    assert int_to_roman(4) == 'IV'\n",
     "int", "str"),

    ("roman_to_int", """def roman_to_int(s: str) -> int:
    roman_map = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    total = 0
    prev_val = 0
    for char in reversed(s):
        val = roman_map[char]
        if val < prev_val:
            total -= val
        else:
            total += val
        prev_val = val
    return total""",
     "def test():\n    assert roman_to_int('MCMXCIV') == 1994\n    assert roman_to_int('LVIII') == 58\n",
     "str", "int")
]

def seed_all():
    conn = init_db()
    stored_count = 0
    for name, source, tests, in_t, out_t in SEEDS_50:
        mid = store(conn, name, source, tests, "MIT", "seed_canonical", in_t, out_t)
        if mid:
            stored_count += 1
    print(f"[+] Successfully verified and seeded {stored_count}/{len(SEEDS_50)} canonical modules.")

if __name__ == "__main__":
    seed_all()
