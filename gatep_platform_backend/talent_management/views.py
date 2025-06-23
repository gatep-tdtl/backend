_B = 'content'
_A = 'meta-llama/Meta-Llama-3-70B-Instruct'
import os, fitz, json, re
from django.http import JsonResponse
from django.conf import settings
from huggingface_hub import InferenceClient
from .models import Resume, CustomUser # Ensure your Resume model is correctly imported
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status # Import status codes

# Get the CustomUser model
User = get_user_model()

def clean_bullets(text):
    return re.sub('^\\s*[-•*0-9.]+\\s*','',text,flags=re.MULTILINE)

HFF_TOKEN = os.getenv('HFF_TOKEN')
if not HFF_TOKEN:
    raise ValueError('HuggingFace token not set in environment (HFF_TOKEN). Please set it to proceed.')

# Constants for clarity (your short variables)
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
    """
    Handles all AI model interactions, PDF text extraction, and data structuring
    based on LLM output.
    """
    def __init__(self):
        self.client = InferenceClient(_A, token=HFF_TOKEN)
        self.temp_pdf_paths = []

    def _extract_text_from_pdf(self, path):
        text = ''
        try:
            doc = fitz.open(path)
            for page in doc:
                text += page.get_text()
            doc.close()
        except Exception as e:
            raise Exception(f"Error extracting text from PDF: {e}. Ensure it's a valid PDF.")
        return text

    def _build_prompt(self, form_data, pdf_text):
        form_info_str = json.dumps(form_data, indent=2)
        return f'''
You are an AI Resume Builder.
Your goal is to extract and structure comprehensive resume information from the provided data.
Combine the user's explicit form input with details extracted from their old resume PDF.
Prioritize explicit form input if it provides clearer or more up-to-date information for a field.
If a piece of information is missing from the form but present in the PDF, extract it from the PDF.
If information exists in both, use the most complete/accurate version.

Return your output in **strict JSON format only**. Do NOT include any markdown (e.g., ```json), conversational text, or explanations outside the JSON.
The JSON structure should strictly follow the schema below, prioritizing sections important to recruiters.

JSON Schema for Resume Data:
{{
    "personal_info": {{
        "name": "Full name of the candidate",
        "email": "Email address",
        "phone": "Phone number",
        "current_location": "Current city or location",
        "aadhar_number": "Aadhar number (if provided in text)",
        "passport_number": "Passport number (if provided in text)",
        "current_company": "Current employer (if any)"
    }},
    "links": {{
        "linkedin_url": "URL to LinkedIn profile",
        "github_url": "URL to GitHub profile",
        "portfolio_url": "URL to personal portfolio",
        "stackoverflow_url": "URL to Stack Overflow profile",
        "medium_or_blog_url": "URL to Medium/blog"
    }},
    "professional_summary": "A concise paragraph summarizing the candidate's overall experience, strengths, and career goals, tailored for an AI Engineer role. Max 3-4 sentences.",
    "skills": [
        "Technical Skill 1 (e.g., Python)",
        "Technical Skill 2 (e.g., TensorFlow)",
        "Soft Skill 1 (e.g., Problem-solving)"
    ],
    "experience": [
        {{
            "title": "Job Title",
            "company": "Company Name",
            "duration": "Start Date - End Date (e.g., Jan 2020 - Dec 2022)",
            "responsibilities": ["Quantifiable achievement 1 (e.g., Led development of X, resulting in Y% improvement)", "Responsibility/Achievement 2"]
        }}
        // List in reverse chronological order (most recent first)
    ],
    "projects": [
        {{
            "name": "Project Name",
            "description": "Short description of the project, including technologies used and quantifiable outcomes/achievements, relevant to AI engineering. Max 2-3 sentences.",
            "url": "Optional URL to project"
        }}
    ],
    "education_details": {{
        "degree": {{
            "degree_name": "Name of the Degree (e.g., Bachelor of Technology, Master of Science)",
            "institution_name": "Name of the Degree institution/university",
            "specialization": "Specialization of the degree (e.g., Computer Science, Electrical Engineering, AI/ML)",
            "year_passing": "Year of passing Degree",
            "score": "Percentage or CGPA for Degree"
        }},
        "diploma": {{
            "course_name": "Name of the Diploma course (e.g., Diploma in Mechanical Engineering)",
            "institution_name": "Name of the Diploma institution",
            "year_passing": "Year of passing Diploma",
            "score": "Percentage or CGPA for Diploma"
        }},
        "twelfth": {{
            "board_name": "Name of the 12th board (e.g., CBSE, HSC, State Board)",
            "college_name": "Name of the college/school for 12th grade",
            "year_passing": "Year of passing 12th grade",
            "score": "Percentage or CGPA for 12th grade"
        }},
        "tenth": {{
            "board_name": "Name of the 10th board (e.g., CBSE, ICSE, State Board)",
            "school_name": "Name of the school for 10th grade",
            "year_passing": "Year of passing 10th grade",
            "score": "Percentage or CGPA for 10th grade"
        }}
    }},
    "certifications": ["Certification Name 1 (e.g., AWS Certified Machine Learning - Specialty)", "Certification Name 2"],
    "awards": ["Award Title 1", "Award Title 2"],
    "publications": ["Publication Title 1 (e.g., 'Leveraging X for Y' - Journal/Conference, Year)", "Publication Title 2"],
    "open_source_contributions": ["Description of contribution 1 (e.g., Fixed critical bug in X library, improving performance by Y%)", "Description of contribution 2"],
    "volunteering_experience": "A description of any unpaid roles or contributions, highlighting leadership or relevant skills.",
    "extracurriculars": "A description of non-academic interests like sports, clubs, or creative pursuits, showing teamwork or leadership.",
    "languages": {{
        "Language 1": "Proficiency (e.g., Native, Fluent, Conversational)",
        "Language 2": "Proficiency"
    }},
    "preferences": {{
        "work_arrangement": "e.g., Remote, Onsite, Hybrid, Freelance",
        "preferred_location": "e.g., Bengaluru, Mumbai, Remote-only, Open to Relocation",
        "other_preferences": "Any other specific job/role preferences (e.g., Prefers roles with strong research component)"
    }},
    "legal": {{
        "work_authorization": "e.g., Indian Citizen, US Permanent Resident, H1B Visa sponsorship required",
        "criminal_record_disclosure": "e.g., None, Details if applicable"
    }},
    "document_verification": "Status indicating content verification (e.g., 'Fully Verified', 'Partially Verified', 'Incomplete').",
    "interests": ["Interest 1", "Interest 2"]
}}

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
        prompt = f"""
You are an AI assistant specialized in extracting academic scores.
Your task is to find the final score (e.g., percentage, CGPA, grade) from the provided text, which is extracted from a marksheet or academic transcript for a {education_level} level.

Look for a prominent numerical value often followed by '%', 'CGPA', 'GPA', or 'Grade'.
If a percentage is available, prioritize it. If CGPA/GPA is available, provide it.
Do NOT include any additional text, explanations, or markdown (e.g., ```json). Return only the score.
If no clear, verifiable score is found, return an empty string.

Examples of desired output: "85%", "9.2 CGPA", "A Grade", "75.5"

Marksheet Text:
{marksheet_text}

Extracted Score:"""
        try:
            response = self.client.chat.completions.create(model=_A, messages=[{'role': 'user', _B: prompt}], max_tokens=50, temperature=.1, stop=['\n'])
            score = response.choices[0].message.content.strip()
            if re.match('^[0-9.]+\\s*(%|CGPA|GPA|Grade)?$', score, re.IGNORECASE):
                return score
            else:
                print(f"LLM returned non-score value for {education_level}: '{score}'. Returning empty.")
                return ''
        except Exception as e:
            print(f"Error calling LLM for {education_level} score extraction: {e}")
            return ''

    def _call_llama_model(self, prompt):
        response = self.client.chat.completions.create(model=_A, messages=[{'role': 'user', _B: prompt}], max_tokens=3000)
        return response.choices[0].message.content

    def process_resume_data(self, data_for_llm_prompt, resume_pdf_file, education_files):
        """
        Main method to process resume data using the LLM.
        Takes form data, main resume PDF file, and education result files.
        Returns the structured resume data and list of temporary PDF paths.
        """
        self.temp_pdf_paths = [] # Reset for each processing call
        structured_resume = {}

        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_uploads')
        os.makedirs(temp_dir, exist_ok=True)

        if resume_pdf_file:
            pdf_path = os.path.join(temp_dir, resume_pdf_file.name)
            with open(pdf_path, 'wb+') as temp_file:
                for chunk in resume_pdf_file.chunks():
                    temp_file.write(chunk)
            self.temp_pdf_paths.append(pdf_path)
            print(f"Main resume PDF saved temporarily at: {pdf_path}")

            pdf_text = self._extract_text_from_pdf(pdf_path)
            print(f"Extracted PDF text (first 200 chars): {pdf_text[:200]}...")

            prompt_text_for_llm = self._build_prompt(data_for_llm_prompt, pdf_text)
            generated_json_text = self._call_llama_model(prompt_text_for_llm)
            structured_resume = json.loads(generated_json_text)
            print(f"Parsed structured_resume from main LLM: {structured_resume}")
        else:
            print("No resume PDF provided to AI pipeline. Populating structured_resume directly from form data.")
            # If no PDF, structured_resume remains empty, so use form_data directly for all fields.
            structured_resume = self._populate_structured_resume_from_form(data_for_llm_prompt)

        # Process marksheet PDFs if the main LLM didn't get a score and file is provided
        education_levels_to_check = {F: education_files.get(F), G: education_files.get(G), H: education_files.get(H), C: education_files.get(C)}
        for (level, upload_file) in education_levels_to_check.items():
            current_llm_score = structured_resume.get(A, {}).get(level, {}).get(D, '')
            form_data_score = data_for_llm_prompt.get(f"{level}_score", '')

            if not (current_llm_score.strip() or form_data_score.strip()) and upload_file:
                print(f"Attempting to extract {level} score from uploaded PDF...")
                marksheet_pdf_path = os.path.join(temp_dir, f"{level}_" + upload_file.name)
                try:
                    with open(marksheet_pdf_path, 'wb+') as temp_file:
                        for chunk in upload_file.chunks():
                            temp_file.write(chunk)
                    self.temp_pdf_paths.append(marksheet_pdf_path)
                    marksheet_text = self._extract_text_from_pdf(marksheet_pdf_path)
                    extracted_score = self._extract_score_from_marksheet_text(marksheet_text, level)
                    if extracted_score:
                        if A not in structured_resume: structured_resume[A] = {}
                        if level not in structured_resume[A]: structured_resume[A][level] = {}
                        structured_resume[A][level][D] = extracted_score
                        print(f"Successfully extracted and updated {level} score: {extracted_score}")
                    else:
                        print(f"Could not extract {level} score from marksheet text.")
                except Exception as score_extract_e:
                    print(f"Error processing {level} marksheet for score extraction: {score_extract_e}")
        
        return structured_resume

    def get_temp_pdf_paths(self):
        return self.temp_pdf_paths

    def _populate_structured_resume_from_form(self, data_for_llm_prompt):
        # This method is called if no resume PDF is provided.
        # It structures the form data to resemble the LLM's expected output structure.
        structured_resume = {}
        structured_resume[B] = { # personal_info
            L: data_for_llm_prompt.get(L, ''), M: data_for_llm_prompt.get(M, ''), N: data_for_llm_prompt.get(N, ''),
            S: data_for_llm_prompt.get(S, ''), T: data_for_llm_prompt.get(T, ''),
            U: data_for_llm_prompt.get(U, ''), V: data_for_llm_prompt.get(V, '')
        }
        structured_resume[I] = { # links
            W: data_for_llm_prompt.get(W, ''), X: data_for_llm_prompt.get(X, ''), Y: data_for_llm_prompt.get(Y, ''),
            Z: data_for_llm_prompt.get(Z, ''), a: data_for_llm_prompt.get(a, '')
        }
        structured_resume[s] = data_for_llm_prompt.get('summary', '') # professional_summary
        structured_resume[h] = data_for_llm_prompt.get(h, []) # skills
        structured_resume[i] = data_for_llm_prompt.get(i, []) # experience
        structured_resume[j] = data_for_llm_prompt.get(j, []) # projects
        structured_resume[k] = data_for_llm_prompt.get(k, []) # certifications
        structured_resume[l] = data_for_llm_prompt.get(l, []) # awards
        structured_resume[m] = data_for_llm_prompt.get(m, []) # publications
        structured_resume[n] = data_for_llm_prompt.get(n, []) # open_source_contributions
        structured_resume[d] = data_for_llm_prompt.get(d, '') # volunteering_experience
        structured_resume[f] = data_for_llm_prompt.get(f, '') # extracurriculars
        structured_resume[p] = data_for_llm_prompt.get(p, {}) # languages (JSONField)
        structured_resume[o] = data_for_llm_prompt.get(o, []) # interests
        structured_resume[q] = data_for_llm_prompt.get(q, []) # references
        
                # Preferences
        raw_preferences = data_for_llm_prompt.get(E, {})
        if not isinstance(raw_preferences, dict):
            try:
                raw_preferences = json.loads(raw_preferences)
            except Exception:
                raw_preferences = {}
        if not isinstance(raw_preferences, dict):
            raw_preferences = {}
        structured_resume[E] = raw_preferences
        structured_resume[E][O] = data_for_llm_prompt.get(O, '')
        structured_resume[E][P] = data_for_llm_prompt.get(P, '')
        structured_resume[Q] = data_for_llm_prompt.get(Q, '') # preferred_tech_stack
        structured_resume[R] = data_for_llm_prompt.get(R, '') # dev_environment

        # Legal
        structured_resume[v] = {
            b: data_for_llm_prompt.get(b, ''), # work_authorization
            c: data_for_llm_prompt.get(c, '') # criminal_record_disclosure
        }
        structured_resume['document_verification'] = data_for_llm_prompt.get('document_verification', 'Incomplete')

        # Education details (from form data if no PDF was processed)
        structured_resume[A] = {
            F: {t: data_for_llm_prompt.get('tenth_board_name', ''), 'school_name': data_for_llm_prompt.get('tenth_school_name', ''), K: data_for_llm_prompt.get('tenth_year_passing', ''), D: data_for_llm_prompt.get('tenth_score', '')},
            G: {t: data_for_llm_prompt.get('twelfth_board_name', ''), 'college_name': data_for_llm_prompt.get('twelfth_college_name', ''), K: data_for_llm_prompt.get('twelfth_year_passing', ''), D: data_for_llm_prompt.get('twelfth_score', '')},
            H: {'course_name': data_for_llm_prompt.get('diploma_course_name', ''), u: data_for_llm_prompt.get('diploma_institution_name', ''), K: data_for_llm_prompt.get('diploma_year_passing', ''), D: data_for_llm_prompt.get('diploma_score', '')},
            C: {g: data_for_llm_prompt.get('degree_name', ''), u: data_for_llm_prompt.get('degree_institution_name', ''), 'specialization': data_for_llm_prompt.get('degree_specialization', ''), K: data_for_llm_prompt.get('degree_year_passing', ''), D: data_for_llm_prompt.get('degree_score', '')}
        }
        return structured_resume


class ResumeBuilderAPIView(APIView):
    """
    Handles incoming HTTP requests for Resume creation, retrieval, update, and soft deletion.
    Processes form data and files, then delegates AI processing to ResumeAIPipeline.
    """
    permission_classes = [IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ai_pipeline = ResumeAIPipeline()

    def _process_incoming_form_data(self, request):
        """
        Extracts all relevant data from the request.data (FormData)
        and organizes it for AI processing or direct database storage.
        """
        data_for_llm_prompt = {}
        files = {}
        
        # --- 1. Extract Plain Text Fields ---
        plain_text_fields = [L, M, N, 'summary', O, P, Q, R, S, T, U, V, W, X, Y, Z, a, b, c, d, f,
                             'tenth_board_name', 'tenth_school_name', 'tenth_year_passing', 'tenth_score',
                             'twelfth_board_name', 'twelfth_college_name', 'twelfth_year_passing', 'twelfth_score',
                             'diploma_course_name', 'diploma_institution_name', 'diploma_year_passing', 'diploma_score',
                             g, 'degree_institution_name', 'degree_specialization', 'degree_year_passing', 'degree_score',
                             'document_verification']

        for field in plain_text_fields:
            # For update, only include if present in request.data. If not present, it implies no change for this field.
            if field in request.data:
                data_for_llm_prompt[field] = request.data.get(field)

        # --- 2. Extract JSON String Fields (sent as strings from frontend) ---
        json_string_fields = [h, i, j, k, l, m, n, o, q]
        for field in json_string_fields:
            if field in request.data: # Only process if the field is present in the request
                json_str_val = request.data.get(field)
                if json_str_val:
                    try:
                        data_for_llm_prompt[field] = json.loads(json_str_val)
                    except json.JSONDecodeError:
                        # If it's not valid JSON, store as raw string (or handle error)
                        data_for_llm_prompt[field] = json_str_val 
                else:
                    # If field is present but empty, it might mean clearing it
                    data_for_llm_prompt[field] = [] # Set to empty list
            # Else, if field not in request.data, it implies no change to this JSON field.

        # Special handling for 'preferences' (JSON dict)
        if E in request.data:
            pref_json_str = request.data.get(E)
            if pref_json_str:
                try:
                    data_for_llm_prompt[E] = json.loads(pref_json_str)
                except json.JSONDecodeError:
                    data_for_llm_prompt[E] = pref_json_str # Fallback to string if not valid JSON
            else:
                data_for_llm_prompt[E] = {} # Clear preferences
        
        # 'languages' is a JSONField in your model, directly takes Python dict
        if p in request.data:
            lang_data = request.data.get(p)
            if lang_data:
                try:
                    data_for_llm_prompt[p] = json.loads(lang_data) if isinstance(lang_data, str) else lang_data
                except json.JSONDecodeError:
                    data_for_llm_prompt[p] = {} # Default to empty dict if malformed string
            else:
                data_for_llm_prompt[p] = {} # Clear languages

        # --- 3. Extract File Fields ---
        file_fields = ['resume_pdf', 'profile_photo', 'tenth_result_upload', 
                       'twelfth_result_upload', 'diploma_result_upload', 'degree_result_upload']
        for field in file_fields:
            if field in request.data: # Check if the file field was actually sent
                files[field] = request.data.get(field)

        print(f"Data prepared for AI pipeline: {data_for_llm_prompt}")

        return {
            'data_for_llm_prompt': data_for_llm_prompt,
            'files': files
        }

    def _update_resume_instance(self, resume_instance, structured_resume, files):
        """
        Updates the Resume model instance with data from the structured_resume 
        (either from LLM or direct form data) and uploaded files.
        This method is now more robust for partial updates: it only updates fields
        if the data is explicitly provided in `structured_resume` or `files`.
        """
        # Personal Info
        # Using .get() with existing value as default ensures fields not in structured_resume aren't nulled out
        resume_instance.name = structured_resume.get(B, {}).get(L, resume_instance.name)
        resume_instance.email = structured_resume.get(B, {}).get(M, resume_instance.email)
        resume_instance.phone = structured_resume.get(B, {}).get(N, resume_instance.phone)
        resume_instance.current_location = structured_resume.get(B, {}).get(S, resume_instance.current_location)
        resume_instance.current_company = structured_resume.get(B, {}).get(V, resume_instance.current_company)
        resume_instance.aadhar_number = structured_resume.get(B, {}).get(T, resume_instance.aadhar_number)
        resume_instance.passport_number = structured_resume.get(B, {}).get(U, resume_instance.passport_number)

        # Links
        resume_instance.linkedin_url = structured_resume.get(I, {}).get(W, resume_instance.linkedin_url)
        resume_instance.github_url = structured_resume.get(I, {}).get(X, resume_instance.github_url)
        resume_instance.portfolio_url = structured_resume.get(I, {}).get(Y, resume_instance.portfolio_url)
        resume_instance.stackoverflow_url = structured_resume.get(I, {}).get(Z, resume_instance.stackoverflow_url)
        resume_instance.medium_or_blog_url = structured_resume.get(I, {}).get(a, resume_instance.medium_or_blog_url)

        # Summaries & Preferences
        resume_instance.summary = structured_resume.get(s, resume_instance.summary)
        # Note: generated_summary could be different from summary if it's purely LLM-generated.
        # For simplicity, we'll keep them synced for now, but you might want to separate them.
        resume_instance.generated_summary = structured_resume.get(s, resume_instance.generated_summary) 
        
        # JSONField for preferences
        if E in structured_resume:
            resume_instance.preferences = structured_resume[E]
        
        resume_instance.work_arrangement = structured_resume.get(E, {}).get(O, resume_instance.work_arrangement)
        resume_instance.preferred_location = structured_resume.get(E, {}).get(P, resume_instance.preferred_location)
        resume_instance.preferred_tech_stack = structured_resume.get(Q, resume_instance.preferred_tech_stack)
        resume_instance.dev_environment = structured_resume.get(R, resume_instance.dev_environment)

        # Legal & Verification
        resume_instance.work_authorization = structured_resume.get(v, {}).get(b, resume_instance.work_authorization)
        resume_instance.criminal_record_disclosure = structured_resume.get(v, {}).get(c, resume_instance.criminal_record_disclosure)
        resume_instance.document_verification = structured_resume.get('document_verification', resume_instance.document_verification)

        # List-based fields (Stored as JSON strings in TextField)
        if h in structured_resume:
            resume_instance.skills = json.dumps(structured_resume[h])
        if i in structured_resume:
            resume_instance.experience = json.dumps(structured_resume[i])
        if j in structured_resume:
            resume_instance.projects = json.dumps(structured_resume[j])
        if k in structured_resume:
            resume_instance.certifications = json.dumps(structured_resume[k])
        if l in structured_resume:
            resume_instance.awards = json.dumps(structured_resume[l])
        if m in structured_resume:
            resume_instance.publications = json.dumps(structured_resume[m])
        if n in structured_resume:
            resume_instance.open_source_contributions = json.dumps(structured_resume[n])
        
        # These are TextFields not expected to store JSON lists/dicts (free text)
        resume_instance.volunteering_experience = structured_resume.get(d, resume_instance.volunteering_experience)
        resume_instance.extracurriculars = structured_resume.get(f, resume_instance.extracurriculars)

        if o in structured_resume:
            resume_instance.interests = json.dumps(structured_resume[o])
        if q in structured_resume:
            resume_instance.references = json.dumps(structured_resume[q])
        
        # languages (JSONField)
        if p in structured_resume:
            resume_instance.languages = structured_resume[p]
        
        # File fields - only update if a new file is provided in the current request
        if files.get('profile_photo'):
            resume_instance.profile_photo = files.get('profile_photo')
        # If a client sends 'profile_photo': '' or 'null' in multipart, it means clear the field
        elif 'profile_photo' in files and files.get('profile_photo') is None:
             resume_instance.profile_photo = None

        if files.get('resume_pdf'): # Main resume PDF
            resume_instance.resume_pdf = files.get('resume_pdf')
        elif 'resume_pdf' in files and files.get('resume_pdf') is None:
            resume_instance.resume_pdf = None

        # Education fields (iterating to apply updates only where data is present)
        edu_details = structured_resume.get(A, {})
        
        # 10th
        if F in edu_details:
            tenth_data = edu_details[F]
            resume_instance.tenth_board_name = tenth_data.get(t, resume_instance.tenth_board_name)
            resume_instance.tenth_school_name = tenth_data.get('school_name', resume_instance.tenth_school_name)
            resume_instance.tenth_year_passing = tenth_data.get(K, resume_instance.tenth_year_passing)
            resume_instance.tenth_score = tenth_data.get(D, resume_instance.tenth_score)
        if files.get('tenth_result_upload'):
            resume_instance.tenth_result_upload = files.get('tenth_result_upload')
        elif 'tenth_result_upload' in files and files.get('tenth_result_upload') is None:
            resume_instance.tenth_result_upload = None
        
        # 12th
        if G in edu_details:
            twelfth_data = edu_details[G]
            resume_instance.twelfth_board_name = twelfth_data.get(t, resume_instance.twelfth_board_name)
            resume_instance.twelfth_college_name = twelfth_data.get('college_name', resume_instance.twelfth_college_name)
            resume_instance.twelfth_year_passing = twelfth_data.get(K, resume_instance.twelfth_year_passing)
            resume_instance.twelfth_score = twelfth_data.get(D, resume_instance.twelfth_score)
        if files.get('twelfth_result_upload'):
            resume_instance.twelfth_result_upload = files.get('twelfth_result_upload')
        elif 'twelfth_result_upload' in files and files.get('twelfth_result_upload') is None:
            resume_instance.twelfth_result_upload = None
        
        # Diploma
        if H in edu_details:
            diploma_data = edu_details[H]
            resume_instance.diploma_course_name = diploma_data.get('course_name', resume_instance.diploma_course_name)
            resume_instance.diploma_institution_name = diploma_data.get(u, resume_instance.diploma_institution_name)
            resume_instance.diploma_year_passing = diploma_data.get(K, resume_instance.diploma_year_passing)
            resume_instance.diploma_score = diploma_data.get(D, resume_instance.diploma_score)
        if files.get('diploma_result_upload'):
            resume_instance.diploma_result_upload = files.get('diploma_result_upload')
        elif 'diploma_result_upload' in files and files.get('diploma_result_upload') is None:
            resume_instance.diploma_result_upload = None
        
        # Degree
        if C in edu_details:
            degree_data = edu_details[C]
            resume_instance.degree_name = degree_data.get(g, resume_instance.degree_name)
            resume_instance.degree_institution_name = degree_data.get(u, resume_instance.degree_institution_name)
            resume_instance.degree_specialization = degree_data.get('specialization', resume_instance.degree_specialization)
            resume_instance.degree_year_passing = degree_data.get(K, resume_instance.degree_year_passing)
            resume_instance.degree_score = degree_data.get(D, resume_instance.degree_score)
        if files.get('degree_result_upload'):
            resume_instance.degree_result_upload = files.get('degree_result_upload')
        elif 'degree_result_upload' in files and files.get('degree_result_upload') is None:
            resume_instance.degree_result_upload = None


    def _serialize_resume_to_json(self, resume_instance):
        """
        Serializes a Resume instance into a dictionary suitable for JSON response.
        Handles parsing of JSON string fields.
        """
        data = {
            'id': resume_instance.pk,
            'talent_id': resume_instance.talent_id.pk,
            
            # Personal Info
            'name': resume_instance.name,
            'email': resume_instance.email,
            'phone': resume_instance.phone,
            'profile_photo_url': resume_instance.profile_photo.url if resume_instance.profile_photo else None,
            'current_location': resume_instance.current_location,
            'current_company': resume_instance.current_company,
            'aadhar_number': resume_instance.aadhar_number,
            'passport_number': resume_instance.passport_number,

            # Links
            'linkedin_url': resume_instance.linkedin_url,
            'github_url': resume_instance.github_url,
            'portfolio_url': resume_instance.portfolio_url,
            'stackoverflow_url': resume_instance.stackoverflow_url,
            'medium_or_blog_url': resume_instance.medium_or_blog_url,

            # Summaries
            'summary': resume_instance.summary,
            'generated_summary': resume_instance.generated_summary,

            # Core Resume Content (Parse JSON strings back to Python objects)
            'skills': json.loads(resume_instance.skills) if resume_instance.skills else [],
            'experience': json.loads(resume_instance.experience) if resume_instance.experience else [],
            'projects': json.loads(resume_instance.projects) if resume_instance.projects else [],
            'certifications': json.loads(resume_instance.certifications) if resume_instance.certifications else [],
            'awards': json.loads(resume_instance.awards) if resume_instance.awards else [],
            'publications': json.loads(resume_instance.publications) if resume_instance.publications else [],
            'open_source_contributions': json.loads(resume_instance.open_source_contributions) if resume_instance.open_source_contributions else [],
            'interests': json.loads(resume_instance.interests) if resume_instance.interests else [],
            'references': json.loads(resume_instance.references) if resume_instance.references else [],

            # Free text fields
            'volunteering_experience': resume_instance.volunteering_experience,
            'extracurriculars': resume_instance.extracurriculars,

            # Preferences (JSONField handles this directly)
            'languages': resume_instance.languages,
            'preferences': resume_instance.preferences,
            'work_arrangement': resume_instance.work_arrangement,
            'preferred_location': resume_instance.preferred_location,
            'preferred_tech_stack': resume_instance.preferred_tech_stack,
            'dev_environment': resume_instance.dev_environment,

            # Legal Information
            'work_authorization': resume_instance.work_authorization,
            'criminal_record_disclosure': resume_instance.criminal_record_disclosure,
            
            # Document Verification Status
            'document_verification': resume_instance.document_verification,

            # Education Details
            'education_details': {
                'tenth': {
                    'board_name': resume_instance.tenth_board_name,
                    'school_name': resume_instance.tenth_school_name,
                    'year_passing': resume_instance.tenth_year_passing,
                    'score': resume_instance.tenth_score,
                    'result_upload_url': resume_instance.tenth_result_upload.url if resume_instance.tenth_result_upload else None
                },
                'twelfth': {
                    'board_name': resume_instance.twelfth_board_name,
                    'college_name': resume_instance.twelfth_college_name,
                    'year_passing': resume_instance.twelfth_year_passing,
                    'score': resume_instance.twelfth_score,
                    'result_upload_url': resume_instance.twelfth_result_upload.url if resume_instance.twelfth_result_upload else None
                },
                'diploma': {
                    'course_name': resume_instance.diploma_course_name,
                    'institution_name': resume_instance.diploma_institution_name,
                    'year_passing': resume_instance.diploma_year_passing,
                    'score': resume_instance.diploma_score,
                    'result_upload_url': resume_instance.diploma_result_upload.url if resume_instance.diploma_result_upload else None
                },
                'degree': {
                    'degree_name': resume_instance.degree_name,
                    'institution_name': resume_instance.degree_institution_name,
                    'specialization': resume_instance.degree_specialization,
                    'year_passing': resume_instance.degree_year_passing,
                    'score': resume_instance.degree_score,
                    'result_upload_url': resume_instance.degree_result_upload.url if resume_instance.degree_result_upload else None
                }
            },
            
            'resume_pdf_url': resume_instance.resume_pdf.url if resume_instance.resume_pdf else None,
            'is_deleted': resume_instance.is_deleted,
            'created_at': resume_instance.created_at.isoformat(),
            'updated_at': resume_instance.updated_at.isoformat(),
        }
        return data

    def get(self, request, *args, **kwargs):
        """
        Retrieves the resume data for the authenticated user.
        """
        user = request.user
        try:
            resume_instance = Resume.objects.get(talent_id=user, is_deleted=False)
            serialized_data = self._serialize_resume_to_json(resume_instance)
            return JsonResponse(serialized_data, status=status.HTTP_200_OK)
        except Resume.DoesNotExist:
            return JsonResponse({'message': 'Resume not found for this user.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return JsonResponse({J: f"An error occurred while retrieving resume: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request, *args, **kwargs):
        """
        Creates or updates resume data.
        All fields are optional; only provided fields will be used.
        """
        user = request.user  # The authenticated CustomUser instance

        print(f"Incoming Content-Type: {request.content_type}")
        print(f"Request Method: {request.method}")
        print(f"Request data (text fields and files): {request.data}")

        processing_result = self._process_incoming_form_data(request)
        data_for_llm_prompt = processing_result['data_for_llm_prompt']
        files = processing_result['files']  # Contains actual Django UploadedFile objects

        try:
            # Check if a resume already exists for this user
            resume_instance, created = Resume.objects.get_or_create(
                talent_id=user,
                defaults={
                    'name': data_for_llm_prompt.get('name', getattr(user, 'username', '')),
                    'email': data_for_llm_prompt.get('email', getattr(user, 'email', '')),
                    'phone': data_for_llm_prompt.get('phone', getattr(user, 'phone_number', '')),
                    'is_deleted': False
                }
            )

            # If existing resume was soft-deleted, reactivate it
            if resume_instance.is_deleted and not created:
                resume_instance.is_deleted = False
                resume_instance.save()
                print(f"Reactivated resume for user: {getattr(user, 'username', '')}")

            # Delegate AI processing to the ResumeAIPipeline instance
            existing_data_for_ai = self._serialize_resume_to_json(resume_instance)
            merged_data_for_ai = {**existing_data_for_ai, **data_for_llm_prompt}

            structured_resume = self.ai_pipeline.process_resume_data(
                merged_data_for_ai,
                files.get('resume_pdf'),
                {
                    F: files.get('tenth_result_upload'),
                    G: files.get('twelfth_result_upload'),
                    H: files.get('diploma_result_upload'),
                    C: files.get('degree_result_upload')
                }
            )

            # Update fields based on processed/form data (this method already handles partial updates)
            self._update_resume_instance(resume_instance, structured_resume, files)

            # Save the updated or newly created resume
            resume_instance.save()

            status_message = "Resume created and saved successfully!" if created else "Resume progress saved successfully!"
            return JsonResponse({'message': status_message, 'resume_id': resume_instance.pk, 'submitted_text_data': data_for_llm_prompt, 'parsed_data_from_llm': structured_resume}, status=status.HTTP_200_OK)

        except json.JSONDecodeError as e:
            raw_llm_output_preview = locals().get('generated_json_text', 'N/A')[:1000]
            return JsonResponse({J: f"Failed to parse LLM response as JSON: {e}. Raw response might be invalid or incomplete. Preview: {raw_llm_output_preview}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            if '402 Client Error' in str(e) and 'HuggingFace' in str(e):
                return JsonResponse({J: 'Hugging Face credits exceeded or payment required. Please check your account on huggingface.co.'}, status=status.HTTP_402_PAYMENT_REQUIRED)
            print(f"An unexpected error occurred: {e}")
            return JsonResponse({J: f"An internal server error occurred: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            # Ensure temporary files are cleaned up after the request
            temp_paths = self.ai_pipeline.get_temp_pdf_paths()
            for path in temp_paths:
                if os.path.exists(path):
                    os.remove(path)
                    print(f"Deleted temporary PDF: {path}")

    def put(self, request, *args, **kwargs):
        """
        Updates the entire resume data for the authenticated user.
        Behaves like PATCH, applying updates to fields provided.
        """
        user = request.user
        try:
            resume_instance = Resume.objects.get(talent_id=user, is_deleted=False)
        except Resume.DoesNotExist:
            return JsonResponse({'message': 'Resume not found for this user.'}, status=status.HTTP_404_NOT_FOUND)

        print(f"Incoming Content-Type (PUT): {request.content_type}")
        print(f"Request data (PUT): {request.data}")

        processing_result = self._process_incoming_form_data(request)
        data_for_llm_prompt = processing_result['data_for_llm_prompt']
        files = processing_result['files']

        try:
            # When updating, we should pass the *current* state of the resume to the AI
            # along with the new incoming data, so the AI has full context for merging.
            existing_data_for_ai = self._serialize_resume_to_json(resume_instance)
            # The incoming `data_for_llm_prompt` should override existing data where provided
            merged_data_for_ai = {**existing_data_for_ai, **data_for_llm_prompt}

            structured_resume = self.ai_pipeline.process_resume_data(
                merged_data_for_ai, # Pass merged data for LLM processing
                files.get('resume_pdf'), # Only pass file if a new one is sent
                {
                    F: files.get('tenth_result_upload'),
                    G: files.get('twelfth_result_upload'),
                    H: files.get('diploma_result_upload'),
                    C: files.get('degree_result_upload')
                }
            )
            
            self._update_resume_instance(resume_instance, structured_resume, files)
            resume_instance.save()
            serialized_data = self._serialize_resume_to_json(resume_instance)
            return JsonResponse({'message': 'Resume updated successfully!', 'resume_data': serialized_data}, status=status.HTTP_200_OK)

        except json.JSONDecodeError as e:
            raw_llm_output_preview = locals().get('generated_json_text', 'N/A')[:1000]
            return JsonResponse({J: f"Failed to parse LLM response as JSON: {e}. Raw response might be invalid or incomplete. Preview: {raw_llm_output_preview}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            if '402 Client Error' in str(e) and 'HuggingFace' in str(e):
                return JsonResponse({J: 'Hugging Face credits exceeded or payment required. Please check your account on huggingface.co.'}, status=status.HTTP_402_PAYMENT_REQUIRED)
            print(f"An unexpected error occurred during PUT: {e}")
            return JsonResponse({J: f"An internal server error occurred: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            temp_paths = self.ai_pipeline.get_temp_pdf_paths()
            for path in temp_paths:
                if os.path.exists(path):
                    os.remove(path)
                    print(f"Deleted temporary PDF: {path}")

    def patch(self, request, *args, **kwargs):
        """
        Partially updates resume data for the authenticated user.
        This method will behave identically to the `PUT` method in this implementation,
        as `_update_resume_instance` already handles partial updates by only
        applying changes for fields present in the request data.
        """
        return self.put(request, *args, **kwargs) # Delegate to PUT for shared logic

    def delete(self, request, *args, **kwargs):
        """
        Soft deletes the resume for the authenticated user by setting `is_deleted` to True.
        """
        user = request.user
        try:
            resume_instance = Resume.objects.get(talent_id=user, is_deleted=False)
            resume_instance.is_deleted = True
            resume_instance.save()
            return JsonResponse({'message': 'Resume soft-deleted successfully!'}, status=status.HTTP_200_OK)
        except Resume.DoesNotExist:
            return JsonResponse({'message': 'Resume not found or already deleted for this user.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return JsonResponse({J: f"An error occurred during soft delete: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)