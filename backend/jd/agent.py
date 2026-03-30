from .tools import extract_job_info


def hiring_agent(job_description):
    
    memory = {}

    data = extract_job_info(job_description)

    memory["role"] = data.get("role")

    memory["must_have_skills"] = data.get("must_have_skills")

    memory["good_to_have_skills"] = data.get("good_to_have_skills")

    memory["experience_required"] = data.get("experience_required")

    return memory