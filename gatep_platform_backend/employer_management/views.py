# employer_management/views.py
import json
from rest_framework.response import Response
from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from .models import ApplicationStatus, Company, JobPosting, Application, Interview, JobStatus, SavedJob, InterviewStatus
from talent_management.models import TalentProfile, Resume, CustomUser, UserRole
from .serializers import (
    CompanySerializer, JobPostingSerializer, ApplicationSerializer, InterviewSerializer,
    SavedJobSerializer, SaveJobActionSerializer, ApplicationListSerializer, ApplicationDetailSerializer
)
from utils.ai_match import get_ai_match_score
from django.db.models import Avg
from rest_framework.exceptions import PermissionDenied
from employer_management.permissions import (
    IsEmployerUser, IsApplicationOwnerOrJobOwner, IsInterviewParticipantOrJobOwner, IsJobPostingOwner
)
from rest_framework import serializers

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
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser]

    def get_object(self):
        # Return only the company associated with the current employer
        return get_object_or_404(Company, user=self.request.user)

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
        # Only allow creation if employer has a company profile
        employer_company = getattr(self.request.user, 'employer_company', None)
        if not employer_company:
            raise serializers.ValidationError({"detail": "You must register your company before posting jobs."})
        serializer.save(company=employer_company)

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
    http_method_names = ['get','post'] 

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated()] 
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Application.objects.none()

        if hasattr(user, 'user_role') and user.user_role == UserRole.TALENT:
            # Use CustomUser directly
            return Application.objects.filter(talent=user) \
                               .select_related('job_posting', 'job_posting__company') \
                               .prefetch_related('interviews') \
                               .order_by('-application_date')
        elif hasattr(user, 'user_role') and user.user_role == UserRole.EMPLOYER:
            company = get_object_or_404(Company, user=user)
            return Application.objects.filter(job_posting__company=company) \
                               .select_related('job_posting', 'job_posting__company') \
                               .prefetch_related('interviews') \
                               .order_by('-application_date')
        return Application.objects.none()

    def perform_create(self, serializer):
        # Ensure the user is a talent
        print ("reached to create application")
        if not hasattr(self.request.user, 'user_role') or self.request.user.user_role != UserRole.TALENT:
            raise serializers.ValidationError({"detail": "Only Talent users can submit applications."})

        job_posting = serializer.validated_data.get('job_posting')
        if not job_posting:
            raise serializers.ValidationError({"job_posting": "Job posting is required."})

        if Application.objects.filter(job_posting=job_posting, talent=self.request.user).exists():
            raise serializers.ValidationError({"detail": "You have already applied for this job."})

        serializer.save(talent=self.request.user, status=ApplicationStatus.APPLIED)

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

        # Use request.user directly as talent
        if SavedJob.objects.filter(talent=request.user, job_posting=job_posting).exists():
            return Response({'message': 'Job already saved.'}, status=status.HTTP_200_OK)

        saved_job = SavedJob.objects.create(talent=request.user, job_posting=job_posting)
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
            saved_job = SavedJob.objects.get(talent=request.user, job_posting__id=job_posting_id)
            print(saved_job)
            saved_job.delete()
            return Response({'message': 'Job unsaved successfully.'}, status=status.HTTP_204_NO_CONTENT)
        except SavedJob.DoesNotExist:
            return Response({'error': 'Saved job not found for this user.'}, status=status.HTTP_404_NOT_FOUND)

class ListSavedJobsView(generics.ListAPIView):
    serializer_class = SavedJobSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not (hasattr(self.request.user, 'user_role') and self.request.user.user_role == UserRole.TALENT):
            raise permissions.PermissionDenied("Only talent users can view saved jobs.")
        return SavedJob.objects.filter(talent=self.request.user).select_related('job_posting__company')


# --- NEW EMPLOYER-SPECIFIC APPLICATION VIEWS (AS REQUESTED) ---

class EmployerApplicationListForJobView(generics.ListAPIView):
    """
    API endpoint for employers to list all applications for a specific job posting.
    Filters applications by job_posting_id from URL and ensures employer owns the job.
    """
    serializer_class = ApplicationListSerializer 
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser]
    
    def get_queryset(self):
        job_posting_id = self.kwargs['job_posting_id']
        job_posting = get_object_or_404(JobPosting, pk=job_posting_id)
        print (job_posting)
        self.check_object_permissions(self.request, job_posting)

        queryset = Application.objects.filter(job_posting=job_posting).order_by('-application_date')


        # Only keep valid related lookups
        # queryset = queryset.select_related('talent')  # ✅ Safe
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
            print(user_skills)
        except Exception:
            user_skills = []

        jobs = JobPosting.objects.filter(is_active=True, status='PUBLISHED').order_by('-posted_date')
        print(jobs)
        job_list = []
        for job in jobs:
            job_required_skills = job.required_skills if hasattr(job, 'required_skills') and job.required_skills else []
            print(job_required_skills)
            score = get_ai_match_score(user_skills, job_required_skills)
            print(score)
            job_list.append({
                'id': job.id,
                'title': job.title,
                'required_skills': job_required_skills,
                'matching_percentage': score
            })
        return Response(job_list)

class EmployerCompanyView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser]

    def get(self, request):
        try:
            company = Company.objects.get(user=request.user)
        except Company.DoesNotExist:
            return Response({'detail': 'Register your company first.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = CompanySerializer(company)
        return Response(serializer.data, status=status.HTTP_200_OK)