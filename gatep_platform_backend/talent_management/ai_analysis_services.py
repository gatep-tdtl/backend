import os
import json
import re
from groq import Groq
import fitz  # PyMuPDF, which you already use in your views.py

# --- Configuration ---
# The Groq client will automatically use the GROQ_API_KEY environment variable.
# Ensure it's set in your .env file and loaded by Django.
try:
    client = Groq()
    MODEL_NAME = "llama3-70b-8192"
except Exception as e:
    raise Exception("GROQ_API_KEY not found or invalid. Please set it in your .env file.")

def _extract_json_from_response(response_text):
    """Safely extracts a JSON object from a string."""
    json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            print(f"Response was: {json_match.group(0)}")
            # Fallback: Return the raw text if JSON parsing fails, wrapped in an error structure
            return {"error": "Failed to parse LLM response as valid JSON.", "raw_response": json_match.group(0)}
    else:
        print("No JSON found in response.")
        print(f"Full response: {response_text}")
        return {"error": "No JSON object found in the LLM response.", "raw_response": response_text}

def extract_text_from_pdf_path(file_path):
    """Extracts text from a PDF file path using PyMuPDF (fitz)."""
    try:
        doc = fitz.open(file_path)
        text = "".join(page.get_text() for page in doc)
        doc.close()
        return text.strip()
    except Exception as e:
        print(f"Error extracting text from PDF path {file_path}: {e}")
        return ""

# --- Module 1: AI Resume Review ---
def generate_resume_review(resume_text, target_role):
    """Generates an ATS-style review for a given resume text."""
    prompt = f"""
You are an expert ATS resume reviewer. Your analysis is critical and direct.
If the resume has bad formatting, emojis, missing keywords, or messy sections, you MUST force the ATS_Compatibility score below 30.
Only give a score above 70 if it's exceptionally professional, quantifiable, and perfectly ATS-optimized for the target role.

Generate a JSON object with the following structure:
{{
  "ATS_Compatibility": {{
    "score": "A number from 0-100",
    "top_issues": ["List of the most critical issues affecting the score"],
    "quick_tips": ["Actionable tips to fix the issues"]
  }},
  "Content_Quality_Analysis": {{
    "summary": "A brief, critical summary of the resume's content quality.",
    "top_strengths": ["List of the strongest parts of the resume"],
    "improvement_areas": ["List of areas needing significant improvement"]
  }},
  "Keyword_Optimization": {{
    "missing_keywords": ["Crucial keywords for the target role that are missing"]
  }},
  "Format_and_Structure_Review": {{
    "format_score": "A number from 0-100 based on readability and ATS-friendliness",
    "missing_sections": ["Standard sections that are missing (e.g., 'Projects', 'Skills')"],
    "quick_suggestions": ["Tips for improving the layout and structure"]
  }}
}}

---
Resume Text:
{resume_text}

Target Role: {target_role}
---

Strict JSON Output:
"""
    res = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"} # Use JSON mode for reliability
    )
    response_text = res.choices[0].message.content
    return json.loads(response_text) # JSON mode guarantees valid JSON


# --- Module 2: Skill Gap Analysis ---
def generate_skill_gap_analysis(resume_skills, job_roles_on_portal):
    """Analyzes skill gaps between a candidate's resume and market demand."""
    prompt = f"""
You are an expert career coach specializing in the tech industry.
Compare the candidate's skills with the provided list of job roles.
Generate a JSON object with a realistic, actionable analysis.

JSON Structure:
{{
  "Current_Skill_Mapping": ["List of the main skills you identified from the resume"],
  "Market_Demand_Analysis": ["Top skills/technologies frequently appearing in the job roles that are MISSING from the resume"],
  "Learning_Path": ["A step-by-step learning plan to bridge the identified skill gaps. Be specific."],
  "Certification_Guidance": ["List of top 2-3 industry-recognized certifications or courses relevant for the missing skills"]
}}

---
Candidate's Resume Skills:
{resume_skills}

---
Job Roles Posted on Our Portal:
{job_roles_on_portal}
---

Strict JSON Output:
"""
    res = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    response_text = res.choices[0].message.content
    return json.loads(response_text)


# --- Module 3: Career Roadmap ---
def generate_career_roadmap(current_role, experience_years, interests, skills):
    """Generates a personalized career roadmap."""
    prompt = f"""
You are an expert career strategist and coach.
Based on the user's profile below, generate a realistic and personalized career roadmap in a JSON object.
The roadmap should be inspiring but grounded in reality. Do NOT use placeholders; fill all fields with real, valuable suggestions.

JSON Structure:
{{
  "Current_Position_Analysis": "A brief analysis of their current role and experience level.",
  "Next_Milestone_1_Year": {{
    "title": "A realistic job title they can aim for in 6-12 months.",
    "company_type": "The type of company they should target (e.g., 'Early-stage Startup', 'Mid-size Tech Company', 'FAANG')."
  }},
  "Long_Term_Goal_3_Years": {{
    "title": "A senior or specialized job title they can aim for in 2-3 years.",
    "company_type": "The type of company where this role is common."
  }},
  "Recommended_Actions": [
    {{
      "action": "Specific action to take (e.g., 'Master PyTorch for NLP applications').",
      "reason": "Why this action is critical for reaching the next milestone."
    }},
    {{
      "action": "Another specific action (e.g., 'Lead a small project from end-to-end').",
      "reason": "Why this helps develop skills needed for the long-term goal."
    }},
    {{
      "action": "A networking or personal branding action (e.g., 'Contribute to a well-known open-source library').",
      "reason": "How this builds visibility and credibility in the field."
    }}
  ]
}}

---
User Profile:
- Current Role/Most Recent Title: {current_role}
- Experience: {experience_years} years
- Key Skills: {skills}
- Stated Interests: {interests}
---

Strict JSON Output:
"""
    res = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    response_text = res.choices[0].message.content
    return json.loads(response_text)



# ...existing imports...
from groq import Groq
import os, json, re

# --- Configuration (reuse your existing Groq client setup) ---
client = Groq()
MODEL_NAME = "llama3-70b-8192"

def generate_multiple_roadmaps(
    current_role="Fresher / Entry-level candidate",
    experience_years=0,
    interests="",
    target_roles=None
):
    if target_roles is None:
        target_roles = []

    try:
        years = float(experience_years or 0)
    except (TypeError, ValueError):
        years = 0.0
    years = max(0.0, years)

    results = {}

    for role_target in target_roles:
        fresher_guidance = ""
        if years == 0:
            fresher_guidance = f"""
- The user is a fresher with no prior industry experience. Tailor the roadmap to highlight beginner-friendly and accessible entry points into the {role_target} role.
- Focus on foundational knowledge, practical exposure, and skill-building activities that do not require job experience.
- Recommend specific and credible internships, beginner-level certifications, relevant online courses, academic or self-initiated projects, open-source contributions, and participation in hackathons or coding communities.
- Emphasize the importance of a strong portfolio and personal branding (e.g., LinkedIn, GitHub, Kaggle) to demonstrate capability in the absence of work history.
- Avoid recommending mid-senior level roles or actions that assume prior professional experience.
"""

        prompt = f"""
You are a professional career advisor with deep industry knowledge across multiple domains.
Generate a comprehensive and realistic personalized career roadmap for an individual aspiring to become a **{role_target}**. The roadmap must be structured in the exact JSON format below.

JSON Format:
{{
  "Current_Position": "{current_role}",
  "Experience_Years": {years},
  "Target_Field": "{role_target}",
  "Next_Milestone": {{
    "title": "job title in 6-12 months",
    "company_type": "company type or location"
  }},
  "Long_Term_Goal": {{
    "title": "job title in 2-3 years",
    "company_type": "company type or location"
  }},
  "Recommended_Actions": [
    {{
      "action": "Action title",
      "reason": "Why this helps"
    }},
    {{
      "action": "Another action",
      "reason": "Why this helps"
    }}
  ]
}}

Rules:
- Be specific and realistic. Fill with real content, not placeholders.
- Assume the user has interests in: {interests}
Guidelines:
- DO NOT use placeholders. Output must contain meaningful, actionable, and realistic information.
- Customize advice based on the user’s current position: **{current_role}** and experience: **{years} years**.
- Tailor suggestions to the user's interests: **{interests}**.
- Recommend concrete job titles, roles, and types of companies at each stage.
- Recommended actions should include a mix of upskilling (courses, certifications), practical exposure (projects, internships), and visibility (portfolio, networking).

{fresher_guidance}
""".strip()

        try:
            res = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that outputs strict JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            response_text = res.choices[0].message.content.strip()

            try:
                parsed = json.loads(response_text)
                results[role_target] = parsed
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", response_text, re.DOTALL)
                if match:
                    try:
                        results[role_target] = json.loads(match.group(0))
                    except json.JSONDecodeError:
                        results[role_target] = {"error": "Invalid JSON from model"}
                else:
                    results[role_target] = {"error": "No JSON found"}
        except Exception as e:
            results[role_target] = {"error": str(e)}

    return results



from typing import Dict, List, Union

MODEL_NAME = "llama3-70b-8192"
client = Groq()  # Use your environment variable for the API key

def _ensure_text(skills: Union[str, List[str]]) -> str:
    if isinstance(skills, list):
        return ", ".join([s.strip() for s in skills if s and str(s).strip()])
    return str(skills).strip()

def _extract_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{(?:[^{}]|(?R))*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None

def generate_skill_gap_for_role(
    resume_skills: Union[str, List[str]],
    role: str,
    job_text_for_role: Union[str, List[str]]
) -> Dict:
    resume_text = _ensure_text(resume_skills)
    jobs_text = _ensure_text(job_text_for_role)

    prompt = f"""
You are an expert career coach.

GOAL:
Compare the candidate's resume skills to the job postings for the specific role below,
then return ONLY valid JSON with this exact structure and field names:

{{
  "Current_Skill_Mapping": [string, ...],
  "Market_Demand_Analysis": [string, ...],
  "Learning_Path": [string, ...],
  "Certification_Guidance": [string, ...]
}}

Rules:
- Output JSON only. No prose, no backticks, no comments.
- Keep items concise and actionable.
- In Market_Demand_Analysis, focus on high-signal, currently in-demand skills missing or weak in the resume relative to the role.
- Learning_Path should be step-by-step (ordered) and role-specific.
- Certification_Guidance should include concrete certs/courses (platform-agnostic where possible).

Target Role: {role}

Resume skills:
{resume_text}

Job postings (titles/descriptions) for this role:
{jobs_text}
""".strip()

    res = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    raw = res.choices[0].message.content
    data = _extract_json(raw)
    if not data:
        raise ValueError(f"Model did not return valid JSON for role '{role}'. Raw response:\n{raw}")
    return data

def generate_skill_gap_analysis_for_roles(
    resume_skills: Union[str, List[str]],
    selected_roles: List[str],
    jobs_index: Dict[str, Union[str, List[str]]]
) -> Dict[str, Dict]:
    result = {}
    for role in selected_roles:
        job_text = jobs_index.get(role) or ""
        analysis = generate_skill_gap_for_role(resume_skills, role, job_text)
        result[role] = analysis
    return result