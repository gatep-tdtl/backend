from django.urls import path
from employer_management.views import (
    CompanyListCreateView, CompanyDetailView,
    JobPostingListCreateView, JobPostingDetailView,
    InterviewListCreateView, InterviewDetailView,
    EmployerApplicationListForJobView,
    EmployerApplicationDetailView,
)

urlpatterns = [
    # 🔹 Company Management
    path('companies/', CompanyListCreateView.as_view(), name='company-list-create'),
    path('companies/<int:pk>/', CompanyDetailView.as_view(), name='company-detail'),

    # 🔹 Job Postings
    path('job-postings/', JobPostingListCreateView.as_view(), name='jobposting-list-create'),
    path('job-postings/<int:pk>/', JobPostingDetailView.as_view(), name='jobposting-detail'),

    # 🔹 Employer-Specific Applications
    path('job-postings/<int:job_posting_id>/applications/', EmployerApplicationListForJobView.as_view(), name='employer-job-applications-list'),
    path('job-postings/<int:job_posting_id>/applications/<int:pk>/', EmployerApplicationDetailView.as_view(), name='employer-job-application-detail'),

    # 🔹 Interviews
    path('interviews/', InterviewListCreateView.as_view(), name='interview-list-create'),
    path('interviews/<int:pk>/', InterviewDetailView.as_view(), name='interview-detail'),
    
]
