# talent_management/ai_passport_generator.py

import json
import re
from .interview_bot.llm_utils import call_llm_api

# (The _create_concise_qa_summary helper function is fine as it is)
def _create_concise_qa_summary(interview_report_json: dict) -> str:
    qa_transcript = interview_report_json.get('full_qa_transcript', [])
    if not qa_transcript:
        return "No Q&A transcript available."
    summary_parts = []
    for qa_pair in qa_transcript:
        question = qa_pair.get('question_text', 'No question text.')
        answer = qa_pair.get('answer', 'No answer provided.')
        summary_parts.append(f"Q: {question[:300]}")
        summary_parts.append(f"A: {answer[:600]}")
    return "\n".join(summary_parts)


def generate_skills_passport_data(interview_report_json: dict, resume_json: dict) -> dict:
    """
    Analyzes interview and resume data to generate insights AND scores for a Skills Passport.
    """
    full_qa_transcript_summary = _create_concise_qa_summary(interview_report_json)
    
    interview_context = (
        f"Position Applied For: {interview_report_json.get('position_applied')}\n"
        f"Candidate Experience Level: {interview_report_json.get('candidate_experience')}\n"
        # ✅ NEW: Pass the original specialization list to the AI
        f"Identified Candidate Specializations: {json.dumps(interview_report_json.get('aiml_specialization', []))}"
    )

    resume_skills_list = resume_json.get('skills', [])
    resume_projects_list = resume_json.get('projects', [])
    resume_certifications_list = resume_json.get('verified_certifications', [])
    
    resume_text_summary = (
        f"Candidate Name: {resume_json.get('name')}\n"
        f"Professional Summary: {resume_json.get('summary')}\n"
        f"Current Location: {resume_json.get('location', 'Not specified')}"
    )

    # --- ✅ FINAL, HIGHLY-DETAILED PROMPT ---
    prompt = f"""
    You are an expert HR and Senior Technical Analyst AI. Your critical task is to generate a structured "Skills Passport" by **analyzing and scoring the raw interview transcript** and resume data.

    **Context for Analysis:**

    1.  **Core Interview Context:**
        ```
        {interview_context}
        ```

    2.  **Full Interview Transcript (Questions & Answers):**
        ```
        {full_qa_transcript_summary}
        ```

    3.  **Candidate's Resume Data (JSON):**
        ```json
        {{
            "summary": "{resume_text_summary}",
            "skills": {json.dumps(resume_skills_list)},
            "projects": {json.dumps(resume_projects_list, indent=2)},
            "certifications": {json.dumps(resume_certifications_list, indent=2)}
        }}
        ```

    **Your Task & Step-by-Step Generation Rules:**
    Based *only* on the data above, generate the missing components for the Skills Passport in **strict JSON format**.

    1.  **`communication_skills_score`**: Analyze the **Full Interview Transcript**. Evaluate clarity, conciseness, and professionalism. Assign a score (0-100). Low scores for "i dont know" or poor answers.
    2.  **`technical_readiness_score`**: Analyze the transcript for technical questions and answers. Also consider resume `skills` and `projects`. Assign an overall technical score (0-100).
    3.  **`specialization_scores`**: Look at the "Identified Candidate Specializations" in the Core Interview Context. For **each** specialization listed there, find relevant questions/answers in the transcript and assign a specific score (0-100). If no relevant questions were asked for a specialization, assign a score of 0.
    4.  **`relocation_score`**: Analyze the "Current Location" in the resume data. If a specific city/country is mentioned, assign a score of 40. If it says "Not specified," assign 10.
    5.  **`cultural_adaptability_score`**: Based on the tone and collaborative nature of answers in the transcript, assign a score (0-100).
    6.  **`rated_certifications`**: This is a crucial two-step analysis. For EACH certification in the resume data:
        a. Find evidence in the **Full Interview Transcript** where the candidate discusses topics related to that certification (e.g., discusses cloud architecture for an AWS cert).
        b. Based on how well they answered those related questions, assign a `validation_score` (0-100). This score reflects how well their interview performance **validates** their on-paper certification. If no related topics were discussed, the score should be lower (e.g., 50, indicating it's unverified by this interview).
    7.  **`ai_powered_summary` & `key_strengths`**: Generate these based on all available data.

    **JSON Structure to Generate:**
    {{
        "communication_skills_score": <integer>,
        "technical_readiness_score": <integer>,
        "specialization_scores": {{ "specialization_name_1": <integer>, "specialization_name_2": <integer> }},
        "relocation_score": <integer>,
        "cultural_adaptability_score": <integer>,
        "ai_powered_summary": "<string>",
        "key_strengths": ["<string>", ...],
        "frameworks_tools": [{{ "name": "<string>", "projects": <integer>, "proficiency": <integer, 1-5> }}],
        "rated_certifications": [
            {{
                "name": "<string, from input>",
                "issued_by": "<string, from input>",
                "validation_score": <integer, 0-100, **YOUR ANALYSIS of how the interview validates the cert**>
            }}
        ]
    }}
    """

    print("[AI Passport Generator]: Calling LLM with final prompt for all scores and ratings...")
    generated_text = call_llm_api(prompt, output_max_tokens=2500)

    if not generated_text:
        print("[AI Passport Generator]: Error - No response from LLM.")
        return None

    try:
        json_match = re.search(r'\{.*\}', generated_text, re.DOTALL)
        if not json_match:
            raise json.JSONDecodeError("No JSON object found in the response.", generated_text, 0)
        
        json_string = json_match.group(0)
        parsed_data = json.loads(json_string)
        return parsed_data
    except (json.JSONDecodeError, AttributeError) as e:
        print(f"[AI Passport Generator]: Error decoding LLM response. Raw text: {generated_text}")
        print(f"Error: {e}")
        return None





# # talent_management/ai_passport_generator.py

# import json
# import re
# from .interview_bot.llm_utils import call_llm_api

# def _create_concise_summary_from_report(interview_report_json: dict) -> str:
#     """
#     Helper function to distill a large interview report into a concise summary
#     for use in another LLM prompt.
#     """
#     summary_parts = [
#         f"Position Applied For: {interview_report_json.get('position_applied')}",
#         f"Candidate Experience: {interview_report_json.get('candidate_experience')}",
#         f"Global Readiness Score: {interview_report_json.get('global_readiness_score')}/100",
#         f"Communication Score: {interview_report_json.get('communication_overall_score')}/100",
#         f"Psychometric Score: {interview_report_json.get('psychometric_overall_score')}/100",
#         f"Language Proficiency Score: {interview_report_json.get('language_proficiency_score')}/100. Analysis: {interview_report_json.get('language_analysis')}"
#     ]
#     tech_scores = interview_report_json.get('technical_specialization_scores', {})
#     if tech_scores:
#         summary_parts.append("Technical Specialization Scores:")
#         for spec, score in tech_scores.items():
#             summary_parts.append(f"- {spec}: {score}/100")
#     round_analysis = interview_report_json.get('round_analysis_json', {})
#     if round_analysis:
#         summary_parts.append("\nKey Takeaways from Interview Rounds:")
#         for round_name, details in round_analysis.items():
#             if 'round_summary' in details:
#                 summary_parts.append(f"- {round_name.title()}: {details['round_summary']}")
#             elif isinstance(details, dict):
#                 for sub_round, sub_details in details.items():
#                      if 'round_summary' in sub_details:
#                          summary_parts.append(f"- {sub_round.replace('_', ' ').title()}: {sub_details['round_summary']}")
#     return "\n".join(summary_parts)

# def _create_concise_qa_summary(interview_report_json: dict) -> str:
#     """
#     Extracts a concise summary of the questions and answers from the interview transcript.
#     """
#     qa_transcript = interview_report_json.get('full_qa_transcript', [])
#     if not qa_transcript:
#         return "No Q&A transcript available."

#     summary_parts = []
#     for qa_pair in qa_transcript[:6]:
#         question = qa_pair.get('question_text', 'No question text.')
#         answer = qa_pair.get('answer', 'No answer provided.')
#         summary_parts.append(f"Q: {question[:250]}")
#         summary_parts.append(f"A: {answer[:500]}")
    
#     return "\n".join(summary_parts)


# def generate_skills_passport_data(interview_report_json: dict, resume_json: dict) -> dict:
#     """
#     Analyzes interview and resume data to generate insights for a Skills Passport.
#     """
#     concise_interview_summary = _create_concise_summary_from_report(interview_report_json)
#     concise_qa_summary = _create_concise_qa_summary(interview_report_json)

#     # Extract FULL lists for better analysis
#     resume_skills_list = resume_json.get('skills', [])
#     resume_projects_list = resume_json.get('projects', [])
#     # --- ✅ NEW: Extract certifications list ---
#     resume_certifications_list = resume_json.get('verified_certifications', [])
    
#     # Create a simple text summary for the other parts of the resume
#     resume_text_summary = (
#         f"Candidate Name: {resume_json.get('name')}\n"
#         f"Summary: {resume_json.get('summary')}\n"
#         # --- ✅ Use the corrected location from the serializer ---
#         f"Current Location: {resume_json.get('location', 'Not specified')}"
#     )

#     # --- ✅ UPDATE THE PROMPT to include certifications ---
#     prompt = f"""
#     You are an expert HR analyst AI. Your task is to analyze the provided data to generate a structured "Skills Passport".

#     **Analyze this context:**

#     1.  **Concise Mock Interview Summary (Scores & Feedback):**
#         ```
#         {concise_interview_summary}
#         ```
    
#     2.  **Sample Questions & Answers from the Interview:**
#         ```
#         {concise_qa_summary}
#         ```

#     3.  **Concise Resume Summary:**
#         ```
#         {resume_text_summary}
#         ```

#     4.  **Candidate's FULL Skill List (JSON):**
#         ```json
#         {json.dumps(resume_skills_list)}
#         ```

#     5.  **Candidate's FULL Project List (JSON):**
#         ```json
#         {json.dumps(resume_projects_list, indent=2)}
#         ```

#     6.  **Candidate's FULL Certifications List (JSON):**
#         ```json
#         {json.dumps(resume_certifications_list, indent=2)}
#         ```

#     **Your Task:**
#     Based *only* on the data above, generate the missing components for the Skills Passport. Pay close attention to the Sample Q&A for judging cultural fit and identifying soft skills. **Analyze the certifications list and incorporate valuable and relevant certifications into the ai_powered_summary and key_strengths.** Provide your output in **strict JSON format only**.

#     **JSON Structure to Generate:**
#     {{
#         "relocation_score": <integer, 0-100, based on 'Current Location' from the resume summary. If a specific city/country is mentioned, give a higher score (e.g., 70-90). If 'Not specified' or very generic, give a lower score (e.g., 30-50).>,
#         "cultural_adaptability_score": <integer, 0-100, based on the interview's communication/psychometric scores AND the tone/content of the Sample Q&A. Look for collaboration, problem-solving attitude, and clarity.>,
#         "ai_powered_summary": "<string, A concise 2-3 sentence professional summary highlighting the candidate's key achievements, skills, and most relevant certifications.>",
#         "key_strengths": ["<string>", "<string>", ...],  // A list of 4-5 key technical or soft skill tags identified from all context. Include tags for important certifications like 'AWS Certified'.
#         "frameworks_tools": [
#             {{
#                 "name": "<string, e.g., 'TensorFlow'>",
#                 "projects": <integer, COUNT how many projects in the FULL Project List use this tool in their 'technologies' array>,
#                 "proficiency": <integer, 1-5 star rating based on how frequently the skill appears across resume, projects, and certifications>
#             }}
#         ] // Generate this for the top 5-7 most prominent skills from the FULL Skill List.
#     }}
#     """

#     print("[AI Passport Generator]: Calling LLM with Q&A and Certifications to generate passport insights...")
#     generated_text = call_llm_api(prompt, output_max_tokens=1500)

#     if not generated_text:
#         print("[AI Passport Generator]: Error - No response from LLM.")
#         return None

#     try:
#         json_match = re.search(r'\{.*\}', generated_text, re.DOTALL)
#         if not json_match:
#             raise json.JSONDecodeError("No JSON object found in the response.", generated_text, 0)
        
#         json_string = json_match.group(0)
#         parsed_data = json.loads(json_string)
#         return parsed_data
#     except (json.JSONDecodeError, AttributeError) as e:
#         print(f"[AI Passport Generator]: Error decoding LLM response. Raw text: {generated_text}")
#         print(f"Error: {e}")
#         return None

