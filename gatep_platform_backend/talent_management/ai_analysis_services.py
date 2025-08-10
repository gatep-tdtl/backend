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
def generate_resume_review(resume_profile_text, target_role):
    """Generates an ATS-style review for a given resume profile text."""
    prompt = f"""
You are an expert ATS resume reviewer and career coach. Your analysis is critical, direct, and actionable.
Analyze the provided candidate profile against the requirements for the target role.

Generate a JSON object with the following structure:
{{
  "ATS_Compatibility": {{
    "score": "A number from 0-100. Score harshly. A score above 70 should be reserved for exceptionally well-structured, quantifiable, and keyword-rich profiles.",
    "top_issues": ["List the most critical issues affecting the score, such as vague descriptions, lack of metrics, or missing keywords."],
    "quick_tips": ["Actionable tips to fix the issues and improve the score."]
  }},
  "Content_Quality_Analysis": {{
    "summary": "A brief, critical summary of the profile's content quality, focusing on impact and clarity.",
    "top_strengths": ["List the strongest parts of the profile (e.g., strong project descriptions, clear career progression)."],
    "improvement_areas": ["List areas needing significant improvement (e.g., 'Work Experience needs more quantifiable achievements', 'Summary is too generic')."]
  }},
  "Keyword_Optimization": {{
    "missing_keywords": ["List crucial keywords and technologies for the '{target_role}' role that are missing or underrepresented in the profile."]
  }},
  "Format_and_Structure_Review": {{
    "format_score": "A number from 0-100 based on readability, clarity, and logical flow.",
    "missing_sections": ["Standard sections that are missing or weak (e.g., 'Projects', 'Skills', 'Certifications')."],
    "quick_suggestions": ["Tips for improving the structure (e.g., 'Move the Skills section higher', 'Use bullet points for responsibilities')."]
  }}
}}

---
Candidate Profile Text:
{resume_profile_text}

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

            # Try direct JSON parse, with a fallback to regex extraction
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




    ############# ai salary insights model below #############33
    import os
import re
import time
import json
import logging
from groq import Groq

# Use the Django-managed Groq client from your existing services if possible,
# or initialize it here. It will automatically use the GROQ_API_KEY from .env
try:
    client = Groq()
    MODEL_NAME = "llama3-70b-8192" # Use a more powerful model for complex JSON
except Exception as e:
    raise Exception("GROQ_API_KEY not found or invalid. Please set it in your .env file.")

# ----- Logging Setup -----
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ----- LLM Call with Retry and Sanitizing -----
def _call_llm(prompt, retries=3):
    """
    Internal helper to call the LLM with retry logic and JSON cleaning.
    """
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME, # Use the more capable model
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                response_format={"type": "json_object"} # Use JSON mode for reliability
            )
            raw_content = response.choices[0].message.content.strip()
            
            # JSON mode is reliable, but we keep a fallback just in case
            try:
                # Direct parsing, as JSON mode should guarantee a valid object string
                parsed = json.loads(raw_content)
                return raw_content # Return the raw string for the caller to parse
            except json.JSONDecodeError:
                logging.warning(f"JSON mode response was not valid JSON on attempt {attempt + 1}. Fallback parsing...")
                match = re.search(r'\{.*\}', raw_content, re.DOTALL)
                if match:
                    return match.group(0)
                else:
                    logging.error(f"Could not find any JSON in the response: {raw_content}")
                    continue
       
        except Exception as e:
            logging.error(f"Groq API Error or other exception on attempt {attempt + 1}: {e}")
            time.sleep(5 + (2 ** attempt))
           
    logging.critical("All retry attempts failed. Could not get valid JSON from LLM.")
    return None # Return None on failure

# ----- STEP 1: Dynamic Location to Currency Mapping -----
def _map_locations_to_currencies(locations):
    locations_str = ", ".join(f'"{loc}"' for loc in locations)
    prompt = (
        f"For the following list of locations [{locations_str}], provide their primary 3-letter currency code (ISO 4217). "
        "Return a single JSON object where keys are the locations and values are the currency codes. "
        "For example, for 'USA', the value should be 'USD'. For 'Mumbai', it should be 'INR'. For 'EU', use 'EUR'."
        "Your response must be only the JSON object."
    )
    logging.info("Step 1: Mapping locations to currency codes...")
    json_string = _call_llm(prompt)
    if not json_string: return None
    try:
        currency_map = json.loads(json_string)
        logging.info(f"Successfully mapped currencies: {currency_map}")
        return currency_map
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse location-currency map from LLM: {e}")
        return None

# ----- STEP 2: Dynamic Currency Rates Fetcher -----
def _fetch_currency_rates_with_llm(currency_codes):
    if not currency_codes: return {}
    codes_to_fetch = [code for code in currency_codes if code != "INR"]
    if not codes_to_fetch: return {"INR": 1.0}
    codes_str = ", ".join(codes_to_fetch)
    prompt = (
        f"Provide the current exchange rates for the following currency codes against INR: {codes_str}. "
        "Return a JSON object with currency codes as keys and exchange rates (float) as values. "
        "Your response must be only the JSON object."
    )
    logging.info(f"Step 2: Fetching exchange rates for {codes_str}...")
    json_string = _call_llm(prompt)
    if not json_string: return {}
    try:
        rates = json.loads(json_string)
        rates["INR"] = 1.0
        logging.info(f"Successfully fetched rates: {rates}")
        return rates
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse currency rates from LLM: {e}")
        return {}

# ----- Universal Salary Parser -----
def _extract_currency_and_value(salary_str):
    if not isinstance(salary_str, str): return None, None
    # Enhanced regex to handle various formats
    match = re.search(r'([$€₹£¥]|S\$|CA\$|[A-Z]{3})?\s*([\d,.]+)\s*([KkMm]?)', salary_str.strip())
    if match:
        symbol_or_code, value_str, suffix = match.groups()
        value = float(value_str.replace(',', ''))
        multiplier = 1000 if suffix and suffix.lower() == 'k' else 1_000_000 if suffix and suffix.lower() == 'm' else 1
        return (symbol_or_code.strip() if symbol_or_code else None), value * multiplier
    return None, None

def _convert_to_inr(salary_str, location, location_currency_map, currency_rates):
    if not salary_str: return "N/A"
    symbol_or_code, amount = _extract_currency_and_value(salary_str)
    if amount is None: return "Invalid Format"
    
    # Determine currency code: explicit > location-based
    final_code = symbol_or_code if symbol_or_code else location_currency_map.get(location)
    
    if not final_code or final_code not in currency_rates:
        return f"Rate for '{final_code or 'Unknown'}' Unavailable"
        
    inr_value = amount * currency_rates.get(final_code, 0)
    return f"₹{inr_value:,.0f} (≈ {inr_value / 1_00_000:.2f} LPA)"

# ----- Main Data Fetcher -----
def _fetch_all_consolidated_data(main_roles, countries_list):
    roles_str = ", ".join(f"'{role}'" for role in main_roles)
    countries_str = ", ".join(countries_list)
    prompt = f"""
    You are a senior IT recruitment consultant and salary expert with deep knowledge of global compensation trends for 2024.
    Your task is to provide ACCURATE and REALISTIC salary and career information for professionals with **3-5 years of experience**.
 
    CRITICAL INSTRUCTION: Your generated salaries must be realistic. For example, a "Data Scientist" in "Banglore" should be in the range of ₹20LPA to ₹40LPA. A similar role in the "USA" should be around $120K to $180K. Reflect these market realities. Pay close attention to high-demand fields like "AI Engineer" in major tech hubs.
 
    Your entire response must be a single, complete, and valid JSON object.
 
    Generate a JSON object with keys for each of the following professional fields: [{roles_str}].
    For each field, create an object with these keys:
    - "sub_roles": an array of 5 common sub-roles.
    - "location_salary": an object where keys are countries from [{countries_str}] and values are objects with "average_salary".
    - "negotiation_tips": an array of 3-4 salary negotiation tips.
    - "market_trends": an array of 3-4 current market trends.
 
    Format all salary values with the correct currency symbol or 3-letter code and units (e.g., '$150K', '£90K', '₹2.5M'). Use snake_case for keys.
    """
    logging.info("Step 3: Fetching all consolidated salary and career data...")
    json_string = _call_llm(prompt)
    if not json_string: return None
    try:
        data = json.loads(json_string)
        logging.info("Successfully fetched and parsed consolidated data.")
        return data
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse consolidated JSON: {e}.")
        return None

# ----- Main Orchestration Function - THIS IS THE ONE YOU WILL IMPORT -----
def generate_salary_insights(roles, countries):
    """
    The main public function to generate salary insights for given roles and countries.
    This function will be called by the API view.
    """
    location_currency_map = _map_locations_to_currencies(countries)
    if not location_currency_map: return None
    
    required_codes = list(set(location_currency_map.values()))
    currency_rates = _fetch_currency_rates_with_llm(required_codes)
    if not currency_rates: return None
    
    consolidated_data_all_roles = _fetch_all_consolidated_data(roles, countries)
    if not consolidated_data_all_roles: return None
 
    logging.info("Step 4: Processing and converting all salary data...")
    final_results = {}
    
    for main_role, role_data in consolidated_data_all_roles.items():
        if main_role not in roles: continue # Ensure we only process requested roles
        
        # Process location-based salaries for the main role
        location_salaries = {}
        for location in countries:
            salary_str = role_data.get("location_salary", {}).get(location, {}).get("average_salary")
            location_salaries[location] = {
                "average_salary_local": salary_str or "N/A",
                "average_salary_inr": _convert_to_inr(salary_str, location, location_currency_map, currency_rates)
            }
            
        final_results[main_role] = {
            "sub_roles": role_data.get("sub_roles", []),
            "location_based_salaries": location_salaries,
            "negotiation_tips": role_data.get("negotiation_tips", []),
            "market_trends": role_data.get("market_trends", [])
        }

    logging.info("Salary insight analysis complete.")
    return final_results
#################ai salary insights model above #########################