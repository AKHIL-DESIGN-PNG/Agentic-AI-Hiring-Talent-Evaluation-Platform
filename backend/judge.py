from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXECUTION_TIMEOUT_SECONDS = float(os.getenv("JUDGE_TIMEOUT_SECONDS", "3"))
CPP_COMPILER = os.getenv("CPP_COMPILER", "").strip()
C_COMPILER = os.getenv("C_COMPILER", "").strip()
CSHARP_COMPILER = os.getenv("CSHARP_COMPILER", "").strip()
GO_COMPILER = os.getenv("GO_COMPILER", "").strip()
TSC_COMPILER = os.getenv("TSC_COMPILER", "").strip()


@dataclass
class CommandResult:
    ok: bool
    stdout: str
    stderr: str
    duration_ms: int


def runtime_availability() -> dict[str, dict[str, Any]]:
    return {
        "java": {"available": _has_command("java") and _has_command("javac"), "label": "Java"},
        "python": {"available": _has_command("python"), "label": "Python"},
        "javascript": {"available": _has_command("node"), "label": "JavaScript"},
        "cpp": {"available": bool(_cpp_command()), "label": "C++"},
        "typescript": {"available": bool(_typescript_command()), "label": "TypeScript"},
        "c": {"available": bool(_c_command()), "label": "C"},
        "csharp": {"available": bool(_csharp_command()), "label": "C#"},
        "go": {"available": bool(_go_command()), "label": "Go"},
    }


def judge_code(
    *,
    language: str,
    code: str,
    tests: list[dict[str, Any]],
    prompt: dict[str, Any],
    reveal_expected: bool,
) -> dict[str, Any]:
    availability = runtime_availability().get(language, {"available": False, "label": language})
    if not availability["available"]:
        message = "Runtime not available for this language on the current server."
        return {
            "ok": False,
            "summary": {
                "passed": 0,
                "total": len(tests),
                "execution_time_ms": 0,
                "memory_usage": "Unavailable",
                "error": message,
            },
            "cases": [
                _case_result(
                    label=test.get("label") or f"Case {idx + 1}",
                    status="error",
                    output="",
                    expected=test.get("output", "") if reveal_expected else "",
                    duration_ms=0,
                    error=message,
                    reveal_expected=reveal_expected,
                )
                for idx, test in enumerate(tests)
            ],
        }

    with tempfile.TemporaryDirectory(prefix="aits-judge-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        build = _build_runner(language=language, code=code, tests=tests, prompt=prompt, workdir=tmp_path)
        if not build["ok"]:
            return {
                "ok": False,
                "summary": {
                    "passed": 0,
                    "total": len(tests),
                    "execution_time_ms": build.get("duration_ms", 0),
                    "memory_usage": "Unavailable",
                    "error": build["error"],
                },
                "cases": [
                    _case_result(
                        label=test.get("label") or f"Case {idx + 1}",
                        status="error",
                        output="",
                        expected=test.get("output", "") if reveal_expected else "",
                        duration_ms=0,
                        error=build["error"],
                        reveal_expected=reveal_expected,
                    )
                    for idx, test in enumerate(tests)
                ],
            }

        execution = _execute(language=language, workdir=tmp_path)
        if not execution.ok:
            return {
                "ok": False,
                "summary": {
                    "passed": 0,
                    "total": len(tests),
                    "execution_time_ms": execution.duration_ms,
                    "memory_usage": "Unavailable",
                    "error": execution.stderr or "Execution failed.",
                },
                "cases": [
                    _case_result(
                        label=test.get("label") or f"Case {idx + 1}",
                        status="error",
                        output="",
                        expected=test.get("output", "") if reveal_expected else "",
                        duration_ms=execution.duration_ms,
                        error=execution.stderr or "Execution failed.",
                        reveal_expected=reveal_expected,
                    )
                    for idx, test in enumerate(tests)
                ],
            }

        try:
            parsed = json.loads(execution.stdout)
        except Exception:
            return {
                "ok": False,
                "summary": {
                    "passed": 0,
                    "total": len(tests),
                    "execution_time_ms": execution.duration_ms,
                    "memory_usage": "Unavailable",
                    "error": "Judge output parsing failed.",
                },
                "cases": [
                    _case_result(
                        label=test.get("label") or f"Case {idx + 1}",
                        status="error",
                        output="",
                        expected=test.get("output", "") if reveal_expected else "",
                        duration_ms=execution.duration_ms,
                        error="Judge output parsing failed.",
                        reveal_expected=reveal_expected,
                    )
                    for idx, test in enumerate(tests)
                ],
            }

        case_results = []
        passed = 0
        total_duration = 0
        for idx, item in enumerate(parsed):
            expected = str(tests[idx].get("output", "")).strip()
            output = _normalize_output(item.get("output", ""))
            has_expected = expected != ""
            execution_ok = bool(item.get("ok"))
            ok = execution_ok and (output == expected if has_expected else True)
            total_duration += int(item.get("duration_ms", 0))
            if ok:
                passed += 1
            case_results.append(
                _case_result(
                    label=tests[idx].get("label") or f"Case {idx + 1}",
                    status="passed" if has_expected and ok else "failed" if has_expected else "completed" if ok else "error",
                    output=output,
                    expected=expected,
                    duration_ms=int(item.get("duration_ms", 0)),
                    error=str(item.get("error", "") or ""),
                    reveal_expected=reveal_expected,
                )
            )

        return {
            "ok": True,
            "summary": {
                "passed": passed,
                "total": len(tests),
                "execution_time_ms": total_duration,
                "memory_usage": "Unavailable",
                "error": "",
            },
            "cases": case_results,
        }


def _build_runner(*, language: str, code: str, tests: list[dict[str, Any]], prompt: dict[str, Any], workdir: Path) -> dict[str, Any]:
    method_name = str(prompt.get("method_name") or "lengthOfLongestSubstring")
    signature = _signature_kind(prompt)
    cases = [_case_arguments(test.get("input", ""), signature) for test in tests]

    if language == "java":
        (workdir / "Solution.java").write_text(code, encoding="utf-8")
        (workdir / "Runner.java").write_text(_java_runner(method_name, cases), encoding="utf-8")
        result = _run(["javac", "Solution.java", "Runner.java"], cwd=workdir)
        return {"ok": result.ok, "error": result.stderr or "Java compilation failed.", "duration_ms": result.duration_ms}

    if language == "python":
        (workdir / "solution.py").write_text(code, encoding="utf-8")
        (workdir / "runner.py").write_text(_python_runner(method_name, cases), encoding="utf-8")
        return {"ok": True, "error": "", "duration_ms": 0}

    if language == "javascript":
        (workdir / "solution.js").write_text(code, encoding="utf-8")
        (workdir / "runner.js").write_text(_javascript_runner(method_name, cases), encoding="utf-8")
        return {"ok": True, "error": "", "duration_ms": 0}

    if language == "typescript":
        compiler = _typescript_command()
        if not compiler:
            return {"ok": False, "error": "TypeScript compiler is not configured on the server.", "duration_ms": 0}
        (workdir / "solution.ts").write_text(code, encoding="utf-8")
        (workdir / "runner.ts").write_text(_typescript_runner(method_name, cases), encoding="utf-8")
        result = _run([compiler, "solution.ts", "runner.ts", "--target", "ES2020", "--module", "commonjs"], cwd=workdir)
        return {"ok": result.ok, "error": result.stderr or "TypeScript compilation failed.", "duration_ms": result.duration_ms}

    if language == "cpp":
        compiler = _cpp_command()
        if not compiler:
            return {"ok": False, "error": "C++ compiler is not configured on the server.", "duration_ms": 0}
        (workdir / "solution.cpp").write_text(code, encoding="utf-8")
        (workdir / "runner.cpp").write_text(_cpp_runner(method_name, cases), encoding="utf-8")
        result = _run([compiler, "solution.cpp", "runner.cpp", "-O2", "-std=c++17", "-o", "solution.exe"], cwd=workdir)
        return {"ok": result.ok, "error": result.stderr or "C++ compilation failed.", "duration_ms": result.duration_ms}

    if language == "c":
        compiler = _c_command()
        if not compiler:
            return {"ok": False, "error": "C compiler is not configured on the server.", "duration_ms": 0}
        (workdir / "solution.c").write_text(code, encoding="utf-8")
        (workdir / "runner.c").write_text(_c_runner(method_name, signature, cases), encoding="utf-8")
        result = _run([compiler, "solution.c", "runner.c", "-O2", "-std=c11", "-o", "solution.exe"], cwd=workdir)
        return {"ok": result.ok, "error": result.stderr or "C compilation failed.", "duration_ms": result.duration_ms}

    if language == "csharp":
        compiler = _csharp_command()
        if not compiler:
            return {"ok": False, "error": "C# compiler is not configured on the server.", "duration_ms": 0}
        (workdir / "Solution.cs").write_text(code, encoding="utf-8")
        (workdir / "Program.cs").write_text(_csharp_runner(method_name, cases), encoding="utf-8")
        result = _run([compiler, "Solution.cs", "Program.cs", "/out:solution.exe"], cwd=workdir)
        return {"ok": result.ok, "error": result.stderr or "C# compilation failed.", "duration_ms": result.duration_ms}

    if language == "go":
        compiler = _go_command()
        if not compiler:
            return {"ok": False, "error": "Go compiler is not configured on the server.", "duration_ms": 0}
        (workdir / "solution.go").write_text(code, encoding="utf-8")
        (workdir / "runner.go").write_text(_go_runner(method_name, cases), encoding="utf-8")
        result = _run([compiler, "build", "-o", "solution.exe", "solution.go", "runner.go"], cwd=workdir)
        return {"ok": result.ok, "error": result.stderr or "Go compilation failed.", "duration_ms": result.duration_ms}

    return {"ok": False, "error": f"Unsupported language: {language}", "duration_ms": 0}


def _execute(*, language: str, workdir: Path) -> CommandResult:
    if language == "java":
        return _run(["java", "-cp", str(workdir), "Runner"], cwd=workdir)
    if language == "python":
        return _run(["python", "runner.py"], cwd=workdir)
    if language == "javascript":
        return _run(["node", "runner.js"], cwd=workdir)
    if language == "typescript":
        return _run(["node", "runner.js"], cwd=workdir)
    if language in {"cpp", "c", "csharp", "go"}:
        return _run([str(workdir / "solution.exe")], cwd=workdir)
    return CommandResult(ok=False, stdout="", stderr="Unsupported language.", duration_ms=0)


def _run(command: list[str], *, cwd: Path) -> CommandResult:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=EXECUTION_TIMEOUT_SECONDS,
            check=False,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        return CommandResult(
            ok=completed.returncode == 0,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
            duration_ms=duration_ms,
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.perf_counter() - started) * 1000)
        return CommandResult(ok=False, stdout="", stderr="Execution timed out.", duration_ms=duration_ms)
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        return CommandResult(ok=False, stdout="", stderr=str(exc), duration_ms=duration_ms)


def _case_result(*, label: str, status: str, output: str, expected: str, duration_ms: int, error: str, reveal_expected: bool) -> dict[str, Any]:
    return {
        "label": label,
        "status": status,
        "output": output,
        "expected": expected if reveal_expected else "",
        "execution_time": f"{duration_ms} ms",
        "memory_usage": "Unavailable",
        "error": error,
    }


def _has_command(name: str) -> bool:
    return shutil.which(name) is not None


def _cpp_command() -> str | None:
    if CPP_COMPILER:
        return CPP_COMPILER
    for candidate in ("g++", "clang++"):
        if _has_command(candidate):
            return candidate
    return None


def _c_command() -> str | None:
    if C_COMPILER:
        return C_COMPILER
    for candidate in ("gcc", "clang", "cc"):
        if _has_command(candidate):
            return candidate
    return None


def _csharp_command() -> str | None:
    if CSHARP_COMPILER:
        return CSHARP_COMPILER
    for candidate in ("csc", "mcs"):
        if _has_command(candidate):
            return candidate
    return None


def _go_command() -> str | None:
    if GO_COMPILER:
        return GO_COMPILER
    if _has_command("go"):
        return "go"
    return None


def _typescript_command() -> str | None:
    if TSC_COMPILER:
        return TSC_COMPILER
    if _has_command("tsc"):
        return "tsc"
    return None


def _signature_kind(prompt: dict[str, Any]) -> str:
    solver_key = str(prompt.get("reference_solver_key") or "").strip().lower()
    if solver_key in {
        "longest_substring_without_repeating_characters",
        "longest_success_streak",
        "min_alternating_edits",
        "longest_distinct_window",
    }:
        return "string"
    if solver_key == "trapping_rain_water":
        return "int_array"
    if solver_key == "remove_element_count":
        return "int_array_and_int"
    if solver_key == "palindrome_number":
        return "int"
    return "string"


def _parse_value(raw_input: Any) -> Any:
    if not isinstance(raw_input, str):
        return raw_input
    try:
        return ast.literal_eval(raw_input)
    except Exception:
        return raw_input


def _case_arguments(raw_input: Any, signature: str) -> list[Any]:
    parsed = _parse_value(raw_input)
    if signature == "int_array":
        return [list(parsed) if isinstance(parsed, (list, tuple)) else []]
    if signature == "int_array_and_int":
        if isinstance(parsed, (list, tuple)) and len(parsed) >= 2:
            return [list(parsed[0]) if isinstance(parsed[0], (list, tuple)) else [], int(parsed[1])]
        return [[], 0]
    if signature == "int":
        return [int(parsed)]
    return [str(parsed)]


def _normalize_output(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (list, dict)):
        return json.dumps(value, separators=(",", ":"))
    return str(value).strip()


def _json_literal(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def _java_literal(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "new int[]{" + ", ".join(str(int(item)) for item in value) + "}"
    return "null"


def _cpp_literal(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "vector<int>{" + ", ".join(str(int(item)) for item in value) + "}"
    return "{}"


def _c_literal(value: Any, name: str) -> tuple[str, str]:
    if isinstance(value, str):
        return "", json.dumps(value)
    if isinstance(value, bool):
        return "", "true" if value else "false"
    if isinstance(value, int):
        return "", str(value)
    if isinstance(value, list):
        declaration = f"int {name}[] = {{{', '.join(str(int(item)) for item in value)}}};"
        return declaration, name
    return "", "0"


def _go_literal(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[]int{" + ", ".join(str(int(item)) for item in value) + "}"
    return "nil"


def _java_runner(method_name: str, cases: list[list[Any]]) -> str:
    blocks = []
    for index, args in enumerate(cases):
        arguments = ", ".join(_java_literal(arg) for arg in args)
        blocks.append(
            f"""        {{
            long started = System.nanoTime();
            try {{
                Object output = solution.{method_name}({arguments});
                long duration = (System.nanoTime() - started) / 1_000_000;
                rows.add(String.format("{{\\"ok\\":true,\\"output\\":\\"%s\\",\\"duration_ms\\":%d,\\"error\\":\\"\\"}}", escapeJson(String.valueOf(output)), duration));
            }} catch (Exception ex) {{
                long duration = (System.nanoTime() - started) / 1_000_000;
                rows.add(String.format("{{\\"ok\\":false,\\"output\\":\\"\\",\\"duration_ms\\":%d,\\"error\\":\\"%s\\"}}", duration, escapeJson(ex.toString())));
            }}
        }}"""
        )
    body = "\n".join(blocks)
    return f"""import java.util.*;

public class Runner {{
    private static String escapeJson(String value) {{
        return value.replace("\\\\", "\\\\\\\\").replace("\\"", "\\\\\\"");
    }}

    public static void main(String[] args) {{
        Solution solution = new Solution();
        List<String> rows = new ArrayList<>();
{body}
        System.out.print("[" + String.join(",", rows) + "]");
    }}
}}
"""


def _python_runner(method_name: str, cases: list[list[Any]]) -> str:
    payload = _json_literal(cases)
    return f"""import json
import time
from solution import Solution

cases = json.loads('{payload}')
solution = Solution()
rows = []
for args in cases:
    started = time.perf_counter()
    try:
        output = getattr(solution, "{method_name}")(*args)
        duration = int((time.perf_counter() - started) * 1000)
        rows.append({{"ok": True, "output": output, "duration_ms": duration, "error": ""}})
    except Exception as exc:
        duration = int((time.perf_counter() - started) * 1000)
        rows.append({{"ok": False, "output": "", "duration_ms": duration, "error": str(exc)}})

print(json.dumps(rows))
"""


def _javascript_runner(method_name: str, cases: list[list[Any]]) -> str:
    payload = _json_literal(cases)
    return f"""const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync('./solution.js', 'utf8');
const cases = JSON.parse('{payload}');
const context = {{ console }};
vm.createContext(context);
vm.runInContext(code, context);
const Solution = vm.runInContext('Solution', context);
const solution = new Solution();
const rows = [];
for (const args of cases) {{
  const started = Date.now();
  try {{
    const output = solution['{method_name}'](...args);
    rows.push({{ ok: true, output, duration_ms: Date.now() - started, error: '' }});
  }} catch (error) {{
    rows.push({{ ok: false, output: '', duration_ms: Date.now() - started, error: String(error) }});
  }}
}}
console.log(JSON.stringify(rows));
"""


def _typescript_runner(method_name: str, cases: list[list[Any]]) -> str:
    payload = _json_literal(cases)
    return f"""const cases = JSON.parse('{payload}');
const solution = new Solution();
const rows: Array<{{ ok: boolean; output: unknown; duration_ms: number; error: string }}> = [];
for (const args of cases) {{
  const started = Date.now();
  try {{
    const output = (solution as any)['{method_name}'](...args);
    rows.push({{ ok: true, output, duration_ms: Date.now() - started, error: '' }});
  }} catch (error) {{
    rows.push({{ ok: false, output: '', duration_ms: Date.now() - started, error: String(error) }});
  }}
}}
console.log(JSON.stringify(rows));
"""


def _cpp_runner(method_name: str, cases: list[list[Any]]) -> str:
    blocks = []
    for args in cases:
        arguments = ", ".join(_cpp_literal(arg) for arg in args)
        blocks.append(
            f"""    {{
        auto started = chrono::steady_clock::now();
        try {{
            auto output = solution.{method_name}({arguments});
            auto duration = chrono::duration_cast<chrono::milliseconds>(chrono::steady_clock::now() - started).count();
            rows.push_back("{{\\"ok\\":true,\\"output\\":\\"" + jsonEscape(toStringValue(output)) + "\\",\\"duration_ms\\":" + to_string(duration) + ",\\"error\\":\\"\\"}}");
        }} catch (const exception& ex) {{
            auto duration = chrono::duration_cast<chrono::milliseconds>(chrono::steady_clock::now() - started).count();
            rows.push_back("{{\\"ok\\":false,\\"output\\":\\"\\",\\"duration_ms\\":" + to_string(duration) + ",\\"error\\":\\"" + jsonEscape(ex.what()) + "\\"}}");
        }}
    }}"""
        )
    body = "\n".join(blocks)
    return f"""#include <chrono>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
using namespace std;

class Solution;

static string jsonEscape(const string& value) {{
    string out;
    for (char c : value) {{
        if (c == '\\\\' || c == '"') out.push_back('\\\\');
        out.push_back(c);
    }}
    return out;
}}

template <typename T>
static string toStringValue(const T& value) {{
    ostringstream stream;
    stream << value;
    return stream.str();
}}

int main() {{
    Solution solution;
    vector<string> rows;
{body}
    cout << "[";
    for (size_t i = 0; i < rows.size(); ++i) {{
        cout << rows[i];
        if (i + 1 < rows.size()) cout << ",";
    }}
    cout << "]";
    return 0;
}}
"""


def _c_runner(method_name: str, signature: str, cases: list[list[Any]]) -> str:
    if signature == "int_array":
        prototype = f"int {method_name}(int height[], int heightSize);"
    elif signature == "int_array_and_int":
        prototype = f"int {method_name}(int nums[], int numsSize, int val);"
    elif signature == "int":
        prototype = f"bool {method_name}(int x);"
    else:
        prototype = f"int {method_name}(char s[]);"

    blocks = []
    for index, args in enumerate(cases):
        declarations: list[str] = []
        call_args: list[str] = []
        for arg_index, arg in enumerate(args):
            declaration, reference = _c_literal(arg, f"arg_{index}_{arg_index}")
            if declaration:
                declarations.append(declaration)
                if isinstance(arg, list):
                    call_args.extend([reference, str(len(arg))])
                else:
                    call_args.append(reference)
            else:
                call_args.append(reference)
        if signature == "int_array_and_int" and len(args) >= 2 and isinstance(args[0], list):
            call_args = [f"arg_{index}_0", str(len(args[0])), str(int(args[1]))]
        block = "\n        ".join(declarations)
        call = ", ".join(call_args)
        result_decl = "bool result = " if signature == "int" else "int result = "
        output_expr = 'result ? "true" : "false"' if signature == "int" else "result"
        blocks.append(
            f"""    {{
        {block if block else ""}
        long started = now_ms();
        int duration = 0;
        char output[128];
        char error[256] = "";
        bool ok = true;
        {result_decl}{method_name}({call});
        duration = (int)(now_ms() - started);
        snprintf(output, sizeof(output), "%s", {output_expr});
        append_row(rows, &row_count, ok, output, duration, error);
    }}"""
        )
    body = "\n".join(blocks)
    return f"""#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

{prototype}

static long now_ms(void) {{
    return (long)((double)clock() * 1000.0 / CLOCKS_PER_SEC);
}}

static void escape_json(const char* src, char* dest, size_t size) {{
    size_t j = 0;
    for (size_t i = 0; src[i] && j + 2 < size; ++i) {{
        if (src[i] == '\\\\' || src[i] == '"') dest[j++] = '\\\\';
        dest[j++] = src[i];
    }}
    dest[j] = '\\0';
}}

static void append_row(char rows[][512], int* row_count, bool ok, const char* output, int duration, const char* error) {{
    char escaped_output[256];
    char escaped_error[256];
    escape_json(output, escaped_output, sizeof(escaped_output));
    escape_json(error, escaped_error, sizeof(escaped_error));
    snprintf(rows[*row_count], 512, "{{\\"ok\\":%s,\\"output\\":\\"%s\\",\\"duration_ms\\":%d,\\"error\\":\\"%s\\"}}", ok ? "true" : "false", escaped_output, duration, escaped_error);
    (*row_count)++;
}}

int main(void) {{
    char rows[128][512];
    int row_count = 0;
{body}
    printf("[");
    for (int i = 0; i < row_count; ++i) {{
        printf("%s", rows[i]);
        if (i + 1 < row_count) printf(",");
    }}
    printf("]");
    return 0;
}}
"""


def _csharp_runner(method_name: str, cases: list[list[Any]]) -> str:
    blocks = []
    for args in cases:
        arguments = ", ".join(_json_literal(arg).replace('"', '"') if isinstance(arg, str) else (_csharp_array_literal(arg) if isinstance(arg, list) else ("true" if arg is True else "false" if arg is False else str(arg))) for arg in args)
        blocks.append(
            f"""            {{
                var started = DateTime.UtcNow;
                try {{
                    var output = solution.{method_name}({arguments});
                    rows.Add(new Dictionary<string, object?> {{
                        ["ok"] = true,
                        ["output"] = output?.ToString() ?? "",
                        ["duration_ms"] = (int)(DateTime.UtcNow - started).TotalMilliseconds,
                        ["error"] = ""
                    }});
                }} catch (Exception ex) {{
                    rows.Add(new Dictionary<string, object?> {{
                        ["ok"] = false,
                        ["output"] = "",
                        ["duration_ms"] = (int)(DateTime.UtcNow - started).TotalMilliseconds,
                        ["error"] = ex.ToString()
                    }});
                }}
            }}"""
        )
    body = "\n".join(blocks)
    return f"""using System;
using System.Collections.Generic;
using System.Text.Json;

public class Program
{{
    public static void Main()
    {{
        var solution = new Solution();
        var rows = new List<Dictionary<string, object?>>();
{body}
        Console.Write(JsonSerializer.Serialize(rows));
    }}
}}
"""


def _csharp_array_literal(values: list[Any]) -> str:
    return "new int[] { " + ", ".join(str(int(item)) for item in values) + " }"


def _go_runner(method_name: str, cases: list[list[Any]]) -> str:
    blocks = []
    for args in cases:
        arguments = ", ".join(_go_literal(arg) for arg in args)
        blocks.append(
            f"""    {{
        started := time.Now()
        func() {{
            defer func() {{
                if recovered := recover(); recovered != nil {{
                    rows = append(rows, map[string]interface{{}}{{"ok": false, "output": "", "duration_ms": time.Since(started).Milliseconds(), "error": fmt.Sprint(recovered)}})
                }}
            }}()
            output := {method_name}({arguments})
            rows = append(rows, map[string]interface{{}}{{"ok": true, "output": fmt.Sprint(output), "duration_ms": time.Since(started).Milliseconds(), "error": ""}})
        }}()
    }}"""
        )
    body = "\n".join(blocks)
    return f"""package main

import (
    "encoding/json"
    "fmt"
    "time"
)

func main() {{
    rows := make([]map[string]interface{{}}, 0)
{body}
    payload, _ := json.Marshal(rows)
    fmt.Print(string(payload))
}}
"""
