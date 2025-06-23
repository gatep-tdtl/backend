# employer_management/models.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from talent_management.models import CustomUser, UserRole, IndustryChoices

class JobStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    PUBLISHED = 'PUBLISHED', 'Published'
    CLOSED = 'CLOSED', 'Closed'
    ARCHIVED = 'ARCHIVED', 'Archived'

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

class InterviewType(models.TextChoices):
    INITIAL_SCREEN = 'INITIAL_SCREEN', 'Initial Screen'
    TECHNICAL = 'TECHNICAL', 'Technical'
    HR = 'HR', 'HR'
    PANEL = 'PANEL', 'Panel'
    FINAL = 'FINAL', 'Final'
    OTHER = 'OTHER', 'Other'

class JobType(models.TextChoices):
    FULL_TIME = 'Full-time', 'Full-time'
    PART_TIME = 'Part-time', 'Part-time'
    CONTRACT = 'Contract', 'Contract'
    TEMPORARY = 'Temporary', 'Temporary'
    INTERNSHIP = 'Internship', 'Internship'
    FREELANCE = 'Freelance', 'Freelance'

class ExperienceLevel(models.TextChoices):
    ENTRY = 'Entry-level', 'Entry Level (0-2 years)'
    MID = 'Mid-level', 'Mid Level (3-5 years)'
    SENIOR = 'Senior-level', 'Senior Level (5+ years)'
    LEAD_PRINCIPAL = 'Lead/Principal', 'Lead/Principal (8+ years)'
    EXECUTIVE = 'Executive', 'Executive (10+ years)'

class InterviewStatus(models.TextChoices):
    SCHEDULED = 'Scheduled', 'Scheduled'
    COMPLETED = 'Completed', 'Completed'
    CANCELED = 'Canceled', 'Canceled'
    RESCHEDULED = 'Rescheduled', 'Rescheduled'

class CompanySizeChoices(models.TextChoices):
    SIZE_1_10 = '1-10', '1-10 employees'
    SIZE_11_50 = '11-50', '11-50 employees'
    SIZE_51_200 = '51-200', '51-200 employees'
    SIZE_201_500 = '201-500', '201-500 employees'
    SIZE_501_1000 = '501-1000', '501-1000 employees'
    SIZE_1001_5000 = '1001-5000', '1001-5000 employees'
    SIZE_5000_PLUS = '5000+', '5000+ employees'

class Company(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='employer_company', null=True, blank=True)
    company_name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    industry = models.CharField(max_length=100, choices=IndustryChoices.choices, blank=True, null=True, verbose_name=_('Industry'))
    website = models.URLField(max_length=200, blank=True)
    headquarters = models.CharField(max_length=255, blank=True)
    size = models.CharField(max_length=50, choices=CompanySizeChoices.choices, blank=True, null=True, verbose_name=_('Company Size'))
    logo = models.ImageField(upload_to='company_logos/', blank=True, null=True)
    founded_date = models.DateField(null=True, blank=True)
    contact_email = models.EmailField(blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name_plural = "Companies"
    def __str__(self):
        return self.company_name

class JobPosting(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='job_postings')
    title = models.CharField(max_length=255)
    description = models.TextField()
    requirements = models.JSONField(default=list, blank=True)
    responsibilities = models.TextField(blank=True)
    location = models.CharField(max_length=255)
    job_type = models.CharField(max_length=50, choices=JobType.choices)
    experience_level = models.CharField(max_length=50, choices=ExperienceLevel.choices, blank=True)
    salary_currency = models.CharField(max_length=10, default='USD', blank=True)
    salary_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    contact_email = models.EmailField(blank=True)
    benefits = models.JSONField(default=list, blank=True)
    required_skills = models.JSONField(default=list, blank=True)
    visa_sponsorship = models.BooleanField(default=False)
    remote_work = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.DRAFT)
    posted_date = models.DateTimeField(auto_now_add=True)
    application_deadline = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self):
        return f"{self.title} at {self.company.company_name}"

class Application(models.Model):
    job_posting = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name='applications')
    talent = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='applications')
    resume = models.FileField(upload_to='resumes/', blank=True, null=True)
    application_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, choices=ApplicationStatus.choices, default=ApplicationStatus.APPLIED)
    cover_letter = models.TextField(blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        unique_together = ('job_posting', 'talent')
        ordering = ['-application_date']
    def __str__(self):
        return f"Application by {self.talent.username} for {self.job_posting.title}"

class Interview(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='interviews')
    interviewer = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='conducted_interviews')
    interview_type = models.CharField(max_length=50, choices=InterviewType.choices, default=InterviewType.TECHNICAL)
    scheduled_at = models.DateTimeField()
    location = models.CharField(max_length=255, blank=True)
    feedback = models.TextField(blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    interview_status = models.CharField(max_length=50, choices=InterviewStatus.choices, default=InterviewStatus.SCHEDULED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['scheduled_at']
    def __str__(self):
        return f"{self.interview_type} for {self.application.talent.username} on {self.scheduled_at.strftime('%Y-%m-%d %H:%M')}"

class SavedJob(models.Model):
    talent = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='saved_jobs', limit_choices_to={'user_role': UserRole.TALENT})
    job_posting = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name='saved_by_talents')
    saved_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        unique_together = ('talent', 'job_posting')
        verbose_name = _('Saved Job')
        verbose_name_plural = _('Saved Jobs')
        ordering = ['-saved_at']
    def __str__(self):
        return f"{self.talent.username} saved {self.job_posting.title}"