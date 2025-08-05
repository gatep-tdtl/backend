

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
    generate_career_roadmap,
    generate_skill_gap_analysis_for_roles
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
            return JsonResponse({'error': f"An error occurred during delete: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
    def _safe_json_loads(self, data, default=None):
        """
        Safely loads a JSON string.
        Returns the default value if the data is None, empty, or not valid JSON.
        """
        # If the data from the DB is already a Python object (e.g., from a JSONField),
        # no need to parse it.
        if isinstance(data, (list, dict)):
            return data
            
        if data is None or data == '':
            return default if default is not None else []
        
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            # Return the default value if parsing fails
            return default if default is not None else []
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
        if len(selected_roles) == 1:
            role = selected_roles[0]
            prompt = (
                f"List 10 trending skills in {role}. For each skill, give the demand percentage, "
                "increase over last year (as +%), and priority (High/Medium). "
                "Return the response as a JSON array like: "
                "[{\"skill\": \"MLOps\", \"demand\": \"95%\", \"increase\": \"+45%\", \"priority\": \"High Priority\"}, ...]"
            )
        else:
            roles = ", ".join(selected_roles)
            prompt = (
                f"List 10 trending skills for each of the following roles: {roles}. "
                "For each skill, include the demand percentage, increase over last year (as +%), and priority (High/Medium). "
                "Return the response as a JSON object with role names as keys and arrays of 10 skill objects as values. Like: "
                "{"
                "\"AI/ML Engineer\": [{\"skill\": \"MLOps\", \"demand\": \"95%\", \"increase\": \"+45%\", \"priority\": \"High Priority\"}, ...], "
                "\"Data Scientist\": [...], "
                "\"Business Analyst\": [...]"
                "}"
            )

        try:
            response = client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "user", "content": prompt}]
            )
            raw_output = response.choices[0].message.content.strip()
            cleaned_output = extract_json(raw_output)
            parsed = json.loads(cleaned_output)

            # Save to cache
            cache.set(cache_key, parsed, timeout=60 * 60)  # 1 hour

            return Response(parsed, status=200)

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


class SalaryInsightsAPIView(APIView):
    """
    Provides AI-generated salary insights for key global tech hubs and roles.
    
    This view uses caching to minimize expensive API calls to the Groq model,
    returning fresh data once every 24 hours.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # Define a unique key for the cache
        cache_key = 'ai_salary_insights_data'
        
        # 1. Try to get the data from the cache first
        cached_insights = cache.get(cache_key)
        if cached_insights:
            print("Serving salary insights from CACHE.") # Or use logger.info
            return Response(cached_insights, status=status.HTTP_200_OK)
            
        # 2. If not in cache, call the AI service
        print("Cache miss. Calling AI service for salary insights...")
        
        # Define the parameters for the AI model
        cities = ["UAE", "USA", "EU", "Singapore"]
        roles = [
            "Data Scientist", "Machine Learning Engineer", "AI Engineer", 
            "Data Analyst", "AI Research Scientist", "Computer Vision Engineer", 
            "NLP Engineer", "ML Ops Engineer", "Generative AI Developer"
        ]

        try:
            insights = generate_salary_insights(cities, roles)
            
            if insights is None:
                return Response(
                    {"error": "Failed to generate salary insights. The AI service may be down or returned an invalid format."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
            
            # 3. Save the new data to the cache for 24 hours (86400 seconds)
            cache.set(cache_key, insights, timeout=86400)
            
            # 4. Return the successful response
            return Response(insights, status=status.HTTP_200_OK)

        except Exception as e:
            # Catch any other unexpected errors
            return Response(
                {"error": f"An unexpected internal server error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )







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
        





#################### speach to text model ################# 
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
import whisper
import tempfile
import os
 
# Load Whisper model ONCE globally
model = whisper.load_model("tiny")  # You can also try "base" if accuracy needed
 
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