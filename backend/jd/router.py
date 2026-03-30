from fastapi import APIRouter, Form
from .database import SessionLocal, engine
from .models import Base, JobRecord
from .agent import hiring_agent
import json

router = APIRouter()

_JD_TABLES_READY = False


def ensure_jd_tables():
    global _JD_TABLES_READY
    if _JD_TABLES_READY:
        return
    Base.metadata.create_all(bind=engine)
    _JD_TABLES_READY = True




@router.post("/run-agent")
def run_agent(job_description: str = Form(...)):
    ensure_jd_tables()

    result = hiring_agent(job_description)

    db = SessionLocal()

    try:

        record = JobRecord(

            role=result["role"],

            must_have_skills=json.dumps(result["must_have_skills"]),

            good_to_have_skills=json.dumps(result["good_to_have_skills"]),

            experience_required=result["experience_required"]

        )

        db.add(record)

        db.commit()

        return {
            "status": "Saved successfully",
            "data": result
        }

    finally:
        db.close()


@router.get("/jobs")
def view_jobs():

    db = SessionLocal()

    jobs = db.query(JobRecord).all()

    db.close()

    results = []

    for j in jobs:

        results.append({

            "id": j.id,

            "role": j.role,

            "must_have_skills": json.loads(j.must_have_skills),

            "good_to_have_skills": json.loads(j.good_to_have_skills),

            "experience": j.experience_required

        })

    return results
