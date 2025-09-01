
# talent_management/views.py

_B = 'content'
_A = 'meta-llama/Meta-Llama-3-70B-Instruct'
import os, fitz, json, re, collections.abc
from django.http import JsonResponse
from django.conf import settings
from huggingface_hub import InferenceClient
from .models import Resume, CustomUser, MockInterviewResult
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.response import Response

# --- AI Analysis Service Imports ---
from .ai_analysis_services import (
    generate_multiple_roadmaps,
    generate_resume_review,
    extract_text_from_pdf_path,
    generate_skill_gap_analysis,
    generate_career_roadmap,
    generate_skill_gap_analysis_for_roles
)
# --- Other Serializer and Model imports from your original file ---
from .serializers import (
    CareerRoadmapRequestSerializer, MockInterviewResultSerializer, RoleListSerializer, SkillGapAnalysisRequestSerializer
)
from .interview_bot.llm_utils import call_llm_api
from .interview_bot.speech_utils import speak_text
from .interview_bot.config import MOCK_INTERVIEW_POSITION
from .interview_bot import config
from .interview_bot.timer_utils import RoundTimer
from .interview_bot.interviewer_logic import AIInterviewer
from django.utils import timezone
from groq import Groq
from django.core.cache import cache
from employer_management.models import JobPosting
from .ai_cultural_prep import generate_cultural_preparation, extract_unique_locations
from .ai_salary_insights import generate_salary_insights
import whisper
import tempfile

# Get the CustomUser model
User = get_user_model()

HFF_TOKEN = os.getenv('HFF_TOKEN')
if not HFF_TOKEN:
    raise ValueError('HuggingFace token not set in environment (HFF_TOKEN). Please set it to proceed.')

# --- UPDATED Constants for clarity (only used constants remain) ---
L = 'name'; M = 'email'; N = 'phone'; V = 'current_company'
J = 'error'; A = 'education_details'; B = 'personal_info'
F = 'tenth'; G = 'twelfth'


class ResumeAIPipeline:
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
        # --- CORRECTED: ALL curly braces inside the JSON example are now escaped with {{ and }} ---
        return f'''
You are an AI assistant that extracts structured information from resume text. Your goal is to parse the provided text and structure it into a specific JSON format.

Return your output in **strict JSON format only**. Do NOT include any markdown (e.g., ```json), conversational text, or explanations. If a section is not found, omit it or set its value to an empty list/object. The JSON structure must follow this schema:
{{{{
    "personal_info": {{{{ "name": "...", "email": "...", "phone": "...", "current_company": "..." }}}},
    "professional_links": [{{{{ "name": "LinkedIn", "url": "..." }}}}, {{{{ "name": "GitHub", "url": "..." }}}}, {{{{ "name": "Portfolio", "url": "..." }}}}],
    "summary": "A concise 3-4 sentence summary of the candidate's profile.",
    "skills": ["Skill 1", "Skill 2", "Programming Language"],
    "experience": [
        {{{{ "title": "Software Engineer", "company": "Tech Corp", "duration": "Jan 2022 - Present", "responsibilities": ["Developed feature X.", "Managed service Y."] }}}}
    ],
    "projects": [
        {{{{ "name": "Resume Parser", "description": "Built a tool using Python and LLMs.", "technologies": ["Python", "Django", "HuggingFace API"], "url": "..." }}}}
    ],
    "education_details": {{
        "tenth": {{{{ "board_name": "...", "school_name": "...", "year_passing": "...", "score": "..." }}}},
        "twelfth": {{{{ "board_name": "...", "college_name": "...", "year_passing": "...", "score": "..." }}}}
    }},
    "degree_details": [
        {{{{ "degree_name": "Bachelor of Engineering", "institution_name": "University of Technology", "specialization": "Computer Science", "year_passing": "2021", "score": "8.5 CGPA" }}}}
    ],
    "diploma_details": [
        {{{{ "course_name": "Diploma in IT", "institution_name": "Polytechnic College", "year_passing": "2018", "score": "92%" }}}}
    ],
     "post_graduate_details": [
        {{{{ "degree_name": "Master of Technology", "institution_name": "Advanced Institute of Science", "specialization": "Artificial Intelligence", "year_passing": "2023", "score": "9.1 CGPA" }}}}
    ],
    "certification_details": [
        {{{{ "name": "Certified Cloud Practitioner", "issuing_organization": "Amazon Web Services", "date_issued": "2023" }}}}
    ],
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
            raise e

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
        finally:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)

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
        structured_data = {k: v for k, v in data.items()}

        for field in list(structured_data.keys()):
            value = structured_data[field]
            if isinstance(value, str) and value.strip().startswith(('{', '[')):
                try:
                    structured_data[field] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass

        personal_info_keys = [L, M, N, V, 'current_area', 'permanent_area', 'current_city', 'permanent_city', 'current_district', 'permanent_district', 'current_state', 'permanent_state', 'current_country', 'permanent_country']
        personal_info_updates = {}
        for key in personal_info_keys:
            if key in structured_data:
                personal_info_updates[key] = structured_data.pop(key)
        
        if personal_info_updates:
            existing_pi = structured_data.get(B, {})
            structured_data[B] = {**existing_pi, **personal_info_updates}

        edu_map = {
            F: {'board_name': 'tenth_board_name', 'school_name': 'tenth_school_name', 'year_passing': 'tenth_year_passing', 'score': 'tenth_score'},
            G: {'board_name': 'twelfth_board_name', 'college_name': 'twelfth_college_name', 'year_passing': 'twelfth_year_passing', 'score': 'twelfth_score'},
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

        def transform_certifications(cert_list):
            if not cert_list:
                return []
            transformed = []
            for cert in cert_list:
                transformed.append({
                    **cert,
                    "photo_urls": [request.build_absolute_uri(settings.BASE_MEDIA_URL + path) if path else None
                                for path in cert.get("photo_urls", [])]
                })
            return transformed

        return {
            'id': resume_instance.pk, 
            'talent_id': resume_instance.talent_id.pk,
            'employee_level': resume_instance.employee_level,
            'is_fresher': resume_instance.is_fresher,
            'domain_interest': resume_instance.domain_interest,
            'name': resume_instance.name, 
            'email': resume_instance.email, 
            'phone': resume_instance.phone, 
            'current_company': resume_instance.current_company, 
            'profile_photo_url': get_url(resume_instance.profile_photo), 
            'resume_pdf_url': get_url(resume_instance.resume_pdf), 
            'professional_links': resume_instance.professional_links, 
            'summary': resume_instance.summary, 
            'generated_summary': resume_instance.generated_summary,
            'generated_preferences': resume_instance.generated_preferences,
            'preferred_tech_stack': resume_instance.preferred_tech_stack, 
            'dev_environment': resume_instance.dev_environment, 
            'volunteering_experience': resume_instance.volunteering_experience, 
            'extracurriculars': resume_instance.extracurriculars, 
            'preferred_location': resume_instance.preferred_location, 
            'work_authorizations': resume_instance.work_authorizations, 
            'work_preferences': resume_instance.work_preferences,
            'languages': resume_instance.languages, 
            'diploma_details': resume_instance.diploma_details, 
            'degree_details': resume_instance.degree_details, 
            'post_graduate_details': resume_instance.post_graduate_details,
            'certification_details': transform_certifications(resume_instance.certification_details), 
            'certification_photos': resume_instance.certification_photos, 
            'skills': self._safe_json_loads(resume_instance.skills, []), 
            'experience': self._safe_json_loads(resume_instance.experience, []), 
            'projects': self._safe_json_loads(resume_instance.projects, []), 
            'awards': self._safe_json_loads(resume_instance.awards, []), 
            'publications': self._safe_json_loads(resume_instance.publications, []), 
            'open_source_contributions': self._safe_json_loads(resume_instance.open_source_contributions, []), 
            'interests': self._safe_json_loads(resume_instance.interests, []), 
            'references': self._safe_json_loads(resume_instance.references, []),
            'current_area': resume_instance.current_area, 'permanent_area': resume_instance.permanent_area, 'current_city': resume_instance.current_city, 'permanent_city': resume_instance.permanent_city, 'current_district': resume_instance.current_district, 'permanent_district': resume_instance.permanent_district, 'current_state': resume_instance.current_state, 'permanent_state': resume_instance.permanent_state, 'current_country': resume_instance.current_country, 'permanent_country': resume_instance.permanent_country, 
            'education_details': {
                'tenth': {'board_name': resume_instance.tenth_board_name, 'school_name': resume_instance.tenth_school_name, 'year_passing': resume_instance.tenth_year_passing, 'score': resume_instance.tenth_score, 'result_upload_url': get_url(resume_instance.tenth_result_upload)},
                'twelfth': {'board_name': resume_instance.twelfth_board_name, 'college_name': resume_instance.twelfth_college_name, 'year_passing': resume_instance.twelfth_year_passing, 'score': resume_instance.twelfth_score, 'result_upload_url': get_url(resume_instance.twelfth_result_upload)},
            },
            'created_at': resume_instance.created_at.isoformat(), 
            'updated_at': resume_instance.updated_at.isoformat(),
        }

    def _update_resume_instance(self, resume, data, files):
        def get_safe_str(source_dict, key, default=""):
            val = source_dict.get(key)
            return val if val is not None else default

        personal_info = data.get(B, {})
        if personal_info:
            resume.name = get_safe_str(personal_info, L)
            resume.email = get_safe_str(personal_info, M)
            resume.phone = get_safe_str(personal_info, N)
            for key in [V, 'current_area', 'permanent_area', 'current_city', 'permanent_city', 'current_district', 'permanent_district', 'current_state', 'permanent_state', 'current_country', 'permanent_country']:
                if key in personal_info:
                    setattr(resume, key, get_safe_str(personal_info, key))

        education_details = data.get(A, {})
        if education_details and isinstance(education_details, dict):
            edu_key_map = {
                'tenth': { 'board_name': 'tenth_board_name', 'school_name': 'tenth_school_name', 'year_passing': 'tenth_year_passing', 'score': 'tenth_score' },
                'twelfth': { 'board_name': 'twelfth_board_name', 'college_name': 'twelfth_college_name', 'year_passing': 'twelfth_year_passing', 'score': 'twelfth_score' },
            }
            for edu_level, details_dict in education_details.items():
                if edu_level in edu_key_map and isinstance(details_dict, dict):
                    for json_key, value in details_dict.items():
                        model_field = edu_key_map[edu_level].get(json_key)
                        if model_field and hasattr(resume, model_field):
                            setattr(resume, model_field, value)
        
        SKIPPED_FIELDS = {B, A, 'id', 'talent_id', 'created_at', 'updated_at'}
        
        for field, value in data.items():
            if field in SKIPPED_FIELDS:
                continue 

            if hasattr(resume, field):
                if field in ['skills', 'experience', 'projects', 'awards', 'publications', 'open_source_contributions', 'interests', 'references']:
                    setattr(resume, field, json.dumps(value or []))
                elif field in ['languages', 'diploma_details', 'degree_details', 'certification_details', 'certification_photos', 'work_preferences', 'work_authorizations', 'professional_links','post_graduate_details']:
                    setattr(resume, field, value or ([] if field != 'languages' else {}))
                else:
                    setattr(resume, field, value if value is not None else "")
        
        for field, file_obj in files.items():
            if hasattr(resume, field):
                setattr(resume, field, file_obj)

        return resume

    def _process_and_update_resume(self, request, user):
        resume, created = Resume.objects.get_or_create(talent_id=user, defaults={'is_deleted': False})
        if resume.is_deleted:
            resume.is_deleted = False

        files = request.FILES
        pdf_extracted_data = self.ai_pipeline.process_resume_data(files.get('resume_pdf'))
        user_input_data = self._structure_form_data(request.data)

        base_data = {}
        if request.method == 'PATCH':
            base_data = self._serialize_resume_to_json(resume)

        merged_data = self._deep_update(base_data, pdf_extracted_data)
        final_data = self._deep_update(merged_data, user_input_data)
        
        self._update_resume_instance(resume, final_data, files)
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
            return JsonResponse({'error': f"An error occurred during delete: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser

from .models import ResumeDocument # Correct model import
from .serializers import ResumeDocumentSerializer # Correct serializer import

# ... (all other views)

# --- ADD THIS VIEW AT THE END OF THE FILE ---

class ResumeDocumentAPIView(APIView):
    """
    API endpoint for managing resume documents linked directly to a user.
    - GET /api/talent/resume-documents/: Lists all documents for the authenticated user.
    - POST /api/talent/resume-documents/: Uploads a new document for the user.
    - PATCH /api/talent/resume-documents/<id>/: Partially updates a specific document.
    - DELETE /api/talent/resume-documents/<id>/: Deletes a specific document.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def _get_object(self, pk, user):
        """Helper method to get the document and ensure ownership."""
        return get_object_or_404(ResumeDocument, pk=pk, talent=user)

    def get(self, request, pk=None):
        """
        Handles listing all documents for the authenticated user.
        """
        # The pk parameter is not used in the list view.
        documents = ResumeDocument.objects.filter(talent=request.user)
        serializer = ResumeDocumentSerializer(documents, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, pk=None):
        """
        Handles uploading a new document.
        """
        serializer = ResumeDocumentSerializer(data=request.data, context={'request': request})
        # The serializer will now handle the required field validation.
        serializer.is_valid(raise_exception=True) 
        serializer.save(talent=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def patch(self, request, pk=None):
        """
        Handles partially updating a specific document.
        Allows changing the 'document_type' or replacing the 'document_file'.
        """
        if not pk:
            return Response({'error': 'Document ID (pk) must be provided for an update.'}, status=status.HTTP_400_BAD_REQUEST)
        
        document = self._get_object(pk, request.user)
        
        # If a new file is uploaded, delete the old one first.
        if 'document_file' in request.FILES:
            document.document_file.delete(save=False)
            
        # Use partial=True to allow partial updates
        serializer = ResumeDocumentSerializer(document, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk=None):
        """
        Handles deleting a specific document identified by its primary key (pk).
        """
        if not pk:
            return Response({'error': 'Document ID (pk) must be provided.'}, status=status.HTTP_400_BAD_REQUEST)

        # The try/except is simplified as get_object_or_404 handles the 404 case.
        # DRF's default exception handler will catch other errors and return a 500.
        document = self._get_object(pk, request.user)
        
        # Delete the physical file from storage.
        document.document_file.delete(save=False)
        
        document.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)



from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.authentication import BasicAuthentication
from rest_framework.response import Response
from django.core.files.storage import default_storage
from django.conf import settings
import os, uuid


@api_view(['POST'])
@authentication_classes([])  # Disable default SessionAuthentication
@permission_classes([AllowAny])
def upload_certification_photo(request):
    if request.method == "POST" and request.FILES.get("photo"):
        photo = request.FILES["photo"]
        
        # Get file extension
        ext = os.path.splitext(photo.name)[1]
        
        # Generate unique filename
        filename = f"{uuid.uuid4().hex}{ext}"
        
        # Save file
        file_path = os.path.join("certifications", filename)
        saved_path = default_storage.save(file_path, photo)
        
        # Build file URL
        file_url = request.build_absolute_uri(settings.BASE_MEDIA_URL + saved_path)
        
        return JsonResponse({"url": saved_path})
    
    return JsonResponse({"error": "No photo uploaded"}, status=400)




class ResumeProgressAPIView(APIView):
    """
    Calculates and returns the completion progress of the authenticated user's resume.
    """
    permission_classes = [IsAuthenticated]

    def _safe_json_loads(self, json_string, default_value=None):
        """
        Safely loads a JSON string from a TextField. Returns a default
        value (e.g., an empty list) if the string is empty or invalid.
        """
        if default_value is None:
            default_value = []
        if not json_string:
            return default_value
        try:
            return json.loads(json_string)
        except (json.JSONDecodeError, TypeError):
            return default_value

    def get(self, request, *args, **kwargs):
        """
        Analyzes the user's resume and returns its completion percentage.
        """
        try:
            resume = Resume.objects.get(talent_id=request.user, is_deleted=False)
        except Resume.DoesNotExist:
            return Response({
                'progress_percentage': 0,
                'message': "You haven't started your resume yet. Let's get started!",
                'missing_sections': [
                    'Personal Info', 'Profile Photo', 'Resume PDF', 'Summary', 
                    'Skills', 'Experience', 'Education', 'Projects', 'Links'
                ]
            }, status=status.HTTP_200_OK)

        # --- Define the scoring rubric ---
        checklist = {
            'Personal Info': {'points': 15, 'check': lambda r: all([r.name, r.email, r.phone])},
            'Profile Photo': {'points': 10, 'check': lambda r: bool(r.profile_photo)},
            'Resume PDF':    {'points': 10, 'check': lambda r: bool(r.resume_pdf)},
            'Summary':       {'points': 10, 'check': lambda r: bool(r.summary)},
            'Skills':        {'points': 15, 'check': lambda r: bool(self._safe_json_loads(r.skills))},
            'Experience':    {'points': 15, 'check': lambda r: bool(self._safe_json_loads(r.experience))},
            'Education':     {'points': 10, 'check': lambda r: bool(r.degree_details)},
            'Projects':      {'points': 10, 'check': lambda r: bool(self._safe_json_loads(r.projects))},
            'Links':         {'points': 5,  'check': lambda r: bool(r.professional_links)},
        }

        achieved_points = 0
        total_possible_points = sum(item['points'] for item in checklist.values())
        missing_sections = []

        # --- Calculate the score ---
        for section_name, details in checklist.items():
            if details['check'](resume):
                achieved_points += details['points']
            else:
                missing_sections.append(section_name)

        # --- Calculate percentage and create a helpful message ---
        progress_percentage = 0
        if total_possible_points > 0:
            progress_percentage = int((achieved_points / total_possible_points) * 100)

        if progress_percentage == 100:
            message = "Congratulations! Your resume profile is complete and looks great."
        elif progress_percentage > 70:
            message = "You're almost there! Complete the remaining sections to stand out."
        elif progress_percentage > 30:
            message = "Great start! Keep filling out your profile to attract more opportunities."
        else:
            message = "Let's build a standout resume! Fill in the missing sections to get started."

        return Response({
            'progress_percentage': progress_percentage,
            'achieved_points': achieved_points,
            'total_possible_points': total_possible_points,
            'message': message,
            'missing_sections': missing_sections
        }, status=status.HTTP_200_OK)


    
# --------------------------------------------------------------------------
# --- AI ANALYSIS MODULES VIEWS (Unchanged, they are fine) ---
# --------------------------------------------------------------------------
from .serializers import ResumeReviewRequestSerializer
class ResumeReviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # 1. Validate the incoming request data
        serializer = ResumeReviewRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        target_roles = serializer.validated_data['target_roles']
        
        try:
            # 2. Fetch the user's resume data from the database
            resume = Resume.objects.get(talent_id=user, is_deleted=False)

            # Helper to safely load JSON from a TextField
            def safe_load_json(json_string, default_value=None):
                if default_value is None:
                    default_value = []
                if not json_string:
                    return default_value
                try:
                    return json.loads(json_string)
                except (json.JSONDecodeError, TypeError):
                    return default_value

            # 3. Construct the comprehensive profile text from the resume model
            summary = resume.summary or "No summary provided."
            skills_list = safe_load_json(resume.skills)
            experience_list = safe_load_json(resume.experience)
            projects_list = safe_load_json(resume.projects)
            degree_list = resume.degree_details or []

            # Build the text block once
            resume_profile_text = f"## Professional Summary\n{summary}\n\n"
            if skills_list:
                resume_profile_text += f"## Skills\n- {', '.join(skills_list)}\n\n"
            if experience_list:
                resume_profile_text += "## Work Experience\n"
                for exp in experience_list:
                    title = exp.get('title', 'N/A')
                    company = exp.get('company', 'N/A')
                    duration = exp.get('duration', 'N/A')
                    responsibilities = exp.get('responsibilities', [])
                    resp_str = " ".join(responsibilities) if isinstance(responsibilities, list) else str(responsibilities)
                    resume_profile_text += f"- **{title}** at {company} ({duration})\n  - {resp_str}\n"
                resume_profile_text += "\n"
            if projects_list:
                resume_profile_text += "## Projects\n"
                for proj in projects_list:
                    name = proj.get('name', 'N/A')
                    description = proj.get('description', 'N/A')
                    tech_list = proj.get('technologies', [])
                    tech_str = ', '.join(tech_list) if isinstance(tech_list, list) else str(tech_list)
                    resume_profile_text += f"- **{name}**: {description} (Technologies: {tech_str})\n"
                resume_profile_text += "\n"
            if degree_list:
                resume_profile_text += "## Education\n"
                for degree in degree_list:
                    degree_name = degree.get('degree_name', 'N/A')
                    institution = degree.get('institution_name', 'N/A')
                    year = degree.get('year_passing', 'N/A')
                    resume_profile_text += f"- {degree_name} from {institution}, passed in {year}\n"

            # 4. Generate a review for each target role
            all_reviews = {}
            for role in target_roles:
                # Call the AI service for the current role
                review_result = generate_resume_review(resume_profile_text.strip(), role)
                all_reviews[role] = review_result

            return Response(all_reviews, status=status.HTTP_200_OK)

        except Resume.DoesNotExist:
            return Response({'error': 'Resume profile not found for this user. Please create one first.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"Error in ResumeReviewAPIView: {e}")
            return Response({'error': f'An internal server error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class SkillGapAnalysisAPIView(APIView):
    def post(self, request):
        serializer = SkillGapAnalysisRequestSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            selected_roles = serializer.validated_data["selected_roles"]

            # 1. Fetch resume_skills from the user's resume in the DB
            try:
                resume = Resume.objects.get(talent_id=user)
                resume_skills = resume.skills  # Adjust this field as per your model
                # If skills are stored as a string, split to list if needed
                if isinstance(resume_skills, str):
                    resume_skills = [s.strip() for s in resume_skills.split(",") if s.strip()]
            except Resume.DoesNotExist:
                return Response({"error": "Resume not found for user."}, status=status.HTTP_404_NOT_FOUND)

            # 2. Build jobs_index for selected_roles from your job postings
            jobs_index = {
                    "AI/ML Engineer": [
                        "Machine Learning Engineer - model training, deployment, MLOps, AWS",
                        "AI Engineer - LLM fine-tuning, embeddings, retrieval systems",
                        "Applied ML Scientist - recommender systems, A/B testing",
                        "AI Research Engineer - GenAI, diffusion models, transformers",
                        "Computer Vision Engineer - YOLOv8, object detection, OpenCV",
                        "ML Infrastructure Engineer - model serving, monitoring, Kubernetes",
                        "AI Developer - LangChain, prompt engineering, vector databases"
                    ],
                    "Data Scientist": [
                        "Data Scientist - statistical modeling, data wrangling, Python, SQL",
                        "ML Data Scientist - XGBoost, SHAP values, model interpretability",
                        "Quantitative Analyst - forecasting, time series, optimization",
                        "NLP Data Scientist - sentiment analysis, transformer-based models",
                        "Product Data Scientist - funnel analysis, growth metrics, A/B testing",
                        "Marketing Analyst - churn prediction, cohort analysis, Tableau",
                        "Business Intelligence Scientist - KPI dashboards, storytelling with data"
                    ],
                    "Business Analyst": [
                        "Business Analyst - requirements gathering, Agile, stakeholder mapping",
                        "Product Analyst - metrics tracking, product strategy, SQL",
                        "BA - financial modeling, variance analysis, Excel dashboards",
                        "Operations Analyst - process optimization, Six Sigma, workflows",
                        "Strategy Analyst - competitive analysis, market research, KPIs",
                        "BA (Tech) - writing user stories, API specs, Jira, BPMN",
                        "Customer Insights Analyst - survey design, NPS, Excel/Power BI"
                    ]
                }
            jobs_index = {role: jobs_index[role] for role in selected_roles if role in jobs_index}

            # 3. Call the skill gap analysis function
            try:
                result = generate_skill_gap_analysis_for_roles(
                    resume_skills=resume_skills,
                    selected_roles=selected_roles,
                    jobs_index=jobs_index
                )
                return Response(result, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CareerRoadmapAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = CareerRoadmapRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        target_roles = serializer.validated_data['target_roles']

        try:
            resume = Resume.objects.get(talent_id=user, is_deleted=False)
            
            # Helper to safely load JSON from TextField
            def safe_load_json(json_string, default_value=None):
                if default_value is None:
                    default_value = []
                if not json_string:
                    return default_value
                try:
                    return json.loads(json_string)
                except (json.JSONDecodeError, TypeError):
                    return default_value if default_value is not None else []
            
            # --- Extract user data from the resume model ---
            experience = safe_load_json(resume.experience)
            interests_list = safe_load_json(resume.interests, ["Not specified"])
            
            current_role_str = "Fresher / Entry-level candidate"
            experience_years_num = 0

            if experience:
                # Use the most recent job title
                current_role_str = experience[0].get('title', 'Not specified')
                # A simple estimation of experience years
                experience_years_num = len(experience) * 1.5 
            
            interests_str = ", ".join(interests_list)

            # --- Call the AI service with the user's data ---
            roadmaps = generate_multiple_roadmaps(
                current_role=current_role_str,
                experience_years=experience_years_num,
                interests=interests_str,
                target_roles=target_roles
            )

            return Response(roadmaps, status=status.HTTP_200_OK)

        except Resume.DoesNotExist:
            return Response({'error': 'Resume profile not found. Please create one to generate a roadmap.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"Error in CareerRoadmapAPIView: {e}")
            return Response({'error': f'An internal server error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ... your other views like TrendingSkillsListView ...
from groq import Groq
client = Groq(api_key=getattr(settings, 'GROQ_API_KEY', None))
from django.core.cache import cache

def extract_json(text):
    if "```" in text:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            return match.group(1)
    start = text.find('{')
    end = text.rfind('}') + 1
    return text[start:end] if start != -1 and end != -1 else text


# class RecommendedSkillsView(APIView):
#     def post(self, request):
#         serializer = RoleListSerializer(data=request.data)
#         if not serializer.is_valid():
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#         selected_roles = serializer.validated_data['selected_roles']
#         cache_key = f"skills_cache_{'_'.join(sorted(selected_roles))}"

#         # Check cache
#         cached_result = cache.get(cache_key)
#         if cached_result:
#             return Response(cached_result, status=200)

#         # Build dynamic prompt
#         if len(selected_roles) == 1:
#             role = selected_roles[0]
#             prompt = (
#                     f"List 10 trending skills for each of the following roles: {roles}. "
#                     "For each skill, include the demand percentage, increase over last year (as +%), and priority (High/Medium). "
#                     "Return ONLY valid JSON as a response. Do NOT include markdown, explanations, or any extra text. "
#                     "The response must be a JSON object with role names as keys and arrays of 10 skill objects as values."
#                 )
#         else:
#             roles = ", ".join(selected_roles)
#             prompt = (
#                 f"List 10 trending skills for each of the following roles: {roles}. "
#                 "For each skill, include the demand percentage, increase over last year (as +%), and priority (High/Medium). "
#                 "Return the response as a JSON object with role names as keys and arrays of 10 skill objects as values. Like: "
#                 "{"
#                 "\"AI/ML Engineer\": [{\"skill\": \"MLOps\", \"demand\": \"95%\", \"increase\": \"+45%\", \"priority\": \"High Priority\"}, ...], "
#                 "\"Data Scientist\": [...], "
#                 "\"Business Analyst\": [...]"
#                 "}"
#             )

#         try:
#             response = client.chat.completions.create(
#                 model="llama3-8b-8192",
#                 messages=[{"role": "user", "content": prompt}]
#             )
#             raw_output = response.choices[0].message.content.strip()
#             cleaned_output = extract_json(raw_output)
#             if not cleaned_output:
#                 return Response({"error": "AI model did not return JSON."}, status=500)
#             parsed = json.loads(cleaned_output)
#             cache.set(cache_key, parsed, timeout=60 * 60)
#             return Response(parsed, status=200)
#         except json.JSONDecodeError as e:
#             return Response({"error": f"AI model returned invalid JSON: {raw_output}"}, status=500)
#         except Exception as e:
#             return Response({"error": str(e)}, status=500)

import os
import json
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
from .serializers import RoleListSerializer

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL_NAME = "gpt-4-turbo"


def extract_json(text):
    """Utility to extract JSON part safely from AI output."""
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return text[start:end]
    except ValueError:
        return None


class RecommendedSkillsView(APIView):
    def post(self, request):
        serializer = RoleListSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        selected_roles = serializer.validated_data['selected_roles']
        cache_key = f"skills_cache_{'_'.join(sorted(selected_roles))}"

        # Check cache
        cached_result = cache.get(cache_key)
        if cached_result:
            return Response(cached_result, status=200)

        # Build dynamic prompt
        role_list_str = ", ".join(selected_roles)
        
        # Define the desired JSON structure as an example in the prompt
        json_example = {
            "RoleName": [
                {"skill": "SkillName1", "demand": "XX%", "increase": "+YY%", "priority": "PriorityLevel"},
                {"skill": "SkillName2", "demand": "XX%", "increase": "+YY%", "priority": "PriorityLevel"}
                # ... up to 10 skills
            ]
        }
        
        prompt = (
            f"List exactly 10 trending skills for each of the following roles: {role_list_str}. "
            "For each skill, provide its 'skill' name, 'demand' percentage, "
            "'increase' over last year (as +%), and 'priority' (High/Medium). "
            "The response MUST be a valid JSON object. Do NOT include markdown, explanations, or any extra text outside the JSON. "
            "The JSON object must have role names as top-level keys. Each role key should map to an array of 10 skill objects. "
            "Each skill object must contain the keys: 'skill', 'demand', 'increase', and 'priority'. "
            f"Here is the exact JSON structure you must follow, replacing 'RoleName' and filling in the skill details: {json.dumps(json_example, indent=2)}"
        )
        # For the extract_json function, ensure it can handle cases where the model might still
        # include some conversational text before or after the JSON. A robust extract_json
        # would look for the first '{' and the last '}' to isolate the JSON.
        def extract_json(text):
            try:
                # Find the first occurrence of '{' and the last occurrence of '}'
                start = text.find('{')
                end = text.rfind('}')
                if start != -1 and end != -1 and end > start:
                    json_str = text[start : end + 1]
                    return json_str
                return None
            except Exception:
                return None

        try:
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": OPENAI_MODEL_NAME,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7
            }

            response = requests.post(OPENAI_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            raw_output = data["choices"][0]["message"]["content"].strip()
            cleaned_output = extract_json(raw_output)
            
            if not cleaned_output:
                return Response({"error": "AI model did not return valid JSON or JSON could not be extracted."}, status=500)

            parsed = json.loads(cleaned_output)
            cache.set(cache_key, parsed, timeout=60 * 60)
            return Response(parsed, status=200)

        except json.JSONDecodeError:
            return Response({"error": f"AI model returned invalid JSON: {raw_output}"}, status=500)
        except Exception as e:
            return Response({"error": str(e)}, status=500)


from django.core.cache import cache  # <--- ADD THIS LINE
 
from employer_management.models import JobPosting
from .ai_cultural_prep import generate_cultural_preparation, extract_unique_locations
class CulturalPreparationAPIView(APIView):
    """
    Provides AI-generated cultural preparation insights for ALL unique
    job locations stored in the database.

    This view fetches locations from the JobPosting model, generates insights
    for the unique set of those locations, and uses caching to avoid
    repeated, expensive API calls.
    """
    # permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # Define a single, static cache key for this system-wide data.
        cache_key = 'all_locations_cultural_insights'

        # 1. First, try to get the data from the cache
        cached_insights = cache.get(cache_key)
        if cached_insights:
            print("Serving all-location cultural insights from CACHE.")
            return Response(cached_insights, status=status.HTTP_200_OK)

        # 2. If not in cache, fetch unique locations from the JobPosting model
        print(f"Cache miss for '{cache_key}'. Fetching locations from database...")

        # Use the Django ORM to get a distinct list of non-empty locations
        # .values_list('location', flat=True) is efficient for getting a single column
        # .distinct() makes the database do the work of finding unique values
        db_locations = JobPosting.objects.values_list('location', flat=True).distinct()

        # The result from the DB is a QuerySet; clean it up.
        # The extract_unique_locations function is great for stripping whitespace and handling any oddities.
        unique_locations = extract_unique_locations(list(db_locations))

        if not unique_locations:
            # If there are no locations in the database yet, return an empty but successful response.
            return Response({"cultural_preparation": []}, status=status.HTTP_200_OK)

        # 3. Call the AI service with the list of unique locations
        print(f"Calling AI service for cultural insights on: {unique_locations}")

        try:
            insights = generate_cultural_preparation(unique_locations)

            if not insights:
                return Response(
                    {"error": "Failed to generate insights. The AI model may be unavailable or returned invalid data."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            # 4. Save the new data to the cache for 24 hours (86400 seconds)
            cache.set(cache_key, insights, timeout=86400)

            # 5. Return the successful response
            return Response(insights, status=status.HTTP_200_OK)

        except Exception as e:
            # General fallback for any unexpected errors
            return Response(
                {"error": f"An unexpected internal server error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



############################## vaishnavi's ai code integration #####################333


from .ai_salary_insights import generate_salary_insights
from rest_framework.response import Response # Use DRF's Response for APIViews
from django.core.cache import cache
import logging

class SalaryInsightsAPIView(APIView):
    """
    Provides AI-generated salary insights for key global tech hubs and roles.
    
    This view dynamically fetches locations from the JobPosting model and uses
    caching to minimize expensive API calls, returning fresh data once every 24 hours.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # 1. Fetch unique, non-empty locations from the JobPosting model
        # .values_list('location', flat=True) is efficient for getting a single column
        # .distinct() makes the database do the work of finding unique values
        db_locations = JobPosting.objects.exclude(location__isnull=True).exclude(location__exact='').values_list('location', flat=True).distinct()
        
        # The extract_unique_locations function is great for cleaning and deduplicating
        unique_locations = extract_unique_locations(list(db_locations))

        # Add a default list of locations in case the database has none yet
        if not unique_locations:
            unique_locations = ["USA", "UK", "Canada", "UAE", "Singapore", "Mumbai", "Banglore"]

        # 2. Define a dynamic cache key based on the sorted locations
        # This ensures that if the locations in the DB change, a new cache entry is created.
        sorted_locations_str = "_".join(sorted(unique_locations))
        cache_key = f'ai_salary_insights_{sorted_locations_str}'
        
        # 3. Try to get the data from the cache first
        cached_insights = cache.get(cache_key)
        if cached_insights:
            print(f"Serving salary insights from CACHE for key: {cache_key}")
            return Response(cached_insights, status=status.HTTP_200_OK)
            
        # 4. If not in cache, call the AI service
        print(f"Cache miss for '{cache_key}'. Calling AI service for new salary insights...")
        
        # Define the roles
        roles = ["AI Engineer", "Data Scientist", "Business Analyst"]

        try:
            # Pass the dynamically fetched locations to the service function
            insights = generate_salary_insights(roles, unique_locations)
            
            if insights is None:
                return Response(
                    {"error": "Failed to generate salary insights. The AI service may be down or returned invalid data."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
            
            # 5. Save the new data to the cache for 24 hours (86400 seconds)
            cache.set(cache_key, insights, timeout=86400)
            
            # 6. Return the successful response
            return Response(insights, status=status.HTTP_200_OK)

        except Exception as e:
            logging.error(f"An unexpected error occurred in SalaryInsightsAPIView: {str(e)}")
            return Response(
                {"error": f"An unexpected internal server error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )






################################ interview bot by RAHUL stage 1  ##########################

################################ interview bot by RAHUL stage 1  ##########################


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
from .serializers import MockInterviewResultSerializer, RoleListSerializer, SkillGapAnalysisRequestSerializer
MALPRACTICE_STATUS_FILE = "malpractice_status.txt"
IDENTITY_VERIFIED_FILE = "identity_verified.txt"
import json
import os # Make sure os is imported for your other functions

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
MOCK_INTERVIEW_POSITION = "AI Engineer"

def safe_json_loads(json_string, default_value=None):
    if not json_string:
        return default_value
    try:
        return json.loads(json_string)
    except (json.JSONDecodeError, TypeError):
        return default_value

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
            candidate_experience_summary = "Not specified"
            if resume.experience:
                exp_list = safe_json_loads(resume.experience, [])
                if exp_list:
                    num_experience_entries = len(exp_list)
                    exp_titles = [e.get('title', '') for e in exp_list if e.get('title')]
                    
                    if num_experience_entries > 0:
                        # A very rough estimate: assume each experience entry is ~2 years
                        # For more accuracy, you'd parse start_date/end_date from each entry
                        estimated_years = num_experience_entries * 2 
                        candidate_experience_summary = f"{estimated_years} years (estimated from {num_experience_entries} roles)" 
                        if exp_titles:
                            candidate_experience_summary += f" including roles like: {', '.join(exp_titles[:3])}" # Limit to first 3 roles
                    elif exp_titles: # If no explicit number of entries, but titles exist
                        candidate_experience_summary = f"Roles: {', '.join(exp_titles[:3])}"
            
            candidate_experience = candidate_experience_summary
            # --- END MODIFIED SECTION ---
            
            # Extract AIML specialization from skills, or leave as None
            # This logic is crucial for populating the new aiml_specialization JSONField
            aiml_specialization_input_str = None # This will go to the CharField
            detected_aiml_specializations_list = [] # This will go to the JSONField

            if resume.skills:
                skills_list = safe_json_loads(resume.skills, [])
                # Simple heuristic: look for common AIML-related skills
                aiml_keywords = ["machine learning", "deep learning", "nlp", "natural language processing", "computer vision", "ai", "artificial intelligence", "data science"]
                
                # Filter for skills that match keywords
                found_aiml_skills = [s for s in skills_list if any(keyword in s.lower() for keyword in aiml_keywords)]
                
                if found_aiml_skills:
                    # For the aiml_specialization_input (CharField), pick the first relevant skill
                    # aiml_specialization_input_str = found_aiml_skills
                    aiml_specialization_input_str = ", ".join(found_aiml_skills)

                    # For the new aiml_specialization (JSONField), store all found skills
                    detected_aiml_specializations_list = list(set(found_aiml_skills)) # Use set to remove duplicates
                else:
                    # If no specific AIML skills, default to a general AI/ML specialization if position is AI Engineer
                    if "ai engineer" in MOCK_INTERVIEW_POSITION.lower():
                        aiml_specialization_input_str =  ", ".join(found_aiml_skills)
                        # detected_aiml_specializations_list = ["Machine Learning Engineering"]
                        detected_aiml_specializations_list = detected_aiml_specializations_list

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
            position_applied=MOCK_INTERVIEW_POSITION,
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
                position=MOCK_INTERVIEW_POSITION,
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
            interview_start_message = interviewer.all_generated_questions["interview_start_message_template"].format(position=MOCK_INTERVIEW_POSITION)
            
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


# class MalpracticeDetectionView(APIView):
#     permission_classes = [IsAuthenticated] # Only authenticated users can trigger this

#     def post(self, request, *args, **kwargs):
#         """
#         Terminates the current in-progress mock interview due to detected malpractice.
#         Expects 'type_of_malpractice' in the request body.
#         """
#         type_of_malpractice = request.data.get('type_of_malpractice')
#         # We will use the current time for interview_end_time.
#         # If 'time_of_malpractice' needs to be a separate, specific timestamp from the client,
#         # you'll need to add a field to MockInterviewResult model and process it here.

#         if not type_of_malpractice:
#             return Response(
#                 {"error": "Missing 'type_of_malpractice' in request body."},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         # Get the ID of the current interview from the session
#         current_mock_interview_id = request.session.get('current_mock_interview_id')

#         if not current_mock_interview_id:
#             return Response(
#                 {"error": "No active interview found for this user in the session."},
#                 status=status.HTTP_404_NOT_FOUND
#             )

#         try:
#             # Retrieve the in-progress interview for the current user
#             mock_interview = MockInterviewResult.objects.get(
#                 id=current_mock_interview_id,
#                 user=request.user, # Ensure the interview belongs to the authenticated user
#                 status=MockInterviewResult.InterviewStatus.IN_PROGRESS # Only terminate if it's currently in progress
#             )

#             # Update the interview status for malpractice
#             mock_interview.malpractice_detected = True
#             mock_interview.malpractice_reason = f"Malpractice detected: {type_of_malpractice}"
#             mock_interview.status = MockInterviewResult.InterviewStatus.TERMINATED_MALPRACTICE
#             mock_interview.interview_end_time = timezone.now() # Set the end time
#             mock_interview.save()

#             # Clear session data to prevent further interaction with this interview
#             request.session.pop('current_mock_interview_id', None)
#             request.session.pop('current_round_name', None)
#             request.session.pop('current_question_index', None)
#             request.session.modified = True # Mark session as modified to ensure changes are saved

#             # Clean up any associated proctoring files
#             cleanup_proctor_files_api_context()

#             return Response(
#                 {
#                     "message": "Interview terminated due to malpractice.",
#                     "interview_id": mock_interview.id,
#                     "malpractice_reason": mock_interview.malpractice_reason,
#                     "status": mock_interview.status
#                 },
#                 status=status.HTTP_200_OK
#             )

#         except MockInterviewResult.DoesNotExist:
#             return Response(
#                 {"error": "No active interview found with the provided ID for this user, or interview is not in progress."},
#                 status=status.HTTP_404_NOT_FOUND
#             )
#         except Exception as e:
#             print(f"Error terminating interview due to malpractice: {e}")
#             return Response(
#                 {"error": f"An internal error occurred while terminating the interview: {e}"},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )

from .services import BeaconTokenAuthentication
 
 
class MalpracticeDetectionView(APIView):
    # ===================================================================
    # ========== 2. SET THE AUTHENTICATION CLASS FOR THIS VIEW ==========
    # ===================================================================
    authentication_classes = [BeaconTokenAuthentication]
    permission_classes = [IsAuthenticated] # This can now succeed
 
    def post(self, request, *args, **kwargs):
        """
        Terminates the current in-progress mock interview due to detected malpractice.
        Expects 'type_of_malpractice' in the request body.
        """
        # ... your existing logic here, NO CHANGES NEEDED ...
        type_of_malpractice = request.data.get('type_of_malpractice')
 
        if not type_of_malpractice:
            return Response(
                {"error": "Missing 'type_of_malpractice' in request body."},
                status=status.HTTP_400_BAD_REQUEST
            )
 
        current_mock_interview_id = request.session.get('current_mock_interview_id')
 
        if not current_mock_interview_id:
            return Response(
                {"error": "No active interview found for this user in the session."},
                status=status.HTTP_404_NOT_FOUND
            )
 
        try:
            mock_interview = MockInterviewResult.objects.get(
                id=current_mock_interview_id,
                user=request.user,
                status=MockInterviewResult.InterviewStatus.IN_PROGRESS
            )
 
            mock_interview.malpractice_detected = True
            mock_interview.malpractice_reason = f"Malpractice detected: {type_of_malpractice}"
            mock_interview.status = MockInterviewResult.InterviewStatus.TERMINATED_MALPRACTICE
            mock_interview.interview_end_time = timezone.now()
            mock_interview.save()
 
            request.session.pop('current_mock_interview_id', None)
            request.session.pop('current_round_name', None)
            request.session.pop('current_question_index', None)
            request.session.modified = True
 
            # cleanup_proctor_files_api_context()
 
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
        

class MockInterviewReportListView(APIView):
    """
    API endpoint to retrieve a list of all mock interview report IDs 
    for the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        """
        Returns a JSON list of all mock interview result IDs associated with the 
        logged-in user, ordered by most recent first.
        """
        user = request.user
        try:
            # Filter MockInterviewResult objects by the current user,
            # order by most recent creation date, and efficiently fetch only the 'id' field.
            report_ids = MockInterviewResult.objects.filter(user=user).order_by('-created_at').values_list('id', flat=True)
            
            # Convert the QuerySet of IDs to a simple list and return it in the response.
            # Example response: [15, 12, 5]
            return Response(list(report_ids), status=status.HTTP_200_OK)
        except Exception as e:
            # Log the error for debugging purposes
            print(f"Error fetching mock interview report list for user {user.username}: {e}")
            return Response(
                {"error": "An error occurred while fetching your interview report history."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



#################### speach to text model ################# 
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
import whisper
import tempfile
import os
 
# Load Whisper model ONCE globally
model = whisper.load_model("base")  # You can also try "base" if accuracy needed
 
class AudioTranscriptionView(APIView):
    parser_classes = (MultiPartParser, FormParser)
 
    def post(self, request, *args, **kwargs):
        audio_file = request.FILES.get("audio")
        if not audio_file:
            return Response({"error": "No audio file provided."}, status=status.HTTP_400_BAD_REQUEST)
 
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            for chunk in audio_file.chunks():
                temp_audio.write(chunk)
            temp_path = temp_audio.name
 
        try:
            # Transcribe using Whisper (remove vad_filter)
            result = model.transcribe(temp_path, fp16=False)  # Only fp16=False needed for CPU
            transcription = result.get("text", "")
 
            return Response({"transcription": transcription}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)



from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
import tempfile
import os
 
from .models import Resume  # Adjust to your model name
from interview_system.interview_cam import run_full_interview_photo_check
 
 
class FullInterviewPhotoCheckAPIView(APIView):
    """
    API to run full AI interview image check.
    Uses resume photo from DB and captured image from request.
    Tracks malpractice_count in session.
    """
    permission_classes = [IsAuthenticated]
 
    def post(self, request):
        try:
            # 1️⃣ Malpractice count from session
            malpractice_count = request.session.get("malpractice_count", 0)
 
            # 2️⃣ Get reference resume photo path from DB
            try:
                resume = Resume.objects.get(talent_id=request.user)
            except Resume.DoesNotExist:
                return Response(
                    {"error": "Resume not found for this user."},
                    status=status.HTTP_404_NOT_FOUND
                )
            if not resume.profile_photo:  # Change field if different
                return Response(
                    {"error": "No reference photo found in DB."},
                    status=status.HTTP_404_NOT_FOUND
                )
            resume_photo_path = resume.profile_photo.path
 
            # 3️⃣ Get uploaded captured photo
            captured_file = request.FILES.get("captured")
            if not captured_file:
                return Response(
                    {"error": "No interview photo uploaded (key: 'captured')."},
                    status=status.HTTP_400_BAD_REQUEST
                )
 
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_captured:
                for chunk in captured_file.chunks():
                    temp_captured.write(chunk)
                interview_photo_path = temp_captured.name
            
            # 4️⃣ Run AI check
            print(resume_photo_path) 
            print(interview_photo_path)
            result = run_full_interview_photo_check(resume_photo_path, interview_photo_path)
 
            # 5️⃣ Update malpractice_count if any fail
            if not result.get("match", True) \
               or not result.get("orientation_ok", True) \
               or result.get("multiple_faces", False) \
               or result.get("malpractice", False):
                malpractice_count += 1
                request.session["malpractice_count"] = malpractice_count
                request.session.modified = True
 
            # 6️⃣ Cleanup
            if os.path.exists(interview_photo_path):
                os.remove(interview_photo_path)
 
            # 7️⃣ Append count to result
            result["malpractice_count"] = malpractice_count
 
            return Response(result, status=status.HTTP_200_OK)
 
        except Exception as e:
            return Response(
                {"error": f"Internal server error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# class FullInterviewPhotoCheckAPIView(APIView):
#     """
#     API to run full AI interview image check.
#     Uses resume photo from DB and captured image from request.
#     Tracks malpractice_count in session.
#     """
#     permission_classes = [IsAuthenticated]
 
#     def post(self, request):
#         try:
#             # 1️⃣ Malpractice count from session
#             malpractice_count = request.session.get("malpractice_count", 0)
 
#             # 2️⃣ Get reference resume photo path from DB
#             try:
#                 resume = Resume.objects.get(talent_id=request.user)
#             except Resume.DoesNotExist:
#                 return Response(
#                     {"error": "Resume not found for this user."},
#                     status=status.status.HTTP_404_NOT_FOUND
#                 )
#             if not resume.profile_photo:
#                 return Response(
#                     {"error": "No reference photo found in DB."},
#                     status=status.status.HTTP_404_NOT_FOUND
#                 )
#             resume_photo_path = resume.profile_photo.path
 
#             # 3️⃣ Get uploaded captured photo
#             captured_file = request.FILES.get("captured")
#             if not captured_file:
#                 return Response(
#                     {"error": "No interview photo uploaded (key: 'captured')."},
#                     status=status.status.HTTP_400_BAD_REQUEST
#                 )
 
#             with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_captured:
#                 for chunk in captured_file.chunks():
#                     temp_captured.write(chunk)
#                 interview_photo_path = temp_captured.name
            
#             # 4️⃣ Run AI check
#             result = run_full_interview_photo_check(resume_photo_path, interview_photo_path)
 
#             # 5️⃣ Update malpractice_count if any fail
#             #    ✅ CHANGE HERE: We now use the single 'success' flag from the new model's response.
#             #    This is cleaner and more robust. If the AI model adds new checks in the future,
#             #    this API code won't need to change as long as the 'success' flag is updated correctly.
#             if not result.get("success", False):
#                 malpractice_count += 1
#                 request.session["malpractice_count"] = malpractice_count
#                 request.session.modified = True
 
#             # 6️⃣ Cleanup
#             if os.path.exists(interview_photo_path):
#                 os.remove(interview_photo_path)
 
#             # 7️⃣ Append count to result
#             result["malpractice_count"] = malpractice_count
 
#             # Handle cases where the AI check itself fails (e.g., file not found)
#             if not result.get("success", False) and "message" in result:
#                  # You can decide if an early exit error from the AI module should be a 400 or 200
#                  # A 200 is fine as the API itself worked, but the check failed.
#                  return Response(result, status=status.HTTP_200_OK)

#             return Response(result, status=status.HTTP_200_OK)
 
#         except Exception as e:
#             # It's good practice to also clean up the temp file in case of an exception
#             if 'interview_photo_path' in locals() and os.path.exists(interview_photo_path):
#                 os.remove(interview_photo_path)
                
#             return Response(
#                 {"error": f"Internal server error: {str(e)}"},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )











# from rest_framework.views import APIView
# from rest_framework.response import Response
# from rest_framework.permissions import IsAuthenticated
# from rest_framework import status
# from .models import Resume, CustomUser, MockInterviewResult, SkillsPassport
# from .serializers import MockInterviewResultSerializer, FullResumeSerializer, SkillsPassportSerializer
# from .ai_passport_generator import generate_skills_passport_data

# # ... (all your other views) ...

# class SkillsPassportView(APIView):
#     """
#     API for generating and retrieving a user's Skills Passport.
#     - POST: Generates a new passport based on the latest completed interview.
#             If a failed/pending passport exists, it will be deleted to allow a retry.
#     - GET:  Retrieves the latest successfully completed passport.
#     """
#     permission_classes = [IsAuthenticated]

#     def get(self, request, *args, **kwargs):
#         """
#         Retrieves the latest successfully COMPLETED Skills Passport for the authenticated user.
#         """
#         passport = SkillsPassport.objects.filter(
#             user=request.user,
#             status=SkillsPassport.PassportStatus.COMPLETED
#         ).order_by('-created_at').first()

#         if not passport:
#             return Response(
#                 {"error": "No completed Skills Passport found. Please complete a mock interview and generate one."},
#                 status=status.HTTP_404_NOT_FOUND
#             )
            
#         serializer = SkillsPassportSerializer(passport)
#         return Response(serializer.data, status=status.HTTP_200_OK)

#     def post(self, request, *args, **kwargs):
#         """
#         Generates a new Skills Passport. If a previously failed or pending passport exists
#         for the latest interview, it will be deleted and a new attempt will be made.
#         """
#         user = request.user
        
#         # 1. Find the latest completed mock interview for the user
#         latest_interview = MockInterviewResult.objects.filter(
#             user=user,
#             status=MockInterviewResult.InterviewStatus.COMPLETED
#         ).order_by('-created_at').first()

#         if not latest_interview:
#             return Response({"error": "No completed mock interview found to generate a passport from."}, status=status.HTTP_404_NOT_FOUND)

#         # 2. Check for an existing passport for this specific interview to handle retries
#         existing_passport = SkillsPassport.objects.filter(source_interview=latest_interview).first()

#         if existing_passport:
#             # If it's already successfully completed, prevent re-generation.
#             if existing_passport.status == SkillsPassport.PassportStatus.COMPLETED:
#                 return Response({
#                     "message": "A completed Skills Passport for this interview already exists. Use the GET endpoint to retrieve it."
#                 }, status=status.HTTP_409_CONFLICT)
            
#             # If it's stuck in a FAILED or PENDING state, delete it to allow a clean retry.
#             else:
#                 print(f"Deleting stale passport (ID: {existing_passport.id}, Status: {existing_passport.status}) to retry generation.")
#                 existing_passport.delete()
        
#         # 3. Fetch the user's resume (required for generation)
#         try:
#             resume = Resume.objects.get(talent_id=user)
#         except Resume.DoesNotExist:
#             return Response({"error": "Resume not found. A resume is required to generate a passport."}, status=status.HTTP_404_NOT_FOUND)

#         # 4. Create a new placeholder passport entry with PENDING status
#         # This is wrapped in the main try/except block to handle any potential errors.
#         passport = None
#         try:
#             passport = SkillsPassport.objects.create(
#                 user=user,
#                 source_interview=latest_interview,
#                 status=SkillsPassport.PassportStatus.PENDING
#             )

#             # 5. Begin the AI generation process
#             # (For production, this block should be in a background task e.g., Celery)
            
#             # Serialize the source data for the AI prompt
#             interview_serializer = MockInterviewResultSerializer(latest_interview)
#             # Pass the request context to the resume serializer to build full URLs
#             resume_serializer = FullResumeSerializer(resume, context={'request': request})
            
#             # Call the AI generation service
#             ai_generated_data = generate_skills_passport_data(
#                 interview_report_json=interview_serializer.data,
#                 resume_json=resume_serializer.data
#             )

#             if not ai_generated_data:
#                 # If AI fails, update status to FAILED and return an error
#                 passport.status = SkillsPassport.PassportStatus.FAILED
#                 passport.save()
#                 return Response({"error": "AI failed to generate passport data. Please try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#             # 6. Assemble all data and save to the passport object
#             # - Get scores from the interview report
#             passport.communication_skills_score = latest_interview.communication_overall_score
#             tech_scores = list(latest_interview.technical_specialization_scores.values())
#             passport.technical_readiness_score = int(sum(tech_scores) / len(tech_scores)) if tech_scores else 0
#             passport.specialization_scores = latest_interview.technical_specialization_scores

#             # - Get data from the AI
#             passport.relocation_score = ai_generated_data.get('relocation_score', 0)
#             passport.cultural_adaptability_score = ai_generated_data.get('cultural_adaptability_score', 0)
#             passport.ai_powered_summary = ai_generated_data.get('ai_powered_summary', '')
#             passport.key_strengths = ai_generated_data.get('key_strengths', [])
#             passport.frameworks_tools = ai_generated_data.get('frameworks_tools', [])

#             # - Calculate the final Global Readiness Score
#             total_score = (
#                 passport.relocation_score +
#                 passport.cultural_adaptability_score +
#                 passport.communication_skills_score +
#                 passport.technical_readiness_score
#             )
#             # Avoid division by zero if all scores are 0
#             passport.global_readiness_score = int(total_score / 4) if total_score > 0 else 0
            
#             # 7. Finalize the passport
#             passport.status = SkillsPassport.PassportStatus.COMPLETED
#             passport.save()

#             # Return the newly created passport data
#             final_serializer = SkillsPassportSerializer(passport)
#             return Response(final_serializer.data, status=status.HTTP_201_CREATED)

#         except Exception as e:
#             # If any unexpected error occurs during generation, mark as FAILED
#             # This check ensures we don't try to save a passport that failed to be created
#             if passport:
#                 passport.status = SkillsPassport.PassportStatus.FAILED
#                 passport.save()
#             print(f"Error during passport generation: {e}")
#             return Response({"error": f"An unexpected error occurred during passport generation: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



# talent_management/views.py

# ... (ensure these imports are at the top of your views.py file)
import json
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .models import Resume, MockInterviewResult, SkillsPassport
from .serializers import MockInterviewResultSerializer, FullResumeSerializer, SkillsPassportSerializer
from .ai_passport_generator import generate_skills_passport_data

# ... (all your other views, like ResumeBuilderAPIView, etc.) ...


class SkillsPassportView(APIView):
    """
    API for generating and retrieving a user's Skills Passport.
    - POST: Generates a new passport by having an AI analyze the latest completed interview transcript and resume.
            If a failed/pending passport exists for that interview, it will be deleted to allow a retry.
    - GET:  Retrieves the latest successfully completed passport.
    """
    permission_classes = [IsAuthenticated]

    def _safe_json_loads(self, data, default_value=None):
        """Safely parse a JSON string, returning a default value on failure."""
        if default_value is None:
            default_value = []
        if isinstance(data, (list, dict)): # If it's already parsed, return it
            return data
        if not isinstance(data, str) or not data.strip():
            return default_value
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return default_value

    def _get_location_from_resume(self, resume):
        """Constructs a location string from a resume object."""
        if resume:
            city = resume.current_city
            country = resume.current_country
            if city and country:
                return f"{city}, {country}"
            return city or country or "Not Specified"
        return "Not Specified"

    def get(self, request, *args, **kwargs):
        """
        Retrieves the latest successfully COMPLETED Skills Passport for the authenticated user.
        """
        passport = SkillsPassport.objects.filter(
            user=request.user,
            status=SkillsPassport.PassportStatus.COMPLETED
        ).order_by('-created_at').first()

        if not passport:
            return Response(
                {"error": "No completed Skills Passport found. Please complete a mock interview and generate one."},
                status=status.HTTP_404_NOT_FOUND
            )
            
        serializer = SkillsPassportSerializer(passport, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        """
        Generates a new Skills Passport. This process involves a comprehensive AI analysis
        of the user's latest interview transcript and resume data.
        """
        user = request.user
        
        # 1. Find the latest completed mock interview for the user
        latest_interview = MockInterviewResult.objects.filter(
            user=user,
            status=MockInterviewResult.InterviewStatus.COMPLETED
        ).order_by('-created_at').first()

        if not latest_interview:
            return Response({"error": "No completed mock interview found to generate a passport from."}, status=status.HTTP_404_NOT_FOUND)

        # 2. Check for an existing passport for this specific interview to handle retries
        existing_passport = SkillsPassport.objects.filter(source_interview=latest_interview).first()

        if existing_passport:
            if existing_passport.status == SkillsPassport.PassportStatus.COMPLETED:
                return Response({
                    "message": "A completed Skills Passport for this interview already exists. Use the GET endpoint to retrieve it."
                }, status=status.HTTP_409_CONFLICT)
            else:
                # If stuck in FAILED or PENDING, delete to allow a clean retry.
                print(f"Deleting stale passport (ID: {existing_passport.id}, Status: {existing_passport.status}) to retry generation.")
                existing_passport.delete()
        
        # 3. Fetch the user's resume
        try:
            resume = Resume.objects.get(talent_id=user)
        except Resume.DoesNotExist:
            return Response({"error": "Resume not found. A resume is required to generate a passport."}, status=status.HTTP_404_NOT_FOUND)

        # 4. Create a placeholder passport entry with PENDING status
        passport = None
        try:
            passport = SkillsPassport.objects.create(
                user=user,
                source_interview=latest_interview,
                status=SkillsPassport.PassportStatus.PENDING
            )

            # 5. Prepare data for the AI prompt
            # We serialize the objects to get a consistent dictionary format.
            interview_serializer = MockInterviewResultSerializer(latest_interview)
            resume_serializer = FullResumeSerializer(resume, context={'request': request})
            
            interview_data = interview_serializer.data
            resume_data = resume_serializer.data

            # Clean and prepare the resume data, ensuring JSON strings are parsed
            resume_data['skills'] = self._safe_json_loads(resume_data.get('skills'), [])
            resume_data['projects'] = self._safe_json_loads(resume_data.get('projects'), [])
            resume_data['verified_certifications'] = self._safe_json_loads(resume.certification_details, [])
            resume_data['location'] = self._get_location_from_resume(resume)

            # Call the AI generation service with the prepared data
            ai_generated_data = generate_skills_passport_data(
                interview_report_json=interview_data,
                resume_json=resume_data
            )

            if not ai_generated_data:
                passport.status = SkillsPassport.PassportStatus.FAILED
                passport.save()
                return Response({"error": "AI failed to generate passport data. Please try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # 6. Assemble all data and save to the passport object
            # --- USE AI-GENERATED SCORES INSTEAD OF DIRECT COPY ---
            passport.communication_skills_score = ai_generated_data.get('communication_skills_score', 0)
            passport.technical_readiness_score = ai_generated_data.get('technical_readiness_score', 0)
            
            # Specialization scores can still come from the interview if available, as they are granular.
            passport.specialization_scores = latest_interview.technical_specialization_scores

            # --- Get the rest of the data from the AI analysis ---
            passport.relocation_score = ai_generated_data.get('relocation_score', 0)
            passport.cultural_adaptability_score = ai_generated_data.get('cultural_adaptability_score', 0)
            passport.ai_powered_summary = ai_generated_data.get('ai_powered_summary', '')
            passport.key_strengths = ai_generated_data.get('key_strengths', [])
            passport.frameworks_tools = ai_generated_data.get('frameworks_tools', [])
            passport.rated_certifications = ai_generated_data.get('rated_certifications', [])

            # --- Calculate the final Global Readiness Score using the NEW AI-generated scores ---
            total_score = (
                passport.relocation_score +
                passport.cultural_adaptability_score +
                passport.communication_skills_score +
                passport.technical_readiness_score
            )
            passport.global_readiness_score = int(total_score / 4) if total_score > 0 else 0
            
            # 7. Finalize the passport
            passport.status = SkillsPassport.PassportStatus.COMPLETED
            passport.save()

            final_serializer = SkillsPassportSerializer(passport, context={'request': request})
            return Response(final_serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            # If any error occurs, mark the passport as FAILED
            if passport:
                passport.status = SkillsPassport.PassportStatus.FAILED
                passport.save()
            print(f"Error during passport generation: {e}")
            return Response({"error": f"An unexpected error occurred during passport generation: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)