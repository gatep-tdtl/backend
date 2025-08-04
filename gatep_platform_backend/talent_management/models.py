# talent_management/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import random
import string
from decimal import Decimal # Import for DecimalField
from decimal import InvalidOperation # Import for handling potential errors in Decimal conversion


# --- USER ROLES ---
class UserRole(models.TextChoices):
    ADMIN = 'ADMIN', _('Admin')
    TALENT = 'TALENT', _('Talent')
    EMPLOYER = 'EMPLOYER', _('Employer')

class CustomUser(AbstractUser):
    email = models.EmailField(_('email address'), blank=True)
    user_role = models.CharField(
        max_length=50,
        choices=UserRole.choices,
        default=UserRole.TALENT,
        verbose_name=_('User Role')
    )
    is_talent_role = models.BooleanField(default=True)
    is_employer_role = models.BooleanField(default=False)

    otp = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True, unique=True)

    def generate_otp(self):
        self.otp = ''.join(random.choices(string.digits, k=6))
        self.otp_created_at = timezone.now()
        self.save()
        return self.otp

    def is_otp_valid(self):
        if self.otp and self.otp_created_at:
            return (timezone.now() - self.otp_created_at) < timezone.timedelta(minutes=5)
        return False

    def save(self, *args, **kwargs):
        self.is_talent_role = (self.user_role == UserRole.TALENT)
        self.is_employer_role = (self.user_role == UserRole.EMPLOYER)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.user_role})"
    

# --- PROFILES ---
class TalentProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, primary_key=True)
    resume_url = models.URLField(blank=True, null=True)
    skills = models.TextField(blank=True, null=True)
    portfolio_url = models.URLField(blank=True, null=True)

    def __str__(self):
        return f'{self.user.username} (Talent Profile)'

# --- NEW CHOICES FOR EMPLOYER INDUSTRY (Defined here for potential reuse or clarity) ---
class IndustryChoices(models.TextChoices):
    IT_SOFTWARE = 'IT_SOFTWARE', _('IT/Software')
    FINANCE = 'FINANCE', _('Finance')
    HEALTHCARE = 'HEALTHCARE', _('Healthcare')
    EDUCATION = 'EDUCATION', _('Education')
    MANUFACTURING = 'MANUFACTURING', _('Manufacturing')
    RETAIL = 'RETAIL', _('Retail')
    CONSULTING = 'CONSULTING', _('Consulting')
    MEDIA_ENTERTAINMENT = 'MEDIA_ENTERTAINMENT', _('Media & Entertainment')
    HOSPITALITY = 'HOSPITALITY', _('Hospitality')
    CONSTRUCTION = 'CONSTRUCTION', _('Construction')
    GOVERNMENT = 'GOVERNMENT', _('Government')
    NON_PROFIT = 'NON_PROFIT', _('Non-Profit')
    E_COMMERCE = 'E_COMMERCE', _('E-commerce') # Added more common industries
    TELECOMMUNICATIONS = 'TELECOMMUNICATIONS', _('Telecommunications')
    AUTOMOTIVE = 'AUTOMOTIVE', _('Automotive')
    PHARMACEUTICALS = 'PHARMACEUTICALS', _('Pharmaceuticals')
    ENERGY = 'ENERGY', _('Energy')
    TRANSPORTATION_LOGISTICS = 'TRANSPORTATION_LOGISTICS', _('Transportation & Logistics')
    FOOD_BEVERAGE = 'FOOD_BEVERAGE', _('Food & Beverage')
    REAL_ESTATE = 'REAL_ESTATE', _('Real Estate')
    MARKETING_ADVERTISING = 'MARKETING_ADVERTISING', _('Marketing & Advertising')
    OTHER = 'OTHER', _('Other')


class EmployerProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, primary_key=True)
    company_name = models.CharField(max_length=255)
    website_url = models.URLField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    industry = models.CharField(
        max_length=100,
        choices=IndustryChoices.choices, # <--- UPDATED TO DROPDOWN
        blank=True,
        null=True,
        verbose_name=_('Industry')
    )

    def __str__(self):
        return f'{self.user.username} (Employer Profile - {self.company_name})'

# --- NEW CHOICES FOR WORK ARRANGEMENT ---
class WorkArrangementChoices(models.TextChoices):
    FULL_TIME = 'FULL_TIME', _('Full-time')
    PART_TIME = 'PART_TIME', _('Part-time')
    CONTRACT = 'CONTRACT', _('Contract')
    TEMPORARY = 'TEMPORARY', _('Temporary')
    FREELANCE = 'FREELANCE', _('Freelance')
    INTERNSHIP = 'INTERNSHIP', _('Internship')
    VOLUNTEER = 'VOLUNTEER', _('Volunteer')
    GIG = 'GIG', _('Gig')
    REMOTE = 'REMOTE', _('Remote') # Can be a work arrangement too
    HYBRID = 'HYBRID', _('Hybrid')


# --- NEW CHOICES FOR DOCUMENT VERIFICATION STATUS ---
class DocumentVerificationStatus(models.TextChoices):
    INCOMPLETE = 'INCOMPLETE', _('Incomplete')
    PENDING_REVIEW = 'PENDING_REVIEW', _('Pending Review')
    VERIFIED = 'VERIFIED', _('Verified')
    REJECTED = 'REJECTED', _('Rejected')
    NOT_APPLICABLE = 'NOT_APPLICABLE', _('Not Applicable')


# --- RESUME ---
class Resume(models.Model):
    # Core personal info
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    talent_id = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='resumes', blank=True, null=True)
    
    # Profile Photo field (already correct)
    profile_photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)
    resume_pdf = models.FileField(upload_to='resumes/', blank=True, null=True)

    # Links
    linkedin_url = models.URLField(blank=True, default="")
    github_url = models.URLField(blank=True, default="")
    portfolio_url = models.URLField(blank=True, default="")
    stackoverflow_url = models.URLField(blank=True, default="")
    medium_or_blog_url = models.URLField(blank=True, default="")

    frameworks_tools = models.JSONField(blank=True, default=list, verbose_name="Frameworks & Tools")

    # Summaries & Preferences 
    summary = models.TextField(blank=True, default="")
    generated_summary = models.TextField(blank=True, default="")
    preferences = models.TextField(blank=True, default="")
    
    work_arrangement = models.CharField( # <--- UPDATED TO DROPDOWN
        max_length=50,
        choices=WorkArrangementChoices.choices,
        blank=True,
        null=True, # Allowing null if not specified by user
        verbose_name=_('Preferred Work Arrangement')
    )
    preferred_location = models.CharField(max_length=100, blank=True, default="")
    preferred_tech_stack = models.TextField(blank=True, default="")
    dev_environment = models.TextField(blank=True, default="")
    
    current_location = models.CharField(max_length=100, blank=True, default="Not Provided")
    aadhar_number = models.CharField(max_length=12, blank=True, default="Not Provided")
    passport_number = models.CharField(max_length=20, blank=True, default="Not Provided")
    current_company = models.CharField(max_length=100, blank=True, default="Not Provided")

    # Legal & Verification
    work_authorization = models.TextField(blank=True, default="")
    criminal_record_disclosure = models.TextField(blank=True, default="")
    document_verification = models.CharField( # <--- UPDATED TO DROPDOWN
        max_length=50,
        choices=DocumentVerificationStatus.choices,
        default=DocumentVerificationStatus.INCOMPLETE,
        verbose_name=_('Document Verification Status')
    )
    generated_preferences = models.TextField(blank=True, default="")

    # List-based fields (Stored as JSON strings in TextField) - For these, if you want dropdowns, you'd usually have a separate model or a fixed set of choices. For now, they remain TextField.
    references = models.TextField(blank=True, default="")
    awards = models.TextField(blank=True, default="")
    publications = models.TextField(blank=True, default="")
    open_source_contributions = models.TextField(blank=True, default="")
    volunteering_experience = models.TextField(blank=True, default="")
    extracurriculars = models.TextField(blank=True, default="")

    skills = models.TextField(blank=True, default="")
    experience = models.TextField(blank=True, default="")
    projects = models.TextField(blank=True, default="")
    certifications = models.TextField(blank=True, default="")
    interests = models.TextField(blank=True, default="")

    languages = models.JSONField(blank=True, default=dict) # Kept as JSONField

    # --- EDUCATION FIELDS (INDIVIDUAL FIELDS AND FILE UPLOADS) ---
    # 10th Boards
    tenth_board_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('10th Board Name'))
    tenth_school_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('10th School Name'))
    tenth_year_passing = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('10th Year Passing'))
    tenth_score = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('10th Score/Grade'))
    tenth_result_upload = models.FileField(upload_to='education_results/10th/', blank=True, null=True, verbose_name=_('10th Result Upload'))

    # 12th Boards
    twelfth_board_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('12th Board Name'))
    twelfth_college_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('12th College Name'))
    twelfth_year_passing = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('12th Year Passing'))
    twelfth_score = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('12th Score/Grade'))
    twelfth_result_upload = models.FileField(upload_to='education_results/12th/', blank=True, null=True, verbose_name=_('12th Result Upload'))

    # Diploma
    diploma_course_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('Diploma Course Name'))
    diploma_institution_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('Diploma Institution Name'))
    diploma_year_passing = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('Diploma Year Passing'))
    diploma_score = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('Diploma Score/Grade'))
    diploma_result_upload = models.FileField(upload_to='education_results/diploma/', blank=True, null=True, verbose_name=_('Diploma Result Upload'))

    # Degree (e.g., Bachelor's, Master's, Ph.D.)
    degree_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('Degree Name'))
    degree_institution_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('Degree Institution Name'))
    degree_specialization = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('Degree Specialization'))
    degree_year_passing = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('Degree Year Passing'))
    degree_score = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('Degree Score/Grade'))
    degree_result_upload = models.FileField(upload_to='education_results/degree/', blank=True, null=True, verbose_name=_('Degree Result Upload'))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Soft Delete Field
    is_deleted = models.BooleanField(default=False)



    current_area = models.CharField(max_length=255, blank=True, default="")
    permanent_area = models.CharField(max_length=255, blank=True, default="")
    current_city = models.CharField(max_length=100, blank=True, default="")
    permanent_city = models.CharField(max_length=100, blank=True, default="")
    current_district = models.CharField(max_length=100, blank=True, default="")
    permanent_district = models.CharField(max_length=100, blank=True, default="")
    current_state = models.CharField(max_length=100, blank=True, default="")
    permanent_state = models.CharField(max_length=100, blank=True, default="")
    current_country = models.CharField(max_length=100, blank=True, default="")
    permanent_country = models.CharField(max_length=100, blank=True, default="")

    # Diploma and Degree details (multiple)
    diploma_details = models.JSONField(blank=True, default=list, verbose_name="Diploma Details")
    degree_details = models.JSONField(blank=True, default=list, verbose_name="Degree Details")

    # Certification details (multiple, with photos)
    certification_details = models.JSONField(blank=True, default=list, verbose_name="Certification Details")
    certification_photos = models.JSONField(blank=True, default=list, verbose_name="Certification Photos")

    # Work preference (multiple)
    work_preferences = models.JSONField(blank=True, default=list, verbose_name="Work Preferences")

    # Work authorization (multiple)
    work_authorizations = models.JSONField(blank=True, default=list, verbose_name="Work Authorizations")

    # Professional links (multiple)
    professional_links = models.JSONField(blank=True, default=list, verbose_name="Professional Links")
    def __str__(self):
        return f"{self.name} ({self.email})"

    class Meta:
        verbose_name = "Resume"
        verbose_name_plural = "Resumes"

# --- JOB LISTING (NEW MODEL) ---
class JobListing(models.Model):
    JOB_STATUS_CHOICES = [
        ('PENDING', 'Pending Verification'),
        ('VERIFIED', 'Verified & Active'),
        ('REJECTED', 'Rejected'),
        ('CLOSED', 'Closed'),
        ('EXPIRED', 'Expired'),
    ]

    EMPLOYMENT_TYPE_CHOICES = [
        ('FULL_TIME', 'Full-time'),
        ('PART_TIME', 'Part-time'),
        ('CONTRACT', 'Contract'),
        ('TEMPORARY', 'Temporary'),
        ('INTERNSHIP', 'Internship'),
        ('VOLUNTEER', 'Volunteer'),
    ]

    WORK_LOCATION_TYPE_CHOICES = [
        ('REMOTE', 'Remote'),
        ('ONSITE', 'On-site'),
        ('HYBRID', 'Hybrid'),
    ]

    # Required fields (from APIJobs: title, description, company_name)
    title = models.CharField(max_length=255, verbose_name=_('Job Title'))
    company_name = models.CharField(max_length=255, verbose_name=_('Company Name'))
    description = models.TextField(verbose_name=_('Job Description'))
    requirements = models.TextField(blank=True, null=True, verbose_name=_('Job Requirements')) # Now explicitly blank/null

    # Optional fields (from APIJobs)
    industry = models.CharField(max_length=100, blank=True, null=True, verbose_name=_('Industry'))
    location = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('Job Location'))

    # Salary information
    salary_min = models.DecimalField(max_digits=50, decimal_places=2, blank=True, null=True, verbose_name=_('Minimum Salary'))
    salary_max = models.DecimalField(max_digits=50, decimal_places=2, blank=True, null=True, verbose_name=_('Maximum Salary'))
    currency = models.CharField(max_length=50, blank=True, null=True, verbose_name=_('Currency'))
    base_salary_unit = models.CharField(max_length=50, blank=True, null=True, verbose_name=_('Salary Unit')) # e.g., "hour", "year"

    employment_type = models.CharField(
        max_length=50,
        choices=EMPLOYMENT_TYPE_CHOICES,
        blank=True,
        null=True,
        verbose_name=_('Employment Type')
    )
    work_location_type = models.CharField(
        max_length=50,
        choices=WORK_LOCATION_TYPE_CHOICES,
        blank=True,
        null=True,
        verbose_name=_('Work Location Type')
    )

    # Foreign Key to the user who posted the job (system user for imported jobs)
    posted_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        related_name='posted_jobs',
        blank=True,
        null=True,
        verbose_name=_('Posted By')
    )

    # APIJobs specific company details
    hiring_organization_url = models.URLField(max_length=500, blank=True, null=True, verbose_name=_('Hiring Org URL'))
    hiring_organization_logo = models.URLField(max_length=500, blank=True, null=True, verbose_name=_('Hiring Org Logo'))

    # APIJobs 'website' field used as external_application_url
    external_application_url = models.URLField(max_length=500, blank=True, null=True, verbose_name=_('External Application URL'))
    
    # APIJobs 'published_at' field
    published_at = models.DateTimeField(blank=True, null=True, verbose_name=_('Publication Date'))

    # Fields for external API integration (CRITICAL for deduplication)
    external_source_id = models.CharField(
        max_length=255,
        unique=True, # Ensure uniqueness across all sources
        blank=True,
        null=True,
        verbose_name=_('External Source ID')
    )
    external_source_name = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_('External Source Name')
    )

    # Job Verification Logic (10.3)
    status = models.CharField(
        max_length=50,
        choices=JOB_STATUS_CHOICES,
        default='PENDING', # Default to PENDING, task will set to VERIFIED
        verbose_name=_('Job Status')
    )
    verified_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='verified_jobs',
        verbose_name=_('Verified By')
    )
    verified_at = models.DateTimeField(blank=True, null=True, verbose_name=_('Verification Timestamp'))

    # Timestamps (Django's auto-managed)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Creation Timestamp'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Last Updated Timestamp'))

    class Meta:
        verbose_name = _('Job Listing')
        verbose_name_plural = _('Job Listings')
        ordering = ['-created_at'] # Order by creation date descending

    def __str__(self):
        return f"{self.title} at {self.company_name} ({self.status})"
    



###################### viashnavi's code ###############


# #add to the bottom
# class TrendingSkill(models.Model):
#     # 👇 ADD THIS FIELD
#     role = models.CharField(max_length=255, default='AI/ML Engineer') 
#     skill = models.CharField(max_length=255)
#     demand = models.CharField(max_length=50, blank=True)
#     increase = models.CharField(max_length=50, blank=True)
#     priority = models.CharField(max_length=50, blank=True)

#     def __str__(self):
#         return f"{self.skill} ({self.role})"

#     class Meta:
#         # Ensures you don't have the same skill listed twice for the same role
#         unique_together = ('role', 'skill')
#         ordering = ['role', '-priority']
    


############################### interview bot models########################

   
class MockInterviewResult(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='mock_interview_results')
    
    interview_start_time = models.DateTimeField(auto_now_add=True)
    interview_end_time = models.DateTimeField(blank=True, null=True)
    
    position_applied = models.CharField(max_length=255, verbose_name=_('Position Applied For'))
    candidate_experience = models.TextField(verbose_name=_('Candidate Experience Description'))
    
    communication_overall_score = models.IntegerField(default=0, verbose_name=_('Communication Overall Score'))
    psychometric_overall_score = models.IntegerField(default=0, verbose_name=_('Psychometric Overall Score'))
    
    aiml_specialization_input = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('AIML Specialization Input'))
    aiml_specialization = models.JSONField(default=list, blank=True, null=True, verbose_name=_('AIML Specialization Details'))

    # NEW FIELDS ADDED HERE
    pre_generated_questions_data = models.JSONField(default=dict, blank=True, null=True, verbose_name=_('Pre-Generated Questions Data'))
    full_qa_transcript = models.JSONField(default=list, blank=True, null=True, verbose_name=_('Full Q&A Transcript'))
    technical_specialization_scores = models.JSONField(default=dict, blank=True, null=True, verbose_name=_('Technical Specialization Scores'))

    identity_verified = models.BooleanField(default=False, verbose_name=_('Identity Verified'))
    
    # Malpractice Tracking
    malpractice_detected = models.BooleanField(default=False, verbose_name=_('Malpractice Detected'))
    malpractice_reason = models.TextField(blank=True, null=True, verbose_name=_('Malpractice Reason'))
    
    # Scores
    global_readiness_score = models.IntegerField(default=0, verbose_name=_('Global Readiness Score'))
    language_proficiency_score = models.IntegerField(default=0, verbose_name=_('Language Proficiency Score'))
    language_analysis = models.TextField(blank=True, null=True, verbose_name=_('Language Analysis'))
    
    # Detailed round-wise analysis (JSONField to store the structure from the bot)
    round_analysis_json = models.JSONField(default=dict, blank=True, null=True, verbose_name=_('Detailed Round Analysis (JSON)'))

    # Interview Status
    class InterviewStatus(models.TextChoices):
        IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
        COMPLETED = 'COMPLETED', _('Completed Successfully')
        TERMINATED_MALPRACTICE = 'TERMINATED_MALPRACTICE', _('Terminated Due to Malpractice')
        TERMINATED_ERROR = 'TERMINATED_ERROR', _('Terminated Due to Error')
        TERMINATED_MANUAL = 'TERMINATED_MANUAL', _('Manually Terminated')

    status = models.CharField(
        max_length=50,
        choices=InterviewStatus.choices,
        default=InterviewStatus.IN_PROGRESS,
        verbose_name=_('Interview Status')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Mock Interview Result')
        verbose_name_plural = _('Mock Interview Results')
        ordering = ['-interview_start_time']

    def __str__(self):
        return f"Mock Interview for {self.user.username} ({self.position_applied}) - {self.status}"
    


############################### interview bot models end ########################