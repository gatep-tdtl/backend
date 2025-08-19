# talent_management/serializers.py
import json
from rest_framework import serializers
from .models import CustomUser, ResumeDocument, TalentProfile, Resume
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

    # --- URL fields for reading file locations (This part is correct) ---
    profile_photo_url = serializers.SerializerMethodField()
    resume_pdf_url = serializers.SerializerMethodField()
    tenth_result_upload_url = serializers.SerializerMethodField()
    twelfth_result_upload_url = serializers.SerializerMethodField()
    
    def get_profile_photo_url(self, obj):
        return self.get_absolute_url(obj, 'profile_photo')
        
    def get_resume_pdf_url(self, obj):
        return self.get_absolute_url(obj, 'resume_pdf')

    def get_tenth_result_upload_url(self, obj):
        return self.get_absolute_url(obj, 'tenth_result_upload')

    def get_twelfth_result_upload_url(self, obj):
        return self.get_absolute_url(obj, 'twelfth_result_upload')

    # --- NEW: Custom JSON Field for TextFields storing JSON ---
    # This will handle both serialization (reading from DB) and deserialization (writing to DB).
    class TextFieldAsJSON(serializers.Field):
        def to_representation(self, value):
            if not value:
                return []
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # If it's not valid JSON, return it as a single-item list
                return [value]

        def to_internal_value(self, data):
            # When receiving data from a request, serialize it to a JSON string
            if not isinstance(data, (list, dict)):
                self.fail('invalid')
            return json.dumps(data)

    # Apply the custom field to all TextFields that store JSON
    skills = TextFieldAsJSON()
    experience = TextFieldAsJSON()
    projects = TextFieldAsJSON()
    awards = TextFieldAsJSON()
    publications = TextFieldAsJSON()
    open_source_contributions = TextFieldAsJSON()
    interests = TextFieldAsJSON()
    references = TextFieldAsJSON()

    class Meta:
        model = Resume
        # The fields list now includes all model fields we want to expose.
        # The serializer will automatically handle native JSONFields and our custom TextFieldAsJSON.
        fields = [
            'id', 'talent_id',
            
            # New Fields
            'employee_level', 'is_fresher', 'domain_interest',

            # Personal Info
            'name', 'email', 'phone', 'profile_photo_url', 'resume_pdf_url',
            'current_company',
            
            # Summaries & Preferences
            'summary', 'generated_summary', 'generated_preferences',
            'preferred_location', 'preferred_tech_stack', 'dev_environment',
            
            # Other TextFields that are just strings
            'volunteering_experience', 'extracurriculars', 
            
            # Native JSONFields (handled automatically by ModelSerializer)
            'professional_links',
            'work_preferences',
            'work_authorizations',
            'languages', 
            'diploma_details', 
            'degree_details', 
            'post_graduate_details',
            'certification_details', 
            'certification_photos',
            
            # TextFields storing JSON (handled by our custom field above)
            'skills', 'experience', 'projects', 'awards', 'publications',
            'open_source_contributions', 'interests', 'references',
            
            # Address Details
            'current_area', 'permanent_area', 'current_city', 'permanent_city',
            'current_district', 'permanent_district', 'current_state', 'permanent_state',
            'current_country', 'permanent_country',

            # Education
            'tenth_board_name', 'tenth_school_name', 'tenth_year_passing', 'tenth_score', 'tenth_result_upload_url',
            'twelfth_board_name', 'twelfth_college_name', 'twelfth_year_passing', 'twelfth_score', 'twelfth_result_upload_url',
            
            # Timestamps
            'created_at', 'updated_at',
        ]
        
        # Read-only fields are for output only, they cannot be written to.
        read_only_fields = [
            'id', 'talent_id', 'created_at', 'updated_at', 
            'profile_photo_url', 'resume_pdf_url', 'tenth_result_upload_url', 
            'twelfth_result_upload_url',
            'generated_summary', 'generated_preferences' 
        ]
        
        # This part ensures that when you upload a file, the file data is used for writing,
        # but it won't be included in the read response. The *_url fields are used instead.
        extra_kwargs = {
            'profile_photo': {'write_only': True, 'required': False, 'allow_null': True},
            'resume_pdf': {'write_only': True, 'required': False, 'allow_null': True},
            'tenth_result_upload': {'write_only': True, 'required': False, 'allow_null': True},
            'twelfth_result_upload': {'write_only': True, 'required': False, 'allow_null': True},
        }

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
    
class RoleListSerializer(serializers.Serializer):
    selected_roles = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False
    )
 
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




class ResumeReviewRequestSerializer(serializers.Serializer):
    target_roles = serializers.ListField(
        child=serializers.CharField(max_length=100),
        allow_empty=False,
        min_length=1
    )



class CareerRoadmapRequestSerializer(serializers.Serializer):
    target_roles = serializers.ListField(
        child=serializers.CharField(max_length=100),
        allow_empty=False,
        min_length=1
    )

from django.conf import settings
from urllib.parse import urljoin
from rest_framework import serializers
from .models import ResumeDocument

class ResumeDocumentSerializer(serializers.ModelSerializer):
    """
    Serializer for the ResumeDocument model.
    Handles serialization of document details and provides a full URL for the file.
    """
    document_url = serializers.SerializerMethodField()
    talent_username = serializers.CharField(source='talent.username', read_only=True)

    class Meta:
        model = ResumeDocument
        fields = [
            'id',
            'talent',
            'talent_username',
            'document_type',
            'document_file',  # This field is used for upload (write-only)
            'description',
            'document_url',   # This field is used for response (read-only)
            'uploaded_at'
        ]
        read_only_fields = ['id', 'talent', 'talent_username', 'document_url', 'uploaded_at']
        extra_kwargs = {
            'document_file': {'write_only': True, 'required': True},
            # We make description optional on update, but required on create
            'description': {'required': False, 'allow_blank': True}
        }

    def get_document_url(self, obj):
        """
        Constructs the full, absolute URL for the document file using
        the BASE_MEDIA_URL from settings.py.
        """
        if obj.document_file and hasattr(obj.document_file, 'name'):
            # obj.document_file.name gives you the relative path e.g., "certifications/file.jpg"
            relative_path = obj.document_file.name
            
            # Use urljoin to safely combine the base URL and the relative path
            return urljoin(settings.BASE_MEDIA_URL, relative_path)
            
        return None

    def validate(self, data):
        """
        On PATCH, 'document_file' is not required. The default required=True in extra_kwargs
        applies only to POST.
        """
        # If this is a partial update (PATCH), 'document_file' is not required.
        if self.instance and not self.partial:
             # This logic is mostly handled by DRF, but explicit check can be useful.
             pass

        # For POST requests, ensure 'document_file' is present.
        # This is already handled by 'required': True in extra_kwargs.
        if not self.instance and 'document_file' not in data:
            raise serializers.ValidationError({"document_file": "This field is required for a new upload."})

        return data
    




from .models import MockInterviewResult, SkillsPassport , Resume# Add SkillsPassport

# ... (at the end of the file, before other non-model serializers) ...
class SkillsPassportSerializer(serializers.ModelSerializer):
    # --- FIX #1: Use username as a fallback for the name ---
    talent_name = serializers.SerializerMethodField()
    
    # --- These are fine ---
    role = serializers.CharField(source='source_interview.position_applied', read_only=True)
    location = serializers.CharField(source='user.resumes.first.preferred_location', read_only=True, default="Not Specified")

    # --- FIX #3: Use a SerializerMethodField to reliably get certifications ---
    verified_certifications = serializers.SerializerMethodField()

    class Meta:
        model = SkillsPassport
        fields = [
            'id',
            'status',
            # Additional combined data
            'talent_name',
            'role',
            'location',
            # Fields from SkillsPassport model
            'global_readiness_score',
            'relocation_score',
            'cultural_adaptability_score',
            'communication_skills_score',
            'technical_readiness_score',
            'ai_powered_summary',
            'key_strengths',
            'specialization_scores',
            'frameworks_tools',
            # Data pulled directly from related models
            'verified_certifications', # Now included
            'created_at'
        ]

    def get_talent_name(self, obj):
        """Returns the user's full name, or their username as a fallback."""
        user = obj.user
        full_name = user.get_full_name()
        return full_name if full_name else user.username

    def get_verified_certifications(self, obj):
        """Safely retrieves certification details from the user's resume."""
        try:
            # A user might have multiple resumes, we'll get the latest one.
            resume = obj.user.resumes.order_by('-updated_at').first()
            if resume and resume.certification_details:
                return resume.certification_details
        except Resume.DoesNotExist:
            return []
        return []