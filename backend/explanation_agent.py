from __future__ import annotations

import re
from typing import Any

KNOWN_JD_SKILLS = {
    "java": "Java",
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "react": "React",
    "spring": "Spring",
    "spring boot": "Spring Boot",
    "fastapi": "FastAPI",
    "machine learning": "Machine Learning",
    "sql": "SQL",
    "mysql": "SQL",
    "postgresql": "SQL",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "aws": "AWS",
    "azure": "Azure",
    "gcp": "GCP",
    "html": "HTML",
    "css": "CSS",
    "node": "Node.js",
    "node.js": "Node.js",
    "express": "Express",
    "django": "Django",
    "flask": "Flask",
    "git": "Git",
}

SKILL_ALIASES = {
    "spring boot": {"spring"},
    "postgresql": {"sql"},
    "mysql": {"sql"},
    "node.js": {"node"},
}

GOOD_TO_HAVE_HINTS = (
    "good to have",
    "nice to have",
    "preferred",
    "bonus",
    "plus",
)


def _clean_skill(skill: Any) -> str:
    value = str(skill or "").strip()
    value = re.sub(r"\s*\(.*?\)\s*", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _normalize_list(skills: list[Any] | tuple[Any, ...] | set[Any]) -> list[str]:
    cleaned = []
    seen = set()
    for skill in skills or []:
        value = _clean_skill(skill)
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(value)
    return cleaned


def _extract_skills(text: str) -> list[str]:
    lowered = str(text or "").lower()
    found = []
    seen = set()
    for token, skill in sorted(KNOWN_JD_SKILLS.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])"
        if re.search(pattern, lowered) and skill.lower() not in seen:
            seen.add(skill.lower())
            found.append(skill)
    return found


def _collapse_overlapping_skills(skills: list[str]) -> list[str]:
    normalized = _normalize_list(skills)
    skill_keys = {item.lower() for item in normalized}
    collapsed = []
    for skill in normalized:
        key = skill.lower()
        if key == "spring" and "spring boot" in skill_keys:
            continue
        if key == "sql" and ("mysql" in skill_keys or "postgresql" in skill_keys):
            continue
        if key == "node.js" and "node" in skill_keys:
            continue
        collapsed.append(skill)
    return collapsed


def _skill_variants(skill: str) -> set[str]:
    key = _clean_skill(skill).lower()
    variants = {key}
    for alias, implied in SKILL_ALIASES.items():
        if key == alias:
            variants.update(implied)
        if key in implied:
            variants.add(alias)
    return variants


def build_jd_match(jd_text: str, candidate_skills: list[Any]) -> dict[str, Any]:
    text = str(jd_text or "")
    lowered = text.lower()
    candidate = _collapse_overlapping_skills(_normalize_list(candidate_skills))
    candidate_keys = set()
    for item in candidate:
        candidate_keys.update(_skill_variants(item))

    good_section = ""
    for hint in GOOD_TO_HAVE_HINTS:
        if hint in lowered:
            good_section = lowered.split(hint, 1)[1]
            break

    good_skills = _collapse_overlapping_skills(_extract_skills(good_section) if good_section else [])
    all_skills = _collapse_overlapping_skills(_extract_skills(text))
    must_skills = [skill for skill in all_skills if skill not in good_skills]

    matched_must = [skill for skill in must_skills if _clean_skill(skill).lower() in candidate_keys]
    missing_must = [skill for skill in must_skills if _clean_skill(skill).lower() not in candidate_keys]
    matched_good = [skill for skill in good_skills if _clean_skill(skill).lower() in candidate_keys]
    missing_good = [skill for skill in good_skills if _clean_skill(skill).lower() not in candidate_keys]

    must_coverage = round((len(matched_must) / len(must_skills)) * 100, 2) if must_skills else 100.0
    good_coverage = round((len(matched_good) / len(good_skills)) * 100, 2) if good_skills else 0.0

    return {
        "must_have": must_skills,
        "good_to_have": good_skills,
        "must_match": matched_must,
        "good_match": matched_good,
        "missing_must": missing_must,
        "missing_good": missing_good,
        "must_coverage": must_coverage,
        "good_coverage": good_coverage,
    }


def generate_explanation(match_result: dict[str, Any], final_score: float) -> str:
    matched_must = _normalize_list(match_result.get("must_match", []))
    matched_good = _normalize_list(match_result.get("good_match", []))

    if not matched_must and match_result.get("must_have"):
        decision = "Not suitable"
        summary = "No critical must-have skill was matched."
    elif final_score >= 75:
        decision = "Strong fit"
        summary = "Strong alignment with required skills and overall role expectations."
    elif final_score >= 45:
        decision = "Moderate fit"
        summary = "Partial alignment; suitable foundation with some important gaps."
    else:
        decision = "Weak fit"
        summary = "Multiple core skill gaps reduce fit for this role."

    must_text = ", ".join(matched_must) if matched_must else "None"
    good_text = ", ".join(matched_good) if matched_good else "None"

    return (
        f"Final Decision: {decision}\n"
        f"Matched Must-Have Skills: {must_text}\n"
        f"Matched Good-to-Have Skills: {good_text}\n"
        f"Summary: {summary}"
    )


def generate_ai_recommendation(
    *,
    jd_match: dict[str, Any],
    profile_score: float,
    exam_score: float,
    exam_max: float,
    interview_rating: int | None,
    interview_feedback: str,
    admin_result: str | None,
) -> dict[str, Any]:
    exam_percent = round((exam_score / exam_max) * 100, 2) if exam_max and exam_max > 0 else 0.0
    interview_component = float(interview_rating * 20) if interview_rating else 0.0
    must_coverage = float(jd_match.get("must_coverage", 0.0) or 0.0)
    has_interview_signal = bool(interview_rating or str(interview_feedback or "").strip() or str(admin_result or "").strip())

    feedback_text = str(interview_feedback or "").lower()
    positive_hits = sum(1 for token in ("strong", "good", "clear", "confident", "excellent", "solid") if token in feedback_text)
    negative_hits = sum(1 for token in ("weak", "poor", "lack", "concern", "confused", "struggle") if token in feedback_text)
    feedback_bias = max(-15.0, min(15.0, (positive_hits - negative_hits) * 4.0))

    composite = (0.4 * profile_score) + (0.25 * exam_percent) + (0.2 * interview_component) + (0.15 * must_coverage) + feedback_bias
    composite = round(max(0.0, min(100.0, composite)), 2)

    if not has_interview_signal:
        explanation = (
            "AI Recommendation: Pending\n"
            f"JD Match Coverage: {must_coverage:.0f}% must-have, {float(jd_match.get('good_coverage', 0.0) or 0.0):.0f}% good-to-have\n"
            f"Profile Score: {profile_score:.2f}\n"
            f"Assessment Score: {exam_percent:.2f}\n"
            "Awaiting interview feedback to produce the final AI decision."
        )
        return {"decision": "Pending", "score": composite, "explanation": explanation}

    normalized_admin_result = str(admin_result or "").strip().title()
    if normalized_admin_result == "Rejected":
        decision = "Rejected"
    elif must_coverage < 35 and jd_match.get("must_have"):
        decision = "Rejected"
    elif composite >= 68 and (interview_rating or 0) >= 3:
        decision = "Selected"
    elif normalized_admin_result == "Selected" and composite >= 55:
        decision = "Selected"
    else:
        decision = "Rejected"

    matched_must = _normalize_list(jd_match.get("must_match", []))
    missing_must = _normalize_list(jd_match.get("missing_must", []))
    strengths = []
    if matched_must:
        strengths.append(f"matched must-have skills: {', '.join(matched_must[:4])}")
    if exam_percent:
        strengths.append(f"assessment score {exam_percent:.0f}%")
    if interview_rating:
        strengths.append(f"interview rating {interview_rating}/5")

    concerns = []
    if missing_must:
        concerns.append(f"missing must-have skills: {', '.join(missing_must[:4])}")
    if exam_percent and exam_percent < 50:
        concerns.append("low assessment performance")
    if interview_rating and interview_rating < 3:
        concerns.append("weak interview rating")
    if negative_hits > positive_hits:
        concerns.append("admin feedback contains more concerns than strengths")

    strengths_text = "; ".join(strengths) if strengths else "limited positive signals"
    concerns_text = "; ".join(concerns) if concerns else "no major risk flags noted"
    explanation = (
        f"AI Recommendation: {decision}\n"
        f"JD Match Coverage: {must_coverage:.0f}% must-have, {float(jd_match.get('good_coverage', 0.0) or 0.0):.0f}% good-to-have\n"
        f"Strengths: {strengths_text}\n"
        f"Concerns: {concerns_text}\n"
        f"Composite Score: {composite:.2f}"
    )
    return {"decision": decision, "score": composite, "explanation": explanation}
