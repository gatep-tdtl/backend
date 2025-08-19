# talent_management/ai_passport_generator.py

import json
import re
from .interview_bot.llm_utils import call_llm_api

def _create_concise_summary_from_report(interview_report_json: dict) -> str:
    """
    Helper function to distill a large interview report into a concise summary
    for use in another LLM prompt.
    """
    # (This function is good, no changes needed here)
    summary_parts = [
        f"Position Applied For: {interview_report_json.get('position_applied')}",
        f"Candidate Experience: {interview_report_json.get('candidate_experience')}",
        f"Global Readiness Score: {interview_report_json.get('global_readiness_score')}/100",
        f"Communication Score: {interview_report_json.get('communication_overall_score')}/100",
        f"Psychometric Score: {interview_report_json.get('psychometric_overall_score')}/100",
        f"Language Proficiency Score: {interview_report_json.get('language_proficiency_score')}/100. Analysis: {interview_report_json.get('language_analysis')}"
    ]
    tech_scores = interview_report_json.get('technical_specialization_scores', {})
    if tech_scores:
        summary_parts.append("Technical Specialization Scores:")
        for spec, score in tech_scores.items():
            summary_parts.append(f"- {spec}: {score}/100")
    round_analysis = interview_report_json.get('round_analysis_json', {})
    if round_analysis:
        summary_parts.append("\nKey Takeaways from Interview Rounds:")
        for round_name, details in round_analysis.items():
            if 'round_summary' in details:
                summary_parts.append(f"- {round_name.title()}: {details['round_summary']}")
            elif isinstance(details, dict):
                for sub_round, sub_details in details.items():
                     if 'round_summary' in sub_details:
                         summary_parts.append(f"- {sub_round.replace('_', ' ').title()}: {sub_details['round_summary']}")
    return "\n".join(summary_parts)

def _create_concise_qa_summary(interview_report_json: dict) -> str:
    """
    --- NEW FUNCTION ---
    Extracts a concise summary of the questions and answers from the interview transcript.
    """
    qa_transcript = interview_report_json.get('full_qa_transcript', [])
    if not qa_transcript:
        return "No Q&A transcript available."

    summary_parts = []
    # Limit to the first 6 Q&A pairs to keep the prompt size manageable,
    # focusing on early-round questions which are often about communication/psychometrics.
    for qa_pair in qa_transcript[:6]:
        question = qa_pair.get('question_text', 'No question text.')
        answer = qa_pair.get('answer', 'No answer provided.')
        # Truncate long questions/answers to be safe
        summary_parts.append(f"Q: {question[:250]}")
        summary_parts.append(f"A: {answer[:500]}")
    
    return "\n".join(summary_parts)


def generate_skills_passport_data(interview_report_json: dict, resume_json: dict) -> dict:
    """
    Analyzes interview and resume data to generate insights for a Skills Passport.
    """
    concise_interview_summary = _create_concise_summary_from_report(interview_report_json)
    
    # --- NEW: Get the concise Q&A summary ---
    concise_qa_summary = _create_concise_qa_summary(interview_report_json)

    # Extract FULL lists of skills and projects for better analysis
    resume_skills_list = resume_json.get('skills', [])
    resume_projects_list = resume_json.get('projects', [])
    # Create a simple text summary for the other parts of the resume
    resume_text_summary = (
        f"Candidate Name: {resume_json.get('name')}\n"
        f"Summary: {resume_json.get('summary')}\n"
        f"Preferred Location: {resume_json.get('preferred_location', 'Not specified')}"
    )

    # --- Use the NEW Q&A summary in the final prompt ---
    prompt = f"""
    You are an expert HR analyst AI. Your task is to analyze the provided data to generate a structured "Skills Passport".

    **Analyze this context:**

    1.  **Concise Mock Interview Summary (Scores & Feedback):**
        ```
        {concise_interview_summary}
        ```
    
    2.  **Sample Questions & Answers from the Interview:**
        ```
        {concise_qa_summary}
        ```

    3.  **Concise Resume Summary:**
        ```
        {resume_text_summary}
        ```

    4.  **Candidate's FULL Skill List (JSON):**
        ```json
        {json.dumps(resume_skills_list)}
        ```

    5.  **Candidate's FULL Project List (JSON):**
        ```json
        {json.dumps(resume_projects_list, indent=2)}
        ```

    **Your Task:**
    Based *only* on the data above, generate the missing components for the Skills Passport. Pay close attention to the Sample Q&A for judging cultural fit and identifying soft skills. Provide your output in **strict JSON format only**.

    **JSON Structure to Generate:**
    {{
        "relocation_score": <integer, 0-100, based on 'preferred_location' from the resume summary.>,
        "cultural_adaptability_score": <integer, 0-100, based on the interview's communication/psychometric scores AND the tone/content of the Sample Q&A. Look for collaboration, problem-solving attitude, and clarity.>,
        "ai_powered_summary": "<string, A concise 2-3 sentence professional summary highlighting the candidate's key achievements.>",
        "key_strengths": ["<string>", "<string>", ...],  // A list of 4-5 key technical or soft skill tags identified from all context, especially from the Q&A.
        "frameworks_tools": [
            {{
                "name": "<string, e.g., 'TensorFlow'>",
                "projects": <integer, COUNT how many projects in the FULL Project List use this tool in their 'technologies' array>,
                "proficiency": <integer, 1-5 star rating based on how frequently the skill appears in the resume and interview context>
            }}
        ] // Generate this for the top 5-7 most prominent skills from the FULL Skill List.
    }}
    """

    print("[AI Passport Generator]: Calling LLM with Q&A summary to generate passport insights...")
    generated_text = call_llm_api(prompt, output_max_tokens=1500)

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





