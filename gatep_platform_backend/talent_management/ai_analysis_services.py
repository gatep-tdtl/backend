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