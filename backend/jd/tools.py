import requests
import json

GROQ_API_KEY = "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"
API_URL = "https://api.groq.com/openai/v1/chat/completions"


def call_llm(prompt):

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"}
    }

    r = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json=payload
    )

    response = r.json()

    print("LLM RESPONSE:", response)

    if "choices" not in response:
        return "{}"

    return response["choices"][0]["message"]["content"]


def normalize_skill(skill):

    mapping = {
        "object-oriented design": "Object-Oriented Programming",
        "apis": "REST API",
        "api": "REST API",
        "cloud computing": "Cloud",
        "containerization": "Docker",
        "source code control": "Git"
    }

    skill_lower = skill.lower()

    if skill_lower in mapping:
        return mapping[skill_lower]

    return skill.title()


def clean_skills(skills):

    remove_words = [
        "Coding Standards",
        "Code Reviews",
        "Build Processes",
        "Testing",
        "Operations",
        "Software Engineering",
        "Computer Science",
        "Computer Engineering",
        "Source Code"
    ]

    cleaned = []

    for s in skills:

        if s in remove_words:
            continue

        s = normalize_skill(s)

        if s not in cleaned:
            cleaned.append(s)

    return cleaned


def extract_job_info(jd):

    prompt = f"""
Analyze the following job description and extract structured job information.

Return JSON with this exact structure:

{{
 "role": "job title",
 "must_have_skills": ["skill1","skill2"],
 "good_to_have_skills": ["skill1","skill2"],
 "experience_required": "X years"
}}

Rules:
- Must-have skills are REQUIRED technical skills
- Good-to-have skills are OPTIONAL technical skills
- Only include real technical skills (languages, frameworks, architecture, tools)
- Do NOT include education fields
- Do NOT include generic phrases
- Infer seniority from experience if possible

Job Description:
{jd}
"""

    result = call_llm(prompt)

    try:
        data = json.loads(result)
    except:
        data = {}

    role = data.get("role", "Not Specified")

    must_skills = clean_skills(data.get("must_have_skills", []))
    good_skills = clean_skills(data.get("good_to_have_skills", []))

    experience = data.get("experience_required", "Not Specified")

    return {
        "role": role,
        "must_have_skills": must_skills,
        "good_to_have_skills": good_skills,
        "experience_required": experience
    }