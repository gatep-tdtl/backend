# employer_management/models.py

from django.db import models
from django.utils.translation import gettext_lazy as _

# IMPORTANT: Importing CustomUser and UserRole from talent_management.models
# as they are central to the user system.
from talent_management.models import CustomUser, UserRole, IndustryChoices


# Enum for Job Status
class JobStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    PUBLISHED = 'PUBLISHED', 'Published'
    CLOSED = 'CLOSED', 'Closed'
    ARCHIVED = 'ARCHIVED', 'Archived'

# Enum for Application Status
class ApplicationStatus(models.TextChoices):
    APPLIED = 'APPLIED', 'Applied'
    REVIEWED = 'REVIEWED', 'Reviewed'
    SHORTLISTED = 'SHORTLISTED', 'Shortlisted'
    INTERVIEW_SCHEDULED = 'INTERVIEW_SCHEDULED', 'Interview Scheduled'
    INTERVIEWED = 'INTERVIEWED', 'Interviewed'
    OFFER_EXTENDED = 'OFFER_EXTENDED', 'Offer Extended'
    OFFER_ACCEPTED = 'OFFER_ACCEPTED', 'Offer Accepted'
    OFFER_REJECTED = 'OFFER_REJECTED', 'Offer Rejected'
    REJECTED = 'REJECTED', 'Rejected'
    HIRED = 'HIRED', 'Hired'
    WITHDRAWN = 'WITHDRAWN', 'Withdrawn'

# Enum for Interview Type
class InterviewType(models.TextChoices):
    INITIAL_SCREEN = 'INITIAL_SCREEN', 'Initial Screen'
    TECHNICAL = 'TECHNICAL', 'Technical'
    HR = 'HR', 'HR'
    PANEL = 'PANEL', 'Panel'
    FINAL = 'FINAL', 'Final'
    OTHER = 'OTHER', 'Other'

# NEW: Enum for Job Type (already well-defined)
class JobType(models.TextChoices):
    FULL_TIME = 'Full-time', 'Full-time'
    PART_TIME = 'Part-time', 'Part-time'
    CONTRACT = 'Contract', 'Contract'
    TEMPORARY = 'Temporary', 'Temporary'
    INTERNSHIP = 'Internship', 'Internship'
    FREELANCE = 'Freelance', 'Freelance'

# NEW: Enum for Experience Level (already well-defined)
class ExperienceLevel(models.TextChoices):
    ENTRY = 'Entry-level', 'Entry Level (0-2 years)'
    MID = 'Mid-level', 'Mid Level (3-5 years)'
    SENIOR = 'Senior-level', 'Senior Level (5+ years)'
    LEAD_PRINCIPAL = 'Lead/Principal', 'Lead/Principal (8+ years)'
    EXECUTIVE = 'Executive', 'Executive (10+ years)' # Added another common level


# NEW: Enum for Interview Status (already well-defined)
class InterviewStatus(models.TextChoices):
    SCHEDULED = 'Scheduled', 'Scheduled'
    COMPLETED = 'Completed', 'Completed'
    CANCELED = 'Canceled', 'Canceled'
    RESCHEDULED = 'Rescheduled', 'Rescheduled'

# NEW: Enum for Company Size (for dropdown)
class CompanySizeChoices(models.TextChoices):
    SIZE_1_10 = '1-10', '1-10 employees'
    SIZE_11_50 = '11-50', '11-50 employees'
    SIZE_51_200 = '51-200', '51-200 employees'
    SIZE_201_500 = '201-500', '201-500 employees'
    SIZE_501_1000 = '501-1000', '501-1000 employees'
    SIZE_1001_5000 = '1001-5000', '1001-5000 employees'
    SIZE_5000_PLUS = '5000+', '5000+ employees'


class Company(models.Model):
    # This model represents the hiring organization
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='employer_company', null=True, blank=True)
    # The user linked here would typically have the EMPLOYER user_role
    company_name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    
    industry = models.CharField( # <--- UPDATED TO DROPDOWN, uses imported choices
        max_length=100,
        choices=IndustryChoices.choices,
        blank=True,
        null=True, # Allow null if not provided
        verbose_name=_('Industry')
    )
    website = models.URLField(max_length=200, blank=True)
    headquarters = models.CharField(max_length=255, blank=True)
    size = models.CharField( # <--- UPDATED TO DROPDOWN
        max_length=50,
        choices=CompanySizeChoices.choices,
        blank=True,
        null=True, # Allow null if not provided
        verbose_name=_('Company Size')
    )
    logo = models.ImageField(upload_to='company_logos/', blank=True, null=True)
    founded_date = models.DateField(null=True, blank=True)
    contact_email = models.EmailField(blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    # Add other fields as needed, e.g., social media links, vision/mission

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Companies" # Correct pluralization in Django Admin

    def __str__(self):
        return self.company_name

class JobPosting(models.Model):
    # A job posted by a company
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='job_postings')
    title = models.CharField(max_length=255)
    description = models.TextField()
    requirements = models.JSONField(default=list, blank=True) # For "Add Requirement"
    responsibilities = models.TextField(blank=True) # e.g., bullet points of daily tasks
    location = models.CharField(max_length=255) # e.g., "Pune, India", "Remote"
    
    job_type = models.CharField(max_length=50, choices=JobType.choices) # Using new Enum (already dropdown)
    experience_level = models.CharField(max_length=50, choices=ExperienceLevel.choices, blank=True) # Using new Enum (already dropdown)
    
    salary_currency = models.CharField(max_length=10, default='USD', blank=True)
    salary_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    contact_email = models.EmailField(blank=True)

    benefits = models.JSONField(default=list, blank=True) # For "Add Benefit"
    required_skills = models.JSONField(default=list, blank=True) # For "Required Skills"
    visa_sponsorship = models.BooleanField(default=False) # For "Visa Sponsorship"
    remote_work = models.BooleanField(default=False) # For "Remote Work"

    status = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.DRAFT) # (already dropdown)
    posted_date = models.DateTimeField(auto_now_add=True)
    application_deadline = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} at {self.company.company_name}"

class Application(models.Model):
    # An application submitted by a talent for a job posting
    job_posting = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name='applications')
    talent = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='applications')
    resume = models.FileField(upload_to='resumes/', blank=True, null=True) 
    application_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, choices=ApplicationStatus.choices, default=ApplicationStatus.APPLIED) # (already dropdown)
    cover_letter = models.TextField(blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True) # Internal screening score
    notes = models.TextField(blank=True) # Recruiter notes

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Ensures a talent can only apply once to a specific job posting
        unique_together = ('job_posting', 'talent')
        ordering = ['-application_date'] # Order applications by most recent first

    def __str__(self):
        # Adjusted for accessing CustomUser's username directly
        return f"Application by {self.talent.username} for {self.job_posting.title}"

class Interview(models.Model):
    # Scheduling and tracking interviews for an application
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='interviews')
    interviewer = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='conducted_interviews')
    
    interview_type = models.CharField(max_length=50, choices=InterviewType.choices, default=InterviewType.TECHNICAL) # (already dropdown)
    scheduled_at = models.DateTimeField()
    location = models.CharField(max_length=255, blank=True) # e.g., "Google Meet link", "Company Office"
    feedback = models.TextField(blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    interview_status = models.CharField(max_length=50, choices=InterviewStatus.choices, default=InterviewStatus.SCHEDULED) # Using new Enum (already dropdown)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['scheduled_at']

    def __str__(self):
        # Adjusted for accessing CustomUser's username directly
        return f"{self.interview_type} for {self.application.talent.username} on {self.scheduled_at.strftime('%Y-%m-%d %H:%M')}"
    
class SavedJob(models.Model):
    # The talent user who saved the job
    talent = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='saved_jobs', limit_choices_to={'user_role': UserRole.TALENT})
    
    # The job posting that was saved, now correctly imported from employer_management
    job_posting = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name='saved_by_talents')
    
    # Timestamp for when the job was saved
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Ensures that a talent can save a particular job only once
        unique_together = ('talent', 'job_posting')
        verbose_name = _('Saved Job')
        verbose_name_plural = _('Saved Jobs')
        ordering = ['-saved_at'] # Order by most recently saved

    def __str__(self):
        return f"{self.talent.username} saved {self.job_posting.title}"