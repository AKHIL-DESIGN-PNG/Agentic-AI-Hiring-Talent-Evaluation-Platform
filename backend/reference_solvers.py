from __future__ import annotations

import ast
from typing import Any, Callable


ReferenceSolver = Callable[[Any], str]


def _parse_value(raw_input: Any) -> Any:
    if not isinstance(raw_input, str):
        return raw_input
    try:
        return ast.literal_eval(raw_input)
    except Exception:
        return raw_input


def longest_substring_without_repeating_characters(raw_input: Any) -> str:
    text = str(_parse_value(raw_input))
    seen: dict[str, int] = {}
    left = 0
    best = 0
    for right, char in enumerate(text):
        if char in seen and seen[char] >= left:
            left = seen[char] + 1
        seen[char] = right
        best = max(best, right - left + 1)
    return str(best)


def longest_success_streak(raw_input: Any) -> str:
    text = str(_parse_value(raw_input))
    best = 0
    streak = 0
    for char in text:
        if char == "S":
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return str(best)


def min_alternating_edits(raw_input: Any) -> str:
    text = str(_parse_value(raw_input))
    patterns = ("AB", "BA")
    best = len(text)
    for pattern in patterns:
        changes = 0
        for index, char in enumerate(text):
            if char != pattern[index % 2]:
                changes += 1
        best = min(best, changes)
    return str(best if text else 0)


def longest_distinct_window(raw_input: Any) -> str:
    return longest_substring_without_repeating_characters(raw_input)


def trapping_rain_water(raw_input: Any) -> str:
    heights = list(_parse_value(raw_input))
    left = 0
    right = len(heights) - 1
    left_max = 0
    right_max = 0
    trapped = 0
    while left <= right:
        if heights[left] <= heights[right]:
            left_max = max(left_max, heights[left])
            trapped += left_max - heights[left]
            left += 1
        else:
            right_max = max(right_max, heights[right])
            trapped += right_max - heights[right]
            right -= 1
    return str(trapped)


def remove_element_count(raw_input: Any) -> str:
    parsed = _parse_value(raw_input)
    nums = list(parsed[0]) if isinstance(parsed, (list, tuple)) and parsed else []
    val = parsed[1] if isinstance(parsed, (list, tuple)) and len(parsed) > 1 else None
    return str(sum(1 for item in nums if item != val))


def palindrome_number(raw_input: Any) -> str:
    value = int(_parse_value(raw_input))
    return "true" if value >= 0 and str(value) == str(value)[::-1] else "false"


REFERENCE_SOLVERS: dict[str, ReferenceSolver] = {
    "longest_substring_without_repeating_characters": longest_substring_without_repeating_characters,
    "longest_success_streak": longest_success_streak,
    "min_alternating_edits": min_alternating_edits,
    "longest_distinct_window": longest_distinct_window,
    "trapping_rain_water": trapping_rain_water,
    "remove_element_count": remove_element_count,
    "palindrome_number": palindrome_number,
}


def solve_reference_case(solver_key: str, raw_input: Any) -> str:
    solver = REFERENCE_SOLVERS.get(solver_key)
    if not solver:
        raise KeyError(f"Unknown reference solver: {solver_key}")
    return solver(raw_input)
