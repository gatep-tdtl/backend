# MODIFIED/FINAL CODE - All top-level indentation removed

_B = 'content'
_A = 'meta-llama/Meta-Llama-3-70B-Instruct'
import os, fitz, json, re, collections.abc
from django.http import JsonResponse
from django.conf import settings
from huggingface_hub import InferenceClient
from .models import Resume, CustomUser
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

# --- AI Analysis Service Imports (for the analysis views at the end) ---
from .ai_analysis_services import (
    generate_resume_review,
    extract_text_from_pdf_path,
    generate_skill_gap_analysis,
    generate_career_roadmap
)

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


class ResumeAIPipeline:
    # This class is well-designed and does not need changes.
    # Its sole responsibility is to process a PDF.
    def __init__(self):
        self.client = InferenceClient(token=HFF_TOKEN)
        self.temp_pdf_paths = []

    def _extract_text_from_pdf(self, pdf_path):
        try:
            doc = fitz.open(pdf_path)
            full_text = "".join(page.get_text() for page in doc)
            doc.close()
            return re.sub(r'\s*\n\s*', '\n', full_text).strip()
        except Exception as e:
            print(f"Error extracting text from PDF at {pdf_path}: {e}")
            return ""

    def _build_prompt(self, pdf_text):
        return f'''
You are an AI assistant that extracts structured information from resume text. Your goal is to parse the provided text and structure it into a specific JSON format.

Return your output in **strict JSON format only**. Do NOT include any markdown (e.g., ```json), conversational text, or explanations. If a field or section is not found in the text, omit it or set its value to null/empty. The JSON structure must follow this schema:
{{{{
    "personal_info": {{{{ "name": "...", "email": "...", "phone": "...", "current_location": "..."}}}},
    "links": {{{{ "linkedin_url": "...", "github_url": "...", "portfolio_url": "..." }}}},
    "professional_summary": "A concise 3-4 sentence summary.",
    "skills": ["Skill 1", "Skill 2"],
    "experience": [{{{{ "title": "...", "company": "...", "duration": "...", "responsibilities": ["..."] }}}}],
    "projects": [{{{{ "name": "...", "description": "...", "url": "..." }}}}],
    "education_details": {{{{
        "degree": {{{{ "degree_name": "...", "institution_name": "...", "year_passing": "...", "score": "..." }}}},
        "twelfth": {{{{ "board_name": "...", "college_name": "...", "year_passing": "...", "score": "..." }}}},
        "tenth": {{{{ "board_name": "...", "school_name": "...", "year_passing": "...", "score": "..." }}}}
    }}}},
    "certifications": ["Certification 1", "Certification 2"],
    "awards": ["Award 1"],
    "publications": ["Publication 1"],
    "languages": {{{{ "Language 1": "Proficiency" }}}},
    "interests": ["Interest 1"]
}}}}

---
Text Extracted from Resume PDF:
{pdf_text}

---
Strict JSON Output:
'''

    def _call_llama_model(self, prompt):
        response = self.client.chat.completions.create(model=_A, messages=[{'role': 'user', _B: prompt}], max_tokens=4096)
        content = response.choices[0].message.content
        clean_content = re.sub(r'^```json\s*|\s*```$', '', content.strip())
        try:
            return json.loads(clean_content)
        except json.JSONDecodeError as e:
            print(f"LLM returned invalid JSON: {clean_content}")
            raise e # Re-raise the exception to be caught by the caller

    def process_resume_data(self, resume_pdf_file):
        if not resume_pdf_file:
            return {}

        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_uploads')
        os.makedirs(temp_dir, exist_ok=True)
        pdf_path = os.path.join(temp_dir, resume_pdf_file.name)

        try:
            with open(pdf_path, 'wb+') as temp_file:
                for chunk in resume_pdf_file.chunks():
                    temp_file.write(chunk)
            self.temp_pdf_paths.append(pdf_path)

            pdf_text = self._extract_text_from_pdf(pdf_path)
            if not pdf_text:
                return {}

            prompt = self._build_prompt(pdf_text)
            return self._call_llama_model(prompt)
        except Exception as e:
            print(f"Error in AI pipeline: {e}")
            return {}

    def get_temp_pdf_paths(self):
        return self.temp_pdf_paths


class ResumeBuilderAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ai_pipeline = ResumeAIPipeline()

    def _safe_json_loads(self, json_string, default_value=None):
        if not json_string: return default_value
        try: return json.loads(json_string)
        except (json.JSONDecodeError, TypeError): return default_value

    def _deep_update(self, base, updates):
        for key, value in updates.items():
            if isinstance(value, collections.abc.Mapping) and key in base and isinstance(base[key], collections.abc.Mapping):
                base[key] = self._deep_update(base[key], value)
            else:
                base[key] = value
        return base

    def _structure_form_data(self, data):
        """
        Unifies processing for both JSON and form-data payloads.
        It starts with the request's data payload (excluding files) and
        restructures any known flat keys into their correct nested dictionaries.
        """
        # Step 1: Create a mutable copy of the request data. This now correctly
        # handles both QueryDict (from forms) and dict (from JSON) without
        # trying to serialize file objects.
        # This is the primary fix for the "not JSON serializable" error.
        structured_data = {k: v for k, v in data.items()}

        # 2. Handle fields that might be sent as JSON-encoded strings (common in form-data)
        for field in list(structured_data.keys()):
            value = structured_data[field]
            if isinstance(value, str) and value.strip().startswith(('{', '[')):
                try:
                    structured_data[field] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass

        # 3. Restructure flat keys into the 'personal_info' nested dictionary.
        personal_info_keys = [L, M, N, S, T, U, V, 'current_area', 'permanent_area', 'current_city', 'permanent_city', 'current_district', 'permanent_district', 'current_state', 'permanent_state', 'current_country', 'permanent_country']
        personal_info_updates = {}
        for key in personal_info_keys:
            if key in structured_data:
                personal_info_updates[key] = structured_data.pop(key)
        
        if personal_info_updates:
            existing_pi = structured_data.get(B, {})
            structured_data[B] = {**existing_pi, **personal_info_updates}

        # 4. Restructure flat keys into the 'links' nested dictionary.
        link_keys = [W, X, Y, Z, a]
        link_updates = {}
        for key in link_keys:
            if key in structured_data:
                link_updates[key] = structured_data.pop(key)

        if link_updates:
            existing_links = structured_data.get(I, {})
            structured_data[I] = {**existing_links, **link_updates}

        # 5. Restructure flat keys into the 'education_details' nested dictionary.
        edu_map = {
            F: {'board_name': 'tenth_board_name', 'school_name': 'tenth_school_name', 'year_passing': 'tenth_year_passing', 'score': 'tenth_score'},
            G: {'board_name': 'twelfth_board_name', 'college_name': 'twelfth_college_name', 'year_passing': 'twelfth_year_passing', 'score': 'twelfth_score'},
            H: {'course_name': 'diploma_course_name', 'institution_name': 'diploma_institution_name', 'year_passing': 'diploma_year_passing', 'score': 'diploma_score'},
            C: {'degree_name': g, 'institution_name': 'degree_institution_name', 'specialization': 'degree_specialization', 'year_passing': 'degree_year_passing', 'score': 'degree_score'}
        }
        education_updates = {}
        for level, fields_map in edu_map.items():
            level_updates = {}
            for dest_key, src_key in fields_map.items():
                if src_key in structured_data:
                    level_updates[dest_key] = structured_data.pop(src_key)
            if level_updates:
                education_updates[level] = level_updates
        
        if education_updates:
            existing_edu = structured_data.get(A, {})
            structured_data[A] = self._deep_update(existing_edu, education_updates)

        return structured_data
        
    def _serialize_resume_to_json(self, resume_instance):
        request = self.request
        get_url = lambda f: request.build_absolute_uri(f.url) if f and hasattr(f, 'url') else None

        # This method is correct and does not need changes.
        # ... (code from previous answer is correct here) ...
        return {
            'id': resume_instance.pk, 'talent_id': resume_instance.talent_id.pk, 'name': resume_instance.name, 'email': resume_instance.email, 'phone': resume_instance.phone, 'current_location': resume_instance.current_location, 'aadhar_number': resume_instance.aadhar_number, 'passport_number': resume_instance.passport_number, 'current_company': resume_instance.current_company, 'profile_photo_url': get_url(resume_instance.profile_photo), 'resume_pdf_url': get_url(resume_instance.resume_pdf), 'linkedin_url': resume_instance.linkedin_url, 'github_url': resume_instance.github_url, 'portfolio_url': resume_instance.portfolio_url, 'stackoverflow_url': resume_instance.stackoverflow_url, 'medium_or_blog_url': resume_instance.medium_or_blog_url, 'summary': resume_instance.summary, 'generated_summary': resume_instance.generated_summary, 'preferred_tech_stack': resume_instance.preferred_tech_stack, 'dev_environment': resume_instance.dev_environment, 'volunteering_experience': resume_instance.volunteering_experience, 'extracurriculars': resume_instance.extracurriculars, 'work_arrangement': resume_instance.work_arrangement, 'preferred_location': resume_instance.preferred_location, 'work_authorization': resume_instance.work_authorization, 'criminal_record_disclosure': resume_instance.criminal_record_disclosure, 'document_verification': resume_instance.document_verification, 'current_area': resume_instance.current_area, 'permanent_area': resume_instance.permanent_area, 'current_city': resume_instance.current_city, 'permanent_city': resume_instance.permanent_city, 'current_district': resume_instance.current_district, 'permanent_district': resume_instance.permanent_district, 'current_state': resume_instance.current_state, 'permanent_state': resume_instance.permanent_state, 'current_country': resume_instance.current_country, 'permanent_country': resume_instance.permanent_country, 'languages': resume_instance.languages, 'frameworks_tools': resume_instance.frameworks_tools, 'diploma_details': resume_instance.diploma_details, 'degree_details': resume_instance.degree_details, 'certification_details': resume_instance.certification_details, 'certification_photos': resume_instance.certification_photos, 'work_preferences': resume_instance.work_preferences, 'work_authorizations': resume_instance.work_authorizations, 'professional_links': resume_instance.professional_links, 'skills': self._safe_json_loads(resume_instance.skills, []), 'experience': self._safe_json_loads(resume_instance.experience, []), 'projects': self._safe_json_loads(resume_instance.projects, []), 'certifications': self._safe_json_loads(resume_instance.certifications, []), 'awards': self._safe_json_loads(resume_instance.awards, []), 'publications': self._safe_json_loads(resume_instance.publications, []), 'open_source_contributions': self._safe_json_loads(resume_instance.open_source_contributions, []), 'interests': self._safe_json_loads(resume_instance.interests, []), 'references': self._safe_json_loads(resume_instance.references, []), 'preferences': self._safe_json_loads(resume_instance.preferences, {}),
            'education_details': {
                'tenth': {'board_name': resume_instance.tenth_board_name, 'school_name': resume_instance.tenth_school_name, 'year_passing': resume_instance.tenth_year_passing, 'score': resume_instance.tenth_score, 'result_upload_url': get_url(resume_instance.tenth_result_upload)},
                'twelfth': {'board_name': resume_instance.twelfth_board_name, 'college_name': resume_instance.twelfth_college_name, 'year_passing': resume_instance.twelfth_year_passing, 'score': resume_instance.twelfth_score, 'result_upload_url': get_url(resume_instance.twelfth_result_upload)},
                'diploma': {'course_name': resume_instance.diploma_course_name, 'institution_name': resume_instance.diploma_institution_name, 'year_passing': resume_instance.diploma_year_passing, 'score': resume_instance.diploma_score, 'result_upload_url': get_url(resume_instance.diploma_result_upload)},
                'degree': {'degree_name': resume_instance.degree_name, 'institution_name': resume_instance.degree_institution_name, 'specialization': resume_instance.degree_specialization, 'year_passing': resume_instance.degree_year_passing, 'score': resume_instance.degree_score, 'result_upload_url': get_url(resume_instance.degree_result_upload)}
            },
            'created_at': resume_instance.created_at.isoformat(), 'updated_at': resume_instance.updated_at.isoformat(),
        }

    def _update_resume_instance(self, resume, data, files):
        """Updates the resume model instance from a dictionary of data."""
        # Helper to safely get a value, converting None to "" for string-based fields
        def get_safe_str(source_dict, key, default=""):
            val = source_dict.get(key)
            return val if val is not None else default

        # ... (personal_info, links, and education_details logic remains the same) ...
        personal_info = data.get(B, {})
        if personal_info:
            resume.name = get_safe_str(personal_info, L)
            resume.email = get_safe_str(personal_info, M)
            resume.phone = get_safe_str(personal_info, N)
            for key in [S, T, U, V, 'current_area', 'permanent_area', 'current_city', 'permanent_city', 'current_district', 'permanent_district', 'current_state', 'permanent_state', 'current_country', 'permanent_country']:
                if key in personal_info:
                    setattr(resume, key, get_safe_str(personal_info, key))

        links = data.get(I, {})
        if links:
            resume.linkedin_url = get_safe_str(links, W)
            resume.github_url = get_safe_str(links, X)
            resume.portfolio_url = get_safe_str(links, Y)
            resume.stackoverflow_url = get_safe_str(links, Z)
            resume.medium_or_blog_url = get_safe_str(links, a)

        education_details = data.get(A, {})
        if education_details and isinstance(education_details, dict):
            edu_key_map = {
                'tenth': {
                    'board_name': 'tenth_board_name', 'school_name': 'tenth_school_name',
                    'year_passing': 'tenth_year_passing', 'score': 'tenth_score',
                },
                'twelfth': {
                    'board_name': 'twelfth_board_name', 'college_name': 'twelfth_college_name',
                    'year_passing': 'twelfth_year_passing', 'score': 'twelfth_score',
                },
                'diploma': {
                    'course_name': 'diploma_course_name', 'institution_name': 'diploma_institution_name',
                    'year_passing': 'diploma_year_passing', 'score': 'diploma_score',
                },
                'degree': {
                    'degree_name': 'degree_name', 'institution_name': 'degree_institution_name',
                    'specialization': 'degree_specialization', 'year_passing': 'degree_year_passing',
                    'score': 'degree_score',
                }
            }
            for edu_level, details_dict in education_details.items():
                if edu_level in edu_key_map and isinstance(details_dict, dict):
                    for json_key, value in details_dict.items():
                        model_field = edu_key_map[edu_level].get(json_key)
                        if model_field and hasattr(resume, model_field):
                            setattr(resume, model_field, value)
        
        # --- START OF THE FIX ---
        # Update remaining top-level fields
        # Define a set of read-only or nested fields to skip in this loop.
        SKIPPED_FIELDS = {
            # Nested fields handled above
            B, I, A, 
            # Read-only fields that should never be updated from request data
            'id', 'talent_id', 'created_at', 'updated_at'
        }
        
        for field, value in data.items():
            if field in SKIPPED_FIELDS:  # This is the corrected line
                continue 

            if hasattr(resume, field):
                # This logic for handling field types is already correct
                if field in ['skills', 'experience', 'projects', 'certifications', 'awards', 'publications', 'open_source_contributions', 'interests', 'references', 'preferences']:
                    setattr(resume, field, json.dumps(value or []))
                elif field in ['languages', 'frameworks_tools', 'diploma_details', 'degree_details', 'certification_details', 'certification_photos', 'work_preferences', 'work_authorizations', 'professional_links']:
                    if field == 'languages':
                        setattr(resume, field, value or {})
                    else:
                        setattr(resume, field, value or [])
                else:
                    setattr(resume, field, value if value is not None else "")
        # --- END OF THE FIX ---
        
        # Update files (This part is correct)
        for field, file_obj in files.items():
            if hasattr(resume, field):
                setattr(resume, field, file_obj)

        return resume

    def _process_and_update_resume(self, request, user):
        """
        Handles the core logic for creating and updating a resume for POST, PUT, and PATCH.
        This version correctly prioritizes data sources across all methods.
        """
        # Step 1: Get or Create the Resume instance for the authenticated user.
        resume, created = Resume.objects.get_or_create(talent_id=user, defaults={'is_deleted': False})
        if resume.is_deleted:
            resume.is_deleted = False

        # Step 2: Extract data from the request.
        files = request.FILES
        
        # Step 3: Run AI pipeline on a new PDF, if provided. This is our lowest-priority data.
        pdf_extracted_data = self.ai_pipeline.process_resume_data(files.get('resume_pdf'))
        
        # Step 4: Get the user's explicit input. This is our highest-priority data.
        user_input_data = self._structure_form_data(request.data)

        # Step 5: Establish the base data.
        # For a brand new resume (POST) or a full replacement (PUT), we start fresh.
        # For a partial update (PATCH), we start with the data already in the database.
        base_data = {}
        if request.method == 'PATCH':
            base_data = self._serialize_resume_to_json(resume)

        # Step 6: Merge all data sources with the correct priority.
        # Priority Order (from lowest to highest):
        # 1. Base Data (existing DB state for PATCH, empty for POST/PUT)
        # 2. PDF Extracted Data
        # 3. User's Explicit Input
        
        # Merge base with PDF data
        merged_data = self._deep_update(base_data, pdf_extracted_data)
        
        # Merge the result with the user's input, which overwrites everything else.
        final_data = self._deep_update(merged_data, user_input_data)
        
        # Step 7: Update the model instance with the final, merged data and save it.
        self._update_resume_instance(resume, final_data, files)
        resume.save()

        return resume, created

    # The GET, POST, PUT, PATCH, DELETE methods are all correct and 
    # don't need changes. They rely on the fixed methods above.
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
            return JsonResponse({'message': message, 'resume_id': resume.pk}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
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
# --- AI ANALYSIS MODULES VIEWS (Unchanged, they are fine) ---
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
    def get(self, request, *args, **kwargs):
        user = request.user
        try:
            resume = Resume.objects.get(talent_id=user, is_deleted=False)
            resume_skills = self._safe_json_loads(resume.skills, [])
            if not resume_skills:
                return JsonResponse({'error': 'No skills found in your resume. Please add skills first.'}, status=status.HTTP_400_BAD_REQUEST)

            job_roles_on_portal = [
                "AI Engineer, NLP focus, PyTorch", "Senior Machine Learning Engineer (MLOps)",
                "Data Scientist with Deep Learning experience", "Research Engineer in Computer Vision"
            ]

            skill_gap_result = generate_skill_gap_analysis(resume_skills, job_roles_on_portal)
            return JsonResponse(skill_gap_result, status=status.HTTP_200_OK)
        except Resume.DoesNotExist:
            return JsonResponse({'error': 'Resume profile not found for this user.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return JsonResponse({'error': f'An internal server error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CareerRoadmapAPIView(APIView):
    permission_classes = [IsAuthenticated]
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
            experience_years = len(experience) * 1.5

            roadmap_result = generate_career_roadmap(current_role, experience_years, interests, skills)
            return JsonResponse(roadmap_result, status=status.HTTP_200_OK)
        except Resume.DoesNotExist:
            return JsonResponse({'error': 'Resume profile not found for this user.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return JsonResponse({'error': f'An internal server error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ... your other views like TrendingSkillsListView ...
from rest_framework import generics
from .models import TrendingSkill
from .serializers import TrendingSkillSerializer

class TrendingSkillsListView(generics.ListAPIView):
    queryset = TrendingSkill.objects.all()
    serializer_class = TrendingSkillSerializer
    permission_classes = [IsAuthenticated]

from django.core.cache import cache  # <--- ADD THIS LINE
 
 
from .ai_cultural_prep import generate_cultural_preparation

from rest_framework.views import APIView, Response
class CulturalPreparationAPIView(APIView):
    """
    Provides AI-generated cultural preparation insights for a fixed
    set of countries (UAE, USA, EU, Singapore).
   
    This view uses caching to avoid repeated, expensive API calls.
    """
    permission_classes = [IsAuthenticated]
 
    def get(self, request, *args, **kwargs):
        # Define a unique key for our cache
        cache_key = 'cultural_preparation_insights'
       
        # 1. First, try to get the data from the cache
        cached_insights = cache.get(cache_key)
        if cached_insights:
            print("Serving cultural insights from CACHE.")
            return Response(cached_insights, status=status.HTTP_200_OK)
 
        # 2. If not in cache, call the AI service
        print("Cache miss. Calling AI service for cultural insights...")
       
        # --- Your hardcoded list of countries ---
        countries = ["UAE", "USA", "EU", "Singapore"]
 
        try:
            insights = generate_cultural_preparation(countries)
           
            if insights is None:
                return Response(
                    {"error": "Failed to generate insights. The AI model may be unavailable."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
           
            # 3. Save the new data to the cache for 24 hours (86400 seconds)
            cache.set(cache_key, insights, timeout=86400)
           
            # 4. Return the successful response
            return Response(insights, status=status.HTTP_200_OK)
 
        except Exception as e:
            return Response(
                {"error": f"An unexpected internal server error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )










# # MODIFIED/FINAL CODE - All top-level indentation removed




# _B = 'content'
# _A = 'meta-llama/Meta-Llama-3-70B-Instruct'
# import os, fitz, json, re, collections.abc
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
#     # This class is well-designed and does not need changes.
#     # Its sole responsibility is to process a PDF.
#     def __init__(self):
#         self.client = InferenceClient(token=HFF_TOKEN)
#         self.temp_pdf_paths = []

#     def _extract_text_from_pdf(self, pdf_path):
#         try:
#             doc = fitz.open(pdf_path)
#             full_text = "".join(page.get_text() for page in doc)
#             doc.close()
#             return re.sub(r'\s*\n\s*', '\n', full_text).strip()
#         except Exception as e:
#             print(f"Error extracting text from PDF at {pdf_path}: {e}")
#             return ""

#     def _build_prompt(self, pdf_text):
#         return f'''
# You are an AI assistant that extracts structured information from resume text. Your goal is to parse the provided text and structure it into a specific JSON format.

# Return your output in **strict JSON format only**. Do NOT include any markdown (e.g., ```json), conversational text, or explanations. If a field or section is not found in the text, omit it or set its value to null/empty. The JSON structure must follow this schema:
# {{{{
#     "personal_info": {{{{ "name": "...", "email": "...", "phone": "...", "current_location": "..."}}}},
#     "links": {{{{ "linkedin_url": "...", "github_url": "...", "portfolio_url": "..." }}}},
#     "professional_summary": "A concise 3-4 sentence summary.",
#     "skills": ["Skill 1", "Skill 2"],
#     "experience": [{{{{ "title": "...", "company": "...", "duration": "...", "responsibilities": ["..."] }}}}],
#     "projects": [{{{{ "name": "...", "description": "...", "url": "..." }}}}],
#     "education_details": {{{{
#         "degree": {{{{ "degree_name": "...", "institution_name": "...", "year_passing": "...", "score": "..." }}}},
#         "twelfth": {{{{ "board_name": "...", "college_name": "...", "year_passing": "...", "score": "..." }}}},
#         "tenth": {{{{ "board_name": "...", "school_name": "...", "year_passing": "...", "score": "..." }}}}
#     }}}},
#     "certifications": ["Certification 1", "Certification 2"],
#     "awards": ["Award 1"],
#     "publications": ["Publication 1"],
#     "languages": {{{{ "Language 1": "Proficiency" }}}},
#     "interests": ["Interest 1"]
# }}}}

# ---
# Text Extracted from Resume PDF:
# {pdf_text}

# ---
# Strict JSON Output:
# '''

#     def _call_llama_model(self, prompt):
#         response = self.client.chat.completions.create(model=_A, messages=[{'role': 'user', _B: prompt}], max_tokens=4096)
#         content = response.choices[0].message.content
#         clean_content = re.sub(r'^```json\s*|\s*```$', '', content.strip())
#         try:
#             return json.loads(clean_content)
#         except json.JSONDecodeError as e:
#             print(f"LLM returned invalid JSON: {clean_content}")
#             raise e # Re-raise the exception to be caught by the caller

#     def process_resume_data(self, resume_pdf_file):
#         if not resume_pdf_file:
#             return {}

#         temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_uploads')
#         os.makedirs(temp_dir, exist_ok=True)
#         pdf_path = os.path.join(temp_dir, resume_pdf_file.name)

#         try:
#             with open(pdf_path, 'wb+') as temp_file:
#                 for chunk in resume_pdf_file.chunks():
#                     temp_file.write(chunk)
#             self.temp_pdf_paths.append(pdf_path)

#             pdf_text = self._extract_text_from_pdf(pdf_path)
#             if not pdf_text:
#                 return {}

#             prompt = self._build_prompt(pdf_text)
#             return self._call_llama_model(prompt)
#         except Exception as e:
#             print(f"Error in AI pipeline: {e}")
#             return {}

#     def get_temp_pdf_paths(self):
#         return self.temp_pdf_paths


# class ResumeBuilderAPIView(APIView):
#     permission_classes = [IsAuthenticated]

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.ai_pipeline = ResumeAIPipeline()

#     def _safe_json_loads(self, json_string, default_value=None):
#         if not json_string: return default_value
#         try: return json.loads(json_string)
#         except (json.JSONDecodeError, TypeError): return default_value

#     def _deep_update(self, base, updates):
#         for key, value in updates.items():
#             if isinstance(value, collections.abc.Mapping) and key in base and isinstance(base[key], collections.abc.Mapping):
#                 base[key] = self._deep_update(base[key], value)
#             else:
#                 base[key] = value
#         return base

#     def _structure_form_data(self, data):
#         structured = {}
#         # Parse fields that are sent as JSON strings
#         for field in [h, i, j, k, l, m, n, o, p, q, E, 'frameworks_tools', 'diploma_details', 'degree_details', 'certification_details', 'certification_photos', 'work_preferences', 'work_authorizations', 'professional_links']:
#             if field in data:
#                 value = data[field]
#                 if isinstance(value, str) and value:
#                     try:
#                         structured[field] = json.loads(value)
#                     except json.JSONDecodeError:
#                         structured[field] = value
#                 else:
#                     structured[field] = value

#         # Map flat fields to nested 'personal_info'
#         structured[B] = {}
#         for key in [L, M, N, S, T, U, V, 'current_area', 'permanent_area', 'current_city', 'permanent_city', 'current_district', 'permanent_district', 'current_state', 'permanent_state', 'current_country', 'permanent_country']:
#             if key in data:
#                 structured[B][key] = data.get(key)
        
#         # Map flat fields to nested 'links'
#         structured[I] = {}
#         for key in [W, X, Y, Z, a]:
#             if key in data:
#                 structured[I][key] = data.get(key)

#         # --- START OF THE FIX ---
#         # Handle 'education_details' to support both nested JSON objects and flat form keys.
        
#         # 1. Use the nested 'education_details' object from the payload as the base.
#         #    This is a deep copy to prevent modifying the original request data.
#         edu_from_nested = json.loads(json.dumps(data.get(A, {})))

#         # 2. Parse any flat educational keys (e.g., 'tenth_board_name').
#         edu_from_flat_keys = {}
#         edu_map = {
#             F: {'board_name': 'tenth_board_name', 'school_name': 'tenth_school_name', 'year_passing': 'tenth_year_passing', 'score': 'tenth_score'},
#             G: {'board_name': 'twelfth_board_name', 'college_name': 'twelfth_college_name', 'year_passing': 'twelfth_year_passing', 'score': 'twelfth_score'},
#             H: {'course_name': 'diploma_course_name', 'institution_name': 'diploma_institution_name', 'year_passing': 'diploma_year_passing', 'score': 'diploma_score'},
#             C: {'degree_name': g, 'institution_name': 'degree_institution_name', 'specialization': 'degree_specialization', 'year_passing': 'degree_year_passing', 'score': 'degree_score'}
#         }
#         for level, fields_map in edu_map.items():
#             for dest_key, src_key in fields_map.items():
#                 if src_key in data:
#                     if level not in edu_from_flat_keys:
#                         edu_from_flat_keys[level] = {}
#                     edu_from_flat_keys[level][dest_key] = data.get(src_key)
        
#         # 3. Merge them. The flat keys will overwrite the nested object's values if there's an overlap.
#         structured[A] = self._deep_update(edu_from_nested, edu_from_flat_keys)
        
#         # Handle other top-level fields
#         for key in [s, O, P, Q, R, b, c, d, f, 'document_verification']:
#              if key in data:
#                  structured[key] = data.get(key)

#         return structured
        
#     def _serialize_resume_to_json(self, resume_instance):
#         request = self.request
#         get_url = lambda f: request.build_absolute_uri(f.url) if f and hasattr(f, 'url') else None

#         # This method is correct and does not need changes.
#         # ... (code from previous answer is correct here) ...
#         return {
#             'id': resume_instance.pk, 'talent_id': resume_instance.talent_id.pk, 'name': resume_instance.name, 'email': resume_instance.email, 'phone': resume_instance.phone, 'current_location': resume_instance.current_location, 'aadhar_number': resume_instance.aadhar_number, 'passport_number': resume_instance.passport_number, 'current_company': resume_instance.current_company, 'profile_photo_url': get_url(resume_instance.profile_photo), 'resume_pdf_url': get_url(resume_instance.resume_pdf), 'linkedin_url': resume_instance.linkedin_url, 'github_url': resume_instance.github_url, 'portfolio_url': resume_instance.portfolio_url, 'stackoverflow_url': resume_instance.stackoverflow_url, 'medium_or_blog_url': resume_instance.medium_or_blog_url, 'summary': resume_instance.summary, 'generated_summary': resume_instance.generated_summary, 'preferred_tech_stack': resume_instance.preferred_tech_stack, 'dev_environment': resume_instance.dev_environment, 'volunteering_experience': resume_instance.volunteering_experience, 'extracurriculars': resume_instance.extracurriculars, 'work_arrangement': resume_instance.work_arrangement, 'preferred_location': resume_instance.preferred_location, 'work_authorization': resume_instance.work_authorization, 'criminal_record_disclosure': resume_instance.criminal_record_disclosure, 'document_verification': resume_instance.document_verification, 'current_area': resume_instance.current_area, 'permanent_area': resume_instance.permanent_area, 'current_city': resume_instance.current_city, 'permanent_city': resume_instance.permanent_city, 'current_district': resume_instance.current_district, 'permanent_district': resume_instance.permanent_district, 'current_state': resume_instance.current_state, 'permanent_state': resume_instance.permanent_state, 'current_country': resume_instance.current_country, 'permanent_country': resume_instance.permanent_country, 'languages': resume_instance.languages, 'frameworks_tools': resume_instance.frameworks_tools, 'diploma_details': resume_instance.diploma_details, 'degree_details': resume_instance.degree_details, 'certification_details': resume_instance.certification_details, 'certification_photos': resume_instance.certification_photos, 'work_preferences': resume_instance.work_preferences, 'work_authorizations': resume_instance.work_authorizations, 'professional_links': resume_instance.professional_links, 'skills': self._safe_json_loads(resume_instance.skills, []), 'experience': self._safe_json_loads(resume_instance.experience, []), 'projects': self._safe_json_loads(resume_instance.projects, []), 'certifications': self._safe_json_loads(resume_instance.certifications, []), 'awards': self._safe_json_loads(resume_instance.awards, []), 'publications': self._safe_json_loads(resume_instance.publications, []), 'open_source_contributions': self._safe_json_loads(resume_instance.open_source_contributions, []), 'interests': self._safe_json_loads(resume_instance.interests, []), 'references': self._safe_json_loads(resume_instance.references, []), 'preferences': self._safe_json_loads(resume_instance.preferences, {}),
#             'education_details': {
#                 'tenth': {'board_name': resume_instance.tenth_board_name, 'school_name': resume_instance.tenth_school_name, 'year_passing': resume_instance.tenth_year_passing, 'score': resume_instance.tenth_score, 'result_upload_url': get_url(resume_instance.tenth_result_upload)},
#                 'twelfth': {'board_name': resume_instance.twelfth_board_name, 'college_name': resume_instance.twelfth_college_name, 'year_passing': resume_instance.twelfth_year_passing, 'score': resume_instance.twelfth_score, 'result_upload_url': get_url(resume_instance.twelfth_result_upload)},
#                 'diploma': {'course_name': resume_instance.diploma_course_name, 'institution_name': resume_instance.diploma_institution_name, 'year_passing': resume_instance.diploma_year_passing, 'score': resume_instance.diploma_score, 'result_upload_url': get_url(resume_instance.diploma_result_upload)},
#                 'degree': {'degree_name': resume_instance.degree_name, 'institution_name': resume_instance.degree_institution_name, 'specialization': resume_instance.degree_specialization, 'year_passing': resume_instance.degree_year_passing, 'score': resume_instance.degree_score, 'result_upload_url': get_url(resume_instance.degree_result_upload)}
#             },
#             'created_at': resume_instance.created_at.isoformat(), 'updated_at': resume_instance.updated_at.isoformat(),
#         }

#     def _update_resume_instance(self, resume, data, files):
#         """Updates the resume model instance from a dictionary of data."""
#         # Helper to safely get a value, converting None to "" for string-based fields
#         def get_safe_str(source_dict, key, default=""):
#             val = source_dict.get(key)
#             return val if val is not None else default

#         # Handle nested structures
#         personal_info = data.get(B, {})
#         if personal_info:
#             resume.name = get_safe_str(personal_info, L)
#             resume.email = get_safe_str(personal_info, M)
#             resume.phone = get_safe_str(personal_info, N)
#             for key in [S, T, U, V, 'current_area', 'permanent_area', 'current_city', 'permanent_city', 'current_district', 'permanent_district', 'current_state', 'permanent_state', 'current_country', 'permanent_country']:
#                 if key in personal_info:
#                     setattr(resume, key, get_safe_str(personal_info, key))

#         links = data.get(I, {})
#         if links:
#             resume.linkedin_url = get_safe_str(links, W)
#             resume.github_url = get_safe_str(links, X)
#             resume.portfolio_url = get_safe_str(links, Y)
#             resume.stackoverflow_url = get_safe_str(links, Z)
#             resume.medium_or_blog_url = get_safe_str(links, a)

#         # --- START OF THE FIX ---
#         # The original prefix-based logic was flawed. This explicit mapping is robust and correct.
#         education_details = data.get(A, {})
#         if education_details and isinstance(education_details, dict):
#             # Define an explicit map from JSON keys to model fields
#             edu_key_map = {
#                 'tenth': {
#                     'board_name': 'tenth_board_name', 'school_name': 'tenth_school_name',
#                     'year_passing': 'tenth_year_passing', 'score': 'tenth_score',
#                 },
#                 'twelfth': {
#                     'board_name': 'twelfth_board_name', 'college_name': 'twelfth_college_name',
#                     'year_passing': 'twelfth_year_passing', 'score': 'twelfth_score',
#                 },
#                 'diploma': {
#                     'course_name': 'diploma_course_name', 'institution_name': 'diploma_institution_name',
#                     'year_passing': 'diploma_year_passing', 'score': 'diploma_score',
#                 },
#                 'degree': {
#                     'degree_name': 'degree_name', 'institution_name': 'degree_institution_name',
#                     'specialization': 'degree_specialization', 'year_passing': 'degree_year_passing',
#                     'score': 'degree_score',
#                 }
#             }
#             # Iterate through the education levels provided in the request (e.g., 'tenth', 'twelfth')
#             for edu_level, details_dict in education_details.items():
#                 if edu_level in edu_key_map and isinstance(details_dict, dict):
#                     # For each detail (e.g., 'board_name'), find its model field and set the value
#                     for json_key, value in details_dict.items():
#                         model_field = edu_key_map[edu_level].get(json_key)
#                         if model_field and hasattr(resume, model_field):
#                             setattr(resume, model_field, value)
#         # --- END OF THE FIX ---

#         # Update remaining top-level fields (This part was already correct)
#         for field, value in data.items():
#             if field in [B, I, A]: continue 

#             if hasattr(resume, field):
#                 if field in ['skills', 'experience', 'projects', 'certifications', 'awards', 'publications', 'open_source_contributions', 'interests', 'references', 'preferences']:
#                     setattr(resume, field, json.dumps(value or []))
#                 elif field in ['languages', 'frameworks_tools', 'diploma_details', 'degree_details', 'certification_details', 'certification_photos', 'work_preferences', 'work_authorizations', 'professional_links']:
#                     if field == 'languages':
#                         setattr(resume, field, value or {})
#                     else:
#                         setattr(resume, field, value or [])
#                 else:
#                     setattr(resume, field, value if value is not None else "")

#         # Update files
#         for field, file_obj in files.items():
#             if hasattr(resume, field):
#                 setattr(resume, field, file_obj)

#         return resume

#     def _process_and_update_resume(self, request, user):
#         # This core logic method is correct and does not need changes.
#         # ... (code from previous answer is correct here) ...
#         resume, created = Resume.objects.get_or_create(talent_id=user, defaults={'is_deleted': False})
#         if resume.is_deleted:
#             resume.is_deleted = False

#         files = request.FILES
#         pdf_extracted_data = self.ai_pipeline.process_resume_data(files.get('resume_pdf'))
#         form_data = self._structure_form_data(request.data)

#         # For PATCH/PUT, we start with the data already in the database
#         if request.method in ['PATCH', 'PUT']:
#             base_data = self._serialize_resume_to_json(resume)
#         else: # For POST, we start with an empty slate
#             base_data = {}

#         # Merge order: existing data -> pdf data -> form data
#         merged_with_base = self._deep_update(base_data, pdf_extracted_data)
#         final_data = self._deep_update(merged_with_base, form_data)
        
#         self._update_resume_instance(resume, final_data, files)
#         resume.save()
#         return resume, created

#     # The GET, POST, PUT, PATCH, DELETE methods are all correct and 
#     # don't need changes. They rely on the fixed methods above.
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
#             return JsonResponse({'message': message, 'resume_id': resume.pk}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
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
# # --- AI ANALYSIS MODULES VIEWS (Unchanged, they are fine) ---
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
#                 return JsonResponse({'error': 'Resume file is missing from storage. Please re-upload.'}, status=status.HTTP_404_NOT_FOUND)

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

#             job_roles_on_portal = [
#                 "AI Engineer, NLP focus, PyTorch", "Senior Machine Learning Engineer (MLOps)",
#                 "Data Scientist with Deep Learning experience", "Research Engineer in Computer Vision"
#             ]

#             skill_gap_result = generate_skill_gap_analysis(resume_skills, job_roles_on_portal)
#             return JsonResponse(skill_gap_result, status=status.HTTP_200_OK)
#         except Resume.DoesNotExist:
#             return JsonResponse({'error': 'Resume profile not found for this user.'}, status=status.HTTP_404_NOT_FOUND)
#         except Exception as e:
#             return JsonResponse({'error': f'An internal server error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
#             experience_years = len(experience) * 1.5

#             roadmap_result = generate_career_roadmap(current_role, experience_years, interests, skills)
#             return JsonResponse(roadmap_result, status=status.HTTP_200_OK)
#         except Resume.DoesNotExist:
#             return JsonResponse({'error': 'Resume profile not found for this user.'}, status=status.HTTP_404_NOT_FOUND)
#         except Exception as e:
#             return JsonResponse({'error': f'An internal server error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# # ... your other views like TrendingSkillsListView ...
# from rest_framework import generics
# from .models import TrendingSkill
# from .serializers import TrendingSkillSerializer

# class TrendingSkillsListView(generics.ListAPIView):
#     queryset = TrendingSkill.objects.all()
#     serializer_class = TrendingSkillSerializer
#     permission_classes = [IsAuthenticated]

# from django.core.cache import cache  # <--- ADD THIS LINE
 
 
# from .ai_cultural_prep import generate_cultural_preparation

# from rest_framework.views import APIView, Response
# class CulturalPreparationAPIView(APIView):
#     """
#     Provides AI-generated cultural preparation insights for a fixed
#     set of countries (UAE, USA, EU, Singapore).
   
#     This view uses caching to avoid repeated, expensive API calls.
#     """
#     permission_classes = [IsAuthenticated]
 
#     def get(self, request, *args, **kwargs):
#         # Define a unique key for our cache
#         cache_key = 'cultural_preparation_insights'
       
#         # 1. First, try to get the data from the cache
#         cached_insights = cache.get(cache_key)
#         if cached_insights:
#             print("Serving cultural insights from CACHE.")
#             return Response(cached_insights, status=status.HTTP_200_OK)
 
#         # 2. If not in cache, call the AI service
#         print("Cache miss. Calling AI service for cultural insights...")
       
#         # --- Your hardcoded list of countries ---
#         countries = ["UAE", "USA", "EU", "Singapore"]
 
#         try:
#             insights = generate_cultural_preparation(countries)
           
#             if insights is None:
#                 return Response(
#                     {"error": "Failed to generate insights. The AI model may be unavailable."},
#                     status=status.HTTP_503_SERVICE_UNAVAILABLE
#                 )
           
#             # 3. Save the new data to the cache for 24 hours (86400 seconds)
#             cache.set(cache_key, insights, timeout=86400)
           
#             # 4. Return the successful response
#             return Response(insights, status=status.HTTP_200_OK)
 
#         except Exception as e:
#             return Response(
#                 {"error": f"An unexpected internal server error occurred: {str(e)}"},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )



