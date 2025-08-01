
# CORRECTED CODE - All top-level indentation removed

_B = 'content'
_A = 'meta-llama/Meta-Llama-3-70B-Instruct'
import os, fitz, json, re
from django.http import JsonResponse
from django.conf import settings
from huggingface_hub import InferenceClient
from .models import Resume, CustomUser
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
# talent_management/views.py
# ... (existing imports) ...
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status # Import status codes
from rest_framework.response import Response # ADD THIS LINE

# ... (rest of your views.py code) ...
# --- AI Analysis Service Imports (for the analysis views at the end) ---
from .ai_analysis_services import (
    generate_resume_review,
    extract_text_from_pdf_path,
    generate_skill_gap_analysis,
    generate_career_roadmap
)
# talent_management/views.py

_B = 'content'
_A = 'meta-llama/Meta-Llama-3-70B-Instruct'
import os, fitz, json, re
from django.http import JsonResponse
from django.conf import settings
from huggingface_hub import InferenceClient
from .models import Resume, CustomUser, MockInterviewResult # Ensure MockInterviewResult is imported
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
# talent_management/views.py
# ... (existing imports) ...
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status # Import status codes
from rest_framework.response import Response # ADD THIS LINE
from django.utils import timezone # Import timezone

# ... (rest of your views.py code) ...
# --- AI Analysis Service Imports (for the analysis views at the end) ---
from .ai_analysis_services import (
    generate_resume_review,
    extract_text_from_pdf_path,
    generate_skill_gap_analysis,
    generate_career_roadmap
)

# NEW: Import AIInterviewer from interview_bot
from .interview_bot.interviewer_logic import AIInterviewer, extract_specialized_skills
from .interview_bot.speech_utils import speak_text 
from .interview_bot.config import MOCK_INTERVIEW_POSITION # Import the position


# Get the CustomUser model
User = get_user_model()

HFF_TOKEN = os.getenv('HFF_TOKEN')
if not HFF_TOKEN:
    raise ValueError('HuggingFace token not set in environment (HFF_TOKEN). Please set it to proceed.')

# Constants for clarity
L = 'name'; M = 'email'; N = 'phone'; O = 'work_arrangement'; P = 'preferred_location'
Q = 'preferred_tech_stack'; R = 'dev_environment'; S = 'current_location'
T = 'aadhar_number'; U = 'passport_number'; V = 'current_company'
W = 'linkedin_url'; X = 'github_url'; Y = 'portfolio_url'
Z = 'stackoverflow_url'; a = 'medium_or_blog_url'
b = 'work_authorization'; c = 'criminal_record_disclosure'
d = 'volunteering_experience'; f = 'extracurriculars'
g = 'degree_name'; h = 'skills'; i = 'experience'
j = 'projects'; k = 'certifications'; l = 'awards'
m = 'publications'; n = 'open_source_contributions'
o = 'interests'; p = 'languages'; q = 'references'
s = 'professional_summary'; t = 'board_name'; u = 'institution_name'
v = 'legal'; K = 'year_passing'; D = 'score'
J = 'error'; I = 'links'; H = 'diploma'
G = 'twelfth'; F = 'tenth'; E = 'preferences'
C = 'degree'; A = 'education_details'; B = 'personal_info'

# --- ADD THIS HELPER FUNCTION HERE (if it's not already) ---
def safe_json_loads(field_value, default_value):
    """Safely loads a JSON string, returning a default value on error or if None."""
    if field_value:
        try:
            # Ensure it's a string before loading, as JSONField might return dict/list directly
            if isinstance(field_value, (dict, list)):
                return field_value
            return json.loads(field_value)
        except (json.JSONDecodeError, TypeError):
            pass # Fall through to return default_value
    return default_value


class ResumeAIPipeline:
    def __init__(self):
        """Initializes the AI pipeline with the Inference Client and other attributes."""
        self.client = InferenceClient(token=HFF_TOKEN)
        self.temp_pdf_paths = []

    # --- THIS IS THE MISSING METHOD THAT CAUSED THE ERROR ---
    def _extract_text_from_pdf(self, pdf_path):
        """
        Extracts all text from a PDF file using the fitz (PyMuPDF) library.
        """
        try:
            doc = fitz.open(pdf_path)
            full_text = "".join(page.get_text() for page in doc)
            doc.close()
            # Clean up excessive newlines for better LLM processing
            return re.sub(r'\s*\n\s*', '\n', full_text).strip()
        except Exception as e:
            print(f"Error extracting text from PDF at {pdf_path}: {e}")
            return "" # Return empty string on failure

    def _build_prompt(self, form_data, pdf_text):
        form_info_str = json.dumps(form_data, indent=2)
        # The prompt is intentionally verbose and detailed to guide the LLM effectively.
        # NOTE THE FIX: Every literal { and } is now doubled as {{ and }}
        return f'''
You are an AI Resume Builder. Your goal is to extract and structure comprehensive resume information. Combine the user's explicit form input with details from their old resume PDF. Prioritize form input for accuracy. If info is only in the PDF, extract it.

Return your output in **strict JSON format only**. Do NOT include any markdown (e.g., ```json), conversational text, or explanations. The JSON structure must follow this schema:
{{{{
    "personal_info": {{{{ "name": "...", "email": "...", "phone": "...", "current_location": "...", "current_area": "...", "permanent_area": "...", "current_city": "...", "permanent_city": "...", "current_district": "...", "permanent_district": "...", "current_state": "...", "permanent_state": "...", "current_country": "...", "permanent_country": "...", "aadhar_number": "...", "passport_number": "...", "current_company": "..." }}}},
    "links": {{{{ "linkedin_url": "...", "github_url": "...", "portfolio_url": "...", "stackoverflow_url": "...", "medium_or_blog_url": "..." }}}},
    "professional_summary": "A concise 3-4 sentence summary.",
    "skills": ["Skill 1", "Skill 2"],
    "experience": [{{{{ "title": "...", "company": "...", "duration": "...", "responsibilities": ["..."] }}}}],
    "projects": [{{{{ "name": "...", "description": "...", "url": "..." }}}}],
    "education_details": {{{{
        "degree": {{{{ "degree_name": "...", "institution_name": "...", "specialization": "...", "year_passing": "...", "score": "..." }}}},
        "diploma": {{{{ "course_name": "...", "institution_name": "...", "year_passing": "...", "score": "..." }}}},
        "twelfth": {{{{ "board_name": "...", "college_name": "...", "year_passing": "...", "score": "..." }}}},
        "tenth": {{{{ "board_name": "...", "school_name": "...", "year_passing": "...", "score": "..." }}}}
    }}}},
    "frameworks_tools": [{{{{ "name": "Tool/Framework", "rating": 5 }}}}],
    "diploma_details": [{{{{ "course_name": "...", "institution_name": "...", "year_passing": "...", "score": "..." }}}}],
    "degree_details": [{{{{ "degree_name": "...", "institution_name": "...", "specialization": "...", "year_passing": "...", "score": "..." }}}}],
    "certification_details": [{{{{ "name": "...", "issuer": "...", "date": "..." }}}}],
    "certification_photos": ["url1", "url2"],
    "work_preferences": ["Remote", "Flexible Hours"],
    "work_authorizations": ["Indian Citizen", "US B1/B2 Visa"],
    "professional_links": ["https://linkedin.com/in/yourprofile"],
    "certifications": ["Certification 1", "Certification 2"],
    "awards": ["Award 1"],
    "publications": ["Publication 1"],
    "open_source_contributions": ["Contribution 1"],
    "volunteering_experience": "Description...",
    "extracurriculars": "Description...",
    "languages": {{{{ "Language 1": "Proficiency" }}}},
    "preferences": {{{{ "work_arrangement": "...", "preferred_location": "...", "other_preferences": "..." }}}},
    "legal": {{{{ "work_authorization": "...", "criminal_record_disclosure": "..." }}}},
    "document_verification": "Status...",
    "interests": ["Interest 1"]
}}}}

---
User Form Information:
{form_info_str}

---
Text Extracted from Resume PDF:
{pdf_text}

---
Strict JSON Output:
'''

    def _extract_score_from_marksheet_text(self, marksheet_text, education_level):
        prompt = f"""You are an AI assistant. Find the final score (percentage, CGPA, grade) from the text for a {education_level} level. Prioritize percentage. Return only the score value (e.g., "85%", "9.2 CGPA", "A Grade"). If none, return an empty string. Marksheet Text: {marksheet_text}. Extracted Score:"""
        try:
            response = self.client.chat.completions.create(model=_A, messages=[{'role': 'user', _B: prompt}], max_tokens=50, temperature=.1)
            score = response.choices[0].message.content.strip()
            return score if re.match('^[0-9.]+\\s*(%|CGPA|GPA|Grade)?$', score, re.IGNORECASE) else ''
        except Exception as e:
            print(f"Error calling LLM for {education_level} score: {e}")
            return ''

    def _call_llama_model(self, prompt):
        response = self.client.chat.completions.create(model=_A, messages=[{'role': 'user', _B: prompt}], max_tokens=4096)
        return response.choices[0].message.content

    def process_resume_data(self, data_for_llm_prompt, resume_pdf_file, education_files):
        structured_resume = {}
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_uploads')
        os.makedirs(temp_dir, exist_ok=True)

        if resume_pdf_file:
            pdf_path = os.path.join(temp_dir, resume_pdf_file.name)
            with open(pdf_path, 'wb+') as temp_file:
                for chunk in resume_pdf_file.chunks(): temp_file.write(chunk)
            self.temp_pdf_paths.append(pdf_path)

            pdf_text = self._extract_text_from_pdf(pdf_path) # <<< THIS CALL NOW WORKS
            prompt = self._build_prompt(data_for_llm_prompt, pdf_text)
            llm_response = self._call_llama_model(prompt)
            structured_resume = json.loads(llm_response)
        else:
            structured_resume = self._populate_structured_resume_from_form(data_for_llm_prompt)

        # This logic to extract scores from marksheets remains a good feature
        for level, upload_file in education_files.items():
            if upload_file:
                # ... score extraction logic ...
                pass # The existing logic is fine here.

        return structured_resume

    def get_temp_pdf_paths(self):
        return self.temp_pdf_paths

    def _populate_structured_resume_from_form(self, data):
        # Fallback to structure form data if no PDF is provided
        return {
            B: data.get(B, {}), I: data.get(I, {}), s: data.get(s, ""),
            h: data.get(h, []), i: data.get(i, []), j: data.get(j, []), k: data.get(k, []), l: data.get(l, []),
            m: data.get(m, []), n: data.get(n, []), o: data.get(o, []), q: data.get(q, []),
            'frameworks_tools': data.get('frameworks_tools', []), 'diploma_details': data.get('diploma_details', []),
            'degree_details': data.get('degree_details', []), 'certification_details': data.get('certification_details', []),
            'certification_photos': data.get('certification_photos', []), 'work_preferences': data.get('work_preferences', []),
            'work_authorizations': data.get('work_authorizations', []), 'professional_links': data.get('professional_links', []),
            p: data.get(p, {}), d: data.get(d, ""), f: data.get(f, ""),
            E: data.get(E, {}), v: data.get(v, {}), A: data.get(A, {})
        }


class ResumeBuilderAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ai_pipeline = ResumeAIPipeline()

    def _safe_json_loads(self, json_string, default_value=None):
        if not json_string: return default_value
        try: return json.loads(json_string)
        except (json.JSONDecodeError, TypeError): return default_value

    def _serialize_resume_to_json(self, resume_instance):
        request = self.request
        get_url = lambda f: request.build_absolute_uri(f.url) if f and hasattr(f, 'url') else None

        return {
            'id': resume_instance.pk,
            'talent_id': resume_instance.talent_id.pk,
            'name': resume_instance.name, 'email': resume_instance.email, 'phone': resume_instance.phone,
            'current_location': resume_instance.current_location, 'aadhar_number': resume_instance.aadhar_number, 'passport_number': resume_instance.passport_number, 'current_company': resume_instance.current_company,
            'profile_photo_url': get_url(resume_instance.profile_photo),
            'resume_pdf_url': get_url(resume_instance.resume_pdf),
            'linkedin_url': resume_instance.linkedin_url, 'github_url': resume_instance.github_url, 'portfolio_url': resume_instance.portfolio_url, 'stackoverflow_url': resume_instance.stackoverflow_url, 'medium_or_blog_url': resume_instance.medium_or_blog_url,
            'summary': resume_instance.summary, 'generated_summary': resume_instance.generated_summary,
            'preferred_tech_stack': resume_instance.preferred_tech_stack, 'dev_environment': resume_instance.dev_environment,
            'volunteering_experience': resume_instance.volunteering_experience, 'extracurriculars': resume_instance.extracurriculars,
            'work_arrangement': resume_instance.work_arrangement, 'preferred_location': resume_instance.preferred_location,
            'work_authorization': resume_instance.work_authorization, 'criminal_record_disclosure': resume_instance.criminal_record_disclosure,
            'document_verification': resume_instance.document_verification,
            'current_area': resume_instance.current_area, 'permanent_area': resume_instance.permanent_area, 'current_city': resume_instance.current_city, 'permanent_city': resume_instance.permanent_city, 'current_district': resume_instance.current_district, 'permanent_district': resume_instance.permanent_district, 'current_state': resume_instance.current_state, 'permanent_state': resume_instance.permanent_state, 'current_country': resume_instance.current_country, 'permanent_country': resume_instance.permanent_country,

            # --- Correctly handle JSONField vs TextField ---
            # JSONField (accessed directly)
            'languages': resume_instance.languages, 'frameworks_tools': resume_instance.frameworks_tools, 'diploma_details': resume_instance.diploma_details, 'degree_details': resume_instance.degree_details, 'certification_details': resume_instance.certification_details, 'certification_photos': resume_instance.certification_photos, 'work_preferences': resume_instance.work_preferences, 'work_authorizations': resume_instance.work_authorizations, 'professional_links': resume_instance.professional_links,

            # TextField storing JSON (must be loaded)
            'skills': self._safe_json_loads(resume_instance.skills, []),
            'experience': self._safe_json_loads(resume_instance.experience, []),
            'projects': self._safe_json_loads(resume_instance.projects, []),
            'certifications': self._safe_json_loads(resume_instance.certifications, []),
            'awards': self._safe_json_loads(resume_instance.awards, []),
            'publications': self._safe_json_loads(resume_instance.publications, []),
            'open_source_contributions': self._safe_json_loads(resume_instance.open_source_contributions, []),
            'interests': self._safe_json_loads(resume_instance.interests, []),
            'references': self._safe_json_loads(resume_instance.references, []),
            'preferences': self._safe_json_loads(resume_instance.preferences, {}),

            'education_details': {
                'tenth': {'board_name': resume_instance.tenth_board_name, 'school_name': resume_instance.tenth_school_name, 'year_passing': resume_instance.tenth_year_passing, 'score': resume_instance.tenth_score, 'result_upload_url': get_url(resume_instance.tenth_result_upload)},
                'twelfth': {'board_name': resume_instance.twelfth_board_name, 'college_name': resume_instance.twelfth_college_name, 'year_passing': resume_instance.twelfth_year_passing, 'score': resume_instance.twelfth_score, 'result_upload_url': get_url(resume_instance.twelfth_result_upload)},
                'diploma': {'course_name': resume_instance.diploma_course_name, 'institution_name': resume_instance.diploma_institution_name, 'year_passing': resume_instance.diploma_year_passing, 'score': resume_instance.diploma_score, 'result_upload_url': get_url(resume_instance.diploma_result_upload)},
                'degree': {'degree_name': resume_instance.degree_name, 'institution_name': resume_instance.degree_institution_name, 'specialization': resume_instance.degree_specialization, 'year_passing': resume_instance.degree_year_passing, 'score': resume_instance.degree_score, 'result_upload_url': get_url(resume_instance.degree_result_upload)}
            },
            'created_at': resume_instance.created_at.isoformat(),
            'updated_at': resume_instance.updated_at.isoformat(),
        }

    def _process_and_update_resume(self, request, user):
        """Single method to handle the logic for POST, PUT, PATCH."""
        # Step 1: Get or Create the Resume instance
        resume, created = Resume.objects.get_or_create(talent_id=user, defaults={'is_deleted': False})
        if resume.is_deleted:
            resume.is_deleted = False

        # Step 2: Process incoming form data
        data_for_llm, files = {}, {}
        all_fields = list(request.data.keys()) + list(request.FILES.keys())

        for field in all_fields:
            if field in request.FILES:
                files[field] = request.FILES.get(field)
            elif field in request.data:
                value = request.data.get(field)
                try: # Attempt to parse as JSON if it's a string
                    data_for_llm[field] = json.loads(value) if isinstance(value, str) else value
                except json.JSONDecodeError: # If not valid JSON, treat as string
                    data_for_llm[field] = value

        # Step 3: Run AI Pipeline
        existing_data = self._serialize_resume_to_json(resume)
        merged_data = {**existing_data, **data_for_llm} # Prioritize new data
        structured_data = self.ai_pipeline.process_resume_data(merged_data, files.get('resume_pdf'), files)

        # Step 4: Update the instance with processed data
        # Assign values only if they exist in the processed data
        for field, value in structured_data.items():
            if hasattr(resume, field):
                # For TextFields that store JSON, dump it back to a string
                if field in ['skills', 'experience', 'projects', 'certifications', 'awards', 'publications', 'open_source_contributions', 'interests', 'references', 'preferences']:
                    setattr(resume, field, json.dumps(value))
                else: # For JSONFields and other standard fields, assign directly
                    setattr(resume, field, value)

        # Handle nested structures
        if B in structured_data:
            for key, val in structured_data[B].items(): setattr(resume, key, val)
        if I in structured_data:
            for key, val in structured_data[I].items(): setattr(resume, key, val)
        if A in structured_data:
            for edu_level, details in structured_data[A].items():
                prefix = f"{edu_level}_"
                if edu_level == "twelfth": prefix += "college_"
                elif edu_level == "tenth": prefix += "school_"
                for key, val in details.items():
                    model_field_name = f"{prefix}{key}"
                    if hasattr(resume, model_field_name): setattr(resume, model_field_name, val)

        # Update files
        for field, file_obj in files.items():
            setattr(resume, field, file_obj)

        # Step 5: Save
        resume.save()
        return resume, created

    def get(self, request, *args, **kwargs):
        try:
            resume = Resume.objects.get(talent_id=request.user, is_deleted=False)
            return JsonResponse(self._serialize_resume_to_json(resume), status=status.HTTP_200_OK)
        except Resume.DoesNotExist:
            return JsonResponse({'message': 'Resume not found for this user.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return JsonResponse({J: f"An error occurred: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request, *args, **kwargs):
        try:
            resume, created = self._process_and_update_resume(request, request.user)
            message = "Resume created and saved successfully!" if created else "Resume progress saved successfully!"
            return JsonResponse({'message': message, 'resume_id': resume.pk}, status=status.HTTP_200_OK)
        except Exception as e:
            if '402 Client Error' in str(e):
                return JsonResponse({J: 'Hugging Face credits may have been exceeded.'}, status=status.HTTP_402_PAYMENT_REQUIRED)
            return JsonResponse({J: f"An internal server error occurred: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            for path in self.ai_pipeline.get_temp_pdf_paths():
                if os.path.exists(path): os.remove(path)

    def put(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        try:
            resume = Resume.objects.get(talent_id=request.user, is_deleted=False)
            resume.is_deleted = True
            resume.save()
            return JsonResponse({'message': 'Resume soft-deleted successfully!'}, status=status.HTTP_200_OK)
        except Resume.DoesNotExist:
            return JsonResponse({'message': 'Resume not found.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return JsonResponse({J: f"An error occurred during delete: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# --------------------------------------------------------------------------
# --- AI ANALYSIS MODULES VIEWS ---
# --------------------------------------------------------------------------

class ResumeReviewAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, *args, **kwargs):
        user = request.user
        target_role = request.query_params.get('target_role', 'AI Engineer')
        try:
            resume = Resume.objects.get(talent_id=user, is_deleted=False)
            if not resume.resume_pdf or not resume.resume_pdf.path:
                return JsonResponse({'error': 'No resume PDF found. Please upload a resume first.'}, status=status.HTTP_404_NOT_FOUND)

            if not os.path.exists(resume.resume_pdf.path):
                return JsonResponse({'error': 'Resume file is missing from storage. Please re-upload.'}, status=status.HTTP_404_NOT_FOUND)

            resume_text = extract_text_from_pdf_path(resume.resume_pdf.path)
            review_result = generate_resume_review(resume_text, target_role)
            return JsonResponse(review_result, status=status.HTTP_200_OK)
        except Resume.DoesNotExist:
            return JsonResponse({'error': 'Resume profile not found for this user.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return JsonResponse({'error': f'An internal server error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class SkillGapAnalysisAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def _safe_json_loads(self, json_string, default_value=None):
        """Helper method to safely load JSON strings."""
        if not json_string: return default_value
        try: return json.loads(json_string)
        except (json.JSONDecodeError, TypeError): return default_value

    def get(self, request, *args, **kwargs):
        user = request.user
        try:
            resume = Resume.objects.get(talent_id=user, is_deleted=False)
            resume_skills = self._safe_json_loads(resume.skills, [])
            if not resume_skills:
                return JsonResponse({'error': 'No skills found in your resume. Please add skills first.'}, status=status.HTTP_400_BAD_REQUEST)

            # TODO: Replace this with a dynamic query to your JobPosting model
            job_roles_on_portal = [
                "AI Engineer, NLP focus, PyTorch", "Senior Machine Learning Engineer (MLOps)",
                "Data Scientist with Deep Learning experience", "Research Engineer in Computer Vision"
            ]

            skill_gap_result = generate_skill_gap_analysis(resume_skills, job_roles_on_portal)
            return JsonResponse(skill_gap_result, status=status.HTTP_200_OK)
        except Resume.DoesNotExist:
            return JsonResponse({'error': 'Resume profile not found for this user.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            # CORRECTED TYPO HERE: 's' changed to 'status'
            return JsonResponse({'error': f'An internal server error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CareerRoadmapAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def _safe_json_loads(self, json_string, default_value=None):
        """Helper method to safely load JSON strings."""
        if not json_string: return default_value
        try: return json.loads(json_string)
        except (json.JSONDecodeError, TypeError): return default_value

    def get(self, request, *args, **kwargs):
        user = request.user
        try:
            resume = Resume.objects.get(talent_id=user, is_deleted=False)
            experience = self._safe_json_loads(resume.experience, [])
            interests = self._safe_json_loads(resume.interests, ["Not specified"])
            skills = self._safe_json_loads(resume.skills, [])

            if not experience:
                return JsonResponse({'error': 'No work experience found. Add it to generate a roadmap.'}, status=status.HTTP_400_BAD_REQUEST)

            current_role = experience[0].get('title', 'Not specified')
            experience_years = len(experience) * 1.5 # Simple placeholder logic

            roadmap_result = generate_career_roadmap(current_role, experience_years, interests, skills)
            return JsonResponse(roadmap_result, status=status.HTTP_200_OK)
        except Resume.DoesNotExist:
            return JsonResponse({'error': 'Resume profile not found for this user.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return JsonResponse({'error': f'An internal server error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


###############vaishnavi's code ##############

from rest_framework import generics
from .models import TrendingSkill
from .serializers import TrendingSkillSerializer

#add in the last
class TrendingSkillsListView(generics.ListAPIView):
    """
    Provides a list of trending skills in the industry, for talent users.
    This data is cached and updated periodically by a background task.
    """
    queryset = TrendingSkill.objects.all()
    serializer_class = TrendingSkillSerializer
    permission_classes = [IsAuthenticated]









# _B = 'content'
# _A = 'meta-llama/Meta-Llama-3-70B-Instruct'
# import os, fitz, json, re
# from django.http import JsonResponse
# from django.conf import settings
# from huggingface_hub import InferenceClient
# from .models import Resume, CustomUser 
# from django.contrib.auth import get_user_model
# from rest_framework.views import APIView
# from rest_framework.permissions import IsAuthenticated
# from rest_framework import status

# # --- AI Analysis Service Imports (for the analysis views at the end) ---
# from .ai_analysis_services import (
#     generate_resume_review,
#     extract_text_from_pdf_path,
#     generate_skill_gap_analysis,
#     generate_career_roadmap
# )


# # Get the CustomUser model
# User = get_user_model()

# HFF_TOKEN = os.getenv('HFF_TOKEN')
# if not HFF_TOKEN:
#     raise ValueError('HuggingFace token not set in environment (HFF_TOKEN). Please set it to proceed.')

# # Constants for clarity
# L = 'name'; M = 'email'; N = 'phone'; O = 'work_arrangement'; P = 'preferred_location'
# Q = 'preferred_tech_stack'; R = 'dev_environment'; S = 'current_location'
# T = 'aadhar_number'; U = 'passport_number'; V = 'current_company'
# W = 'linkedin_url'; X = 'github_url'; Y = 'portfolio_url'
# Z = 'stackoverflow_url'; a = 'medium_or_blog_url'
# b = 'work_authorization'; c = 'criminal_record_disclosure'
# d = 'volunteering_experience'; f = 'extracurriculars'
# g = 'degree_name'; h = 'skills'; i = 'experience'
# j = 'projects'; k = 'certifications'; l = 'awards'
# m = 'publications'; n = 'open_source_contributions'
# o = 'interests'; p = 'languages'; q = 'references'
# s = 'professional_summary'; t = 'board_name'; u = 'institution_name'
# v = 'legal'; K = 'year_passing'; D = 'score'
# J = 'error'; I = 'links'; H = 'diploma'
# G = 'twelfth'; F = 'tenth'; E = 'preferences'
# C = 'degree'; A = 'education_details'; B = 'personal_info'


# class ResumeAIPipeline:
#     # ... other methods ...

#     # THIS IS THE CORRECTED FUNCTION
#     def _build_prompt(self, form_data, pdf_text):
#         form_info_str = json.dumps(form_data, indent=2)
#         # The prompt is intentionally verbose and detailed to guide the LLM effectively.
#         # NOTE THE FIX: Every literal { and } is now doubled as {{ and }}
#         return f'''
# You are an AI Resume Builder. Your goal is to extract and structure comprehensive resume information. Combine the user's explicit form input with details from their old resume PDF. Prioritize form input for accuracy. If info is only in the PDF, extract it.

# Return your output in **strict JSON format only**. Do NOT include any markdown (e.g., ```json), conversational text, or explanations. The JSON structure must follow this schema:
# {{{{
#     "personal_info": {{{{ "name": "...", "email": "...", "phone": "...", "current_location": "...", "current_area": "...", "permanent_area": "...", "current_city": "...", "permanent_city": "...", "current_district": "...", "permanent_district": "...", "current_state": "...", "permanent_state": "...", "current_country": "...", "permanent_country": "...", "aadhar_number": "...", "passport_number": "...", "current_company": "..." }}}},
#     "links": {{{{ "linkedin_url": "...", "github_url": "...", "portfolio_url": "...", "stackoverflow_url": "...", "medium_or_blog_url": "..." }}}},
#     "professional_summary": "A concise 3-4 sentence summary.",
#     "skills": ["Skill 1", "Skill 2"],
#     "experience": [{{{{ "title": "...", "company": "...", "duration": "...", "responsibilities": ["..."] }}}}],
#     "projects": [{{{{ "name": "...", "description": "...", "url": "..." }}}}],
#     "education_details": {{{{
#         "degree": {{{{ "degree_name": "...", "institution_name": "...", "specialization": "...", "year_passing": "...", "score": "..." }}}},
#         "diploma": {{{{ "course_name": "...", "institution_name": "...", "year_passing": "...", "score": "..." }}}},
#         "twelfth": {{{{ "board_name": "...", "college_name": "...", "year_passing": "...", "score": "..." }}}},
#         "tenth": {{{{ "board_name": "...", "school_name": "...", "year_passing": "...", "score": "..." }}}}
#     }}}},
#     "frameworks_tools": [{{{{ "name": "Tool/Framework", "rating": 5 }}}}],
#     "diploma_details": [{{{{ "course_name": "...", "institution_name": "...", "year_passing": "...", "score": "..." }}}}],
#     "degree_details": [{{{{ "degree_name": "...", "institution_name": "...", "specialization": "...", "year_passing": "...", "score": "..." }}}}],
#     "certification_details": [{{{{ "name": "...", "issuer": "...", "date": "..." }}}}],
#     "certification_photos": ["url1", "url2"],
#     "work_preferences": ["Remote", "Flexible Hours"],
#     "work_authorizations": ["Indian Citizen", "US B1/B2 Visa"],
#     "professional_links": ["https://linkedin.com/in/yourprofile"],
#     "certifications": ["Certification 1", "Certification 2"],
#     "awards": ["Award 1"],
#     "publications": ["Publication 1"],
#     "open_source_contributions": ["Contribution 1"],
#     "volunteering_experience": "Description...",
#     "extracurriculars": "Description...",
#     "languages": {{{{ "Language 1": "Proficiency" }}}},
#     "preferences": {{{{ "work_arrangement": "...", "preferred_location": "...", "other_preferences": "..." }}}},
#     "legal": {{{{ "work_authorization": "...", "criminal_record_disclosure": "..." }}}},
#     "document_verification": "Status...",
#     "interests": ["Interest 1"]
# }}}}

# ---
# User Form Information:
# {form_info_str}

# ---
# Text Extracted from Resume PDF:
# {pdf_text}

# ---
# Strict JSON Output:
# '''

#     def _extract_score_from_marksheet_text(self, marksheet_text, education_level):
#         prompt = f"""You are an AI assistant. Find the final score (percentage, CGPA, grade) from the text for a {education_level} level. Prioritize percentage. Return only the score value (e.g., "85%", "9.2 CGPA", "A Grade"). If none, return an empty string. Marksheet Text: {marksheet_text}. Extracted Score:"""
#         try:
#             response = self.client.chat.completions.create(model=_A, messages=[{'role': 'user', _B: prompt}], max_tokens=50, temperature=.1)
#             score = response.choices[0].message.content.strip()
#             return score if re.match('^[0-9.]+\\s*(%|CGPA|GPA|Grade)?$', score, re.IGNORECASE) else ''
#         except Exception as e:
#             print(f"Error calling LLM for {education_level} score: {e}")
#             return ''

#     def _call_llama_model(self, prompt):
#         response = self.client.chat.completions.create(model=_A, messages=[{'role': 'user', _B: prompt}], max_tokens=4096)
#         return response.choices[0].message.content

#     def process_resume_data(self, data_for_llm_prompt, resume_pdf_file, education_files):
#         self.temp_pdf_paths = [] 
#         structured_resume = {}
#         temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_uploads')
#         os.makedirs(temp_dir, exist_ok=True)

#         if resume_pdf_file:
#             pdf_path = os.path.join(temp_dir, resume_pdf_file.name)
#             with open(pdf_path, 'wb+') as temp_file:
#                 for chunk in resume_pdf_file.chunks(): temp_file.write(chunk)
#             self.temp_pdf_paths.append(pdf_path)
            
#             pdf_text = self._extract_text_from_pdf(pdf_path)
#             prompt = self._build_prompt(data_for_llm_prompt, pdf_text)
#             llm_response = self._call_llama_model(prompt)
#             structured_resume = json.loads(llm_response)
#         else:
#             structured_resume = self._populate_structured_resume_from_form(data_for_llm_prompt)
        
#         # This logic to extract scores from marksheets remains a good feature
#         for level, upload_file in education_files.items():
#             if upload_file:
#                 # ... score extraction logic ...
#                 pass # The existing logic is fine here.
        
#         return structured_resume

#     def get_temp_pdf_paths(self):
#         return self.temp_pdf_paths

#     def _populate_structured_resume_from_form(self, data):
#         # Fallback to structure form data if no PDF is provided
#         return {
#             B: data.get(B, {}), I: data.get(I, {}), s: data.get(s, ""),
#             h: data.get(h, []), i: data.get(i, []), j: data.get(j, []), k: data.get(k, []), l: data.get(l, []),
#             m: data.get(m, []), n: data.get(n, []), o: data.get(o, []), q: data.get(q, []),
#             'frameworks_tools': data.get('frameworks_tools', []), 'diploma_details': data.get('diploma_details', []),
#             'degree_details': data.get('degree_details', []), 'certification_details': data.get('certification_details', []),
#             'certification_photos': data.get('certification_photos', []), 'work_preferences': data.get('work_preferences', []),
#             'work_authorizations': data.get('work_authorizations', []), 'professional_links': data.get('professional_links', []),
#             p: data.get(p, {}), d: data.get(d, ""), f: data.get(f, ""),
#             E: data.get(E, {}), v: data.get(v, {}), A: data.get(A, {})
#         }


# class ResumeBuilderAPIView(APIView):
#     permission_classes = [IsAuthenticated]
    
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.ai_pipeline = ResumeAIPipeline()

#     def _safe_json_loads(self, json_string, default_value=None):
#         if not json_string: return default_value
#         try: return json.loads(json_string)
#         except (json.JSONDecodeError, TypeError): return default_value

#     def _serialize_resume_to_json(self, resume_instance):
#         request = self.request
#         get_url = lambda f: request.build_absolute_uri(f.url) if f and hasattr(f, 'url') else None

#         return {
#             'id': resume_instance.pk,
#             'talent_id': resume_instance.talent_id.pk,
#             'name': resume_instance.name, 'email': resume_instance.email, 'phone': resume_instance.phone,
#             'current_location': resume_instance.current_location, 'aadhar_number': resume_instance.aadhar_number, 'passport_number': resume_instance.passport_number, 'current_company': resume_instance.current_company,
#             'profile_photo_url': get_url(resume_instance.profile_photo),
#             'resume_pdf_url': get_url(resume_instance.resume_pdf),
#             'linkedin_url': resume_instance.linkedin_url, 'github_url': resume_instance.github_url, 'portfolio_url': resume_instance.portfolio_url, 'stackoverflow_url': resume_instance.stackoverflow_url, 'medium_or_blog_url': resume_instance.medium_or_blog_url,
#             'summary': resume_instance.summary, 'generated_summary': resume_instance.generated_summary,
#             'preferred_tech_stack': resume_instance.preferred_tech_stack, 'dev_environment': resume_instance.dev_environment,
#             'volunteering_experience': resume_instance.volunteering_experience, 'extracurriculars': resume_instance.extracurriculars,
#             'work_arrangement': resume_instance.work_arrangement, 'preferred_location': resume_instance.preferred_location,
#             'work_authorization': resume_instance.work_authorization, 'criminal_record_disclosure': resume_instance.criminal_record_disclosure,
#             'document_verification': resume_instance.document_verification,
#             'current_area': resume_instance.current_area, 'permanent_area': resume_instance.permanent_area, 'current_city': resume_instance.current_city, 'permanent_city': resume_instance.permanent_city, 'current_district': resume_instance.current_district, 'permanent_district': resume_instance.permanent_district, 'current_state': resume_instance.current_state, 'permanent_state': resume_instance.permanent_state, 'current_country': resume_instance.current_country, 'permanent_country': resume_instance.permanent_country,
            
#             # --- Correctly handle JSONField vs TextField ---
#             # JSONField (accessed directly)
#             'languages': resume_instance.languages, 'frameworks_tools': resume_instance.frameworks_tools, 'diploma_details': resume_instance.diploma_details, 'degree_details': resume_instance.degree_details, 'certification_details': resume_instance.certification_details, 'certification_photos': resume_instance.certification_photos, 'work_preferences': resume_instance.work_preferences, 'work_authorizations': resume_instance.work_authorizations, 'professional_links': resume_instance.professional_links,
            
#             # TextField storing JSON (must be loaded)
#             'skills': self._safe_json_loads(resume_instance.skills, []),
#             'experience': self._safe_json_loads(resume_instance.experience, []),
#             'projects': self._safe_json_loads(resume_instance.projects, []),
#             'certifications': self._safe_json_loads(resume_instance.certifications, []),
#             'awards': self._safe_json_loads(resume_instance.awards, []),
#             'publications': self._safe_json_loads(resume_instance.publications, []),
#             'open_source_contributions': self._safe_json_loads(resume_instance.open_source_contributions, []),
#             'interests': self._safe_json_loads(resume_instance.interests, []),
#             'references': self._safe_json_loads(resume_instance.references, []),
#             'preferences': self._safe_json_loads(resume_instance.preferences, {}),
            
#             'education_details': {
#                 'tenth': {'board_name': resume_instance.tenth_board_name, 'school_name': resume_instance.tenth_school_name, 'year_passing': resume_instance.tenth_year_passing, 'score': resume_instance.tenth_score, 'result_upload_url': get_url(resume_instance.tenth_result_upload)},
#                 'twelfth': {'board_name': resume_instance.twelfth_board_name, 'college_name': resume_instance.twelfth_college_name, 'year_passing': resume_instance.twelfth_year_passing, 'score': resume_instance.twelfth_score, 'result_upload_url': get_url(resume_instance.twelfth_result_upload)},
#                 'diploma': {'course_name': resume_instance.diploma_course_name, 'institution_name': resume_instance.diploma_institution_name, 'year_passing': resume_instance.diploma_year_passing, 'score': resume_instance.diploma_score, 'result_upload_url': get_url(resume_instance.diploma_result_upload)},
#                 'degree': {'degree_name': resume_instance.degree_name, 'institution_name': resume_instance.degree_institution_name, 'specialization': resume_instance.degree_specialization, 'year_passing': resume_instance.degree_year_passing, 'score': resume_instance.degree_score, 'result_upload_url': get_url(resume_instance.degree_result_upload)}
#             },
#             'created_at': resume_instance.created_at.isoformat(),
#             'updated_at': resume_instance.updated_at.isoformat(),
#         }

#     def _process_and_update_resume(self, request, user):
#         """Single method to handle the logic for POST, PUT, PATCH."""
#         # Step 1: Get or Create the Resume instance
#         resume, created = Resume.objects.get_or_create(talent_id=user, defaults={'is_deleted': False})
#         if resume.is_deleted:
#             resume.is_deleted = False

#         # Step 2: Process incoming form data
#         data_for_llm, files = {}, {}
#         all_fields = list(request.data.keys()) + list(request.FILES.keys())

#         for field in all_fields:
#             if field in request.FILES:
#                 files[field] = request.FILES.get(field)
#             elif field in request.data:
#                 value = request.data.get(field)
#                 try: # Attempt to parse as JSON if it's a string
#                     data_for_llm[field] = json.loads(value) if isinstance(value, str) else value
#                 except json.JSONDecodeError: # If not valid JSON, treat as string
#                     data_for_llm[field] = value

#         # Step 3: Run AI Pipeline
#         existing_data = self._serialize_resume_to_json(resume)
#         merged_data = {**existing_data, **data_for_llm} # Prioritize new data
#         structured_data = self.ai_pipeline.process_resume_data(merged_data, files.get('resume_pdf'), files)

#         # Step 4: Update the instance with processed data
#         # Assign values only if they exist in the processed data
#         for field, value in structured_data.items():
#             if hasattr(resume, field):
#                 # For TextFields that store JSON, dump it back to a string
#                 if field in ['skills', 'experience', 'projects', 'certifications', 'awards', 'publications', 'open_source_contributions', 'interests', 'references', 'preferences']:
#                     setattr(resume, field, json.dumps(value))
#                 else: # For JSONFields and other standard fields, assign directly
#                     setattr(resume, field, value)
        
#         # Handle nested structures
#         if B in structured_data:
#             for key, val in structured_data[B].items(): setattr(resume, key, val)
#         if I in structured_data:
#             for key, val in structured_data[I].items(): setattr(resume, key, val)
#         if A in structured_data:
#             for edu_level, details in structured_data[A].items():
#                 prefix = f"{edu_level}_"
#                 if edu_level == "twelfth": prefix += "college_"
#                 elif edu_level == "tenth": prefix += "school_"
#                 for key, val in details.items():
#                     model_field_name = f"{prefix}{key}"
#                     if hasattr(resume, model_field_name): setattr(resume, model_field_name, val)

#         # Update files
#         for field, file_obj in files.items():
#             setattr(resume, field, file_obj)

#         # Step 5: Save
#         resume.save()
#         return resume, created

#     def get(self, request, *args, **kwargs):
#         try:
#             resume = Resume.objects.get(talent_id=request.user, is_deleted=False)
#             return JsonResponse(self._serialize_resume_to_json(resume), status=status.HTTP_200_OK)
#         except Resume.DoesNotExist:
#             return JsonResponse({'message': 'Resume not found for this user.'}, status=status.HTTP_404_NOT_FOUND)
#         except Exception as e:
#             return JsonResponse({J: f"An error occurred: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#     def post(self, request, *args, **kwargs):
#         try:
#             resume, created = self._process_and_update_resume(request, request.user)
#             message = "Resume created and saved successfully!" if created else "Resume progress saved successfully!"
#             return JsonResponse({'message': message, 'resume_id': resume.pk}, status=status.HTTP_200_OK)
#         except Exception as e:
#             if '402 Client Error' in str(e):
#                 return JsonResponse({J: 'Hugging Face credits may have been exceeded.'}, status=status.HTTP_402_PAYMENT_REQUIRED)
#             return JsonResponse({J: f"An internal server error occurred: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
#         finally:
#             for path in self.ai_pipeline.get_temp_pdf_paths():
#                 if os.path.exists(path): os.remove(path)

#     def put(self, request, *args, **kwargs):
#         return self.post(request, *args, **kwargs)

#     def patch(self, request, *args, **kwargs):
#         return self.post(request, *args, **kwargs)

#     def delete(self, request, *args, **kwargs):
#         try:
#             resume = Resume.objects.get(talent_id=request.user, is_deleted=False)
#             resume.is_deleted = True
#             resume.save()
#             return JsonResponse({'message': 'Resume soft-deleted successfully!'}, status=status.HTTP_200_OK)
#         except Resume.DoesNotExist:
#             return JsonResponse({'message': 'Resume not found.'}, status=status.HTTP_404_NOT_FOUND)
#         except Exception as e:
#             return JsonResponse({J: f"An error occurred during delete: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# # --------------------------------------------------------------------------
# # --- AI ANALYSIS MODULES VIEWS ---
# # --------------------------------------------------------------------------

# class ResumeReviewAPIView(APIView):
#     permission_classes = [IsAuthenticated]
#     def get(self, request, *args, **kwargs):
#         user = request.user
#         target_role = request.query_params.get('target_role', 'AI Engineer')
#         try:
#             resume = Resume.objects.get(talent_id=user, is_deleted=False)
#             if not resume.resume_pdf or not resume.resume_pdf.path:
#                 return JsonResponse({'error': 'No resume PDF found. Please upload a resume first.'}, status=status.HTTP_404_NOT_FOUND)

#             if not os.path.exists(resume.resume_pdf.path):
#                  return JsonResponse({'error': 'Resume file is missing from storage. Please re-upload.'}, status=status.HTTP_404_NOT_FOUND)

#             resume_text = extract_text_from_pdf_path(resume.resume_pdf.path)
#             review_result = generate_resume_review(resume_text, target_role)
#             return JsonResponse(review_result, status=status.HTTP_200_OK)
#         except Resume.DoesNotExist:
#             return JsonResponse({'error': 'Resume profile not found for this user.'}, status=status.HTTP_404_NOT_FOUND)
#         except Exception as e:
#             return JsonResponse({'error': f'An internal server error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# class SkillGapAnalysisAPIView(APIView):
#     permission_classes = [IsAuthenticated]
#     def get(self, request, *args, **kwargs):
#         user = request.user
#         try:
#             resume = Resume.objects.get(talent_id=user, is_deleted=False)
#             resume_skills = self._safe_json_loads(resume.skills, [])
#             if not resume_skills:
#                 return JsonResponse({'error': 'No skills found in your resume. Please add skills first.'}, status=status.HTTP_400_BAD_REQUEST)
            
#             # TODO: Replace this with a dynamic query to your JobPosting model
#             job_roles_on_portal = [
#                 "AI Engineer, NLP focus, PyTorch", "Senior Machine Learning Engineer (MLOps)", 
#                 "Data Scientist with Deep Learning experience", "Research Engineer in Computer Vision"
#             ]
            
#             skill_gap_result = generate_skill_gap_analysis(resume_skills, job_roles_on_portal)
#             return JsonResponse(skill_gap_result, status=status.HTTP_200_OK)
#         except Resume.DoesNotExist:
#             return JsonResponse({'error': 'Resume profile not found for this user.'}, status=status.HTTP_404_NOT_FOUND)
#         except Exception as e:
#             return JsonResponse({'error': f'An internal server error occurred: {e}'}, status=s.HTTP_500_INTERNAL_SERVER_ERROR)

# class CareerRoadmapAPIView(APIView):
#     permission_classes = [IsAuthenticated]
#     def get(self, request, *args, **kwargs):
#         user = request.user
#         try:
#             resume = Resume.objects.get(talent_id=user, is_deleted=False)
#             experience = self._safe_json_loads(resume.experience, [])
#             interests = self._safe_json_loads(resume.interests, ["Not specified"])
#             skills = self._safe_json_loads(resume.skills, [])

#             if not experience:
#                 return JsonResponse({'error': 'No work experience found. Add it to generate a roadmap.'}, status=status.HTTP_400_BAD_REQUEST)

#             current_role = experience[0].get('title', 'Not specified')
#             experience_years = len(experience) * 1.5 # Simple placeholder logic

#             roadmap_result = generate_career_roadmap(current_role, experience_years, interests, skills)
#             return JsonResponse(roadmap_result, status=status.HTTP_200_OK)
#         except Resume.DoesNotExist:
#             return JsonResponse({'error': 'Resume profile not found for this user.'}, status=status.HTTP_404_NOT_FOUND)
#         except Exception as e:
#             return JsonResponse({'error': f'An internal server error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

# ###############viashnavi's code ##############


# from rest_framework import generics # <-- ADD THIS IMPORT
# from .models import TrendingSkill # <-- ADD THIS IMPORT
# from .serializers import TrendingSkillSerializer # <-- ADD THIS IMPORT



# #add in the last
# class TrendingSkillsListView(generics.ListAPIView):
#     """
#     Provides a list of trending skills in the industry, for talent users.
#     This data is cached and updated periodically by a background task.
#     """
#     queryset = TrendingSkill.objects.all()
#     serializer_class = TrendingSkillSerializer
#     permission_classes = [IsAuthenticated]




# # Import the AI Interviewer bot logic from the new sub-package
# from .interview_bot.interviewer_logic import AIInterviewer
# # If you need config directly (though interviewer_logic imports it), then:
# from .interview_bot import config 


# from .models import MockInterviewResult
# from .serializers import MockInterviewResultSerializer
# from django.utils import timezone
# import time

from .interview_bot.llm_utils import call_llm_api
from .interview_bot.speech_utils import speak_text 
from .interview_bot.config import MOCK_INTERVIEW_POSITION
from .interview_bot import config # Import config from the same package
from .interview_bot.timer_utils import RoundTimer
from .interview_bot.interviewer_logic import AIInterviewer
# If you need config directly (though interviewer_logic imports it), then:
from .interview_bot import config 
from .models import Resume, CustomUser, MockInterviewResult
from django.utils import timezone
from .serializers import MockInterviewResultSerializer
MALPRACTICE_STATUS_FILE = "malpractice_status.txt"
IDENTITY_VERIFIED_FILE = "identity_verified.txt"

def cleanup_proctor_files_api_context():
    """Removes temporary status files used by the proctoring system."""
    files_to_remove = [MALPRACTICE_STATUS_FILE, IDENTITY_VERIFIED_FILE]
    for f in files_to_remove:
        if os.path.exists(f):
            try:
                os.remove(f)
                print(f"Cleaned up {f} in API context.")
            except OSError as e:
                print(f"Error cleaning up {f} in API context: {e}")

def read_malpractice_status_api_context():
    """Reads the current malpractice status from the file for API context."""
    try:
        if os.path.exists(MALPRACTICE_STATUS_FILE):
            with open(MALPRACTICE_STATUS_FILE, "r") as f:
                return f.read().strip()
        return "NOT_STARTED" # Default if file doesn't exist yet
    except IOError as e:
        print(f"Error reading malpractice status file in API context: {e}")
        return "ERROR_READING_STATUS"

# Hardcoded position for mock interviews


# talent_management/views.py

# ... (existing imports at the top) ...

# --- MockInterviewStartView.post method ---
# --- MockInterviewStartView.post method ---
class MockInterviewStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        
        # Clean up any residual files from previous runs
        cleanup_proctor_files_api_context()

        # Fetch candidate's experience and AIML specialization from their Resume
        try:
            resume = Resume.objects.get(talent_id=user)
            
            # --- MODIFIED: Extract candidate experience from 'experience' JSONField ---

# Clean up any residual files from previous runs
            cleanup_proctor_files_api_context()

# Fetch candidate's experience and AIML specialization from their Resume
            candidate_experience = ""
            if resume.experience:
                exp_list = safe_json_loads(resume.experience, [])
                if exp_list:
                    print(exp_list, "experience list")
                    candidate_experience = json.dumps(exp_list, indent=2)
            # --- END MODIFIED SECTION ---
            
            # Extract AIML specialization from skills, or leave as None
            # This logic is crucial for populating the new aiml_specialization JSONField
            aiml_specialization_input_str = None # This will go to the CharField
            detected_aiml_specializations_list = [] # This will go to the JSONField
            resume = Resume.objects.get(talent_id=user)
            position = resume.desired_domain or "General"

            if resume.skills:
                skills_list = safe_json_loads(resume.skills, [])
                print(skills_list,"skill list")
                # Simple heuristic: look for common AIML-related skills
                found_aiml_skills = extract_specialized_skills(position, skills_list)
                print(found_aiml_skills, "test0")
                print(found_aiml_skills, "test1")
                if resume.skills:
                    skills_list = safe_json_loads(resume.skills, [])
                    found_aiml_skills = extract_specialized_skills(position, skills_list)
                    print(found_aiml_skills, "test1")

                if found_aiml_skills:
                    aiml_specialization_input_str = ", ".join(found_aiml_skills)
                    detected_aiml_specializations_list = list(set(found_aiml_skills))
                else:
                    aiml_specialization_input_str = "Could not fetch relevant skills. Make sure your resume includes skills aligned with your job interests."
                    detected_aiml_specializations_list = []


        except Resume.DoesNotExist:
            return Response({"error": "Resume not found for this user. Please create your resume before starting a mock interview."},
                            status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"Error fetching resume data: {e}")
            return Response({"error": f"Failed to retrieve candidate data: {e}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Create a new MockInterviewResult entry
        mock_interview = MockInterviewResult.objects.create(
            user=user,
            position_applied=resume.desired_domain,
            candidate_experience=candidate_experience,
            aiml_specialization_input=aiml_specialization_input_str, # Save to CharField
            aiml_specialization=detected_aiml_specializations_list,     # NEW: Save to JSONField
            status=MockInterviewResult.InterviewStatus.IN_PROGRESS,
            pre_generated_questions_data={}, # Initialize, will be populated by AIInterviewer
            full_qa_transcript=[], # Initialize
            technical_specialization_scores={} # Initialize
        )
        
        try:
            # Initialize the AI Interviewer bot
            interviewer = AIInterviewer(
                position=resume.desired_domain or "General",
                experience=candidate_experience,
                aiml_specialization=detected_aiml_specializations_list, # Pass the string input to AIInterviewer
                mock_interview_result_instance=mock_interview # Pass the instance
            )
            
            # Store ONLY the interview ID in the session
            request.session['current_mock_interview_id'] = mock_interview.id
            # Store the current round and question index in the session
            # This is a simplification; for robustness, these should be in MockInterviewResult
            request.session['current_round_name'] = "communication"
            request.session['current_question_index'] = 0
            request.session.modified = True 

            # Pre-generate questions (this might take a moment)
            # This method will now save the questions directly to mock_interview.pre_generated_questions_data
            interviewer._pre_generate_all_questions()

            # Save the mock_interview instance after pre-generation to persist questions
            mock_interview.save()

            if interviewer.malpractice_detected: # Check if pre-generation failed
                # Malpractice status is already saved by interviewer._check_malpractice_status
                return Response({
                    "message": "Interview terminated during setup.",
                    "reason": interviewer.malpractice_reason,
                    "interview_id": mock_interview.id,
                    "status": mock_interview.status
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Return initial messages and first question of the first round
            welcome_message = interviewer.all_generated_questions["welcome_message"]
            interview_start_message = interviewer.all_generated_questions["interview_start_message_template"].format(position=resume.desired_domain or "General")
            
            # Ensure communication questions exist before accessing
            if not interviewer.all_generated_questions["communication"]["questions"]:
                return Response({
                    "message": "No communication questions generated. Cannot start interview.",
                    "interview_id": mock_interview.id,
                    "status": mock_interview.status
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            first_question_dict = interviewer.all_generated_questions["communication"]["questions"][0]
            first_question_text = first_question_dict["question_text"]
            
            # Update chat history in the bot instance (this will be saved in the DB later if needed)
            interviewer._add_to_chat_history("model", first_question_text)
            # No need to save interviewer to session, only its state via DB

            return Response({
                "message": f"{welcome_message} {interview_start_message}",
                "interview_id": mock_interview.id,
                "current_round": "communication",
                "question_number": 1,
                "question_text": first_question_text,
                "status": mock_interview.status
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Error initializing AI Interviewer: {e}")
            # Ensure mock_interview status is updated even if AIInterviewer init fails
            mock_interview.status = MockInterviewResult.InterviewStatus.TERMINATED_ERROR
            mock_interview.malpractice_detected = True
            mock_interview.malpractice_reason = f"Error during AI bot initialization: {e}"
            mock_interview.interview_end_time = timezone.now()
            mock_interview.save()
            # Clear session data
            request.session.pop('current_mock_interview_id', None)
            request.session.pop('current_round_name', None)
            request.session.pop('current_question_index', None)
            request.session.modified = True
            cleanup_proctor_files_api_context()
            return Response({"error": f"Failed to start interview: {e}", "interview_id": mock_interview.id},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class MockInterviewVerifyIdentityView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        interview_id = request.session.get('current_mock_interview_id')
        current_round_name = request.session.get('current_round_name')
        current_question_index = request.session.get('current_question_index')

        if not interview_id or current_round_name is None or current_question_index is None:
            return Response({"error": "No active interview session found. Please restart interview."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            mock_interview = MockInterviewResult.objects.get(id=interview_id, user=request.user)
            
            # Reconstruct AIInterviewer from DB instance
            interviewer = AIInterviewer.load_from_db_instance(mock_interview)
            if not interviewer:
                return Response({"error": "Failed to reconstruct AI Interviewer instance. Please restart interview."},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Re-set current state (not strictly needed if load_from_db_instance handles it, but safer)
            interviewer.current_round_name = current_round_name
            interviewer.current_question_index = current_question_index
            interviewer.current_round_questions = interviewer.all_generated_questions[current_round_name]["questions"]


            is_verified = request.data.get('is_verified', False)

            mock_interview.identity_verified = is_verified
            if not is_verified:
                mock_interview.status = MockInterviewResult.InterviewStatus.TERMINATED_ERROR
                mock_interview.malpractice_detected = True
                mock_interview.malpractice_reason = "Identity verification failed."
                mock_interview.interview_end_time = timezone.now()
                mock_interview.save()
                # Clear session data
                request.session.pop('current_mock_interview_id', None)
                request.session.pop('current_round_name', None)
                request.session.pop('current_question_index', None)
                request.session.modified = True
                return Response({
                    "message": "Identity verification failed. Interview terminated.",
                    "interview_id": mock_interview.id,
                    "status": mock_interview.status,
                    "reason": mock_interview.malpractice_reason
                }, status=status.HTTP_403_FORBIDDEN)
            
            mock_interview.save()
            request.session.modified = True # Ensure session is saved

            # If verification is successful, send the actual first question
            first_question_text = interviewer.current_round_questions[interviewer.current_question_index]["question_text"]
            
            return Response({
                "message": "Identity verified. We can now proceed with the interview.",
                "interview_id": mock_interview.id,
                "current_round": interviewer.current_round_name,
                "question_number": interviewer.current_question_index + 1,
                "question_text": first_question_text,
                "status": mock_interview.status
            }, status=status.HTTP_200_OK)

        except MockInterviewResult.DoesNotExist:
            return Response({"error": "Mock interview session not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"Error during identity verification: {e}")
            # Ensure mock_interview status is updated even if AIInterviewer reconstruction fails
            if interview_id:
                try:
                    mock_interview = MockInterviewResult.objects.get(id=interview_id)
                    mock_interview.status = MockInterviewResult.InterviewStatus.TERMINATED_ERROR
                    mock_interview.malpractice_detected = True
                    mock_interview.malpractice_reason = f"System error during identity verification: {e}"
                    mock_interview.interview_end_time = timezone.now()
                    mock_interview.save()
                except MockInterviewResult.DoesNotExist:
                    pass
            # Clear session data
            request.session.pop('current_mock_interview_id', None)
            request.session.pop('current_round_name', None)
            request.session.pop('current_question_index', None)
            request.session.modified = True
            return Response({"error": f"An error occurred during identity verification: {e}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# --- MockInterviewSubmitAnswerView.post method ---
class MockInterviewSubmitAnswerView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        interview_id = request.session.get('current_mock_interview_id')
        current_round_name = request.session.get('current_round_name')
        current_question_index = request.session.get('current_question_index')

        if not interview_id or current_round_name is None or current_question_index is None:
            return Response({"error": "No active interview session found. Please start a new interview."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            mock_interview = MockInterviewResult.objects.get(id=interview_id, user=request.user)
            
            # Reconstruct AIInterviewer from DB instance
            interviewer = AIInterviewer.load_from_db_instance(mock_interview)
            if not interviewer:
                return Response({"error": "Failed to reconstruct AI Interviewer instance. Please restart interview."},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Re-set current state for the interviewer instance
            interviewer.current_round_name = current_round_name
            interviewer.current_question_index = current_question_index
            
            # Get the questions for the current round from the pre-generated data
            questions_for_current_round = []
            if current_round_name == "communication" or current_round_name == "psychometric":
                questions_for_current_round = interviewer.all_generated_questions[current_round_name]["questions"]
            elif current_round_name in interviewer.technical_specializations:
                questions_for_current_round = interviewer.all_generated_questions["technical"]["specializations"].get(current_round_name, {}).get("questions", [])
            elif current_round_name in ["predict_output", "fix_error", "write_program"]: # Coding stages
                questions_for_current_round = interviewer.all_generated_questions["coding"][current_round_name]["questions"]
            
            interviewer.current_round_questions = questions_for_current_round # Ensure the interviewer has the correct list

            if mock_interview.status != MockInterviewResult.InterviewStatus.IN_PROGRESS:
                return Response({
                    "message": f"Interview is not in progress. Current status: {mock_interview.status}",
                    "interview_id": mock_interview.id,
                    "status": mock_interview.status
                }, status=status.HTTP_400_BAD_REQUEST)

            # --- DEBUGGING ADDITION (Keep for now to confirm input) ---
            print(f"DEBUG VIEWS: Received request data: {request.data}")
            candidate_answer = request.data.get('answer_text', '').strip()
            print(f"DEBUG VIEWS: Extracted candidate_answer: '{candidate_answer}'")
            # --- DEBUGGING ADDITION END ---
            
            malpractice_status_from_file = read_malpractice_status_api_context()
            if malpractice_status_from_file.startswith("TERMINATED") and malpractice_status_from_file != "TERMINATED_NORMAL_EXIT":
                interviewer._check_malpractice_status(read_malpractice_status_api_context)
                request.session.pop('current_mock_interview_id', None)
                request.session.pop('current_round_name', None)
                request.session.pop('current_question_index', None)
                request.session.modified = True
                cleanup_proctor_files_api_context()
                return Response({
                    "message": "Interview terminated due to detected malpractice.",
                    "reason": mock_interview.malpractice_reason,
                    "interview_id": mock_interview.id,
                    "status": mock_interview.status
                }, status=status.HTTP_403_FORBIDDEN)

            # Check if current question index is valid for the current round
            if not questions_for_current_round or current_question_index >= len(questions_for_current_round):
                print(f"DEBUG VIEWS: No valid current question found for {current_round_name} at index {current_question_index}. Attempting to transition.")
                pass 
            else:
                # Get the current question details
                current_question_dict = questions_for_current_round[current_question_index]
                current_question_text = current_question_dict["question_text"]
                current_question_speak_text = current_question_dict["speak_text"]
                
                # Directly record the answer using the new method
                interviewer.record_answer(current_question_text, current_question_speak_text, candidate_answer)
                
                # --- NEW DEBUGGING ADDITION START ---
                print(f"DEBUG VIEWS: State of interviewer.all_interview_answers BEFORE save:")
                for i, qa_pair in enumerate(interviewer.all_interview_answers):
                    print(f"  Q{i+1}: '{qa_pair.get('question_text', '')[:50]}...' A: '{qa_pair.get('answer', '')}'")
                # --- NEW DEBUGGING ADDITION END ---

                # IMPORTANT: Persist the full Q&A transcript after each answer
                mock_interview.full_qa_transcript = interviewer.all_interview_answers
                mock_interview.save(update_fields=['full_qa_transcript'])

                interviewer.current_question_index += 1
            
            next_question_text = None
            next_round_name = interviewer.current_round_name
            message_to_user = "Answer received. Moving to the next question."

            # Determine if we are at the end of the current round
            if interviewer.current_question_index >= len(questions_for_current_round):
                print(f"DEBUG VIEWS: End of round '{interviewer.current_round_name}'. Scoring round.")

                relevant_answers_for_scoring = []
                original_questions_for_completed_round = []
                if interviewer.current_round_name == "communication" or interviewer.current_round_name == "psychometric":
                    original_questions_for_completed_round = interviewer.all_generated_questions[interviewer.current_round_name]["questions"]
                elif interviewer.current_round_name in interviewer.technical_specializations:
                    original_questions_for_completed_round = interviewer.all_generated_questions["technical"]["specializations"].get(interviewer.current_round_name, {}).get("questions", [])
                elif interviewer.current_round_name in ["predict_output", "fix_error", "write_program"]:
                    original_questions_for_completed_round = interviewer.all_generated_questions["coding"][interviewer.current_round_name]["questions"]

                normalized_completed_round_questions = {re.sub(r'\s+', ' ', q['question_text'].strip().lower()) for q in original_questions_for_completed_round}

                for qa_pair in interviewer.all_interview_answers:
                    normalized_qa_question = re.sub(r'\s+', ' ', qa_pair.get('question_text', '').strip().lower())
                    if normalized_qa_question in normalized_completed_round_questions:
                        relevant_answers_for_scoring.append(qa_pair)
                
                round_scoring_results = interviewer._score_round(
                    interviewer.current_round_name,
                    relevant_answers_for_scoring,
                    specialization=interviewer.current_round_name if interviewer.current_round_name in interviewer.technical_specializations else None,
                    coding_stage=interviewer.current_round_name if interviewer.current_round_name in ["predict_output", "fix_error", "write_program"] else None
                )
                
                if interviewer.current_round_name == "coding":
                    if "coding" not in interviewer.round_detailed_results:
                        interviewer.round_detailed_results["coding"] = {}
                    interviewer.round_detailed_results["coding"][interviewer.current_round_name] = {
                        "overall_score": round_scoring_results['overall_score'],
                        "round_summary": round_scoring_results['round_summary'],
                        "questions": round_scoring_results['questions']
                    }
                    interviewer.round_scores["coding"][interviewer.current_round_name] = round_scoring_results['overall_score']
                elif interviewer.current_round_name in interviewer.technical_specializations:
                    if "technical" not in interviewer.round_detailed_results:
                        interviewer.round_detailed_results['technical'] = {}
                    interviewer.round_detailed_results["technical"][interviewer.current_round_name] = {
                        "overall_score": round_scoring_results['overall_score'],
                        "round_summary": round_scoring_results['round_summary'],
                        "questions": round_scoring_results['questions']
                    }
                    interviewer.round_scores["technical"][interviewer.current_round_name] = round_scoring_results['overall_score']
                else: 
                    interviewer.round_detailed_results[interviewer.current_round_name] = {
                        "overall_score": round_scoring_results['overall_score'],
                        "round_summary": round_scoring_results['round_summary'],
                        "questions": round_scoring_results['questions']
                    }
                    interviewer.round_scores[interviewer.current_round_name] = round_scoring_results['overall_score']

                mock_interview.round_analysis_json = interviewer.round_detailed_results
                mock_interview.communication_overall_score = interviewer.round_scores.get("communication", 0)
                mock_interview.psychometric_overall_score = interviewer.round_scores.get("psychometric", 0)
                mock_interview.technical_specialization_scores = interviewer.round_scores["technical"]

                mock_interview.save(update_fields=[
                    'round_analysis_json', 
                    'communication_overall_score', 
                    'psychometric_overall_score', 
                    'technical_specialization_scores'
                ])

                message_to_user = f"Round '{interviewer.current_round_name.replace('_', ' ').title()}' completed. Moving to the next round."
                
                if interviewer.current_round_name == "communication":
                    next_round_name = "psychometric"
                    interviewer.current_round_name = next_round_name
                    interviewer.current_question_index = 0
                    if not interviewer.all_generated_questions["psychometric"]["questions"]:
                        interviewer.current_round_questions = []
                    else:
                        interviewer.current_round_questions = interviewer.all_generated_questions["psychometric"]["questions"]
                elif interviewer.current_round_name == "psychometric":
                    has_technical_questions = False
                    if interviewer.technical_specializations:
                        for spec in interviewer.technical_specializations:
                            if interviewer.all_generated_questions["technical"]["specializations"].get(spec, {}).get("questions"):
                                has_technical_questions = True
                                break
                    if has_technical_questions:
                        first_tech_spec_with_questions = None
                        for spec in interviewer.technical_specializations:
                            if interviewer.all_generated_questions["technical"]["specializations"].get(spec, {}).get("questions"):
                                first_tech_spec_with_questions = spec
                                break
                        next_round_name = first_tech_spec_with_questions
                        interviewer.technical_current_specialization_index = interviewer.technical_specializations.index(first_tech_spec_with_questions)
                        interviewer.current_round_name = next_round_name
                        interviewer.current_round_questions = interviewer.all_generated_questions["technical"]["specializations"].get(interviewer.current_round_name, {}).get("questions", [])
                        interviewer.current_question_index = 0
                        message_to_user = f"Starting Technical Skills Round, focusing on {interviewer.current_round_name}."
                    else:
                        coding_stages_with_questions = [
                            stage for stage in ["predict_output", "fix_error", "write_program"]
                            if interviewer.all_generated_questions["coding"].get(stage, {}).get("questions")
                        ]
                        if coding_stages_with_questions:
                            next_round_name = coding_stages_with_questions[0]
                            interviewer.coding_current_stage_index = list(interviewer.all_generated_questions["coding"].keys()).index(next_round_name)
                            interviewer.current_round_name = next_round_name
                            interviewer.current_round_questions = interviewer.all_generated_questions["coding"][interviewer.current_round_name]["questions"]
                            interviewer.current_question_index = 0
                            message_to_user = f"Starting Coding Skills Round - {interviewer.current_round_name.replace('_', ' ').title()} stage."
                        else:
                            next_round_name = "interview_complete"
                            message_to_user = interviewer.all_generated_questions["interview_complete_message"]
                elif interviewer.current_round_name in interviewer.technical_specializations:
                    current_spec_index = interviewer.technical_specializations.index(interviewer.current_round_name)
                    
                    next_tech_spec_with_questions = None
                    for i in range(current_spec_index + 1, len(interviewer.technical_specializations)):
                        spec = interviewer.technical_specializations[i]
                        if interviewer.all_generated_questions["technical"]["specializations"].get(spec, {}).get("questions"):
                            next_tech_spec_with_questions = spec
                            interviewer.technical_current_specialization_index = i
                            break

                    if next_tech_spec_with_questions:
                        next_round_name = next_tech_spec_with_questions
                        interviewer.current_round_name = next_round_name
                        interviewer.current_round_questions = interviewer.all_generated_questions["technical"]["specializations"].get(interviewer.current_round_name, {}).get("questions", [])
                        interviewer.current_question_index = 0
                        message_to_user = f"Moving to Technical Sub-Round: {interviewer.current_round_name}."
                    else: 
                        coding_stages_with_questions = [
                            stage for stage in ["predict_output", "fix_error", "write_program"]
                            if interviewer.all_generated_questions["coding"].get(stage, {}).get("questions")
                        ]
                        if coding_stages_with_questions:
                            next_round_name = coding_stages_with_questions[0]
                            interviewer.coding_current_stage_index = list(interviewer.all_generated_questions["coding"].keys()).index(next_round_name)
                            interviewer.current_round_name = next_round_name
                            interviewer.current_round_questions = interviewer.all_generated_questions["coding"][interviewer.current_round_name]["questions"]
                            interviewer.current_question_index = 0
                            message_to_user = f"Starting Coding Skills Round - {interviewer.current_round_name.replace('_', ' ').title()} stage."
                        else:
                            next_round_name = "interview_complete"
                            message_to_user = interviewer.all_generated_questions["interview_complete_message"]
                elif interviewer.current_round_name in ["predict_output", "fix_error", "write_program"]:
                    coding_stages_keys_with_questions = [
                        stage for stage in ["predict_output", "fix_error", "write_program"]
                        if interviewer.all_generated_questions["coding"].get(stage, {}).get("questions")
                    ]
                    
                    if not coding_stages_keys_with_questions:
                        next_round_name = "interview_complete"
                        message_to_user = interviewer.all_generated_questions["interview_complete_message"]
                    else:
                        try:
                            current_coding_stage_index_in_filtered = coding_stages_keys_with_questions.index(interviewer.current_round_name)
                            if current_coding_stage_index_in_filtered + 1 < len(coding_stages_keys_with_questions):
                                next_round_name = coding_stages_keys_with_questions[current_coding_stage_index_in_filtered + 1]
                                interviewer.current_round_name = next_round_name
                                interviewer.current_round_questions = interviewer.all_generated_questions["coding"][interviewer.current_round_name]["questions"]
                                interviewer.current_question_index = 0
                                message_to_user = f"Moving to Coding Stage: {interviewer.current_round_name.replace('_', ' ').title()}."
                            else:
                                next_round_name = "interview_complete"
                                message_to_user = interviewer.all_generated_questions["interview_complete_message"]
                        except ValueError:
                             next_round_name = "interview_complete"
                             message_to_user = interviewer.all_generated_questions["interview_complete_message"]
                else:
                    next_round_name = "interview_complete"
                    message_to_user = interviewer.all_generated_questions["interview_complete_message"]


                if next_round_name == "interview_complete":
                    interviewer._score_language_proficiency(interviewer.all_interview_answers)
                    
                    total_score_sum = 0
                    num_scores = 0

                    if "communication" in interviewer.round_scores:
                        total_score_sum += interviewer.round_scores["communication"]
                        num_scores += 1
                    if "psychometric" in interviewer.round_scores:
                        total_score_sum += interviewer.round_scores["psychometric"]
                        num_scores += 1

                    coding_stage_scores = [score for score in interviewer.round_scores["coding"].values()]
                    if coding_stage_scores:
                        avg_coding_score = sum(coding_stage_scores) / len(coding_stage_scores)
                        total_score_sum += avg_coding_score
                        num_scores += 1

                    technical_specialization_scores = [score for score in interviewer.round_scores["technical"].values()]
                    if technical_specialization_scores:
                        avg_technical_score = sum(technical_specialization_scores) / len(technical_specialization_scores)
                        total_score_sum += avg_technical_score
                        num_scores += 1
                    
                    total_score_sum += interviewer.language_score
                    num_scores += 1

                    if num_scores > 0:
                        interviewer.global_readiness_score = int(total_score_sum / num_scores)
                    else:
                        interviewer.global_readiness_score = 0

                    interviewer._generate_final_report()

                    request.session.pop('current_mock_interview_id', None)
                    request.session.pop('current_round_name', None)
                    request.session.pop('current_question_index', None)
                    request.session.modified = True
                    cleanup_proctor_files_api_context()

                    return Response({
                        "message": message_to_user,
                        "interview_id": mock_interview.id,
                        "status": mock_interview.status,
                        "global_readiness_score": mock_interview.global_readiness_score,
                        "report_url": request.build_absolute_uri(f'/api/mock-interview/report/{mock_interview.id}/')
                    }, status=status.HTTP_200_OK)
                
                if interviewer.current_round_questions and interviewer.current_question_index < len(interviewer.current_round_questions):
                    next_question_text = interviewer.current_round_questions[interviewer.current_question_index]["question_text"]
                    interviewer._add_to_chat_history("model", next_question_text)
                else:
                    next_round_name = "interview_complete"
                    message_to_user = interviewer.all_generated_questions["interview_complete_message"]
                    
                    interviewer._score_language_proficiency(interviewer.all_interview_answers)
                    total_score_sum = 0
                    num_scores = 0
                    if "communication" in interviewer.round_scores: total_score_sum += interviewer.round_scores["communication"]; num_scores += 1
                    if "psychometric" in interviewer.round_scores: total_score_sum += interviewer.round_scores["psychometric"]; num_scores += 1
                    coding_stage_scores = [score for score in interviewer.round_scores["coding"].values()]
                    if coding_stage_scores: avg_coding_score = sum(coding_stage_scores) / len(coding_stage_scores); total_score_sum += avg_coding_score; num_scores += 1
                    technical_specialization_scores = [score for score in interviewer.round_scores["technical"].values()]
                    if technical_specialization_scores: avg_technical_score = sum(technical_specialization_scores) / len(technical_specialization_scores); total_score_sum += avg_technical_score; num_scores += 1
                    total_score_sum += interviewer.language_score; num_scores += 1
                    interviewer.global_readiness_score = int(total_score_sum / num_scores) if num_scores > 0 else 0

                    interviewer._generate_final_report()

                    request.session.pop('current_mock_interview_id', None)
                    request.session.pop('current_round_name', None)
                    request.session.pop('current_question_index', None)
                    request.session.modified = True
                    cleanup_proctor_files_api_context()
                    return Response({
                        "message": message_to_user,
                        "interview_id": mock_interview.id,
                        "status": mock_interview.status,
                        "global_readiness_score": mock_interview.global_readiness_score,
                        "report_url": request.build_absolute_uri(f'/api/mock-interview/report/{mock_interview.id}/')
                    }, status=status.HTTP_200_OK)

            else: 
                next_question_text = interviewer.current_round_questions[interviewer.current_question_index]["question_text"]
                interviewer._add_to_chat_history("model", next_question_text)
            
            request.session['current_round_name'] = interviewer.current_round_name
            request.session['current_question_index'] = interviewer.current_question_index
            request.session.modified = True 

            return Response({
                "message": message_to_user,
                "interview_id": mock_interview.id,
                "current_round": interviewer.current_round_name,
                "question_number": interviewer.current_question_index + 1,
                "question_text": next_question_text,
                "status": mock_interview.status
            }, status=status.HTTP_200_OK)

        except MockInterviewResult.DoesNotExist:
            return Response({"error": "Mock interview session not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"Error submitting answer: {e}")
            if interview_id:
                try:
                    mock_interview = MockInterviewResult.objects.get(id=interview_id)
                    mock_interview.status = MockInterviewResult.InterviewStatus.TERMINATED_ERROR
                    mock_interview.malpractice_detected = True
                    mock_interview.malpractice_reason = f"System error during answer submission: {e}"
                    mock_interview.interview_end_time = timezone.now()
                    mock_interview.save()
                except MockInterviewResult.DoesNotExist:
                    pass
            
            request.session.pop('current_mock_interview_id', None)
            request.session.pop('current_round_name', None)
            request.session.pop('current_question_index', None)
            request.session.modified = True
            cleanup_proctor_files_api_context()
            return Response({"error": f"An error occurred while processing your answer: {e}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
# --- MockInterviewSubmitAnswerView.post method ---
class MockInterviewReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            mock_interview = MockInterviewResult.objects.get(pk=pk, user=request.user)
            serializer = MockInterviewResultSerializer(mock_interview)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except MockInterviewResult.DoesNotExist:
            return Response({"error": "Mock interview report not found or you do not have permission to view it."},
                            status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"Error fetching interview report: {e}")
            return Response({"error": f"An error occurred while fetching the report: {e}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        


class MalpracticeDetectionView(APIView):
    permission_classes = [IsAuthenticated] # Only authenticated users can trigger this

    def post(self, request, *args, **kwargs):
        """
        Terminates the current in-progress mock interview due to detected malpractice.
        Expects 'type_of_malpractice' in the request body.
        """
        type_of_malpractice = request.data.get('type_of_malpractice')
        # We will use the current time for interview_end_time.
        # If 'time_of_malpractice' needs to be a separate, specific timestamp from the client,
        # you'll need to add a field to MockInterviewResult model and process it here.

        if not type_of_malpractice:
            return Response(
                {"error": "Missing 'type_of_malpractice' in request body."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get the ID of the current interview from the session
        current_mock_interview_id = request.session.get('current_mock_interview_id')

        if not current_mock_interview_id:
            return Response(
                {"error": "No active interview found for this user in the session."},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            # Retrieve the in-progress interview for the current user
            mock_interview = MockInterviewResult.objects.get(
                id=current_mock_interview_id,
                user=request.user, # Ensure the interview belongs to the authenticated user
                status=MockInterviewResult.InterviewStatus.IN_PROGRESS # Only terminate if it's currently in progress
            )

            # Update the interview status for malpractice
            mock_interview.malpractice_detected = True
            mock_interview.malpractice_reason = f"Malpractice detected: {type_of_malpractice}"
            mock_interview.status = MockInterviewResult.InterviewStatus.TERMINATED_MALPRACTICE
            mock_interview.interview_end_time = timezone.now() # Set the end time
            mock_interview.save()

            # Clear session data to prevent further interaction with this interview
            request.session.pop('current_mock_interview_id', None)
            request.session.pop('current_round_name', None)
            request.session.pop('current_question_index', None)
            request.session.modified = True # Mark session as modified to ensure changes are saved

            # Clean up any associated proctoring files
            cleanup_proctor_files_api_context()

            return Response(
                {
                    "message": "Interview terminated due to malpractice.",
                    "interview_id": mock_interview.id,
                    "malpractice_reason": mock_interview.malpractice_reason,
                    "status": mock_interview.status
                },
                status=status.HTTP_200_OK
            )

        except MockInterviewResult.DoesNotExist:
            return Response(
                {"error": "No active interview found with the provided ID for this user, or interview is not in progress."},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            print(f"Error terminating interview due to malpractice: {e}")
            return Response(
                {"error": f"An internal error occurred while terminating the interview: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        

    # ------------------------------------------------------rahul 31 july-------------------------------------------------------------------#



from .serializers import DesiredDomainUpdateSerializer
class UpdateDesiredDomainView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            resume = Resume.objects.get(talent_id=request.user)
        except Resume.DoesNotExist:
            return Response({"detail": "Resume not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = DesiredDomainUpdateSerializer(resume, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Desired domain updated successfully."}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




    #----------------------------------------------------------------------------------------------------------------------------------------#