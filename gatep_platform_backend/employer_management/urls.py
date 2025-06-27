from django.urls import path
from employer_management.views import (
    CompanyListCreateView, CompanyDetailView,
    JobPostingListCreateView, JobPostingDetailView,
    ApplicationListCreateView, ApplicationDetailView,
    InterviewListCreateView, InterviewDetailView,
    SaveJobView, UnsaveJobView, ListSavedJobsView,
    EmployerApplicationListForJobView, EmployerApplicationDetailView,
    JobListWithMatchingScoreAPIView,
    EmployerCompanyView
)

urlpatterns = [
    # Company Management
    path('companies/', CompanyListCreateView.as_view(), name='company-list-create'),
    path('companies/<int:pk>/', CompanyDetailView.as_view(), name='company-detail'),

    # Job Postings
    path('job-postings/', JobPostingListCreateView.as_view(), name='jobposting-list-create'),
    path('job-postings/<int:pk>/', JobPostingDetailView.as_view(), name='jobposting-detail'),

    # Application Management (for talents)
    path('applications/', ApplicationListCreateView.as_view(), name='application-list-create'),
    path('applications/<int:pk>/', ApplicationDetailView.as_view(), name='application-detail'),

    # Employer-Specific Applications
    path('job-postings/<int:job_posting_id>/applications/', EmployerApplicationListForJobView.as_view(), name='employer-job-applications-list'),
    path('job-postings/<int:job_posting_id>/applications/<int:pk>/', EmployerApplicationDetailView.as_view(), name='employer-job-application-detail'),

    # Interviews
    path('interviews/', InterviewListCreateView.as_view(), name='interview-list-create'),
    path('interviews/<int:pk>/', InterviewDetailView.as_view(), name='interview-detail'),

   # 🔹 Saved Jobs
    path('saved-jobs/', ListSavedJobsView.as_view(), name='saved-jobs-list'),
    path('saved-jobs/save/', SaveJobView.as_view(), name='save-job'),
    path('saved-jobs/unsave/', UnsaveJobView.as_view(), name='unsave-job'),

    # Job posts with AI score and summary
    path('job-postings/ai-score/', JobListWithMatchingScoreAPIView.as_view(), name='jobposting-ai-score'),

    # Employer Company
    path('my-company/', EmployerCompanyView.as_view(), name='employer-company'),
]
