from rest_framework import serializers
from .models import Company, JobPosting, Application, Interview, SavedJob # Ensure SavedJob is imported

# Import CustomUser, TalentProfile from talent_management.models
from talent_management.models import CustomUser, TalentProfile
# Import FullResumeSerializer from talent_management.serializers for detailed application views
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
        # Fields relevant for a quick overview of the talent profile
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
        # Robustness: Check if request and user exist and user_role is defined
        if request and request.user.is_authenticated and \
           hasattr(request.user, 'user_role') and request.user.user_role == 'EMPLOYER':
            employer_company = getattr(request.user, 'employer_company', None)
            if employer_company:
                validated_data['company'] = employer_company
            else:
                raise serializers.ValidationError("Employer user has no associated company.")
        # If 'company' is not in validated_data and it's required by the model,
        # Django's model validation will usually catch this. 
        # The `pass` here means no specific serializer-level error is raised
        # if the user isn't an employer AND hasn't provided a company.
        pass

        return super().create(validated_data)


# --- Application Serializer (General purpose, used by Talent to create/list their own) ---
class ApplicationSerializer(serializers.ModelSerializer):
    talent_details = SimpleUserSerializer(source='talent.user', read_only=True) # Access talent's CustomUser details
    job_posting_details = JobPostingSerializer(source='job_posting', read_only=True)
    status_display = serializers.SerializerMethodField()
    

    class Meta:
        model = Application
        fields = [
            'id', 'job_posting', 'job_posting_details', 'talent', 'talent_details',
            'cover_letter', 'resume', 'application_date', 'status', 'status_display',
            'notes', 'created_at','interviews', 'updated_at', 'score' 
        ]
        read_only_fields = ['talent', 'application_date', 'created_at', 'updated_at', 'score'] # Talent cannot directly set score

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
    

# --- Saved Job Serializers ---
class SavedJobSerializer(serializers.ModelSerializer):
    # Nested serializer to display the full job details when listing saved jobs
    job_posting = JobPostingSerializer(read_only=True) 

    class Meta:
        model = SavedJob
        fields = ['id', 'job_posting', 'saved_at']
        read_only_fields = ['id', 'job_posting', 'saved_at'] # Talent cannot directly set these

# Serializer for creating/deleting SavedJob instances (expects only job_posting ID)
class SaveJobActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedJob
        fields = ['job_posting'] # Only need job_posting ID to save/unsave


# --- NEW: Employer Application Management Serializers ---

class ApplicationListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing applications for an employer, providing key details
    of the talent and application status for a specific job posting.
    """
    talent_user_details = SimpleUserSerializer(source='talent.user', read_only=True)
    talent_profile_summary = serializers.CharField(source='talent.profile_summary', read_only=True)
    
    # Method field to get the URL of the talent's latest resume PDF
    talent_resume_latest_url = serializers.SerializerMethodField()
    
    status_display = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            'id', 'talent', 'talent_user_details', 'talent_profile_summary',
            'talent_resume_latest_url', 
            'application_date', 'status', 'status_display', 'score' # score for match percentage
        ]
        read_only_fields = fields # All fields read-only for listing

    def get_talent_resume_latest_url(self, obj):
        # Access the related_name 'resumes' from TalentProfile to Resume model
        # Assuming `obj.talent` is a TalentProfile instance
        if hasattr(obj.talent, 'resumes') and obj.talent.resumes.exists():
            # Get the most recently updated resume associated with this talent profile
            latest_resume = obj.talent.resumes.order_by('-updated_at').first()
            if latest_resume and latest_resume.resume_pdf and hasattr(latest_resume.resume_pdf, 'url'):
                request = self.context.get('request')
                if request is not None:
                    return request.build_absolute_uri(latest_resume.resume_pdf.url)
        return None

    def get_status_display(self, obj):
        return obj.get_status_display()


class ApplicationDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed view of a single application for an employer.
    Includes full resume details and related interviews.
    """
    talent_user_details = SimpleUserSerializer(source='talent.user', read_only=True)
    # Embed the full resume serializer from talent_management.
    # Assumes TalentProfile has a related_name 'resumes' to the Resume model (e.g., resumes.all()).
    # `many=True` is used because a TalentProfile might have multiple resumes, even if only one is current.
    # The FullResumeSerializer will handle selecting the relevant one or displaying all if configured.
    talent_full_resume = FullResumeSerializer(source='talent.resumes.all', many=True, read_only=True) 
    
    # List related interviews for this application (assuming Application model has a related_name 'interviews' to Interview model)
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