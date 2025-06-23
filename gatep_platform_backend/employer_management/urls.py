from django.urls import path
from employer_management.views import (
    CompanyListCreateView, CompanyDetailView,
    JobPostingListCreateView, JobPostingDetailView,
    ApplicationListCreateView, ApplicationDetailView,
    InterviewListCreateView, InterviewDetailView,
    SaveJobView, UnsaveJobView, ListSavedJobsView,
    EmployerApplicationListForJobView, EmployerApplicationDetailView,
    JobListWithMatchingScoreAPIView
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

    # Saved Jobs
    path('saved-jobs/', SaveJobView.as_view(), name='savedjob-list-create'),
    path('unsave-jobs/', UnsaveJobView.as_view(), name='unsavedjob-list-create'),
    path('List-Saved-Jobs-View/', ListSavedJobsView.as_view(), name='savedjob-list-view'),

    # Job posts with AI score and summary
    path('job-postings/ai-score/', JobListWithMatchingScoreAPIView.as_view(), name='jobposting-ai-score'),
]
