# talent_management/serializers.py
import json # Ensure json is imported for dumping JSONField data
from rest_framework import serializers
from .models import CustomUser, TalentProfile, Resume 
# IMPORTANT: Import JobPosting, Company from employer_management.models
from employer_management.models import JobPosting, Company # Now importing Company and JobPosting
# No need to import JobType, ExperienceLevel directly here if they are only used as choices on JobPosting.

class CustomUserLiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'phone_number', 'first_name', 'last_name']

class TalentProfileLiteSerializer(serializers.ModelSerializer):
    user = CustomUserLiteSerializer(read_only=True)
    class Meta:
        model = TalentProfile
        fields = ['user', 'resume_url', 'skills', 'portfolio_url', 'profile_summary']
        read_only_fields = ['user']


class ResumeBasicInfoSerializer(serializers.ModelSerializer):
    profile_photo = serializers.ImageField(required=False, allow_null=True)
    
    class Meta:
        model = Resume
        fields = [
            'name', 'email', 'phone', 'profile_photo', 'summary',
            'current_location', 'aadhar_number', 'passport_number',
            'current_company'
        ]
        read_only_fields = ['talent_id']

class ResumeLinksSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resume
        fields = [
            'linkedin_url', 'github_url', 'portfolio_url', 'stackoverflow_url',
            'medium_or_blog_url'
        ]
        read_only_fields = ['talent_id']

class ResumePreferencesSerializer(serializers.ModelSerializer):
    # The actual preferences field in your model is TextField, so it should be handled as a string.
    # If you intend to store JSON in it, it should be a JSONField.
    # For now, I'll assume your view handles json.dumps for preferences
    # and this serializer will treat it as a string.
    
    # These were TextField in your model, they should probably be JSONField if they are lists/dicts
    # For now, assume they are handled as strings that contain JSON.
    preferred_tech_stack = serializers.CharField(required=False, allow_blank=True) 
    dev_environment = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Resume
        fields = [
            'preferences', 'work_arrangement', 'preferred_location',
            'preferred_tech_stack', 'dev_environment',
        ]
        read_only_fields = ['talent_id']

class ResumeExperienceProjectsSerializer(serializers.ModelSerializer):
    experience = serializers.CharField(required=False, allow_blank=True) # TextField
    projects = serializers.CharField(required=False, allow_blank=True)   # TextField

    class Meta:
        model = Resume
        fields = [
            'experience', 'projects', 'open_source_contributions'
        ]
        read_only_fields = ['talent_id']

class ResumeSkillsCertsInterestsSerializer(serializers.ModelSerializer):
    skills = serializers.CharField(required=False, allow_blank=True)         # TextField
    certifications = serializers.CharField(required=False, allow_blank=True) # TextField
    interests = serializers.CharField(required=False, allow_blank=True)      # TextField
    languages = serializers.JSONField(required=False)                        # JSONField

    class Meta:
        model = Resume
        fields = [
            'skills', 'certifications', 'interests', 'languages'
        ]
        read_only_fields = ['talent_id']

class ResumeEducationSerializer(serializers.ModelSerializer):
    tenth_result_upload = serializers.FileField(required=False, allow_null=True)
    twelfth_result_upload = serializers.FileField(required=False, allow_null=True)
    diploma_result_upload = serializers.FileField(required=False, allow_null=True)
    degree_result_upload = serializers.FileField(required=False, allow_null=True)

    class Meta:
        model = Resume
        fields = [
            'tenth_board_name', 'tenth_school_name', 'tenth_year_passing', 'tenth_score', 'tenth_result_upload',
            'twelfth_board_name', 'twelfth_college_name', 'twelfth_year_passing', 'twelfth_score', 'twelfth_result_upload',
            'diploma_course_name', 'diploma_institution_name', 'diploma_year_passing', 'diploma_score', 'diploma_result_upload',
            'degree_name', 'degree_institution_name', 'degree_specialization', 'degree_year_passing', 'degree_score', 'degree_result_upload'
        ]
        read_only_fields = ['talent_id']

class ResumeOtherDetailsSerializer(serializers.ModelSerializer):
    volunteering_experience = serializers.CharField(required=False, allow_blank=True) # TextField
    extracurriculars = serializers.CharField(required=False, allow_blank=True)      # TextField
    references = serializers.CharField(required=False, allow_blank=True)           # TextField
    awards = serializers.CharField(required=False, allow_blank=True)               # TextField
    publications = serializers.CharField(required=False, allow_blank=True)         # TextField

    class Meta:
        model = Resume
        fields = [
            'volunteering_experience', 'extracurriculars', 'references', 'awards', 'publications',
            'work_authorization', 'criminal_record_disclosure', 'document_verification'
        ]
        read_only_fields = ['talent_id']


class FullResumeSerializer(serializers.ModelSerializer):
    talent_id = CustomUserLiteSerializer(read_only=True)
    profile_photo_url = serializers.SerializerMethodField()
    resume_pdf_url = serializers.SerializerMethodField()
    tenth_result_upload_url = serializers.SerializerMethodField()
    twelfth_result_upload_url = serializers.SerializerMethodField()
    diploma_result_upload_url = serializers.SerializerMethodField()
    degree_result_upload_url = serializers.SerializerMethodField()

    def get_profile_photo_url(self, obj):
        if obj.profile_photo and hasattr(obj.profile_photo, 'url'):
            request = self.context.get('request')
            if request is not None:
                return request.build_absolute_uri(obj.profile_photo.url)
        return None

    def get_resume_pdf_url(self, obj):
        if obj.resume_pdf and hasattr(obj.resume_pdf, 'url'):
            request = self.context.get('request')
            if request is not None:
                return request.build_absolute_uri(obj.resume_pdf.url)
        return None

    def get_tenth_result_upload_url(self, obj):
        if obj.tenth_result_upload and hasattr(obj.tenth_result_upload, 'url'):
            request = self.context.get('request')
            if request is not None:
                return request.build_absolute_uri(obj.tenth_result_upload.url)
        return None

    def get_twelfth_result_upload_url(self, obj):
        if obj.twelfth_result_upload and hasattr(obj.twelfth_result_upload, 'url'):
            request = self.context.get('request')
            if request is not None:
                return request.build_absolute_uri(obj.twelfth_result_upload.url)
        return None

    def get_diploma_result_upload_url(self, obj):
        if obj.diploma_result_upload and hasattr(obj.diploma_result_upload, 'url'):
            request = self.context.get('request')
            if request is not None:
                return request.build_absolute_uri(obj.diploma_result_upload.url)
        return None

    def get_degree_result_upload_url(self, obj):
        if obj.degree_result_upload and hasattr(obj.degree_result_upload, 'url'):
            request = self.context.get('request')
            if request is not None:
                return request.build_absolute_uri(obj.degree_result_upload.url)
        return None

    class Meta:
        model = Resume
        fields = [
            'id', 'talent_id', 
            'name', 'email', 'phone', 'profile_photo', 'profile_photo_url', 'resume_pdf', 'resume_pdf_url',
            'linkedin_url', 'github_url', 'portfolio_url', 'stackoverflow_url', 'medium_or_blog_url',
            'summary', 'preferences', 'work_arrangement', 'preferred_location', 'preferred_tech_stack', 
            'dev_environment', 'current_location', 'aadhar_number', 'passport_number', 'current_company',
            'work_authorization', 'criminal_record_disclosure', 'document_verification',
            'references', 'awards', 'publications', 'open_source_contributions',
            'volunteering_experience', 'extracurriculars', 'skills', 'experience',
            'projects', 'certifications', 'interests', 'languages',
            'tenth_board_name', 'tenth_school_name', 'tenth_year_passing', 'tenth_score', 'tenth_result_upload', 'tenth_result_upload_url',
            'twelfth_board_name', 'twelfth_college_name', 'twelfth_year_passing', 'twelfth_score', 'twelfth_result_upload', 'twelfth_result_upload_url',
            'diploma_course_name', 'diploma_institution_name', 'diploma_year_passing', 'diploma_score', 'diploma_result_upload', 'diploma_result_upload_url',
            'degree_name', 'degree_institution_name', 'degree_specialization', 'degree_year_passing', 'degree_score', 'degree_result_upload', 'degree_result_upload_url',
            'created_at', 'updated_at', 'generated_summary', 'generated_preferences'
        ]
        read_only_fields = [
            'id', 'talent_id', 'created_at', 'updated_at', 
            'profile_photo_url', 'resume_pdf_url', 'tenth_result_upload_url', 
            'twelfth_result_upload_url', 'diploma_result_upload_url', 'degree_result_upload_url',
            'document_verification', 'generated_summary', 'generated_preferences'
        ]

    def update(self, instance, validated_data):
        for field_name in ['skills', 'experience', 'projects', 'certifications', 'awards', 'publications', 'interests', 'references', 'preferences', 'open_source_contributions', 'generated_preferences']:
            if field_name in validated_data and isinstance(validated_data[field_name], (list, dict)):
                validated_data[field_name] = json.dumps(validated_data[field_name])
        return super().update(instance, validated_data)


# --- Re-defined JobPostingSerializer using the actual JobPosting model from employer_management ---
class CompanyNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['company_name', 'logo'] # Include logo for display

class JobPostingSerializer(serializers.ModelSerializer):
    # Use CompanyNameSerializer to get company_name and logo
    company = CompanyNameSerializer(read_only=True) 
    
    # These fields are choices, so we might want to display their human-readable values
    job_type = serializers.CharField(source='get_job_type_display', read_only=True)
    experience_level = serializers.CharField(source='get_experience_level_display', read_only=True)
    status = serializers.CharField(source='get_status_display', read_only=True) # Also include status display

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
        # Adjust read_only_fields to correctly reflect what's truly read-only
        # from a talent's perspective when viewing a job posting.
        read_only_fields = [
            'id', 'company', 'title', 'description', 'requirements', 
            'responsibilities', 'location', 'job_type', 'experience_level', 
            'salary_currency', 'salary_min', 'salary_max', 'contact_email', 
            'benefits', 'required_skills', 'visa_sponsorship', 'remote_work', 
            'status', 'posted_date', 'application_deadline', 'is_active', 
            'created_at', 'updated_at'
        ]
