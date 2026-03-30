from __future__ import annotations

import io
import json
import re
from collections import Counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen

import pdfplumber
import os
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

KNOWN_SKILLS = {
    "java": "Java",
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "react": "React",
    "spring": "Spring",
    "spring boot": "Spring Boot",
    "fastapi": "FastAPI",
    "machine learning": "Machine Learning",
    "ml": "Machine Learning",
    "sql": "SQL",
    "postgresql": "SQL",
    "mysql": "SQL",
    "scikit-learn": "Machine Learning",
    "tensorflow": "Machine Learning",
    "pytorch": "Machine Learning",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "redis": "Redis",
    "kafka": "Kafka",
    "angular": "Angular",
    "vue": "Vue",
    "node": "Node.js",
    "node.js": "Node.js",
    "express": "Express",
    "django": "Django",
    "flask": "Flask",
    "aws": "AWS",
    "azure": "Azure",
    "gcp": "GCP",
    "html": "HTML",
    "css": "CSS",
    "git": "Git",
    "github": "GitHub",
    "mongodb": "MongoDB",
    "oracle": "Oracle",
    "jdbc": "JDBC",
    "numpy": "NumPy",
    "pandas": "Pandas",
    "jupyter": "Jupyter",
    "android studio": "Android Studio",
    "vs code": "VS Code",
    "linux": "Linux",
    "core java": "Core Java",
    "c#": "C#",
    "c++": "C++",
    "go": "Go",
}

LANGUAGE_SKILLS = {
    "java": "Java",
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "jupyter notebook": "Machine Learning",
    "c#": "C#",
    "c++": "C++",
    "go": "Go",
}

GENERIC_SKILL_STOPWORDS = {
    "experience", "required", "requirements", "responsible", "responsibilities", "knowledge",
    "ability", "understanding", "strong", "good", "excellent", "working", "hands", "years",
    "year", "month", "months", "team", "teams", "project", "projects", "developer", "development",
    "design", "build", "building", "support", "testing", "communication", "leadership", "problem",
    "problems", "candidate", "role", "must", "should", "with", "for", "the", "and", "or",
    "worked", "work", "using", "use", "on", "skills", "skill", "technologies", "technology",
    "tools", "framework", "frameworks", "boot", "libraries", "library", "languages",
    "language", "database", "databases", "programming", "web technologies", "soft skills",
    "english", "hindi", "telugu", "teamwork", "patience", "time management", "kali",
}

GENERIC_SKILL_PREFIXES = (
    "programming",
    "libraries/frameworks",
    "libraries",
    "frameworks",
    "web technologies",
    "databases",
    "database",
    "tools/ technologies",
    "tools/technologies",
    "tools",
    "soft skills",
    "languages",
)

SKILL_SECTION_HEADERS = {
    "skills",
    "technical skills",
    "core competencies",
    "tech stack",
    "toolkit",
}

RESUME_SECTION_HEADERS = {
    "education",
    "projects",
    "experience",
    "work experience",
    "internship",
    "internships",
    "certifications",
    "certification",
    "workshops",
    "workshops and trainings",
    "trainings",
    "interests",
    "declaration",
    "summary",
    "professional summary",
    "professional experience",
    "achievements",
    "languages",
}


class ProfileParserError(Exception):
    pass




def http_json(url: str, *, method: str = "GET", headers=None, payload=None):
    body = None
    request_headers = dict(headers or {})

    github_token = os.getenv("GITHUB_TOKEN")
    if "api.github.com" in url and github_token:
        request_headers["Authorization"] = f"token {github_token}"

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    request_headers.setdefault("Accept", "application/json")
    request_headers.setdefault("User-Agent", "AITS-Profile-Parser/1.0")

    request = Request(url, data=body, method=method, headers=request_headers)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            if not raw.strip():
                return {}
            return json.loads(raw)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")

        if "rate limit" in detail.lower():
            raise ProfileParserError("GitHub rate limit exceeded")
        raise ProfileParserError(detail or exc.reason) from exc
    except URLError as exc:
        raise ProfileParserError(str(exc.reason)) from exc
    except json.JSONDecodeError as exc:
        raise ProfileParserError("Invalid JSON response from upstream profile source") from exc


def http_bytes(url: str, *, headers: dict[str, str] | None = None) -> bytes:
    request = Request(url, headers={"User-Agent": "AITS-Profile-Parser/1.0", **(headers or {})})
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise ProfileParserError(detail or exc.reason) from exc
    except URLError as exc:
        raise ProfileParserError(str(exc.reason)) from exc


def extract_github_username(github_url: str) -> str:
    github_url = github_url.strip()

    if not github_url.startswith("http"):
        github_url = "https://" + github_url

    parsed = urlparse(github_url)

    if "github.com" not in parsed.netloc:
        raise ProfileParserError("Invalid GitHub URL")

    parts = [part for part in parsed.path.split("/") if part]

    if not parts:
        raise ProfileParserError("GitHub username missing")

    return parts[0]


def extract_leetcode_username(leetcode_url: str) -> str:
    parsed = urlparse(leetcode_url.strip())
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        raise ProfileParserError("Invalid LeetCode profile URL")
    if parts[0] in {"u", "profile"} and len(parts) > 1:
        return parts[1]
    return parts[0]


def normalize_skill_name(raw: str) -> str | None:
    lowered = raw.strip().lower()
    if not lowered:
        return None
    return KNOWN_SKILLS.get(lowered)


def detect_skills_from_text(text: str) -> set[str]:
    lowered = text.lower()
    skills: set[str] = set()
    for token, skill in KNOWN_SKILLS.items():
        pattern = r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])"
        if re.search(pattern, lowered):
            skills.add(skill)
    skills.update(extract_generic_tech_terms(text))
    return skills


def strict_technical_skills(values: list[Any] | set[Any] | tuple[Any, ...]) -> list[str]:
    allowed = set(KNOWN_SKILLS.values())
    ordered: list[str] = []
    seen: set[str] = set()

    for value in values:
        text = str(value or "").strip()
        if not text or text not in allowed:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(text)

    return ordered


def normalize_generic_skill(raw: str) -> str | None:
    value = re.sub(r"\s+", " ", str(raw or "").strip(" ,.;:()[]{}")).strip()
    if not value:
        return None
    lowered = value.lower()
    for prefix in GENERIC_SKILL_PREFIXES:
        if lowered.startswith(prefix + " "):
            value = value[len(prefix):].strip(" ,.;:()[]{}")
            lowered = value.lower()
            break
    if not value:
        return None
    lowered = value.lower()
    if lowered in GENERIC_SKILL_STOPWORDS:
        return None
    if value.isdigit():
        return None
    if len(value) < 2:
        return None
    if len(value.split()) > 3:
        return None
    mapped = KNOWN_SKILLS.get(lowered)
    if mapped:
        return mapped
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9.+#/-]{1,24}", value):
        if value.islower():
            return value.title()
        return value
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9.+#/-]{1,24}(?: [A-Za-z][A-Za-z0-9.+#/-]{1,24}){1,2}", value):
        return " ".join(part if not part.islower() else part.title() for part in value.split())
    return None


def is_resume_section_header(line: str) -> bool:
    compact = re.sub(r"\s+", " ", str(line or "").strip(" :-|")).strip()
    if not compact:
        return False
    lowered = compact.lower()
    if lowered in RESUME_SECTION_HEADERS or lowered in SKILL_SECTION_HEADERS:
        return True
    if len(compact.split()) <= 4 and compact.upper() == compact and re.search(r"[A-Z]", compact):
        return True
    return False


def extract_skill_section_lines(text: str) -> list[str]:
    lines = [line.strip() for line in str(text or "").splitlines()]
    captured: list[str] = []
    inside_skills_section = False

    for line in lines:
        if not line:
            if inside_skills_section:
                captured.append("")
            continue

        lowered = line.lower().strip(" :-|")
        if lowered in SKILL_SECTION_HEADERS:
            inside_skills_section = True
            continue

        if inside_skills_section:
            if is_resume_section_header(line):
                break
            captured.append(line)
            continue

        if any(marker in lowered for marker in ("skills:", "technologies:", "tools:", "frameworks:", "stack:")):
            captured.append(line)

    return captured


def extract_generic_tech_terms(text: str) -> set[str]:
    content = "\n".join(extract_skill_section_lines(text))
    candidates: set[str] = set()
    if not content.strip():
        return candidates

    for line in content.splitlines():
        lowered = line.lower()
        if any(marker in lowered for marker in ("skills", "technology", "technologies", "stack", "tools", "framework")):
            for part in re.split(r"[:,|/]", line):
                for chunk in re.split(r",|;|•|-", part):
                    normalized = normalize_generic_skill(chunk)
                    if normalized:
                        candidates.add(normalized)
        else:
            for chunk in re.split(r",|;|•", line):
                normalized = normalize_generic_skill(chunk)
                if normalized:
                    candidates.add(normalized)

    return candidates


def github_analysis(github_url: str) -> dict[str, Any]:
    username = extract_github_username(github_url)
    profile = http_json(f"https://api.github.com/users/{quote(username)}")
    if not profile:
        raise ProfileParserError("GitHub API failed")

    if profile.get("message") == "Not Found":
        raise ProfileParserError("GitHub profile does not exist")

    if "rate limit" in str(profile.get("message", "")).lower():
        raise ProfileParserError("GitHub rate limit exceeded")

    repos = http_json(f"https://api.github.com/users/{quote(username)}/repos?per_page=100&sort=updated")
    if not isinstance(repos, list):
        repos = []

    repo_count = len(repos)
    stars = sum(int(repo.get("stargazers_count") or 0) for repo in repos)
    forks = sum(int(repo.get("forks_count") or 0) for repo in repos)
    complexity = 0
    commit_activity = 0
    languages_counter: Counter[str] = Counter()
    detected_skills: set[str] = set()

    for repo in repos[:10]:
        repo_name = str(repo.get("name") or "").strip()
        complexity += min(10, (int(repo.get("size") or 0) // 50) + int(bool(repo.get("has_issues"))) + int(bool(repo.get("has_wiki"))))
        repo_default_language = str(repo.get("language") or "").strip()
        if repo_default_language:
            languages_counter[repo_default_language] += 1
            normalized = LANGUAGE_SKILLS.get(repo_default_language.lower())
            if normalized:
                detected_skills.add(normalized)

        repo_text = " ".join(
            str(value or "")
            for value in [
                repo.get("name"),
                repo.get("description"),
                " ".join(repo.get("topics") or []),
            ]
        )
        detected_skills.update(detect_skills_from_text(repo_text))

        if repo_name:
            try:
                language_payload = http_json(
                    f"https://api.github.com/repos/{quote(username)}/{quote(repo_name)}/languages"
                )
            except ProfileParserError:
                language_payload = {}
            if isinstance(language_payload, dict):
                for language_name, bytes_used in language_payload.items():
                    languages_counter[str(language_name)] += int(bytes_used or 0) > 0
                    normalized = LANGUAGE_SKILLS.get(str(language_name).lower())
                    if normalized:
                        detected_skills.add(normalized)

            try:
                commit_payload = http_json(
                    f"https://api.github.com/repos/{quote(username)}/{quote(repo_name)}/stats/commit_activity"
                )
            except ProfileParserError:
                commit_payload = []
            if isinstance(commit_payload, list):
                commit_activity += sum(int(item.get("total") or 0) for item in commit_payload[-12:])

    language_diversity = len({name.lower() for name in languages_counter if name})
    github_score = min(
        100,
        int(
            repo_count * 2
            + stars
            + language_diversity * 3
            + min(commit_activity // 5, 20)
            + min(complexity, 20)
            + min(forks, 10)
        ),
    )

    return {
        "github_valid": True,
        "username": username,
        "repo_count": repo_count,
        "stars": stars,
        "forks": forks,
        "commit_activity": commit_activity,
        "languages": sorted({name for name in languages_counter if name}),
        "skills": sorted(detected_skills),
        "github_score": github_score,
    }


def leetcode_analysis(leetcode_url: str) -> dict[str, Any]:
    username = extract_leetcode_username(leetcode_url)
    payload = {
        "query": """
        query getUserProfile($username: String!) {
          matchedUser(username: $username) {
            username
            submitStats {
              acSubmissionNum {
                difficulty
                count
              }
            }
          }
        }
        """,
        "variables": {"username": username},
    }
    response = http_json(
        "https://leetcode.com/graphql",
        method="POST",
        headers={"Referer": "https://leetcode.com", "Origin": "https://leetcode.com"},
        payload=payload,
    )
    matched_user = ((response or {}).get("data") or {}).get("matchedUser")
    if not matched_user:
        raise ProfileParserError("LeetCode profile does not exist")

    solved = {"Easy": 0, "Medium": 0, "Hard": 0}
    for item in ((matched_user.get("submitStats") or {}).get("acSubmissionNum") or []):
        difficulty = str(item.get("difficulty") or "")
        if difficulty in solved:
            solved[difficulty] = int(item.get("count") or 0)

    leetcode_score = min(
        100,
        solved["Easy"] * 1 + solved["Medium"] * 3 + solved["Hard"] * 5,
    )

    return {
        "leetcode_valid": True,
        "username": username,
        "easy_solved": solved["Easy"],
        "medium_solved": solved["Medium"],
        "hard_solved": solved["Hard"],
        "leetcode_score": leetcode_score,
    }


def extract_drive_file_id(drive_url: str) -> str | None:
    parsed = urlparse(drive_url)
    parts = [part for part in parsed.path.split("/") if part]
    if "file" in parts and "d" in parts:
        try:
            return parts[parts.index("d") + 1]
        except Exception:
            return None
    query_id = parse_qs(parsed.query).get("id")
    return query_id[0] if query_id else None


def download_drive_pdf(drive_url: str) -> bytes:
    file_id = extract_drive_file_id(drive_url)
    if not file_id:
        raise ProfileParserError("Unsupported Google Drive link")
    base_url = f"https://drive.google.com/uc?{urlencode({'export': 'download', 'id': file_id})}"
    first_response = http_bytes(base_url)
    if first_response.startswith(b"%PDF"):
        return first_response

    html = first_response.decode("utf-8", errors="ignore")
    match = re.search(r"confirm=([0-9A-Za-z_]+)", html)
    if not match:
        raise ProfileParserError("Unable to download Google Drive file")
    confirmed_url = f"https://drive.google.com/uc?{urlencode({'export': 'download', 'confirm': match.group(1), 'id': file_id})}"
    second_response = http_bytes(confirmed_url)
    if not second_response.startswith(b"%PDF"):
        raise ProfileParserError("Google Drive file is not a PDF")
    return second_response


def extract_resume_text(*, resume_pdf_bytes: bytes | None, resume_drive_link: str | None) -> str:
    pdf_bytes = resume_pdf_bytes
    if pdf_bytes is None and resume_drive_link:
        pdf_bytes = download_drive_pdf(resume_drive_link)
    if pdf_bytes is None:
        raise ProfileParserError("Resume is required")
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = [(page.extract_text() or "") for page in pdf.pages]
    except Exception as exc:
        raise ProfileParserError(f"Unable to parse resume PDF: {exc}") from exc
    text = "\n".join(pages).strip()
    if not text:
        raise ProfileParserError("Resume text could not be extracted")
    return text


def extract_location_from_resume(resume_text: str) -> str:
    lines = [line.strip() for line in str(resume_text or "").splitlines() if line.strip()]
    for line in lines[:12]:
        compact = re.sub(r"\s+", " ", line)
        if re.search(r"\b[A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)*,\s*[A-Z]{2,}\b", compact):
            return compact
        if re.search(r"\b(remote|hybrid|onsite)\b", compact, re.IGNORECASE):
            return compact
    return ""


def resume_analysis(resume_text: str) -> dict[str, Any]:
    lowered = resume_text.lower()
    project_count = len(re.findall(r"\bprojects?\b", lowered))
    internship_count = len(re.findall(r"\bintern(ship|ships)?\b", lowered))
    skills = detect_skills_from_text(resume_text)
    if "mysql" in lowered or "postgres" in lowered or "sql" in lowered:
        skills.add("SQL")
    if "spring boot" in lowered:
        skills.add("Spring Boot")

    # Keep the resume score conservative: count only core known skills and cap
    # the contribution so the resume component stays separate from final evaluation.
    scored_skills = {skill for skill in skills if skill in set(KNOWN_SKILLS.values())}
    scored_skill_count = min(5, len(scored_skills))
    resume_score = min(
        100,
        project_count * 10 + scored_skill_count * 5 + internship_count * 10,
    )
    location = extract_location_from_resume(resume_text)

    return {
        "resume_score": resume_score,
        "project_count": project_count,
        "internship_experience": internship_count,
        "scored_skill_count": scored_skill_count,
        "skills": sorted(skills),
        "location": location,
    }


def analyze_candidate_profile(
    *,
    first_name: str,
    last_name: str,
    email: str,
    github_url: str,
    leetcode_url: str,
    resume_pdf_bytes: bytes | None = None,
    resume_drive_link: str | None = None,
) -> dict[str, Any]:
    github = github_analysis(github_url)
    leetcode = leetcode_analysis(leetcode_url)
    resume_text = extract_resume_text(resume_pdf_bytes=resume_pdf_bytes, resume_drive_link=resume_drive_link)
    resume = resume_analysis(resume_text)
    skills = strict_technical_skills(sorted(set(github["skills"]) | set(resume["skills"])))
    profile_score = round(
        0.33 * github["github_score"] +
        0.33 * leetcode["leetcode_score"] +
        0.33 * resume["resume_score"]
    )

    return {
        "candidate_name": f"{first_name.strip()} {last_name.strip()}".strip(),
        "candidate_email": email.strip().lower(),
        "github_valid": True,
        "leetcode_valid": True,
        "github_score": github["github_score"],
        "leetcode_score": leetcode["leetcode_score"],
        "resume_score": resume["resume_score"],
        "skills": skills,
        "profile_score": profile_score,
        "location": resume.get("location", ""),
        "details": {
            "github": {
                "repo_count": github["repo_count"],
                "stars": github["stars"],
                "forks": github["forks"],
                "commit_activity": github["commit_activity"],
                "languages": github["languages"],
            },
            "leetcode": {
                "easy_solved": leetcode["easy_solved"],
                "medium_solved": leetcode["medium_solved"],
                "hard_solved": leetcode["hard_solved"],
            },
            "resume": {
                "project_count": resume["project_count"],
                "internship_experience": resume["internship_experience"],
                "location": resume.get("location", ""),
            },
        },
    }
