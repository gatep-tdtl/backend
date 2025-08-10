# employer_management/views.py
from collections import Counter
# CORRECT IMPORT
from django.utils import timezone
from datetime import timedelta # Keep this one, it's correct
import json
from rest_framework.response import Response
from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from .models import ApplicationStatus, Company, JobPosting, Application, Interview, JobStatus, SavedJob, InterviewStatus
from talent_management.models import TalentProfile, Resume, CustomUser, UserRole
from .serializers import (
    ApplicationStatusUpdateSerializer, CandidateDashboardSerializer, CompanySerializer, InterviewStatusUpdateSerializer, JobPostingSerializer, ApplicationSerializer, InterviewSerializer, PotentialCandidateSerializer,
    SavedJobSerializer, SaveJobActionSerializer, ApplicationListSerializer, ApplicationDetailSerializer, InterviewListItemSerializer
)
from utils1.ai_match import get_ai_match_score
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

class EmployerCompanyDetailView(APIView):
    """
    Get the company details for the currently authenticated employer.
    """
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser]

    def get(self, request):
        try:
            company = Company.objects.get(user=request.user)
        except Company.DoesNotExist:
            return Response({'detail': 'Register your company first.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = CompanySerializer(company)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class EmployerCompanyUpdateView(APIView):
    """
    Update the company details for the currently authenticated employer.
    """
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser]

    def put(self, request):
        try:
            company = Company.objects.get(user=request.user)
        except Company.DoesNotExist:
            return Response({'detail': 'Register your company first.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = CompanySerializer(company, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



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
                return JobPosting.objects.filter(company=user.employer_company, is_active=True).order_by('-posted_date')
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
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsEmployerUser(), IsJobPostingOwner()]

    def delete(self, request, *args, **kwargs):
        job_posting = self.get_object()
        job_posting.is_active = False
        job_posting.save()
        return Response({'detail': 'Job posting soft deleted.'}, status=status.HTTP_204_NO_CONTENT)

class PublishJobPostingView(APIView):
    """
    Endpoint to publish a draft job posting (set status to PUBLISHED).
    Only the owner employer can perform this action.
    """
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser, IsJobPostingOwner]

    def put(self, request, pk):
        job_posting = get_object_or_404(JobPosting, pk=pk)
        self.check_object_permissions(request, job_posting)
        if job_posting.status != JobStatus.DRAFT:
            return Response({'detail': 'Only draft jobs can be published.'}, status=status.HTTP_400_BAD_REQUEST)
        job_posting.status = JobStatus.PUBLISHED
        job_posting.save()
        return Response({'detail': 'Job posting published.'}, status=status.HTTP_200_OK)

class CloseJobPostingView(APIView):
    """
    Endpoint to close a published job posting (set status to CLOSED).
    Only the owner employer can perform this action.
    """
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser, IsJobPostingOwner]

    def delete(self, request, pk):
        job_posting = get_object_or_404(JobPosting, pk=pk)
        self.check_object_permissions(request, job_posting)
        if job_posting.status != JobStatus.PUBLISHED:
            return Response({'detail': 'Only published jobs can be closed.'}, status=status.HTTP_400_BAD_REQUEST)
        job_posting.status = JobStatus.CLOSED
        job_posting.is_active = False
        job_posting.save()
        return Response({'detail': 'Job posting closed.'}, status=status.HTTP_200_OK)

class PotentialCandidateMatchView(APIView):
    """
    API endpoint for an employer to discover potential candidates from the talent pool
    who have NOT applied for a specific job, ranked by their AI match score.

    Accessible via: GET /api/job-postings/<job_posting_id>/potential-candidates/
    """
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser, IsJobPostingOwner]

    def get(self, request, job_posting_id, *args, **kwargs):
        job_posting = get_object_or_404(JobPosting, pk=job_posting_id)
        self.check_object_permissions(request, job_posting)

        job_required_skills = job_posting.required_skills if job_posting.required_skills else []
        if not job_required_skills:
            return Response({"detail": "Job posting has no required skills listed."}, status=status.HTTP_400_BAD_REQUEST)

        applied_talent_ids = Application.objects.filter(job_posting=job_posting).values_list('talent_id', flat=True)
        potential_talents = CustomUser.objects.filter(
            user_role=UserRole.TALENT
        ).exclude(
            id__in=applied_talent_ids
        )

        candidate_scores = []

        for talent in potential_talents:
            resume = Resume.objects.filter(talent_id=talent.id, is_deleted=False).order_by('-updated_at').first()
            
            # If no resume exists for the talent, we cannot get skills, location, or a resume URL.
            # So, we skip to the next potential candidate.
            if not resume:
                continue

            user_skills = []
            if resume.skills:
                try:
                    user_skills = json.loads(resume.skills)
                except (json.JSONDecodeError, TypeError):
                    user_skills = [s.strip() for s in str(resume.skills).split(',') if s.strip()]

            # Only proceed to score and list candidates who have skills in their resume.
            if user_skills:
                score = get_ai_match_score(user_skills, job_required_skills)
                
                # --- START: Corrected data retrieval ---
                
                # Correctly determine the candidate's location.
                # Prioritize 'current_city', fallback to 'current_location',
                # and standardize empty or default values to None for a cleaner API response.
                location = resume.current_city or resume.current_location
                if not location or location.strip() == "Not Provided":
                    location = None

                # Correctly get the resume URL from the `resume_pdf` FileField.
                # The `resume_pdf` field is a FileField, not a URLField named `resume_url`.
                resume_url = None
                if resume.resume_pdf and hasattr(resume.resume_pdf, 'url'):
                    # `request.build_absolute_uri` creates a full URL (e.g., http://domain/media/...)
                    resume_url = request.build_absolute_uri(resume.resume_pdf.url)
                    
                # --- END: Corrected data retrieval ---

                candidate_scores.append({
                    'talent_id': talent.id,
                    'name': f"{talent.first_name} {talent.last_name}".strip() or talent.username,
                    'ai_match_score': score,
                    'location': location,      # Now correctly populated
                    'resume_url': resume_url,  # Now correctly populated
                })

        sorted_candidates = sorted(candidate_scores, key=lambda x: x['ai_match_score'], reverse=True)
        serializer = PotentialCandidateSerializer(sorted_candidates, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)





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
                                        .exclude(status=ApplicationStatus.DELETED) \
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

    def create(self, request, *args, **kwargs):
        # Ensure the user is a talent
        if not hasattr(request.user, 'user_role') or request.user.user_role != UserRole.TALENT:
            return Response({"detail": "Only Talent users can submit applications."}, status=status.HTTP_400_BAD_REQUEST)

        job_posting_id = request.data.get('job_posting')
        if not job_posting_id:
            return Response({"job_posting": "Job posting is required."}, status=status.HTTP_400_BAD_REQUEST)

        # You may need to fetch the job_posting instance if the serializer expects an object, not just an ID
        job_posting = JobPosting.objects.filter(pk=job_posting_id).first()
        if not job_posting:
            return Response({"job_posting": "Job posting not found."}, status=status.HTTP_400_BAD_REQUEST)

        existing_application = Application.objects.filter(job_posting=job_posting, talent=request.user).first()
        if existing_application:
            if existing_application.status == ApplicationStatus.DELETED:
                # Reactivate the deleted application
                existing_application.status = ApplicationStatus.APPLIED
                existing_application.save(update_fields=['status'])
                # Return 200 OK with a custom message
                serializer = self.get_serializer(existing_application)
                return Response(
                    {
                        "detail": "Your previous withdrawn application has been re-applied.",
                        "application": serializer.data
                    },
                    status=status.HTTP_200_OK
                )
            else:
                return Response({"detail": "You have already applied for this job."}, status=status.HTTP_400_BAD_REQUEST)

        # If no existing application, proceed as normal
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(talent=request.user, status=ApplicationStatus.APPLIED)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

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

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return InterviewListItemSerializer
        return InterviewSerializer

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

class InterviewStatusUpdateView(generics.UpdateAPIView):
    queryset = Interview.objects.all()
    serializer_class = InterviewStatusUpdateSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser, IsInterviewParticipantOrJobOwner]
    http_method_names = ['patch']

    def get_object(self):
        obj = super().get_object()
        self.check_object_permissions(self.request, obj)
        return obj


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

        queryset = Application.objects.filter(job_posting=job_posting).exclude(status=ApplicationStatus.DELETED).order_by('-application_date')


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


class EmployerApplicationDetailView(generics.RetrieveUpdateAPIView):
    """
    API endpoint for employers to retrieve and partially update application details.
    Ensures employer owns the job posting associated with the application.
    """
    queryset = Application.objects.all()
    serializer_class = ApplicationDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser, IsApplicationOwnerOrJobOwner]
    lookup_field = 'pk'

    def get_object(self):
        obj = get_object_or_404(self.get_queryset(), pk=self.kwargs['pk'])
        self.check_object_permissions(self.request, obj)
        return obj

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
from utils1.ai_match import get_ai_match_score

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



# ai score to talnet for the jobposting owned by the employer 
from .serializers import TalentJobMatchScoreSerializer

class EmployerTalentJobMatchScoreAPIView(APIView):
    """
    GET: /job-postings/<job_posting_id>/applications/<application_id>/ai-score/
    Returns the AI match score between the job's required skills and the applicant's skills.
    """
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser]

    def get(self, request, job_posting_id, application_id, *args, **kwargs):
        job = get_object_or_404(JobPosting, pk=job_posting_id)
        application = get_object_or_404(Application, pk=application_id, job_posting=job)

        job_required_skills = job.required_skills if job.required_skills else []

        # Get user skills from latest resume
        from talent_management.models import Resume
        resume_obj = Resume.objects.filter(talent_id=application.talent, is_deleted=False).order_by('-updated_at').first()
        user_skills = []
        if resume_obj and resume_obj.skills:
            try:
                user_skills = json.loads(resume_obj.skills)
            except Exception:
                user_skills = []

        score = get_ai_match_score(user_skills, job_required_skills)

        data = {
            "job_id": job.id,
            "application_id": application.id,
            "job_required_skills": job_required_skills,
            "user_skills": user_skills,
            "matching_percentage": score,
        }
        serializer = TalentJobMatchScoreSerializer(data)
        return Response(serializer.data, status=200)
    

from .serializers import TalentInterviewListSerializer

class TalentInterviewListView(generics.ListAPIView):
    serializer_class = TalentInterviewListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated or not hasattr(user, 'user_role') or user.user_role != UserRole.TALENT:
            return Interview.objects.none()
        return Interview.objects.filter(application__talent=user).order_by('scheduled_at')


class ApplicationStatusUpdateView(generics.UpdateAPIView):
    """
    API endpoint for an employer to update the status of a specific application.
    This action is restricted to the employer who owns the associated job posting.

    Usage:
    - METHOD: PATCH
    - URL: /api/applications/<application_pk>/update-status/
    - BODY: { "status": "REVIEWED" } or { "status": "REJECTED" }, etc.
    
    The status must be one of the valid choices defined in the ApplicationStatus model.
    """
    queryset = Application.objects.all()
    serializer_class = ApplicationStatusUpdateSerializer
    # permission_classes = [permissions.IsAuthenticated, IsEmployerUser, IsApplicationOwnerOrJobOwner]
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['patch'] # Only allow PATCH requests for partial updates

    def update(self, request, *args, **kwargs):
        """
        Handles the PATCH request to update the application status.
        The permissions check ensures only the correct employer can access this.
        Returns the full, updated application details upon success.
        """
        # A talent user might pass the IsApplicationOwnerOrJobOwner check,
        # but employers should be the only ones changing status here (except for withdrawals).
        # The IsEmployerUser permission class already blocks non-employers.
        if not request.user.is_employer_role:
             raise PermissionDenied("You do not have permission to change the application status.")

        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        # On success, return the full representation of the application
        # using the more detailed serializer for a better frontend experience.
        response_serializer = ApplicationDetailSerializer(instance, context={'request': request})
        return Response("thank you prathamesh, i am very grateful to you for making this api. " + request.data['status']+" successfully ", status=status.HTTP_200_OK)


class ApplicationDeleteView(generics.DestroyAPIView):
    """
    API endpoint for a talent user to withdraw/delete their own application.
    
    This performs a "soft delete" by setting the application status to 'DELETED'
    instead of removing the record from the database. This action is restricted
    to the user who created the application.

    Usage:
    - METHOD: DELETE
    - URL: /api/applications/<id>/
    """
    queryset = Application.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def perform_destroy(self, instance):
        """
        Overrides the default delete behavior. Instead of deleting the object,
        it updates the status to 'DELETED' and saves it.
        """
        # Make sure 'DELETED' is a valid choice in your Application model's status field.
        instance.status = 'DELETED'
        # Using update_fields is more efficient as it only touches the 'status' column.
        instance.save(update_fields=['status'])

    def destroy(self, request, *args, **kwargs):
        """
        Customizes the response message after a successful soft delete.
        The default is to return 204 No Content, but a message is more user-friendly.
        """
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {"detail": "Application has been successfully withdrawn."},
            status=status.HTTP_200_OK  # Return 200 OK with a message
        )




################nikita's code below ###################
from rest_framework.decorators import action
from rest_framework import viewsets


class CombinedDashboardView(APIView):
    """
    Derives dashboard metrics on-the-fly from core models.
    Requires employer authentication.
    """
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser] # <--- ADDED THIS LINE

    def get(self, request):
        # Filter params
        time_range = request.query_params.get('time_range', 'Last 6 Months')
        job_filter = request.query_params.get('job_filter', 'All Jobs')

        # Time filter logic
        end_date = timezone.now()
        date_threshold = {
            'Last Month': end_date - timedelta(days=30),
            'Last 3 Months': end_date - timedelta(days=90),
            'Last 6 Months': end_date - timedelta(days=180),
            'Last Year': end_date - timedelta(days=365)
        }.get(time_range, end_date - timedelta(days=180)) # Default to Last 6 Months

        # Base query
        applications_qs = Application.objects.filter(application_date__gte=date_threshold)
        interviews_qs = Interview.objects.filter(scheduled_at__gte=date_threshold)

        # Filter by job role if provided
        if job_filter != 'All Jobs':
            applications_qs = applications_qs.filter(job_posting__title__icontains=job_filter)
            interviews_qs = interviews_qs.filter(application__job_posting__title__icontains=job_filter)

        # --- Summary Stats ---
        total_applications = applications_qs.count()
        total_interviews = interviews_qs.count()
        total_hires = applications_qs.filter(status=ApplicationStatus.HIRED).count()
        acceptance_rate = (total_hires / total_applications * 100) if total_applications > 0 else 0

        # --- Application Trend per Month ---
        trend_counter = Counter(applications_qs.datetimes('application_date', 'month'))
        application_trend = [
            {"month": dt.strftime("%b %Y"), "application_count": count}
            for dt, count in sorted(trend_counter.items())
        ]

        # --- Recent Activity (last 5 applications) ---
        recent_activities = applications_qs.order_by('-application_date')[:5]
        recent_activity_list = [
            {
                "candidate_name": f"{app.talent.first_name or ''} {app.talent.last_name or ''}".strip() or app.talent.username,
                "activity": f"Applied for {app.job_posting.title}",
                "time_ago": app.application_date.strftime("%b %d, %Y")
            }
            for app in recent_activities
        ]

        # --- Job Performance (average score per job title) ---
        job_perf_raw = applications_qs.values('job_posting__title') \
                                     .annotate(avg_score=Avg('score')) \
                                     .order_by('-avg_score')
        job_performance_data = [
            {"job_role": j['job_posting__title'], "performance_value": round(j['avg_score'] or 0, 2)}
            for j in job_perf_raw
        ]

        return Response({
            "summary_stats": {
                "total_applications": total_applications,
                "total_interviews": total_interviews,
                "total_hires": total_hires,
                "acceptance_rate": f"{acceptance_rate:.2f}%"
            },
            "application_trend": application_trend,
            "recent_activity": recent_activity_list,
            "job_performance": job_performance_data
        }, status=status.HTTP_200_OK)


class HiringAnalyticsDashboardViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API ViewSet for the Hiring Analytics Dashboard.
    Provides top matching candidates with filtering capabilities.
    Requires employer authentication.
    """
    permission_classes = [permissions.IsAuthenticated, IsEmployerUser] # <--- ADDED THIS LINE

    queryset = Application.objects.select_related(
        'job_posting',
        'talent',
    ).prefetch_related(
        'talent__resumes'
    ).all()
    serializer_class = CandidateDashboardSerializer # Ensured this is imported at the top

    def get_queryset(self):
        queryset = super().get_queryset()

        job_filter = self.request.query_params.get('job_filter', '').strip()
        valid_job_filters = {
            'All Jobs', 'AI Engineer', 'ML Specialist', 'Data Scientist', 'NLP Engineer'
        }

        if job_filter and job_filter != 'All Jobs' and job_filter in valid_job_filters:
            queryset = queryset.filter(job_posting__title__iexact=job_filter)
        
        time_range = self.request.query_params.get('time_range', 'Last 6 Months').strip()
        
        end_date = timezone.now()
        start_date = None

        if time_range == 'Last 6 Months':
            start_date = end_date - timedelta(days=6 * 30)
        elif time_range == 'Last 3 Months':
            start_date = end_date - timedelta(days=3 * 30)
        elif time_range == 'Last Month':
            start_date = end_date - timedelta(days=30)
        elif time_range == 'Last Year':
            start_date = end_date - timedelta(days=365)

        if start_date:
            queryset = queryset.filter(application_date__gte=start_date, application_date__lte=end_date)

        queryset = queryset.order_by('-score', '-application_date')

        return queryset

    @action(detail=False, methods=['get'], url_path='top-matching-candidates')
    def top_matching_candidates(self, request):
        """
        Custom action to retrieve top matching candidates with applied filters.
        Accessible at /api/hiring-analytics/top-matching-candidates/
        Query parameters:
        - job_filter: e.g., 'AI Engineer', 'ML Specialist', 'Data Scientist', 'NLP Engineer'
        - time_range: 'Last 6 Months', 'Last 3 Months', 'Last Month', 'Last Year'
        """
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

from django.db import connection     
class EmployerDashboardAPIView(APIView):
    def get(self, request):
        dashboard_data = {}

        # --- 1. Total Applicants with 'applied' status ---
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM gatep_platform_db.employer_management_application 
                WHERE status = 'applied'
            """)
            dashboard_data['total_applicants'] = cursor.fetchone()[0]

        # --- 2. Interviews Scheduled ---
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM gatep_platform_db.employer_management_interview 
                WHERE scheduled_at IS NOT NULL
            """)
            dashboard_data['interview_scheduled'] = cursor.fetchone()[0]

        # --- 3. Active Jobs where is_active = 1 ---
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM gatep_platform_db.employer_management_jobposting 
                WHERE is_active = 1
            """)
            dashboard_data['active_jobs'] = cursor.fetchone()[0]

        # --- 4. Offer Extended (Placeholder) ---
        dashboard_data['offer_extended'] = 0  # Update when logic is available

        return Response(dashboard_data)

import re

class EmployerAnalyticsDemographicAPIView(APIView):
    # permission_classes = [permissions.IsAuthenticated, IsEmployerUser]
 
    def get(self, request):
        data = {}
 
        # --- Step 1: Fetch all unique required_skills from JobPosting ---
        all_skills_set = set()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT required_skills
                FROM gatep_platform_db.employer_management_jobposting
                WHERE required_skills IS NOT NULL AND required_skills != ''
            """)
            skill_rows = cursor.fetchall()
 
        for row in skill_rows:
            raw = row[0]
            if raw:
                # Try to extract quoted skills (JSON-like), else fallback to comma-split
                skills = re.findall(r'"([^"]+)"', raw) or raw.split(',')
                all_skills_set.update(skill.strip().lower() for skill in skills if skill.strip())
 
        # --- Step 2: Count how many times each skill appears in Resume.skills ---
        skill_distribution = []
        with connection.cursor() as cursor:
            for skill in sorted(all_skills_set):
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM gatep_platform_db.talent_management_resume
                    WHERE LOWER(skills) LIKE %s
                """, [f"%{skill}%"])
                count = cursor.fetchone()[0]
                skill_distribution.append({
                    "skill": skill,
                    "count": count
                })
 
        data["skill_distribution"] = skill_distribution
 
        # --- Step 3: Candidate location counts ---
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT current_district, COUNT(*)
                FROM gatep_platform_db.talent_management_resume
                WHERE current_district IS NOT NULL AND current_district != ''
                GROUP BY current_district
            """)
            location_rows = cursor.fetchall()
 
        candidate_locations = [
            {"location": row[0], "candidates": row[1]}
            for row in location_rows
        ]
 
        data["candidate_locations"] = candidate_locations
 
        return Response(data)
    
###################### nikita's code end ##############################