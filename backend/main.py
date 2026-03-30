from __future__ import annotations

import ast
import json
import os
import random
import secrets
import smtplib
import shutil
import base64
import hashlib
import hmac
import re
import threading
import time
import urllib.request
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import uuid4
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import JSON, Column, delete, text
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlmodel import Field, SQLModel, Session, create_engine, select

if __package__:
    from .judge import judge_code, runtime_availability
    from .nvidia_llm import request_nvidia_chat
    from .proctoring import check_proctoring_frame, get_engine
    from .reference_solvers import solve_reference_case
    from .profile_parser_agent import ProfileParserError, analyze_candidate_profile, strict_technical_skills
    from .explanation_agent import build_jd_match, generate_ai_recommendation, generate_explanation
    from .jd.router import router as jd_router
else:
    from judge import judge_code, runtime_availability
    from nvidia_llm import request_nvidia_chat
    from proctoring import check_proctoring_frame, get_engine
    from reference_solvers import solve_reference_case
    from profile_parser_agent import ProfileParserError, analyze_candidate_profile, strict_technical_skills
    from explanation_agent import build_jd_match, generate_ai_recommendation, generate_explanation
    from jd.router import router as jd_router
# AI generation is no longer part of the live assessment flow.

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


# ---------- Config ----------
APP_HOST = os.getenv("APP_HOST", "localhost")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres.xxorkvmykzufcjwlmdgj:Hackminds%4002@aws-1-ap-south-1.pooler.supabase.com:6543/postgres?sslmode=require",
)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
JWT_SECRET = os.getenv("JWT_SECRET", "3f2e5a8c9d1b4f7a6e0c2d9f1a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0")
JWT_ALGO = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "720"))
GOOGLE_CLIENT_ID = os.getenv(
    "GOOGLE_CLIENT_ID",
    "1000371775549-m8q7ll6e67uq63a1u23cveu11u04uc3r.apps.googleusercontent.com",
)

GMAIL_SMTP_HOST = os.getenv("GMAIL_SMTP_HOST", "smtp.gmail.com")
GMAIL_SMTP_PORT = int(os.getenv("GMAIL_SMTP_PORT", "587"))
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "AITS Hiring")
PROCTORING_VIOLATION_LIMIT = int(os.getenv("PROCTORING_VIOLATION_LIMIT", "10"))

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, connect_args={"prepare_threshold": None})
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt_sha256", "bcrypt"],
    deprecated="auto",
)
security = HTTPBearer()
PASSWORD_ITERATIONS = 390000


# ---------- Models ----------
class Admin(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    full_name: str
    email: str = Field(index=True, unique=True)
    password_hash: Optional[str] = None
    google_sub: Optional[str] = Field(default=None, index=True)
    company_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AdminPasswordResetToken(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    admin_id: str = Field(foreign_key="admin.id", index=True)
    token: str = Field(index=True, unique=True)
    expires_at: datetime
    used: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Section(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    key: str = Field(index=True, unique=True)
    title: str
    section_type: str  # mcq | verbal | coding
    duration_minutes: int = 10
    description: str


class Assessment(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    name: str
    slug: str = Field(index=True, unique=True)
    admin_id: Optional[str] = Field(default=None, foreign_key="admin.id")
    jd_text: str = ""
    generation_status: str = Field(default="ready", index=True)
    generation_error: str = ""
    generated_sections_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_finished: bool = False


class AssessmentSection(SQLModel, table=True):
    assessment_id: str = Field(foreign_key="assessment.id", primary_key=True)
    section_id: str = Field(foreign_key="section.id", primary_key=True)
    config_json: str = "{}"


class GenerationJob(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    assessment_id: str = Field(foreign_key="assessment.id", index=True)
    admin_id: str = Field(index=True)
    section_key: str = Field(index=True)
    batch_index: int = 0
    batch_size: int = 0
    status: str = Field(default="pending", index=True)  # pending | processing | completed | failed | skipped
    attempts: int = 0
    available_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    payload_json: str = "{}"
    last_error: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class QuestionHistory(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    admin_id: str = Field(index=True)
    assessment_id: str = Field(index=True)
    section_key: str = Field(index=True)
    entry_type: str = Field(default="question", index=True)  # question | coding
    raw_text: str
    normalized_text: str = Field(index=True)
    content_hash: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Invite(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    assessment_id: str = Field(foreign_key="assessment.id")
    full_name: str
    email: str
    token: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Candidate(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    invite_id: str = Field(foreign_key="invite.id", index=True)
    full_name: str
    email: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CandidateProfileAnalysis(SQLModel, table=True):
    __tablename__ = "candidate_profile_analysis"

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    exam_invite_id: str = Field(index=True, unique=True)
    candidate_email: str = Field(index=True)
    candidate_name: str
    github_score: float = 0
    leetcode_score: float = 0
    resume_score: float = 0
    profile_score: float = 0
    skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    summary_json: str = "{}"
    raw_response_json: str = "{}"
    parser_status: str = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class InterviewSchedule(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    assessment_id: str = Field(foreign_key="assessment.id", index=True)
    invite_id: str = Field(foreign_key="invite.id", index=True)
    candidate_id: Optional[str] = Field(default=None, foreign_key="candidate.id", index=True)
    candidate_name: str
    candidate_email: str = Field(index=True)
    interviewer_email: str = Field(index=True)
    interview_datetime: datetime
    duration: int = 30
    meeting_id: str = Field(index=True, unique=True)
    meeting_link: str
    status: str = "Scheduled"
    rating: Optional[int] = None
    feedback: str = ""
    ai_summary: str = ""
    result: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class Attempt(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    candidate_id: str = Field(foreign_key="candidate.id", index=True)
    section_id: str = Field(foreign_key="section.id", index=True)
    status: str = "not_started"  # not_started | in_progress | completed
    agreed_rules: bool = False
    score: float = 0
    max_score: float = 0
    started_at: Optional[datetime] = None
    deadline_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    answers_json: str = "{}"
    code_submission: str = ""
    violation_count: int = 0
    cheating_flag: bool = False
    proctor_event_counts_json: str = "{}"



class SignupPayload(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    company_name: str


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthPayload(BaseModel):
    credential: str


class AdminSignupPayload(BaseModel):
    full_name: Optional[str] = None
    email: EmailStr
    password: str
    confirm_password: str


class ForgotPasswordPayload(BaseModel):
    email: EmailStr


class ResetPasswordPayload(BaseModel):
    token: str
    password: str
    confirm_password: str


class CompanyProfilePayload(BaseModel):
    company_name: str


class AssignSectionsPayload(BaseModel):
    section_ids: list[str]


class McqSectionConfigPayload(BaseModel):
    questions: list[dict[str, Any]]
    display_count: Optional[int] = None


class McqAIGeneratePayload(BaseModel):
    count: int = 5
    difficulty: str = "MEDIUM"


class VerbalSectionConfigPayload(BaseModel):
    config: dict[str, Any]


class VerbalAIGeneratePayload(BaseModel):
    kind: str
    transcript: Optional[str] = None
    count: int = 1


class InvitePayload(BaseModel):
    full_name: str
    email: EmailStr


class InterviewSchedulePayload(BaseModel):
    candidate_name: str
    candidate_email: EmailStr
    interviewer_email: EmailStr
    interview_datetime: str
    duration: int
    assessment_id: Optional[str] = None
    invite_id: Optional[str] = None


class InterviewFeedbackPayload(BaseModel):
    candidate_email: EmailStr
    rating: int
    feedback: str
    result: Optional[str] = None
    interview_id: Optional[str] = None
    invite_id: Optional[str] = None


class InterviewDecisionPayload(BaseModel):
    candidate_email: EmailStr
    decision: str
    interview_id: Optional[str] = None
    invite_id: Optional[str] = None


class CandidateSignupPayload(BaseModel):
    full_name: str
    email: EmailStr


class StartSectionPayload(BaseModel):
    agreed_rules: bool


class SubmitMcqPayload(BaseModel):
    answers: dict[str, str]


class SubmitCodingPayload(BaseModel):
    problem_states: list[dict[str, Any]] = []


class SubmitVerbalPayload(BaseModel):
    listening_answers: dict[str, str] = {}
    speaking_responses: list[dict[str, Any]] = []
    writing_responses: list[dict[str, Any]] = []
    drag_drop_answers: dict[str, list[str]] = {}


class RunCodingPayload(BaseModel):
    problem_index: int = 0
    code: str
    language: str = "java"
    testcases: list[dict[str, Any]]


class SaveMcqProgressPayload(BaseModel):
    answers: dict[str, str]
    current_index: int = 0


class SaveCodingProgressPayload(BaseModel):
    problem_states: list[dict[str, Any]] = []
    active_problem: int = 0


class ProctorEventPayload(BaseModel):
    candidate_id: Optional[str] = None
    section_id: Optional[str] = None
    event: str
    detail: Optional[str] = None


class ProctorPayload(BaseModel):
    image: Optional[str] = None
    frame: Optional[str] = None
    candidate_id: Optional[str] = None


# ---------- Static Question Bank ----------
MCQ_BANK: dict[str, list[dict[str, Any]]] = {
    "verbal_reasoning": [
        {
            "id": "q1",
            "passage": "Meryl Streep is considered by many one of the greatest actors. She has said her ideal director gives her complete artistic control.",
            "question": "She prefers directors who allow freedom in interpreting roles.",
            "options": ["True", "False", "Cannot say"],
            "answer": "True",
        },
        {
            "id": "q2",
            "passage": "The note says all shortlisted candidates receive an email within 24 hours.",
            "question": "Every applicant receives an email within 24 hours.",
            "options": ["True", "False", "Cannot say"],
            "answer": "False",
        },
    ],
    "numerical_reasoning": [
        {
            "id": "n1",
            "passage": "A team solved 48 tickets on Monday and 60 on Tuesday.",
            "question": "What is the percentage increase from Monday to Tuesday?",
            "options": ["20%", "25%", "30%", "40%"],
            "answer": "25%",
        },
        {
            "id": "n2",
            "passage": "Revenue was 12 lakh and costs were 8 lakh.",
            "question": "Profit margin on revenue is:",
            "options": ["25%", "33.33%", "40%", "50%"],
            "answer": "33.33%",
        },
    ],
    "abstract_reasoning": [
        {
            "id": "a1",
            "passage": "Pattern: triangle, square, pentagon, hexagon",
            "question": "Which comes next?",
            "options": ["Heptagon", "Octagon", "Circle", "Rectangle"],
            "answer": "Heptagon",
        },
        {
            "id": "a2",
            "passage": "Series: 2, 6, 12, 20",
            "question": "Next number is:",
            "options": ["28", "30", "32", "36"],
            "answer": "30",
        },
    ],
}

CODING_PROMPTS: dict[str, dict[str, Any]] = {
    "coding_section": {
        "title": "Longest Substring Without Repeating Characters",
        "difficulty": "Medium",
        "description": "Given a string s, find the length of the longest substring without duplicate characters.",
        "starter_code": (
            "class Solution {\n"
            "    public int lengthOfLongestSubstring(String s) {\n"
            "        \n"
            "    }\n"
            "}\n"
        ),
        "constraints": "0 <= s.length <= 50000",
        "sample_input": '"abcabcbb"',
        "sample_output": "3",
        "examples": [
            {
                "title": "Example 1",
                "input": 's = "abcabcbb"',
                "output": "3",
                "explanation": 'The answer is "abc", with the length of 3.',
            },
            {
                "title": "Example 2",
                "input": 's = "bbbbb"',
                "output": "1",
                "explanation": 'The answer is "b", with the length of 1.',
            },
            {
                "title": "Example 3",
                "input": 's = "pwwkew"',
                "output": "3",
                "explanation": 'The answer is "wke", with the length of 3.',
            },
        ],
        "testcases": [
            {"label": "Case 1", "input_label": "s", "input": '"abcabcbb"', "output": "3"},
            {"label": "Case 2", "input_label": "s", "input": '"bbbbb"', "output": "1"},
            {"label": "Case 3", "input_label": "s", "input": '"pwwkew"', "output": "3"},
        ],
        "hidden_tests": [
            {"input": '" "', "output": "1"},
            {"input": '""', "output": "0"},
        ],
        "method_name": "lengthOfLongestSubstring",
        "reference_solver_key": "longest_substring_without_repeating_characters",
    }
}

DEFAULT_CODING_LANGUAGES = [
    "java",
    "python",
    "cpp",
    "javascript",
    "typescript",
    "c",
    "csharp",
    "go",
]


def coding_problem_signature(reference_solver_key: str) -> dict[str, Any]:
    normalized = str(reference_solver_key or "").strip().lower()
    if normalized in {
        "longest_substring_without_repeating_characters",
        "longest_success_streak",
        "min_alternating_edits",
        "longest_distinct_window",
    }:
        return {
            "java_args": "String s",
            "python_args": "self, s: str",
            "cpp_args": "string s",
            "javascript_args": "s",
            "typescript_args": "s: string",
            "c_args": "char s[]",
            "csharp_args": "string s",
            "go_args": "s string",
            "return_type_java": "int",
            "return_type_cpp": "int",
            "return_type_typescript": "number",
            "return_type_c": "int",
            "return_type_csharp": "int",
            "return_type_go": "int",
            "default_return": "0",
        }
    if normalized == "trapping_rain_water":
        return {
            "java_args": "int[] height",
            "python_args": "self, height: list[int]",
            "cpp_args": "vector<int>& height",
            "javascript_args": "height",
            "typescript_args": "height: number[]",
            "c_args": "int height[], int heightSize",
            "csharp_args": "int[] height",
            "go_args": "height []int",
            "return_type_java": "int",
            "return_type_cpp": "int",
            "return_type_typescript": "number",
            "return_type_c": "int",
            "return_type_csharp": "int",
            "return_type_go": "int",
            "default_return": "0",
        }
    if normalized == "remove_element_count":
        return {
            "java_args": "int[] nums, int val",
            "python_args": "self, nums: list[int], val: int",
            "cpp_args": "vector<int>& nums, int val",
            "javascript_args": "nums, val",
            "typescript_args": "nums: number[], val: number",
            "c_args": "int nums[], int numsSize, int val",
            "csharp_args": "int[] nums, int val",
            "go_args": "nums []int, val int",
            "return_type_java": "int",
            "return_type_cpp": "int",
            "return_type_typescript": "number",
            "return_type_c": "int",
            "return_type_csharp": "int",
            "return_type_go": "int",
            "default_return": "0",
        }
    if normalized == "palindrome_number":
        return {
            "java_args": "int x",
            "python_args": "self, x: int",
            "cpp_args": "int x",
            "javascript_args": "x",
            "typescript_args": "x: number",
            "c_args": "int x",
            "csharp_args": "int x",
            "go_args": "x int",
            "return_type_java": "boolean",
            "return_type_cpp": "bool",
            "return_type_typescript": "boolean",
            "return_type_c": "bool",
            "return_type_csharp": "bool",
            "return_type_go": "bool",
            "default_return": "false",
        }
    return {
        "java_args": "String input",
        "python_args": "self, input_data",
        "cpp_args": "string input",
        "javascript_args": "input",
        "typescript_args": "input: unknown",
        "c_args": "char input[]",
        "csharp_args": "string input",
        "go_args": "input string",
        "return_type_java": "int",
        "return_type_cpp": "int",
        "return_type_typescript": "number",
        "return_type_c": "int",
        "return_type_csharp": "int",
        "return_type_go": "int",
        "default_return": "0",
    }


def coding_starter_template(language: str, method_name: str, reference_solver_key: str = "") -> str:
    normalized = str(language or "").strip().lower()
    safe_method = re.sub(r"[^a-zA-Z0-9_]", "", str(method_name or "solution")) or "solution"
    signature = coding_problem_signature(reference_solver_key)
    default_return = signature["default_return"]
    if normalized == "java":
        return (
            "class Solution {\n"
            f"    public {signature['return_type_java']} {safe_method}({signature['java_args']}) {{\n"
            f"        return {default_return};\n"
            "    }\n"
            "}\n"
        )
    if normalized == "python":
        return (
            "class Solution:\n"
            f"    def {safe_method}({signature['python_args']}):\n"
            f"        return {default_return}\n"
        )
    if normalized == "cpp":
        return (
            "#include <string>\n#include <vector>\nusing namespace std;\n\n"
            "class Solution {\n"
            "public:\n"
            f"    {signature['return_type_cpp']} {safe_method}({signature['cpp_args']}) {{\n"
            f"        return {default_return};\n"
            "    }\n"
            "};\n"
        )
    if normalized == "javascript":
        return (
            "class Solution {\n"
            f"  {safe_method}({signature['javascript_args']}) {{\n"
            f"    return {default_return};\n"
            "  }\n"
            "}\n"
        )
    if normalized == "typescript":
        return (
            "class Solution {\n"
            f"  {safe_method}({signature['typescript_args']}): {signature['return_type_typescript']} {{\n"
            f"    return {default_return};\n"
            "  }\n"
            "}\n"
        )
    if normalized == "c":
        return (
            "#include <stdbool.h>\n#include <string.h>\n\n"
            f"{signature['return_type_c']} {safe_method}({signature['c_args']}) {{\n"
            f"    return {default_return};\n"
            "}\n"
        )
    if normalized == "csharp":
        return (
            "public class Solution\n"
            "{\n"
            f"    public {signature['return_type_csharp']} {safe_method}({signature['csharp_args']})\n"
            "    {\n"
            f"        return {default_return};\n"
            "    }\n"
            "}\n"
        )
    if normalized == "go":
        return (
            "package main\n\n"
            f"func {safe_method}({signature['go_args']}) {signature['return_type_go']} {{\n"
            f"    return {default_return}\n"
            "}\n"
        )
    return ""

DEFAULT_SECTIONS = [
    {
        "key": "aptitude",
        "title": "Aptitude",
        "section_type": "mcq",
        "duration_minutes": 10,
        "description": "Solve aptitude and quantitative reasoning questions from the configured JSON bank.",
    },
    {
        "key": "verbal_ability",
        "title": "Verbal Ability",
        "section_type": "verbal",
        "duration_minutes": 25,
        "description": "Listening, speaking, writing, and drag-drop language assessment configured by the admin.",
    },
    {
        "key": "coding_section",
        "title": "Coding Section",
        "section_type": "coding",
        "duration_minutes": 60,
        "description": "Solve coding problems from the configured JSON bank.",
    },
    {
        "key": "coding_mcq_python",
        "title": "Coding MCQs - Python",
        "section_type": "mcq",
        "duration_minutes": 15,
        "description": "Solve Python-focused coding MCQs selected from the configured JSON bank.",
    },
    {
        "key": "coding_mcq_java",
        "title": "Coding MCQs - Java",
        "section_type": "mcq",
        "duration_minutes": 15,
        "description": "Solve Java-focused coding MCQs selected from the configured JSON bank.",
    },
]

ACTIVE_SECTION_KEYS = {item["key"] for item in DEFAULT_SECTIONS}
LEGACY_SECTION_KEYS = {"coding_problem_1", "coding_problem_2", "coding_problem_3"}
TEST_BANK_PATHS = {
    "aptitude": os.path.join(os.path.dirname(__file__), "..", "tests", "aptitude", "aptitude.json"),
    "verbal_ability": os.path.join(os.path.dirname(__file__), "..", "tests", "verbal", "verbal.json"),
    "coding_section": os.path.join(os.path.dirname(__file__), "..", "tests", "coding", "coding.json"),
    "coding_mcq_python": os.path.join(os.path.dirname(__file__), "..", "tests", "coding", "MCQs", "python.json"),
    "coding_mcq_java": os.path.join(os.path.dirname(__file__), "..", "tests", "coding", "MCQs", "java.json"),
}
TOPIC_BANK_DIRS = {
    "aptitude": os.path.join(os.path.dirname(__file__), "..", "tests", "aptitude", "topics"),
}
MEDIA_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads", "verbal_media")

RULES = [
    "Keep your camera ON throughout the test.",
    "Do not use mobile phones or external devices.",
    "Do not switch browser tabs/windows during the test.",
    "Do not take screenshots or use screen capture tools during the test.",
    "Do not seek external help, AI tools, or copy answers.",
    "Submit before the timer ends.",
]


# ---------- Helpers ----------
def slugify(name: str) -> str:
    return "-".join(name.lower().strip().split())


def is_valid_github_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() in {"github.com", "www.github.com"} and len(parsed.path.strip("/")) > 0


def is_valid_leetcode_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {"leetcode.com", "www.leetcode.com"}:
        return False
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return False
    if parts[0] in {"u", "profile"}:
        return len(parts) > 1
    return len(parts) == 1


def is_valid_google_drive_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() in {
        "drive.google.com",
        "docs.google.com",
        "www.drive.google.com",
        "www.docs.google.com",
    }


def infer_media_kind(media_url: str, media_type: str = "") -> str:
    value = str(media_url or "").strip().lower()
    normalized_type = str(media_type or "").strip().lower()
    if re.search(r"\.(mp3|wav|ogg|m4a|aac|flac|opus|weba)(\?.*)?$", value):
        return "audio"
    if re.search(r"\.(mp4|webm|mov|m4v|avi|mkv|ogv)(\?.*)?$", value):
        return "video"
    return "video" if normalized_type == "video" else "audio"


def validate_candidate_profile_inputs(
    first_name: str,
    last_name: str,
    github_url: str,
    leetcode_url: str,
    resume_drive_link: Optional[str],
    resume_file: Optional[UploadFile],
) -> None:
    if not first_name.strip():
        raise HTTPException(status_code=400, detail="First name is required")
    if not last_name.strip():
        raise HTTPException(status_code=400, detail="Last name is required")
    if not is_valid_github_url(github_url):
        raise HTTPException(status_code=400, detail="GitHub URL must be a valid github.com profile link")
    if not is_valid_leetcode_url(leetcode_url):
        raise HTTPException(status_code=400, detail="LeetCode URL must be a valid leetcode.com profile link")

    has_pdf = bool(resume_file and resume_file.filename)
    has_drive = bool((resume_drive_link or "").strip())
    if (has_pdf and has_drive) or (not has_pdf and not has_drive):
        raise HTTPException(status_code=400, detail="Provide either a resume PDF or a Google Drive link")

    if has_drive and not is_valid_google_drive_url(resume_drive_link or ""):
        raise HTTPException(status_code=400, detail="Resume link must be a valid Google Drive URL")

    if has_pdf:
        filename = (resume_file.filename or "").lower()
        if not filename.endswith(".pdf") or (resume_file.content_type and resume_file.content_type not in {"application/pdf", "application/octet-stream"}):
            raise HTTPException(status_code=400, detail="Resume upload must be a PDF file")


def get_session():
    with Session(engine) as session:
        yield session


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "pbkdf2_sha256${iterations}${salt}${digest}".format(
        iterations=PASSWORD_ITERATIONS,
        salt=base64.b64encode(salt).decode("ascii"),
        digest=base64.b64encode(derived).decode("ascii"),
    )


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt_b64, digest_b64 = password_hash.split("$", 3)
            salt = base64.b64decode(salt_b64.encode("ascii"))
            expected = base64.b64decode(digest_b64.encode("ascii"))
            actual = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                int(iterations),
            )
            return hmac.compare_digest(actual, expected)
        except Exception:
            return False
    try:
        return pwd_context.verify(password, password_hash)
    except Exception as error:
        print(f"[auth] password_verify_failed: {error}")
        return False


def create_token(admin: Admin) -> str:
    expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": admin.id, "email": admin.email, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: Session = Depends(get_session),
) -> Admin:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        admin_id = payload.get("sub")
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    admin = session.get(Admin, admin_id)
    if not admin:
        raise HTTPException(status_code=401, detail="Admin not found")
    return admin


def send_html_email(subject: str, to_email: str, html: str, *, from_name: str) -> dict[str, str | bool]:
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print(f"[mail-skipped] {subject} for {to_email}")
        return {
            "sent": False,
            "status": "skipped",
            "message": "Gmail not configured.",
        }

    msg = MIMEText(html, "html")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{GMAIL_ADDRESS}>"
    msg["To"] = to_email

    try:
        with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
        return {
            "sent": True,
            "status": "sent",
            "message": f"Email sent to {to_email}.",
        }
    except Exception as exc:
        print(f"[mail-failed] {subject} for {to_email}: {exc}")
        return {
            "sent": False,
            "status": "failed",
            "message": f"Email send failed: {exc}",
        }


def send_invite_email(to_name: str, to_email: str, assessment_name: str, link: str, company_name) -> dict[str, str | bool]:
    company_name = company_name.strip() or "AITS Hiring"
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print(f"[mail-skipped] Invite for {to_email}: {link}")
        return {
            "sent": False,
            "status": "skipped",
            "message": "Gmail not configured. Shareable link generated.",
        }

    html = f"""
    <div style="font-family: Arial, sans-serif; background-color: #f5f7fa; padding: 30px;">
    <div style="max-width: 620px; margin: auto; background: white; padding: 35px; border-radius: 14px; box-shadow: 0 8px 20px rgba(0,0,0,0.08);">
        <h2 style="text-align: center; color: #172648; margin-bottom: 5px;">{company_name}</h2>
        <p style="text-align: center; color: #666; margin-top: 0;">Powered by <strong>AITS Hiring</strong></p>

        <h3 style="color: #172648; margin-top: 30px;">Hello {to_name},</h3>

        <p style="font-size: 15px; color: #333; line-height: 1.7;">
        You have been invited by <strong>{company_name}</strong> to take an assessment for the role.
        </p>

        <div style="text-align: center; margin: 35px 0;">
        <a href="{link}" style="background: linear-gradient(135deg, #172648, #28407c); color: white; text-decoration: none; padding: 14px 24px; border-radius: 8px; font-weight: bold; display: inline-block;">
            Start Your Assessment
        </a>
        </div>

        <p style="font-size: 14px; color: #444; line-height: 1.6;">
        This link is unique to you. Please use it to complete the assessment at your convenience.
        </p>

        <hr style="margin: 20px 0;" />
        <p style="font-size: 13px; color: #999;">If the button does not work, copy and paste this link into your browser:</p>
        <p style="font-size: 13px; word-break: break-all; color: #555;">{link}</p>
        <p style="font-size: 14px; color: #333; margin-top: 30px;">Best regards,<br/><strong>{company_name}</strong></p>
        <p style="font-size: 12px; color: #aaa; text-align: center; margin-top: 30px;">This assessment is conducted via AITS Hiring Platform.</p>
    </div>
    </div>
    """
    msg = MIMEText(html, "html")
    msg["Subject"] = f"{assessment_name} | Powered by AITS Hiring"
    msg["From"] = f"{company_name} via AITS Hiring <{GMAIL_ADDRESS}>"
    msg["To"] = to_email

    try:
        with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
        return {
            "sent": True,
            "status": "sent",
            "message": f"Invitation email sent to {to_email}.",
        }
    except Exception as exc:
        print(f"[mail-failed] Invite for {to_email}: {exc}")
        return {
            "sent": False,
            "status": "failed",
            "message": f"Email send failed: {exc}",
        }


def send_password_reset_email(to_name: str, to_email: str, link: str) -> None:
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print(f"[mail-skipped] Password reset for {to_email}: {link}")
        return

    html = f"""
    <h2>Password Reset - AITS Hiring</h2>
    <p>Hi {to_name},</p>
    <p>Click the link below to reset your password:</p>
    <p><a href=\"{link}\">Reset password</a></p>
    <p>This link expires in 1 hour.</p>
    """
    msg = MIMEText(html, "html")
    msg["Subject"] = "Reset your AITS Hiring password"
    msg["From"] = f"{MAIL_FROM_NAME} <{GMAIL_ADDRESS}>"
    msg["To"] = to_email

    with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


def parse_interview_datetime(raw_value: str) -> datetime:
    value = (raw_value or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="Interview date and time are required")
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid interview date/time format") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    if parsed <= datetime.now():
        raise HTTPException(status_code=400, detail="Interview date/time must be in the future")
    return parsed


def interview_join_link(meeting_id: str) -> str:
    return f"{FRONTEND_URL.rstrip('/')}/interview/{meeting_id}"


def serialize_interview(interview: Optional[InterviewSchedule]) -> Optional[dict[str, Any]]:
    if not interview:
        return None
    return {
        "id": interview.id,
        "assessment_id": interview.assessment_id,
        "invite_id": interview.invite_id,
        "candidate_id": interview.candidate_id,
        "candidate_name": interview.candidate_name,
        "candidate_email": interview.candidate_email,
        "interviewer_email": interview.interviewer_email,
        "interview_datetime": interview.interview_datetime,
        "duration": interview.duration,
        "meeting_id": interview.meeting_id,
        "meeting_link": interview.meeting_link,
        "join_link": interview_join_link(interview.meeting_id),
        "status": interview.status,
        "rating": interview.rating,
        "feedback": interview.feedback,
        "ai_summary": interview.ai_summary,
        "result": interview.result,
        "created_at": interview.created_at,
        "updated_at": interview.updated_at,
        "completed_at": interview.completed_at,
    }


def latest_interview_record(session: Session, invite_id: str) -> Optional[InterviewSchedule]:
    return session.exec(
        select(InterviewSchedule)
        .where(InterviewSchedule.invite_id == invite_id)
        .order_by(InterviewSchedule.interview_datetime.desc(), InterviewSchedule.created_at.desc())
    ).first()


def send_interview_schedule_emails(
    *,
    candidate_name: str,
    candidate_email: str,
    interviewer_email: str,
    interview_datetime: datetime,
    duration: int,
    meeting_id: str,
    meeting_link: str,
) -> dict[str, dict[str, str | bool]]:
    join_link = interview_join_link(meeting_id)
    when_label = interview_datetime.strftime("%d %b %Y, %I:%M %p")

    candidate_html = f"""
    <div style="font-family: Arial, sans-serif; background:#f6f7fb; padding:24px;">
      <div style="max-width:640px; margin:auto; background:#fff; border-radius:12px; padding:28px;">
        <h2 style="margin:0 0 16px; color:#172648;">Interview Scheduled</h2>
        <p>Hello <strong>{candidate_name}</strong>,</p>
        <p>Your live interview has been scheduled.</p>
        <p><strong>Date & Time:</strong> {when_label}</p>
        <p><strong>Duration:</strong> {duration} minutes</p>
        <p><strong>Interviewer:</strong> {interviewer_email}</p>
        <p><a href="{join_link}" style="display:inline-block; background:#172648; color:#fff; text-decoration:none; padding:12px 18px; border-radius:8px;">Join Interview</a></p>
        <p style="font-size:13px; color:#666;">Fallback Jitsi room: {meeting_link}</p>
      </div>
    </div>
    """
    interviewer_html = f"""
    <div style="font-family: Arial, sans-serif; background:#f6f7fb; padding:24px;">
      <div style="max-width:640px; margin:auto; background:#fff; border-radius:12px; padding:28px;">
        <h2 style="margin:0 0 16px; color:#172648;">Interview Assigned</h2>
        <p>You have been assigned an interview.</p>
        <p><strong>Candidate:</strong> {candidate_name}</p>
        <p><strong>Candidate Email:</strong> {candidate_email}</p>
        <p><strong>Date & Time:</strong> {when_label}</p>
        <p><strong>Duration:</strong> {duration} minutes</p>
        <p><a href="{join_link}" style="display:inline-block; background:#172648; color:#fff; text-decoration:none; padding:12px 18px; border-radius:8px;">Join Interview</a></p>
        <p style="font-size:13px; color:#666;">Fallback Jitsi room: {meeting_link}</p>
      </div>
    </div>
    """
    return {
        "candidate": send_html_email(
            "Interview Scheduled",
            candidate_email,
            candidate_html,
            from_name=MAIL_FROM_NAME,
        ),
        "interviewer": send_html_email(
            "Interview Assigned",
            interviewer_email,
            interviewer_html,
            from_name=MAIL_FROM_NAME,
        ),
    }


def send_interview_decision_email(
    *,
    candidate_name: str,
    candidate_email: str,
    assessment_name: str,
    decision: str,
    company_name: str,
) -> dict[str, str | bool]:
    company = company_name.strip() or "AITS Hiring"
    normalized = (decision or "").strip().title()
    if normalized not in {"Selected", "Rejected"}:
        return {"sent": False, "status": "failed", "message": "Invalid decision."}

    if normalized == "Selected":
        title = "Congratulations! You have been selected"
        copy = (
            f"<p>Hi <strong>{candidate_name}</strong>,</p>"
            f"<p>We are pleased to let you know that you have been <strong>selected</strong> after the interview process for <strong>{assessment_name}</strong>.</p>"
            "<p>Our team will contact you with the next steps shortly.</p>"
        )
    else:
        title = "Interview update"
        copy = (
            f"<p>Hi <strong>{candidate_name}</strong>,</p>"
            f"<p>Thank you for taking part in the interview process for <strong>{assessment_name}</strong>.</p>"
            "<p>After careful review, we will not be moving forward with your application at this stage.</p>"
            "<p>We appreciate your time and interest.</p>"
        )

    html = f"""
    <div style="font-family: Arial, sans-serif; background:#f6f7fb; padding:24px;">
      <div style="max-width:640px; margin:auto; background:#fff; border-radius:12px; padding:28px;">
        <h2 style="margin:0 0 16px; color:#172648;">{title}</h2>
        {copy}
        <p style="margin-top:24px;">Regards,<br><strong>{company}</strong></p>
      </div>
    </div>
    """
    return send_html_email(
        f"{assessment_name} | {normalized}",
        candidate_email,
        html,
        from_name=f"{company} via AITS Hiring",
    )


def summarize_interview_feedback(*, candidate_name: str, rating: int, result: str, feedback: str) -> str:
    cleaned_feedback = feedback.strip()
    if not cleaned_feedback:
        return ""
    prompt = (
        "Summarize this interview feedback for an internal admin dashboard.\n"
        "Return plain text only.\n"
        "Keep it concise and under 90 words.\n"
        "Include overall impression, strengths, concerns, and recommendation.\n\n"
        f"Candidate: {candidate_name}\n"
        f"Rating: {rating}/5\n"
        f"Result: {result}\n"
        f"Feedback Notes:\n{cleaned_feedback}"
    )
    system_prompt = (
        "You are an expert hiring coordinator. Write a concise, factual interview summary. "
        "Do not invent details. Do not use markdown or bullet points."
    )
    try:
        return request_nvidia_chat(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=180,
            temperature=0.2,
            top_p=0.7,
        ).strip()
    except Exception:
        return ""


def normalize_mcq_answer(raw_answer: Any, options: list[str]) -> str:
    answer = str(raw_answer or "").strip()
    if not options:
        return answer
    if answer in options:
        return answer
    upper = answer.upper()
    letter_to_idx = {"A": 0, "B": 1, "C": 2, "D": 3}
    if upper in letter_to_idx and letter_to_idx[upper] < len(options):
        return options[letter_to_idx[upper]]
    if answer.isdigit():
        idx = int(answer) - 1
        if 0 <= idx < len(options):
            return options[idx]
    return options[0]


def infer_difficulty(question: str, passage: str) -> str:
    text = f"{question} {passage}".lower()
    hard_markers = ("except", "inference", "assumption", "evaluate", "derive", "pattern", "critical")
    medium_markers = ("which", "best", "most likely", "interpret", "reason")
    if len(text) > 260 or any(marker in text for marker in hard_markers):
        return "Hard"
    if len(text) > 120 or any(marker in text for marker in medium_markers):
        return "Medium"
    return "Easy"


def normalize_shared_media(raw: Any) -> dict[str, Any]:
    shared = raw if isinstance(raw, dict) else {}
    items_raw = shared.get("items") if isinstance(shared.get("items"), list) else []
    normalized_items: list[dict[str, Any]] = []
    for idx, item in enumerate(items_raw):
        if not isinstance(item, dict):
            continue
        question_ids_raw = item.get("question_ids") if isinstance(item.get("question_ids"), list) else []
        normalized_items.append(
            {
                "id": str(item.get("id") or f"media-{idx + 1}"),
                "audio": str(item.get("audio") or "").strip(),
                "video": str(item.get("video") or "").strip(),
                "scope": "selected" if str(item.get("scope") or "").strip().lower() == "selected" else "all",
                "question_ids": [str(value) for value in question_ids_raw if str(value).strip()],
            }
        )
    if not normalized_items:
        question_ids_raw = shared.get("question_ids") if isinstance(shared.get("question_ids"), list) else []
        legacy_audio = str(shared.get("audio") or "").strip()
        legacy_video = str(shared.get("video") or "").strip()
        if legacy_audio or legacy_video:
            normalized_items.append(
                {
                    "id": "media-1",
                    "audio": legacy_audio,
                    "video": legacy_video,
                    "scope": "selected" if str(shared.get("scope") or "").strip().lower() == "selected" else "all",
                    "question_ids": [str(value) for value in question_ids_raw if str(value).strip()],
                }
            )
    return {"items": normalized_items}


def shared_media_for_question(shared: dict[str, Any], question_id: str) -> dict[str, str]:
    normalized = normalize_shared_media(shared)
    audio = ""
    video = ""
    for item in normalized.get("items", []):
        if item.get("scope") == "selected":
            selected_ids = set(item.get("question_ids") or [])
            if question_id not in selected_ids:
                continue
        if not audio:
            audio = str(item.get("audio") or "")
        if not video:
            video = str(item.get("video") or "")
        if audio and video:
            break
    return {"audio": audio, "video": video}


def get_assessment_sections(session: Session, assessment_id: str) -> list[Section]:
    links = session.exec(
        select(AssessmentSection).where(AssessmentSection.assessment_id == assessment_id)
    ).all()
    for link in links:
        ensure_assessment_section_belongs_to_assessment(link, assessment_id)
    section_ids = [link.section_id for link in links]
    if not section_ids:
        return []
    sections = session.exec(select(Section).where(Section.id.in_(section_ids))).all()
    order_map = {section_id: idx for idx, section_id in enumerate(section_ids)}
    ordered = sorted(sections, key=lambda item: order_map.get(item.id, 999))
    has_new_coding_section = any(section.key == "coding_section" for section in ordered)
    filtered = []
    for section in ordered:
        if section.key not in ACTIVE_SECTION_KEYS and section.key not in LEGACY_SECTION_KEYS:
            continue
        if has_new_coding_section and section.key in LEGACY_SECTION_KEYS:
            continue
        filtered.append(section)
    return filtered


def assessment_for_admin(session: Session, assessment_id: str, admin_id: str) -> Assessment:
    assessment = session.get(Assessment, assessment_id)
    if not assessment or assessment.admin_id != admin_id:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return assessment


def assessment_for_admin_slug(session: Session, assessment_slug: str, admin_id: str) -> Assessment:
    direct_match = session.exec(
        select(Assessment).where(
            Assessment.slug == assessment_slug,
            Assessment.admin_id == admin_id,
        )
    ).first()
    if direct_match:
        return direct_match

    # Support older rows and stale pretty URLs by resolving against the
    # admin's assessments using the current name-derived slug.
    admin_assessments = session.exec(
        select(Assessment).where(Assessment.admin_id == admin_id)
    ).all()

    for assessment in admin_assessments:
        derived_slug = slugify(assessment.name or "")
        if assessment_slug in {assessment.id, derived_slug}:
            if assessment.slug != derived_slug and derived_slug:
                assessment.slug = derived_slug
                session.add(assessment)
                session.commit()
                session.refresh(assessment)
            return assessment

    raise HTTPException(status_code=404, detail="Assessment not found")


def ensure_assessment_section_belongs_to_assessment(
    link: Optional[AssessmentSection],
    assessment_id: str,
) -> Optional[AssessmentSection]:
    if link and link.assessment_id != assessment_id:
        raise HTTPException(status_code=409, detail="Assessment section ownership mismatch")
    return link


def build_assessment_section_link(
    assessment_id: str,
    section_id: str,
    config_json: str = "{}",
) -> AssessmentSection:
    return ensure_assessment_section_belongs_to_assessment(
        AssessmentSection(
            assessment_id=assessment_id,
            section_id=section_id,
            config_json=config_json,
        ),
        assessment_id,
    )


def get_assessment_section_link(session: Session, assessment_id: str, section_id: str) -> Optional[AssessmentSection]:
    return ensure_assessment_section_belongs_to_assessment(
        session.exec(
        select(AssessmentSection).where(
            AssessmentSection.assessment_id == assessment_id,
            AssessmentSection.section_id == section_id,
        )
    ).first(),
        assessment_id,
    )


def ensure_assessment_section_link(session: Session, assessment_id: str, section: Section) -> AssessmentSection:
    link = get_assessment_section_link(session, assessment_id, section.id)
    if link:
        return link

    link = build_assessment_section_link(
        assessment_id=assessment_id,
        section_id=section.id,
        config_json=json.dumps(initial_section_config(section)),
    )
    session.add(link)
    session.commit()
    session.refresh(link)
    return link


def recommended_section_keys_for_assessment(assessment: Assessment) -> list[str]:
    jd_text = str(assessment.jd_text or "").lower()
    selected = ["aptitude", "verbal_ability", "coding_section"]
    if "python" in jd_text:
        selected.append("coding_mcq_python")
    if "java" in jd_text:
        selected.append("coding_mcq_java")
    return selected


def resolve_assessment_mcq_section(session: Session, assessment_id: str, section_id: str) -> Optional[Section]:
    section = session.get(Section, section_id)
    if section and section.section_type == "mcq":
        return section

    sections = get_assessment_sections(session, assessment_id)
    for item in sections:
        if item.id == section_id and item.section_type == "mcq":
            return item

    for item in sections:
        if item.section_type == "mcq":
            return item

    return None


def parse_section_config(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {}


def load_section_bank(section_key: str) -> dict[str, Any]:
    section_title = section_key.replace("_", " ").title()
    topic_dir = TOPIC_BANK_DIRS.get(section_key, "")
    if topic_dir and os.path.isdir(topic_dir):
        merged_questions: list[dict[str, Any]] = []
        for file_name in sorted(os.listdir(topic_dir)):
            if not file_name.lower().endswith(".json"):
                continue
            file_path = os.path.join(topic_dir, file_name)
            try:
                with open(file_path, "r", encoding="utf-8") as handle:
                    parsed = json.load(handle)
            except Exception:
                continue
            if not isinstance(parsed, dict):
                continue
            section_title = str(parsed.get("section") or section_title)
            questions = parsed.get("questions")
            if isinstance(questions, list):
                merged_questions.extend(item for item in questions if isinstance(item, dict))
        if merged_questions:
            return {"section": section_title, "questions": merged_questions}
    path = TEST_BANK_PATHS.get(section_key, "")
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            parsed = json.load(handle)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            questions = [item for item in parsed if isinstance(item, dict)]
            return {"section": section_title, "questions": questions}
        return {}
    except Exception:
        return {}


def generate_mcq_questions_with_nvidia(section: Section, count: int, difficulty: str) -> list[dict[str, Any]]:
    topic_hints = _section_topic_hints(section)
    prompt = (
        f"Generate {count} {difficulty.upper()} multiple-choice questions for the section "
        f"'{section.title}'. Return only JSON in the shape "
        '{"questions":[{"question":"...","options":["...","...","...","..."],"answer":"...","difficulty":"EASY|MEDIUM|HARD"}]}\n'
        f"Use these topic hints and stay close to them: {json.dumps(topic_hints)}.\n"
        "Do not generate generic trivia or repeated fallback-style questions.\n"
        "Do not ask prime-number identification, basic odd/even checks, or toy arithmetic unless those are explicitly part of the listed topics.\n"
        "Vary the questions across the provided topics."
    )
    try:
        content = request_nvidia_chat(
            prompt=prompt,
            system_prompt="You generate concise, valid MCQ JSON only.",
            max_tokens=1024,
            temperature=0.2,
            top_p=0.7,
        )
        try:
            parsed = _extract_json_object(content)
        except Exception as first_error:
            repaired = request_nvidia_chat(
                prompt=(
                    f"{prompt}\n\n"
                    "Your previous response was invalid. Return only strict valid JSON. "
                    f"Fix this exact error: {first_error}"
                ),
                system_prompt="You generate concise, valid MCQ JSON only.",
                max_tokens=1024,
                temperature=0.2,
                top_p=0.7,
            )
            try:
                parsed = _extract_json_object(repaired)
            except Exception:
                fallback_questions = _extract_mcq_questions_from_text(repaired) or _extract_mcq_questions_from_text(content)
                if fallback_questions:
                    return [normalize_mcq_question(section, item, idx) for idx, item in enumerate(fallback_questions)]
                raise
        questions = parsed.get("questions", [])
        if not isinstance(questions, list):
            raise ValueError("Invalid AI payload")
        return [normalize_mcq_question(section, item, idx) for idx, item in enumerate(questions)]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"NVIDIA AI question generation failed: {exc}") from exc


def _section_topic_hints(section: Section) -> list[str]:
    explicit_topics = {
        "aptitude": [
            "percentages and averages",
            "ratio and proportion",
            "time speed and distance",
            "profit and loss",
            "work and time",
            "series and pattern reasoning",
            "probability and permutations",
            "clocks calendars and ages",
            "geometry and mensuration",
            "data interpretation",
        ],
        "coding_mcq_java": [
            "JVM and JDK",
            "OOP concepts",
            "inheritance and polymorphism",
            "encapsulation and abstraction",
            "method overloading and overriding",
            "collections",
            "exceptions",
            "strings",
            "multithreading",
            "interfaces and access modifiers",
        ],
        "coding_mcq_python": [
            "Python syntax and semantics",
            "functions and arguments",
            "lists tuples dictionaries and sets",
            "comprehensions",
            "object oriented programming",
            "exceptions",
            "iterators and generators",
            "modules and packages",
            "string handling",
            "time complexity and debugging",
        ],
    }
    if section.key in explicit_topics:
        return explicit_topics[section.key]

    bank = load_section_bank(section.key)
    questions = bank.get("questions") if isinstance(bank, dict) else []
    hints: list[str] = []
    if isinstance(questions, list):
        for item in questions[:12]:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or "").strip()
            if question:
                hints.append(question[:120])
    return hints or [section.title]


def _extract_json_object(raw_text: str) -> Any:
    cleaned = str(raw_text or "").strip()
    if not cleaned:
        raise ValueError("AI response was empty")
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    candidates = [_repair_mcq_json_shape(cleaned), cleaned]
    object_match = re.search(r"\{.*\}", cleaned, flags=re.S)
    if object_match:
        matched = object_match.group(0)
        candidates.append(_repair_mcq_json_shape(matched))
        candidates.append(matched)
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
    raise ValueError("AI response did not contain valid JSON")


def _repair_mcq_json_shape(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    if '"questions"' in text and text.count("[") > text.count("]"):
        trailing_braces = len(text) - len(text.rstrip("}"))
        if trailing_braces:
            missing = "]" * (text.count("[") - text.count("]"))
            text = f"{text[:-trailing_braces]}{missing}{text[-trailing_braces:]}"
    return text


def _extract_mcq_questions_from_text(value: str) -> list[dict[str, Any]]:
    text = str(value or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()

    object_pattern = re.compile(
        r'\{\s*"question"\s*:\s*"(?P<question>.*?)"\s*,\s*"options"\s*:\s*\[(?P<options>.*?)\]\s*,\s*"answer"\s*:\s*"(?P<answer>.*?)"(?:\s*,\s*"difficulty"\s*:\s*"(?P<difficulty>.*?)")?\s*\}',
        flags=re.S,
    )
    option_pattern = re.compile(r'"(.*?)"', flags=re.S)
    questions: list[dict[str, Any]] = []

    for match in object_pattern.finditer(text):
        raw_options = match.group("options") or ""
        options = [item.encode("utf-8").decode("unicode_escape").strip() for item in option_pattern.findall(raw_options)]
        answer = match.group("answer").encode("utf-8").decode("unicode_escape").strip()
        question = match.group("question").encode("utf-8").decode("unicode_escape").strip()
        difficulty = (match.group("difficulty") or "").encode("utf-8").decode("unicode_escape").strip()
        if not question or len(options) != 4 or answer not in options:
            continue
        questions.append(
            {
                "question": question,
                "options": options,
                "answer": answer,
                "difficulty": difficulty or "MEDIUM",
            }
        )
    return questions


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
    open_brackets = text.count("[")
    close_brackets = text.count("]")
    if open_brackets > close_brackets:
        missing = "]" * (open_brackets - close_brackets)
        trailing_braces = len(text) - len(text.rstrip("}"))
        if trailing_braces:
          text = f"{text[:-trailing_braces]}{missing}{text[-trailing_braces:]}"
        else:
          text += missing
    open_braces = text.count("{")
    close_braces = text.count("}")
    if open_braces > close_braces:
        text += "}" * (open_braces - close_braces)
    return text


def generate_audio_video_ai_questions(transcript: str, count: int) -> list[dict[str, Any]]:
    prompt = f"""
Generate ONLY valid JSON.

Return this exact shape:
{{
  "questions": [
    {{
      "prompt": "",
      "options": ["", "", "", ""],
      "answer": ""
    }}
  ]
}}

Rules:
- Generate exactly {count} MCQ questions from the transcript.
- Each question must have exactly 4 options.
- The answer must exactly match one option.
- Keep questions clear and suitable for candidate assessments.

Transcript:
{transcript}
""".strip()
    raw = request_nvidia_chat(prompt=prompt, max_tokens=1200, temperature=0.2, top_p=0.7)
    parsed = _extract_json_object(raw)
    questions = parsed.get("questions") if isinstance(parsed, dict) else []
    if not isinstance(questions, list):
        raise ValueError("Audio/video AI response missing questions")
    normalized = []
    for index, item in enumerate(questions[:count]):
        if not isinstance(item, dict):
            continue
        options = [str(option).strip() for option in (item.get("options") or []) if str(option).strip()][:4]
        answer = str(item.get("answer") or "").strip()
        if len(options) != 4 or answer not in options:
            continue
        normalized.append(
            {
                "id": f"ai-question-{uuid4().hex}",
                "prompt": str(item.get("prompt") or "").strip(),
                "options": options,
                "answer": answer,
            }
        )
    if not normalized:
        raise ValueError("Audio/video AI did not return usable questions")
    return normalized


def generate_speaking_ai_prompts(count: int) -> list[dict[str, Any]]:
    prompt = f"""
Generate ONLY valid JSON.

Return this exact shape:
{{
  "prompts": [
    {{
      "prompt": ""
    }}
  ]
}}

Rules:
- Generate exactly {count} speaking prompts.
- Each prompt should be concise, realistic, and suitable for hiring assessments.
""".strip()
    raw = request_nvidia_chat(prompt=prompt, max_tokens=700, temperature=0.2, top_p=0.7)
    parsed = _extract_json_object(raw)
    prompts = parsed.get("prompts") if isinstance(parsed, dict) else []
    if not isinstance(prompts, list):
        raise ValueError("Speaking AI response missing prompts")
    normalized = [
        {
            "id": f"speaking-{uuid4().hex}",
            "prompt": str(item.get("prompt") or "").strip(),
        }
        for item in prompts[:count]
        if isinstance(item, dict) and str(item.get("prompt") or "").strip()
    ]
    if not normalized:
        raise ValueError("Speaking AI did not return usable prompts")
    return normalized


def generate_writing_ai_topics(count: int) -> list[dict[str, Any]]:
    prompt = f"""
Generate ONLY valid JSON.

Return this exact shape:
{{
  "topics": [
    {{
      "topic": "",
      "min_words": 120
    }}
  ]
}}

Rules:
- Generate exactly {count} essay-style writing topics.
- Topics should be suitable for hiring assessments.
- min_words should be a practical integer between 80 and 200.
""".strip()
    raw = request_nvidia_chat(prompt=prompt, max_tokens=700, temperature=0.2, top_p=0.7)
    parsed = _extract_json_object(raw)
    topics = parsed.get("topics") if isinstance(parsed, dict) else []
    if not isinstance(topics, list):
        raise ValueError("Writing AI response missing topics")
    normalized = [
        {
            "id": f"writing-{uuid4().hex}",
            "topic": str(item.get("topic") or "").strip(),
            "min_words": max(80, int(item.get("min_words") or 120)),
        }
        for item in topics[:count]
        if isinstance(item, dict) and str(item.get("topic") or "").strip()
    ]
    if not normalized:
        raise ValueError("Writing AI did not return usable topics")
    return normalized


def generate_fill_blanks_ai_items(count: int) -> list[dict[str, Any]]:
    prompt = f"""
Generate ONLY valid JSON.

Return this exact shape:
{{
  "items": [
    {{
      "template": "",
      "options": ["", "", "", ""],
      "answer_order": ["", ""]
    }}
  ]
}}

Rules:
- Generate exactly {count} fill-in-the-blanks questions.
- template must contain blanks suitable for the answer_order.
- options must include the correct answers and distractors.
- answer_order must contain the correct words in blank order.
""".strip()
    raw = request_nvidia_chat(prompt=prompt, max_tokens=900, temperature=0.2, top_p=0.7)
    parsed = _extract_json_object(raw)
    items = parsed.get("items") if isinstance(parsed, dict) else []
    if not isinstance(items, list):
        raise ValueError("Fill blanks AI response missing items")
    normalized = []
    for item in items[:count]:
        if not isinstance(item, dict):
            continue
        template = str(item.get("template") or "").strip()
        options = [str(option).strip() for option in (item.get("options") or []) if str(option).strip()]
        answer_order = [str(option).strip() for option in (item.get("answer_order") or []) if str(option).strip()]
        if not template or not options or not answer_order:
            continue
        normalized.append(
            {
                "id": f"drag-drop-{uuid4().hex}",
                "template": template,
                "options": options,
                "answer_order": answer_order,
            }
        )
    if not normalized:
        raise ValueError("Fill blanks AI did not return usable items")
    return normalized


def initial_section_config(section: Section) -> dict[str, Any]:
    if section.section_type == "coding":
        bank = load_section_bank(section.key)
        if isinstance(bank.get("problems"), list) and bank.get("problems"):
            return {"section": bank.get("section") or section.title, "problems": bank.get("problems")}
        return {"section": section.title, "problems": []}
    if section.section_type == "verbal":
        return {
            "section": section.title,
            "listening_blocks": [],
            "speaking_tasks": [],
            "writing_tasks": [],
            "drag_drop_questions": [],
        }
    bank = load_section_bank(section.key)
    if isinstance(bank.get("questions"), list) and bank.get("questions"):
        questions = bank.get("questions")
        return {
            "section": bank.get("section") or section.title,
            "questions": questions,
            "display_count": len(questions),
        }
    return {"section": section.title, "questions": [], "display_count": 0}


def mcq_display_count(raw_config: dict[str, Any]) -> Optional[int]:
    value = raw_config.get("display_count")
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, parsed)


def select_assigned_mcq_questions(raw_config: dict[str, Any], questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    display_count = mcq_display_count(raw_config)
    if display_count is None:
        return questions

    max_count = min(len(questions), display_count)
    assigned_ids = raw_config.get("assigned_question_ids")
    if isinstance(assigned_ids, list) and assigned_ids:
        assigned_set = {str(item) for item in assigned_ids}
        selected = [question for question in questions if str(question.get("id")) in assigned_set]
        if len(selected) >= max_count:
            return selected[:max_count]

    return questions[:max_count]


SECTION_EXPECTED_COUNTS = {
    "aptitude": 10,
    "verbal_ability": 4,
    "coding_section": 3,
    "coding_mcq_python": 20,
    "coding_mcq_java": 20,
}

SECTION_BATCH_SIZES = {
    "aptitude": 10,
    "verbal_ability": 1,
    "coding_section": 1,
    "coding_mcq_python": 20,
    "coding_mcq_java": 20,
}

GENERATION_SECTION_ORDER = [
    "coding_section",
]

GENERATION_STOP_EVENT = threading.Event()
GENERATION_WORKER_STARTED = False


def batch_plan_for_section(section_key: str) -> list[int]:
    expected = SECTION_EXPECTED_COUNTS[section_key]
    step = SECTION_BATCH_SIZES[section_key]
    plan: list[int] = []
    remaining = expected
    while remaining > 0:
        current = min(step, remaining)
        plan.append(current)
        remaining -= current
    return plan


def expected_count_for_section(section_key: str) -> int:
    return SECTION_EXPECTED_COUNTS.get(section_key, 0)


def count_generated_items(config: dict[str, Any], section_key: str) -> int:
    if section_key == "coding_section":
        return len(config.get("problems") or []) if isinstance(config.get("problems"), list) else 0
    if section_key == "verbal_ability":
        total = 0
        for key in ("listening_blocks", "speaking_tasks", "writing_tasks", "drag_drop_questions"):
            total += len(config.get(key) or []) if isinstance(config.get(key), list) else 0
        return total
    return len(config.get("questions") or []) if isinstance(config.get("questions"), list) else 0


def append_generated_batch(existing_config: dict[str, Any], section_key: str, batch_payload: dict[str, Any]) -> dict[str, Any]:
    section_title = str(existing_config.get("section") or batch_payload.get("section") or section_key.replace("_", " ").title())
    if section_key == "coding_section":
        existing_problems = existing_config.get("problems") if isinstance(existing_config.get("problems"), list) else []
        incoming = batch_payload.get("problems") if isinstance(batch_payload.get("problems"), list) else []
        return {
            "section": section_title,
            "problems": [*existing_problems, *incoming],
        }
    existing_questions = existing_config.get("questions") if isinstance(existing_config.get("questions"), list) else []
    incoming = batch_payload.get("questions") if isinstance(batch_payload.get("questions"), list) else []
    return {
        "section": section_title,
        "questions": [*existing_questions, *incoming],
    }


def section_ready_threshold(section_key: str) -> int:
    if section_key in {"coding_section", "verbal_ability"}:
        return 1
    return SECTION_BATCH_SIZES.get(section_key, 1)


def section_generated_count(session: Session, assessment_id: str, section: Section) -> int:
    link = get_assessment_section_link(session, assessment_id, section.id)
    config = parse_section_config(link.config_json if link else "")
    if section.section_type == "mcq" and not config.get("questions"):
        config = initial_section_config(section)
    elif section.section_type == "verbal" and not any(
        config.get(key) for key in ("listening_blocks", "speaking_tasks", "writing_tasks", "drag_drop_questions")
    ):
        config = initial_section_config(section)
    elif section.section_type == "coding" and not config.get("problems"):
        config = initial_section_config(section)
    return count_generated_items(config, section.key)


def section_expected_count(session: Session, assessment_id: str, section: Section) -> int:
    link = get_assessment_section_link(session, assessment_id, section.id)
    config = parse_section_config(link.config_json if link else "")
    if section.section_type == "mcq" and not config.get("questions"):
        config = initial_section_config(section)
    elif section.section_type == "verbal" and not any(
        config.get(key) for key in ("listening_blocks", "speaking_tasks", "writing_tasks", "drag_drop_questions")
    ):
        config = initial_section_config(section)
    elif section.section_type == "coding" and not config.get("problems"):
        config = initial_section_config(section)
    return count_generated_items(config, section.key)


def section_ready_for_candidate(session: Session, assessment_id: str, section: Section) -> bool:
    return section_generated_count(session, assessment_id, section) >= section_ready_threshold(section.key)


def section_has_candidate_content(session: Session, assessment_id: str, section: Section) -> bool:
    return section_generated_count(session, assessment_id, section) > 0


def auto_skip_empty_section(session: Session, attempt: Attempt) -> None:
    if attempt.status == "completed":
        return
    attempt.score = 0.0
    attempt.max_score = 0.0
    attempt.answers_json = "{}"
    attempt.status = "completed"
    attempt.submitted_at = datetime.utcnow()
    session.add(attempt)
    session.commit()


def queue_generation_jobs(session: Session, assessment: Assessment) -> None:
    for section_key in GENERATION_SECTION_ORDER:
        if section_key == "metadata":
            session.add(
                GenerationJob(
                    assessment_id=assessment.id,
                    admin_id=str(assessment.admin_id or ""),
                    section_key="metadata",
                    batch_index=0,
                    batch_size=1,
                )
            )
            continue
        for batch_index, batch_size in enumerate(batch_plan_for_section(section_key)):
            session.add(
                GenerationJob(
                    assessment_id=assessment.id,
                    admin_id=str(assessment.admin_id or ""),
                    section_key=section_key,
                    batch_index=batch_index,
                    batch_size=batch_size,
                )
            )


def recalculate_assessment_generation(session: Session, assessment_id: str) -> None:
    assessment = session.get(Assessment, assessment_id)
    if not assessment:
        return
    jobs = session.exec(select(GenerationJob).where(GenerationJob.assessment_id == assessment_id)).all()
    completed_section_keys = {
        job.section_key
        for job in jobs
        if job.status == "completed"
    }
    assessment.generated_sections_count = len([key for key in completed_section_keys if key != "metadata"])
    if jobs and any(job.status in {"pending", "processing"} for job in jobs):
        assessment.generation_status = "generating"
    elif jobs and any(job.status == "failed" for job in jobs):
        assessment.generation_status = "partial"
    elif jobs:
        assessment.generation_status = "ready"
    session.add(assessment)
    session.commit()


def next_generation_job(session: Session) -> Optional[GenerationJob]:
    now = datetime.utcnow()
    return session.exec(
        select(GenerationJob)
        .where(GenerationJob.status == "pending", GenerationJob.available_at <= now)
        .order_by(GenerationJob.created_at.asc())
    ).first()


def process_generation_job(job_id: str) -> None:
    with Session(engine) as session:
        job = session.get(GenerationJob, job_id)
        if not job or job.status not in {"pending", "processing"}:
            return
        job.status = "skipped"
        job.updated_at = datetime.utcnow()
        job.last_error = "Background AI generation is disabled. Static section banks are used instead."
        session.add(job)
        session.commit()


def generation_worker_loop() -> None:
    while not GENERATION_STOP_EVENT.is_set():
        try:
            with Session(engine) as session:
                job = next_generation_job(session)
                if not job:
                    time.sleep(1.0)
                    continue
                job.status = "processing"
                job.updated_at = datetime.utcnow()
                session.add(job)
                session.commit()
                job_id = job.id
            process_generation_job(job_id)
        except Exception:
            time.sleep(1.5)


def normalize_question_history_text(value: str) -> str:
    normalized = " ".join(str(value or "").strip().lower().split())
    return normalized[:1000]


def question_history_hash(value: str) -> str:
    return hashlib.sha256(normalize_question_history_text(value).encode("utf-8")).hexdigest()


def tokenize_similarity_text(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalize_question_history_text(value))
        if len(token) > 2
    }


def similarity_score(left: str, right: str) -> float:
    left_tokens = tokenize_similarity_text(left)
    right_tokens = tokenize_similarity_text(right)
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return intersection / union if union else 0.0


def extract_generated_prompt_texts(generated_sections: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for section_key, config in generated_sections.items():
        if not isinstance(config, dict):
            continue
        questions = config.get("questions")
        if isinstance(questions, list):
            for item in questions:
                if not isinstance(item, dict):
                    continue
                question = str(item.get("question") or "").strip()
                if question:
                    texts.append(question)
            continue
        if section_key == "coding_section" and isinstance(config.get("problems"), list):
            for problem in config["problems"]:
                if not isinstance(problem, dict):
                    continue
                combined = " ".join(
                    part for part in [
                        str(problem.get("title") or "").strip(),
                        str(problem.get("description") or "").strip(),
                    ] if part
                )
                if combined:
                    texts.append(combined)
    return texts


def find_similar_generated_prompt(
    generated_sections: dict[str, Any],
    previous_texts: list[str],
    threshold: float = 0.72,
) -> Optional[str]:
    generated_texts = extract_generated_prompt_texts(generated_sections)
    for candidate in generated_texts:
        for previous in previous_texts:
            if normalize_question_history_text(candidate) == normalize_question_history_text(previous):
                return candidate
            if similarity_score(candidate, previous) >= threshold:
                return candidate
    return None


def collect_previous_question_texts(session: Session, admin_id: str, limit: int = 150) -> list[str]:
    history_rows = session.exec(
        select(QuestionHistory)
        .where(QuestionHistory.admin_id == admin_id)
        .order_by(QuestionHistory.created_at.desc())
    ).all()
    if history_rows:
        texts: list[str] = []
        seen: set[str] = set()
        for row in history_rows:
            normalized = row.content_hash or question_history_hash(row.raw_text)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            texts.append(row.raw_text)
            if len(texts) >= limit:
                break
        return texts

    assessment_ids = [
        item.id for item in session.exec(select(Assessment).where(Assessment.admin_id == admin_id)).all()
    ]
    if not assessment_ids:
        return []
    texts: list[str] = []
    links = session.exec(
        select(AssessmentSection).where(AssessmentSection.assessment_id.in_(assessment_ids))
    ).all()
    for link in links:
        config = parse_section_config(link.config_json)
        questions = config.get("questions")
        if isinstance(questions, list):
            for item in questions:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("question") or "").strip()
                if text and text not in texts:
                    texts.append(text)
        else:
            title = str(config.get("title") or "").strip()
            description = str(config.get("description") or "").strip()
            if title and title not in texts:
                texts.append(title)
            if description and description not in texts:
                texts.append(description)
        if len(texts) >= limit:
            break
    return texts[:limit]


def save_question_history(
    session: Session,
    *,
    admin_id: str,
    assessment_id: str,
    generated_sections: dict[str, Any],
) -> None:
    pending: list[QuestionHistory] = []
    existing_hashes = {
        str(row)
        for row in session.exec(
            select(QuestionHistory.content_hash).where(QuestionHistory.admin_id == admin_id)
        ).all()
        if row
    }
    staged_hashes: set[str] = set()
    for section_key, config in generated_sections.items():
        if not isinstance(config, dict):
            continue
        questions = config.get("questions")
        if isinstance(questions, list):
            for item in questions:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("question") or "").strip()
                normalized = normalize_question_history_text(text)
                content_hash = question_history_hash(text)
                if not normalized or content_hash in existing_hashes or content_hash in staged_hashes:
                    continue
                staged_hashes.add(content_hash)
                pending.append(
                    QuestionHistory(
                        admin_id=admin_id,
                        assessment_id=assessment_id,
                        section_key=section_key,
                        entry_type="question",
                        raw_text=text,
                        normalized_text=normalized,
                        content_hash=content_hash,
                    )
                )
            continue

        if section_key == "coding_section" and isinstance(config.get("problems"), list):
            for problem in config["problems"]:
                if not isinstance(problem, dict):
                    continue
                combined = " ".join(
                    part for part in [
                        str(problem.get("title") or "").strip(),
                        str(problem.get("description") or "").strip(),
                    ] if part
                )
                normalized = normalize_question_history_text(combined)
                content_hash = question_history_hash(combined)
                if not normalized or content_hash in existing_hashes or content_hash in staged_hashes:
                    continue
                staged_hashes.add(content_hash)
                pending.append(
                    QuestionHistory(
                        admin_id=admin_id,
                        assessment_id=assessment_id,
                        section_key=section_key,
                        entry_type="coding",
                        raw_text=combined,
                        normalized_text=normalized,
                        content_hash=content_hash,
                    )
                )

    if pending:
        try:
            session.add_all(pending)
            session.commit()
        except Exception:
            session.rollback()


def normalize_mcq_question(section: Section, item: dict[str, Any], index: int) -> dict[str, Any]:
    question = item.get("question") or item.get("title") or ""
    options = item.get("options") or []
    if not question or not isinstance(options, list):
        raise HTTPException(status_code=400, detail=f"Invalid question format in {section.title}")
    normalized_options = [str(option) for option in options]
    passage = str(item.get("passage") or item.get("description") or "")
    return {
        "id": str(item.get("id") or f"{section.key}-{index + 1}"),
        "passage": passage,
        "question": str(question),
        "options": normalized_options,
        "answer": normalize_mcq_answer(item.get("answer"), normalized_options),
        "audio": str(item.get("audio") or ""),
        "video": str(item.get("video") or ""),
        "image": str(item.get("image") or ""),
        "difficulty": str(item.get("difficulty") or infer_difficulty(str(question), passage)),
    }


def normalize_coding_testcase(item: dict[str, Any], index: int, *, require_output: bool) -> dict[str, Any]:
    raw_input = item.get("input")
    if raw_input is None:
        raise HTTPException(status_code=400, detail=f"Invalid coding testcase at position {index + 1}")
    output = item.get("output", "")
    if require_output and str(output).strip() == "":
        raise HTTPException(status_code=400, detail=f"Coding testcase {index + 1} must include output")
    return {
        "label": str(item.get("label") or f"Case {index + 1}"),
        "input_label": str(item.get("input_label") or "s"),
        "input": str(raw_input),
        "output": str(output or ""),
    }


def normalize_coding_problem_config(
    section: Section,
    raw_config: dict[str, Any],
    base: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    merged = dict(base or {})
    merged.update(raw_config or {})

    title = str(merged.get("title") or section.title).strip()
    statement = str(merged.get("statement") or merged.get("description") or "").strip()
    starter_code_map = merged.get("starter_code_by_language")
    if not isinstance(starter_code_map, dict):
        starter_code_map = {}
    starter_code_map = {str(key): str(value) for key, value in starter_code_map.items() if str(value).strip()}
    starter_code = str(merged.get("starter_code") or "")
    if not starter_code and starter_code_map:
        starter_code = next(iter(starter_code_map.values()))
    method_name = str(merged.get("method_name") or merged.get("function_name") or "solution")
    reference_solver_key = str(merged.get("reference_solver_key") or "")
    if not title or not statement or not starter_code or not method_name or not reference_solver_key:
      raise HTTPException(
          status_code=400,
          detail="Coding problem config must include title, statement, starter_code, method_name, and reference_solver_key",
      )

    visible_source = merged.get("visible_tests", merged.get("testcases", []))
    hidden_source = merged.get("hidden_tests", [])
    if not isinstance(visible_source, list) or not visible_source:
        raise HTTPException(status_code=400, detail="Coding problem config must include a non-empty visible_tests array")
    if not isinstance(hidden_source, list) or not hidden_source:
        raise HTTPException(status_code=400, detail="Coding problem config must include a non-empty hidden_tests array")

    configured_languages = [str(item).strip().lower() for item in (merged.get("supported_languages") or []) if str(item).strip()]
    supported_languages: list[str] = []
    for language in [*configured_languages, *DEFAULT_CODING_LANGUAGES]:
        if language and language not in supported_languages:
            supported_languages.append(language)

    for language in supported_languages:
        if not str(starter_code_map.get(language) or "").strip():
            template = coding_starter_template(language, method_name, reference_solver_key)
            if template:
                starter_code_map[language] = template

    if not starter_code:
        starter_code = starter_code_map.get("java") or next(iter(starter_code_map.values()), "")

    visible_tests = [
        normalize_coding_testcase(item, idx, require_output=False)
        for idx, item in enumerate(visible_source)
    ]
    hidden_tests = [
        normalize_coding_testcase(item, idx, require_output=True)
        for idx, item in enumerate(hidden_source)
    ]

    return {
        "title": title,
        "description": statement,
        "statement": statement,
        "starter_code": starter_code,
        "starter_code_by_language": starter_code_map,
        "supported_languages": supported_languages,
        "method_name": method_name,
        "reference_solver_key": reference_solver_key,
        "constraints": str(merged.get("constraints") or ""),
        "sample_input": str(merged.get("sample_input") or ""),
        "sample_output": str(merged.get("sample_output") or ""),
        "examples": merged.get("examples") if isinstance(merged.get("examples"), list) else [],
        "testcases": visible_tests,
        "visible_tests": visible_tests,
        "hidden_tests": hidden_tests,
    }


def normalize_verbal_config(section: Section, raw_config: dict[str, Any]) -> dict[str, Any]:
    listening_blocks = []
    for index, block in enumerate(raw_config.get("listening_blocks") or []):
        if not isinstance(block, dict):
            continue
        media_url = str(block.get("media_url") or "").strip()
        questions = []
        for question_index, question in enumerate(block.get("questions") or []):
            if not isinstance(question, dict):
                continue
            questions.append(
                {
                    "id": str(question.get("id") or f"{block.get('id') or f'media-block-{index + 1}'}-question-{question_index + 1}"),
                    "prompt": str(question.get("prompt") or "").strip(),
                    "options": [str(option).strip() for option in (question.get("options") or []) if str(option).strip()],
                    "answer": str(question.get("answer") or "").strip(),
                }
            )
        listening_blocks.append(
            {
                "id": str(block.get("id") or f"media-block-{index + 1}"),
                "title": str(block.get("title") or f"Media Block {index + 1}"),
                "media_type": infer_media_kind(media_url, str(block.get("media_type") or "audio")),
                "media_url": media_url,
                "prompt": str(block.get("prompt") or "Write what you heard or answer the questions about the audio/video.").strip(),
                "questions": questions,
            }
        )

    speaking_tasks = [
        {
            "id": str(item.get("id") or f"speaking-{index + 1}"),
            "prompt": str(item.get("prompt") or ""),
        }
        for index, item in enumerate(raw_config.get("speaking_tasks") or [])
        if isinstance(item, dict)
    ]
    writing_tasks = [
        {
            "id": str(item.get("id") or f"writing-{index + 1}"),
            "topic": str(item.get("topic") or ""),
            "min_words": int(item.get("min_words") or 80),
        }
        for index, item in enumerate(raw_config.get("writing_tasks") or [])
        if isinstance(item, dict)
    ]
    drag_drop_questions = [
        {
            "id": str(item.get("id") or f"drag-drop-{index + 1}"),
            "template": str(item.get("template") or ""),
            "options": [str(option).strip() for option in (item.get("options") or []) if str(option).strip()],
            "answer_order": [str(option).strip() for option in (item.get("answer_order") or []) if str(option).strip()],
        }
        for index, item in enumerate(raw_config.get("drag_drop_questions") or [])
        if isinstance(item, dict)
    ]
    return {
        "section": str(raw_config.get("section") or section.title),
        "listening_blocks": listening_blocks,
        "speaking_tasks": speaking_tasks,
        "writing_tasks": writing_tasks,
        "drag_drop_questions": drag_drop_questions,
    }


def questions_for_section(session: Session, assessment_id: str, section: Section) -> list[dict[str, Any]]:
    link = get_assessment_section_link(session, assessment_id, section.id)
    config = parse_section_config(link.config_json if link else "")
    if not config.get("questions"):
        config = initial_section_config(section)
    if "questions" in config:
        questions = [normalize_mcq_question(section, item, idx) for idx, item in enumerate(config["questions"])]
        return select_assigned_mcq_questions(config, questions)
    return []


def verbal_prompt_for_section(session: Session, assessment_id: str, section: Section) -> dict[str, Any]:
    link = get_assessment_section_link(session, assessment_id, section.id)
    config = parse_section_config(link.config_json if link else "")
    return normalize_verbal_config(section, config or {})


def coding_prompt_for_section(session: Session, assessment_id: str, section: Section) -> dict[str, Any]:
    link = get_assessment_section_link(session, assessment_id, section.id)
    config = parse_section_config(link.config_json if link else "")
    base = dict(CODING_PROMPTS.get(section.key, {}))
    if config:
        if config.get("problems"):
            return {
                "section": str(config.get("section") or section.title),
                "problems": [
                    normalize_coding_problem_config(section, item, None)
                    for item in config.get("problems", [])
                    if isinstance(item, dict)
                ],
            }
        return normalize_coding_problem_config(section, config, base)
    if not base:
        return {"section": section.title, "problems": []}
    base.setdefault("difficulty", "Medium")
    base.setdefault("examples", [])
    base.setdefault("method_name", "lengthOfLongestSubstring")
    base.setdefault("reference_solver_key", "")
    base.setdefault(
        "testcases",
        [
            {"label": "Case 1", "input_label": "s", "input": '"abcabcbb"', "output": "3"},
            {"label": "Case 2", "input_label": "s", "input": '"bbbbb"', "output": "1"},
            {"label": "Case 3", "input_label": "s", "input": '"pwwkew"', "output": "3"},
        ],
    )
    base.setdefault("hidden_tests", [])
    return base


def default_attempt_max_score(session: Session, assessment_id: str, section: Section) -> float:
    if section.section_type == "mcq":
        return float(len(questions_for_section(session, assessment_id, section)))
    if section.section_type == "verbal":
        prompt = verbal_prompt_for_section(session, assessment_id, section)
        total = 0
        total += len(prompt.get("listening_blocks") or [])
        total += len(prompt.get("speaking_tasks") or [])
        total += len(prompt.get("writing_tasks") or [])
        total += len(prompt.get("drag_drop_questions") or [])
        return float(total or 1)
    prompt = coding_prompt_for_section(session, assessment_id, section)
    if isinstance(prompt.get("problems"), list):
        total = 0
        for problem in prompt["problems"]:
            total += len(problem.get("hidden_tests", [])) or len(problem.get("testcases", [])) or 1
        return float(total or 1)
    return float(len(prompt.get("hidden_tests", [])) or len(prompt.get("testcases", [])) or 1)


def hydrate_visible_coding_tests(prompt: dict[str, Any], tests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    solver_key = str(prompt.get("reference_solver_key") or "")
    hydrated: list[dict[str, Any]] = []
    for index, test in enumerate(tests):
        item = dict(test)
        item.setdefault("label", f"Case {index + 1}")
        if str(item.get("output", "")).strip() == "":
            if not solver_key:
                raise HTTPException(status_code=400, detail="Reference evaluator not configured for this coding problem")
            try:
                item["output"] = solve_reference_case(solver_key, item.get("input", ""))
            except KeyError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        hydrated.append(item)
    return hydrated


def coding_problem_by_index(prompt: dict[str, Any], problem_index: int) -> dict[str, Any]:
    problems = prompt.get("problems")
    if isinstance(problems, list) and problems:
        safe_index = max(0, min(problem_index, len(problems) - 1))
        return problems[safe_index]
    return prompt


def assessment_complete(session: Session, candidate_id: str, assessment_id: str) -> bool:
    sections = get_assessment_sections(session, assessment_id)
    if not sections:
        return False
    for section in sections:
        attempt = attempt_or_404(session, candidate_id, section.id)
        auto_complete_if_deadline_passed(session, attempt)
        if attempt.status != "completed":
            return False
    return True


def next_section_meta(
    session: Session,
    candidate_id: str,
    assessment_id: str,
    current_section_id: str,
) -> dict[str, Any]:
    sections = get_assessment_sections(session, assessment_id)
    current_seen = False
    for section in sections:
        if section.id == current_section_id:
            current_seen = True
            continue
        if not current_seen:
            continue
        attempt = attempt_or_404(session, candidate_id, section.id)
        auto_complete_if_deadline_passed(session, attempt)
        if attempt.status != "completed" and not section_has_candidate_content(session, assessment_id, section):
            auto_skip_empty_section(session, attempt)
        if attempt.status != "completed":
            return {"next_section_id": section.id, "next_section_name": section.title, "all_completed": False}
    return {"next_section_id": None, "next_section_name": None, "all_completed": True}


def ensure_candidate_and_attempts(session: Session, invite: Invite, full_name: str, email: str) -> Candidate:
    candidate = session.exec(select(Candidate).where(Candidate.invite_id == invite.id)).first()
    if not candidate:
        candidate = Candidate(invite_id=invite.id, full_name=full_name, email=email)
        session.add(candidate)
        session.commit()
        session.refresh(candidate)

    for interview in session.exec(select(InterviewSchedule).where(InterviewSchedule.invite_id == invite.id)).all():
        if interview.candidate_id != candidate.id:
            interview.candidate_id = candidate.id
            interview.updated_at = datetime.utcnow()
            session.add(interview)

    for section in get_assessment_sections(session, invite.assessment_id):
        attempt = session.exec(
            select(Attempt).where(
                Attempt.candidate_id == candidate.id,
                Attempt.section_id == section.id,
            )
        ).first()
        if not attempt:
            session.add(
                Attempt(
                    candidate_id=candidate.id,
                    section_id=section.id,
                    max_score=default_attempt_max_score(session, invite.assessment_id, section),
                )
            )
    session.commit()
    return candidate


def candidate_profile_record(session: Session, invite_id: str) -> Optional[CandidateProfileAnalysis]:
    return session.exec(select(CandidateProfileAnalysis).where(CandidateProfileAnalysis.exam_invite_id == invite_id)).first()


def process_candidate_profile_analysis(
    *,
    analysis_id: str,
    invite_id: str,
    first_name: str,
    last_name: str,
    email: str,
    github_url: str,
    leetcode_url: str,
    resume_pdf_bytes: Optional[bytes],
    resume_drive_link: Optional[str],
) -> None:
    with Session(engine) as job_session:
        analysis = job_session.get(CandidateProfileAnalysis, analysis_id)
        if not analysis:
            return
        invite = job_session.get(Invite, invite_id)
        assessment = job_session.get(Assessment, invite.assessment_id) if invite else None

        try:
            parser_output = analyze_candidate_profile(
                first_name=first_name,
                last_name=last_name,
                email=email,
                github_url=github_url,
                leetcode_url=leetcode_url,
                resume_pdf_bytes=resume_pdf_bytes,
                resume_drive_link=resume_drive_link,
            )
            analysis.github_score = float(parser_output["github_score"])
            analysis.leetcode_score = float(parser_output["leetcode_score"])
            analysis.resume_score = float(parser_output["resume_score"])
            analysis.profile_score = float(parser_output["profile_score"])
            analysis.skills = parser_output["skills"]
            jd_match = build_jd_match(assessment.jd_text if assessment else "", parser_output["skills"])
            analysis.summary_json = json.dumps(
                {
                    "github_score": parser_output["github_score"],
                    "leetcode_score": parser_output["leetcode_score"],
                    "resume_score": parser_output["resume_score"],
                    "profile_score": parser_output["profile_score"],
                    "skills": parser_output["skills"],
                    "jd_match": jd_match,
                    "location": parser_output.get("location", ""),
                    "details": parser_output.get("details", {}),
                    "explanation": generate_explanation(jd_match, float(parser_output["profile_score"])),
                }
            )
            analysis.raw_response_json = json.dumps(parser_output)
            analysis.parser_status = "completed"
        except ProfileParserError as exc:
            analysis.github_score = 0
            analysis.leetcode_score = 0
            analysis.resume_score = 0
            analysis.profile_score = 0
            analysis.skills = []
            analysis.summary_json = "{}"
            analysis.raw_response_json = json.dumps({"error": str(exc)})
            analysis.parser_status = "failed"
        except Exception as exc:
            analysis.github_score = 0
            analysis.leetcode_score = 0
            analysis.resume_score = 0
            analysis.profile_score = 0
            analysis.skills = []
            analysis.summary_json = "{}"
            analysis.raw_response_json = json.dumps({"error": str(exc)})
            analysis.parser_status = "failed"

        analysis.updated_at = datetime.utcnow()
        job_session.add(analysis)
        job_session.commit()


def recommendation_skill_pool(parser_result: Optional[CandidateProfileAnalysis], parser_summary: dict[str, Any]) -> list[str]:
    skills: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if not text:
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        skills.append(text)

    if parser_result:
        for item in parser_result.skills or []:
            add(item)

    for item in parser_summary.get("skills", []) if isinstance(parser_summary.get("skills"), list) else []:
        add(item)

    details = parser_summary.get("details")
    if isinstance(details, dict):
        github = details.get("github")
        if isinstance(github, dict):
            for item in github.get("languages", []) if isinstance(github.get("languages"), list) else []:
                add(item)

    return strict_technical_skills(skills)


def safe_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {}


PROCTOR_REASON_LABELS = {
    "tab_switch": "Tab switched",
    "mobile_detected": "Mobile detected",
    "multiple_faces": "Multiple faces",
    "no_face": "No face",
    "fullscreen_exit": "Fullscreen exited",
    "right_click": "Right click",
    "blocked_shortcut": "Blocked shortcut",
    "screenshot_attempt": "Screenshot attempt",
    "clipboard_blocked": "Copy/paste blocked",
    "background_capture": "Virtual/screen app detected",
}


def summarize_proctor_reason(total_violations: int, limit: int, event_counts: dict[str, int]) -> str:
    detail_parts = []
    for key in (
        "tab_switch",
        "mobile_detected",
        "multiple_faces",
        "no_face",
        "fullscreen_exit",
        "right_click",
        "blocked_shortcut",
        "screenshot_attempt",
        "clipboard_blocked",
        "background_capture",
    ):
        count = int(event_counts.get(key, 0) or 0)
        if count <= 0:
            continue
        label = PROCTOR_REASON_LABELS.get(key, key.replace("_", " ").title())
        detail_parts.append(f"{label}: {count}")
    base = f"Violations: {total_violations} (limit {limit})"
    if not detail_parts:
        return base
    return f"{base}. " + ", ".join(detail_parts)


def attempt_or_404(session: Session, candidate_id: str, section_id: str) -> Attempt:
    attempt = session.exec(
        select(Attempt).where(
            Attempt.candidate_id == candidate_id,
            Attempt.section_id == section_id,
        )
    ).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Section not assigned")
    return attempt


def normalize_dt(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


def is_empty_answers(raw: str) -> bool:
    if not raw:
        return True
    try:
        parsed = json.loads(raw)
        return not bool(parsed)
    except Exception:
        return True


def parse_attempt_state(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {}


def extract_mcq_answers(raw: str) -> dict[str, str]:
    parsed = parse_attempt_state(raw)
    answers = parsed.get("answers") if isinstance(parsed.get("answers"), dict) else parsed
    if not isinstance(answers, dict):
        return {}
    return {str(key): str(value) for key, value in answers.items()}


def verbal_similarity_score(left: str, right: str) -> float:
    left_tokens = {token for token in re.findall(r"[a-z0-9]+", str(left or "").lower()) if token}
    right_tokens = {token for token in re.findall(r"[a-z0-9]+", str(right or "").lower()) if token}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(1, len(right_tokens))


def extract_coding_state(raw: str) -> dict[str, Any]:
    parsed = parse_attempt_state(raw)
    if isinstance(parsed.get("problem_states"), list):
        return {
            "problem_states": parsed.get("problem_states"),
            "active_problem": int(parsed.get("active_problem") or 0),
        }
    return {
        "problem_states": [
            {
                "language": str(parsed.get("language") or "java"),
                "testcases": parsed.get("testcases") if isinstance(parsed.get("testcases"), list) else [],
                "active_case": int(parsed.get("active_case") or 0),
                "active_tab": str(parsed.get("active_tab") or "testcase"),
                "result": parsed.get("result") if isinstance(parsed.get("result"), dict) else None,
                "code": "",
            }
        ],
        "active_problem": 0,
    }


def candidate_assessment(session: Session, candidate_id: str) -> tuple[Candidate, Invite, Assessment]:
    candidate = session.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    invite = session.get(Invite, candidate.invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    assessment = session.get(Assessment, invite.assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return candidate, invite, assessment


def blocked_by_previous_section(
    session: Session,
    candidate_id: str,
    assessment_id: str,
    section_id: str,
) -> Optional[dict[str, str]]:
    for section in get_assessment_sections(session, assessment_id):
        if section.id == section_id:
            return None
        attempt = attempt_or_404(session, candidate_id, section.id)
        recover_false_completed_attempt(session, attempt)
        auto_complete_if_deadline_passed(session, attempt)
        if attempt.status != "completed":
            return {"section_id": section.id, "section_name": section.title}
    return None


def recover_false_completed_attempt(session: Session, attempt: Attempt) -> None:
    # Automatic recovery for accidental auto-submit cases:
    # completed with zero score, no answers/code, and near-immediate submission.
    if attempt.status != "completed":
        return
    if attempt.score > 0:
        return
    if (attempt.code_submission or "").strip():
        return
    if not is_empty_answers(attempt.answers_json):
        return
    started = normalize_dt(attempt.started_at)
    submitted = normalize_dt(attempt.submitted_at)
    if started and submitted and (submitted - started).total_seconds() <= 30:
        attempt.status = "not_started"
        attempt.agreed_rules = False
        attempt.started_at = None
        attempt.deadline_at = None
        attempt.submitted_at = None
        session.add(attempt)
        session.commit()


def auto_complete_if_deadline_passed(session: Session, attempt: Attempt) -> None:
    deadline = normalize_dt(attempt.deadline_at)
    if attempt.status == "in_progress" and deadline and datetime.utcnow() > deadline:
        attempt.status = "completed"
        attempt.submitted_at = datetime.utcnow()
        session.add(attempt)
        session.commit()


# ---------- App ----------
app = FastAPI(title="AITS Hiring Assessment Platform")
app.include_router(jd_router, prefix="/api/jd", tags=["JD Agent"])
os.makedirs(MEDIA_UPLOAD_DIR, exist_ok=True)
app.mount("/media", StaticFiles(directory=MEDIA_UPLOAD_DIR), name="media")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    global GENERATION_WORKER_STARTED
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        # lightweight schema sync for existing DBs without migrations
        try:
            conn.execute(text("ALTER TABLE admin ADD COLUMN IF NOT EXISTS company_name VARCHAR"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE assessment ADD COLUMN IF NOT EXISTS admin_id VARCHAR"))
            conn.execute(text("ALTER TABLE assessment ADD COLUMN IF NOT EXISTS jd_text TEXT DEFAULT ''"))
            conn.execute(text("ALTER TABLE assessment ADD COLUMN IF NOT EXISTS generation_status VARCHAR DEFAULT 'ready'"))
            conn.execute(text("ALTER TABLE assessment ADD COLUMN IF NOT EXISTS generation_error TEXT DEFAULT ''"))
            conn.execute(text("ALTER TABLE assessment ADD COLUMN IF NOT EXISTS generated_sections_count INTEGER DEFAULT 0"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE assessmentsection ADD COLUMN IF NOT EXISTS config_json TEXT DEFAULT '{}'"))
        except Exception:
            pass
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_generationjob_status_available_at ON generationjob (status, available_at)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_generationjob_assessment_id ON generationjob (assessment_id)"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE questionhistory ADD COLUMN IF NOT EXISTS content_hash VARCHAR"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_questionhistory_admin_hash ON questionhistory (admin_id, content_hash)"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE candidate_profile_analysis ADD COLUMN IF NOT EXISTS exam_invite_id VARCHAR"))
            conn.execute(text("ALTER TABLE candidate_profile_analysis ADD COLUMN IF NOT EXISTS candidate_email VARCHAR"))
            conn.execute(text("ALTER TABLE candidate_profile_analysis ADD COLUMN IF NOT EXISTS candidate_name VARCHAR"))
            conn.execute(text("ALTER TABLE candidate_profile_analysis ADD COLUMN IF NOT EXISTS github_score DOUBLE PRECISION DEFAULT 0"))
            conn.execute(text("ALTER TABLE candidate_profile_analysis ADD COLUMN IF NOT EXISTS leetcode_score DOUBLE PRECISION DEFAULT 0"))
            conn.execute(text("ALTER TABLE candidate_profile_analysis ADD COLUMN IF NOT EXISTS resume_score DOUBLE PRECISION DEFAULT 0"))
            conn.execute(text("ALTER TABLE candidate_profile_analysis ADD COLUMN IF NOT EXISTS profile_score DOUBLE PRECISION DEFAULT 0"))
            conn.execute(text("ALTER TABLE candidate_profile_analysis ADD COLUMN IF NOT EXISTS skills JSONB DEFAULT '[]'::jsonb"))
            conn.execute(text("ALTER TABLE candidate_profile_analysis ADD COLUMN IF NOT EXISTS summary_json TEXT DEFAULT '{}'"))
            conn.execute(text("ALTER TABLE candidate_profile_analysis ADD COLUMN IF NOT EXISTS raw_response_json TEXT DEFAULT '{}'"))
            conn.execute(text("ALTER TABLE candidate_profile_analysis ADD COLUMN IF NOT EXISTS parser_status VARCHAR DEFAULT 'pending'"))
            conn.execute(text("ALTER TABLE candidate_profile_analysis ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"))
            conn.execute(text("UPDATE candidate_profile_analysis SET summary_json = '{}' WHERE summary_json IS NULL"))
            conn.execute(text("UPDATE candidate_profile_analysis SET raw_response_json = '{}' WHERE raw_response_json IS NULL"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE interviewschedule ADD COLUMN IF NOT EXISTS assessment_id VARCHAR"))
            conn.execute(text("ALTER TABLE interviewschedule ADD COLUMN IF NOT EXISTS invite_id VARCHAR"))
            conn.execute(text("ALTER TABLE interviewschedule ADD COLUMN IF NOT EXISTS candidate_id VARCHAR"))
            conn.execute(text("ALTER TABLE interviewschedule ADD COLUMN IF NOT EXISTS candidate_name VARCHAR"))
            conn.execute(text("ALTER TABLE interviewschedule ADD COLUMN IF NOT EXISTS candidate_email VARCHAR"))
            conn.execute(text("ALTER TABLE interviewschedule ADD COLUMN IF NOT EXISTS interviewer_email VARCHAR"))
            conn.execute(text("ALTER TABLE interviewschedule ADD COLUMN IF NOT EXISTS interview_datetime TIMESTAMP"))
            conn.execute(text("ALTER TABLE interviewschedule ADD COLUMN IF NOT EXISTS duration INTEGER DEFAULT 30"))
            conn.execute(text("ALTER TABLE interviewschedule ADD COLUMN IF NOT EXISTS meeting_id VARCHAR"))
            conn.execute(text("ALTER TABLE interviewschedule ADD COLUMN IF NOT EXISTS meeting_link VARCHAR"))
            conn.execute(text("ALTER TABLE interviewschedule ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'Scheduled'"))
            conn.execute(text("ALTER TABLE interviewschedule ADD COLUMN IF NOT EXISTS rating INTEGER"))
            conn.execute(text("ALTER TABLE interviewschedule ADD COLUMN IF NOT EXISTS feedback TEXT DEFAULT ''"))
            conn.execute(text("ALTER TABLE interviewschedule ADD COLUMN IF NOT EXISTS ai_summary TEXT DEFAULT ''"))
            conn.execute(text("ALTER TABLE interviewschedule ADD COLUMN IF NOT EXISTS result VARCHAR"))
            conn.execute(text("ALTER TABLE interviewschedule ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"))
            conn.execute(text("ALTER TABLE interviewschedule ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE attempt ADD COLUMN IF NOT EXISTS violation_count INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE attempt ADD COLUMN IF NOT EXISTS cheating_flag BOOLEAN DEFAULT FALSE"))
            conn.execute(text("ALTER TABLE attempt ADD COLUMN IF NOT EXISTS proctor_event_counts_json TEXT DEFAULT '{}'"))
            conn.execute(text("UPDATE attempt SET violation_count = 0 WHERE violation_count IS NULL"))
            conn.execute(text("UPDATE attempt SET cheating_flag = FALSE WHERE cheating_flag IS NULL"))
            conn.execute(text("UPDATE attempt SET proctor_event_counts_json = '{}' WHERE proctor_event_counts_json IS NULL"))
        except Exception:
            pass
    with Session(engine) as session:
        for history in session.exec(select(QuestionHistory).where((QuestionHistory.content_hash == "") | (QuestionHistory.content_hash.is_(None)))).all():
            history.content_hash = question_history_hash(history.raw_text)
            session.add(history)
        for section_data in DEFAULT_SECTIONS:
            existing = session.exec(select(Section).where(Section.key == section_data["key"])).first()
            if not existing:
                session.add(Section(**section_data))
            else:
                existing.title = section_data["title"]
                existing.section_type = section_data["section_type"]
                existing.duration_minutes = section_data["duration_minutes"]
                existing.description = section_data["description"]
                session.add(existing)
        session.commit()
    GENERATION_WORKER_STARTED = False


@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.on_event("shutdown")
def on_shutdown() -> None:
    GENERATION_STOP_EVENT.set()


# ---------- Auth ----------
@app.post("/api/auth/signup")
def admin_signup(payload: SignupPayload, session: Session = Depends(get_session)):
    existing = session.exec(select(Admin).where(Admin.email == payload.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    admin = Admin(
        full_name=payload.full_name,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        company_name=payload.company_name.strip(),
    )
    session.add(admin)
    session.commit()
    session.refresh(admin)

    token = create_token(admin)
    return {
        "token": token,
        "admin": {
            "id": admin.id,
            "full_name": admin.full_name,
            "email": admin.email,
            "company_name": admin.company_name,
        },
        "needs_company_profile": False,
    }


@app.post("/api/auth/login")
def admin_login(payload: LoginPayload, session: Session = Depends(get_session)):
    admin = session.exec(select(Admin).where(Admin.email == payload.email.lower())).first()
    if not admin or not admin.password_hash or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(admin)
    return {
        "token": token,
        "admin": {
            "id": admin.id,
            "full_name": admin.full_name,
            "email": admin.email,
            "company_name": admin.company_name,
        },
        "needs_company_profile": not bool((admin.company_name or "").strip()),
    }


@app.post("/api/admin/login")
def admin_login_legacy(payload: LoginPayload, session: Session = Depends(get_session)):
    return admin_login(payload, session)


@app.post("/api/admin/signup")
def admin_signup_legacy(payload: AdminSignupPayload, session: Session = Depends(get_session)):
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    full_name = (payload.full_name or "").strip() or payload.email.split("@")[0]
    existing = session.exec(select(Admin).where(Admin.email == payload.email.lower())).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    admin = Admin(
        full_name=full_name,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        company_name=None,
    )
    session.add(admin)
    session.commit()
    session.refresh(admin)
    token = create_token(admin)
    return {
        "token": token,
        "admin": {
            "id": admin.id,
            "full_name": admin.full_name,
            "email": admin.email,
            "company_name": admin.company_name,
        },
        "needs_company_profile": True,
    }


@app.post("/api/auth/google")
def admin_google(payload: GoogleAuthPayload, session: Session = Depends(get_session)):
    try:
        info = id_token.verify_oauth2_token(payload.credential, google_requests.Request(), GOOGLE_CLIENT_ID)
    except Exception as exc:
        print(f"[google-auth-failed] {exc}")
        raise HTTPException(status_code=401, detail=f"Google OAuth verification failed: {exc}") from exc

    email = info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Google account email not available")

    sub = info.get("sub")
    name = info.get("name") or email.split("@")[0]

    admin = session.exec(select(Admin).where(Admin.email == email.lower())).first()
    if not admin:
        admin = Admin(full_name=name, email=email.lower(), google_sub=sub)
        session.add(admin)
    else:
        admin.google_sub = sub
        session.add(admin)

    session.commit()
    session.refresh(admin)

    token = create_token(admin)
    return {
        "token": token,
        "admin": {
            "id": admin.id,
            "full_name": admin.full_name,
            "email": admin.email,
            "company_name": admin.company_name,
        },
        "needs_company_profile": not bool((admin.company_name or "").strip()),
    }


@app.post("/api/admin/google-login")
def admin_google_legacy(payload: GoogleAuthPayload, session: Session = Depends(get_session)):
    return admin_google(payload, session)


@app.post("/api/admin/forgot-password")
def admin_forgot_password(payload: ForgotPasswordPayload, session: Session = Depends(get_session)):
    admin = session.exec(select(Admin).where(Admin.email == payload.email.lower())).first()
    if admin:
        reset_token = AdminPasswordResetToken(
            admin_id=admin.id,
            token=secrets.token_urlsafe(32),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        session.add(reset_token)
        session.commit()
        link = f"{FRONTEND_URL}/admin/reset-password?token={reset_token.token}"
        try:
            send_password_reset_email(admin.full_name or admin.email, admin.email, link)
        except Exception as exc:
            print(f"[mail-failed] Password reset for {admin.email}: {exc}")
    return {"ok": True}


@app.post("/api/admin/reset-password")
def admin_reset_password(payload: ResetPasswordPayload, session: Session = Depends(get_session)):
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    reset_token = session.exec(
        select(AdminPasswordResetToken).where(AdminPasswordResetToken.token == payload.token)
    ).first()
    if not reset_token or reset_token.used or normalize_dt(reset_token.expires_at) < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Reset token is invalid or expired")
    admin = session.get(Admin, reset_token.admin_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")

    admin.password_hash = hash_password(payload.password)
    reset_token.used = True
    session.add(admin)
    session.add(reset_token)
    session.commit()
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(admin: Admin = Depends(current_admin)):
    return {
        "id": admin.id,
        "full_name": admin.full_name,
        "email": admin.email,
        "company_name": admin.company_name,
    }


@app.post("/api/auth/company-profile")
def set_company_profile(
    payload: CompanyProfilePayload,
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
):
    company = (payload.company_name or "").strip()
    if not company:
        raise HTTPException(status_code=400, detail="Company name is required")
    admin.company_name = company
    session.add(admin)
    session.commit()
    session.refresh(admin)
    return {
        "ok": True,
        "admin": {
            "id": admin.id,
            "full_name": admin.full_name,
            "email": admin.email,
            "company_name": admin.company_name,
        },
    }


@app.post("/schedule-interview")
@app.post("/api/schedule-interview")
def schedule_interview(
    payload: InterviewSchedulePayload,
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
):
    if payload.duration not in {30, 45, 60}:
        raise HTTPException(status_code=400, detail="Duration must be 30, 45, or 60 minutes")

    interview_at = parse_interview_datetime(payload.interview_datetime)

    invite: Optional[Invite] = None
    assessment: Optional[Assessment] = None
    if payload.assessment_id:
        assessment = assessment_for_admin(session, payload.assessment_id, admin.id)
    if payload.invite_id:
        invite = session.get(Invite, payload.invite_id)
        if not invite:
            raise HTTPException(status_code=404, detail="Candidate invite not found")
        assessment = session.get(Assessment, invite.assessment_id)
        if not assessment or assessment.admin_id != admin.id:
            raise HTTPException(status_code=404, detail="Assessment not found")
    if assessment and not invite:
        invite = session.exec(
            select(Invite).where(
                Invite.assessment_id == assessment.id,
                Invite.email == payload.candidate_email.lower(),
            )
        ).first()
    if not invite or not assessment:
        raise HTTPException(status_code=404, detail="Candidate invite not found")

    existing = latest_interview_record(session, invite.id)
    if existing and existing.status == "Scheduled":
        raise HTTPException(status_code=400, detail="An interview is already scheduled for this candidate")

    candidate = session.exec(select(Candidate).where(Candidate.invite_id == invite.id)).first()
    meeting_id = f"interview-{uuid4().hex}"
    meeting_link = f"https://meet.jit.si/{meeting_id}"
    interview = InterviewSchedule(
        assessment_id=assessment.id,
        invite_id=invite.id,
        candidate_id=candidate.id if candidate else None,
        candidate_name=payload.candidate_name.strip() or invite.full_name,
        candidate_email=payload.candidate_email.lower(),
        interviewer_email=payload.interviewer_email.lower(),
        interview_datetime=interview_at,
        duration=payload.duration,
        meeting_id=meeting_id,
        meeting_link=meeting_link,
        status="Scheduled",
        updated_at=datetime.utcnow(),
    )
    session.add(interview)
    session.commit()
    session.refresh(interview)

    email_status = send_interview_schedule_emails(
        candidate_name=interview.candidate_name,
        candidate_email=interview.candidate_email,
        interviewer_email=interview.interviewer_email,
        interview_datetime=interview.interview_datetime,
        duration=interview.duration,
        meeting_id=interview.meeting_id,
        meeting_link=interview.meeting_link,
    )
    return {
        "ok": True,
        "message": "Interview scheduled successfully",
        "interview": serialize_interview(interview),
        "emails": email_status,
    }


@app.post("/submit-feedback")
@app.post("/api/submit-feedback")
def submit_feedback(
    payload: InterviewFeedbackPayload,
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
):
    if not 1 <= payload.rating <= 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    normalized_result = (payload.result or "").strip().title()
    if normalized_result and normalized_result not in {"Selected", "Rejected"}:
        raise HTTPException(status_code=400, detail="Result must be Selected or Rejected")

    interview: Optional[InterviewSchedule] = None
    if payload.interview_id:
        interview = session.get(InterviewSchedule, payload.interview_id)
    elif payload.invite_id:
        interview = latest_interview_record(session, payload.invite_id)
    else:
        interview = session.exec(
            select(InterviewSchedule)
            .where(InterviewSchedule.candidate_email == payload.candidate_email.lower())
            .order_by(InterviewSchedule.interview_datetime.desc(), InterviewSchedule.created_at.desc())
        ).first()

    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    assessment = session.get(Assessment, interview.assessment_id)
    if not assessment or assessment.admin_id != admin.id:
        raise HTTPException(status_code=404, detail="Interview not found")

    cleaned_feedback = payload.feedback.strip()
    interview.rating = payload.rating
    interview.feedback = cleaned_feedback
    interview.ai_summary = summarize_interview_feedback(
        candidate_name=interview.candidate_name,
        rating=payload.rating,
        result=normalized_result or "Pending",
        feedback=cleaned_feedback,
    )
    if normalized_result:
        interview.result = normalized_result
    interview.status = "Completed"
    interview.completed_at = datetime.utcnow()
    interview.updated_at = datetime.utcnow()
    session.add(interview)
    session.commit()
    session.refresh(interview)

    return {
        "ok": True,
        "message": "Interview feedback submitted",
        "interview": serialize_interview(interview),
    }


@app.post("/api/send-interview-decision")
def send_interview_decision(
    payload: InterviewDecisionPayload,
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
):
    normalized_decision = (payload.decision or "").strip().title()
    if normalized_decision not in {"Selected", "Rejected"}:
        raise HTTPException(status_code=400, detail="Decision must be Selected or Rejected")

    interview: Optional[InterviewSchedule] = None
    if payload.interview_id:
        interview = session.get(InterviewSchedule, payload.interview_id)
    elif payload.invite_id:
        interview = latest_interview_record(session, payload.invite_id)
    else:
        interview = session.exec(
            select(InterviewSchedule)
            .where(InterviewSchedule.candidate_email == payload.candidate_email.lower())
            .order_by(InterviewSchedule.interview_datetime.desc(), InterviewSchedule.created_at.desc())
        ).first()

    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    assessment = session.get(Assessment, interview.assessment_id)
    if not assessment or assessment.admin_id != admin.id:
        raise HTTPException(status_code=404, detail="Interview not found")

    interview.result = normalized_decision
    interview.updated_at = datetime.utcnow()
    session.add(interview)
    session.commit()
    session.refresh(interview)

    email_status = send_interview_decision_email(
        candidate_name=interview.candidate_name,
        candidate_email=interview.candidate_email,
        assessment_name=assessment.name,
        decision=normalized_decision,
        company_name=admin.company_name or MAIL_FROM_NAME,
    )
    return {
        "ok": True,
        "message": f"{normalized_decision} email processed",
        "interview": serialize_interview(interview),
        "email": email_status,
    }


@app.get("/api/admin/assessments")
def list_assessments(admin: Admin = Depends(current_admin), session: Session = Depends(get_session)):
    assessments = session.exec(
        select(Assessment).where(Assessment.admin_id == admin.id).order_by(Assessment.created_at.desc())
    ).all()
    response = []
    for assessment in assessments:
        invites = session.exec(select(Invite).where(Invite.assessment_id == assessment.id)).all()
        response.append(
            {
                "id": assessment.id,
                "name": assessment.name,
                "slug": assessment.slug,
                "created_at": assessment.created_at,
                "candidate_count": len(invites),
                "is_finished": assessment.is_finished,
                "generation_status": assessment.generation_status,
                "generated_sections_count": assessment.generated_sections_count,
            }
        )
    return response

import pdfplumber
from docx import Document
import io

def extract_jd_text(file):

    filename = file.filename.lower()

    content = file.file.read()

    file_stream = io.BytesIO(content)

    # -------- PDF --------
    if filename.endswith(".pdf"):

        text = ""

        with pdfplumber.open(file_stream) as pdf:

            for page in pdf.pages:

                text += page.extract_text() or ""

        return text


    # -------- DOCX --------
    if filename.endswith(".docx"):

        doc = Document(file_stream)

        return "\n".join(p.text for p in doc.paragraphs)


    # -------- TXT --------
    if filename.endswith(".txt"):

        return content.decode("utf-8")


    return ""

@app.get("/api/admin/sections")
def list_sections(admin: Admin = Depends(current_admin), session: Session = Depends(get_session)):
    _ = admin
    sections = session.exec(select(Section).where(Section.key.in_(list(ACTIVE_SECTION_KEYS)))).all()
    order_map = {item["key"]: index for index, item in enumerate(DEFAULT_SECTIONS)}
    return sorted(sections, key=lambda section: order_map.get(section.key, 999))


@app.post("/api/admin/assessments")
async def create_assessment(
    name: str = Form(...),
    jd_file: UploadFile | None = File(default=None),
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
    
):
    base = slugify(name)
    slug = base
    counter = 1
    while session.exec(select(Assessment).where(Assessment.slug == slug)).first():
        counter += 1
        slug = f"{base}-{counter}"
    jd_text = extract_jd_text(jd_file) if jd_file else ""

    assessment = Assessment(
        name=name,
        slug=slug,
        admin_id=admin.id,
        jd_text=jd_text,
        generation_status="ready",
        generation_error="",
        generated_sections_count=len(ACTIVE_SECTION_KEYS),
        is_finished=True,
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    section_keys = recommended_section_keys_for_assessment(assessment)
    sections = session.exec(select(Section).where(Section.key.in_(section_keys))).all()
    for section in sections:
        empty_config = initial_section_config(section)
        session.add(
            build_assessment_section_link(
                assessment_id=assessment.id,
                section_id=section.id,
                config_json=json.dumps(empty_config),
            )
        )
    session.commit()

    return {
        "id": assessment.id,
        "name": assessment.name,
        "slug": assessment.slug,
        "generation_status": assessment.generation_status,
    }

@app.put("/api/admin/assessments/{assessment_id}/sections")
def assign_sections(
    assessment_id: str,
    payload: AssignSectionsPayload,
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
):
    assessment = assessment_for_admin(session, assessment_id, admin.id)
    section_ids = list(dict.fromkeys(payload.section_ids))
    if not section_ids:
        raise HTTPException(status_code=400, detail="Select at least one section")

    existing_links = {
        existing.section_id: existing.config_json
        for existing in session.exec(
            select(AssessmentSection).where(AssessmentSection.assessment_id == assessment_id)
        ).all()
    }

    sections = session.exec(select(Section).where(Section.id.in_(section_ids))).all()
    if len(sections) != len(section_ids):
        raise HTTPException(status_code=400, detail="One or more sections are invalid")

    for existing in session.exec(
        select(AssessmentSection).where(AssessmentSection.assessment_id == assessment_id)
    ).all():
        session.delete(existing)

    for section in sections:
        session.add(
            build_assessment_section_link(
                assessment_id=assessment_id,
                section_id=section.id,
                config_json=existing_links.get(section.id, json.dumps(initial_section_config(section))),
            )
        )

    assessment.generated_sections_count = len(section_ids)
    session.add(assessment)
    session.commit()
    return {"ok": True}


@app.get("/api/admin/assessments/{assessment_id}/sections/{section_id}/mcq-config")
def get_mcq_section_config(
    assessment_id: str,
    section_id: str,
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
):
    _ = assessment_for_admin(session, assessment_id, admin.id)
    section = resolve_assessment_mcq_section(session, assessment_id, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    link = ensure_assessment_section_link(session, assessment_id, section)

    config = parse_section_config(link.config_json if link else "")
    if not config.get("questions"):
        config = initial_section_config(section)
    questions = [normalize_mcq_question(section, item, idx) for idx, item in enumerate(config.get("questions", []))]
    display_count = mcq_display_count(config)
    return {
        "section": section,
        "questions": questions,
        "display_count": display_count if display_count is not None else len(questions),
        "assigned_question_ids": config.get("assigned_question_ids") if isinstance(config.get("assigned_question_ids"), list) else [],
    }


@app.put("/api/admin/assessments/{assessment_id}/sections/{section_id}/mcq-config")
def update_mcq_section_config(
    assessment_id: str,
    section_id: str,
    payload: McqSectionConfigPayload,
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
):
    _ = assessment_for_admin(session, assessment_id, admin.id)
    section = resolve_assessment_mcq_section(session, assessment_id, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    link = ensure_assessment_section_link(session, assessment_id, section)

    if not isinstance(payload.questions, list):
        raise HTTPException(status_code=400, detail="Questions must be a list")

    existing_config = parse_section_config(link.config_json if link else "")
    normalized_questions = [
        normalize_mcq_question(section, item, idx)
        for idx, item in enumerate(payload.questions)
    ]
    display_count = payload.display_count if payload.display_count is not None else len(normalized_questions)
    display_count = max(0, min(int(display_count), len(normalized_questions)))
    shuffled_questions = list(normalized_questions)
    random.shuffle(shuffled_questions)
    assigned_question_ids = [str(item.get("id")) for item in shuffled_questions[:display_count]]
    link.config_json = json.dumps(
        {
            "section": str(existing_config.get("section") or section.title),
            "questions": normalized_questions,
            "display_count": display_count,
            "assigned_question_ids": assigned_question_ids,
            "shared_media": normalize_shared_media(existing_config.get("shared_media")),
        }
    )

    session.add(link)
    session.commit()
    return {"ok": True, "question_count": len(normalized_questions)}


@app.post("/api/admin/assessments/{assessment_id}/sections/{section_id}/mcq-ai-generate")
def ai_generate_mcq_section_questions(
    assessment_id: str,
    section_id: str,
    payload: McqAIGeneratePayload,
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
):
    _ = assessment_for_admin(session, assessment_id, admin.id)
    section = resolve_assessment_mcq_section(session, assessment_id, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    count = max(1, min(int(payload.count or 1), 20))
    difficulty = str(payload.difficulty or "MEDIUM").upper()
    if difficulty not in {"EASY", "MEDIUM", "HARD"}:
        difficulty = "MEDIUM"
    return {"questions": generate_mcq_questions_with_nvidia(section, count, difficulty)}


@app.get("/api/admin/assessments/{assessment_id}/sections/{section_id}/verbal-config")
def get_verbal_section_config(
    assessment_id: str,
    section_id: str,
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
):
    _ = assessment_for_admin(session, assessment_id, admin.id)
    section = session.get(Section, section_id)
    if not section or section.section_type != "verbal":
        raise HTTPException(status_code=404, detail="Verbal section not found")
    link = ensure_assessment_section_link(session, assessment_id, section)
    config = parse_section_config(link.config_json if link else "")
    if not config:
        config = initial_section_config(section)
    return {"section": section, "config": normalize_verbal_config(section, config)}


@app.post("/api/admin/verbal-media-upload")
def upload_verbal_media(
    admin: Admin = Depends(current_admin),
    media_file: UploadFile = File(...),
):
    _ = admin
    content_type = str(media_file.content_type or "")
    if not (content_type.startswith("audio/") or content_type.startswith("video/")):
        raise HTTPException(status_code=400, detail="Only audio or video files are allowed")

    original_name = str(media_file.filename or "")
    _, ext = os.path.splitext(original_name)
    safe_ext = ext[:10] if ext else ""
    filename = f"{uuid4().hex}{safe_ext}"
    destination = os.path.join(MEDIA_UPLOAD_DIR, filename)

    with open(destination, "wb") as buffer:
        shutil.copyfileobj(media_file.file, buffer)

    media_type = "video" if content_type.startswith("video/") else "audio"
    return {"ok": True, "media_url": f"/media/{filename}", "media_type": media_type}


@app.post("/api/admin/verbal-ai/generate")
def generate_verbal_ai_content(
    payload: VerbalAIGeneratePayload,
    admin: Admin = Depends(current_admin),
):
    _ = admin
    count = max(1, min(int(payload.count or 1), 20))
    kind = str(payload.kind or "").strip()
    try:
        if kind == "audio_video":
            transcript = str(payload.transcript or "").strip()
            if not transcript:
                raise HTTPException(status_code=400, detail="Transcript is required for audio/video AI generation")
            return {"items": generate_audio_video_ai_questions(transcript, count)}
        if kind == "speaking":
            return {"items": generate_speaking_ai_prompts(count)}
        if kind == "writing":
            return {"items": generate_writing_ai_topics(count)}
        if kind == "fill_blanks":
            return {"items": generate_fill_blanks_ai_items(count)}
        raise HTTPException(status_code=400, detail="Unsupported verbal AI generation kind")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"NVIDIA verbal AI generation failed: {exc}") from exc


@app.put("/api/admin/assessments/{assessment_id}/sections/{section_id}/verbal-config")
def update_verbal_section_config(
    assessment_id: str,
    section_id: str,
    payload: VerbalSectionConfigPayload,
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
):
    _ = assessment_for_admin(session, assessment_id, admin.id)
    section = session.get(Section, section_id)
    if not section or section.section_type != "verbal":
        raise HTTPException(status_code=404, detail="Verbal section not found")
    link = ensure_assessment_section_link(session, assessment_id, section)
    link.config_json = json.dumps(normalize_verbal_config(section, payload.config or {}))
    session.add(link)
    session.commit()
    return {"ok": True}


@app.get("/api/admin/assessments/{assessment_id}")
def assessment_detail(
    assessment_id: str,
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
):
    assessment = assessment_for_admin(session, assessment_id, admin.id)

    sections = get_assessment_sections(session, assessment.id)
    section_links = session.exec(
        select(AssessmentSection).where(AssessmentSection.assessment_id == assessment.id)
    ).all()
    section_link_map = {link.section_id: link for link in section_links}
    invites = session.exec(select(Invite).where(Invite.assessment_id == assessment.id)).all()
    invite_ids = [item.id for item in invites]

    candidates_by_invite: dict[str, Candidate] = {}
    parser_by_invite: dict[str, CandidateProfileAnalysis] = {}
    interview_by_invite: dict[str, InterviewSchedule] = {}
    attempts_by_candidate_section: dict[tuple[str, str], Attempt] = {}

    if invite_ids:
        candidates = session.exec(select(Candidate).where(Candidate.invite_id.in_(invite_ids))).all()
        candidates_by_invite = {candidate.invite_id: candidate for candidate in candidates}

        parser_results = session.exec(
            select(CandidateProfileAnalysis).where(CandidateProfileAnalysis.exam_invite_id.in_(invite_ids))
        ).all()
        parser_by_invite = {result.exam_invite_id: result for result in parser_results}

        interviews = session.exec(select(InterviewSchedule).where(InterviewSchedule.invite_id.in_(invite_ids))).all()
        for interview in interviews:
            current = interview_by_invite.get(interview.invite_id)
            if not current:
                interview_by_invite[interview.invite_id] = interview
                continue
            current_key = (current.interview_datetime or datetime.min, current.created_at or datetime.min)
            next_key = (interview.interview_datetime or datetime.min, interview.created_at or datetime.min)
            if next_key > current_key:
                interview_by_invite[interview.invite_id] = interview

        candidate_ids = [candidate.id for candidate in candidates]
        section_ids = [section.id for section in sections]
        if candidate_ids and section_ids:
            attempts = session.exec(
                select(Attempt).where(
                    Attempt.candidate_id.in_(candidate_ids),
                    Attempt.section_id.in_(section_ids),
                )
            ).all()
            attempts_by_candidate_section = {
                (attempt.candidate_id, attempt.section_id): attempt for attempt in attempts
            }

    invite_rows = []
    for invite in invites:
        candidate = candidates_by_invite.get(invite.id)
        parser_result = parser_by_invite.get(invite.id)
        interview = interview_by_invite.get(invite.id)
        parser_summary = safe_json_object(parser_result.summary_json if parser_result else "{}")
        parser_raw = safe_json_object(parser_result.raw_response_json if parser_result else "{}")
        parser_details = parser_summary.get("details")
        if not isinstance(parser_details, dict):
            parser_details = parser_raw.get("details")
        if not isinstance(parser_details, dict):
            parser_details = {}
        resume_details = parser_details.get("resume") if isinstance(parser_details.get("resume"), dict) else {}
        parser_location = (
            str(parser_summary.get("location") or "").strip()
            or str(parser_raw.get("location") or "").strip()
            or str(resume_details.get("location") or "").strip()
        )
        candidate_skills = recommendation_skill_pool(parser_result, parser_summary)
        attempts = []
        total_score = 0.0
        total_max = 0.0
        total_violations = 0
        proctor_event_totals: dict[str, int] = {}
        last_updated = invite.created_at
        status = "invited"
        cheating_detected = False
        if parser_result and parser_result.updated_at:
            last_updated = max(last_updated, parser_result.updated_at)
        if interview and interview.updated_at:
            last_updated = max(last_updated, interview.updated_at)
        if candidate:
            for section in sections:
                attempt = attempts_by_candidate_section.get((candidate.id, section.id))
                if not attempt:
                    continue
                recover_false_completed_attempt(session, attempt)
                auto_complete_if_deadline_passed(session, attempt)
                if attempt.cheating_flag:
                    cheating_detected = True
                total_violations += int(attempt.violation_count or 0)
                event_counts = safe_json_object(attempt.proctor_event_counts_json)
                for event_key, event_value in event_counts.items():
                    proctor_event_totals[event_key] = int(proctor_event_totals.get(event_key, 0) or 0) + int(event_value or 0)
                attempts.append(
                    {
                        "section_id": section.id,
                        "section_name": section.title,
                        "score": attempt.score,
                        "max_score": attempt.max_score,
                        "status": attempt.status,
                        "violation_count": int(attempt.violation_count or 0),
                        "cheating_flag": bool(attempt.cheating_flag),
                        "proctor_event_counts": event_counts,
                    }
                )
                total_score += attempt.score
                total_max += attempt.max_score
                last_updated = max(last_updated, attempt.submitted_at or attempt.started_at or invite.created_at)
            if attempts and all(item["status"] == "completed" for item in attempts):
                status = "completed"
            elif any(item["status"] == "in_progress" for item in attempts):
                status = "in_progress"
            else:
                status = "registered"
            if cheating_detected:
                status = "cheating"
        jd_match = (
            parser_summary.get("jd_match")
            if isinstance(parser_summary.get("jd_match"), dict)
            else build_jd_match(assessment.jd_text or "", candidate_skills)
        )
        ai_recommendation = generate_ai_recommendation(
            jd_match=jd_match,
            profile_score=float(parser_summary.get("profile_score", parser_result.profile_score if parser_result else 0.0) or 0.0),
            exam_score=total_score,
            exam_max=total_max,
            interview_rating=interview.rating if interview and interview.rating is not None else None,
            interview_feedback=interview.feedback if interview else "",
            admin_result=interview.result if interview else None,
        )
        invite_rows.append(
            {
                "id": invite.id,
                "full_name": invite.full_name,
                "email": invite.email,
                "created_at": invite.created_at,
                "link": f"{FRONTEND_URL}/candidate/invite/{invite.token}",
                "status": status,
                "cheating_detected": cheating_detected,
                "violation_total": total_violations,
                "cheating_threshold": PROCTORING_VIOLATION_LIMIT,
                "status_reason": (
                    summarize_proctor_reason(total_violations, PROCTORING_VIOLATION_LIMIT, proctor_event_totals)
                    if cheating_detected
                    else ""
                ),
                "proctor_event_totals": proctor_event_totals,
                "last_updated": last_updated,
                "candidate": (
                    {
                        "id": candidate.id,
                        "full_name": candidate.full_name,
                        "email": candidate.email,
                    }
                    if candidate
                    else None
                ),
                "profile_parser": (
                    {
                        "status": parser_result.parser_status,
                        "github_score": parser_result.github_score,
                        "leetcode_score": parser_result.leetcode_score,
                        "resume_score": parser_result.resume_score,
                        "profile_score": parser_result.profile_score,
                        "skills": candidate_skills,
                        "jd_match": jd_match,
                        "decision": ai_recommendation["decision"],
                        "ai_score": ai_recommendation["score"],
                        "explanation": ai_recommendation["explanation"] or parser_summary.get("explanation", ""),
                        "location": parser_location,
                        "details": parser_details,
                        "updated_at": parser_result.updated_at,
                    }
                    if parser_result
                    else None
                ),
                "results": attempts,
                "total_score": total_score,
                "total_max_score": total_max,
                "interview": serialize_interview(interview),
            }
        )

    return {
        "id": assessment.id,
        "name": assessment.name,
        "slug": assessment.slug,
        "is_finished": assessment.is_finished,
        "generation_status": assessment.generation_status,
        "generation_error": assessment.generation_error,
        "generated_sections_count": assessment.generated_sections_count,
        "sections": [
            {
                "id": section.id,
                "key": section.key,
                "title": section.title,
                "section_type": section.section_type,
                "duration_minutes": section.duration_minutes,
                "description": section.description,
                "generated_count": count_generated_items(
                    parse_section_config(
                        (section_link_map.get(section.id).config_json if section_link_map.get(section.id) else "")
                    ),
                    section.key,
                ),
                "expected_count": section_expected_count(session, assessment.id, section),
                "has_custom_config": bool(
                    parse_section_config(
                        (section_link_map.get(section.id).config_json if section_link_map.get(section.id) else "")
                    )
                ),
            }
            for section in sections
        ],
        "invites": invite_rows,
    }


@app.get("/api/admin/assessments/slug/{assessment_slug}")
def assessment_detail_by_slug(
    assessment_slug: str,
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
):
    assessment = assessment_for_admin_slug(session, assessment_slug, admin.id)
    return assessment_detail(assessment.id, admin, session)


@app.get("/api/admin/assessments/{assessment_id}/candidates/{invite_id}/results")
def invite_results(
    assessment_id: str,
    invite_id: str,
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
):
    assessment = assessment_for_admin(session, assessment_id, admin.id)
    invite = session.get(Invite, invite_id)
    if not invite or invite.assessment_id != assessment.id:
        raise HTTPException(status_code=404, detail="Candidate invite not found")
    candidate = session.exec(select(Candidate).where(Candidate.invite_id == invite.id)).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate has not started the assessment")

    sections = get_assessment_sections(session, assessment.id)
    results = []
    for section in sections:
        attempt = attempt_or_404(session, candidate.id, section.id)
        auto_complete_if_deadline_passed(session, attempt)
        results.append(
            {
                "section_id": section.id,
                "section_name": section.title,
                "status": attempt.status,
                "score": attempt.score,
                "max_score": attempt.max_score,
            }
        )

    return {
        "candidate": {"id": candidate.id, "full_name": candidate.full_name, "email": candidate.email},
        "results": results,
    }


@app.delete("/api/admin/assessments/{assessment_id}")
def delete_assessment(
    assessment_id: str,
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
):
    assessment = assessment_for_admin(session, assessment_id, admin.id)
    session.exec(delete(GenerationJob).where(GenerationJob.assessment_id == assessment.id))
    invite_ids = session.exec(select(Invite.id).where(Invite.assessment_id == assessment.id)).all()
    if invite_ids:
        session.exec(delete(InterviewSchedule).where(InterviewSchedule.invite_id.in_(invite_ids)))
        candidate_ids = session.exec(select(Candidate.id).where(Candidate.invite_id.in_(invite_ids))).all()
        if candidate_ids:
            session.exec(delete(Attempt).where(Attempt.candidate_id.in_(candidate_ids)))
            session.exec(delete(Candidate).where(Candidate.id.in_(candidate_ids)))
        session.exec(delete(Invite).where(Invite.id.in_(invite_ids)))

    session.exec(delete(AssessmentSection).where(AssessmentSection.assessment_id == assessment.id))
    session.exec(delete(Assessment).where(Assessment.id == assessment.id))
    session.commit()
    return {"ok": True}


@app.delete("/api/admin/assessments/{assessment_id}/invites/{invite_id}")
def delete_invite(
    assessment_id: str,
    invite_id: str,
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
):
    assessment = assessment_for_admin(session, assessment_id, admin.id)
    invite = session.get(Invite, invite_id)
    if not invite or invite.assessment_id != assessment.id:
        raise HTTPException(status_code=404, detail="Candidate invite not found")
    session.exec(delete(InterviewSchedule).where(InterviewSchedule.invite_id == invite.id))
    candidate_ids = session.exec(select(Candidate.id).where(Candidate.invite_id == invite.id)).all()
    if candidate_ids:
        session.exec(delete(Attempt).where(Attempt.candidate_id.in_(candidate_ids)))
        session.exec(delete(Candidate).where(Candidate.id.in_(candidate_ids)))
    session.exec(delete(Invite).where(Invite.id == invite.id))
    session.commit()
    return {"ok": True}


@app.post("/api/admin/assessments/{assessment_id}/invite")
def invite_candidate(
    assessment_id: str,
    payload: InvitePayload,
    background_tasks: BackgroundTasks,
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
):
    assessment = assessment_for_admin(session, assessment_id, admin.id)
    if not assessment.is_finished:
        raise HTTPException(status_code=400, detail="Finish the assessment before inviting candidates")

    invite = Invite(
        assessment_id=assessment.id,
        full_name=payload.full_name,
        email=payload.email.lower(),
        token=secrets.token_urlsafe(24),
    )
    session.add(invite)
    session.commit()
    session.refresh(invite)

    link = f"{FRONTEND_URL}/candidate/invite/{invite.token}"
    background_tasks.add_task(
        send_invite_email,
        payload.full_name,
        payload.email,
        assessment.name,
        link,
        admin.company_name,
    )

    return {
        "invite": invite,
        "link": link,
        "mail": {"queued": True},
    }


@app.post("/api/admin/assessments/{assessment_id}/bulk-invite")
def bulk_invite_candidates(
    assessment_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    admin: Admin = Depends(current_admin),
    session: Session = Depends(get_session),
):
    assessment = assessment_for_admin(session, assessment_id, admin.id)
    if not assessment.is_finished:
        raise HTTPException(status_code=400, detail="Finish assessment first")

    import pandas as pd
    from io import BytesIO

    filename = (file.filename or "").lower()
    contents = file.file.read()

    if filename.endswith(".csv"):
        df = pd.read_csv(BytesIO(contents))
    elif filename.endswith(".xlsx"):
        df = pd.read_excel(BytesIO(contents), engine="openpyxl")
    else:
        raise HTTPException(status_code=400, detail="Only CSV and XLSX files are supported")

    required_columns = {"full_name", "email"}
    if not required_columns.issubset(set(df.columns)):
        raise HTTPException(status_code=400, detail="File must contain full_name and email columns")

    created = []
    invites_to_send: list[tuple[str, str, str]] = []
    for _, row in df.iterrows():
        invite = Invite(
            assessment_id=assessment.id,
            full_name=row["full_name"],
            email=row["email"].lower(),
            token=secrets.token_urlsafe(24),
        )
        session.add(invite)
        session.flush()
        link = f"{FRONTEND_URL}/candidate/invite/{invite.token}"
        invites_to_send.append((row["full_name"], row["email"], link))

        created.append({
            "name": row["full_name"],
            "email": row["email"],
            "link": link
        })

    session.commit()

    for full_name, email, link in invites_to_send:
        background_tasks.add_task(
            send_invite_email,
            full_name,
            email,
            assessment.name,
            link,
            admin.company_name,
        )

    return {
        "total_created": len(created),
        "emails_queued": len(invites_to_send),
        "invites": created
    }


# ---------- Candidate ----------
@app.get("/api/candidate/invite/{token}")
def candidate_invite_details(token: str, session: Session = Depends(get_session)):
    invite = session.exec(select(Invite).where(Invite.token == token)).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invalid invite link")
    assessment = session.get(Assessment, invite.assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    candidate = session.exec(select(Candidate).where(Candidate.invite_id == invite.id)).first()
    profile_analysis = candidate_profile_record(session, invite.id)
    already_taken = False
    if candidate:
        section_count = session.exec(
            select(AssessmentSection).where(AssessmentSection.assessment_id == assessment.id)
        ).all()
        completed_attempts = session.exec(
            select(Attempt).where(
                Attempt.candidate_id == candidate.id,
                Attempt.status == "completed",
            )
        ).all()
        already_taken = bool(section_count) and len(completed_attempts) >= len(section_count)

    return {
        "assessment": {"id": assessment.id, "name": assessment.name},
        "invite": {"full_name": invite.full_name, "email": invite.email},
        "sections": [],
        "candidate": candidate,
        "profile_completed": bool(profile_analysis and profile_analysis.parser_status == "completed"),
        "already_taken": already_taken,
        "contact_email": "balajichanda797@gmail.com",
    }


@app.post("/api/candidate/invite/{token}/signup")
def candidate_signup(token: str, payload: CandidateSignupPayload, session: Session = Depends(get_session)):
    invite = session.exec(select(Invite).where(Invite.token == token)).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invalid invite link")

    if payload.email.lower() != invite.email.lower():
        raise HTTPException(status_code=400, detail="Please use invited email address")

    existing = session.exec(select(Candidate).where(Candidate.invite_id == invite.id)).first()
    if existing and assessment_complete(session, existing.id, invite.assessment_id):
        raise HTTPException(status_code=409, detail="You have already taken this assessment.")

    candidate = ensure_candidate_and_attempts(session, invite, payload.full_name, payload.email.lower())
    profile = candidate_profile_record(session, invite.id)
    return {"candidate_id": candidate.id, "profile_completed": bool(profile and profile.parser_status == "completed")}


@app.get("/api/candidate/{candidate_id}/profile")
def get_candidate_profile(candidate_id: str, session: Session = Depends(get_session)):
    candidate, invite, assessment = candidate_assessment(session, candidate_id)
    profile = candidate_profile_record(session, invite.id)

    return {
        "candidate": {
            "id": candidate.id,
            "full_name": candidate.full_name,
            "email": candidate.email,
        },
        "assessment": {"id": assessment.id, "name": assessment.name},
        "invite_id": invite.id,
        "profile_completed": bool(profile and profile.parser_status == "completed"),
    }


@app.post("/candidate/profile")
def create_candidate_profile(
    background_tasks: BackgroundTasks,
    candidate_id: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    github_url: str = Form(...),
    leetcode_url: str = Form(...),
    resume_drive_link: Optional[str] = Form(default=None),
    resume_pdf: Optional[UploadFile] = File(default=None),
    session: Session = Depends(get_session),
):
    candidate, invite, _assessment = candidate_assessment(session, candidate_id)
    existing = candidate_profile_record(session, invite.id)
    validate_candidate_profile_inputs(
        first_name=first_name,
        last_name=last_name,
        github_url=github_url,
        leetcode_url=leetcode_url,
        resume_drive_link=resume_drive_link,
        resume_file=resume_pdf,
    )
    analysis = existing or CandidateProfileAnalysis(
        exam_invite_id=invite.id,
        candidate_email=candidate.email,
        candidate_name=f"{first_name.strip()} {last_name.strip()}".strip(),
        summary_json="{}",
        raw_response_json="{}",
    )
    analysis.candidate_email = candidate.email
    analysis.candidate_name = f"{first_name.strip()} {last_name.strip()}".strip()
    analysis.parser_status = "pending"
    analysis.summary_json = "{}"
    analysis.raw_response_json = "{}"
    analysis.updated_at = datetime.utcnow()
    session.add(analysis)
    session.commit()

    resume_pdf_bytes = None
    if resume_pdf and resume_pdf.filename:
        resume_pdf_bytes = resume_pdf.file.read()
    background_tasks.add_task(
        process_candidate_profile_analysis,
        analysis_id=analysis.id,
        invite_id=invite.id,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        email=candidate.email,
        github_url=github_url.strip(),
        leetcode_url=leetcode_url.strip(),
        resume_pdf_bytes=resume_pdf_bytes,
        resume_drive_link=(resume_drive_link or "").strip() or None,
    )

    next_meta = next_section(candidate_id, session)
    return {
        "ok": True,
        "candidate_id": candidate.id,
        "profile_processing": True,
        "next_section_id": next_meta.get("next_section_id"),
        "next_section_name": next_meta.get("next_section_name"),
        "redirect_to": f"/candidate/{candidate.id}/dashboard",
    }


@app.get("/api/candidate/{candidate_id}/dashboard")
def candidate_dashboard(candidate_id: str, session: Session = Depends(get_session)):
    candidate, invite, assessment = candidate_assessment(session, candidate_id)
    ensure_candidate_and_attempts(session, invite, candidate.full_name, candidate.email)
    profile = candidate_profile_record(session, invite.id)
    if not profile or profile.parser_status != "completed":
        return {
            "candidate": {"id": candidate.id, "full_name": candidate.full_name, "email": candidate.email},
            "assessment": {"id": assessment.id, "name": assessment.name},
            "profile_completed": False,
        }
    owner = session.get(Admin, assessment.admin_id) if assessment.admin_id else None

    sections = get_assessment_sections(session, assessment.id)
    cards = []
    unlocked = True
    for section in sections:
        attempt = session.exec(
            select(Attempt).where(
                Attempt.candidate_id == candidate.id,
                Attempt.section_id == section.id,
            )
        ).first()
        if not attempt:
            attempt = Attempt(
                candidate_id=candidate.id,
                section_id=section.id,
                max_score=default_attempt_max_score(session, invite.assessment_id, section),
            )
            session.add(attempt)
            session.commit()
            session.refresh(attempt)
        recover_false_completed_attempt(session, attempt)
        auto_complete_if_deadline_passed(session, attempt)
        cards.append(
            {
                "section": section,
                "attempt": {
                    "id": attempt.id,
                    "status": attempt.status,
                    "score": attempt.score,
                    "max_score": attempt.max_score,
                    "deadline_at": attempt.deadline_at,
                },
                "locked": not unlocked and attempt.status == "not_started",
            }
        )
        if attempt.status != "completed":
            unlocked = False

    remaining = [item for item in cards if item["attempt"]["status"] != "completed"]
    message = "Thank you for taking assessment." if not remaining else ""

    return {
        "candidate": {"id": candidate.id, "full_name": candidate.full_name, "email": candidate.email},
        "assessment": {"id": assessment.id, "name": assessment.name},
        "profile_completed": True,
        "invited_by": (owner.company_name if owner and owner.company_name else "AITS"),
        "sections": [
            {
                **item,
                "expected_count": section_expected_count(session, assessment.id, item["section"]),
                "generated_count": section_generated_count(session, assessment.id, item["section"]),
                "ready_threshold": section_ready_threshold(item["section"].key),
                "ready_for_candidate": section_ready_for_candidate(session, assessment.id, item["section"]),
            }
            for item in cards
        ],
        "message": message,
        "all_completed": not remaining,
        "next_section_id": remaining[0]["section"].id if remaining else None,
    }


@app.get("/api/candidate/{candidate_id}/next-section")
def next_section(candidate_id: str, session: Session = Depends(get_session)):
    candidate = session.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    invite = session.get(Invite, candidate.invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")

    for section in get_assessment_sections(session, invite.assessment_id):
        existing = session.exec(
            select(Attempt).where(
                Attempt.candidate_id == candidate.id,
                Attempt.section_id == section.id,
            )
        ).first()
        if not existing:
            session.add(
                Attempt(
                    candidate_id=candidate.id,
                    section_id=section.id,
                    max_score=default_attempt_max_score(session, invite.assessment_id, section),
                )
            )
    session.commit()

    for section in get_assessment_sections(session, invite.assessment_id):
        attempt = attempt_or_404(session, candidate_id, section.id)
        auto_complete_if_deadline_passed(session, attempt)
        if attempt.status != "completed" and not section_has_candidate_content(session, invite.assessment_id, section):
            auto_skip_empty_section(session, attempt)
        if attempt.status != "completed":
            return {"next_section_id": section.id, "next_section_name": section.title}

    return {"next_section_id": None, "next_section_name": None, "message": "Thank you for taking assessment."}


@app.get("/api/candidate/{candidate_id}/review")
def candidate_review(candidate_id: str, session: Session = Depends(get_session)):
    candidate, invite, assessment = candidate_assessment(session, candidate_id)
    ensure_candidate_and_attempts(session, invite, candidate.full_name, candidate.email)

    sections_payload: list[dict[str, Any]] = []
    for section in get_assessment_sections(session, assessment.id):
        attempt = attempt_or_404(session, candidate_id, section.id)
        recover_false_completed_attempt(session, attempt)
        auto_complete_if_deadline_passed(session, attempt)

        prompt: dict[str, Any] = {}
        preview: dict[str, Any] = {}
        parsed_answers = parse_attempt_state(attempt.answers_json)

        if section.section_type == "mcq":
            questions = questions_for_section(session, assessment.id, section)
            answers = extract_mcq_answers(attempt.answers_json)
            preview = {
                "questions": [
                    {
                        "id": item["id"],
                        "question": item["question"],
                        "selected_answer": answers.get(item["id"], ""),
                    }
                    for item in questions
                ]
            }
        elif section.section_type == "verbal":
            prompt = verbal_prompt_for_section(session, assessment.id, section)
            preview = {
                "listening_answers": parsed_answers.get("listening_answers", {}) if isinstance(parsed_answers.get("listening_answers"), dict) else {},
                "speaking_responses": parsed_answers.get("speaking_responses", []) if isinstance(parsed_answers.get("speaking_responses"), list) else [],
                "writing_responses": parsed_answers.get("writing_responses", []) if isinstance(parsed_answers.get("writing_responses"), list) else [],
                "drag_drop_answers": parsed_answers.get("drag_drop_answers", {}) if isinstance(parsed_answers.get("drag_drop_answers"), dict) else {},
            }
        else:
            prompt = coding_prompt_for_section(session, assessment.id, section)
            coding_state = extract_coding_state(attempt.answers_json)
            preview = {
                "problem_states": coding_state.get("problem_states", []),
                "last_submit_result": parsed_answers.get("last_submit_result", []) if isinstance(parsed_answers.get("last_submit_result"), list) else [],
            }

        sections_payload.append(
            {
                "section": section,
                "attempt": {
                    "status": attempt.status,
                    "score": attempt.score,
                    "max_score": attempt.max_score,
                },
                "prompt": prompt,
                "preview": preview,
            }
        )

    return {
        "candidate": {"id": candidate.id, "full_name": candidate.full_name, "email": candidate.email},
        "assessment": {"id": assessment.id, "name": assessment.name},
        "sections": sections_payload,
    }


@app.get("/api/candidate/{candidate_id}/sections/{section_id}/instructions")
def section_instructions(candidate_id: str, section_id: str, session: Session = Depends(get_session)):
    candidate, invite, assessment = candidate_assessment(session, candidate_id)
    section = session.get(Section, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Candidate or section not found")
    blocked = blocked_by_previous_section(session, candidate_id, assessment.id, section_id)
    if blocked:
        raise HTTPException(status_code=400, detail=f"Complete {blocked['section_name']} before starting this section.")
    if not section_ready_for_candidate(session, assessment.id, section):
        raise HTTPException(status_code=409, detail=f"{section.title} is still generating. Please wait for the first batch.")

    attempt = attempt_or_404(session, candidate_id, section_id)
    recover_false_completed_attempt(session, attempt)
    auto_complete_if_deadline_passed(session, attempt)

    if attempt.status == "completed":
        raise HTTPException(status_code=400, detail="Section already completed")

    return {
        "section": section,
        "generated_count": section_generated_count(session, assessment.id, section),
        "ready_threshold": section_ready_threshold(section.key),
        "rules": RULES,
        "already_agreed": attempt.agreed_rules,
        "status": attempt.status,
        "deadline_at": attempt.deadline_at,
        "candidate": {"id": candidate.id, "full_name": candidate.full_name, "email": candidate.email},
        "assessment": {"id": assessment.id, "name": assessment.name},
    }


@app.post("/api/candidate/{candidate_id}/sections/{section_id}/start")
def start_section(
    candidate_id: str,
    section_id: str,
    payload: StartSectionPayload,
    session: Session = Depends(get_session),
):
    candidate, invite, assessment = candidate_assessment(session, candidate_id)
    section = session.get(Section, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    blocked = blocked_by_previous_section(session, candidate_id, assessment.id, section_id)
    if blocked:
        raise HTTPException(status_code=400, detail=f"Complete {blocked['section_name']} before starting this section.")
    if not section_ready_for_candidate(session, assessment.id, section):
        raise HTTPException(status_code=409, detail=f"{section.title} is still generating. Please wait for the first batch.")

    attempt = attempt_or_404(session, candidate_id, section_id)
    recover_false_completed_attempt(session, attempt)
    auto_complete_if_deadline_passed(session, attempt)

    if attempt.status == "completed":
        raise HTTPException(status_code=400, detail="Section already completed")
    if not payload.agreed_rules:
        raise HTTPException(status_code=400, detail="Please agree to all rules")

    if attempt.status == "not_started":
        now = datetime.utcnow()
        attempt.status = "in_progress"
        attempt.started_at = now
        attempt.deadline_at = now + timedelta(minutes=section.duration_minutes)

    attempt.agreed_rules = True
    session.add(attempt)
    session.commit()

    return {"ok": True, "deadline_at": attempt.deadline_at}


@app.get("/api/candidate/{candidate_id}/sections/{section_id}/exam")
def get_exam(candidate_id: str, section_id: str, session: Session = Depends(get_session)):
    candidate, invite, assessment = candidate_assessment(session, candidate_id)
    section = session.get(Section, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    blocked = blocked_by_previous_section(session, candidate_id, assessment.id, section_id)
    if blocked:
        raise HTTPException(status_code=400, detail=f"Complete {blocked['section_name']} before starting this section.")
    if not section_ready_for_candidate(session, assessment.id, section):
        raise HTTPException(status_code=409, detail=f"{section.title} is still generating. Please wait for the first batch.")

    attempt = attempt_or_404(session, candidate_id, section_id)
    recover_false_completed_attempt(session, attempt)
    auto_complete_if_deadline_passed(session, attempt)

    if attempt.status != "in_progress":
        raise HTTPException(status_code=400, detail="Section not active")

    if section.section_type == "mcq":
        questions = questions_for_section(session, invite.assessment_id, section)
        link = get_assessment_section_link(session, invite.assessment_id, section.id)
        parsed_config = parse_section_config(link.config_json if link else "")
        shared_media = normalize_shared_media(parsed_config.get("shared_media"))
        return {
            "section": section,
            "deadline_at": attempt.deadline_at,
            "generation_status": assessment.generation_status,
            "expected_count": section_expected_count(session, invite.assessment_id, section),
            "generated_count": len(questions),
            "candidate": {"id": candidate.id, "full_name": candidate.full_name, "email": candidate.email},
            "saved_answers": extract_mcq_answers(attempt.answers_json),
            "saved_state": {
                "current_index": int(parse_attempt_state(attempt.answers_json).get("current_index") or 0),
            },
            "questions": [
                {
                    "id": q["id"],
                    "passage": q["passage"],
                    "question": q["question"],
                    "options": q["options"],
                    "audio": q.get("audio") or shared_media_for_question(shared_media, str(q["id"])).get("audio") or "",
                    "video": q.get("video") or shared_media_for_question(shared_media, str(q["id"])).get("video") or "",
                    "image": q.get("image") or "",
                }
                for q in questions
            ],
        }

    if section.section_type == "verbal":
        prompt = verbal_prompt_for_section(session, invite.assessment_id, section)
        return {
            "section": section,
            "deadline_at": attempt.deadline_at,
            "generation_status": assessment.generation_status,
            "expected_count": default_attempt_max_score(session, invite.assessment_id, section),
            "generated_count": count_generated_items(prompt, section.key),
            "candidate": {"id": candidate.id, "full_name": candidate.full_name, "email": candidate.email},
            "saved_state": parse_attempt_state(attempt.answers_json),
            "prompt": prompt,
        }

    prompt = coding_prompt_for_section(session, invite.assessment_id, section)

    return {
        "section": section,
        "deadline_at": attempt.deadline_at,
        "generation_status": assessment.generation_status,
        "expected_count": section_expected_count(session, invite.assessment_id, section),
        "generated_count": len(prompt.get("problems") if isinstance(prompt.get("problems"), list) else [prompt] if prompt else []),
        "candidate": {"id": candidate.id, "full_name": candidate.full_name, "email": candidate.email},
        "saved_state": extract_coding_state(attempt.answers_json),
        "prompt": prompt,
        "runtime_availability": runtime_availability(),
    }


@app.post("/api/candidate/{candidate_id}/sections/{section_id}/submit-mcq")
def submit_mcq(
    candidate_id: str,
    section_id: str,
    payload: SubmitMcqPayload,
    session: Session = Depends(get_session),
):
    section = session.get(Section, section_id)
    if not section or section.section_type != "mcq":
        raise HTTPException(status_code=400, detail="Invalid section")

    attempt = attempt_or_404(session, candidate_id, section_id)
    auto_complete_if_deadline_passed(session, attempt)

    if attempt.status != "in_progress":
        raise HTTPException(status_code=400, detail="Section not active")

    candidate = session.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    invite = session.get(Invite, candidate.invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")

    questions = questions_for_section(session, invite.assessment_id, section)
    score = 0
    for item in questions:
        if payload.answers.get(item["id"]) == item["answer"]:
            score += 1

    attempt.score = float(score)
    attempt.max_score = float(len(questions))
    attempt.answers_json = json.dumps(payload.answers)
    attempt.status = "completed"
    attempt.submitted_at = datetime.utcnow()
    session.add(attempt)
    session.commit()

    next_meta = next_section_meta(session, candidate_id, invite.assessment_id, section_id)
    return {"ok": True, "score": attempt.score, "max_score": attempt.max_score, **next_meta}


@app.post("/api/candidate/{candidate_id}/sections/{section_id}/submit-verbal")
def submit_verbal(
    candidate_id: str,
    section_id: str,
    payload: SubmitVerbalPayload,
    session: Session = Depends(get_session),
):
    section = session.get(Section, section_id)
    if not section or section.section_type != "verbal":
        raise HTTPException(status_code=400, detail="Invalid section")

    attempt = attempt_or_404(session, candidate_id, section_id)
    auto_complete_if_deadline_passed(session, attempt)
    if attempt.status != "in_progress":
        raise HTTPException(status_code=400, detail="Section not active")

    candidate = session.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    invite = session.get(Invite, candidate.invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")

    prompt = verbal_prompt_for_section(session, invite.assessment_id, section)
    score = 0.0
    max_score = 0.0

    for block in prompt.get("listening_blocks") or []:
        block_questions = [item for item in (block.get("questions") or []) if isinstance(item, dict) and str(item.get("prompt") or "").strip()]
        if block_questions:
            for question in block_questions:
                max_score += 1
                response = str(payload.listening_answers.get(question.get("id")) or "")
                if response and response == str(question.get("answer") or ""):
                    score += 1
        else:
            max_score += 1
            response = str(payload.listening_answers.get(block.get("id")) or "")
            if response:
                score += 1

    for task in prompt.get("speaking_tasks") or []:
        max_score += 1
        response = next((item for item in payload.speaking_responses if str(item.get("id")) == str(task.get("id"))), None)
        if response:
            transcript = str(response.get("transcript") or "").strip()
            audio_url = str(response.get("audio_url") or "").strip()
            if transcript:
                similarity = verbal_similarity_score(transcript, task.get("prompt") or "")
                score += round(min(1.0, similarity), 2)
            elif audio_url:
                score += 1

    for task in prompt.get("writing_tasks") or []:
        max_score += 1
        response = next((item for item in payload.writing_responses if str(item.get("id")) == str(task.get("id"))), None)
        if response:
            text_value = str(response.get("text") or "").strip()
            word_count = len([item for item in re.findall(r"\b\w+\b", text_value) if item])
            sentence_count = len([item for item in re.split(r"[.!?]+", text_value) if item.strip()])
            meets_length = word_count >= int(task.get("min_words") or 80)
            score += min(1.0, (0.6 if meets_length else word_count / max(1, int(task.get("min_words") or 80))) + (0.4 if sentence_count >= 3 else sentence_count / 3 * 0.4))

    for task in prompt.get("drag_drop_questions") or []:
        max_score += 1
        answer = payload.drag_drop_answers.get(task.get("id"), [])
        if answer == (task.get("answer_order") or []):
            score += 1

    attempt.score = round(score, 2)
    attempt.max_score = max_score or 1
    attempt.answers_json = json.dumps(payload.dict())
    attempt.status = "completed"
    attempt.submitted_at = datetime.utcnow()
    session.add(attempt)
    session.commit()

    next_meta = next_section_meta(session, candidate_id, invite.assessment_id, section_id)
    return {"ok": True, "score": attempt.score, "max_score": attempt.max_score, **next_meta}


@app.post("/api/candidate/{candidate_id}/sections/{section_id}/save-mcq")
def save_mcq_progress(
    candidate_id: str,
    section_id: str,
    payload: SaveMcqProgressPayload,
    session: Session = Depends(get_session),
):
    section = session.get(Section, section_id)
    if not section or section.section_type != "mcq":
        raise HTTPException(status_code=400, detail="Invalid section")

    attempt = attempt_or_404(session, candidate_id, section_id)
    auto_complete_if_deadline_passed(session, attempt)
    if attempt.status != "in_progress":
        raise HTTPException(status_code=400, detail="Section not active")

    attempt.answers_json = json.dumps(
        {
            "answers": payload.answers,
            "current_index": payload.current_index,
        }
    )
    session.add(attempt)
    session.commit()
    return {"ok": True}


@app.post("/api/candidate/{candidate_id}/sections/{section_id}/submit-coding")
def submit_coding(
    candidate_id: str,
    section_id: str,
    payload: SubmitCodingPayload,
    session: Session = Depends(get_session),
):
    section = session.get(Section, section_id)
    if not section or section.section_type != "coding":
        raise HTTPException(status_code=400, detail="Invalid section")

    attempt = attempt_or_404(session, candidate_id, section_id)
    auto_complete_if_deadline_passed(session, attempt)

    if attempt.status != "in_progress":
        raise HTTPException(status_code=400, detail="Section not active")

    candidate = session.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    invite = session.get(Invite, candidate.invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")

    prompt = coding_prompt_for_section(session, invite.assessment_id, section)
    problems = prompt.get("problems") if isinstance(prompt.get("problems"), list) else [prompt]
    problem_states = payload.problem_states or []
    total_passed = 0
    total_tests = 0
    combined_results = []
    combined_code: list[str] = []
    for index, problem in enumerate(problems):
        state = problem_states[index] if index < len(problem_states) and isinstance(problem_states[index], dict) else {}
        language = str(state.get("language") or (problem.get("supported_languages") or ["java"])[0])
        code = str(state.get("code") or problem.get("starter_code") or "")
        judge_result = judge_code(
            language=language,
            code=code,
            tests=problem.get("hidden_tests", []),
            prompt=problem,
            reveal_expected=False,
        )
        combined_results.append({"problem_id": problem.get("id") or f"problem-{index + 1}", "summary": judge_result["summary"]})
        total_passed += int(judge_result["summary"]["passed"])
        total_tests += int(judge_result["summary"]["total"])
        combined_code.append(f"// Problem {index + 1} ({language})\n{code}")

    attempt.code_submission = "\n\n".join(combined_code)
    attempt.score = float(total_passed)
    attempt.max_score = float(total_tests)
    attempt.status = "completed"
    attempt.submitted_at = datetime.utcnow()
    attempt.answers_json = json.dumps(
        {
            **parse_attempt_state(attempt.answers_json),
            "problem_states": problem_states,
            "last_submit_result": combined_results,
        }
    )
    session.add(attempt)
    session.commit()

    next_meta = next_section_meta(session, candidate_id, invite.assessment_id, section_id)
    return {
        "ok": True,
        "score": attempt.score,
        "max_score": attempt.max_score,
        "judge": combined_results,
        **next_meta,
    }


@app.post("/api/candidate/{candidate_id}/sections/{section_id}/save-coding")
def save_coding_progress(
    candidate_id: str,
    section_id: str,
    payload: SaveCodingProgressPayload,
    session: Session = Depends(get_session),
):
    section = session.get(Section, section_id)
    if not section or section.section_type != "coding":
        raise HTTPException(status_code=400, detail="Invalid section")

    attempt = attempt_or_404(session, candidate_id, section_id)
    auto_complete_if_deadline_passed(session, attempt)
    if attempt.status != "in_progress":
        raise HTTPException(status_code=400, detail="Section not active")

    joined_code = []
    for index, state in enumerate(payload.problem_states):
        if isinstance(state, dict):
            joined_code.append(f"// Problem {index + 1}\n{str(state.get('code') or '')}")
    attempt.code_submission = "\n\n".join(joined_code)
    attempt.answers_json = json.dumps(
        {
            "problem_states": payload.problem_states,
            "active_problem": payload.active_problem,
        }
    )
    session.add(attempt)
    session.commit()
    return {"ok": True}


@app.post("/api/candidate/{candidate_id}/sections/{section_id}/run-coding")
def run_coding(
    candidate_id: str,
    section_id: str,
    payload: RunCodingPayload,
    session: Session = Depends(get_session),
):
    section = session.get(Section, section_id)
    if not section or section.section_type != "coding":
        raise HTTPException(status_code=400, detail="Invalid section")

    attempt = attempt_or_404(session, candidate_id, section_id)
    auto_complete_if_deadline_passed(session, attempt)
    if attempt.status != "in_progress":
        raise HTTPException(status_code=400, detail="Section not active")

    candidate, invite, _ = candidate_assessment(session, candidate_id)
    _ = candidate
    prompt = coding_prompt_for_section(session, invite.assessment_id, section)
    active_problem = coding_problem_by_index(prompt, payload.problem_index)
    tests = hydrate_visible_coding_tests(active_problem, payload.testcases or active_problem.get("testcases", []))
    result = judge_code(
        language=payload.language,
        code=payload.code,
        tests=tests,
        prompt=active_problem,
        reveal_expected=True,
    )
    hidden_result = judge_code(
        language=payload.language,
        code=payload.code,
        tests=active_problem.get("hidden_tests", []),
        prompt=active_problem,
        reveal_expected=False,
    )
    return {
        **result,
        "hidden_summary": hidden_result.get("summary", {}),
    }


@app.post("/api/proctoring/check")
def proctoring_check(payload: ProctorPayload):
    frame = payload.image or payload.frame
    if not frame:
        raise HTTPException(status_code=400, detail="Frame payload is required")
    return check_proctoring_frame(frame, payload.candidate_id)


@app.post("/api/proctor/analyze")
def proctor_analyze(payload: ProctorPayload):
    frame = payload.image or payload.frame
    if not frame:
        raise HTTPException(status_code=400, detail="Frame payload is required")
    result = check_proctoring_frame(frame, payload.candidate_id)
    return {
        "faces": int(result.get("faces", 0)),
        "multiple_faces": bool(result.get("multiple_faces", False)),
        "mobile": bool(result.get("mobile", False)),
    }


@app.get("/api/proctoring/warmup")
def proctoring_warmup():
    engine = get_engine()
    return engine.public_status()


@app.post("/api/proctoring/event")
def proctoring_event(payload: ProctorEventPayload):
    counted_events = {
        "tab_switch",
        "fullscreen_exit",
        "right_click",
        "blocked_shortcut",
        "screenshot_attempt",
        "clipboard_blocked",
        "background_capture",
        "mobile_detected",
        "multiple_faces",
        "no_face",
    }
    violation_count = None
    cheating_flag = None
    if payload.candidate_id and payload.section_id and payload.event in counted_events:
        with Session(engine) as session:
            attempt = session.exec(
                select(Attempt).where(
                    Attempt.candidate_id == payload.candidate_id,
                    Attempt.section_id == payload.section_id,
                )
            ).first()
            if attempt:
                event_counts = safe_json_object(attempt.proctor_event_counts_json)
                event_counts[payload.event] = int(event_counts.get(payload.event, 0) or 0) + 1
                attempt.proctor_event_counts_json = json.dumps(event_counts)
                attempt.violation_count = int(attempt.violation_count or 0) + 1
                if attempt.violation_count >= PROCTORING_VIOLATION_LIMIT:
                    attempt.cheating_flag = True
                violation_count = attempt.violation_count
                cheating_flag = bool(attempt.cheating_flag)
                session.add(attempt)
                session.commit()

    print(
        "[proctoring-event]",
        json.dumps(
            {
                "candidate_id": payload.candidate_id,
                "section_id": payload.section_id,
                "event": payload.event,
                "detail": payload.detail,
                "violation_count": violation_count,
                "cheating_flag": cheating_flag,
                "at": datetime.utcnow().isoformat(),
            }
        ),
    )
    return {"ok": True, "violation_count": violation_count, "cheating_flag": cheating_flag}
