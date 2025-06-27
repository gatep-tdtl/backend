from rest_framework import serializers
from .models import Company, JobPosting, Application, Interview, SavedJob
from talent_management.models import CustomUser, TalentProfile
from talent_management.serializers import FullResumeSerializer


# Optional: Basic User Serializer for nested display
class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'user_role']


# Serializer for a basic view of TalentProfile, for use in application listing
class TalentProfileBasicSerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True)
    class Meta:
        model = TalentProfile
        fields = ['id', 'user', 'profile_summary', 'skills']


# --- Company Serializer ---
class CompanySerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True)
    user_id = serializers.ReadOnlyField(source='user.id')

    class Meta:
        model = Company
        fields = [
            'id', 'user', 'user_id', 'company_name', 'description', 'industry',
            'website', 'headquarters', 'size', 'contact_email', 'phone_number',
            'logo', 'founded_date', 'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'user_id', 'created_at', 'updated_at']

# --- Job Posting Serializer ---
class JobPostingSerializer(serializers.ModelSerializer):
    status_display = serializers.SerializerMethodField()
    job_type_display = serializers.SerializerMethodField()
    experience_level_display = serializers.SerializerMethodField()
    company_details = CompanySerializer(source='company', read_only=True)

    class Meta:
        model = JobPosting
        fields = [
            'id', 'company', 'company_details', 'title', 'description', 'requirements', 'responsibilities',
            'location', 'job_type', 'job_type_display', 
            'experience_level', 'experience_level_display', 
            'salary_currency', 'salary_min', 'salary_max',
            'contact_email', 'benefits', 'required_skills', 'visa_sponsorship', 'remote_work',
            'status', 'status_display', 
            'application_deadline', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at'] 

    def get_status_display(self, obj):
        return obj.get_status_display()

    def get_job_type_display(self, obj):
        return obj.get_job_type_display()
    
    def get_experience_level_display(self, obj): 
        return obj.get_experience_level_display()
        
    def create(self, validated_data):
        request = self.context.get('request', None)
        if request and request.user.is_authenticated and hasattr(request.user, 'user_role') and request.user.user_role == 'EMPLOYER':
            employer_company = getattr(request.user, 'employer_company', None)
            if employer_company:
                validated_data['company'] = employer_company
            else:
                raise serializers.ValidationError("Employer user has no associated company.")
        elif 'company' not in validated_data:
            raise serializers.ValidationError({"company": "This field is required if not auto-assigned by employer."})
        return super().create(validated_data)

# --- Application Serializer (General purpose, used by Talent to create/list their own) ---
class ApplicationSerializer(serializers.ModelSerializer):
    talent_details = SimpleUserSerializer(source='talent.user', read_only=True)
    job_posting_details = JobPostingSerializer(source='job_posting', read_only=True)
    status_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Application
        fields = [
            'id', 'job_posting', 'job_posting_details', 'talent', 'talent_details',
            'cover_letter', 'resume', 'application_date', 'status', 'status_display',
            'notes', 'created_at', 'updated_at', 'score'
        ]
        read_only_fields = ['talent', 'application_date', 'created_at', 'updated_at', 'score']

    def get_status_display(self, obj):
        return obj.get_status_display()


# --- Interview Serializer ---
class InterviewSerializer(serializers.ModelSerializer):
    application_details = ApplicationSerializer(source='application', read_only=True)
    interviewer_details = SimpleUserSerializer(source='interviewer', read_only=True)
    interview_status_display = serializers.SerializerMethodField()

    class Meta:
        model = Interview
        fields = [
            'id', 'application', 'application_details', 'interviewer', 'interviewer_details',
            'interview_type', 'scheduled_at', 'location', 'interview_status', 'interview_status_display',
            'feedback', 'score', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_interview_status_display(self, obj):
        return obj.get_interview_status_display()


    class Meta:
        model = Interview
        fields = [
            'id', 'application', 'application_details', 'interviewer', 'interviewer_details',
            'interview_type', 'scheduled_at', 'location', 'interview_status', 'interview_status_display',
            'feedback', 'score', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_interview_status_display(self, obj):
        return obj.get_interview_status_display()
    

# --- Saved Job Serializers ---
class SavedJobSerializer(serializers.ModelSerializer):
    job_posting = JobPostingSerializer(read_only=True)
    class Meta:
        model = SavedJob
        fields = ['id', 'job_posting', 'saved_at']
        read_only_fields = ['id', 'job_posting', 'saved_at']

class SaveJobActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedJob
        fields = ['job_posting']

# --- NEW: Employer Application Management Serializers ---
class ApplicationListSerializer(serializers.ModelSerializer):
    talent_user_details = SimpleUserSerializer(source='talent.user', read_only=True)
    talent_profile_summary = serializers.CharField(source='talent.profile_summary', read_only=True)
    talent_resume_latest_url = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            'id', 'talent', 'talent_user_details', 'talent_profile_summary',
            'talent_resume_latest_url', 
            'application_date', 'status', 'status_display', 'score'
        ]
        read_only_fields = fields

    def get_talent_resume_latest_url(self, obj):
        if hasattr(obj.talent, 'resumes') and obj.talent.resumes.exists():
            latest_resume = obj.talent.resumes.order_by('-updated_at').first()
            if latest_resume and latest_resume.resume_pdf and hasattr(latest_resume.resume_pdf, 'url'):
                request = self.context.get('request')
                if request is not None:
                    return request.build_absolute_uri(latest_resume.resume_pdf.url)
        return None

    def get_status_display(self, obj):
        return obj.get_status_display()

class ApplicationDetailSerializer(serializers.ModelSerializer):
    talent_user_details = SimpleUserSerializer(source='talent.user', read_only=True)
    talent_full_resume = FullResumeSerializer(source='talent.resumes.all', many=True, read_only=True)
    interviews = InterviewSerializer(many=True, read_only=True)
    job_posting_details = JobPostingSerializer(source='job_posting', read_only=True)
    status_display = serializers.SerializerMethodField()


    class Meta:
        model = Application
        fields = [
            'id', 'job_posting', 'job_posting_details', 'talent', 'talent_user_details',
            'talent_full_resume', # Full resume details
            'cover_letter', 'resume', # Original cover letter/resume upload (if direct file field on Application)
            'application_date', 'status', 'status_display', 'score', 'notes',
            'interviews', # Include related interviews
            'created_at', 'updated_at'
        ]
        # All fields read-only for a detail view retrieved by an employer.
        # Updates to application status or notes would typically be handled via a PATCH/PUT endpoint
        # with a different, more specific serializer if needed.
        read_only_fields = fields 

    def get_status_display(self, obj):
        return obj.get_status_display()

    def get_serializer_context(self):
        """
        Ensures 'request' is passed to the serializer context for nested serializers
        (e.g., FullResumeSerializer) to generate absolute URLs for file fields.
        """
        context = super().get_serializer_context()
        if 'request' in self.context:
            context['request'] = self.context['request']
        return context
