# employer_management/views.py
import json 
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from rest_framework import serializers # Import serializers to raise ValidationError

from django.db.models import Count, Avg, Prefetch

from utils.ai_match import get_ai_match_score# Importing AI match utility for job matching score
# --- CORRECTED IMPORTS ---
# Ensure InterviewStatus is imported directly
from .models import (
    Company,
    JobPosting,
    Application,
    Interview,
    ApplicationStatus,
    JobStatus,
    InterviewStatus, # <--- THIS IS THE CRUCIAL IMPORT
    SavedJob # Import SavedJob model for saved job functionality
)
# --- END CORRECTED IMPORTS ---

# Import all necessary serializers, including the new ones for employer application management
from .serializers import (
    CompanySerializer, JobPostingSerializer, ApplicationSerializer, InterviewSerializer,
    ApplicationListSerializer, ApplicationDetailSerializer,
    SavedJobSerializer, SaveJobActionSerializer # <-- ADD THESE TWO
)

# IMPORTANT: Importing EmployerProfile, TalentProfile, CustomUser, UserRole from talent_management.models
# as per your project structure. Update this if you move them to auth_management later.
from talent_management.models import EmployerProfile, TalentProfile, CustomUser, UserRole


# --- Permission Classes ---
# (Keeping your existing permissions, with minor adjustments for robustness)

class IsEmployerUser(permissions.BasePermission):
    """
    Custom permission to only allow employer users to access.
    Checks if user is authenticated and has the EMPLOYER role.
    """
    def has_permission(self, request, view):
        # Added hasattr checks for robustness, preventing AttributeError if user is anonymous or lacks user_role.
        return request.user and request.user.is_authenticated and \
               hasattr(request.user, 'user_role') and request.user.user_role == UserRole.EMPLOYER

class IsCompanyOwner(permissions.BasePermission):
    """
    Custom permission to only allow the owner of a company to modify it.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True # Allow safe methods (GET, HEAD, OPTIONS) for any authenticated user
        # For unsafe methods (POST, PUT, PATCH, DELETE), check if user is the company owner
        return obj.user == request.user

class IsJobPostingOwner(permissions.BasePermission):
    """
    Custom permission to only allow the owner of a job posting (via their company) to modify it.
    This permission is critical for ensuring employers only manage applications for their own jobs.
    """
    def has_object_permission(self, request, view, obj):
        # For GET requests (safe methods), strictly check if the user is an employer AND owns the job's company.
        if request.method in permissions.SAFE_METHODS:
            if request.user.is_authenticated and hasattr(request.user, 'user_role') and request.user.user_role == UserRole.EMPLOYER:
                # Ensure the employer user has an associated company profile before checking ownership
                return hasattr(request.user, 'employer_company') and request.user.employer_company == obj.company
            return False # Non-owners (including other roles/unauthenticated) cannot view applications for this job.
        
        # For unsafe methods (PUT, PATCH, DELETE), strict ownership check for modification/deletion
        return request.user.is_authenticated and hasattr(request.user, 'user_role') and request.user.user_role == UserRole.EMPLOYER and \
               hasattr(request.user, 'employer_company') and request.user.employer_company == obj.company

class IsApplicationOwnerOrJobOwner(permissions.BasePermission):
    """
    Custom permission to allow the talent who submitted the application OR
    the employer who owns the job posting to access/modify the application.
    """
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        if request.user.user_role == UserRole.TALENT and hasattr(request.user, 'talent_profile'):
            return obj.talent == request.user.talent_profile
        elif request.user.user_role == UserRole.EMPLOYER and hasattr(request.user, 'employer_company'):
            return obj.job_posting.company == request.user.employer_company
        return False


class IsInterviewParticipantOrJobOwner(permissions.BasePermission):
    """
    Custom permission to allow the interviewer, the talent being interviewed, OR
    the employer who owns the job posting to access/modify the interview.
    """
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        is_interviewer = (obj.interviewer == request.user)
        is_talent_applicant = (
            request.user.user_role == UserRole.TALENT and 
            hasattr(request.user, 'talent_profile') and 
            obj.application.talent == request.user.talent_profile
        )
        is_owner_employer = (
            request.user.user_role == UserRole.EMPLOYER and 
            hasattr(request.user, 'employer_company') and
            obj.application.job_posting.company == request.user.employer_company
        )
        
        return is_interviewer or is_talent_applicant or is_owner_employer


# --- ViewSets/APIViews (EXISTING VIEWS - MINIMAL ADJUSTMENTS FOR ROBUSTNESS/CLARITY) ---

class CompanyListCreateView(generics.ListCreateAPIView):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    
    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated(), IsEmployerUser()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        # Raise DRF ValidationError for better API response
        if Company.objects.filter(user=self.request.user).exists():
            raise serializers.ValidationError({"detail": "This employer user already has an associated company profile."})
        serializer.save(user=self.request.user)

class CompanyDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser, IsCompanyOwner]

class JobPostingListCreateView(generics.ListCreateAPIView):
    serializer_class = JobPostingSerializer
    
    def get_permissions(self):
        if self.request.method == 'GET':
            # Anyone can view job listings
            return [permissions.AllowAny()]
        # Only authenticated EMPLOYER users can create job postings
        return [permissions.IsAuthenticated(), IsEmployerUser()]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated or (hasattr(user, 'user_role') and user.user_role == UserRole.TALENT):
            # Always return only published and active jobs for unauthenticated or talent users
            return JobPosting.objects.filter(status=JobStatus.PUBLISHED, is_active=True).order_by('-posted_date')
        
        elif hasattr(user, 'user_role') and user.user_role == UserRole.EMPLOYER:
            # If authenticated and employer, show their company's job postings
            # Ensure employer_company exists before accessing it
            if hasattr(user, 'employer_company') and user.employer_company: 
                return JobPosting.objects.filter(company=user.employer_company).order_by('-posted_date')
            else:
                return JobPosting.objects.none() # Employer without a company profile sees no jobs
        return JobPosting.objects.none() # Fallback for other roles or unauthenticated (if not caught above)

    def perform_create(self, serializer):
        # Ensure company exists for the current user before saving
        company = get_object_or_404(Company, user=self.request.user)
        serializer.save(company=company)

class JobPostingDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = JobPosting.objects.all()
    serializer_class = JobPostingSerializer
    
    def get_permissions(self):
        if self.request.method == 'GET':
            # Anyone can view a single job posting
            return [permissions.AllowAny()]
        # Only authenticated EMPLOYER users who own the job posting can update/delete it
        return [permissions.IsAuthenticated(), IsEmployerUser(), IsJobPostingOwner()]


class ApplicationListCreateView(generics.ListCreateAPIView):
    # This view is primarily for Talent users to list/create applications.
    serializer_class = ApplicationSerializer 
    
    # --- ADD THIS LINE TO ALLOW ONLY POST METHOD ---
    http_method_names = ['get','post'] 
    # --- END ADDITION ---
    
    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated()] 
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Application.objects.none()

        if hasattr(user, 'user_role') and user.user_role == UserRole.TALENT:
            talent_profile = get_object_or_404(TalentProfile, user=user)
            # Original filtering: Application.objects.filter(talent=talent_profile.user)
            # Added for performance: .select_related('job_posting', 'job_posting__company') and .prefetch_related('interviews')
            return Application.objects.filter(talent=talent_profile.user) \
                               .select_related('job_posting', 'job_posting__company') \
                               .prefetch_related('interviews') \
                               .order_by('-application_date')
        elif hasattr(user, 'user_role') and user.user_role == UserRole.EMPLOYER:
            company = get_object_or_404(Company, user=user)
            # Original filtering: Application.objects.filter(job_posting__company=company)
            # Added for performance: .select_related('job_posting', 'job_posting__company') and .prefetch_related('interviews')
            return Application.objects.filter(job_posting__company=company) \
                               .select_related('job_posting', 'job_posting__company') \
                               .prefetch_related('interviews') \
                               .order_by('-application_date')
        return Application.objects.none()
    def perform_create(self, serializer):
        # Ensure the user is a talent and has a profile
        if not hasattr(self.request.user, 'user_role') or self.request.user.user_role != UserRole.TALENT:
            raise serializers.ValidationError({"detail": "Only Talent users can submit applications."})

        talent_profile = get_object_or_404(TalentProfile, user=self.request.user)
        
        job_posting = serializer.validated_data.get('job_posting')
        if not job_posting:
            raise serializers.ValidationError({"job_posting": "Job posting is required."})

        # --- COMPATIBILITY CHECK (STILL COMMENTED OUT) ---
        # if not self._is_profile_compatible_with_job(talent_profile, job_posting):
        #    raise serializers.ValidationError({"detail": "Your profile is not compatible with this job's requirements."})
        # --- END COMPATIBILITY CHECK ---

        if Application.objects.filter(job_posting=job_posting, talent=talent_profile.user).exists():
            raise serializers.ValidationError({"detail": "You have already applied for this job."})

        serializer.save(talent=talent_profile.user, status=ApplicationStatus.APPLIED)

    # Helper method for compatibility check (STILL COMMENTED OUT)
    # def _is_profile_compatible_with_job(self, talent_profile, job_posting):
    #    # ... (your commented out compatibility logic)
    #    return True
    # Helper method for compatibility check


    
    def _is_profile_compatible_with_job(self, talent_profile, job_posting):
        # Define compatibility logic here
        # This is a basic example. You'll need to tailor it to your actual model fields
        # and business logic for what "compatible" means.

        # 1. Skill Compatibility (simple intersection check)
        # Assumes job_posting.required_skills and talent_profile.skills are lists/arrays of strings
        # If using ManyToManyField to a Skill model, you'd do:
        # job_skills = set(job_posting.required_skills.values_list('name', flat=True))
        # talent_skills = set(talent_profile.skills.values_list('name', flat=True))
        job_skills = set(job_posting.required_skills) if job_posting.required_skills else set()
        talent_skills = set(talent_profile.skills) if hasattr(talent_profile, 'skills') and talent_profile.skills else set()

        # If job requires skills, and talent has none of them, it's not compatible
        if job_skills and not (job_skills.intersection(talent_skills)):
            return False 
            
        # 2. Experience Level Compatibility
        # Assumes experience_level in JobPosting is a choice field (e.g., 'ENTRY_LEVEL', 'MID_LEVEL')
        # And talent_profile has a 'total_experience_years' or similar numeric field.
        # Adjust 'total_experience_years' based on your TalentProfile model.
        experience_mapping = {
            JobPosting.ExperienceLevel.ENTRY: (0, 2),    # Adjusted to use JobPosting.ExperienceLevel enum values
            JobPosting.ExperienceLevel.MID: (3, 5),      # Adjusted
            JobPosting.ExperienceLevel.SENIOR: (5, 8),   # Adjusted
            JobPosting.ExperienceLevel.LEAD_PRINCIPAL: (8, 99) # Adjusted
        }

        talent_years = getattr(talent_profile, 'total_experience_years', 0) # Default to 0 if field doesn't exist or is not set

        # Get the required experience range from the job posting
        # Use .get() with a default in case experience_level is not found or is None
        required_min_exp, required_max_exp = experience_mapping.get(job_posting.experience_level, (0, 99))

        if talent_years < required_min_exp:
            return False # Not enough experience

        # Add more compatibility checks as needed:
        # - Location preference (e.g., if job is on-site, talent must be nearby or willing to relocate)
        # - Job Type preference (e.g., talent wants full-time, job is full-time)
        # - Visa Sponsorship (if job requires it, talent must be eligible)

        return True # If all checks pass, profile is compatible


class ApplicationDetailView(generics.RetrieveUpdateDestroyAPIView):
    # This view is for general application detail, used by talent to withdraw or employer to update
    queryset = Application.objects.all()
    serializer_class = ApplicationSerializer 
    permission_classes = [permissions.IsAuthenticated, IsApplicationOwnerOrJobOwner]

    def perform_update(self, serializer):
        if hasattr(self.request.user, 'user_role') and self.request.user.user_role == UserRole.EMPLOYER:
            if hasattr(self.request.user, 'employer_company') and serializer.instance.job_posting.company == self.request.user.employer_company:
                serializer.save()
            else:
                self.permission_denied(self.request, message="You do not own the company associated with this job posting.")
        elif hasattr(self.request.user, 'user_role') and self.request.user.user_role == UserRole.TALENT:
            if hasattr(self.request.user, 'talent_profile') and serializer.instance.talent == self.request.user.talent_profile:
                if 'status' in serializer.validated_data and serializer.validated_data['status'] != ApplicationStatus.WITHDRAWN:
                    raise serializers.ValidationError({"status": "Talent can only withdraw their application. Other status changes are not allowed."})
                serializer.save()
            else:
                self.permission_denied(self.request, message="You do not own this application.")
        else:
            self.permission_denied(self.request, message="You do not have permission to update this application.")


class InterviewListCreateView(generics.ListCreateAPIView):
    serializer_class = InterviewSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser] 

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Interview.objects.none()

        if hasattr(user, 'user_role') and user.user_role == UserRole.EMPLOYER:
            company = get_object_or_404(Company, user=user)
            return Interview.objects.filter(application__job_posting__company=company).order_by('scheduled_at')
        elif hasattr(user, 'user_role') and user.user_role == UserRole.TALENT:
            talent_profile = get_object_or_404(TalentProfile, user=user)
            return Interview.objects.filter(application__talent=talent_profile).order_by('scheduled_at')
        
        return Interview.objects.none()

    def perform_create(self, serializer):
        application = serializer.validated_data.get('application')
        
        # Ensure employer has an associated company and owns the job posting
        if not hasattr(self.request.user, 'employer_company') or application.job_posting.company != self.request.user.employer_company:
            raise permissions.PermissionDenied("You can only schedule interviews for your company's job postings.")
        
        serializer.save(interviewer=self.request.user)
    
class InterviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Interview.objects.all()
    serializer_class = InterviewSerializer
    permission_classes = [permissions.IsAuthenticated, IsInterviewParticipantOrJobOwner]

    def perform_update(self, serializer):
        serializer.save()


# --- Saved Job Views (No changes to their core logic) ---
# Removed redundant imports here, as they are already at the top or in serializers.py
# from rest_framework.response import Response
# from .serializers import (JobPostingSerializer, SavedJobSerializer, SaveJobActionSerializer)
# from .models import SavedJob
# from employer_management.models import JobPosting
# from rest_framework.permissions import IsAuthenticated
# from rest_framework.views import APIView
# from rest_framework.exceptions import PermissionDenied


class SaveJobView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if not (hasattr(request.user, 'user_role') and request.user.user_role == UserRole.TALENT):
            raise permissions.PermissionDenied("Only talent users can save jobs.")

        job_posting_id = request.data.get('job_posting_id')
        if not job_posting_id:
            return Response({'error': 'job_posting_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            job_posting = JobPosting.objects.get(id=job_posting_id)
        except JobPosting.DoesNotExist:
            return Response({'error': 'Job Posting not found.'}, status=status.HTTP_404_NOT_FOUND)

        talent_profile = get_object_or_404(TalentProfile, user=request.user)

        if SavedJob.objects.filter(talent=talent_profile, job_posting=job_posting).exists():
            return Response({'message': 'Job already saved.'}, status=status.HTTP_200_OK)

        saved_job = SavedJob.objects.create(talent=talent_profile, job_posting=job_posting)
        serializer = SavedJobSerializer(saved_job)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class UnsaveJobView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, *args, **kwargs):
        if not (hasattr(request.user, 'user_role') and request.user.user_role == UserRole.TALENT):
            raise permissions.PermissionDenied("Only talent users can unsave jobs.")
            
        job_posting_id = request.data.get('job_posting_id')
        if not job_posting_id:
            return Response({'error': 'job_posting_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            talent_profile = get_object_or_404(TalentProfile, user=request.user)
            saved_job = SavedJob.objects.get(talent=talent_profile, job_posting__id=job_posting_id)
            saved_job.delete()
            return Response({'message': 'Job unsaved successfully.'}, status=status.HTTP_204_NO_CONTENT)
        except TalentProfile.DoesNotExist:
            # Raising PermissionDenied for user-related permission issues
            raise permissions.PermissionDenied("Talent profile not found for the user.") 
        except SavedJob.DoesNotExist:
            return Response({'error': 'Saved job not found for this user.'}, status=status.HTTP_404_NOT_FOUND)

class ListSavedJobsView(generics.ListAPIView):
    serializer_class = SavedJobSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not (hasattr(self.request.user, 'user_role') and self.request.user.user_role == UserRole.TALENT):
            raise permissions.PermissionDenied("Only talent users can view saved jobs.")
            
        talent_profile = get_object_or_404(TalentProfile, user=self.request.user)
        return SavedJob.objects.filter(talent=talent_profile).select_related('job_posting__company')


# --- NEW EMPLOYER-SPECIFIC APPLICATION VIEWS (AS REQUESTED) ---

class EmployerApplicationListForJobView(generics.ListAPIView):
    """
    API endpoint for employers to list all applications for a specific job posting.
    Filters applications by job_posting_id from URL and ensures employer owns the job.
    """
    serializer_class = ApplicationListSerializer 
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser, IsJobPostingOwner]
    
    def get_queryset(self):
        job_posting_id = self.kwargs['job_posting_id']
        job_posting = get_object_or_404(JobPosting, pk=job_posting_id)
        self.check_object_permissions(self.request, job_posting)

        queryset = Application.objects.filter(job_posting=job_posting).order_by('-application_date')

        # Only keep valid related lookups
        queryset = queryset.select_related('talent', 'talent__talentprofile')  # ✅ Safe
        return queryset

    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        # Pass request context to serializer for file URL generation (e.g., in FullResumeSerializer)
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        
        # Calculate summary statistics (from screenshot 1)
        total_applications = queryset.count()
        under_review_count = queryset.filter(status=ApplicationStatus.REVIEWED).count() 
        
        # Count scheduled interviews for these applications
        interviews_scheduled_count = Interview.objects.filter(
            application__in=queryset,
            # FIXED LINE: Referencing InterviewStatus directly as it's a top-level class
            interview_status=InterviewStatus.SCHEDULED # Now correctly uses the imported class
        ).count()
        
        # Average match calculation (assuming 'score' field exists on Application model)
        average_match_obj = queryset.aggregate(avg_score=Avg('score'))
        average_match = f"{average_match_obj['avg_score']:.0f}%" if average_match_obj['avg_score'] is not None else "N/A"

        return Response({
            "job_posting_id": self.kwargs['job_posting_id'],
            "summary_stats": {
                "total_applications": total_applications,
                "under_review_count": under_review_count,
                "interviews_scheduled_count": interviews_scheduled_count,
                "average_match": average_match,
            },
            "applications": serializer.data
        }, status=status.HTTP_200_OK)


class EmployerApplicationDetailView(generics.RetrieveAPIView):
    """
    API endpoint for employers to retrieve comprehensive details of a single application.
    Ensures employer owns the job posting associated with the application.
    """
    queryset = Application.objects.all() 
    serializer_class = ApplicationDetailSerializer 
    # Use IsApplicationOwnerOrJobOwner as it covers both scenarios for employer access.
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser, IsApplicationOwnerOrJobOwner] 
    lookup_field = 'pk' 

    def get_object(self):
        obj = get_object_or_404(self.get_queryset(), pk=self.kwargs['pk'])
        
        # Check object-level permission on the retrieved Application object
        self.check_object_permissions(self.request, obj)
        return obj

    def get_serializer_context(self):
        """
        Ensure 'request' is passed to the serializer context for nested serializers (e.g., FullResumeSerializer)
        to generate absolute URLs for file fields.
        """
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    from utils.ai_match import get_ai_match_score

from talent_management.models import Resume

class JobListWithMatchingScoreAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        if not request.user.is_talent_role:
            return Response({"detail": "Only talent users can view this list."}, status=403)

        resume = Resume.objects.filter(talent_id=request.user, is_deleted=False).order_by('-updated_at').first()
        if not resume or not resume.skills:
            return Response({"detail": "Resume or skills not found."}, status=404)

        try:
            user_skills = json.loads(resume.skills) if resume.skills else []
        except Exception:
            user_skills = []

        jobs = JobPosting.objects.filter(is_active=True, status='PUBLISHED').order_by('-posted_date')

        job_list = []
        for job in jobs:
            job_required_skills = job.required_skills if hasattr(job, 'required_skills') and job.required_skills else []
            score = get_ai_match_score(user_skills, job_required_skills)
            job_list.append({
                'id': job.id,
                'title': job.title,
                'required_skills': job_required_skills,
                'matching_percentage': score
            })
        return Response(job_list)