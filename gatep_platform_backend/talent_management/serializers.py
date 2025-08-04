# talent_management/serializers.py
import json
from rest_framework import serializers
from .models import CustomUser, TalentProfile, Resume
from employer_management.models import JobPosting, Company

class CustomUserLiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'phone_number', 'first_name', 'last_name']

class TalentProfileLiteSerializer(serializers.ModelSerializer):
    user = CustomUserLiteSerializer(read_only=True)
    class Meta:
        model = TalentProfile
        fields = ['user', 'resume_url', 'skills', 'portfolio_url'] # Removed 'profile_summary' as it's not in the model
        read_only_fields = ['user']

# --- Segmented Resume Serializers (No changes needed here, they are fine for partial updates) ---
# ResumeBasicInfoSerializer, ResumeLinksSerializer, etc. are okay as they are.

# --- THE MAIN FULL RESUME SERIALIZER (CORRECTED) ---
class FullResumeSerializer(serializers.ModelSerializer):
    talent_id = CustomUserLiteSerializer(read_only=True)
    
    # --- Helper to generate full URLs for file fields ---
    def get_absolute_url(self, obj, field_name):
        request = self.context.get('request')
        file_obj = getattr(obj, field_name, None)
        if request and file_obj and hasattr(file_obj, 'url'):
            return request.build_absolute_uri(file_obj.url)
        return None

    # --- URL fields for reading file locations ---
    profile_photo_url = serializers.SerializerMethodField()
    resume_pdf_url = serializers.SerializerMethodField()
    tenth_result_upload_url = serializers.SerializerMethodField()
    twelfth_result_upload_url = serializers.SerializerMethodField()
    diploma_result_upload_url = serializers.SerializerMethodField()
    degree_result_upload_url = serializers.SerializerMethodField()
    
    def get_profile_photo_url(self, obj):
        return self.get_absolute_url(obj, 'profile_photo')
        
    def get_resume_pdf_url(self, obj):
        return self.get_absolute_url(obj, 'resume_pdf')

    def get_tenth_result_upload_url(self, obj):
        return self.get_absolute_url(obj, 'tenth_result_upload')

    def get_twelfth_result_upload_url(self, obj):
        return self.get_absolute_url(obj, 'twelfth_result_upload')

    def get_diploma_result_upload_url(self, obj):
        return self.get_absolute_url(obj, 'diploma_result_upload')

    def get_degree_result_upload_url(self, obj):
        return self.get_absolute_url(obj, 'degree_result_upload')

    # --- Fields that are TextFields in the model but store JSON strings ---
    # We will use a custom method to deserialize them for GET requests.
    skills = serializers.SerializerMethodField()
    experience = serializers.SerializerMethodField()
    projects = serializers.SerializerMethodField()
    certifications = serializers.SerializerMethodField()
    awards = serializers.SerializerMethodField()
    publications = serializers.SerializerMethodField()
    open_source_contributions = serializers.SerializerMethodField()
    interests = serializers.SerializerMethodField()
    references = serializers.SerializerMethodField()

    def get_json_from_textfield(self, obj, field_name, default_value=None):
        json_string = getattr(obj, field_name, "")
        if not json_string:
            return default_value if default_value is not None else []
        try:
            return json.loads(json_string)
        except (json.JSONDecodeError, TypeError):
            return [json_string] # Return as list with the string if it's not valid JSON

    def get_skills(self, obj): return self.get_json_from_textfield(obj, 'skills')
    def get_experience(self, obj): return self.get_json_from_textfield(obj, 'experience')
    def get_projects(self, obj): return self.get_json_from_textfield(obj, 'projects')
    def get_certifications(self, obj): return self.get_json_from_textfield(obj, 'certifications')
    def get_awards(self, obj): return self.get_json_from_textfield(obj, 'awards')
    def get_publications(self, obj): return self.get_json_from_textfield(obj, 'publications')
    def get_open_source_contributions(self, obj): return self.get_json_from_textfield(obj, 'open_source_contributions')
    def get_interests(self, obj): return self.get_json_from_textfield(obj, 'interests')
    def get_references(self, obj): return self.get_json_from_textfield(obj, 'references')

    class Meta:
        model = Resume
        fields = [
            'id', 'talent_id',
            # Personal Info (URL fields replace raw file fields in output)
            'name', 'email', 'phone', 'profile_photo_url', 'resume_pdf_url',
            'current_location', 'aadhar_number', 'passport_number', 'current_company',
            
            # Links (now includes the new JSONField for professional_links)
            'linkedin_url', 'github_url', 'portfolio_url', 'stackoverflow_url', 'medium_or_blog_url',
            'professional_links',
            
            # Summaries & Preferences
            'summary', 'generated_summary', 'preferences', 'generated_preferences',
            'work_arrangement', 'preferred_location', 'preferred_tech_stack', 'dev_environment',
            'work_preferences', # <-- New JSONField for preferences

            # Legal & Verification
            'work_authorization', 'criminal_record_disclosure', 'document_verification',
            'work_authorizations', # <-- New JSONField for authorizations
            
            # TextFields containing JSON data (handled by SerializerMethodFields above)
            'skills', 'experience', 'projects', 'certifications', 'awards', 'publications',
            'open_source_contributions', 'interests', 'references',
            
            # Other TextFields
            'volunteering_experience', 'extracurriculars', 
            
            # JSONFields (handled directly)
            'languages', 'frameworks_tools', 'diploma_details', 'degree_details',
            'certification_details', 'certification_photos',
            
            # Address Details
            'current_area', 'permanent_area', 'current_city', 'permanent_city',
            'current_district', 'permanent_district', 'current_state', 'permanent_state',
            'current_country', 'permanent_country',

            # Education (URL fields replace raw file fields in output)
            'tenth_board_name', 'tenth_school_name', 'tenth_year_passing', 'tenth_score', 'tenth_result_upload_url',
            'twelfth_board_name', 'twelfth_college_name', 'twelfth_year_passing', 'twelfth_score', 'twelfth_result_upload_url',
            'diploma_course_name', 'diploma_institution_name', 'diploma_year_passing', 'diploma_score', 'diploma_result_upload_url',
            'degree_name', 'degree_institution_name', 'degree_specialization', 'degree_year_passing', 'degree_score', 'degree_result_upload_url',
            
            # Timestamps
            'created_at', 'updated_at',
        ]
        
        # All fields that aren't for input should be read_only
        read_only_fields = [
            'id', 'talent_id', 'created_at', 'updated_at', 
            'profile_photo_url', 'resume_pdf_url', 'tenth_result_upload_url', 
            'twelfth_result_upload_url', 'diploma_result_upload_url', 'degree_result_upload_url',
            'document_verification', 'generated_summary', 'generated_preferences' 
        ]
        
        # --- IMPORTANT: Make file upload fields write-only ---
        # This allows them to be used for input (POST/PUT) but they won't be part of the GET response.
        # The *_url fields are used for the GET response instead.
        extra_kwargs = {
            'profile_photo': {'write_only': True, 'required': False, 'allow_null': True},
            'resume_pdf': {'write_only': True, 'required': False, 'allow_null': True},
            'tenth_result_upload': {'write_only': True, 'required': False, 'allow_null': True},
            'twelfth_result_upload': {'write_only': True, 'required': False, 'allow_null': True},
            'diploma_result_upload': {'write_only': True, 'required': False, 'allow_null': True},
            'degree_result_upload': {'write_only': True, 'required': False, 'allow_null': True},
        }

    def update(self, instance, validated_data):
        # This handles converting incoming list/dict data for TextField-based JSON storage
        # This logic is now mostly handled in the view, but it's good practice to have it here
        # for other potential uses of the serializer.
        for field_name in ['skills', 'experience', 'projects', 'certifications', 'awards', 'publications', 'interests', 'references', 'open_source_contributions']:
            if field_name in validated_data and isinstance(validated_data[field_name], (list, dict)):
                validated_data[field_name] = json.dumps(validated_data[field_name])
        return super().update(instance, validated_data)

# --- JobPostingSerializer (No changes needed) ---
class CompanyNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['company_name', 'logo']

class JobPostingSerializer(serializers.ModelSerializer):
    company = CompanyNameSerializer(read_only=True)
    job_type = serializers.CharField(source='get_job_type_display', read_only=True)
    experience_level = serializers.CharField(source='get_experience_level_display', read_only=True)
    status = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = JobPosting
        fields = [
            'id', 'company', 'title', 'description', 'requirements', 
            'responsibilities', 'location', 'job_type', 'experience_level', 
            'salary_currency', 'salary_min', 'salary_max', 'contact_email', 
            'benefits', 'required_skills', 'visa_sponsorship', 'remote_work', 
            'status', 'posted_date', 'application_deadline', 'is_active', 
            'created_at', 'updated_at'
        ]
        read_only_fields = fields # Correctly makes all fields read-only for talent view


########## vaishnavi's code #################33


from .models import CustomUser, TalentProfile, Resume


#add to the bottom
class TrendingSkillSerializer(serializers.ModelSerializer):
    class Meta:
        # model = TrendingSkill
        fields = ['id', 'skill', 'demand', 'increase', 'priority', 'updated_at']

from rest_framework import serializers

class CareerRoadmapRequestSerializer(serializers.Serializer):
    current_role = serializers.CharField()
    experience_years = serializers.FloatField()
    interests = serializers.CharField()
    target_roles = serializers.ListField(child=serializers.CharField())

 
class SkillGapAnalysisRequestSerializer(serializers.Serializer):
    selected_roles = serializers.ListField(child=serializers.CharField())
################ interview bot serilizer #################33


from .models import MockInterviewResult # ADD THIS IMPORT

class MockInterviewResultSerializer(serializers.ModelSerializer):
    user = serializers.ReadOnlyField(source='user.username') # Display username instead of user ID

    class Meta:
        model = MockInterviewResult
        fields = [
            'id', 'user', 'interview_start_time', 'interview_end_time',
            'position_applied', 'candidate_experience', 'aiml_specialization_input',
            'aiml_specialization', # NEW: Include this field
            'identity_verified', 'malpractice_detected', 'malpractice_reason',
            'global_readiness_score', 'language_proficiency_score', 'language_analysis',
            'communication_overall_score', # NEW: Include this field
            'psychometric_overall_score',  # NEW: Include this field
            'technical_specialization_scores', # NEW: Include this field
            'pre_generated_questions_data', # NEW: Include this field
            'full_qa_transcript', # NEW: Include this field
            'round_analysis_json', 'status', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'user', 'interview_start_time', 'interview_end_time',
            'malpractice_detected', 'malpractice_reason',
            'global_readiness_score', 'language_proficiency_score',
            'communication_overall_score', 'psychometric_overall_score',
            'technical_specialization_scores', 'pre_generated_questions_data',
            'full_qa_transcript', 'round_analysis_json', 'status', 'created_at', 'updated_at'
        ]