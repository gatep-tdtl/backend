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
    # logo = serializers.SerializerMethodField()  # override logo field

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
    applicant_name = serializers.SerializerMethodField()
    preferred_location = serializers.SerializerMethodField()
    talent_resume_latest_url = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            'id',
            'talent',
            'applicant_name',
            'preferred_location',
            'talent_resume_latest_url',
            'application_date',
            'status',
            'status_display',
            'score'
        ]

    def get_applicant_name(self, obj):
        # Assuming obj.talent is a CustomUser
        if obj.talent:
            return f"{obj.talent.first_name} {obj.talent.last_name}".strip()
        return ""

    def get_preferred_location(self, obj):
        # Try to get from related TalentProfile or Resume
        if hasattr(obj.talent, 'talentprofile') and obj.talent.talentprofile:
            return getattr(obj.talent.talentprofile, 'preferred_location', "")
        # Or from latest resume
        resume = getattr(obj.talent, 'resumes', None)
        if resume and resume.exists():
            latest_resume = resume.order_by('-updated_at').first()
            return getattr(latest_resume, 'preferred_location', "")
        return ""

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

# ...existing code...

class InterviewListItemSerializer(serializers.ModelSerializer):
    candidate_name = serializers.SerializerMethodField()
    job_title = serializers.SerializerMethodField()
    experience_level = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    interview_date = serializers.SerializerMethodField()
    interview_time = serializers.SerializerMethodField()
    interview_mode = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()
    notes = serializers.SerializerMethodField()

    class Meta:
        model = Interview
        fields = [
            'id',
            'candidate_name',
            'job_title',
            'experience_level',
            'location',
            'interview_date',
            'interview_time',
            'interview_mode',
            'status',
            'skills',
            'notes',
        ]

    def get_candidate_name(self, obj):
        # Assuming obj.application.talent has first_name and last_name
        user = getattr(obj.application.talent, 'user', obj.application.talent)
        return f"{user.first_name} {user.last_name}".strip() or user.username

    def get_job_title(self, obj):
        return obj.application.job_posting.title if obj.application and obj.application.job_posting else ""

    def get_experience_level(self, obj):
        return obj.application.job_posting.get_experience_level_display() if obj.application and obj.application.job_posting else ""

    def get_location(self, obj):
        return obj.location if obj.location else ""

    def get_interview_date(self, obj):
        return obj.scheduled_at.date().isoformat() if obj.scheduled_at else ""

    def get_interview_time(self, obj):
        return obj.scheduled_at.strftime("%H:%M") if obj.scheduled_at else ""

    def get_interview_mode(self, obj):
        return obj.get_interview_type_display() if obj.interview_type else ""

    def get_status(self, obj):
        return obj.interview_status.lower() if obj.interview_status else ""

    def get_skills(self, obj):
        # Try to get from job posting required_skills
        if obj.application and obj.application.job_posting and obj.application.job_posting.required_skills:
            return obj.application.job_posting.required_skills
        return []

    def get_notes(self, obj):
        return obj.feedback or ""




class TalentInterviewListSerializer(serializers.ModelSerializer):
    company_name = serializers.SerializerMethodField()
    company_profile = serializers.SerializerMethodField()
    location = serializers.CharField()
    skills = serializers.SerializerMethodField()
    status = serializers.CharField(source='get_interview_status_display')
    date = serializers.SerializerMethodField()
    time = serializers.SerializerMethodField()
    type = serializers.CharField(source='get_interview_type_display')

    class Meta:
        model = Interview
        fields = [
            'id', 'company_name', 'company_profile', 'location', 'skills',
            'status', 'date', 'time', 'type'
        ]

    def get_company_name(self, obj):
        return obj.application.job_posting.company.company_name

    def get_company_profile(self, obj):
        # You can return a nested CompanySerializer or just the company id/url
        company = obj.application.job_posting.company
        return {
            "id": company.id,
            "company_name": company.company_name,
            "description": company.description,
            "logo": self.context['request'].build_absolute_uri(company.logo.url) if company.logo else None,
            "industry": company.industry,
            "website": company.website,
        }

    def get_skills(self, obj):
        return obj.application.job_posting.required_skills

    def get_date(self, obj):
        return obj.scheduled_at.date()

    def get_time(self, obj):
        return obj.scheduled_at.time()
    


class TalentJobMatchScoreSerializer(serializers.Serializer):
    job_id = serializers.IntegerField()
    application_id = serializers.IntegerField()
    job_required_skills = serializers.ListField(child=serializers.CharField())
    user_skills = serializers.ListField(child=serializers.CharField())
    matching_percentage = serializers.FloatField()