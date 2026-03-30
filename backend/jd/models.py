from sqlalchemy import Column, Integer, String, Text, DateTime
import datetime
from .database import Base


class JobRecord(Base):

    __tablename__ = "agent_jobs"

    id = Column(Integer, primary_key=True, index=True)

    role = Column(String(255))

    must_have_skills = Column(Text)

    good_to_have_skills = Column(Text)

    experience_required = Column(String(100))

    created_at = Column(DateTime, default=datetime.datetime.utcnow)