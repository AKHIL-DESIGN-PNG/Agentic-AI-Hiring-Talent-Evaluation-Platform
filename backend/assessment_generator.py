from __future__ import annotations

import ast
import json
import os
import re
from typing import Any
from dotenv import load_dotenv
from nvidia_llm import request_nvidia_chat

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "35"))
MAX_LLM_ATTEMPTS = 3
SUPPORTED_RUNTIME_LANGUAGES = {"java", "python", "cpp", "javascript"}

SECTION_BATCH_TARGETS = {
    "numerical_reasoning": 10,
    "verbal_reasoning": 10,
    "abstract_reasoning": 10,
    "coding_mcq": 22,
    "coding_section": 3,
}


def generate_mcq_block_questions(
    *,
    section_title: str,
    transcript: str,
    difficulty: str = "Medium",
    count: int = 5,
) -> list[dict[str, Any]]:
    prompt = f"""
Generate ONLY valid JSON. Do not wrap in markdown.

Return this exact shape:
{{
  "questions": [
    {{
      "question": "",
      "passage": "",
      "options": ["", "", "", ""],
      "answer": "",
      "difficulty": "{difficulty}"
    }}
  ]
}}

Rules:
- Generate exactly {count} MCQ questions.
- Use the transcript/context below as the source.
- Each question must have exactly 4 options.
- The answer must exactly match one option.
- Questions must test understanding, inference, or detail recall.
- Keep the questions concise and production-ready for a hiring assessment.
- Difficulty must be {difficulty}.

Section title: {section_title}
Transcript/context:
{transcript}
""".strip()
    payload = _call_llm_json_with_retry(
        prompt,
        max_output_tokens=900,
        section_key="mcq_block",
        validator=lambda item: item if isinstance(item, dict) else (_ for _ in ()).throw(ValueError("MCQ block payload must be an object")),
    )
    questions = payload.get("questions") if isinstance(payload.get("questions"), list) else []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(questions[:count]):
        if not isinstance(item, dict):
            continue
        options = item.get("options") if isinstance(item.get("options"), list) else []
        normalized_options = [str(option or "").strip() for option in options][:4]
        if len(normalized_options) < 4:
            continue
        answer = str(item.get("answer") or "").strip()
        if answer not in normalized_options:
            continue
        normalized.append(
            {
                "id": f"mcq-block-{index + 1}",
                "question": str(item.get("question") or "").strip(),
                "passage": str(item.get("passage") or transcript).strip(),
                "options": normalized_options,
                "answer": answer,
                "difficulty": str(item.get("difficulty") or difficulty).strip() or difficulty,
            }
        )
    if normalized:
        return normalized

    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", transcript) if item.strip()]
    source_lines = sentences or [transcript]
    fallback: list[dict[str, Any]] = []
    for index in range(count):
        basis = source_lines[index % len(source_lines)]
        summary = basis[:140] if basis else "Insufficient context"
        fallback.append(
            {
                "id": f"mcq-block-fallback-{index + 1}",
                "question": f"What is the most accurate interpretation of statement {index + 1}?",
                "passage": basis,
                "options": [
                    summary,
                    "The statement contradicts the context",
                    "The statement is unrelated to the context",
                    "Cannot be determined from the context",
                ],
                "answer": summary,
                "difficulty": difficulty,
            }
        )
    return fallback


def detect_languages(job_description: str) -> list[str]:
    patterns = [
        ("java", r"(?<![a-z0-9])java(?![a-z0-9])"),
        ("python", r"(?<![a-z0-9])python(?![a-z0-9])"),
        ("cpp", r"(?<![a-z0-9])(c\+\+|cpp)(?![a-z0-9])"),
        ("javascript", r"(?<![a-z0-9])(javascript|node\.?js|js)(?![a-z0-9])"),
        ("typescript", r"(?<![a-z0-9])(typescript|ts)(?![a-z0-9])"),
        ("csharp", r"(?<![a-z0-9])(c#|c-sharp|\.net)(?![a-z0-9])"),
        ("c", r"(?<![a-z0-9])c(?![a-z0-9])"),
        ("go", r"(?<![a-z0-9])(go|golang)(?![a-z0-9])"),
        ("php", r"(?<![a-z0-9])php(?![a-z0-9])"),
        ("ruby", r"(?<![a-z0-9])ruby(?![a-z0-9])"),
        ("swift", r"(?<![a-z0-9])swift(?![a-z0-9])"),
        ("kotlin", r"(?<![a-z0-9])kotlin(?![a-z0-9])"),
    ]
    framework_hints = [
        ("java", ("spring boot", "spring mvc", "hibernate", "maven", "gradle", "j2ee")),
        ("python", ("django", "flask", "fastapi", "pandas", "numpy", "pytest")),
        ("javascript", ("node.js", "nodejs", "react", "next.js", "nextjs", "express.js", "expressjs")),
        ("cpp", ("stl", "boost", "modern c++")),
    ]
    lowered = (job_description or "").lower()
    found: list[str] = []
    for label, pattern in patterns:
        if re.search(pattern, lowered) and label not in found:
            found.append(label)
    for label, hints in framework_hints:
        if label not in found and any(hint in lowered for hint in hints):
            found.append(label)
    return found


def runtime_languages(detected: list[str]) -> list[str]:
    mapped: list[str] = []
    for item in detected:
        if item in SUPPORTED_RUNTIME_LANGUAGES:
            mapped.append(item)
        elif item == "typescript":
            mapped.append("javascript")
        elif item == "c":
            mapped.append("cpp")
    deduped: list[str] = []
    for item in mapped:
        if item not in deduped:
            deduped.append(item)
    return deduped


def generate_assessment_metadata(
    assessment_name: str,
    job_description: str,
    company_name: str | None = None,
) -> dict[str, Any]:
    detected_languages = detect_languages(job_description)
    prompt = f"""
Generate ONLY valid JSON. Do not wrap in markdown.

Return this exact shape:
{{
  "role": "",
  "must_have_skills": [],
  "good_to_have_skills": [],
  "experience_required": "",
  "languages": []
}}

Rules:
- Infer role, must-have skills, good-to-have skills, experience, and languages from the JD.
- Keep the output concise and realistic.

Assessment name: {assessment_name}
Company name: {company_name or "Not provided"}
Detected languages from JD: {json.dumps(detected_languages)}

Job description:
{job_description}
""".strip()
    payload = _call_llm_json_with_retry(
        prompt,
        max_output_tokens=320,
        section_key="metadata",
        validator=lambda item: item if isinstance(item, dict) else (_ for _ in ()).throw(ValueError("Metadata payload must be an object")),
    )
    return {
        "role": str(payload.get("role") or "").strip() or assessment_name,
        "must_have_skills": _string_list(payload.get("must_have_skills")),
        "good_to_have_skills": _string_list(payload.get("good_to_have_skills")),
        "experience_required": str(payload.get("experience_required") or "").strip() or "Not specified",
        "languages": _string_list(payload.get("languages")) or detected_languages,
    }


def generate_section_batch(
    section_key: str,
    assessment_name: str,
    job_description: str,
    company_name: str | None = None,
    previous_questions: list[str] | None = None,
    batch_size: int = 3,
    existing_count: int = 0,
) -> dict[str, Any]:
    detected_languages = detect_languages(job_description)
    available_runtime_languages = runtime_languages(detected_languages)
    if section_key == "coding_section":
        prompt = _build_coding_problem_batch_prompt(
            assessment_name=assessment_name,
            job_description=job_description,
            company_name=company_name or "",
            detected_languages=detected_languages,
            runtime_supported=available_runtime_languages,
            previous_questions=previous_questions or [],
            batch_size=batch_size,
            existing_count=existing_count,
        )
        return _call_llm_json_with_retry(
            prompt,
            max_output_tokens=850,
            section_key=section_key,
            validator=lambda item: _normalize_coding_problem_batch(item, available_runtime_languages),
        )

    prompt = _build_question_batch_prompt(
        section_key=section_key,
        assessment_name=assessment_name,
        job_description=job_description,
        company_name=company_name or "",
        detected_languages=detected_languages,
        runtime_supported=available_runtime_languages,
        previous_questions=previous_questions or [],
        batch_size=batch_size,
        existing_count=existing_count,
    )
    return _call_llm_json_with_retry(
        prompt,
        max_output_tokens=650 if section_key == "coding_mcq" else 420,
        section_key=section_key,
        validator=lambda item: _normalize_question_batch(item, section_key, available_runtime_languages),
    )


def generate_assessment_blueprint(
    assessment_name: str,
    job_description: str,
    company_name: str | None = None,
    previous_questions: list[str] | None = None,
) -> dict[str, Any]:
    metadata = generate_assessment_metadata(assessment_name, job_description, company_name)
    sections: dict[str, Any] = {}
    batch_sizes = {
        "numerical_reasoning": 10,
        "verbal_reasoning": 10,
        "abstract_reasoning": 10,
        "coding_mcq": 22,
        "coding_section": 3,
    }
    for section_key, batch_size in batch_sizes.items():
        sections[section_key] = generate_section_batch(
            section_key=section_key,
            assessment_name=assessment_name,
            job_description=job_description,
            company_name=company_name,
            previous_questions=previous_questions or [],
            batch_size=batch_size,
            existing_count=0,
        )
    return {
        "role": metadata["role"],
        "must_have_skills": metadata["must_have_skills"],
        "good_to_have_skills": metadata["good_to_have_skills"],
        "experience_required": metadata["experience_required"],
        "languages": metadata["languages"],
        "sections": sections,
    }


def _build_question_batch_prompt(
    section_key: str,
    assessment_name: str,
    job_description: str,
    company_name: str,
    detected_languages: list[str],
    runtime_supported: list[str],
    previous_questions: list[str],
    batch_size: int,
    existing_count: int,
) -> str:
    section_titles = {
        "numerical_reasoning": "Numerical Reasoning",
        "verbal_reasoning": "Verbal Reasoning",
        "abstract_reasoning": "Abstract Reasoning",
        "coding_mcq": "Coding MCQ",
    }
    rules_by_section = {
        "numerical_reasoning": "Use arithmetic, percentages, ratio and proportion, time-based reasoning, data interpretation, and logical series. Keep each question solvable within 60 seconds.",
        "verbal_reasoning": "Use comprehension, sentence correction, rearrangement, inference, and tone detection. Focus on logic and understanding rather than memory.",
        "abstract_reasoning": "Use pattern recognition, visual analogy, odd one out, rotation or reflection, and matrix logic. Keep it logic-focused.",
        "coding_mcq": f"Use only these runtime languages: {json.dumps(runtime_supported or sorted(SUPPORTED_RUNTIME_LANGUAGES))}. Cover output prediction, debugging, logic tracing, time complexity, and edge cases.",
    }
    return f"""
Generate ONLY valid JSON. Do not wrap in markdown.

Return this exact shape:
{{
  "section": "{section_titles[section_key]}",
  "questions": []
}}

Rules:
- Generate exactly {batch_size} new questions.
- These are batch questions starting after existing_count={existing_count}.
- Each MCQ must have 4 options, one answer matching an option, and a short explanation.
- {rules_by_section[section_key]}
- Avoid any question or wording too similar to previous questions.

Assessment name: {assessment_name}
Company name: {company_name or "Not provided"}
Detected languages from JD: {json.dumps(detected_languages)}
Previous questions to avoid: {json.dumps(previous_questions[:120])}

Job description:
{job_description}
""".strip()


def _build_coding_problem_batch_prompt(
    assessment_name: str,
    job_description: str,
    company_name: str,
    detected_languages: list[str],
    runtime_supported: list[str],
    previous_questions: list[str],
    batch_size: int,
    existing_count: int,
) -> str:
    runtime_list = runtime_supported or sorted(SUPPORTED_RUNTIME_LANGUAGES)
    return f"""
Generate ONLY valid JSON. Do not wrap in markdown.

Return this exact shape:
{{
  "section": "Coding Section",
  "problems": []
}}

Rules:
- Generate exactly {batch_size} coding problems.
- These are batch problems starting after existing_count={existing_count}.
- Use only runtime languages from: {json.dumps(runtime_list)}.
- If JD implies one primary language, each problem must use only that language.
- Each problem must include title, description, method_name, supported_languages, starter_code_by_language, examples, testcases, hidden_tests, reference_solver_key, time_complexity, space_complexity.
- method_name must accept one string input and return an integer.
- reference_solver_key must be one of: ["longest_success_streak","min_alternating_edits","longest_distinct_window"].
- Avoid any problem too similar to previous questions.

Assessment name: {assessment_name}
Company name: {company_name or "Not provided"}
Detected languages from JD: {json.dumps(detected_languages)}
Previous questions to avoid: {json.dumps(previous_questions[:120])}

Job description:
{job_description}
""".strip()


def _call_llm_with_retry(prompt: str, max_output_tokens: int, section_key: str) -> str:
    _ = section_key
    last_error = "NVIDIA API request failed"
    desired_tokens = max_output_tokens
    for _ in range(MAX_LLM_ATTEMPTS):
        try:
            return request_nvidia_chat(
                prompt=prompt,
                max_tokens=desired_tokens,
                temperature=0.2,
                top_p=0.7,
                timeout_seconds=LLM_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            last_error = str(exc)
            reduced_tokens = _affordable_token_limit(last_error, desired_tokens)
            if reduced_tokens and reduced_tokens < desired_tokens:
                desired_tokens = reduced_tokens
                continue
    raise ValueError(last_error)


def _call_llm_json_with_retry(
    prompt: str,
    max_output_tokens: int,
    section_key: str,
    validator,
):
    last_error = "NVIDIA JSON validation failed"
    repair_hint = ""
    for _ in range(MAX_LLM_ATTEMPTS):
        raw = _call_llm_with_retry(
            f"{prompt}\n\n{repair_hint}".strip(),
            max_output_tokens=max_output_tokens,
            section_key=section_key,
        )
        try:
            parsed = _extract_json(raw)
            return validator(parsed)
        except Exception as exc:
            last_error = str(exc)
            repair_hint = (
                "Previous response was invalid. Return only valid strict JSON with properly escaped quotes, "
                f"commas, and brackets. Fix this error exactly: {last_error}"
            )
    raise ValueError(last_error)


def _affordable_token_limit(error_text: str, requested_tokens: int) -> int | None:
    lowered = str(error_text or "").lower()
    if "402" not in lowered and "credits" not in lowered and "afford" not in lowered:
        return None
    match = re.search(r"can only afford\s+(\d+)", str(error_text), flags=re.I)
    if not match:
        return None
    affordable = int(match.group(1))
    if affordable <= 0:
        return None
    # Keep a small safety margin below the provider-reported ceiling.
    adjusted = max(96, affordable - 32)
    return min(adjusted, requested_tokens)


def _extract_json(raw_text: str) -> Any:
    cleaned = str(raw_text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    candidates: list[str] = [cleaned]
    object_match = re.search(r"\{.*\}", cleaned, flags=re.S)
    array_match = re.search(r"\[.*\]", cleaned, flags=re.S)
    if object_match:
        candidates.append(object_match.group(0))
    if array_match:
        candidates.append(array_match.group(0))
    candidates.append(_sanitize_jsonish_text(cleaned))
    seen: set[str] = set()
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        try:
            return json.loads(text)
        except Exception:
            pass
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, (dict, list)):
                return parsed
        except Exception:
            pass
    raise ValueError("NVIDIA API did not return valid JSON")


def _sanitize_jsonish_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    replacements = {
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)", r'\1"\2"\3', text)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


def _normalize_question_batch(payload: dict[str, Any], section_key: str, runtime_supported: list[str]) -> dict[str, Any]:
    payload = _soft_normalize_question_payload(payload, section_key)
    if not isinstance(payload, dict):
        raise ValueError("Generated section batch must be an object")
    if "problems" in payload:
        raise ValueError(f"Section {section_key} returned coding format instead of MCQ format")
    questions = payload.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("Generated section batch missing questions")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(questions):
        if not isinstance(item, dict):
            raise ValueError(f"Question {index + 1} is invalid")
        options = item.get("options")
        if not isinstance(options, list) or len(options) != 4:
            raise ValueError(f"Question {index + 1} must have 4 options")
        options = [str(option).strip() for option in options]
        answer = _normalize_answer_value(item.get("answer"), options)
        if answer not in options:
            raise ValueError(f"Question {index + 1} answer must match one option")
        question_text = str(item.get("question") or "").strip()
        passage_text = str(item.get("passage") or "").strip()
        if section_key == "coding_mcq":
            language = _infer_language_from_text(f"{question_text}\n{passage_text}")
            allowed = runtime_supported or sorted(SUPPORTED_RUNTIME_LANGUAGES)
            if language and language not in allowed:
                raise ValueError(f"Coding MCQ targets {language}, not one of {allowed}")
        normalized.append(
            {
                "id": str(item.get("id") or f"{section_key}-{index + 1}"),
                "passage": passage_text,
                "question": question_text,
                "options": options,
                "answer": answer,
                "explanation": str(item.get("explanation") or "").strip(),
            }
        )
    return {
        "section": str(payload.get("section") or section_key.replace("_", " ").title()),
        "questions": normalized,
    }


def _normalize_coding_problem_batch(payload: dict[str, Any], runtime_supported: list[str]) -> dict[str, Any]:
    payload = _soft_normalize_coding_payload(payload)
    if not isinstance(payload, dict):
        raise ValueError("Generated coding section batch must be an object")
    if "questions" in payload:
        raise ValueError("Coding section returned MCQ format instead of coding format")
    problems = payload.get("problems")
    if not isinstance(problems, list) or not problems:
        raise ValueError("Generated coding section batch missing problems")
    return {
        "section": str(payload.get("section") or "Coding Section"),
        "problems": [
            {
                **_normalize_coding_problem(item, runtime_supported),
                "id": str(item.get("id") or f"coding-problem-{index + 1}"),
            }
            for index, item in enumerate(problems)
        ],
    }


def _normalize_coding_problem(problem: Any, runtime_supported: list[str]) -> dict[str, Any]:
    problem = _soft_normalize_coding_problem(problem, runtime_supported)
    if not isinstance(problem, dict):
        raise ValueError("Coding problem section is invalid")
    title = str(problem.get("title") or "").strip()
    description = str(problem.get("description") or "").strip()
    method_name = str(problem.get("method_name") or "").strip()
    if not title or not description or not method_name:
        raise ValueError("Coding problem must include title, description, and method_name")
    allowed_languages = runtime_supported or sorted(SUPPORTED_RUNTIME_LANGUAGES)
    supported_languages = [item for item in _string_list(problem.get("supported_languages")) if item in allowed_languages]
    starter_code_by_language = problem.get("starter_code_by_language")
    if not isinstance(starter_code_by_language, dict):
        raise ValueError("Coding problem missing starter_code_by_language")
    starter_code_by_language = {
        str(key): str(value)
        for key, value in starter_code_by_language.items()
        if str(key) in supported_languages and str(value).strip()
    }
    if not supported_languages or not starter_code_by_language:
        raise ValueError("Coding problem must include runtime languages and starter code")
    testcases = _normalize_testcases(problem.get("testcases"), "testcases")
    hidden_tests = _normalize_testcases(problem.get("hidden_tests"), "hidden_tests")
    solver_key = str(problem.get("reference_solver_key") or "").strip()
    if solver_key not in {"longest_success_streak", "min_alternating_edits", "longest_distinct_window"}:
        raise ValueError(f"Unsupported reference solver key: {solver_key}")
    examples = problem.get("examples") if isinstance(problem.get("examples"), list) else []
    return {
        "title": title,
        "description": description,
        "method_name": method_name,
        "supported_languages": supported_languages,
        "starter_code_by_language": starter_code_by_language,
        "starter_code": starter_code_by_language[supported_languages[0]],
        "examples": [
            {
                "title": str(item.get("title") or f"Example {index + 1}"),
                "input": str(item.get("input") or ""),
                "output": str(item.get("output") or ""),
                "explanation": str(item.get("explanation") or ""),
            }
            for index, item in enumerate(examples)
            if isinstance(item, dict)
        ],
        "testcases": testcases,
        "hidden_tests": hidden_tests,
        "reference_solver_key": solver_key,
        "time_complexity": str(problem.get("time_complexity") or "Not specified"),
        "space_complexity": str(problem.get("space_complexity") or "Not specified"),
    }


def _normalize_testcases(value: Any, label: str) -> list[dict[str, str]]:
    value = _soft_normalize_testcases(value)
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    normalized = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"{label} item {index + 1} is invalid")
        raw_input = item.get("input")
        raw_output = item.get("output")
        if raw_input is None or raw_output is None:
            raise ValueError(f"{label} item {index + 1} must include input and output")
        normalized.append(
            {
                "label": str(item.get("label") or f"Case {index + 1}"),
                "input_label": str(item.get("input_label") or "input"),
                "input": str(raw_input),
                "output": str(raw_output),
            }
        )
    return normalized


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_answer_value(answer: Any, options: list[str]) -> str:
    raw = str(answer or "").strip()
    if raw in options:
        return raw
    lowered_map = {option.lower(): option for option in options}
    if raw.lower() in lowered_map:
        return lowered_map[raw.lower()]
    letter_map = {"a": 0, "b": 1, "c": 2, "d": 3}
    normalized_letter = raw.lower().replace(".", "").replace(")", "").strip()
    if normalized_letter in letter_map and letter_map[normalized_letter] < len(options):
        return options[letter_map[normalized_letter]]
    prefixed = re.match(r"^(option\s+)?([abcd])$", raw.strip(), flags=re.I)
    if prefixed:
        return options[letter_map[prefixed.group(2).lower()]]
    return raw


def _soft_normalize_question_payload(payload: Any, section_key: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    normalized = dict(payload)
    if "questions" not in normalized:
        for key in ("items", "mcqs", "quiz", "data"):
            if isinstance(normalized.get(key), list):
                normalized["questions"] = normalized.get(key)
                break
    if not normalized.get("section"):
        normalized["section"] = section_key.replace("_", " ").title()
    if isinstance(normalized.get("questions"), list):
        normalized["questions"] = [_soft_normalize_question_item(item, index) for index, item in enumerate(normalized["questions"])]
    return normalized


def _soft_normalize_question_item(item: Any, index: int) -> dict[str, Any] | Any:
    if not isinstance(item, dict):
        return item
    normalized = dict(item)
    if not normalized.get("question"):
        normalized["question"] = normalized.get("prompt") or normalized.get("text") or normalized.get("title") or ""
    if not normalized.get("passage"):
        normalized["passage"] = normalized.get("description") or normalized.get("context") or normalized.get("passage_text") or ""
    options = normalized.get("options")
    if not isinstance(options, list):
        for key in ("choices", "answers", "answer_options"):
            if isinstance(normalized.get(key), list):
                options = normalized.get(key)
                break
    normalized_options = _coerce_options(options)
    if normalized_options:
        normalized["options"] = normalized_options[:4]
    if not normalized.get("id"):
        normalized["id"] = f"question-{index + 1}"
    if normalized.get("explanation") is None:
        normalized["explanation"] = ""
    return normalized


def _coerce_options(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if isinstance(item, dict):
            option_text = item.get("text")
            if option_text is None:
                option_text = item.get("option")
            if option_text is None:
                option_text = item.get("label")
            if option_text is None and len(item) == 1:
                option_text = next(iter(item.values()))
            text = str(option_text or "").strip()
        else:
            text = str(item or "").strip()
        text = re.sub(r"^\s*(?:option\s+)?[A-D][\).\:\-]\s*", "", text, flags=re.I)
        if text:
            normalized.append(text)
    deduped: list[str] = []
    for text in normalized:
        if text not in deduped:
            deduped.append(text)
    return deduped


def _soft_normalize_coding_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    normalized = dict(payload)
    if "problems" not in normalized:
        for key in ("items", "coding_problems", "questions", "data"):
            if isinstance(normalized.get(key), list):
                normalized["problems"] = normalized.get(key)
                break
    if not normalized.get("section"):
        normalized["section"] = "Coding Section"
    if isinstance(normalized.get("problems"), list):
        normalized["problems"] = [_soft_normalize_coding_problem(item, []) for item in normalized["problems"]]
    return normalized


def _soft_normalize_coding_problem(problem: Any, runtime_supported: list[str]) -> dict[str, Any] | Any:
    if not isinstance(problem, dict):
        return problem
    normalized = dict(problem)
    if not normalized.get("title"):
        normalized["title"] = normalized.get("name") or normalized.get("question") or ""
    if not normalized.get("description"):
        normalized["description"] = normalized.get("statement") or normalized.get("prompt") or ""
    if not normalized.get("method_name"):
        normalized["method_name"] = normalized.get("function_name") or normalized.get("method") or "solution"
    if not isinstance(normalized.get("supported_languages"), list):
        language = str(normalized.get("language") or "").strip().lower()
        normalized["supported_languages"] = [language] if language else []
    if not isinstance(normalized.get("starter_code_by_language"), dict):
        starter_value = normalized.get("starter_code")
        starter_map = {}
        if isinstance(starter_value, dict):
            starter_map = {str(key): str(value) for key, value in starter_value.items() if str(value).strip()}
        elif str(starter_value or "").strip():
            languages = [item for item in _string_list(normalized.get("supported_languages")) if item]
            if not languages and runtime_supported:
                languages = runtime_supported[:1]
            if languages:
                starter_map[languages[0]] = str(starter_value)
        normalized["starter_code_by_language"] = starter_map
    if not normalized.get("reference_solver_key"):
        normalized["reference_solver_key"] = _infer_solver_key_from_text(
            f"{normalized.get('title', '')}\n{normalized.get('description', '')}"
        )
    if normalized.get("examples") is None:
        normalized["examples"] = []
    if not normalized.get("time_complexity"):
        normalized["time_complexity"] = "Not specified"
    if not normalized.get("space_complexity"):
        normalized["space_complexity"] = "Not specified"
    visible_tests = normalized.get("testcases")
    if visible_tests is None:
        visible_tests = normalized.get("visible_tests")
    normalized["testcases"] = _soft_normalize_testcases(visible_tests)
    normalized["hidden_tests"] = _soft_normalize_testcases(normalized.get("hidden_tests"))
    return normalized


def _soft_normalize_testcases(value: Any) -> list[dict[str, str]] | Any:
    if value is None:
        return []
    if not isinstance(value, list):
        return value
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if isinstance(item, dict):
            raw_input = item.get("input")
            if raw_input is None:
                raw_input = item.get("stdin")
            if raw_input is None:
                raw_input = item.get("in")
            raw_output = item.get("output")
            if raw_output is None:
                raw_output = item.get("expected")
            if raw_output is None:
                raw_output = item.get("out")
            if raw_input is None:
                continue
            normalized.append(
                {
                    "label": str(item.get("label") or item.get("name") or f"Case {index + 1}"),
                    "input_label": str(item.get("input_label") or "input"),
                    "input": str(raw_input),
                    "output": str("" if raw_output is None else raw_output),
                }
            )
            continue
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            normalized.append(
                {
                    "label": f"Case {index + 1}",
                    "input_label": "input",
                    "input": str(item[0]),
                    "output": str(item[1]),
                }
            )
    return normalized


def _infer_solver_key_from_text(text: str) -> str:
    lowered = str(text or "").lower()
    if any(token in lowered for token in ("distinct", "unique", "without repeating", "substring")):
        return "longest_distinct_window"
    if any(token in lowered for token in ("alternating", "binary", "flip", "edits")):
        return "min_alternating_edits"
    return "longest_success_streak"


def _infer_language_from_text(text: str) -> str | None:
    lowered = str(text or "").lower()
    markers = [
        ("java", ("java:", "system.out", "hashmap", "charat(", "public static void main")),
        ("python", ("python:", " print(", "def ", "len(", "append(", "elif ")),
        ("cpp", ("c++:", "cpp:", "cout", "std::", "vector<", "#include")),
        ("javascript", ("javascript:", "js:", "console.log", "const ", "let ", "===")),
    ]
    for language, hints in markers:
        if any(hint in lowered for hint in hints):
            return language
    return None
